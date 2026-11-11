"""Which part of a SharePoint page is whose, and which part to audit.

A modern SharePoint Online page is three kinds of markup in one document,
and only two of them are anybody's to fix:

* **microsoft** - the chrome: the suite bar, the app bar, the site and hub
  header, the command bar, the comments, the footer, and every wrapper the
  canvas puts around a web part. Nobody involved in the site can change a
  line of it. It is **not audited**, and what was left out is counted, so a
  short list is never mistaken for a clean page.
* **custom** - SPFx web parts, application customizer placeholders, and the
  markup an SPFx part moves out of the canvas into the chrome. Code somebody
  wrote and deployed into the tenant: audited with every rule and named by
  the part that owns it.
* **author** - what the page's author typed or chose: the Text web part
  (the rich-text editor), the title area (the `PageTitle` web part), and the
  content inside Microsoft's own web parts - an image's alt text, a quick
  link's title, a heading. For a Microsoft web part only the rules about that
  content apply (`OOTB_CONTENT_RULES`); a structural or ARIA defect in the
  part's own markup is Microsoft's, and is counted as skipped, not reported.

**What is verified and what is not.** The structure below was checked
against the rendered DOM of a live SharePoint Online tenant (seven modern
pages, after scrolling every lazy web part into view). Each selector carries
one of three marks:

* ``VERIFIED`` - seen on that live DOM;
* ``HYPOTHESIS`` - SharePoint's DOM as commonly documented, not seen there
  (a part type or a region those pages did not have);
* ``HEURISTIC`` - an inference from evidence that is usually right and can
  be wrong (`SPFx outside the canvas`, below).

**How a web part is recognised (VERIFIED).** Every web part sits in a canvas
control - `[data-automation-id="CanvasControl"]`, `id` = its instance id -
which is the zone's root. Inside it, the part's element carries
`data-sp-feature-tag="<Alias> web part (<title>)"`: the alias is the part's
English, stable code name, the title is localised. `data-sp-web-part-id` is
the part type's GUID. `data-viewport-id="WebPart.<Alias>.internal.<id>"`
marks a part Microsoft ships, `.external.` one deployed from an app catalog,
and `WebPart.unknown.<id>` one that did not render (its tag then reads
`undefined web part (<title>)`).

**What is not a web part (VERIFIED).** `data-sp-feature-tag` is on the
chrome too - "Page Chrome", "Suite Navigation Placeholder", "Site header
host", "Comments", `CanvasComponent.internal.<guid>` - and the chrome's
`data-sp-feature-instance-id` starts with `_`. Neither is ever a zone.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ZONE_MICROSOFT = "microsoft"
ZONE_CUSTOM = "custom"
ZONE_AUTHOR = "author"
ZONES = (ZONE_MICROSOFT, ZONE_CUSTOM, ZONE_AUTHOR)

# --------------------------------------------------------------- the page

#: Literals that say "this document is a SharePoint page". VERIFIED: a
#: modern page's raw HTML carries `spClientSidePageContext` (not always
#: `_spPageContextInfo`, which classic pages and `project_profile` use); the
#: rendered DOM carries the canvas and chrome attributes. Not
#: `data-sp-canvascontrol`: it turns up inside JSON on pages that are not
#: canvases, so it proves nothing.
_PAGE_SIGNALS = re.compile(
    r"spClientSidePageContext|_spPageContextInfo|data-sp-feature-tag|"
    r"data-automation-id=[\"']?Canvas(?:Zone|Control)|"
    r"id=[\"']?spPageChromeAppDiv",
    re.I)

#: The attribute SharePoint writes on every web part, and on the chrome.
#: VERIFIED: a web part's value is `<Alias> web part (<title>)`; the Text
#: web part's is "Rich Text Editor" (seen inside the title area).
FEATURE_TAG = "data-sp-feature-tag"

#: `<Alias> web part (<title>)`. VERIFIED.
FEATURE_TAG_PATTERN = re.compile(r"^\s*(\S+)\s+web\s*part\s*\((.*)\)\s*$", re.I)

#: Attributes that carry a web part's *type* id (the manifest GUID), in the
#: order they are trusted. VERIFIED: `data-sp-web-part-id`, on the same
#: element as the feature tag. The rest are older spellings `audit/spfx.py`
#: also looks for - HYPOTHESIS.
WEB_PART_ID_ATTRIBUTES = ("data-sp-web-part-id", "data-webpart-id",
                          "data-sp-componentid", "data-sp-component-id")

#: One placement of a part on the page. VERIFIED; the chrome's values start
#: with `_` ("_Page Chrome").
INSTANCE_ATTRIBUTE = "data-sp-feature-instance-id"

#: The root of every web part's zone. VERIFIED: `div.ControlZone`, `id` =
#: the instance id, inside `CanvasSection` inside `CanvasZone`.
CANVAS_CONTROL = '[data-automation-id="CanvasControl"]'

#: `WebPart.<Alias>.internal|external.<instance>` or
#: `WebPart.unknown.<instance>`. VERIFIED.
VIEWPORT_ATTRIBUTE = "data-viewport-id"
VIEWPORT_PATTERN = re.compile(
    r"^WebPart\.(?:(?P<alias>[^.]+)\.(?P<origin>internal|external)|"
    r"(?P<unknown>unknown))\.", re.I)
ORIGIN_MICROSOFT = "internal"
ORIGIN_CATALOG = "external"

#: Feature tags that are the chrome, normalised by `_norm`. VERIFIED.
CHROME_FEATURE_TAGS = frozenset({"pagechrome", "suitenavigationplaceholder",
                                 "siteheaderhost", "comments"})
CHROME_FEATURE_PREFIXES = ("CanvasComponent.",)

#: Application customizer placeholders. VERIFIED: `data-sp-placeholder`
#: `Top`, `TopContent` and `Bottom` (`#spTopPlaceholder`,
#: `#spTopContentPlaceholder`, `#spBottomPlaceholder`). They are always in
#: the page, empty unless an extension filled them - so only a placeholder
#: with something in it is a zone.
PLACEHOLDER_ATTRIBUTE = "data-sp-placeholder"

#: Kept for callers; there is no page-header element (VERIFIED): the title
#: area is the `PageTitle` web part, whose text is
#: `[data-automation-id="TitleTextId"]`.
PAGE_HEADER_SELECTORS = ()
PAGE_TITLE_TEXT = '[data-automation-id="TitleTextId"]'

#: Microsoft's chrome, named so the report can say *what* was left out.
#: Naming is all these do: anything outside a recognised zone is Microsoft's
#: whether or not it matched one of them, which is what keeps a selector
#: that has changed from leaking chrome into the findings. VERIFIED unless
#: marked.
PLATFORM_REGIONS = (
    ("suite-bar", ("#SuiteNavWrapper", "#O365_NavHeader")),
    ("app-bar", ("#sp-appBar",)),
    # `data-automationid`, no hyphen, on the site header.
    ("site-header", ('[data-automationid="SiteHeader"]', "#spSiteHeader")),
    ("hub-nav", ('[data-automationid="HubNav"]',)),               # HYPOTHESIS
    ("command-bar", ("#spCommandBar",)),
    ("site-nav", ("#spLeftNav",)),
    ("comments", ("#CommentsWrapper",)),
    ("footer", ('[data-automation-id="SiteFooter"]', "#spSiteFooter")),  # HYPOTHESIS
)

#: The wrapper of the whole page, canvas included. Counted by name, never
#: excluded: excluding it would exclude every web part with it.
PAGE_CHROME = ("page-chrome", ("#spPageChromeAppDiv",))

#: What axe is confined to in the browser pass. Empty on purpose: an SPFx
#: part can move its markup out of the canvas into the chrome (see
#: `SPFX_MODULE_CLASS`), and no CSS selector names "an element with a CSS
#: module class". So axe reads the page minus the chrome regions below, and
#: `classify_browser_issues` drops and counts whatever it found outside a
#: zone.
AXE_INCLUDE = ()

#: The chrome axe is told to leave alone.
AXE_EXCLUDE = tuple(selector for _name, selectors in PLATFORM_REGIONS
                    for selector in selectors)

#: An SPFx CSS-module class: `<name>_<8 hex>`, the hash the SPFx build
#: appends (VERIFIED on the live pages: the custom header an SPFx part draws
#: into the chrome is `header.<name>_<hash>`). Microsoft's own generated
#: classes are a different shape (`f_xxxxx_y`, `root-123`). HEURISTIC: a
#: Microsoft bundle built the SPFx way would match too.
SPFX_MODULE_CLASS = re.compile(r"^([A-Za-z][A-Za-z0-9]+)_([0-9a-f]{8})$")

# ----------------------------------------------------- Microsoft's parts

#: Microsoft's web part type ids. VERIFIED on live pages; ids not here are
#: learned with `OotbRegistry.register` / `--ootb-registry`.
OOTB_WEB_PART_IDS = {
    "cbe7b0a9-3504-44dd-a3a3-0e5cacd07788": "Title area",
    "8c88f208-6c77-4bdb-86a0-0c47b4316588": "News",
    "eb95c819-ab8f-4689-bd03-0c2d65d47b1f": "Site activity",
    "c70391ea-0b10-4ee9-b2b4-006d3fcad0cd": "Quick links",
    "f92bf067-bc19-489e-a556-7fe95f508720": "List",
}

#: The title area's type id. VERIFIED.
PAGE_TITLE_ID = "cbe7b0a9-3504-44dd-a3a3-0e5cacd07788"

#: Aliases and toolbox names of the web parts Microsoft ships, normalised
#: by `_norm` (lower case, letters and digits only, a trailing "web part"
#: removed). VERIFIED for `pagetitle`, `news`, `siteactivity`, `quicklinks`,
#: `list`; HYPOTHESIS for the rest. Matched against the **alias**, never the
#: localised title. A part whose viewport says `.external.` is custom
#: whatever its alias.
OOTB_FEATURE_NAMES = frozenset({
    "richtexteditor", "text", "image", "hero", "news", "newsreel",
    "quicklinks", "events", "highlightedcontent", "contentrollup",
    "documentlibrary", "list", "listproperties", "fileviewer", "file",
    "documentembed", "embed", "divider", "spacer", "button", "calltoaction",
    "people", "pageproperties", "siteactivity", "sites", "weather",
    "worldclock", "youtube", "twitter", "yammer", "vivaengage",
    "conversations", "microsoftforms", "forms", "powerbi", "stream",
    "planner", "bingmaps", "maps", "codesnippet", "countdowntimer",
    "groupcalendar", "imagegallery", "link", "markdown", "organizationchart",
    "orgchart", "recentdocuments", "savedforlater", "myfeed", "banner",
    "kindleinstantpreview", "connectors", "officeconnectors", "spotlight",
    "pagetitle", "title", "quickchart", "highlights", "recentsites",
    "followedsites", "communityengagement", "emphasis",
})

#: Feature-tag names of the Text web part, whose content is the author's
#: own rich text and is audited with every rule. VERIFIED: "Rich Text
#: Editor" (seen nested in the title area; a standalone Text part is the
#: same editor - HYPOTHESIS).
TEXT_FEATURE_NAMES = frozenset({"richtexteditor", "text", "rte"})

#: The alias SharePoint writes for a part that has not rendered. VERIFIED.
UNRENDERED_ALIAS = "undefined"


def _norm(name: str) -> str:
    text = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    return text[:-7] if text.endswith("webpart") and len(text) > 7 else text


def _guid(value: str) -> str:
    return (value or "").strip().strip("{}").lower()


@dataclass
class OotbRegistry:
    """Microsoft's web part ids and names, as far as this run knows them.

    Starts with the ids seen on live pages (`OOTB_WEB_PART_IDS`), never with
    ones typed from memory. `register` and `load_file` are how it grows: a
    file of the shape

        {"web_parts": [{"id": "<guid>", "name": "Quick links"}],
         "feature_tags": ["Some new part"]}

    read from a live page.
    """
    ids: dict = field(default_factory=lambda: dict(OOTB_WEB_PART_IDS))
    names: set = field(default_factory=lambda: set(OOTB_FEATURE_NAMES))

    def register(self, web_part_id: str = "", name: str = "") -> None:
        if web_part_id:
            self.ids[_guid(web_part_id)] = name or web_part_id
        if name:
            self.names.add(_norm(name))

    def load_file(self, path) -> int:
        """Add what a JSON file lists, and say how many entries it had."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        count = 0
        for entry in data.get("web_parts") or []:
            if isinstance(entry, dict) and entry.get("id"):
                self.register(str(entry["id"]), str(entry.get("name") or ""))
                count += 1
        for name in data.get("feature_tags") or []:
            self.register(name=str(name))
            count += 1
        return count

    def name_for_id(self, web_part_id: str) -> str:
        return self.ids.get(_guid(web_part_id), "")

    def knows_name(self, feature_tag: str) -> bool:
        """Is this alias (or legacy tag) one of Microsoft's parts?"""
        match = FEATURE_TAG_PATTERN.match(feature_tag or "")
        return _norm(match.group(1) if match else feature_tag) in self.names


