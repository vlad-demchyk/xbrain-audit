# XAnalyze

Finds AI-written copy, invisible characters, and accessibility, SEO, performance
and security defects in a website, an HTML file or a repository - and reports the
exact line, not a score.

[Українська](README_ua.md) | [Italiano](README_it.md)

## What it is for

You are handed a page, a theme, a web part or a repository and have to answer
three questions: is this copy machine-written, does the markup carry characters
no keyboard produces, and is the thing accessible and correct. XAnalyze answers
all three in one run and names the file and line behind every answer.

It is one binary with three surfaces - a desktop window, a terminal interface
and a command line - over one core, so the three cannot disagree about what a
run measured.

## Install

**macOS app**

```bash
curl -L -o XAnalyze.app.zip https://github.com/vlad-demchyk/xAnalyze-/releases/latest/download/XAnalyze.app.zip
ditto -x -k XAnalyze.app.zip /Applications/
```

On first launch the app offers once to link itself as `xanalyze` in
`~/.local/bin`, so the CLI and the TUI need no second download, and
`xanalyze update` updates all three at once. The bundle is
not signed yet: the first launch needs Control-click -> Open.

**Command line only**

The app is the only download: the window, the CLI and the terminal interface
are one program. To get the `xanalyze` command without opening the window:

```bash
/Applications/XAnalyze.app/Contents/MacOS/XAnalyze --install-cli
```

**From source**

```bash
git clone https://github.com/vlad-demchyk/xAnalyze-.git && cd xAnalyze-
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py                                  # window
python cli.py fullscan https://example.com      # command line
python cli.py                                   # terminal interface
```

**Windows 10/11, from source**

There is no Windows download yet; it runs from a checkout. Python 3.13 or
newer from python.org (the `py` launcher comes with it), in PowerShell:

```powershell
git clone https://github.com/vlad-demchyk/xAnalyze-.git; cd xAnalyze-
py -3.13 -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python main.py                              # window
venv\Scripts\python cli.py fullscan https://example.com  # command line
venv\Scripts\python cli.py                               # terminal interface
```

The output is UTF-8 whatever the console code page, so it can be redirected
to a file or piped into an agent. Settings, the credential fallback file and
signed-in site sessions live in `%APPDATA%\xanalyze`, the app's own log in
`%LOCALAPPDATA%\xanalyze\logs`, and keys go to the Windows Credential
Manager. `xanalyze update` replaces a macOS app only; on Windows update the
checkout with `git pull`.

A Windows build (`dist\XAnalyze\XAnalyze.exe` for the window and
`xanalyze-cli.exe` for the command line and the TUI) is made with
`pip install pyinstaller` and then
`powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1`.

## Use it

```bash
xanalyze                                      # terminal interface
xanalyze fullscan https://example.com         # everything, in one run
xanalyze fullscan ./my-project                # the same, over a checkout
xanalyze scan ./src                           # AI patterns and characters only
xanalyze audit ./page.html                    # website rules only
xanalyze fix ./src                            # apply character fixes (.bak kept)
xanalyze runs                                 # list, resume, compare
```

`fullscan` is the answer to "check this". A URL is crawled and rendered; a
folder is read as source unless `--devserver` starts the project's own server;
a single HTML file is read as the finished page it is.

### Commands

| Command | What it does |
|---|---|
| `fullscan TARGET` | AI patterns, characters and every website rule, plus reports |
| `scan PATHS` | AI patterns and non-keyboard characters, changing nothing |
| `audit TARGET` | website rules only, over a URL, an HTML file or a folder |
| `fix` / `undo` | apply exact character corrections; restore the `.bak` copies |
| `runs` / `resume` / `compare` | a run is an object: list it, continue it, diff it against the last |
| `ignore FINGERPRINT --reason TEXT` | dismiss one finding as a false positive in `.xanalyze-ignore`, with why; the fingerprint is in `audit --json`, and every later run says how many it hid and why |
| `login URL` | sign in to a site by hand, in a real browser, so a run can read behind it; kept only when you press Done |
| `logs` | what a run actually did, as JSON Lines |
| `ai` | the account behind the model passes: `status`, `login`, `rewrite` |
| `agent-scan` / `agent-judge` | hand candidate passages to an agent and take its verdicts back |
| `clean` | filter text from stdin to stdout |
| `update` / `uninstall` | self-update from the latest release; remove everything |

