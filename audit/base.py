"""Audit rules: the interface, the finding, and the registry.

This started as accessibility only and now covers six categories, because
they turned out to be the same job. A page that ships 2 MB of render-blocking
JavaScript is unusable on a slow connection for the same practical reason a
missing label is unusable with a screen reader: the person cannot do what
they came to do. And the checks overlap outright — `lang`, `<title>`, `alt`
and heading order are each simultaneously an accessibility rule and an SEO
rule. Running them as one pass over one parsed document means each is
written once and reported under the category the user is thinking in.

Same shape as `detectors/` — one interface, a registry, concrete rules that
register themselves — for the same reason: the UI, the report and the CLI
talk to the interface and never to a rule directly, so adding a check is
one class and one registration.

What is different from the text detectors, and why it matters:

**An accessibility finding is a fact, not a probability.** An `<img>` either
has an `alt` attribute or it does not. So `Issue` carries no score. It
carries a severity, which is about *consequence* — whether a person using a
screen reader is blocked or merely inconvenienced — not about how sure the
rule is.

**Every finding must say how to fix it.** A list of violated success
criteria is not useful to the person who has to change the markup. Each rule
therefore produces `details` (what it found, as data) and, wherever the
correction is derivable from the markup, a `fix_snippet` showing the element
as it should be written.

**The honest limit is recorded, not hidden.** This runs no browser: no
JavaScript executes and no styles are computed. Contrast after the cascade,
focus order, and anything that only exists after hydration are out of reach
of a static pass. Rules that can only partly check their criterion say so
via `Rule.confidence` = `NEEDS_BROWSER`, and the report prints that next to
the finding rather than implying full WCAG coverage.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# --------------------------------------------------------------- categories
#
# What kind of problem this is, from the point of view of the person reading
# the report. A rule declares one; a finding carries it so the report can be
# grouped and filtered without asking each rule where it came from.
ACCESSIBILITY = "accessibility"
PERFORMANCE = "performance"
SEO = "seo"
GEO = "geo"
BEST_PRACTICES = "best-practices"
#: What the repository exposes rather than what a page does. A `.env` sitting
#: where the next `git add .` will take it is not a best practice anyone
#: departed from - it is a credential about to be published, and filing it
#: under "best practices" would state it too quietly to act on.
SECURITY = "security"

CATEGORIES = (ACCESSIBILITY, PERFORMANCE, SEO, GEO, BEST_PRACTICES, SECURITY)

# --------------------------------------------------------------- severity
#
# Ordered by what happens to the person using the page, which is what should
# drive the order of work — not by how easy the fix is.
CRITICAL = "critical"   # blocks the task outright: unlabelled control, keyboard trap
SERIOUS = "serious"     # the content is reachable but its meaning is lost
MODERATE = "moderate"   # navigation is harder than it should be
MINOR = "minor"         # a smell; correct in some designs

SEVERITY_ORDER = (CRITICAL, SERIOUS, MODERATE, MINOR)

# ------------------------------------------------------------- confidence
EXACT = "exact"                  # the markup answers the question completely
NEEDS_BROWSER = "needs-browser"  # a static pass can only see part of this
ADVISORY = "advisory"            # nothing will settle this; a person decides

#: Weakest first, so a caller can say "nothing below this" in one comparison.
#: The order is the whole point: `exact` means the markup settles the
#: question, `needs-browser` means something outside this file decides it and
#: the finding is a candidate rather than a fact.
#:
#: Every finding has carried this since the rules were written and nothing
#: exposed it, so an engine's "I could not determine the background colour"
#: sat in the same list as a missing `alt`. Measured on ten pages of
#: `https://www.gov.uk/`: 60 of 61 contrast findings were the first kind.
#:
#: `advisory` is the third level and it is not a weaker `needs-browser`.
#: `needs-browser` is a promise: run one and the answer arrives. The GEO
#: rules had been given that value to keep them out of `--confidence exact`,
#: which worked, but told the reader to go and launch a browser for a
#: question no browser answers - whether a missing byline is worth adding is
#: an editorial call and stays one. One field was carrying two meanings, so
#: it now carries three names.
CONFIDENCE_ORDER = (ADVISORY, NEEDS_BROWSER, EXACT)


def meets_confidence(issue, floor: str) -> bool:
    """Is this finding at least as certain as `floor`?

    An unknown confidence counts as meeting the floor. A finding whose
    certainty nobody recorded is not evidence that it is weak, and dropping
    it would be the tool hiding what it does not know about itself.
    """
    if not floor:
        return True
    try:
        wanted = CONFIDENCE_ORDER.index(floor)
    except ValueError:
        return True
    level = getattr(issue, "confidence", EXACT)
    if level not in CONFIDENCE_ORDER:
        return True
    return CONFIDENCE_ORDER.index(level) >= wanted


def issues_in_view(issues, categories=(), confidence: str = "",
                   unsettled: bool = False) -> list:
    """The findings a reader asked to see, out of the ones the pass produced.

    Both narrowings are a *view* over one pass, never a different run: the
    rules are cheap and share the parse, so `--category seo` and a full audit
    return identical findings for the categories they have in common.

    One function because there were two surfaces doing it and only one of
    them did it. `cli.py` filtered by category and by certainty; the window
    ran the same pass and showed everything, so `--category seo --confidence
    exact` and the desktop app disagreed about the same page while both
    called it an audit. `categories` empty means every category, which is
    what "no choice made" has to mean here - an empty list is not an
    instruction to report nothing.

    **What is not shown at all: the undecided.** `needs-browser` is an engine
    saying it could not tell - "this element is on a background image",
    "absolutely positioned, the background colour cannot be determined". On
    one page of `python.org` that was **312 of 348** contrast findings, and a
    report two thirds made of "we do not know" is not a list anybody can work
    through. `fullscan` loads the page in a real browser precisely so these
    get settled; what is still undecided after that is not a finding, and
    where no browser ran it is not one either.

    Nothing is silently lost: `unsettled_count` gives the number a caller
    prints, and `unsettled=True` brings the list back.

    Editorial recommendations (`advisory`) are also out by default. They
    remain available through `unsettled=True`, not counted as proven defects.
    """
    wanted = set(categories or ()) & set(CATEGORIES)
    kept = list(issues)
    if wanted and wanted != set(CATEGORIES):
        kept = [issue for issue in kept if issue.category in wanted]
    if not unsettled:
        kept = [issue for issue in kept
                if getattr(issue, "confidence", EXACT) not in (NEEDS_BROWSER, ADVISORY)]
    if confidence:
        kept = [issue for issue in kept if meets_confidence(issue, confidence)]
    return kept


def unsettled_count(issues) -> int:
    """How many findings were left out for being undecided.

    Printed rather than silently dropped: hiding a number is how a report
    starts to lie by omission, and the reader has to be able to ask for the
    list back.
    """
    return sum(1 for issue in issues
               if getattr(issue, "confidence", EXACT) in (NEEDS_BROWSER, ADVISORY))


def unsettled_summary(issues, limit: int = 5) -> str:
    """Which checks were left undecided, by rule: `media-captions ×2, …`.

    The count alone said "2 checks could not be decided" and nothing about
    which, so a reader could not tell whether it was worth `--unsettled` -
    on `apps/coach/src` it was a live-call `<Video>` and a dialog named by a
    prop, both worth a look.
    """
    counts: dict = {}
    for issue in issues:
        if getattr(issue, "confidence", EXACT) in (NEEDS_BROWSER, ADVISORY):
            counts[issue.rule_id] = counts.get(issue.rule_id, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    shown = [f"{rule} ×{count}" if count > 1 else rule
             for rule, count in ordered[:limit]]
    if len(ordered) > limit:
        shown.append(f"+{len(ordered) - limit}")
    return ", ".join(shown)


@dataclass
class Issue:
    """One accessibility problem, at one place in one document."""
    rule_id: str
    severity: str
    #: Where it is. `selector` is a CSS-ish DOM path for a page; `line` is
    #: set instead when the source is a file on disk.
    selector: str = ""
    line: int | None = None
    #: The offending markup, truncated — enough to recognise, not to flood.
    snippet: str = ""
    #: Rule-specific data, rendered into a sentence in the user's language
    #: by `a11y.explanations`. Data rather than prose for the same reason as
    #: `TextSpan.details`: the UI language can change after a scan.
    details: dict = field(default_factory=dict)
    #: The element as it should be written, where that follows from the
    #: markup. None when the fix needs a human decision (what the alt text
    #: should actually say, which heading level is correct).
    fix_snippet: str | None = None
    confidence: str = EXACT
    #: Document this came from: a URL in web mode, a path in repo mode.
    source: str = ""
    #: Which of the four audit categories this belongs to.
    category: str = ACCESSIBILITY
    #: Which platform emitted the markup this was found in, when a platform
    #: was detected and its own asset paths are in the element - `""` when
    #: the page's author owns it, which is the answer for anything the
    #: platform did not generate. Never suppresses: it says who can act.
    owner: str = ""
    #: Which engine produced it: "static" (our own rules), "axe",
    #: "htmlcs", "browser" (a measurement), or "ai". Kept so the report can
    #: say where a finding came from and so two engines finding the same
    #: thing can be collapsed into one row.
    engine: str = "static"

    def __post_init__(self) -> None:
        # Masked at birth, so every consumer sees one spelling: a username
        # or an access hash in a quoted address never reaches a report, and
        # the fingerprint is the same for everybody (see `privacy`).
        from privacy import mask_issue

        mask_issue(self)

    @property
    def key(self) -> tuple:
        """Identity for de-duplication across a crawl: the same rule firing
        on the same element of the same document is one problem, even when
        the crawler reached that page twice.

        The snippet is part of it, not a fallback for a missing selector.
        It was `selector or snippet`, and that made the element the whole
        identity: `abbreviation-expansion` reports what it found, so "HTML"
        and "CSS" in one paragraph were two findings about two different
        things at one selector - and the second was dropped as a duplicate
        of the first. For every rule whose snippet is just the element's
        markup, this changes nothing: same element, same snippet.
        """
        return (self.source, self.rule_id, self.selector, self.snippet, self.line)


class Rule(ABC):
    """One check, run over one parsed document."""

    #: stable machine name, used as the i18n key stem and in --json output
    id: str = "base"
    category: str = ACCESSIBILITY
    severity: str = MODERATE
    confidence: str = EXACT
    #: WCAG success criteria this contributes to. Deliberately "contributes
    #: to": a static check almost never covers a criterion in full, and
    #: claiming otherwise is how tools end up promising compliance.
    wcag: tuple = ()
    #: True when the check only means something for a whole document: a
    #: doctype, a title, exactly one h1. A component file holds a fragment of
    #: a page, so running these over it reports the absence of things that
    #: were never supposed to be there — which is how a repo report fills up
    #: with findings nobody can act on.
    page_level: bool = False
    #: True when a "missing" verdict depends on a stylesheet the parser never
    #: sees. `<img>` with no `width`/`height` still might have both reserved
    #: by a CSS class or a sibling `.module.css` file - true on a live page,
    #: which is why `--browser` catches the real absence there. A repo
    #: fragment carries none of that: its own file is all a rule ever sees,
    #: and treating an unknown as a violation is indistinguishable from
    #: treating an unstyled `<div>` as one. Confirmed against
    #: `~/repositories/xformat`: every one of 48 `seo-image-dimensions`
    #: findings on `.tsx` fragments had no `width`/`height` *and* no
    #: `className`/`style` visible in the snippet either - not a bound
    #: expression to read, evidence genuinely absent rather than hidden.
    needs_external_css: bool = False
    #: True when the check is about a document a *browser* serves. An HTML
    #: email is the same file format and almost nothing else: it has no
    #: canonical URL, is never crawled, is not shared to Open Graph, and lands
    #: in clients that implement neither landmarks nor skip links.
    #:
    #: Measured on `~/repositories/VSC`, a workspace of newsletter and funnel
    #: deliverables: the six loudest rules in a 1074-finding run were all of
    #: this kind - `seo-canonical` 93, `seo-structured-data` 93,
    #: `seo-open-graph` 91, `seo-meta-description` 83, `landmark-regions` 80,
    #: `skip-link` 67. Asking for them is a category error repeated eighty
    #: times, not a strict audit.
    #:
    #: Accessibility is deliberately **not** web-only. `image-alt`,
    #: `control-name`, `table-headers` and contrast are as real in a mail
    #: client as in a browser. See `audit.medium`.
    web_only: bool = False
    #: The mirror image of `web_only`: a check that means something **only**
    #: in a mail client. "Give this font a generic fallback" is not advice a
    #: browser needs - it has the font or downloads it - and "say what colour
    #: this link is" is only urgent where the client will otherwise pick one.
    #: Skipped everywhere `audit.medium` did not say email, which means it
    #: never fires on a page that merely happens to use tables.
    email_only: bool = False
    #: Which source syntaxes this check means anything in. Empty - the
    #: default - is "every one of them", which is right for a rule that reads
    #: markup: an `<img>` with no `alt` is the same defect in a `.html` file,
    #: in a Twig template and in a React component.
    #:
    #: A non-empty tuple is for a check that reads something only one syntax
    #: has. `htmlFor`, `onClick` and `dangerouslySetInnerHTML` do not exist in
    #: HTML at all; they are JSX spellings, and a rule that looks for them
    #: would be dead weight on every other document. See `audit/rules/jsx.py`.
    syntaxes: tuple = ()
    #: Which detected project stacks this check means anything in. Empty is
    #: "every one of them". A non-empty tuple names stacks as
    #: `project_profile` names them, and the rule is skipped whenever the
    #: stack was **not** detected - never guessed at: a WordPress rule on a
    #: project nobody proved is WordPress is a rule firing on a coincidence.
    stacks: tuple = ()

    @abstractmethod
    def check(self, document, context) -> list:
        """Return `Issue`s. `document` is a BeautifulSoup tree; `context`
        carries the source name and a `dom_path` helper so rules don't each
        reimplement one."""
        raise NotImplementedError


class RuleRegistry:
    _rules: dict = {}

    @classmethod
    def register(cls, rule_cls) -> None:
        cls._rules[rule_cls.id] = rule_cls

    @classmethod
    def available(cls) -> list:
        return sorted(cls._rules)

    @classmethod
    def all_rules(cls, categories=None) -> list:
        rules = [cls._rules[name]() for name in sorted(cls._rules)]
        if categories is None:
            return rules
        wanted = set(categories)
        return [r for r in rules if r.category in wanted]

    @classmethod
    def by_category(cls) -> dict:
        grouped: dict = {}
        for rule in cls.all_rules():
            grouped.setdefault(rule.category, []).append(rule.id)
        return grouped

    @classmethod
    def create(cls, rule_id: str):
        return cls._rules[rule_id]()


@dataclass
class RuleContext:
    """What a rule needs to know about where it is running."""
    source: str = ""
    #: "page" for a served page or a self-contained file, "fragment" for a
    #: source file that merely contains markup. Page-level rules are skipped
    #: on a fragment; see `Rule.page_level`.
    document_kind: str = "page"
    #: "web" for a document a browser serves, "email" for one a mail client
    #: renders. Web-only rules are skipped on an email; see `Rule.web_only`.
    medium: str = "web"
    #: How the markup in this document is written: "html" for markup a
    #: browser or a mail client receives, "jsx" for a React source file whose
    #: attributes are JSX spellings of the DOM ones. Rules that read a
    #: syntax-specific attribute declare it in `Rule.syntaxes`.
    syntax: str = "html"
    #: The stacks `project_profile` proved for the project this document
    #: belongs to, by name. Empty when nothing was detected or when the
    #: document has no project behind it - a single page named on the command
    #: line - and a stack-specific rule stays silent in both cases.
    stacks: tuple = ()
    #: Maps a bs4 tag to a CSS-ish path. Injected rather than imported so the
    #: web and repo paths can supply their own (a repo file also wants a line
    #: number, which a live page has no notion of).
    dom_path = None
    line_of = None

    def locate(self, tag) -> tuple:
        selector = self.dom_path(tag) if self.dom_path else ""
        line = self.line_of(tag) if self.line_of else None
        return selector, line


def is_binding(value) -> str:
    """Is this attribute value an unevaluated template expression?

    `onClick={handleClose}` in JSX, `:href="url"` in Vue, `{#if}` in Svelte:
    an HTML parser reads these as ordinary attribute values, so a rule sees
    the literal text `{handleClose}` where the browser will see a function
    reference — or, for an aria-label, a string the parser cannot know.
    Judging the placeholder as if it were the final value is what turns every
    React handler into an "inline event handler" finding.

    Returns the kind of binding for the report, or "" when the value is a
    plain literal.
    """
    text = (value if isinstance(value, str) else " ".join(value or [])).strip()
    if not text:
        return ""
    if text.startswith("{{") and text.endswith("}}"):
        return "mustache"       # Vue, Angular, Handlebars
    if text.startswith("{"):
        return "expression"     # JSX, Svelte
    if text.startswith(("<%", "${")):
        return "template"       # ERB/EJS, template literal
    return ""


#: Where a parsed document remembers the text it was parsed from, so a
#: snippet can be quoted from the source instead of re-serialised. Attached to
#: the soup by `analyze_document`; absent for a document that has no source
#: text of its own, such as a DOM read back out of a browser.
SOURCE_ATTR = "_xa_source"
LINE_STARTS_ATTR = "_xa_line_starts"


def remember_source(document, markup: str) -> None:
    """Let `snippet_of` quote this document rather than re-print it."""
    starts = [0]
    for index, char in enumerate(markup):
        if char == "\n":
            starts.append(index + 1)
    setattr(document, SOURCE_ATTR, markup)
    setattr(document, LINE_STARTS_ATTR, starts)


def document_source(document) -> str:
    """The file as it is on disk, for a rule that has to read past the DOM.

    Almost every rule reads the parsed tree, and should: that is what a
    browser will see. A few cannot, because what they check is *removed*
    before parsing - `repo_scanner.mask_server_tags` takes `<?php wp_head(); ?>`
    out so the parser does not read it as a processing instruction, and a
    rule asking whether a theme calls `wp_head()` would then always find that
    it does not. Those rules read this instead.

    Empty for a document with no source of its own, such as a DOM read back
    out of a browser - where the question does not arise, because a served
    page has no template calls left in it.
    """
    return getattr(document, SOURCE_ATTR, "") or ""


def _source_of(tag):
    """The markup this tag was parsed from, and its line offsets."""
    node = tag
    while node is not None:
        markup = getattr(node, SOURCE_ATTR, None)
        if markup is not None:
            return markup, getattr(node, LINE_STARTS_ATTR, None)
        node = getattr(node, "parent", None)
    return None, None


def _open_tag_end(markup: str, start: int) -> int:
    """Where the opening tag that begins at `start` ends.

    Not `markup.find(">")`: a JSX attribute can contain one
    (`title={a > b ? "x" : "y"}`), and so can a quoted value. Quotes and brace
    depth are tracked for exactly that reason.
    """
    quote = ""
    depth = 0
    index = start
    while index < len(markup):
        char = markup[index]
        if quote:
            if char == quote:
                quote = ""
            index += 1
            continue
        # A `//` comment inside a JSX expression, which is legal and common
        # in a multi-line prop object. Its prose is not code: one apostrophe
        # in "the plugin's own classes" opened a quote that never closed, the
        # tag was declared unterminated, and the finding fell back to the
        # parser's re-print - `<codemirror ""}`}="" ?=""`, which is in nobody's
        # file. Skipped only inside an expression, so a `//` in a plain HTML
        # attribute value still means whatever it meant before.
        if depth > 0 and char == "/" and markup[index:index + 2] == "//":
            newline = markup.find("\n", index)
            index = len(markup) if newline == -1 else newline + 1
            continue
        if char in "\"'":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif char == ">" and depth == 0:
            return index + 1
        index += 1
    return -1


#: The filler `repo_scanner.mask_server_tags` leaves behind: `${` then only
#: hyphens then `}`. Unmistakable, because a real `${...}` binding carries a
#: name.
_SERVER_TAG_FILLER = re.compile(r"\$\{-*\}")


def _unmask_server_tags(text: str) -> str:
    """Put `<?php … ?>` back where the mask stands, for display only.

    The last resort in `snippet_of` is the parser's own re-print, and the
    parser was handed masked markup. Printing that shows a developer a run of
    hyphens where their own code is - which is worse than useless in a report
    (`P-21`). It cannot be un-masked exactly, because the mask deliberately
    discards what it covered, so this says what *kind* of thing was there.
    """
    return _SERVER_TAG_FILLER.sub("<?php \u2026 ?>", text)


#: How far back and forward to look for an element whose recorded position
#: did not land on it. Two lines back covers a tag whose attributes were
#: rewritten by a mask; a whole file scan would find *an* element of that
#: name rather than *this* one.
_TAG_SEARCH_LINES = 2


def _find_open_tag(markup: str, line_starts, line, tag) -> str:
    """The opening tag of `tag`, found by name near the recorded line.

    The parser records a line even when the column is unusable, and the
    element's own name is the strongest thing left to search on. Bounded to
    a few lines on purpose: the answer must be *this* element, and a
    file-wide search for `<a` would confidently return the wrong one.

    Returns "" when it cannot be sure, so the caller can fall back rather
    than print a guess.
    """
    name = getattr(tag, "name", "") or ""
    if not name or not line or not line_starts:
        return ""
    index = int(line) - 1
    if not 0 <= index < len(line_starts):
        return ""
    begin = line_starts[max(0, index - _TAG_SEARCH_LINES)]
    stop_index = min(len(line_starts) - 1, index + _TAG_SEARCH_LINES)
    stop = (line_starts[stop_index + 1] if stop_index + 1 < len(line_starts)
            else len(markup))
    window = markup[begin:stop]
    needle = "<" + name
    at = window.find(needle)
    while at != -1:
        after = window[at + len(needle):at + len(needle) + 1]
        # `<a` must not match `<abbr`. A name is followed by whitespace, `>`
        # or `/`.
        if after in ("", " ", "\t", "\n", "\r", ">", "/"):
            end = _open_tag_end(window, at)
            if end != -1:
                return window[at:end]
            break
        at = window.find(needle, at + 1)
    return ""


#: How a framework spells "this attribute's value is an expression".
#:
#: Vue writes `:alt="photo.caption"` (and `v-bind:alt`), Angular writes
#: `[alt]` and `[attr.aria-label]`, Alpine and Svelte write `x-bind:` and
#: `bind:`. The attribute the rule looks for is then *absent*: an `<img>`
#: with `:alt` has no `alt`, and `image-alt` reported a correct Vue component
#: as missing its alternative text.
#:
#: Measured on `tests/fixtures/frameworks`: before this, the idiomatic Vue
#: component and the deliberately broken one produced identical findings -
#: three each - which means the pass could not tell them apart at all. Svelte
#: and JSX were already fine, because they put the expression in the *value*
#: (`alt={caption}`), which `is_binding` recognises.
#: `hx-` is deliberately absent. htmx's `hx-get="/y"` is a *behaviour*, not
#: "bind the `get` attribute" - reading it as a binding invented a `get`
#: attribute that no element has. A prefix earns a place here only when the
#: framework's own meaning is "this attribute's value is an expression".
_BINDING_PREFIXES = (":", "v-bind:", "x-bind:", "bind:", "th:")
_ANGULAR_ATTR = re.compile(r"^\[(?:attr\.)?(?P<name>[\w:-]+)\]$")


def _bound_target(name: str) -> str:
    """The plain attribute a bound name stands for, or ""."""
    match = _ANGULAR_ATTR.match(name)
    if match:
        return match.group("name")
    for prefix in _BINDING_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix):
            target = name[len(prefix):]
            # `:` also introduces Vue's shorthand for a *directive argument*
            # that is not an attribute (`:key`), and XML namespaces
            # (`xlink:href`, `xmlns:xlink`) share the colon without being
            # bindings. A namespace has text on both sides; a shorthand
            # binding does not.
            if prefix == ":" and not name.startswith(":"):
                continue
            if target and ":" not in target:
                return target
    return ""


#: Attributes that supply an element's **text** rather than one of its
#: attributes. An element carrying one of these is written empty on purpose:
#: the framework fills it at runtime.
#:
#: This is its own class of blindness, separate from bound attributes. A link
#: written `<a href="/x" x-text="label"></a>` has no children, so it reads as
#: an empty link with no accessible name - a *serious* finding against markup
#: that names itself perfectly well. Alpine, Vue, Angular, Thymeleaf, Knockout
#: and every `data-i18n` extractor write the same shape.
_TEXT_DIRECTIVES = (
    "v-text", "v-html",           # Vue
    "x-text", "x-html",           # Alpine
    "th:text", "th:utext",        # Thymeleaf
    "ng-bind", "ng-bind-html",    # AngularJS
    "data-i18n", "data-t",        # i18next and friends
    "data-bind",                  # Knockout
)


def resolve_text_directives(document) -> None:
    """Give an element that is filled at runtime something to say.

    A placeholder, not the real string - the real string lives in a
    translation file or a component's state and is not in this document. What
    matters to every rule that asks "does this have a name" is that the answer
    is yes, and that it stops being no for the wrong reason.

    Only for an element that is otherwise empty: markup that has both a
    directive and literal text already answers the question, and the literal
    is the better answer.
    """
    from bs4 import NavigableString

    for tag in document.find_all(True):
        attrs = getattr(tag, "attrs", None)
        if not attrs:
            continue
        directive = next((name for name in _TEXT_DIRECTIVES if name in attrs), "")
        if not directive:
            continue
        if tag.get_text(strip=True):
            continue
        value = attrs.get(directive)
        if isinstance(value, list):
            value = " ".join(value)
        tag.append(NavigableString("{" + str(value or directive).strip() + "}"))


def unwrap_template_text(document) -> None:
    """Make text inside `<template>` readable again, for a fragment.

    BeautifulSoup wraps it in `TemplateString`, and `get_text()` and
    `stripped_strings` skip that class the way they skip comments and script
    bodies. On a served page that is right: a `<template>` is an inert
    prototype the browser does not render.

    In a component file it is exactly wrong. A Vue single-file component
    *is* a `<template>`, and so is an Angular inline template and the body
    of a web component. Every label, heading and link inside one read as
    empty, so `tests/fixtures/frameworks/vue/Correct.vue` - an idiomatic,
    correct component - reported the same findings as the deliberately
    broken one beside it. A pass that cannot tell those apart is not
    measuring the code.

    Fragments only, which is why this is called from the fragment branch:
    the page case is the one bs4 has right.
    """
    from bs4 import NavigableString
    from bs4.element import TemplateString

    for node in list(document.descendants):
        if isinstance(node, TemplateString):
            node.replace_with(NavigableString(str(node)))


def resolve_bound_attributes(document) -> None:
    """Give every bound attribute its plain name back, as a binding value.

    Mutates the parsed tree rather than the source text, so no offset moves
    and `snippet_of` still quotes the developer's own file. The value becomes
    `{expression}` - the shape `is_binding` already knows - so a rule that
    asks "is this a real value or a computed one" gets the right answer
    without any rule having to learn framework syntax.

    Only ever *adds*: a tag that already carries the plain attribute keeps
    what it has, because a literal beats an expression when both are written.
    """
    for tag in document.find_all(True):
        attrs = getattr(tag, "attrs", None)
        if not attrs:
            continue
        for name in list(attrs):
            target = _bound_target(name)
            if not target or target in attrs:
                continue
            value = attrs[name]
            if isinstance(value, list):
                value = " ".join(value)
            attrs[target] = "{" + str(value or "").strip() + "}"


def source_tag_name(tag) -> str:
    """The tag's name **as it is written in the file**, or "".

    An HTML parser lowercases tag names, so `<Button>` and `<button>` are
    both `button` by the time a rule sees them - and in JSX that is the whole
    difference between a design-system component, whose behaviour this file
    cannot see, and a bare DOM element, whose behaviour is right there in the
    attributes. Reading it back from the source is the only way to tell.

    Deliberately not `snippet_of(...)[1:]`: the snippet has to find the *end*
    of the opening tag, which a hostile enough attribute can defeat, and the
    name is available without that - it is the word immediately after the
    `<`. Empty for a document with no source text, such as a DOM read out of
    a browser, where there are no components to confuse anything with.
    """
    markup, line_starts = _source_of(tag)
    line = getattr(tag, "sourceline", None)
    column = getattr(tag, "sourcepos", None)
    if not markup or not line_starts or not line or column is None:
        return ""
    index = int(line) - 1
    if not 0 <= index < len(line_starts):
        return ""
    start = line_starts[index] + int(column)
    if not 0 <= start < len(markup) or markup[start] != "<":
        return ""
    name = []
    for char in markup[start + 1:start + 1 + 60]:
        if char.isalnum() or char in "._-:":
            name.append(char)
        else:
            break
    return "".join(name)


def source_position(tag) -> tuple:
    """`(markup, offset)` of the tag's `<` in the file, or `(None, -1)`.

    For a rule that has to read what surrounds an element in the source -
    which branch of a JSX conditional it sits in - rather than the element.
    """
    markup, line_starts = _source_of(tag)
    line = getattr(tag, "sourceline", None)
    column = getattr(tag, "sourcepos", None)
    if not markup or not line_starts or not line or column is None:
        return None, -1
    index = int(line) - 1
    if not 0 <= index < len(line_starts):
        return None, -1
    start = line_starts[index] + int(column)
    if not 0 <= start < len(markup) or markup[start] != "<":
        return None, -1
    return markup, start


def opening_tag_source(tag) -> str:
    """The whole opening tag as written, however long; "" without a source."""
    markup, start = source_position(tag)
    if markup is None:
        return ""
    end = _open_tag_end(markup, start)
    return markup[start:end] if end != -1 else ""


def attribute_expression(tag, attribute: str) -> str:
    """The JS inside `attribute={…}` in the source, or "".

    The parser cannot give it back: `aria-describedby={on ? `${id}-x` :
    undefined}` reaches it as an attribute whose value is `{on` and a row of
    junk attributes after it. Read from the file, braces balanced and string
    literals skipped.
    """
    opening = opening_tag_source(tag)
    if not opening:
        return ""
    match = re.search(r"(?<![\w-])" + re.escape(attribute) + r"\s*=\s*\{",
                      opening, re.IGNORECASE)
    if match is None:
        return ""
    depth, index, quote = 1, match.end(), ""
    while index < len(opening):
        char = opening[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
        elif char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return opening[match.end():index].strip()
        index += 1
    return ""


_BRANCHES_ATTR = "_xa_jsx_branches"


def _branches_of(tag):
    """The scanned constructs of the file this tag came from, or None."""
    from .jsx_branches import Branches

    node = tag
    while node is not None and getattr(node, SOURCE_ATTR, None) is None:
        node = getattr(node, "parent", None)
    if node is None:
        return None
    branches = getattr(node, _BRANCHES_ATTR, None)
    if branches is None:
        branches = Branches(getattr(node, SOURCE_ATTR))
        setattr(node, _BRANCHES_ATTR, branches)
    return branches


def jsx_path(tag, depth: int = 5) -> str:
    """A readable path to a JSX element: its real JSX ancestors, as written.

    The CSS path a page gets is wrong for a component file. An HTML parser
    turns `useState<string>()` and `Record<CoachSessionParticipant["status"],
    …>` into tags, and every element after them is nested inside: the
    selectors read `coachsessionparticipant["status"],:nth-of-type(1) >
    string,:…`. Only elements the scanner saw open as JSX are kept, in their
    source spelling (`Select`, `div.card`), the nearest few.
    """
    branches = _branches_of(tag)
    if branches is None:
        return ""
    parts = []
    node = tag
    while node is not None and getattr(node, "name", None) not in (None, "[document]"):
        _markup, offset = source_position(node)
        if offset in branches.tags and (node is tag or offset not in branches.self_closing):
            name = source_tag_name(node) or node.name
            classes = node.get("classname") or node.get("class") or ""
            if isinstance(classes, list):
                classes = " ".join(classes)
            first = classes.split()[0] if classes and not classes.startswith("{") else ""
            if first and re.fullmatch(r"[\w-]+", first):
                name = f"{name}.{first}"
            parts.append(name)
            if len(parts) >= depth:
                break
        node = node.parent
    return " > ".join(reversed(parts))


def jsx_exclusive(first, second) -> bool:
    """Can these two JSX elements never render together?

    True when they sit on different arms of one conditional, of one
    `cond &&` / `!cond &&` pair, or in two separate `return` statements.
    False whenever that cannot be shown - including for anything that is
    not JSX source - so a caller only ever stays silent on proof.
    """
    markup, one = source_position(first)
    other_markup, two = source_position(second)
    if markup is None or other_markup is not markup:
        return False
    branches = _branches_of(first)
    return branches.exclusive(one, two) if branches is not None else False


def snippet_of(tag, limit: int = 160) -> str:
    """The opening tag as it is written in the file.

    Deliberately not `str(tag)` when the source is known. An HTML parser is
    the only practical way to run these rules over a JSX or Vue file, but it
    re-prints what it parsed: `className` comes back as `classname`, and an
    expression attribute (`alt={photo.caption}`) comes back as the debris
    `alt="{photo.caption}"` or as empty `="" ?=""` pairs. A developer reading
    the report then cannot find the line, because that text is not in their
    file. So the snippet is cut out of the original markup by the position the
    parser recorded, and `str(tag)` remains the fallback for a document with
    no source text - a DOM read back out of a browser, where the serialisation
    *is* the truth.

    A `<div>` wrapping half the page is still cut at its opening tag: the
    attributes are what the finding is about.
    """
    markup, line_starts = _source_of(tag)
    line = getattr(tag, "sourceline", None)
    column = getattr(tag, "sourcepos", None)
    if markup and line_starts and line and column is not None:
        index = int(line) - 1
        if 0 <= index < len(line_starts):
            start = line_starts[index] + int(column)
            if 0 <= start < len(markup) and markup[start] == "<":
                end = _open_tag_end(markup, start)
                if end != -1:
                    return _clip(markup[start:end], limit)
        # The position did not land on a tag. That happens when the parsed
        # text is not character-for-character the file: a server tag in
        # attribute position (`<a <?php echo $attrs; ?> href=...>`) is masked
        # before parsing, and the mask can move where the parser thinks the
        # tag begins. Falling through to `str(tag)` then prints the *mask* -
        # filler where the developer expects their own code.
        #
        # So the element is looked for by name instead, from the start of the
        # line the parser did record. Not the whole line: a report that
        # answers "which element" with `></use>` or a line of pure PHP is
        # pointing at the file rather than at the finding (`P-21`).
        found = _find_open_tag(markup, line_starts, line, tag)
        if found:
            return _clip(found, limit)

    text = _unmask_server_tags(str(tag))
    closing = text.find(">")
    return _clip(text[:closing + 1] if closing != -1 else text, limit)


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"
