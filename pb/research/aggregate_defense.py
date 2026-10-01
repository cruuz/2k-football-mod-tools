#!/usr/bin/env python3
"""PROVED OFFLINE: defensive counts from joined nflverse participation and PBP."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from aggregate import keyed, rows


def aggregate(root):
    names = ['play_by_play_2025.csv.gz', 'pbp_participation_2025.csv', 'ftn_charting_2025.csv']
    people = keyed(root/names[1], 'nflverse_game_id', 'play_id')
    chart = keyed(root/names[2], 'nflverse_game_id', 'nflverse_play_id')
    teams = defaultdict(Counter)
    coverages = defaultdict(Counter)
    personnel = defaultdict(Counter)
    for p in rows(root/names[0]):
        if p['season_type'] != 'REG' or p['play_type'] not in ('run','pass') or p['qb_kneel']=='1' or p['qb_spike']=='1' or not p['defteam']:
            continue
        key = (p['game_id'], int(float(p['play_id'])))
        t = p['defteam']; c = teams[t]; c['snaps'] += 1
        r = people.get(key)
        c['ftn_joined'] += key in chart
        if r is None: continue
        assert r['possession_team'] == p['posteam'], key
        c['participation_joined'] += 1
        kinds = {k:int(n) for n,k in re.findall(r'(\d+) ([A-Z]+)',r['defense_personnel'])}
        if sum(kinds.values())==11:
            c['personnel_known'] += 1
            db = sum(kinds.get(k,0) for k in ('CB','DB','FS','SS','S'))
            c['nickel'] += db == 5; c['dime'] += db == 6
            personnel[t][r['defense_personnel']] += 1
        if p['qb_dropback'] != '1': continue
        c['dropbacks'] += 1
        if r['defense_man_zone_type'] in ('MAN_COVERAGE','ZONE_COVERAGE'):
            c['man_zone_known'] += 1
            c['man'] += r['defense_man_zone_type']=='MAN_COVERAGE'
            c['zone'] += r['defense_man_zone_type']=='ZONE_COVERAGE'
        cov = r['defense_coverage_type']
        if cov:
            c['coverage_known'] += 1; coverages[t][cov] += 1
            c['cover0'] += cov=='COVER_0'
            c['single_family'] += cov in ('COVER_1','COVER_3')
            c['split_family'] += cov in ('COVER_2','2_MAN','COVER_4','COVER_6','COVER_9')
        # Zero on a dropback is an uncharted/sentinel count, not a proved zero-man rush.
        n = int(r['number_of_pass_rushers'] or '0')
        if 1 <= n <= 11:
            c['rush_known'] += 1; c['blitz'] += n >= 5
            c['rush4'] += n == 4
    result={}
    for t,c in sorted(teams.items()):
        rates={k:round(100*c[k]/c[d],4) if c[d] else None for k,d in (
            ('nickel','personnel_known'),('dime','personnel_known'),('man','man_zone_known'),('zone','man_zone_known'),
            ('cover0','coverage_known'),('single_family','coverage_known'),('split_family','coverage_known'),('blitz','rush_known'))}
        result[t]=dict(counts=dict(c),rates=rates,coverage_counts=dict(coverages[t]),personnel_counts=dict(personnel[t]),
            presnap_single_high=None,presnap_two_high=None,simulated_pressure=None,creeper=None,
            base_front_charting=None)
    base='https://github.com/nflverse/nflverse-data/releases/download'
    return dict(status='PROVED OFFLINE',season=2025,season_type='REG',
        sources=[dict(file=n,sha256=hashlib.sha256((root/n).read_bytes()).hexdigest(),bytes=(root/n).stat().st_size,
            url=f'{base}/{tag}/{n}') for n,tag in zip(names,('pbp','pbp_participation','ftn_charting'))],
        attribution='nflverse participation and PBP; FTN public charting joined for availability, CC-BY-SA-4.0. Defensive rates use participation, not absent FTN fields.',
        definitions='run/pass excluding kneels/spikes; coverage and rush rates use charted QB dropbacks; nickel/dime use eleven-player personnel on all eligible snaps; split/single are post-snap coverage-family proxies, not pre-snap shell observations; blitz = at least five counted rushers; missing and zero rush counts excluded',
        unavailable='No pre-snap shell, aligned front, simulated-pressure or creeper labels in these extracts. Personnel positions do not prove alignment. Public FTN subset lacks those defense fields.',teams=result)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.write_text(json.dumps(aggregate(a.data),indent=2)+'\n')
