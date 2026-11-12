"""Explicit public-benchmark API inference, typed vendor scores and verified ranges."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import re
from time import monotonic, perf_counter, sleep
from uuid import uuid4

import requests

from .corpus import canonical_text, digest, strict_json

API_METHODS = ("copyleaks", "pangram", "gptzero")
API_SETTINGS = {"copyleaks": {"expected_model_version", "sensitivity"},
                "pangram": {"expected_model_version", "model", "poll_timeout_seconds"},
                "gptzero": {"expected_model_version", "request_version"}}
ENDPOINTS = {"copyleaks": "https://api.copyleaks.com/v2/writer-detector",
             "pangram": "https://text.external-api.pangram.com/task",
             "gptzero": "https://api.gptzero.me/v2/predict/text"}
KEY_ENV = {"copyleaks": "COPYLEAKS_ACCESS_TOKEN", "pangram": "PANGRAM_API_KEY", "gptzero": "GPTZERO_API_KEY"}


def validate_api_config(name, config):
    if name not in API_METHODS or not isinstance(config, dict) or set(config) - API_SETTINGS[name]:
        raise ValueError("invalid API benchmark configuration")
    if name == "pangram" and (not isinstance(config.get("model"), str) or not config["model"] or config["model"] in ("default", "latest")):
        raise ValueError("Pangram requires an explicit model selector")
    if name == "gptzero" and (not isinstance(config.get("request_version"), str) or not config["request_version"]):
        raise ValueError("GPTZero requires an explicit request version")
    if name in ("pangram", "copyleaks") and not config.get("expected_model_version"):
        raise ValueError("this API benchmark requires an expected response model version")
    for key in ("model", "expected_model_version", "request_version"):
        if key in config and (not isinstance(config[key], str) or not config[key].strip() or len(config[key]) > 120):
            raise ValueError(f"invalid {key}")
    if "sensitivity" in config and (type(config["sensitivity"]) is not int or config["sensitivity"] not in (1, 2, 3)):
        raise ValueError("invalid Copyleaks sensitivity")
    timeout = config.get("poll_timeout_seconds", 30)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 1 <= timeout <= 120:
        raise ValueError("poll_timeout_seconds must be between 1 and 120")


def probability(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("invalid vendor 0..1 score")
    return float(value)


def _distribution(data, keys):
    if not isinstance(data, dict):
        raise ValueError("vendor distribution must be an object")
    values = {key: probability(data[key]) for key in keys}
    if not math.isclose(sum(values.values()), 1., abs_tol=.001):
        raise ValueError("vendor fractions/probabilities do not sum to one")
    return values


def _unique_quote(text, quote):
    if not isinstance(quote, str) or not quote:
        return None
    first = text.find(quote)
    if first < 0 or text.find(quote, first + 1) >= 0:
        return None
    return first, first + len(quote)


def quote_range(original, returned, quote, start=None, end=None):
    """Provider offsets select only an exact quote; unknown units never guess."""
    if not isinstance(quote, str) or not quote:
        return None
    candidates = set()
    if returned == original and type(start) is int and type(end) is int and 0 <= start < end:
        if end <= len(original) and original[start:end] == quote:
            candidates.add((start, end))
        offsets = {0: 0}
        units = 0
        for index, char in enumerate(original):
            units += 2 if ord(char) > 0xFFFF else 1
            offsets[units] = index + 1
        if start in offsets and end in offsets and original[offsets[start]:offsets[end]] == quote:
            candidates.add((offsets[start], offsets[end]))
    if len(candidates) == 1:
        return next(iter(candidates))
    if len(candidates) > 1:
        return None
    return _unique_quote(original, quote)


def _base_response(data, version, score, semantics):
    if not isinstance(data, dict):
        raise ValueError("vendor response must be an object")
    return {"status": "checked", "score": probability(score), "spans": [],
            "localization_supported": False, "score_semantics": semantics,
            "actual_model_version": version if isinstance(version, str) and version else None,
            "response_sha256": digest(data), "cost_usd": None}


def parse_copyleaks(data, text):
    summary = _distribution(data["summary"], ("human", "ai"))
    result = _base_response(data, data.get("modelVersion"), summary["ai"], "vendor summary.ai; separate from section confidence")
    sections = data.get("results")
    if not isinstance(sections, list):
        raise ValueError("Copyleaks results array is missing")
    result["section_evidence"] = []
    # The API exposes starts/lengths but does not establish their Unicode
    # unit or echo the section quote. Keep ranges as vendor evidence; do not
    # invent a Python span for an emoji-containing input.
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("invalid Copyleaks section")
        label = section.get("classification")
        if type(label) is not int or label not in (1, 2):
            raise ValueError("unknown Copyleaks classification")
        confidence = probability(section["probability"])
        matches = section.get("matches", [])
        if not isinstance(matches, list):
            raise ValueError("invalid Copyleaks matches")
        for match in matches:
            if not isinstance(match, dict) or not isinstance(match.get("text"), dict):
                raise ValueError("invalid Copyleaks match")
            chars = match.get("text", {}).get("chars", {})
            if not isinstance(chars, dict):
                raise ValueError("invalid Copyleaks character ranges")
            starts, lengths = chars.get("starts", []), chars.get("lengths", [])
            if not isinstance(starts, list) or not isinstance(lengths, list) or len(starts) != len(lengths):
                raise ValueError("invalid Copyleaks ranges")
            for start, length in zip(starts, lengths):
                if type(start) is not int or type(length) is not int or start < 0 or length < 1:
                    raise ValueError("invalid Copyleaks range")
                result["section_evidence"].append({"classification": label, "confidence": confidence,
                    "start": start, "length": length, "coordinate_system": "vendor characters, unit unverified"})
    scanned = data.get("scannedDocument") or {}
    if not isinstance(scanned, dict):
        raise ValueError("invalid Copyleaks scanned document")
    result["usage"] = {key: scanned[key] for key in ("actualCredits", "credits", "expectedCredits", "totalWords")
                      if key in scanned and type(scanned[key]) in (int, float) and math.isfinite(scanned[key]) and scanned[key] >= 0}
    return result


def parse_pangram(data, text):
    if data.get("stage") != "STAGE_SUCCESS":
        raise ValueError("Pangram result is not successful")
    returned = data.get("text")
    if not isinstance(returned, str) or canonical_text(returned) != canonical_text(text):
        raise ValueError("Pangram returned a different document")
    fractions = _distribution(data, ("fraction_ai", "fraction_ai_assisted", "fraction_human"))
    result = _base_response(data, data.get("version"), fractions["fraction_ai"], "fraction labelled AI-generated, not document probability")
    result.update(fractions=fractions, provider_text_sha256=hashlib.sha256(returned.encode()).hexdigest(),
                  assistance_evidence=[], localization_supported=True)
    windows = data.get("windows")
    if not isinstance(windows, list):
        raise ValueError("Pangram windows array is missing")
    for window in windows:
        if not isinstance(window, dict):
            raise ValueError("invalid Pangram window")
        label = window.get("label")
        if label not in ("AI-Generated", "AI-Assisted", "Human Written"):
            raise ValueError("unknown Pangram window label")
        value = probability(window["ai_assistance_score"])
        position = quote_range(text, returned, window.get("text"), window.get("start_index"), window.get("end_index"))
        if position is None:
            result["localization_supported"] = False
            continue
        start, end = position
        evidence = {"start": start, "end": end, "score": value, "score_semantics": "ai_assistance_score",
                    "selection": "provider-label", "selected": label == "AI-Generated", "label": label,
                    "confidence": window.get("confidence"), "mapping": "verified exact quote"}
        if label == "AI-Generated":
            result["spans"].append(evidence)
        elif label == "AI-Assisted":
            result["assistance_evidence"].append(evidence)
    return result


def parse_gptzero(data, text):
    documents = data.get("documents")
    if not isinstance(documents, list) or len(documents) != 1 or not isinstance(documents[0], dict):
        raise ValueError("GPTZero must return exactly one document")
    doc = documents[0]
    values = _distribution(doc["class_probabilities"], ("human", "ai", "mixed"))
    result = _base_response(data, doc.get("model_version") or data.get("version"), values["ai"], "vendor class_probabilities.ai")
    result["class_probabilities"] = values
    if doc.get("document_classification") not in ("HUMAN_ONLY", "MIXED", "AI_ONLY"):
        raise ValueError("unknown GPTZero document classification")
    sentences = doc.get("sentences")
    if not isinstance(sentences, list):
        return result  # A document score alone does not supply localization.
    result["localization_supported"] = True
    for sentence in sentences:
        if not isinstance(sentence, dict):
            raise ValueError("invalid GPTZero sentence")
        highlight = sentence.get("highlight_sentence_for_ai")
        if type(highlight) is not bool:
            result["localization_supported"] = False
            continue
        if not highlight:
            continue
        if doc["document_classification"] == "HUMAN_ONLY":
            result["localization_supported"] = False
            continue
        position = _unique_quote(text, sentence.get("sentence"))
        if position is None:
            result["localization_supported"] = False
            continue
        start, end = position
        result["spans"].append({"start": start, "end": end, "score": values["ai"],
                               "selection": "provider-label", "selected": True,
                               "mapping": "verified unique sentence"})
    return result


def _request(session, method, url, headers, *, timeout=(5, 30), **kwargs):
    response = session.request(method, url, headers=headers, timeout=timeout, allow_redirects=False, **kwargs)
    if response.status_code != 200:
        raise ValueError(f"vendor HTTP {response.status_code}")
    data = strict_json(response.text)
    if not isinstance(data, dict):
        raise ValueError("vendor JSON must be an object")
    return data


def _pangram(session, headers, text, config, credential):
    directory = Path(os.environ.get("XANALYZE_API_JOB_CACHE", str(Path.home() / ".xanalyze" / "validation" / "api-jobs")))
    # Partition handles by credential without persisting the credential.
    key = digest(["pangram", config["model"], hashlib.sha256(text.encode()).hexdigest(), credential])
    path = directory / (key + ".json")
    if path.exists():
        task = strict_json(path.read_text(encoding="utf-8"))
        task_id = task["task_id"]
    else:
        directory.mkdir(parents=True, exist_ok=True)
        submission = path.with_suffix(".submitting")
        try:
            with submission.open("x") as marker:
                marker.write("submission outcome must be resolved before retry")
        except FileExistsError:
            return {"submission_unresolved": True}
        task = _request(session, "POST", ENDPOINTS["pangram"], headers,
                        json={"text": text, "model": config["model"], "public_dashboard_link": False})
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", task_id):
            raise ValueError("invalid Pangram task ID")
        from .protocol import write_new
        write_new(path, {"task_id": task_id})
        submission.unlink()
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", task_id):
        raise ValueError("invalid cached task ID")
    deadline = monotonic() + config.get("poll_timeout_seconds", 30)
    while monotonic() < deadline:
        remaining = max(.001, deadline - monotonic())
        data = _request(session, "GET", ENDPOINTS["pangram"] + "/" + task_id, headers,
                        timeout=(min(5, remaining), min(30, remaining)))
        if data.get("task_id", task_id) != task_id:
            raise ValueError("Pangram returned another task")
        stage = data.get("stage")
        if stage == "STAGE_SUCCESS":
            return data
        if stage == "STAGE_FAILED":
            raise ValueError("Pangram task failed")
        if not isinstance(stage, str) or not stage.startswith("STAGE_"):
            raise ValueError("unknown Pangram task state")
        sleep(min(1., max(0., deadline - monotonic())))
    return {"pending_task_id": task_id}


def score_api_samples(samples, name, config, *, allow_remote=False, session=None):
    validate_api_config(name, config)
    if not allow_remote or any(r.get("provenance", {}).get("public_benchmark") is not True for r in samples):
        raise ValueError("API inference requires explicit permission and public benchmark text")
    credential = os.environ.get(KEY_ENV[name], "")
    own_session = session is None
    session = session or requests.Session()
    results = []
    try:
        for row in samples:
            result = {**row, "status": "abstained", "score": None, "spans": [], "cost_usd": None,
                      "localization_supported": False, "latency_ms": None,
                      "input_sha256": hashlib.sha256(row["text"].encode()).hexdigest()}
            if not credential:
                result["reason"] = f"{KEY_ENV[name]} not configured"
                results.append(result)
                continue
            if name == "copyleaks" and not 255 <= len(row["text"]) <= 100000:
                result["reason"] = "outside Copyleaks 255..100000 character range"
                results.append(result)
                continue
            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            headers.update({"Authorization": "Bearer " + credential} if name == "copyleaks" else {"x-api-key": credential})
            started = perf_counter()
            try:
                if name == "copyleaks":
                    body = {"text": row["text"], "sandbox": False, "explain": False,
                            "sensitivity": config.get("sensitivity", 2)}
                    data = _request(session, "POST", ENDPOINTS[name] + "/" + str(uuid4()) + "/check", headers, json=body)
                    parsed = parse_copyleaks(data, row["text"])
                elif name == "pangram":
                    data = _pangram(session, headers, row["text"], config, credential)
                    if data.get("pending_task_id") or data.get("submission_unresolved"):
                        result.update(reason="Pangram task pending or submission unresolved; never automatically resubmit",
                                      task_id=data.get("pending_task_id"))
                        results.append(result)
                        continue
                    parsed = parse_pangram(data, row["text"])
                else:
                    data = _request(session, "POST", ENDPOINTS[name], headers,
                                    json={"document": row["text"], "version": config["request_version"]})
                    parsed = parse_gptzero(data, row["text"])
                expected = config.get("expected_model_version")
                result.update(actual_model_version=parsed["actual_model_version"], response_sha256=parsed["response_sha256"])
                if expected and parsed["actual_model_version"] != expected:
                    raise ValueError("vendor model version changed or absent")
                result.update(parsed, captured_at=datetime.now(timezone.utc).isoformat())
            except (ValueError, TypeError, KeyError, requests.RequestException, OSError) as exc:
                # Request exceptions can embed credentials and request data.
                result.update(status="error", reason=type(exc).__name__)
            finally:
                result["latency_ms"] = (perf_counter() - started) * 1000
            results.append(result)
    finally:
        if own_session:
            session.close()
    return results
