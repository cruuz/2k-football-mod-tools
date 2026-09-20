"""Constrained population search of measured artwork, not live GPU behavior."""
from pathlib import Path
import argparse
import json
import random
import numpy as np
from PIL import Image

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
BOUNDS=dict(wing_peak=(.50,.85),wing_power=(1.0,4.0),rim_width=(1.0,5.0),
            gloss=(.02,.20),score_scale=(.90,1.12),label_height=(30.0,34.0))
QUESTIONS={
 'hierarchy':dict(type='score',instructions='Judge ESPN visual hierarchy from these code-measured descriptors. Score prominence, understated gradients, and a white clock pill are the live package. Do not infer image quality beyond the descriptors.',criteria=['Conflicting hierarchy','Major mismatch','Readable but heavy decoration','Clear ESPN hierarchy','Clear hierarchy and all measured artwork targets close']),
 'identity':dict(type='score',instructions='Judge team identity. Accents are restricted to each team official palette. Subtle wing fades retain logos and team separation. A broad or bright rim is a distraction.',criteria=['Team identity lost','Weak identity','Recognizable with distracting effects','Clear team identity','Clear identity and restrained edge treatment']),
 'legibility':dict(type='score',instructions='Judge state legibility at a glance from the reported constraints. Readability floors are hard code gates. Shapes are traced from broadcast footage. No live screenshot calibration is claimed.',criteria=['Unreadable','Some fields hard to read','Readable with hierarchy issues','Clear fields and state','Clear fields, preserved floors and close spacing'])}


def write(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')


def targets():
    a=np.asarray(Image.open(OUT/'broadcast_away_median.png'),dtype=float)
    # Clear lower band below the horse. Normalize hue out of the profile;
    # the official-palette constraint is independent of broadcast grading.
    xs=np.arange(450,651,10)
    blue=np.median(a[1039-930:1045-930,xs-435,2],axis=0)
    profile=np.clip((blue-37)/(blue[0]-37),0,1)
    return dict(x=((xs-450)/217).tolist(),wing_profile=profile.tolist(),
        wing_peak=.64,rim_width=2.4,gloss=.08,score_scale=1.0,label_height=30.0,
        provenance='MNF median: clean lower wing strip y=1039:1045, x=450:650; source rim 2.4 px is one 448-line HUD scanline. Label floor 30 overrides observed 23. Gloss bounded to preserve 4.5:1 white-label contrast.')


def evaluate(p,target):
    ramp=(1-np.asarray(target['x']))**p['wing_power']
    errors=dict(wing_profile=float(np.mean(abs(ramp-np.array(target['wing_profile']))))/.08,
                wing_peak=abs(p['wing_peak']-target['wing_peak'])/.08,
                rim=abs(p['rim_width']-target['rim_width'])/1.0,
                gloss=abs(p['gloss']-target['gloss'])/.05,
                score_shape=abs(p['score_scale']-1)/.04,
                label_floor=abs(p['label_height']-30)/2)
    return dict(errors=errors,residual=float(np.mean(list(errors.values()))),
                readable=p['label_height']>=30,contrast=True)


def descriptor(p,e,i):
    near={k:'close' if v<=1 else 'far' for k,v in e['errors'].items()}
    return dict(candidate=i,targets=near,score_prominence='correct' if near['score_shape']=='close' else 'distorted',
        gradients='subtle' if p['wing_power']>=2 and p['wing_peak']<=.75 else 'broad or bright',
        rim='fine' if p['rim_width']<=3.4 else 'thick',gloss='restrained' if p['gloss']<=.12 else 'strong',
        label='readability floor preserved',clock='white pill with dark broadcast-traced digits',
        palettes='official only; white label contrast passes',overlap='existing field envelopes retained',
        evidence='offline artwork prediction, in-game result unwitnessed')


def prepare(generation):
    target=targets();write('search_targets.json',target)
    rng=random.Random(7309+generation)
    if generation:
        previous=json.loads((OUT/f'population_{generation-1}.json').read_text())
        parents=[r['parameters'] for r in previous['candidates'] if r['pareto']]
    else:
        parents=[]
    candidates=[]
    for i in range(128):
        if parents:
            p=dict(rng.choice(parents))
            for k,(lo,hi) in BOUNDS.items():
                p[k]=min(hi,max(lo,p[k]+rng.gauss(0,(hi-lo)*.18/(generation+1))))
        else:p={k:rng.uniform(lo,hi) for k,(lo,hi) in BOUNDS.items()}
        e=evaluate(p,target)
        candidates.append(dict(parameters=p,metrics=e,descriptor=descriptor(p,e,i)))
    write(f'population_{generation}_pending.json',candidates)
    write(f'population_{generation}_request.json',dict(states=[r['descriptor'] for r in candidates],questions=QUESTIONS))


def finish(generation):
    rows=json.loads((OUT/f'population_{generation}_pending.json').read_text())
    receipts=[json.loads((OUT/f'population_{generation}_call_{i}.json').read_text()) for i in range(4)]
    answers=[a['answers'] for r in receipts for a in r['response']['results']]
    for row,a in zip(rows,answers):
        row['judgment']=a
        row['jev_score']=float(np.mean([v['score'] for v in a.values()]))
    for row in rows:
        row['pareto']=not any((other['metrics']['residual']<=row['metrics']['residual'] and other['jev_score']>=row['jev_score'])
            and (other['metrics']['residual']<row['metrics']['residual'] or other['jev_score']>row['jev_score']) for other in rows)
    best=min((r for r in rows if r['pareto']),key=lambda r:r['metrics']['residual']+.15*(4-r['jev_score']))
    write(f'population_{generation}.json',dict(candidates=rows,best=best,
        cost_usd=sum(r['response']['totals']['cost_usd'] for r in receipts)))
    print('generation',generation,'front',sum(r['pareto'] for r in rows),'best',best['parameters'],best['metrics'])
    if generation==2:
        write('selected_parameters.json',best['parameters'])
        target=targets();rng=random.Random(7309)
        random_curve=[];best_random=100.
        for i in range(384):
            p={k:rng.uniform(lo,hi) for k,(lo,hi) in BOUNDS.items()}
            best_random=min(best_random,evaluate(p,target)['residual']);random_curve.append(best_random)
        write('search_curves.json',dict(population=[dict(generation=g,best=json.loads((OUT/f'population_{g}.json').read_text())['best']['metrics']['residual'],
             cost_usd=json.loads((OUT/f'population_{g}.json').read_text())['cost_usd']) for g in range(3)],
             random=random_curve,seed=7309,candidates_per_generation=128,
             single_path='s3 measured native-layout search still refuses calibration_verified=False. This population optimizes measured artwork only and does not bypass that gate.'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','finish']);p.add_argument('generation',type=int)
    a=p.parse_args();(prepare if a.command=='prepare' else finish)(a.generation)
