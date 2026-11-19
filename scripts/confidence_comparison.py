"""Compare Jev and non-reasoning Gemma probabilities without fitting on test labels."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts import gemma4_openrouter as gemma, jev_openrouter as jev

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
PROMPT = (gemma.BASE_INSTRUCTIONS.split(' Identify the source type')[0] + ' ' +
          gemma.NEWS_RULES['include'] +
          ' Output exactly one digit: 0 or 1. Do not output an explanation or other text.')
SETTINGS = {'model': gemma.MODEL, 'reasoning': {'enabled': False}, 'temperature': 1,
            'top_p': 1, 'max_tokens': 1, 'logprobs': True, 'top_logprobs': 20,
            'provider': {'only': ['darkbloom'], 'require_parameters': True}}
FIELDS = ['source_row', 'label', 'prediction', 'probability', 'status', 'logprob_0',
          'logprob_1', 'label_probability_mass', 'sampled_token', 'reasoning_tokens',
          'model', 'provider', 'request_id', 'input_tokens', 'output_tokens', 'cost',
          'truncated', 'email_sha256', 'config_sha256']


def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def canonical(email):
    return re.sub(r'\s+', ' ', email).strip()


def inputs():
    test = gemma.load_labeled_rows(DATA / 'enron_labeled_curated_test.csv')
    old = read_csv(DATA / 'jev_test_predictions.csv')
    by_id = {int(r['source_row']): r for r in old}
    if len(by_id) != len(old) or set(by_id) != {r['source_row'] for r in test}:
        raise ValueError('Jev test IDs do not match source')
    for row in test:
        saved = by_id[row['source_row']]
        variants = [row['email'], row['email'].replace('\r\n', '\n').replace('\n', '\r\n')]
        row['email'] = next((e for e in variants if sha(e) == saved['email_sha256']), None)
        if row['email'] is None or row['label'] != int(saved['label']):
            raise ValueError('Historical test input mismatch')
        if saved['config_sha256'] != jev.config_hash(jev.MODEL, jev.MAX_EMAIL_CHARS):
            raise ValueError('Historical Jev configuration mismatch')
        if int(saved['prediction']) != int(float(saved['probability']) >= .5):
            raise ValueError('Historical Jev threshold mismatch')
    train = gemma.load_labeled_rows(DATA / 'enron_labeled_curated_train.csv')
    test_keys = {canonical(r['email']) for r in test}
    groups = {}
    for row in train:
        groups.setdefault(canonical(row['email']), []).append(row)
    eligible = [rs[0] for key, rs in groups.items()
                if key not in test_keys and len({r['label'] for r in rs}) == 1]
    validation = sorted(random.Random(20261001).sample(eligible, 500), key=lambda r:r['source_row'])
    manifest = {'seed': 20261001, 'validation_source': 'enron_labeled_curated_train.csv',
                'validation_rows': [r['source_row'] for r in validation],
                'validation_email_sha256': [sha(r['email']) for r in validation],
                'eligible_unique_train_rows': len(eligible),
                'validation_positives': sum(r['label'] for r in validation),
                'test_rows': len(test), 'unique_test_emails': len(test_keys),
                'deduplication': 'Whitespace-normalized exact text; no near-duplicate or thread deduplication.'}
    path = DATA / 'confidence_validation_manifest.json'
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise ValueError('Validation sample changed; use separate experiment files')
    path.write_text(json.dumps(manifest, indent=2)+'\n')
    return validation, test


def parse_scores(result):
    choices = result.get('choices') or []
    if not choices:
        raise ValueError('Gemma returned no choices')
    choice = choices[0]
    message = choice.get('message') or {}
    usage = result.get('usage') or {}
    thinking = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
    if thinking not in (0, None) or message.get('reasoning') or message.get('reasoning_details'):
        raise ValueError('Gemma reported reasoning despite disabled setting')
    entries = (choice.get('logprobs') or {}).get('content') or []
    if len(entries) != 1:
        raise ValueError('Expected probabilities at exactly one output-token position')
    entry = entries[0]
    alternatives = {r['token']: float(r['logprob']) for r in entry.get('top_logprobs', [])}
    alternatives.setdefault(entry['token'], float(entry['logprob']))
    out = {'status': 'missing_label_probability', 'probability': '', 'prediction': '',
           'logprob_0': alternatives.get('0', ''), 'logprob_1': alternatives.get('1', ''),
           'label_probability_mass': '', 'sampled_token': entry['token'],
           'reasoning_tokens': thinking if thinking is not None else ''}
    if '0' in alternatives and '1' in alternatives:
        a,b = alternatives['0'], alternatives['1']
        if not all(math.isfinite(x) and -9999 < x <= 0 for x in (a,b)):
            raise ValueError('Invalid or censored label log probability')
        m = max(a,b)
        probability = math.exp(b-m)/(math.exp(a-m)+math.exp(b-m))
        out.update(status='ok', probability=probability, prediction=int(probability>=.5),
                   label_probability_mass=math.exp(a)+math.exp(b))
    out.update(model=result.get('model', gemma.MODEL), provider=result.get('provider',''),
               request_id=result.get('id',''), input_tokens=usage.get('prompt_tokens',''),
               output_tokens=usage.get('completion_tokens',''), cost=usage.get('cost',''))
    return out


def gemma_score(email, key):
    if not key:
        raise ValueError('OPENROUTER_API_KEY is required')
    payload = {**SETTINGS, 'messages': [{'role':'system','content':PROMPT},
               {'role':'user','content':'Classify this email:\n<email>\n'+email[:gemma.MAX_EMAIL_CHARS]+'\n</email>'}]}
    request = Request(gemma.API_URL, data=json.dumps(payload).encode(), headers={
        'Authorization':'Bearer '+key, 'Content-Type':'application/json'})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=90) as f:
                result = json.load(f)
            break
        except HTTPError as e:
            if e.code not in (429,500,502,503,504) or attempt==3:
                raise RuntimeError(f'Gemma HTTP {e.code}') from e
            time.sleep(2**attempt)
        except (URLError, TimeoutError):
            if attempt==3: raise
            time.sleep(2**attempt)
    return {**parse_scores(result), 'truncated':len(email)>gemma.MAX_EMAIL_CHARS}


def score_config(model):
    config = ({'settings':SETTINGS,'prompt':PROMPT,'max_email_chars':gemma.MAX_EMAIL_CHARS,
               'score':'normalized exact digit tokens at position zero; threshold 0.5'}
              if model=='gemma' else {'jev_config':jev.config_hash(jev.MODEL,jev.MAX_EMAIL_CHARS)})
    return sha(json.dumps(config,sort_keys=True))


def run_rows(rows, path, key, model, workers=10):
    fingerprint = score_config(model)
    previous = {}
    if path.exists():
        for r in read_csv(path):
            i=int(r['source_row'])
            if i in previous: raise ValueError('Duplicate saved prediction')
            previous[i]=r
    pending=[]
    for r in rows:
        old=previous.get(r['source_row'])
        if old:
            if old['email_sha256']!=sha(r['email']) or old['config_sha256']!=fingerprint or int(old['label'])!=r['label']:
                raise ValueError('Saved inputs or configuration mismatch')
        else: pending.append(r)
    if not pending: return [previous[r['source_row']] for r in rows]
    if not key: raise ValueError('OPENROUTER_API_KEY is required')
    def classify(row):
        result = gemma_score(row['email'],key) if model=='gemma' else {**jev.classify_email(row['email'],key),'status':'ok'}
        return {**result,'source_row':row['source_row'],'label':row['label'],
                'email_sha256':sha(row['email']),'config_sha256':fingerprint}
    with path.open('a',newline='') as f, ThreadPoolExecutor(max_workers=workers) as pool:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        if f.tell()==0: writer.writeheader()
        # Bound submitted work; a failure cannot leave hundreds of requests queued.
        remaining=iter(pending)
        futures={pool.submit(classify,r):r for r in [next(remaining,None) for _ in range(workers)] if r is not None}
        errors=[]
        while futures:
            future=next(as_completed(futures)); row=futures.pop(future)
            try:
                result=future.result();writer.writerow(result);f.flush();previous[row['source_row']]=result
                if len(previous)%25==0: print(path.stem,len(previous),'/',len(rows),flush=True)
            except Exception as e:
                errors.append((row['source_row'],e))
            if not errors:
                nxt=next(remaining,None)
                if nxt is not None:futures[pool.submit(classify,nxt)]=nxt
        if errors: raise RuntimeError(f'{model} failed at row {errors[0][0]}: {errors[0][1]}')
    return [previous[r['source_row']] for r in rows]


def load_key():
    key=os.environ.get('OPENROUTER_API_KEY','')
    if not key and (ROOT/'.env').exists():
        key=next((s.split('=',1)[1].strip() for s in (ROOT/'.env').read_text().splitlines() if s.startswith('OPENROUTER_API_KEY=')),'')
    return key


def collect():
    validation,test=inputs();key=load_key()
    print('Validation:',len(validation),'positives:',sum(r['label'] for r in validation),flush=True)
    # Pilot on both classes before dispatching the full Gemma batch.
    pilot=[next(r for r in validation if r['label']==label) for label in (0,1)]
    path=DATA/'gemma4_probability_validation.csv'
    result=run_rows(pilot,path,key,'gemma',workers=1)
    if any(r['status']!='ok' for r in result):raise ValueError('Pilot lacks both label probabilities')
    print('Gemma probability pilot passed',flush=True)
    run_rows(validation,path,key,'gemma')
    run_rows(test,DATA/'gemma4_probability_test.csv',key,'gemma')
    run_rows(validation,DATA/'jev_probability_validation.csv',key,'jev')

def predict_with_confidence(email, model='gemma4', api_key=None):
    """Use the saved validation calibrator for one new email (incurs API cost)."""
    if model not in ('gemma4', 'jev'):
        raise ValueError("model must be 'gemma4' or 'jev'")
    report=json.loads((DATA/'confidence_comparison/evaluation.json').read_text())
    fitted=report['models'][model]
    if fitted['score_config_sha256'] != score_config('gemma' if model=='gemma4' else 'jev'):
        raise ValueError('Calibrator does not match current scoring configuration')
    key=api_key or load_key()
    raw=gemma_score(email,key) if model=='gemma4' else jev.classify_email(email,key)
    if raw.get('status','ok')!='ok':
        raise ValueError('Both label probabilities are required; no confidence available')
    from scripts.evaluate_confidence import calibrate
    p=float(calibrate([raw['probability']],fitted['calibrator'])[0])
    return {**raw,'raw_probability':raw['probability'],'probability':p,'calibrated_probability':p,
            'prediction':int(p>=.5),'predicted_class_confidence':max(p,1-p)}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--collect',action='store_true')
    args=parser.parse_args()
    if args.collect:collect()
