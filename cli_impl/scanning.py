"""Scan pipeline helpers shared by the CLI commands.

Everything between "the user gave me paths" and "here are finding dicts"
lives here: ignore rules, the walk over files, detector construction and
the analysis pass that turns spans into the plain-dict findings both the
JSON and the human output print.
"""
from __future__ import annotations

import sys
from pathlib import Path

import config
import progress
import suppression
import unicode_rules
from detectors.factory import DetectorFactory
from detectors.judges import (
    JUDGE_ALIASES, JUDGE_BY_PROVIDER, JUDGE_NAMES, judge_for_provider,
)
from models import Confidence, ScanDiagnostics
from repo_scanner import (
    DEFAULT_IGNORE_PATTERNS,
    ScanConfig,
    _parse_ignore_text,
    scan_file,
    scan_repo,
)

# `fix` may only apply findings whose correction is fixed by a rule. That is
# now a property of the *pass* that produced a finding, not of a detector
# name: the character pass runs both standalone and inside the merged
# offline detector, so its findings arrive under more than one detector name
# but always carry this source stamp (see detectors/offline.py).
CHARACTER_SOURCE = "characters"

#: The name that runs both engines over the same text and merges the result.
#: Spelled here as well as in the factory because `--detector hybrid` needs
#: the provider resolved for the judge half, exactly like a bare judge does.
HYBRID_NAME = "hybrid"


def _build_ignore_list(args, target: str | None = None) -> list:
    """Build the ignore pattern list from args and defaults.

    Single source of truth for the ignore logic used by scan, audit,
    fullscan, and reaudit.

    `target` adds what the project itself says it vendors. A WordPress
    install carries `wp-includes/`, a Laravel app carries `vendor/`, a
    SvelteKit app carries `.svelte-kit/`, and every one of those is code the
    developer did not write and cannot change. Until this was read from the
    project, each stack had to be discovered the hard way - `wp-admin/` was
    added after 455 findings arrived from vendored WordPress core in a real
    audit. See `project_profile`.

    Detection is evidence-based and additive: an undetected project gets
    exactly the list it got before, and `--no-default-excludes` still drops
    the lot.
    """
    use_defaults = getattr(args, "use_default_excludes", True)
    ignore = _parse_ignore_text(DEFAULT_IGNORE_PATTERNS) if use_defaults else []
    if use_defaults and target:
        import project_profile

        ignore = project_profile.detect(target).applied_to(ignore)
    ignore += list(getattr(args, "exclude", None) or [])
    return ignore


def _build_scan_config(args, extensions=None,
                       target: str | None = None) -> "ScanConfig":
    """Build a ScanConfig from args.

    Single source of truth for scan configuration used by scan, audit,
    fullscan, and reaudit.
    """
    if extensions is None and getattr(args, "ext", None):
        extensions = tuple(e if e.startswith(".") else "." + e for e in args.ext)
    return ScanConfig(
        extensions=extensions,
        ignore_patterns=_build_ignore_list(args, target),
        max_files=getattr(args, "max_files", 5000),
        scope=getattr(args, "scope", "content"),
    )


