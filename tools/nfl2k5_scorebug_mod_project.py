#!/usr/bin/env python3
"""Typed, fail-closed NFL 2K5 scorebug project builder and verifier.

The canonical project recipe names one to three proved texture targets.  It
contains no offsets, codec knobs, archive paths, or replacement bytes.  Those
values come only from the pinned scorebug audit and strict fixed-span importer.

``build`` creates one layout-identical copy of the pinned retail XISO and puts
all selected replacements into that copy.  ``verify`` independently reruns the
importers and reconstructs the complete allowed-byte union before consulting
the build manifest.  Originals are opened read-only and are never modified.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
from typing import Any

from nfl_scorebug_png_import import (
    AUDIT_SHA256,
    INDEX_SHA256,
    INDEX_SIZE,
    TARGET_NAMES,
    build_import,
    canonical_json,
)
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_scorebug_mod_project/v1"
BUILD_SCHEMA = "nfl2k5_scorebug_mod_build/v1"
VERIFY_SCHEMA = "nfl2k5_scorebug_mod_verify/v1"
ROOT = Path(__file__).resolve().parents[1]
CANONICAL_INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
CANONICAL_AUDIT = ROOT / "reports/assets/scorebug_presentation_audit.json"
AUDIT_SIZE = 46_512
MAX_PROJECT_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_PNG_BYTES = 32 * 1024 * 1024
TARGET_DIMENSIONS = {
    "score_buga": (64, 64),
    "shield_espn": (128, 64),
    "digital_font": (128, 128),
}
SOURCE_PIN: dict[str, object] = {
    "canonical_index_sha256": INDEX_SHA256,
    "canonical_index_size": INDEX_SIZE,
    "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
    "default_xbe_size": common.EXPECTED_XBE_SIZE,
    "scorebug_audit_sha256": AUDIT_SHA256,
    "scorebug_audit_size": AUDIT_SIZE,
    "xiso_sha256": common.EXPECTED_XISO_SHA256,
    "xiso_size": common.EXPECTED_XISO_SIZE,
}
HEX_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)


class ScorebugProjectError(ValueError):
    """Raised when any project, input, output, or proof fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ScorebugProjectError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def offset_hash(offsets: list[int], fmt: str) -> str:
    return digest(b"".join(struct.pack(fmt, value) for value in offsets))


def runs(offsets: list[int]) -> list[list[int]]:
    result: list[list[int]] = []
    for value in offsets:
        if not result or value != result[-1][1] + 1:
            result.append([value, value])
        else:
            result[-1][1] = value
    return result


@dataclass(frozen=True)
class ProjectFile:
    path: Path
    payload: bytes
    value: dict[str, Any]
    identity: tuple[int, int]


@dataclass(frozen=True)
class InputPin:
    path: Path
    payload: bytes
    size: int
    sha256: str
    identity: tuple[int, int]


@dataclass(frozen=True)
class LargePin:
    path: Path
    descriptor: int
    size: int
    sha256: str
    identity: tuple[int, int]


@dataclass(frozen=True)
class PreparedEdit:
    order: int
    recipe: dict[str, Any]
    pin: InputPin
    replacement: bytes
    preview: bytes
    import_report: dict[str, Any]
    import_payload: bytes
    target: dict[str, Any]
    absolute_offset: int
    relative_changed: list[int]

    @property
    def name(self) -> str:
        return str(self.recipe["target"])

    @property
    def end_offset(self) -> int:
        return self.absolute_offset + len(self.replacement)


@dataclass(frozen=True)
class ArtifactFile:
    path: Path
    identity: tuple[int, int]


def read_regular_bounded(path: Path, maximum: int, label: str) \
        -> tuple[Path, bytes, tuple[int, int]]:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise ScorebugProjectError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(descriptor)
        identity = (info.st_dev, info.st_ino)
        require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= maximum and
                identity == (supplied.st_dev, supplied.st_ino) and
                common.path_identity(resolved) == identity,
                f"{label} pathname/type/size changed")
        payload = common.read_exact(descriptor, 0, info.st_size)
        require(not os.pread(descriptor, 1, info.st_size),
                f"{label} grew while reading")
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (identity[0], identity[1], info.st_size),
                f"{label} changed while reading")
        return resolved, payload, identity
    finally:
        os.close(descriptor)


