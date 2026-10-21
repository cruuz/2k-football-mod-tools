"""Give the scorebar ESPN's asymmetric outline: a rounded upper-right corner, the other three nearly square.

The outline is a rounded rectangle in layout pixels (which are display pixels at both aspects). Every static
layer that reaches the bar's right edge gets that outline's box-filtered coverage per source texel, through its own
stretch and flip, so no square ghost survives behind the curve. The home rim's top highlight then follows the curve
and runs down the right side with the falloff the top line already has. Logos are separate textures and untouched.

python3 tools/scorebug_sprite/corner_shape.py [--folder FOLDER] [--check]
"""
from pathlib import Path
import argparse
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FOLDER = ROOT/'data/nfl2k5_scorebug_sprite'
# 2026 ESPN MNF/NFL temporal-median contour fits: R 19.25 and 17.75 px on a 110 px bar (hd1 SCOREBUG_SHAPE_SPEC).
# The body's 6 px wide texels and bilinear sampling pull the drawn 50% contour in, so the authored radius is larger:
# 21 renders as about 18.5 through the Studio's own atlas and scene at 1x and 3x.
RADIUS = 21.0
RENDERED_RADIUS = 18.5
# The home rim's top line, measured from its own rows: 139 at the first row centre, e-folding over 2 display px.
RIM_PEAK, RIM_CENTRE, RIM_FALLOFF = 139, 1.22, 2.0
# Broadcast lip: a brighter glint mid-curve and a slightly wider line down the right side than along the top.
ARC_GLINT, SIDE_FALLOFF = 0.35, 2.5
SUPERSAMPLE = 6
# Marks whose upper-right tip reached past the curve, checked over every team panel: only Washington's full-height
# W. A smaller zoom clears it without shifting the mark into the panel's left edge.
LOGO_CLEARANCE = {'WAS': dict(zoom=0.94)}
BEFORE_SHA256 = 'eba14b66c490fc08f57900fd615c278f851472552eb54e717218d300c1888f4b'
RECORD = 'hu1_corner'


def bar_box(spec):
    return next(r['box'] for r in spec['static'] if r['name'] == 'body')


def edge_layers(spec):
    """Static atlas layers whose quad reaches the bar's right edge."""
    right = bar_box(spec)[2]
    return [r for r in spec['static'] if r['cell'] != 'logo' and r['box'][2] >= right]


def inside(x, y, box, radius=RADIUS):
    x0, y0, x1, y1 = box
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cx, cy = x1-radius, y0+radius
    return not (x > cx and y < cy) or math.hypot(x-cx, y-cy) <= radius


def depth(x, y, box, radius=RADIUS):
    """Distance inside the right end's outline (top, curve, right side) and where along it the point lies."""
    x0, y0, x1, y1 = box
    cx, cy = x1-radius, y0+radius
    if x > cx and y < cy:
        angle = math.atan2(x-cx, cy-y)
        return radius-math.hypot(x-cx, y-cy), 'arc', angle
    if x1-x < y-y0:
        return x1-x, 'side', (y-cy)/max(1e-6, y1-cy)
    return y-y0, 'top', 0.0


def rim_alpha(x, y, box, radius=RADIUS):
    d, part, where = depth(x, y, box, radius)
    if d < 0:
        return 0.0
    peak, falloff = RIM_PEAK, RIM_FALLOFF
    if part == 'arc':
        peak *= 1+ARC_GLINT*math.sin(2*where)
        falloff += (SIDE_FALLOFF-RIM_FALLOFF)*math.sin(where)
    elif part == 'side':
        falloff = SIDE_FALLOFF
    return peak*math.exp(-max(0.0, d-RIM_CENTRE)/falloff)


def footprint(row, cell_size, i, j):
    """Display rectangle of source texel (i, j) of a static layer."""
    x0, y0, x1, y1 = row['box']
    w, h = cell_size
    sx, sy = (x1-x0)/w, (y1-y0)/h
    left = x1-(i+1)*sx if row.get('flip_x') else x0+i*sx
    return left, y0+j*sy, left+sx, y0+(j+1)*sy


def coverage(rect, box, radius=RADIUS, n=SUPERSAMPLE):
    a, b, c, d = rect
    hits = sum(inside(a+(c-a)*(u+.5)/n, b+(d-b)*(v+.5)/n, box, radius) for u in range(n) for v in range(n))
    return hits/(n*n)


def shape(image, spec, radius=RADIUS):
    """Return a copy of the template with the outline applied to every right-edge layer."""
    import numpy as np
    from PIL import Image
    image = image.convert('RGBA')
    out = np.asarray(image).copy()
    box = bar_box(spec)
    zone_x = box[2]-radius-8
    for row in edge_layers(spec):
        cx0, cy0, cx1, cy1 = spec['cells'][row['cell']]['box']
        size = (cx1-cx0, cy1-cy0)
        rim = row['tint'] == 'home rim'
        for j in range(size[1]):
            for i in range(size[0]):
                rect = footprint(row, size, i, j)
                if rect[2] <= zone_x:
                    continue
                px = out[cy0+j, cx0+i]
                alpha = float(px[3])
                if rim:
                    centre = ((rect[0]+rect[2])/2, (rect[1]+rect[3])/2)
                    added = rim_alpha(*centre, box, radius)
                    if added > alpha:
                        alpha = added
                        px[:3] = 255
                px[3] = int(round(alpha*coverage(rect, box, radius)))
    return Image.fromarray(out, 'RGBA')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def record(spec):
    return dict(job='hu1 2026-10-14', radius=RADIUS, rendered_radius=RENDERED_RADIUS, layers=[r['name'] for r in edge_layers(spec)],
                method='rounded-rectangle coverage in layout pixels, box-filtered per source texel through each '
                       'layer stretch and flip; home rim top-line falloff continued around the curve and down the '
                       'right side; left and lower-right corners unchanged',
                reference='2026 ESPN MNF Broncos at Chiefs and NFL Raiders at Texans temporal-median contours, '
                          'R 19.25 and 17.75 px on a 110 px bar (measurement only, no broadcast pixels)',
                logo_clearance=LOGO_CLEARANCE, template_before_sha256=BEFORE_SHA256)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, default=DEFAULT_FOLDER)
    parser.add_argument('--check', action='store_true', help='report the state without writing')
    args = parser.parse_args()
    from PIL import Image
    layout = args.folder/'layout.json'
    spec = json.loads(layout.read_text(encoding='utf-8'))
    raw = (args.folder/'template.png').read_bytes()
    if spec['provenance'].get(RECORD):
        print('already shaped: template', sha(raw))
        return 0
    if sha(raw) != BEFORE_SHA256:
        raise SystemExit('unknown template; refusing to reshape (sha256 '+sha(raw)+')')
    if args.check:
        print('unshaped: template', sha(raw))
        return 0
    with Image.open(args.folder/'template.png') as image:
        shaped = shape(image, spec)
    shaped.save(args.folder/'template.png', optimize=True)
    accents_path = args.folder/'team_accents.json'
    accents = json.loads(accents_path.read_text(encoding='utf-8'))
    for team, fit in LOGO_CLEARANCE.items():
        spec['logo_fit']['by_team'][team].update(fit)
        accents['teams'][team]['logo_fit'].update(fit)
    accents_path.write_text(json.dumps(accents, indent=2)+'\n', encoding='utf-8', newline='\n')
    spec['provenance'][RECORD] = record(spec)
    layout.write_text(json.dumps(spec, indent=1)+'\n', encoding='utf-8', newline='\n')
    print('shaped: template', sha((args.folder/'template.png').read_bytes()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
