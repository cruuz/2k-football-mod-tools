#!/usr/bin/env python3
"""Copy-only PNG-to-XISO workflow for any proved compatible jersey selector."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import tempfile

import nfl2k5_jersey_png_workflow as ownership
import nfl_jersey_tset_png_import as importer
import nfl_jersey_tset_xiso_patch as xwriter
from nfl_jersey_tset_targets import DEFAULT_REPORT, JerseyTarget, select_target
import nfl_tset_png_import_xiso_generic_patch as pinning
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_uniform_jersey_png_workflow/v3"


def verify_output_span(output: Path, identity: tuple[int, int], target: JerseyTarget,
                       replacement_span: bytes) -> os.stat_result:
    descriptor = os.open(
        output,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        info = os.fstat(descriptor)
        common.require(common.fd_identity(descriptor) == identity and
                       common.path_identity(output) == identity and
                       stat.S_ISREG(info.st_mode) and
                       info.st_size == common.EXPECTED_XISO_SIZE,
                       "output XISO pathname/size/type changed")
        common.require(common.read_exact(
            descriptor, target.xiso_absolute_span_offset, target.span_size
        ) == replacement_span, "output selected jersey span changed")
        return info
    finally:
        os.close(descriptor)


def run(
    *,
    source_xiso: Path,
    compatibility_path: Path,
    target: JerseyTarget,
    clean_png: Path,
    mud_png: Path | None,
    mud_mode: str,
    output_xiso: Path,
    manifest_path: Path,
    preview_dir: Path,
    index_path: Path = ownership.DEFAULT_INDEX,
    inventory_path: Path = ownership.DEFAULT_INVENTORY,
) -> dict[str, object]:
    common.require(mud_mode in {"identity", "darken_60"}, "invalid mud mode")
    common.require(mud_png is None or mud_mode == "identity",
                   "--mud-png cannot be combined with --mud-mode darken_60")
    compatibility_resolved, _, compatibility_payload, selected = select_target(
        target.asset_code, target.side, target.variant, compatibility_path
    )
    common.require(selected == target, "selected compatible target changed")
    compatibility_pin = pinning.pin_small_file(
        compatibility_resolved, "compatibility report"
    )
    output = pinning.canonical_new_path(output_xiso)
    final_manifest = pinning.canonical_new_path(manifest_path)
    final_previews = pinning.canonical_new_path(preview_dir)
    common.require(not output.exists() and not final_manifest.exists() and
                   not final_previews.exists(),
                   "output XISO, manifest, or preview directory already exists")

    clean_pin = pinning.pin_small_file(clean_png, "clean PNG")
    mud_pin = pinning.pin_small_file(mud_png, "mud PNG") if mud_png else None
    source_supplied = source_xiso.lstat()
    common.require(not stat.S_ISLNK(source_supplied.st_mode),
                   "retail source XISO must not be a symlink")
    source = source_xiso.resolve(strict=True)
    common.require(source.is_file(), "retail source XISO is not a regular file")
    index_pin = ownership.pin_large_file(
        index_path, "canonical extracted pack 0",
        ownership.INDEX_SIZE, ownership.INDEX_SHA256,
    )
    inventory_pin: ownership.PinnedLargeFile | None = None
    temp_files: list[ownership.OwnedPath] = []
    temp_directories: list[ownership.OwnedPath] = []
    final_files: list[ownership.OwnedPath] = []
    final_directories: list[ownership.OwnedPath] = []
    success = False
    try:
        inventory_pin = ownership.pin_large_file(
            inventory_path, "canonical chunk inventory",
            ownership.INVENTORY_SIZE, ownership.INVENTORY_SHA256,
        )
        paths = {
            source, compatibility_pin.path, clean_pin.path, index_pin.path,
            inventory_pin.path, output, final_manifest, final_previews,
        }
        if mud_pin is not None:
            paths.add(mud_pin.path)
        common.require(len(paths) == (9 if mud_pin is not None else 8),
                       "an input/output path aliases another workflow path")

        temporary = Path(tempfile.mkdtemp(
            prefix=f".nfl2k5-{target.selector.lower()}-jersey-", dir=output.parent
        )).resolve(strict=True)
        temp_root = ownership.track_existing(temporary, True)
        temp_directories.append(temp_root)
        clean_dir = temporary / "clean-input"
        os.mkdir(clean_dir, 0o700)
        clean_dir_owned = ownership.track_existing(clean_dir, True)
        temp_directories.append(clean_dir_owned)
        clean_copy = clean_dir / clean_pin.path.name
        temp_files.append(ownership.exclusive_copy(
            clean_copy, clean_pin.payload, clean_dir_owned
        ))
        mud_copy: Path | None = None
        if mud_pin is not None:
            mud_dir = temporary / "mud-input"
            os.mkdir(mud_dir, 0o700)
            mud_dir_owned = ownership.track_existing(mud_dir, True)
            temp_directories.append(mud_dir_owned)
            mud_copy = mud_dir / mud_pin.path.name
            temp_files.append(ownership.exclusive_copy(
                mud_copy, mud_pin.payload, mud_dir_owned
            ))

        replacement_path = temporary / "replacement.tset.bin"
        import_manifest_path = temporary / "import.json"
        import_previews_path = temporary / "import-previews"
        importer.run(
            index_pin.path, inventory_pin.path, compatibility_resolved, target,
            clean_copy, mud_copy, mud_mode,
            replacement_path, import_manifest_path, import_previews_path,
        )
        temp_files.extend([
            ownership.track_existing(replacement_path, False),
            ownership.track_existing(import_manifest_path, False),
        ])
        import_previews_owned = ownership.track_existing(import_previews_path, True)
        temp_directories.append(import_previews_owned)
        for child in sorted(import_previews_path.iterdir(), key=lambda value: value.name):
            temp_files.append(ownership.track_existing(child, False))

        writer_manifest_path = temporary / "writer.json"
        writer_result = xwriter.run(
            source_path=source,
            compatibility_path=compatibility_resolved,
            target=target,
            replacement_path=replacement_path,
            import_manifest_path=import_manifest_path,
            clean_png_path=clean_copy,
            mud_png_path=mud_copy,
            previews_path=import_previews_path,
            output_path=output,
            writer_manifest_path=writer_manifest_path,
        )
        output_identity = (
            int(writer_result["output"]["device"]),
            int(writer_result["output"]["inode"]),
        )
        final_output_owned = ownership.OwnedPath(output, output_identity, False)
        common.require(ownership.owned_matches(final_output_owned),
                       "generalized writer output ownership mismatch")
        final_files.append(final_output_owned)
        temp_files.append(ownership.track_existing(writer_manifest_path, False))

        preview_source, preview_source_identity, preview_pins = pinning.pin_previews(
            import_previews_path
        )
        os.mkdir(final_previews, 0o755)
        final_previews_owned = ownership.track_existing(final_previews, True)
        final_directories.append(final_previews_owned)
        for name, pin in sorted(preview_pins.items()):
            final_files.append(ownership.exclusive_copy(
                final_previews / name, pin.payload, final_previews_owned
            ))
        pinning.verify_previews(preview_source, preview_source_identity, preview_pins)

        replacement_payload = replacement_path.read_bytes()
        import_payload = import_manifest_path.read_bytes()
        import_value = json.loads(import_payload)
        common.require(import_payload == ownership.canonical_manifest_payload(import_value),
                       "temporary import manifest canonical encoding changed")
        writer_payload = writer_manifest_path.read_bytes()
        common.require(json.loads(writer_payload) == writer_result,
                       "generalized writer manifest readback mismatch")
        ownership.verify_large_pin(index_pin, "canonical extracted pack 0")
        ownership.verify_large_pin(inventory_pin, "canonical chunk inventory")
        pinning.verify_pin(compatibility_pin, "compatibility report")
        pinning.verify_pin(clean_pin, "original clean PNG")
        if mud_pin is not None:
            pinning.verify_pin(mud_pin, "original mud PNG")
        source_identity = (
            int(writer_result["source"]["device"]),
            int(writer_result["source"]["inode"]),
        )
        common.require(common.path_identity(source) == source_identity,
                       "retail source XISO pathname was swapped")
        output_info = verify_output_span(
            output, output_identity, target, replacement_payload
        )
        final_preview_hashes: dict[str, str] = {}
        for item in final_files[1:]:
            common.require(ownership.owned_matches(item),
                           f"final preview changed: {item.path.name}")
            final_preview_hashes[item.path.name] = hashlib.sha256(
                item.path.read_bytes()
            ).hexdigest()
        common.require(final_preview_hashes == {
            name: pin.sha256 for name, pin in sorted(preview_pins.items())
        }, "final preview copies differ from validated target previews")

        result: dict[str, object] = {
            "schema": SCHEMA,
            "target": writer_result["target"],
            "source": writer_result["source"],
            "compatibility_report": {
                "path": str(compatibility_resolved),
                "sha256": hashlib.sha256(compatibility_payload).hexdigest(),
                "layout_signature_sha256": target.layout_signature_sha256,
                "compatible_package_count": 634,
            },
            "inputs": {
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
            },
            "import": {
                "manifest_sha256": hashlib.sha256(import_payload).hexdigest(),
                "manifest": import_value,
                "replacement_span_sha256": hashlib.sha256(
                    replacement_payload
                ).hexdigest(),
                "replacement_span_size": len(replacement_payload),
                "dynamic_validation": writer_result["dynamic_validation"],
            },
            "output": {
                "xiso_path": str(output),
                "xiso_size": output_info.st_size,
                "xiso_sha256": writer_result["output"]["sha256"],
                "xiso_device": output_identity[0],
                "xiso_inode": output_identity[1],
                "copy_method": writer_result["output"]["copy_method"],
                "manifest_path": str(final_manifest),
                "preview_directory": str(final_previews),
                "preview_file_count": len(final_preview_hashes),
                "preview_sha256": final_preview_hashes,
                "exclusively_created": True,
            },
            "xdvdfs": writer_result["xdvdfs"],
            "patch": writer_result["patch"],
            "safety": {
                "writer_schema": writer_result["schema"],
                "writer_manifest_sha256": hashlib.sha256(writer_payload).hexdigest(),
                "selector_and_mapping_pinned": True,
                "inputs_pinned_by_inode_and_hash": True,
                "intermediates_independently_reconstructed": True,
                "temporary_outputs_removed_before_final_manifest": True,
                "only_owned_temporary_inodes_removed": True,
                "all_non_target_xiso_bytes_identical": True,
            },
            "claims": {
                "compatible_jersey_chunk1_target_only": True,
                "user_png_consumed": True,
                "target_wrapper_descriptors_preserved_overlap_scratch_rebuilt": True,
                "loader_in_place_decode_guarded": True,
                "layout_identical_copy_only_xiso": True,
                "originals_modified": False,
                "retail_pixel_assets_exported_or_bundled": False,
                "models_or_other_texture_chunks_supported": False,
                "runtime_visibility_proved": False,
                "xemu_started": False,
                "title_executed": False,
                "portme": "PORTME: runtime visibility remains a separate proof.",
            },
        }

        ownership.assert_owned_tree(
            temp_root, temp_files,
            [item for item in temp_directories if item != temp_root],
        )
        leftovers = ownership.cleanup_owned(temp_files, [])
        leftovers.extend(ownership.cleanup_owned([], temp_directories))
        common.require(not leftovers and not temporary.exists(),
                       f"owned temporary cleanup incomplete: {leftovers}")
        temp_files.clear()
        temp_directories.clear()

        manifest_owned_file = common.reserve_file(final_manifest)
        final_manifest_owned = ownership.OwnedPath(
            final_manifest, manifest_owned_file.identity, False
        )
        final_files.append(final_manifest_owned)
        try:
            common.write_owned_json(manifest_owned_file, result)
        finally:
            os.close(manifest_owned_file.descriptor)
        common.require(ownership.owned_matches(final_manifest_owned) and
                       json.loads(final_manifest.read_bytes()) == result,
                       "final generalized workflow manifest readback mismatch")
        final_output_info = verify_output_span(
            output, output_identity, target, replacement_payload
        )
        # Both stats come from verify_output_span()'s os.fstat of the output
        # descriptor: fd against fd, so st_ctime_ns is comparable on every
        # platform and stays in.  NOTE: this tuple carries no st_dev/st_ino;
        # verify_output_span checks fd_identity/path_identity itself.
        common.require((final_output_info.st_size, final_output_info.st_mtime_ns,
                        final_output_info.st_ctime_ns) ==
                       (output_info.st_size, output_info.st_mtime_ns,
                        output_info.st_ctime_ns),
                       "final output XISO metadata changed")
        for item in final_files[1:-1]:
            common.require(ownership.owned_matches(item) and
                           hashlib.sha256(item.path.read_bytes()).hexdigest() ==
                           final_preview_hashes[item.path.name],
                           f"final preview changed before commit: {item.path.name}")
        pinning.verify_pin(compatibility_pin, "compatibility report")
        pinning.verify_pin(clean_pin, "original clean PNG")
        if mud_pin is not None:
            pinning.verify_pin(mud_pin, "original mud PNG")
        success = True
        return result
    finally:
        os.close(index_pin.descriptor)
        if inventory_pin is not None:
            os.close(inventory_pin.descriptor)
        ownership.cleanup_owned(temp_files, temp_directories)
        if not success:
            ownership.cleanup_owned(final_files, final_directories)


def main() -> int:
    def handle_sigterm(_signum: int, _frame: object) -> None:
        raise InterruptedError("compatible jersey workflow interrupted")

    signal.signal(signal.SIGTERM, handle_sigterm)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--target-code", required=True)
    parser.add_argument("--target-side", required=True)
    parser.add_argument("--target-variant", required=True, type=int)
    parser.add_argument("--clean-png", required=True, type=Path)
    parser.add_argument("--mud-png", type=Path)
    parser.add_argument("--mud-mode", choices=("identity", "darken_60"),
                        default="identity")
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--preview-dir", required=True, type=Path)
    parser.add_argument("--index", type=Path, default=ownership.DEFAULT_INDEX,
                        help=argparse.SUPPRESS)
    parser.add_argument("--inventory", type=Path, default=ownership.DEFAULT_INVENTORY,
                        help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        *_, target = select_target(
            args.target_code, args.target_side, args.target_variant,
            args.compatibility,
        )
        result = run(
            source_xiso=args.source_xiso,
            compatibility_path=args.compatibility,
            target=target,
            clean_png=args.clean_png,
            mud_png=args.mud_png,
            mud_mode=args.mud_mode,
            output_xiso=args.output_xiso,
            manifest_path=args.manifest,
            preview_dir=args.preview_dir,
            index_path=args.index,
            inventory_path=args.inventory,
        )
    except (OSError, ValueError, json.JSONDecodeError, InterruptedError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "schema": result["schema"],
        "target": target.selector,
        "output": result["output"]["xiso_path"],
        "sha256": result["output"]["xiso_sha256"],
        "replacement_span_sha256": result["import"]["replacement_span_sha256"],
        "preview_count": result["output"]["preview_file_count"],
        "runtime_visibility_proved": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
