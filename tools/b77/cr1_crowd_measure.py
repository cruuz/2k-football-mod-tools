#!/usr/bin/env python3
"""cr1: crowd person proportion audit for the stadium scenes of venue bundles (read only, offline).

    python3 tools/b77/cr1_crowd_measure.py --retail DIR --files DIR --out DIR [--codes s07 ...]

For every visible crowd triangle (material ``crowd``) the affine map from atlas UV to world metres gives:

* ``m_per_u``: metres per atlas unit along U (the runtime crowd atlas runs a person's height along U: one person
  strip is a quarter of U, heads at the strip's low-U edge);
* ``m_per_v``: metres per atlas unit along V (along the seating row);
* ``texel_aspect`` = m_per_v / m_per_u: how much wider than tall one atlas texel is drawn in the world. The atlas is
  square (256 x 256) so this is the aspect stretch of every person: an atlas person cell keeps its drawn shape when the
  value equals the retail value;
* ``person_m`` = 0.25 * m_per_u: world height of one full person strip (one quarter of U);
* ``shown_fraction``: the share of the strip the triangle's band shows (U span / 0.25; a cropped person < ~0.94).

The retail reference is every retail venue bundle's crowd triangles (the retail disc's own stadium scenes). A quad
is flagged when its texel aspect is more than 15 percent off the retail median, or its person height falls outside the
retail range. Degenerate (zero-area) triangles are counted, never measured. Bands are reported per shape and atlas
strip (quarter); each native strip primitive is one band section between aisles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np

from mod_editor.core import nfl2k5_modern_metlife as ml
from mod_editor.core import nfl2k5_scne_builder as sb

STRIP = 0.25          # one atlas person strip along U
TOLERANCE = 0.15
AREA_EPS = 1e-6       # m^2
LANE = np.dtype([("c", "u1", 4), ("uv", "<i2", 2), ("s", "<i2")])
VENUE_NAMES = {
    "s00": "State Farm", "s01": "Mercedes-Benz", "s02": "M&T Bank", "s03": "Highmark", "s04": "Bank of America",
    "s05": "Soldier Field", "s06": "Paycor", "s07": "AT&T", "s08": "Empower Field", "s09": "Ford Field",
    "s10": "Lambeau", "s11": "Lucas Oil", "s12": "EverBank", "s13": "Arrowhead", "s14": "Hard Rock",
    "s15": "U.S. Bank", "s16": "Gillette", "s17": "Caesars Superdome", "s18": "MetLife (Giants)",
    "s19": "MetLife (Jets)", "s20": "Allegiant", "s21": "Lincoln Financial", "s22": "Acrisure", "s23": "SoFi (Rams)",
    "s24": "SoFi (Chargers)", "s25": "Levi's", "s26": "Lumen", "s27": "Raymond James", "s28": "Nissan",
    "s29": "Northwest", "s30": "Huntington Bank", "s40": "Super Bowl SoFi",
}


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def strip_triangles(mode, ids):
    """(triangle, quad index) pairs; a strip's quad j is its triangles 2j and 2j+1."""
    if mode == sb.TRIANGLE_STRIP:
        for k in range(len(ids) - 2):
            a, b, c = ids[k:k + 3]
            yield ((b, a, c) if k % 2 else (a, b, c)), k // 2
    elif mode == 5:
        for k in range(0, len(ids) - 2, 3):
            yield tuple(ids[k:k + 3]), k // 3
    elif mode == 7:
        for k in range(1, len(ids) - 1):
            yield (ids[0], ids[k], ids[k + 1]), k - 1


def stadium_scene(data):
    chunk = ml.bundle_scenes(data)["stadium"]
    _rec, decoded = ml._scene(data, chunk)
    return sb.parse(decoded, chunk.system_bytes, secondary=True)


def shape_uv(shape):
    n = shape.vertex_count
    P = np.frombuffer(shape.streams[0], "<f4").reshape(n, 3).astype(float) / 100.0
    raw = np.frombuffer(shape.streams[1], dtype=LANE)["uv"].astype(float)
    scale = np.array(struct.unpack_from("<2f", shape.record, 0x30))
    offset = np.array(struct.unpack_from("<2f", shape.record, 0x38))
    return P, raw / 32767.0 * scale + offset


def crowd_geometry_key(sc, *, with_colours=False):
    """Hash of the crowd shapes' positions, UV lanes, UV constants and draw words (``with_colours`` adds the baked
    vertex colours: the retail reference deduplicates exact copies only, as the committed constants were measured)."""
    h = hashlib.sha256()
    for s in sc.shapes:
        subs = [sub for sub in s.submeshes if sc.materials[sub.material].name == "crowd"]
        if not subs:
            continue
        h.update(s.name.encode())
        h.update(bytes(s.record[0x30:0x40]))
        h.update(s.streams[0] or b"")
        if with_colours:
            h.update(s.streams[1] or b"")
        elif s.streams[1] and s.stride(1) == 10:    # UV lanes only: baked vertex colours differ per lighting job
            h.update(np.frombuffer(s.streams[1], dtype=LANE)["uv"].tobytes())
        for sub in subs:
            h.update(sub.words)
    return h.hexdigest()


