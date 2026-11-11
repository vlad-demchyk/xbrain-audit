"""The offline accessibility rules.

Every rule here answers a question the markup alone can answer. Where a
check can only be partly done without a browser, it says so
(`confidence = NEEDS_BROWSER`) instead of pretending otherwise.

Two habits run through the file:

* **Report the element, not the page.** A finding names one element and
  shows its opening tag, so the fix has an address.
* **Derive the fix when the markup allows it.** `fix_snippet` is filled in
  when the correction follows from what is already there — adding
  `alt=""` to a spacer image, adding `type="button"`, removing a positive
  `tabindex`. It is left empty when the fix needs a human decision, because
  a generated `alt="image"` is worse than no alt text at all: it silences
  the error and tells the reader nothing.
"""
from __future__ import annotations

import re

from ..base import (
    ACCESSIBILITY, ADVISORY, CRITICAL, EXACT, MINOR, MODERATE, NEEDS_BROWSER, PERFORMANCE,
    SERIOUS, Issue, Rule, RuleRegistry, attribute_expression, is_binding,
    jsx_exclusive, snippet_of,
)

# Elements that are focusable and actionable, i.e. need an accessible name.
_INTERACTIVE = ("a", "button", "input", "select", "textarea", "summary")
# Input types that are not text fields and label differently.
_UNLABELLED_INPUT_TYPES = {"hidden", "submit", "reset", "button", "image"}
# Link text that describes the mechanism instead of the destination.
_VAGUE_LINK_TEXT = {
    "en": {"click here", "here", "read more", "more", "link", "this", "learn more",
           "details", "download", "see more", "continue"},
    "uk": {"тут", "детальніше", "докладніше", "читати далі", "далі", "посилання",
           "більше", "дивитись", "перейти", "завантажити"},
    "it": {"clicca qui", "qui", "leggi di più", "altro", "link", "questo",
           "scopri di più", "dettagli", "continua", "vedi"},
}
_WHITESPACE_RE = re.compile(r"\s+")


def _text_of(tag) -> str:
    return _WHITESPACE_RE.sub(" ", " ".join(tag.stripped_strings)).strip()


def _accessible_name(tag) -> str:
    """A rough accessible name, in roughly the order the spec computes it.

    Rough on purpose: the full algorithm walks `aria-labelledby` across the
    document, applies CSS-generated content and consults native host
    semantics. What is implemented here is what static markup supports —
    and it is enough to answer the only question these rules ask, which is
    whether there is *any* name at all.
    """
    for attribute in ("aria-label", "title"):
        value = (tag.get(attribute) or "").strip()
        if value:
            return value
    labelled_by = (tag.get("aria-labelledby") or "").strip()
    if labelled_by:
        root = tag.find_parent() or tag
        for token in labelled_by.split():
            target = root.find(id=token) if hasattr(root, "find") else None
            if target is not None and _text_of(target):
                return _text_of(target)
    if tag.name == "img":
        return (tag.get("alt") or "").strip()
    if tag.name == "input":
        value = (tag.get("value") or "").strip()
        if tag.get("type", "").lower() in ("submit", "button", "reset") and value:
            return value
    text = _text_of(tag)
    if text:
        return text
    # An icon-only control: a nested image's alt is the name.
    nested = tag.find("img") if hasattr(tag, "find") else None
    if nested is not None:
        return (nested.get("alt") or "").strip()
    return ""


class AccessibilityRule(Rule):
    """Base for this module, so the category is declared once rather than
    repeated on seventeen classes and eventually mistyped on one."""
    category = ACCESSIBILITY


class ImageAlt(AccessibilityRule):
    id = "image-alt"
    severity = CRITICAL
    wcag = ("1.1.1",)

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all("img"):
            if tag.has_attr("alt"):
                continue
            # A presentational image is announced as "image" with no name,
            # which is noise; an informative one loses its content entirely.
            # Static markup can't tell which this is, so the finding says
            # both and the fix offers the decorative form explicitly.
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector, line=line,
                snippet=snippet_of(tag), source=context.source,
                details={"src": (tag.get("src") or "")[:120]},
                fix_snippet=_with_attribute(tag, "alt", ""),
            ))
        return issues


_IMAGE_EXTENSION_RE = re.compile(r"\.(png|jpe?g|gif|svg|webp|avif)$", re.IGNORECASE)
# What a CMS appends to a stem: `-1024x683`, `-scaled`, `-e1700000000000`,
# a duplicate counter. None of it is part of what the author named the file.
_STEM_SUFFIX_RE = re.compile(r"(-\d+x\d+|-scaled|-e\d{6,}|-\d{1,2})+$")
# Words joined by hyphens or underscores with no space: `mappa-parlante-example`.
_SLUG_RE = re.compile(r"^[^\W_]+(?:[-_][^\W_]+){2,}$")
# A date, or a camera / export counter. Nothing a person would say aloud.
_COUNTER_ALT_RE = re.compile(
    r"^(?:\d{4}[-_.]\d{2}[-_.]\d{2}(?:[-_. ]\d+)*|"
    r"(?:img|dsc|dscn|dscf|pxl|image|immagine|screenshot|foto|photo)[-_ ]?\d+(?:[-_. ]\d+)*)$",
    re.IGNORECASE,
)


def _image_stem(src: str) -> str:
    """The file's name as an author typed it, comparable with an `alt`.

    Query string, directory and extension go; so do the size and counter
    suffixes a media library adds, because `Piazza-Grande-1024x683.jpg` is
    the file `Piazza-Grande.jpg` and the alt that matches either is the same
    mistake. Case and `_` / space are folded so `Piazza_Grande` still matches.
    """
    name = (src or "").split("#")[0].split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    name = _IMAGE_EXTENSION_RE.sub("", name)
    name = _STEM_SUFFIX_RE.sub("", name)
    return re.sub(r"[-_ ]+", "-", name).strip("-").lower()


class ImageAltIsFilename(AccessibilityRule):
    """An `alt` that is the file's name, or a slug somebody pasted in its place.

    `alt="hero-banner-2.png"` was always caught. The pattern that actually
    filled a WordPress media library was the same string without the
    extension: `mappa-parlante-example`, `Piazza-Grande`,
    `meccanica-della-fortezza`, and `2025-10-28`. Every "has alt" checker
    passes those, and a screen reader reads them out letter by letter.

    Two grades of certainty, because they are two different claims:

    * the `alt` **is the file's name** (extension, size suffix and case
      ignored): the markup settles it, so `EXACT`;
    * the `alt` only **looks like a slug** (three or more words joined by `-`
      or `_`, no space) or is a date or a camera counter: very likely, but
      `covid-19-vaccine` is a sentence nobody wrote with spaces, so a person
      decides - `ADVISORY`.

    Single words are never flagged on shape alone; `Logo` is a fine alt.
    """
    id = "image-alt-filename"
    severity = SERIOUS
    wcag = ("1.1.1",)

    _FILENAME_RE = re.compile(r"^[\w\-. ]+\.(png|jpe?g|gif|svg|webp|avif)$", re.IGNORECASE)

    def _kind(self, alt: str, src: str) -> str:
        # An unevaluated template expression (`{caption}`, `<%= @caption %>`)
        # is not text yet. The parser sees a masked placeholder, and two
        # placeholders of the same shape compared equal: an ERB page with a
        # bound `alt` and a bound `src` was reported as an alt that is its
        # file's name.
        if is_binding(alt):
            return ""
        if self._FILENAME_RE.match(alt):
            return "filename"
        # An alt with a space is prose, whatever else it looks like.
        if re.search(r"\s", alt):
            return ""
        stem = "" if is_binding(src) else _image_stem(src)
        folded = re.sub(r"[-_ ]+", "-", alt).strip("-").lower()
        if stem and folded == stem:
            return "filename"
        if _COUNTER_ALT_RE.match(alt) or _SLUG_RE.match(alt):
            return "slug"
        return ""

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all("img"):
            alt = (tag.get("alt") or "").strip()
            if not alt:
                continue
            kind = self._kind(alt, tag.get("src") or "")
            if not kind:
                continue
            # alt="hero-banner-2.png" passes every "has alt" checker and
            # tells the listener nothing, which is why it gets its own rule.
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector, line=line,
                snippet=snippet_of(tag), source=context.source,
                confidence=EXACT if kind == "filename" else ADVISORY,
                details={"alt": alt, "kind": kind},
            ))
        return issues


class ControlName(AccessibilityRule):
    id = "control-name"
    severity = CRITICAL
    wcag = ("4.1.2", "2.4.4")

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all(_INTERACTIVE):
            if tag.name == "input" and tag.get("type", "text").lower() in _UNLABELLED_INPUT_TYPES:
                continue
            if tag.name == "a" and not tag.has_attr("href"):
                continue  # an anchor without href is not a control
            if tag.name in ("input", "select", "textarea") and _has_label(tag, document):
                continue
            if _accessible_name(tag):
                continue
            if _is_hidden(tag):
                continue
            selector, line = context.locate(tag)
            component = context.syntax == "jsx" and _written_as_component(tag)
            if component and any((tag.get(prop) or "").strip()
                                 for prop in _COMPONENT_NAMING_PROPS):
                # `<Select label={t("lesson")}>` from a design system: the
                # parser lowercases it into a `<select>` with no name, and a
                # *critical* went out about a control whose component turns
                # `label` into `aria-labelledby`. What `Select` renders is
                # that component's business and this file cannot see it.
                continue
            # A component with no naming prop keeps the full weight: on
            # XFormat these were `<Input placeholder=…>`, and a placeholder
            # is not a name whatever `Input` renders.
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector,
                line=line, snippet=snippet_of(tag), source=context.source,
                details={"element": tag.name, "component": component},
            ))
        return issues


