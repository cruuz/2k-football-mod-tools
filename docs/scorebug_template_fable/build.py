#!/usr/bin/env python3
"""Export the scorebar template: layers, team blocks, atlas, previews, comparison.

Run from anywhere:  python3 docs/scorebug_template_fable/build.py [--skip-teams] [--skip-export]

Needs: inkscape (any 1.x) on PATH, Pillow, numpy.  Reads layout.json (the contract),
scorebug_bar_master.svg, team_block_template.svg and teams.json; writes

  layers/1x/*.png, layers/2x/*.png      one full-canvas RGBA PNG per layer (476x48 / 952x96)
  teams/1x/<ABBR>_{away,home}.png, teams/2x/...
  atlas/atlas_1x.png, atlas/atlas.json, atlas/palette_report.json
  preview_640x480.png, preview_2x.png, compare.png, previews/*.png

Nothing here touches the game; the studio compiler consumes the folder.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
LAYOUT = json.loads((HERE / "layout.json").read_text())
BAR_W, BAR_H = LAYOUT["hud"]["bar_size"]
RAILS = LAYOUT["hud"]["rails"]
SCALES = {"1x": 1, "2x": 2}
FONT_BOLD = "/usr/share/fonts/truetype/msttcorefonts/arialbd.ttf"
FONT_FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FIELD_GREEN = (47, 90, 42)
SVG_NS = "http://www.w3.org/2000/svg"


# ------------------------------------------------------------------ inkscape export
def inkscape_export(svg: Path, jobs: list[tuple[str, Path, int]]) -> None:
    """Export several group ids from one SVG in one inkscape process.

    jobs = [(svg_id, out_png, export_width_px), ...]
    """
    if not jobs:
        return
    actions = []
    for svg_id, out, width in jobs:
        out.parent.mkdir(parents=True, exist_ok=True)
        actions.append(
            f"export-id:{svg_id};export-id-only;export-area-page;export-width:{width};"
            f"export-background-opacity:0;export-filename:{out};export-do"
        )
    cmd = ["inkscape", str(svg), "--actions=" + ";".join(actions)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"inkscape failed ({res.returncode}):\n{res.stderr}")
    for _, out, width in jobs:
        if not out.exists():
            sys.exit(f"inkscape did not write {out}")
        im = Image.open(out)
        if im.size[0] != width:
            sys.exit(f"{out}: expected width {width}, got {im.size}")


def export_layers() -> None:
    master = HERE / LAYOUT["sources"]["master_svg"]
    jobs = []
    for layer in LAYOUT["layers"]:
        for tag, s in SCALES.items():
            jobs.append((layer["svg_id"], HERE / "layers" / tag / layer["file"], BAR_W * s))
    inkscape_export(master, jobs)
    print(f"layers: {len(jobs)} PNGs")


def export_teams() -> None:
    """One SVG sheet with all 64 blocks (ids team_<ABBR>_away/home), exported by id."""
    template = HERE / LAYOUT["sources"]["team_block_svg"]
    teams = json.loads((HERE / LAYOUT["sources"]["teams"]).read_text())
    ET.register_namespace("", SVG_NS)
    tree = ET.parse(template)
    root = tree.getroot()
    away = root.find(f"{{{SVG_NS}}}g[@id='layer_away_block']")
    home = root.find(f"{{{SVG_NS}}}g[@id='layer_home_block']")
    root.remove(away)
    root.remove(home)

    def filled(proto: ET.Element, team: dict, side: str) -> ET.Element:
        g = ET.fromstring(ET.tostring(proto))
        g.set("id", f"team_{team['abbr']}_{side}")
        for node in g.iter():
            binding = node.get("data-fill")
            if binding:
                _, key = binding.split(".")
                node.set("fill", team[key])
            # ids must stay unique across the sheet
            if node is not g and node.get("id"):
                node.set("id", f"{node.get('id')}-{team['abbr']}-{side}")
        return g

    jobs = []
    for team in teams:
        root.append(filled(away, team, "away"))
        root.append(filled(home, team, "home"))
        for side in ("away", "home"):
            for tag, s in SCALES.items():
                jobs.append((f"team_{team['abbr']}_{side}", HERE / "teams" / tag / f"{team['abbr']}_{side}.png", BAR_W * s))
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        sheet = Path(tmp) / "team_sheet.svg"
        tree.write(sheet, xml_declaration=True, encoding="UTF-8")
        inkscape_export(sheet, jobs)
    # The 1x team blocks are compile-ready: each is reduced to the per-texture palette target so a
    # block never carries more colours than the P8 texture it becomes.  2x stays raw for editing.
    target = LAYOUT["atlas"]["palette_target"]
    for _, out, width in jobs:
        if width == BAR_W:
            quantize_rgba_png(out, target)
    print(f"teams: {len(teams)} teams, {len(jobs)} PNGs (1x reduced to <= {target} colours each)")


def quantize_rgba(im: Image.Image, colours: int, edge_budget: int = 16) -> Image.Image:
    """Reduce an RGBA image to at most `colours` distinct RGBA values, gradient-friendly.

    Opaque pixels get median-cut (far smoother on gradients than the octree), the few
    anti-aliased edge pixels (0 < alpha < 255) get their own small octree budget, and
    fully transparent pixels collapse to (0,0,0,0).  No dithering: the P8 texture is
    bilinear-filtered in game and dither noise would show.
    """
    im = im.convert("RGBA")
    a = np.asarray(im)
    alpha = a[:, :, 3]
    opaque = alpha == 255
    edge = (alpha > 0) & (alpha < 255)
    out = np.zeros_like(a)
    if opaque.any():
        rgb = Image.fromarray(a[:, :, :3], "RGB")
        q = rgb.quantize(colors=max(2, colours - edge_budget), method=Image.Quantize.MEDIANCUT,
                         dither=Image.Dither.NONE).convert("RGB")
        qa = np.asarray(q)
        out[opaque, :3] = qa[opaque]
        out[opaque, 3] = 255
    if edge.any():
        px = a[edge]
        uniq = np.unique(px, axis=0)
        if len(uniq) > edge_budget:
            strip = Image.fromarray(px.reshape(1, -1, 4), "RGBA")
            qs = strip.quantize(colors=edge_budget, method=Image.Quantize.FASTOCTREE,
                                dither=Image.Dither.NONE).convert("RGBA")
            px = np.asarray(qs).reshape(-1, 4)
        out[edge] = px
    return Image.fromarray(out, "RGBA")


def quantize_rgba_png(path: Path, colours: int) -> None:
    quantize_rgba(Image.open(path), colours).save(path)


def to_p8(im: Image.Image) -> Image.Image:
    """Lossless RGBA -> P (RGBA palette) for an image with at most 256 distinct colours."""
    a = np.asarray(im.convert("RGBA"))
    flat = a.reshape(-1, 4)
    uniq, inverse = np.unique(flat, axis=0, return_inverse=True)
    if len(uniq) > 256:
        raise ValueError(f"{len(uniq)} colours; P8 holds 256")
    p = Image.fromarray(inverse.reshape(a.shape[:2]).astype(np.uint8), "P")
    p.putpalette(uniq.astype(np.uint8).tobytes(), rawmode="RGBA")
    return p


# ------------------------------------------------------------------ composition
def load_layer(name: str, scale: str) -> Image.Image:
    layer = next(l for l in LAYOUT["layers"] if l["name"] == name)
    return Image.open(HERE / "layers" / scale / layer["file"]).convert("RGBA")


def compose_bar(scale: str, away: str | None = None, home: str | None = None,
                timeouts: bool | None = None) -> Image.Image:
    s = SCALES[scale]
    bar = Image.new("RGBA", (BAR_W * s, BAR_H * s), (0, 0, 0, 0))
    for layer in LAYOUT["layers"]:
        enabled = layer["enabled"]
        if layer["name"] == "timeout_marks" and timeouts is not None:
            enabled = timeouts
        if not enabled:
            continue
        src = HERE / "layers" / scale / layer["file"]
        if layer["name"] == "away_block" and away:
            src = HERE / "teams" / scale / f"{away}_away.png"
        if layer["name"] == "home_block" and home:
            src = HERE / "teams" / scale / f"{home}_home.png"
        bar.alpha_composite(Image.open(src).convert("RGBA"))
    return bar


def font(cap_px: float) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if os.path.exists(FONT_BOLD) else FONT_FALLBACK
    # Arial Bold cap height is 0.716 em
    return ImageFont.truetype(path, max(6, round(cap_px / 0.716)))


def draw_text(canvas: Image.Image, state: dict, s: int, origin=(0, 0), possession: str | None = None) -> None:
    """Draw the eight live fields as the game would, at the layout.json anchors."""
    dr = ImageDraw.Draw(canvas)
    for spec in LAYOUT["text"]:
        text = state.get(spec["field"])
        if text is None:
            continue
        f = font(spec["cap_height_px"] * s)
        x = (spec["x"] - origin[0]) * s
        y = (spec["y"] - origin[1]) * s
        anchor = {"left": "ls", "centre": "ms", "right": "rs"}[spec["align"]]
        colour = spec["colour"]
        if possession and spec["field"] == f"{possession}_abbreviation":
            colour = "#F2D21C"
        dr.text((x + s, y + s), text, font=f, fill=(0, 0, 0, 170), anchor=anchor)
        dr.text((x, y), text, font=f, fill=colour, anchor=anchor)


def field(scale_px: int, size=(640, 480)) -> Image.Image:
    """Neutral field-green background with faint yard lines, like the capture."""
    w, h = size[0] * scale_px, size[1] * scale_px
    im = Image.new("RGBA", (w, h), FIELD_GREEN + (255,))
    dr = ImageDraw.Draw(im)
    for i in range(-2, 12):
        x0 = i * 80 * scale_px
        dr.line([(x0, h), (x0 + 60 * scale_px, 0)], fill=(215, 228, 210, 255), width=max(1, scale_px))
    return im


def preview(scale: str, state: dict, out: Path, away=None, home=None, timeouts=None, possession=None,
            label: str | None = None) -> Image.Image:
    s = SCALES[scale]
    canvas = field(s)
    bar = compose_bar(scale, away, home, timeouts)
    canvas.alpha_composite(bar, (RAILS[0] * s, RAILS[1] * s))
    draw_text(canvas, state, s, possession=possession)
    if label:
        ImageDraw.Draw(canvas).text((8 * s, 6 * s), label, font=font(7 * s), fill=(235, 240, 235, 255))
    canvas.convert("RGB").save(out)
    return canvas


def crop_rails(im: Image.Image, s: int) -> Image.Image:
    return im.crop((RAILS[0] * s, RAILS[1] * s, RAILS[2] * s, RAILS[3] * s))


def compare(mine_2x: Image.Image, out: Path) -> None:
    target = Image.open(HERE / "reference" / "target_NO_MIA.png").convert("RGBA")
    v9 = Image.open(HERE / "reference" / "after_v9_640x480.png").convert("RGBA")
    v9 = v9.resize((v9.width * 2, v9.height * 2), Image.NEAREST)
    rows = [
        ("THIS TEMPLATE (new art, preview text is a stand-in for the game font)", crop_rails(mine_2x, 2)),
        ("SUPPLIED TARGET target_NO_MIA.png (staged mockup, rails [84,381,560,429])", crop_rails(target, 2)),
        ("STATIC V9 from disc art (after_v9_640x480.png)", crop_rails(v9, 2)),
    ]
    pad, label_h = 16, 22
    w = max(r.width for _, r in rows) + pad * 2
    h = sum(r.height + label_h + pad for _, r in rows) + pad
    sheet = Image.new("RGB", (w, h), (24, 26, 30))
    dr = ImageDraw.Draw(sheet)
    y = pad
    for label, im in rows:
        dr.text((pad, y), label, font=font(9), fill=(200, 205, 210))
        y += label_h
        sheet.paste(im.convert("RGB"), (pad, y))
        y += im.height + pad
    sheet.save(out)


# ------------------------------------------------------------------ atlas + palette
def unique_colours(im: Image.Image) -> int:
    a = np.asarray(im.convert("RGBA")).reshape(-1, 4)
    a = a[a[:, 3] > 0]
    if len(a) == 0:
        return 0
    return len(np.unique(a, axis=0))


def build_atlas() -> dict:
    spec = LAYOUT["atlas"]
    sw, sh = spec["sheet_size"]
    sheet = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    placed = []
    # shelf packer, tallest tile first (packing_order in layout.json is the DRAW order)
    crops = []
    for tile in spec["tiles"]:
        x0, y0, x1, y1 = tile["src_bar"]
        crops.append((tile, load_layer(tile["layer"], "1x").crop((x0, y0, x1, y1))))
    crops.sort(key=lambda tc: -tc[1].height)
    x = y = shelf_h = 0
    for tile, crop in crops:
        if x + crop.width > sw:
            x, y, shelf_h = 0, y + shelf_h, 0
        if y + crop.height > sh:
            sys.exit(f"atlas sheet {sw}x{sh} is too small at tile {tile['name']}")
        sheet.alpha_composite(crop, (x, y))
        placed.append({**tile, "atlas_rect": [x, y, x + crop.width, y + crop.height]})
        x += crop.width
        shelf_h = max(shelf_h, crop.height)
    raw = unique_colours(sheet)
    target = spec["palette_target"]
    reduced = quantize_rgba(sheet, target)
    quant = to_p8(reduced)  # exact: the image already has <= target colours
    (HERE / "atlas").mkdir(exist_ok=True)
    quant.save(HERE / "atlas" / "atlas_1x.png")
    back = Image.open(HERE / "atlas" / "atlas_1x.png")
    palette_len = unique_colours(back.convert("RGBA"))
    if palette_len > 256:
        sys.exit(f"atlas has {palette_len} colours after quantization; the P8 budget is 256")
    (HERE / "atlas" / "atlas.json").write_text(json.dumps({
        "sheet_size": [sw, sh], "format": spec["format"], "tiles": placed,
        "raw_unique_rgba": raw, "quantized_unique_rgba": palette_len, "palette_target": target}, indent=2))
    return {"raw": raw, "quantized": palette_len, "mode": back.mode}


def palette_report(atlas: dict) -> None:
    rep = {"atlas_1x": atlas, "layers_1x": {}, "layers_2x": {}, "default_composite_1x": None, "teams_1x": {}}
    for layer in LAYOUT["layers"]:
        for tag in SCALES:
            rep[f"layers_{tag}"][layer["name"]] = unique_colours(Image.open(HERE / "layers" / tag / layer["file"]))
    rep["default_composite_1x"] = unique_colours(compose_bar("1x"))
    rep["default_composite_2x"] = unique_colours(compose_bar("2x"))
    tdir = HERE / "teams" / "1x"
    if tdir.exists():
        worst = 0
        for p in sorted(tdir.glob("*.png")):
            n = unique_colours(Image.open(p))
            rep["teams_1x"][p.stem] = n
            worst = max(worst, n)
        rep["teams_1x_max"] = worst
    over = [k for k, v in rep["teams_1x"].items() if v > 256]
    rep["verdict"] = {
        "atlas_within_256": atlas["quantized"] <= 256,
        "atlas_within_target_128": atlas["quantized"] <= 128,
        "team_blocks_over_256": over,
    }
    (HERE / "atlas" / "palette_report.json").write_text(json.dumps(rep, indent=2))
    print("palette:", json.dumps(rep["verdict"]), "| atlas raw", atlas["raw"], "-> quantized", atlas["quantized"],
          "| composite 1x", rep["default_composite_1x"], "| team max", rep.get("teams_1x_max"))


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-export", action="store_true", help="reuse layers/ PNGs")
    ap.add_argument("--skip-teams", action="store_true", help="do not re-export the 32 team pairs")
    args = ap.parse_args()
    if not args.skip_export:
        export_layers()
        if not args.skip_teams:
            export_teams()

    state_no_mia = {"away_abbreviation": "NO", "away_score": "0", "home_abbreviation": "MIA", "home_score": "0",
                    "down_distance": "1st & 10", "quarter": "1st", "game_clock": "13:10", "play_clock": ":12"}
    p1 = preview("1x", state_no_mia, HERE / "preview_640x480.png", possession="away")
    p2 = preview("2x", state_no_mia, HERE / "preview_2x.png", possession="away")
    compare(p2, HERE / "compare.png")

    pv = HERE / "previews"
    pv.mkdir(exist_ok=True)
    long_state = {"away_abbreviation": "KC", "away_score": "38", "home_abbreviation": "BUF", "home_score": "35",
                  "down_distance": "4th & Inches", "quarter": "OT2", "game_clock": "15:00", "play_clock": ":40"}
    preview("2x", long_state, pv / "widest_strings_2x.png", timeouts=True, possession="home",
            label="widest strings + timeout marks on")
    if (HERE / "teams" / "1x").exists():
        matchups = [("NO", "MIA", state_no_mia), ("BAL", "PIT", {**state_no_mia, "away_abbreviation": "BAL", "home_abbreviation": "PIT", "away_score": "17", "home_score": "14", "down_distance": "2nd & 7", "quarter": "2nd", "game_clock": "6:42", "play_clock": ":24"}),
                    ("LV", "HOU", {**state_no_mia, "away_abbreviation": "LV", "home_abbreviation": "HOU"}), ("KC", "BUF", long_state)]
        rows = []
        for a, h, st in matchups:
            im = preview("2x", st, pv / f"team_{a}_{h}_2x.png", away=a, home=h, timeouts=True, possession="away",
                         label=f"per-team blocks {a} at {h} (runtime hook required)")
            rows.append(crop_rails(im, 2))
        sheet = Image.new("RGB", (rows[0].width + 32, (rows[0].height + 16) * len(rows) + 16), FIELD_GREEN)
        for i, r in enumerate(rows):
            sheet.paste(r.convert("RGB"), (16, 16 + i * (r.height + 16)))
        sheet.save(pv / "team_matchups_2x.png")
        teams = json.loads((HERE / "teams.json").read_text())
        all_sheet = Image.new("RGB", (BAR_W * 2 + 32, (BAR_H * 2 + 8) * len(teams) + 8), FIELD_GREEN)
        for i, t in enumerate(teams):
            bar = compose_bar("2x", away=t["abbr"], home=t["abbr"], timeouts=True)
            canvas = Image.new("RGBA", bar.size, (0, 0, 0, 0))
            canvas.alpha_composite(bar)
            draw_text(canvas, {**state_no_mia, "away_abbreviation": t["abbr"], "home_abbreviation": t["abbr"]}, 2,
                      origin=(RAILS[0], RAILS[1]))
            all_sheet.paste(canvas.convert("RGB"), (16, 8 + i * (BAR_H * 2 + 8)), canvas)
        all_sheet.save(pv / "all_32_teams_2x.png")

    # zoom crops: the 1x bar (what the game actually samples) and one team block, nearest-neighbour
    bar1x = crop_rails(Image.open(HERE / "preview_640x480.png").convert("RGBA"), 1)
    bar1x.resize((bar1x.width * 3, bar1x.height * 3), Image.NEAREST).save(pv / "zoom_1x_bar_x3.png")
    if (HERE / "teams" / "1x" / "NO_away.png").exists():
        blk = Image.open(HERE / "teams" / "1x" / "NO_away.png").crop((104, 1, 222, 47))
        blk.resize((blk.width * 4, blk.height * 4), Image.NEAREST).save(pv / "zoom_NO_away_1x_x4.png")
    for stale in pv.glob("_zoom_*.png"):
        stale.unlink()

    atlas = build_atlas()
    palette_report(atlas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
