#!/usr/bin/env python3
"""Create one safe Detroit HOME 09H0 jersey XISO copy from an RGBA PNG.

This is deliberately not a general team/uniform importer.  It accepts the
proved 512x256 two-palette P8 layout only, creates all intermediates in an
owned temporary directory, independently validates them, and exclusively
creates a layout-identical retail XISO copy plus previews and a final manifest.
It never starts an emulator and never edits any input.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import tempfile

import nfl_tset_png_import as importer
import nfl_tset_png_import_xiso_generic_patch as writer
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_jersey_png_workflow/v2"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
DEFAULT_INVENTORY = ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json"
INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
INVENTORY_SIZE = 55_746_414
INVENTORY_SHA256 = "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac"


@dataclass(frozen=True)
class PinnedLargeFile:
    path: Path
    descriptor: int
    identity: tuple[int, int]
    size: int
    sha256: str


@dataclass(frozen=True)
class OwnedPath:
    path: Path
    identity: tuple[int, int]
    is_directory: bool


def pin_large_file(
    path: Path,
    label: str,
    expected_size: int,
    expected_sha256: str,
) -> PinnedLargeFile:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise common.PatchError(f"{label} does not exist: {path}") from exc
    common.require(not stat.S_ISLNK(supplied.st_mode), f"{label} must not be a symlink")
    supplied_identity = (supplied.st_dev, supplied.st_ino)
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    try:
        info = os.fstat(descriptor)
        identity = common.fd_identity(descriptor)
        common.require(stat.S_ISREG(info.st_mode), f"{label} is not a regular file")
        common.require(identity == supplied_identity and
                       common.path_identity(resolved) == identity,
                       f"{label} pathname was swapped while opening")
        common.require(info.st_size == expected_size, f"{label} size mismatch")
        digest = common.sha256_fd(descriptor)
        common.require(digest == expected_sha256, f"{label} SHA-256 mismatch")
        return PinnedLargeFile(resolved, descriptor, identity, info.st_size, digest)
    except Exception:
        os.close(descriptor)
        raise


def verify_large_pin(pin: PinnedLargeFile, label: str) -> None:
    common.require(common.fd_identity(pin.descriptor) == pin.identity and
                   common.path_identity(pin.path) == pin.identity,
                   f"{label} pathname/inode was swapped")
    common.require(os.fstat(pin.descriptor).st_size == pin.size and
                   common.sha256_fd(pin.descriptor) == pin.sha256,
                   f"{label} changed during workflow")


def path_identity_required(path: Path, is_directory: bool) -> tuple[int, int]:
    info = path.stat(follow_symlinks=False)
    if is_directory:
        common.require(stat.S_ISDIR(info.st_mode), f"owned path is not a directory: {path}")
    else:
        common.require(stat.S_ISREG(info.st_mode), f"owned path is not a file: {path}")
    return info.st_dev, info.st_ino


def track_existing(path: Path, is_directory: bool) -> OwnedPath:
    return OwnedPath(path, path_identity_required(path, is_directory), is_directory)


def owned_matches(item: OwnedPath) -> bool:
    try:
        info = item.path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    expected_type = stat.S_ISDIR(info.st_mode) if item.is_directory else stat.S_ISREG(info.st_mode)
    return expected_type and (info.st_dev, info.st_ino) == item.identity


def assert_owned_tree(root: OwnedPath, files: list[OwnedPath],
                      directories: list[OwnedPath]) -> None:
    common.require(root.is_directory and owned_matches(root),
                   "owned temporary root pathname changed")
    all_directories = [root, *directories]
    expected_children: dict[Path, set[str]] = {
        item.path: set() for item in all_directories
    }
    for item in [*directories, *files]:
        common.require(item.path.parent in expected_children,
                       f"untracked temporary parent: {item.path}")
        expected_children[item.path.parent].add(item.path.name)
        common.require(owned_matches(item), f"owned temporary path changed: {item.path}")
    for directory in all_directories:
        common.require(owned_matches(directory),
                       f"owned temporary directory changed: {directory.path}")
        actual = {child.name for child in directory.path.iterdir()}
        common.require(actual == expected_children[directory.path],
                       f"temporary directory contains an unknown/missing entry: {directory.path}")


def cleanup_owned(files: list[OwnedPath], directories: list[OwnedPath]) -> list[str]:
    """Remove only exact owned inodes; return paths that could not be removed."""

    leftovers: list[str] = []
    for item in reversed(files):
        try:
            if owned_matches(item):
                item.path.unlink()
            elif item.path.exists() or item.path.is_symlink():
                leftovers.append(str(item.path))
        except OSError:
            leftovers.append(str(item.path))
    for item in reversed(directories):
        try:
            if owned_matches(item):
                item.path.rmdir()
            elif item.path.exists() or item.path.is_symlink():
                leftovers.append(str(item.path))
        except OSError:
            leftovers.append(str(item.path))
    return leftovers


def exclusive_copy(path: Path, payload: bytes, expected_parent: OwnedPath) -> OwnedPath:
    common.require(owned_matches(expected_parent),
                   f"output directory changed before writing {path.name}")
    identity = importer.exclusive_write(path, payload)
    common.require(owned_matches(expected_parent),
                   f"output directory changed while writing {path.name}")
    return OwnedPath(path, identity, False)


def canonical_manifest_payload(value: dict[str, object]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def verify_output_span(output: Path, identity: tuple[int, int],
                       replacement_span: bytes) -> os.stat_result:
    descriptor = os.open(
        output,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    try:
        info = os.fstat(descriptor)
        common.require(common.fd_identity(descriptor) == identity and
                       common.path_identity(output) == identity,
                       "output XISO pathname/inode was swapped")
        common.require(stat.S_ISREG(info.st_mode) and
                       info.st_size == common.EXPECTED_XISO_SIZE,
                       "output XISO size/type changed")
        common.require(common.read_exact(
            descriptor, writer.TARGET_ABSOLUTE, writer.SPAN_SIZE
        ) == replacement_span, "output XISO target span changed")
        return info
    finally:
        os.close(descriptor)


def run(
    *,
    source_xiso: Path,
    clean_png: Path,
    mud_png: Path | None,
    mud_mode: str,
    output_xiso: Path,
    manifest_path: Path,
    preview_dir: Path,
    index_path: Path = DEFAULT_INDEX,
    inventory_path: Path = DEFAULT_INVENTORY,
) -> dict[str, object]:
    common.require(mud_mode in {"identity", "darken_60"}, "invalid mud mode")
    common.require(mud_png is None or mud_mode == "identity",
                   "--mud-png cannot be combined with --mud-mode darken_60")

    output = writer.canonical_new_path(output_xiso)
    final_manifest = writer.canonical_new_path(manifest_path)
    final_previews = writer.canonical_new_path(preview_dir)
    common.require(not output.exists() and not final_manifest.exists() and
                   not final_previews.exists(),
                   "output XISO, manifest, or preview directory already exists")

    clean_pin = writer.pin_small_file(clean_png, "clean PNG")
    mud_pin = writer.pin_small_file(mud_png, "mud PNG") if mud_png else None
    source_supplied = source_xiso.lstat()
    common.require(not stat.S_ISLNK(source_supplied.st_mode),
                   "retail source XISO must not be a symlink")
    source = source_xiso.resolve(strict=True)
    common.require(source.is_file(), "retail source XISO is not a regular file")
    index_pin = pin_large_file(index_path, "canonical extracted pack 0",
                               INDEX_SIZE, INDEX_SHA256)
    inventory_pin: PinnedLargeFile | None = None
    temp_files: list[OwnedPath] = []
    temp_directories: list[OwnedPath] = []
    final_files: list[OwnedPath] = []
    final_directories: list[OwnedPath] = []
    success = False
    try:
        inventory_pin = pin_large_file(
            inventory_path, "canonical chunk inventory",
            INVENTORY_SIZE, INVENTORY_SHA256,
        )
        paths = {
            source, clean_pin.path, index_pin.path, inventory_pin.path,
            output, final_manifest, final_previews,
        }
        if mud_pin is not None:
            paths.add(mud_pin.path)
        common.require(len(paths) == (8 if mud_pin is not None else 7),
                       "an input/output path aliases another workflow path")

        temporary = Path(tempfile.mkdtemp(
            prefix=".nfl2k5-jersey-png-", dir=output.parent
        )).resolve(strict=True)
        temp_root = track_existing(temporary, True)
        temp_directories.append(temp_root)

        clean_dir = temporary / "clean-input"
        os.mkdir(clean_dir, 0o700)
        clean_dir_owned = track_existing(clean_dir, True)
        temp_directories.append(clean_dir_owned)
        clean_copy = clean_dir / clean_pin.path.name
        temp_files.append(exclusive_copy(clean_copy, clean_pin.payload, clean_dir_owned))

        mud_copy: Path | None = None
        if mud_pin is not None:
            mud_dir = temporary / "mud-input"
            os.mkdir(mud_dir, 0o700)
            mud_dir_owned = track_existing(mud_dir, True)
            temp_directories.append(mud_dir_owned)
            mud_copy = mud_dir / mud_pin.path.name
            temp_files.append(exclusive_copy(mud_copy, mud_pin.payload, mud_dir_owned))

        replacement_path = temporary / "replacement.tset.bin"
        import_manifest_path = temporary / "import.json"
        import_previews_path = temporary / "import-previews"
        importer.run(
            index_pin.path, inventory_pin.path, clean_copy, mud_copy, mud_mode,
            replacement_path, import_manifest_path, import_previews_path,
        )
        replacement_owned = track_existing(replacement_path, False)
        import_manifest_owned = track_existing(import_manifest_path, False)
        import_previews_owned = track_existing(import_previews_path, True)
        temp_files.extend([replacement_owned, import_manifest_owned])
        temp_directories.append(import_previews_owned)
        for child in sorted(import_previews_path.iterdir(), key=lambda value: value.name):
            temp_files.append(track_existing(child, False))

        writer_manifest_path = temporary / "writer.json"
        writer_result = writer.run(
            source, replacement_path, import_manifest_path, clean_copy, mud_copy,
            import_previews_path, output, writer_manifest_path,
        )
        output_identity = (
            int(writer_result["output"]["device"]),
            int(writer_result["output"]["inode"]),
        )
        final_output_owned = OwnedPath(output, output_identity, False)
        common.require(owned_matches(final_output_owned),
                       "generic writer output ownership mismatch")
        final_files.append(final_output_owned)
        writer_manifest_owned = track_existing(writer_manifest_path, False)
        temp_files.append(writer_manifest_owned)

        preview_source, preview_source_identity, preview_pins = writer.pin_previews(
            import_previews_path
        )
        os.mkdir(final_previews, 0o755)
        final_previews_owned = track_existing(final_previews, True)
        final_directories.append(final_previews_owned)
        for name, pin in sorted(preview_pins.items()):
            final_files.append(exclusive_copy(
                final_previews / name, pin.payload, final_previews_owned
            ))
        writer.verify_previews(preview_source, preview_source_identity, preview_pins)

        replacement_payload = replacement_path.read_bytes()
        import_payload = import_manifest_path.read_bytes()
        import_value = json.loads(import_payload)
        common.require(import_payload == canonical_manifest_payload(import_value),
                       "temporary import manifest canonical encoding changed")
        writer_payload = writer_manifest_path.read_bytes()
        common.require(json.loads(writer_payload) == writer_result,
                       "generic writer manifest readback mismatch")

        verify_large_pin(index_pin, "canonical extracted pack 0")
        verify_large_pin(inventory_pin, "canonical chunk inventory")
        writer.verify_pin(clean_pin, "original clean PNG")
        if mud_pin is not None:
            writer.verify_pin(mud_pin, "original mud PNG")
        source_identity = (
            int(writer_result["source"]["device"]),
            int(writer_result["source"]["inode"]),
        )
        common.require(common.path_identity(source) == source_identity,
                       "retail source XISO pathname was swapped")
        output_info = verify_output_span(output, output_identity, replacement_payload)

        final_preview_hashes: dict[str, str] = {}
        for item in final_files[1:]:
            common.require(owned_matches(item), f"final preview changed: {item.path.name}")
            payload = item.path.read_bytes()
            final_preview_hashes[item.path.name] = hashlib.sha256(payload).hexdigest()
        common.require(final_preview_hashes == {
            name: pin.sha256 for name, pin in sorted(preview_pins.items())
        }, "final preview copies differ from independently validated previews")

        result: dict[str, object] = {
            "schema": SCHEMA,
            "scope": {
                "title": "ESPN NFL 2K5 (original Xbox)",
                "team": "Detroit",
                "uniform_slot": "current HOME",
                "resource": "09H0.IFF",
                "outer_index": 3685,
                "outer_id": "0x9a4832d6",
                "chunk_index": 1,
                "texture_names": ["jersey00", "jersey00_mud"],
            },
            "source": {
                "path": str(source),
                "size": writer_result["source"]["size"],
                "sha256_before": writer_result["source"]["sha256_before"],
                "sha256_after": writer_result["source"]["sha256_after"],
                "device": source_identity[0],
                "inode": source_identity[1],
                "opened_read_only": True,
                "modified": False,
            },
            "inputs": {
                "clean_png": {
                    "path": str(clean_pin.path),
                    "file_name": clean_pin.path.name,
                    "size": clean_pin.size,
                    "sha256": clean_pin.sha256,
                    "device": clean_pin.device,
                    "inode": clean_pin.inode,
                },
                "mud_png": None if mud_pin is None else {
                    "path": str(mud_pin.path),
                    "file_name": mud_pin.path.name,
                    "size": mud_pin.size,
                    "sha256": mud_pin.sha256,
                    "device": mud_pin.device,
                    "inode": mud_pin.inode,
                },
                "mud_mode": mud_mode,
                "canonical_index": {
                    "path": str(index_pin.path),
                    "size": index_pin.size,
                    "sha256": index_pin.sha256,
                },
                "canonical_inventory": {
                    "path": str(inventory_pin.path),
                    "size": inventory_pin.size,
                    "sha256": inventory_pin.sha256,
                },
            },
            "import": {
                "manifest_sha256": hashlib.sha256(import_payload).hexdigest(),
                "manifest": import_value,
                "replacement_span_sha256": hashlib.sha256(replacement_payload).hexdigest(),
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
                "generic_writer_schema": writer_result["schema"],
                "generic_writer_manifest_sha256": hashlib.sha256(writer_payload).hexdigest(),
                "inputs_pinned_by_inode_and_hash": True,
                "intermediates_independently_reconstructed": True,
                "temporary_outputs_removed_before_final_manifest": True,
                "only_owned_temporary_inodes_removed": True,
                "all_non_target_xiso_bytes_identical": True,
            },
            "claims": {
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
            },
        }

        # Do not recursively delete anything: first prove the complete temp tree
        # is exactly the set of owned files, then unlink/rmdir those exact inodes.
        assert_owned_tree(temp_root, temp_files,
                          [item for item in temp_directories if item != temp_root])
        leftovers = cleanup_owned(temp_files, [])
        # Files are gone; directories must be removed deepest-first.  The helper
        # already reverses its argument, so retain creation order here.
        leftovers.extend(cleanup_owned([], temp_directories))
        common.require(not leftovers and not temporary.exists(),
                       f"owned temporary cleanup incomplete: {leftovers}")
        temp_files.clear()
        temp_directories.clear()

        manifest_owned_file = common.reserve_file(final_manifest)
        final_manifest_owned = OwnedPath(
            final_manifest, manifest_owned_file.identity, False
        )
        final_files.append(final_manifest_owned)
        try:
            common.write_owned_json(manifest_owned_file, result)
        finally:
            os.close(manifest_owned_file.descriptor)
        common.require(owned_matches(final_manifest_owned) and
                       json.loads(final_manifest.read_bytes()) == result,
                       "final workflow manifest readback mismatch")
        common.require(owned_matches(final_output_owned) and
                       owned_matches(final_previews_owned),
                       "final output pathname changed before commit")
        final_output_info = verify_output_span(output, output_identity, replacement_payload)
        common.require((final_output_info.st_size, final_output_info.st_mtime_ns,
                        final_output_info.st_ctime_ns) ==
                       (output_info.st_size, output_info.st_mtime_ns,
                        output_info.st_ctime_ns),
                       "output XISO metadata changed after full-image validation")
        for item in final_files[1:-1]:
            common.require(owned_matches(item) and
                           hashlib.sha256(item.path.read_bytes()).hexdigest() ==
                           final_preview_hashes[item.path.name],
                           f"final preview changed before commit: {item.path.name}")
        writer.verify_pin(clean_pin, "original clean PNG")
        if mud_pin is not None:
            writer.verify_pin(mud_pin, "original mud PNG")
        success = True
        return result
    finally:
        os.close(index_pin.descriptor)
        if inventory_pin is not None:
            os.close(inventory_pin.descriptor)
        cleanup_owned(temp_files, temp_directories)
        if not success:
            cleanup_owned(final_files, final_directories)


def main() -> int:
    def handle_sigterm(_signum: int, _frame: object) -> None:
        raise InterruptedError("jersey PNG workflow interrupted by SIGTERM")

    signal.signal(signal.SIGTERM, handle_sigterm)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--clean-png", required=True, type=Path)
    parser.add_argument("--mud-png", type=Path)
    parser.add_argument("--mud-mode", choices=("identity", "darken_60"),
                        default="identity")
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--preview-dir", required=True, type=Path)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX,
                        help=argparse.SUPPRESS)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY,
                        help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        result = run(
            source_xiso=args.source_xiso,
            clean_png=args.clean_png,
            mud_png=args.mud_png,
            mud_mode=args.mud_mode,
            output_xiso=args.output_xiso,
            manifest_path=args.manifest,
            preview_dir=args.preview_dir,
            index_path=args.index,
            inventory_path=args.inventory,
        )
    except (OSError, importer.TxtrError, importer.ImportError, common.PatchError,
            ValueError, json.JSONDecodeError, InterruptedError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "schema": result["schema"],
        "output": result["output"]["xiso_path"],
        "sha256": result["output"]["xiso_sha256"],
        "replacement_span_sha256": result["import"]["replacement_span_sha256"],
        "preview_count": result["output"]["preview_file_count"],
        "runtime_visibility_proved": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
