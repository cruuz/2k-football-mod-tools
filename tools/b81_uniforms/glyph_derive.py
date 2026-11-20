#!/usr/bin/env python3
"""b81-retail-free-art: take the retail-derived b81u digit pictures out of the package.

  glyph_derive.py DISC VERDICTS --retail RETAIL [--paint FAMILY ...] [--drop FAMILY ...]

DISC is the released v0.9 disc (every b81u digit row is pinned to its spans). VERDICTS is a JSON object
{png name: {"verdict": "A"|"B"|"C"|"unsure", "families": [...]}} (the provenance measurement of the lane,
retail-free/glyphs/glyph_provenance.json "round1"). For every row whose picture is C or unsure:

* the uniform lane made it by editing the v0.9 glyph, which the Studio builds from a retail donor on the user's own
  disc. This tool finds the edit as operations (mod_editor/core/nfl2k5_glyph_fixes_2026.DERIVE_OPS: whole rows and
  columns repeated or removed, fill grown or thinned with the outline rebuilt, an edge ring or an inline recoloured)
  whose result is the picture texel for texel, checks that the Studio compiles it to the row's output pin, and turns
  the row into a ``digit_derived`` row (no picture ships);
* a row whose picture no operation list rebuilds (a redraw drawn by code, a nameplate strip) ships as ``paint``: only
  the texels that differ from the glyph or strip the build holds at that point, with their places; a texel equal to
  it is never shipped (coordinator, 2026-11-20). ``--drop FAMILY`` withdraws a family instead (not used for beta 81).

Pictures no row uses any more are deleted from the art folder. Prints a line per family.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_bump_texture_writer as bw  # noqa: E402
from mod_editor.core import nfl2k5_glyph_fixes_2026 as gf  # noqa: E402
from nfl_tset_png_import import decode_rgba_png  # noqa: E402

ORANGE = '#D96428'                     # the Buccaneers inline (DECISIONS tb_four.py, tb_home_inline.py)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def hexc(c):
    return None if c is None else '#%02X%02X%02X' % tuple(int(x) for x in c)


# -- parameters the lane's tools measured -------------------------------------------------------------------------------

def set_colours(a):
    """embolden.py colours(): the fill (most used opaque colour) and the outline (most used one 40+ levels away)."""
    a = np.asarray(a).astype(int)
    op = a[..., 3] >= 128
    cols, cnt = np.unique(a[op][:, :3], axis=0, return_counts=True)
    fill = cols[cnt.argmax()].astype(int)
    rest = [(c.astype(int), n) for c, n in zip(cols, cnt) if np.abs(c.astype(int) - fill).max() > 40]
    return fill, (max(rest, key=lambda t: t[1])[0] if rest else None)


def ring_width(a, fill_c):
    """embolden.py ring_width() on the padded glyph."""
    b = np.pad(np.asarray(a).astype(int), ((8, 8), (8, 8), (0, 0)))
    glyph = b[..., 3] >= 128
    fill = glyph & (np.abs(b[..., :3] - fill_c).max(-1) <= 40)
    ring = glyph & ~fill
    if not ring.any():
        return 0
    depth = gf._taxicab_depth(~fill)
    picked = depth[ring & gf._grow(~glyph)]
    return int(np.median(picked)) if picked.size else None


def edge_colours(a):
    """edge6.py: the edge colour (most common on the rim) and the fill (most common other colour inside)."""
    from collections import Counter
    op = a[..., 3] >= 128
    depth = gf._taxicab_depth(np.pad(op, 1))[1:-1, 1:-1]
    rim = op & (depth == 1)
    edge = Counter(tuple(int(x) for x in c) for c in a[rim][:, :3]).most_common(1)[0][0]
    rest = Counter(tuple(int(x) for x in c) for c in a[op & (depth > 1)][:, :3])
    return edge, next(c for c, _ in rest.most_common() if c != edge)


def fill_colour(a):
    opaque = a[..., 3] == 255
    cols, counts = np.unique(a[opaque][:, :3], axis=0, return_counts=True)
    return cols[counts.argmax()]


# -- separable remap ------------------------------------------------------------------------------------------------

def apply_remap(old, rows, cols):
    return gf.derive_digit(old, [dict(op='remap', rows=rows, cols=cols)])


def _cost(new_lines, old_lines, key):
    n, m = len(new_lines), len(old_lines)
    kn, ko = key(new_lines), key(old_lines)
    out = np.empty((n, m + 1), np.int64)
    for j in range(m):
        out[:, j] = (kn != ko[j][None]).reshape(n, -1).sum(-1)
    out[:, m] = (kn != key(np.zeros_like(new_lines[:1]))[0][None]).reshape(n, -1).sum(-1)
    return out


def _monotone(cost):
    """Each new line to an old line (non-decreasing among the real ones) or to a cleared line, least mismatch."""
    n, m1 = cost.shape
    m = m1 - 1
    best = np.full((n + 1, m + 1), 1 << 60, np.int64)
    back = np.zeros((n + 1, m + 1, 2), np.int64)
    best[0, :] = 0
    for i in range(n):
        arg = np.zeros(m + 1, np.int64)
        cur = 0
        for k in range(m + 1):
            if best[i, k] < best[i, cur]:
                cur = k
            arg[k] = cur
        prefix = best[i][arg]
        for j in range(m):
            v = prefix[j + 1] + cost[i, j]
            if v < best[i + 1, j + 1]:
                best[i + 1, j + 1] = v
                back[i + 1, j + 1] = (arg[j + 1], j)
        for k in range(m + 1):
            v = best[i, k] + cost[i, m]
            if v < best[i + 1, k]:
                best[i + 1, k] = v
                back[i + 1, k] = (k, -1)
    k = int(np.argmin(best[n]))
    mapping = []
    for i in range(n, 0, -1):
        pk, j = back[i, k]
        mapping.append(int(j))
        k = int(pk)
    return mapping[::-1]


def _linear(n_len, ink_n, ink_o):
    out = [-1] * n_len
    if len(ink_n) and len(ink_o):
        for y in range(ink_n[0], ink_n[-1] + 1):
            out[y] = int(round(ink_o[0] + (y - ink_n[0]) * (ink_o[-1] - ink_o[0]) / max(ink_n[-1] - ink_n[0], 1)))
    return out


def solve_remap(new, old, key=None, exhaustive=False):
    """Monotone row and column maps of ``old`` onto ``new`` (alternating exact dynamic programs, started from the rows
    and from the columns); (rows, cols, texels left over under ``key``)."""
    full = key is None
    key = key or (lambda x: x)
    h, w = new.shape[:2]
    best = None
    for rows_first in (False, True):
        rows = _linear(h, np.nonzero((new[..., 3] > 0).any(1))[0], np.nonzero((old[..., 3] > 0).any(1))[0])
        cols = _linear(w, np.nonzero((new[..., 3] > 0).any(0))[0], np.nonzero((old[..., 3] > 0).any(0))[0])
        for _ in range(8):
            if rows_first:
                rows = _monotone(_cost(new, apply_remap(old, list(range(old.shape[0])), cols), key))
                cols = _monotone(_cost(np.swapaxes(new, 0, 1),
                                       np.swapaxes(apply_remap(old, rows, list(range(old.shape[1]))), 0, 1), key))
            else:
                cols = _monotone(_cost(np.swapaxes(new, 0, 1),
                                       np.swapaxes(apply_remap(old, rows, list(range(old.shape[1]))), 0, 1), key))
                rows = _monotone(_cost(new, apply_remap(old, list(range(old.shape[0])), cols), key))
            left = int((key(apply_remap(old, rows, cols)) != key(new)).reshape(h, w, -1).any(-1).sum())
            if best is None or left < best[2]:
                best = (rows, cols, left)
            if left == 0:
                return best
    if not exhaustive or not full or best[2] > 16:  # the fallback is for near misses in full colour only
        return best
    return _search_rows(new, old, best)


def _search_rows(new, old, best):
    """The exhaustive fallback (the alternating programs can stop in a local optimum): the old ink rows, with up to two
    rows repeated or one removed anywhere, at every nearby vertical offset; the column map exact for each."""
    h = new.shape[0]
    ink_n = np.nonzero((new[..., 3] > 0).any(1))[0]
    ink_o = np.nonzero((old[..., 3] > 0).any(1))[0]
    if not len(ink_n) or not len(ink_o):
        return best
    base = list(range(ink_o[0], ink_o[-1] + 1))
    seqs = [base]
    for i in range(len(base)):
        seqs.append(base[:i] + base[i:i + 1] + base[i:])
        seqs.append(base[:i] + base[i + 1:])
    for i in range(len(base)):
        for j in range(i, len(base)):
            seqs.append(base[:i] + base[i:i + 1] + base[i:j] + base[j:j + 1] + base[j:])
    for seq in seqs:
        for top in range(max(0, ink_n[0] - 2), ink_n[0] + 3):
            rows = [-1] * h
            for k, v in enumerate(seq):
                if 0 <= top + k < h:
                    rows[top + k] = v
            cols = _monotone(_cost(np.swapaxes(new, 0, 1),
                                   np.swapaxes(apply_remap(old, rows, list(range(old.shape[1]))), 0, 1), lambda x: x))
            left = int((apply_remap(old, rows, cols) != new).any(-1).sum())
            if left < best[2]:
                best = (rows, cols, left)
            if left == 0:
                return best
    return best


def candidates(old, digit0):
    yield []
    fill_c, out_c = set_colours(digit0)
    t = ring_width(old, fill_c) if out_c is not None else 0
    if t is not None:
        for k in (1, -1, 2, -2, 0):
            for extra in (False, True):
                if k or extra:
                    yield [dict(op='embolden', k=k, extra=extra, fill=hexc(fill_c), outline=hexc(out_c), ring=t)]
    try:
        e, f = edge_colours(old)
    except (StopIteration, IndexError):
        return
    for keep in (1, 2, 3):
        yield [dict(op='edge', keep=keep, edge=hexc(e), fill=hexc(f))]


def recolour_to(got, new):
    """An exact colour swap list that turns ``got`` into ``new``, or None (alpha must already agree)."""
    if not np.array_equal(got[..., 3], new[..., 3]):
        return None
    differ = (got[..., :3] != new[..., :3]).any(-1) & (new[..., 3] > 0)
    pairs = {}
    for a, b in zip(map(tuple, got[differ][:, :3].tolist()), map(tuple, new[differ][:, :3].tolist())):
        if pairs.setdefault(a, b) != b:
            return None
    ops = [dict(op='recolour', pairs=[[hexc(a), hexc(b)] for a, b in sorted(pairs.items())])]
    return ops if np.array_equal(gf.derive_digit(got, ops), new) else None


def find_ops(old, new, digit0):
    misses = []
    for pre in candidates(old, digit0):
        src = gf.derive_digit(old, pre)
        rows, cols, left = solve_remap(new, src)
        if left == 0:
            ops = pre + [dict(op='remap', rows=rows, cols=cols)]
            if np.array_equal(gf.derive_digit(old, ops), new):
                return ops
        misses.append((left, len(misses), pre, src))
    # near misses: the alternating programs stopped in a local optimum; search the rows exhaustively (best first)
    for left, _i, pre, src in sorted(misses, key=lambda m: m[:2])[:2]:
        if 0 < left <= 16:
            rows, cols, left = solve_remap(new, src, exhaustive=True)
            ops = pre + [dict(op='remap', rows=rows, cols=cols)]
            if left == 0 and np.array_equal(gf.derive_digit(old, ops), new):
                return ops
    # the same geometry with colours swapped afterwards (a club colour corrected): the alpha alone fixes the maps
    for _left, _i, pre, src in sorted(misses, key=lambda m: m[:2])[:4]:
        rows, cols, left = solve_remap(new, src, key=lambda x: x[..., 3:])
        if left == 0:
            ops = pre + [dict(op='remap', rows=rows, cols=cols)]
            swap = recolour_to(gf.derive_digit(old, ops), new)
            if swap is not None:
                return ops + swap
    # an inline after the geometry (the Buccaneers): solve the geometry with the inline taken back out, then apply it
    orange = np.array([int(ORANGE[i:i + 2], 16) for i in (1, 3, 5)])
    inline = (new[..., :3] == orange).all(-1) & (new[..., 3] == 255)
    if inline.any():
        if old.shape == new.shape:                  # the geometry as released (every digit but the narrowed 4)
            same = [dict(op='remap', rows=list(range(old.shape[0])), cols=list(range(old.shape[1])))]
            for tail in ([dict(op='inline_fill', colour=ORANGE, fill=hexc(fill_colour(old)))],
                         [dict(op='inline_dark', colour=ORANGE)]):
                if np.array_equal(gf.derive_digit(old, same + tail), new):
                    return same + tail
        undone = new.copy()
        undone[inline, :3] = fill_colour(old)
        rows, cols, left = solve_remap(undone, old)
        if left == 0:
            geo = apply_remap(old, rows, cols)
            ops = [dict(op='remap', rows=rows, cols=cols), dict(op='inline_fill', colour=ORANGE, fill=hexc(fill_colour(geo)))]
            if np.array_equal(gf.derive_digit(old, ops), new):
                return ops
        dark = lambda x: np.concatenate([x[..., 3:], np.where((x[..., :3].max(-1, keepdims=True) < 0x60) | (x[..., 3:] < 255),
                                                              x[..., :3], 0)], -1)
        rows, cols, left = solve_remap(new, old, key=dark)
        if left == 0:
            geo = apply_remap(old, rows, cols)
            for tail in ([dict(op='inline_dark', colour=ORANGE)],
                         [dict(op='inline_fill', colour=ORANGE, fill=hexc(fill_colour(geo)))]):
                ops = [dict(op='remap', rows=rows, cols=cols)] + tail
                if np.array_equal(gf.derive_digit(old, ops), new):
                    return ops
    return None


#: review F4 (coordinator, 2026-11-20): a difference may never encode the base's shape. Erasures are instructions,
#: additions are pixels; the shipped texels of a ``paint`` op may cover at most this share of the base's edge texels.
EDGE_OVERLAP_LIMIT = 0.25


def base_edges(a):
    """Texels whose colour or alpha differs from a 4-neighbour: both sides of the base's outlines and colour boundaries
    (a clear texel next to ink counts, so a paint of the clear surround is measured too)."""
    a = np.asarray(a)
    key = (a[..., 0].astype(np.int64) << 24) | (a[..., 1].astype(np.int64) << 16) | (a[..., 2].astype(np.int64) << 8) | a[..., 3]
    key = np.where(a[..., 3] == 0, -1, key)
    edge = np.zeros(key.shape, bool)
    edge[1:] |= key[1:] != key[:-1]
    edge[:-1] |= key[:-1] != key[1:]
    edge[:, 1:] |= key[:, 1:] != key[:, :-1]
    edge[:, :-1] |= key[:, :-1] != key[:, 1:]
    return edge


def paint_positions(ops, shape):
    out = np.zeros(shape[:2], bool)
    for op in ops:
        if op['op'] == 'paint':
            for y, x0, values in op['runs']:
                out[y, x0:x0 + len(values) // 8] = True
    return out


def edge_overlap(base, ops):
    """Share of the base's edge texels that the shipped paint texels cover (0 when nothing is painted)."""
    edges = base_edges(base)
    if not edges.any():
        return 0.0
    return float((paint_positions(ops, base.shape) & edges).sum()) / float(edges.sum())


