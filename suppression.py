"""Ignoring findings you have already decided about.

Any detector that flags style will be wrong sometimes, and some of what it
gets right will still be wanted: a company whose product genuinely is
"comprehensive" does not need that word underlined on every page forever. A
tool with no way to say "not this one" gets switched off entirely, so the
suppression list is part of the detector, not an afterthought.

Five levels, from the most surgical to the broadest, because they answer
different questions:

* **fingerprint** — "this exact finding, here, is fine." Survives a
  re-scan, and only this one.
* **phrase** — "never flag this word or phrase at all." For house style.
* **rule** — "switch this check off." A signal (`cliches`, `dashes`), a
  character category (`typography`), or an accessibility rule id
  (`link-text-vague`). One namespace on purpose: the user thinks in terms
  of "the check that keeps bothering me", not in terms of which subsystem
  it came from.
* **path** — "not in this file or on this URL." gitignore-style patterns
  and URL globs — generated files, a vendored theme, a staging domain.
* **selector** — "not inside this part of the page." CSS selectors, which
  is also exactly the shape `axe.run({exclude})` takes, so one list drives
  both the text analysis and the accessibility engine rather than two.

Where the list lives:

1. `Settings.ignore` — the user's own, across every project.
2. `.xaudit-ignore` in the scanned folder — the project's own, committed
   alongside the code so a team shares one decision instead of each member
   re-dismissing the same finding.

Both are read; neither overrides the other. That is deliberate: a personal
"I never want this" and a project's "we decided this is fine" are both
true at once, and making one win would silently discard a decision.
"""
from __future__ import annotations

import fnmatch
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import app_identity

#: The file a project keeps its own suppressions in. A project that still
#: has the pre-rename `.xanalyze-ignore` keeps using it: see `ignore_file`.
IGNORE_FILENAME = app_identity.PROJECT_IGNORE_FILE


def ignore_file(folder) -> Path:
    """The ignore file of `folder`, for reading and for writing alike.

    `.xaudit-ignore`, or `.xanalyze-ignore` when only that one exists, so a
    dismissal is added to the file the project already committed instead of
    starting a second one beside it.
    """
    return app_identity.project_ignore_file(Path(folder))

#: A bare line before any section header that is plainly a file pattern: it
#: ends in `/` or carries a glob. The README teaches the file as "gitignore
#: syntax" and its example is a bare list of `vendor/`, `third_party/`,
#: `*.min.js` - which, read as phrases, excluded nothing at all. Narrow on
#: purpose: a phrase somebody writes ("comprehensive", "cutting-edge") has
#: neither, so no existing list changes meaning.
_PATH_SHAPED_RE = re.compile(r"/\s*$|[*?]|^\*\*/")

#: Section headers inside that file. A bare line with no section yet is
#: treated as a phrase, because that is what people write first.
_SECTIONS = {
    "phrases": "phrases",
    "phrase": "phrases",
    "rules": "rules",
    "rule": "rules",
    "paths": "paths",
    "path": "paths",
    "selectors": "selectors",
    "selector": "selectors",
    "fingerprints": "fingerprints",
    "fingerprint": "fingerprints",
}

_SECTION_RE = re.compile(r"^\[(?P<name>[\w-]+)\]\s*$")

#: A `#` only opens a trailing note when whitespace comes before it. Without
#: that guard a CSS id selector (`#main`) or a path containing a hash would be
#: read as an empty value plus a comment, and the entry would silently stop
#: matching anything.
_TRAILING_NOTE_RE = re.compile(r"\s#")

#: Inside `[selectors]` that guard is not enough: `#main` is the commonest CSS
#: selector there is, and `.faq #main` is an ordinary descendant selector. There
#: a note has to be a `#` followed by a space, which is how people write notes
#: anyway. Narrow on purpose - applying it everywhere would turn `#todo` in
#: somebody's existing file from a comment into a phrase.
_SELECTOR_NOTE_RE = re.compile(r"\s#(?=\s|$)")


