#!/usr/bin/env python3
"""Build a copy-only NFL 2K5 XISO with live number/nameplate PNG edits."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any

from nfl_live_numbers_nameplate_png_import import build_import, canonical_json
from nfl_live_numbers_nameplate_targets import DEFAULT_REPORT
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_live_numbers_nameplate_xiso_workflow/v1"
PLAN_SCHEMA = "nfl2k5_live_numbers_nameplate_plan/v1"
MAX_PLAN_BYTES = 64 * 1024 * 1024
MAX_EDITS = 19_654
INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"


class WorkflowError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_plan(path: Path) -> tuple[Path, bytes, list[dict[str, Any]]]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "plan must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(descriptor)
        require((opened.st_dev, opened.st_ino) == (supplied.st_dev, supplied.st_ino) and
                stat.S_ISREG(opened.st_mode) and opened.st_size <= MAX_PLAN_BYTES,
                "plan identity/type/size mismatch")
        payload = common.read_exact(descriptor, 0, opened.st_size)
        require(not os.pread(descriptor, 1, opened.st_size), "plan grew while reading")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise WorkflowError("plan is invalid JSON") from exc
    require(isinstance(value, dict) and payload == canonical_json(value) and
            set(value) == {"schema", "purpose", "edits"} and
            value["schema"] == PLAN_SCHEMA and
            isinstance(value["purpose"], str) and value["purpose"] and
            isinstance(value["edits"], list) and 1 <= len(value["edits"]) <= MAX_EDITS,
            "plan schema/canonical encoding mismatch")
    fields = {"family", "asset_code", "side", "variant", "digit", "png"}
    edits: list[dict[str, Any]] = []
    for edit in value["edits"]:
        require(isinstance(edit, dict) and set(edit) == fields and
                type(edit["family"]) is str and type(edit["asset_code"]) is str and
                type(edit["side"]) is str and type(edit["variant"]) is int and
                (edit["digit"] is None or type(edit["digit"]) is int) and
                type(edit["png"]) is str and bool(edit["png"]),
                "plan edit fields/types mismatch")
        edits.append(edit)
    return resolved, payload, edits


def write_all(descriptor: int, offset: int, payload: bytes) -> None:
    position = 0
    while position < len(payload):
        amount = os.pwrite(descriptor, payload[position:], offset + position)
        require(amount > 0, "short XISO patch write")
        position += amount


def relative_runs(offsets: list[int]) -> list[list[int]]:
    result: list[list[int]] = []
    for value in offsets:
        if not result or value != result[-1][1] + 1:
            result.append([value, value])
        else:
            result[-1][1] = value
    return result


def offset_hash(offsets: list[int], width: str) -> str:
    return digest(b"".join(struct.pack(width, value) for value in offsets))


def run(source_path: Path, output_path: Path, manifest_path: Path,
        preview_dir_path: Path, plan_path: Path, index_path: Path,
        compatibility_path: Path) -> dict[str, Any]:
    supplied = source_path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "source XISO must be a non-symlink regular file")
    source = source_path.resolve(strict=True)
    output = common.canonical_new_path(output_path)
    manifest = common.canonical_new_path(manifest_path)
    preview_dir = preview_dir_path.parent.resolve(strict=True) / preview_dir_path.name
    require(not output.exists() and not manifest.exists() and not preview_dir.exists() and
            output.name not in {"", ".", ".."} and manifest.name not in {"", ".", ".."} and
            preview_dir.name not in {"", ".", ".."},
            "outputs exist or have invalid final components")
    plan, plan_payload, edits = read_plan(plan_path)
    index = index_path.resolve(strict=True)
    require(index.stat().st_size == INDEX_SIZE and file_digest(index) == INDEX_SHA256,
            "canonical extracted index identity changed")

    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0))
    output_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    preview_created = False
    success = False
    try:
        info = os.fstat(source_fd)
        source_identity = common.fd_identity(source_fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size == common.EXPECTED_XISO_SIZE and
                source_identity == (supplied.st_dev, supplied.st_ino) and
                common.path_identity(source) == source_identity,
                "source XISO identity/size mismatch")
        source_sha = common.sha256_fd(source_fd)
        require(source_sha == common.EXPECTED_XISO_SHA256,
                "retail source XISO SHA-256 mismatch")
        entries, directory = common.parse_xdvdfs(source_fd, info.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        xbe = entries.get("default.xbe")
        require(len(files) == 19 and xbe is not None and
                xbe.size == common.EXPECTED_XBE_SIZE and
                common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "retail XDVDFS/default.xbe identity mismatch")
        assert xbe is not None

        prepared: list[dict[str, Any]] = []
        selectors: set[str] = set()
        ranges: list[tuple[int, int]] = []
        allowed: set[int] = set()
        verified_packs: dict[str, str] = {}
        png_paths: list[Path] = []
        for order, edit in enumerate(edits):
            family = str(edit["family"])
            code = str(edit["asset_code"])
            side = str(edit["side"])
            variant = int(edit["variant"])
            digit_value = edit["digit"]
            digit = None if digit_value is None else int(digit_value)
            png = Path(str(edit["png"]))
            png_paths.append(png.resolve(strict=True))
            preview_name = (
                f"{order:03d}_{family}_{code}_{side}_{variant}_"
                f"{'atlas' if digit is None else digit}.png"
            )
            names = {"span_file": f"{order:03d}_replacement.txtr.bin",
                     "manifest_file": f"{order:03d}_import.json",
                     "preview_file": preview_name}
            replacement, preview, import_value = build_import(
                index, compatibility_path, family, code, side, variant, digit, png, names)
            target = import_value["target"]
            selector = str(target["selector"])
            require(selector not in selectors, "plan repeats one resource target")
            selectors.add(selector)
            pack_key = str(target["xiso_pack_path"]).casefold()
            pack = entries.get(pack_key)
            require(pack is not None and pack.sector == int(target["xiso_pack_sector"]) and
                    pack.size == int(target["xiso_pack_size"]),
                    f"source pack extent changed for {selector}")
            assert pack is not None
            if pack_key not in verified_packs:
                verified_packs[pack_key] = common.sha256_fd(
                    source_fd, pack.byte_offset, pack.size)
            require(verified_packs[pack_key] == target["xiso_pack_sha256"],
                    f"source pack hash changed for {selector}")
            absolute = pack.byte_offset + int(target["pack_offset"])
            require(absolute == int(target["xiso_absolute_span_offset"]),
                    f"absolute target arithmetic changed for {selector}")
            source_span = common.read_exact(source_fd, absolute, len(replacement))
            require(digest(source_span) == target["span_sha256"],
                    f"source target span changed for {selector}")
            after = absolute + len(replacement)
            require(all(after <= first or absolute >= last for first, last in ranges),
                    "plan target spans overlap")
            ranges.append((absolute, after))
            relative = [index for index, pair in enumerate(zip(source_span, replacement))
                        if pair[0] != pair[1]]
            require(relative, f"replacement equals retail for {selector}")
            absolute_changes = [absolute + value for value in relative]
            require(not (allowed & set(absolute_changes)), "changed-byte sets overlap")
            allowed.update(absolute_changes)
            prepared.append({"order": order, "selector": selector,
                             "target": target, "replacement": replacement,
                             "preview": preview, "preview_name": preview_name,
                             "import_manifest": import_value,
                             "absolute": absolute, "relative": relative})

        path_set = {source, output, manifest, preview_dir, plan, index,
                    compatibility_path.resolve(strict=True), *png_paths}
        require(len(path_set) == 7 + len(set(png_paths)),
                "workflow control/output paths alias an input")
        output_owned = common.reserve_file(output)
        require(output_owned.identity != source_identity, "output XISO aliases source")
        copy_method = common.copy_fd_exact(source_fd, output_owned.descriptor, info.st_size)
        for item in prepared:
            write_all(output_owned.descriptor, item["absolute"], item["replacement"])
            require(common.read_exact(output_owned.descriptor, item["absolute"],
                                      len(item["replacement"])) == item["replacement"],
                    f"replacement readback failed for {item['selector']}")
        os.fsync(output_owned.descriptor)
        source_after, output_sha, actual = common.compare_and_hash(
            source_fd, output_owned.descriptor, info.st_size, allowed)
        require(source_after == source_sha and actual == sorted(allowed) and
                common.path_identity(source) == source_identity and
                common.owned_path_matches(output_owned),
                "copy/patch ledger or pathname verification failed")
        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, info.st_size)
        require(output_entries == entries and output_directory == directory and
                common.sha256_fd(output_owned.descriptor, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "output XDVDFS/default.xbe changed")

        os.mkdir(preview_dir, 0o755)
        preview_created = True
        for item in prepared:
            destination = preview_dir / item["preview_name"]
            descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                                 getattr(os, "O_NOFOLLOW", 0) |
                                 getattr(os, "O_CLOEXEC", 0), 0o644)
            try:
                offset = 0
                while offset < len(item["preview"]):
                    amount = os.write(descriptor, item["preview"][offset:])
                    require(amount > 0, "short preview write")
                    offset += amount
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

        edit_records = []
        for item in prepared:
            relative = item["relative"]
            edit_records.append({
                "order": item["order"], "selector": item["selector"],
                "target": item["target"],
                "input_png": item["import_manifest"]["input_png"],
                "import_manifest": item["import_manifest"],
                "import_manifest_sha256": digest(canonical_json(item["import_manifest"])),
                "absolute_span_offset": item["absolute"],
                "replacement_span_size": len(item["replacement"]),
                "replacement_span_sha256": digest(item["replacement"]),
                "relative_changed_byte_count": len(relative),
                "relative_changed_offsets_u32le_sha256": offset_hash(relative, "<I"),
                "relative_changed_runs": relative_runs(relative),
                "preview_file": item["preview_name"],
                "preview_sha256": digest(item["preview"]),
            })
        result: dict[str, Any] = {
            "schema": SCHEMA,
            "source": {"path": str(source), "size": info.st_size,
                       "sha256_before": source_sha, "sha256_after": source_after,
                       "opened_read_only": True, "modified": False},
            "plan": {"path": str(plan), "sha256": digest(plan_payload),
                     "edit_count": len(edits)},
            "canonical_index": {"path": str(index), "size": INDEX_SIZE,
                                "sha256": INDEX_SHA256},
            "compatibility_report": {"path": str(compatibility_path.resolve(strict=True)),
                                     "sha256": file_digest(compatibility_path)},
            "edits": edit_records,
            "output": {"xiso_path": str(output), "xiso_size": info.st_size,
                       "xiso_sha256": output_sha, "copy_method": copy_method,
                       "manifest_path": str(manifest),
                       "preview_directory": str(preview_dir),
                       "exclusively_created": True},
            "xdvdfs": {**directory, "file_count": len(files),
                       "tree_and_extents_identical": True,
                       "default_xbe_sha256": common.EXPECTED_XBE_SHA256},
            "patch": {"edit_count": len(prepared),
                      "changed_byte_count": len(actual),
                      "changed_offsets_u64le_sha256": offset_hash(actual, "<Q"),
                      "all_changed_bytes_inside_selected_spans": True,
                      "all_other_xiso_bytes_identical": True},
            "claims": {"copy_only": True, "retail_source_modified": False,
                       "all_mips_rebuilt": True, "name_metrics_modified": False,
                       "offline_transport_proved": True,
                       "xemu_started": False, "title_executed": False,
                       "runtime_visibility_proved": False,
                       "portme": (
                           "PORTME(runtime): capture each edited family in a live player scene "
                           "before claiming visibility."
                       )},
        }
        manifest_owned = common.reserve_file(manifest)
        common.write_owned_json(manifest_owned, result)
        require(common.owned_path_matches(manifest_owned), "manifest pathname changed")
        success = True
        return result
    finally:
        os.close(source_fd)
        if output_owned is not None:
            os.close(output_owned.descriptor)
        if manifest_owned is not None:
            os.close(manifest_owned.descriptor)
        if not success:
            for path in (output, manifest):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            if preview_created:
                for path in preview_dir.iterdir():
                    path.unlink()
                preview_dir.rmdir()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", type=Path, default=root / "ESPN NFL 2K5 (USA).xiso.iso")
    parser.add_argument("--output-xiso", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--preview-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--index", type=Path, default=root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    try:
        report = run(args.source_xiso, args.output_xiso, args.manifest,
                     args.preview_dir, args.plan, args.index, args.compatibility)
        print("NFL_LIVE_NUMBERS_NAMEPLATE_XISO_WORKFLOW_COMPLETE "
              f"edits={report['patch']['edit_count']} "
              f"changed={report['patch']['changed_byte_count']} "
              f"sha256={report['output']['xiso_sha256']} runtime=false")
        return 0
    except (WorkflowError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
