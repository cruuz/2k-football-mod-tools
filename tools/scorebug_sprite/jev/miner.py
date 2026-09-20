"""Broadcast state requests and confidence-gated clustering; no pixel model."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from tools.scorebug_sprite.jev.descriptors import STATES,describe,compact

QUESTIONS=dict(state=dict(type='choice',instructions='Classify the broadcast scorebug using only measured facts. Prefer absent if the bar is absent. Use other when text is uncertain or needed evidence is unknown. Do not invent clock, yard line or scoring events.',criteria={s:None for s in STATES}),
               clean=dict(type='noul',instructions='Is this a clean representative of the chosen state? Reject unreadable or uncertain text, transitions and unknown banners, unless the bar is absent.'))
REPRODUCIBLE={'normal','kickoff','first_and_ten','short_yardage','third_and_long','fourth_down','red_zone','goal_to_go','flag','timeout','two_minute','end_of_quarter','absent'}


def prepare(frames,output,limit=200):
    files=sorted(Path(frames).glob('frame_*.jpg'))[::10]
    if limit and len(files)>limit:
        files=[files[round(i*(len(files)-1)/(limit-1))] for i in range(limit)]
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    descriptors=[];requests=[]
    for f in files:
        d=describe(f);d.update(frame=f.name,sha256=hashlib.sha256(f.read_bytes()).hexdigest())
        descriptors.append(d);requests.append(dict(tool='jev_ask',state=compact(d),questions=QUESTIONS))
    for name,value in [('descriptors.json',descriptors),('requests.json',requests)]:
        (output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
    return requests


def cluster(descriptors,answers):
    if len(descriptors)!=len(answers):raise ValueError('One answer is required per descriptor')
    import numpy as np
    groups={s:[] for s in STATES};rejected=[]
    for d,a in zip(descriptors,answers):
        a=a.get('answers',a);decision=a.get('state',{});state=decision.get('choice','other')
        if state not in groups:state='other'
        if decision.get('confidence',0)<.6 or a.get('clean',{}).get('noul',0)<.8:
            rejected.append(dict(frame=d['frame'],state=state,reason='confidence_or_clean_gate'));continue
        groups[state].append(d)
    normal=groups['normal'] or groups['first_and_ten']
    reference=normal[len(normal)//2] if normal else None
    result={}
    for state,rows in groups.items():
        if not rows:
            result[state]=dict(representatives=[],game_reproducible=state in REPRODUCIBLE,observed=False);continue
        # Deterministic medoid of measured luminance vectors.
        vectors=np.array([[v['luma'][1] for v in d['fields'].values()] for d in rows])
        center=np.median(vectors,axis=0);order=np.argsort(abs(vectors-center).mean(1))[:3]
        reps=[]
        for i in order:
            d=rows[int(i)];deltas={k:round(d['fields'][k]['luma'][1]-reference['fields'][k]['luma'][1],2) for k in d['fields']} if reference else None
            reps.append(dict(frame=d['frame'],sha256=d['sha256'],median_luma_delta_from_normal=deltas))
        result[state]=dict(representatives=reps,game_reproducible=state in REPRODUCIBLE,observed=True,count=len(rows))
    return dict(schema='scorebug-broadcast-states/v1',sampling='every tenth source frame; pilot stratified across that subset',
                normal_reference=reference['frame'] if reference else None,states=result,rejected=rejected,
                limitations=['State reproducibility describes retail predicates, not authored event banners.','Uncertain frames are retained for review, not assigned invented labels.'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--frames',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int,default=200)
    a=p.parse_args();print('Prepared',len(prepare(a.frames,a.output,a.limit)),'text-only requests')

if __name__=='__main__':main()
