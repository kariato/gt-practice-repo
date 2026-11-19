# How the calibrated confidence scores were produced

This explains how the JEV and Gemma 4 confidence scores in
`data/confidence_comparison/` were calibrated. It traces one real email from start to finish
and explains what the calibrated numbers do and don't mean.

## At a glance

The calibrated score is the raw model probability passed through **Platt scaling** (a sigmoid
fit), learned on **500 separate validation emails**. The 559 test emails were never used for
fitting. The code is in [`scripts/evaluate_confidence.py`](../scripts/evaluate_confidence.py)
(`fit_calibrator` and `calibrate`).

1. **Raw score.**
   - **Gemma:** a one-token prompt asks for `0` or `1` with reasoning off. The raw score is
     P(1) ÷ (P(0) + P(1)), from the log probabilities of those two tokens.
   - **JEV:** its own returned probability is the raw score.
2. **Validation sample.** 500 emails drawn from the training file (seed 20261001, 67 positive),
   after removing duplicates, emails that also appear in the test set, and duplicates with
   conflicting labels.
3. **Fit.** One calibrator per model, fit on those 500 emails:
   `calibrated = sigmoid(slope × logit(raw) + intercept)`, where `logit(p) = ln(p / (1 − p))`.
4. **Apply.** The saved parameters are applied to the test scores, or to a new email via
   `predict_with_confidence`.

| Model | Slope | Intercept |
|---|---|---|
| JEV | 0.833 | −0.391 |
| Gemma | 0.203 | −2.235 |

Gemma's slope of 0.2 means its raw scores were heavily overconfident. A raw 0.90 becomes 0.14,
a raw 0.99 becomes 0.21, and a raw 0.9999 becomes 0.41. JEV changes only slightly: a raw 0.5
becomes 0.40, and a raw 0.9 becomes 0.81.

| | Brier | Log loss | ECE | ROC AUC | At 0.5: relevant found / false alarms |
|---|---|---|---|---|---|
| Gemma raw | 0.135 | 1.353 | 0.139 | 0.942 | 67 / 74 |
| Gemma calibrated | 0.062 | 0.201 | 0.034 | 0.942 | 56 / 34 |
| JEV raw | 0.061 | 0.202 | 0.034 | 0.942 | 51 / 24 |
| JEV calibrated | 0.057 | 0.194 | 0.025 | 0.942 | 47 / 16 |

- **Ranking doesn't change.** The mapping only goes up, so ROC AUC stays the same. Calibration
  improves how well the probabilities match reality, not how well the model separates emails.
- **The 0.5 cutoff means something different.** It now sits at a much higher raw score, which is
  why Gemma finds fewer emails at 0.5 after calibration. Choose the operating threshold
  separately for your recall target.
- **The probabilities match these curated labels, not production.** They reflect this dataset's
  positive rate (about 13%). On real traffic the rate will be much lower, so refit the
  calibrator on a labeled sample from that traffic.

The rest of this document covers each stage in detail.

---

## 1. The problem calibration solves

A score is **calibrated** if, out of all emails that get 0.70, about 70% really are positive.

Gemma's raw scores were badly off. On the validation set, emails Gemma scored at 0.9999 or
higher (99.99% sure) were positive only **62%** of the time. The scores still ranked emails well
(ROC AUC 0.942), but the numbers themselves weren't believable probabilities.

Calibration changes the numbers so they can be read as probabilities. It never changes the order
of the emails.

---

## 2. Stage 1: the raw score

### Gemma

Code: `gemma_score` and `parse_scores` in
[`scripts/confidence_comparison.py`](../scripts/confidence_comparison.py). This scoring prompt is
separate from the JSON classifier used elsewhere in the project.

- **Prompt:** the include-news rule, followed by *"Output exactly one digit: 0 or 1. Do not
  output an explanation or other text."*