def _is_note_line(line: str, section: str) -> bool:
    """Whether a line that opens with `#` is a note rather than a value."""
    if not line.startswith("#"):
        return False
    return section != "selectors" or line[1:2] in ("", " ", "\t")


def _split_note(line: str, section: str = "") -> tuple:
    """One line as the value people meant and the note they wrote next to it."""
    pattern = _SELECTOR_NOTE_RE if section == "selectors" else _TRAILING_NOTE_RE
    match = pattern.search(line)
    if not match:
        return line.strip(), ""
    return line[:match.start()].strip(), line[match.start():].strip()


@dataclass
class _Line:
    """One line of the file as it was written.

    Kept so that writing the file back is an edit of a document somebody
    maintains, not a dump of a dataclass. `kind` is `header`, `comment`,
    `blank` or `value`.
    """
    kind: str
    section: str = ""
    value: str = ""
    note: str = ""

    def render(self) -> str:
        if self.kind == "header":
            return f"[{self.section}]"
        if self.kind == "comment":
            return self.note
        if self.kind == "blank":
            return ""
        return f"{self.value}  {self.note}".rstrip() if self.note else self.value


@dataclass
class Suppressions:
    """Everything the user has said they do not want to be told about."""
    phrases: list = field(default_factory=list)
    rules: list = field(default_factory=list)
    paths: list = field(default_factory=list)
    selectors: list = field(default_factory=list)
    fingerprints: list = field(default_factory=list)

    #: The note written next to a value, by value. A fingerprint is a hash,
    #: so without this the list of dismissed findings is a list of hashes and
    #: "un-hide this one" is a blind action.
    labels: dict = field(default_factory=dict)

    #: The file as it was read, line by line. Empty for a list that never came
    #: from a file. See `render`.
    layout: list = field(default_factory=list, repr=False, compare=False)

    def __post_init__(self):
        # Phrases and rules are matched case-insensitively; paths and
        # selectors are not, because file systems and CSS are not.
        self._phrases_lower = {p.strip().lower() for p in self.phrases if p.strip()}
        self._rules = {r.strip() for r in self.rules if r.strip()}
        self._fingerprints = {f.strip() for f in self.fingerprints if f.strip()}

    # ------------------------------------------------------------- loading

    @classmethod
    def from_dict(cls, data: dict | None) -> "Suppressions":
        data = data or {}
        return cls(
            phrases=list(data.get("phrases") or []),
            rules=list(data.get("rules") or []),
            paths=list(data.get("paths") or []),
            selectors=list(data.get("selectors") or []),
            fingerprints=list(data.get("fingerprints") or []),
            labels=dict(data.get("labels") or {}),
        )

    def to_dict(self) -> dict:
        return {
            "phrases": list(self.phrases),
            "rules": list(self.rules),
            "paths": list(self.paths),
            "selectors": list(self.selectors),
            "fingerprints": list(self.fingerprints),
        }

    def as_settings(self) -> dict:
        """`to_dict` plus the notes, for `Settings.ignore`.

        Kept apart from `to_dict` because that one is five parallel lists and
        every caller merges it by extending them; a dict among them would be
        extended into a list of keys.
        """
        data = self.to_dict()
        if self.labels:
            data["labels"] = dict(self.labels)
        return data

    @classmethod
    def parse(cls, text: str) -> "Suppressions":
        """Read the `.xaudit-ignore` format.

        Deliberately the simplest thing that can be edited by hand and read
        in a diff — sections in brackets, one entry per line, `#` comments.
        A config format nobody can read without documentation is a config
        format nobody maintains.
        """
        buckets = {"phrases": [], "rules": [], "paths": [], "selectors": [],
                   "fingerprints": []}
        labels: dict = {}
        layout: list = []
        current = "phrases"
        header_seen = False
        #: Comments and blank lines belong to whatever comes *after* them -
        #: `# generated` is the heading of the group below it, not a trailer
        #: on the group above. Held back until the next line says which
        #: section that is, which matters before the first header, where a
        #: value can be a path while `current` still says phrases.
        pending: list = []

        def flush(section: str) -> None:
            for held in pending:
                held.section = section
                layout.append(held)
            pending.clear()

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                pending.append(_Line("blank"))
                continue
            if _is_note_line(line, current):
                pending.append(_Line("comment", note=line))
                continue
            match = _SECTION_RE.match(line)
            if match:
                current = _SECTIONS.get(match.group("name").lower(), current)
                header_seen = True
                flush(current)
                layout.append(_Line("header", section=current))
                continue
            value, note = _split_note(line, current)
            if not value:
                # A line that is only a note once the `#` is honoured.
                pending.append(_Line("comment", note=note))
                continue
            level = current
            if not header_seen and _PATH_SHAPED_RE.search(value):
                level = "paths"
            flush(level)
            buckets[level].append(value)
            if note:
                labels[value] = note.lstrip("#").strip()
            layout.append(_Line("value", section=level, value=value, note=note))
        flush(current)
        return cls(**buckets, labels=labels, layout=layout)

    @classmethod
    def load(cls, settings=None, root: str | None = None) -> "Suppressions":
        """The user's list and the project's list, merged."""
        merged = {"phrases": [], "rules": [], "paths": [], "selectors": [],
                  "fingerprints": []}
        labels: dict = {}

        def take(other: "Suppressions") -> None:
            for key, values in other.to_dict().items():
                merged[key].extend(values)
            # First note wins: the personal list is read first, and a note
            # somebody typed on their own machine is about their own decision.
            for value, note in other.labels.items():
                labels.setdefault(value, note)

        if settings is not None:
            take(cls.from_dict(getattr(settings, "ignore", None)))

        for path in _ignore_files(root):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            take(cls.parse(text))

        # De-duplicate while keeping the order they were written in, so the
        # settings dialog shows the list back the way the user typed it.
        for key, values in merged.items():
            seen = set()
            merged[key] = [v for v in values if not (v in seen or seen.add(v))]
        return cls(**merged, labels=labels)

    # ------------------------------------------------------------ matching

    def ignores_rule(self, rule_id: str) -> bool:
        return bool(rule_id) and rule_id in self._rules

    def ignores_phrase(self, phrase: str) -> bool:
        return phrase.strip().lower() in self._phrases_lower

    def ignores_fingerprint(self, value: str) -> bool:
        return value in self._fingerprints

    def ignores_path(self, source: str) -> bool:
        """Match a file path or a URL against the path patterns.

        One list handles both because the user is expressing the same thing
        either way — "not this part of the site" — and asking them to keep
        two lists that differ only in whether the string starts with http
        would be a distinction that serves the code, not them.
        """
        if not source or not self.paths:
            return False
        candidates = {source}
        # A path also matches on its tail, so "src/generated/" works without
        # the user having to write out an absolute path.
        posix = source.replace("\\", "/")
        candidates.add(posix)
        candidates.add(Path(posix).name)
        for pattern in self.paths:
            pattern = pattern.strip()
            if not pattern:
                continue
            if pattern.endswith("/"):
                if f"/{pattern.rstrip('/')}/" in f"/{posix}/":
                    return True
                continue
            if any(fnmatch.fnmatch(c, pattern) for c in candidates):
                return True
            if pattern in posix:
                return True
        return False

    def ignores_selector(self, selector: str) -> bool:
        if not selector or not self.selectors:
            return False
        return any(s.strip() and s.strip() in selector for s in self.selectors)

    def is_empty(self) -> bool:
        return not any((self.phrases, self.rules, self.paths, self.selectors,
                        self.fingerprints))

    # --------------------------------------------------------------- writing

    #: The order sections are written in when the file is generated rather
    #: than edited: the most surgical level first, as in the module docstring.
    _SECTION_ORDER = ("fingerprints", "phrases", "rules", "paths", "selectors")

    def render(self) -> str:
        """The inverse of `parse`: back into the section format on disk.

        A list that came from a file is written back **as an edit of that
        file**: every comment, blank line and grouping the author typed stays
        where they put it, removed entries disappear, and new ones are added
        at the end of the section they belong to. This is a file the README
        tells people to commit and review, and the previous version rewrote it
        from the dataclass - so one dismissal in the window deleted every
        reason anybody had written down.
        """
        if not self.layout:
            return self._render_fresh()

        remaining = {name: list(values) for name, values in self._sections()}
        lines: list = []
        #: Where a new entry for each section should be inserted: after the
        #: last line already belonging to that section's block.
        insert_at: dict = {}
        for entry in self.layout:
            if entry.kind == "value":
                values = remaining.get(entry.section, [])
                if entry.value not in values:
                    continue  # removed since the file was read
                values.remove(entry.value)
                note = self.labels.get(entry.value, "")
                lines.append(_Line("value", entry.section, entry.value,
                                   f"# {note}" if note else "").render())
            else:
                # A section always opens on its own: without this, a section
                # whose last line was consumed by an edit would run straight
                # into the next header.
                if (entry.kind == "header" and lines and lines[-1] != ""):
                    lines.append("")
                lines.append(entry.render())
            if entry.kind in ("header", "value"):
                insert_at[entry.section] = len(lines)

        for name in self._SECTION_ORDER:
            new_values = remaining.get(name) or []
            if not new_values:
                continue
            written = [_Line("value", name, value,
                             f"# {self.labels[value]}" if self.labels.get(value) else "").render()
                       for value in new_values]
            at = insert_at.get(name)
            if at is None:
                if lines and lines[-1] != "":
                    lines.append("")
                lines.append(f"[{name}]")
                lines.extend(written)
            else:
                lines[at:at] = written
                # Everything after the insertion point moved down by as much.
                for section, index in insert_at.items():
                    if index > at:
                        insert_at[section] = index + len(written)
                insert_at[name] = at + len(written)

        return "\n".join(lines).rstrip() + "\n" if lines else ""

    def replace_section(self, level: str, text: str) -> None:
        """Replace one level with the lines somebody typed into a box.

        The text is that section written the way a person writes it: values,
        `#` notes and blank lines. Everything outside the level is left
        exactly as it was, which is the whole point - a box for files and
        folders must not be able to delete a rule, and a round trip through
        the dataclass would do precisely that.
        """
        block = Suppressions.parse(f"[{level}]\n{text}")
        old_values = set(getattr(self, level))
        setattr(self, level, list(getattr(block, level)))
        for value in old_values - set(getattr(block, level)):
            self.labels.pop(value, None)
        self.labels.update(block.labels)

        new_lines = [line for line in block.layout if line.kind != "header"]
        for line in new_lines:
            line.section = level
        if self.layout:
            rebuilt: list = []
            at = None
            for line in self.layout:
                if line.section == level and line.kind != "header":
                    continue  # the old contents of this section
                rebuilt.append(line)
                if line.section == level and line.kind == "header":
                    at = len(rebuilt)
            if at is None:
                rebuilt.append(_Line("header", section=level))
                at = len(rebuilt)
            self.layout = rebuilt[:at] + new_lines + rebuilt[at:]
        self.__post_init__()

    def section_text(self, level: str) -> str:
        """One level as the lines a person would edit, notes and all."""
        if not self.layout:
            return "\n".join(
                _Line("value", level, value,
                      f"# {self.labels[value]}" if self.labels.get(value) else "").render()
                for value in getattr(self, level))
        lines = [line.render() for line in self.layout
                 if line.section == level
                 and line.kind in ("value", "comment", "blank")]
        return "\n".join(lines).strip("\n")

    def _sections(self):
        return tuple((name, getattr(self, name)) for name in self._SECTION_ORDER)

    def _render_fresh(self) -> str:
        lines: list = []
        for name, values in self._sections():
            if not values:
                continue
            lines.append(f"[{name}]")
            lines.extend(
                _Line("value", name, value,
                      f"# {self.labels[value]}" if self.labels.get(value) else "").render()
                for value in values
            )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n" if lines else ""


