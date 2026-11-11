"""The agent workflow commands.

`agent-scan` runs the free offline detector and hands candidate blocks to
an LLM coding agent; `agent-judge` reads the agent's judgments back and
merges them into a final report. No API key, no registration - the agent
IS the judge.
"""
from __future__ import annotations

import json
import os
import sys

import duplicates
import progress

from detectors.factory import DetectorFactory
from models import Confidence, score_to_confidence

from cli_impl import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK
from cli_impl.auditpass import looks_like_url, with_scheme
from cli_impl.scanning import _categories, _collect_files
from cli_impl.output import _print_human, _print_json


def _blocks_from_pages(pages) -> list:
    """Crawled page blocks, adapted to the shape this pipeline reads.

    `TextBlock` carries `page_url`; everything downstream here - the origin
    matcher, the finding dicts, the human output - reads `file_path`,
    `line_number` and `start`/`end`, because it was written for a repository
    scan. Adapting at the boundary keeps one pipeline instead of two.

    The page URL becomes the "file". A page has no lines, so the line is 0
    and the offsets span the block: the origin matcher falls back to
    matching on the wording, which is what actually survives between a scan
    and the judgment of it - `block_id` is a fresh uuid every process, so it
    never does.
    """
    from models import CodeBlock

    blocks = []
    for page in pages:
        for block in page.blocks:
            blocks.append(CodeBlock(
                block_id=block.block_id,
                file_path=page.url,
                start=0,
                end=len(block.text),
                text=block.text,
                line_number=0,
                language_hint=block.language_hint,
            ))
    return blocks


def _agent_blocks(args, walked: list | None = None) -> list:
    """The blocks to judge, from whichever kind of target was named.

    A URL is crawled; a path is walked. `agent-scan` and `agent-judge` used
    to walk the filesystem unconditionally, so pointing either at a website
    produced zero blocks - and for `agent-judge` that meant every judgment
    the agent had just made matched nothing and was dropped with a single
    warning. `fullscan --agent` on a URL prints an instruction to run
    exactly that command, so the documented workflow ended in silence.
    """
    targets = list(getattr(args, "paths", None) or [])
    urls = [t for t in targets if looks_like_url(t)]
    paths = [t for t in targets if t not in urls]

    blocks: list = []
    if paths:
        files = _collect_files(paths, args, diagnostics_out=walked)
        blocks.extend(b for f in files for b in f.blocks)
    for url in urls:
        blocks.extend(_blocks_from_pages(_crawl_for_agent(url, args)))
    return blocks


def _crawl_for_agent(url: str, args):
    """Crawl one URL with the same rules the audit uses."""
    from cli_impl.auditpass import _crawl_maybe_rendering, _render_mode
    from crawler import CrawlConfig

    config = CrawlConfig(max_depth=getattr(args, "depth", 0) or 0,
                         max_pages=getattr(args, "max_pages", None) or 30,
                         render_mode=_render_mode(args))
    progress.stage("crawl", "begin",
                   f"# [crawl] {with_scheme(url)} depth={config.max_depth}",
                   depth=config.max_depth, target=with_scheme(url))
    pages = _crawl_maybe_rendering(with_scheme(url), config)
    progress.stage("crawl", "end", f"# [crawl done] {len(pages)} page(s)",
                   pages=len(pages))
    return pages


