"""Background thread that runs the crawl + detection pipeline so the UI
never freezes while a scan is in progress.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

import applog
import site_session
import suppression
from crawler import CrawlConfig, crawl
from detectors.base import DetectorUnavailable
from detectors.factory import DetectorFactory
from models import (
    AnalysisResult, CodeBlock, PageResult, RepoAnalysisResult,
    ScanDiagnostics, TextBlock, TextSpan,
)
from repo_scanner import ScanConfig, scan_file, scan_repo


def _apply_suppressions(result, settings, root):
    """Drop findings the user has already decided about.

    Applied once, at the end of a scan, rather than inside each detector:
    the suppression list is a statement about findings, and a detector that
    knew about it would have to be handed it by every caller.
    """
    if settings is None:
        return result.spans
    suppressions = suppression.Suppressions.load(settings, root)
    blocks_by_id = {b.block_id: b for b in result.blocks()}
    return suppression.filter_spans(result.spans, blocks_by_id, suppressions)


def run_unicode_pass(blocks, categories, selected_detector: str = "") -> list:
    """Run the non-keyboard-character pass on top of the selected detector.

    It answers a different question from any content detector (exact
    character defects vs. probabilistic style) and costs nothing, so it is
    worth running whichever paid backend the user picked.

    It is skipped when the selected detector already contains this pass (the
    offline one, and the hybrid one that wraps it) — running it again there
    produced every character finding twice. Asked of the detector class
    rather than of its name, so a third such backend cannot be added without
    this staying true. `categories` falsy disables it entirely.
    """
    if not categories:
        return []
    detector_cls = DetectorFactory.lookup(selected_detector)
    if getattr(detector_cls, "includes_character_pass", False):
        return []
    detector = DetectorFactory.create(
        "offline", categories=tuple(categories), include_style=False
    )
    return detector.analyze_blocks(blocks)


class _PairingMixin:
    """Shared by the workers that can be handed a checkout to pair against."""

    def _pair_with_repo(self, blocks) -> None:
        """Name the file behind each passage, and count what was explained.

        Failure here is deliberately not failure of the run: the scan already
        found what it found, and a checkout that cannot be walked - a path
        that moved, a permission - must not throw that away. The counts stay
        at zero, which is what the window reports.
        """
        import repo_pairing

        from duplicates import distinct_blocks

        try:
            index = repo_pairing.index_for_path(
                self.paired_repo, self.paired_ignore,
                max_files=getattr(self.settings, "max_files", 5000) or 5000)
        except Exception as exc:  # noqa: BLE001 - the findings still stand
            applog.error("pairing.failed", repo=self.paired_repo, error=str(exc))
            return
        self.paired_total = len(distinct_blocks(blocks))
        repo_pairing.pair_blocks(blocks, index)
        self.paired_matched = sum(bool(rep.source_candidates) for rep, _ in distinct_blocks(blocks))


class AnalysisWorker(_PairingMixin, QThread):
    crawling = Signal(str, int)          # url, depth
    detecting = Signal(str)              # detector display name
    finished_ok = Signal(object)         # AnalysisResult
    failed = Signal(str)                 # error message

    def __init__(self, root_url: str, depth: int, detector_name: str,
                 detector_config: dict, max_pages: int = 30,
                 unicode_categories: tuple | None = None, settings=None,
                 pages: list | None = None, paired_repo: str = "",
                 no_session: bool = False,
                 paired_ignore=None, crawl=None, session_host: str = "",
                 session_values: int = 0, cancellation=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        #: `--repo`: the checkout that serves this site. Given one, every
        #: passage that also exists in it gets a file and a line, so a
        #: finding stops being "somewhere on the pricing page". Empty is the
        #: normal case and changes nothing. See `repo_pairing`.
        self.paired_repo = (paired_repo or "").strip()
        #: `--no-session`: ignore any stored sign-in for this host. Off, so
        #: the ordinary run is the one that reads what the person can see.
        self.no_session = bool(no_session)
        self.paired_ignore = list(paired_ignore or [])
        #: How many distinct passages the checkout explained, and how many
        #: there were. Read by the window: three matches out of forty means
        #: the wrong checkout, and a surface that showed only the three
        #: would never say so.
        self.paired_matched = 0
        self.paired_total = 0
        #: Which host's stored session this run used, and how many values it
        #: carried. The count is for the status line; the values never leave
        #: `site_session`.
        self.session_host = session_host or ""
        self.session_values = int(session_values or 0)
        self.ignore_root = None  # a URL has no folder to hold an ignore file
        #: Pages already fetched by an earlier run over the same target. Given
        #: them, this worker never touches the network: the expensive half of a
        #: scan is getting the documents, and changing the question about them
        #: is not a reason to fetch them again.
        self.pages = pages
        self.root_url = root_url
        self.depth = depth
        self.detector_name = detector_name
        self.detector_config = detector_config
        self.max_pages = max_pages
        self.unicode_categories = unicode_categories
        self.crawl = crawl
        self.cancellation = cancellation
        self.acquired_pages = None
        self.acquired_files = None
        self.scan_diagnostics = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        if self.cancellation is not None:
            self.cancellation.cancel()

    def _is_cancelled(self) -> bool:
        return self._cancelled or bool(
            self.cancellation and self.cancellation.cancelled)

    def run(self) -> None:
        try:
            def progress_cb(url: str, depth: int) -> None:
                self.crawling.emit(url, depth)

            from models import CrawlDiagnostics
            walk = self.crawl or CrawlDiagnostics()
            if self.pages is not None:
                pages: list[PageResult] = self.pages
            else:
                config = CrawlConfig(max_depth=self.depth, max_pages=self.max_pages)
                # Read as the person who signed in, when they did. Both
                # clients or neither: see `site_session.apply_to`.
                # `no_session` is `--no-session`: read the site the way a
                # stranger sees it, which is the only way to find out that
                # half of it is behind a door.
                if not self.no_session:
                    self.session_host, self.session_values = \
                        site_session.apply_to(config, self.root_url)
                pages = crawl(self.root_url, config, progress_cb=progress_cb,
                              walk=walk, cancelled=self._is_cancelled)
            if self._is_cancelled():
                return

            try:
                detector = DetectorFactory.create(self.detector_name, **self.detector_config)
            except KeyError as exc:
                self.failed.emit(str(exc))
                return

            self.detecting.emit(detector.display_name)

            result = AnalysisResult(root_url=self.root_url, pages=pages,
                                    crawl=walk)
            all_blocks = result.blocks()
            try:
                result.spans = detector.analyze_blocks(all_blocks)
            except DetectorUnavailable as exc:
                self.failed.emit(str(exc))
                return
            result.spans.extend(
                run_unicode_pass(all_blocks, self.unicode_categories, self.detector_name)
            )
            result.spans = _apply_suppressions(result, self.settings, self.ignore_root)

            if self.paired_repo:
                self._pair_with_repo(all_blocks)

            if self._is_cancelled():
                return
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001 - surface any unexpected failure to the UI
            self.failed.emit(str(exc))


class SingleBlockWorker(QThread):
    """Re-runs one detector on a single block — used by the "additional
    analysis" button in the detail panel, so a deeper (e.g. Claude-backed)
    pass on one flagged passage doesn't require rescanning the whole site.
    """
    finished_ok = Signal(list)   # list[TextSpan]
    failed = Signal(str)

    def __init__(self, block: TextBlock, detector_name: str, detector_config: dict, parent=None):
        super().__init__(parent)
        self.block = block
        self.detector_name = detector_name
        self.detector_config = detector_config

    def run(self) -> None:
        try:
            detector = DetectorFactory.create(self.detector_name, **self.detector_config)
            spans = detector.analyze_block(self.block)
            self.finished_ok.emit(spans)
        except DetectorUnavailable as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class RepoAnalysisWorker(QThread):
    """Repo-mode counterpart to AnalysisWorker: walks a local folder instead
    of crawling a URL, then runs the same Detector interface over whatever
    tag-embedded text it found.
    """
    scanning = Signal(str)                # relative file path
    detecting = Signal(str)               # detector display name
    finished_ok = Signal(object)          # RepoAnalysisResult
    failed = Signal(str)

    def __init__(self, root_dir: str, ignore_patterns: list[str], detector_name: str,
                 detector_config: dict, unicode_categories: tuple | None = None,
                 scope: str = "content", settings=None,
                 files: list | None = None, diagnostics=None,
                 cancellation=None, extensions: tuple[str, ...] | None = None,
                 incremental: bool = False, parent=None):
        super().__init__(parent)
        self.settings = settings
        #: Files extracted by an earlier run. They are only consulted when
        #: incremental mode is on, and `scan_repo` compares their complete
        #: source text before reusing blocks.
        self.files = files
        self.incremental = bool(incremental)
        self.extensions = extensions
        self.ignore_root = root_dir
        self.root_dir = root_dir
        self.ignore_patterns = ignore_patterns
        self.scope = scope
        self.detector_name = detector_name
        self.detector_config = detector_config
        self.unicode_categories = unicode_categories
        self.diagnostics = diagnostics
        self.cancellation = cancellation
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        if self.cancellation is not None:
            self.cancellation.cancel()

    def _is_cancelled(self) -> bool:
        return self._cancelled or bool(
            self.cancellation and self.cancellation.cancelled)

    def run(self) -> None:
        try:
            def progress_cb(rel_path: str) -> None:
                self.scanning.emit(rel_path)

            from pathlib import Path

            walk = self.diagnostics or ScanDiagnostics()
            if Path(self.root_dir).is_file():
                # One named file, which is what the HTML-file source asks for.
                # Naming a file is an instruction to read it, so neither the
                # extension list nor the exclusions apply - the same rule the
                # CLI already follows for a named path.
                progress_cb(Path(self.root_dir).name)
                files = [scan_file(self.root_dir, self.scope)]
            else:
                config = ScanConfig(ignore_patterns=self.ignore_patterns,
                                    extensions=self.extensions,
                                    scope=self.scope,
                                    # The window's own ceiling, which it now
                                    # has: `Settings.max_files`, the same
                                    # number `--max-files` sets.
                                    max_files=getattr(self.settings,
                                                      "max_files", 5000) or 5000)
                # The walk's own account of itself. Without it the window
                # could not tell "read 1732 files, nothing crossed the
                # threshold" from "stopped at the cap after 500" - and it
                # used to do the second while showing the first.
                walk = ScanDiagnostics()
                files = scan_repo(self.root_dir, config, progress_cb=progress_cb,
                                  diagnostics=walk, cancelled=self._is_cancelled,
                                  reusable_files=(self.files
                                                  if self.incremental else None))
            if self._is_cancelled():
                return

            try:
                detector = DetectorFactory.create(self.detector_name, **self.detector_config)
            except KeyError as exc:
                self.failed.emit(str(exc))
                return

            self.detecting.emit(detector.display_name)

            result = RepoAnalysisResult(root_dir=self.root_dir, files=files,
                                        diagnostics=walk)
            all_blocks = result.blocks()
            try:
                result.spans = detector.analyze_blocks(all_blocks)
            except DetectorUnavailable as exc:
                self.failed.emit(str(exc))
                return
            result.spans.extend(
                run_unicode_pass(all_blocks, self.unicode_categories, self.detector_name)
            )
            result.spans = _apply_suppressions(result, self.settings, self.ignore_root)

            if self._is_cancelled():
                return
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class AuditWorker(QThread):
    """The accessibility/SEO/performance audit, off the UI thread.

    Separate from `AnalysisWorker` rather than a flag on it because the two
    answer different questions about the same page and produce different
    result types: one finds passages a person wrote, the other finds defects
    in the document. Sharing a worker would mean every caller unpacking a
    union.

    The browser pass is deliberately **not** here. QtWebEngine is only usable
    from the thread that owns the application, so it runs on the main thread
    after this worker finishes; see `MainWindow._run_browser_pass`.
    """
    crawling = Signal(str, int)     # url, depth
    auditing = Signal(str)          # what is being audited right now
    finished_ok = Signal(object)    # audit.AccessibilityResult
    failed = Signal(str)

    def __init__(self, target: str, depth: int, max_pages: int = 30,
                 is_repo: bool = False, is_page_file: bool = False,
                 ignore_patterns=None, max_files: int = 5000,
                 settings=None, pages: list | None = None,
                 site_controls: bool = False, medium: str = "",
                 within: str = "", web_parts=(), no_session: bool = False,
                 crawl=None, session_host: str = "", session_values: int = 0,
                 cancellation=None, extensions: tuple[str, ...] | None = None,
                 files: list | None = None, incremental: bool = False,
                 sharepoint=None, parent=None):
        super().__init__(parent)
        #: `cli_impl.auditpass.SharePointRun` for this target, or `None`.
        #: Decided by the caller through `plan_sharepoint`, the function the
        #: CLI decides it through, so the window and the command line read a
        #: SharePoint site the same way: its page tree, inside its own site
        #: path, with Microsoft's chrome out of the audit.
        self.sharepoint = sharepoint
        #: `sharepoint_tree.SiteTree` the page list came from, or `None`.
        self.page_tree = None
        #: `--within`: confine the reading to one subtree. The document is
        #: then a *fragment* by construction, so the page-level rules stop
        #: applying - it has no `<head>` to carry a canonical link and no
        #: business owning the page's only `<h1>`. A selector that matches
        #: nothing comes back as an error on that document rather than as a
        #: clean result.
        self.within = (within or "").strip()
        self.session_host = session_host or ""
        self.session_values = int(session_values or 0)
        #: `--medium`: "web", "email", or empty for "read it off each file".
        #: Only the folder branch reads it - a crawled site is a site, and a
        #: single page file is autodetected the same way the CLI does it.
        self.medium = medium
        #: `--site-controls`: also fetch robots.txt and the same-origin
        #: sitemaps it declares. Off unless asked for - it is two requests to
        #: an address the user did not type - and meaningless off the web,
        #: which is why only the crawl branch below reads it.
        self.site_controls = site_controls
        #: `--web-parts`: the SPFx parts read out of the paired checkout, so
        #: the audit is confined to what this repository actually ships into
        #: somebody else's page. Empty is the ordinary case, and an empty
        #: tuple audits the whole document exactly as before.
        self.web_parts = tuple(web_parts or ())
        #: `--no-session`: see `WebAnalysisWorker.no_session`.
        self.no_session = bool(no_session)
        #: Pages already fetched - by an earlier run, or by the browser on the
        #: main thread. Given them, this worker does not crawl: a run that asks
        #: both questions about one site must fetch it once.
        self.pages = pages
        self.target = target
        self.depth = depth
        self.max_pages = max_pages
        self.is_repo = is_repo
        self.is_page_file = is_page_file
        self.ignore_patterns = list(ignore_patterns or [])
        self.max_files = max_files
        self.extensions = extensions
        self.files = files
        self.incremental = bool(incremental)
        self.settings = settings
        self.crawl = crawl
        self.cancellation = cancellation
        #: What this run actually read, handed to the view model so a
        #: second pass reuses it instead of fetching again. Declared here
        #: rather than only in `run`, so a branch that reads nothing - a
        #: single page file - still answers the question.
        self.acquired_pages = None
        self.acquired_files = None
        self.scan_diagnostics = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        if self.cancellation is not None:
            self.cancellation.cancel()

    def _is_cancelled(self) -> bool:
        return self._cancelled or bool(
            self.cancellation and self.cancellation.cancelled)

    def run(self) -> None:
        try:
            import audit

            if self.is_page_file:
                # One file, read as a whole page. No crawl and no scan: the
                # user pointed at the document itself.
                self.auditing.emit(self.target)
                result = audit.analyze_page_file(self.target,
                                                 within=self.within,
                                                 web_parts=self.web_parts)
                ignore_root = None
            elif self.is_repo:
                walk = ScanDiagnostics()
                files = scan_repo(self.target,
                                  ScanConfig(ignore_patterns=self.ignore_patterns,
                                             extensions=self.extensions,
                                             max_files=self.max_files),
                                  diagnostics=walk,
                                  cancelled=self._is_cancelled,
                                  reusable_files=(self.files
                                                  if self.incremental else None))
                self.acquired_files = files
                self.scan_diagnostics = walk
                if self._is_cancelled():
                    return
                self.auditing.emit(self.target)
                result = audit.analyze_files(files, self.target,
                                             force_medium=self.medium or None)
                ignore_root = self.target
            else:
                def progress_cb(url: str, depth: int) -> None:
                    self.crawling.emit(url, depth)

                if self.pages is not None:
                    pages = self.pages
                else:
                    from models import CrawlDiagnostics

                    walk = self.crawl or CrawlDiagnostics()
                    config = CrawlConfig(max_depth=self.depth,
                                         max_pages=self.max_pages)
                    if not self.no_session:
                        self.session_host, self.session_values = \
                            site_session.apply_to(config, self.target)
                    pages = self._crawl(config, walk, progress_cb)
                    self.crawl = walk
                    if pages is None:
                        return
                self.acquired_pages = pages
                if self._is_cancelled():
                    return
                self.auditing.emit(self.target)
                result = audit.analyze_pages(pages, self.target,
                                             site_controls=self.site_controls,
                                             within=self.within,
                                             web_parts=self.web_parts,
                                             **self._sharepoint_kwargs())
                ignore_root = None

            # The same list that governs the text scan: a user who said "not
            # this part of the page" meant it for the whole tool.
            if self.settings is not None:
                suppressions = suppression.Suppressions.load(self.settings, ignore_root)
                for document in result.documents:
                    document.issues = suppression.filter_issues(document.issues, suppressions)

            if self._is_cancelled():
                return
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001 - surface any unexpected failure to the UI
            self.failed.emit(str(exc))

    def _crawl(self, config, walk, progress_cb):
        """The pages of the site, or `None` after saying why there are none.

        A SharePoint run goes through `auditpass.sharepoint_pages`: the
        site's page tree, inside its own path. When the tree answers that the
        sign-in is missing or not enough, nothing was crawled, and auditing
        an empty list would be reported as a clean site - so the run fails
        with the CLI's own sentence instead.
        """
        plan = self.sharepoint
        if plan is None or not plan.sharepoint:
            return crawl(self.target, config, progress_cb=progress_cb,
                         walk=walk, cancelled=self._is_cancelled)
        from cli_impl import auditpass

        pages, tree = auditpass.sharepoint_pages(
            self.target, config, page_tree=plan.page_tree,
            site_scope=plan.site_scope, progress_cb=progress_cb,
            cancelled=self._is_cancelled, walk=walk)
        self.page_tree = tree
        refusal = auditpass.tree_refusal(tree, self.target)
        if refusal and not pages:
            self.failed.emit(refusal)
            return None
        return pages

    def _sharepoint_kwargs(self) -> dict:
        plan = self.sharepoint
        if plan is None or not plan.sharepoint:
            return {}
        return {"sharepoint": True}


def audit_worker_for(source: str, *, target: str, depth: int, max_pages: int,
                     pages=None, ignore_patterns=None, max_files: int = 5000,
                     settings=None, site_controls: bool = False,
                     medium: str = "", within: str = "", web_parts=(),
                     no_session: bool = False, crawl=None,
                     session_host: str = "", session_values: int = 0,
                     cancellation=None, extensions: tuple[str, ...] | None = None,
                     files: list | None = None, incremental: bool = False,
                     sharepoint=None, parent=None):
    """The right `AuditWorker` for the source, or `(None, message)` on refusal.

    One place, because there were two: the window and the view model each
    built this worker, and both built it the same wrong way. Neither ever
    passed `is_repo`, and both prefixed `https://` onto anything that was not
    a single file - so auditing a *folder* sent `https:///Users/me/project`
    to the crawler. That produced one document with a fetch error and zero
    findings, and the window reported it as a clean audit. Accessibility
    auditing of a repository did not work at all from the desktop app.

    Returns `(worker, "")` or `(None, reason)`.
    """
    from analysis_modes import SOURCE_FILE, SOURCE_REPO
    from cli_impl.auditpass import looks_like_url, with_scheme

    target = (target or "").strip()
    if not target:
        return None, "no_target"

    if source == SOURCE_REPO:
        # A folder of source files. Walked and audited as files, never
        # fetched: there is no server, and the templates in it are not pages
        # a browser could load.
        return AuditWorker(target=target, depth=0, max_pages=max_pages,
                           is_repo=True, ignore_patterns=ignore_patterns,
                           max_files=max_files, settings=settings,
                           medium=medium, cancellation=cancellation,
                           extensions=extensions, files=files,
                           incremental=incremental,
                           parent=parent), ""
    if source == SOURCE_FILE:
        return AuditWorker(target=target, depth=0, max_pages=max_pages,
                           is_page_file=True, settings=settings,
                           within=within, web_parts=web_parts,
                           cancellation=cancellation, parent=parent), ""

    # A site. `example.com` is accepted here exactly as the CLI accepts it,
    # rather than only `https://example.com`.
    address = with_scheme(target) if looks_like_url(target) else target
    if not address.startswith(("http://", "https://")):
        return None, "not_a_url"
    return AuditWorker(pages=pages, target=address, depth=depth,
                       max_pages=max_pages, settings=settings,
                       site_controls=site_controls, within=within,
                       web_parts=web_parts, no_session=no_session,
                       crawl=crawl, session_host=session_host,
                       session_values=session_values,
                       cancellation=cancellation, sharepoint=sharepoint,
                       parent=parent), ""


class RewriteAllWorker(QThread):
    """Generates a human-sounding rewrite for every (block, span) passed in
    that doesn't already have a draft, through whichever LLM provider is
    configured (own Anthropic key or xformat.net subscription). Powers both
    repo-mode buttons — "generate replacement list" stops after this;
    "auto-replace in files" chains a file_writer.apply_replacements call
    onto the result.

    Partial results are kept: if a call fails or the user cancels halfway,
    whatever was already rewritten is still handed back rather than thrown
    away, since each one costs a billable request.
    """
    progress = Signal(int, int)   # done, total
    finished_ok = Signal(object)  # dict[(block_id, start, end)] -> rewritten text
    failed = Signal(str)

    def __init__(self, items: list[tuple[CodeBlock, TextSpan]], settings, parent=None):
        super().__init__(parent)
        self.items = items
        self.settings = settings
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        import rewriter
        from llm.base import LLMUnavailable

        results: dict[tuple, str] = {}
        try:
            # Built once and reused: one HTTP session / API client and one
            # auth token for the whole batch instead of per passage.
            provider = rewriter.build_provider(self.settings)
        except (LLMUnavailable, KeyError) as exc:
            self.failed.emit(str(exc))
            return

        total = len(self.items)
        for i, (block, span) in enumerate(self.items):
            if self._cancelled:
                self.finished_ok.emit(results)
                return
            try:
                original = block.text[span.start:span.end]
                rewritten = provider.rewrite(original, block.language_hint)
                results[(block.block_id, span.start, span.end)] = rewritten
            except Exception as exc:  # noqa: BLE001
                if results:
                    self.finished_ok.emit(results)
                self.failed.emit(str(exc))
                return
            self.progress.emit(i + 1, total)

        self.finished_ok.emit(results)


class SingleRewriteWorker(QThread):
    """Rewrites one passage through the configured provider — powers the
    detail panel's per-passage rewrite button, so a single fix doesn't
    require running the whole bulk job."""
    finished_ok = Signal(str)     # rewritten text
    failed = Signal(str)

    def __init__(self, text: str, language: str | None, settings, parent=None):
        super().__init__(parent)
        self.text = text
        self.language = language
        self.settings = settings
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        import rewriter
        try:
            provider = rewriter.build_provider(self.settings)
            result = provider.rewrite(self.text, self.language)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        if not self._cancelled:
            self.finished_ok.emit(result)


class DevServerWorker(QThread):
    """Installs (if confirmed) and starts a repo's own dev server.

    Off the UI thread because either half can take well over a minute -
    `npm install` on a real project, or a bundler's cold start - and the
    window must not freeze for either. The confirmation itself is not this
    worker's job: it is asked on the UI thread, synchronously, before this
    is even constructed (see `MainWindow._on_analyze_clicked`), exactly like
    the cheap detection that decides whether to ask at all. This worker only
    ever does the part that has to run in the background.
    """
    ready = Signal(str, object)  # local URL, the running DevServerProcess
    failed = Signal(str)         # why it never became ready

    def __init__(self, repo_path: str, install_confirmed: bool,
                 start_command: str = "", port: int = 0, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.install_confirmed = install_confirmed
        #: `--start-command`: what to run instead of the detected script.
        #: Split here, at the boundary, so a fixed argv is what reaches
        #: `devserver.build_plan` - the same contract the CLI has.
        self.start_command = (start_command or "").strip()
        #: `--dev-server-port`: the port to expect, for the stacks that do
        #: not announce their own (Django, Rails).
        self.port = int(port or 0)
        self.proc = None

    def run(self) -> None:
        import devserver
        from pathlib import Path

        try:
            repo = Path(self.repo_path)
            stack = devserver.detect_stack(repo)
            if stack is None:
                self.failed.emit("no dev server detected")
                return
            import shlex

            start_argv = (shlex.split(self.start_command)
                          if self.start_command else None)
            plan = devserver.build_plan(stack, repo, start_argv=start_argv,
                                        port=self.port or None)
            if plan.install_argv is not None:
                if not self.install_confirmed:
                    self.failed.emit(
                        f"{stack.name}: dependencies missing, install declined")
                    return
                try:
                    devserver.run_install(plan)
                except devserver.DevServerInstallFailed as exc:
                    self.failed.emit(str(exc))
                    return
            self.proc = devserver.DevServerProcess.start(plan)
            try:
                url = self.proc.wait_ready(60)
            except devserver.DevServerNeverReady as exc:
                self.proc.stop()
                self.failed.emit(str(exc))
                return
            self.ready.emit(url, self.proc)
        except Exception as exc:  # noqa: BLE001 - surfaced, not swallowed
            self.failed.emit(str(exc))
