"""A finding dismissed as false, with its reason, and counted out loud (T-1963)."""
from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

import suppression
from audit.base import Issue


def _issue(rule="image-alt", source="https://s.test/", snippet="<img>", selector="img"):
    return Issue(rule_id=rule, severity="critical", source=source,
                 snippet=snippet, selector=selector)


class TheAccount(unittest.TestCase):
    def test_nothing_hidden_says_nothing(self):
        account = suppression.account_for_suppressed([_issue()], suppression.Suppressions())
        self.assertEqual(account["hidden"], 0)

    def test_each_level_is_counted_and_a_fingerprint_keeps_its_reason(self):
        dismissed = _issue(snippet='<img src="logo.svg">')
        value = suppression.issue_fingerprint(dismissed)
        lists = suppression.Suppressions(
            rules=["skip-link"], fingerprints=[value],
            labels={value: "logo has a text alternative in the link"})
        issues = [dismissed, _issue(rule="skip-link"), _issue(rule="control-name")]
        account = suppression.account_for_suppressed(issues, lists)
        self.assertEqual(account["hidden"], 2)
        self.assertEqual(account["by_level"], {"fingerprints": 1, "rules": 1})
        self.assertEqual(account["dismissed"], [{
            "rule": "image-alt", "source": "https://s.test/", "fingerprint": value,
            "reason": "logo has a text alternative in the link"}])

    def test_the_account_and_the_filter_agree(self):
        dismissed = _issue()
        lists = suppression.Suppressions(
            fingerprints=[suppression.issue_fingerprint(dismissed)])
        issues = [dismissed, _issue(rule="control-name")]
        kept = suppression.filter_issues(issues, lists)
        account = suppression.account_for_suppressed(issues, lists)
        self.assertEqual(len(issues) - len(kept), account["hidden"])


class TheJsonCarriesTheFingerprint(unittest.TestCase):
    def test_it_is_the_one_the_ignore_file_takes(self):
        from finding_contract import serialize_issue

        issue = _issue()
        self.assertEqual(serialize_issue(issue)["fingerprint"],
                         suppression.issue_fingerprint(issue))


class TheIgnoreCommand(unittest.TestCase):
    def _run(self, **values):
        import cli

        return cli.cmd_ignore(argparse.Namespace(**values))

    def test_it_writes_the_entry_with_its_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._run(fingerprint="0123456789abcdef",
                                       reason="  a  false alarm ", root=tmp), 0)
            text = (Path(tmp) / ".xaudit-ignore").read_text(encoding="utf-8")
            self.assertIn("0123456789abcdef  # a false alarm", text)
            parsed = suppression.Suppressions.parse(text)
            self.assertEqual(parsed.labels["0123456789abcdef"], "a false alarm")

    def test_a_reason_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._run(fingerprint="0123456789abcdef",
                                       reason="  ", root=tmp), 2)
            self.assertFalse((Path(tmp) / ".xaudit-ignore").exists())

    def test_something_that_is_not_a_fingerprint_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._run(fingerprint="image-alt",
                                       reason="x", root=tmp), 2)


if __name__ == "__main__":
    unittest.main()
