"""Contact sheets for the report: every team in 16:9 and 4:3, and the three measured matchups beside the broadcast.

``all --tag TAG``: tools/scorebug_sprite/render.py's all-teams sheet (each team against itself, 1st and 10, home
ball) for the current data folder, in both aspects: all_teams_TAG_169.png and all_teams_TAG_43.png.

``compose``: for each aspect, the broadcast crop (normalized to the same 617-pixel player bar by the measuring
module's own reference(), a small derived crop of read-only evidence), the before render and the after render of
NYG at LAR (q1 and q4), DEN at KC and LV at HOU: sheet_matchups_169.png and sheet_matchups_43.png. Run
``residuals.py --tag before --save-renders`` on the base data and ``--tag after --save-renders`` on the result
first. Renders are the offline native HUD model; no in-game result is shown or claimed.
"""
import argparse
import importlib.util
import sys
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def all_teams(tag):
    render = load(ROOT / 'tools/scorebug_sprite/render.py', 'scorebug_render')
    preview = render.sprite.NativePreview()
    for aspect, suffix in (('16:9', '169'), ('4:3', '43')):
        path = OUT / ('all_teams_%s_%s.png' % (tag, suffix))
        render.contact_sheet(preview, path, aspect)
        receipt = path.with_suffix('.json')
        if receipt.exists():
            receipt.unlink()
        image = Image.open(path).convert('RGB')
        image.save(path, optimize=True)
        print(path)


def compose():
    s12 = load(ROOT / 'reports/b76_s12/player_scale.py', 'b76_s12_player_scale')
    s11 = load(ROOT / 'reports/b72_s11/player_scale.py', 'b72_s11_player_scale')
    crop = (425, 930, 1495, 1060)
    for aspect, label in (('169', '16:9'), ('43', '4:3')):
        tiles = []
        for module in (s12, s11):
            for name, (path, _state) in module.CASES.items():
                box = module.box(crop)
                tiles.append(('%s | broadcast, normalized to the 617-pixel player bar' % name,
                              module.reference(path).crop(box)))
                for tag, caption in (('before', 'BEFORE: s12 bar (base 30db13952)'),
                                     ('after', 'AFTER: b76-s14 broadcast display shades and marks')):
                    image = Image.open(OUT / ('render_%s_%s_%s.png' % (tag, name, aspect))).convert('RGB')
                    tiles.append(('%s | %s, offline native render' % (name, caption), module.aligned(image).crop(box)))
        width = max(t.width for _, t in tiles) + 30
        height = 44 + sum(t.height + 26 for _, t in tiles) + 30
        sheet = Image.new('RGB', (width, height), '#252525')
        d = ImageDraw.Draw(sheet)
        d.text((15, 10), 'b76-s14 | %s | 617-pixel player bars | open at 100 percent' % label, fill='white')
        y = 44
        for caption, tile in tiles:
            d.text((15, y), caption, fill='#ffdb88' if 'AFTER' in caption else '#dddddd')
            sheet.paste(tile, (15, y + 18))
            y += tile.height + 26
        d.text((15, y + 2), 'The 4:3 rows reuse the 16:9 broadcast (no 4:3 broadcast exists). No in-game result is '
                            'claimed.', fill='#bbbbbb')
        sheet.save(OUT / ('sheet_matchups_%s.png' % aspect), optimize=True)
        print(OUT / ('sheet_matchups_%s.png' % aspect))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=('all', 'compose'))
    p.add_argument('--tag', default='after')
    a = p.parse_args(argv)
    all_teams(a.tag) if a.command == 'all' else compose()


if __name__ == '__main__':
    main()