#: Props a component conventionally turns into an accessible name.
_COMPONENT_NAMING_PROPS = ("label", "aria-label", "aria-labelledby", "title",
                           "labelledby", "arialabel")


def _written_as_component(tag) -> bool:
    from .jsx import _is_component

    return _is_component(tag)


def _is_hidden(tag) -> bool:
    """Is this control outside the accessibility tree entirely?

    A control nobody can reach needs no name. The commonest case by far is
    the file input every upload button in the world hides and clicks
    programmatically - `<input type="file" hidden>`, or the same with
    `style="display:none"`. Measured on `XFormat`: `critical` findings
    about controls that are not controls, on the rule whose whole value is
    that a `critical` here is worth acting on.

    `aria-hidden` is checked on ancestors too: hiding a wrapper hides
    everything in it, and reporting the child is reporting the same
    decision the author already made.
    """
    if tag.has_attr("hidden"):
        return True
    style = (tag.get("style") or "").replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    for element in [tag, *tag.parents]:
        if getattr(element, "get", None) is None:
            continue
        if element.get("aria-hidden") == "true":
            return True
        if element.has_attr("hidden"):
            return True
    return False


def _has_label(tag, document) -> bool:
    """A form control is named by a <label> as well as by its own attributes."""
    if tag.find_parent("label") is not None:
        return True
    control_id = tag.get("id")
    if not control_id:
        return False
    for label in document.find_all("label"):
        # `htmlFor` is React's spelling of the same attribute, and an HTML
        # parser lowercases it. Reading only `for` made every labelled JSX
        # field look unlabelled.
        target = label.get("for") or label.get("htmlfor")
        if target == control_id and _text_of(label):
            return True
    return False


class VagueLinkText(AccessibilityRule):
    id = "link-text-vague"
    severity = MODERATE
    wcag = ("2.4.4",)

    def check(self, document, context) -> list:
        issues = []
        vague = set()
        for words in _VAGUE_LINK_TEXT.values():
            vague |= words
        for tag in document.find_all("a", href=True):
            text = _text_of(tag).lower().strip(" .!?:»«\"'")
            if not text or text not in vague:
                continue
            # 2.4.4 is "Link Purpose **in Context**", and `title` is one of
            # the context mechanisms the criterion names. `<a title="More
            # Events">More</a>` on `python.org` says what the link is for;
            # calling it vague is applying 2.4.9 (link text alone, AAA) and
            # citing 2.4.4 for it. The title has to add something - repeating
            # the text is not context.
            title = (tag.get("title") or "").strip()
            if title and title.lower() != text:
                continue
            # Screen reader users navigate by pulling up a list of every link
            # on the page, out of context. Fifteen entries reading "read
            # more" is a list of fifteen identical, useless choices.
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector, line=line,
                snippet=snippet_of(tag), source=context.source,
                details={"text": _text_of(tag), "href": (tag.get("href") or "")[:120]},
            ))
        return issues


class DocumentLanguage(AccessibilityRule):
    id = "html-lang"
    page_level = True
    severity = SERIOUS
    wcag = ("3.1.1",)

    def check(self, document, context) -> list:
        html = document.find("html")
        if html is None:
            return []  # a fragment, not a document — nothing to declare on
        lang = (html.get("lang") or "").strip()
        if lang:
            return []
        selector, line = context.locate(html)
        return [Issue(
            rule_id=self.id, severity=self.severity, selector=selector, line=line,
            snippet=snippet_of(html), source=context.source, details={},
            fix_snippet='<html lang="uk">',
        )]


class DocumentLanguageMismatch(AccessibilityRule):
    """The page declares one language and is written in another.

    `html-lang` asks whether the attribute is there. This asks whether it is
    *true*, which is what 3.1.1 is actually about: a screen reader trusts the
    attribute completely, so `lang="en"` over Ukrainian copy is read out with
    English phonetics and is worse than no attribute at all - with none, the
    reader falls back to the user's own setting.

    Both halves already existed and had never been introduced: the audit
    knew the declared language and `lang_detect.guess_language_safe` was
    reading the real one for the text detectors two modules away.

    Deliberately silent in two cases, and the second is the important one:

    * Not enough text to tell. `guess_language_safe` answers `None` there
      rather than guessing, and this passes it straight through.
    * **Whenever the detector's answer is English.** It has no "some fourth
      language" verdict - anything non-Cyrillic with no Italian markers comes
      back `en` - so `lang="de"` on a German page would be reported as a lie.
      Ukrainian is decided by the share of Cyrillic letters and Italian by
      its own markers, and those two are evidence; English is a default
      wearing the same coat. See the language step in the hunting plan.
    """
    id = "html-lang-mismatch"
    page_level = True
    severity = SERIOUS
    wcag = ("3.1.1",)

    #: Below this the page is a shell or a menu, and no detector should be
    #: asked. The threshold is in words because that is what the detector
    #: measures.
    MIN_WORDS = 40

    def check(self, document, context) -> list:
        from lang_detect import UNSUPPORTED, guess_language_safe

        html = document.find("html")
        if html is None:
            return []
        declared = (html.get("lang") or "").strip().lower()
        if not declared:
            return []  # `html-lang` already reports the absence
        body = document.find("body")
        text = _text_of(body) if body is not None else ""
        if len(text.split()) < self.MIN_WORDS:
            return []
        # Read twice, on the two halves of the page, and report only when
        # both readings agree. A single stray word is what makes a long
        # English page look Italian - "per user", "che" in a quoted name -
        # and a stray word lands in one half, not in both. The same
        # corroboration the audit already asks of two engines, asked of one
        # detector on two samples.
        words = text.split()
        middle = len(words) // 2
        readings = (guess_language_safe(" ".join(words[:middle])),
                    guess_language_safe(" ".join(words[middle:])),
                    guess_language_safe(text))
        detected = readings[-1]
        # UNSUPPORTED is not a language code: proposing `<html lang="other">`
        # would be this rule writing a fact it does not have.
        if (detected in (None, "en", UNSUPPORTED)
                or any(r != detected for r in readings)):
            return []
        if declared.split("-")[0] == detected:
            return []
        selector, line = context.locate(html)
        return [Issue(
            rule_id=self.id, severity=self.severity, selector=selector, line=line,
            snippet=snippet_of(html), source=context.source,
            details={"declared": declared, "detected": detected,
                     "sample": text[:120]},
            fix_snippet=f'<html lang="{detected}">',
        )]


#: A language subtag as BCP 47 writes it: two or three letters, optionally
#: followed by a script or region. Kept permissive on purpose - the rule
#: never acts on one signal alone, so a false read of a single path segment
#: cannot produce a finding by itself.
_LANGUAGE_TAG_RE = re.compile(r"^([a-z]{2,3})(?:[-_][a-z0-9]{2,8})*$", re.I)
#: Query parameters that carry a language, in the spellings actually used by
#: CMSes and by Google's own tooling.
_LANGUAGE_QUERY_KEYS = ("lang", "language", "hl", "locale", "l")


def _primary_subtag(value) -> str:
    """`de-DE`, `de_DE`, `DE` -> `de`; anything not a language tag -> ``.

    Comparing whole tags would call `de-AT` a contradiction of `de-DE`, which
    is a regional variant and not a wrong language.
    """
    text = (value or "").strip()
    if not text:
        return ""
    match = _LANGUAGE_TAG_RE.match(text)
    return match.group(1).lower() if match else ""


def _language_from_address(url: str) -> dict:
    """Language codes the address itself names, by where they were found.

    Three layouts are in use and a site may combine them, so all three are
    read: `example.com/de/page`, `de.example.com/page`, `example.com/page?lang=de`.
    """
    from urllib.parse import parse_qs, urlsplit

    found: dict = {}
    if not url or "://" not in url:
        return found  # a repository path, not an address
    parts = urlsplit(url)

    segments = [seg for seg in (parts.path or "").split("/") if seg]
    if segments:
        code = _primary_subtag(segments[0])
        if code:
            found["path prefix"] = code

    host_labels = (parts.hostname or "").split(".")
    if len(host_labels) > 2:
        code = _primary_subtag(host_labels[0])
        if code:
            found["subdomain"] = code

    query = parse_qs(parts.query or "")
    for key in _LANGUAGE_QUERY_KEYS:
        for spelling in (key, key.upper()):
            values = query.get(spelling)
            if values:
                code = _primary_subtag(values[0])
                if code:
                    found["query parameter"] = code
                break
        if "query parameter" in found:
            break
    return found


def _language_from_open_graph(document) -> str:
    """`<meta property="og:locale" content="de_DE">` -> `de`."""
    for tag in document.find_all("meta"):
        key = (tag.get("property") or tag.get("name") or "").strip().lower()
        if key == "og:locale":
            return _primary_subtag(tag.get("content"))
    return ""


def _language_from_self_hreflang(document, url: str) -> str:
    """The language the page's own `hreflang` set gives to this address.

    A correct `hreflang` set includes the page itself. That self-entry is a
    statement by the site about this page and nothing else, which makes it a
    signal independent of the address.
    """
    if not url:
        return ""
    from urllib.parse import urljoin, urlsplit

    def shape(value: str) -> tuple:
        parsed = urlsplit(value)
        path = (parsed.path or "/").rstrip("/") or "/"
        return (parsed.netloc.lower(), path)

    here = shape(url)
    for tag in document.find_all("link", href=True):
        rels = tag.get("rel") or []
        if isinstance(rels, str):
            rels = [rels]
        if "alternate" not in [str(r).lower() for r in rels]:
            continue
        language = (tag.get("hreflang") or "").strip().lower()
        if not language or language == "x-default":
            continue
        if shape(urljoin(url, tag["href"])) == here:
            return _primary_subtag(language)
    return ""


