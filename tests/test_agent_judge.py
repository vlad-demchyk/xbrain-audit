"""Agent-as-judge workflow: agent-scan, agent-judge, and hybrid merge.

Tests the two-step workflow where the agent (opencode, Claude Code, Cursor)
acts as the LLM judge without an API key. Covers:

- agent-scan output structure and candidates
- agent-scan --full mode with raw blocks
- agent-judge simple merge (offline + agent judgments)
- agent-judge hybrid merge (offline + agent judgments + agent findings)
- detection rules presence in output
- block_id stability through pipeline
- fullscan --agent integration
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


def _cli(*args, **kwargs):
    return subprocess.run([sys.executable, str(ROOT / "cli.py"), *args],
                          capture_output=True, text=True, encoding="utf-8", timeout=180,
                          cwd=str(ROOT), **kwargs)


def _json_cli(*args):
    done = _cli(*args)
    if done.returncode not in (EXIT_OK, EXIT_FINDINGS):
        raise RuntimeError(f"CLI failed: {done.stderr}")
    return json.loads(done.stdout)


# -- fixtures ---------------------------------------------------------------

AI_HTML = """\
<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>AI Test</title></head><body>
<p>It is worth noting that this comprehensive solution delves into the
intricacies of modern software development.</p>
<p>Unlock the full potential of your development process with our
cutting-edge tools. Our seamless integration ensures focus.</p>
<p>In today's fast-paced digital landscape, it is essential to stay
ahead of the curve.</p>
<p>This is a normal human-written sentence. The cat sat on the mat.</p>
</body></html>"""

HUMAN_HTML = """\
<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Clean Page</title></head><body>
<p>The quick brown fox jumps over the lazy dog.</p>
<p>I went to the store yesterday and bought some milk.</p>
</body></html>"""


# -- agent-scan output structure --------------------------------------------

class AgentScanOutputTests(unittest.TestCase):
    """agent-scan produces valid, structured JSON."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.html"
            p.write_text(AI_HTML, encoding="utf-8")
            cls.data = _json_cli("agent-scan", str(p), "--json")

    def test_output_has_candidates(self):
        self.assertIn("candidates", self.data)
        self.assertIsInstance(self.data["candidates"], list)

    def test_output_has_total_blocks(self):
        self.assertIn("total_blocks", self.data)
        self.assertGreater(self.data["total_blocks"], 0)

    def test_output_has_total_candidates(self):
        self.assertIn("total_candidates", self.data)
        self.assertEqual(self.data["total_candidates"],
                         len(self.data["candidates"]))

    def test_output_has_threshold(self):
        self.assertIn("threshold", self.data)
        self.assertGreater(self.data["threshold"], 0)

    def test_output_has_detection_rules(self):
        self.assertIn("detection_rules", self.data)

    def test_output_has_instruction(self):
        self.assertIn("instruction", self.data)
        self.assertIn("detection_rules", self.data)

    def test_output_mode_is_candidates_only(self):
        self.assertEqual(self.data["mode"], "candidates-only")