def _collect_files(paths: list[str], args, missing_out=None,
                   diagnostics_out=None) -> list:
    """Turn the given paths into FileResults. A directory is walked with the
    exclusion rules; a file named directly is always scanned.

    `diagnostics_out`, if given, collects one `ScanDiagnostics` per walked
    directory, so the caller can say what was read rather than only what was
    found. A file named directly needs none: naming it is the answer.
    """
    cfg = _build_scan_config(args, target=paths[0] if paths else None)
    scope = getattr(args, "scope", "content")

    results = []
    #: Paths that do not exist, collected so the caller can fail rather than
    #: report a clean scan of nothing. A mistyped path is a pipeline pass
    #: otherwise, which is the worst kind of wrong answer.
    missing: list = []
    # One `file` event per file opened, and only when something is reading
    # them: the walk already takes a per-file callback for the window's
    # progress bar, so this costs a function call per file and only when the
    # machine-readable stream is on. The total is not known while walking -
    # that is what the walk is finding out - so `of` is the cap, not a
    # count, and is left out when there is none.
    read_so_far = [0]

    def _opened(rel: str) -> None:
        read_so_far[0] += 1
        progress.file_read(read_so_far[0], cfg.max_files or None, rel)

    watcher = _opened if progress.enabled() else None
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            walk = ScanDiagnostics()
            results.extend(scan_repo(str(p), cfg, progress_cb=watcher,
                                     diagnostics=walk))
            if diagnostics_out is not None:
                diagnostics_out.append((str(p), walk))
        elif p.exists():
            if watcher is not None:
                watcher(str(p))
            results.append(scan_file(str(p), scope))
        else:
            progress.notice("error", f"path not found: {raw}",
                            human=f"path not found: {raw}")
            missing.append(raw)
    if missing_out is not None:
        missing_out.extend(missing)
    return results


def _create_detector(args):
    """Build the detector `--detector` asked for, billed where it belongs.

    `scan` used to build it by name alone, which meant the name carried the
    billing decision: `claude-llm-judge` and only it, paid for with an
    `ANTHROPIC_API_KEY` from the environment. `audit --ai` had already stopped
    working that way - it asks `rewriter` which account is in play, so inside
    a Claude Code session it uses that session. The two commands disagreed on
    the same machine, and the disagreement showed up as an error message about
    a key the user did not need.
    """
    import rewriter

    name = args.detector
    provider = getattr(args, "provider", None)

    def resolved_judge() -> str:
        settings = config.Settings.load()
        return judge_for_provider(rewriter.effective_provider_name(
            settings, force=provider, allow_auto=True))

    if name == HYBRID_NAME:
        # The hybrid runs the offline pass itself, so only its judge half
        # needs an account - resolved the same way a bare judge is, which is
        # what keeps `--provider` meaning one thing across both.
        judge = resolved_judge()
        judge_config = ({"api_key": config.get_anthropic_api_key()}
                        if judge == "claude-llm-judge" else {})
        return DetectorFactory.create(
            name, judge_name=judge, judge_config=judge_config)

    if name in JUDGE_NAMES and (provider or name in JUDGE_ALIASES):
        name = resolved_judge()

    # `--model` and `--effort` are about the pass, not about the account, so
    # they apply to whichever judge the account resolved to. Only what was
    # actually asked for is passed: an unset flag must leave the settings'
    # answer alone rather than overwrite it with a default of its own.
    overrides = {key: value for key, value in
                 (("model", getattr(args, "model", None)),
                  ("effort", getattr(args, "effort", None))) if value}

    if name == "claude-llm-judge":
        # The key can live in the keychain as well as the environment; reading
        # only the environment made a key entered in Settings invisible here.
        return DetectorFactory.create(name, api_key=config.get_anthropic_api_key(),
                                      **overrides)
    if overrides and name == "xformat-llm-judge":
        # The subscription picks the model on its side, so there is nothing
        # here to override. Said out loud rather than dropped: a flag that is
        # accepted and ignored is the defect this file has been fixing all
        # day, and it is no better when the reason is good.
        print(f"# note: --{'/--'.join(sorted(overrides))} does not apply to the "
              f"xFormat subscription; it chooses the model itself",
              file=sys.stderr, flush=True)
        overrides = {}

    if overrides and name in JUDGE_BY_PROVIDER.values():
        # A provider-backed judge builds its own account client from the
        # settings, so an override has to arrive as a ready provider rather
        # than as a constructor argument it would ignore.
        settings = config.Settings.load()
        forced = rewriter.effective_provider_name(
            settings, force=provider, allow_auto=True)
        return DetectorFactory.create(
            name, provider=rewriter.build_provider(force=forced, **overrides))
    return DetectorFactory.create(name)


