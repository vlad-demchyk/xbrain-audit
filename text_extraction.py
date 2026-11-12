"""Raw text, normalised views and exact coordinates from one DOM snapshot."""
from __future__ import annotations

import re

ASCII_WHITESPACE = " \t\r\n\f\v"


class RenderedHTML(str):
    """HTML-compatible renderer output with trusted out-of-band text data."""
    def __new__(cls, html, snapshot=None):
        result = super().__new__(cls, html)
        result.text_snapshot = snapshot or {}
        return result


def normalize_with_map(text: str) -> tuple[str, list]:
    """Compact [normalised start/end, raw start/end] segments, code points."""
    output, mapping = [], []
    offset = 0
    for match in re.finditer(r"\S+|\s+", text):
        raw = match.group()
        if raw.isspace():
            if not output or match.end() == len(text):
                continue
            normal = " "
        else:
            normal = raw
        output.append(normal)
        mapping.append([offset, offset + len(normal), match.start(), match.end()])
        offset += len(normal)
    return "".join(output), mapping


def normalized_range_to_raw(mapping, start: int, end: int) -> tuple[int, int]:
    if type(start) is not int or type(end) is not int or start < 0 or end <= start:
        raise ValueError("invalid normalised range")
    first = next((m for m in mapping if m[0] <= start < m[1]), None)
    last = next((m for m in mapping if m[0] < end <= m[1]), None)
    if first is None or last is None:
        raise ValueError("normalised range is outside the text")
    raw_start = first[2] + start - first[0]
    raw_end = last[3] if end == last[1] else last[2] + end - last[0]
    return raw_start, raw_end


def text_from_nodes(nodes) -> tuple[str, list, list]:
    """Trim structural ASCII margins while retaining NBSP and node identity."""
    raw = "".join(n["text"] for n in nodes)
    left = len(raw) - len(raw.lstrip(ASCII_WHITESPACE))
    right = len(raw.rstrip(ASCII_WHITESPACE))
    text = raw[left:right]
    ranges, languages = [], []
    offset = 0
    for node in nodes:
        stop = offset + len(node["text"])
        low, high = max(left, offset), min(right, stop)
        if low < high:
            ranges.append({"text_start": low - left, "text_end": high - left,
                           "node_start": low - offset, "node_text": node["text"],
                           "selector": node["selector"], "node_index": node["node_index"]})
            if node.get("language"):
                languages.append({"start": low - left, "end": high - left,
                                  "language": node["language"]})
        offset = stop
    return text, ranges, languages


def span_dom_ranges(block, start: int, end: int) -> list:
    """Python code-point spans -> native DOM Range UTF-16 offsets."""
    ranges = []
    for node in getattr(block, "dom_ranges", []):
        low, high = max(start, node["text_start"]), min(end, node["text_end"])
        if low >= high:
            continue
        node_start = node["node_start"] + low - node["text_start"]
        node_end = node["node_start"] + high - node["text_start"]
        raw = node["node_text"]
        item = {"selector": node["selector"], "start": len(raw[:node_start].encode("utf-16-le")) // 2,
                "end": len(raw[:node_end].encode("utf-16-le")) // 2,
                "unit": "utf-16", "context_path": list(getattr(block, "context_path", []))}
        if node["node_index"] < 0:
            item["attribute"] = block.attribute_name
        else:
            item["node_index"] = node["node_index"]
        ranges.append(item)
    return ranges


