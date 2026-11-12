"""Independent experiments must reject leakage, refitting and fabricated certainty."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from validation import adapters, corpus, metrics, protocol


def sample(key, label="human", split="calibration", **changes):
    result = {"id": key, "text": f"This fixture has unique ordinary wording {key}.",
        "label": label, "language": "en", "register": "product-copy", "condition": "original",
        "split": split, "groups": {name: f"{name}:{key}" for name in corpus.GROUP_FIELDS},
        "gold_spans": None, "provenance": {"source": f"fixture:{key}", "date": "2026-10-13",
            "license": "test fixture", "verified_by": "unit-test fixture, not real authorship",
            "evidence": "synthetic contract case", "public_benchmark": False,
            "generator": {"name": "fixture", "model_version": "fixture-v1", "prompt": "test case", "date": "2026-10-13"}}}
    result.update(changes)
    return result


def dataset():
    return {"schema_version": 1, "dataset_id": "contract-fixture", "purpose": "fixture", "samples": [
        sample(f"{split}-{label}", label, split) for split in corpus.PARTITIONS for label in ("human", "model")]}


def prediction(key, label, score, **changes):
    return {**sample(key, label), "group_id": key, "status": "checked", "score": score,
            "latency_ms": 10., "cost_usd": 0., "spans": [], **changes}


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    monkeypatch.setenv("XAUDIT_VALIDATION_LEDGER", str(tmp_path / "ledger"))
    calls = []
    def score(rows, *args, **kwargs):
        calls.append([r["id"] for r in rows])
        return [{**r, "status": "checked", "score": .8 if r["label"] == "model" else .1,
                 "spans": [], "latency_ms": 1., "cost_usd": 0.} for r in rows]
    monkeypatch.setattr(protocol, "score_samples", score)
    return calls


def test_shared_site_and_transitive_authors_cannot_cross_splits():
    data = dataset()
    a, b, c = data["samples"][0], data["samples"][2], data["samples"][4]
    b["groups"]["site_id"] = a["groups"]["site_id"]
    c["groups"]["author_id"] = b["groups"]["author_id"]
    with pytest.raises(ValueError, match="cross split"):
        corpus.validate_dataset(data)


def test_unicode_whitespace_variants_cannot_leak_into_test_and_keep_raw_offsets():
    data = dataset()
    raw = "Fixture\u00a0text with hidden\u200b spacing."
    data["samples"][0]["text"] = raw
    data["samples"][4]["text"] = "fixture text with hidden spacing."
    with pytest.raises(ValueError, match="cross split"):
        corpus.validate_dataset(data)
    assert data["samples"][0]["text"] == raw


def test_transform_parent_links_cannot_leak_between_calibration_and_test():
    data = dataset()
    data["samples"][4]["parents"] = [data["samples"][2]["id"]]
    with pytest.raises(ValueError, match="cross split"):
        corpus.validate_dataset(data)


@pytest.mark.parametrize("change", [lambda d: d["samples"][0].update(label="unlabelled"),
    lambda d: d["samples"][0]["provenance"].pop("verified_by"),
    lambda d: d["samples"][1]["provenance"]["generator"].pop("prompt"),
    lambda d: d["samples"][0]["groups"].pop("author_id"),
    lambda d: d["samples"][0].update(gold_spans=[[0, 999999]]),
    lambda d: d["samples"][0].update(gold_spans=[[False, 1]]),
    lambda d: d["samples"][0].update(parents=["unknown"]),
    lambda d: d.update(schema_version=True)])
def test_unverifiable_or_malformed_dataset_is_rejected(change):
    data = dataset();change(data)
    with pytest.raises(ValueError):
        corpus.validate_dataset(data)


def test_partitioning_is_stable_under_reordering_and_never_rewrites_existing_splits():
    data = dataset()
    for row in data["samples"]:
        del row["split"]
    first = corpus.assign_splits(data, "fixed-seed")
    second = corpus.assign_splits({**data, "samples": list(reversed(data["samples"]))}, "fixed-seed")
    assert {r["id"]: r["split"] for r in first["samples"]} == {r["id"]: r["split"] for r in second["samples"]}
    with pytest.raises(ValueError, match="never rewritten"):
        corpus.assign_splits(first, "different-seed")


def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected():
    for value in ('{"label":"human","label":"model"}', '{"score":NaN}'):
        with pytest.raises(ValueError):
            corpus.strict_json(value)


def test_prevalence_adjustment_and_abstention_do_not_inflate_quality():
    rows = [prediction(f"m{i}", "model", .9 if i < 8 else .1) for i in range(10)]
    rows += [prediction(f"h{i}", "human", .9 if i == 0 else .1) for i in range(10)]
    result = metrics.rates(rows, .5, prevalence=.1)
    assert result["recall"] == .8 and result["fpr"] == .1 and result["precision"] == 8/9
    assert result["precision_at_prevalence"] == pytest.approx(.08/.17)
    rows[0].update(status="abstained", score=None)
    rows[-1].update(status="error", score=None)
    result = metrics.rates(rows, .5)
    assert result["recall"] == .7 and result["coverage"] == .9
    assert result["fpr_bounds_with_abstention"] == [.1, .2]
    assert result["precision_at_prevalence"] is None


def test_zero_errors_on_twenty_examples_does_not_prove_one_percent_fpr():
    assert metrics.wilson(0, 20)[1] == pytest.approx(.161125, abs=.000001)
    # NIST's 95% one-sided example is equivalent to this 90% two-sided lower bound.
    assert metrics.wilson(26, 200, .90)[0] == pytest.approx(.09577, abs=.00001)
    assert metrics.wilson(0, 0) is None


def test_many_paragraphs_from_one_source_do_not_become_independent_groups():
    rows = [prediction(f"h{i}", "human", .1, group_id="one-website") for i in range(100)]
    result = metrics.rates(rows, .5)
    assert result["group_intervals"]["human_groups"] == 1
    assert result["group_intervals"]["any_human_error"][1] > .79
    assert result["nominal_sample_intervals"]["fpr"][1] < .04


def test_overlapping_spans_count_once_in_original_unicode_codepoints():
    rows = [prediction("mixed", "mixed", .9, text="A😀BCDE", gold_spans=[[1, 4]],
                       spans=[{"start": 1, "end": 3, "score": .9}, {"start": 2, "end": 5, "score": .9}])]
    result = metrics.span_localization(rows, .5)
    assert result["character_precision"] == .75 and result["character_recall"] == 1
    assert result["iou"] == .75
    rows[0]["gold_spans"] = None
    assert metrics.span_localization(rows, .5)["iou"] is None


def test_high_aggregate_recall_cannot_hide_weak_italian_or_missing_strata():
    rows = [prediction(f"en-{i}", "model", .9, language="en") for i in range(100)]
    rows += [prediction(f"it-{i}", "model", .9 if i < 4 else .1, language="it") for i in range(11)]
    rows += [prediction(f"h-{i}", "human", .1) for i in range(40)]
    report = metrics.metric_report(rows, .5)
    failures = metrics.quality_failures(report, independent=True)
    assert report["overall"]["recall"] > .9
    assert any("language:it: recall" in error for error in failures)
    assert "missing language: uk" in failures
    assert "missing length: 25+" in failures


@pytest.mark.parametrize("changes", [{"max_fpr": float("nan")}, {"min_recall": True},
                                    {"min_groups": 0}, {"languages": []}, {"prevalence": 1}])
def test_invalid_policy_cannot_disable_checks(changes):
    with pytest.raises(ValueError):
        metrics.QualityPolicy(**changes)


def test_freeze_reads_only_calibration_and_test_is_consumed_once(experiment):
    data = dataset()
    frozen = protocol.freeze(data)
    assert experiment == [["calibration-human", "calibration-model"]]
    assert frozen["threshold"] == .8 and not frozen["test_scores_read"]
    report = protocol.evaluate(data, frozen)
    assert experiment[-1] == ["test-human", "test-model"]
    assert not report["quality"]["passed"]  # Synthetic fixture is never an independent release test.
    with pytest.raises(ValueError, match="consumed"):
        protocol.evaluate(data, frozen)
    with pytest.raises(ValueError, match="already exposed"):
        protocol.freeze(data)


def test_dataset_threshold_or_detector_changes_invalidate_protocol(experiment, monkeypatch):
    data = dataset();frozen = protocol.freeze(data)
    modified = deepcopy(frozen);modified["threshold"] = .1
    with pytest.raises(ValueError, match="protocol changed"):
        protocol.verify_protocol(data, modified)
    altered = deepcopy(data);altered["samples"][0]["text"] += " changed"
    with pytest.raises(ValueError, match="dataset changed"):
        protocol.verify_protocol(altered, frozen)
    monkeypatch.setattr(protocol, "detector_identity", lambda *a: {"fingerprint": "changed"})
    with pytest.raises(ValueError, match="detector/prompt"):
        protocol.verify_protocol(data, frozen)


def test_private_benchmark_never_reaches_remote_detector(monkeypatch):
    monkeypatch.setattr(adapters.DetectorFactory, "create", lambda *a, **k: pytest.fail("remote constructor called"))
    with pytest.raises(ValueError, match="public benchmark"):
        adapters.score_samples([sample("private")], "claude-llm-judge", {"model": "explicit-model"}, [], allow_remote=True)


def test_detector_error_does_not_become_a_correct_negative(monkeypatch):
    from detectors.base import Detector
    class Broken:
        supports_language = staticmethod(lambda _l: True)
        def analyze_block(self, block):
            return [Detector._error_span(self, block, RuntimeError("fixture error"))]
        name = "broken"
    monkeypatch.setattr(adapters.DetectorFactory, "create", lambda *a, **k: Broken())
    result = adapters.score_samples([sample("error")], "offline", {}, [])
    assert result[0]["status"] == "error" and result[0]["score"] is None


def test_remote_permission_failure_does_not_consume_test(experiment):
    data = dataset();frozen = protocol.freeze(data, "claude-llm-judge", {"model": "explicit-model"}, allow_remote=True)
    with pytest.raises(ValueError, match="public benchmark"):
        protocol.evaluate(data, frozen, allow_remote=True)
    assert not list(protocol.ledger_dir().glob("*.json"))


def test_output_artifacts_are_created_once(tmp_path):
    output = tmp_path / "protocol.json"
    protocol.write_new(output, {"first": True})
    with pytest.raises(FileExistsError):
        protocol.write_new(output, {"second": True})
    assert json.loads(output.read_text()) == {"first": True}


def test_saved_report_is_recomputed_and_forged_groups_or_metrics_are_rejected(experiment):
    data = dataset();frozen = protocol.freeze(data)
    report = protocol.evaluate(data, frozen)
    assert protocol.verify_report(report) == report["metrics"]
    for field in ("group_id", "score"):
        modified = deepcopy(report)
        modified["predictions"][0][field] = "fake-source" if field == "group_id" else .95
        modified["report_sha256"] = corpus.digest({k: v for k, v in modified.items() if k != "report_sha256"})
        with pytest.raises(ValueError, match="groups changed|metrics changed"):
            protocol.verify_report(modified)


def test_missing_prediction_or_access_record_invalidates_saved_report(experiment):
    data = dataset();frozen = protocol.freeze(data);report = protocol.evaluate(data, frozen)
    modified = deepcopy(report);modified["predictions"].pop()
    modified["report_sha256"] = corpus.digest({k: v for k, v in modified.items() if k != "report_sha256"})
    with pytest.raises(ValueError, match="incomplete"):
        protocol.verify_report(modified)
    for path in protocol.ledger_dir().glob("*.json"):
        path.unlink()
    with pytest.raises(FileNotFoundError):
        protocol.verify_report(report)


def test_release_gate_does_not_accept_fixture_or_an_experiment_relaxed_policy(experiment, tmp_path):
    from scripts.gate import Result, run_quality_report
    data = dataset();frozen = protocol.freeze(data, fixed_threshold=.33)
    report = protocol.evaluate(data, frozen)
    output = tmp_path / "report.json";protocol.write_new(output, report)
    result = Result();run_quality_report(result, output)
    assert result.failures and any("independent locked test" in failure for failure in result.failures)


def test_legacy_quality_gate_is_red_for_current_italian_recall():
    from scripts.gate import Result, run_quality
    result = Result();run_quality(result)
    assert any("it recall" in failure for failure in result.failures)
    assert any("independent multilingual" in failure for failure in result.failures)


def test_score_fields_cannot_be_smuggled_into_an_unscored_test_manifest():
    data = dataset();data["samples"][4]["score"] = .9
    with pytest.raises(ValueError, match="precomputed scores"):
        corpus.validate_dataset(data)


def test_no_false_flags_classifier_cannot_pass_a_positive_recall_requirement():
    rows = [prediction("h", "human", .1), prediction("m", "model", .1)]
    policy = metrics.QualityPolicy(languages=("en",), lengths=("5-24",), registers=("product-copy",),
        conditions=("original",), min_per_class=1, min_groups=1, max_fpr=.9, min_precision=0., min_recall=.5)
    failures = metrics.quality_failures(metrics.metric_report(rows, .5), policy, independent=True)
    assert any("recall" in failure for failure in failures)


def test_a_complete_supported_scope_can_pass_a_declared_policy():
    rows = [prediction("h", "human", .1), prediction("m", "model", .9)]
    policy = metrics.QualityPolicy(languages=("en",), lengths=("5-24",), registers=("product-copy",),
        conditions=("original",), min_per_class=1, min_groups=1, max_fpr=.9, min_precision=0., min_recall=.1)
    assert metrics.quality_failures(metrics.metric_report(rows, .5), policy, independent=True) == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "0.9"])
def test_invalid_scores_cannot_create_a_green_report(value):
    with pytest.raises(ValueError):
        metrics.rates([prediction("invalid", "human", value)], .5)


def test_unicode_variants_preserve_authorship_groups_parent_and_gold_offsets():
    from validation.transforms import unicode_variant, add_unicode_variants
    row = sample("unicode", "mixed", text="A😀BC end", gold_spans=[[2, 4]])
    variant = unicode_variant(row, "zero-width")
    a, b = variant["gold_spans"][0]
    assert variant["text"][a:b] == "B\u200bC"
    assert variant["label"] == row["label"] and variant["groups"] == row["groups"]
    assert variant["parents"] == [row["id"]]
    assert corpus.canonical_text(variant["text"]) == corpus.canonical_text(row["text"])
    data = dataset();augmented = add_unicode_variants(data)
    assert len(augmented["samples"]) == 4 * len(data["samples"])
    assert len(set(corpus.connected_groups(augmented["samples"]).values())) == len(data["samples"])
    assert data["samples"][0]["condition"] == "original"
    with pytest.raises(ValueError, match="duplicate sample"):
        add_unicode_variants(augmented)
