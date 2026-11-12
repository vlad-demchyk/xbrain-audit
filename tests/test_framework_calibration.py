"""One pair of files per technology: correct code, and broken code.

This is the harness the tool did not have. Every exclusion and every mask it
carries was added after a false-positive class turned up in somebody's
project - `.tsx` skipped for two months (`P-19`), PHP server tags read as
having no text, `#` in an attribute treated as a comment, 455 findings from
vendored WordPress core. Each was found by a person looking at a real report,
which means the next framework fails the same way until someone looks again.

So each technology gets two fixtures that differ in exactly one thing: one is
written the way its framework says to write it, the other is not.

* the **correct** file must produce **no findings**. A finding there is the
  tool not understanding the framework.
* the **broken** file must produce the findings it deserves. Silence there is
  the tool blind, which is the more expensive failure - a scan that reports
  nothing reads as a clean one.

Two whole-framework defects were found by writing this file, and neither was
visible in any real report:

* Vue, Angular, Alpine, Svelte and Thymeleaf bind attributes by *renaming*
  them -
  `:alt="caption"`, `[attr.alt]`, `x-bind:alt`. The plain attribute is then
  absent, so a correct component was reported as missing its `alt`. See
  `audit.base.resolve_bound_attributes`.
* BeautifulSoup hides text inside `<template>` the way it hides a comment,
  and a Vue single-file component *is* a `<template>`. Every label, link and
  heading inside one read as empty. See `audit.base.unwrap_template_text`.

* An element whose text arrives at runtime - `x-text`, `v-text`, `th:text`,
  `ng-bind`, `data-i18n` - is written empty on purpose, and read literally it
  is an empty link with no accessible name. See
  `audit.base.resolve_text_directives`.
* A `.html` file with no `<html>` in it is a *template*, not a page. An
  Angular component template collected eight page-level findings -
  `bp-charset`, `landmark-regions`, `skip-link`, `seo-canonical` - for not
  being a document it was never going to be. See
  `audit.engine._document_kind`.

Before those fixes the idiomatic Vue component and the deliberately broken one
produced identical findings - three each - which means the pass could not
tell them apart at all.
"""
from __future__ import annotations

import collections
import shutil
import tempfile
import unittest
from pathlib import Path

import audit
from models import FileResult

#: Two trees, and the split is the point. `frameworks/` is one pair per
#: *template language* - the same component through fourteen syntaxes.
#: `rules/` is one pair per *rule category* that needed opening, which so far
#: is `security`, a category that existed with no rules in it at all.
FIXTURES = Path(__file__).parent / "fixtures" / "frameworks"
RULE_FIXTURES = Path(__file__).parent / "fixtures" / "rules"


def _folder_for(technology: str, root: Path) -> Path:
    """Where this pair lives, in whichever tree holds it."""
    direct = root / "frameworks" / technology
    return direct if direct.is_dir() else root / "rules" / technology

#: What each broken fixture is broken in, and must therefore be caught for.
#: Written per technology rather than as one list, because the point is that
#: the same defect is caught through six different syntaxes.
#: Each broken fixture also has a search field labelled only by its
#: placeholder: named (the name computation falls back to the hint), so not
#: `control-name`, but a 3.3.2 failure all the same.
_NAMES_AND_ALT = {"control-name", "image-alt", "label-placeholder-only"}
_AND_AN_EMPTY_LINK = _NAMES_AND_ALT | {"seo-empty-link"}
#: The server-side template languages translate the hint
#: (`placeholder="{% trans 'Search' %}"`): a bound value says nothing about
#: what renders, so `label-placeholder-only` stays silent there.
_SERVER_TEMPLATE = (_AND_AN_EMPTY_LINK - {"label-placeholder-only"})

