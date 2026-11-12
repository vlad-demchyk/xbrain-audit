"""A report never carries the signed-in person's login, hash or address.

Seen on a live intranet audit: an embedded survey quoted as
`<iframe src="https://survey.example/home?username=<login>&hash=<per-user
hash>&type=intranet">` in the snippet, the details and the fix, in the JSON,
the HTML report and stderr. Everything here is synthetic.
"""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr

from audit.base import ACCESSIBILITY, Issue
from privacy import EMAIL_PLACEHOLDER, PLACEHOLDER, mask_text, mask_value

SURVEY = ("https://survey.example/home?username=jdoe&hash=0123abcdef456789"
          "&type=intranet")


class MaskText(unittest.TestCase):

    def test_sensitive_parameter_values_are_masked_names_kept(self):
        masked = mask_text(SURVEY)
        self.assertNotIn("jdoe", masked)
        self.assertNotIn("0123abcdef456789", masked)
        self.assertIn(f"username={PLACEHOLDER}", masked)
        self.assertIn(f"hash={PLACEHOLDER}", masked)
        self.assertIn("type=intranet", masked)
        self.assertIn("https://survey.example/home?", masked)

    def test_html_escaped_ampersands_and_case(self):
        masked = mask_text('<iframe src="/s?Type=a&amp;UserName=jdoe&amp;Token=x1">')
        self.assertNotIn("jdoe", masked)
        self.assertNotIn("x1", masked)
        self.assertIn("Type=a", masked)

    def test_every_listed_parameter(self):
        for name in ("user", "email", "mail", "token", "access_token", "auth",
                     "key", "sig", "signature", "session", "sid", "code",
                     "password", "pwd", "upn", "login"):
            with self.subTest(name=name):
                self.assertEqual(mask_text(f"/x?{name}=secret1&a=1"),
                                 f"/x?{name}={PLACEHOLDER}&a=1")

    def test_a_longer_name_is_not_a_listed_one(self):
        for text in ("/x?keyword=shoes", "/x?username_hint=a=1", "/x?monkey=1",
                     '<div data-user="x">'):
            with self.subTest(text=text):
                self.assertEqual(mask_text(text), text)

    def test_percent_encoded_inside_another_parameter(self):
        masked = mask_text("/login?next=%2Fhome%3Fusername%3Djdoe%26a%3D1")
        self.assertNotIn("jdoe", masked)
        self.assertIn("%26a%3D1", masked)

    def test_email_addresses_and_not_retina_files(self):
        masked = mask_text('<a href="mailto:j.doe@contoso.example">j.doe@contoso.example</a>'
                           '<img src="logo@2x.png"> /u/j.doe%40contoso.example')
        self.assertNotIn("j.doe", masked)
        self.assertEqual(masked.count(EMAIL_PLACEHOLDER), 3)
        self.assertIn("logo@2x.png", masked)

    def test_idempotent_and_safe_on_anything(self):
        once = mask_text(SURVEY)
        self.assertEqual(mask_text(once), once)
        self.assertIsNone(mask_text(None))
        self.assertEqual(mask_value({"a": [SURVEY, 3, None]})["a"][1:], [3, None])


class AFindingIsMaskedAtBirth(unittest.TestCase):

    def _issue(self):
        return Issue(rule_id="sec-frame-sandbox", severity="minor",
                     category=ACCESSIBILITY, source="https://contoso.sharepoint.com/p",
                     snippet=f'<iframe src="{SURVEY}">',
                     details={"src": SURVEY, "nested": [{"url": SURVEY}]},
                     fix_snippet=f'<iframe sandbox src="{SURVEY}">',
                     selector=f'iframe[src="{SURVEY}"]')

    def test_snippet_details_fix_and_selector(self):
        issue = self._issue()
        dumped = json.dumps([issue.snippet, issue.details, issue.fix_snippet,
                             issue.selector])
        self.assertNotIn("jdoe", dumped)
        self.assertNotIn("0123abcdef456789", dumped)

    def test_the_fingerprint_does_not_depend_on_the_person(self):
        from suppression import issue_fingerprint

        mine = self._issue()
        theirs = Issue(rule_id="sec-frame-sandbox", severity="minor",
                       source=mine.source,
                       snippet=f'<iframe src="{SURVEY.replace("jdoe", "asmith").replace("0123", "9a9a")}">')
        self.assertEqual(issue_fingerprint(mine), issue_fingerprint(theirs))

    def test_the_json_record_fingerprint_is_the_one_recomputed_from_it(self):
        from audit.precision import finding_fingerprint
        from finding_contract import serialize_issue

        record = mask_value(serialize_issue(self._issue()))
        self.assertEqual(record["fingerprint"], finding_fingerprint(record))
        self.assertNotIn("jdoe", json.dumps(record))


class EveryBoundaryMasks(unittest.TestCase):

    def test_progress_lines_on_stderr(self):
        import progress

        buffer = io.StringIO()
        with redirect_stderr(buffer):
            progress.notice("browser", f"failed {SURVEY}",
                            human=f"# failed {SURVEY} j.doe@contoso.example")
        self.assertNotIn("jdoe", buffer.getvalue())
        self.assertNotIn("j.doe@", buffer.getvalue())

    def test_the_styled_report(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from report import export

        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(export, "render_html",
                                  return_value=f"<p>{SURVEY}</p>"):
            target = Path(folder) / "r.html"
            export.write_styled_report(target, object(), "en")
            self.assertNotIn("jdoe", target.read_text(encoding="utf-8"))

    def test_the_browser_console_forwarded_by_qt(self):
        from audit import driver

        buffer = io.StringIO()
        driver.write_qt_message(f"js: Refused to load '{SURVEY}'", stream=buffer)
        self.assertIn("js: Refused to load", buffer.getvalue())
        self.assertNotIn("jdoe", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
