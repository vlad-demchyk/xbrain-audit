"""A phase's product, kept on disk so resume does not recompute it.

The expensive phases of a full scan are the crawl and the browser pass: on a
192-page site they were three minutes and forty-three minutes respectively,
against two minutes for everything that comes after. A failure in one of the
cheap late phases used to cost the whole forty-six.

What is stored is the *product*, not the process: the audit's findings rather
than the pages they came from. `AccessibilityResult`, `DocumentReport` and
`Issue` are all plain dataclasses, so this is an exact round trip rather than
a stand-in that happens to answer the attributes today's report writers read -
which is what it would have had to be if any of them held a live object.

Deliberately not stored: the crawled pages themselves. Their text runs to
tens of megabytes on a large site and nothing after the audit reads them, so
keeping them would cost far more than the phase they would save.
"""
from __future__ import annotations

import json
from pathlib import Path

from finding_contract import SCHEMA_VERSION, deserialize_finding, json_value, serialize_issue

AUDIT_FILE = "checkpoint-audit.json"
SCAN_FILE = "checkpoint-scan.json"


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)
    return path


def save_audit(run_dir, result) -> Path | None:
    """Store an `AccessibilityResult`. Returns the file, or None if empty."""
    if result is None:
        return None
    from audit.coverage import content_digest
    payload = {
        "schema_version": SCHEMA_VERSION,
        "root": result.root,
        "mode": result.mode,
        "rules_run": list(getattr(result, "rules_run", ()) or ()),
        "coverage": json_value(getattr(result, "coverage", {})),
        "coverage_documents": json_value(getattr(result, "coverage_documents", [])),
        "browser_errors": json_value(getattr(result, "browser_errors", [])),
        "browser_coverage": json_value(getattr(result, "browser_coverage", [])),
        "auth": json_value(result.auth), "repo": json_value(result.repo),
        "media": json_value(result.media),
        "media_type": type(result.media).__name__ if result.media is not None else None,
        # A SharePoint run's zones and page list: without them a resumed
        # browser pass would read the chrome as if it were the site.
        "sharepoint": json_value(getattr(result, "sharepoint", {}) or {}),
        "page_tree": json_value(getattr(result, "page_tree", {}) or {}),
        "content_hashes": {source: content_digest(markup)
                           for source, markup in result.markup_by_source.items()},
        "documents": [
            {"source": doc.source, "error": doc.error,
             "kind": doc.kind, "checks": json_value(doc.checks), "content_hash": doc.content_hash,
             "elements_checked": doc.elements_checked,
             "issues": [serialize_issue(issue, source=doc.source) for issue in doc.issues]}
            for doc in result.documents
        ],
    }
    return _write(Path(run_dir) / AUDIT_FILE, payload)


def load_audit(run_dir):
    """Rebuild the `AccessibilityResult`, or None when there is no file.

    Unknown keys are dropped rather than passed through: a checkpoint written
    by an older build must not crash the resume that reads it, and a field
    this version does not have is a field it does not need.
    """
    path = Path(run_dir) / AUDIT_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    from audit.engine import AccessibilityResult, DocumentReport
    documents = []
    for doc in payload.get("documents", []):
        issues = [deserialize_finding(raw, finding_type="issue")
                  for raw in doc.get("issues", [])]
        documents.append(DocumentReport(
            source=doc.get("source", ""), issues=issues,
            error=doc.get("error"),
            kind=doc.get("kind", "page"), checks=doc.get("checks", []),
            content_hash=doc.get("content_hash", ""),
            elements_checked=doc.get("elements_checked", 0)))
    result = AccessibilityResult(
        root=payload.get("root", ""), mode=payload.get("mode", "web"),
        documents=documents, rules_run=payload.get("rules_run", []),
        browser_errors=payload.get("browser_errors", []),
        browser_coverage=payload.get("browser_coverage", []),
        coverage_documents=payload.get("coverage_documents", []),
        coverage=payload.get("coverage", {}))
    result.coverage.setdefault("content_hashes", payload.get("content_hashes", {}))
    if isinstance(payload.get("sharepoint"), dict):
        result.sharepoint = payload["sharepoint"]
    if payload.get("page_tree"):
        result.page_tree = payload["page_tree"]
    from dataclasses import fields
    from audit.authwall import Wall, WallReport
    from audit.media import MediaFetchScan, MediaScan, Provenance
    from audit.repo_facts import RepoFacts
    for name, model in (("auth", WallReport), ("repo", RepoFacts),
                        ("media", MediaScan if payload.get("media_type") == "MediaScan" else MediaFetchScan)):
        raw = payload.get(name)
        if not isinstance(raw, dict):
            continue
        known = {f.name for f in fields(model)}
        values = {k: v for k, v in raw.items() if k in known}
        if name == "auth":
            wall_fields = {f.name for f in fields(Wall)}
            values["walls"] = [Wall(**{k: v for k, v in wall.items() if k in wall_fields})
                               for wall in values.get("walls", [])]
        elif name == "media":
            provenance_fields = {f.name for f in fields(Provenance)}
            values["findings"] = [(source, Provenance(**{k: v for k, v in found.items() if k in provenance_fields}))
                                   for source, found in values.get("findings", [])]
        setattr(result, name, model(**values))
    return result


def save_scan(run_dir, findings: list, counts: dict | None = None, *, scan_result=None) -> Path:
    """Store the AI-patterns and typography findings."""
    payload = json_value(scan_result or {})
    payload.update(schema_version=SCHEMA_VERSION, findings=json_value(findings or []), counts=counts or {})
    return _write(Path(run_dir) / SCAN_FILE, payload)


def load_scan(run_dir):
    """Returns `(findings, counts)`, or `(None, None)` when absent."""
    payload = load_scan_result(run_dir)
    if payload is None:
        return None, None
    return payload.get("findings", []), payload.get("counts", {})


def load_scan_result(run_dir):
    """The full scan product, including read/error/hash evidence on resume."""
    path = Path(run_dir) / SCAN_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload
