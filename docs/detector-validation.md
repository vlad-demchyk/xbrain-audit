# Independent detector validation

The old `corpus/*.jsonl` files are historical regression material. Their
holdout has already been used to change rules and thresholds. It cannot
establish independent release quality. `scripts/calibrate.py` now says so;
its historical sweeps remain useful for diagnostics. Existing production
scores, thresholds and embedding reference selection are unchanged.

`scripts/benchmark.py` separates preparation, calibration and one locked test:

```sh
python scripts/benchmark.py inspect dataset.json
python scripts/benchmark.py partition unassigned.json --seed study-v1 --output dataset.json
python scripts/benchmark.py unicode dataset.json --output dataset-with-unicode.json
python scripts/benchmark.py freeze dataset.json --detector offline --output protocol.json
python scripts/benchmark.py run dataset.json --protocol protocol.json --output results.json
python scripts/gate.py --quality-report results.json
```

Outputs are new files, never overwrites. `run` exits 2 when measured quality
does not meet the declared requirements; malformed inputs exit 1. Without
an independent report, the release gate reports historical diagnostics and
fails readiness. The current Italian historical holdout recall is 4/11,
36.4%, below its existing 50% release floor. Missing groups also fail; the
English/Ukrainian aggregate cannot hide Italian. `--skip-quality` explicitly
skips this requirement and reports that only selected checks passed.

For a comparison, declare **all** methods and configurations before accessing
the shared test. For example, `methods.json`:

```json
[
  {"id": "offline", "detector": "offline"},
  {"id": "heuristic", "detector": "heuristic"},
  {"id": "ensemble", "detector": "ensemble", "config": {
    "members": [{"detector": "offline"}, {"detector": "heuristic"}],
    "weights": [1, 1]}}
]
```

This is a wiring example: `heuristic` currently resolves to `offline`, so those
two entries are the same predictor and their ensemble adds no independent signal.
Actual comparisons need distinct frozen models/configurations, chosen before test.

```sh
python scripts/benchmark.py freeze-comparison dataset.json --methods methods.json --output comparison.json
python scripts/benchmark.py run-comparison dataset.json --protocol comparison.json --output comparison-results.json
```

Every method calibrates before exposure. The ledger then claims each test text
once for the entire declared comparison. Permission/configuration failures in
preflight do not consume test; a failure after inference starts does. Reruns,
adding methods after exposure and refitting on exposed test text are rejected.
Every declared result must remain in the comparison, including weak/error
results. `validation.comparison.verify_comparison_report` checks membership,
ledger evidence, metrics and quality without trusting saved pass flags. Individual
member reports can be verified with `verify_report`; the release gate consumes
one such member report, not the comparison container. The container's quality
flag means every declared method passed, not that the best method was chosen.
Choosing a winner or changing weights after reading test results requires a new
independent test. This mode does not relax the prohibition on test-driven tuning.

## Dataset contract

The manifest is one JSON object with `schema_version: 1`, a `dataset_id`,
`purpose: validation` (or `fixture` for synthetic plumbing checks) and `samples`.
Each sample has:

* `id`, original `text`, `label` (`human`, `model`, `mixed`), `language`,
  `register`, `condition`, `split` (`reference`, `calibration`, `test`).
* `groups` with explicit `author_id`, `site_id`, `source_id`, `template_id`.
* `provenance` with `source`, `date`, `license`, `verified_by`, `evidence`, and
  an explicit boolean `public_benchmark`. Model/mixed samples also require
  `generator` with `name`, `model_version`, `prompt`, `date`.
* Optional `parents` sample IDs for edited/transformed/mixed lineage.
* `gold_spans`: original Unicode code-point `[start, end]` pairs, or null
  when unannotated. Human gold spans must be empty. Missing span annotation
  is unknown, never an invented whole-text ground truth.

Unknown authorship is not a human negative. Supplied provenance is a recorded
assertion requiring review, not automatic proof that a person wrote a text.
No existing unlabelled pool is relabelled. New labels require confirmed authorship.
Model generator/prompt/date fields are never guessed for historical examples.

Samples sharing any source-group field, parent or canonical duplicate belong
to one connected component and cannot cross partitions. Canonical identity
uses NFKC, case folding, whitespace and removal of format characters only for
leakage checks; input text and span offsets remain original. Partitioning is
deterministic under reordering. Adding/merging groups creates a new manifest
requiring review; existing split assignments are never silently rewritten.
The test must not overlap any historical corpus file. Semantic near-duplicate
and unknown pretrained-model contamination are not certified absent.

