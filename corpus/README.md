# Calibration corpus

Thresholds moved without data are just a different arbitrary number. This is the
data: text with a known author, so a score can be checked against an answer.

## Labels

`model` — written by a language model. Every entry here was generated as part of
building this corpus, so the label is true by construction, not by judgement.

`human` — written by a person before language models were writing product copy.
Provenance is recorded per entry. Where it is documentation rather than
marketing, the entry says so: register matters to this detector, and a corpus
that only holds one register will calibrate for one register.

`unlabelled` — real strings from a real product, kept separate on purpose. Their
author is not known to whoever assembled this file, and guessing would put a
guess into the ground truth, which is the one place a guess must not go.

## Sources

Every entry records where it came from. Three kinds of source are in here, and
they are not interchangeable:

`locale` — interface strings from the xFormat product (`en.json`, `it.json`,
`uk.json`). These are button labels and field names: the Italian median is 7
words. They are the right negatives for the question "does the detector flag a
menu", and the wrong ones for "does it flag a person's prose".

`documentation` / `product copy` — longer human writing, kept because register
matters to this detector and a corpus holding one register calibrates for one
register.

`encyclopedic` — paragraphs taken verbatim from Wikipedia in all three
languages, each at a named revision from 2018 (a few from 2017), years before
language models were writing this kind of copy. The source field carries the
article, the revision id and the revision date, so the claim "a person wrote
this, and it is dated" is checkable rather than asserted. This text is CC BY-SA;
it is quoted here with attribution, and it is measurement material, not product
content.

`promotional` — `promotional.jsonl`, 466 paragraphs from dated Wikivoyage
revisions (2020-2021) in the three languages. A travel guide is marketing
writing by function: the prose exists to make a place sound worth the trip,
which is the register a cliché list is likeliest to collide with and the one
register this corpus had none of. Same MediaWiki provenance as the
encyclopedic half — article, revision id, revision date — and the same CC
BY-SA terms.

It paid for itself the day it existed. Four human paragraphs were being
reported: `un vero e proprio` (it), `exceptional` and `innovative` (en), and
the Italian structural pattern `non solo X ma anche Y`, which had been added
as the twin of the English "not just X but Y" and is in fact a correlative
conjunction — ordinary grammar, 0 model entries in the whole corpus against 2
human ones. All four removed after counting both sides; held-out recall
unchanged (en 11/20, it 4/11, uk 10/14), false alarms on that register 4 → 0.

## What is missing, and why it is not filled in

**Negatives that argue rather than describe — measured 2026-08-31.**
`promotional.jsonl` fills this: 466 paragraphs of human travel writing, the
register that persuades rather than explains. It is a yardstick and not part
of `labelled.jsonl`, for the reason the section below gives.

**Positives that were not written for this file.** Every `model` entry was
generated while building this corpus. The label is true by construction, but so
is the distribution: it is how a model writes when asked to write for a corpus,
not how generated copy looks in a shipped product.

This is the half that stays open, and it is worth being exact about what it
blocks. A phrase's **cost** is now measurable in every register a scan meets;
its **benefit** is not, for phrases that only occur in the wild. Measured
2026-08-31: the five phrases a model judge named on a live Italian hotel page
— `atmosfera senza tempo`, `ogni angolo racconta`, `nel cuore di`, `le tre
anime` — occur **zero** times among the corpus positives, so nothing here can
say what adding them would catch. Closing that needs generated marketing copy
whose author confirms it, which is a person's answer and not a fetch.

**The unlabelled pool.** `unlabelled.jsonl` holds real strings whose author is
not known to whoever assembled this file. Guessing would put a guess into the
ground truth, which is the one place a guess must not go, so they stay out of
every number until someone who knows confirms them.

## Half of this file is a detector

`EmbeddingDetector` scores by nearest-neighbour margin against these entries, so
the corpus is a *component* of it as well as the yardstick it is judged by, and
the two roles pull opposite ways. Measured 2026-08-31: adding 95 correct human
paragraphs raised the human side of the margin from 0.461 to 0.541 and dropped
the score on an unchanged AI passage from 0.590 to 0.549. The corpus got better
and the detector got worse.

So the halves have jobs, decided by a hash of the text in `corpus_split.py`:

* the **tune half** is the only part that detector is allowed to read;
* the **held-out half** is the only part any number about it may be measured on.

A hash rather than a position, so an entry added today lands in one half and
stays there instead of moving an existing entry across the line and quietly
restating every number measured before it.

Two consequences worth knowing before editing this file:

* **A corpus change is a detector change.** Re-run
  `python scripts/calibrate.py --detector embedding --holdout --sweep` after
  adding entries; the threshold in `detectors/embedding.py` is a measurement,
  not a preference.
* **The whole-corpus number for such a detector does not exist.** Asked for one,
  the script refuses: read whole, the corpus separates itself almost perfectly
  (model 0.73-0.79 against human near 0.16) and every point of it is
  self-recognition.

## `foreign.jsonl` - the other side of the language question

