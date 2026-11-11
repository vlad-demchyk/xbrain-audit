"""The browser pass: loading audited pages in a real browser, at one or
several viewport widths, and folding what it finds back into the static
result. Also the small pieces of crawl plumbing the audit command shares
with fullscan - when to render, how to turn a source into a URL.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import applog
import progress


#: `--breakpoints` with no value means all of them.
def _chosen_breakpoints(args):
    """The widths to audit at, or () for the engine's default single pass."""
    from audit import responsive

    raw = getattr(args, "breakpoints", None)
    if not raw:
        return ()
    if raw == "all":
        return responsive.BREAKPOINTS
    wanted = [name.strip() for name in raw.split(",") if name.strip()]
    known = {name: (name, w, h) for name, w, h in responsive.BREAKPOINTS}
    unknown = [name for name in wanted if name not in known]
    if unknown:
        raise SystemExit(
            f"unknown breakpoint: {', '.join(unknown)}. "
            f"Valid: {', '.join(known)}")
    # Kept in the canonical order, widest first, whatever order they were
    # typed in: the first pass to see a finding is the one whose selector the
    # merged row keeps, and that should not depend on typing order.
    return tuple(known[name] for name, _w, _h in responsive.BREAKPOINTS
                 if name in wanted)


def _audit_at_widths(urls, options, sizes, on_page=None, markup=None,
                     profile=None, cancelled=None) -> list:
    """One browser, every page, every width - skipping what has not changed.

    `markup` maps a url to the bytes the crawler already received for it.
    Given that, a page whose markup is identical to one a previous run
    audited is read from `browser_cache` instead of being loaded again: this
    is the expensive half of an audit (12 s per page at four widths against
    0.05 s for every static rule) and a re-run of an unchanged page was
    paying it in full.

    Without `markup` nothing is cached, because there would be nothing
    honest to key on: a URL is where a page lives, not what it says.
    """
    from audit import driver
    from audit import responsive
    from dataclasses import replace

    import browser_cache

    markup = markup or {}
    cache = browser_cache.BrowserCache(options, sizes) if (
        markup and getattr(options, "performance_repeats", 1) == 1
        and not getattr(options, "performance_scenario", [])
        and not getattr(options, "performance_fresh", False)) else None

    results = []
    todo = []
    #: Addresses already answered from the cache, so a repeat is filled from
    #: here rather than looked up (and counted) a second time.
    seen_hits = {}
    #: Which index already asked for this url. The audit returns more than
    #: one document per page - the page's own rules, the response headers,
    #: an image's provenance - and this pass is driven by documents, so a
    #: 250-page crawl arrived here as 474 loads. Measured on a live
    #: WordPress site: every one of the 250 addresses appeared at least
    #: twice, which is half the browser pass, and the browser pass is the
    #: expensive half of an audit (12 s per page at four widths).
    #:
    #: The cache below cannot save it: every lookup happens before the first
    #: render, so the second copy of a url is already in `todo` by the time
    #: the first one is answered. So the duplicate is resolved here, and the
    #: answer is *shared*, not recomputed.
    first_index = {}
    for index, url in enumerate(urls):
        if url in first_index or url in seen_hits:
            # A repeat asks the cache nothing: the lookup is keyed on the
            # markup, so the answer would be the same one, and counting it
            # again made the cache report "9/9 pages" for a four-page site.
            results.append(None)
            continue
        stored = cache.get(markup[url], url) if (cache and url in markup) else None
        results.append(stored)
        if stored is not None:
            seen_hits[url] = stored
            continue
        first_index[url] = index
        todo.append(url)

    if todo:
        driver.ensure_headless_application()
        first = (replace(options, viewport=(sizes[0][1], sizes[0][2]))
                 if sizes else options)
        if profile is None and cancelled is None:
            runner = driver.BrowserAuditRunner(first)
        else:
            runner = driver.BrowserAuditRunner(first, profile=profile,
                                               cancelled=cancelled)
        try:
            done = 0
            for index, url in enumerate(urls):
                if results[index] is not None or first_index.get(url) != index:
                    continue
                done += 1
                if on_page:
                    on_page(done, url)
                # No widths asked for is one pass at the engine's own
                # viewport, which is what `audit` does without
                # `--breakpoints`. Both shapes go through here so both are
                # cached; they are different questions and the key says so.
                audited = (responsive.audit_responsive(url, sizes, options,
                                                       runner=runner)
                           if sizes else runner.audit(url))
                results[index] = audited
                if cache is not None and url in markup:
                    cache.put(markup[url], audited)
        finally:
            runner.close()

    # Every other document naming the same address gets the answer that was
    # already paid for. After the loop rather than inside it, so a url that
    # only repeats later is covered too.
    for index, url in enumerate(urls):
        if results[index] is not None:
            continue
        if url in seen_hits:
            results[index] = seen_hits[url]
        elif first_index.get(url) is not None:
            results[index] = results[first_index[url]]

    if cache is not None:
        cache.save()
        note = cache.summary()
        if note:
            progress.notice("browser", note, human=f"# [browser] {note}")
    return results