- **Request settings:**
  - `max_tokens: 1`, so the model writes a single token.
  - `reasoning: {enabled: false}`.
  - `temperature: 1, top_p: 1`, so the log probabilities are the model's unmodified
    distribution. A temperature of 0 would distort what gets reported.
  - `logprobs: true, top_logprobs: 20`, which returns the 20 most likely candidate tokens and
    their log probabilities.
  - Provider pinned to Darkbloom with `require_parameters: true`, so the request fails rather
    than silently dropping the `logprobs` setting.
- **Score:** take the log probabilities of exactly the tokens `"0"` and `"1"` at that position
  and normalize them so they add to 1:

  ```
  raw = e^lp1 / (e^lp0 + e^lp1)
  ```

  The code subtracts the larger log probability first so the arithmetic can't overflow.
- **Prediction comes from the score, not the sampled token.** At temperature 1 the sampled token
  is random, so the decision uses `raw ≥ 0.5`.
- **Safety checks:**
  - If either `"0"` or `"1"` is missing from the candidates, the row is marked
    `missing_label_probability`. It is never treated as zero.
  - Any reported reasoning, or log probabilities that aren't finite, raise an error.
  - `label_probability_mass` (P("0") + P("1")) is recorded to show nothing else was competing.
    Its lowest value on validation was 0.99982.
  - All 1,059 calls (500 validation + 559 test) returned both label probabilities and zero
    reasoning tokens.

**Worked example, test email (source row) 2.** Its label is 0 (not relevant).

| | Value |
|---|---|
| `logprob_0` | −2.9997 |
| `logprob_1` | −0.0511 |
| raw = 1 / (1 + e^−(−0.0511 − (−2.9997))) | **0.950** |

At raw 0.5 this email would be flagged as relevant.

### JEV

JEV returns its own probability (the `relevant` answer). The raw score is that probability. Its
existing test predictions were reused, and new calls were made only for the 500 validation emails.

---

## 3. Stage 2: the validation set

A calibrator learned from the test emails would make the test metrics look better than they are.
So it was fitted on emails taken from the **training** file, built like this (`inputs()` in
[`scripts/confidence_comparison.py`](../scripts/confidence_comparison.py)):

1. Normalize whitespace in every email, to catch copies that differ only in spacing or line
   endings.
2. Group identical emails and keep one per group. Drop any group whose copies have
   **conflicting labels**.
3. Drop any email that also appears in the test set.
4. That leaves **2,097** eligible emails. Draw **500** at random with seed `20261001`; **67** are
   positive (13.4%).
5. Save the row ids and email hashes to `data/confidence_validation_manifest.json`. If a later
   run would draw a different sample, the code stops rather than overwriting it.

Those 500 emails were then scored by both models: Gemma for $0.0115 and JEV for $0.0162 in API
cost.

**Why Gemma needed so much correction.** Here are the 500 validation emails grouped by raw Gemma
score:

| Raw Gemma score | Emails | Actually positive | Positive rate |
|---|---|---|---|
| below 0.0001 | 359 | 2 | 1% |
| 0.0001–0.01 | 7 | 0 | 0% |
| 0.01–0.5 | 11 | 1 | 9% |
| 0.5–0.99 | 23 | 6 | 26% |
| 0.99–0.9999 | 15 | 5 | 33% |
| **0.9999 and up** | **85** | **53** | **62%** |

Gemma pushes most emails to the extremes. The top group claims at least 99.99% but is right 62%
of the time, and the 0.5–0.99 group is mostly wrong. The calibrator learns exactly this mismatch.

---

## 4. Stage 3: fitting the calibrator

Code: `fit_calibrator` in [`scripts/evaluate_confidence.py`](../scripts/evaluate_confidence.py).

### The model

This is **Platt scaling**: a two-parameter logistic regression on the raw score's log-odds.

```
logit(p)   = ln(p / (1 − p))                                 # 0.5→0, 0.95→2.94, 0.9999→9.2
calibrated = sigmoid(slope × logit(raw) + intercept)         # sigmoid(z) = 1 / (1 + e^−z)
```

- **Slope** stretches or squeezes the model's confidence.
  - Below 1 means the model is overconfident, so its log-odds are shrunk.
  - Above 1 means it is underconfident.
  - Exactly 1 means its confidence is about right.
