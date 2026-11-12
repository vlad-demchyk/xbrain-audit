"""Ignoring findings: the five levels, and the re-scoring that has to follow.

The re-scoring cases matter most. Suppressing one reason out of three and
leaving the original score would show a "high confidence" finding whose
explanation no longer contains the thing that made it high — which is worse
than either reporting or hiding it.
"""
from __future__ import annotations

import unittest
import uuid

import detectors  # noqa: F401 - registers the detectors
import suppression
from detectors.factory import DetectorFactory
from models import Confidence, TextBlock

SAMPLE = ("In today's fast-paced world our comprehensive platform is robust and "
          "will unlock the potential of your team — every single day.")


def block(text: str = SAMPLE, url: str = "http://x/a", dom: str = "html > body > p") -> TextBlock:
    return TextBlock(block_id=str(uuid.uuid4()), page_url=url, dom_path=dom, text=text)


def analyse(b: TextBlock):
    spans = DetectorFactory.create("offline").analyze_block(b)
    return spans, {b.block_id: b}


def style_spans(spans):
    return [s for s in spans if (s.details or {}).get("source") == "style"]


class Parsing(unittest.TestCase):
    def test_sections_and_comments(self):
        parsed = suppression.Suppressions.parse(
            "# a comment\n[phrases]\nrobust\n\n[rules]\ndashes\n[paths]\nsrc/gen/\n")
        self.assertEqual(parsed.phrases, ["robust"])
        self.assertEqual(parsed.rules, ["dashes"])
        self.assertEqual(parsed.paths, ["src/gen/"])

    def test_a_bare_list_is_read_as_phrases(self):
        # What people write first, before reading any documentation.
        self.assertEqual(suppression.Suppressions.parse("robust\ndelve\n").phrases,
                         ["robust", "delve"])

    def test_round_trip_through_settings(self):
        original = suppression.Suppressions(phrases=["a"], rules=["dashes"])
        restored = suppression.Suppressions.from_dict(original.to_dict())
        self.assertEqual(restored.phrases, ["a"])
        self.assertEqual(restored.rules, ["dashes"])


class Matching(unittest.TestCase):
    def test_phrases_are_case_insensitive(self):
        s = suppression.Suppressions(phrases=["Robust"])
        self.assertTrue(s.ignores_phrase("robust"))
        self.assertTrue(s.ignores_phrase(" ROBUST "))

    def test_directory_pattern_matches_anywhere_in_the_path(self):
        s = suppression.Suppressions(paths=["src/generated/"])
        self.assertTrue(s.ignores_path("a/src/generated/page.html"))
        self.assertFalse(s.ignores_path("src/app.html"))

    def test_glob_matches_the_file_name(self):
        s = suppression.Suppressions(paths=["*.min.html"])
        self.assertTrue(s.ignores_path("/deep/path/page.min.html"))
        self.assertFalse(s.ignores_path("/deep/path/page.html"))

    def test_a_url_is_matched_by_the_same_list(self):
        s = suppression.Suppressions(paths=["https://staging.example.com/*"])
        self.assertTrue(s.ignores_path("https://staging.example.com/pricing"))
        self.assertFalse(s.ignores_path("https://example.com/pricing"))


class Fingerprints(unittest.TestCase):
    def test_same_text_in_the_same_place_gives_the_same_id(self):
        a = suppression.fingerprint("page.html", "Hello  there", "style")
        b = suppression.fingerprint("page.html", "Hello there", "style")
        # Whitespace is normalised, so reformatting the source does not
        # silently expire a dismissal.
        self.assertEqual(a, b)

    def test_different_documents_give_different_ids(self):
        self.assertNotEqual(
            suppression.fingerprint("a.html", "Hello", "style"),
            suppression.fingerprint("b.html", "Hello", "style"),
        )

    def test_dismissing_one_finding_leaves_the_others(self):
        b = block()
        spans, blocks = analyse(b)
        target = style_spans(spans)[0]
        s = suppression.Suppressions(
            fingerprints=[suppression.span_fingerprint(target, b)])
        kept = suppression.filter_spans(spans, blocks, s)
        self.assertEqual(len(kept), len(spans) - 1)


