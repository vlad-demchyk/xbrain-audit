"""Grouping findings that are the same finding in more than one file.

A project holds copies of its own code: the source, the compiled output, the
bundle, the deployed folder. One en dash in a Cherry Bank address arrived
four times from four such copies, and reading a list where three of every
four rows say the same thing is how a list stops being read.

The obvious fix - exclude directories called `lib/` and `release/` - was
tried and rejected: `src/lib/` is *source* in most React and Svelte
projects, and the exclusion blinded the scanner to 67 real findings in
xFormat the moment it was applied. A name cannot tell a build output from a
source directory. Identical text at identical fault can, and needs no
guessing.

**Grouping is presentational, and nothing is dropped.** Every finding stays
in the list with its own file and offset, because every copy is a real file
that a fix has to edit - collapsing them into one would mean writing the
correction into one file and leaving three stale. What grouping changes is
what the reader is shown first: one row, and a note that it also appears in
N other places.
"""
from __future__ import annotations

import re
from functools import lru_cache

#: What makes two findings in two files the same finding. The flagged text
#: and what it becomes: the offsets differ between copies (the compiled file
#: has different line numbers), and the file is the thing that varies by
#: definition, so neither can be part of the identity.
def identity(finding: dict) -> tuple:
    return (
        finding.get("text", ""),
        finding.get("replacement"),
        finding.get("source", ""),
        finding.get("explanation", ""),
    )


def group(findings: list) -> list:
    """Return `[(first, others)]`, in the order the findings arrived.

    `first` is the finding to show; `others` are the identical ones in other
    files. A finding with no twin comes back with an empty `others`, so a
    caller can render every case through the same branch.
    """
    order: list = []
    seen: dict = {}
    for finding in findings:
        key = identity(finding)
        if key in seen:
            seen[key][1].append(finding)
            continue
        entry = (finding, [])
        seen[key] = entry
        order.append(entry)
    return order


def copies_of(finding: dict, others: list) -> list:
    """The other files the same finding sits in, as plain paths."""
    return [other.get("file", "") for other in others]


# ------------------------------------------------------- audit issues
#
# The same reasoning, one document type further out. A crawl of thirty pages
# that share a header reports the header's unlabelled search field thirty
# times, and a missing meta description once per page - the count says
# "thirty problems" when there is one problem and thirty places. Reports and
# lists therefore group on what the problem *is* and carry the places with
# it, rather than repeating the whole finding per place.


def issue_identity(issue) -> tuple:
    """What makes two audit findings the same problem.

    The rule that fired, and the element it fired on. `source` is excluded
    by definition - being in more than one document is what makes this a
    group - and so is `line`, since the same shared markup sits at a
    different line in every page that includes it.

    The element is identified by its markup rather than by its selector: a
    selector is a position (`body > header:nth-child(1) > img`) and shifts
    with anything the page renders above it, so two copies of one header
    image would look like two different problems. The markup is the same
    string in both.

    Generated identifiers inside the markup are masked first, and that is not
    cosmetic. A theme that stamps a unique id into a component - WordPress
    writes `aria-controls="page-toc-panel-6a8c2c05ce8bd"` - produces markup
    that differs on every page while describing one bug in one template. On a
    live ten-page crawl that turned one broken TOC toggle into ten separate
    critical findings, which is the same inflation grouping exists to remove,
    wearing a different disguise.

    Masked narrowly on purpose: long hex runs, UUIDs and long digit runs are
    machine-made, and anything shorter is likely to be meaningful (`h2`,
    `col-6`, `id="nav"`). Over-masking would merge findings that really are
    different, and a wrongly merged problem hides a real one.
    """
    if ((getattr(issue, "details", None) or {}).get("zone") or "") == "custom":
        return component_identity(issue)
    snippet = canonical_markup(getattr(issue, "snippet", "") or "")
    selector = getattr(issue, "selector", "") or ""
    # A finding about the page or the run rather than an element - a missing
    # response header, a string left untranslated - has neither a snippet nor
    # a selector, and with nothing to tell them apart every one of a rule's
    # findings would merge into a single "problem". 473 untranslated strings
    # were one row. What tells them apart is what the finding says it found.
    evidence = ""
    if not snippet and not selector:
        details = getattr(issue, "details", None) or {}
        for key in ("text", "value", "header", "path", "target", "alt", "id"):
            if details.get(key):
                evidence = f"{key}={details[key]}"
                break
    details = getattr(issue, "details", None) or {}
    return (
        getattr(issue, "rule_id", ""),
        getattr(issue, "category", ""),
        getattr(issue, "severity", ""),
        getattr(issue, "confidence", "exact"),
        details.get("zone", ""),
        details.get("zone_name", "").removesuffix(OUTSIDE_CANVAS),
        snippet or selector or evidence,
    )


