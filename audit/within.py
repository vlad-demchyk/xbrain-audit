"""Auditing one part of a page rather than the whole page.

Some work is delivered as a *fragment of somebody else's document*. A
SharePoint web part is the clearest case: the page around it is the tenant's
- suite bar, site navigation, comments, footer, all of it emitted by
Microsoft - and the only thing the developer wrote, and the only thing they
can fix, is one subtree. Auditing the whole page there reports hundreds of
findings against markup the reader has no access to, and buries the handful
that are theirs.

The suppression list answers the opposite question: "not inside this part".
Saying "**only** inside this part" needs its own answer, and this is it.

Two things make it usable on a real SharePoint page rather than only in
principle:

* the platform generates the identifiers. `ControlZone_1a2b3c`,
  `WebPartWPQ3`, `root-137` - the suffix changes between renders and between
  environments, so a selector typed once stops matching. A selector that
  finds nothing is therefore retried against the *stem* of each class and
  id, which is the part the developer wrote.
* what actually got used has to be said out loud. A scope that silently
  matched nothing would report a clean page, and a clean page is what a
  reader is least equipped to doubt.
"""
from __future__ import annotations

import re

#: The generated tail of a platform-written identifier: SharePoint's
#: `_1a2b3c`, Fluent UI's `-137`, CSS-module hashes, React's `:r1:`. Only
#: ever used to find the stem a person would have typed.
_GENERATED_TAIL = re.compile(
    r"(?:[_-][0-9a-f]{4,}|[_-]\d+|__[A-Za-z0-9]{5,}|:r[0-9a-z]+:)$", re.I)


class ScopeNotFound(LookupError):
    """The selector matched nothing, exactly or by stem."""


def stem(identifier: str) -> str:
    """`ControlZone_1a2b3c` -> `ControlZone`. Idempotent."""
    previous = None
    current = identifier or ""
    while current != previous:
        previous = current
        current = _GENERATED_TAIL.sub("", current)
    return current


def _wanted(selector: str) -> tuple:
    """`(kind, name)` for the one simple selector this can match by stem.

    Deliberately narrow: `#id`, `.class` and `[data-x="y"]` are what a web
    part is identified by, and a general CSS parser here would be a promise
    this cannot keep - the stem retry has to know which token to compare.
    """
    text = (selector or "").strip()
    if text.startswith("#"):
        return ("id", text[1:])
    if text.startswith(".") and " " not in text and ">" not in text:
        return ("class", text[1:])
    return ("", "")


def find(document, selector: str):
    """The subtree `selector` names, matched exactly or by stem.

    Returns `(element, how)` where `how` is `"exact"` or `"stem"`, so the
    caller can report which reading it used. Raises `ScopeNotFound` when
    neither matches - never returns the whole document as a fallback, which
    would turn "audit this web part" into "audit the tenant's page" without
    saying so.
    """
    try:
        found = document.select_one(selector)
    except Exception:  # noqa: BLE001 - an invalid selector is a message, not a crash
        found = None
    if found is not None:
        return found, "exact"

    kind, name = _wanted(selector)
    if not name:
        raise ScopeNotFound(selector)
    target = stem(name)
    for element in document.find_all(True):
        if kind == "id":
            if stem(str(element.get("id") or "")) == target:
                return element, "stem"
        else:
            classes = element.get("class") or []
            if any(stem(str(value)) == target for value in classes):
                return element, "stem"
    raise ScopeNotFound(selector)


def narrow_any(document, selectors) -> tuple:
    """The first of `selectors` that matches, as `(element, how, selector)`.

    A web part is looked for by several: its GUID in each of the attributes
    SharePoint is known to write it into, then the stems of its own CSS
    module classes. The first that matches wins, and which one it was is
    part of the answer - "found by its GUID" and "found by a class name that
    looked like yours" are not the same claim.
    """
    for selector in selectors:
        try:
            element, how = find(document, selector)
        except ScopeNotFound:
            continue
        return element, how, selector
    raise ScopeNotFound(", ".join(selectors) or "(no selectors)")


def find_all(document, selector: str) -> tuple:
    """Every subtree `selector` names, as `(elements, how)`.

    The same two readings as `find` - exact first, then by stem - but every
    match rather than the first. A web part placed twice on one page is two
    deliveries of the same code, and auditing only the first left the second
    unread without saying so.

    An element inside another match is dropped: its markup is already part
    of the outer one, and reading it twice would report each defect twice.
    Raises `ScopeNotFound` when neither reading matches anything.
    """
    try:
        found = list(document.select(selector))
    except Exception:  # noqa: BLE001 - an invalid selector is a message, not a crash
        found = []
    how = "exact"
    if not found:
        kind, name = _wanted(selector)
        if not name:
            raise ScopeNotFound(selector)
        target = stem(name)
        how = "stem"
        for element in document.find_all(True):
            if kind == "id":
                if stem(str(element.get("id") or "")) == target:
                    found.append(element)
            elif any(stem(str(value)) == target
                     for value in element.get("class") or []):
                found.append(element)
    if not found:
        raise ScopeNotFound(selector)
    return _outermost(found), how


def _outermost(elements) -> list:
    """`elements` without any that sit inside another one, in page order."""
    chosen = {id(element) for element in elements}
    kept = []
    for element in elements:
        if any(id(parent) in chosen for parent in element.parents):
            continue
        if any(element is other for other in kept):
            continue
        kept.append(element)
    return kept


def narrow_all(document, selectors) -> list:
    """Every match of every selector, as `[(element, how, selector)]`.

    The counterpart of `narrow_any` for a part that may appear more than
    once. Selectors are still tried strongest first, and the first that
    matches anything decides the reading - "found by its GUID" and "found by
    a class that looked like yours" must not be mixed in one answer - but
    every element it matches is returned. Raises `ScopeNotFound` when no
    selector matches.
    """
    for selector in selectors:
        try:
            elements, how = find_all(document, selector)
        except ScopeNotFound:
            continue
        return [(element, how, selector) for element in elements]
    raise ScopeNotFound(", ".join(selectors) or "(no selectors)")


def narrow(markup: str, selector: str) -> tuple:
    """`(markup_of_the_subtree, how)` for a document and a selector.

    The subtree is re-serialised rather than analysed in place, because
    every rule here takes markup and because a fragment is what it is: page
    level rules must not run on it, and `document_kind="fragment"` is how
    that is said.
    """
    from bs4 import BeautifulSoup

    document = BeautifulSoup(markup or "", "html.parser")
    element, how = find(document, selector)
    return str(element), how