Updates stage and validate the GUI bundle before replacing it, restoring the previous
app if installation fails. A partial CLI/GUI update returns exit code `3` and names
the component that failed; check again before retrying from the TUI.

New log records hide URL credentials, query strings, fragments and structured secret
fields. On macOS/Linux, logs and fallback credential files are private to the user;
fallback credential updates are atomic and serialized across processes.

Incremental file scans match the analyzed text, options, suppressions and app version.
AI verdicts use the dedicated judgment cache. Concurrent scan, browser and judgment
cache writes merge changed entries under a lock before replacing the file atomically.

Machine findings use `schema_version: 1` and preserve source locations, ranges,
confidence, engines, structured details and complete snippets. Existing keys remain
available. JSON briefings include full `findings` and `content_findings` beside their
human summaries; checkpoints preserve the same evidence on resume.

`audit` and `fullscan` include a coverage manifest with checked, skipped, unknown and
failed executions, engine versions/hashes, options and decoded-input hashes. Unknown
checks survive result filters. Missing instrumentation and unverified source mappings
stay explicit. See [the finding contract](docs/finding-contract.md).

`xanalyze COMMAND --help` prints every option. The ones worth knowing:

| Option | Purpose |
|---|---|
| `--depth N`, `--max-pages N` | how far a crawl goes, and how many pages; a page over 10 MB is listed as not read, and images are never fetched from private or local addresses the crawl did not visit itself |
| `--repo PATH` | the checkout behind a site, so a finding names the file and not only the page |
| `--devserver` | start the project's own dev server and audit the rendered site |
| `--breakpoints all` | audit every width; without it, one width (1440x900) |
| `--color-scheme dark` | show the page `prefers-color-scheme: dark`, to audit a dark theme; one scheme per run |
| `--no-browser` | the static reading only, and much faster |
| `--detector NAME` | `offline` (default, free), `embedding`, `hybrid`, `ai` |
| `--category`, `--confidence` | narrow what is reported; both are views over one pass |
| `--within SELECTOR` | audit only this part of the page - a delivered widget or web part |
| `--report PATH`, `--styled-report PATH` | agent briefing (`.md`/`.json`) and human report (`.pdf`/`.html`) |
| `--json`, `--check` | machine-readable output; exit 1 on serious findings |
| `--progress jsonl` | one JSON event per line on stderr *while* the run happens |
| `--language uk\|it\|en` | report language; detected from the pages otherwise |
| `--project NAME` | one project inside a folder that holds several, by folder name or path |
| `--start-command CMD`, `--dev-server-port N` | what to run instead of the detected script, and the port to expect |
| `--no-session` | read a site the way a stranger does, ignoring any stored sign-in |
| `--profile-defaults` | switch on what the detected stack asks for (see below) |

## What it checks

**AI-written copy.** The offline pass reads sentence rhythm, repeated
structure and cliche phrases, and names the phrase it matched so a finding can
be argued with. An embedding pass and a model-judged pass are available for a
second opinion. None of it is proof of authorship.

**Non-keyboard characters.** Zero-width characters, homoglyphs, unusual
spaces, styled letters and typography characters - each one exact, and each one
fixable in place.

**Website rules**, by category, with the count the test suite enforces:

`accessibility` (40), `best-practices` (13), `geo` (2), `performance` (8), `security` (10), `seo` (8)

A rule runs where it means something and nowhere else, decided on evidence:
the file's syntax (JSX rules only in `.jsx`/`.tsx`), what the document is for
(email rules only on an email), and which stack the project proved on disk
(the WordPress escaping rule only in WordPress). In a React file the rules
read the component as written: two elements on different arms of a
conditional, of `cond &&` / `!cond &&` or in separate `return`s are not a
duplicate id, text in code (`JSON.parse`, `CSS.escape`) is not text, a
design-system component with a `label` prop is named, and selectors are the
JSX path (`section.card > div.list > img`). A literal `aria-label`,
`placeholder`, `title` or `alt` in a file that translates its other texts is
reported as `advisory` (`jsx-untranslated-literal`).

