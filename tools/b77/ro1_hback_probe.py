"""Full native H-back season, rollover and draft from an integrated ROST.

EXPERIMENTAL / UNWITNESSED. Can take substantial CPU time. No emulator boot,
disc copy, GUI, audio or network. Only a JSON receipt is written.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_senior_bowl as bowl
from tools.b77.ro1_native_fixture import Machine


def probe(output, xbe, body, seed=12345):
    output=Path(output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    payload,roster=Path(xbe).read_bytes(),Path(body).read_bytes()
    from mod_editor.core import nfl2k5_hback as hb
    if hb.status(payload)!='applied':raise ValueError('Installed H-back image required')
    start=time.monotonic()
    receipt=dict(schema='nfl2k5.hback.season.v1',experimental=True,runtime_witnessed=False,
        roster_sha256=hashlib.sha256(roster).hexdigest(),
        patched_xbe_sha256=hashlib.sha256(payload).hexdigest(),seed=seed,
        states=[],native_class_generations=0,complete=False,
        enum8_native_signings=0,enum8_native_draft_label_reads=0,
        requested_endpoint='draft',
        substituted='Existing frontend hardware/layout leaves, plus 177990 progress presentation only. RNG, league processing, class creation, picks and signing remain native; executed stages depend on the requested endpoint.')
    def record():
        receipt['elapsed_seconds']=round(time.monotonic()-start,3)
        output.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8',newline='\n')
    record()
    with Machine(payload) as m:
        m.frontend(roster)
        m.replace_stub(0x48BC0,None)
        m.replace_stub(0x177990,lambda:m.ret(pop=4))
        for rng in (0xB12680,0xE5FCA0):
            m.call(0x48BE0,ecx=rng,edx=seed)
        def generated(*_):
            receipt['native_class_generations']+=1
        m.stubs.append(m.uc.hook_add(m.u.UC_HOOK_BLOCK,generated,begin=0x2BE940,end=0x2BE940))
        def signed(*_):
            if m.uc.mem_read(m.reg('ECX')+53,1)==b'\x08':
                receipt['enum8_native_signings']+=1
        def named(*_):
            if m.get(0xE576A4)==5 and m.uc.mem_read(m.reg('ECX')+53,1)==b'\x08':
                receipt['enum8_native_draft_label_reads']+=1
        for va,hook in ((0x325B50,signed),(0xE5FC0,named)):
            m.stubs.append(m.uc.hook_add(m.u.UC_HOOK_BLOCK,hook,begin=va,end=va))
        try:
            m.call(0x6E390,ecx=m.manager,edx=0x5015CC)
            m.select(1)
            m.select(0,budget=500000000)
            for step in range(40):
                m.frame(budget=3000000000)
                row=dict(step=step,stage=m.get(0xE576A4),week=m.get(0xE576B4),
                    end=m.get(0xE576B0),year=m.get(0xE576B8),entry_phase=m.get(mode.EXTRA_VA))
                receipt['states'].append(row);record()
                print(row,flush=True)
                if m.get(mode.EXTRA_VA)!=1:break
            if m.get(mode.EXTRA_VA)!=2 or m.get(0xE576A4)!=4 or m.get(0xE576B8)!=1:
                raise AssertionError('native bootstrap did not reach the first Combine and CAP')
            receipt.update(cap_pointer=m.get(0xCB8B14),cap_menu=m.top(),final_menu=m.top())
            player=m.get(0xCB8B14)
            if not player:raise AssertionError('Native CAP allocation failed')
            m.uc.mem_write(player+53,b'\x08')
            m.call(0x343460)
            for _ in range(4):m.frame(0x10,budget=10000000)
            if m.top()!=m.labels['m3_prep_menu']:
                raise AssertionError('created player did not reach preparation')
            index=m.get(m.state+28);pool=m.get(m.root+4)
            rows=[bowl.Prospect(i,m.uc.mem_read(pool+84*i+53,1)[0],m.uc.mem_read(pool+84*i+8,1)[0])
                  for i in range(m.get(m.root))]
            selected=[p.index for team in bowl.select_squads(rows,scheme='one_pool') for p in team]
            if index not in selected:raise AssertionError('MyPlayer is absent from default preparation squads')
            receipt.update(primary_index=index,class_count=len(bowl.current_class(rows,'one_pool')),
                           selected_count=len(selected),myplayer_selected=True,final_menu=m.top())
            from collections import Counter
            counts=Counter(p.position for p in bowl.current_class(rows,'one_pool'))
            if counts.get(10) or not counts.get(8):raise AssertionError('Invalid one-pool draft class')
            receipt['draft_position_counts']=dict(counts)
            pointer=m.call(0xE5FB0,ecx=8)
            raw=bytes(m.uc.mem_read(pointer,64)).decode('utf-16le').split('\0')[0]
            if raw!='FB / H-back':raise AssertionError('Native H-back category label differs')
            receipt['draft_category_label']=raw
            m.select(0,budget=200000000)
            for pick in range(224):
                if m.get(0xE576A4)!=5:break
                m.frame(budget=6000000000)
                if pick%32==31:print('completed round',pick//32+1,flush=True)
            if m.get(0xE576A4)==5:raise AssertionError('native draft did not finish')
            receipt.update(final_stage=m.get(0xE576A4),career_phase=m.get(m.state+24),
                           club=m.get(m.state+56),final_menu=m.top())
            primary=m.call('primary')
            if not primary or m.uc.mem_read(primary+53,1)!=b'\x08':
                raise AssertionError('MyCareer H-back identity lost during draft')
            saved=m.native_save(budget=500000000)
            output.with_suffix('.sav').write_bytes(saved)
            receipt['native_save_bytes']=len(saved)
            receipt['draft_complete']=True
        except Exception as exc:
            receipt['failure']=f'{type(exc).__name__}: {exc}'
            receipt['failure_eip']=hex(m.reg('EIP'))
            raise
        finally:
            record()
    with Machine(payload) as cold:
        cold.cold(roster,saved)
        primary=cold.call('primary')
        if not primary or cold.uc.mem_read(primary+53,1)!=b'\x08':
            raise AssertionError('Post-draft native cold load lost H-back identity')
        if cold.get(0xE576B8)!=1 or cold.get(cold.state+24)!=receipt['career_phase']:
            raise AssertionError('Post-draft native cold load changed career state')
        receipt['post_draft_cold_load']=True
        receipt['complete']=True
    record()
    print('FULL_NATIVE_SEASON_DRAFT',json.dumps({k:receipt[k] for k in
        ('complete','native_class_generations','class_count','draft_category_label',
         'enum8_native_signings','enum8_native_draft_label_reads','final_stage',
         'career_phase','post_draft_cold_load','elapsed_seconds')}),flush=True)
    return receipt


def fresh_save(xbe, body, destination):
    """Create a new enum-8 career through the native menus and save it."""
    from mod_editor.core import nfl2k5_hback as hb
    payload=Path(xbe).read_bytes()
    if hb.status(payload)!='applied':raise ValueError('Installed H-back image required')
    with Machine(payload) as m:
        player=m.create(Path(body).read_bytes(),club=22,position=8,preseason=False)
        assert m.uc.mem_read(player+53,1)==b'\x08'
        m.put(0xE60140,1);m.call(0x2BDCF0,budget=100000000)
        data=m.native_save(budget=500000000)
        Path(destination).write_bytes(data)
        print('FRESH_NATIVE_MYCAREER enum=8 bytes='+str(len(data)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--xbe',required=True,type=Path)
    parser.add_argument('--body',required=True,type=Path)
    parser.add_argument('--seed',type=int,default=12345)
    parser.add_argument('--fresh-save',type=Path)
    args=parser.parse_args()
    if args.fresh_save:
        fresh_save(args.xbe,args.body,args.fresh_save)
    elif args.output:
        probe(args.output,args.xbe,args.body,args.seed)
    else:parser.error('--output or --fresh-save is required')
