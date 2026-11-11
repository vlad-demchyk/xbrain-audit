"""The archived request is isolated, identifiable and uses current evidence validation."""
import json
from types import SimpleNamespace

import pytest

from detectors.claude_llm_judge import ClaudeLLMJudgeDetector
from models import TextBlock
from tests.test_validation_contract import sample
from validation import adapters, prompt_baseline


class Client:
    def __init__(self, payload):
        self.calls = []
        self.payload = payload
        self.messages = SimpleNamespace(create=self.create)
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(self.payload))])


def block():
    return TextBlock(block_id="fixture", page_url="benchmark://fixture", dom_path="", language_hint="en",
                     text="A measured sentence. Another ordinary sentence.")


def payload(quote="A measured sentence."):
    return {"results": [{"block_index": 0, "flags": [{"quote": quote, "score": .7, "reason": "fixture reason"}]}]}


def test_archived_old_request_has_git_origin_and_differs_from_current_prompt_and_schema():
    old = prompt_baseline.request_identity("claude-legacy-prompt")
    new = prompt_baseline.request_identity("claude-llm-judge")
    assert old["source_commit"] == "8f8914aa4408f303da37893257bd385923dfddaa"
    assert old["source_sha256"] == "09a5b4bd69943c8b4df30c678bfbc96c20d42d18c9f80c53c4cbdd282dfc8db5"
    assert old["prompt_sha256"] != new["prompt_sha256"] and old["schema_sha256"] != new["schema_sha256"]
    assert old["input_format"] == "numbered-text" and new["input_format"] == "json-blocks"
    assert old["verdict_contract"] == new["verdict_contract"] == 2


def test_request_variant_retains_model_effort_and_archived_packet_without_changing_new_request():
    old_client = Client(payload())
    old = prompt_baseline.LegacyClaudePrompt(model="fixture-model-version", effort="low")
    old._client = old_client
    flags = old.analyze_block(block())
    assert len(flags) == 1 and flags[0].details["quote_status"] == "verified"
    request = old_client.calls[0]
    packet = json.loads(prompt_baseline.ASSET.read_text(encoding="utf-8"))
    assert request["system"] == packet["system_prompt"]
    assert request["output_config"]["format"]["schema"] == packet["response_schema"]
    assert request["messages"][0]["content"] == "[0] " + block().text
    assert request["model"] == "fixture-model-version" and request["output_config"]["effort"] == "low"
    current_client = Client(payload())
    current = ClaudeLLMJudgeDetector(model="fixture-model-version");current._client = current_client
    current.analyze_block(block())
    assert current_client.calls[0]["system"] != packet["system_prompt"]
    assert json.loads(current_client.calls[0]["messages"][0]["content"])["blocks"][0]["text"] == block().text


@pytest.mark.parametrize("change", [lambda p: p["results"][0]["flags"][0].update(quote="not supplied"),
    lambda p: p["results"][0]["flags"][0].update(score=".9"), lambda p: p.update(results=[])])
def test_legacy_request_cannot_restore_whole_block_fallback_score_coercion_or_omitted_negative(change):
    data = payload();change(data)
    detector = prompt_baseline.LegacyClaudePrompt(model="fixture-version");detector._client = Client(data)
    flags = detector.analyze_block(block())
    assert len(flags) == 1 and "error" in flags[0].details


def test_legacy_benchmark_obeys_remote_policy_and_carries_frozen_request_identity(monkeypatch):
    client = Client(payload())
    monkeypatch.setattr(ClaudeLLMJudgeDetector, "_get_client", lambda self: client)
    row = sample("prompt", text=block().text)
    with pytest.raises(ValueError, match="public benchmark"):
        adapters.score_samples([row], "claude-legacy-prompt", {"model": "fixture-version"}, [], allow_remote=True)
    assert client.calls == []
    row["provenance"]["public_benchmark"] = True
    result = adapters.score_samples([row], "claude-legacy-prompt", {"model": "fixture-version"}, [], allow_remote=True)[0]
    assert result["status"] == "checked" and result["score"] == .7
    identity = adapters.detector_identity("claude-legacy-prompt", {"model": "fixture-version"})
    assert not identity["snapshot_verified"] and identity["request_identity"]["source_commit"]


def test_legacy_variant_is_not_registered_in_production_factory():
    from detectors.factory import DetectorFactory
    with pytest.raises(KeyError, match="Unknown detector"):
        DetectorFactory.create("claude-legacy-prompt")


def test_altered_archive_cannot_keep_claiming_the_original_git_source(monkeypatch):
    packet = json.loads(prompt_baseline.ASSET.read_text(encoding="utf-8"))
    packet["system_prompt"] += " changed after archival"
    monkeypatch.setattr(prompt_baseline, "ASSET", SimpleNamespace(read_text=lambda **_: json.dumps(packet)))
    with pytest.raises(ValueError, match="git-derived packet"):
        prompt_baseline.request_identity("claude-legacy-prompt")
