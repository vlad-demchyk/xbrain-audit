"""What a real browser already said about a page, kept between runs.

The browser pass is the expensive half of an audit and the only half that
costs seconds rather than milliseconds: measured on this machine, 12 s for
one page at four widths against 0.05 s for every static rule over the same
markup. A crawl of thirty pages is six minutes of it, and re-running the
same audit an hour later paid that again for a byte-identical page.

**Keyed on the markup, never on the address.** A URL is not an answer: a
page changes, and a cache keyed on where it lives would serve yesterday's
findings about today's page - the exact failure this project refuses
elsewhere. The crawler has already fetched the markup by the time the
browser pass starts, so the key is a hash of *what was served*, together
with everything else that changes the answer: the widths, the engines that
were asked, the rules that were disabled and the selectors that were
excluded. Change any of those and it is a different question, so it is a
different entry.

**What is not cached.** A page that failed to load: an error is a fact
about one attempt, and the next attempt is entitled to a different one.
Measurements are kept, because they were measured on that same markup, but
they are timings from a machine that was doing something else at the time -
`fresh` says which run they came from, so a reader can tell.

The store is a directory of JSON files, one per key-shape, under the user's
home beside the judgment cache. Same reasoning as there: the same page
audited from two checkouts is the same page.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy
import json
import time
from pathlib import Path
from cache_store import merge_cache

#: Where entries live.
#: Under `app_identity.data_home()`, resolved at each call: the folder is
#: renamed at startup, after this module may already be imported.
CACHE_SUBDIR = "browser"

#: Overrides the location. For CI, for containers and above all for tests:
#: without it a test run writes into the developer's real cache and the next
#: run reads its own leftovers back as browser answers. The old
#: `XANALYZE_BROWSER_CACHE` is still read when this is not set.
DIR_ENV = "XAUDIT_BROWSER_CACHE"

#: How long an entry is honoured. A week: long enough that a working session
#: and the next day's re-check are free, short enough that an engine upgrade
#: or a changed environment does not haunt a report for a month.
MAX_AGE_DAYS = 7

#: Above this the file is rewritten from scratch rather than grown. A crawl
#: of a large site puts a few hundred entries in; a cache nobody prunes is a
#: cache that eventually costs more to read than the pass it saves.
MAX_ENTRIES = 500

#: Bumped by hand when the *driver* changes what a pass can observe without
#: any script changing: 2 is the hidden view being given window focus, which
#: turned three focus checks from "read nothing" into "read the page". A
#: changed in-page script needs no bump (its source is hashed into the key);
#: a changed way of running it does. So does a change in how an engine's
#: output becomes a finding, because what is stored here is the finding, not
#: the engine's raw message: 3 is HTML_CodeSniffer's prompts and the removed
#: 4.1.1 getting their own weight; 4 is axe's `target-size` (2.5.8) switched
#: on, which the cached findings of 3 never ran; 5 is HTML_CodeSniffer's
#: caption suggestion (H39.3.NoCaption) weighed as a prompt; 6 waits for a
#: page to stop being aria-busy before measuring it; 7 also waits for finite
#: animations to end.
PASS_REVISION = 7


def cache_dir() -> Path:
    import app_identity

    override = app_identity.env("BROWSER_CACHE")
    return Path(override) if override else app_identity.data_home() / CACHE_SUBDIR


def markup_key(markup: str) -> str:
    """The identity of one page: what the server actually sent."""
    return hashlib.sha256((markup or "").encode("utf-8")).hexdigest()[:32]


def _fingerprint(*parts) -> str:
    # A separator that cannot occur inside any of the parts, so ("ab", "c")
    # and ("a", "bc") are two keys rather than one.
    joined = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:20]


def options_key(options, sizes) -> str:
    """Everything besides the markup that changes what comes back.

    Read off the options object rather than listed by hand where possible:
    a new switch that changes the answer and is not in the key is a cache
    that lies, and that is worse than no cache at all.
    """
    from audit import browser, states, vitals
    return _fingerprint(
        vitals.vendor_identity()["artifact_sha256"],
        vitals.vendor_identity()["collector_sha256"],
        # The state pass is our own script, and until now the one input to the
        # answer that was not in the key: a changed focus check kept serving
        # the findings of the old one for up to a week. Hashing the source is
        # the whole fix - there is nothing to remember to bump.
        hashlib.sha256(states.STATE_SCRIPT.encode("utf-8")).hexdigest()[:16],
        # The HTML_CodeSniffer collector is ours too: what it reports about
        # the flagged element (its attribute name, for H30.2) is in the answer.
        hashlib.sha256(browser.htmlcs_script().encode("utf-8")).hexdigest()[:16],
        PASS_REVISION,
        tuple(sorted(getattr(options, "exclude", ()) or ())),
        tuple(sorted(getattr(options, "disabled_rules", ()) or ())),
        bool(getattr(options, "run_axe", True)),
        bool(getattr(options, "run_htmlcs", True)),
        bool(getattr(options, "run_states", True)),
        bool(getattr(options, "run_measurements", True)),
        bool(getattr(options, "allow_local_files", False)),
        str(getattr(options, "color_scheme", "light") or "light"),
        int(getattr(options, "settle_ms", 0) or 0),
        int(getattr(options, "performance_repeats", 1)),
        json.dumps(getattr(options, "performance_scenario", []), sort_keys=True),
        tuple((name, width, height) for name, width, height in (sizes or ())),
    )


def _issue_to_record(issue) -> dict:
    return {
        "rule_id": issue.rule_id,
        "severity": issue.severity,
        "selector": issue.selector,
        "line": issue.line,
        "snippet": issue.snippet,
        "details": issue.details or {},
        "fix_snippet": issue.fix_snippet,
        "confidence": issue.confidence,
        "source": issue.source,
        "category": issue.category,
        "owner": issue.owner,
        "engine": issue.engine,
    }


def _record_to_issue(record: dict, source: str):
    from audit.base import Issue

    data = dict(record)
    # The address is the caller's, not the cache's: the same markup can be
    # served at two URLs, and a finding has to point at the page in hand.
    data["source"] = source
    return Issue(**data)


class BrowserCache:
    """Verdicts for one shape of question: these engines, these widths."""

    def __init__(self, options, sizes, directory: Path | None = None) -> None:
        self.key = options_key(options, sizes)
        self.directory = Path(directory) if directory else cache_dir()
        self.path = self.directory / f"{self.key}.json"
        self._entries: dict = {}
        self._dirty = False
        self.hits = 0
        self.misses = 0
        self._load()
        self._baseline = deepcopy(self._entries)

    # ---------------------------------------------------------------- disk
    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        cutoff = time.time() - MAX_AGE_DAYS * 86400
        self._entries = {
            key: value for key, value in raw.items()
            if isinstance(value, dict) and value.get("at", 0) >= cutoff
        }
        self._dirty = len(self._entries) != len(raw)

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            self._entries = merge_cache(self.path, self._entries, self._baseline,
                                        cutoff=time.time() - MAX_AGE_DAYS * 86400,
                                        limit=MAX_ENTRIES)
            self._baseline = deepcopy(self._entries)
            self._dirty = False
        except OSError:
            # A cache that cannot be written is a slow run, not a failed one.
            pass

    # --------------------------------------------------------------- reads
    def get(self, markup: str, source: str):
        """The stored `PageAudit` for this markup, or None."""
        entry = self._entries.get(markup_key(markup))
        if entry is None:
            self.misses += 1
            return None
        from audit.driver import PageAudit

        self.hits += 1
        measurements = deepcopy(entry.get("measurements") or {})
        if measurements:
            measurements.setdefault("conditions", {}).update({
                "cacheHit": True, "reusedAtUnix": time.time(),
                "freshMeasurement": False, "originalMeasurementUnix": entry.get("at"),
            })
        issues = [_record_to_issue(deepcopy(record), source)
                  for record in entry.get("issues", [])]
        for issue in issues:
            if issue.details and "measurements" in issue.details:
                issue.details["measurements"] = deepcopy(measurements)
        return PageAudit(
            url=source,
            issues=issues,
            measurements=measurements,
            error="",
            engine_errors={},
            html=entry.get("html", "") or "",
        )

    def put(self, markup: str, page_audit) -> None:
        """Remember one page. A failed pass is not remembered."""
        if getattr(page_audit, "error", "") or getattr(page_audit, "engine_errors", {}):
            return
        self._entries[markup_key(markup)] = {
            "at": int(time.time()),
            "issues": [_issue_to_record(issue) for issue in page_audit.issues],
            "measurements": getattr(page_audit, "measurements", {}) or {},
            "html": getattr(page_audit, "html", "") or "",
        }
        self._dirty = True

    def summary(self) -> str:
        """One line for stderr, or empty when there is nothing to say."""
        total = self.hits + self.misses
        if not total or not self.hits:
            return ""
        return (f"{self.hits}/{total} page(s) unchanged since a previous run, "
                f"read from cache instead of the browser")
