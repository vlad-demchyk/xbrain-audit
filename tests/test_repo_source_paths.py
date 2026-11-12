"""`fullscan --repo`: a site's findings point at the file that renders them.

Measured on matched content: a готовий HTML page and its PHP template read
the same visible text but disagree on almost everything else - the page
carries `<html lang>`, canonical links and image dimensions that WordPress's
`wp_head()` writes and no template file holds; the template carries the exact
line to edit that the page never says. Neither reading replaces the other.

`--repo` is additive on top of that, not a mode switch: a site scanned
without it behaves exactly as before, because most runs have no checkout to
point at and must not be worse off for lacking one.
"""
from __future__ import annotations

import argparse
import os
import tempfile
import unittest
from pathlib import Path

from lang_detect import guess_language
from models import Confidence, TextBlock, TextSpan


def _block(text, url="https://example.com", language=None, ident=None):
    # The real crawler always runs `guess_language` (never leaves the hint
    # unset), and so does the repo scan on the other side of a `--repo`
    # match - `block_identity` includes the language, so a test block that
    # skipped this would compare against a repo block that never could.
    return TextBlock(block_id=ident or f"{url}:{text[:12]}", page_url=url,
                     dom_path="p", text=text,
                     language_hint=language or guess_language(text))


class _Page:
    def __init__(self, url, blocks):
        self.url = url
        self.blocks = blocks


class _Judge:
    """One high-confidence span per block, deterministically."""
    name = "fake-judge"

    def analyze_blocks(self, blocks):
        return [TextSpan(block_id=b.block_id, start=0, end=len(b.text),
                         score=0.9, confidence=Confidence.HIGH,
                         detector_name=self.name, explanation="because",
                         details={"source": "model"})
                for b in blocks]


