"""Headless mode — the same engine as the desktop app, driven from a
terminal so it can run as a post-processing step after an LLM coding agent
(Claude Code, Codex, Cursor and friends) has written files.

Typical use: the agent edits your source, then this runs over the result
and strips the characters no keyboard produces — curly quotes, em dashes,
non-breaking spaces, zero-width joiners, letters lifted from the wrong
alphabet — before anything reaches a commit.

    python cli.py fix ./src                  # clean files in place
    python cli.py scan ./src --json          # machine-readable report
    python cli.py scan ./src --check         # exit 1 if anything is found
    echo "text" | python cli.py clean        # filter text on stdin

Imports no GUI toolkit, so it runs anywhere Python does — a git hook, CI,
a container, an agent's shell tool.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

import detectors  # noqa: F401 - registers the detectors
import progress
import suppression
import unicode_rules
import config
from config import APP_VERSION
from audit.base import (
    CATEGORIES, CONFIDENCE_ORDER, issues_in_view, unsettled_count,
    unsettled_summary,
)
from detectors.factory import DetectorFactory
from file_writer import ReplacementPlan, apply_replacements
from lang_detect import guess_language
from models import Confidence
from repo_scanner import DEFAULT_EXTENSIONS, scan_repo
# The scan pipeline and the terminal output live in `cli_impl`; the names are
# imported here so both this module's own commands and anything that does
# `import cli` keep working unchanged.
from cli_impl.scanning import (  # noqa: F401 - re-exported for `import cli`
    CHARACTER_SOURCE, HYBRID_NAME,
    _analyze, _build_ignore_list, _build_scan_config, _categories,
    _collect_files, _create_detector, _ignore_root, _report_detector_errors,
    _settings_for_ignore, _split_unchanged, _store_unchanged,
)
from cli_impl.output import (  # noqa: F401 - re-exported for `import cli`
    _counts, _coverage_line, _print_human, _print_json, _public, _visible,
)
from cli_impl.reports import (  # noqa: F401 - re-exported for `import cli`
    _file_map, _fix_summary, _history_dir, _history_key, _now, _previous_run,
    _read_history, _report_markdown, _write_history, _write_report,
    _write_styled_text_report,
)
from cli_impl.auditpass import (  # noqa: F401 - re-exported for `import cli`
    PAGE_FILE_SUFFIXES, _audit_at_widths, _browser_url,
    _chosen_breakpoints, _crawl_maybe_rendering, _is_page_file,
    _render_mode, _run_browser_pass, _wrap, apply_session, looks_like_url,
    unquote_target, with_scheme,
)
from cli_impl.aicmds import (  # noqa: F401 - re-exported for `import cli`
    _provider_for, _xformat_provider,
    cmd_ai_apps, cmd_ai_grant, cmd_ai_login, cmd_ai_logout, cmd_ai_revoke,
    cmd_ai_rewrite, cmd_ai_status,
)
from cli_impl.agentcmds import (  # noqa: F401 - re-exported for `import cli`
    _agent_detection_rules, cmd_agent_judge, cmd_agent_scan,
)
from cli_impl.fullscan import (  # noqa: F401 - re-exported for `import cli`
    cmd_fullscan,
)
from cli_impl.uninstall import (  # noqa: F401 - re-exported for `import cli`
    cmd_uninstall,
)

# Re-exported rather than defined here: the window needs the same mapping,
# and the copy that used to live in this file was invisible to it. See
# `detectors/judges.py`.
from detectors.judges import (  # noqa: F401 - re-exported for `import cli`
    JUDGE_ALIASES, JUDGE_BY_PROVIDER, JUDGE_NAMES, judge_for_provider,
)

from cli_impl import (  # noqa: F401 - re-exported for `import cli`
    EXIT_ERROR, EXIT_FINDINGS, EXIT_OK,
)


#: The exit codes, in the one place a person or an agent will look for them:
#: `xanalyze --help`. They were always the same four values, but the list
#: existed only as constants in `cli_impl`, which is not a contract anybody
#: outside this repository can read - and a caller that cannot tell 1
#: ("found something") from 2 ("the command was wrong") has to parse prose to
#: find out whether its scan worked.
#:
#: What `--check` counts differs per command, and that is deliberate rather
#: than an oversight: a text scan reports any finding, an audit reports the
#: two severities that mean the page is broken for somebody. Said here,
#: because a difference nobody documented is indistinguishable from a bug.
EXIT_CODE_HELP = """exit codes:
  0  clean - the command did what it was asked and found nothing to report
  1  findings - only with --check. `scan`/`fix`/`clean`: any finding.
     `audit`/`fullscan`: a critical or serious one
  2  error - the command could not run: a path that does not exist, a flag
     that does not apply, a detector that could not read the text
  3  incomplete - a run stopped part-way and its work is on disk;
     `xanalyze resume` continues it

progress protocol:
  --progress jsonl writes one JSON object per line to stderr while the run
  happens (events: run.start, stage, page, file, notice, finding, run.end).
  Add =findings for one object per finding. See progress.py."""


# ---------------------------------------------------------------- commands

def cmd_scan(args) -> int:
    missing: list = []
    unjudged: list = []
    walked: list = []

    # A dated folder, and the two documents in it, unless this run is being
    # parsed rather than read. See `runfolder.prepare_for`.
    from cli_impl import runfolder

    target_for_folder = args.paths[0] if args.paths else "."
    folder = runfolder.prepare_for(target_for_folder, args)

    from cli_impl import prerun

    prerun.announce("scan", target_for_folder, args, is_url=False, out=sys.stderr)

    files = _collect_files(args.paths, args, missing_out=missing,
                           diagnostics_out=walked)

    incremental = bool(getattr(args, "incremental", False))
    cached_findings: list = []
    to_read = files
    if incremental:
        to_read, cached_findings, reused = _split_unchanged(files, args)
        progress.notice(
            "scan",
            f"incremental: {reused} file(s) unchanged since the last scan, "
            f"{len(to_read)} re-read",
            human=f"# incremental: {reused} file(s) unchanged since the last "
                  f"scan, {len(to_read)} re-read",
            reused=reused, reread=len(to_read))

    progress.stage("scan", "begin", files=len(to_read))
    findings, _ = _analyze(to_read, args, unjudged_out=unjudged)
    progress.stage("scan", "end", findings=len(findings))
    if incremental:
        _store_unchanged(to_read, findings, args)
        # Cached rows have no `TextSpan` behind them - it does not survive
        # JSON - so the styled report, which reads spans, covers only the
        # files actually re-read this run. It says so; see
        # `_write_styled_text_report`.
        findings = findings + cached_findings
        findings.sort(key=lambda f: (f.get("file", ""), f.get("offset", 0)))
    progress.set_summary(counts=_counts(findings))
    if args.json:
        _print_json(findings, walked=walked)
    else:
        _print_human(findings, walked=walked,
                     scope=getattr(args, "scope", "content"))
    if getattr(args, "report", None):
        from cli_impl.reports import write_text_briefing

        write_text_briefing(files, findings, args, args.report)
    if getattr(args, "styled_report", None):
        _write_styled_text_report(files, findings, args)
    if folder is not None:
        progress.notice("run-folder", str(folder.run),
                        human=f"# run folder: {folder.run}",
                        path=str(folder.run))
    if missing:
        # Said again at the end: the warning above scrolls past a long report,
        # and "nothing found" plus exit 0 is indistinguishable from success.
        progress.notice(
            "warning",
            f"{len(missing)} path(s) did not exist; nothing was read from "
            f"them",
            human=f"# {len(missing)} path(s) did not exist; nothing was read "
                  f"from them",
            missing=len(missing))
        return EXIT_ERROR
    if unjudged:
        # Same rule, one step further in: a detector that was asked and could
        # not answer leaves the text unread, and exit 0 would report that as
        # clean to whatever runs this in a pipeline.
        progress.notice(
            "warning",
            "the requested detector could not read the text; the result "
            "above is not a clean bill of health",
            human="# the requested detector could not read the text; "
                  "the result above is not a clean bill of health",
            unjudged=len(unjudged))
        return EXIT_ERROR
    if args.check and findings:
        return EXIT_FINDINGS
    return EXIT_OK


def cmd_fix(args) -> int:
    files = _collect_files(args.paths, args)
    findings, _ = _analyze(files, args)

    # Only the non-keyboard-character findings carry a deterministic
    # correction; style findings need a human or a model and are reported
    # but never auto-applied.
    fixable = [f for f in findings
               if f["source"] == CHARACTER_SOURCE and f["replacement"] is not None
               and f["replacement"] != f["text"]]

    if args.dry_run:
        if args.json:
            _print_json(findings, applied={"dry_run": True, "would_fix": len(fixable)})
        else:
            _print_human(findings)
            print(f"\nDry run — would fix {len(fixable)} occurrence(s), nothing written.")
        return EXIT_FINDINGS if (args.check and findings) else EXIT_OK

    plans = [
        ReplacementPlan(
            file_path=f["_block"].file_path,
            abs_start=f["offset"],
            abs_end=f["end_offset"],
            original_text=f["text"],
            new_text=f["replacement"],
            block_id=f["_block"].block_id,
            allow_empty=(f["replacement"] == ""),
        )
        for f in fixable
    ]
    result = apply_replacements(plans) if plans else None

    if args.no_backup and result:
        # Don't delete existing .bak files from previous runs — only skip
        # creating new ones. The user might need them for recovery.
        pass

    applied = {
        "passages_applied": result.passages_applied if result else 0,
        "files_changed": result.files_changed if result else [],
        "skipped_stale": len(result.passages_skipped_stale) if result else 0,
        "skipped_overlap": len(result.passages_skipped_overlap) if result else 0,
        "errors": result.errors if result else [],
    }

    if args.json:
        _print_json(findings, applied=applied)
    else:
        _print_human(findings)
        print(f"\nFixed {applied['passages_applied']} occurrence(s) "
              f"in {len(applied['files_changed'])} file(s).")
        if applied["skipped_stale"]:
            print(f"Skipped {applied['skipped_stale']} (file changed since scan).")
        if applied["errors"]:
            for err in applied["errors"]:
                print(f"error: {err}", file=sys.stderr)

    if applied["errors"]:
        return EXIT_ERROR
    if args.check and findings:
        return EXIT_FINDINGS
    return EXIT_OK


def cmd_clean(args) -> int:
    """Filter text on stdin to stdout. Handy for piping a model's output
    through before it's written anywhere."""
    text = sys.stdin.read()
    language = args.language or guess_language(text)
    cleaned = unicode_rules.clean_text(text, language, _categories(args))
    sys.stdout.write(cleaned)
    if args.check and cleaned != text:
        return EXIT_FINDINGS
    return EXIT_OK


