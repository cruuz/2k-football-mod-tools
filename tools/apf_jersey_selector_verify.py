#!/usr/bin/env python3
"""Independently verify the APF 2K8 ROST jersey-selector writer.

This verifier is deliberately standard-library-only.  It imports neither the
writer nor any project archive, IFF, H7A, or roster implementation.  It binds
all supplied artifacts to stable no-follow descriptors, reparses the retail
``0A`` directory and the fixed ROST IFF, independently decodes and re-encodes
H7A, resolves the ROST one-based pointers, reconstructs the intended selector
edit and the complete canonical writer manifest, and compares the entire
copied volume outside the one fixed outer entry.

The admitted write remains narrow: byte 0 of the two derived jersey selector
records for each assigned built-in team.  Runtime visibility and Xbox 360
hardware acceptance remain false.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any
import zlib


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

VERIFY_SCHEMA = "apf2k8_jersey_selector_verify/v1"
RECIPE_SCHEMA = "apf2k8_jersey_selector_assignment_recipe/v1"
MANIFEST_SCHEMA = "apf2k8_jersey_selector_patch/v1"
OPERATION = "replace_jersey_selector_byte0_in_both_banks"
MAX_RECIPE_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024

SOURCE_VOLUME_SIZE = 1_140_850_688
SOURCE_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
SOURCE_PREFIX_SHA256 = "e771b5533d94ae0f9e5dc6dccf6fd81d13a93894b1e01807e69a10ce8407e550"
SOURCE_SUFFIX_SHA256 = "cebb3cf73db1047d74a08ea4c8eb86ef38ed7c3472b23ee92fa835ad0c56bb0c"

OUTER_MAGIC = 0xAA00B3BF
OUTER_ALIGNMENT = 0x800
OUTER_PACK_COUNT = 4
OUTER_ENTRY_COUNT = 0x607
OUTER_FIXED_HEADER = 0x18
OUTER_PACK_DESCRIPTOR = 0x10
OUTER_ENTRY_RECORD = 0x0C
OUTER_PACKS = (
    ("0A", 557_056),
    ("0B", 524_335),
    ("1A", 557_056),
    ("1B", 252_916),
)
OUTER_INDEX = 1126
OUTER_NAME_ID = 0xBCEFFD46
OUTER_OFFSET = 47_699_968
OUTER_SIZE = 436_224
OUTER_SHA256 = "e98dd07b38caa73ea2ce91eed19bef68896f9b63830a9169af4b7f22d8788cc7"

IFF_MAGIC = 0xFF3BEF94
IFF_HEADER_SIZE = 84
IFF_BLOCK_TABLE_OFFSET = 0x20
IFF_BLOCK_DESCRIPTOR_SIZE = 0x20
IFF_FILE_POINTER_OFFSET = 0x40
IFF_FILE_DESCRIPTOR_OFFSET = 0x44
IFF_FILE_ID = 0x60B9ADF9
IFF_FILE_TYPE = 0xC61649B2
IFF_BLOCK_HASH = 0xBB05A9C1
NAME_FOOTER_MAGIC = 0xAA171516
SOURCE_FILE_LENGTH = 435_329
FOOTER_TOTAL = 96
FOOTER_SHA256 = "70f420d23342ac94ad3ce62f1acfe986f69f6b8c9a4461323b087f80d783a6d7"
SOURCE_TAIL_SIZE = 799

H7A_MAGIC = 0x0E4837C3
H7A_HEADER_SIZE = 20
H7A_SHIFT = 10
H7A_UNKNOWN = 7
SOURCE_H7A_PAYLOAD_SIZE = 435_225
MAX_H7A_PAYLOAD_SIZE = 436_024
DECODED_SIZE = 2_294_304
DECODED_SHA256 = "e959d3067ebcdbeb4f08979fa74d9fa61cf90fd91b90793863e6a3313be7f7ff"

ROOT_PAIR_COUNT = 40
ROOT_SIZE = 0x14C
ROOT_COUNTS = (
    2254, 0, 1, 31, 40, 295, 199, 199, 199, 42, 5957, 69,
    650, 1050, 3200, 266, 266, 3724, 266, 40, 93, 204, 212,
) + (0,) * 17
ROOT_STRIDES: tuple[int | None, ...] = (
    0x14C, None, 0xFA4, 0x24, 0x180, 0x08, 0x18, 0x18,
    0x18, 0xB4, 0xBC, 0x0C, 0x08, 0x08, 0x08, 0x02,
    0x30, 0x08, 0x05, 0x98, 0x98, 0x20, 0x78,
) + (None,) * 17

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


class VerifyError(ValueError):
    """The independently reconstructed output violates the frozen contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class BoundFile:
    """A non-symlink regular file held by one stable read-only descriptor."""

    def __init__(self, path: Path, label: str) -> None:
        supplied_path = path.expanduser()
        if not supplied_path.is_absolute():
            supplied_path = Path.cwd() / supplied_path
        self.supplied_path = Path(os.path.normpath(supplied_path))
        self.label = label
        try:
            supplied = self.supplied_path.lstat()
        except OSError as exc:
            raise VerifyError(f"cannot stat {label}: {self.supplied_path}") from exc
        require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
                f"{label} must be a regular non-symlink file")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            self.fd = os.open(self.supplied_path, flags)
        except OSError as exc:
            raise VerifyError(f"cannot open {label} with no-follow semantics") from exc
        try:
            current = os.fstat(self.fd)
            require(stat.S_ISREG(current.st_mode), f"{label} descriptor is not regular")
            self.identity = (current.st_dev, current.st_ino)
            require(self.identity == (supplied.st_dev, supplied.st_ino),
                    f"{label} pathname changed while opening")
            self.size = current.st_size
            self.times = (current.st_mtime_ns, *change_time_identity(current))
            self.path = self.supplied_path.resolve(strict=True)
            require(self.path == self.supplied_path,
                    f"{label} path contains a symlink component")
            resolved = self.path.stat(follow_symlinks=False)
            require((resolved.st_dev, resolved.st_ino) == self.identity,
                    f"{label} resolved pathname names another inode")
        except Exception:
            os.close(self.fd)
            raise

    def close(self) -> None:
        if getattr(self, "fd", -1) >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> "BoundFile":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def read(self, offset: int, size: int) -> bytes:
        require(0 <= offset <= self.size and 0 <= size <= self.size - offset,
                f"{self.label} read range is outside the file")
        result = bytearray()
        while len(result) < size:
            piece = os.pread(self.fd, size - len(result), offset + len(result))
            require(bool(piece), f"short read from {self.label}")
            result.extend(piece)
        return bytes(result)

    def read_all(self, maximum: int) -> bytes:
        require(0 < self.size <= maximum, f"{self.label} size is outside its bound")
        return self.read(0, self.size)

    def digest(self, offset: int = 0, size: int | None = None) -> str:
        if size is None:
            size = self.size - offset
        require(0 <= offset <= self.size and 0 <= size <= self.size - offset,
                f"{self.label} hash range is outside the file")
        digest = hashlib.sha256()
        cursor = offset
        remaining = size
        while remaining:
            amount = min(8 * 1024 * 1024, remaining)
            digest.update(self.read(cursor, amount))
            cursor += amount
            remaining -= amount
        return digest.hexdigest()

    def assert_stable(self) -> None:
        current = os.fstat(self.fd)
        require(stat.S_ISREG(current.st_mode)
                and (current.st_dev, current.st_ino) == self.identity
                and current.st_size == self.size
                and (current.st_mtime_ns, *change_time_identity(current)) == self.times,
                f"{self.label} descriptor changed during verification")
        try:
            direct = self.supplied_path.lstat()
            resolved = self.path.stat(follow_symlinks=False)
        except OSError as exc:
            raise VerifyError(f"{self.label} pathname disappeared during verification") from exc
        require(stat.S_ISREG(direct.st_mode) and not stat.S_ISLNK(direct.st_mode)
                and (direct.st_dev, direct.st_ino) == self.identity
                and (resolved.st_dev, resolved.st_ino) == self.identity,
                f"{self.label} pathname changed during verification")