**Written for what a manual audit found.** An `alt` that is a slug
(`mappa-parlante-palmanova`, `Piazza-Grande`, a date) and not only a file name
with an extension; a YouTube, Vimeo or similar embed whose captions, transcript
and audio description the page does not answer (1.2.2, 1.2.3, 1.2.5); a "load
more" button on a page with no live region (4.1.3); and, across a crawled
multilingual site, a link that goes somewhere else in the translation than in
the original (2.4.4). The embed, live-region and translated-link checks are
`advisory`: they say where a person must look, not that the page fails.
Links listed in another order in the translation are matched by their words
and destination, not by position. Search and filter addresses whose canonical
does not name themselves are left out of the hreflang reciprocity check and
counted in one row; a link HTML_CodeSniffer reports as an image with no `alt`
but that is named by `aria-label`, `aria-labelledby` or `title` is a note to
check the name, not a violation.

**In a browser**, when one is available: axe-core and HTML_CodeSniffer, the
page in the state a person puts it in - focus indicator and whether it can be
seen against its background (3:1), whether a sticky header covers the focused
element (2.4.11), keyboard traps, focus order, hover-only content, an open
modal, the form journey, the size of every pointer target and the space around
it (2.5.8, measured by axe-core with the box and the nearest target in the
finding) - and the same page at several widths. It reads and
never acts: nothing is typed, clicked or submitted. In the desktop app the
hidden page cannot take window focus without stealing it from the main window,
so the three focus checks report `focus-not-measured` there (shown with
`--unsettled`); the command line measures them. Every finding carries the WCAG
criteria it contributes to, in the report and in `--json` (`wcag`).

**Provenance, not verdicts.** IPTC/XMP fields and C2PA manifests in every
image a page refers to (only the first 512 KB of each is fetched), and
repository facts: tracked `.env` files, assistant-named commits, committed
assistant configuration. Reported as facts about origin, never as defects.

**Certainty.** Every finding is `exact`, `needs-browser` or `advisory`. The
undecided are not listed by default - on one real page that was 312 of 348
contrast findings - and the run says how many it left out. `--unsettled`
brings them back; `--confidence exact` drops the advisory ones too.

**Distinct problems, not repeats.** The headline, `counts` in `--json`, the
status line of the window and the terminal interface count each problem once: a
header or an icon sprite is on every page, so a crawl of 381 pages was 15 338
findings and about 980 causes. The occurrences stay beside it (`occurrences`,
`distinct` and `problems` in `--json`, each with the pages it was found on) and
every finding is still listed. HTML_CodeSniffer's "check this by hand" prompts
(label in name, `position: fixed`, an ignored image, "use a list") and the
dropped WCAG 4.1.1 are `advisory` and `minor`; what it measured, like a contrast
ratio, keeps its weight.

**A local site's server is not the project's defect.** On `localhost`, `*.local`,
`*.test` or a private address, what the server decides and plain HTTP makes
inevitable is left out of the list and counted: missing `Content-Security-Policy`,
`X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, compression and
cache headers, `http://` form actions, and a development copy's `noindex`. One
crawl of a local WordPress site had 365 critical findings that were all
`http://` forms. The run says how many it left out (`environment` in `--json`);
`--include-environment` lists them. Everything about the page itself - a
synchronous third-party script, an image, an accessible name - is reported on a
local address exactly as on a public one, and a repository audit is untouched.

## The target decides what to ask

A project announces what it is, and that decides more than which folders to
skip. An SPFx checkout knows it ships web parts and cannot know which site
they land on. A Vite or Next app read off disk is templates the bundler has
not run, where `<App />` is not a heading. One self-contained HTML file has no
second page to crawl to, so width is the only axis left.

Each of those becomes a parameter, and each arrives with the stack that asked
for it and the marker file that proved that stack: "enabled, because ..." is a
sentence you can disagree with, not a silent default. **Anything you set
yourself is never overwritten.**

The window and the terminal form apply it - the control is ticked, the reason
is under it, one click undoes it. The command line does not: a command line is
a contract, and a run that started a dev server because it found a
`vite.config.ts` would not be the run the script author wrote. There the same
suggestions are printed as `# [profile]` lines on stderr, and
`--profile-defaults` asks for them to be applied.

