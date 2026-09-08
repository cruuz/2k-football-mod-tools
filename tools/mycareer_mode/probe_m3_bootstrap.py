"""Bounded native draft entry from retail ROST, without a prepared franchise.

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
from mod_editor.core import nfl2k5_draft_ai as ai
from mod_editor.core import nfl2k5_senior_bowl as bowl
from tests.nfl2k5_my_career_played_fixture import Machine
from tests.nfl2k5_supersim_draft_fixture import retail_bytes
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


def probe(output, seed=12345, finish_creation=False, finish_draft=False):
    output=Path(output).resolve()
    if ROOT/'.scratch' not in output.parents:
        raise ValueError('probe receipt must remain under this worktree .scratch')
    output.parent.mkdir(parents=True,exist_ok=True)
    retail,roster=retail_bytes(),retail_roster()
    payload=mode.apply(ai.apply(retail)[0])[0]
    start=time.monotonic()
    receipt=dict(schema='nfl2k5.mycareer.m3-bootstrap.v1',experimental=True,runtime_witnessed=False,
        retail_xbe_sha256=hashlib.sha256(retail).hexdigest(),roster_sha256=hashlib.sha256(roster).hexdigest(),
        patched_xbe_sha256=hashlib.sha256(payload).hexdigest(),seed=seed,
        states=[],native_class_generations=0,complete=False,
        requested_endpoint='draft' if finish_draft else 'preparation' if finish_creation else 'CAP opened',
        substituted='Existing frontend hardware/layout leaves, plus 177990 progress presentation only. RNG, league processing, class creation, picks and signing remain native; executed stages depend on the requested endpoint.')
    def record():
        receipt['elapsed_seconds']=round(time.monotonic()-start,3)
        output.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    with Machine(payload) as m:
        m.frontend(roster)
        m.replace_stub(0x48BC0,None)
        m.replace_stub(0x177990,lambda:m.ret(pop=4))
        for rng in (0xB12680,0xE5FCA0):
            m.call(0x48BE0,ecx=rng,edx=seed)
        def generated(*_):
            receipt['native_class_generations']+=1
        m.stubs.append(m.uc.hook_add(m.u.UC_HOOK_CODE,generated,begin=0x2BE940,end=0x2BE940))
        m.call(0x6E390,ecx=m.manager,edx=0x5015CC)
        m.select(1)
        m.select(0,budget=500000000)
        try:
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
            if not finish_creation and not finish_draft:
                receipt['complete']=True
                return receipt
            for _ in range(4):m.frame(0x10,budget=10000000)
            if m.top()!=m.labels['m3_prep_menu']:
                raise AssertionError('created player did not reach preparation')
            index=m.get(m.state+28);pool=m.get(m.root+4)
            rows=[bowl.Prospect(i,m.uc.mem_read(pool+84*i+53,1)[0],m.uc.mem_read(pool+84*i+8,1)[0])
                  for i in range(m.get(m.root))]
            selected=[p.index for team in bowl.select_squads(rows) for p in team]
            if index not in selected:raise AssertionError('MyPlayer is absent from default preparation squads')
            receipt.update(primary_index=index,class_count=len(bowl.current_class(rows)),
                           selected_count=len(selected),myplayer_selected=True,final_menu=m.top())
            if finish_draft:
                m.select(0,budget=200000000)
                for pick in range(224):
                    if m.get(0xE576A4)!=5:break
                    m.frame(budget=6000000000)
                    if pick%32==31:print('completed round',pick//32+1,flush=True)
                if m.get(0xE576A4)==5:raise AssertionError('native draft did not finish')
                receipt.update(final_stage=m.get(0xE576A4),career_phase=m.get(m.state+24),
                               club=m.get(m.state+56),final_menu=m.top())
            receipt['complete']=True
        except Exception as exc:
            receipt['failure']=f'{type(exc).__name__}: {exc}'
            receipt['failure_eip']=hex(m.reg('EIP'))
            raise
        finally:
            record()
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--seed',type=int,default=12345)
    parser.add_argument('--finish-creation',action='store_true')
    parser.add_argument('--finish-draft',action='store_true')
    args=parser.parse_args()
    probe(args.output,args.seed,args.finish_creation,args.finish_draft)
