"""Precision of the audit rules on real audits, from a person's labels (T-1963).

`corpus/audit/verdicts.jsonl` holds shapes; this measures sites. A person
labels the findings of real audits as true or false, once, and this counts
per rule how many of the labelled ones were right.

The number is never shown alone. Precision from three labelled findings is a
guess with a percent sign, so every line carries `n`, and below
`MIN_LABELLED` the line says the rule is not measured yet instead of
printing a number. Nothing here changes a rule's severity: a low precision is
a reason for a person to look, not a reason for the tool to stop reporting.

Labels live in a JSON-lines file of their own, keyed by the same fingerprint
`.xaudit-ignore` uses, so a label survives a re-run of the audit:

    {"fingerprint": "…", "verdict": true, "reason": "…"}

`template_records` writes that file with every distinct finding of the given
audits and `verdict: null`, which is the work list for whoever labels them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from suppression import fingerprint

#: Below this many labelled findings a rule is reported as not measured.
MIN_LABELLED = 5


def _issues_of(audit: dict) -> list:
    return [issue for issue in audit.get("issues", [])
            if isinstance(issue, dict) and issue.get("rule_id")]


def finding_fingerprint(issue: dict) -> str:
    """The fingerprint `suppression.issue_fingerprint` gives the same issue."""
    return fingerprint(issue.get("source", ""),
                       issue.get("snippet") or issue.get("selector") or "",
                       issue.get("rule_id", ""))


def load_audits(paths) -> list:
    audits = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            audits.append(json.load(handle))
    return audits


def load_labels(path) -> dict:
    """`fingerprint -> True/False`. Unlabelled (`null`) lines are skipped."""
    labels = {}
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            record = json.loads(line)
            verdict = record.get("verdict")
            if verdict is None:
                continue
            if not isinstance(verdict, bool):
                raise ValueError(f"line {number}: verdict must be true, false or null")
            labels[record["fingerprint"]] = verdict
    return labels


@dataclass
class RulePrecision:
    rule: str
    #: Distinct findings of this rule across the audits.
    found: int = 0
    true: int = 0
    false: int = 0
    sources: set = field(default_factory=set)

    @property
    def labelled(self) -> int:
        return self.true + self.false

    @property
    def precision(self) -> float | None:
        """None until `MIN_LABELLED` findings are labelled."""
        if self.labelled < MIN_LABELLED:
            return None
        return self.true / self.labelled


def measure(audits, labels: dict) -> list:
    """One `RulePrecision` per rule that found anything, worst first."""
    by_rule: dict = {}
    seen: set = set()
    for audit in audits:
        for issue in _issues_of(audit):
            key = finding_fingerprint(issue)
            if key in seen:
                continue  # the same finding in two audits is one finding
            seen.add(key)
            row = by_rule.setdefault(issue["rule_id"], RulePrecision(issue["rule_id"]))
            row.found += 1
            row.sources.add(issue.get("source", ""))
            if key in labels:
                if labels[key]:
                    row.true += 1
                else:
                    row.false += 1

    def order(row):
        measured = row.precision is not None
        return (not measured, row.precision if measured else 0, -row.found, row.rule)

    return sorted(by_rule.values(), key=order)


def template_records(audits, labels: dict | None = None) -> list:
    """Every distinct finding as a label line, labelled ones keeping theirs."""
    labels = labels or {}
    records, seen = [], set()
    for audit in audits:
        for issue in _issues_of(audit):
            key = finding_fingerprint(issue)
            if key in seen:
                continue
            seen.add(key)
            records.append({
                "fingerprint": key,
                "rule": issue["rule_id"],
                "severity": issue.get("severity", ""),
                "source": issue.get("source", ""),
                "snippet": (issue.get("snippet") or issue.get("selector") or "")[:200],
                "verdict": labels.get(key),
                "reason": "",
            })
    return records


def render(rows, *, pages: int | None = None) -> str:
    """A plain table: one rule per line, `n` beside every number."""
    lines = [f"{'rule':<44} {'found':>6} {'labelled':>8} {'true':>5} {'false':>5}  precision"]
    for row in rows:
        if row.precision is None:
            verdict = (f"not measured (n={row.labelled}, needs {MIN_LABELLED})"
                       if row.labelled else "not labelled")
        else:
            verdict = f"{row.precision:.0%} (n={row.labelled})"
        lines.append(f"{row.rule:<44} {row.found:>6} {row.labelled:>8} "
                     f"{row.true:>5} {row.false:>5}  {verdict}")
        if pages and len(row.sources) >= pages > 1:
            lines.append(f"{'':<44} fires on every one of {pages} pages: worth a look")
    return "\n".join(lines)


def pages_in(audits) -> int:
    """How many distinct pages the audits read."""
    sources = set()
    for audit in audits:
        for document in (audit.get("coverage") or {}).get("documents", []):
            if document.get("kind") == "page" and not document.get("reason"):
                sources.add(document.get("source"))
    return len(sources)


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="audit_precision",
        description="Precision of the audit rules on labelled findings.")
    parser.add_argument("audits", nargs="+", type=Path,
                        help="JSON files written by `xaudit audit --json`")
    parser.add_argument("--labels", type=Path,
                        help="JSON lines of {fingerprint, verdict, reason}")
    parser.add_argument("--template", type=Path,
                        help="write a label file for every finding and stop")
    args = parser.parse_args(argv)

    audits = load_audits(args.audits)
    labels = load_labels(args.labels) if args.labels and args.labels.exists() else {}
    if args.template:
        with open(args.template, "w", encoding="utf-8") as out:
            for record in template_records(audits, labels):
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"wrote {args.template}: label each line true or false")
        return 0
    print(render(measure(audits, labels), pages=pages_in(audits)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