def cmd_cache(args) -> int:
    """Manage the scan cache."""
    from scan_cache import get_cache
    
    cache = get_cache()
    
    if args.cache_command == "stats":
        stats = cache.stats()
        print(f"Cache entries: {stats['entries']}")
        print(f"Cache size: {stats['size_bytes']} bytes")
        return EXIT_OK
    
    if args.cache_command == "clear":
        cache.clear()
        print("Cache cleared.")
        return EXIT_OK
    
    if args.cache_command == "path":
        print(cache.cache_path)
        return EXIT_OK
    
    return EXIT_OK


def cmd_compare(args) -> int:
    """Compare different detectors on the same files."""
    files = _collect_files(args.paths, args)
    if not files:
        print("No files found.", file=sys.stderr)
        return EXIT_ERROR
    
    blocks = [b for f in files for b in f.blocks]
    if not blocks:
        print("No text blocks found.", file=sys.stderr)
        return EXIT_ERROR
    
    detectors_to_compare = ["offline", "embedding"]
    results = {}
    
    for det_name in detectors_to_compare:
        try:
            detector = DetectorFactory.create(det_name)
            spans = detector.analyze_blocks(blocks)
            style_spans = [s for s in spans 
                          if s.confidence != Confidence.LOW
                          and (s.details or {}).get("source") != "characters"]
            results[det_name] = {
                "total": len(style_spans),
                "scores": [s.score for s in style_spans],
            }
        except Exception as e:
            results[det_name] = {"error": str(e)}
    
    if args.json:
        import json
        output = {}
        for name, data in results.items():
            if "error" in data:
                output[name] = data
            else:
                output[name] = {
                    "total": data["total"],
                    "mean_score": sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0,
                    "max_score": max(data["scores"]) if data["scores"] else 0,
                }
        print(json.dumps(output, indent=2))
    else:
        print(f"Comparing detectors on {len(blocks)} blocks:")
        print()
        for name, data in results.items():
            if "error" in data:
                print(f"  {name}: error - {data['error']}")
            else:
                mean = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
                max_s = max(data["scores"]) if data["scores"] else 0
                print(f"  {name}: {data['total']} findings, "
                      f"mean={mean:.3f}, max={max_s:.3f}")
    
    return EXIT_OK


def _web_parts_for(args) -> list:
    """The web parts `--web-parts` asks for, or `[]`.

    Refuses rather than guesses: without `--repo` there is no repository to
    read them from, and a flag that quietly did nothing would leave a whole
    site audited as one page under a report the caller narrowed on purpose.
    """
    if not getattr(args, "web_parts", False):
        return []
    repo = getattr(args, "repo", None)
    if not repo:
        progress.notice(
            "web-parts",
            "--web-parts needs --repo: the parts are read from the solution "
            "that ships them",
            human="# --web-parts needs --repo: the parts are read from the "
                  "solution that ships them")
        return []
    from audit import spfx

    found = spfx.web_parts(repo)
    if not found:
        progress.notice(
            "web-parts",
            f"no web part manifest under {repo} - nothing to confine the "
            f"audit to, so the whole page is read",
            human=f"# --web-parts: no web part manifest under {repo} - "
                  f"nothing to confine the audit to, so the whole page is "
                  f"read",
            repo=str(repo), parts=0)
        return []
    aliases = [p.alias for p in found]
    progress.notice(
        "web-parts", f"{len(found)} part(s) from {repo}: "
                     f"{', '.join(aliases[:6])}",
        human=f"# [web-parts] {len(found)} part(s) from {repo}: "
              f"{', '.join(aliases[:6])}{'…' if len(found) > 6 else ''}",
        repo=str(repo), parts=len(found), aliases=aliases)
    return found


def _served_by_sharepoint(target: str, pages) -> bool:
    """Did the crawled markup say SharePoint, as an on-premises farm does?"""
    import project_profile

    for page in pages[:5]:
        markup = getattr(page, "raw_html", "") or ""
        if markup and any(stack.name == "sharepoint" for stack in
                          project_profile.detect_from_url(target, markup).stacks):
            return True
    return False


def _narrow_to_project(target: str, args):
    """`(target, "")`, or `("", why not)` when `--project` names nothing.

    Shared by `audit` and `fullscan`, and refusing rather than guessing: a
    misspelled project silently auditing the whole folder is the behaviour
    `--project` exists to replace, and it would look exactly like success.
    """
    import run_profile

    wanted = (getattr(args, "project", None) or "").strip()
    if not wanted:
        return target, ""
    plan = run_profile.build(target, forced_url=getattr(args, "url", False))
    if plan.kind != run_profile.KIND_REPO:
        return "", ("--project names a folder inside a folder; "
                    f"{target} is not one")
    chosen = run_profile.choose_project(plan, wanted)
    if chosen:
        progress.notice(
            "profile",
            f"auditing {wanted} on its own, not the whole folder",
            human=f"# [profile] auditing {wanted} on its own, not the whole "
                  f"folder",
            project=wanted)
        return chosen, ""
    choices = ", ".join(plan.choices()) or "none - nothing under it proved a stack"
    return "", f"--project {wanted}: no such project here. Found: {choices}"


