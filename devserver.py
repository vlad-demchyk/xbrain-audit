"""Start a repo's own dev server, so `fullscan` can read the rendered site.

A repo target has never had a browser look at it: `fullscan ./repo` reads
source files directly, and a rendered page triggers audit rules a source
file never can (`<html lang>`, canonical links, axe-core, Core Web Vitals -
measured live: 15 rules on a rendered page against 3 on the matching source).
When there is no live URL but there *is* a checkout, this closes that gap by
finding the project's own "run the dev server" command and starting it.

**Every command here is a fixed argv list, never a shell string.** Reading
`package.json`'s `scripts.dev` and running it executes repo-controlled data,
which is a different risk class from every other subprocess call in this
codebase (`llm/claude_code_provider.py`, `report/activity.py`,
`cli_install.py` - all fixed, hardcoded argv). The name of a script is read;
its value never is - `npm run dev` lets npm's own argv dispatch resolve it,
so nothing here ever passes a string through a shell.

Three stacks in this version, one shared interface so a fourth is additive:
Node (`package.json`), Django (`manage.py`), Rails (`Gemfile` + `bin/rails`).
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

#: How long a line buffer is kept, for both "why did it never become ready"
#: and "what did the install command say" diagnostics.
_MAX_LINES = 200

#: No new output (Node) or no new connect attempt (Django/Rails) for this
#: long means stalled. Not a total timeout - see `report/activity.py`, which
#: this mirrors in shape: a fixed print ceiling and no ceiling at all are the
#: same design error from two sides, so this watches for progress and stops
#: on its absence.
STALL_SECONDS = 30.0

_POLL_SECONDS = 0.5

#: `npm run dev` (or `start`), `pnpm dev`, `yarn dev` all read the same way:
#: a package manager resolving a script name it is handed, never the script
#: text itself.
_READY_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1):(\d+)")


class DevServerUnavailable(RuntimeError):
    """The runtime, a required binary, or an installable manifest is missing.

    Never retried automatically - installing something is a separate,
    explicitly confirmed action, not something this exception triggers.
    """


class DevServerInstallFailed(RuntimeError):
    """The install command ran and exited non-zero."""


class DevServerNeverReady(RuntimeError):
    """The process exited, or stalled, before a ready signal was seen."""


@dataclass
class DevServerPlan:
    stack: str
    start_argv: list[str]
    cwd: Path
    install_argv: list[str] | None = None
    #: Set for Django/Rails, where the invocation is ours to choose. `None`
    #: for Node, where a bundler (Vite/Next/CRA/webpack-dev-server) picks its
    #: own port and the only way to learn it is to read what the process says.
    fixed_port: int | None = None


# ---------------------------------------------------------------- stacks

class Stack(Protocol):
    name: str

    def detect(self, repo: Path) -> bool: ...
    def deps_satisfied(self, repo: Path) -> bool: ...
    def install_argv(self, repo: Path) -> list[str]: ...
    def start_argv(self, repo: Path, port: int | None) -> list[str]: ...
    #: `True` when this stack's process announces its own URL in its output
    #: (Node); `False` when the caller chose the port and should poll it
    #: directly (Django, Rails).
    reads_own_port: bool


def _require(binary: str | None, name: str, how: str) -> str:
    if not binary:
        raise DevServerUnavailable(
            f"{name} was not found on PATH. {how}")
    return binary


class NodeStack:
    name = "node"
    reads_own_port = True

    def detect(self, repo: Path) -> bool:
        return (repo / "package.json").exists()

    def deps_satisfied(self, repo: Path) -> bool:
        return (repo / "node_modules").is_dir()

    def _package_manager(self, repo: Path) -> str:
        if (repo / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (repo / "yarn.lock").exists():
            return "yarn"
        return "npm"

    def _npm_binary(self, repo: Path) -> str:
        manager = self._package_manager(repo)
        return _require(shutil.which(manager), manager,
                        "install Node.js (which provides npm), or the "
                        "package manager this project's lockfile names.")

    def install_argv(self, repo: Path) -> list[str]:
        return [self._npm_binary(repo), "install"]

    def start_argv(self, repo: Path, port: int | None) -> list[str]:
        import json

        binary = self._npm_binary(repo)
        try:
            manifest = json.loads((repo / "package.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DevServerUnavailable(f"package.json could not be read: {exc}")
        scripts = manifest.get("scripts") or {}
        # The *name* is read to know a runnable script exists; the *value*
        # is never executed directly - `npm run dev` lets npm resolve it.
        for script in ("dev", "start", "serve"):
            if script in scripts:
                return [binary, "run", script]
        raise DevServerUnavailable(
            "package.json has no dev/start/serve script")


class DjangoStack:
    name = "django"
    reads_own_port = False

    def detect(self, repo: Path) -> bool:
        return (repo / "manage.py").exists()

    def _python(self, repo: Path) -> str:
        for venv_dir in (".venv", "venv"):
            candidate = repo / venv_dir / "bin" / "python"
            if candidate.exists():
                return str(candidate)
        return sys.executable

    def deps_satisfied(self, repo: Path) -> bool:
        python = self._python(repo)
        result = subprocess.run([python, "-c", "import django"],
                                cwd=str(repo), capture_output=True)
        return result.returncode == 0

    def install_argv(self, repo: Path) -> list[str]:
        requirements = repo / "requirements.txt"
        if not requirements.exists():
            raise DevServerUnavailable(
                "Django is not importable and there is no requirements.txt "
                "to install from")
        return [self._python(repo), "-m", "pip", "install", "-r",
                str(requirements)]

    def start_argv(self, repo: Path, port: int | None) -> list[str]:
        return [self._python(repo), str(repo / "manage.py"), "runserver",
                f"127.0.0.1:{port}"]


class RailsStack:
    name = "rails"
    reads_own_port = False

    def detect(self, repo: Path) -> bool:
        return (repo / "Gemfile").exists() and (repo / "bin" / "rails").exists()

    def deps_satisfied(self, repo: Path) -> bool:
        bundle = _require(shutil.which("bundle"), "bundle",
                          "install Ruby and Bundler.")
        result = subprocess.run([bundle, "check"], cwd=str(repo),
                                capture_output=True)
        return result.returncode == 0

    def install_argv(self, repo: Path) -> list[str]:
        bundle = _require(shutil.which("bundle"), "bundle",
                          "install Ruby and Bundler.")
        return [bundle, "install"]

    def start_argv(self, repo: Path, port: int | None) -> list[str]:
        return ["bin/rails", "server", "-p", str(port), "-b", "127.0.0.1"]


#: Checked in this order; the first match wins. A repo with more than one
#: marker (rare) gets whichever is listed first.
STACKS: tuple[Stack, ...] = (NodeStack(), DjangoStack(), RailsStack())


def detect_stack(repo: Path) -> Stack | None:
    for stack in STACKS:
        if stack.detect(repo):
            return stack
    return None


def is_workspace_root(repo: Path) -> bool:
    """Does this directory's dev server serve more than this directory?

    A monorepo root is not a project that happens to contain projects: its
    `dev` script starts, or orchestrates, the applications under it.
    Measured on `~/repositories/XFormat`: the root declares
    `workspaces: ["apps/*", "packages/*"]` and a `dev` script, and each of
    its four applications declares a `dev` script of its own. Starting the
    root's server and auditing it as "the project" audits whichever app that
    script happens to bring up first.

    Read from the manifests the package managers themselves read - npm and
    yarn `workspaces`, pnpm's `pnpm-workspace.yaml`, and the lockfile-level
    workspace files of the others - never guessed from a directory called
    `apps/`.
    """
    import json

    for name in ("pnpm-workspace.yaml", "lerna.json", "nx.json",
                 "turbo.json", "rush.json"):
        if (repo / name).exists():
            return True
    manifest = repo / "package.json"
    if not manifest.is_file():
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(data.get("workspaces"))


@dataclass(frozen=True)
class Server:
    """One directory that can serve itself, and what serving it means."""
    root: str
    #: `devserver.Stack.name` - "node", "django", "rails".
    stack: str
    #: True when starting this one starts (or orchestrates) more than itself.
    #: The caller has to say so rather than pretend the choice is not there.
    workspace: bool = False
    #: True when the dependencies are already installed, so starting it will
    #: not ask to run an install first.
    ready: bool = True


def servers_under(root: str | Path, projects=None) -> list:
    """Every dev server this target could start, nearest first.

    `projects` is `project_profile.projects(root)` when the caller already
    has it - both walk the same tree and neither needs to walk it twice.

    A monorepo answers with more than one, and that is the whole point: the
    root's server and each application's own server are different runs, and
    a flag that silently took the first was making the choice for the person
    who asked for it.
    """
    root = Path(root)
    found: list = []
    seen: set = set()
    candidates = [root]
    for profile in (projects or ()):
        candidates.append(Path(getattr(profile, "root", "")))
    for candidate in candidates:
        key = str(candidate)
        if not key or key in seen or not candidate.is_dir():
            continue
        seen.add(key)
        stack = detect_stack(candidate)
        if stack is None:
            continue
        try:
            # A Node project answers off the filesystem; the other two shell
            # out, which is not something to do once per project in a
            # twenty-project folder while a form is being drawn.
            ready = (stack.deps_satisfied(candidate)
                     if stack.name == "node" else True)
        except Exception:  # noqa: BLE001 - a stack that cannot answer is not
            ready = True   # a reason for a form to fail to draw
        found.append(Server(root=key, stack=stack.name,
                            workspace=is_workspace_root(candidate),
                            ready=ready))
    return found


def pick_port() -> int:
    """A port nothing is listening on right now.

    Only used for Django/Rails, where the invocation is ours to choose.
    Releasing the socket before the real server binds it is a known,
    accepted race - see the plan's trade-offs section - not treated as a
    correctness bug here.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def build_plan(stack: Stack, repo: Path, *,
              start_argv: list[str] | None = None,
              port: int | None = None) -> DevServerPlan:
    """The plan for `stack`, or the caller's own override.

    `start_argv`, when given, already came from `shlex.split()` at the CLI
    boundary - a fixed argv by the time it reaches here, exactly like every
    other path through this module.
    """
    resolved_port = None if stack.reads_own_port else (port or pick_port())
    argv = start_argv if start_argv is not None else stack.start_argv(repo, resolved_port)
    install = None
    if not stack.deps_satisfied(repo):
        install = stack.install_argv(repo)
    return DevServerPlan(stack=stack.name, start_argv=argv, cwd=repo,
                         install_argv=install, fixed_port=resolved_port)


