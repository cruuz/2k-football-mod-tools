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


def edge_overlap(shipped, base, edges=None):
    if not shipped.any():
        return 0.0
    edges = strong_edges(base) if edges is None else edges
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
    lab, _n = ndi.label(ndi.binary_dilation(mask, iterations=grow) if grow > 0 else mask)   # iterations=0 would grow forever
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


def convert_row(row, span, prior_runs, zones, erasure_first=False):
    base = level0(span, row)
    final, _ = kf.paint(base, row['ops'])
    carriers = [o for o in row['ops'] if o['op'] == 'texels']
    assert [o['op'] for o in row['ops']].count('runs') == 1 and len(carriers) == len(row['ops']) - 1, row['selector']
    # the one-texel ``texels`` operations only name palette colours: they become ``want`` (a colour, no texel), and the
    # runs carry whatever those texels still need
    wants = [dict(op='want', color=o['color']) for o in carriers]
    head = wants + prior_runs
    ref, _ = kf.paint(base, head)
    changed = (final != ref).any(-1)
    edges = strong_edges(base)
    # an erasure: a texel the row sets to the texture's field colour where the base had a mark (the measure the release
    # check's generator uses, tools/b81_uniforms/texel_rows.py)
    bcols, bcnt = np.unique(base[..., :3].reshape(-1, 3), axis=0, return_counts=True)
    field = bcols[bcnt.argmax()].astype(np.int64)
    marked = (np.abs(base[..., :3].astype(np.int64) - field).max(-1) >= 48) | edges
    to_field = np.abs(final[..., :3].astype(np.int64) - field).max(-1) <= 8
    trials = [None]
    cols, cnt = np.unique(final[changed][:, :3], axis=0, return_counts=True)
    candidates = [tuple(int(v) for v in field)] + [tuple(int(v) for v in cols[i]) for i in np.argsort(-cnt)[:3]]
    near = changed & to_field                          # the field shade the painter put back (a local cloth shade)
    if near.any():
        ncols, ncnt = np.unique(final[near][:, :3], axis=0, return_counts=True)
        candidates += [tuple(int(v) for v in ncols[i]) for i in np.argsort(-ncnt)[:2]]
    for to in dict.fromkeys(candidates):
        hexed = '#%02X%02X%02X' % to
        erased = changed & (final[..., :3] == np.array(to, np.uint8)).all(-1)
        if to == candidates[0] or near[(final[..., :3] == np.array(to, np.uint8)).all(-1)].any():
            erased = changed & to_field
        if erased.sum() < 4:
            continue
        # boxes never reach beyond the texels the row changes (grow 0): a clear that touched a texel the row keeps
        # would make the runs put the base's own colour back there
        shapes = ([boxes_of(changed, 0, most) for most in (1, 2, 4, 6)] + [boxes_of(erased, 0, most) for most in (1, 2, 4)]
                  + [z for z in zones if z])
        if erasure_first:
            shapes += [boxes_of(erased, 0, most) for most in (8, 16)]
        for bx in shapes:
            for above, grow in itertools.product((0, 8, 16, 20, 24, 32, 40, 48, 64, 96), (0, 1, 2)):
                trials.append(dict(op='clear', to=hexed, boxes=bx, above=above, grow=grow))
    best = None
    for trial in trials:
        ops = head + ([trial] if trial else [])
        now, _ = kf.paint(base, ops)
        runs, shipped = runs_of(final, now)
        erasure = shipped & to_field & marked & changed
        restored = shipped & ~changed                  # a texel the row keeps, shipped back: the base's own colour
        score = (int(restored.sum()), int(erasure.sum()), round(edge_overlap(shipped, base, edges), 4), int(shipped.sum()))
        if erasure_first:                              # authored art over a region cleared by rule (ruling 1)
            score = (int(erasure.sum()), int(restored.sum())) + score[2:]
        if best is None or score < best[0]:
            best = (score, ops + [dict(op='runs', rows=runs)], shipped)
    for _stage in range(4 if erasure_first else 0):
        if best[0][0] == 0:
            break
        # a further clear, in the shade the painter put back, for what the clears so far left (coarse boxes only)
        ops1 = best[1][:-1]
        now1, _ = kf.paint(base, ops1)
        _r, left = runs_of(final, now1)
        left &= to_field & marked & changed
        lcols, lcnt = np.unique(final[left][:, :3], axis=0, return_counts=True)
        hexed = '#%02X%02X%02X' % tuple(int(v) for v in (lcols[lcnt.argmax()] if len(lcols) else field))
        for most in (1, 2, 3, 4):
            for bx in [boxes_of(left, 0, most), boxes_of(left, 1, most)]:      # grown by one: never single texels
                if any((x1 - x0) * (y1 - y0) < 4 for x0, y0, x1, y1 in bx):
                    continue
                for above, grow in itertools.product((0, 8, 16, 24, 32, 48), (0, 1)):
                    trial = dict(op='clear', to=hexed, boxes=bx, above=above, grow=grow)
                    ops = ops1 + [trial]
                    now, _ = kf.paint(base, ops)
                    runs, shipped = runs_of(final, now)
                    erasure = shipped & to_field & marked & changed
                    restored = shipped & ~changed
                    score = (int(erasure.sum()), int(restored.sum()), round(edge_overlap(shipped, base, edges), 4),
                             int(shipped.sum()))
                    if score < best[0]:
                        best = (score, ops + [dict(op='runs', rows=runs)], shipped)
    (restored, erasures, overlap, n), ops, shipped = best
    if erasure_first:
        erasures, restored = restored, erasures                # the tuple was (erasure, restored, ...)
    check, _ = kf.paint(base, ops)
    assert np.array_equal(check, final), row['selector']
    return ops, dict(shipped=n, erasure_texels=erasures, restored_texels=restored, edge_overlap=overlap, changed=int(changed.sum()),
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