def _run_browser_pass(result, suppressions, args=None) -> None:
    """Load each audited page in a real browser and fold the findings in.

    Runs for a crawled site and for a single self-contained HTML file. Not for
    repo mode: a browser has nothing to load for a `.jsx` fragment that was
    never a page, and half-auditing a template would report problems the built
    page does not have.

    The suppression list is handed to the engines rather than applied to
    their output, so an excluded region is never analysed in the first place
    — for axe that is the difference between "ignore these results" and "do
    not spend seconds computing them".
    """
    if result.mode not in ("web", "file"):
        return
    from audit import browser as browser_mod
    from audit import driver

    usable, reason = driver.available()
    if not usable:
        result.browser_coverage.append({"engine": "browser", "status": "error",
                                        "reason": str(reason)})
        applog.warning("browser.skipped", reason=str(reason))
        progress.notice("browser", f"browser pass skipped: {reason}",
                        human=f"# browser pass skipped: {reason}",
                        skipped=True, reason=str(reason))
        return

    unread = unread_sources(result.documents)
    targets = [d for d in result.documents
               if not d.error and d.source not in unread
               and _is_renderable(d.source)]
    if not targets:
        result.browser_coverage.append({"engine": "browser", "status": "skipped",
                                        "reason": "no renderable documents"})
        return

    within = getattr(args, "within", None) or "" if args is not None else ""
    from audit.vitals import validate_scenario
    scenario_path = getattr(args, "performance_scenario", None)
    scenario = []
    if scenario_path:
        import json
        from pathlib import Path
        scenario = validate_scenario(json.loads(Path(scenario_path).read_text(encoding="utf-8")))
    options = browser_mod.BrowserAuditOptions(
        exclude=list(suppressions.selectors),
        disabled_rules=list(suppressions.rules),
        allow_local_files=result.mode == "file",
        within=within,
        # axe takes an `include` context and confines itself to it. The
        # other three read the whole document by construction:
        # HTML_CodeSniffer walks from `document`, the state pass tabs
        # through the page, and a measurement is a property of the page
        # load. Running them here would answer a question the caller did
        # not ask - and answering it quietly, under a report they narrowed
        # on purpose - so they are switched off and the reason is printed.
        run_htmlcs=not within,
        run_states=not within,
        run_measurements=not within,
        settle_ms=getattr(args, "performance_settle_ms", 2500),
        color_scheme=getattr(args, "color_scheme", None) or "light",
        performance_repeats=getattr(args, "performance_repeats", 1),
        performance_scenario=scenario,
        performance_fresh=getattr(args, "performance_fresh", False),
    )
    # A SharePoint run reads the zones, not the chrome: axe is confined to
    # them, the whole-document engines are off, and the DOM is kept so each
    # finding can be placed. See `audit.sharepoint_zones`.
    sharepoint = bool(getattr(result, "sharepoint", None))
    zone_summary = None
    if sharepoint:
        from audit import sharepoint_zones

        options = sharepoint_zones.browser_options(options)
        zone_summary = sharepoint_zones.Summary()
    if within:
        progress.notice(
            "within",
            f"browser pass: axe only, confined to {within}. "
            f"HTML_CodeSniffer, the state pass and the measurements read the "
            f"whole document and are skipped.",
            human=f"# [within] browser pass: axe only, confined to {within}. "
                  f"HTML_CodeSniffer, the state pass and the measurements "
                  f"read the whole document and are skipped.",
            selector=within)
    sizes = _chosen_breakpoints(args) if args is not None else ()
    where = (f" at {len(sizes)} widths" if sizes else "")
    # The document is still keyed by its own source (a path, in file mode), so
    # the findings land back on the row the user recognises rather than on a
    # `file://` URL they never typed.
    urls = [_browser_url(d.source) for d in targets]
    # Addresses, not documents. Several documents describe one page - the
    # page's rules, its response headers - and counting documents told the
    # reader a four-page site was nine loads and then stopped at "4/9",
    # which reads as a crawl that gave up.
    total = len(dict.fromkeys(urls))
    progress.stage("browser", "begin",
                   f"# browser pass over {total} page(s){where}",
                   pages=total, widths=len(sizes) or None)

    def _show(page_no: int, url: str) -> None:
        widths = f" at {len(sizes)} width(s)" if sizes else ""
        progress.page(page_no, total, url,
                      human=f"# [browser {page_no}/{total}{widths}] {url}")

    # The markup the crawl already received, keyed by the browser url the
    # pass will use. It is what makes the cache honest: the same bytes get
    # the same answer, a changed page gets a fresh browser.
    served = getattr(result, "markup_by_source", None) or {}
    markup = {url: served[document.source]
              for document, url in zip(targets, urls)
              if document.source in served}
    profile = None
    if not (args is not None and getattr(args, "no_session", False)):
        profile = driver.session_profile(result.root)
    audit_kwargs = {"on_page": _show, "markup": markup}
    if profile is not None:
        audit_kwargs["profile"] = profile
    audits = _audit_at_widths(urls, options, sizes, **audit_kwargs)
    from audit.performance_sources import optional_sources
    result.coverage.setdefault("performance_sources", []).extend(
        optional_sources(urls, args, scoped=bool(within)))
    by_url = {a.url: a for a in audits}
    #: Addresses already handled. One page is several documents, and
    #: merging the same audit into each of them counted every browser
    #: finding two or three times: measured on a live site, `perf-page-weight`
    #: for the home page appeared three times in one report, and the run's
    #: total was inflated by the same factor. The first document for an
    #: address is the page's own, which is where a reader expects the
    #: browser's answer to land.
    processed_urls = set()
    for document, url in zip(targets, urls):
        page_audit = by_url.get(url)
        if url in processed_urls:
            continue
        processed_urls.add(url)
        if page_audit is None:
            result.browser_coverage.append({"source": document.source, "engine": "browser",
                                            "status": "unknown", "reason": "no page result"})
            continue
        for engine, enabled in (("axe", options.run_axe), ("htmlcs", options.run_htmlcs),
                                ("states", options.run_states), ("browser", options.run_measurements)):
            error = page_audit.error or page_audit.engine_errors.get(
                "measurements" if engine == "browser" else engine)
            result.browser_coverage.append({"source": document.source, "engine": engine,
                "status": "skipped" if not enabled else "error" if error else "checked",
                "reason": "excluded by scope/options" if not enabled else str(error or "")})
        if zone_summary is not None and not page_audit.error:
            page_audit.issues = sharepoint_zones.classify_browser_issues(
                page_audit.issues, page_audit.html,
                getattr(args, "_web_parts_found", ()) if args is not None else (),
                getattr(args, "_ootb_registry", None) if args is not None else None,
                summary=zone_summary)
        browser_mod.merge_page_audit(result, document, page_audit)
        if page_audit.error:
            progress.notice(
                "browser", f"{document.source}: {page_audit.error}",
                human=f"# {document.source}: {page_audit.error}",
                source=str(document.source), error=str(page_audit.error))
            continue
        for name, message in page_audit.engine_errors.items():
            applog.error("browser.engine_error", engine=name,
                         source=document.source, message=str(message)[:300])
            progress.notice(
                "browser", f"{document.source}: {name} {message}",
                human=f"# {document.source}: {name} {message}",
                source=str(document.source), engine=name,
                error=str(message))
    if zone_summary is not None:
        _add_skipped(result, zone_summary)
    # Again, because the findings the browser brought arrived after the crawl
    # attributed the ones it had. A second engine's finding is owned by
    # whoever emitted the element, exactly as the first engine's is.
    if getattr(result, "mode", "") == "web":
        from audit.engine import attribute_ownership

        attribute_ownership(result)


