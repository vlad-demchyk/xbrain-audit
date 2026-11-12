"""All comparison decisions precede one shared test exposure, including failures."""
from copy import deepcopy
import json

import pytest

from tests.test_validation_contract import dataset, experiment
from validation import comparison, corpus, protocol


METHODS = [{"id": "offline", "detector": "offline"}, {"id": "heuristic", "detector": "heuristic"}]


def rehash(value, field):
    value[field] = corpus.digest({k: v for k, v in value.items() if k != field})


def test_frozen_comparison_calibrates_all_then_consumes_shared_test_once(experiment):
    data = dataset()
    frozen = comparison.freeze_comparison(data, METHODS)
    assert experiment == [["calibration-human", "calibration-model"]] * 2
    report = comparison.evaluate_comparison(data, frozen)
    assert experiment == [["calibration-human", "calibration-model"]] * 2 + [["test-human", "test-model"]] * 2
    assert set(report["reports"]) == {"offline", "heuristic"}
    assert not report["quality"]["passed"]  # Synthetic fixtures cannot certify readiness.
    assert set(comparison.verify_comparison_report(report)) == {"offline", "heuristic"}
    for child in report["reports"].values():
        assert protocol.verify_report(child) == child["metrics"]
    with pytest.raises(ValueError, match="already been consumed"):
        comparison.evaluate_comparison(data, frozen)
    with pytest.raises(ValueError, match="already been consumed"):
        protocol.evaluate(data, frozen["protocols"]["offline"])
    with pytest.raises(ValueError, match="already exposed"):
        protocol.freeze(data)


@pytest.mark.parametrize("methods", [[], [METHODS[0]], METHODS * 2,
    [{"id": "a", "detector": "offline"}, {"id": "b", "detector": "offline"}],
    [METHODS[0], {"id": "../bad", "detector": "heuristic"}],
    [METHODS[0], {"id": "bad", "detector": "heuristic", "api_key": "secret"}],
    [METHODS[0], {"id": "bad", "detector": "heuristic", "fixed_threshold": True}],
    [METHODS[0], {"id": "bad", "detector": "unavailable"}]])
def test_invalid_method_set_fails_before_any_calibration_or_http(experiment, methods):
    with pytest.raises(ValueError):
        comparison.freeze_comparison(dataset(), methods)
    assert experiment == []


def test_remote_preflight_failure_does_not_consume_any_test(experiment):
    data = dataset()
    for row in data["samples"]:
        row["provenance"]["public_benchmark"] = True
    methods = [METHODS[0], {"id": "judge", "detector": "claude-llm-judge", "config": {"model": "fixture-version"}}]
    frozen = comparison.freeze_comparison(data, methods, allow_remote=True)
    with pytest.raises(ValueError, match="allow-remote"):
        comparison.evaluate_comparison(data, frozen)
    assert not any(p.exists() for p in protocol._test_paths(data["samples"]).values())
    assert len(experiment) == 2


def test_catastrophic_method_failure_still_exposes_the_whole_shared_test(experiment, monkeypatch):
    data = dataset();frozen = comparison.freeze_comparison(data, METHODS)
    original = protocol.score_samples
    def failing(rows, name, *args, **kwargs):
        if name == "heuristic":
            raise RuntimeError("deliberate fixture failure")
        return original(rows, name, *args, **kwargs)
    monkeypatch.setattr(protocol, "score_samples", failing)
    with pytest.raises(RuntimeError, match="deliberate"):
        comparison.evaluate_comparison(data, frozen)
    assert all(p.exists() for p in protocol._test_paths([r for r in data["samples"] if r["split"] == "test"]).values())
    with pytest.raises(ValueError, match="already been consumed"):
        comparison.evaluate_comparison(data, frozen)


def test_cannot_drop_bad_method_rewrite_quality_or_reassign_results(experiment):
    data = dataset();frozen = comparison.freeze_comparison(data, METHODS)
    result = comparison.evaluate_comparison(data, frozen)
    removed = deepcopy(result);removed["reports"].pop("heuristic");rehash(removed, "report_sha256")
    with pytest.raises(ValueError, match="every predeclared"):
        comparison.verify_comparison_report(removed)
    forged = deepcopy(result);forged["quality"]["passed"] = True;rehash(forged, "report_sha256")
    with pytest.raises(ValueError, match="quality changed"):
        comparison.verify_comparison_report(forged)
    swapped = deepcopy(result)
    swapped["reports"]["offline"], swapped["reports"]["heuristic"] = swapped["reports"]["heuristic"], swapped["reports"]["offline"]
    rehash(swapped, "report_sha256")
    with pytest.raises(ValueError, match="member protocol changed"):
        comparison.verify_comparison_report(swapped)


def test_frozen_method_set_cannot_expand_after_test_even_with_recomputed_hashes(experiment):
    data = dataset();frozen = comparison.freeze_comparison(data, METHODS)
    extra = protocol.freeze(data, "offline", {"batch_size": 2})
    comparison.evaluate_comparison(data, frozen)
    expanded = deepcopy(frozen);expanded["protocols"]["extra"] = extra;rehash(expanded, "comparison_sha256")
    with pytest.raises(ValueError, match="already been consumed"):
        comparison.evaluate_comparison(data, expanded)


def test_standalone_report_cannot_borrow_comparison_ledger_without_membership(experiment):
    data = dataset();frozen = comparison.freeze_comparison(data, METHODS)
    result = comparison.evaluate_comparison(data, frozen)
    child = deepcopy(result["reports"]["offline"])
    child.pop("comparison_sha256");rehash(child, "report_sha256")
    with pytest.raises(ValueError, match="another protocol"):
        protocol.verify_report(child)


def test_real_cli_comparison_on_offline_fixture_consumes_test_once(tmp_path, monkeypatch):
    from scripts.benchmark import main
    monkeypatch.setenv("XAUDIT_VALIDATION_LEDGER", str(tmp_path / "ledger"))
    data = tmp_path / "data.json";data.write_text(json.dumps(dataset()))
    methods = tmp_path / "methods.json";methods.write_text(json.dumps([{**m, "fixed_threshold": 1.} for m in METHODS]))
    frozen = tmp_path / "frozen.json";report = tmp_path / "report.json"
    assert main(["freeze-comparison", str(data), "--methods", str(methods), "--output", str(frozen)]) == 0
    assert main(["run-comparison", str(data), "--protocol", str(frozen), "--output", str(report)]) == 2
    result = json.loads(report.read_text())
    assert set(comparison.verify_comparison_report(result)) == {"offline", "heuristic"}
    assert main(["run-comparison", str(data), "--protocol", str(frozen), "--output", str(tmp_path / "again.json")]) == 1
