"""`corpus/promotional.jsonl`: human writing whose job is to make you want
something.

Every human entry this project had was one of three registers - interface
strings, documentation, encyclopedic paragraphs - and a scan is pointed at
none of them. `P-03` said so and `P-06` measured the cost on a live Italian
hotel page: the offline pass found nothing there, and the reason was not the
language label or the length ceiling but that the Italian lists do not hold
what promotional copy is made of.

Adding what they lack is a two-sided change, and until this file existed only
one side could be counted. `nel cuore di` is not evidence of a model - it is
how a person writes about a town square - so a list that gains a phrase
without a promotional yardstick has traded precision for recall in the dark.

Dated Wikivoyage revisions are that yardstick: a travel guide is marketing
writing by function, and a MediaWiki revision id makes "a person wrote this,
and it is dated" checkable per row rather than asserted.

Measured 2026-08-31, the first time this file existed: **four** of these human
paragraphs crossed the reporting threshold. Three on a single word each, one
on a structural pattern. All four causes were counted on both sides and
removed; held-out recall did not move (en 11/20, it 4/11, uk 10/14) and false
alarms on this register went **4 to 0**.
"""
import json
import re
import unittest
from pathlib import Path

from detectors.heuristic import (
    CLICHE_PHRASES, STRUCTURAL_PATTERNS, HeuristicDetector,
)
from lang_detect import guess_language_safe
from models import TextBlock

CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "promotional.jsonl"
THRESHOLD = 0.33

#: Removed by that audit, with what each one was worth beside it. Named here
#: so putting one back needs the same counting rather than a hunch.
#:
#: `un vero e proprio` ("a veritable") and `exceptional` caught no corpus
#: positive at all. `innovative` caught two, and both still cross the
#: threshold without it.
RETIRED = {
    "it": ("un vero e proprio",),
    "en": ("exceptional", "innovative"),
}

#: The Italian correlative conjunction, which sat in the structural list as
#: the twin of the English "not just X but Y". It is not a twin: the English
#: is a rhetorical tic, the Italian is grammar. 0 model entries, 2 human.
RETIRED_STRUCTURE = "non solo"


def _rows():
    with open(CORPUS, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class TheCorpusIsWhatItClaims(unittest.TestCase):

    def test_three_languages_and_a_usable_number_of_each(self):
        rows = _rows()
        by_language = {}
        for row in rows:
            by_language[row["language"]] = by_language.get(row["language"], 0) + 1
        self.assertEqual(set(by_language), {"en", "it", "uk"})
        for language, count in by_language.items():
            with self.subTest(language):
                self.assertGreaterEqual(count, 50)

    def test_every_entry_carries_a_checkable_provenance(self):
        """A revision id and a date, or the claim "a person wrote this" is an
        assertion rather than something a reader can go and verify."""
        for row in _rows():
            with self.subTest(source=row["source"]):
                self.assertIn("revid", row["source"])
                self.assertRegex(row["source"], r"\d{4}-\d{2}-\d{2}$")
                self.assertEqual(row["label"], "human")
                self.assertEqual(row["register"], "promotional")

    def test_the_dates_are_before_this_kind_of_copy_was_generated(self):
        for row in _rows():
            year = int(row["source"][-10:-6])
            with self.subTest(source=row["source"]):
                self.assertLessEqual(year, 2021)

    def test_it_is_the_register_the_other_corpora_lack(self):
        """Paragraph-length prose, not button labels: the length band where
        the corpus was thinnest is the one this has to fill."""
        italian = [r for r in _rows() if r["language"] == "it"]
        long_enough = [r for r in italian if len(r["text"].split()) >= 25]
        self.assertGreater(len(long_enough), 100)


class NotOneParagraphIsFlagged(unittest.TestCase):

    def test_no_human_travel_writing_crosses_the_threshold(self):
        detector = HeuristicDetector()
        flagged = []
        for index, row in enumerate(_rows()):
            block = TextBlock(block_id=f"p{index}", page_url="u", dom_path="p",
                              text=row["text"],
                              language_hint=guess_language_safe(row["text"]))
            spans = detector.analyze_block(block)
            worst = max(spans, key=lambda s: s.score, default=None)
            if worst is not None and worst.score >= THRESHOLD:
                flagged.append((round(worst.score, 2),
                                worst.details.get("cliches"),
                                worst.details.get("structural"),
                                row["source"], row["text"][:70]))
        self.assertEqual(flagged, [])


class TheRemovalsStay(unittest.TestCase):

    def test_the_retired_phrases_stay_retired(self):
        for language, phrases in RETIRED.items():
            for phrase in phrases:
                with self.subTest(f"{language}:{phrase}"):
                    self.assertNotIn(phrase, CLICHE_PHRASES[language])

    def test_the_italian_correlative_is_not_a_structural_marker(self):
        for pattern in STRUCTURAL_PATTERNS["it"]:
            with self.subTest(pattern=pattern.pattern):
                self.assertNotIn(RETIRED_STRUCTURE, pattern.pattern)

    def test_the_english_construction_it_was_modelled_on_is_still_there(self):
        """The removal is about Italian grammar, not about the idea: "not
        just X but Y" in English remains what it was."""
        self.assertTrue(any(re.search(r"not just", pattern.pattern)
                            for pattern in STRUCTURAL_PATTERNS["en"]))


if __name__ == "__main__":
    unittest.main()