#: The registry used when the caller passes none.
DEFAULT_REGISTRY = OotbRegistry()

# ------------------------------------------------- what counts as content

#: The rules that are about what an **author** puts into a Microsoft web
#: part, and therefore still apply inside one. Everything else found inside
#: Microsoft's markup - roles, ARIA wiring, keyboard handling, landmarks,
#: table structure, the part's own colours - is Microsoft's to fix and is
#: counted as skipped.
#:
#: Why each family is here:
#:
#: * alt text - the author types it in the image's properties;
#: * link names and link text - a quick link's title, a button's label;
#: * headings - the author chooses a part's title and its level in the
#:   page, and an empty one is an empty title;
#: * language - a passage in another language is the author's text;
#: * captions and media alternatives - the author uploads the video;
#: * an image's file format - the author uploads the picture, so a JPEG
#:   where a modern format would do is the author's choice to make;
#: * AI-sounding wording - the words are the author's (every `ai-` rule);
#: * abbreviations - the author's text.
#:
#: Colour contrast is deliberately **not** here: inside a Microsoft part it
#: is the theme's, and colour the author typed into rich text lives in the
#: Text web part, which is audited with every rule.
OOTB_CONTENT_RULES = frozenset({
    # static rules (audit/rules)
    "image-alt", "image-alt-filename",
    "link-text-vague", "seo-empty-link",
    "heading-order",
    "html-lang-mismatch", "language-change",
    "media-captions", "embedded-video-alternatives", "image-modern-format",
    "abbreviation-expansion", "bp-ai-markup-artifact",
    # axe-core
    "axe:image-alt", "axe:image-redundant-alt", "axe:input-image-alt",
    "axe:area-alt", "axe:object-alt",
    "axe:link-name",
    "axe:empty-heading", "axe:heading-order",
    "axe:valid-lang",
    "axe:video-caption", "axe:audio-caption",
})