def dthick(dx, dy, s=2, stretch=1.7, dk=0.95):
    """jax_thin / font._dthick: the horizontal weight of a diagonal (authoring time only; stored as float64 hex)."""
    ang = np.arctan2(abs(dx) * stretch, abs(dy))
    return max(float(s), s * dk / max(np.cos(ang), 0.35))


def thin_weights(ch, W, H, s=2, b=2):
    """The diagonal weights jax_thin.thin computes for one letter, in its order (see nfl2k5_glyph_fixes_2026)."""
    if ch == 'W':
        t = dthick(W * 0.2, H * 0.8, s)
        q1, q3 = W * 0.30, W * 0.70
        xa = W / 2 - t / 2
        return [t, dthick(q1 - t / 2 - xa, H - H * 0.22, s), dthick(q3 - t / 2 - xa, H - H * 0.22, s)]
    if ch == 'M':
        depth = H * 0.70
        t = dthick(W / 2, depth, s)
        return [t, dthick(W / 2 - t / 2, depth, s), dthick(W / 2 - t / 2 - (W - t), depth, s)]
    if ch == 'N':
        t = dthick(W - s, H, s)
        return [t, dthick(W - t, H, s)]
    if ch == 'K':
        yk = H * 0.58
        t = dthick(W - s, yk, s)
        d1 = dthick(s - (W - t), yk, s)
        ya = yk - 4.0
        xa = (W - t) + (ya / yk) * (s - (W - t)) + 1.0
        t2 = dthick(W - xa, H - ya, s)
        return [t, d1, t2, dthick(W - round(t2) - xa, H - ya, s)]
    if ch == 'X':
        t = dthick(W, H, s)
        return [t, dthick(W - t, H, s), dthick(0 - (W - t), H, s)]
    if ch == 'Y':
        yj = H * 0.52
        x0 = int(round((W - s) / 2))
        t = dthick(W / 2, yj, s)
        return [t, dthick(x0, yj, s), dthick(x0 + s - t - (W - t), yj, s)]
    if ch == 'Z':
        t = dthick(W, H - 2 * b, s)
        return [t, dthick(0 - (W - t), H - b + 0.5 - (b - 0.5), s)]
    return []