class ReportReservation:
    """Exclusively reserve and atomically populate an optional report path."""

    def __init__(self, path: Path, forbidden: list[BoundFile]) -> None:
        supplied = path.expanduser()
        if not supplied.is_absolute():
            supplied = Path.cwd() / supplied
        supplied = Path(os.path.normpath(supplied))
        require(supplied.name not in {"", ".", ".."}, "report filename is invalid")
        try:
            parent = supplied.parent.resolve(strict=True)
        except OSError as exc:
            raise VerifyError("report parent does not exist") from exc
        require(parent.is_dir(), "report parent is not a directory")
        require(parent == supplied.parent,
                "report parent path contains a symlink component")
        self.path = parent / supplied.name
        forbidden_paths = {item.path for item in forbidden} | {
            item.supplied_path for item in forbidden
        }
        require(self.path not in forbidden_paths and self.path.resolve(strict=False) not in forbidden_paths,
                "report path aliases an input or verified output")
        require(not os.path.lexists(self.path), "report path already exists")
        directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                           | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0))
        try:
            self.parent_fd = os.open(parent, directory_flags)
        except OSError as exc:
            raise VerifyError("cannot bind report parent directory") from exc
        parent_info = os.fstat(self.parent_fd)
        self.parent_identity = (parent_info.st_dev, parent_info.st_ino)
        self.parent_path = parent
        flags = (os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
        try:
            self.fd = os.open(self.path.name, flags, 0o644, dir_fd=self.parent_fd)
        except Exception:
            os.close(self.parent_fd)
            raise
        info = os.fstat(self.fd)
        require(stat.S_ISREG(info.st_mode), "report reservation is not regular")
        self.identity = (info.st_dev, info.st_ino)
        self.payload_size: int | None = None
        self.payload_times: tuple[int, int] | None = None
        self.payload_sha256: str | None = None
        self.committed = False

    def _assert_owned(self) -> os.stat_result:
        info = os.fstat(self.fd)
        require(stat.S_ISREG(info.st_mode)
                and (info.st_dev, info.st_ino) == self.identity,
                "report descriptor changed during write")
        if self.payload_size is not None:
            require(info.st_size == self.payload_size,
                    "report size changed after write")
        if self.payload_times is not None:
            require((info.st_mtime_ns, *change_time_identity(info)) == self.payload_times,
                    "report content metadata changed after write")
        parent_info = os.fstat(self.parent_fd)
        path_info = os.stat(self.path.name, dir_fd=self.parent_fd, follow_symlinks=False)
        require((parent_info.st_dev, parent_info.st_ino) == self.parent_identity
                and (path_info.st_dev, path_info.st_ino) == self.identity
                and stat.S_ISREG(path_info.st_mode),
                "report parent or pathname changed during write")
        direct_parent = self.parent_path.stat(follow_symlinks=False)
        resolved_parent = self.parent_path.resolve(strict=True)
        require((direct_parent.st_dev, direct_parent.st_ino) == self.parent_identity
                and stat.S_ISDIR(direct_parent.st_mode)
                and resolved_parent == self.parent_path,
                "report parent pathname changed during write")
        return info

    def commit(self, payload: bytes) -> None:
        cursor = 0
        while cursor < len(payload):
            amount = os.write(self.fd, payload[cursor:])
            require(amount > 0, "short report write")
            cursor += amount
        os.fsync(self.fd)
        info = self._assert_owned()
        require(info.st_size == len(payload), "report size changed during write")
        self.payload_size = len(payload)
        self.payload_times = (info.st_mtime_ns, *change_time_identity(info))
        self.payload_sha256 = sha256_bytes(payload)

    def finalize(self) -> None:
        require(self.payload_size is not None
                and self.payload_times is not None
                and self.payload_sha256 is not None,
                "report was not populated before finalization")
        self._assert_owned()
        digest = hashlib.sha256()
        cursor = 0
        while cursor < self.payload_size:
            piece = os.pread(self.fd, self.payload_size - cursor, cursor)
            require(bool(piece), "short report read-back")
            digest.update(piece)
            cursor += len(piece)
        require(digest.hexdigest() == self.payload_sha256,
                "report content changed before finalization")
        self._assert_owned()
        self.committed = True

    def close(self) -> None:
        try:
            if not self.committed:
                try:
                    current = os.stat(
                        self.path.name, dir_fd=self.parent_fd, follow_symlinks=False
                    )
                    if (current.st_dev, current.st_ino) == self.identity:
                        os.unlink(self.path.name, dir_fd=self.parent_fd)
                except OSError:
                    pass
        finally:
            try:
                os.close(self.fd)
            finally:
                os.close(self.parent_fd)


def _unique_object(what: str):
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise VerifyError(f"{what} contains duplicate key {key!r}")
            result[key] = value
        return result
    return hook


def load_canonical_json(bound: BoundFile, maximum: int, what: str) -> tuple[dict[str, Any], bytes]:
    raw = bound.read_all(maximum)

    def reject_constant(value: str) -> None:
        raise VerifyError(f"{what} contains non-JSON numeric constant {value!r}")

    try:
        value = json.loads(
            raw,
            parse_constant=reject_constant,
            object_pairs_hook=_unique_object(what),
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VerifyError(f"invalid {what}: {exc}") from exc
    require(isinstance(value, dict) and raw == canonical_json_bytes(value),
            f"{what} is not canonical sorted UTF-8 object JSON")
    return value, raw


def validate_recipe(recipe: dict[str, Any]) -> list[tuple[int, int, int]]:
    require(set(recipe) == {
        "assignments", "claim_flags", "game", "mode", "operation", "schema",
        "source_contract",
    }, "recipe top-level key set differs")
    require(recipe.get("schema") == RECIPE_SCHEMA and recipe.get("operation") == OPERATION,
            "recipe schema or operation differs")
    require(recipe.get("game") == {
        "platform": "Xbox 360", "title": "All-Pro Football 2K8",
    }, "recipe game identity differs")
    require(recipe.get("source_contract") == {
        "outer_entry_index": OUTER_INDEX,
        "outer_entry_sha256": OUTER_SHA256,
        "retail_0A_sha256": SOURCE_VOLUME_SHA256,
    }, "recipe source contract differs")
    mode = recipe.get("mode")
    require(mode in {"targeted", "full_built_in_unique"}, "recipe mode is not admitted")
    require(recipe.get("claim_flags") == {
        "all_24_built_in_teams_mutually_unique_requested": mode == "full_built_in_unique",
        "archive_growth_requested": False,
        "emulator_runtime_visibility_proved": False,
        "original_xbox_360_hardware_proved": False,
        "selector_bytes_1_through_7_authoring_requested": False,
    }, "recipe claim flags differ")
    assignments = recipe.get("assignments")
    require(isinstance(assignments, list) and 1 <= len(assignments) <= BUILT_IN_COUNT,
            "recipe assignment count is outside 1..24")
    parsed: list[tuple[int, int, int]] = []
    for ordinal, row in enumerate(assignments):
        require(isinstance(row, dict) and set(row) == {
            "team_index", "expected_retail_asset_index", "replacement_asset_index",
        }, f"assignment {ordinal} key set differs")
        values = tuple(row[key] for key in (
            "team_index", "expected_retail_asset_index", "replacement_asset_index",
        ))
        require(not any(isinstance(value, bool) or not isinstance(value, int)
                        for value in values),
                f"assignment {ordinal} has a non-integer")
        team, expected, replacement = values
        require(0 <= team < BUILT_IN_COUNT and 0 <= expected < CATALOG_COUNT
                and 0 <= replacement < CATALOG_COUNT,
                f"assignment {ordinal} is outside its bounds")
        require(expected == RETAIL_BUILT_IN_ASSETS[team],
                f"assignment {ordinal} retail expectation differs")
        parsed.append((team, expected, replacement))
    require([row[0] for row in parsed] == sorted({row[0] for row in parsed}),
            "recipe assignments are not unique and strictly increasing")
    if mode == "full_built_in_unique":
        require(len(parsed) == BUILT_IN_COUNT
                and [row[0] for row in parsed] == list(range(BUILT_IN_COUNT)),
                "full unique recipe does not assign teams 0..23")
        require(sorted(row[2] for row in parsed) == list(range(CATALOG_COUNT)),
                "full unique replacements are not a permutation of 0..23")
    return parsed


@dataclass(frozen=True)
class OuterEntry:
    name_id: int
    virtual_offset: int
    size: int
    pack_name: str
    pack_offset: int


def _decode_pack_name(raw: bytes) -> str:
    try:
        value = raw.decode("utf-16-be")
    except UnicodeDecodeError as exc:
        raise VerifyError("outer pack name is invalid UTF-16BE") from exc
    name, separator, tail = value.partition("\0")
    require(bool(name) and (not separator or not tail.strip("\0")),
            "outer pack name has invalid termination")
    require(name not in {".", ".."} and Path(name).name == name
            and "/" not in name and "\\" not in name,
            "outer pack name is unsafe")
    return name


def parse_outer_directory(volume: BoundFile) -> OuterEntry:
    fixed = volume.read(0, OUTER_FIXED_HEADER)
    magic, alignment, pack_count, reserved_0c, entry_count, reserved_14 = struct.unpack(
        ">6I", fixed
    )
    require((magic, alignment, pack_count, reserved_0c, entry_count, reserved_14) == (
        OUTER_MAGIC, OUTER_ALIGNMENT, OUTER_PACK_COUNT, 0, OUTER_ENTRY_COUNT, 0,
    ), "APF outer fixed header differs")
    descriptor_bytes = volume.read(
        OUTER_FIXED_HEADER, pack_count * OUTER_PACK_DESCRIPTOR
    )
    packs: list[tuple[str, int, int]] = []
    virtual = 0
    for ordinal in range(pack_count):
        size_blocks, reserved, raw_name = struct.unpack_from(
            ">II8s", descriptor_bytes, ordinal * OUTER_PACK_DESCRIPTOR
        )
        name = _decode_pack_name(raw_name)
        require(reserved == 0 and (name, size_blocks) == OUTER_PACKS[ordinal],
                f"outer pack descriptor {ordinal} differs")
        packs.append((name, virtual, size_blocks * alignment))
        virtual += size_blocks * alignment
    require(packs[0][0] == "0A" and packs[0][2] == SOURCE_VOLUME_SIZE,
            "outer first-volume allocation differs")
    table_start = OUTER_FIXED_HEADER + pack_count * OUTER_PACK_DESCRIPTOR
    table_size = entry_count * OUTER_ENTRY_RECORD
    require(table_start + table_size <= volume.size,
            "outer entry table exceeds 0A")
    table = volume.read(table_start, table_size)
    target: OuterEntry | None = None
    pack_starts = [item[1] for item in packs]
    total = packs[-1][1] + packs[-1][2]
    for index in range(entry_count):
        name_id, offset_blocks, size_blocks = struct.unpack_from(
            ">III", table, index * OUTER_ENTRY_RECORD
        )
        offset = offset_blocks * alignment
        size = size_blocks * alignment
        require(size > 0 and 0 <= offset <= total and size <= total - offset,
                f"outer entry {index} range is invalid")
        pack_index = max(
            candidate for candidate, start in enumerate(pack_starts) if start <= offset
        )
        pack_name, pack_start, pack_size = packs[pack_index]
        require(offset + size <= pack_start + pack_size or index != OUTER_INDEX,
                "target outer entry crosses a volume boundary")
        if index == OUTER_INDEX:
            target = OuterEntry(name_id, offset, size, pack_name, offset - pack_start)
    require(target == OuterEntry(
        OUTER_NAME_ID, OUTER_OFFSET, OUTER_SIZE, "0A", OUTER_OFFSET,
    ), "outer entry 1126 routing/name/allocation differs")
    require(target is not None, "outer target entry was not derived")
    return target


@dataclass(frozen=True)
class ParsedIFF:
    file_length: int
    stored: bytes
    payload: bytes
    footer: bytes
    tail: bytes


def _decode_utf16le_z(data: bytes, offset: int, what: str) -> str:
    require(0 <= offset < len(data), f"{what} offset is outside footer")
    cursor = offset
    while cursor + 1 < len(data) and data[cursor:cursor + 2] != b"\0\0":
        cursor += 2
    require(cursor + 1 < len(data), f"{what} is unterminated")
    try:
        return data[offset:cursor].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise VerifyError(f"{what} is invalid UTF-16LE") from exc


def _parse_footer(footer: bytes) -> None:
    require(len(footer) == FOOTER_TOTAL, "IFF footer has the wrong total size")
    magic = struct.unpack_from(">I", footer, 0)[0]
    payload_size = struct.unpack_from("<I", footer, 4)[0]
    require(magic == NAME_FOOTER_MAGIC and payload_size + 8 == len(footer),
            "IFF footer header differs")
    payload = footer[8:]
    require(len(payload) >= 8 and struct.unpack_from("<I", payload, 0)[0] == 1,
            "IFF footer name count differs")
    table = 4 + struct.unpack_from("<I", payload, 4)[0] - 1
    require(0 <= table <= len(payload) - 4, "IFF footer pointer table is out of bounds")
    record = table + struct.unpack_from("<I", payload, table)[0] - 1
    require(0 <= record <= len(payload) - 8, "IFF footer record is out of bounds")
    name_offset = record + struct.unpack_from("<I", payload, record)[0] - 1
    type_field = record + 4
    type_offset = type_field + struct.unpack_from("<I", payload, type_field)[0] - 1
    name = _decode_utf16le_z(payload, name_offset, "IFF file name")
    type_name = _decode_utf16le_z(payload, type_offset, "IFF file type")
    require((name, type_name) == ("roster", "ROST"),
            "IFF footer does not name roster/ROST")
    require(zlib.crc32(name.encode("ascii")) & 0xFFFFFFFF == IFF_FILE_ID
            and zlib.crc32(type_name.encode("ascii")) & 0xFFFFFFFF == IFF_FILE_TYPE,
            "IFF footer CRC ownership differs")


def parse_iff(entry: bytes) -> ParsedIFF:
    require(len(entry) == OUTER_SIZE, "ROST outer entry has the wrong allocation")
    fields = struct.unpack_from(">8I", entry, 0)
    magic, header_size, file_length, zero, block_count, block_pointer, file_count, file_pointer = fields
    require(magic == IFF_MAGIC and header_size == IFF_HEADER_SIZE and zero == 0
            and block_count == 1 and file_count == 1,
            "ROST IFF fixed header differs")
    require(0 <= header_size <= file_length <= len(entry),
            "ROST IFF file length is outside its allocation")
    require(0x14 + block_pointer - 1 == IFF_BLOCK_TABLE_OFFSET
            and 0x1C + file_pointer - 1 == IFF_FILE_POINTER_OFFSET,
            "ROST IFF relative header pointers differ")
    block = struct.unpack_from(">8I", entry, IFF_BLOCK_TABLE_OFFSET)
    (name_hash, type_hash, unknown_08, uncompressed, unknown_10,
     start, compressed_length, indexed) = block
    require((name_hash, type_hash, unknown_08, uncompressed, unknown_10,
             start, indexed) == (
        IFF_BLOCK_HASH, IFF_BLOCK_HASH, 0x20, DECODED_SIZE, H7A_UNKNOWN,
        IFF_HEADER_SIZE, 0,
    ), "ROST block descriptor differs")
    require(compressed_length >= H7A_HEADER_SIZE
            and start + compressed_length == file_length,
            "ROST block stored extent differs")
    pointer_value = struct.unpack_from(">I", entry, IFF_FILE_POINTER_OFFSET)[0]
    require(IFF_FILE_POINTER_OFFSET + pointer_value - 1 == IFF_FILE_DESCRIPTOR_OFFSET,
            "ROST inner-file pointer differs")
    file_id, type_hash, offset_count, block_offset = struct.unpack_from(
        ">4I", entry, IFF_FILE_DESCRIPTOR_OFFSET
    )
    require((file_id, type_hash, offset_count, block_offset) == (
        IFF_FILE_ID, IFF_FILE_TYPE, 1, 0,
    ), "ROST inner-file descriptor differs")
    require(IFF_FILE_DESCRIPTOR_OFFSET + 16 == IFF_HEADER_SIZE,
            "ROST packed header has unexpected padding")
    stored = entry[start:start + compressed_length]
    h7a = struct.unpack_from(">5I", stored, 0)
    require(h7a == (
        H7A_MAGIC, DECODED_SIZE, compressed_length, H7A_UNKNOWN, H7A_SHIFT,
    ), "ROST H7A wrapper differs")
    footer_header = entry[file_length:file_length + 8]
    require(len(footer_header) == 8, "ROST footer header is truncated")
    footer_payload_size = struct.unpack_from("<I", footer_header, 4)[0]
    footer_end = file_length + 8 + footer_payload_size
    require(footer_end <= len(entry), "ROST footer exceeds fixed allocation")
    footer = entry[file_length:footer_end]
    _parse_footer(footer)
    tail = entry[footer_end:]
    require(not any(tail), "ROST unused fixed-allocation tail is nonzero")
    return ParsedIFF(file_length, stored, stored[H7A_HEADER_SIZE:], footer, tail)


@dataclass(frozen=True)
class H7AToken:
    kind: str
    output_start: int
    length: int
    literal: int | None
    distance: int | None


def decode_h7a(payload: bytes) -> tuple[bytes, tuple[H7AToken, ...], int]:
    output = bytearray()
    tokens: list[H7AToken] = []
    source = 0
    distance_mask = (1 << H7A_SHIFT) - 1
    length_mask = (1 << (16 - H7A_SHIFT)) - 1
    while len(output) < DECODED_SIZE:
        require(source < len(payload), "H7A descriptor stream is truncated")
        descriptor = payload[source]
        source += 1
        for bit in range(8):
            if len(output) >= DECODED_SIZE:
                break
            start = len(output)
            if descriptor & (1 << bit):
                require(source + 2 <= len(payload), "H7A match word is truncated")
                word = int.from_bytes(payload[source:source + 2], "big")
                source += 2
                distance = word & distance_mask
                length = ((word >> H7A_SHIFT) & length_mask) + 3
                require(distance > 0 and distance <= len(output)
                        and len(output) + length <= DECODED_SIZE,
                        "H7A match violates output/lookback bounds")
                tokens.append(H7AToken("match", start, length, None, distance))
                for _ in range(length):
                    output.append(output[-distance])
            else:
                require(source < len(payload), "H7A literal is truncated")
                literal = payload[source]
                source += 1
                tokens.append(H7AToken("literal", start, 1, literal, None))
                output.append(literal)
    require(not any(payload[source:]), "H7A has unread nonzero bytes")
    return bytes(output), tuple(tokens), source


def _match_run(data: bytes, position: int, end: int, distance: int) -> int:
    length = 0
    while (position + length < end
           and data[position + length] == data[position + length - distance]):
        length += 1
    return length


def encode_preserving_h7a(
    retail_tokens: tuple[H7AToken, ...], retail_zero_alignment_bytes: int,
    wanted: bytes,
) -> tuple[bytes, dict[str, int]]:
    emitted: list[tuple[str, int, int]] = []
    preserved = 0
    split = 0
    maximum_length = ((1 << (16 - H7A_SHIFT)) - 1) + 3
    for token in retail_tokens:
        start = token.output_start
        end = start + token.length
        first = len(emitted)
        if token.kind == "literal":
            emitted.append(("literal", wanted[start], 1))
        else:
            require(token.distance is not None,
                    "parsed H7A match token is missing its distance")
            cursor = start
            while cursor < end:
                run = _match_run(wanted, cursor, end, token.distance)
                if run >= 3:
                    length = min(run, maximum_length)
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
        group = emitted[group_start:group_start + 8]
        descriptor = sum((kind == "match") << bit
                         for bit, (kind, _, _) in enumerate(group))
        output.append(descriptor)
        for kind, value, length in group:
            if kind == "literal":
                output.append(value)
            else:
                word = ((length - 3) << H7A_SHIFT) | value
                require(0 < value < (1 << H7A_SHIFT) and 0 <= word <= 0xFFFF,
                        "reconstructed H7A match is outside word bounds")
                output.extend(word.to_bytes(2, "big"))
    encoded = bytes(output)
    decoded, output_tokens, _ = decode_h7a(encoded)
    require(decoded == wanted, "independent H7A reconstruction does not round-trip")
    return encoded, {
        "output_token_count": len(output_tokens),
        "retail_tokens_preserved_semantically": preserved,
        "retail_tokens_split_or_replaced": split,
        "retail_zero_alignment_bytes": retail_zero_alignment_bytes,
    }


@dataclass(frozen=True)
class RootTable:
    index: int
    count: int
    offset: int
    stride: int | None


def _u32be(data: bytes, offset: int, what: str) -> int:
    require(0 <= offset <= len(data) - 4, f"{what} field is out of bounds")
    return struct.unpack_from(">I", data, offset)[0]


def resolve_relative(data: bytes, field: int, what: str) -> int:
    stored = _u32be(data, field, what)
    signed = stored if stored < 0x80000000 else stored - 0x1_0000_0000
    target = field + signed - 1
    require(0 <= target < len(data), f"{what} relative pointer is out of bounds")
    return target


def parse_root(data: bytes) -> tuple[RootTable, ...]:
    require(len(data) == DECODED_SIZE, "decoded ROST size differs")
    targets: list[int] = []
    for index in range(ROOT_PAIR_COUNT):
        pair = index * 8
        require(_u32be(data, pair, f"root table {index} count") == ROOT_COUNTS[index],
                f"root table {index} count differs")
        targets.append(resolve_relative(data, pair + 4, f"root table {index} pointer"))
    pointer_140 = resolve_relative(data, 0x140, "root pointer 0x140")
    pointer_144 = resolve_relative(data, 0x144, "root pointer 0x144")
    string_pool = resolve_relative(data, 0x148, "root string-pool pointer")
    tables: list[RootTable] = []
    for index in range(ROOT_PAIR_COUNT):
        start = targets[index]
        end = targets[index + 1] if index + 1 < ROOT_PAIR_COUNT else pointer_140
        stride = ROOT_STRIDES[index]
        storage = 0 if stride is None else ROOT_COUNTS[index] * stride
        padding = 2 if index == 18 else 0
        require(end >= start and end - start == storage + padding,
                f"root table {index} bounds/stride differ")
        require(not padding or data[end - padding:end] == bytes(padding),
                "root table 18 alignment padding differs")
        tables.append(RootTable(index, ROOT_COUNTS[index], start, stride))
    require(targets[0] == ROOT_SIZE, "first ROST table does not follow the root")
    require(pointer_140 == pointer_144 == targets[23],
            "ROST end-of-array root pointers differ")
    require(string_pool >= pointer_144 and not any(data[pointer_144:string_pool]),
            "ROST reserved UTF-16 workspace differs")
    return tuple(tables)


@dataclass(frozen=True)
class SelectorLayout:
    offsets: tuple[tuple[int, int], ...]
    record_indices: tuple[tuple[int, int], ...]
    assets: tuple[int, ...]


def _aligned_record(target: int, table: RootTable, stride: int, what: str) -> int:
    delta = target - table.offset
    require(delta >= 0 and delta % stride == 0 and delta // stride < table.count,
            f"{what} does not target an aligned root-table record")
    return delta // stride


def derive_selector_layout(decoded: bytes) -> SelectorLayout:
    tables = parse_root(decoded)
    team_table = tables[TEAM_TABLE]
    config_table = tables[CONFIG_TABLE]
    selector_table = tables[SELECTOR_TABLE]
    require((team_table.count, team_table.stride) == (40, TEAM_STRIDE)
            and (config_table.count, config_table.stride) == (40, CONFIG_STRIDE)
            and (selector_table.count, selector_table.stride) == (3724, SELECTOR_STRIDE),
            "team/config/selector table contract differs")
    all_targets: set[int] = set()
    jersey_offsets: list[tuple[int, int]] = []
    jersey_indices: list[tuple[int, int]] = []
    assets: list[int] = []
    for team in range(40):
        team_record = team_table.offset + team * TEAM_STRIDE
        config = resolve_relative(
            decoded, team_record + TEAM_CONFIG_POINTER_OFFSET, f"team {team} config"
        )
        require(_aligned_record(config, config_table, CONFIG_STRIDE,
                                f"team {team} config") == team,
                f"team {team} config is not one-to-one")
        selected_offsets: list[int] = []
        selected_indices: list[int] = []
        for bank in range(BANK_COUNT):
            for slot in range(SLOTS_PER_BANK):
                field = config + (bank * SLOTS_PER_BANK + slot) * 4
                target = resolve_relative(
                    decoded, field, f"team {team} bank {bank} slot {slot}"
                )
                index = _aligned_record(
                    target, selector_table, SELECTOR_STRIDE,
                    f"team {team} bank {bank} slot {slot}",
                )
                require(target not in all_targets, "two selector pointers alias one record")
                all_targets.add(target)
                if slot == JERSEY_SLOT:
                    selected_offsets.append(target)
                    selected_indices.append(index)
        require(len(selected_offsets) == BANK_COUNT,
                "derived jersey selector bank count differs")
        selected_assets = tuple(decoded[offset] for offset in selected_offsets)
        require(len(selected_assets) == 2 and selected_assets[0] == selected_assets[1]
                and selected_assets[0] < CATALOG_COUNT,
                f"team {team} jersey selector assets differ or exceed catalog")
        jersey_offsets.append((selected_offsets[0], selected_offsets[1]))
        jersey_indices.append((selected_indices[0], selected_indices[1]))
        assets.append(selected_assets[0])
    require(len(all_targets) == 40 * BANK_COUNT * SLOTS_PER_BANK,
            "selector pointer graph is not one-to-one")
    return SelectorLayout(tuple(jersey_offsets), tuple(jersey_indices), tuple(assets))


def build_expected(
    source_entry: bytes,
    source_iff: ParsedIFF,
    source_decoded: bytes,
    source_tokens: tuple[H7AToken, ...],
    source_consumed: int,
    source_layout: SelectorLayout,
    recipe: dict[str, Any],
    recipe_raw: bytes,
    assignments: list[tuple[int, int, int]],
    output_name: str,
    output_volume_sha256: str,
) -> tuple[bytes, bytes, dict[str, Any], list[int]]:
    require(source_layout.assets[:BUILT_IN_COUNT] == RETAIL_BUILT_IN_ASSETS,
            "retail built-in jersey assignment vector differs")
    wanted = bytearray(source_decoded)
    authorized_offsets: list[int] = []
    assignment_manifest: list[dict[str, Any]] = []
    for team, expected, replacement in assignments:
        offsets = source_layout.offsets[team]
        indices = source_layout.record_indices[team]
        require(tuple(source_decoded[offset] for offset in offsets) == (expected, expected),
                f"team {team} selectors disagree with recipe expectation")
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
    differences = [offset for offset, (before, after) in
                   enumerate(zip(source_decoded, wanted_bytes)) if before != after]
    expected_differences = sorted(
        offset
        for team, expected, replacement in assignments
        if expected != replacement
        for offset in source_layout.offsets[team]
    )
    require(differences == expected_differences
            and set(differences).issubset(authorized_offsets),
            "intended decoded differences escape authorized selector bytes")
    mode = "no_op" if not differences else "changed"
    if mode == "no_op":
        payload = source_iff.payload
        rebuilt = source_entry
        new_file_length = SOURCE_FILE_LENGTH
        token_metrics: dict[str, int | bool] = {
            "retail_token_count": len(source_tokens),
            "output_token_count": len(source_tokens),
            "retail_tokens_preserved_semantically": len(source_tokens),
            "retail_tokens_split_or_replaced": 0,
            "retail_payload_consumed_bytes": source_consumed,
            "retail_zero_alignment_bytes": len(source_iff.payload) - source_consumed,
            "identity_noop_returned_source_span_verbatim": True,
            "changed_path_recompressed": False,
        }
    else:
        payload, metrics = encode_preserving_h7a(
            source_tokens, len(source_iff.payload) - source_consumed, wanted_bytes
        )
        require(len(payload) <= MAX_H7A_PAYLOAD_SIZE,
                "reconstructed H7A payload exceeds fixed allocation")
        stored = struct.pack(
            ">5I", H7A_MAGIC, DECODED_SIZE, H7A_HEADER_SIZE + len(payload),
            H7A_UNKNOWN, H7A_SHIFT,
        ) + payload
        header = bytearray(source_entry[:IFF_HEADER_SIZE])
        struct.pack_into(
            ">8I", header, IFF_BLOCK_TABLE_OFFSET,
            IFF_BLOCK_HASH, IFF_BLOCK_HASH, 0x20, DECODED_SIZE, H7A_UNKNOWN,
            IFF_HEADER_SIZE, len(stored), 0,
        )
        new_file_length = IFF_HEADER_SIZE + len(stored)
        struct.pack_into(">I", header, 0x08, new_file_length)
        active = bytes(header) + stored + source_iff.footer
        require(len(active) <= OUTER_SIZE, "reconstructed ROST exceeds fixed allocation")
        rebuilt = active + bytes(OUTER_SIZE - len(active))
        token_metrics = {
            "retail_token_count": len(source_tokens),
            "output_token_count": metrics["output_token_count"],
            "retail_tokens_preserved_semantically": metrics[
                "retail_tokens_preserved_semantically"
            ],
            "retail_tokens_split_or_replaced": metrics[
                "retail_tokens_split_or_replaced"
            ],
            "retail_payload_consumed_bytes": source_consumed,
            "retail_zero_alignment_bytes": len(source_iff.payload) - source_consumed,
            "identity_noop_returned_source_span_verbatim": False,
            "changed_path_recompressed": True,
        }
    output_decoded, _, _ = decode_h7a(payload)
    require(output_decoded == wanted_bytes,
            "reconstructed final H7A payload differs from intended ROST")
    full_values = list(source_layout.assets[:BUILT_IN_COUNT])
    for team, _expected, replacement in assignments:
        full_values[team] = replacement
    all_unique = len(set(full_values)) == BUILT_IN_COUNT
    if recipe["mode"] == "full_built_in_unique":
        require(all_unique and sorted(full_values) == list(range(CATALOG_COUNT)),
                "full unique recipe reconstruction is not one-to-one")
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
            "decoded_changed_byte_count": len(differences),
            "decoded_output_sha256": sha256_bytes(wanted_bytes),
            "footer_bit_exact": True,
            "opaque_selector_bytes_1_through_7_bit_exact": True,
            "other_decoded_bytes_bit_exact": True,
            "output_zero_tail_bytes": OUTER_SIZE - new_file_length - FOOTER_TOTAL,
            "rebuilt_iff_reparsed": True,
        },
        "recipe": {
            "assignment_count": len(assignments),
            "mode": recipe["mode"],
            "schema": RECIPE_SCHEMA,
            "sha256": sha256_bytes(recipe_raw),
            "size_bytes": len(recipe_raw),
        },
        "result": {
            "copied_volume": {
                "name": output_name,
                "outside_outer_entry_prefix_sha256": SOURCE_PREFIX_SHA256,
                "outside_outer_entry_suffix_sha256": SOURCE_SUFFIX_SHA256,
                "sha256": output_volume_sha256,
                "size_bytes": SOURCE_VOLUME_SIZE,
            },
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
    return rebuilt, wanted_bytes, manifest, differences


def compare_complete_volumes(source: BoundFile, output: BoundFile) -> dict[str, Any]:
    require(source.size == output.size == SOURCE_VOLUME_SIZE,
            "source/output 0A sizes differ from retail")
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    source_prefix = hashlib.sha256()
    output_prefix = hashlib.sha256()
    source_suffix = hashlib.sha256()
    output_suffix = hashlib.sha256()
    cursor = 0
    changed_inside = 0
    outer_end = OUTER_OFFSET + OUTER_SIZE
    while cursor < source.size:
        amount = min(8 * 1024 * 1024, source.size - cursor)
        before = source.read(cursor, amount)
        after = output.read(cursor, amount)
        source_hash.update(before)
        output_hash.update(after)
        end = cursor + amount
        prefix_end = min(end, OUTER_OFFSET)
        if cursor < prefix_end:
            count = prefix_end - cursor
            source_prefix.update(before[:count])
            output_prefix.update(after[:count])
            require(before[:count] == after[:count],
                    "copied 0A differs before the ROST outer entry")
        inside_start = max(cursor, OUTER_OFFSET)
        inside_end = min(end, outer_end)
        if inside_start < inside_end:
            first = inside_start - cursor
            last = inside_end - cursor
            changed_inside += sum(left != right for left, right in
                                  zip(before[first:last], after[first:last]))
        suffix_start = max(cursor, outer_end)
        if suffix_start < end:
            first = suffix_start - cursor
            source_suffix.update(before[first:])
            output_suffix.update(after[first:])
            require(before[first:] == after[first:],
                    "copied 0A differs after the ROST outer entry")
        cursor = end
    facts = {
        "source_sha256": source_hash.hexdigest(),
        "output_sha256": output_hash.hexdigest(),
        "source_prefix_sha256": source_prefix.hexdigest(),
        "output_prefix_sha256": output_prefix.hexdigest(),
        "source_suffix_sha256": source_suffix.hexdigest(),
        "output_suffix_sha256": output_suffix.hexdigest(),
        "changed_bytes_inside_outer_entry": changed_inside,
    }
    require(facts["source_sha256"] == SOURCE_VOLUME_SHA256,
            "retail source 0A SHA-256 differs")
    require(facts["source_prefix_sha256"] == facts["output_prefix_sha256"]
            == SOURCE_PREFIX_SHA256,
            "copied 0A prefix hash differs")
    require(facts["source_suffix_sha256"] == facts["output_suffix_sha256"]
            == SOURCE_SUFFIX_SHA256,
            "copied 0A suffix hash differs")
    return facts


def verify(
    source_path: Path,
    recipe_path: Path,
    output_path: Path,
    manifest_path: Path,
    report_path: Path | None = None,
) -> dict[str, Any]:
    with ExitStack() as stack:
        format_spec = stack.enter_context(BoundFile(FORMAT_SPEC, "format specification"))
        recipe_schema = stack.enter_context(BoundFile(RECIPE_SCHEMA_FILE, "recipe schema"))
        source = stack.enter_context(BoundFile(source_path, "retail source 0A"))
        recipe_file = stack.enter_context(BoundFile(recipe_path, "assignment recipe"))
        output = stack.enter_context(BoundFile(output_path, "copied output 0A"))
        manifest_file = stack.enter_context(BoundFile(manifest_path, "writer manifest"))
        bound = [format_spec, recipe_schema, source, recipe_file, output, manifest_file]
        require(len({item.identity for item in bound}) == len(bound),
                "an input/output/authority pair aliases the same inode")
        require(len({item.path for item in bound}) == len(bound),
                "an input/output/authority pair aliases the same path")
        require(format_spec.size == FORMAT_SPEC_SIZE
                and format_spec.digest() == FORMAT_SPEC_SHA256,
                "format specification identity differs")
        require(recipe_schema.size == RECIPE_SCHEMA_FILE_SIZE
                and recipe_schema.digest() == RECIPE_SCHEMA_FILE_SHA256,
                "recipe schema identity differs")
        require(source.size == SOURCE_VOLUME_SIZE and source.supplied_path.name == "0A",
                "source index is not the pinned 0A shape")
        recipe, recipe_raw = load_canonical_json(
            recipe_file, MAX_RECIPE_BYTES, "assignment recipe"
        )
        assignments = validate_recipe(recipe)
        supplied_manifest, _manifest_raw = load_canonical_json(
            manifest_file, MAX_MANIFEST_BYTES, "writer manifest"
        )

        source_outer = parse_outer_directory(source)
        output_outer = parse_outer_directory(output)
        require(source_outer == output_outer,
                "copied output 0A outer directory routing differs")
        source_entry = source.read(source_outer.pack_offset, source_outer.size)
        output_entry = output.read(output_outer.pack_offset, output_outer.size)
        require(sha256_bytes(source_entry) == OUTER_SHA256,
                "retail ROST outer-entry SHA-256 differs")
        source_iff = parse_iff(source_entry)
        require(source_iff.file_length == SOURCE_FILE_LENGTH
                and len(source_iff.payload) == SOURCE_H7A_PAYLOAD_SIZE
                and sha256_bytes(source_iff.footer) == FOOTER_SHA256
                and len(source_iff.tail) == SOURCE_TAIL_SIZE,
                "retail ROST IFF/footer/tail identity differs")
        source_decoded, source_tokens, source_consumed = decode_h7a(source_iff.payload)
        require(sha256_bytes(source_decoded) == DECODED_SHA256,
                "retail decoded ROST SHA-256 differs")
        source_layout = derive_selector_layout(source_decoded)
        require(source_layout.assets[:BUILT_IN_COUNT] == RETAIL_BUILT_IN_ASSETS,
                "retail built-in jersey vector differs")

        volume_facts = compare_complete_volumes(source, output)
        expected_entry, wanted_decoded, expected_manifest, decoded_differences = build_expected(
            source_entry,
            source_iff,
            source_decoded,
            source_tokens,
            source_consumed,
            source_layout,
            recipe,
            recipe_raw,
            assignments,
            output.supplied_path.name,
            str(volume_facts["output_sha256"]),
        )
        require(output_entry == expected_entry,
                "output ROST outer entry differs from independent reconstruction")
        output_iff = parse_iff(output_entry)
        output_decoded, _output_tokens, _output_consumed = decode_h7a(output_iff.payload)
        require(output_decoded == wanted_decoded,
                "output H7A decode differs from intended ROST")
        output_layout = derive_selector_layout(output_decoded)
        require(output_layout.offsets == source_layout.offsets
                and output_layout.record_indices == source_layout.record_indices,
                "output selector pointer graph differs")
        expected_assets = list(source_layout.assets)
        for team, _expected, replacement in assignments:
            expected_assets[team] = replacement
        require(output_layout.assets == tuple(expected_assets),
                "output jersey selector assets differ from recipe")
        require(supplied_manifest == expected_manifest,
                "writer manifest differs from complete independent reconstruction")
        if expected_manifest["mode"] == "no_op":
            require(volume_facts["output_sha256"] == SOURCE_VOLUME_SHA256,
                    "identity output volume is not bit-exact retail")
        require(volume_facts["changed_bytes_inside_outer_entry"] == sum(
            left != right for left, right in zip(source_entry, expected_entry)
        ), "full-volume entry difference count differs")

        report = {
            "assignment_count": len(assignments),
            "claims": {
                "all_bytes_outside_outer_entry_bit_exact": True,
                "complete_manifest_reconstructed": True,
                "emulator_runtime_visibility_proved": False,
                "original_xbox_360_hardware_proved": False,
                "production_gui_exposed": False,
                "selector_byte_0_only": True,
                "selector_bytes_1_through_7_bit_exact": True,
            },
            "decoded_changed_byte_count": len(decoded_differences),
            "decoded_output_sha256": sha256_bytes(wanted_decoded),
            "manifest_sha256": manifest_file.digest(),
            "mode": expected_manifest["mode"],
            "outer_entry_sha256": sha256_bytes(output_entry),
            "output_volume_sha256": volume_facts["output_sha256"],
            "payload_size_after": len(output_iff.payload),
            "recipe_sha256": sha256_bytes(recipe_raw),
            "schema": VERIFY_SCHEMA,
        }

        for item in bound:
            item.assert_stable()
        if report_path is not None:
            reservation = ReportReservation(report_path, bound)
            try:
                reservation.commit(canonical_json_bytes(report))
                for item in bound:
                    item.assert_stable()
                reservation.finalize()
            finally:
                reservation.close()
        return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source-index", required=True, type=Path,
                        help="pinned user-owned retail APF 0A")
    result.add_argument("--recipe", required=True, type=Path,
                        help="canonical jersey-selector assignment recipe")
    result.add_argument("--output-volume", required=True, type=Path,
                        help="copied 0A produced by the writer")
    result.add_argument("--manifest", required=True, type=Path,
                        help="canonical writer manifest")
    result.add_argument("--report", type=Path,
                        help="optional new canonical verifier report path")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = verify(
            args.source_index, args.recipe, args.output_volume, args.manifest, args.report
        )
    except (OSError, OverflowError, struct.error, VerifyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "APF_JERSEY_SELECTOR_VERIFY_PASS "
        f"mode={report['mode']} assignments={report['assignment_count']} "
        f"changed_bytes={report['decoded_changed_byte_count']} "
        f"payload={report['payload_size_after']} "
        "outside=true manifest=true runtime=false hardware=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