def _categories(args) -> tuple[str, ...]:
    if args.categories:
        chosen = tuple(c.strip() for c in args.categories.split(",") if c.strip())
        unknown = [c for c in chosen if c not in unicode_rules.ALL_CATEGORIES]
        if unknown:
            raise SystemExit(
                f"unknown category: {', '.join(unknown)}. "
                f"Valid: {', '.join(unicode_rules.ALL_CATEGORIES)}"
            )
        return chosen
    if args.no_typography:
        return unicode_rules.HARD_CATEGORIES
    return unicode_rules.ALL_CATEGORIES


def _settings_for_ignore(args):
    """The user's own suppression list, unless --no-ignore was passed.

    Loaded lazily and defensively: the CLI must keep working in a container
    with no config directory, which is exactly where it runs in CI.
    """
    if getattr(args, "no_ignore", False):
        return None
    try:
        return config.Settings.load()
    except Exception:  # noqa: BLE001
        return None


def _ignore_root(args) -> str | None:
    if getattr(args, "no_ignore", False):
        return None
    paths = getattr(args, "paths", None) or []
    if paths:
        return paths[0]
    return getattr(args, "target", None)


def _report_detector_errors(spans) -> int:
    """Say, once, what the detector could not judge. Returns how many blocks."""
    failures = [s for s in spans if (s.details or {}).get("error")]
    if not failures:
        return 0
    reasons = []
    for span in failures:
        reason = span.details["error"]
        if reason not in reasons:
            reasons.append(reason)
    print(f"# {len(failures)} block(s) were not judged by "
          f"{failures[0].detector_name}:", file=sys.stderr)
    for reason in reasons[:3]:
        print(f"#   {reason}", file=sys.stderr)
    if len(reasons) > 3:
        print(f"#   ... and {len(reasons) - 3} other error(s)", file=sys.stderr)
    return len(failures)


#: Keys of a finding dict that only make sense in the process that produced
#: it: the `TextSpan` and the `CodeBlock` behind it. Everything else is plain
#: JSON, so everything else can be cached.
_UNCACHEABLE = ("_span", "_block")


def _incremental_signature(args) -> dict:
    """What a cached result is only valid for.

    A cache keyed on the file alone is worse than no cache: `--detector
    offline` and `--detector llm-judge` read the same bytes and must not
    read each other's answers, and neither must a run with a different
    `--scope` or a narrower `--categories`. So the configuration that
    changes the answer is stored alongside the answer and compared before it
    is trusted. The app version is in there too - a rule added in a release
    changes what the same file yields, and a cache that outlives the release
    would keep reporting the old verdict.
    """
    from finding_contract import SCHEMA_VERSION
    return {
        "version": config.APP_VERSION,
        "finding_schema": SCHEMA_VERSION,
        "detector": DetectorFactory.resolve(getattr(args, "detector", None)
                                            or "none"),
        "scope": getattr(args, "scope", "content"),
        "categories": sorted(set(_categories(args))),
        "no_unicode": bool(getattr(args, "no_unicode", False)),
        "no_ignore": bool(getattr(args, "no_ignore", False)),
        "suppressions": suppression.Suppressions.load(
            _settings_for_ignore(args), _ignore_root(args)).to_dict(),
    }


def _split_unchanged(file_results, args):
    """Partition files into "must be read again" and "answer already known".

    Returns `(fresh, cached_findings, reused)`. `--incremental` exists for
    the pre-commit case: a repository of four thousand files where two
    changed. Reading the two is the whole point, and the cache is keyed on
    the text already read by the scanner, together with the configuration
    and detector version. File timestamps are not evidence of identity.
    """
    from scan_cache import get_cache

    cache = get_cache()
    signature = _incremental_signature(args)
    # Model verdicts have their own cache with provider/model/prompt identity.
    # A file-level result must not bypass it or cache a failed provider call.
    if signature["detector"] not in ("none", "offline"):
        return list(file_results), [], 0
    fresh, cached_findings, reused = [], [], 0
    for result in file_results:
        entry = cache.get(result.path, content=result.raw_text)
        if entry and entry.get("config") == signature:
            cached_findings.extend(entry.get("findings") or [])
            reused += 1
            continue
        fresh.append(result)
    return fresh, cached_findings, reused