class MatchingAPassageToItsFile(unittest.TestCase):
    """`--repo` given, a passage that lives there."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["XAUDIT_JUDGMENT_CACHE"] = self.tmp.name
        self.repo = Path(self.tmp.name).resolve() / "repo"
        self.repo.mkdir()
        (self.repo / "hero.php").write_text(
            "<?php _e('Immerso in un paesaggio unico', 'theme'); ?>\n",
            encoding="utf-8")

    def tearDown(self):
        os.environ.pop("XAUDIT_JUDGMENT_CACHE", None)
        self.tmp.cleanup()

    def _run(self, pages, args):
        from cli_impl import fullscan

        real = fullscan._content_passes
        fullscan._content_passes = lambda _a: [_Judge()]
        try:
            return fullscan._content_findings_from_pages(pages, args)
        finally:
            fullscan._content_passes = real

    def test_a_matched_passage_carries_the_file_and_line(self):
        pages = [_Page("https://example.com",
                       [_block("Immerso in un paesaggio unico")])]
        args = argparse.Namespace(repo=str(self.repo))
        findings = self._run(pages, args)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["source_file"], str(self.repo / "hero.php"))
        self.assertEqual(findings[0]["source_line"], 1)

    def test_the_page_location_is_unchanged(self):
        """`source_file` is additive - `file`/`line` still mean the page."""
        pages = [_Page("https://example.com",
                       [_block("Immerso in un paesaggio unico")])]
        args = argparse.Namespace(repo=str(self.repo))
        findings = self._run(pages, args)
        self.assertEqual(findings[0]["file"], "https://example.com")

    def test_an_unmatched_passage_carries_no_source_file(self):
        pages = [_Page("https://example.com",
                       [_block("Text that is not in the given repo")])]
        args = argparse.Namespace(repo=str(self.repo))
        findings = self._run(pages, args)
        self.assertEqual(len(findings), 1)
        self.assertNotIn("source_file", findings[0])

    def test_without_repo_no_finding_ever_carries_a_source_file(self):
        pages = [_Page("https://example.com",
                       [_block("Immerso in un paesaggio unico")])]
        findings = self._run(pages, argparse.Namespace(repo=None))
        self.assertNotIn("source_file", findings[0])

    def test_args_is_none_is_the_same_as_no_repo(self):
        """`_content_findings_from_pages(pages)` - the pre-existing call
        shape used by every caller that never heard of `--repo`."""
        pages = [_Page("https://example.com",
                       [_block("Immerso in un paesaggio unico")])]
        findings = self._run(pages, None)
        self.assertNotIn("source_file", findings[0])

    def test_every_occurrence_of_a_shared_passage_gets_the_same_source(self):
        pages = [_Page(f"https://example.com/{i}",
                       [_block("Immerso in un paesaggio unico",
                               f"https://example.com/{i}", ident=f"h{i}")])
                for i in range(3)]
        args = argparse.Namespace(repo=str(self.repo))
        findings = self._run(pages, args)
        self.assertEqual(len(findings), 3)
        self.assertTrue(all(f["source_file"] == str(self.repo / "hero.php")
                            for f in findings))
        self.assertEqual({f["file"] for f in findings},
                         {f"https://example.com/{i}" for i in range(3)})


class RepoCoverageStats(unittest.TestCase):
    """`stats_out`: how much of a site's distinct content the given repo
    explains, over every passage - not only the ones that produced a
    finding, since that question has an answer even when nothing was
    flagged."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["XAUDIT_JUDGMENT_CACHE"] = self.tmp.name
        self.repo = Path(self.tmp.name).resolve() / "repo"
        self.repo.mkdir()
        (self.repo / "hero.php").write_text(
            "<?php _e('Immerso in un paesaggio unico', 'theme'); ?>\n",
            encoding="utf-8")

    def tearDown(self):
        os.environ.pop("XAUDIT_JUDGMENT_CACHE", None)
        self.tmp.cleanup()

    def _run(self, pages, args, stats_out):
        from cli_impl import fullscan

        real = fullscan._content_passes
        fullscan._content_passes = lambda _a: [_Judge()]
        try:
            return fullscan._content_findings_from_pages(
                pages, args, stats_out=stats_out)
        finally:
            fullscan._content_passes = real

    def test_matched_and_total_count_distinct_passages(self):
        pages = [_Page("https://example.com",
                       [_block("Immerso in un paesaggio unico"),
                        _block("Nothing like this in the repo",
                               ident="other")])]
        stats: dict = {}
        self._run(pages, argparse.Namespace(repo=str(self.repo)), stats)
        self.assertEqual(stats, {"repo_matched": 1, "repo_total": 2})

    def test_a_passage_repeated_across_pages_counts_once(self):
        pages = [_Page(f"https://example.com/{i}",
                       [_block("Immerso in un paesaggio unico",
                               f"https://example.com/{i}", ident=f"h{i}")])
                for i in range(5)]
        stats: dict = {}
        self._run(pages, argparse.Namespace(repo=str(self.repo)), stats)
        self.assertEqual(stats, {"repo_matched": 1, "repo_total": 1})

    def test_without_repo_stats_out_stays_empty(self):
        pages = [_Page("https://example.com", [_block("Some text")])]
        stats: dict = {}
        self._run(pages, argparse.Namespace(repo=None), stats)
        self.assertEqual(stats, {})


class CommandLineValidation(unittest.TestCase):
    """`--repo` is checked before anything is crawled or written."""

    def test_a_missing_repo_path_fails_before_any_network_call(self):
        from cli_impl import EXIT_ERROR
        from cli_impl.fullscan import cmd_fullscan

        args = argparse.Namespace(
            target="https://example.invalid", url=False, language=None,
            repo="/definitely/does/not/exist")
        # No mocking of the crawl: if this reaches it, the test hangs or
        # errors on the network instead of failing fast and clean.
        self.assertEqual(cmd_fullscan(args), EXIT_ERROR)

    def test_a_repo_path_that_is_a_file_not_a_directory_also_fails(self):
        from cli_impl import EXIT_ERROR
        from cli_impl.fullscan import cmd_fullscan

        with tempfile.NamedTemporaryFile() as f:
            args = argparse.Namespace(
                target="https://example.invalid", url=False, language=None,
                repo=f.name)
            self.assertEqual(cmd_fullscan(args), EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
