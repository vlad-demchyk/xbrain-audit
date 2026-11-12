"""Existing production detectors under the same benchmark contract and input policy."""
from __future__ import annotations

import hashlib
from importlib import metadata
from pathlib import Path
import sys
from time import perf_counter
import unicodedata

from detectors.factory import DetectorFactory
from lang_detect import guess_language_safe
from models import TextBlock

from .corpus import digest
from .api_adapters import API_METHODS, score_api_samples, validate_api_config
from .local_models import MODEL_METHODS, artifact_identity, score_local_samples, validate_model_config
from .ensemble import score_ensemble_samples, validate_ensemble_config
from .prompt_baseline import LegacyClaudePrompt, request_identity

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ("offline", "heuristic", "embedding", "ensemble") + MODEL_METHODS
REMOTE = ("hybrid", "claude-llm-judge", "claude-legacy-prompt") + API_METHODS
CONFIG_KEYS = {"model_name", "model", "effort", "batch_size", "judge_name", "judge_config"}


def validate_config(config, name=None):
    if name == "ensemble":
        validate_ensemble_config(config)
        return
    if name in MODEL_METHODS:
        validate_model_config(name, config)
        digest(config)
        return
    if name in API_METHODS:
        validate_api_config(name, config)
        digest(config)
        return
    if not isinstance(config, dict) or set(config) - CONFIG_KEYS:
        raise ValueError("benchmark config contains unsupported or secret-bearing fields")
    if "judge_config" in config:
        validate_config(config["judge_config"])
    for key, value in config.items():
        if key != "judge_config" and (isinstance(value, (dict, list)) or type(value) not in (str, int, float, bool)):
            raise ValueError("benchmark config must contain scalar model settings")
    digest(config)  # Also rejects non-finite numbers.


def detector_identity(name: str, config: dict) -> dict:
    validate_config(config, name)
    paths = sorted((ROOT / "detectors").glob("*.py"))
    paths += [ROOT / "models.py", ROOT / "lang_detect.py", ROOT / "unicode_rules.py", Path(__file__)]
    paths += sorted((ROOT / "llm").glob("*.py"))
    paths += sorted((ROOT / "heuristic_rules").glob("*.py"))
    paths += sorted(ROOT.glob("*.py"))
    paths += sorted((ROOT / "validation").glob("*.py"))
    paths += sorted((ROOT / "validation" / "assets").glob("*.json"))
    paths += [ROOT / "scripts" / "benchmark.py", ROOT / "scripts" / "gate.py"]
    files = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
    versions = {}
    for package in ("anthropic", "sentence-transformers", "torch", "transformers", "tokenizers", "safetensors",
                    "numpy", "scikit-learn", "huggingface-hub", "langdetect", "requests"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    versions["python"] = sys.version
    versions["unicode"] = unicodedata.unidata_version
    artifacts = artifact_identity(name, config) if name in MODEL_METHODS else {}
    request = request_identity(name)
    components = []
    if name == "ensemble":
        for member in config["members"]:
            identity = detector_identity(member["detector"], member.get("config", {}))
            components.append({k: identity[k] for k in ("name", "config", "fingerprint", "snapshot_verified", "model_artifacts")})
    return {"name": name, "config": config, "source_hashes": files,
            "dependency_versions": versions, "model_artifacts": artifacts,
            "component_identities": components,
            "request_identity": request,
            "snapshot_verified": (name in ("offline", "heuristic")
                                  or bool(artifacts) and all(a["status"] == "frozen" for a in artifacts.values())
                                  or bool(components) and all(c["snapshot_verified"] for c in components)),
            "fingerprint": digest([name, config, files, versions, artifacts, components, request])}


def inference_policy(samples, name, config, allow_remote):
    validate_config(config, name)
    if name not in LOCAL + REMOTE:
        raise ValueError("method has no classification benchmark adapter; inspect benchmark capabilities")
    if name == "ensemble":
        for member in config["members"]:
            inference_policy(samples, member["detector"], member.get("config", {}), allow_remote)
        return
    if name in REMOTE:
        if not allow_remote or any(r["provenance"]["public_benchmark"] is not True for r in samples):
            raise ValueError("remote inference requires --allow-remote and exclusively public benchmark text")
        if name in API_METHODS:
            return
        settings = config.get("judge_config", {}) if name == "hybrid" else config
        if not isinstance(settings.get("model"), str) or not settings["model"]:
            raise ValueError("remote benchmark requires an explicit model identifier")
        if name == "hybrid" and config.get("judge_name", "claude-llm-judge") != "claude-llm-judge":
            raise ValueError("provider-bound models are not yet pinned for this benchmark")


def score_samples(samples: list[dict], name: str, config: dict, reference: list[dict], *, allow_remote=False) -> list[dict]:
    """One record per sample; errors and unsupported inputs never become negatives."""
    inference_policy(samples, name, config, allow_remote)
    if name == "ensemble":
        return score_ensemble_samples(samples, config, reference, allow_remote=allow_remote)
    if name in API_METHODS:
        return score_api_samples(samples, name, config, allow_remote=allow_remote)
    if name in MODEL_METHODS:
        return score_local_samples(samples, name, config)
    remote = name in REMOTE
    import tempfile
    import json
    with tempfile.TemporaryDirectory(prefix="xaudit-reference-") as temporary:
        settings = dict(config)
        if name == "embedding":
            path = Path(temporary) / "reference.jsonl"
            # The production loader still applies its legacy hash within this
            # file. Every row it can see is nevertheless in reference, never
            # calibration or test; report that selection rather than claiming
            # every reference row became a neighbour.
            path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in reference if r["label"] in ("human", "model")), encoding="utf-8")
            settings.update(corpus_path=str(path), threshold=0.)
        detector = None
        initialization_error = None
        try:
            detector = LegacyClaudePrompt(**settings) if name == "claude-legacy-prompt" else DetectorFactory.create(name, **settings)
        except Exception as exc:
            initialization_error = type(exc).__name__
        results = []
        for row in samples:
            result = {**row, "status": "abstained", "score": None, "spans": [],
                      "latency_ms": None, "cost_usd": None if remote else 0.}
            if initialization_error:
                result.update(status="error", reason=initialization_error)
                results.append(result)
                continue
            hint = guess_language_safe(row["text"])
            if (name in LOCAL and len(row["text"].split()) < 5) or not detector.supports_language(hint):
                result["reason"] = "outside calibrated language/length support"
                results.append(result)
                continue
            if remote and len(" ".join(row["text"].split())) < 20:
                result["reason"] = "below production website wording floor"
                results.append(result)
                continue
            block = TextBlock(block_id=row["id"], page_url="benchmark://" + row["id"],
                              dom_path="", text=row["text"], language_hint=hint)
            started = perf_counter()
            try:
                spans = detector.analyze_block(block)
                if any("error" in (span.details or {}) for span in spans):
                    raise ValueError("detector returned error evidence")
                style = [s for s in spans if (s.details or {}).get("source") != "characters"]
                for span in style:
                    if type(span.start) is not int or type(span.end) is not int or not 0 <= span.start < span.end <= len(block.text):
                        raise ValueError("invalid detector span")
                    if type(span.score) not in (int, float) or not 0 <= span.score <= 1:
                        raise ValueError("invalid detector score")
                result.update(status="checked", score=max((s.score for s in style), default=0.),
                              spans=[{"start": s.start, "end": s.end, "score": s.score} for s in style])
            except Exception as exc:
                result.update(status="error", reason=type(exc).__name__)
            result["latency_ms"] = (perf_counter() - started) * 1000
            results.append(result)
        return results
