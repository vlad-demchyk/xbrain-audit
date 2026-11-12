"""The method combo has to decide what actually runs.

This file exists because of one bug, and the bug was not a crash: the window
offered "offline / AI / both", normalised the choice, reported it in the
status bar - and then started every copy pass with whatever detector a
*second* combo happened to name. Choosing AI ran the offline engine and
presented its findings as the model's answer. Nothing failed, so nothing
said anything.

So these tests assert the connection itself, not the shape of the widgets:
what `MainWindow._detector_for_request` hands to the worker, for each method.

Headless: Qt runs on the offscreen platform.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from analysis_modes import (
        AnalysisRequest, CHECK_ACCESSIBILITY, CHECK_AI_PATTERNS, METHOD_AI,
        METHOD_EMBEDDING, METHOD_LOCAL,
    )
    from detectors.judges import JUDGE_BY_PROVIDER
except Exception:  # noqa: BLE001 - no Qt here is a skip, not a failure
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 not available")
class MethodDecidesTheEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        # An account is a fact about this machine, not about the choice under
        # test: without pinning it, the request would normalise the AI method
        # away on a machine with nothing signed in, and the test would pass
        # for the wrong reason.
        # Pinned on AppState, which is where the answer now lives: the
        # window used to carry its own `_ai_available`, and the two could
        # disagree.
        self.window.app_state.set_ai_available(True)
        # Readiness has its own async tests. Pin it when this test changes
        # providers so routing is tested independently of machine credentials.
        self.window._refresh_account_control = lambda **_kwargs: None
        # Picking an account in the toolbar writes it to settings, which is
        # the point of the control - but a test run must not edit the config
        # of whoever is running it.
        self.window.settings.save = lambda: None
        self.window.view_model._last_request = None
        self.window._retranslate_choices()
        self._select(self.window.checks_combo,
                     (CHECK_ACCESSIBILITY, CHECK_AI_PATTERNS))

    def _select(self, combo, value):
        index = combo.findData(MainWindow.choice_key(value))
        self.assertGreaterEqual(index, 0, f"{value} is not offered")
        combo.setCurrentIndex(index)

    def _select_provider(self, name):
        index = self.window.provider_combo.findData(name)
        self.assertGreaterEqual(index, 0, f"{name} is not offered")
        self.window.provider_combo.setCurrentIndex(index)

    def test_offline_only_runs_the_offline_engine(self):
        self._select(self.window.method_combo, (METHOD_LOCAL,))
        name, _config = self.window._detector_for_request()
        self.assertEqual(name, "offline")

    def test_ai_only_runs_the_judge_of_the_chosen_account(self):
        self._select(self.window.method_combo, (METHOD_AI,))
        for provider, judge in JUDGE_BY_PROVIDER.items():
            with self.subTest(provider=provider):
                self._select_provider(provider)
                name, _config = self.window._detector_for_request()
                self.assertEqual(name, judge)

    def test_hybrid_runs_both_and_carries_the_judge_with_it(self):
        self._select(self.window.method_combo, (METHOD_LOCAL, METHOD_AI))
        self._select_provider("xformat")
        name, config = self.window._detector_for_request()
        self.assertEqual(name, "hybrid")
        self.assertEqual(config["judge_name"], JUDGE_BY_PROVIDER["xformat"])
        # The judge half is configured like any other judge, or an xFormat
        # run would reach the default base URL instead of the chosen one.
        self.assertIn("base_url", config["judge_config"])

    def test_the_ai_method_never_silently_runs_the_offline_engine(self):
        """The regression itself, stated as one assertion."""
        self._select(self.window.method_combo, (METHOD_AI,))
        name, _config = self.window._detector_for_request()
        self.assertNotEqual(name, "offline")

    def test_no_account_is_refused_before_it_is_offered(self):
        """With nothing signed in, the AI entries are not in the combo at
        all - the window does not offer a method it would then substitute."""
        self.window.app_state.set_ai_available(False)
        self.window._retranslate_choices()
        offered = [self.window.method_combo.itemData(i)
                   for i in range(self.window.method_combo.count())]
        self.assertEqual(offered, [
            MainWindow.choice_key((METHOD_LOCAL,)),
            MainWindow.choice_key((METHOD_EMBEDDING,)),
        ])
        self.assertFalse(self.window.method_combo.isEnabled())

    def test_a_stored_ai_method_with_no_account_is_stated_not_swallowed(self):
        """The other way in: a settings file that asks for the model pass on
        a machine that cannot pay for one. The request normalises back to
        offline and records why, which is what the status bar reads out."""
        request = AnalysisRequest(methods=(METHOD_LOCAL, METHOD_AI),
                                  ai_available=False).normalised()
        self.assertNotIn(METHOD_AI, request.methods)
        self.assertTrue(request.notes)

    def test_the_account_is_asked_for_only_when_a_model_reads(self):
        self._select(self.window.method_combo, (METHOD_LOCAL,))
        self.window._apply_mode_visibility()
        self.assertTrue(self.window.provider_combo.isHidden())

        self._select(self.window.method_combo, (METHOD_LOCAL, METHOD_AI))
        self.window._apply_mode_visibility()
        self.assertFalse(self.window.provider_combo.isHidden())

        # ... and not when no copy is judged at all: an accessibility-only
        # run has no text for a model to read.
        self._select(self.window.checks_combo, (CHECK_ACCESSIBILITY,))
        self.window._apply_mode_visibility()
        self.assertTrue(self.window.provider_combo.isHidden())

    def test_choosing_an_account_here_is_the_same_setting_the_dialog_writes(self):
        self._select(self.window.method_combo, (METHOD_AI,))
        self._select_provider("claude-code")
        self.assertEqual(self.window.settings.llm_provider, "claude-code")


if __name__ == "__main__":
    unittest.main()


class DetectorReachesACrawledSite(unittest.TestCase):
    """`--detector` has to mean the same thing on a site as in a folder.

    It did not. `_content_findings_from_pages` hardcoded the offline engine,
    so `fullscan https://site --detector llm-judge` crawled the site, said
    nothing, and ran the free heuristic - the AI mode was inert on the path
    most people use, and nothing raised to say so.
    """

    def _args(self, detector):
        import argparse

        return argparse.Namespace(detector=detector, provider=None,
                                  scope="both", no_typography=False,
                                  categories=None, no_unicode=False)

    def test_no_detector_is_the_offline_engine_alone(self):
        from cli_impl.fullscan import _content_passes

        passes = _content_passes(self._args(None))
        self.assertEqual(len(passes), 1)

    def test_naming_offline_explicitly_is_the_same_thing(self):
        from cli_impl.fullscan import _content_passes

        self.assertEqual(len(_content_passes(self._args("offline"))), 1)

    def test_a_judge_is_added_not_substituted(self):
        """The offline engine finds the exact character defects a model does
        not, so replacing it would be a downgrade wearing an upgrade's name."""
        from cli_impl.fullscan import _content_passes

        passes = _content_passes(self._args("ai"))
        self.assertEqual(len(passes), 2)
        self.assertEqual(passes[0].name, "offline")

    def test_a_judge_that_cannot_be_built_is_reported_not_swallowed(self):
        from cli_impl import fullscan

        import io
        import contextlib

        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            passes = fullscan._content_passes(self._args("no-such-detector"))
        self.assertEqual(len(passes), 1)          # the crawl is not lost
        self.assertIn("could not be used", captured.getvalue())

    def test_the_run_says_which_account_it_will_be_billed_to(self):
        from cli_impl import fullscan

        import io
        import contextlib

        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            fullscan._content_passes(self._args("ai"))
        # The judge's own name, not the alias that was typed: `ai` does not
        # say whose account pays and that is the part worth printing.
        self.assertIn("AI patterns:", captured.getvalue())
        self.assertNotIn("AI patterns: ai", captured.getvalue())


