#!/usr/bin/env python3
"""Build sourced ten-digit art into pinned, fixed-span uniform replacements.

The team spec is the reproducible source. The actual-disc export is read only;
the existing safe writer provides mip/descriptor/readback and size gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import numpy as np
from PIL import Image
import nfl2k5_team_2026_art as art
from nfl_live_numbers_nameplate_png_import import build_import
from tools.b765.u1_repair import apply_spans, publish_batch

FAMILY_BLOCKS = {
    "jersey_digit": ("digits", "digit_jersey"),
    "helmet_digit": ("helmet_digits", "digit_helmet"),
    "arm_digit": ("arm_digits", "digit_arm"),
}
DEFAULT_FAMILIES = ("jersey_digit", "helmet_digit")


def selected_blocks(kit: dict, families: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """Validate only explicitly owned families; preserve all other artwork."""
    if not families or len(set(families)) != len(families) or set(families) - FAMILY_BLOCKS.keys():
        raise ValueError("select unique jersey_digit, helmet_digit and/or arm_digit families")
    selected = []
    for family in families:
        block_key, prefix = FAMILY_BLOCKS[family]
        if family == "arm_digit" and kit.get(block_key) == "none":
            continue
        validate_family(kit[block_key])
        selected.append((block_key, prefix, family))
    return selected


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_family(block: dict) -> None:
    """Refuse incomplete families and coordinates that would clip or drift."""
    shapes = block.get("glyph_shapes")
    if not isinstance(shapes, dict) or set(shapes) != set(map(str, range(10))):
        raise ValueError("a sourced family must contain exactly digits 0..9")
    if block.get("font") or block.get("registration") != "as_authored":
        raise ValueError("sourced shapes require as_authored registration and no font file")
    center = block.get("glyph_center", [])
    height = block.get("glyph_height", 0)
    if len(center) != 2 or not all(math.isfinite(float(v)) for v in [height, *center]) or height <= 0:
        raise ValueError("invalid family height/centre")
    for digit, shape in shapes.items():
        width, units = float(shape["width"]), float(shape["height"])
        if not (0 < width <= units * 2 and units > 0):
            raise ValueError(f"invalid digit {digit} dimensions")
        if not shape.get("contours"):
            raise ValueError(f"empty digit {digit}")
        for contour in shape["contours"] + shape.get("holes", []):
            if len(contour) < 3:
                raise ValueError(f"short digit {digit} contour")
            for point in contour:
                if len(point) != 2 or not all(math.isfinite(float(v)) for v in point):
                    raise ValueError(f"invalid digit {digit} point")
                if not (0 <= point[0] <= width + .001 and 0 <= point[1] <= units + .001):
                    raise ValueError(f"digit {digit} coordinates exceed declared bounds")


def ink_bounds(png: Path) -> list[int]:
    with Image.open(png) as im:
        alpha = np.asarray(im.convert("RGBA"))[:, :, 3]
    ys, xs = np.nonzero(alpha >= 128)
    if not len(ys):
        raise ValueError(f"empty decoded digit: {png}")
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def build(spec_path: Path, baseline_path: Path, out: Path, index: Path, compatibility: Path,
          families: tuple[str, ...] = DEFAULT_FAMILIES) -> dict:
    spec = art.Spec(spec_path)
    blocks = {name: selected_blocks(kit, families) for name, kit in spec.data["kits"].items()}
    baseline = json.loads(baseline_path.read_text())
    if baseline.get("schema") != "b765/u1/actual-kit-export/v1":
        raise ValueError("unexpected actual-disc export schema")
    sets = {item["selector"]: item for item in baseline["sets"]}
    out = out.absolute()
    edits, resources, measurements, receipts = [], {}, [], {}
    for kit_name, kit in spec.data["kits"].items():
        selector = kit["selector"]
        before = sets[selector]
        resource = Path(before["resource_path"]).read_bytes()
        if len(resource) != before["resource_size"] or sha(resource) != before["resource_sha256"]:
            raise ValueError(f"actual-disc resource changed: {selector}")
        patches = []
        assets = {Path(a["png"]).stem: a for a in before["assets"]}
        for block_key, prefix, family in blocks[kit_name]:
            block = kit[block_key]
            for digit in range(10):
                name = f"{prefix}_{digit}"
                asset = assets[name]
                donor_root = Path(before["art"]).parent
                master = art.author_glyphs(spec, kit, donor_root, name, block_key)
                png = out / "retail" / selector / f"{name}.png"
                art.save(master, out / "master4x" / selector / f"{name}.png", digit_registration="as_authored")
                art.save(art.downscale(master), png, digit_registration="as_authored")
                span, preview, report = build_import(index, compatibility, family,
                    spec.data["asset_code"], selector[2], int(selector[3:]), digit, png)
                target = report["target"]
                if target["chunk_offset"] != asset["offset"] or len(span) != asset["length"]:
                    raise ValueError(f"stored target span disagrees with actual disc: {selector}/{name}")
                old = resource[asset["offset"]:asset["offset"] + asset["length"]]
                if sha(old) != asset["span_sha256"]:
                    raise ValueError(f"actual-disc span changed: {selector}/{name}")
                stem = f"{selector}_{name}"
                publish_batch([(out / "spans" / f"{stem}.bin", span),
                               (out / "readback" / selector / f"{name}.png", preview),
                               (out / "imports" / f"{stem}.json", (json.dumps(report, indent=2) + "\n").encode())])
                patches.append({"offset": asset["offset"], "length": len(span),
                    "before_sha256": sha(old), "after_sha256": sha(span),
                    "replacement": f"spans/{stem}.bin"})
                edits.append({"kind": "live_number_nameplate", "family": family,
                    "asset_code": spec.data["asset_code"], "side": selector[2],
                    "variant": int(selector[3:]), "digit": digit, "png": str(png)})
                a = np.asarray(Image.open(asset["png"]).convert("RGBA"))
                b = np.asarray(Image.open(out / "readback" / selector / f"{name}.png").convert("RGBA"))
                measurements.append({"selector": selector, "family": family, "digit": digit,
                    "before": asset["png"], "authored": str(png),
                    "readback": str(out / "readback" / selector / f"{name}.png"),
                    "before_bounds": ink_bounds(Path(asset["png"])),
                    "authored_bounds": ink_bounds(png),
                    "readback_bounds": ink_bounds(out / "readback" / selector / f"{name}.png"),
                    "changed_pixels": int(np.any(a != b, axis=2).sum()),
                    "decoded_sha256": report["replacement"]["decoded_sha256"]})
                print(f"compiled {selector} {name}", flush=True)
        fixed, receipt = apply_spans(resource, patches, out)
        repeated, second = apply_spans(fixed, patches, out)
        if repeated != fixed or not all(s["already_applied"] for s in second["spans"]):
            raise ValueError("repair idempotence failed")
        receipt["idempotent"] = True
        publish_batch([(out / "resources" / f"{selector}.IFF", fixed)])
        resources[f"{selector}.IFF"] = patches
        receipts[selector] = receipt
    artifacts = {
        "project.json": {"schema": "nfl2k5_visual_mod_project/v1", "name": f"u1 {spec.data['team']} sourced numerals", "edits": edits},
        "repair_manifest.json": {"schema": "b765/u1/texture-repair/v1", "resources": resources},
        "font_receipts.json": {"schema": "b765/u1/fonts/v1", "team": spec.data["team"],
            "spec_sha256": sha(spec_path.read_bytes()), "resources": receipts, "digits": measurements,
            "families": list(families), "runtime_visibility_proved": False},
    }
    publish_batch([(out / name, (json.dumps(data, indent=2) + "\n").encode()) for name, data in artifacts.items()])
    return artifacts["font_receipts.json"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--baseline-export", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--index", type=Path, default=ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
    parser.add_argument("--compatibility", type=Path, default=ROOT / "reports/assets/nfl2k5_live_numbers_nameplate_compatibility.json")
    parser.add_argument("--families", default=",".join(DEFAULT_FAMILIES),
                        help="Comma-separated jersey_digit,helmet_digit,arm_digit; unselected or explicitly blank arm families stay unchanged")
    args = parser.parse_args()
    build(args.spec, args.baseline_export, args.out, args.index, args.compatibility,
          tuple(args.families.split(",")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
