"""Passive benchmark prerequisites; research availability and provenance stay separate."""
from __future__ import annotations

from importlib import metadata
import os

from .adapters import LOCAL, REMOTE, validate_config
from .api_adapters import API_METHODS, KEY_ENV
from .local_models import MODEL_METHODS, artifact_identity

REVIEWED_AT = "2026-10-14"
RESEARCH = {
    "adadetectgpt": {
        "source": "https://github.com/Mamba413/AdaDetectGPT",
        "revision": "ff83b52efd0d2f81afac1692d4ea0765658bb6e0",
        "requirements": ["frozen scoring/reference models with aligned tokenizers",
                         "frozen B-spline witness and its configuration; learned on reference only",
                         "CUDA for the reviewed upstream inference script"],
        "limitations": ["upstream CLI hard-codes CUDA and has a sampling-model argument typo",
                        "pretrained witness coefficients are tied to the author's setup",
                        "target uk/it/en website quality has not been measured"],
    },
    "prossd": {
        "source": "https://github.com/RuoChoXio/ProSSD",
        "revision": "988125b1bc11213314a5f10dd21cb4db75729625",
        "paper": "https://aclanthology.org/2026.acl-long.638/",
        "requirements": ["frozen encoder/tokenizer", "supervised projection.npy from reference human/model pairs",
                         "frozen style library distributions from reference, not calibration/test",
                         "spaCy en_core_web_sm POS model in the reviewed implementation"],
        "limitations": ["upstream POS pipeline is English; uk/it support is unverified",
                        "upstream library uses pickle and its training-derived threshold",
                        "XBrain Audit would freeze a calibration threshold without importing an upstream test optimum"],
    },
}
WATERMARK = {
    "name": "claude-official-watermark", "channel": "provenance",
    "adapter_implemented": False, "availability": "private-preview",
    "inference_checked": False, "authorship_score": None,
    "source": "https://www.anthropic.com/news/claude-text-watermark",
    "source_updated_at": "2026-09-01", "reviewed_at": REVIEWED_AT,
    "blockers": ["approved private-preview access and documented endpoint contract are not configured"],
    "interpretation": "Claude involvement only; absence does not establish human authorship or exclude other AI",
}


def _runtime():
    versions = {}
    for package in ("torch", "transformers", "tokenizers", "safetensors", "requests", "spacy", "en-core-web-sm"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    cuda = mps = mps_built = None
    if versions["torch"]:
        try:
            import torch
            cuda = bool(torch.cuda.is_available())
            mps_built = bool(torch.backends.mps.is_built())
            mps = bool(torch.backends.mps.is_available())
        except (ImportError, OSError):
            pass
    return {"dependencies": versions, "cuda_available": cuda, "mps_available": mps, "mps_built": mps_built}


def method_capabilities(name=None, config=None):
    """Check supplied configuration and artifact presence without running models/API."""
    names = LOCAL + REMOTE + tuple(RESEARCH) + (WATERMARK["name"],)
    if name is not None and name not in names:
        raise ValueError("unknown benchmark method")
    if config is not None and name is None:
        raise ValueError("capability configuration requires --detector")
    if config is not None and name not in LOCAL + REMOTE:
        raise ValueError("research/provenance methods have no inference configuration contract yet")
    runtime = _runtime()
    classifications = []
    for method in LOCAL + REMOTE + tuple(RESEARCH):
        if name is not None and method != name:
            continue
        item = {"name": method, "channel": "classification", "inference_checked": False,
                "accuracy_validation": "not measured on a fresh confirmed corpus", "blockers": []}
        if method in RESEARCH:
            item.update(RESEARCH[method], adapter_implemented=False, status="research-only", reviewed_at=REVIEWED_AT)
            item["blockers"] = ["experimental adapter and frozen reference-trained artifacts are not supplied"]
            if method == "adadetectgpt" and runtime["cuda_available"] is not True:
                item["blockers"].append("reviewed upstream inference requires CUDA; unavailable here")
            if method == "prossd" and not runtime["dependencies"]["en-core-web-sm"]:
                item["blockers"].append("reviewed upstream English POS model is not installed")
        else:
            item.update(adapter_implemented=True, status="implemented", remote=method in REMOTE)
            if method == name and config is not None:
                validate_config(config, method)
            if method == "ensemble":
                item["requirements"] = ["declared component configurations and positive weights", "calibration threshold"]
                item["remote"] = any(m["detector"] in REMOTE for m in config["members"]) if name == method and config is not None else None
                if name != method or config is None:
                    item["blockers"].append("ensemble configuration not supplied")
            if method in MODEL_METHODS:
                item["requirements"] = ["local safetensors/config/tokenizer snapshot", "calibration threshold",
                                        "aligned tokenizers for paired causal models"]
                if method == name and config is not None:
                    item["model_artifacts"] = artifact_identity(method, config)
                    if not all(a["status"] == "frozen" for a in item["model_artifacts"].values()):
                        item["blockers"].append("local model artifacts unavailable")
                else:
                    item["blockers"].append("local model configuration not supplied")
                for package in ("torch", "transformers", "safetensors"):
                    if not runtime["dependencies"][package]:
                        item["blockers"].append(package + " not installed")
                if name == method and config is not None:
                    device = config.get("device", "cpu")
                    item["inference_device"] = device
                    item["statistics_device"] = "cpu" if device == "mps" else device
                    item["statistics_dtype"] = "float64"
                    if device in ("cuda", "mps") and runtime.get(device + "_available") is not True:
                        item["blockers"].append("requested " + device + " device unavailable")
            if method in REMOTE:
                item["requirements"] = ["explicit --allow-remote", "public benchmark text only", "pinned request configuration"]
                if method in API_METHODS:
                    item["credential_configured"] = bool(os.environ.get(KEY_ENV[method]))
                    item["snapshot_verified"] = False  # Version strings cannot inspect opaque vendor weights.
                    if not item["credential_configured"]:
                        item["blockers"].append(KEY_ENV[method] + " not configured")
                    if config is None:
                        item["blockers"].append("explicit vendor version configuration not supplied")
                else:
                    if name != method or config is None:
                        item["blockers"].append("explicit judge model configuration not supplied")
                    if method in ("claude-llm-judge", "claude-legacy-prompt"):
                        item["credential_configured"] = bool(os.environ.get("ANTHROPIC_API_KEY"))
                        if not item["credential_configured"]:
                            item["blockers"].append("ANTHROPIC_API_KEY not configured")
        classifications.append(item)
    return {"schema_version": 1, "runtime": runtime, "classification_methods": classifications,
            "provenance_signals": [dict(WATERMARK)] if name in (None, WATERMARK["name"]) else [],
            "network_calls": 0, "model_loads": 0}