The same reading decides which fields exist at all: `--depth` needs an
address, `--incremental` needs files on disk, and a control that reaches
nothing for this target is not shown - nor read, so a `--devserver` ticked for
a repository does not follow you to a single file.

A folder holding several projects is asked about rather than merged: twenty
SPFx solutions in one directory are twenty deliverables. `--project NAME`, and
the picker the window and the terminal form show, audit one of them on its own
- the scan, the ignore file and the dev server all follow it, so they cannot
end up describing different projects. A repository that proves something of
its own is still one project: Bedrock's `web/` is that project's docroot, not
a second project.

**A monorepo has more than one dev server, and they are not the same run.**
The root's `dev` script starts, or orchestrates, the applications under it;
each application has a script of its own. `--devserver` was picking silently.
Now the run says which one it would start and that naming a project starts
that project's instead - measured on a real workspace, where the root
declares `workspaces: ["apps/*"]` and each of four applications declares its
own `dev`. `--start-command` overrides the script where neither is right.

## Work delivered as a fragment of somebody else's site

A **WordPress theme or plugin** is recognised the way WordPress recognises it
- the `Theme Name:` header in `style.css`, the `Plugin Name:` header in the
main PHP file - and its templates are read as fragments, so nothing asks
`header.php` for a canonical link or an `<h1>`.

A **SharePoint web part** is one subtree of a page the tenant owns.
`--within SELECTOR` confines the audit to it and switches off, with the reason
printed, everything that reads the whole document by construction. A generated
class suffix (`root-137`) need not be typed: the selector is retried against
the stem. `--repo PATH --web-parts` works the other way - it reads the
solution's manifests and finds this repository's parts wherever they appear on
the site.

Markup inside a **template literal** is audited too. `.ts` and `.js` are
skipped as files - a `<` in them is an operator - but a backtick string is not
code, and a classic SPFx part builds its whole interface in one. Measured on a
real solution: 72 of its 168 `.ts` files, and 131 findings nobody had read.

## Sites behind a login

`xanalyze login https://example.com/admin` opens a real browser on the site's
own form. 2FA, SSO and captchas all work, because it is a browser. XAnalyze
never sees a username or a password: what is kept is what the site handed that
browser, per host, readable only by you. `--no-session` reads the site the way
a stranger does; `login --list` and `login --forget HOST` manage what is
stored. Nothing about a session ever reaches a report, a log or the terminal.

A crawl also records when an address answered with a door rather than a page,
and says so plainly - a clean summary over nothing but sign-in forms is the
most misleading output this tool can produce.

## Reports

Every command writes a dated run folder, `~/Documents/XAnalyze/` by default
(`XANALYZE_REPORT_ROOT` moves it). An archive already in `~/Desktop/XAnalyze/`
from an earlier version is moved across on the first run, so the run history a
comparison needs stays where the tool looks for it:

```text
XAnalyze/example.com/2026-09-02-0930/
  report.md     grouped briefing for an agent
  report.pdf    report for a person
  timings.md    stage timings
  changes.md    what changed since the last run
  state.json    resumable state
```

Every document opens by naming the command and the parameters that changed
what was measured. A repeated problem is listed once with its locations nested
under it. `--json` keeps every finding, for CI.

Because of that grouping the summary holds two units at once, so every row
of it names its own: a category counts **distinct problems**, a character
tally counts **occurrences**, and both numbers are printed under the same
heading rather than one replacing the other. Five typography problems over
fifty-two occurrences is two facts, not a contradiction.

## Driving it from an agent

`--json` answers when the run is over. On a thirty-page site that is minutes
of silence, and whatever started the run cannot tell a slow crawl from a hung
one. `--progress jsonl` writes one JSON object per line to **stderr** as the
run happens, while stdout stays exactly what it was:

```bash
xanalyze fullscan https://example.com --progress jsonl
```