#: Rule-id prefixes that are content by construction: the AI review judges
#: the author's wording.
OOTB_CONTENT_PREFIXES = ("ai-",)

#: Categories that are content by construction.
OOTB_CONTENT_CATEGORIES = frozenset({"ai-text"})


def is_content_finding(issue) -> bool:
    """Is this finding about what the author put in, not how it is built?"""
    rule = getattr(issue, "rule_id", "") or ""
    if rule in OOTB_CONTENT_RULES or rule.startswith(OOTB_CONTENT_PREFIXES):
        return True
    if getattr(issue, "category", "") in OOTB_CONTENT_CATEGORIES:
        return True
    # A rule that crashed is a fact about this run, never hidden.
    return bool((getattr(issue, "details", None) or {}).get("rule_error"))


# ------------------------------------------------------------- the map

@dataclass
class Zone:
    """One part of the page somebody other than Microsoft is answerable for."""
    kind: str
    #: What a reader calls it: the part's title or alias, "Text", "Title
    #: area", "Application customizer (Top)".
    name: str
    element: object = field(repr=False, compare=False, default=None)
    #: Only `OOTB_CONTENT_RULES` apply: the markup is Microsoft's, the
    #: content is the author's.
    content_only: bool = False
    #: The attribute and value that decided this, so a wrong call can be
    #: argued with.
    evidence: str = ""
    web_part_id: str = ""
    #: The manifest the part came from, when a repository named it.
    manifest: str = ""
    #: The part's code name (`QuickLinksWebPart`), when the page said it.
    alias: str = ""
    #: False for a part SharePoint placed and did not render
    #: (`undefined web part`, `WebPart.unknown`): nothing of it was audited,
    #: and that is a fact about the site the report has to show.
    rendered: bool = True
    #: True when the zone was inferred rather than read (`HEURISTIC`).
    heuristic: bool = False

    def details(self) -> dict:
        """What every finding in this zone carries."""
        out = {"zone": self.kind, "zone_name": self.name,
               "zone_evidence": self.evidence}
        if self.kind == ZONE_CUSTOM:
            out["web_part"] = self.name
        if self.manifest:
            out["manifest"] = self.manifest
        if self.content_only:
            out["zone_content_only"] = True
        if self.heuristic:
            out["zone_heuristic"] = True
        return out


