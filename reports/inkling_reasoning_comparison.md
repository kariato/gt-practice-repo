# Inkling 2 Mini reasoning sweep versus Gemma 4

Run date: 22 November 2026. Paired evaluation on 559 Enron test emails (73 positive). Source IDs, labels, and email SHA-256 hashes match both historical Gemma baselines.

Inkling uses the identical Gemma classification instructions, includes relevant news, clips emails at 20,000 characters, requests the same strict JSON schema, and uses temperature 0. All six settings have the same 8,192-token combined reasoning/output cap. Providers are automatically routed with required parameter support; provider names are recorded. No test labels are sent to the model and no thresholds are tuned.

| Model / reasoning | Completed | Accuracy | Recall | Precision | F1 | Found / missed | False alarms | Recorded API cost | Cost / 1,000 emails | Median request seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 559/559 | 87.84% | 89.04% | 52.00% | 0.657 | 65 / 8 | 60 | $0.039978 | $0.0715 | 0.82 |
| minimal | 559/559 | 88.01% | 84.93% | 52.54% | 0.649 | 62 / 11 | 56 | $0.056064 | $0.1003 | 1.38 |
| low | 559/559 | 88.19% | 87.67% | 52.89% | 0.660 | 64 / 9 | 57 | $0.058443 | $0.1045 | 1.51 |
| medium | 559/559 | 87.84% | 84.93% | 52.10% | 0.646 | 62 / 11 | 57 | $0.081713 | $0.1462 | 2.10 |
| high | 558/559 | 88.71% | 84.93% | 54.39% | 0.663 | 62 / 11 | 52 | $0.115115 | $0.2059 | 2.75 |
| max | 559/559 | 88.73% | 86.30% | 54.31% | 0.667 | 63 / 10 | 53 | $0.142701 | $0.2553 | 3.13 |
| gemma_none | 559/559 | 84.97% | 90.41% | 46.15% | 0.611 | 66 / 7 | 77 | $0.022500 | $0.0402 | 1.12 |
| gemma_on_recovered | 559/559 | 85.87% | 93.15% | 47.89% | 0.633 | 68 / 5 | 74 | $0.090628 | $0.1621 | 6.24 |

| Inkling effort | Reasoning tokens | Failures | Attempts without cost |
| --- | --- | --- | --- |
| none | 0 | 0 | 0 |
| minimal | 60,083 | 0 | 0 |
| low | 67,213 | 0 | 0 |
| medium | 143,334 | 0 | 0 |
| high | 254,885 | 3 | 0 |
| max | 346,933 | 8 | 0 |

## Findings

On this sample, Gemma without reasoning has the lowest recorded API cost and higher recall than every Inkling setting. Gemma with recovered reasoning has the highest observed recall (68 of 73 relevant emails). Inkling produces fewer false alarms at every setting. For Inkling, reasoning off has the highest recall (65 of 73) and lowest cost; max has the highest observed F1 among its complete settings, but finds only 63 relevant emails and costs about 3.6 times reasoning off. Increased reasoning did not consistently improve quality on this task.

For a high-recall screening workflow, retain the Gemma baseline pending a separate validation experiment. Inkling with reasoning off is the economical Inkling candidate when reducing false alarms matters more. The high setting has one unresolved classification (source row 242, a negative example) after two attempts at the same cap; max recovered all eight initial failures. All retry charges are included. There were 3,354 initial calls plus 10 retry calls; the three unit checks for response validation and cost retention passed.


## Cost and interpretation

Costs above are API-reported usage.cost, summed once per response; completion tokens already include reasoning tokens. Reasoning text is excluded from saved responses, but its tokens are still billed. Failures retain any reported cost and are listed in summary.json; missing cost means unknown, not free. Metrics for incomplete settings describe successful responses only and must not be ranked as full-set results.

Gemma results are historical, so price, caching, provider, and run-date differences are not controlled. The recovered Gemma reasoning run combines token caps of 4,096, 8,192, and 16,384, different seeds, and provider recovery settings. Its listed cost covers saved successful requests, with additional recovery attempts documented separately in data/gemma4_reasoning_recovery_evaluation.json; older failed/interrupted costs are not fully known. This is a comparison of observed workflows, not an isolated causal estimate of model or reasoning effects.

This small, previously inspected test set supports exploratory comparison. Differences of one or two positive emails should not establish superiority. Choose a deployment setting using separate validation data and the cost of reviewing false alarms.

The catalog snapshot in data/inkling_reasoning/model_snapshot.json records current advertised prices and accepted reasoning efforts. Prices can differ from public page summaries and from the selected provider.

Reproduce: `python3 -m scripts.inkling_reasoning_comparison`. Matching recorded attempts are reused without API calls. Errors are retained in the journal. `--retry-errors` retries failed emails once per invocation with identical settings and includes all recorded attempt costs. The initial sandbox DNS failures are preserved separately in network_failures.jsonl and never reached OpenRouter.
