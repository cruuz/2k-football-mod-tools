#!/usr/bin/env python3
"""Write data/vip/defense_identity_2026.json: each club's defensive identity for the CPU coach-profile rings (b779 dp1).

Inputs (all in the repository):
  * pb/research/defense_profiles.json: the 2026 defensive coordinator, his scheme family and the 2025 team his rates
    come from (his last play-calling job: e.g. TEN Gus Bradley -> SF 2025, NYG Dennard Wilson -> TEN 2025), with the
    official staff source;
  * pb/research/defense_situational_2025.json: that team's 2025 snaps in the fifteen coach-profile cells (personnel,
    coverage family, man, five-plus rushers, simulated-pressure proxy);
  * pb/v2/defense/design.py SCHEMES: the coordinator's signature calls (the same package the defense books use).
Two DESIGN knobs are lineage judgements, not charting (no public pre-snap shell data exists for 2025):
  * ``disguise`` (design.DISGUISE): the share of single-high calls shown from a two-high shell before the snap;
  * ``package``: concept labels the ring fit prefers on a tie.

  python3 pb/research/make_defense_identity.py   (rewrites data/vip/defense_identity_2026.json)
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pb/v2/defense'))
sys.dont_write_bytecode = True
import design as D  # noqa: E402

OUT = ROOT / 'data/vip/defense_identity_2026.json'
RESEARCH_CODE = {'ARZ': 'ARI', 'STL': 'LA', 'SD': 'LAC', 'OAK': 'LV'}
KEYS = ('snaps', 'pers_known', 'base', 'nickel', 'dime', 'dropbacks', 'mz_known', 'man', 'cov_known',
        'C0', 'C1', '2M', 'C2', 'C3', 'C4', 'C6', 'rush_known', 'blitz', 'sim_known', 'sim')


def compact(cell: dict) -> dict:
    return {k: int(cell.get(k, 0)) for k in KEYS if cell.get(k)}


def main() -> int:
    profiles = json.loads((ROOT / 'pb/research/defense_profiles.json').read_text())
    situ = json.loads((ROOT / 'pb/research/defense_situational_2025.json').read_text())
    league = {}
    for cells in situ['teams'].values():
        for k, c in cells.items():
            league.setdefault(k, Counter()).update({x: int(c.get(x, 0)) for x in KEYS})
    teams = {}
    for team, prof in sorted(profiles.items()):
        base = prof['baseline_team'] or prof['design_fallback_team']
        code = RESEARCH_CODE.get(base, base)
        cells = situ['teams'][code]
        scheme = D.SCHEMES[team]
        teams[team] = dict(dc=prof['dc'], family=prof['family'], source=prof['source'], baseline_2025=code,
                           baseline_role=prof['baseline_role'], front=scheme.family, package=list(scheme.package),
                           mug=scheme.mug, disguise=scheme.disguise,
                           cells={k: compact(v) for k, v in sorted(cells.items())})
    doc = dict(schema='nfl2k5_defense_identity/v1',
               status='PROVED OFFLINE counts (nflverse 2025); DESIGN disguise/package knobs (coaching lineage)',
               generator='pb/research/make_defense_identity.py',
               inputs=['pb/research/defense_profiles.json', 'pb/research/defense_situational_2025.json',
                       'pb/v2/defense/design.py SCHEMES'],
               sources=situ['sources'], attribution=situ['attribution'], cell_key=situ['cell_key'],
               league_cells={k: dict(sorted(v.items())) for k, v in sorted(league.items())}, teams=teams)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n', newline='\n')
    print(OUT.relative_to(ROOT), len(teams), 'teams')
    return 0


if __name__ == '__main__':
    sys.exit(main())