@dataclass
class ZoneMap:
    """A page, split into what is audited and what is Microsoft's."""
    zones: list = field(default_factory=list)
    #: Elements outside every zone: Microsoft's, not audited.
    platform_elements: int = 0
    elements_total: int = 0
    #: `{region name: count}` for the chrome that was recognised by name.
    platform_regions: dict = field(default_factory=dict)

    @property
    def recognised(self) -> bool:
        """Did this page have a canvas this module could read?"""
        return bool(self.zones)

    def zone_of(self, element):
        """The zone `element` sits in, or `None` when it is Microsoft's."""
        owners = {id(zone.element): zone for zone in self.zones}
        node = element
        while node is not None:
            zone = owners.get(id(node))
            if zone is not None:
                return zone
            node = getattr(node, "parent", None)
        return None


def is_sharepoint_page(markup: str) -> bool:
    """Does this document look like a modern SharePoint page at all?"""
    return bool(_PAGE_SIGNALS.search(markup or ""))


def _web_part_id(element) -> str:
    for attribute in WEB_PART_ID_ATTRIBUTES:
        value = element.get(attribute)
        if value:
            return _guid(str(value))
    return ""


def _is_chrome_tag(element) -> bool:
    """A `data-sp-feature-tag` on Microsoft's chrome rather than a part."""
    tag = str(element.get(FEATURE_TAG) or "")
    if not tag:
        return False
    if str(element.get(INSTANCE_ATTRIBUTE) or "").startswith("_"):
        return True
    return _norm(tag) in CHROME_FEATURE_TAGS or tag.startswith(CHROME_FEATURE_PREFIXES)


#: Elements whose presence makes a placeholder worth auditing.
_SUBSTANCE = ("img", "svg", "a", "button", "input", "select", "textarea",
              "iframe", "video", "audio", "picture", "canvas", "object")


def _has_content(element) -> bool:
    if element.get_text(strip=True):
        return True
    return element.find(_SUBSTANCE) is not None


def _repo_match(element, web_parts):
    """The repository part `element` is (or contains), or `None`."""
    if not web_parts:
        return None
    from audit import within as within_mod

    ids = {_web_part_id(element)}
    for tagged in element.select(f"[{FEATURE_TAG}]"):
        ids.add(_web_part_id(tagged))
    ids.discard("")
    for part in web_parts:
        if part.id and _guid(part.id) in ids:
            return part
    for part in web_parts:
        selectors = part.selectors()
        try:
            within_mod.narrow_any(element, selectors)
        except within_mod.ScopeNotFound:
            # `narrow_any` searches below the element; the element itself
            # may be the match.
            if any(_matches_self(element, selector) for selector in selectors):
                return part
            continue
        return part
    return None