#: A UUID, first: it contains hex runs that the next pattern would otherwise
#: chew up piecemeal, leaving the dashes behind as false structure.
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
#: Eight hex characters or more. Short enough to catch a theme's suffix,
#: long enough that ordinary words and class names do not qualify.
_HEXRUN_RE = re.compile(r"\b[0-9a-f]{8,}\b", re.I)
#: Four digits or more: a timestamp, a post id, a counter. Three would catch
#: `col-3` and every year in a copyright line.
_DIGITRUN_RE = re.compile(r"\d{4,}")

#: React's `useId`, which is what every headless component library builds its
#: `id`/`aria-controls` pairs out of. The value is a render counter, so it
#: differs on every page while describing one element in one component.
_REACT_USE_ID_RE = re.compile(r":[rR][0-9a-z]*:")

#: Prefixes a framework or CSS-in-JS runtime stamps in front of a generated
#: suffix. The prefix is the evidence: nobody types `_ngcontent-ng-c` or
#: `sc-` by hand, so whatever follows it is machine-made whatever its shape.
#: Measured need, not a guess - nine of twelve real identifier styles were
#: splitting one problem into one finding per page before this existed.
_FRAMEWORK_PREFIXES = (
    "radix-", "mui-", "css-", "sc-", "svelte-", "astro-", "jsx-",
    "chakra-", "emotion-", "headlessui-", "downshift-", "ember",
    "_ngcontent-", "_nghost-", "data-v-",
)
_PREFIX_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(p) for p in _FRAMEWORK_PREFIXES) +
    r")[A-Za-z0-9_:-]*", re.I)

#: Attributes whose value is an identifier rather than content. `src`, `href`,
#: `alt` and `title` are deliberately absent: two images missing `alt` are two
#: problems, and masking what tells them apart would merge them into one.
_ID_ATTRS = frozenset((
    "class", "id", "for", "name", "headers", "list", "form",
    "aria-controls", "aria-labelledby", "aria-describedby", "aria-owns",
    "aria-activedescendant",
))
_ATTR_RE = re.compile(r"""([\w:.-]+)\s*=\s*("([^"]*)"|'([^']*)')""")
#: Separators a class or id is built out of. Splitting on them is what keeps
#: `text-2xl`, `col-md-6` and `mt-4` intact: their parts are all too short or
#: too plain to look machine-made on their own.
_TOKEN_SPLIT_RE = re.compile(r"([^A-Za-z0-9]+)")


def _looks_generated(token: str) -> bool:
    """Is this token a hash rather than something a person wrote?

    Two shapes, both measured against real markup:

    * **Digits woven through letters** - `1q2w3e`, `j7pv25f6`, `9a8b7c`. Six
      characters and at least two digits, which `mt-4`, `col-6` and `text-2xl`
      cannot reach once the separators have split them up.
    * **Case flipping** - `bdVaJa`, `hUyXlM`, what styled-components emits.
      Three or more case changes; `myButton` and `navBar` have one.
    """
    if len(token) < 6 or not token.isalnum():
        return False
    digits = sum(ch.isdigit() for ch in token)
    letters = sum(ch.isalpha() for ch in token)
    if digits >= 2 and letters >= 2:
        return True
    flips = sum(1 for a, b in zip(token, token[1:])
                if a.isalpha() and b.isalpha() and a.islower() != b.islower())
    return flips >= 3


def _mask_value(value: str) -> str:
    parts = _TOKEN_SPLIT_RE.split(value)
    return "".join("#" if _looks_generated(part) else part for part in parts)


