"""Auditing the page a visitor actually gets, by running a real browser.

The static rules read the HTML the server sent. This reads the page after
the browser has finished with it, which is a different document on most
modern sites and the only one that matters to a visitor.

There is no new dependency for this. The app already ships QtWebEngine —
the same Chromium that draws the site preview — so the audit runs in a real
engine rather than an approximation of one. That single fact is what makes
this worth doing: it removes the two limits the static pass has to declare
as `NEEDS_BROWSER`, and it un-blinds the case where the static pass sees
nothing at all.

Three things happen once the page has settled:

1. **Engines.** `axe-core` and `HTML_CodeSniffer` are injected as plain
   scripts and run against the live DOM. They are Deque's and Squiz's rules,
   not ours, and they disagree with each other often enough to be worth
   running together: on a published comparison against 142 known problems,
   axe alone found 27%, HTML_CodeSniffer alone 20%, and both together 35%.
2. **Measurements.** Navigation and resource timings, read from the
   Performance API. These are readings, not inferences, and are labelled as
   such so the report never mixes the two.
3. **States.** The page is interacted with — every control focused, menus
   opened — and re-examined. This is the part no snapshot can do, and the
   largest remaining source of automatable findings that does not involve a
   model. See `audit/states.py`.

Everything here is asynchronous, because `QWebEnginePage.runJavaScript` and
`loadFinished` are. The driver is therefore built on signals and a callback,
not on blocking waits: blocking the thread that owns the page is what
deadlocks Qt.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .base import (
    ACCESSIBILITY, ADVISORY, CRITICAL, EXACT, MINOR, MODERATE, NEEDS_BROWSER,
    PERFORMANCE, SERIOUS, Issue,
)
from . import engine_codes

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
AXE_PATH = VENDOR_DIR / "axe.min.js"
HTMLCS_PATH = VENDOR_DIR / "HTMLCS.js"

#: axe severity names -> ours. axe's "critical"/"serious"/"moderate"/"minor"
#: happen to be the same four words, which is why ours are named this way.
_AXE_IMPACT = {
    "critical": CRITICAL, "serious": SERIOUS,
    "moderate": MODERATE, "minor": MINOR,
}

#: HTML_CodeSniffer emits Error / Warning / Notice. A Notice is a "check this
#: manually" prompt, not a finding, so it is dropped rather than shown as a
#: problem the user then has to learn to ignore.
_HTMLCS_TYPE = {1: SERIOUS, 2: MODERATE}


#: The size a browser pass runs at when nobody asked for a particular one.
#:
#: It has to be a real size. `QWebEnginePage` with no widget behind it is
#: 0x0, and a page that believes it is 0 pixels tall has no element with a
#: layout box: `getBoundingClientRect()` returns zeroes, axe skips the checks
#: that need geometry, and the state pass concludes that every focused
#: element is outside the viewport - because it is.
#:
#: The default used to be `None`, described as "whatever the engine defaults
#: to". There is no such default, and the cost was measured 2026-08-31 by
#: running the same page both ways:
#:
#:     https://www.python.org/     151 findings unsized -> 244 sized
#:                                 (31 axe:color-contrast existed only sized,
#:                                  htmlcs contrast 87 -> 145)
#:     https://en.wikipedia.org/wiki/Rome
#:                                 3 state:focus-outside-viewport existed only
#:                                 unsized - a finding of the 0x0 layout, not
#:                                 of the page
#:     https://www.gov.uk/         17 -> 18, and the one state finding changed
#:                                 identity between the two runs
#:
#: So the unsized pass both lost real findings and invented false ones. This
#: matches `responsive.BREAKPOINTS[0]`, which owns the same numbers, so a
#: plain `--browser` run and `--breakpoints desktop` answer the same.
DEFAULT_VIEWPORT = (1440, 900)


@dataclass
class BrowserAuditOptions:
    """What to run, and what to leave alone."""
    run_axe: bool = True
    #: Both engines on by default: the overlap is what raises coverage from
    #: 27% to 35%, and the duplicates between them are collapsed below.
    run_htmlcs: bool = True
    run_measurements: bool = True
    run_states: bool = True
    #: CSS selectors excluded from the engines. Shared with the app's
    #: suppression list, so "not this part of the page" is said once.
    exclude: list = field(default_factory=list)
    #: One selector the audit is confined to: "only inside this part of the
    #: page". A SharePoint web part is delivered as a subtree of somebody
    #: else's document, and auditing the tenant's chrome around it reports
    #: hundreds of findings nobody involved can act on. Passed to axe as its
    #: `include` context; see `audit/within.py` for the static side.
    within: str = ""
    #: Several selectors the audit is confined to, together: "only inside
    #: these parts". What a SharePoint page needs, where the parts somebody
    #: other than Microsoft wrote are many subtrees rather than one - see
    #: `audit.sharepoint_zones.browser_options`. A selector that matches
    #: nothing on the page is dropped before axe runs, and a page on which
    #: none matches is audited as having nothing in scope rather than failing.
    include: list = field(default_factory=list)
    #: Rule ids to switch off, passed through to axe as `rules: {id: {...}}`.
    disabled_rules: list = field(default_factory=list)
    #: Milliseconds to wait after load before auditing, for the JavaScript
    #: that renders the page to finish. Deliberately generous: auditing a
    #: half-rendered SPA produces confident nonsense. 2500ms is enough for
    #: most React/Vue/Next.js apps to hydrate and render their content.
    settle_ms: int = 2500
    #: Let a `file://` page read its neighbours on disk. Off for anything
    #: fetched over the network, where it would be a way for a remote page to
    #: read the local drive; switched on only when the user themselves pointed
    #: the tool at a file, and then only because an exported page whose images
    #: sit beside it would otherwise be audited half-loaded.
    allow_local_files: bool = False
    #: Which `prefers-color-scheme` the page is told, "light" or "dark". A
    #: site with a dark theme has a second set of colours, and Coach's 41
    #: indigo focus rings were 2.65-2.93:1 there - found by hand, because the
    #: pass only ever saw the light one. Chromium takes the scheme once per
    #: process (`apply_color_scheme`), so it is one scheme per run.
    color_scheme: str = "light"
    #: The size the page believes it is being viewed at, as `(width, height)`
    #: in CSS pixels. It is what makes a responsive audit possible: media
    #: queries answer to this number, so a page audited at one size has only
    #: been audited at one size - the mobile navigation of most sites does not
    #: exist in the DOM at desktop width, and neither do its findings.
    #:
    #: `None` means genuinely unsized, and there is no engine default behind
    #: it: an unsized page reports `innerWidth`/`innerHeight` of **0**, so
    #: nothing has a layout box. That is why the default here is a real size
    #: rather than `None` - see `DEFAULT_VIEWPORT`.
    viewport: tuple | None = DEFAULT_VIEWPORT
    #: Also bring back the DOM as the browser built it. This is what lets a
    #: client-rendered page be *read* rather than only audited: the copy and
    #: the links of an application shell exist only after hydration, and a
    #: plain fetch of it returns neither.
    capture_html: bool = False
    capture_text: bool = False
    text_within: str = ""
    performance_repeats: int = 1
    performance_scenario: list = field(default_factory=list)
    performance_fresh: bool = False


#: The rendered document, source of both text and links for a page whose
#: server returns an empty shell.
#:
#: The doctype is put back by hand: `documentElement.outerHTML` starts at
#: `<html>` and leaves it out, so a rendered page read without this looks like
#: a page with no doctype at all - and one of the rules says so, three pages in
#: a row, about a site whose doctype is right there in the response.
HTML_SCRIPT = (
    '(function () {'
    '  var type = document.doctype;'
    '  var prefix = type ? "<!DOCTYPE " + type.name + ">" : "";'
    '  return prefix + document.documentElement.outerHTML;'
    '})()'
)


def engines_available() -> dict:
    """Which vendored engines are actually present.

    Checked rather than assumed: the files are large, and a checkout that
    skipped them should degrade to the static rules with a clear reason,
    not fail at the point of use.
    """
    return {"axe": AXE_PATH.is_file(), "htmlcs": HTMLCS_PATH.is_file()}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------- JS payloads

#: axe rules that ship disabled and that this pass turns on.
#:
#: `target-size` is WCAG 2.2's 2.5.8 (AA): a pointer target of at least
#: 24x24 CSS px, or one whose 24 px circle does not overlap a neighbour's.
#: Disabled in axe because it measures every widget and is slow on big
#: pages; left off here it meant the criterion the EN 301 549 V4.1.1 update
#: made a legal requirement under the EAA was never checked, and the static
#: `viewport-touch-target` cannot see a size that comes from a CSS class.
#: axe itself keeps the exceptions out - inline links (`widget-not-inline-
#: matches`), fully obscured controls - and says `incomplete` where it cannot
#: decide, which `issues_from_axe` weighs as a note.
_AXE_OFF_BY_DEFAULT = ("target-size",)

#: Rules whose check `data` is worth carrying: what was measured.
_AXE_MEASURED = ("target-size",)

def axe_script(options: BrowserAuditOptions) -> str:
    """axe-core plus the call that runs it and hands back JSON.

    `exclude` and per-rule disabling are passed to axe rather than filtered
    afterwards, so a suppressed region costs nothing to analyse instead of
    being analysed and then thrown away.
    """
    rules = {rule: {"enabled": True} for rule in _AXE_OFF_BY_DEFAULT}
    # A person's "off" wins over ours "on": the same dict, written second.
    rules.update({rule: {"enabled": False} for rule in options.disabled_rules})
    config = {
        "resultTypes": ["violations", "incomplete"],
        "rules": rules,
    }
    context = {}
    if options.exclude:
        context["exclude"] = [[selector] for selector in options.exclude]
    # "Only inside this" - the opposite question from `exclude`, and the one
    # a delivered fragment asks. axe takes both in the same context object.
    if getattr(options, "within", ""):
        context["include"] = [[options.within]]
    # Several parts at once. Unlike `within`, a selector here is a guess
    # about a platform's DOM (see `audit.sharepoint_zones`), so the ones that
    # match nothing are dropped in the page before axe sees them: axe refuses
    # a context whose include finds no element, and one stale selector must
    # not fail the pass for the parts that are there.
    include = list(getattr(options, "include", None) or [])
    scope_guard = ""
    if include:
        context["include"] = context.get("include", []) + [[s] for s in include]
        scope_guard = """
  context.include = context.include.filter(function(entry) {
    try { return document.querySelector(entry[0]) !== null; }
    catch (e) { return false; }
  });
  if (!context.include.length) {
    return Promise.resolve(JSON.stringify({violations: [], incomplete: [],
                                           scope_empty: true}));
  }"""
    return f"""
