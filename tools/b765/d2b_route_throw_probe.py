#!/usr/bin/env python3
"""Actual PLAY initialization to native target, accuracy, launch and ruling.

Current receiver poses are explicit samples of native initialized route records;
they are not captured animation frames. QB release is the actual native drop
endpoint. No throw/classifier/route arithmetic callee is replaced. All supplied
ratings, RNG, clock, Challenges/history inputs are recorded. Gameplay unwitnessed.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.b765.d2b_route_probe import native_assignment, native_qb_drop
from tools.b765.d2b_passing_probe import ThrowMachine
from tools.b765.d2_repair import V04_SHA256, COMBINED_SHA256
from tools.b765 import d2b_checkdown_routes_repair as repair
from tools.nfl2k5_back_throws_replay import DEFAULT_XBE, read_retail
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_playbook_inspector as inspector
from mod_editor.core import nfl2k5_throw_tuning as tuning


def cases(payload, entry_id):
    book = inspector.parse_playbook_resource(payload)
    found = {}
    for formation in book.formations:
        fr = lib.formation_record(payload[32:], formation.index)
        codes = lib.category_positions(payload[32:], lib.formation_category(payload[32:], formation.index))
        for link in formation.play_links:
            play = book.plays[link.play_index]
            qb = [codec.Node.from_bytes(bytes.fromhex(n.raw_hex)) for n in book.assignment_chain(play.assignments[0]).nodes]
            if not any(n.op == 6 for n in qb) or not any(n.op == 4 for n in qb):
                continue
            depth = min([fr.slots[0].z[0]] + [n.operands[2] for n in qb if n.op == 4])
            cluster = 'under_center' if abs(depth+457.2)<.01 else 'pistol' if depth == -366 else None
            if cluster is None or cluster in found:
                continue
            for slot in range(6,11):
                nodes = [codec.Node.from_bytes(bytes.fromhex(n.raw_hex)) for n in book.assignment_chain(play.assignments[slot]).nodes]
                if codes[slot]&31 == lib.HB and fr.slots[slot].z[0] == -640 and len(nodes) == 2 and nodes[1].op == 18 and nodes[1].operands[0] == 5:
                    found[cluster] = dict(cluster=cluster, entry_id=entry_id, book=book.book_name, formation=formation.name,
                        formation_index=formation.index, play=play.name, play_index=play.index, slot=slot)
                    break
    return list(found.values())


def sample(machine, payload, case, *, repaired, stage, direction, challenges, referee):
    m = machine
    qb = native_qb_drop(m, payload, case['formation_index'], case['play_index'], direction=direction)
    full = native_assignment(m, payload, case['formation_index'], case['play_index'], case['slot'], direction=direction)
    current = (full['records'][1]['x'], full['records'][1]['z']) if repaired else None
    # Activate the actual ordinary flat after its native approach endpoint.
    route = native_assignment(m, payload, case['formation_index'], case['play_index'], case['slot'],
                              direction=direction, active_index=2 if repaired else 1,
                              current_position=current)
    first, end = route['records'][:2]
    duration = end['time']-first['time']
    if stage == 'stopped':
        xx, zz, now = end['x'], end['z'], end['time']+.05
        vx, vz = 0., 0.
    else:
        distance = float(stage)
        fraction = distance/abs(end['x']-first['x'])
        xx = first['x']+fraction*(end['x']-first['x'])
        zz = first['z']+fraction*(end['z']-first['z'])
        now = first['time']+fraction*duration
        vx, vz = (end['x']-first['x'])/duration, (end['z']-first['z'])/duration
    m.vec(m.P+0x530, (xx*direction,0.,zz*direction,1.))
    m.vec(m.P+0x540, (vx*direction,0.,vz*direction,0.))
    m.f(m.CLOCK+0x10, now)
    result = m.throw_from_route(release=qb['z'], direction=direction, seed=7, hold=.5,
                                challenges=challenges, referee_random=referee)
    return dict(qb=qb, full_route=full, active_flat=route,
                receiver_pose_cm=[xx,zz], receiver_velocity_cm_s=[vx,vz],
                supplied_clock=now, **result)


def compare(retail, pack, before, pistol_before):
    if repair.sha(pack) not in {V04_SHA256, COMBINED_SHA256}:
        raise ValueError('Expected exact v0.4 or composed d2 executable')
    fixed = tuning.apply_forward_pass_ruling(pack)[0]
    after, repair_receipt = repair.repair_resource(before, 310)
    pistol_after, pistol_receipt = repair.repair_resource(pistol_before, 307)
    selected = [c for c in cases(before,310) if c['cluster']=='under_center'] + [c for c in cases(pistol_before,307) if c['cluster']=='pistol']
    if len(selected) != 2:
        raise ValueError('Expected actual BUF under-center and ARZ Pistol clusters')
    images = [('retail',retail),('v04',pack),('ruling_fixed',fixed)]
    machines = {name:ThrowMachine(data) for name,data in images}
    rows = []
    for case in selected:
        original, repaired_resource = (before,after) if case['entry_id']==310 else (pistol_before,pistol_after)
        for repaired, payload in ((False,original),(True,repaired_resource)):
            for stage in ('300','800','stopped'):
                for direction in (-1,1):
                    for challenges in (0,1):
                        for referee in (-.99,-.5,0.,.5,.99):
                            group = []
                            for source,_ in images:
                                result = sample(machines[source],payload,case,repaired=repaired,stage=stage,
                                                direction=direction,challenges=challenges,referee=referee)
                                row = dict(case=case, resource_state='repaired' if repaired else 'original',
                                           source=source, stage=stage, direction=direction, challenges=challenges,
                                           referee_random=referee, hold=.5, rng_seed=7, **result)
                                group.append(row);rows.append(row)
                            for field in ('target','accuracy_point','launch_velocity','endpoint'):
                                if any(r[field] != group[0][field] for r in group[1:]):
                                    raise AssertionError(f'Independent XBE repair changed {field}')
                            if group[0]['kind'] != group[1]['kind']:
                                raise AssertionError('Retail/v04 actual native ruling differs')
                            fixed_row = group[-1]
                            if fixed_row['downfield_velocity'] != 0 and fixed_row['kind'] != (3 if fixed_row['downfield_velocity']<0 else 4):
                                raise AssertionError('Repaired ruling violates native launch direction')
    summary = []
    for cluster in ('under_center','pistol'):
        for state in ('original','repaired'):
            for source,_ in images:
                selected = [r for r in rows if r['case']['cluster']==cluster and r['resource_state']==state and r['source']==source]
                summary.append(dict(cluster=cluster,resource_state=state,source=source,cases=len(selected),
                    backward_launches=sum(r['downfield_velocity']<0 for r in selected),
                    forward_kind3=sum(r['downfield_velocity']>0 and r['kind']==3 for r in selected),
                    backward_kind3=sum(r['downfield_velocity']<0 and r['kind']==3 for r in selected)))
    return dict(schema='b765.d2b.actual-route-throw.v1', gameplay_witness=False, full_game_frame=False,
                supplied_ratings=.8, pose_source='Explicit linear samples and stopped endpoint of native initialized PLAY route predictions',
                limits=__doc__, paired_cases=len(rows)//3, native_throws=len(rows),
                xbe_sha256={name:repair.sha(data) for name,data in images},
                repair=[repair_receipt,pistol_receipt], summary=summary,rows=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retail',type=Path,default=DEFAULT_XBE)
    parser.add_argument('--pack',type=Path,required=True)
    parser.add_argument('--buf-book',type=Path,required=True)
    parser.add_argument('--pistol-book',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args()
    if args.receipt.exists() or args.receipt.is_symlink():
        parser.error('Choose a new receipt path')
    with args.pack.open('rb') as stream:
        pack=stream.read(16*1024*1024+1)
    resources=[]
    for path in(args.buf_book,args.pistol_book):
        with path.open('rb') as stream:
            resources.append(stream.read(inspector.RESOURCE_HEADER_SIZE+inspector.BODY_SIZE+1))
    result=compare(read_retail(args.retail),pack,*resources)
    with args.receipt.open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(result['summary'],indent=2))

if __name__=='__main__':main()
