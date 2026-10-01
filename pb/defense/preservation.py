#!/usr/bin/env python3
"""PROVED OFFLINE: independent postcomposition comparison with phase 2 semantics."""
from concurrent.futures import ProcessPoolExecutor
import hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from pb.defense.verify import IMAGE,OuterImage,BOOK_ENTRIES
from mod_editor.core import nfl2k5_playbook_pack as pk,nfl2k5_play_library as lib,nfl2k5_playbook_inspector as ip

def check(row):
    t=row['team'];off=pk.load_pack(ROOT/row['pack']);de=pk.load_pack(ROOT/f'data/playbooks/softdrink_{t.lower()}_defense.2k5book')
    with OuterImage(IMAGE) as source:before=pk.apply_pack_to_resource(source.read_entry(BOOK_ENTRIES[t]),off,xbe=IMAGE).replacement
    after=(ROOT/f'.scratch/pb3/compiled/{t}.bin').read_bytes();b=ip.parse_playbook_resource(before);a=ip.parse_playbook_resource(after)
    owned={p.replace_index for p in de.plays};forms={f.replace_index for f in de.formations};n=0
    for p in b.plays:
        if p.index in owned:continue
        q=a.plays[p.index]
        assert (p.name,p.flags_or_id)==(q.name,q.flags_or_id),(t,p.index)
        assert lib.play_chains(before[32:],p.index)==lib.play_chains(after[32:],p.index),(t,p.index)
        n+=1
    for f in b.formations:
        assert f.play_links==a.formations[f.index].play_links,(t,f.index)
        if f.index not in forms:
            start=32+ip.FORMATION_BASE+f.index*ip.FORMATION_SIZE
            assert before[start:start+ip.FORMATION_SIZE]==after[start:start+ip.FORMATION_SIZE],(t,f.index)
    return t,dict(unchanged_play_records=n,unchanged_formations=len(b.formations)-len(forms),
        source_sha256=hashlib.sha256(before).hexdigest(),result_sha256=hashlib.sha256(after).hexdigest())
def main():
    rows=json.loads((ROOT/'pb/league_manifest.json').read_text())['teams']
    with ProcessPoolExecutor(max_workers=4) as pool:result=dict(pool.map(check,rows))
    dest=ROOT/'pb/receipts/defense/preservation.json'
    dest.write_text(json.dumps(dict(status='PROVED OFFLINE',teams=result),indent=2)+'\n')
    print('PROVED OFFLINE: all 32 books retain every unowned phase-2 play and formation')
if __name__=='__main__':main()