def _add_skipped(result, zone_summary) -> None:
    """Fold the browser's skipped findings into the run's SharePoint summary.

    The static pass counted what it left out of Microsoft's markup; the
    browser pass leaves out more, and a summary that showed only the first
    half would understate how much of the page was not reported.
    """
    summary = result.sharepoint if isinstance(result.sharepoint, dict) else {}
    skipped = summary.setdefault("skipped", {})
    skipped["findings"] = (skipped.get("findings", 0)
                           + zone_summary.skipped_findings)
    by_rule = dict(skipped.get("by_rule") or {})
    for rule, count in zone_summary.skipped_by_rule.items():
        by_rule[rule] = by_rule.get(rule, 0) + count
    skipped["by_rule"] = dict(sorted(by_rule.items(),
                                     key=lambda kv: (-kv[1], kv[0])))
    result.sharepoint = summary


#: Extensions that make a file a page rather than a piece of a project.
PAGE_FILE_SUFFIXES = (".html", ".htm", ".xhtml")


def _is_page_file(target: str) -> bool:
    """Is this one HTML file rather than a folder or a URL?"""
    from pathlib import Path
    path = Path(target)
    return path.is_file() and path.suffix.lower() in PAGE_FILE_SUFFIXES


#: Last labels that read as a file suffix rather than a TLD. Everything the
#: scanner can open, plus the archive and document suffixes a person is most
#: likely to point at by mistake. Only consulted for a target with no slash
#: and no port - see `looks_like_url`.
_FILE_SUFFIXES = frozenset((
    ".html", ".htm", ".xhtml", ".xml", ".jsx", ".tsx", ".vue", ".svelte",
    ".js", ".ts", ".mjs", ".cjs", ".py", ".php", ".rb", ".erb", ".go",
    ".java", ".cs", ".json", ".yml", ".yaml", ".md", ".txt", ".css",
    ".scss", ".less", ".zip", ".tar", ".gz", ".pdf", ".png", ".jpg",
    ".jpeg", ".svg", ".webp", ".lock", ".log", ".toml", ".ini", ".cfg",
    ".sh", ".bak",
))

