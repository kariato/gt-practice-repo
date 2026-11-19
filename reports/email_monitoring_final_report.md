# Email monitoring: final cost and performance report

**Project closeout · 2 October 2026**  
**Audience:** senior management and the data science lead  
**Decision:** which evaluated classifier should advance to an email monitoring pilot, under which operating conditions?  
**Evidence baseline:** repository commit `4154ece`; 559 curated Enron test emails and a separate 500-email calibration sample.

## Executive overview

**Recommendation: advance the Gemma probability-score workflow to a bounded shadow pilot, with JEV evaluated alongside it as the option for a smaller review queue.** Select the deployment threshold from newly labeled operational emails using the organization’s tolerance for missed cases and its review capacity. The completed project supports this pilot decision; it does not yet establish the performance or total cost of a live enterprise monitoring service.

The strongest practical finding is that **review workload dominates inference cost**. The Gemma score workflow found 67 of 73 relevant emails, missed 6, and generated 74 false alarms. JEV at its raw 0.5 cutoff found 51, missed 22, and generated 24 false alarms. Gemma’s 16 additional relevant emails required 66 additional reviews in this benchmark. Neither outcome is a universal winner: the choice depends on the cost of missing a relevant email and the time available to investigate alerts.

**Ensemble follow-up:** a fixed 50/50 average of calibrated JEV and Gemma scores is a useful pilot challenger. At thresholds chosen to target 90% validation recall, it finds 66 test positives with 66 false alarms. JEV finds 65 positives with 78 false alarms, and Gemma finds 64 with 58 false alarms at their corresponding validation-selected thresholds. It does not improve on Gemma at the 95% validation target. The detailed ensemble analysis is in Section 4; these small gains require fresh-data confirmation.

### The management decision in five points

1. **When missed relevant emails are the main concern, start with Gemma’s score workflow.** Its raw 0.5 cutoff achieved 91.8% recall at an observed inference cost of $0.01358 for 559 emails. It also exposes a score that can support a different review threshold after operational validation.
2. **When review capacity is the binding constraint, start with JEV and a validated threshold.** Its raw cutoff generated 75 alerts, versus Gemma score’s 141. JEV’s calibrated 0.5 cutoff reduced the queue to 63 alerts but missed 26 of 73 positives. That is an explicit loss of coverage.
3. **Keep recovered reasoning as a challenger for difficult cases.** It found one additional positive relative to the Gemma score run, with the same total number of false alarms. It also required recovery work and had materially longer recorded request times than the JSON run with reasoning disabled. One extra positive on this sample is insufficient evidence to make it the default.
4. **Budget for review and integration before optimizing API spend.** At an illustrative 100,000 emails per month, 1% relevant-email prevalence, three minutes per alert, and $60 per reviewer hour, the observed rates imply approximately $16,763 in monthly review labor for raw JEV and $47,976 for raw Gemma score. Their extrapolated API charges are only $3.32 and $2.43. These are sensitivity estimates, not production forecasts or vendor quotes.
5. **Approve a limited pilot with measurable exit conditions.** The missing evidence is operational: current-company labels, case-level usefulness, reviewer time, rare-event precision, end-to-end latency, and complete failure accounting. The project has completed a reproducible offline comparison; production rollout remains a separate decision.

### What management should authorize next

Authorize a pilot using a fixed, approved email population and a capped review queue. Assign an operations owner to define relevant cases and acceptable misses, a data science owner to freeze the label policy and threshold, and an engineering owner to measure delivery latency and incomplete classifications. Fund measured labeling, review, and integration work. A full production budget cannot be justified from inference charges alone.

## 1. What this project established

### Business question and scope

The classifier identifies **substantive discussion or evidence of Enron accounting irregularities**: misleading reporting, improper mark-to-market valuation, concealed losses, and misuse of special purpose entities. The broad benchmark counts relevant news and allegations as positive. A positive prediction is an email that merits review; it is not a finding that wrongdoing occurred.

This is a retrospective case study with a company-specific prompt. It has not evaluated general fraud detection, phishing, malware, all employee misconduct, or arbitrary modern enterprise correspondence. Adapting the prompt to a current organization changes the task and requires new labels and evaluation.

### Evidence and completed work

- **Test set:** 559 emails, comprising 73 positives and 486 negatives; relevant-email prevalence is 13.06%.
- **Independent calibration sample:** 500 emails from the training file, including 67 positives. Whitespace-normalized exact duplicates and exact overlaps with test emails were removed before sampling.
- **Coverage:** each primary workflow has a saved prediction for all 559 emails. The recovered reasoning workflow combines 214 historical successes with 345 recovered predictions.
- **Input consistency:** source IDs, curated labels, and email hashes were checked across runs. Historical CRLF line endings are accounted for when matching saved request hashes.
- **Input limit:** classifier code caps email text at 20,000 characters. No saved test input is marked truncated. Attachments, thread reconstruction, mailbox ingestion, and reviewer actions were not part of this benchmark.
- **Completion status:** offline classification, calibration, cost analysis, and comparison artifacts are complete. A continuously operating monitoring service has not been built or load-tested by this project.

The experiments compare complete workflows. Prompts, news policies, output formats, generation settings, and recovery behavior differ. They do not isolate the causal effect of model choice or reasoning alone.

### Configurations represented in the results

