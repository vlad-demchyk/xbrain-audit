"""A sign-in kept in localStorage survives into a later run (T-2337).

Coach keeps its Supabase session in localStorage, not in a cookie. If
`xaudit login` kept only cookies, every audit behind the sign-in would see
the sign-in wall. Run as two processes, as `login` and `audit` are, so the
storage has to reach the disk.
"""
from __future__ import annotations

import functools
import http.server
import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent

LOGIN = """<!DOCTYPE html><html lang="en"><head><title>Login</title></head><body>
<main><h1>Login</h1></main><script>localStorage.setItem('sb-token', 'abc');
document.title = 'stored';</script></body></html>"""
APP = """<!DOCTYPE html><html lang="en"><head><title>App</title></head><body>
<main id="m"></main><script>document.getElementById('m').innerHTML =
localStorage.getItem('sb-token') ? '<h1>Signed in</h1>' : '<h1>Sign-in wall</h1>';
</script></body></html>"""

STEP = r'''
import os, re, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, sys.argv[3])
from audit import browser, driver
from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
step, host = sys.argv[1], sys.argv[2]
driver.ensure_headless_application()
if step == "login":
    page = QWebEnginePage(driver.open_session_profile(host), None)
    loop = QEventLoop(); page.loadFinished.connect(lambda ok: loop.quit())
    page.setUrl(QUrl(f"http://{host}/login.html")); loop.exec()
    QTimer.singleShot(1000, loop.quit); loop.exec()
    print("TITLE", page.title())
    # What Done does: the sign-in is confirmed. A localStorage-only sign-in
    # has no cookies, and Done still makes it a session (P-25).
    import site_session; site_session.save_cookies(host, [])
    page.deleteLater(); QTimer.singleShot(300, loop.quit); loop.exec()
else:
    profile = driver.session_profile(f"http://{host}/")
    options = browser.BrowserAuditOptions(
        run_axe=False, run_htmlcs=False, run_states=False, run_measurements=False,
        settle_ms=300, capture_html=True, capture_text=False)
    runner = driver.BrowserAuditRunner(options, profile=profile)
    result = runner.audit(f"http://{host}/app.html"); runner.close()
    print("MAIN", re.search(r'<main id="m">(.*?)</main>', result.html).group(1))
'''


class AcrossTwoRuns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from audit import driver

        usable, reason = driver.available()
        if not usable:
            raise unittest.SkipTest(reason)

    def test_the_audit_sees_what_the_sign_in_stored(self):
        with TemporaryDirectory() as site, TemporaryDirectory() as config:
            Path(site, "login.html").write_text(LOGIN, encoding="utf-8")
            Path(site, "app.html").write_text(APP, encoding="utf-8")
            handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                        directory=site)
            handler.log_message = lambda *a, **k: None
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            host = f"127.0.0.1:{server.server_address[1]}"
            env = dict(os.environ, XDG_CONFIG_HOME=config)

            def run(step: str) -> str:
                done = subprocess.run([sys.executable, "-c", STEP, step, host, str(ROOT)],
                                      capture_output=True, text=True, env=env, timeout=120)
                return done.stdout

            try:
                before = run("audit")
                self.assertIn("MAIN <h1>Sign-in wall</h1>", before)
                self.assertIn("TITLE stored", run("login"))
                self.assertIn("MAIN <h1>Signed in</h1>", run("audit"))
            finally:
                server.shutdown()


if __name__ == "__main__":
    unittest.main()