def _ignore_files(root: str | None):
    """The project's ignore file, if the scanned folder has one.

    Only the root of the scan is checked, not every directory: nested
    ignore files would mean a finding's fate depends on which folder the
    scan happened to start from, which is a rule nobody can hold in mind.
    """
    if not root:
        return []
    path = Path(root)
    if path.is_file():
        path = path.parent
    candidate = ignore_file(path)
    return [candidate] if candidate.is_file() else []


# ------------------------------------------------------------- fingerprints

def fingerprint(source: str, text: str, kind: str = "") -> str:
    """A stable id for one finding, so "ignore this one" survives a re-scan.

    Built from the source document, the flagged text and the kind of finding
    — deliberately **not** from character offsets, which shift the moment a
    line is added above and would make every dismissal expire on the next
    edit.
    """
    from privacy import mask_text

    # From the masked text and address: a per-user value would make the same
    # finding a new one on every run (see `privacy`).
    source, text = mask_text(source or ""), mask_text(text or "")
    payload = "␟".join((kind or "", source or "", " ".join((text or "").split())))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def span_fingerprint(span, block) -> str:
    source = getattr(block, "file_path", None) or getattr(block, "page_url", "") or ""
    text = block.text[span.start:span.end]
    kind = (span.details or {}).get("source", span.detector_name)
    return fingerprint(source, text, kind)


