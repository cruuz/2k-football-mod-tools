"""Replay FA's exact comparisons against decoded G bytes, not a field overlay.

The adapter keeps FA's source joins, counter map and comparisons. Its explicit
changes replace F's predicted donor history with G's actual streams/TEAM words,
point frozen-integrity checks at G's contract ledger, and redirect output.
"""
from pathlib import Path
import hashlib
import sys
FA=Path('/media/noah/Storage/.b76-research/fa')
FR=Path('/media/noah/Storage/.b76-research/fr')
STACK=Path(__file__).resolve().parents[1]
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--roster',type=Path,default=Path('/media/noah/Storage/.b76-research/main/freeze/candG/league_roster_edits_candG_fr.json'))
parser.add_argument('--out',type=Path,default=FR/'audit_g')
parser.add_argument('--school-equivalents',action='store_true')
args=parser.parse_args()
G=args.roster
AUDIT=args.out
AUDIT.mkdir(parents=True,exist_ok=True)
source=(FA/'audit_f.py').read_text()
original_hash=hashlib.sha256((FA/'audit_f.py').read_bytes()).hexdigest()

def swap(old,new):
    global source
    assert source.count(old)==1,(old,source.count(old))
    source=source.replace(old,new)

swap("ROOT=Path(__file__).resolve().parent",f"ROOT=Path({str(FA)!r})")
swap("STACK=Path('/home/noah/2k-worktrees/beta-76')",f"STACK=Path({str(STACK)!r})")
swap("EDITS=Path('/media/noah/Storage/.b76-research/main/freeze/candF/league_roster_edits_candE_dc.json')",f"EDITS=Path({str(G)!r})")
swap("PROJECT=EDITS.with_name('league_project_k2_v55_49ers_frozen.json')","PROJECT=Path('/media/noah/Storage/.b76-research/main/freeze/candF/league_project_k2_v55_49ers_frozen.json')")
swap("OUT=ROOT/'results';OUT.mkdir(exist_ok=True)",f"OUT=Path({str(AUDIT)!r});OUT.mkdir(exist_ok=True)")
swap("hist=th.parse_body(bytes(doc.body))\nadds,history_log=th.match_rows(hist,th.load_rows('retail')[0])",'''retail_doc=doc
body,replay=rr.apply_body(bytes(doc.body),edits)
assert not replay['log'],replay['log']
doc=rr.RosterDocument(body,reference_year=2026)
hist=th.parse_body(body)
from types import SimpleNamespace
history_log=SimpleNamespace(actual_G_streams=True,retail_fallback=False)
adds={p.index:{cs.Word(w).slot:(w&65535)-1 for w in p.entries if cs.Word(w).field==87
                   and not cs.Word(w).deleted and not cs.Word(w).folded and cs.Word(w).phase=='regular'} for p in hist.players}''')
swap("retail_name=p.display,retail_college=p.college", "retail_name=next(q.display for q in retail_doc.players if (q.pool,q.index)==(p.pool,p.index)),retail_college=next(q.college for q in retail_doc.players if (q.pool,q.index)==(p.pool,p.index))")
start=source.index("for e in edits['edits']:")
end=source.index('active=[p for p in players.values()',start)
source=source[:start]+source[end:]
swap("old_audit=json.loads((STACK/'fc/data/contract_audit.json').read_text())",f"old_audit=json.loads(Path({str(FR/'contract_audit.json')!r}).read_text())")
swap("def team(s): return {'ARI':'ARZ','LA':'STL','LAR':'STL','LAC':'SD','LV':'OAK'}.get(s,s)",
     "def team(s): return th.TEAM_ALIASES.get(s, {'LA':'STL'}.get(s,s))")
swap("retail_body_sha256=hashlib.sha256(doc.body).hexdigest()", "decoded_body_sha256=hashlib.sha256(doc.body).hexdigest()")
# The old meta labels described donor words. They must not label decoded G
# streams as inherited; actual donor removal is checked by verify.py.
source=source.replace('players_with_inherited_stream','players_with_decoded_stream').replace('players_with_inherited_current_games_slot','players_with_current_games_slot').replace('players_with_inherited_future_games_slots','players_with_future_games_slots')
if args.school_equivalents:
    # Retain FA's original membership comparison as a separate column, then
    # apply the explicit CL equivalences. Literal spelling checks are unchanged.
    swap("def school(s):return aliases.get(norm(s),norm(s))", "def original_school(s):return aliases.get(norm(s),norm(s))\n        from fr.colleges import school")
    swap("check(p,'college_school',school(p['college']) in {school(s) for s in schools},True,'school_review',roster_url,p['college']+' vs '+r['college'])",
         "check(p,'college_school_original',original_school(p['college']) in {original_school(s) for s in schools},True,'school_review_original',roster_url,p['college']+' vs '+r['college'])\n            check(p,'college_school',school(p['college']) in {school(s) for s in schools},True,'school_review_cl_equivalences',roster_url,p['college']+' vs '+r['college'])")
(AUDIT/'adapter.json').write_text(__import__('json').dumps(dict(evidence='PROVED OFFLINE',fa_audit_sha256=original_hash,
 adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),g_file=str(G)),indent=2)+'\n')
exec(compile(source,str(FA/'audit_f.py'),'exec'),{'__name__':'__main__','__file__':str(FA/'audit_f.py')})
