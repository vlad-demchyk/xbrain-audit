"""`corpus/negative_pool.jsonl`: the shortest register a scan ever meets.

`P-35`: 292 human interface lines sat in `corpus/` without entering a single
calibration number - `scripts/calibrate.py` reads `labelled.jsonl`,
`EmbeddingDetector` reads the tune half of that same file, `scripts/gate.py`
asks the same question of the same rows, and `corpus/README.md` did not name
this file at all. A corpus file nobody reads is not a negative set; it is a
file.

Measured 2026-09-01, and the measurement is what decides its role:

* **0 of 292** cross the reporting threshold in the wording pass;
* **no entry reaches five words** (the longest is four), so
  `EmbeddingDetector` - which refuses anything shorter - can never return a
  span here, and `guess_language_safe` answers `None` rather than a language;
* merging it into `labelled.jsonl` would therefore add nothing the embedding
  detector can read, while restating every ratio measured on that file and
  making these lines a *component* of the detector they are meant to judge
  (see the "Half of this file is a detector" section of `corpus/README.md`).

So it stays a yardstick, like `prose.jsonl` and `promotional.jsonl`, and the
numbers live here rather than in a comment: this is the register where a
cliché list is cheapest to break silently, because one wrong entry flags a
menu on every page of a site at once.
"""
import json
import unittest
from pathlib import Path

from detectors.heuristic import HeuristicDetector
from lang_detect import guess_language_safe
from models import TextBlock

CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "negative_pool.jsonl"
THRESHOLD = 0.33

#: The floor under `EmbeddingDetector.analyze_block`, repeated here because
#: this file's role depends on it: raise that floor and nothing changes,
#: lower it below five and these 292 lines start reaching a detector that has
#: never been measured on them.
EMBEDDING_MIN_WORDS = 5


def _rows():
    with open(CORPUS, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class InterfaceStringsAreNotFlagged(unittest.TestCase):

    def test_the_pool_is_what_it_claims_to_be(self):
        rows = _rows()
        self.assertEqual(len(rows), 292)
        self.assertEqual({row["label"] for row in rows}, {"human"})
        by_language = {}
        for row in rows:
            by_language[row["language"]] = by_language.get(row["language"], 0) + 1
        self.assertEqual(set(by_language), {"en", "it", "uk"})
        for language, count in by_language.items():
            with self.subTest(language):
                self.assertGreaterEqual(count, 50)
        # Provenance and register, per entry: "0 false alarms" is a claim
        # about a register, and an entry that does not say which one it is
        # cannot support it.
        for row in rows:
            self.assertTrue(row["source"])
            self.assertTrue(row["register"])

    def test_not_one_interface_line_crosses_the_threshold(self):
        detector = HeuristicDetector()
        flagged = []
        for index, row in enumerate(_rows()):
            block = TextBlock(block_id=f"n{index}", page_url="u", dom_path="p",
                              text=row["text"],
                              language_hint=guess_language_safe(row["text"]))
            spans = detector.analyze_block(block)
            worst = max(spans, key=lambda s: s.score, default=None)
            if worst is not None and worst.score >= THRESHOLD:
                flagged.append((round(worst.score, 2),
                                worst.details.get("cliches"),
                                row["text"]))
        self.assertEqual(flagged, [])

    def test_this_register_stays_out_of_reach_of_the_embedding_detector(self):
        """Why the file is a yardstick and not part of `labelled.jsonl`.

        Not an assumption about the detector: the longest entry here is four
        words, and the detector refuses under five. If either side of that
        moves, this test fails and the role has to be decided again rather
        than drifting.
        """
        longest = max(len(row["text"].split()) for row in _rows())
        self.assertLess(longest, EMBEDDING_MIN_WORDS)


if __name__ == "__main__":
    unittest.main()
