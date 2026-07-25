#!/usr/bin/env python3
"""Fail-closed APF 2K8 ROST jersey-selector writer.

The writer changes only byte 0 of the two jersey selector records derived for
an authorized built-in team.  It resolves every target through the retail
ROST root and one-based relative pointers, preserves selector bytes 1..7 and
all other decoded bytes, emits a bounded H7A/IFF rebuild, and patches only the
fixed roster outer entry in a newly copied 0A volume.

This is an offline serializer proof.  Runtime visibility in Xenia and Xbox 360
hardware acceptance remain separate, explicitly false claims.
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

import apf_inner
import apf_outer
import apf_roster
import apf_texture_patch as transport


def change_time_identity(info: os.stat_result) -> tuple[int, ...]:
    """``(info.st_ctime_ns,)`` on POSIX; ``()`` on Windows.

    Inlined rather than imported from
    :mod:`mod_editor.core.platform_compat` because this module is executed as a
    self-contained, tools-only closure and may not import the editor package;
    the contract is byte-for-byte that helper's.

    On Windows a path stat and an fd stat of the *same, untouched* file do not
    agree on ``st_ctime``, so putting it in an identity tuple refuses a file
    nothing touched.  ``st_dev``/``st_ino`` stay the identity and
    ``st_size``/``st_mtime_ns`` stay the change detectors, so a swapped or
    rewritten file is still caught.  What is genuinely lost on Windows is the
    metadata-only-change signal -- a permission or attribute edit that leaves
    the bytes, the size and the modification time untouched -- and Windows
    offers no equivalent field that is stable across the two calls, so this
    check is weaker there than on POSIX.  Stated, not hidden.
    """

    if sys.platform.startswith("win"):
        return ()
    return (info.st_ctime_ns,)


ROOT = Path(__file__).resolve().parents[1]
FORMAT_SPEC = ROOT / "reports/specs/apf2k8_roster_jersey_selector_writeback.v1.json"
FORMAT_SPEC_SIZE = 33_352
FORMAT_SPEC_SHA256 = "c769e983132f8c6041e8a1961585b7e2f96113cf892b590fdc0d48b1218575f1"
RECIPE_SCHEMA_FILE = ROOT / "reports/specs/apf2k8_jersey_selector_assignment_recipe.schema.json"
RECIPE_SCHEMA_FILE_SIZE = 26_227
RECIPE_SCHEMA_FILE_SHA256 = "5e21fa1c18486743558eb3b1caab2c8a99e45166e3dbb5ed1f979e9f930ecf90"

RECIPE_SCHEMA = "apf2k8_jersey_selector_assignment_recipe/v1"
MANIFEST_SCHEMA = "apf2k8_jersey_selector_patch/v1"
OPERATION = "replace_jersey_selector_byte0_in_both_banks"
MAX_RECIPE_BYTES = 64 * 1024

SOURCE_VOLUME_SIZE = 1_140_850_688
SOURCE_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
SOURCE_PREFIX_SHA256 = "e771b5533d94ae0f9e5dc6dccf6fd81d13a93894b1e01807e69a10ce8407e550"
SOURCE_SUFFIX_SHA256 = "cebb3cf73db1047d74a08ea4c8eb86ef38ed7c3472b23ee92fa835ad0c56bb0c"
ARCHIVE_MAGIC = 0xAA00B3BF
ARCHIVE_ALIGNMENT = 2048
ARCHIVE_ENTRY_COUNT = 1543
ARCHIVE_DIRECTORY_SIZE = 0x48AC
ARCHIVE_DIRECTORY_SHA256 = "2463120a5fd4aacec49e50585eb23a4fc3ee27759f7bd11b407d35a2ab809942"
ARCHIVE_PACKS = (
    ("0A", 557056),
    ("0B", 524335),
    ("1A", 557056),
    ("1B", 252916),
)

OUTER_INDEX = 1126
OUTER_NAME_ID = 0xBCEFFD46
OUTER_OFFSET = 47_699_968
OUTER_SIZE = 436_224
OUTER_SHA256 = "e98dd07b38caa73ea2ce91eed19bef68896f9b63830a9169af4b7f22d8788cc7"
SOURCE_FILE_LENGTH = 435_329
IFF_HEADER_SIZE = 84
FOOTER_TOTAL = 96
FOOTER_SHA256 = "70f420d23342ac94ad3ce62f1acfe986f69f6b8c9a4461323b087f80d783a6d7"
SOURCE_TAIL_SIZE = 799

DECODED_SIZE = 2_294_304
DECODED_SHA256 = "e959d3067ebcdbeb4f08979fa74d9fa61cf90fd91b90793863e6a3313be7f7ff"
H7A_SHIFT = 10
H7A_UNKNOWN = 7
SOURCE_H7A_PAYLOAD_SIZE = 435_225
MAX_H7A_PAYLOAD_SIZE = 436_024

TEAM_TABLE = 4
TEAM_STRIDE = 0x180
TEAM_CONFIG_POINTER_OFFSET = 0xBC
CONFIG_TABLE = 19
CONFIG_STRIDE = 0x98
SELECTOR_TABLE = 17
SELECTOR_STRIDE = 8
BANK_COUNT = 2
SLOTS_PER_BANK = 14
JERSEY_SLOT = 4
BUILT_IN_COUNT = 24
CATALOG_COUNT = 24

BUILT_IN_NAMES = (
    "Americans", "Assassins", "Beasts", "Cobras", "Cougars", "Cyclones",
    "Federals", "Firebirds", "Gunslingers", "Indians", "Iron Men", "Knights",
    "Legends", "Minutemen", "Red Dogs", "Rhinos", "Rollers", "Rustlers",
    "Sailors", "Scorpions", "Sharks", "Top Guns", "Wasps", "Werewolves",
)
RETAIL_BUILT_IN_ASSETS = (
    6, 11, 0, 2, 23, 19, 13, 4, 23, 23, 23, 23,
    23, 23, 23, 23, 23, 2, 8, 23, 23, 23, 4, 2,
)

RECIPE_CONSTANTS: dict[str, Any] = {
    "schema": RECIPE_SCHEMA,
    "operation": OPERATION,
    "game": {"platform": "Xbox 360", "title": "All-Pro Football 2K8"},
    "source_contract": {
        "outer_entry_index": OUTER_INDEX,
        "outer_entry_sha256": OUTER_SHA256,
        "retail_0A_sha256": SOURCE_VOLUME_SHA256,
    },
}


class PatchError(ValueError):
    """The source, recipe, compressed stream, or output contract failed."""


@dataclass(frozen=True)
class H7AToken:
    kind: str
    output_start: int
    length: int
    literal: int | None
    distance: int | None


@dataclass(frozen=True)
class SelectorLayout:
    tables: tuple[apf_roster.RootTable, ...]
    offsets: tuple[tuple[int, int], ...]
    record_indices: tuple[tuple[int, int], ...]
    retail_assets: tuple[int, ...]


@dataclass(frozen=True)
class BuildResult:
    entry: bytes
    manifest: dict[str, Any]


@dataclass
class BoundSourceVolume:
    path: Path
    descriptor: int
    identity: tuple[int, int]
    size: int
    times: tuple[int, ...]
    metadata: os.stat_result
    sha256: str


@dataclass
class BoundOutputReservation:
    path: Path
    parent_path: Path
    parent_descriptor: int
    parent_identity: tuple[int, int]
    descriptor: int
    identity: tuple[int, int]


class BytesReader:
    def __init__(self, data: bytes):
        self.data = data

    def read(self, entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise apf_inner.FormatError("memory entry read is outside its fixed span")
        return self.data[offset : offset + size]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    size = os.fstat(descriptor).st_size
    cursor = 0
    while cursor < size:
        chunk = os.pread(descriptor, min(8 * 1024 * 1024, size - cursor), cursor)
        if not chunk:
            raise PatchError("short descriptor read while hashing")
        digest.update(chunk)
        cursor += len(chunk)
    return digest.hexdigest()


def _pread_exact(descriptor: int, size: int, offset: int) -> bytes:
    if size < 0 or offset < 0:
        raise PatchError("negative descriptor read range")
    chunks: list[bytes] = []
    cursor = offset
    remaining = size
    while remaining:
        chunk = os.pread(descriptor, remaining, cursor)
        if not chunk:
            raise PatchError("short descriptor read")
        chunks.append(chunk)
        cursor += len(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _pwrite_all(descriptor: int, data: bytes, offset: int) -> None:
    if offset < 0:
        raise PatchError("negative descriptor write offset")
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = os.pwrite(descriptor, view[written:], offset + written)
        if count <= 0:
            raise PatchError("short descriptor write")
        written += count


def _sha256_fd_range(descriptor: int, offset: int, size: int) -> str:
    metadata = os.fstat(descriptor)
    if offset < 0 or size < 0 or offset > metadata.st_size or size > metadata.st_size - offset:
        raise PatchError("descriptor hash range is out of bounds")
    digest = hashlib.sha256()
    cursor = offset
    remaining = size
    while remaining:
        chunk = os.pread(descriptor, min(8 * 1024 * 1024, remaining), cursor)
        if not chunk:
            raise PatchError("short descriptor read while hashing a range")
        digest.update(chunk)
        cursor += len(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def _stat_times(metadata: os.stat_result) -> tuple[int, ...]:
    return metadata.st_mtime_ns, *change_time_identity(metadata)


def _assert_bound_source(source: BoundSourceVolume) -> None:
    current = os.fstat(source.descriptor)
    if (
        not stat.S_ISREG(current.st_mode)
        or (current.st_dev, current.st_ino) != source.identity
        or current.st_size != source.size
        or _stat_times(current) != source.times
    ):
        raise PatchError("source 0A descriptor changed during copied-volume transaction")
    try:
        direct = os.lstat(source.path)
        resolved = source.path.resolve(strict=True)
    except OSError as exc:
        raise PatchError("source 0A pathname disappeared during copied-volume transaction") from exc
    if (
        not stat.S_ISREG(direct.st_mode)
        or stat.S_ISLNK(direct.st_mode)
        or (direct.st_dev, direct.st_ino) != source.identity
        or resolved != source.path
    ):
        raise PatchError("source 0A pathname changed during copied-volume transaction")


def _bind_source_volume(path: Path) -> BoundSourceVolume:
    path = _absolute_no_symlink_path(path, "source 0A for copied-volume transaction")
    before = os.lstat(path)
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_size != SOURCE_VOLUME_SIZE
    ):
        raise PatchError("copied-volume source is not the pinned retail 0A shape")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        if (
            not stat.S_ISREG(opened.st_mode)
            or identity != (before.st_dev, before.st_ino)
            or opened.st_size != SOURCE_VOLUME_SIZE
        ):
            raise PatchError("copied-volume source pathname changed while opening")
        source = BoundSourceVolume(
            path=path,
            descriptor=descriptor,
            identity=identity,
            size=opened.st_size,
            times=_stat_times(opened),
            metadata=opened,
            sha256=_sha256_fd(descriptor),
        )
        if source.sha256 != SOURCE_VOLUME_SHA256:
            raise PatchError("copied-volume source SHA-256 differs from pinned retail 0A")
        _assert_bound_source(source)
        return source
    except Exception:
        os.close(descriptor)
        raise


def _assert_bound_output(
    reservation: BoundOutputReservation,
    *,
    expected_size: int | None = None,
    expected_times: tuple[int, ...] | None = None,
) -> os.stat_result:
    current = os.fstat(reservation.descriptor)
    if (
        not stat.S_ISREG(current.st_mode)
        or (current.st_dev, current.st_ino) != reservation.identity
        or (expected_size is not None and current.st_size != expected_size)
        or (expected_times is not None and _stat_times(current) != expected_times)
    ):
        raise PatchError("reserved output descriptor changed")
    parent = os.fstat(reservation.parent_descriptor)
    if (
        not stat.S_ISDIR(parent.st_mode)
        or (parent.st_dev, parent.st_ino) != reservation.parent_identity
    ):
        raise PatchError("reserved output parent descriptor changed")
    try:
        named = os.stat(
            reservation.path.name,
            dir_fd=reservation.parent_descriptor,
            follow_symlinks=False,
        )
        direct_parent = os.lstat(reservation.parent_path)
        resolved_parent = reservation.parent_path.resolve(strict=True)
    except OSError as exc:
        raise PatchError("reserved output pathname or parent disappeared") from exc
    if (
        not stat.S_ISREG(named.st_mode)
        or (named.st_dev, named.st_ino) != reservation.identity
        or not stat.S_ISDIR(direct_parent.st_mode)
        or stat.S_ISLNK(direct_parent.st_mode)
        or (direct_parent.st_dev, direct_parent.st_ino) != reservation.parent_identity
        or resolved_parent != reservation.parent_path
    ):
        raise PatchError("reserved output pathname or parent changed")
    return current


def _reserve_bound_output(path: Path, mode: int) -> BoundOutputReservation:
    if path.name in {"", ".", ".."}:
        raise PatchError("output filename is invalid")
    parent_path = path.parent
    before = os.lstat(parent_path)
    if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise PatchError("output parent is not a real directory")
    parent_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    parent_descriptor = os.open(parent_path, parent_flags)
    descriptor = -1
    identity: tuple[int, int] | None = None
    try:
        parent = os.fstat(parent_descriptor)
        parent_identity = (parent.st_dev, parent.st_ino)
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent_identity != (before.st_dev, before.st_ino)
        ):
            raise PatchError("output parent pathname changed while opening")
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(
            path.name,
            flags,
            mode,
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size != 0:
            raise PatchError("new output reservation is not an empty regular file")
        identity = (opened.st_dev, opened.st_ino)
        reservation = BoundOutputReservation(
            path=path,
            parent_path=parent_path,
            parent_descriptor=parent_descriptor,
            parent_identity=parent_identity,
            descriptor=descriptor,
            identity=identity,
        )
        _assert_bound_output(reservation, expected_size=0)
        return reservation
    except Exception:
        if identity is not None:
            try:
                named = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
                if stat.S_ISREG(named.st_mode) and (named.st_dev, named.st_ino) == identity:
                    os.unlink(path.name, dir_fd=parent_descriptor)
            except OSError:
                pass
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        os.close(parent_descriptor)
        raise


def _close_bound_output(reservation: BoundOutputReservation, *, keep: bool) -> None:
    if not keep:
        try:
            named = os.stat(
                reservation.path.name,
                dir_fd=reservation.parent_descriptor,
                follow_symlinks=False,
            )
            if (
                stat.S_ISREG(named.st_mode)
                and (named.st_dev, named.st_ino) == reservation.identity
            ):
                os.unlink(reservation.path.name, dir_fd=reservation.parent_descriptor)
        except OSError:
            pass
    try:
        os.close(reservation.descriptor)
    except OSError:
        pass
    try:
        os.close(reservation.parent_descriptor)
    except OSError:
        pass


def _commit_bound_output(
    reservation: BoundOutputReservation, data: bytes
) -> tuple[int, ...]:
    os.ftruncate(reservation.descriptor, 0)
    _pwrite_all(reservation.descriptor, data, 0)
    os.ftruncate(reservation.descriptor, len(data))
    os.fsync(reservation.descriptor)
    current = _assert_bound_output(reservation, expected_size=len(data))
    if _sha256_fd(reservation.descriptor) != sha256_bytes(data):
        raise PatchError("reserved output content differs after write-back")
    return _stat_times(current)


def _write_bound_copied_volume(
    source: BoundSourceVolume,
    output: BoundOutputReservation,
    replacement: bytes,
) -> tuple[dict[str, object], tuple[int, ...]]:
    if source.identity == output.identity:
        raise PatchError("source and copied output alias the same inode")
    if source.size != SOURCE_VOLUME_SIZE or source.sha256 != SOURCE_VOLUME_SHA256:
        raise PatchError("copied-volume source identity is not pinned retail 0A")
    if len(replacement) != OUTER_SIZE:
        raise PatchError("replacement ROST span differs from its fixed allocation")
    _assert_bound_source(source)
    _assert_bound_output(output, expected_size=0)

    copied_source = hashlib.sha256()
    cursor = 0
    while cursor < source.size:
        chunk = os.pread(
            source.descriptor,
            min(8 * 1024 * 1024, source.size - cursor),
            cursor,
        )
        if not chunk:
            raise PatchError("unexpected end of source 0A during bound copy")
        copied_source.update(chunk)
        _pwrite_all(output.descriptor, chunk, cursor)
        cursor += len(chunk)
    if copied_source.hexdigest() != SOURCE_VOLUME_SHA256:
        raise PatchError("bytes read during copied-volume copy differ from pinned retail 0A")
    os.ftruncate(output.descriptor, source.size)

    prefix_length = OUTER_OFFSET
    suffix_offset = OUTER_OFFSET + len(replacement)
    before = _pread_exact(output.descriptor, len(replacement), prefix_length)
    mode = "bit_exact_no_op" if before == replacement else "replaced_entry"
    _pwrite_all(output.descriptor, replacement, prefix_length)
    os.fsync(output.descriptor)
    if os.fstat(output.descriptor).st_size != SOURCE_VOLUME_SIZE:
        raise PatchError("copied output volume size changed")
    written = _pread_exact(output.descriptor, len(replacement), prefix_length)
    if written != replacement:
        raise PatchError("copied-volume replacement read-back differs")

    suffix_length = SOURCE_VOLUME_SIZE - suffix_offset
    output_prefix_sha = _sha256_fd_range(output.descriptor, 0, prefix_length)
    output_suffix_sha = _sha256_fd_range(
        output.descriptor, suffix_offset, suffix_length
    )
    if (
        output_prefix_sha != SOURCE_PREFIX_SHA256
        or output_suffix_sha != SOURCE_SUFFIX_SHA256
    ):
        raise PatchError("copied 0A complement differs from pinned retail spans")
    output_sha = _sha256_fd(output.descriptor)
    source_sha_after = _sha256_fd(source.descriptor)
    if source_sha_after != SOURCE_VOLUME_SHA256:
        raise PatchError("source 0A changed during copied-volume transaction")
    _assert_bound_source(source)

    transport._copy_fd_metadata(  # type: ignore[attr-defined]
        source.descriptor,
        output.descriptor,
        source.metadata,
    )
    os.fsync(output.descriptor)
    output_metadata = _assert_bound_output(
        output, expected_size=SOURCE_VOLUME_SIZE
    )
    _assert_bound_source(source)
    return ({
        "mode": mode,
        "source_volume": str(source.path),
        "output_volume": str(output.path),
        "volume_size": SOURCE_VOLUME_SIZE,
        "replacement_read_back_sha256": sha256_bytes(written),
        "source_volume_sha256_before": source.sha256,
        "source_volume_sha256_after": source_sha_after,
        "output_volume_sha256": output_sha,
        "outside_replacement": {
            "prefix_length": prefix_length,
            "prefix_sha256": output_prefix_sha,
            "suffix_offset": suffix_offset,
            "suffix_length": suffix_length,
            "suffix_sha256": output_suffix_sha,
            "source_and_output_match": True,
        },
    }, _stat_times(output_metadata))


def _absolute_no_symlink_path(path: Path, what: str) -> Path:
    raw = path.expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    raw = Path(os.path.normpath(raw))
    try:
        resolved = raw.resolve(strict=True)
    except OSError as exc:
        raise PatchError(f"cannot resolve {what}: {exc}") from exc
    if resolved != raw.absolute():
        raise PatchError(f"{what} path contains a symlink")
    return raw


def _new_output_path(path: Path, what: str) -> Path:
    raw = path.expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    raw = Path(os.path.normpath(raw))
    parent = raw.parent
    try:
        metadata = os.lstat(parent)
    except OSError as exc:
        raise PatchError(f"{what} parent must already exist: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise PatchError(f"{what} parent is not a real directory")
    resolved = parent.resolve(strict=True)
    if resolved != parent.absolute():
        raise PatchError(f"{what} parent path contains a symlink")
    result = resolved / raw.name
    if os.path.lexists(result):
        raise PatchError(f"refusing existing {what}")
    return result


def _read_bound_file(path: Path, maximum: int, what: str) -> bytes:
    path = _absolute_no_symlink_path(path, what)
    before = os.lstat(path)
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
        raise PatchError(f"{what} is not a bounded regular non-symlink file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        if identity != (before.st_dev, before.st_ino) or not stat.S_ISREG(opened.st_mode) or opened.st_size != before.st_size:
            raise PatchError(f"{what} pathname changed during open")
        raw = _pread_exact(descriptor, opened.st_size, 0)
        after = os.lstat(path)
        if (after.st_dev, after.st_ino) != identity or os.fstat(descriptor).st_size != opened.st_size:
            raise PatchError(f"{what} pathname or length changed during read")
        return raw
    finally:
        os.close(descriptor)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _load_canonical_json(path: Path, maximum: int, what: str) -> tuple[dict[str, Any], bytes]:
    raw = _read_bound_file(path, maximum, what)

    def reject_constant(value: str) -> None:
        raise PatchError(f"{what} contains non-JSON numeric constant {value!r}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PatchError(f"{what} contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PatchError(f"invalid {what}: {exc}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise PatchError(f"{what} must be canonical sorted UTF-8 object JSON")
    return value, raw


def _checked_authorities() -> None:
    for path, size, digest, label in (
        (FORMAT_SPEC, FORMAT_SPEC_SIZE, FORMAT_SPEC_SHA256, "format specification"),
        (RECIPE_SCHEMA_FILE, RECIPE_SCHEMA_FILE_SIZE, RECIPE_SCHEMA_FILE_SHA256, "recipe schema"),
    ):
        raw = _read_bound_file(path, size, f"checked {label}")
        if len(raw) != size or sha256_bytes(raw) != digest:
            raise PatchError(f"checked {label} identity drift")


def load_recipe(path: Path) -> tuple[dict[str, Any], bytes]:
    _checked_authorities()
    recipe, raw = _load_canonical_json(path, MAX_RECIPE_BYTES, "recipe")
    required = set(RECIPE_CONSTANTS) | {"mode", "claim_flags", "assignments"}
    if set(recipe) != required:
        raise PatchError("recipe top-level key set differs from the frozen contract")
    for key, expected in RECIPE_CONSTANTS.items():
        if recipe.get(key) != expected:
            raise PatchError(f"recipe constant-pinned field differs: {key}")
    mode = recipe.get("mode")
    if mode not in ("targeted", "full_built_in_unique"):
        raise PatchError("recipe mode is not admitted")
    flags = recipe.get("claim_flags")
    expected_flags = {
        "all_24_built_in_teams_mutually_unique_requested": mode == "full_built_in_unique",
        "archive_growth_requested": False,
        "emulator_runtime_visibility_proved": False,
        "original_xbox_360_hardware_proved": False,
        "selector_bytes_1_through_7_authoring_requested": False,
    }
    if flags != expected_flags:
        raise PatchError("recipe claim flags differ from the admitted mode boundary")
    assignments = recipe.get("assignments")
    if not isinstance(assignments, list) or not 1 <= len(assignments) <= BUILT_IN_COUNT:
        raise PatchError("recipe must contain 1..24 assignments")
    parsed: list[tuple[int, int, int]] = []
    for ordinal, row in enumerate(assignments):
        if not isinstance(row, dict) or set(row) != {
            "team_index", "expected_retail_asset_index", "replacement_asset_index"
        }:
            raise PatchError(f"assignment {ordinal} has the wrong key set")
        values = tuple(row[key] for key in (
            "team_index", "expected_retail_asset_index", "replacement_asset_index"
        ))
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise PatchError(f"assignment {ordinal} contains a non-integer")
        team, expected, replacement = values
        if not 0 <= team < BUILT_IN_COUNT or not 0 <= expected < CATALOG_COUNT or not 0 <= replacement < CATALOG_COUNT:
            raise PatchError(f"assignment {ordinal} is outside the built-in/catalog bounds")
        if expected != RETAIL_BUILT_IN_ASSETS[team]:
            raise PatchError(f"assignment {ordinal} expected retail asset is wrong")
        parsed.append((team, expected, replacement))
    if [row[0] for row in parsed] != sorted({row[0] for row in parsed}):
        raise PatchError("assignments must have unique, strictly increasing team indices")
    if mode == "full_built_in_unique":
        if len(parsed) != BUILT_IN_COUNT or [row[0] for row in parsed] != list(range(BUILT_IN_COUNT)):
            raise PatchError("full unique mode must assign every built-in team 0..23")
        if sorted(row[2] for row in parsed) != list(range(CATALOG_COUNT)):
            raise PatchError("full unique mode replacements must be a permutation of 0..23")
    return recipe, raw


def _relative_target(data: bytes, field: int, what: str) -> int:
    target = apf_roster.resolve_relative(data, field, what)
    if target is None:
        raise PatchError(f"{what} unexpectedly resolved to null")
    return target


def _aligned_index(target: int, table: apf_roster.RootTable, stride: int, what: str) -> int:
    delta = target - table.offset
    if delta < 0 or delta >= table.count * stride or delta % stride:
        raise PatchError(f"{what} is not an aligned record in root table {table.index}")
    return delta // stride


def derive_selector_layout(decoded: bytes) -> SelectorLayout:
    tables_list, _ = apf_roster.parse_root(decoded)
    tables = tuple(tables_list)
    team_table = tables[TEAM_TABLE]
    config_table = tables[CONFIG_TABLE]
    selector_table = tables[SELECTOR_TABLE]
    if (
        team_table.count != 40 or team_table.stride != TEAM_STRIDE
        or config_table.count != 40 or config_table.stride != CONFIG_STRIDE
        or selector_table.count != 3724 or selector_table.stride != SELECTOR_STRIDE
    ):
        raise PatchError("ROST team/config/selector table contract drift")
    all_targets: set[int] = set()
    jersey_offsets: list[tuple[int, int]] = []
    jersey_indices: list[tuple[int, int]] = []
    assets: list[int] = []
    for team in range(40):
        team_record = team_table.offset + team * TEAM_STRIDE
        config_field = team_record + TEAM_CONFIG_POINTER_OFFSET
        config_target = _relative_target(decoded, config_field, f"team {team} config")
        if _aligned_index(config_target, config_table, CONFIG_STRIDE, f"team {team} config") != team:
            raise PatchError(f"team {team} does not point one-to-one to config {team}")
        selected_offsets: list[int] = []
        selected_indices: list[int] = []
        for bank in range(BANK_COUNT):
            for slot in range(SLOTS_PER_BANK):
                field = config_target + (bank * SLOTS_PER_BANK + slot) * 4
                target = _relative_target(decoded, field, f"team {team} bank {bank} slot {slot}")
                index = _aligned_index(target, selector_table, SELECTOR_STRIDE, f"team {team} bank {bank} slot {slot}")
                if target in all_targets:
                    raise PatchError("two team selector pointers alias one table-17 record")
                all_targets.add(target)
                if slot == JERSEY_SLOT:
                    selected_offsets.append(target)
                    selected_indices.append(index)
        if len(selected_offsets) != BANK_COUNT:
            raise PatchError("jersey selector bank count drift")
        selected_assets = tuple(decoded[offset] for offset in selected_offsets)
        if any(asset >= CATALOG_COUNT for asset in selected_assets) or selected_assets[0] != selected_assets[1]:
            raise PatchError(f"team {team} jersey selectors are outside/either side of the proved catalog")
        jersey_offsets.append((selected_offsets[0], selected_offsets[1]))
        jersey_indices.append((selected_indices[0], selected_indices[1]))
        assets.append(selected_assets[0])
    if len(all_targets) != 40 * BANK_COUNT * SLOTS_PER_BANK:
        raise PatchError("ROST selector pointers are not one-to-one")
    if tuple(assets[:BUILT_IN_COUNT]) != RETAIL_BUILT_IN_ASSETS:
        raise PatchError("retail built-in jersey assignment vector drift")
    return SelectorLayout(tables, tuple(jersey_offsets), tuple(jersey_indices), tuple(assets))


def parse_h7a_tokens(payload: bytes, expected_size: int, shift: int) -> tuple[list[H7AToken], int]:
    if not 1 <= shift <= 15:
        raise PatchError("invalid H7A shift")
    tokens: list[H7AToken] = []
    source = 0
    target = 0
    distance_mask = (1 << shift) - 1
    while target < expected_size:
        if source >= len(payload):
            raise PatchError("retail H7A descriptor stream is truncated")
        descriptor = payload[source]
        source += 1
        for bit in range(8):
            if target >= expected_size:
                break
            start = target
            if descriptor & (1 << bit):
                if source + 2 > len(payload):
                    raise PatchError("retail H7A match is truncated")
                word = int.from_bytes(payload[source : source + 2], "big")
                source += 2
                distance = word & distance_mask
                length = (word >> shift) + 3
                if distance == 0 or distance > target or target + length > expected_size:
                    raise PatchError("retail H7A match violates its decoded bounds")
                tokens.append(H7AToken("match", start, length, None, distance))
                target += length
            else:
                if source >= len(payload):
                    raise PatchError("retail H7A literal is truncated")
                tokens.append(H7AToken("literal", start, 1, payload[source], None))
                source += 1
                target += 1
    if any(payload[source:]):
        raise PatchError("retail H7A has unread nonzero trailing bytes")
    return tokens, source


def _match_run(data: bytes, position: int, end: int, distance: int) -> int:
    length = 0
    while position + length < end and data[position + length] == data[position + length - distance]:
        length += 1
    return length


def encode_preserving_h7a(retail_payload: bytes, retail_decoded: bytes, wanted: bytes, shift: int) -> tuple[bytes, dict[str, int]]:
    if len(retail_decoded) != len(wanted):
        raise PatchError("retail and wanted H7A outputs differ in length")
    if apf_inner.decompress_h7a(retail_payload, len(retail_decoded), shift) != retail_decoded:
        raise PatchError("retail H7A payload does not decode to the pinned ROST")
    original, consumed = parse_h7a_tokens(retail_payload, len(retail_decoded), shift)
    emitted: list[tuple[str, int, int]] = []
    preserved = 0
    split = 0
    max_length = ((1 << (16 - shift)) - 1) + 3
    for token in original:
        start = token.output_start
        end = start + token.length
        first = len(emitted)
        if token.kind == "literal":
            emitted.append(("literal", wanted[start], 1))
        else:
            if token.distance is None:
                raise PatchError("parsed H7A match token is missing its distance")
            cursor = start
            while cursor < end:
                run = _match_run(wanted, cursor, end, token.distance)
                if run >= 3:
                    length = min(run, max_length)
                    emitted.append(("match", token.distance, length))
                    cursor += length
                else:
                    emitted.append(("literal", wanted[cursor], 1))
                    cursor += 1
        local = emitted[first:]
        exact = (
            token.kind == "literal"
            and local == [("literal", int(token.literal), 1)]
        ) or (
            token.kind == "match"
            and local == [("match", int(token.distance), token.length)]
        )
        if exact:
            preserved += 1
        else:
            split += 1

    output = bytearray()
    for group_start in range(0, len(emitted), 8):
        group = emitted[group_start : group_start + 8]
        descriptor = sum((kind == "match") << bit for bit, (kind, _, _) in enumerate(group))
        output.append(descriptor)
        for kind, value, length in group:
            if kind == "literal":
                output.append(value)
            else:
                word = ((length - 3) << shift) | value
                if not 0 < value < (1 << shift) or not 0 <= word <= 0xFFFF:
                    raise PatchError("emitted H7A match is outside its word bounds")
                output.extend(word.to_bytes(2, "big"))
    encoded = bytes(output)
    if apf_inner.decompress_h7a(encoded, len(wanted), shift) != wanted:
        raise PatchError("preservation-aware H7A encode/decode is not exact")
    return encoded, {
        "retail_token_count": len(original),
        "output_token_count": len(emitted),
        "retail_tokens_preserved_semantically": preserved,
        "retail_tokens_split_or_replaced": split,
        "retail_payload_consumed_bytes": consumed,
        "retail_zero_alignment_bytes": len(retail_payload) - consumed,
    }


def _target_entry() -> apf_outer.Entry:
    return apf_outer.Entry(
        table_index=OUTER_INDEX,
        name_id=OUTER_NAME_ID,
        offset_blocks=OUTER_OFFSET // ARCHIVE_ALIGNMENT,
        size_blocks=OUTER_SIZE // ARCHIVE_ALIGNMENT,
        virtual_offset=OUTER_OFFSET,
        size=OUTER_SIZE,
        head_hex="ff3bef94",
        segments=(apf_outer.Segment(0, "0A", OUTER_OFFSET, OUTER_SIZE),),
    )


def _parse_target_from_bound_directory(directory: bytes) -> apf_outer.Entry:
    if len(directory) != ARCHIVE_DIRECTORY_SIZE or sha256_bytes(directory) != ARCHIVE_DIRECTORY_SHA256:
        raise PatchError("APF outer directory identity drift")
    if len(directory) < 24:
        raise PatchError("APF outer directory header is truncated")
    magic, alignment, pack_count, reserved_0c, entry_count, reserved_14 = struct.unpack_from(">6I", directory, 0)
    if (magic, alignment, pack_count, reserved_0c, entry_count, reserved_14) != (
        ARCHIVE_MAGIC, ARCHIVE_ALIGNMENT, len(ARCHIVE_PACKS), 0, ARCHIVE_ENTRY_COUNT, 0
    ):
        raise PatchError("APF outer directory header drift")
    cursor = 24
    for ordinal, (expected_name, expected_blocks) in enumerate(ARCHIVE_PACKS):
        size_blocks, reserved, raw_name = struct.unpack_from(">II8s", directory, cursor)
        cursor += 16
        try:
            name = raw_name.decode("utf-16-be").split("\0", 1)[0]
        except UnicodeDecodeError as exc:
            raise PatchError(f"APF pack {ordinal} name is invalid UTF-16BE") from exc
        if (name, size_blocks, reserved) != (expected_name, expected_blocks, 0):
            raise PatchError(f"APF pack descriptor {ordinal} drift")
    record_offset = cursor + OUTER_INDEX * 12
    name_id, offset_blocks, size_blocks = struct.unpack_from(">3I", directory, record_offset)
    if (name_id, offset_blocks, size_blocks) != (
        OUTER_NAME_ID, OUTER_OFFSET // ARCHIVE_ALIGNMENT, OUTER_SIZE // ARCHIVE_ALIGNMENT
    ):
        raise PatchError("APF ROST outer directory record drift")
    return _target_entry()


def _validate_source(index_path: Path) -> tuple[None, apf_outer.Entry, apf_inner.IFFRecord, bytes, bytes, bytes, SelectorLayout]:
    index_path = _absolute_no_symlink_path(index_path, "source 0A")
    metadata = os.lstat(index_path)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_size != SOURCE_VOLUME_SIZE:
        raise PatchError("source 0A must be the pinned regular non-symlink retail volume")
    descriptor = os.open(index_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        if identity != (metadata.st_dev, metadata.st_ino) or not stat.S_ISREG(opened.st_mode) or opened.st_size != SOURCE_VOLUME_SIZE:
            raise PatchError("source 0A pathname changed during open")
        if _sha256_fd(descriptor) != SOURCE_VOLUME_SHA256:
            raise PatchError("source 0A SHA-256 differs from the pinned retail volume")
        directory = _pread_exact(descriptor, ARCHIVE_DIRECTORY_SIZE, 0)
        entry = _parse_target_from_bound_directory(directory)
        original_entry = _pread_exact(descriptor, OUTER_SIZE, OUTER_OFFSET)
        after = os.lstat(index_path)
        if (after.st_dev, after.st_ino) != identity or os.fstat(descriptor).st_size != SOURCE_VOLUME_SIZE:
            raise PatchError("source 0A pathname or length changed during bound read")
    finally:
        os.close(descriptor)
    memory_reader = BytesReader(original_entry)
    record = apf_inner.parse_iff(memory_reader, entry)
    decoded = apf_inner.decode_block(memory_reader, record, 0, 16 * 1024 * 1024)
    stored = original_entry[record.blocks[0].start_offset : record.blocks[0].start_offset + record.blocks[0].stored_length]
    if sha256_bytes(original_entry) != OUTER_SHA256:
        raise PatchError("retail ROST outer-entry identity drift")
    if record.warnings or record.header_size != IFF_HEADER_SIZE or record.file_length != SOURCE_FILE_LENGTH or record.block_count != 1 or record.file_count != 1:
        raise PatchError("retail ROST IFF envelope drift")
    if len(record.files) != 1 or record.files[0].name != "roster" or record.files[0].type_name != "ROST" or record.files[0].parts != (apf_inner.FilePart(0, 0, DECODED_SIZE),):
        raise PatchError("retail roster/ROST inner ownership drift")
    block = record.blocks[0]
    if not block.is_compressed or block.start_offset != IFF_HEADER_SIZE or block.stored_length != 20 + SOURCE_H7A_PAYLOAD_SIZE or block.wrapper is None:
        raise PatchError("retail ROST H7A block envelope drift")
    if block.wrapper.uncompressed_length != DECODED_SIZE or block.wrapper.compressed_length != len(stored) or block.wrapper.shift != H7A_SHIFT or block.unknown_10 != H7A_UNKNOWN:
        raise PatchError("retail ROST H7A wrapper fields drift")
    if len(decoded) != DECODED_SIZE or sha256_bytes(decoded) != DECODED_SHA256:
        raise PatchError("retail decoded ROST identity drift")
    if record.footer is None or record.footer.offset != SOURCE_FILE_LENGTH or 8 + record.footer.payload_size != FOOTER_TOTAL:
        raise PatchError("retail ROST name footer layout drift")
    footer = original_entry[SOURCE_FILE_LENGTH : SOURCE_FILE_LENGTH + FOOTER_TOTAL]
    tail = original_entry[SOURCE_FILE_LENGTH + FOOTER_TOTAL :]
    if sha256_bytes(footer) != FOOTER_SHA256 or len(tail) != SOURCE_TAIL_SIZE or any(tail):
        raise PatchError("retail ROST footer or fixed zero tail drift")
    layout = derive_selector_layout(decoded)
    return None, entry, record, original_entry, stored, decoded, layout


def _decoded_difference_offsets(before: bytes, after: bytes) -> list[int]:
    if len(before) != len(after):
        raise PatchError("decoded comparison lengths differ")
    return [index for index, (left, right) in enumerate(zip(before, after)) if left != right]


def build_patch(index_path: Path, recipe_path: Path) -> BuildResult:
    recipe, recipe_raw = load_recipe(recipe_path)
    _, entry, record, original_entry, original_stored, decoded, layout = _validate_source(index_path)
    wanted = bytearray(decoded)
    assignment_manifest: list[dict[str, Any]] = []
    authorized_offsets: list[int] = []
    for row in recipe["assignments"]:
        team = int(row["team_index"])
        expected = int(row["expected_retail_asset_index"])
        replacement = int(row["replacement_asset_index"])
        offsets = layout.offsets[team]
        indices = layout.record_indices[team]
        if tuple(decoded[offset] for offset in offsets) != (expected, expected):
            raise PatchError(f"team {team} source jersey selector differs from recipe expectation")
        for offset in offsets:
            wanted[offset] = replacement
            authorized_offsets.append(offset)
        assignment_manifest.append({
            "bank_selector_record_indices": [indices[0], indices[1]],
            "changed": expected != replacement,
            "expected_retail_asset_index": expected,
            "replacement_asset_index": replacement,
            "team_index": team,
            "team_name": BUILT_IN_NAMES[team],
        })
    wanted_bytes = bytes(wanted)
    actual_differences = _decoded_difference_offsets(decoded, wanted_bytes)
    expected_differences = sorted(
        offset for row in recipe["assignments"]
        if row["expected_retail_asset_index"] != row["replacement_asset_index"]
        for offset in layout.offsets[int(row["team_index"])]
    )
    if actual_differences != expected_differences or not set(actual_differences).issubset(authorized_offsets):
        raise PatchError("decoded edit set is not exactly the authorized selector byte set")
    mode = "no_op" if not actual_differences else "changed"

    footer = original_entry[SOURCE_FILE_LENGTH : SOURCE_FILE_LENGTH + FOOTER_TOTAL]
    token_metrics: dict[str, int | bool]
    if mode == "no_op":
        rebuilt = original_entry
        payload = original_stored[20:]
        new_file_length = SOURCE_FILE_LENGTH
        tokens, consumed = parse_h7a_tokens(payload, DECODED_SIZE, H7A_SHIFT)
        token_metrics = {
            "retail_token_count": len(tokens),
            "output_token_count": len(tokens),
            "retail_tokens_preserved_semantically": len(tokens),
            "retail_tokens_split_or_replaced": 0,
            "retail_payload_consumed_bytes": consumed,
            "retail_zero_alignment_bytes": len(payload) - consumed,
            "identity_noop_returned_source_span_verbatim": True,
            "changed_path_recompressed": False,
        }
    else:
        payload, metrics = encode_preserving_h7a(original_stored[20:], decoded, wanted_bytes, H7A_SHIFT)
        if len(payload) > MAX_H7A_PAYLOAD_SIZE:
            raise PatchError(f"rebuilt H7A payload exceeds fixed allocation by {len(payload) - MAX_H7A_PAYLOAD_SIZE} bytes")
        stored = struct.pack(">5I", apf_inner.H7A_MAGIC, DECODED_SIZE, 20 + len(payload), H7A_UNKNOWN, H7A_SHIFT) + payload
        header = bytearray(original_entry[:IFF_HEADER_SIZE])
        struct.pack_into(">8I", header, apf_inner.IFF_HEADER_SIZE, record.blocks[0].name_hash, record.blocks[0].type_hash, record.blocks[0].unknown_08, DECODED_SIZE, H7A_UNKNOWN, IFF_HEADER_SIZE, len(stored), record.blocks[0].indexed)
        new_file_length = IFF_HEADER_SIZE + len(stored)
        struct.pack_into(">I", header, 0x08, new_file_length)
        active = bytes(header) + stored + footer
        if len(active) > OUTER_SIZE:
            raise PatchError(f"rebuilt ROST exceeds its fixed outer allocation by {len(active) - OUTER_SIZE} bytes")
        rebuilt = active + bytes(OUTER_SIZE - len(active))
        memory = BytesReader(rebuilt)
        rebuilt_record = apf_inner.parse_iff(memory, entry)
        rebuilt_decoded = apf_inner.decode_block(memory, rebuilt_record, 0, 16 * 1024 * 1024)
        if rebuilt_record.warnings or rebuilt_decoded != wanted_bytes:
            raise PatchError("rebuilt ROST did not reparse/decode exactly")
        if rebuilt[new_file_length : new_file_length + FOOTER_TOTAL] != footer or any(rebuilt[new_file_length + FOOTER_TOTAL :]):
            raise PatchError("rebuilt ROST footer/tail preservation failed")
        token_metrics = {
            **metrics,
            "identity_noop_returned_source_span_verbatim": False,
            "changed_path_recompressed": True,
        }

    if mode == "no_op" and rebuilt != original_entry:
        raise PatchError("identity recipe did not return the retail outer span verbatim")
    output_decoded = apf_inner.decompress_h7a(payload, DECODED_SIZE, H7A_SHIFT)
    if output_decoded != wanted_bytes:
        raise PatchError("final H7A payload differs from intended decoded ROST")
    full_values = list(layout.retail_assets[:BUILT_IN_COUNT])
    for row in recipe["assignments"]:
        full_values[int(row["team_index"])] = int(row["replacement_asset_index"])
    all_unique = len(set(full_values)) == BUILT_IN_COUNT
    if recipe["mode"] == "full_built_in_unique" and (not all_unique or sorted(full_values) != list(range(CATALOG_COUNT))):
        raise PatchError("full unique recipe did not yield exactly one built-in owner per asset")

    manifest: dict[str, Any] = {
        "assignments": assignment_manifest,
        "claim_flags": {
            "all_24_built_in_teams_mutually_unique_offline": all_unique,
            "all_40_on_disc_team_slots_mutually_unique": False,
            "archive_growth_required": False,
            "emulator_runtime_visibility_proved": False,
            "original_xbox_360_hardware_proved": False,
            "production_gui_exposed": False,
            "selector_byte_0_filename_ownership_proved": True,
            "selector_bytes_1_through_7_semantics_proved": False,
        },
        "compression": {
            "fixed_payload_limit_bytes": MAX_H7A_PAYLOAD_SIZE,
            "headroom_bytes_after": MAX_H7A_PAYLOAD_SIZE - len(payload),
            "payload_sha256_after": sha256_bytes(payload),
            "payload_size_after": len(payload),
            "payload_size_before": SOURCE_H7A_PAYLOAD_SIZE,
            "shift": H7A_SHIFT,
            **token_metrics,
        },
        "mode": mode,
        "preservation": {
            "authorized_decoded_byte_count": len(set(authorized_offsets)),
            "decoded_changed_byte_count": len(actual_differences),
            "decoded_output_sha256": sha256_bytes(wanted_bytes),
            "footer_bit_exact": True,
            "opaque_selector_bytes_1_through_7_bit_exact": True,
            "other_decoded_bytes_bit_exact": True,
            "output_zero_tail_bytes": OUTER_SIZE - new_file_length - FOOTER_TOTAL,
            "rebuilt_iff_reparsed": True,
        },
        "recipe": {
            "assignment_count": len(recipe["assignments"]),
            "mode": recipe["mode"],
            "schema": RECIPE_SCHEMA,
            "sha256": sha256_bytes(recipe_raw),
            "size_bytes": len(recipe_raw),
        },
        "result": {
            "file_length_after": new_file_length,
            "outer_entry_sha256": sha256_bytes(rebuilt),
            "outer_entry_size": len(rebuilt),
        },
        "schema": MANIFEST_SCHEMA,
        "source": {
            "decoded_roster_sha256": DECODED_SHA256,
            "format_spec_sha256": FORMAT_SPEC_SHA256,
            "format_spec_size_bytes": FORMAT_SPEC_SIZE,
            "outer_entry_index": OUTER_INDEX,
            "outer_entry_pack_offset": OUTER_OFFSET,
            "outer_entry_sha256": OUTER_SHA256,
            "retail_0A_sha256": SOURCE_VOLUME_SHA256,
            "retail_0A_size_bytes": SOURCE_VOLUME_SIZE,
        },
    }
    return BuildResult(rebuilt, manifest)


def write_output(index_path: Path, recipe_path: Path, output_volume: Path, manifest_path: Path) -> dict[str, Any]:
    index_path = index_path.expanduser()
    recipe_path = recipe_path.expanduser()
    output_volume = _new_output_path(output_volume, "output volume")
    manifest_path = _new_output_path(manifest_path, "manifest")
    transport._preflight_output_paths(  # type: ignore[attr-defined]
        [index_path, recipe_path, FORMAT_SPEC, RECIPE_SCHEMA_FILE],
        [("output volume", output_volume), ("manifest", manifest_path)],
    )
    source: BoundSourceVolume | None = None
    output_reservation: BoundOutputReservation | None = None
    manifest_reservation: BoundOutputReservation | None = None
    keep_outputs = False
    try:
        result = build_patch(index_path, recipe_path)
        source = _bind_source_volume(index_path)
        output_reservation = _reserve_bound_output(
            output_volume, stat.S_IMODE(source.metadata.st_mode)
        )
        manifest_reservation = _reserve_bound_output(manifest_path, 0o644)
        copied, output_times = _write_bound_copied_volume(
            source, output_reservation, result.entry
        )
        if (
            copied["volume_size"] != SOURCE_VOLUME_SIZE
            or copied["source_volume_sha256_before"] != SOURCE_VOLUME_SHA256
            or copied["source_volume_sha256_after"] != SOURCE_VOLUME_SHA256
        ):
            raise PatchError("copied-volume source identity differs from pinned retail 0A")
        result.manifest["result"]["copied_volume"] = {
            "name": output_volume.name,
            "outside_outer_entry_prefix_sha256": copied["outside_replacement"]["prefix_sha256"],
            "outside_outer_entry_suffix_sha256": copied["outside_replacement"]["suffix_sha256"],
            "sha256": copied["output_volume_sha256"],
            "size_bytes": copied["volume_size"],
        }
        if copied["outside_replacement"]["prefix_sha256"] != SOURCE_PREFIX_SHA256 or copied["outside_replacement"]["suffix_sha256"] != SOURCE_SUFFIX_SHA256:
            raise PatchError("copied 0A complement differs from pinned retail spans")
        if result.manifest["mode"] == "no_op" and copied["output_volume_sha256"] != SOURCE_VOLUME_SHA256:
            raise PatchError("identity recipe did not produce a byte-identical copied 0A")
        document = canonical_json_bytes(result.manifest)
        manifest_times = _commit_bound_output(manifest_reservation, document)
        _assert_bound_source(source)
        _assert_bound_output(
            output_reservation,
            expected_size=SOURCE_VOLUME_SIZE,
            expected_times=output_times,
        )
        _assert_bound_output(
            manifest_reservation,
            expected_size=len(document),
            expected_times=manifest_times,
        )
        if _sha256_fd(manifest_reservation.descriptor) != sha256_bytes(document):
            raise PatchError("manifest content changed before transaction commit")
        keep_outputs = True
        return result.manifest
    finally:
        if manifest_reservation is not None:
            _close_bound_output(manifest_reservation, keep=keep_outputs)
        if output_reservation is not None:
            _close_bound_output(output_reservation, keep=keep_outputs)
        if source is not None:
            try:
                os.close(source.descriptor)
            except OSError:
                pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path, help="user-owned retail APF 0A")
    parser.add_argument("--recipe", required=True, type=Path, help="canonical jersey assignment recipe")
    parser.add_argument("--output-volume", required=True, type=Path, help="new copied 0A to create")
    parser.add_argument("--manifest", required=True, type=Path, help="new canonical manifest to create")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = write_output(args.index, args.recipe, args.output_volume, args.manifest)
        print(
            "APF_JERSEY_SELECTOR_PATCH_PASS "
            f"mode={manifest['mode']} assignments={manifest['recipe']['assignment_count']} "
            f"changed_bytes={manifest['preservation']['decoded_changed_byte_count']} "
            f"payload={manifest['compression']['payload_size_after']} "
            f"headroom={manifest['compression']['headroom_bytes_after']} "
            "runtime=false hardware=false"
        )
        return 0
    except (PatchError, apf_outer.FormatError, apf_inner.FormatError, apf_roster.RosterError, transport.PatchError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