(function() {{
  {_read(AXE_PATH)}
  var context = {json.dumps(context) or "document"};{scope_guard}
  return axe.run(Object.keys(context).length ? context : document, {json.dumps(config)})
    .then(function(results) {{
      var measured = {json.dumps(list(_AXE_MEASURED))};
      var pack = function(nodes, bucket) {{
        return (nodes || []).map(function(v) {{
          return {{
            bucket: bucket,
            id: v.id,
            impact: v.impact,
            help: v.help,
            description: v.description,
            helpUrl: v.helpUrl,
            tags: v.tags,
            nodes: (v.nodes || []).slice(0, 20).map(function(n) {{
              var packed = {{
                target: (n.target || []).join(' '),
                html: (n.html || '').slice(0, 300),
                failureSummary: (n.failureSummary || '').slice(0, 600)
              }};
              if (measured.indexOf(v.id) !== -1) {{
                var data = {{}}, related = [];
                [].concat(n.any || [], n.all || [], n.none || []).forEach(function(c) {{
                  if (c && c.data && typeof c.data === 'object') {{
                    Object.keys(c.data).forEach(function(k) {{
                      var x = c.data[k];
                      if (typeof x === 'number' || typeof x === 'string') data[k] = x;
                    }});
                  }}
                  (c && c.relatedNodes || []).slice(0, 3).forEach(function(r) {{
                    related.push((r.target || []).join(' '));
                  }});
                }});
                packed.data = data;
                packed.related = related;
              }}
              return packed;
            }})
          }};
        }});
      }};
      return JSON.stringify({{
        violations: pack(results.violations, 'violation'),
        incomplete: pack(results.incomplete, 'incomplete')
      }});
    }})
    .catch(function(err) {{ return JSON.stringify({{error: String(err)}}); }});
}})()
"""


def htmlcs_script(standard: str = "WCAG2AA") -> str:
    """HTML_CodeSniffer, which reports through a callback rather than a
    promise — hence the collector array."""
    return f"""
