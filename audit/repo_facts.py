"""What a repository reveals about itself, as opposed to what its pages do.

Three different questions live here, and they share a module because they
share a method: none of them judges anything. Each reads a fact that is
either present or absent, the way `unicode_rules` reads a zero-width
character and `audit/rules/provenance.py` reads a vendor class name.

**Who wrote it.** A commit trailer naming an assistant is a record, not an
inference. Every classifier in this tool is guessing at whether a model
wrote a passage; the repository has been keeping the answer in plain text
the whole time. It is reported as provenance, not as a problem: writing code
with an assistant is not a defect, and the tool that says otherwise is
telling people how to work.

**What the assistants left behind.** `CLAUDE.md`, `.cursor/`, a Copilot
instructions file: committed configuration for tools that wrote here.
Interesting for the same reason, and for one more - these files often carry
project context somebody did not mean to publish.

**What is about to leak.** A `.env` that no ignore rule covers is a
credential waiting for the next `git add .`, and one that is already tracked
is a credential that has been published and needs rotating, not deleting.
Those are different findings with different fixes, and telling them apart
needs git rather than the filesystem - so it asks git, and says so when it
cannot.

Everything here degrades to silence rather than to a guess. A folder that is
not a git repository produces no commit findings at all, because "no
assistant commits found" and "no history to look at" are opposite statements
and only one of them is true.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

#: Trailers and phrases that name an assistant as an author. Matched against
#: the whole commit message, case-insensitively. Each is something a tool
#: writes about itself, not a word a person might use in passing: "claude"
#: alone would match "reviewed with claude's suggestion in mind", which is a
#: sentence about a person's process and nobody else's business.
_ASSISTANT_MARKS = (
    r"co-authored-by:\s*claude",
    r"co-authored-by:.*\bcopilot\b",
    r"co-authored-by:.*\bcursor\b",
    r"co-authored-by:.*\baider\b",
    r"co-authored-by:.*\bdevin\b",
    r"generated with \[?claude",
    r"generated with \[?github copilot",
    r"🤖 generated with",
)
_ASSISTANT_RE = re.compile("|".join(_ASSISTANT_MARKS), re.I)

#: Files and folders an assistant leaves in a project. Paths relative to the
#: repository root, matched exactly for files and as a prefix for folders.
_TOOL_ARTIFACTS = (
    "CLAUDE.md", "AGENTS.md", ".claude/", ".cursor/", ".cursorrules",
    ".github/copilot-instructions.md", ".aider.chat.history.md",
    ".aider.input.history", ".continue/", ".windsurfrules", ".codeium/",
)

#: Files that carry credentials. `.env.example` and friends are the
#: convention for *not* carrying them, so they are excluded by name rather
#: than by guessing at contents.
_ENV_RE = re.compile(r"(^|/)\.env(\.|$)", re.I)
_ENV_SAFE_SUFFIXES = (".example", ".sample", ".template", ".dist")

#: How many commits back to read. Enough to describe a project's habits,
#: bounded so a repository with a decade of history does not turn a scan
#: into a `git log` of the whole thing.
_COMMITS_READ = 500

#: Seconds any one git call may take. A repository on a slow disk, or one
#: git decides to garbage-collect mid-scan, must not hang a run.
_GIT_TIMEOUT = 20


@dataclass
class RepoFacts:
    """What the walk established, including what it could not."""
    is_git: bool = False
    commits_read: int = 0
    assistant_commits: list = field(default_factory=list)
    tool_artifacts: list = field(default_factory=list)
    exposed_env: list = field(default_factory=list)
    tracked_env: list = field(default_factory=list)
    #: Why git was not consulted, when it was not. Empty when it was.
    git_unavailable: str = ""
    #: Findings `blame_issues` could place on a line, and how many of those
    #: sit on a line an assistant commit last touched. Both, because the
    #: second is meaningless without the first: two out of two and two out of
    #: four hundred are the same numerator.
    blamed_total: int = 0
    blamed_assistant: int = 0


def _git(root: Path, *args: str) -> str | None:
    """Run one git command in `root`. None when git could not answer.

    Never raises: a missing git, a folder that is not a repository, a
    timeout and a non-zero exit are all the same answer here - we do not
    know - and each of them must leave the rest of the scan running.
    """
    try:
        done = subprocess.run(("git", "-C", str(root)) + args,
                              capture_output=True, text=True,
                              # git writes paths and messages as UTF-8; the
                              # Windows locale default (cp1252) crashed the
                              # reader thread on the first non-ASCII byte.
                              encoding="utf-8", errors="replace",
                              timeout=_GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _git_status(root: Path, *args: str) -> int | None:
    """The exit code of one git command, or None when git did not run.

    `_git` folds every non-zero exit into "we do not know", and for most
    commands that is right. It is wrong for the one command whose *exit
    code is the answer*: `git check-ignore` exits 1 to say "not ignored"
    and 128 to say "I could not look", and treating those the same is how
    a busy repository turns into a security finding.
    """
    try:
        done = subprocess.run(("git", "-C", str(root)) + args,
                              capture_output=True, text=True,
                              # git writes paths and messages as UTF-8; the
                              # Windows locale default (cp1252) crashed the
                              # reader thread on the first non-ASCII byte.
                              encoding="utf-8", errors="replace",
                              timeout=_GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.returncode


def _is_env_file(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1].lower()
    if not _ENV_RE.search("/" + rel.lower()):
        return False
    return not name.endswith(_ENV_SAFE_SUFFIXES)


def read_facts(root, config=None) -> RepoFacts:
    """Everything this module can establish about `root`."""
    from repo_scanner import ScanConfig, build_matcher, iter_unignored_paths

    root = Path(root)
    config = config or ScanConfig()
    facts = RepoFacts()
    if not root.is_dir():
        return facts

    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    facts.is_git = bool(inside and inside.strip() == "true")
    if not facts.is_git:
        facts.git_unavailable = "not a git repository"

    # -- who wrote it
    if facts.is_git:
        log = _git(root, "log", f"-{_COMMITS_READ}", "--format=%H%x1f%s%x1f%b%x1e")
        if log is None:
            facts.git_unavailable = "git could not read this repository's log"
        else:
            for record in log.split("\x1e"):
                record = record.strip("\n")
                if not record:
                    continue
                parts = record.split("\x1f")
                if len(parts) < 3:
                    continue
                facts.commits_read += 1
                sha, subject, body = parts[0], parts[1], parts[2]
                if _ASSISTANT_RE.search(f"{subject}\n{body}"):
                    facts.assistant_commits.append((sha[:12], subject))

    # -- what the assistants left behind, and what is about to leak
    matcher = build_matcher(config.ignore_patterns)
    tracked = None
    if facts.is_git:
        listing = _git(root, "ls-files", "-z")
        if listing is not None:
            tracked = {name for name in listing.split("\0") if name}

    for artifact in _TOOL_ARTIFACTS:
        path = root / artifact.rstrip("/")
        if path.exists():
            facts.tool_artifacts.append(artifact)

    for path in iter_unignored_paths(root, matcher):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if not _is_env_file(rel):
            continue
        # An ignored `.env` is the normal, correct arrangement and not a
        # finding. This is the whole check: the danger is the one nothing
        # covers.
        if _git_ignores(root, rel, facts):
            continue
        if tracked is not None and rel in tracked:
            facts.tracked_env.append(rel)
        else:
            facts.exposed_env.append(rel)
    return facts


def _git_ignores(root: Path, rel: str, facts: RepoFacts) -> bool:
    """Does the repository's own `.gitignore` cover this path?

    Asked of git rather than parsed here, because git is the authority on
    its own ignore rules and a second implementation of them would
    eventually disagree - and disagreeing in the safe direction means
    staying quiet about a credential.

    Three answers, not two. `check-ignore` uses its exit code to speak: 0
    ignored, 1 not ignored, anything else "I could not look". The third was
    being read as the second.
    """
    if not facts.is_git:
        return False
    code = _git_status(root, "check-ignore", "-q", "--", rel)
    if code == 0:
        return True
    if code == 1:
        return False
    # Anything else is git failing to answer, not git saying no. Measured:
    # an audit that ran while a commit held `index.lock` reported this
    # repository's `.env.e2e.local` as unignored - a `serious` finding about
    # a credential, produced by a race and gone on the next run. Silence is
    # the honest answer, and the reason is recorded so the run can say the
    # check did not happen rather than that it passed.
    facts.git_unavailable = facts.git_unavailable or f"check-ignore failed ({code})"
    return True


# --------------------------------------------------------------- as findings

RULE_ASSISTANT_COMMITS = "bp-assistant-commits"
RULE_TOOL_ARTIFACTS = "bp-assistant-artifacts"
RULE_ENV_EXPOSED = "sec-env-not-ignored"
RULE_ENV_TRACKED = "sec-env-tracked"
RULE_ASSISTANT_TOUCHED = "bp-assistant-touched"

#: How many examples a finding names before it says "+N". Enough to
#: recognise the pattern, short enough to stay one line.
_NAMED = 3


def _listed(values: list) -> str:
    named = ", ".join(str(v) for v in values[:_NAMED])
    extra = len(values) - _NAMED
    return f"{named}, +{extra}" if extra > 0 else named


def as_documents(facts: RepoFacts, root: str) -> list:
    """The facts as `DocumentReport`s, in the order they matter.

    Security first, and not as a formality: a credential in the working tree
    is the only thing here that gets worse the longer it is not read.
    """
    from audit.base import (
        BEST_PRACTICES, CRITICAL, EXACT, Issue, MINOR, SECURITY, SERIOUS,
    )
    from audit.engine import DocumentReport

    documents = []

    def add(source: str, rule: str, severity: str, category: str, details: dict,
            snippet: str = "") -> None:
        documents.append(DocumentReport(
            source=source, elements_checked=1,
            issues=[Issue(rule_id=rule, severity=severity, category=category,
                          confidence=EXACT, source=source, selector="",
                          line=None, snippet=snippet, details=details,
                          engine="repo")]))

    for rel in facts.tracked_env:
        # Already published. Deleting the file does not undo that, and a
        # finding that says "remove it" would be advice that leaves the
        # secret where it is.
        add(rel, RULE_ENV_TRACKED, CRITICAL, SECURITY, {"path": rel})
    for rel in facts.exposed_env:
        add(rel, RULE_ENV_EXPOSED, SERIOUS, SECURITY, {"path": rel})

    if facts.tool_artifacts:
        add(root, RULE_TOOL_ARTIFACTS, MINOR, BEST_PRACTICES,
            {"count": len(facts.tool_artifacts),
             "names": _listed(facts.tool_artifacts)},
            snippet=_listed(facts.tool_artifacts))
    if facts.blamed_assistant:
        add(root, RULE_ASSISTANT_TOUCHED, MINOR, BEST_PRACTICES,
            {"count": facts.blamed_assistant, "read": facts.blamed_total})
    if facts.assistant_commits:
        add(root, RULE_ASSISTANT_COMMITS, MINOR, BEST_PRACTICES,
            {"count": len(facts.assistant_commits),
             "read": facts.commits_read,
             "names": _listed([subject for _sha, subject
                               in facts.assistant_commits])},
            snippet=_listed([f"{sha} {subject}"
                             for sha, subject in facts.assistant_commits]))
    return documents


# ------------------------------------------------------------------- blame
#
# When a flagged line arrived, and in whose commit. This is the part of the
# module that answers a question no classifier can: not "does this look
# written by a model" but "was it written in a commit that says it was".

#: Files blamed in one run. `git blame` walks a file's whole history, so an
#: unbounded pass over a large repository is a scan of its own - and the
#: files that carry findings are few (nine of four hundred, in the run this
#: was measured on).
_BLAME_FILES = 60

#: `git blame --porcelain` opens each line's record with the commit sha, and
#: precedes it with header lines this reads.
_BLAME_HEADER = re.compile(r"^(?P<sha>[0-9a-f]{40})\s+\d+\s+(?P<line>\d+)")


@dataclass
class Arrival:
    """When one line last changed, and in which commit."""
    sha: str = ""
    summary: str = ""
    author: str = ""
    when: str = ""
    #: True when that commit names an assistant as a co-author.
    assistant: bool = False


def _blame_file(root: Path, rel: str) -> dict:
    """`line number -> Arrival` for one file. Empty when git cannot say."""
    out = _git(root, "blame", "--porcelain", "--", rel)
    if not out:
        return {}
    lines: dict = {}
    # Keyed by sha and kept for the whole file, because `--porcelain` sends
    # a commit's `summary`/`author` **once**, the first time that commit is
    # seen; every later line of the same commit gets a bare header. Reset
    # per line, the second finding in a file blamed to one commit came back
    # with an empty summary - true of the output, false about the commit.
    seen: dict = {}
    sha = ""
    number = 0
    for row in out.splitlines():
        header = _BLAME_HEADER.match(row)
        if header:
            sha = header.group("sha")
            number = int(header.group("line"))
            seen.setdefault(sha, {})
            continue
        if not sha:
            continue
        if row.startswith("summary "):
            seen[sha]["summary"] = row[len("summary "):]
        elif row.startswith("author "):
            seen[sha]["author"] = row[len("author "):]
        elif row.startswith("author-time "):
            seen[sha]["time"] = row[len("author-time "):]
        elif row.startswith("\t"):
            known = seen.get(sha, {})
            lines[number] = Arrival(sha=sha[:12],
                                    summary=known.get("summary", ""),
                                    author=known.get("author", ""),
                                    when=known.get("time", ""))
    return lines


def blame_issues(root, issues, facts: RepoFacts | None = None) -> int:
    """Attach `details["arrived"]` to every issue git can place. Returns how
    many were placed.

    Grouped by file rather than asked per finding: `git blame` reads a
    file's whole history either way, so one call per finding would read the
    same history thirty times for thirty findings in one file.

    **What blame answers, and what it does not.** It names the commit that
    last touched a line, which is not the same as the commit that introduced
    the problem - a reformat, a rename or a moved block all take the line
    over. The explanation says so rather than letting a date imply an
    authorship it cannot support.
    """
    root = Path(root)
    facts = facts or read_facts(root)
    if not facts.is_git:
        return 0

    assistant_shas = {sha for sha, _subject in facts.assistant_commits}
    by_file: dict = {}
    for issue in issues:
        line = getattr(issue, "line", None)
        source = getattr(issue, "source", "") or ""
        if not line or not source:
            continue
        try:
            rel = Path(source).resolve().relative_to(root.resolve()).as_posix()
        except (ValueError, OSError):
            continue
        by_file.setdefault(rel, []).append(issue)

    placed = 0
    for rel in sorted(by_file)[:_BLAME_FILES]:
        blamed = _blame_file(root, rel)
        if not blamed:
            continue
        for issue in by_file[rel]:
            arrival = blamed.get(int(issue.line))
            if arrival is None:
                continue
            arrival.assistant = arrival.sha in assistant_shas or bool(
                _ASSISTANT_RE.search(arrival.summary))
            details = dict(getattr(issue, "details", None) or {})
            details["arrived"] = arrival
            issue.details = details
            placed += 1
    facts.blamed_total = placed
    facts.blamed_assistant = len(assistant_authored(issues))
    return placed


def assistant_authored(issues) -> list:
    """The issues whose line last changed in a commit naming an assistant."""
    out = []
    for issue in issues:
        arrival = (getattr(issue, "details", None) or {}).get("arrived")
        if isinstance(arrival, Arrival) and arrival.assistant:
            out.append(issue)
    return out