def issue_fingerprint(issue) -> str:
    return fingerprint(issue.source, issue.snippet or issue.selector, issue.rule_id)


#: The five levels, in the order the module docstring introduces them: most
#: surgical first. One list so a screen that shows "everything hidden" does
#: not have to keep its own copy of what the levels are.
LEVELS = ("fingerprints", "phrases", "rules", "paths", "selectors")

#: Where an entry lives. Not cosmetic: "put this back" has to remove the line
#: from the list it is actually in, and `Suppressions.load` merges the two
#: into one object that can no longer say which that was.
PERSONAL = "personal"
PROJECT = "project"


@dataclass
class Source:
    """One list of suppressions, and where it is kept.

    `Suppressions.load` answers "is this finding hidden", which is all the
    scan needs. A screen that offers to un-hide something needs the other
    half: which of the two lists the entry is written in, because removing it
    from the wrong one changes nothing and looks like the button is broken.
    """
    kind: str
    entries: "Suppressions"
    path: Path = None

    def remove(self, level: str, value: str) -> bool:
        """Take one entry out. False when it was not in this list."""
        values = getattr(self.entries, level, None)
        if not values or value not in values:
            return False
        values.remove(value)
        self.entries.labels.pop(value, None)
        self.entries.__post_init__()
        return True

    def save(self, settings=None) -> None:
        """Write the list back where it came from."""
        if self.kind == PROJECT and self.path is not None:
            self.path.write_text(self.entries.render(), encoding="utf-8")
            return
        if settings is not None:
            settings.ignore = self.entries.as_settings()
            settings.save()


