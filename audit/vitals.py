"""Early, isolated web-vitals collection and explicit lab measurement evidence."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from statistics import median, pstdev

VENDOR = Path(__file__).resolve().parent / "vendor"
METRICS = {"LCP": "largestContentfulPaint", "CLS": "cumulativeLayoutShift",
           "INP": "interactionToNextPaint"}


def vendor_identity() -> dict:
    identity = json.loads((VENDOR / "web-vitals.json").read_text(encoding="utf-8"))
    actual = hashlib.sha256((VENDOR / "web-vitals.attribution.iife.js").read_bytes()).hexdigest()
    if actual != identity["artifact_sha256"]:
        raise ValueError("web-vitals artifact hash differs from its manifest")
    identity["collector_sha256"] = hashlib.sha256((BOOTSTRAP + SNAPSHOT).encode()).hexdigest()
    return identity


def bootstrap_script() -> str:
    """Installed at document creation, before the page's scripts or inputs."""
    vendor_identity()
    return (VENDOR / "web-vitals.attribution.iife.js").read_text(encoding="utf-8") + BOOTSTRAP


BOOTSTRAP = r"""
;(function() {
  const state = window.__xanalyzeVitals = {
    metrics: {}, errors: {}, startedAt: performance.now(),
    capturedAt: new Date().toISOString(), initialVisibility: document.visibilityState,
    supported: typeof PerformanceObserver === 'function' ? Array.from(PerformanceObserver.supportedEntryTypes || []) : []
  };
  // Retain the maximum after *each* entry, including buffered deliveries
  // containing multiple windows. web-vitals 6.2.3 compares only the last
  // session in one delivery; a later smaller session must not erase a peak.
  let session = [], sessionValue = 0, peak = [], peakValue = 0;
  function clsMetric(metric) {
    if (peakValue <= metric.value) return metric;
    const largest = peak.reduce((a, b) => a.value >= b.value ? a : b);
    const node = largest.sources && largest.sources[0] && largest.sources[0].node;
    const attribution = {largestShiftTime: largest.startTime, largestShiftValue: largest.value};
    if (node) attribution.largestShiftTarget = node.id ? '#' + CSS.escape(node.id) : node.nodeName.toLowerCase();
    return Object.assign({}, metric, {value: peakValue, entries: peak, attribution: attribution,
      rating: peakValue > .25 ? 'poor' : peakValue > .1 ? 'needs-improvement' : 'good'});
  }
  if (state.supported.includes('layout-shift')) {
    const observer = new PerformanceObserver(list => {
      list.getEntries().forEach(entry => {
        if (entry.hadRecentInput || !Number.isFinite(entry.value)) return;
        if (session.length && entry.startTime - session[session.length - 1].startTime < 1000
            && entry.startTime - session[0].startTime < 5000) {
          session.push(entry); sessionValue += entry.value;
        } else { session = [entry]; sessionValue = entry.value; }
        if (sessionValue > peakValue) { peakValue = sessionValue; peak = session.slice(); }
      });
      if (state.metrics.CLS) record(clsMetric(state.metrics.CLS));
    });
    observer.observe({type: 'layout-shift', buffered: true});
  }
  function record(metric) {
    if (metric.name === 'CLS') metric = clsMetric(metric);
    const attribution = {};
    Object.entries(metric.attribution || {}).forEach(([key, value]) => {
      if (typeof value === 'number' && Number.isFinite(value)) attribution[key] = value;
      if (typeof value === 'string') attribution[key] = value.slice(0, 1000);
    });
    state.metrics[metric.name] = {
      name: metric.name, value: metric.value, rating: metric.rating, navigationType: metric.navigationType,
      attribution: attribution, observedAt: performance.now(),
      entries: metric.entries.slice(-50).map(e => ({
        entryType: e.entryType, startTime: e.startTime, duration: e.duration,
        value: e.value, hadRecentInput: e.hadRecentInput, interactionId: e.interactionId,
        name: e.name, processingStart: e.processingStart, processingEnd: e.processingEnd
      }))
    };
  }
  [['CLS', webVitals.onCLS], ['LCP', webVitals.onLCP], ['INP', webVitals.onINP]]
    .forEach(([name, observe]) => {
      try { observe(record, {reportAllChanges: true, durationThreshold: 16}); }
      catch (error) { state.errors[name] = String(error); }
    });
})();
"""