| Workflow | Recorded configuration |
| --- | --- |
| JEV | Requested `typesafe/jev-1.13`; saved responses report `typesafe/jev-1.13-20260917`; native positive probability and a structured decision question |
| Gemma JSON include/exclude | `google/gemma-4-26b-a4b-it`; temperature 0; 350-token output allowance; label, source type, and reason; historical reasoning setting unspecified |
| Gemma JSON reasoning disabled | Same Gemma model, include-news policy, temperature 0, 350-token allowance, and `reasoning.enabled=false`; saved provider Darkbloom |
| Gemma probability score | Same Gemma model; different one-token prompt; temperature 1, top-p 1, reasoning disabled; Darkbloom only, requiring supported parameters and both label log probabilities |
| Recovered reasoning | Same Gemma model; temperature 0; explicit reasoning; recovery seed 2 while historical seed was unspecified; final selected responses use a 4,096-token allowance for 558 rows and 8,192 for one; retries attempted larger budgets and one row required repetition penalty 1.1 |

These configuration differences are part of each workflow's observed cost and behavior. No local model fine-tuning was performed.

## 2. Which option fits which operating conditions?

| Operating condition | Recommended candidate | Evidence supporting the choice | Condition before deployment |
| --- | --- | --- | --- |
| Missing relevant emails is costly; reviewers can handle a larger queue | Gemma probability score, with a recall-oriented threshold | Raw 0.5 found 67/73 positives; it was the cheapest evaluated inference workflow | Measure rare-event precision and validate the required recall on new operational labels; reserve review capacity |
| Small analyst team; alerts must be prioritized tightly | JEV probability score, with a capacity-based threshold | Higher measured AP, 0.772 vs 0.735; raw 0.5 produced 75 alerts vs 141 for Gemma score | Agree the acceptable miss rate; do not assume the default cutoff is optimal |
| Exploring a better balance of coverage and review workload | Evaluate the calibrated JEV/Gemma score ensemble alongside both models | Fixed 50/50 scores found 66/73 positives with 66 false alarms at the 90% validation target | Tune only on development data; confirm on fresh emails; measure two-request latency and failure behavior |
| Need an intermediate coverage/workload tradeoff | Gemma score with calibration and a tuned cutoff | Calibrated 0.5 found 56/73, with 34 false alarms and 90 reviews | Treat 0.5 as an evaluated reference point; choose the business cutoff on a separate validation sample |
| Every alert needs a generated source type and short reason in the initial response | Gemma JSON with reasoning disabled | 66/73 found; 77 false alarms; source type and reason saved; explicit reasoning configuration | Check that reasons are grounded in the message and useful to reviewers; validate the production schema |
| Specialist review of difficult or high-value cases; longer processing is acceptable | Evaluate reasoning as a separate challenger or escalation experiment | Recovered reasoning found 68/73; only one more than Gemma score | Test the proposed escalation population and full retry cost; its combined-system benefit has not been measured |
| The business explicitly excludes copied news and third-party commentary | Gemma exclude-news workflow with policy-aligned labels | Found 19/20 non-news positives; this is a different task from the broad benchmark | Independently validate source labels; define how forwarded articles with internal commentary should be treated |
| Strict high recall plus a very small queue | No evaluated operating point is yet established as suitable | At an assumed 1% prevalence, even calibrated JEV projects 3,903 alerts per 100,000 emails | Improve or narrow the task, tune on new data, and measure coverage lost through any filtering |

**Pilot default:** deploy one selected workflow in shadow mode, which records scores and routes a bounded sample to reviewers without changing email delivery. Evaluate the other score model on the same pilot sample as a challenger. The production choice should follow the measured operational tradeoff.

## 3. Observed benchmark performance

TP is a relevant email found; FN is a relevant email missed. FP is a false alarm; TN is a negative email correctly rejected. Recall measures coverage of relevant emails. Precision measures the useful fraction of the alert queue. Specificity measures the fraction of negative emails rejected.

| Workflow | TP / FN | FP / TN | Recall | Precision | Specificity | F1 | AP |
| --- | --- | --- | --- | --- | --- | --- | --- |
| JEV raw ≥0.5 | 51 / 22 | 24 / 462 | 69.9% | 68.0% | 95.1% | 0.689 | 0.772 |
| Gemma score raw ≥0.5 | 67 / 6 | 74 / 412 | 91.8% | 47.5% | 84.8% | 0.626 | 0.735 |
| Gemma JSON: include news | 67 / 6 | 79 / 407 | 91.8% | 45.9% | 83.7% | 0.612 | — |
| Gemma JSON: reasoning disabled | 66 / 7 | 77 / 409 | 90.4% | 46.2% | 84.2% | 0.611 | — |
| Gemma: recovered reasoning | 68 / 5 | 74 / 412 | 93.2% | 47.9% | 84.8% | 0.633 | — |
| Gemma JSON: exclude news | 19 / 54 | 39 / 447 | 26.0% | 32.8% | 92.0% | 0.290 | — |

**Interpretation.** Gemma score and Gemma JSON with news included found the same number of positives, but the score workflow generated five fewer false alarms and cost about 40% less in inference. The JSON workflow offers a short reason and source type; whether those fields save reviewer time was not measured. Historical include-news JSON omitted the reasoning setting, so its reasoning behavior is unknown.

