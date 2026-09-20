from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from tools.scorebug_sprite.jev import session,accents
out=ROOT/'reports/b72_s5/accents';data=json.loads((ROOT/'data/nfl2k5_scorebug_sprite/team_accents.json').read_text());proposals=json.loads((out/'proposals.json').read_text())
s=session.Session(ROOT/'reports/b72_s5');review=[];decisions=[]
for rec in json.loads((out/'responses.json').read_text()):
 r=rec['request'];response=rec['response'];s.record(r,response);a=session.answers(response);name=r['state']['team'];t=data['teams'][name]
 one,two=(a[k] for k in ('choice_a','choice_b'));agreed=one['choice']==two['choice'] and min(one['confidence'],two['confidence'])>=.8 and one['choice']!='defer'
 if agreed and one['choice']=='proposed':t.update(proposals[name])
 reasons=[]
 if not agreed:reasons.append('Jev group choice did not agree at confidence >= 0.8; retained code-valid prior group')
 for role in ('wing','rim','plate'):
  candidates=[c for c in t['candidates'].values() if c['hex']==t[role]]
  assert candidates and all(c['parent'] in t['official'] for c in candidates) and accents.contrast(accents.rgb(t[role]))>=4.5
  if any(e.get('confidence')=='low' and e['hex'].upper() in {c['parent'] for c in candidates} for e in t.get('palette_evidence',[])):reasons.append(role+': supplied source shade remains low confidence')
 t['review_required']=bool(reasons)
 if reasons:review.append(dict(team=name,reasons=reasons))
 decisions.append(dict(team=name,applied=agreed,choice=one['choice'],answers=a,reasons=reasons))
# Noah explicitly requests silver and black for the Raiders. Keep the reviewed
# silver-derived wing/rim and select official black for the possession plate.
data['teams']['LV']['plate']='#000000'
# Native identity is asset code + kind. Historical teams sharing it must have
# one tint group. No choice introduces a colour outside their common palette.
pal=json.loads((ROOT/'reports/b72_s3/official_accents/palettes.json').read_text())['teams'];by_identity={}
for name,t in data['teams'].items():
 t['kind']=pal[name]['kind'];key=(t['asset_code'],t['kind'])
 if key in by_identity:
  first=by_identity[key]
  for role in ('wing','rim','plate','wash'):t[role]=data['teams'][first][role]
  t['identity_shared_with']=first
 else:by_identity[key]=name
 if t['slot']>=32 and 'fallback' in t['source']:
  t['review_required']=True;review.append(dict(team=name,reasons=['Custom or undocumented team uses explicit neutral fallback; supply its own palette']))
data.update(status='active build-time accents; GPU calibration unresolved',review=review,limitation='Extra slots have independent code/kind tint binding and neutral logos when no NFL asset exists.')
session.write_json(ROOT/'data/nfl2k5_scorebug_sprite/team_accents.json',data);session.write_json(out/'decisions.json',decisions)
accents.contact_sheet(data,out/'contact_sheet.png');session.write_json(out/'review.json',review)
print('resolved',sum(d['applied'] for d in decisions),'of',len(decisions),'Jev review groups; remaining review entries',len(review),'cost',s.spent())