def verify_pin(pin: InputPin) -> None:
    descriptor = os.open(pin.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and
                (info.st_dev, info.st_ino, info.st_size) ==
                (*pin.identity, pin.size) and
                common.path_identity(pin.path) == pin.identity and
                common.sha256_fd(descriptor) == pin.sha256,
                f"pinned PNG changed during workflow: {pin.path}")
    finally:
        os.close(descriptor)


def verify_project_file(project: ProjectFile) -> None:
    descriptor = os.open(project.path, os.O_RDONLY |
                         getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and
                (info.st_dev, info.st_ino, info.st_size) ==
                (*project.identity, len(project.payload)) and
                common.path_identity(project.path) == project.identity and
                common.sha256_fd(descriptor) == digest(project.payload),
                "scorebug project changed during workflow")
    finally:
        os.close(descriptor)


def pin_large(path: Path, size: int, sha256: str, label: str) -> LargePin:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(descriptor)
        identity = common.fd_identity(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_size == size and
                identity == (supplied.st_dev, supplied.st_ino) and
                common.path_identity(resolved) == identity and
                common.sha256_fd(descriptor) == sha256,
                f"{label} identity/size/SHA-256 changed")
        return LargePin(resolved, descriptor, size, sha256, identity)
    except Exception:
        os.close(descriptor)
        raise


def verify_large_pin(pin: LargePin) -> None:
    info = os.fstat(pin.descriptor)
    require(stat.S_ISREG(info.st_mode) and
            (info.st_dev, info.st_ino, info.st_size) ==
            (*pin.identity, pin.size) and
            common.path_identity(pin.path) == pin.identity and
            common.sha256_fd(pin.descriptor) == pin.sha256,
            f"pinned canonical input changed during workflow: {pin.path}")


def pin_canonical_inputs() -> tuple[LargePin, LargePin]:
    index = pin_large(CANONICAL_INDEX, INDEX_SIZE, INDEX_SHA256,
                      "canonical extracted pack 0")
    try:
        audit = pin_large(CANONICAL_AUDIT, AUDIT_SIZE, AUDIT_SHA256,
                          "canonical scorebug audit")
        return index, audit
    except Exception:
        os.close(index.descriptor)
        raise


def close_large_pins(pins: tuple[LargePin, LargePin]) -> None:
    for pin in pins:
        os.close(pin.descriptor)


def read_project(path: Path) -> ProjectFile:
    resolved, payload, identity = read_regular_bounded(
        path, MAX_PROJECT_BYTES, "scorebug project")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ScorebugProjectError("scorebug project is invalid JSON") from exc
    require(isinstance(value, dict) and payload == canonical_json(value) and
            set(value) == {"schema", "purpose", "source", "edits"} and
            value.get("schema") == SCHEMA and
            type(value.get("purpose")) is str and
            0 < len(value["purpose"]) <= 4096 and "\0" not in value["purpose"] and
            value.get("source") == SOURCE_PIN and
            isinstance(value.get("edits"), list) and
            1 <= len(value["edits"]) <= len(TARGET_NAMES),
            "scorebug project schema/canonical encoding/source pins mismatch")
    normalized_edits: list[dict[str, Any]] = []
    names: list[str] = []
    for order, record in enumerate(value["edits"]):
        require(isinstance(record, dict) and
                set(record) == {"target", "png", "png_size", "png_sha256"} and
                type(record.get("target")) is str and
                record["target"] in TARGET_NAMES and
                type(record.get("png")) is str and bool(record["png"]) and
                "\0" not in record["png"] and
                type(record.get("png_size")) is int and
                0 < record["png_size"] <= MAX_PNG_BYTES and
                type(record.get("png_sha256")) is str and
                HEX_SHA256.fullmatch(record["png_sha256"]) is not None,
                f"edit {order} has invalid fields/types/target")
        names.append(record["target"])
        normalized_edits.append(dict(record))
    require(len(names) == len(set(names)),
            "each scorebug target may appear at most once")
    normalized = {
        "schema": SCHEMA,
        "purpose": value["purpose"],
        "source": dict(SOURCE_PIN),
        "edits": normalized_edits,
    }
    require(payload == canonical_json(normalized),
            "scorebug project normalization changed canonical encoding")
    return ProjectFile(resolved, payload, normalized, identity)


def edit_png_path(project: ProjectFile, record: dict[str, Any]) -> Path:
    supplied = Path(record["png"])
    return supplied if supplied.is_absolute() else project.path.parent / supplied


