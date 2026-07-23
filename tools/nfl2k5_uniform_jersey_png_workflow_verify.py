#!/usr/bin/env python3
"""Independently verify a generalized compatible-jersey workflow XISO."""

from __future__ import annotations

import argparse
import copy
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

import nfl2k5_jersey_png_workflow as ownership
import nfl2k5_jersey_png_workflow_verify as old_verify
import nfl2k5_uniform_jersey_png_workflow as workflow
from nfl_jersey_tset_dynamic_validate import (
    ValidatedImport,
    independent_decode_target,
    validate_dynamic_import,
)
import nfl_jersey_tset_png_import as current_import
from nfl_jersey_tset_targets import DEFAULT_REPORT, JerseyTarget, select_target
import nfl_jersey_tset_xiso_patch as xwriter
import nfl_tset_png_import_xiso_generic_patch as helper
from nfl_txtr import HEADER, rebuild_compressed_chunk_fixed_span
import nfl_uniform_color_xiso_direct_patch as common


LEGACY_WORKFLOW_SCHEMA = "nfl2k5_uniform_jersey_png_workflow/v2"
LEGACY_IMPORT_SCHEMA = "nfl2k5_jersey_tset_png_import/v2"
LEGACY_WRITER_SCHEMA = "nfl2k5_jersey_tset_xiso_patch/v2"