```json
{"event":"run.start","ts":"…","command":"fullscan","target":"https://example.com","version":"0.63.0"}
{"event":"stage","ts":"…","name":"crawl","state":"begin","depth":1,"max_pages":30}
{"event":"page","ts":"…","n":3,"of":30,"url":"https://example.com/pricing","depth":1}
{"event":"stage","ts":"…","name":"crawl","state":"end","pages":12}
{"event":"notice","ts":"…","kind":"authwall","text":"2 address(es) answered with a login wall …"}
{"event":"run.end","ts":"…","exit_code":0,"counts":{…},"documents":31,"sources":12}
```

| `event` | When | Fields |
|---|---|---|
| `run.start` | first line | `command`, `target`, `version` |
| `stage` | a phase begins, reports its way through, or ends | `name` (`devserver`, `scan`, `crawl`, `audit`, `browser`, `report`), `state` (`begin`, `progress`, `end`) |
| `page` | each page read | `n`, `of`, `url`, `depth` |
| `file` | each file opened | `n`, `of`, `path` |
| `notice` | anything the terminal would have said in prose | `kind`, `text`, plus the fields behind it |
| `finding` | one per finding, with `--progress jsonl=findings` | `rule`, `severity`, `source`, `line`, `kind` |
| `run.end` | last line | `exit_code`, `counts`, `documents`, `sources` |

Without the flag nothing changes: the same human lines, no JSON. `finding` is
off unless asked for, because a large site produces tens of thousands of them.

It is not the default, and deliberately: a person at a terminal wants the
sentences, and progress is already on - `jsonl` changes the *format*, not
whether the run reports itself. Which one is reading is a property of the
environment rather than of the command, so set `XANALYZE_PROGRESS=jsonl` once
and every run in that shell speaks it; `--progress human` on a single command
still wins, so one run can always be read by eye.
A line that does not parse as JSON did not come from XAnalyze - Qt writes its
own diagnostics to the same stream - so skip it rather than failing on it.

**Exit codes** are the same for every command:

| Code | Meaning |
|---|---|
| `0` | clean - the command ran and found nothing to report |
| `1` | findings, and only with `--check`. `scan`/`fix`/`clean`: any finding. `audit`/`fullscan`: a critical or serious one |
| `2` | error - the command could not run: a path that does not exist, a flag that does not apply, a detector that could not read the text |
| `3` | incomplete - a run stopped part-way and its work is on disk; `xanalyze resume` continues it |

## Interfaces

**Window** (`python main.py`, or the app). A setup screen for the target and
the run, then the finding list beside a source or rendered preview, with
fixes, replacement review and report export. Two widths can be put on screen
at once, to settle "this only breaks on mobile".

**Terminal** (`xanalyze` with no arguments). Scan, Audit, Full Scan, Reports,
Settings, Account, Update, Logs. Arrow keys, number shortcuts, `Tab`, `Esc`,
and `Ctrl+R` to run.

Mechanical corrections are selected by default; model drafts always require
review; judgement calls such as photographic alt text are never presented as
automatic fixes.

## Configuration

Settings live in `~/.config/xanalyze/settings.json` (`%APPDATA%\xanalyze\settings.json`
on Windows) - language, provider, `max_pages`, character categories.

`.xanalyze-ignore` in a project root uses gitignore syntax, and can also
suppress by rule, selector or fingerprint:

```text
vendor/
*.min.js

[rules]
meta-viewport

[fingerprints]
083bea550659aadb  # the logo's text is already in the link
```

A dismissal with a reason is one command: `xanalyze ignore FINGERPRINT
--reason "…"`, with the fingerprint taken from `audit --json`. Every later run
says how many findings the lists hid and quotes the reasons, so a hidden
finding never reads like a clean page.

## How the audit rules are kept honest

- **A corpus of checked verdicts.** `corpus/audit/verdicts.jsonl` holds real
  defects and known false positives, with where each came from. Every serious
  or critical rule has at least one of each, and the tests fail the moment a
  rule starts missing the first or reporting the second.
- **Precision on your own audits.** `python -m audit.precision AUDIT.json
  --template labels.jsonl` lists every finding to label true or false;
  `--labels labels.jsonl` then prints each rule's precision with the number of
  labelled findings beside it, and says "not measured" below five.
