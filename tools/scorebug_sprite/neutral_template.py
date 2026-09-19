"""Author neutral coverage masks in the existing sprite cell layout.

Glyph cells and measured brand marks retain their source pixels. Team shapes
contain only grey/white so runtime multiplication cannot introduce a foreign hue.
"""
from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parents[2]


def neutralize(folder):
    import numpy as np
    from PIL import Image
    folder = Path(folder)
    spec = json.loads((folder/'layout.json').read_text(encoding='utf-8'))
    image = Image.open(folder/'template.png').convert('RGBA')
    if spec.get('team_accents'):
        raise ValueError('Template already neutralized; start from the original source')
    tinted = {'away_rim', 'home_rim', 'plate', 'pointer', 'capsule', 'red'}
    for name in tinted | {'body', 'housing'}:
        box = spec['cells'][name]['box']
        pixels = np.asarray(image.crop(box)).copy()
        grey = pixels[:, :, :3].max(axis=2)
        if name in ('capsule', 'red'):
            grey[:] = 255
        pixels[:, :, :3] = grey[:, :, None]
        image.paste(Image.fromarray(pixels), box[:2])
    for name in ('wing', 'home_wing'):
        box = spec['cells'][name]['box']
        pixels = np.asarray(image.crop(box)).copy()
        pixels[:, :, :3] = 255
        pixels[:, :, 3] = np.rint(pixels[:, :, 3]*.75).astype('uint8')
        image.paste(Image.fromarray(pixels), box[:2])
    for row in spec['static']:
        if row['name'] in ('capsule', 'red', 'pointer'):
            row['tint'] = 'possessing team'
    for row in spec['fields']:
        if row['name'] in ('clock', 'quarter'):
            row['colour'] = '#FFFFFF'
    spec.update(team_accents='team_accents.json', plate_tints={}, wing_tints={})
    spec['provenance']['team_shapes'] = 'Neutral masks; official per-team accents from team_accents.json; wing coverage reduced to 75 percent.'
    image.save(folder/'template.png')
    (folder/'layout.json').write_text(json.dumps(spec, indent=1)+'\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    neutralize(parser.parse_args().folder)
