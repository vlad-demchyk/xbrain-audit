"""Source glyphs and DOM positions survive static and native text extraction."""
import json
import os
from pathlib import Path

import pytest

from crawler import page_from_html
from detectors.offline import OfflineDetector
from finding_contract import serialize_span
from models import Confidence, TextSpan
from text_extraction import normalize_with_map, normalized_range_to_raw


@pytest.mark.parametrize("raw,normal", [(" a\t\n b ", "a b"), ("a\u00a0b", "a b"),
                                       ("🙂 a  b", "🙂 a b"), ("e\u0301\u00a0x", "e\u0301 x")])
def test_normalization_is_a_separate_view_with_exact_reverse_coordinates(raw, normal):
    text, mapping = normalize_with_map(raw)
    assert text == normal
    for token in normal.split():
        start = normal.index(token)
        low, high = normalized_range_to_raw(mapping, start, start + len(token))
        assert raw[low:high] == token
    if " " in normal:
        start = normal.index(" ")
        low, high = normalized_range_to_raw(mapping, start, start + 1)
        assert raw[low:high].isspace()


@pytest.mark.parametrize("start,end", [(True, 2), (0, False), (-1, 3), (3, 3), (3, 2), (0, 100)])
def test_invalid_normalized_ranges_are_not_guessed(start, end):
    _, mapping = normalize_with_map("hello world")
    with pytest.raises(ValueError):
        normalized_range_to_raw(mapping, start, end)


@pytest.mark.parametrize("attribute", ["hidden", "style='display:none'", "style='visibility:hidden'",
                                       "style='opacity:0'", "style='content-visibility:hidden'"])
def test_known_hidden_text_is_excluded_including_ancestor_styles(attribute):
    markup = f'<div {attribute}><p>Hidden text with enough words to analyse.</p></div><p>Visible words to read on this page.</p>'
    page = page_from_html(markup, "fixture://hidden")
    assert all("Hidden text" not in b.text for b in page.blocks)
    assert any("Visible words" in b.text for b in page.blocks)


def test_aria_hidden_is_not_claimed_to_hide_visible_pixels():
    page = page_from_html('<p aria-hidden="true">Visible text excluded from accessibility.</p>', "fixture://aria")
    assert page.blocks and page.blocks[0].visibility == "unknown"


def test_child_visibility_override_and_hidden_child_are_handled_separately():
    page = page_from_html('<div style="visibility:hidden"><p style="visibility:visible">This child is explicitly visible.</p></div>'
                          '<p>Prefix <span hidden>hidden words</span> visible suffix.</p>', "fixture://styles")
    texts = [b.text for b in page.blocks]
    assert "This child is explicitly visible." in texts
    assert any("Prefix" in text and "hidden words" not in text for text in texts)


def test_nbsp_survives_the_character_pass_and_json_with_exact_dom_position():
    page = page_from_html('<p>Hello&nbsp;world with enough copy to read.</p>', "fixture://nbsp")
    block = page.blocks[0]
    assert block.text == block.raw_text and "\u00a0" in block.text
    assert "\u00a0" not in block.normalized_text
    spans = [s for s in OfflineDetector().analyze_blocks(page.blocks) if block.text[s.start:s.end] == "\u00a0"]
    assert spans
    record = json.loads(json.dumps(serialize_span(spans[0], block)))
    assert record["text"] == "\u00a0"
    assert record["dom_ranges"][0]["start"] == 5
    assert record["dom_ranges"][0]["end"] == 6
    assert record["dom_ranges"][0]["unit"] == "utf-16"


def test_short_controls_keep_raw_characters_without_claiming_a_style_judgment():
    page = page_from_html('<button>Save&nbsp;file</button>', "fixture://short")
    block = page.blocks[0]
    assert not block.analysis_eligible
    spans = OfflineDetector().analyze_blocks(page.blocks)
    assert any(block.text[s.start:s.end] == "\u00a0" for s in spans)
    assert all(s.details["source"] == "characters" for s in spans)


def test_utf16_ranges_include_astral_characters_and_real_text_node_indices():
    page = page_from_html('<p>🙂 Prefix<!--comment--> with&nbsp;enough copy to read.</p>', "fixture://utf16")
    block = page.blocks[0]
    index = block.text.index("\u00a0")
    span = TextSpan(block.block_id, index, index + 1, 1, Confidence.HIGH, "test")
    record = serialize_span(span, block)
    # NBSP belongs to the second text node, after a comment node.
    assert record["dom_ranges"][0]["node_index"] == 2
    assert record["dom_ranges"][0]["start"] == len(" with")
    emoji = TextSpan(block.block_id, 0, 1, 1, Confidence.HIGH, "test")
    assert serialize_span(emoji, block)["dom_ranges"][0]["end"] == 2


def test_nested_language_is_kept_per_source_segment():
    page = page_from_html('<p lang="en">An English prefix <span lang="it">con parole italiane</span> and suffix.</p>', "fixture://lang")
    block = page.blocks[0]
    assert block.declared_language == "mixed"
    assert {r["language"] for r in block.language_context} == {"en", "it"}


