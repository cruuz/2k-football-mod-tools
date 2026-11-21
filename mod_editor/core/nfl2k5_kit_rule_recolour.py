"""b81-retail-free-art (ruling 2): exact build-time recolour and move rules for the 2026 kit fixes.

Reached from ``nfl2k5_kit_fixes_2026.paint`` as ``{"op": "rule", "module": "recolour", "do": <kind>, ...}``. Each rule
reads only what the build holds (``out``: the texture so far; ``rgba``: the row's input level 0 from the user's own
disc; ``donors``: the row's pinned donor textures) and writes a new RGBA uint8 array. No rule stores a base texel: the
parameters are boxes, a few seed points, colour axes and the TARGET colours of a recolour. Integers only (numpy
int64, no floats, no unordered reductions), so the bytes are the same on every platform.

Kinds (``do``):

``ramp``    recolour keeping each texel's own shade or mix. Each texel colour c in the region is placed on the axis
            ``ends`` = [A, B] at t = clip((c - A).(B - A) / |B - A|^2, 0, 1) (an exact rational) and takes
            ``levels``[k]: k = the number of ``cuts`` [num, den] with t >= num/den, or, without cuts, t * (L - 1)
            rounded half to even (L = number of levels). Membership: inside ``boxes`` and outside ``keep``; optional
            ``min`` [num, den] (t >= num/den), ``off`` (largest RGB distance from the A-B segment, in levels;
            ``off_above``: farther than that), ``near`` / ``tolerance`` (largest channel distance to any listed
            colour), ``far`` / ``far_tolerance`` (never a texel that close to a listed colour) and ``seeds``
            [[x, y], ...]: only the 8-connected pieces of the member texels that hold a seed. Colours are read from
            the texture so far.
``scale``   recolour keeping shading by scaling: each member texel's channel c becomes round(c * T / F) (half up,
            exact integers, at most 255) for ``from`` F and ``to`` T; membership as for a ramp.
``move``    move the build's own art: the member texels of the ``src`` box of the INPUT texture (members as for a
            ramp, read from ``rgba``) are copied by ``by`` [dx, dy]. The texels they leave (members not covered by the
            moved art) first take ``vacate``: {"to": "#RRGGBB"} (a flat field colour) or {"copy_by": [dx, dy]} (the
            input's plain cloth that far away: a strip of the same fabric below the chest marks).
``map``     an exact colour table inside boxes (``pairs`` [[old, new], ...], matched on the texture so far; colour
            pairs only, no positions): only where nothing parametric is exact, e.g. a donor's art stamped 1:1 and
            requantised to this kit's palette the way the round-1 compile did (26H4 from 26H0).
``cols``    narrow a mark by taking whole columns out: inside rows ``rows`` [y0, y1) of the input, the columns of
            ``src`` (a list of runs [x0, x1)) are laid side by side from column ``at`` (rows shifted by ``dy``),
            copying only member texels of ``boxes``; the members of the old mark not covered are first vacated as for
            ``move``.
"""
from __future__ import annotations

import numpy as np

__all__ = ["apply"]


def _rgb(text):
    text = str(text).lstrip("#")
    if len(text) != 6:
        raise ValueError("kit rule: colour must be #RRGGBB: " + repr(text))
    return np.array([int(text[i:i + 2], 16) for i in (0, 2, 4)], np.int64)


def _require(ok, message):
    if not ok:
        raise ValueError("kit rule (recolour): " + message)


def _boxes(shape, boxes, keep=()):
    h, w = shape[:2]
    zone = np.zeros((h, w), bool)
    for box in boxes:
        x0, y0, x1, y1 = (int(v) for v in box)
        _require(0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h, "box outside the texture")
        zone[y0:y1, x0:x1] = True
    for box in keep:
        x0, y0, x1, y1 = (int(v) for v in box)
        zone[max(y0, 0):y1, max(x0, 0):x1] = False
    return zone


def _axis(c, ends):
    """(num, den, off2den2): t = num / den on the A-B axis (clipped to [0, 1]) and the squared distance from the
    segment times den^2, all exact integers."""
    a = _rgb(ends[0])
    d = _rgb(ends[1]) - a
    den = int((d * d).sum())
    _require(den > 0, "axis ends must differ")
    rel = c - a
    num = np.clip((rel * d).sum(axis=-1), 0, den)
    off = rel * den - d * num[..., None]
    return num, den, (off * off).sum(axis=-1)


