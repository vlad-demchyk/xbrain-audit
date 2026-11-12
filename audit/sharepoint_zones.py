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
    # A classic page's chrome (SharePoint 2013 master page). VERIFIED on a
    # live classic subsite: the suite bar, the ribbon, the title area (which
    # holds the search box web part) and the left navigation.
    ("classic-suite-bar", ("#suiteBarDelta",)),
    ("classic-ribbon", ("#s4-ribbonrow",)),
    ("classic-title-area", ("#titleAreaBox",)),
    ("classic-nav", ("#sideNavBox",)),
)

#: The wrapper of the whole page, canvas included. Counted by name, never
#: excluded: excluding it would exclude every web part with it.
PAGE_CHROME = ("page-chrome", ("#spPageChromeAppDiv",))

#: The modern canvas and its layout. VERIFIED: both are on a modern page
#: even when nobody put a web part on it - the layout is then empty.
CANVAS = '[data-automation-id="Canvas"]'
CANVAS_LAYOUT = '[data-automation-id="CanvasLayout"]'

#: A classic page's content area, the first that exists. VERIFIED on a live
#: classic subsite: `#DeltaPlaceHolderMain` inside `#contentBox`.
CLASSIC_MAIN = ("#DeltaPlaceHolderMain", "#contentBox")
#: A classic web part: `div#WebPartWPQ<n>` carrying `webpartid`. VERIFIED.
#: The search box in the title area is one too, and is outside the main
#: area - Microsoft's chrome.
CLASSIC_WEB_PART = "div[id^=WebPartWPQ][webpartid]"
#: A classic rich-text field (a publishing page's content, a Content Editor
#: web part's body). VERIFIED inside the web parts of a live page.
CLASSIC_RICH_TEXT = ".ms-rtestate-field"

#: What kind of page `map_document` recognised.
PAGE_MODERN = "modern"
PAGE_EMPTY_CANVAS = "empty-canvas"
PAGE_CLASSIC = "classic"

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
    # HTML_CodeSniffer, by success criterion: 1.1.1 (text alternatives),
    # 2.4.4 (link purpose), 3.1.2 (language of parts).
    "htmlcs:1_1_1", "htmlcs:2_4_4", "htmlcs:3_1_2",
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
    #: `PAGE_MODERN`, `PAGE_EMPTY_CANVAS`, `PAGE_CLASSIC`, or "" for a page
    #: this module could not read.
    page_kind: str = ""
    #: Said about a recognised page with nothing in it to audit.
    note: str = ""

    @property
    def recognised(self) -> bool:
        """Did this page have a canvas (or a classic content area) this
        module could read? An empty one counts: it was read, and it is
        empty - which is a different answer from "not audited"."""
        return bool(self.zones) or self.page_kind in (PAGE_EMPTY_CANVAS,
                                                      PAGE_CLASSIC)

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


#: What draws something on screen inside an SVG. Anything of these under a
#: `<defs>` or `<symbol>` only defines it.
_SVG_DRAWING = ("path", "circle", "rect", "polygon", "polyline", "ellipse",
                "line", "use", "image", "text", "foreignobject")
_SVG_DEFINITION = ("defs", "symbol")
_INTERACTIVE_OR_MEDIA = ("a", "button", "input", "select", "textarea", "img",
                         "iframe", "video", "audio", "object", "embed")


def _hidden_by_style(element) -> bool:
    if element.has_attr("hidden") or element.get("aria-hidden") == "true":
        return True
    style = (element.get("style") or "").replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    return ("width:0" in style and "height:0" in style)


