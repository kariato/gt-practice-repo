# GTPracticum
Practicum for GT 

## Final project report

Read the [email monitoring cost and performance report](reports/email_monitoring_final_report.md)
for the executive overview, recommendations by operating need, measured results,
review workload and cost scenarios, JEV/Gemma ensemble feasibility, and the
proposed pilot acceptance criteria.
The [standalone HTML report](reports/email_monitoring_final_report.html) can be
downloaded from GitHub with **Download raw** and opened in a browser.
[Aggregate evidence and input hashes](reports/email_monitoring_metrics.json)
are included for technical review.

## Jev classifier

Open [the Jev notebook](EDA/jev_openrouter_classifier.ipynb) to classify the curated
Enron test emails with TypeSafe Jev through OpenRouter. Jev makes a structured
yes/no decision for each email; this workflow does not fine-tune model weights.
The existing test labels are used only for evaluation.

Set `OPENROUTER_API_KEY` in the environment that starts Jupyter. For example,
in PowerShell:

```powershell
$env:OPENROUTER_API_KEY = "your-key"
jupyter lab
```

Run the notebook from this repository or its `EDA` folder. It defaults to all
559 held-out emails and saves predictions to the ignored `data` directory.
Set `MAX_TEST_ROWS = 100` for a smaller random pilot. The output is saved after
each request, so reruns resume without repeating completed calls. An API key is
needed only for new requests; the completed evaluation can be reproduced from
the saved predictions without a key. OpenRouter requests may incur charges.

The [results EDA notebook](EDA/jev_results_eda.ipynb) replays the completed
evaluation offline. It traces a decision from input email to probability and
threshold, then examines the confusion matrix, probability distributions,
threshold sensitivity, and errors.

## Gemma 4 classifier

Open [the Gemma 4 notebook](EDA/gemma4_openrouter_classifier.ipynb) to run
`google/gemma-4-26b-a4b-it` on the same curated test emails through OpenRouter.
It saves each predicted label, source type, and short reason to a separate CSV,
then reports metrics and example errors. The notebook uses the same
`OPENROUTER_API_KEY` environment variable and resumes saved requests. Set
`MAX_WORKERS` from 1 to 10 for simultaneous API requests; the default is 10.

By default, its rule excludes third-party news articles from the positive
class, addressing the observed news-related false positives. This differs from
the Jev rule, which counts relevant news. Set `NEWS_POLICY = 'include'` in the
Gemma notebook to approximate the Jev label definition; the notebook writes
that run to a different CSV. Gemma produces a discrete label rather than
Jev's probability, so probability-threshold plots do not apply.

The [Gemma precision and recall EDA notebook](EDA/gemma4_precision_recall_eda.ipynb)
replays the saved predictions offline. It shows the confusion matrix, precision
and recall overall and by model-identified source type, Wilson intervals, and
false-positive and false-negative email excerpts. It also shows Jev's saved
metrics with the news-policy difference made explicit. Run
`python scripts/label_news.py` to regenerate
`data/enron_labeled_curated_test_with_news.csv`, which adds an auditable
`news_label` and `news_label_basis` to the 559-email test set without changing
its accounting labels. The publication label uses text rules plus reviewed
exceptions and is an audit aid, not a blinded gold standard.

For recall on the original labels, the completed `NEWS_POLICY = 'include'`
Gemma run finds 67/73 positives (0.918 recall). The exclude-news run finds
19/73 (0.260 recall) on the original labels because 53 of its 54 false
negatives are annotated news. On annotated non-news, its recall is 19/20
(0.950); the remaining case is a university accounting job description that
appears mislabeled in the curated set. The EDA notebook compares the two
news-policy runs.

### Gemma with reasoning disabled

[The additional experiment](EDA/gemma4_no_reasoning.ipynb) sends
`reasoning: {"enabled": false}` with the same include-news prompt and 559
historical email inputs. It verifies the saved input hashes, including the
historical CRLF line endings, and starts with a one-email pilot. Predictions
and metrics use separate `gemma4_include_no_reasoning_*` files. The CSV records
reported reasoning tokens, whether reasoning was returned, provider, and request
latency including retries. Missing reasoning telemetry is unknown, not zero.
The configuration fingerprint prevents resuming a different reasoning setting.

Set `OPENROUTER_API_KEY` in the Jupyter environment and run the notebook. It
compares precision, recall, F1, errors, cost, and changed predictions against
the saved Gemma include-news run and JEV. Historical Gemma requests omitted the
reasoning setting, so their reasoning status is unknown; this experiment does
not establish a controlled reasoning-on versus reasoning-off comparison.

### Explicit reasoning option