def _ge(num, den, frac):
    """num/den >= p/q, exactly."""
    p, q = (int(v) for v in frac)
    _require(q > 0, "fraction denominator must be positive")
    return num * q >= p * den


def _pieces(member, seeds):
    """The 8-connected pieces of ``member`` that hold a seed (an explicit stack, deterministic)."""
    h, w = member.shape
    keep = np.zeros_like(member)
    stack = []
    for x, y in seeds:
        x, y = int(x), int(y)
        _require(0 <= x < w and 0 <= y < h, "seed outside the texture")
        _require(bool(member[y, x]), "seed (%d, %d) is not a member texel" % (x, y))
        stack.append((y, x))
    while stack:
        y, x = stack.pop()
        if keep[y, x] or not member[y, x]:
            continue
        keep[y, x] = True
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = y + dy, x + dx
                if (dy or dx) and 0 <= ny < h and 0 <= nx < w and member[ny, nx] and not keep[ny, nx]:
                    stack.append((ny, nx))
    return keep


def _members(src, op, zone):
    """Texels of ``zone`` that the op's membership tests accept, read from ``src`` (RGBA)."""
    c = src[..., :3].astype(np.int64)
    member = zone.copy()
    if op.get("near"):
        tol = int(op.get("tolerance", 0))
        hit = np.zeros_like(member)
        for colour in op["near"]:
            hit |= np.abs(c - _rgb(colour)).max(axis=-1) <= tol
        member &= hit
    if op.get("far"):
        # texels within ``far_tolerance`` of these colours are never members
        tol = int(op.get("far_tolerance", 0))
        for colour in op["far"]:
            member &= ~(np.abs(c - _rgb(colour)).max(axis=-1) <= tol)
    if "ends" in op and any(k in op for k in ("min", "off", "off_above")):
        num, den, off2 = _axis(c, op["ends"])
        if "min" in op:
            member &= _ge(num, den, op["min"])
        if "off" in op:
            member &= off2 <= (int(op["off"]) * den) ** 2
        if "off_above" in op:
            member &= off2 > (int(op["off_above"]) * den) ** 2
    if op.get("seeds"):
        member = _pieces(member, op["seeds"])
    return member


def _levels(c, op):
    num, den, _ = _axis(c, op["ends"])
    levels = [_rgb(v) for v in op["levels"]]
    _require(len(levels) >= 1, "a ramp needs levels")
    if len(levels) == 1:
        k = np.zeros(num.shape, np.int64)
    elif op.get("cuts") is not None:
        cuts = op["cuts"]
        _require(len(cuts) == len(levels) - 1, "a ramp needs one cut fewer than levels")
        k = np.zeros(num.shape, np.int64)
        for frac in cuts:
            k += _ge(num, den, frac).astype(np.int64)
    else:
        n = len(levels) - 1
        q, r = np.divmod(num * n, den)           # t * n = q + r / den
        twice = 2 * r
        up = (twice > den) | ((twice == den) & (q % 2 == 1))
        k = q + up.astype(np.int64)
    return np.stack(levels)[k]


def _ramp(out, op, rgba):
    src = out
    zone = _boxes(out.shape, op["boxes"], op.get("keep", ()))
    member = _members(src, op, zone)
    new = out.copy()
    if member.any():
        colours = _levels(src[..., :3].astype(np.int64)[member], op)
        new[..., :3][member] = colours.astype(np.uint8)
    return new