def cmd_audit(args) -> int:
    """Audit a URL or a folder across all six categories.

    Kept in the same CLI as the text scan because it answers a question about
    the same artefact and belongs in the same pre-commit hook or pipeline
    step, not because the two analyses share code — they do not.
    """
    import audit
    from audit.explanations import one_line, render, summary_line
    from i18n.translations import t
    from cli_impl import runfolder

    # Built before the crawl so a missing sign-in fails immediately, rather
    # than after crawling thirty pages.
    reviewer = None
    if getattr(args, "ai", False):
        from audit.ai_review import AIAccessibilityReview

        name, provider = _provider_for(args)
        progress.notice("ai-patterns", f"AI pass via {name}",
                        human=f"# AI pass via {name}", provider=name)
        reviewer = AIAccessibilityReview(provider=provider)

    # As a terminal or a file manager hands it over: quoted, escaped, or
    # as a `file://` URL. See `cli_impl.auditpass.unquote_target`.
    target = unquote_target(args.target)
    # `example.com` is what people type; treating it as a path and answering
    # "path not found" is the wrong answer to a question that had one obvious
    # reading. An existing path still wins - see `looks_like_url`.
    is_url = looks_like_url(target) or args.url
    if is_url:
        target = with_scheme(target)
    # A target that is neither a URL nor a path that exists is a typo, and the
    # only honest answer is to say so. Auditing it used to print "0 findings"
    # and exit 0 - which in a pipeline is a pass, so a mistyped path read as a
    # clean bill of health.
    if not is_url and not Path(target).exists():
        progress.notice("error", f"path not found: {target}",
                        human=f"path not found: {target}")
        return EXIT_ERROR

    # `--project`: one deliverable out of a folder that holds several. Done
    # before the run folder is prepared, so the folder is named after what
    # was audited.
    narrowed, refusal = _narrow_to_project(target, args)
    if refusal:
        progress.notice("error", refusal, human=refusal)
        return EXIT_ERROR
    target = narrowed

    # A SharePoint Online target without a sign-in is refused before the run
    # folder exists: a refused run must not leave an empty folder behind.
    if is_url:
        from cli_impl import auditpass

        refusal = auditpass.sign_in_refusal(target, args)
        if refusal:
            auditpass.say_refusal(refusal, target, "sign-in-required")
            return EXIT_ERROR
    # `--ootb-registry` is a local file: read before the folder, so a typo
    # in its path leaves nothing behind.
    from cli_impl import auditpass as _auditpass

    refusal = _auditpass.registry_refusal(args)
    if refusal:
        progress.notice("error", refusal, human=refusal)
        return EXIT_ERROR

    # Prepared after the target is resolved, so the folder is named by what
    # was audited rather than by what was typed.
    folder = runfolder.prepare_for(target, args)

    from cli_impl import prerun

    prerun.announce("audit", target, args, is_url=is_url, out=sys.stderr)
    # What this target's own stack asks for. A line, unless
    # `--profile-defaults` was passed - see `cli_impl.prerun.profile`.
    prerun.profile("audit", target, args, is_url=is_url, out=sys.stderr)

    #: Which host's stored sign-in this run used, if any. Set by the crawl
    #: branch below and read when the walls are announced: an expired-session
    #: notice only makes sense for a run that actually used one.
    session_host = ""

    if _is_page_file(target) and not args.url:
        # A page built into one file is a finished document, so it is audited
        # as a page: `<head>` included, line numbers on, and - with --browser -
        # rendered from `file://`, which is faithful precisely because
        # everything it needs is inlined.
        result = audit.analyze_page_file(
            target, ai_review=reviewer,
            within=getattr(args, "within", None) or "",
            web_parts=_web_parts_for(args))
    elif is_url:
        from crawler import CrawlConfig, EMPTY_JS_RENDERED
        from models import CrawlDiagnostics

        from cli_impl import auditpass

        # What a SharePoint target changes: the page list, the scope, the
        # render mode. A flag typed by hand wins; what the target decided is
        # said out loud. See `cli_impl.auditpass.plan_sharepoint`.
        sp = auditpass.plan_sharepoint(target, args)
        # Same crawler as the text scan: depth-limited, and refusing to leave
        # the domain. That rule holds for both modes because there is one
        # crawler, not two.
        config = CrawlConfig(max_depth=args.depth, max_pages=args.max_pages,
                             render_mode=sp.render or _render_mode(args))
        auditpass.say_plan(sp)
        # A site the person signed in to is read as them, in both clients.
        # See `cli_impl.auditpass.apply_session`.
        no_session = bool(getattr(args, "no_session", False))
        session_host = apply_session(target, config,
                                     use_session=not no_session)

        # Checked before the run folder too (`sign_in_refusal`); this is
        # the session that existed then and could not be read now, or gave
        # the fetcher nothing.
        message = auditpass.session_refusal(target, config, session_host,
                                            no_session)
        if message:
            auditpass.say_refusal(message, target, "sign-in-required")
            return EXIT_ERROR
        # Loaded before the run folder (`registry_refusal`).
        registry = getattr(args, "_ootb_registry", None)
        # Read once, here: `--web-parts` prints what it found, and the
        # browser pass needs the same list.
        args._web_parts_found = _web_parts_for(args)

        crawled = 0

        def _crawl_progress(url: str, depth: int) -> None:
            nonlocal crawled
            crawled += 1
            limit = f"/{args.max_pages}" if args.max_pages else ""
            progress.page(crawled, args.max_pages or None, url, depth=depth,
                          human=f"# [crawl {crawled}{limit}] depth={depth} "
                                f"{url}")

        walk = CrawlDiagnostics()
        pages, tree = auditpass.crawl_site(
            target, config, progress_cb=_crawl_progress,
            session_host=session_host, page_tree=sp.page_tree,
            site_scope=sp.site_scope, walk=walk)
        refusal = auditpass.tree_refusal(tree, target)
        if refusal:
            auditpass.say_refusal(refusal, target, tree.status)
            return EXIT_ERROR
        auditpass.say_tree(tree)
        progress.stage("crawl", "end",
                       f"# [crawl done] {len(pages)} page(s)",
                       pages=len(pages))
        
        # Check if SPA pages were detected but not rendered
        spa_pages = [p for p in pages if EMPTY_JS_RENDERED in (p.diagnostics.reasons or [])]
        rendered_pages = [p for p in pages if "rendered" in (p.diagnostics.reasons or [])]
        if spa_pages and not rendered_pages:
            progress.notice(
                "spa",
                f"{len(spa_pages)} SPA page(s) detected but browser "
                f"rendering failed. Install PySide6 + QtWebEngine for SPA "
                f"support, or use --no-browser to skip rendering.",
                human=f"# WARNING: {len(spa_pages)} SPA page(s) detected but "
                      f"browser rendering failed.\n"
                      f"# Install PySide6 + QtWebEngine for SPA support, or "
                      f"use --no-browser to skip rendering.",
                failed=len(spa_pages), rendered=0)
        elif spa_pages and rendered_pages:
            progress.notice(
                "spa",
                f"{len(rendered_pages)} page(s) rendered via browser, "
                f"{len(spa_pages)} failed.",
                human=f"# SPA: {len(rendered_pages)} page(s) rendered via "
                      f"browser, {len(spa_pages)} failed.",
                rendered=len(rendered_pages), failed=len(spa_pages))
        
        progress.stage("audit", "begin", target=target)
        sharepoint = sp.sharepoint or _served_by_sharepoint(target, pages)
        extra = {}
        if sharepoint:
            extra = {"sharepoint": True, "ootb_registry": registry}
        result = audit.analyze_pages(
            pages, target, ai_review=reviewer,
            site_controls=getattr(args, "site_controls", False),
            within=getattr(args, "within", None) or "",
            web_parts=args._web_parts_found,
            include_environment=bool(getattr(args, "include_environment", False)),
            **extra)
        result.page_tree = auditpass.page_tree_summary(
            tree, walk, sp.site_scope, sp.page_tree)
    else:
        from repo_scanner import scan_repo

        progress.stage("audit", "begin", target=target)
        files = scan_repo(target, _build_scan_config(args, target=target))
        result = audit.analyze_files(files, target, ai_review=reviewer,
                                     force_medium=getattr(args, "medium", None))
    progress.stage("audit", "end",
                   documents=len(result.documents),
                   sources=len({d.source for d in result.documents}))

    # The same suppression list governs both analyses: a user thinking "not
    # this part of the site" means it for the whole tool, not per subsystem.
    suppressions = suppression.Suppressions.load(
        _settings_for_ignore(args), _ignore_root(args))

    # The browser pass is part of what "audit a page" means: a URL or a
    # self-contained file is loaded for real unless --no-browser says
    # otherwise. Repo mode never had a page to load, and the pass refuses
    # it on its own.
    if not getattr(args, "no_browser", False):
        _run_browser_pass(result, suppressions, args)

    result.suppressed = suppression.account_for_suppressed(
        [issue for document in result.documents for issue in document.issues],
        suppressions)
    for document in result.documents:
        document.issues = suppression.filter_issues(document.issues, suppressions)
    _announce_suppressed(result.suppressed)

    from audit.coverage import build_coverage
    result.coverage = build_coverage(result, args)

    # Category narrowing and the certainty floor are one *view* over one
    # pass, not a different run, and `audit.base.issues_in_view` is where
    # that view lives - the window applies the identical function to the
    # identical findings, which is what stops the two surfaces from
    # disagreeing about the same page.
    wanted = set(getattr(args, "category", None) or CATEGORIES)
    floor = getattr(args, "confidence", None) or ""
    unsettled = bool(getattr(args, "unsettled", False))
    # Counted before the view narrows, and said out loud below: a number
    # dropped in silence is a report lying by omission.
    hidden = 0 if unsettled else sum(unsettled_count(d.issues)
                                     for d in result.documents)
    which = "" if unsettled else unsettled_summary(
        [i for d in result.documents for i in d.issues])
    for document in result.documents:
        document.issues = issues_in_view(document.issues, wanted, floor,
                                         unsettled=unsettled)
    if hidden:
        progress.notice(
            "audit",
            f"{hidden} check(s) could not be decided and are not listed "
            f"({which}); add --unsettled to see them",
            human=f"# {hidden} check(s) could not be decided and are not "
                  f"listed ({which}); add --unsettled to see them",
            unsettled=hidden, unsettled_rules=which)
    # What a local site's server decides, left out of the list and said so:
    # `audit.environment` has the reason, `--include-environment` the list.
    left_out = (getattr(result, "environment", None) or {}).get("hidden", 0)
    if left_out:
        rules = ", ".join((result.environment.get("by_rule") or {}))
        progress.notice(
            "audit",
            f"{left_out} finding(s) about the local environment are not "
            f"listed ({rules}); add --include-environment to see them",
            human=f"# {left_out} finding(s) about the local environment "
                  f"(server headers, http forms, a development noindex) are "
                  f"not listed: they depend on the server, not the code; add "
                  f"--include-environment to see them",
            environment=left_out)
    _announce_auth_walls(result, session_host=session_host)

    from i18n.translations import report_language

    lang = report_language(args.language)

    fix_outcome = None
    if getattr(args, "fix", False):
        fix_outcome = _apply_fixes(result, args, lang)
        if fix_outcome.files_changed and result.mode in ("file", "repo"):
            # Re-read what is now on disk. Printing the numbers from before
            # the corrections were written would tell the user - or the agent
            # parsing `--json` - that work is outstanding when it is done.
            result = _reaudit(args, target, result)
            result.coverage = build_coverage(result, args)
            for document in result.documents:
                document.issues = suppression.filter_issues(
                    document.issues, suppressions)
            for document in result.documents:
                document.issues = issues_in_view(document.issues, wanted, floor)
    if getattr(args, "report", None):
        _write_report(result, args, lang, fix_outcome)
    if getattr(args, "styled_report", None):
        from report.export import write_styled_report
        from report.model import from_accessibility

        from cli_impl.reports import _command_of
        from cli_impl.runheader import describe

        model = from_accessibility(result, lang)
        model.meta.run = describe(_command_of(args), result.root, args,
                                  language=lang)
        model.meta.repo = str(getattr(args, "repo", "") or "")
        write_styled_report(args.styled_report, model, lang)
        progress.notice("report", f"styled report: {args.styled_report}",
                        human=f"# styled report: {args.styled_report}",
                        path=str(args.styled_report), kind_of="styled")
    if folder is not None:
        progress.notice("run-folder", str(folder.run),
                        human=f"# run folder: {folder.run}",
                        path=str(folder.run))

    # What `run.end` reports, recorded where the counts exist. See
    # `progress.set_summary`.
    progress.set_summary(counts=result.counts(),
                         documents=len(result.documents),
                         sources=len({d.source for d in result.documents}))
    if args.json:
        from duplicates import places_of
        from finding_contract import SCHEMA_VERSION, serialize_issue
        distinct = result.distinct()
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "root": result.root,
            "mode": result.mode,
            # `counts` counts distinct problems: a header on every page is one
            # job, not one per page. `occurrences` is the old number - every
            # place a problem was found - for a reader who wants it.
            "counts": result.distinct_counts(),
            "distinct": len(distinct),
            "occurrences": result.counts(),
            "problems": [{
                "rule": first.rule_id, "severity": first.severity,
                "category": first.category, "confidence": first.confidence,
                "snippet": first.snippet[:300], "selector": first.selector,
                "occurrences": len(others) + 1,
                "pages": len(places_of(first, others)),
                "sources": [p for p in places_of(first, others)][:25],
            } for first, others in distinct],
            "platform_owned": _owned_counts(result),
            # How the page list was found and what it left out; the zones a
            # SharePoint page was split into and what was not reported.
            "page_tree": getattr(result, "page_tree", {}) or {},
            "sharepoint": getattr(result, "sharepoint", {}) or {},
            "environment": getattr(result, "environment", {}),
            "suppressed": getattr(result, "suppressed", {}),
            "rules_run": result.rules_run,
            "coverage": getattr(result, "coverage", {}),
            "issues": [serialize_issue(issue, source=document.source)
                       for document in result.documents for issue in document.issues],
        }, ensure_ascii=False, indent=2, default=_json_default))
    else:
        for document in result.documents_with_issues():
            print()
            print(document.source)
            for issue in document.issues:
                explanation = render(issue, lang)
                location = f"line {issue.line}" if issue.line else issue.selector[-60:]
                owned = (f"  <- {t('a11y_owned_marker', lang, platform=issue.owner)}"
                         if issue.owner else "")
                print(f"  [{issue.severity}] {one_line(explanation.title)}  ({location}){owned}")
                print(f"      {explanation.found}")
                print(f"      {_wrap(explanation.why)}")
                print(f"      fix: {_wrap(explanation.fix)}")
                if issue.fix_snippet:
                    print(f"      -> {issue.fix_snippet}")
                if explanation.caveat:
                    print(f"      ! {explanation.caveat}")
        for document in result.documents:
            if document.error:
                print(f"\n{document.source}\n  not checked: {document.error}")
        print()
        print(summary_line(result, lang))
        for platform, count in sorted(_owned_counts(result).items()):
            print(t("a11y_platform_owned", lang, count=count, platform=platform))

    counts = result.counts()
    if args.check and (counts.get("critical") or counts.get("serious")):
        return EXIT_FINDINGS
    return EXIT_OK