def _language_signals(document, url: str) -> dict:
    """Every independent statement about this page's language, by source."""
    signals = _language_from_address(url)
    # The address can name the same language twice (a `/de/` path under a
    # `de.` subdomain). That is one statement wearing two hats, not two
    # witnesses, so the corroboration count collapses them.
    if len(set(signals.values())) == 1 and len(signals) > 1:
        signals = {"address": next(iter(signals.values()))}

    open_graph = _language_from_open_graph(document)
    if open_graph:
        signals["og:locale"] = open_graph
    self_hreflang = _language_from_self_hreflang(document, url)
    if self_hreflang:
        signals["hreflang self-entry"] = self_hreflang
    return signals


class DeclaredLanguageContradictsAddress(AccessibilityRule):
    """The page declares one language while the site says it is another.

    `html-lang-mismatch` asks the text. That answer needs a detector, and a
    detector only knows the languages it was taught: `lang_detect` returns
    `uk`, `it`, `en` or `other`, so a German page comes back `other` and the
    rule stays silent by design. A whole site can therefore serve every page
    with the wrong `lang` and no rule notices - which is exactly what a real
    audit found: sixty-five pages of a three-language site all declaring
    `lang="it"`, the German ones included.

    This rule asks the site instead of the text, so it holds for any
    language, including ones no detector here knows. Three independent
    places already name the language of a page:

    * the address - a path prefix (`/de/…`), a subdomain (`de.example.com`)
      or a query parameter (`?lang=de`);
    * `og:locale`;
    * the page's own entry in its `hreflang` set.

    **Two of them must agree before this speaks.** One alone is not
    evidence: `/de/` can be a Spanish preposition in a path, and a single
    stray `og:locale` is a typo rather than a policy. Two independent
    sources naming the same language, against a third that says something
    else, is the shape of a forgotten attribute - and the same corroboration
    the sibling rule asks of one detector on two samples.
    """
    id = "html-lang-contradicts-address"
    page_level = True
    web_only = True
    severity = SERIOUS
    wcag = ("3.1.1",)

    #: Enough agreement to speak. See the class docstring.
    MIN_AGREEING_SIGNALS = 2

    def check(self, document, context) -> list:
        html = document.find("html")
        if html is None:
            return []
        declared = _primary_subtag(html.get("lang"))
        if not declared:
            return []  # `html-lang` already reports the absence

        signals = _language_signals(document, context.source)
        if not signals:
            return []
        agreed = {code for code in signals.values() if code}
        if len(agreed) != 1:
            return []  # the sources disagree: this rule has no verdict
        expected = agreed.pop()
        if expected == declared:
            return []
        naming = sorted(name for name, code in signals.items() if code == expected)
        if len(naming) < self.MIN_AGREEING_SIGNALS:
            return []

        selector, line = context.locate(html)
        return [Issue(
            rule_id=self.id, severity=self.severity, selector=selector, line=line,
            snippet=snippet_of(html), source=context.source,
            details={"declared": declared, "expected": expected,
                     # The sentence names how many witnesses there are. Two
                     # is the minimum, not the number: a page can carry a
                     # path prefix, an `og:locale` and a self-`hreflang` at
                     # once, and a report that says "two" while listing
                     # three is wrong about its own evidence.
                     "count": len(naming),
                     "signals": ", ".join(naming)},
            fix_snippet=f'<html lang="{expected}">',
        )]


class DocumentTitle(AccessibilityRule):
    id = "document-title"
    page_level = True
    severity = SERIOUS
    wcag = ("2.4.2",)

    def check(self, document, context) -> list:
        if document.find("html") is None:
            return []
        title = document.find("title")
        if title is not None and _text_of(title):
            return []
        return [Issue(
            rule_id=self.id, severity=self.severity, source=context.source,
            snippet="<head>…</head>", details={"present": title is not None},
        )]


class HeadingOrder(AccessibilityRule):
    id = "heading-order"
    severity = MODERATE
    wcag = ("1.3.1", "2.4.6")

    def check(self, document, context) -> list:
        issues = []
        headings = [h for h in document.find_all(re.compile(r"^h[1-6]$"))
                    if _text_of(h)]
        previous = 0
        seen: list = []
        for heading in headings:
            level = int(heading.name[1])
            if context.syntax == "jsx":
                # The heading before this one *in the same render*. An early
                # `return` with its own h1, or the other arm of a
                # conditional, is never on screen with this heading, and
                # comparing the two reported jumps no page has. A component
                # that starts at h3 is still fine: the first heading of a
                # render is compared with nothing, because its level depends
                # on the page that places it.
                previous = next((int(h.name[1]) for h in reversed(seen)
                                 if not jsx_exclusive(h, heading)), 0)
                seen.append(heading)
            if previous and level > previous + 1:
                # Headings are how a screen reader user skims. A jump from h2
                # to h4 reads as a missing section, not as a design choice.
                selector, line = context.locate(heading)
                issues.append(Issue(
                    rule_id=self.id, severity=self.severity, selector=selector,
                    line=line, snippet=snippet_of(heading), source=context.source,
                    details={"from": previous, "to": level, "text": _text_of(heading)[:80]},
                    fix_snippet=f"<h{previous + 1}>{_text_of(heading)[:60]}</h{previous + 1}>",
                ))
            previous = level
        return issues


class MissingH1(AccessibilityRule):
    id = "page-has-h1"
    page_level = True
    severity = MODERATE
    wcag = ("1.3.1",)

    def check(self, document, context) -> list:
        if document.find("html") is None:
            return []
        h1s = [h for h in document.find_all("h1") if _text_of(h)]
        if len(h1s) == 1:
            return []
        return [Issue(
            rule_id=self.id, severity=self.severity, source=context.source,
            snippet="<body>…</body>", details={"count": len(h1s)},
        )]


class PositiveTabindex(AccessibilityRule):
    id = "tabindex-positive"
    severity = SERIOUS
    wcag = ("2.4.3",)

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all(attrs={"tabindex": True}):
            try:
                value = int((tag.get("tabindex") or "0").strip())
            except ValueError:
                continue
            if value <= 0:
                continue
            # A positive tabindex pulls the element out of document order and
            # in front of everything with tabindex 0 — including the skip
            # link. One such element re-orders the whole page's keyboard path.
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector, line=line,
                snippet=snippet_of(tag), source=context.source,
                details={"value": value, "element": tag.name},
                fix_snippet=_with_attribute(tag, "tabindex", "0"),
            ))
        return issues


class DuplicateIds(AccessibilityRule):
    id = "duplicate-id"
    severity = MODERATE
    # 4.1.1 Parsing, which this used to name, is not in WCAG 2.2. A duplicate
    # id is still a defect where a `for`, `aria-*` or `url(#id)` points at it,
    # but the standard no longer says so, and a report must not cite it.
    wcag = ()

    def check(self, document, context) -> list:
        seen: dict = {}
        issues = []
        for tag in document.find_all(id=True):
            identifier = (tag.get("id") or "").strip()
            if not identifier:
                continue
            if is_binding(identifier):
                # `id={m.id}` is one expression that yields a different id per
                # render, and a list renders it many times. Comparing the
                # source text makes every row after the first a duplicate of
                # itself, which is a statement about the file rather than
                # about the page. Same reasoning as `bp-inline-handlers` and
                # `onClick={close}`; found on `ChatMessageRenderer.tsx` and
                # `SettingsCollapsible.tsx` once repo mode could read `.tsx`.
                continue
            if identifier in seen and context.syntax == "jsx" and all(
                    jsx_exclusive(earlier, tag) for earlier in seen[identifier]):
                # The sign-in and the sign-up arm of one page each write
                # `<h1 id="auth-title">`, and only one of them renders. The
                # parser sees both; the source says they cannot meet.
                # Measured on `apps/coach/src`: 17 of 25 problems.
                seen[identifier].append(tag)
                continue
            if identifier in seen:
                # `for`, `aria-labelledby` and `aria-describedby` all resolve
                # to the *first* match, so a duplicate silently points every
                # reference at one element and leaves the other unnamed.
                #
                # Inside `<svg>` it is a different weight. `url(#id)` resolves
                # the same way, but the usual cause is one exported icon
                # placed twice, whose two `<filter>` or `<mask>` definitions
                # are identical - the rendering is right and the markup is
                # not. 130 of these on a sixteen-target run sat beside real
                # duplicate form ids at the same severity, which is what made
                # the real ones hard to see.
                in_svg = tag.find_parent("svg") is not None
                selector, line = context.locate(tag)
                issues.append(Issue(
                    rule_id=self.id,
                    severity=MINOR if in_svg else self.severity,
                    selector=selector,
                    line=line, snippet=snippet_of(tag), source=context.source,
                    details={"id": identifier, "in_svg": in_svg},
                ))
            seen.setdefault(identifier, []).append(tag)
        return issues


