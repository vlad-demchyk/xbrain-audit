"""Checking the page in the states a person actually puts it in.

Everything else in this package looks at one snapshot. But most of what
makes a page unusable only exists in a state: the focus ring that turns out
to be invisible, the menu that opens but cannot be closed with a key, the
dialog that lets focus wander out behind it, the content that only appears
on hover and therefore never appears to a keyboard at all.

This is the largest remaining source of automatable findings that does not
involve a model. It is also the part that genuinely needs a browser: every
check below is "do something, then look", and there is nothing to do to a
static string.

The script runs entirely inside the page, in one pass, and restores what it
touched. It deliberately does **not** click anything: a click can submit a
form, navigate away, or fire an analytics event on a real site. Focus and
keyboard events are safe in a way that clicks are not, so the checks are
built from those.
"""
from __future__ import annotations

import json

from .base import (
    ACCESSIBILITY, MINOR, MODERATE, NEEDS_BROWSER, SERIOUS, Issue,
)

#: What each check reports, and how badly. Keyboard traps come first because
#: a trapped keyboard user cannot leave the page at all.
STATE_RULES = {
    "keyboard-trap": SERIOUS,
    "focus-not-visible": SERIOUS,
    "focus-order-mismatch": MODERATE,
    "hover-only-content": MODERATE,
    "no-skip-link": MODERATE,
    "focus-outside-viewport": MODERATE,
    "modal-focus-not-contained": SERIOUS,
    # --- what a focus ring is drawn against ---------------------------------
    # `focus-not-visible` asks whether anything changes on focus. These two
    # ask the questions it cannot: whether the thing that changed can be seen
    # against what is behind it, and whether anything the author built hides
    # the focused element altogether. Both were found by hand on a live site
    # with a sticky header and had passed every automated engine.
    "focus-indicator-low-contrast": SERIOUS,
    "focus-obscured": SERIOUS,
    # Not a defect of the page: the page never had focus, so the two focus
    # checks above and `focus-not-visible` had nothing to read. Said once per
    # page instead of being silent, because "no focus problems found" and "focus
    # could not be looked at" are different sentences.
    "focus-not-measured": MINOR,
    # --- the form journey ---------------------------------------------------
    # A form is the part of a page where a mistake costs the visitor the
    # whole task, and every check here reads the state the page is *in*: the
    # accessible name after scripts have run, the browser's own verdict on
    # what has been typed, the error text that is on screen right now.
    "form-field-unnamed": SERIOUS,
    "form-placeholder-as-label": MODERATE,
    "form-invalid-not-announced": MODERATE,
    "form-error-not-associated": SERIOUS,
}

#: The success criteria each state check contributes to, as the registry rules
#: declare theirs (`Rule.wcag`). "Contributes to", never "proves": a page can
#: pass every check here and still fail the criterion. Without this the report
#: printed a WCAG line for a static rule and none for the browser's own
#: verdict on the same criterion, because `_wcag_for` only knew the registry.
STATE_WCAG = {
    "keyboard-trap": ("2.1.2",),
    "focus-not-visible": ("2.4.7",),
    "focus-order-mismatch": ("2.4.3",),
    "hover-only-content": ("1.4.13",),
    "no-skip-link": ("2.4.1",),
    "focus-outside-viewport": ("2.4.7",),
    "modal-focus-not-contained": ("2.4.3",),
    "focus-indicator-low-contrast": ("2.4.7", "1.4.11"),
    "focus-obscured": ("2.4.11",),
    "focus-not-measured": ("2.4.7",),
    "form-field-unnamed": ("4.1.2", "3.3.2"),
    "form-placeholder-as-label": ("3.3.2",),
    "form-invalid-not-announced": ("3.3.1",),
    "form-error-not-associated": ("3.3.1", "1.3.1"),
}

