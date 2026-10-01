"""4x pack images for the Modern MetLife textures, one per bundle variant, and a 2K5 Edition pack manifest.

Noah's rule: the disc carries the real look at retail size (nfl2k5_modern_metlife); a texture pack only adds
resolution. This tool takes the 4x masters the art tool drew (masters.json beside them) and, for each of the
eighteen bundles, applies the same variant treatment the build applies at retail size: the overlays are composited
over the variant's retail turf, the patches are pasted into the variant's retail texture, and the retail dry to
rain or snow look (per-channel affine, plus the snow drifts on the pads) is carried over. Retail pixels outside the
patched rectangles are upscaled only (no new detail exists for them). The manifest names targets, not keys: x2's
`nfl2k5_texture_pack.py build` keys them from the catalog of the disc that will be played.

    python3 tools/nfl2k5_modern_metlife_masters.py SOURCE MASTERS_DIR OUT_DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_metlife as mm  # noqa: E402

S = 4


def up(rgba, scale=S, resample=Image.Resampling.BICUBIC):
    im = Image.fromarray(np.ascontiguousarray(rgba), "RGBA")
    return np.array(im.resize((im.width * scale, im.height * scale), resample), dtype=np.uint8)


def variant_images(bundle_name, data, dry_data, masters):
    """[(scene, chunk index, texture index, descriptor offset, material, 4x RGBA)] for one bundle's authored art."""
    venue, _tod, weather = mm.variant_parts(bundle_name)
    dry = mm.dry_reference(dry_data)
    out = []
    for scene_name, chunk in mm.bundle_scenes(data).items():
        rec, decoded = mm._scene(data, chunk)
        rows = mm.texture_rows(rec)
        descriptors = {int(t["index"]): int(t["descriptor_offset"]) for t in rec["embedded_textures"]}
        done = set()
        for kind in ("patches", "overlays"):
            for item in mm._venue_items(kind, venue, scene_name):
                for material in mm._item_materials(item, rows):
                    row = rows[material]
                    index = int(row["index"])
                    if index in done:
                        continue
                    done.add(index)
                    master_path = masters.get(item["art"])
                    if master_path is None:
                        continue
                    master = np.asarray(Image.open(master_path).convert("RGBA"), dtype=np.uint8)
                    width, height = int(row["width"]), int(row["height"])
                    if master.shape[:2] != (height * S, width * S):
                        master = np.asarray(Image.fromarray(master, "RGBA").resize((width * S, height * S),
                                            Image.Resampling.LANCZOS), dtype=np.uint8)
                    current, _raw = mm.read_p8(decoded, int(rec["system_bytes"]), row)
                    base_dry = (dry.get(scene_name) or {}).get(material, current)
                    dry4 = up(base_dry, resample=Image.Resampling.NEAREST)
                    cur4 = up(current, resample=Image.Resampling.NEAREST)
                    if kind == "overlays":
                        authored = mm.composite_over(up(base_dry), master)
                        result, _fits = mm.weather_transfer(dry4, cur4, authored, snow=False)
                    else:
                        result = up(current)
                        for x0, y0, x1, y1 in item.get("rects") or [[0, 0, width, height]]:
                            region = (y0 * S, y1 * S, x0 * S, x1 * S)
                            piece, _fit = mm.weather_transfer(dry4, cur4, master, region=region,
                                                              snow=weather == "s" and bool(item.get("snow_drift")))
                            result[y0 * S:y1 * S, x0 * S:x1 * S] = piece[y0 * S:y1 * S, x0 * S:x1 * S]
                    out.append((scene_name, int(chunk.index), index, descriptors[index], material, result))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="retail packs folder or disc image (the retail bundles are read from it)")
    parser.add_argument("masters", help="the art tool's --masters folder (masters.json)")
    parser.add_argument("out")
    args = parser.parse_args(argv)
    record = json.loads((Path(args.masters) / "masters.json").read_text())
    masters = {row["art"]: row["master"] for row in record}
    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    entries, seen = [], {}
    with mm._outer_image()(args.source) as archive:
        found = mm.metlife_entries(archive)
        data = {name: archive.read(found[name].virtual_offset, found[name].size) for name in mm.VARIANTS}
        outer = {name: int(found[name].index) for name in mm.VARIANTS}
    for name in mm.VARIANTS:
        for scene_name, chunk, index, descriptor, material, image in variant_images(
                name, data[name], data[mm.dry_name(name)], masters):
            digest = hashlib.sha256(image.tobytes()).hexdigest()[:16]
            path = seen.get(digest)
            if path is None:
                path = out / "images" / f"{name[:5]}_{scene_name}_{material}_{digest}.png"
                Image.fromarray(image, "RGBA").save(path, optimize=True)
                seen[digest] = path
            entries.append(dict(image=path.relative_to(out).as_posix(), group="metlife",
                                target=dict(outer=outer[name], chunk=chunk, descriptor=descriptor),
                                note=f"{name} scene {scene_name}#{index} ({material})"))
    manifest = dict(name="MetLife Stadium 4x (u2)", priority=0,
                    description="Modern MetLife 4x: the disc's MetLife art at four times the size, one image per "
                                "bundle variant. Build it against the catalog of the disc that has Modern MetLife.",
                    entries=entries)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"{len(entries)} targets, {len(seen)} distinct images -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