def pin_project_pngs(project: ProjectFile) -> dict[str, InputPin]:
    pins: dict[str, InputPin] = {}
    for record in project.value["edits"]:
        name = record["target"]
        resolved, payload, identity = read_regular_bounded(
            edit_png_path(project, record), MAX_PNG_BYTES, f"{name} PNG")
        sha = digest(payload)
        require(len(payload) == record["png_size"] and
                sha == record["png_sha256"],
                f"{name} PNG differs from its project size/SHA-256 pin")
        pins[name] = InputPin(resolved, payload, len(payload), sha, identity)
    return pins


def prepare_project(project: ProjectFile,
                    canonical_pins: tuple[LargePin, LargePin] | None = None) \
        -> list[PreparedEdit]:
    pins = pin_project_pngs(project)
    prepared: list[PreparedEdit] = []
    for order, record in enumerate(project.value["edits"]):
        if canonical_pins is not None:
            require(all(common.path_identity(pin.path) == pin.identity
                        for pin in canonical_pins),
                    "canonical input pathname changed before import")
        name = record["target"]
        pin = pins[name]
        replacement, preview, report = build_import(
            CANONICAL_INDEX, CANONICAL_AUDIT, name, pin.path)
        target = report["target"]
        width, height = TARGET_DIMENSIONS[name]
        require(report["input_png"]["size"] == pin.size and
                report["input_png"]["sha256"] == pin.sha256 and
                (report["input_png"]["width"],
                 report["input_png"]["height"]) == (width, height) and
                target["name"] == name and
                len(replacement) == int(target["span_size"]) and
                digest(replacement) == report["rebuild"]["span_sha256"],
                f"{name} strict importer result does not match its pinned recipe")
        # The strict importer already records differences from the retail span.
        # Reconstruct the exact set from its bounded changed-run ledger, then
        # verify it against the replacement when the retail XISO is opened.
        relative = []
        for first, last in report["rebuild"]["changed_runs"]:
            require(type(first) is int and type(last) is int and
                    0 <= first <= last < len(replacement),
                    f"{name} importer changed-run ledger is invalid")
            relative.extend(range(first, last + 1))
        require(relative and len(relative) == report["rebuild"]["changed_byte_count"],
                f"{name} importer changed-byte ledger is invalid")
        prepared.append(PreparedEdit(
            order, dict(record), pin, replacement, preview, report,
            canonical_json(report), target,
            int(target["xiso_absolute_span_offset"]), relative))
    ordered = sorted(prepared, key=lambda edit: edit.absolute_offset)
    for left, right in zip(ordered, ordered[1:]):
        require(left.end_offset <= right.absolute_offset,
                f"scorebug spans overlap: {left.name}/{right.name}")
    for pin in pins.values():
        verify_pin(pin)
    verify_project_file(project)
    if canonical_pins is not None:
        for pin in canonical_pins:
            verify_large_pin(pin)
    return prepared


def canonical_new_path(path: Path, label: str) -> Path:
    parent = path.parent.resolve(strict=True)
    require(parent.is_dir(), f"{label} parent is not a directory")
    target = parent / path.name
    require(not target.exists() and not target.is_symlink(),
            f"{label} already exists: {target}")
    return target


