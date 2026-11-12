"""The `fullscan` command: AI patterns + accessibility audit + reports.

Combines scan (AI patterns, characters) and audit (accessibility, SEO,
performance, best practices) into one command, saves the styled report
and the agent briefing, and prints one JSON document for agent consumption.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from collections import Counter
from pathlib import Path

import devserver
import duplicates
import progress
import suppression

import detectors  # noqa: F401 - registers the detectors
from detectors.factory import DetectorFactory

from cli_impl import EXIT_ERROR, EXIT_FINDINGS, EXIT_INCOMPLETE, EXIT_OK
from cli_impl.agentcmds import _agent_detection_rules
from cli_impl.auditpass import (
    _is_page_file, _run_browser_pass, looks_like_url,
    with_scheme,
)
from cli_impl.output import _public
from cli_impl import checkpoint, runfolder, runstate
from cli_impl.scanning import (
    _analyze, _build_scan_config, _collect_files, _ignore_root,
    _settings_for_ignore,
)

#: Offline spans under this score never reach the agent candidate list.
_AGENT_CANDIDATE_FLOOR = 0.25


def _severity_counts(issues) -> dict:
    """`{severity: n}` for the four levels, in the order the report prints them."""
    counts = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}
    for issue in issues:
        if issue.severity in counts:
            counts[issue.severity] += 1
    return counts


def _fullscan_report_paths(args, target: str):
    """Put this run's documents in this target's folder on the Desktop.

    A folder per target, a sub-folder per run: see `cli_impl.runfolder`. The
    documents used to be timestamped files dropped loose on the Desktop,
    which made a second run of the same site impossible to find next to the
    first - and the run history was keyed on those ever-changing file names,
    so no run was ever compared with any other.

    The folder is created either way. Naming both report paths says where the
    *reports* go, and it used to mean no run folder at all - which also meant
    no phase record and no checkpoints, so the one caller who had asked for
    control over their output was the one who could not resume. The reports
    now go exactly where they were asked for, and the run still has a folder
    to keep its state and its intermediate results in.
    """
    from cli_impl import runfolder

    named_styled = bool(getattr(args, "styled_report", None))
    named_report = bool(getattr(args, "report", None))
    folder = runfolder.prepare(target)
    if not named_styled:
        args.styled_report = str(folder.styled_report)
    if not named_report:
        args.report = str(folder.report)
    return folder


def _candidate(block, source_url: str, line: int, span) -> dict:
    """One candidate row as the agent pipeline consumes it."""
    return {
        "block_id": span.block_id,
        "file": source_url,
        "line": line,
        "text": block.text,
        # `null` when the passage is too short to read, and null rather
        # than "en": an agent told a two-word Italian button is English
        # judges it against English expectations. See `crawler._make_block`.
        "language": block.language_hint,
        "offline_score": round(span.score, 3),
        "offline_explanation": span.explanation,
    }


def _agent_candidates_from_blocks(blocks) -> list:
    """Candidates for a local repo: one per distinct passage.

    Same reasoning as the crawled-site version, and the same defect before
    it: `block_id` is a fresh uuid, so a project holding its own source and
    its build output handed the agent both copies of every string.
    """
    offline = DetectorFactory.create("offline", include_style=True)
    candidates = []
    for representative, occurrences in duplicates.distinct_blocks(blocks, exact_text=True):
        for span in offline.analyze_blocks([representative]):
            if span.score < _AGENT_CANDIDATE_FLOOR \
                    or (span.details or {}).get("error"):
                continue
            entry = _candidate(representative, representative.file_path,
                               representative.line_number, span)
            entry["places"] = [f"{b.file_path}:{b.line_number}"
                               for b in occurrences]
            entry["occurrences"] = len(occurrences)
            candidates.append(entry)
            break
    return candidates


def _agent_candidates_from_pages(pages) -> list:
    """Candidates for a crawled site: one per distinct passage.

    The agent pays for every candidate it is handed, whichever model it runs
    - that is the point of this path - so handing it the same header ten
    times is ten times the cost for one answer. It used to: the only guard
    was `block_id`, which is a fresh uuid per block, so it deduplicated
    nothing at all across pages. Measured on a ten-page site: 124 candidates,
    68 distinct, **45% repeats**.

    Each candidate now carries `places`, so the agent can see that a passage
    is site-wide - which is real context for judging a header - and
    `agent-judge` gives its verdict to every one of them.
    """
    offline = DetectorFactory.create("offline", include_style=True)
    blocks = [block for page in pages for block in page.blocks]
    candidates = []
    for representative, occurrences in duplicates.distinct_blocks(blocks, exact_text=True):
        for span in offline.analyze_blocks([representative]):
            if span.score < _AGENT_CANDIDATE_FLOOR \
                    or (span.details or {}).get("error"):
                continue
            entry = _candidate(representative, representative.page_url, 0, span)
            entry["places"] = [block.page_url for block in occurrences]
            entry["occurrences"] = len(occurrences)
            candidates.append(entry)
            break
    return candidates


def _content_passes(args) -> list:
    """The detectors a crawled page's text is read by, given `--detector`.

    Mirrors what `cli_impl.scanning._analyze` does for a folder, and it has to:
    the two are the same question asked of a page and of a file, and the moment
    they answer differently the flag means one thing on disk and another on the
    web - which is exactly what happened.

    Offline is always in the list, because it carries the character pass. When
    a judge was asked for, it is added rather than substituted: the offline
    engine finds the exact character defects a model does not, so replacing it
    would be a downgrade wearing an upgrade's name.
    """
    offline = DetectorFactory.create("offline", include_style=True)
    if args is not None:
        args._detector_unavailable = []
    name = getattr(args, "detector", None) if args is not None else None
    if not name or DetectorFactory.resolve(name) == "offline":
        return [offline]

    from .scanning import _create_detector

    try:
        judge = _create_detector(args)
    except Exception as exc:  # noqa: BLE001 - said out loud, not swallowed
        if args is not None:
            args._detector_unavailable.append({"engine": name, "status": "error", "reason": str(exc)})
        # Loud, and the run continues on the offline pass. A judge that cannot
        # be built (no account, an exhausted plan, a typo in a name) must not
        # cost the crawl that already happened - but it must never be silent
        # either, which is the whole defect this function exists to close.
        progress.notice(
            "warning",
            f"--detector {name} could not be used ({exc}); the offline "
            f"engine ran instead",
            human=f"# warning: --detector {name} could not be used ({exc}); "
                  f"the offline engine ran instead",
            about="detector", detector=name)
        return [offline]
    # The judge's own name, not the flag's. `ai` and `llm-judge` mean "ask a
    # model" without saying whose account pays, and which account it turned
    # out to be is the part worth printing - it is what the run will be
    # billed to.
    progress.stage("scan", "begin",
                   f"# [stage] AI patterns: {getattr(judge, 'name', name)}",
                   detector=getattr(judge, "name", name))
    return [offline, judge]


def _judge_distinct(groups, passes, args) -> dict:
    """Run the detectors over one block per distinct passage.

    Returns `{block_id: [span]}` keyed on the representative, so the caller
    can fan a verdict back out to every place the passage appears.

    A judged verdict is also remembered on disk between runs. That is not
    only about cost: this judge is **not deterministic** - two runs of one
    site with identical flags returned 6 findings and then 24 - and no route
    here exposes a temperature or a seed, so identical output cannot be
    requested from the model. It can only be remembered, which is what makes
    a repeat run reproducible.
    """
    import judgment_cache

    representatives = [rep for rep, _ in groups]
    spans_by_id: dict = {}
    for detector in passes:
        cache = _cache_for(detector, args)
        eligible = [b for b in representatives if getattr(detector, "includes_character_pass", False)
                    or getattr(b, "analysis_eligible", True)]
        todo = eligible
        if cache is not None:
            todo = []
            for block in eligible:
                stored = cache.get(block.text, block.language_hint)
                if stored is None:
                    todo.append(block)
                    continue
                spans_by_id.setdefault(block.block_id, []).extend(
                    judgment_cache.record_to_span(record, block)
                    for record in stored)
        fresh = _run_detector(detector, todo, talkative=cache is not None)
        for block in todo:
            produced = fresh.get(block.block_id, [])
            spans_by_id.setdefault(block.block_id, []).extend(produced)
            if cache is not None:
                cache.put(block.text,
                          [judgment_cache.span_to_record(s) for s in produced],
                          block.language_hint)
        if cache is not None:
            cache.save()
            note = cache.summary()
            if note:
                progress.notice("ai-patterns", note,
                                human=f"# [AI patterns] {note}")
    return spans_by_id


def _cache_for(detector, args):
    """The verdict cache for this detector, or None when it must not be used.

    None for the offline pass: it is deterministic and costs a tenth of a
    second, so a cache would add a disk round trip and a staleness risk to
    buy nothing. None for `--no-judgment-cache`, because a cached wrong
    answer must not be un-fixable.
    """
    import judgment_cache

    name = getattr(detector, "name", "")
    if not name or name == "offline" or getattr(args, "no_judgment_cache", False):
        return None
    from detectors.claude_llm_judge import _SYSTEM_PROMPT

    return judgment_cache.JudgmentCache(
        detector=name,
        model=str(getattr(detector, "model", "") or ""),
        effort=str(getattr(detector, "effort", "") or ""),
        prompt=_SYSTEM_PROMPT,
        exact_text=True,
    )


def _run_detector(detector, blocks, *, talkative: bool) -> dict:
    """One detector over `blocks`, batched, reporting progress by batch.

    By batch and not by page: deduplication is across the whole run, so the
    work stopped being per page and a "3/10 pages" counter would be counting
    something that is no longer happening.
    """
    if not blocks:
        return {}
    size = max(1, int(getattr(detector, "batch_size", len(blocks)) or len(blocks)))
    batches = (len(blocks) + size - 1) // size
    out: dict = {}
    for index in range(batches):
        chunk = blocks[index * size:(index + 1) * size]
        if talkative:
            progress.stage("scan", "progress",
                           f"# [AI patterns {index + 1}/{batches} batches] "
                           f"{len(chunk)} passage(s)",
                           batch=index + 1, batches=batches,
                           passages=len(chunk))
        for span in detector.analyze_blocks(chunk):
            out.setdefault(span.block_id, []).append(span)
    return out


def _repo_content_index(repo_path: str, args) -> dict:
    """Distinct content blocks under `repo_path`, keyed by passage identity.

    Built once per run, so a paragraph rendered on ten crawled pages is one
    lookup rather than ten. The key is `duplicates.block_identity` - the same
    normalise-and-mask identity a crawled page's own blocks are grouped by -
    so a passage matches whichever side it is asked from: the rendered page,
    or the template that produced it.

    A repo given without matching pages is not an error here: WordPress
    puts `<html lang>`, canonical links and most of `<head>` in `wp_head()`,
    not in a theme file, so the given checkout can be entirely genuine and
    still explain none of a particular finding. That is `--repo`'s honest
    answer for those, not a bug in this lookup.
    """
    scan_args = argparse.Namespace(
        paths=[repo_path],
        ext=None,
        exclude=None,
        use_default_excludes=True,
        max_files=getattr(args, "max_files", 5000) if args is not None else 5000,
        scope="content",
    )
    import repo_pairing

    # One implementation, shared with the window: two ways of building this
    # index is two answers to "which file wrote this sentence".
    return repo_pairing.content_index(_collect_files(scan_args.paths, scan_args))


def _note_weak_detector(args, blocks, stats_out) -> None:
    """Tell the person their detector is the weak one here, if it is.

    On stderr because that is where every other stage note goes, and into
    `stats_out` so the JSON carries it too: a caller reading the document
    rather than the terminal needs the same warning, and the window and the
    TUI have no stderr to read.
    """
    import detector_advice

    name = getattr(args, "detector", None) if args is not None else None
    note = detector_advice.weak_language_note(name or "offline", blocks)
    if not note:
        return
    progress.notice("warning", note, human=f"# WARNING: {note}",
                    about="detector")
    if stats_out is not None:
        stats_out["detector_note"] = note


def _content_findings_from_pages(pages, args=None, stats_out: dict | None = None) -> list:
    """The AI-patterns and typography pass for a crawled site.

    Local targets get this through the ordinary scan; a crawled page never
    was a file, so the detector runs over its text blocks here and the spans
    become the finding dicts the reports read. Without this, a website scan
    silently lost whole report sections a repo scan had.

    **`--detector` reaches this.** It did not, and that was the whole of the
    AI mode on the path most people use: this hardcoded the offline engine, so
    `fullscan https://site --detector llm-judge` crawled the site, said
    nothing, and ran the free heuristic. The flag was accepted, reported
    nowhere, and did nothing - the failure mode this project keeps finding,
    where a control looks like it works because nothing raises.

    The character pass stays offline whatever was asked for. It is exact and
    free, a model has nothing to add to "this is an en dash", and paying a
    judge to re-answer it would be a cost with no result.

    The same threshold as the repo scan, and this is not a detail. Without it
    this path appended *every* span the detector produced, scored or not: a
    real 192-page run reported 10,976 "AI text patterns" of which 10,946 were
    `low` - blocks that scored 0.00 and were listed anyway. They inflated the
    count the user reads, and they are most of why that run's artifacts came
    to 14 MB of JSON, 31 MB of HTML and a 117 MB PDF.

    Character findings are kept at any confidence, exactly as the repo scan
    keeps them: a wrong dash is a fact about the text, so a low score there
    means "a small defect", not "probably nothing". A style score below the
    threshold means the second thing, and saying it 10,946 times says nothing.

    **`args.repo`**, when given, adds `source_file`/`source_line` to a
    finding whose passage matches a block found under that path - the actual
    place to fix it, not just the page it renders on. This is additive: a
    site given without `--repo` behaves exactly as before, because most runs
    have no checkout to point at and are not made worse for lacking one.
    `stats_out`, when given, receives `{"repo_matched", "repo_total"}` over
    every distinct passage on the site, not only the ones that produced a
    finding - "how much of this site the given checkout explains" is a
    question worth an answer even when nothing was flagged.
    """
    from models import Confidence

    from .scanning import CHARACTER_SOURCE

    passes = _content_passes(args)
    blocks = [block for page in pages for block in page.blocks]
    # Deduplicated across the whole run, not within a page. A header and a
    # footer appear on every page, so the repetition worth removing is exactly
    # the one a single page cannot see: ten pages of a real site gave 573
    # blocks and 236 distinct passages, with a phone number read 26 times.
    #
    # Both detectors read the same list. A second list would be a second
    # answer to "what is distinct here", and the offline pass would keep
    # paying for repeats the judge had stopped paying for.
    groups = duplicates.distinct_blocks(blocks, exact_text=True)
    spans_by_id = _judge_distinct(groups, passes, args)
    if args is not None:
        args._detector_coverage = list(getattr(args, "_detector_unavailable", []))
        for detector in passes:
            failed = [span for spans in spans_by_id.values() for span in spans
                      if span.detector_name == detector.name and (span.details or {}).get("error")]
            args._detector_coverage.append({"engine": detector.name,
                "status": "error" if failed else "checked", "blocks": sum(
                    getattr(detector, "includes_character_pass", False) or getattr(rep, "analysis_eligible", True)
                    for rep, _ in groups),
                "style_skipped": sum(not getattr(rep, "analysis_eligible", True) for rep, _ in groups),
                "model": getattr(detector, "model", None), "version": getattr(detector, "version", None)})
    if stats_out is not None:
        from finding_contract import serialize_span
        scan_errors = [serialize_span(span, block)
            for block, _ in groups for span in spans_by_id.get(block.block_id, ())
            if (span.details or {}).get("error")]
        if scan_errors:
            stats_out["scan_errors"] = scan_errors

    # Said once per run, and said at all. The offline pass finds 36% of known
    # Italian AI passages where the embedding detector finds 100%, and until
    # now that lived only in a calibration report nobody runs - so an Italian
    # page got a third of the available answer and looked like a clean scan.
    # See `detector_advice`, which holds the measurement.
    _note_weak_detector(args, blocks, stats_out)

    repo_path = getattr(args, "repo", None) if args is not None else None
    repo_index = _repo_content_index(repo_path, args) if repo_path else None
    if repo_index is not None:
        from repo_pairing import pair_blocks
        pair_blocks(blocks, repo_index)
    if repo_index is not None and stats_out is not None:
        matched = sum(bool(representative.source_candidates) for representative, _occurrences in groups)
        stats_out["repo_matched"] = matched
        stats_out["repo_total"] = len(groups)
        for status in ("ambiguous", "inferred"):
            count = sum(rep.source_mapping == status for rep, _ in groups)
            if count:
                stats_out["repo_" + status] = count

    findings = []
    for representative, occurrences in groups:
        for span in spans_by_id.get(representative.block_id, ()):
            if (span.details or {}).get("error"):
                continue
            if span.confidence == Confidence.LOW \
                    and (span.details or {}).get("source") != CHARACTER_SOURCE:
                continue
            confidence = span.confidence
            if isinstance(confidence, Confidence):
                confidence = confidence.value
            # The passage that was judged, not the block it sat in. The
            # local scan has always sliced the span (`cli_impl/scanning.py`);
            # this path showed `block.text[:200]`, so a judge that returned
            # five findings for five sentences of one hero block produced
            # five rows with identical text and five different reasons - the
            # reader could not tell which sentence each reason was about.
            passage = representative.text[span.start:span.end] \
                or representative.text
            # One finding per occurrence. Reading once is about what is
            # *asked*; every place is still reported, because a fix has to
            # visit each page that carries the passage.
            for block in occurrences:
                from finding_contract import serialize_span
                finding = serialize_span(span, block)
                if not finding["text"]:
                    finding.update(text=passage, range=None, evidence_status="unknown")
                findings.append(finding)
    return findings


def _scan_local_target(target, args, lang, agent_mode):
    """Phase 1 for repos and loose files: the AI-patterns pass.

    Returns (scan_findings, scan_result, agent_candidates).
    """
    scan_args = argparse.Namespace(
        paths=[target],
        ext=args.ext,
        exclude=args.exclude,
        use_default_excludes=not getattr(args, "no_default_excludes", False),
        max_files=args.max_files,
        detector=args.detector,
        scope=args.scope,
        no_typography=getattr(args, "no_typography", False),
        no_ignore=False,
        no_unicode=False,
        categories=None,
        json=False,
        check=False,
        # The file-level cache the pre-commit case uses, keyed on
        # modification time and size. Off unless asked for, exactly as in
        # `scan`: a cached answer must be something the reader chose.
        incremental=bool(getattr(args, "incremental", False)),
        styled_report=None,
        language=lang,
    )

    scan_findings: list = []
    scan_result = None
    agent_candidates: list = []

    # What the walk read, not only what it found. `counts` counts files
    # among the *findings*, so without this a quiet repository cannot say
    # whether it read four thousand files or none - and `fullscan` was
    # dropping the diagnostic that `scan --json` has always carried.
    walked: list = []
    files = _collect_files(scan_args.paths, scan_args, diagnostics_out=walked)
    if not files:
        return scan_findings, {"findings": [], "counts": {"total": 0, "style": 0, "characters": 0},
                               "read": _read_diagnostics(walked)}, agent_candidates
    # Said out loud, not only in the JSON. Measured on this repository: the
    # walk stopped at the 5000-file limit with a third of the tree unopened,
    # `scan` prints that in one line, and `fullscan` printed nothing at all -
    # so the surface that writes the report was the quiet one.
    for root, walk in walked:
        if walk.truncated:
            progress.notice(
                "scan",
                f"{root}: stopped at the {walk.limit}-file limit - everything "
                f"past it was not examined. Raise it with --max-files.",
                human=f"# [scan] {root}: stopped at the {walk.limit}-file "
                      f"limit - everything past it was not examined. Raise it "
                      f"with --max-files.",
                root=str(root), limit=walk.limit, truncated=True)

    if agent_mode:
        # Agent mode: run offline scan, collect candidates for LLM judgment
        blocks = [b for f in files for b in f.blocks]
        agent_candidates = _agent_candidates_from_blocks(blocks)
        scan_result = {
            "findings": [],
            "counts": {"total": 0, "style": 0, "characters": 0},
            "agent_mode": True,
            "candidates_count": len(agent_candidates),
        }
    else:
        # The same file-level cache `scan --incremental` uses, and for the
        # same case: a repository of four thousand files where two changed.
        # Off unless asked for - a cached answer has to be something the
        # reader chose - and the number reused is printed, not assumed.
        cached_findings: list = []
        reused = 0
        to_read = files
        if getattr(scan_args, "incremental", False):
            from cli_impl.scanning import _split_unchanged, _store_unchanged

            to_read, cached_findings, reused = _split_unchanged(files, scan_args)
            progress.notice(
                "scan",
                f"incremental: {reused} file(s) unchanged since the last "
                f"scan, {len(to_read)} re-read",
                human=f"# [scan] incremental: {reused} file(s) unchanged "
                      f"since the last scan, {len(to_read)} re-read",
                reused=reused, reread=len(to_read))
        unjudged = []
        scan_findings, _ = _analyze(to_read, scan_args, unjudged_out=unjudged)
        if getattr(scan_args, "incremental", False):
            from cli_impl.scanning import _store_unchanged

            _store_unchanged(to_read, scan_findings, scan_args)
            scan_findings = scan_findings + cached_findings
        clean_findings = [_public(f) for f in scan_findings]
        scan_result = {
            "findings": clean_findings,
            "counts": {
                "total": len(clean_findings),
                "style": len([f for f in clean_findings if f.get("source") == "style"]),
                "characters": len([f for f in clean_findings if f.get("source") == "characters"]),
            },
            "read": _read_diagnostics(walked),
        }
        if unjudged:
            scan_result["errors"] = [{"engine": scan_args.detector, "unjudged_blocks": sum(unjudged)}]
        scan_result["detector_coverage"] = getattr(scan_args, "_detector_coverage", [])
        scan_result["cached_files"] = reused
    from audit.coverage import content_digest
    scan_result["read"] = _read_diagnostics(walked)
    scan_result["content_hashes"] = {f.path: content_digest(f.raw_text)
                                     for f in files if f.raw_text is not None}
    return scan_findings, scan_result, agent_candidates


def _read_diagnostics(walked) -> list:
    """The walk's own numbers, in the shape `scan --json` already prints.

    One shape rather than two: an agent that reads a `fullscan` result and
    an agent that reads a `scan` result are asking the same question - what
    did this run actually open - and a second spelling of the same answer is
    how the two drift.
    """
    return [
        {
            "root": root,
            "files_read": walk.files_read,
            "blocks_found": walk.blocks_found,
            "skipped_ignored": walk.skipped_ignored,
            "skipped_too_large": walk.skipped_too_large,
            "unreadable": walk.unreadable,
            "truncated": walk.truncated,
            "limit": walk.limit,
        }
        for root, walk in walked
    ]


class SharePointRefused(Exception):
    """The site's page tree said this sign-in cannot read it. Exit 2."""

    def __init__(self, message: str, reason: str):
        super().__init__(message)
        self.reason = reason