class TheSlowStageSaysSomething(unittest.TestCase):
    """A judge reads every block over the network.

    On ten pages that is minutes with nothing on screen. The crawl and the
    browser pass both count themselves out loud; this one did not, so the
    stage that can legitimately take longest was the one that looked hung.
    """

    class _Page:
        def __init__(self, url):
            from models import TextBlock

            self.url = url
            # Real blocks, and different on each page: with none there is
            # nothing to judge, and with identical text the run would
            # correctly collapse to a single batch.
            self.blocks = [
                TextBlock(block_id=f"{url}-{i}", page_url=url, dom_path="p",
                          text=f"a passage from {url} number {i}")
                for i in range(4)]

    class _Judge:
        """A judge that answers instantly and costs nothing.

        These two tests are about the counter, not about a model. With a
        real judge the answer depends on which account the machine happens
        to have: measured 2026-09-02 on CI, where no Claude Code session and
        no `ANTHROPIC_API_KEY` resolved to the API-key judge and the test
        failed with `DetectorUnavailable` instead of saying anything about
        progress. On a developer's machine the same line quietly spawned
        real `claude -p` processes.

        The name is load-bearing: `_cache_for` is what switches the counter
        on, and it keys off `detector.name` being neither empty nor
        `offline`.
        """

        name = "claude-code-llm-judge"
        model = ""
        effort = ""

        def analyze_blocks(self, blocks):
            return []

    def _run(self, detector):
        import argparse
        import contextlib
        import io
        import os
        import tempfile

        from cli_impl import fullscan
        from cli_impl.fullscan import _content_findings_from_pages

        args = argparse.Namespace(detector=detector, provider=None,
                                  scope="both", no_typography=False,
                                  categories=None, no_unicode=False)
        pages = [self._Page(f"https://example.com/{i}") for i in range(3)]
        captured = io.StringIO()
        real = fullscan._content_passes
        # Only the judge half is faked. The offline case has to go through
        # the real builder, because "the offline pass stays quiet" is a
        # statement about the pass this function would actually construct.
        if detector:
            fullscan._content_passes = lambda _args: [self._Judge()]
        # An isolated cache. Without it the previous test run's answers come
        # back as this run's, and the detector is never called at all.
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["XAUDIT_JUDGMENT_CACHE"] = tmp
            try:
                with contextlib.redirect_stderr(captured):
                    _content_findings_from_pages(pages, args)
            finally:
                fullscan._content_passes = real
                os.environ.pop("XAUDIT_JUDGMENT_CACHE", None)
        return captured.getvalue()

    def test_a_judged_run_counts_its_batches(self):
        """By batch, not by page.

        Deduplication is across the whole run, so the work stopped being per
        page: a "3/10 pages" counter would be counting something that is no
        longer happening.
        """
        output = self._run("ai")
        self.assertIn("batches]", output)
        self.assertIn("[AI patterns 1/", output)

    def test_the_offline_pass_stays_quiet(self):
        """It finishes in a tenth of a second; a progress line is noise."""
        self.assertNotIn("[AI patterns", self._run(None))


