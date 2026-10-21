#!/usr/bin/env python3
"""Measure (and optionally draw) where every field's midfield logo sits against the 50-yard line and the centre line.

  python3 tools/b77/ar1_midfield_audit.py --disc DISC.iso [--codes dd,nd,ad] [--json OUT.json] [--sheets DIR]

For each field bundle (home venues ``s<NN>``, special slots and Anniversary aliases ``a<NN>``) on the disc it reads the
field scene (read only), finds the ``center_logo`` quad, maps the logo's ink through the quad's UVs to field coordinates
(centimetres, the 50 at z = 0, the centre line at x = 0) and prints the offset in centimetres and in texels of the logo
texture; ``nfl2k5_midfield_centre.recentre`` is then run on a copy and the offset after the move is printed too.
``--sheets`` writes one image per bundle with the logo drawn on a crosshair, before on the left and after on the right.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def bundle_names(codes):
    return [f"{kind}{i:02}{code}.iff" for kind in "sa" for i in range(100) for code in codes]


def field_scenes(disc, codes):
    """Yield (bundle name, rec, decoded) for every field bundle the disc holds."""
    from mod_editor.core import nfl2k5_modern_venues_2026 as mv
    mm = mv._mm()
    with mv._outer_image()(str(disc)) as archive:
        entries = {e.name_id: e for e in archive.entries}
        for name in bundle_names(codes):
            entry = entries.get(mv.name_id(name))
            if entry is None:
                continue
            data = archive.read(entry.virtual_offset, entry.size)
            try:
                chunks = mv.bundle_scenes(data)
                if "field" not in chunks:
                    continue
                rec, decoded = mm._scene(data, chunks["field"])
            except (ValueError, KeyError, IndexError):
                continue
            yield name, rec, decoded


def logo_texture(rec, decoded):
    from mod_editor.core import nfl2k5_modern_venues_2026 as mv
    from mod_editor.core import nfl2k5_midfield_centre as centre
    row = centre.logo_row(mv.p8_rows(rec), mv.rows_by_material(rec))
    return None if row is None else mv.read_texture(decoded, rec, row)


def draw(rec, decoded, texture, size=420, half_cm=900.0):
    """Top-down picture around the middle: the logo on its quad, the 50-yard line and centre line in red, the ink box in
    yellow. z runs bottom to top, x right to left."""
    import numpy as np
    from mod_editor.core import nfl2k5_midfield_centre as centre
    q = centre.quad(rec, decoded)
    canvas = np.full((size, size, 3), (34, 96, 52), np.uint8)
    if q is not None and texture is not None:
        ax, az = centre._axes(q)
        # invert (u, v) -> (x, z) for every canvas pixel
        matrix = np.array([[ax[0], ax[1]], [az[0], az[1]]])
        if abs(np.linalg.det(matrix)) > 1e-9:
            inverse = np.linalg.inv(matrix)
            ys, xs = np.mgrid[0:size, 0:size]
            wx = (xs + 0.5) / size * 2 * half_cm - half_cm
            wz = half_cm - (ys + 0.5) / size * 2 * half_cm
            uv = inverse @ np.stack([wx.ravel() - ax[2], wz.ravel() - az[2]])
            u, v = uv[0].reshape(size, size), uv[1].reshape(size, size)
            h, w = texture.shape[:2]
            tx, ty = ((u + 1) / 2 * w).astype(int), ((v + 1) / 2 * h).astype(int)
            inside = (tx >= 0) & (tx < w) & (ty >= 0) & (ty < h)
            sample = texture[np.clip(ty, 0, h - 1), np.clip(tx, 0, w - 1)]
            alpha = (sample[..., 3:4] / 255.0) * inside[..., None]
            canvas = (canvas * (1 - alpha) + sample[..., :3] * alpha).astype(np.uint8)
    mid = size // 2
    canvas[mid - 1:mid + 1, :] = (230, 30, 30)
    canvas[:, mid - 1:mid + 1] = (230, 30, 30)
    m = centre.measure(rec, decoded, texture)
    if m is not None:  # the ink centre as a yellow square
        px = int(round((m["ink_offset_cm"][0] + half_cm) / (2 * half_cm) * size))
        py = int(round((half_cm - m["ink_offset_cm"][1]) / (2 * half_cm) * size))
        canvas[max(py - 4, 0):py + 4, max(px - 4, 0):px + 4] = (255, 230, 0)
    return np.ascontiguousarray(canvas[:, ::-1])  # x runs right to left, so the mapped logo reads the right way round


def audit(disc, codes):
    from mod_editor.core import nfl2k5_midfield_centre as centre
    rows = []
    for name, rec, decoded in field_scenes(disc, codes):
        texture = logo_texture(rec, decoded)
        m = centre.measure(rec, decoded, texture)
        if m is None:
            continue
        out = bytearray(decoded)
        ranges, receipt = centre.recentre(out, rec, decoded, texture)
        after = centre.measure(rec, bytes(out), texture)
        rows.append(dict(bundle=name, before_cm=[round(v, 2) for v in m["ink_offset_cm"]],
                         before_texels=[round(v, 2) for v in m["offset_texels"]],
                         texel_cm=[round(v, 2) for v in m["texel_cm"]], state=receipt["state"],
                         after_cm=[round(v, 3) for v in after["ink_offset_cm"]], floats_moved=len(ranges)))
        yield rows[-1], rec, decoded, bytes(out), texture


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--disc", type=Path, required=True)
    parser.add_argument("--codes", default="dd,nd,ad")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--sheets", type=Path)
    args = parser.parse_args(argv)
    result = []
    for row, rec, before, after, texture in audit(args.disc, [c for c in args.codes.split(",") if c]):
        result.append(row)
        print(f"{row['bundle']:<10} before {row['before_cm']} cm = {row['before_texels']} texels"
              f"  {row['state']:<8} after {row['after_cm']} cm")
        if args.sheets and row["state"] == "moved":
            import numpy as np
            from PIL import Image
            args.sheets.mkdir(parents=True, exist_ok=True)
            sheet = np.hstack([draw(rec, before, texture), np.full((420, 6, 3), 255, np.uint8), draw(rec, after, texture)])
            Image.fromarray(sheet).save(args.sheets / f"{row['bundle'][:-4]}_before_after.png")
    moved = [r["bundle"] for r in result if r["state"] == "moved"]
    print(f"{len(result)} field bundles with a midfield logo; {len(moved)} off by more than a texel: {moved}")
    if args.json:
        args.json.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