def _store_unchanged(file_results, findings, args) -> None:
    """Record this run's answer per file, for the next `--incremental` run.

    Every scanned file is recorded, including the ones with nothing wrong:
    otherwise a clean file has no cache entry and is re-read on every run,
    which is most of the repository and most of the time.
    """
    from scan_cache import get_cache

    cache = get_cache()
    signature = _incremental_signature(args)
    if signature["detector"] not in ("none", "offline"):
        return
    by_file: dict = {result.path: [] for result in file_results}
    for finding in findings:
        bucket = by_file.get(finding.get("file"))
        if bucket is not None:
            bucket.append({k: v for k, v in finding.items()
                           if k not in _UNCACHEABLE})
    for result in file_results:
        cache.put(result.path, {"config": signature, "findings": by_file[result.path]},
                  save=False, content=result.raw_text)
    cache.save()


def _analyze(file_results, args, unjudged_out: list | None = None):
    """Return (findings, blocks_by_id). Findings are plain dicts so the JSON
    output and the human output share one shape."""
    blocks = [b for f in file_results for b in f.blocks]
    blocks_by_id = {b.block_id: b for b in blocks}
    spans = []
    args._detector_coverage = []

    categories = _categories(args)
    # The offline detector holds both free passes. Style analysis is opt-in
    # here (it is reported, never auto-applied), so the two are requested
    # independently rather than as two detectors.
    wants_style = DetectorFactory.resolve(args.detector or "none") == "offline"
    if not args.no_unicode or wants_style:
        offline = DetectorFactory.create(
            "offline",
            categories=categories if not args.no_unicode else (),
            include_style=wants_style,
        )
        spans.extend(s for s in offline.analyze_blocks(blocks)
                     if s.confidence != Confidence.LOW
                     or (s.details or {}).get("source") == CHARACTER_SOURCE)
        args._detector_coverage.append({"engine": offline.name, "status": "checked",
                                        "blocks": len(blocks), "version": config.APP_VERSION})
    if args.detector and args.detector != "none" and not wants_style:
        detector = _create_detector(args)
        judged = detector.analyze_blocks(blocks)
        # Blocks the detector could not read at all. Reported rather than
        # filtered away with the weak findings: an exhausted plan or a dead
        # key would otherwise print "No findings", which reads as a clean
        # result and is the one answer a failed run must never give.
        failed = _report_detector_errors(judged)
        args._detector_coverage.append({"engine": detector.name, "status": "error" if failed else "checked",
            "blocks": len(blocks), "model": getattr(detector, "model", None),
            "version": getattr(detector, "version", None)})
        if failed and unjudged_out is not None:
            unjudged_out.append(failed)
        spans.extend(s for s in judged
                     if s.confidence != Confidence.LOW
                     and not (s.details or {}).get("error"))

    # Applied before anything is reported, so a suppressed finding never
    # reaches --json, the exit code, or `fix`. The project's own
    # `.xaudit-ignore` is read from the first scanned path.
    spans = suppression.filter_spans(
        spans, blocks_by_id,
        suppression.Suppressions.load(_settings_for_ignore(args), _ignore_root(args)),
    )

    findings = []
    for span in spans:
        block = blocks_by_id.get(span.block_id)
        if block is None:
            continue
        from finding_contract import serialize_span
        findings.append({
            **serialize_span(span, block),
            "_span": span,
            "_block": block,
        })
    findings.sort(key=lambda f: (f["file"], f["offset"]))
    return findings, blocks_by_id
