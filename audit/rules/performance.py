"""Performance rules that a static pass can honestly make.

The split matters here more than anywhere else in this package. Real
performance is a measurement — how long the page took, on what connection,
on what hardware — and no amount of reading markup produces a number. What
markup *does* answer is the question underneath most slow pages: **what did
the browser have to do before it could show anything?**

So these rules report *causes*, never times, and never a score. A page with
six render-blocking scripts in the head is slow for a reason that is visible
in the HTML; whether it takes 1.2s or 6s depends on the network, and the
browser pass (`audit/browser.py`) is what supplies that.

Anything claiming to be a measurement is marked `NEEDS_BROWSER`, so a
report never presents an inference as a reading.
"""
from __future__ import annotations

import re

from ..base import (
    MINOR, MODERATE, NEEDS_BROWSER, PERFORMANCE, SERIOUS, Issue, Rule,
    RuleRegistry, snippet_of,
)

#: Above this many blocking requests in <head>, first paint is visibly delayed
#: on anything but a fast connection.
BLOCKING_BUDGET = 3
#: Inline blocks past this size are parsed on the main thread before paint.
INLINE_STYLE_BUDGET = 20_000
INLINE_SCRIPT_BUDGET = 20_000

_SIZE_RE = re.compile(r"\d")


class PerformanceRule(Rule):
    category = PERFORMANCE


class RenderBlockingResources(PerformanceRule):
    id = "perf-render-blocking"
    page_level = True
    web_only = True
    severity = SERIOUS

    def check(self, document, context) -> list:
        head = document.find("head")
        if head is None:
            return []

        blocking = []
        for tag in head.find_all("script"):
            if tag.get("src") and not (tag.has_attr("async") or tag.has_attr("defer")
                                       or (tag.get("type") or "") == "module"):
                blocking.append(tag)
        for tag in head.find_all("link"):
            rel = [r.lower() for r in (tag.get("rel") or [])]
            if "stylesheet" not in rel:
                continue
            media = (tag.get("media") or "all").lower()
            if media in ("all", "screen", ""):
                blocking.append(tag)

        if len(blocking) <= BLOCKING_BUDGET:
            return []
        # Reported once for the page, not once per tag: the problem is the
        # total, and eight separate rows would bury it.
        selector, line = context.locate(blocking[0])
        return [Issue(
            rule_id=self.id, severity=self.severity, category=self.category,
            selector=selector, line=line, snippet=snippet_of(blocking[0]),
            source=context.source,
            details={"count": len(blocking), "budget": BLOCKING_BUDGET},
        )]


class SynchronousThirdPartyScripts(PerformanceRule):
    id = "perf-third-party-sync"
    page_level = True
    severity = SERIOUS

    def check(self, document, context) -> list:
        issues = []
        page_host = _host_of(context.source)
        for tag in document.find_all("script", src=True):
            if tag.has_attr("async") or tag.has_attr("defer"):
                continue
            # `nomodule` is the browser's own opt-out: a browser that
            # understands modules ignores the tag entirely and never fetches
            # it. Every one of these on `wix.com` was a core-js or
            # focus-within polyfill that no current browser downloads, and
            # calling them render-blocking is describing a browser nobody
            # has used for years.
            if tag.has_attr("nomodule"):
                continue
            src = tag.get("src") or ""
            host = _host_of(src)
            if not host or (page_host and host == page_host):
                continue
            # A third-party script loaded synchronously hands a stranger the
            # power to stop the page rendering — if their server is slow, the
            # site is slow, and nothing on it is under this team's control.
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, category=self.category,
                selector=selector, line=line, snippet=snippet_of(tag),
                source=context.source, details={"host": host, "src": src[:120]},
                fix_snippet=_with_defer(tag),
            ))
        return issues


class OversizedInlineBlocks(PerformanceRule):
    id = "perf-large-inline"
    severity = MODERATE

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all(("style", "script")):
            if tag.name == "script" and tag.get("src"):
                continue
            body = tag.string or ""
            budget = INLINE_STYLE_BUDGET if tag.name == "style" else INLINE_SCRIPT_BUDGET
            if len(body) <= budget:
                continue
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, category=self.category,
                selector=selector, line=line, snippet=f"<{tag.name}>…</{tag.name}>",
                source=context.source,
                details={"element": tag.name, "bytes": len(body), "budget": budget},
            ))
        return issues


class ImagesWithoutLazyLoading(PerformanceRule):
    id = "perf-image-loading"
    severity = MINOR
    #: DOM order is a guess at geometry, and the browser pass is what settles
    #: it (`browser.settle_image_loading`). Measured 2026-08-31 at 1280x900
    #: over four pages and 188 images: one of the eight images this rule would
    #: have flagged sat 176px down the page. Recommending `loading="lazy"` for
    #: an image the visitor can already see delays the largest paint, which is
    #: the opposite of the point - so the finding is a candidate until a
    #: browser has looked, not a fact.
    confidence = NEEDS_BROWSER

    #: The first few images are usually above the fold, where lazy loading
    #: makes things *worse* — it delays the largest paint. Only images past
    #: this position are worth deferring. A guess, and named as one: the fold
    #: is a rendered position and this file only has markup.
    ABOVE_THE_FOLD = 3

    def check(self, document, context) -> list:
        images = document.find_all("img")
        if len(images) <= self.ABOVE_THE_FOLD:
            return []
        issues = []
        for tag in images[self.ABOVE_THE_FOLD:]:
            loading = (tag.get("loading") or "").lower()
            if loading == "lazy":
                continue
            # `eager` written out is a decision, not an omission. The default
            # is eager, so an author who typed it meant it - the same reason
            # `fetchpriority="high"` is left alone below.
            if loading == "eager":
                continue
            # An `<img>` with no address loads nothing, so there is nothing
            # to defer. A template's placeholder, or a `src` a framework
            # fills in later.
            if not (tag.get("src") or tag.get("data-src") or tag.get("srcset")):
                continue
            # `fetchpriority="high"` is the author saying this image is the
            # one the page is judged on. Telling them to defer it is telling
            # them to undo a decision they made deliberately, and the two
            # attributes contradict each other by design.
            if (tag.get("fetchpriority") or "").lower() == "high":
                continue
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, category=self.category,
                selector=selector, line=line, snippet=snippet_of(tag),
                source=context.source, confidence=self.confidence,
                # The whole address up to the length the browser keeps
                # (`browser.IMAGE_SRC_LIMIT`): it is what the browser pass
                # matches on, and a shorter cut never matched a long URL.
                details={"src": (tag.get("src") or "")[:500]},
                fix_snippet=_with_attribute(tag, "loading", "lazy"),
            ))
        return issues


