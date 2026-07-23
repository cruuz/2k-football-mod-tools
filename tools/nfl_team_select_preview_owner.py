#!/usr/bin/env python3
"""Build the focused NFL 2K5 Team Select preview-owner evidence report."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from xbe_info import Xbe


XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
ROI = (250, 155, 570, 440)


class EvidenceError(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pin(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "size": path.stat().st_size, "sha256": sha256(path)}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def read_va(xbe: Xbe, address: int, size: int) -> bytes:
    offset = xbe.va_to_offset(address, size)
    return xbe.data[offset:offset + size]


def u32_va(xbe: Xbe, address: int) -> int:
    return struct.unpack("<I", read_va(xbe, address, 4))[0]


def call_target(xbe: Xbe, address: int) -> int:
    data = read_va(xbe, address, 5)
    require(data[0] == 0xE8, f"0x{address:08X} is not CALL rel32")
    return address + 5 + struct.unpack("<i", data[1:])[0]


def anchor(xbe: Xbe, address: int, expected_hex: str, label: str) -> dict[str, Any]:
    expected = bytes.fromhex(expected_hex)
    actual = read_va(xbe, address, len(expected))
    require(actual == expected, f"{label} bytes changed at 0x{address:08X}")
    record: dict[str, Any] = {
        "label": label,
        "address": f"0x{address:08X}",
        "bytes": actual.hex(),
    }
    if actual[:1] == b"\xe8":
        record["call_target"] = f"0x{call_target(xbe, address):08X}"
    return record


def compact(row: dict[str, str], fields: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        value = row[field]
        if value in ("True", "False"):
            result[field] = value == "True"
        elif value.isdecimal():
            result[field] = int(value)
        else:
            result[field] = value
    return result


def affine_match(source_path: Path, frame_path: Path) -> dict[str, Any]:
    source = np.asarray(Image.open(source_path).convert("RGBA"))
    frame = np.asarray(Image.open(frame_path).convert("RGB"))
    source_gray = cv2.cvtColor(source[:, :, :3], cv2.COLOR_RGB2GRAY)
    frame_gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    frame_mask = np.zeros(frame_gray.shape, np.uint8)
    x0, y0, x1, y1 = ROI
    frame_mask[y0:y1, x0:x1] = 255
    sift = cv2.SIFT_create(nfeatures=1500, contrastThreshold=0.01)
    source_points, source_desc = sift.detectAndCompute(
        source_gray, (source[:, :, 3] > 64).astype(np.uint8) * 255)
    frame_points, frame_desc = sift.detectAndCompute(frame_gray, frame_mask)
    require(source_desc is not None and frame_desc is not None, "SIFT descriptor failure")
    matches = cv2.BFMatcher().knnMatch(source_desc, frame_desc, k=2)
    good = [first for first, second in matches if first.distance < 0.7 * second.distance]
    require(len(good) >= 4, f"too few matches for {source_path}")
    source_xy = np.float32([source_points[item.queryIdx].pt for item in good])
    frame_xy = np.float32([frame_points[item.trainIdx].pt for item in good])
    cv2.setRNGSeed(0)
    matrix, inlier_mask = cv2.estimateAffine2D(
        source_xy, frame_xy, method=cv2.RANSAC, ransacReprojThreshold=4,
        maxIters=2000, confidence=0.99, refineIters=10)
    require(matrix is not None and inlier_mask is not None, f"affine fit failed for {source_path}")
    inliers = inlier_mask.ravel().astype(bool)
    prediction = np.c_[source_xy[inliers], np.ones(inliers.sum())] @ matrix.T
    median_error = float(np.median(np.linalg.norm(prediction - frame_xy[inliers], axis=1)))

    warped_rgb = cv2.warpAffine(
        source[:, :, :3].astype(np.float32), matrix,
        (frame.shape[1], frame.shape[0]), flags=cv2.INTER_LINEAR)
    warped_alpha = cv2.warpAffine(
        source[:, :, 3], matrix, (frame.shape[1], frame.shape[0]),
        flags=cv2.INTER_LINEAR)
    yy, xx = np.mgrid[:frame.shape[0], :frame.shape[1]]
    compare = ((warped_alpha > 245) & (xx >= 250) & (xx < 515) &
               (yy >= 155) & (yy < 438))
    source_rgb = warped_rgb[compare].astype(np.float64)
    target_rgb = frame[compare].astype(np.float64)
    correlations: list[float] = []
    fitted_rmse: list[float] = []
    for channel in range(3):
        x = source_rgb[:, channel]
        y = target_rgb[:, channel]
        correlations.append(float(np.corrcoef(x, y)[0, 1]))
        design = np.c_[x, np.ones(len(x))]
        coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
        fitted_rmse.append(float(np.sqrt(np.mean((design @ coefficients - y) ** 2))))
    source_luma = cv2.cvtColor(warped_rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(float)
    target_luma = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY).astype(float)
    eroded = cv2.erode(compare.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    gradient_correlations: list[float] = []
    for dx, dy in ((1, 0), (0, 1)):
        source_gradient = cv2.Sobel(source_luma, cv2.CV_64F, dx, dy, ksize=3)
        target_gradient = cv2.Sobel(target_luma, cv2.CV_64F, dx, dy, ksize=3)
        gradient_correlations.append(
            float(np.corrcoef(source_gradient[eroded], target_gradient[eroded])[0, 1]))
    return {
        "source_keypoints": len(source_points),
        "frame_keypoints_in_roi": len(frame_points),
        "ratio_test_matches": len(good),
        "ransac_inliers": int(inliers.sum()),
        "median_inlier_error_pixels": round(median_error, 6),
        "source_to_frame_affine": [[round(float(value), 6) for value in line] for line in matrix],
        "opaque_comparison_pixels": int(compare.sum()),
        "mean_rgb_correlation": round(float(np.mean(correlations)), 6),
        "mean_fitted_rgb_rmse": round(float(np.mean(fitted_rmse)), 6),
        "mean_gradient_correlation": round(float(np.mean(gradient_correlations)), 6),
    }


def match_rank(candidates: list[dict[str, str]], frame: Path) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            stats = affine_match(Path(candidate["png_path"]), frame)
        except EvidenceError:
            stats = {"ransac_inliers": 0, "ratio_test_matches": 0,
                     "median_inlier_error_pixels": 999.0}
        ranked.append({
            "outer_index": int(candidate["outer_index"]),
            "name": candidate["name"],
            "rgba_sha256": candidate["rgba_sha256"],
            "ransac_inliers": stats["ransac_inliers"],
            "ratio_test_matches": stats["ratio_test_matches"],
            "median_inlier_error_pixels": stats["median_inlier_error_pixels"],
        })
    ranked.sort(key=lambda item: (
        -item["ransac_inliers"], -item["ratio_test_matches"],
        item["median_inlier_error_pixels"], item["outer_index"], item["name"]))
    return ranked


def build(root: Path) -> dict[str, Any]:
    xbe_path = root / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
    scene_path = root / "reports/assets/nfl2k5_scne_scenes.tsv"
    material_path = root / "reports/assets/nfl2k5_scne_material_textures.tsv"
    submesh_path = root / "reports/assets/nfl2k5_scne_submeshes.tsv"
    txtr_path = root / "reports/assets/nfl2k5_all_txtr_inventory_v2.tsv"
    runtime_path = root / "reports/assets/nfl2k5_actual_jersey_binding_away_loader_safe_xemu_runtime.json"
    trace_path = root / "reports/assets/nfl2k5_team_select_preview_owner/nfl_team_select_preview_owner_trace.txt"
    pseudo_path = root / "reports/assets/nfl2k5_team_select_preview_owner/nfl_team_select_preview_owner_pseudo_c.c"
    frame_dir = root / "reports/assets/nfl2k5_actual_jersey_binding_away_loader_safe_xemu_runtime"
    frame0 = frame_dir / "lions-away-loader-safe-team-select-00.png"
    frame6 = frame_dir / "lions-away-loader-safe-team-select-06.png"

    xbe = Xbe(xbe_path)
    require(hashlib.md5(xbe.data).hexdigest() == XBE_MD5, "unexpected XBE MD5")
    require(hashlib.sha256(xbe.data).hexdigest() == XBE_SHA256, "unexpected XBE SHA-256")
    require(read_va(xbe, 0x0052728C, 0x20).hex() ==
            "f4b2e90028725200a03d0f008072520000000000000000000cb3e90000000000",
            "Team Select descriptor changed")
    require(xbe.utf16z_va(u32_va(xbe, 0x0052728C)) == "Team Select", "state title changed")

    strings = {
        "team_select_screen": 0x00EA2A30,
        "right_logo_material": 0x00EA2AE8,
        "right_uniform_material": 0x00EA2B38,
        "left_logo_material": 0x00EA2BAC,
        "left_uniform_material": 0x00EA2BF8,
        "helmet_format": 0x00EA2C78,
        "uniform_format": 0x00EA2C94,
        "ghost_fallback_format": 0x00EA2CB0,
        "home_context": 0x00EA2CDC,
        "away_context": 0x00EA2CE0,
        "preload_format": 0x00EA2CFC,
        "single_scene": 0x00EA2D14,
        "double_scene": 0x00EA2D3C,
        "logos_lookup_context": 0x00EA2C6C,
    }
    decoded_strings = {key: {"address": f"0x{address:08X}", "text": xbe.utf16z_va(address)}
                       for key, address in strings.items()}
    expected_strings = {
        "helmet_format": "helm_%s%s_%1d", "uniform_format": "unif_%s%s_%1d",
        "preload_format": "%s_%s%s_%1d", "home_context": "h", "away_context": "a",
        "single_scene": "single_team_select", "double_scene": "double_team_select",
        "logos_lookup_context": "LOGOS",
    }
    for key, value in expected_strings.items():
        require(decoded_strings[key]["text"] == value, f"unexpected {key} string")

    code_specs = (
        (0x002C21F3, "e868d50500", "Team Select event 3 initializes preview subsystem"),
        (0x002C1259, "e862e50500", "Team Select event 8 calls preview resolver/draw"),
        (0x002C0B92, "e879e30500", "selected team/style setter call"),
        (0x002C1291, "e8aadc0500", "home helmet preload call"),
        (0x0031EE59, "68142dea00", "single_team_select name push"),
        (0x0031EE65, "e8765bd2ff", "single_team_select SCNE lookup"),
        (0x0031EE92, "683c2dea00", "double_team_select name push"),
        (0x0031EE9E, "e83d5bd2ff", "double_team_select SCNE lookup"),
        (0x0031F1FA, "e8f159d4ff", "lookup-context gate read"),
        (0x0031F2C5, "68782cea00", "helmet format address push"),
        (0x0031F2FD, "68942cea00", "uniform format address push"),
        (0x0031F33A, "e8a156d2ff", "formatted uniform TXTR lookup"),
        (0x0031F353, "e88856d2ff", "formatted helmet TXTR lookup"),
        (0x0031F43C, "e88f9bd4ff", "logo material resolver"),
        (0x0031F44F, "e83cf6ffff", "helmet TXTR material write"),
        (0x0031F46F, "e85c9bd4ff", "uniform material resolver"),
        (0x0031F486, "e805f6ffff", "uniform TXTR material write"),
        (0x0031F48F, "e87cf4ffff", "backdrop material resolver"),
        (0x0031F8DF, "e8ecf8ffff", "right binding call"),
        (0x0031F90C, "e8bff8ffff", "left binding call"),
    )
    code = [anchor(xbe, address, data, label) for address, data, label in code_specs]

    pointer_tables: dict[str, list[dict[str, Any]]] = {}
    for side, base in (("right", 0x00AE2C78), ("left", 0x00AE2C8C)):
        pointer_tables[side] = []
        for index in range(4):
            slot = base + index * 4
            pointer = u32_va(xbe, slot)
            pointer_tables[side].append({
                "slot": f"0x{slot:08X}", "pointer": f"0x{pointer:08X}",
                "name": xbe.utf16z_va(pointer),
            })

    scene_rows = [item for item in rows(scene_path)
                  if item["name"] in ("single_team_select", "double_team_select")]
    require(len(scene_rows) == 3, "expected three Team Select SCNE inventory rows")
    scene_fields = ("scene_index", "outer_index", "outer_id", "chunk_index", "chunk_offset",
                    "stored_size", "system_bytes", "video_bytes", "name", "materials_count",
                    "shapes_count", "decoded_sha256")
    scene_inventory = [compact(item, scene_fields) for item in scene_rows]

    material_rows = [item for item in rows(material_path)
                     if item["scene_name"] in ("single_team_select", "double_team_select")]
    dynamic_names = {"C_l_uniform_SELECT", "C_r_uniform_SELECT",
                     "LEFT_team_select_logo", "RIGHT_team_select_logo"}
    dynamic_materials = [compact(item, (
        "scene_index", "outer_index", "chunk_index", "scene_name", "material_index",
        "material_name", "material_offset", "texture_pointer_field", "conversion_status"))
        for item in material_rows if item["material_name"] in dynamic_names]
    require(len(dynamic_materials) == 10, "unexpected dynamic Team Select material count")

    submesh_rows = [item for item in rows(submesh_path)
                    if item["scene_name"] in ("single_team_select", "double_team_select") and
                    item["material_name"] in dynamic_names]
    require(len(submesh_rows) == 10, "dynamic materials are not all backed by submeshes")
    dynamic_submeshes = [compact(item, (
        "scene_index", "outer_index", "chunk_index", "scene_name", "shape_name",
        "submesh_index", "record_offset", "material_index", "material_name",
        "command_offset", "command_count", "primitive_mode_counts")) for item in submesh_rows]

    texture_rows = rows(txtr_path)
    team_candidates = [item for item in texture_rows
                       if re.fullmatch(r"(?:unif|helm)_[ha]09_\d+", item["name"])]
    uniform_candidates = [item for item in team_candidates if item["name"].startswith("unif_")]
    helmet_candidates = [item for item in team_candidates if item["name"].startswith("helm_")]
    require(len(uniform_candidates) == 20, "unexpected Detroit uniform-card count")
    require(len(helmet_candidates) == 40, "unexpected Detroit helmet-card count")
    unif0 = [item for item in uniform_candidates if item["name"] == "unif_a09_0"]
    helm0 = [item for item in helmet_candidates if item["name"] == "helm_a09_0"]
    require(len(unif0) == 1 and len(helm0) == 2, "unexpected selected-card multiplicity")
    helm256 = next(item for item in helm0 if item["width"] == "256")
    helm128 = next(item for item in helm0 if item["width"] == "128")
    txtr_fields = ("outer_index", "outer_id", "chunk_index", "chunk_offset", "name",
                   "format_name", "width", "height", "decoded_sha256", "rgba_sha256", "png_path")

    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    team_select = runtime["observations"]["team_select"]
    require(team_select["frame_count"] == 13 and not team_select["diagnostic_visible"],
            "runtime preview split evidence changed")
    for frame in team_select["frames"]:
        local = frame_dir / Path(frame["asset"]["path"]).name
        require(sha256(local) == frame["asset"]["sha256"], f"runtime frame {frame['index']} changed")
        counts = frame["lions_preview_crop"]["counts"]
        require(counts["magenta"] == 0 and counts["green"] == 0,
                f"diagnostic colors appeared in Team Select frame {frame['index']}")

    cv2.setNumThreads(1)
    uniform_rank = match_rank(uniform_candidates, frame0)
    helmet_rank = match_rank(helmet_candidates, frame6)
    uniform_stats = affine_match(Path(unif0[0]["png_path"]), frame0)
    helmet256_stats = affine_match(Path(helm256["png_path"]), frame6)
    helmet128_stats = affine_match(Path(helm128["png_path"]), frame6)
    require(uniform_rank[0]["name"] == "unif_a09_0", "frame 00 did not rank unif_a09_0 first")
    require(uniform_stats["ransac_inliers"] >= 70, "uniform card match weakened")
    require(helmet256_stats["ransac_inliers"] >= 30, "256px helmet card match weakened")
    require(helmet256_stats["mean_gradient_correlation"] > 0.95,
            "256px helmet residual match weakened")
    require(helmet128_stats["mean_gradient_correlation"] < 0.85,
            "128px helmet control unexpectedly matches")
    require(helm256["rgba_sha256"] == next(item for item in helmet_candidates
            if item["outer_index"] == "3102" and item["name"] == "helm_a09_9")["rgba_sha256"],
            "helmet style 0/9 equivalence changed")

    trace = trace_path.read_text(encoding="utf-8")
    pseudo = pseudo_path.read_text(encoding="utf-8")
    for phrase in (
        "0x0031F2C5 68782cea00 PUSH 0xea2c78",
        "0x0031F2FD 68942cea00 PUSH 0xea2c94",
        "0x0031F44F e83cf6ffff CALL 0x0031ea90",
        "0x0031F486 e805f6ffff CALL 0x0031ea90",
        "0x0031F8DF e8ecf8ffff CALL 0x0031f1d0",
        "0x0031F90C e8bff8ffff CALL 0x0031f1d0",
    ):
        require(phrase in trace, f"Ghidra trace lacks {phrase}")
    for phrase in ("DAT_00a83a1c", "DAT_00ea2d14", "DAT_00ea2d3c",
                   "*(int *)(in_EAX + 0x30) = param_1"):
        require(phrase in pseudo, f"Ghidra pseudo-C lacks {phrase}")

    return {
        "schema": "nfl2k5_team_select_preview_owner/v1",
        "conclusion": {
            "classification": "standalone_pre_rendered_txtr_cards_bound_to_team_select_scne_quads",
            "live_player_09A0_iff_is_not_the_team_select_preview_owner": True,
            "selected_detroit_uniform_card": "unif_a09_0",
            "selected_detroit_helmet_card": "helm_a09_0",
            "selected_card_outer_index": 3102,
            "selected_card_resolution": [256, 256],
            "binding": "FUN_0031f1d0 writes formatted TXTR resources to SCNE material+0x30; FUN_0031f7c0 invokes it for both side tables; FUN_0031f4e0 draws team_select_screen.",
            "important_nuance": "unif_a09_0 is itself a baked torso-plus-lower-helmet image; helm_a09_0 is the separate helmet phase. The menu crossfades these flat cards rather than rendering a live player torso.",
        },
        "inputs": {
            "xbe": pin(xbe_path), "scenes": pin(scene_path), "materials": pin(material_path),
            "submeshes": pin(submesh_path), "txtr_inventory": pin(txtr_path),
            "runtime_split": pin(runtime_path), "ghidra_trace": pin(trace_path),
            "ghidra_pseudo_c": pin(pseudo_path), "frame_00": pin(frame0), "frame_06": pin(frame6),
        },
        "team_select_state": {
            "descriptor": "0x0052728C", "title": "Team Select",
            "event_table": "0x00527228", "event_3_callback": "0x002C21F0",
            "event_8_callback": "0x002C1250",
        },
        "code_anchors": code,
        "strings": decoded_strings,
        "cache_and_state_slots": {
            "lookup_context_gate": {"address": "0x00A83A1C", "reader": "0x00064BF0"},
            "side_0_team_pointer": "0x00AE2B34", "side_0_style_index": "0x00AE2B3C",
            "side_1_team_pointer": "0x00AE2B38", "side_1_style_index": "0x00AE2B40",
            "single_scene_cache": "0x00AE2B44", "double_scene_cache": "0x00AE2B48",
            "side_0_transition_block": "0x00AE2B58..0x00AE2B60",
            "side_1_transition_block": "0x00AE2B64..0x00AE2B6C",
            "txtr_binding_slot": "resolved SCNE material record + 0x30 (not a proved persistent global TXTR cache)",
            "material_tint_slot": "resolved backdrop SCNE material record + 0x18",
        },
        "material_pointer_tables": pointer_tables,
        "binding_writes": [
            {"table_index": 0, "resource": "formatted helm_* TXTR", "write": "material+0x30", "color": "transition alpha"},
            {"table_index": 1, "resource": "same helm_* TXTR", "write": "material+0x30 if name resolves", "static_inventory_note": "RIGHT/LEFT_text_logo is absent from all three inventoried Team Select SCNE material lists"},
            {"table_index": 2, "resource": "formatted unif_* TXTR", "write": "material+0x30", "color": "inverse transition alpha"},
            {"table_index": 3, "resource": "team primary/secondary ARGB", "write": "material+0x18", "purpose": "embedded ESPN backdrop tint"},
        ],
        "scene_inventory": scene_inventory,
        "dynamic_materials": dynamic_materials,
        "dynamic_material_submeshes": dynamic_submeshes,
        "detroit_card_inventory": {
            "uniform_candidate_count": len(uniform_candidates),
            "helmet_candidate_count_including_256_and_128_duplicates": len(helmet_candidates),
            "selected_uniform": compact(unif0[0], txtr_fields),
            "selected_helmet_256": compact(helm256, txtr_fields),
            "same_name_128_control": compact(helm128, txtr_fields),
        },
        "runtime_visual_join": {
            "route": runtime["observations"]["route"],
            "team_select_frames": 13,
            "diagnostic_visible_in_team_select": False,
            "diagnostic_visible_on_live_coin_toss_players": True,
            "feature_method": {"opencv": cv2.__version__, "detector": "SIFT", "ratio": 0.7,
                               "ransac_threshold_pixels": 4, "roi": list(ROI)},
            "uniform_frame_00": {"selected": "unif_a09_0", "stats": uniform_stats,
                                 "top_ranked_candidates": uniform_rank[:6]},
            "helmet_frame_06": {"selected": "helm_a09_0 outer 3102", "stats": helmet256_stats,
                                "same_name_128_control_stats": helmet128_stats,
                                "top_ranked_candidates": helmet_rank[:8],
                                "style_equivalence": "outer-3102 helm_a09_0 and helm_a09_9 have identical RGBA; the matched unif_a09_0 and shared formatter style parameter disambiguate the live selection as style 0."},
        },
        "static_limits_and_portmes": [
            "PORTME(scene-return): hook FUN_000449e0 at 0x0031EE9E in a live double-team run to distinguish outer 8 from the duplicate outer 346 double_team_select SCNE; both have the same relevant material/submesh contract.",
            "PORTME(context): capture 0x00A83A1C and the ECX context at formatted TXTR lookups 0x0031F33A..0x0031F3B3 to prove the live global-versus-LOGOS lookup branch.",
            "PORTME(pointer): capture C_l_uniform_SELECT/C_r_uniform_SELECT and LEFT/RIGHT_team_select_logo material+0x30 after 0x0031F44F/0x0031F486 for pointer-level confirmation independent of the strong screenshot-to-PNG match.",
            "PORTME(text-logo): explain or observe RIGHT_text_logo/LEFT_text_logo resolution; those table names are not static materials in any of the three inventoried Team Select SCNE records.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