The `unicode` command derives fullwidth Latin, zero-width and NBSP formatting
variants from original samples. It retains supplied labels and group IDs,
records parent/transformation provenance and maps annotated spans to changed
code-point offsets. It does not create human ground truth or paraphrase/mixed
labels. Variants stay with their source partition and independent group count.

## Freeze and test access

Freeze scores only calibration. It chooses maximum recall under the declared
worst-case calibration FPR (including abstentions), or checks an explicitly
fixed threshold with `--fixed-threshold`. The measured test FPR is reported
as observed; no test sweep forces it to the target.

The frozen protocol hashes the complete dataset, individual test samples,
reference, model settings, source/prompt code, benchmark methodology and
dependency versions. Any change invalidates it. Test scores are not read
while fitting. The source-group guard and each original sample are rechecked
when consuming a saved report; its `passed` flag is not trusted.

Test text access is claimed atomically before inference in
`~/.xbrain-audit/validation/test-access`. A failed run still consumes the test;
refitting or a second run is refused. `XAUDIT_VALIDATION_LEDGER` points to
an isolated ledger for synthetic tests. Copying/renaming a protocol does not
reset exposure because keys identify canonical text, not filenames. This is
process protection on the current machine, not cryptographic attestation or
a cross-machine dataset registry.

## What is measured

Reports include confusion counts, FPR, conservative recall, conditional recall,
sample precision and precision projected to an explicitly stated prevalence,
macro-language recall, language/length/register/edit strata, coverage,
abstention/error counts, measured latency and known API cost. Missing cost
stays null. Mixed labels are excluded from binary authorship rates and use
annotated span localization. Character precision/recall and IoU merge overlapping
ranges before counting; unannotated or failed samples do not become zeros.

Nominal Wilson intervals assume independent Bernoulli observations. Reports
also count independent source groups, with separate group-event intervals:
any human false flag/abstention and all model passages detected. These group
events are not labelled document-level population FPR/recall. Repeating one
website's paragraphs cannot inflate independent group count. Sampling and
distribution assumptions still require review.

Default requirements are deliberately conservative readiness checks, not a
claim that the current tool meets them: all uk/it/en, all three length bands,
specified registers and editing conditions; recall >=50%, projected precision
>=90% at prevalence 10%, worst-case FPR <=1%, coverage >=95%, at least 30
samples per applicable class and 30 source groups. Group error upper bound
must also be <=1% and group detection lower bound >=50%. Zero errors on 20
samples does not establish a 1% FPR. Human marketing uses negative-only checks;
mixed content requires at least 30 annotated samples, IoU >=0.5 and coverage.
A policy JSON can declare a research scope, but cannot loosen release defaults.

## Benchmark adapters

The production adapters use offline/heuristic, embedding, direct Claude judge
and hybrid detectors. Production language guessing is used,
not the benchmark's gold language. Character findings are not AI-authorship
evidence. Unsupported lengths/languages abstain; detector failures are errors.
Embedding reads only the reference file and retains its production text-hash
selection within that file. It does not read calibration/test neighbours.

`ensemble` takes 2..12 explicitly configured components and positive finite
weights. It combines document ranking scores with a normalized weighted mean;
its threshold is selected only on calibration and all component snapshots are
frozen. An abstaining/error component makes the aggregate abstain/error; weights
are never renormalized over only successful components. Unknown API cost stays
unknown. This ranking is not an authorship probability and has no inferred span
localization. Remote components inherit the permission/public-text requirement.

`claude-legacy-prompt` is a benchmark-only counterpart to `claude-llm-judge`.
The archived prompt, response schema and numbered input format come exactly from
git commit `8f8914aa4408f303da37893257bd385923dfddaa`; its source SHA and explicit
prompt/schema hashes are recorded. Both variants use the current strict verdict
checker. Thus this compares the old/new request under the same evidence contract,
not the whole old backend with its former score coercion, omitted-block negatives
or unverifiable whole-block fallback. The archived variant is absent from the
production detector registry. Declare both with the same explicit model/effort
in a comparison before access; approved public benchmark calls still require
`--allow-remote`. Actual prompt quality has not been measured. Remote model
weights remain opaque, so neither request is a certified immutable model snapshot.

Additional benchmark adapters implement the following contracts. They do not
change the production detector or establish independent accuracy.