def measure_scene(sc):
    """Rows of per-triangle measurements and the degenerate counts of one stadium scene's crowd."""
    rows = []
    counts = dict(triangles=0, world_degenerate=0, uv_degenerate=0)
    for si, s in enumerate(sc.shapes):
        subs = [(sj, sub) for sj, sub in enumerate(s.submeshes) if sc.materials[sub.material].name == "crowd"]
        if not subs:
            continue
        if s.stride(0) != 12 or s.stride(1) != 10:
            counts.setdefault("unsupported_shapes", []).append(s.name)
            continue
        P, UV = shape_uv(s)
        for sj, sub in subs:
            for pi, (mode, ids) in enumerate(sb.decode_words(sub.words)):
                for tri, quad in strip_triangles(mode, ids):
                    counts["triangles"] += 1
                    p, t = P[list(tri)], UV[list(tri)]
                    e = np.stack([p[1] - p[0], p[2] - p[0]], 1)
                    area = 0.5 * float(np.linalg.norm(np.cross(e[:, 0], e[:, 1])))
                    if area < AREA_EPS:
                        counts["world_degenerate"] += 1
                        continue
                    T = np.stack([t[1] - t[0], t[2] - t[0]], 1)
                    det = float(np.linalg.det(T))
                    if abs(det) < 1e-12:
                        counts["uv_degenerate"] += 1
                        rows.append(dict(shape=si, name=s.name, submesh=sj, strip=pi, quad=quad, tri=list(map(int, tri)),
                                         area=area, uv_degenerate=True, centroid=p.mean(0).round(3).tolist()))
                        continue
                    J = e @ np.linalg.inv(T)
                    mu, mv = float(np.linalg.norm(J[:, 0])), float(np.linalg.norm(J[:, 1]))
                    cos = float(J[:, 0] @ J[:, 1] / max(mu * mv, 1e-12))
                    umid = float(t[:, 0].mean())
                    rows.append(dict(shape=si, name=s.name, submesh=sj, strip=pi, quad=quad, tri=list(map(int, tri)),
                                     area=area, m_per_u=mu, m_per_v=mv, texel_aspect=mv / mu, person_m=STRIP * mu,
                                     u_up=float(-J[1, 0] / mu), shear_cos=cos, quarter=int(np.floor(umid / STRIP)) % 4,
                                     shown_fraction=float(np.ptp(t[:, 0]) / STRIP),
                                     band_height_m=float(np.ptp(t[:, 0]) * mu),
                                     centroid=p.mean(0).round(3).tolist()))
    return rows, counts


def stats(values, weights=None):
    v = np.asarray(values, float)
    if not len(v):
        return {}
    q = np.percentile(v, [0, 1, 5, 25, 50, 75, 95, 99, 100])
    return dict(n=int(len(v)), min=q[0], p1=q[1], p5=q[2], p25=q[3], median=q[4], p75=q[5], p95=q[6], p99=q[7], max=q[8])


def retail_reference(files, codes):
    rows_all, per_venue, seen = [], {}, {}
    for code in codes:
        path = files / f"{code}dd.iff"
        if not path.exists():
            continue
        try:
            sc = stadium_scene(path.read_bytes())
        except Exception as error:  # noqa: BLE001 - a bundle without a stadium scene is reported, not measured
            per_venue[code] = dict(error=str(error))
            continue
        key = crowd_geometry_key(sc, with_colours=True)
        rows, counts = measure_scene(sc)
        good = [r for r in rows if not r.get("uv_degenerate")]
        if not good:
            per_venue[code] = dict(counts=counts, crowd=False)
            continue
        per_venue[code] = dict(venue=VENUE_NAMES.get(code, code), geometry=key, counts=counts,
                               duplicate_of=seen.get(key),
                               texel_aspect=stats([r["texel_aspect"] for r in good]),
                               person_m=stats([r["person_m"] for r in good]),
                               m_per_v=stats([r["m_per_v"] for r in good]),
                               shown_fraction=stats([r["shown_fraction"] for r in good]))
        if key not in seen:
            seen[key] = code
            rows_all += good
    A = np.array([r["texel_aspect"] for r in rows_all])
    H = np.array([r["person_m"] for r in rows_all])
    venue_medians = [v["texel_aspect"]["median"] for v in per_venue.values() if v.get("texel_aspect") and not v.get("duplicate_of")]
    ref = dict(venues=per_venue, texel_aspect=stats(A), person_m=stats(H),
               texel_aspect_median=float(np.median(A)), person_m_range=[float(H.min()), float(H.max())],
               venue_median_texel_aspect=stats(venue_medians),
               shown_fraction=stats([r["shown_fraction"] for r in rows_all]),
               u_up=stats([r["u_up"] for r in rows_all]))
    return ref