class FontsWithoutDisplaySwap(PerformanceRule):
    id = "perf-font-display"
    page_level = True
    web_only = True
    severity = MODERATE
    confidence = NEEDS_BROWSER

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all("link", href=True):
            rel = [r.lower() for r in (tag.get("rel") or [])]
            href = tag.get("href") or ""
            if "stylesheet" not in rel or "font" not in href.lower():
                continue
            if "display=" in href.lower():
                continue
            # Without a display strategy the browser hides the text until the
            # font arrives. On a slow connection the page is blank of words
            # while being technically "loaded".
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, category=self.category,
                selector=selector, line=line, snippet=snippet_of(tag),
                source=context.source, confidence=self.confidence,
                details={"href": href[:120]},
            ))
        for tag in document.find_all("style"):
            body = tag.string or ""
            if "@font-face" in body and "font-display" not in body:
                selector, line = context.locate(tag)
                issues.append(Issue(
                    rule_id=self.id, severity=self.severity, category=self.category,
                    selector=selector, line=line, snippet="<style>@font-face…</style>",
                    source=context.source, confidence=self.confidence,
                    details={"href": "inline @font-face"},
                ))
        return issues


class MissingResourceHints(PerformanceRule):
    id = "perf-preconnect"
    page_level = True
    web_only = True
    severity = MINOR

    def check(self, document, context) -> list:
        head = document.find("head")
        if head is None:
            return []
        page_host = _host_of(context.source)
        hinted = set()
        for tag in head.find_all("link"):
            rel = [r.lower() for r in (tag.get("rel") or [])]
            if "preconnect" in rel or "dns-prefetch" in rel:
                hinted.add(_host_of(tag.get("href") or ""))

        origins = set()
        for tag in head.find_all(("script", "link")):
            url = tag.get("src") or tag.get("href") or ""
            host = _host_of(url)
            if host and host != page_host:
                origins.add(host)

        missing = sorted(origins - hinted)
        if not missing:
            return []
        return [Issue(
            rule_id=self.id, severity=self.severity, category=self.category,
            source=context.source, snippet="<head>…</head>",
            details={"hosts": missing[:6], "count": len(missing)},
            fix_snippet=f'<link rel="preconnect" href="https://{missing[0]}">',
        )]


class DeprecatedSizeAttributes(PerformanceRule):
    """Layout stability: an image with no reserved space pushes the page
    around when it finally loads."""
    id = "perf-layout-shift"
    severity = MODERATE
    confidence = NEEDS_BROWSER
    #: Whether the space is reserved is a stylesheet's answer, not the tag's:
    #: `.preview-iframe` may well set `aspect-ratio`, and a fragment carries
    #: no stylesheet to read. Exactly the reasoning that already excuses
    #: `seo-image-dimensions` on a fragment; this rule wanted it too and
    #: never got it, because `.tsx` was skipped before it could show up.
    needs_external_css = True

    def check(self, document, context) -> list:
        issues = []
        for tag in document.find_all(("img", "iframe", "video")):
            style = (tag.get("style") or "").lower()
            has_size = (_SIZE_RE.search(tag.get("width") or "")
                        and _SIZE_RE.search(tag.get("height") or ""))
            if has_size or "aspect-ratio" in style:
                continue
            if tag.name == "img" and (tag.get("loading") or "").lower() != "lazy":
                continue  # eager above-the-fold images are covered by SEO's rule
            selector, line = context.locate(tag)
            issues.append(Issue(
                rule_id=self.id, severity=self.severity, category=self.category,
                selector=selector, line=line, snippet=snippet_of(tag),
                source=context.source, confidence=self.confidence,
                details={"element": tag.name},
            ))
        return issues


# ------------------------------------------------------------------ helpers

def _host_of(url: str) -> str:
    match = re.match(r"^(?:https?:)?//([^/?#]+)", (url or "").strip())
    return match.group(1).lower() if match else ""


def _with_attribute(tag, name: str, value: str) -> str:
    attributes = dict(tag.attrs)
    attributes[name] = value
    parts = []
    for key, val in attributes.items():
        if isinstance(val, list):
            val = " ".join(val)
        parts.append(f'{key}="{val}"')
    return f"<{tag.name} " + " ".join(parts) + ">"


def _with_defer(tag) -> str:
    parts = []
    for key, val in tag.attrs.items():
        if isinstance(val, list):
            val = " ".join(val)
        parts.append(f'{key}="{val}"')
    return f"<{tag.name} " + " ".join(parts) + " defer>"


for _rule in (RenderBlockingResources, SynchronousThirdPartyScripts,
              OversizedInlineBlocks, ImagesWithoutLazyLoading,
              FontsWithoutDisplaySwap, MissingResourceHints,
              DeprecatedSizeAttributes):
    RuleRegistry.register(_rule)