JEV’s lower recall is accompanied by fewer false alarms and higher precision. This can be valuable when analysts cannot review a large queue. Its higher average precision (AP) suggests stronger overall ordering of relevant messages on this test set, but it does not prove that JEV will outperform at every review budget or at a common recall target. That requires a threshold-specific comparison on fresh data.

**Why AP is blank for JSON runs.** AP summarizes the precision–recall ranking across score thresholds. JSON classifiers saved discrete labels, so they do not provide the numeric ranking needed for a comparable AP measurement. Their one precision/recall pair is an operating point.

**Why accuracy is not the decision metric.** A classifier that marks every email negative would be 86.9% accurate here while missing all 73 positives. The business needs coverage and a manageable review queue, so this report emphasizes recall, false alarms, ranking, and total review effort.

### The exclude-news result answers a separate business question

The news audit marks 161 emails as news, including 53 of the original 73 positives. On the original labels, exclude-news finds only 19/73 positives because rejecting relevant news conflicts with the broad benchmark policy.

On the 398 annotated non-news emails, it finds 19/20 positives, with 39 false alarms: **95.0% recall, 32.8% precision, and 89.7% specificity**. If the policy-aligned label is applied to all 559 emails, there are 20 positives and 539 negatives; specificity becomes 92.8% because the 161 rejected news emails are now negatives. Those denominators must not be mixed.

The 95% recall interval for 19/20 is approximately 76.4%–99.1%. The remaining miss is a university accounting job description previously identified as a possible labeling error; it remains counted in these results. The news annotations were assisted by rules and review after model results were available. They need independent confirmation before they support a deployment decision.

## 4. Calibration and threshold selection

Calibration maps model scores onto an estimated probability of the curated positive label. It is useful for prioritization and cost decisions, but it does not turn a relevance score into the probability of actual misconduct.

### A 0.5 cutoff means different things before and after calibration

| Score / cutoff | Found / missed | False alarms | Alerts to review | Recall | Precision | Specificity |
| --- | --- | --- | --- | --- | --- | --- |
| JEV raw ≥0.5 | 51 / 22 | 24 | 75 | 69.9% | 68.0% | 95.1% |
| JEV calibrated ≥0.5 | 47 / 26 | 16 | 63 | 64.4% | 74.6% | 96.7% |
| Gemma score raw ≥0.5 | 67 / 6 | 74 | 141 | 91.8% | 47.5% | 84.8% |
| Gemma score calibrated ≥0.5 | 56 / 17 | 34 | 90 | 76.7% | 62.2% | 93.0% |

The Gemma calibrated cutoff removes 51 reviews compared with its raw cutoff, including 40 false alarms and 11 true positives. JEV calibration removes 12 reviews, including eight false alarms and four true positives. Calibration improved probability estimates on this benchmark, while using 0.5 on the transformed score changed the operational decision boundary.

Both fitted mappings are monotonic, so they preserve ranking and AP. Calibration itself does not create a better ranking or a free recall improvement. A threshold can also be selected directly on raw scores; a calibrated scale makes the intended risk tradeoff easier to express if calibration transfers to the deployment population.

### Probability quality

Lower values are better for Brier score (squared probability error), log loss (which penalizes confident mistakes), and ECE (the weighted gap between confidence and observed frequency across ten bins). ECE is descriptive and sensitive to binning and sample size.

| Model | Brier: raw → calibrated | Log loss: raw → calibrated | ECE: raw → calibrated | AP, unchanged |
| --- | --- | --- | --- | --- |
| JEV | 0.0606 → 0.0570 | 0.2023 → 0.1943 | 0.0336 → 0.0248 | 0.772 |
| Gemma score | 0.1348 → 0.0624 | 1.3533 → 0.2009 | 0.1394 → 0.0336 | 0.735 |

Raw Gemma token scores are strongly overconfident on this task. Among 130 test emails in its 0.9–1.0 score bin, the average raw score is about 99.6%, while only 50.8% have a positive curated label. The fitted calibration reduces this mismatch. The raw normalized token score should therefore be labeled as a model score in a review interface unless a suitable calibrator has been validated.

The Gemma score workflow normalizes the probabilities of the exact `0` and `1` tokens, uses a one-token response, temperature 1, top-p 1, and reasoning disabled. Predictions come from the normalized score rather than the sampled token. All 1,059 recorded validation and test requests supplied both label probabilities and reported zero reasoning tokens. This establishes coverage for those saved requests, not future provider availability.

### Thresholds selected on validation data

The existing procedure selected a calibrated threshold by maximizing F1 on the 500-email validation sample. These are the resulting **test-set** metrics:

| Model | Validation-selected calibrated cutoff | Test recall | Test precision | Test F1 | Test alerts |
| --- | --- | --- | --- | --- | --- |
| JEV | 0.348425 | 71.2% | 63.4% | 0.671 | 82 |
| Gemma score | 0.478497 | 78.1% | 59.4% | 0.675 | 96 |

F1 gives a particular balance between precision and recall; it does not encode analyst capacity or the business cost of a missed case. The F1-selected cutoffs are therefore useful experimental references, not approved business thresholds. Their test F1 also does not improve on every 0.5 reference point.

For deployment, first define a recall requirement and queue limit, then select a threshold on a representative validation sample. Freeze the prompt, model, provider constraints, calibrator, and threshold before evaluating on a later untouched sample. If no threshold meets both requirements, report the gap explicitly.