class Rescoring(unittest.TestCase):
    def test_suppressed_phrase_lowers_the_score_and_leaves_the_rest(self):
        b = block()
        spans, blocks = analyse(b)
        before = style_spans(spans)[0]
        s = suppression.Suppressions(phrases=["comprehensive", "robust"])
        after = style_spans(suppression.filter_spans(spans, blocks, s))[0]

        self.assertLess(after.score, before.score)
        self.assertNotIn("robust", after.details["cliches"])
        # The reasons that were not suppressed are still reported.
        self.assertIn("unlock the potential", after.details["cliches"])

    def test_suppressing_a_signal_zeroes_it_in_the_explanation(self):
        b = block()
        spans, blocks = analyse(b)
        s = suppression.Suppressions(rules=["dashes"])
        after = style_spans(suppression.filter_spans(spans, blocks, s))[0]
        self.assertEqual(after.details["signals"]["dashes"], 0.0)

    def test_a_finding_with_nothing_left_to_say_is_dropped(self):
        b = block("Our comprehensive platform is robust.")
        spans, blocks = analyse(b)
        s = suppression.Suppressions(phrases=["comprehensive", "robust"])
        self.assertEqual(style_spans(suppression.filter_spans(spans, blocks, s)), [])

    def test_an_untouched_finding_keeps_its_exact_score(self):
        b = block()
        spans, blocks = analyse(b)
        before = style_spans(spans)[0]
        s = suppression.Suppressions(phrases=["something else entirely"])
        after = style_spans(suppression.filter_spans(spans, blocks, s))[0]
        self.assertEqual(after.score, before.score)


class CharacterAndScopeSuppression(unittest.TestCase):
    def test_a_character_category_can_be_switched_off(self):
        b = block("This costs 5 — 6 euros.")
        spans, blocks = analyse(b)
        s = suppression.Suppressions(rules=["typography"])
        kept = suppression.filter_spans(spans, blocks, s)
        self.assertEqual([x for x in kept
                          if (x.details or {}).get("category") == "typography"], [])

    def test_a_whole_document_can_be_skipped(self):
        b = block()
        spans, blocks = analyse(b)
        s = suppression.Suppressions(paths=["http://x/a"])
        self.assertEqual(suppression.filter_spans(spans, blocks, s), [])

    def test_a_region_of_the_page_can_be_skipped(self):
        b = block(dom="html > body > footer:nth-of-type(1) > p:nth-of-type(1)")
        spans, blocks = analyse(b)
        s = suppression.Suppressions(selectors=["footer"])
        self.assertEqual(suppression.filter_spans(spans, blocks, s), [])

    def test_an_empty_list_changes_nothing(self):
        b = block()
        spans, blocks = analyse(b)
        empty = suppression.Suppressions()
        self.assertIs(suppression.filter_spans(spans, blocks, empty), spans)


class AccessibilitySuppression(unittest.TestCase):
    def test_a_rule_can_be_switched_off(self):
        from audit import analyze_document

        issues = analyze_document('<img src="/a.png">', "p.html").issues
        s = suppression.Suppressions(rules=["image-alt"])
        kept = suppression.filter_issues(issues, s)
        # Only the accessibility rule is switched off. The same <img> also
        # legitimately produces an SEO finding about missing dimensions, and
        # suppressing one category must not silently take the other with it.
        self.assertEqual([i.rule_id for i in kept if i.category == "accessibility"], [])
        self.assertTrue([i for i in kept if i.category == "seo"])

    def test_one_accessibility_finding_can_be_dismissed(self):
        from audit import analyze_document

        issues = analyze_document('<img src="/a.png"><img src="/b.png">', "p.html").issues
        s = suppression.Suppressions(
            fingerprints=[suppression.issue_fingerprint(issues[0])])
        self.assertEqual(len(suppression.filter_issues(issues, s)), len(issues) - 1)

    def test_one_list_governs_both_analyses(self):
        # The user thinking "not this part of the site" means it for the
        # whole tool, not per subsystem.
        from audit import analyze_document

        s = suppression.Suppressions(paths=["vendor/"])
        issues = analyze_document('<img src="/a.png">', "vendor/theme.html").issues
        self.assertTrue(issues)  # the page does have findings when not ignored
        self.assertEqual(suppression.filter_issues(issues, s), [])

        b = block(url="vendor/theme.html")
        spans, blocks = analyse(b)
        self.assertEqual(suppression.filter_spans(spans, blocks, s), [])


class KnownIds(unittest.TestCase):
    def test_the_settings_ui_can_list_every_switchable_check(self):
        ids = suppression.known_rule_ids()
        self.assertIn("dashes", ids["style"])
        self.assertIn("typography", ids["characters"])
        self.assertIn("image-alt", ids["accessibility"])


if __name__ == "__main__":
    unittest.main()


