#!/usr/bin/env python3
"""b780 art1: the old 2004 logo left around the new 2026 logo on the SOFTDRINK Team Select helmet cards, cleaned at
the source PNGs (Noah 2026-11-03: "any team helmet and logo on team select that shows the old logo still visible
underneath the new logo, that needs cleaned up to match the background color of the helmet, so only the new logo
shows").

The SOFTDRINK league project's Team Select cards (``team_select`` edits: ``helm`` 256 and 128, ``unif`` 256) are
Blender renders of the 2026 helmet art (job k2, cards v5). Where the helmet texture still carried pieces of the
retail decal that the 2026 logo does not cover (Detroit's old lion head, tail, front leg and hind paws, Baltimore's
old raven outline tips, Arizona's old crest tip beside the vent, the Jets' old oval top on the white throwback,
Washington's old feather, feather tips and dark red roundel ring), the renders show them next to the new logo. This step repaints only those pieces, card by card, from the hand masks in
``data/nfl2k5_team_select_old_logo_cleanup.json``:

1. every region is a polygon in card pixels drawn around one old-logo piece, clear of the new logo;
2. the helmet's own colour under the region is rebuilt from the clean shell just outside it: the pixels of a 2-pixel
   band around the polygon are fitted with a plane per channel (the shell's local shading; ``shell_box`` names a box
   of clean shell to fit instead, where the band is mostly a strap or the card's bar), band pixels that do not fit
   (the new logo, a vent, a strap) are dropped, and the region is filled by harmonic interpolation from the
   remaining band pixels, so the shading and gradient carry on underneath;
3. ``"mode": "all"`` (most regions) repaints the whole polygon with that rebuilt shell; ``"mode": "deviation"``
   repaints only the pixels that differ from it by more than the region's threshold (``"sign": "darker"`` or
   ``"lighter"`` limits it to one direction, so a highlight next to a dark piece stays; ``"redder"`` takes only the
   pixels redder than the shell (red, not gold), for a red piece on a neutral shell; ``"estimate": "local"`` rebuilds the shell from
   a blur of its own pixels instead, which keeps the helmet's highlights under a thin piece), plus ``grow`` pixels
   of anti-aliased fringe; ``inset`` keeps a region that many pixels inside the helmet's outline (its piping);
   alpha never changes and only opaque pixels are painted;
4. the 128 helm card is the premultiplied 2 x 2 box reduction of the 256 card (measured: within 1.6 levels on every
   card), so its blocks that cover a repainted 256 pixel take the box of the cleaned 256 card plus the original 128
   residual; every other 128 pixel stays as it was.

Every input card is pinned (RGBA SHA-256 of the source PNG) and so is every output; a card that is not the known art
is refused, so user or older art is never touched. All arithmetic is float64 with a fixed iteration count and round
half up, so the result is the same on every platform. Encoding is not this step's: outside the regions the cleaned
card is the source art byte for byte, and the importer's re-quantized card stays as close to it as the RC1 card did.

  python3 tools/b780_team_select_old_logo_cleanup.py apply --project PROJECT.json --out-dir DIR --project-out NEW.json
  python3 tools/b780_team_select_old_logo_cleanup.py check --project PROJECT.json

``apply`` writes the cleaned PNGs (same file names, in DIR) and a copy of the project whose ``team_select`` edits
point at them; nothing else in the project changes. The Studio's own Team Select importer then quantizes the cleaned
PNGs exactly as before (256-entry median cut, the retail P8 slot, wrapper and size unchanged). Washington's 29_0
cards are then repainted by the Studio's hu1 W pass (nfl2k5_menu_helmet_w2026), which knows the cleaned cards as a
second pinned pair (``also``) next to the art it was first pinned to.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/nfl2k5_team_select_old_logo_cleanup.json"
SCHEMA = "nfl2k5_team_select_old_logo_cleanup/v1"
BAND = 2                 # pixels of shell around a region that the fill is built from
OPAQUE = 250             # only pixels at or above this alpha are painted or used as shell
FIT_TOLERANCE = 14.0     # band pixels further than this from the fitted shading plane are not shell
JACOBI = 1500            # harmonic smoothing sweeps after the outside-in start


class CleanupError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise CleanupError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def spec(path=None) -> dict:
    doc = json.loads(Path(path or DATA).read_text(encoding="utf-8"))
    require(doc.get("schema") == SCHEMA, "unknown Team Select cleanup document")
    return doc


# ----------------------------------------------------------------------------------------------- image helpers
def load_rgba(path) -> np.ndarray:
    from PIL import Image
    with Image.open(path) as image:
        require(image.mode == "RGBA", f"{path}: expected an RGBA PNG")
        return np.asarray(image, dtype=np.uint8).copy()


def save_rgba(array: np.ndarray, path) -> None:
    from PIL import Image
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.ascontiguousarray(array, dtype=np.uint8), "RGBA").save(path, optimize=False, compress_level=9)


def rgba_sha(array: np.ndarray) -> str:
    return sha(np.ascontiguousarray(array, dtype=np.uint8).tobytes())


def polygon_mask(shape, poly) -> np.ndarray:
    """Pixels whose centre is inside the polygon (even-odd rule), card pixel coordinates."""
    h, w = shape
    ys, xs = np.mgrid[0:h, 0:w]
    px, py = xs + 0.5, ys + 0.5
    inside = np.zeros((h, w), bool)
    pts = [(float(x), float(y)) for x, y in poly]
    require(len(pts) >= 3, "a region polygon needs three points")
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        if ay == by:
            continue
        crosses = (ay > py) != (by > py)
        x_at = ax + (py - ay) * (bx - ax) / (by - ay)
        inside ^= crosses & (px < x_at)
    return inside


def shifted(array, dy, dx, fill=0):
    """``array`` moved by (dy, dx); vacated cells take ``fill``."""
    out = np.full_like(array, fill)
    h, w = array.shape[:2]
    ys = slice(max(dy, 0), h + min(dy, 0)), slice(max(-dy, 0), h + min(-dy, 0))
    xs = slice(max(dx, 0), w + min(dx, 0)), slice(max(-dx, 0), w + min(-dx, 0))
    out[ys[0], xs[0]] = array[ys[1], xs[1]]
    return out


NEIGHBOURS8 = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
NEIGHBOURS4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def dilate(mask, steps=1) -> np.ndarray:
    out = mask.copy()
    for _ in range(steps):
        grown = out.copy()
        for dy, dx in NEIGHBOURS8:
            grown |= shifted(out, dy, dx, False)
        out = grown
    return out


def harmonic_fill(rgb: np.ndarray, unknown: np.ndarray, known: np.ndarray) -> np.ndarray:
    """Fill ``unknown`` from ``known`` (float64 RGB): outside-in neighbour means, then fixed Jacobi sweeps of the
    4-neighbour Laplace equation (known pixels fixed; neighbours that are neither are left out)."""
    out = rgb.copy()
    if not unknown.any():
        return out
    require(known.any(), "a region has no shell around it to fill from")
    ys, xs = np.nonzero(unknown | known)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sub = out[y0:y1, x0:x1].copy()
    u, k = unknown[y0:y1, x0:x1], known[y0:y1, x0:x1] & ~unknown[y0:y1, x0:x1]
    have, todo = k.copy(), u.copy()
    while todo.any():
        total = np.zeros(sub.shape, np.float64)
        count = np.zeros(sub.shape[:2], np.float64)
        for dy, dx in NEIGHBOURS8:
            ok = shifted(have, dy, dx, False)
            total += np.where(ok[..., None], shifted(sub, dy, dx, 0.0), 0.0)
            count += ok
        ready = todo & (count > 0)
        if not ready.any():
            # pixels cut off from the shell (enclosed by the logo or the piping) take the shell's median colour
            sub[todo] = np.median(sub[k], axis=0)
            break
        sub[ready] = total[ready] / count[ready][:, None]
        have |= ready
        todo &= ~ready
    valid = u | k
    for _ in range(JACOBI):
        total = np.zeros(sub.shape, np.float64)
        count = np.zeros(sub.shape[:2], np.float64)
        for dy, dx in NEIGHBOURS4:
            ok = shifted(valid, dy, dx, False)
            total += np.where(ok[..., None], shifted(sub, dy, dx, 0.0), 0.0)
            count += ok
        new = total / np.maximum(count, 1.0)[..., None]
        sub[u] = new[u]
    out[y0:y1, x0:x1] = sub
    return out


def shell_band(rgb: np.ndarray, band: np.ndarray, reference: np.ndarray | None = None) -> np.ndarray:
    """The band pixels that are helmet shell: a plane per channel (the local shading) is fitted by least squares to
    the band pixels nearest the band's median colour (or, with ``reference``, to those clean shell pixels: a region
    whose band is mostly a strap line or the card's bar names a box of shell beside it), refitted to every band pixel
    within FIT_TOLERANCE of it until it settles; the pixels it explains are kept, the rest (the new logo, a vent, a
    strap) are not shell."""
    ys, xs = np.nonzero(band)
    require(len(ys) >= 6, "a region's shell band is too small")
    keep = np.zeros_like(band)
    if reference is not None:
        ry, rx = np.nonzero(reference)
        require(len(ry) >= 6, "a region's shell reference is too small")
        a = np.stack([np.ones(len(ry)), rx.astype(np.float64), ry.astype(np.float64)], axis=1)
        coef, *_ = np.linalg.lstsq(a, rgb[ry, rx], rcond=None)
        full = np.stack([np.ones(len(ys)), xs.astype(np.float64), ys.astype(np.float64)], axis=1) @ coef
        keep[ys, xs] = np.abs(rgb[ys, xs] - full).max(axis=1) <= FIT_TOLERANCE
        require(keep.sum() >= 6, "a region's shell band has no pixel like its shell reference")
        return keep
    values = rgb[ys, xs]
    distance = np.abs(values - np.median(values, axis=0)).max(axis=1)
    keep[ys, xs] = distance <= max(30.0, float(np.sort(distance)[len(distance) // 2]))
    for _ in range(8):
        sel = keep[ys, xs]
        if sel.sum() < 6:
            break
        a = np.stack([np.ones(int(sel.sum())), xs[sel].astype(np.float64), ys[sel].astype(np.float64)], axis=1)
        coef, *_ = np.linalg.lstsq(a, rgb[ys[sel], xs[sel]], rcond=None)
        full = np.stack([np.ones(len(ys)), xs.astype(np.float64), ys.astype(np.float64)], axis=1) @ coef
        resid = np.abs(rgb[ys, xs] - full).max(axis=1)
        new = np.zeros_like(keep)
        new[ys, xs] = resid <= FIT_TOLERANCE
        if (new == keep).all():
            break
        keep = new
    require(keep.sum() >= 6, "a region's shell band has no clean shell")
    return keep


def round_half_up(values: np.ndarray) -> np.ndarray:
    return np.clip(np.floor(values + 0.5), 0, 255).astype(np.uint8)


KERNEL = np.array([1, 12, 66, 220, 495, 792, 924, 792, 495, 220, 66, 12, 1], np.float64) / 4096.0  # binomial 12


def blur(values: np.ndarray) -> np.ndarray:
    """Separable binomial blur (13 taps, sigma about 1.7), zero outside the array."""
    out = values.astype(np.float64)
    r = len(KERNEL) // 2
    for axis in (0, 1):
        padded = np.pad(out, [(r, r) if a == axis else (0, 0) for a in range(out.ndim)])
        acc = np.zeros_like(out)
        for i, weight in enumerate(KERNEL):
            index = [slice(None)] * out.ndim
            index[axis] = slice(i, i + out.shape[axis])
            acc += weight * padded[tuple(index)]
        out = acc
    return out


def local_shell(rgb: np.ndarray, support: np.ndarray, threshold: float, sign: str) -> np.ndarray:
    """Pixels of ``support`` that are shell: a normalized blur of the shell pixels (which keeps the helmet's broad
    shading, highlights and reflections) is compared with every pixel, the ones that stand out are dropped and the
    blur is redone, four times."""
    keep = support.copy()
    for _ in range(4):
        weight = blur(keep.astype(np.float64))
        estimate = blur(np.where(keep[..., None], rgb, 0.0)) / np.maximum(weight, 1e-9)[..., None]
        deviation = signed_deviation(rgb - estimate, sign)
        new = support & ((deviation <= threshold) | (weight < 1e-6))
        if (new == keep).all():
            break
        keep = new
    return keep


def redness(rgb: np.ndarray) -> np.ndarray:
    """How much a pixel is red rather than neutral or gold: red over green and blue, less their own difference
    (gold and yellow, green well above blue, come out negative)."""
    return rgb[..., 0] - np.maximum(rgb[..., 1], rgb[..., 2]) - np.abs(rgb[..., 1] - rgb[..., 2])


def signed_deviation(difference: np.ndarray, sign: str) -> np.ndarray:
    require(sign in ("any", "darker", "lighter", "redder"), f"unknown region sign {sign!r}")
    if sign == "redder":
        return difference[..., 0]
    if sign == "darker":
        return (-difference).max(axis=2)
    if sign == "lighter":
        return difference.max(axis=2)
    return np.abs(difference).max(axis=2)


def clean_regions(rgba: np.ndarray, regions) -> tuple[np.ndarray, list[dict]]:
    """Repaint each region of one card; returns the new RGBA and a receipt row per region."""
    out = rgba.copy()
    h, w = rgba.shape[:2]
    opaque = rgba[..., 3] >= OPAQUE
    rows = []
    for number, region in enumerate(regions):
        rgb = out[..., :3].astype(np.float64)
        area = polygon_mask((h, w), region["poly"]) & opaque
        if region.get("inset"):
            # keep clear of the helmet's outline (its piping) by ``inset`` pixels from the card's transparent edge
            area &= ~dilate(~opaque, int(region["inset"]))
        require(area.any(), f"region {number} covers no opaque pixel")
        band = dilate(area, BAND) & ~area & opaque
        reference = None
        if "shell_box" in region:
            x0, y0, x1, y1 = (int(v) for v in region["shell_box"])
            reference = np.zeros((h, w), bool)
            reference[y0:y1, x0:x1] = True
            reference &= opaque & ~area
        shell = shell_band(rgb, band, reference)
        mode = region.get("mode", "deviation")
        if mode == "all":
            paint = area
        else:
            require(mode == "deviation", f"unknown region mode {mode!r}")
            sign = region.get("sign", "any")
            threshold = float(region.get("threshold", 12))
            if region.get("estimate", "harmonic") == "local":
                # thin pieces over shaded shell: the shell estimate follows the helmet's own highlights
                paint = area & ~local_shell(rgb, area | shell, threshold, sign)
            elif sign == "redder":
                # a red piece on a neutral shell (Washington's old roundel ring on the black helmet): the excess of
                # red over green and blue, against the same excess of the rebuilt shell
                require(region.get("estimate", "harmonic") == "harmonic", "a redder region uses the harmonic estimate")
                estimate = harmonic_fill(rgb, area, shell)
                paint = area & ((redness(rgb) - redness(estimate)) > threshold)
            else:
                require(region.get("estimate", "harmonic") == "harmonic", "unknown region estimate")
                estimate = harmonic_fill(rgb, area, shell)
                paint = area & (signed_deviation(rgb - estimate, sign) > threshold)
            paint = dilate(paint, int(region.get("grow", 1))) & area
        keep = (area | band) & ~paint
        keep &= ~band | shell
        if mode != "all" and region.get("sign") == "redder":
            # the gold piping and logo outline beside a red piece are not shell to fill it from
            keep &= (np.minimum(rgb[..., 0], rgb[..., 1]) - rgb[..., 2]) <= 40
        filled = harmonic_fill(rgb, paint, keep)
        out[paint, :3] = round_half_up(filled[paint])
        rows.append(dict(region=number, note=region.get("note", ""), area_pixels=int(area.sum()),
                         painted_pixels=int(paint.sum()), shell_band_pixels=int(shell.sum())))
    return out, rows


def box_reduce(rgba: np.ndarray) -> np.ndarray:
    """Premultiplied 2 x 2 box reduction, float64 RGBA 0..255 (the 128 helm card is made this way from the 256)."""
    a = rgba.astype(np.float64)
    pre = a.copy()
    pre[..., :3] *= a[..., 3:4] / 255.0
    h, w = a.shape[:2]
    pre = pre.reshape(h // 2, 2, w // 2, 2, 4).mean(axis=(1, 3))
    alpha = pre[..., 3:4]
    pre[..., :3] = np.where(alpha > 0, pre[..., :3] * 255.0 / np.maximum(alpha, 1e-9), 0.0)
    return pre


def derive_half(old_small: np.ndarray, old_big: np.ndarray, new_big: np.ndarray) -> np.ndarray:
    """The 128 card after the 256 card changed: blocks that hold a repainted 256 pixel take the box of the new 256
    card plus the old 128 card's own residual from the box of the old 256 card; all other pixels stay."""
    require(old_big.shape[0] == 2 * old_small.shape[0] and old_big.shape[1] == 2 * old_small.shape[1],
            "the small card is not half the big card")
    changed = (old_big != new_big).any(axis=2)
    h, w = old_small.shape[:2]
    blocks = changed.reshape(h, 2, w, 2).any(axis=(1, 3))
    out = old_small.copy()
    if blocks.any():
        moved = old_small.astype(np.float64) + box_reduce(new_big) - box_reduce(old_big)
        moved[..., 3] = old_small[..., 3]
        out[blocks] = round_half_up(moved[blocks])
    return out