[The reasoning options notebook](EDA/gemma4_reasoning_options.ipynb) adds
`REASONING_MODE = 'enabled'`, alongside `'disabled'` and `'default'`. It uses
`reasoning: {"enabled": true}` and a 8,192-token total output cap to leave room
for thinking and the classification. Enabled means the provider's default
thinking level; it is not an explicit high-effort setting. The 350-token cap
is retained for historical/default and disabled runs, and the cap is included
in the configuration fingerprint when changed. Comparisons must account for
this difference in output allowance.

The notebook loads `OPENROUTER_API_KEY` from the environment or the local,
Git-ignored `.env`, verifies historical inputs, checks pilot rows for
reported reasoning, and saves the enabled run to
`data/gemma4_include_reasoning_enabled_8192_test_predictions.csv`. It compares
complete runs against disabled reasoning, historical defaults, and JEV.
The original Gemma classifier notebook also exposes these three options.

Live validation on October 1 found that explicit reasoning does generate
thinking tokens, but source row 112 exhausted both 4,096- and 8,192-token caps
without an answer. That original run was incomplete; the recovery workflow below now provides
all 559 predictions while retaining the historical results.
Partial prediction costs exclude failed and interrupted requests and must not
be compared with the complete-run totals. Classifier failures now cancel queued
requests while preserving successful responses already in flight.

### Confidence scores: JEV and Gemma with reasoning disabled

[The confidence notebook](EDA/jev_gemma4_confidence.ipynb) compares raw and
calibrated probabilities on the same 559 test emails. It fits a separate sigmoid
calibrator for each model on 500 randomly selected training-file emails, after
removing whitespace-normalized duplicates and overlap with test emails. The
sample manifest is saved in `data/confidence_validation_manifest.json`.

Gemma uses a new label-only prompt, reasoning disabled, temperature 1, top-p 1,
one output token, and `logprobs`/`top_logprobs` from Darkbloom. It normalizes the
probabilities of the exact `0` and `1` tokens. The decision is computed from the
score, not the sampled token. Both label probabilities must be present; missing
alternatives are recorded as missing, never zero. This differs from the previous
JSON label/source/reason classifier. All 1,059 recorded Gemma calls returned both
label probabilities and reported zero reasoning tokens. JEV uses its native
probabilities; its existing test predictions are reused.

Run `python -m scripts.confidence_comparison --collect` to resume collection,
and `python -m scripts.evaluate_confidence` for offline evaluation (NumPy is
required). Results, calibrators, per-email probabilities, and SVG figures are
saved under `data/confidence_comparison/`. The notebook includes probability
error, reliability plots, precision–recall curves, costs, and test performance
at thresholds selected on validation data. Data outputs remain Git-ignored.

For a new email, call
`predict_with_confidence(email_text, model='gemma4')` or use `model='jev'`, imported
from `scripts.confidence_comparison`. This makes an API call using the local key
and returns `raw_probability`, calibrated `probability`, `prediction`, and
`predicted_class_confidence`. Calibration reflects the curated dataset's class
balance and does not guarantee confidence accuracy on a new email population.
Near-duplicate threads and articles are not removed, and the test set was
previously inspected; fresh data is needed for a confirmatory comparison.

### Recover failed reasoning requests

The current [reasoning notebook](EDA/gemma4_reasoning_options.ipynb) reads the
recovery results offline by default. Run
`python -m scripts.gemma_reasoning_recovery --pilot` to retry the previously
failing row 112, then `python -m scripts.gemma_reasoning_recovery --run` to
process missing rows. Previously successful predictions are verified and reused.
Recovery keeps reasoning enabled, temperature at 0, and generation seed at 2,
with the original top-p/top-k defaults. Historical successful rows had no explicit
seed and are retained with that provenance. Truncated responses have a bounded token-cap schedule
of 4,096, 8,192, and 16,384; exhausted retries remain explicitly unresolved.

Each attempt is journaled with cost, request ID, token usage, and settings.
Successful responses persist immediately. The combined CSV records provenance
and configuration per row; temperature remains 0 throughout, but token caps may vary by row, so it
must not be presented as one uniform-cap reasoning experiment.
The original prediction files are preserved. Recovery costs include recorded
failed responses; earlier interrupted costs are not fully known.

Recovery completed on October 1: 214 historical predictions were preserved and
345 missing rows were recovered, with temperature 0 and seed 2 on every new
request. After the normal cap schedule, a bounded Darkbloom retry with repetition
penalty 1.1 resolved row 112; the penalty and requested provider are recorded per
row. All 559 final responses reported reasoning usage. Recovery cost $0.062392,
including 4 failed responses across 349 attempts. Historical rows had no explicit
seed. The completed notebook reports the combined metrics and those limitations.

The [all-runs comparison notebook](EDA/jev_gemma4_all_runs_comparison.ipynb)
also has a [standalone HTML export](EDA/jev_gemma4_all_runs_comparison.html)
with its saved tables and chart.
