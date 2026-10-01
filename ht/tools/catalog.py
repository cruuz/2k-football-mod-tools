#!/usr/bin/env python3
"""PROVED OFFLINE: census every outer archive ROST resource, including unselected ones."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_espn25_rosters as e
retail=Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)')
rows=[]
with rr._outer_image()(retail) as archive:
    context=e.describe_context(archive.read_entry(5),archive.read_entry(22),archive.entries)
    named={r['outer']:r['filename'] for r in context['descriptors']}
    for entry in archive.entries:
        if archive.read(entry.virtual_offset,min(entry.size,32))[:4] != b'ROST':
            continue
        raw=archive.read_entry(entry.index)
        doc=rr.RosterDocument(raw[32:])
        current_slots={slot for t in doc.teams if t.kind==0 for slot in t.slots}
        free_slots=set(doc.free_agents)
        rows.append(dict(outer=entry.index,name_id=f'{entry.name_id:08x}',
                        filename=named.get(entry.index),main=entry.index==5,
                        players=len(doc.players),teams=[dict(name=t.nickname,identity=t.asset_id,category=t.kind,
                            current_nfl_pointer_members=sum(slot in current_slots for slot in t.slots) if entry.index==5 else None,
                            free_agent_pointer_members=sum(slot in free_slots for slot in t.slots) if entry.index==5 else None,
                            other_pointer_members=sum(slot not in current_slots|free_slots for slot in t.slots) if entry.index==5 else None,
                            players=t.player_count,sample_names=[p.first+' '+p.last for p in doc.team_players(t.index)[:5]])
                            for t in doc.teams]))
    count=len(archive.entries)
result=dict(label='PROVED OFFLINE',outer_entries_scanned=count,roster_resources=rows,
            unrecognized_roster_outers=[r['outer'] for r in rows if not r['filename'] and not r['main']],
            limitation='All top-level archive ROST resources; not an exhaustive classification of arbitrary nested or unused bytes.')
(ROOT/'ht/evidence/roster_catalog.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(entries=count,rost_resources=len(rows),unknown=result['unrecognized_roster_outers']),indent=2))
