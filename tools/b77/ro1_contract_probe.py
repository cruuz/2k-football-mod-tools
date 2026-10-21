"""Counterfactual native IR salary proof for newly owned unsigned records.

Supplies a single legitimate IR ownership input, then executes native C3F00.
Before, repaired and undo cases run on separate fresh CPU instances. No salary
or division routine is replaced. Requires private native franchise saves.
"""
from pathlib import Path
import argparse
import json
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.b77.ro1_native_fixture import Machine
from mod_editor.core import nfl2k5_roster_records as rr


def probe(xbe,body,before,after,output):
    payload=Path(xbe).read_bytes();roster=Path(body).read_bytes();results=[]
    for name,save,undo in (('before',before,False),('repaired',after,False),('undo',after,True)):
        with Machine(payload) as m:
            m.cold(roster,Path(save).read_bytes())
            p=m.get(m.get(0xB72918)+4)+2464*84
            team=m.get(0xE5786C+19*4)  # GB owns the identity-guarded Kevin Zeitler.
            if undo:
                rec=rr.PlayerRecord.decode(bytes(m.uc.mem_read(p,84)))
                for key in ('contract_value','contract_length','contract_remaining','contract_type','contract_bonus'):
                    rec.set(key,0)
                m.uc.mem_write(p,rec.encode())
            length=(m.get(p+36)>>24)&15
            if m.call(0xC3EB0,ecx=team,edx=p)!=1:raise AssertionError('IR input player was not owned')
            m.put(0xE421E0+19*20,p)
            row=dict(case=name,primary_index=2464,contract_length=length)
            try:
                m.call(0xC3F00,ecx=team,budget=1000000)
                row['result']='returned'
            except m.u.UcError as exc:
                row.update(result=str(exc),pc=hex(m.reg('EIP')))
            if name=='repaired':assert row['result']=='returned',row
            else:assert row.get('pc')=='0xe6032',row
            results.append(row);print('NATIVE_IR_CONTRACT',json.dumps(row),flush=True)
    Path(output).write_text(json.dumps(dict(complete=True,counterfactual=results),indent=2)+'\n',newline='\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('xbe','body','before','after','output'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();probe(a.xbe,a.body,a.before,a.after,a.output)
