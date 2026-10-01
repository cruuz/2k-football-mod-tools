#!/usr/bin/env python3
"""PROVED OFFLINE: validate and aggregate the separate outer-selector receipts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pb.scoring_selectors import scenarios,BOOK_ENTRIES


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--receipts',type=Path,default=ROOT/'pb/receipts/phase5/selectors')
    ap.add_argument('--sweep',type=Path,default=ROOT/'pb/receipts/phase5/after-expanded-independent.json')
    ap.add_argument('--output',type=Path,default=ROOT/'pb/receipts/phase5/selectors-summary.json')
    args=ap.parse_args();sweep=json.loads(args.sweep.read_text());states=scenarios()
    expected={(variant,r['book']):r['resource_sha256'] for group,variant in [('retail','retail'),('final','authored')] for r in sweep[group]}
    rows=[];calls=Counter();visits=Counter();faults=[];files={}
    for team in BOOK_ENTRIES:
        path=args.receipts/f'{team}.json';payload=path.read_bytes();d=json.loads(payload)
        assert d['states']==states,(team,'stale or partial world fixture')
        files[path.name]=hashlib.sha256(payload).hexdigest()
        for r in d['books']:
            assert r['resource_sha256']==expected[r['variant'],team],team
            assert r['states']==len(states) and r['calls']['0x20b820']==len(states),team
            rows.append({k:r[k] for k in ('book','variant','resource_sha256','states','seconds')})
            calls.update(r['calls']);visits.update(r['visits'])
            faults.extend(dict(book=team,variant=r['variant'],**f) for f in r['faults'])
    assert Counter(r['variant'] for r in rows)=={'retail':37,'authored':32}
    authored=[f for f in faults if f['variant']=='authored']
    # Preserve control faults, never recast them as successful native calls.
    # PRACTICE is a partial utility book, not a full-match special-teams book.
    unexpected=[f for f in faults if not (f['book']=='PRACTICE' and f['variant']=='retail'
                and f['detail']==dict(kind='unmapped-access',pc='0x2045f0',address='0x4',size=4,access=19))]
    result=dict(status='PROVED OFFLINE',runtime_witness=False,states_per_book=len(states),
                world_states=sum(r['states'] for r in rows),books=rows,calls=dict(calls),native_visits=dict(visits),
                authored_fault_count=len(authored),retail_control_fault_count=len(faults)-len(authored),
                unexpected_fault_count=len(unexpected),faults=faults,receipt_sha256=files,
                control_scope='PRACTICE has no special-teams formations. Full-match fourth-down/kick fixtures can give 0x20B820 a null formation. These native faults remain recorded; they are not PLAY table-index faults. All 37 retail resources separately pass the exhaustive per-play scorer sweep.',
                coverage='Factored world-state experiment; all indexed PLAY scorer domains are exhausted by the separate sweep.')
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    assert not unexpected,unexpected[:1]
    print('PROVED OFFLINE:',len(rows),'book variants,',result['world_states'],'world states, authored faults',len(authored),', retail control faults',result['retail_control_fault_count'])
if __name__=='__main__':main()