def _matches_self(element, selector: str) -> bool:
    try:
        return bool(element.parent is not None
                    and any(found is element
                            for found in element.parent.select(selector)))
    except Exception:  # noqa: BLE001 - an invalid selector is not a match
        return False


def _part_element(root):
    """The element inside a canvas control that says which part it is.

    The outermost feature tag that is not chrome: the title area holds a
    "Rich Text Editor" inside it, and the part is the title area.
    """
    if root.get(FEATURE_TAG) and not _is_chrome_tag(root):
        return root
    for element in root.select(f"[{FEATURE_TAG}]"):
        if not _is_chrome_tag(element):
            return element
    return None


def _viewport(root):
    """`(alias, origin)` from the part's viewport id; origin `unknown` for a
    part that did not render, `("", "")` without one."""
    elements = [root] if root.get(VIEWPORT_ATTRIBUTE) else []
    elements.extend(root.select(f"[{VIEWPORT_ATTRIBUTE}]"))
    for element in elements:
        match = VIEWPORT_PATTERN.match(str(element.get(VIEWPORT_ATTRIBUTE) or ""))
        if match:
            if match.group("unknown"):
                return "", "unknown"
            return match.group("alias"), match.group("origin").lower()
    return "", ""


def _classify(root, web_parts, registry: OotbRegistry) -> Zone:
    """Decide one candidate's zone. Strongest evidence first."""
    part = _repo_match(root, web_parts)
    if part is not None:
        return Zone(ZONE_CUSTOM, part.title or part.alias, root,
                    evidence=f"manifest {part.manifest}",
                    web_part_id=_guid(part.id), manifest=part.manifest,
                    alias=part.alias)

    placeholder = root.get(PLACEHOLDER_ATTRIBUTE)
    if placeholder:
        return Zone(ZONE_CUSTOM, f"Application customizer ({placeholder})",
                    root, evidence=f'{PLACEHOLDER_ATTRIBUTE}="{placeholder}"')

    tagged = _part_element(root)
    tag = str(tagged.get(FEATURE_TAG) or "") if tagged is not None else ""
    web_part_id = _web_part_id(tagged) if tagged is not None else ""
    web_part_id = web_part_id or _web_part_id(root)
    match = FEATURE_TAG_PATTERN.match(tag)
    alias = match.group(1) if match else ""
    title = (match.group(2).strip() if match else "") or ""
    view_alias, origin = _viewport(root)
    alias = alias or view_alias
    evidence = "; ".join(bit for bit in (
        f'{FEATURE_TAG}="{tag}"' if tag else "",
        f"{VIEWPORT_ATTRIBUTE} {origin}" if origin else "",
        f"web part id {web_part_id}" if web_part_id else "") if bit)
    name = title or (_display(tag) if tag and not match else "") or alias \
        or web_part_id or "Web part"

    if _norm(alias) == UNRENDERED_ALIAS or origin == "unknown":
        return Zone(ZONE_CUSTOM, f"{title or name} (not rendered)", root,
                    evidence=evidence, web_part_id=web_part_id, alias="",
                    rendered=False)
    if tag and not match and _norm(tag) in TEXT_FEATURE_NAMES:
        return Zone(ZONE_AUTHOR, "Text", root, evidence=evidence)
    if origin == ORIGIN_CATALOG:
        return Zone(ZONE_CUSTOM, name, root, evidence=evidence,
                    web_part_id=web_part_id, alias=alias)
    known = registry.name_for_id(web_part_id) if web_part_id else ""
    if web_part_id == PAGE_TITLE_ID or _norm(alias) == "pagetitle":
        return Zone(ZONE_AUTHOR, "Title area", root, content_only=True,
                    evidence=evidence, web_part_id=web_part_id, alias=alias)
    if (known or origin == ORIGIN_MICROSOFT
            or (alias and _norm(alias) in registry.names)
            or (tag and not match and registry.knows_name(tag))):
        return Zone(ZONE_AUTHOR, name if (title or not known) else known, root,
                    content_only=True, evidence=evidence,
                    web_part_id=web_part_id, alias=alias)
    return Zone(ZONE_CUSTOM, name, root, evidence=evidence,
                web_part_id=web_part_id, alias=alias)


def _display(tag: str) -> str:
    """`Quick links web part` -> `Quick links`."""
    text = re.sub(r"\s*web\s*part\s*$", "", (tag or "").strip(), flags=re.I)
    return text or tag


def _in_page_order(document, elements) -> list:
    from audit.within import _outermost

    unique, seen = [], set()
    for element in elements:
        if id(element) not in seen:
            seen.add(id(element))
            unique.append(element)
    order = {id(element): index
             for index, element in enumerate(document.find_all(True))}
    unique.sort(key=lambda element: order.get(id(element), 0))
    return _outermost(unique)