def validate_source(path: Path) \
        -> tuple[Path, int, tuple[int, int], str,
                 dict[str, common.XdvdfsEntry], dict[str, int], common.XdvdfsEntry]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "source XISO must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(descriptor)
        identity = common.fd_identity(descriptor)
        # Container not pinned -- see the note in nfl2k5_visual_mod_project. The
        # game partition, its file count and default.xbe are still exact below.
        require(stat.S_ISREG(info.st_mode) and
                identity == (supplied.st_dev, supplied.st_ino) and
                common.path_identity(resolved) == identity,
                "source XISO identity/type changed")
        sha = common.sha256_fd(descriptor)
        entries, directory = common.parse_xdvdfs(descriptor, info.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        xbe = entries.get("default.xbe")
        require(len(files) == 19 and xbe is not None and
                xbe.size == common.EXPECTED_XBE_SIZE and
                common.sha256_fd(descriptor, xbe.byte_offset, xbe.size) ==
                    common.EXPECTED_XBE_SHA256,
                "retail XDVDFS/default.xbe identity changed")
        assert xbe is not None
        return resolved, descriptor, identity, sha, entries, directory, xbe
    except Exception:
        os.close(descriptor)
        raise


def bind_to_source(edits: list[PreparedEdit], source_fd: int,
                   entries: dict[str, common.XdvdfsEntry]) -> set[int]:
    allowed: set[int] = set()
    pack_hashes: dict[str, str] = {}
    for edit in edits:
        target = edit.target
        path = str(target["pack_path"])
        pack = entries.get(path.casefold())
        require(pack is not None and
                pack.sector == int(target["xiso_pack_sector"]) and
                pack.byte_offset == int(target["xiso_pack_byte_offset"]) and
                pack.size == int(target["pack_size"]),
                f"retail target pack extent changed: {edit.name}")
        if path not in pack_hashes:
            pack_hashes[path] = common.sha256_fd(
                source_fd, pack.byte_offset, pack.size)
        require(pack_hashes[path] == target["pack_sha256"] and
                pack.byte_offset + int(target["pack_offset"]) ==
                    edit.absolute_offset,
                f"retail target pack identity/arithmetic changed: {edit.name}")
        source_span = common.read_exact(
            source_fd, edit.absolute_offset, len(edit.replacement))
        require(digest(source_span) == target["span_sha256"],
                f"retail target span changed: {edit.name}")
        actual_relative = [index for index, (before, after) in
                           enumerate(zip(source_span, edit.replacement))
                           if before != after]
        require(actual_relative == edit.relative_changed,
                f"importer/source difference ledger changed: {edit.name}")
        overlap = allowed & {
            edit.absolute_offset + value for value in actual_relative
        }
        require(not overlap, f"changed-byte sets overlap: {edit.name}")
        allowed.update(edit.absolute_offset + value for value in actual_relative)
    require(bool(allowed), "project replacement union is empty")
    return allowed


def write_all(descriptor: int, offset: int, payload: bytes) -> None:
    position = 0
    while position < len(payload):
        amount = os.pwrite(descriptor, payload[position:], offset + position)
        require(amount > 0, "short XISO replacement write")
        position += amount


def union_record(edits: list[PreparedEdit], source_fd: int, output_fd: int,
                 source_sha: str, allowed: set[int],
                 source_size: int) -> dict[str, Any]:
    source_after, output_sha, actual = common.compare_and_hash(
        source_fd, output_fd, source_size, allowed)
    require(source_after == source_sha and actual == sorted(allowed),
            "source changed or full-XISO difference union mismatch")
    return {
        "actual_changed_byte_count": len(actual),
        "actual_changed_offsets_u64le_sha256": offset_hash(actual, "<Q"),
        "actual_changed_runs": runs(actual),
        "all_bytes_outside_union_identical": True,
        "output_sha256": output_sha,
        "source_sha256_after": source_after,
        "span_count": len(edits),
        "span_union": [
            {
                "absolute_offset": edit.absolute_offset,
                "size": len(edit.replacement),
                "target": edit.name,
            }
            for edit in sorted(edits, key=lambda item: item.absolute_offset)
        ],
    }


def artifact_payloads(edits: list[PreparedEdit]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for edit in edits:
        result[f"{edit.name}.import.json"] = edit.import_payload
        result[f"{edit.name}.preview.png"] = edit.preview
    return dict(sorted(result.items()))


def create_regular(path: Path, payload: bytes) -> ArtifactFile:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0), 0o644)
    identity = common.fd_identity(descriptor)
    success = False
    try:
        position = 0
        while position < len(payload):
            amount = os.write(descriptor, payload[position:])
            require(amount > 0, "short artifact write")
            position += amount
        os.fsync(descriptor)
        info = os.fstat(descriptor)
        require((info.st_dev, info.st_ino, info.st_size) ==
                (identity[0], identity[1], len(payload)) and
                common.path_identity(path) == identity,
                "artifact pathname/size changed")
        success = True
        return ArtifactFile(path, identity)
    finally:
        os.close(descriptor)
        if not success and common.path_identity(path) == identity:
            path.unlink()


def cleanup_artifacts(root: Path | None, root_identity: tuple[int, int] | None,
                      files: list[ArtifactFile]) -> None:
    for item in reversed(files):
        if common.path_identity(item.path) == item.identity:
            item.path.unlink()
    if (root is not None and root_identity is not None and
            common.path_identity(root) == root_identity):
        try:
            root.rmdir()
        except OSError:
            pass


