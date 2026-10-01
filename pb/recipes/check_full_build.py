#!/usr/bin/env python3
"""PROVED OFFLINE: retain every inspection status before deleting the build disc."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pb.recipes.compose import compose, ROOT

session,base=map(Path,sys.argv[1:3])
dest=ROOT/'pb/receipts'/('phase4' if len(sys.argv)<4 else sys.argv[3])
recipe=json.loads((session/'recipe.json').read_text())
assert recipe==compose(json.loads(base.read_text()),json.loads((ROOT/'pb/recipes/final_playbooks.json').read_text()))
ledger=json.loads((session/'final.xiso.build.json').read_text())
summary=json.loads((session/'final.xiso.summary.json').read_text())
receipt=ledger['result']
plan=receipt['plan']; result=receipt['result']
assert plan['qb_spy'] is True and plan['screen_timing']=='D'
assert plan['xemu_display_list_fix'] is True
assert result['qb_spy']=='applied' and result['screen_timing']=='applied'
assert receipt['play_intents_final']['qb_spy_count']==1
assert receipt['playbook_menus']['problems']==0
assert receipt['playbook_scoring']['status']=='applied'
assert receipt['playbook_scoring']['books']==37 and receipt['playbook_scoring']['faults']==0
pack_steps=[step for step in receipt['steps'] if step['step'] in ('playbook_packs','defense_playbook_packs')]
assert len(pack_steps)==2 and all(step['status']=='applied' and len(step['packs'])==32 for step in pack_steps)
from mod_editor.core import nfl2k5_playbook_pack as packs, nfl2k5_play_library as library
from mod_editor.core import nfl2k5_play_codec as codec
import struct
readback=[]
recode=packs._outer_image()
with recode.OuterImage(session/'final.xiso.iso') as archive:
    for path in plan['playbook_packs']:
        pack=packs.load_pack(Path(path));team=pack.book.team
        raw=archive.read_entry(recode.BOOK_ENTRIES[team]);book=packs.parse_playbook_resource(raw)
        holes=0
        for play in pack.plays:
            assert book.plays[play.replace_index].name==play.custom_name,(team,play.replace_index,play.custom_name)
            chains=library.play_chains(raw[32:],play.replace_index)[1]
            for slot,chain in enumerate(play.assignments):
                for ni,node in enumerate(chain or ()):
                    if node[0] not in (0x16,0x17):continue
                    actual=chains[slot][1][ni]
                    assert actual[0]==node[0] and struct.unpack_from('<I',actual,4)[0]==codec.encode_operands(node[0],node[1]),(team,play.replace_index,slot,ni)
                    holes+=1
        readback.append(dict(pack=str(path),team=team,play_names=len(pack.plays),handoff_operands=holes,
                             resource_sha256=hashlib.sha256(raw).hexdigest()))
assert len(readback)==64
from mod_editor.core.mod_build import _check_playbook_scoring
final_scoring = _check_playbook_scoring(session/'final.xiso.iso', lambda *args: print(args[0], flush=True))
assert final_scoring['books']==37 and final_scoring['faults']==0
record=dict(status='PROVED OFFLINE',runtime_witness=False,seconds=ledger['seconds'],
    recipe_sha256=hashlib.sha256((session/'recipe.json').read_bytes()).hexdigest(),
    base_recipe_sha256=hashlib.sha256(base.read_bytes()).hexdigest(),
    recipe_changed_keys=sorted(json.loads((ROOT/'pb/recipes/final_playbooks.json').read_text())['overrides']),
    source=str(base),session=str(session),disc_bytes=(session/'final.xiso.iso').stat().st_size,
    owners=result,steps=[dict(step=s.get('step'),status=s.get('status')) for s in receipt['steps']],
    play_intents=receipt['play_intents_final'],menus=receipt['playbook_menus'],scoring=final_scoring,
    pack_steps=pack_steps,final_pack_readback=readback,
    scoring_source_sha256=hashlib.sha256((ROOT/'mod_editor/core/nfl2k5_play_scoring.py').read_bytes()).hexdigest(),
    final_gate_source_sha256=hashlib.sha256((ROOT/'mod_editor/core/mod_build.py').read_bytes()).hexdigest(),
    host_revision_note='The build began with the initial scoring gate. This completion check replays the expanded final gate against the finished disc after every writer; all 64 pack inputs remained unchanged.',
    nvme_free_bytes=shutil.disk_usage(ROOT).free,storage_free_bytes=shutil.disk_usage(session).free,
    log_tail=(session/'build.log').read_text().splitlines()[-25:])
(dest/'full-build.json').write_text(json.dumps(record,indent=2,default=str)+'\n')
for source,name in ((session/'build.log','full-build.log'),(session/'recipe.json','full-recipe.json'),
                    (session/'final.xiso.summary.json','full-summary.json')):
    shutil.copyfile(source,dest/name)
print('PROVED OFFLINE: final owner inspection and compiler counts retained; QB Spy and screen D applied.')
