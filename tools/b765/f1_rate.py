#!/usr/bin/env python3
"""Reproduce FA estimates with the shipped r1-ratings-v2.4 model.

Supply the original r1 derived inputs and nflverse cache. The writer uses the
frozen result, so an installed Studio never needs private research directories
or a network fetch. Output includes every model basis and input SHA-256.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools/ratings_v2')]


def rate(args):
    import common
    from model import Data, MODEL_VERSION, rate_all
    from mod_editor.core import nfl2k5_roster_records as rr
    common.CFG.update(work=str(args.model_inputs), nflverse=str(args.nflverse))
    document=rr.RosterDocument(args.roster.read_bytes(),scheme='one_pool',reference_year=2026)
    authoring=json.loads(args.authoring.read_text())
    identities={(r['pool'],r['index']):r for r in authoring['franchise_history']['players']}
    candidates=json.loads(args.candidates.read_text())['players']
    as_of=dt.date(2026,10,5)
    players=[]
    for p in document.players:
        identity=identities.get((p.pool,p.index))
        if not identity: continue
        born=dt.date.fromisoformat(identity['birth_date'])
        years=p.record.get('years_pro');pos=p.record.position_name
        players.append(dict(gsis=identity['gsis_id'],name=p.display,pos=pos,index=p.index,pool=p.pool,
            team='FA' if p.offset in document.free_agents else document.teams[p.teams[0]].abbreviation,
            depth=p.record.get('depth_rank'),tier='backup' if p.offset in document.free_agents else
            ('starter' if p.record.get('depth_rank')<common_start(pos) else 'backup'),
            weight=p.record.get('weight'),height=p.record.get('height'),
            age=as_of.year-born.year-((as_of.month,as_of.day)<(born.month,born.day)),
            years=years,current=p.record.ratings()))
    for i,row in enumerate(candidates):
        born=dt.date.fromisoformat(row['birth_date'])
        years=as_of.year-row['entry_year']
        pos=row.get('game_position') or rr.position_name(rr.position_code(row['position'],'one_pool'),'one_pool')
        row['model_index']=2324+i
        players.append(dict(gsis=row['gsis_id'],name=row['name'],pos=pos,index=row['model_index'],pool='primary',
            team='FA',depth=7,tier='backup',weight=row['weight'],height=row['height'],
            age=as_of.year-born.year-((as_of.month,as_of.day)<(born.month,born.day)),years=years,
            current={k:0 for k in rr.RATING_BYTE_ORDER}))
    data=Data([str(ROOT/'data/nfl2k5_ratings_forty_sources.json')])
    with gzip.open(args.nflverse/'players.csv.gz','rt') as stream:
        draft={r['gsis_id']:int(float(r['draft_pick'])) if r['draft_pick'] else None
               for r in csv.DictReader(stream) if r['gsis_id']}
    rate_all(data,players,draft)
    by_gsis={p['gsis']:p for p in players}
    for row in candidates:
        p=by_gsis[row['gsis_id']]
        row.update(ratings=p['ratings'],rating_basis=p['basis'],age=p['age'],years_exp=p['years'])
        row['inactivity']=dict(last_played_season=row.get('last_played_season'),
            completed_seasons_out=max(0,2025-int(row['last_played_season'])) if row.get('last_played_season') else None,
            rule='Same r1 2024/2025 component weights/shrinkage and backup-tier priors; physicals use actual Oct5 2026 age and retail slopes past29. No invented inactivity skill penalty.')
    input_paths=[args.roster,args.authoring,args.candidates,args.model_inputs/'features_2024.json',
         args.model_inputs/'features_2025.json',args.model_inputs/'ratings_v2_reference.json',
         args.model_inputs/'stability.json',args.nflverse/'players.csv.gz',args.nflverse/'combine.csv.gz',
         ROOT/'tools/ratings_v2/model.py',ROOT/'tools/ratings_v2/common.py',
         ROOT/'mod_editor/core/nfl2k5_ratings_model.py',ROOT/'data/nfl2k5_ratings_forty_sources.json']
    if (args.model_inputs/'honors.json').exists(): input_paths.append(args.model_inputs/'honors.json')
    input_paths.extend(sorted((args.model_inputs/'predraft').glob('*.json')))
    inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in input_paths}
    result=dict(schema='nfl2k5.fa_ratings.v1',model=MODEL_VERSION,as_of=as_of.isoformat(),
        comparison_population=len(players),existing_ratings_written=False,inputs_sha256=inputs,
        players=candidates)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(model=MODEL_VERSION,added=len(candidates),comparison_population=len(players))))


def common_start(position):
    from model import STARTERS
    return STARTERS[position]


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('roster','authoring','candidates','model-inputs','nflverse','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    rate(parser.parse_args())