def _owned_counts(result) -> dict:
    """`{platform: findings}` for what a platform emitted itself.

    Reported separately rather than subtracted from the totals. The finding
    is real - the stylesheet does block rendering - and hiding it would make
    the run quieter without making the site better. What the split buys is
    the next question a person actually asks: which of these can I fix?
    """
    counts: dict = {}
    for issue in result.issues():
        if getattr(issue, "owner", ""):
            counts[issue.owner] = counts.get(issue.owner, 0) + 1
    return counts


def cmd_ignore(args) -> int:
    """Write one dismissal, with its reason, into the project's ignore file.

    The reason is required. A fingerprint is a one-way hash, so the note is
    the only thing that will ever tell the next reader - or the next audit's
    summary - what was hidden and on what grounds.
    """
    import re

    value = (args.fingerprint or "").strip()
    reason = " ".join((args.reason or "").split())
    if not re.fullmatch(r"[0-9a-f]{16}", value):
        print("ignore needs a 16-character fingerprint from `audit --json`",
              file=sys.stderr)
        return EXIT_ERROR
    if not reason:
        print("ignore needs a reason: --reason \"why this is not a problem\"",
              file=sys.stderr)
        return EXIT_ERROR
    root = Path(args.root or ".")
    if not root.exists():
        print(f"no such folder: {root}", file=sys.stderr)
        return EXIT_ERROR
    path = suppression.add_fingerprint_to_ignore_file(str(root), value, reason)
    print(f"dismissed {value} in {path}: {reason}")
    return EXIT_OK


def cmd_login(args) -> int:
    """Sign in to a site by hand, so a run can read what is behind the login.

    The whole command is a browser window: it opens the address, the person
    signs in the way they always do - including 2FA and SSO, which work here
    because this really is a browser - and what the site gives that browser
    is kept for the next run. This tool never sees a credential.

    `--forget` and `--list` are the other half of that bargain. Something
    that quietly keeps a way into somebody's account and offers no way to see
    or remove it is not a tool anyone should install.
    """
    import site_session

    if getattr(args, "list", False):
        hosts = site_session.known_hosts()
        if not hosts:
            print("no stored sessions")
            return EXIT_OK
        for host in hosts:
            print(host)
        return EXIT_OK

    target = (getattr(args, "url", "") or "").strip()
    host = site_session.host_of(target)
    if getattr(args, "forget", False):
        if not target:
            removed = site_session.forget_all()
            print(f"forgot {removed} session(s)")
            return EXIT_OK
        # `--list` prints old profiles as `legacy:<name>`, and that name is
        # not a URL and never resolves to one. It is still what a person
        # reads before deciding what to remove, so it is accepted verbatim.
        if target.startswith("legacy:"):
            print(f"forgot the session for {target}"
                  if site_session.forget(target)
                  else f"no stored session for {target}")
            return EXIT_OK
        if not host:
            print("forget needs a valid site URL", file=sys.stderr)
            return EXIT_ERROR
        print(f"forgot the session for {host}" if site_session.forget(host)
              else f"no stored session for {host}")
        return EXIT_OK

    if not host:
        print("login needs a URL: xanalyze login https://example.com/admin",
              file=sys.stderr)
        return EXIT_ERROR

    try:
        from PySide6.QtWidgets import QApplication

        from ui.site_sign_in import SiteSignInDialog
    except Exception as exc:  # noqa: BLE001 - a build without Qt says so
        print(f"signing in needs the desktop components: {exc}",
              file=sys.stderr)
        # `EXIT_ERROR`, not 1: 1 means "something was found" everywhere else
        # in this CLI, and a build with no Qt in it has found nothing.
        return EXIT_ERROR

    address = target if "://" in target else f"https://{target}"
    app = QApplication.instance() or QApplication([])
    from i18n.translations import report_language

    dialog = SiteSignInDialog(address, lang=report_language(
        getattr(args, "language", "")))
    dialog.exec()
    if not dialog.saved:
        print("nothing saved", file=sys.stderr)
        return EXIT_ERROR
    # The count and the host, and nothing else. A terminal keeps scrollback
    # and scrollback gets pasted into issues.
    print(f"session stored for {host}; runs against that host will use it. "
          f"Remove it with: xanalyze login --forget {host}")
    del app
    return EXIT_OK


def cmd_logs(args) -> int:
    """The app's own log, for whoever has to debug a run that already ended.

    Reading, not tailing: a scan writes in bursts and finishes, and the
    question afterwards is always "what did that run do", not "what is
    happening now".
    """
    import applog

    if getattr(args, "logs_command", "") == "path":
        print(applog.log_dir())
        return EXIT_OK

    if getattr(args, "logs_command", "") == "clear":
        removed = 0
        for path in sorted(applog.log_dir().glob(f"{applog.APP_NAME}-*.log")):
            try:
                path.unlink()
                removed += 1
            except OSError as exc:
                print(f"# {path.name}: {exc}", file=sys.stderr)
        print(f"removed {removed} file(s)")
        return EXIT_OK

    if getattr(args, "logs_command", "") == "clean":
        result = applog.clean()
        print(f"expired {result['removed_expired']}, "
              f"over budget {result['removed_oversize']}, "
              f"kept {result['kept']}")
        return EXIT_OK

    summary = applog.summary()
    if args.json:
        print(json.dumps(
            {"summary": summary,
             "records": applog.read_records(limit=args.limit, level=args.level,
                                            contains=args.contains, run=args.run)},
            ensure_ascii=False, indent=2, default=str))
        return EXIT_OK

    megabytes = summary["bytes"] / (1024 * 1024)
    print(f"# {summary['directory']}  "
          f"{len(summary['files'])} file(s), {megabytes:.2f} MB, "
          f"level {summary['level']}, kept {summary['retention_days']} days")
    records = applog.read_records(limit=args.limit, level=args.level,
                                  contains=args.contains, run=args.run)
    if not records:
        print("# nothing logged yet - run a scan, or set XANALYZE_LOG_LEVEL=debug")
        return EXIT_OK
    # Oldest first on screen: a log reads forwards even though it is
    # collected backwards.
    for record in reversed(records):
        print(applog.format_line(record))
    return EXIT_OK


def _json_default(value):
    """Serialise the dataclasses a finding's `details` can carry.

    `details` is a free-form dict that rules and passes fill in, and one of
    them puts a whole object there: `audit.repo_facts.blame_issues` writes
    `details["arrived"] = Arrival(...)` so the window and the report can read
    `arrival.summary` and `arrival.assistant` by attribute. `json.dumps` has
    no answer for that, and `audit --json` died with "Object of type Arrival
    is not JSON serializable" the moment a repo finding was blamed.

    It went unseen because repo mode had no findings to blame: `.tsx` was
    skipped before any rule ran (`P-19`), so the only repository this was
    tried on came back empty. Handled here rather than by flattening
    `Arrival` into a dict at the source, because the attribute access is what
    every other consumer is written against.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _reaudit(args, target: str, previous):
    """Run the same audit again over the same files, after correcting them."""
    import audit

    if previous.mode == "file":
        return audit.analyze_page_file(
            target, within=getattr(args, "within", None) or "")

    files = scan_repo(target, _build_scan_config(args, target=target))
    return audit.analyze_files(files, target)


def _announce_suppressed(account: dict) -> None:
    """Say how many findings the ignore lists hid, and on whose word.

    A dismissed finding is a decision, and a report that drops it in silence
    reads exactly like a clean one. The reasons are the notes written next
    to the entries; a dismissal with no note is counted as such, because
    "nobody said why" is itself worth seeing.
    """
    hidden = (account or {}).get("hidden", 0)
    if not hidden:
        return
    levels = ", ".join(f"{count} by {level.rstrip('s')}"
                       for level, count in sorted(account["by_level"].items()))
    reasons = sorted({d["reason"] for d in account.get("dismissed", []) if d["reason"]})
    unexplained = sum(1 for d in account.get("dismissed", []) if not d["reason"])
    because = ""
    if reasons:
        because = "; reasons: " + " | ".join(reasons[:5])
    if unexplained:
        because += f"; {unexplained} dismissed with no reason written"
    progress.notice(
        "audit",
        f"{hidden} finding(s) hidden by the ignore lists ({levels}){because}; "
        f"add --no-ignore to see them",
        human=f"# {hidden} finding(s) hidden by the ignore lists ({levels})"
              f"{because}; add --no-ignore to see them",
        suppressed=hidden)


def _announce_auth_walls(result, session_host: str = "") -> None:
    """Say if what was audited was the door rather than the site.

    Printed before anything else about the findings, because it changes what
    they mean: three findings on a login form are not three findings on the
    application behind it, and the summary underneath cannot say so on its
    own. Silent when nothing was walled, which is nearly always.
    """
    report = getattr(result, "auth", None)
    if report is None or not report.blocked:
        return
    for signal, walls in report.by_signal().items():
        addresses = ", ".join(wall.url for wall in walls[:3])
        if len(walls) > 3:
            addresses += f", +{len(walls) - 3}"
        detail = walls[0].detail
        progress.notice(
            "authwall",
            f"{len(walls)} address(es) answered with a login wall "
            f"({signal}: {detail}): {addresses}",
            human=f"# [authwall] {len(walls)} address(es) answered with a "
                  f"login wall ({signal}: {detail}): {addresses}",
            signal=signal, detail=detail, addresses=len(walls))
    if report.whole_site:
        progress.notice(
            "authwall",
            "every page this run read was a login wall, so nothing behind it "
            "was audited. Sign in first, or point the run at a page that is "
            "public.",
            human="# [authwall] every page this run read was a login wall, "
                  "so nothing behind it was audited. Sign in first, or point "
                  "the run at a page that is public.",
            whole_site=True)
    # The case worth naming separately: this run *was* signed in and still
    # met a door. That is an expired session, and reporting it as "the site
    # has a login" would send somebody to sign in again without saying why
    # the last sign-in stopped counting.
    #
    # Only when the session was actually *used*. A run given `--no-session`
    # is a stranger by request, and telling that run its session expired is
    # advice about a thing it deliberately did not do - which is how a
    # correct message becomes a wrong one.
    if session_host:
        progress.notice(
            "session",
            f"the stored session for {session_host} did not get past the "
            f"login - it has most likely expired. Sign in again with: "
            f"xanalyze login {session_host}",
            human=f"# [session] the stored session for {session_host} did "
                  f"not get past the login - it has most likely expired. "
                  f"Sign in again with: xanalyze login {session_host}",
            host=session_host, expired=True)


def _apply_fixes(result, args, lang: str):
    """Write back what the audit already knows how to correct.

    Returns a small record of what happened, so `--report` and the JSON output
    can say it rather than the user having to diff their own files.

    The order is deliberate. Corrections that need no decision go in first and
    alone; the ones that encode a judgement are only written when `--ai` was
    asked for, and even then a value the model declined to invent is left
    undone rather than filled with something plausible.
    """
    from audit import fix_ai, fixer

    ready, pending, skipped = fixer.plan_fixes(result.documents)

    if pending:
        # The page's own language is in the page. Reading it beats asking a
        # model, and beats the rule's default, which is a guess.
        page_text = _document_text(result)
        filled, pending = fix_ai.fill_locally(pending, page_text)
        ready += filled

    ai_written = []
    if pending and getattr(args, "ai", False):
        name, provider = _provider_for(args)
        print(f"# writing the remaining corrections with {name}", file=sys.stderr)
        filled, pending = fix_ai.describe(pending, _document_text(result),
                                          provider, lang)
        ready += filled
        ai_written = [p.rule_id for p in filled]

    outcome = fixer.apply_fixes(ready)
    outcome.skipped.extend(skipped)
    for plan in pending:
        outcome.skipped.append(fixer.SkippedFix(
            plan.rule_id, plan.path, plan.line, plan.needs_input))

    print(f"# fixed {len(outcome.applied)} in {len(outcome.files_changed)} file(s); "
          f"{len(outcome.skipped)} left alone", file=sys.stderr)
    if outcome.backups:
        print(f"# backups: {', '.join(outcome.backups)} "
              f"(restore with `cli.py undo`)", file=sys.stderr)
    for error in outcome.errors:
        print(f"# {error}", file=sys.stderr)
    outcome.ai_written = ai_written
    return outcome


def _document_text(result) -> str:
    """The page's own words, for anything that has to read it."""
    import re as _re
    parts = []
    for document in result.documents:
        path = document.source
        if path.startswith(("http://", "https://")):
            continue
        try:
            with open(path, encoding="utf-8", errors="surrogateescape") as handle:
                markup = handle.read()
        except OSError:
            continue
        parts.append(_re.sub(r"<[^>]+>", " ", markup))
    return " ".join(parts)


