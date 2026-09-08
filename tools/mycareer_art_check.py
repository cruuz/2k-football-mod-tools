#!/usr/bin/env python3
"""Check the MyCareer apartment hub art against its native P8 constraints.

For every PNG in ``docs/mycareer_art`` that the asset request names, this tool
verifies the file (non-interlaced 8-bit RGBA PNG of the pinned size), the alpha
policy, the full mip chain (the same round-half-up RGBA box rule the Crib and
live-helmet importers use), the shared palette after quantization (the repo's
median cut over the whole chain, ``nfl_tset_png_import.median_cut_palette``,
with a 1,024-byte BGRA palette), the quantization error and a banding proxy,
and the layout rectangles from ``manifest.json``: crop safety for the
background, tile padding and alpha classes for the panel atlas, distinct icon
shapes for the calendar atlas, and a clear rim, a filled centre and
stretch-safe columns for the focus row.

Palette assignment uses a vectorised nearest-entry search with the same tie
rule as ``nfl_tset_png_import.quantize_levels`` (lowest index wins); pass
``--reference`` to run the pure-Python original instead. Both give identical
indices; the test proves it.

Exit status 0 means every asset passed. The JSON report lists each check.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import nfl_tset_png_import as palettes  # noqa: E402

DEFAULT_FOLDER = ROOT / "docs" / "mycareer_art"

# Native specification from ASTRA_MYCAREER_MODE_DESIGN.md, asset request list.
SPECS = {
    "mycareer_apartment.png": {"size": (512, 512), "mips": 7, "alpha": "opaque", "index_bytes": 349_504},
    "mycareer_panels.png": {"size": (256, 128), "mips": 5, "alpha": "mixed", "index_bytes": 43_648},
    "mycareer_calendar.png": {"size": (128, 128), "mips": 5, "alpha": "mixed", "index_bytes": 21_824},
    "mycareer_focus.png": {"size": (128, 32), "mips": 1, "alpha": "mixed", "index_bytes": 4_096},
}
PALETTE_LIMIT = 256
PALETTE_BYTES = 1_024

# Quality limits. Median cut over a 512 chain with grain lands well inside these;
# they are here so a future repaint that bands or posterises is caught.
MAX_CHANNEL_ERROR = 48          # hard cap on any single channel of any pixel in the chain
MAX_CHANNEL_ERROR_P995 = 24     # 99.5% of chain pixels stay within this per-channel error
MAX_RMS_ERROR = 6.0             # root mean square RGBA error over the whole chain
# Banding measure: luma of the original and of the P8 result, both box-blurred
# 7x7, compared inside the smooth regions the manifest names. A band is a
# plateau the blur cannot hide (a 20-level step reads as ~10 here); a gradient
# that quantizes with fine grain keeps its local means within a few levels.
MAX_LOWPASS_BANDING = 8.0
MAX_LOWPASS_BANDING_P99 = 6.0

# Calm-zone limits in texture space (4:3 mapping of the UI rectangles).
MENU_MAX_MEAN_LUMA = 96         # white text needs a dark, quiet ground
MENU_MAX_P99_LUMA = 170
MENU_MAX_MEAN_GRADIENT = 9.0    # the shaded night photo measures 8.1; the drawn room measured 2.6
SUMMARY_MAX_MEAN_GRADIENT = 16.0  # under an opaque card and tiles of at least 65% opacity
FOOTER_MAX_MEAN_LUMA = 110
FOOTER_MAX_MEAN_GRADIENT = 7.0

ICON_MAX_IOU = 0.80             # two icons whose masks overlap more than this share a shape
ICON_MIN_PIXELS = 60


class CheckError(ValueError):
    """A plain, actionable check failure."""


# ----------------------------------------------------------------------------- image io
def read_png(path: Path, size: tuple[int, int]):
    """Decode with the repo's strict PNG reader; also refuse interlaced files."""
    import numpy as np
    payload = path.read_bytes()
    if payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        raise CheckError(f"{path.name} is not a PNG")
    width, height, depth, colour, _comp, _filt, interlace = struct.unpack(">IIBBBBB", payload[16:29])
    if (width, height) != size:
        raise CheckError(f"{path.name} is {width}x{height}; the native slot is {size[0]}x{size[1]}")
    if interlace != 0:
        raise CheckError(f"{path.name} is interlaced; the writers take non-interlaced PNGs only")
    if depth != 8 or colour != 6:
        raise CheckError(f"{path.name} must be an 8-bit RGBA PNG (colour type 6), not depth {depth} type {colour}")
    w, h, rgba = palettes.decode_rgba_png(payload, size)
    return np.frombuffer(rgba, dtype=np.uint8).reshape(h, w, 4).copy(), payload


