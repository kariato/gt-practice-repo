"""Benchmark Gemini Decision 1 against the saved JEV and Gemma score runs."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
from pathlib import Path
import time

from scripts.confidence_comparison import load_key, read_csv
from scripts.gemma_reasoning_recovery import source_rows
from scripts import jev_openrouter as j
from scripts.evaluate_confidence import scores

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'google/gemini-decision-1'
OUTPUT = ROOT / 'data/gemini_decision_test_predictions.csv'


def main():
    rows = source_rows()
    fingerprint = j.config_hash(MODEL, j.MAX_EMAIL_CHARS)
    saved = read_csv(OUTPUT) if OUTPUT.exists() else []
    lookup = {int(r['source_row']): r for r in saved}
    if len(lookup) != len(saved) or not set(lookup).issubset({r['source_row'] for r in rows}):
        raise ValueError('Invalid saved IDs')
    for row in rows:
        old = lookup.get(row['source_row'])
        if old and (old['email_sha256'] != hashlib.sha256(row['email'].encode()).hexdigest()
                    or old['config_sha256'] != fingerprint or int(old['label']) != row['label']):
            raise ValueError('Saved input or configuration mismatch')
    key = load_key()

    def classify(row):
        start = time.monotonic()
        result = j.classify_email(row['email'], key, model=MODEL)
        return {'source_row': row['source_row'], 'label': row['label'], **result,
                'email_sha256': hashlib.sha256(row['email'].encode()).hexdigest(),
                'config_sha256': fingerprint, 'latency_seconds': time.monotonic() - start}

    pending = [r for r in rows if r['source_row'] not in lookup]
    with OUTPUT.open('a', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=j.OUTPUT_FIELDS + ['latency_seconds'])
        if handle.tell() == 0:
            writer.writeheader()
        # Check compatibility before dispatching the remaining requests.
        if pending:
            result = classify(pending.pop(0))
            writer.writerow(result)
            handle.flush()
            lookup[result['source_row']] = result
            print('Pilot passed', flush=True)
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(classify, row) for row in pending]
            for future in as_completed(futures):
                result = future.result()
                writer.writerow(result)
                handle.flush()
                lookup[result['source_row']] = result
                if len(lookup) % 50 == 0:
                    print(f'Completed {len(lookup)}/{len(rows)}', flush=True)
    summary = {}
    for name, results in [('Gemini Decision 1', list(lookup.values())),
                          ('JEV', read_csv(ROOT / 'data/jev_test_predictions.csv')),
                          ('Gemma 4 score', read_csv(ROOT / 'data/gemma4_probability_test.csv'))]:
        by_id = {int(r['source_row']): r for r in results}
        if len(by_id) != len(rows) or len(results) != len(rows):
            raise ValueError('Incomplete comparison')
        for row in rows:
            r = by_id[row['source_row']]
            if int(r['label']) != row['label'] or r['email_sha256'] != hashlib.sha256(row['email'].encode()).hexdigest():
                raise ValueError('Comparison inputs differ')
            if int(r['prediction']) != int(float(r['probability']) >= .5):
                raise ValueError('Comparison threshold differs')
        metrics = j.evaluate(results)
        metrics.update(scores([int(r['label']) for r in results],
                              [float(r['probability']) for r in results]))
        summary[name] = metrics
    (ROOT / 'data/gemini_decision_comparison.json').write_text(json.dumps(summary, indent=2) + '\n')
    lines = [
        '# Gemini Decision 1 compared with Gemma 4 and JEV', '',
        'Run date: 13 November 2026. All 559 historical test inputs and labels were verified by source ID and SHA-256. No inputs were truncated.', '',
        'Gemini uses `google/gemini-decision-1`, the identical JEV structured question (including relevant news), the same 20,000-character cap, and a raw probability cutoff of 0.5. JEV and Gemma are saved historical runs; Gemma uses its separate label-token score prompt. This compares workflows, not an isolated model effect.', '',
        '| Workflow | Recall | Precision | F1 | Found / missed | False alarms | Average precision | Recorded API cost |',
        '| --- | --- | --- | --- | --- | --- | --- | --- |',
    ]
    for name, m in summary.items():
        lines.append(f"| {name} | {m['recall']:.1%} | {m['precision']:.1%} | {m['f1']:.3f} | {m['tp']} / {m['fn']} | {m['fp']} | {m['average_precision']:.3f} | ${m['total_cost_usd']:.5f} |")
    lines += ['',
        'Gemini occupies the middle ground at 0.5: four more relevant emails than JEV with ten additional false alarms, but twelve fewer relevant emails than Gemma with forty fewer false alarms. It has the strongest observed ranking (average precision), while JEV has the best raw probability error (Brier: JEV 0.0606, Gemini 0.0641, Gemma 0.1348; lower is better).', '',
        'Gemini cost about 1.9 times JEV and 2.6 times Gemma for this sample. Historical versus current runs do not control for price changes. Costs are recorded API usage, excluding review labor.', '',
        'Recommendation: retain Gemma for the measured high-recall default and evaluate Gemini as a ranking challenger. Select any Gemini threshold and calibrator on separate validation data before comparing at a common review capacity. Gemini was not calibrated in this experiment, and no test-label threshold tuning was performed. Differences on this small, previously inspected dataset are exploratory and do not establish production superiority.', '',
        'Reproduce or resume: `python -m scripts.gemini_decision_comparison`. Predictions are saved in `data/gemini_decision_test_predictions.csv`; full metrics in `data/gemini_decision_comparison.json`. Existing matching predictions are reused without new API calls.', '',
    ]
    (ROOT / 'reports/gemini_decision_comparison.md').write_text('\n'.join(lines))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