def _scale(out, op, rgba):
    src = out
    zone = _boxes(out.shape, op["boxes"], op.get("keep", ()))
    member = _members(src, op, zone)
    num = _rgb(op["to"])
    den = _rgb(op["from"])
    _require(bool((den > 0).all()), "a scale needs a non-zero source colour")
    new = out.copy()
    if member.any():
        c = src[..., :3].astype(np.int64)[member]
        new[..., :3][member] = np.minimum((c * num + den // 2) // den, 255).astype(np.uint8)
    return new


def _map(out, op, rgba):
    """An exact colour table inside boxes: texels whose colour is exactly ``pairs``[i][0] take ``pairs``[i][1] (every
    pair is matched on the texture as it was before this op, so pairs never chain). Used only where no parametric
    rule is exact: texels the compile's palette-twin merge moved by one level, a donor copy requantised to this kit."""
    zone = _boxes(out.shape, op["boxes"], op.get("keep", ()))
    c = out[..., :3].astype(np.int64)
    new = out.copy()
    for old, to in op["pairs"]:
        hit = zone & (c == _rgb(old)).all(axis=-1)
        new[..., :3][hit] = _rgb(to).astype(np.uint8)
    return new


def _vacate(new, gone, spec, rgba):
    """Fill the texels a move leaves: a flat colour (``to``) or the input texture's cloth ``copy_by`` [dx, dy] away."""
    if "to" in spec:
        new[..., :3][gone] = _rgb(spec["to"]).astype(np.uint8)
        return new
    if "copy_by" in spec:
        h, w = gone.shape
        dx, dy = (int(v) for v in spec["copy_by"])
        ys, xs = np.nonzero(gone)
        inside = (ys + dy >= 0) & (ys + dy < h) & (xs + dx >= 0) & (xs + dx < w)
        _require(bool(inside.all()), "vacate source outside the texture")
        new[ys, xs, :3] = rgba[ys + dy, xs + dx, :3]
        return new
    _require(False, "unknown vacate rule")


def _move(out, op, rgba):
    h, w = out.shape[:2]
    x0, y0, x1, y1 = (int(v) for v in op["src"])
    dx, dy = (int(v) for v in op["by"])
    _require(0 <= x0 + dx and x1 + dx <= w and 0 <= y0 + dy and y1 + dy <= h, "move target outside the texture")
    zone = _boxes(out.shape, [op["src"]])
    member = _members(rgba, op, zone)
    landed = np.zeros_like(member)
    landed[y0 + dy:y1 + dy, x0 + dx:x1 + dx] = member[y0:y1, x0:x1]
    new = out.copy()
    if op.get("vacate"):
        new = _vacate(new, member & ~landed, op["vacate"], rgba)
    new[landed, :3] = rgba[y0:y1, x0:x1][member[y0:y1, x0:x1]][:, :3]
    return new


def _cols(out, op, rgba):
    h, w = out.shape[:2]
    y0, y1 = (int(v) for v in op["rows"])
    dy = int(op.get("dy", 0))
    at = int(op["at"])
    src_cols = [x for a, b in op["src"] for x in range(int(a), int(b))]
    _require(0 <= y0 < y1 <= h and 0 <= y0 + dy and y1 + dy <= h, "rows outside the texture")
    _require(0 <= at and at + len(src_cols) <= w, "columns land outside the texture")
    zone = _boxes(out.shape, op["boxes"])
    member = _members(rgba, op, zone)
    landed = np.zeros_like(member)
    sx = np.array(src_cols, np.int64)
    dxs = np.arange(at, at + len(src_cols))
    landed[y0 + dy:y1 + dy, dxs] = member[y0:y1][:, sx]
    new = out.copy()
    if op.get("vacate"):
        new = _vacate(new, member & ~landed, op["vacate"], rgba)
    block = rgba[y0:y1][:, sx]
    hit = member[y0:y1][:, sx]
    region = new[y0 + dy:y1 + dy, at:at + len(src_cols)]
    region[hit, :3] = block[hit][:, :3]
    return new


def _mirror(out, op, rgba):
    """b81 R55 (the Hail Raiser): the box ``box`` takes, colour only, the mirror image of the build's own texture about
    the atlas axis ``axis`` (rows y and axis - y swap: the helmet atlas's two side islands), as the art lane's
    fixes7.mirror_upper_from_lower lays one side's logo from the other's."""
    h, w = out.shape[:2]
    x0, y0, x1, y1 = (int(v) for v in op["box"])
    axis = int(op["axis"])
    _require(0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h and 0 <= axis - y1 + 1 and axis - y0 + 1 <= h,
             "mirror box outside the texture")
    new = out.copy()
    new[y0:y1, x0:x1, :3] = rgba[axis - y1 + 1:axis - y0 + 1, x0:x1, :3][::-1]
    return new


_KINDS = {"ramp": _ramp, "scale": _scale, "map": _map, "move": _move, "cols": _cols, "mirror": _mirror}


def apply(out, op, rgba, donors):
    """One recolour rule over ``out`` (the texture so far); returns the new RGBA uint8 array."""
    kind = op.get("do")
    _require(kind in _KINDS, "unknown rule " + repr(kind))
    _require("color" not in op, "a rule names no palette colour (use a want op)")
    new = _KINDS[kind](np.asarray(out, np.uint8), op, np.asarray(rgba, np.uint8))
    return np.ascontiguousarray(new, np.uint8)