def _is_definitions(element) -> bool:
    """An SVG sprite or definitions block: draws nothing, is nobody's part.

    Microsoft's file icons ship an SVG `<defs>` container with a CSS module
    class (`ColoredFolderDefs_<hash>`), outside the canvas on every page that
    shows a document. The `<name>_<hash>` shape made it "SPFx outside the
    canvas" - a custom part nobody deployed, measured on a live intranet.
    Nothing in it is rendered, so there is nothing in it to audit, whoever
    built it: an SVG whose every drawing element sits in `<defs>`/`<symbol>`,
    or an element hidden by its own attributes with no text, is skipped.
    """
    if element.name in _INTERACTIVE_OR_MEDIA or element.find(_INTERACTIVE_OR_MEDIA):
        return False
    svgs = [element] if element.name == "svg" else element.find_all("svg")
    if svgs and element.name != "svg":
        # Text outside the SVGs is content.
        for text in element.find_all(string=True):
            if text.strip() and text.find_parent("svg") is None:
                return False
    if svgs:
        drawn = [node for svg in svgs for node in svg.find_all(_SVG_DRAWING)
                 if node.find_parent(_SVG_DEFINITION) is None]
        if not drawn:
            return True
    return _hidden_by_style(element) and not element.get_text(strip=True)


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
    ancestors = {id(parent) for zone in zones for parent in zone.element.parents}
    regions = {id(element) for element in _select(document, AXE_EXCLUDE)}
    roots = [element for element in document.find_all(True)
             if id(element) not in inside and id(element) not in ancestors
             and _module_class(element)
             and not _in_region(element, regions)
             and not _is_definitions(element)]
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


def _empty_canvas(document) -> bool:
    """A modern canvas with nothing in its layout: a page nobody authored.

    VERIFIED on a live tenant: `[data-automation-id=Canvas]` holding an empty
    `[data-automation-id=CanvasLayout]`, no canvas control anywhere.
    """
    canvas = _select(document, [CANVAS])
    if not canvas:
        return False
    layouts = _select(canvas[0], [CANVAS_LAYOUT])
    if not layouts:
        return False
    return not any(_has_content(layout) or layout.find(True) is not None
                   for layout in layouts)


def _classic_zones(document):
    """The zones of a classic page, or `None` when it is not one.

    Each web part in the main content area with something in it is a zone,
    `custom`: on a classic page the web part's markup is the site owner's
    (a Content Editor holds their HTML, a Script Editor their script), so
    every rule applies. A rich-text field outside every web part (a
    publishing page's content) is the author's. Everything else - the suite
    bar, the ribbon, the title area with its search box, the left
    navigation - is Microsoft's.
    """
    main = None
    for selector in CLASSIC_MAIN:
        found = _select(document, [selector])
        if found:
            main = found[0]
            break
    if main is None:
        return None
    zones = []
    parts = _in_page_order(document, _select(main, [CLASSIC_WEB_PART]))
    for part in parts:
        if not _has_content(part):
            continue
        ident = str(part.get("id") or "")
        short = ident[len("WebPart"):] if ident.startswith("WebPart") else ident
        guid = _guid(str(part.get("webpartid") or ""))
        zones.append(Zone(
            ZONE_CUSTOM, f"Classic web part ({short})", part,
            evidence=f'classic page: id="{ident}"; webpartid={guid}',
            web_part_id=guid))
    inside = {id(element) for zone in zones
              for element in (zone.element, *zone.element.find_all(True))}
    fields = [field_ for field_ in _in_page_order(
                  document, _select(main, [CLASSIC_RICH_TEXT]))
              if id(field_) not in inside and _has_content(field_)]
    for field_ in fields:
        zones.append(Zone(ZONE_AUTHOR, "Classic page content", field_,
                          evidence=f"classic page: {CLASSIC_RICH_TEXT}"))
    return zones