def _agent_detection_rules() -> dict:
    """All AI detection rules the system knows, for the agent LLM judge."""
    return {
        "statistical_signals": {
            "uniformity": {
                "weight": 0.40,
                "description": "Sentence length variation (burstiness). Human writing varies a lot; AI is uniform.",
                "score_meaning": "0.0 = bursty (human), 1.0 = uniform (AI-like)",
                "threshold": "Below 3 sentences: not measured"
            },
            "repetition": {
                "weight": 0.35,
                "description": "Lexical diversity (type-token ratio). AI repeats words more.",
                "score_meaning": "0.0 = diverse (human), 1.0 = repetitive (AI-like)",
                "threshold": "Below 20 words: not measured"
            },
            "dash_density": {
                "weight": 0.25,
                "description": "Em/en-dash usage density. AI overuses em dashes as commas/parentheses.",
                "score_meaning": "0.3 dashes/100w = normal human, >2/100w = heavy AI-like",
                "note": "This IS a real AI signal. Do NOT dismiss it as 'just typography'."
            }
        },
        "structural_patterns": {
            "en": [
                "not just X but Y",
                "it's not about X, it's about Y",
                "no X. no Y. just Z.",
                "whether you're X or Y",
                "take your X to the next level"
            ],
            "uk": [
                "не просто X а Y",
                "справа не в X справа в Y",
                "чи ви X чи Y",
                "це не просто про X; це про Y",
                "жодних X. жодних Y. лише Z.",
                "вивести X на новий рівень"
            ],
            "it": [
                "non solo X ma anche Y",
                "non si tratta di X si tratta di Y",
                "che tu sia X o Y",
                "niente X. niente Y. solo Z.",
                "portare X a un nuovo livello"
            ]
        },
        "cliche_phrases": {
            "description": "Phrases AI reaches for far more than humans. Strong phrases (with space) weight 0.30, weak (single word) weight 0.10.",
            "en_strong": [
                "it's important to note", "it is worth mentioning", "it should be noted that",
                "in today's fast-paced world", "in today's digital age", "in the era of",
                "in a world where", "furthermore,", "moreover,", "additionally,",
                "in conclusion", "to summarize", "let's dive in", "let's explore",
                "unlock the potential", "seamless experience", "look no further",
                "elevate your", "unleash the power", "game-changer",
                "comprehensive solution", "all-in-one solution", "intuitive interface",
                "in just a few clicks", "join thousands of", "satisfied users",
                "streamline your workflow", "bridges the gap between"
            ],
            "en_weak": [
                "delve", "underscore", "pivotal", "realm", "harness", "illuminate",
                "facilitate", "refine", "bolster", "streamline", "revolutionize",
                "innovative", "transformative", "seamless", "scalable", "comprehensive",
                "robust", "stellar", "exceptional", "unparalleled", "dynamic",
                "intricate", "nuanced", "holistic", "paramount", "testament", "tapestry"
            ],
            "uk_strong": [
                "у сучасному світі", "варто зазначити", "важливо підкреслити",
                "зануримося", "розкрити потенціал", "на завершення", "підсумовуючи",
                "комплексне рішення", "все в одному", "інтуїтивний інтерфейс",
                "у кілька кліків", "за кілька хвилин", "все, що вам потрібно",
                "задоволених користувачів", "розкрийте повний потенціал"
            ],
            "it_strong": [
                "nel mondo di oggi", "è importante sottolineare", "vale la pena notare",
                "in conclusione", "soluzione completa", "tutto in uno",
                "interfaccia intuitiva", "in pochi clic", "utenti soddisfatti",
                "sblocca il pieno potenziale", "ottimizza il tuo flusso di lavoro"
            ]
        },
        "scoring_formula": {
            "description": "Evidence combines with diminishing returns. Base = weighted average of measured signals. Then each cliché/structural hit reduces remaining room.",
            "base": "0.40*uniformity + 0.35*repetition + 0.25*dashes (renormalized if any is None)",
            "cliches": "Each strong phrase reduces remaining by 30%, each weak word by 10%",
            "structural": "Each structural hit reduces remaining by 25%",
            "reporting_threshold": "Without at least one concrete marker (cliché or structural), score capped at 0.32"
        },
        "important_notes": [
            "Em dash density IS a real AI signal, not just typography",
            "Short phrases without spaces (single words) are weak signals",
            "Phrases with spaces are strong signals",
            "Statistical signals alone (uniformity, diversity, dashes) without cliché/structural markers are capped at 0.32",
            "Technical code/docstrings are almost never AI-generated",
            "Marketing copy, landing pages, onboarding text are prime AI targets"
        ]
    }


class _PipelineBlock:
    """A block as the agent-scan pipeline described it.

    block_id values are minted per process, so the re-scan inside
    agent-judge cannot produce the ids the agent saw. Where the pipeline
    handed its blocks back, they are reconstructed under their original ids
    so offline spans can be remapped onto them.
    """

    def __init__(self, data: dict):
        self.block_id = data["block_id"]
        self.file_path = data.get("file", "")
        self.line_number = data.get("line", 0)
        self.text = data.get("text", "")
        self.language_hint = data.get("language")
        self.start = 0