def _select(document, selectors) -> list:
    found = []
    for selector in selectors:
        try:
            found.extend(document.select(selector))
        except Exception:  # noqa: BLE001 - one bad selector is not the map
            continue
    return found


def _candidates(document, web_parts) -> list:
    """The roots of the zones read off the page, outermost, in page order.

    A canvas control is the root of its part. Outside a canvas (a page
    without `CanvasControl`, an older layout) a web part's own tagged
    element is; the chrome's tags are never candidates.
    """
    found = _select(document, [CANVAS_CONTROL])
    found.extend(element for element in _select(document, [f"[{FEATURE_TAG}]"])
                 if not _is_chrome_tag(element))
    found.extend(element for element in _select(
                     document, [f"[{attribute}]" for attribute in WEB_PART_ID_ATTRIBUTES])
                 if not _is_chrome_tag(element))
    found.extend(element for element in _select(document, [f"[{PLACEHOLDER_ATTRIBUTE}]"])
                 if _has_content(element))
    for part in web_parts or ():
        found.extend(_select(document, part.selectors()))
    return _in_page_order(document, found)


def _module_class(element) -> tuple:
    """`(stem, hash, class)` of the first SPFx CSS-module class, or `()`."""
    for value in element.get("class") or ():
        match = SPFX_MODULE_CLASS.match(str(value))
        if match:
            return match.group(1), match.group(2), str(value)
    return ()


def _in_region(element, regions: set) -> bool:
    node = element
    while node is not None:
        if id(node) in regions:
            return True
        node = getattr(node, "parent", None)
    return False


def _outside_canvas(document, zones, web_parts) -> list:
    """SPFx markup that left the canvas: `custom`, named by what built it.

    HEURISTIC. An SPFx part may render into the chrome (a custom header in
    the app chrome, a pop-up on `body`); what it leaves behind is its CSS
    module classes, `<name>_<hash>`, where the hash is one per stylesheet of
    one bundle. Microsoft builds some of its own chrome the same way (the
    left navigation, the persona card), so:

    * an element inside a named chrome region (`PLATFORM_REGIONS`) is never
      taken - an SPFx extension renders into placeholders, not there;
    * an element is bound to a part on the page when its stem is the part's
      alias (`fooHeader_…` -> `FooHeaderWebPart`) or its hash is one the
      part's own markup in the canvas uses;
    * one bound to nothing is still `custom`, named by its stem: a part
      nobody recognised is audited rather than dropped.
    """
    inside = set()
    for zone in zones:
        inside.add(id(zone.element))
        inside.update(id(element) for element in zone.element.find_all(True))
    regions = {id(element) for element in _select(document, AXE_EXCLUDE)}
    roots = [element for element in document.find_all(True)
             if id(element) not in inside and _module_class(element)
             and not _in_region(element, regions)]
    if not roots:
        return []
    by_stem, by_hash = {}, {}
    for zone in zones:
        if zone.kind != ZONE_CUSTOM:
            continue
        if zone.alias:
            by_stem.setdefault(_norm(zone.alias), zone.name)
        for element in (zone.element, *zone.element.find_all(True)):
            found = _module_class(element)
            if found:
                by_hash.setdefault(found[1], zone.name)
    for part in web_parts or ():
        if part.alias:
            by_stem.setdefault(_norm(part.alias), part.title or part.alias)
    roots = _in_page_order(document, roots)
    # A stem names its own bundle's hash: the header that is
    # `fooHeader_1a2b3c4d` makes every other `*_1a2b3c4d` the same part's.
    for root in roots:
        stem, digest, _value = _module_class(root)
        if _norm(stem) in by_stem:
            by_hash.setdefault(digest, by_stem[_norm(stem)])
    out = []
    for root in roots:
        stem, digest, value = _module_class(root)
        owner = by_stem.get(_norm(stem)) or by_hash.get(digest)
        name = f"{owner} (outside the canvas)" if owner             else f"SPFx outside the canvas ({stem})"
        evidence = f"HEURISTIC: CSS module class {value} outside the canvas"
        if owner:
            how = "stem" if _norm(stem) in by_stem else "bundle hash"
            evidence += f"; bound to {owner} by its {how}"
        out.append(Zone(ZONE_CUSTOM, name, root, evidence=evidence,
                        heuristic=True))
    return out


def _count_regions(document) -> dict:
    regions = {}
    for name, selectors in (*PLATFORM_REGIONS, PAGE_CHROME):
        for selector in selectors:
            try:
                if document.select_one(selector) is not None:
                    regions[name] = regions.get(name, 0) + 1
                    break
            except Exception:  # noqa: BLE001
                continue
    return regions


