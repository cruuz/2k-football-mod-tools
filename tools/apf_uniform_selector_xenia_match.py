#!/usr/bin/env python3
"""Select a pose-matched APF Assassins helmet-selector runtime pair.

The Logo Selection previews animate continuously.  This helper compares only
the two face/facemask reference regions to select the closest control/modified
pair, then reports the two helmet-crown regions separately.  It does not parse
or import either selector writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Iterable, Sequence

from PIL import Image, ImageDraw


SCHEMA = "apf_uniform_selector_xenia_pose_match/v1"
FRAME_SIZE = (1280, 739)

# These boxes are intentionally disjoint.  The reference boxes cover the
# moving face/facemask/shoulder areas but exclude the upper helmet stripe.  The
# evidence boxes cover the upper crowns where helmet assets 1 and 2 differ.
REFERENCE_BOXES = (
    (448, 568, 535, 630),
    (755, 568, 842, 630),
)
EVIDENCE_BOXES = (
    (432, 528, 516, 566),
    (770, 528, 854, 566),
)
PREVIEW_LABELS = ("left_home_labeled_preview", "right_away_labeled_preview")
MAX_REFERENCE_MAD = 8.0
MIN_EVIDENCE_TO_REFERENCE_MAD_RATIO = 1.5
MIN_CHANGED_PIXEL_FRACTION_PER_PREVIEW = 0.05


class MatchError(ValueError):
    """The frame set cannot support the frozen pose-match contract."""


def sha256_path(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _regular_pngs(directory: Path) -> list[Path]:
    if not directory.is_dir() or directory.is_symlink():
        raise MatchError(f"frame directory is not a real directory: {directory}")
    paths = sorted(
        path for path in directory.iterdir()
        if path.suffix.lower() == ".png" and path.is_file() and not path.is_symlink()
    )
    if not paths:
        raise MatchError(f"frame directory contains no regular PNGs: {directory}")
    return paths


def _load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        image.load()
        if image.size != FRAME_SIZE:
            raise MatchError(
                f"frame {path} is {image.size[0]}x{image.size[1]}, expected "
                f"{FRAME_SIZE[0]}x{FRAME_SIZE[1]}"
            )
        return image.convert("RGB")


def _box_pixels(image: Image.Image, boxes: Sequence[tuple[int, int, int, int]]) -> bytes:
    return b"".join(image.crop(box).tobytes() for box in boxes)


def difference_metrics(left: bytes, right: bytes) -> dict[str, int | float]:
    if len(left) != len(right) or len(left) % 3:
        raise MatchError("RGB comparison buffers have incompatible lengths")
    differences = [abs(a - b) for a, b in zip(left, right)]
    pixel_count = len(left) // 3
    different_pixels = sum(
        left[index:index + 3] != right[index:index + 3]
        for index in range(0, len(left), 3)
    )
    return {
        "pixel_count": pixel_count,
        "different_pixels": different_pixels,
        "different_components": sum(value != 0 for value in differences),
        "maximum_absolute_component_difference": max(differences, default=0),
        "mean_absolute_component_difference": (
            sum(differences) / len(differences) if differences else 0.0
        ),
    }


def _frame_record(path: Path, image: Image.Image) -> dict[str, object]:
    return {
        "path": str(path),
        "sha256": sha256_path(path),
        "reference_rgb_sha256": hashlib.sha256(
            _box_pixels(image, REFERENCE_BOXES)
        ).hexdigest(),
        "evidence_rgb_sha256": hashlib.sha256(
            _box_pixels(image, EVIDENCE_BOXES)
        ).hexdigest(),
    }


def match_frame_sets(
    control_paths: Iterable[Path], modified_paths: Iterable[Path]
) -> tuple[dict[str, object], Image.Image, Image.Image]:
    def prepare(path: Path) -> dict[str, object]:
        image = _load_rgb(path)
        return {
            "path": path,
            "image": image,
            "record": _frame_record(path, image),
            "reference": _box_pixels(image, REFERENCE_BOXES),
            "reference_boxes": [_box_pixels(image, (box,)) for box in REFERENCE_BOXES],
            "evidence": _box_pixels(image, EVIDENCE_BOXES),
            "evidence_boxes": [_box_pixels(image, (box,)) for box in EVIDENCE_BOXES],
        }

    controls = [prepare(path) for path in control_paths]
    modified = [prepare(path) for path in modified_paths]
    if not controls or not modified:
        raise MatchError("both frame sets must be non-empty")

    pairs: list[tuple[tuple[float, int, str, str], dict[str, object], Image.Image, Image.Image]] = []
    gate_rows: list[dict[str, object]] = []
    for control in controls:
        for changed in modified:
            control_path = control["path"]
            modified_path = changed["path"]
            control_image = control["image"]
            modified_image = changed["image"]
            assert isinstance(control_path, Path) and isinstance(modified_path, Path)
            assert isinstance(control_image, Image.Image) and isinstance(modified_image, Image.Image)
            reference = difference_metrics(
                control["reference"], changed["reference"]  # type: ignore[arg-type]
            )
            evidence = difference_metrics(
                control["evidence"], changed["evidence"]  # type: ignore[arg-type]
            )
            record = {
                "control": control["record"],
                "modified": changed["record"],
                "reference_metrics": reference,
                "reference_box_metrics": [
                    {
                        "preview": label,
                        **difference_metrics(left, right),
                    }
                    for label, left, right in zip(
                        PREVIEW_LABELS,
                        control["reference_boxes"],  # type: ignore[arg-type]
                        changed["reference_boxes"],  # type: ignore[arg-type]
                    )
                ],
                "evidence_metrics": evidence,
                "evidence_box_metrics": [
                    {
                        "preview": label,
                        **difference_metrics(left, right),
                    }
                    for label, left, right in zip(
                        PREVIEW_LABELS,
                        control["evidence_boxes"],  # type: ignore[arg-type]
                        changed["evidence_boxes"],  # type: ignore[arg-type]
                    )
                ],
            }
            reference_mad = float(reference["mean_absolute_component_difference"])
            evidence_mad = float(evidence["mean_absolute_component_difference"])
            ratio = evidence_mad / max(reference_mad, 1e-12)
            changed_fractions = [
                float(row["different_pixels"]) / int(row["pixel_count"])
                for row in record["evidence_box_metrics"]  # type: ignore[union-attr]
            ]
            reference_eligible = reference_mad <= MAX_REFERENCE_MAD
            all_gates_pass = (
                reference_eligible
                and ratio >= MIN_EVIDENCE_TO_REFERENCE_MAD_RATIO
                and min(changed_fractions) >= MIN_CHANGED_PIXEL_FRACTION_PER_PREVIEW
            )
            gate_rows.append({
                "control_frame": control_path.name,
                "modified_frame": modified_path.name,
                "reference_mad": reference_mad,
                "evidence_mad": evidence_mad,
                "evidence_to_reference_mad_ratio": ratio,
                "per_preview_changed_pixel_fractions": {
                    label: fraction
                    for label, fraction in zip(PREVIEW_LABELS, changed_fractions)
                },
                "reference_eligible": reference_eligible,
                "all_localization_gates_pass": all_gates_pass,
            })
            key = (
                reference_mad,
                int(reference["different_pixels"]),
                control_path.name,
                modified_path.name,
            )
            pairs.append((key, record, control_image, modified_image))

    pairs.sort(key=lambda item: item[0])
    _, selected, control_image, modified_image = pairs[0]
    runner_up = pairs[1][1] if len(pairs) > 1 else None
    reference_eligible_rows = [
        row for row in gate_rows if row["reference_eligible"] is True
    ]
    maximum_ratio_row = (
        max(
            reference_eligible_rows,
            key=lambda row: (
                float(row["evidence_to_reference_mad_ratio"]),
                str(row["control_frame"]),
                str(row["modified_frame"]),
            ),
        )
        if reference_eligible_rows
        else None
    )
    result = {
        "schema": SCHEMA,
        "frame_dimensions": list(FRAME_SIZE),
        "reference_boxes": [list(box) for box in REFERENCE_BOXES],
        "evidence_boxes": [list(box) for box in EVIDENCE_BOXES],
        "selection_rule": (
            "global minimum reference-region mean absolute RGB component "
            "difference; ties use different-pixel count then filenames"
        ),
        "control_frame_count": len(controls),
        "modified_frame_count": len(modified),
        "candidate_pair_count": len(pairs),
        "localization_gate_search": {
            "gates": {
                "maximum_reference_mean_absolute_component_difference": MAX_REFERENCE_MAD,
                "minimum_evidence_to_reference_mad_ratio": MIN_EVIDENCE_TO_REFERENCE_MAD_RATIO,
                "minimum_changed_pixel_fraction_per_preview": MIN_CHANGED_PIXEL_FRACTION_PER_PREVIEW,
            },
            "reference_eligible_pair_count": len(reference_eligible_rows),
            "all_gate_pair_count": sum(
                row["all_localization_gates_pass"] is True for row in gate_rows
            ),
            "maximum_ratio_reference_eligible_pair": maximum_ratio_row,
        },
        "selected": selected,
        "runner_up": runner_up,
    }
    return result, control_image, modified_image


def _reserve(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise MatchError(f"refusing to replace output: {path}")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise MatchError(f"output parent is not a real directory: {path.parent}")


def _comparison_panel(control: Image.Image, modified: Image.Image) -> Image.Image:
    title_height = 54
    panel = Image.new("RGB", (FRAME_SIZE[0] * 2, FRAME_SIZE[1] + title_height), "black")
    panel.paste(control, (0, title_height))
    panel.paste(modified, (FRAME_SIZE[0], title_height))
    draw = ImageDraw.Draw(panel)
    draw.text((20, 18), "RETAIL CONTROL — helmet asset 1", fill="white")
    draw.text((FRAME_SIZE[0] + 20, 18), "VERIFIED COPIED 0A — helmet asset 2", fill="white")
    for offset in (0, FRAME_SIZE[0]):
        for box in REFERENCE_BOXES:
            shifted = (box[0] + offset, box[1] + title_height,
                       box[2] + offset, box[3] + title_height)
            draw.rectangle(shifted, outline=(60, 180, 255), width=2)
        for box in EVIDENCE_BOXES:
            shifted = (box[0] + offset, box[1] + title_height,
                       box[2] + offset, box[3] + title_height)
            draw.rectangle(shifted, outline=(255, 220, 40), width=2)
    return panel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-frames", required=True, type=Path)
    parser.add_argument("--modified-frames", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--panel", required=True, type=Path)
    parser.add_argument("--selected-control", required=True, type=Path)
    parser.add_argument("--selected-modified", required=True, type=Path)
    args = parser.parse_args(argv)
    outputs = (args.json, args.panel, args.selected_control, args.selected_modified)
    try:
        for output in outputs:
            _reserve(output)
        result, control, modified = match_frame_sets(
            _regular_pngs(args.control_frames), _regular_pngs(args.modified_frames)
        )
        selected = result["selected"]
        assert isinstance(selected, dict)
        control_record = selected["control"]
        modified_record = selected["modified"]
        assert isinstance(control_record, dict) and isinstance(modified_record, dict)
        shutil.copyfile(Path(str(control_record["path"])), args.selected_control)
        shutil.copyfile(Path(str(modified_record["path"])), args.selected_modified)
        panel = _comparison_panel(control, modified)
        panel.save(args.panel, format="PNG")
        result["outputs"] = {
            "selected_control": {
                "path": str(args.selected_control),
                "sha256": sha256_path(args.selected_control),
            },
            "selected_modified": {
                "path": str(args.selected_modified),
                "sha256": sha256_path(args.selected_modified),
            },
            "comparison_panel": {
                "path": str(args.panel),
                "sha256": sha256_path(args.panel),
            },
        }
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(
            "APF_UNIFORM_SELECTOR_XENIA_MATCH_PASS "
            f"pairs={result['candidate_pair_count']} "
            f"reference_mad={selected['reference_metrics']['mean_absolute_component_difference']:.6f} "
            f"evidence_mad={selected['evidence_metrics']['mean_absolute_component_difference']:.6f}"
        )
        return 0
    except (MatchError, OSError) as exc:
        for output in outputs:
            output.unlink(missing_ok=True)
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
