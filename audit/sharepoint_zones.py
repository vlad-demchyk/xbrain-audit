"""Which part of a SharePoint page is whose, and which part to audit.

A modern SharePoint Online page is three kinds of markup in one document,
and only two of them are anybody's to fix:

* **microsoft** - the chrome: the suite bar, the app bar, the site and hub
  header, the command bar, the comments, the footer, and every wrapper the
  canvas puts around a web part. Nobody involved in the site can change a
  line of it. It is **not audited**, and what was left out is counted, so a
  short list is never mistaken for a clean page.
* **custom** - SPFx web parts and application customizer placeholders. Code
  somebody wrote and deployed into the tenant: audited with every rule and
  named by the part that owns it.
* **author** - what the page's author typed or chose: the Text web part
  (the rich-text editor), the page header (title, banner), and the content
  inside Microsoft's own web parts - an image's alt text, a quick link's
  title, a heading. For a Microsoft web part only the rules about that
  content apply (`OOTB_CONTENT_RULES`); a structural or ARIA defect in the
  part's own markup is Microsoft's, and is counted as skipped, not reported.

**What is verified and what is not.** Nothing here has yet been checked
against a live tenant's DOM: the site this was written for needs a sign-in
this code has not had. Every selector below carries one of two marks:

* ``VERIFIED`` - checked against something real (Microsoft's documentation
  or a live response);
* ``HYPOTHESIS`` - SharePoint's DOM as it is commonly documented by the
  community and remembered, to be confirmed on a live page after sign-in.

The classification is built so that a wrong hypothesis fails loudly rather
than quietly: a page on which no canvas is recognised is reported as such
(`ZoneMap.recognised` is false) instead of being audited whole or not at
all, and an unknown web part is treated as **custom** - audited in full -
rather than as Microsoft's and dropped.

**Recognising Microsoft's web parts without a list of their GUIDs.** There
is no official list of the out-of-the-box web part ids, and inventing one
from memory would be worse than having none. So the primary signal is the
name SharePoint writes into `data-sp-feature-tag`, matched against
`OOTB_FEATURE_NAMES`; a GUID registry (`OotbRegistry`) exists beside it and
starts empty, to be filled from a live page (`?maintenancemode=true`, or a
page's `CanvasContent1`) with `register()` or `load_file()`. A web part whose
id is in neither, and whose tag names nothing Microsoft ships, is custom.
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

#: Literals that say "this document is a SharePoint page". `_spPageContextInfo`
#: is the one `project_profile` already relies on (VERIFIED as a signature
#: used there; its presence in every modern page is a HYPOTHESIS). The rest
#: are the canvas attributes below.
_PAGE_SIGNALS = re.compile(
    r"_spPageContextInfo|data-sp-feature-tag|data-sp-canvascontrol|"
    r"data-automation-id=[\"']?CanvasZone|id=[\"']?spPageChromeAppDiv",
    re.I)

#: The attribute SharePoint writes on the container of every canvas control
#: (web part or text), naming what it is. HYPOTHESIS: the value is the web
#: part's title, sometimes followed by "web part"; the Text web part is
#: "Rich Text Editor".
FEATURE_TAG = "data-sp-feature-tag"

#: Attributes that carry a web part's *type* id (the manifest GUID), in the
#: order they are trusted. HYPOTHESIS for every one: `audit/spfx.py` looks
#: for the same names when it finds a repository's parts in a page.
WEB_PART_ID_ATTRIBUTES = ("data-sp-web-part-id", "data-webpart-id",
                          "data-sp-componentid", "data-sp-component-id")

#: The attribute that identifies one placement of a part on the page.
#: HYPOTHESIS.
INSTANCE_ATTRIBUTE = "data-sp-feature-instance-id"

#: Application customizer placeholders. VERIFIED: the placeholders are
#: called `Top` and `Bottom` (Microsoft Learn, "Use page placeholders from
#: Application Customizer"). HYPOTHESIS: the DOM marks them with
#: `data-sp-placeholder`.
PLACEHOLDER_ATTRIBUTE = "data-sp-placeholder"

#: The page header: title, banner image, author byline. The words are the
#: author's, the markup is Microsoft's - so it is an author zone with the
#: content rules only. HYPOTHESIS for the selector.
PAGE_HEADER_SELECTORS = ('[data-automation-id="pageHeader"]',)

#: Microsoft's chrome, named so the report can say *what* was left out.
#: Naming is all these do: anything outside a recognised zone is Microsoft's
#: whether or not it matched one of them, which is what keeps a selector
#: that has changed from leaking chrome into the findings. HYPOTHESIS, all.
PLATFORM_REGIONS = (
    ("suite-bar", ("#SuiteNavWrapper", "#SuiteNavPlaceholder", "#O365_NavHeader")),
    ("app-bar", ("#sp-appBar", '[data-automation-id="appBar"]')),
    ("site-header", ('[data-automationid="SiteHeader"]',
                     '[data-automation-id="SiteHeader"]', "#spSiteHeader")),
    ("hub-nav", ('[data-automationid="HubNav"]', '[data-automation-id="HubNav"]')),
    ("command-bar", ("#spCommandBar", '[data-automation-id="pageCommandBar"]')),
    ("site-nav", ("#spLeftNav", '[data-automation-id="spNav"]')),
    ("comments", ('[data-automation-id="CommentsWrapper"]', "#CommentsWrapper")),
    ("footer", ('[data-automation-id="SiteFooter"]', "#spSiteFooter")),
)

#: What axe is confined to in the browser pass: every zone that can hold
#: anything somebody other than Microsoft wrote. A selector that matches
#: nothing is dropped by the script before axe runs (see
#: `audit.browser.axe_script`), so a wrong guess here narrows nothing
#: rather than failing the pass.
AXE_INCLUDE = (f"[{FEATURE_TAG}]", f"[{PLACEHOLDER_ATTRIBUTE}]") + PAGE_HEADER_SELECTORS

#: What axe is told to leave alone even inside an included zone: the chrome,
#: in case a region above is nested in the canvas.
AXE_EXCLUDE = tuple(selector for _name, selectors in PLATFORM_REGIONS
                    for selector in selectors)

# ----------------------------------------------------- Microsoft's parts

#: Feature-tag names of the web parts Microsoft ships, normalised by
#: `_norm` (lower case, letters and digits only, a trailing "web part"
#: removed). HYPOTHESIS: taken from the names the web part toolbox shows,
#: not from a live DOM. A custom part that happens to share one of these
#: names is recognised by its GUID first when a repository is given.
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
#: own rich text and is audited with every rule. HYPOTHESIS.
TEXT_FEATURE_NAMES = frozenset({"richtexteditor", "text", "rte"})


def _norm(name: str) -> str:
    text = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    return text[:-7] if text.endswith("webpart") and len(text) > 7 else text


def _guid(value: str) -> str:
    return (value or "").strip().strip("{}").lower()


@dataclass
class OotbRegistry:
    """Microsoft's web part ids and names, as far as this run knows them.

    Starts with no ids on purpose (see the module docstring). `register`
    and `load_file` are how it grows: a file of the shape

        {"web_parts": [{"id": "<guid>", "name": "Quick links"}],
         "feature_tags": ["Some new part"]}

    read from a live page, never typed from memory.
    """
    ids: dict = field(default_factory=dict)
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
        return _norm(feature_tag) in self.names


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
    #: What a reader calls it: the part's alias or title, "Text", "Page
    #: header", "Application customizer (Top)".
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


def _repo_match(element, web_parts):
    """The repository part `element` is (or contains), or `None`."""
    if not web_parts:
        return None
    from audit import within as within_mod

    own_id = _web_part_id(element)
    for part in web_parts:
        if own_id and part.id and own_id == _guid(part.id):
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


def _classify(element, web_parts, registry: OotbRegistry) -> Zone:
    """Decide one candidate's zone. Strongest evidence first."""
    part = _repo_match(element, web_parts)
    if part is not None:
        return Zone(ZONE_CUSTOM, part.title or part.alias, element,
                    evidence=f"manifest {part.manifest}",
                    web_part_id=_guid(part.id), manifest=part.manifest)

    placeholder = element.get(PLACEHOLDER_ATTRIBUTE)
    if placeholder:
        return Zone(ZONE_CUSTOM, f"Application customizer ({placeholder})",
                    element, evidence=f'{PLACEHOLDER_ATTRIBUTE}="{placeholder}"')

    tag = str(element.get(FEATURE_TAG) or "")
    web_part_id = _web_part_id(element)
    if tag:
        evidence = f'{FEATURE_TAG}="{tag}"'
        if _norm(tag) in TEXT_FEATURE_NAMES:
            return Zone(ZONE_AUTHOR, "Text", element, evidence=evidence)
        known = registry.name_for_id(web_part_id) if web_part_id else ""
        if known or registry.knows_name(tag):
            return Zone(ZONE_AUTHOR, known or _display(tag), element,
                        content_only=True, evidence=evidence,
                        web_part_id=web_part_id)
        return Zone(ZONE_CUSTOM, _display(tag), element, evidence=evidence,
                    web_part_id=web_part_id)
    if web_part_id:
        known = registry.name_for_id(web_part_id)
        evidence = f"web part id {web_part_id}"
        if known:
            return Zone(ZONE_AUTHOR, known, element, content_only=True,
                        evidence=evidence, web_part_id=web_part_id)
        return Zone(ZONE_CUSTOM, web_part_id, element, evidence=evidence,
                    web_part_id=web_part_id)
    # Only the page header is left among the candidates.
    return Zone(ZONE_AUTHOR, "Page header", element, content_only=True,
                evidence=PAGE_HEADER_SELECTORS[0])