def _crawl_for_fullscan(target: str, args, no_browser: bool):
    """Crawl a URL for the fullscan pass; returns (pages, resolved target).

    A SharePoint Online target is read the way `audit` reads it, through the
    same functions: the plan (`plan_sharepoint`), the page tree and the site
    scope (`crawl_site`), and the refusal when the tree says the sign-in is
    missing or not enough (`SharePointRefused`). The plan, the tree and the
    walk are kept on `args` for the audit and the JSON summary.
    """
    from crawler import CrawlConfig, RENDER_ALWAYS, RENDER_NEVER
    from models import CrawlDiagnostics

    from cli_impl import auditpass

    if not target.startswith(("http://", "https://")):
        target = "https://" + target
    sp = auditpass.plan_sharepoint(target, args)
    auditpass.say_plan(sp)
    # Browser mode reads actual layout/text, including server-rendered pages
    # whose styles hide copy. A nonempty HTTP body is not visibility evidence.
    render_mode = RENDER_NEVER if no_browser else RENDER_ALWAYS
    config = CrawlConfig(max_depth=args.depth, max_pages=args.max_pages,
                         render_mode=render_mode)
    no_session = bool(getattr(args, "no_session", False))
    session_host = auditpass.apply_session(target, config,
                                           use_session=not no_session)
    # The same late check `audit` makes: a session that existed when the run
    # started but was not applied, or gave the fetcher nothing.
    message = auditpass.session_refusal(target, config, session_host,
                                        no_session)
    if message:
        raise SharePointRefused(message, "sign-in-required")
    # `--ootb-registry` was read before the run folder (`registry_refusal`).
    progress.stage(
        "crawl", "begin",
        f"# [stage crawl] depth={args.depth} "
        f"max_pages={args.max_pages or 'unlimited'} render={render_mode}",
        depth=args.depth, max_pages=args.max_pages or None,
        render=str(render_mode), target=target)

    crawled = 0

    def _crawl_progress(url: str, depth: int) -> None:
        nonlocal crawled
        crawled += 1
        limit = f"/{args.max_pages}" if args.max_pages else ""
        progress.page(crawled, args.max_pages or None, url, depth=depth,
                      human=f"# [crawl {crawled}{limit}] depth={depth} {url}")

    walk = CrawlDiagnostics()
    pages, tree = auditpass.crawl_site(
        target, config, progress_cb=_crawl_progress, session_host=session_host,
        within=getattr(args, "within", None) or "", page_tree=sp.page_tree,
        site_scope=sp.site_scope, walk=walk)
    refusal = auditpass.tree_refusal(tree, target)
    if refusal:
        raise SharePointRefused(refusal, tree.status)
    auditpass.say_tree(tree)
    args._sharepoint_run = sp
    args._page_tree = auditpass.page_tree_summary(
        tree, walk, sp.site_scope, sp.page_tree) if sp.sharepoint else None
    progress.stage("crawl", "end", f"# [crawl done] {len(pages)} page(s)",
                   pages=len(pages))
    return pages, target


