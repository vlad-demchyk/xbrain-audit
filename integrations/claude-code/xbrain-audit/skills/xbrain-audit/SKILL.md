---
name: xbrain-audit
description: Run and read XBrain Audit (the `xaudit` CLI): AI-written copy and non-keyboard characters in text or code, and website audits (accessibility, SEO, performance, security) of a URL, an HTML file or a repository; fixing characters, comparing runs, auditing pages behind a login. Use when the person mentions xaudit or XBrain Audit (formerly XAnalyze, `xanalyze`), «запусти xaudit», «проскануй на ШІ-текст», «невидимі символи», «перевір сайт», «аудит сайту», «аудит доступності», «повний скан», or asks to check copy or a page an agent just wrote.
---

# Working with XBrain Audit

XBrain Audit measures; the agent decides what to run, reads the result in the right order and proves a fix with a second run. It is read-only unless `fix` is asked for, and a clean run means "nothing the tool can see", never "accessible" or "human-written".

For an accessibility audit and its triage, follow `brain-a11y-verify` as well; this skill is the tool itself.

## 1. Which binary

- Installed: `xaudit` (`~/.local/bin/xaudit`, a link into `/Applications/XBrain Audit.app`). `xaudit --version` first.
- Source: `~/repositories/XAnalyze`, branch `refactor/mvvm-state-machine`; `./venv/bin/python cli.py …` runs the code as it is now. `make check` says whether the built app (window, CLI and TUI are one bundle) matches the source. A stale bundle reports old behaviour: when a finding looks like a fixed bug, check the version before reporting it.
- Rebuilding and replacing the installed app are the person's decision: `make rebuild-all PYINST="./venv/bin/python -m PyInstaller"` (the venv's own `pyinstaller` script can carry a dead shebang), after raising `APP_VERSION` in `config.py`.

## 2. Pick the command

| The question | Command |
|---|---|
| "Check this", everything at once | `xaudit fullscan TARGET` (URL, folder or one HTML file) |
| AI-sounding copy and non-keyboard characters only | `xaudit scan PATHS` |
| Website rules only | `xaudit audit TARGET` (alias `a11y`) |
| Replace non-keyboard characters | `xaudit fix PATHS` (keeps `.bak`), `xaudit undo` |
| What did earlier runs find, continue one, diff two | `xaudit runs`, `resume`, `compare` |
| A page behind a sign-in | `xaudit login URL` once, then the run |
| An agent judges the AI candidates itself | `agent-scan` → judge → `agent-judge --judgments FILE` |

Options worth knowing (`xaudit COMMAND --help` lists all):

- `--json` (machine result on stdout), `--report FILE.md|.json` (briefing for an agent), `--styled-report FILE.html|.pdf` (for a person).
- `--browser` / `--no-browser`: the browser pass adds axe-core, HTML_CodeSniffer, focus, keyboard, forms and target size (2.5.8). Without it only markup is read, much faster.
- `--depth N --max-pages N` for a crawl; `--site-controls` reads robots.txt and sitemaps.
- `--color-scheme dark` shows the page `prefers-color-scheme: dark`. One scheme per run: a site with a dark theme needs a second run, and each page records the scheme it actually saw.
- `--repo PATH` maps a site's findings to files; `--devserver` starts the project's own server and audits the rendered site.
- `--category`, `--confidence exact|needs-browser|advisory`, `--unsettled` are views over one pass, not different runs.
- `--language uk|it|en` is the report's language. `--detector offline|ai|hybrid|embedding` for the AI-copy pass (offline is free and the default; `ai` is billed to the account `--provider` names).
- `--progress jsonl` streams one JSON event per line on stderr while stdout stays the result; set `XAUDIT_PROGRESS=jsonl` for a whole shell. A stderr line that is not JSON is Qt's, skip it.
- `--check` turns serious findings into exit code 1, for CI.

Exit codes: `0` clean, `1` findings (only with `--check`), `2` could not run, `3` stopped part-way (`xaudit resume`).

## 3. Where the output goes

Every run writes a dated folder under `~/Documents/XBrain Audit/<target>/` (`XAUDIT_REPORT_ROOT` moves it). Put an agent's own copies outside the repository, in a dated folder such as `~/Downloads/<project>-xaudit-<date>/`, with `--json` and `--styled-report`. Never inside the audited project.

## 4. Read the result in this order

1. `counts` and the headline are **distinct problems**; `occurrences` is how many places. Plan by `problems` (each with its `pages` / `sources`), never by the raw total.
2. `coverage` and the `# [browser n/m]` lines: how much was really audited, what failed to load, what was skipped.
3. The notices on stderr: `# N check(s) could not be decided … (rules)` names what `--unsettled` would add; `# [environment] …` on a local site counts server findings left out (`--include-environment` lists them); `# [profile] …` suggests options for the detected stack.
4. Then findings by severity and cause. Each one has `confidence`: `exact` (measured or read), `needs-browser` (a static reading a browser should settle), `advisory` (a person decides).

Every finding that will change a project is checked against the real source first: open the file and line it names, or `curl` the page and read the element. A finding is a lead, not a fact about the project. A rule that fires hundreds of times on one component is suspect first: read the element, and if the tool is wrong, that is a task for the XBrain Audit project, not something to hide in the report.

## 5. React and other component files

`audit` reads `.jsx`/`.tsx` as written: elements on different branches of a conditional, `cond &&` / `!cond &&` or separate `return`s are not duplicates; a component with a `label` prop is named; text in code is not text; selectors are JSX paths (`section.card > div.list > img`). What a component renders is invisible to a static pass, so `needs-browser` findings there are questions for a `--devserver` or URL run, not defects.

## 6. Behind a login

`xaudit login https://site/path` opens a real browser on the site's own form; the person (or the agent with a **test** account the person gave) signs in there. XBrain Audit stores what the site handed the browser, per host, never the password. Then run the audit normally; `--no-session` reads the site as a stranger. `login --list` and `login --forget HOST` manage the stored sessions. Never put a password or a cookie on the command line, in a report or in a message. On production, only test accounts and nothing that changes data: the browser pass reads and never types, clicks or submits.

A crawl that reached a door instead of a page says so (`authwall` notice); a clean summary over sign-in forms means nothing was audited.

## 7. Prove a fix

1. The **same command** before and after, into two folders. Compare `distinct` and the specific rule ids, not totals.
2. The fixed cause is gone and nothing new appeared; a new problem after a fix is usually a page the first run did not reach, so compare the crawled address lists.
3. Browser results are cached by page markup and pass revision. After changing the **server** (a header, a stylesheet), run with `XAUDIT_BROWSER_CACHE=<empty folder>`.
4. Say what was checked (command, version, pages, date), what was not, and the residual risk.

## 8. AI-written copy

The offline detector names the phrase or pattern it matched, so a finding can be argued with. It is corpus-dependent and weak in Italian; a run over Italian text says so and names the better detector. No detector result is proof of authorship. For the agent loop: `xaudit agent-scan PATHS --json` lists candidate blocks; judge each yourself; `xaudit agent-judge PATHS --judgments verdicts.json` merges the verdicts with the offline pass. Details in `references/agent-loop.md`.
