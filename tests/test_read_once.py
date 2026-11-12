"""Each distinct passage is read once per run, and once ever.

A crawl of ten pages of one site produced 573 blocks and **236 distinct
texts**: a header and a footer appear on every page, so `Tel. +39 0432
924815` was read 26 times. The offline pass paid for that in wasted local
work; the judge paid in network round trips, and on the Claude Code route
each round trip is a process start of about seven seconds.

The cache carries a second job. The judge is **not deterministic** - two runs
of one site with identical flags returned 6 findings and then 24 - and no
route here exposes a temperature or a seed, so identical output cannot be
requested from the model. It can only be remembered.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import judgment_cache
from duplicates import block_identity, distinct_blocks
from models import Confidence, TextBlock, TextSpan


def _block(text, url="https://example.com", language=None, ident=None):
    return TextBlock(block_id=ident or f"{url}:{text[:12]}", page_url=url,
                     dom_path="p", text=text, language_hint=language)


class WhatCountsAsTheSamePassage(unittest.TestCase):
    def test_identical_text_on_two_pages_is_one_passage(self):
        a = _block("Tel. +39 0432 924815", "https://example.com/a")
        b = _block("Tel. +39 0432 924815", "https://example.com/b")
        self.assertEqual(block_identity(a), block_identity(b))

    def test_whitespace_does_not_make_a_new_passage(self):
        self.assertEqual(block_identity(_block("a  b\n c")),
                         block_identity(_block("a b c")))

    def test_a_per_page_generated_id_does_not_make_a_new_passage(self):
        """A menu that renders with a fresh uuid is still one menu."""
        a = _block('<span id="toc-6a8c2c05ce8bd">Menu</span>')
        b = _block('<span id="toc-6a8c2c534c8eb">Menu</span>')
        self.assertEqual(block_identity(a), block_identity(b))

    def test_the_language_is_part_of_the_identity(self):
        """The detectors genuinely answer differently for it.

        The same string read as Italian and as English is two questions, and
        collapsing them would silently pick one answer for both.
        """
        self.assertNotEqual(block_identity(_block("Ciao", language="it")),
                            block_identity(_block("Ciao", language="en")))

    def test_different_text_stays_different(self):
        self.assertNotEqual(block_identity(_block("one")),
                            block_identity(_block("two")))


class Grouping(unittest.TestCase):
    def test_a_header_on_ten_pages_is_one_group(self):
        blocks = [_block("Shared header", f"https://example.com/{i}")
                  for i in range(10)]
        groups = distinct_blocks(blocks)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0][1]), 10)

    def test_every_occurrence_is_kept(self):
        """Reading once is about what is asked, never about what is reported.

        A fix has to visit each page that carries the passage.
        """
        blocks = [_block("Shared", f"https://example.com/{i}") for i in range(4)]
        _first, occurrences = distinct_blocks(blocks)[0]
        self.assertEqual([b.page_url for b in occurrences],
                         [f"https://example.com/{i}" for i in range(4)])

    def test_the_representative_is_the_first_seen(self):
        blocks = [_block("Shared", "https://example.com/first"),
                  _block("Shared", "https://example.com/second")]
        self.assertEqual(distinct_blocks(blocks)[0][0].page_url,
                         "https://example.com/first")

    def test_arrival_order_is_preserved(self):
        blocks = [_block("a"), _block("b"), _block("a"), _block("c")]
        texts = [rep.text for rep, _ in distinct_blocks(blocks)]
        self.assertEqual(texts, ["a", "b", "c"])

    def test_nothing_in_means_nothing_out(self):
        self.assertEqual(distinct_blocks([]), [])


class _Counting:
    """A detector that records how much it was asked to do."""

    name = "counting-judge"
    batch_size = 8

    def __init__(self, score=0.9):
        self.calls = 0
        self.passages = 0
        self.score = score

    def analyze_blocks(self, blocks):
        self.calls += 1
        self.passages += len(blocks)
        return [TextSpan(block_id=b.block_id, start=0, end=len(b.text),
                         score=self.score, confidence=Confidence.HIGH,
                         detector_name=self.name, explanation="because",
                         details={"source": "model"})
                for b in blocks]


class _Page:
    def __init__(self, url, blocks):
        self.url = url
        self.blocks = blocks


class ReadOncePerRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["XAUDIT_JUDGMENT_CACHE"] = self.tmp.name

    def tearDown(self):
        os.environ.pop("XAUDIT_JUDGMENT_CACHE", None)
        self.tmp.cleanup()

    def _run(self, pages, detector, args=None):
        from cli_impl import fullscan

        real = fullscan._content_passes
        fullscan._content_passes = lambda _a: [detector]
        try:
            return fullscan._content_findings_from_pages(pages, args)
        finally:
            fullscan._content_passes = real

    def _site(self, pages=10):
        """A site whose every page carries the same header and its own body."""
        return [_Page(f"https://example.com/{i}",
                      [_block("Tel. +39 0432 924815", f"https://example.com/{i}",
                              ident=f"h{i}"),
                       _block(f"Body text of page {i}", f"https://example.com/{i}",
                              ident=f"b{i}")])
                for i in range(pages)]

    def test_a_shared_header_is_judged_once(self):
        detector = _Counting()
        self._run(self._site(10), detector)
        # Ten headers plus ten distinct bodies: eleven passages, not twenty.
        self.assertEqual(detector.passages, 11)

    def test_deduplication_spans_the_whole_run_not_one_page(self):
        """The repetition worth removing is the one a page cannot see."""
        detector = _Counting()
        self._run(self._site(10), detector)
        self.assertEqual(detector.calls, 2)     # 11 passages, batches of 8

    def test_every_page_still_gets_its_finding(self):
        findings = self._run(self._site(10), _Counting())
        header = [f for f in findings if "0432" in f["text"]]
        self.assertEqual(len(header), 10)
        self.assertEqual(len({f["file"] for f in header}), 10)

    def test_a_verdict_lands_on_the_page_it_was_found_on(self):
        findings = self._run(self._site(3), _Counting())
        for finding in findings:
            self.assertTrue(finding["file"].startswith("https://example.com/"))

    def test_one_page_is_unaffected(self):
        page = _Page("https://example.com", [_block("only text")])
        detector = _Counting()
        self._run([page], detector)
        self.assertEqual(detector.passages, 1)


class ReadOnceAcrossRuns(unittest.TestCase):
    """The cache is what makes a repeat run reproducible."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["XAUDIT_JUDGMENT_CACHE"] = self.tmp.name

    def tearDown(self):
        os.environ.pop("XAUDIT_JUDGMENT_CACHE", None)
        self.tmp.cleanup()

    def _run(self, detector, args=None):
        from cli_impl import fullscan

        pages = [_Page("https://example.com",
                       [_block("A passage worth judging")])]
        real = fullscan._content_passes
        fullscan._content_passes = lambda _a: [detector]
        try:
            return fullscan._content_findings_from_pages(pages, args)
        finally:
            fullscan._content_passes = real

    def test_a_second_run_asks_nothing(self):
        first = _Counting()
        self._run(first)
        second = _Counting()
        self._run(second)
        self.assertEqual(first.passages, 1)
        self.assertEqual(second.passages, 0)

    def test_a_second_run_reports_the_same_thing(self):
        """The point: the judge is not deterministic, so the answer is
        remembered rather than re-requested."""
        before = self._run(_Counting(score=0.9))
        # A detector that would now answer differently. The cache means it is
        # never asked, so the report does not move.
        after = self._run(_Counting(score=0.1))
        self.assertEqual([f["score"] for f in before],
                         [f["score"] for f in after])

    def test_the_bypass_gets_a_fresh_opinion(self):
        """A cached wrong answer must not be un-fixable."""
        import argparse

        self._run(_Counting(score=0.9))
        detector = _Counting(score=0.1)
        self._run(detector, argparse.Namespace(no_judgment_cache=True,
                                               detector="ai"))
        self.assertEqual(detector.passages, 1)

    def test_a_changed_model_is_a_changed_question(self):
        from detectors.claude_llm_judge import _SYSTEM_PROMPT

        one = judgment_cache.JudgmentCache("j", model="sonnet",
                                           prompt=_SYSTEM_PROMPT,
                                           directory=Path(self.tmp.name))
        two = judgment_cache.JudgmentCache("j", model="opus",
                                           prompt=_SYSTEM_PROMPT,
                                           directory=Path(self.tmp.name))
        self.assertNotEqual(one.path, two.path)

    def test_a_changed_effort_is_a_changed_question(self):
        one = judgment_cache.JudgmentCache("j", effort="low",
                                           directory=Path(self.tmp.name))
        two = judgment_cache.JudgmentCache("j", effort="high",
                                           directory=Path(self.tmp.name))
        self.assertNotEqual(one.path, two.path)

    def test_a_changed_rubric_is_a_changed_question(self):
        """Versioned by the prompt's own text, so editing the rubric
        invalidates every entry with nobody having to bump a number."""
        one = judgment_cache.JudgmentCache("j", prompt="rate this",
                                           directory=Path(self.tmp.name))
        two = judgment_cache.JudgmentCache("j", prompt="rate this, carefully",
                                           directory=Path(self.tmp.name))
        self.assertNotEqual(one.path, two.path)

    def test_the_offline_pass_is_not_cached(self):
        """Deterministic and a tenth of a second: a cache would add a disk
        round trip and a staleness risk to buy nothing."""
        from cli_impl import fullscan

        class Offline:
            name = "offline"

        self.assertIsNone(fullscan._cache_for(Offline(), None))


