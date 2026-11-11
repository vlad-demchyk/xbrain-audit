"""Catch missing translations and visible hardcoded TUI choice labels."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from i18n.translations import LANGUAGES, _STRINGS, t


ROOT = Path(__file__).resolve().parents[1]


class TranslationCatalog(unittest.TestCase):
    def test_every_entry_has_a_nonempty_value_in_every_supported_language(self):
        for key, translations in _STRINGS.items():
            with self.subTest(key=key):
                self.assertEqual(set(translations), set(LANGUAGES))
                for lang, value in translations.items():
                    self.assertTrue(value.strip(), f"{key}/{lang} is empty")

    def test_static_translation_calls_in_gui_and_tui_name_real_keys(self):
        missing = []
        for surface in (ROOT / "ui", ROOT / "tui"):
            for path in surface.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call) or not node.args:
                        continue
                    function = node.func
                    name = (function.id if isinstance(function, ast.Name)
                            else function.attr if isinstance(function, ast.Attribute)
                            else "")
                    if name not in {"t", "tr"}:
                        continue
                    key = node.args[0]
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        if key.value not in _STRINGS:
                            missing.append(f"{path.relative_to(ROOT)}:{node.lineno}: {key.value}")
        self.assertEqual(missing, [])

    def test_tui_settings_choices_are_translated_or_language_names(self):
        from tui.screens.settings import CHOICES

        language_names = {"Українська", "English", "Italiano"}
        for lang in LANGUAGES:
            for attribute, _label, options in CHOICES:
                for label, _value in options:
                    with self.subTest(lang=lang, setting=attribute, label=label):
                        if label in language_names or label.isdigit():
                            continue
                        self.assertIn(label, _STRINGS)
                        self.assertEqual(t(label, lang), _STRINGS[label][lang])
                        self.assertNotEqual(t(label, lang), label)

    def test_dynamic_tui_choices_have_translations(self):
        from audit.base import CATEGORIES, CONFIDENCE_ORDER
        from audit.responsive import BREAKPOINTS
        from tui.screens.results import _SUMMARY_DETECTOR_KEYS

        keys = {
            "tui_detector_offline", "tui_detector_embedding",
            "tui_detector_hybrid", "tui_detector_judge", "tui_detector_none",
            "breakpoint_default", "breakpoint_all", "breakpoint_desktop_mobile",
            "tui_medium_auto", "setup_medium_web", "setup_medium_email",
            "tui_account_not_xformat", "tui_account_elsewhere_anthropic",
            "tui_account_elsewhere_claude-code", "tui_sum_target",
            "tui_sum_by", "tui_sum_audit_severity",
        }
        keys.update(f"breakpoint_{name}" for name, _width, _height in BREAKPOINTS)
        keys.update(f"audit_category_{value}" for value in CATEGORIES)
        keys.update(f"certainty_{value}" for value in CONFIDENCE_ORDER)
        keys.update(_SUMMARY_DETECTOR_KEYS.values())
        for key in keys:
            with self.subTest(key=key):
                self.assertIn(key, _STRINGS)
                for lang in LANGUAGES:
                    self.assertTrue(t(key, lang).strip())

    def test_dynamic_result_labels_translate_detector_and_severity_rows(self):
        from tui.screens.results import summary_label, summary_rows

        payload = {
            "target": "https://example.com",
            "summary": {"total_findings": 4, "ai_patterns": 2,
                        "characters": 2, "accessibility": 1,
                        "seo": 1, "performance": 1, "best_practices": 1},
            "counts": {"offline": 1, "heuristic": 1,
                       "unicode-anomalies": 1, "hybrid": 1,
                       "embedding": 1, "claude-llm-judge": 1,
                       "claude-code-llm-judge": 1,
                       "xformat-llm-judge": 1, "critical": 1},
            "audit": {"counts": {"serious": 1}},
        }
        rows = summary_rows(payload)
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                shown = {label: summary_label(label, lang) for label, _ in rows}
                self.assertEqual(shown["target"], t("tui_sum_target", lang))
                self.assertEqual(shown["critical"], t("tui_sum_critical", lang))
                self.assertEqual(
                    shown["audit serious"],
                    t("tui_sum_audit_severity", lang,
                      severity=t("severity_serious", lang)))
                for detector, key in {
                    "offline": "tui_detector_offline",
                    "heuristic": "tui_detector_heuristic",
                    "unicode-anomalies": "tui_detector_unicode_anomalies",
                    "hybrid": "tui_detector_hybrid",
                    "embedding": "tui_detector_embedding",
                    "claude-llm-judge": "tui_detector_claude",
                    "claude-code-llm-judge": "tui_detector_claude_code",
                    "xformat-llm-judge": "tui_detector_xformat",
                }.items():
                    label = f"by {detector}"
                    self.assertEqual(shown[label], t(
                        "tui_sum_by", lang, detector=t(key, lang)))

    def test_dynamic_log_labels_have_translations(self):
        import applog

        keys = set(applog._LEVEL_KEYS.values()) | set(applog._EVENT_KEYS.values())
        for key in keys:
            with self.subTest(key=key):
                self.assertIn(key, _STRINGS)
                for lang in LANGUAGES:
                    self.assertTrue(t(key, lang).strip())

    def test_localized_uninstall_labels_keep_the_path(self):
        from pathlib import Path
        from uninstaller import UninstallItem, display_item

        item = UninstallItem(
            key="legacy-config", kind="dir", path=Path("/tmp/legacy"),
            label="/tmp/legacy (pre-rename settings)")
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                shown = display_item(item, lang)
                # The path as this OS writes it: `\tmp\legacy` on Windows.
                self.assertIn(str(Path("/tmp/legacy")), shown)
                self.assertNotIn("pre-rename settings", shown)

    def test_tui_header_subtitle_is_localized_in_every_language(self):
        import config
        from tui.app import XAnalyzeApp

        app = XAnalyzeApp()
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                app.lang = lang
                self.assertEqual(app._localized_subtitle(),
                                 t("tui_subtitle", lang,
                                   version=config.APP_VERSION))


if __name__ == "__main__":
    unittest.main()
