#!/usr/bin/env python3
"""Bounded FRZ offline consumers of extracted disc bytes. No emulator or build.

The selector fixture supplies ratings, kicker range, clock urgency and tendency
history. The lineup fixture uses the disc ROST records including depth rank and
side, and executes the native chart builder and eligibility caller. Route tests
execute native lookahead, not the full animation or blocking system.
"""
import argparse
from collections import Counter, deque
import hashlib
import itertools
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(Path(__file__).parent)]
from frz_probe import Lineup, rr, ip, lib
from mod_editor.core import nfl2k5_play_scoring as scoring


def save(path, result):
    path.write_text(json.dumps(result, indent=1)+'\n')


def books(directory):
    from nfl2k5_playbook_position_recode import BOOK_ENTRIES
    from mod_editor.core.nfl2k5_playbook_pack import TEAM_BOOKS
    return [(key, (directory/(key+'.play')).read_bytes())
            for key in BOOK_ENTRIES if key in TEAM_BOOKS]


def caller(directory, output):
    doc = rr.load_body((directory/'entry5.bin').read_bytes()[32:], scheme='one_pool')
    machine = Lineup((directory/'default.xbe').read_bytes())
    aliases = {'ARI':'ARZ', 'LAC':'SD', 'LV':'OAK', 'LAR':'STL'}
    result = dict(fixture=__doc__, budget=500000, teams=[])
    for team in doc.teams[:32]:
        key = aliases.get(team.abbreviation, team.abbreviation)
        raw = (directory/(key+'.play')).read_bytes()
        book, body = ip.parse_playbook_resource(raw), raw[32:]
        row = dict(team=key, formations=len(book.formations), cases=0, faults=[], exhausted=0)
        # Categories include personnel twins, kicking and both unit types.
        categories = set(lib.formation_category(body, form.index) for form in book.formations)
        categories.update(c.index for c in book.categories)
        for side, state in itertools.product((0, 1), ('rested', 'tired', 'injured', 'mixed')):
            machine.team(doc, team, 'rested' if state == 'mixed' else state, side)
            if state == 'mixed':
                for n, player in enumerate(machine.players):
                    if n % 2:
                        machine.u.mem_write(machine.TEAM+0xa000+n*0x40+0x24, struct.pack('<f', 0.05))
            for category in sorted(categories):
                desc = body[ip.CATEGORY_BASE+category*16:ip.CATEGORY_BASE+(category+1)*16]
                machine.u.mem_write(machine.DESC, desc)
                for slot, tier, fatigue in itertools.product(range(11), (0,1,2,6), (0,1)):
                    row['cases'] += 1
                    lineup = machine.DESC+0x100
                    machine.u.mem_write(lineup, bytes(44))
                    try:
                        player = machine.call(0x189360, (slot, 0, fatigue, tier, lineup),
                                              ecx=0xE5FC20 if side else 0xE5FD00,
                                              edx=machine.DESC, count=500000)
                        row['exhausted'] += int(player == 0)
                        if player and player not in machine.players:
                            raise RuntimeError(f'foreign player {player:#x}')
                    except Exception as exc:
                        row['faults'].append(dict(side=side, state=state, category=category,
                            descriptor=desc.hex(), slot=slot, tier=tier, fatigue=fatigue,
                            pc=hex(machine.u.reg_read(__import__('unicorn').x86_const.UC_X86_REG_EIP)), error=str(exc)))
        result['teams'].append(row)
        save(output, result)
        print(key, row['cases'], len(row['faults']), flush=True)
    return result