def run_install(plan: DevServerPlan) -> None:
    result = subprocess.run(plan.install_argv, cwd=str(plan.cwd),
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = "\n".join((result.stderr or result.stdout or "").splitlines()[-20:])
        raise DevServerInstallFailed(
            f"`{' '.join(plan.install_argv)}` exited {result.returncode}:\n{tail}")


# ------------------------------------------------------------------ process

@dataclass
class DevServerProcess:
    """A started dev server: readable output, a clean way to stop it.

    `start_new_session=True` gives the process its own process group (POSIX
    `setsid`), which is what makes `stop()` able to reach a bundler's child
    processes - a plain `Popen.terminate()` only reaches the immediate
    child and leaves the rest running.
    """
    popen: subprocess.Popen
    plan: DevServerPlan
    _lines: list = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_line_at: float = field(default_factory=time.monotonic)

    @classmethod
    def start(cls, plan: DevServerPlan) -> "DevServerProcess":
        kwargs = {}
        if sys.platform != "win32":
            kwargs["start_new_session"] = True
        popen = subprocess.Popen(
            plan.start_argv, cwd=str(plan.cwd), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
            encoding="utf-8", errors="replace", **kwargs)
        proc = cls(popen=popen, plan=plan)
        reader = threading.Thread(target=proc._drain, daemon=True)
        reader.start()
        return proc

    def _drain(self) -> None:
        if self.popen.stdout is None:
            return
        for line in self.popen.stdout:
            with self._lock:
                self._lines.append(line.rstrip("\n"))
                if len(self._lines) > _MAX_LINES:
                    del self._lines[0]
                self._last_line_at = time.monotonic()

    def tail(self, count: int = 20) -> str:
        with self._lock:
            return "\n".join(self._lines[-count:])

    def wait_ready(self, timeout_s: float = 60.0) -> str:
        """Block until the server answers, or raise why it never did.

        Node: a new stdout line matching a `localhost:PORT` URL is the
        signal - the port is not ours to know in advance. Django/Rails: a
        real TCP connect to the port we chose is the stronger signal, and
        does not depend on the process's own logging.
        """
        deadline = time.monotonic() + timeout_s
        seen = 0
        while time.monotonic() < deadline:
            if self.popen.poll() is not None:
                raise DevServerNeverReady(
                    f"{self.plan.stack} exited with code {self.popen.returncode} "
                    f"before it was ready:\n{self.tail()}")
            if self.plan.fixed_port is not None:
                if _port_open("127.0.0.1", self.plan.fixed_port):
                    return f"http://127.0.0.1:{self.plan.fixed_port}"
            else:
                with self._lock:
                    new_lines = self._lines[seen:]
                    seen = len(self._lines)
                for line in new_lines:
                    match = _READY_RE.search(line)
                    if match:
                        return match.group(0)
            with self._lock:
                idle = time.monotonic() - self._last_line_at
            # For a fixed-port stack there is no stdout progress signal to
            # measure idleness by, so only Node's stall clock is stdout-fed;
            # Django/Rails simply run out the timeout via the loop above,
            # which is itself the progress signal (a fresh connect attempt
            # every poll).
            if self.plan.fixed_port is None and idle >= STALL_SECONDS:
                raise DevServerNeverReady(
                    f"{self.plan.stack}: no output for {STALL_SECONDS:.0f}s:\n{self.tail()}")
            time.sleep(_POLL_SECONDS)
        raise DevServerNeverReady(
            f"{self.plan.stack}: not ready after {timeout_s:.0f}s:\n{self.tail()}")

    def stop(self) -> None:
        if self.popen.poll() is not None:
            return
        try:
            if sys.platform != "win32":
                os.killpg(os.getpgid(self.popen.pid), signal.SIGTERM)
            else:
                self.popen.terminate()
        except ProcessLookupError:
            return
        try:
            self.popen.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                if sys.platform != "win32":
                    os.killpg(os.getpgid(self.popen.pid), signal.SIGKILL)
                else:
                    self.popen.kill()
            except ProcessLookupError:
                pass


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        try:
            probe.connect((host, port))
            return True
        except OSError:
            return False