# Appended inside the measurement probe in the same isolated world.
SNAPSHOT = r"""
      const state = window.__xanalyzeVitals;
      result.vitals = {};
      const types = {LCP: 'largest-contentful-paint', CLS: 'layout-shift', INP: 'event'};
      const keys = {LCP: 'largestContentfulPaint', CLS: 'cumulativeLayoutShift', INP: 'interactionToNextPaint'};
      Object.entries(keys).forEach(([name, key]) => {
        const measured = state && state.metrics[name];
        const supported = state && state.supported.includes(types[name]);
        const error = state && state.errors[name];
        const reason = !state ? 'early collector unavailable'
          : error ? error : !supported ? 'performance API unsupported'
          : name === 'INP' ? 'no measured interactions'
          : name === 'CLS' ? 'no foreground first contentful paint'
          : 'no largest contentful paint candidate';
        result.vitals[name] = measured
          ? Object.assign({status: 'checked', provisional: true}, measured)
          : {status: error ? 'error' : 'unknown', reason: reason};
        if (measured && Number.isFinite(measured.value)) result[key] = measured.value;
      });
      result.conditions = {
        kind: 'lab', scope: 'top-level navigation', final: false,
        lifecycle: 'bounded foreground observation, not full page lifetime',
        collectorStartedAtMs: state ? state.startedAt : null,
        observedUntilMs: performance.now(), capturedAt: new Date().toISOString(),
        initialVisibility: state ? state.initialVisibility : null,
        visibility: document.visibilityState, readyState: document.readyState,
        viewport: {width: innerWidth, height: innerHeight, devicePixelRatio: devicePixelRatio},
        userAgent: navigator.userAgent,
        cpu: {throttling: 'none'}, network: {throttling: 'none'},
        device: {emulation: 'viewport only', hardware: 'host hardware, unspecified'},
        interactionCount: typeof performance.interactionCount === 'number' ? performance.interactionCount : null,
        bfcache: 'not exercised', subframes: 'not aggregated', cacheHit: false, freshMeasurement: true
      };
"""


def repeat_summary(samples: list[dict]) -> dict:
    """Dispersion from actual successful samples; missing data is not zero."""
    summary = {}
    for name, key in METRICS.items():
        values = [s[key] for s in samples if type(s.get(key)) in (int, float)
                  and math.isfinite(s[key])]
        summary[name] = ({"status": "checked", "samples": len(values), "median": median(values),
                          "min": min(values), "max": max(values), "stddev": pstdev(values)}
                         if values else {"status": "unknown", "samples": 0})
    return {"requested_runs": len(samples), "metrics": summary}


def validate_scenario(actions) -> list[dict]:
    """Bounded opt-in native input, without arbitrary JavaScript or text values."""
    if not isinstance(actions, list) or len(actions) > 10:
        raise ValueError("performance scenario must be an array of at most 10 actions")
    normalized = []
    for action in actions:
        if not isinstance(action, dict) or set(action) - {"action", "selector", "key", "wait_ms"}:
            raise ValueError("invalid performance scenario fields")
        kind, selector = action.get("action"), action.get("selector")
        if kind not in ("click", "key") or not isinstance(selector, str) or not selector.strip() or len(selector) > 500:
            raise ValueError("each scenario action needs click/key and one CSS selector")
        delay = action.get("wait_ms", 200)
        if type(delay) is not int or not 50 <= delay <= 2000:
            raise ValueError("scenario wait_ms must be between 50 and 2000")
        key = action.get("key", "")
        if kind == "key" and key not in ("Enter", "Space", "Tab", "Escape", "ArrowDown", "ArrowUp"):
            raise ValueError("unsupported scenario key")
        if kind == "click" and key:
            raise ValueError("click actions cannot specify a key")
        normalized.append({"action": kind, "selector": selector, "key": key, "wait_ms": delay})
    return normalized


