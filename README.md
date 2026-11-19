# GT practice repo: labelled Enron data and decision-model calculations

A reproducible snapshot of the labelled email dataset, JEV and Gemma notebooks, Gemini Decision 1 comparison, and calculation code from [kariato/GTPracticum](https://github.com/kariato/GTPracticum). The source checkout was at commit `fe537a0d3a9160cc6806196659de8b0820645bb8`. Completed experiment outputs that were ignored in the original repository are included here so offline evaluation works after cloning. `SOURCE_MANIFEST.json` records the source files, byte sizes, and SHA-256 hashes; `ORIGINAL_README.md` preserves the original usage notes.

For a complete explanation of calibration, including the motivation, validation sampling, equations, fitting algorithm, worked example, metrics, threshold tradeoffs, and reproduction steps, read the [dedicated calibration guide](calibration/README.md).

## What is being classified?

Label **1** means the email substantively discusses or documents Enron accounting irregularities: misleading financial reporting, improper mark-to-market valuation, hidden losses, or misuse of special-purpose entities. Label **0** means unrelated or routine financial/accounting content without a substantive irregularity concern. A positive label indicates relevance for review, not proof of misconduct.

The broad benchmark includes relevant third-party news and allegations. Gemma's separate exclude-news experiment deliberately changes that policy. Its metrics against the original labels therefore answer a different question. The `news_label` annotations are based on rules and reviewed exceptions, not a blinded independent gold standard.

## Included data and artifacts

| Path | Contents |
| --- | --- |
| `data/enron_labeled_curated_train.csv` | 2,236 labelled emails, 318 positive; columns `email`, `label` |
| `data/enron_labeled_curated_test.csv` | 559 held-out emails, 73 positive and 486 negative |
| `data/enron_labeled_curated_test_with_news.csv` | Test emails with auditable news annotations |
| `data/enron_labeled_curated.zip` | Original curated dataset archive |
| `data/*test_predictions.csv` | Historical decisions, scores where available, settings/input hashes, and usage metadata |
| `data/*probability_validation.csv` | Scores on the separate 500-email calibration sample |
| `data/gemma4_probability_test.csv` | One-token Gemma scores on all 559 test emails |
| `data/confidence_comparison/` | Calibrators, raw/calibrated per-email scores, metrics, and SVG charts |
| `data/gemma4_reasoning_recovery_attempts.jsonl` | Recorded successful and failed recovery attempts |
| `reports/` | Original performance, cost, ensemble, and Gemini comparison reports |
| `calibration/README.md` | Original detailed calibration explanation with a worked email example |

`source_row` is a zero-based row index in the relevant train or test CSV, not a global email ID. Join test outputs to test data and validation outputs to training data. The validation manifest specifies the selected training rows. Preserve input text and line endings: historical predictions sometimes hash CRLF text, and the supplied loaders explicitly check the historical variants. No raw mailbox corpus, local credentials, or model weights are needed for replay.

The curated labels are inherited from the original project; they are not newly adjudicated here. `labeling_v2.ipynb` preserves the original labelling workflow for inspection. It is a historical notebook with additional source-data and package requirements, rather than a clean-room recipe for independently establishing ground truth. Some older notebook paths refer to exploratory artifacts outside this focused snapshot.

## Notebooks and code

| Notebook | Purpose |
| --- | --- |
| [JEV classifier](EDA/jev_openrouter_classifier.ipynb) | Structured decision requests and evaluation |
| [JEV results](EDA/jev_results_eda.ipynb) | Trace probability, threshold, confusion matrix, and errors |
| [Gemma classifier](EDA/gemma4_openrouter_classifier.ipynb) | JSON label/source/reason classification, include/exclude news |
| [Gemma precision and recall](EDA/gemma4_precision_recall_eda.ipynb) | Offline confusion matrices, error review, and news-policy analysis |
| [Reasoning disabled](EDA/gemma4_no_reasoning.ipynb) | Separate include-news JSON run with reasoning disabled |
| [Reasoning options](EDA/gemma4_reasoning_options.ipynb) | Historical and recovered explicit-reasoning results |
| [Confidence calculations](EDA/jev_gemma4_confidence.ipynb) | One-token scores, calibration, reliability, and threshold selection |
| [All-runs comparison](EDA/jev_gemma4_all_runs_comparison.ipynb) | Historical comparison across workflows |
| [Gemini Decision comparison](EDA/gemini_decision_comparison.ipynb) | Added offline notebook that verifies saved inputs and recomputes all three score workflows |

The original Gemini experiment is implemented in `scripts/gemini_decision_comparison.py`; the added notebook wraps its saved evidence for offline review. Core implementations are `scripts/jev_openrouter.py`, `scripts/gemma4_openrouter.py`, `scripts/confidence_comparison.py`, and `scripts/evaluate_confidence.py`. These classify with hosted models; they do not fine-tune model weights.

## How raw decisions and probabilities are calculated

### JEV and Gemini Decision 1

JEV requests `typesafe/jev-1.13` through OpenRouter's structured decisions endpoint. The `QUESTION` constant in `scripts/jev_openrouter.py` contains the exact instructions and true/false criteria. Gemini Decision 1 requests `google/gemini-decision-1` with the same question. Both use the numeric `answers.relevant.noul` response as the positive probability `p` and predict `1` when `p >= 0.5`, otherwise `0`.

The email character cap is 20,000; the saved test runs have no truncated inputs. Each output stores the original email's SHA-256, a configuration fingerprint, label, model, decision, probability, and available request usage. These fields allow the replay code to reject mismatched inputs or settings. The returned probability is supplied by the API; this repository does not reconstruct the proprietary model's internal probability calculation.

### Gemma JSON classification

The JSON workflow requests `google/gemma-4-26b-a4b-it`, asking for a discrete label, source type, and short reason. That label is the prediction. A text explanation or discrete label is not a numeric probability, and these runs cannot be calibrated or thresholded as if they contained token scores.

Historical default runs omitted a reasoning setting. The disabled run explicitly requests `reasoning.enabled=false`. The recovered enabled run combines 214 historical successes and 345 recovered predictions, with temperature 0, seed 2 on new requests, varying token budgets, and a special repetition-penalty retry for one difficult row. It is a recovery workflow, not a controlled uniform-setting reasoning experiment. See the original README and recovery journal for provenance and cost limitations.

### Gemma one-token probability score

This separate prompt asks for exactly `0` or `1`, includes relevant news, disables reasoning, sets temperature 1, top-p 1, one output token, and requests token log probabilities from Darkbloom. Let `l0` and `l1` be log probabilities of the exact digit tokens. The positive score is:

```text
m = max(l0, l1)
p = exp(l1 - m) / [exp(l0 - m) + exp(l1 - m)]
prediction = 1 if p >= 0.5 else 0
```

This is the probability normalized over those two tokens. It is not necessarily calibrated to empirical relevance. Both alternatives must be present; a missing alternative is recorded as missing rather than zero. Decisions use the score, not the sampled output token. All 1,059 saved validation/test calls returned both alternatives and reported zero reasoning tokens.

## Calibration and threshold selection

`inputs()` in `scripts/confidence_comparison.py` normalizes whitespace, groups duplicate training emails, excludes conflicting-label groups and exact test overlap, and draws 500 of the remaining 2,097 unique eligible emails with seed `20261001`. The saved sample contains 67 positives. Near-duplicate articles and threads are not removed.

A separate sigmoid calibrator is fit for JEV and Gemma using only those validation emails:

```text
p_clip = clip(p, 1e-12, 1 - 1e-12)
x = log(p_clip / (1 - p_clip))
z = a*x + b
q = sigmoid(z) = 1 / (1 + exp(-z))
loss = sum[log(1 + exp(z_i)) - y_i*z_i] + 0.5*a^2
```

The fixed L2 penalty applies only to slope `a`. Newton iterations start at `(a,b)=(1,0)`, use a Hessian with a small numerical stabilizer, halve steps if loss rises, and stop at a step below `1e-8` or 100 iterations. Nonpositive fitted slopes are rejected. Approximate fitted parameters are JEV `(0.833, -0.391)` and Gemma `(0.203, -2.235)`; exact values live in `data/confidence_comparison/evaluation.json`.

For example, Gemma test row 2 has raw probability about 0.950. Its logit is about 2.949; applying the fitted slope/intercept gives about -1.637, whose sigmoid is about **0.163**. Its gold label is 0. Calibration lowers its score below the 0.5 decision cutoff.

The ordinary calibrated prediction is `q >= 0.5`. Predicted-class confidence is `max(q, 1-q)`; it is distinct from positive-class probability. The alternative F1 operating threshold is chosen from unique **validation** scores, maximizing F1, breaking ties by higher precision then higher threshold, and then applied unchanged to test. Gemini is uncalibrated in this experiment. A positive sigmoid mapping preserves ranking except for possible clipping ties; calibration changes the interpretation of scores and the operating point.

## Evaluation formulas

Against gold labels, TP and TN are correct positive/negative predictions; FP are false alerts and FN are missed positives. Predictions at the threshold use `>=`.

```text
precision   = TP / (TP + FP)
recall      = TP / (TP + FN)
accuracy    = (TP + TN) / N
specificity = TN / (TN + FP)
FPR         = FP / (FP + TN)
F1          = 2*TP / (2*TP + FP + FN)
alerts      = TP + FP
Brier       = mean((p - y)^2)
log loss    = -mean(y*log(p) + (1-y)*log(1-p))
```

The score implementation clips probabilities to `[1e-15, 1-1e-15]` for log loss. ROC AUC is the fraction of positive/negative pairs correctly ordered, awarding half credit for ties. Average precision sums `(recall_new - recall_old) * precision_new` as the threshold descends through distinct scores, grouping ties. Ten-bin ECE is `sum(n_bin/N * abs(mean_probability - positive_fraction))` using equal-width bins; 1 is included in the final bin. Reliability plots show those bin means. The report code uses 95% Wilson intervals with `z=1.959963984540054` for proportions.

### Saved raw-score results at 0.5

| Workflow | TP | FN | FP | TN | Precision | Recall | F1 | Recorded test API cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| JEV | 51 | 22 | 24 | 462 | 68.0% | 69.9% | 0.689 | $0.01853 |
| Gemma one-token score | 67 | 6 | 74 | 412 | 47.5% | 91.8% | 0.626 | $0.01358 |
| Gemini Decision 1 | 55 | 18 | 34 | 452 | 61.8% | 75.3% | 0.679 | $0.03546 |

These compare workflows with different prompts/settings and historical run dates. They do not isolate model architecture effects. Gemma's larger alert queue trades more false alerts for fewer missed positives. Exact saved metrics and ranking scores are in `data/gemini_decision_comparison.json`.

## Cost, review workload, and ensembles

Recorded API cost is the sum of available per-request `cost` fields; it excludes human review and unrecorded failures. Recovery journals include recorded failed attempts, but some earlier interrupted costs are unknown. Historical prices are not current vendor quotes.

The original report's sensitivity scenarios use email volume `V`, assumed positive prevalence `r`, test recall `R`, and false-positive rate `F`:

```text
true alerts  = V*r*R
false alerts = V*(1-r)*F
total alerts = true alerts + false alerts
review hours = total alerts * minutes_per_alert / 60
review cost  = review hours * hourly_rate
API estimate = V * recorded_test_API_cost / 559
```

The example assumptions are 100,000 monthly emails, three minutes per alert, and $60 per reviewer hour. Holding recall/FPR constant as prevalence changes is a scenario assumption, not a measured production forecast. The fixed ensemble averages JEV and Gemma calibrated probabilities 50/50; operating cutoffs are selected on validation data for recall targets. Detailed ensemble and review-capacity calculations are preserved in `scripts/email_monitoring_analysis.py` and `reports/email_monitoring_final_report.md`.

## Reproduce offline

Use Python 3.10 or newer. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m scripts.evaluate_confidence
python -m scripts.email_monitoring_analysis
jupyter lab
```

Run `EDA/gemini_decision_comparison.ipynb` to verify and recompute the three-model score comparison without a key. The supplied confidence and report scripts also run offline. Historical labelling notebooks may need additional packages and source artifacts beyond the replay dependencies. Saved notebook outputs are historical; recompute from the included CSVs for verification.

For new hosted classifications, set `OPENROUTER_API_KEY` locally in the Jupyter process environment. The original classifier notebooks and `python -m scripts.confidence_comparison --collect` can make billable requests. `python -m scripts.gemini_decision_comparison` runs the original resume workflow; it loads an API key even when all predictions are already saved, so use the offline notebook for key-free replay. Availability of historical model IDs/providers is not guaranteed. Never commit an API key or `.env` file.

## Interpretation and provenance

The benchmark's positive rate is about 13%; calibration does not automatically transfer to a different email population. Labels contain known questionable cases, exact deduplication does not remove related threads, and this test set was inspected during exploratory development. Fresh operational labels are required for confirmatory performance and threshold selection. A changed prompt, model, provider, or score setup requires revalidation and usually recalibration.

This is a focused copy of project artifacts, not the original Git history. Original attribution and dataset provenance remain with the source project and Enron corpus; no new license or independent rights grant is asserted by this snapshot. See `data/enron_raw_source.json` for the original corpus source metadata.

## Snapshot verification

Verified on 19 November 2026: all 61 copied source artifacts match their recorded SHA-256 hashes; offline calibration, six-run report/ensemble analysis, and the added three-model decision notebook completed successfully. The decision notebook checks recomputed metrics against the original saved comparison. All 15 inherited unit tests passed. No live model requests were made during this verification.
