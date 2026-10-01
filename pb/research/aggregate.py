#!/usr/bin/env python3
"""PROVED OFFLINE: reproduce team tendencies from local nflverse CSV releases.

DESIGN: no network, pandas, estimated values, or inferred run-concept labels.
"""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re


def rows(path):
    with (gzip.open(path, 'rt') if path.suffix == '.gz' else path.open()) as stream:
        yield from csv.DictReader(stream)


def keyed(path, game, play):
    result = {}
    for row in rows(path):
        key = (row[game], int(float(row[play])))
        if key in result:
            raise ValueError(f'Duplicate key in {path.name}: {key}')
        result[key] = row
    return result


def aggregate(root, year):
    names = [f'play_by_play_{year}.csv.gz', f'ftn_charting_{year}.csv',
             f'pbp_participation_{year}.csv']
    pbp, ftn, participation = [root / n for n in names]
    chart = keyed(ftn, 'nflverse_game_id', 'nflverse_play_id')
    people = keyed(participation, 'nflverse_game_id', 'play_id')
    teams = defaultdict(Counter)
    formations, personnel, locations = (defaultdict(Counter) for _ in range(3))
    dates = set()
    for p in rows(pbp):
        if (p['season_type'] != 'REG' or p['play_type'] not in ('run', 'pass')
                or p['qb_kneel'] == '1' or p['qb_spike'] == '1' or not p['posteam']):
            continue
        key = (p['game_id'], int(float(p['play_id'])))
        t, c = p['posteam'], teams[p['posteam']]
        c['snaps'] += 1
        c['shotgun'] += p['shotgun'] == '1'
        c['dropbacks'] += p['qb_dropback'] == '1'
        if p['play_type'] == 'run' and p['qb_scramble'] != '1':
            c['designed_runs'] += 1
            locations[t][p['run_location'] or 'unknown'] += 1
        if key in people and people[key]['offense_personnel']:
            r = people[key]
            if r['possession_team'] != t:
                raise ValueError(f'Possession mismatch: {key}')
            kinds = {kind: int(n) for n, kind in re.findall(r'(\d+) ([A-Z]+)', r['offense_personnel'])}
            # Count FB with RB. Preserve six-OL and other unusual packages separately.
            label = f"{kinds.get('RB', 0) + kinds.get('FB', 0)}{kinds.get('TE', 0)}"
            if (sum(kinds.get(k, 0) for k in ('C', 'G', 'T')) != 5
                    or sum(kinds.values()) != 11 or kinds.get('QB') != 1):
                label = 'other'
            personnel[t][label] += 1
            c['personnel_known'] += 1
            if r['offense_formation']:
                formations[t][r['offense_formation']] += 1
        if key in chart:
            r = chart[key]
            c['chart_joined'] += 1
            dates.add(r['date_pulled'])
            if r['is_motion'] in ('TRUE', 'FALSE'):
                c['motion_known'] += 1
                c['motion'] += r['is_motion'] == 'TRUE'
            if p['qb_dropback'] == '1' and r['is_play_action'] in ('TRUE', 'FALSE'):
                c['pa_known_dropbacks'] += 1
                c['play_action'] += r['is_play_action'] == 'TRUE'
            if r['qb_location'] in ('U', 'S', 'P'):
                c['qb_location_known'] += 1
                c['pistol'] += r['qb_location'] == 'P'
    result = []
    for t, c in sorted(teams.items()):
        def pct(n, d):
            return round(100 * n / d, 2) if d else None
        result.append(dict(team=t, **c, personnel=dict(personnel[t]),
                           formation_families=dict(formations[t]), run_locations=dict(locations[t]),
                           shotgun_pct=pct(c['shotgun'], c['snaps']),
                           pistol_pct=pct(c['pistol'], c['qb_location_known']),
                           motion_pct=pct(c['motion'], c['motion_known']),
                           play_action_pct=pct(c['play_action'], c['pa_known_dropbacks']),
                           p11_pct=pct(personnel[t]['11'], c['personnel_known']),
                           p12_pct=pct(personnel[t]['12'], c['personnel_known']),
                           p21_pct=pct(personnel[t]['21'], c['personnel_known'])))
    base = 'https://github.com/nflverse/nflverse-data/releases/download'
    return dict(status='PROVED OFFLINE', season=year, season_type='REG',
                filter='play_type run/pass, exclude kneels/spikes; designed runs exclude scrambles',
                rate_denominators='See counts per team. PA uses charted dropbacks; missing is not false.',
                run_concepts='Unavailable in these public files; run_location is not a concept.',
                ftn_date_pulled=sorted(dates),
                sources=[dict(file=n, bytes=(root/n).stat().st_size,
                              sha256=hashlib.sha256((root/n).read_bytes()).hexdigest(),
                              url=f'{base}/{tag}/{n}') for n, tag in zip(names, ('pbp', 'ftn_charting', 'pbp_participation'))],
                teams=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--year', type=int, default=2025)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(aggregate(args.data, args.year), indent=2) + '\n')


if __name__ == '__main__':
    main()
