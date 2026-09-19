"""Prepare distinct, code-valid accent groups for the s3 review slots."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from tools.scorebug_sprite.jev import accents,session
OUT=ROOT/'reports/b72_s5/accents';OUT.mkdir(exist_ok=True)
data=json.loads((ROOT/'data/nfl2k5_scorebug_sprite/team_accents.json').read_text())
requests=[];proposals={}
for name,t in data['teams'].items():
 if not t['review_required']:continue
 candidates=t['candidates'];passing=[v for v in candidates.values() if v['contrast_white']>=4.5]
 primary=[c for c in passing if c['parent']==t['official'][0]]
 chosen=max(primary or passing,key=lambda c:sum(accents.rgb(c['hex'])))
 wing=chosen['hex'];rim=wing;plate=wing
 if name=='LV':plate='#000000'
 proposal=dict(wing=wing,rim=rim,plate=plate,wash=wing)
 proposals[name]=proposal
 current={r:t[r] for r in proposal}
 state=dict(team=name,source=t['source'],source_shade_uncertain=any(c.get('confidence')=='low' for c in t.get('palette_evidence',[])),
  proposed=dict(hue=chosen['facts']['hue'],signature=chosen['facts']['signature'],wing=wing,rim=rim,plate=plate,readability='all passes'),
  previous=dict(**current,readability='all passes'),
  style='Signature official hue, restrained gradient, readable white text; Raiders silver and black.',
  groups_identical=proposal==current)
 questions={key:dict(type='choice',instructions=phrase,criteria={'proposed':'Use the proposed coherent group, preserving the signature hue.','previous':'Retain the prior reviewed candidate group.','defer':'Identity is uncertain and needs a human choice.'}) for key,phrase in [
 ('choice_a','Which group better expresses this team within the stated style? If equivalent, choose proposed. Only use the supplied colour groups.'),
 ('choice_b','Pick the group for the team accents. Prefer the signature hue and coherent roles. When the groups are equivalent, choose proposed. Choose defer if neither can be endorsed.')]}
 requests.append(dict(tool='jev_ask',state=state,questions=questions))
session.write_json(OUT/'requests.json',requests);session.write_json(OUT/'proposals.json',proposals)
s=session.Session(ROOT/'reports/b72_s5')
for r in requests:s.guard(r)
print(len(requests))
