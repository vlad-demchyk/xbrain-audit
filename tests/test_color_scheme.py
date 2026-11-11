"""The browser pass can be told the dark colour scheme (T-2337).

Coach's 41 indigo focus rings were 2.65-2.93:1 in its dark theme - found by
hand, because the pass only ever saw `prefers-color-scheme: light`. Run
through the real CLI, because the scheme is a flag of Chromium's process
and has to be set before it starts.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent

PAGE = """<!DOCTYPE html><html lang="en"><head><title>Theme</title><style>
  body { background: #ffffff; color: #111111; }
  a:focus { outline: 3px solid #1e1b4b; outline-offset: 2px; }
  @media (prefers-color-scheme: dark) {
    body { background: #111111; color: #eeeeee; }
    a { color: #eeeeee; }
    a:focus { outline: 3px solid #312e81; }
  }
</style></head><body><main><h1>Theme</h1><p><a href="/a">First link</a></p>
<p><a href="/b">Second link</a></p></main></body></html>"""


def _run(folder: str, *extra) -> dict:
    path = Path(folder) / "theme.html"
    path.write_text(PAGE, encoding="utf-8")
    env = dict(os.environ, XANALYZE_BROWSER_CACHE=str(Path(folder) / "cache"),
               XANALYZE_REPORT_ROOT=str(Path(folder) / "runs"))
    env.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)
    done = subprocess.run(
        [sys.executable, str(ROOT / "cli.py"), "audit", str(path), "--browser",
         "--json", "--unsettled", "--no-update-check", *extra],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=300, cwd=str(ROOT))
    return json.loads(done.stdout), done.stderr


class ThroughTheCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from audit import driver

        usable, reason = driver.available()
        if not usable:
            raise unittest.SkipTest(reason)

    def rules(self, result: dict) -> set:
        return {i["rule_id"] for i in result["issues"]}

    def test_the_dark_theme_ring_is_measured_only_when_asked_for(self):
        with TemporaryDirectory() as folder:
            light, _ = _run(folder)
        with TemporaryDirectory() as folder:
            dark, stderr = _run(folder, "--color-scheme", "dark")
        self.assertNotIn("state:focus-indicator-low-contrast", self.rules(light))
        self.assertIn("state:focus-indicator-low-contrast", self.rules(dark), stderr[-2000:])
        self.assertNotIn("asked for dark", stderr)


class TooLate(unittest.TestCase):
    setUpClass = ThroughTheCli.setUpClass

    def test_a_scheme_chromium_never_got_is_said_not_assumed(self):
        """In this process Chromium started light; asking for dark now
        must not produce a report that calls itself dark."""
        from audit import browser, driver

        with TemporaryDirectory() as folder:
            path = Path(folder) / "theme.html"
            path.write_text(PAGE, encoding="utf-8")
            options = browser.BrowserAuditOptions(
                run_axe=False, run_htmlcs=False, run_states=False,
                run_measurements=False, allow_local_files=True, settle_ms=100,
                color_scheme="dark")
            driver.ensure_headless_application()
            runner = driver.BrowserAuditRunner(options)
            try:
                result = runner.audit(path.resolve().as_uri())
            finally:
                runner.close()
        self.assertIn("color_scheme", result.engine_errors)


if __name__ == "__main__":
    unittest.main()