def thin_op(base_strip, name_span, new, stem=2, bar=2, top=4, cap=24):
    """The ``thin_letters`` instruction that rebuilds ``new`` from the strip the build holds, or None."""
    sys.path.insert(0, str(ROOT))
    from mod_editor.core import nfl2k5_kit_fixes_2026 as kf
    offsets = [int(x) for x, _w in kf.name_metrics(name_span)]
    opaque = new[new[..., 3] == 255][:, :3]
    if not len(opaque):
        return None
    fill = hexc(np.unique(opaque, axis=0)[0])
    weights = {}
    for i, ch in enumerate(gf._THIN_GLYPHS):
        m = base_strip[top:top + cap, offsets[i]:offsets[i] + 32, 3] >= 128
        cols = np.flatnonzero(m.any(0))
        w = thin_weights(ch, int(cols[-1] - cols[0] + 1), cap, stem, bar)
        if w:
            weights[ch] = [float(v).hex() for v in w]
    op = dict(op='thin_letters', stem=stem, bar=bar, top=top, cap=cap, fill=fill, offsets=offsets, weights=weights)
    return [op] if np.array_equal(gf.derive_digit(base_strip, [op]), new) else None


def paint_runs(base, new):
    """The texels of ``new`` that differ from ``base`` as [row, first column, "RRGGBBAA" per texel] runs."""
    differ = (np.asarray(base) != np.asarray(new)).any(-1)
    runs = []
    for y in range(differ.shape[0]):
        xs = np.flatnonzero(differ[y])
        if not len(xs):
            continue
        start = prev = int(xs[0])
        for x in [int(v) for v in xs[1:]] + [None]:
            if x is not None and x == prev + 1:
                prev = x
                continue
            runs.append([y, start, new[y, start:prev + 1].tobytes().hex().upper()])
            if x is not None:
                start = prev = x
    return runs


