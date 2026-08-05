#!/usr/bin/env python3
"""Build the fixed APF Assassins helmet-selector 1-to-2 witness.

This is deliberately not an arbitrary selector editor.  It creates a copied
retail ``0A`` in which only byte 0 of team 1's two pointer-derived helmet
selector records changes from asset 1 to asset 2.  Its purpose is to isolate
the pending Xenia witness from the broader deterministic all-family plan.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any

import apf_uniform_selector_patch as core


ROOT = Path(__file__).resolve().parents[1]
CORE_FILE = ROOT / "tools/apf_uniform_selector_patch.py"
CORE_FILE_SIZE = 27_577
CORE_FILE_SHA256 = "dff67326a52f61bd479b13aad72c59878d8f4a602692a3cb85bf8708781abfef"

SCHEMA = "apf_assassins_helmet_selector_patch/v1"
TEAM_INDEX = 1
TEAM_NAME = "Assassins"
FAMILY = "helmet"
SELECTOR_SLOT = 3
EXPECTED_ASSET = 1
REPLACEMENT_ASSET = 2
EXPECTED_OFFSETS = (0x1E10B0, 0x1E1040)
EXPECTED_RECORD_INDICES = (465, 451)

transport = core.transport


class PatchError(ValueError):
    """The fixed witness or its copied-volume transaction differs."""


def _check_dependency() -> None:
    raw = transport._read_bound_file(
        CORE_FILE, CORE_FILE_SIZE, "checked all-family writer dependency"
    )
    if len(raw) != CORE_FILE_SIZE or core.sha256_bytes(raw) != CORE_FILE_SHA256:
        raise PatchError("all-family writer dependency identity drift")


def build_patch(index_path: Path) -> transport.BuildResult:
    _check_dependency()
    allocation, _allocation_raw, _capacity, _capacity_raw = core.load_authorities()
    (
        _,
        entry,
        record,
        original_entry,
        original_stored,
        decoded,
        _,
    ) = transport._validate_source(index_path)
    layout = core.derive_selector_layout(
        decoded, allocation, require_retail_vectors=True
    )
    helmet = layout.families[FAMILY]
    offsets = helmet.offsets[TEAM_INDEX]
    indices = helmet.record_indices[TEAM_INDEX]
    if (
        offsets != EXPECTED_OFFSETS
        or indices != EXPECTED_RECORD_INDICES
        or helmet.assets[TEAM_INDEX] != EXPECTED_ASSET
        or tuple(decoded[offset] for offset in offsets)
        != (EXPECTED_ASSET, EXPECTED_ASSET)
    ):
        raise PatchError("Assassins helmet source witness drift")

    wanted = bytearray(decoded)
    for offset in offsets:
        wanted[offset] = REPLACEMENT_ASSET
    wanted_bytes = bytes(wanted)
    differences = core._difference_offsets(decoded, wanted_bytes)
    if differences != sorted(offsets):
        raise PatchError("decoded edit set is not exactly the two helmet bytes")
    for offset in offsets:
        if wanted_bytes[offset + 1 : offset + transport.SELECTOR_STRIDE] != decoded[
            offset + 1 : offset + transport.SELECTOR_STRIDE
        ]:
            raise PatchError("opaque selector bytes changed")

    payload, metrics = transport.encode_preserving_h7a(
        original_stored[20:], decoded, wanted_bytes, transport.H7A_SHIFT
    )
    if len(payload) > transport.MAX_H7A_PAYLOAD_SIZE:
        raise PatchError("rebuilt H7A payload exceeds the fixed allocation")
    stored = struct.pack(
        ">5I",
        transport.apf_inner.H7A_MAGIC,
        transport.DECODED_SIZE,
        20 + len(payload),
        transport.H7A_UNKNOWN,
        transport.H7A_SHIFT,
    ) + payload
    header = bytearray(original_entry[: transport.IFF_HEADER_SIZE])
    block = record.blocks[0]
    struct.pack_into(
        ">8I",
        header,
        transport.apf_inner.IFF_HEADER_SIZE,
        block.name_hash,
        block.type_hash,
        block.unknown_08,
        transport.DECODED_SIZE,
        transport.H7A_UNKNOWN,
        transport.IFF_HEADER_SIZE,
        len(stored),
        block.indexed,
    )
    file_length = transport.IFF_HEADER_SIZE + len(stored)
    struct.pack_into(">I", header, 0x08, file_length)
    footer = original_entry[
        transport.SOURCE_FILE_LENGTH :
        transport.SOURCE_FILE_LENGTH + transport.FOOTER_TOTAL
    ]
    active = bytes(header) + stored + footer
    if len(active) > transport.OUTER_SIZE:
        raise PatchError("rebuilt ROST exceeds the fixed outer allocation")
    rebuilt = active + bytes(transport.OUTER_SIZE - len(active))

    memory = transport.BytesReader(rebuilt)
    rebuilt_record = transport.apf_inner.parse_iff(memory, entry)
    rebuilt_decoded = transport.apf_inner.decode_block(
        memory, rebuilt_record, 0, 16 * 1024 * 1024
    )
    if rebuilt_record.warnings or rebuilt_decoded != wanted_bytes:
        raise PatchError("rebuilt helmet witness did not reparse/decode exactly")
    if rebuilt[file_length : file_length + transport.FOOTER_TOTAL] != footer:
        raise PatchError("rebuilt helmet witness footer drift")
    if any(rebuilt[file_length + transport.FOOTER_TOTAL :]):
        raise PatchError("rebuilt helmet witness tail is not zero")

    output_layout = core.derive_selector_layout(
        rebuilt_decoded, allocation, require_retail_vectors=False
    )
    output_helmet = output_layout.families[FAMILY]
    if (
        output_layout.all_pointer_targets != layout.all_pointer_targets
        or output_helmet.offsets != helmet.offsets
        or output_helmet.record_indices != helmet.record_indices
    ):
        raise PatchError("output selector pointer graph drift")
    expected_assets = list(helmet.assets)
    expected_assets[TEAM_INDEX] = REPLACEMENT_ASSET
    if output_helmet.assets != tuple(expected_assets):
        raise PatchError("output helmet asset vector drift")

    changed_offset_digest = core.sha256_bytes(
        b"".join(offset.to_bytes(4, "big") for offset in differences)
    )
    manifest: dict[str, Any] = {
        "claim_flags": {
            "all_other_team_family_assignments_bit_exact": True,
            "emulator_runtime_visibility_proved": False,
            "original_xbox_360_hardware_proved": False,
            "production_gui_exposed": False,
            "selector_byte_0_filename_ownership_proved": True,
            "selector_bytes_1_through_7_semantics_proved": False,
            "target_is_fixed_not_user_authored": True,
        },
        "compression": {
            "fixed_payload_limit_bytes": transport.MAX_H7A_PAYLOAD_SIZE,
            "headroom_bytes_after": transport.MAX_H7A_PAYLOAD_SIZE - len(payload),
            "payload_sha256_after": core.sha256_bytes(payload),
            "payload_size_after": len(payload),
            "payload_size_before": transport.SOURCE_H7A_PAYLOAD_SIZE,
            "shift": transport.H7A_SHIFT,
            **metrics,
        },
        "preservation": {
            "authorized_decoded_byte_count": 2,
            "changed_decoded_offsets_sha256": changed_offset_digest,
            "decoded_changed_byte_count": 2,
            "decoded_output_sha256": core.sha256_bytes(wanted_bytes),
            "footer_bit_exact": True,
            "online_and_user_team_selector_records_bit_exact": True,
            "opaque_selector_bytes_1_through_7_bit_exact": True,
            "other_decoded_bytes_bit_exact": True,
            "output_zero_tail_bytes": (
                transport.OUTER_SIZE - file_length - transport.FOOTER_TOTAL
            ),
            "rebuilt_iff_reparsed": True,
        },
        "result": {
            "file_length_after": file_length,
            "outer_entry_sha256": core.sha256_bytes(rebuilt),
            "outer_entry_size": len(rebuilt),
        },
        "schema": SCHEMA,
        "source": {
            "allocation_report_sha256": core.ALLOCATION_REPORT_SHA256,
            "allocation_report_size_bytes": core.ALLOCATION_REPORT_SIZE,
            "decoded_roster_sha256": transport.DECODED_SHA256,
            "outer_entry_index": transport.OUTER_INDEX,
            "outer_entry_pack_offset": transport.OUTER_OFFSET,
            "outer_entry_sha256": transport.OUTER_SHA256,
            "retail_0A_sha256": transport.SOURCE_VOLUME_SHA256,
            "retail_0A_size_bytes": transport.SOURCE_VOLUME_SIZE,
            "writer_dependency_sha256": CORE_FILE_SHA256,
            "writer_dependency_size_bytes": CORE_FILE_SIZE,
        },
        "target": {
            "bank_selector_decoded_offsets": list(offsets),
            "bank_selector_record_indices": list(indices),
            "expected_retail_asset_index": EXPECTED_ASSET,
            "family": FAMILY,
            "replacement_asset_index": REPLACEMENT_ASSET,
            "selector_slot": SELECTOR_SLOT,
            "team_index": TEAM_INDEX,
            "team_name": TEAM_NAME,
        },
    }
    return transport.BuildResult(rebuilt, manifest)


def write_output(
    index_path: Path, output_volume: Path, manifest_path: Path
) -> dict[str, Any]:
    index_path = index_path.expanduser()
    output_volume = transport._new_output_path(output_volume, "output volume")
    manifest_path = transport._new_output_path(manifest_path, "manifest")
    transport.transport._preflight_output_paths(  # type: ignore[attr-defined]
        [
            index_path,
            CORE_FILE,
            core.ALLOCATION_REPORT,
            core.CAPACITY_REPORT,
            core.RECIPE_SCHEMA_FILE,
            core.MANIFEST_SCHEMA_FILE,
        ],
        [("output volume", output_volume), ("manifest", manifest_path)],
    )
    source: transport.BoundSourceVolume | None = None
    output_reservation: transport.BoundOutputReservation | None = None
    manifest_reservation: transport.BoundOutputReservation | None = None
    keep = False
    try:
        result = build_patch(index_path)
        source = transport._bind_source_volume(index_path)
        output_reservation = transport._reserve_bound_output(
            output_volume, stat.S_IMODE(source.metadata.st_mode)
        )
        manifest_reservation = transport._reserve_bound_output(manifest_path, 0o644)
        copied, output_times = transport._write_bound_copied_volume(
            source, output_reservation, result.entry
        )
        result.manifest["result"]["copied_volume"] = {
            "name": output_volume.name,
            "outside_outer_entry_prefix_sha256": copied["outside_replacement"]["prefix_sha256"],
            "outside_outer_entry_suffix_sha256": copied["outside_replacement"]["suffix_sha256"],
            "sha256": copied["output_volume_sha256"],
            "size_bytes": copied["volume_size"],
        }
        document = transport.canonical_json_bytes(result.manifest)
        manifest_times = transport._commit_bound_output(
            manifest_reservation, document
        )
        transport._assert_bound_source(source)
        transport._assert_bound_output(
            output_reservation,
            expected_size=transport.SOURCE_VOLUME_SIZE,
            expected_times=output_times,
        )
        transport._assert_bound_output(
            manifest_reservation,
            expected_size=len(document),
            expected_times=manifest_times,
        )
        keep = True
        return result.manifest
    finally:
        if manifest_reservation is not None:
            transport._close_bound_output(manifest_reservation, keep=keep)
        if output_reservation is not None:
            transport._close_bound_output(output_reservation, keep=keep)
        if source is not None:
            try:
                os.close(source.descriptor)
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--output-volume", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = write_output(args.index, args.output_volume, args.manifest)
        print(
            "APF_ASSASSINS_HELMET_SELECTOR_PATCH_PASS "
            f"changed_bytes={manifest['preservation']['decoded_changed_byte_count']} "
            f"payload={manifest['compression']['payload_size_after']} "
            f"headroom={manifest['compression']['headroom_bytes_after']} "
            "runtime=false hardware=false"
        )
        return 0
    except (
        PatchError,
        core.PatchError,
        transport.PatchError,
        transport.apf_outer.FormatError,
        transport.apf_inner.FormatError,
        transport.apf_roster.RosterError,
        transport.transport.PatchError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