def map_document(document, web_parts=(), registry: OotbRegistry | None = None) -> ZoneMap:
    """Split a parsed page into zones. `document` is a BeautifulSoup tree.

    Three kinds of page are read: a modern page (its canvas controls), a
    modern page whose canvas is empty (recognised, no zones, said so), and a
    classic page (`_classic_zones`). Anything else has no zones and is not
    recognised, which the caller reports.
    """
    registry = registry or DEFAULT_REGISTRY
    zones = [_classify(element, web_parts, registry)
             for element in _candidates(document, web_parts)]
    page_kind, note = "", ""
    if zones:
        page_kind = PAGE_MODERN
        # Only on a page this module recognised: a CSS module class on an
        # ordinary page says nothing about SharePoint.
        zones.extend(_outside_canvas(document, zones, web_parts))
    elif _empty_canvas(document):
        page_kind, note = PAGE_EMPTY_CANVAS, "the page's canvas is empty"
    else:
        classic = _classic_zones(document)
        if classic is not None:
            zones, page_kind = classic, PAGE_CLASSIC
            if not zones:
                note = "the classic page has no web part with content"
    if zones:
        order = {id(element): index
                 for index, element in enumerate(document.find_all(True))}
        zones.sort(key=lambda zone: order.get(id(zone.element), 0))
    total = len(document.find_all(True))
    inside = sum(1 + len(zone.element.find_all(True)) for zone in zones)
    return ZoneMap(zones=zones, platform_elements=max(0, total - inside),
                   elements_total=total,
                   platform_regions=_count_regions(document),
                   page_kind=page_kind, note=note)


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


def settle_references(issues, document) -> list:
    """Drop `aria-reference-broken` findings the whole page resolves.

    A zone is audited as a fragment, and an `aria-describedby` in a web part
    may name an element elsewhere on the page - the page title, a status
    line in the chrome. The fragment cannot see it and reported the
    reference broken, `exact`. The page can: a finding whose every missing
    id exists in the page's own markup is not a broken reference.
    """
    ids = None
    kept = []
    for issue in issues:
        missing = (getattr(issue, "details", None) or {}).get("missing")
        if getattr(issue, "rule_id", "") == "aria-reference-broken" and missing:
            if ids is None:
                ids = {str(tag.get("id")) for tag in document.find_all(id=True)}
            if all(token in ids for token in missing):
                continue
        kept.append(issue)
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
    from privacy import mask_text

    for key in _IDENTIFYING:
        value = attributes.get(key)
        if not value:
            continue
        for element in document.find_all(name):
            current = element.get(key)
            if isinstance(current, list):
                current = " ".join(current)
            # The quoted snippet was masked at birth (`privacy`); the DOM
            # was not.
            if current == value or mask_text(current) == value:
                return element
    return None


def element_by_path(document, path: str):
    """The element at `path` in the captured DOM, or `None`.

    `path` is what the state pass and the HTML_CodeSniffer collector record
    (`html/body:1/div:0/a:3`): from the root, each step a tag and its index
    among the parent's element children. Every step's tag is checked, so a
    DOM that changed between the finding and the capture (a part that
    re-rendered at another width) gives `None`, never a neighbour.
    """
    from bs4 import Tag

    steps = [step for step in str(path or "").split("/") if step]
    if not steps or steps[0] != "html":
        return None
    node = next((child for child in document.children
                 if isinstance(child, Tag) and child.name == "html"), None)
    for step in steps[1:]:
        if node is None:
            return None
        name, _, index = step.rpartition(":")
        if not name or not index.isdigit():
            return None
        children = [child for child in node.children if isinstance(child, Tag)]
        position = int(index)
        if position >= len(children) or children[position].name != name:
            return None
        node = children[position]
    return node


