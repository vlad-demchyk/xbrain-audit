"""A keyboard trap is where real keys cannot leave, not where Tab is cancelled.

The state script flags an element whose Tab keydown is cancelled. Every
roving-tabindex widget does that (Fluent's FocusZone, a menu, a tab list) and
moves focus itself - out of the widget. On a live intranet the custom
header's links were reported as traps that way. The runner now presses Tab
and Shift+Tab for real and keeps the finding only when focus never leaves.
Synthetic markup; the browser really runs.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Traps</title>
<style>button:focus, a:focus { outline: 3px solid #000; }</style></head><body>
<a href="#before">Before</a>
<div role="toolbar" aria-label="Formatting" class="roving">
  <button type="button" tabindex="0">Bold</button>
  <button type="button" tabindex="-1">Italic</button>
  <button type="button" tabindex="-1">Underline</button>
</div>
<a href="#between" id="between">Between</a>
<div class="trap">
  <button type="button" class="first">One</button>
  <button type="button" class="second">Two</button>
</div>
<a href="#after">After</a>
<script>
  // A roving toolbar, the FocusZone way: Tab is cancelled and focus is moved
  // by the widget itself, to the next stop after the toolbar.
  document.querySelector('.roving').addEventListener('keydown', function(event) {
    if (event.key !== 'Tab') return;
    event.preventDefault();
    var next = event.shiftKey ? document.querySelector('a[href="#before"]')
                              : document.getElementById('between');
    next.focus();
  });
  // A real trap: Tab cycles inside, and leaving pulls focus back.
  var trap = document.querySelector('.trap');
  trap.addEventListener('keydown', function(event) {
    if (event.key !== 'Tab') return;
    event.preventDefault();
    var buttons = trap.querySelectorAll('button');
    (document.activeElement === buttons[0] ? buttons[1] : buttons[0]).focus();
  });
  trap.addEventListener('focusout', function(event) {
    if (!trap.contains(event.relatedTarget)) {
      setTimeout(function() { trap.querySelector('.first').focus(); }, 0);
    }
  });
</script></body></html>"""


class TrapsAreTriedWithRealKeys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from audit import browser, driver

        usable, reason = driver.available()
        if not usable:
            raise unittest.SkipTest(reason)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "traps.html"
            path.write_text(PAGE, encoding="utf-8")
            driver.ensure_headless_application()
            runner = driver.BrowserAuditRunner(browser.BrowserAuditOptions(
                run_axe=False, run_htmlcs=False, run_states=True, run_measurements=False,
                allow_local_files=True, settle_ms=200))
            try:
                cls.audit = runner.audit(path.resolve().as_uri())
            finally:
                runner.close()
        cls.traps = [issue for issue in cls.audit.issues if issue.rule_id == "state:keyboard-trap"]

    def test_a_roving_tabindex_toolbar_is_not_a_trap(self):
        self.assertFalse(any("Bold" in issue.snippet for issue in self.traps))

    def test_a_container_that_pulls_focus_back_is_a_trap(self):
        hits = [issue for issue in self.traps if 'class="first"' in issue.snippet
                or 'class="second"' in issue.snippet]
        self.assertTrue(hits)
        self.assertIn("real Tab", hits[0].details.get("verified", ""))


if __name__ == "__main__":
    unittest.main()
