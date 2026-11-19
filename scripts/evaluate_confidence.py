"""Offline probability calibration and held-out evaluation (NumPy only)."""
from __future__ import annotations
import csv
import json
from pathlib import Path
import numpy as np
from scripts.confidence_comparison import DATA, read_csv, inputs, sha, score_config

EPS=1e-12

def sigmoid(z):
    z=np.asarray(z,dtype=float)
    return np.exp(-np.logaddexp(0,-z))

def logits(probabilities):
    p=np.clip(np.asarray(probabilities,dtype=float),EPS,1-EPS)
    return np.log(p)-np.log1p(-p)

def fit_calibrator(probabilities, labels):
    """Fixed L2=1 slope penalty; validation data only, no test-driven tuning."""
    x=np.column_stack([logits(probabilities),np.ones(len(labels))]);y=np.asarray(labels,dtype=float)
    if set(y)!={0.,1.}:raise ValueError('Calibration requires both classes')
    beta=np.array([1.,0.]);penalty=np.array([1.,0.])
    def loss(b):
        z=x@b
        return np.sum(np.logaddexp(0,z)-y*z)+.5*np.sum(penalty*b*b)
    for _ in range(100):
        p=sigmoid(x@beta)
        gradient=x.T@(p-y)+penalty*beta
        hessian=x.T@((p*(1-p))[:,None]*x)+np.diag(penalty)+np.eye(2)*1e-10
        step=np.linalg.solve(hessian,gradient)
        scale=1.
        while loss(beta-scale*step)>loss(beta) and scale>1e-8:scale*=.5
        beta-=scale*step
        if np.max(np.abs(scale*step))<1e-8:break
    if beta[0]<=0:raise ValueError('Calibration reversed ordering; inspect scores')
    return {'slope':float(beta[0]),'intercept':float(beta[1]),'clip_epsilon':EPS,'slope_l2':1.0}

def calibrate(p, parameters):
    return sigmoid(parameters['slope']*logits(p)+parameters['intercept'])

def classification(y,p,threshold=.5):
    y=np.asarray(y,dtype=int);pred=np.asarray(p)>=threshold
    tp=int(np.sum((y==1)&pred));fp=int(np.sum((y==0)&pred));fn=int(np.sum((y==1)&~pred));tn=int(np.sum((y==0)&~pred))
    precision=tp/(tp+fp) if tp+fp else 0.;recall=tp/(tp+fn) if tp+fn else 0.
    return {'threshold':float(threshold),'tp':tp,'fp':fp,'fn':fn,'tn':tn,
            'precision':precision,'recall':recall,'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.}

def reliability(y,p):
    y=np.asarray(y);p=np.asarray(p);bands=[]
    for i in range(10):
        selected=(p>=i/10)&(p<(i+1)/10 if i<9 else p<=1)
        if selected.any():bands.append({'low':i/10,'high':(i+1)/10,'n':int(selected.sum()),'mean_probability':float(p[selected].mean()),'positive_fraction':float(y[selected].mean())})
    return bands

def scores(y,p):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float)
    if len(y)!=len(p) or not np.all(np.isfinite(p)) or np.any((p<0)|(p>1)):raise ValueError('Invalid probabilities')
    pos=p[y==1];neg=p[y==0]
    auc=float(((pos[:,None]>neg).sum()+.5*(pos[:,None]==neg).sum())/(len(pos)*len(neg)))
    # Group ties before integrating stepwise precision (average precision).
    ap=0.;last_recall=0.
    for t in sorted(set(p),reverse=True):
        m=classification(y,p,t);ap+=(m['recall']-last_recall)*m['precision'];last_recall=m['recall']
    c=np.clip(p,1e-15,1-1e-15);bins=reliability(y,p)
    return {**classification(y,p),'n':len(y),'brier':float(np.mean((p-y)**2)),
            'log_loss':float(-np.mean(y*np.log(c)+(1-y)*np.log1p(-c))),
            'roc_auc':auc,'average_precision':ap,
            'ece_10_bins':sum(b['n']*abs(b['mean_probability']-b['positive_fraction']) for b in bins)/len(y)}

def choose_threshold(y,p):
    candidates=[classification(y,p,t) for t in sorted(set(p))]
    return max(candidates,key=lambda r:(r['f1'],r['precision'],r['threshold']))['threshold']

def load_verified(path, expected):
    rows=read_csv(path);ids=[int(r['source_row']) for r in rows]
    if len(ids)!=len(set(ids)) or set(ids)!={r['source_row'] for r in expected}:raise ValueError(f'Incomplete or duplicate rows: {path}')
    expected_by_id={r['source_row']:r for r in expected}
    for row in rows:
        source=expected_by_id[int(row['source_row'])]
        if row['email_sha256']!=sha(source['email']) or int(row['label'])!=source['label']:
            raise ValueError(f'Input or label mismatch: {path}')
    return sorted(rows,key=lambda r:int(r['source_row']))

