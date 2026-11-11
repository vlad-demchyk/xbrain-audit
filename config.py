"""Local app configuration: API keys and persisted user settings.

Settings are stored in a small JSON file in the user's config directory so
they survive restarts. Secrets (API keys) are read from environment
variables first and only fall back to the file, so you can keep them out
of the file entirely if you prefer (e.g. export ANTHROPIC_API_KEY=...).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import platform_dirs

APP_NAME = "xanalyze"
APP_VERSION = "0.73.0"
# Pre-rename config dir name. Only used to migrate an existing install's
# settings into the new location the first time this runs after upgrading;
# see `migrate_legacy_file`.
OLD_APP_NAME = "ai-content-scanner"


def migrate_legacy_file(old_dir: Path, new_dir: Path, filename: str) -> None:
    """Copy `filename` from `old_dir` into `new_dir` once, if needed.

    Used when an app/service gets renamed and its config dir (or keychain
    fallback dir) moves with it: without this, someone upgrading would find
    the app behaving like a fresh install and silently lose settings that
    were never actually gone, just under the old directory name.

    Only runs when `new_dir` doesn't have the file yet, so it's idempotent
    and never clobbers changes made after the migration already happened.
    The old file is left in place (copied, not moved) — another instance of
    the app, an older version, or some other tool may still be reading or
    writing it until everything using the old name is gone.
    """
    new_file = new_dir / filename
    if new_file.exists():
        return
    old_file = old_dir / filename
    if not old_file.exists():
        return
    try:
        new_file.write_bytes(old_file.read_bytes())
    except OSError:
        pass


def _config_dir() -> Path:
    base = str(platform_dirs.config_home())
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    migrate_legacy_file(Path(base) / OLD_APP_NAME, path, "settings.json")
    return path


def config_file() -> Path:
    """Where settings live, resolved now rather than at import.

    It used to be `CONFIG_FILE = _config_dir() / "settings.json"`, a module
    constant, and that made the real file unavoidable for a test: by the time
    a test could set `XDG_CONFIG_HOME`, the path had already been computed
    from whatever the variable was during import. `tests/test_devserver_gui.py`
    found that out by flipping the developer's own auto-start setting on disk
    and passing anyway, and three lines in `tests/test_ui_suppression.py` still
    carry the copy-paste workaround it forced. See `P-13`.

    A function instead, so the environment decides at the moment of the read
    or the write, and one variable isolates the whole process.
    """
    return _config_dir() / "settings.json"


@dataclass
class Settings:
    ui_language: str = "uk"                 # 'uk' | 'it' | 'en'
    # Kept only so a choice made in an older version can be migrated into
    # `default_method` and `llm_provider` on load - nothing reads it to
    # decide what runs any more. See `_migrate_detector_choice`.
    default_detector: str = "offline"        # matches DetectorFactory registry names
    # What the window's method combo is set to: which engines judge the copy.
    # Stored as the same "+"-joined key the combo carries (see
    # `MainWindow.choice_key`): "local", "ai", or "local+ai" for the hybrid.
    # A method rather than a detector name because "run a model too" is the
    # decision the user makes; which class implements it follows from that
    # and from `llm_provider`.
    default_method: str = "local"
    crawl_depth: int = 1
    max_pages: int = 30
    # The folder walk's ceiling, the window's copy of `--max-files`. It had
    # none, so a monorepo was silently cut at `ScanConfig`'s default and the
    # window never said which number did the cutting. Same default as the
    # CLI: two surfaces reading different amounts of one repository is the
    # kind of disagreement nobody notices until the reports differ.
    max_files: int = 5000
    # Anthropic's current default model. Older ids stay valid — this is only
    # what a fresh install starts on; see `_MIGRATIONS` for how a stored
    # value from a previous version is handled.
    claude_model: str = "claude-opus-5"
    # 'auto' follows the OS appearance; 'light' / 'dark' pin it. The palette
    # itself comes from xFormat's design tokens either way (ui/tokens.py).
    theme: str = "auto"
    # Repository mode: what counts as text worth reading. 'content' is the
    # copy that ships to a user; 'technical' is comments and docstrings;
    # 'both' is either. See repo_scanner's SCOPE_* constants.
    repo_scope: str = "content"
    # The checkout last paired with a site, remembered so the second audit of
    # the same project does not ask again. A path, or empty. Only the window
    # writes it: the CLI is told with `--repo` on every run, which is the
    # right contract for something a pipeline drives.
    last_paired_repo: str = ""

    # The non-keyboard-character pass runs alongside whichever detector is
    # selected: it's offline, exact, and its fix costs nothing, so there's
    # no reason to make the user choose between it and a content detector.
    unicode_check_enabled: bool = True
    # Which unicode_rules categories to report. Defaults to all of them;
    # drop "typography" to keep proper em dashes and curly quotes.
    unicode_categories: list = field(
        default_factory=lambda: ["invisible", "space", "homoglyph", "styled", "typography"]
    )

    # Which backend pays for rewrite calls: "anthropic" (your own API key),
    # "xformat" (app.xformat.net subscription) or "claude-code" (the `claude`
    # CLI already signed in on this machine). See llm/.
    llm_provider: str = "anthropic"
    # When this tool runs *inside* Claude Code — a hook, a CI step, an agent
    # calling cli.py — that session is already authenticated and already
    # being paid for. Routing those calls to a subscription instead would
    # bill a second account for the same work, and would fail outright on a
    # machine that has Claude Code but no xFormat login. So inside Claude
    # Code the CLI uses Claude Code, unless `--provider` says otherwise.
    # This only affects the CLI: the desktop app is not launched by an agent,
    # and there the user's explicit choice in Settings is the answer.
    prefer_claude_code_in_cli: bool = True
    # Model for that automatic route. Empty means "whatever the CLI is
    # configured to use", which is what someone driving this from a Claude
    # Code session normally expects; set e.g. "sonnet" to pin it cheaper.
    claude_code_model: str = ""
    # How hard that session thinks. Empty means "whatever the session is set
    # to". A scan classifies short passages against a fixed rubric, which a
    # low setting does as well as a high one and far faster - the API judge
    # has always sent `effort: "low"` for the same reason. Set it here to make
    # the Claude Code route match, or raise it for a one-off careful pass.
    claude_code_effort: str = ""
    # The API host, not the app host: app.xformat.net serves the web client.
    # Mirrors BUILTIN_API_URL in the frontend's saasAuth/backendUrl.ts.
    xformat_base_url: str = "https://api.xformat.net"
    # Overrides for XFormatEndpoints — only the keys you want to change.
    # Lets the API contract be corrected from Settings without a code edit.
    xformat_endpoints: dict = field(default_factory=dict)

    # Findings the user has already decided about — phrases that are house
    # style, checks they don't want, paths and page regions to skip, and
    # individual dismissed findings. See suppression.py; a scanned project
    # can add its own list in a committed `.xanalyze-ignore` file.
    ignore: dict = field(default_factory=dict)

    # Whether the packaged app has already offered to put the `xanalyze`
    # command on PATH (`cli_install.offer_is_due`). Set once the question has
    # been *asked*, not once it has been answered yes: "no" is an answer, and
    # re-asking on every launch would turn a convenience into a nag. Someone
    # who changes their mind has the button in Settings.
    cli_install_offered: bool = False

    # Off by default: a repo target's dev server may already be running
    # (someone's own `npm run dev` in another terminal), and starting a
    # second one on a different port would be the confusing outcome, not the
    # helpful one. On, Analyze detects and starts it automatically, exactly
    # as the toolbar's "Start server" button does on its own when clicked.
    auto_start_devserver: bool = False

    @classmethod
    def load(cls) -> "Settings":
        path = config_file()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                merged = {**asdict(cls()), **data}
                # Drop keys from older/newer versions so an out-of-date config
                # file can't stop the app from starting.
                known = set(cls.__dataclass_fields__)
                return _migrate(cls(**{k: v for k, v in merged.items() if k in known}))
            except (json.JSONDecodeError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        config_file().write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")


# Values that were *this application's* defaults in an earlier version, and
# what they become. Applied on load so an existing settings.json doesn't
# leave someone pinned to a retired model or a detector that no longer
# exists as a separate entry.
#
# Only these exact strings are rewritten. A value the user chose themselves
# is left alone even when it is old — picking a specific model or a specific
# base URL is a decision, and silently overruling it would be worse than
# leaving it slightly stale.
_MIGRATIONS = {
    "default_detector": {
        # The two offline passes stopped being separate detectors; see
        # detectors/offline.py. The factory also aliases both names, so this
        # is belt and braces — it keeps the stored value truthful rather
        # than relying on the alias forever.
        "heuristic": "offline",
        "unicode-anomalies": "offline",
    },
    "claude_model": {
        "claude-sonnet-4-5": "claude-opus-5",
    },
    "xformat_base_url": {
        # Was a guess at the API host before the backend was wired up; the
        # app domain serves the web client and answers 404 for /api/auth/*.
        "https://app.xformat.net": "https://api.xformat.net",
    },
}


#: The judge each old `default_detector` value stood for, as a provider.
#: One direction only: this is a migration, not a lookup table for running
#: code - see `detectors/judges.py` for that.
_DETECTOR_PROVIDERS = {
    "claude-llm-judge": "anthropic",
    "xformat-llm-judge": "xformat",
    "claude-code-llm-judge": "claude-code",
}


def _migrate_detector_choice(settings: "Settings") -> "Settings":
    """Turn "my detector is the xFormat judge" into "my method is hybrid and
    my account is xFormat".

    Someone who had picked a judge in the old dropdown was asking for a model
    to read their text; after the change, the method combo decides that, and
    leaving it at its default would have quietly demoted them to offline-only
    on first launch - the same silent substitution this release exists to
    remove. The hybrid is the honest target rather than AI-only: the offline
    pass is free, finds exact character defects a model does not, and used to
    run alongside every judge anyway.

    Only the stored default is touched, and only while the new fields are
    still untouched themselves, so a deliberate choice made after upgrading
    is never overwritten by one made before it.
    """
    provider = _DETECTOR_PROVIDERS.get(settings.default_detector)
    if provider is None:
        return settings
    if settings.default_method == Settings.default_method:
        settings.default_method = "local+ai"
    if settings.llm_provider == Settings.llm_provider:
        settings.llm_provider = provider
    settings.default_detector = "offline"
    return settings


def _migrate(settings: "Settings") -> "Settings":
    for field_name, replacements in _MIGRATIONS.items():
        current = getattr(settings, field_name, None)
        if current in replacements:
            setattr(settings, field_name, replacements[current])
    return _migrate_detector_choice(settings)


def get_anthropic_api_key() -> str | None:
    """Env var first, then the OS keychain (see llm/credentials.py).

    The key is never written to the plain settings.json — if the user types
    one into Settings it goes to the keychain like any other secret.
    """
    env = os.environ.get("ANTHROPIC_API_KEY")
    if env:
        return env
    try:
        from llm import credentials
        return credentials.load_secret("anthropic_api_key")
    except Exception:  # noqa: BLE001 - never let credential storage break startup
        return None


def set_anthropic_api_key(value: str) -> None:
    from llm import credentials
    if value:
        credentials.save_secret("anthropic_api_key", value)
    else:
        credentials.delete_secret("anthropic_api_key")
