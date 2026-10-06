#!/usr/bin/env python3
"""Read-only field-art census, native P8 mip dumps and labelled offline previews.

No game/art bytes ship in this tool. ``extract`` reads only home-venue bundles
from a supplied XISO/loose archive. ``audit`` accepts sparse repaired bundles:
an absent after bundle explicitly inherits the original, and is recorded as
such. The images are UV previews, not emulator captures or gameplay witnesses.

Example:
  python tools/b765/s2_audit.py extract --disc DISC --out SCRATCH/native_before
  python tools/b765/s2_audit.py audit --before SCRATCH/native_before \
      --after SCRATCH/native_after --art-root ART_ROOT --out SCRATCH/audit
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEAM_PREFIXES = dict(zip(
    ("ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "DAL", "DEN", "DET",
     "GB", "IND", "JAX", "KC", "MIA", "MIN", "NE", "NO", "NYG", "NYJ",
     "LV", "PHI", "PIT", "LAR", "LAC", "SF", "SEA", "TB", "TEN", "WAS", "CLE", "HOU"),
    tuple(f"s{i:02}" for i in range(31)) + ("s37",)))
CODES = tuple(t + w for t in "dan" for w in "drs")
PREVIEW_NOTE = "OFFLINE native UV preview; lighting/detail shaders omitted; no gameplay witness"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def selected_teams(value):
    teams = list(TEAM_PREFIXES) if value == "all" else value.upper().split(",")
    unknown = set(teams) - TEAM_PREFIXES.keys()
    if unknown or len(set(teams)) != len(teams):
        raise ValueError(f"unknown or repeated teams: {value}")
    return teams


def extract(disc, out, teams, codes=CODES):
    """Extract selected native bundles, refusing an existing different file."""
    from mod_editor.core import nfl2k5_modern_metlife as mm
    out.mkdir(parents=True, exist_ok=True)
    wanted = {mm.name_id(f"{TEAM_PREFIXES[t]}{c}.iff"): (t, c) for t in teams for c in codes}
    rows = []
    with mm._outer_image()(disc) as archive:
        found = {e.name_id: e for e in archive.entries if e.name_id in wanted}
        if set(found) != set(wanted):
            raise ValueError("some requested native bundles are missing")
        for ident, (team, code) in wanted.items():
            entry = found[ident]
            name = f"{TEAM_PREFIXES[team]}{code}.iff"
            data = archive.read(entry.virtual_offset, entry.size)
            target = out / name
            if target.exists() and target.read_bytes() != data:
                raise ValueError(f"refusing different existing extraction: {target}")
            if not target.exists():
                target.write_bytes(data)
            rows.append(dict(team=team, name=name, name_id=ident, outer=entry.index,
                             virtual_offset=entry.virtual_offset, size=entry.size, sha256=sha(data)))
    write_json(out / "extraction.json", dict(schema="b765_s2_extraction/v1", source=str(disc),
                                           read_only_source=True, bundles=rows))
    return rows


def read_mips(decoded, system, row):
    """Decode the actual native mip chain, not mips regenerated from level zero."""
    import numpy as np
    from mod_editor.core import nfl2k5_modern_metlife as mm
    tx, _inv, _rr, _header, stw = mm._tools()
    dims = stw._mip_dimensions(int(row["width"]), int(row["height"]), int(row["mip_levels"]))
    at = system + int(row["pixel_offset"])
    pal_at = system + int(row["palette_offset"])
    if at + sum(w * h for w, h in dims) != pal_at or pal_at + 1024 > len(decoded):
        raise ValueError("P8 mip/palette allocation mismatch")
    palette_raw = bytes(decoded[pal_at:pal_at + 1024])
    palette = np.frombuffer(palette_raw, dtype=np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]]
    levels, used = [], []
    for w, h in dims:
        raw = bytes(decoded[at:at + w * h])
        at += w * h
        indices = np.frombuffer(tx.unswizzle_2d(raw, w, h, 1), dtype=np.uint8).reshape(h, w)
        levels.append(palette[indices].copy())
        used.append(int(len(np.unique(indices))))
    return levels, used, palette_raw


def texture_stats(levels, used, palette_raw):
    import numpy as np
    from mod_editor.core import nfl2k5_modern_venues_2026 as mv
    first = levels[0]
    alpha = first[..., 3]
    opaque = alpha >= 240
    bbox = None
    if (alpha >= 128).any():
        y, x = np.where(alpha >= 128)
        bbox = [int(x.min()), int(y.min()), int(x.max()) + 1, int(y.max()) + 1]
    out = dict(rgba_sha256=sha(first.tobytes()), palette_sha256=sha(palette_raw),
               opaque_fraction=round(float(opaque.mean()), 6),
               transparent_fraction=round(float((alpha == 0).mean()), 6),
               alpha_edge_fraction=round(float(((alpha > 0) & (alpha < 255)).mean()), 6),
               visible_bbox_px=bbox, mip_chain=[])
    for level, (rgba, colours) in enumerate(zip(levels, used)):
        r = dict(level=level, size=[rgba.shape[1], rgba.shape[0]], rgba_sha256=sha(rgba.tobytes()),
                 used_palette_indices=colours)
        if level:
            # This diagnoses fringe risk, not visual correctness. The existing
            # writer may average straight RGB while correct filtering uses alpha.
            expected = mv.resample(levels[level - 1], rgba.shape[1], rgba.shape[0])
            a = rgba.astype(np.float64) / 255
            b = expected.astype(np.float64) / 255
            ap = np.concatenate([a[..., :3] * a[..., 3:4], a[..., 3:4]], axis=-1)
            bp = np.concatenate([b[..., :3] * b[..., 3:4], b[..., 3:4]], axis=-1)
            r["premultiplied_box_rmse_255"] = round(float(np.sqrt(((ap - bp) ** 2).mean()) * 255), 4)
        out["mip_chain"].append(r)
    return out


def safe_key(names, index):
    return re.sub(r"[^A-Za-z0-9_.+-]", "_", "+".join(names) or f"t{index}")[:110]


def triangle_indices(gltf_mode, indices):
    """Expand native strip/fan topology; ignore degenerate strip joins."""
    if gltf_mode == 5:
        triangles = []
        for n in range(len(indices) - 2):
            tri = indices[n:n + 3]
            if len(set(tri)) == 3:
                triangles.extend(tri if n % 2 == 0 else (tri[1], tri[0], tri[2]))
        return triangles
    if gltf_mode == 6:
        return [v for n in range(1, len(indices) - 1)
                for v in (indices[0], indices[n], indices[n + 1])]
    return indices if gltf_mode == 4 else []


def field_draws(rec, decoded):
    """Native submesh placement from real command indices and shape UV lanes."""
    import numpy as np
    from mod_editor.core import nfl2k5_models as models
    gltf = models._tools_module("nfl_scne_gltf")
    shapes = {}
    for shape in rec["shapes"]:
        lanes = models._shape_lanes(rec, shape, decoded)
        if lanes.position_format not in ("FLOAT3", "NORMSHORT3") or lanes.texcoord is None:
            continue
        positions = np.asarray(models.read_positions(decoded, shape, lanes), dtype=np.float64)
        pairs = models.read_lane_2h(decoded, shape, lanes.texcoord, lanes.vertex_count)
        uvs = np.asarray([models.uv_to_gltf(u, v, lanes.uv_scale, lanes.uv_offset) for u, v in pairs])
        shapes[int(shape["index"])] = (positions, uvs)
    draws = []
    for sub in rec["submeshes"]:
        if int(sub["shape_index"]) not in shapes:
            continue
        batches = gltf.decode_batches(decoded, int(sub["command_offset"]), int(sub["primary_command_word_count"]))
        pos, uv = shapes[int(sub["shape_index"])]
        for mode, idx in batches:
            gltf_mode, indices, _conversion = gltf.gltf_topology(mode, idx)
            indices = triangle_indices(gltf_mode, indices)
            if not indices:
                continue
            inds = np.asarray(indices, dtype=np.int32)
            p = pos[inds]
            bounds = [[round(float(v), 4) for v in p.min(axis=0)],
                      [round(float(v), 4) for v in p.max(axis=0)]]
            draws.append(dict(material=sub["material_name"], shape=sub["shape_name"],
                              bounds_cm=bounds, triangle_count=len(indices) // 3,
                              positions=pos, uvs=uv, indices=inds))
    return draws


def draw_triangle(canvas, points, uvs, texture, repeat=False):
    import numpy as np
    h, w = canvas.shape[:2]
    x0 = max(0, int(np.floor(points[:, 0].min())))
    y0 = max(0, int(np.floor(points[:, 1].min())))
    x1 = min(w, int(np.ceil(points[:, 0].max())) + 1)
    y1 = min(h, int(np.ceil(points[:, 1].max())) + 1)
    if x1 <= x0 or y1 <= y0:
        return
    p0, p1, p2 = points
    den = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
    if abs(den) < 1e-9:
        return
    xx, yy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
    a = ((p1[1] - p2[1]) * (xx - p2[0]) + (p2[0] - p1[0]) * (yy - p2[1])) / den
    b = ((p2[1] - p0[1]) * (xx - p2[0]) + (p0[0] - p2[0]) * (yy - p2[1])) / den
    c = 1 - a - b
    mask = (a >= -1e-6) & (b >= -1e-6) & (c >= -1e-6)
    uv = a[..., None] * uvs[0] + b[..., None] * uvs[1] + c[..., None] * uvs[2]
    uv = uv % 1 if repeat else np.clip(uv, 0, 1)
    th, tw = texture.shape[:2]
    tx = np.clip(uv[..., 0] * tw - 0.5, 0, tw - 1)
    ty = np.clip(uv[..., 1] * th - 0.5, 0, th - 1)
    ix, iy = tx.astype(int), ty.astype(int)
    fx, fy = (tx - ix)[..., None], (ty - iy)[..., None]
    jx, jy = np.minimum(ix + 1, tw - 1), np.minimum(iy + 1, th - 1)
    # Filter premultiplied colours so the preview doesn't invent dark alpha edges.
    f = texture.astype(float) / 255
    pre = np.concatenate((f[..., :3] * f[..., 3:4], f[..., 3:4]), axis=-1)
    sample = ((pre[iy, ix] * (1 - fx) + pre[iy, jx] * fx) * (1 - fy)
              + (pre[jy, ix] * (1 - fx) + pre[jy, jx] * fx) * fy)
    dest = canvas[y0:y1, x0:x1]
    alpha = sample[..., 3:4]
    rgb = np.clip(sample[..., :3] * 255 + dest[..., :3] * (1 - alpha), 0, 255)
    dest[..., :3][mask] = rgb[mask]


def field_preview(draws, textures, size=(880, 400)):
    import numpy as np
    from PIL import Image
    width, height = size
    canvas = np.zeros((height, width, 4), dtype=np.uint8)
    canvas[...] = (53, 90, 44, 255)
    # All native fields use game centimetres. Projection is identical for teams;
    # scene shader activation for event badges isn't reproduced, so omit those.
    priority = lambda d: (0 if "premipped" in d["material"] else
                          1 if "endzone" in d["material"] else 2)
    for d in sorted(draws, key=priority):
        name = d["material"]
        if not (name.startswith("endzone_") or name in ("center_logo", "numbers", "color_premipped")):
            continue
        if name not in textures:
            continue
        pos, uv, indices = d["positions"], d["uvs"], d["indices"]
        points = np.column_stack(((pos[:, 2] + 5540) / 11080 * width,
                                  (2530 - pos[:, 0]) / 5060 * height))
        for i in range(0, len(indices), 3):
            idx = indices[i:i + 3]
            draw_triangle(canvas, points[idx], uv[idx], textures[name], name == "color_premipped")
    return Image.fromarray(canvas, "RGBA")


def analyse_bundle(data, dump, *, stadium=True):
    from PIL import Image
    from mod_editor.core import nfl2k5_modern_venues_2026 as mv
    mm = mv._mm()
    scenes = mm.bundle_scenes(data)
    out, images, draws = {}, {}, []
    for scene in ("field", "stadium") if stadium else ("field",):
        if scene not in scenes:
            continue
        rec, decoded = mm._scene(data, scenes[scene])
        rows = []
        for index, row in mv.p8_rows(rec).items():
            names = list(row.get("mapped_material_names") or [])
            levels, used, raw = read_mips(decoded, int(rec["system_bytes"]), row)
            item = dict(index=index, materials=names, format="P8", size=[int(row["width"]), int(row["height"])],
                        mip_levels=int(row["mip_levels"]), **texture_stats(levels, used, raw))
            if dump is not None:
                directory = dump / scene
                directory.mkdir(parents=True, exist_ok=True)
                for level, rgba in enumerate(levels):
                    filename = directory / f"t{index:02}_{safe_key(names, index)}_mip{level}.png"
                    Image.fromarray(rgba, "RGBA").save(filename)
                item["base_image"] = str(directory / f"t{index:02}_{safe_key(names, index)}_mip0.png")
            rows.append(item)
            if scene == "field":
                for name in names:
                    images[name] = levels[0]
        out[scene] = dict(textures=rows, scene_sha256=sha(decoded),
                          scene_span_sha256=sha(mm.scene_span(data, scenes[scene])))
        if scene == "field":
            draws = field_draws(rec, decoded)
            out[scene]["placement"] = [{k: v for k, v in d.items() if k not in ("positions", "uvs", "indices")}
                                        for d in draws]
            out[scene]["has_midfield_material"] = "center_logo" in images
            out[scene]["has_midfield_draw"] = any(d["material"] == "center_logo" for d in draws)
    return out, images, draws


def source_manifest(art_root, team):
    if art_root is None:
        return None
    path = art_root / team / "venue" / "manifest.json"
    if not path.exists():
        return dict(path=str(path), exists=False)
    doc = json.loads(path.read_text(encoding="utf-8"))
    return dict(path=str(path), exists=True, sha256=sha(path.read_bytes()), colours=doc.get("colours"),
                notes=doc.get("notes"), sources=doc.get("sources"),
                field_items=[i for i in doc.get("items", []) if i.get("scene") == "field"])


def audit_team(task):
    team, prefix, before, after, art_root, out, variants, reviews = task
    from PIL import Image, ImageDraw
    dest = out / team
    dest.mkdir(parents=True, exist_ok=True)
    codes = [c for c in CODES if (before / f"{prefix}{c}.iff").exists()]
    if "dd" not in codes:
        raise ValueError(f"{team}: dry-day native bundle missing")
    bundles, data_by_phase = [], {}
    for code in codes:
        name = f"{prefix}{code}.iff"
        bpath = before / name
        apath = after / name if after is not None else None
        changed = apath is not None and apath.exists()
        b = bpath.read_bytes()
        a = apath.read_bytes() if changed else b
        bundles.append(dict(name=name, before_sha256=sha(b), after_sha256=sha(a), size_before=len(b), size_after=len(a),
                            byte_identical=b == a, after_source=str(apath) if changed else str(bpath),
                            after_uses_original=not changed))
        if code == "dd":
            data_by_phase = dict(before=b, after=a)
    phases = {}
    for phase, data in data_by_phase.items():
        if phase == "after" and data == data_by_phase["before"]:
            phases[phase] = phases["before"].copy()
            preview = Image.open(dest / "before.png").copy()
        else:
            info, images, draws = analyse_bundle(data, dest / "native_textures" / phase)
            phases[phase] = info
            preview = field_preview(draws, images)
        # Save a full-labelled preview so isolated screenshots retain context.
        image = Image.new("RGB", (preview.width, preview.height + 44), "#151b22")
        image.paste(preview.convert("RGB"), (0, 44))
        draw = ImageDraw.Draw(image)
        draw.text((8, 5), f"{team} / {prefix} / {phase.upper()} / dry day", fill="white")
        draw.text((8, 22), PREVIEW_NOTE, fill="#c6cbd2")
        # The unchanged reuse already contains the label; keep identical field pixels.
        if phase == "after" and data == data_by_phase["before"]:
            image = preview
            ImageDraw.Draw(image).rectangle((0, 0, image.width, 44), fill="#151b22")
            ImageDraw.Draw(image).text((8, 5), f"{team} / {prefix} / AFTER / native bytes unchanged", fill="white")
            ImageDraw.Draw(image).text((8, 22), PREVIEW_NOTE, fill="#c6cbd2")
        image.save(dest / f"{phase}.png")
    variant_info, after_variant_info = {}, {}
    if variants:
        for code in codes:
            if code == "dd":
                continue
            path = before / f"{prefix}{code}.iff"
            info, _images, _draws = analyse_bundle(path.read_bytes(), None, stadium=False)
            variant_info[code] = info["field"]
            apath = after / path.name if after is not None else None
            if apath is not None and apath.exists() and apath.read_bytes() != path.read_bytes():
                info, _images, _draws = analyse_bundle(apath.read_bytes(), None, stadium=False)
                after_variant_info[code] = info["field"]
            else:
                after_variant_info[code] = variant_info[code]
    field = phases["before"]["field"]
    issues = []
    if not field["has_midfield_draw"]:
        issues.append(dict(kind="midfield_not_drawn", evidence="native field has no center_logo submesh",
                           status=("fixed in after dry-day field; consult variant/native repair receipts"
                                   if phases["after"]["field"]["has_midfield_draw"] else
                                   "requires scoped field-logo geometry and source writer review")))
    for t in field["textures"]:
        if "center_logo" in t["materials"]:
            bb = t["visible_bbox_px"]
            if bb and (bb[0] == 0 or bb[1] == 0 or bb[2] == t["size"][0] or bb[3] == t["size"][1]):
                issues.append(dict(kind="midfield_alpha_at_texture_boundary", materials=t["materials"],
                                   status="inspect clipping/registration in gameplay; may be intentional"))
            errors = [m.get("premultiplied_box_rmse_255", 0) for m in t["mip_chain"]]
            if max(errors, default=0) > 5:
                issues.append(dict(kind="mip_filter_difference", materials=t["materials"],
                                   max_premultiplied_rmse=max(errors), status="offline minification review required"))
    document = dict(schema="b765_s2_field_art_audit/v1", team=team, venue_prefix=prefix,
                    evidence="offline native decode and UV projection", gameplay_witness=False,
                    before_image=str(dest / "before.png"), after_image=str(dest / "after.png"),
                    after_status="changed" if any(not r["byte_identical"] for r in bundles) else "unchanged",
                    visual_review="pending manual offline image review; byte identity alone is not a visual pass",
                    issues=issues, source_art=source_manifest(art_root, team), bundles=bundles,
                    dry_day=phases, before_variant_fields=variant_info, after_variant_fields=after_variant_info,
                    limitations=["2026 placement/colours require dated reference imagery",
                                 "UV projection omits lighting, detail shaders and runtime activation masks",
                                 "Mip error is a diagnostic, not a quality verdict"])
    if team in reviews:
        review = reviews[team]
        document["manual_offline_review"] = review
        document["visual_review"] = review.get("disposition", "reviewed offline")
        document["issues"].extend(review.get("issues", []))
    write_json(dest / "field_art_audit.json", document)
    return dict(team=team, venue_prefix=prefix, audit=str(dest / "field_art_audit.json"),
                changed=document["after_status"] == "changed", issues=issues)


def contact_sheet(out, rows):
    from PIL import Image, ImageDraw
    cell_w, cell_h = 448, 490
    sheet = Image.new("RGB", (cell_w * 4, cell_h * 8 + 70), "#111820")
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 10), "32 home fields: native BEFORE / AFTER", fill="white")
    draw.text((12, 28), PREVIEW_NOTE, fill="#c6cbd2")
    draw.text((12, 46), "Untouched after panels inherit original native bundles; see per-team JSON for exact scope.", fill="#c6cbd2")
    for i, row in enumerate(rows):
        x, y = (i % 4) * cell_w, (i // 4) * cell_h + 70
        for phase, dy in (("before", 0), ("after", 232)):
            with Image.open(out / row["team"] / f"{phase}.png") as src:
                im = src.copy()
            im.thumbnail((cell_w - 12, 228), Image.Resampling.LANCZOS)
            sheet.paste(im, (x + 6, y + dy))
        status = "CHANGED" if row["changed"] else "UNCHANGED"
        draw.text((x + 8, y + 466), f"{row['team']} {status}; native placement / palette / mips in JSON", fill="#e2e6ea")
    path = out / "all32_before_after_contact_sheet.png"
    sheet.save(path)
    # Smaller separate halves remain easy to inspect without losing all32 coverage.
    for start, name in ((0, "teams_01_16"), (16, "teams_17_32")):
        part = Image.new("RGB", (cell_w * 4, cell_h * 4 + 70), "#111820")
        part.paste(sheet.crop((0, 0, cell_w * 4, 70)), (0, 0))
        part.paste(sheet.crop((0, 70 + start // 4 * cell_h, cell_w * 4, 70 + (start // 4 + 4) * cell_h)), (0, 70))
        part.save(out / f"{name}_contact_sheet.png")
    return path


def write_summary(out, rows, path):
    bundles = []
    for row in rows:
        document = json.loads(Path(row["audit"]).read_text(encoding="utf-8"))
        bundles.extend(document["bundles"])
    write_json(out / "field_art_audit.json", dict(schema="b765_s2_all_fields/v1", teams=rows,
               contact_sheet=str(path) if path else None, gameplay_witness=False,
               scope=dict(total_bundles=len(bundles),
                          changed_bundles=[r["name"] for r in bundles if not r["byte_identical"]],
                          unchanged_bundles=sum(r["byte_identical"] for r in bundles))))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    e = subs.add_parser("extract")
    e.add_argument("--disc", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--teams", default="all")
    e.add_argument("--dry-day-only", action="store_true")
    a = subs.add_parser("audit")
    a.add_argument("--before", type=Path, required=True)
    a.add_argument("--after", type=Path)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--art-root", type=Path)
    a.add_argument("--teams", default="all")
    a.add_argument("--variants", action="store_true", help="decode all extracted variant fields as well")
    a.add_argument("--review-json", type=Path, help="manual offline review dispositions keyed by team")
    a.add_argument("--workers", type=int, default=4)
    s = subs.add_parser("sheet", help="refresh the all32 sheet after rerunning selected team audits")
    s.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "sheet":
        rows = []
        for team, prefix in TEAM_PREFIXES.items():
            file = args.out / team / "field_art_audit.json"
            doc = json.loads(file.read_text(encoding="utf-8"))
            if doc.get("team") != team or doc.get("venue_prefix") != prefix:
                raise ValueError(f"wrong team identity in {file}")
            rows.append(dict(team=team, venue_prefix=prefix, audit=str(file),
                             changed=doc["after_status"] == "changed", issues=doc["issues"]))
        path = contact_sheet(args.out, rows)
        write_summary(args.out, rows, path)
        print(json.dumps(dict(teams=len(rows), contact_sheet=str(path), out=str(args.out))))
        return 0
    teams = selected_teams(args.teams)
    if args.command == "extract":
        rows = extract(args.disc, args.out, teams, ("dd",) if args.dry_day_only else CODES)
        print(json.dumps(dict(bundles=len(rows), bytes=sum(r["size"] for r in rows), out=str(args.out))))
        return 0
    args.out.mkdir(parents=True, exist_ok=True)
    reviews = json.loads(args.review_json.read_text(encoding="utf-8")) if args.review_json else {}
    if set(reviews) - set(TEAM_PREFIXES):
        raise ValueError("review file contains unknown teams")
    if args.after is not None:
        expected = {f"{TEAM_PREFIXES[t]}{c}.iff" for t in teams for c in CODES}
        unexpected = {p.name for p in args.after.glob("*.iff")} - expected
        if unexpected:
            raise ValueError(f"after directory contains out-of-scope bundles: {sorted(unexpected)}")
    tasks = [(t, TEAM_PREFIXES[t], args.before, args.after, args.art_root, args.out, args.variants, reviews) for t in teams]
    with ProcessPoolExecutor(max_workers=max(1, min(args.workers, 12))) as pool:
        rows = list(pool.map(audit_team, tasks))
    path = contact_sheet(args.out, rows) if len(rows) == 32 else None
    write_summary(args.out, rows, path)
    print(json.dumps(dict(teams=len(rows), contact_sheet=str(path), out=str(args.out))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
