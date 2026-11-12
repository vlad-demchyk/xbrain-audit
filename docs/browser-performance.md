# Browser performance evidence

Qt installs the pinned, Apache-2.0 licensed `web-vitals` 6.2.3 attribution
build at document creation in its isolated application world. Vendor version,
source and SHA-256 are recorded in `audit/vendor/web-vitals.json`; the loader
checks the artifact hash. LCP/CLS/INP use browser performance entries, not
markup guesses. CLS retains the maximum session value after each entry,
including deliveries spanning several sessions: consecutive gaps must be
strictly below 1 second and each window strictly below 5 seconds. Recent-input
shifts are excluded. This also preserves peaks that the upstream build's
last-session comparison can miss in a buffered delivery.

Every metric has `checked`, `unknown` or `error` evidence and attribution.
No measured input means INP unknown, with no numeric zero. These are bounded
laboratory observations, not a final full-lifetime visitor measurement. The
capture records actual viewport, visibility, navigation, settle interval,
browser user agent, profile/cache conditions and the observation end time.
Qt does not throttle network or CPU; their conditions say `none`. Subframe
metrics and bfcache restoration are not aggregated or exercised.

Measurements run before the accessibility probes can focus controls or
change the page. Responsive audits measure the first navigation only;
subsequent resizes check layout accessibility without pretending each resize
is a fresh page load. Browser-cache reuse is explicit, with the original
measurement time and `freshMeasurement: false`. It is keyed on served markup,
not on every external resource, and is not a fresh performance benchmark.
Clean measurements remain in report coverage even when no budget was crossed.

`audit` and `fullscan` accept `--performance-fresh` to bypass stored browser
results, `--performance-repeats 3` for fresh navigations with median, minimum,
maximum and population standard deviation, and `--performance-settle-ms 2500`
to bound observation after load. Repeat navigations share the profile's HTTP
cache; they are not independent cold-cache/device samples. Failed or absent
metric samples never become zero. All samples and conditions remain in JSON
coverage and checkpoints; Markdown/HTML/PDF show the values and dispersion.

`--performance-scenario scenario.json` opts into native Qt input before the
measurement snapshot. Actions are explicit, unique CSS targets in the current
viewport, with at most 10 steps and 50–2000 ms observation after each:

```json
[
  {"action": "click", "selector": "#open-menu", "wait_ms": 300},
  {"action": "key", "selector": "#menu-button", "key": "Enter", "wait_ms": 300}
]
```

Supported keys are Enter, Space, Tab, Escape, ArrowDown and ArrowUp. Arbitrary
JavaScript and text values are not scenario inputs. Missing, covered or
ambiguous targets are recorded as errors. Navigating to a different document
ends the scenario. A trusted native event, not `element.click()`, produces the
Event Timing evidence. A short scenario INP is provisional and is not a field
INP percentile for the site's visitors.

`--lighthouse` uses an already installed CLI (or `XAUDIT_LIGHTHOUSE` pointing
at one), with `--lighthouse-profile mobile|desktop` and the requested repeats.
It creates a separate Chrome session, retaining Lighthouse version and its
actual screen/network/CPU simulation settings. It does not inherit XBrain Audit's
stored sign-in. Navigation Lighthouse LCP/CLS are separate lab results; TBT
is never substituted for an unmeasured INP. No CLI means unknown; process or
runtime failures mean error. The adapter does not install software.

`--crux` explicitly queries Google's API for a public HTTP(S) target using
`CRUX_API_KEY`. `--crux-scope url|origin` controls the requested granularity;
`--crux-form-factor all|PHONE|TABLET|DESKTOP` controls the aggregation. Field
records retain their actual key, p75, histograms and collection period. Missing
data means unknown, with no automatic origin fallback. Credentials and local
addresses are excluded; keys and request exception URLs never enter reports.
Both optional sources skip subtree-only audits. Their data is never blended
with native Qt metrics.

Sources: [web-vitals](https://github.com/GoogleChrome/web-vitals),
[CLS session windows](https://github.com/GoogleChrome/web-vitals/blob/main/src/lib/LayoutShiftManager.ts),
[Lighthouse configuration](https://github.com/GoogleChrome/lighthouse/blob/main/docs/configuration.md),
[CrUX API](https://developer.chrome.com/docs/crux/api/).
