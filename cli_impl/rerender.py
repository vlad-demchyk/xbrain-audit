"""`xaudit report <run-folder>`: the reports of a finished run, written again.

A run folder keeps the audit's product (`checkpoint-audit.json`, and
`checkpoint-scan.json` when the text was analysed). A styled report is a view
of that product, and the view changes more often than the site: grouping,
the compact to-check section, a language. Crawling a 104-page intranet again
for half an hour to print the same findings differently is the wrong cost, so
this reads the checkpoint and writes the reports with the current code.

What it applies is what a fresh run would: findings are rebuilt through
`finding_contract.deserialize_finding`, so `privacy` masks them again at
birth; the certainty view (`--unsettled`, `--confidence`) is the one asked
for now; grouping and layout are the current template's. What it cannot do is
change what was found: the rules that ran, and their verdicts, are the run's.
"""
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path


def _original_args(run_dir: Path):
    """The run's own command line, parsed, or `None` when it cannot be."""
    import json

    try:
        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    argv = [str(part) for part in state.get("argv") or []]
    if not argv:
        return None
    from cli import build_parser

    try:
        return build_parser().parse_args(argv)
    except SystemExit:
        return None


def cmd_report(args) -> int:
    from cli_impl import checkpoint
    from cli_impl.fullscan import _write_styled_report

    run_dir = Path(args.run_folder).expanduser()
    result = checkpoint.load_audit(run_dir)
    content, _counts = checkpoint.load_scan(run_dir)
    if result is None and not content:
        print(f"xaudit report: no finished audit in {run_dir} "
              f"(expected {checkpoint.AUDIT_FILE})", file=sys.stderr)
        return 2
    if not args.styled_report:
        print("xaudit report: say where to write it: --styled-report FILE.pdf|.html",
              file=sys.stderr)
        return 2

    original = _original_args(run_dir) or argparse.Namespace()
    # The run's flags head the report (what was measured), with the view and
    # the output asked for now.
    original.styled_report = str(Path(args.styled_report).expanduser())
    original.report = None
    original.unsettled = bool(args.unsettled)
    original.confidence = args.confidence or ""
    original.language = args.language or getattr(original, "language", None)

    from i18n.translations import report_language

    lang = report_language(original.language)
    if result is not None:
        result = result.narrowed(confidence=original.confidence,
                                 unsettled=original.unsettled)
    Path(original.styled_report).parent.mkdir(parents=True, exist_ok=True)
    _write_styled_report(original, result, list(content or []), lang)
    if not Path(original.styled_report).exists():
        print(f"xaudit report: nothing was written to {original.styled_report}",
              file=sys.stderr)
        return 1
    print(f"# report re-rendered from {run_dir} "
          f"({shlex.quote(original.styled_report)})", file=sys.stderr)
    return 0


def add_parser(sub) -> None:
    parser = sub.add_parser(
        "report",
        help="write the reports of a finished run again, from its folder, without crawling",
        description="Re-render the styled report of a finished run from its run "
                    "folder (checkpoint-audit.json), with the current grouping, "
                    "masking and layout. Nothing is crawled or audited again.")
    parser.add_argument("run_folder", help="the run folder, e.g. "
                        "'~/Documents/XBrain Audit/<target>/<timestamp>'")
    parser.add_argument("--styled-report", metavar="FILE",
                        help="where to write it: .pdf or .html")
    parser.add_argument("--language", choices=("en", "uk", "it"), default=None,
                        help="report language (default: the run's)")
    parser.add_argument("--unsettled", action="store_true",
                        help="include what no engine could settle (the to-check section)")
    parser.add_argument("--confidence", default=None,
                        help="certainty floor, as for audit")
    parser.set_defaults(func=cmd_report)