def audit_variant(rows, counts, ref):
    a0 = ref["texel_aspect_median"]
    lo, hi = ref["person_m_range"]
    good = [r for r in rows if not r.get("uv_degenerate")]
    flagged = []
    for r in rows:
        why = []
        if r.get("uv_degenerate"):
            why.append("uv_degenerate")
        else:
            off = r["texel_aspect"] / a0 - 1.0
            r["aspect_off"] = off
            if abs(off) > TOLERANCE:
                why.append("aspect_wide" if off > 0 else "aspect_narrow")
            if r["person_m"] < lo - 1e-9:
                why.append("person_short")
            if r["person_m"] > hi + 1e-9:
                why.append("person_tall")
        if why:
            flagged.append(dict(r, why=why))
    bands = {}
    for r in good:
        bands.setdefault(f"{r['name']}/q{r['quarter']}", []).append(r)
    band_rows = {}
    for k, rs in sorted(bands.items()):
        band_rows[k] = dict(triangles=len(rs), strips=len({(r['submesh'], r['strip']) for r in rs}),
                            texel_aspect=stats([r["texel_aspect"] for r in rs]),
                            person_m=stats([r["person_m"] for r in rs]),
                            band_height_m=stats([r["band_height_m"] for r in rs]),
                            m_per_v=stats([r["m_per_v"] for r in rs]),
                            flagged=sum(1 for f in flagged if f.get('name') == rs[0]['name'] and f.get('quarter') == rs[0]['quarter']))
    quads = {(r["shape"], r["submesh"], r["strip"], r["quad"]) for r in good}
    fquads = {(r["shape"], r["submesh"], r["strip"], r["quad"]) for r in flagged}
    area = sum(r["area"] for r in good)
    farea = sum(r["area"] for r in flagged if not r.get("uv_degenerate"))
    why_counts = {}
    for f in flagged:
        for w in f["why"]:
            why_counts[w] = why_counts.get(w, 0) + 1
    return dict(counts=counts, visible_triangles=len(good), visible_quads=len(quads), flagged_quads=len(fquads),
                flagged_triangles=len(flagged), flagged_area_share=farea / area if area else 0.0, why=why_counts,
                texel_aspect=stats([r["texel_aspect"] for r in good]), person_m=stats([r["person_m"] for r in good]),
                m_per_v=stats([r["m_per_v"] for r in good]), band_height_m=stats([r["band_height_m"] for r in good]),
                shown_fraction=stats([r["shown_fraction"] for r in good]), bands=band_rows, flagged=flagged)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--retail", type=Path, required=True, help="retail venue bundles (sNNdd.iff ...)")
    p.add_argument("--files", type=Path, required=True, help="venue bundles to audit")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--codes", nargs="*", help="audit only these codes (default: every code present)")
    p.add_argument("--label", default="audit")
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    retail_codes = sorted({x.name[:3] for x in a.retail.glob("s??dd.iff")})
    ref_path = a.out / "retail_reference.json"
    if ref_path.exists():
        ref = json.loads(ref_path.read_text())
    else:
        ref = retail_reference(a.retail, retail_codes)
        ref_path.write_text(json.dumps(ref, indent=1) + "\n", newline="\n")
    codes = a.codes or sorted({x.name[:3] for x in a.files.glob("s???*.iff")})
    variants, cache, retail_keys = {}, {}, {}
    for code in codes:
        for path in sorted(a.files.glob(f"{code}??.iff")):
            data = path.read_bytes()
            try:
                sc = stadium_scene(data)
            except Exception as error:  # noqa: BLE001
                variants[path.name] = dict(error=str(error))
                continue
            key = crowd_geometry_key(sc)
            retail_path = a.retail / path.name
            if retail_path.exists() and path.name not in retail_keys:
                try:
                    retail_keys[path.name] = crowd_geometry_key(stadium_scene(retail_path.read_bytes()))
                except Exception:  # noqa: BLE001
                    retail_keys[path.name] = None
            if key not in cache:
                rows, counts = measure_scene(sc)
                cache[key] = audit_variant(rows, counts, ref)
            res = cache[key]
            variants[path.name] = dict(venue=VENUE_NAMES.get(code, code), bundle_sha256=sha(data), crowd_geometry=key,
                                       crowd_geometry_is_retail=key == retail_keys.get(path.name),
                                       visible_quads=res["visible_quads"], flagged_quads=res["flagged_quads"],
                                       flagged_area_share=res["flagged_area_share"], why=res["why"])
            print(path.name, "quads", res["visible_quads"], "flagged", res["flagged_quads"],
                  "aspect med %.3f" % res["texel_aspect"].get("median", float("nan")),
                  "retail" if key == retail_keys.get(path.name) else "MOD", flush=True)
    doc = dict(schema="b77_cr1_crowd_proportion/v1", label=a.label, files=str(a.files), retail=str(a.retail),
               tolerance=TOLERANCE, strip=STRIP,
               retail_texel_aspect_median=ref["texel_aspect_median"], retail_person_m_range=ref["person_m_range"],
               variants=variants, geometries=cache)
    (a.out / f"{a.label}.json").write_text(json.dumps(doc, indent=1, default=float) + "\n", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
