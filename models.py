"""Shared data structures used across the crawler, detectors and UI."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Confidence(str, Enum):
    """Discrete confidence buckets used for highlighting."""
    LOW = "low"          # weak / inconclusive signal
    MEDIUM = "medium"    # moderate signal
    HIGH = "high"        # strong signal


@dataclass
class TextBlock:
    """A single extracted chunk of visible text from a page.

    `dom_path` is a best-effort CSS-like path so a block can be traced back
    to where it came from on the page (used for the bottom list and for a
    future "write back to source" feature).
    """
    block_id: str
    page_url: str
    dom_path: str
    text: str
    language_hint: str | None = None  # 'uk' | 'it' | 'en' | None if unknown
    #: Where this passage is *written*, when a checkout was paired with the
    #: site (`repo_pairing`). A page tells a reader where to look and never
    #: where to edit; these two fields are that second answer. Empty when no
    #: repository was given, and empty for a passage the given one does not
    #: contain - which is a real answer about that checkout, not a failure.
    source_file: str = ""
    source_line: int | None = None
    source_mapping: str = ""
    source_candidates: list = field(default_factory=list)
    source_context: dict = field(default_factory=dict)
    #: `text` retains the decoded source characters. Normalisation is a
    #: separate view with a reversible offset map, never a destructive read.
    raw_text: str | None = None
    normalized_text: str | None = None
    normalization_map: list = field(default_factory=list)
    rendered_visible_text: str | None = None
    visibility: str = "unknown"
    text_kind: str = "dom-text"
    attribute_name: str = ""
    dom_ranges: list = field(default_factory=list)
    declared_language: str | None = None
    language_context: list = field(default_factory=list)
    context_path: list = field(default_factory=list)
    analysis_eligible: bool = True


@dataclass
class TextSpan:
    """A detection result for a slice of a TextBlock's text.

    start/end are character offsets into TextBlock.text (Python slice
    semantics: text[start:end]).
    """
    block_id: str
    start: int
    end: int
    score: float               # 0.0 (human-like) .. 1.0 (AI-like), detector-specific
    confidence: Confidence
    detector_name: str
    explanation: str = ""
    # Set by detectors that know the exact correction (the non-keyboard
    # character pass). Carrying it here matters: the fix depends on
    # surrounding context — which alphabet the rest of the word uses — so
    # recomputing it later from the span text alone would silently produce
    # a no-op for homoglyphs.
    replacement: str | None = None
    # Structured record of *why* this span was flagged: which signals fired
    # and at what strength, which cliché phrases matched, which character
    # category was hit. Kept as data rather than as prose because the
    # explanation shown to the user is rendered in the UI language, which
    # can change after a scan — a pre-formatted sentence would then be
    # stuck in the language that was selected when the scan ran.
    # See `explanations.render()` for the keys each detector sets.
    details: dict = field(default_factory=dict)


@dataclass
class PageDiagnostics:
    """What the crawler actually received, and what happened to it.

    This exists because "0 flagged passages" is ambiguous in the worst way:
    it looks identical whether the page is clean, whether the page renders
    its text in the browser and arrived as an empty shell, whether the
    server answered with a bot-check, or whether every paragraph on it was
    just under the minimum length. Recording the counts and the markers at
    fetch time is the only place the difference is still visible — by the
    time the UI has a span list, the evidence is gone.

    `reasons` holds machine-readable codes (see `crawler.EMPTY_*`), which
    the UI renders as sentences in the user's language.
    """
    status_code: int | None = None
    content_type: str = ""
    final_url: str = ""          # after redirects; differs -> worth showing
    html_bytes: int = 0
    text_ratio: float = 0.0      # visible text vs markup; ~0 on an app shell
    candidates_found: int = 0    # elements that could have held copy
    blocks_kept: int = 0
    dropped_too_short: int = 0
    dropped_duplicate: int = 0
    js_framework: str = ""       # "react" / "next" / "vue" / ... when detected
    #: Why the browser could not render this page, when one was asked to. The
    #: fetched reading still stands, so this is a note on the result rather
    #: than an error that replaces it.
    render_error: str = ""
    extraction: dict = field(default_factory=dict)
    has_noscript_notice: bool = False
    #: The response headers, lower-cased keys. Kept because they arrived
    #: with the page and were being thrown away: everything except
    #: `Content-Type` died with the response object, so the audit had ten
    #: security rules and none of them about how the page is served.
    headers: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


@dataclass
class LinkRef:
    """One anchor, read once and reused.

    The crawl already parses every page to find where to go next, and the
    crawlability pass needs the same anchors to say which internal link
    reached a failure. Reading the markup a second time for the same list is
    the cost this record removes; carrying the anchor markup along with the
    address is what lets the second reader keep the evidence the first one
    threw away.
    """
    #: The `href` exactly as authored, for a report that quotes the page.
    href: str
    #: Absolute and normalised the way the crawl compares addresses.
    url: str
    #: The anchor element, truncated, so a finding can show what it read.
    snippet: str = ""


@dataclass
class PageResult:
    url: str
    depth: int
    blocks: list[TextBlock] = field(default_factory=list)
    error: str | None = None
    raw_html: str | None = None  # kept so the UI can render a graphical preview
    diagnostics: PageDiagnostics = field(default_factory=PageDiagnostics)
    #: Anchors found on this page, or `None` when nobody looked.
    #:
    #: The distinction is the point: an empty list means the markup was read
    #: and holds no links, while `None` means this result came from a
    #: producer that does not extract them. A reader that treats the two as
    #: the same thing either re-parses pages that were already read, or
    #: silently reports nothing for a page that genuinely has no anchors.
    links: list[LinkRef] | None = None


@dataclass
class CrawlDiagnostics:
    """What the crawl reached, and what it did not.

    The web counterpart of `ScanDiagnostics`, and it exists for the same
    reason: a clean result over pages nobody read is not a clean result. The
    walk stops at `limit` and the queue it stops on leaves no trace - by the
    time a caller holds a list of `PageResult`, the addresses that were
    found and never fetched are gone, and "30 pages, no findings" reads as a
    verdict on the site rather than on the thirty.
    """
    #: Pages actually read as HTML. Not every fetch: an address that turns
    #: out to be a `.jpg` or a `.pdf` is recorded as a result too, and
    #: counting those here made a crawl of 225 pages plus 25 uploads report
    #: itself as 250 pages read.
    pages_read: int = 0
    #: The ceiling this crawl ran under; 0 means there was none.
    limit: int = 0
    #: Addresses found and still queued when the walk stopped. A lower
    #: bound on what was missed, not a total: the pages never fetched would
    #: have contributed links of their own.
    queued_when_stopped: int = 0
    #: Addresses found and not read because they lie outside `site_scope`
    #: (one SharePoint host serves every site of a tenant). Counted, not
    #: listed: they are not this run's pages, only proof the scope held.
    out_of_scope: int = 0

    @property
    def truncated(self) -> bool:
        return self.queued_when_stopped > 0

    @property
    def at_least(self) -> int:
        """Pages the crawl knew about: read, plus still queued."""
        return self.pages_read + self.queued_when_stopped


@dataclass
class AnalysisResult:
    root_url: str
    pages: list[PageResult] = field(default_factory=list)
    spans: list[TextSpan] = field(default_factory=list)
    #: How the crawl went as a whole, as opposed to page by page.
    crawl: CrawlDiagnostics = field(default_factory=CrawlDiagnostics)

    def blocks(self) -> list[TextBlock]:
        out: list[TextBlock] = []
        for p in self.pages:
            out.extend(p.blocks)
        return out

    def spans_for_block(self, block_id: str) -> list[TextSpan]:
        return [s for s in self.spans if s.block_id == block_id]


def score_to_confidence(score: float) -> Confidence:
    if score >= 0.66:
        return Confidence.HIGH
    if score >= 0.33:
        return Confidence.MEDIUM
    return Confidence.LOW


# --------------------------------------------------------------------------
# Repository / local-folder scan mode.
#
# CodeBlock deliberately exposes the same `block_id` / `text` / `language_hint`
# attributes as TextBlock, so every existing Detector implementation (which
# only ever reads those) works against it unmodified — the abstract factory
# doesn't need to know whether a block came from a live web page or a file
# on disk. What's different is `file_path`/`start`/`end`/`line_number`,
# which exist so a flagged passage can be written straight back into the
# source file it came from.
# --------------------------------------------------------------------------

#: What kind of text a CodeBlock holds. Kept on the block because the three
#: read very differently and must not be judged, or rewritten, alike:
#:
#:   markup    — text between tags: <h1>Welcome back</h1>. Ships to the user.
#:   injected  — a string literal that becomes visible copy without ever
#:               sitting between tags: a placeholder="" attribute, a
#:               `.textContent =` assignment, a t("...") translation call.
#:               Ships to the user too, which is exactly why it belongs in
#:               the same scan as markup.
#:   technical — comments and docstrings. Never reaches the user, so it is
#:               off by default; but it is where an assistant's writing shows
#:               up most, which is why it can be scanned deliberately.
KIND_MARKUP = "markup"
KIND_INJECTED = "injected"
KIND_TECHNICAL = "technical"


@dataclass
class CodeBlock:
    block_id: str
    file_path: str
    start: int              # char offset into the file's raw text
    end: int                # file_content[start:end] == text, always
    text: str
    line_number: int
    language_hint: str | None = None
    kind: str = KIND_MARKUP
    source_context: dict = field(default_factory=dict)


@dataclass
class FileResult:
    path: str
    blocks: list[CodeBlock] = field(default_factory=list)
    error: str | None = None
    raw_text: str | None = None


@dataclass
class ScanDiagnostics:
    """What the walk actually opened, and what happened to it.

    The repository counterpart of `PageDiagnostics`, and it exists for the
    same reason: "no findings" is ambiguous in the worst way. A run that read
    161 files and scored none of them above the threshold, and a run that
    matched no files at all, produced the same `No findings.` and the same
    `{"total": 0, "files": 0}` - because `counts.files` counts files *among
    the findings*. Measured on real projects: `xformat-backend` reads 161
    files and 202 blocks and reports neither number anywhere.

    Recorded during the walk rather than derived afterwards: by the time a
    caller holds a list of `FileResult`, the files that were never opened
    have left no trace to count.
    """
    #: Files whose extension matched and which the walk actually opened.
    files_read: int = 0
    #: Files skipped by an ignore pattern, and by which kind of pattern -
    #: a user's own exclusion is a different fact from a built-in default.
    skipped_ignored: int = 0
    skipped_too_large: int = 0
    unreadable: int = 0
    blocks_found: int = 0
    #: True when the walk stopped early on `ScanConfig.max_files`. The one
    #: fact that must never be silent: everything past the cap is unexamined,
    #: and a result that does not say so claims to have looked at a whole
    #: repository when it looked at part of one.
    truncated: bool = False
    #: The cap that did the truncating, so the message can name it.
    limit: int = 0

    @property
    def complete(self) -> bool:
        return not self.truncated


@dataclass
class RepoAnalysisResult:
    root_dir: str
    files: list[FileResult] = field(default_factory=list)
    spans: list[TextSpan] = field(default_factory=list)
    #: What the walk saw. Default-constructed so every existing caller keeps
    #: working and simply reports zeroes until it fills this in.
    diagnostics: "ScanDiagnostics" = field(default_factory=lambda: ScanDiagnostics())

    def blocks(self) -> list[CodeBlock]:
        out: list[CodeBlock] = []
        for f in self.files:
            out.extend(f.blocks)
        return out