def create_artifacts(path: Path, payloads: dict[str, bytes]) \
        -> tuple[Path, tuple[int, int], list[ArtifactFile], dict[str, Any]]:
    os.mkdir(path, 0o755)
    info = path.stat(follow_symlinks=False)
    identity = (info.st_dev, info.st_ino)
    require(stat.S_ISDIR(info.st_mode), "artifact directory is not a directory")
    files: list[ArtifactFile] = []
    success = False
    try:
        for name, payload in payloads.items():
            files.append(create_regular(path / name, payload))
        require(common.path_identity(path) == identity and
                {child.name for child in path.iterdir()} == set(payloads),
                "artifact directory changed during creation")
        ledger = {
            name: {"sha256": digest(payload), "size": len(payload)}
            for name, payload in payloads.items()
        }
        success = True
        return path, identity, files, ledger
    finally:
        if not success:
            cleanup_artifacts(path, identity, files)


def verify_artifacts(path: Path, payloads: dict[str, bytes]) \
        -> tuple[Path, tuple[int, int], dict[str, Any]]:
    supplied = path.lstat()
    require(stat.S_ISDIR(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "artifact directory must be a non-symlink directory")
    resolved = path.resolve(strict=True)
    identity = (supplied.st_dev, supplied.st_ino)
    require(common.path_identity(resolved) == identity and
            {child.name for child in resolved.iterdir()} == set(payloads),
            "artifact directory identity/file set changed")
    ledger: dict[str, Any] = {}
    for name, expected in payloads.items():
        child, actual, _ = read_regular_bounded(
            resolved / name, MAX_MANIFEST_BYTES, f"artifact {name}")
        require(actual == expected,
                f"artifact differs from independently rebuilt input: {name}")
        ledger[name] = {"sha256": digest(actual), "size": len(actual)}
        require(child.parent == resolved, "artifact escaped its directory")
    require(common.path_identity(resolved) == identity and
            {child.name for child in resolved.iterdir()} == set(payloads),
            "artifact directory changed during verification")
    return resolved, identity, ledger


def stable_edit_record(edit: PreparedEdit) -> dict[str, Any]:
    return {
        "import_manifest": edit.import_report,
        "import_manifest_sha256": digest(edit.import_payload),
        "input_png": {
            "path": str(edit.pin.path),
            "project_path": edit.recipe["png"],
            "sha256": edit.pin.sha256,
            "size": edit.pin.size,
        },
        "order": edit.order,
        "patch": {
            "absolute_span_offset": edit.absolute_offset,
            "pack_offset": int(edit.target["pack_offset"]),
            "pack_path": edit.target["pack_path"],
            "relative_changed_byte_count": len(edit.relative_changed),
            "relative_changed_offsets_u32le_sha256":
                offset_hash(edit.relative_changed, "<I"),
            "relative_changed_runs": runs(edit.relative_changed),
            "replacement_span_sha256": digest(edit.replacement),
            "replacement_span_size": len(edit.replacement),
            "retail_span_sha256": edit.target["span_sha256"],
        },
        "target": edit.name,
        "target_dimensions": {
            "height": TARGET_DIMENSIONS[edit.name][1],
            "width": TARGET_DIMENSIONS[edit.name][0],
        },
    }


def claims(edits: list[PreparedEdit]) -> dict[str, Any]:
    names = {edit.name for edit in edits}
    return {
        "code_bound_field_scorebug_textures_selected":
            sorted(names & {"score_buga", "shield_espn"}),
        "digital_font_has_global_ui_side_effects": "digital_font" in names,
        "layout_identical_copy_only_xiso": True,
        "loader_in_place_decode_guarded": True,
        "originals_modified": False,
        "portme": (
            "PORTME(runtime): boot this copied XISO in xemu and capture every "
            "selected texture in the field HUD and any global-font side effects."
        ),
        "runtime_visibility_proved": False,
        "title_executed": False,
        "xemu_started": False,
    }


def make_manifest(project: ProjectFile, edits: list[PreparedEdit], source: Path,
                  source_identity: tuple[int, int], source_sha: str,
                  output: Path, output_identity: tuple[int, int],
                  copy_method: str, manifest: Path, artifact_dir: Path,
                  artifact_identity: tuple[int, int], artifact_ledger: dict[str, Any],
                  directory: dict[str, int], union: dict[str, Any],
                  source_size: int) -> dict[str, Any]:
    return {
        "artifacts": {
            "device": artifact_identity[0],
            "directory": str(artifact_dir),
            "file_count": len(artifact_ledger),
            "files": dict(sorted(artifact_ledger.items())),
            "inode": artifact_identity[1],
        },
        "canonical_inputs": {
            "index": {"path": str(CANONICAL_INDEX.resolve(strict=True)),
                      "sha256": INDEX_SHA256, "size": INDEX_SIZE},
            "scorebug_audit": {"path": str(CANONICAL_AUDIT.resolve(strict=True)),
                               "sha256": AUDIT_SHA256, "size": AUDIT_SIZE},
        },
        "claims": claims(edits),
        "edits": [stable_edit_record(edit) for edit in edits],
        "output": {
            "copy_method": copy_method,
            "device": output_identity[0],
            "exclusively_created": True,
            "inode": output_identity[1],
            "manifest_path": str(manifest),
            "xiso_path": str(output),
            "xiso_sha256": union["output_sha256"],
            "xiso_size": source_size,
        },
        "patch": union,
        "project": {
            "edit_count": len(edits),
            "path": str(project.path),
            "purpose": project.value["purpose"],
            "sha256": digest(project.payload),
            "size": len(project.payload),
            "source_pins": dict(SOURCE_PIN),
        },
        "schema": BUILD_SCHEMA,
        "source": {
            "device": source_identity[0],
            "inode": source_identity[1],
            "modified": False,
            "opened_read_only": True,
            "path": str(source),
            "sha256_before": source_sha,
            "sha256_after": union["source_sha256_after"],
            "size": source_size,
        },
        "xdvdfs": {
            **directory,
            "all_sector_extents_preserved": True,
            "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
            "file_count": 19,
            "tree_identical_after_patch": True,
        },
    }


def validate_only(project_path: Path) -> dict[str, Any]:
    project = read_project(project_path)
    canonical_pins = pin_canonical_inputs()
    try:
        edits = prepare_project(project, canonical_pins)
        for edit in edits:
            verify_pin(edit.pin)
        verify_project_file(project)
        for pin in canonical_pins:
            verify_large_pin(pin)
        return {
            "edit_count": len(edits),
            "project_path": str(project.path),
            "project_sha256": digest(project.payload),
            "schema": SCHEMA,
            "source_pins_valid": True,
            "strict_importers_passed": True,
            "targets": [edit.name for edit in edits],
            "target_dimensions": {
                name: {"width": TARGET_DIMENSIONS[name][0],
                       "height": TARGET_DIMENSIONS[name][1]}
                for name in (edit.name for edit in edits)
            },
        }
    finally:
        close_large_pins(canonical_pins)


def build(project_path: Path, source_path: Path, output_path: Path,
          manifest_path: Path, artifact_dir_path: Path) -> dict[str, Any]:
    project = read_project(project_path)
    canonical_pins = pin_canonical_inputs()
    try:
        return _build_pinned(project, canonical_pins, source_path, output_path,
                             manifest_path, artifact_dir_path)
    finally:
        close_large_pins(canonical_pins)


def _build_pinned(project: ProjectFile,
                  canonical_pins: tuple[LargePin, LargePin],
                  source_path: Path, output_path: Path,
                  manifest_path: Path, artifact_dir_path: Path) -> dict[str, Any]:
    edits = prepare_project(project, canonical_pins)
    output = canonical_new_path(output_path, "output XISO")
    manifest = canonical_new_path(manifest_path, "build manifest")
    artifact_dir = canonical_new_path(artifact_dir_path, "artifact directory")
    source, source_fd, source_identity, source_sha, entries, directory, xbe = \
        validate_source(source_path)
    output_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    artifacts_root: Path | None = None
    artifacts_identity: tuple[int, int] | None = None
    artifact_files: list[ArtifactFile] = []
    success = False
    try:
        fixed = (
            {project.path, source, output, manifest, artifact_dir,
             CANONICAL_INDEX.resolve(strict=True),
             CANONICAL_AUDIT.resolve(strict=True)} |
            {edit.pin.path for edit in edits}
        )
        require(len(fixed) == 7 + len({edit.pin.path for edit in edits}),
                "project/source/input/output paths alias")
        allowed = bind_to_source(edits, source_fd, entries)
        # The build copies the user's container and patches it in place, so
        # every length here is the size of THEIR file. Using the project's own
        # EXPECTED_XISO_SIZE truncated or over-read any legal dump packaged
        # differently, which is why Build refused images that had loaded fine.
        source_size = os.fstat(source_fd).st_size
        output_owned = common.reserve_file(output)
        require(output_owned.identity != source_identity, "output aliases source")
        copy_method = common.copy_fd_exact(
            source_fd, output_owned.descriptor, source_size)
        for edit in edits:
            write_all(output_owned.descriptor, edit.absolute_offset, edit.replacement)
            require(common.read_exact(output_owned.descriptor, edit.absolute_offset,
                                      len(edit.replacement)) == edit.replacement,
                    f"replacement readback failed: {edit.name}")
        os.fsync(output_owned.descriptor)
        require(common.owned_path_matches(output_owned),
                "output pathname changed during build")
        union = union_record(edits, source_fd, output_owned.descriptor,
                             source_sha, allowed)
        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_size)
        require(output_entries == entries and output_directory == directory and
                common.sha256_fd(output_owned.descriptor,
                                 xbe.byte_offset, xbe.size) ==
                    common.EXPECTED_XBE_SHA256,
                "output XDVDFS tree/default.xbe changed")
        payloads = artifact_payloads(edits)
        artifacts_root, artifacts_identity, artifact_files, artifact_ledger = \
            create_artifacts(artifact_dir, payloads)
        result = make_manifest(
            project, edits, source, source_identity, source_sha,
            output, output_owned.identity, copy_method, manifest,
            artifacts_root, artifacts_identity, artifact_ledger,
            directory, union, source_size)
        manifest_owned = common.reserve_file(manifest)
        common.write_owned_json(manifest_owned, result)
        for edit in edits:
            verify_pin(edit.pin)
        verify_project_file(project)
        for pin in canonical_pins:
            verify_large_pin(pin)
        require(common.path_identity(source) == source_identity and
                common.owned_path_matches(output_owned) and
                common.owned_path_matches(manifest_owned) and
                common.path_identity(artifacts_root) == artifacts_identity,
                "build pathname identity changed before commit")
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
            cleanup_artifacts(artifacts_root, artifacts_identity, artifact_files)