- **Engine updates are checked, not trusted.** After axe or HTML_CodeSniffer
  is updated, a code the reviewed version did not have is reported as a note
  until someone looks at it (`python -m audit.engine_codes`).

## Templates it understands

Fourteen template languages have a **pair** of fixtures in
`tests/fixtures/frameworks`: the same component written the way its framework
says to, and written wrong. The correct half must produce no findings and the
broken half must produce the right ones, so this is a measured claim:

`alpine`, `angular`, `blade`, `django`, `erb`, `handlebars`, `liquid`, `php`, `razor`, `react`, `svelte`, `thymeleaf`, `twig`, `vue`

Markup in anything not on this list is still read - the parser does not refuse
it - but nothing has proved that a correct file in it comes back clean.

**Both passes read a server template.** A `.blade.php` view, a WordPress
theme's `.php`, a `.twig`, `.erb`, `.ejs`, `.phtml` or `.liquid` file is markup
with a server language mixed into it, so its copy is read by the AI-pattern and
character passes exactly as the `.html` it produces would be, and its markup is
audited the same way. What the template language emits - `{{ $plan->name }}`,
`<?php echo … ?>`, `@endsection` - is not copy and is not read as it. A `.php`
file that is a controller rather than a view stays code: `$id < 10` is a
comparison, not a tag.

## Stacks it recognises

A project is identified from its own marker files, and what it turns out to be
decides what is treated as vendored rather than written here:

`angular`, `astro`, `bedrock`, `beehiiv`, `carrd`, `craft`, `django`, `docusaurus`, `dotnet`, `drupal`, `eleventy`, `ember`, `flutter`, `gatsby`, `ghost`, `hugo`, `jekyll`, `joomla`, `laravel`, `magento`, `nextjs`, `nuxt`, `qwik`, `rails`, `remix`, `shopify`, `silverstripe`, `spfx`, `spring`, `squarespace`, `statamic`, `storybook`, `sveltekit`, `symfony`, `typo3`, `vite`, `wagtail`, `webflow`, `wix`, `wordpress`, `wordpress-plugin`, `wordpress-theme`

Detection is evidence: a profile names the file that proved it, the exclusions
it implies are stated rather than applied silently, and one click scans them
anyway.

## Limits

- AI-text detection is corpus-dependent. It is not proof of authorship, and
  model judgments are not deterministic.
- **Text detection covers Ukrainian, Italian and English only.** A passage in
  another language is named as such and left unscored rather than measured
  against lists that do not speak it. Character and website checks are
  language-independent.
- **The offline wording pass is weak in Italian**: on the held-out corpus it
  finds 36% of known AI passages there, against 55% in English and 71% in
  Ukrainian, while the embedding pass finds 100%, 85% and 86%. A run over
  Italian pages says so and names the better detector.
- A folder scan cannot see content that exists only after rendering. Use a URL
  or `--devserver`.
- One width cannot describe responsive behaviour. Use `--breakpoints all`.
- One colour scheme per run: a site with a dark theme needs a second run with `--color-scheme dark`.
- Browser performance reports include LCP/CLS/INP evidence and measurement
  conditions. Use `--performance-repeats 3` and an explicit interaction scenario
  for repeated lab observations; optional Lighthouse and CrUX stay separate.
  See [browser performance](docs/browser-performance.md).
- Typography checks can flag intentional punctuation (`--no-typography`).
- C2PA reading needs the optional `c2pa-python` and `cryptography` packages.

## Building a release

Independent detector validation uses [frozen benchmark protocols](docs/detector-validation.md).
The release quality gate checks all uk/it/en and required strata; historical
calibration alone cannot approve a release.

```bash
make version        # what config.py says
make rebuild        # the one bundle: window, CLI and TUI, at that version
make package        # XAnalyze.app.zip and its manifest, what `xanalyze update` looks for
```

`make package` refuses to run over a stale bundle. The archive is not signed
or notarised yet.

## Requirements

Python 3.13+ (CI and the macOS release are built on 3.14; 3.13 is checked on
Windows 11), PySide6 for the window, QtWebEngine for browser rendering,
sentence-transformers for the embedding detector, and `c2pa-python` with
`cryptography` for optional C2PA reading.

## License

MIT