def _warn_about_spa(pages) -> None:
    """Say so when client-rendered pages came back empty shells."""
    from crawler import EMPTY_JS_RENDERED

    spa_pages = [p for p in pages
                 if EMPTY_JS_RENDERED in (p.diagnostics.reasons or [])]
    rendered_pages = [p for p in pages
                      if "rendered" in (p.diagnostics.reasons or [])]
    if spa_pages and not rendered_pages:
        progress.notice(
            "spa",
            f"{len(spa_pages)} SPA page(s) detected but browser rendering "
            f"failed; pages may appear empty. Install PySide6 + QtWebEngine "
            f"for full support.",
            human=f"# WARNING: {len(spa_pages)} SPA page(s) detected but "
                  f"browser rendering failed.\n"
                  f"# Pages may appear empty. Install PySide6 + QtWebEngine "
                  f"for full support.",
            failed=len(spa_pages), rendered=0)
    elif spa_pages and rendered_pages:
        progress.notice(
            "spa",
            f"{len(rendered_pages)} page(s) rendered via browser, "
            f"{len(spa_pages)} failed.",
            human=f"# SPA: {len(rendered_pages)} page(s) rendered via "
                  f"browser, {len(spa_pages)} failed.",
            rendered=len(rendered_pages), failed=len(spa_pages))