def _find_job(job):
    old, new, digit0 = job
    return find_ops(old, new, digit0)


def convert(disc, retail, limit_rows=None):
    """Review F3/F4: re-express every derived row that ships texels (``paint``) under the rule "a difference may never
    encode the base's shape": a nameplate strip as ``thin_letters`` (no texel), a digit as operations, or a remap plus a
    residual paint whose texels cover at most EDGE_OVERLAP_LIMIT of the base's edges. The picture (``rgba_sha256``) and
    the compiled span (``after_sha256``) of every row stay exactly as they are (checked)."""
    import b81_uniform_pass as up
    path = gf.DATA_B81U
    document = json.loads(path.read_text(encoding='utf-8'))
    rows = [r for r in document['textures'] if r['kind'] in ('digit_derived', 'names_derived')
            and any(op['op'] == 'paint' for op in r['derive'])]
    if limit_rows:
        rows = [r for r in rows if f"{r['selector']}:{r['chunk']}" in limit_rows]
    with bw._Image.open(Path(disc), writable=False) as image:
        index = bw._parsed_index(image)
        entries = {bw.logical_name_for(e.name_id): e for e in index.entries}
        raws = {s_: image.read_segments(index.sub_extents(entries[s_ + '.IFF'], 0, entries[s_ + '.IFF'].size))
                for s_ in sorted({r['selector'] for r in rows})}
    strips = sorted({r['selector'] for r in rows if r['kind'] == 'names_derived'})
    if strips:
        kits = up.retail_kits_for_nameplates(retail)
        for s_ in strips:
            raws[s_] = up.after_nameplate_pass(s_, raws[s_], kits)

    def span_of(sel, chunk):
        c = gf._chunk_for(raws[sel], chunk)
        return raws[sel][c.offset:c.end_offset]

    report = {}
    for row in rows:
        span = span_of(row['selector'], row['chunk'])
        assert sha(span) == row['before_sha256'], (row['selector'], row['chunk'], 'input differs from its pin')
        names = row['kind'] == 'names_derived'
        base = gf.names_level0(span) if names else gf.digit_level0(span)
        picture = gf.derive_digit(base, row['derive'])
        assert sha(picture.tobytes()) == row['rgba_sha256'], (row['selector'], row['chunk'], 'picture pin')
        ops = None
        if names:
            for stem, bar in ((3, 3), (2, 2), (3, 2), (2, 3)):
                ops = thin_op(base, span_of(row['selector'], 44), picture, stem, bar)
                if ops:
                    break
            assert ops, (row['selector'], 'no thinning rule rebuilds this strip')
        else:
            # the operations before the paint stay (round 2's own Ravens and Raiders operations); a row that is all
            # paint (the Giants and Cowboys navy redraws as first restored) takes the remap that explains most of it
            lead = [op for op in row['derive'] if op['op'] != 'paint']
            if not lead:
                rows_, cols_, _left = solve_remap(picture, base)
                lead = [dict(op='remap', rows=rows_, cols=cols_)]
            # the colour stored under clear texels, by rule: a recolour that moves it too (as the picture editor did),
            # or one colour under every clear texel (``clear_rgb``); never a list of the clear surround's texels
            clear = picture[..., 3] == 0
            if any(op['op'] == 'recolour' for op in lead):
                alt = [dict(op, hidden=True) if op['op'] == 'recolour' else op for op in lead]
                if np.array_equal(gf.derive_digit(base, alt)[clear], picture[clear]):
                    lead = alt
            hidden = np.unique(picture[clear][:, :3], axis=0)
            if len(hidden) == 1 and not any(op['op'] == 'clear_rgb' for op in lead):
                alt = lead + [dict(op='clear_rgb', colour='#%02X%02X%02X' % tuple(int(v) for v in hidden[0]))]
                left = lambda ops_: int((gf.derive_digit(base, ops_) != picture).any(-1).sum())
                if left(alt) < left(lead):                  # only where it spares listed texels
                    lead = alt
            ops = lead + [dict(op='paint', runs=paint_runs(gf.derive_digit(base, lead), picture))]
            if edge_overlap(base, ops) > EDGE_OVERLAP_LIMIT:
                fam = 33 if row['chunk'] >= 33 else 13
                found = find_ops(base, picture, gf.digit_level0(span_of(row['selector'], fam)))
                if found is not None:
                    ops = found
            if ops[-1]['op'] == 'paint' and not ops[-1]['runs']:
                ops = ops[:-1]
        assert np.array_equal(gf.derive_digit(base, ops), picture), (row['selector'], row['chunk'])
        overlap = edge_overlap(base, ops)
        new_row = dict(row, derive=ops)
        compiled, _detail = (gf.compile_derived_names if names else gf.compile_derived_digit)(span, new_row)
        assert sha(compiled) == row['after_sha256'], (row['selector'], row['chunk'], 'compile differs')
        key = '+'.join(o['op'] for o in ops)
        line = report.setdefault(row['defects'][0] if row.get('defects') else row['selector'], dict(rows=0, ops={}))
        line['rows'] += 1
        line['ops'][key] = line['ops'].get(key, 0) + 1
        line['painted_texels'] = line.get('painted_texels', 0) + int(paint_positions(ops, base.shape).sum())
        line['max_edge_overlap'] = max(line.get('max_edge_overlap', 0.0), round(overlap, 3))
        if overlap > EDGE_OVERLAP_LIMIT:
            line.setdefault('refused', []).append(f"{row['selector']}:{row['chunk']} {overlap:.2f}")
            continue
        row['derive'] = ops
    path.write_text(json.dumps(document, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    gf.spec(path)
    for family, line in sorted(report.items()):
        print(family, json.dumps(line, sort_keys=True))
    refused = [r for line in report.values() for r in line.get('refused', [])]
    print('rows', len(rows), 'refused (texels would trace the base):', refused)
    return 1 if refused else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('disc')
    parser.add_argument('verdicts')
    parser.add_argument('--retail', help='the retail disc (the nameplate strips are pinned after the nameplate pass)')
    parser.add_argument('--paint', nargs='*', default=[], help='families redrawn by code: skip the operation search, '
                        'ship the texels that differ from the base')
    parser.add_argument('--drop', nargs='*', default=[], help='families to withdraw instead (not used for beta 81)')
    parser.add_argument('--convert', action='store_true', help='re-express derived rows that ship texels (review F3/F4)')
    args = parser.parse_args()
    if args.convert:
        raise SystemExit(convert(args.disc, args.retail))
    path = gf.DATA_B81U
    document = json.loads(path.read_text(encoding='utf-8'))
    folder = gf.art_folder(document)
    verdicts = json.loads(Path(args.verdicts).read_text(encoding='utf-8'))
    retail_derived = {png for png, v in verdicts.items() if v['verdict'] in ('C', 'unsure')}
    rows = [r for r in document['textures'] if r.get('png') in retail_derived]
    with bw._Image.open(Path(args.disc), writable=False) as image:
        index = bw._parsed_index(image)
        entries = {bw.logical_name_for(e.name_id): e for e in index.entries}
        raws = {}
        for sel in sorted({r['selector'] for r in rows}):
            e = entries[sel + '.IFF']
            raws[sel] = image.read_segments(index.sub_extents(e, 0, e.size))
    if any(r['kind'] == 'names_png' for r in rows):
        # the strip rows are pinned to the strip a build holds after the nameplate pass (b81_uniform_pass helpers)
        import b81_uniform_pass as up
        retail_kits = up.retail_kits_for_nameplates(args.retail)
        for sel in sorted({r['selector'] for r in rows if r['kind'] == 'names_png'}):
            raws[sel] = up.after_nameplate_pass(sel, raws[sel], retail_kits)

    def span_of(sel, chunk):
        c = gf._chunk_for(raws[sel], chunk)
        return raws[sel][c.offset:c.end_offset]

    def picture(row, shape):
        payload = (folder / row['png']).read_bytes()
        if row['kind'] == 'names_png':
            return gf.names_png_rgba(payload)
        w, h, rgba = decode_rgba_png(payload, (shape[1], shape[0]))
        return np.frombuffer(rgba, np.uint8).reshape(h, w, 4)

    drop_families = set(args.drop)
    paint_families = set(args.paint)
    drop, report, jobs, keys = set(), {}, [], {}
    for row in rows:
        family = verdicts[row['png']]['families'][0]
        span = span_of(row['selector'], row['chunk'])
        assert sha(span) == row['before_sha256'], (row['selector'], row['chunk'])
        if row['kind'] == 'digit_png' and family not in drop_families | paint_families:
            fam = 'arm' if '_digit_arm_' in row['png'] else 'jersey'
            digit0 = span_of(row['selector'], (33 if fam == 'arm' else 13))
            key = (row['before_sha256'], row['png_sha256'], sha(digit0))
            if key not in keys:
                old = gf.digit_level0(span)
                keys[key] = len(jobs)
                jobs.append((old, picture(row, old.shape), gf.digit_level0(digit0)))
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=3) as pool:
        found = list(pool.map(_find_job, jobs, chunksize=1))
    for row in rows:
        family = verdicts[row['png']]['families'][0]
        line = report.setdefault(family, dict(rows=0, operations=0, painted=0, painted_texels=0, dropped=0, ops={}))
        line['rows'] += 1
        if family in drop_families:
            drop.add((row['selector'], row['chunk']))
            line['dropped'] += 1
            continue
        span = span_of(row['selector'], row['chunk'])
        if row['kind'] == 'names_png':
            base = gf.names_level0(span)
            new = picture(row, base.shape)
            ops = thin_op(base, span_of(row['selector'], 44), new)    # the old letters cleared by instruction (F3)
            kind = 'names_derived'
        elif family in paint_families:
            # drawn by code: the remap of the build's glyph that explains most of it, then only the texels that
            # still differ (review F4: the old outline is never shipped as texels)
            base = gf.digit_level0(span)
            new = picture(row, base.shape)
            rows_, cols_, _left = solve_remap(new, base)
            remap = [dict(op='remap', rows=rows_, cols=cols_)]
            ops = remap + [dict(op='paint', runs=paint_runs(gf.derive_digit(base, remap), new))]
            kind = 'digit_derived'
        else:
            fam = 'arm' if '_digit_arm_' in row['png'] else 'jersey'
            key = (row['before_sha256'], row['png_sha256'], sha(span_of(row['selector'], (33 if fam == 'arm' else 13))))
            base, new, _d0 = jobs[keys[key]]
            ops = found[keys[key]]
            kind = 'digit_derived'
        if ops is None:
            # no operation list rebuilds it: ship only the texels that differ from what the build holds here
            ops = [dict(op='paint', runs=paint_runs(base, new))]
        painted = int(paint_positions(ops, np.asarray(base).shape).sum())
        if painted:
            overlap = edge_overlap(base, ops)
            assert overlap <= EDGE_OVERLAP_LIMIT, (row['selector'], row['chunk'], 'shipped texels cover %.2f of the '
                                                   'base edges: the difference would encode the base shape' % overlap)
            line['painted'] += 1
            line['painted_texels'] += painted
            line['max_edge_overlap'] = max(line.get('max_edge_overlap', 0.0), round(overlap, 3))
        else:
            line['operations'] += 1
        derived = dict(row, kind=kind, derive=ops, rgba_sha256=sha(np.ascontiguousarray(new).tobytes()))
        for name in ('png', 'png_sha256'):
            derived.pop(name)
        assert np.array_equal(gf.derive_digit(base, ops), new), (row['selector'], row['chunk'], 'derivation differs')
        compile_row = gf.compile_derived_names if kind == 'names_derived' else gf.compile_derived_digit
        compiled, _detail = compile_row(span, derived)
        assert sha(compiled) == row['after_sha256'], (row['selector'], row['chunk'], 'compile differs')
        row.clear()
        row.update(derived)
        kinds = '+'.join(o['op'] for o in ops)
        line['ops'][kinds] = line['ops'].get(kinds, 0) + 1
    # a withdrawn nameplate strip takes its glyph widths with it (they were set for those letters)
    strips = {r['selector'] for r in document['textures'] if (r['selector'], r['chunk']) in drop and r['kind'] == 'names_png'}
    for r in document['textures']:
        if r['kind'] == 'name_widths' and r['selector'] in strips:
            drop.add((r['selector'], r['chunk']))
    document['textures'] = [r for r in document['textures'] if (r['selector'], r['chunk']) not in drop]
    used = {r['png'] for r in document['textures'] if 'png' in r}
    removed = 0
    for png in sorted(p.name for p in folder.glob('*.png')):
        if png not in used:
            (folder / png).unlink()
            removed += 1
    path.write_text(json.dumps(document, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    gf.spec(path)
    for family, line in sorted(report.items()):
        print(family, json.dumps(line, sort_keys=True))
    print('rows now', len(document['textures']), 'withdrawn', len(drop), 'pictures deleted', removed, 'pictures left', len(used))


if __name__ == '__main__':
    main()