def selectors(directory, output, samples, focused=False):
    from b77.p9_harness import Fixture
    from pb.scoring_selectors import scenarios
    result = dict(fixture=__doc__, budget=20000000, samples=samples, focused=focused, teams=[])
    payload = (directory/'default.xbe').read_bytes()
    for key, raw in books(directory):
        m = Fixture(payload)
        # World normally overrides a caller's bound with twenty million.
        m.m.emu_start = lambda a,b,**kw: m.native_start(a,b,count=20000000)
        m.load_book(raw)
        for n, team in enumerate((scoring.TEAM, m.defense)):
            base = scoring.SOURCE+0x1d000+n*0x200
            m.m.mem_write(base+0x100, (key+'\0').encode('utf-16le'))
            m.put(base+4, base+0x100)
            m.put(team+0x110, base)
            m.put(team+0x128, 0)
        row = dict(team=key, cases=0, faults=[], choices=Counter())
        states = scenarios()
        states += [dict(phase=3, quarter=4, margin=margin, seconds=sec)
                   for margin,sec in itertools.product(range(-16,17), (0,30,120,300))]
        if focused:
            states = [dict(down=d,distance=dist,yard=25,quarter=1,seconds=360)
                      for d,dist in ((1,10),(2,8),(3,3),(3,10),(4,1),(4,12))]
            states += [dict(phase=phase,quarter=1,seconds=359) for phase in (1,2,3)]
            states += [dict(phase=3,quarter=4,margin=margin,seconds=30) for margin in (-8,-2,1,5)]
        for index, state in enumerate(states):
            for seed in range(samples):
                settings = dict(state)
                direction = settings.pop('direction', 1)
                m.state(**settings)
                m.fput(scoring.DIRECTION+4, direction)
                m.seed((seed+0.5)/samples, 1000003*seed+index+17)
                for pc, team, args, out in ((0x20B670, scoring.TEAM, (), scoring.SOURCE+0x19100),
                                           (0x20B820, m.defense, (0,), scoring.SOURCE+0x19200)):
                    row['cases'] += 1
                    m.m.mem_write(out, bytes(16))
                    try:
                        m.call(pc, ecx=team, edx=out, args=args)
                        values = struct.unpack('<4I', m.m.mem_read(out,16))
                        if pc == 0x20B670:
                            row['choices'][str(values)] += 1
                    except Exception as exc:
                        row['faults'].append(dict(state=state, seed=seed, routine=hex(pc),
                            pc=hex(m.m.reg_read(m.r.UC_X86_REG_EIP)), error=str(exc), detail=m.problem))
        # All formation family filters and mirror contexts, including twins
        # that this sample of random draws may not select.
        m.state()
        for form in m.book.formations:
            fv = scoring.BOOK+ip.FORMATION_BASE+form.index*ip.FORMATION_SIZE
            if (m.get(fv+4)>>8)&63 not in (0,1,2,3):
                continue
            cv = m.call(0xE1A80, ecx=scoring.BOOK, edx=fv)
            for kind, context in itertools.product(range(9), (0,1)):
                row['cases'] += 1
                try:
                    m.call(0x2096A0, ecx=scoring.TEAM, edx=kind, args=(fv,cv,context))
                except Exception as exc:
                    row['faults'].append(dict(formation=form.index, kind=kind, context=context,
                        pc=hex(m.m.reg_read(m.r.UC_X86_REG_EIP)), error=str(exc), detail=m.problem))
        row['distinct_offensive_choices'] = len(row.pop('choices'))
        result['teams'].append(row)
        save(output,result)
        print(key,row['cases'],len(row['faults']),flush=True)
    return result


def routes(directory, output):
    from b77.p6s_route_check import trace, book_rows, ROLE
    from nfl2k5_back_throws_replay import NativeMachine
    m = NativeMachine((directory/'default.xbe').read_bytes())
    result = dict(fixture=__doc__, budget=200000, teams=[], unique_cases=0, unique_faults=0)
    cache = {}
    for team,raw in books(directory):
        row = dict(team=team, cases=0, faults=[])
        for fname,pname,rows in book_rows(raw):
            for slot,kind,x,z,nodes in rows:
                if kind not in ROLE:
                    continue
                for active,node in enumerate(nodes):
                    if node.op != 0x12 or int(node.operands[0]) == 9:
                        continue
                    for mirror in (1,-1):
                        key = (b''.join(n.to_bytes() for n in nodes), mirror*x,z,kind,active)
                        row['cases'] += 1
                        if key not in cache:
                            try:
                                path = trace(m,nodes,mirror*x,z,kind,active)
                                cache[key] = None
                            except Exception as exc:
                                cache[key] = dict(error=str(exc), pc=hex(m.uc.reg_read(__import__('unicorn').x86_const.UC_X86_REG_EIP)))
                                result['unique_faults'] += 1
                            result['unique_cases'] += 1
                        if cache[key]:
                            row['faults'].append(dict(formation=fname,play=pname,slot=slot,active=active,
                                kind=kind,mirror=mirror,nodes=[n.to_bytes().hex() for n in nodes], **cache[key]))
        result['teams'].append(row)
        save(output,result)
        print(team,row['cases'],len(row['faults']),result['unique_cases'],flush=True)
    return result


