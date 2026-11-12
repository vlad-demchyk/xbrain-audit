"""`corpus/prose.jsonl`: human writing on the subjects a scan is pointed at.

The corpus's human half is interface strings plus encyclopedic paragraphs
about the web, and "0 false alarms" was measured on that. It was a claim
about the wrong text. A scan is pointed at pages about tourism, software,
marketing and usability, and those are exactly the subjects whose ordinary
vocabulary collides with a marketing cliché list - `efficienza` is what an
Italian article on productivity is made of, `scalable` is what one about
cloud computing is made of.

Measured 2026-08-31, the first time this file existed: **six** of these human
paragraphs crossed the reporting threshold, one cliché entry each. Eleven
further entries matched this text without crossing, and each caught no more
positives than it cost. All seventeen were removed, and held-out recall went
from (en 11/20, it 4/11, uk 10/14) to exactly the same numbers.
"""
import json
import unittest
from pathlib import Path

from detectors.heuristic import CLICHE_PHRASES, HeuristicDetector
from lang_detect import guess_language_safe
from models import TextBlock

CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "prose.jsonl"
THRESHOLD = 0.33

#: Phrases removed by that audit. Named so the removal is a decision with a
#: measurement behind it rather than a gap somebody refills by eye.
RETIRED = {
    "en": ("scalable", "dynamic", "holistic", "bandwidth", "additionally,"),
    "it": ("efficienza", "efficiente", "fondamentale", "integrazione",
           "tuttavia,", "sempre più spesso", "punto di svolta",
           "nuove possibilità"),
    "uk": ("в епоху", "феномен", "у підсумку,", "крім того,"),
}


def _rows():
    with open(CORPUS, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class HumanProseIsNotFlagged(unittest.TestCase):

    def test_the_corpus_covers_all_three_languages(self):
        rows = _rows()
        self.assertEqual(len(rows), 334)
        by_language = {}
        for row in rows:
            by_language[row["language"]] = by_language.get(row["language"], 0) + 1
        self.assertEqual(set(by_language), {"en", "it", "uk"})
        for language, count in by_language.items():
            with self.subTest(language):
                self.assertGreaterEqual(count, 50)
        for row in rows:
            self.assertIn("revid", row["source"])

    def test_not_one_paragraph_crosses_the_threshold(self):
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
                                row["text"][:70]))
        self.assertEqual(flagged, [])

    def test_the_retired_phrases_stay_retired(self):
        """Each was counted on both sides before it went. Putting one back
        needs the same, not a hunch that it looks AI-ish."""
        for language, phrases in RETIRED.items():
            for phrase in phrases:
                with self.subTest(f"{language}:{phrase}"):
                    self.assertNotIn(phrase, CLICHE_PHRASES[language])


if __name__ == "__main__":
    unittest.main()
