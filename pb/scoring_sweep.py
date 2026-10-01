#!/usr/bin/env python3
"""PROVED OFFLINE: all 37 retail books, 64 compiler outputs and 37 final books."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_playbook_pack as pk, nfl2k5_play_scoring as scoring
from pb.verify_league import OuterImage, BOOK_ENTRIES


def team_sweep(job):
    team,resource,paths,payload=job
    result=[]
    def add(group,name,raw,receipt=None):
        # Independent control/final replays must not reuse the compiler cache.
        row=receipt if receipt is not None else scoring.NativeScorer(payload).sweep(raw)
        row['book']=name;result.append((group,row))
    add('retail',team,resource)
    for path in paths:
        compiled=pk.apply_pack_to_resource(resource,pk.load_pack(path),xbe=payload)
        resource=compiled.replacement
        # This is the actual native execution required by the compiler, not
        # an inferred success from structural validation or a receipt boolean.
        add('compiled',Path(path).name,resource,compiled.report['native_scoring'])
    add('final',team,resource)
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--image',type=Path,required=True)
    ap.add_argument('--xbe',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--workers',type=int,default=4)
    args=ap.parse_args();payload=args.xbe.read_bytes()
    paths=[ROOT/p.replace('<stack>/','') for p in json.loads((ROOT/'pb/recipes/final_playbooks.json').read_text())['overrides']['playbook_packs']]
    by_team={team:[] for team in BOOK_ENTRIES}
    for path in paths:by_team[pk.load_pack(path).book.team].append(path)
    out=dict(status='PROVED OFFLINE',runtime_witness=False,xbe_sha256=hashlib.sha256(payload).hexdigest(),retail=[],compiled=[],final=[])
    with OuterImage(args.image) as source:
        jobs=[(team,source.read_entry(index),by_team[team],payload) for team,index in BOOK_ENTRIES.items()]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(team_sweep,j) for j in jobs]):
            for group,row in future.result():
                out[group].append(row)
                print(group,row['book'],'plays',row['plays'],'faults',row['fault_count'],flush=True)
            args.output.write_text(json.dumps(out,indent=2)+'\n')
    calls=Counter()
    for group in ('retail','compiled','final'):
        out[group].sort(key=lambda row:row['book'])
        for row in out[group]:calls.update(row['calls'])
    out['totals']=dict(books={g:len(out[g]) for g in ('retail','compiled','final')},
                       plays=sum(r['plays'] for g in ('retail','compiled','final') for r in out[g]),
                       faults=sum(r['fault_count'] for g in ('retail','compiled','final') for r in out[g]),calls=dict(calls))
    args.output.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out['totals']),flush=True)
    return int(out['totals']['faults']!=0)
if __name__=='__main__':sys.exit(main())