class BatchingIsNotDefeated(unittest.TestCase):
    """The judges batch in eights; a per-block loop throws that away.

    The Claude Code judge starts one `claude -p` process per call, so calling
    `analyze_block` in a loop turned roughly a hundred requests into roughly
    eight hundred. Measured on a live ten-page run: still going after five
    minutes, on course for about an hour.
    """

    class _Page:
        def __init__(self, url, blocks):
            self.url = url
            self.blocks = blocks

    class _CountingDetector:
        name = "counting"

        def __init__(self):
            self.block_calls = 0
            self.batch_calls = 0

        def analyze_block(self, block):
            self.block_calls += 1
            return []

        def analyze_blocks(self, blocks):
            self.batch_calls += 1
            return []

    def test_the_whole_page_is_handed_over_at_once(self):
        from models import TextBlock
        from cli_impl import fullscan

        detector = self._CountingDetector()
        blocks = [TextBlock(block_id=f"b{i}", text=f"passage {i}",
                            page_url="https://example.com", dom_path="p")
                  for i in range(20)]
        page = self._Page("https://example.com", blocks)

        import os
        import tempfile

        real = fullscan._content_passes
        fullscan._content_passes = lambda args: [detector]
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["XAUDIT_JUDGMENT_CACHE"] = tmp
            try:
                fullscan._content_findings_from_pages([page], None)
            finally:
                fullscan._content_passes = real
                os.environ.pop("XAUDIT_JUDGMENT_CACHE", None)

        self.assertEqual(detector.batch_calls, 1)
        self.assertEqual(detector.block_calls, 0)


class TheRowShowsWhatWasJudged(unittest.TestCase):
    """Five reasons about five sentences must not show one block five times.

    A live run's hero block produced five findings with five different
    explanations and five identical text columns, because this path showed
    `block.text[:200]` while the local scan has always sliced the span. The
    reader could not tell which sentence each reason was about.
    """

    class _Page:
        def __init__(self, url, blocks):
            self.url = url
            self.blocks = blocks

    class _Judge:
        name = "fake-judge"

        def __init__(self, ranges):
            self.ranges = ranges

        def analyze_blocks(self, blocks):
            from models import Confidence, TextSpan

            block = blocks[0]
            return [TextSpan(block_id=block.block_id, start=s, end=e,
                             score=0.8, confidence=Confidence.HIGH,
                             detector_name=self.name, explanation=f"reason {i}",
                             details={"source": "model"})
                    for i, (s, e) in enumerate(self.ranges)]

    def _run(self, text, ranges):
        from models import TextBlock
        from cli_impl import fullscan

        block = TextBlock(block_id="b1", text=text,
                          page_url="https://example.com", dom_path="p")
        page = self._Page("https://example.com", [block])
        import os
        import tempfile

        real = fullscan._content_passes
        fullscan._content_passes = lambda args: [self._Judge(ranges)]
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["XAUDIT_JUDGMENT_CACHE"] = tmp
            try:
                return fullscan._content_findings_from_pages([page], None)
            finally:
                fullscan._content_passes = real
                os.environ.pop("XAUDIT_JUDGMENT_CACHE", None)

    def test_each_row_carries_its_own_passage(self):
        text = "First sentence here. Second sentence here. Third one here."
        found = self._run(text, [(0, 20), (21, 42), (43, len(text))])
        texts = [f["text"] for f in found]
        self.assertEqual(len(set(texts)), 3)
        self.assertIn("First sentence", texts[0])
        self.assertIn("Second sentence", texts[1])

    def test_a_whole_block_flag_still_shows_the_block(self):
        """The judge falls back to the whole block when it paraphrases."""
        text = "One passage that was not quoted verbatim."
        found = self._run(text, [(0, len(text))])
        self.assertEqual(found[0]["text"], text)

    def test_an_empty_slice_falls_back_to_the_block(self):
        """A zero-width span would otherwise print an empty row."""
        text = "Some text."
        found = self._run(text, [(3, 3)])
        self.assertEqual(found[0]["text"], text)