def sources(settings=None, root: str | None = None) -> list:
    """Both lists, kept apart, in the order they are read.

    The personal list first because it is always there; the project's file
    only when the scanned folder has one.
    """
    found = [Source(kind=PERSONAL,
                    entries=Suppressions.from_dict(getattr(settings, "ignore", None)))]
    for path in _ignore_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        found.append(Source(kind=PROJECT, entries=Suppressions.parse(text), path=path))
    return found


def _short_source(source: str) -> str:
    """The part of a path or URL worth putting in a one-line note."""
    source = (source or "").strip()
    if not source:
        return ""
    if "://" in source:
        return source.split("://", 1)[1].split("?", 1)[0] or source
    return Path(source).name or source


def span_label(span, block) -> str:
    """What a dismissed text finding was, in one readable line.

    The fingerprint is a one-way hash, so this note is the only thing that
    can answer "what am I un-hiding?" - and the window used to answer it with
    sixteen hex characters.
    """
    kind = (span.details or {}).get("source") or span.detector_name
    source = _short_source(getattr(block, "file_path", None)
                           or getattr(block, "page_url", "") or "")
    text = " ".join((block.text[span.start:span.end] or "").split())
    return " · ".join(part for part in (kind, source, _clip(text)) if part)


def issue_label(issue) -> str:
    """The audit counterpart of `span_label`."""
    where = issue.selector or (f"line {issue.line}" if issue.line else "")
    return " · ".join(part for part in (issue.rule_id, _short_source(issue.source),
                                        where) if part)


