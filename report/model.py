"""The one shape `template.py` renders from.

Two very different analyses feed a styled report — the AI-text pass
(`AnalysisResult` / `RepoAnalysisResult`, scoring `TextSpan`s as a
probability) and the site audit (`AccessibilityResult`, reporting `Issue`s
as facts with a severity). They disagree about almost everything: one has a
0..1 score and a detector name, the other has a fixed severity vocabulary
and a WCAG reference. Rather than let the template know both, each source
gets its own adapter function here (`from_text_analysis` /
`from_accessibility`) that flattens it into one `ReportModel` of
`ReportFinding`s. The template — and the PDF renderer behind it — reads only
that, so it has exactly one shape to lay out regardless of which mode
produced it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from models import AnalysisResult, CodeBlock, Confidence

#: The category a text-mode finding is filed under. Kept distinct from the
#: audit categories (`audit.base.CATEGORIES`) rather than folded into
#: "best-practices": an AI-sounding sentence and a missing `alt` are not the
#: same kind of problem, and a report that mixed them under one label would
#: hide which pass found what.
CATEGORY_AI_TEXT = "ai-text"

#: Two severity vocabularies exist in this codebase and both reach the
#: report unchanged (`Confidence.value` for text, `Issue.severity` for
#: audit) — rewriting one to match the other would lose information the
#: source truly has. This is the shared ordering used to sort a mixed list
#: and to pick a display colour; lower is worse. Unknown values sort last
#: rather than raising, so a future severity name still renders (just
#: unordered) instead of breaking the report.
SEVERITY_RANK = {
    "critical": 0, "serious": 1, "moderate": 2, "minor": 3,
    "high": 0, "medium": 1, "low": 2,
}


def page_index(rows) -> list:
    """One row per address, for the page index both reports print.

    A page produces several documents - its own rules, its response headers,
    the provenance of an image on it - and the index is a reader's list of
    *pages*. Printed straight from the documents it showed the same URL two
    or three times with different counts, which reads as three pages that
    disagree rather than one page counted in parts.

    Rows are `{"source", "findings_count", "error"}`; counts add up and the
    first error on an address is the one kept.
    """
    merged = {}
    for row in rows:
        source = row.get("source", "")
        into = merged.setdefault(source, {"source": source,
                                          "findings_count": 0, "error": ""})
        into["findings_count"] += int(row.get("findings_count") or 0)
        into["error"] = into["error"] or (row.get("error") or "")
    return list(merged.values())


@dataclass
class ReportFinding:
    """One row in the report, whichever pass produced it."""
    title: str
    category: str
    severity: str
    location: str
    #: What was found, plain text (a code/markup snippet is shown separately
    #: in `snippet`, so this stays a short human sentence).
    found: str = ""
    why: str = ""
    fix: str = ""
    #: The offending markup or the flagged passage, verbatim. Rendered as
    #: text in a monospace block by the template, never as markup — see
    #: `template.py`'s escaping.
    snippet: str = ""
    #: The ready replacement, when one exists: `Issue.fix_snippet` for an
    #: audit finding, an AI-rewritten draft or the exact character
    #: correction for a text finding. Empty when the correction needs a
    #: human decision.
    replacement: str = ""
    #: Which engine or detector produced this: "static" / "axe" / "htmlcs"
    #: for audit, the detector name for text.
    engine: str = ""
    wcag: tuple = ()
    #: Every place this same problem was found, `location` included and
    #: first. Filled by `ReportModel.grouped_findings`; empty on an
    #: ungrouped finding, where `location` alone is the answer.
    locations: list = field(default_factory=list)
    #: The platform that emitted the element, when one did - so the branded
    #: report says which rows are not the reader's to fix. Empty is the
    #: author's own markup, which is most of them.
    owner: str = ""
    #: Whose part of a SharePoint page this is: `custom` (an SPFx part or a
    #: placeholder) or `author` (what the page's author wrote), and the
    #: part's name. Empty on any other run. Microsoft's own zone never
    #: appears here: it is not audited. See `audit.sharepoint_zones`.
    zone: str = ""
    zone_name: str = ""
    #: How many independent engines found this. 1 unless the browser pass ran
    #: and a second engine corroborated; the number the JSON already carried
    #: and the printed report did not.
    agreement: int = 1
    #: How settled the finding is: `exact`, `advisory` or `needs-browser`
    #: (`audit.base`'s confidence vocabulary). Empty for a text finding,
    #: which has a score instead.
    #:
    #: It reached the window and the terminal and stopped there. The whole
    #: point of the confidence levels is that an `advisory` finding is a
    #: judgement call and an `exact` one is not - and the two documents a
    #: person actually hands on, the styled report and the agent briefing,
    #: printed them as the same kind of claim.
    confidence: str = ""
    #: The sentence that says what this finding is *not*: "an engine could
    #: not decide this, open it in a browser", "nothing will check this for
    #: you". Written by `audit.explanations.render` and, until now, dropped
    #: on the floor by both report adapters.
    caveat: str = ""
    #: The engine's own identifier for the check, e.g. `axe:button-name`.
    #: Printed as-is beside the engine name: it is what a reader searches
    #: for, what a suppression list names, and what two runs are compared
    #: on. It was in the JSON and nowhere in the document a person reads.
    rule_id: str = ""
    #: The HTML element this finding is about, lowercased, or `""` when the
    #: finding is not about one (a passage of prose, a response header, a
    #: page-level rule). Read off the markup the engine quoted rather than
    #: guessed from the selector - see `report.markup.element_of` - and used
    #: to ink the finding by role.
    element: str = ""
    #: What the document this came from is: "page", "fragment" or "email".
    #: Carried per finding rather than per document because the report groups
    #: by it - "this is an email, and these three things matter in Outlook"
    #: is a different sentence from "this page has 23 problems", and the
    #: reader needs the first one before the second.
    document_kind: str = ""
    #: Detached machine evidence from the shared finding contract. Display
    #: prose and grouping never replace the source facts or span offsets.
    evidence: dict = field(default_factory=dict)

    @property
    def severity_rank(self) -> int:
        return SEVERITY_RANK.get(self.severity, 9)

    @property
    def occurrences(self) -> int:
        """How many places this problem was found in - 1 when ungrouped."""
        return max(1, len(self.locations))

    @property
    def identity(self) -> tuple:
        """What makes two findings the same problem in different places.

        Everything the reader would compare *except* where it is. Two pages
        missing a meta description produce the same title, the same
        explanation and the same (empty) markup, so they are one problem
        with two places; two different images missing `alt` differ in
        `snippet` and stay two problems.

        The snippet is compared with generated identifiers masked, the same
        way `duplicates.issue_identity` compares it, and for the same reason
        that function already documents: a theme that stamps a unique id into
        a component - WordPress writes `aria-controls="page-toc-panel-6a8c2c05ce8bd"`
        - produces markup that differs on every page while describing one bug
        in one template.

        It was not masked here, and that mattered, because this is the
        identity behind the *branded* report - the PDF a person reads. On a
        three-page crawl of a real WordPress site the two groupings disagreed
        (374 problems here against 369 there) over the same 552 occurrences,
        and the human-facing half was the one inflating. The audit-facing
        half had been protected against exactly this since the function was
        written.

        The rule id joins it now that the document *prints* the rule id.
        Two checks can produce the same sentence - `axe` and HTML_CodeSniffer
        both say a contrast is too low - and a group that merged them would
        show one id above occurrences the other found, which is a printed
        fact that is wrong for half its rows.
        """
        from duplicates import mask_generated_ids
        import json

        return (self.category, self.severity, self.rule_id, self.confidence,
                self.zone, self.zone_name,
                self.title, self.found, self.why, self.fix,
                mask_generated_ids(" ".join((self.snippet or "").split())),
                self.replacement, self.engine, self.wcag,
                json.dumps((self.evidence or {}).get("mapping", {}), sort_keys=True))


@dataclass
class ReportMeta:
    target: str
    #: "text-web" | "text-repo" | "audit-web" | "audit-repo" | "audit-file"
    mode: str
    #: `[(label, value)]` describing the run that produced this document -
    #: the command and the parameters that changed what it measured. Empty
    #: when the caller did not say, which is honest: a document that does
    #: not know how it was produced should not invent an answer. See
    #: `cli_impl.runheader`.
    run: list = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    generator: str = "XAnalyze"
    #: The checkout behind the target, when the run knew of one (`--repo`, or
    #: the folder whose dev server is being read). It is what names a run
    #: against `http://127.0.0.1:5173/`: an address like that identifies a
    #: port on this machine and nothing else, and a report headed by it is
    #: unrecognisable a week later.
    repo: str = ""


def display_name(target: str, repo: str = "") -> str:
    """The short name this run should be called by.

    The heading used to be the raw target, so a report was headed
    `/Users/vlad/repositories/ai-content-scanner/simulations/mixed-problems`
    - a line that wraps to three, says almost nothing at a glance, and is
    mostly somebody's home directory. The full target does not disappear; it
    moves to the line under the heading, where a path belongs.

    A local address is the case that needs `repo`: `127.0.0.1:5173` names a
    port, and the thing being audited is the checkout serving it.
    """
    from urllib.parse import urlparse

    text = (target or "").strip()
    if not text:
        return ""
    if text.startswith(("http://", "https://")):
        host = urlparse(text).hostname or text
        local = (host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
                 or host.startswith("192.168.") or host.startswith("10."))
        if local and repo:
            return Path(repo.rstrip("/")).name or host
        return host
    name = Path(text.rstrip("/")).name
    return name or text


@dataclass
class ReportModel:
    """Everything `template.render_html` needs, and nothing it has to guess."""
    meta: ReportMeta
    findings: list[ReportFinding] = field(default_factory=list)
    pages: list = field(default_factory=list)          # [{source, findings_count, error}]
    ai_patterns: dict = field(default_factory=dict)     # {total, high, medium, low, files, top_patterns}
    typography: dict = field(default_factory=dict)      # {total, files, by_character, top_examples}
    #: What stood in front of the site: `{blocked, pages, whole, rows}`, where
    #: a row is `{signal, count, addresses}`. Empty when nothing was walled,
    #: which is nearly always. It is in the report and not only in the
    #: terminal because the report is the artefact somebody hands to somebody
    #: else, and "40 pages, 3 findings" over a login form is the one sentence
    #: in it that would be a lie.
    auth: dict = field(default_factory=dict)
    coverage: dict = field(default_factory=dict)
    #: A SharePoint run's split: `audit.sharepoint_zones.Summary.as_dict()`.
    #: Empty for any other run, and then the template prints nothing.
    sharepoint: dict = field(default_factory=dict)

    def counts_by_severity(self) -> dict:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts

    def counts_by_title(self, limit: int = 8) -> list:
        """The problems that repeat most, worst first.

        This is the view a person schedules work from: "fifty missing `alt`
        attributes" is one job, and a report that only shows severity and
        category cannot say which job. Grouped rows, not raw findings, so a
        header repeated on thirty pages counts once per place rather than
        thirty times per page.
        """
        counts: dict = {}
        for finding in self.grouped_findings():
            key = (finding.title, finding.severity)
            # A grouped row carries every place it was seen at, so the count
            # is places rather than rows: one header repeated on thirty pages
            # is thirty jobs' worth of nothing and one job's worth of work,
            # and the number a reader schedules by is how many places a fix
            # has to visit.
            counts[key] = counts.get(key, 0) + max(1, len(finding.locations or []))
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0][0]))
        return [(title, severity, count)
                for (title, severity), count in ranked[:limit]]

    def counts_by_place(self, limit: int = 8) -> list:
        """Where the findings are, worst page first.

        The pages table lists every page examined; this answers a different
        question - which of them to open first.
        """
        counts: dict = {}
        for finding in self.findings:
            place = finding.location or ""
            if place:
                counts[place] = counts.get(place, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:limit]

    def counts_by_category(self) -> dict:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.category] = counts.get(finding.category, 0) + 1
        return counts

    def sorted_findings(self) -> list:
        """Worst first, then grouped by category, then by where it is —
        so two findings in the same file sit next to each other."""
        return sorted(self.findings,
                      key=lambda f: (f.severity_rank, f.category, f.location))

    def grouped_findings(self) -> list:
        """The same findings, with one row per distinct problem.

        A crawl of thirty pages that share a header reports the header's
        every fault thirty times. Thirty identical cards is not thirty times
        the information — it is the same card, and a reader stops reading a
        list where every row repeats the previous one. So identical findings
        collapse into one, carrying the full list of places in `locations`,
        and nothing is lost: every address a fix has to visit is still named.

        Ordering follows `sorted_findings`, and the collapsed row keeps the
        first place it was seen at as its own `location`, so a grouped report
        and an ungrouped one open on the same finding.
        """
        from dataclasses import replace

        grouped: dict = {}
        order: list = []
        for finding in self.sorted_findings():
            key = finding.identity
            if key in grouped:
                where = finding.location
                if where and where not in grouped[key]:
                    grouped[key].append(where)
                continue
            grouped[key] = [finding.location] if finding.location else []
            order.append((key, finding))
        return [replace(first, locations=grouped[key]) for key, first in order]

    def first_things(self, per_kind: int = 3) -> list:
        """What to do first, per kind of document, rather than what is wrong.

        A run over a folder of deliverables answers a question nobody asked:
        it says "820 findings". Measured on `~/repositories/VSC`, a workspace
        of newsletters, landing pages and exported layouts, the top of that
        list is six page-level SEO rules repeated across 93 documents - true,
        uniform, and useless as a place to start.

        What a person can act on is the other shape of the same data: this
        is an email, and these three things break it in Outlook; this is a
        page, and these three are worth an hour. So the findings are grouped
        by what the document *is* and ranked inside each group by
        consequence - severity first, then how many distinct places it has,
        because a serious fault in one file outranks a minor one in forty.

        Returns `[(kind, [(finding, places), ...]), ...]`, worst kind first.
        Empty when nothing recorded a kind, which is what an older report or
        a text-only run looks like; the section then does not render at all.
        """
        # Counted from the ungrouped findings on purpose. `grouped_findings`
        # collapses one problem across the whole run, and one problem really
        # can appear in two kinds of document at once - the same missing
        # `alt` in a page and in a component. Collapsing first attributes the
        # whole pile to whichever kind happened to be seen first, which is
        # how "no h1" arrived under Emails with a count of 34.
        buckets: dict = {}
        for finding in self.sorted_findings():
            kind = finding.document_kind
            if not kind:
                continue
            bucket = buckets.setdefault(kind, {})
            key = (finding.title, finding.rule_id)
            first, places = bucket.get(key, (finding, set()))
            places = set(places)
            places.add(finding.location)
            bucket[key] = (first, places)
        buckets = {kind: {key: (first, len(places))
                          for key, (first, places) in bucket.items()}
                   for kind, bucket in buckets.items()}
        ranked = []
        for kind, bucket in buckets.items():
            rows = sorted(bucket.values(),
                          key=lambda pair: (pair[0].severity_rank, -pair[1]))
            ranked.append((kind, rows[:per_kind]))
        # Worst kind first, by the worst thing in it: the reader opens on the
        # group that has the most serious single finding, not on whichever
        # kind happens to have the most documents.
        ranked.sort(key=lambda item: (item[1][0][0].severity_rank
                                      if item[1] else 99))
        return [(kind, rows) for kind, rows in ranked if rows]

    def counts_by_severity_grouped(self) -> dict:
        """`counts_by_severity`, counting each distinct problem once."""
        counts: dict = {}
        for finding in self.grouped_findings():
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts


# --------------------------------------------------------------- text mode

def _text_location(block) -> str:
    if isinstance(block, CodeBlock):
        return f"{block.file_path}:{block.line_number}"
    return getattr(block, "page_url", "")


#: The category a character/typography finding is filed under. Separate from
#: `CATEGORY_AI_TEXT` for the same reason that one is separate from the audit
#: categories: a curly quote and a sentence that reads like a model wrote it
#: are different problems with different fixes, and a summary that merges
#: them cannot say which pass did the work.
CATEGORY_TYPOGRAPHY = "typography"


def from_finding_dicts(findings, target: str | None = None,
                       character_of=None) -> ReportModel:
    """A `ReportModel` from the plain dicts `fullscan` already has.

    `from_text_analysis` needs live `TextSpan` and block objects. `fullscan`
    does not have them by the time it writes reports - the checkpoint keeps
    the public dicts, because spans hold detector objects that do not
    survive JSON - so it passed a stand-in whose `spans` was permanently
    `[]`. Every content finding was dropped on the floor: the styled report's
    cards, its two charts and its finding list counted the audit only, while
    the sections below them, filled from the same dicts by a different route,
    listed the AI patterns and the characters. Measured 2026-09-02 on
    `simulations/mixed-problems`: 18 findings in the summary, 33 in the run.

    So this reads the dicts directly. It is the shorter path anyway - the
    dict already carries the file, the line, the text, the explanation and
    the replacement - and it cannot silently produce nothing, because there
    is no object graph to be missing.
    """
    # `character_of` is a parameter and not an import: the predicate lives in
    # `cli_impl.fullscan`, which imports this module, and reaching back for
    # it would make the two modules import each other. The caller that owns
    # the answer passes it.
    is_character_finding = character_of or (lambda _finding: False)
    from finding_contract import serialize_finding

    rows: list[ReportFinding] = []
    for finding in findings or ():
        text = finding.get("text", "") or ""
        title = " ".join(text.split())
        if len(title) > 90:
            title = title[:89] + "…"
        line = finding.get("line")
        path = finding.get("file", "") or finding.get("source", "") or ""
        location = f"{path}:{line}" if path and line else (path or "")
        replacement = finding.get("replacement")
        character = is_character_finding(finding)
        rows.append(ReportFinding(
            title=title or "(empty match)",
            category=CATEGORY_TYPOGRAPHY if character else CATEGORY_AI_TEXT,
            severity=finding.get("confidence", "") or "medium",
            location=location,
            found=title,
            why=(finding.get("explanation")
                 or finding.get("offline_explanation", "") or ""),
            fix=replacement or "",
            snippet=text,
            replacement=replacement or "",
            engine=finding.get("detector", "") or finding.get("source", ""),
            evidence=serialize_finding(finding),
        ))
    return ReportModel(meta=ReportMeta(target=target or "", mode="text-repo"),
                       findings=rows)


def from_text_analysis(result, target: str | None = None,
                       drafts: dict | None = None) -> ReportModel:
    """Build a `ReportModel` from `AnalysisResult` (web) or
    `RepoAnalysisResult` (repo) — the AI-text scan.

    `drafts` mirrors the UI's `self.drafts`: `{(block_id, start, end): text}`,
    the rewritten replacement a person or the AI-rewrite pass produced for a
    span. Optional because a bare CLI scan has none — every finding then
    reports its exact character correction (when the character pass has one)
    and otherwise leaves `replacement` empty, same as `--json` does today.
    """
    drafts = drafts or {}
    from finding_contract import serialize_span
    blocks_by_id = {b.block_id: b for b in result.blocks()}
    findings: list[ReportFinding] = []
    for span in result.spans:
        if span.confidence == Confidence.LOW:
            continue
        block = blocks_by_id.get(span.block_id)
        if block is None:
            continue
        original = block.text[span.start:span.end]
        draft = drafts.get((block.block_id, span.start, span.end), "")
        title = " ".join(original.split())
        if len(title) > 90:
            title = title[:89] + "…"
        findings.append(ReportFinding(
            title=title or "(empty match)",
            category=CATEGORY_AI_TEXT,
            severity=span.confidence.value,
            location=_text_location(block),
            found=title,
            why=span.explanation,
            fix=draft,
            snippet=original,
            replacement=draft or (span.replacement or ""),
            engine=(span.details or {}).get("source") or span.detector_name,
            evidence=serialize_span(span, block),
        ))
    root = target or getattr(result, "root_url", None) or getattr(result, "root_dir", "")
    mode = "web" if isinstance(result, AnalysisResult) else "repo"
    return ReportModel(meta=ReportMeta(target=root or "", mode=f"text-{mode}"),
                       findings=findings)


# ------------------------------------------------------------ audit mode

def from_accessibility(result, lang: str = "uk") -> ReportModel:
    """Build a `ReportModel` from an `AccessibilityResult` — the site audit.

    Explanations come from `audit.explanations.render`, the same function
    the window and `cli.py --report` already call, so the wording a person
    reads in the styled report matches every other surface exactly.
    """
    from audit.explanations import render
    from report.markup import element_of
    from finding_contract import json_value, serialize_issue

    findings: list[ReportFinding] = []
    for document in result.documents:
        for issue in document.issues:
            explanation = render(issue, lang)
            if issue.line:
                where = f"line {issue.line}"
            else:
                where = issue.selector or ""
            location = f"{document.source} — {where}" if where else document.source
            findings.append(ReportFinding(
                title=explanation.title,
                category=issue.category,
                severity=issue.severity,
                location=location,
                found=explanation.found,
                why=explanation.why,
                fix=explanation.fix,
                snippet=issue.snippet,
                replacement=issue.fix_snippet or "",
                engine=issue.engine,
                wcag=explanation.wcag,
                owner=getattr(issue, "owner", ""),
                zone=(issue.details or {}).get("zone", "") or "",
                zone_name=(issue.details or {}).get("zone_name", "") or "",
                agreement=(issue.details or {}).get("agreement", 1),
                element=element_of(issue.snippet, issue.selector),
                rule_id=issue.rule_id,
                confidence=getattr(issue, "confidence", ""),
                caveat=explanation.caveat,
                document_kind=getattr(document, "kind", ""),
                evidence=serialize_issue(issue, source=document.source),
            ))
    return ReportModel(meta=ReportMeta(target=result.root, mode=f"audit-{result.mode}"),
                       findings=findings, auth=_auth_summary(result),
                       coverage=json_value(getattr(result, "coverage", {})),
                       sharepoint=dict(getattr(result, "sharepoint", None) or {}))


def _auth_summary(result) -> dict:
    """`AccessibilityResult.auth` as the flat shape a template renders."""
    report = getattr(result, "auth", None)
    if report is None or not report.blocked:
        return {}
    rows = []
    for signal, walls in sorted(report.by_signal().items()):
        rows.append({
            "signal": signal,
            "count": len(walls),
            "addresses": [wall.url for wall in walls[:5]],
            "detail": walls[0].detail,
        })
    return {"blocked": report.blocked, "pages": report.pages_read,
            "whole": report.whole_site, "rows": rows}