def _audit_fullscan_target(is_url: bool, is_page_file: bool, target: str,
                           args, pages):
    """Phase 2: accessibility/SEO/performance over whichever shape came in.

    A repository the scanner could not read anything in still gets a result,
    and that is the point of the last branch. This used to answer `None`, and
    `None` travels: `_write_markdown_briefing` skips on it and
    `_styled_report_model` returns `None` on it, so **both** writers returned
    without a word. The run then exited 0, printed `total_findings: 0`, and
    wrote neither of the files it had been asked for.

    Reproduced on `~/Desktop/XAnalyze/contrast.html`, which is a directory of
    old run folders rather than the page its name suggests: `fullscan ...
    --report r.json` reported a clean target and left no `r.json` behind. An
    over-broad `--exclude`, an `--ext` that matches nothing, or a path with
    one wrong component all reach the same place. It is the founding defect
    of this project wearing a different hat - an empty result reported as a
    clean one - and it also breaks the contract `--report` makes with
    whatever runs next.

    An empty `AccessibilityResult` says the true thing instead: zero
    documents, zero findings, written down. The pass still walks the target
    for what belongs to the repository rather than to any file in it - a
    committed `.env` is a finding about a directory with no readable source
    in it too.
    """
    import audit

    if is_url:
        seen_images = [0]

        def _image_progress(url: str) -> None:
            # Every twenty-fifth, not every one: the point is a heartbeat
            # that says the stage is moving, and one line per image would
            # bury the crawl's own output on a site with a thousand of them.
            seen_images[0] += 1
            if seen_images[0] % 25 == 1:
                progress.notice("images", url,
                                human=f"# [images {seen_images[0]}] {url}",
                                n=seen_images[0], url=url)

        from cli import _served_by_sharepoint, _web_parts_for

        # Read once: the browser pass places its findings by the same parts.
        args._web_parts_found = _web_parts_for(args)
        sp = getattr(args, "_sharepoint_run", None)
        extra = {}
        if (sp is not None and sp.sharepoint) or _served_by_sharepoint(target, pages):
            extra = {"sharepoint": True,
                     "ootb_registry": getattr(args, "_ootb_registry", None)}
        result = audit.analyze_pages(
            pages, target, media_progress=_image_progress,
            site_controls=getattr(args, "site_controls", False),
            within=getattr(args, "within", None) or "",
            web_parts=args._web_parts_found,
            include_environment=bool(getattr(args, "include_environment", False)),
            **extra)
        tree = getattr(args, "_page_tree", None)
        if tree:
            result.page_tree = tree
        return result
    if is_page_file:
        return audit.analyze_page_file(
            target, within=getattr(args, "within", None) or "")
    from repo_scanner import scan_repo

    repo_files = scan_repo(target, _build_scan_config(args, target=target))
    if not repo_files:
        print(f"# nothing readable in {target} - the report will say so "
              f"rather than call it clean", file=sys.stderr)
    return audit.analyze_files(repo_files, target,
                               force_medium=getattr(args, "medium", None))


#: The languages a report exists in. `report/template.py` carries labels for
#: exactly these, `i18n.translations` carries strings for exactly these, and
#: `detector_advice` writes advice in exactly these - so the list lives with
#: the strings, and `i18n.translations.report_language` is the one function
#: that decides.
from i18n.translations import LANGUAGES as _LANGUAGES, report_language

REPORT_LANGUAGES = tuple(sorted(_LANGUAGES))


def _detect_report_language(lang, pages, announce=None) -> str:
    """Which language the report is written in, and why.

    Three steps, in this order:

    1. `--language`, when it names one of `REPORT_LANGUAGES`. What the
       caller asked for is the answer, and a value outside the three is
       refused rather than half-honoured.
    2. What the pages are written in, when that is one of the three. Voted
       on passages long enough to read, not on menu labels - see below.
    3. English.

    Step 3 is the part that was missing. `lang_detect` answers `other` for a
    page in a language this tool has no lists for, and that answer was being
    used as the report language: a German or Spanish site produced a report
    whose language is `"other"`, which no label table and no advice list
    has. It read as English only because every lookup happens to fall back
    to English on a missing key - an accident, in the one place that should
    be a decision.
    """
    if lang is not None:
        chosen = report_language(lang)
        if chosen != lang and announce:
            announce(f"# [report] language {lang!r} is not one of "
                     f"{', '.join(REPORT_LANGUAGES)}; writing in English")
        return chosen
    # Only blocks long enough to *read* vote. Every block used to, and a
    # navigation label is one or two words: measured on an Italian site whose
    # prose is 9:2 Italian, the whole-page vote was 23 `en` against 19 `it`
    # - menu items, button captions and a cookie line - and the report came
    # out in English. With the short strings out of it the same page votes
    # 9:2 and reads Italian, which is also what makes `detector_advice`
    # reach an Italian reader at all: the advice is chosen by this answer.
    #
    # The fallback is the old vote rather than `en`: a page that is all
    # short strings still has a language, and guessing English there would
    # be the same defect pointing the other way.
    MIN_WORDS = 8
    long_hints, all_hints = [], []
    for page in (pages or []):
        for block in page.blocks:
            if not block.language_hint:
                continue
            all_hints.append(block.language_hint)
            if len(block.text.split()) >= MIN_WORDS:
                long_hints.append(block.language_hint)
    hints = [h for h in (long_hints or all_hints) if h in REPORT_LANGUAGES]
    if not hints:
        return report_language(None)
    chosen, votes = Counter(hints).most_common(1)[0]
    if announce:
        announce(f"# [report] language {chosen} "
                 f"({votes} of {len(hints)} readable passage(s))")
    return chosen


def _issues_at_floor(audit_result, floor: str | None,
                     unsettled: bool = False) -> list:
    """Apply the view, then flatten - in that order.

    `audit` filters in `cli.py`; `fullscan` builds its own result, so the
    same view has to be taken here or the flag would mean two things.

    The order is the whole reason this is a function. The filter used to run
    *after* the documents had already been flattened into the list the JSON
    and the summary are built from, so `--confidence exact` reached the
    reports and never the machine-readable output: measured on
    `https://www.python.org/`, the JSON kept all 1030 findings and all 46
    GEO rows while the HTML showed 918 and none. One flag, two answers.
    """
    if audit_result is None or not audit_result:
        return []
    from audit.base import issues_in_view, unsettled_count, unsettled_summary

    # `fullscan` loads the page in a real browser, which is what settles
    # these; what the browser still could not decide is not a finding. Said
    # out loud rather than dropped in silence.
    hidden = 0 if unsettled else sum(unsettled_count(d.issues)
                                     for d in audit_result.documents)
    which = "" if unsettled else unsettled_summary(
        [i for d in audit_result.documents for i in d.issues])
    if hidden:
        progress.notice(
            "audit",
            f"{hidden} check(s) could not be decided and are not listed "
            f"({which}); add --unsettled to see them",
            human=f"# [audit] {hidden} check(s) could not be decided and are "
                  f"not listed ({which}); add --unsettled to see them",
            unsettled=hidden, unsettled_rules=which)
    return [issue for document in audit_result.documents
            for issue in issues_in_view(document.issues, (), floor or "", unsettled=unsettled)]


def _count(audit_issues, category: str) -> int:
    """Findings in one audit category.

    Exists so the category names in the summary come from `audit.base`
    instead of being retyped: the retyped one was `"best_practices"` against
    a constant of `"best-practices"`, and that count read 0 forever without
    failing anything.
    """
    return sum(1 for issue in audit_issues if issue.category == category)


def _build_combined(args, target: str, is_url: bool, lang: str,
                    scan_result, clean_findings: list, audit_issues: list) -> dict:
    """Phase 3: the single JSON document the command prints."""
    from audit import base
    from finding_contract import SCHEMA_VERSION, serialize_issue
    return {
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "is_url": is_url,
        "language": lang,
        "scan": scan_result or {"findings": [], "counts": {"total": 0, "style": 0, "characters": 0}},
        "audit": {
            # Distinct problems, as `audit --json` counts them: a header on
            # every page is one job. The occurrences are beside them.
            "counts": _severity_counts(first for first, _ in
                                       duplicates.group_issues(audit_issues)),
            "occurrences": _severity_counts(audit_issues),
            "distinct": len(duplicates.group_issues(audit_issues)),
            "issues": [serialize_issue(i) for i in audit_issues],
        },
        "summary": {
            "total_findings": len(clean_findings) + len(audit_issues),
            # One predicate, not two. See `is_character_finding`: counting
            # `source == "style"` here missed every judge finding, because a
            # judge stamps its own name.
            "ai_patterns": len([f for f in clean_findings
                                if not is_character_finding(f)]),
            "characters": len([f for f in clean_findings
                               if is_character_finding(f)]),
            # The constants, not copies of them. `"best_practices"` was
            # written here by hand while the category is `"best-practices"`,
            # so that count was 0 on every scan ever run.
            "accessibility": _count(audit_issues, base.ACCESSIBILITY),
            "seo": _count(audit_issues, base.SEO),
            "geo": _count(audit_issues, base.GEO),
            "performance": _count(audit_issues, base.PERFORMANCE),
            "best_practices": _count(audit_issues, base.BEST_PRACTICES),
        },
    }


def _attach_agent_payload(combined: dict, agent_candidates: list,
                          target: str) -> None:
    """Agent mode: hand the candidates plus judging rules to the caller."""
    combined["agent_candidates"] = agent_candidates
    combined["detection_rules"] = _agent_detection_rules()
    combined["agent_instruction"] = (
        "You are an AI text judge. Use the detection_rules to evaluate "
        "each candidate. Consider ALL signals: statistical (uniformity, "
        "repetition, dash density), structural patterns, and cliché phrases. "
        "Do NOT dismiss dash density as 'typography' — it IS an AI signal. "
        "For each candidate return block_id, score (0.0=human, 1.0=AI), "
        "and a one-sentence reason. Then pipe judgments to: "
        "xanalyze agent-judge " + target + " --judgments -"
    )