EXPECTED = {
    # JSX puts the expression in the attribute *value* (`alt={caption}`).
    "react": _AND_AN_EMPTY_LINK | {"control-name"},
    # These four bind by *renaming* the attribute, which is the class
    # `resolve_bound_attributes` exists for.
    "vue": _NAMES_AND_ALT,          # :alt, :aria-label, v-model
    "angular": _NAMES_AND_ALT,      # [alt], [attr.aria-label], [textContent]
    "svelte": _NAMES_AND_ALT,       # alt={x}, bind:value
    "alpine": _NAMES_AND_ALT,       # x-bind:alt, x-text
    "thymeleaf": _NAMES_AND_ALT,    # th:alt, th:text - and a whole page
    # And these six put code where an HTML parser expects text.
    "php": {"control-name", "seo-empty-link", "label-placeholder-only"},
    "twig": _SERVER_TEMPLATE,
    "django": _SERVER_TEMPLATE,   # {% %} and {{ }}
    "liquid": _SERVER_TEMPLATE,
    "handlebars": _SERVER_TEMPLATE,
    "erb": _SERVER_TEMPLATE,
    "blade": _SERVER_TEMPLATE,
    "razor": _AND_AN_EMPTY_LINK,
    # Not a template language: the pair that guards the `security` category,
    # which had no rules in it at all until these six. Every one is `EXACT`
    # on purpose - a security finding that turns out to be wrong costs more
    # trust than any other kind.
    "security": {"sec-frame-sandbox", "sec-frame-permissions",
                 "sec-form-insecure-action", "sec-script-integrity",
                 "sec-secret-in-markup", "sec-autocomplete-secret",
                 "sec-password-in-get-form", "sec-formaction-insecure",
                 "sec-credentials-in-url", "sec-srcdoc-sandbox"},
}


def _audit(path: Path, root: Path) -> collections.Counter:
    result = audit.analyze_files(
        [FileResult(path=str(path), raw_text=path.read_text(encoding="utf-8"))],
        root=str(root), media=False, repo_facts=False)
    return collections.Counter(issue.rule_id
                               for document in result.documents
                               for issue in document.issues)


class _Copied(unittest.TestCase):
    """Fixtures are audited from a temporary copy, and they have to be.

    `tests/` is in `audit.engine.SKIP_AUDIT_DIRS` - correctly, since a real
    project's tests are not its product - so a fixture read from where it
    lives is skipped, and every assertion below would pass while measuring
    nothing. That is the same vacuous-pass shape `P-19` was made of.
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name) / "app"
        shutil.copytree(FIXTURES.parent, cls.root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _files(self, technology: str, kind: str) -> list:
        folder = _folder_for(technology, self.root)
        return [p for p in sorted(folder.iterdir()) if kind in p.name.lower()]


class CorrectCodeIsSilent(_Copied):
    """Idiomatic code in every supported technology reports nothing."""

    def test_every_correct_fixture_is_clean(self):
        for technology in sorted(EXPECTED):
            for path in self._files(technology, "correct"):
                with self.subTest(technology=technology, file=path.name):
                    found = _audit(path, self.root)
                    self.assertEqual(
                        dict(found), {},
                        f"{technology} written correctly still reports "
                        f"{sorted(found)} - the tool does not understand it")


class BrokenCodeIsCaught(_Copied):
    """And the tool is not silent, which is the costlier failure."""

    def test_every_broken_fixture_is_reported(self):
        for technology, expected in sorted(EXPECTED.items()):
            for path in self._files(technology, "broken"):
                with self.subTest(technology=technology, file=path.name):
                    found = set(_audit(path, self.root))
                    self.assertEqual(
                        found, expected,
                        f"{technology}: expected {sorted(expected)}, "
                        f"got {sorted(found)}")

    def test_the_pair_actually_differs(self):
        """A guard on the fixtures themselves.

        If someone 'fixes' a broken fixture, both halves go silent and both
        cases above still pass - the suite would then assert that the tool
        agrees with itself about nothing.
        """
        for technology in sorted(EXPECTED):
            with self.subTest(technology=technology):
                correct = sum(sum(_audit(p, self.root).values())
                              for p in self._files(technology, "correct"))
                broken = sum(sum(_audit(p, self.root).values())
                             for p in self._files(technology, "broken"))
                self.assertEqual(correct, 0)
                self.assertGreater(broken, 0)


class EveryTechnologyHasAPair(unittest.TestCase):
    """The fixture set is the coverage claim; it must not quietly shrink."""

    def test_each_named_technology_has_both_halves(self):
        for technology in sorted(EXPECTED):
            with self.subTest(technology=technology):
                folder = _folder_for(technology, FIXTURES.parent)
                self.assertTrue(folder.is_dir(), f"{technology} fixtures missing")
                names = [p.name.lower() for p in folder.iterdir()]
                self.assertTrue(any("correct" in n for n in names))
                self.assertTrue(any("broken" in n for n in names))

    def test_no_fixture_folder_is_unclaimed(self):
        """A folder nobody asserts on is coverage that is not being checked."""
        folders = {p.name for p in FIXTURES.iterdir() if p.is_dir()}
        folders |= {p.name for p in RULE_FIXTURES.iterdir() if p.is_dir()}
        self.assertEqual(folders, set(EXPECTED))


if __name__ == "__main__":
    unittest.main()