class _OriginMatcher:
    """Matches agent output back onto re-scanned blocks.

    block_id values are random per process, so an id from a previous
    agent-scan run can never match the ids minted by the re-scan below.
    Match by origin as well: (file basename, line) plus the wording, which
    travels through the candidates and is stable across runs. Each judgment
    or finding is consumed at most once.
    """

    def __init__(self, judgments_list, agent_findings_list, blocks, blocks_by_id):
        self.judgments_list = judgments_list
        self.agent_findings_list = agent_findings_list
        self.blocks = blocks
        self.blocks_by_id = blocks_by_id
        self.judgments = {j["block_id"]: j
                          for j in judgments_list if "block_id" in j}
        self.used: set = set()

    @staticmethod
    def _norm_text(value: str) -> str:
        return " ".join((value or "").split())

    @staticmethod
    def _as_int(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return -1

    def match_judgment(self, block):
        """The agent's judgment for this block: by id, then file+line+wording,
        then wording alone."""
        found = self.judgments.get(block.block_id)
        if found is not None and id(found) not in self.used:
            self.used.add(id(found))
            return found
        base = os.path.basename(block.file_path)
        block_text = self._norm_text(block.text)
        for j in self.judgments_list:
            if id(j) in self.used:
                continue
            if (os.path.basename(j.get("file", "")) == base
                    and self._as_int(j.get("line")) == block.line_number):
                jt = self._norm_text(j.get("text", ""))
                if not jt or jt == block_text:
                    self.used.add(id(j))
                    return j
        # Wording alone, and deliberately *not* consumed. The first two tiers
        # match a place - an id, or a file and a line - so pairing them one to
        # one is right: two blocks at two places deserve two judgments. This
        # tier matches the passage itself, and a passage that appears on ten
        # pages is one passage. Since the agent is now handed each distinct
        # wording once (see `_agent_candidates_from_pages`), consuming here
        # would give the verdict to the first page and leave the other nine
        # unjudged - which is how deduplication turns into data loss.
        for j in self.judgments_list:
            if self._norm_text(j.get("text", "")) == block_text and block_text:
                return j
        return None

    def hits_for(self, block):
        """Agent's independent findings for this block, with the same
        id-then-origin fallback."""
        direct = self.agent_by_block.get(block.block_id, [])
        if direct:
            return direct
        base = os.path.basename(block.file_path)
        block_text = self._norm_text(block.text)
        out = []
        for af in self.agent_findings_list:
            if (os.path.basename(af.get("file", "")) == base
                    and self._as_int(af.get("line")) == block.line_number):
                at = self._norm_text(af.get("text", ""))
                if not at or at in block_text or block_text in at:
                    out.append(af)
        return out

    @property
    def agent_by_block(self) -> dict:
        index: dict[str, list] = {}
        for af in self.agent_findings_list:
            index.setdefault(af.get("block_id", ""), []).append(af)
        return index

    def find_block(self, entry):
        """The re-scanned block an agent finding refers to."""
        found = self.blocks_by_id.get(entry.get("block_id", ""))
        if found is not None:
            return found
        base = os.path.basename(entry.get("file", ""))
        entry_text = self._norm_text(entry.get("text", ""))
        for b in self.blocks:
            if (os.path.basename(b.file_path) == base
                    and b.line_number == self._as_int(entry.get("line"))):
                bt = self._norm_text(b.text)
                if not entry_text or entry_text in bt or bt in entry_text:
                    return b
        return None


def cmd_agent_scan(args) -> int:
    """Offline scan that outputs candidate blocks for an agent to judge.

    Runs the free offline detector (heuristic + unicode anomalies) and
    outputs every block that scored >= threshold as JSON. The agent
    (opencode, Claude Code, Cursor) reads this, judges each block with
    its own LLM, and pipes the judgments to `xanalyze agent-judge`.

    With --full: also outputs all blocks for the agent to read and judge
    independently (hybrid mode). The agent judges both offline candidates
    AND reads raw blocks to find patterns the offline detector missed.

    No API key, no registration, no network call — the agent IS the judge.
    """
    walked: list = []
    blocks = _agent_blocks(args, walked)

    categories = _categories(args)
    offline = DetectorFactory.create(
        "offline",
        categories=categories if not args.no_unicode else (),
        include_style=True,
    )

    # One candidate per distinct passage. The agent pays for every candidate
    # it is handed, whichever model it runs, so the same header on ten pages
    # was ten times the cost of one answer. `block_id` is a fresh uuid per
    # block, so guarding on it deduplicated nothing at all.
    groups = duplicates.distinct_blocks(blocks)
    representatives = [rep for rep, _ in groups]
    occurrences_by_id = {rep.block_id: rest for rep, rest in groups}
    spans = offline.analyze_blocks(representatives)

    threshold = getattr(args, "threshold", 0.25)
    full_mode = getattr(args, "full", False)
    candidates = []
    seen_blocks = set()
    by_id = {b.block_id: b for b in representatives}
    for span in spans:
        if span.score < threshold:
            continue
        if (span.details or {}).get("error"):
            continue
        block_id = span.block_id
        block = by_id.get(block_id)
        if block is None:
            continue
        if block_id not in seen_blocks:
            seen_blocks.add(block_id)
            places = occurrences_by_id.get(block_id, [block])
            candidates.append({
                "block_id": block_id,
                "file": block.file_path,
                "line": block.line_number,
                "text": block.text,
                # `null` where the passage is too short to read. See
                # `crawler._make_block`: naming a language there is a
                # guess, and the agent would judge on it.
                "language": block.language_hint,
                "offline_score": round(span.score, 3),
                "offline_explanation": span.explanation,
                "offline_details": span.details,
                # Where else this exact passage sits. Context worth having
                # when judging a header, and what `agent-judge` fans the
                # verdict out across.
                "places": [f"{b.file_path}:{b.line_number}" for b in places],
                "occurrences": len(places),
            })

    payload = {
        "candidates": candidates,
        "total_blocks": len(blocks),
        "total_candidates": len(candidates),
        "threshold": threshold,
        "mode": "full" if full_mode else "candidates-only",
        "detection_rules": _agent_detection_rules(),
    }

    if full_mode:
        # Output ALL blocks for the agent to read independently
        all_blocks = []
        for block in blocks:
            all_blocks.append({
                "block_id": block.block_id,
                "file": block.file_path,
                "line": block.line_number,
                "text": block.text,
                # `null` where the passage is too short to read. See
                # `crawler._make_block`: naming a language there is a
                # guess, and the agent would judge on it.
                "language": block.language_hint,
            })
        payload["blocks"] = all_blocks
        payload["instruction"] = (
            "HYBRID MODE: You have two tasks.\n"
            "1. JUDGE CANDIDATES: Evaluate each candidate in 'candidates' using "
            "detection_rules. For each return block_id, score, reason.\n"
            "2. READ BLOCKS: Read every block in 'blocks' independently. Find "
            "AI-generated passages the offline detector MISSED. For each finding "
            "return block_id, quote (verbatim from text), score, reason.\n"
            "Use ALL detection rules: statistical signals, structural patterns, "
            "cliché phrases. Do NOT dismiss dash density as typography.\n"
            "IMPORTANT: Pass the 'blocks' array through unchanged in your output.\n"
            "Output JSON: {\"judgments\": [...], \"agent_findings\": [...], "
            "\"blocks\": [...]}"
        )
    else:
        payload["instruction"] = (
            "You are an AI text judge. Use the detection_rules above to evaluate "
            "each candidate. Consider ALL signals: statistical (uniformity, "
            "repetition, dash density), structural patterns, and cliché phrases. "
            "Do NOT dismiss dash density as 'typography' — it IS an AI signal. "
            "For each candidate return block_id, score (0.0=human, 1.0=AI), "
            "and a one-sentence reason referencing which rules fired. "
            "ALSO echo the candidate's file, line and text fields back: block_id "
            "is minted per run, so those three fields are what lets a judgment "
            "be matched if the scan is re-run in a new process. "
            "Output JSON: [{\"block_id\": \"...\", \"score\": 0.8, "
            "\"reason\": \"...\", \"file\": \"...\", \"line\": 7, "
            "\"text\": \"...\"}]"
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return EXIT_OK


# Agreement labels for the hybrid merge.
AGREE_BOTH = "both"
AGREE_OFFLINE_ONLY = "offline-only"
AGREE_MODEL_ONLY = "model-only"

#: Findings below this score do not reach the report.
_REPORT_THRESHOLD = 0.33


def _load_judgment_input(args):
    """Read and parse the agent's JSON from --judgments or stdin."""
    import_file = getattr(args, "judgments", None)
    if import_file and import_file != "-":
        with open(import_file, encoding="utf-8") as f:
            raw = f.read()
    else:
        raw = sys.stdin.read()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON in input: {exc}", file=sys.stderr)
        return None


def _split_input(input_data, hybrid_flag: bool = False):
    """Split the parsed input into its three parts.

    Simple mode is a bare list of judgments; hybrid mode is a dict carrying
    judgments plus the agent's independent findings and the pipeline blocks.
    """
    hybrid_mode = bool(hybrid_flag)
    judgments_list: list = []
    agent_findings_list: list = []
    pipeline_blocks: list = []

    if isinstance(input_data, dict):
        judgments_list = input_data.get("judgments", [])
        agent_findings_list = input_data.get("agent_findings", [])
        pipeline_blocks = input_data.get("blocks", [])
        if agent_findings_list:
            hybrid_mode = True
    elif isinstance(input_data, list):
        judgments_list = input_data
    return hybrid_mode, judgments_list, agent_findings_list, pipeline_blocks


def _remap_offline_spans(offline_spans, blocks_by_id, pipeline_blocks,
                         blocks):
    """Give offline spans the pipeline's stable block_ids where possible.

    Returns (spans, blocks_by_id): blocks_by_id may gain synthetic
    _PipelineBlock entries for ids the re-scan did not produce.
    """
    if not pipeline_blocks:
        return offline_spans, blocks_by_id

    pipeline_block_map = {}  # (file, line) -> pipeline block_id
    for pb in pipeline_blocks:
        bid = pb.get("block_id", "")
        if bid:
            key = (pb.get("file", ""), pb.get("line", 0))
            pipeline_block_map[key] = bid
            # Also index by block_id for direct lookup
            if bid not in blocks_by_id:
                blocks_by_id[bid] = _PipelineBlock(pb)

    for span in offline_spans:
        block = blocks_by_id.get(span.block_id)
        if block:
            key = (block.file_path, block.line_number)
            if key in pipeline_block_map:
                span.block_id = pipeline_block_map[key]
    return offline_spans, blocks_by_id


def _finding_dict(block, start, end, source, merged_score, explanation,
                  replacement=None, text=None):
    """One row of the final report, shared by both merge paths."""
    return {
        "file": block.file_path,
        "line": block.line_number,
        "offset": block.start + start,
        "end_offset": block.start + end,
        "detector": "agent-llm-judge",
        "source": source,
        "confidence": score_to_confidence(merged_score).value,
        "score": round(merged_score, 3),
        "text": text if text is not None else block.text[start:end],
        "replacement": replacement,
        "explanation": explanation,
    }


def _is_style_span(span) -> bool:
    """A wording finding (not a character finding) the offline pass trusts."""
    return ((span.details or {}).get("source") == "style"
            and span.confidence != Confidence.LOW)


def _overlap(start_a, end_a, start_b, end_b) -> bool:
    return start_a < end_b and start_b < end_a


def _merge_hybrid(offline_spans, matcher: _OriginMatcher) -> list:
    """Offline + agent judgments + agent independent findings.

    Agreement = both found it, offline-only, model-only.
    """
    findings = []
    agent_findings_list = matcher.agent_findings_list

    # Process offline spans
    for span in offline_spans:
        block = matcher.blocks_by_id.get(span.block_id)
        if block is None:
            continue

        # Check if agent also judged this block (via judgments)
        judgment = matcher.match_judgment(block)
        # Check if agent found something independently in this block
        agent_hits = matcher.hits_for(block)

        if _is_style_span(span):
            # Find overlapping agent findings
            overlapping = [af for af in agent_hits
                           if _overlap(span.start, span.end,
                                       af.get("start", 0),
                                       af.get("end", len(block.text)))]

            if judgment is not None or overlapping:
                # Agreement: offline + agent both found it
                agent_score = float(judgment.get("score", 0)) if judgment else 0
                agent_reason = judgment.get("reason", "") if judgment else ""
                for af in overlapping:
                    agent_score = max(agent_score, float(af.get("score", 0)))
                    if af.get("reason"):
                        agent_reason = af["reason"]

                merged_score = max(span.score, agent_score)
                explanation = (
                    f"[{AGREE_BOTH}] agent: {agent_reason} "
                    f"(score={agent_score:.2f}); "
                    f"offline: {span.explanation}"
                )
                source = "agent+offline"
            else:
                # Offline-only
                merged_score = span.score
                explanation = f"[{AGREE_OFFLINE_ONLY}] {span.explanation}"
                source = "offline"
        else:
            # Character findings — keep as-is
            merged_score = span.score
            explanation = span.explanation
            source = (span.details or {}).get("source", "characters")

        if merged_score < _REPORT_THRESHOLD and source != "characters":
            continue

        findings.append(_finding_dict(
            block, span.start, span.end, source, merged_score, explanation,
            replacement=span.replacement))

    # Agent-only findings (not overlapping with any offline span)
    for af in agent_findings_list:
        block = matcher.find_block(af)
        if block is None:
            continue
        af_start = af.get("start", 0)
        af_end = af.get("end", len(block.text))
        already_covered = any(
            s.block_id == block.block_id
            and _overlap(s.start, s.end, af_start, af_end)
            for s in offline_spans)
        if already_covered:
            continue

        agent_score = float(af.get("score", 0))
        if agent_score < _REPORT_THRESHOLD:
            continue

        findings.append(_finding_dict(
            block, af_start, af_end, "agent-only", agent_score,
            f"[{AGREE_MODEL_ONLY}] {af.get('reason', 'Agent detected AI pattern')}"))
    return findings


def _merge_simple(offline_spans, matcher: _OriginMatcher) -> list:
    """Offline pass + agent judgments."""
    findings = []
    for span in offline_spans:
        block = matcher.blocks_by_id.get(span.block_id)
        if block is None:
            continue

        judgment = matcher.match_judgment(block)
        if judgment is not None:
            agent_score = float(judgment.get("score", 0))
            agent_reason = judgment.get("reason", "")
            merged_score = max(span.score, agent_score)
            explanation = (
                f"agent: {agent_reason} (score={agent_score:.2f}); "
                f"offline: {span.explanation}"
            )
            source = "agent+offline"
        else:
            merged_score = span.score
            explanation = span.explanation
            source = (span.details or {}).get("source", "offline")

        if merged_score < _REPORT_THRESHOLD:
            continue

        findings.append(_finding_dict(
            block, span.start, span.end, source, merged_score, explanation,
            replacement=span.replacement))
    return findings


def cmd_agent_judge(args) -> int:
    """Combine offline scan with agent's LLM judgments into a final report.

    Two input modes:

    SIMPLE (default): Reads judgments from --judgments or stdin:
        [{"block_id": "...", "score": 0.8, "reason": "..."}]
        Merges offline scores with agent judgments.

    HYBRID (--hybrid): Reads a dict with both judgments and agent_findings:
        {"judgments": [...], "agent_findings": [...]}
        agent_findings are the agent's independent analysis of raw blocks.
        Merges using hybrid logic: agreement / offline-only / model-only.
    """
    input_data = _load_judgment_input(args)
    if input_data is None:
        return EXIT_ERROR

    hybrid_mode, judgments_list, agent_findings_list, pipeline_blocks = \
        _split_input(input_data, getattr(args, "hybrid", False))

    walked: list = []
    blocks = _agent_blocks(args, walked)
    blocks_by_id = {b.block_id: b for b in blocks}

    categories = _categories(args)
    offline = DetectorFactory.create(
        "offline",
        categories=categories if not args.no_unicode else (),
        include_style=True,
    )
    offline_spans = offline.analyze_blocks(blocks)
    offline_spans, blocks_by_id = _remap_offline_spans(
        offline_spans, blocks_by_id, pipeline_blocks, blocks)

    matcher = _OriginMatcher(judgments_list, agent_findings_list,
                             blocks, blocks_by_id)
    if hybrid_mode:
        findings = _merge_hybrid(offline_spans, matcher)
    else:
        findings = _merge_simple(offline_spans, matcher)

    # Judgments that matched nothing mean the agent's output and this re-scan
    # drifted apart (a file changed, a path moved, ids only). Silent loss here
    # reads as "the agent found nothing", so say how much actually landed.
    unmatched = len(judgments_list) - len(matcher.used)
    if judgments_list and unmatched:
        print(f"# warning: {unmatched} of {len(judgments_list)} judgment(s) "
              f"matched no scanned block; echo file, line and text from "
              f"agent-scan so judgments survive a re-scan",
              file=sys.stderr)

    findings.sort(key=lambda f: (f["file"], f["offset"]))

    if args.json:
        _print_json(findings, walked=walked)
    else:
        _print_human(findings, walked=walked)

    if findings:
        return EXIT_FINDINGS
    return EXIT_OK
