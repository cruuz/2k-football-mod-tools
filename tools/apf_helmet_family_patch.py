#!/usr/bin/env python3
"""Copy-only two-channel PNG writer for APF helmet_color assets 00..23.

The retail source 0A is read-only.  Outputs must be new paths.  The writer
selects one independently hash-pinned outer entry, regenerates all seven DXN
mips, preserves ``helmet_normal``, and fails closed if H7A/IFF reconstruction
does not fit the original allocation.  Runtime visibility is not claimed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import apf_helmet_color_transport as transport
import apf_inner
import apf_outer
import apf_texture_patch as archive_patch
import apf_xenos_dxn_mip_layout as dxn_mips


SCHEMA = "apf_helmet_family_patch/v1"
WORKSPACE = Path(__file__).resolve().parents[1]
CATALOG = WORKSPACE / "reports/assets/apf_helmet_family_layout.json"
EXPECTED_CATALOG_SHA256 = "29c3f097f63105f0ae2067d8f99f0ce8666e447d8bf13de4b1cb071e9638ed4c"
EXPECTED_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"


class HelmetFamilyPatchError(ValueError):
    """Raised when the family catalog or target is not exact."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_catalog() -> dict[str, object]:
    payload = CATALOG.read_bytes()
    if sha256(payload) != EXPECTED_CATALOG_SHA256:
        raise HelmetFamilyPatchError("helmet-family catalog hash changed")
    document = json.loads(payload)
    if document.get("schema") != "apf_helmet_family_layout/v1":
        raise HelmetFamilyPatchError("helmet-family catalog schema changed")
    source = document["source"]
    if (source["sha256_before"] != EXPECTED_VOLUME_SHA256 or
            source["sha256_after"] != EXPECTED_VOLUME_SHA256):
        raise HelmetFamilyPatchError("catalog is not pinned to retail APF 0A")
    boundary = document["claim_boundary"]
    if (not boundary["structural_layout_generalizes_across_all_24_helmets"] or
            not boundary["in_memory_transport_and_fixed_allocation_rebuild_proved_for_all_24"] or
            not boundary["helmet_normal_preservation_proved_for_all_24"] or
            boundary["retail_or_copied_game_volume_written"]):
        raise HelmetFamilyPatchError("catalog proof boundary changed")
    rows = document["helmets"]
    if len(rows) != 24 or [row["asset_index"] for row in rows] != list(range(24)):
        raise HelmetFamilyPatchError("helmet target roster changed")
    return document


def target_record(asset_index: int) -> dict[str, object]:
    if not 0 <= asset_index < 24:
        raise HelmetFamilyPatchError("--asset-index must be in 0..23")
    return _load_catalog()["helmets"][asset_index]  # type: ignore[index,return-value]


def build_patch(
    index_path: Path, png_path: Path, asset_index: int
) -> archive_patch.PatchResult:
    row = target_record(asset_index)
    result = transport.build_patch(index_path, png_path, row)
    source = result.manifest["source"]
    if (source["outer_entry_index"] != row["outer_table_index"] or
            source["entry_sha256"] != row["outer_allocation"]["sha256"] or
            source["texture_sha256"] != row["inner_file"]["texture_sha256"]):
        raise HelmetFamilyPatchError("transport selected a target outside catalog")
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
        "team_bank_use_count": row["team_bank_use_count"],
        "team_bank_uses": row["team_bank_uses"],
        "editing_affects_every_listed_use": True,
        "png_contract": "R/G are DXN channels; B=0; A=255",
        "helmet_color_channel_meanings_named": False,
        "runtime_visibility_proved": False,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path,
                        help="user-owned retail APF 0A")
    parser.add_argument("--asset-index", required=True, type=int,
                        help="uniform_helmet index 0..23")
    parser.add_argument("--png", required=True, type=Path,
                        help="256x1024 RGBA PNG: R/G data, B=0, A=255")
    parser.add_argument("--output-entry", type=Path,
                        help="new rebuilt logical IFF path")
    parser.add_argument("--output-volume", type=Path,
                        help="new copied 0A path")
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    reservation: archive_patch.OutputReservation | None = None
    manifest_path = args.manifest.expanduser()
    try:
        index_path, png_path = args.index.expanduser(), args.png.expanduser()
        output_entry = args.output_entry.expanduser() if args.output_entry else None
        output_volume = args.output_volume.expanduser() if args.output_volume else None
        archive_patch._preflight_output_paths(  # type: ignore[attr-defined]
            [index_path, png_path],
            [("manifest", manifest_path), ("output entry", output_entry),
             ("output volume", output_volume)],
        )
        reservation = archive_patch._reserve_new(manifest_path)  # type: ignore[attr-defined]
        row = target_record(args.asset_index)
        result = build_patch(index_path, png_path, args.asset_index)
        archive = apf_outer.parse_archive(index_path)
        document = result.manifest
        if output_entry is not None:
            archive_patch._write_new(output_entry, result.entry_bytes)  # type: ignore[attr-defined]
            document["output_entry"] = {
                "path": str(output_entry), "size": len(result.entry_bytes),
                "sha256": sha256(result.entry_bytes),
            }
        if output_volume is not None:
            document["copied_volume"] = archive_patch._write_copied_volume(  # type: ignore[attr-defined]
                index_path, output_volume,
                archive.entries[int(row["outer_table_index"])], result.entry_bytes,
            )
        archive_patch._commit_reserved(  # type: ignore[attr-defined]
            manifest_path, reservation,
            (json.dumps(document, indent=2) + "\n").encode("utf-8"),
        )
        archive_patch._close_reserved(reservation)  # type: ignore[attr-defined]
        reservation = None
        print(
            "APF_HELMET_FAMILY_PATCH_PASS "
            f"mode={document['mode']} asset={args.asset_index} "
            f"entry={row['outer_table_index']} sha256={sha256(result.entry_bytes)} "
            "runtime_visibility=false"
        )
    except (HelmetFamilyPatchError, transport.HelmetTransportError,
            dxn_mips.MipLayoutError, archive_patch.PatchError,
            apf_inner.FormatError, apf_outer.FormatError, OSError) as exc:
        if reservation is not None:
            archive_patch._abort_reserved(manifest_path, reservation)  # type: ignore[attr-defined]
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
