#!/usr/bin/env python3
"""Measure the real broadcast, compare installed native inputs, retain every trial.

No emulator, display or disc copy. GPU blend/filter/cull remain software models.
All pack reads are bounded and the existing static/native-runtime writers own
compilation. Scores never substitute the reference pixels into a generated bar.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import nfl2k5_scorebug_projection as projection
from mod_editor.core import nfl2k5_scorebug_exact as exact
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_scorebug_resources as art
from mod_editor.core import nfl2k5_scorebug_fonts as scoped

REFERENCE = ROOT / "docs/scorebug_ingame/reference_LV_HOU_broadcast.jpeg"
TEXT_ROIS = {
    "0xfc070": (720, 955, 790, 1026), "0xfc050": (1125, 955, 1195, 1026),
    "0xfc7d0": (888, 951, 1031, 982), "0xfc090": (850, 1004, 902, 1036),
    "0xfc150": (906, 1000, 1015, 1037), "0xfbe30": (1024, 1004, 1067, 1035),
}


def write_json(path, value):
    # Readers and Git may inspect a long-running loop's evidence between trials.
    # Publish a complete snapshot instead of truncating their mapped input.
    import os
    import tempfile
    path = Path(path).resolve()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                dir=path.parent, prefix="." + path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def reference():
    from PIL import Image
    if scene.digest(REFERENCE.read_bytes()) != exact.REFERENCE_SHA256:
        raise ValueError("broadcast reference identity changed")
    with Image.open(REFERENCE) as opened:
        source = opened.convert("RGB")
    if source.size != (1920, 1080):
        raise ValueError("unexpected broadcast dimensions")
    result = Image.new("RGB", (640, 480), "black")
    result.paste(source.resize((640, 448), Image.Resampling.LANCZOS), (0, 16))
    return source, result


def box_of(points):
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def wide_reference(target):
    """Apply widescreen v3's 27/32 contraction about x=320 to the comparison."""
    from PIL import Image
    out = Image.new("RGB", target.size, "black")
    out.paste(target.resize((540, 480), Image.Resampling.LANCZOS), (50, 0))
    return out