def read_manifest(path: Path) \
        -> tuple[Path, bytes, dict[str, Any], tuple[int, int]]:
    resolved, payload, identity = read_regular_bounded(
        path, MAX_MANIFEST_BYTES, "build manifest")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ScorebugProjectError("build manifest is invalid JSON") from exc
    require(isinstance(value, dict) and payload == canonical_json(value) and
            set(value) == {"schema", "project", "source", "canonical_inputs",
                           "edits", "output", "xdvdfs", "patch", "claims",
                           "artifacts"} and value.get("schema") == BUILD_SCHEMA,
            "build manifest schema/canonical encoding mismatch")
    return resolved, payload, value, identity


def open_output(path: Path, source_identity: tuple[int, int],
                source_size: int) -> tuple[Path, int, tuple[int, int]]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "output XISO must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(descriptor)
        identity = common.fd_identity(descriptor)
        require(stat.S_ISREG(info.st_mode) and
                info.st_size == source_size and
                identity == (supplied.st_dev, supplied.st_ino) and
                identity != source_identity and
                common.path_identity(resolved) == identity,
                "output XISO identity/type/size mismatch")
        return resolved, descriptor, identity
    except Exception:
        os.close(descriptor)
        raise


def verify(project_path: Path, source_path: Path, output_path: Path,
           manifest_path: Path, artifact_dir_path: Path) -> dict[str, Any]:
    project = read_project(project_path)
    canonical_pins = pin_canonical_inputs()
    try:
        return _verify_pinned(project, canonical_pins, source_path, output_path,
                              manifest_path, artifact_dir_path)
    finally:
        close_large_pins(canonical_pins)