def hooks(directory, output):
    from tests.nfl2k5_abilities_machine import Machine
    from tests.nfl2k5_cpu_money_downs_native import Machine as CpuMachine
    from mod_editor.core import nfl2k5_abilities_runtime as ability
    from mod_editor.core import nfl2k5_cpu_money_downs as cpu
    from mod_editor.core import nfl2k5_punter_holder as holder
    from mod_editor.core import nfl2k5_honors as honors
    payload = (directory/'default.xbe').read_bytes()
    doc = rr.load_body((directory/'entry5.bin').read_bytes()[32:], scheme='one_pool')
    m = Machine(payload)
    p9 = CpuMachine(payload)
    result = dict(fixture=__doc__, budget=5000, teams=[],
        owners=dict(g2=ability.status(payload), p9=cpu.status(payload),
                    h1=holder.status(payload), f5=honors.status(payload)), target_cases=0, target_faults=[])
    for team in doc.teams[:32]:
        row = dict(team=team.abbreviation, cases=0, faults=[])
        for player in doc.team_players(team.index):
            word = struct.unpack_from('<H', player.record.encode(), 0x52)[0]
            for controller, context, command in itertools.product((-1,0,3), (6,8,10), (0x1a,0x1b,0x23,*range(0x24,0x2c))):
                row['cases'] += 1
                try:
                    m.player(controller=controller, context=context, abilities=word, command=command)
                    m.run('filter',regs={'EBX':m.P})
                except Exception as exc:
                    row['faults'].append(dict(player=player.slot,word=word,controller=controller,
                        context=context,command=command,pc=hex(m.uc.reg_read(m.r.UC_X86_REG_EIP)) if hasattr(m,'r') else '',error=str(exc)))
            for controller, meter in itertools.product((-1,0), (0.0,1.0)):
                for address in (0x2D43F0,0x2D46D0):
                    row['cases'] += 1
                    try:
                        m.player(controller=controller, abilities=word)
                        m.f32(m.S+0x44,meter)
                        m.run(address)
                    except Exception as exc:
                        row['faults'].append(dict(word=word,routine=hex(address),error=str(exc)))
        result['teams'].append(row)
        save(output,result)
        print(team.abbreviation,row['cases'],len(row['faults']),flush=True)
    for down, distance, direction in itertools.product((1,2,3,4),(1,3,7,12),(-1,1)):
        for bad in ({},{'available':False},{'viable':False},{'score':0.49}):
            result['target_cases'] += 1
            try:
                p9.targets([dict(yards=distance-1,score=0.8),dict(dict(yards=distance,score=0.7),**bad)],
                           down=down,distance=distance,direction=direction)
            except Exception as exc:
                result['target_faults'].append(dict(down=down,distance=distance,direction=direction,error=str(exc)))
    save(output,result)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('caller','selectors','routes','hooks'))
    ap.add_argument('directory',type=Path)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--samples',type=int,default=3)
    ap.add_argument('--focused',action='store_true',help='early-game and try states; still all formation filters')
    args = ap.parse_args()
    result = selectors(args.directory,args.out,args.samples,args.focused) if args.mode == 'selectors' else globals()[args.mode](args.directory,args.out)
    return int(any(row['faults'] for row in result['teams']) or bool(result.get('target_faults')))


if __name__ == '__main__':
    sys.exit(main())
