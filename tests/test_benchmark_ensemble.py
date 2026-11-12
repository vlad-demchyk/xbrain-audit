"""Weighted ensembles retain missing coverage and freeze their component identities."""
from copy import deepcopy

import pytest

from tests.test_validation_contract import dataset, prediction, sample, experiment
from validation import adapters, ensemble, protocol


SETTINGS = {"members": [{"detector": "offline"}, {"detector": "heuristic"}], "weights": [1, 3]}


def test_ensemble_aligns_ids_uses_normalized_weights_and_retains_unknown_cost():
    samples = [sample("a"), sample("b")]
    first = [prediction("a", "human", .2), prediction("b", "human", .6)]
    second = [prediction("b", "human", .4), prediction("a", "human", .8, cost_usd=None)]
    result = ensemble.combine_predictions(samples, [first, second], [1, 3])
    assert [r["score"] for r in result] == pytest.approx([.65, .45])
    assert result[0]["cost_usd"] is None and result[1]["cost_usd"] == 0
    assert all(r["latency_ms"] == 20. and not r["localization_supported"] for r in result)
    assert result[0]["component_scores"] == [.2, .8]


@pytest.mark.parametrize("status", ["abstained", "error"])
def test_ensemble_never_renormalizes_away_an_unknown_member(status):
    result = ensemble.combine_predictions([sample("a")], [[prediction("a", "human", .1)],
        [prediction("a", "human", None, status=status)]], [1, 3])[0]
    assert result["status"] == status and result["score"] is None


@pytest.mark.parametrize("weights", [[0, 1], [-1, 1], [True, 1], [float("nan"), 1], [1e308, 1e308], [1]])
def test_invalid_weights_fail_before_inference(weights):
    with pytest.raises(ValueError):
        ensemble.validate_ensemble_config({**SETTINGS, "weights": weights})


def test_recursive_duplicate_unknown_and_secret_member_configuration_is_rejected():
    for members in ([{"detector": "ensemble"}, {"detector": "offline"}],
                    [{"detector": "offline"}] * 2,
                    [{"detector": "unavailable"}, {"detector": "offline"}],
                    [{"detector": "offline", "config": {"api_key": "secret"}}, {"detector": "heuristic"}]):
        with pytest.raises(ValueError):
            ensemble.validate_ensemble_config({"members": members, "weights": [1, 1]})


def test_incomplete_or_invalid_member_output_cannot_hide_failed_coverage():
    for rows in ([], [prediction("wrong", "human", .2)], [prediction("a", "human", .2)] * 2):
        with pytest.raises(ValueError, match="incomplete or duplicated"):
            ensemble.combine_predictions([sample("a")], [[prediction("a", "human", .8)], rows], [1, 1])
    with pytest.raises(ValueError, match="member score"):
        ensemble.combine_predictions([sample("a")], [[prediction("a", "human", float("nan"))],
                                      [prediction("a", "human", .2)]], [1, 1])


def test_remote_member_requires_permission_and_public_text_before_any_inference(monkeypatch):
    monkeypatch.setattr("requests.Session", lambda: pytest.fail("network session created"))
    settings = {"members": [{"detector": "offline"},
        {"detector": "gptzero", "config": {"request_version": "fixture-version"}}], "weights": [1, 1]}
    for allow in (False, True):
        with pytest.raises(ValueError, match="public benchmark"):
            adapters.score_samples([sample("private")], "ensemble", settings, [], allow_remote=allow)


def test_real_offline_ensemble_calibration_and_test_with_frozen_components(tmp_path, monkeypatch):
    monkeypatch.setenv("XAUDIT_VALIDATION_LEDGER", str(tmp_path / "ledger"))
    frozen = protocol.freeze(dataset(), "ensemble", SETTINGS, fixed_threshold=1.)
    assert frozen["detector"]["snapshot_verified"]
    assert len(frozen["detector"]["component_identities"]) == 2
    result = protocol.evaluate(dataset(), frozen)
    assert all(r["status"] == "checked" for r in result["predictions"])
    assert protocol.verify_report(result) == result["metrics"]
    assert not result["quality"]["passed"]
    changed = deepcopy(SETTINGS);changed["weights"] = [3, 1]
    assert adapters.detector_identity("ensemble", changed)["fingerprint"] != frozen["detector"]["fingerprint"]


def test_opaque_remote_component_prevents_a_verified_ensemble_snapshot():
    settings = {"members": [{"detector": "offline"},
        {"detector": "gptzero", "config": {"request_version": "fixture-version"}}], "weights": [1, 1]}
    assert not adapters.detector_identity("ensemble", settings)["snapshot_verified"]


def test_embedding_ensemble_records_its_reference_selection_instead_of_claiming_unused(experiment):
    settings = {"members": [{"detector": "offline"}, {"detector": "embedding", "config": {"model_name": "fixture-model"}}],
                "weights": [1, 1]}
    frozen = protocol.freeze(dataset(), "ensemble", settings)
    assert frozen["reference_selection"] == "legacy text hash within reference for embedding component"
    assert not frozen["detector"]["snapshot_verified"]
