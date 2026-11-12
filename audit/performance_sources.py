"""Opt-in Lighthouse lab and CrUX field adapters, with independent provenance."""
from __future__ import annotations

import ipaddress
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

import requests

from .vitals import METRICS, repeat_summary

CRUX_ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"
CRUX_METRICS = {"LCP": "largest_contentful_paint", "CLS": "cumulative_layout_shift",
                "INP": "interaction_to_next_paint"}


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def crux(url: str, *, scope="url", form_factor="all", post=None) -> dict:
    """No-data is unknown; no silent URL-to-origin fallback or lab substitution."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    safe_url = parts._replace(netloc=parts.netloc.rsplit("@", 1)[-1]).geturl()
    result = {"source": "CrUX", "kind": "field", "status": "unknown", "scope": scope,
              "form_factor": form_factor, "requested_url": safe_url}
    if scope not in ("url", "origin") or form_factor not in ("all", "PHONE", "TABLET", "DESKTOP"):
        raise ValueError("invalid CrUX scope/form factor")
    private = host in ("localhost", "") or host.endswith((".localhost", ".local"))
    try:
        private = private or not ipaddress.ip_address(host).is_global
    except ValueError:
        pass
    if parts.scheme not in ("http", "https") or private or parts.username or parts.password:
        return {**result, "reason": "CrUX requires a public HTTP(S) URL without credentials"}
    key = os.environ.get("CRUX_API_KEY", "")
    if not key:
        return {**result, "reason": "CRUX_API_KEY is not configured"}
    identifier = f"{parts.scheme}://{parts.netloc}" if scope == "origin" else url.split("#", 1)[0]
    query = {scope: identifier, "metrics": list(CRUX_METRICS.values())}
    if form_factor != "all":
        query["formFactor"] = form_factor
    try:
        response = (post or requests.post)(CRUX_ENDPOINT, params={"key": key}, json=query, timeout=20)
        if response.status_code == 404:
            return {**result, "reason": "no field data for the requested scope"}
        if response.status_code != 200:
            return {**result, "status": "error", "reason": f"CrUX HTTP {response.status_code}"}
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        # Exception strings can contain the API key embedded in the request URL.
        return {**result, "status": "error", "reason": type(exc).__name__}
    record = data.get("record") if isinstance(data, dict) else None
    if not isinstance(record, dict):
        return {**result, "status": "error", "reason": "CrUX response has no record"}
    metrics = {}
    for name, upstream in CRUX_METRICS.items():
        records = record.get("metrics") or {}
        raw = records.get(upstream) if isinstance(records, dict) else None
        raw = raw if isinstance(raw, dict) else {}
        percentiles = raw.get("percentiles") or {}
        value = _number(percentiles.get("p75")) if isinstance(percentiles, dict) else None
        metrics[name] = ({"status": "checked", "p75": value, "histogram": raw.get("histogram", [])}
                         if value is not None else {"status": "unknown", "reason": "metric unavailable"})
    return {**result, "status": "checked", "record_key": record.get("key", {}),
            "collection_period": record.get("collectionPeriod", {}), "metrics": metrics,
            "aggregation": "p75 over the CrUX collection period"}


def lighthouse(url: str, *, profile="mobile", repeats=1, run=None) -> dict:
    """Use an installed CLI; do not install software or reuse sign-in implicitly."""
    if profile not in ("desktop", "mobile") or type(repeats) is not int or not 1 <= repeats <= 10:
        raise ValueError("invalid Lighthouse profile/repeats")
    base = {"source": "Lighthouse", "kind": "lab", "profile": profile, "requested_url": url}
    if urlsplit(url).scheme not in ("http", "https"):
        return {**base, "status": "unknown", "reason": "Lighthouse needs an HTTP(S) page"}
    binary = os.environ.get("XANALYZE_LIGHTHOUSE") or shutil.which("lighthouse")
    if not binary:
        return {**base, "status": "unknown", "reason": "Lighthouse CLI is not installed"}
    samples, runs = [], []
    with tempfile.TemporaryDirectory(prefix="xanalyze-lighthouse-") as temporary:
        for index in range(repeats):
            output = Path(temporary) / f"run-{index}.json"
            command = [binary, url, "--only-categories=performance", "--output=json",
                       f"--output-path={output}", "--quiet", "--chrome-flags=--headless"]
            if profile == "desktop":
                command.append("--preset=desktop")
            try:
                completed = (run or subprocess.run)(command, capture_output=True, text=True,
                                                    encoding="utf-8", errors="replace", timeout=90)
                if completed.returncode:
                    runs.append({"status": "error", "reason": f"Lighthouse exit {completed.returncode}"})
                    samples.append({})
                    continue
                payload = json.loads(output.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Lighthouse JSON is not an object")
                if payload.get("runtimeError"):
                    raise ValueError("Lighthouse runtime error")
                audits = payload.get("audits") or {}
                metrics, sample = {}, {}
                for name, audit_id in (("LCP", "largest-contentful-paint"), ("CLS", "cumulative-layout-shift")):
                    raw = audits.get(audit_id) or {}
                    value = _number(raw.get("numericValue"))
                    metrics[name] = ({"status": "checked", "value": value}
                                     if value is not None else {"status": "unknown"})
                    if value is not None:
                        sample[METRICS[name]] = value
                metrics["INP"] = {"status": "unknown", "reason": "navigation run has no scenario interactions"}
                settings = payload.get("configSettings") or {}
                conditions = {k: settings.get(k) for k in ("formFactor", "screenEmulation", "throttlingMethod",
                              "throttling", "disableStorageReset")}
                runs.append({"status": "checked", "metrics": metrics, "conditions": conditions,
                             "version": payload.get("lighthouseVersion"), "captured_at": payload.get("fetchTime"),
                             "final_url": payload.get("finalDisplayedUrl") or payload.get("finalUrl"),
                             "performance_score": (payload.get("categories", {}).get("performance") or {}).get("score")})
                samples.append(sample)
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                runs.append({"status": "error", "reason": type(exc).__name__})
                samples.append({})
    status = "checked" if all(r["status"] == "checked" for r in runs) else "error"
    return {**base, "status": status, "runs": runs, "dispersion": repeat_summary(samples),
            "session": "separate Chrome profile; stored XAnalyze sign-in is not used"}


def optional_sources(urls, args, *, scoped=False) -> list:
    """Only explicit flags enable external adapters; defaults make no requests."""
    result = []
    for url in dict.fromkeys(urls):
        if getattr(args, "lighthouse", False):
            result.append({"source": "Lighthouse", "kind": "lab", "status": "skipped",
                           "reason": "subtree scope does not describe a page load"} if scoped else
                          lighthouse(url, profile=getattr(args, "lighthouse_profile", "mobile"),
                                     repeats=getattr(args, "performance_repeats", 1)))
        if getattr(args, "crux", False):
            result.append({"source": "CrUX", "kind": "field", "status": "skipped",
                           "reason": "subtree scope does not describe field page data"} if scoped else
                          crux(url, scope=getattr(args, "crux_scope", "url"),
                               form_factor=getattr(args, "crux_form_factor", "all")))
    return result
