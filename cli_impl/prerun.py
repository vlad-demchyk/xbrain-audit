"""What this run is about to do, and what it is about to leave undone.

A scan takes what it was given and reports what it found. Two of the most
useful things this tool can do are not defaults and were never mentioned:

* a **site** audited without `--repo` reports the page a problem is on, and
  cannot say which file to open - the repository behind it was never asked
  for;
* a **repository** scanned without `--devserver` is read as source, so every
  rule that needs a rendered page (contrast, focus order, layout at a
  breakpoint, the measurements) simply does not run - and the project may
  be one command away from serving itself.

Neither is a defect in the run. Both are the difference between a shallow
answer and a deep one, and the person or the agent that started the run is
the only one who can decide. So they are said before the work starts, in a
line an agent can match on and a person can read, and the run continues
either way: this is a notice, not a prompt, because a scan that blocks on a
question cannot be put in a pipeline.

`--no-hints` silences them. Nothing here changes what is measured.
"""
from __future__ import annotations

from pathlib import Path

import progress

#: Prefix every line carries, so an agent driving the CLI can find them
#: without parsing prose. One code per kind of missed depth.
PREFIX = "# [hint]"


def _repo_hint(target: str) -> str:
    return (f"{PREFIX} repo: no --repo given, so findings will name the page "
            f"and not the file behind it. Pass --repo PATH to point at the "
            f"checkout that serves {target} and every text finding that "
            f"matches a passage in it gets a file and a line.")


def _devserver_hint(root: Path, stack_name: str, deps: bool) -> str:
    how = (f"Pass --devserver to start it and audit the rendered site"
           if deps else
           f"Pass --devserver --yes to install its dependencies and start it")
    return (f"{PREFIX} devserver: this looks like a {stack_name} project, so "
            f"it can serve itself. Read as source, the rules that need a "
            f"rendered page do not run: contrast, focus order, layout at a "
            f"breakpoint, and every measurement. {how}, or point the scan at "
            f"a server you already have with --url http://localhost:PORT.")


def _browser_hint() -> str:
    return (f"{PREFIX} browser: --no-browser was given, so this is the static "
            f"reading only. axe, HTML_CodeSniffer, the state rules and the "
            f"measurements are all skipped, and a quiet result here is not "
            f"the same answer a rendered one would give.")


def _breakpoints_hint() -> str:
    return (f"{PREFIX} breakpoints: only the desktop width is audited. Pass "
            f"--breakpoints all for tablet, mobile and the 320 px reflow "
            f"check, which is where responsive failures live.")


#: The codes, which are also the translation-key stems for a surface that
#: does not print English. One per kind of depth a run is not reaching.
REPO = "repo"
DEVSERVER = "devserver"
BROWSER = "browser"
BREAKPOINTS = "breakpoints"


def missed(command: str, target: str, args, *, is_url: bool) -> list:
    """`[(code, fields)]` - the depth this run is not reaching, as data.

    Split out of `hints` when the window needed the same answers: the CLI
    prints an English line with a flag in it, and a window has neither a
    flag to name nor English to print. Two implementations of "what is this
    run leaving undone" is how two surfaces start disagreeing about it.
    """
    if getattr(args, "no_hints", False):
        return []
    found = []
    if is_url:
        if not getattr(args, "repo", None):
            found.append((REPO, {"target": target}))
    else:
        root = Path(target)
        if root.is_dir() and not getattr(args, "devserver", False) \
                and not getattr(args, "url", False):
            stack = _stack_of(root)
            if stack is not None:
                found.append((DEVSERVER, {"stack": stack.name,
                                          "deps": stack.deps_satisfied(root)}))
    if command in ("audit", "fullscan"):
        if getattr(args, "no_browser", False):
            found.append((BROWSER, {}))
        elif is_url and not getattr(args, "breakpoints", None):
            found.append((BREAKPOINTS, {}))
    return found


def hints(command: str, target: str, args, *, is_url: bool) -> list:
    """The lines to print before this run starts. Empty is a normal answer."""
    writers = {
        REPO: lambda fields: _repo_hint(fields["target"]),
        DEVSERVER: lambda fields: _devserver_hint(Path(target), fields["stack"],
                                                  fields["deps"]),
        BROWSER: lambda _fields: _browser_hint(),
        BREAKPOINTS: lambda _fields: _breakpoints_hint(),
    }
    return [writers[code](fields)
            for code, fields in missed(command, target, args, is_url=is_url)]