- **Intercept** shifts every score up or down. It corrects for the model leaning too far toward
  "relevant" or "not relevant" overall.
- **No ordering change.** Because the slope must be positive, the order of emails can't change.
  The code raises an error if the fit ever produces a slope of 0 or below.

### How the fit runs

- **Clipping:** raw scores are first clipped to [10⁻¹², 1 − 10⁻¹²], so the logit stays finite
  (at most about ±27.6).
- **Objective:** the loss is binary cross-entropy (log loss) over the 500 emails, plus a fixed
  L2 penalty ½·1·slope².
  - The penalty applies to the slope only and pulls it gently toward 0, which keeps the fit
    stable.
  - It was set in advance, not tuned on the test set. With 500 emails its effect is small.
- **Solver:** Newton's method, starting from slope 1 and intercept 0. Each step uses the gradient
  and the 2×2 Hessian, then halves the step until the loss improves. It stops when the step size
  falls below 10⁻⁸, or after 100 iterations.
- **Separate calibrators:** JEV and Gemma were each fitted separately, on their own validation
  scores.

### The fitted parameters

From `data/confidence_comparison/evaluation.json`:

| Model | Slope | Intercept | Meaning |
|---|---|---|---|
| Gemma | **0.203** | **−2.235** | Log-odds shrunk about 5×, then pushed strongly toward "not relevant" |
| JEV | 0.833 | −0.391 | Mild shrink and a small shift down; JEV was already close to calibrated |

---

## 5. Stage 4: applying it

### The worked example, continued (row 2)

| Step | Calculation | Result |
|---|---|---|
| Raw score | from Stage 1 | 0.950 |
| Logit | ln(0.950 / 0.050) | 2.949 |
| Scale and shift | 0.2028 × 2.949 − 2.2347 | −1.637 |
| Sigmoid | 1 / (1 + e^1.637) | **0.163** |

Raw Gemma called this email 95% likely relevant. Calibrated, it is **16%**. That matches the
validation evidence: emails Gemma scored around 0.5–0.99 were relevant about 26% of the time. The
email's label is 0, so calibration moved it the right way.

### The mapping for each model

| Raw score | Gemma calibrated | JEV calibrated |
|---|---|---|
| 0.5 | 0.097 | 0.403 |
| 0.9 | 0.14 | 0.81 |
| 0.99 | 0.21 | 0.97 |
| 0.9999 | 0.41 | ~1.0 |

What this means in practice:

- **Gemma's 0.5 cutoff moves enormously.** A calibrated 0.5 needs a raw Gemma score of at least
  **0.999984** (a logit of about 11). For JEV it needs a raw score of 0.615.
- **Gemma's calibrated scores are capped.**
  - On the 559 test emails they range from 0.005 to **0.78**.
  - Even a raw score at the clipping limit only reaches 0.967.
  - That is the calibrator saying that, on this evidence, Gemma's top scores are right about
    three-quarters of the time.
  - JEV's calibrated test scores range from 0.014 to 0.945.

---

## 6. Stage 5: evaluating it on the test set

Code: `evaluate()` in [`scripts/evaluate_confidence.py`](../scripts/evaluate_confidence.py).

The fitted calibrator was applied once to the 559 test emails (73 positive). Each saved row is
first checked against its email hash, label and settings fingerprint.

### What the metrics mean

- **Brier score:** the average of (probability − truth)². Lower is better.
- **Log loss:** heavily penalizes confident mistakes. Lower is better.
- **ECE (expected calibration error):** sort emails into ten equal-width score bands, then take
  the average gap between predicted and actual positive rate, weighted by how many emails are in
  each band. 0 would be perfect.
- **ROC AUC / average precision:** measure ranking only. Calibration doesn't change them.

### Results