def element_for(document, issue):
    """The element a browser finding is about, or `None`.

    The recorded path first (exact, when the engine gave one), then the
    selector, then the quoted markup.
    """
    path = (getattr(issue, "details", None) or {}).get("dom_path")
    if path:
        found = element_by_path(document, path)
        if found is not None:
            return found
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
    from audit.browser import COVERAGE_RULES

    document, zone_map = map_page(markup, web_parts, registry)
    kept = []
    for issue in issues:
        rule = getattr(issue, "rule_id", "") or ""
        if rule in COVERAGE_RULES or rule in RUN_FACT_RULES:
            # Not a finding about an element: what axe could not reach
            # (recorded as coverage by `browser.take_untested_frames`), an
            # engine that failed, a focus the run could not measure. Facts
            # about this run, passed on as they are.
            kept.append(issue)
            continue
        engine = browser_engine(issue)
        if rule in page_measurement_rules():
            # A budget over the whole page load - Microsoft's bundles, its
            # chrome's DOM and requests included. No zone owns it; the
            # numbers stay in the performance section.
            if summary is not None:
                summary.count_browser(engine, "page_level", rule)
            continue
        if is_page_frame_finding(issue):
            # The page frame's: see `PAGE_FRAME_RULES`.
            if summary is not None:
                summary.skip_finding(issue, platform=True)
                summary.count_browser(engine, "platform", rule)
            continue
        element = element_for(document, issue)
        if element is None:
            details = dict(getattr(issue, "details", None) or {})
            details.setdefault("zone", "")
            issue.details = details
            kept.append(issue)
            if summary is not None:
                summary.count_browser(engine, "unplaced", rule)
            continue
        zone = zone_map.zone_of(element)
        if zone is None:
            if summary is not None:
                summary.skip_finding(issue, platform=True)
                summary.count_browser(engine, "platform", rule)
            continue
        placed = apply_zone([issue], zone, summary=summary)
        if summary is not None:
            summary.count_browser(engine, "placed" if placed else "skipped", rule)
        kept.extend(placed)
    return kept


#: Browser findings that are facts about the run, not about an element:
#: kept as they are, never placed and never counted as unplaced. An engine
#: that failed (`state-pass`, `htmlcs` with `engine_error`), and a page whose
#: focus styles could not be read.
RUN_FACT_RULES = frozenset({"state-pass", "htmlcs", "state:focus-not-measured"})

#: Findings about the page frame, which on SharePoint is Microsoft's: "can a
#: keyboard get past the navigation" (2.4.1), asked by three engines. The
#: navigation (the suite bar, the app bar, the site header and its menus)
#: is the chrome. SharePoint Online draws its own skip link there -
#: `sp-skipToContent`, a link to the canvas that appears on the first Tab;
#: HYPOTHESIS for a tenant this was not run on - and nobody running the site
#: can add or change one. Each engine points the finding at some element:
#: the state pass at the first focusable one it examined, which with the
#: chrome excluded is inside a web part, and HTML_CodeSniffer at whichever
#: link it read first. Placed by that element it would blame a part for the
#: platform's navigation, so it is dropped and counted as Microsoft's.
PAGE_FRAME_RULES = frozenset({"state:no-skip-link", "axe:bypass", "htmlcs:2_4_1"})


def is_page_frame_finding(issue) -> bool:
    """Is this the page frame's question (`PAGE_FRAME_RULES`)?

    HTML_CodeSniffer files an `<iframe>` without a title (`H64`) under 2.4.1
    too; that one is about an element a part may own, and is placed.
    """
    rule = getattr(issue, "rule_id", "") or ""
    if rule not in PAGE_FRAME_RULES:
        return False
    code = str((getattr(issue, "details", None) or {}).get("code", ""))
    return not (rule.startswith("htmlcs:") and ".H64" in code)


def page_measurement_rules() -> frozenset:
    """The rules a page-load measurement can raise (`DEFAULT_BUDGETS`)."""
    from audit.browser import DEFAULT_BUDGETS

    return frozenset(rule for _limit, _severity, rule in DEFAULT_BUDGETS.values())


def browser_engine(issue) -> str:
    """Which browser pass a finding came from, as coverage names them."""
    rule = getattr(issue, "rule_id", "") or ""
    if rule.startswith("state:"):
        return "states"
    if rule.startswith("htmlcs:"):
        return "htmlcs"
    if rule.startswith("axe:"):
        return "axe"
    return "measurements"