WORKFLOW_FIELDS = {
    "schema", "target", "source", "compatibility_report", "inputs",
    "import", "output", "xdvdfs", "patch", "safety", "claims",
}
IMPORT_FIELDS = {
    "schema", "source_index", "canonical_inventory", "compatibility_report",
    "target", "input", "mips", "quantization", "layout", "compression",
    "rebuild", "previews", "claims", "outputs",
}
LEGACY_VALIDATED_FIELDS = (
    "selector", "logical_name", "outer_index", "span_sha256",
    "decoded_sha256", "import_manifest_sha256", "clean_png_sha256",
    "mud_source_kind", "mud_png_sha256", "encoded_bytes", "stored_size",
    "zero_padding_bytes", "palette_entries", "quantization_differing_pixels",
    "mip_count", "preview_count", "shared_indices",
)
LEGACY_REBUILD_INFO_FIELDS = (
    "kind", "stored_size", "system_bytes", "video_bytes", "stream_tag",
    "offset_bits", "original_consumed_bytes", "original_unused_bytes",
    "recompressed_bytes", "zero_padding_bytes", "template_decoded_matches_input",
    "compressed_stream_matches_template", "complete_span_matches_template",
    "decoded_sha256", "rebuilt_span_sha256",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def current_import_target(target: JerseyTarget, rebuilt_overlap_scratch_bytes: int) \
        -> dict[str, object]:
    return {
        "asset_code": target.asset_code,
        "side": target.side,
        "variant": target.variant,
        "selector": target.selector,
        "logical_name": target.logical_name,
        "outer_index": target.outer_index,
        "outer_id": f"0x{target.outer_id:08x}",
        "outer_size": target.outer_size,
        "chunk_index": target.chunk_index,
        "chunk_offset": target.chunk_offset,
        "stored_size": target.stored_size,
        "complete_span_size": target.span_size,
        "system_bytes": target.system_bytes,
        "video_bytes": target.video_bytes,
        "template_overlap_scratch_bytes": target.overlap_scratch_bytes,
        "rebuilt_overlap_scratch_bytes": rebuilt_overlap_scratch_bytes,
        "stream_tag": target.stream_tag,
        "offset_bits": target.offset_bits,
        "template_span_sha256": target.span_sha256,
        "template_decoded_sha256": target.decoded_sha256,
        "layout_signature_sha256": target.layout_signature_sha256,
        "pack_name": target.pack_name,
        "pack_ordinal": target.pack_ordinal,
        "span_pack_offset": target.pack_offset,
        "xiso_pack_path": target.xiso_pack_path,
        "xiso_pack_sector": target.xiso_pack_sector,
        "xiso_absolute_span_offset": target.xiso_absolute_span_offset,
        "system_bytes_preserved": True,
        "descriptor_records_preserved": True,
    }


def legacy_import_target(target: JerseyTarget) -> dict[str, object]:
    current = current_import_target(target, target.overlap_scratch_bytes)
    current["overlap_scratch_bytes"] = current.pop(
        "template_overlap_scratch_bytes"
    )
    del current["rebuilt_overlap_scratch_bytes"]
    return current


def current_import_claims() -> dict[str, object]:
    return {
        "real_png_input_consumed": True,
        "all_clean_and_mud_mips_generated": True,
        "all_mips_swizzled_and_decoded": True,
        "all_preview_pngs_strictly_reparsed": True,
        "two_reference_shared_index_layout_preserved": True,
        "target_selected_from_pinned_634_package_compatibility_inventory": True,
        "target_wrapper_preserved_except_loader_overlap_scratch": True,
        "loader_in_place_decode_guarded": True,
        "fixed_span_only": True,
        "output_exclusively_created": True,
        "originals_modified": False,
        "xiso_created": False,
        "title_executed": False,
        "runtime_visibility_proved": False,
        "models_or_other_texture_chunks_supported": False,
        "portme": (
            "PORTME: separately audit any non-jersey chunk or model layout before import."
        ),
    }


def legacy_import_claims() -> dict[str, object]:
    claims = current_import_claims()
    del claims["target_wrapper_preserved_except_loader_overlap_scratch"]
    del claims["loader_in_place_decode_guarded"]
    claims["target_specific_wrapper_and_allocation_preserved"] = True
    return claims


def validate_legacy_dynamic_import(
    *,
    target: JerseyTarget,
    compatibility_path: Path,
    source_span: bytes,
    replacement_span: bytes,
    import_manifest_payload: bytes,
    clean_png_name: str,
    clean_png_payload: bytes,
    mud_png_name: str | None,
    mud_png_payload: bytes | None,
    preview_payloads: dict[str, bytes],
    replacement_span_name: str | None = None,
    import_manifest_name: str | None = None,
    preview_directory_name: str | None = None,
) -> tuple[ValidatedImport, dict[str, object]]:
    """Verify a preserved v2 artifact without weakening the v3 validator.

    Version 2 kept wrapper word +0x14 byte-identical to the retail template.
    Version 3 raises that loader overlap-scratch word when required.  The VC-LZ
    body is otherwise deterministic and identical.  Upgrade the historical
    bytes and manifest in memory, run the strict v3 validator, and separately
    require the supplied v2 projection to match its historical schema exactly.
    No artifact is rewritten.
    """

    try:
        legacy_manifest = json.loads(import_manifest_payload)
    except json.JSONDecodeError as exc:
        raise common.PatchError("legacy v2 import manifest is invalid JSON") from exc
    common.require(
        isinstance(legacy_manifest, dict) and
        import_manifest_payload == ownership.canonical_manifest_payload(
            legacy_manifest
        ) and
        set(legacy_manifest) == IMPORT_FIELDS and
        legacy_manifest.get("schema") == LEGACY_IMPORT_SCHEMA,
        "legacy v2 import manifest schema/encoding mismatch",
    )
    common.require(
        len(source_span) == len(replacement_span) == target.span_size and
        HEADER.unpack_from(source_span) == target.complete_header and
        HEADER.unpack_from(replacement_span) == target.complete_header,
        "legacy v2 replacement did not preserve the retail wrapper",
    )

    decoded, _ = independent_decode_target(replacement_span[HEADER.size:], target)
    upgraded_span, rebuild_info = rebuild_compressed_chunk_fixed_span(
        source_span, decoded
    )
    common.require(
        replacement_span == source_span[:HEADER.size] + upgraded_span[HEADER.size:],
        "legacy v2 replacement body differs from deterministic v3 reconstruction",
    )
    rebuild_record = asdict(rebuild_info)
    legacy_span_sha256 = sha256_bytes(replacement_span)
    expected_legacy_rebuild = {
        key: rebuild_record[key] for key in LEGACY_REBUILD_INFO_FIELDS
    }
    expected_legacy_rebuild["rebuilt_span_sha256"] = legacy_span_sha256
    expected_legacy_rebuild.update({
        "decoded_roundtrip_sha256": sha256_bytes(decoded),
        "complete_span_sha256": legacy_span_sha256,
        "complete_span_size": target.span_size,
        "fixed_span_fit": True,
        "zero_padding_verified": replacement_span[
            HEADER.size + rebuild_info.recompressed_bytes:
        ] == bytes(rebuild_info.zero_padding_bytes),
    })
    common.require(
        legacy_manifest.get("target") == legacy_import_target(target) and
        legacy_manifest.get("rebuild") == expected_legacy_rebuild and
        legacy_manifest.get("claims") == legacy_import_claims(),
        "legacy v2 import target/rebuild/claims mismatch",
    )

    upgraded_manifest = copy.deepcopy(legacy_manifest)
    upgraded_manifest["schema"] = current_import.SCHEMA
    upgraded_manifest["target"] = current_import_target(
        target, rebuild_info.rebuilt_overlap_scratch_bytes
    )
    upgraded_manifest["rebuild"] = {
        **rebuild_record,
        "decoded_roundtrip_sha256": sha256_bytes(decoded),
        "complete_span_sha256": sha256_bytes(upgraded_span),
        "complete_span_size": target.span_size,
        "fixed_span_fit": True,
        "zero_padding_verified": upgraded_span[
            HEADER.size + rebuild_info.recompressed_bytes:
        ] == bytes(rebuild_info.zero_padding_bytes),
    }
    upgraded_manifest["claims"] = current_import_claims()
    validated, evidence = validate_dynamic_import(
        target=target,
        compatibility_path=compatibility_path,
        source_span=source_span,
        replacement_span=upgraded_span,
        import_manifest_payload=ownership.canonical_manifest_payload(
            upgraded_manifest
        ),
        clean_png_name=clean_png_name,
        clean_png_payload=clean_png_payload,
        mud_png_name=mud_png_name,
        mud_png_payload=mud_png_payload,
        preview_payloads=preview_payloads,
        replacement_span_name=replacement_span_name,
        import_manifest_name=import_manifest_name,
        preview_directory_name=preview_directory_name,
    )
    common.require(
        validated.loader_in_place_end_guard is True and
        validated.loader_in_place_alias_guard is True,
        "in-memory v3 upgrade failed loader in-place guards",
    )

    legacy_validated = {
        key: evidence["validated"][key] for key in LEGACY_VALIDATED_FIELDS
    }
    legacy_validated["span_sha256"] = legacy_span_sha256
    legacy_validated["import_manifest_sha256"] = sha256_bytes(
        import_manifest_payload
    )
    legacy_evidence = {
        "validated": legacy_validated,
        "quantization": evidence["quantization"],
        "mud_mode": evidence["mud_mode"],
        "compression": evidence["compression"],
        "source_independent_decode": evidence["source_independent_decode"],
        "replacement_independent_decode": evidence[
            "replacement_independent_decode"
        ],
    }
    historical_header_scratch = int(target.complete_header[5])
    return replace(
        validated,
        span_sha256=legacy_span_sha256,
        import_manifest_sha256=sha256_bytes(import_manifest_payload),
        rebuilt_overlap_scratch_bytes=historical_header_scratch,
        loader_in_place_end_guard=(
            historical_header_scratch >= rebuild_info.zero_padding_bytes
        ),
        loader_in_place_alias_guard=(
            historical_header_scratch >=
            rebuild_info.exact_minimum_overlap_scratch_bytes
        ),
    ), legacy_evidence


def verify(
    *,
    source_path: Path,
    output_path: Path,
    manifest_path: Path,
    compatibility_path: Path,
    asset_code: str,
    side: str,
    variant: int,
    clean_png_path: Path,
    mud_png_path: Path | None,
    previews_path: Path,
    index_path: Path = ownership.DEFAULT_INDEX,
    inventory_path: Path = ownership.DEFAULT_INVENTORY,
) -> dict[str, object]:
    compatibility_resolved, _, compatibility_payload, target = select_target(
        asset_code, side, variant, compatibility_path
    )
    compatibility_pin = helper.pin_small_file(
        compatibility_resolved, "compatibility report"
    )
    manifest_pin = helper.pin_small_file(manifest_path, "workflow manifest")
    clean_pin = helper.pin_small_file(clean_png_path, "clean PNG")
    mud_pin = helper.pin_small_file(mud_png_path, "mud PNG") if mud_png_path else None
    preview_dir, preview_identity, preview_pins = helper.pin_previews(previews_path)
    index_pin = ownership.pin_large_file(
        index_path, "canonical extracted pack 0",
        ownership.INDEX_SIZE, ownership.INDEX_SHA256,
    )
    inventory_pin: ownership.PinnedLargeFile | None = None
    source_fd = -1
    output_fd = -1
    try:
        inventory_pin = ownership.pin_large_file(
            inventory_path, "canonical chunk inventory",
            ownership.INVENTORY_SIZE, ownership.INVENTORY_SHA256,
        )
        source, source_fd, source_identity = old_verify.open_pinned_image(
            source_path, "retail source XISO"
        )
        output, output_fd, output_identity = old_verify.open_pinned_image(
            output_path, "workflow output XISO"
        )
        common.require(source_identity != output_identity,
                       "source and output XISOs alias one inode")
        try:
            value = json.loads(manifest_pin.payload)
        except json.JSONDecodeError as exc:
            raise common.PatchError("workflow manifest is invalid JSON") from exc
        manifest_schema = value.get("schema") if isinstance(value, dict) else None
        legacy_v2 = manifest_schema == LEGACY_WORKFLOW_SCHEMA
        common.require(isinstance(value, dict) and
                       manifest_pin.payload == ownership.canonical_manifest_payload(value) and
                       set(value) == WORKFLOW_FIELDS and
                       manifest_schema in {workflow.SCHEMA, LEGACY_WORKFLOW_SCHEMA},
                       "generalized workflow manifest schema/encoding mismatch")
        common.require(b".nfl2k5-" not in manifest_pin.payload,
                       "workflow manifest leaked an owned temporary path")

        source_span = common.read_exact(
            source_fd, target.xiso_absolute_span_offset, target.span_size
        )
        output_span = common.read_exact(
            output_fd, target.xiso_absolute_span_offset, target.span_size
        )
        common.require(sha256_bytes(source_span) == target.span_sha256,
                       "selected retail source span hash mismatch")
        embedded = value.get("import")
        common.require(isinstance(embedded, dict) and set(embedded) == {
            "manifest_sha256", "manifest", "replacement_span_sha256",
            "replacement_span_size", "dynamic_validation",
        }, "embedded generalized import fields mismatch")
        import_value = embedded["manifest"]
        common.require(isinstance(import_value, dict) and
                       import_value.get("source_index") == str(index_pin.path) and
                       import_value.get("canonical_inventory") == str(inventory_pin.path) and
                       import_value.get("outputs") == {
                           "span_file": "replacement.tset.bin",
                           "manifest_file": "import.json",
                           "preview_directory": "import-previews",
                           "preview_file_count": 12,
                       }, "embedded generalized import provenance mismatch")
        import_payload = ownership.canonical_manifest_payload(import_value)
        validator = validate_legacy_dynamic_import if legacy_v2 else \
            validate_dynamic_import
        validated, dynamic_evidence = validator(
            target=target,
            compatibility_path=compatibility_resolved,
            source_span=source_span,
            replacement_span=output_span,
            import_manifest_payload=import_payload,
            clean_png_name=clean_pin.path.name,
            clean_png_payload=clean_pin.payload,
            mud_png_name=mud_pin.path.name if mud_pin else None,
            mud_png_payload=mud_pin.payload if mud_pin else None,
            preview_payloads={name: pin.payload for name, pin in preview_pins.items()},
            replacement_span_name="replacement.tset.bin",
            import_manifest_name="import.json",
            preview_directory_name="import-previews",
        )
        if not legacy_v2:
            common.require(validated.loader_in_place_end_guard is True and
                           validated.loader_in_place_alias_guard is True,
                           "v3 workflow failed loader in-place guards")
        common.require(embedded == {
            "manifest_sha256": validated.import_manifest_sha256,
            "manifest": import_value,
            "replacement_span_sha256": validated.span_sha256,
            "replacement_span_size": target.span_size,
            "dynamic_validation": dynamic_evidence,
        }, "embedded generalized import differs from independent reconstruction")

        relative = [
            index for index, (before, after) in enumerate(zip(source_span, output_span))
            if before != after
        ]
        common.require(relative, "selected output span equals retail")
        absolute = [target.xiso_absolute_span_offset + index for index in relative]
        runs = helper.difference_runs(relative)
        source_sha, output_sha, actual = common.compare_and_hash(
            source_fd, output_fd, common.EXPECTED_XISO_SIZE, set(absolute)
        )
        common.require(source_sha == common.EXPECTED_XISO_SHA256 and actual == absolute,
                       "full-image source hash/difference ledger mismatch")
        source_entries, source_directory = common.parse_xdvdfs(
            source_fd, common.EXPECTED_XISO_SIZE
        )
        output_entries, output_directory = common.parse_xdvdfs(
            output_fd, common.EXPECTED_XISO_SIZE
        )
        common.require(source_entries == output_entries and
                       source_directory == output_directory,
                       "output XDVDFS tree/layout differs")
        files = [entry for entry in source_entries.values()
                 if not (entry.attributes & 0x10)]
        target_pack = source_entries[target.xiso_pack_path.casefold()]
        pack0 = source_entries[xwriter.PACK0_PATH.casefold()]
        xbe = source_entries["default.xbe"]
        common.require(target_pack.sector == target.xiso_pack_sector and
                       target_pack.byte_offset == target.xiso_pack_byte_offset and
                       target_pack.size == target.xiso_pack_size and
                       target_pack.byte_offset + target.pack_offset ==
                       target.xiso_absolute_span_offset and len(files) == 19,
                       "target pack/XISO extent arithmetic mismatch")
        source_target_pack_sha = common.sha256_fd(
            source_fd, target_pack.byte_offset, target_pack.size
        )
        output_target_pack_sha = common.sha256_fd(
            output_fd, target_pack.byte_offset, target_pack.size
        )
        common.require(source_target_pack_sha == target.xiso_pack_sha256 and
                       common.sha256_fd(source_fd, pack0.byte_offset, pack0.size) ==
                       xwriter.PACK0_SHA256 and
                       common.sha256_fd(output_fd, pack0.byte_offset, pack0.size) ==
                       xwriter.PACK0_SHA256 and
                       common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                       common.EXPECTED_XBE_SHA256 and
                       common.sha256_fd(output_fd, xbe.byte_offset, xbe.size) ==
                       common.EXPECTED_XBE_SHA256,
                       "target/unrelated pack or default.xbe hash mismatch")

        expected_target = {
            "asset_code": target.asset_code,
            "side": target.side,
            "variant": target.variant,
            "selector": target.selector,
            "logical_name": target.logical_name,
            "outer_index": target.outer_index,
            "outer_id": f"0x{target.outer_id:08x}",
            "chunk_index": target.chunk_index,
            "chunk_offset": target.chunk_offset,
            "stored_size": target.stored_size,
            "span_size": target.span_size,
            "layout_signature_sha256": target.layout_signature_sha256,
            "pack_path": target.xiso_pack_path,
            "pack_sector": target.xiso_pack_sector,
            "span_pack_offset": target.pack_offset,
            "absolute_span_offset": target.xiso_absolute_span_offset,
        }
        if not legacy_v2:
            expected_target.update({
                "template_overlap_scratch_bytes":
                    validated.template_overlap_scratch_bytes,
                "rebuilt_overlap_scratch_bytes":
                    validated.rebuilt_overlap_scratch_bytes,
            })
        common.require(value.get("target") == expected_target,
                       "workflow selected target record mismatch")
        common.require(value.get("source") == {
            "path": str(source),
            "size": common.EXPECTED_XISO_SIZE,
            "sha256_before": common.EXPECTED_XISO_SHA256,
            "sha256_after": common.EXPECTED_XISO_SHA256,
            "device": source_identity[0],
            "inode": source_identity[1],
            "opened_read_only": True,
            "modified": False,
        }, "workflow source record mismatch")
        common.require(value.get("compatibility_report") == {
            "path": str(compatibility_resolved),
            "sha256": sha256_bytes(compatibility_payload),
            "layout_signature_sha256": target.layout_signature_sha256,
            "compatible_package_count": 634,
        }, "workflow compatibility provenance mismatch")
        mud_mode = "identity" if mud_pin is not None else \
            str(import_value["input"]["mud"].get("mode"))
        common.require(value.get("inputs") == {
            "clean_png": {
                "path": str(clean_pin.path), "file_name": clean_pin.path.name,
                "size": clean_pin.size, "sha256": clean_pin.sha256,
                "device": clean_pin.device, "inode": clean_pin.inode,
            },
            "mud_png": None if mud_pin is None else {
                "path": str(mud_pin.path), "file_name": mud_pin.path.name,
                "size": mud_pin.size, "sha256": mud_pin.sha256,
                "device": mud_pin.device, "inode": mud_pin.inode,
            },
            "mud_mode": mud_mode,
            "canonical_index": {
                "path": str(index_pin.path), "size": index_pin.size,
                "sha256": index_pin.sha256,
            },
            "canonical_inventory": {
                "path": str(inventory_pin.path), "size": inventory_pin.size,
                "sha256": inventory_pin.sha256,
            },
        }, "workflow input provenance mismatch")

        expected_preview_hashes = {
            name: pin.sha256 for name, pin in sorted(preview_pins.items())
        }
        output_record = value.get("output")
        common.require(isinstance(output_record, dict) and
                       output_record.get("xiso_path") == str(output) and
                       output_record.get("xiso_size") == common.EXPECTED_XISO_SIZE and
                       output_record.get("xiso_sha256") == output_sha and
                       output_record.get("xiso_device") == output_identity[0] and
                       output_record.get("xiso_inode") == output_identity[1] and
                       output_record.get("copy_method") in
                           {"copy_file_range", "pread_pwrite"} and
                       output_record.get("manifest_path") == str(manifest_pin.path) and
                       output_record.get("preview_directory") == str(preview_dir) and
                       output_record.get("preview_file_count") == 12 and
                       output_record.get("preview_sha256") == expected_preview_hashes and
                       output_record.get("exclusively_created") is True and
                       set(output_record) == {
                           "xiso_path", "xiso_size", "xiso_sha256", "xiso_device",
                           "xiso_inode", "copy_method", "manifest_path",
                           "preview_directory", "preview_file_count",
                           "preview_sha256", "exclusively_created",
                       },
                       "workflow output record mismatch")
        common.require(value.get("xdvdfs") == {
            **source_directory,
            "file_count": len(files),
            "tree_identical_after_patch": True,
            "all_sector_extents_preserved": True,
            "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
        }, "workflow XDVDFS record mismatch")
        expected_patch = {
            "source_span_sha256": target.span_sha256,
            "replacement_span_sha256": validated.span_sha256,
            "relative_changed_byte_count": len(relative),
            "relative_changed_offsets_u32le_sha256": helper.offset_digest(relative, "<I"),
            "relative_changed_run_count": len(runs),
            "relative_changed_runs_u32le_sha256": sha256_bytes(b"".join(
                struct.pack("<II", start, end) for start, end in runs
            )),
            "actual_changed_byte_count": len(actual),
            "actual_changed_offsets_u64le_sha256": helper.offset_digest(actual, "<Q"),
            "all_other_image_bytes_identical": True,
            "source_target_pack_sha256": target.xiso_pack_sha256,
            "output_target_pack_sha256": output_target_pack_sha,
            "unrelated_pack0_sha256": xwriter.PACK0_SHA256,
        }
        common.require(value.get("patch") == expected_patch,
                       "workflow patch/difference record mismatch")
        safety = value.get("safety")
        common.require(isinstance(safety, dict) and
                       set(safety) == {
                           "writer_schema", "writer_manifest_sha256",
                           "selector_and_mapping_pinned",
                           "inputs_pinned_by_inode_and_hash",
                           "intermediates_independently_reconstructed",
                           "temporary_outputs_removed_before_final_manifest",
                           "only_owned_temporary_inodes_removed",
                           "all_non_target_xiso_bytes_identical",
                       } and
                       safety.get("writer_schema") == (
                           LEGACY_WRITER_SCHEMA if legacy_v2 else xwriter.SCHEMA
                       ) and
                       isinstance(safety.get("writer_manifest_sha256"), str) and
                       len(safety["writer_manifest_sha256"]) == 64 and
                       all(safety.get(key) is True for key in (
                           "selector_and_mapping_pinned",
                           "inputs_pinned_by_inode_and_hash",
                           "intermediates_independently_reconstructed",
                           "temporary_outputs_removed_before_final_manifest",
                           "only_owned_temporary_inodes_removed",
                           "all_non_target_xiso_bytes_identical",
                       )), "workflow safety record mismatch")
        expected_claims = {
            "compatible_jersey_chunk1_target_only": True,
            "user_png_consumed": True,
            "layout_identical_copy_only_xiso": True,
            "originals_modified": False,
            "retail_pixel_assets_exported_or_bundled": False,
            "models_or_other_texture_chunks_supported": False,
            "runtime_visibility_proved": False,
            "xemu_started": False,
            "title_executed": False,
            "portme": "PORTME: runtime visibility remains a separate proof.",
        }
        if legacy_v2:
            expected_claims[
                "target_wrapper_descriptors_allocation_preserved"
            ] = True
        else:
            expected_claims.update({
                "target_wrapper_descriptors_preserved_overlap_scratch_rebuilt": True,
                "loader_in_place_decode_guarded": True,
            })
        common.require(value.get("claims") == expected_claims,
                       "workflow claims mismatch")

        ownership.verify_large_pin(index_pin, "canonical extracted pack 0")
        ownership.verify_large_pin(inventory_pin, "canonical chunk inventory")
        for pin, label in ((compatibility_pin, "compatibility report"),
                           (manifest_pin, "workflow manifest"),
                           (clean_pin, "clean PNG")):
            helper.verify_pin(pin, label)
        if mud_pin is not None:
            helper.verify_pin(mud_pin, "mud PNG")
        helper.verify_previews(preview_dir, preview_identity, preview_pins)
        common.require(common.path_identity(source) == source_identity and
                       common.path_identity(output) == output_identity,
                       "source/output pathname changed during verification")
        return {
            "schema": manifest_schema,
            "target": target.selector,
            "outer_index": target.outer_index,
            "pack": target.pack_name,
            "source_sha256": source_sha,
            "output_sha256": output_sha,
            "replacement_span_sha256": validated.span_sha256,
            "changed_bytes": len(actual),
            "changed_runs": len(runs),
            "encoded_bytes": validated.encoded_bytes,
            "stored_size": target.stored_size,
            "zero_padding_bytes": validated.zero_padding_bytes,
            "mips": validated.mip_count,
            "previews": validated.preview_count,
            "files": len(files),
            "runtime_visibility_proved": False,
        }
    finally:
        if source_fd >= 0:
            os.close(source_fd)
        if output_fd >= 0:
            os.close(output_fd)
        os.close(index_pin.descriptor)
        if inventory_pin is not None:
            os.close(inventory_pin.descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--target-code", required=True)
    parser.add_argument("--target-side", required=True)
    parser.add_argument("--target-variant", required=True, type=int)
    parser.add_argument("--clean-png", required=True, type=Path)
    parser.add_argument("--mud-png", type=Path)
    parser.add_argument("--previews", required=True, type=Path)
    parser.add_argument("--index", type=Path, default=ownership.DEFAULT_INDEX)
    parser.add_argument("--inventory", type=Path, default=ownership.DEFAULT_INVENTORY)
    args = parser.parse_args()
    try:
        result = verify(
            source_path=args.source_xiso,
            output_path=args.output_xiso,
            manifest_path=args.manifest,
            compatibility_path=args.compatibility,
            asset_code=args.target_code,
            side=args.target_side,
            variant=args.target_variant,
            clean_png_path=args.clean_png,
            mud_png_path=args.mud_png,
            previews_path=args.previews,
            index_path=args.index,
            inventory_path=args.inventory,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