def is_character_finding(finding: dict) -> bool:
    """Is this about a character, rather than about the wording?

    The one place that answers it. There were two, and they disagreed: the
    summary counted `source == "style"` while the report counted "anything
    that is not typography". A judge stamps its findings `source: "model"`,
    so a live run that found six model-written passages - three of them at
    high confidence, with the reasoning written out in Italian - reported
    `ai_patterns: 0` in the same JSON whose own `counts` said `style: 6`.

    Asked the way round that stays true when a new detector is added: a
    character finding is recognisable (it says so), and everything else is
    about the wording. The other phrasing has to be extended for every
    backend, and is silently wrong until someone notices.
    """
    explanation = finding.get("explanation",
                              finding.get("offline_explanation", "")) or ""
    source = (finding.get("source") or "").lower()
    return "characters" in source or "typography" in explanation.lower()


def _split_style_typography(content_findings: list):
    """Sort content findings into wording vs character buckets."""
    style_findings: list = []
    typo_findings: list = []
    for f in content_findings:
        (typo_findings if is_character_finding(f) else style_findings).append(f)
    return style_findings, typo_findings


def _populate_ai_patterns(model, style_findings: list, repo_stats: dict | None = None) -> None:
    top_patterns = []
    for f in sorted(style_findings,
                    key=lambda x: x.get("score", x.get("offline_score", 0)),
                    reverse=True)[:10]:
        row = {"text": f.get("text", f.get("offline_explanation", ""))[:100],
               "score": f.get("score", f.get("offline_score", 0)),
               "confidence": f.get("confidence", "low"),
               "explanation": f.get("explanation", f.get("offline_explanation", ""))[:120]}
        # Present only when `--repo` was given and this passage matched -
        # the direct place to fix it, alongside the page it renders on.
        if f.get("source_file"):
            row["source_file"] = f["source_file"]
            row["source_line"] = f.get("source_line", 0)
        if f.get("mapping"):
            row["mapping"] = f["mapping"]
        top_patterns.append(row)
    model.ai_patterns = {
        "total": len(style_findings),
        "high": len([f for f in style_findings if f.get("confidence") == "high"]),
        "medium": len([f for f in style_findings if f.get("confidence") == "medium"]),
        "low": len([f for f in style_findings if f.get("confidence") == "low"]),
        "files": len({f.get("file", "") for f in style_findings}),
        "top_patterns": top_patterns,
    }
    if repo_stats and repo_stats.get("repo_total"):
        model.ai_patterns["repo_matched"] = repo_stats["repo_matched"]
        model.ai_patterns["repo_total"] = repo_stats["repo_total"]


def _populate_typography(model, typo_findings: list) -> None:
    by_char: dict = {}
    for f in typo_findings:
        exp = f.get("explanation", f.get("offline_explanation", ""))
        char_name = exp.split("] ")[-1].split(" ->")[0] if "] " in exp else exp[:50]
        by_char.setdefault(char_name, 0)
        by_char[char_name] += 1
    model.typography = {
        "total": len(typo_findings),
        "files": len({f.get("file", "") for f in typo_findings}),
        "by_character": dict(sorted(by_char.items(), key=lambda x: -x[1])[:10]),
    }


def _styled_report_model(args, audit_result, content_findings: list,
                         lang: str, repo_stats: dict | None = None):
    """Build the ReportModel behind --styled-report.

    `args` is a parameter and not a closure: the run header needs the flags
    the person typed, and reading them from a name this function never
    received raised `NameError` inside the writer's own `try` - so every
    `fullscan` said "styled report failed" and wrote no styled report at
    all, on every run, while the suite stayed green. See
    `tests/test_styled_report_written.py`.
    """
    from report.model import (
        from_accessibility, from_finding_dicts,
    )

    model = None
    if audit_result:
        model = from_accessibility(audit_result, lang=lang)
        from cli_impl.reports import _command_of
        from cli_impl.runheader import describe

        model.meta.run = describe(_command_of(args), audit_result.root, args,
                                  language=lang)
        # The checkout behind the address, when there is one. `--devserver`
        # sets `args.repo` to the folder it started, so a run against
        # `http://127.0.0.1:5173/` is headed by the project's name instead
        # of by a port number. See `report.model.display_name`.
        model.meta.repo = str(getattr(args, "repo", "") or "")

    if content_findings:
        # `from_finding_dicts`, not `from_text_analysis`: by this point the
        # live spans are gone - the checkpoint keeps the public dicts,
        # because a span holds detector objects that do not survive JSON -
        # and the dicts are what the run still has. Every content finding used to be
        # dropped here, so the report's cards and charts counted the audit
        # only - 18 of 33 on `simulations/mixed-problems`.
        text_model = from_finding_dicts(list(content_findings),
                                        character_of=is_character_finding)
        if model:
            model.findings.extend(text_model.findings)
        else:
            model = text_model

    if model is None:
        return None

    if audit_result:
        from report.model import page_index

        model.pages = page_index(
            {"source": doc.source, "findings_count": len(doc.issues),
             "error": doc.error or ""}
            for doc in audit_result.documents
        )

    style_findings, typo_findings = _split_style_typography(content_findings)
    if style_findings:
        _populate_ai_patterns(model, style_findings, repo_stats)
    if typo_findings:
        _populate_typography(model, typo_findings)
    return model


def _write_styled_report(args, audit_result, content_findings: list,
                         lang: str, repo_stats: dict | None = None) -> None:
    if not getattr(args, "styled_report", None):
        return
    model = _styled_report_model(args, audit_result, content_findings, lang,
                                 repo_stats)
    if model is None:
        return
    from report.export import write_styled_report

    progress.stage("report", "begin", "# [stage] writing reports...")
    # The markdown path travels with it so that, if the PDF cannot be
    # printed, the one-page stand-in can name the report to read instead of
    # merely gesturing at the folder.
    write_styled_report(args.styled_report, model, lang,
                        markdown_path=getattr(args, "report", None))
    progress.notice("report", f"styled report: {args.styled_report}",
                    human=f"# styled report: {args.styled_report}",
                    path=str(args.styled_report), kind_of="styled")


def _markdown_briefing_input(agent_mode: bool, agent_candidates: list,
                             scan_findings: list) -> list:
    """AI-pattern rows for the markdown briefing."""
    if agent_mode and agent_candidates:
        return [
            {"file": c.get("file", ""), "line": c.get("line", 0),
             "text": c.get("text", "")[:200],
             "score": c.get("offline_score", 0),
             "confidence": "medium" if c.get("offline_score", 0) >= 0.5 else "low",
             "explanation": c.get("offline_explanation", "")}
            for c in agent_candidates
        ]
    rows = []
    for f in scan_findings:
        row = _public(f)
        # `file`/`line` stay the page - the agent briefing's other rows all
        # mean "here" that way. `source_file`/`source_line` are additive:
        # where `--repo` was given and this passage matched, an agent about
        # to edit the code should not have to re-derive that from the page.
        if f.get("source_file"):
            row["source_file"] = f["source_file"]
            row["source_line"] = f.get("source_line", 0)
        rows.append(row)
    return rows


def _write_markdown_briefing(args, audit_result, agent_mode: bool,
                             agent_candidates: list, scan_findings: list,
                             lang: str) -> dict | None:
    """Write the briefing and hand back the payload it wrote.

    The payload carries the grouped problems and the run history, which the
    comparison document needs; recomputing either would mean grouping the
    findings twice.
    """
    from cli_impl.reports import _write_report

    if not getattr(args, "report", None) or audit_result is None:
        return None
    ai_for_report = _markdown_briefing_input(
        agent_mode, agent_candidates, scan_findings)
    # No second "agent briefing: <path>" line here: `_write_report` already
    # prints the path it wrote, and two lines naming one file read as two
    # files.
    return _write_report(audit_result, args, lang, None,
                         ai_findings=ai_for_report)


def _write_run_documents(folder, target: str, timings, payload, combined,
                         documents: int, args=None) -> None:
    """The two documents that describe the run rather than the target.

    `timings.md` says where the time went, so "why did this take an hour"
    has an answer without re-running anything. `changes.md` says what the
    last round of work achieved - and is not written at all on a first run,
    because a comparison document with nothing to compare reads as a broken
    comparison rather than as a first run.
    """
    from cli_impl.reports import write_comparison_document

    summary = combined.get("summary", {})
    # The same passport the reports carry, so a folder of timings from
    # several runs can be told apart by what each run actually did rather
    # than by its clock time alone.
    from cli_impl.reports import _command_of
    from cli_impl.runheader import as_line, describe

    extra = {}
    if args is not None:
        extra["run"] = as_line(describe(_command_of(args), target, args))
    timings.write(folder.timings, target, extra={
        **extra,
        "pages or files examined": documents,
        "findings": summary.get("total_findings", 0),
        "AI patterns": summary.get("ai_patterns", 0),
        "accessibility": summary.get("accessibility", 0),
        "run folder": str(folder.run),
    })
    if payload is not None:
        wrote = write_comparison_document(folder.changes, payload)
        if not wrote:
            earlier = folder.previous_runs()
            text = ("first run of this target - nothing to compare against"
                    if not earlier else
                    "no comparable previous run recorded for this target")
            progress.notice("report", text, human=f"# {text}",
                            compared=False)


