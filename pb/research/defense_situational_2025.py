#!/usr/bin/env python3
"""PROVED OFFLINE: 2025 defensive calls per team, split the way the CPU's coach profile splits them (b779 dp1).

The automatic coach profile (``nfl2k5_coach_ai``, on in the SOFTDRINK release preset) calls every CPU defensive play
from fifteen four-call rings: native 0xF7450 picks ring ``bin * 5 + group``, where ``bin`` comes from native 0xF7010
(down and distance: 0 short, 1 medium, 2 long; fourth down has no ring) and ``group`` is the offense's personnel group
once it has lined up (0 not known yet, 1 heavy, 2 two-back / two-tight-end, 3 three receivers, 4 four or more
receivers).  This script counts the 2025 regular season in exactly those cells so the rings can be fitted per
situation: defensive personnel (base / nickel / dime), coverage family, man, five-plus rushers and simulated pressure.

Sources (the same hashed nflverse release files as aggregate_defense.py): play_by_play_2025.csv.gz,
pbp_participation_2025.csv (personnel, coverage label, man/zone, rushers), ftn_charting_2025.csv (n_pass_rushers,
n_blitzers).  Definitions:
  * bin: native 0xF7010 measured at midfield (tools: b779 dp1 bins table): 1st down 1-7 yd short, 8-16 medium, 17+ long;
    2nd down 1-4 / 5-10 / 11+; 3rd down 1 / 2-3 / 4+; 4th down is not a ring (native lottery) and is excluded;
  * group from offensive personnel: at most one WR heavy (1), two WR (2), three WR (3), four or more WR (4);
  * defensive personnel from defense_personnel: four or fewer DBs base, five nickel, six or more dime;
  * coverage family from defense_coverage_type (COVER_9 joins COVER_6); man from defense_man_zone_type;
  * blitz = five or more pass rushers (participation number_of_pass_rushers, else FTN n_pass_rushers);
  * simulated pressure = exactly four rushers with at least one FTN blitzer (a non-lineman rushing while a lineman
    drops): a proxy, not a charted sim label.
Coverage, man, blitz and sim use QB dropbacks; personnel uses every run/pass snap.  Kneels and spikes are excluded.

  python3 pb/research/defense_situational_2025.py --data /media/noah/Storage/.b76-research/r1/data/nflverse \
      --output pb/research/defense_situational_2025.json
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aggregate import keyed, rows  # noqa: E402

FAMILY = {'COVER_0': 'C0', 'COVER_1': 'C1', '2_MAN': '2M', 'COVER_2': 'C2', 'COVER_3': 'C3', 'COVER_4': 'C4',
          'COVER_6': 'C6', 'COVER_9': 'C6'}


def distance_bin(down: int, togo: int) -> int | None:
    """Native 0xF7010 / 0xF7450 distance bin (0 short, 1 medium, 2 long) measured at midfield; None on 4th down."""
    if down == 1:
        return 0 if togo <= 7 else 1 if togo <= 16 else 2
    if down == 2:
        return 0 if togo <= 4 else 1 if togo <= 10 else 2
    if down == 3:
        return 0 if togo <= 1 else 1 if togo <= 3 else 2
    return None


def offense_group(personnel: str) -> int | None:
    kinds = {k: int(n) for n, k in re.findall(r'(\d+) ([A-Z]+)', personnel or '')}
    if not kinds:
        return None
    wr = kinds.get('WR', 0)
    return 1 if wr <= 1 else 2 if wr == 2 else 3 if wr == 3 else 4


def defense_class(personnel: str) -> str | None:
    kinds = {k: int(n) for n, k in re.findall(r'(\d+) ([A-Z]+)', personnel or '')}
    if sum(kinds.values()) != 11:
        return None
    db = sum(kinds.get(k, 0) for k in ('CB', 'DB', 'FS', 'SS', 'S'))
    return 'base' if db <= 4 else 'nickel' if db == 5 else 'dime'


def aggregate(root: Path) -> dict:
    names = ['play_by_play_2025.csv.gz', 'pbp_participation_2025.csv', 'ftn_charting_2025.csv']
    people = keyed(root / names[1], 'nflverse_game_id', 'play_id')
    chart = keyed(root / names[2], 'nflverse_game_id', 'nflverse_play_id')
    cells = defaultdict(lambda: defaultdict(Counter))
    for p in rows(root / names[0]):
        if (p['season_type'] != 'REG' or p['play_type'] not in ('run', 'pass') or p['qb_kneel'] == '1'
                or p['qb_spike'] == '1' or not p['defteam'] or not p['down']):
            continue
        b = distance_bin(int(float(p['down'])), int(float(p['ydstogo'])))
        if b is None:
            continue
        key = (p['game_id'], int(float(p['play_id'])))
        r = people.get(key)
        if r is None:
            continue
        g = offense_group(r['offense_personnel'])
        if g is None:
            continue
        c = cells[p['defteam']][f'{b}{g}']
        c['snaps'] += 1
        d = defense_class(r['defense_personnel'])
        if d:
            c['pers_known'] += 1
            c[d] += 1
        if p['qb_dropback'] != '1':
            continue
        c['dropbacks'] += 1
        if r['defense_man_zone_type'] in ('MAN_COVERAGE', 'ZONE_COVERAGE'):
            c['mz_known'] += 1
            c['man'] += r['defense_man_zone_type'] == 'MAN_COVERAGE'
        fam = FAMILY.get(r['defense_coverage_type'])
        if fam:
            c['cov_known'] += 1
            c[fam] += 1
        n = int(r['number_of_pass_rushers'] or '0')
        ftn = chart.get(key) or {}
        if not 1 <= n <= 11:
            n = int(float(ftn.get('n_pass_rushers') or 0))
        if 1 <= n <= 11:
            c['rush_known'] += 1
            c['blitz'] += n >= 5
            blitzers = ftn.get('n_blitzers')
            if blitzers not in (None, ''):
                c['sim_known'] += 1
                c['sim'] += n == 4 and int(float(blitzers)) >= 1
    teams = {t: {k: dict(v) for k, v in sorted(cs.items())} for t, cs in sorted(cells.items())}
    base = 'https://github.com/nflverse/nflverse-data/releases/download'
    return dict(status='PROVED OFFLINE (public nflverse data; aggregation only)', season=2025, season_type='REG',
                generator='pb/research/defense_situational_2025.py',
                sources=[dict(file=n, sha256=hashlib.sha256((root / n).read_bytes()).hexdigest(),
                              url=f'{base}/{tag}/{n}')
                         for n, tag in zip(names, ('pbp', 'pbp_participation', 'ftn_charting'))],
                attribution='nflverse PBP and participation; FTN public charting (CC-BY-SA-4.0).',
                cell_key='"<bin><group>": bin 0 short / 1 medium / 2 long (native 0xF7010), group 1 heavy / 2 two WR / '
                         '3 three WR / 4 four+ WR (native 0xF7450 groups 1..4)',
                teams=teams)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    a.output.write_text(json.dumps(aggregate(a.data), indent=1, sort_keys=True) + '\n', newline='\n')