class BrokenAriaReference(AccessibilityRule):
    id = "aria-reference-broken"
    severity = SERIOUS
    wcag = ("1.3.1", "4.1.2")

    _REFERENCING = ("aria-labelledby", "aria-describedby", "aria-controls", "aria-owns")

    #: A name has to exist whenever the element does, so a dangling
    #: `aria-labelledby` is a fact about the page as served. What an element
    #: *controls* is routinely created on demand - a dropdown Alpine renders
    #: on click, a Wix search panel that appears on focus - and a fetched
    #: page has not clicked anything. Measured on `wix.com` and a Shopify
    #: store: every `aria-controls` finding pointed at markup a browser would
    #: have. Reported at a weight that says the pass could not settle it,
    #: which `--confidence exact` then drops.
    _NEEDS_A_BROWSER = ("aria-controls", "aria-owns")

    def check(self, document, context) -> list:
        issues = []
        ids = {tag.get("id") for tag in document.find_all(id=True)}
        id_expressions = None
        for attribute in self._REFERENCING:
            for tag in document.find_all(attrs={attribute: True}):
                expression = (attribute_expression(tag, attribute)
                              if is_binding(tag.get(attribute) or "") else "")
                if expression:
                    if id_expressions is None:
                        id_expressions = _id_expressions(document)
                    verdict = _expression_reference(expression, ids, id_expressions)
                    if verdict == "resolved":
                        continue
                    if verdict == "unknown":
                        # `aria-labelledby={labelledBy}`: a prop, whose value
                        # is decided by whoever renders this. Nothing here can
                        # call it broken; the rendered page can.
                        selector, line = context.locate(tag)
                        issues.append(Issue(
                            rule_id=self.id, severity=MINOR,
                            confidence=NEEDS_BROWSER, selector=selector,
                            line=line, snippet=snippet_of(tag),
                            source=context.source,
                            details={"attribute": attribute, "missing": [],
                                     "value": expression[:120],
                                     "dynamic": True, "has_space": False}))
                        continue
                    missing = verdict
                elif _INTERPOLATION.search(tag.get(attribute) or ""):
                    # `aria-labelledby="fm-{{ $group['key'] }}"`: a server or
                    # client template prints part of the id. Split on spaces
                    # it became `fm-{{`, `$group['key']` and `}}` - three ids
                    # nobody wrote, reported serious against a heading that
                    # carries the same template one line below (no-press,
                    # Blade). The same template as an id resolves; anything
                    # else only the rendered page can answer.
                    raw = (tag.get(attribute) or "").strip()
                    if raw in ids:
                        continue
                    selector, line = context.locate(tag)
                    issues.append(Issue(
                        rule_id=self.id, severity=MINOR,
                        confidence=NEEDS_BROWSER, selector=selector,
                        line=line, snippet=snippet_of(tag),
                        source=context.source,
                        details={"attribute": attribute, "missing": [],
                                 "value": raw[:120], "dynamic": True,
                                 "has_space": False}))
                    continue
                else:
                    missing = [token for token in (tag.get(attribute) or "").split()
                               if token not in ids]
                if not missing:
                    continue
                # A dangling aria-labelledby is worse than none: the element
                # ends up with no name at all, and the markup looks correct.
                selector, line = context.locate(tag)
                raw = (tag.get(attribute) or "").strip()
                # An id cannot contain whitespace, so a value that does can
                # never resolve however the page is rendered: that one is
                # settled from the markup alone.
                unsettled = (attribute in self._NEEDS_A_BROWSER
                             and " " not in raw)
                issues.append(Issue(
                    rule_id=self.id,
                    severity=MODERATE if unsettled else self.severity,
                    confidence=NEEDS_BROWSER if unsettled else EXACT,
                    selector=selector,
                    line=line, snippet=snippet_of(tag), source=context.source,
                    # The raw value as well as the tokens. An author who wrote
                    # `aria-labelledby="dialog_Privacy policy"` meant one name
                    # with a space in it, and an id cannot contain one - so the
                    # finding is right and the list of "missing ids" reads like
                    # the tool misparsed it. Quoting the value says which it is.
                    details={"attribute": attribute, "missing": missing,
                             "value": raw[:120],
                             "has_space": " " in raw},
                ))
        return issues


#: A template printing part of an attribute value: Blade, Twig, Vue and
#: Handlebars `{{ }}`, a template literal's `${}`, ERB's `<% %>`, Jinja's
#: `{% %}`, and the `${---}` filler `mask_server_tags` leaves for PHP.
_INTERPOLATION = re.compile(r"\{\{|\$\{|<%|\{%")

_STRING_LITERAL = re.compile(r"\"([^\"]*)\"|'([^']*)'")
_TEMPLATE_LITERAL = re.compile(r"`[^`]*`")


def _normal_expression(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _id_expressions(document) -> set:
    """The JS expressions `id={…}` is written with in this file."""
    found = set()
    for tag in document.find_all(id=True):
        if is_binding(tag.get("id") or ""):
            expression = attribute_expression(tag, "id")
            if expression:
                found.add(_normal_expression(expression))
    return found


def _expression_reference(expression: str, ids: set, id_expressions: set):
    """What an `aria-*={…}` expression points at, as far as the file shows.

    "resolved" when one of the values it can take is an id this file has -
    a literal (`cond ? "title" : undefined`), a template literal written the
    same way as an element's `id={…}`, or the very expression an element's
    id is (`aria-labelledby={titleId}` beside `id={titleId}`). The list of
    missing ids when it only offers literals and none exists. "unknown"
    when nothing in it can be read without running it.
    """
    whole = _normal_expression(expression)
    if whole in id_expressions:
        return "resolved"
    templates = [_normal_expression(m) for m in _TEMPLATE_LITERAL.findall(expression)]
    if any(template in id_expressions or "{" + template + "}" in id_expressions
           for template in templates):
        return "resolved"
    literals = [one or two for one, two in _STRING_LITERAL.findall(
        _TEMPLATE_LITERAL.sub("", expression))]
    literals = [value for value in literals if value.strip()]
    if any(all(token in ids for token in value.split()) for value in literals):
        return "resolved"
    if literals and not templates:
        return [token for value in literals for token in value.split()
                if token not in ids]
    return "unknown"


class ButtonWithoutType(AccessibilityRule):
    id = "button-type"
    severity = MINOR
    wcag = ()

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all("button"):
            if tag.get("type"):
                continue
            if tag.find_parent("form") is None:
                continue
            # Inside a form a button defaults to type="submit", so an
            # icon-only "clear" button submits the form on Enter.
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector, line=line,
                snippet=snippet_of(tag), source=context.source, details={},
                fix_snippet=_with_attribute(tag, "type", "button"),
            ))
        return issues


class MediaWithoutCaptions(AccessibilityRule):
    id = "media-captions"
    severity = SERIOUS
    confidence = NEEDS_BROWSER
    wcag = ("1.2.2",)

    @staticmethod
    def _is_decorative_background(tag) -> bool:
        """A muted, looping, uncontrollable video has no audio to caption.

        1.2.2 is about the audio of synchronised media. The background video
        idiom - `<video autoplay muted loop playsinline>` with no `controls`
        - plays no sound and gives the visitor no way to turn any on, so
        there is nothing for a caption to carry. `media-autoplay` next door
        already exempts the same element for the same reason.

        Measured 2026-09-01 on a live site: the hero video on every page of
        it was reported at `serious` for missing captions it cannot use.
        What such a video *does* need is a text alternative for what it
        shows, which is 1.2.1 and 1.2.3 and a different question from this
        one.
        """
        return (tag.name == "video"
                and tag.has_attr("muted")
                and tag.has_attr("autoplay")
                and not tag.has_attr("controls"))

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all(("video", "audio")):
            if self._is_decorative_background(tag):
                continue
            tracks = tag.find_all("track")
            if any((t.get("kind") or "").lower() in ("captions", "subtitles") for t in tracks):
                continue
            # Tracks added by a player's JavaScript are invisible here, hence
            # needs-browser: this finds the markup-only case honestly and
            # says the rest needs checking in a browser.
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector, line=line,
                snippet=snippet_of(tag), source=context.source, confidence=self.confidence,
                details={"element": tag.name, "tracks": len(tracks)},
            ))
        return issues


#: Hosts whose player is embedded as an `<iframe>`, so `media-captions`
#: (which reads `<video>` and `<audio>`) never sees them.
_VIDEO_HOSTS = {
    "youtube.com": "YouTube", "youtube-nocookie.com": "YouTube", "youtu.be": "YouTube",
    "vimeo.com": "Vimeo", "dailymotion.com": "Dailymotion",
    "wistia.com": "Wistia", "wistia.net": "Wistia",
    "brightcove.net": "Brightcove",
}
_TRANSCRIPT_RE = re.compile(
    r"transcript|transcription|trascrizion|transkript|транскрип|стенограм",
    re.IGNORECASE)


def _video_provider(src: str) -> str:
    from urllib.parse import urlsplit
    host = (urlsplit(src or "").netloc or "").lower().split(":")[0]
    for suffix, name in _VIDEO_HOSTS.items():
        if host == suffix or host.endswith("." + suffix):
            return name
    return ""


