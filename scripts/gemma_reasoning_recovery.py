"""Resume missing reasoning rows, preserving legacy successes and recording retries."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import csv
import hashlib
import json
from pathlib import Path
import threading
from datetime import datetime, timezone
from scripts import gemma4_openrouter as g
from scripts.confidence_comparison import load_key, read_csv

DATA=Path(__file__).resolve().parents[1]/'data'
SAMPLING=None  # Preserve the original temperature=0; omit top_p/top_k overrides.
SEED=2
CAPS=(4096,8192,16384)
FALLBACK_PROVIDER="darkbloom"
ATTEMPTS=[(cap,None,None) for cap in CAPS]+[(4096,FALLBACK_PROVIDER,1.1),(8192,FALLBACK_PROVIDER,1.1)]
JOURNAL=DATA/'gemma4_reasoning_recovery_attempts.jsonl'
OUTPUT=DATA/'gemma4_include_reasoning_recovered_test_predictions.csv'
SUMMARY=DATA/'gemma4_reasoning_recovery_evaluation.json'
FIELDS=g.OUTPUT_FIELDS+['reasoning_enabled','reasoning_tokens','reasoning_returned',
        'latency_seconds','provider','max_output_tokens','temperature','top_p','top_k','seed','requested_provider','repetition_penalty','origin']
lock=threading.Lock()


def digest(text):return hashlib.sha256(text.encode()).hexdigest()


def source_rows():
    rows=g.load_labeled_rows(DATA/'enron_labeled_curated_test.csv')
    baseline=read_csv(DATA/'gemma4_include_test_predictions.csv')
    lookup={int(r['source_row']):r for r in baseline}
    if len(lookup)!=len(baseline) or set(lookup)!=set(range(len(rows))):raise ValueError('Invalid baseline IDs')
    for r in rows:
        old=lookup[r['source_row']]
        if int(old['label'])!=r['label']:raise ValueError('Historical label mismatch')
        variants=[r['email'],r['email'].replace('\r\n','\n').replace('\n','\r\n')]
        r['email']=next((e for e in variants if digest(e)==old['email_sha256']),None)
        if r['email'] is None:raise ValueError('Historical email mismatch')
    return rows


def history():
    return [json.loads(line) for line in JOURNAL.read_text().splitlines()] if JOURNAL.exists() else []


def validate_saved(row,source,cap,sampling,seed=None,provider_only=None,repetition_penalty=None):
    if (int(row['label'])!=source['label'] or row['email_sha256']!=digest(source['email'])
        or row['config_sha256']!=g.config_hash(news_policy='include',reasoning_enabled=True,max_output_tokens=cap,sampling=sampling,seed=seed,provider_only=provider_only,repetition_penalty=repetition_penalty)
        or str(row['reasoning_enabled']).lower()!='true' or int(row['prediction']) not in (0,1)):
        raise ValueError(f"Saved row {source['source_row']} failed verification")


def completed(rows,attempts):
    source={r['source_row']:r for r in rows};saved={}
    for cap,suffix in [(4096,''),(8192,'_8192')]:
        path=DATA/f'gemma4_include_reasoning_enabled{suffix}_test_predictions.csv';seen=set()
        if not path.exists():continue
        for r in read_csv(path):
            i=int(r['source_row'])
            if i in seen or i not in source:raise ValueError('Duplicate or invalid legacy row')
            seen.add(i);validate_saved(r,source[i],cap,None)
            saved.setdefault(i,{**r,'max_output_tokens':cap,'temperature':0,'top_p':'','top_k':'','seed':'','origin':f'legacy_{cap}'})
    for attempt in attempts:
        if attempt['status']!='success':continue
        r=attempt['result'];i=int(r['source_row'])
        validate_saved(r,source[i],int(r['max_output_tokens']),SAMPLING,SEED,r.get('requested_provider') or None,r.get('repetition_penalty') or None)
        if i in saved:raise ValueError('Recovery duplicated a completed email')
        saved[i]=r
    return saved


def write_attempt(record):
    with lock,JOURNAL.open('a',encoding='utf-8') as f:
        f.write(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),**record})+'\n');f.flush()


def recover_one(row,key,previous):
    used={(int(a['max_output_tokens']),a.get('provider_only'),a.get('repetition_penalty')) for a in previous if a['source_row']==row['source_row'] and a['status']!='request_error'}
    for cap,provider_only,repetition_penalty in ATTEMPTS:
        if (cap,provider_only,repetition_penalty) in used:continue
        common={'source_row':row['source_row'],'max_output_tokens':cap,'sampling':SAMPLING,'seed':SEED,'provider_only':provider_only,'repetition_penalty':repetition_penalty}
        try:
            result=g.classify_email(row['email'],key,news_policy='include',reasoning_enabled=True,max_output_tokens=cap,sampling=SAMPLING,seed=SEED,provider_only=provider_only,repetition_penalty=repetition_penalty)
            result={**result,'source_row':row['source_row'],'label':row['label'],'email_sha256':digest(row['email']),
                    'config_sha256':g.config_hash(news_policy='include',reasoning_enabled=True,max_output_tokens=cap,sampling=SAMPLING,seed=SEED,provider_only=provider_only,repetition_penalty=repetition_penalty),
                    'max_output_tokens':cap,'temperature':0,'top_p':'','top_k':'','seed':SEED,'requested_provider':provider_only or '', 'repetition_penalty':repetition_penalty or '', 'origin':'recovery'}
            write_attempt({**common,'status':'success','result':result,'cost':result.get('cost')})
            return result
        except g.ClassificationResponseError as error:
            write_attempt({**common,'status':'response_error','error':str(error),**error.metadata})
            if error.metadata['finish_reason']!='length':return None
        except Exception as error:
            write_attempt({**common,'status':'request_error','error':type(error).__name__,'cost':None})
            raise
    return None


def summarize(rows):
    attempts=history();saved=completed(rows,attempts);temp=OUTPUT.with_suffix('.tmp')
    with temp.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(saved[i] for i in sorted(saved))
    temp.replace(OUTPUT)
    missing=sorted(set(r['source_row'] for r in rows)-set(saved))
    summary={'status':'complete' if not missing else 'incomplete','rows':len(saved),'expected_rows':len(rows),'missing_source_rows':missing,
             'legacy_rows':sum(r['origin'].startswith('legacy') for r in saved.values()),'recovered_rows':sum(r['origin']=='recovery' for r in saved.values()),
             'recovery_sampling':{'seed':SEED,'temperature':0,'top_p':'provider default','top_k':'provider default'},'recovery_max_output_tokens':list(CAPS),'recovery_attempts':len(attempts),
             'fallback_provider':FALLBACK_PROVIDER,'fallback_caps':[4096,8192],'fallback_repetition_penalty':1.1,
             'recovery_response_errors':sum(a['status']=='response_error' for a in attempts),
             'recovery_known_cost_usd':sum(float(a.get('cost') or 0) for a in attempts),
             'attempts_with_unknown_cost':sum(a.get('cost') in (None,'') for a in attempts),
             'reasoning_telemetry_rows':sum(r.get('reasoning_tokens') not in ('',None) for r in saved.values()),
             'rows_reporting_reasoning':sum(float(r.get('reasoning_tokens') or 0)>0 for r in saved.values()),
             'note':'Temperature 0 throughout; recovery seed=2, legacy seed unspecified; per-row token caps may differ, so this is a recovery workflow rather than a uniform-cap experiment. Historical failed/interrupted costs are not fully known.'}
    if not missing:summary['metrics']=g.evaluate(list(saved.values()))
    SUMMARY.write_text(json.dumps(summary,indent=2)+'\n');return summary


def run(pilot=False):
    rows=source_rows();attempts=history();saved=completed(rows,attempts)
    pending=[r for r in rows if r['source_row'] not in saved and (not pilot or r['source_row']==112)]
    print(f'Preserving {len(saved)} successes; requesting {len(pending)} missing rows.',flush=True)
    key=load_key()
    if pending and not key:raise ValueError('Missing OpenRouter key')
    errors=[]
    try:
        with ThreadPoolExecutor(max_workers=1 if pilot else 10) as pool:
            remaining=iter(pending)
            futures={pool.submit(recover_one,r,key,attempts):r for r in [next(remaining,None) for _ in range(1 if pilot else 10)] if r is not None}
            processed=0
            while futures:
                future=next(as_completed(futures));row=futures.pop(future)
                try:
                    result=future.result()
                    if result is None:print('Unresolved row:',row['source_row'],flush=True)
                    elif row['source_row']==112:print('Row 112 recovered; reasoning tokens:',result['reasoning_tokens'],flush=True)
                except Exception as error:errors.append(error)
                processed+=1
                if processed%20==0:print(f'Processed {processed}/{len(pending)} missing rows',flush=True)
                if not errors:
                    nxt=next(remaining,None)
                    if nxt is not None:futures[pool.submit(recover_one,nxt,key,attempts)]=nxt
    finally:
        summary=summarize(rows)
        print(json.dumps({k:summary[k] for k in ['status','rows','legacy_rows','recovered_rows','recovery_known_cost_usd']}),flush=True)
    if errors:raise RuntimeError('Recovery stopped after a request error; see attempt journal') from errors[0]
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pilot',action='store_true');parser.add_argument('--run',action='store_true');args=parser.parse_args()
    if args.pilot or args.run:run(pilot=args.pilot)
    else:print(json.dumps(summarize(source_rows()),indent=2))