| Method | Input/configuration | Score and localization |
| --- | --- | --- |
| `multilingual-encoder` | Local Transformers sequence-classifier checkpoint; explicit `ai_class_index` and declared `languages` | AI-class softmax; no sentence localization. Language declarations need empirical validation. |
| `fast-detectgpt` | Local scoring/reference causal models with identical vocabulary/tokenization | Analytic conditional sampling discrepancy, higher means more AI-like. Bounded logistic ranking score, not an authorship probability. |
| `binoculars` | Local observer/performer causal models with identical vocabulary/tokenization | Performer next-token NLL divided by observer-to-performer cross-entropy. Lower raw ratio means more AI-like; bounded logistic of its negative. |
| `copyleaks` | `COPYLEAKS_ACCESS_TOKEN`, explicit `expected_model_version`, optional sensitivity 1/2/3 | `summary.ai` is separate from section confidence. Vendor character ranges have no verified Unicode unit/quote, so localization remains unknown. |
| `pangram` | `PANGRAM_API_KEY`, explicit `model` and `expected_model_version` | AI-generated fraction; AI-assisted fraction/evidence stays separate. Windows become spans only after exact-quote verification. |
| `gptzero` | `GPTZERO_API_KEY`, explicit `request_version`, optional expected observed version | `class_probabilities.ai`, with human/mixed kept separately. Provider sentence highlights require an exact unique quote. |

