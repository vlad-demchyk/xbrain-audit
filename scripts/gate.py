#!/usr/bin/env python
"""One command that says whether the tool is shippable.

Three kinds of check, because they fail in three different ways:

  tests       the suite. Catches what someone thought to assert.
  smoke       the CLI, end to end, on a throwaway copy of real files. Catches
              the wiring the unit tests mock away - a flag that no longer
              reaches the function, a writer that leaves no backup.
  quality     the calibration corpus: does the detector still tell model-written
              text from human-written text. A detector that runs and separates
              nothing passes every other check here.
  budget      a real repository, scanned under a wall-clock limit. Catches the
              failure that has no assertion: not a wrong answer but no answer,
              which is what a pathological input produces and what a test suite
              of small strings will never see.

Run it before a commit that touches extraction, the CLI or the audit engine:

    python scripts/gate.py                  # tests + smoke
    python scripts/gate.py --repo ~/some/repo   # ... and the budget check
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# The gate lives in scripts/, the code it checks lives one level up. Added
# rather than assumed: run from anywhere, and `python scripts/gate.py` puts
# only scripts/ on the path.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: Wall clock for one full content scan of the named repository. Not a
#: benchmark: a limit that only a blow-up can exceed.
SCAN_BUDGET_SECONDS = 120


class Result:
    def __init__(self) -> None:
        self.failures: list = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}"
              + (f"  - {detail}" if detail and not ok else ""))
        if not ok:
            self.failures.append(f"{name}: {detail}" if detail else name)
        return ok


def run_tests(result: Result) -> None:
    """The suite, run the way the project runs it: `python -m pytest tests/`.

    It used to be `unittest.TestLoader().discover(...)` in this process, and
    that is not the same suite. `tests/conftest.py` points `XDG_CONFIG_HOME`
    at a temporary directory at collection time, and unittest discovery does
    not read a conftest - so the gate ran every test against the
    developer's real `~/.config/xanalyze/settings.json`, and
    `test_settings_isolation` correctly failed to say so. The release gate
    reported two failures of its own making on every run, which is the kind
    of noise that gets a gate ignored.
    """
    print("tests")
    done = subprocess.run([PYTHON, "-m", "pytest", str(ROOT / "tests"), "-q"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=str(ROOT))
    tail = (done.stdout or "").strip().splitlines()
    summary = tail[-1] if tail else "no output"
    result.check(f"suite: {summary}", done.returncode == 0,
                 "\n".join(tail[-12:]))


def _cli(*args, timeout=300):
    return subprocess.run([PYTHON, str(ROOT / "cli.py"), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout,
                          cwd=str(ROOT))


#: Two defects on purpose: a missing `lang`, which the tool can correct on its
#: own, and a missing `alt`, which it must not - that one needs words only a
#: person has. The smoke test asserts both halves of that distinction.
PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>A page worth auditing</title></head>
<body><h1>Heading</h1><img src="/logo.svg"><p>Text that ships to a reader.</p></body>
</html>
"""


def run_smoke(result: Result) -> None:
    """The CLI, on files it may safely write to."""
    print("smoke")
    work = Path(tempfile.mkdtemp(prefix="xanalyze-gate-"))
    try:
        page = work / "index.html"
        page.write_text(PAGE, encoding="utf-8")

        done = _cli("audit", str(page), "--json")
        result.check("audit --json exits 0", done.returncode == 0,
                     done.stderr[-300:])
        try:
            report = json.loads(done.stdout)
            findings = len(report.get("issues", []))
            result.check("audit reports the missing alt", findings > 0
                         and any(i["rule"] == "image-alt" for i in report["issues"]))
        except json.JSONDecodeError as exc:
            result.check("audit --json is JSON", False, str(exc))

        # A missing target must not read as a clean result.
        done = _cli("audit", str(work / "nope.html"), "--check")
        result.check("a missing target is not reported as clean",
                     done.returncode != 0,
                     "exit 0 on a path that does not exist")

        before = page.read_text(encoding="utf-8")
        done = _cli("audit", str(page), "--fix")
        result.check("--fix exits 0", done.returncode == 0, done.stderr[-300:])
        result.check("--fix leaves a backup", (work / "index.html.bak").exists())
        after = page.read_text(encoding="utf-8")
        result.check("--fix changed the file", after != before)
        result.check("--fix applied the correction it could decide alone",
                     "lang=" in after)
        result.check("--fix left the one needing words alone",
                     "alt=" not in after)

        done = _cli("undo", str(page))
        result.check("undo exits 0", done.returncode == 0, done.stderr[-300:])
        result.check("undo restores the original byte for byte",
                     page.read_text(encoding="utf-8") == before)

        report_path = work / "report.md"
        done = _cli("audit", str(page), "--report", str(report_path))
        result.check("--report writes a briefing",
                     report_path.exists() and report_path.stat().st_size > 200)

        source = work / "Panel.tsx"
        source.write_text(
            'export const P = () => <p>Copy for a reader</p>;\n'
            'const t: Map<string, number> = new Map();\n', encoding="utf-8")
        done = _cli("scan", str(source), "--detector", "offline", "--json")
        result.check("scan --json exits 0", done.returncode == 0, done.stderr[-300:])
    finally:
        shutil.rmtree(work, ignore_errors=True)


