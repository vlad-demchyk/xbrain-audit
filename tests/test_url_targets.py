"""A target typed without `https://` is a website, not a missing path.

`xaudit fullscan example.com` answered `path not found: example.com` -
the wrong answer to a question with one obvious reading. These pin the
heuristic that decides, in both directions: a bare host is a site, and
anything that could be a path stays a path.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from cli_impl.auditpass import looks_like_url, with_scheme


class LooksLikeUrl(unittest.TestCase):
    def test_explicit_scheme(self):
        self.assertTrue(looks_like_url("https://example.com"))
        self.assertTrue(looks_like_url("http://example.com/a/b?c=1"))

    def test_bare_host(self):
        for target in ("example.com", "www.example.co.uk",
                       "sub.domain.example.com", "example.com/pricing",
                       "example.com?ref=1", "xn--80ak6aa92e.com"):
            with self.subTest(target=target):
                self.assertTrue(looks_like_url(target))

    def test_host_with_port(self):
        self.assertTrue(looks_like_url("localhost:8000"))
        self.assertTrue(looks_like_url("127.0.0.1:8000/admin"))

    def test_internationalised_host(self):
        self.assertTrue(looks_like_url("приклад.укр"))

    def test_paths_stay_paths(self):
        for target in ("./src", "src", "/tmp", "~/repo", ".xaudit",
                       "some_folder", "a/b/c"):
            with self.subTest(target=target):
                self.assertFalse(looks_like_url(target))

    def test_missing_file_is_not_a_host(self):
        """`page.html` is TLD-shaped and must still read as a file.

        Otherwise a mistyped file name is crawled as a website and the real
        answer - it is not there - never reaches the user.
        """
        for target in ("page.html", "missing.py", "notes.md",
                       "archive.tar.gz", "styles.css"):
            with self.subTest(target=target):
                self.assertFalse(looks_like_url(target))

    def test_other_schemes_are_not_ours(self):
        self.assertFalse(looks_like_url("file:///tmp/a.html"))
        self.assertFalse(looks_like_url("mailto:a@b.c"))

    def test_empty(self):
        self.assertFalse(looks_like_url(""))

    def test_existing_path_wins_over_host_shape(self):
        """A directory genuinely named like a domain is still a directory."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "example.com").mkdir()
            previous = os.getcwd()
            os.chdir(tmp)
            try:
                self.assertFalse(looks_like_url("example.com"))
            finally:
                os.chdir(previous)


class WithScheme(unittest.TestCase):
    def test_adds_https(self):
        self.assertEqual(with_scheme("example.com"), "https://example.com")

    def test_keeps_explicit_scheme(self):
        self.assertEqual(with_scheme("http://a.b"), "http://a.b")
        self.assertEqual(with_scheme("https://a.b"), "https://a.b")


class GlobalFlagPlacement(unittest.TestCase):
    """`--no-update-check` belongs to the command as much as to the program.

    It used to be accepted only before the subcommand, so the natural
    `xaudit fullscan X --no-update-check` failed with "unrecognized
    arguments".
    """

    def parse(self, argv):
        import cli
        return cli.build_parser().parse_args(argv)

    def test_before_subcommand(self):
        self.assertTrue(self.parse(["--no-update-check", "scan", "."])
                        .no_update_check)

    def test_after_subcommand(self):
        self.assertTrue(self.parse(["scan", ".", "--no-update-check"])
                        .no_update_check)

    def test_default_is_off(self):
        self.assertFalse(self.parse(["scan", "."]).no_update_check)

    def test_nested_subcommand(self):
        self.assertTrue(self.parse(["cache", "stats", "--no-update-check"])
                        .no_update_check)

    def test_before_does_not_lose_to_subparser_default(self):
        """The regression `default=SUPPRESS` exists to prevent.

        With an ordinary `default=False` on the subparser copy, a flag given
        before the subcommand is overwritten by the subparser's default.
        """
        self.assertTrue(self.parse(["--no-update-check", "audit", "x"])
                        .no_update_check)


if __name__ == "__main__":
    unittest.main()
