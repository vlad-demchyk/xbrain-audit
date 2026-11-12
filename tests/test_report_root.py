"""Where run folders land, and what happened to the ones already written.

Changed 2026-09-02 at the owner's request: `~/Documents/XBrain Audit` rather
than `~/Desktop/XBrain Audit`. A run leaves a folder per target and a sub-folder
per run inside it, so what accumulates is an archive - and an archive on the
Desktop is in front of everything else all day.

The half worth testing is not the new path but the old one. Changing a
default silently strands the data written under it: the runs panel empties,
and the second run of a target has nothing to compare against because its
history is somewhere the code no longer looks. So the move is part of the
change, and it has exactly one rule - never over an existing destination,
because merging two roots would have to silently pick between two runs of
the same target in the same minute.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli_impl import runfolder  # noqa: E402


class _FakeHome(unittest.TestCase):
    """Every test here runs against a home directory of its own.

    Not optional: the function under test *moves a directory*, and the one
    it moves is the person's real report archive.
    """

    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        patch = mock.patch.object(runfolder.Path, "home",
                                  classmethod(lambda cls: self.home))
        patch.start()
        self.addCleanup(patch.stop)
        env = mock.patch.dict("os.environ", {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        import os

        os.environ.pop(runfolder.ROOT_ENV, None)

    def desktop_root(self, *runs: str) -> Path:
        # Only ever written under the pre-rename name.
        old = self.home / "Desktop" / runfolder._OLD_DESKTOP_FOLDER
        for name in runs:
            (old / name).mkdir(parents=True)
            (old / name / "report.md").write_text(name, encoding="utf-8")
        return old


class TheDefaultRoot(_FakeHome):

    def test_it_is_under_documents(self):
        (self.home / "Documents").mkdir()
        self.assertEqual(runfolder.default_root(),
                         self.home / "Documents" / "XBrain Audit")

    def test_a_machine_with_no_documents_still_gets_somewhere(self):
        """A container or a server has no `~/Documents`, and an error is not
        an acceptable answer for "where does the report go"."""
        self.assertEqual(runfolder.default_root(), self.home / "XBrain Audit")

    def test_the_environment_still_wins(self):
        import os

        (self.home / "Documents").mkdir()
        with TemporaryDirectory() as elsewhere:
            os.environ[runfolder.ROOT_ENV] = elsewhere
            try:
                self.assertEqual(runfolder.default_root(), Path(elsewhere))
            finally:
                os.environ.pop(runfolder.ROOT_ENV, None)

    def test_nothing_is_written_to_the_desktop_any_more(self):
        (self.home / "Documents").mkdir()
        root = runfolder.prepare("https://example.com", ).run
        self.assertIn(self.home / "Documents", root.parents)
        self.assertNotIn(self.home / "Desktop", root.parents)


class WhatHappensToReportsAlreadyWritten(_FakeHome):

    def test_an_existing_desktop_archive_moves_across(self):
        (self.home / "Documents").mkdir()
        self.desktop_root("example.com", "shop")
        root = runfolder.default_root()
        self.assertEqual(sorted(p.name for p in root.iterdir()),
                         ["example.com", "shop"])
        self.assertEqual((root / "shop" / "report.md").read_text(
            encoding="utf-8"), "shop")

    def test_the_desktop_folder_is_gone_afterwards(self):
        """Copied and left behind is not what was asked for: the request was
        that the Desktop stops collecting folders."""
        (self.home / "Documents").mkdir()
        old = self.desktop_root("example.com")
        runfolder.default_root()
        self.assertFalse(old.exists())

    def test_an_existing_destination_is_never_merged_into(self):
        """And it is a decision, not a rescued error.

        Attempting the move anyway happens to leave the data intact -
        `rename` onto a non-empty directory fails - but it reports "could
        not be moved", which is a different and untrue thing to tell
        somebody. So the check is that nothing was said at all.
        """
        (self.home / "Documents").mkdir()
        new = self.home / "Documents" / "XBrain Audit"
        (new / "already-here").mkdir(parents=True)
        old = self.desktop_root("example.com")
        with mock.patch.object(runfolder.progress, "notice") as said:
            runfolder.default_root()
        said.assert_not_called()
        self.assertTrue(old.is_dir(), "the old archive was consumed")
        self.assertEqual([p.name for p in new.iterdir()], ["already-here"])

    def test_no_desktop_archive_is_not_an_error(self):
        (self.home / "Documents").mkdir()
        self.assertEqual(runfolder.default_root(),
                         self.home / "Documents" / "XBrain Audit")

    def test_a_move_that_cannot_happen_says_so_and_does_not_raise(self):
        """A sync client holding the folder, a cross-device home: the run
        still has to produce its documents."""
        (self.home / "Documents").mkdir()
        old = self.desktop_root("example.com")
        with mock.patch.object(runfolder.Path, "rename",
                               side_effect=OSError("busy")):
            root = runfolder.default_root()
        self.assertEqual(root, self.home / "Documents" / "XBrain Audit")
        self.assertTrue(old.is_dir())


if __name__ == "__main__":
    unittest.main()
