# Inkling 2 Mini: detailed performance, reasoning, cost, and reliability report

**Contents**

- [1. Findings and decision implications](#1-findings-and-decision-implications)
- [2. What was measured](#2-what-was-measured)
- [3. Classification results](#3-classification-results)
- [4. Paired changes across reasoning levels](#4-paired-changes-across-reasoning-levels)
- [5. API cost and token accounting](#5-api-cost-and-token-accounting)
- [6. Reliability, retries, and incomplete results](#6-reliability-retries-and-incomplete-results)
- [7. Latency and response shape](#7-latency-and-response-shape)
- [8. Interpretation boundaries](#8-interpretation-boundaries)
- [9. Recommended next experiment](#9-recommended-next-experiment)
- [10. Reproducibility and artifact inventory](#10-reproducibility-and-artifact-inventory)

**Report date:** 22 November 2026. **Experiment:** zero-shot Enron email classification through OpenRouter. **Status:** completed initial sweep at all six efforts, followed by one same-settings retry for each initially failed email. **Evidence:** 3,364 billable Inkling requests, 3,353 complete classifications, two historical Gemma workflows, and a hash-verified 559-email benchmark.

Companion documents: [prompt and labeling audit](inkling_prompt_and_labeling_audit.md), [aggregate evidence and input hashes](inkling_reasoning_evidence.json), and [short comparison](inkling_reasoning_comparison.md). The detailed label audit explains why agreement with the curated labels is not equivalent to correctness under a settled business policy.

## 1. Findings and decision implications

Inkling demonstrates a useful precision–recall tradeoff on this task. Every evaluated Inkling setting has higher measured precision and F1 than both historical Gemma JSON classifiers. Every setting also finds fewer curated-positive emails than either Gemma baseline. That combination is consistent with a more selective decision rule; it is not evidence of unconditional superiority or inferiority.

For Inkling itself, reasoning off has the highest recall, lowest recorded cost, shortest median request latency, and no request failures. Max has the highest observed F1 among complete Inkling settings and a smaller review queue, at roughly 3.57 times the cost of off. High/max sometimes spend the entire output allowance on reasoning and return no classification. Those failures and their charges belong in the comparison.

Only 21 emails change labels across the six efforts. Seventeen have curated label 0 and four have label 1. Fifteen of those 21 change direction more than once as effort increases. The evidence therefore does not support a monotonic claim such as “more reasoning is more accurate” or “more reasoning always makes the model more conservative.” The substantive explanations repeatedly turn on the threshold between investigative relevance and an explicit allegation of accounting misconduct.

**Operational interpretation:** keep the historical Gemma workflow as the higher-recall reference while policy and labels are adjudicated. Inkling off is the lowest-cost Inkling candidate for a separate validation experiment; Inkling max is a candidate when fewer false alarms and higher F1 matter more than the observed loss of relevant emails. Do not select a production setting solely from this repeatedly inspected test set.

## 2. What was measured

### 2.1 Task and population

The task is to identify substantive evidence or discussion of Enron accounting irregularities, misleading financial reporting, improper mark-to-market valuation, concealed losses, or misuse of special purpose entities. The include-news rule counts relevant third-party reports and allegations. It excludes routine financial business and accounting disputes about unrelated companies.

This is a discrete JSON classifier with a label, source type, and short reason. It is not the repository's separate Gemma label-token probability workflow, and its results must not be mixed with that workflow's calibration, average precision, or threshold studies. No numeric confidence score was collected in this experiment. Neither a precision–recall curve nor “precision at equal recall” can be reconstructed from these binary labels alone.

| Property | Observed value / interpretation |
| --- | --- |
| Test emails | 559 rows, of which 73 are positive and 486 negative |
| Positive prevalence | 13.06%; an evaluation-set property, not an estimate for production |
| Unique exact email texts | 554; five duplicate pairs, including one pair with conflicting labels |
| Largest / median input | 2,970 / 1,407 characters after historical line-ending alignment |
| Character limit | 20,000; no input reached it and no email was clipped |
| Missing material | Some emails reference attachments or articles not present in the supplied text |
| Label usage | Evaluation only; labels and prior predictions were not sent to the classifier |
| Index convention | source_row is the zero-based index of a CSV data row, excluding the header |

### 2.2 Models and reasoning controls

Inkling uses `thinkingmachines/inkling-2-mini`; the Gemma reference uses `google/gemma-4-26b-a4b-it`. The frozen OpenRouter catalog snapshot describes Inkling as an open-weight multimodal mixture-of-experts model with a looped architecture and a 1,048,576-token context. Gemma's advertised context is 262,144 tokens. These architectural and context differences did not bind this experiment: the inputs were short text emails, no images were used, and no local-weight deployment was tested.

The snapshot exposes Inkling efforts `none`, `minimal`, `low`, `medium`, `high`, and `max`, with reasoning enabled by default and default effort high. Gemma exposes reasoning enabled/disabled, without an enumerated effort selector. The experiment explicitly supplied every Inkling effort rather than relying on the default. It does not assume that an effort name corresponds to the same reasoning budget or training behavior across models.

Sources: the [OpenRouter Inkling listing](https://openrouter.ai/thinkingmachines/inkling-2-mini/), [Gemma listing](https://openrouter.ai/google/gemma-4-26b-a4b-it), and [catalog API](https://openrouter.ai/api/v1/models). Catalog descriptions and rates in the committed evidence are a dated snapshot, not a promise about current routing or future prices. General benchmark rankings were not used to grade these emails.

### 2.3 Inkling request configuration

| Setting | Value |
| --- | --- |
| Temperature | 0 for every request |
| Reasoning | Explicit effort; exclude=true so internal reasoning text is not returned |
| Total max_tokens | 8,192, shared by reasoning and visible output |
| Output contract | Strict JSON schema: label ∈ {0,1}, source_type ∈ {internal,news,other}, reason is a string |
| Provider requirement | require_parameters=true; no provider pin and no fixed seed |
| Observed successful provider | PrimeIntellect for all 3,353 successful Inkling responses |
| Client concurrency | Eight workers; queued by effort, not randomized/interleaved by experimental block |
| Reasoning retention | Reported token counts are retained; internal reasoning text is excluded |
| Response acceptance | finish_reason=stop, parseable JSON, valid binary integer label and source type, string reason |
| Recovery | One identical-configuration retry per initial failure; no increase to the cap |

Temperature zero reduces sampling variation but does not establish deterministic inference. Backend execution, routing details, and model nondeterminism remain possible sources of variation. The same successful provider removes one observed provider-switch explanation; it does not make the experiment a randomized, repeated causal study of reasoning.

### 2.4 Input integrity and historical Gemma comparability

Historical CRLF line endings were reconstructed where necessary to match existing email SHA-256 hashes. Every Inkling attempt was checked against the expected email hash, curated label, source ID, and complete request-payload hash. Both Gemma files were checked for 559 unique source IDs and matching input hashes/labels. The same Gemma instructions, include-news rule, schema, email envelope, and 20,000-character cap were used for Inkling.

Other conditions differ. Gemma off uses the historical 350-token output allowance. The recovered Gemma reasoning workflow mixes 4,096-, 8,192-, and 16,384-token allowances, legacy and recovery seeds, and recovery provider/sampling adjustments. The Gemma runs occurred earlier. Latency, caching, provider implementation, and rates therefore are not controlled across the model comparison. The right description is an observed workflow comparison on matched inputs, not an isolated measurement of model quality.

## 3. Classification results

### 3.1 Confusion matrices and review volume

TP/FP/FN/TN are measured against the original curated labels. An alert is a positive prediction. High has one abstention rather than a negative prediction: its row-242 output-limit failure is excluded from its classification denominator. That row has curated label 0, so high still covers all 73 positive-label emails. No other setting has a missing final classification.

| Workflow | Answered | TP | FP | FN | TN | Alerts |
| --- | --- | --- | --- | --- | --- | --- |
| Inkling none | 559/559 | 65 | 60 | 8 | 426 | 125 |
| Inkling minimal | 559/559 | 62 | 56 | 11 | 430 | 118 |
| Inkling low | 559/559 | 64 | 57 | 9 | 429 | 121 |
| Inkling medium | 559/559 | 62 | 57 | 11 | 429 | 119 |
| Inkling high | 558/559 | 62 | 52 | 11 | 433 | 114 |
| Inkling max | 559/559 | 63 | 53 | 10 | 433 | 116 |
| Gemma reasoning off | 559/559 | 66 | 77 | 7 | 409 | 143 |
| Gemma reasoning on, recovered | 559/559 | 68 | 74 | 5 | 412 | 142 |

| Workflow | Accuracy | Recall | Precision | Specificity | Balanced accuracy | F1 | F2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Inkling none | 87.84% | 89.04% | 52.00% | 87.65% | 88.35% | 0.6566 | 0.7794 |
| Inkling minimal | 88.01% | 84.93% | 52.54% | 88.48% | 86.70% | 0.6492 | 0.7561 |
| Inkling low | 88.19% | 87.67% | 52.89% | 88.27% | 87.97% | 0.6598 | 0.7748 |
| Inkling medium | 87.84% | 84.93% | 52.10% | 88.27% | 86.60% | 0.6458 | 0.7543 |
| Inkling high | 88.71% | 84.93% | 54.39% | 89.28% | 87.10% | 0.6631 | 0.7635 |
| Inkling max | 88.73% | 86.30% | 54.31% | 89.09% | 87.70% | 0.6667 | 0.7721 |
| Gemma reasoning off | 84.97% | 90.41% | 46.15% | 84.16% | 87.28% | 0.6111 | 0.7586 |
| Gemma reasoning on, recovered | 85.87% | 93.15% | 47.89% | 84.77% | 88.96% | 0.6326 | 0.7834 |

**Accuracy needs context.** Predicting every email negative would achieve 486/559 = 86.94% accuracy, zero recall, and no useful screening. Inkling's roughly 88% accuracy is only modestly above that majority baseline, despite a useful recall/precision operating point. Accuracy alone is a poor basis for choosing a rare-event review system. Balanced accuracy weights the positive and negative classes equally; F2 weights recall more heavily than F1 but still embodies a particular preference, not an organization-approved miss cost.

**Recall has a small denominator.** A single additional positive email changes measured recall by 1/73 = 1.37 percentage points. A one- or two-email difference is consequential to those cases but weak evidence of stable population superiority. Report counts alongside percentages.

### 3.2 Descriptive uncertainty

The following 95% Wilson intervals describe binomial uncertainty around each observed recall and precision. They are not paired confidence intervals for model differences, do not correct for the many settings examined, and do not account for duplicate/thread dependence, test-set reuse, label inconsistency, or distribution shift. They should not be read as confirmatory deployment bounds.

| Workflow | Recall estimate | Recall Wilson 95% | Precision estimate | Precision Wilson 95% |
| --- | --- | --- | --- | --- |
| Inkling none | 89.04% | 79.84%–94.34% | 52.00% | 43.31%–60.57% |
| Inkling minimal | 84.93% | 75.00%–91.37% | 52.54% | 43.60%–61.33% |
| Inkling low | 87.67% | 78.20%–93.38% | 52.89% | 44.05%–61.56% |
| Inkling medium | 84.93% | 75.00%–91.37% | 52.10% | 43.20%–60.87% |
| Inkling high | 84.93% | 75.00%–91.37% | 54.39% | 45.25%–63.24% |
| Inkling max | 86.30% | 76.59%–92.39% | 54.31% | 45.25%–63.09% |
| Gemma reasoning off | 90.41% | 81.50%–95.28% | 46.15% | 38.19%–54.32% |
| Gemma reasoning on, recovered | 93.15% | 84.95%–97.04% | 47.89% | 39.84%–56.05% |

### 3.3 Practical interpretation of the operating points

Gemma off flags 143 emails and finds 66 positives. Inkling off flags 125 and finds 65: 18 fewer reviews consist of 17 fewer false alarms and one lost positive. Gemma recovered reasoning flags 142 and finds 68. Inkling max flags 116 and finds 63: 26 fewer reviews consist of 21 fewer false alarms and five lost positives. Those workload savings are inseparable from the missed-email tradeoff.

Within Inkling, off → max reduces alerts from 125 to 116. Seven of the nine fewer alerts are false alarms and two are curated positives. Max improves precision from 52.00% to 54.31% and F1 from 0.6566 to 0.6667, while recall falls from 89.04% to 86.30%. Its apparent F1 lead is a small descriptive gain, not a general-purpose reasoning benefit.

Review cost can dominate these sub-dollar API differences, but this experiment did not measure analyst time, reviewer agreement, alert value, downstream investigations, or losses caused by missed cases. A smaller queue is beneficial only if its lost coverage is acceptable. Do not claim a measured business ROI from inference charges alone.

## 4. Paired changes across reasoning levels

### 4.1 Adjacent effort transitions

“Corrected” means a previous prediction disagreed with the curated label and the next agreed. “Regressed” means the reverse. These are benchmark-relative terms; a questionable label can reverse the substantive interpretation. For transitions involving high, row 242 is absent from both sides of the paired comparison.

| Transition | Paired | Changed | Corrected | Regressed | Positive gained/lost | FP removed/added |
| --- | --- | --- | --- | --- | --- | --- |
| none → minimal | 559 | 13 | 7 | 6 | 0/3 | 7/3 |
| minimal → low | 559 | 9 | 5 | 4 | 2/0 | 3/4 |
| low → medium | 559 | 12 | 5 | 7 | 0/2 | 5/5 |
| medium → high | 558 | 7 | 6 | 1 | 1/1 | 5/0 |
| high → max | 558 | 8 | 4 | 4 | 1/0 | 3/4 |

Minimal → low recovers two positives but also adds a net false alarm. Low → medium loses two positives and has equal numbers of false alarms removed and introduced. Medium → high removes five false alarms but trades one recovered positive for one lost positive. High → max gains one positive and adds a net false alarm; corrected and regressed counts are tied on the 558 common answers. These patterns resist a single “deeper is better” interpretation.

### 4.2 All 15 Inkling pairwise comparisons

| First → second | Paired | Flips | Corrected/regressed | Positive gained/lost | FP removed/added |
| --- | --- | --- | --- | --- | --- |
| none → minimal | 559 | 13 | 7/6 | 0/3 | 7/3 |
| none → low | 559 | 8 | 5/3 | 0/1 | 5/2 |
| none → medium | 559 | 14 | 7/7 | 0/3 | 7/4 |
| none → high | 558 | 15 | 10/5 | 0/3 | 10/2 |
| none → max | 559 | 11 | 8/3 | 0/2 | 8/1 |
| minimal → low | 559 | 9 | 5/4 | 2/0 | 3/4 |
| minimal → medium | 559 | 9 | 4/5 | 0/0 | 4/5 |
| minimal → high | 558 | 10 | 7/3 | 1/1 | 6/2 |
| minimal → max | 559 | 12 | 8/4 | 2/1 | 6/3 |
| low → medium | 559 | 12 | 5/7 | 0/2 | 5/5 |
| low → high | 558 | 9 | 6/3 | 0/2 | 6/1 |
| low → max | 559 | 11 | 7/4 | 1/2 | 6/2 |
| medium → high | 558 | 7 | 6/1 | 1/1 | 5/0 |
| medium → max | 559 | 9 | 7/2 | 2/1 | 5/1 |
| high → max | 558 | 8 | 4/4 | 1/0 | 3/4 |

### 4.3 The complete disagreement set

The 21 changing rows are 10, 11, 63, 85, 93, 94, 119, 127, 133, 136, 204, 295, 309, 328, 347, 429, 454, 491, 493, 514, and 539. There are 537 other emails answered at all six efforts with the same label, plus row 242 with five negative answers and one unanswered high request. An unanswered request is not a label disagreement.

No higher-reasoning setting finds a curated-positive email missed by Inkling off. The changing positives are exactly 133, 454, 493, and 514; off catches all four. The eight positive-label emails missed at every effort are 18, 69, 108, 254, 262, 355, 382, and 479. They form a shared error set rather than a reasoning-level delta; the audit identifies scope/label concerns in several without establishing the cause of every miss.

The companion audit contains every prediction, the six saved reasons, a direct evidence phrase, interpretation, and adjudication recommendation for each of the 21 cases. It also identifies suspect labels that do not change with reasoning, including an exact duplicate with contradictory labels.

### 4.4 Relationship to the Gemma detections

Across these saved runs, every curated-positive email found by any Inkling effort is also found by Gemma off and by Gemma recovered reasoning. There is no observed positive-label discovery complementarity from adding Inkling's hard decisions to either Gemma workflow. This does not establish the same result for calibrated scores, different prompts, new data, or review policies. It only describes the recorded binary operating points.

| Inkling effort | Additional positives vs Gemma off | Positives lost vs Gemma off | Additional positives vs Gemma on | Positives lost vs Gemma on |
| --- | --- | --- | --- | --- |
| none | 0 | 1 | 0 | 3 |
| minimal | 0 | 4 | 0 | 6 |
| low | 0 | 2 | 0 | 4 |
| medium | 0 | 4 | 0 | 6 |
| high | 0 | 4 | 0 | 6 |
| max | 0 | 3 | 0 | 5 |

## 5. API cost and token accounting

### 5.1 What each cost number includes

Inkling charges are the sum of `usage.cost` across all recorded requests for a setting, including output-limit failures and recovery attempts. Pilot calls are already present in the journal and are reused rather than charged a second time for the full sweep. The 12 initial sandbox DNS failures are stored separately; they did not reach OpenRouter and are not billable model calls. All 3,364 actual Inkling responses have known costs.

Completion tokens already include reasoning tokens. Adding reasoning tokens to completion tokens would double-count them. `reasoning.exclude=true` suppresses returned reasoning text, not the charge. Recorded costs are used directly instead of estimating them from a public page's headline rates.

Gemma off's figure is the saved successful-response total; no complete accounting of every possible historical exploratory call is asserted. Gemma on has two distinct useful totals: $0.09062778978 for the selected 559 successful classifications, and a known experiment lower bound of $0.09802271754 including legacy successes, all recorded recovery attempts, and an extra pilot success. Older failed/interrupted charges are not fully known. Mixing Inkling's all-attempt total with only Gemma's selected-success total overstates the known cross-workflow cost difference.

| Workflow | Selected-success cost | Recorded comparison cost | Cost basis | USD / 1,000 inputs | USD / 1M inputs |
| --- | --- | --- | --- | --- | --- |
| Inkling none | $0.03997794 | $0.03997794 | All attempts, including retries | $0.0715 | $71.52 |
| Inkling minimal | $0.05606435 | $0.05606435 | All attempts, including retries | $0.1003 | $100.29 |
| Inkling low | $0.05844344 | $0.05844344 | All attempts, including retries | $0.1045 | $104.55 |
| Inkling medium | $0.08171273 | $0.08171273 | All attempts, including retries | $0.1462 | $146.18 |
| Inkling high | $0.10767098 | $0.11511453 | All attempts, including retries | $0.2059 | $205.93 |
| Inkling max | $0.12286755 | $0.14270075 | All attempts, including retries | $0.2553 | $255.28 |
| Gemma reasoning off | $0.02249961 | $0.02249961 | Historical saved successes | $0.0402 | $40.25 |
| Gemma reasoning on, recovered | $0.09062779 | $0.09802272 | Known historical experiment lower bound | $0.1754 | $175.35 |

The scaled columns assume the same email lengths, output behavior, retry frequency, provider terms, and caching conditions as this sample. They are arithmetic projections, not quotes or capacity forecasts. They exclude labeling, review labor, storage, orchestration, account fees, and any unrecorded historical calls. A 559-email sample cannot establish rare tail-failure frequency at million-email scale.

Inkling off costs approximately 1.78 times the recorded Gemma-off successes. Inkling max costs approximately 1.46 times Gemma on's known experiment lower bound, or 1.57 times its selected-success subtotal. Because the latter is a subtotal and the former is only a lower bound, neither ratio establishes a controlled present-day unit-price advantage.

### 5.2 Reasoning cost within Inkling

| Effort | All attempts USD | Cost / off | Failed-attempt USD | Input tokens | Completion tokens incl. reasoning | Reasoning tokens | Reasoning share |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | $0.03997794 | 1.00× | $0.00000000 | 434,681 | 37,302 | 0 | 0.0% |
| minimal | $0.05606435 | 1.40× | $0.00000000 | 434,681 | 94,793 | 60,083 | 63.4% |
| low | $0.05844344 | 1.46× | $0.00000000 | 434,681 | 102,573 | 67,213 | 65.5% |
| medium | $0.08171273 | 2.04× | $0.00000000 | 434,681 | 180,844 | 143,334 | 79.3% |
| high | $0.11511453 | 2.88× | $0.00744355 | 436,284 | 292,472 | 254,885 | 87.1% |
| max | $0.14270075 | 3.57× | $0.01983320 | 440,470 | 384,974 | 346,933 | 90.1% |

| Effort | Median reasoning tokens / attempt | 95th percentile reasoning tokens / attempt |
| --- | --- | --- |
| none | 0 | 0.0 |
| minimal | 88 | 251.4 |
| low | 98 | 292.2 |
| medium | 199 | 587.9 |
| high | 302 | 1,113.0 |
| max | 360 | 1,520.0 |

The first four settings have identical aggregate input token counts because they each sent the same 559 inputs once. High and max have larger totals because their retries resend inputs. The reasoning-token distributions confirm that off reports zero reasoning and the enabled settings consume measurable reasoning tokens. They do not prove that token usage alone caused the classification changes.

### 5.3 Advertised catalog rates versus observed bills

In the saved 22 November catalog response, Inkling's listed input/output rates are $0.075/$0.30 per million tokens; Gemma's are $0.0675/$0.225. The corresponding cached-input entries are $0.015 and $0.0375 per million. These are metadata rates, not the per-response effective price guaranteed for a selected provider. The observed billed totals remain the accounting source of truth for this report.

No claim is made that today’s API listing will reproduce those exact rates or that a model with fewer active parameters must be cheaper. Model architecture, provider implementation, caching, billed tokens, and generated reasoning length are distinct factors.

## 6. Reliability, retries, and incomplete results

| Effort | Initial complete / 559 | Initial failures | Retry calls | Total failed attempts | Final complete / 559 | Unanswered rows |
| --- | --- | --- | --- | --- | --- | --- |
| none | 559/559 | 0 | 0 | 0 | 559/559 | None |
| minimal | 559/559 | 0 | 0 | 0 | 559/559 | None |
| low | 559/559 | 0 | 0 | 0 | 559/559 | None |
| medium | 559/559 | 0 | 0 | 0 | 559/559 | None |
| high | 557/559 | 2 | 2 | 3 | 558/559 | 242 |
| max | 551/559 | 8 | 8 | 8 | 559/559 | None |

Every failed attempt returned `finish_reason=length`, with 8,192 completion tokens and 8,192 reasoning tokens. The model exhausted the total allowance before producing a usable classification. These were response failures with known bills, not network errors or missing usage telemetry.

High initially failed on rows 242 and 342. The retry recovered 342 and failed again on 242. Max initially failed on 10, 148, 242, 297, 300, 411, 477, and 491; every retry recovered. Row 297 is positive-label, so excluding its initial failure from a partial max evaluation would have distorted the recall denominator. Final max results include its recovered classification.

Retrying at unchanged settings can alter outcomes even at temperature zero. That is direct evidence that first-pass response completeness was not deterministic in this environment. It does not quantify classification-label repeatability, because the failures had no prior usable labels to compare. No internal reasoning transcript was saved, so the cause of excessive reasoning cannot be diagnosed beyond token exhaustion.

A larger cap might recover row 242, but it would change the experiment and potentially increase tail cost. This sweep deliberately retained its cap. Its negative label and five other negative predictions make it a straightforward semantic negative in the audit; its high-setting failure is an operational defect, not evidence for a positive classification.

| Effort | Row | Curated label | Completion / reasoning tokens | Recorded cost | Attempt seconds |
| --- | --- | --- | --- | --- | --- |
| high | 242 | 0 | 8192/8192 | $0.00247368 | 20.850 |
| high | 342 | 0 | 8192/8192 | $0.00249618 | 15.861 |
| max | 10 | 0 | 8192/8192 | $0.00251029 | 39.332 |
| max | 148 | 0 | 8192/8192 | $0.00246804 | 20.596 |
| max | 242 | 0 | 8192/8192 | $0.00247368 | 22.527 |
| max | 297 | 1 | 8192/8192 | $0.00249440 | 16.927 |
| max | 300 | 0 | 8192/8192 | $0.00247331 | 20.691 |
| max | 411 | 0 | 8192/8192 | $0.00248705 | 45.330 |
| max | 477 | 0 | 8192/8192 | $0.00245757 | 19.915 |
| max | 491 | 0 | 8192/8192 | $0.00246886 | 16.683 |
| high | 242 | 0 | 8192/8192 | $0.00247368 | 24.303 |

For a conservative coverage-sensitive accuracy calculation, high has 495 correct answers out of all 559 inputs = 88.55%, counting the unanswered email as not correct. Its answered-only accuracy is 495/558 = 88.71%. Neither formulation should silently substitute a negative prediction for the abstention. A production system should surface “unanswered” explicitly and route it to retry or review.

## 7. Latency and response shape

Inkling latency is client-observed request duration for each recorded attempt. The distributions include unsuccessful attempts and retries as separate requests. They do not measure a complete email's wall-clock journey through the batch, queue waiting, human review, or maximum sustainable production throughput. Gemma latency comes from historical saved successful rows; its recovery/retry treatment and deployment conditions differ. A median comparison is descriptive, not a controlled service benchmark.

| Workflow | Median seconds | Mean seconds | 95th percentile seconds | Maximum seconds |
| --- | --- | --- | --- | --- |
| Inkling none | 0.820 | 3.230 | 16.795 | 24.283 |
| Inkling minimal | 1.380 | 4.916 | 25.091 | 54.869 |
| Inkling low | 1.506 | 6.810 | 34.070 | 109.957 |
| Inkling medium | 2.095 | 6.347 | 33.303 | 76.883 |
| Inkling high | 2.747 | 8.115 | 33.922 | 76.337 |
| Inkling max | 3.126 | 8.799 | 38.826 | 78.557 |
| Gemma reasoning off | 1.116 | 1.144 | 1.648 | 2.559 |
| Gemma reasoning on, recovered | 6.238 | 7.512 | 15.730 | 71.421 |

Reasoning off is the fastest median Inkling setting at 0.82 seconds; max's median is 3.13 seconds. Max's historical comparison with Gemma on's 6.24-second median is encouraging, but the difference cannot be attributed solely to model architecture. Means and upper quantiles matter because a small set of slow responses can dominate batch completion and user experience.

**The tail changes the speed conclusion.** Inkling off's 95th percentile is 16.80 seconds versus historical Gemma off's 1.65 seconds. Inkling max's 95th percentile is 38.83 seconds versus Gemma on's 15.73 seconds. Thus Inkling has favorable medians in those comparisons but substantially worse observed upper tails. Calling it uniformly faster would be inaccurate. Provider/load differences, historical configurations, and separate-attempt retry accounting limit causal interpretation, and this dataset does not establish the source of the long tail.

Source type was generated by each classifier rather than supplied as an independent ground truth. Its distribution changes across efforts. Consequently, a source-type-stratified quality result using these generated categories could conflate category reassignment with a real performance change. The existing independent/rule-assisted news annotations are a separate artifact and would require their own audit before subgroup conclusions.

| Inkling effort | Predicted internal | Predicted news | Predicted other |
| --- | --- | --- | --- |
| none | 326 | 144 | 89 |
| minimal | 331 | 161 | 67 |
| low | 330 | 161 | 68 |
| medium | 326 | 159 | 74 |
| high | 326 | 164 | 68 |
| max | 325 | 166 | 68 |

## 8. Interpretation boundaries

1. **Labels are not fully reliable.** Identical text at rows 283 and 517 has opposite labels. Some positive-label inputs are generic accounting material or brief attachment transmittals. Several changing cases have defensible competing policy interpretations. Metrics remain frozen to the original labels; suspected defects were not silently corrected.
2. **The test set has been inspected repeatedly.** This experiment, earlier Gemma/JEV comparisons, and the error audit are exploratory. Tuning a prompt to these cases and then reporting the same test score would overstate generalization.
3. **One successful response per setting is not a repeatability study.** There is no fixed seed and no repeated successful-label sample. Stable duplicate pairs do not establish stability on boundary cases.
4. **Effort order is not randomized.** Provider load, caches, or backend changes over the run could correlate with effort. All successful requests used PrimeIntellect, but that does not remove every service-level confound.
5. **Prompt interpretation and model capability are entangled.** A model that obeys a narrow misconduct definition may score worse against broad relevance labels. That is not necessarily poorer reasoning.
6. **The observed prevalence is curated.** Production precision depends on prevalence, task mix, language, date, and source distribution. Scaling API cost is simpler than scaling precision or workload.
7. **Only text classification was tested.** No tool-use, coding, long-context, vision, local-inference, or general reasoning capability was evaluated. “More advanced model” is not a measurable conclusion from this task alone.
8. **The cap is part of the setting.** High/max failure behavior at 8,192 tokens is relevant to this workflow; it should not be represented as a universal limit of the model with all possible budgets.
9. **No confidence ranking was collected.** The data support binary operating points and paired decisions, not calibrated probabilities, AUC, average precision, or equal-recall threshold comparisons.

## 9. Recommended next experiment

First settle the label policy using the companion audit, not a model popularity ranking. Separate review relevance from proof of wrongdoing; explicitly specify audit access, document destruction, SPE-related financial issues, missing attachments, and general scandal commentary. Resolve duplicate-label conflicts and document the rationale in a new label version while preserving the original benchmark.

Next evaluate the policy prompt on a separate validation sample, grouped by exact duplicates and email threads. Repeat boundary-case calls at fixed provider/configuration and report label agreement as well as token/latency distributions. Randomize or interleave effort settings to reduce time-of-run confounding. Predeclare retry caps and account for every response, including failures.

If a score or probability interface is added, choose thresholds on validation data and compare models at the same recall or the same review capacity. Do not treat verbal confidence as a calibrated probability. Lock the prompt, model/provider version, cap, recovery policy, and threshold before using a fresh grouped/chronological holdout.

For the confirmation run, report TP/FP/FN/TN, answered coverage, abstentions, positive and negative repeatability, all-attempt cost, latency tails, review workload, and reviewer adjudication. A setting is preferable only relative to an agreed objective and uncertainty tolerance; this sample does not supply a universal winner.

## 10. Reproducibility and artifact inventory

The repository contains the experiment client, the row audit, this report builder, unit checks, and aggregate evidence. Raw email datasets, full request journals, credentials, and full-email audit pages remain under the existing Git-ignored `data/` directory. The committed JSON includes aggregate results, row IDs/labels/input hashes, case patterns, duplicate-group metadata, failure charges, and input-file hashes. Cloning the repository alone does not provide the raw inputs needed for a full rerun.

| Artifact | Purpose |
| --- | --- |
| `scripts/inkling_reasoning_comparison.py` | Resumable API sweep and explicitly requested failed-email retries |
| `scripts/inkling_delta_review.py` | Offline 21-case audit, exact-quote checks, CSV/HTML generation |
| `scripts/build_inkling_reports.py` | Offline recomputation, consistency checks, both detailed Markdown reports and committed evidence |
| `tests/test_inkling_reasoning.py` | Validates cost retention and rejection of incomplete/invalid outputs |
| `reports/inkling_reasoning_evidence.json` | Publishable aggregate calculations and file/row hash manifest |
| `data/inkling_reasoning/attempts.jsonl` | Local raw attempt journal; includes all charged failures/retries |
| `data/inkling_reasoning/delta_review.csv` | Local six-level reasons and review annotations for changing cases |

With the original local data available, rebuild this analysis without making requests:

```sh
python3 -m scripts.inkling_delta_review
python3 -m scripts.build_inkling_reports
python3 -m unittest tests.test_inkling_reasoning
```

`python3 -m scripts.inkling_reasoning_comparison` is the experiment client, not the offline reporting command. It reuses matching recorded attempts, but can make billable requests when inputs are missing. `--retry-errors` requests additional same-settings retries and can incur charges. Neither command is required to rebuild these reports.

### 10.1 Metric definitions

- Recall = TP / (TP + FN); precision = TP / (TP + FP).
- Specificity = TN / (TN + FP); false-positive rate = FP / (TN + FP).
- Accuracy = (TP + TN) / answered inputs; balanced accuracy = (recall + specificity) / 2.
- F1 = 2TP / (2TP + FP + FN); F2 = 5TP / (5TP + FP + 4FN).
- An alert is a positive prediction; an abstention is a request without a valid final classification.
- Percentiles use linear interpolation at position `(n − 1) × quantile` on sorted values.
- Inkling cost is summed once per response from `usage.cost`; output token totals already contain reasoning.

### 10.2 Validation performed

The builder verifies all input/label/payload hashes; source-ID uniqueness for successful responses; all 559 initial requests per effort; exact attempt counts; baseline input correspondence; the fixed 21-case audit set; all 15 Inkling pairwise balances; and the $0.4940137323 total. Three unit tests verify that a valid response preserves reasoning usage without double-counting output, an output-limit failure preserves cost without a prediction, and an invalid label is rejected. These checks validate accounting and analysis consistency; they do not validate the substantive labels or establish production quality.