def svg_plot(series,path,kind):
    colors=['#1d4ed8','#0891b2','#dc2626','#d97706']
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="760" height="540" viewBox="0 0 760 540">',
           '<rect width="760" height="540" fill="white"/><style>text{font:14px sans-serif;fill:#222}</style>']
    for t in np.linspace(0,1,6):
        x=70+600*t;y=430-350*t
        parts.extend([f'<path d="M{x},80V430 M70,{y}H670" stroke="#ddd"/>',f'<text x="{x}" y="453" text-anchor="middle">{t:.1f}</text>',f'<text x="55" y="{y+5}" text-anchor="end">{t:.1f}</text>'])
    if kind=='calibration':parts.append('<path d="M70,430L670,80" stroke="#888" stroke-dasharray="5 5"/>')
    for index,(name,y,p) in enumerate(series):
        if kind=='calibration':points=[(b['mean_probability'],b['positive_fraction']) for b in reliability(y,p)]
        else:
            points=[(0,1)]+[(classification(y,p,t)['recall'],classification(y,p,t)['precision']) for t in sorted(set(p),reverse=True)]
        coords=' '.join(f'{70+600*x:.2f},{430-350*z:.2f}' for x,z in points)
        color=colors[index]
        parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2"/>')
        if kind=='calibration':
            for x,z in points:parts.append(f'<circle cx="{70+600*x:.2f}" cy="{430-350*z:.2f}" r="3" fill="{color}"/>')
        parts.append(f'<text x="{75+(index%2)*315}" y="{25+(index//2)*25}" style="fill:{color}">{name}</text>')
    xlabel,ylabel=('Mean predicted probability','Observed positive fraction') if kind=='calibration' else ('Recall','Precision')
    parts.extend([f'<text x="370" y="485" text-anchor="middle">{xlabel}</text>',f'<text transform="translate(18 260) rotate(-90)" text-anchor="middle">{ylabel}</text>','<text x="70" y="520">Held-out test set; reliability bins may contain few examples.</text></svg>'])
    path.write_text(''.join(parts))

def evaluate():
    validation,test=inputs();report={'method':'L2-regularized sigmoid of clipped log odds; fit on 500 deduplicated validation emails only','models':{}};series=[]
    destination=DATA/'confidence_comparison';destination.mkdir(exist_ok=True)
    for name in ['jev','gemma4']:
        val=load_verified(DATA/f'{name}_probability_validation.csv',validation)
        tst=load_verified(DATA/('jev_test_predictions.csv' if name=='jev' else f'{name}_probability_test.csv'),test)
        expected_config=score_config('gemma' if name=='gemma4' else 'jev')
        for row in val + (tst if name=='gemma4' else []):
            if row['config_sha256'] != expected_config: raise ValueError('Score configuration mismatch')
        missing_val=[r for r in val if r.get('status','ok')!='ok'];missing_test=[r for r in tst if r.get('status','ok')!='ok']
        if missing_val or missing_test:raise ValueError(f'{name}: missing label probabilities in {len(missing_val)} validation and {len(missing_test)} test rows; cannot claim full coverage')
        v=np.array([float(r['probability']) for r in val]);vy=np.array([int(r['label']) for r in val]);p=np.array([float(r['probability']) for r in tst]);y=np.array([int(r['label']) for r in tst])
        params=fit_calibrator(v,vy);cp=calibrate(p,params);cv=calibrate(v,params)
        threshold=choose_threshold(vy,cv)
        entry={'score_config_sha256':expected_config,'calibrator':params,'raw':scores(y,p),'calibrated':scores(y,cp),
               'validation_selected_threshold':classification(y,cp,threshold),
               'validation_cost_usd':sum(float(r['cost'] or 0) for r in val),
               'test_cost_usd':sum(float(r['cost'] or 0) for r in tst),
               'test_models':sorted({r['model'] for r in tst}),'validation_models':sorted({r['model'] for r in val}),
               'reliability_raw':reliability(y,p),'reliability_calibrated':reliability(y,cp)}
        report['models'][name]=entry
        with (destination/f'{name}_test_probabilities.csv').open('w',newline='') as f:
            fields=['source_row','label','raw_probability','calibrated_probability','prediction','predicted_class_confidence']
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            for r,raw,c in zip(tst,p,cp):w.writerow({'source_row':r['source_row'],'label':r['label'],'raw_probability':raw,'calibrated_probability':c,'prediction':int(c>=.5),'predicted_class_confidence':max(c,1-c)})
        for mode,prob in [('raw',p),('calibrated',cp)]:series.append((f'{name} {mode}',y,prob))
    (destination/'evaluation.json').write_text(json.dumps(report,indent=2)+'\n')
    svg_plot(series,destination/'calibration.svg','calibration')
    svg_plot([series[0],series[2]],destination/'precision_recall.svg','pr')
    return report

if __name__=='__main__':
    r=evaluate()
    for name,e in r['models'].items():
        for mode in ['raw','calibrated']:print(name,mode,json.dumps(e[mode]))
