"""Report writing and run history.

A briefing another tool - or an agent - can act on directly: where the work
is concentrated, which files to open, what has already been done, and whether
the situation is getting better or worse. Markdown by default because that is
what a coding agent reads best; `.json` if the suffix asks for it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import progress
from models import RepoAnalysisResult


def _write_styled_text_report(files, findings, args) -> None:
    """`scan --styled-report`: the same findings as `--json`, laid out as a
    document for a person instead of a pipeline.

    Rebuilds a `RepoAnalysisResult` from what `_analyze` already computed —
    the actual `FileResult`s and the actual `TextSpan`s it kept under
    `finding["_span"]` — rather than re-scanning: `report.model.
    from_text_analysis` reads that type, and everything it needs was
    produced a few lines up in `cmd_scan`, at no extra cost.
    """
    from report.export import write_styled_report
    from report.model import from_text_analysis

    # Not `or "en"`: `--language fr` and a detected `other` both used to
    # travel on as a language nothing here has strings for. See
    # `i18n.translations.report_language`.
    from i18n.translations import report_language

    lang = report_language(getattr(args, "language", None))
    root = args.paths[0] if len(args.paths) == 1 else ", ".join(args.paths)
    # A finding replayed from the incremental cache has no `TextSpan`: the
    # span does not survive JSON, and the report is built from spans. Such a
    # finding is skipped rather than faked, and the difference is said out
    # loud - a document that quietly covers fewer files than the scan did is
    # the kind of report that gets trusted wrongly.
    spans = [f["_span"] for f in findings if f.get("_span") is not None]
    skipped = len(findings) - len(spans)
    result = RepoAnalysisResult(root_dir=root, files=files, spans=spans)
    from cli_impl.runheader import describe

    model = from_text_analysis(result)
    model.meta.run = describe(_command_of(args), root, args, language=lang)
    model.meta.repo = str(getattr(args, "repo", "") or "")
    write_styled_report(args.styled_report, model, lang)
    progress.notice("report", f"styled report: {args.styled_report}",
                    human=f"# styled report: {args.styled_report}",
                    path=str(args.styled_report), kind_of="styled")
    if skipped:
        print(f"# {skipped} finding(s) came from the incremental cache and are "
              f"not in the styled report; run without --incremental for a "
              f"complete document", file=sys.stderr)


def write_text_briefing(files, findings, args, path) -> None:
    """`scan --report`: the text scan's own briefing, in markdown.

    `--styled-report` has always existed for a person and `--json` for a
    pipeline; between them sat the document an agent reads, and the text
    scan was the one command that could not produce it. The audit briefing
    (`_write_report`) is built from an `AccessibilityResult` and cannot
    describe a text scan, so this is its counterpart rather than a flag on
    it: same shape - what this run was, where the work is, what to open
    first - over the findings a scan actually has.
    """
    from collections import Counter
    from pathlib import Path

    from i18n.translations import report_language
    from cli_impl.runheader import describe

    lang = report_language(getattr(args, "language", None))
    root = args.paths[0] if len(args.paths) == 1 else ", ".join(args.paths)
    by_source = Counter(f.get("source", "") for f in findings)
    by_confidence = Counter(f.get("confidence", "") for f in findings)
    by_file = Counter(f.get("file", "") for f in findings)

    out = [f"# Scan of {root}", "",
           f"Generated {_now()} · {len(findings)} finding(s) in "
           f"{len(by_file)} file(s) of {len(files)} read.", "",
           "## This run", ""]
    out += [f"- **{label}:** {value}" for label, value
            in describe(_command_of(args), root, args, language=lang)]
    out += ["", "## What was found", ""]
    if not findings:
        # An empty table reads as a broken report; the sentence reads as an
        # answer. And it is the answer that needs the coverage beside it,
        # which the line above already carries: nothing found *in what*.
        out += ["Nothing. The files above were read and no finding came out "
                "of them - which is a result, not an absence of one.", ""]
    else:
        out += ["| kind | count |", "|---|---|"]
        for kind, count in by_source.most_common():
            out.append(f"| {kind or 'unnamed'} | {count} |")
        out += ["", "| certainty | count |", "|---|---|"]
        for level, count in by_confidence.most_common():
            out.append(f"| {level or 'unstated'} | {count} |")
        out.append("")

    if by_file:
        out += ["## Files, worst first", "", "| file | findings |", "|---|---|"]
        for name, count in by_file.most_common(_PAGES_LISTED):
            out.append(f"| {name} | {count} |")
        rest = len(by_file) - _PAGES_LISTED
        if rest > 0:
            out.append(f"| *and {rest} more* | |")
        out.append("")

    # The findings themselves, worst first and cut off: a briefing is read,
    # and `--json` is the complete list for anything that parses.
    ranked = sorted(findings, key=lambda f: -(f.get("score") or 0))
    if ranked:
        out += ["## Findings, most certain first", ""]
        for finding in ranked[:_FINDINGS_LISTED]:
            where = finding.get("file", "")
            line = finding.get("line") or 0
            out.append(f"- `{where}:{line}` — {finding.get('explanation', '')}")
        rest = len(ranked) - _FINDINGS_LISTED
        if rest > 0:
            out.append(f"- *and {rest} more; `--json` has all of them*")
        out.append("")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(out), encoding="utf-8")
    progress.notice("report", f"report: {path}", human=f"# report: {path}",
                    path=str(path), kind_of="briefing")


#: How many findings a briefing lists before it stops informing.
_FINDINGS_LISTED = 40


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _command_of(args) -> str:
    """Which subcommand produced this document.

    Read off argparse's own `func` default rather than passed in by every
    caller: `p_audit.set_defaults(func=cmd_audit)` already records it, and a
    second place to state it is a second place to get it wrong.
    """
    func = getattr(args, "func", None)
    name = getattr(func, "__name__", "") or ""
    return name[4:] if name.startswith("cmd_") else (name or "scan")


def _write_report(result, args, lang: str, fix_outcome=None, ai_findings=None) -> dict:
    """Write a briefing another tool - or an agent - can act on directly.

    The plain `--json` output is a list of findings, which is the right shape
    for a pipeline and the wrong shape for an agent about to edit the code. An
    agent needs to know where the work is concentrated, which files to open,
    what has already been done to them, and whether the situation is getting
    better or worse. So this is a different document, not a flag on the same
    one.

    Markdown by default because that is what a coding agent reads best; `.json`
    if the suffix asks for it, for anything that would rather parse than read.

    Returns the payload it wrote, so a caller that also needs the grouped
    problems or the run history (the comparison document, for one) reads
    them from here instead of computing them a second time.
    """
    from audit.explanations import render
    from audit.saturation import saturated_rules
    from finding_contract import SCHEMA_VERSION, serialize_finding, serialize_issue

    path = Path(args.report)
    history = _read_history(result.root, result.mode)
    counts = result.counts()
    problems = _problem_map(result, render, lang)
    entry = {
        "at": _now(),
        "root": result.root,
        "mode": result.mode,
        "counts": counts,
        # Recorded per run so the comparison with the previous run can talk
        # about problems solved, not only about rows removed: fixing one
        # shared header takes thirty findings off the total and one problem
        # off this number, and those are two different pieces of news.
        "distinct": len(problems),
        "rules": sorted({p["rule"] for p in problems}),
        # How many places each rule fires in. The per-rule number is what
        # makes "did the last round of work help" answerable: grouping keys
        # on the offending markup, so correcting two of five copies *splits*
        # one group into two and the count of distinct problems goes up
        # while the situation improved. Occurrences per rule only go down
        # when something was actually fixed.
        "rule_counts": {rule: len(issues)
                        for rule, issues in result.by_rule().items()},
        # Rules that *measure* rather than inspect: first paint, load time,
        # page weight, request count. Their number moves between runs because
        # the network did, not because anyone changed the page - so a
        # comparison that counts them as work reports progress nobody made.
        # Recorded per run because it is a property of the engine that
        # produced the finding, and only this run knows that.
        "measured_rules": sorted({
            rule for rule, issues in result.by_rule().items()
            if issues and all(getattr(i, "engine", "") == "browser"
                              for i in issues)}),
        "documents": len(result.documents),
        "fixed": len(fix_outcome.applied) if fix_outcome else 0,
        "report": str(path),
    }

    # AI pattern statistics (only style findings, not typography/characters)
    ai_stats = {}
    typo_stats = {}
    if ai_findings:
        # One owner for "is this about a character or about the wording",
        # and it is `fullscan.is_character_finding`. This was a third copy
        # of that decision and it disagreed with the other two: reading only
        # the explanation, `[invisible] U+00AD SOFT HYPHEN` has neither the
        # word "typography" nor a source to check, so nine invisible
        # characters were reported as AI-written passages at high
        # confidence.
        from cli_impl.fullscan import is_character_finding

        style_findings = []
        typo_findings = []
        for f in ai_findings:
            (typo_findings if is_character_finding(f)
             else style_findings).append(f)

        if style_findings:
            ai_stats = {
                "total": len(style_findings),
                "high": len([f for f in style_findings if f.get("confidence") == "high"]),
                "medium": len([f for f in style_findings if f.get("confidence") == "medium"]),
                "low": len([f for f in style_findings if f.get("confidence") == "low"]),
                "files": len({f.get("file", "") for f in style_findings}),
                "top_patterns": [],
            }
            # Top AI patterns by score
            sorted_findings = sorted(style_findings, key=lambda f: f.get("score", 0), reverse=True)
            for f in sorted_findings[:10]:
                row = {
                    "text": f.get("text", "")[:100],
                    "score": f.get("score", 0),
                    "confidence": f.get("confidence", ""),
                    "explanation": f.get("explanation", "")[:120],
                    "file": f.get("file", ""),
                    "line": f.get("line", 0),
                }
                # Where `--repo` matched this passage to a file - the place
                # an agent about to edit the code should open, not the page
                # it renders on. Absent for a site-only run, which is the
                # ordinary case, not something this summary should imply is
                # missing.
                if f.get("source_file"):
                    row["source_file"] = f["source_file"]
                    row["source_line"] = f.get("source_line", 0)
                ai_stats["top_patterns"].append(row)

        # Typography statistics
        if typo_findings:
            # Group by character type
            by_char = {}
            for f in typo_findings:
                exp = f.get("explanation", "")
                # Extract character name from explanation like "[typography] U+2013 EN DASH -> '-'"
                char_name = exp.split("] ")[-1].split(" ->")[0] if "] " in exp else exp[:50]
                by_char.setdefault(char_name, 0)
                by_char[char_name] += 1
            typo_stats = {
                "total": len(typo_findings),
                "files": len({f.get("file", "") for f in typo_findings}),
                "by_character": dict(sorted(by_char.items(), key=lambda x: -x[1])[:10]),
                "top_examples": [
                    {"text": f.get("text", "")[:80], "explanation": f.get("explanation", "")[:100]}
                    for f in typo_findings[:5]
                ],
            }

    from cli_impl.runheader import describe

    payload = {
        "schema_version": SCHEMA_VERSION,
        "findings": [serialize_issue(issue, source=document.source)
                     for document in result.documents for issue in document.issues],
        "content_findings": [serialize_finding(f) for f in (ai_findings or ())],
        "coverage": getattr(result, "coverage", {}),
        "generated": entry["at"],
        "root": result.root,
        "mode": result.mode,
        # What produced this document: the command and the parameters that
        # changed what it measured. Two reports on one site differ by a
        # factor of three depending on whether the browser ran, and neither
        # of them used to say which one it was. See `cli_impl.runheader`.
        "run": [{"label": label, "value": value} for label, value
                in describe(_command_of(args), result.root, args,
                            language=lang)],
        "summary": {
            "counts": counts,
            "total": sum(counts.values()),
            # The same problem on thirty pages is one problem and thirty
            # places. Both counts are reported; see `_problem_map`.
            "distinct_problems": len(problems),
            "documents": len(result.documents),
            "documents_with_findings": len(result.documents_with_issues()),
            "rules_triggered": len(result.by_rule()),
            # `{platform: findings}` for what the platform emitted itself.
            # Never subtracted from the counts above - the finding is real -
            # but a person triaging needs to know which of it they can act
            # on. See `project_profile.PLATFORM_ASSETS`.
            "platform_owned": _owned_counts(result),
            # A SharePoint run's split of each page: what was audited, by
            # part, and what of Microsoft's markup was left out. Empty for
            # any other run. See `audit.sharepoint_zones.Summary`.
            "sharepoint": dict(getattr(result, "sharepoint", None) or {}),
        },
        # Rules whose findings are spread too evenly across the run to be
        # describing the content. Not removed - a saturated rule is
        # sometimes right - but said out loud, because every large false
        # positive this tool has shipped had exactly this shape. See
        # `audit.saturation`.
        # What the target turned out to be, and the evidence that proved it.
        # For a folder this comes from marker files; for a crawled site, from
        # the served markup - which had no detection at all until now, so a
        # site scan knew nothing about what it was reading while the same
        # project on disk knew everything. See `project_profile`.
        "detected_stacks": _detected_stacks(result),
        "saturated_rules": [
            {"rule": s.rule, "findings": s.findings,
             "documents": s.documents, "documents_total": s.documents_total,
             "note": s.message()}
            for s in saturated_rules(result)
        ],
        # What the image pass reached, and what it did not. The pass reads
        # what a file says about how it was made (IPTC `DigitalSourceType`,
        # PNG generation parameters, a generator's name in EXIF/XMP, a C2PA
        # container marker) and it works under a budget: 40 images, 20 MB.
        # Reporting the findings without the coverage is the one thing that
        # module must not do - an image nobody fetched has not come back
        # clean, it has not come back - and until now `result.media` was
        # written by the pass and read by nobody.
        "media": _media_coverage(result),
        "ai_patterns": ai_stats,
        "typography": typo_stats,
        # Same list as the history entry's, at the top level where
        # `compare_runs` reads this run's half of the question.
        "measured_rules": entry["measured_rules"],
        "history": history + [entry],
        "changed_this_run": _fix_summary(fix_outcome),
        "files": _file_map(result, render, lang),
        "problems": problems,
        "by_rule": [
            {"rule": rule, "count": len(issues),
             "severity": issues[0].severity,
             "category": issues[0].category,
             "title": render(issues[0], lang).title,
             "fix": render(issues[0], lang).fix,
             "where": [f"{i.source}:{i.line}" if i.line else i.source
                       for i in issues[:20]]}
            for rule, issues in result.by_rule().items()
        ],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    else:
        path.write_text(_report_markdown(payload, lang), encoding="utf-8")
    _write_history(result.root, result.mode, history + [entry])
    progress.notice("report", f"report: {path}", human=f"# report: {path}",
                    path=str(path), kind_of="markdown")
    # Handed back so a caller that also writes a comparison document does
    # not have to recompute the grouping and re-read the history.
    return payload


def _fix_summary(fix_outcome) -> dict:
    if fix_outcome is None:
        return {"applied": 0, "files": [], "left_alone": [], "backups": []}
    return {
        "applied": len(fix_outcome.applied),
        "files": list(fix_outcome.files_changed),
        "backups": list(fix_outcome.backups),
        "written_by_model": list(getattr(fix_outcome, "ai_written", [])),
        "left_alone": [
            {"rule": s.rule_id, "where": f"{s.source}:{s.line}" if s.line else s.source,
             "reason": s.reason}
            for s in fix_outcome.skipped
        ],
        "errors": list(fix_outcome.errors),
    }


def _media_coverage(result) -> dict:
    """The image pass's own numbers, or `{}` when no pass ran.

    Kept separate from the findings for the reason `audit.media` states in
    its first paragraph: the absence of provenance means nothing at all - a
    re-save or an upload strips every field - so the count of images read is
    what makes a quiet result readable rather than reassuring.
    """
    scan = getattr(result, "media", None)
    if scan is None:
        return {}
    places = getattr(scan, "places", {}) or {}
    return {
        "found": getattr(scan, "found", 0),
        "read": getattr(scan, "checked", 0),
        # Fetched, then recognised by their bytes as a file already read.
        # Analysed once and reported once; the extra addresses are places.
        "duplicates": getattr(scan, "duplicates", 0),
        "skipped_budget": getattr(scan, "skipped_budget", 0),
        "skipped_too_large": getattr(scan, "skipped_too_large", 0),
        "unreachable": getattr(scan, "unreachable", 0),
        "said_something": len(getattr(scan, "findings", []) or []),
        "places": {source: list(extra) for source, extra in places.items()},
    }


def _file_map(result, render, lang: str) -> list:
    """Every audited file, what is wrong in it, and where exactly."""
    files = []
    for document in result.documents:
        entry = {"source": document.source,
                 "error": document.error or "",
                 "elements_checked": document.elements_checked,
                 "findings": []}
        for issue in document.issues:
            explanation = render(issue, lang)
            entry["findings"].append({
                "rule": issue.rule_id,
                "severity": issue.severity,
                "category": issue.category,
                "line": issue.line,
                "selector": issue.selector,
                "engine": issue.engine,
                "title": explanation.title,
                "found": explanation.found,
                "why": explanation.why,
                "fix": explanation.fix,
                "ready_fix": issue.fix_snippet or "",
                "snippet": issue.snippet,
                # How settled it is, and what it is not. Both were on the
                # window and in the terminal and in neither document a
                # person or an agent is handed: an `advisory` row read as
                # a measured fact, which is the one thing the confidence
                # vocabulary exists to prevent.
                "confidence": getattr(issue, "confidence", ""),
                "caveat": explanation.caveat,
                "confirmed_by": (issue.details or {}).get("also_found_by", []),
                # Empty unless a detected platform emitted this element; see
                # `audit.engine.attribute_ownership`.
                "owner": getattr(issue, "owner", ""),
                # On a SharePoint run: whose part of the page this is
                # (`custom` / `author`) and which part. See
                # `audit.sharepoint_zones`.
                "zone": (issue.details or {}).get("zone", ""),
                "zone_name": (issue.details or {}).get("zone_name", ""),
            })
        files.append(entry)
    return files


#: How many places one grouped problem names in full before the rest become
#: a count. Same reasoning as `report.template._LOCATIONS_SHOWN`.
_PLACES_SHOWN = 15


def _detected_stacks(result) -> list:
    """`[{name, evidence, why, hosted}]` for whatever the target turned out
    to be. Empty is the normal answer for a hand-built site.

    Read from the markup for a crawl and from marker files for a folder,
    because those are the two places the evidence exists. Never guessed: a
    platform is named only when a literal it emits is present.
    """
    import project_profile

    if result.mode == "repo":
        profile = project_profile.detect(result.root)
    else:
        markup = "\n".join(
            (getattr(document, "source", "") or "")
            for document in result.documents)
        # The documents carry addresses, not bodies, by the time the report is
        # written; the crawl attaches what it saw to the result instead.
        markup = getattr(result, "markup_sample", "") or markup
        profile = project_profile.detect_from_markup(markup)
    return [
        {"name": stack.name,
         "evidence": profile.evidence.get(stack.name, ""),
         # The markup carries it or it does not. "WordPress" is a guess
         # someone has to verify; "WordPress 7.1" is a fact they can act on,
         # and it was being detected and then dropped on the floor here.
         "version": profile.versions.get(stack.name, ""),
         "why": stack.why,
         "hosted": bool(getattr(stack, "hosted", False))}
        for stack in profile.stacks
    ]


def _owned_counts(result) -> dict:
    counts: dict = {}
    for issue in result.issues():
        owner = getattr(issue, "owner", "")
        if owner:
            counts[owner] = counts.get(owner, 0) + 1
    return counts


def _problem_map(result, render, lang: str) -> list:
    """Every distinct problem once, with every place it was found.

    The counterpart of `_file_map`, which walks documents and repeats the
    whole finding in each. Both are kept: an agent about to edit files wants
    the file map, and a person reading the report wants to know there is one
    unlabelled search field in a shared header, not thirty of them. See
    `duplicates.group_issues`.
    """
    import duplicates

    issues = [issue for document in result.documents for issue in document.issues]
    problems = []
    for first, others in duplicates.group_issues(issues):
        explanation = render(first, lang)
        problems.append({
            "rule": first.rule_id,
            "severity": first.severity,
            "category": first.category,
            "engine": first.engine,
            "title": explanation.title,
            "found": explanation.found,
            "why": explanation.why,
            "fix": explanation.fix,
            "ready_fix": first.fix_snippet or "",
            "snippet": first.snippet,
            "selector": first.selector,
            "caveat": explanation.caveat,
            # How many independent engines found it. 1 unless the browser
            # pass ran and a second engine corroborated; see
            # `audit.browser._merge_engine_duplicates`. The number a reader
            # triages on before anything else.
            "agreement": (first.details or {}).get("agreement", 1),
            "confidence": getattr(first, "confidence", "exact"),
            "owner": getattr(first, "owner", ""),
            "zone": (first.details or {}).get("zone", ""),
            "zone_name": (first.details or {}).get("zone_name", ""),
            "occurrences": len(others) + 1,
            "places": duplicates.places_of(first, others),
        })
    problems.sort(key=lambda p: (_SEVERITY_ORDER.get(p["severity"], 9),
                                 -p["occurrences"], p["rule"]))
    return problems


#: Worst first. Local to the report writer rather than imported from
#: `audit.base`: this orders a rendered payload, which may have come from a
#: JSON file written by an older version whose vocabulary differed.
_SEVERITY_ORDER = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}


def _problems_section(payload: dict) -> list:
    """The grouped problem list, as markdown lines."""
    problems = payload.get("problems") or []
    if not problems:
        return []
    out = [
        "## Problems, worst and most widespread first",
        "",
        f"{len(problems)} distinct problem(s). A problem found on several "
        f"pages is listed once, with every place it was found.",
        "",
    ]
    for problem in problems:
        times = (f" — {problem['occurrences']}×"
                 if problem["occurrences"] > 1 else "")
        out.append(f"### [{problem['severity']}] {problem['title']}{times}")
        out.append("")
        # The certainty rides on the rule line rather than on its own, and
        # only when it is not `exact`: a briefing where most rows carry a
        # certainty note teaches the reader to skip the note.
        certainty = (f" · certainty {problem['confidence']}"
                     if problem.get("confidence")
                     and problem["confidence"] != "exact" else "")
        out.append(f"- rule: `{problem['rule']}` · {problem['category']} "
                   f"· found by {problem['engine'] or 'static'}{certainty}")
        if problem["found"]:
            out.append(f"- found: {' '.join(problem['found'].split())}")
        if problem["why"]:
            out.append(f"- why: {' '.join(problem['why'].split())}")
        if problem["fix"]:
            out.append(f"- fix: {' '.join(problem['fix'].split())}")
        if problem["ready_fix"]:
            out.append(f"- ready replacement: `{problem['ready_fix'][:200]}`")
        if problem["snippet"]:
            out.append(f"- element: `{problem['snippet'][:200]}`")
        if problem.get("caveat"):
            out.append(f"- note: {' '.join(problem['caveat'].split())}")
        places = problem["places"]
        shown = places[:_PLACES_SHOWN]
        out.append(f"- where ({len(places)}):")
        for place in shown:
            out.append(f"  - {place}")
        if len(places) > len(shown):
            out.append(f"  - and {len(places) - len(shown)} more")
        out.append("")
    return out


def _report_markdown(payload: dict, lang: str) -> str:
    """The same facts, laid out for something that reads rather than parses."""
    summary = payload["summary"]
    counts = summary["counts"]
    files = payload.get("files", [])
    out = [
        f"# Audit of {payload['root']}",
        "",
        f"Generated {payload['generated']} · mode `{payload['mode']}` · "
        f"{summary['documents']} document(s) examined.",
        "",
    ]
    run = payload.get("run") or []
    if payload.get("coverage"):
        from audit.coverage import coverage_summary
        title, text = coverage_summary(payload["coverage"], lang)
        out += [f"## {title}", "", text, ""]
        from audit.vitals import performance_lines
        title, lines = performance_lines(payload["coverage"], lang)
        if lines:
            out += [f"## {title}", ""] + [f"- {line}" for line in lines] + [""]
    mappings = [f.get("mapping") for f in payload.get("content_findings", [])
                if f.get("mapping", {}).get("status") in ("ambiguous", "inferred")]
    if mappings:
        from repo_pairing import mapping_lines
        title = {"uk": "Джерела вебтексту", "it": "Sorgenti del testo web", "en": "Web text sources"}
        out += [f"## {title.get(lang, title['en'])}", ""]
        seen = set()
        for mapping in mappings:
            key = (mapping["status"], tuple((c["file"], c["offset"]) for c in mapping["candidates"]))
            if key in seen:
                continue
            seen.add(key)
            out += [f"- {line}" for line in mapping_lines(mapping, lang)]
            out.append("")
    if run:
        out += ["## This run", ""]
        out += [f"- **{row['label']}:** {row['value']}" for row in run]
        out.append("")

    # The index of what was examined, as a table and worst first.
    #
    # It used to be a numbered list of every page, in reading order, at the
    # top of the briefing: on a 192-page crawl that was 192 lines before the
    # first finding. It is context, not content - so it is a table, the pages
    # carrying the most problems come first, and it is cut off once it stops
    # informing. The full count stays in the heading, because truncating the
    # list must not truncate the fact.
    if files:
        # One row per address, by the same owner the styled report uses:
        # `payload["files"]` is one entry per *document*, which is right for
        # a JSON consumer and wrong for a reader's index. See
        # `report.model.page_index`.
        from report.model import page_index

        ranked = sorted(
            page_index({"source": f.get("source", "") or f.get("url", ""),
                        "findings_count": len(f.get("findings", [])),
                        "error": f.get("error", "")} for f in files),
            key=lambda f: (bool(f.get("error")), -f["findings_count"]))
        out += [
            f"## Pages examined ({len(ranked)})",
            "",
            "| page or file | findings |",
            "|---|---|",
        ]
        for f in ranked[:_PAGES_LISTED]:
            error = f.get("error", "")
            count = f"*error: {error}*" if error else f["findings_count"]
            out.append(f"| {f['source']} | {count} |")
        rest = len(ranked) - _PAGES_LISTED
        if rest > 0:
            out.append(f"| *and {rest} more* | |")
        out.append("")

    # Both numbers, because they answer different questions and reporting
    # only one misleads: "70 findings" reads as seventy pieces of work when
    # it is fourteen problems on five pages, and "14 problems" hides how
    # much of the site each one touches.
    distinct = len(payload.get("problems") or [])
    out += [
        "## Where the work is",
        "",
        "| critical | serious | moderate | minor | total | distinct problems |",
        "|---|---|---|---|---|---|",
        f"| {counts.get('critical', 0)} | {counts.get('serious', 0)} | "
        f"{counts.get('moderate', 0)} | {counts.get('minor', 0)} | "
        f"{summary['total']} | {distinct or summary['total']} |",
        "",
    ]

    # AI patterns section
    ai = payload.get("ai_patterns", {})
    if ai.get("total", 0) > 0:
        out += [
            "## AI-generated text patterns",
            "",
            f"**{ai['total']}** passages flagged across **{ai['files']}** file(s).",
            "",
            "| Confidence | Count |",
            "|---|---|",
            f"| high | {ai.get('high', 0)} |",
            f"| medium | {ai.get('medium', 0)} |",
            f"| low | {ai.get('low', 0)} |",
            "",
        ]
        top = ai.get("top_patterns", [])
        if top:
            out += [
                "### Top AI patterns detected",
                "",
                "| Score | Confidence | Text | Explanation |",
                "|---|---|---|---|",
            ]
            for p in top:
                text = p["text"].replace("|", "\\|")[:80]
                exp = p["explanation"].replace("|", "\\|")[:80]
                out.append(f"| {p['score']:.2f} | {p['confidence']} | {text} | {exp} |")
            out.append("")

    # Typography section
    typo = payload.get("typography", {})
    if typo.get("total", 0) > 0:
        out += [
            "## Typography issues (non-keyboard characters)",
            "",
            f"**{typo['total']}** passages with non-standard characters across **{typo['files']}** file(s).",
            "",
            "### By character type",
            "",
            "| Character | Count |",
            "|---|---|",
        ]
        for char_name, count in typo.get("by_character", {}).items():
            out.append(f"| {char_name} | {count} |")
        out.append("")
        examples = typo.get("top_examples", [])
        if examples:
            out += [
                "### Examples",
                "",
            ]
            for ex in examples:
                text = ex["text"].replace("|", "\\|")[:60]
                exp = ex["explanation"].replace("|", "\\|")[:60]
                out.append(f"- `{text}` — {exp}")
            out.append("")

    # What the image pass read. A section rather than a line, because a
    # quiet result here is the easiest thing in the whole report to
    # misread: no provenance finding is not "the pictures are fine", it is
    # "the files carry no such field", and a budget means some were never
    # opened at all.
    media = payload.get("media") or {}
    if media.get("found"):
        out += [
            "## Image provenance",
            "",
            f"**{media['read']}** of **{media['found']}** image address(es) "
            f"read for what the file says about how it was made: "
            f"**{media['said_something']}** said anything.",
            "",
        ]
        unread = [
            (media.get("skipped_budget", 0), "past the per-run byte budget"),
            (media.get("skipped_too_large", 0),
             "read short of the provenance window"),
            (media.get("unreachable", 0), "could not be fetched"),
        ]
        duplicates = media.get("duplicates", 0)
        if duplicates:
            out.append(f"- **{duplicates}** were the same bytes as a file "
                       f"already read, so they were analysed once")
        for count, why in unread:
            if count:
                out.append(f"- **{count}** {why}")
        if any(count for count, _ in unread):
            out.append("")
        out += [
            "A file that says nothing has said nothing: a screenshot, a "
            "re-save or an upload through most platforms strips every "
            "provenance field. This section reports what the files carry, "
            "never a verdict about the pixels.",
            "",
        ]

    # No comparison section. A report says what is wrong with the page in
    # front of the reader; what changed since Tuesday is a different
    # document and it already exists - `changes.md`, written beside this one
    # in the run folder. Two genres in one file made the first page of a
    # findings report be about the previous run.

    changed = payload.get("changed_this_run") or {}
    if changed.get("applied"):
        out += [
            "## Already corrected in this run",
            "",
            f"{changed['applied']} correction(s) written to "
            f"{len(changed['files'])} file(s). Backups: "
            f"{', '.join(changed['backups']) or 'none'} - `cli.py undo <path>` "
            f"puts every file back.",
            "",
        ]
        if changed.get("written_by_model"):
            out += [
                f"Written by a model, so worth reading before trusting: "
                f"{', '.join(sorted(set(changed['written_by_model'])))}.",
                "",
            ]

    left = [s for s in changed.get("left_alone", [])]
    if left:
        # Without line numbers on purpose. These were recorded before the
        # corrections were written, so their positions have since moved; the
        # file map below is the one that matches the file on disk now, and
        # two sets of line numbers that disagree is worse than one set.
        out += ["## Deliberately not corrected", "",
                "These need a decision rather than an edit. Current positions "
                "are in the file map below.", ""]
        seen = set()
        for item in left[:40]:
            key = (item["rule"], item["reason"])
            if key in seen:
                continue
            seen.add(key)
            source = item["where"].rsplit(":", 1)[0] if ":" in item["where"] else item["where"]
            same = sum(1 for other in left if (other["rule"], other["reason"]) == key)
            count = f" ({same}\u00d7)" if same > 1 else ""
            out.append(f"- `{item['rule']}`{count} in {source} - {item['reason']}")
        out.append("")

    out += ["## By rule, most affected first", "",
            "| rule | severity | count | what to do |", "|---|---|---|---|"]
    for rule in payload["by_rule"]:
        fix = " ".join(rule["fix"].split())[:150]
        out.append(f"| `{rule['rule']}` | {rule['severity']} | {rule['count']} | {fix} |")
    out.append("")

    # One entry per distinct problem, not per (document × problem). A crawl
    # of thirty pages sharing one header used to repeat that header's every
    # fault thirty times, and a list where every row restates the previous
    # one stops being read. The complete per-document map is still in the
    # `.json` form of this report, under `files`, for anything that parses
    # rather than reads.
    problems = _problems_section(payload)
    if problems:
        out += problems
    else:
        out += ["## File map", ""]
        for entry in payload["files"]:
            if entry["error"]:
                out += [f"### {entry['source']}", "",
                        f"Not checked: {entry['error']}", ""]

    unchecked = [e for e in payload["files"] if e["error"]]
    if problems and unchecked:
        out += ["## Not checked", ""]
        for entry in unchecked:
            out.append(f"- {entry['source']} — *{entry['error']}*")
        out.append("")

    out += [
        "## How to act on this",
        "",
        "Corrections marked *ready replacement* are exact: the element they "
        "name can be swapped for the markup given. Everything else is a "
        "decision - describing an image, writing a description - and the "
        "wording matters more than the markup.",
        "",
        "`python cli.py audit <target> --fix` applies the exact ones and keeps "
        "a `.bak` of every file it touches. `--fix --ai` also writes the ones "
        "that need words. `python cli.py undo <path>` reverses either.",
        "",
    ]
    return "\n".join(out)


def compare_runs(payload: dict) -> dict | None:
    """This run against the previous one of the same target, or None.

    Two numbers, not one. **Findings** is how many rows the report has, and
    it moves for reasons that are not progress: crawling five more pages
    raises it, a page that timed out lowers it. **Problems** is how many
    distinct faults were found (see `_problem_map`), and it is the number
    that answers "did we fix anything" - correcting one shared header takes
    thirty findings and exactly one problem off the total.

    Rule identity carries the rest: a rule in the previous run and not in
    this one was *solved*, the other way round is a *regression*, and naming
    them is what makes the comparison actionable rather than a score.
    """
    previous = _previous_run(payload)
    if previous is None:
        return None
    now_counts = {rule["rule"]: rule["count"] for rule in payload.get("by_rule") or []}
    before_counts = dict(previous.get("rule_counts") or {})
    now_rules = set(now_counts) or {p["rule"] for p in payload.get("problems") or []}
    before_rules = set(before_counts) or set(previous.get("rules") or [])
    summary = payload["summary"]
    # A run recorded before rule identity was stored knows only its totals.
    # Comparing rule sets against an empty set would announce every rule as
    # brand new and every count as a regression from zero - a confident lie
    # about a run we simply do not have the detail for. So the per-rule
    # verdicts are withheld, and the totals still compare.
    comparable = bool(before_rules)
    all_moved = [
        {"rule": rule,
         "before": before_counts.get(rule, 0),
         "now": now_counts.get(rule, 0)}
        for rule in sorted(before_rules | now_rules)
        if before_counts.get(rule, 0) != now_counts.get(rule, 0)
    ] if before_counts else []
    # A measurement that moved is not work done. `perf-first-paint` fired on
    # ten pages in one run and none in the next because the second run hit a
    # warm cache - and the document said "11 places corrected", which is the
    # one thing a comparison must never get wrong. Recorded in both runs, so
    # a rule counts as measured if either run said so.
    measured = (set(previous.get("measured_rules") or ())
                | set(payload.get("measured_rules") or ()))
    moved = [m for m in all_moved if m["rule"] not in measured]
    moved_measurements = [m for m in all_moved if m["rule"] in measured]
    return {
        "previous_at": previous.get("at", "?"),
        "at": payload.get("generated", "?"),
        "findings_before": sum((previous.get("counts") or {}).values()),
        "findings_now": summary["total"],
        # `distinct` is absent from runs recorded before it was written;
        # `None` says "not comparable" rather than pretending it was zero.
        "problems_before": previous.get("distinct"),
        "problems_now": summary.get("distinct_problems", 0),
        "solved_rules": sorted(before_rules - now_rules) if comparable else [],
        "new_rules": sorted(now_rules - before_rules) if comparable else [],
        "still_open_rules": sorted(now_rules & before_rules) if comparable
        else sorted(now_rules),
        #: Rules whose number of places changed, in either direction. Empty
        #: for a run recorded before `rule_counts` existed.
        "moved_rules": moved,
        #: Rules that measure rather than inspect, reported apart so their
        #: movement is never counted as work.
        "moved_measurements": moved_measurements,
        "comparable_per_rule": bool(before_counts),
        "comparable_rule_set": comparable,
        "places_fixed": sum(max(0, m["before"] - m["now"]) for m in moved),
        "places_added": sum(max(0, m["now"] - m["before"]) for m in moved),
    }


def runs_open(history: list, rule: str, root: str, mode: str) -> int:
    """How many consecutive runs, ending with the latest, this rule fired in.

    The number the design puts beside a finding that has not moved. It is
    the difference between "this appeared last week" and "this has survived
    six rounds of work", and only the second one is an argument for changing
    how it is being approached.

    Counted backwards from the newest run and stopped at the first run that
    did not have it, so a rule fixed and then broken again reports the
    current streak rather than its whole career. Runs recorded before
    `rule_counts` existed end the streak instead of extending it: they
    cannot say whether the rule fired, and guessing would inflate exactly
    the number that is supposed to be evidence.
    """
    mine = [e for e in history
            if e.get("root") == root and e.get("mode") == mode]
    streak = 0
    for entry in reversed(mine):
        counts = entry.get("rule_counts")
        if not counts or not counts.get(rule):
            break
        streak += 1
    return streak


def comparison_view(payload: dict) -> dict | None:
    """`compare_runs` arranged as the three answers a person asks for.

    What was fixed, what appeared, and what is still there - which is the
    shape of the comparison document and of artboard 3n, and not the shape
    of `compare_runs`, whose job is to be correct rather than readable.

    Rule titles come from this run's `by_rule`, so a rule that stopped
    firing entirely has none: it is not in this run. Those are listed by id
    under `solved`, which is also the more useful fact about them - the
    point is that the rule is gone, not what it used to be called.

    Measurements are kept apart and never counted into either total. A
    `perf-first-paint` that fired on ten pages and then none did not get
    fixed; the second run hit a warm cache.
    """
    comparison = compare_runs(payload)
    if comparison is None:
        return None
    titles = {row["rule"]: row["title"] for row in payload.get("by_rule") or []}
    counts = {row["rule"]: row["count"] for row in payload.get("by_rule") or []}
    where = {row["rule"]: row.get("where") or [] for row in payload.get("by_rule") or []}
    history = payload.get("history") or []
    root, mode = payload.get("root", ""), payload.get("mode", "")

    fixed, appeared = [], []
    for moved in comparison["moved_rules"]:
        rule = moved["rule"]
        delta = moved["now"] - moved["before"]
        row = {"rule": rule, "title": titles.get(rule, rule), "delta": delta}
        if delta < 0:
            fixed.append(row)
        elif delta > 0:
            row["where"] = where.get(rule, [])[:3]
            appeared.append(row)

    # `still_open_rules` means "present in both runs", which includes every
    # rule whose count moved - so a rule fixed from seven places to two was
    # listed as fixed *and* as unchanged. Unchanged has to mean unchanged:
    # the section is read as the list of things the last round of work did
    # not touch, and a rule that moved does not belong on it.
    moved_rules = ({m["rule"] for m in comparison["moved_rules"]}
                   | {m["rule"] for m in comparison["moved_measurements"]})
    still = [{"rule": rule, "title": titles.get(rule, rule),
              "count": counts.get(rule, 0),
              "runs": runs_open(history, rule, root, mode)}
             for rule in comparison["still_open_rules"]
             if rule not in moved_rules]
    # Longest-standing first: a rule that has survived six rounds of work is
    # the one worth talking about, and sorting by count would put a fresh
    # thirty-place rule above it.
    still.sort(key=lambda row: (-row["runs"], -row["count"], row["rule"]))

    return {
        "target": root,
        "before_at": comparison["previous_at"],
        "now_at": comparison["at"],
        "findings_before": comparison["findings_before"],
        "findings_now": comparison["findings_now"],
        "fixed": {"places": comparison["places_fixed"],
                  "rules": sorted(fixed, key=lambda r: r["delta"]),
                  "solved": comparison["solved_rules"]},
        "appeared": {"places": comparison["places_added"],
                     "rules": sorted(appeared, key=lambda r: -r["delta"]),
                     "new": comparison["new_rules"]},
        "unchanged": {"places": sum(row["count"] for row in still),
                      "rules": still},
        "measurements": comparison["moved_measurements"],
        "comparable_per_rule": comparison["comparable_per_rule"],
    }


def _direction(before: int, now: int) -> str:
    if now < before:
        return f"down {before - now}"
    if now > before:
        return f"up {now - before}"
    return "unchanged"


def _comparison_lines(comparison: dict) -> list:
    """The comparison as markdown lines, shared by the report section and
    the standalone comparison document."""
    out = [
        f"Previous run {comparison['previous_at']} · this run "
        f"{comparison['at']}.",
        "",
        "| | previous | now | change |",
        "|---|---|---|---|",
        f"| findings | {comparison['findings_before']} | "
        f"{comparison['findings_now']} | "
        f"{_direction(comparison['findings_before'], comparison['findings_now'])} |",
    ]
    out.append("")
    # `distinct_problems` deliberately does not appear here. Grouping keys on
    # the offending markup, so correcting two of five copies of one bad
    # image splits one group into two: the count of distinct problems rises
    # while the site got better. It is an honest number for "how much is
    # there to read" and a misleading one for "did we make progress", and a
    # progress table is exactly the wrong place for it. Progress is the
    # per-rule table below.

    if comparison["comparable_per_rule"]:
        out += [
            f"**{comparison['places_fixed']} place(s) corrected**, "
            f"{comparison['places_added']} new one(s) appeared.",
            "",
        ]

    solved, appeared = comparison["solved_rules"], comparison["new_rules"]
    if solved:
        out += [f"**Gone entirely ({len(solved)}):** "
                + ", ".join(f"`{rule}`" for rule in solved), ""]
    if appeared:
        out += [f"**New since last run ({len(appeared)}):** "
                + ", ".join(f"`{rule}`" for rule in appeared), ""]

    moved = comparison["moved_rules"]
    if moved:
        out += [
            "### What moved, by rule",
            "",
            "| rule | previous | now | change |",
            "|---|---|---|---|",
        ]
        # Biggest improvement first: the point of the table is what the last
        # round of work achieved, not an alphabet.
        for row in sorted(moved, key=lambda r: (r["now"] - r["before"], r["rule"])):
            out.append(f"| `{row['rule']}` | {row['before']} | {row['now']} | "
                       f"{_direction(row['before'], row['now'])} |")
        out.append("")
    elif comparison["comparable_per_rule"]:
        # Qualified when a measurement moved: "every rule fires in exactly as
        # many places" would be read as "nothing changed at all", and the
        # table below it would then look like a contradiction.
        out += ["Every rule that inspects the page fires in exactly as many "
                "places as last time: nothing was corrected and nothing "
                "regressed."
                if comparison.get("moved_measurements") else
                "Every rule fires in exactly as many places as last time: "
                "nothing was corrected and nothing regressed.", ""]
    elif not comparison["comparable_rule_set"]:
        out += ["The previous run recorded only its totals, not which rules "
                "fired, so what was solved and what appeared cannot be named "
                "for this comparison. The next one will have both.", ""]
    elif not solved and not appeared:
        out += ["The same rules fire as last time.", ""]

    measured = comparison.get("moved_measurements") or []
    if measured:
        out += [
            "### Measurements that moved",
            "",
            "These are timings and weights taken while the page loaded, not "
            "facts about the page. They move because the network did, so "
            "they are listed apart and are **not** counted as corrections.",
            "",
            "| rule | previous | now | change |",
            "|---|---|---|---|",
        ]
        for row in sorted(measured,
                          key=lambda r: (r["now"] - r["before"], r["rule"])):
            out.append(f"| `{row['rule']}` | {row['before']} | {row['now']} | "
                       f"{_direction(row['before'], row['now'])} |")
        out.append("")

    still = comparison["still_open_rules"]
    if still:
        out += [f"**Still open ({len(still)}):** "
                + ", ".join(f"`{rule}`" for rule in still), ""]
    return out


def write_comparison_document(path, payload: dict) -> bool:
    """The comparison as a document of its own, next to the report.

    Separate from the report on purpose: the report answers "what is wrong
    now", and the question a second run actually asks is "what did the last
    round of work change". Two questions, two documents. Returns False -
    writing nothing - when there is no previous run to compare against, so
    a first run leaves no empty file behind.
    """
    comparison = compare_runs(payload)
    if comparison is None:
        return False
    path = Path(path)
    lines = [
        f"# What changed for {payload.get('root', '')}",
        "",
    ] + _comparison_lines(comparison) + [
        "## How to read this",
        "",
        "*Findings* counts rows in the report; it also moves when the crawl "
        "reaches a different number of pages, which is not progress. "
        "*Places corrected* and the per-rule table are the numbers that "
        "track work done: a rule fires in fewer places only when something "
        "was actually fixed.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    progress.notice("report", f"comparison: {path}",
                    human=f"# comparison: {path}",
                    path=str(path), kind_of="comparison")
    return True


def _previous_run(payload: dict) -> dict | None:
    """The last run of *this* target, or None if there was not one.

    The history file lives beside the report, so pointing `--report` at one
    path while scanning different things put unrelated runs in one list, and
    the comparison then read the count of another target as progress on this
    one - a run over a clean file announced "8 finding(s). Now 0 - down"
    because the previous entry was a different root. Matching on root and mode
    is what makes the sentence true: an audit and a text scan of the same
    directory count different things and are not each other's history either.
    """
    history = payload.get("history") or []
    root, mode = payload.get("root"), payload.get("mode")
    mine = [e for e in history[:-1]
            if e.get("root") == root and e.get("mode") == mode]
    return mine[-1] if mine else None


#: Rows of the page index before the briefing cuts it short. Long enough to
#: be useful on an ordinary site, short enough that a large crawl does not
#: bury the findings under its own table of contents.
_PAGES_LISTED = 40


def _history_dir() -> Path:
    """Where run history lives: `~/.xanalyze/history/`.

    Not `.xanalyze/` in the working directory, which is where this used to
    live. Two reasons, both found by running the tool:

    * A run started from a different folder saw no history at all, so the
      comparison silently disappeared depending on where the terminal
      happened to be.
    * The history of a *website* has no working directory to belong to.

    The legacy location is still read - see `_legacy_history` - so runs
    recorded before this change keep counting.
    """
    d = Path.home() / ".xanalyze" / "history"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def _history_key(root: str, mode: str) -> str:
    """Identity of a run series: what was scanned, and which analysis.

    Keyed on the *target*, not on the report path. The report path used to
    be the key, and `fullscan` puts a timestamp in the file name it
    generates - so every run produced a new key, every history read came
    back empty, and the "since the last run" comparison never once appeared
    in a default fullscan. An audit and a text scan of the same folder count
    different things, so `mode` is part of the identity too.
    """
    import hashlib
    return hashlib.md5(f"{root}|{mode}".encode()).hexdigest()[:12]


def _legacy_history(root: str, mode: str) -> list:
    """Entries for this target recorded under the old `.xanalyze/` scheme.

    Read once per run and merged in, so the runs already on disk - keyed by
    report path, one file per run - are not lost. Each file is filtered by
    root and mode because the old key said nothing about either.
    """
    legacy_dir = Path.cwd() / ".xanalyze"
    if not legacy_dir.is_dir():
        return []
    found: list = []
    for path in legacy_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, list):
            continue
        found.extend(e for e in data if isinstance(e, dict)
                     and e.get("root") == root and e.get("mode") == mode)
    return found


def _read_history(root: str, mode: str) -> list:
    history_path = _history_dir() / f"{_history_key(root, mode)}.json"
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = []
    entries = data if isinstance(data, list) else []
    known = {(e.get("at"), e.get("root"), e.get("mode"))
             for e in entries if isinstance(e, dict)}
    for entry in _legacy_history(root, mode):
        stamp = (entry.get("at"), entry.get("root"), entry.get("mode"))
        if stamp not in known:
            known.add(stamp)
            entries.append(entry)
    entries.sort(key=lambda e: e.get("at") or "")
    return entries


def _write_history(root: str, mode: str, history: list) -> None:
    history_path = _history_dir() / f"{_history_key(root, mode)}.json"
    try:
        history_path.write_text(
            json.dumps(history[-20:], ensure_ascii=False, indent=2),
            encoding="utf-8")
    except OSError:
        pass


def _now() -> str:
    # Seconds included: history is sorted on this string, and two runs
    # started in the same minute (a re-run right after a fix - the common
    # case) were indistinguishable without them, so "previous run" could
    # name either of the two.
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