class AgentScanCandidateStructureTests(unittest.TestCase):
    """Each candidate has the required fields."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.html"
            p.write_text(AI_HTML, encoding="utf-8")
            cls.data = _json_cli("agent-scan", str(p), "--json")
            cls.candidates = cls.data["candidates"]

    def test_candidates_are_non_empty(self):
        self.assertGreater(len(self.candidates), 0)

    def test_candidate_has_block_id(self):
        for c in self.candidates:
            self.assertIn("block_id", c)
            self.assertTrue(len(c["block_id"]) > 0)

    def test_candidate_has_file(self):
        for c in self.candidates:
            self.assertIn("file", c)

    def test_candidate_has_text(self):
        for c in self.candidates:
            self.assertIn("text", c)
            self.assertTrue(len(c["text"]) > 0)

    def test_candidate_has_language(self):
        for c in self.candidates:
            self.assertIn("language", c)

    def test_candidate_has_offline_score(self):
        for c in self.candidates:
            self.assertIn("offline_score", c)
            self.assertGreaterEqual(c["offline_score"], 0)
            self.assertLessEqual(c["offline_score"], 1)

    def test_candidate_has_offline_explanation(self):
        for c in self.candidates:
            self.assertIn("offline_explanation", c)


# -- detection rules --------------------------------------------------------

class DetectionRulesTests(unittest.TestCase):
    """Detection rules contain all required sections."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.html"
            p.write_text(AI_HTML, encoding="utf-8")
            cls.rules = _json_cli("agent-scan", str(p), "--json")["detection_rules"]

    def test_has_statistical_signals(self):
        self.assertIn("statistical_signals", self.rules)
        for name in ("uniformity", "repetition", "dash_density"):
            self.assertIn(name, self.rules["statistical_signals"])

    def test_statistical_signals_have_weights(self):
        for name, info in self.rules["statistical_signals"].items():
            self.assertIn("weight", info)
            self.assertGreater(info["weight"], 0)

    def test_has_structural_patterns(self):
        self.assertIn("structural_patterns", self.rules)
        for lang in ("en", "uk", "it"):
            self.assertIn(lang, self.rules["structural_patterns"])
            self.assertGreater(len(self.rules["structural_patterns"][lang]), 0)

    def test_has_cliche_phrases(self):
        self.assertIn("cliche_phrases", self.rules)
        self.assertIn("en_strong", self.rules["cliche_phrases"])
        self.assertGreater(len(self.rules["cliche_phrases"]["en_strong"]), 0)

    def test_has_scoring_formula(self):
        self.assertIn("scoring_formula", self.rules)
        self.assertIn("base", self.rules["scoring_formula"])

    def test_has_important_notes(self):
        self.assertIn("important_notes", self.rules)
        notes = self.rules["important_notes"]
        self.assertTrue(any("dash" in n.lower() for n in notes),
                        "Should mention dash density as AI signal")


# -- agent-scan --full mode -------------------------------------------------

