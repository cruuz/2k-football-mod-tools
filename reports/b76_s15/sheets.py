"""Beta 76 s15 comparison sheets: the 2026 MNF bar beside the sprite bar with records, the possession arrow and pips.

Each broadcast row is a small crop of a read-only Giants at Rams frame (Noah's off-air recording or the highlight
reel); the row under it is our bar rendered by the native preview over that same frame, in the same game state (score,
clock, down, possession, timeouts) with the week-2 records (Giants 1-0, Rams 0-1). Extra rows show states the footage
lacks: week 1 (no record), a kickoff (the arrow on the receiving team), a tie record and the playoffs. The 4:3 sheet
reuses the 16:9 broadcast rows (no 4:3 broadcast exists). Renders are the offline native HUD with the Lanczos display
approximation; nothing here is an in-game result.

    python3 reports/b76_s15/sheets.py --frames <.../scratchpad/b76>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite  # noqa: E402

GAME = dict(away='NYG', home='LAR', broadcast='monday_night', away_record=[1, 0, 0], home_record=[0, 1, 0])
MATCHED = (
    ('obs/frames/frame_000621.png', 'Giants ball, 1st 11:27, timeouts 3 / 3',
     dict(away_score=0, home_score=0, quarter=1, clock=687, play_clock=40, down=3, distance=7, possession='away',
          away_timeouts=3, home_timeouts=3)),
    ('obs/frames/frame_001526.png', 'Rams ball, 3rd :54, timeouts 3 / 3',
     dict(away_score=6, home_score=21, quarter=3, clock=54, play_clock=9, down=1, distance=10, possession='home',
          away_timeouts=3, home_timeouts=3)),
    ('obs/frames/frame_002229.png', 'Rams ball, 4th 12:07, Rams 2 timeouts left',
     dict(away_score=6, home_score=21, quarter=4, clock=727, play_clock=11, down=3, distance=1, possession='home',
          away_timeouts=3, home_timeouts=2)),
    ('mnf/frames/frame_000280.png', 'Giants ball, 2nd 6:30, Rams 1 timeout left',
     dict(away_score=0, home_score=14, quarter=2, clock=390, play_clock=40, down=3, distance=8, possession='away',
          away_timeouts=3, home_timeouts=1)),
    ('mnf/frames/frame_000361.png', 'Giants ball, 2nd 1:21, Rams 0 timeouts left',
     dict(away_score=0, home_score=14, quarter=2, clock=81, play_clock=9, down=3, distance=2, possession='away',
          away_timeouts=3, home_timeouts=0)),
)
EXTRA = (
    ('Week 1 (no game played yet): no record, no tab (as DEN at KC, week 1)',
     dict(away_score=0, home_score=0, quarter=1, clock=900, play_clock=40, down=1, distance=10, possession='away',
          away_record=[0, 0, 0], home_record=[0, 0, 0])),
    ('Kickoff, Rams kicking (phase 2): the arrow and plate mark the Giants, who receive',
     dict(away_score=0, home_score=7, quarter=1, clock=512, play_clock=40, down=1, distance=10, possession='home',
          phase=2)),
    ('Tie records, the widest text shape: Giants 8-7-1, Rams 10-5-1 (week 17)',
     dict(away_score=17, home_score=20, quarter=4, clock=95, play_clock=21, down=2, distance=6, possession='home',
          away_record=[8, 7, 1], home_record=[10, 5, 1])),
    ('Divisional round: the regular-season records (a played Wild Card win is not added)',
     dict(away_score=10, home_score=13, quarter=3, clock=301, play_clock=18, down=1, distance=10, possession='away',
          season='playoffs', away_record=[11, 5, 0], home_record=[12, 4, 0])),
)
CROP = {True: (420, 925, 1500, 1065), False: (0, 925, 1440, 1065)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--frames', type=Path, required=True, help='folder holding mnf/frames and obs/frames')
    args = parser.parse_args(argv)
    preview = sprite.NativePreview()
    receipts = []
    with tempfile.TemporaryDirectory(prefix='s15-sheets-') as folder:
        for wide in (True, False):
            tiles = []
            for relative, caption, state in MATCHED:
                frame = args.frames / relative
                tiles.append(('ESPN 2026 MNF, Giants at Rams: ' + caption,
                              Image.open(frame).convert('RGB').crop(CROP[True])))
                result = preview.render(Path(folder) / 'r.png', screenshot=frame, state=dict(GAME, **state), widescreen=wide)
                tiles.append(('b76-s15 sprite bar, same state (Giants 1-0, Rams 0-1)',
                              Image.open(result['display']['path']).convert('RGB').crop(CROP[wide])))
                receipts.append(dict(aspect='16:9' if wide else '4:3', reference=relative, state=result['state']))
            for caption, state in EXTRA:
                frame = args.frames / MATCHED[0][0]
                state = dict(GAME, **state)
                result = preview.render(Path(folder) / 'r.png', screenshot=frame, state=state, widescreen=wide)
                tiles.append(('b76-s15 sprite bar: ' + caption,
                              Image.open(result['display']['path']).convert('RGB').crop(CROP[wide])))
                receipts.append(dict(aspect='16:9' if wide else '4:3', reference=None, state=result['state']))
            width = max(t.width for _, t in tiles) + 30
            height = 44 + sum(t.height + 26 for _, t in tiles) + 40
            sheet = Image.new('RGB', (width, height), '#252525')
            d = ImageDraw.Draw(sheet)
            aspect = '16:9' if wide else '4:3'
            d.text((15, 10), f'b76-s15 | records, possession arrow, used timeouts | {aspect} | 1080-line crops | open at 100 percent',
                   fill='white')
            y = 44
            for caption, tile in tiles:
                d.text((15, y), caption, fill='#dddddd' if caption.startswith('ESPN') else '#ffdb88')
                sheet.paste(tile, (15, y + 18))
                y += tile.height + 26
            d.text((15, y + 4), ('The 4:3 rows reuse the 16:9 broadcast (no 4:3 broadcast exists). ' if not wide else '') +
                   'Offline native renders; no in-game result is claimed.', fill='#bbbbbb')
            sheet.save(OUT / f'sheet_{"169" if wide else "43"}.png', optimize=True)
    (OUT / 'sheet_receipts.json').write_text(json.dumps(receipts, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('Wrote sheet_169.png and sheet_43.png')


if __name__ == '__main__':
    raise SystemExit(main())
