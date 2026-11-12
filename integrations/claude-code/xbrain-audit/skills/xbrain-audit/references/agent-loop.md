# The agent loop for AI-written copy

`agent-scan` does the cheap offline reading and hands the agent only what is worth a judgement; `agent-judge` takes the agent's verdicts back and writes the same report a model-judged run would. No account is billed: the agent is the judge.

## Candidates only (default)

```bash
xaudit agent-scan PATHS --json > candidates.json
```

The payload carries `candidates` (each with `block_id`, `file`, `line`, `text`, the offline `score` and what fired), `detection_rules` and an `instruction`. Judge each candidate against the rules and write a JSON list:

```json
[{"block_id": "…", "score": 0.8, "reason": "which rules fired", "file": "src/About.tsx", "line": 7, "text": "…"}]
```

`score` is 0.0 for human, 1.0 for AI. Echo `file`, `line` and `text`: a `block_id` is minted per run, and those three fields are what lets a verdict match when the scan is re-run in a new process. Then:

```bash
xaudit agent-judge PATHS --judgments verdicts.json --json > final.json
```

(`--judgments` omitted reads stdin.)

## Hybrid: judge and read everything

```bash
xaudit agent-scan PATHS --full --json > all.json
```

Adds `blocks`: every passage. Return `{"judgments": [...], "agent_findings": [...], "blocks": [...]}`, where an agent finding is `{"block_id", "quote" (verbatim), "score", "reason"}` for a passage the offline pass missed, and `blocks` is passed through unchanged. Merge with `agent-judge PATHS --judgments FILE --hybrid`.

## What a verdict is not

A high score is evidence about wording, not proof of authorship. Say so in a report, and quote the passage and the reason rather than a percentage alone.