def cmd_undo(args) -> int:
    """Put files back the way they were before the corrections went in."""
    import backups

    paths = []
    for target in args.paths:
        path = Path(target)
        if path.is_dir():
            paths += [str(p)[:-len(backups.SUFFIX)]
                      for p in path.rglob("*" + backups.SUFFIX)]
        elif str(path).endswith(backups.SUFFIX):
            paths.append(str(path)[:-len(backups.SUFFIX)])
        else:
            paths.append(str(path))

    if not paths:
        print("nothing to undo: no .bak copies found", file=sys.stderr)
        return EXIT_OK

    # Undo covers both writers - the character fixes from `fix` and the
    # corrections from `audit --fix` - because there is one backup rule and
    # therefore one way back.
    restored, problems = backups.restore(paths)
    for path in restored:
        print(f"restored {path}")
    for problem in problems:
        print(problem, file=sys.stderr)
    return EXIT_ERROR if problems and not restored else EXIT_OK


def cmd_update(args) -> int:
    """Self-update the CLI binary from the latest GitHub Release.

    Checks the configured GitHub repository for a newer version,
    downloads the platform-appropriate CLI asset, and replaces the
    running binary in place.  When running from source, prints the
    download link instead.
    """
    import updater
    return updater.do_update()


# ------------------------------------------------------------------ parser