class TheFileIsADocument(unittest.TestCase):
    """`.xaudit-ignore` is committed and reviewed like any other file.

    Every case here failed before: the writer rebuilt the file from the
    dataclass, so one dismissal in the window deleted every comment somebody
    had written; a trailing note was read as part of the value, so a rule
    switched off with a reason next to it stayed on; and a line opening with
    `#` was always a comment, which quietly threw away every CSS id selector.
    """

    SAMPLE = ("# vendored code we do not own\n"
              "[paths]\n"
              "vendor/\n"
              "third_party/\n"
              "\n"
              "# generated\n"
              "*.min.js\n"
              "\n"
              "[rules]\n"
              "meta-viewport  # we ship a fixed-width admin on purpose\n")

    def test_a_note_next_to_a_rule_is_not_part_of_the_rule(self):
        parsed = suppression.Suppressions.parse(self.SAMPLE)
        self.assertEqual(parsed.rules, ["meta-viewport"])
        self.assertTrue(parsed.ignores_rule("meta-viewport"))
        self.assertEqual(parsed.labels["meta-viewport"],
                         "we ship a fixed-width admin on purpose")

    def test_writing_it_back_keeps_the_comments(self):
        parsed = suppression.Suppressions.parse(self.SAMPLE)
        written = parsed.render()
        for comment in ("# vendored code we do not own", "# generated",
                        "# we ship a fixed-width admin on purpose"):
            self.assertIn(comment, written)

    def test_a_new_entry_lands_in_its_own_section(self):
        parsed = suppression.Suppressions.parse(self.SAMPLE)
        parsed.paths.append("build/")
        written = parsed.render()
        self.assertIn("build/", written)
        # Still under [paths], not appended after [rules] at the end.
        self.assertLess(written.index("build/"), written.index("[rules]"))
        self.assertIn("# generated", written)

    def test_a_removed_entry_disappears_and_the_rest_stays(self):
        parsed = suppression.Suppressions.parse(self.SAMPLE)
        parsed.paths.remove("third_party/")
        written = parsed.render()
        self.assertNotIn("third_party/", written)
        self.assertIn("vendor/", written)
        self.assertIn("# vendored code we do not own", written)

    def test_a_file_it_did_not_edit_comes_back_byte_for_byte(self):
        original = ("# vendored\n"
                    "vendor/\n"
                    "third_party/\n"
                    "\n"
                    "# generated\n"
                    "*.min.js\n"
                    "\n"
                    "[rules]\n"
                    "region  # decided in review\n")
        self.assertEqual(suppression.Suppressions.parse(original).render(), original)

    def test_a_group_heading_belongs_to_the_group_below_it(self):
        # `# generated` heads the lines under it; attaching it to the group
        # above would put it in the wrong pane and, once a section is edited,
        # in the wrong place in the file.
        parsed = suppression.Suppressions.parse(
            "# vendored\nvendor/\n\n# generated\n*.min.js\n")
        box = parsed.section_text("paths")
        self.assertEqual(box.splitlines(),
                         ["# vendored", "vendor/", "", "# generated", "*.min.js"])

    def test_an_id_selector_is_a_selector_and_not_a_comment(self):
        parsed = suppression.Suppressions.parse("[selectors]\n#main .ads\n.faq #q1\n")
        self.assertEqual(parsed.selectors, ["#main .ads", ".faq #q1"])

    def test_a_note_inside_the_selector_section_still_works(self):
        parsed = suppression.Suppressions.parse(
            "[selectors]\n# third-party embeds\n.ads  # sold, not ours\n")
        self.assertEqual(parsed.selectors, [".ads"])
        self.assertEqual(parsed.labels[".ads"], "sold, not ours")


class TheDocumentedExampleWorks(unittest.TestCase):
    """The README's own ignore file, copied verbatim.

    It is taught as "gitignore syntax" and written as a bare list, which the
    parser read as phrases - so the example everybody starts from excluded
    nothing, silently, and `vendor/` was still scanned.
    """

    README_EXAMPLE = ("# Ignore vendored code\n"
                      "vendor/\n"
                      "third_party/\n"
                      "\n"
                      "# Ignore generated files\n"
                      "*.min.js\n"
                      "*.min.css\n")

    def test_it_actually_excludes_those_files(self):
        parsed = suppression.Suppressions.parse(self.README_EXAMPLE)
        self.assertTrue(parsed.ignores_path("vendor/thing.js"))
        self.assertTrue(parsed.ignores_path("src/app.min.js"))
        self.assertEqual(parsed.phrases, [])

    def test_a_plain_word_is_still_a_phrase(self):
        parsed = suppression.Suppressions.parse("robust\ndelve\ncutting-edge\n")
        self.assertEqual(parsed.phrases, ["robust", "delve", "cutting-edge"])
        self.assertEqual(parsed.paths, [])

    def test_inside_a_section_the_section_decides(self):
        # Only a bare line before the first header is reclassified; a phrase
        # somebody deliberately filed under [phrases] stays one.
        parsed = suppression.Suppressions.parse("[phrases]\nand/or\n")
        self.assertEqual(parsed.phrases, ["and/or"])
        self.assertEqual(parsed.paths, [])


class ADismissedFindingSaysWhatItWas(unittest.TestCase):
    """A fingerprint is a one-way hash, so the note is the only record."""

    def test_a_text_finding_gets_a_readable_note(self):
        b = block(url="https://example.com/about")
        spans, _ = analyse(b)
        label = suppression.span_label(spans[0], b)
        self.assertIn("example.com/about", label)
        self.assertTrue(label.strip())

    def test_the_note_is_one_line_and_bounded(self):
        b = block(text="comprehensive " * 60)
        spans, _ = analyse(b)
        label = suppression.span_label(spans[0], b)
        self.assertNotIn("\n", label)
        self.assertLess(len(label), 160)