# A raw string: everything below is JavaScript, and its backslashes belong to
# the browser's regexes (`/\s+/`) and to its own escaping (`\\"`). Read as
# Python escapes they are a `SyntaxWarning` on 3.12+ and an error later, and
# `\s` in a Python string is not `\s` in the regex the browser receives.
STATE_SCRIPT = r"""
(function() {
  var FOCUSABLE = 'a[href],button,input,select,textarea,summary,[tabindex]';
  var findings = [];
  var active = document.activeElement;
  var scrollX = window.scrollX, scrollY = window.scrollY;

  function selectorFor(el) {
    var parts = [];
    while (el && el.nodeType === 1 && parts.length < 6) {
      var name = el.tagName.toLowerCase();
      if (el.id) { parts.unshift(name + '#' + el.id); break; }
      var parent = el.parentElement;
      if (parent) {
        var same = Array.prototype.filter.call(parent.children, function(c) {
          return c.tagName === el.tagName;
        });
        if (same.length > 1) name += ':nth-of-type(' + (same.indexOf(el) + 1) + ')';
      }
      parts.unshift(name);
      el = el.parentElement;
    }
    return parts.join(' > ');
  }

  function record(rule, el, extra) {
    var item = {rule: rule, selector: el ? selectorFor(el) : '',
                html: el ? (el.outerHTML || '').slice(0, 200) : '',
                tag: el ? el.tagName.toLowerCase() : ''};
    for (var k in (extra || {})) item[k] = extra[k];
    findings.push(item);
    return item;
  }

  function visible(el) {
    var style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    var rect = el.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0;
  }

  // --- colour helpers, for what a focus ring is drawn against ---------------
  // Computed colours come back as `rgb(r, g, b)` / `rgba(r, g, b, a)`, or as
  // `color(srgb r g b / a)` for the modern syntaxes. Anything else (a `lab()`
  // value, a keyword that survived) is "unknown", and unknown is never
  // reported: a contrast verdict made from a colour this could not read would
  // be the tool inventing a number.
  function parseColor(text) {
    if (!text) return null;
    var m = /^rgba?\(([^)]+)\)$/i.exec(text.trim());
    if (m) {
      var parts = m[1].split(/[\s,\/]+/).filter(Boolean).map(parseFloat);
      if (parts.length < 3 || parts.slice(0, 3).some(isNaN)) return null;
      return {r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1};
    }
    m = /^color\(srgb\s+([^)]+)\)$/i.exec(text.trim());
    if (m) {
      var p = m[1].split(/[\s\/]+/).filter(Boolean).map(parseFloat);
      if (p.length < 3 || p.slice(0, 3).some(isNaN)) return null;
      return {r: p[0] * 255, g: p[1] * 255, b: p[2] * 255, a: p.length > 3 ? p[3] : 1};
    }
    return null;
  }
  function over(top, bottom) {
    var a = top.a + bottom.a * (1 - top.a);
    if (a === 0) return {r: 0, g: 0, b: 0, a: 0};
    return {
      r: (top.r * top.a + bottom.r * bottom.a * (1 - top.a)) / a,
      g: (top.g * top.a + bottom.g * bottom.a * (1 - top.a)) / a,
      b: (top.b * top.a + bottom.b * bottom.a * (1 - top.a)) / a,
      a: a
    };
  }
  function luminance(c) {
    function channel(v) {
      v = v / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    }
    return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
  }
  function contrastOf(a, b) {
    var la = luminance(a), lb = luminance(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  }
  function cssRgb(c) {
    return 'rgb(' + Math.round(c.r) + ', ' + Math.round(c.g) + ', ' + Math.round(c.b) + ')';
  }
  // What is behind an element: its own and its ancestors' backgrounds,
  // composited until something is opaque, the white canvas at the bottom.
  // `null` when an image or gradient is in the way - pixels this cannot
  // sample, and a ratio against a guess is not a measurement.
  function backgroundBehind(el) {
    var layers = [];
    var node = el;
    while (node && node.nodeType === 1) {
      var style = getComputedStyle(node);
      if (style.backgroundImage && style.backgroundImage !== 'none') return null;
      var color = parseColor(style.backgroundColor);
      if (color === null) return null;
      if (color.a > 0) layers.push(color);
      if (color.a >= 1) break;
      node = node.parentElement;
    }
    var result = {r: 255, g: 255, b: 255, a: 1};
    for (var i = layers.length - 1; i >= 0; i--) result = over(layers[i], result);
    return result;
  }
  // Comma-separated `box-shadow` list, split outside the colour's parentheses.
  function splitShadows(text) {
    var out = [], depth = 0, start = 0;
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i);
      if (ch === '(') depth++;
      else if (ch === ')') depth--;
      else if (ch === ',' && depth === 0) { out.push(text.slice(start, i)); start = i + 1; }
    }
    out.push(text.slice(start));
    return out.map(function(s) { return s.trim(); }).filter(Boolean);
  }

  // --- 0. An already-open modal owns focus -------------------------------
  // This observes an existing state only. It does not click an opener or
  // dispatch Escape, because either can submit a form or change a real
  // session. A visible aria-modal dialog with focus still behind it is a
  // concrete failure of the state the visitor is currently in.
  var openModal = Array.prototype.slice.call(
    document.querySelectorAll('[role="dialog"][aria-modal="true"], [role="alertdialog"][aria-modal="true"]')
  ).find(visible);
  if (openModal && (!active || !openModal.contains(active))) {
    record('modal-focus-not-contained', openModal, {});
  }

  var candidates = Array.prototype.slice.call(document.querySelectorAll(FOCUSABLE))
    .filter(function(el) {
      return visible(el) && el.tabIndex >= 0 && !el.disabled;
    })
    .slice(0, 120);   // a bounded pass; huge pages are sampled, not skipped

  // --- 1. Is the focus indicator actually visible? ------------------------
  // A ring that the design removed and never replaced is the single most
  // common keyboard problem, and it is invisible to any static check
  // because `outline: none` usually lives in a stylesheet, not the markup.
  //
  // It is also the check most able to lie, and it did. A document that does
  // not itself have focus never matches `:focus` in Chromium: `el.focus()`
  // sets `activeElement`, no focus rule applies, no computed style changes,
  // and every focusable element on the page reports a missing indicator.
  // Measured on `https://www.gov.uk/` - whose focus state is among the most
  // tested on the web - the pass returned 588 serious findings across ten
  // pages, one for very nearly every element it examined.
  //
  // So the precondition is checked first, and a pass that cannot see focus
  // styles reports *nothing* and says why. A check firing on ~100% of what
  // it looks at is measuring the harness, not the page.
  var canSeeFocus = false;
  if (candidates.length) {
    try { window.focus(); } catch (e) {}
    var probe = candidates[0];
    try { probe.focus({preventScroll: true}); } catch (e) {}
    try {
      canSeeFocus = document.hasFocus() && probe.matches(':focus');
    } catch (e) { canSeeFocus = false; }
  }

  // The ring that exists but cannot be seen. `focus-not-visible` is satisfied
  // by *any* change, and a white outline on a white header is a change: found
  // by hand on a live site, where the only thing marking focus on the search
  // button was an outline of the colour of the page. WCAG asks for 3:1 between
  // the indicator and what is next to it (1.4.11, and 2.4.7 in spirit).
  //
  // Judged only when the indicator is an outline, a ring-shaped shadow or a
  // border: a change of fill or text colour alone is a different measurement
  // (against the unfocused look, not the surroundings), and a soft glow has no
  // single colour to compare. Anything this cannot read is left unreported.
  function checkIndicatorContrast(el, after, beforeBg, gained) {
    var outer = el.parentElement ? backgroundBehind(el.parentElement)
                                 : {r: 255, g: 255, b: 255, a: 1};
    var inner = backgroundBehind(el);
    if (!outer || !inner) return;
    var rings = [];
    var unjudged = false;
    if (gained.outline) {
      // `outline-style: auto` is the browser's own ring: two-tone, drawn to
      // be visible on any background, and its computed `outline-color` is a
      // single colour that says nothing about what is painted. Judging it
      // flagged every link of every page that had never styled its focus -
      // the one case where the answer is known to be fine.
      if (after.outlineStyle === 'auto') return null;
      var outlineColor = parseColor(after.outlineColor);
      if (!outlineColor) return null;
      var offset = parseFloat(after.outlineOffset || '0');
      rings.push({name: 'outline', color: outlineColor, against: offset < 0 ? inner : outer});
    }
    if (gained.shadow) {
      splitShadows(after.boxShadow).forEach(function(shadow) {
        var colorMatch = /(rgba?\([^)]*\)|color\([^)]*\))/.exec(shadow);
        var color = colorMatch ? parseColor(colorMatch[1]) : null;
        if (!color) { unjudged = true; return; }
        var inset = /(^|\s)inset(\s|$)/.test(shadow);
        var numbers = shadow.replace(colorMatch[1], '').replace('inset', '').trim()
          .split(/\s+/).map(parseFloat).filter(function(n) { return !isNaN(n); });
        var x = numbers[0] || 0, y = numbers[1] || 0;
        var blur = numbers[2] || 0, spread = numbers[3] || 0;
        if (spread <= 0 && x === 0 && y === 0 && !inset) {
          // A glow: no edge, so no single colour to hold against the page.
          if (blur > 0) unjudged = true;
          return;
        }
        rings.push({name: 'box-shadow', color: color, against: inset ? inner : outer});
      });
    }
    if (gained.border && parseFloat(after.borderTopWidth || '0') > 0) {
      var borderColor = parseColor(after.borderTopColor);
      if (borderColor) rings.push({name: 'border', color: borderColor, against: outer});
    }
    if (unjudged || !rings.length) return;
    // A fill that changes enough on its own is an indicator too, and a ring
    // that is invisible beside it does not make the control invisible.
    if (gained.background) {
      var afterFill = parseColor(after.backgroundColor), beforeFill = parseColor(beforeBg);
      if (afterFill && beforeFill &&
          contrastOf(over(afterFill, inner), over(beforeFill, inner)) >= 3) return;
    }
    var best = 0, bestRing = null;
    rings.forEach(function(ring) {
      var shown = ring.color.a < 1 ? over(ring.color, ring.against) : ring.color;
      var ratio = contrastOf(shown, ring.against);
      if (ratio > best) { best = ratio; bestRing = ring; }
    });
    if (bestRing && best < 3) {
      // Handed back, not recorded here: `record` snapshots `outerHTML`, and
      // while this runs the element carries the inline `transition: none`
      // that the measurement put on it. A finding quoting that is quoting
      // the tool's own scaffolding, and it would never match the same
      // element found by another engine.
      return {rule: 'focus-indicator-low-contrast', extra: {
        ratio: Math.round(best * 100) / 100, required: 3,
        indicator: bestRing.name, color: cssRgb(bestRing.color),
        background: cssRgb(bestRing.against)}};
    }
    return null;
  }

  candidates.forEach(function(el) {
    // Off-canvas, not below the fold. The third condition used to be
    // `rect.top > innerHeight + scrollY + 2000`, which is a statement about
    // how long the page is: on `https://www.gov.uk/` it reported 151
    // `govuk-footer__link` elements - the ordinary footer - as focusable
    // content outside the viewport. Content further down a page is reached
    // by scrolling, which is what pages do.
    //
    // What the rule is for is the element parked off-screen with
    // `left: -9999px` and left focusable, so a keyboard lands somewhere the
    // eye cannot follow. That is what a negative edge means.
    var rect = el.getBoundingClientRect();
    if (rect.bottom < 0 || rect.right < 0) {
      record('focus-outside-viewport', el, {});
    }
    if (!canSeeFocus) return;
    // A transition makes `getComputedStyle` return the first frame of the
    // animation, which is the unfocused look: the ring a person sees 150ms
    // later is not the ring read here. Switched off for this element for the
    // length of the measurement and put back exactly as it was found.
    var priorTransition = el.style.getPropertyValue('transition');
    var priorPriority = el.style.getPropertyPriority('transition');
    var hadStyleAttribute = el.hasAttribute('style');
    el.style.setProperty('transition', 'none', 'important');
    var pending = null;
    try {
    // Whatever held focus before (the probe, or the previous element) is
    // let go first: the "before" snapshot has to be of an unfocused element,
    // and the first candidate is the probe that detected whether focus is
    // visible at all, which was still focused when it was measured - one
    // false "focus-not-visible" on the first link of every page.
    try {
      var held = document.activeElement;
      if (held && held !== document.body && held.blur) held.blur();
    } catch (e) {}
    var before = getComputedStyle(el);
    var beforeShadow = before.boxShadow, beforeBorder = before.borderColor;
    var beforeOutlineW = before.outlineWidth, beforeOutlineS = before.outlineStyle;
    var beforeBg = before.backgroundColor, beforeColor = before.color;
    // The ring can be drawn on a container: Coach's FAQ draws it on the
    // `<details>` through `:has(summary:focus-visible)`, and the summary
    // itself keeps `outline: none`. Every question was reported as having no
    // visible focus. So the nearest few ancestors are read too, with their
    // transitions held still for the same reason as the element's.
    var ancestors = [], node = el.parentElement;
    while (node && ancestors.length < 3 && node !== document.body && node !== document.documentElement) {
      var kept = {el: node, transition: node.style.getPropertyValue('transition'),
                  priority: node.style.getPropertyPriority('transition'),
                  hadStyle: node.hasAttribute('style')};
      node.style.setProperty('transition', 'none', 'important');
      var cs = getComputedStyle(node);
      kept.look = [cs.outlineStyle, cs.outlineWidth, cs.boxShadow, cs.borderColor].join('|');
      ancestors.push(kept);
      node = node.parentElement;
    }
    try { el.focus({preventScroll: true}); } catch (e) { restoreAncestors(); return; }
    if (document.activeElement !== el) { restoreAncestors(); return; }
    var ancestorRing = ancestors.some(function(kept) {
      var cs = getComputedStyle(kept.el);
      var look = [cs.outlineStyle, cs.outlineWidth, cs.boxShadow, cs.borderColor].join('|');
      if (look === kept.look) return false;
      return (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth || '0') > 0) ||
             cs.boxShadow !== 'none' || cs.borderColor !== kept.look.split('|')[3];
    });
    restoreAncestors();
    function restoreAncestors() {
      ancestors.forEach(function(kept) {
        if (kept.transition) kept.el.style.setProperty('transition', kept.transition, kept.priority);
        else kept.el.style.removeProperty('transition');
        if (!kept.hadStyle && kept.el.getAttribute('style') === '') kept.el.removeAttribute('style');
      });
      ancestors = [];
    }
    var after = getComputedStyle(el);
    var gainedOutline = after.outlineStyle !== 'none' &&
                        parseFloat(after.outlineWidth || '0') > 0 &&
                        (after.outlineStyle !== beforeOutlineS ||
                         after.outlineWidth !== beforeOutlineW);
    var gainedShadow = after.boxShadow !== beforeShadow && after.boxShadow !== 'none';
    var gainedBorder = after.borderColor !== beforeBorder;
    // Background and text colour count too, and leaving them out was the
    // second half of the same defect: GOV.UK's indicator is a yellow
    // background (`#fd0`), not a ring, and 83 rules in its stylesheet set
    // `background` on `:focus`. WCAG asks for a visible change, not for an
    // outline specifically.
    var gainedBackground = after.backgroundColor !== beforeBg;
    var gainedColor = after.color !== beforeColor;
    if (!gainedOutline && !gainedShadow && !gainedBorder &&
        !gainedBackground && !gainedColor) {
      // A ring on a container is a visible change; its contrast is not
      // measured here, which is a question left open rather than a pass.
      if (!ancestorRing) {
        pending = {rule: 'focus-not-visible', extra: {outline: after.outlineStyle}};
      }
    } else {
      pending = checkIndicatorContrast(el, after, beforeBg, {
        outline: gainedOutline, shadow: gainedShadow,
        border: gainedBorder, background: gainedBackground});
    }
    } finally {
      if (priorTransition) el.style.setProperty('transition', priorTransition, priorPriority);
      else el.style.removeProperty('transition');
      // `removeProperty` leaves an empty `style=""` behind, which would be
      // quoted in every finding and match nothing another engine reports.
      if (!hadStyleAttribute && el.getAttribute('style') === '') el.removeAttribute('style');
    }
    if (pending) record(pending.rule, el, pending.extra);
  });

  // --- 1b. Is the focused element hidden by something the page built? ------
  // A sticky header that is 98px tall covers whatever a browser scrolls to the
  // top edge of the window, and Shift+Tab scrolls exactly there. Found by hand
  // on a live site: the breadcrumb's focused link sat at y 4-32px, entirely
  // under the bar, on four of nine pages. WCAG 2.4.11 asks that the element is
  // not *entirely* hidden by author-created content, so that is the line drawn
  // here: five points of the element (centre and four inset corners) all land
  // on something fixed or sticky that is not the element and not its ancestor.
  //
  // The check puts the element at the top edge and then at the bottom edge of
  // the window - where a keyboard moving up or down leaves it - and looks at
  // what is on top. Nothing is clicked; the scroll position is restored at the
  // end like everything else here. Skipped when no fixed or sticky box exists
  // (nothing can cover anything), and while a modal is open (the page behind
  // it is meant to be covered).
  var hasStuck = false;
  if (!openModal) {
    var everything = document.querySelectorAll('body *');
    var scanLimit = Math.min(everything.length, 4000);
    for (var si = 0; si < scanLimit && !hasStuck; si++) {
      var position = getComputedStyle(everything[si]).position;
      if ((position === 'fixed' || position === 'sticky') && visible(everything[si])) {
        hasStuck = true;
      }
    }
  }
  function stuckBox(node) {
    while (node && node.nodeType === 1 && node !== document.body) {
      var position = getComputedStyle(node).position;
      if (position === 'fixed' || position === 'sticky') return node;
      node = node.parentElement;
    }
    return null;
  }
  var obscuredRecords = [], obscuredTotal = 0;
  if (hasStuck) {
    candidates.slice(0, 60).forEach(function(el) {
      ['top', 'bottom'].forEach(function(edge) {
        var box = el.getBoundingClientRect();
        var absoluteTop = box.top + window.scrollY;
        var wanted = edge === 'top' ? absoluteTop
                                    : absoluteTop + box.height - window.innerHeight;
        window.scrollTo(0, Math.max(0, wanted));
        box = el.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) return;
        if (box.bottom <= 0 || box.top >= window.innerHeight) return;
        var covering = null, entirely = true;
        [[0.5, 0.5], [0.1, 0.1], [0.9, 0.1], [0.1, 0.9], [0.9, 0.9]].forEach(function(p) {
          if (!entirely) return;
          var x = box.left + box.width * p[0], y = box.top + box.height * p[1];
          if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight) {
            entirely = false; return;
          }
          var hit = document.elementFromPoint(x, y);
          if (!hit || el.contains(hit) || hit.contains(el)) { entirely = false; return; }
          var fixedBox = stuckBox(hit);
          if (!fixedBox || fixedBox.contains(el)) { entirely = false; return; }
          covering = covering || fixedBox;
        });
        if (entirely && covering) {
          obscuredTotal += 1;
          if (obscuredRecords.length < 5) {
            // Both boxes, as the browser had them at that moment: a finding
            // that could not be reproduced by hand in Coach's lesson editor
            // said only what covered the element, not where either was.
            var cover = covering.getBoundingClientRect();
            var round = function(r) {
              return [Math.round(r.left), Math.round(r.top),
                      Math.round(r.width), Math.round(r.height)];
            };
            obscuredRecords.push(record('focus-obscured', el, {
              edge: edge, coveredBy: selectorFor(covering),
              coverHeight: Math.round(cover.height),
              elementBox: round(box).join(','), coverBox: round(cover).join(','),
              viewport: window.innerWidth + 'x' + window.innerHeight}));
          }
        }
      });
    });
    obscuredRecords.forEach(function(item) { item.count = obscuredTotal; });
  }

  // --- 2. Keyboard traps --------------------------------------------------
  // Anything that swallows Tab without moving focus onwards. Checked by
  // dispatching the key and seeing whether the element cancels it — not by
  // actually tabbing, which the page's own handlers would fight over.
  //
  // An open aria-modal dialog that offers a way out is the exception. Keeping
  // Tab inside it is what the ARIA dialog pattern asks for (2.4.3), not a
  // trap (2.1.2): Coach's welcome tour cycles Tab through its own buttons,
  // closes on Escape and has "Skip", and every header link behind it was
  // reported as a trap because the tour's document-level handler cancels the
  // key. The way out is read, not tried - pressing Escape or a button would
  // change the page, and this pass never acts. A modal with no button, link
  // or close control in it is still a trap, and so is anything when no modal
  // is open.
  var modalExit = openModal && openModal.querySelector(
    'button, a[href], [role="button"], [aria-label*="close" i], [aria-label*="chiudi" i], [aria-label*="закри" i]');
  candidates.forEach(function(el) {
    try { el.focus({preventScroll: true}); } catch (e) { return; }
    if (document.activeElement !== el) return;
    var event = new KeyboardEvent('keydown', {key: 'Tab', code: 'Tab',
                                              bubbles: true, cancelable: true});
    var delivered = el.dispatchEvent(event);
    if (!delivered && !el.matches('input,textarea,select,[contenteditable]')) {
      if (openModal && modalExit) return;
      record('keyboard-trap', el, {});
    }
  });

  // --- 3. Does focus order follow reading order? --------------------------
  // Compared against document order rather than pixel position, because a
  // two-column layout legitimately reads down one column first.
  //
  // Two things are not a jump back up. A move to a column further right
  // starts at the top again, which is how a page with a sidebar after its
  // article reads left to right. And an element inside a sticky or fixed
  // box has a position that depends on the scroll, not on the document:
  // Coach's help pinned "On this page" at the top of the window, and its
  // seven links read as seven jumps up. Both reset the comparison instead.
  function pinned(el) {
    for (var node = el; node && node !== document.body; node = node.parentElement) {
      var position = getComputedStyle(node).position;
      if (position === 'sticky' || position === 'fixed') return true;
    }
    return false;
  }
  var lastTop = -Infinity, prevRight = -Infinity, mismatches = 0, firstMismatch = null;
  candidates.forEach(function(el) {
    if (pinned(el)) return;
    var box = el.getBoundingClientRect();
    var top = box.top + window.scrollY;
    if (top < lastTop - 40) {
      if (box.left >= prevRight - 1) {
        lastTop = top;            // a new column to the right starts here
      } else {
        mismatches += 1;
        if (!firstMismatch) firstMismatch = el;
      }
    }
    lastTop = Math.max(lastTop, top);
    prevRight = box.right;
  });
  if (mismatches > 2 && firstMismatch) {
    record('focus-order-mismatch', firstMismatch, {count: mismatches});
  }

  // --- 4. Content that only exists on hover --------------------------------
  // A submenu that opens on hover and has no focus equivalent is unreachable
  // from a keyboard, and its links are invisible to anyone not using a mouse.
  var hoverOnly = 0, hoverExample = null;
  Array.prototype.slice.call(document.querySelectorAll('[class*="dropdown"],[class*="submenu"],[class*="tooltip"],[class*="popover"]'))
    .slice(0, 40)
    .forEach(function(el) {
      var style = getComputedStyle(el);
      if (style.display !== 'none' && style.visibility !== 'hidden') return;
      var parent = el.parentElement;
      if (!parent) return;
      var opensOnFocus = parent.querySelector(FOCUSABLE) !== null ||
                         parent.getAttribute('aria-expanded') !== null;
      if (!opensOnFocus) {
        hoverOnly += 1;
        if (!hoverExample) hoverExample = el;
      }
    });
  if (hoverExample) record('hover-only-content', hoverExample, {count: hoverOnly});

  // --- 5. The form journey -------------------------------------------------
  // Read-only, like everything else here, and for a sharper reason: this is
  // the one region of a page where *acting* has consequences. Typing into a
  // field fires the page's own handlers - autosave, validation requests,
  // analytics - and submitting is worse still, so nothing below fills,
  // clears, clicks or submits anything. What it does instead is read the
  // live state the browser already maintains:
  //
  //   * the accessible name, computed after scripts have run, which is what
  //     makes this different from the static rule of the same shape - a
  //     field labelled by JavaScript is labelled, and a field the markup
  //     labelled and a script detached is not;
  //   * `el.validity`, the browser's own verdict on what is currently in the
  //     field. The property is read; the method of a similar name is not,
  //     because calling it fires an `invalid` event the page can act on;
  //   * the error text that is on screen at this moment, and whether
  //     anything points a screen reader at it.
  //
  // What is deliberately not here: filling a field to see what a form does
  // with a wrong value. That is the other half of the journey and there is
  // no way to do it on somebody's real page without changing their page.
  var fields = Array.prototype.slice.call(
    document.querySelectorAll('input,select,textarea')
  ).filter(function(el) {
    var type = (el.getAttribute('type') || '').toLowerCase();
    // Hidden inputs have nothing to label, and the three button types are
    // named by their own value rather than by a label.
    if (type === 'hidden' || type === 'submit' || type === 'button' ||
        type === 'reset') return false;
    if (el.disabled) return false;
    if (el.getAttribute('aria-hidden') === 'true') return false;
    return visible(el);
  }).slice(0, 60);

  function labelText(el) {
    var parts = [];
    var wrapping = el.closest ? el.closest('label') : null;
    if (wrapping) parts.push(wrapping.textContent || '');
    var id = el.getAttribute('id');
    if (id) {
      try {
        Array.prototype.forEach.call(
          document.querySelectorAll('label[for="' + id.replace(/"/g, '\\"') + '"]'),
          function(label) { parts.push(label.textContent || ''); });
      } catch (e) { /* an id no selector can express is an id with no label */ }
    }
    return parts.join(' ').replace(/\s+/g, ' ').trim();
  }

  function referencedText(el, attribute) {
    var value = el.getAttribute(attribute) || '';
    var text = '';
    value.split(/\s+/).forEach(function(id) {
      if (!id) return;
      var target = document.getElementById(id);
      if (target) text += ' ' + (target.textContent || '');
    });
    return text.replace(/\s+/g, ' ').trim();
  }

  fields.forEach(function(el) {
    var named = labelText(el) ||
                (el.getAttribute('aria-label') || '').trim() ||
                referencedText(el, 'aria-labelledby') ||
                (el.getAttribute('title') || '').trim();
    var placeholder = (el.getAttribute('placeholder') || '').trim();
    if (!named) {
      // A placeholder is not a label: it is gone the moment somebody types,
      // it is not announced by every screen reader, and it fails contrast
      // far more often than body text does. Reported apart from a field
      // with nothing at all, because the fix is different - one needs a
      // label written, the other needs the words it already has moved.
      record(placeholder ? 'form-placeholder-as-label' : 'form-field-unnamed',
             el, placeholder ? {placeholder: placeholder} : {});
    }

    // The browser's own verdict on what is in the field right now, read as a
    // property. The method that asks the same question fires an `invalid`
    // event on the way out, and hands the page's own code a reason to react.
    var validity = null;
    try { validity = el.validity; } catch (e) { validity = null; }
    if (validity && validity.valid === false &&
        (el.getAttribute('aria-invalid') || '').toLowerCase() !== 'true') {
      record('form-invalid-not-announced', el,
             {reason: validity.valueMissing ? 'value-missing'
                      : (validity.typeMismatch ? 'type-mismatch' : 'constraint')});
    }
  });

  // Error text that is on screen and pointed at by nothing. The static rule
  // asks the mirror-image question - a field marked `aria-invalid` with no
  // description - and neither finds this one: a red sentence under a field,
  // rendered by the page's own validation, that no `aria-describedby` or
  // `aria-errormessage` refers to. A screen reader never reaches it.
  var describedIds = {};
  fields.forEach(function(el) {
    ['aria-describedby', 'aria-errormessage'].forEach(function(attribute) {
      (el.getAttribute(attribute) || '').split(/\s+/).forEach(function(id) {
        if (id) describedIds[id] = true;
      });
    });
  });
  var errorNodes = Array.prototype.slice.call(document.querySelectorAll(
    '[role="alert"],[class*="error"],[class*="invalid"],[id*="error"]'
  )).filter(function(el) {
    if (!visible(el)) return false;
    if (!el.closest || !el.closest('form')) return false;
    var text = (el.textContent || '').trim();
    // A wrapper whose class happens to contain "error" is not a message.
    // Text, and not the whole form's worth of it.
    if (text.length < 3 || text.length > 200) return false;
    return el.querySelectorAll('input,select,textarea').length === 0;
  }).slice(0, 20);
  errorNodes.forEach(function(el) {
    var id = el.getAttribute('id');
    if (id && describedIds[id]) return;
    if (el.getAttribute('role') === 'alert' && !id) return;  // announced live
    record('form-error-not-associated', el,
           {message: (el.textContent || '').trim().slice(0, 80)});
  });

  // --- 6. Skip link --------------------------------------------------------
  // On a page with a lot of navigation, its absence means every keyboard
  // visit starts by tabbing through the whole menu again.
  var navLinks = document.querySelectorAll('nav a, header a').length;
  if (navLinks > 8) {
    var first = candidates[0];
    // Three ways to recognise a skip link, and the word list is the last of
    // them. It used to be the only one, in five languages, matched against
    // the link's text: measured on a live trilingual site, the German page
    // was reported as having no skip link while its own skip link -
    // `<a id="site-skip-to-content" class="…skiplink-link"
    // href="#main-container">Zum Inhalt springen</a>` - was quoted in the
    // finding. A page is not missing a skip link because the tool speaks
    // fewer languages than the page does.
    //
    // So the structural signals come first and hold in any language: the
    // element says `skip` in its own id or class, or it points at the
    // document's main landmark. The words stay as a fallback for a link
    // that has neither.
    var hasSkip = Array.prototype.slice.call(document.querySelectorAll('a[href^="#"]'))
      .slice(0, 5)
      .some(function(a) {
        var name = (a.getAttribute('id') || '') + ' ' + (a.className || '');
        if (/skip/i.test(name)) return true;
        var href = a.getAttribute('href') || '';
        if (href.length > 1) {
          var target = null;
          try { target = document.querySelector(href); } catch (e) { target = null; }
          if (target && (target.tagName === 'MAIN'
                         || target.getAttribute('role') === 'main'
                         || target.querySelector('main, [role="main"]'))) {
            return true;
          }
          if (/^#(main|content|inhalt|contenu|contenido|contenuto|conteudo)/i.test(href)) {
            return true;
          }
        }
        var label = (a.textContent || '') + ' ' + (a.getAttribute('aria-label') || '');
        return /skip|jump|перейти|content|main|vai|inhalt|springen|contenu|contenido|contenuto|saltar|aller/i.test(label);
      });
    if (!hasSkip) record('no-skip-link', first, {navLinks: navLinks});
  }

  // Put the page back the way it was found.
  try { if (active && active.focus) active.focus({preventScroll: true}); } catch (e) {}
  window.scrollTo(scrollX, scrollY);

  return JSON.stringify({findings: findings.slice(0, 200),
                         focusableChecked: candidates.length,
                         fieldsChecked: fields.length,
                         focusMeasured: canSeeFocus});
})()
"""


