#!/usr/bin/env python3
"""Verify the cleaned NFL 2K5 portrait proof XISO as a virtual product.

This is deliberately separate from the physical-output verifier.  It accepts
only the exact absent output path recorded by the pinned historical manifest,
reconstructs every replacement from the retained plan/PNG/import inputs, and
hashes a logical copied XISO without creating one.  Existing files, symlinks,
different missing paths, and changed receipts fail closed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any

from nfl_player_portrait_png_import import build_import, canonical_json
import nfl_uniform_color_xiso_direct_patch as common


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PIN = (
    12_468,
    "f105ba11b2e5cd184f9e2a5022caad112fe0b4d6842a412e41b1c897d3d936b2",
)
PLAN_PIN = (
    305,
    "6c332d6db442236885571cf11d17f01d7e3180a24a9844374f805ba84f24d337",
)
INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
COMPATIBILITY_SHA256 = "c0f792df4aa03a9a0c4e670c7b214da53a97f19526c84fd52765137120713481"
HISTORICAL_COMPATIBILITY_SHA256 = (
    "f1eee623e5d9d026f5d85b6a6b6fb75287a655ccc034626477dadcf19b74e7bc"
)
SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
OUTPUT_SHA256 = "bb96a267077d670bb1fb206e3e523dec0934827739fa09e8cf36ec29ef0946a7"
MAX_JSON = 32 * 1024 * 1024


class VirtualVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class Opened:
    path: Path
    descriptor: int
    identity: tuple[int, int, int]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VirtualVerificationError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def open_regular(path: Path, label: str, expected_size: int | None = None) -> Opened:
    supplied = path.lstat()
    require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        f"{label} must be a regular non-symlink file",
    )
    if expected_size is not None:
        require(supplied.st_size == expected_size, f"{label} size differs")
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    opened = os.fstat(descriptor)
    identity = (opened.st_dev, opened.st_ino, opened.st_size)
    require(
        stat.S_ISREG(opened.st_mode)
        and identity == (supplied.st_dev, supplied.st_ino, supplied.st_size),
        f"{label} identity changed while opening",
    )
    return Opened(resolved, descriptor, identity)


def verify_unchanged(opened: Opened, label: str) -> None:
    current = opened.path.stat(follow_symlinks=False)
    require(
        (current.st_dev, current.st_ino, current.st_size) == opened.identity,
        f"{label} changed while open",
    )


def close(opened: Opened, label: str) -> None:
    try:
        verify_unchanged(opened, label)
    finally:
        os.close(opened.descriptor)


def read_canonical_pin(path: Path, pin: tuple[int, str], label: str) -> tuple[bytes, dict[str, Any]]:
    opened = open_regular(path, label, pin[0])
    try:
        raw = common.read_exact(opened.descriptor, 0, pin[0])
        require(digest(raw) == pin[1], f"{label} SHA-256 differs")
        value = json.loads(raw)
        require(
            isinstance(value, dict) and raw == canonical_json(value),
            f"{label} is not canonical JSON",
        )
        return raw, value
    finally:
        close(opened, label)


def validate_absent_output(recorded: dict[str, Any], requested: Path) -> Path:
    require(set(recorded) == {
        "copy_method", "device", "exclusively_created", "inode", "manifest_path",
        "preview_directory", "preview_sha256", "xiso_path", "xiso_sha256", "xiso_size",
    }, "historical output record fields differ")
    require(
        recorded["xiso_size"] == common.EXPECTED_XISO_SIZE
        and recorded["xiso_sha256"] == OUTPUT_SHA256
        and recorded["copy_method"] in {"copy_file_range", "pread_pwrite"}
        and recorded["exclusively_created"] is True
        and type(recorded["device"]) is int and recorded["device"] > 0
        and type(recorded["inode"]) is int and recorded["inode"] > 0,
        "historical output receipt boundary differs",
    )
    require(not os.path.lexists(requested),
            "absent-output mode refuses an existing file or symlink")
    parent_info = requested.parent.lstat()
    require(stat.S_ISDIR(parent_info.st_mode) and not stat.S_ISLNK(parent_info.st_mode),
            "absent-output parent must be a regular directory, not a symlink")
    canonical_requested = requested.parent.resolve(strict=True) / requested.name
    canonical_recorded = Path(recorded["xiso_path"])
    require(canonical_recorded.is_absolute(), "recorded XISO path must be absolute")
    require(canonical_requested == canonical_recorded,
            "absent-output path does not exactly match the pinned receipt")
    require(not os.path.lexists(canonical_requested),
            "recorded output appeared during absent-output validation")
    return canonical_requested


def offset_hash(offsets: list[int], fmt: str) -> str:
    return digest(b"".join(struct.pack(fmt, value) for value in offsets))


def relative_runs(offsets: list[int]) -> list[list[int]]:
    result: list[list[int]] = []
    for value in offsets:
        if not result or value != result[-1][1] + 1:
            result.append([value, value])
        else:
            result[-1][1] = value
    return result


def absolute_for_relative(segments: list[dict[str, Any]], relative: int) -> int:
    for segment in segments:
        start = int(segment["span_relative_offset"])
        size = int(segment["size"])
        if start <= relative < start + size:
            return int(segment["xiso_absolute_offset"]) + relative - start
    raise VirtualVerificationError("changed portrait byte is outside its segments")


def apply(block: bytearray, position: int, offset: int, replacement: bytes) -> None:
    start = max(position, offset)
    end = min(position + len(block), offset + len(replacement))
    if start < end:
        block[start - position:end - position] = replacement[
            start - offset:end - offset
        ]


def read_plan(path: Path) -> tuple[Path, bytes, list[dict[str, str]]]:
    raw, value = read_canonical_pin(path, PLAN_PIN, "portrait proof plan")
    require(
        set(value) == {"schema", "purpose", "edits"}
        and value["schema"] == "nfl2k5_player_portrait_plan/v1"
        and value["purpose"] == "deterministic non-retail numeric roster portrait copy-only proof"
        and value["edits"] == [{
            "png": str((ROOT / "assets/fixtures/nfl2k5/player_portrait/portrait_0124_nonretail.png").resolve()),
            "portrait_id": "0124",
        }],
        "portrait proof plan differs",
    )
    return path.resolve(strict=True), raw, value["edits"]


def reconstruct_historical_compatibility(
    payload: bytes, source: Path, index: Path,
) -> str:
    value = json.loads(payload)
    require(payload == canonical_json(value),
            "current compatibility report is not canonical JSON")
    inputs = value["inputs"]
    require(
        inputs["canonical_index"]["path"] == "user-source/vc_53450030/0"
        and inputs["default_xbe"]["path"] == "user-source/default.xbe"
        and inputs["retail_xiso"]["path"] == "user-source/ESPN NFL 2K5.xiso.iso"
        and inputs["roster_players"]["path"]
        == "generation-evidence/nfl2k5_roster_players.tsv"
        and inputs["txtr_inventory"]["path"]
        == "generation-evidence/nfl2k5_all_txtr_inventory_v2.json",
        "current compatibility provenance labels differ",
    )
    inputs["canonical_index"]["path"] = str(index)
    inputs["default_xbe"]["path"] = str(
        (ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe").resolve(strict=True)
    )
    inputs["retail_xiso"]["path"] = str(source)
    inputs["roster_players"]["path"] = str(
        (ROOT / "reports/assets/nfl2k5_roster_players.tsv").resolve(strict=True)
    )
    inputs["txtr_inventory"]["path"] = str(
        (ROOT / "reports/assets/nfl2k5_all_txtr_inventory_v2.json").resolve(strict=True)
    )
    historical = digest(canonical_json(value))
    require(historical == HISTORICAL_COMPATIBILITY_SHA256,
            "historical absolute-path compatibility receipt cannot be reconstructed")
    return historical


def preview_directory(path: Path, expected: dict[str, bytes]) -> dict[str, str]:
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            "preview directory must be a non-symlink directory")
    require(set(os.listdir(path)) == set(expected), "preview directory members differ")
    result: dict[str, str] = {}
    for name, payload in expected.items():
        opened = open_regular(path / name, f"preview {name}", len(payload))
        try:
            actual = common.read_exact(opened.descriptor, 0, len(payload))
            require(actual == payload, f"preview {name} differs from reconstruction")
            result[name] = digest(actual)
        finally:
            close(opened, f"preview {name}")
    return result


def verify(
    source_path: Path,
    absent_output_path: Path,
    manifest_path: Path,
    preview_dir_path: Path,
    plan_path: Path,
    index_path: Path,
    compatibility_path: Path,
) -> dict[str, Any]:
    manifest_payload, recorded = read_canonical_pin(
        manifest_path, MANIFEST_PIN, "portrait proof manifest",
    )
    require(recorded.get("schema") == "nfl2k5_player_portrait_xiso_workflow/v1"
            and set(recorded) == {
                "schema", "source", "plan", "canonical_index", "compatibility_report",
                "edits", "output", "xdvdfs", "patch", "claims",
            }, "portrait proof manifest schema/fields differ")
    absent_output = validate_absent_output(recorded["output"], absent_output_path)
    source = open_regular(source_path, "retail source XISO", common.EXPECTED_XISO_SIZE)
    index = open_regular(index_path, "canonical extracted index", INDEX_SIZE)
    compatibility = open_regular(compatibility_path, "portrait compatibility report")
    try:
        plan, plan_payload, edits = read_plan(plan_path)
        require(common.sha256_fd(index.descriptor) == INDEX_SHA256,
                "canonical extracted index SHA-256 differs")
        compatibility_payload = common.read_exact(
            compatibility.descriptor, 0, compatibility.identity[2]
        )
        compatibility_sha = digest(compatibility_payload)
        require(compatibility_sha == COMPATIBILITY_SHA256,
                "portrait compatibility report SHA-256 differs")
        historical_compatibility_sha = reconstruct_historical_compatibility(
            compatibility_payload, source.path, index.path,
        )
        entries, directory = common.parse_xdvdfs(source.descriptor, source.identity[2])
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        xbe = entries.get("default.xbe")
        require(len(files) == 19 and xbe is not None
                and xbe.size == common.EXPECTED_XBE_SIZE,
                "retail XDVDFS/default.xbe layout differs")

        selectors: set[str] = set()
        logical_ranges: list[tuple[int, int]] = []
        all_changes: set[int] = set()
        patch_spans: list[tuple[int, bytes]] = []
        expected_edits: list[dict[str, Any]] = []
        previews: dict[str, bytes] = {}
        pack_extents: dict[str, tuple[int, int, str]] = {}
        for order, edit in enumerate(edits):
            portrait_id = edit["portrait_id"]
            png = Path(edit["png"])
            preview_name = f"{order:04d}_portrait_{portrait_id}.png"
            names = {
                "span_file": f"{order:04d}_replacement.txtr.bin",
                "manifest_file": f"{order:04d}_import.json",
                "preview_file": preview_name,
            }
            replacement, preview, imported = build_import(
                index.path, compatibility.path, portrait_id, png, names,
            )
            require(
                imported["compatibility_report"]["sha256"] == compatibility_sha,
                "current imported compatibility binding differs",
            )
            imported["compatibility_report"]["sha256"] = historical_compatibility_sha
            target = imported["target"]
            selector = str(target["selector"])
            require(selector not in selectors, "portrait proof repeats a selector")
            selectors.add(selector)
            segments = list(target["span_segments"])
            normalized: list[dict[str, Any]] = []
            source_pieces: list[bytes] = []
            for segment in segments:
                pack_path = str(segment["pack_path"])
                pack = entries.get(pack_path.casefold())
                require(pack is not None and pack.sector == int(segment["pack_sector"])
                        and pack.size == int(segment["pack_size"]),
                        f"source pack extent differs for {selector}")
                assert pack is not None
                absolute = pack.byte_offset + int(segment["pack_offset"])
                require(absolute == int(segment["xiso_absolute_offset"]),
                        f"portrait segment arithmetic differs for {selector}")
                size = int(segment["size"])
                relative = int(segment["span_relative_offset"])
                source_pieces.append(common.read_exact(source.descriptor, absolute, size))
                patch_spans.append((absolute, replacement[relative:relative + size]))
                normalized.append({**segment, "xiso_absolute_offset": absolute})
                pack_extents[pack_path] = (
                    pack.byte_offset, pack.size, str(segment["pack_sha256"]),
                )
            source_span = b"".join(source_pieces)
            require(digest(source_span) == target["span_sha256"]
                    and len(source_span) == len(replacement),
                    f"retail source span differs for {selector}")
            logical_start = int(target["chunk_offset"])
            logical_end = logical_start + len(replacement)
            require(all(logical_end <= start or logical_start >= end
                        for start, end in logical_ranges),
                    "portrait logical targets overlap")
            logical_ranges.append((logical_start, logical_end))
            relative_changes = [
                index for index, pair in enumerate(zip(source_span, replacement))
                if pair[0] != pair[1]
            ]
            absolute_changes = [
                absolute_for_relative(normalized, value) for value in relative_changes
            ]
            require(relative_changes and not (all_changes & set(absolute_changes)),
                    "portrait changes are empty or overlap")
            all_changes.update(absolute_changes)
            previews[preview_name] = preview
            expected_edits.append({
                "order": order,
                "selector": selector,
                "target": target,
                "input_png": imported["input_png"],
                "import_manifest": imported,
                "import_manifest_sha256": digest(canonical_json(imported)),
                "replacement_span_sha256": digest(replacement),
                "replacement_span_size": len(replacement),
                "preview_file": preview_name,
                "preview_sha256": digest(preview),
                "absolute_span_segments": normalized,
                "relative_changed_byte_count": len(relative_changes),
                "relative_changed_offsets_u32le_sha256": offset_hash(relative_changes, "<I"),
                "relative_changed_runs": relative_runs(relative_changes),
            })

        require(recorded["edits"] == expected_edits,
                "manifest edits differ from independent reconstruction")
        preview_hashes = preview_directory(preview_dir_path, previews)
        ordered_changes = sorted(all_changes)
        require(recorded["patch"] == {
            "target_count": len(expected_edits),
            "target_pack_paths": sorted(pack_extents),
            "actual_changed_byte_count": len(ordered_changes),
            "actual_changed_offsets_u64le_sha256": offset_hash(ordered_changes, "<Q"),
            "all_other_xiso_bytes_identical": True,
        }, "portrait logical change ledger differs")

        source_hash = hashlib.sha256()
        virtual_hash = hashlib.sha256()
        pack_hashes = {name: hashlib.sha256() for name in pack_extents}
        xbe_hash = hashlib.sha256()
        position = 0
        block_size = 16 * 1024 * 1024
        while position < source.identity[2]:
            block = os.pread(
                source.descriptor, min(block_size, source.identity[2] - position), position,
            )
            require(block, "short retail XISO read")
            source_hash.update(block)
            block_end = position + len(block)
            for name, (offset, size, _expected) in pack_extents.items():
                start = max(position, offset)
                end = min(block_end, offset + size)
                if start < end:
                    pack_hashes[name].update(block[start - position:end - position])
            xbe_start = max(position, xbe.byte_offset)
            xbe_end = min(block_end, xbe.byte_offset + xbe.size)
            if xbe_start < xbe_end:
                xbe_hash.update(block[xbe_start - position:xbe_end - position])
            virtual = bytearray(block)
            for offset, replacement in patch_spans:
                apply(virtual, position, offset, replacement)
            virtual_hash.update(virtual)
            position = block_end

        require(source_hash.hexdigest() == SOURCE_SHA256,
                "retail source XISO SHA-256 differs")
        require(virtual_hash.hexdigest() == recorded["output"]["xiso_sha256"] == OUTPUT_SHA256,
                "virtual portrait XISO SHA-256 differs")
        require(xbe_hash.hexdigest() == common.EXPECTED_XBE_SHA256,
                "retail/virtual default.xbe identity differs")
        require(all(pack_hashes[name].hexdigest() == expected
                    for name, (_offset, _size, expected) in pack_extents.items()),
                "retail portrait pack SHA-256 differs")

        source_record = recorded["source"]
        require(source_record == {
            "path": str(source.path), "size": source.identity[2],
            "sha256_before": SOURCE_SHA256, "sha256_after": SOURCE_SHA256,
            "device": source.identity[0], "inode": source.identity[1],
            "opened_read_only": True, "modified": False,
        }, "portrait source receipt differs")
        require(recorded["plan"] == {
            "path": str(plan), "sha256": digest(plan_payload), "edit_count": len(edits),
        } and recorded["canonical_index"] == {
            "path": str(index.path), "size": INDEX_SIZE, "sha256": INDEX_SHA256,
        } and recorded["compatibility_report"] == {
            "path": str(compatibility.path), "sha256": historical_compatibility_sha,
        }, "portrait input receipt differs")
        require(recorded["output"]["manifest_path"] == str(manifest_path.resolve(strict=True))
                and recorded["output"]["preview_directory"]
                == str(preview_dir_path.resolve(strict=True))
                and recorded["output"]["preview_sha256"] == preview_hashes,
                "portrait retained output sidecars differ")
        require(recorded["xdvdfs"] == {
            **directory, "file_count": len(files), "tree_identical_after_patch": True,
            "all_sector_extents_preserved": True,
            "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
        }, "portrait virtual XDVDFS receipt differs")
        require(recorded["claims"] == {
            "numeric_roster_portraits_only": True,
            "action_photo_family_modified": False,
            "live_3d_face_family_modified": False,
            "layout_identical_copy_only_xiso": True,
            "originals_modified": False,
            "retail_artwork_exported_or_bundled": False,
            "runtime_visibility_proved": False,
            "xemu_started": False,
            "title_executed": False,
            "portme": "PORTME(runtime): capture the edited portrait in a roster/wrap-up UI before claiming visibility.",
        }, "portrait claim boundary differs")
        require(not os.path.lexists(absent_output),
                "portrait output appeared during virtual verification")
        verify_unchanged(source, "retail source XISO")
        verify_unchanged(index, "canonical extracted index")
        verify_unchanged(compatibility, "portrait compatibility report")
        require(digest(manifest_payload) == MANIFEST_PIN[1],
                "portrait manifest changed during verification")
        return {
            "schema": "nfl2k5_player_portrait_xiso_virtual_verify/v1",
            "edit_count": len(expected_edits),
            "changed_byte_count": len(ordered_changes),
            "source_sha256": SOURCE_SHA256,
            "virtual_output_sha256": OUTPUT_SHA256,
            "xdvdfs_identical": True,
            "default_xbe_unchanged": True,
            "all_other_xiso_bytes_identical": True,
            "output_xiso_absent": True,
            "output_xiso_written": False,
            "historical_compatibility_receipt_reconstructed": True,
            "runtime_visibility_proved": False,
        }
    finally:
        close(compatibility, "portrait compatibility report")
        close(index, "canonical extracted index")
        close(source, "retail source XISO")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--absent-output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--preview-dir", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument(
        "--index", type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"),
    )
    parser.add_argument(
        "--compatibility", type=Path,
        default=Path("reports/assets/nfl2k5_player_portrait_compatibility.json"),
    )
    args = parser.parse_args()
    try:
        result = verify(
            args.source_xiso, args.absent_output_xiso, args.manifest,
            args.preview_dir, args.plan, args.index, args.compatibility,
        )
    except (OSError, KeyError, TypeError, json.JSONDecodeError,
            VirtualVerificationError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
