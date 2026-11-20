#!/usr/bin/env python3
"""Review rule for the kit-fix texel rows (b81-retail-free-art): an old mark is cleared by rule (the ``clear``
operation), never by listing its texels; only the new art ships as texels.

  python3 tools/b81_uniforms/kitfix_convert.py DISC SEL:CHUNK... [--prior OLD_DOC.json] [--zone FAMILY=BOXES.json]

DISC is the disc whose kit textures are the rows' inputs (the released v0.9 disc: no step before the uniform pass
touches these chunks; every input is checked against its ``before_sha256``). For each row the texture its operations
make (F) is rebuilt; the reference X is the input (or, for a row an earlier round already shipped, the texture that
round's runs make: ``--prior``, kept as they are). The tool then searches a ``clear`` (target colour, boxes, threshold,
grow) that removes the old mark the way the painter did, and writes the row as

    [the row's colour-carrier ``texels`` points] + [earlier round's runs] + [clear] + [runs of the texels still differing]

checking that the operations make F texel for texel and that the Studio compile gives the row's ``after_sha256``.
Report per row: shipped texels, erasure texels left in the runs (a texel set to the clear colour over a base mark: must be
0) and the edge overlap (EDGE_OVERLAP_LIMIT, the same rule as the glyph generator: shipped texels on the base's strong
edges over the base's strong edges in the shipped texels' box)."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_bump_texture_writer as bw  # noqa: E402
from mod_editor.core import nfl2k5_kit_fixes_2026 as kf  # noqa: E402

EDGE_OVERLAP_LIMIT = 0.25
STRONG = 32


def sha(data):
    return hashlib.sha256(data).hexdigest()


def strong_edges(a, t=STRONG):
    """Texels whose RGB differs from a 4-neighbour by at least ``t`` in some channel (a mark's outline, not cloth shading)."""
    a = a[..., :3].astype(np.int64)
    e = np.zeros(a.shape[:2], bool)
    d = np.abs(a[1:] - a[:-1]).max(-1) >= t
    e[1:] |= d
    e[:-1] |= d
    d = np.abs(a[:, 1:] - a[:, :-1]).max(-1) >= t
    e[:, 1:] |= d
    e[:, :-1] |= d
    return e


def edge_overlap(shipped, base):
    if not shipped.any():
        return 0.0
    edges = strong_edges(base)
    ys, xs = np.nonzero(shipped)
    box = np.zeros_like(shipped)
    box[max(ys.min() - 2, 0):ys.max() + 3, max(xs.min() - 2, 0):xs.max() + 3] = True
    n = int((edges & box).sum())
    return float((shipped & edges).sum()) / n if n else 0.0


def runs_of(final, now):
    """[y, x0, "RRGGBB..."] runs of the texels where ``final`` differs from ``now`` (RGB only; alpha never changes)."""
    assert (final[..., 3] == now[..., 3]).all()
    diff = (final[..., :3] != now[..., :3]).any(-1)
    rows = []
    for y in range(final.shape[0]):
        xs = np.flatnonzero(diff[y])
        if not len(xs):
            continue
        start = prev = int(xs[0])
        for x in list(xs[1:].tolist()) + [None]:
            if x is not None and x == prev + 1:
                prev = x
                continue
            rows.append([y, start, final[y, start:prev + 1, :3].tobytes().hex().upper()])
            if x is not None:
                start = prev = x
    return rows, diff


def boxes_of(mask, grow=2, most=6):
    from scipy import ndimage as ndi
    lab, _n = ndi.label(ndi.binary_dilation(mask, iterations=grow))
    bx = [[s[1].start, s[0].start, s[1].stop, s[0].stop] for s in ndi.find_objects(lab)]
    while len(bx) > most:
        best = None
        for i, j in itertools.combinations(range(len(bx)), 2):
            a, b = bx[i], bx[j]
            u = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
            cost = (u[2] - u[0]) * (u[3] - u[1]) - (a[2] - a[0]) * (a[3] - a[1]) - (b[2] - b[0]) * (b[3] - b[1])
            if best is None or cost < best[0]:
                best = (cost, i, j, u)
        _c, i, j, u = best
        bx = [b for k, b in enumerate(bx) if k not in (i, j)] + [u]
    return [[int(v) for v in b] for b in bx]


def level0(span, row):
    chunk, decoded, textures = kf.native_textures(span, row['kind'])
    planes = kf.read_planes(decoded, chunk, textures[0])
    palette = kf.read_palette(decoded, chunk, textures[0])
    if 'palette_remap' in row:
        palette, _ = kf.remap_palette(palette, row)
    return palette[planes[0]].astype(np.uint8)


def convert_row(row, span, prior_runs, zones):
    base = level0(span, row)
    final, _ = kf.paint(base, row['ops'])
    carriers = [o for o in row['ops'] if o['op'] == 'texels']
    assert [o['op'] for o in row['ops']].count('runs') == 1 and len(carriers) == len(row['ops']) - 1, row['selector']
    head = carriers + prior_runs
    ref, _ = kf.paint(base, head)
    changed = (final != ref).any(-1)
    trials = [None]
    cols, cnt = np.unique(final[changed][:, :3], axis=0, return_counts=True)
    for i in np.argsort(-cnt)[:3]:
        to = tuple(int(v) for v in cols[i])
        hexed = '#%02X%02X%02X' % to
        erased = changed & (final[..., :3] == np.array(to, np.uint8)).all(-1)
        if erased.sum() < 4:
            continue
        shapes = [boxes_of(erased, 2, most) for most in (1, 2, 4, 6)] + [z for z in zones if z]
        for bx in shapes:
            for above, grow in itertools.product((0, 8, 16, 20, 24, 32, 40, 48, 64, 96), (0, 1, 2)):
                trials.append(dict(op='clear', to=hexed, boxes=bx, above=above, grow=grow))
    best = None
    for trial in trials:
        ops = head + ([trial] if trial else [])
        now, _ = kf.paint(base, ops)
        runs, shipped = runs_of(final, now)
        to = np.array(kf.hex_rgb(trial['to']) if trial else (-1, -1, -1))
        erasure = shipped & (final[..., :3] == to).all(-1) & ~(base[..., :3] == to).all(-1)
        score = (int(erasure.sum()), round(edge_overlap(shipped, base), 4), int(shipped.sum()))
        if best is None or score < best[0]:
            best = (score, ops + [dict(op='runs', rows=runs)], shipped)
    (erasures, overlap, n), ops, shipped = best
    check, _ = kf.paint(base, ops)
    assert np.array_equal(check, final), row['selector']
    return ops, dict(shipped=n, erasure_texels=erasures, edge_overlap=overlap, changed=int(changed.sum()),
                     clear=next((o for o in ops if o['op'] == 'clear'), None) is not None)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('disc')
    parser.add_argument('rows', nargs='+')
    parser.add_argument('--prior', help='the kit-fix document of the earlier round (rows it shipped keep its runs)')
    parser.add_argument('--zone', action='append', default=[], help='SEL_PREFIX=boxes.json: a painter\'s own clear zone')
    args = parser.parse_args()
    path = kf.DATA_B81U
    document = json.loads(path.read_text(encoding='utf-8'))
    prior = {}
    if args.prior:
        prior = {f"{r['selector']}:{r['chunk']}": r for r in json.loads(Path(args.prior).read_text())['textures']}
    zones = {}
    for z in args.zone:
        prefix, file = z.split('=', 1)
        zones[prefix] = json.loads(Path(file).read_text())
    rows = {f"{r['selector']}:{r['chunk']}": r for r in document['textures']}
    report = {}
    with bw._Image.open(Path(args.disc), writable=False) as image:
        index = bw._parsed_index(image)
        entries = {bw.logical_name_for(e.name_id): e for e in index.entries}
        for key in args.rows:
            row = rows[key]
            raw = image.read_segments(index.sub_extents(entries[row['selector'] + '.IFF'], 0, entries[row['selector'] + '.IFF'].size))
            c = kf._chunk_for(raw, row['chunk'])
            span = raw[c.offset:c.end_offset]
            assert sha(span) == row['before_sha256'], (key, 'input differs from its pin')
            prior_runs = [o for o in prior[key]['ops'] if o['op'] == 'runs'] if key in prior else []
            ops, line = convert_row(row, span, prior_runs, [v for p, v in zones.items() if row['selector'].startswith(p)])
            new_row = dict(row, ops=ops)
            new, _detail = kf.compile_texture(span, new_row)
            assert sha(new) == row['after_sha256'], (key, 'compile differs from its output pin')
            row['ops'] = ops
            line['over_limit'] = line['edge_overlap'] > EDGE_OVERLAP_LIMIT
            report[key] = line
            print(key, json.dumps(line), flush=True)
    path.write_text(json.dumps(document, sort_keys=True, separators=(', ', ': ')) + '\n', encoding='utf-8')
    kf.uniforms_b81()
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