257 paragraphs of human text in five languages this tool has **no** lists for
(German, French, Spanish, Polish, Russian), from dated 2018 Wikipedia revisions
with the revision id in `source`. Rebuild it with
`python scripts/fetch_foreign_corpus.py corpus/foreign.jsonl`.

No detector reads this file. It is a yardstick only, and it answers a question
the three-language corpus cannot ask: what the tool does with a page it was
never calibrated for. Two of the numbers it produced on 2026-08-31:

* the wording pass returned a span for **all 257**, every score pinned at 0.32
  by the statistical-only clamp - silent, but by three thousandths, not by
  decision;
* the embedding detector crossed its threshold on **five** of them, which was
  not silent at all.

Both now return nothing outside `supported_languages`, and
`tests/test_foreign_corpus.py` holds the count.

## `prose.jsonl` - human writing about what a scan is pointed at

334 human paragraphs in English, Italian and Ukrainian, from dated Wikipedia
revisions, on the subjects the tool is actually aimed at: tourism, software,
usability, marketing, cloud computing, Renaissance architecture. Rebuild with
`python scripts/fetch_prose_corpus.py corpus/prose.jsonl`.

Why it is separate from `labelled.jsonl`, and why that separation is the
point: this file is a **yardstick only**, and merging it would make it a
component of `EmbeddingDetector` instead - see the section above. No detector
reads it.

It answers a question the human half of `labelled.jsonl` cannot ask. That half
is interface strings plus encyclopedic paragraphs about the web, so
"0 false alarms" was measured on text nobody scans. Measured 2026-08-31, the
first time this file existed: **six** of these paragraphs were reported, on
`nuove possibilità`, `integrazione`, `additionally,`, `в епоху`, `крім того,`
and `феномен` - words an article about productivity or cloud computing is
simply written in. Seventeen cliché entries were retired, held-out recall did
not move, and `tests/test_prose_corpus.py` holds the zero.

## `negative_pool.jsonl` - the shortest register there is

292 human interface lines from the xFormat product in English, Italian and
Ukrainian: buttons, menu items, form labels, validation messages, empty
states. Every entry carries its source (`UI navigation`, `UI form`, …) and its
register, because "0 false alarms" is a claim about a register and an entry
that does not name one cannot support it.

It is a **yardstick only**, for the same reason as `prose.jsonl`, and for one
more that is specific to it: **no entry here reaches five words** — the
longest is four. `EmbeddingDetector` refuses anything shorter than five, so
merging this file into `labelled.jsonl` would hand that detector nothing it
can read while restating every ratio measured on that file, and would make
these lines a *component* of the detector meant to judge them.

Measured 2026-09-01, held by `tests/test_negative_pool_corpus.py`: **0 of
292** cross the reporting threshold in the wording pass, and the embedding
pass returns no span at all. This is the register where a cliché list is
cheapest to break silently — one wrong entry flags the menu on every page of
a site at once.

## Running it

    python scripts/calibrate.py                 # metrics at the current bands
    python scripts/calibrate.py --sweep         # every threshold, side by side
    python scripts/calibrate.py --review        # the unlabelled pool, ranked

    # a detector built out of this file: the held-out half is the only number
    python scripts/calibrate.py --detector embedding --holdout --sweep

## `audit/verdicts.jsonl` - checked verdicts on site-audit findings

Everything above is about the text detectors. This file is about the audit
rules (accessibility, SEO, performance, security), which had no corpus at all:
each new rule produced false positives on its first real crawl, and a person
found them by reading the output. A verdict records what that person decided,
so the rules can be held to it by `tests/test_audit_verdicts.py`.

One JSON object per line; `audit/verdicts.py` loads and replays it. In a
folder of its own on purpose: every `corpus/*.jsonl` is read as text samples
by `validation/corpus.py`, and a verdict is not one.

- `verdict: true` - a real defect. The rule must report it at its own weight:
  its declared severity and confidence, not lower.
- `verdict: false` - a false positive or a near miss. The rule must stay
  silent, or lower itself to a note (a lighter severity or confidence).
- `engine` - `static` replays `html` through `analyze_document` (with
  `syntax` and `stacks` when the rule needs them); `htmlcs` replays an
  HTML_CodeSniffer `message`; `axe` replays an axe result (`payload`);
  `pages` replays several pages of one crawl (`pages: [{url, html}]`) for
  the rules that compare pages - translations, hreflang, duplicates.
- For an engine's own code (`axe:…`, `htmlcs:…`) "lowered" means its
  confidence was lowered: the engine sets the severity, and what this tool
  does with an answer it doubts is mark it uncertain.
- `source` - where the verdict came from: a named audit and task
  (`municipal site final audit, T-1961`) or `synthetic`, a shape written from the
  rule's own definition. Synthetic entries guard a rule's edges; only the
  named ones say anything about real sites.

Every serious or critical rule has at least one entry of each kind, and the
test fails when a new one is added without them.

Markup shapes only. No client's text, cookies, tokens, addresses or any other
personal data: a verdict is about the shape of the markup, and the shape is
all it needs. The test checks the file for the obvious kinds.