def _stack_of(root: Path):
    """The dev-server stack this project looks like, or None.

    Imported here rather than at module level: `devserver` pulls in the
    process machinery, and a hint must not make a scan slower to start.
    """
    try:
        import devserver

        return devserver.detect_stack(root)
    except Exception:  # noqa: BLE001 - a hint is never worth a failed run
        return None


def announce(command: str, target: str, args, *, is_url: bool, out) -> list:
    """Print the hints and hand them back, for a caller that also logs them."""
    lines = hints(command, target, args, is_url=is_url)
    for line in lines:
        # `kind` is the word after the prefix (`repo`, `devserver`, …): the
        # line already carries it for a person, and an agent should not have
        # to re-derive it from prose.
        body = line.removeprefix(PREFIX + " ")
        progress.notice("hint", body, human=line,
                        code=body.split(":", 1)[0], stream=out)
    return lines


#: Prefix for a line about what the target's own stack asks for. Separate
#: from `PREFIX` because the two say different things: a hint is depth this
#: run is not reaching, a profile line is a parameter this target implies.
PROFILE_PREFIX = "# [profile]"


#: Options `audit` and `fullscan` apply from the target itself rather than
#: suggesting.
_APPLIED_BY_AUDIT = frozenset({"page_tree", "site_scope", "render"})


def profile(command: str, target: str, args, *, is_url: bool, out) -> list:
    """What this target's stack asks for - said, and applied only if asked.

    The window and the terminal form pre-tick these controls, because there
    a person sees the tick and the sentence under it before pressing Run.
    The CLI does not: a command line is a contract, and a run that started a
    dev server because a `vite.config.ts` was found would be a different run
    from the one the script author wrote. So here it is a line, and
    `--profile-defaults` is how a caller asks for the same behaviour the
    forms have.

    Returns the applied suggestions - empty unless `--profile-defaults`.
    """
    import run_profile

    if getattr(args, "no_hints", False):
        return []
    kind = run_profile.KIND_SITE if is_url else None
    plan = run_profile.build(target, forced_url=bool(is_url),
                             repo=getattr(args, "repo", None) or "")
    if kind and plan.kind != kind:  # pragma: no cover - build agrees
        return []
    lang = getattr(args, "language", None) or "en"
    applied = []
    if getattr(args, "profile_defaults", False):
        applied = plan.apply(args, touched=getattr(args, "_explicit", ()))
        # Kept on `args` so the report can name what was switched on. See
        # `cli_impl.runheader.describe`.
        args._profile_applied = tuple(applied)
    for item in plan.suggestions:
        if command in ("audit", "fullscan") and item.option in _APPLIED_BY_AUDIT:
            # `audit` applies these itself and says so in its own line
            # (`cli_impl.auditpass.plan_sharepoint`); "consider" here would
            # contradict it.
            continue
        flag = "--" + item.option.replace("_", "-")
        on = item in applied
        verb = "on" if on else "consider"
        why = run_profile.explain(item, lang, enabled=on)
        progress.notice("profile", f"{verb} {flag}={item.value}: {why}",
                        human=f"{PROFILE_PREFIX} {verb} {flag}={item.value}: "
                              f"{why}",
                        option=item.option, value=item.value, applied=on,
                        stream=out)
    for prompt in plan.prompts:
        why = run_profile.explain(prompt, lang)
        progress.notice("profile", f"ask {prompt.field}: {why}",
                        human=f"{PROFILE_PREFIX} ask {prompt.field}: {why}",
                        ask=prompt.field, stream=out)
    if plan.ambiguous():
        names = ", ".join(plan.choices()[:6])
        more = ", …" if len(plan.projects) > 6 else ""
        text = (f"{len(plan.projects)} projects under this folder "
                f"({names}{more}); auditing all of them as one. "
                f"`--project NAME` audits one on its own.")
        progress.notice("profile", text, human=f"{PROFILE_PREFIX} {text}",
                        projects=len(plan.projects),
                        choices=plan.choices()[:6], stream=out)
    shared = plan.shared_server()
    if shared is not None and plan.project_servers():
        text = (f"this is a workspace root: its own dev server is what "
                f"--devserver starts, and {len(plan.project_servers())} "
                f"project(s) under it have one of their own. "
                f"`--project NAME` starts that project's.")
        progress.notice("profile", text, human=f"{PROFILE_PREFIX} {text}",
                        project_servers=len(plan.project_servers()), stream=out)
    return applied