def map_document(document, web_parts=(), registry: OotbRegistry | None = None) -> ZoneMap:
    """Split a parsed page into zones. `document` is a BeautifulSoup tree."""
    registry = registry or DEFAULT_REGISTRY
    zones = [_classify(element, web_parts, registry)
             for element in _candidates(document, web_parts)]
    if zones:
        # Only on a page this module recognised: a CSS module class on an
        # ordinary page says nothing about SharePoint.
        zones.extend(_outside_canvas(document, zones, web_parts))
        order = {id(element): index
                 for index, element in enumerate(document.find_all(True))}
        zones.sort(key=lambda zone: order.get(id(zone.element), 0))
    total = len(document.find_all(True))
    inside = sum(1 + len(zone.element.find_all(True)) for zone in zones)
    return ZoneMap(zones=zones, platform_elements=max(0, total - inside),
                   elements_total=total,
                   platform_regions=_count_regions(document))


def map_page(markup: str, web_parts=(), registry: OotbRegistry | None = None):
    """`(document, ZoneMap)` for a page's markup."""
    from bs4 import BeautifulSoup

    document = BeautifulSoup(markup or "", "html.parser")
    return document, map_document(document, web_parts, registry)


# ---------------------------------------------------- applying the map

def apply_zone(issues, zone: Zone, summary: "Summary | None" = None) -> list:
    """Tag `issues` found in `zone`, dropping Microsoft's structural ones.

    Returns what is kept. Anything dropped is counted on `summary`, by rule,
    so the report can say how much was left out and why.
    """
    kept = []
    for issue in issues:
        if zone.content_only and not is_content_finding(issue):
            if summary is not None:
                summary.skip_finding(issue)
            continue
        details = dict(getattr(issue, "details", None) or {})
        details.update(zone.details())
        issue.details = details
        kept.append(issue)
    if summary is not None:
        summary.count_findings(zone, len(kept))
    return kept


def _first_target(selector) -> str:
    """axe's `target` is a list (one entry per frame or shadow root)."""
    if isinstance(selector, (list, tuple)):
        for entry in selector:
            text = _first_target(entry)
            if text:
                return text
        return ""
    return str(selector or "")


_OPEN_TAG = re.compile(r"<\s*([a-zA-Z][\w-]*)([^>]*)>")
_ATTRIBUTE = re.compile(r"([\w:-]+)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)")
#: Attributes specific enough to find an element by, strongest first.
_IDENTIFYING = ("id", "src", "href", "data-sp-feature-instance-id", "name",
                "aria-label", "class")


def _by_snippet(document, snippet: str):
    """The element an engine quoted, found by its identifying attributes."""
    match = _OPEN_TAG.search(snippet or "")
    if not match:
        return None
    name = match.group(1).lower()
    attributes = {key.lower(): value.strip("\"'")
                  for key, value in _ATTRIBUTE.findall(match.group(2))}
    for key in _IDENTIFYING:
        value = attributes.get(key)
        if not value:
            continue
        for element in document.find_all(name):
            current = element.get(key)
            if isinstance(current, list):
                current = " ".join(current)
            if current == value:
                return element
    return None


def element_for(document, issue):
    """The element a browser finding is about, or `None`."""
    target = _first_target(getattr(issue, "selector", ""))
    if target:
        try:
            found = document.select_one(target)
        except Exception:  # noqa: BLE001 - axe writes selectors soupsieve may not read
            found = None
        if found is not None:
            return found
    return _by_snippet(document, getattr(issue, "snippet", "") or "")


def classify_browser_issues(issues, markup: str, web_parts=(),
                            registry: OotbRegistry | None = None,
                            summary: "Summary | None" = None) -> list:
    """Keep the browser findings that belong to a zone, tagged with it.

    `markup` is the DOM the browser built (`PageAudit.html`, which needs
    `capture_html=True`). A finding on Microsoft's chrome is dropped and
    counted; one inside a Microsoft web part keeps only the content rules;
    one that cannot be placed at all - no selector the parser reads, no
    quoted element it can find - is kept and marked `zone: ""`, because
    hiding a finding nobody located would be guessing in the quiet direction.
    """
    document, zone_map = map_page(markup, web_parts, registry)
    kept = []
    for issue in issues:
        element = element_for(document, issue)
        if element is None:
            details = dict(getattr(issue, "details", None) or {})
            details.setdefault("zone", "")
            issue.details = details
            kept.append(issue)
            continue
        zone = zone_map.zone_of(element)
        if zone is None:
            if summary is not None:
                summary.skip_finding(issue, platform=True)
            continue
        kept.extend(apply_zone([issue], zone, summary=summary))
    return kept


def browser_options(options):
    """`options` confined to the zones, for the browser pass on SharePoint.

    axe is told to leave the chrome regions alone (`AXE_EXCLUDE`) and reads
    the rest; nothing is `include`d, because the markup an SPFx part moves
    out of the canvas has no selector (see `AXE_INCLUDE`). What it finds
    outside a zone is dropped and counted by `classify_browser_issues`. The
    other three engines read the whole document by construction - the same
    reason `--within` switches them off - so they are switched off here, and
    the DOM is captured so each finding can be placed.
    """
    from dataclasses import replace

    exclude = list(getattr(options, "exclude", []) or [])
    exclude.extend(selector for selector in AXE_EXCLUDE if selector not in exclude)
    return replace(options, include=list(AXE_INCLUDE), exclude=exclude,
                   run_htmlcs=False, run_states=False, run_measurements=False,
                   capture_html=True)


