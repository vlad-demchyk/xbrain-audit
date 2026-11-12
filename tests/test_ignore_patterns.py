"""What a scan refuses to open, as a table rather than as a library's mood.

`repo_scanner` matches ignore patterns through `pathspec`, and pathspec has
more than one dialect: `gitwildmatch`, which this project used and which is
now deprecated, and `gitignore`, which replaced it. Swapping them decides
what every scan reads, so it was not done on the strength of a deprecation
warning - the two were compared over the project's own 36 default patterns
and a set of edge cases a user's `.xaudit-ignore` might contain, and they
disagreed nowhere.

This file is what remains after that comparison: the behaviour itself,
written down. Comparing against the deprecated dialect forever would pin
this project to the thing it just left; a table says what the tool must do
and fails if any future version of anything moves it.

The one that matters most is `node_modules/`. A walk that stops honouring
it does not fail - it reads a hundred megabytes of dependencies and reports
findings in code nobody here wrote.
"""
from __future__ import annotations

import unittest

from repo_scanner import (
    DEFAULT_IGNORE_PATTERNS, _parse_ignore_text, build_matcher, is_ignored,
)

#: `(path, ignored?)` under the project's own defaults. Directories are
#: written with a trailing slash, the way the walk asks about them.
DEFAULTS = (
    ("node_modules/pkg/index.js", True),
    ("src/node_modules/pkg/a.js", True),
    ("dist/app.js", True),
    ("build/main.css", True),
    ("venv/lib/python3.14/site-packages/x.py", True),
    ("__pycache__/a.pyc", True),
    (".git/config", True),
    ("vendor/autoload.php", True),
    ("wp-content/plugins/akismet/a.php", True),
    ("app/plugins/thing/a.php", True),
    ("deeply/nested/app/plugins/thing/a.php", True),
    ("assets/main.min.js", True),
    ("assets/main.min.css", True),
    ("assets/app.js.map", True),
    ("package-lock.json", True),
    ("mytheme.egg-info/PKG-INFO", True),
    # And the things a scan must still read.
    ("src/components/Hero.tsx", False),
    ("src/main.js", False),
    ("index.html", False),
    ("locales/uk.json", False),
    ("assets/main.js", False),
    ("nodemodules/a.js", False),
    ("my-dist-helper.js", False),
    ("docs/build-notes.md", False),
)

#: Patterns the project does not use but a user's own ignore file might.
#: These are the ones two dialects are most likely to read differently.
DIALECT_EDGES = (
    (["*.log"], "server.log", True),
    (["*.log", "!keep.log"], "keep.log", False),
    (["/root-only.txt"], "root-only.txt", True),
    (["/root-only.txt"], "sub/root-only.txt", False),
    (["docs/**/*.md"], "docs/a/b.md", True),
    (["**/tmp"], "a/b/tmp", True),
    (["*.py[co]"], "m.pyc", True),
    (["*.py[co]"], "m.py", False),
    (["sub/"], "sub/f.txt", True),
    (["build"], "build/x.js", True),
)


class TheProjectsOwnDefaults(unittest.TestCase):
    def setUp(self):
        self.patterns = _parse_ignore_text(DEFAULT_IGNORE_PATTERNS)
        self.matcher = build_matcher(self.patterns)

    def test_the_table(self):
        for path, expected in DEFAULTS:
            with self.subTest(path=path):
                self.assertEqual(is_ignored(path, self.matcher), expected)

    def test_dependencies_are_never_read(self):
        """The one that costs the most when it breaks: a walk that stops
        honouring this does not fail, it reads a hundred megabytes and
        reports findings in code nobody here wrote."""
        self.assertTrue(is_ignored("node_modules/react/index.js", self.matcher))

    def test_a_folder_pattern_does_not_match_a_similarly_named_file(self):
        """`dist/` is a folder. `my-dist-helper.js` is somebody's source."""
        self.assertFalse(is_ignored("my-dist-helper.js", self.matcher))


class WhatAUsersOwnIgnoreFileCanSay(unittest.TestCase):
    """The edge cases the two pathspec dialects were compared over."""

    def test_the_table(self):
        for patterns, path, expected in DIALECT_EDGES:
            with self.subTest(patterns=patterns, path=path):
                self.assertEqual(
                    is_ignored(path, build_matcher(patterns)), expected)

    def test_a_negation_takes_a_file_back_out(self):
        """The single most likely thing to differ between dialects, and the
        one whose failure is silent: a file the user asked to keep quietly
        stops being scanned."""
        matcher = build_matcher(["*.log", "!keep.log"])
        self.assertTrue(is_ignored("server.log", matcher))
        self.assertFalse(is_ignored("keep.log", matcher))


class TheMatcherIsBuiltFromOneDialect(unittest.TestCase):
    def test_no_deprecated_pattern_factory_is_used(self):
        """It warned once per matcher built, which a scan does per walk -
        two thousand warnings in one suite run. The volume was the symptom;
        the reason to move was that the dialect is going away."""
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            build_matcher(_parse_ignore_text(DEFAULT_IGNORE_PATTERNS))
        self.assertEqual([w for w in caught
                          if issubclass(w.category, DeprecationWarning)], [])


if __name__ == "__main__":
    unittest.main()
