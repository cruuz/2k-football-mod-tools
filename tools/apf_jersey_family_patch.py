#!/usr/bin/env python3
"""Safely patch any proved APF jersey package in a newly copied 0A volume.

Targets are selected by the exact retail asset index 0..23 and are gated by
the independently generated all-jersey catalog. This wrapper reuses the
validated nine-mip transport and fixed-allocation IFF writer. It never opens
the retail source for writing and refuses an existing destination or an image
whose rebuilt entry does not fit the selected package.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
from typing import Iterator

import apf_inner
import apf_outer
import apf_texture_patch as archive_patch
import apf_uniform_mip_patch as uniform_patch
import apf_xenos_mip_layout as xenos_mips


SCHEMA = "apf_jersey_family_patch/v1"
WORKSPACE = Path(__file__).resolve().parents[1]
CATALOG = WORKSPACE / "reports/assets/apf_jersey_family_layout.json"
EXPECTED_CATALOG_SHA256 = (
    "b60783b9c47b57e9b9f545e95f5c17d3c850e263e0d7d453aa6c3be4a0f809e4"
)
EXPECTED_VOLUME_SHA256 = (
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
)


class JerseyFamilyPatchError(ValueError):
    """Raised when the family catalog or requested target is not exact."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_catalog() -> dict[str, object]:
    data = CATALOG.read_bytes()
    if _sha256(data) != EXPECTED_CATALOG_SHA256:
        raise JerseyFamilyPatchError("jersey-family catalog hash changed")
    document = json.loads(data)
    if document.get("schema") != "apf_jersey_family_layout/v1":
        raise JerseyFamilyPatchError("jersey-family catalog schema changed")
    source = document["source"]
    if source["sha256_before"] != EXPECTED_VOLUME_SHA256 or (
        source["sha256_after"] != EXPECTED_VOLUME_SHA256
    ):
        raise JerseyFamilyPatchError("catalog is not for the pinned retail 0A")
    boundary = document["claim_boundary"]
    if not boundary["structural_layout_generalizes_across_all_24_jerseys"]:
        raise JerseyFamilyPatchError("catalog does not prove the family layout")
    if boundary["retail_or_copied_game_volume_written"]:
        raise JerseyFamilyPatchError("catalog safety boundary changed")
    jerseys = document["jerseys"]
    if len(jerseys) != 24 or [row["asset_index"] for row in jerseys] != list(range(24)):
        raise JerseyFamilyPatchError("catalog target roster changed")
    return document


def target_record(asset_index: int) -> dict[str, object]:
    if not 0 <= asset_index < 24:
        raise JerseyFamilyPatchError("--asset-index must be in 0..23")
    return _load_catalog()["jerseys"][asset_index]


@contextmanager
def _selected_target(row: dict[str, object]) -> Iterator[None]:
    """Bind the already validated single-target writer to one pinned jersey."""
    old = (
        uniform_patch.ENTRY_INDEX,
        uniform_patch.FILE_INDEX,
        uniform_patch.ENTRY_NAME,
        uniform_patch.INNER_NAME,
        uniform_patch.EXPECTED_ENTRY_SHA256,
        uniform_patch.EXPECTED_TEXTURE_SHA256,
    )
    try:
        uniform_patch.ENTRY_INDEX = int(row["outer_table_index"])
        uniform_patch.FILE_INDEX = 0
        uniform_patch.ENTRY_NAME = str(row["outer_name"])
        uniform_patch.INNER_NAME = "jersey_color"
        uniform_patch.EXPECTED_ENTRY_SHA256 = str(
            row["outer_allocation"]["sha256"]
        )
        uniform_patch.EXPECTED_TEXTURE_SHA256 = str(
            row["inner_file"]["texture_sha256"]
        )
        yield
    finally:
        (
            uniform_patch.ENTRY_INDEX,
            uniform_patch.FILE_INDEX,
            uniform_patch.ENTRY_NAME,
            uniform_patch.INNER_NAME,
            uniform_patch.EXPECTED_ENTRY_SHA256,
            uniform_patch.EXPECTED_TEXTURE_SHA256,
        ) = old


