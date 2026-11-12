"""`corpus/foreign.jsonl` against the two claims that were made about it.

The claims are numbers, so they are held here rather than in a comment: a
marker added to `lang_detect` for one language can quietly cost another, and
the wording pass going quiet outside its lists is worth exactly as much as
the count of entries it stays quiet on.

The entries are paragraphs from dated 2018 Wikipedia revisions in five
languages this tool has no lists for - human by date, and rebuildable with
`scripts/fetch_foreign_corpus.py`.
"""
import json
import unittest
from pathlib import Path

from detectors.heuristic import HeuristicDetector
from lang_detect import UNSUPPORTED, guess_language
from models import TextBlock

CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "foreign.jsonl"
SUPPORTED = [Path(__file__).resolve().parent.parent / "corpus" / name
             for name in ("labelled.jsonl", "negative_pool.jsonl")]

#: Measured 2026-08-31. Not 100%: six French, one Spanish and one Russian
#: paragraph still read as a supported language, and the fix for each costs
#: more than it buys - see the outcome. Held as a floor so the number can
#: only improve silently, never decay silently.
MIN_READ_AS_FOREIGN = 249


def _rows(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class ForeignTextIsNamedForeign(unittest.TestCase):

    def test_the_corpus_is_there_and_is_five_languages(self):
        rows = _rows(CORPUS)
        self.assertEqual(len(rows), 257)
        self.assertEqual({row["language"] for row in rows},
                         {"de", "fr", "es", "pl", "ru"})
        # Provenance, not plausibility: every entry names the revision it
        # came from, which is what makes it checkable.
        for row in rows:
            self.assertIn("revid", row["source"])

    def test_almost_all_of_it_reads_as_unsupported(self):
        rows = _rows(CORPUS)
        foreign = sum(1 for row in rows
                      if guess_language(row["text"]) == UNSUPPORTED)
        self.assertGreaterEqual(foreign, MIN_READ_AS_FOREIGN)

    def test_the_marker_lists_cost_the_supported_side_nothing(self):
        # The other half of the trade. A marker that also occurs in English
        # or Italian would show up here as a corpus entry called foreign.
        for path in SUPPORTED:
            for row in _rows(path):
                with self.subTest(row["text"][:40]):
                    self.assertNotEqual(guess_language(row["text"]), UNSUPPORTED)


class TheCharacterPassJudgesOnlyWhatItCanRead(unittest.TestCase):
    """The character pass is language-independent and keeps running - but the
    punctuation *exemption* is a claim about a language's convention, and for
    a language nobody read there is no convention to assert.

    Measured 2026-08-31: the exemption row for an unrecognised language was a
    copy of the Ukrainian one, so `„`, `“`, `”`, `‚`, `‘` and `’` - the German
    and Polish opening quotes and the French apostrophe - were reported on
    human text as anomalies. 92 of 95 typography findings on this corpus.
    """

    #: What is left is not punctuation convention: a non-breaking space, an
    #: `&nbsp;` entity, one ellipsis, one Latin letter inside a Cyrillic word.
    MAX_TYPOGRAPHY_FINDINGS = 3

    def test_a_language_with_no_table_keeps_its_own_quotation_marks(self):
        from unicode_rules import find_anomalies
        found = 0
        for row in _rows(CORPUS):
            language = guess_language(row["text"])
            if language != UNSUPPORTED:
                continue
            found += sum(1 for anomaly in find_anomalies(row["text"], language)
                         if anomaly.category == "typography")
        self.assertLessEqual(found, self.MAX_TYPOGRAPHY_FINDINGS)

    def test_english_still_reports_them(self):
        # The exemption is per language, not a general amnesty.
        from unicode_rules import find_anomalies
        text = 'Er sagte „das ist gut“ und ging.'
        self.assertTrue(find_anomalies(text, "en"))


class TheWordingPassStaysQuiet(unittest.TestCase):

    def test_no_foreign_paragraph_gets_a_style_score(self):
        detector = HeuristicDetector()
        scored = []
        for index, row in enumerate(_rows(CORPUS)):
            if guess_language(row["text"]) != UNSUPPORTED:
                continue  # a leaked label is the other test's business
            block = TextBlock(block_id=f"b{index}", page_url=row["source"],
                              dom_path="p", text=row["text"])
            if detector.analyze_block(block):
                scored.append(row["text"][:60])
        self.assertEqual(scored, [])


if __name__ == "__main__":
    unittest.main()
