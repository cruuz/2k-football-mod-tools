#!/usr/bin/env python3
"""Insert a validated compatible pants TSET into a layout-identical XISO copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import struct
import sys

from nfl_pants_tset_dynamic_validate import validate_dynamic_import
from nfl_pants_tset_targets import DEFAULT_REPORT, PantsTarget, select_target
import nfl_tset_png_import_xiso_generic_patch as helper
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_pants_tset_xiso_patch/v3"
PACK0_PATH = "vc_53450030/0"
PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def run(
    *,
    source_path: Path,
    compatibility_path: Path,
    target: PantsTarget,
    replacement_path: Path,
    import_manifest_path: Path,
    clean_png_path: Path,
    mud_png_path: Path | None,
    previews_path: Path,
    output_path: Path,
    writer_manifest_path: Path,
) -> dict[str, object]:
    compatibility_resolved, _, compatibility_payload, selected = select_target(
        target.asset_code, target.side, target.variant, compatibility_path
    )
    common.require(selected == target, "selected target changed")
    compatibility_pin = helper.pin_small_file(
        compatibility_resolved, "compatibility report"
    )
    try:
        supplied_source = source_path.lstat()
    except FileNotFoundError as exc:
        raise common.PatchError(f"retail source XISO absent: {source_path}") from exc
    common.require(not stat.S_ISLNK(supplied_source.st_mode),
                   "retail source XISO must not be a symlink")
    source = source_path.resolve(strict=True)
    output = helper.canonical_new_path(output_path)
    writer_manifest = helper.canonical_new_path(writer_manifest_path)
    common.require(source.is_file() and not output.exists() and
                   not writer_manifest.exists(),
                   "source invalid or output XISO/writer manifest already exists")

    replacement = helper.pin_small_file(
        replacement_path, "replacement TSET", target.span_size
    )
    import_manifest = helper.pin_small_file(import_manifest_path, "import manifest")
    clean_png = helper.pin_small_file(clean_png_path, "clean PNG")
    mud_png = helper.pin_small_file(mud_png_path, "mud PNG") if mud_png_path else None
    preview_dir, preview_identity, preview_pins = helper.pin_previews(
        previews_path, expected_count=12
    )
    paths = {
        source, output, writer_manifest, compatibility_pin.path, replacement.path,
        import_manifest.path, clean_png.path, preview_dir,
    }
    if mud_png is not None:
        paths.add(mud_png.path)
    common.require(len(paths) == (9 if mud_png is not None else 8),
                   "an input/output path aliases another workflow path")

    source_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    output_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    success = False
    try:
        source_info = os.fstat(source_fd)
        common.require(stat.S_ISREG(source_info.st_mode) and
                       source_info.st_size == common.EXPECTED_XISO_SIZE,
                       "retail source XISO size/type mismatch")
        source_identity = common.fd_identity(source_fd)
        common.require(common.path_identity(source) == source_identity,
                       "retail source pathname changed")
        source_sha_before = common.sha256_fd(source_fd)
        common.require(source_sha_before == common.EXPECTED_XISO_SHA256,
                       "retail source XISO SHA-256 mismatch")
        entries, directory = common.parse_xdvdfs(source_fd, source_info.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        common.require(len(files) == 19, "retail XDVDFS file count mismatch")
        target_pack = entries.get(target.xiso_pack_path.casefold())
        pack0 = entries.get(PACK0_PATH.casefold())
        xbe = entries.get("default.xbe")
        common.require(target_pack is not None and pack0 is not None and xbe is not None,
                       "target pack/pack0/default.xbe absent")
        assert target_pack is not None and pack0 is not None and xbe is not None
        common.require(target_pack.sector == target.xiso_pack_sector and
                       target_pack.byte_offset == target.xiso_pack_byte_offset and
                       target_pack.size == target.xiso_pack_size and
                       common.sha256_fd(source_fd, target_pack.byte_offset,
                                        target_pack.size) == target.xiso_pack_sha256,
                       "target pack XDVDFS extent/hash mismatch")
        common.require(common.sha256_fd(source_fd, pack0.byte_offset, pack0.size) ==
                       PACK0_SHA256 and
                       common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                       common.EXPECTED_XBE_SHA256,
                       "retail pack0/default.xbe hash mismatch")
        target_absolute = target_pack.byte_offset + target.pack_offset
        common.require(target_absolute == target.xiso_absolute_span_offset,
                       "target XISO absolute offset arithmetic mismatch")
        source_span = common.read_exact(source_fd, target_absolute, target.span_size)
        common.require(sha256_bytes(source_span) == target.span_sha256,
                       "retail selected target span hash mismatch")

        validated, validation_evidence = validate_dynamic_import(
            target=target,
            compatibility_path=compatibility_resolved,
            source_span=source_span,
            replacement_span=replacement.payload,
            import_manifest_payload=import_manifest.payload,
            clean_png_name=clean_png.path.name,
            clean_png_payload=clean_png.payload,
            mud_png_name=mud_png.path.name if mud_png else None,
            mud_png_payload=mud_png.payload if mud_png else None,
            preview_payloads={name: pin.payload for name, pin in preview_pins.items()},
            replacement_span_name=replacement.path.name,
            import_manifest_name=import_manifest.path.name,
            preview_directory_name=preview_dir.name,
        )
        relative = [
            index for index, (before, after) in enumerate(
                zip(source_span, replacement.payload)
            ) if before != after
        ]
        common.require(relative, "replacement target span equals retail")
        absolute = [target_absolute + index for index in relative]
        runs = helper.difference_runs(relative)

        pins = [
            (compatibility_pin, "compatibility report"),
            (replacement, "replacement TSET"),
            (import_manifest, "import manifest"),
            (clean_png, "clean PNG"),
        ]
        for pin, label in pins:
            helper.verify_pin(pin, label)
        if mud_png is not None:
            helper.verify_pin(mud_png, "mud PNG")
        helper.verify_previews(preview_dir, preview_identity, preview_pins)

        output_owned = common.reserve_file(output)
        common.require(common.fd_identity(output_owned.descriptor) != source_identity,
                       "output XISO aliases retail source")
        copy_method = common.copy_fd_exact(
            source_fd, output_owned.descriptor, source_info.st_size
        )
        helper.pwrite_all(output_owned.descriptor, target_absolute, replacement.payload)
        common.require(common.read_exact(
            output_owned.descriptor, target_absolute, target.span_size
        ) == replacement.payload, "replacement target span readback mismatch")
        os.fsync(output_owned.descriptor)
        source_sha_after, output_sha, actual = common.compare_and_hash(
            source_fd, output_owned.descriptor, source_info.st_size, set(absolute)
        )
        common.require(source_sha_after == source_sha_before and actual == absolute,
                       "source changed or full-image difference ledger mismatch")
        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_info.st_size
        )
        common.require(output_entries == entries and output_directory == directory,
                       "output XDVDFS tree/layout changed")
        output_pack_sha = common.sha256_fd(
            output_owned.descriptor, target_pack.byte_offset, target_pack.size
        )
        common.require(common.sha256_fd(
            output_owned.descriptor, pack0.byte_offset, pack0.size
        ) == PACK0_SHA256 and common.sha256_fd(
            output_owned.descriptor, xbe.byte_offset, xbe.size
        ) == common.EXPECTED_XBE_SHA256,
            "unrelated pack0/default.xbe changed")
        for pin, label in pins:
            helper.verify_pin(pin, label)
        if mud_png is not None:
            helper.verify_pin(mud_png, "mud PNG")
        helper.verify_previews(preview_dir, preview_identity, preview_pins)
        common.require(common.path_identity(source) == source_identity,
                       "retail source pathname changed during write")

        result: dict[str, object] = {
            "schema": SCHEMA,
            "source": {
                "path": str(source),
                "size": source_info.st_size,
                "sha256_before": source_sha_before,
                "sha256_after": source_sha_after,
                "device": source_identity[0],
                "inode": source_identity[1],
                "opened_read_only": True,
                "modified": False,
            },
            "compatibility_report": {
                "path": str(compatibility_resolved),
                "sha256": sha256_bytes(compatibility_payload),
                "device": compatibility_pin.device,
                "inode": compatibility_pin.inode,
            },
            "inputs": {
                "clean_png": {
                    "path": str(clean_png.path), "sha256": clean_png.sha256,
                    "device": clean_png.device, "inode": clean_png.inode,
                },
                "mud_png": None if mud_png is None else {
                    "path": str(mud_png.path), "sha256": mud_png.sha256,
                    "device": mud_png.device, "inode": mud_png.inode,
                },
                "replacement_span": {
                    "path": str(replacement.path), "sha256": replacement.sha256,
                    "size": replacement.size,
                },
                "import_manifest": {
                    "path": str(import_manifest.path), "sha256": import_manifest.sha256,
                },
                "preview_directory": str(preview_dir),
                "preview_sha256": {
                    name: pin.sha256 for name, pin in sorted(preview_pins.items())
                },
            },
            "dynamic_validation": validation_evidence,
            "target": {
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
                "template_overlap_scratch_bytes":
                    validated.template_overlap_scratch_bytes,
                "template_exact_minimum_overlap_scratch_bytes":
                    validated.template_exact_minimum_overlap_scratch_bytes,
                "rebuilt_overlap_scratch_bytes":
                    validated.rebuilt_overlap_scratch_bytes,
                "rebuilt_exact_minimum_overlap_scratch_bytes":
                    validated.rebuilt_exact_minimum_overlap_scratch_bytes,
                "layout_signature_sha256": target.layout_signature_sha256,
                "pack_path": target.xiso_pack_path,
                "pack_sector": target_pack.sector,
                "span_pack_offset": target.pack_offset,
                "absolute_span_offset": target_absolute,
            },
            "output": {
                "path": str(output),
                "size": os.fstat(output_owned.descriptor).st_size,
                "sha256": output_sha,
                "copy_method": copy_method,
                "device": output_owned.identity[0],
                "inode": output_owned.identity[1],
                "exclusively_created": True,
                "distinct_from_source_inode": True,
            },
            "xdvdfs": {
                **directory,
                "file_count": len(files),
                "tree_identical_after_patch": True,
                "all_sector_extents_preserved": True,
                "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
            },
            "patch": {
                "source_span_sha256": target.span_sha256,
                "replacement_span_sha256": validated.span_sha256,
                "relative_changed_byte_count": len(relative),
                "relative_changed_offsets_u32le_sha256":
                    helper.offset_digest(relative, "<I"),
                "relative_changed_run_count": len(runs),
                "relative_changed_runs_u32le_sha256": sha256_bytes(b"".join(
                    struct.pack("<II", start, end) for start, end in runs
                )),
                "actual_changed_byte_count": len(actual),
                "actual_changed_offsets_u64le_sha256":
                    helper.offset_digest(actual, "<Q"),
                "all_other_image_bytes_identical": True,
                "source_target_pack_sha256": target.xiso_pack_sha256,
                "output_target_pack_sha256": output_pack_sha,
                "unrelated_pack0_sha256": PACK0_SHA256,
            },
            "claims": {
                "target_derived_from_pinned_compatibility_inventory": True,
                "target_wrapper_descriptors_preserved_overlap_scratch_rebuilt": True,
                "loader_in_place_decode_guarded": True,
                "layout_identical_copy_only_xiso": True,
                "originals_modified": False,
                "models_or_other_texture_chunks_supported": False,
                "runtime_visibility_proved": False,
                "xemu_started": False,
                "title_executed": False,
                "portme": "PORTME: runtime visibility remains a separate proof.",
            },
        }
        manifest_owned = common.reserve_file(writer_manifest)
        common.write_owned_json(manifest_owned, result)
        common.require(common.owned_path_matches(output_owned) and
                       common.owned_path_matches(manifest_owned),
                       "output/writer-manifest pathname changed")
        success = True
        return result
    finally:
        os.close(source_fd)
        if output_owned is not None:
            os.close(output_owned.descriptor)
        if manifest_owned is not None:
            os.close(manifest_owned.descriptor)
        if not success:
            common.unlink_if_owned(manifest_owned)
            common.unlink_if_owned(output_owned)


def main() -> int:
    def handle_sigterm(_signum: int, _frame: object) -> None:
        raise InterruptedError("generalized pants XISO writer interrupted")

    signal.signal(signal.SIGTERM, handle_sigterm)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--target-code", required=True)
    parser.add_argument("--target-side", required=True)
    parser.add_argument("--target-variant", required=True, type=int)
    parser.add_argument("--replacement-span", required=True, type=Path)
    parser.add_argument("--import-manifest", required=True, type=Path)
    parser.add_argument("--clean-png", required=True, type=Path)
    parser.add_argument("--mud-png", type=Path)
    parser.add_argument("--previews", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--writer-manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        *_, target = select_target(
            args.target_code, args.target_side, args.target_variant, args.compatibility
        )
        result = run(
            source_path=args.source_xiso,
            compatibility_path=args.compatibility,
            target=target,
            replacement_path=args.replacement_span,
            import_manifest_path=args.import_manifest,
            clean_png_path=args.clean_png,
            mud_png_path=args.mud_png,
            previews_path=args.previews,
            output_path=args.output_xiso,
            writer_manifest_path=args.writer_manifest,
        )
    except (OSError, ValueError, json.JSONDecodeError, InterruptedError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "schema": result["schema"],
        "target": target.selector,
        "output": result["output"]["path"],
        "sha256": result["output"]["sha256"],
        "span_sha256": result["patch"]["replacement_span_sha256"],
        "changed_bytes": result["patch"]["actual_changed_byte_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