def _display(tag: str) -> str:
    """`Quick links web part` -> `Quick links`."""
    text = re.sub(r"\s*web\s*part\s*$", "", (tag or "").strip(), flags=re.I)
    return text or tag


def _candidates(document, web_parts) -> list:
    selectors = [f"[{FEATURE_TAG}]", f"[{PLACEHOLDER_ATTRIBUTE}]",
                 *PAGE_HEADER_SELECTORS,
                 *(f"[{attribute}]" for attribute in WEB_PART_ID_ATTRIBUTES)]
    for part in web_parts or ():
        selectors.extend(part.selectors())
    found = []
    for selector in selectors:
        try:
            found.extend(document.select(selector))
        except Exception:  # noqa: BLE001 - one bad selector is not the map
            continue
    from audit.within import _outermost

    unique, seen = [], set()
    for element in found:
        if id(element) not in seen:
            seen.add(id(element))
            unique.append(element)
    # Page order, then outermost: a part's wrapper and the part inside it
    # are one zone, and the wrapper is the one whose markup includes both.
    order = {id(element): index
             for index, element in enumerate(document.find_all(True))}
    unique.sort(key=lambda element: order.get(id(element), 0))
    return _outermost(unique)


def _count_regions(document) -> dict:
    regions = {}
    for name, selectors in PLATFORM_REGIONS:
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

    axe is given the zones as `include` and the chrome as `exclude`. The
    other three engines read the whole document by construction - the same
    reason `--within` switches them off - so they are switched off here too,
    and the DOM is captured so `classify_browser_issues` can place what axe
    found.
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
CANVAS_COUNT_SCRIPT = (
    "(function() { return document.querySelectorAll("
    f"'[{FEATURE_TAG}], [{PLACEHOLDER_ATTRIBUTE}]').length; }})();")


# -------------------------------------------------------------- summary

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
            part = self.parts.setdefault(zone.name, {
                "kind": zone.kind, "placements": 0, "findings": 0,
                "evidence": zone.evidence, "content_only": zone.content_only})
            part["placements"] += 1

    def count_findings(self, zone: Zone, count: int) -> None:
        part = self.parts.setdefault(zone.name, {
            "kind": zone.kind, "placements": 0, "findings": 0,
            "evidence": zone.evidence, "content_only": zone.content_only})
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
