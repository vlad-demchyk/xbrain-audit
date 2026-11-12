"""A cached session profile can be let go of, so the sign-in window can read it.

On Windows QtWebEngine locks a profile's `Cookies` file for as long as the
profile is open, and the sign-in window reads the session from that file
before it opens the profile. In the desktop app the profile is cached for the
whole process (`driver._SESSION_PROFILES`), so a browser pass or an earlier
window left the file locked and the window found nothing.
`driver.release_session_profile` closes it first.

Run in its own process: the profile has to be really created, written and
deleted by Chromium, and a test process that shares Qt with the rest of the
suite should not hold a persistent profile. Every value is a placeholder.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent

STEP = r'''
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, sys.argv[1])
from audit import driver
import site_session
from PySide6.QtCore import QByteArray, QDateTime, QUrl
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineCore import QWebEnginePage

host = "contoso.sharepoint.com"
driver.ensure_headless_application()
profile = driver.open_session_profile(host)
# The network context, and with it the cookie database, starts with a page.
page = QWebEnginePage(profile, None)
page.setUrl(QUrl("about:blank"))
driver._pump(500)
cookie = QNetworkCookie(QByteArray(b"FedAuth"), QByteArray(b"placeholder"))
cookie.setDomain(host); cookie.setPath("/"); cookie.setSecure(True)
cookie.setExpirationDate(QDateTime.currentDateTime().addDays(1))
profile.cookieStore().setCookie(cookie, QUrl(f"https://{host}/"))
folder = site_session.profile_dir(host)
files = [folder / "Cookies", folder / "Network" / "Cookies"]
deadline = time.monotonic() + 15
while not any(p.is_file() for p in files) and time.monotonic() < deadline:
    driver._pump(100)
driver._pump(1500)

def opens():
    try:
        for p in files:
            if p.is_file():
                open(p, "rb").close()
        return True
    except OSError:
        return False

print("WRITTEN", any(p.is_file() for p in files))
print("OPEN WHILE HELD", opens())
# A page still using it: release must refuse, not delete under it.
print("REFUSED WITH PAGE", not driver.release_session_profile(host))
page.deleteLater()
print("RELEASED", driver.release_session_profile(host))
print("CACHED AFTER", host in driver._SESSION_PROFILES)
print("OPEN AFTER", opens())
names = [c["name"] for c in site_session.read_profile_cookies(str(folder), host)]
print("READ", names)
print("NOTHING HELD", driver.release_session_profile(host))
'''


class ReleaseLetsTheFileBeRead(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from audit import driver

        usable, reason = driver.available()
        if not usable:
            raise unittest.SkipTest(reason)

    def test_a_held_profile_is_released_and_its_cookies_read(self):
        with TemporaryDirectory() as config:
            env = dict(os.environ, XDG_CONFIG_HOME=config, APPDATA=config)
            done = subprocess.run([sys.executable, "-c", STEP, str(ROOT)],
                                  capture_output=True, text=True, env=env,
                                  timeout=120)
        out = done.stdout
        self.assertIn("WRITTEN True", out, done.stderr[-2000:])
        if sys.platform == "win32":
            # The reason this exists: the open profile locks its file.
            self.assertIn("OPEN WHILE HELD False", out)
        self.assertIn("REFUSED WITH PAGE True", out)
        self.assertIn("RELEASED True", out)
        self.assertIn("CACHED AFTER False", out)
        self.assertIn("OPEN AFTER True", out)
        self.assertIn("READ ['FedAuth']", out)
        self.assertIn("NOTHING HELD True", out)


if __name__ == "__main__":
    unittest.main()
