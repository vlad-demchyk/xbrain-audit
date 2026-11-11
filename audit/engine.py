"""Runs the accessibility rules over a crawled site or a local folder.

The two sources differ in exactly two ways, and both are handled by the
context rather than by the rules: a page locates an element by CSS path, a
file locates it by line number. Everything else — parsing, rule order,
de-duplication, the result shape — is shared, which is what keeps the rules
from having to know which mode they are in.

Same-domain crawling is not re-implemented here: `crawler.crawl` already
walks to a depth and refuses to leave the domain, and this runs over what it
returned. That is the point of reusing it — the rule holds for both modes of
the app because there is only one crawler.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import re
from pathlib import Path, PurePath

from bs4 import BeautifulSoup

import applog
import progress
from project_profile import looks_generated

from . import environment, medium
from .base import (
    SEVERITY_ORDER, Issue, RuleContext, RuleRegistry,
    remember_source, resolve_bound_attributes, resolve_text_directives,
    unwrap_template_text,
)


@dataclass
class DocumentReport:
    """Findings for one page or one file, plus what was actually examined."""
    source: str
    issues: list = field(default_factory=list)
    error: str | None = None
    elements_checked: int = 0
    #: What this document *is*, which decides what advice makes sense about
    #: it: "page" for a finished document, "fragment" for a piece of one, and
    #: "email" for a page a mail client renders. One word rather than the two
    #: fields that produced it, because that is how a reader thinks about it -
    #: and because a report that says "23 things wrong" is far less useful
    #: than one that says "this is an email, and three of those matter in
    #: Outlook".
    kind: str = "page"
    checks: list = field(default_factory=list)
    content_hash: str = ""

    def by_severity(self) -> dict:
        out = {level: [] for level in SEVERITY_ORDER}
        for issue in self.issues:
            out.setdefault(issue.severity, []).append(issue)
        return out


@dataclass
class AccessibilityResult:
    """A whole run: every document, and the roll-up the report needs."""
    root: str
    mode: str = "web"          # "web" | "repo" | "file"
    documents: list = field(default_factory=list)
    rules_run: list = field(default_factory=list)
    #: What the media pass reached, when one ran. An image nobody fetched
    #: has not come back clean - it has not come back - and without these
    #: counts the run has no way to say so.
    media: object = None
    #: What the repository said about itself, when it was asked. Carries the
    #: reason git could not answer, which is the difference between "no
    #: assistant commits" and "no history to look at".
    repo: object = None
    #: What stood in front of the site, when anything did: the login walls
    #: this crawl ran into (`audit.authwall.WallReport`). `None` when nobody
    #: looked, which is a repo run - a folder has no door.
    auth: object = None
    #: A slice of the markup the crawl actually saw, kept so the report can
    #: ask what platform served it. The documents keep addresses, not bodies,
    #: so without this the answer would have to be fetched a second time.
    markup_sample: str = ""
    #: What was served, per document, kept only so the browser pass can ask
    #: whether it has already seen exactly this page. A URL is not an answer
    #: - a page changes - so the cache is keyed on the bytes rather than on
    #: the address. Dropped from every report and never serialised.
    markup_by_source: dict = field(default_factory=dict)
    #: Browser pages or individual engines that did not complete. Kept on
    #: the result so every surface can say the audit is partial instead of
    #: silently presenting the static half as the whole answer.
    browser_errors: list = field(default_factory=list)
    browser_coverage: list = field(default_factory=list)
    #: Includes clean and skipped source documents that the finding list
    #: historically omits. Never derive coverage from triggered rules alone.
    coverage_documents: list = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    #: What `audit.environment.apply` left out of a local site's list: counts
    #: and the rules, so a surface can say so instead of presenting the shorter
    #: list as the whole answer. Empty when the target was not local.
    environment: dict = field(default_factory=dict)
    #: How a SharePoint run split its pages: the zones audited, the parts
    #: named, and what of Microsoft's markup was left out and how much
    #: (`audit.sharepoint_zones.Summary.as_dict`). Empty for any other run.
    sharepoint: dict = field(default_factory=dict)

    def issues(self) -> list:
        out = []
        for document in self.documents:
            out.extend(document.issues)
        return out

    def counts(self) -> dict:
        """Occurrences by severity: one for every place a problem was found."""
        counts = {level: 0 for level in SEVERITY_ORDER}
        for issue in self.issues():
            counts[issue.severity] = counts.get(issue.severity, 0) + 1
        return counts

    def distinct(self) -> list:
        """`[(first, others)]`: one entry per distinct problem.

        A header, a footer or a sprite is on every page, so a crawl of 381
        pages reported four repeated ids as 2 612 findings, and a run that
        looked like 15 338 problems was about 980. The number a person plans
        work by is the second one. Nothing is dropped: `others` are the same
        problem in the other places, and `counts()` still gives occurrences.
        """
        from duplicates import group_issues
        return group_issues(self.issues())

    def distinct_counts(self) -> dict:
        """`counts()`, counting each distinct problem once."""
        counts = {level: 0 for level in SEVERITY_ORDER}
        for first, _others in self.distinct():
            counts[first.severity] = counts.get(first.severity, 0) + 1
        return counts

    def by_rule(self) -> dict:
        """Issues grouped by rule, most-affected rule first.

        This is the view that makes a report actionable: fifty missing `alt`
        attributes are one job to schedule, not fifty separate problems to
        triage.
        """
        grouped: dict = {}
        for issue in self.issues():
            grouped.setdefault(issue.rule_id, []).append(issue)
        return dict(sorted(grouped.items(),
                           key=lambda kv: (-len(kv[1]), kv[0])))

    def documents_with_issues(self) -> list:
        return [d for d in self.documents if d.issues]

    def narrowed(self, categories=(), confidence: str = "",
                 unsettled: bool = False) -> "AccessibilityResult":
        """The same run, read through a category and certainty filter.

        A copy rather than an edit in place: the run happened once, and a
        reader who narrows the view then widens it again must get the
        findings back without re-auditing anything. Every document is kept,
        including the ones left with nothing - a page that was read and has
        no findings *in this view* is not a page that was not read, and the
        counts printed beside the list are counts of documents.
        """
        from .base import issues_in_view

        return replace(self, documents=[
            replace(document,
                    issues=issues_in_view(document.issues, categories,
                                          confidence, unsettled=unsettled))
            for document in self.documents
        ])


def _dom_path(tag) -> str:
    """CSS-ish path to an element.

    Sibling position is found by identity, not by `list.index()`: bs4 tags
    compare equal by content, so index() returns the first tag with matching
    markup and would produce a selector pointing at the wrong element.
    """
    parts = []
    node = tag
    while node is not None and getattr(node, "name", None) not in (None, "[document]"):
        index = 1
        if node.parent is not None:
            siblings = node.parent.find_all(node.name, recursive=False)
            for position, sibling in enumerate(siblings):
                if sibling is node:
                    index = position + 1
                    break
        parts.append(f"{node.name}:nth-of-type({index})")
        node = node.parent
    return " > ".join(reversed(parts))


def _line_lookup(raw_text: str):
    """Map a tag back to a 1-based line in the source file.

    bs4's html.parser records `sourceline` on every tag, so the line comes
    from the parser rather than from searching the text for the snippet —
    which would land on the wrong one whenever a file repeats an element.
    """
    def line_of(tag):
        line = getattr(tag, "sourceline", None)
        return int(line) if line else None
    return line_of


#: Suffixes whose contents are a finished document rather than a fragment of
#: one. Everything else in a repository is source that merely contains markup.
PAGE_SUFFIXES = {".html", ".htm", ".xhtml"}
#: Suffixes with no markup to read, skipped before a rule ever runs.
#:
#: `.tsx` and `.jsx` are deliberately *not* here. They were, and that made the
#: whole fragment path — `document_kind`, `Rule.page_level`,
#: `Rule.needs_external_css`, `mask_code_comments` — unreachable for React,
#: because this check runs before the `kind = "fragment"` branch below. A Vite
#: repository then audited down to its empty `index.html` shell and reported
#: zero findings, which reads as clean. See `P-19`.
#:
#: `.ts`, `.js` and `.mjs` stay skipped, and the reason is not the same one.
#: JSX is not valid in them, so their `<` is an operator: `if (a < b)` handed
#: to an HTML parser is an open tag, and every finding under it would be about
#: markup nobody wrote. A `.tsx` file's `<` is markup by definition of the
#: extension.
#: Extended 2026-09-01 after a sweep of seven repositories on this machine.
#: The list stopped at the languages someone thought of first, and the gate
#: in front of it is one character - `"<" not in raw_text` - so every other
#: language's `<` walked straight in: a `WHERE created_at < now()` in a
#: `.sql` file, a `node -e` heredoc in a `.sh` hook, a `.cjs` config. Those
#: three suffixes alone produced 51 `abbreviation-expansion` findings about
#: the words SQL and JSON appearing in a file that has no reader to be
#: accessible to. Same reasoning as `.ts` above, one measurement later.
SKIP_AUDIT_SUFFIXES = {
    ".mjs", ".ts", ".js", ".cjs", ".mts", ".cts",
    ".py", ".rb", ".go", ".rs", ".java", ".c", ".cpp", ".cc", ".h", ".hpp",
    ".cs", ".kt", ".kts", ".swift", ".scala", ".dart", ".lua", ".pl", ".r",
    ".m", ".mm",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat",
    ".sql", ".graphql", ".proto",
    ".css", ".scss", ".sass", ".less",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
}
#: Directory names that mean "not the product". Matched as whole path
#: segments, never as substrings: `test` inside a substring also matches
#: `src/features/coach/CoachTestEditor.tsx` and `SmartTestModal.tsx`, two real
#: screens in `~/repositories/XFormat` that were being skipped as tests.
#:
#: `spec` and `specs` are deliberately absent. A directory by that name is a
#: written specification at least as often as a test suite - this repository's
#: own `specs/` holds `read-once` and `resumable-runs`, neither of which is a
#: test. The JS convention that *is* unambiguous is the filename, `Foo.spec.tsx`,
#: and that is covered below; RSpec's `foo_spec.rb` is skipped by suffix.
#: `fixtures`, `__fixtures__` and `testdata` are here because
#: `project_profile._MARKER_BLIND` already treats them that way and the two
#: modules were answering the same question differently. A fixture is markup
#: written to be wrong on purpose, and reporting it as a defect of the
#: project is the audit failing to know what it is reading.
SKIP_AUDIT_DIRS = {"test", "tests", "__tests__", "__mocks__",
                   "fixtures", "__fixtures__", "testdata",
                   "node_modules", "dist", "build", ".next"}
#: Filename markers that mean the same thing, matched inside the name only.
SKIP_AUDIT_NAME_MARKERS = (".test.", ".spec.", ".stories.", ".min.")


def _is_skipped_path(path: str) -> bool:
    """Is this a file the repo audit has no business reading?

    Split out of `analyze_files` because it is the half of that loop that
    decides what is *never seen*, and a wrong answer here is invisible: the
    report simply comes back shorter, and a shorter report reads as a
    cleaner one.
    """
    parts = PurePath(path.replace("\\", "/")).parts
    if any(part.lower() in SKIP_AUDIT_DIRS for part in parts[:-1]):
        return True
    name = parts[-1].lower() if parts else ""
    if any(marker in name for marker in SKIP_AUDIT_NAME_MARKERS):
        return True
    return PurePath(name).suffix in SKIP_AUDIT_SUFFIXES


#: Suffixes whose markup is JSX rather than HTML. The distinction is not
#: cosmetic: `onClick` in a `.tsx` file is a function reference React binds,
#: and `onclick` in a `.html` file is a string the browser evaluates. Same
#: eight letters to a parser, opposite verdicts to a rule.
JSX_SUFFIXES = {".jsx", ".tsx"}


def _syntax_of(path: str) -> str:
    """"jsx" for a React source file, "html" for everything else."""
    suffix = PurePath(path.replace("\\", "/")).suffix.lower()
    return "jsx" if suffix in JSX_SUFFIXES else "html"


#: How much of the first page to keep for platform detection.
_MARKUP_SAMPLE = 200_000

#: What a finished document has and a template of one does not. A page is not
#: one tag, it is the whole shape: a root, and the two halves inside it.
_PAGE_ROOT = re.compile(r"<!doctype\s+html|<html[\s>]", re.I)
_PAGE_HALVES = re.compile(r"<head[\s>]|<body[\s>]", re.I)


def _document_kind(path: str, markup: str) -> str:
    """"page" for a finished document, "fragment" for a piece of one.

    The suffix is not enough, and believing it cost a whole framework. An
    Angular component template is a `.html` file with no `<html>` in it, so
    every page-level rule fired on it: `bp-charset`, `landmark-regions`,
    `skip-link`, `seo-canonical`, `seo-open-graph` - eight findings against a
    file that was never going to be a page on its own. The same is true of
    every `_header.html` partial ever written.

    So the question is asked of the content instead, and asked about the
    whole shape rather than one tag: a finished document has a root - a
    doctype or `<html>` - **and** the halves inside it, a `<head>` or a
    `<body>`. A fragment has neither, and a file with a stray `<html>` and
    nothing else is not a page anybody is going to serve. That is evidence
    rather than a naming convention, and it is the same test in every
    technology.

    `analyze_page_file` is unaffected - naming a single file on the command
    line *is* the statement that it is a page.
    """
    if Path(path).suffix.lower() not in PAGE_SUFFIXES:
        return "fragment"
    text = markup or ""
    complete = bool(_PAGE_ROOT.search(text)) and bool(_PAGE_HALVES.search(text))
    return "page" if complete else "fragment"


def analyze_document(markup: str, source: str, rules=None,
                     line_numbers: bool = False, ai_review=None,
                     document_kind: str = "page",
                     source_text: str | None = None,
                     force_medium: str | None = None,
                     within: str = "",
                     syntax: str = "html",
                     stacks: tuple = ()) -> DocumentReport:
    """Run every rule over one document.

    `ai_review` is an optional `AIAccessibilityReview`. It runs on the same
    parsed document as the rules rather than on a second pass, so the AI only
    ever judges wording the offline rules could not settle, and its findings
    land in the same list, sorted by the same severity order.

    `within` confines the whole reading to one subtree - the case a delivered
    SharePoint web part or an embedded widget makes, where the document
    around it belongs to somebody else. The subtree is then a *fragment* by
    construction, whatever the file was, so the page-level rules stop
    applying: it has no `<head>` to carry a canonical link and no business
    owning the page's only `<h1>`. A selector that matches nothing is an
    error and not an empty result - see `audit.within`.
    """
    rules = rules if rules is not None else RuleRegistry.all_rules()
    selected_rules = list(rules)
    if within:
        from audit import within as within_mod

        try:
            markup, how = within_mod.narrow(markup, within)
        except within_mod.ScopeNotFound:
            return DocumentReport(
                source=source,
                error=f"--within {within!r} matched nothing on this page")
        document_kind = "fragment"
        source_text = markup
        if how == "stem":
            # Said, not silently accepted: the selector that was typed is not
            # the one that matched, and the difference is a generated suffix
            # this run guessed past.
            progress.notice(
                "within",
                f"{within} matched by stem (the platform's generated suffix "
                f"was ignored)",
                human=f"# [within] {within} matched by stem (the platform's "
                      f"generated suffix was ignored)",
                selector=within, matched_by="stem")
    try:
        document = BeautifulSoup(markup, "html.parser")
    except Exception as exc:  # noqa: BLE001 - malformed markup is a finding, not a crash
        return DocumentReport(source=source, error=str(exc))

    # The source text, kept with the parsed document so a finding can quote
    # the file rather than the parser's re-print of it. See `snippet_of`.
    # The *unmasked* text, when the caller had to mask something to parse it:
    # a snippet must show what the developer will find in the file.
    remember_source(document, source_text if source_text is not None else markup)

    context = RuleContext(source=source)
    context.document_kind = document_kind
    # What the document is *for*, which the file format does not say. See
    # `audit.medium`: an email and a page are both complete HTML documents.
    context.medium = force_medium or medium.detect(markup).name
    # How the markup is *written*, which the medium does not say. A React
    # component spells the DOM in its own words - `htmlFor`, `onClick`,
    # `dangerouslySetInnerHTML` - and a rule that reads those spellings has
    # nothing to do in a `.html` file. See `Rule.syntaxes`.
    context.syntax = syntax
    context.stacks = tuple(stacks or ())
    context.dom_path = _dom_path
    if syntax == "jsx":
        # A component file has no DOM to point into; the parser's invented
        # ancestors made selectors nobody could read. See `jsx_path`.
        from .base import jsx_path

        context.dom_path = lambda tag: jsx_path(tag) or _dom_path(tag)
    if line_numbers:
        context.line_of = _line_lookup(markup)

    # `:alt="caption"` is an `alt`, spelled the way Vue, Angular, Alpine,
    # Svelte and Thymeleaf spell it. Given its plain name back before any rule
    # runs, so no rule has to know five framework syntaxes and none of them
    # reports a correct component as missing what it has.
    #
    # Run for a page as well as a fragment, and safely: both of these only
    # ever *add* a plain attribute where a bound one exists, and a served page
    # has no `th:alt`, `[alt]` or `:alt` to find. A Thymeleaf template is a
    # whole page and still needs them.
    resolve_bound_attributes(document)
    # An element whose text arrives at runtime - `x-text`, `v-text`,
    # `th:text`, `ng-bind`, `data-i18n` - is written empty on purpose. Read
    # literally it is an empty link with no accessible name.
    resolve_text_directives(document)
    # A rule that reads a syntax nobody wrote here would either be silent
    # for free or - worse - match the wrong thing: `onclick` in HTML is an
    # inline handler and a real finding, while in JSX it is a function
    # reference and is not. Filtered once, here, so no rule has to ask.
    rules = [rule for rule in rules
             if not getattr(rule, "syntaxes", ())
             or context.syntax in rule.syntaxes]
    # Same question one level up: what the *project* is built with. A stack
    # that was not detected is not a stack the rule may assume - see
    # `Rule.stacks`.
    rules = [rule for rule in rules
             if not getattr(rule, "stacks", ())
             or set(rule.stacks) & set(context.stacks)]
    if context.medium == medium.EMAIL:
        # An HTML email is the same file format as a page and almost nothing
        # else: no canonical URL, never crawled, not shared to Open Graph, and
        # rendered by clients that implement neither landmarks nor skip links.
        # The accessibility rules are untouched - `alt`, control names, table
        # headers and contrast are as real in a mail client as in a browser.
        rules = [rule for rule in rules if not getattr(rule, "web_only", False)]
    else:
        # And the other way round: the email pack has nothing to say about a
        # page a browser renders. See `Rule.email_only`.
        rules = [rule for rule in rules if not getattr(rule, "email_only", False)]
    if document_kind != "page":
        # A Vue single-file component *is* a `<template>`, whose text bs4
        # hides the way it hides a comment. Fragments only: on a served page
        # a `<template>` really is an inert prototype.
        unwrap_template_text(document)
        # A component file is a piece of a page. Asking it for a doctype, a
        # title or exactly one h1 reports the absence of things that belong to
        # the page it will be part of. A rule that needs a stylesheet is
        # skipped for the same reason: the fragment carries none, so an
        # "absent" verdict would be indistinguishable from an unseen one.
        rules = [rule for rule in rules
                if not getattr(rule, "page_level", False)
                and not getattr(rule, "needs_external_css", False)]

    report = DocumentReport(source=source)
    from audit.coverage import content_digest
    report.content_hash = content_digest(source_text if source_text is not None else markup)
    active_ids = {rule.id for rule in rules}
    report.checks = [{"rule": rule.id, "engine": "static", "status": "skipped",
                      "reason": "not applicable to syntax, stack, medium or document kind"}
                     for rule in selected_rules if rule.id not in active_ids]
    report.kind = (medium.EMAIL if context.medium == medium.EMAIL
                   else document_kind)
    report.elements_checked = len(document.find_all(True))
    seen = set()
    for rule in rules:
        try:
            found = rule.check(document, context)
        except Exception as exc:  # noqa: BLE001 - one broken rule can't fail the run
            applog.error("rule.raised", rule=rule.id, source=source,
                          error=f"{type(exc).__name__}: {exc}")
            report.issues.append(Issue(
                rule_id=rule.id, severity="minor", source=source,
                details={"rule_error": str(exc)},
            ))
            report.checks.append({"rule": rule.id, "engine": "static",
                                  "status": "error", "reason": str(exc)})
            continue
        found = list(found)
        status = "unknown" if any(i.confidence == "needs-browser" for i in found) else "checked"
        report.checks.append({"rule": rule.id, "engine": "static", "status": status})
        for issue in found:
            if issue.key in seen:
                continue
            seen.add(issue.key)
            report.issues.append(issue)

    if ai_review is not None:
        try:
            report.issues.extend(ai_review.review_document(document, context))
        except Exception as exc:  # noqa: BLE001 - the offline findings still stand
            report.issues.append(Issue(
                rule_id="ai-review", severity="minor", source=source,
                details={"rule_error": str(exc)},
            ))

    report.issues.sort(key=lambda i: (SEVERITY_ORDER.index(i.severity)
                                      if i.severity in SEVERITY_ORDER else 99,
                                      i.rule_id, i.line or 0))
    return report



def _no_html_reason(page) -> str:
    """Why a crawled page reached the audit with no HTML, in one clause.

    The crawl's diagnostics already know; "see crawl diagnostics" sent the
    reader to a place the JSON does not include.
    """
    reasons = getattr(getattr(page, "diagnostics", None), "reasons", None) or []
    if "too-large" in reasons:
        from crawler import CrawlConfig

        return ("page larger than "
                f"{CrawlConfig.max_page_bytes // (1024 * 1024)} MB, not read")
    if "not-html" in reasons:
        return "not an HTML page"
    return "no HTML received (see crawl diagnostics)"

def analyze_pages(pages, root: str, rules=None, ai_review=None,
                  media: bool = True, media_fetch=None,
                  media_progress=None,
                  site_controls: bool = False,
                  within: str = "",
                  web_parts=(),
                  include_environment: bool = False,
                  sharepoint: bool = False,
                  ootb_registry=None) -> AccessibilityResult:
    """Web mode: run over what the crawler returned.

    `sharepoint` reads every page as a modern SharePoint page: Microsoft's
    chrome is left out and counted, SPFx parts and placeholders are audited
    in full and named, and what the author put into Microsoft's own web
    parts is held to the content rules only. See `audit.sharepoint_zones`;
    `web_parts`, when given, names the repository's parts among them, and
    `ootb_registry` is what is known of Microsoft's part ids.

    On a local address (`localhost`, `*.local`, a private IP) the findings that
    describe the server rather than the page - missing security headers, `http`
    form actions, a development copy's `noindex` - are left out of the list and
    counted in `result.environment`. `include_environment=True` keeps them. See
    `audit.environment`.

    Pages the crawler could not read are carried through with their error
    rather than dropped — a page that failed to load is a finding about the
    site, and silently omitting it would make the run look cleaner than it is.

    `media` reads what the site's images say about how they were made
    (`audit.media`). Unlike every other check here it needs the network: the
    crawler kept the markup, not the pictures. `media_fetch` is injected the
    way the crawler injects `render`, so a test proves what the pass does
    with bytes without needing a network to hand them over.
    """
    rules = rules if rules is not None else RuleRegistry.all_rules()
    result = AccessibilityResult(root=root, mode="web",
                                 rules_run=[r.id for r in rules])
    zone_summary = None
    if sharepoint:
        from audit import sharepoint_zones

        zone_summary = sharepoint_zones.Summary()
    for page in pages:
        if page.error or not page.raw_html:
            result.documents.append(DocumentReport(
                source=page.url,
                error=page.error or _no_html_reason(page),
            ))
            continue
        if not result.markup_sample:
            # The first page that loaded is enough to say what served it: a
            # platform's signature is in the shell, and the shell is the same
            # on every page it renders. Bounded, because this is kept for a
            # regex and not for reading.
            result.markup_sample = page.raw_html[:_MARKUP_SAMPLE]
        result.markup_by_source[page.url] = page.raw_html
        if zone_summary is not None:
            result.documents.extend(_documents_for_zones(
                page, rules, ai_review, web_parts, zone_summary,
                ootb_registry))
            continue
        if web_parts:
            # One document per part *found on this page*, not one per page.
            # A repository ships thirty of them and a page carries three;
            # reporting the other twenty-seven as absent would be a finding
            # about the tenant's page composition, which is not this
            # repository's business.
            result.documents.extend(
                _documents_for_parts(page, rules, ai_review, web_parts))
            continue
        result.documents.append(
            analyze_document(page.raw_html, page.url, rules,
                             ai_review=ai_review, within=within))
    # What the response said. Free: these bytes arrived with the page, and
    # until now everything but `Content-Type` was discarded. See
    # `audit.headers`.
    if within:
        # Everything below is about the *page* - its response headers, its
        # canonical, the titles it shares with its siblings, the images it
        # links to. A run confined to one web part is not making a claim
        # about any of that, and reporting the tenant's headers under a
        # finding list the developer asked to be narrowed would be the
        # widest possible reading of "only inside this part".
        attribute_ownership(result)
        environment.apply(result, include=include_environment)
        applog.info("audit.web_done", pages=len(pages),
                    documents=len(result.documents),
                    findings=len(result.issues()), counts=result.counts(),
                    platform_owned={}, within=within)
        return result

    from audit import authwall as authwall_pass
    from audit import crosspage as crosspage_pass
    from audit import crawlability as crawlability_pass
    from audit import headers as header_pass

    # Whether what was read is the site or the door in front of it. A
    # diagnostic about the run and never a finding about the page: a login
    # wall is not a defect, it is the reason the pages in this report are not
    # the pages anyone wanted audited. See `audit.authwall`.
    result.auth = authwall_pass.scan(pages)

    if zone_summary is None:
        # A SharePoint run leaves the response headers out: SharePoint
        # Online's servers send them, and nothing a site owner or a part's
        # developer does changes one.
        result.documents.extend(header_pass.as_documents(pages))
    # The crawler already paid for these response codes and headers. Turn
    # confirmed noindex directives and links to reached HTTP failures into
    # SEO findings without treating unvisited, depth-limited URLs as broken.
    result.documents.extend(crawlability_pass.as_documents(
        pages, root_url=root, site_controls=site_controls))
    # What only a whole crawl can see: the same title, description or
    # canonical repeated across pages. Every rule above reads one document,
    # so this class of problem was invisible by construction.
    result.documents.extend(crosspage_pass.as_documents(pages, root_url=root))
    if media:
        from audit import media as media_pass

        # On by default, bounded hard. A site's images are part of what was
        # published, and a check that only runs when asked for is a check
        # that mostly does not run - the same reasoning that made both
        # questions the default. The budget is what keeps "read the images"
        # from becoming "mirror the site", and whatever it did not reach is
        # counted so the run can say so.
        # Said out loud, because it is now the pass that reads *every*
        # image a crawl found rather than the first forty: on a 250-page
        # site that is minutes of requests, and a stage that prints nothing
        # for minutes reads as a hang.
        # On SharePoint only the images in audited zones: an icon in the
        # suite bar is Microsoft's, and its provenance is nobody's question.
        media_pages = (pages if zone_summary is None
                       else _zone_markup_pages(pages, web_parts, ootb_registry))
        scan = media_pass.scan_page_media(media_pages, fetch=media_fetch,
                                          progress_cb=media_progress)
        result.media = scan
        result.documents.extend(media_pass.as_web_documents(scan))
    if zone_summary is not None:
        result.sharepoint = zone_summary.as_dict()
    owned = attribute_ownership(result)
    environment.apply(result, include=include_environment)
    applog.info("audit.web_done", pages=len(pages),
                documents=len(result.documents), findings=len(result.issues()),
                counts=result.counts(), platform_owned=owned)
    return result



def attribute_ownership(result) -> dict:
    """Name the platform that emitted each finding, where one did.

    Runs once per crawl, after the rules, because it needs two things that
    only exist together at the end: what the site turned out to be, and every
    finding's markup.

    Why the detection has to end here rather than in a line of the report:
    a platform's own bundles are not the site owner's to fix, and a report
    that mixes them into the same list is asking a person to triage work they
    cannot do. On `wordpress.org/news` five of the eight `serious` findings
    were core's own enqueued stylesheets.

    Returns `{platform: count}` for the summary. Nothing is removed and no
    severity is lowered - see `PLATFORM_ASSETS` for why suppression is the
    wrong answer here.
    """
    from project_profile import detect_from_url, platform_owner

    # The address counts as well as the markup: a `*.sharepoint.com` host is
    # SharePoint before a page is read, and the first page a run keeps may be
    # one whose markup names no platform at all.
    root = getattr(result, "root", "") or ""
    markup = getattr(result, "markup_sample", "") or ""
    names = [stack.name for stack in detect_from_url(root, markup).stacks]
    counts: dict = {}
    if not names:
        return counts
    for issue in result.issues():
        # The snippet is the offending element, so an address in it is the
        # address the platform wrote. The selector is a DOM path and carries
        # no provenance, which is why it is not consulted.
        owner = platform_owner(names, issue.snippet or "")
        if owner:
            issue.owner = owner
            counts[owner] = counts.get(owner, 0) + 1
    return counts

#: Suffixes whose template literals are worth reading. Only the languages
#: whose `<` is an operator - everything else is either already audited as
#: markup or has no template literals to speak of.
EMBEDDED_MARKUP_SUFFIXES = {".ts", ".js", ".mjs", ".cjs", ".mts", ".cts"}


def _documents_from_embedded(file_result, rules, ai_review) -> list:
    """The markup a skipped source file builds in its template literals."""
    from pathlib import PurePath

    from audit import embedded

    if PurePath(file_result.path).suffix.lower() not in EMBEDDED_MARKUP_SUFFIXES:
        return []
    found = []
    for markup, line in embedded.markup_fragments(file_result.raw_text or ""):
        report = analyze_document(markup, file_result.path, rules,
                                  ai_review=ai_review,
                                  document_kind="fragment")
        for issue in report.issues:
            # The line the literal starts on, so a finding points into the
            # `.ts` a person has open rather than into a string nobody can
            # navigate to. Offsets inside the literal are not added: the
            # parser's line is relative to the fragment, and claiming a
            # precise line we have not computed would be worse than naming
            # where the markup begins.
            issue.line = line
            details = dict(issue.details or {})
            details["embedded_in"] = "template literal"
            issue.details = details
        if report.issues:
            found.append(report)
    return found


def _documents_for_parts(page, rules, ai_review, web_parts) -> list:
    """This repository's web parts, wherever they appear on this page.

    Each match is audited as its own fragment and each finding is tagged
    with the part that owns it, so a report over a whole SharePoint site
    reads as "this part, on these pages" rather than as one undifferentiated
    list against the tenant's document.
    """
    from bs4 import BeautifulSoup

    from audit import within as within_mod

    try:
        document = BeautifulSoup(page.raw_html or "", "html.parser")
    except Exception:  # noqa: BLE001 - malformed markup is not a crash
        return []
    found = []
    for part in web_parts:
        try:
            matches = within_mod.narrow_all(document, part.selectors())
        except within_mod.ScopeNotFound:
            continue
        # Every placement, not only the first: a part put on a page twice is
        # two deliveries of the same code, and the second one used to go
        # unread without the report saying so.
        for index, (element, how, selector) in enumerate(matches, 1):
            report = analyze_document(str(element), page.url, rules,
                                      ai_review=ai_review,
                                      document_kind="fragment")
            for issue in report.issues:
                details = dict(issue.details or {})
                details["web_part"] = part.alias
                details["matched_by"] = f"{selector} ({how})"
                if len(matches) > 1:
                    details["instance"] = index
                issue.details = details
            found.append(report)
    return found


def _documents_for_zones(page, rules, ai_review, web_parts, summary,
                         registry=None) -> list:
    """One page of a SharePoint run: a document per zone, Microsoft's left out.

    Each zone is audited as a fragment and its findings carry the zone, the
    part's name and the evidence that placed it. A page on which no canvas
    was recognised is reported with an error rather than audited whole -
    auditing it whole is exactly the tenant's chrome this mode exists to
    leave out, and auditing nothing without a word would read as clean.
    """
    from audit import sharepoint_zones

    try:
        _document, zone_map = sharepoint_zones.map_page(
            page.raw_html or "", web_parts, registry)
    except Exception as exc:  # noqa: BLE001 - malformed markup is not a crash
        return [DocumentReport(source=page.url, error=str(exc))]
    summary.add_page(zone_map, page.url)
    if not zone_map.recognised:
        return [DocumentReport(
            source=page.url,
            error="no SharePoint canvas recognised on this page; it was not "
                  "audited (sharepoint mode reads web parts, not the chrome)")]
    found = []
    for zone in zone_map.zones:
        report = analyze_document(str(zone.element), page.url, rules,
                                  ai_review=ai_review,
                                  document_kind="fragment")
        report.issues = sharepoint_zones.apply_zone(report.issues, zone,
                                                    summary)
        found.append(report)
    return found


def _zone_markup_pages(pages, web_parts=(), registry=None) -> list:
    """The pages with only their audited zones as markup, for the media pass."""
    from dataclasses import replace as replace_page

    from audit import sharepoint_zones

    narrowed = []
    for page in pages:
        if page.error or not page.raw_html:
            narrowed.append(page)
            continue
        _document, zone_map = sharepoint_zones.map_page(page.raw_html,
                                                        web_parts, registry)
        markup = "".join(str(zone.element) for zone in zone_map.zones)
        try:
            narrowed.append(replace_page(page, raw_html=markup))
        except TypeError:  # not a dataclass: a test double
            narrowed.append(page)
    return narrowed


def _mask_for_audit(markup: str, path: str) -> str:
    """Hide what an HTML parser reads as something other than what it is.

    Two masks, and the **order is load-bearing**. A PHP block may hold a
    `//` comment of its own:

        <a href="..."<?php echo $aria; // phpcs:ignore ?>>

    Masking comments first blanks from `//` to end of line, which takes the
    closing `?>>` with it. The block is then unterminated, the anchor
    swallows everything down to the next `?>`, and a link whose text sits on
    the following line reports as nameless. Removing the whole server tag
    first means its comment never reaches the comment masker.

    `<?php echo esc_html($name); ?>` is a *processing instruction* to the
    parser and carries no text, so a link or a field named by the server read
    as nameless. On three real WordPress projects this was the largest single
    source of false `control-name` criticals.

    One function because there were two call sites and only one of them did
    it: `analyze_files` masked, `analyze_page_file` did not, so
    `xanalyze audit header.php` and the same file inside a folder scan
    disagreed about whether its link had a name. Measured 2026-09-02.
    """
    from repo_scanner import (
        mask_code_comments, mask_jsx_attribute_expressions, mask_server_tags,
    )

    markup = mask_server_tags(markup)
    markup = mask_code_comments(markup, path, server_tags_masked=True)
    if _syntax_of(path) == "jsx":
        markup = mask_jsx_attribute_expressions(markup)
    return markup


def analyze_page_file(path: str, rules=None, ai_review=None,
                      within: str = "", web_parts=()) -> AccessibilityResult:
    """One self-contained HTML file, treated as a page rather than as source.

    A page exported or built into a single file - inlined CSS, inlined
    scripts, data-URI images - is a finished document, not a template. Repo
    mode is the wrong reading of it: that mode exists for markup fragments
    inside a project and deliberately skips whatever has no elements, while
    this file is the whole page and its `<head>` is worth auditing exactly as
    a served one would be.

    It also unlocks the browser pass, which repo mode cannot have. A file with
    everything inlined renders faithfully from `file://`, so axe, the state
    pass and the load measurements all mean what they mean on a real page.
    """
    rules = rules if rules is not None else RuleRegistry.all_rules()
    result = AccessibilityResult(root=path, mode="file",
                                 rules_run=[r.id for r in rules])
    try:
        markup = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result.documents.append(DocumentReport(source=path, error=str(exc)))
        return result
    result.markup_by_source[path] = markup
    # A `.php` or `.twig` file named directly is still a template, and the
    # parser needs the same masking a folder scan gives it. Only for those
    # suffixes: a finished `.html` page has nothing to mask, and masking is
    # not free of consequence.
    from repo_scanner import _SERVER_TEMPLATE_EXTENSIONS

    if Path(path).suffix.lower() in _SERVER_TEMPLATE_EXTENSIONS:
        markup = _mask_for_audit(markup, path)
    # Line numbers on: the user has the file open, so "line 42" is directly
    # actionable in a way a CSS selector into a one-file build is not.
    if web_parts:
        # The same reading a crawled page gets, for a page saved to disk.
        class _AsPage:
            url = path
            raw_html = markup

        result.documents.extend(
            _documents_for_parts(_AsPage(), rules, ai_review, web_parts))
        return result
    result.documents.append(
        analyze_document(markup, path, rules, line_numbers=True,
                         ai_review=ai_review, within=within))
    return result


def analyze_files(file_results, root: str, rules=None, ai_review=None,
                  media: bool = True, repo_facts: bool = True,
                  force_medium: str | None = None,
                  stacks=None) -> AccessibilityResult:
    """Repo mode: run over the markup files the scanner read.

    Only files that actually contain markup are examined. A `.py` opened for
    its comments has no elements to check, and reporting "no issues" for it
    would pad the report with meaningless rows.

    `media` also reads what the project's image files say about how they
    were made (`audit.media`). A second walk rather than a filter over
    `file_results`, because the scanner never opens an image: its extension
    list is the list of files that hold *text*, so the assets are not in
    that list to be filtered. On by default because a repository's images
    are part of the repository, and off is there for a caller that has
    already read them or does not want the walk.

    `repo_facts` reads what the repository says about itself rather than
    about any file in it (`audit.repo_facts`): who the commits name as
    authors, which assistant configuration is committed, and whether a
    secrets file is sitting where the next `git add .` will take it. On by
    default for the same reason - a `.env` nobody ignores is a fact about
    this project, and a scan that walks past it to count image dimensions
    has its priorities wrong.
    """
    rules = rules if rules is not None else RuleRegistry.all_rules()
    # What the project is built with, asked once for the whole walk. A
    # stack-specific rule may only run where the stack was *proved*, and the
    # proof lives on disk rather than in any one file - a theme's
    # `style.css` header says WordPress, the template that uses `get_header()`
    # does not say it about itself. Passed in by a caller that already
    # detected it, so a scan does not walk the tree twice.
    if stacks is None:
        import project_profile

        try:
            stacks = tuple(stack.name for stack in project_profile.detect(root).stacks)
        except Exception:  # noqa: BLE001 - an undetected stack is not a failed audit
            stacks = ()
    stacks = tuple(stacks or ())
    result = AccessibilityResult(root=root, mode="repo",
                                 rules_run=[r.id for r in rules])
    for file_result in file_results:
        if file_result.error or not file_result.raw_text:
            result.coverage_documents.append({"source": file_result.path,
                "status": "error" if file_result.error else "skipped",
                "reason": file_result.error or "empty source", "checks": []})
            continue
        if "<" not in file_result.raw_text:
            result.coverage_documents.append({"source": file_result.path,
                "status": "skipped", "reason": "no markup", "checks": []})
            continue
        if _is_skipped_path(file_result.path):
            # Skipped as a *file*, and rightly: in `.ts` and `.js` a `<` is
            # an operator. But a backtick string is not code, and a classic
            # SPFx web part builds its whole interface in one - measured on
            # a real solution, 72 of 168 `.ts` files, none of it ever read.
            # So the file stays skipped and its template-literal markup is
            # audited as the fragments it is. See `audit/embedded.py`.
            result.documents.extend(
                _documents_from_embedded(file_result, rules, ai_review))
            continue
        if looks_generated(file_result.raw_text):
            # A finding in a generated file is not wrong, it is unactionable:
            # the fix belongs in the generator and the file is overwritten on
            # the next build. The marker is a convention rather than a
            # technology - protobuf, GraphQL codegen, OpenAPI clients, Prisma
            # and `.d.ts` emitters all write one - so it is checked here,
            # where every stack passes through, rather than per stack.
            result.coverage_documents.append({"source": file_result.path,
                "status": "skipped", "reason": "generated source", "checks": []})
            continue
        kind = _document_kind(file_result.path, file_result.raw_text)
        markup = file_result.raw_text
        if kind == "fragment":
            # A source file's comments are prose, and prose talks about markup:
            # `// the <img> is replaced on remount` is an element with no alt
            # to an HTML parser. Masked rather than stripped, so every line and
            # column still points where it did.
            markup = _mask_for_audit(markup, file_result.path)
        report = analyze_document(markup, file_result.path, rules,
                                  line_numbers=True, ai_review=ai_review,
                                  document_kind=kind,
                                  source_text=file_result.raw_text,
                                  force_medium=force_medium,
                                  syntax=_syntax_of(file_result.path),
                                  stacks=stacks)
        from audit.coverage import document_coverage
        result.coverage_documents.append(document_coverage(report))
        if report.issues or report.error:
            result.documents.append(report)
    if media:
        from audit import media as media_pass

        # Appended, not merged into a document: an image is a document of
        # its own, and the rest of the pipeline - the report, the grouping,
        # the file list in the window - already works in documents.
        result.documents.extend(
            media_pass.as_documents(media_pass.scan_media(root)))
    # Declarations a multilingual project makes about itself, against what
    # its code uses. Reads the project rather than any one file, so it sits
    # with the other whole-repository passes rather than in `audit.rules`.
    from audit import i18n_wpml as i18n_pass

    result.documents.extend(i18n_pass.as_documents(root))
    if repo_facts:
        from audit import repo_facts as facts_pass

        facts = facts_pass.read_facts(root)
        # Blamed before the findings are turned into documents, because one
        # of those documents reports how many of them landed on lines an
        # assistant commit last touched - and that count does not exist
        # until the blame has run.
        facts_pass.blame_issues(root, result.issues(), facts)
        result.repo = facts
        result.documents.extend(facts_pass.as_documents(facts, root))
    return result
