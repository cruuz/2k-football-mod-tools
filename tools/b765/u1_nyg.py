#!/usr/bin/env python3
"""Author the reviewed Giants logo mip correction through the Studio writer.

The v0.4 export supplies the protected native pixels. The team recipe selects
only measured logo mip cells; base artwork, other mips and geometry stay exact.
Outputs are private game-derived PNGs, spans and a normal live_helmet project.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import replace
import io
import json
from pathlib import Path
import sys
import tempfile
import zlib

import numpy as np
from PIL import Image, PngImagePlugin

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(Path(__file__).resolve().parent)]
import nfl_live_helmet_txtr_png_import as helmet
from nfl_txtr import HEADER, decode_chunk, parse_chunks
from u1_repair import (apply_spans, publish_batch, require, sha, refuse_links,
                       verify_helmet_pixel_scope, helmet_scope_masks)


def scoped_levels(levels, palette, boxes, selected):
    """Direct premultiplied area coverage, mapped to existing native colours.

    Native P8 blending operates on encoded channel values. Each selected mip
    is filtered directly from mip0, avoiding recursive quantization. Original
    palette colours and deterministic ties retain exact protected RGBA.
    """
    base = np.frombuffer(levels[0].rgba, np.uint8).reshape(256, 256, 4)
    base_mask = np.zeros((256, 256), bool)
    for x0, y0, x1, y1 in boxes:
        base_mask[y0:y1, x0:x1] = True
    pal = np.asarray(palette, dtype=np.int32)
    alpha = base[:, :, 3].astype(float) / 255
    premult = base[:, :, :3].astype(float) * alpha[:, :, None]
    result = []
    protected = []
    for mip in levels:
        scale = 1 << mip.level
        size = 256 // scale
        native = np.frombuffer(mip.rgba, np.uint8).reshape(size, size, 4)
        own = (base_mask.reshape(size, scale, size, scale).any((1, 3))
               if mip.level in selected else np.zeros((size, size), bool))
        out = native.copy()
        if own.any():
            a = alpha.reshape(size, scale, size, scale).mean((1, 3))
            rgb = premult.reshape(size, scale, size, scale, 3).mean((1, 3))
            filtered = np.empty((size, size, 4))
            filtered[:, :, :3] = np.divide(
                rgb, a[:, :, None], out=np.zeros_like(rgb), where=a[:, :, None] > 0)
            filtered[:, :, 3] = a * 255
            values = np.rint(filtered[own]).clip(0, 255).astype(np.int32)
            distances = ((values[:, None, :] - pal[None, :, :]) ** 2).sum(2)
            out[own] = pal[distances.argmin(1)]
        require(np.array_equal(out[~own], native[~own]), "unowned mip artwork changed")
        result.append(helmet.palette_tools.MipLevel(mip.level, size, size, out.tobytes()))
        protected.append(sha(native[~own].tobytes()))
    return result, protected


def authored_png(levels, palette):
    tail = b"".join(m.rgba for m in levels[1:])
    record = {"schema": "nfl2k5_palette_lock/v1", "rgba": sorted(set(palette)),
              "helmet_mips": {"schema": "nfl2k5_helmet_mips/v1",
                              "base_rgba_sha256": sha(levels[0].rgba),
                              "tail_sha256": sha(tail),
                              "tail_zlib": base64.b64encode(zlib.compress(tail, 9)).decode()}}
    info = PngImagePlugin.PngInfo()
    info.add_text("nfl2k5_palette_lock", json.dumps(record, sort_keys=True))
    stream = io.BytesIO()
    Image.frombytes("RGBA", (256, 256), levels[0].rgba).save(
        stream, format="PNG", pnginfo=info)
    return stream.getvalue()


def build(spec_path, baseline_export, out):
    refuse_links(out)
    spec = json.loads(spec_path.read_text())
    require(isinstance(spec, dict) and spec.get("schema") == "nfl2k5_team_2026/v1" and
            spec.get("team") == "NYG" and spec.get("asset_code") == "18",
            "only the reviewed Giants targets are owned")
    recipe = spec.get("live_helmet_mip_refinement")
    require(isinstance(recipe, dict) and recipe.get("schema") == "b765/u1/nyg-logo-mips/v1" and
            recipe.get("family") == "helmet02" and
            recipe.get("filter") == "direct_premultiplied_area_native_palette" and
            recipe.get("mip_levels") == [1] and "base_boxes" in recipe,
            "unreviewed helmet mip recipe")
    boxes, selected = recipe["base_boxes"], recipe["mip_levels"]
    # Validate before any image write, including exact integer box coordinates.
    helmet_scope_masks({"schema": "b765/u1/helmet-pixel-scope/v1", "family": "helmet02",
                        "base_boxes": boxes, "mip_levels": selected,
                        "system_sha256": "0" * 64, "descriptor_sha256": "0" * 64,
                        "protected_rgba_sha256": ["0" * 64] * 6})
    baseline = json.loads(baseline_export.read_text())
    require(isinstance(baseline, dict) and
            baseline.get("schema") == "b765/u1/actual-kit-export/v1" and
            isinstance(baseline.get("sets"), list),
            "invalid baseline export")
    rows = baseline["sets"]
    require(all(isinstance(row, dict) and isinstance(row.get("selector"), str) for row in rows),
            "invalid baseline selectors")
    sets = {s["selector"]: s for s in rows}
    require(len(sets) == len(rows), "duplicate baseline selector")
    prepared = []
    # Pin-check BOTH inputs before staging any artwork or invoking a writer.
    for side in ("H", "A"):
        selector = "18" + side + "0"
        require(selector in sets, "missing Giants baseline selector")
        row = sets[selector]
        require(isinstance(row.get("resource_path"), str) and
                isinstance(row.get("resource_sha256"), str), "invalid baseline resource pin")
        path = refuse_links(Path(row["resource_path"]))
        require(path.is_file(), "missing baseline resource")
        raw = path.read_bytes()
        require(sha(raw) == row["resource_sha256"], "baseline resource pin changed")
        chunks = [c for c in parse_chunks(raw) if c.index == 12]
        require(len(chunks) == 1, "missing helmet02 stored span")
        native, _ = decode_chunk(raw, chunks[0])
        prepared.append((side, selector, raw, chunks[0], native))
    manifest = {"schema": "b765/u1/texture-repair/v1", "resources": {}}
    project = {"schema": "nfl2k5_visual_mod_project/v1", "edits": [],
               "purpose": "Giants shell-C logo mip refinement; protected native pixels"}
    receipt = {"schema": "b765/u1/nyg-logo-mips-receipt/v1", "recipe": recipe,
               "spec_sha256": sha(spec_path.read_bytes()), "resources": {},
               "geometry_edited": False, "runtime_visibility_proved": False}
    items = {}
    # All compiler, scope and repeat checks finish before one exclusive publish.
    with tempfile.TemporaryDirectory(prefix="u1-nyg-") as temporary:
        stage = Path(temporary)
        for side, selector, raw, chunk, native in prepared:
            levels = helmet.decode_levels(native)
            palette = helmet.parse_palette(native[128:])
            art, protected = scoped_levels(levels, palette, boxes, selected)
            scope = {"schema": "b765/u1/helmet-pixel-scope/v1", "family": "helmet02",
                     "base_boxes": boxes, "mip_levels": selected,
                     "system_sha256": sha(native[:128]),
                     "descriptor_sha256": sha(native[52:76]),
                     "protected_rgba_sha256": protected}
            png = out / "art" / (selector + "_helmet02.png")
            png_data = authored_png(art, palette)
            staged_png = stage / png.name
            staged_png.write_bytes(png_data)
            span, previews, compiler = helmet.build_import(
                helmet.DEFAULT_INDEX, helmet.DEFAULT_REPORT, "18", side, 0, "helmet02", staged_png)
            compiler["delivered_png"] = {"path": str(png.resolve()), "sha256": sha(png_data),
                                          "identical_to_staged_compiler_input": True}
            # The delivered copy has the independently checked compiler input
            # bytes. Use its stable locator so a repeated build is idempotent.
            compiler["input_png"].update(path=str(png.resolve()), staging_used=True)
            decoded, _ = decode_chunk(span, replace(chunk, offset=0,
                              overlap_scratch_bytes=HEADER.unpack_from(span)[5]))
            require(helmet.decode_levels(decoded) == art, "Studio writer changed authored pixels")
            original_span = raw[chunk.offset:chunk.end_offset]
            pixel_receipt = verify_helmet_pixel_scope(original_span, span, scope)
            patch = {"offset": chunk.offset, "length": len(span),
                     "before_sha256": sha(original_span), "after_sha256": sha(span),
                     "replacement": sha(span) + ".span", "helmet_pixel_scope": scope}
            (stage / patch["replacement"]).write_bytes(span)
            manifest["resources"][selector + ".IFF"] = [patch]
            repaired, resource_receipt = apply_spans(raw, [patch], stage)
            repeated, repeat_receipt = apply_spans(repaired, [patch], stage)
            require(repeated == repaired and all(s["already_applied"] for s in repeat_receipt["spans"]),
                    "repair is not idempotent")
            receipt["resources"][selector] = dict(resource_receipt, pixel_scope=pixel_receipt,
                                                 idempotent=True)
            project["edits"].append({"kind": "live_helmet", "asset_code": "18", "side": side,
                                    "variant": 0, "family": "helmet02", "png": str(png.resolve())})
            items.update([(png, png_data), (out / "payload" / patch["replacement"], span),
                          (out / "resources" / (selector + ".IFF"), repaired),
                           (out / "compiler" / (selector + ".json"),
                            (json.dumps(compiler, indent=2) + "\n").encode())] +
                          [(out / "previews" / selector / name, data) for name, data in previews])
    items.update([(out / "payload/native_manifest.json", (json.dumps(manifest, indent=2) + "\n").encode()),
                   (out / "correction_project.json", (json.dumps(project, indent=2, sort_keys=True) + "\n").encode()),
                   (out / "receipt.json", (json.dumps(receipt, indent=2) + "\n").encode())])
    publish_batch(list(items.items()))
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", type=Path, default=ROOT / "data/nfl2k5_teams_2026/NYG.json")
    p.add_argument("--baseline-export", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = build(a.spec, a.baseline_export, a.out)
    print(f"NYG: {len(result['resources'])} native resources; fixed spans and protected mip pixels exact")