def _verify_pinned(project: ProjectFile,
                   canonical_pins: tuple[LargePin, LargePin],
                   source_path: Path, output_path: Path,
                   manifest_path: Path, artifact_dir_path: Path) -> dict[str, Any]:
    edits = prepare_project(project, canonical_pins)
    manifest_path_resolved, manifest_payload, manifest_value, manifest_identity = \
        read_manifest(manifest_path)
    source, source_fd, source_identity, source_sha, entries, directory, xbe = \
        validate_source(source_path)
    output_fd: int | None = None
    try:
        output, output_fd, output_identity = open_output(
            output_path, source_identity, os.fstat(source_fd).st_size)
        require(len({project.path, source, output, manifest_path_resolved,
                     CANONICAL_INDEX.resolve(strict=True),
                     CANONICAL_AUDIT.resolve(strict=True),
                     *[edit.pin.path for edit in edits]}) ==
                6 + len({edit.pin.path for edit in edits}),
                "project/source/input/output/manifest paths alias")
        allowed = bind_to_source(edits, source_fd, entries)
        union = union_record(edits, source_fd, output_fd, source_sha, allowed,
                             os.fstat(source_fd).st_size)
        output_entries, output_directory = common.parse_xdvdfs(
            output_fd, os.fstat(source_fd).st_size)
        require(output_entries == entries and output_directory == directory and
                common.sha256_fd(output_fd, xbe.byte_offset, xbe.size) ==
                    common.EXPECTED_XBE_SHA256,
                "verified output XDVDFS tree/default.xbe changed")
        payloads = artifact_payloads(edits)
        artifact_dir, artifact_identity, artifact_ledger = verify_artifacts(
            artifact_dir_path, payloads)
        copy_method = manifest_value.get("output", {}).get("copy_method")
        require(copy_method in {"copy_file_range", "pread_pwrite"},
                "build manifest copy method is invalid")
        expected = make_manifest(
            project, edits, source, source_identity, source_sha,
            output, output_identity, copy_method, manifest_path_resolved,
            artifact_dir, artifact_identity, artifact_ledger, directory, union,
            os.fstat(source_fd).st_size)
        require(manifest_value == expected,
                "build manifest differs from independently reconstructed proof")
        for edit in edits:
            verify_pin(edit.pin)
        verify_project_file(project)
        for pin in canonical_pins:
            verify_large_pin(pin)
        manifest_pin = InputPin(
            manifest_path_resolved, manifest_payload, len(manifest_payload),
            digest(manifest_payload), manifest_identity)
        verify_pin(manifest_pin)
        require(common.path_identity(source) == source_identity and
                common.path_identity(output) == output_identity and
                common.path_identity(artifact_dir) == artifact_identity,
                "verification pathname identity changed")
        return {
            "all_bytes_outside_union_identical": True,
            "artifacts_reconstructed": True,
            "changed_byte_count": union["actual_changed_byte_count"],
            "default_xbe_unchanged": True,
            "edit_count": len(edits),
            "manifest_sha256": digest(manifest_payload),
            "output_sha256": union["output_sha256"],
            "project_sha256": digest(project.payload),
            "runtime_visibility_proved": False,
            "schema": VERIFY_SCHEMA,
            "source_sha256": source_sha,
            "targets": [edit.name for edit in edits],
            "union_reconstructed_from_recipe_source_and_importers": True,
            "xdvdfs_identical": True,
        }
    finally:
        os.close(source_fd)
        if output_fd is not None:
            os.close(output_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser(
        "validate", help="validate canonical recipe, pins, dimensions, and imports")
    validate_parser.add_argument("--project", required=True, type=Path)
    for command in ("build", "verify"):
        item = subparsers.add_parser(command)
        item.add_argument("--project", required=True, type=Path)
        item.add_argument("--source-xiso", required=True, type=Path)
        item.add_argument("--output-xiso", required=True, type=Path)
        item.add_argument("--manifest", required=True, type=Path)
        item.add_argument("--artifact-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            result = validate_only(args.project)
            print(json.dumps(result, sort_keys=True))
        elif args.command == "build":
            result = build(args.project, args.source_xiso, args.output_xiso,
                           args.manifest, args.artifact_dir)
            print("NFL2K5_SCOREBUG_MOD_BUILD_PASS "
                  f"targets={len(result['edits'])} "
                  f"changed={result['patch']['actual_changed_byte_count']} "
                  f"sha256={result['output']['xiso_sha256']} runtime=false")
        else:
            result = verify(args.project, args.source_xiso, args.output_xiso,
                            args.manifest, args.artifact_dir)
            print("NFL2K5_SCOREBUG_MOD_VERIFY_PASS "
                  f"targets={result['edit_count']} "
                  f"changed={result['changed_byte_count']} "
                  f"sha256={result['output_sha256']} runtime=false")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