class EmbeddedVideoAlternatives(AccessibilityRule):
    """A hosted video player is an `<iframe>`, and nothing here can look inside.

    `media-captions` answers for `<video>` and `<audio>`. A YouTube or Vimeo
    embed is neither: the markup holds an address, and whether the video has
    captions, a transcript or an audio description is a fact about a file on
    another server. Measured by hand on a tourism site: a five-minute narrated
    video embedded on a page, with only YouTube's auto-generated captions, no
    transcript on the page and no audio description - and every automated
    engine silent, because the iframe had a perfectly good `title`.

    So this cannot say the video fails. It says there is a video whose three
    alternatives (1.2.2 captions, 1.2.3 transcript or description, 1.2.5
    audio description) the page itself does not answer, and that a person has
    to check the hosted file. Hence `ADVISORY`: no browser will settle it
    either. A page that carries a transcript is noted as such in the finding;
    that closes one of the three, not all of them.
    """
    id = "embedded-video-alternatives"
    severity = MODERATE
    confidence = ADVISORY
    wcag = ("1.2.2", "1.2.3", "1.2.5")

    @staticmethod
    def _is_background(src: str) -> bool:
        """A muted, controls-less embed is the background-video idiom: no
        audio to caption, same exemption `media-captions` gives `<video>`."""
        query = (src.split("?", 1) + [""])[1].lower()
        params = dict(p.split("=", 1) if "=" in p else (p, "") for p in query.split("&") if p)
        return params.get("controls") == "0" and params.get("mute") == "1"

    def check(self, document, context) -> list:
        page_text = document.get_text(" ", strip=True) if hasattr(document, "get_text") else ""
        has_transcript = bool(_TRANSCRIPT_RE.search(page_text))
        issues = []
        for tag in document.find_all("iframe"):
            src = (tag.get("src") or tag.get("data-src") or "").strip()
            provider = _video_provider(src)
            if not provider or self._is_background(src):
                continue
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector, line=line,
                snippet=snippet_of(tag), source=context.source, confidence=self.confidence,
                details={"provider": provider, "src": src[:160],
                         "transcript": has_transcript},
            ))
        return issues


#: What a button that appends results to the page is called, in the languages
#: this tool answers in and the ones its test sites are written in. Matched
#: against the visible text, `id` and `class` together, because the label is
#: often an icon and the class is the only honest name.
_LOAD_MORE_RE = re.compile(
    r"load[-_ ]?more|loadmore|show[-_ ]?more|more[-_ ]results|"
    r"carica[-_ ]?(?:altri|altre|più|piu|ancora)|mostra[-_ ]?(?:altri|altre|di[-_ ]?pi[uù]|ancora)|"
    r"altri[-_ ]risultati|mehr[-_ ]?(?:laden|anzeigen|ergebnisse)|"
    r"weitere[-_ ]?(?:laden|ergebnisse)|завантажити ще|показати ще",
    re.IGNORECASE)


class StatusMessageLiveRegion(AccessibilityRule):
    """Results that arrive without a page load, announced to nobody.

    A "load more" button replaces or appends content over AJAX, and the
    messages around it - "loading", "showing 12 of 40", "no more results" -
    are status messages in the sense of 4.1.3: they change what is on screen
    without moving focus. Without a live region a screen reader says nothing
    and the visitor does not learn that anything happened. Found by hand on a
    live site, where the button swapped the whole results container and the
    "no more results" sentence appeared by dropping a CSS class.

    Static markup cannot see what the script writes, so this reports only the
    structural half: a document that has such a trigger and **no live region
    anywhere** (`aria-live`, `role="status"`, `role="alert"`, `role="log"`,
    `<output>`). A page that has one may still announce nothing useful, and
    that is why this is advisory and not exact.
    """
    id = "status-message-live-region"
    severity = MODERATE
    confidence = ADVISORY
    wcag = ("4.1.3",)
    page_level = True

    @staticmethod
    def _has_live_region(document) -> bool:
        if document.find(attrs={"aria-live": lambda v: v and v.strip().lower() != "off"}):
            return True
        if document.find(attrs={"role": ["status", "alert", "log"]}):
            return True
        return document.find("output") is not None

    def check(self, document, context) -> list:
        triggers = []
        for tag in document.find_all(("button", "a", "input")):
            if tag.name == "input" and (tag.get("type") or "").lower() not in ("button", "submit"):
                continue
            label = " ".join([
                _text_of(tag) if tag.name != "input" else (tag.get("value") or ""),
                (tag.get("aria-label") or ""), (tag.get("id") or ""),
                " ".join(tag.get("class") or []),
            ])
            if _LOAD_MORE_RE.search(label):
                triggers.append(tag)
        if not triggers or self._has_live_region(document):
            return []
        issues = []
        for tag in triggers:
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector, line=line,
                snippet=snippet_of(tag), source=context.source, confidence=self.confidence,
                details={"element": tag.name},
                fix_snippet='<p role="status" aria-live="polite" class="visually-hidden"></p>',
            ))
        return issues


class AutoplayingMedia(AccessibilityRule):
    id = "media-autoplay"
    severity = SERIOUS
    wcag = ("1.4.2",)

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all(("video", "audio")):
            if not tag.has_attr("autoplay"):
                continue
            if tag.has_attr("muted") and tag.name == "video":
                continue
            if tag.has_attr("controls"):
                continue
            # Sound the visitor did not ask for, with no way to stop it,
            # covers a screen reader's own speech.
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector, line=line,
                snippet=snippet_of(tag), source=context.source,
                details={"element": tag.name},
                fix_snippet=_with_attribute(tag, "controls", ""),
            ))
        return issues


class TableStructure(AccessibilityRule):
    id = "table-headers"
    severity = SERIOUS
    wcag = ("1.3.1",)

    #: Attributes that mean "this table is drawing a layout". A data table
    #: does not switch its borders and spacing off: the idiom below is the
    #: one every HTML email and every 2005 page is built from.
    _LAYOUT_ATTRS = ("cellpadding", "cellspacing", "border")

    @classmethod
    def _is_layout(cls, table) -> bool:
        """Is this table drawing a layout rather than holding data?

        `role="presentation"` says so outright, and everything below is for
        the tables that do not say it. Measured 2026-09-01 on a workspace of
        Beehiiv and Ghost deliverables: **47** findings of this rule, at
        `serious`, every one of them against
        `<table width="100%" cellpadding="0" cellspacing="0" border="0">` -
        the wrapper an email is laid out in. A layout table has no headers
        to be missing, so the rule was reporting the absence of something
        that must not be there.

        Three questions, each one a thing a data table does not do: declare
        itself presentational, switch its borders and spacing off, or wrap
        another table.

        A fourth was measured and dropped: "every row holds one cell". It
        catches the same emails and it also catches a one-column list of
        values, which is a data table with a missing header - the thing this
        rule exists to find. The three above cover all 47 real findings
        without that trade.
        """
        if str(table.get("role") or "").lower() in ("presentation", "none"):
            return True
        if table.find("th") is not None or table.find("caption") is not None:
            return False
        attributes = [a for a in cls._LAYOUT_ATTRS if table.get(a) is not None]
        if len(attributes) >= 2 and str(table.get("border", "")).strip() in ("0", ""):
            return True
        return table.find("table") is not None

    def check(self, document, context) -> list:
        issues = []
        for table in document.find_all("table"):
            if self._is_layout(table):
                continue
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue  # a one-row table is layout, not data
            if table.find("th") is not None:
                continue
            # Without <th>, every cell is announced as a bare value with no
            # indication of which column it belongs to.
            selector, line = context.locate(table)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector, line=line,
                snippet=snippet_of(table), source=context.source,
                details={"rows": len(rows)},
            ))
        return issues


class ViewportZoomBlocked(AccessibilityRule):
    id = "viewport-zoom"
    page_level = True
    severity = SERIOUS
    wcag = ("1.4.4",)

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all("meta"):
            if (tag.get("name") or "").lower() != "viewport":
                continue
            content = (tag.get("content") or "").lower()
            blocked = "user-scalable=no" in content.replace(" ", "")
            capped = re.search(r"maximum-scale\s*=\s*(1(\.0+)?|0?\.\d+)\b", content)
            if not blocked and not capped:
                continue
            # Blocking zoom is a one-line meta tag that makes the site
            # unusable for anyone who needs larger text.
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector, line=line,
                snippet=snippet_of(tag), source=context.source,
                details={"content": content[:120]},
                fix_snippet='<meta name="viewport" content="width=device-width, initial-scale=1">',
            ))
        return issues


class InlineContrast(AccessibilityRule):
    id = "contrast-inline"
    severity = SERIOUS
    confidence = NEEDS_BROWSER
    wcag = ("1.4.3",)

    _COLOR_RE = re.compile(r"(^|;)\s*color\s*:\s*([^;]+)", re.IGNORECASE)
    _BG_RE = re.compile(r"(^|;)\s*background(?:-color)?\s*:\s*([^;]+)", re.IGNORECASE)

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all(style=True):
            style = tag.get("style") or ""
            foreground = self._COLOR_RE.search(style)
            background = self._BG_RE.search(style)
            if not foreground or not background:
                continue  # only judgeable when both are on the same element
            fg = _parse_color(foreground.group(2))
            bg = _parse_color(background.group(2))
            if fg is None or bg is None:
                continue
            ratio = contrast_ratio(fg, bg)
            if ratio >= 4.5:
                continue
            # Only inline pairs are checkable without a browser; the real
            # contrast of the page comes from the cascade, which this pass
            # cannot see. Hence needs-browser, and hence "found in the
            # markup" rather than "the page fails contrast".
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector, line=line,
                snippet=snippet_of(tag), source=context.source, confidence=self.confidence,
                details={"ratio": round(ratio, 2), "foreground": foreground.group(2).strip(),
                         "background": background.group(2).strip(), "required": 4.5},
            ))
        return issues


def _style_sources(document) -> list:
    """Every (element, css_text) pair holding style declarations: inline
    `style` attributes plus the contents of <style> blocks. Stylesheet
    files need the browser pass; these two cover what the markup ships."""
    pairs = [(tag, tag.get("style") or "") for tag in document.find_all(style=True)]
    for block in document.find_all("style"):
        pairs.append((block, block.get_text() or ""))
    return pairs