def _clip(text: str, limit: int = 60) -> str:
    """Short enough to stay one line in a file people read in a diff."""
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "\u2026"


def add_fingerprint_to_ignore_file(root: str, value: str, label: str = "") -> Path:
    """Append one "ignore this exact finding" line to the project's ignore
    file, creating it if it does not exist yet.

    Read-modify-write through `parse`/`render` rather than a raw text append,
    so a fingerprint added next to a file that already has a `[rules]` or
    `[phrases]` section lands in the right one instead of at the end under
    whatever section happened to be last. Idempotent: the same finding
    dismissed twice is still one line.
    """
    path = Path(root)
    if path.is_file():
        path = path.parent
    ignore_path = ignore_file(path)
    existing = (Suppressions.parse(ignore_path.read_text(encoding="utf-8"))
                if ignore_path.is_file() else Suppressions())
    if value not in existing.fingerprints:
        existing.fingerprints.append(value)
    if label:
        # A fingerprint is a one-way hash of the finding, so this note is the
        # only thing that can ever tell the reader what they hid.
        existing.labels[value] = label
    ignore_path.write_text(existing.render(), encoding="utf-8")
    return ignore_path


# ----------------------------------------------------------------- filtering

def filter_spans(spans: list, blocks_by_id: dict, suppressions: Suppressions) -> list:
    """Drop text findings the user has already decided about.

    Phrase suppression is applied *inside* a finding rather than to the
    whole finding: a sentence flagged for three clichés, one of which is
    house style, should still be reported for the other two — but with a
    lower score, because part of the reason for the score just went away.
    """
    if suppressions.is_empty():
        return spans

    kept = []
    for span in spans:
        block = blocks_by_id.get(span.block_id)
        if block is None:
            kept.append(span)
            continue

        source = getattr(block, "file_path", None) or getattr(block, "page_url", "") or ""
        if suppressions.ignores_path(source):
            continue
        if suppressions.ignores_selector(getattr(block, "dom_path", "")):
            continue
        if suppressions.ignores_fingerprint(span_fingerprint(span, block)):
            continue

        details = span.details or {}
        source_kind = details.get("source")
        if source_kind == "characters":
            if suppressions.ignores_rule(details.get("category", "")):
                continue
        elif source_kind == "style":
            span = _apply_style_suppressions(span, suppressions)
            if span is None:
                continue
        kept.append(span)
    return kept