class CacheMechanics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = judgment_cache.JudgmentCache(
            "j", directory=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_miss_is_none_and_a_hit_is_the_stored_verdict(self):
        self.assertIsNone(self.cache.get("nothing here"))
        self.cache.put("a passage", [{"score": 0.5}])
        self.assertEqual(self.cache.get("a passage"), [{"score": 0.5}])

    def test_it_survives_a_reload(self):
        self.cache.put("a passage", [{"score": 0.5}])
        self.cache.save()
        again = judgment_cache.JudgmentCache("j", directory=Path(self.tmp.name))
        self.assertEqual(again.get("a passage"), [{"score": 0.5}])

    def test_an_unreadable_file_is_an_empty_cache_not_a_crash(self):
        self.cache.path.parent.mkdir(parents=True, exist_ok=True)
        self.cache.path.write_text("{not json", encoding="utf-8")
        again = judgment_cache.JudgmentCache("j", directory=Path(self.tmp.name))
        self.assertEqual(len(again), 0)

    def test_a_stale_entry_is_dropped(self):
        import json
        import time

        self.cache.path.parent.mkdir(parents=True, exist_ok=True)
        key = judgment_cache.JudgmentCache.passage_key("old")
        old = time.time() - (judgment_cache.MAX_AGE_DAYS + 1) * 86400
        self.cache.path.write_text(
            json.dumps({key: {"at": int(old), "spans": []}}), encoding="utf-8")
        again = judgment_cache.JudgmentCache("j", directory=Path(self.tmp.name))
        self.assertEqual(len(again), 0)

    def test_clearing_removes_the_file(self):
        self.cache.put("a", [])
        self.cache.save()
        self.cache.clear()
        self.assertFalse(self.cache.path.exists())

    def test_the_summary_says_what_was_saved(self):
        self.cache.put("a", [])
        self.cache.get("a")
        self.cache.get("b")
        self.assertIn("1/2", self.cache.summary())

    def test_a_span_survives_the_round_trip(self):
        block = _block("some passage")
        span = TextSpan(block_id=block.block_id, start=2, end=6, score=0.42,
                        confidence=Confidence.MEDIUM, detector_name="j",
                        explanation="why", details={"source": "model"})
        back = judgment_cache.record_to_span(
            judgment_cache.span_to_record(span), block)
        for attribute in ("start", "end", "score", "detector_name",
                          "explanation", "details"):
            self.assertEqual(getattr(back, attribute),
                             getattr(span, attribute), attribute)
        self.assertEqual(back.confidence, Confidence.MEDIUM)

    def test_a_verdict_is_rebuilt_against_the_place_it_is_reported_at(self):
        """The identity is the passage; the place is not part of it."""
        stored = judgment_cache.span_to_record(
            TextSpan(block_id="original", start=0, end=3, score=0.5,
                     confidence=Confidence.MEDIUM, detector_name="j"))
        elsewhere = _block("some passage", "https://other.example", ident="other")
        self.assertEqual(
            judgment_cache.record_to_span(stored, elsewhere).block_id, "other")


if __name__ == "__main__":
    unittest.main()


class TheAgentPathReadsOnceToo(unittest.TestCase):
    """The agent pays for every candidate it is handed, whichever model.

    That is the point of this path - the agent is the judge, with its own
    model and its own bill - so handing it the same header ten times is ten
    times the cost of one answer. It used to: the only guard was `block_id`,
    which is a fresh uuid per block, so it deduplicated nothing across pages.
    Measured on a ten-page site: 124 candidates, 68 distinct, 45% repeats.
    """

    def _site(self, pages=6):
        return [_Page(f"https://example.com/{i}", [
            _block("Unlock the potential of your seamless journey today",
                   f"https://example.com/{i}", ident=f"h{i}"),
            _block(f"In today's fast-paced world, page {i} delivers value",
                   f"https://example.com/{i}", ident=f"b{i}")])
            for i in range(pages)]

    def test_a_site_wide_passage_is_offered_once(self):
        from cli_impl.fullscan import _agent_candidates_from_pages

        candidates = _agent_candidates_from_pages(self._site(6))
        texts = [c["text"] for c in candidates]
        self.assertEqual(len(texts), len(set(texts)))

    def test_every_place_travels_with_the_candidate(self):
        """The verdict has to reach all of them, so the agent must be told."""
        from cli_impl.fullscan import _agent_candidates_from_pages

        candidates = _agent_candidates_from_pages(self._site(6))
        shared = [c for c in candidates if c.get("occurrences", 1) > 1]
        self.assertTrue(shared)
        self.assertEqual(shared[0]["occurrences"], len(shared[0]["places"]))

    def test_the_places_are_the_pages_it_appears_on(self):
        from cli_impl.fullscan import _agent_candidates_from_pages

        candidates = _agent_candidates_from_pages(self._site(4))
        shared = [c for c in candidates if c.get("occurrences", 1) > 1][0]
        self.assertEqual(sorted(shared["places"]),
                         sorted(f"https://example.com/{i}" for i in range(4)))

    def test_a_repo_candidate_carries_file_and_line(self):
        from cli_impl.fullscan import _agent_candidates_from_blocks
        from models import CodeBlock

        blocks = [CodeBlock(block_id=f"c{i}", file_path=f"src/{i}.py",
                            start=0, end=40, line_number=12,
                            text="Unlock the potential of your seamless journey")
                  for i in range(3)]
        candidates = _agent_candidates_from_blocks(blocks)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["places"],
                         ["src/0.py:12", "src/1.py:12", "src/2.py:12"])


