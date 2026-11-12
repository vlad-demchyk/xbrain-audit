"""What the two entry points tag a block with, and why it is not "en".

`lang_detect` has two answers for "I could not read this": `None` means the
passage is too short to tell, and `UNSUPPORTED` means it is a language with
no lists here. The whole point of `None` is that it makes a caller check
every list instead of one - `_cliche_hits` implements exactly that, and the
docstrings in `lang_detect` argue for it at length.

It was dead on both live paths. `crawler` and `repo_scanner` tagged blocks
with `guess_language`, which turns `None` into `"en"`, so nothing downstream
ever saw the answer the mechanism was built for. Measured 2026-08-31 on a
live Italian page: 29 of 71 blocks arrived tagged `en` while
`guess_language_safe` said `None`, and on the corpus 232 entries carried the
wrong tag - 116 of them Italian.
"""
import json
import unittest
from pathlib import Path

from crawler import page_from_html
from detectors.heuristic import HeuristicDetector
from lang_detect import guess_language_safe
from models import TextBlock

CORPUS = Path(__file__).resolve().parent.parent / "corpus"


class AShortStringIsNotEnglish(unittest.TestCase):

    HTML = ("<html lang='it'><body>"
            "<p>Nascondi la navigazione</p>"
            "<p>Scopri le esperienze</p>"
            "<p>Nel cuore della citta fortezza, storia e architettura si "
            "incontrano in un equilibrio rinascimentale che merita una "
            "visita lunga e attenta da parte di chiunque passi di qui.</p>"
            "</body></html>")

    def test_the_crawler_tags_none_not_en(self):
        blocks = page_from_html(self.HTML, "https://example.it/").blocks
        hints = {b.text[:20]: b.language_hint for b in blocks}
        self.assertTrue(blocks)
        short = [h for t, h in hints.items() if "Nascondi" in t or "Scopri" in t]
        self.assertTrue(short)
        for hint in short:
            self.assertIsNone(hint, f"short Italian tagged {hint!r}")

    def test_a_readable_passage_still_gets_its_language(self):
        # The change must not cost the answers that were right.
        blocks = page_from_html(self.HTML, "https://example.it/").blocks
        long_block = max(blocks, key=lambda b: len(b.text))
        self.assertEqual(long_block.language_hint, "it")

    def test_the_tag_agrees_with_the_safe_reading(self):
        for block in page_from_html(self.HTML, "https://example.it/").blocks:
            with self.subTest(block.text[:30]):
                self.assertEqual(block.language_hint,
                                 guess_language_safe(block.text))


class TheCorpusDoesNotMoveUnderTheChange(unittest.TestCase):
    """232 entries change tag; none of them changes a verdict.

    Both sides matter. The tag was wrong on 116 Italian entries, and it was
    wrong in the direction that suppresses the Italian cliché list - but
    those entries are short interface strings that match nothing in any list,
    so nothing was being missed. Held here so the day a list grows a phrase
    that does match one, the change shows up as a number rather than as a
    surprise.
    """

    def setUp(self):
        self.rows = []
        for name in ("labelled.jsonl", "negative_pool.jsonl"):
            with open(CORPUS / name, encoding="utf-8") as handle:
                self.rows += [json.loads(line) for line in handle if line.strip()]

    def _flagged(self, hint_of):
        detector = HeuristicDetector()
        found = 0
        for index, row in enumerate(self.rows):
            block = TextBlock(block_id=f"b{index}", page_url="u", dom_path="p",
                              text=row["text"], language_hint=hint_of(row))
            spans = detector.analyze_block(block)
            if max((s.score for s in spans), default=0.0) >= 0.33:
                found += 1
        return found

    def test_no_human_entry_is_flagged_either_way(self):
        humans = [r for r in self.rows if r["label"] == "human"]
        detector = HeuristicDetector()
        for index, row in enumerate(humans):
            block = TextBlock(block_id=f"h{index}", page_url="u", dom_path="p",
                              text=row["text"],
                              language_hint=guess_language_safe(row["text"]))
            spans = detector.analyze_block(block)
            self.assertLess(max((s.score for s in spans), default=0.0), 0.33,
                            f"new false alarm: {row['text'][:60]}")

    def test_the_count_of_flagged_entries_is_unchanged(self):
        """Against the tag the live path actually produced, not the corpus's.

        `guess_language` is what `crawler` and `repo_scanner` called before,
        and it differs from `guess_language_safe` in exactly one way: it
        turns `None` into `"en"`. Comparing against the corpus's own
        `language` field would measure something else - the reading against
        the truth - and that comparison has its own home in
        `test_calibration`, because what it finds is a gap in the Italian
        marker list, not a consequence of this change.
        """
        from lang_detect import guess_language

        before = self._flagged(lambda r: guess_language(r["text"]))
        after = self._flagged(lambda r: guess_language_safe(r["text"]))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