#: A bare host, with an optional port and path: `example.com`,
#: `www.example.co.uk/pricing`, `localhost:8000`, `127.0.0.1:8000/admin`.
#: Anchored, so a shell path never matches by accident. Built on first use.
_BARE_HOST = None


def _bare_host_pattern():
    """Compiled lazily and cached: `cmd_scan` never needs it."""
    global _BARE_HOST
    if _BARE_HOST is None:
        import re
        label = r"[A-Za-z0-9¡-￿](?:[A-Za-z0-9¡-￿-]*[A-Za-z0-9¡-￿])?"
        _BARE_HOST = re.compile(
            r"^(?:"
            # dotted host whose last label is a TLD-shaped word: example.com
            rf"{label}(?:\.{label})*\.[A-Za-z¡-￿]{{2,}}"
            # or a name that only makes sense with a port: localhost:8000
            rf"|{label}(?=:\d)"
            # or a dotted-quad address
            r"|\d{1,3}(?:\.\d{1,3}){3}"
            r")"
            r"(?::\d{1,5})?"      # optional port
            r"(?:[/?#].*)?$",     # optional path, query, fragment
            re.IGNORECASE)
    return _BARE_HOST


def unquote_target(target: str) -> str:
    """A path exactly as a terminal or a file manager hands it over.

    Dragging a folder onto a terminal window pastes it quoted - macOS uses
    `'/Users/me/My Project'`, some shells escape the spaces instead - and
    dragging it onto a form pastes a `file://` URL. All three were rejected
    with `path not found`, quotes and all, which is the tool blaming the
    person for the paste its own prompt invited.

    Only *matched* wrapping quotes are removed: a directory really can be
    called `it's`, and stripping one apostrophe off that name would break a
    path that worked.
    """
    from urllib.parse import unquote, urlparse

    text = (target or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    if text.startswith("file://"):
        parsed = urlparse(text)
        text = unquote(parsed.path or "")
    # `\ ` is how a shell escapes a space in a dragged path. Unescaped only
    # for a path that exists that way, so a Windows-style `C:\dir` and a
    # regex-looking argument are left alone.
    if "\\" in text:
        from pathlib import Path

        candidate = text.replace("\\ ", " ").replace("\\", "")
        if Path(candidate).exists():
            text = candidate
    return text.strip()


def looks_like_url(target: str) -> bool:
    """Is this target meant as a website rather than a path on disk?

    `https://example.com` is unambiguous; `example.com` is what people
    actually type, and answering it with `path not found: example.com` is
    the wrong answer to a question that had one obvious reading. So a target
    with no scheme is treated as a host when it *looks* like one and there
    is no such file or directory - an existing path always wins, so a folder
    genuinely named `example.com` still scans as a folder.

    Deliberately not "anything without a slash": `./src`, `src`, `~/repo`
    and `page.html` must keep resolving as paths, and a single word with no
    dot and no port is far more likely a typo'd directory than a hostname.
    """
    if not target:
        return False
    if target.startswith(("http://", "https://")):
        return True
    # Another scheme entirely (file://, ftp://, mailto:) is not ours to crawl.
    if "://" in target:
        return False
    from pathlib import Path
    try:
        if Path(target).exists():
            return False
    except OSError:
        pass  # a name too long or otherwise unopenable is not a path
    if target.startswith(("/", ".", "~")):
        return False
    if not _bare_host_pattern().match(target):
        return False
    # `page.html` matches the host shape - `.html` is TLD-shaped - but a
    # target with no slash, no port and a file suffix is a file the user
    # expected to find, and reporting it as an unreachable website would
    # hide the real answer: it is not there. A suffix inside a path
    # (`example.com/page.html`) is unaffected; the host is what is checked.
    host = target.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if ":" in host:
        return True
    import posixpath
    return posixpath.splitext(host)[1].lower() not in _FILE_SUFFIXES


def with_scheme(target: str) -> str:
    """`example.com` -> `https://example.com`; an explicit scheme is kept."""
    if target.startswith(("http://", "https://")):
        return target
    return "https://" + target


def _render_mode(args) -> str:
    """When to hand a page to a browser during the crawl.

    Defaults to following the browser pass: auditing a page means loading
    it for real, and a client-rendered site is precisely where the plain
    fetch finds nothing to audit. `--no-browser` turns both off together.
    `--render` overrides either way, because "audit what the server sends"
    is also a legitimate question.
    """
    from crawler import RENDER_AUTO, RENDER_NEVER

    explicit = getattr(args, "render", None)
    if explicit:
        return explicit
    if getattr(args, "no_browser", False):
        return RENDER_NEVER
    return RENDER_AUTO


def apply_session(target: str, config, use_session: bool = True) -> str:
    """Sign this crawl in, when the person has signed in to this host.

    Both halves or neither. `requests` fetches the pages and QtWebEngine
    renders them, and the two share no storage: giving the cookies to one of
    them produces a run where the browser sees the account and the fetch sees
    the login form. So the cookies go on the config and the host is returned
    for the renderer, and the caller passes it on.

    Returns the host to render as, or `""`. Says so on stderr, because a run
    that is authenticated is a different run and the log has to show which:
    the host, never a value.
    """
    if not use_session:
        return ""
    import site_session

    host, count = site_session.apply_to(config, target)
    if not host:
        return ""
    progress.notice(
        "session",
        f"signed in as the stored session for {host} ({count} value(s); "
        f"pass --no-session to run as a stranger)",
        human=f"# [session] signed in as the stored session for {host} "
              f"({count} value(s); pass --no-session to run as a stranger)",
        host=host, values=count)
    return host


#: How the list of pages is found. `links` follows them from the target;
#: `sharepoint` asks the site for its page tree (`sharepoint_tree`).
PAGE_TREE_LINKS = "links"
PAGE_TREE_SHAREPOINT = "sharepoint"
PAGE_TREES = (PAGE_TREE_LINKS, PAGE_TREE_SHAREPOINT)


def sharepoint_pages(target: str, config, *, page_tree: str = PAGE_TREE_LINKS,
                     site_scope: str = "", progress_cb=None, cancelled=None,
                     render=None, walk=None, discover=None, session=None):
    """The pages of a run, found the way `page_tree` says. Qt-free, silent.

    Returns `(pages, tree)`. With `page_tree="sharepoint"` the site's own
    page tree is read first (`sharepoint_tree.discover`, signed in with
    `config.cookies`) and the crawl reads exactly those pages; `tree` is the
    `SiteTree`, and the caller decides what its status means. When the tree
    says the sign-in is missing or not enough (`auth-required`,
    `access-denied`) nothing is crawled and `pages` is empty - auditing the
    sign-in page would be the wrong answer. When the tree came back with no
    pages for another reason the crawl falls back to following links, inside
    `site_scope`, and `tree` still says why.

    `discover` and `session` are injectable for tests and for a caller that
    already holds a session; `render`, `walk` and `cancelled` go to
    `crawler.crawl` unchanged.
    """
    from crawler import crawl

    tree = None
    seeds = None
    if page_tree == PAGE_TREE_SHAREPOINT:
        import sharepoint_tree

        discover = discover or sharepoint_tree.discover
        if session is None:
            session = sharepoint_tree.session_from_cookies(config.cookies,
                                                           target)
        tree = discover(target, session, cancelled=cancelled)
        if tree.status in (sharepoint_tree.STATUS_AUTH,
                           sharepoint_tree.STATUS_ACCESS_DENIED):
            return [], tree
        if tree.status in (sharepoint_tree.STATUS_OK,
                           sharepoint_tree.STATUS_PARTIAL):
            seeds = sharepoint_tree.seed_urls(tree) or None
    kwargs = {"progress_cb": progress_cb}
    if render is not None:
        kwargs["render"] = render
    if walk is not None:
        kwargs["walk"] = walk
    if cancelled is not None:
        kwargs["cancelled"] = cancelled
    if seeds:
        kwargs["seeds"] = seeds
    if site_scope:
        kwargs["site_scope"] = site_scope
    return crawl(target, config, **kwargs), tree


def crawl_site(target: str, config, *, progress_cb=None, session_host: str = "",
               within: str = "", page_tree: str = PAGE_TREE_LINKS,
               site_scope: str = "", walk=None):
    """`sharepoint_pages` with a browser started when the config can use one.

    Returns `(pages, tree)`, like `sharepoint_pages`.
    """
    from crawler import RENDER_NEVER

    def _pages(render=None):
        return sharepoint_pages(target, config, page_tree=page_tree,
                                site_scope=site_scope, progress_cb=progress_cb,
                                render=render, walk=walk)

    if config.render_mode == RENDER_NEVER:
        return _pages()

    from audit import driver

    usable, reason = driver.available()
    if not usable:
        _say_no_renderer(reason)
        return _pages()
    extra = {"within": within} if within else {}
    with driver.html_renderer(session_host=session_host, **extra) as render:
        return _pages(render)


def _say_no_renderer(reason) -> None:
    progress.notice(
        "browser",
        f"browser rendering unavailable: {reason}. SPA/React/Vue pages "
        f"may return empty results; install PySide6 and QtWebEngine for "
        f"full SPA support.",
        human=f"# Browser rendering unavailable: {reason}\n"
              f"# SPA/React/Vue pages may return empty results.\n"
              f"# Install PySide6 and QtWebEngine for full SPA support.",
        available=False, reason=str(reason))


@dataclass
class SharePointRun:
    """What a SharePoint target changes about a run, and who decided it."""
    #: Read as SharePoint: zones in the audit, the sign-in required.
    sharepoint: bool = False
    page_tree: str = PAGE_TREE_LINKS
    site_scope: str = ""
    #: `always` when the run should render every page; `None` leaves
    #: `--render` / the default alone.
    render: str | None = None
    #: The options set by the target rather than by hand, for a notice.
    automatic: tuple = ()


def plan_sharepoint(target: str, args) -> SharePointRun:
    """Read the SharePoint recipes of `run_profile` for this target.

    A flag the person typed always wins: `--page-tree links` keeps the walk
    on a SharePoint host, `--render never` keeps the fetch. What the target
    decided is listed in `automatic`, so the CLI can say it out loud.
    """
    import project_profile
    import run_profile

    run = SharePointRun(sharepoint=project_profile.is_sharepoint_online(target))
    plan = run_profile.build(target, forced_url=True,
                             repo=getattr(args, "repo", None) or "",
                             signed_in=True)
    automatic = []
    chosen = getattr(args, "page_tree", None)
    if chosen:
        run.page_tree = chosen
    else:
        item = plan.suggestion("page_tree")
        if item is not None:
            run.page_tree = item.value
            automatic.append("page_tree")
    scope = getattr(args, "site_scope", None)
    if scope:
        run.site_scope = scope
    else:
        item = plan.suggestion("site_scope")
        if item is not None:
            run.site_scope = item.value
            automatic.append("site_scope")
    item = plan.suggestion("render")
    if (item is not None and not getattr(args, "render", None)
            and not getattr(args, "no_browser", False)):
        run.render = item.value
        automatic.append("render")
    if run.page_tree == PAGE_TREE_SHAREPOINT:
        run.sharepoint = True
    run.automatic = tuple(automatic)
    return run


def login_hint(target: str) -> str:
    return f"xanalyze login {target}"


def missing_session_message(target: str, host: str, no_session: bool) -> str:
    """Why a SharePoint run without a sign-in stops before it starts."""
    if no_session:
        return (f"{host} is SharePoint Online, and --no-session reads it as a "
                f"stranger: every address answers with Microsoft's sign-in "
                f"page, and auditing that is not auditing the site. Drop "
                f"--no-session, or sign in first: {login_hint(target)}")
    return (f"{host} is SharePoint Online and there is no stored sign-in for "
            f"it: every address would answer with Microsoft's sign-in page. "
            f"Sign in first, then run again: {login_hint(target)}")


def sign_in_refusal(target: str, args) -> str:
    """Why a SharePoint Online run cannot start, or `""`. Writes nothing.

    Asked before the run folder is prepared, so a run refused for a missing
    sign-in leaves no empty dated folder behind. Every address of a tenant
    without a session answers with Microsoft's sign-in page, and an audit of
    that page is not an audit of the site.
    """
    import project_profile

    if not project_profile.is_sharepoint_online(target):
        return ""
    host = project_profile._host_of(target)
    if getattr(args, "no_session", False):
        return missing_session_message(target, host, True)
    import site_session

    try:
        signed_in = site_session.has_session(site_session.host_of(target))
    except Exception:  # noqa: BLE001 - a session that cannot be read is none
        signed_in = False
    return "" if signed_in else missing_session_message(target, host, False)


def session_refusal(target: str, config, session_host: str,
                    no_session: bool) -> str:
    """Why a SharePoint run that got past `sign_in_refusal` still cannot read.

    The session existed when the run started, and then either was not
    applied (`session_host` empty) or handed the fetcher no values at all - a
    profile whose cookies cannot be read. Crawling on would read every page
    as a stranger, i.e. Microsoft's sign-in page. `""` when the run may go on.
    """
    import project_profile

    if not project_profile.is_sharepoint_online(target):
        return ""
    if session_host and list(getattr(config, "cookies", None) or ()):
        return ""
    return missing_session_message(target, project_profile._host_of(target),
                                   no_session)


def registry_refusal(args) -> str:
    """Load `--ootb-registry` onto `args._ootb_registry`, or say why not.

    Called before the run folder exists: reading a local JSON file needs no
    network, and a mistyped path must not leave an empty folder behind.
    """
    path = getattr(args, "ootb_registry", None) or ""
    try:
        registry, entries = load_ootb_registry(path)
    except SystemExit as exc:
        args._ootb_registry = None
        return str(exc)
    args._ootb_registry = registry
    say_registry(registry, entries, path)
    return ""


def say_refusal(message: str, target: str, reason: str) -> None:
    """The refusal line both commands print, with the command that fixes it."""
    progress.notice("error", message, human=message, reason=reason,
                    login=login_hint(target))


def say_plan(sp) -> None:
    """`# [sharepoint] SharePoint site: --page-tree=...` for what the target set."""
    if not sp.automatic:
        return
    values = {"page_tree": sp.page_tree, "site_scope": sp.site_scope,
              "render": sp.render}
    said = ", ".join(f"--{name.replace('_', '-')}={values[name]}"
                     for name in sp.automatic)
    progress.notice(
        "sharepoint", f"SharePoint site: {said}",
        human=f"# [sharepoint] SharePoint site: {said} "
              f"(a flag given by hand overrides any of them)",
        page_tree=sp.page_tree, site_scope=sp.site_scope,
        render=sp.render or "")


def say_tree(tree) -> None:
    """What the page tree found, or why the crawl follows links instead."""
    if tree is None:
        return
    if tree.pages:
        line = (f"page tree: {len(tree.pages)} page(s) in {len(tree.webs)} "
                f"site(s), {len(tree.documents)} document(s) not audited, "
                f"{sum(tree.skipped_counts().values())} address(es) left out "
                f"({tree.status})")
        progress.notice("sharepoint", line, human=f"# [sharepoint] {line}",
                        status=tree.status, pages=len(tree.pages))
    else:
        line = f"page tree unavailable ({tree.status}); following links instead"
        progress.notice("sharepoint", line, human=f"# [sharepoint] {line}",
                        status=tree.status,
                        errors=[e.message for e in tree.errors][:5])


def say_registry(registry, entries: int, path: str) -> None:
    if registry is None:
        return
    line = f"OOTB registry: {entries} entr(ies) from {path}"
    progress.notice("sharepoint", line, human=f"# [sharepoint] {line}",
                    entries=entries)


def tree_refusal(tree, target: str) -> str:
    """The sentence for a page tree that cannot be read as this person, or ""."""
    import sharepoint_tree

    if tree is None:
        return ""
    host = urlparse(target).hostname or target
    if tree.status == sharepoint_tree.STATUS_AUTH:
        return (f"SharePoint answered {host} with a sign-in "
                f"({tree.auth_reason or 'sign-in required'}): the stored "
                f"session is missing or has expired. Sign in again, then run "
                f"again: {login_hint(target)}")
    if tree.status == sharepoint_tree.STATUS_ACCESS_DENIED:
        return (f"SharePoint refused {host}: the stored session is signed in "
                f"but has no permission on this site. Sign in as an account "
                f"that can open it ({login_hint(target)}), or ask the site "
                f"owner for access.")
    return ""


def page_tree_summary(tree, walk=None, site_scope: str = "",
                      page_tree: str = PAGE_TREE_LINKS) -> dict:
    """What the page list was and what it left out - for the JSON summary.

    Every number here is something the run did *not* audit or could not
    read, so it is carried whole: a list of skipped addresses reduced to a
    total would hide which kind of address was skipped.
    """
    out: dict = {"mode": page_tree}
    if site_scope:
        out["site_scope"] = site_scope
    if walk is not None:
        out["out_of_scope"] = walk.out_of_scope
        out["pages_read"] = walk.pages_read
        out["not_read"] = walk.queued_when_stopped
    if tree is None:
        return out
    out.update({
        "status": tree.status,
        "pages": len(tree.pages),
        "webs": [web.url for web in tree.webs],
        "documents": [{"url": doc.url, "title": doc.title}
                      for doc in tree.documents],
        "skipped": tree.skipped_counts(),
        "errors": [{"source": e.source, "url": e.url, "status": e.status,
                    "message": e.message} for e in tree.errors],
        "truncated": tree.truncated,
        "requests": tree.requests_made,
    })
    return out


def load_ootb_registry(path: str):
    """`--ootb-registry FILE`: Microsoft's web part ids read from a live page.

    Returns `(registry, entries)`; `(None, 0)` without a path. A file that
    cannot be read raises `SystemExit` with the reason - a registry asked
    for and silently missing would audit Microsoft's parts as custom code.
    """
    if not path:
        return None, 0
    from audit import sharepoint_zones

    registry = sharepoint_zones.OotbRegistry()
    try:
        entries = registry.load_file(path)
    except (OSError, ValueError, AttributeError) as exc:
        raise SystemExit(f"--ootb-registry {path}: {exc}") from None
    return registry, entries


def _crawl_maybe_rendering(target: str, config, progress_cb=None,
                           session_host: str = "", within: str = ""):
    """Crawl, starting a browser only if the configuration can use one."""
    pages, _tree = crawl_site(target, config, progress_cb=progress_cb,
                              session_host=session_host, within=within)
    return pages


#: Suffixes a document can carry that are not a page. The media pass reports
#: an image's provenance as a document of its own (`audit/media.py`), and the
#: source of that document is the image address - so on a photo-heavy site
#: the browser pass was opening `.jpg` and `.pdf` in a page engine and running
#: axe against whatever the browser wrapped them in. Measured on a live
#: WordPress site: 50 of 502 documents, each at four widths.
_NOT_A_PAGE = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".bmp",
               ".svg", ".pdf", ".mp4", ".webm", ".mp3", ".zip")