# ----------------------------------------------------------------------------------------------- the document
def card_regions(doc: dict) -> dict:
    """{card name: [regions]} for every 256 card the document cleans (helm_h09_0_256, unif_a02_3_256, ...)."""
    out: dict[str, list] = {}
    for group in doc["groups"]:
        family, side = group["card"].split("_")[:2]
        require(family in ("helm", "unif") and side in ("h", "a") and group["card"].endswith("_256"),
                f"unknown card {group['card']!r}")
        for style in group["styles"]:
            name = f"{family}_{side}{group['code']}_{int(style)}_256"
            out.setdefault(name, []).extend(group["regions"])
    return out


def derived_cards(doc: dict) -> dict:
    """{128 card name: its 256 card name} for the helm cards the document cleans."""
    return {name.replace("_256", "_128"): name for name in card_regions(doc) if name.startswith("helm_")}


def edit_name(edit: dict) -> str:
    side = "h" if edit["side"] == "home" else "a"
    return f"{edit['family']}_{side}{edit['asset_code']}_{int(edit['style'])}_{int(edit['resolution'])}"


def clean_project_cards(project: dict, doc: dict | None = None) -> tuple[dict, dict]:
    """{card name: cleaned RGBA} and {card name: receipt} for the project's cards that the document names.
    Refuses a card whose source is not the pinned art."""
    doc = doc or spec()
    regions = card_regions(doc)
    halves = derived_cards(doc)
    pins = doc["cards"]
    edits = {edit_name(e): e for e in project["edits"] if e.get("kind") == "team_select"}
    missing = sorted((set(regions) | set(halves)) - set(edits))
    require(not missing, f"the project has no Team Select edit for {missing}")
    images, receipts = {}, {}
    for name, rows in sorted(regions.items()):
        before = load_rgba(edits[name]["png"])
        require(rgba_sha(before) == pins[name]["source_rgba_sha256"], f"{name}: the source is not the known art")
        after, region_rows = clean_regions(before, rows)
        images[name] = after
        receipts[name] = dict(source=edits[name]["png"], source_rgba_sha256=rgba_sha(before),
                              clean_rgba_sha256=rgba_sha(after),
                              changed_pixels=int((before != after).any(axis=2).sum()), regions=region_rows)
    for small, big in sorted(halves.items()):
        before = load_rgba(edits[small]["png"])
        require(rgba_sha(before) == pins[small]["source_rgba_sha256"], f"{small}: the source is not the known art")
        after = derive_half(before, load_rgba(edits[big]["png"]), images[big])
        images[small] = after
        receipts[small] = dict(source=edits[small]["png"], source_rgba_sha256=rgba_sha(before),
                               clean_rgba_sha256=rgba_sha(after), derived_from=big,
                               changed_pixels=int((before != after).any(axis=2).sum()))
    for name, receipt in receipts.items():
        require(receipt["clean_rgba_sha256"] == pins[name]["clean_rgba_sha256"], f"{name}: the result differs from its pin")
        require(receipt["changed_pixels"] > 0, f"{name}: nothing was cleaned")
    return images, receipts


