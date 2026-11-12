"""Colour as information: which element a finding is about, and which half
of a diff you are reading.

The styled report quoted markup as one undifferentiated grey block. That is
readable but not *legible*: on a page of forty findings the eye has nothing
to sort by, and the two code blocks under a finding - the markup that is
wrong and the markup that would fix it - looked identical, so the reader had
to parse both to learn which was which.

Two colour systems, deliberately kept apart, because they answer different
questions and mixing them makes a rainbow that means nothing:

**Elements are coloured by role, not by name.** A hash of the tag name would
give every tag its own hue and no hue any meaning. Six roles instead - a
landmark, an interactive control, a grouping wrapper, media, running text,
document metadata - so a reader who has seen three findings has already
learnt the scheme, and `<button>` and `<a>` share an ink because they share a
problem space. Unknown tags fall to the grouping ink rather than to a
seventh colour: a custom element is a wrapper until something says otherwise.

**Diff direction is red and green, and nothing else is.** The design bundle
draws exactly this (artboard 3a, the `−`/`+` pair under a finding), and it
only works while red and green mean *before* and *after* and never also mean
"a media tag". So the role inks below are chosen from the rest of the
palette: the reserved two are not among them.

Every value comes from `ui.tokens.Palette` - the XBrain Audit desktop palette,
which is the design bundle read as tokens - and never from a hex typed here.
"""
from __future__ import annotations

import html
import re

#: Role -> (the tags that have it, the `Palette` attribute that inks it).
#:
#: Order matters only for reading: a tag belongs to exactly one role, and
#: `_ROLE_OF` below is built from this so a tag added to two roles is a
#: mistake that shows up as one of them silently winning. It cannot: the
#: builder raises.
ROLES: dict = {
    "landmark": (
        ("html", "body", "head", "header", "nav", "main", "footer",
         "section", "article", "aside", "dialog", "form", "fieldset"),
        "text",
    ),
    "control": (
        ("a", "button", "input", "select", "option", "optgroup", "textarea",
         "label", "legend", "summary", "details", "output", "progress",
         "meter"),
        "accent",
    ),
    "media": (
        ("img", "picture", "source", "svg", "path", "use", "canvas", "video",
         "audio", "track", "iframe", "embed", "object", "figure",
         "figcaption", "map", "area"),
        "sev_high",
    ),
    "content": (
        ("h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote", "q", "cite",
         "strong", "em", "b", "i", "u", "small", "mark", "abbr", "time",
         "code", "pre", "kbd", "samp", "var", "sub", "sup", "caption"),
        "amber_text",
    ),
    "meta": (
        ("meta", "title", "link", "base", "script", "style", "noscript",
         "template", "slot"),
        "text_subtle",
    ),
    "grouping": (
        ("div", "span", "ul", "ol", "li", "dl", "dt", "dd", "table", "thead",
         "tbody", "tfoot", "tr", "td", "th", "colgroup", "col", "hr", "br",
         "wbr", "picture-frame"),
        "text_muted",
    ),
}

#: What an unrecognised tag gets. A `<my-widget>` is a wrapper until its
#: markup says otherwise, and inventing a seventh ink for "unknown" would
#: colour the most common case the most loudly.
FALLBACK_ROLE = "grouping"

#: How the legend names each role, in the report's three languages. The
#: report carries its own small vocabulary rather than reaching into
#: `i18n.translations` - same boundary `template.py` documents.
ROLE_LABELS = {
    "en": {"landmark": "Landmark & structure", "control": "Interactive",
           "media": "Media & embeds", "content": "Text content",
           "meta": "Document metadata", "grouping": "Grouping & tables"},
    "uk": {"landmark": "Орієнтири і структура", "control": "Інтерактивні",
           "media": "Медіа і вбудоване", "content": "Текстовий вміст",
           "meta": "Метадані документа", "grouping": "Групування і таблиці"},
    "it": {"landmark": "Landmark e struttura", "control": "Interattivi",
           "media": "Media e incorporati", "content": "Contenuto testuale",
           "meta": "Metadati del documento", "grouping": "Raggruppamento e tabelle"},
}


def _build_role_index() -> dict:
    index: dict = {}
    for role, (tags, _ink) in ROLES.items():
        for tag in tags:
            if tag in index:
                raise ValueError(f"tag {tag!r} is in two roles: "
                                 f"{index[tag]} and {role}")
            index[tag] = role
    return index


_ROLE_OF = _build_role_index()