def unread_sources(documents) -> set:
    """Addresses some pass could not read, so the browser must not load them.

    A page refused by the crawl (larger than its ceiling, not HTML, an
    error) still gets a document from passes that need no HTML, such as the
    response headers - and that document, carrying no error, used to send
    the page to the browser anyway: a 13 MB page the crawl had refused was
    loaded into QtWebEngine on the window's thread.
    """
    return {d.source for d in documents if d.error}


def _is_renderable(source: str) -> bool:
    """Is this document something a browser should open as a page?

    Asked of the address, because that is all a document carries here. A
    query string means the address does not end in its own suffix, and such
    a url is left in: it is far likelier a page than a bare `.jpg`.
    """
    address = str(source or "").split("?", 1)[0].split("#", 1)[0].lower()
    return not address.endswith(_NOT_A_PAGE)


def _browser_url(source: str) -> str:
    """The address the browser should open for a document.

    A crawled page already is a URL. A file has to become one, and it has to
    be absolute: `file://page.html` is not a path the browser can resolve.
    """
    if source.startswith(("http://", "https://", "file://")):
        return source
    from pathlib import Path
    return Path(source).resolve().as_uri()


def _wrap(text: str, width: int = 96, indent: str = "      ") -> str:
    """Fold a paragraph for terminal output; the explanations are written as
    prose, and prose at 400 columns is unreadable."""
    import textwrap
    lines = textwrap.wrap(text, width=width)
    return ("\n" + indent).join(lines)