def _add_sharepoint_flags(parser) -> None:
    """`--page-tree`, `--site-scope`, `--ootb-registry`."""
    from cli_impl.auditpass import PAGE_TREES

    parser.add_argument(
        "--page-tree", choices=PAGE_TREES, default=None,
        help="where the list of pages comes from: links (follow them from "
             "the target) or sharepoint (ask the site for every page in its "
             "libraries and subsites). Defaults to sharepoint on a "
             "*.sharepoint.com site, links elsewhere")
    parser.add_argument(
        "--site-scope", default=None, metavar="PATH",
        help="stay inside this path (/sites/x), compared without case; "
             "addresses outside it are counted, not read. Defaults to the "
             "site collection of a *.sharepoint.com target")
    parser.add_argument(
        "--ootb-registry", default=None, metavar="FILE",
        help="JSON of Microsoft's web part ids read from a live page "
             "({\"web_parts\": [{\"id\", \"name\"}], \"feature_tags\": []}), "
             "so the SharePoint zones recognise them")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xanalyze",
        description="Find and fix characters no keyboard produces (and optionally "
                    "flag AI-sounding copy) in web pages' source files. "
                    "Designed to run after an LLM coding agent.",
        epilog=EXIT_CODE_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--no-update-check", action="store_true", default=False,
        help="skip the automatic daily check for a newer version")
    parser.add_argument(
        "--progress", default=None, metavar="FORMAT",
        choices=("human", "jsonl", "jsonl=findings"),
        help="how the run reports itself on stderr: human (the default, "
             "unchanged) | jsonl (one JSON object per line, an event per "
             "step) | jsonl=findings (the same plus one object per finding). "
             "$XANALYZE_PROGRESS sets it for every run in a shell; this flag "
             "wins over it. See progress.py for the event list")
    parser.add_argument(
        "--version", action="version",
        version=f"xanalyze {config.APP_VERSION}")
    sub = parser.add_subparsers(dest="command", required=False)

    def common(p, with_paths=True):
        if with_paths:
            p.add_argument("paths", nargs="+", help="files or directories to process")
            p.add_argument("--ext", nargs="*", default=None,
                           help=f"extensions to scan (default: {' '.join(DEFAULT_EXTENSIONS)})")
            p.add_argument("--exclude", action="append", default=None,
                           help="extra gitignore-style exclude pattern (repeatable)")
            p.add_argument("--no-default-excludes", dest="use_default_excludes",
                           action="store_false", default=True,
                           help="don't skip node_modules/, dist/, .git/ etc.")
            p.add_argument("--max-files", type=int, default=5000)
            p.add_argument("--detector", default="none",
                           help="also run a content detector: offline (adds the "
                                "wording/cliche analysis to the character pass) | "
                                "llm-judge (ask a model, billed to whichever "
                                "account --provider names) | hybrid (offline "
                                "first, then a model checks and extends it) | "
                                "claude-llm-judge | xformat-llm-judge | "
                                "claude-code-llm-judge | none. "
                                "'agent-llm-judge' is an old name for "
                                "'offline'; for real agent judgment use the "
                                "'agent-scan' + 'agent-judge' workflow)")
            p.add_argument("--provider", default=None,
                           choices=["anthropic", "xformat", "claude-code"],
                           help="which account pays for --detector llm-judge; "
                                "the default is the same one `ai status` reports")
            p.add_argument("--no-unicode", action="store_true",
                           help="skip the non-keyboard character pass")
            p.add_argument("--scope", default="content",
                           choices=["content", "technical", "both"],
                           help="what to read: content (copy that ships to a "
                                "user: markup text plus injected strings) | "
                                "technical (comments and docstrings) | both")
        p.add_argument("--categories", default=None,
                       help="comma-separated: " + ",".join(unicode_rules.ALL_CATEGORIES))
        p.add_argument("--no-typography", action="store_true",
                       help="leave em dashes and curly quotes alone (keeps proper "
                            "Ukrainian/Italian typography)")
        p.add_argument("--no-ignore", action="store_true",
                       help="report everything, including findings suppressed by "
                            "settings or by a .xanalyze-ignore file")
        p.add_argument("--json", action="store_true", help="machine-readable output")
        p.add_argument("--check", action="store_true",
                       help="exit 1 when anything is found (for hooks and CI)")

    p_scan = sub.add_parser("scan", help="report findings without changing anything")
    common(p_scan)
    p_scan.add_argument("--incremental", action="store_true",
                        help="only scan files that changed since last scan "
                             "(uses cache)")
    p_scan.add_argument("--styled-report", default=None, metavar="PATH",
                        help="also write a branded, print-ready report for a "
                             "person to read: a .pdf or .html by suffix. "
                             "Different from --json/--check, which are for a "
                             "pipeline, not a reader")
    p_scan.add_argument("--report", metavar="PATH", default=None,
                        help="agent briefing for this scan (.md); written "
                             "into the run folder when not named")
    p_scan.add_argument("--language", default=None, help="uk | it | en; "
                        "language of the reports' own labels (default: the "
                        "language of the text, or English)")
    p_scan.add_argument("--no-hints", action="store_true",
                        help="do not print what this run leaves "
                             "undone (see cli_impl/prerun.py)")
    p_scan.set_defaults(func=cmd_scan)

    p_fix = sub.add_parser("fix", help="rewrite non-keyboard characters in place")
    common(p_fix)
    p_fix.add_argument("--dry-run", action="store_true", help="show what would change")
    p_fix.add_argument("--no-backup", action="store_true",
                       help="don't keep .bak copies (fine when the repo is in git)")
    p_fix.set_defaults(func=cmd_fix)

    # Renamed from `a11y` when the pass grew past accessibility into SEO,
    # performance and best practices — one pass over one parsed document, so
    # one command. `a11y` stays as a hidden alias: it is in people's hooks
    # and CI files already, and breaking those to rename a word would be a
    # cost paid by users for a change that benefits only the vocabulary.
    p_audit = sub.add_parser(
        "audit", aliases=["a11y"],
        help="audit a URL or a folder: accessibility, SEO, performance, best practices")
    p_audit.add_argument(
        "target",
        help="URL to crawl, a directory to scan, or one .html file to audit "
             "as a page (for a site built into a single self-contained file)")
    p_audit.add_argument("--url", action="store_true",
                         help="treat the target as a URL even without a scheme")
    p_audit.add_argument("--depth", type=int, default=0,
                         help="link depth to crawl; same-domain only (default 0: one page)")
    p_audit.add_argument("--max-pages", type=int, default=30)
    p_audit.add_argument("--max-files", type=int, default=5000)
    p_audit.add_argument("--render", choices=("never", "auto", "always"),
                         default=None,
                         help="hand pages to a real browser during the crawl, "
                              "so a client-rendered site is read rather than "
                              "diagnosed: auto renders only the pages whose "
                              "fetch came back an empty shell. Defaults to "
                              "auto (never with --no-browser)")
    p_audit.add_argument("--exclude", nargs="*", default=None)
    p_audit.add_argument("--no-default-excludes", dest="use_default_excludes",
                         action="store_false", default=True)
    p_audit.add_argument("--category", nargs="*", default=None,
                         choices=list(CATEGORIES),
                         help="report only these categories (default: all six)")
    p_audit.add_argument("--medium", default=None, choices=["web", "email"],
                         help="what these documents are for. Autodetected per "
                              "file from the markup (Outlook namespaces, merge "
                              "tags); set it when the deliverable is an email "
                              "that carries neither. On 'email' the browser-only "
                              "checks - canonical, Open Graph, structured data, "
                              "skip link, landmarks, WebP - are skipped, because "
                              "no mail client has them. Accessibility is not.")
    p_audit.add_argument("--confidence", default=None,
                         choices=list(CONFIDENCE_ORDER),
                         help="report only findings at least this certain: "
                              "'exact' keeps what the markup settles and drops "
                              "the editorial ones. The undecided are already "
                              "out - see --unsettled")
    p_audit.add_argument("--include-environment", action="store_true",
                         help="on a local address (localhost, *.local, a "
                              "private IP) also list what the server decides, "
                              "not the code: missing security headers, http "
                              "form actions, a development copy's noindex. "
                              "Out by default; the run says how many it left "
                              "out")
    p_audit.add_argument("--unsettled", action="store_true",
                         help="also list what could not be decided: an "
                              "engine's 'this element is on a background "
                              "image, check by hand'. Out by default - on one "
                              "page of python.org that was 312 of 348 contrast "
                              "findings, and a report two thirds made of 'we "
                              "do not know' is not a list anybody works through")
    p_audit.add_argument("--repo", default=None, metavar="PATH",
                         help="the checkout behind this site: needed by "
                              "--web-parts, and used to name the file "
                              "behind a finding")
    p_audit.add_argument("--web-parts", action="store_true",
                         help="with --repo pointing at an SPFx solution: audit only the web parts that repository ships, wherever they appear, and name the part behind each finding")
    p_audit.add_argument("--within", metavar="SELECTOR", default=None,
                         help="audit only this part of the page (a SharePoint "
                              "web part, an embedded widget). A generated "
                              "suffix on the class or id is matched past; a "
                              "selector that matches nothing is an error")
    p_audit.add_argument("--language", default=None, help="uk | it | en (output language)")
    p_audit.add_argument("--no-ignore", action="store_true",
                         help="report everything, including suppressed findings")
    p_audit.add_argument("--json", action="store_true", help="machine-readable output")
    p_audit.add_argument("--check", action="store_true",
                         help="exit 1 when a critical or serious issue is found")
    p_audit.add_argument("--ai", action="store_true",
                         help="also run the AI pass: whether alt text, link text "
                              "and headings actually describe what they point at "
                              "(costs tokens; see `ai status`)")
    p_audit.add_argument("--provider", default=None,
                         choices=["anthropic", "xformat", "claude-code"],
                         help="override the provider used by --ai")
    p_audit.add_argument("--fix", action="store_true",
                         help="write the corrections the audit already knows "
                              "back into the files, keeping a .bak copy of "
                              "each. Only the ones that need no decision; run "
                              "with --ai to have the rest written too")
    p_audit.add_argument("--report", default=None, metavar="PATH",
                         help="write a briefing an agent can act on: statistics, "
                              "a file map, every finding with its fix, what "
                              "changed since last time. .md or .json by suffix")
    p_audit.add_argument("--browser", action="store_true",
                         help="kept for compatibility: the browser pass "
                              "(axe-core, HTML_CodeSniffer, the keyboard/focus "
                              "state pass, load measurements) already runs by "
                              "default for a URL and for a single .html file")
    p_audit.add_argument("--no-browser", action="store_true",
                         help="skip the browser pass and render nothing: "
                              "audit only what the markup alone proves. Faster")
    p_audit.add_argument("--breakpoints", nargs="?", const="all", default=None,
                         metavar="NAMES",
                         help="audit each page at several "
                              "widths (desktop 1440, tablet 834, mobile 390, reflow 320) "
                              "instead of one. Bare, or a comma-separated "
                              "subset. A finding seen at several widths stays "
                              "one row and records where it was seen; one seen "
                              "at a single width says so - which is the point, "
                              "since a mobile menu is not in the DOM at all at "
                              "desktop width")
    p_audit.add_argument("--color-scheme", choices=("light", "dark"), default="light",
                         help="which prefers-color-scheme the browser pass shows "
                              "the page (default light). One scheme per run: "
                              "run twice to audit both themes")
    p_audit.add_argument("--site-controls", action="store_true",
                         help="also fetch robots.txt and same-origin sitemaps "
                              "declared in it. Opt-in: this makes requests "
                              "beyond the bounded page crawl")
    p_audit.add_argument("--styled-report", default=None, metavar="PATH",
                         help="also write a branded, print-ready report for a "
                              "person to read: a .pdf or .html by suffix. "
                              "Different from --report, which is a briefing "
                              "for an agent")
    p_audit.add_argument("--no-session", action="store_true",
                        help="ignore any stored sign-in for this host and "
                             "read the site the way a stranger sees it")
    _add_sharepoint_flags(p_audit)
    p_audit.add_argument("--project", default=None, metavar="NAME",
                         help="one project inside this folder, by its folder name "
                              "or a path: a directory of twenty SPFx solutions is "
                              "twenty deliverables, and auditing it as one root "
                              "reports them as one")
    p_audit.add_argument("--profile-defaults", action="store_true",
                         help="switch on what the detected stack asks for "
                              "(printed either way as `# [profile]` lines); "
                              "anything named on the command line wins")
    p_audit.add_argument("--no-hints", action="store_true",
                        help="do not print what this run leaves "
                             "undone (see cli_impl/prerun.py)")
    p_audit.set_defaults(func=cmd_audit)

    # `ai` groups everything that spends money or needs an account, so the
    # commands that never do (scan, fix, audit) stay usable with no setup.
    p_undo = sub.add_parser(
        "undo",
        help="put files back the way they were before --fix wrote to them")
    p_undo.add_argument("paths", nargs="+",
                        help="files or folders that were corrected")
    p_undo.set_defaults(func=cmd_undo)

    p_cache = sub.add_parser(
        "cache",
        help="manage the scan cache")
    cache_sub = p_cache.add_subparsers(dest="cache_command", required=True)
    
    p_cache_stats = cache_sub.add_parser(
        "stats", help="show cache statistics")
    p_cache_stats.set_defaults(func=cmd_cache)
    
    p_cache_clear = cache_sub.add_parser(
        "clear", help="clear the cache")
    p_cache_clear.set_defaults(func=cmd_cache)
    
    p_cache_path = cache_sub.add_parser(
        "path", help="show cache file path")
    p_cache_path.set_defaults(func=cmd_cache)
    
    p_cache.set_defaults(func=cmd_cache)

    p_compare = sub.add_parser(
        "compare",
        help="compare different detectors on the same files")
    common(p_compare)
    p_compare.set_defaults(func=cmd_compare)

    p_ai = sub.add_parser("ai", help="account and AI-backed operations")
    ai_sub = p_ai.add_subparsers(dest="ai_command", required=True)

    def with_provider(parser):
        parser.add_argument(
            "--provider", default=None,
            choices=["anthropic", "xformat", "claude-code"],
            help="override the configured provider for this command")

    p_ai_status = ai_sub.add_parser(
        "status", help="which account pays, and is it usable (costs nothing)")
    with_provider(p_ai_status)
    p_ai_status.set_defaults(func=cmd_ai_status)

    p_ai_login = ai_sub.add_parser("login", help="sign in to the xFormat subscription")
    with_provider(p_ai_login)
    p_ai_login.add_argument("--email", default=None)
    p_ai_login.set_defaults(func=cmd_ai_login)

    p_ai_logout = ai_sub.add_parser("logout", help="revoke the session and forget the tokens")
    with_provider(p_ai_logout)
    p_ai_logout.set_defaults(func=cmd_ai_logout)

    p_ai_apps = ai_sub.add_parser(
        "apps", help="which applications this xFormat account has let in")
    p_ai_apps.set_defaults(func=cmd_ai_apps)

    p_ai_grant = ai_sub.add_parser(
        "grant", help="allow this application to use the xFormat account")
    p_ai_grant.add_argument("app", nargs="?", default=None,
                            help="application slug; default is this one")
    p_ai_grant.set_defaults(func=cmd_ai_grant)

    p_ai_revoke = ai_sub.add_parser(
        "revoke", help="take that permission back")
    p_ai_revoke.add_argument("app", nargs="?", default=None)
    p_ai_revoke.set_defaults(func=cmd_ai_revoke)

    p_ai_rewrite = ai_sub.add_parser(
        "rewrite", help="rewrite a passage through the configured provider")
    with_provider(p_ai_rewrite)
    p_ai_rewrite.add_argument("text", nargs="?", default=None,
                              help="the passage; omitted means read stdin")
    p_ai_rewrite.add_argument("--language", default=None, help="uk | it | en")
    p_ai_rewrite.add_argument("--split", action="store_true",
                              help="treat blank-line-separated blocks as separate "
                                   "passages and rewrite them in one batched call")
    p_ai_rewrite.add_argument("--quiet", action="store_true",
                              help="print only the rewrite")
    p_ai_rewrite.set_defaults(func=cmd_ai_rewrite)

    p_fullscan = sub.add_parser(
        "fullscan",
        help="full scan: AI patterns + accessibility audit + reports for agent")
    p_fullscan.add_argument(
        "target",
        help="URL to crawl, a directory to scan, or one .html file")
    p_fullscan.add_argument("--url", action="store_true",
                            help="treat target as URL even without scheme")
    p_fullscan.add_argument("--depth", type=int, default=1,
                            help="crawl depth for URLs (default 1: target + direct links)")
    p_fullscan.add_argument("--max-pages", type=int, default=30,
                            help="max pages to crawl (default 30, 0=unlimited)")
    p_fullscan.add_argument("--max-files", type=int, default=5000,
                            help="max files to scan (default 5000)")
    p_fullscan.add_argument("--ext", nargs="*", default=None,
                            help="file extensions to scan")
    p_fullscan.add_argument("--exclude", action="append", default=None,
                            help="additional gitignore patterns to exclude")
    p_fullscan.add_argument("--no-default-excludes", action="store_true",
                            help="don't skip node_modules/, dist/, .git/ etc")
    # Only meaningful alongside a URL target: a repo scan already reads its
    # own files directly, and has nothing to cross-reference against. A site
    # given without --repo scans exactly as it always did - this is additive,
    # not a mode switch, because a live site with no matching checkout is the
    # ordinary case, not the exception.
    p_fullscan.add_argument("--repo", default=None, metavar="PATH",
                            help="local checkout behind this URL, if any: AI-"
                                 "pattern findings that match a passage in it "
                                 "get the file and line to fix, not just the "
                                 "page")
    # Off by default: a repo's dev server may already be running in another
    # terminal, and starting a second one on a different port is a confusing
    # outcome, not a helpful one. A repo scanned without this flag is scanned
    # statically, exactly as it always has been - this is additive, not a
    # mode switch.
    p_fullscan.add_argument("--devserver", action="store_true",
                            help="detect and start a repo's own dev server "
                                 "(package.json, manage.py, Gemfile+bin/rails) "
                                 "and scan the rendered site instead of the "
                                 "source; already have one running? pass "
                                 "--url http://localhost:PORT instead")
    p_fullscan.add_argument("--start-command", default=None, metavar="CMD",
                            help="override the detected dev server start "
                                 "command, run without a shell (e.g. "
                                 "--start-command 'npm run dev:custom')")
    p_fullscan.add_argument("--dev-server-port", type=int, default=None,
                            help="port to expect, when it can't be read "
                                 "from the server's own output "
                                 "(Django/Rails; Node servers announce "
                                 "their own)")
    p_fullscan.add_argument("--yes", action="store_true",
                            help="install missing dev server dependencies "
                                 "without asking")
    # `ai` first, because it is the word people reach for and it was the one
    # the help did not mention: the list named `llm-judge`, a backend name,
    # and left the natural request undiscoverable even though it has always
    # worked. `ai`, `judge` and `llm-judge` all mean the same thing - ask a
    # model, billed to whichever account is configured (see
    # `detectors/judges.py`); the concrete judge is printed when the run
    # starts, so the answer to "whose account paid" is in the log.
    p_fullscan.add_argument("--detector", default="offline",
                            help="how to read for AI patterns: offline "
                                 "(default, free), ai (ask a model; also "
                                 "spelled llm-judge), hybrid (both), embedding")
    # Which model, and how hard it thinks. Both only matter when `--detector`
    # asks for a model at all; both default to whatever the account is
    # configured for, so naming them here is an override rather than a
    # requirement. `sonnet` at `low` effort is enough for this job - the pass
    # classifies short passages against a fixed rubric - and is what the
    # settings should hold for a route that runs over every block on a site.
    p_fullscan.add_argument("--model", default=None,
                            help="model for the AI pass, e.g. sonnet, opus "
                                 "(default: whatever the account is set to)")
    p_fullscan.add_argument("--effort", default=None,
                            choices=["low", "medium", "high"],
                            help="how hard the AI pass thinks (default: low "
                                 "for the API judge, the session's own "
                                 "setting for Claude Code)")
    # A cached wrong answer must not be un-fixable, and a rubric change that
    # the prompt hash somehow did not catch must have a way out.
    p_fullscan.add_argument("--no-judgment-cache", action="store_true",
                            help="re-ask the model about passages it has "
                                 "already judged (slower, and the only way to "
                                 "get a fresh opinion)")
    p_fullscan.add_argument("--scope", default="both",
                            choices=["content", "technical", "both"],
                            help="what to read for AI patterns (default: both)")
    p_fullscan.add_argument("--no-typography", action="store_true",
                            help="leave em dashes and curly quotes alone")
    p_fullscan.add_argument("--styled-report", default=None, metavar="PATH",
                            help="branded PDF/HTML report for a person")
    p_fullscan.add_argument("--report", default=None, metavar="PATH",
                            help="agent briefing: .md or .json by suffix")
    p_fullscan.add_argument("--check", action="store_true",
                            help="exit 1 when critical/serious issues found")
    p_fullscan.add_argument("--medium", default=None, choices=["web", "email"],
                            help="what these documents are for (see "
                                 "`audit --medium`)")
    p_fullscan.add_argument("--confidence", default=None,
                            choices=list(CONFIDENCE_ORDER),
                            help="report only findings at least this certain "
                                 "(see `audit --confidence`)")
    p_fullscan.add_argument("--incremental", action="store_true",
                            help="skip files unchanged since the last scan "
                                 "(see `scan --incremental`)")
    p_fullscan.add_argument("--include-environment", action="store_true",
                            help="on a local address also list what the "
                                 "server decides, not the code (see `audit "
                                 "--include-environment`)")
    p_fullscan.add_argument("--unsettled", action="store_true",
                            help="also list what could not be decided, even "
                                 "in the browser (see `audit --unsettled`)")
    p_fullscan.add_argument("--web-parts", action="store_true",
                         help="with --repo pointing at an SPFx solution: audit only the web parts that repository ships, wherever they appear, and name the part behind each finding")
    p_fullscan.add_argument("--within", metavar="SELECTOR", default=None,
                            help="scan only this part of each page (see "
                                 "`audit --within`)")
    p_fullscan.add_argument("--language", default=None,
                            help="uk | it | en; language of reports (auto-detected if omitted)")
    p_fullscan.add_argument("--breakpoints", nargs="?", const="all", default="desktop",
                            metavar="NAMES",
                            help="responsive breakpoints for browser audit: "
                                 "desktop (default), all, tablet, mobile, reflow, "
                                 "or comma-separated subset (e.g. desktop,mobile)")
    p_fullscan.add_argument("--color-scheme", choices=("light", "dark"), default="light",
                         help="which prefers-color-scheme the browser pass shows "
                              "the page (default light). One scheme per run: "
                              "run twice to audit both themes")
    p_fullscan.add_argument("--site-controls", action="store_true",
                           help="also fetch robots.txt and same-origin sitemaps "
                                "declared in it during a URL audit")
    p_fullscan.add_argument("--no-browser", action="store_true",
                            help="skip browser rendering and responsive audit "
                                 "(faster, but misses JS-rendered content)")
    p_fullscan.add_argument("--agent", action="store_true",
                            help="run offline scan and output candidate blocks "
                                 "for agent to judge with its own LLM "
                                 "(no API key needed)")
    p_fullscan.add_argument("--json", action="store_true",
                            help="machine-readable JSON output for agent")
    p_fullscan.add_argument("--no-session", action="store_true",
                        help="ignore any stored sign-in for this host and "
                             "read the site the way a stranger sees it")
    p_fullscan.add_argument("--project", default=None, metavar="NAME",
                        help="one project inside this folder, by its folder name "
                             "or a path: a directory of twenty SPFx solutions is "
                             "twenty deliverables, and auditing it as one root "
                             "reports them as one")
    p_fullscan.add_argument("--profile-defaults", action="store_true",
                        help="switch on what the detected stack asks for "
                             "(printed either way as `# [profile]` lines); "
                             "anything named on the command line wins")
    p_fullscan.add_argument("--no-hints", action="store_true",
                        help="do not print what this run leaves "
                             "undone (see cli_impl/prerun.py)")
    _add_sharepoint_flags(p_fullscan)
    p_fullscan.set_defaults(func=cmd_fullscan)

    for performance_parser in (p_audit, p_fullscan):
        performance_parser.add_argument("--performance-repeats", type=int, choices=range(1, 11), default=1,
                                        help="fresh performance navigations per page (1-10); report dispersion")
        performance_parser.add_argument("--performance-fresh", action="store_true",
                                        help="bypass stored browser results for fresh lab measurements")
        performance_parser.add_argument("--performance-settle-ms", type=int, default=2500,
                                        help="foreground observation after load, in milliseconds")
        performance_parser.add_argument("--performance-scenario", metavar="JSON",
                                        help="opt-in file of native clicks/keys on explicit CSS selectors")
        performance_parser.add_argument("--lighthouse", action="store_true",
                                        help="also run an installed Lighthouse CLI as a separate lab source")
        performance_parser.add_argument("--lighthouse-profile", choices=("desktop", "mobile"), default="mobile")
        performance_parser.add_argument("--crux", action="store_true",
                                        help="query Google CrUX for this public URL; uses CRUX_API_KEY")
        performance_parser.add_argument("--crux-scope", choices=("url", "origin"), default="url")
        performance_parser.add_argument("--crux-form-factor", choices=("all", "PHONE", "TABLET", "DESKTOP"), default="all")

    # `runs` / `resume` / `pause`: a long scan that stops must not be a scan
    # that is lost. Registered from their own module because they are about
    # the run rather than about the target.
    from cli_impl.runcmds import add_run_parsers
    add_run_parsers(sub)

    p_logs = sub.add_parser(
        "logs",
        help="show the app's own log (what a run actually did)")
    p_logs.add_argument("--limit", type=int, default=200,
                        help="how many records, newest first (default 200)")
    p_logs.add_argument("--level", default="",
                        choices=["", "debug", "info", "warning", "error"],
                        help="this level and worse")
    p_logs.add_argument("--contains", default="", help="substring filter")
    p_logs.add_argument("--run", default="", help="only this run id")
    p_logs.add_argument("--json", action="store_true")
    logs_sub = p_logs.add_subparsers(dest="logs_command")
    logs_sub.add_parser("path", help="print the log directory").set_defaults(func=cmd_logs)
    logs_sub.add_parser("clean", help="apply the retention limits now").set_defaults(func=cmd_logs)
    logs_sub.add_parser("clear", help="delete every log file").set_defaults(func=cmd_logs)
    p_logs.set_defaults(func=cmd_logs)

    p_login = sub.add_parser(
        "login",
        help="sign in to a site by hand, so a run can read what is behind it")
    p_login.add_argument("url", nargs="?", default="",
                         help="the address to sign in to")
    p_login.add_argument("--forget", action="store_true",
                         help="remove the stored session for this host "
                              "(or every host, with no URL)")
    p_login.add_argument("--list", action="store_true",
                         help="list the hosts that have a stored session")
    p_login.add_argument("--language", default="",
                         help="interface language for the sign-in window")
    p_login.set_defaults(func=cmd_login)

    p_ignore = sub.add_parser(
        "ignore",
        help="dismiss one finding as a false positive, with the reason, in "
             ".xanalyze-ignore")
    p_ignore.add_argument("fingerprint",
                          help="the finding's `fingerprint`, from `audit --json`")
    p_ignore.add_argument("--reason", required=True,
                          help="why it is not a problem; kept next to the entry")
    p_ignore.add_argument("--root", default=".",
                          help="the project folder whose .xanalyze-ignore to "
                               "write (default: the current folder)")
    p_ignore.set_defaults(func=cmd_ignore)

    p_update = sub.add_parser(
        "update",
        help="self-update the CLI binary from the latest GitHub Release")
    p_update.set_defaults(func=cmd_update)

    p_uninstall = sub.add_parser(
        "uninstall",
        help="remove XAnalyze from this machine (command, app, settings, keychain)")
    p_uninstall.add_argument("--yes", action="store_true", default=False,
                             help="remove without asking for confirmation")
    p_uninstall.add_argument("--dry-run", action="store_true", default=False,
                             help="only list what would be removed")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_clean = sub.add_parser("clean", help="filter text from stdin to stdout")
    common(p_clean, with_paths=False)
    p_clean.add_argument("--language", default=None, choices=["uk", "it", "en"],
                         help="override language detection")
    p_clean.set_defaults(func=cmd_clean)

    p_agent_scan = sub.add_parser(
        "agent-scan",
        help="offline scan → candidate blocks as JSON for agent to judge")
    common(p_agent_scan)
    p_agent_scan.add_argument(
        "--threshold", type=float, default=0.25,
        help="minimum offline score to include as candidate (default: 0.25)")
    p_agent_scan.add_argument(
        "--full", action="store_true",
        help="hybrid mode: also output all blocks for agent to read "
             "independently (agent judges candidates AND reads raw content)")
    p_agent_scan.set_defaults(func=cmd_agent_scan)

    p_agent_judge = sub.add_parser(
        "agent-judge",
        help="merge agent's LLM judgments with offline scan → final report")
    common(p_agent_judge)
    p_agent_judge.add_argument(
        "--judgments", default=None, metavar="PATH",
        help="JSON file with agent's judgments (default: read stdin)")
    p_agent_judge.add_argument(
        "--hybrid", action="store_true",
        help="hybrid merge: input contains both judgments and agent_findings")
    p_agent_judge.set_defaults(func=cmd_agent_judge)

    # The global flags again, on every subcommand. `xanalyze fullscan X
    # --no-update-check` is what people type - the flag reads as belonging to
    # the command, not to the program - and argparse answered it with
    # "unrecognized arguments", which is a wrong answer to a correct request.
    # `--progress` is here for the same reason and one more: an agent writes
    # `xanalyze fullscan URL --progress jsonl`, never the other order.
    #
    # `default=SUPPRESS` is what makes the two copies co-operate rather than
    # fight: without it the subparser's own default would write `False` over
    # a `True` set before the subcommand, so putting the flag first would
    # stop working the moment it also worked last.
    _accept_global_flags_everywhere(sub)
    return parser