class AgentScanFullModeTests(unittest.TestCase):
    """--full mode outputs all blocks for independent agent analysis."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.html"
            p.write_text(AI_HTML, encoding="utf-8")
            cls.data = _json_cli("agent-scan", str(p), "--full", "--json")

    def test_mode_is_full(self):
        self.assertEqual(self.data["mode"], "full")

    def test_blocks_are_present(self):
        self.assertIn("blocks", self.data)
        self.assertGreater(len(self.data["blocks"]), 0)

    def test_blocks_have_block_id(self):
        for b in self.data["blocks"]:
            self.assertIn("block_id", b)

    def test_blocks_have_text(self):
        for b in self.data["blocks"]:
            self.assertIn("text", b)
            self.assertTrue(len(b["text"]) > 0)

    def test_blocks_have_file(self):
        for b in self.data["blocks"]:
            self.assertIn("file", b)

    def test_blocks_have_language(self):
        for b in self.data["blocks"]:
            self.assertIn("language", b)

    def test_full_instruction_mentions_hybrid(self):
        self.assertIn("HYBRID", self.data["instruction"])

    def test_full_instruction_mentions_two_tasks(self):
        self.assertIn("JUDGE CANDIDATES", self.data["instruction"])
        self.assertIn("READ BLOCKS", self.data["instruction"])


# -- agent-judge simple merge ------------------------------------------------

class AgentJudgeSimpleTests(unittest.TestCase):
    """Simple merge: offline + agent judgments."""

    def _run_judge(self, html, judgments):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.html"
            p.write_text(html, encoding="utf-8")
            jf = Path(td) / "judgments.json"
            jf.write_text(json.dumps(judgments), encoding="utf-8")
            done = _cli("agent-judge", str(p), "--json",
                        "--judgments", str(jf))
            if done.returncode not in (EXIT_OK, EXIT_FINDINGS):
                self.fail(f"agent-judge failed: {done.stderr}")
            return json.loads(done.stdout)

    def _get_candidates(self, html):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.html"
            p.write_text(html, encoding="utf-8")
            return _json_cli("agent-scan", str(p), "--json")["candidates"]

    def test_agent_judgments_merge_with_offline(self):
        candidates = self._get_candidates(AI_HTML)
        judgments = [
            {"block_id": c["block_id"], "score": 0.8, "reason": "AI detected"}
            for c in candidates
        ]
        result = self._run_judge(AI_HTML, judgments)
        self.assertGreater(result["counts"]["total"], 0)

    def test_high_agent_score_boosts_finding(self):
        # Use pipeline to keep block_ids stable
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.html"
            p.write_text(AI_HTML, encoding="utf-8")
            # Run agent-scan | transform | agent-judge in pipeline
            scan_done = _cli("agent-scan", str(p), "--json")
            scan = json.loads(scan_done.stdout)
            candidates = scan["candidates"]
            judgments = [
                {"block_id": c["block_id"], "score": 0.9, "reason": "Strong AI signal"}
                for c in candidates
            ]
            jf = Path(td) / "judgments.json"
            jf.write_text(json.dumps(judgments), encoding="utf-8")
            done = _cli("agent-judge", str(p), "--json", "--judgments", str(jf))
            result = json.loads(done.stdout)
        # Should have findings with high scores
        self.assertGreater(result["counts"]["total"], 0)
        scores = [f["score"] for f in result["findings"]]
        self.assertTrue(any(s >= 0.5 for s in scores))

    def test_low_agent_score_keeps_offline(self):
        candidates = self._get_candidates(AI_HTML)
        judgments = [
            {"block_id": c["block_id"], "score": 0.1, "reason": "Looks human"}
            for c in candidates
        ]
        result = self._run_judge(AI_HTML, judgments)
        self.assertGreater(result["counts"]["total"], 0)

    def test_empty_judgments_keeps_offline(self):
        result = self._run_judge(AI_HTML, [])
        self.assertGreater(result["counts"]["total"], 0)


# -- agent-judge hybrid merge ------------------------------------------------

class AgentJudgeHybridTests(unittest.TestCase):
    """Hybrid merge: offline + agent judgments + agent independent findings."""

    def _run_pipeline(self, html, transform_fn):
        """Run agent-scan | transform | agent-judge in a single pipeline."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.html"
            p.write_text(html, encoding="utf-8")
            # Run agent-scan
            scan_done = _cli("agent-scan", str(p), "--full", "--json")
            if scan_done.returncode != EXIT_OK:
                self.fail(f"agent-scan failed: {scan_done.stderr}")
            scan_data = json.loads(scan_done.stdout)
            # Transform the output (agent's work)
            agent_output = transform_fn(scan_data)
            # Run agent-judge with the transformed output
            jf = Path(td) / "agent_output.json"
            jf.write_text(json.dumps(agent_output), encoding="utf-8")
            done = _cli("agent-judge", str(p), "--json",
                        "--judgments", str(jf))
            if done.returncode not in (EXIT_OK, EXIT_FINDINGS):
                self.fail(f"agent-judge failed: {done.stderr}")
            return json.loads(done.stdout)

    def test_agent_only_finding_appears(self):
        """Agent finds something offline missed."""
        def transform(scan_data):
            blocks = scan_data["blocks"]
            # Agent finds the last block (human text) as suspicious
            agent_findings = [{
                "block_id": blocks[-1]["block_id"],
                "start": 0,
                "end": len(blocks[-1]["text"]),
                "score": 0.7,
                "reason": "Suspiciously normal"
            }]
            return {"judgments": [], "agent_findings": agent_findings,
                    "blocks": blocks}

        result = self._run_pipeline(AI_HTML, transform)
        self.assertGreater(result["counts"]["total"], 0)

    def test_agreement_marks_both(self):
        """When offline and agent agree on a finding."""
        def transform(scan_data):
            blocks = scan_data["blocks"]
            candidates = scan_data["candidates"]
            # Agent confirms all candidates
            judgments = [
                {"block_id": c["block_id"], "score": 0.8, "reason": "Confirmed"}
                for c in candidates
            ]
            # Agent also finds the same blocks independently
            agent_findings = []
            for c in candidates:
                agent_findings.append({
                    "block_id": c["block_id"],
                    "start": 0,
                    "end": len(c["text"]),
                    "score": 0.8,
                    "reason": "Confirmed independently"
                })
            return {"judgments": judgments, "agent_findings": agent_findings,
                    "blocks": blocks}

        result = self._run_pipeline(AI_HTML, transform)
        explanations = [f["explanation"] for f in result["findings"]]
        self.assertTrue(any("[both]" in e for e in explanations),
                        "Should have at least one agreement finding")

    def test_offline_only_finding_preserved(self):
        """Offline finding that agent didn't confirm stays."""
        def transform(scan_data):
            blocks = scan_data["blocks"]
            # One dummy agent finding to trigger hybrid mode
            agent_findings = [{
                "block_id": blocks[0]["block_id"],
                "start": 0, "end": 1,
                "score": 0.1, "reason": "dummy"
            }]
            return {"judgments": [], "agent_findings": agent_findings,
                    "blocks": blocks}

        result = self._run_pipeline(AI_HTML, transform)
        explanations = [f["explanation"] for f in result["findings"]]
        # Should have offline-only findings (agent didn't confirm most)
        self.assertTrue(any("offline-only" in e for e in explanations),
                        "Should have offline-only findings")


