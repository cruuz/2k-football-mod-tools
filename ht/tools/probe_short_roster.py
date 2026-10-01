#!/usr/bin/env python3
"""PROVED OFFLINE: bounded importer experiment, not a proper-roster writer."""
import json
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from mod_editor.core import nfl2k5_historic_teams_quick_game as h
from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_roster_records as rr
from nfl2k5_historic_quick_game_native import TeamSelectCPU,disc_evidence
retail=Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)')
raw,_=e.apply_xbe((retail/'default.xbe').read_bytes());xbe,_=h.apply(raw)
resources,context,identities=disc_evidence(retail)
d=context['descriptors'][0]
original=resources[d['outer']]
results=[]
for count in (36,40,45):
    doc=rr.RosterDocument(original[32:]); team=doc.teams[0]
    body=bytearray(original)
    struct.pack_into('<I',body,32+doc.obj_base+rr.POOL_FIELDS['primary'][0],count)
    body[32+team.offset+rr.TEAM_PLAYER_COUNT]=count
    for slot in range(count,rr.TEAM_SLOTS):
        struct.pack_into('<I',body,32+team.offset+slot*4,0)
    trial=dict(resources);trial[d['outer']]=bytes(body)
    cpu=TeamSelectCPU(xbe,trial,context,identities)
    cpu.team_select(cpu.team(0),cpu.team(15),flow=1)
    mask=cpu.run(h.SYMBOLS['team_mask'])
    last=cpu.run(h.SYMBOLS['iter_prev'],ecx=cpu.team(0),edx=mask)
    cpu.team_select(last,cpu.team(15),flow=1)
    s=cpu.press('home',1)
    results.append(dict(requested=count,selected=s['home'],pool=cpu.pool(),loaded=s['loaded']))
    assert s['home']['players']==count and cpu.pool()['used']==count
out=dict(label='PROVED OFFLINE',results=results,
    limitation='Synthetic removal of final retail roster slots; no claim of valid lineups or game safety. '
    'Importer accepts fewer than 53 players. A real writer must compact sourced players, rebuild depth/special teams '
    'and validate every position and match-start route. The existing fixed-quota draft overstates missing membership.')
(ROOT/'ht/evidence/short_rosters.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