def role_of(tag: str) -> str:
    """Which role an element name has. Case- and namespace-insensitive."""
    name = (tag or "").strip().lower().lstrip("/")
    if ":" in name:                      # `svg:path`, `xhtml:div`
        name = name.rsplit(":", 1)[-1]
    return _ROLE_OF.get(name, FALLBACK_ROLE)


_OPEN_TAG = re.compile(r"<\s*/?\s*([a-zA-Z][\w:.-]*)")
#: The tail of a CSS selector, for the case where there is no markup to read:
#: `#container > .element-1.tier-1` has no element at all and yields nothing,
#: which is correct - guessing `div` there would be inventing a fact.
_SELECTOR_TAIL = re.compile(r"([a-zA-Z][\w-]*)\s*(?:[.#\[:]|$)")


def element_of(snippet: str = "", selector: str = "") -> str:
    """The element a finding is about, lowercased, or `""` when unknown.

    The markup wins over the selector: the snippet is what the engine
    actually quoted, while a selector can name a class and no element at
    all. Neither is invented - a finding with no markup and a classes-only
    selector has no element, and the report says nothing rather than
    guessing.
    """
    match = _OPEN_TAG.search(snippet or "")
    if match:
        return match.group(1).lower()
    tail = (selector or "").strip().split(">")[-1].strip().split()[-1:]
    if tail:
        match = _SELECTOR_TAIL.match(tail[0])
        if match:
            return match.group(1).lower()
    return ""


# ------------------------------------------------------------- highlighting

#: One tag, with its attributes: `<a href="/x" class="y">`, `</a>`, `<br/>`.
#: Quoted attribute values may contain `>` (a `style` with a data URI does),
#: so the body alternates between quoted runs and anything-but-a-quote-or-`>`.
_TAG = re.compile(
    r"""<\s*(/?)\s*([a-zA-Z][\w:.-]*)((?:[^>"']|"[^"]*"|'[^']*')*)(/?)\s*>""",
    re.S,
)

#: One attribute inside a tag body: name, optional `=`, optional value.
_ATTR = re.compile(
    r"""([^\s=/>"']+)(\s*=\s*)?("[^"]*"|'[^']*'|[^\s>]+)?""",
)


def _span(css_class: str, text: str) -> str:
    return f'<span class="{css_class}">{html.escape(text, quote=True)}</span>'


def _attributes(body: str) -> str:
    out = []
    position = 0
    for match in _ATTR.finditer(body):
        if match.start() == match.end():
            continue
        out.append(html.escape(body[position:match.start()], quote=True))
        name, equals, value = match.group(1), match.group(2), match.group(3)
        out.append(_span("a-name", name))
        if equals:
            out.append(_span("m-punct", equals))
        if value:
            out.append(_span("a-value", value))
        position = match.end()
    out.append(html.escape(body[position:], quote=True))
    return "".join(out)


def highlight(markup: str) -> str:
    """Quoted markup as HTML: tag names inked by role, attributes and text
    told apart. Everything is escaped - the result is *shown*, never parsed.

    Text that contains no tag at all comes back escaped and unchanged, which
    is what an AI-text finding quotes: a passage of prose is not markup and
    must not be painted as though a colour there meant something.
    """
    source = markup or ""
    out = []
    position = 0
    for match in _TAG.finditer(source):
        out.append(_span("m-text", source[position:match.start()])
                   if source[position:match.start()] else "")
        closing, tag, body, selfclose = match.groups()
        out.append(_span("m-punct", "<" + closing))
        out.append(_span(f"t-{role_of(tag)}", tag))
        out.append(_attributes(body))
        out.append(_span("m-punct", selfclose + ">"))
        position = match.end()
    tail = source[position:]
    if tail:
        out.append(_span("m-text", tail) if out
                   else html.escape(tail, quote=True))
    return "".join(out)


def roles_used(findings) -> list:
    """The roles actually present, in `ROLES` order.

    A legend that lists six roles when the report contains two is noise: it
    describes the scheme rather than the document. Only what is on the page
    is explained.
    """
    seen = set()
    for finding in findings:
        element = getattr(finding, "element", "")
        if element:
            seen.add(role_of(element))
    return [role for role in ROLES if role in seen]


def role_css(palette) -> str:
    """One rule per role, plus the parts of a tag that are not its name."""
    rules = [f".t-{role} {{ color: {getattr(palette, ink)}; font-weight: 600; }}"
             for role, (_tags, ink) in ROLES.items()]
    rules += [
        f".a-name {{ color: {palette.text_muted}; }}",
        f".a-value {{ color: {palette.text}; }}",
        f".m-punct {{ color: {palette.text_subtle}; }}",
        f".m-text {{ color: {palette.text}; }}",
    ]
    return "\n".join(rules)