### Recall targets chosen on validation data

For a decision closer to monitoring requirements, this final analysis also selects the highest threshold that reaches at least 90% or 95% recall on the 500 validation emails, then applies it unchanged to the 559 test emails. The threshold search uses validation labels only; all resulting test outcomes are reported. These are additional exploratory analyses of an already inspected test set, so they do not restore an untouched confirmatory evaluation.

| Model | Validation target | Calibrated cutoff | Achieved validation recall | Test recall | Test false alarms | Test alerts |
| --- | --- | --- | --- | --- | --- | --- |
| JEV | 90% | 0.072681 | 91.0% (61/67) | 89.0% (65/73) | 78 | 143 |
| JEV | 95% | 0.054978 | 95.5% (64/67) | 93.2% (68/73) | 92 | 160 |
| Gemma score | 90% | 0.170838 | 91.0% (61/67) | 87.7% (64/73) | 58 | 122 |
| Gemma score | 95% | 0.101736 | 95.5% (64/67) | 91.8% (67/73) | 73 | 140 |

Neither model sustains its requested validation recall target on test. At the 95% validation target, JEV finds 68 test positives with 92 false alarms, while Gemma score finds 67 with 73 false alarms. JEV can reach higher recall by lowering its threshold; it then creates a much larger queue than its raw 0.5 operating point. The raw-default comparison is therefore a comparison of operating choices, not a fixed capability limit for either model.

For the pilot, retain both score workflows until operational validation identifies the better coverage/workload tradeoff. The raw cutoffs used for these calculations are retained in the aggregate JSON so threshold ties can be reproduced exactly. No additional model API requests were needed for this analysis.

### Ensemble feasibility: JEV plus Gemma score

**Recommendation: evaluate a score ensemble as a challenger in the pilot.** A fixed 50/50 average of the two calibrated scores shows a modest improvement at one useful operating point. The evidence supports another controlled comparison; it does not establish an ensemble as the production winner.

This analysis combines JEV with the Gemma probability-score workflow on the same emails and broad include-news definition. No additional model requests were made. The 500 validation emails and 559 test emails were matched by source ID and label, with input hashes checked for the underlying predictions.

#### Method and threshold selection

The exploratory combination is:

```text
ensemble_score = 0.5 × calibrated_JEV_score + 0.5 × calibrated_Gemma_score
```

The weights were fixed at 50/50; they were not fitted or selected by searching the test outcomes. Each model retains its previously fitted sigmoid calibrator. For each of the 90% and 95% validation recall targets, the highest ensemble cutoff meeting that target is selected on validation labels and then applied unchanged to the test emails. The selected ensemble cutoffs are approximately 0.126026 and 0.084440, respectively.

Averaging calibrated probabilities is a standard soft-voting approach. Calibration is particularly relevant here because Gemma's raw token scores were overconfident. The averaged score still needs its own calibration assessment before it is presented as an operational probability. See the [scikit-learn soft-voting documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.VotingClassifier.html).

#### What the observed results show

| Workflow | Validation recall target | Test positives found | Test recall | Test false alarms | Test reviews |
| --- | --- | --- | --- | --- | --- |
| JEV | 90% | 65/73 | 89.0% | 78 | 143 |
| Gemma score | 90% | 64/73 | 87.7% | 58 | 122 |
| 50/50 score ensemble | 90% | 66/73 | 90.4% | 66 | 132 |
| JEV | 95% | 68/73 | 93.2% | 92 | 160 |
| Gemma score | 95% | 67/73 | 91.8% | 73 | 140 |
| 50/50 score ensemble | 95% | 67/73 | 91.8% | 77 | 144 |

At the 90% validation target, the ensemble finds one more positive than JEV while removing 12 false alarms and 11 total reviews. Compared with Gemma, it finds two more positives while adding eight false alarms and ten reviews. These cutoffs share a validation target; their achieved test recall differs, so this is not a comparison at identical test recall.

At the 95% validation target, the ensemble and Gemma both find 67 positives, but the ensemble generates four more false alarms. JEV finds one additional positive, with 15 more false alarms than the ensemble. The ensemble therefore does not improve every operating choice.

The ensemble's test AP is **0.781**, compared with **0.772 for JEV** and **0.735 for Gemma score**. This is a small descriptive ranking improvement; its statistical uncertainty has not been estimated. At a fixed ensemble cutoff of 0.5, the result is 50 positives found, 22 false alarms, and 68.5% recall. A useful ensemble still requires a threshold appropriate to the business objective.

#### Why voting on labels adds little here

At the original raw 0.5 cutoffs, all 51 positives found by JEV are also found by Gemma. Gemma finds 16 additional positives, while both miss six. There are no positive emails uniquely found by JEV at those cutoffs.

| Raw 0.5 decisions | Positives found | False alarms | Total reviews |
| --- | --- | --- | --- |
| JEV alone | 51 | 24 | 75 |
| Gemma score alone | 67 | 74 | 141 |
| Alert when at least one model is positive | 67 | 75 | 142 |
| Alert only when both models are positive | 51 | 23 | 74 |

These results explain why adding JEV's yes/no decision gives little benefit to Gemma at the default cutoffs. The score average can still use information in the relative strengths of their predictions, even where the hard labels overlap.