def _accept_global_flags_everywhere(subparsers, seen: set | None = None) -> None:
    """Add `--no-update-check` to every subcommand, at every depth.

    Recursive because two commands nest further (`cache stats`, `ai login`),
    and a flag accepted on `cache` but not on `cache stats` is the same
    surprise one level down.

    Deduplicated by object identity: an alias (`a11y` for `audit`) is the
    same parser under a second name, and adding one flag to it twice raises.
    """
    seen = seen if seen is not None else set()
    for subparser in subparsers.choices.values():
        if id(subparser) in seen:
            continue
        seen.add(id(subparser))
        subparser.add_argument(
            "--no-update-check", action="store_true",
            default=argparse.SUPPRESS,
            help="skip the automatic daily check for a newer version")
        subparser.add_argument(
            "--progress", default=argparse.SUPPRESS, metavar="FORMAT",
            choices=("human", "jsonl", "jsonl=findings"),
            help="human (default) | jsonl | jsonl=findings")
        for action in subparser._subparsers._group_actions if \
                subparser._subparsers else ():
            if hasattr(action, "choices") and action.choices:
                _accept_global_flags_everywhere(action, seen)


#: Options whose flag spelling is not their destination. Only the ones a
#: `run_profile` recipe can touch need to be here: `_explicit` exists to stop
#: a suggestion overwriting a deliberate choice, and a flag no recipe names
#: cannot be overwritten by one.
_FLAG_DESTS = {"no_default_excludes": "use_default_excludes"}