def _strip_small_screen_media(css: str) -> str:
    """Drop @media blocks scoped to narrow screens (`max-width` up to
    900px): those declarations exist to FIX phone layouts, and reporting
    them as hazards would punish exactly the right fix."""
    out = []
    pos = 0
    while True:
        start = css.find("@media", pos)
        if start == -1:
            out.append(css[pos:])
            break
        out.append(css[pos:start])
        brace = css.find("{", start)
        if brace == -1:
            break
        depth = 1
        end = brace + 1
        while end < len(css) and depth:
            if css[end] == "{":
                depth += 1
            elif css[end] == "}":
                depth -= 1
            end += 1
        block = css[start:end]
        limit = re.search(r"max-width\s*:\s*(\d+)px", block)
        if limit and int(limit.group(1)) <= 900:
            pass  # mobile-scoped: ignore its declarations
        else:
            out.append(block)
        pos = end
    return "".join(out)


class FixedPixelWidth(AccessibilityRule):
    id = "viewport-fixed-width"
    severity = MODERATE
    confidence = NEEDS_BROWSER
    wcag = ("1.4.10",)

    #: Anchored so `max-width` / `min-width` never match: those are the fix,
    #: not the bug.
    _WIDTH_RE = re.compile(r"(?:^|;|\{)\s*width\s*:\s*(\d+(?:\.\d+)?)px",
                           re.IGNORECASE)

    def check(self, document, context) -> list:
        issues = []
        for tag, css in _style_sources(document):
            css = _strip_small_screen_media(css)
            for found in self._WIDTH_RE.finditer(css):
                px = float(found.group(1))
                if px < 600:
                    continue  # fits a 390px phone with margin for chrome
                selector, line = context.locate(tag)
                issues.append(Issue(
                    rule_id=self.id, severity=self.severity, selector=selector,
                    line=line, snippet=snippet_of(tag)[:160], source=context.source,
                    confidence=self.confidence,
                    details={"width_px": int(px),
                             "mobile_viewport": 390},
                    fix_snippet=_with_attribute(
                        tag, "style",
                        self._WIDTH_RE.sub(f"max-width: {int(px)}px",
                                           css, count=1)) if tag.has_attr("style") else None,
                ))
        return issues


class TinyFont(AccessibilityRule):
    id = "viewport-tiny-font"
    severity = SERIOUS
    confidence = NEEDS_BROWSER
    wcag = ("1.4.4",)

    _FONT_RE = re.compile(
        r"(?:^|;|\{)\s*font-size\s*:\s*(\d+(?:\.\d+)?)(px|pt|rem|em)",
        re.IGNORECASE)
    _PX_PER_UNIT = {"px": 1.0, "pt": 4.0 / 3.0, "rem": 16.0, "em": 16.0}

    def check(self, document, context) -> list:
        issues = []
        for tag, css in _style_sources(document):
            css = _strip_small_screen_media(css)
            for found in self._FONT_RE.finditer(css):
                value = float(found.group(1)) * self._PX_PER_UNIT[
                    found.group(2).lower()]
                if value >= 10:
                    continue
                selector, line = context.locate(tag)
                issues.append(Issue(
                    rule_id=self.id, severity=self.severity, selector=selector,
                    line=line, snippet=snippet_of(tag)[:160], source=context.source,
                    confidence=self.confidence,
                    details={"font_px": round(value, 1),
                             "minimum_recommended": 10},
                ))
        return issues


class SmallTouchTarget(AccessibilityRule):
    id = "viewport-touch-target"
    severity = MINOR
    confidence = NEEDS_BROWSER
    wcag = ("2.5.8",)

    _SIZE_RE = re.compile(
        r"(?:^|;)\s*(width|height)\s*:\s*(\d+(?:\.\d+)?)px", re.IGNORECASE)
    _MINIMUM_PX = 24

    def check(self, document, context) -> list:
        issues = []
        for name in _INTERACTIVE:
            for tag in document.find_all(name, style=True):
                sizes = {m.group(1).lower(): float(m.group(2))
                         for m in self._SIZE_RE.finditer(tag.get("style") or "")}
                too_small = {axis: px for axis, px in sizes.items()
                             if px < self._MINIMUM_PX}
                if not too_small:
                    continue
                selector, line = context.locate(tag)
                issues.append(Issue(
                    rule_id=self.id, severity=self.severity, selector=selector,
                    line=line, snippet=snippet_of(tag), source=context.source,
                    confidence=self.confidence,
                    details={"declared": ", ".join(f"{axis}={int(px)}px"
                                                   for axis, px in sorted(too_small.items())),
                             "wcag_minimum": self._MINIMUM_PX,
                             "recommended": 44},
                ))
        return issues


# ------------------------------------------------------------------ helpers

#: Attributes whose presence is the whole meaning; writing `autoplay=""` in
#: a suggested fix is valid HTML but reads as a mistake to anyone copying it.
_BOOLEAN_ATTRIBUTES = frozenset((
    "controls", "muted", "autoplay", "loop", "playsinline", "disabled",
    "checked", "selected", "readonly", "required", "open", "hidden",
    "multiple", "novalidate", "default", "reversed", "async", "defer",
))


def _with_attribute(tag, name: str, value: str) -> str:
    """The element's opening tag with one attribute set — the fix, written
    out, so it can be copied straight into the source."""
    attributes = dict(tag.attrs)
    attributes[name] = value
    parts = []
    for key, val in attributes.items():
        if isinstance(val, list):
            val = " ".join(val)
        if key in _BOOLEAN_ATTRIBUTES and val in ("", key, True):
            parts.append(key)
        else:
            parts.append(f'{key}="{val}"')
    return f"<{tag.name} " + " ".join(parts) + ">"


_NAMED_COLORS = {
    "white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0),
    "green": (0, 128, 0), "blue": (0, 0, 255), "gray": (128, 128, 128),
    "grey": (128, 128, 128), "silver": (192, 192, 192), "yellow": (255, 255, 0),
}


def _parse_color(value: str) -> tuple | None:
    """The opaque sRGB triple this declaration paints, or None when the
    markup alone cannot say.

    None is the honest answer far more often than it looks: `var(--fg)`,
    `currentColor`, `transparent`, `hsl()`, `color-mix()` and percentage
    channels all resolve somewhere this pass cannot see. Translucent
    colours belong in the same group — a ratio computed against a colour
    that is half the layer underneath is a number nobody measured.
    """
    value = value.strip().lower()
    if value in _NAMED_COLORS:
        return _NAMED_COLORS[value]
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) in (3, 4):
            digits = "".join(c * 2 for c in digits)
        if len(digits) == 8 and _hex_pair(digits[6:8]) not in (255, None):
            return None  # translucent: the colour behind it is unknown
        if len(digits) >= 6:
            channels = tuple(_hex_pair(digits[i:i + 2]) for i in (0, 2, 4))
            return None if None in channels else channels
    match = re.match(r"rgba?\(([^)]+)\)", value)
    if match:
        parts = [p.strip() for p in match.group(1).replace("/", ",").split(",")]
        parts = [p for p in parts if p]
        if len(parts) < 3 and parts and len(parts[0].split()) == 3:
            parts = parts[0].split() + parts[1:]  # rgb(0 0 0 / 50%) space syntax
        try:
            channels = tuple(_clamp_channel(float(p)) for p in parts[:3])
            alpha = float(parts[3]) if len(parts) > 3 else 1.0
        except ValueError:
            return None
        if len(channels) < 3 or alpha < 1.0:
            return None
        return channels
    return None


def _hex_pair(digits: str) -> int | None:
    try:
        return int(digits, 16)
    except ValueError:
        return None


def _clamp_channel(value: float) -> int:
    """CSS channels outside 0-255 are clamped by browsers, not honoured;
    letting them through produces luminances no screen ever shows."""
    return max(0, min(255, int(value)))


def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple) -> float:
    r, g, b = (_channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: tuple, background: tuple) -> float:
    """WCAG 2.x contrast ratio, 1.0 (identical) to 21.0 (black on white)."""
    light, dark = sorted(
        (relative_luminance(foreground), relative_luminance(background)), reverse=True
    )
    return (light + 0.05) / (dark + 0.05)


class LandmarkRegions(AccessibilityRule):
    """Page should have landmark regions for screen reader navigation.

    Landmarks (<main>, <nav>, <header>, <footer>, or ARIA equivalents) let
    screen reader users jump directly to the section they need instead of
    tabbing through the entire page. A page with no landmarks at all forces
    linear navigation.
    """
    id = "landmark-regions"
    web_only = True
    page_level = True
    severity = MODERATE
    wcag = ("1.3.1", "2.4.1")

    _LANDMARK_TAGS = {"main", "nav", "header", "footer", "aside", "form"}
    _LANDMARK_ROLES = {
        "banner", "complementary", "contentinfo", "form", "main",
        "navigation", "region", "search",
    }

    def check(self, document, context) -> list:
        if document.find("html") is None:
            return []
        found = set()
        for tag in document.find_all(True):
            if tag.name in self._LANDMARK_TAGS:
                found.add(tag.name)
            role = (tag.get("role") or "").lower().strip()
            if role in self._LANDMARK_ROLES:
                found.add(role)
        if "main" in found or "main" in {t.name for t in document.find_all("main")}:
            return []
        return [Issue(
            rule_id=self.id, severity=self.severity, source=context.source,
            snippet="<body>…</body>",
            details={"found": sorted(found)},
            fix_snippet='<main>…</main>',
        )]


