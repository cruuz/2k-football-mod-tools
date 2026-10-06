#!/usr/bin/env python3
"""Measure active crowd-column texture seams without editing game data.

python3 tools/b765/s1_seams.py --input s07dd.iff --output seams.json \
    [--atlas actual_runtime_atlas.png]
python3 tools/b765/s1_seams.py --files DIR --variant dd --exclude-prefix s31 \
    --output day_seams.json

A coincident column is a local UV discontinuity candidate, not proof that it is
visible or defective in gameplay. Native retail crowds can also contain seams.
The optional atlas is supplied evidence; its capture provenance is not inferred.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from mod_editor.core import nfl2k5_scne_builder as sb  # noqa: E402
from tools.b765 import s1_geometry as geometry  # noqa: E402

SCHEMA = "b765_s1_crowd_seams/v1"
METHOD = {
    "position_space": "Native FLOAT3 draw stream /100, in metres; no node transform applied.",
    "active_faces": "Crowd-material triangles with cross-product norm >=1e-7 m²; zero-area connectors excluded.",
    "column_edge": "0.15<abs(delta U)<0.35, abs(delta V)<0.002, vertical extent>1e-4 m.",
    "coincidence": "Both bottom and top coordinates exactly identical on different native shapes.",
    "uv_normalization": "Signed NORMSHORT2: divide negative by32768 and nonnegative by32767, then shape scale/offset.",
    "atlas": "Supplied RGBA image, repeated bilinear UV samples at pixel centres; alpha threshold127.5.",
    "limitation": "No visibility, alpha-sorting, temporal z-fighting, LOD, actual GPU filtering or crowd quality verdict.",
}


def _triangles(mode, ids):
    if mode == sb.TRIANGLE_STRIP:
        for k in range(len(ids) - 2):
            a, b, c = ids[k:k + 3]
            yield (b, a, c) if k % 2 else (a, b, c)
    elif mode == 5:  # Native NV2A TRIANGLES, not glTF primitive mode.
        for k in range(0, len(ids) - 2, 3):
            yield tuple(ids[k:k + 3])
    elif mode == 7:  # Native NV2A TRIANGLE_FAN.
        for k in range(1, len(ids) - 1):
            yield (ids[0], ids[k], ids[k + 1])


def _stats(values):
    if not values:
        return None
    a = np.asarray(values, dtype=float)
    return dict(samples=len(a), minimum=float(a.min()), p05=float(np.percentile(a, 5)),
                median=float(np.median(a)), p95=float(np.percentile(a, 95)), maximum=float(a.max()))


def sample_atlas(atlas, u, v):
    """Repeated, bilinear sampling with texel centres at (i+.5)/dimension."""
    atlas = np.asarray(atlas, dtype=float)
    geometry.require(atlas.ndim == 3 and atlas.shape[2] == 4
                     and min(atlas.shape[:2]) > 0 and np.isfinite(atlas).all(),
                     "atlas must contain finite RGBA pixels")
    u, v = np.broadcast_arrays(np.asarray(u, dtype=float), np.asarray(v, dtype=float))
    height, width = atlas.shape[:2]
    x, y = u * width - .5, v * height - .5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (atlas[y0 % height, x0 % width] * ((1 - fx) * (1 - fy))[..., None]
            + atlas[y0 % height, (x0 + 1) % width] * (fx * (1 - fy))[..., None]
            + atlas[(y0 + 1) % height, x0 % width] * ((1 - fx) * fy)[..., None]
            + atlas[(y0 + 1) % height, (x0 + 1) % width] * (fx * fy)[..., None])


def atlas_disagreement(atlas, a, b, samples=1024):
    t = (np.arange(samples) + .5) / samples
    pixels = []
    for column in (a, b):
        u = column["top_u"] + (column["bottom_u"] - column["top_u"]) * t
        v = column["top_v"] + (column["bottom_v"] - column["top_v"]) * t
        pixels.append(sample_atlas(atlas, u, v))
    A, B = pixels
    aa, ba = A[:, 3] > 127.5, B[:, 3] > 127.5
    both = aa & ba
    return dict(height_samples=samples, alpha_threshold=127.5,
                side_a_opaque_fraction=float(aa.mean()), side_b_opaque_fraction=float(ba.mean()),
                opacity_disagreement_fraction=float(np.mean(aa != ba)),
                both_opaque_fraction=float(both.mean()),
                both_opaque_mean_absolute_rgb_difference=(float(np.mean(abs(A[both, :3] - B[both, :3])))
                                                         if both.any() else None))


def analyze_bundle(data: bytes, name: str, *, atlas=None, phase_threshold=.01):
    """Return original native IDs and exact matching active column endpoints."""
    geometry.require(np.isfinite(phase_threshold) and 0 <= phase_threshold < .5,
                     "phase threshold must be finite and between0 inclusive and0.5 exclusive")
    chunk, _, decoded = geometry.stadium(data)
    scene = sb.parse(decoded, chunk.system_bytes)
    columns, repeats, thin = [], [], []
    selectors, colours = Counter(), Counter()
    used_shapes = set()
    for si, shape in enumerate(scene.shapes):
        if shape.stride(0) != 12 or shape.stride(1) != 10 or not shape.vertex_count:
            continue
        points = np.frombuffer(shape.streams[0], dtype="<f4").reshape(-1, 3).astype(float) / 100
        raw = np.frombuffer(shape.streams[1], dtype=np.dtype([
            ("colour", "u1", 4), ("uv", "<i2", 2), ("selector", "<i2")]))
        packed = raw["uv"].astype(float)
        uv = (packed / np.where(packed < 0, 32768., 32767.)
              * np.array(struct.unpack_from("<2f", shape.record, 0x30))
              + np.array(struct.unpack_from("<2f", shape.record, 0x38)))
        edges, used = defaultdict(list), set()
        for sj, sub in enumerate(shape.submeshes):
            if scene.materials[sub.material].name != "crowd":
                continue
            for mode, ids in sb.decode_words(sub.words):
                for tri in _triangles(mode, ids):
                    cross = np.linalg.norm(np.cross(points[tri[1]] - points[tri[0]],
                                                    points[tri[2]] - points[tri[0]]))
                    if cross < 1e-7:
                        continue
                    used.update(tri)
                    face = dict(submesh=sj, vertices=list(tri), area_m2=float(cross / 2))
                    for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                        edges[tuple(sorted((a, b)))].append(face)
        if not used:
            continue
        used_shapes.add(shape.name)
        for i in sorted(used):
            selectors[int(raw["selector"][i])] += 1
            colours[tuple(int(x) for x in raw["colour"][i])] += 1
        for (a, b), faces in sorted(edges.items()):
            delta = abs(uv[a] - uv[b])
            height = abs(points[a, 1] - points[b, 1])
            distance = np.linalg.norm(points[a] - points[b])
            if delta[0] < .0002 and delta[1] > 1e-5 and distance > 1e-4:
                repeats.append(float(distance / delta[1]))
            if not (.15 < delta[0] < .35 and delta[1] < .002 and height > 1e-4):
                continue
            lo, hi = (a, b) if points[a, 1] < points[b, 1] else (b, a)
            column = dict(shape=si, shape_name=shape.name, vertices_bottom_top=[lo, hi],
                          bottom_m=points[lo].tolist(), top_m=points[hi].tolist(),
                          height_m=float(height), top_u=float(uv[hi, 0]), bottom_u=float(uv[lo, 0]),
                          top_v=float(uv[hi, 1]), bottom_v=float(uv[lo, 1]),
                          active_adjacent_faces=faces)
            columns.append(column)
            if height < .5:
                thin.append(column)
    matching = defaultdict(list)
    for column in columns:
        matching[(tuple(column["bottom_m"]), tuple(column["top_m"]))].append(column)
    pairs = []
    for group in matching.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a["shape"] == b["shape"]:
                    continue
                top_jump = (a["top_v"] - b["top_v"] + .5) % 1 - .5
                bottom_jump = (a["bottom_v"] - b["bottom_v"] + .5) % 1 - .5
                if max(abs(top_jump), abs(bottom_jump)) <= phase_threshold:
                    continue
                pair = dict(a=a, b=b, wrapped_v_phase_jump_top=float(top_jump),
                            wrapped_v_phase_jump_bottom=float(bottom_jump),
                            matching_u_range=(abs(a["top_u"] - b["top_u"]) < 1e-6
                                              and abs(a["bottom_u"] - b["bottom_u"]) < 1e-6))
                if atlas is not None:
                    pair["atlas_at_seam"] = atlas_disagreement(atlas, a, b)
                pairs.append(pair)
    pairs.sort(key=lambda x: (x["a"]["shape"], x["a"]["vertices_bottom_top"],
                              x["b"]["shape"], x["b"]["vertices_bottom_top"]))
    transformed = [n.name for n in scene.nodes if n.shape_name in used_shapes
                   and not np.array_equal(np.frombuffer(n.matrix14, "<f4").reshape(4, 4), np.eye(4))]
    result = dict(name=name, bundle_sha256=geometry.sha(data),
                  phase_threshold=phase_threshold, crowd_column_edges=len(columns),
                  matched_active_column_pairs=len(pairs),
                  pairs_base_y_under_15m=sum(p["a"]["bottom_m"][1] < 15 for p in pairs),
                  pairs_matching_u_range=sum(p["matching_u_range"] for p in pairs),
                  absolute_wrapped_v_phase_repeat=_stats([
                      max(abs(p["wrapped_v_phase_jump_top"]), abs(p["wrapped_v_phase_jump_bottom"]))
                      for p in pairs]),
                  column_height_m=_stats([c["height_m"] for c in columns]),
                  metres_per_v_repeat=_stats(repeats),
                  thin_column_edges_under_0p5m=thin,
                  used_crowd_vertices=sum(selectors.values()),
                  selector_counts=dict(sorted(selectors.items())), unique_bgra_colours=len(colours),
                  nonidentity_crowd_nodes=transformed, pairs=pairs,
                  verdict="Measured local UV seam candidates; gameplay visibility and quality unresolved.")
    if atlas is not None:
        result["alpha_disagreement_fraction"] = _stats([
            p["atlas_at_seam"]["opacity_disagreement_fraction"] for p in pairs])
    return result


def _analyze_path(job):
    path, atlas_path, threshold = job
    atlas = np.asarray(Image.open(atlas_path).convert("RGBA")) if atlas_path else None
    return analyze_bundle(path.read_bytes(), path.name, atlas=atlas, phase_threshold=threshold)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, action="append")
    source.add_argument("--files", type=Path)
    parser.add_argument("--variant", default="dd", choices=[a + b for a in "dan" for b in "drs"])
    parser.add_argument("--exclude-prefix", action="append", default=[])
    parser.add_argument("--atlas", type=Path)
    parser.add_argument("--phase-threshold", type=float, default=.01)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        paths = args.input or sorted(args.files.glob("s[0-9][0-9]" + args.variant + ".iff"))
        paths = [p for p in paths if p.name[:3] not in args.exclude_prefix]
        geometry.require(bool(paths), "no input bundles selected")
        geometry.require(args.workers > 0, "workers must be positive")
        protected = {p.resolve() for p in paths}
        if args.atlas:
            protected.add(args.atlas.resolve())
        geometry.require(args.output.resolve() not in protected, "output must preserve input bundles and atlas")
        jobs = [(p, args.atlas, args.phase_threshold) for p in paths]
        if args.workers == 1:
            results = [_analyze_path(job) for job in jobs]
        else:
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                results = list(pool.map(_analyze_path, jobs))
        atlas_receipt = (dict(path=str(args.atlas.resolve()), sha256=geometry.sha(args.atlas.read_bytes()),
                              provenance="Supplied image; capture provenance must be established separately.")
                         if args.atlas else None)
        report = dict(schema=SCHEMA, method=METHOD, supplied_atlas=atlas_receipt, bundles=results)
        geometry.write_atomic(args.output, geometry.json_bytes(report))
        print(json.dumps(dict(output=str(args.output), bundles=len(results),
                              matched_active_column_pairs=sum(r["matched_active_column_pairs"] for r in results))))
    except (ValueError, OSError, KeyError, IndexError, struct.error) as exc:
        print(f"s1_seams: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
