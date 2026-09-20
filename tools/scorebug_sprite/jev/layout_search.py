"""Measured greedy layout search and equal-budget random proposal control.

The evaluator owns rendering and arithmetic. Jev proposes one bounded input;
it cannot override a worsening objective or an unverified calibration.
"""
from copy import deepcopy
import random

NUDGES=dict(label_larger='Increase down label cap by one HUD pixel',
            label_smaller='Decrease down label cap by one HUD pixel',
            label_left='Move down label one HUD pixel left',label_right='Move down label one HUD pixel right',
            label_up='Move down label one HUD pixel up',label_down='Move down label one HUD pixel down',
            tracking_tighter='Reduce label advances by one source pixel',
            tracking_looser='Increase label advances by one source pixel',none='Keep the current layout')


def nudge(spec,name,aspect='16:9'):
    if name not in NUDGES:raise ValueError('Unlisted Jev input')
    out=deepcopy(spec);label=next(f for f in out['fields'] if f['name']=='down')
    dx=3 if aspect=='16:9' else 2.25;dy=1080/448
    if name in ('label_larger','label_smaller'):
        label['size']+=dy*(1 if name=='label_larger' else -1)
        label['size']=max(12,min(40,label['size']))
    elif name in ('label_left','label_right','label_up','label_down'):
        axis=0 if name in ('label_left','label_right') else 1
        change=(dx if axis==0 else dy)*(-1 if name in ('label_left','label_up') else 1)
        label['anchor'][axis]+=change
        label['box'][axis]+=change;label['box'][axis+2]+=change
    elif name.startswith('tracking_'):
        for g in out['glyph_sets'][label['glyph_set']]['glyphs'].values():
            g['advance']=max(g['size'][0],g['advance']+(1 if name=='tracking_looser' else -1))
    return out


def objective(residuals,readability):
    """Each residual supplies its measured error and independent tolerance."""
    if not residuals:raise ValueError('Measured residuals are required')
    normalized=[abs(r['error'])/r['tolerance'] for r in residuals if r['tolerance']>0]
    if len(normalized)!=len(residuals):raise ValueError('Positive tolerances are required')
    penalties=sum(10 for passed in readability.values() if not passed)
    return sum(normalized)/len(normalized)+penalties


def request(residuals,readability,history=(),calibration_verified=False):
    return dict(tool='jev_next_input',goal='every field readable and within tolerance of ESPN',
        state=dict(calibration='verified' if calibration_verified else 'unresolved',
            features={r['feature']:'within' if abs(r['error'])<=r['tolerance'] else 'near' if abs(r['error'])<=2*r['tolerance'] else 'far' for r in residuals},
            readability=readability),allowed_inputs=NUDGES,history=list(history),act_threshold=.8)


def run(spec,evaluate,decide,*,steps=12,aspect='16:9',calibration_verified=False,seed=72):
    if not calibration_verified:
        raise ValueError('Search is blocked until screenshot calibration passes. No layout was changed.')
    start=evaluate(spec);initial=objective(start['residuals'],start['readability'])
    curves={};final=spec
    for mode in ('jev','random'):
        rng=random.Random(seed);current=deepcopy(spec);measured=deepcopy(start);score=initial;history=[];curve=[]
        for step in range(steps):
            choice=decide(request(measured['residuals'],measured['readability'],history,True)) if mode=='jev' else dict(next_input=rng.choice(list(NUDGES)),goal_reached=0,confidence=1)
            proposal=choice.get('next_input','none');history.append(proposal)
            code_pass=all(abs(r['error'])<=r['tolerance'] for r in measured['residuals']) and all(measured['readability'].values())
            reached=choice.get('goal_reached_p',0)>=.9 and code_pass
            candidate=nudge(current,proposal,aspect);trial=evaluate(candidate);trial_score=objective(trial['residuals'],trial['readability'])
            keep=choice.get('confidence',0)>=.8 and trial_score<score
            if keep:current,measured,score=candidate,trial,trial_score
            curve.append(dict(step=step,input=proposal,proposed_objective=trial_score,objective=score,kept=keep,goal_reached=reached))
            # Random gets exactly the same number of trials as Jev.
            if reached and mode=='jev':steps=len(curve);break
        curves[mode]=curve
        if mode=='jev':final=current
    return final,dict(initial_objective=initial,curves=curves,seed=seed)