def _apply_style_suppressions(span, suppressions: Suppressions):
    """Remove suppressed signals from a style finding and re-score it.

    Returns None when nothing is left to say. Re-scoring rather than
    dropping matters: leaving the original score after removing the reason
    for it would show a "high confidence" finding whose explanation no
    longer contains anything.
    """
    from models import score_to_confidence

    details = dict(span.details or {})
    original_cliches = list(details.get("cliches") or [])
    original_structural = list(details.get("structural") or [])
    signals = dict(details.get("signals") or {})

    cliches = [c for c in original_cliches if not suppressions.ignores_phrase(c)]
    structural = original_structural if not suppressions.ignores_rule("structural") else []
    for signal in list(signals):
        if suppressions.ignores_rule(signal):
            signals[signal] = 0.0

    removed = (len(original_cliches) - len(cliches)) > 0 \
        or len(structural) != len(original_structural) \
        or signals != (details.get("signals") or {})
    if not removed:
        return span

    # Scored by the detector's own function rather than by a copy of its
    # formula. The copy had already drifted once: it still averaged in a
    # missing signal as zero after the detector had learned to leave one out,
    # and it still weighed a phrase the same as a single word.
    from detectors.heuristic import combine_score

    score = combine_score(
        uniformity=signals.get("uniformity"),
        repetition=signals.get("repetition"),
        dashes=signals.get("dashes"),
        structural=bool(structural),
        cliches=cliches,
    )

    if not cliches and not structural and score < 0.33:
        return None

    details["cliches"] = cliches
    details["structural"] = structural
    details["signals"] = signals
    details["suppressed"] = True

    from dataclasses import replace
    return replace(span, score=score, confidence=score_to_confidence(score),
                   details=details)


def suppressed_by(issue, suppressions: Suppressions):
    """`(level, value)` of the entry that hides `issue`, or None.

    Checked in the order `filter_issues` always applied them, so the entry
    named is the one that actually did the hiding.
    """
    if suppressions.ignores_rule(issue.rule_id):
        return "rules", issue.rule_id
    if suppressions.ignores_path(issue.source):
        return "paths", issue.source
    if suppressions.ignores_selector(issue.selector):
        return "selectors", issue.selector
    value = issue_fingerprint(issue)
    if suppressions.ignores_fingerprint(value):
        return "fingerprints", value
    return None


def filter_issues(issues: list, suppressions: Suppressions) -> list:
    """Drop accessibility findings the user has already decided about."""
    if suppressions.is_empty():
        return issues
    return [issue for issue in issues if suppressed_by(issue, suppressions) is None]


#: How many dismissed findings a summary names one by one.
_ACCOUNT_LIMIT = 25


def account_for_suppressed(issues, suppressions: Suppressions) -> dict:
    """What the ignore lists hid from these findings, and why (T-1963).

    A hidden finding is a decision somebody made, and a report that drops it
    without a word reads exactly like a clean one. So the count is kept, by
    level and by rule, and each dismissed finding is named with the reason
    written next to it - the note in `.xaudit-ignore`, which for a
    fingerprint is the only human-readable trace of what was hidden.
    """
    account = {"hidden": 0, "by_level": {}, "by_rule": {}, "dismissed": []}
    if suppressions.is_empty():
        return account
    for issue in issues:
        found = suppressed_by(issue, suppressions)
        if found is None:
            continue
        level, value = found
        account["hidden"] += 1
        account["by_level"][level] = account["by_level"].get(level, 0) + 1
        account["by_rule"][issue.rule_id] = account["by_rule"].get(issue.rule_id, 0) + 1
        if level == "fingerprints" and len(account["dismissed"]) < _ACCOUNT_LIMIT:
            account["dismissed"].append({
                "rule": issue.rule_id, "source": issue.source,
                "fingerprint": value,
                "reason": suppressions.labels.get(value, ""),
            })
    return account


#: Everything that can go in the `[rules]` section, for the settings UI to
#: offer as a list rather than making the user guess the spelling.
def known_rule_ids() -> dict:
    from unicode_rules import ALL_CATEGORIES

    ids = {
        "style": ["uniformity", "repetition", "dashes", "structural", "cliches"],
        "characters": list(ALL_CATEGORIES),
    }
    try:
        import audit
        ids["accessibility"] = audit.RuleRegistry.available()
    except Exception:  # noqa: BLE001 - the a11y package is optional at import time
        ids["accessibility"] = []
    return ids