class SkipLink(AccessibilityRule):
    """First focusable element should be a skip-to-content link.

    Keyboard users (including screen reader users) need a way to bypass
    repeated navigation. The convention is a link at the top of the page
    that jumps to the main content area. Without it, every page visit
    requires tabbing through the entire nav.
    """
    id = "skip-link"
    web_only = True
    page_level = True
    severity = MODERATE
    wcag = ("2.4.1",)

    def check(self, document, context) -> list:
        if document.find("html") is None:
            return []
        body = document.find("body")
        if body is None:
            return []
        # Look for a link near the top that points to an anchor
        for tag in body.find_all("a", href=True, limit=10):
            href = (tag.get("href") or "").strip()
            if href.startswith("#") and len(href) > 1:
                target_id = href[1:]
                if body.find(id=target_id) is not None:
                    return []
        return [Issue(
            rule_id=self.id, severity=self.severity, source=context.source,
            snippet="<body>…</body>",
            details={},
            fix_snippet='<a href="#main-content" class="skip-link">Skip to main content</a>',
        )]


class FormErrorMessage(AccessibilityRule):
    """Form inputs with errors should be described by the error message.

    When a form field has an error (indicated by aria-invalid="true"), the
    error message must be programmatically linked to the field via
    aria-describedby or aria-errormessage. Without this, screen reader users
    know the field is invalid but not why.
    """
    id = "form-error-message"
    severity = SERIOUS
    wcag = ("3.3.1",)

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all(("input", "select", "textarea")):
            if (tag.get("aria-invalid") or "").lower() != "true":
                continue
            described_by = (tag.get("aria-describedby") or "").strip()
            errormessage = (tag.get("aria-errormessage") or "").strip()
            if described_by or errormessage:
                continue
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector,
                line=line, snippet=snippet_of(tag), source=context.source,
                details={"element": tag.name, "type": tag.get("type", "")},
            ))
        return issues


class TableScope(AccessibilityRule):
    """Data table headers should use scope attribute.

    The scope attribute on <th> tells screen readers whether the header
    applies to a row or a column. Without it, complex tables become
    ambiguous — the user hears a cell value but not which header it belongs to.
    """
    id = "table-scope"
    severity = MODERATE
    wcag = ("1.3.1",)

    def check(self, document, context) -> list:
        issues = []
        for table in document.find_all("table"):
            if table.get("role") == "presentation":
                continue
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            ths = table.find_all("th")
            if not ths:
                continue
            # Only flag if there are th elements but none use scope
            has_scope = any(th.get("scope") for th in ths)
            if has_scope:
                continue
            # Multi-row or multi-column tables benefit most from scope
            if len(ths) <= 1:
                continue
            selector, line = context.locate(table)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, selector=selector,
                line=line, snippet=snippet_of(table), source=context.source,
                details={"th_count": len(ths), "rows": len(rows)},
                fix_snippet='<th scope="col">…</th>',
            ))
        return issues


#: The languages a switcher is looked for in. Not every ISO code: this is a
#: hint about a page, and a longer list buys nothing but more ways to match
#: a word that happens to start with two letters.
_SWITCHER_LANGUAGES = ("en", "uk", "it", "de", "fr", "es", "pl")

#: What a language link calls itself, in its own language and in English.
#: A bare code counts only when the whole text is the code - "EN" is a
#: switcher, "ENTERPRISE" is not.
_LANGUAGE_NAMES = {
    "english", "українська", "українською", "ukrainian", "italiano",
    "italian", "deutsch", "german", "français", "francais", "french",
    "español", "espanol", "spanish", "polski", "polish",
}


def _switches_language(href: str) -> bool:
    """Is one *segment* of this path a language code?

    Segments, not substrings. `/en/pricing`, `/pricing/en` and `/en` are
    switchers; `/enterprise` and `/energy` are not, and telling their owner
    to add hreflang is a finding about a word.
    """
    from urllib.parse import urlparse

    path = urlparse(href).path if "//" in href else href
    segments = [s for s in path.split("/") if s]
    return any(s in _SWITCHER_LANGUAGES for s in segments)


def _names_a_language(text: str) -> bool:
    """Does the link call itself a language?

    The other half of a switcher, and the reason a flag-only or
    `?lang=` switcher is still found: the href says nothing, the text does.
    """
    label = (text or "").strip().lower()
    if not label:
        return False
    return label in _LANGUAGE_NAMES or label in _SWITCHER_LANGUAGES


class HreflangLinks(AccessibilityRule):
    """Multilingual pages should declare language alternatives.

    hreflang links tell search engines and browsers which language/version
    of a page exists. Without them, users may land on the wrong language
    version, and search engines cannot properly index multilingual content.
    """
    id = "hreflang-links"
    web_only = True
    page_level = True
    severity = MINOR
    wcag = ("3.1.2",)

    def check(self, document, context) -> list:
        if document.find("html") is None:
            return []
        html_tag = document.find("html")
        lang = (html_tag.get("lang") or "").strip()
        if not lang:
            return []  # Already reported by html-lang rule
        # Check if there are links to other language versions
        links = document.find_all("a", hreflang=True)
        alternate_links = [l for l in document.find_all("link")
                          if "alternate" in (l.get("rel") or []) and l.get("hreflang")]
        if links or alternate_links:
            return []
        # Only suggest it when the page really does offer another language.
        # `"/en" in href` was the test, and it is true of `/enterprise`,
        # `/energy` and `/end-of-life`: a one-language site with an
        # "Enterprise" link in its menu was told to add hreflang. Measured
        # 2026-09-02 on a page whose only links were those two.
        #
        # A language switcher is recognisable by two things, and this asks
        # for either: a path *segment* that is exactly a language code, or a
        # link whose own text names a language. The second is what the
        # discarded `text` variable was for - the comment below it always
        # said "language switcher patterns", and nothing ever read it.
        for tag in document.find_all("a", href=True):
            href = (tag.get("href") or "").lower()
            if _switches_language(href) or _names_a_language(_text_of(tag)):
                return [Issue(
                    rule_id=self.id, severity=self.severity, source=context.source,
                    snippet="<head>…</head>",
                    details={"lang": lang},
                    fix_snippet='<link rel="alternate" hreflang="en" href="https://example.com/en/" />',
                )]
        return []


class BreadcrumbMarkup(AccessibilityRule):
    """Breadcrumb navigation should use proper markup.

    Breadcrumbs help users understand their location in the site hierarchy.
    When present, they should use <nav aria-label="breadcrumb"> and an
    ordered list (<ol>) for proper screen reader announcement.
    """
    id = "breadcrumb-markup"
    severity = MINOR
    wcag = ("1.3.1", "2.4.8")

    _BREADCRUMB_SELECTORS = [
        {"class": "breadcrumb"}, {"class": "breadcrumbs"},
        {"aria-label": "breadcrumb"}, {"aria-label": "Breadcrumbs"},
        {"aria-label": "Breadcrumb"},
    ]

    def check(self, document, context) -> list:
        issues = []
        for selector in self._BREADCRUMB_SELECTORS:
            for tag in document.find_all(attrs=selector):
                # Check if it's properly wrapped in nav
                if tag.name == "nav":
                    continue
                parent_nav = tag.find_parent("nav")
                if parent_nav:
                    continue
                # Has breadcrumb-like content but not in nav
                if tag.find("a") or tag.find("li"):
                    selector_path, line = context.locate(tag)
                    issues.append(Issue(
                        rule_id=self.id, severity=self.severity,
                        selector=selector_path, line=line,
                        snippet=snippet_of(tag), source=context.source,
                        details={"element": tag.name},
                        fix_snippet='<nav aria-label="breadcrumb"><ol>…</ol></nav>',
                    ))
                    break  # One finding per page
        return issues


class ImageModernFormat(AccessibilityRule):
    """Images should use modern formats when possible.

    WebP and AVIF offer better compression than PNG/JPG, reducing page
    weight and improving load times. The srcset attribute allows serving
    different sizes to different viewports.
    """
    id = "image-modern-format"
    severity = MINOR
    category = PERFORMANCE
    # WebP and AVIF are a browser's formats. Mail clients are years behind on
    # both, and asking an email to ship them is asking it to break.
    web_only = True
    wcag = ()

    _LEGACY_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp")
    _MODERN_EXTENSIONS = (".webp", ".avif", ".svg")

    #: Markers of an image pipeline that picks the format from the request's
    #: `Accept` header. The extension in such a URL names the source file,
    #: not what is sent: Wix, Squarespace, Photon, imgix, Cloudflare and
    #: Next.js all serve WebP from a `.jpg` address to a browser that takes
    #: it. Measured on sixteen targets: 430 of 514 findings were these, and
    #: every one of them was a claim about bytes nobody had looked at.
    #:
    #: Establishing the truth needs a request with an `Accept` header, which
    #: is not free and not this pass's job. So the rule says nothing there
    #: rather than saying something it cannot support.
    _NEGOTIATED = (
        "wixstatic.com", "sqspcdn.com", "squarespace-cdn.com",
        "/cdn-cgi/image/", "imgix.net", "res.cloudinary.com",
        "/_next/image", "i0.wp.com", "i1.wp.com", "i2.wp.com",
        "~mv2", "/v1/fill/", "/auto/", "cdn.shopify.com/s/files",
        "images.ctfassets.net", "cdn.sanity.io", "ucarecdn.com",
        # Cloudinary's own transformation grammar, which runs on custom
        # domains too: `assets.vercel.com/image/upload/f_auto,c_fill/...`
        # says "pick the format" in the URL itself.
        "/image/upload/", "f_auto",
    )

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all("img"):
            raw_src = tag.get("src") or ""
            # Lower-cased for matching only. The address itself is reported
            # as written: a path is case-sensitive on most servers, and a
            # report that hands back `logo-barra-fvg.png` for
            # `logo-Barra-FVG.png` sends the reader to a 404.
            src = raw_src.lower()
            if not src:
                continue
            # Skip data URIs and SVGs
            if src.startswith("data:") or src.endswith(".svg"):
                continue
            if any(marker in src for marker in self._NEGOTIATED) or "?" in src:
                # The address names a source file; a pipeline decides what
                # actually arrives. See `_NEGOTIATED`.
                continue
            # Check if using legacy format without srcset
            has_legacy = any(src.endswith(ext) for ext in self._LEGACY_EXTENSIONS)
            has_srcset = bool(tag.get("srcset"))
            if has_legacy and not has_srcset:
                selector, line = context.locate(tag)
                issues.append(Issue(
                    rule_id=self.id, severity=self.severity,
                    category=self.category, selector=selector, line=line,
                    snippet=snippet_of(tag), source=context.source,
                    details={"src": raw_src[:120]},
                ))
        return issues