Local model settings use `model_path`, `scoring_model_path`/`reference_model_path`
or `observer_model_path`/`performer_model_path` according to method. Checkpoints
must already contain config, tokenizer and safetensors. No Hub downloads or
remote model code run. SHA-256 manifests cover artifacts before/after loading,
calibration and test. Dependency versions and source hashes are frozen too.
The loader requests `output_loading_info` and rejects missing/mismatched weights
or loading errors. A base encoder cannot acquire a randomly initialized classifier
head and still produce a benchmark score. Tokenizers/models are cached only after
every model, tokenizer alignment and post-load manifest have passed; a failed load
never leaves a partial cache for the next sample. Extra unused checkpoint keys
are permitted when all required model weights were loaded. A frozen file manifest
alone does not establish that a checkpoint is loadable or trained for authorship;
passive `capabilities` output still records `inference_checked: false`.
See [Transformers loading diagnostics](https://huggingface.co/docs/transformers/main_classes/model#transformers.PreTrainedModel.from_pretrained).
Missing artifacts abstain with no score. Token lengths outside `max_tokens`
(default 512) or model context abstain instead of truncating. Device defaults
to CPU; `mps`/`cuda` require explicit configuration. Tiny owned checkpoints in
tests exercise real inference; they are not trained authorship detectors.

On MPS, inference stays on the GPU and logits/labels/masks move to CPU for
float64 statistics. The transfer and cast are separate operations; a combined
MPS-to-CPU float64 conversion also fails on the tested PyTorch 2.13 runtime.
CPU/CUDA statistics retain float64 on their inference device. Checked predictions
record `inference_device`, `statistics_device` and `statistics_dtype`; latency
includes the transfer. `capabilities` reports actual MPS/CUDA availability.
An unavailable requested accelerator abstains before loading, without switching
to another device. Changing the declared device changes the frozen fingerprint;
CPU/MPS numerical agreement on tiny fixtures does not certify identical outputs
for every model. See [PyTorch MPS](https://docs.pytorch.org/docs/2.13/notes/mps.html)
and [Tensor.to](https://docs.pytorch.org/docs/2.13/generated/torch.Tensor.to.html).

Example classifier configuration, requiring a genuinely trained local model:

```json
{"model_path": "/absolute/path/to/frozen-classifier", "ai_class_index": 1,
 "languages": "uk,it,en", "device": "cpu", "max_tokens": 512}
```

The index and language scope must come from that classifier's documented label
mapping and supported languages, then be checked on independent data. A generic
multilingual encoder alone does not identify authorship. Published thresholds
for other model pairs, precisions or datasets are not imported. Select a
threshold on calibration; the frozen protocol records the exact configuration.

Remote inference requires both `--allow-remote` and exclusively declared public
benchmark text. Keys are read only from environment variables, never config or
reports. Copyleaks uses its synchronous writer detector and enforces its
255..100000-character range. Pangram uses asynchronous `POST /task`, then
`GET /task/{id}`, with `public_dashboard_link: false`. Task IDs are persisted;
pending tasks are polled again without another submission. An ambiguous POST
outcome leaves a submission marker requiring resolution, preventing an automatic
paid retry. Job cache defaults to `~/.xbrain-audit/validation/api-jobs`; override
with `XAUDIT_API_JOB_CACHE`. Request/poll timeouts are finite; polling is not a
strict whole-request wall-clock deadline. GPTZero uses `POST /v2/predict/text`.

Observed response versions/hashes are recorded separately from requested
versions. A configured expected version mismatch is an error with no score.
An absent observed version remains unknown. Opaque vendor weights are never
marked as a verified snapshot merely because a version string matches.
These remote reports and the existing embedding/judge/hybrid reports therefore
cannot pass release readiness. Unknown API cost stays null; usage credits or
word counts do not invent a USD charge. Local `cost_usd: 0` means no API billing,
not free hardware. Local HTTP tests verify requests and payloads without vendor
calls; they do not prove account authorization or current vendor behavior.

Provider-labelled AI spans are selected independently of the calibrated document
threshold. Fractions, class probabilities and assistance confidence are distinct
quantities. Unverifiable offsets, normalized/ambiguous repeated quotes and absent
localization are counted as unsupported, never as successful empty localization.

Primary API contracts: [Copyleaks request](https://docs.copyleaks.com/reference/actions/writer-detector/check),
[Copyleaks response](https://docs.copyleaks.com/reference/data-types/ai-detector/ai-text-detector-response),
[Pangram detection](https://docs.pangram.com/api-reference/ai-detection),
[Pangram models](https://docs.pangram.com/api-reference/models),
[GPTZero endpoint](https://gptzero.me/developers),
[GPTZero score interpretation](https://support.gptzero.me/articles/8947054519-how-do-i-use-and-interpret-the-results-from-your-api).
Research formulas were checked against [Fast-DetectGPT](https://github.com/baoguangsheng/fast-detect-gpt/tree/971b05202bac2bb504d60c0ac0812fea7a8f7c82)
and [Binoculars](https://github.com/ahans30/Binoculars/tree/c8ae2f90d50ee696418bc71d8d9e5020e5f9d7b8).

## Experimental availability and provenance

Inspect configuration and prerequisites without inference or downloads:

```sh
python scripts/benchmark.py capabilities
python scripts/benchmark.py capabilities --detector multilingual-encoder --config classifier.json
python scripts/benchmark.py capabilities --detector prossd --output capabilities.json
```

The command records adapter availability and actual runtime prerequisites,
not a readiness/accuracy certificate. Unknown methods and unsupported configuration
fail instead of silently running another detector.

[AdaDetectGPT](https://github.com/Mamba413/AdaDetectGPT/tree/ff83b52efd0d2f81afac1692d4ea0765658bb6e0)
was reviewed at that revision. Its upstream inference hard-codes CUDA and has
a sampling-model argument typo. A learned B-spline witness requires separate
training data; published pretrained coefficients belong to the author's setup.
No CUDA is available on the development host, and no frozen scoring/reference
pair and witness have been supplied. This is an assessed experimental method,
without an XBrain Audit inference adapter or measured target-language performance.

[ProSSD's paper](https://aclanthology.org/2026.acl-long.638/) links to its
[implementation](https://github.com/RuoChoXio/ProSSD/tree/988125b1bc11213314a5f10dd21cb4db75729625).
It needs an encoder, supervised `projection.npy` and reference style distributions;
a generic embedding distance is not equivalent. The reviewed implementation
uses spaCy `en_core_web_sm` POS tagging, so uk/it coverage is unverified. The
upstream library is pickled and has a training-derived threshold. Artifacts are
not supplied or loaded here. A future adapter must freeze reference-trained
artifacts and select its threshold on calibration. No quality result is claimed.

Anthropic's [official announcement](https://www.anthropic.com/news/claude-text-watermark),
updated 1 September 2026 and reviewed 14 October, confirms a private-preview
detection API. Approved access and an implemented endpoint contract are not
configured here. A general Anthropic API key is insufficient. The placeholder
fails before crawling even when a key/base URL is present. Capability output
places this under `provenance_signals`, outside classification methods and
their FPR/recall metrics. A watermark concerns Claude involvement; absence
does not prove human authorship or exclude another AI.

## Remaining validation

The command expects a supplied manifest with confirmed provenance. Synthetic
fixtures prove the pipeline contract, not detector accuracy. Fresh uk/it/en
authorship annotations, reference/calibration/test splits, real perturbation
strata and comparative measurements remain pending in T-64/T-1797. No external
provider inference was used to produce the implementation's test results.
New calibration does not silently
replace a production configuration; release consumption also checks the
current offline configuration and reporting threshold.

Statistical reference: [NIST confidence intervals](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
