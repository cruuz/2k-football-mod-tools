#!/usr/bin/env python3
"""b81-uniforms: decode every 2026 kit package of a built disc (read only) into PNGs.
usage: export_kits.py DISC OUT [SELECTOR ...]"""
import sys, json, zlib
from pathlib import Path
WT = Path('/home/noah/2k-worktrees/b81-uniforms')
sys.path[:0] = [str(WT), str(WT / 'tools'), str(WT / 'tools/b765')]
import u1_audit as U
from nfl2k5_playbook_position_recode import OuterImage
PROJ = Path('/media/noah/Storage/2K5-project/b81-art/src128/SOFTDRINK-league-project.json')
TEAMS = {'00':'ARI','01':'ATL','02':'BAL','03':'BUF','04':'CAR','05':'CHI','06':'CIN','07':'DAL','08':'DEN','09':'DET','10':'GB','11':'IND','12':'JAX','13':'KC','14':'MIA','15':'MIN','16':'NE','17':'NO','18':'NYG','19':'NYJ','20':'LV','21':'PHI','22':'PIT','23':'LAR','24':'LAC','25':'SF','26':'SEA','27':'TB','28':'TEN','29':'WAS','30':'CLE','37':'HOU'}
def selectors():
    p = json.load(open(PROJ))
    s = set()
    for e in p['edits']:
        if e.get('kind') in ('torso', 'pants', 'sleeve') and e.get('asset_code') in TEAMS:
            s.add(f"{e['asset_code']}{e['side']}{e['variant']}")
    return sorted(s, key=lambda x: (x[:2], int(x[3:]), x[2] != 'H'))
def main():
    disc, out = Path(sys.argv[1]), Path(sys.argv[2])
    want = sys.argv[3:] or selectors()
    rows = []
    with OuterImage(disc) as archive:
        lookup = {e.name_id: e for e in archive.entries}
        for sel in want:
            name_id = zlib.crc32((sel + '.IFF').encode('utf-16le')) & 0xffffffff
            entry = lookup[name_id]
            package = archive.read(entry.virtual_offset, entry.size)
            row = U.export_package(package, dict(team=TEAMS[sel[:2]], selector=sel, outer_index=entry.index), out)
            rows.append(row)
    (out / 'export.json').write_text(json.dumps({'source': str(disc), 'sets': rows}, indent=1))
    print(len(rows), 'kits')
if __name__ == '__main__':
    main()