TEXT_SNAPSHOT_SCRIPT = r"""
(function () {
  const result = {version: 1, blocks: [], contexts: [], unknown: [], hidden_excluded: 0,
    captured_at: new Date().toISOString(), truncated: false, closed_shadow_roots: 'unknown',
    conditions: {width: innerWidth, height: innerHeight, ready_state: document.readyState},
    limits: {roots: 32, blocks: 10000, characters: 2000000},
    visibility_definition: 'CSS visibility and rendered layout; occlusion is not measured'};
  result.main_html = (document.doctype ? new XMLSerializer().serializeToString(document.doctype) : '') +
    document.documentElement.outerHTML;
  let roots = 0, characters = 0;
  const candidates = 'h1,h2,h3,h4,h5,h6,p,li,a,button,span,figcaption,blockquote,td,th,label';
  const containers = 'div,section,article,dd,dt,figure,summary,caption';
  const skip = 'script,style,noscript,template,svg,path,head,meta,link';
  const scope = ""; // XAUDIT_SCOPE
  result.conditions.within = scope;
  function query(root, selector) {
    const found = [...root.querySelectorAll(selector)];
    if (root.nodeType === 1 && root.matches(selector)) found.unshift(root);
    return found;
  }
  function path(el) {
    const parts = [];
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      const name = node.localName;
      let position = 1;
      for (let prior = node.previousElementSibling; prior; prior = prior.previousElementSibling)
        if (prior.localName === name) position++;
      parts.unshift(name + ':nth-of-type(' + position + ')');
    }
    return parts.join(' > ');
  }
  function language(el) {
    for (let node = el; node; node = node.parentElement || (node.getRootNode().host || null)) {
      const value = node.getAttribute('lang') || node.getAttribute('xml:lang');
      if (value) return value;
    }
    return null;
  }
  function knownHidden(el) {
    if (!el) return true;
    const view = el.ownerDocument.defaultView;
    if (!view) return true;
    const own = view.getComputedStyle(el);
    if (own.visibility === 'hidden' || own.visibility === 'collapse') return true;
    for (let node = el; node; node = node.parentElement || (node.getRootNode().host || null)) {
      const style = view.getComputedStyle(node);
      if (node.hasAttribute('hidden') || style.display === 'none' ||
          style.contentVisibility === 'hidden' || Number(style.opacity) === 0) return true;
    }
    return false;
  }
  function nodesFor(el, direct, includeHidden) {
    const nodes = [];
    const walker = el.ownerDocument.createTreeWalker(el, 4);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const parent = node.parentElement;
      if (!parent || (direct && parent !== el) || parent.closest(includeHidden ? 'script,style,noscript,template,head,meta,link' : skip)) continue;
      if (!includeHidden) {
        if (knownHidden(parent)) continue;
        const range = el.ownerDocument.createRange();
        range.selectNodeContents(node);
        if (![...range.getClientRects()].some(rect => rect.height > 0)) continue;
      }
      nodes.push({text: node.nodeValue, selector: path(parent),
        node_index: [...parent.childNodes].indexOf(node), language: language(parent)});
    }
    return nodes;
  }
  function add(el, nodes, context, attribute, textKind) {
    const text = nodes.map(node => node.text).join('');
    if (!text.replace(/^[ \t\r\n\f\v]+|[ \t\r\n\f\v]+$/g, '')) return;
    if (result.blocks.length >= result.limits.blocks || characters + text.length > result.limits.characters) {
      result.truncated = true;
      return;
    }
    characters += text.length;
    result.blocks.push({selector: path(el), nodes, context_path: context,
      attribute: attribute || '', text_kind: textKind || (attribute ? 'attribute' : 'dom-text'),
      visibility: 'visible', declared_language: language(el),
      rendered_visible_text: attribute ? null : (typeof el.innerText === 'string' ? el.innerText : null),
      source_context: {element: el.localName, document_url: el.ownerDocument.URL,
        locale_key: el.getAttribute('data-i18n') || el.getAttribute('data-l10n-key') || null,
        component_file: el.getAttribute('data-component-file') || null}});
  }
  function visit(root, context) {
    if (++roots > result.limits.roots) {
      result.truncated = true;
      result.unknown.push({context_path: context, reason: 'root budget'});
      return;
    }
    result.contexts.push({context_path: context, status: 'checked'});
    const elements = query(root, candidates);
    const texts = new Map();
    const records = new Map();
    for (const el of elements) {
      const nodes = nodesFor(el, false, false);
      records.set(el, nodes);
      texts.set(el, nodes.map(node => node.text).join('').trim());
    }
    for (const el of elements) {
      if (el.closest(skip)) continue;
      if (knownHidden(el)) { result.hidden_excluded++; continue; }
      let duplicate = false;
      for (let parent = el.parentElement; parent; parent = parent.parentElement)
        if (texts.has(parent) && texts.get(parent) === texts.get(el)) { duplicate = true; break; }
      if (!duplicate) add(el, records.get(el), context);
    }
    for (const el of query(root, containers))
      if (!knownHidden(el) && !el.closest(skip)) add(el, nodesFor(el, true, false), context);
    for (const el of query(root, '[aria-label],[placeholder],[alt],[title],[aria-labelledby]')) {
      if (knownHidden(el) || el.closest('script,style,noscript,template,head,meta,link')) continue;
      if (![...el.getClientRects()].some(rect => rect.width > 0 || rect.height > 0)) continue;
      for (const attribute of ['aria-label','placeholder','alt','title']) {
        const text = el.getAttribute(attribute);
        if (text) add(el, [{text, selector: path(el), node_index: -1, language: language(el)}], context, attribute);
      }
      for (const id of (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean)) {
        const labels = root.querySelectorAll('#' + CSS.escape(id));
        if (labels.length === 1) add(el, nodesFor(labels[0], false, true), context, 'aria-labelledby', 'referenced-label');
        else result.unknown.push({context_path: context, selector: path(el), reason: 'unavailable or ambiguous label reference'});
      }
    }
    for (const el of query(root, '*')) {
      if (el.shadowRoot && !knownHidden(el)) visit(el.shadowRoot, context.concat([{type:'shadow', selector:path(el)}]));
      if (el.localName === 'iframe') {
        const frame = context.concat([{type:'frame', selector:path(el), url:el.src || 'about:srcdoc'}]);
        if (knownHidden(el)) { result.contexts.push({context_path:frame, status:'skipped', reason:'hidden frame'}); continue; }
        try {
          if (el.contentDocument && el.contentDocument.documentElement) visit(el.contentDocument, frame);
          else result.unknown.push({context_path:frame, reason:'cross-origin or unavailable frame'});
        } catch (_) { result.unknown.push({context_path:frame, reason:'inaccessible frame'}); }
      }
    }
  }
  try {
    const root = scope ? document.querySelector(scope) : document;
    if (root) visit(root, []);
    else result.unknown.push({selector: scope, reason: 'requested text scope not found'});
  } catch (error) {
    result.unknown.push({selector: scope, reason: 'text scope failed: ' + String(error)});
  }
  return JSON.stringify(result);
})()
"""