| | Brier | Log loss | ECE | ROC AUC | At 0.5: relevant found / false alarms |
|---|---|---|---|---|---|
| Gemma raw | 0.135 | **1.353** | 0.139 | 0.942 | 67 / 74 |
| Gemma calibrated | 0.062 | 0.201 | 0.034 | 0.942 | 56 / 34 |
| JEV raw | 0.061 | 0.202 | 0.034 | 0.942 | 51 / 24 |
| JEV calibrated | 0.057 | 0.194 | 0.025 | 0.942 | 47 / 16 |

**Calibration bands for Gemma on the test set:**

- **Raw:** 130 emails sat in the 0.9–1.0 band with an average score of **0.996**, and only
  **51%** were positive. That one band produces most of the 0.139 ECE.
- **Calibrated:** the bands mostly line up. For example, 0.6–0.7 averages 0.65 predicted against
  58% actual, and 0.7–0.8 averages 0.74 against 82%.
- **Weak spot:** the 0.4–0.6 bands still overestimate (about 0.5 predicted against 17–31%
  actual). They hold only 12–16 emails each, so they are noisy.

### Threshold picked on validation

The code also picks the cutoff that maximized F1 on the **calibrated validation** scores, then
reports how that cutoff performs on test:

| Model | Cutoff (calibrated) | Test: found / missed / false alarms |
|---|---|---|
| Gemma | 0.478 (raw ≈ 0.999975) | 57 / 16 / 39 |
| JEV | 0.348 (raw ≈ 0.43) | 52 / 21 / 30 |

These cutoffs are F1 reference points, not business thresholds. In practice, pick the cutoff
from your recall target or reviewer capacity.

### Outputs

- `data/confidence_comparison/gemma4_test_probabilities.csv` and `jev_test_probabilities.csv`:
  raw score, calibrated score, prediction, and `predicted_class_confidence = max(p, 1 − p)` for
  each email.
- `data/confidence_comparison/evaluation.json`: the fitted parameters and all the metrics above.
- `calibration.svg` and `precision_recall.svg`: the calibration and precision–recall charts.

---

## 7. Scoring a new email

`predict_with_confidence` in [`scripts/confidence_comparison.py`](../scripts/confidence_comparison.py):

1. Load the saved calibrator from `evaluation.json`.
2. Check that its settings fingerprint matches the current prompt and request settings. If
   anything has changed, the old calibrator no longer applies, so it raises an error.
3. Make one live API call to get the raw score. This costs money.
4. Apply `sigmoid(slope × logit(raw) + intercept)`.
5. Return `raw_probability`, the calibrated `probability`, `prediction` (calibrated ≥ 0.5) and
   `predicted_class_confidence`.

```python
from scripts.confidence_comparison import predict_with_confidence
predict_with_confidence(email_text, model="gemma4")   # or model="jev"
```

---

## 8. What the calibrated score does and doesn't mean

- **It is the probability of the *curated relevance label*,** not the probability of actual
  misconduct.
- **It assumes a positive rate of about 13%.**
  - Validation was 13.4% positive and test 13.1%. The intercept partly encodes that rate.
  - On real email traffic, where relevant emails might be 1% or fewer, these probabilities will
    be **too high**.
  - Refit the calibrator, or at least the intercept, on a labeled sample from the traffic you'll
    actually score.
- **It is tied to one exact setup:** model, prompt, provider and settings, all captured by the
  fingerprint. Change any of them and you need a new calibrator. A different serving stack (for
  example an internally hosted Gemma) may produce different log probabilities, so fit a new
  calibrator there.
- **It rests on a small sample.** Only 67 positive validation emails, and the upper score bands
  hold few emails, so the slope and intercept carry real uncertainty.
- **Duplicates were only partly removed.** Exact copies (after whitespace normalization) were
  removed, but near-duplicate threads and forwarded articles were not, so validation and test may
  still share very similar content. The test set had also been looked at during earlier work, so
  a confirmatory result needs fresh data.

---

## 9. Reproducing it

```bash
python -m scripts.confidence_comparison --collect   # resumes API scoring; skips completed rows
python -m scripts.evaluate_confidence               # offline: fit, apply, metrics, charts (needs NumPy)
```

The second command needs no API key. It rebuilds everything from the saved CSVs.
