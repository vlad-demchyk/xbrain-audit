"""What the exit code says, because a pipeline reads nothing else.

The failure this guards against is not a crash but the opposite: a mistyped
path that produced "No findings." and exit 0, which any CI step reads as a
clean pass. Silence has to be distinguishable from success.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXIT_OK = 0
EXIT_ERROR = 2


def _cli(*args):
    return subprocess.run([sys.executable, str(ROOT / "cli.py"), *args],
                          capture_output=True, text=True, encoding="utf-8", timeout=180,
                          cwd=str(ROOT))


class MissingPaths(unittest.TestCase):
    def test_scan_of_a_missing_path_is_an_error(self):
        done = _cli("scan", "/no/such/path/at/all")
        self.assertEqual(done.returncode, EXIT_ERROR)
        self.assertIn("did not exist", done.stderr)

    def test_audit_of_a_missing_path_is_an_error(self):
        done = _cli("audit", "/no/such/path/at/all")
        self.assertEqual(done.returncode, EXIT_ERROR)
        self.assertIn("path not found", done.stderr)

    def test_audit_with_check_does_not_pass_on_a_typo(self):
        # The combination that matters: `--check` in a hook, and a path that
        # moved. It must fail loudly rather than certify nothing.
        done = _cli("audit", "/no/such/path/at/all", "--check")
        self.assertNotEqual(done.returncode, EXIT_OK)


class RealPaths(unittest.TestCase):
    def test_a_clean_page_exits_zero(self):
        with tempfile.TemporaryDirectory() as work:
            page = Path(work) / "index.html"
            page.write_text(
                '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
                '<title>A perfectly ordinary page</title>'
                '<meta name="description" content="'
                + "A description of the right sort of length for a search result, "
                  "which is between seventy and a hundred and sixty characters."
                + '"></head><body><h1>Heading</h1>'
                '<p>Copy that ships to a reader.</p></body></html>',
                encoding="utf-8")
            done = _cli("audit", str(page), "--check", "--no-browser")
            # --no-browser keeps this a test of the exit-code contract for
            # markup alone; the automatic browser pass would rightly flag
            # this synthetic page (no viewport meta) as imperfect.
            self.assertEqual(done.returncode, EXIT_OK, done.stdout[-400:])


if __name__ == "__main__":
    unittest.main()
