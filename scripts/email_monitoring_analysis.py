"""Recompute aggregate evidence for the final email-monitoring report offline.

Run: python3 -m scripts.email_monitoring_analysis
Requires the saved, Git-ignored data files; never makes API calls.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = {
    'jev': ('JEV raw', 'jev_test_predictions.csv', 'probability'),
    'gemma_score': ('Gemma score raw', 'gemma4_probability_test.csv', 'probability'),
    'gemma_include': ('Gemma JSON include news', 'gemma4_include_test_predictions.csv', None),
    'gemma_disabled': ('Gemma JSON reasoning disabled', 'gemma4_include_no_reasoning_test_predictions.csv', None),
    'gemma_recovered': ('Gemma reasoning recovered', 'gemma4_include_reasoning_recovered_test_predictions.csv', None),
    'gemma_exclude': ('Gemma JSON exclude news', 'gemma4_exclude_test_predictions.csv', None),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def wilson(successes, total):
    z = 1.959963984540054
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [center - half, center + half]


def metrics(rows):
    c = Counter((int(r['label']), int(r['prediction'])) for r in rows)
    tp, fp, fn, tn = c[1, 1], c[0, 1], c[1, 0], c[0, 0]
    return {
        'n': len(rows), 'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        'alerts': tp + fp, 'recall': tp / (tp + fn),
        'precision': tp / (tp + fp) if tp + fp else 0,
        'specificity': tn / (tn + fp), 'fpr': fp / (tn + fp),
        'f1': 2 * tp / (2 * tp + fp + fn),
        'recall_wilson_95': wilson(tp, tp + fn),
        'specificity_wilson_95': wilson(tn, tn + fp),
    }


def average_precision(rows):
    ranked = sorted(rows, key=lambda r: float(r['probability']), reverse=True)
    positives = sum(int(r['label']) for r in rows)
    tp = seen = 0
    ap = 0.
    i = 0
    while i < len(ranked):
        score = float(ranked[i]['probability'])
        previous_tp = tp
        while i < len(ranked) and float(ranked[i]['probability']) == score:
            tp += int(ranked[i]['label'])
            seen += 1
            i += 1
        ap += (tp - previous_tp) / positives * tp / seen
    return ap


def calibrated_probability(raw, fitted):
    clipped = min(1 - 1e-12, max(1e-12, float(raw)))
    z = fitted['slope'] * math.log(clipped / (1 - clipped)) + fitted['intercept']
    return 1 / (1 + math.exp(-z))


def ensemble_analysis(validation, scored, raw, confidence, result):
    """Fixed equal-weight score average; select cutoffs using validation labels only."""
    def combine(left, right, saved_calibration):
        a = {int(row['source_row']): row for row in left}
        b = {int(row['source_row']): row for row in right}
        require(set(a) == set(b), 'Ensemble source IDs differ')
        combined = []
        for source_id in sorted(a):
            x, y = a[source_id], b[source_id]
            require(x['label'] == y['label'], 'Ensemble labels differ')
            if saved_calibration:
                p, q = float(x['calibrated_probability']), float(y['calibrated_probability'])
            else:
                require(x['email_sha256'] == y['email_sha256'], 'Ensemble validation inputs differ')
                p = calibrated_probability(x['probability'], confidence['models']['jev']['calibrator'])
                q = calibrated_probability(y['probability'], confidence['models']['gemma4']['calibrator'])
            score = (p + q) / 2
            combined.append({'source_row': source_id, 'label': int(x['label']),
                             'probability': score, 'prediction': int(score >= .5)})
        return combined

    val = combine(validation['jev'], validation['gemma4'], False)
    test = combine(scored['jev'], scored['gemma4'], True)
    targets = {}
    for target in [.90, .95]:
        cutoff = max(score for score in {row['probability'] for row in val}
                     if sum(row['label'] for row in val if row['probability'] >= score) / 67 >= target)
        decision = lambda rows: [{**row, 'prediction': int(row['probability'] >= cutoff)} for row in rows]
        targets[f'{target:.2f}'] = {'validation_recall_target': target, 'threshold': cutoff,
                                   'validation': metrics(decision(val)), 'test': metrics(decision(test))}

    a = {int(row['source_row']): row for row in raw['jev']}
    b = {int(row['source_row']): row for row in raw['gemma_score']}
    votes = {}
    for rule, operation in [('at_least_one_positive', max), ('both_positive', min)]:
        votes[rule] = metrics([{**a[i], 'prediction': operation(int(a[i]['prediction']), int(b[i]['prediction']))}
                               for i in sorted(a)])
    positive_overlap = Counter((int(a[i]['prediction']), int(b[i]['prediction']))
                               for i in a if int(a[i]['label']) == 1)
    amount = result['jev']['cost_559_usd'] + result['gemma_score']['cost_559_usd']
    return {
        'method': 'Unweighted mean of independently calibrated JEV and Gemma scores; no fitted ensemble weights.',
        'weights': {'jev': .5, 'gemma4': .5},
        'fixed_threshold_0_5': metrics(test), 'average_precision': average_precision(test),
        'brier': sum((row['probability'] - row['label']) ** 2 for row in test) / len(test),
        'recall_target_study': targets, 'raw_0_5_hard_votes': votes,
        'raw_0_5_positive_overlap': {'both_detect': positive_overlap[1, 1],
                                   'jev_only': positive_overlap[1, 0], 'gemma_only': positive_overlap[0, 1],
                                   'both_miss': positive_overlap[0, 0]},
        'cost_559_usd': amount, 'cost_per_email_usd': amount / 559,
        'scaled_cost_per_million_usd': amount / 559 * 1_000_000,
        'limitations': 'Exploratory on an already inspected test set; calibration and cutoff selection share the validation sample. Combined latency and production gain are unmeasured.',
    }


def project(row, prevalence, n=100_000, minutes=3, hourly_usd=60):
    tp = n * prevalence * row['recall']
    fp = n * (1 - prevalence) * row['fpr']
    fn = n * prevalence * (1 - row['recall'])
    alerts = tp + fp
    return {'emails': n, 'prevalence': prevalence, 'true_alerts': tp,
            'false_alerts': fp, 'missed_positives': fn, 'alerts': alerts,
            'precision': tp / alerts, 'review_hours': alerts * minutes / 60,
            'review_cost_usd': alerts * minutes / 60 * hourly_usd,
            'api_cost_usd': n * row['cost_per_email_usd'],
            'api_cost_is_lower_bound': row['cost_is_lower_bound']}


def analyze(data):
    inputs = {}

    def load(name, kind='csv'):
        path = data / name
        content = path.read_bytes()
        inputs[name] = {'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
        if kind == 'json':
            return json.loads(content)
        if kind == 'jsonl':
            return [json.loads(line) for line in content.splitlines() if line]
        with path.open(newline='', encoding='utf-8-sig') as handle:
            return list(csv.DictReader(handle))

    raw = {key: load(filename) for key, (_, filename, _) in RUNS.items()}
    reference = {int(r['source_row']): r for r in raw['jev']}
    require(len(raw['jev']) == len(reference) == 559, 'Reference must have 559 unique rows')
    require(set(reference) == set(range(559)), 'Reference source IDs differ')
    require(sum(int(r['label']) for r in raw['jev']) == 73, 'Reference class balance differs')
    source = load('enron_labeled_curated_test.csv')
    require(len(source) == len(reference), 'Source count differs')
    for i, r in enumerate(source):
        # Historical requests used CRLF line endings, as in confidence_comparison.inputs.
        variants = [r['email'], r['email'].replace('\r\n', '\n').replace('\n', '\r\n')]
        hashes = {hashlib.sha256(email.encode()).hexdigest() for email in variants}
        require(reference[i]['email_sha256'] in hashes and r['label'] == reference[i]['label'],
                f'Source input or label mismatch: {i}')

    for key, rows in raw.items():
        ids = [int(r['source_row']) for r in rows]
        require(len(ids) == len(set(ids)) == 559 and set(ids) == set(reference), f'{key}: IDs differ')
        for r in rows:
            ref = reference[int(r['source_row'])]
            require(r['email_sha256'] == ref['email_sha256'] and r['label'] == ref['label'],
                    f'{key}: input/label mismatch')
            require(r['prediction'] in ('0', '1'), f'{key}: invalid prediction')
            require(r['cost'] != '' and float(r['cost']) >= 0, f'{key}: missing/invalid cost')
            if RUNS[key][2]:
                score = float(r['probability'])
                require(math.isfinite(score) and 0 <= score <= 1, f'{key}: invalid score')
                require(int(r['prediction']) == int(score >= .5), f'{key}: threshold mismatch')

    recovery = load('gemma4_reasoning_recovery_evaluation.json', 'json')
    attempts = load('gemma4_reasoning_recovery_attempts.jsonl', 'jsonl')
    historical = load('gemma4_include_reasoning_enabled_test_predictions.csv')
    extra_pilot = load('gemma4_include_reasoning_enabled_8192_test_predictions.csv')
    cost = lambda rows: sum(float(r['cost']) for r in rows)
    require(all(a.get('cost') not in ('', None) for a in attempts), 'Unknown recovery attempt cost')
    components = {
        'historical_successes_usd': cost(historical),
        'all_recovery_attempts_usd': cost(attempts),
        'extra_pilot_success_usd': cost(extra_pilot),
    }
    components['known_experiment_lower_bound_usd'] = sum(components.values())
    components['selected_559_successes_usd'] = cost(raw['gemma_recovered'])
    components['recovery_failed_attempts_usd'] = cost([a for a in attempts if a['status'] in ('response_error', 'request_error')])
    require(math.isclose(cost(attempts), recovery['recovery_known_cost_usd'], abs_tol=1e-12), 'Recovery cost mismatch')

    result = {}
    for key, (name, _, score_field) in RUNS.items():
        rows = raw[key]
        m = metrics(rows)
        amount = components['known_experiment_lower_bound_usd'] if key == 'gemma_recovered' else cost(rows)
        m.update(name=name, cost_559_usd=amount, cost_per_email_usd=amount/559,
                 cost_is_lower_bound=key == 'gemma_recovered',
                 average_precision=average_precision(rows) if score_field else None,
                 truncated=sum(str(r.get('truncated', '')).lower() == 'true' for r in rows),
                 models=sorted({r['model'] for r in rows}),
                 providers=sorted({r['provider'] for r in rows if r.get('provider')}))
        latency = [float(r['latency_seconds']) for r in rows if r.get('latency_seconds')]
        m['latency'] = ({'n': len(latency), 'p50_seconds': percentile(latency, .5),
                         'p95_seconds': percentile(latency, .95), 'max_seconds': max(latency)} if latency else None)
        result[key] = m

    confidence = load('confidence_comparison/evaluation.json', 'json')
    manifest = load('confidence_validation_manifest.json', 'json')
    recall_target_study = {}
    validation_by_model, scores_by_model = {}, {}
    for model, key in [('jev', 'jev'), ('gemma4', 'gemma_score')]:
        entry = confidence['models'][model]
        validation = load(f'{model}_probability_validation.csv')
        expected_hashes = dict(zip(manifest['validation_rows'], manifest['validation_email_sha256']))
        ids = [int(row['source_row']) for row in validation]
        require(len(ids) == len(set(ids)) == 500 and set(ids) == set(expected_hashes), 'Validation IDs differ')
        require(sum(int(row['label']) for row in validation) == 67, 'Validation class balance differs')
        for row in validation:
            require(row['email_sha256'] == expected_hashes[int(row['source_row'])], 'Validation input hash differs')
            require(row['config_sha256'] == entry['score_config_sha256'], 'Validation configuration differs')
        validation_by_model[model] = validation
        for target in [.90, .95]:
            # Select on validation labels only. The monotonic calibrator preserves this ordering.
            cutoff = max(score for score in {float(row['probability']) for row in validation}
                         if sum(int(row['label']) for row in validation if float(row['probability']) >= score) / 67 >= target)
            fitted = entry['calibrator']
            clipped = min(1 - 1e-12, max(1e-12, cutoff))
            z = fitted['slope'] * math.log(clipped / (1 - clipped)) + fitted['intercept']
            decision = lambda rows: [{**row, 'prediction': int(float(row['probability']) >= cutoff)} for row in rows]
            recall_target_study[f'{model}_target_{target:.2f}'] = {
                'model': model, 'validation_recall_target': target,
                'raw_cutoff': cutoff, 'calibrated_cutoff': 1 / (1 + math.exp(-z)),
                'validation': metrics(decision(validation)), 'test': metrics(decision(raw[key])),
            }
        for field in ['tp', 'fp', 'fn', 'tn']:
            require(entry['raw'][field] == result[key][field], f'{key}: saved metric mismatch')
        require(math.isclose(result[key]['average_precision'], entry['raw']['average_precision'], abs_tol=1e-12), 'AP mismatch')
        scored = load(f'confidence_comparison/{model}_test_probabilities.csv')
        require(len(scored) == 559 and len({int(r['source_row']) for r in scored}) == 559, 'Calibrated rows incomplete')
        originals = {int(r['source_row']): r for r in raw[key]}
        for r in scored:
            original = originals[int(r['source_row'])]
            require(r['label'] == original['label'] and float(r['raw_probability']) == float(original['probability']), 'Raw score mismatch')
            p = min(1-1e-12, max(1e-12, float(r['raw_probability'])))
            c = entry['calibrator']
            z = c['slope'] * math.log(p/(1-p)) + c['intercept']
            expected = 1 / (1 + math.exp(-z))
            require(math.isclose(expected, float(r['calibrated_probability']), abs_tol=1e-12), 'Calibration mismatch')
        scores_by_model[model] = scored
        for mode, threshold in [('calibrated', .5), ('validation_selected_threshold', entry['validation_selected_threshold']['threshold'])]:
            converted = [{**r, 'prediction': int(float(r['calibrated_probability']) >= threshold)} for r in scored]
            m = metrics(converted)
            for field in ['tp', 'fp', 'fn', 'tn']:
                require(m[field] == entry[mode][field], f'{model}/{mode}: count mismatch')
            m.update(name=result[key]['name'].replace('raw', mode.replace('_', ' ')),
                     threshold=threshold, cost_559_usd=result[key]['cost_559_usd'],
                     cost_per_email_usd=result[key]['cost_per_email_usd'], cost_is_lower_bound=False,
                     average_precision=result[key]['average_precision'])
            result[f'{key}_{mode}'] = m

    ensemble = ensemble_analysis(validation_by_model, scores_by_model, raw, confidence, result)

    annotations = load('enron_labeled_curated_test_with_news.csv')
    require(len(annotations) == len(source), 'Annotation count mismatch')
    for a, s in zip(annotations, source):
        require(a['email'] == s['email'] and a['label'] == s['label'], 'Annotation source mismatch')
    exclude = raw['gemma_exclude']
    non_news = [r for r in exclude if annotations[int(r['source_row'])]['news_label'] == '0']
    policy_rows = [{**r, 'label': int(r['label']) * (annotations[int(r['source_row'])]['news_label'] == '0')} for r in exclude]
    news = {'non_news_subset': metrics(non_news), 'policy_aligned_all_rows': metrics(policy_rows),
            'annotated_news': sum(r['news_label'] == '1' for r in annotations),
            'positive_news': sum(r['news_label'] == '1' and r['label'] == '1' for r in annotations)}

    paired = {}
    for base in ['gemma_score', 'jev']:
        old = {int(r['source_row']): r for r in raw[base]}
        changes = Counter()
        for r in raw['gemma_recovered']:
            previous = old[int(r['source_row'])]
            if r['prediction'] != previous['prediction']:
                changes[f'label_{r["label"]}_{previous["prediction"]}_to_{r["prediction"]}'] += 1
        paired[f'recovered_vs_{base}'] = dict(changes)

    keys = ['jev', 'jev_calibrated', 'gemma_score', 'gemma_score_calibrated', 'gemma_recovered']
    scenarios = {str(p): {key: project(result[key], p) for key in keys} for p in [.001, .01, 73/559]}
    return {'report_date': '2026-10-02', 'benchmark': {'emails': 559, 'positives': 73, 'negatives': 486,
            'prevalence': 73/559, 'unique_normalized_test_emails': manifest['unique_test_emails'],
            'validation_emails': len(manifest['validation_rows']), 'validation_positives': manifest['validation_positives']},
            'runs': result, 'recovery_cost_components': components,
            'recovery_attempt_status_counts': dict(Counter(a['status'] for a in attempts)),
            'confidence': confidence, 'recall_target_study': recall_target_study, 'ensemble': ensemble,
            'news_policy': news, 'paired_changes': paired,
            'scenarios': scenarios, 'scenario_assumptions': {'monthly_emails': 100_000,
                'minutes_per_alert': 3, 'reviewer_hourly_cost_usd': 60,
                'note': 'Sensitivity analysis assumes benchmark recall and false-positive rate transfer; not a production forecast.'},
            'inputs': inputs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT/'data')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/email_monitoring_metrics.json')
    args = parser.parse_args()
    report = analyze(args.data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(f'Wrote {args.output}: six verified runs, four calibrated operating points, four validation recall targets, and ensemble analysis.')


if __name__ == '__main__':
    main()