(function() {{
  {_read(HTMLCS_PATH)}
  // The name an element gets from its own attributes. HTML_CodeSniffer's
  // H30.2 reads only a link's content, so a gallery link named by
  // `aria-label` was reported as having no name at all.
  function __xaAttributeName(el) {{
    if (!el || !el.getAttribute) return '';
    var own = (el.getAttribute('aria-label') || '').trim();
    if (own) return own;
    var ids = (el.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean);
    var byId = ids.map(function(id) {{
      var node = document.getElementById(id);
      return node ? (node.textContent || '').trim() : '';
    }}).join(' ').trim();
    if (byId) return byId.slice(0, 200);
    return (el.getAttribute('title') || '').trim().slice(0, 200);
  }}
  // Text a sighted person cannot see right now: clipped to nothing, or a
  // box of a pixel or less - the "visually hidden" pattern of a skip link
  // that appears on focus. Its colours are not what anyone reads; measured
  // unfocused, a municipal site's skip link was 3.79:1 against an ancestor's dark
  // background, and 12.63:1 as it is actually shown.
  function __xaVisuallyHidden(el) {{
    if (!el || !el.getBoundingClientRect) return false;
    var box = el.getBoundingClientRect();
    if (box.width <= 1 || box.height <= 1) return true;
    var style = getComputedStyle(el);
    var clip = (style.clip || '').replace(/\\s+/g, '');
    if (clip === 'rect(0px,0px,0px,0px)' || clip === 'rect(1px,1px,1px,1px)') return true;
    return /inset\\(50%\\)/.test(style.clipPath || '');
  }}
  // Text that is part of a logo. 1.4.3 exempts it by name ("text that is
  // part of a logo or brand name has no contrast requirement"); Coach's
  // wordmark ends in a coloured `.brand-dot`, reported serious on all 36
  // pages. Read from the markup: within three levels, a home link or
  // something whose class or name says brand or logo.
  function __xaInLogo(el) {{
    var node = el, depth = 0;
    while (node && node.getAttribute && depth < 4) {{
      var words = ((node.getAttribute('class') || '') + ' ' +
                   (node.getAttribute('id') || '')).toLowerCase();
      if (/(^|[\\s_-])(brand|logo|wordmark)([\\s_-]|$)/.test(words)) return true;
      if (node.tagName === 'A') {{
        var href = node.getAttribute('href') || '';
        if (href === '/' || href === './' || href === location.origin + '/') return true;
      }}
      node = node.parentElement;
      depth += 1;
    }}
    return false;
  }}
  return new Promise(function(resolve) {{
    var found = [];
    try {{
      HTMLCS.process({json.dumps(standard)}, document, function() {{
        (HTMLCS.getMessages() || []).forEach(function(m) {{
          found.push({{
            type: m.type,
            code: m.code,
            msg: (m.msg || '').slice(0, 600),
            html: (m.element && m.element.outerHTML || '').slice(0, 300),
            tag: (m.element && m.element.tagName || '').toLowerCase(),
            label: __xaAttributeName(m.element),
            hidden: __xaVisuallyHidden(m.element),
            logo: __xaInLogo(m.element)
          }});
        }});
        resolve(JSON.stringify({{messages: found.slice(0, 400)}}));
      }});
    }} catch (err) {{
      resolve(JSON.stringify({{error: String(err)}}));
    }}
  }});
}})()
"""


MEASUREMENT_SCRIPT = """
(function() {
  var nav = (performance.getEntriesByType('navigation') || [])[0] || {};
  var paints = {};
  (performance.getEntriesByType('paint') || []).forEach(function(p) {
    paints[p.name] = Math.round(p.startTime);
  });
  var resources = performance.getEntriesByType('resource') || [];
  var byType = {};
  var totalBytes = 0;
  resources.forEach(function(r) {
    var kind = r.initiatorType || 'other';
    var size = r.transferSize || r.encodedBodySize || 0;
    byType[kind] = byType[kind] || {count: 0, bytes: 0};
    byType[kind].count += 1;
    byType[kind].bytes += size;
    totalBytes += size;
  });
  var slowest = resources.slice()
    .sort(function(a, b) { return b.duration - a.duration; })
    .slice(0, 5)
    .map(function(r) {
      return {name: String(r.name).slice(0, 160), ms: Math.round(r.duration),
              bytes: r.transferSize || r.encodedBodySize || 0};
    });
  // Buffered observers read entries that happened before this script was
  // injected. Unlike a page-load timer, they retain the browser's actual
  // LCP and layout-shift candidates rather than trying to infer them from
  // markup. Not every embedded Chromium exposes every entry type, so an
  // unavailable metric stays absent instead of becoming a fabricated zero.
  var longTaskMs = 0;
  function observe(type, each) {
    try {
      if (typeof PerformanceObserver !== 'function' ||
          !(PerformanceObserver.supportedEntryTypes || []).includes(type)) return null;
      var observer = new PerformanceObserver(function(list) {
        list.getEntries().forEach(each);
      });
      observer.observe({type: type, buffered: true});
      return observer;
    } catch (e) { return null; }
  }
  var longTaskObserver = observe('longtask', function(entry) {
    longTaskMs += Math.round(entry.duration || 0);
  });
  return new Promise(function(resolve) {
    setTimeout(function() {
      [longTaskObserver].forEach(function(observer) {
        if (observer) observer.disconnect();
      });
      var result = {
        domContentLoaded: Math.round(nav.domContentLoadedEventEnd || 0),
        loadComplete: Math.round(nav.loadEventEnd || 0),
        firstPaint: paints['first-paint'] || 0,
        firstContentfulPaint: paints['first-contentful-paint'] || 0,
        transferBytes: totalBytes,
        requestCount: resources.length,
        byType: byType,
        slowest: slowest,
        domNodes: document.getElementsByTagName('*').length
      };
      // Where the images actually are. The static rule guesses this from
      // DOM order (`perf-image-loading`, "the first three are above the
      // fold"), and the guess is wrong often enough to matter: measured
      // 2026-08-31 over four pages and 188 images, one of the eight images
      // it would have flagged sat 176px down a 900px viewport - being told
      // to lazy-load it is being told to delay the largest paint, which is
      // the opposite of the rule's purpose. Keyed by `src` because that is
      // what the static finding recorded; an image with none cannot be
      // matched and is left as the static pass had it.
      result.imagesAboveFold = [];
      var seenSrc = {};
      var images = document.getElementsByTagName('img');
      for (var i = 0; i < images.length; i++) {
        var rect = images[i].getBoundingClientRect();
        var src = images[i].getAttribute('src') || '';
        if (!src || seenSrc[src]) continue;
        if (rect.top + window.scrollY < window.innerHeight) {
          seenSrc[src] = true;
          result.imagesAboveFold.push(src.slice(0, 500));
        }
      }
      // XANALYZE_VITALS_SNAPSHOT
      // A supported observer reporting no entries is a real zero. An engine
      // that has no long-task observer exposes no metric at all, so it cannot
      // be mistaken for an idle page.
      if (longTaskObserver) result.longTaskMs = longTaskMs;
      resolve(JSON.stringify(result));
    }, 50);
  });
})()
"""

# Early web-vitals collector owns CLS session windows and input percentiles.
from .vitals import SNAPSHOT as _VITALS_SNAPSHOT
MEASUREMENT_SCRIPT = MEASUREMENT_SCRIPT.replace(
    "// XANALYZE_VITALS_SNAPSHOT", _VITALS_SNAPSHOT)


# ------------------------------------------------------------- normalisation

def issues_from_axe(payload: str, source: str, exclude_rules=()) -> list:
    """axe results -> our `Issue`s.

    `incomplete` becomes a finding marked `NEEDS_BROWSER` rather than being
    dropped or promoted: axe puts things there precisely when it cannot
    decide, and that is the same honest state our own rules use.
    """
    data = _load(payload)
    if "error" in data:
        return [Issue(rule_id="axe", severity=MODERATE, category=ACCESSIBILITY,
                      source=source, engine="axe",
                      details={"engine_error": data["error"]})]

    issues = []
    for bucket, entries in (("violation", data.get("violations", [])),
                            ("incomplete", data.get("incomplete", []))):
        for entry in entries:
            if entry.get("id") in exclude_rules:
                continue
            # An `incomplete` is axe saying it could not decide, and it
            # carries the same `impact` as a confirmed failure - so
            # `aria-valid-attr-value` arrived as *critical* on the municipal WordPress
            # site with the message "Unable to determine if aria-controls
            # referenced ID exists". Checked on the live page: all five
            # `aria-controls` targets exist. Weighted as a note, the same way
            # HTML_CodeSniffer's undetermined results are, so an engine's
            # uncertainty never outranks what it actually found.
            severity = (MINOR if bucket == "incomplete"
                        else _AXE_IMPACT.get(entry.get("impact") or "", MODERATE))
            # A rule this axe version brought and nobody has weighed yet is a
            # note until somebody does; see `audit.engine_codes`.
            unverified = not engine_codes.is_known(engine_codes.AXE, entry.get("id", ""))
            if unverified:
                engine_codes.note_unverified(engine_codes.AXE, entry.get("id", ""))
                severity = MINOR
            for node in entry.get("nodes", []):
                measured = _measured_details(entry.get("id"), node)
                issues.append(Issue(
                    rule_id=f"axe:{entry.get('id')}",
                    severity=severity,
                    category=ACCESSIBILITY,
                    selector=node.get("target", ""),
                    snippet=node.get("html", ""),
                    source=source,
                    engine="axe",
                    confidence=(ADVISORY if unverified
                                else NEEDS_BROWSER if bucket == "incomplete" else EXACT),
                    details={
                        "engine": "axe-core",
                        "rule": entry.get("id"),
                        "unverified_engine_code": unverified,
                        "help": entry.get("help", ""),
                        "description": entry.get("description", ""),
                        "why": node.get("failureSummary", ""),
                        "url": entry.get("helpUrl", ""),
                        "tags": entry.get("tags", []),
                        "bucket": bucket,
                        **measured,
                    },
                ))
    return issues


#: Detail names `_measured_details` writes; carried across a deduplication.
_MEASURED_KEYS = ("min_size", "width", "height", "closest_offset",
                  "min_offset", "neighbour", "measure")


def _measured_details(rule: str, node: dict) -> dict:
    """What axe measured for a target, in this tool's own detail names.

    axe's `target-size` check reports the box (`width`, `height`) against
    `minSize`, and `target-offset` the distance to the nearest neighbour
    (`closestOffset` against `minOffset`) with that neighbour as a related
    node. A finding that says "too small" without the number is one nobody
    can check against devtools.
    """
    if rule != "target-size":
        return {}
    data = node.get("data") or {}
    found = {"wcag": ["2.5.8"]}
    for theirs, ours in (("minSize", "min_size"), ("width", "width"),
                         ("height", "height"), ("closestOffset", "closest_offset"),
                         ("minOffset", "min_offset"), ("messageKey", "measure")):
        value = data.get(theirs)
        if isinstance(value, (int, float)) or (isinstance(value, str) and value):
            found[ours] = value
    related = [r for r in node.get("related") or [] if r]
    if related:
        found["neighbour"] = related[0]
    return found


#: HTML_CodeSniffer code fragments that mean "I could not work this out",
#: not "this is wrong". Its contrast check reports both through the same
#: message type, so an element it cannot measure arrived as a *serious*
#: contrast violation.
#:
#: Measured on ten pages of `https://www.gov.uk/`: 60 of 61 `1_4_3` findings
#: were `.Abs` - "this element is absolutely positioned and the background
#: color can not be determined". On ten pages of a municipal WordPress site, 93 of
#: 103. Reporting an engine's own uncertainty as a violation is the same
#: defect this project keeps finding in its own checks, arriving through a
#: vendored one.
_HTMLCS_UNDETERMINED = (".Abs", ".BgImage", ".Alpha", ".BgGradient")

#: HTML_CodeSniffer *warnings* that are a prompt to look, not a defect it
#: measured. Each one fires on every element of a shape, whatever its state:
#:
#: * `.F96` (2.5.3) - "check that the accessible name contains the visible
#:   label". It fired on a skip link whose `aria-label` *did* contain its
#:   visible text, 221 times on a 381-page crawl;
#: * `1_4_10.C32…` - "this element is `position: fixed`, which may require
#:   scrolling in two dimensions": 1011 times, on the page's overlay, close
#:   button and skip link, on a site that reflows without horizontal scroll at
#:   320px;
#: * `.H67.2` - "this image is marked as ignored by assistive technology",
#:   which is what `alt=""` is for;
#: * `.H48`, `.H48.2`, `.H85.2` - "it is recommended that this be a list /
#:   an `optgroup`";
#: * `.H39.3.NoCaption` - "if this table is a data table, consider using a
#:   caption". A suggestion about every table without one, which arrived as
#:   a `moderate exact` finding on each of Coach's data tables.
#:
#: What HTML_CodeSniffer *measured* is untouched: `G18.Fail` carries the
#: contrast ratio, `H30.2` is an image that is the only content of a link and
#: has no text. Those stay at the weight the engine gave them.
_HTMLCS_MANUAL_CHECK = (".F96", "1_4_10.C32", ".H67.2", ".H48", ".H85.2",
                        ".H39.3.NoCaption")

#: Success criteria WCAG 2.2 removed. 4.1.1 Parsing was dropped because the
#: failures it described (duplicate ids, bad nesting) are handled by user
#: agents and assistive technology; a duplicate id still matters where
#: something *references* it, which is what the `duplicate-id` rule is for.
_HTMLCS_OBSOLETE = (".F77",)


def _is_undetermined(code: str) -> bool:
    return any(marker in code for marker in _HTMLCS_UNDETERMINED)


def _is_manual_check(code: str) -> bool:
    return any(marker in code for marker in _HTMLCS_MANUAL_CHECK)


def _is_obsolete(code: str) -> bool:
    return any(marker in code for marker in _HTMLCS_OBSOLETE)


#: HTML_CodeSniffer's "the image is the only content of the link and has no
#: alt". It looks at the link's content only; a link named by `aria-label`,
#: `aria-labelledby` or `title` has an accessible name, and the 93 serious
#: rows a 381-page crawl gave for such gallery links were false. What is left
#: is a person's call - "Open image 1" is a name that describes nothing - so
#: the row stays, at the weight of a note.
_HTMLCS_LINK_IMAGE_NO_ALT = ".H30.2"

_NAMING_ATTRIBUTE = re.compile(
    r"""\b(aria-label|aria-labelledby|title)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""",
    re.IGNORECASE)


def _attribute_name(message: dict) -> str:
    """The name the flagged element has from its own attributes.

    The collector reports it as `label`; a payload from before it did (a
    cached run) only has the opening tag in `html`, which carries the same
    attributes - `aria-labelledby` there counts as a name whose text this
    side cannot read.
    """
    label = (message.get("label") or "").strip()
    if label:
        return label
    opening = (message.get("html") or "").split(">", 1)[0]
    for match in _NAMING_ATTRIBUTE.finditer(opening):
        value = next((g for g in match.groups()[1:] if g is not None), "").strip()
        if value:
            return value
    return ""


def issues_from_htmlcs(payload: str, source: str) -> list:
    data = _load(payload)
    if "error" in data:
        return [Issue(rule_id="htmlcs", severity=MODERATE, category=ACCESSIBILITY,
                      source=source, engine="htmlcs",
                      details={"engine_error": data["error"]})]
    issues = []
    for message in data.get("messages", []):
        severity = _HTMLCS_TYPE.get(message.get("type"))
        if severity is None:
            continue  # Notice: a manual-check prompt, not a finding
        code = message.get("code", "")
        undetermined = _is_undetermined(code)
        manual = _is_manual_check(code)
        obsolete = _is_obsolete(code)
        named_by = (_attribute_name(message)
                    if _HTMLCS_LINK_IMAGE_NO_ALT in code else "")
        manual = manual or bool(named_by)
        # 1.4.3 is about text as it is shown. A visually hidden element is
        # shown only in another state (a skip link on focus), and this pass
        # did not see that state - a question for a person, not a ratio.
        hidden_text = bool(message.get("hidden")) and "1_4_3" in code
        # Logotypes are exempt from 1.4.3 by the criterion's own wording;
        # whether this is one is a person's call, so a note, not silence.
        logo_text = bool(message.get("logo")) and "1_4_3" in code
        manual = manual or hidden_text or logo_text
        # A code this HTML_CodeSniffer version brought, not yet weighed by a
        # person: a note until it is; see `audit.engine_codes`.
        unverified = not engine_codes.is_known(engine_codes.HTMLCS, code)
        if unverified:
            engine_codes.note_unverified(engine_codes.HTMLCS, code)
        manual = manual or unverified
        issues.append(Issue(
            rule_id=f"htmlcs:{_short_code(code)}",
            # An unmeasurable element is not a failing one. Kept - the
            # element is worth a human's eye - but at the weight of a note
            # and flagged as needing a browser, so it cannot crowd out the
            # violations the same rule really did find. A prompt to check by
            # hand and a criterion WCAG 2.2 no longer has get the same
            # weight, for the same reason.
            severity=MINOR if (undetermined or manual or obsolete) else severity,
            # `advisory`, not `needs-browser`: a browser has already looked,
            # and what is left is a person's call.
            confidence=(NEEDS_BROWSER if undetermined
                        else ADVISORY if (manual or obsolete) else EXACT),
            category=ACCESSIBILITY,
            snippet=message.get("html", ""),
            source=source,
            engine="htmlcs",
            details={"engine": "HTML_CodeSniffer", "code": code,
                     "undetermined": undetermined,
                     "manual_check": manual, "obsolete_criterion": obsolete,
                     "accessible_name_from_attributes": named_by,
                     "visually_hidden": hidden_text,
                     "logo": logo_text,
                     "unverified_engine_code": unverified,
                     "why": message.get("msg", ""), "element": message.get("tag", "")},
        ))
    return issues


def issues_from_measurements(payload: str, source: str, budgets=None) -> list:
    """Measurements become findings only where they cross a budget.

    The numbers themselves are kept on the result for the report; turning
    every timing into a "problem" would produce a page of rows that say
    nothing is wrong.
    """
    data = _load(payload)
    if not data or "error" in data:
        return []
    budgets = budgets or DEFAULT_BUDGETS

    issues = []
    for key, (limit, severity, rule) in budgets.items():
        value = data.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= limit:
            continue
        issues.append(Issue(
            rule_id=rule, severity=severity, category=PERFORMANCE,
            source=source, engine="browser",
            details={"metric": key, "value": value, "budget": limit,
                     "measurements": data},
        ))
    return issues


#: metric -> (budget, severity, rule id). Chosen to match the thresholds the
#: field generally treats as "good": 1.8s first contentful paint, ~1.6 MB of
#: transfer, 50 requests, 1500 DOM nodes.
DEFAULT_BUDGETS = {
    "firstContentfulPaint": (1800, SERIOUS, "perf-first-paint"),
    "largestContentfulPaint": (2500, SERIOUS, "perf-largest-contentful-paint"),
    "cumulativeLayoutShift": (0.1, MODERATE, "perf-layout-shift-browser"),
    "interactionToNextPaint": (200, SERIOUS, "perf-interaction-to-next-paint"),
    "loadComplete": (5000, MODERATE, "perf-load-time"),
    "transferBytes": (1_600_000, MODERATE, "perf-page-weight"),
    "requestCount": (50, MINOR, "perf-request-count"),
    "domNodes": (1500, MODERATE, "perf-dom-size"),
    "longTaskMs": (200, MODERATE, "perf-long-tasks"),
}


def merge_into_document(document, page_audit) -> None:
    """Fold one page's browser findings into its static ones. One owner.

    Both the CLI's browser pass (`cli_impl/auditpass._run_browser_pass`) and
    the window (`ui/main_window._run_browser_pass`) did this with their own
    copy of the two calls, and the copies drifted: only the CLI settled
    `perf-image-loading`, so the same page audited from the window kept a
    finding the browser had already disproved. Two surfaces, two answers, for
    a reason nobody chose.

    The order matters and is the reason this is a function: a static finding
    the browser disproved must not reach `deduplicate`, or it would be
    corroborated by a real finding and reported alongside it.

    Geometry comes from the widest pass that produced numbers (see
    `responsive.merge`): desktop is the DOM the reader is most likely to have
    open, and it is the same choice made for the selector a merged row keeps.
    """
    settled = settle_image_loading(
        list(document.issues), getattr(page_audit, "measurements", None) or {})
    document.issues = deduplicate(
        settled + list(page_audit.issues),
        markup=getattr(page_audit, "html", "") or "")


def merge_page_audit(result, document, page_audit) -> bool:
    """Record browser failures and merge a complete answer in one place.

    Returns true when findings were merged. A page failure leaves the static
    findings intact but is recorded as partial evidence on the whole result;
    an engine failure records the same fact while preserving the engines that
    did answer.
    """
    errors = getattr(result, "browser_errors", None)
    if errors is None:
        errors = []
        result.browser_errors = errors
    if page_audit.error:
        item = {"source": document.source, "engine": "browser",
                "error": str(page_audit.error)}
        if item not in errors:
            errors.append(item)
        return False
    for engine, message in page_audit.engine_errors.items():
        item = {"source": document.source, "engine": str(engine),
                "error": str(message)}
        if item not in errors:
            errors.append(item)
    measurements = getattr(page_audit, "measurements", None) or {}
    if measurements:
        result.coverage.setdefault("performance", []).append({
            "source": document.source, "measurements": measurements})
    merge_into_document(document, page_audit)
    return True


def settle_image_loading(issues: list, measurements: dict) -> list:
    """Drop `perf-image-loading` findings the browser shows to be visible.

    `perf-image-loading` is a static rule guessing at page geometry: it
    assumes the first three `<img>` in DOM order are above the fold and every
    later one is not. Measured 2026-08-31 at 1280x900 over four pages and 188
    images: of the eight images the rule would have flagged, **one** sat 176px
    down the page (an icon on `en.wikipedia.org/wiki/Rome`). Telling an author
    to defer an image the visitor can already see delays the largest paint,
    which is the opposite of what the rule is for - and the rule's own comment
    says so.

    So the rule now declares `NEEDS_BROWSER` and this settles it, which is
    what that value means. Findings are matched by `details["src"]`, the one
    thing both sides recorded; an `<img>` that loads from `srcset` or
    `data-src` alone has no `src` to match and is left as the static pass had
    it, reported rather than silently dropped.
    """
    above = measurements.get("imagesAboveFold")
    if not isinstance(above, list) or not above:
        return list(issues)
    visible = {str(src) for src in above if src}
    return [issue for issue in issues
            if not (issue.rule_id == "perf-image-loading"
                    and str((issue.details or {}).get("src", "")) in visible)]


def deduplicate(issues: list, markup: str = "") -> list:
    """Collapse the same problem found by more than one engine.

    Two engines on the same element and the same underlying rule is one
    problem, and showing it twice teaches people that the report is padded.
    The kept copy records who else found it, which is useful signal: a
    finding both engines agree on is not one to argue with.

    Matching cannot go through the selector, which is the obvious key and the
    wrong one: our own rules emit a full `html:nth-of-type(1) > body... > img`
    path, axe emits `img`, and HTML_CodeSniffer emits nothing at all. Three
    spellings of one element look like three elements, and the collapse
    silently never happens. So elements are compared by what they *are* —
    tag name plus attributes, recovered from the snippet each engine carries
    — and the selector is only a fallback for findings that have no element
    (a missing canonical link is about the page, not about a node).

    Cross-engine only. Within one engine the selectors are consistent and two
    findings on `<button></button>` really are two buttons; merging those
    would hide a genuine second problem, which is worse than a duplicate row.

    An element key that several elements share is not an identity, and the
    document is what says so. Two empty `<button></button>` tags have the same
    name and the same (absent) attributes, so the key alone made them one
    element: the finding on the second button attached to the first as "also
    found by axe" and vanished from the list - a real missing accessible name,
    dropped. Nothing local can pair them either, because the engines that
    repeat an element are the ones that emit no selector.

    So `markup` decides. When the document holds exactly one element with that
    key, a repeat really is a repeat and collapses as before (HTML_CodeSniffer
    emits two messages under one criterion for the same heading). When it
    holds several, no finding about them is merged with any other - at worst a
    duplicate row, which is the trade this function already makes in the other
    direction. Without `markup` nothing changes: the key still merges across
    engines, because there is no evidence to say otherwise.
    """
    from .base import SEVERITY_ORDER

    #: How many elements of each key the document actually contains. Empty
    #: when the caller had no document to give.
    element_counts = _element_counts(markup)

    kept: dict = {}
    order = []
    #: (source, family, element key) -> the issue already kept for it, used
    #: only to match findings that came from a *different* engine.
    by_element: dict = {}
    unpaired = 0

    for issue in issues:
        family = _rule_family(issue.rule_id)
        element = _element_key(issue)
        shared = element_counts.get(element, 0) > 1

        existing = None
        if element and not shared:
            candidate = by_element.get((issue.source, family, element))
            if candidate is not None and candidate.engine != issue.engine:
                existing = candidate

        if family in _DOCUMENT_FAMILIES:
            signature = (issue.source, family)
        elif shared and not issue.selector:
            # Several such elements exist and this finding does not say which.
            # Given to nothing else to merge with, rather than to the wrong one.
            unpaired += 1
            signature = (issue.source, family, issue.snippet, unpaired)
        else:
            signature = (issue.source, family, issue.selector or issue.snippet)
        if existing is None:
            existing = kept.get(signature)

        if existing is None:
            kept[signature] = issue
            order.append(signature)
            if element and not shared:
                by_element.setdefault((issue.source, family, element), issue)
            continue

        # Only a *different* engine is corroboration. One engine reporting the
        # same element twice (HTML_CodeSniffer does this under one criterion)
        # still collapses to one row, but writing "also found by htmlcs" on an
        # htmlcs finding would read as nonsense to whoever has to act on it.
        if issue.engine != existing.engine:
            confirmations = set(existing.details.get("also_found_by", []))
            confirmations.add(issue.engine)
            existing.details["also_found_by"] = sorted(confirmations)
            # How many independent engines said it. Recorded rather than left
            # to be counted from the list, because this is the number a
            # reader triages on: three engines looking at one page and two of
            # them agreeing is the strongest evidence a static pass can
            # produce.
            existing.details["agreement"] = 1 + len(confirmations)
            # And the strongest certainty among them wins. An engine that
            # positively confirmed the problem has settled it; another
            # engine's inability to decide does not un-settle it. Two
            # engines that *both* could not decide stay undecided - two
            # uncertainties are not a certainty, which is the direction this
            # must not be wrong in.
            existing.confidence = _stronger(existing.confidence, issue.confidence)
            # A measurement settles what a static reading could only guess:
            # the box axe measured goes with the row that is kept, so a
            # static `viewport-touch-target` confirmed in the browser still
            # says how big the target really is.
            for key in _MEASURED_KEYS:
                if key in issue.details and key not in existing.details:
                    existing.details[key] = issue.details[key]
        # Keep the more severe reading of the same problem.
        if SEVERITY_ORDER.index(issue.severity) < SEVERITY_ORDER.index(existing.severity):
            existing.severity = issue.severity
    return [kept[signature] for signature in order]


def _stronger(left: str, right: str) -> str:
    """The more certain of two confidences."""
    from .base import CONFIDENCE_ORDER

    def rank(value: str) -> int:
        return (CONFIDENCE_ORDER.index(value)
                if value in CONFIDENCE_ORDER else len(CONFIDENCE_ORDER))

    return left if rank(left) >= rank(right) else right


#: The opening tag of a snippet: name, then everything up to the `>`.
_OPEN_TAG = re.compile(r"<\s*([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^>]*?)?)/?\s*>")
_ATTRIBUTE = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)")


def _element_counts(markup: str) -> dict:
    """How many elements of each `_element_key` the document contains.

    Parsed once per document. The key is built the same way as from a snippet,
    so the two are comparable: that is the whole point of computing it here
    rather than trusting the findings to describe the page.
    """
    if not markup:
        return {}
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(markup, "html.parser")
    except Exception:  # noqa: BLE001 - unparseable markup just means no evidence
        return {}
    counts: dict = {}
    for tag in soup.find_all(True):
        key = _key_of_tag(tag)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _key_of_tag(tag) -> str:
    attributes = sorted(
        (name.lower(),
         " ".join(value) if isinstance(value, list) else str(value))
        for name, value in (tag.attrs or {}).items()
    )
    rendered = ";".join(f"{name}={value}" for name, value in attributes)
    return f"{tag.name.lower()}|{rendered}"


def _element_key(issue) -> str:
    """A spelling-independent identity for the element a finding is about.

    Built from the snippet rather than the selector because every engine
    serialises the element it found, and none of them agree on how to address
    it. `<img src="a.png"/>` and `<img src="a.png">` are the same image, and
    this is what makes them compare equal.
    """
    match = _OPEN_TAG.search(issue.snippet or "")
    if not match:
        return ""
    tag = match.group(1).lower()
    attributes = sorted(
        (name.lower(), value.strip("\"'"))
        for name, value in _ATTRIBUTE.findall(match.group(2) or "")
    )
    rendered = ";".join(f"{name}={value}" for name, value in attributes)
    return f"{tag}|{rendered}"


#: Rules that mean the same thing across engines, so the deduplicator can
#: tell that `image-alt`, `axe:image-alt` and an HTMLCS 1_1_1 message about a
#: missing alt are one finding rather than three.
_RULE_FAMILIES = {
    # alt text
    "image-alt": "alt", "image-alt-filename": "alt",
    "axe:image-alt": "alt", "htmlcs:1_1_1": "alt",
    # accessible name. The state pass answers this question again, after
    # scripts have run, so the two must collapse: a field labelled by
    # JavaScript is a static finding the browser disproves, and one the
    # markup labelled and a script detached is the opposite - either way it
    # is one problem with one element, not two rows.
    "control-name": "name", "state:form-field-unnamed": "name",
    "axe:button-name": "name", "axe:link-name": "name",
    "axe:input-button-name": "name", "axe:aria-input-field-name": "name",
    "axe:label": "name", "htmlcs:4_1_2": "name",
    # language
    "html-lang": "lang",
    "axe:html-has-lang": "lang", "axe:html-lang-valid": "lang",
    # title
    "document-title": "title", "axe:document-title": "title",
    # headings
    "heading-order": "heading-order", "page-has-h1": "heading-order",
    "axe:heading-order": "heading-order", "axe:page-has-heading-one": "heading-order",
    # ids
    "duplicate-id": "id", "aria-reference-broken": "id",
    "axe:duplicate-id": "id", "axe:duplicate-id-active": "id",
    # HTML_CodeSniffer's own duplicate-id message (the 4.1.1 failure F77) is
    # the same element the static rule already named. Without this a page
    # with one repeated sprite id listed it twice, from two engines.
    "htmlcs:4_1_1": "id",
    # contrast
    "contrast-inline": "contrast",
    "axe:color-contrast": "contrast", "htmlcs:1_4_3": "contrast",
    # tables
    "table-headers": "table", "axe:th-has-data-cells": "table",
    # zoom
    "viewport-zoom": "zoom", "axe:meta-viewport": "zoom",
    # tabindex
    "tabindex-positive": "tabindex", "axe:tabindex": "tabindex",
    # link text
    "link-text-vague": "link-text", "axe:link-in-text-block": "link-text",
    # buttons
    "button-type": "button-type",
    # media
    "media-captions": "media", "media-autoplay": "media",
    "axe:video-caption": "media", "axe:audio-caption": "media",
    # bypassing repeated navigation. Three engines answer this question and
    # none of them was mapped, so a page with no skip link was reported three
    # times, by three names, with nothing saying they agreed - on the one
    # finding where agreement is the whole signal.
    "skip-link": "skip", "state:no-skip-link": "skip",
    "axe:bypass": "skip", "htmlcs:2_4_1": "skip",
    # target size (2.5.8). The static rule reads a size from `style` and
    # cannot be sure; axe measured the box. One element, one row.
    "viewport-touch-target": "target-size", "axe:target-size": "target-size",
}

#: Families whose finding is about the document, not about a node in it.
#: For these the element and the selector are not identity - "this page has
#: no way to bypass the navigation" is one fact per page however each engine
#: chooses to point at it, and matching on the pointer is what kept three
#: spellings of one fact apart.
_DOCUMENT_FAMILIES = frozenset(("skip",))


def _rule_family(rule_id: str) -> str:
    return _RULE_FAMILIES.get(rule_id, rule_id)


def _short_code(code: str) -> str:
    """HTML_CodeSniffer codes are long dotted paths; the middle part is the
    success criterion, which is the useful half."""
    parts = (code or "").split(".")
    for part in parts:
        if part and part[0].isdigit():
            return part
    return parts[-1] if parts else code


def _load(payload) -> dict:
    if isinstance(payload, dict):
        return payload
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except (TypeError, ValueError):
        return {"error": "engine returned a non-JSON result"}