def _mask_identifier_attributes(text: str) -> str:
    """Mask hash-shaped tokens inside identifier attributes only.

    Scoped to the attributes in `_ID_ATTRS` because the same string means
    different things in different places: `css-1q2w3e` in a `class` is a
    build artefact, and a hash in an `href` is the address of a different
    file. Over-masking merges findings that really are different, and a
    wrongly merged problem hides a real one.
    """
    def replace(match):
        name = match.group(1).lower()
        quote = match.group(2)[0]
        value = match.group(3) if match.group(3) is not None else match.group(4)
        if name not in _ID_ATTRS and not name.startswith("data-"):
            return match.group(0)
        return f"{match.group(1)}={quote}{_mask_value(value)}{quote}"

    return _ATTR_RE.sub(replace, text)


def mask_generated_ids(text: str) -> str:
    """Replace machine-generated identifiers with `#`.

    Exported because the report, the GUI and the tests all have to agree on
    what "the same markup" means, and a second copy of these patterns is how
    they would stop agreeing.

    The order matters: UUIDs before hex runs, and the whole-token patterns
    before the attribute-scoped ones, so a value that is already `#` is not
    picked over again.
    """
    if not text:
        return text
    text = _UUID_RE.sub("#", text)
    text = _HEXRUN_RE.sub("#", text)
    text = _DIGITRUN_RE.sub("#", text)
    text = _REACT_USE_ID_RE.sub("#", text)
    text = _PREFIX_RE.sub(lambda m: m.group(1) + "#", text)
    return _mask_identifier_attributes(text)


# ------------------------------------------------- a custom component
#
# A custom SPFx web part is code somebody deployed into the tenant. The same
# defect on every instance of its button, on every page it is placed on, is
# one problem: one fix in the component's code fixes all of them. Measured on
# a live intranet: 383 unnamed `ms-Button`s in one custom header were 383
# rows. So inside a `custom` zone a problem is the rule's family, the web
# part, and the element's shape - its tag and the classes that name the
# component's element - and not what each instance says or points at.
#
# Not for `author` zones and not for any other site: there each image and
# each link was written by a person, and needs its own fix.

#: Class shapes that are not part of the element's identity in a component:
#: state classes (`is-disabled`), Fluent UI's style counters (`root-262`,
#: `field-261`), Griffel's atomic hashes (`f16hsg94`, always with a digit,
#: and `___1q2w3e_0000000`).
_STATE_CLASS = re.compile(r"^is-")
_FLUENT_COUNTER = re.compile(r"^[A-Za-z]+-\d+$")
_GRIFFEL_ATOMIC = re.compile(r"^(f(?=[a-z0-9]*\d)[a-z0-9]{6,8}|___[A-Za-z0-9_]+)$")
_OPEN_TAG = re.compile(r"<\s*([a-zA-Z][\w-]*)([^>]*)")
_CLASS_ATTR = re.compile(r"""\bclass\s*=\s*("([^"]*)"|'([^']*)'|([^\s>"']+))""", re.I)
_SELECTOR_PART = re.compile(r"^([a-zA-Z][\w-]*)?((?:[.#:\[][^\s>+~]*)*)$")

#: The part of a zone name that says where the markup was found, not whose.
OUTSIDE_CANVAS = " (outside the canvas)"


def semantic_classes(classes) -> tuple:
    """The classes that name a component's element, sorted."""
    kept = {name for name in classes
            if name and not _STATE_CLASS.match(name)
            and not _FLUENT_COUNTER.match(name)
            and not _GRIFFEL_ATOMIC.match(name)}
    return tuple(sorted(kept))


def element_shape(snippet: str, selector="") -> str:
    """`tag.class.class` of the element a finding quotes: the shape of a
    component's element, without anything that comes from data."""
    match = _OPEN_TAG.search(snippet or "")
    if match:
        tag = match.group(1).lower()
        found = _CLASS_ATTR.search(match.group(2) or "")
        value = ""
        if found:
            value = found.group(2) or found.group(3) or found.group(4) or ""
        return ".".join((tag,) + semantic_classes(value.split()))
    if isinstance(selector, (list, tuple)):
        selector = " ".join(str(part) for part in selector)
    last = str(selector or "").strip().split(" ")[-1] if selector else ""
    part = _SELECTOR_PART.match(last) if last else None
    if not part:
        return ""
    tag = (part.group(1) or "").lower()
    classes = re.findall(r"\.([\w-]+)", part.group(2) or "")
    return ".".join(((tag,) if tag else ()) + semantic_classes(classes))