#### Cost, operational implications, and next experiment

Running both models on every email would sum to **$0.03211422 for the 559-message workload**, or approximately **$57.45 per million benchmark-like emails**. Gemma score alone extrapolates to $24.29 and JEV to $33.16. These are saved inference charges scaled by volume; they exclude additional failures and service overhead. The ensemble requires two model requests per email, and its combined latency and availability have not been measured.

The additional API spend is small relative to the report's review-labor scenarios. Whether the ensemble is worthwhile depends on useful detections and the review queue, rather than its AP improvement alone. A production design must also define what happens when one component is unavailable; silently switching to a single score would change the meaning of the ensemble threshold.

The next experiment should compare the fixed 50/50 baseline with a small number of weights selected on development data, or a regularized combiner trained on the two scores. Compare the chosen combination with both individual models at an agreed recall target or review budget. Keep related threads together, separate tuning from final evaluation, and confirm on a fresh sample before adopting a weight or threshold. Add reasoning only if it demonstrates further value on the cases routed to it.

**Evidence limit:** this is an exploratory extension on an already inspected test set. Calibration and cutoff selection reuse the same validation sample, and the ensemble idea was considered after examining the earlier results. The gains involve only a few emails. This supports a pilot challenger, not a claim of a confirmed production improvement.

## 5. Strength of the evidence

### Uncertainty around measured rates

These Wilson intervals use 73 positive and 486 negative observations and assume independent emails. Repeated or related threads can make them optimistic.

| Workflow | Recall point estimate | Approximate 95% interval | Specificity point estimate | Approximate 95% interval |
| --- | --- | --- | --- | --- |
| JEV raw ≥0.5 | 69.9% | 58.6%–79.2% | 95.1% | 92.8%–96.7% |
| Gemma score raw ≥0.5 | 91.8% | 83.2%–96.2% | 84.8% | 81.3%–87.7% |
| Gemma: recovered reasoning | 93.2% | 84.9%–97.0% | 84.8% | 81.3%–87.7% |

One positive email changes recall by 1.37 percentage points. The recovered reasoning result and Gemma score result differ by exactly one positive. A row-level comparison shows that reasoning recovers one positive missed by the score run, loses none of its detected positives, removes three false alarms, and introduces three other false alarms. This is a useful candidate improvement, but insufficient evidence that the gain will repeat in deployment.

The headline JEV/Gemma tradeoff is substantial within this sample. The project has not estimated a confidence interval for the AP difference, performed a production-domain comparison, or established performance on the most costly incident categories.

### Limits that affect the rollout decision

| Evidence limitation | Consequence for management and data science |
| --- | --- |
| Curated historical Enron emails and a company-specific prompt | Performance cannot be assumed to transfer to a current enterprise mailbox |
| Test labels and errors were inspected during iterative analysis | The comparison is descriptive; a new locked test sample is needed for confirmation |
| 559 test rows contain 554 unique whitespace-normalized texts | Exact repeats exist; near-duplicate articles and related threads were not removed |
| 500 calibration emails contain 67 positives | Calibration in rare score regions is uncertain and reflects the curated class balance |
| News audit was informed by earlier model outputs | Policy-specific estimates may be optimistic |
| Different prompts, token budgets, and sampling settings | Report workflow outcomes; do not attribute differences solely to reasoning or model architecture |
| Reasoning recovery mixes historical and recovered requests | It is not a single uniform configuration; earlier failed/interrupted charges are incomplete |
| No mailbox, attachment, reviewer, or case-resolution experiment | Case detection, time saved, operational latency, and business return remain unmeasured |

Future validation should group related threads and near-duplicate content, use a chronological holdout, and measure relevant subgroups such as source type, message length, and actual incident category. A negative-message sample is essential: reviewing alerts alone cannot measure recall or calibrate the miss rate.

## 6. Cost of an email monitoring service

### 6.1 Observed inference charges and volume sensitivity

The following figures use reported OpenRouter charges from the saved runs, divided by 559 and multiplied by volume. They assume the same email-length distribution, prompt, response format, and provider economics. **They are historical workload extrapolations, not current list prices or production quotes.** They exclude infrastructure, integration, human review, storage, taxes or account fees, and unrecorded failures.

| Workflow | Observed 559-email cost | 10,000 emails | 100,000 emails | 1 million emails |
| --- | --- | --- | --- | --- |
| JEV raw ≥0.5 | $0.01853 | $0.33 | $3.32 | $33.16 |
| Gemma score raw ≥0.5 | $0.01358 | $0.24 | $2.43 | $24.29 |
| Gemma JSON: include news | $0.02261 | $0.40 | $4.05 | $40.45 |
| Gemma JSON: reasoning disabled | $0.02250 | $0.40 | $4.02 | $40.25 |
| Gemma: recovered reasoning | ≥$0.09802 | ≥$1.75 | ≥$17.54 | ≥$175.35 |
| Gemma JSON: exclude news | $0.02259 | $0.40 | $4.04 | $40.41 |

Calibrated JEV and calibrated Gemma score reuse the same test responses and therefore have the same per-email API cost as their corresponding raw scores. The separate validation requests cost $0.01616 for JEV and $0.01147 for Gemma, or $0.02763 combined. That is only the recorded API cost of calibration data collection; it excludes labeling and staff work.