def _stop_short(state, folder, target, timings, phase, reason, *,
                paused=False) -> int:
    """End a run that could not finish, keeping everything it produced.

    The whole point of the phase record is this function existing at all: a
    run that stops has to leave behind what it computed, a statement of where
    it stopped, and one command that continues. Before this, a failure in the
    last of six phases discarded the five that had succeeded - on a real site
    that was forty-six minutes of crawling and auditing thrown away because a
    two-minute step raised.
    """
    if state is None:
        word = "paused" if paused else "stopped"
        progress.notice("warning", f"{word}: {reason}",
                        human=f"# {word}: {reason}",
                        paused=paused, reason=reason)
        return EXIT_INCOMPLETE
    if not paused:
        state.fail(phase, reason)
    timings.finish()
    if folder is not None:
        try:
            timings.write(folder.timings, target,
                          extra={"stopped in": phase, "reason": reason})
        except Exception as exc:  # noqa: BLE001 - the state file matters more
            progress.notice("warning", f"timings failed: {exc}",
                            human=f"# warning: timings failed: {exc}",
                            about="timings")
    state.write_feedback()
    state.write_markdown()
    info = state.feedback()
    word = "paused" if paused else "stopped"
    progress.notice("warning", f"{word} in {phase}: {reason}",
                    human=f"# {word} in {phase}: {reason}",
                    paused=paused, phase=phase, reason=reason,
                    artifacts=len(info["artifacts"]) or None,
                    resume_with=info["resume_with"] or None)
    if not progress.enabled():
        if info["artifacts"]:
            print(f"# kept {len(info['artifacts'])} artifact(s) in "
                  f"{state.run_dir}", file=sys.stderr)
        if info["resume_with"]:
            print(f"# continue with: {info['resume_with']}", file=sys.stderr)
    # The machine-readable half goes to stdout, where every other command
    # puts its JSON: an agent that ran this must be able to read the outcome
    # the same way it reads a success, and not have to scrape stderr.
    from audit.coverage import build_coverage
    from audit.engine import AccessibilityResult
    from finding_contract import SCHEMA_VERSION, serialize_issue
    partial_audit = checkpoint.load_audit(state.run_dir) or AccessibilityResult(target)
    partial_scan = checkpoint.load_scan_result(state.run_dir)
    coverage = partial_audit.coverage or build_coverage(partial_audit, scan=partial_scan)
    coverage["status"] = "incomplete"
    coverage.setdefault("errors", []).append({"phase": phase, "reason": reason})
    print(json.dumps({"schema_version": SCHEMA_VERSION,
                      "target": target, "incomplete": True, "coverage": coverage,
                      "audit": {"issues": [serialize_issue(i) for i in partial_audit.issues()]},
                      "scan": partial_scan,
                      "run": str(state.run_dir), "state": info},
                     indent=2, ensure_ascii=False))
    return EXIT_INCOMPLETE