def cmd_apply(args) -> int:
    project_path = Path(args.project)
    project = json.loads(project_path.read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    images, receipts = clean_project_cards(project, spec(args.data) if args.data else None)
    by_source = {}
    for name, image in images.items():
        source = Path(receipts[name]["source"])
        target = out_dir / source.name
        require(target.resolve() != source.resolve(), "the cleaned PNG would overwrite its source")
        if source in by_source:
            require(rgba_sha(image) == rgba_sha(images[by_source[source]]), f"{source} is cleaned two ways")
            continue
        save_rgba(image, target)
        require(rgba_sha(load_rgba(target)) == receipts[name]["clean_rgba_sha256"], f"{target} read-back differs")
        by_source[source] = name
        receipts[name]["output"] = str(target)
        receipts[name]["output_file_sha256"] = sha(target.read_bytes())
    replaced = 0
    for edit in project["edits"]:
        if edit.get("kind") == "team_select" and Path(edit["png"]) in by_source:
            edit["png"] = str(out_dir / Path(edit["png"]).name)
            replaced += 1
    # the league project's own layout (indent 2, sorted keys), so the copy differs from it only in the repointed lines
    Path(args.project_out).write_text(json.dumps(project, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    receipt = dict(schema=SCHEMA + "/receipt", project=str(project_path), project_sha256=sha(project_path.read_bytes()),
                   project_out=str(args.project_out), project_out_sha256=sha(Path(args.project_out).read_bytes()),
                   edits_repointed=replaced, cards=receipts)
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(dict(cards=len(images), files=len(by_source), edits_repointed=replaced)))
    return 0


def cmd_check(args) -> int:
    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    images, receipts = clean_project_cards(project, spec(args.data) if args.data else None)
    print(json.dumps({name: dict(changed_pixels=r["changed_pixels"], clean_rgba_sha256=r["clean_rgba_sha256"])
                      for name, r in sorted(receipts.items())}, indent=1))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 tools/b780_team_select_old_logo_cleanup.py")
    sub = parser.add_subparsers(dest="command", required=True)
    ap = sub.add_parser("apply", help="write the cleaned cards and a project that uses them")
    ap.add_argument("--project", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--project-out", required=True)
    ap.add_argument("--receipt")
    ap.add_argument("--data")
    ck = sub.add_parser("check", help="clean in memory and compare every card with its pin")
    ck.add_argument("--project", required=True)
    ck.add_argument("--data")
    args = parser.parse_args(argv)
    return cmd_apply(args) if args.command == "apply" else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