# --------------------------------------------------------- lazy loading

#: Starts scrolling the page to the bottom in steps, then back to the top,
#: so web parts SharePoint renders only when they come into view are in the
#: DOM before anything reads it. HYPOTHESIS: that SharePoint Online defers
#: web parts below the fold. Returns at once; poll `SCROLL_DONE_SCRIPT`.
#: Bounded: at most 60 steps, so an infinite feed cannot hold the run.
SCROLL_SCRIPT = """(function() {
  window.__xaScrollDone = false;
  var steps = 0, limit = 60;
  var scroller = document.querySelector('[data-is-scrollable="true"]')
      || document.scrollingElement || document.documentElement;
  function step() {
    var before = scroller.scrollTop;
    scroller.scrollTop = before + Math.max(200, window.innerHeight * 0.8);
    steps += 1;
    if (scroller.scrollTop === before || steps >= limit) {
      scroller.scrollTop = 0;
      window.__xaScrollDone = true;
      return;
    }
    setTimeout(step, 150);
  }
  step();
  return true;
})();"""

#: `true` once `SCROLL_SCRIPT` has reached the bottom and come back.
SCROLL_DONE_SCRIPT = "(function() { return window.__xaScrollDone === true; })();"

#: How many canvas controls are in the DOM now. Polled until it stops
#: changing, which is how "every web part has rendered" can be asked
#: without knowing how many there are.
#: Counts canvas controls plus the parts that have rendered (a tag that is
#: no longer `undefined web part`), so a part that renders late changes the
#: number even when no control was added. VERIFIED on a live home page: 17
#: parts before scrolling, 24 after, stable within 750-2000 ms.
CANVAS_COUNT_SCRIPT = (
    "(function() { return document.querySelectorAll("
    f"'{CANVAS_CONTROL}').length + document.querySelectorAll("
    f"'[{FEATURE_TAG}]:not([{FEATURE_TAG}^=\"undefined\"])').length; }})();")


# -------------------------------------------------------------- summary

def _part_entry(zone: Zone) -> dict:
    entry = {"kind": zone.kind, "placements": 0, "findings": 0,
             "evidence": zone.evidence, "content_only": zone.content_only}
    if not zone.rendered:
        entry["rendered"] = False
    if zone.heuristic:
        entry["heuristic"] = True
    return entry


@dataclass
class Summary:
    """What a whole run split, audited and left out. Serialisable as-is."""
    pages: int = 0
    #: Pages on which no canvas was recognised: not audited, listed.
    pages_without_canvas: list = field(default_factory=list)
    #: `{zone kind: placements}`.
    zones: dict = field(default_factory=dict)
    #: `{name: {"kind", "placements", "findings", "evidence"}}`.
    parts: dict = field(default_factory=dict)
    #: Microsoft's elements outside every zone, summed over pages.
    platform_elements: int = 0
    platform_regions: dict = field(default_factory=dict)
    #: Findings in Microsoft's markup that were not reported.
    skipped_findings: int = 0
    skipped_by_rule: dict = field(default_factory=dict)

    def add_page(self, zone_map: ZoneMap, url: str) -> None:
        self.pages += 1
        if not zone_map.recognised:
            self.pages_without_canvas.append(url)
            return
        self.platform_elements += zone_map.platform_elements
        for name, count in zone_map.platform_regions.items():
            self.platform_regions[name] = self.platform_regions.get(name, 0) + count
        for zone in zone_map.zones:
            self.zones[zone.kind] = self.zones.get(zone.kind, 0) + 1
            part = self.parts.setdefault(zone.name, _part_entry(zone))
            part["placements"] += 1

    def count_findings(self, zone: Zone, count: int) -> None:
        part = self.parts.setdefault(zone.name, _part_entry(zone))
        part["findings"] += count

    def skip_finding(self, issue, platform: bool = False) -> None:
        self.skipped_findings += 1
        rule = getattr(issue, "rule_id", "") or ""
        self.skipped_by_rule[rule] = self.skipped_by_rule.get(rule, 0) + 1

    def as_dict(self) -> dict:
        return {
            "pages": self.pages,
            "pages_without_canvas": list(self.pages_without_canvas),
            "zones": dict(self.zones),
            "parts": {name: dict(value) for name, value in self.parts.items()},
            "skipped": {
                "elements": self.platform_elements,
                "regions": dict(self.platform_regions),
                "findings": self.skipped_findings,
                "by_rule": dict(sorted(self.skipped_by_rule.items(),
                                       key=lambda kv: (-kv[1], kv[0]))),
            },
        }
