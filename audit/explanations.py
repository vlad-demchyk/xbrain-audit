"""Turns an accessibility `Issue` into something a person can act on.

Three things per finding, in the user's language:

* **What was found** — the concrete element and the concrete value.
* **Why it matters** — what actually happens to the person using the page.
  Not the number of the success criterion: "1.1.1" tells a developer nothing
  about why they should care, whereas "a screen reader announces the file
  name instead of the picture" does.
* **How to fix it** — the correction, plus the ready-made snippet where the
  markup allows one to be derived.

The criterion numbers are still carried, because an audit report is often
read against a checklist — but they sit alongside the explanation rather
than standing in for it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from i18n.translations import plural, t

from .base import ADVISORY, NEEDS_BROWSER, RuleRegistry

#: `{name}` in a translation string.
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


@dataclass
class IssueExplanation:
    title: str
    found: str
    why: str
    fix: str
    fix_snippet: str | None = None
    caveat: str = ""
    wcag: tuple = ()

    def as_text(self) -> str:
        parts = [self.title, self.found, self.why, self.fix]
        if self.fix_snippet:
            parts.append(self.fix_snippet)
        if self.caveat:
            parts.append(self.caveat)
        return "\n".join(p for p in parts if p)


def render(issue, lang: str = "uk") -> IssueExplanation:
    details = dict(issue.details or {})
    # A rule that raised is reported as itself rather than swallowed: a check
    # that silently stopped running is worse than one that failed loudly.
    if "rule_error" in details:
        return IssueExplanation(
            title=t("a11y_rule_error_title", lang, rule=issue.rule_id),
            found=details["rule_error"], why="", fix="",
        )

    if "engine_error" in details:
        engine = {
            "axe": "axe-core",
            "htmlcs": "HTML_CodeSniffer",
        }.get(issue.engine, t("a11y_engine_generic_name", lang))
        return IssueExplanation(
            title=t("a11y_engine_error_title", lang),
            found=t("a11y_engine_error_found", lang, engine=engine),
            why=t("a11y_engine_error_detail", lang,
                  error=_flatten(str(details["engine_error"]))),
            fix=t("a11y_engine_error_fix", lang),
        )

    if issue.rule_id == "axe:target-size":
        return _target_size(issue, details, lang)

    # A third-party engine already wrote the explanation, in its own words.
    # Rendering it beats inventing a translation key that will never exist:
    # axe and HTML_CodeSniffer between them ship hundreds of rules, and a
    # missing key shows the user `a11y_axe:region_title` instead of a
    # sentence. See `_from_engine` for why the wording is attributed.
    if ":" in issue.rule_id and details.get("engine") in _ENGINE_NAMES:
        return _from_engine(issue, details, lang)

    stem = issue.rule_id.replace("-", "_")
    # Values are pre-formatted so a template only has to interpolate: the
    # keys differ per rule, and a missing one must not raise inside the UI.
    fields = _template_fields(details)
    # A boolean in `details` is a fact, and `True` is not a word in any of
    # the three languages. Translated here rather than in the rule, because
    # a rule that emitted "yes" would have written English into a Ukrainian
    # sentence and no test would have called it a failure.
    for name, value in list(fields.items()):
        if isinstance(value, bool):
            fields[name] = t("word_yes" if value else "word_no", lang)
    # The window edge is data (`top`, `bottom`) and has to read as a word that
    # agrees with the sentence it sits in, in the reader's language.
    if fields.get("edge") in ("top", "bottom"):
        fields["edge"] = t(f"word_edge_{fields['edge']}", lang)
    _add_count_noun(stem, fields, lang)

    # All four strings get the same values: "how to fix it" is worth far
    # more when it names the actual budget, the actual limit and the actual
    # replacement element than when it repeats the rule in the abstract.
    explanation = IssueExplanation(
        title=_fill(f"a11y_{stem}_title", lang, fields),
        found=_fill(f"a11y_{stem}_found", lang, fields),
        why=_fill(f"a11y_{stem}_why", lang, fields),
        fix=_fill(f"a11y_{stem}_fix", lang, fields),
        fix_snippet=issue.fix_snippet,
        wcag=_wcag_for(issue.rule_id),
    )
    # Two different caveats, because the reader is being told two different
    # things: "go and check this in a browser" and "nothing will check this
    # for you". Sharing one sentence sent people looking for an answer that
    # does not exist.
    if issue.confidence == NEEDS_BROWSER:
        explanation.caveat = t("a11y_needs_browser", lang)
    elif issue.confidence == ADVISORY:
        explanation.caveat = t("a11y_advisory", lang)
    _add_breakpoints(explanation, details, lang)
    return explanation


def _add_breakpoints(explanation, details: dict, lang: str) -> None:
    """Say at which widths the finding was seen, when more than one was tried.

    Appended to "what was found" rather than made a caveat: at which width a
    problem exists is part of the problem. A row that exists at exactly one
    width is the one worth naming out loud - it is the half of the page the
    other passes cannot see at all (see `audit/responsive.py`).
    """
    names = details.get("breakpoints") or []
    if not names:
        return
    key = "a11y_breakpoint_only" if len(names) == 1 else "a11y_breakpoint_seen"
    sentence = t(key, lang, breakpoints=", ".join(
        t(f"breakpoint_{name}", lang) for name in names))
    explanation.found = f"{explanation.found} {sentence}".strip()


#: Engines whose findings carry their own prose. Ours do not appear here:
#: `state:` rules are this tool's own and have real translations.
_ENGINE_NAMES = {"axe-core", "HTML_CodeSniffer"}


def _target_size(issue, details: dict, lang: str) -> IssueExplanation:
    """2.5.8 in this tool's own words, with the numbers axe measured.

    axe's own sentence for it is generic ("All touch targets must be 24px
    large, or leave sufficient space"); the measured box and the distance to
    the nearest target are what makes the row checkable in devtools, so the
    sentence is built from whichever of the two axe reported.
    """
    fields = _template_fields(details)
    found = []
    if "width" in details and "height" in details:
        found.append(_fill("a11y_axe_target_size_found_size", lang, fields))
    if "closest_offset" in details:
        key = ("a11y_axe_target_size_found_offset_to" if details.get("neighbour")
               else "a11y_axe_target_size_found_offset")
        found.append(_fill(key, lang, fields))
    explanation = IssueExplanation(
        title=t("a11y_axe_target_size_title", lang),
        found=" ".join(found) or t("a11y_axe_target_size_found", lang),
        why=t("a11y_axe_target_size_why", lang),
        fix=t("a11y_axe_target_size_fix", lang),
        fix_snippet=issue.fix_snippet,
        wcag=("2.5.8",),
    )
    if issue.confidence == NEEDS_BROWSER:
        explanation.caveat = t("a11y_engine_incomplete", lang, engine="axe-core")
    _add_breakpoints(explanation, details, lang)
    return explanation


def _from_engine(issue, details: dict, lang: str) -> IssueExplanation:
    """Render a finding in the words of the engine that made it.

    The wording stays English even when the interface is not, and that is
    said out loud rather than hidden: pretending an untranslated sentence is
    ours would be worse than naming its author. Everything around it - the
    severity, the element, the field labels - is still in the user's language,
    so the row reads consistently even where one sentence does not.
    """
    engine = details.get("engine", "")
    title = (details.get("help") or details.get("why")
             or details.get("code") or issue.rule_id)
    # axe's `failureSummary` is multi-line and starts with "Fix any of the
    # following:", which is advice, not a description - so it is shown as the
    # fix rather than as the reason.
    summary = (details.get("why") or "").strip()
    description = (details.get("description") or "").strip()

    explanation = IssueExplanation(
        title=_flatten(title),
        found=t("a11y_engine_found", lang, engine=engine,
                rule=details.get("rule") or details.get("code") or issue.rule_id),
        why=description or "",
        fix=summary,
        fix_snippet=issue.fix_snippet,
        wcag=(),
    )
    if details.get("url"):
        explanation.fix = (explanation.fix + "\n" + details["url"]).strip()
    if issue.confidence == NEEDS_BROWSER:
        explanation.caveat = t("a11y_engine_incomplete", lang, engine=engine)
    return explanation


def _flatten(text: str) -> str:
    """One line, whole. Engine text is sometimes a paragraph; a paragraph
    with its newlines removed is still the whole sentence."""
    return " ".join(str(text).split())


#: What a *list row* can show. A row is one line of a fixed width, so it
#: has to end somewhere.
ROW_LIMIT = 120


def one_line(text: str, limit: int = ROW_LIMIT) -> str:
    """Clip for a surface that has one line to draw in.

    Lives here, and is called by the surfaces that need it, because clipping
    is a property of the *view* and not of the explanation. It used to happen
    inside `render`, which meant the styled report - a document with a whole
    page width and no reason to abbreviate anything - printed engine
    sentences ending in an ellipsis, and the reader could not find out what
    the rest of the sentence said from any surface at all. The window's list
    delegate elides at draw time (`ui/widgets.py`), so it needs nothing; the
    CLI prints a terminal line, so it calls this.
    """
    flat = _flatten(text)
    return flat if len(flat) <= limit else flat[:limit - 1] + "…"


class _Blank(dict):
    """A placeholder with no value renders as nothing at all."""

    def __missing__(self, key):  # noqa: D105 - the docstring above says it
        return ""


def _fill(key: str, lang: str, fields: dict) -> str:
    """Interpolate a rule's template with whatever that rule actually found.

    Formatted here rather than through `t(**fields)` because the placeholders
    differ per rule and are not knowable from this side: a rule that mentions
    `{replacement}` while this finding has no replacement must render a
    slightly thinner sentence, not raise `KeyError` in the middle of drawing
    the list. Which is precisely what it did until a coverage test walked
    every registered rule.
    """
    template = t(key, lang)
    try:
        return template.format_map(_Blank(fields))
    except (IndexError, ValueError):
        # A malformed template (stray brace) is the translator's bug, and the
        # honest thing is to show the text as written rather than nothing.
        return template


#: Per-rule noun forms for a `{count}` that is followed by a noun rather
#: than standing alone as a label (`знайдено N файлів`, unlike the plain
#: `Знайдено заголовків h1: {count}` label-then-number rows, which need no
#: agreement because the noun never follows the number). Keyed by rule stem
#: because "count" means a different noun for every rule that uses it.
_COUNT_NOUNS = {
    "perf_render_blocking": {
        "uk": dict(one="блокувальний файл", few="блокувальні файли",
                   many="блокувальних файлів"),
        "it": dict(one="file bloccante", few="file bloccanti"),
        "en": dict(one="blocking file", few="blocking files"),
    },
    "perf_preconnect": {
        # Genitive, governed by "до": 2-4 and 5+ share one plural form, same
        # as the locative documents count in `summary_line`.
        "uk": dict(one="чужого домену", few="чужих доменів", many="чужих доменів"),
        "it": dict(one="dominio esterno", few="domini esterni"),
        "en": dict(one="external host", few="external hosts"),
    },
    # Locative, governed by "у": the rule speaks at two witnesses and can
    # have three, so the number is counted rather than written into the
    # sentence. See `DeclaredLanguageContradictsAddress`.
    "html_lang_contradicts_address": {
        "uk": dict(one="незалежному місці", few="незалежних місцях",
                   many="незалежних місцях"),
        "it": dict(one="punto indipendente", few="punti indipendenti"),
        "en": dict(one="independent place", few="independent places"),
    },
}


def _add_count_noun(stem: str, fields: dict, lang: str) -> None:
    forms_by_lang = _COUNT_NOUNS.get(stem)
    if forms_by_lang is None:
        return
    count = fields.get("count")
    if not isinstance(count, int):
        return
    forms = forms_by_lang.get(lang, forms_by_lang["en"])
    noun_key = {"perf_render_blocking": "files_noun",
               "perf_preconnect": "domains_noun",
               "html_lang_contradicts_address": "places_noun"}[stem]
    fields[noun_key] = plural(count, lang, **forms)


def template_fields_for(rule_id: str) -> tuple:
    """Which detail names the sentences for this rule actually interpolate.

    Exported so `duplicates` can decide when two findings are the same
    problem *to a reader*: two that feed the same values into the same
    template render the same sentence, and a list where one row repeats the
    previous one is a list nobody reads to the bottom.

    Language-independent, and that is load-bearing rather than lucky. Every
    translation of one key carries the same `{placeholders}` - it has to, or
    `.format()` would raise - so this returns the same answer in uk, it and
    en. Keying on the *rendered* sentence instead would make the shape of a
    report depend on the language it was read in.
    """
    from i18n.translations import t

    stem = str(rule_id or "").replace("-", "_")
    names: set = set()
    for part in ("title", "found"):
        key = f"a11y_{stem}_{part}"
        # `t` returns the key when there is no entry, which has no
        # placeholders - so an unknown rule contributes nothing and falls
        # back to grouping on everything else.
        for lang in ("uk", "it", "en"):
            names.update(_PLACEHOLDER_RE.findall(t(key, lang)))
    return tuple(sorted(names))


def _template_fields(details: dict) -> dict:
    fields = {}
    for key, value in details.items():
        if isinstance(value, (list, tuple)):
            fields[key] = ", ".join(str(v) for v in value)
        else:
            fields[key] = value
    # Every template placeholder used anywhere gets a default, so a rule that
    # legitimately has nothing to say for one of them still renders.
    for key in ("src", "alt", "text", "href", "element", "id", "attribute",
                "missing", "value", "count", "rows", "tracks", "ratio",
                "required", "foreground", "background", "content", "from", "to",
                "marker", "tool", "path", "names", "read", "indicator", "color",
                "edge", "coveredBy", "coverHeight", "provider", "target",
                "language", "other_text", "name"):
        fields.setdefault(key, "")
    return fields


#: Success criteria WCAG 2.2 removed; nothing here may be reported against them.
_REMOVED_CRITERIA = frozenset({"4.1.1"})


def _wcag_for(rule_id: str) -> tuple:
    """The success criteria a rule contributes to.

    The registry knows its own rules. The browser's state pass and the
    whole-crawl comparisons are not registry rules, so they used to print no
    criterion at all - the report showed "WCAG 2.4.7" for a static finding and
    nothing for the same criterion measured live. Each of those modules now
    declares its own table and this is the one place that reads them.
    """
    try:
        return RuleRegistry.create(rule_id).wcag
    except KeyError:
        pass
    from .crosspage import CROSSPAGE_WCAG
    from .states import STATE_WCAG
    if rule_id.startswith("state:"):
        return STATE_WCAG.get(rule_id[len("state:"):], ())
    # HTML_CodeSniffer names its rules after the criterion they came from:
    # `htmlcs:2_5_3` is 2.5.3, `htmlcs:1_3_1_A` is 1.3.1 at level A.
    match = re.match(r"^htmlcs:(\d)_(\d)_(\d{1,2})(?:_|$)", rule_id)
    if match:
        criterion = ".".join(match.groups())
        # 4.1.1 Parsing is not in WCAG 2.2. The finding stays (a duplicate id
        # is still a defect where it is referenced) but it no longer claims a
        # criterion the standard has dropped.
        return () if criterion in _REMOVED_CRITERIA else (criterion,)
    return CROSSPAGE_WCAG.get(rule_id, ())


#: The noun after a document count, by language. Locative case in Ukrainian
#: ("на ... документі/документах"): 2-4 and 5+ share one plural form there,
#: so `few` and `many` are given the same string rather than inventing a
#: second one the grammar has no room for.
_DOCUMENTS_NOUN = {
    "uk": dict(one="документі", few="документах", many="документах"),
    "it": dict(one="documento", few="documenti"),
    "en": dict(one="document", few="documents"),
}


def summary_line(result, lang: str = "uk") -> str:
    """One sentence over a whole run, for the status bar and report header.

    The headline counts **distinct problems**, with the occurrences after it.
    A header or a footer is on every page, so the occurrence count measures
    how many pages a site has, not how much work there is: 381 pages gave
    15 338 findings from about 980 causes. When nothing repeats the two are the
    same number and the shorter sentence is used.
    """
    counts = result.counts()
    documents = len(result.documents_with_issues())
    distinct_counts = getattr(result, "distinct_counts", None)
    if callable(distinct_counts):
        unique = distinct_counts()
        distinct, occurrences = sum(unique.values()), sum(counts.values())
        if occurrences > distinct:
            return t(
                "a11y_summary_distinct", lang,
                distinct=distinct, occurrences=occurrences,
                critical=unique.get("critical", 0),
                serious=unique.get("serious", 0),
                moderate=unique.get("moderate", 0),
                minor=unique.get("minor", 0),
                documents=documents,
                documents_noun=plural(documents, lang, **_DOCUMENTS_NOUN.get(lang, _DOCUMENTS_NOUN["en"])),
            )
        counts = unique
    return t(
        "a11y_summary", lang,
        critical=counts.get("critical", 0),
        serious=counts.get("serious", 0),
        moderate=counts.get("moderate", 0),
        minor=counts.get("minor", 0),
        documents=documents,
        documents_noun=plural(documents, lang, **_DOCUMENTS_NOUN.get(lang, _DOCUMENTS_NOUN["en"])),
    )
