#!/usr/bin/env python3
"""PROVED OFFLINE: one 64-pack composition, native validation and menu walks.
DESIGN: no gameplay or xemu invocation. Retail image is read-only.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_playbook_pack as pk,nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_playbook_inspector as ip,mod_build
from pb.verify_league import OuterImage,BOOK_ENTRIES,Overlay,menu_gate
from pb.verify import native_receipt
from pb.defense.selector import Selector,XBE
from pb.defense.build import semantic,ORDINARY
IMAGE=Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
OUT=ROOT/'pb/receipts/defense'
def sha(data):return hashlib.sha256(data).hexdigest()
def meaning(raw,index):
    book=ip.parse_playbook_resource(raw);p=book.plays[index]
    return (p.name,p.flags_or_id,lib.decoded_chains(raw[32:],index))
def main():
    recipe=json.loads((ROOT/'pb/recipes/final_playbooks.json').read_text())
    options=recipe['overrides'];paths=[Path(p.replace('<stack>',str(ROOT))) for p in options['playbook_packs']]
    assert len(paths)==len(set(paths))==64
    plan=mod_build.BuildPlan(str(IMAGE),str(ROOT/'.scratch/pb3/not-built.iso'))
    for k,v in options.items():setattr(plan,k,tuple(str(p) for p in paths) if k=='playbook_packs' else v)
    blockers=mod_build.validate_plan(plan);assert not blockers,blockers
    packs=[(str(p.relative_to(ROOT)),pk.load_pack(p)) for p in paths]
    expected={r['team']:r for r in json.loads((ROOT/'pb/defense_manifest.json').read_text())['teams']}
    assert all(not p.option_intent for _,pack in packs for p in pack.plays)
    report=dict(status='PROVED OFFLINE',runtime_witness=False,pack_count=64,validate_plan=blockers,
        recipe_sha256=sha((ROOT/'pb/recipes/final_playbooks.json').read_bytes()),teams={})
    compiled=ROOT/'.scratch/pb3/compiled';compiled.mkdir(parents=True,exist_ok=True)
    xbe=XBE.read_bytes()
    with OuterImage(IMAGE) as source:
        overlay=Overlay(source);receipts=[]
        report['install']=pk.apply_packs_to_archive(overlay,packs,book_entries=BOOK_ENTRIES,collector=receipts,progress=lambda s:print(s,flush=True),xbe=xbe)
        report['compilers']=[];phase2_resources={}
        for (label,pack),(raw,receipt) in zip(packs,receipts):
            keys=('schema','source_sha256','replacement_sha256','old_node_count','new_node_count',
                  'old_formation_count','new_formation_count','old_play_count','new_play_count',
                  'replaced_formation_indices','replaced_play_indices')
            report['compilers'].append(dict(pack=label,receipt={k:receipt[k] for k in keys if k in receipt}))
            if pack.schema==pk.OFFENSE_SCHEMA:phase2_resources[pack.book.team]=raw
            else:(compiled/f'{pack.book.team}.bin').write_bytes(raw)

        assert len(overlay.pending)==32
        report['menu_gate']=menu_gate(IMAGE,overlay)
        report['utility_unchanged']=[t for t,i in BOOK_ENTRIES.items() if t not in pk.TEAM_BOOKS and overlay.read_entry(i)==source.read_entry(i)]
        assert len(report['utility_unchanged'])==5
        for team in pk.TEAM_BOOKS:
            before=source.read_entry(BOOK_ENTRIES[team]);after=overlay.read_entry(BOOK_ENTRIES[team]);b=ip.parse_playbook_resource(before);a=ip.parse_playbook_resource(after)
            dpack=next(p for _,p in packs if p.schema==pk.DEFENSE_SCHEMA and p.book.team==team)
            offense=next(p for _,p in packs if p.schema==pk.OFFENSE_SCHEMA and p.book.team==team)
            phase2=phase2_resources[team]
            assert sha(after)==expected[team]['compile']['replacement_sha256']
            assert semantic(dpack)==expected[team]['semantic_sha256']
            names=struct.unpack_from('<I',after,32+0x1083c)[0]*2
            assert a.node_count<=3500 and names<=11088
            # Exact link bytes in ALL formations are preserved by the defense stage.
            assert phase2[32+ip.FORMATION_AUX_BASE:32+ip.PLAY_BASE]==after[32+ip.FORMATION_AUX_BASE:32+ip.PLAY_BASE]
            for c in b.categories:
                start=32+ip.CATEGORY_BASE+16*c.index
                assert before[start+4:start+16]==after[start+4:start+16]
            protected=[]
            for f in b.formations:
                if f.name in ORDINARY or lib.formation_record(before[32:],f.index).type_code in (0,1,2,3):continue
                # PROVED OFFLINE: special formation bytes and linked scripts stay retail.
                start=32+ip.FORMATION_BASE+f.index*ip.FORMATION_SIZE
                assert before[start+4:start+ip.FORMATION_SIZE]==after[start+4:start+ip.FORMATION_SIZE],(team,f.name)
                for p in b.plays_for_formation(f.index):
                    q=a.plays[p.index]
                    assert (p.name,p.flags_or_id,lib.decoded_chains(before[32:],p.index))==(q.name,q.flags_or_id,lib.decoded_chains(after[32:],p.index)),(team,f.name,p.index)
                protected.append(f.name)
            menus=ip.inspect_defense(after)['formations']
            pairs=0
            for m in menus:
                for pair in m['pairs']:
                    assert pair['active']==list(range(11)),(team,m,pair)
                    pairs+=1
            machine=Selector(xbe,after)
            walks=native_receipt(xbe,after)
            (compiled/f'{team}.bin').write_bytes(after)
            report['teams'][team]=dict(nodes=a.node_count,name_bytes=names,resource_sha256=sha(after),
                defense_semantic_sha256=semantic(dpack),native_validated=machine.native_validated,
                protected=protected,full_pairs=pairs,formations=len(walks),pages=sum(len(w['pages']) for w in walks),
                walks=walks)
            print(team,a.node_count,names,pairs,'PASS',flush=True)
            (OUT/'composition.partial.json').write_text(json.dumps(report,indent=2)+'\n')
    assert len({r['defense_semantic_sha256'] for r in report['teams'].values()})==32
    (OUT/'composition.json').write_text(json.dumps(report,indent=2)+'\n');(OUT/'composition.partial.json').unlink()
if __name__=='__main__':main()