def performance_lines(coverage, lang="en") -> tuple[str, list[str]]:
    """Human exports keep clean metric values and uncertainty beside conditions."""
    title, lab, field, unknown, cached = {
        "uk": ("Продуктивність", "Лабораторний прогін", "Польові дані", "невідомо", "з кешу"),
        "it": ("Prestazioni", "Misura di laboratorio", "Dati sul campo", "sconosciuto", "dalla cache"),
        "en": ("Performance", "Lab observation", "Field data", "unknown", "cached"),
    }.get(lang, ("Performance", "Lab observation", "Field data", "unknown", "cached"))
    unit, cpu_network, no_throttle, median_label = {
        "uk": ("мс", "CPU/мережа", "без обмежень", "медіана"),
        "it": ("ms", "CPU/rete", "nessun limite", "mediana"),
        "en": ("ms", "CPU/network", "unthrottled", "median"),
    }.get(lang, ("ms", "CPU/network", "unthrottled", "median"))
    statuses = {"uk": {"checked": "перевірено", "unknown": "невідомо", "error": "помилка", "skipped": "пропущено"},
                "it": {"checked": "verificato", "unknown": "sconosciuto", "error": "errore", "skipped": "saltato"}}
    reasons = {
        "uk": {"no measured interactions": "немає виміряних взаємодій",
               "navigation run has no scenario interactions": "прогін завантаження без взаємодій",
               "CrUX requires a public HTTP(S) URL without credentials": "CrUX доступний для публічних HTTP(S) адрес без облікових даних",
               "CRUX_API_KEY is not configured": "ключ CrUX не налаштовано",
               "no field data for the requested scope": "немає польових даних у запитаних межах",
               "Lighthouse CLI is not installed": "Lighthouse CLI не встановлено"},
        "it": {"no measured interactions": "nessuna interazione misurata",
               "navigation run has no scenario interactions": "caricamento senza interazioni",
               "CRUX_API_KEY is not configured": "chiave CrUX non configurata",
               "no field data for the requested scope": "nessun dato sul campo nell'ambito richiesto"},
    }.get(lang, {})
    lines = []
    for page in coverage.get("performance", []):
        data = page.get("measurements") or {}
        conditions = data.get("conditions") or {}
        viewport = conditions.get("viewport") or {}
        metrics = data.get("vitals") or {}
        values = []
        for name in METRICS:
            metric = metrics.get(name) or {}
            value = metric.get("value") if metric.get("status") == "checked" else None
            reason = metric.get("reason", unknown)
            values.append(f"{name} {value:g}{' ' + unit if name != 'CLS' else ''}" if type(value) in (int, float)
                          else f"{name} {unknown} ({reasons.get(reason, reason)})")
        cache = f"; {cached}" if conditions.get("cacheHit") else ""
        source = " ".join(str(page.get("source", "")).split())
        lines.append(f"{source}: {lab}{cache}; {viewport.get('width', '?')}×{viewport.get('height', '?')}; "
                     f"{cpu_network}: " + (no_throttle if
                         conditions.get("cpu", {}).get("throttling") == conditions.get("network", {}).get("throttling") == "none"
                         else unknown) + "; " + "; ".join(values))
        for action in conditions.get("scenario", []):
            if action.get("status") == "error":
                lines.append(f"{action.get('selector')}: {action.get('reason')}")
        repeats = data.get("repeats") or {}
        for name, statistics in (repeats.get("metrics") or {}).items():
            if statistics.get("samples", 0) > 1:
                lines.append(f"{name}: n={statistics['samples']}, {median_label}={statistics['median']:g}, "
                             f"min={statistics['min']:g}, max={statistics['max']:g}, σ={statistics['stddev']:g}")
    for source in coverage.get("performance_sources", []):
        kind = field if source.get("kind") == "field" else lab
        status = statuses.get(lang, {}).get(source.get("status"), source.get("status"))
        reason = source.get("reason", "")
        lines.append(f"{source.get('source')}: {kind}; {status}; "
                     f"{source.get('profile') or source.get('form_factor') or ''} "
                     f"{reasons.get(reason, reason)}".strip())
        for name, metric in (source.get("metrics") or {}).items():
            lines.append(f"{name}: p75={metric['p75']:g}" if metric.get("status") == "checked"
                         else f"{name}: {unknown}")
        period = source.get("collection_period")
        if period:
            dates = ['-'.join(str((period.get(key) or {}).get(part, '?')) for part in ('year', 'month', 'day'))
                     for key in ('firstDate', 'lastDate')]
            lines.append(f"CrUX: {' → '.join(dates)}; {source.get('scope')}")
        for name, statistics in (source.get("dispersion", {}).get("metrics") or {}).items():
            if statistics.get("status") == "checked":
                lines.append(f"{name}: n={statistics['samples']}, {median_label}={statistics['median']:g}, "
                             f"min={statistics['min']:g}, max={statistics['max']:g}, σ={statistics['stddev']:g}")
        for run in source.get("runs", [])[:1]:
            if run.get("conditions"):
                conditions = run["conditions"]
                screen, throttle = conditions.get("screenEmulation") or {}, conditions.get("throttling") or {}
                lines.append(f"Lighthouse: {screen.get('width', '?')}×{screen.get('height', '?')}; "
                             f"CPU ×{throttle.get('cpuSlowdownMultiplier', '?')}; "
                             f"{conditions.get('throttlingMethod')}; RTT {throttle.get('rttMs', '?')} {unit}; "
                             f"{throttle.get('throughputKbps', '?')} kbit/s")
            if run.get("metrics", {}).get("INP", {}).get("status") == "unknown":
                reason = run['metrics']['INP'].get('reason', unknown)
                lines.append(f"INP: {unknown} ({reasons.get(reason, reason)})")
    return title, lines