def component_identity(issue) -> tuple:
    """What makes two findings in a custom web part the same problem.

    The rule's family (`audit.browser._family_of`: `control-name`,
    `axe:button-name` and `htmlcs:4_1_2` are one "name" problem), the web
    part (`(outside the canvas)` folded into its name), the element's shape
    (`element_shape`), its category and how settled it is. Severity is not in
    it: a group is reported at its worst.
    """
    from audit.browser import _family_of

    details = getattr(issue, "details", None) or {}
    try:
        family = _family_of(issue)
    except Exception:  # noqa: BLE001 - a family is a grouping hint, never a reason to fail
        family = getattr(issue, "rule_id", "") or ""
    return (
        "component",
        family,
        getattr(issue, "category", ""),
        getattr(issue, "confidence", "exact"),
        str(details.get("zone_name", "")).removesuffix(OUTSIDE_CANVAS),
        element_shape(getattr(issue, "snippet", "") or "",
                      getattr(issue, "selector", "") or ""),
    )


@lru_cache(maxsize=8192)
def canonical_markup(text: str) -> str:
    """Compare element structure, preserving content and resource addresses."""
    from bs4 import BeautifulSoup

    if not text.lstrip().startswith("<"):
        return " ".join(text.split())
    document = BeautifulSoup(text, "html.parser")
    for element in document.find_all(True):
        fluent = any(value.startswith("ms-") for value in element.get("class", []))
        for name, value in list(element.attrs.items()):
            if name.startswith(("data-v-", "_ngcontent-", "_nghost-")):
                element.attrs.pop(name)
                element.attrs[mask_generated_ids(name)] = value
                continue
            if name not in _ID_ATTRS and not name.startswith("data-"):
                continue
            values = value if isinstance(value, list) else [value]
            masked = []
            for item in values:
                if item is None:
                    continue
                value_text = _UUID_RE.sub("#", str(item))
                value_text = _HEXRUN_RE.sub("#", value_text)
                value_text = _DIGITRUN_RE.sub("#", value_text)
                value_text = _REACT_USE_ID_RE.sub("#", value_text)
                value_text = _PREFIX_RE.sub(lambda match: match.group(1) + "#", value_text)
                masked.append(_mask_value(value_text))
            if name == "class":
                if fluent:
                    masked = [re.sub(r"^(root|field|icon|dropdown|cellTitle|cellName|cell)-\d+$", r"\1-#", item)
                              for item in masked]
                element.attrs[name] = sorted(masked)
            elif masked:
                element.attrs[name] = masked if isinstance(value, list) else masked[0]
    return " ".join(str(document).split())


class GroupInvariantError(AssertionError):
    """Two findings that are not the same problem were put in one group."""


def _strict_groups() -> bool:
    import os

    return bool(os.environ.get("XAUDIT_STRICT_GROUPS") or os.environ.get("PYTEST_CURRENT_TEST"))


def group_conflict(first, other) -> str:
    """Why `other` may not share a group with `first`, or "" when it may.

    The invariant every grouped list keeps, checked member by member rather
    than trusted from the key: a group never mixes rule families, zones or
    web parts, element shapes (in a custom part), or - anywhere else -
    findings `issue_identity` tells apart. A smaller number made by grouping
    unrelated things is the one error a summary must never make.
    """
    from audit.browser import _family_of

    def zone_of(issue):
        details = getattr(issue, "details", None) or {}
        return (details.get("zone", "") or "",
                str(details.get("zone_name", "") or "").removesuffix(OUTSIDE_CANVAS))

    try:
        families = (_family_of(first), _family_of(other))
    except Exception:  # noqa: BLE001 - compared by rule instead
        families = (getattr(first, "rule_id", ""), getattr(other, "rule_id", ""))
    if families[0] != families[1]:
        return f"rule family {families[0]} != {families[1]}"
    if zone_of(first) != zone_of(other):
        return f"zone {zone_of(first)} != {zone_of(other)}"
    if getattr(first, "confidence", "exact") != getattr(other, "confidence", "exact"):
        return "certainty differs"
    if zone_of(first)[0] == "custom":
        shapes = tuple(element_shape(getattr(issue, "snippet", "") or "",
                                     getattr(issue, "selector", "") or "")
                       for issue in (first, other))
        if shapes[0] != shapes[1]:
            return f"element shape {shapes[0]} != {shapes[1]}"
        return ""
    if issue_identity(first) != issue_identity(other):
        return "identity differs"
    return ""


