"""Freeze calibration decisions before test access and record irreversible exposure."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import os
from pathlib import Path

from .adapters import detector_identity, inference_policy, score_samples
from .corpus import canonical_text, digest, historical_overlap, strict_json, validate_dataset
from .metrics import QualityPolicy, metric_report, quality_failures, rates

ROOT = Path(__file__).resolve().parent.parent


def ledger_dir() -> Path:
    override = os.environ.get("XANALYZE_VALIDATION_LEDGER")
    return Path(override) if override else Path.home() / ".xanalyze" / "validation" / "test-access"


def _test_paths(samples):
    return {digest(canonical_text(row["text"])): ledger_dir() / (digest(canonical_text(row["text"])) + ".json") for row in samples}


def write_new(path, payload):
    import json
    encoded = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(encoded)


def choose_threshold(calibration: list[dict], target_fpr: float, *, fixed=None) -> float:
    if type(target_fpr) not in (int, float) or not 0 <= target_fpr <= 1:
        raise ValueError("invalid calibration FPR target")
    if not any(r["label"] == "human" and r["status"] == "checked" for r in calibration) or not any(r["label"] == "model" and r["status"] == "checked" for r in calibration):
        raise ValueError("calibration needs measured human and model samples")
    import math
    candidates = {0., 1., .33} if fixed is None else {fixed}
    if fixed is None:
        for row in calibration:
            if row["status"] == "checked":
                candidates.add(row["score"])
                after = math.nextafter(row["score"], math.inf)
                if after <= 1:
                    candidates.add(after)
    valid = []
    for threshold in candidates:
        result = rates(calibration, threshold)
        upper = result["fpr_bounds_with_abstention"][1]
        if upper is not None and upper <= target_fpr:
            valid.append((result["recall"], threshold))
    if not valid:
        raise ValueError("no calibration threshold meets the FPR target including abstention")
    return max(valid)[1]


def freeze(data: dict, detector="offline", config=None, policy=None, *, allow_remote=False, fixed_threshold=None) -> dict:
    groups = validate_dataset(data)
    policy = policy or QualityPolicy()
    config = config or {}
    test = [r for r in data["samples"] if r["split"] == "test"]
    calibration = [r for r in data["samples"] if r["split"] == "calibration"]
    reference = [r for r in data["samples"] if r["split"] == "reference"]
    if not test or not calibration or not reference:
        raise ValueError("reference, calibration and test must all be populated")
    if any(path.exists() for path in _test_paths(test).values()):
        raise ValueError("test text was already exposed; cannot refit on this test")
    overlap = historical_overlap(test, ROOT / "corpus")
    if overlap:
        raise ValueError("test overlaps historical corpus: " + ", ".join(overlap[:10]))
    identity = detector_identity(detector, config)
    scored = score_samples(calibration, detector, config, reference, allow_remote=allow_remote)
    if digest(identity) != digest(detector_identity(detector, config)):
        raise ValueError("detector/model artifact changed during calibration")
    threshold = choose_threshold(scored, policy.max_fpr, fixed=fixed_threshold)
    calibration_report = metric_report([{**r, "group_id": groups[r["id"]]} for r in scored], threshold, policy.prevalence)
    frozen = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
              "dataset_id": data["dataset_id"], "dataset_sha256": digest(data),
              "purpose": data["purpose"], "detector": identity,
              "threshold": threshold, "policy": asdict(policy), "reference_sha256": digest(reference),
              "reference_selection": ("legacy text hash within reference" if detector == "embedding" else
                  "legacy text hash within reference for embedding component" if detector == "ensemble"
                  and any(m["detector"] == "embedding" for m in config["members"]) else "not used"),
              "calibration_report": calibration_report, "test_scores_read": False}
    frozen["calibration_constraint"] = {"target_fpr": policy.max_fpr,
        "selection": "fixed threshold" if fixed_threshold is not None else "maximum recall under worst-case calibration FPR"}
    frozen["test_sample_hashes"] = {r["id"]: digest(r) for r in test}
    frozen["test_sample_fields"] = {r["id"]: sorted(r) for r in test}
    frozen["protocol_sha256"] = digest(frozen)
    return frozen


def verify_protocol(data, frozen):
    groups = validate_dataset(data)
    if frozen.get("schema_version") != 1 or frozen.get("test_scores_read") is not False:
        raise ValueError("invalid frozen protocol")
    claimed = frozen.get("protocol_sha256")
    if claimed != digest({k: v for k, v in frozen.items() if k != "protocol_sha256"}):
        raise ValueError("protocol changed after freezing")
    if frozen["dataset_sha256"] != digest(data):
        raise ValueError("dataset changed after freezing")
    identity = detector_identity(frozen["detector"]["name"], frozen["detector"]["config"])
    if digest(identity) != digest(frozen["detector"]):
        raise ValueError("detector/prompt code changed after freezing")
    QualityPolicy(**frozen["policy"])
    return groups


def evaluate(data, frozen, *, allow_remote=False):
    groups = verify_protocol(data, frozen)
    test = [r for r in data["samples"] if r["split"] == "test"]
    reference = [r for r in data["samples"] if r["split"] == "reference"]
    inference_policy(test, frozen["detector"]["name"], frozen["detector"]["config"], allow_remote)
    # Claim every text before inference. A crashed/failed run still exposed
    # the test; retrying with a newly fitted threshold is not independent.
    access = {"protocol_sha256": frozen["protocol_sha256"], "dataset_sha256": digest(data),
              "accessed_at": datetime.now(timezone.utc).isoformat(), "purpose": data["purpose"]}
    paths = _test_paths(test)
    if any(path.exists() for path in paths.values()):
        raise ValueError("locked test has already been consumed")
    for path in paths.values():
        write_new(path, access)
    return _evaluate_claimed(data, frozen, groups, access, allow_remote=allow_remote)


def _evaluate_claimed(data, frozen, groups, access, *, allow_remote=False, comparison_sha256=None):
    """Score a protocol after its test was claimed by a single run or frozen comparison."""
    test = [r for r in data["samples"] if r["split"] == "test"]
    reference = [r for r in data["samples"] if r["split"] == "reference"]
    scored = score_samples(test, frozen["detector"]["name"], frozen["detector"]["config"], reference, allow_remote=allow_remote)
    if digest(detector_identity(frozen["detector"]["name"], frozen["detector"]["config"])) != digest(frozen["detector"]):
        raise ValueError("detector/model artifact changed during test inference")
    scored = [{**r, "group_id": groups[r["id"]]} for r in scored]
    policy = QualityPolicy(**frozen["policy"])
    metrics = metric_report(scored, frozen["threshold"], policy.prevalence)
    failures = quality_failures(metrics, policy, independent=data["purpose"] == "validation")
    if not frozen["detector"]["snapshot_verified"]:
        failures.append("external model weights/response identity not fully pinned")
    report = {"schema_version": 1, "protocol": frozen, "metrics": metrics,
              "test_access": access,
              "predictions": scored, "quality": {"passed": not failures, "failures": failures},
              "completed_at": datetime.now(timezone.utc).isoformat(),
              "limitations": ["Provenance is an explicit supplier assertion, not automatically verified authorship.",
                "Unknown training-data exposure of pretrained models is not certified absent.",
                "Group event intervals are not document-level population intervals."]}
    if comparison_sha256 is not None:
        report["comparison_sha256"] = comparison_sha256
    report["report_sha256"] = digest(report)
    return report


def verify_report(report: dict) -> dict:
    """Recompute metrics and source groups; a saved 'passed' flag proves nothing."""
    if report.get("schema_version") != 1 or report.get("report_sha256") != digest({k: v for k, v in report.items() if k != "report_sha256"}):
        raise ValueError("benchmark report changed or is incomplete")
    frozen = report["protocol"]
    if frozen["protocol_sha256"] != digest({k: v for k, v in frozen.items() if k != "protocol_sha256"}):
        raise ValueError("frozen protocol changed")
    identity = detector_identity(frozen["detector"]["name"], frozen["detector"]["config"])
    if digest(identity) != digest(frozen["detector"]):
        raise ValueError("benchmark describes different code/dependencies")
    originals = []
    seen = set()
    for row in report["predictions"]:
        key = row["id"]
        if key in seen or key not in frozen["test_sample_hashes"]:
            raise ValueError("duplicate/unexpected benchmark prediction")
        seen.add(key)
        original = {field: row[field] for field in frozen["test_sample_fields"][key]}
        if digest(original) != frozen["test_sample_hashes"][key]:
            raise ValueError("test sample changed")
        originals.append(original)
    if seen != set(frozen["test_sample_hashes"]):
        raise ValueError("benchmark predictions are incomplete")
    groups = validate_dataset({"schema_version": 1, "dataset_id": frozen["dataset_id"],
                               "purpose": frozen["purpose"], "samples": originals})
    for row in report["predictions"]:
        if row["group_id"] != groups[row["id"]]:
            raise ValueError("benchmark source groups changed")
    for path in _test_paths(originals).values():
        access = strict_json(path.read_text(encoding="utf-8"))
        if report.get("test_access") != access:
            raise ValueError("test access evidence changed")
        single = (access.get("protocol_sha256") == frozen["protocol_sha256"]
                  and "comparison_sha256" not in access and "comparison_sha256" not in report)
        comparison = (isinstance(access.get("comparison_sha256"), str)
                      and access["comparison_sha256"] == report.get("comparison_sha256")
                      and frozen["protocol_sha256"] in access.get("protocol_sha256s", []))
        if not (single or comparison) or access.get("dataset_sha256") != frozen["dataset_sha256"]:
            raise ValueError("test access record belongs to another protocol")
    policy = QualityPolicy(**frozen["policy"])
    computed = metric_report(report["predictions"], frozen["threshold"], policy.prevalence)
    if digest(computed) != digest(report["metrics"]):
        raise ValueError("benchmark metrics changed")
    return computed