def _explicit_options(argv) -> set:
    """Every option the person actually typed, as argparse destinations.

    Not "differs from the default": `--breakpoints desktop` on a single file
    is a deliberate choice that happens to equal the default, and a profile
    that overrode it would be overriding exactly the case this set exists to
    protect.
    """
    named = set()
    for token in argv or ():
        if not isinstance(token, str) or not token.startswith("--"):
            continue
        name = token[2:].split("=", 1)[0].replace("-", "_")
        named.add(_FLAG_DESTS.get(name, name))
        named.add(name)
    return named


def _utf8_streams() -> None:
    """Read and write the standard streams as UTF-8 on Windows.

    Python on Windows encodes a redirected or piped stream with the ANSI
    code page (cp1252 on a western install), and the help text alone carries
    `→`: `cli.py --help > help.txt`, or any run under an agent reading the
    pipe, died with `UnicodeEncodeError` before printing a line. stdin is
    the same stream turned round: `clean` and `agent-judge` read an agent's
    UTF-8 from a pipe, and cp1252 turned every Cyrillic letter into two
    wrong ones. A console is already handled as UTF-16 by Python itself, so
    this changes nothing there. `errors="replace"` because a report line is
    worth more than the one character a terminal cannot show.
    """
    if sys.platform != "win32":
        return
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main(argv=None) -> int:
    _utf8_streams()
    args = build_parser().parse_args(argv)
    # Recorded before anything reads it, because argparse cannot be asked
    # afterwards which values came from the command line and which are its
    # own defaults.
    args._explicit = _explicit_options(sys.argv[1:] if argv is None else argv)

    # Before the first line of output of any kind, including the update
    # hint below: a stream that starts with prose an agent cannot parse is
    # not a stream it can read from the first byte.
    progress.configure(getattr(args, "progress", None))

    # Before anything can start Chromium: the colour scheme is a flag of its
    # browser process, read once. See `audit.driver.apply_color_scheme`.
    if getattr(args, "color_scheme", None) == "dark":
        from audit.driver import apply_color_scheme
        apply_color_scheme("dark")

    # No subcommand → launch interactive TUI
    if args.command is None:
        from tui.app import run_tui
        return run_tui()

    # Background update check (once per day, unless suppressed).
    # Skipped for the `update` command itself — that already checks.
    if not getattr(args, "no_update_check", False) and args.command != "update":
        try:
            import updater
            new = updater.check_for_update(quiet=True)
            if new:
                updater.print_update_hint(new)
        except Exception:  # noqa: BLE001
            pass  # never let the check break the real command

    # One record in, one out. The pair is what makes a log readable: a
    # start with no end is a crash, and the exit code is the answer a
    # person is usually looking for. `logs` itself is not logged - reading
    # the log would otherwise change it.
    import applog

    quiet = args.command == "logs"
    if not quiet:
        applog.set_run(f"{int(time.time())}-{os.getpid()}")
        applog.info("command.start", command=args.command,
                    target=getattr(args, "target", "") or "",
                    version=APP_VERSION)
    # The bracket around the whole command, so a reader of the stream never
    # has to decide whether a run that stopped producing events finished or
    # died: `run.end` carries the exit code, and its absence means the
    # process was killed.
    # `target` for the commands that take one, the first path for the ones
    # that take a list: `scan ./src` reported an empty target, which is the
    # one field a reader uses to tell two concurrent runs apart.
    named = getattr(args, "target", "") or ""
    if not named:
        paths = getattr(args, "paths", None) or []
        named = str(paths[0]) if paths else ""
    progress.run_start(args.command, str(named), APP_VERSION)
    started = time.monotonic()
    try:
        code = args.func(args)
        if not quiet:
            applog.info("command.done", command=args.command, exit=code,
                        seconds=round(time.monotonic() - started, 2))
        progress.run_end(code)
        return code
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        if not quiet:
            applog.error("command.failed", command=args.command,
                         error=f"{type(exc).__name__}: {exc}",
                         seconds=round(time.monotonic() - started, 2))
        progress.notice("error", f"{type(exc).__name__}: {exc}",
                        human=f"error: {exc}")
        progress.run_end(EXIT_ERROR)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