def issues_from_states(payload: str, source: str) -> list:
    """State-pass results -> `Issue`s."""
    data = _load(payload)
    if "error" in data:
        return [Issue(rule_id="state-pass", severity=MODERATE,
                      category=ACCESSIBILITY, source=source, engine="browser",
                      details={"engine_error": data["error"]})]

    issues = []
    for finding in data.get("findings", []):
        rule = finding.get("rule", "")
        severity = STATE_RULES.get(rule, MODERATE)
        details = {k: v for k, v in finding.items()
                   if k not in ("rule", "selector", "html")}
        details["engine"] = "state-pass"
        issues.append(Issue(
            rule_id=f"state:{rule}",
            severity=severity,
            category=ACCESSIBILITY,
            selector=finding.get("selector", ""),
            snippet=finding.get("html", ""),
            source=source,
            engine="browser",
            details=details,
        ))
    # The script ran, there were focusable elements, and the document never
    # had focus: `:focus` styles cannot match, so three checks read nothing.
    # That is recorded as a note and not left as silence. It is `NEEDS_BROWSER`
    # on purpose - the default view treats "could not be decided" as not a
    # finding, and `--unsettled` is where it shows.
    if data.get("focusableChecked") and data.get("focusMeasured") is False:
        issues.append(Issue(
            rule_id="state:focus-not-measured",
            severity=STATE_RULES["focus-not-measured"],
            category=ACCESSIBILITY, source=source, engine="browser",
            confidence=NEEDS_BROWSER,
            details={"engine": "state-pass",
                     "count": data.get("focusableChecked", 0)},
        ))
    return issues


def _load(payload) -> dict:
    if isinstance(payload, dict):
        return payload
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except (TypeError, ValueError):
        return {"error": "state pass returned a non-JSON result"}


def state_script() -> str:
    return STATE_SCRIPT