def _confirm_install(stack_name: str, install_argv: list, args) -> bool:
    """Ask before running an install command. Mirrors `uninstall._confirm`.

    `--yes` bypasses the prompt, exactly like `uninstall`'s own bypass - the
    same shape for the same reason: a script driving this CLI has no stdin to
    answer with, and `EOFError` alone would make every unattended run silently
    decline an install it might have wanted.
    """
    if getattr(args, "yes", False):
        return True
    try:
        answer = input(f"{stack_name}: dependencies are missing. Run "
                       f"`{' '.join(install_argv)}`? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def _maybe_start_devserver(args, repo_path: str):
    """Detect and start a dev server for `repo_path`, or say why not.

    Returns `(target, process_or_None, skip_reason_or_None)`. `target` is
    `repo_path` unchanged unless a server was actually confirmed listening -
    every failure here falls back to the static repo scan `fullscan` already
    does, rather than aborting the run: the same "warn, never silent, keep
    going on the fallback path" shape as `_content_passes` handling a judge
    that could not be built.
    """
    repo = Path(repo_path)
    stack = devserver.detect_stack(repo)
    if stack is None:
        return repo_path, None, None

    override = getattr(args, "start_command", None)
    start_argv = shlex.split(override) if override else None
    port = getattr(args, "dev_server_port", None)
    try:
        plan = devserver.build_plan(stack, repo, start_argv=start_argv, port=port)
    except devserver.DevServerUnavailable as exc:
        return repo_path, None, f"{stack.name}: {exc}"

    if plan.install_argv is not None:
        progress.notice("devserver", f"{stack.name}: dependencies missing",
                        human=f"# [devserver] {stack.name}: dependencies "
                              f"missing",
                        stack=stack.name)
        if not _confirm_install(stack.name, plan.install_argv, args):
            return repo_path, None, f"{stack.name}: dependencies missing, install declined"
        try:
            devserver.run_install(plan)
        except devserver.DevServerInstallFailed as exc:
            return repo_path, None, str(exc)

    proc = devserver.DevServerProcess.start(plan)
    try:
        url = proc.wait_ready(60)
    except devserver.DevServerNeverReady as exc:
        proc.stop()
        return repo_path, None, str(exc)
    progress.notice("devserver", f"{stack.name} ready at {url}",
                    human=f"# [devserver] {stack.name} ready at {url}",
                    stack=stack.name, url=url)
    return url, proc, None


def cmd_fullscan(args) -> int:
    """Full scan: AI patterns + accessibility audit + reports for agent.

    Combines scan (AI patterns, characters) and audit (accessibility, SEO,
    performance, best practices) into one command. Saves styled report and
    agent briefing, outputs JSON for agent consumption.

    For URLs and HTML files: automatically enables browser rendering and
    responsive breakpoints (desktop, tablet, mobile). Reports are auto-saved
    to ~/Desktop unless --styled-report/--report specify a different path.

    With --agent: runs offline scan and outputs candidate blocks for the
    agent to judge with its own LLM (no API key needed). The agent reads
    the candidates, judges them, and pipes judgments to `agent-judge`.

    Usage:
      xanalyze fullscan https://example.com           # full scan with browser
      xanalyze fullscan ./repo                        # repo scan (no browser)
      xanalyze fullscan ./repo --devserver             # start its dev server, scan the render
      xanalyze fullscan https://example.com --breakpoints desktop  # desktop only
      xanalyze fullscan ./repo --agent                # agent judges AI patterns
    """
    lang = args.language  # None if not specified, will auto-detect after crawl
    from cli_impl.auditpass import unquote_target

    target = unquote_target(args.target)
    is_url = looks_like_url(target) or args.url
    if is_url:
        # Normalised here rather than inside the crawl, so the report file
        # names and the JSON `target` say the same address that was fetched.
        target = with_scheme(target)
    is_page = _is_page_file(target) if not is_url else False
    # Browser is automatic for URLs and HTML files, not for repos
    no_browser = getattr(args, "no_browser", False)
    wants_browser = (is_url or is_page) and not no_browser
    agent_mode = getattr(args, "agent", False)

    # Validated before the run folder is created: a typo must not leave an
    # empty folder behind on someone's Desktop.
    if not is_url and not is_page and not Path(target).exists():
        progress.notice("error", f"path not found: {target}",
                        human=f"path not found: {target}")
        return EXIT_ERROR

    # `--project`: one deliverable out of a folder that holds several. Done
    # before anything is prepared, so every document is named after what was
    # actually audited. See `cli._narrow_to_project`.
    from cli import _narrow_to_project

    target, refusal = _narrow_to_project(target, args)
    if refusal:
        progress.notice("error", refusal, human=refusal)
        return EXIT_ERROR

    # A SharePoint Online target without a sign-in, refused before the run
    # folder exists - the same check `audit` makes, in the same place.
    if is_url:
        from cli_impl.auditpass import say_refusal, sign_in_refusal

        sp_refusal = sign_in_refusal(target, args)
        if sp_refusal:
            say_refusal(sp_refusal, target, "sign-in-required")
            return EXIT_ERROR
    # A local file, so read before the folder: a typo leaves nothing behind.
    from cli_impl.auditpass import registry_refusal

    bad_registry = registry_refusal(args)
    if bad_registry:
        progress.notice("error", bad_registry, human=bad_registry)
        return EXIT_ERROR

    # Before any work: what this run is about to leave undone, and the one
    # flag that would change it. See `cli_impl.prerun`.
    from cli_impl import prerun

    prerun.announce("fullscan", target, args, is_url=is_url, out=sys.stderr)
    # What this target's own stack asks for. A line, unless
    # `--profile-defaults` was passed - see `cli_impl.prerun.profile`.
    prerun.profile("fullscan", target, args, is_url=is_url, out=sys.stderr)

    repo_arg = getattr(args, "repo", None)
    if repo_arg and not Path(repo_arg).is_dir():
        text = f"--repo path not found or not a directory: {repo_arg}"
        progress.notice("error", text, human=text)
        return EXIT_ERROR

    resumed = getattr(args, "_resume_state", None)
    if resumed is not None:
        folder = runfolder.RunFolder(resumed.run_dir.parent, resumed.run_dir)
        state = resumed
    else:
        folder = _fullscan_report_paths(args, target)
        state = (runstate.RunState.begin(folder, target) if folder is not None
                 else None)
    timings = runfolder.Timings()

    def already(phase: str) -> bool:
        """Did an earlier attempt finish this phase?

        Only ever true on a resume, and it is what makes resume worth having:
        the crawl and the browser pass are three minutes and forty-three on a
        real site, against two for everything after them.
        """
        entry = state.phase(phase) if state is not None else None
        return bool(entry and entry["status"] == runstate.DONE)

    def guard(phase: str) -> None:
        """Honour a pause request at a phase boundary."""
        if state is not None:
            state.checkpoint(phase)

    try:
        return _run_phases(args, state, folder, timings, target, lang, is_url,
                           is_page, wants_browser, agent_mode, already, guard)
    except runstate.Paused as paused:
        return _stop_short(state, folder, target, timings,
                           state.next_phase() if state else "", str(paused),
                           paused=True)


def _run_phases(args, state, folder, timings, target, lang, is_url, is_page,
                wants_browser, agent_mode, already, guard) -> int:
    """The phases themselves, each recording its own outcome.

    Split out from `cmd_fullscan` so the pause exception has one place to be
    caught: a `Paused` raised at any boundary unwinds to exactly one handler,
    and a paused run and a failed run then leave the same shape behind - which
    is what lets `resume` have one code path instead of two.
    """
    # --- Phase 0: dev server, for a repo target with no URL ---
    #
    # Deliberately local to this function rather than done in `cmd_fullscan`
    # before the run folder is created: `cmd_fullscan` names the folder and
    # the resumed run's identity from `target` as given, and that must stay
    # the repo path across every run of it - not the dev server's port,
    # which is different every time and would otherwise turn one project
    # into a new "target" on every scan. `is_url`/`is_page`/`wants_browser`
    # are plain local variables here, so reassigning them below is exactly
    # what the rest of this function, unmodified, then runs on.
    devserver_proc = None
    is_repo_target = not is_url and not is_page and Path(target).is_dir()
    if is_repo_target and not getattr(args, "devserver", False):
        # Not requested: said once, because a repo that happens to have a
        # start command is the ordinary case, not something worth a warning -
        # but silence would mean nobody ever learns the flag exists.
        stack = devserver.detect_stack(Path(target))
        if stack is not None:
            progress.notice(
                "devserver",
                f"{stack.name} detected but not started - scanning source "
                f"only. Pass --devserver to read the rendered site instead, "
                f"or --url if one is already running",
                human=f"# [devserver] {stack.name} detected but not started - "
                      f"scanning source only. Pass --devserver to read the "
                      f"rendered site instead, or --url if one is already "
                      f"running",
                stack=stack.name, started=False)
    if (is_repo_target and getattr(args, "devserver", False)
            and not already("crawl")):
        guard("devserver")
        if state is not None:
            state.start("devserver")
        repo_path = target
        target, devserver_proc, skip_reason = _maybe_start_devserver(args, repo_path)
        is_url = looks_like_url(target) or args.url
        is_page = _is_page_file(target) if not is_url else False
        wants_browser = (is_url or is_page) and not getattr(args, "no_browser", False)
        if devserver_proc is not None:
            if not getattr(args, "repo", None):
                # The checkout that was just used to start the server *is*
                # the code behind the site now being scanned - the same
                # source-file cross-referencing `--repo` already gives
                # applies without saying the same path twice.
                args.repo = repo_path
            if state is not None:
                state.done("devserver")
        elif state is not None:
            state.skip("devserver", skip_reason or "no dev server detected")
    elif state is not None:
        state.skip("devserver", "target is a URL, a single file, or --devserver was not passed")

    try:
        return _run_phases_body(args, state, folder, timings, target, lang,
                                is_url, is_page, wants_browser, agent_mode,
                                already, guard)
    finally:
        if devserver_proc is not None:
            devserver_proc.stop()


def _run_phases_body(args, state, folder, timings, target, lang, is_url, is_page,
                     wants_browser, agent_mode, already, guard) -> int:
    """The phases from the AI-patterns scan onward.

    Split out from `_run_phases` so the dev server it may have started has
    exactly one place to be stopped - a `finally` around this call - whether
    the run below finishes, fails, or pauses.
    """
    # --- Phase 1: AI patterns scan (for local files/repos) ---
    pages = None
    agent_candidates: list = []
    scan_findings, scan_result = [], None
    if not is_url:
        guard("scan")
        if already("scan"):
            scan_result = checkpoint.load_scan_result(state.run_dir) or {}
            scan_findings = scan_result.get("findings", [])
            progress.notice("resume", "AI patterns scan reused",
                            human="# [resume] AI patterns scan reused",
                            phase="scan")
        else:
            timings.start("AI patterns scan")
            if state is not None:
                state.start("scan")
            progress.stage("scan", "begin", target=target)
            try:
                scan_findings, scan_result, agent_candidates = \
                    _scan_local_target(target, args, lang, agent_mode)
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                return _stop_short(state, folder, target, timings, "scan",
                                   f"the AI patterns scan failed: {exc}")
            progress.stage("scan", "end",
                           findings=len((scan_result or {}).get("findings", [])))
            if state is not None:
                # The public form, not the raw findings: those carry `_span`
                # and `_block` keys holding live detector objects, which are
                # what `fix` rewrites files through and are not serialisable.
                # Nothing after this phase reads them - the reports take the
                # same public dicts a crawl produces - so the checkpoint is
                # complete for every consumer that exists.
                saved = checkpoint.save_scan(
                    state.run_dir, (scan_result or {}).get("findings", []),
                    (scan_result or {}).get("counts"), scan_result=scan_result)
                state.done("scan", artifacts=[saved])
    elif state is not None:
        state.skip("scan", "folded into the crawl for a website")
    if not is_url and state is not None:
        # A folder is not crawled. Said explicitly, because a phase left
        # `pending` is one `resume` will try to run: without this a finished
        # repo scan reported itself as unfinished and offered to continue.
        state.skip("crawl", "not a website")

    # --- Phase 2: Accessibility audit ---
    audit_issues: list = []
    audit_result = None
    if is_url:
        guard("crawl")
        timings.start("crawl")
        if state is not None:
            state.start("crawl")
        try:
            pages, target = _crawl_for_fullscan(target, args, no_browser=
                                                getattr(args, "no_browser", False))
        except SharePointRefused as refused:
            # Not a crash and not a pause: the site said this sign-in cannot
            # read it, and `resume` would get the same answer. Exit 2, as
            # `audit` does, with the command that fixes it.
            from cli_impl.auditpass import say_refusal

            say_refusal(str(refused), target, refused.reason)
            # The run folder already exists (the tree needs the network, so
            # it is asked after the folder): it says why it is empty -
            # `state.json`, `state.md` and the timings name the phase and the
            # refusal, the same record `_stop_short` leaves.
            if state is not None:
                state.fail("crawl", str(refused))
                state.write_feedback()
                state.write_markdown()
            timings.finish()
            if folder is not None:
                try:
                    timings.write(folder.timings, target,
                                  extra={"stopped in": "crawl",
                                         "reason": str(refused)})
                except Exception as exc:  # noqa: BLE001 - the state matters more
                    progress.notice("warning", f"timings failed: {exc}",
                                    human=f"# warning: timings failed: {exc}",
                                    about="timings")
            return EXIT_ERROR
        except Exception as exc:  # noqa: BLE001
            return _stop_short(state, folder, target, timings, "crawl",
                               f"the crawl failed: {exc}")
        if state is not None:
            state.done("crawl")
        _warn_about_spa(pages)

        # Agent mode: extract candidates from crawled pages
        if agent_mode and pages:
            agent_candidates = _agent_candidates_from_pages(pages)
            scan_result = {
                "findings": [],
                "counts": {"total": 0, "style": 0, "characters": 0},
                "agent_mode": True,
                "candidates_count": len(agent_candidates),
            }
        elif pages:
            # Not agent mode: the same content pass a repo gets, so the
            # AI-patterns and typography sections exist in the reports.
            timings.start("AI patterns scan")
            repo_stats: dict = {}
            scan_findings = _content_findings_from_pages(
                pages, args, stats_out=repo_stats)
            counts = {
                "total": len(scan_findings),
                "style": len([f for f in scan_findings
                              if f.get("source") != "characters"]),
                "characters": len([f for f in scan_findings
                                   if f.get("source") == "characters"]),
            }
            # `counts` is read as numbers - the TUI renders a row per key -
            # so only the numeric stats go in. The detector note is a
            # sentence and belongs beside the findings, not among them.
            note = repo_stats.pop("detector_note", None)
            scan_errors = repo_stats.pop("scan_errors", [])
            if "repo_matched" in repo_stats:
                counts.update(repo_stats)
                # One line, not one per passage: `--repo` given but almost
                # nothing matching is worth knowing about (wrong checkout,
                # or a gap like `_I18N_CALLS` missing WordPress's `_e()`),
                # and it belongs beside the other stage notes, not buried in
                # the JSON only an agent will read.
                progress.notice(
                    "ai-patterns",
                    f"matched to --repo: {repo_stats['repo_matched']}/"
                    f"{repo_stats['repo_total']} distinct passage(s)",
                    human=f"# [AI patterns] matched to --repo: "
                          f"{repo_stats['repo_matched']}/"
                          f"{repo_stats['repo_total']} distinct passage(s)",
                    matched=repo_stats["repo_matched"],
                    total=repo_stats["repo_total"])
            scan_result = {
                "findings": scan_findings,
                "counts": counts,
                "errors": scan_errors,
            }
            if note:
                scan_result["detector_note"] = note

    guard("audit")
    if already("audit") and not already("browser"):
        # The static findings survived; the browser pass did not finish, so
        # it runs again over the reloaded result. Not resumed at page 97 -
        # per-page checkpointing is a bigger change, and the crawl, which is
        # the expensive part, is what this already saves.
        audit_result = checkpoint.load_audit(state.run_dir)
        if audit_result is not None:
            progress.notice("resume", "static audit reused",
                            human="# [resume] static audit reused",
                            phase="audit")
    if audit_result is None:
        timings.start("static audit")
        if state is not None:
            state.start("audit")
        progress.stage("audit", "begin", target=target)
        try:
            audit_result = _audit_fullscan_target(
                is_url, is_page and not is_url, target, args, pages)
        except Exception as exc:  # noqa: BLE001
            return _stop_short(state, folder, target, timings, "audit",
                               f"the static audit failed: {exc}")
        # Both numbers, because they are different numbers and one name
        # for them is how "4 documents" and "2 documents" ended up in the
        # same stream: a page is audited as several documents (its own
        # rules, its response headers, an image's provenance), and the
        # count a reader recognises is the addresses.
        progress.stage(
            "audit", "end",
            documents=len(audit_result.documents) if audit_result else 0,
            sources=len({d.source for d in audit_result.documents})
            if audit_result else 0)
        if state is not None:
            state.done("audit", artifacts=filter(
                None, [checkpoint.save_audit(state.run_dir, audit_result)]))

    if audit_result:
        # Run browser pass automatically for URLs and HTML files
        if already("browser"):
            reloaded = checkpoint.load_audit(state.run_dir)
            if reloaded is not None:
                audit_result = reloaded
                progress.notice("resume", "browser pass reused",
                                human="# [resume] browser pass reused",
                                phase="browser")
        elif wants_browser:
            guard("browser")
            timings.start("browser pass")
            if state is not None:
                state.start("browser")
            suppressions = suppression.Suppressions.load(
                _settings_for_ignore(args), _ignore_root(args))
            try:
                _run_browser_pass(audit_result, suppressions, args)
                progress.stage("browser", "end")
            except Exception as exc:  # noqa: BLE001
                # The static findings are already checkpointed, so stopping
                # here keeps them: a browser pass that dies half-way used to
                # cost the crawl and the static audit as well.
                return _stop_short(state, folder, target, timings, "browser",
                                   f"the browser pass failed: {exc}")
            if state is not None:
                state.done("browser", artifacts=filter(
                    None, [checkpoint.save_audit(state.run_dir, audit_result)]))
        elif state is not None:
            state.skip("browser", "no browser pass for this target")
    if audit_result is not None:
        from audit.coverage import build_coverage
        audit_result.coverage = build_coverage(audit_result, args, scan=scan_result, pages=pages)
        if state is not None:
            checkpoint.save_audit(state.run_dir, audit_result)
    audit_issues.extend(
        _issues_at_floor(audit_result, getattr(args, "confidence", None),
                         unsettled=bool(getattr(args, "unsettled", False))))
    if audit_result is not None:
        audit_result = audit_result.narrowed(
            confidence=getattr(args, "confidence", None) or "",
            unsettled=bool(getattr(args, "unsettled", False)))
    # One event per finding, for a reader that asked for them
    # (`--progress jsonl=findings`). Here rather than at the end: this is the
    # first moment each one exists as a decided finding, and the reports
    # below can take minutes. `progress.finding` returns immediately when the
    # option is off, which is the ordinary case.
    if progress.wants_findings():
        # `kind` because the two halves answer different questions and
        # their `rule` fields are not the same kind of name: a content
        # finding names the detector that produced it, an audit finding
        # names the rule that fired.
        for finding in scan_findings:
            progress.finding(finding.get("detector", "") or "",
                             severity=finding.get("confidence", "") or "",
                             source=finding.get("file", "") or "",
                             line=finding.get("line"), kind="content")
        for issue in audit_issues:
            progress.finding(issue.rule_id, severity=issue.severity,
                             source=issue.source, line=issue.line,
                             category=issue.category, kind="audit")
    timings.finish()

    lang = _detect_report_language(
        lang, pages,
        announce=lambda line: progress.notice(
            "report", line.removeprefix("# [report] "), human=line))

    # --- Phase 3: Build combined result ---
    if pages and scan_result is not None:
        from finding_contract import json_value
        scan_result["text_blocks"] = [json_value(block) for page in pages for block in page.blocks]
    clean_findings = scan_result["findings"] if scan_result else []
    combined = _build_combined(args, target, is_url, lang, scan_result,
                               clean_findings, audit_issues)
    combined["coverage"] = audit_result.coverage if audit_result is not None else {"status": "unknown"}
    # The same two keys `audit --json` carries: how the page list was found,
    # and the zones a SharePoint page was split into.
    if audit_result is not None:
        if getattr(audit_result, "page_tree", None):
            combined["audit"]["page_tree"] = audit_result.page_tree
        if getattr(audit_result, "sharepoint", None):
            combined["audit"]["sharepoint"] = audit_result.sharepoint

    if agent_mode and agent_candidates:
        _attach_agent_payload(combined, agent_candidates, target)

    # --- Phase 4: Save reports ---
    all_content_findings = []
    if agent_mode and agent_candidates:
        all_content_findings = list(agent_candidates)
    elif scan_findings:
        all_content_findings = list(scan_findings)

    # Markdown first: it is plain text written in milliseconds and is the
    # artifact every consumer parses. The styled export starts a browser and
    # can take minutes on a large scan, so each writer is isolated: one
    # report failing must not take the others or the JSON below down with
    # it (a 158-page PDF once died after the whole browser pass and left
    # the run without any output at all).
    guard("reports")
    timings.start("writing reports")
    if state is not None:
        state.start("reports")
    written: dict = {}
    report_failures: list = []

    def _briefing() -> None:
        written["payload"] = _write_markdown_briefing(
            args, audit_result, agent_mode, agent_candidates, scan_findings,
            lang)

    def _say_saturation() -> None:
        """Say it on stderr too, where a person actually looks.

        A saturated rule is the shape every large false positive this tool
        shipped had, and burying the warning in a JSON key means the number
        gets acted on before anyone reads it. See `audit.saturation`.
        """
        from audit.saturation import saturated_rules

        if audit_result is None:
            return
        for note in saturated_rules(audit_result):
            progress.notice("warning", note.message(),
                            human=f"# warning: {note.message()}",
                            about="saturation")

    for label, write in (
        ("saturation check", _say_saturation),
        ("agent briefing", _briefing),
        ("styled report",
         lambda: _write_styled_report(args, audit_result,
                                      all_content_findings, lang,
                                      repo_stats=(scan_result or {}).get("counts"))),
    ):
        try:
            write()
        except Exception as exc:  # noqa: BLE001 - keep shipping the rest
            report_failures.append(f"{label}: {exc}")
            progress.notice("warning", f"{label} failed: {exc}",
                            human=f"# warning: {label} failed: {exc}",
                            about=label)

    if state is not None:
        produced = [p for p in (getattr(args, "report", None),
                                getattr(args, "styled_report", None))
                    if p and Path(p).exists()]
        if report_failures and not produced:
            # Every writer failed, so there is no report at all. Recorded as
            # a failure rather than warned about, because "no findings" and
            # "nothing was written" look identical to whoever opens the
            # folder next, and only one of them is a clean result.
            return _stop_short(state, folder, target, timings, "reports",
                               "; ".join(report_failures))
        if report_failures:
            # Partly written: the phase did its job, and the reason records
            # which writer did not, so a resume can be a deliberate choice
            # rather than a guess.
            state.phase("reports")["reason"] = "; ".join(report_failures)
        state.done("reports", artifacts=produced)

    # The comparison and the timings go in the run folder next to the
    # documents they describe. Isolated the same way as the reports above:
    # a failure here must not cost the caller the JSON result.
    if folder is not None:
        if state is not None:
            state.start("documents")
        try:
            # Addresses, not documents: a page is audited as several
            # documents (its own rules, its response headers, an image's
            # provenance), and "9 pages or files examined" for a four-page
            # crawl is the same miscount the page index used to print.
            _write_run_documents(
                folder, target, timings, written.get("payload"), combined,
                len({d.source for d in audit_result.documents})
                if audit_result else 0, args=args)
            if state is not None:
                state.done("documents", artifacts=[
                    p for p in (folder.timings, folder.changes) if p.exists()])
        except Exception as exc:  # noqa: BLE001 - keep shipping the rest
            progress.notice("warning", f"run documents failed: {exc}",
                            human=f"# warning: run documents failed: {exc}",
                            about="run documents")
            if state is not None:
                state.fail("documents", str(exc))
        progress.notice("run-folder", str(folder.run),
                        human=f"# run folder: {folder.run}",
                        path=str(folder.run))

    if state is not None:
        # Before `finish`, so a run that ends here carries its own headline
        # number. Nothing else can answer it afterwards: the catalogue is
        # built by walking folders, and re-reading every report to list five
        # rows would be a second scan rather than a list.
        state.record_findings(combined.get("summary", {}).get("total_findings", 0))
        if state.next_phase() is None:
            state.finish()
        state.write_feedback()
        state.write_markdown()

    # --- Phase 5: Output (always JSON for agent) ---
    #
    # The numbers `run.end` will carry, recorded here because this is where
    # they exist: `cli.main` knows the exit code and nothing else about the
    # run. See `progress.set_summary`.
    progress.stage("report", "end")
    progress.set_summary(
        counts=combined.get("summary", {}),
        documents=len(audit_result.documents) if audit_result else 0,
        sources=len({d.source for d in audit_result.documents})
        if audit_result else 0)
    print(json.dumps(combined, indent=2, ensure_ascii=False))

    if args.check:
        critical = combined['audit']['counts']['critical']
        serious = combined['audit']['counts']['serious']
        if critical > 0 or serious > 0:
            return EXIT_FINDINGS
    return EXIT_OK
