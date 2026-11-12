"""ViewModel: business logic separated from UI.

MainViewModel owns the workers, caching, and action handlers that used
to live directly on MainWindow. The window forwards user actions here
and subscribes to signals for results, progress, and errors.

Design:
- AppState owns the user's choices (source, reader, check, method).
- ViewModel owns what happens when the user acts (analyze, rewrite, fix).
- MainWindow owns the widgets and layout.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

import config
import suppression
from analysis_modes import (
    SOURCE_FILE,
    SOURCE_REPO,
    SOURCE_SITE,
    AnalysisRequest,
    ExtractionSnapshot,
    RunContext,
)
from detectors.factory import DetectorFactory
from detectors.judges import judge_for_provider
from models import AnalysisResult, RepoAnalysisResult, TextSpan
from ui.app_state import AppState
from ui.worker import (
    AnalysisWorker,
    RepoAnalysisWorker,
    RewriteAllWorker,
    SingleRewriteWorker,
)


def _browser_url(source: str) -> str:
    if source.startswith(("http://", "https://", "file://")):
        return source
    return Path(source).resolve().as_uri()


class MainViewModel(QObject):
    """Business logic for the main window.

    Signals carry results and status to the UI layer. The UI never
    accesses workers, caches, or settings directly - it goes through
    this object.
    """

    # -- result signals ----------------------------------------------------
    web_result_ready = Signal(object)       # AnalysisResult
    repo_result_ready = Signal(object)      # RepoAnalysisResult
    audit_result_ready = Signal(object)     # AuditResult
    rewrite_ready = Signal(object)          # dict[tuple, str]
    single_rewrite_ready = Signal(object, object)  # (key, draft)

    # -- progress signals --------------------------------------------------
    status_message = Signal(str)            # status bar text
    crawling = Signal(str, int)             # (url, depth)
    scanning = Signal(str)                  # repo file path
    detecting = Signal(str)                 # detector phase
    auditing = Signal(str)                  # audit target

    # -- error signal ------------------------------------------------------
    error = Signal(str)                     # error message

    # -- browser pass signal -----------------------------------------------
    browser_pass_needed = Signal()          # audit done, browser pass needed

    # -- UI dialog signals -------------------------------------------------
    undo_outcome = Signal(str)              # message
    download_choice_needed = Signal(bool, bool)  # (has_audit, has_text)
    unicode_fixed = Signal(int)             # filled count

    # -- state signals -----------------------------------------------------
    busy_changed = Signal(bool)             # analysis running or not
    buttons_changed = Signal()              # recompute button enabled state

    def __init__(self, app_state: AppState, settings: config.Settings,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.state = app_state
        self.settings = settings

        # Results
        self.result: AnalysisResult | RepoAnalysisResult | None = None
        self.audit_result: Any | None = None
        self.drafts: dict[tuple, str] = {}

        # Workers
        self._worker = None
        self._rewrite_worker: RewriteAllWorker | None = None
        self._active_workers: list = []

        # One run, one acquisition snapshot. Compatibility properties below
        # expose the old cache names to the window while this is the owner.
        self._last_request: AnalysisRequest | None = None
        self._run_context: RunContext | None = None
        self._snapshot: ExtractionSnapshot | None = None
        self._acquired_crawl = None
        self._acquired_session_host = ""
        self._acquired_session_values = 0

        # Repo config. The person's own list; what the *run* uses is
        # `effective_ignore_patterns`, which adds what the detected stack
        # says is not theirs. Two names because they are two facts, and
        # storing the sum would make the person's own list unrecoverable the
        # moment a profile was detected.
        self.repo_ignore_patterns: list[str] = []

        # Pending copy pass (for both-questions runs)
        self._pending_copy_pass = False
        # File mode: run code analysis then browser analysis
        self._file_both_passes = False

    # -- public properties -------------------------------------------------
    @property
    def is_busy(self) -> bool:
        return self._worker is not None

    @property
    def mode(self) -> str:
        return self.state.mode

    @property
    def _extraction_request(self):
        return self._snapshot.request if self._snapshot is not None else None

    @property
    def _cached_pages(self):
        return list(self._snapshot.pages) if self._snapshot and self._snapshot.pages else None

    @property
    def _cached_files(self):
        return list(self._snapshot.files) if self._snapshot and self._snapshot.files else None

    @property
    def _cached_scope(self):
        return self._snapshot.scope if self._snapshot is not None else None

    @property
    def cancellation_requested(self) -> bool:
        return bool(self._run_context and self._run_context.cancellation.cancelled)

    @property
    def session_host(self) -> str:
        return self._snapshot.session_host if self._snapshot is not None else ""

    # -- request building --------------------------------------------------
    def current_request(self) -> AnalysisRequest:
        """Build a normalised request from the current state."""
        return AnalysisRequest(
            source=self.state.source,
            # `scan_target`, not `target`: one project may have been chosen
            # out of a folder that holds several, and every pass has to read
            # the same one.
            target=self.state.scan_target,
            depth=self.state.depth,
            readers=self.state.readers,
            checks=self.state.checks,
            methods=self.state.methods,
            ai_available=self.state.ai_available,
        ).normalised()

    def _ai_available(self) -> bool:
        try:
            import rewriter
            from llm.base import LLMUnavailable
            provider = rewriter.build_provider(self.settings, allow_auto=True)
            try:
                return bool(provider.auth_status().signed_in)
            except LLMUnavailable:
                return False
        except Exception:
            return False

    def refresh_ai_available(self) -> None:
        self.state.set_ai_available(self._ai_available())

    # -- extraction cache --------------------------------------------------
    def _reusable_snapshot(self, *, scope: str | None = None):
        request = self.current_request()
        snapshot = self._snapshot
        if snapshot and snapshot.reusable_for(request, scope=scope):
            return snapshot
        return None

    def _reusable_pages(self):
        request = self.current_request()
        snapshot = self._reusable_snapshot()
        if snapshot is not None and snapshot.pages:
            return snapshot.pages_for(request)
        return None

    def _reusable_files(self):
        scope = self._repo_scope()
        snapshot = self._reusable_snapshot(scope=scope)
        if snapshot is not None and snapshot.files:
            return list(snapshot.files)
        return None

    def _remember_extraction(self, request, *, pages=None, files=None, scope=None,
                             crawl=None, scan=None, session_host=None,
                             session_values=None):
        if request is None:
            return None
        if self._run_context is None or self._run_context.request != request:
            self._run_context = RunContext(request=request)
        evidence = {}
        for name, value in (("pages", pages), ("files", files),
                            ("scope", scope), ("crawl", crawl), ("scan", scan),
                            ("session_host", session_host),
                            ("session_values", session_values)):
            if value is not None:
                evidence[name] = value
        self._snapshot = self._run_context.remember(**evidence)
        return self._snapshot

    def forget_extraction(self):
        self._snapshot = None
        if self._run_context is not None:
            self._run_context.snapshot = None

    def _begin_run(self, request: AnalysisRequest) -> RunContext:
        """Start a fresh user run; reuse is only inside this context."""
        self._run_context = RunContext(request=request)
        self._snapshot = None
        self._acquired_crawl = None
        self._acquired_session_host = ""
        self._acquired_session_values = 0
        return self._run_context

    def _repo_scope(self) -> str:
        return self.state.scope

    # -- detector selection ------------------------------------------------
    def _detector_for_request(self) -> tuple[str, dict]:
        request = self._last_request or self.current_request()
        provider_key = self.state.provider or self.settings.llm_provider
        judge = judge_for_provider(provider_key)
        if request.wants_ai and request.wants_local:
            name = "hybrid"
        elif request.wants_ai:
            name = judge
        elif request.wants_embedding:
            name = "embedding"
        else:
            name = "offline"
        return name, self._detector_config_for(name, judge)

    def _detector_config_for(self, detector_name: str, judge_name: str = "") -> dict:
        resolved = DetectorFactory.resolve(detector_name)
        if resolved == "hybrid":
            judge = judge_name or judge_for_provider(self.settings.llm_provider)
            return {
                "categories": self._active_unicode_categories() or (),
                "judge_name": judge,
                "judge_config": self._detector_config_for(judge),
            }
        if resolved in ("claude-llm-judge", "claude-official-watermark"):
            return {
                "api_key": config.get_anthropic_api_key(),
                "model": self.settings.claude_model,
            }
        if resolved == "xformat-llm-judge":
            return {
                "base_url": self.settings.xformat_base_url,
                "endpoints": self.settings.xformat_endpoints,
            }
        if resolved == "offline":
            return {"categories": self._active_unicode_categories() or ()}
        return {}

    def _active_unicode_categories(self):
        if not self.settings.unicode_check_enabled:
            return None
        return tuple(self.settings.unicode_categories or ())

    # -- analysis actions --------------------------------------------------
    def analyze(self) -> str | None:
        """Start analysis. Returns error message or None on success."""
        request = self.current_request()
        if not request.target:
            return self._missing_target_message()

        for note in request.notes:
            self.status_message.emit(self._note_message(note))

        self._last_request = request
        self._begin_run(request)

        # A browser reader still starts with the static acquisition worker.
        # Network I/O must not happen on the GUI thread, and the later
        # browser audit already loads each page in Chromium. That one load
        # captures the rendered DOM for the copy pass, so there is no hidden
        # pre-render crawl and no third reading of the same revision.
        browser_copy = (request.wants_browser and request.wants_ai_patterns
                        and request.source in (SOURCE_SITE, SOURCE_FILE))
        self._pending_copy_pass = (request.wants_ai_patterns
                                   and (request.wants_accessibility
                                        or browser_copy))
        if request.wants_accessibility or browser_copy:
            self._start_audit()
        else:
            self._start_copy_pass()
        return None

    def _missing_target_message(self) -> str:
        from i18n.translations import t
        lang = self.settings.ui_language
        if self.state.source == SOURCE_REPO:
            return t("no_repo_path", lang)
        if self.state.source == SOURCE_FILE:
            return t("no_file_path", lang)
        return t("url_label_full", lang)

    def _note_message(self, note: str) -> str:
        from i18n.translations import t
        lang = self.settings.ui_language
        if "browser" in note:
            return t("reader_browser_unavailable", lang)
        if "AI pass" in note or "account or key" in note:
            return t("method_ai_unavailable", lang)
        return note

    def _render_for_request(self, request: AnalysisRequest):
        """Browser rendering - must be called from the main thread."""
        from audit import driver

        usable, reason = driver.available()
        if not usable:
            self.error.emit(reason)
            return None

        if request.source == SOURCE_FILE:
            return self._render_single_file(request.target)
        elif request.source == SOURCE_SITE:
            return self._render_crawl(request.target)
        return None

    def _render_crawl(self, url: str):
        import site_session
        from audit import driver
        from crawler import RENDER_AUTO, CrawlConfig
        from models import CrawlDiagnostics

        usable, reason = driver.available()
        if not usable:
            self.error.emit(reason)
            return None

        cfg = CrawlConfig(max_depth=self.state.depth,
                          max_pages=self.settings.max_pages,
                          render_mode=RENDER_AUTO)
        walk = CrawlDiagnostics()
        session_host, session_values = "", 0
        if not self.state.no_session:
            session_host, session_values = site_session.apply_to(cfg, url)
        self._acquired_session_host = session_host
        self._acquired_session_values = session_values

        def progress(page_url: str, _depth: int) -> None:
            from i18n.translations import t
            self.status_message.emit(
                t("status_browser_pass", self.settings.ui_language, url=page_url))

        from cli_impl.auditpass import PAGE_TREE_LINKS, sharepoint_pages

        plan = self._sharepoint_run()
        try:
            with driver.html_renderer(session_host=session_host) as render:
                pages, _tree = sharepoint_pages(
                    url, cfg,
                    page_tree=plan.page_tree if plan else PAGE_TREE_LINKS,
                    site_scope=plan.site_scope if plan else "",
                    progress_cb=progress, render=render, walk=walk,
                    cancelled=self._run_context.cancellation
                    if self._run_context else None)
                self._acquired_crawl = walk
                return pages
        except Exception as exc:
            self.error.emit(str(exc))
            return None

    def _render_single_file(self, path: str):
        from audit import driver
        from crawler import page_from_html

        if not path:
            from i18n.translations import t
            self.error.emit(t("no_file_path", self.settings.ui_language))
            return None
        usable, reason = driver.available()
        if not usable:
            self.error.emit(reason)
            return None
        address = _browser_url(path)
        from i18n.translations import t
        self.status_message.emit(
            t("status_browser_pass", self.settings.ui_language, url=address))
        session_host, session_values = "", 0
        if not self.state.no_session:
            import site_session
            from crawler import CrawlConfig
            cfg = CrawlConfig(max_depth=0, max_pages=1)
            session_host, session_values = site_session.apply_to(cfg, address)
        self._acquired_session_host = session_host
        self._acquired_session_values = session_values
        try:
            with driver.html_renderer(session_host=session_host) as render:
                html = render(address) or ""
        except Exception as exc:
            self.error.emit(str(exc))
            return None
        if not html:
            from i18n.translations import t
            self.error.emit(t("reader_browser_empty", self.settings.ui_language))
            return None
        return [page_from_html(html, address)]

    def _start_copy_pass(self):
        if self.state.source == SOURCE_REPO:
            self._start_repo_analysis()
        elif self.state.source == SOURCE_FILE:
            # File: always run code analysis first, then browser if available.
            # The raw file and the rendered DOM show different things.
            self._file_both_passes = self._reusable_pages() is not None
            self._start_file_copy_analysis()
        else:
            self._start_web_analysis()

    def _start_web_analysis(self, root: str = ""):
        url = root or self.state.scan_target
        if not url:
            from i18n.translations import t
            self.error.emit(t("url_label_full", self.settings.ui_language))
            return
        if not url.startswith(("http://", "https://", "file://")):
            url = "https://" + url

        detector_name, detector_config = self._detector_for_request()
        reused = self._reusable_pages()
        snapshot = self._reusable_snapshot()
        if reused is not None:
            from i18n.translations import t
            self.status_message.emit(
                t("status_reusing_pages", self.settings.ui_language, count=len(reused)))

        self._worker = AnalysisWorker(
            pages=reused,
            root_url=url,
            depth=self.state.depth,
            detector_name=detector_name,
            detector_config=detector_config,
            max_pages=self.settings.max_pages,
            unicode_categories=self._active_unicode_categories(),
            settings=self.settings,
            # The checkout behind this site, when one was named. Findings
            # then carry the file and the line that wrote the passage; see
            # `repo_pairing`.
            paired_repo=self.state.paired_repo,
            paired_ignore=self.effective_ignore_patterns,
            no_session=self.state.no_session,
            crawl=snapshot.crawl if snapshot is not None else None,
            session_host=snapshot.session_host if snapshot is not None else "",
            session_values=snapshot.session_values if snapshot is not None else 0,
            cancellation=self._run_context.cancellation if self._run_context else None,
        )
        self._wire_worker(self._worker,
                          on_finished=self._on_web_finished)
        self._worker.start()
        self.busy_changed.emit(True)

    def _start_file_copy_analysis(self):
        self._start_repo_analysis(self.state.scan_target)

    def _start_repo_analysis(self, path: str | None = None):
        path = path if path is not None else self.state.scan_target
        if not path:
            from i18n.translations import t
            self.error.emit(t("no_repo_path", self.settings.ui_language))
            return

        detector_name, detector_config = self._detector_for_request()
        incremental = self.state.incremental
        self._worker = RepoAnalysisWorker(
            files=self._reusable_files() if incremental else None,
            root_dir=path,
            ignore_patterns=self.effective_ignore_patterns,
            detector_name=detector_name,
            detector_config=detector_config,
            unicode_categories=self._active_unicode_categories(),
            scope=self._repo_scope(),
            settings=self.settings,
            extensions=self.state.extensions or None,
            incremental=incremental,
            cancellation=self._run_context.cancellation if self._run_context else None,
        )
        self._wire_worker(self._worker,
                          on_finished=self._on_repo_finished)
        self._worker.start()
        self.busy_changed.emit(True)

    @property
    def effective_ignore_patterns(self) -> list:
        """What a folder run actually skips: the person's list plus the
        detected stack's, unless they have lifted the latter."""
        return self.state.ignore_patterns_with_project(self.repo_ignore_patterns)

    def _start_audit(self):
        """Audit whatever the source is: a site, one page file, or a folder.

        A folder used to end up here with `https://` glued onto its path -
        see `ui.worker.audit_worker_for`, which now decides this once for
        both callers.
        """
        from i18n.translations import t
        from ui.worker import audit_worker_for

        lang = self.settings.ui_language
        worker, refusal = audit_worker_for(
            self.state.source,
            target=self.state.scan_target,
            depth=self.state.depth,
            max_pages=self.settings.max_pages,
            pages=(self._reusable_pages()
                   if self.state.source == SOURCE_SITE else None),
            ignore_patterns=self.effective_ignore_patterns,
            max_files=self.settings.max_files,
            extensions=self.state.extensions or None,
            files=(self._reusable_files()
                   if self.state.source == SOURCE_REPO
                   and self.state.incremental else None),
            incremental=self.state.incremental,
            settings=self.settings,
            site_controls=self.state.site_controls,
            medium=self.state.medium,
            within=self.state.within,
            web_parts=self._web_parts_for_run(),
            no_session=self.state.no_session,
            sharepoint=self._sharepoint_run(),
            crawl=(self._snapshot.crawl if self._snapshot is not None else None),
            session_host=(self._snapshot.session_host
                          if self._snapshot is not None else ""),
            session_values=(self._snapshot.session_values
                            if self._snapshot is not None else 0),
            cancellation=self._run_context.cancellation if self._run_context else None,
        )
        if worker is None:
            self.error.emit(self._missing_target_message() if refusal == "no_target"
                            else t("url_label_full", lang))
            return

        self.audit_result = None
        self._worker = worker
        self._wire_worker(self._worker,
                          on_finished=self._on_audit_finished)
        self._worker.start()
        self.busy_changed.emit(True)

    def _sharepoint_run(self):
        """`auditpass.SharePointRun` for this target, or `None` off a site.

        Read through `plan_sharepoint`, the function `fullscan` reads it
        through, with nothing typed by hand: the window has no controls for
        `--page-tree` or `--site-scope`, so what the target asks for is the
        whole answer. One function for both surfaces is the point - the
        same SharePoint address must be read as the same set of pages.
        """
        if self.state.source != SOURCE_SITE:
            return None
        target = (self.state.scan_target or "").strip()
        if not target:
            return None
        from types import SimpleNamespace

        from cli_impl import auditpass

        args = SimpleNamespace(repo=self.state.paired_repo or "",
                               page_tree=None, site_scope=None, render=None,
                               no_browser=False)
        run = auditpass.plan_sharepoint(target, args)
        return run if run.sharepoint else None

    def _web_parts_for_run(self) -> tuple:
        """The SPFx parts to confine this audit to, or `()`.

        Read here rather than in the worker so a solution that ships nothing
        is an empty tuple - which audits the whole page, exactly as before -
        instead of a thread that starts and finds it has nothing to do. The
        CLI answers the same question in `cli._web_parts_for`, and refuses
        the same way: without a checkout there is nothing to read parts from.
        """
        if not self.state.web_parts or not self.state.paired_repo:
            return ()
        from audit import spfx

        try:
            return tuple(spfx.web_parts(self.state.paired_repo))
        except OSError:
            return ()

    def cancel(self):
        if self._run_context is not None:
            self._run_context.cancellation.cancel()
        if self._worker is not None:
            if hasattr(self._worker, "cancel"):
                self._worker.cancel()
            self._worker.requestInterruption()

    # -- worker management -------------------------------------------------
    def _wire_worker(self, worker, *, on_finished):
        if hasattr(worker, 'crawling'):
            worker.crawling.connect(self.crawling)
        if hasattr(worker, 'scanning'):
            worker.scanning.connect(self.scanning)
        if hasattr(worker, 'detecting'):
            worker.detecting.connect(self.detecting)
        if hasattr(worker, 'auditing'):
            worker.auditing.connect(self.auditing)
        worker.finished_ok.connect(on_finished)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(
            lambda finished_worker=worker:
                self._on_worker_finished(finished_worker))
        self._active_workers.append(worker)

    def _on_worker_finished(self, finished_worker=None):
        """Release only the worker that actually ended.

        A two-pass run starts the copy worker from the audit worker's result
        callback. Qt emits the old worker's `finished` afterwards; clearing
        `self._worker` there discarded the new worker, made Cancel miss it and
        told the window the run was idle halfway through.
        """
        if finished_worker in self._active_workers:
            self._active_workers.remove(finished_worker)
        if finished_worker is not None and self._worker is not finished_worker:
            return
        self._worker = None
        self.busy_changed.emit(False)
        self.buttons_changed.emit()

    def _on_failed(self, message: str):
        self.error.emit(message)

    def _on_web_finished(self, result: AnalysisResult):
        self._report_session()
        self._report_pairing()
        if isinstance(self.result, RepoAnalysisResult) and self.state.source == SOURCE_FILE:
            # Merge browser findings into the code analysis result
            self.result.spans.extend(result.spans)
            self.repo_result_ready.emit(self.result)
        else:
            self.result = result
            self._remember_extraction(self._last_request,
                                      pages=result.pages, crawl=result.crawl,
                                      session_host=getattr(self._worker, "session_host", ""),
                                      session_values=getattr(self._worker, "session_values", 0))
            self.web_result_ready.emit(result)

    def _report_session(self, worker=None) -> None:
        """Say when a run read the site as a signed-in person.

        The host and nothing else. A run that was authenticated is a
        different run - what it found is what *that account* sees - and a
        report of it that does not say so is a report about the wrong
        visitor.
        """
        from i18n.translations import t

        worker = worker if worker is not None else self._worker
        host = getattr(worker, "session_host", "")
        if host:
            self.status_message.emit(
                t("sign_in_site_active", self.settings.ui_language, host=host))

    def _report_pairing(self) -> None:
        """Say how much of the site the paired checkout actually explained.

        The number is the honest half of pairing. Three matches out of forty
        means the wrong folder - or copy that arrives from a CMS - and a
        window that showed only the three files it did find would let a
        person believe the other thirty-seven passages are not in the code.
        """
        from i18n.translations import t

        worker = self._worker
        if not getattr(worker, "paired_repo", ""):
            return
        total = getattr(worker, "paired_total", 0)
        matched = getattr(worker, "paired_matched", 0)
        if not total:
            return
        key = "paired_repo_matched" if matched else "paired_repo_none"
        self.status_message.emit(t(key, self.settings.ui_language,
                                   matched=matched, total=total))

    def _on_repo_finished(self, result: RepoAnalysisResult):
        self.result = result
        self._remember_extraction(self._last_request,
                                  files=result.files,
                                  scope=self._repo_scope(),
                                  scan=result.diagnostics)
        if self._file_both_passes:
            # Code analysis done, now run browser analysis on the rendered DOM
            self._file_both_passes = False
            self._start_web_analysis(root=_browser_url(self.state.target))
        else:
            self.repo_result_ready.emit(result)

    def _on_audit_finished(self, result):
        self._report_session()
        worker = self._worker
        if self.state.source == SOURCE_SITE:
            pages = getattr(worker, "acquired_pages", None)
            if pages is not None:
                self._remember_extraction(
                    self._last_request, pages=pages,
                    crawl=getattr(worker, "crawl", None),
                    session_host=getattr(worker, "session_host", ""),
                    session_values=getattr(worker, "session_values", 0))
        elif self.state.source == SOURCE_REPO:
            files = getattr(worker, "acquired_files", None)
            if files is not None:
                self._remember_extraction(
                    self._last_request, files=files, scope=self._repo_scope(),
                    scan=getattr(worker, "scan_diagnostics", None))
        self.audit_result = result
        # A SharePoint page is assembled in the browser (`render=always` in
        # `run_profile.RECIPES`): without the browser pass the run reports on
        # an empty canvas, so a SharePoint result always gets one.
        if self._last_request and (self._last_request.wants_browser
                                   or getattr(result, "sharepoint", None)):
            self.browser_pass_needed.emit()
        if self.cancellation_requested:
            self._pending_copy_pass = False
            return
        # The browser signal is a direct main-thread continuation. Emit the
        # public result only after it has merged the browser answer, so the
        # window never paints a knowingly incomplete intermediate report.
        if self._last_request and self._last_request.wants_accessibility:
            self.audit_result_ready.emit(result)
        if self._pending_copy_pass:
            self._pending_copy_pass = False
            self._start_copy_pass()

    def remember_browser_html(self, rendered_by_source: dict[str, str]) -> None:
        """Make the one Chromium load the run's authoritative DOM snapshot.

        Copy analysis and the static rule registry receive the DOM produced
        from that same run, with the original crawl depths and HTTP evidence
        retained. Neither consumer touches the network again.
        """
        if not rendered_by_source or self._last_request is None:
            return
        from dataclasses import replace

        from crawler import page_from_html

        old_pages = list(self._snapshot.pages) if self._snapshot else []
        old_by_source = {page.url: page for page in old_pages}
        replacements = {}
        for source, html in rendered_by_source.items():
            if not html:
                continue
            address = _browser_url(source)
            old = old_by_source.get(source, old_by_source.get(address))
            page = page_from_html(html, address, old.depth if old else 0)
            if old is not None:
                # Rendering changes the DOM evidence, not what the HTTP
                # response said. Headers, status and redirect provenance are
                # still needed by security, crawlability and auth-wall rules.
                previous = old.diagnostics
                page.diagnostics = replace(
                    page.diagnostics,
                    status_code=previous.status_code,
                    content_type=previous.content_type,
                    final_url=previous.final_url or address,
                    render_error=previous.render_error,
                    headers=dict(previous.headers or {}),
                )
            replacements[source] = page
            replacements[address] = page

        # A browser failure on one page must not make that page disappear
        # from the snapshot. Replace only pages for which Chromium returned a
        # DOM, keeping crawl order and every untouched error/result.
        pages = []
        used = set()
        for old in old_pages:
            page = replacements.get(old.url, old)
            pages.append(page)
            used.add(id(page))
        for page in replacements.values():
            if id(page) not in used:
                pages.append(page)
                used.add(id(page))
        if pages:
            self._remember_extraction(self._last_request, pages=pages)
            self._refresh_site_audit_from_snapshot()

    def _refresh_site_audit_from_snapshot(self) -> None:
        """Re-run network-free audit stages against the rendered DOM.

        The acquisition worker first audits the server response so it can
        hand the browser a bounded target list. Once Chromium has returned
        the actual DOM, that DOM supersedes the response shell for our own
        rules. HTTP diagnostics, media bytes and explicitly requested
        robots/sitemap evidence are carried forward rather than fetched a
        second time.
        """
        if (self.state.source != SOURCE_SITE or self.audit_result is None
                or self._snapshot is None or not self._snapshot.pages):
            return

        import audit
        from audit import browser as browser_mod
        from audit.engine import DocumentReport, attribute_ownership

        result = self.audit_result
        browser_issues = [
            issue for document in result.documents for issue in document.issues
            if issue.engine in {"axe", "htmlcs", "browser"}
        ]
        external_issues = [
            issue for document in result.documents for issue in document.issues
            if issue.engine in {"robots.txt", "sitemap"}
        ]

        refreshed = audit.analyze_pages(
            list(self._snapshot.pages), result.root,
            media=False, site_controls=False,
            within=self.state.within,
            web_parts=self._web_parts_for_run(),
            # Zoned again on the rendered DOM: the browser is what drew the
            # web parts the zones are made of.
            sharepoint=bool(getattr(result, "sharepoint", None)),
        )

        # Media already consumed its bounded network budget in the worker.
        # Rebuild only its report objects from the retained scan result.
        refreshed.media = result.media
        if result.media is not None:
            from audit import media as media_pass

            refreshed.documents.extend(media_pass.as_web_documents(result.media))

        if external_issues:
            by_source = {}
            for issue in external_issues:
                by_source.setdefault(issue.source, []).append(issue)
            refreshed.documents.extend(
                DocumentReport(source=source, issues=issues,
                               elements_checked=1)
                for source, issues in by_source.items()
            )

        suppressions = suppression.Suppressions.load(self.settings, None)
        for document in refreshed.documents:
            document.issues = suppression.filter_issues(
                document.issues, suppressions)

        # Browser engines have already inspected this exact DOM. Put their
        # evidence back onto the newly built primary page report and collapse
        # agreements using the rendered markup as element identity evidence.
        markup = refreshed.markup_by_source
        for issue in browser_issues:
            document = next(
                (item for item in refreshed.documents
                 if item.source == issue.source and not item.error), None)
            if document is None:
                document = DocumentReport(source=issue.source)
                refreshed.documents.append(document)
            document.issues = browser_mod.deduplicate(
                [*document.issues, issue], markup.get(issue.source, ""))

        refreshed.browser_errors = list(result.browser_errors)
        attribute_ownership(refreshed)
        for name in (
                "root", "mode", "documents", "rules_run", "media", "repo",
                "auth", "markup_sample", "markup_by_source", "browser_errors",
                "sharepoint"):
            setattr(result, name, getattr(refreshed, name))

    # -- rewrite actions ---------------------------------------------------
    def rewrite_all(self):
        if not self.result or not self.result.spans:
            return
        self._rewrite_worker = RewriteAllWorker(
            self.result.spans, self.settings)
        self._rewrite_worker.finished_ok.connect(self._on_rewrite_finished)
        self._rewrite_worker.failed.connect(self._on_failed)
        self._rewrite_worker.finished.connect(
            lambda: setattr(self, '_rewrite_worker', None))
        self._active_workers.append(self._rewrite_worker)
        self._rewrite_worker.start()
        self.busy_changed.emit(True)

    def _on_rewrite_finished(self, drafts: dict):
        self.drafts = drafts
        self.rewrite_ready.emit(drafts)

    def rewrite_single(self, span: TextSpan, block):
        worker = SingleRewriteWorker(span, block, self.settings)
        worker.finished_ok.connect(
            lambda key, draft: self._on_single_rewrite(key, draft))
        worker.failed.connect(self._on_failed)
        worker.finished.connect(
            lambda: self._active_workers.remove(worker)
            if worker in self._active_workers else None)
        self._active_workers.append(worker)
        worker.start()

    def _on_single_rewrite(self, key, draft):
        self.drafts[key] = draft
        self.single_rewrite_ready.emit(key, draft)

    # -- fix actions -------------------------------------------------------
    def fix_unicode(self, spans):
        if not spans or not self.result:
            return
        blocks_by_id = {b.block_id: b for b in self.result.blocks()}
        filled = 0
        for span in spans:
            block = blocks_by_id.get(span.block_id)
            if block is None or span.replacement is None:
                continue
            original = block.text[span.start:span.end]
            if span.replacement != original:
                self.drafts[(block.block_id, span.start, span.end)] = span.replacement
                filled += 1
        self.unicode_fixed.emit(filled)
        self.buttons_changed.emit()

    # `fix_on_disk` and `apply_fix_with_ai` lived here and wrote the audit's
    # corrections straight to disk after a message box with two counts in it.
    # They are gone: the same corrections are rows in the replacement list
    # now, read before they are written, and a second path to the same write
    # is a second answer to "what changed in my repository". What the model
    # can answer is `replacements.fill_decisions`.

    def undo_fix(self):
        from audit import fixer
        from i18n.translations import t
        lang = self.settings.ui_language
        docs = self.audit_result.documents if self.audit_result else []
        paths = fixer.backups_for(docs)
        if not paths:
            return
        restored, problems = fixer.restore(paths)
        message = t("undo_done", lang, files=len(restored))
        if problems:
            message += "\n\n" + "\n".join(problems)
        self.undo_outcome.emit(message)
        self.buttons_changed.emit()

    # -- download actions --------------------------------------------------
    def download(self):
        has_audit = bool(self.audit_result and self.audit_result.documents)
        has_text = bool(self.result and self.result.spans)
        if not has_audit and not has_text:
            return
        self.download_choice_needed.emit(has_audit, has_text)

    def _report_model(self):
        """The findings of this run as one report model, or None.

        An audit and a copy scan can both be asked for in the same run, and
        the report is of the run, not of one of its halves - so the two sets
        of findings go into one model rather than producing two documents
        that each omit half of what was found.
        """
        from report.model import from_accessibility, from_text_analysis
        lang = self.settings.ui_language
        has_text = bool(self.result and self.result.spans)
        has_audit = bool(self.audit_result and self.audit_result.documents)
        # Exported through the same view the window is showing. A report
        # that carries findings the list on screen is hiding would make the
        # two disagree about one run, and the reader has no way to tell which
        # of them is the audit.
        audited = (self.audit_result.narrowed(self.state.categories,
                                              self.state.confidence_floor,
                                              unsettled=self.state.unsettled)
                   if has_audit else None)
        model = from_accessibility(audited, lang=lang) if has_audit else None
        if has_text:
            # No `lang`: the copy adapter does not take one - it was being
            # passed one anyway, which raised `TypeError` the moment a run
            # with copy findings reached this line.
            text_model = from_text_analysis(self.result)
            if model:
                model.findings.extend(text_model.findings)
            else:
                model = text_model
        return model

    def export_styled_report(self, path: str):
        from report.export import write_styled_report
        model = self._report_model()
        if model is None:
            return
        # `path` first, then the model: they were the other way round here,
        # which meant `Path(model)` and a TypeError every time the button was
        # pressed. The language was missing too, so an Italian window would
        # have printed an English report if it had printed one at all.
        write_styled_report(path, model, self.settings.ui_language)
        from i18n.translations import t

        self.status_message.emit(t("status_report_saved",
                                   self.settings.ui_language, path=path))

    def export_agent_report(self, path: str):
        import cli
        if self.audit_result is None:
            return
        class _Args:
            report = path
        cli._write_report(self.audit_result, _Args(), self.settings.ui_language, None)
        from i18n.translations import t

        self.status_message.emit(t("status_report_saved",
                                   self.settings.ui_language, path=path))

    def save_run_documents(self, stage_timings=None, run_began=None):
        """Write this run's folder, and say what ended up in it.

        The window used to have one report button and a save dialog behind
        it, which asks the wrong question: a run does not produce *a file*,
        it produces a set of documents that only make sense together, and
        where they go is already decided - one folder per target, one
        sub-folder per run (`cli_impl.runfolder`). Asking where to put each
        one is how the four documents of a run end up in four places.

        The same folder layout the CLI writes, through the same functions:
        `report.md` and its history come from `cli_impl.reports`, so a run
        started from the window and a run started from `xanalyze fullscan`
        share one history and each can be the previous run of the other.

        Returns a `RunDocuments`. `changes.md` is absent on a first run,
        deliberately: an empty comparison reads as a broken comparison.
        """
        from cli_impl import runfolder
        from cli_impl.runfolder import RunDocuments
        from report.export import write_styled_report

        model = self._report_model()
        if model is None:
            return None
        lang = self.settings.ui_language
        target = self.state.scan_target or (
            getattr(self.result, "root_url", None) or "scan")
        folder = runfolder.prepare(target)
        written, absent = {}, {}

        payload = None
        if self.audit_result is not None:
            import cli

            class _Args:
                report = str(folder.report)

            payload = cli._write_report(self.audit_result, _Args(), lang, None)
            written["report.md"] = folder.report
        else:
            # A copy scan has no rule-by-rule briefing to write. Named as
            # absent with its reason rather than left off the list: a
            # document that is missing for a knowable reason is information,
            # a document that is silently not mentioned is not.
            absent["report.md"] = "no_audit"

        write_styled_report(str(folder.styled_report), model, lang,
                            markdown_path=str(folder.report) if payload else None)
        written["report.pdf"] = folder.styled_report

        timings = runfolder.Timings(started=run_began)
        for label, seconds in (stage_timings or []):
            timings.note(label, seconds)
        timings.write(folder.timings, target, extra={
            "findings": len(model.findings),
            "run folder": str(folder.run),
        })
        written["timings.md"] = folder.timings

        comparison = None
        if payload is not None:
            from cli_impl.reports import comparison_view, write_comparison_document
            if write_comparison_document(folder.changes, payload):
                written["changes.md"] = folder.changes
                # Built from the same payload that produced the document, so
                # the panel and the file are two renderings of one comparison
                # rather than two comparisons that can drift apart.
                comparison = comparison_view(payload)
            else:
                absent["changes.md"] = (
                    "first_run" if not folder.previous_runs() else "not_comparable")
        else:
            absent["changes.md"] = "no_audit"

        documents = RunDocuments(folder=folder, target=target,
                                 written=written, absent=absent,
                                 comparison=comparison)
        from i18n.translations import t

        self.status_message.emit(t("status_run_documents",
                                   self.settings.ui_language, path=folder.run))
        return documents

    # -- suppression -------------------------------------------------------
    def ignore_span(self, span: TextSpan, block):
        root = self._ignore_scan_root()
        fingerprint = suppression.span_fingerprint(span, block)
        label = suppression.span_label(span, block)
        if root:
            suppression.add_fingerprint_to_ignore_file(root, fingerprint, label)
        else:
            fingerprints = list((self.settings.ignore or {}).get("fingerprints") or [])
            if fingerprint not in fingerprints:
                fingerprints.append(fingerprint)
                ignore = dict(self.settings.ignore or {})
                ignore["fingerprints"] = fingerprints
                labels = dict(ignore.get("labels") or {})
                labels[fingerprint] = label
                ignore["labels"] = labels
                self.settings.ignore = ignore
                self.settings.save()
        if self.result is not None:
            self.result.spans = [s for s in self.result.spans if s is not span]
        self.buttons_changed.emit()

    def _ignore_scan_root(self) -> str | None:
        if self.state.source == SOURCE_REPO:
            return self.state.scan_target or None
        if self.state.source == SOURCE_FILE:
            path = self.state.target
            return str(Path(path).parent) if path else None
        return None

    # -- shutdown ----------------------------------------------------------
    def shutdown(self):
        if self._run_context is not None:
            self._run_context.cancellation.cancel()
        for w in self._active_workers:
            if w.isRunning():
                if hasattr(w, "cancel"):
                    w.cancel()
                w.requestInterruption()
                w.wait(2000)
