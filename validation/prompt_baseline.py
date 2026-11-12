"""Archived Claude prompt/schema/input packet under the current strict verdict checker."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from detectors.claude_llm_judge import ClaudeLLMJudgeDetector, _RESPONSE_SCHEMA, _SYSTEM_PROMPT
from .corpus import digest, strict_json

ASSET = Path(__file__).parent / "assets" / "legacy-claude-request.json"
ARCHIVE_DIGEST = "f7548aa7d3d655b5d575f9ff6fc0dc600e1acf3d2bbcf151879713edd08b0a38"


def _legacy_packet():
    packet = strict_json(ASSET.read_text(encoding="utf-8"))
    if digest(packet) != ARCHIVE_DIGEST:
        raise ValueError("archived Claude request no longer matches its git-derived packet")
    return packet


def request_identity(name):
    if name == "claude-legacy-prompt":
        packet = _legacy_packet()
        return {"prompt_sha256": digest(packet["system_prompt"]), "schema_sha256": digest(packet["response_schema"]),
                "input_format": packet["input_format"], "source_commit": packet["source_commit"],
                "source_sha256": packet["source_sha256"], "verdict_contract": 2}
    if name == "claude-llm-judge":
        return {"prompt_sha256": digest(_SYSTEM_PROMPT), "schema_sha256": digest(_RESPONSE_SCHEMA),
                "input_format": "json-blocks", "verdict_contract": 2}
    return {}


class LegacyClaudePrompt(ClaudeLLMJudgeDetector):
    """Benchmark-only request variant, never registered in the production factory."""
    name = "claude-legacy-prompt"

    def _analyze_batch(self, client, batch):
        packet = _legacy_packet()
        def create(**kwargs):
            kwargs["system"] = packet["system_prompt"]
            kwargs["output_config"] = {**kwargs["output_config"],
                                       "format": {"type": "json_schema", "schema": packet["response_schema"]}}
            kwargs["messages"] = [{"role": "user", "content": "\n\n".join(f"[{idx}] {b.text}" for idx, b in enumerate(batch))}]
            return client.messages.create(**kwargs)
        proxy = SimpleNamespace(messages=SimpleNamespace(create=create))
        return super()._analyze_batch(proxy, batch)
