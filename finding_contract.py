"""Lossless, versioned finding records shared by CLI, reports and checkpoints.

Version 1 is additive: legacy keys remain valid, including the text scan's
`source` (signal family). `location.source` always names the document. Ranges
name their coordinate system; a DOM selector is not a source character offset.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path

SCHEMA_VERSION = 1


def json_value(value):
    """Detach data from live models, preserving structured rule evidence."""
    if isinstance(value, Enum):
        return json_value(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: json_value(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"Unsupported finding evidence: {type(value).__name__}")


def _status(confidence, details, *, text=False):
    if any(details.get(key) for key in ("error", "engine_error", "rule_error")):
        return "error"
    if confidence == "needs-browser":
        return "unknown"
    if confidence == "advisory":
        return "advisory"
    return "scored" if text and details.get("source") != "characters" else "observed"


def serialize_issue(issue, *, source="") -> dict:
    # Imported here: `audit.explanations` pulls in the translations, which a
    # reader of a saved checkpoint should not need just to load a record.
    from audit.explanations import _wcag_for

    data = json_value(issue)
    data["source"] = issue.source or source
    data.update(
        schema_version=SCHEMA_VERSION, finding_type="issue", rule=issue.rule_id,
        range=None, evidence_status=_status(issue.confidence, issue.details or {}),
        location={"source": data["source"], "line": issue.line,
                  "selector": issue.selector},
        # The success criteria the rule contributes to, so a machine reader
        # gets the number the printed report shows. Additive, and derived from
        # the rule id alone: recomputed, never stored, so a record written
        # before a rule learned its criteria reads the same today.
        wcag=list(_wcag_for(issue.rule_id)),
        # What `.xanalyze-ignore` and `xanalyze ignore` take to dismiss this
        # one finding, so a reader of the JSON can act on it without
        # recomputing a hash.
        fingerprint=_fingerprint(issue, data["source"]),
    )
    # Whose part of a SharePoint page this was found in. Only when a
    # SharePoint run placed it, so every other record keeps its shape.
    zone = (issue.details or {}).get("zone")
    if zone is not None:
        data["zone"] = zone
        data["zone_name"] = (issue.details or {}).get("zone_name", "")
    return data


def _fingerprint(issue, source: str) -> str:
    from suppression import fingerprint

    return fingerprint(source, issue.snippet or issue.selector, issue.rule_id)


def serialize_span(span, block=None) -> dict:
    data = json_value(span)
    data.update(schema_version=SCHEMA_VERSION, finding_type="text-span",
                detector=span.detector_name, engine=span.detector_name,
                source=(span.details or {}).get("source", ""),
                evidence_status=_status(data["confidence"], span.details or {}, text=True))
    data["range"] = {"start": span.start, "end": span.end,
                     "coordinate_system": "block-text", "block_id": span.block_id}
    data["location"] = {"source": "", "line": None, "selector": ""}
    if block is not None:
        local = hasattr(block, "file_path")
        path = block.file_path if local else block.page_url
        line = block.line_number if local else 0
        data.update(file=path, line=line, text=block.text[span.start:span.end],
                    block_id=block.block_id)
        data["range"]["block_id"] = block.block_id
        data["location"] = {"source": path, "line": line or None,
                            "selector": getattr(block, "dom_path", "")}
        if local:
            data.update(offset=block.start + span.start, end_offset=block.start + span.end)
            data["range"] = {"start": data["offset"], "end": data["end_offset"],
                             "coordinate_system": "source-text"}
        else:
            if getattr(block, "source_file", ""):
                data.update(source_file=block.source_file,
                            source_line=getattr(block, "source_line", None))
            from repo_pairing import mapping_for
            mapping = mapping_for(block)
            if mapping:
                data["mapping"] = mapping
            from text_extraction import span_dom_ranges
            data.update(visibility=getattr(block, "visibility", "unknown"),
                        text_kind=getattr(block, "text_kind", "dom-text"),
                        attribute_name=getattr(block, "attribute_name", ""),
                        declared_language=getattr(block, "declared_language", None),
                        language_context=json_value(getattr(block, "language_context", [])),
                        context_path=json_value(getattr(block, "context_path", [])),
                        dom_ranges=span_dom_ranges(block, span.start, span.end))
            if data["attribute_name"]:
                data["range"]["coordinate_system"] = (
                    "referenced-label-text" if data["text_kind"] == "referenced-label" else "attribute-text")
                data["range"]["attribute"] = data["attribute_name"]
    return data


def serialize_finding(finding, block=None) -> dict:
    """Keep the complete record; display renderers choose their own limits."""
    from audit.base import Issue
    from models import TextSpan
    if isinstance(finding, Issue):
        return serialize_issue(finding)
    if isinstance(finding, TextSpan):
        return serialize_span(finding, block)
    if isinstance(finding, dict):
        data = json_value({k: v for k, v in finding.items() if not k.startswith("_")})
        data.setdefault("schema_version", SCHEMA_VERSION)
        data.setdefault("finding_type", "text-span")
        return data
    from report.model import ReportFinding
    if isinstance(finding, ReportFinding):
        evidence = finding.evidence or {}
        location = evidence.get("location") or {}
        return {**json_value(finding), "schema_version": SCHEMA_VERSION,
                "finding_type": "report-finding", "source": location.get("source", ""),
                "line": location.get("line"), "range": json_value(evidence.get("range")),
                "details": json_value(evidence.get("details") or {}),
                "evidence_status": evidence.get("evidence_status", "unknown")}
    raise TypeError(f"Unsupported finding: {type(finding).__name__}")


def deserialize_finding(data: dict, *, finding_type=None):
    """Read version 1 or legacy records; reject unsupported major schemas."""
    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported finding schema version: {version}")
    from audit.base import Issue
    from models import Confidence, TextSpan
    from report.model import ReportFinding
    kind = finding_type or data.get("finding_type", "issue")
    model = {"issue": Issue, "text-span": TextSpan, "report-finding": ReportFinding}[kind]
    values = {f.name: deepcopy(data[f.name]) for f in fields(model) if f.name in data}
    if model is Issue:
        values.setdefault("rule_id", data.get("rule", ""))
        arrived = (values.get("details") or {}).get("arrived")
        if isinstance(arrived, dict):
            from audit.repo_facts import Arrival
            known = {f.name for f in fields(Arrival)}
            values["details"]["arrived"] = Arrival(**{k: v for k, v in arrived.items() if k in known})
    elif model is TextSpan:
        values["confidence"] = Confidence(values["confidence"])
    else:
        values["wcag"] = tuple(values.get("wcag", ()))
    return model(**values)
