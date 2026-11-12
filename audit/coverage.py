"""Evidence about what ran, detached before result views hide unknown checks."""
from __future__ import annotations

import hashlib
import re
from importlib import metadata
from pathlib import Path

from finding_contract import SCHEMA_VERSION, json_value, serialize_issue


def content_digest(text: str) -> str:
    """SHA-256 of the decoded text used by the pass, encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def document_coverage(document) -> dict:
    return {"source": document.source,
            "status": "error" if document.error else ("checked" if document.checks else "unknown"),
            "reason": document.error or "",
            "kind": document.kind, "elements_checked": document.elements_checked,
            "content_hash": document.content_hash or None,
            "checks": json_value(document.checks)}


def _engines() -> dict:
    from config import APP_VERSION
    engines = {"static": {"version": APP_VERSION}}
    # Hash shipped artifacts; an app version alone does not identify a
    # working tree's rules or a replaced vendor script.
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    paths = sorted((root / "rules").glob("*.py"))
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    engines["static"]["rules_sha256"] = digest.hexdigest() if paths else None
    for name, filename in (("axe", "axe.min.js"), ("htmlcs", "HTMLCS.js")):
        path = root / "vendor" / filename
        data = path.read_bytes() if path.is_file() else None
        version = re.search(rb"\bv(\d+\.\d+\.\d+)\b", data[:200]) if data else None
        engines[name] = {"version": version[1].decode() if version else None,
                         "artifact_sha256": hashlib.sha256(data).hexdigest() if data else None}
    for name in ("PySide6", "beautifulsoup4"):
        try:
            engines[name] = {"version": metadata.version(name)}
        except metadata.PackageNotFoundError:
            engines[name] = {"version": None}
    from .vitals import vendor_identity
    try:
        engines["web-vitals"] = vendor_identity()
    except (OSError, ValueError) as exc:
        engines["web-vitals"] = {"version": None, "error": type(exc).__name__}
    return engines


def build_coverage(result, args=None, *, scan=None, pages=None) -> dict:
    """Recorded executions, never a claim that every possible rule ran.

    Extra passes without instrumentation are unknown. `checked` says a pass
    returned, not that a document is defect-free. Hashes cover decoded input,
    not original transport bytes or every transient DOM/browser state.
    """
    documents = list(json_value(result.coverage_documents))
    for document in result.documents:
        record = document_coverage(document)
        if record not in documents:
            documents.append(record)
    unresolved, errors = [], list(json_value(result.browser_errors))
    for document in result.documents:
        if document.error:
            errors.append({"source": document.source, "error": document.error})
        for issue in document.issues:
            record = serialize_issue(issue, source=document.source)
            if record["evidence_status"] == "unknown":
                unresolved.append(record)
            elif record["evidence_status"] == "error":
                errors.append(record)
    hashes = dict(result.coverage.get("content_hashes") or {})
    hashes.update({source: content_digest(markup)
              for source, markup in result.markup_by_source.items()}
    )
    for document in documents:
        if document.get("content_hash"):
            hashes.setdefault(document["source"], document["content_hash"])
    scan = scan or {}
    unresolved.extend(json_value(f) for f in scan.get("findings", [])
                      if f.get("evidence_status") == "unknown")
    hashes.update(scan.get("content_hashes") or {})
    options = {name: json_value(getattr(args, name)) for name in (
        "detector", "ai_text", "model", "effort", "scope", "depth", "max_pages", "max_files",
        "ext", "exclude", "no_default_excludes", "no_typography", "no_browser",
        "no_judgment_cache", "incremental", "confidence", "category", "unsettled", "include_environment",
        "breakpoints", "within", "medium", "agent", "no_session", "site_controls",
        "performance_repeats", "performance_fresh", "performance_settle_ms", "performance_scenario",
        "lighthouse", "lighthouse_profile", "crux", "crux_scope", "crux_form_factor",
    ) if args is not None and hasattr(args, name)}
    walk = json_value(scan.get("read") or [])
    scan_errors = json_value(scan.get("errors") or [])
    errors.extend(scan_errors)
    content = json_value(scan.get("detector_coverage") or getattr(args, "_detector_coverage", []) or [])
    if not content:
        content = [{"engine": options.get("detector"), "status": "unknown",
                    "reason": "no detector execution record"}]
    if options.get("ai_text") is False and not options.get("agent"):
        content = [{"engine": "text-analysis", "status": "skipped",
                    "reason": "not requested (--ai-text)"}]
    if options.get("agent"):
        content = [{"engine": "agent", "status": "unknown", "reason": "judgments pending"}]
    errors.extend(c for c in content if c["status"] == "error")
    browser = json_value(result.browser_coverage)
    if not browser:
        browser = [{"engine": "browser", "status": "skipped" if
                    result.mode == "repo" or options.get("no_browser") else "unknown",
                    "reason": "source-only target or --no-browser" if
                    result.mode == "repo" or options.get("no_browser") else "no execution record"}]
    page_records = [{"source": p.url, "error": p.error,
                     "diagnostics": {k: v for k, v in json_value(p.diagnostics).items() if k != "headers"}}
                    for p in (pages or ())]
    media = json_value(result.media)
    auth = json_value(result.auth)
    incomplete = bool(errors or unresolved or any(d["status"] == "error" for d in documents)
                      or any(check["status"] == "error"
                             for d in documents for check in d.get("checks", []))
                      or any(w.get("truncated") or w.get("unreadable") or w.get("skipped_too_large")
                             for w in walk)
                      or any(p["error"] or p["diagnostics"].get("render_error") for p in page_records)
                      or any(p["diagnostics"].get("extraction", {}).get("truncated")
                             or p["diagnostics"].get("extraction", {}).get("snapshot_error")
                             or p["diagnostics"].get("extraction", {}).get("unknown") for p in page_records)
                      or any(b["status"] in ("error", "unknown") for b in browser))
    incomplete = incomplete or bool(
        result.media is not None and (getattr(result.media, "unchecked", 0)
                                      or getattr(result.media, "unreadable", 0))
        or result.auth is not None and getattr(result.auth, "blocked", 0))
    # A legacy empty result has no evidence of a completed audit.
    status = "incomplete" if incomplete else "unknown" if (
        not documents or any(d["status"] == "unknown" for d in documents)
        or any(c["status"] == "unknown" for c in content)) else "checked"
    return {"schema_version": SCHEMA_VERSION, "status": status,
            "performance": json_value(result.coverage.get("performance", [])),
            "performance_sources": json_value(result.coverage.get("performance_sources", [])),
            "documents": documents, "rules_selected": list(result.rules_run),
            "browser": browser, "content": content, "unknown": unresolved, "errors": errors,
            "scan_read": walk, "pages": page_records, "engines": _engines(),
            "scan_cached_files": scan.get("cached_files", 0),
            "media": media, "auth": auth, "repo": json_value(result.repo),
            # Frames axe could not test (cross-origin), per page: a limit of
            # this run's coverage, not a defect of the page.
            "untested_frames": json_value(result.coverage.get("untested_frames", [])),
            "options": options, "content_hashes": hashes,
            "hash_coordinate_system": "decoded-text-utf8",
            "mapping_confidence": "unknown",
            "limitations": ["Auxiliary passes without execution records have unknown coverage.",
                            "Content hashes do not identify all browser DOM states.",
                            "Source mapping confidence has not been independently verified."]}


def coverage_summary(coverage, lang="en") -> tuple[str, str]:
    """A small translated coverage statement for human report exports."""
    labels = {
        "en": ("Check coverage", "Recorded executions: {checked} checked, {skipped} skipped, {unknown} unknown, {error} errors. Unresolved findings: {pending}. Coverage: {status}.",
               {"checked": "checked within the recorded scope", "incomplete": "incomplete", "unknown": "unknown"}),
        "uk": ("Покриття перевірки", "Зафіксовані перевірки: {checked} виконано, {skipped} пропущено, {unknown} невідомо, {error} помилок. Невирішені знахідки: {pending}. Покриття: {status}.",
               {"checked": "перевірено в зафіксованих межах", "incomplete": "неповне", "unknown": "невідоме"}),
        "it": ("Copertura dei controlli", "Controlli registrati: {checked} eseguiti, {skipped} saltati, {unknown} sconosciuti, {error} errori. Risultati irrisolti: {pending}. Copertura: {status}.",
               {"checked": "verificata nell'ambito registrato", "incomplete": "incompleta", "unknown": "sconosciuta"}),
    }
    title, sentence, statuses = labels.get(lang, labels["en"])
    records = list(coverage.get("browser") or []) + list(coverage.get("content") or [])
    for document in coverage.get("documents") or []:
        records.extend(document.get("checks") or [document])
    counts = {status: sum(r.get("status") == status for r in records)
              for status in ("checked", "skipped", "unknown", "error")}
    text = sentence.format(**counts, pending=len(coverage.get("unknown") or []),
                           status=statuses.get(coverage.get("status"), statuses["unknown"]))
    frames = [entry for entry in coverage.get("untested_frames") or []
              if isinstance(entry, dict)]
    if frames:
        origins = sorted({origin for entry in frames
                          for origin in entry.get("origins") or []})
        said = {
            "en": " Frames axe could not test (their content is not covered): {pages} page(s), {origins}.",
            "uk": " Фрейми, які axe не зміг перевірити (їхній вміст не покрито): сторінок {pages}, {origins}.",
            "it": " Frame che axe non ha potuto verificare (il loro contenuto non è coperto): {pages} pagine, {origins}.",
        }
        text += said.get(lang, said["en"]).format(pages=len(frames),
                                                  origins=", ".join(origins[:5]))
    return title, text