def admits(first, other) -> bool:
    """May `other` join `first`'s group? A conflict raises under tests (and
    with `XAUDIT_STRICT_GROUPS`), and is logged and split otherwise."""
    reason = group_conflict(first, other)
    if not reason:
        return True
    if _strict_groups():
        raise GroupInvariantError(
            f"{getattr(first, 'rule_id', '')} / {getattr(other, 'rule_id', '')}: {reason}")
    try:
        import applog

        applog.error("grouping.invariant", reason=reason,
                     rule=getattr(first, "rule_id", ""), other=getattr(other, "rule_id", ""))
    except Exception:  # noqa: BLE001 - logging must not stop a report
        pass
    return False


def group_issues(issues: list) -> list:
    """`[(first, others)]` for audit issues, in arrival order.

    Same contract as `group`: nothing is dropped, and a finding with no twin
    comes back with an empty `others`, so one branch renders every case.
    Every member is checked against its group's first (`admits`).
    """
    order: list = []
    seen: dict = {}
    for issue in issues:
        key = issue_identity(issue)
        entries = seen.setdefault(key, [])
        for entry in entries:
            if admits(entry[0], issue):
                entry[1].append(issue)
                break
        else:
            entry = (issue, [])
            entries.append(entry)
            order.append(entry)
    return order


def places_of(issue, others: list) -> list:
    """Every document the grouped problem was found in, first one included.

    Deduplicated and in arrival order: a page reached twice by the crawl, or
    two findings collapsed within one document, must not make the list say
    the same address twice.
    """
    places: list = []
    for candidate in [issue] + list(others):
        where = getattr(candidate, "source", "") or ""
        line = getattr(candidate, "line", None)
        label = f"{where}:{line}" if line else where
        if label and label not in places:
            places.append(label)
    return places


# ------------------------------------------------------- text blocks
#
# One step earlier than everything above. The functions before this group
# findings *after* they were produced; this one stops the same passage being
# read twice in the first place.
#
# A crawl of ten pages produced 573 blocks and 236 distinct texts: a header
# and a footer appear on every page, so `Tel. +39 0432 924815` was read 26
# times. The offline pass paid for that in wasted local work and the judge
# paid for it in network round trips - on the Claude Code route each one is a
# process start, so the waste was minutes and real money spent asking the
# same question of the same string.


def block_identity(block) -> tuple:
    """What makes two extracted passages the same passage.

    The text, normalised, and the language it was taken to be. The language
    belongs in the identity because the detectors genuinely answer
    differently for it - the same string read as Italian and as English is
    two questions, and collapsing them would silently pick one answer for
    both.

    Machine-generated identifiers are masked, so a menu that renders with a
    fresh uuid on every page is still one passage. Same reasoning, and the
    same function, as `issue_identity`.
    """
    text = mask_generated_ids(" ".join((getattr(block, "text", "") or "").split()))
    return (text, getattr(block, "language_hint", None) or "")


def distinct_blocks(blocks: list, *, exact_text=False) -> list:
    """`[(representative, [every block with that identity])]`, in arrival order.

    The representative is the first occurrence, and it is the one handed to a
    detector. Every occurrence is carried alongside because each is a real
    place on a real page that a fix has to visit: this changes what is
    *asked*, never what is *reported*.
    """
    order: list = []
    seen: dict = {}
    for block in blocks:
        key = (block.text, block.language_hint) if exact_text else block_identity(block)
        if key in seen:
            seen[key].append(block)
            continue
        group = [block]
        seen[key] = group
        order.append((block, group))
    return order
