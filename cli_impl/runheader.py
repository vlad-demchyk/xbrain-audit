"""What a document says about the run that produced it.

Every report in this tool describes findings and, until now, said almost
nothing about *how they were obtained*. Two reports on the same site can
differ by a factor of three because one ran the browser and the other did
not, one read the whole repository and the other stopped at a file limit,
one asked for `--confidence exact` and the other took everything. A reader
comparing them, or checking one months later, had no way to tell which run
they were holding.

So each document opens with the command, the target and the parameters that
changed what was measured. Only those: `--report` and `--styled-report` say
where the file went, not what is in it, and listing them would pad the line
that has to stay readable.
"""
from __future__ import annotations

#: `(attribute, label, how to render it)` for the options that change what a
#: run measures. Order is the order a reader checks them in: what read the
#: text, how far it went, what it was allowed to say.
_PARAMETERS = (
    ("detector", "detector", None),
    ("scope", "scope", None),
    ("medium", "medium", None),
    ("confidence", "confidence", None),
    ("depth", "depth", None),
    ("max_pages", "max pages", None),
    ("max_files", "max files", None),
    ("language", "language", None),
)


def _breakpoints(args) -> str:
    names = getattr(args, "breakpoints", None)
    if names in (None, "", False):
        return ""
    return names if isinstance(names, str) else ",".join(names)


def describe(command: str, target: str, args, *, language: str = "",
             extra: dict | None = None) -> list:
    """`[(label, value)]` for the run, in reading order.

    `language` is passed in rather than read off `args` because the report
    language is *decided* - asked for, detected, or English - and the
    decision is what a reader needs, not the flag that may have been absent.
    """
    rows = [("command", command), ("target", target)]
    if command == "fullscan":
        rows.append(("AI text analysis", "on" if getattr(args, "ai_text", False)
                     or getattr(args, "agent", False) else "off"))
    for attribute, label, render in _PARAMETERS:
        if attribute == "language":
            continue
        value = getattr(args, attribute, None)
        if value in (None, "", False):
            continue
        rows.append((label, render(value) if render else str(value)))

    widths = _breakpoints(args)
    if widths:
        rows.append(("breakpoints", widths))
    # Browser rendering is the single biggest difference between two runs of
    # the same target, and it is spelled by absence: `--no-browser`.
    if getattr(args, "no_browser", False):
        rows.append(("browser", "off (--no-browser)"))
    elif command in ("fullscan", "audit"):
        rows.append(("browser", "on"))
    for flag, label in (("site_controls", "site controls"),
                        ("unsettled", "unsettled shown"),
                        ("include_environment", "local environment shown"),
                        ("incremental", "incremental"),
                        ("no_typography", "typography off"),
                        ("devserver", "dev server"),
                        # A run confined to the parts a checkout ships is a
                        # different run from one that read the whole page,
                        # and a report that does not say so invites the two
                        # to be compared as if they were the same reading.
                        ("web_parts", "web parts only")):
        if getattr(args, flag, False):
            rows.append((label, "yes"))
    # Which project, when one was picked out of a folder that holds
    # several. Without it two runs over the same monorepo read as two runs
    # over the same thing, which is exactly what they are not.
    project = getattr(args, "project", None)
    if project:
        rows.append(("project", str(project)))
    # What the detected stack switched on, when it switched anything on.
    # Set by `cli_impl.prerun.profile`; a parameter that changed what was
    # measured has to be in the document that reports the measurement.
    applied = getattr(args, "_profile_applied", ())
    if applied:
        rows.append(("stack defaults",
                     ", ".join(f"--{item.option.replace('_', '-')}"
                               for item in applied)))
    if language:
        rows.append(("report language", language))
    for label, value in (extra or {}).items():
        rows.append((label, str(value)))
    return rows


def as_markdown(rows) -> list:
    """The same rows as a compact definition list, for a `.md` document."""
    if not rows:
        return []
    return ["## This run", "",
            *[f"- **{label}:** {value}" for label, value in rows], ""]


def as_line(rows) -> str:
    """One line, for a place that has no room for a list."""
    return " · ".join(f"{label} {value}" for label, value in rows)