def test_attributes_are_explicit_sources_and_never_password_values():
    page = page_from_html('<input type="password" value="private-value" placeholder="Enter&nbsp;password" aria-label="Password">', "fixture://attributes")
    assert {b.attribute_name for b in page.blocks} == {"placeholder", "aria-label"}
    assert all("private-value" not in b.text for b in page.blocks)
    assert all(b.text_kind == "attribute" for b in page.blocks)


def test_hidden_aria_reference_is_a_declared_label_source_not_visible_body_copy():
    page = page_from_html('<span id="label" hidden>Hidden accessible label text.</span><button aria-labelledby="label"></button>', "fixture://refs")
    assert len(page.blocks) == 1
    block = page.blocks[0]
    assert block.text_kind == "referenced-label" and block.attribute_name == "aria-labelledby"
    assert block.visibility == "unknown"


@pytest.mark.parametrize("platform", ["cms", "spa", "wordpress", "spfx"])
def test_platform_fixtures_keep_known_unicode_spans_to_json(platform):
    root = Path(__file__).parent / "fixtures" / "text_extraction"
    page = page_from_html((root / f"{platform}.html").read_text(encoding="utf-8"), f"fixture://{platform}")
    blocks = {b.block_id: b for b in page.blocks}
    records = [serialize_span(s, blocks[s.block_id]) for s in OfflineDetector().analyze_blocks(page.blocks)]
    assert any(r["text"] == "\u00a0" for r in json.loads(json.dumps(records)))
    assert not any("EXCLUDED-HIDDEN" in b.text for b in page.blocks)


def test_real_browser_snapshot_reads_shadow_frames_css_and_scoped_copy(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from audit import driver
    if not driver.available()[0]:
        pytest.skip("QtWebEngine unavailable")
    path = tmp_path / "native.html"
    path.write_text('''<!doctype html><html lang="en"><head><meta charset="utf-8"><style>.hide{display:none}</style></head><body>
      <p class="hide">EXCLUDED-HIDDEN CSS copy with enough text.</p>
      <p>Ordinary visible copy with enough words to read.</p>
      <section id="scope"><p>Scoped visible copy&nbsp;with enough text to read.</p><div id="host"></div>
      <iframe srcdoc="<p lang='it'>Testo nel frame con abbastanza parole da leggere.</p>"></iframe></section>
      <script>document.querySelector('#host').attachShadow({mode:'open'}).innerHTML='<p>Shadow copy with enough words to read.</p>';</script>
    </body></html>''')
    with driver.html_renderer(settle_ms=50, allow_local_files=True, within="#scope") as render:
        rendered = render(path.as_uri())
    page = page_from_html(rendered, path.as_uri())
    assert page.diagnostics.extraction["mode"] == "rendered"
    assert not any("Ordinary" in b.text or "EXCLUDED-HIDDEN" in b.text for b in page.blocks)
    assert any("Shadow copy" in b.text and b.context_path[0]["type"] == "shadow" for b in page.blocks)
    frame = next(b for b in page.blocks if "Testo nel frame" in b.text)
    assert frame.context_path[0]["type"] == "frame" and frame.declared_language == "it"
    assert all(b.visibility == "visible" for b in page.blocks)
    assert page.diagnostics.extraction["closed_shadow_roots"] == "unknown"


def test_exact_dedup_and_cache_do_not_reuse_character_ranges_across_whitespace(tmp_path):
    from duplicates import distinct_blocks
    from judgment_cache import JudgmentCache
    a = page_from_html('<p>Read&nbsp;the documentation with enough copy.</p>', "fixture://a").blocks[0]
    b = page_from_html('<p>Read the documentation with enough copy.</p>', "fixture://b").blocks[0]
    assert len(distinct_blocks([a, b], exact_text=True)) == 2
    cache = JudgmentCache("test", directory=tmp_path, exact_text=True)
    cache.put(a.text, [])
    cache.put(b.text, [])
    assert len(cache) == 2


def test_a_script_preparation_error_finishes_the_browser_probe(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from audit import driver, browser
    if not driver.available()[0]:
        pytest.skip("QtWebEngine unavailable")
    path = tmp_path / "simple.html"
    path.write_text("<p>Some text with enough words to read.</p>")
    driver.ensure_headless_application()
    options = browser.BrowserAuditOptions(run_axe=False, run_htmlcs=False,
        run_measurements=False, run_states=False, capture_text=True,
        allow_local_files=True, settle_ms=0)
    def fail(*args):
        raise ValueError("fixture preparation failure")
    monkeypatch.setattr(driver, "_js", fail)
    runner = driver.BrowserAuditRunner(options)
    try:
        result = runner.audit(path.as_uri())
    finally:
        runner.close()
    assert "fixture preparation failure" in result.engine_errors["text"]