def build_patch(
    index_path: Path, png_path: Path, asset_index: int
) -> archive_patch.PatchResult:
    row = target_record(asset_index)
    with _selected_target(row):
        result = uniform_patch.build_patch(index_path, png_path)
    source = result.manifest["source"]
    if source["outer_entry_index"] != row["outer_table_index"]:
        raise JerseyFamilyPatchError("writer selected the wrong outer entry")
    if source["entry_sha256"] != row["outer_allocation"]["sha256"]:
        raise JerseyFamilyPatchError("writer source entry differs from catalog")
    if source["texture_sha256"] != row["inner_file"]["texture_sha256"]:
        raise JerseyFamilyPatchError("writer texture differs from catalog")
    result.manifest["transport_schema"] = result.manifest["schema"]
    result.manifest["schema"] = SCHEMA
    result.manifest["family_target"] = {
        "asset_index": asset_index,
        "outer_name": row["outer_name"],
        "outer_table_index": row["outer_table_index"],
        "fixed_allocation": row["outer_allocation"]["size"],
        "retail_entry_sha256": row["outer_allocation"]["sha256"],
        "retail_texture_sha256": row["inner_file"]["texture_sha256"],
        "catalog_sha256": EXPECTED_CATALOG_SHA256,
        "runtime_visibility_proved": False,
    }
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path,
                        help="user-owned APF 0A")
    parser.add_argument("--asset-index", required=True, type=int,
                        help="uniform_jersey asset index, exactly 0..23")
    parser.add_argument("--png", required=True, type=Path,
                        help="edited 1024x1024 RGBA PNG")
    parser.add_argument("--output-entry", type=Path,
                        help="new rebuilt logical IFF path")
    parser.add_argument("--output-volume", type=Path,
                        help="copy 0A here and patch only the selected entry")
    parser.add_argument("--manifest", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest_reservation: archive_patch.OutputReservation | None = None
    manifest_path = args.manifest.expanduser()
    try:
        index_path = args.index.expanduser()
        png_path = args.png.expanduser()
        output_entry = (
            args.output_entry.expanduser() if args.output_entry is not None else None
        )
        output_volume = (
            args.output_volume.expanduser() if args.output_volume is not None else None
        )
        archive_patch._preflight_output_paths(  # type: ignore[attr-defined]
            [index_path, png_path],
            [("manifest", manifest_path), ("output entry", output_entry),
             ("output volume", output_volume)],
        )
        manifest_reservation = archive_patch._reserve_new(  # type: ignore[attr-defined]
            manifest_path
        )
        row = target_record(args.asset_index)
        result = build_patch(index_path, png_path, args.asset_index)
        archive = apf_outer.parse_archive(index_path)
        document = result.manifest
        if output_entry is not None:
            uniform_patch._write_new(output_entry, result.entry_bytes)  # type: ignore[attr-defined]
            document["output_entry"] = {
                "path": str(output_entry),
                "size": len(result.entry_bytes),
                "sha256": _sha256(result.entry_bytes),
            }
        if output_volume is not None:
            document["copied_volume"] = archive_patch._write_copied_volume(  # type: ignore[attr-defined]
                index_path,
                output_volume,
                archive.entries[int(row["outer_table_index"])],
                result.entry_bytes,
            )
        archive_patch._commit_reserved(  # type: ignore[attr-defined]
            manifest_path,
            manifest_reservation,
            (json.dumps(document, indent=2) + "\n").encode("utf-8"),
        )
        archive_patch._close_reserved(  # type: ignore[attr-defined]
            manifest_reservation
        )
        manifest_reservation = None
        print(
            "APF_JERSEY_FAMILY_PATCH_PASS "
            f"mode={document['mode']} asset={args.asset_index} "
            f"entry={row['outer_table_index']} sha256={_sha256(result.entry_bytes)}"
        )
    except (
        JerseyFamilyPatchError,
        uniform_patch.UniformPatchError,
        xenos_mips.MipLayoutError,
        archive_patch.PatchError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        OSError,
    ) as exc:
        if manifest_reservation is not None:
            archive_patch._abort_reserved(  # type: ignore[attr-defined]
                manifest_path, manifest_reservation
            )
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