def run_quality(result: Result) -> None:
    """Historical regression evidence cannot establish independent release quality."""
    print("quality")
    from corpus_split import split
    from scripts.calibrate import load, score_rows

    rows = load("labelled.jsonl")
    if not rows:
        result.check("calibration corpus present", False, "corpus/labelled.jsonl is empty")
        return
    scored = score_rows(rows)
    flagged_human = [r for r in scored
                     if r["label"] == "human" and r["score"] >= 0.33]
    result.check(f"no false alarms on {sum(1 for r in scored if r['label']=='human')} human entries",
                 not flagged_human,
                 f"flagged: {[r['text'][:40] for r in flagged_human]}")

    _train, test = split(scored)
    models = [r for r in test if r["label"] == "model"]
    found = [r for r in models if r["score"] >= 0.33]
    recall = len(found) / len(models) if models else 0
    result.check(f"held-out recall {recall*100:.0f}%", recall >= 0.5,
                 "below the 50% floor")

    for language in ("en", "it", "uk"):
        subset = [r for r in test
                  if r["label"] == "model" and r["language"] == language]
        if not subset:
            result.check(f"{language} model samples present", False, "missing subgroup")
            continue
        hit = sum(1 for r in subset if r["score"] >= 0.33) / len(subset)
        result.check(f"{language} recall {hit*100:.0f}%", hit >= 0.5,
                     "one language far behind the other is a broken detector, "
                     "not a weaker one")
    from validation.metrics import metric_report, quality_failures
    evaluated = [{**row, "status": "abstained" if len(row["text"].split()) < 5 else "checked",
                  "register": row.get("register", "unknown").replace(" ", "-"),
                  "condition": "original"} for row in test]
    report = metric_report(evaluated, .33)
    failures = quality_failures(report, independent=False)
    result.check("independent multilingual quality requirements", not failures,
                 "; ".join(failures[:8]) + (f"; {len(failures) - 8} more requirements unmet" if len(failures) > 8 else ""))


def run_quality_report(result: Result, path: Path) -> None:
    """Only an unchanged, independently evaluated production configuration can pass."""
    from validation.corpus import strict_json
    from validation.metrics import QualityPolicy, metric_report, quality_failures
    from validation.protocol import verify_report
    try:
        report = strict_json(path.read_text(encoding="utf-8"))
        verify_report(report)
        frozen = report["protocol"]
        policy = QualityPolicy()  # An experiment's relaxed policy cannot relax the release gate.
        computed = metric_report(report["predictions"], frozen["threshold"], policy.prevalence)
        failures = quality_failures(computed, policy, independent=frozen["purpose"] == "validation")
        if frozen["detector"]["name"] != "offline" or frozen["detector"]["config"] or frozen["threshold"] != .33:
            failures.append("benchmark configuration differs from the production offline detector")
        if not frozen["detector"]["snapshot_verified"]:
            failures.append("model snapshot is unverified")
        result.check("independent production quality", not failures,
                     "; ".join(failures[:8]) + (f"; {len(failures) - 8} more requirements unmet" if len(failures) > 8 else ""))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result.check("independent benchmark report valid", False, str(exc))


def run_budget(result: Result, repo: Path) -> None:
    """A real repository, under a wall clock.

    The check that catches a stall. A stall has no wrong output to assert
    against, which is exactly why it survived a passing suite once already.
    """
    print(f"budget  ({repo})")
    import repo_scanner

    start = time.time()
    files = repo_scanner.scan_repo(
        str(repo), repo_scanner.ScanConfig(scope="content", max_files=5000))
    elapsed = time.time() - start
    blocks = sum(len(f.blocks or []) for f in files)
    result.check(f"scanned {len(files)} files, {blocks} blocks in {elapsed:.1f}s",
                 elapsed < SCAN_BUDGET_SECONDS,
                 f"over the {SCAN_BUDGET_SECONDS}s budget")

    # Per file as well as in total: one slow file inside a fast total is the
    # shape that grows into a stall on a bigger checkout.
    slowest = ("", 0.0)
    for file_result in files[:400]:
        if not file_result.raw_text:
            continue
        started = time.time()
        repo_scanner._extract_blocks(file_result.raw_text, file_result.path, "content")
        spent = time.time() - started
        if spent > slowest[1]:
            slowest = (file_result.path, spent)
    result.check(f"slowest single file {slowest[1]:.2f}s", slowest[1] < 1.0,
                 f"{slowest[0]} took {slowest[1]:.1f}s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=None,
                        help="a real repository to scan under the time budget")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--skip-quality", action="store_true")
    parser.add_argument("--quality-report", type=Path,
                        help="verify a frozen independent benchmark; without it, only historical diagnostics run")
    args = parser.parse_args()

    result = Result()
    if not args.skip_tests:
        run_tests(result)
    if not args.skip_smoke:
        run_smoke(result)
    if not args.skip_quality:
        if args.quality_report:
            run_quality_report(result, args.quality_report)
        else:
            run_quality(result)
    if args.repo is not None:
        run_budget(result, args.repo.expanduser())

    print()
    if result.failures:
        print(f"{len(result.failures)} check(s) failed:")
        for failure in result.failures:
            print(f"  - {failure}")
        return 1
    print("all selected checks passed" + ("; quality was skipped" if args.skip_quality else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
