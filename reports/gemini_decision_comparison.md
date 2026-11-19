# Gemini Decision 1 compared with Gemma 4 and JEV

Run date: 13 November 2026. All 559 historical test inputs and labels were verified by source ID and SHA-256. No inputs were truncated.

Gemini uses `google/gemini-decision-1`, the identical JEV structured question (including relevant news), the same 20,000-character cap, and a raw probability cutoff of 0.5. JEV and Gemma are saved historical runs; Gemma uses its separate label-token score prompt. This compares workflows, not an isolated model effect.

| Workflow | Recall | Precision | F1 | Found / missed | False alarms | Average precision | Recorded API cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Gemini Decision 1 | 75.3% | 61.8% | 0.679 | 55 / 18 | 34 | 0.804 | $0.03546 |
| JEV | 69.9% | 68.0% | 0.689 | 51 / 22 | 24 | 0.772 | $0.01853 |
| Gemma 4 score | 91.8% | 47.5% | 0.626 | 67 / 6 | 74 | 0.735 | $0.01358 |

Gemini occupies the middle ground at 0.5: four more relevant emails than JEV with ten additional false alarms, but twelve fewer relevant emails than Gemma with forty fewer false alarms. It has the strongest observed ranking (average precision), while JEV has the best raw probability error (Brier: JEV 0.0606, Gemini 0.0641, Gemma 0.1348; lower is better).

Gemini cost about 1.9 times JEV and 2.6 times Gemma for this sample. Historical versus current runs do not control for price changes. Costs are recorded API usage, excluding review labor.

Recommendation: retain Gemma for the measured high-recall default and evaluate Gemini as a ranking challenger. Select any Gemini threshold and calibrator on separate validation data before comparing at a common review capacity. Gemini was not calibrated in this experiment, and no test-label threshold tuning was performed. Differences on this small, previously inspected dataset are exploratory and do not establish production superiority.

Reproduce or resume: `python -m scripts.gemini_decision_comparison`. Predictions are saved in `data/gemini_decision_test_predictions.csv`; full metrics in `data/gemini_decision_comparison.json`. Existing matching predictions are reused without new API calls.