class ModelAndEffortAreSettable(unittest.TestCase):
    """The AI pass runs over every block, so what it costs is a setting.

    `sonnet` at `low` effort is enough for this job - it classifies short
    passages against a fixed rubric - and there was no way to say so from the
    CLI, the TUI or the window.
    """

    def setUp(self):
        """A stub `claude` on `CLAUDE_CODE_BIN`.

        `_argv` asks the provider for its binary and refuses without one, so
        without this the test measures whether Claude Code is installed on
        the machine running it - which on CI it is not. What is under test
        is the argv the flags produce, and that does not need a real binary,
        only a path that exists.
        """
        import tempfile
        from pathlib import Path
        from unittest import mock

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        stub = Path(tmp.name) / "claude"
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
        patch = mock.patch.dict(os.environ, {"CLAUDE_CODE_BIN": str(stub)})
        patch.start()
        self.addCleanup(patch.stop)

    def _detector(self, model=None, effort=None):
        import argparse

        from cli_impl.scanning import _create_detector

        # The provider is named, not left to the machine. `provider=None`
        # asks `rewriter` which account is in play, so the class under test
        # was whichever one this computer happens to be signed into: a
        # Claude Code session gives `ClaudeCodeLLMJudgeDetector`, which has
        # `_get_provider`, and a machine with neither session nor key gives
        # `ClaudeLLMJudgeDetector`, which does not. Measured 2026-09-02 on
        # CI, where all four tests failed with `AttributeError`. What is
        # being tested is that a flag reaches a provider CLI's argv, so the
        # provider is part of the case.
        return _create_detector(argparse.Namespace(
            detector="ai", provider="claude-code", model=model, effort=effort))

    def _argv(self, detector):
        # The provider the run would actually use, reached without the auth
        # gate. There are two paths and both matter: with a flag set,
        # `_create_detector` builds a configured provider and injects it -
        # that injection *is* how a flag reaches the invocation - and with
        # nothing set the judge builds its own from the settings.
        # `_get_provider` returns the same object on both, and on the second
        # one it first checks that the account is signed in. An account is
        # not what this measures: on CI that check failed and the test
        # reported nothing about `--model` at all.
        provider = detector._provider or detector._build_provider()
        return provider._argv("system prompt")

    def test_nothing_asked_for_leaves_the_session_alone(self):
        """An unset flag must not overwrite the setting with its own default."""
        argv = self._argv(self._detector())
        self.assertNotIn("--model", argv)
        self.assertNotIn("--effort", argv)

    def test_a_model_reaches_the_invocation(self):
        argv = self._argv(self._detector(model="sonnet"))
        self.assertIn("--model", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "sonnet")

    def test_an_effort_reaches_the_invocation(self):
        argv = self._argv(self._detector(effort="low"))
        self.assertIn("--effort", argv)
        self.assertEqual(argv[argv.index("--effort") + 1], "low")

    def test_one_may_be_set_without_the_other(self):
        argv = self._argv(self._detector(model="haiku"))
        self.assertIn("--model", argv)
        self.assertNotIn("--effort", argv)

    def test_the_settings_carry_it_when_the_flags_do_not(self):
        import config
        import rewriter

        settings = config.Settings.load()
        settings.claude_code_model = "sonnet"
        settings.claude_code_effort = "low"
        provider = rewriter.build_provider(settings, force="claude-code")
        self.assertEqual(provider.model, "sonnet")
        self.assertEqual(provider.effort, "low")

    def test_a_flag_beats_the_setting(self):
        import config
        import rewriter

        settings = config.Settings.load()
        settings.claude_code_model = "opus"
        provider = rewriter.build_provider(settings, force="claude-code",
                                           model="haiku")
        self.assertEqual(provider.model, "haiku")

    def test_the_tui_offers_both(self):
        from tui.screens.settings import CHOICES

        names = {attribute for attribute, _label, _options in CHOICES}
        self.assertIn("claude_code_model", names)
        self.assertIn("claude_code_effort", names)
