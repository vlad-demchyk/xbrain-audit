"""Field data never masquerades as lab timings, or unavailable data as zero."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from audit import performance_sources as sources


def response(status, payload=None):
    return SimpleNamespace(status_code=status, json=lambda: payload)


def test_crux_preserves_scope_p75_and_collection_period(monkeypatch):
    monkeypatch.setenv("CRUX_API_KEY", "fixture-key")
    calls = []
    period = {"firstDate": {"year": 2026, "month": 9, "day": 1},
              "lastDate": {"year": 2026, "month": 9, "day": 28}}
    def post(endpoint, **kwargs):
        calls.append((endpoint, kwargs))
        return response(200, {"record": {"key": {"url": "https://example.test/path", "formFactor": "PHONE"},
            "collectionPeriod": period, "metrics": {
                "cumulative_layout_shift": {"percentiles": {"p75": "0.12"}},
                "largest_contentful_paint": {"percentiles": {"p75": 2300}}}}})
    result = sources.crux("https://example.test/path", form_factor="PHONE", post=post)
    assert result["kind"] == "field" and result["status"] == "checked"
    assert result["metrics"]["CLS"]["p75"] == .12
    assert result["metrics"]["INP"]["status"] == "unknown"
    assert result["collection_period"] == period
    assert calls[0][1]["json"]["url"] == "https://example.test/path"
    assert "origin" not in calls[0][1]["json"]
    assert "fixture-key" not in json.dumps(result)


def test_no_crux_data_stays_unknown_without_origin_retry(monkeypatch):
    monkeypatch.setenv("CRUX_API_KEY", "fixture-key")
    calls = []
    result = sources.crux("https://example.test/a", post=lambda *a, **k: calls.append(k) or response(404))
    assert result["status"] == "unknown" and len(calls) == 1
    assert "metrics" not in result


def test_crux_exceptions_never_leak_key(monkeypatch):
    monkeypatch.setenv("CRUX_API_KEY", "do-not-log-this-key")
    def post(*a, **k):
        raise requests.ConnectionError("request failed?key=do-not-log-this-key")
    result = sources.crux("https://example.test/", post=post)
    assert result["status"] == "error"
    assert "do-not-log" not in json.dumps(result)


@pytest.mark.parametrize("url", ["http://localhost:8080/", "http://127.0.0.1/",
    "http://192.168.0.1/", "https://user:secret@example.test/", "file:///tmp/page.html"])
def test_private_or_authenticated_urls_do_not_reach_crux(monkeypatch, url):
    monkeypatch.setenv("CRUX_API_KEY", "fixture-key")
    def post(*a, **kw):
        pytest.fail("non-public URL sent to CrUX")
    assert sources.crux(url, post=post)["status"] == "unknown"


def test_lighthouse_profile_and_repeated_values_come_from_its_own_results(monkeypatch):
    monkeypatch.setenv("XAUDIT_LIGHTHOUSE", "/fixture/lighthouse")
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        output = next(arg.split("=", 1)[1] for arg in command if arg.startswith("--output-path="))
        Path(output).write_text(json.dumps({"lighthouseVersion": "13.5.0", "fetchTime": "fixture-date",
            "configSettings": {"formFactor": "desktop", "throttlingMethod": "simulate",
                               "throttling": {"cpuSlowdownMultiplier": 1}},
            "audits": {"largest-contentful-paint": {"numericValue": 100 * len(calls)},
                       "cumulative-layout-shift": {"numericValue": 0}}}))
        return SimpleNamespace(returncode=0)
    result = sources.lighthouse("https://example.test/", profile="desktop", repeats=3, run=run)
    assert result["status"] == "checked" and result["kind"] == "lab"
    assert all("--preset=desktop" in command for command in calls)
    assert result["dispersion"]["metrics"]["LCP"]["median"] == 200
    assert result["runs"][0]["metrics"]["INP"]["status"] == "unknown"
    assert result["runs"][0]["conditions"]["throttlingMethod"] == "simulate"


def test_lighthouse_failure_does_not_count_as_zero_or_success(monkeypatch):
    monkeypatch.setenv("XAUDIT_LIGHTHOUSE", "/fixture/lighthouse")
    result = sources.lighthouse("https://example.test/", repeats=2,
                                run=lambda *a, **kw: SimpleNamespace(returncode=1))
    assert result["status"] == "error"
    assert result["dispersion"]["metrics"]["LCP"] == {"status": "unknown", "samples": 0}


def test_default_options_make_no_external_requests(monkeypatch):
    monkeypatch.setattr(sources, "crux", lambda *a, **kw: pytest.fail("implicit CrUX"))
    monkeypatch.setattr(sources, "lighthouse", lambda *a, **kw: pytest.fail("implicit Lighthouse"))
    assert sources.optional_sources(["https://example.test/"], SimpleNamespace()) == []


def test_cli_flags_and_subtree_scope_preserve_the_requested_bounds():
    from cli import build_parser
    args = build_parser().parse_args(["audit", "https://example.test/", "--within", "#part", "--lighthouse", "--crux"])
    results = sources.optional_sources(["https://example.test/"], args, scoped=True)
    assert len(results) == 2 and all(r["status"] == "skipped" for r in results)
