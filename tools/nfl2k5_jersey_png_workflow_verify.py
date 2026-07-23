#!/usr/bin/env python3
"""Independently verify a completed bounded Detroit 09H0 PNG workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys

import nfl2k5_jersey_png_workflow as workflow
from nfl_tset_png_import_dynamic_validate import validate_dynamic_import
import nfl_tset_png_import_xiso_generic_patch as writer
import nfl_uniform_color_xiso_direct_patch as common


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def open_pinned_image(path: Path, label: str) -> tuple[Path, int, tuple[int, int]]:
    supplied = path.lstat()
    common.require(not stat.S_ISLNK(supplied.st_mode), f"{label} must not be a symlink")
    identity = (supplied.st_dev, supplied.st_ino)
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    info = os.fstat(descriptor)
    try:
        common.require(stat.S_ISREG(info.st_mode) and
                       info.st_size == common.EXPECTED_XISO_SIZE,
                       f"{label} size/type mismatch")
        common.require(common.fd_identity(descriptor) == identity and
                       common.path_identity(resolved) == identity,
                       f"{label} pathname was swapped while opening")
        return resolved, descriptor, identity
    except Exception:
        os.close(descriptor)
        raise


def verify(
    *,
    source_path: Path,
    output_path: Path,
    manifest_path: Path,
    clean_png_path: Path,
    mud_png_path: Path | None,
    previews_path: Path,
    index_path: Path = workflow.DEFAULT_INDEX,
    inventory_path: Path = workflow.DEFAULT_INVENTORY,
) -> dict[str, object]:
    manifest_pin = writer.pin_small_file(manifest_path, "workflow manifest")
    clean_pin = writer.pin_small_file(clean_png_path, "clean PNG")
    mud_pin = writer.pin_small_file(mud_png_path, "mud PNG") if mud_png_path else None
    preview_dir, preview_identity, preview_pins = writer.pin_previews(previews_path)
    index_pin = workflow.pin_large_file(
        index_path, "canonical extracted pack 0",
        workflow.INDEX_SIZE, workflow.INDEX_SHA256,
    )
    inventory_pin: workflow.PinnedLargeFile | None = None
    source_fd = -1
    output_fd = -1
    try:
        inventory_pin = workflow.pin_large_file(
            inventory_path, "canonical chunk inventory",
            workflow.INVENTORY_SIZE, workflow.INVENTORY_SHA256,
        )
        source, source_fd, source_identity = open_pinned_image(
            source_path, "retail source XISO"
        )
        output, output_fd, output_identity = open_pinned_image(
            output_path, "workflow output XISO"
        )
        common.require(source_identity != output_identity,
                       "source and output XISOs alias one inode")
        common.require(len({
            source, output, manifest_pin.path, clean_pin.path, preview_dir,
            index_pin.path, inventory_pin.path,
            *(() if mud_pin is None else (mud_pin.path,)),
        }) == (8 if mud_pin is not None else 7),
                       "a verifier input path aliases another input")

        try:
            value = json.loads(manifest_pin.payload)
        except json.JSONDecodeError as exc:
            raise common.PatchError("workflow manifest is invalid JSON") from exc
        common.require(isinstance(value, dict) and
                       manifest_pin.payload == workflow.canonical_manifest_payload(value),
                       "workflow manifest is not canonical JSON")
        common.require(set(value) == {
            "schema", "scope", "source", "inputs", "import", "output",
            "xdvdfs", "patch", "safety", "claims",
        } and value.get("schema") == workflow.SCHEMA,
                       "workflow manifest schema/top-level fields mismatch")
        common.require(b".nfl2k5-jersey-png-" not in manifest_pin.payload,
                       "workflow manifest leaked an owned temporary path")

        source_span = common.read_exact(
            source_fd, writer.TARGET_ABSOLUTE, writer.SPAN_SIZE
        )
        output_span = common.read_exact(
            output_fd, writer.TARGET_ABSOLUTE, writer.SPAN_SIZE
        )
        common.require(sha256_bytes(source_span) == writer.SOURCE_SPAN_SHA256,
                       "retail source target span hash mismatch")

        embedded_import = value.get("import")
        common.require(isinstance(embedded_import, dict) and set(embedded_import) == {
            "manifest_sha256", "manifest", "replacement_span_sha256",
            "replacement_span_size", "dynamic_validation",
        }, "workflow embedded-import fields mismatch")
        import_value = embedded_import["manifest"]
        common.require(isinstance(import_value, dict),
                       "embedded import manifest is not an object")
        common.require(import_value.get("source_index") == str(index_pin.path) and
                       import_value.get("canonical_inventory") == str(inventory_pin.path),
                       "embedded import index/inventory provenance mismatch")
        import_payload = workflow.canonical_manifest_payload(import_value)
        common.require(sha256_bytes(import_payload) ==
                       embedded_import["manifest_sha256"],
                       "embedded import manifest hash mismatch")
        import_outputs = import_value.get("outputs")
        common.require(import_outputs == {
            "span_file": "replacement.tset.bin",
            "manifest_file": "import.json",
            "preview_directory": "import-previews",
            "preview_file_count": 12,
        }, "embedded import output provenance mismatch")
        validated, dynamic_evidence = validate_dynamic_import(
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
        common.require(embedded_import == {
            "manifest_sha256": validated.import_manifest_sha256,
            "manifest": import_value,
            "replacement_span_sha256": validated.span_sha256,
            "replacement_span_size": writer.SPAN_SIZE,
            "dynamic_validation": dynamic_evidence,
        }, "workflow embedded import does not equal independent reconstruction")

        relative = [
            index for index, (before, after) in enumerate(zip(source_span, output_span))
            if before != after
        ]
        common.require(relative, "workflow output target span is unchanged")
        absolute = [writer.TARGET_ABSOLUTE + index for index in relative]
        runs = writer.difference_runs(relative)
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
        pack_a = source_entries[writer.PACK_A_PATH.casefold()]
        pack_b = source_entries[writer.PACK_B_PATH.casefold()]
        pack0 = source_entries[writer.PACK0_PATH.casefold()]
        xbe = source_entries["default.xbe"]
        common.require((pack_a.sector, pack_a.size) ==
                       (writer.PACK_A_SECTOR, writer.PACK_A_SIZE) and
                       pack_a.byte_offset + writer.TARGET_SPAN_PACK_OFFSET ==
                       writer.TARGET_ABSOLUTE and len(files) == 19,
                       "retail extent/target arithmetic mismatch")
        source_pack_a_sha = common.sha256_fd(
            source_fd, pack_a.byte_offset, pack_a.size
        )
        output_pack_a_sha = common.sha256_fd(
            output_fd, pack_a.byte_offset, pack_a.size
        )
        common.require(source_pack_a_sha == writer.PACK_A_SHA256 and
                       common.sha256_fd(source_fd, pack_b.byte_offset, pack_b.size) ==
                       writer.PACK_B_SHA256 and
                       common.sha256_fd(output_fd, pack_b.byte_offset, pack_b.size) ==
                       writer.PACK_B_SHA256 and
                       common.sha256_fd(source_fd, pack0.byte_offset, pack0.size) ==
                       writer.PACK0_SHA256 and
                       common.sha256_fd(output_fd, pack0.byte_offset, pack0.size) ==
                       writer.PACK0_SHA256 and
                       common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                       common.EXPECTED_XBE_SHA256 and
                       common.sha256_fd(output_fd, xbe.byte_offset, xbe.size) ==
                       common.EXPECTED_XBE_SHA256,
                       "pack/default.xbe hash boundary mismatch")

        expected_scope = {
            "title": "ESPN NFL 2K5 (original Xbox)",
            "team": "Detroit",
            "uniform_slot": "current HOME",
            "resource": "09H0.IFF",
            "outer_index": 3685,
            "outer_id": "0x9a4832d6",
            "chunk_index": 1,
            "texture_names": ["jersey00", "jersey00_mud"],
        }
        common.require(value["scope"] == expected_scope,
                       "workflow scope claim mismatch")
        common.require(value["source"] == {
            "path": str(source),
            "size": common.EXPECTED_XISO_SIZE,
            "sha256_before": common.EXPECTED_XISO_SHA256,
            "sha256_after": common.EXPECTED_XISO_SHA256,
            "device": source_identity[0],
            "inode": source_identity[1],
            "opened_read_only": True,
            "modified": False,
        }, "workflow source record mismatch")

        expected_inputs = {
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
            "mud_mode": "identity" if mud_pin is not None else
                str(import_value["input"]["mud"].get("mode")),
            "canonical_index": {
                "path": str(index_pin.path), "size": index_pin.size,
                "sha256": index_pin.sha256,
            },
            "canonical_inventory": {
                "path": str(inventory_pin.path), "size": inventory_pin.size,
                "sha256": inventory_pin.sha256,
            },
        }
        common.require(value["inputs"] == expected_inputs,
                       "workflow input provenance mismatch")

        expected_xdvdfs = {
            **source_directory,
            "file_count": len(files),
            "tree_identical_after_patch": True,
            "all_sector_extents_preserved": True,
            "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
        }
        common.require(value["xdvdfs"] == expected_xdvdfs,
                       "workflow XDVDFS record mismatch")
        expected_patch = {
            "target_resource": "09H0.IFF",
            "target_outer_index": 3685,
            "target_outer_id": "0x9a4832d6",
            "target_chunk_index": 1,
            "target_chunk_offset": writer.TARGET_CHUNK_OFFSET,
            "absolute_span_offset": writer.TARGET_ABSOLUTE,
            "span_size": writer.SPAN_SIZE,
            "source_span_sha256": writer.SOURCE_SPAN_SHA256,
            "replacement_span_sha256": validated.span_sha256,
            "relative_changed_byte_count": len(relative),
            "relative_changed_offsets_u32le_sha256": writer.offset_digest(relative, "<I"),
            "relative_changed_run_count": len(runs),
            "relative_changed_runs_u32le_sha256": sha256_bytes(b"".join(
                struct.pack("<II", start, end) for start, end in runs
            )),
            "actual_changed_byte_count": len(actual),
            "actual_changed_offsets_u64le_sha256": writer.offset_digest(actual, "<Q"),
            "all_other_image_bytes_identical": True,
            "source_pack_a_sha256": writer.PACK_A_SHA256,
            "output_pack_a_sha256": output_pack_a_sha,
            "unrelated_pack_b_sha256": writer.PACK_B_SHA256,
            "unrelated_pack0_sha256": writer.PACK0_SHA256,
        }
        common.require(value["patch"] == expected_patch,
                       "workflow patch/difference record mismatch")

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
                       }, "workflow output record mismatch")

        safety = value.get("safety")
        common.require(isinstance(safety, dict) and set(safety) == {
            "generic_writer_schema", "generic_writer_manifest_sha256",
            "inputs_pinned_by_inode_and_hash", "intermediates_independently_reconstructed",
            "temporary_outputs_removed_before_final_manifest",
            "only_owned_temporary_inodes_removed", "all_non_target_xiso_bytes_identical",
        } and safety.get("generic_writer_schema") == writer.SCHEMA and
                       isinstance(safety.get("generic_writer_manifest_sha256"), str) and
                       len(safety["generic_writer_manifest_sha256"]) == 64 and
                       all(safety.get(key) is True for key in (
                           "inputs_pinned_by_inode_and_hash",
                           "intermediates_independently_reconstructed",
                           "temporary_outputs_removed_before_final_manifest",
                           "only_owned_temporary_inodes_removed",
                           "all_non_target_xiso_bytes_identical",
                       )), "workflow safety record mismatch")
        common.require(value.get("claims") == {
            "bounded_target_only": "Detroit current HOME 09H0.IFF chunk 1",
            "user_png_consumed": True,
            "loader_in_place_decode_guarded": True,
            "layout_identical_copy_only_xiso": True,
            "originals_modified": False,
            "retail_pixel_assets_exported_or_bundled": False,
            "runtime_visibility_proved": False,
            "xemu_started": False,
            "title_executed": False,
            "other_teams_supported": False,
            "portme": (
                "PORTME: prove and add a separate target-layout profile before "
                "claiming any other team, slot, or texture layout."
            ),
        }, "workflow claims mismatch")

        workflow.verify_large_pin(index_pin, "canonical extracted pack 0")
        workflow.verify_large_pin(inventory_pin, "canonical chunk inventory")
        writer.verify_pin(manifest_pin, "workflow manifest")
        writer.verify_pin(clean_pin, "clean PNG")
        if mud_pin is not None:
            writer.verify_pin(mud_pin, "mud PNG")
        writer.verify_previews(preview_dir, preview_identity, preview_pins)
        common.require(common.path_identity(source) == source_identity and
                       common.path_identity(output) == output_identity,
                       "source/output pathname changed during verification")
        return {
            "schema": workflow.SCHEMA,
            "source_sha256": source_sha,
            "output_sha256": output_sha,
            "replacement_span_sha256": validated.span_sha256,
            "changed_bytes": len(actual),
            "changed_runs": len(runs),
            "encoded_bytes": validated.encoded_bytes,
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
    parser.add_argument("--clean-png", required=True, type=Path)
    parser.add_argument("--mud-png", type=Path)
    parser.add_argument("--previews", required=True, type=Path)
    parser.add_argument("--index", type=Path, default=workflow.DEFAULT_INDEX)
    parser.add_argument("--inventory", type=Path, default=workflow.DEFAULT_INVENTORY)
    args = parser.parse_args()
    try:
        result = verify(
            source_path=args.source_xiso,
            output_path=args.output_xiso,
            manifest_path=args.manifest,
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