At one million benchmark-like emails, the score workflow extrapolates to about $24 in API charges, JEV to $33, and the JSON workflows to about $40. These small differences should not drive a decision that changes thousands of monthly reviews. Future messages with longer bodies, attachments, extra prompts, or additional retries can change this cost profile.

### 6.2 Recovered reasoning: reconcile the cost before comparing it

| Cost component | Recorded USD |
| --- | ---: |
| 214 retained historical successful requests | $0.03547155 |
| All 349 recovery attempts, including four failed responses | $0.06239245 |
| Additional 8,192-token pilot success not selected for the combined result | $0.00015872 |
| **Known experiment cost lower bound** | **$0.09802272** |

The selected 559 successful responses alone sum to $0.09062779. That smaller number excludes $0.00723621 of recorded failed recovery responses and the additional pilot. Earlier failed or interrupted attempts are not fully billed in the available records, so the report uses **at least $0.09802** as the experiment total.

The ≥$175.35 per million figure is a scaled lower bound from this experiment, including its recovery overhead. It is not a steady-state service estimate. It is at least 7.2 times the observed Gemma score inference cost, but the absolute difference is still small beside human review costs. The stronger reason to defer default reasoning is the limited demonstrated gain plus unresolved operational behavior.

### 6.3 Human review changes the economics

**Illustrative assumptions:** 100,000 incoming emails per month; 1% genuinely relevant; three minutes to review each alert; $60 per fully loaded reviewer hour. Each alert costs $3 to review. Benchmark recall and false-positive rates are assumed to remain constant. No thread grouping, duplicate suppression, or reviewer productivity improvement is assumed.

| Operating point | True alerts | False alerts | Missed positives | All alerts | Review hours | Review labor |
| --- | --- | --- | --- | --- | --- | --- |
| JEV raw ≥0.5 | 699 | 4,889 | 301 | 5,588 | 279 | $16,763 |
| JEV calibrated ≥0.5 | 644 | 3,259 | 356 | 3,903 | 195 | $11,709 |
| Gemma score raw ≥0.5 | 918 | 15,074 | 82 | 15,992 | 800 | $47,976 |
| Gemma score calibrated ≥0.5 | 767 | 6,926 | 233 | 7,693 | 385 | $23,079 |
| Gemma: recovered reasoning | 932 | 15,074 | 68 | 16,006 | 800 | $48,017 |

Counts and costs are rounded independently. Inference adds approximately $2.43–$3.32 for the score models, or at least $17.54 for the scaled reasoning experiment. The table excludes investigation after initial triage and the financial or operational impact of missed cases.

With 160 fully productive review hours per person per month, these queues would consume approximately 1.75 reviewer-equivalents for raw JEV, 1.22 for calibrated JEV, 5.00 for raw Gemma score, and 2.40 for calibrated Gemma score. Staffing would need additional allowance for leave, training, coordination, and follow-up work. These are workload equivalents, not a hiring plan.

**Marginal decision example.** In this 1% scenario, raw Gemma score finds about 219 more relevant emails than raw JEV and requires roughly 10,404 extra reviews. Its additional review-plus-inference cost is about $31,212 per month, or **$142 per additional relevant email found**. If the expected avoided loss per additional detected email exceeds that amount, the higher-recall option may be economically preferable under these assumptions. The project has not measured that loss, and several emails may describe the same underlying case. This is a break-even illustration, not a claimed return on investment.

A total-cost model should use:

```text
Monthly operating cost = API charges + queue/storage/monitoring costs
                       + alert reviews × minutes per review × hourly cost / 60
                       + investigation and quality-audit costs
                       + support and maintenance

Decision cost can additionally include expected loss from missed cases
and costs caused by false escalations. Those values require business input.
```

### 6.4 Rare relevant emails make precision worse

The benchmark has 13.1% positives. In a general mailbox the relevant fraction may be much smaller; this project has not measured it. The table shows what happens if recall and the false-positive rate stay fixed while prevalence changes:

| Operating point | Precision if 0.1% relevant | Precision if 1% relevant | Precision at benchmark 13.1% |
| --- | --- | --- | --- |
| JEV raw ≥0.5 | 1.40% | 12.50% | 68.00% |
| JEV calibrated ≥0.5 | 1.92% | 16.50% | 74.60% |
| Gemma score raw ≥0.5 | 0.60% | 5.74% | 47.52% |
| Gemma score calibrated ≥0.5 | 1.09% | 9.97% | 62.22% |
| Gemma: recovered reasoning | 0.61% | 5.82% | 47.89% |

At 1% prevalence, Gemma’s raw precision falls from 47.5% to about 5.7% in this sensitivity calculation. At 0.1%, it is about 0.6%. That is why copying the benchmark precision into a production business case would materially understate the review burden.

For prevalence `p`, recall `r`, and false-positive rate `f`:

```text
Expected true alerts  = N × p × r
Expected false alerts = N × (1 − p) × f
Expected misses       = N × p × (1 − r)
Expected precision    = (p × r) / (p × r + (1 − p) × f)
```

If the organization can review at most 2,000 of 100,000 monthly emails and requires 90% recall at 1% prevalence, the permitted false-positive rate is approximately **1.11%**. None of the evaluated operating points establishes that combination. Raising a threshold or filtering content may reduce the queue, but its lost coverage must be measured. Review capacity should influence the experiment design before rollout.

