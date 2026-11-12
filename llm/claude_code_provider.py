"""Claude Code provider — calls run through the `claude` CLI already
installed and signed in on this machine.

Why this exists as a third provider rather than a setting on the Anthropic
one: when this tool is driven from inside Claude Code (a hook, a CI step, an
agent running `cli.py`), there is already an authenticated Claude session in
the environment. Sending those calls to the xFormat subscription instead
would bill a second account for work the first one is already paying for,
and would fail outright on a machine that has Claude Code but no xFormat
login. So inside Claude Code the right backend is Claude Code itself.

Three things about driving the CLI are worth knowing, because each one cost
a call to discover:

**`--bare` cannot be used.** It restricts authentication to
`ANTHROPIC_API_KEY`, which is precisely what this provider exists to avoid;
with it, a perfectly signed-in machine reports "Not logged in".

**The default run loads the whole agent.** Without
`--strict-mcp-config`/`--allowedTools ""` a one-sentence rewrite ships the
full tool catalogue and every configured MCP server as input: measured at
~33k tokens for a 17-token answer. With them the same call reads a small
cached prefix instead.

**The working directory is part of the prompt.** Claude Code discovers
`CLAUDE.md` from the directory it runs in, so running in the scanned project
would let that project's house rules rewrite the user's copy. Calls are made
from a neutral empty directory for that reason.

Checking authentication is free here — `claude auth status --json` reads the
local credentials and calls nothing — which is why `auth_status()` on this
provider, unlike the xFormat one, costs nothing to ask.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import (
    REWRITE_SYSTEM_PROMPT, AuthStatus, LLMAuthError, LLMProvider,
    LLMProviderFactory, LLMUnavailable, prompt_language,
)

#: Overrides binary discovery when the CLI lives somewhere unusual.
BIN_ENV_VAR = "CLAUDE_CODE_BIN"

#: Where the native installer puts it when it is not on PATH.
_FALLBACK_PATHS = (
    Path.home() / ".local" / "bin" / "claude",
    Path("/opt/homebrew/bin/claude"),
    Path("/usr/local/bin/claude"),
)

#: Set by Claude Code in every process it spawns. Presence of this is what
#: "we are running inside Claude Code" means; see `running_inside_claude_code`.
_SESSION_ENV_VARS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")

#: Passing `--model` at all is optional: without it the CLI uses whatever
#: model the session or the user's config selects, which is usually what
#: someone driving this from Claude Code expects.
DEFAULT_MODEL = ""

#: How hard the session thinks. Empty means "whatever the session is set to",
#: the same contract as the model. The CLI accepts `--effort <level>`; a scan
#: classifies short passages against a fixed rubric, which is the kind of work
#: a low setting does as well as a high one and far faster - see
#: `detectors/claude_llm_judge.py`, which has made the same choice on the API
#: path since it was written.
DEFAULT_EFFORT = ""

#: A rewrite is short. A CLI start-up plus one turn measured ~6s cold and
#: ~2s warm, so this is generous rather than tight.
DEFAULT_TIMEOUT = 180.0

#: Batch marker. Deliberately not JSON: asking for prose *inside* JSON makes
#: the model escape quotes and newlines, and one bad escape loses the whole
#: batch instead of one passage.
_MARKER = "<<<{n}>>>"


def find_binary() -> str | None:
    override = os.environ.get(BIN_ENV_VAR)
    if override:
        return override if Path(override).exists() else None
    found = shutil.which("claude")
    if found:
        return found
    for path in _FALLBACK_PATHS:
        if path.exists():
            return str(path)
    return None


def running_inside_claude_code() -> bool:
    """True when this process was started by Claude Code.

    Used by `rewriter.build_provider` to route AI calls here instead of to a
    paid subscription — the session that launched this tool is already
    authenticated and already being billed.
    """
    return any(os.environ.get(var) for var in _SESSION_ENV_VARS)


class ClaudeCodeProvider(LLMProvider):
    name = "claude-code"
    display_name = "Claude Code CLI (this machine's signed-in session)"
    uses_account = True

    def __init__(self, model: str = DEFAULT_MODEL, timeout: float = DEFAULT_TIMEOUT,
                 binary: str | None = None, effort: str = DEFAULT_EFFORT,
                 **config):
        super().__init__(**config)
        self.model = model or ""
        self.effort = effort or ""
        self.timeout = timeout
        self._binary = binary or find_binary()
        self._workdir: str | None = None

    # ------------------------------------------------------------ plumbing

    def _require_binary(self) -> str:
        if not self._binary:
            raise LLMUnavailable(
                "The `claude` CLI was not found. Install Claude Code, or set "
                f"{BIN_ENV_VAR} to its path, or switch the provider to your "
                "own Anthropic key or the xFormat subscription."
            )
        return self._binary

    def _neutral_workdir(self) -> str:
        """An empty directory, so no project's CLAUDE.md joins the prompt."""
        if self._workdir is None:
            self._workdir = tempfile.mkdtemp(prefix="xanalyze-claude-")
        return self._workdir

    def _argv(self, system: str) -> list:
        argv = [
            self._require_binary(), "-p", "--output-format", "json",
            # No tools, no MCP servers: a rewrite needs neither, and their
            # definitions would be the largest part of every request.
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--tools", "",
            "--allowedTools", "",
            "--system-prompt", system,
        ]
        if self.model:
            argv += ["--model", self.model]
        if self.effort:
            argv += ["--effort", self.effort]
        return argv

    def _call(self, system: str, user_text: str) -> str:
        try:
            completed = subprocess.run(
                self._argv(system), input=user_text, capture_output=True,
                # UTF-8 both ways: the locale default on Windows (cp1252)
                # cannot even encode a Cyrillic prompt.
                text=True, encoding="utf-8", errors="replace", timeout=self.timeout, cwd=self._neutral_workdir(),
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMUnavailable(
                f"The claude CLI did not answer within {self.timeout:.0f}s."
            ) from exc
        except OSError as exc:
            raise LLMUnavailable(f"Could not run the claude CLI: {exc}") from exc

        try:
            payload = json.loads(completed.stdout or "{}")
        except ValueError:
            detail = (completed.stderr or completed.stdout or "").strip()[:300]
            raise LLMUnavailable(
                f"The claude CLI returned no JSON (exit {completed.returncode}): {detail}"
            )

        result = payload.get("result")
        if payload.get("is_error"):
            message = result if isinstance(result, str) else "unknown error"
            if _looks_like_auth_error(message):
                raise LLMAuthError(
                    f"Claude Code is not signed in ({message.strip()}). "
                    "Run `claude auth login` in a terminal."
                )
            raise LLMUnavailable(f"The claude CLI reported an error: {message}")
        if not isinstance(result, str) or not result.strip():
            raise LLMUnavailable("The claude CLI returned an empty answer.")
        return result.strip()

    # ---------------------------------------------------------------- API

    def auth_status(self) -> AuthStatus:
        """Free: reads local credentials, makes no request and bills nothing."""
        if not self._binary:
            return AuthStatus(signed_in=False, detail="claude CLI not found")
        try:
            completed = subprocess.run(
                [self._binary, "auth", "status"], capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=30,
            )
            payload = json.loads(completed.stdout or "{}")
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            return AuthStatus(signed_in=False, detail=f"status check failed: {exc}")

        if not payload.get("loggedIn"):
            return AuthStatus(signed_in=False, detail="not signed in (`claude auth login`)")
        detail = " · ".join(
            str(payload[key]) for key in ("email", "subscriptionType", "authMethod")
            if payload.get(key)
        )
        return AuthStatus(signed_in=True, detail=detail or "signed in")

    def rewrite(self, text: str, language: str | None = None) -> str:
        language = prompt_language(language)
        prompt = f"{text}\n\n(language: {language})" if language else text
        return self._call(REWRITE_SYSTEM_PROMPT, prompt)

    def rewrite_batch(self, items: list) -> list:
        """One process per batch instead of one per passage.

        Each CLI call pays a start-up and a cached-prefix read, which for a
        one-sentence rewrite costs more than the rewrite itself. A hundred
        flagged passages sent one at a time measured minutes; sent together
        they are one call. If the answer comes back unparseable the sequential
        path still runs, so a malformed batch costs time, never content.
        """
        if len(items) <= 1:
            return [self.rewrite(text, lang) for text, lang in items]

        parts = []
        for index, (text, language) in enumerate(items, start=1):
            marker = _MARKER.format(n=index)
            language = prompt_language(language)
            hint = f" (language: {language})" if language else ""
            parts.append(f"{marker}{hint}\n{text}")
        instruction = (
            REWRITE_SYSTEM_PROMPT + "\n\n"
            "Several passages follow, each introduced by a marker line of the "
            "form <<<N>>>. Rewrite every one of them. Return the rewrites in "
            "the same order, each preceded by its own unchanged marker line "
            "and nothing else. Do not merge, reorder, number or comment on them."
        )
        answer = self._call(instruction, "\n\n".join(parts))
        parsed = _split_marked(answer, len(items))
        if parsed is None:
            return [self.rewrite(text, lang) for text, lang in items]
        return parsed

    def analyze(self, system: str, user_text: str) -> str:
        """Used by the judge detector, so an AI review runs on the same
        session as the rewrites rather than needing a second account."""
        return self._call(system, user_text)


def _split_marked(answer: str, expected: int) -> list | None:
    """Cut a batch answer back apart, or None if it does not line up.

    Markers are only recognised on a line of their own, and only in order.
    Both conditions matter: a rewritten passage may well *contain* the text
    "<<<2>>>" (this tool's own documentation does), and treating that as a
    boundary would cut someone's sentence in half and hand the tail to the
    next passage.

    None rather than a partial list on purpose: a batch that lost one passage
    would otherwise put someone else's rewrite into the wrong place, which is
    worse than paying for a second, slower pass.
    """
    lines = answer.splitlines()
    starts = []
    cursor = 0
    for index in range(1, expected + 1):
        marker = _MARKER.format(n=index)
        while cursor < len(lines) and lines[cursor].strip() != marker:
            cursor += 1
        if cursor >= len(lines):
            return None
        starts.append(cursor)
        cursor += 1

    pieces = []
    for order, start in enumerate(starts):
        end = starts[order + 1] if order + 1 < len(starts) else len(lines)
        piece = "\n".join(lines[start + 1:end]).strip()
        if not piece:
            return None
        pieces.append(piece)
    return pieces


def _looks_like_auth_error(message: str) -> bool:
    lowered = (message or "").lower()
    return "not logged in" in lowered or "/login" in lowered or "unauthor" in lowered


LLMProviderFactory.register(ClaudeCodeProvider.name, ClaudeCodeProvider)
