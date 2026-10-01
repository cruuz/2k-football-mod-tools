#!/usr/bin/env python3
"""Read every historic equipment vector from the completed diagnostic disc."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_modern_helmets as hm
from mod_editor.core import nfl2k5_historic_rosters as ht
from mod_editor.core import nfl2k5_historic_styles as styles


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('disc',type=Path)
    ap.add_argument('--summary',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    summary=json.loads(args.summary.read_text())
    rows=[]
    with rr._outer_image()(args.disc) as archive:
        main_raw,situ=archive.read_entry(5),archive.read_entry(22)
        context=e.describe_context(main_raw,situ,archive.entries)
        ids={e.name_id:e.index for e in archive.entries}
        for d in ht.require_build_ready()['teams']:
            outer=ids[styles.name_id(d['alias'])]
            raw=archive.read_entry(outer)
            doc=rr.RosterDocument(raw[32:])
            helmets=Counter(p.record.get('helmet') for p in doc.players)
            masks=Counter(p.record.get('face_mask') for p in doc.players)
            assert len(doc.players)==len(d['players']) and set(helmets)=={0} and set(masks)<=set(range(12))
            rows.append(dict(filename=d['alias'],outer=outer,players=len(doc.players),
                             helmets=dict(helmets),masks=dict(masks),sha256=e.sha(raw)))
        main=rr.RosterDocument(main_raw[32:])
        current=[p for t in main.teams if t.kind==0 for p in main.team_players(t.index)]
        current_helmets=Counter(p.record.get('helmet') for p in current)
        current_masks=Counter(p.record.get('face_mask') for p in current)
        assert current_helmets[1]>0 and any(k>=12 for k in current_masks)
    assert len(rows)==75
    states=dict(espn25_rosters=e.image_status(args.disc),modern_helmets=hm.image_status(args.disc),
                historic_rosters_2026=ht.image_status(args.disc))
    assert set(states.values())=={'applied'},states
    assert not summary['not_applied'],summary['not_applied']
    assert 'historic_teams_quick_game' in summary['applied']
    assert 'historic_rosters_2026' in summary['applied']
    result=dict(label='PROVED OFFLINE',recipe_scope='candidate B plus ht rosters and e2 phase 2',
                applied=summary['applied'],not_applied=summary['not_applied'],owner_states=states,
                expected_foreign=summary.get('expected_foreign',{}),
                not_inspected=summary.get('not_inspected',{}),
                historic_players=sum(r['players'] for r in rows),historic_resources=rows,
                current_equipment=dict(players=len(current),helmets=dict(current_helmets),masks=dict(current_masks)))
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(label='PROVED OFFLINE',owners=len(summary['applied']),
                         historic_players=result['historic_players'],states=states,
                         expected_foreign=result['expected_foreign']),indent=2))


if __name__=='__main__':
    main()