# -- clean page produces no candidates --------------------------------------

class CleanPageTests(unittest.TestCase):
    """A clean page should produce few or no candidates."""

    def test_clean_page_has_no_candidates(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "clean.html"
            p.write_text(HUMAN_HTML, encoding="utf-8")
            data = _json_cli("agent-scan", str(p), "--json")
        self.assertEqual(data["total_candidates"], 0)


# -- threshold parameter ----------------------------------------------------

class ThresholdTests(unittest.TestCase):
    """--threshold controls which candidates are included."""

    def test_lower_threshold_includes_more(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.html"
            p.write_text(AI_HTML, encoding="utf-8")
            low = _json_cli("agent-scan", str(p), "--threshold", "0.1", "--json")
            high = _json_cli("agent-scan", str(p), "--threshold", "0.5", "--json")
        self.assertGreaterEqual(low["total_candidates"], high["total_candidates"])


# -- CLI integration ---------------------------------------------------------

class CLIIntegrationTests(unittest.TestCase):
    """End-to-end CLI commands work without errors."""

    def test_agent_scan_help(self):
        done = _cli("agent-scan", "--help")
        self.assertEqual(done.returncode, EXIT_OK)
        self.assertIn("--full", done.stdout)
        self.assertIn("--threshold", done.stdout)

    def test_agent_judge_help(self):
        done = _cli("agent-judge", "--help")
        self.assertEqual(done.returncode, EXIT_OK)
        self.assertIn("--judgments", done.stdout)
        self.assertIn("--hybrid", done.stdout)

    def test_fullscan_help(self):
        done = _cli("fullscan", "--help")
        self.assertEqual(done.returncode, EXIT_OK)
        self.assertIn("--agent", done.stdout)

    def test_agent_scan_missing_path_is_no_candidates(self):
        done = _cli("agent-scan", "/no/such/path", "--json")
        # agent-scan returns 0 with empty candidates for missing paths
        data = json.loads(done.stdout)
        self.assertEqual(data["total_candidates"], 0)

    def test_agent_judge_missing_path_is_no_findings(self):
        done = _cli("agent-judge", "/no/such/path", "--json",
                    "--judgments", "-",
                    input="[]")
        # agent-judge returns 0 for missing paths (no files = no findings)
        self.assertEqual(done.returncode, EXIT_OK)


# -- version -----------------------------------------------------------------

class VersionTests(unittest.TestCase):
    """App version is defined."""

    def test_version_is_defined(self):
        from config import APP_VERSION
        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+$")

    def test_version_is_recent(self):
        from config import APP_VERSION
        major, minor, patch = (int(x) for x in APP_VERSION.split("."))
        self.assertGreaterEqual(major, 0)
        self.assertGreaterEqual(minor, 5)


if __name__ == "__main__":
    unittest.main()