def reference_text_boxes(source):
    from collections import deque
    import numpy as np
    pixels = np.asarray(source)
    result = {}
    for callback, (a, b, c, d) in TEXT_ROIS.items():
        roi = pixels[b:d, a:c].astype(float)
        hit = roi.min(axis=2) > 190 if callback in ("0xfc070", "0xfc050", "0xfc7d0") else roi.max(axis=2) < 100
        # Border fragments are not glyphs. In the quarter ROI a five-pixel
        # capsule-rim component touches the lower/left ROI edge; including it
        # falsely measured 12.7x10.8 instead of the actual 9.0x7.05 text.
        seen = np.zeros_like(hit)
        ink = []
        for y, x in np.argwhere(hit):
            if seen[y, x]:
                continue
            queue, component = deque([(int(y), int(x))]), []
            seen[y, x] = True
            while queue:
                yy, xx = queue.popleft()
                component.append((yy, xx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = yy+dy, xx+dx
                        if 0 <= ny < hit.shape[0] and 0 <= nx < hit.shape[1] and hit[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            queue.append((ny, nx))
            if len(component) >= 3 and not any(y in (0, hit.shape[0]-1) or x in (0, hit.shape[1]-1) for y,x in component):
                ink.extend(component)
        if not ink:
            raise ValueError("no reference text in " + callback)
        ys, xs = zip(*ink)
        result[callback] = list(exact.hud_box((a + min(xs), b + min(ys), a + max(xs) + 1, b + max(ys) + 1)))
    return result


def edge_distance(first, second, mask=None):
    """Symmetric nearest-edge distance; bounded chunks, no quadratic big image."""
    import numpy as np
    def points(rgb):
        gray = rgb.astype(float).mean(axis=2)
        gy, gx = np.gradient(gray)
        hit = np.hypot(gx, gy) > 24
        if mask is not None:
            hit &= mask
        return np.argwhere(hit)
    a, b = points(first), points(second)
    if not len(a) or not len(b):
        return None
    def distances(a, b):
        values = []
        for start in range(0, len(a), 64):
            delta = a[start:start + 64, None, :] - b[None, :, :]
            values.extend(np.sqrt((delta * delta).sum(axis=2).min(axis=1)).tolist())
        return values
    values = distances(a, b) + distances(b, a)
    return dict(mean_px=float(np.mean(values)), p95_px=float(np.percentile(values, 95)),
                max_px=max(values), reference_edges=len(a), rendered_edges=len(b))


def rendered_text_ink(pixels, callback, widescreen=False):
    """Separate threshold diagnostic; this does not replace native quad metrics.

    The photographed ROIs are mapped into the HUD raster. Components touching
    their edge include clock-rim fragments and the home possession marker.
    One HUD pixel already covers more than the source's three-pixel speck limit.
    """
    import numpy as np
    box = list(exact.hud_box(TEXT_ROIS[callback]))
    if widescreen:
        for i in (0,2): box[i] = 320+(box[i]-320)*27/32
    a,b,c,d = map(round,box)
    roi = pixels[b:d,a:c]
    if not roi.size: return None
    hit = roi.min(axis=2)>190 if callback in ('0xfc050','0xfc070','0xfc7d0','0xfbe30') else roi.max(axis=2)<100
    seen = np.zeros_like(hit);ink = []
    for y,x in np.argwhere(hit):
        if seen[y,x]: continue
        queue,component = [(int(y),int(x))],[];seen[y,x] = True
        while queue:
            yy,xx = queue.pop();component.append((yy,xx))
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    ny,nx = yy+dy,xx+dx
                    if 0<=ny<hit.shape[0] and 0<=nx<hit.shape[1] and hit[ny,nx] and not seen[ny,nx]:
                        seen[ny,nx] = True;queue.append((ny,nx))
        if not any(y in (0,hit.shape[0]-1) or x in (0,hit.shape[1]-1) for y,x in component):
            ink.extend(component)
    if not ink: return None
    ys,xs = zip(*ink)
    return [a+min(xs),b+min(ys),a+max(xs)+1,b+max(ys)+1]


def compare(reference_image, rendered, geometry, text_boxes, *, runtime=False):
    import numpy as np
    ref, out = np.asarray(reference_image), np.asarray(rendered.convert("RGB"))
    regions = {}
    meshes = {"frame_rim": geometry["frame"], "centre_pill": geometry["down"],
              "clock_strip": geometry["clock"]}
    if runtime:
        meshes.update(left_panel=geometry["objects"].get("zscore_buga"),
                      right_panel=geometry["objects"].get("hscore_buga"))
    for name, box in exact.SOURCE_REGIONS.items():
        target = list(exact.hud_box(box))
        if geometry["widescreen"]:
            target[0] = 320 + (target[0] - 320) * 27 / 32
            target[2] = 320 + (target[2] - 320) * 27 / 32
        a, b, c, d = [round(v) for v in target]
        want, have = ref[b:d, a:c], out[b:d, a:c]
        mask = np.ones(want.shape[:2], dtype=bool)
        if name == "frame_rim":
            mask[2:-2, 2:-2] = False
        histogram = []
        for channel in range(3):
            x, _ = np.histogram(want[:, :, channel][mask], bins=16, range=(0, 256), density=True)
            y, _ = np.histogram(have[:, :, channel][mask], bins=16, range=(0, 256), density=True)
            histogram.append(float(np.abs(np.cumsum(x - y)).sum() * 256))
        actual = meshes.get(name)
        regions[name] = dict(
            reference_box=target, native_box=actual,
            native_boundary_error_px=None if actual is None else max(abs(x - y) for x, y in zip(actual, target)),
            rgb_mae=float(np.abs(want.astype(float) - have.astype(float))[mask].mean()),
            histogram_wasserstein_rgb=histogram,
            compared_pixels=int(mask.sum()), pixel_edges=edge_distance(want, have, mask),
            neutral_subset=not runtime and name in ("left_panel", "right_panel"))
    texts = {}
    for row in geometry["draws"]:
        callback = row["callback"]
        if callback not in text_boxes or not row["vertices"]:
            continue
        actual = box_of([v["screen"] for v in row["vertices"]])
        target = text_boxes[callback][:]
        if geometry["widescreen"]:
            for i in (0, 2):
                target[i] = 320 + (target[i] - 320) * 27 / 32
        texts[callback] = dict(text=row["text"], font=row["font"], native_quad_box=actual,
                               reference_ink_box=target,
                               max_error_px=max(abs(x - y) for x, y in zip(actual, target)))
        ink = rendered_text_ink(out,callback,geometry["widescreen"])
        texts[callback]['rendered_ink_box'] = ink
        texts[callback]['rendered_ink_max_error_px'] = None if ink is None else max(abs(x-y) for x,y in zip(ink,target))
    limits = dict(native_boundary_px=1, edge_p95_px=1, rgb_mae=8, text_box_px=1)
    measured = [row for row in regions.values() if not row["neutral_subset"]]
    passed = all(row["native_boundary_error_px"] is not None and row["native_boundary_error_px"] <= 1
                 and row["rgb_mae"] <= 8 and row["pixel_edges"] is not None
                 and row["pixel_edges"]["p95_px"] <= 1 for row in measured)
    passed = passed and bool(texts) and all(row["max_error_px"] <= 1 for row in texts.values())
    return dict(regions=regions, text=texts, acceptance_limits=limits,
                mean_region_rgb_mae=sum(v["rgb_mae"] for v in regions.values()) / len(regions),
                containment=projection.containment_failures(geometry, geometry["frame"], .02),
                exact_match=passed,
                metric_limits="Native quad bounds include transparent glyph padding. Rendered-ink boxes are a separate threshold diagnostic at HUD resolution with ROI-edge components excluded. Pixel edges include text/logos; static neutral panels intentionally omit team art.")


class Build:
    def __init__(self, pack, xbe):
        from contextlib import ExitStack
        with ExitStack() as stack:
            self.file = stack.enter_context(pack.open("rb"))
            self.view = art.PackView.from_fd(self.file.fileno(), 0, pack.stat().st_size)
            self.spans = {n: self.view[v["pack_offset"]:v["pack_offset"] + v["span_size"]]
                          for n, v in art.RESOURCES.items()}
            self.payload = xbe.read_bytes()
            self.fonts = projection.read_fonts(pack)
            self.retail_scene = scene.pinned(self.spans["score_bug"], art.RESOURCES["score_bug"])
            self.panels = []
            for team, side in (("LV", "away"), ("HOU", "home")):
                v = art.TEAM_LOGOS[team]
                span = self.view[v["pack_offset"]:v["pack_offset"] + v["span_size"]]
                self.panels.extend(art._compiled_panels(self.spans["score_buga"], span, team, side))
            self.font_spans = scoped.compile_collection(self.view)
            self.private_fonts = [projection.private_font(span, self.fonts[slot])
                                  for span, (slot, _sx, _sy) in zip(self.font_spans, scoped.SCALES)]
            self._files = stack.pop_all()

    def close(self):
        self._files.close()

    def render(self, path, *, runtime=False, widescreen=False, mode=0, historical=False,
               atlas_image=None, mesh=None, score_values=(0, 0), score_phase=0, timeouts=(3, 3),
               previous_scores=(0,0), possession='home'):
        if historical:
            mesh = scene.mesh_v9(self.retail_scene)
            atlas_image = scene.atlas_v9(self.spans)
        if mesh is None:
            mesh = exact.mesh(self.retail_scene, runtime=runtime)
        if atlas_image is None:
            atlas_image = exact.atlas()
        span, _ = scene.layout.refit(self.spans["score_bug"], scene.serialize(mesh))
        decoded = scene.decode(span)[1]  # Installed bytes, including normshort quantization.
        texture, receipt = scene.encode_atlas(self.spans["score_buga"], atlas_image)
        capture = {}
        geometry = projection.native_geometry(self.payload, decoded, widescreen=widescreen, mode=mode,
                    texture_span=texture, fonts=self.fonts, capture=capture, baseline_v9=historical,
                    runtime_textures=self.panels if runtime else None,
                    identity=dict(home="HOU", away="LV", home_code="37", away_code="20"),
                    score_values=score_values, score_phase=score_phase, timeouts=timeouts,
                    previous_scores=previous_scores, possession=possession,
                    runtime_fonts=self.font_spans if runtime else ())
        try:
            geometry.update(projection.native_text_draw(capture))
            geometry.update(projection.render_native(decoded, texture, self.fonts + (self.private_fonts if runtime else []), geometry, path,
                                                       texture_spans=capture["texture_spans"]))
            geometry["resource_receipt"] = dict(scene_sha256=scene.digest(span), atlas_sha256=scene.digest(texture),
                                                atlas=receipt, wrapper_identical=span[:32] == self.spans["score_bug"][:32])
            return geometry
        finally:
            capture["machine"].close()


def compiler_pins(build):
    """Generate identities from pinned source slices, never trust missing pins."""
    static = scene.layout.refit(build.spans["score_bug"], scene.serialize(exact.mesh(build.retail_scene)))[0]
    runtime = scene.stage_binding_scene(build.spans["score_bug"], runtime=True)[0]
    texture = scene.encode_atlas(build.spans["score_buga"], exact.atlas())[0]
    hud = bytearray(build.view[art.HUD_START:art.HUD_START + art.HUD_SIZE])
    for name, data in (("score_bug", runtime), ("score_buga", texture)):
        off = art.RESOURCES[name]["pack_offset"] - art.HUD_START
        hud[off:off + len(data)] = data
    panels = []
    for team, record in [(None, {"asset_code": "--"})] + sorted(art.TEAM_LOGOS.items()):
        span = b"" if team is None else build.view[record["pack_offset"]:record["pack_offset"] + record["span_size"]]
        for side in ("home", "away"):
            panels += [(record["asset_code"], data) for data in
                       art._compiled_panels(build.spans["score_buga"], span, team, side)]
    return dict(PATCHED_SHA256=dict(score_bug=scene.digest(static), score_buga=scene.digest(texture)),
                STATIC_SCENE_SHA256=scene.digest(scene.decode(static)[1]),
                RUNTIME_SCENE_SHA256=scene.digest(scene.decode(runtime)[1]),
                RUNTIME_PINS={**art.RUNTIME_PINS, "hud_after": scene.digest(hud),
                              "appendix": scene.digest(b"".join(data for _, data in panels) + b"".join(scoped.compile_collection(build.view)))},
                PROBE_APPEND_PINS={probe: scene.digest(b"".join(data for code, data in panels
                                                               if code in art.probe_codes(probe)) + (b"".join(scoped.compile_collection(build.view)) if art.probe_codes(probe) else b""))
                                   for probe in ("transport", "hooks", "neutral", "pair")})


def supplemental_evidence(build, output):
    """Bounded, disc-derived font study and all 32 compiled native panel pairs."""
    from PIL import Image, ImageDraw
    from nfl_main_menu_font import rgba_from_font
    fonts, panel_rows = {}, []
    sheet = Image.new("RGBA", (540, 36 * len(build.fonts)), "#252525")
    for index, font in enumerate(build.fonts):
        atlas = Image.frombytes("RGBA", (font.width, font.height), rgba_from_font(font))
        measurements = {}
        glyphs = {chr(g.codepoint): g for g in font.glyphs}
        for sample in ("0", "1st & 10", "1st", "13:10", "12", "4th & Inches"):
            at, boxes = 0, []
            for character in sample:
                if character == " ":
                    at += font.space_advance
                    continue
                glyph = glyphs[character]
                u, v, x, y = glyph.uv
                tile = atlas.crop(tuple(round(k) for k in (u * font.width, v * font.height,
                                                           x * font.width, y * font.height)))
                box = tile.getchannel("A").getbbox()
                if box:
                    boxes += [(at + glyph.left + box[0], glyph.top + box[1]),
                              (at + glyph.left + box[2], glyph.top + box[3])]
                at += glyph.advance
            measurements[sample] = dict(ink_box=box_of(boxes), advance=at)
        x = 58
        ImageDraw.Draw(sheet).text((5, index * 36 + 10), font.name, fill="white")
        for character in "01ST13:10&Inches":
            glyph = glyphs[character]
            u, v, a, b = glyph.uv
            tile = atlas.crop(tuple(round(k) for k in (u * font.width, v * font.height,
                                                       a * font.width, b * font.height)))
            sheet.alpha_composite(tile, (round(x + glyph.left), index * 36 + 2))
            x += glyph.advance
        fonts[font.name] = dict(slot=font.slot, decoded_sha256=font.decoded_sha256,
                                measurements=measurements)
    sheet.convert("RGB").save(output / "retail_font_study.png")
    private = []
    private_sheet = Image.new("RGBA", (540, 36 * len(build.private_fonts)), "#252525")
    for index, font in enumerate(build.private_fonts):
        atlas = Image.frombytes("RGBA", (font.width, font.height), rgba_from_font(font))
        glyphs = {chr(g.codepoint): g for g in font.glyphs}
        ImageDraw.Draw(private_sheet).text((5, index*36+10), font.name, fill="white")
        x = 105
        for character in ("V" if index == 4 else "01st13:10&"):
            glyph = glyphs[character]
            u, v, a, b = glyph.uv
            tile = atlas.crop(tuple(round(k) for k in (u*font.width, v*font.height, a*font.width, b*font.height)))
            width = max(1, round(glyph.positions[4] - glyph.positions[0]))
            height = max(1, round(glyph.positions[9] - glyph.positions[1]))
            tile = tile.resize((width, height), Image.Resampling.BILINEAR)
            private_sheet.alpha_composite(tile, (round(x+glyph.left), index*36+2+round(glyph.top)))
            x += glyph.advance
        private.append(dict(name=font.name, decoded_sha256=font.decoded_sha256,
            donor=scoped.SCALES[index][0]+1, scales=scoped.SCALES[index][1:], weight=scoped.WEIGHT,
            glyph_quads={character: dict(advance=glyphs[character].advance, positions=glyphs[character].positions,
                                        uv=glyphs[character].uv) for character in "01st:&"}))
    private_sheet.convert("RGB").save(output / "private_font_study.png")
    write_json(output / "font_study.json", dict(fonts=fonts, private_fonts=private,
        private_font_descriptors_bound=True, authored_chevron_bound=scoped.CHEVRON,
        custom_glyph_atlas_bound=bool((scoped.WEIGHT if type(scoped.WEIGHT) is int else any(scoped.WEIGHT)) or scoped.CHEVRON),
        selected=dict(static_scores="font8", static_small_text="font4", runtime=list(scoped.NAMES)),
        global_fonts_replaced=False, private_append_bytes=scoped.APPEND_SIZE,
        native_heap_bytes=scoped.HEAP_BYTES, experimental=True, runtime_witnessed=False,
        evidence="Private FONT descriptors are registered through native 43e30/44b60/492c0 and bound only to scorebug objects."
                 " Native quad submissions are measured separately in native_audit.json."
                 " Glyph families remain retail; the private possession mask is authored. GPU filtering/blend is a model."))
    sheet = Image.new("RGB", (1072, 448), "#101010")
    for index, (team, record) in enumerate(sorted(art.TEAM_LOGOS.items())):
        span = build.view[record["pack_offset"]:record["pack_offset"] + record["span_size"]]
        col, row = index % 4, index // 4
        ImageDraw.Draw(sheet).text((col * 268 + 4, row * 56 + 2), team, fill="white")
        pair = {}
        for side_index, side in enumerate(("away", "home")):
            compiled = art._compiled_panels(build.spans["score_buga"], span, team, side)[3]
            chunk, decoded, _ = scene.decode(compiled)
            texture = scene.tx.parse_texture(decoded, chunk)
            pixels = Image.frombytes("RGBA", (128, 32), scene.tx.texture_to_rgba(decoded, chunk, texture))
            sheet.paste(pixels.convert("RGB"), (col * 268 + side_index * 132 + 4, row * 56 + 19))
            pair[side] = dict(name=texture.name, span_sha256=scene.digest(compiled))
        panel_rows.append(dict(team=team, source=record, pair=pair))
    sheet.save(output / "all_32_native_panels.png")
    write_json(output / "panel_inventory.json", panel_rows)


def main(argv=None):
    from PIL import Image, ImageDraw
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True, type=Path)
    parser.add_argument("--xbe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--witness", type=Path, help="historical witness path; never marks this build witnessed")
    parser.add_argument("--accept-palette", action="store_true",
                        help="author the selected red bias and compiler identities in this checkout")
    parser.add_argument("--audit-only", action="store_true",
                        help="verify the selected compiler and refresh both aspect audits without repeating tuning")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    source, target = reference()
    source.crop(exact.SOURCE_RAILS).save(args.output / "reference_crop.png")
    target.save(args.output / "reference_640x480.png")
    wide_target = wide_reference(target)
    wide_target.save(args.output / "reference_wide_v3.png")
    text_boxes = reference_text_boxes(source)
    write_json(args.output / "measurement.json", dict(source=str(REFERENCE.relative_to(ROOT)),
        sha256=exact.REFERENCE_SHA256, source_size=list(source.size), source_rails=exact.SOURCE_RAILS,
        hud_rails=exact.RAILS, regions=exact.SOURCE_REGIONS, text_ink_boxes=text_boxes,
        text_measurement="8-connected threshold components; discard ROI-edge components and specks under three source pixels. Metric v4 removes the five-pixel quarter capsule-rim fragment.",
        transform="x=x/3; y=16+y*448/1080. Full photo fitted to native active viewport, not clipped at y=464.",
        boundary_uncertainty_source_px=2, evidence="Measured JPEG transition bands; no clean vector alpha or GPU witness."))
    build = Build(args.pack, args.xbe)
    try:
        scores_path = args.output / "scores.json"
        trials = json.loads(scores_path.read_text())["iterations"] if scores_path.is_file() else []
        def trial(label, atlas, *, historical=False, bias=None):
            number = len(trials)
            rows, pictures = {}, []
            for runtime in (False, True):
                if historical and runtime:
                    continue
                suffix = "runtime" if runtime else "static"
                path = args.output / f"iter_{number:02d}_{suffix}.png"
                geometry = build.render(path, historical=historical, runtime=runtime, atlas_image=atlas)
                with Image.open(path) as opened:
                    picture = opened.convert("RGB")
                rows[suffix] = compare(target, picture, geometry, text_boxes, runtime=runtime)
                rows[suffix]["resources"] = geometry["resource_receipt"]
                pictures.append((suffix, picture))
            sheet = Image.new("RGB", (640 * len(pictures), 504), "#101010")
            for i, (suffix, picture) in enumerate(pictures):
                sheet.paste(picture, (i * 640, 24))
                ImageDraw.Draw(sheet).text((i * 640 + 8, 6), label + " / " + suffix, fill="white")
            sheet.save(args.output / f"iter_{number:02d}.png")
            record = dict(iteration=number, label=label, layers=rows, metric_version=2,
                          red_bias=bias, accepted=False, variant_is_shipped=False,
                          parameters=dict(anchors=exact.ANCHORS, red_bias=bias,
                            core_sha256=scene.digest(Path(exact.__file__).read_bytes()),
                            resources_sha256=scene.digest(Path(art.__file__).read_bytes())))
            trials.append(record)
            write_json(args.output / "scores.json", dict(iterations=trials, complete=False))
            print(label, {k: round(v["mean_region_rgb_mae"], 4) for k, v in rows.items()}, flush=True)
            return record
        previous = json.loads(scores_path.read_text()) if args.audit_only else None
        if args.audit_only:
            if not previous.get("complete") or previous["selected_red_bias"] != exact.RED_BIAS:
                raise ValueError("audit-only requires a completed, selected compiler")
            current = trials[previous["selected_iteration"]]
        else:
            trial("v9 baseline / corrected rim metric", exact.atlas(), historical=True)
            current = trial("measured anchors and shared timeout palette", exact.atlas(), bias=exact.RED_BIAS)
        candidates = {exact.RED_BIAS: current}
        def objective(record):
            return sum(layer["mean_region_rgb_mae"] for layer in record["layers"].values())
        # Deterministic bounded coordinate descent. Preserve every rejected
        # neighbour as evidence; do not call an arbitrarily chosen pass a plateau.
        best_bias = exact.RED_BIAS
        for step in (() if args.audit_only else (4, 2, 1)):
            while True:
                for bias in (best_bias - step, best_bias + step):
                    if -24 <= bias <= 24 and bias not in candidates:
                        candidates[bias] = trial(f"gradient red bias {bias:+d}", exact.atlas(red_bias=bias), bias=bias)
                selected = min(candidates, key=lambda v: (objective(candidates[v]), abs(v), v))
                if objective(candidates[best_bias]) - objective(candidates[selected]) < .005:
                    break
                best_bias = selected
        best = candidates[best_bias]
        if best_bias != exact.RED_BIAS and not args.accept_palette:
            write_json(scores_path, dict(iterations=trials, complete=False,
                       recommended_red_bias=best_bias, instruction="Re-run with --accept-palette to install the measured candidate."))
            raise ValueError("better palette found; --accept-palette is required to author source and pins")
        exact.RED_BIAS = best_bias
        pins = compiler_pins(build)
        if args.accept_palette:
            path = Path(exact.__file__)
            path.write_text(re.sub(r"^RED_BIAS = .*", "RED_BIAS = " + str(best_bias), path.read_text(), flags=re.M), encoding="utf-8")
            path = Path(art.__file__)
            contents = path.read_text()
            for key, value in pins.items():
                contents, count = re.subn(r"^" + key + r" = .*", key + " = " + repr(value), contents, flags=re.M)
                if count != 1:
                    raise ValueError("missing unique compiler identity " + key)
            path.write_text(contents, encoding="utf-8")
            # Pin objects imported by the unchanged public writer as well.
            for key, value in pins.items():
                setattr(art, key, value)
            scene.PATCHED_SHA256 = art.PATCHED_SHA256
        elif any(getattr(art, key) != value for key, value in pins.items()):
            raise ValueError("compiler pins differ; use --accept-palette in an authoring checkout")
        for record in trials:
            record["accepted"] = record["variant_is_shipped"] = record is best
        write_json(args.output / "compiler_pins.json", pins)
        supplemental_evidence(build, args.output)
        finals, final_scores = {}, {}
        for runtime in (False, True):
            for widescreen in (False, True):
                for mode in (0, 1):
                    name = ("runtime" if runtime else "static") + ("_wide" if widescreen else "_4x3") + f"_mode{mode}"
                    path = args.output / (name + ".png")
                    geometry = build.render(path, runtime=runtime, widescreen=widescreen, mode=mode)
                    failures = projection.containment_failures(geometry, geometry["frame"], .02)
                    if failures:
                        raise ValueError("containment: " + name + " " + str(failures))
                    finals[name] = geometry
                    with Image.open(path) as opened:
                        final_scores[name] = compare(wide_target if widescreen else target,
                            opened.convert("RGB"), geometry, text_boxes, runtime=runtime)
        write_json(args.output / "native_audit.json", dict(experimental=True, witnessed=False,
                                                          historical_witness_argument=str(args.witness) if args.witness else None,
                                                          static_receipts=projection.static_receipts(build.payload, build.spans),
                                                          projections=finals))
        sheet = Image.new("RGB", (1110, 140), "#101010")
        for i, (label, path) in enumerate((("REAL BROADCAST", args.output / "reference_640x480.png"),
                                          ("STATIC: NATIVE INPUTS", args.output / "static_4x3_mode0.png"),
                                          ("RUNTIME: NATIVE INPUTS", args.output / "runtime_4x3_mode0.png"))):
            with Image.open(path) as image:
                sheet.paste(image.crop((135, 398, 505, 460)), (i * 370, 30))
            ImageDraw.Draw(sheet).text((i * 370 + 6, 8), label, fill="white")
        ImageDraw.Draw(sheet).text((6, 108), "EXPERIMENTAL / UNWITNESSED / GPU AND FONT RESIDUALS REMAIN", fill="white")
        sheet.save(args.output / "final_side_by_side.png")
        strip = Image.new("RGB", (740, 85 * len(trials)), "#101010")
        for trial in trials:
            y = trial["iteration"] * 85
            ImageDraw.Draw(strip).text((6, y + 2), trial["label"], fill="white")
            for i, suffix in enumerate(("static", "runtime")):
                path = args.output / f"iter_{trial['iteration']:02d}_{suffix}.png"
                if path.is_file():
                    with Image.open(path) as image:
                        strip.paste(image.crop((135, 398, 505, 460)), (i * 370, y + 20))
        strip.save(args.output / "iteration_strip.png")
        result = dict(**(previous or {}))
        result.update(iterations=trials, complete=True, full_audit_current=True,
                    audit_scope="Installed static/runtime inputs in both aspects and both modes; metric v4.",
                    exact_match=all(row["exact_match"] for row in final_scores.values()),
                    stopping_rule=("See converged_stages and region_plateaus for retained coordinate neighbours, domains and thresholds. Local plateaus do not establish pixel equality."
                        if previous and previous.get("converged_stages") else
                        "Red-channel coordinate descent at steps 4, 2, 1; no neighbour improves combined static/runtime region MAE by 0.005. This is a local palette plateau, not pixel equality."),
                    selected_iteration=best["iteration"], selected_red_bias=best_bias,
                    final_scores=final_scores)
        from mod_editor.core import nfl2k5_scorebug_runtime as owner
        result.setdefault("audit", {})["current_source_sha256"] = {
            str(Path(module.__file__).relative_to(ROOT)): scene.digest(Path(module.__file__).read_bytes())
            for module in (exact, scoped, art, scene, owner, projection)}
        result['audit']['current_source_sha256'][str(Path(__file__).relative_to(ROOT))] = scene.digest(Path(__file__).read_bytes())
        write_json(args.output / "scores.json", result)
        write_json(args.output / "font_binding.json", dict(experimental=True, witnessed=False,
            measurement_version=4, selected_iteration=best["iteration"], scales=scoped.SCALES,
            text=final_scores["runtime_4x3_mode0"]["text"], native_resources=finals["runtime_4x3_mode0"]["private_fonts"],
            static_fallback="Retail FONT4/FONT8; private descriptors belong only to the diagnostic runtime collection.",
            loader_code_guards=scoped.CODE_GUARDS, code_used=len(owner.code_for(0,0)[0].rstrip(b"\xcc")),
            code_budget=owner.CODE_SIZE, data_budget=owner.DATA_SIZE,
            append_bytes=scoped.APPEND_SIZE, native_heap_bytes=scoped.HEAP_BYTES))
    finally:
        build.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