## 7. Latency, reliability, and system design

### What timing data actually show

| Workflow with recorded timing | Rows | Median | 95th percentile | Maximum |
| --- | --- | --- | --- | --- |
| Gemma JSON: reasoning disabled | 559 | 1.12 s | 1.65 s | 2.56 s |
| Gemma: recovered reasoning | 559 | 6.24 s | 15.73 s | 71.42 s |

These are recorded successful-call latencies, not email-arrival-to-alert times or controlled load-test results. The recovered column mixes historical and recovery requests; it does not include the full time spent in earlier failed attempts, interruptions, or queues. It shows roughly 5.6 times the median and 9.5 times the 95th-percentile latency of the JSON run with reasoning disabled.

Comparable timing was not saved for JEV or the Gemma score workflow. The one-token score format is economical, but this evidence cannot establish it as the fastest option. Ten configured workers do not by themselves demonstrate sustainable throughput or a service-level objective.

The recovery journal contains 345 successes and four failed responses across 349 attempts. That is a record of a targeted recovery operation, not an unbiased estimate of production availability. One email required additional provider/repetition settings after exhausting earlier output budgets. All 559 final predictions are present, but completeness was achieved with intervention and retries.

### Proposed monitoring flow

```text
Approved email feed
  → durable ingestion queue and message identity
  → text extraction and explicit scope checks
  → versioned classifier request
  → schema/score validation or unresolved-message queue
  → calibrated score and business threshold
  → prioritized reviewer queue and evidence link
  → reviewer outcome, sampled negative audits, and quality monitoring
```

This is the proposed next implementation. In particular:

