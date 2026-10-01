"""PROVED OFFLINE: reproducible match rates, fit errors and OTC comparison tables."""
from __future__ import annotations
import csv
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.franchise_economy.probe import assess


def main():
    audit=json.loads((ROOT/'fc/data/contract_audit.json').read_text())
    otc=json.loads((ROOT/'fc/data/otc_team_caps_2026.json').read_text())
    path=ROOT/'fc/proof/real_rollover.json'
    proof=json.loads(path.read_text())
    if proof['status']!='completed':
        raise ValueError('a completed native run is required, never summarize a partial run as proof')
    # Recompute annotations from retained observations. This also migrates the
    # phase-1 name "release_proof" to the narrower native-financial-gate result.
    assess(proof)
    path.write_text(json.dumps(proof,indent=2)+'\n')
    rows=[]
    for team in audit['by_team']:
        name='Commanders' if team['name']=='Redskins' else team['name']
        published=next(r for r in otc['rows'] if r['team']==name)
        for checkpoint in ('start','rollover','after_free_agency'):
            native=next(r for r in proof['finances_'+checkpoint] if r['team']==team['team'])
            rows.append({'evidence':'PROVED OFFLINE','team':name,'checkpoint':checkpoint,
                         'players':native['players'],'payroll':native['payroll_real_dollars'],
                         'cap_space':native['cap_space_real_dollars'],
                         'dead_money':native['effective_dead_money_real_dollars'],
                         'dead_money_ledger':native['dead_money_ledger_real_dollars'],
                         'native_gate':native['native_gate'],
                         'otc_season':2026, 'otc_active':published['active_cap_spending'],
                         'otc_space':published['cap_space'],'otc_dead':published['dead_money'],
                         'scope':'OTC is a 2026 reference, not a 2027 prediction or the same roster/accounting scope'})
    with (ROOT/'fc/proof/team_cap_comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    with (ROOT/'fc/proof/contract_match_rates.csv').open('w',newline='') as f:
        fields=['evidence','team','players','active_contract_matches','match_rate','observed_schedules','modeled_schedules']
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for t in audit['by_team']:
            writer.writerow({'evidence':'PROVED OFFLINE','team':'Commanders' if t['name']=='Redskins' else t['name'],
                             **{k:t[k] for k in fields[2:]}})
    errors=sorted(({'evidence':'PROVED OFFLINE','name':r['name'],'year':2026+i,
                    'source_dollars':r['fit']['source_cap_dollars'][i],
                    'represented_dollars':r['fit']['represented_cap_dollars'][i],'error':error}
                   for r in audit['ledger'] for i,error in enumerate(r['fit']['errors_dollars'])),
                  key=lambda r:abs(r['error']),reverse=True)
    review={'evidence':'PROVED OFFLINE','observed_schedules':audit['observed_schedules'],
            'modeled_schedules':audit['modeled_schedules'],
            'opening_max_absolute_error':max(abs(r['fit']['errors_dollars'][0]) for r in audit['ledger']),
            'largest_annual_errors':errors[:50], 'exceptions':audit['exceptions'],
            'release_ready':False,'release_blocker':proof['release_blocker']}
    (ROOT/'fc/proof/fit_review.json').write_text(json.dumps(review,indent=2)+'\n')
    columns='| Team | Start payroll | Space | Dead | Rollover payroll | Space | Dead | OTC 2026 payroll | Space | Dead |'
    lines=['PROVED OFFLINE: all amounts below are real-dollar millions, rounded to three decimals. Every row is an offline observation.',
           '', 'DESIGN: OTC includes its own roster, carryover and adjustments. The native experiment does not import legacy dead money. Rollover is a simulation, compared with 2026 only as a reference.',
           '',columns,'|'+'---|'*10]
    for t in audit['by_team']:
        name='Commanders' if t['name']=='Redskins' else t['name']
        a=next(r for r in rows if r['team']==name and r['checkpoint']=='start')
        b=next(r for r in rows if r['team']==name and r['checkpoint']=='rollover')
        amounts=[a['payroll'],a['cap_space'],a['dead_money'],b['payroll'],b['cap_space'],b['dead_money'],a['otc_active'],a['otc_space'],a['otc_dead']]
        lines.append('| '+name+' | '+' | '.join(f'{v/1e6:.3f}' for v in amounts)+' |')
    lines += ['', 'PROVED OFFLINE: source [OTC team cap table](https://overthecap.com/salary-cap-space), observed 2026-09-25. Exact integers and the post-free-agency checkpoint are in `team_cap_comparison.csv`.']
    (ROOT/'fc/proof/TEAM_CAP_TABLE.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'evidence':'PROVED OFFLINE','checks':proof['checks'],'comparison_rows':len(rows),
                      'opening_max_absolute_error':review['opening_max_absolute_error'],
                      'largest_annual_error':errors[0]}))


if __name__=='__main__':main()