def browser_options(options):
    """`options` confined to the zones, for the browser pass on SharePoint.

    Every engine is told to leave the chrome regions alone (`AXE_EXCLUDE`)
    and reads the rest; nothing is `include`d, because the markup an SPFx
    part moves out of the canvas has no selector (see `AXE_INCLUDE`). axe
    takes the exclusion as its context; the state pass skips elements inside
    it; HTML_CodeSniffer walks the whole document and its messages inside it
    are dropped in the page. The DOM is captured so each finding can be
    placed in a zone by `classify_browser_issues`: axe by its selector, the
    state pass and HTML_CodeSniffer by the element's recorded path. What
    lands outside a zone is dropped and counted as Microsoft's; what cannot
    be placed is kept and counted as unplaced.

    The three whole-document engines were off here until 0.77.0, because
    their findings could not be placed: a SharePoint audit checked no
    keyboard, focus or hover-only content and never settled
    `perf-image-loading`.
    What is still left out, and why, is said by `classify_browser_issues`
    (the page-level budgets, `no-skip-link`) and by the coverage.
    """
    from dataclasses import replace

    exclude = list(getattr(options, "exclude", []) or [])
    exclude.extend(selector for selector in AXE_EXCLUDE if selector not in exclude)
    return replace(options, include=list(AXE_INCLUDE), exclude=exclude,
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
    #: Pages that were read and had nothing to audit (an empty canvas, a
    #: classic page with no web part content), with the reason.
    pages_empty: list = field(default_factory=list)
    #: Classic pages, read through `_classic_zones`.
    pages_classic: list = field(default_factory=list)
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
    #: The browser pass: which engines ran (`passes`), and per engine how
    #: many findings were placed in a zone, dropped as Microsoft's
    #: (`platform`), skipped by a content-only zone (`skipped`), left
    #: unplaced (kept, zone ""), or not listed as page-level measurements.
    browser: dict = field(default_factory=dict)

    def add_page(self, zone_map: ZoneMap, url: str) -> None:
        self.pages += 1
        if not zone_map.recognised:
            self.pages_without_canvas.append(url)
            return
        if zone_map.page_kind == PAGE_CLASSIC:
            self.pages_classic.append(url)
        if not zone_map.zones:
            # `reason` is a code a report translates; `note` the sentence.
            reason = ("classic-empty" if zone_map.page_kind == PAGE_CLASSIC
                      else zone_map.page_kind)
            self.pages_empty.append({"url": url, "reason": reason,
                                     "note": zone_map.note})
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

    def record_passes(self, options) -> None:
        """Which browser engines this run asked for, as they will run."""
        from audit import browser

        available = browser.engines_available()
        self.browser["passes"] = {
            "axe": bool(getattr(options, "run_axe", False)) and bool(available.get("axe")),
            "states": bool(getattr(options, "run_states", False)),
            "measurements": bool(getattr(options, "run_measurements", False)),
            "htmlcs": bool(getattr(options, "run_htmlcs", False)) and bool(available.get("htmlcs")),
        }

    def count_browser(self, engine: str, outcome: str, rule: str = "") -> None:
        """One browser finding's fate: `placed`, `platform`, `skipped`,
        `unplaced` or `page_level`, by engine and, when unplaced, by rule."""
        engines = self.browser.setdefault("engines", {})
        counts = engines.setdefault(engine, {})
        counts[outcome] = counts.get(outcome, 0) + 1
        if outcome == "unplaced" and rule:
            by_rule = self.browser.setdefault("unplaced_by_rule", {})
            by_rule[rule] = by_rule.get(rule, 0) + 1

    def skip_finding(self, issue, platform: bool = False) -> None:
        self.skipped_findings += 1
        rule = getattr(issue, "rule_id", "") or ""
        self.skipped_by_rule[rule] = self.skipped_by_rule.get(rule, 0) + 1

    def as_dict(self) -> dict:
        return {
            "pages": self.pages,
            "pages_without_canvas": list(self.pages_without_canvas),
            "pages_empty": [dict(entry) for entry in self.pages_empty],
            "pages_classic": list(self.pages_classic),
            "zones": dict(self.zones),
            "parts": {name: dict(value) for name, value in self.parts.items()},
            "skipped": {
                "elements": self.platform_elements,
                "regions": dict(self.platform_regions),
                "findings": self.skipped_findings,
                "by_rule": dict(sorted(self.skipped_by_rule.items(),
                                       key=lambda kv: (-kv[1], kv[0]))),
            },
            "browser": {key: (dict(value) if isinstance(value, dict) else value)
                        for key, value in self.browser.items()},
        }