# ----------------------------------------------------------------------------- mips + palette
def box_mips(rgba, count: int):
    """Round-half-up RGBA box chain, identical to nfl2k5_crib._generate_mips."""
    import numpy as np
    levels = [palettes.MipLevel(0, rgba.shape[1], rgba.shape[0], rgba.tobytes())]
    current = rgba.astype(np.uint16)
    for level in range(1, count):
        h, w = current.shape[:2]
        if h % 2 or w % 2:
            raise CheckError(f"mip {level} cannot halve {w}x{h}")
        total = current[0::2, 0::2] + current[1::2, 0::2] + current[0::2, 1::2] + current[1::2, 1::2]
        current = (total + 2) // 4
        levels.append(palettes.MipLevel(level, w // 2, h // 2, current.astype(np.uint8).tobytes()))
    return levels


def nearest_indices(colors, palette):
    """Nearest palette entry per colour, squared RGBA distance, lowest index on ties."""
    import numpy as np
    pal = np.asarray(palette, dtype=np.int32)
    out = np.empty(len(colors), dtype=np.uint8)
    step = 4096
    for start in range(0, len(colors), step):
        block = np.asarray(colors[start:start + step], dtype=np.int32)
        d = ((block[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2)
        out[start:start + step] = np.argmin(d, axis=1)     # argmin returns the first minimum
    return out


def quantize_chain(levels, reference: bool = False):
    """Shared palette for the whole chain, the repo's way; returns (palette, indices, stats)."""
    if reference:
        palette, indices, _stats = palettes.quantize_levels(levels, PALETTE_LIMIT)
        return palette, indices, error_stats(levels, palette, indices)
    import numpy as np
    histogram: Counter = Counter()
    per_level = []
    for level in levels:
        arr = np.frombuffer(level.rgba, dtype=np.uint8).reshape(-1, 4)
        uniq, inverse, counts = np.unique(arr, axis=0, return_inverse=True, return_counts=True)
        per_level.append((uniq, inverse.reshape(-1)))
        histogram.update(dict(zip(map(tuple, uniq.tolist()), counts.tolist())))
    palette = palettes.median_cut_palette(histogram, PALETTE_LIMIT)
    colors = sorted(histogram)
    mapping = nearest_indices(colors, palette)
    lookup = {color: int(index) for color, index in zip(colors, mapping)}
    pal = np.asarray(palette, dtype=np.int32)
    indices = []
    for (uniq, inverse), level in zip(per_level, levels):
        uniq_idx = np.array([lookup[tuple(c)] for c in uniq.tolist()], dtype=np.uint8)
        indices.append(uniq_idx[inverse].tobytes())
    return palette, indices, error_stats(levels, palette, indices, len(histogram))


def error_stats(levels, palette, indices, unique_colors: int | None = None) -> dict:
    """Quantization error over the whole chain, the same keys as quantize_levels plus percentiles."""
    import numpy as np
    pal = np.asarray(palette, dtype=np.int32)
    total_sq = 0
    differing = 0
    total = 0
    channel_errors = []
    colors = set()
    for level, chunk in zip(levels, indices):
        arr = np.frombuffer(level.rgba, dtype=np.uint8).reshape(-1, 4).astype(np.int32)
        mapped = pal[np.frombuffer(chunk, dtype=np.uint8)]
        err = arr - mapped
        total_sq += int((err ** 2).sum())
        differing += int((err != 0).any(axis=1).sum())
        total += len(arr)
        channel_errors.append(np.abs(err).max(axis=1))
        if unique_colors is None:
            colors.update(map(tuple, np.unique(arr, axis=0).tolist()))
    worst = np.concatenate(channel_errors)
    return {
        "input_unique_rgba_colors": unique_colors if unique_colors is not None else len(colors),
        "palette_entries": len(palette),
        "total_squared_rgba_error": total_sq,
        "maximum_channel_error": int(worst.max()),
        "channel_error_p995": float(np.percentile(worst, 99.5)),
        "differing_pixel_count": differing,
        "total_pixel_count": total,
    }


def lowpass_banding(original, quantized):
    """Max and 99th percentile of |blur(luma q) - blur(luma o)| over a smooth region."""
    import numpy as np
    from PIL import Image, ImageFilter
    def blurred(arr):
        image = Image.fromarray(np.ascontiguousarray(arr[..., :3]), "RGB").convert("L")
        return np.asarray(image.filter(ImageFilter.BoxBlur(3)), dtype=np.float32)
    diff = np.abs(blurred(quantized) - blurred(original))
    return float(diff.max()), float(np.percentile(diff, 99))


# ----------------------------------------------------------------------------- per-asset checks
def luma(arr):
    return 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]


def mean_gradient(arr):
    import numpy as np
    y = luma(arr.astype(np.float32))
    gx = np.abs(np.diff(y, axis=1)).mean() if y.shape[1] > 1 else 0.0
    gy = np.abs(np.diff(y, axis=0)).mean() if y.shape[0] > 1 else 0.0
    return float((gx + gy) / 2)


def ui_rect_to_texture(rect):
    x0, y0, x1, y1 = rect
    return (round(x0 * 0.8), round(64 + y0 * 0.8), round(x1 * 0.8), round(64 + y1 * 0.8))


def inside(inner, outer) -> bool:
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def check_apartment(arr, manifest, results: dict, quantized0=None):
    import numpy as np
    h, w = arr.shape[:2]
    crop43 = tuple(manifest["crop_43"])
    wide = tuple(manifest["crop_wide"])
    expect = {"crop_43": (0, (h - 384) // 2, w, (h + 384) // 2), "crop_wide": (0, (h - 288) // 2, w, (h + 288) // 2)}
    if crop43 != expect["crop_43"] or wide != expect["crop_wide"]:
        raise CheckError(f"crops are not the centred 512x384 and 512x288 rectangles: {crop43} {wide}")
    if (arr[..., 3] != 255).any():
        raise CheckError("the background must be fully opaque")
    core = manifest["core_objects"]
    for name in core:
        rect = tuple(manifest["objects"][name])
        if not inside(rect, wide):
            raise CheckError(f"core object {name} {rect} leaves the wide crop {wide}")
        if not inside(rect, crop43):
            raise CheckError(f"core object {name} {rect} leaves the 4:3 crop {crop43}")
    results["core_objects_inside_crops"] = list(core)
    ui = manifest["ui"]
    menu = ui_rect_to_texture(ui["menu"])
    summary = ui_rect_to_texture(ui["summary"])
    footer = (crop43[0], round(64 + ui["footer_y"] * 0.8), crop43[2], crop43[3])
    zones = {}
    for name, rect, limits in (
        ("menu", menu, {"mean_luma": MENU_MAX_MEAN_LUMA, "p99_luma": MENU_MAX_P99_LUMA, "mean_gradient": MENU_MAX_MEAN_GRADIENT}),
        ("summary", summary, {"mean_gradient": SUMMARY_MAX_MEAN_GRADIENT}),
        ("footer", footer, {"mean_luma": FOOTER_MAX_MEAN_LUMA, "mean_gradient": FOOTER_MAX_MEAN_GRADIENT}),
    ):
        x0, y0, x1, y1 = rect
        region = arr[y0:y1, x0:x1, :3]
        y = luma(region.astype(np.float32))
        measured = {"rect": list(rect), "mean_luma": round(float(y.mean()), 1),
                    "p99_luma": round(float(np.percentile(y, 99)), 1),
                    "mean_gradient": round(mean_gradient(region), 2)}
        for key, limit in limits.items():
            if measured[key] > limit:
                raise CheckError(f"{name} zone {rect} is not calm enough: {key} {measured[key]} > {limit}")
        measured["limits"] = limits
        zones[name] = measured
    results["calm_zones"] = zones
    if quantized0 is not None:
        banding = {}
        for region, rect in manifest["smooth_rects"].items():
            sx0, sy0, sx1, sy1 = rect
            worst, p99 = lowpass_banding(arr[sy0:sy1, sx0:sx1], quantized0[sy0:sy1, sx0:sx1])
            banding[region] = {"rect": list(rect), "max": round(worst, 1), "p99": round(p99, 1)}
            if worst > MAX_LOWPASS_BANDING or p99 > MAX_LOWPASS_BANDING_P99:
                raise CheckError(f"the {region} bands after quantization: low-pass error max {worst:.1f}, p99 {p99:.1f} "
                                 f"(limits {MAX_LOWPASS_BANDING}, {MAX_LOWPASS_BANDING_P99})")
        banding["limits"] = {"max": MAX_LOWPASS_BANDING, "p99": MAX_LOWPASS_BANDING_P99}
        results["banding"] = banding


def check_panels(arr, manifest, results: dict):
    import numpy as np
    h, w = arr.shape[:2]
    tiles = manifest["panel_tiles"]
    covered = np.zeros((h, w), dtype=bool)
    rects = []
    for name, tile in tiles.items():
        x0, y0, x1, y1 = tile["rect"]
        if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
            raise CheckError(f"panel tile {name} {tile['rect']} leaves the atlas")
        for other, orect in rects:
            ox0, oy0, ox1, oy1 = orect
            gap_x = max(ox0 - x1, x0 - ox1)
            gap_y = max(oy0 - y1, y0 - oy1)
            if max(gap_x, gap_y) < 4:
                raise CheckError(f"panel tiles {name} and {other} are closer than 4 px")
        rects.append((name, (x0, y0, x1, y1)))
        covered[y0:y1, x0:x1] = True
        inset = int(tile["nine_slice_inset"])
        core = arr[y0 + inset:y1 - inset, x0 + inset:x1 - inset, 3]
        if core.size == 0:
            raise CheckError(f"panel tile {name} is smaller than twice its 9-slice inset")
        if tile["kind"] == "opaque":
            if (core != 255).any():
                raise CheckError(f"opaque panel tile {name} has translucent pixels inside its 9-slice core")
        elif tile["kind"] == "translucent":
            if core.min() < 96 or core.max() > 240:
                raise CheckError(f"translucent panel tile {name} alpha {core.min()}..{core.max()} leaves 96..240")
        else:
            raise CheckError(f"panel tile {name} has an unknown kind {tile['kind']}")
    if (arr[..., 3][~covered] != 0).any():
        raise CheckError("panel atlas has pixels outside its tiles; padding must stay transparent")
    results["tiles"] = {name: {"rect": list(rect)} for name, rect in rects}


def check_calendar(arr, manifest, results: dict):
    import numpy as np
    cell = int(manifest["calendar"]["cell"])
    icons = manifest["calendar"]["icons"]
    h, w = arr.shape[:2]
    covered = np.zeros((h, w), dtype=bool)
    masks = {}
    for name, rect in icons.items():
        x0, y0, x1, y1 = rect
        if (x1 - x0, y1 - y0) != (cell, cell) or x0 % cell or y0 % cell:
            raise CheckError(f"icon {name} {rect} is not on the {cell} px grid")
        mask = arr[y0:y1, x0:x1, 3] >= 128
        if mask.sum() < ICON_MIN_PIXELS:
            raise CheckError(f"icon {name} has only {int(mask.sum())} solid pixels")
        if mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any():
            raise CheckError(f"icon {name} touches its cell edge; keep a transparent margin")
        masks[name] = mask
        covered[y0:y1, x0:x1] = True
    if (arr[..., 3][~covered] != 0).any():
        raise CheckError("calendar atlas has pixels outside the declared icon cells")
    names = list(masks)
    worst = 0.0
    pairs = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            inter = (masks[a] & masks[b]).sum()
            union = (masks[a] | masks[b]).sum()
            iou = float(inter / union) if union else 0.0
            pairs[f"{a}/{b}"] = round(iou, 3)
            worst = max(worst, iou)
            if iou > ICON_MAX_IOU:
                raise CheckError(f"icons {a} and {b} share a shape (IoU {iou:.2f}); meaning must not be colour only")
    results["icons"] = names
    results["shape_iou"] = {"worst": round(worst, 3), "limit": ICON_MAX_IOU, "pairs": pairs}


def check_focus(arr, manifest, results: dict):
    import numpy as np
    h, w = arr.shape[:2]
    rim = int(manifest["focus"]["rim_px"])
    c0, c1 = manifest["focus"]["stretch_columns"]
    body = arr[:, c0:c1]
    if not (body == body[:, :1]).all():
        raise CheckError(f"focus columns {c0}..{c1} differ; the row must stretch without distortion")
    centre = arr[rim + 2:h - rim - 2, rim + 2:w - rim - 2]
    if (centre[..., 3] < 250).any():
        raise CheckError("focus centre fill is not solid")
    ring = np.concatenate([arr[:rim, c0:c1].reshape(-1, 4), arr[h - rim:, c0:c1].reshape(-1, 4)])
    rim_luma = float(luma(ring[:, :3].astype(np.float32)).mean())
    fill_luma = float(luma(centre[..., :3].astype(np.float32)).mean())
    if ring[:, 3].min() < 250:
        raise CheckError("focus rim is not solid")
    if rim_luma - fill_luma < 30:
        raise CheckError(f"focus rim (luma {rim_luma:.0f}) does not read against the fill ({fill_luma:.0f})")
    if (arr[..., 3] == 0).sum() == 0:
        raise CheckError("focus has no transparent corner pixels; give it a soft end")
    results["rim_luma"] = round(rim_luma, 1)
    results["fill_luma"] = round(fill_luma, 1)


# ----------------------------------------------------------------------------- driver
def check_asset(folder: Path, name: str, manifest: dict, *, reference: bool = False, preview_dir: Path | None = None) -> dict:
    import numpy as np
    spec = SPECS[name]
    path = folder / name
    arr, payload = read_png(path, spec["size"])
    result = {"file": name, "size": list(spec["size"]), "bytes": len(payload), "sha256": palettes.sha256_bytes(payload)}
    alpha = arr[..., 3]
    if spec["alpha"] == "opaque" and (alpha != 255).any():
        raise CheckError(f"{name} must be fully opaque")
    if spec["alpha"] == "mixed" and not ((alpha == 0).any() and (alpha == 255).any()):
        raise CheckError(f"{name} should carry both transparent and solid pixels")
    result["alpha"] = {"min": int(alpha.min()), "max": int(alpha.max()),
                       "distinct": int(len(np.unique(alpha)))}
    levels = box_mips(arr, spec["mips"])
    dims = [[level.width, level.height] for level in levels]
    index_bytes = sum(level.width * level.height for level in levels)
    if index_bytes != spec["index_bytes"]:
        raise CheckError(f"{name} mip chain holds {index_bytes} index bytes, the slot needs {spec['index_bytes']}")
    palette, indices, stats = quantize_chain(levels, reference=reference)
    if len(palette) > PALETTE_LIMIT:
        raise CheckError(f"{name} needs {len(palette)} palette entries")
    if len(palettes.palette_bytes(palette)) != PALETTE_BYTES:
        raise CheckError("palette bytes are not 1,024")
    if any(len(chunk) != level.width * level.height for chunk, level in zip(indices, levels)):
        raise CheckError("index chain lengths differ from the mip dimensions")
    rms = (stats["total_squared_rgba_error"] / max(1, stats["total_pixel_count"] * 4)) ** 0.5
    if stats["maximum_channel_error"] > MAX_CHANNEL_ERROR:
        raise CheckError(f"{name} quantizes with a channel error of {stats['maximum_channel_error']} (limit {MAX_CHANNEL_ERROR})")
    if stats["channel_error_p995"] > MAX_CHANNEL_ERROR_P995:
        raise CheckError(f"{name}: 0.5% of chain pixels exceed a channel error of {MAX_CHANNEL_ERROR_P995} "
                         f"(p99.5 is {stats['channel_error_p995']:.1f})")
    if rms > MAX_RMS_ERROR:
        raise CheckError(f"{name} quantizes with an RMS error of {rms:.2f} (limit {MAX_RMS_ERROR})")
    result["mips"] = {"count": len(levels), "dimensions": dims, "index_bytes": index_bytes}
    result["palette"] = {"entries": len(palette), "limit": PALETTE_LIMIT, "palette_bytes": PALETTE_BYTES,
                         "input_unique_rgba_colors": stats["input_unique_rgba_colors"],
                         "maximum_channel_error": stats["maximum_channel_error"],
                         "channel_error_p995": stats["channel_error_p995"],
                         "rms_rgba_error": round(rms, 3),
                         "differing_pixel_count": stats["differing_pixel_count"],
                         "total_pixel_count": stats["total_pixel_count"],
                         "mapping": "reference quantize_levels" if reference else "median_cut_palette + vectorised nearest"}
    pal = np.asarray(palette, dtype=np.uint8)
    quantized0 = pal[np.frombuffer(indices[0], dtype=np.uint8)].reshape(arr.shape)
    if preview_dir is not None:
        write_previews(preview_dir, name, levels, indices, pal)
    if name == "mycareer_apartment.png":
        check_apartment(arr, manifest, result, quantized0)
    elif name == "mycareer_panels.png":
        check_panels(arr, manifest, result)
    elif name == "mycareer_calendar.png":
        check_calendar(arr, manifest, result)
    elif name == "mycareer_focus.png":
        check_focus(arr, manifest, result)
    result["ok"] = True
    return result


def write_previews(preview_dir: Path, name: str, levels, indices, pal) -> None:
    """The P8 result at mip 0 and the whole chain side by side, for eyes."""
    import numpy as np
    from PIL import Image
    preview_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(name).stem
    images = []
    for level, chunk in zip(levels, indices):
        rgba = pal[np.frombuffer(chunk, dtype=np.uint8)].reshape(level.height, level.width, 4)
        images.append(Image.fromarray(rgba, "RGBA"))
    images[0].save(preview_dir / f"preview_p8_{stem}.png", optimize=True)
    width = sum(im.width for im in images) + 4 * (len(images) - 1)
    strip = Image.new("RGBA", (width, images[0].height), (0, 0, 0, 0))
    x = 0
    for im in images:
        strip.paste(im, (x, 0))
        x += im.width + 4
    strip.save(preview_dir / f"preview_mips_{stem}.png", optimize=True)


def check_folder(folder: Path | None = None, *, reference: bool = False, preview_dir: Path | None = None) -> dict:
    root = Path(folder).expanduser().resolve() if folder else DEFAULT_FOLDER
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise CheckError(f"{manifest_path} is missing; run docs/mycareer_art/build.py")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "mycareer_art/v1":
        raise CheckError("manifest.json is not a mycareer_art/v1 manifest")
    try:
        shown = root.relative_to(ROOT).as_posix()
    except ValueError:
        shown = str(root)
    report = {"folder": shown, "assets": [], "ok": True}
    for name in SPECS:
        try:
            report["assets"].append(check_asset(root, name, manifest, reference=reference, preview_dir=preview_dir))
        except CheckError as exc:
            report["assets"].append({"file": name, "ok": False, "error": str(exc)})
            report["ok"] = False
        except FileNotFoundError:
            report["assets"].append({"file": name, "ok": False, "error": f"{name} is missing"})
            report["ok"] = False
    for mock, size in (("hub_mockup_640x480.png", (640, 480)), ("hub_mockup_wide.png", (854, 480))):
        path = root / mock
        try:
            from PIL import Image
            with Image.open(path) as im:
                ok = im.size == size
            report["assets"].append({"file": mock, "ok": ok, "size": list(size)})
            report["ok"] = report["ok"] and ok
        except (OSError, ValueError) as exc:
            report["assets"].append({"file": mock, "ok": False, "error": str(exc)})
            report["ok"] = False
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folder", nargs="?", default=None, help="art folder (default docs/mycareer_art)")
    parser.add_argument("--reference", action="store_true", help="use the pure-Python quantize_levels mapping")
    parser.add_argument("--preview-dir", type=Path, default=None, help="write P8 and mip-chain previews here")
    parser.add_argument("--json", type=Path, default=None, help="write the report to this path")
    args = parser.parse_args(argv)
    report = check_folder(args.folder, reference=args.reference, preview_dir=args.preview_dir)
    text = json.dumps(report, indent=2) + "\n"
    if args.json:
        args.json.write_bytes(text.encode("utf-8"))
    sys.stdout.write(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
