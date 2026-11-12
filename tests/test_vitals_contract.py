"""Standards boundaries and real renderer evidence for Core Web Vitals."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from audit import browser, driver, vitals


def observed(shifts):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for deterministic browser-observer fixtures")
    result = subprocess.run([node, str(Path(__file__).with_name("vitals_observer_harness.cjs"))],
                            input=json.dumps({"bootstrap": vitals.bootstrap_script(),
                                              "snapshot": vitals.SNAPSHOT, "shifts": shifts}),
                            text=True, encoding="utf-8", capture_output=True, timeout=5)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("shifts,expected", [
    ([{"startTime": 200, "value": .08}, {"startTime": 2200, "value": .08}], .08),
    ([{"startTime": 200, "value": .08}, {"startTime": 1199, "value": .08}], .16),
    ([{"startTime": 200, "value": .08}, {"startTime": 1200, "value": .08}], .08),
    ([{"startTime": 200 + n * 900, "value": .02} for n in range(7)], .12),
    ([{"startTime": 200, "value": .08, "hadRecentInput": True}], 0),
    ([], 0),
])
def test_cls_uses_maximum_session_window_not_lifetime_sum(shifts, expected):
    result = observed(shifts)
    assert result["cumulativeLayoutShift"] == pytest.approx(expected)
    assert result["vitals"]["CLS"]["status"] == "checked"
    assert result["vitals"]["INP"]["status"] == "unknown"
    assert "interactionToNextPaint" not in result


def test_renderer_captures_early_metrics_and_truthful_conditions(tmp_path):
    page = tmp_path / "vitals.html"
    page.write_text('<h1>A measured page</h1><p>Visible first paint.</p>')
    driver.ensure_headless_application()
    runner = driver.BrowserAuditRunner(browser.BrowserAuditOptions(
        run_axe=False, run_htmlcs=False, run_states=False, settle_ms=200))
    try:
        result = runner.audit(page.as_uri())
    finally:
        runner.close()
    assert not result.error and not result.engine_errors
    assert result.measurements["vitals"]["LCP"]["status"] == "checked"
    assert result.measurements["vitals"]["CLS"]["value"] == 0
    assert result.measurements["vitals"]["INP"]["status"] == "unknown"
    conditions = result.measurements["conditions"]
    assert conditions["kind"] == "lab" and conditions["final"] is False
    assert conditions["viewport"]["width"] == 1440
    assert conditions["cpu"]["throttling"] == "none"
    assert conditions["webVitals"]["version"] == "6.2.3"


def test_dispersion_never_treats_missing_measurements_as_zero():
    summary = vitals.repeat_summary([{"largestContentfulPaint": 100},
                                    {"largestContentfulPaint": 300}, {}])
    assert summary["metrics"]["LCP"] == {"status": "checked", "samples": 2,
        "median": 200, "min": 100, "max": 300, "stddev": 100}
    assert summary["metrics"]["INP"] == {"status": "unknown", "samples": 0}


@pytest.mark.parametrize("action", [{"action": "click", "selector": "#work"},
                                    {"action": "key", "selector": "#work", "key": "Enter"}])
def test_explicit_native_input_produces_attributed_inp(tmp_path, action):
    page = tmp_path / "input.html"
    page.write_text('''<button id="work">Run work</button><p id="answer">Ready</p>
      <script>work.onclick=()=>{const until=performance.now()+120;
      while(performance.now()<until){};answer.textContent='Done';};</script>''')
    driver.ensure_headless_application()
    runner = driver.BrowserAuditRunner(browser.BrowserAuditOptions(
        run_axe=False, run_htmlcs=False, run_states=False, settle_ms=150,
        performance_scenario=[{**action, "wait_ms": 300}]))
    try:
        result = runner.audit(page.as_uri())
    finally:
        runner.close()
    inp = result.measurements["vitals"]["INP"]
    assert inp["status"] == "checked" and inp["value"] >= 100
    assert inp["attribution"]["interactionTarget"] == "#work"
    assert inp["attribution"]["interactionType"] == ("pointer" if action["action"] == "click" else "keyboard")
    assert result.measurements["conditions"]["scenario"][0]["status"] == "checked"


def test_missing_scenario_target_does_not_fabricate_an_inp(tmp_path):
    page = tmp_path / "no-target.html"
    page.write_text('<h1>No button</h1>')
    driver.ensure_headless_application()
    runner = driver.BrowserAuditRunner(browser.BrowserAuditOptions(
        run_axe=False, run_htmlcs=False, run_states=False, settle_ms=100,
        performance_scenario=[{"action": "click", "selector": "#missing"}]))
    try:
        result = runner.audit(page.as_uri())
    finally:
        runner.close()
    assert result.measurements["vitals"]["INP"]["status"] == "unknown"
    assert result.measurements["conditions"]["scenario"][0]["status"] == "error"


def test_scenario_navigation_does_not_attribute_a_new_page_to_the_original(tmp_path):
    destination = tmp_path / "destination.html"
    destination.write_text('<h1>A different navigation</h1>')
    page = tmp_path / "navigate.html"
    page.write_text(f'<a id="next" href="{destination.as_uri()}">Next page</a>')
    driver.ensure_headless_application()
    runner = driver.BrowserAuditRunner(browser.BrowserAuditOptions(
        run_axe=False, run_htmlcs=False, run_states=False, settle_ms=100,
        performance_scenario=[{"action": "click", "selector": "#next"}]))
    try:
        result = runner.audit(page.as_uri())
    finally:
        runner.close()
    assert result.error == "performance scenario changed navigation"
    assert not result.issues and "vitals" not in result.measurements


@pytest.mark.parametrize("actions", [[{"action": "eval", "selector": "body"}],
    [{"action": "click", "selector": "body", "wait_ms": True}],
    [{"action": "key", "selector": "body", "key": "arbitrary"}],
    [{"action": "click", "selector": "body", "code": "alert(1)"}], {}])
def test_scenarios_reject_unbounded_or_arbitrary_operations(actions):
    with pytest.raises(ValueError):
        vitals.validate_scenario(actions)


def test_repeat_navigations_keep_samples_and_dispersion(tmp_path):
    page = tmp_path / "repeat.html"
    page.write_text('<h1>Repeat a measured navigation</h1>')
    driver.ensure_headless_application()
    runner = driver.BrowserAuditRunner(browser.BrowserAuditOptions(
        run_axe=False, run_htmlcs=False, run_states=False, settle_ms=150, performance_repeats=3))
    try:
        result = runner.audit(page.as_uri())
    finally:
        runner.close()
    repeats = result.measurements["repeats"]
    assert repeats["completed_runs"] == repeats["requested_runs"] == 3
    assert repeats["metrics"]["LCP"]["samples"] == 3
    assert len(repeats["runs"]) == 3
    assert repeats["metrics"]["INP"]["status"] == "unknown"
    json.dumps(result.measurements, allow_nan=False)  # No cycles or unsupported numeric values.


def test_clean_metrics_and_repeats_reach_reports_and_checkpoint(tmp_path):
    from audit.coverage import build_coverage
    from audit.engine import AccessibilityResult, DocumentReport
    from cli_impl.checkpoint import save_audit, load_audit
    result = AccessibilityResult(mode="file", root="page.html")
    document = DocumentReport(source="page.html")
    result.documents.append(document)
    payload = {"vitals": {"LCP": {"status": "checked", "value": 123},
                           "INP": {"status": "unknown", "reason": "no measured interactions"}},
               "conditions": {"kind": "lab", "viewport": {"width": 1440, "height": 900}},
               "repeats": vitals.repeat_summary([{"largestContentfulPaint": 100}, {"largestContentfulPaint": 200}])}
    browser.merge_page_audit(result, document, driver.PageAudit(url="page.html", measurements=payload))
    result.coverage = build_coverage(result)
    assert result.coverage["performance"][0]["measurements"] == payload
    save_audit(tmp_path, result)
    restored = load_audit(tmp_path)
    assert restored.coverage["performance"] == result.coverage["performance"]
    title, lines = vitals.performance_lines(restored.coverage, "uk")
    assert title == "Продуктивність"
    assert any("LCP 123" in line and "INP невідомо" in line for line in lines)
    assert any("медіана=150" in line for line in lines)


def test_cached_measurements_and_findings_agree_without_mutating_original(tmp_path):
    from browser_cache import BrowserCache
    measurements = {"cumulativeLayoutShift": .2, "conditions": {"cacheHit": False}}
    issues = browser.issues_from_measurements(measurements, "https://example.test/")
    cache = BrowserCache(browser.BrowserAuditOptions(), (), directory=tmp_path)
    cache.put("<p>page</p>", driver.PageAudit(url="https://example.test/", issues=issues,
                                           measurements=measurements))
    stored = cache.get("<p>page</p>", "https://example.test/")
    assert stored.issues[0].details["measurements"] == stored.measurements
    assert stored.measurements["conditions"]["cacheHit"]
    assert not measurements["conditions"]["cacheHit"]


def test_incomplete_browser_pass_is_never_reused_as_a_clean_measurement(tmp_path):
    from browser_cache import BrowserCache
    cache = BrowserCache(browser.BrowserAuditOptions(), (), directory=tmp_path)
    cache.put("<p>page</p>", driver.PageAudit(url="https://example.test/",
                                           engine_errors={"measurements": "failed"}))
    assert cache.get("<p>page</p>", "https://example.test/") is None


@pytest.mark.parametrize("value", [float("inf"), float("nan"), True, "0.2"])
def test_invalid_numeric_measurements_do_not_become_findings(value):
    assert not browser.issues_from_measurements({"cumulativeLayoutShift": value}, "https://example.test/")