class OneJudgmentReachesEveryPlace(unittest.TestCase):
    """Deduplication must not become data loss.

    The matcher consumed each judgment once, which is right for a match on a
    *place* and wrong for a match on a *passage*: with one judgment per
    distinct wording, consuming would give the verdict to the first page and
    leave the rest unjudged.
    """

    class _Block:
        def __init__(self, path, line, text):
            self.block_id = f"{path}:{line}"
            self.file_path = path
            self.line_number = line
            self.text = text

    def _matcher(self, judgments, blocks):
        from cli_impl.agentcmds import _OriginMatcher

        return _OriginMatcher(judgments, [], blocks,
                              {b.block_id: b for b in blocks})

    def test_one_wording_judgment_serves_every_occurrence(self):
        blocks = [self._Block(f"p{i}.html", 3, "Shared header text")
                  for i in range(5)]
        matcher = self._matcher([{"text": "Shared header text", "score": 0.8}],
                                blocks)
        matched = [matcher.match_judgment(b) for b in blocks]
        self.assertTrue(all(m is not None for m in matched))
        self.assertEqual(len({id(m) for m in matched}), 1)

    def test_a_place_specific_judgment_is_still_consumed_once(self):
        """Two blocks at two places deserve two judgments, not one twice."""
        blocks = [self._Block("a.html", 3, "same wording"),
                  self._Block("b.html", 4, "same wording")]
        judgments = [{"file": "a.html", "line": 3, "text": "same wording",
                      "score": 0.8},
                     {"file": "b.html", "line": 4, "text": "same wording",
                      "score": 0.2}]
        matcher = self._matcher(judgments, blocks)
        first = matcher.match_judgment(blocks[0])
        second = matcher.match_judgment(blocks[1])
        self.assertEqual(first["score"], 0.8)
        self.assertEqual(second["score"], 0.2)

    def test_an_unjudged_block_still_gets_nothing(self):
        blocks = [self._Block("a.html", 1, "never judged")]
        matcher = self._matcher([{"text": "something else"}], blocks)
        self.assertIsNone(matcher.match_judgment(blocks[0]))


class TheSubscriptionSaysWhatDoesNotApply(unittest.TestCase):
    """A flag accepted and ignored is the defect, however good the reason."""

    def test_model_and_effort_are_reported_as_inapplicable(self):
        import argparse
        import contextlib
        import io

        from cli_impl.scanning import _create_detector

        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            _create_detector(argparse.Namespace(
                detector="xformat-llm-judge", provider="xformat",
                model="sonnet", effort="low"))
        note = captured.getvalue()
        self.assertIn("xFormat", note)
        self.assertIn("--model", note)

    def test_nothing_is_said_when_nothing_was_asked_for(self):
        import argparse
        import contextlib
        import io

        from cli_impl.scanning import _create_detector

        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            _create_detector(argparse.Namespace(
                detector="xformat-llm-judge", provider="xformat",
                model=None, effort=None))
        self.assertEqual(captured.getvalue(), "")