class LanguageChange(AccessibilityRule):
    """Inline foreign text should declare its language.

    When a passage in a different language appears within a page, screen
    readers need a `lang` attribute on the surrounding element to switch
    pronunciation. Without it, Ukrainian text inside an English page is
    read with English phonetics, which is unintelligible.
    """
    id = "language-change"
    severity = MINOR
    wcag = ("3.1.2",)

    # Common inline elements that might wrap foreign text
    _INLINE_TAGS = {"span", "em", "strong", "a", "b", "i", "u", "mark", "small", "cite", "q"}

    def check(self, document, context) -> list:
        if document.find("html") is None:
            return []
        page_lang = ""
        html_tag = document.find("html")
        if html_tag:
            page_lang = (html_tag.get("lang") or "").strip().lower()[:2]
        if not page_lang:
            return []  # Already reported by html-lang rule

        issues = []
        # Look for elements with lang attribute different from page lang
        for tag in document.find_all(attrs={"lang": True}):
            if tag.name == "html":
                continue
            element_lang = (tag.get("lang") or "").strip().lower()[:2]
            if element_lang and element_lang != page_lang:
                # This is correct usage - no issue
                continue

        # Look for text that might be in a different language but has no lang
        # This is a heuristic: check for common non-Latin/Cyrillic patterns
        # when page is Latin, or vice versa
        import unicodedata

        def _script_of(text):
            """Dominant script of a text string."""
            scripts = {}
            for ch in text:
                if ch.isalpha():
                    try:
                        name = unicodedata.name(ch, "")
                        if "CYRILLIC" in name:
                            scripts["cyrillic"] = scripts.get("cyrillic", 0) + 1
                        elif "LATIN" in name:
                            scripts["latin"] = scripts.get("latin", 0) + 1
                        elif "GREEK" in name:
                            scripts["greek"] = scripts.get("greek", 0) + 1
                        elif "ARABIC" in name:
                            scripts["arabic"] = scripts.get("arabic", 0) + 1
                        elif "CJK" in name or "HIRAGANA" in name or "KATAKANA" in name:
                            scripts["cjk"] = scripts.get("cjk", 0) + 1
                    except ValueError:
                        pass
            if not scripts:
                return ""
            return max(scripts, key=scripts.get)

        _SCRIPT_TO_LANG = {
            "cyrillic": ("uk", "ru", "bg", "sr"),
            "greek": ("el",),
            "arabic": ("ar", "fa", "ur"),
            "cjk": ("zh", "ja", "ko"),
        }

        page_script = "latin" if page_lang in ("en", "it", "de", "fr", "es", "pl", "pt") else "cyrillic" if page_lang in ("uk", "ru") else ""

        if not page_script:
            return []

        for tag in document.find_all(self._INLINE_TAGS):
            # Skip if already has lang
            if tag.get("lang"):
                continue
            # Skip if parent has lang
            parent_with_lang = tag.find_parent(attrs={"lang": True})
            if parent_with_lang:
                continue
            text = _text_of(tag)
            if len(text) < 10:  # Too short to judge
                continue
            script = _script_of(text)
            if script and script != page_script and script in _SCRIPT_TO_LANG:
                selector, line = context.locate(tag)
                issues.append(Issue(
                    rule_id=self.id, severity=self.severity,
                    selector=selector, line=line,
                    snippet=snippet_of(tag), source=context.source,
                    details={"page_lang": page_lang, "detected_script": script,
                             "suggested_lang": _SCRIPT_TO_LANG[script][0]},
                    fix_snippet=f'<span lang="{_SCRIPT_TO_LANG[script][0]}">{text[:60]}</span>',
                ))
        return issues


class AbbreviationExpansion(AccessibilityRule):
    """Abbreviations should use <abbr> with title.

    Screen readers cannot pronounce abbreviations correctly without
    expansion. The <abbr> element with a title attribute provides the
    full form, which screen readers can announce on first encounter.
    """
    id = "abbreviation-expansion"
    severity = MINOR
    wcag = ("3.1.4",)

    # Common abbreviations that should be expanded
    _COMMON_ABBREVS = {
        "WCAG", "HTML", "CSS", "JS", "API", "URL", "SEO", "UX", "UI",
        "FAQ", "CEO", "CTO", "CFO", "HR", "PR", "R&D", "B2B", "B2C",
        "SaaS", "PaaS", "IaaS", "CRM", "ERP", "CMS", "CDN", "DNS",
        "SSL", "TLS", "HTTP", "HTTPS", "FTP", "SSH", "SQL", "REST",
        "GraphQL", "JSON", "XML", "YAML", "CSV", "PDF", "PNG", "JPG",
        "SVG", "GIF", "WebP", "AVIF", "WOFF", "TTF", "EOT",
    }

    #: Whole words, and case as written. Substring matching is what this
    #: rule shipped with, and it is why one run produced 446 findings: `UI`
    #: matched "building" and "guide", `PR` matched "PRODUCT", `HR` matched
    #: "THROUGH". Compiled once, because it is consulted on every text node
    #: of every document.
    _PATTERN = None

    @classmethod
    def _matcher(cls):
        if cls._PATTERN is None:
            import re as _re

            alternatives = "|".join(sorted((_re.escape(a) for a in cls._COMMON_ABBREVS),
                                           key=len, reverse=True))
            cls._PATTERN = _re.compile(rf"(?<![A-Za-z0-9])({alternatives})(?![A-Za-z0-9])")
        return cls._PATTERN

    def check(self, document, context) -> list:
        """One finding per abbreviation per document, not per text node.

        The rule already carried the comment "only report once per page per
        abbreviation" and had never done it: the loop appended a finding for
        every text node it saw, so a page that says "API" in the nav, the
        body and the footer reported it three times. 3.1.4 is about the
        first occurrence - the reader needs the expansion once.
        """
        from bs4 import Comment, Doctype, ProcessingInstruction

        issues = []
        reported = set()
        # `string=True` returns every `NavigableString`, and a comment is
        # one. Measured 2026-09-01 across three repositories: more hits came
        # from HTML comments - "STEP 1 WIREFRAME", "MASTHEAD (upload
        # img/web/logo-simple.png...)" - than from the page's own prose. A
        # comment has no reader to be accessible to, and `stripped_strings`,
        # which every other rule here reads through, skips them already.
        skip_types = (Comment, Doctype, ProcessingInstruction)
        # In a React file the parser's "text" is mostly code. Only what the
        # scanner reads as JSX text can be shown to anyone; `CSS.escape` and
        # `JSON.parse` were five of the eight findings on `apps/coach/src`.
        shown = None
        if context.syntax == "jsx":
            from audit.base import document_source
            from audit.jsx_branches import visible_text

            shown = {m.group(1) for m in self._matcher().finditer(
                visible_text(document_source(document)))}
        for tag in document.find_all(string=True):
            if isinstance(tag, skip_types):
                continue
            if tag.parent.name in ("script", "style", "code", "pre", "abbr"):
                continue
            parent = tag.parent
            if parent is not None and parent.find_parent("abbr") is not None:
                continue
            for match in self._matcher().finditer(str(tag)):
                abbrev = match.group(1)
                if abbrev in reported:
                    continue
                if shown is not None and abbrev not in shown:
                    continue
                if parent and parent.find("abbr", string=lambda s: s and abbrev in s):
                    continue
                reported.add(abbrev)
                selector, line = context.locate(parent) if parent else ("", None)
                issues.append(Issue(
                    rule_id=self.id, severity=self.severity,
                    selector=selector, line=line,
                    snippet=f"...{abbrev}...",
                    source=context.source,
                    details={"abbreviation": abbrev},
                    fix_snippet=f'<abbr title="Full form">{abbrev}</abbr>',
                ))
        return issues


for _rule in (
    ImageAlt, ImageAltIsFilename, ControlName, VagueLinkText, DocumentLanguage,
    DocumentLanguageMismatch, DeclaredLanguageContradictsAddress,
    DocumentTitle, HeadingOrder, MissingH1, PositiveTabindex, DuplicateIds,
    BrokenAriaReference, ButtonWithoutType, MediaWithoutCaptions, AutoplayingMedia,
    TableStructure, ViewportZoomBlocked, InlineContrast,
    FixedPixelWidth, TinyFont, SmallTouchTarget,
    LandmarkRegions, SkipLink, FormErrorMessage, TableScope,
    HreflangLinks, BreadcrumbMarkup, ImageModernFormat,
    LanguageChange, AbbreviationExpansion,
    EmbeddedVideoAlternatives, StatusMessageLiveRegion,
):
    RuleRegistry.register(_rule)