- Persist an input reference, model/prompt/configuration version, score, threshold, decision, attempt status, provider, latency, and billed cost. This allows an alert to be reconstructed after a model or threshold change.
- Treat malformed responses, missing token probabilities, timeouts, and exhausted retries as unresolved classifications. Route them to an explicit retry or manual-review path; counting them as negatives would conceal missed coverage.
- Use bounded retries and record every attempt. OpenRouter documents error codes and `Retry-After` handling for retryable responses; production handling should respect that signal. See the [OpenRouter error guide](https://openrouter.ai/docs/api_reference/errors-and-debugging).
- For the Gemma score method, retain provider and parameter requirements because the score depends on token log probabilities. A new provider or fallback configuration needs its own compatibility and quality checks. OpenRouter supports provider allowlists, `require_parameters`, and data-policy routing controls. See [provider routing documentation](https://openrouter.ai/docs/guides/routing/provider-selection).
- Establish approved access, retention, and processing locations for operational email. Verify that the intended provider supports the required data policy; no such production approval or endpoint capability is established by the benchmark. Model selection alone does not settle these requirements.
- Present a score, relevant message evidence, and any generated reason to a reviewer. Keep the human decision distinct from the classifier output. Track which alerts become useful cases and how long they take to review.
- If thread grouping or duplicate suppression is added, measure both reduced reviews and any cases lost. A claimed workload saving requires this measurement.

Provider documentation was checked on 2 October 2026. The production design above is an engineering recommendation; it has not been implemented or tested as part of the offline evaluation.

## 8. Transition plan and release criteria

The following is a proposed four-to-six-week sequence after access and reviewers are available. It is a planning estimate, not a committed schedule or a measured project duration.

| Stage | Accountable owner | Deliverable | Exit condition |
| --- | --- | --- | --- |
| Define the operational task | Business/monitoring lead, supported by data science | Written label policy, scope, news treatment, review budget, and miss-cost priorities | Stakeholders agree what an alert means and what coverage is required |
| Build a representative labeled sample | Data science lead and subject-matter reviewers | Independently reviewed positives and sampled negatives; grouped duplicates/threads; chronological split | Label disagreements resolved and enough positives collected for the planned precision of recall estimates |
| Compare and freeze candidate configurations | Data science lead | JEV and Gemma score at validation-selected business cutoffs; calibration and confidence intervals | Select one candidate whose validation results fit both recall and queue requirements |
| Run shadow monitoring | Engineering and operations | Durable queue, complete attempt/cost logging, reviewer outcomes, end-to-end latency | New locked sample and live measurements support the required quality, capacity, and reliability |
| Decide on limited production | Sponsor with data science and operations leads | Signed operating choice, budget, alert policy, rollback owner | Required targets are met, or the project reports the remaining gap and stops expansion |

### Suggested acceptance scorecard

Targets should be set before the pilot is scored. The values below distinguish measured outcomes from decisions management still needs to make.

| Measure | Pilot measurement | Decision needed |
| --- | --- | --- |
| Recall | Estimate on independent positives, with a confidence interval and critical-category breakdown | Minimum acceptable recall and how much uncertainty is acceptable |
| Queue size and precision | Alerts per 1,000 emails, true-alert fraction, and peak backlog | Monthly review capacity and maximum acceptable backlog |
| Case usefulness | Distinct useful cases, duplicate alerts, escalation quality, reviewer time | Minimum value per review; what counts as a useful case |
| Delivery and failure behavior | Arrival-to-alert p50/p95, unresolved fraction, retry counts, and recovery time | Required alert latency and handling of unresolved messages |
| Total cost | All attempts, infrastructure, review hours, audit sampling, and follow-up | Budget ceiling and acceptable cost per useful case |
| Stability | Quality by time window, source type, and message length; performance after provider/model changes | Drift triggers, change approval, and rollback thresholds |

For sample-size planning, a simple binomial approximation at 90% recall needs about **139 independent positives** for a ±5 percentage-point 95% margin. This is only a planning approximation; cluster structure and subgroup evaluation may require more. At a true 1% prevalence, obtaining that many positives through simple random sampling would require roughly 13,900 emails on average. Enriching a recall evaluation with positives can help, but precision and workload still require a representative sample or appropriate weighting.

## 9. Project closeout assessment

**The project has delivered a defensible offline basis for choosing a pilot configuration.** Gemma score provides the strongest observed combination of high recall and low inference cost among the individual models. JEV provides a more selective queue and higher measured AP than Gemma alone. Calibration offers interpretable score adjustments and additional operating choices, with explicit recall losses at the tested 0.5 cutoff. The score ensemble warrants a pilot comparison because it improves one observed operating point and ranking slightly, while failing to improve every target. Recovered reasoning is a promising but unconfirmed incremental improvement.

**The outstanding investment decision is operational validation.** Inference charges are small in this workload. The financial value will depend on whether alerts identify useful cases early enough to matter, how many alerts reviewers can handle, and how many important cases remain undetected. Those quantities should determine the production threshold and business case.

The recommended handoff is a limited shadow pilot with a named owner, a representative labeled sample, a review budget, and pre-agreed acceptance targets. Expansion should follow demonstrated case value and capacity, using the same discipline applied to the offline comparison.

## Appendix A. Evidence and reproducibility

### Repository artifacts

- [All-runs comparison notebook](../EDA/jev_gemma4_all_runs_comparison.ipynb): saved benchmark metrics, calibration comparison, and recall/specificity analysis.
- [All-runs HTML export](../EDA/jev_gemma4_all_runs_comparison.html): downloadable notebook output.
- [Aggregate evidence for this report](email_monitoring_metrics.json): recomputed confusion counts, AP, Wilson intervals, latency summaries, cost components, scenarios, paired prediction changes, ensemble results, and input file hashes.
- [Offline analysis script](../scripts/email_monitoring_analysis.py): verifies matching source IDs, labels, and hashes, checks scores and calibration outputs, and rebuilds the aggregate evidence.
- [Calibration implementation](../scripts/evaluate_confidence.py) and [score collection/configuration](../scripts/confidence_comparison.py): calibration fitting, F1 threshold selection, and the token-score method.
- [Recovery implementation](../scripts/gemma_reasoning_recovery.py): retry provenance and cost accounting.

The prediction CSVs, labels, and recovery journal remain in the Git-ignored `data/` directory. This report publishes aggregate findings and an input-hash manifest. Downloading the repository alone does not supply the row-level inputs required to rerun the analysis.

### Reproduction commands

With the saved data available locally:

```bash
python3 -m scripts.email_monitoring_analysis
```

To re-fit calibration and regenerate its underlying evaluation, use an environment with NumPy:

```bash
python3 -m scripts.evaluate_confidence
python3 -m scripts.email_monitoring_analysis
```

The calibration rerun was checked against the prior saved metrics. The final-report analysis checks all six complete workflows, four additional calibrated operating points, four validation recall-target choices, and the fixed score ensemble with both recall targets and hard-vote baselines. It reconstructs historical input hashes with the known line-ending variants, recomputes AP with tied scores grouped, verifies calibrated probabilities, and reconciles recovery charges with the attempt journal.

To rebuild the HTML from this Markdown report, use an environment with `markdown-it-py`:

```bash
python3 scripts/render_report_html.py reports/email_monitoring_final_report.md
```

The Markdown and HTML are authored decision reports using the aggregate evidence. If new experiments change that evidence, review the narrative and recommendations as well as the tables before publishing a refreshed report.

### Metric definitions

```text
Recall       = TP / (TP + FN)
Precision    = TP / (TP + FP)
Specificity  = TN / (TN + FP)
False-positive rate = FP / (FP + TN)
F1           = 2 × TP / (2 × TP + FP + FN)
Alert count  = TP + FP
```

AP is the threshold-weighted precision integral over recall increments, grouping equal scores before each increment. All main test comparisons use the same 73 positives and 486 negatives. The exclude-news subsection explicitly changes the label policy or restricts the population, so its denominators are stated separately.

## Appendix B. Facts, assumptions, and decisions

| Category | Items |
| --- | --- |
| Measured or reproduced | Saved predictions and charges; benchmark confusion counts; ranking and calibration metrics; available successful-call latency; logged recovery attempts |
| Scenario assumptions | 100,000 emails per month; 0.1%, 1%, or benchmark prevalence; constant recall/FPR under changed prevalence; three minutes per alert; $60 per review hour |
| Not yet measured | Operational prevalence; current-company performance; incident-level recall; reviewer time; full deployment cost; end-to-end throughput and latency; benefits of routing or grouping |
| Management choices | Relevant-email definition; acceptable misses; review capacity; cost of missed cases; processing requirements; pilot and expansion thresholds |

This separation is central to the recommendation: the measured benchmark supports selecting candidates, while the operating assumptions must be replaced with pilot evidence before a production business case is approved.
