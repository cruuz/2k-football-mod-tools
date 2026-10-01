"""DESIGN: compare snapshot depth to native chart rows without editing starters."""
import csv
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dc.import_depth import OUT, SNAPSHOT, latest_rows, matcher, ALIASES, player_info
from dc.native_probe import Probe, minimal_xbe

COMMON={'QB':(0,0),'RB':(7,0),'FB':(8,0),'TE':(9,0),'LT':(14,0),'RT':(14,1),
        'LG':(13,0),'RG':(13,1),'C':(12,0),'LCB':(4,0),'RCB':(4,1),'NB':(4,2),'SS':(6,0),'FS':(5,0)}
FRONT43={'LDE':(16,0),'RDE':(16,1),'LDT':(15,0),'RDT':(15,1),
         'WLB':(11,1),'MLB':(11,0),'SLB':(11,3)}
FRONT34={'LDE':(15,1),'NT':(15,0),'RDE':(15,3),'WLB':(16,1),
         'LILB':(11,0),'RILB':(11,1),'SLB':(16,0)}

def run():
    rows,dates=latest_rows(SNAPSHOT)
    xbe=minimal_xbe()
    before=Probe(xbe,(OUT/'candidate_C_before.rost').read_bytes())
    after=Probe(xbe,(OUT/'candidate_C_dc.rost').read_bytes())
    match=matcher(before.doc,json.loads((ROOT/'fc/data/contract_audit.json').read_text())['ledger'])
    entries=[]
    for team in before.doc.teams[:32]:
        code=ALIASES.get(team.abbreviation,team.abbreviation)
        for r in (r for r in rows if r['team']==code and r['pos_grp']!='Special Teams'):
            # nflverse flattens all WRs into one list: the first three represent
            # the 3WR starter set. Their X/Z/SLOT association is a comparison
            # convention, not a claim ESPN assigns left/right/slot roles.
            wr=r['pos_abb']=='WR' and int(r['pos_rank'])<=3
            if r['pos_rank']!='1' and not wr:continue
            mapping={**COMMON,**(FRONT34 if r['pos_grp']=='Base 3-4 D' else FRONT43)}
            if wr:pos,chain=3,int(r['pos_rank'])-1
            else:pos,chain=mapping[r['pos_abb']]
            args=(0,pos,chain)
            def read(probe):return probe.info(probe.m.call(0x242ae0,edx=probe.m.team_base+team.index*500,args=args))
            current,updated=read(before),read(after)
            assert current==updated,(code,r['pos_abb'],current,updated)
            expected,method=match(r,team.index)
            status='match' if current and expected and current['index']==expected.index else 'missing_from_roster' if not expected else 'different'
            entries.append({'evidence':'DESIGN' if wr else 'PROVED OFFLINE','team':code,'group':r['pos_grp'],
                            'source_role':r['pos_abb'],'source_rank':int(r['pos_rank']),'source_name':r['player_name'],
                            'gsis_id':r['gsis_id'],'match_method':method,'expected':player_info(expected),
                            'native_position':pos,'native_chain':chain,'current':current,'status':status})
    report={'evidence':'PROVED OFFLINE','rows_compared':len(entries),'changed_by_dc':0,
            'comparison_convention':'DESIGN: compare nflverse WR1/2/3 to X/Z/SLOT; do not infer alignment accuracy from WR ordering.',
            'counts':{s:sum(e['status']==s for e in entries) for s in ('match','different','missing_from_roster')},'entries':entries}
    (ROOT/'dc/proof/starters.json').write_text(json.dumps(report,indent=2)+'\n')
    with (ROOT/'dc/proof/starter_differences.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['evidence','team','group','role','source_rank','source_name','roster_name','status','native_position','native_chain'])
        writer.writeheader()
        for e in entries:
            if e['status']=='match':continue
            writer.writerow({'evidence':e['evidence'],'team':e['team'],'group':e['group'],'role':e['source_role'],
                             'source_rank':e['source_rank'],'source_name':e['source_name'],
                             'roster_name':e['current']['name'] if e['current'] else '', 'status':e['status'],
                             'native_position':e['native_position'],'native_chain':e['native_chain']})
    print({k:v for k,v in report.items() if k!='entries'})
if __name__=='__main__':run()
