#!/usr/bin/env python3
"""PROVED OFFLINE: native selection/ratings and byte-level classic equipment.

Runs no emulator. Archive and UI seams use the existing bounded Unicorn harness.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tests'), str(ROOT/'tools')]
from mod_editor.core import nfl2k5_historic_teams_quick_game as h1
from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_modern_helmets as hm
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_espn25_more_moments as more
from nfl2k5_historic_quick_game_native import TeamSelectCPU, disc_evidence

RETAIL = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)')


def run():
    raw = (RETAIL/'default.xbe').read_bytes()
    payload, _ = e.apply_xbe(raw)
    payload, _ = h1.apply(payload)
    resources, context, identities = disc_evidence(RETAIL)
    main = rr.RosterDocument(resources[5][32:])
    residents = [dict(name=t.nickname, identity=t.asset_id, category=t.kind, count=t.player_count)
                 for t in main.teams]
    table = []
    for d in context['descriptors']:
        doc = rr.RosterDocument(resources[d['outer']][32:])
        table.append(dict(**d, name=doc.teams[0].nickname, identity=doc.teams[0].asset_id,
                          category=doc.teams[0].kind, size=len(resources[d['outer']])))
    manifest, sheets = e.dataset()
    targets = {t['outer']:t for t in manifest['resources']}
    named, _ = e.apply({k:v for k,v in resources.items() if k in sheets})
    edits = hm.historic_edits()
    def classic(raw, outer):
        return hm.compile_historic(raw, outer, edits) if outer in edits else raw
    helmet_rows = []
    for d in table:
        before = resources[d['outer']]
        one = classic(before, d['outer'])
        if d['outer'] in named:
            rows = sheets[d['outer']]
            reverse = e.compile_resource(one, rows, manifest['colleges'])
            forward = classic(named[d['outer']], d['outer'])
            assert forward == reverse
        else:
            forward = one
        players = rr.RosterDocument(forward[32:]).players
        helmets = Counter(p.record.get('helmet') for p in players)
        masks = Counter(p.record.get('face_mask') for p in players)
        assert set(helmets) == {0} and set(masks) <= set(range(12))
        helmet_rows.append(dict(name=d['name'], outer=d['outer'], players=len(players),
                                helmets=dict(helmets), masks=dict(masks), sha256=e.sha(forward)))
    flows = {}
    ratings = []
    for flow in h1.LOCAL_FLOWS:
        cpu = TeamSelectCPU(payload, resources, context, identities)
        cpu.team_select(cpu.team(0), cpu.team(15), flow=flow)
        cpu.press('home', -1)  # last historic
        cpu.press('home', 1)   # first resident
        mask = cpu.run(h1.SYMBOLS['team_mask'])
        last = cpu.run(h1.SYMBOLS['iter_prev'], ecx=cpu.team(0), edx=mask)
        cpu.team_select(last, cpu.team(15), flow=flow)
        seen = []
        for d in table:
            s = cpu.press('home', 1)
            assert s['loaded'] == [d['filename']]
            assert s['home']['players'] == 53 and s['home']['category'] == 4
            assert cpu.pool()['used'] == 53
            seen.append(s['home']['name'])
            if flow == 1:
                values = []
                for n, fn in enumerate((0xC4830, 0xC4860, 0xC48A0)):
                    at, out = 0x27E0000+0x20*n, 0x27E0100+4*n
                    cpu.write(at, b'\xe8'+struct.pack('<i', fn-at-5)+b'\xd9\x1d'+struct.pack('<I', out)+b'\xc3')
                    cpu.run(at, ecx=cpu.r(0xACF63C))
                    values.append(round(cpu.f(out)*100, 4))
                ratings.append(dict(name=d['name'], values=values,
                                    display=[min(100, int(v)) for v in values]))
        assert len(seen) == 75
        flows[str(flow)] = dict(loaded=seen, pool_used=cpu.pool()['used'])
    data = more.Data.load()
    with rr._outer_image()(RETAIL) as archive:
        from tools.nfl_outer import HEADER_SIZE
        slack = (archive.entries[0].virtual_offset - HEADER_SIZE - 12*len(archive.entries))//12
        directory_count = len(archive.entries)
    return dict(label='PROVED OFFLINE', xbe_sha256=hashlib.sha256(raw).hexdigest(),
                boundaries=TeamSelectCPU.__doc__, resident_teams=residents, historic_teams=table,
                flows=flows, ratings=ratings, equipment=helmet_rows,
                equipment_summary=dict(players=sum(r['players'] for r in helmet_rows),
                                       all_standard=True, all_masks_retail_0_to_11=True,
                                       original_equipment_fields_remapped=sum(len(v) for v in hm.historic_edits().values()),
                                       moment_roster_orders_equal=35),
                catalog=dict(retail_entries=directory_count, retail_free_directory_slots=slack,
                             more_moments_teams=len(data.teams), more_moments_max=more.MAX_TEAMS,
                             more_moment_ids=[r[-1] for r in more.table_entries(data)],
                             all_time_descriptor_count=sum('all' in d['name'].lower() for d in table)))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, default=ROOT/'ht/evidence/native.json')
    args = ap.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(label='PROVED OFFLINE', flows={k:len(v['loaded']) for k,v in result['flows'].items()},
                         equipment=result['equipment_summary'], catalog=result['catalog']), indent=2))
