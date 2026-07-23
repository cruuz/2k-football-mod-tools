#!/usr/bin/env python3
"""Independently verify the fixed Assassins helmet-selector witness.

The verifier imports neither a selector writer nor an allocation planner.  It
reparses both complete volumes, derives the two helmet records through the
ROST pointer graph, independently rebuilds the expected H7A/IFF entry and
manifest, and proves that no byte outside outer entry 1126 changed.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
from pathlib import Path
import struct
import sys
from typing import Any

import apf_uniform_selector_verify as selectors


ROOT = Path(__file__).resolve().parents[1]
ALLOCATION_REPORT = ROOT / "reports/assets/apf_uniform_selector_allocation.json"
ALLOCATION_REPORT_SIZE = 264_669
ALLOCATION_REPORT_SHA256 = "389efe3a90839bcc2210df6292817920b7bbfa1f2c0389ee632b2915adcdbef6"
WRITER_DEPENDENCY = ROOT / "tools/apf_uniform_selector_patch.py"
WRITER_DEPENDENCY_SIZE = 27_197
WRITER_DEPENDENCY_SHA256 = "4b107f2d77d33d65d1e91ccc96e3a80bd23f732040cdeee9e0c61a6ac16db3fe"

PATCH_SCHEMA = "apf_assassins_helmet_selector_patch/v1"
VERIFY_SCHEMA = "apf_assassins_helmet_selector_verify/v1"
MAX_MANIFEST_BYTES = 256 * 1024
TEAM_INDEX = 1
TEAM_NAME = "Assassins"
FAMILY = "helmet"
SELECTOR_SLOT = 3
EXPECTED_ASSET = 1
REPLACEMENT_ASSET = 2
EXPECTED_OFFSETS = (0x1E10B0, 0x1E1040)
EXPECTED_RECORD_INDICES = (465, 451)

base = selectors.base


class VerifyError(ValueError):
    """The fixed witness differs from the independent reconstruction."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _expected_entry_and_manifest(
    source_entry: bytes,
    source_iff: Any,
    source_decoded: bytes,
    source_tokens: list[Any],
    source_consumed: int,
    layout: selectors.SelectorLayout,
    output_name: str,
    output_volume_sha256: str,
) -> tuple[bytes, bytes, dict[str, Any], list[int]]:
    helmet = layout.families[FAMILY]
    offsets = helmet.offsets[TEAM_INDEX]
    indices = helmet.record_indices[TEAM_INDEX]
    require(
        offsets == EXPECTED_OFFSETS
        and indices == EXPECTED_RECORD_INDICES
        and helmet.assets[TEAM_INDEX] == EXPECTED_ASSET
        and tuple(source_decoded[offset] for offset in offsets)
        == (EXPECTED_ASSET, EXPECTED_ASSET),
        "Assassins helmet source witness differs",
    )
    wanted = bytearray(source_decoded)
    for offset in offsets:
        wanted[offset] = REPLACEMENT_ASSET
    wanted_bytes = bytes(wanted)
    differences = [
        offset
        for offset, pair in enumerate(zip(source_decoded, wanted_bytes))
        if pair[0] != pair[1]
    ]
    require(differences == sorted(offsets), "independent decoded edit set differs")
    for offset in offsets:
        require(
            wanted_bytes[offset + 1 : offset + base.SELECTOR_STRIDE]
            == source_decoded[offset + 1 : offset + base.SELECTOR_STRIDE],
            "opaque selector bytes differ",
        )

    payload, metrics = base.encode_preserving_h7a(
        source_tokens,
        len(source_iff.payload) - source_consumed,
        wanted_bytes,
    )
    require(
        len(payload) <= base.MAX_H7A_PAYLOAD_SIZE,
        "independent H7A payload exceeds fixed allocation",
    )
    stored = struct.pack(
        ">5I",
        base.H7A_MAGIC,
        base.DECODED_SIZE,
        base.H7A_HEADER_SIZE + len(payload),
        base.H7A_UNKNOWN,
        base.H7A_SHIFT,
    ) + payload
    header = bytearray(source_entry[: base.IFF_HEADER_SIZE])
    struct.pack_into(
        ">8I",
        header,
        base.IFF_BLOCK_TABLE_OFFSET,
        base.IFF_BLOCK_HASH,
        base.IFF_BLOCK_HASH,
        0x20,
        base.DECODED_SIZE,
        base.H7A_UNKNOWN,
        base.IFF_HEADER_SIZE,
        len(stored),
        0,
    )
    file_length = base.IFF_HEADER_SIZE + len(stored)
    struct.pack_into(">I", header, 0x08, file_length)
    active = bytes(header) + stored + source_iff.footer
    require(len(active) <= base.OUTER_SIZE, "independent ROST exceeds allocation")
    rebuilt = active + bytes(base.OUTER_SIZE - len(active))
    decoded_check, _tokens, _consumed = base.decode_h7a(payload)
    require(decoded_check == wanted_bytes, "independent H7A decode differs")

    changed_offset_digest = sha256_bytes(
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
            "fixed_payload_limit_bytes": base.MAX_H7A_PAYLOAD_SIZE,
            "headroom_bytes_after": base.MAX_H7A_PAYLOAD_SIZE - len(payload),
            "payload_sha256_after": sha256_bytes(payload),
            "payload_size_after": len(payload),
            "payload_size_before": base.SOURCE_H7A_PAYLOAD_SIZE,
            "retail_payload_consumed_bytes": source_consumed,
            "retail_token_count": len(source_tokens),
            "shift": base.H7A_SHIFT,
            **metrics,
        },
        "preservation": {
            "authorized_decoded_byte_count": 2,
            "changed_decoded_offsets_sha256": changed_offset_digest,
            "decoded_changed_byte_count": 2,
            "decoded_output_sha256": sha256_bytes(wanted_bytes),
            "footer_bit_exact": True,
            "online_and_user_team_selector_records_bit_exact": True,
            "opaque_selector_bytes_1_through_7_bit_exact": True,
            "other_decoded_bytes_bit_exact": True,
            "output_zero_tail_bytes": (
                base.OUTER_SIZE - file_length - base.FOOTER_TOTAL
            ),
            "rebuilt_iff_reparsed": True,
        },
        "result": {
            "copied_volume": {
                "name": output_name,
                "outside_outer_entry_prefix_sha256": base.SOURCE_PREFIX_SHA256,
                "outside_outer_entry_suffix_sha256": base.SOURCE_SUFFIX_SHA256,
                "sha256": output_volume_sha256,
                "size_bytes": base.SOURCE_VOLUME_SIZE,
            },
            "file_length_after": file_length,
            "outer_entry_sha256": sha256_bytes(rebuilt),
            "outer_entry_size": len(rebuilt),
        },
        "schema": PATCH_SCHEMA,
        "source": {
            "allocation_report_sha256": ALLOCATION_REPORT_SHA256,
            "allocation_report_size_bytes": ALLOCATION_REPORT_SIZE,
            "decoded_roster_sha256": base.DECODED_SHA256,
            "outer_entry_index": base.OUTER_INDEX,
            "outer_entry_pack_offset": base.OUTER_OFFSET,
            "outer_entry_sha256": base.OUTER_SHA256,
            "retail_0A_sha256": base.SOURCE_VOLUME_SHA256,
            "retail_0A_size_bytes": base.SOURCE_VOLUME_SIZE,
            "writer_dependency_sha256": WRITER_DEPENDENCY_SHA256,
            "writer_dependency_size_bytes": WRITER_DEPENDENCY_SIZE,
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
    return rebuilt, wanted_bytes, manifest, differences


def verify(
    source_path: Path,
    output_path: Path,
    manifest_path: Path,
    report_path: Path | None = None,
) -> dict[str, Any]:
    with ExitStack() as stack:
        allocation_file = stack.enter_context(
            base.BoundFile(ALLOCATION_REPORT, "allocation report")
        )
        dependency_file = stack.enter_context(
            base.BoundFile(WRITER_DEPENDENCY, "writer dependency")
        )
        source = stack.enter_context(base.BoundFile(source_path, "retail source 0A"))
        output = stack.enter_context(base.BoundFile(output_path, "copied output 0A"))
        manifest_file = stack.enter_context(
            base.BoundFile(manifest_path, "writer manifest")
        )
        bound = [allocation_file, dependency_file, source, output, manifest_file]
        require(
            len({item.identity for item in bound}) == len(bound),
            "an authority/input/output pair aliases one inode",
        )
        allocation, _raw = selectors.load_compact_authority(
            allocation_file,
            ALLOCATION_REPORT_SIZE,
            ALLOCATION_REPORT_SHA256,
            "apf2k8_uniform_selector_allocation/v1",
            "allocation report",
        )
        require(
            dependency_file.size == WRITER_DEPENDENCY_SIZE
            and dependency_file.digest() == WRITER_DEPENDENCY_SHA256,
            "writer dependency identity differs",
        )
        require(
            source.size == base.SOURCE_VOLUME_SIZE
            and source.supplied_path.name == "0A",
            "source is not the pinned retail 0A shape",
        )
        supplied_manifest, _manifest_raw = base.load_canonical_json(
            manifest_file, MAX_MANIFEST_BYTES, "writer manifest"
        )

        source_outer = base.parse_outer_directory(source)
        output_outer = base.parse_outer_directory(output)
        require(source_outer == output_outer, "output outer directory routing differs")
        source_entry = source.read(source_outer.pack_offset, source_outer.size)
        output_entry = output.read(output_outer.pack_offset, output_outer.size)
        require(
            sha256_bytes(source_entry) == base.OUTER_SHA256,
            "retail ROST outer-entry identity differs",
        )
        source_iff = base.parse_iff(source_entry)
        require(
            source_iff.file_length == base.SOURCE_FILE_LENGTH
            and len(source_iff.payload) == base.SOURCE_H7A_PAYLOAD_SIZE
            and sha256_bytes(source_iff.footer) == base.FOOTER_SHA256,
            "retail ROST IFF/footer identity differs",
        )
        source_decoded, source_tokens, source_consumed = base.decode_h7a(
            source_iff.payload
        )
        require(
            sha256_bytes(source_decoded) == base.DECODED_SHA256,
            "retail decoded ROST identity differs",
        )
        source_layout = selectors.derive_selector_layout(
            source_decoded, allocation, require_retail_vectors=True
        )
        volume_facts = base.compare_complete_volumes(source, output)
        expected_entry, wanted_decoded, expected_manifest, differences = (
            _expected_entry_and_manifest(
                source_entry,
                source_iff,
                source_decoded,
                source_tokens,
                source_consumed,
                source_layout,
                output.supplied_path.name,
                str(volume_facts["output_sha256"]),
            )
        )
        require(output_entry == expected_entry, "output ROST entry differs")
        output_iff = base.parse_iff(output_entry)
        output_decoded, _output_tokens, _output_consumed = base.decode_h7a(
            output_iff.payload
        )
        require(output_decoded == wanted_decoded, "output decoded ROST differs")
        output_layout = selectors.derive_selector_layout(
            output_decoded, allocation, require_retail_vectors=False
        )
        require(
            output_layout.all_pointer_targets == source_layout.all_pointer_targets,
            "output selector pointer graph differs",
        )
        expected_assets = list(source_layout.families[FAMILY].assets)
        expected_assets[TEAM_INDEX] = REPLACEMENT_ASSET
        require(
            output_layout.families[FAMILY].assets == tuple(expected_assets),
            "output helmet asset vector differs",
        )
        require(
            supplied_manifest == expected_manifest,
            "writer manifest differs from independent reconstruction",
        )
        require(
            volume_facts["changed_bytes_inside_outer_entry"]
            == sum(left != right for left, right in zip(source_entry, expected_entry)),
            "complete-volume changed-byte accounting differs",
        )

        report = {
            "claims": {
                "all_bytes_outside_outer_entry_bit_exact": True,
                "all_other_team_family_assignments_bit_exact": True,
                "complete_manifest_reconstructed": True,
                "emulator_runtime_visibility_proved": False,
                "original_xbox_360_hardware_proved": False,
                "selector_byte_0_only": True,
                "selector_bytes_1_through_7_bit_exact": True,
                "target_is_fixed_not_user_authored": True,
            },
            "decoded_changed_byte_count": len(differences),
            "decoded_output_sha256": sha256_bytes(wanted_decoded),
            "manifest_sha256": manifest_file.digest(),
            "outer_entry_sha256": sha256_bytes(output_entry),
            "output_volume_sha256": volume_facts["output_sha256"],
            "payload_size_after": len(output_iff.payload),
            "schema": VERIFY_SCHEMA,
            "target": expected_manifest["target"],
        }
        for item in bound:
            item.assert_stable()
        if report_path is not None:
            reservation = base.ReportReservation(report_path, bound)
            try:
                reservation.commit(base.canonical_json_bytes(report))
                for item in bound:
                    item.assert_stable()
                reservation.finalize()
            finally:
                reservation.close()
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-index", required=True, type=Path)
    parser.add_argument("--output-volume", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    try:
        report = verify(
            args.source_index,
            args.output_volume,
            args.manifest,
            args.json,
        )
        print(
            "APF_ASSASSINS_HELMET_SELECTOR_VERIFY_PASS "
            f"changed_bytes={report['decoded_changed_byte_count']} "
            f"payload={report['payload_size_after']} "
            "runtime=false hardware=false"
        )
        return 0
    except (
        VerifyError,
        selectors.VerifyError,
        base.VerifyError,
        KeyError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
