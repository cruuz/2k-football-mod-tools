"""S10 versus s11 at identical player scale, including the supplied witnesses."""
import json
from pathlib import Path
from PIL import Image, ImageDraw
import fit as F
import player_scale as P
from mod_editor.core import nfl2k5_scorebug_teams as teams


def main():
    before_path = F.baseline()
    teams.DATA = before_path
    before = P.sprite.NativePreview(folder=before_path)
    teams.DATA = F.DATA
    after = P.sprite.NativePreview()
    matchups = dict(WAS_LAC=dict(away='WAS', home='LAC', away_score=0, home_score=0,
        clock=177, play_clock=22, quarter=1, down=1, distance=10, possession='away'),
        LV_HOU=P.CASES['LV_HOU'][1],
        PIT_TEN=dict(away='PIT', home='TEN', away_score=7, home_score=7, clock=273,
            play_clock=40, quarter=2, down=1, distance=10, possession='home'))
    (F.OUT/'sheets').mkdir(exist_ok=True)
    receipts = []
    for matchup, state in matchups.items():
        for wide in (False, True):
            aspect = '169' if wide else '43'
            sheet = Image.new('RGB', (1320, 600 if matchup=='WAS_LAC' else 370), '#252525')
            d = ImageDraw.Draw(sheet)
            d.text((15, 10), f'b72-s11 | {matchup} | {aspect} | 617-pixel bars | Open at 100 percent', fill='white')
            for col, (name, preview, data) in enumerate((('s10 BEFORE', before, before_path), ('s11 AFTER', after, F.DATA))):
                teams.DATA = data
                image, receipt = P.draw(preview, state, wide)
                image.save(F.OUT/f'{name[:3]}_{matchup}_{aspect}.png')
                receipts.append(dict(phase=name, matchup=matchup, aspect=aspect, **receipt))
                d.text((15+660*col, 42), name+' | OFFLINE native HUD and display approximation', fill='#ffdb88')
                sheet.paste(P.bar(image), (15+660*col, 65))
                fits = json.loads((data/'layout.json').read_text())['logo_fit']['by_team']
                parts = [f"{team} full source ink {F.retained(team, fits[team])['source']['ink_fraction']*100:.2f}%"
                         for team in (state['away'], state['home'])]
                d.text((15+660*col, 154), ' | '.join(parts), fill='white')
            if matchup=='WAS_LAC':
                from reports.b72_s10.sheets import WITNESSES
                for i, (filename, bounds, _state) in enumerate(WITNESSES):
                    x, y, r, b = bounds
                    original = Image.open(P.HUB/'disc_r_witness_0919'/filename).convert('RGB')
                    ox, oy = 15+i%2*660, 205+i//2*120
                    d.text((ox, oy), 'Supplied disc r witness | '+filename, fill='white')
                    sheet.paste(original.crop((x-7, y-7, r+10, b+8)), (ox, oy+20))
                footer_y=478
            elif matchup=='LV_HOU':
                d.text((15, 194), 'Supplied ESPN Raiders-Texans broadcast, normalized to the same bar width', fill='white')
                sheet.paste(P.bar(P.reference(P.CASES['LV_HOU'][0])), (15, 216))
                footer_y=305
            else:
                d.text((15, 208), 'Steelers and Titans: circular enclosures, both with zero crop tolerance.', fill='white')
                d.text((15, 235), 'No matching PIT-TEN broadcast or played s11 capture supplied.', fill='#cccccc')
                footer_y=280
            d.text((15, footer_y), 'Both candidate rows are offline. The supplied witness remains labelled with its original provenance.', fill='#cccccc')
            d.text((15, footer_y+23), 'All complete source alpha and filtered mark ink must lie inside the wing. No in-game result is claimed.', fill='#cccccc')
            d.text((15, footer_y+46), 'Display uses the same Lanczos approximation as s10; GPU calibration and gameplay remain unverified.', fill='#cccccc')
            sheet.save(F.OUT/'sheets'/f'{matchup}_{aspect}.png')
    teams.DATA = F.DATA
    F.write('sheet_receipts.json', receipts)
    print('PASS: six before/after sheets, actual player scale, both aspects.')


if __name__ == '__main__':
    main()
