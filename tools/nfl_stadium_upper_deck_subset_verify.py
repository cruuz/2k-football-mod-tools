#!/usr/bin/env python3
"""Independently verify the NFL 2K5 ``upper_deck`` source-subset writer.

This verifier is deliberately standard-library-only.  It imports neither the
writer nor any project archive, scene, or compression implementation.  It
independently parses the pinned archive mapping, VC-LZ stream, one-based SCNE
pointers, shape/stream/submesh records, native DRAW_ARRAYS command, complete
copied-volume diff, and manifest.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
from typing import Any


VERIFY_SCHEMA = "nfl2k5_upper_deck_source_subset_verify/v1"
MANIFEST_SCHEMA = "nfl2k5_upper_deck_source_subset_patch/v1"
RECIPE_SCHEMA = "nfl2k5_upper_deck_source_subset_recipe/v1"
IDENTITY_REQUEST_SCHEMA = "nfl2k5_upper_deck_identity_noop_request/v1"
BOUNDARY_SCHEMA = "nfl2k5_upper_deck_changed_count_boundary/v1"
CATALOG_SCHEMA = "nfl2k5_stadium_static_target_catalog/v1"
TARGET_ID = "nfl2k5/stadium/o3280/c5/s1"

BOUNDARY_SIZE = 25_285
BOUNDARY_SHA256 = "54e6d20dcf9c525a5248d94b4f45516425f0e69702df31dfd93fc351efd43eab"
CATALOG_SIZE = 858_600
CATALOG_SHA256 = "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa"
RECIPE_SCHEMA_SIZE = 2_209
RECIPE_SCHEMA_SHA256 = "4fac01c6cffe03481b456899ec2b2f3cd25f74954d5db94ccb3b8351f841ca4b"
MAX_RECIPE_BYTES = 16 * 1024
MAX_MANIFEST_BYTES = 256 * 1024

INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
PACK_SIZE = 634_941_440
PACK_SHA256 = "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a"
ENTRY_INDEX = 3280
ENTRY_ID = 0xE4D6B0BC
ENTRY_SIZE = 1_390_448
ENTRY_OFFSET_BLOCKS = 1_747_476
ENTRY_VIRTUAL_OFFSET = 3_578_830_848
ENTRY_PACK_OFFSET = 0x07E47000
ENTRY_SHA256 = "3b2a505e2f0cab433fbe74c5211e4b370112e4e70a2ad45f1fa39a59af9a92cd"

CHUNK_START = 0x07EA5A40
CHUNK_SPAN = 908_912
CHUNK_END = CHUNK_START + CHUNK_SPAN
CHUNK_STORED = 908_880
SYSTEM_BYTES = 577_792
VIDEO_BYTES = 947_072
DECODED_SIZE = 1_524_864
RETAIL_CONSUMED = 908_864
SOURCE_SPAN_SHA256 = "0cd1977a6097851f9366d935098bdd9e97144f3ffce0f8690593c2623fbbd73a"
SOURCE_WRAPPER_SHA256 = "d4049cd35f3588259072ff9d05952c6bd830f6c1cd6181fc1d72b25b8cdc41ae"
SOURCE_DECODED_SHA256 = "229db9f309bf69eaa28901ae6e2e15b26a279b3f1f37abed01e36041c5e5ead8"
RETAIL_STREAM_SHA256 = "beb71504d82a7634d73bf6603fb96d8d0ba33beb4fd0eaa870efd4007a8d3af8"
TAIL_SHA256 = "cb57e42b9b8d9e1cba31e18c38dbc3347c8caa1361fcf7fe9cfad5b9f138fae4"
OUTSIDE_SHA256 = "8ef9522d0b4e4c5dfd9bb65c2e18d6ddf4c506ce5513f341701958666edc2bc6"
RETAIL_SCRATCH = 16
OBSERVED_SCRATCH_MAX = 3_120

SHAPE_OFFSET = 30_464
VERTEX_COUNT_FIELD = 30_540
TRANSFORM_OFFSET = 69_632
SUBMESH_OFFSET = 69_744
PUSH_OFFSET = 69_872
PUSH_SIZE = 24
DRAW_PARAMETER_OFFSET = 69_884
DRAW_COUNT_BYTE_OFFSET = 69_887
STREAM0_OFFSET = 69_920
STREAM0_STRIDE = 12
STREAM0_END = 70_064
STREAM1_OFFSET = 70_080
STREAM1_STRIDE = 10
STREAM1_END = 70_200
SOURCE_VERTEX_COUNT = 12


class UpperDeckSubsetVerifyError(ValueError):
    """The independent reconstruction found a contract violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise UpperDeckSubsetVerifyError(message)


class BoundFile:
    """One non-symlink regular file held by a stable read-only descriptor."""

    def __init__(self, path: Path, label: str) -> None:
        self.path = path.expanduser().absolute()
        self.label = label
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            self.fd = os.open(self.path, flags)
        except (FileNotFoundError, OSError) as exc:
            raise UpperDeckSubsetVerifyError(
                f"{label} cannot be opened as a no-follow file: {self.path}"
            ) from exc
        self._capture()

    @classmethod
    def from_dir(cls, directory_fd: int, directory_path: Path,
                 name: str, label: str) -> "BoundFile":
        require("/" not in name and name not in {"", ".", ".."},
                f"{label} child name is invalid")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(name, flags, dir_fd=directory_fd)
        except (FileNotFoundError, OSError) as exc:
            raise UpperDeckSubsetVerifyError(
                f"{label} cannot be opened relative to the pinned directory"
            ) from exc
        instance = cls.__new__(cls)
        instance.path = (directory_path / name).absolute()
        instance.label = label
        instance.fd = fd
        instance._capture()
        return instance

    def _capture(self) -> None:
        info = os.fstat(self.fd)
        require(stat.S_ISREG(info.st_mode), f"{self.label} is not a regular file")
        self.identity = (info.st_dev, info.st_ino)
        self.size = info.st_size

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
                f"{self.label} read extent is invalid")
        output = bytearray()
        while len(output) < size:
            block = os.pread(self.fd, size - len(output), offset + len(output))
            require(bool(block), f"{self.label} read is short")
            output.extend(block)
        return bytes(output)

    def read_all(self, maximum: int) -> bytes:
        require(0 < self.size <= maximum, f"{self.label} size is outside its limit")
        return self.read(0, self.size)

    def digest(self, *, skip: tuple[int, int] | None = None) -> str:
        digest = hashlib.sha256()
        cursor = 0
        spans = [(0, self.size)]
        if skip is not None:
            start, end = skip
            require(0 <= start <= end <= self.size,
                    f"{self.label} skipped hash extent is invalid")
            spans = [(0, start), (end, self.size)]
        for start, end in spans:
            cursor = start
            while cursor < end:
                size = min(8 * 1024 * 1024, end - cursor)
                digest.update(self.read(cursor, size))
                cursor += size
        return digest.hexdigest()

    def assert_stable(self) -> None:
        info = os.fstat(self.fd)
        require(stat.S_ISREG(info.st_mode)
                and (info.st_dev, info.st_ino) == self.identity
                and info.st_size == self.size,
                f"{self.label} descriptor identity or size changed")
        try:
            path_info = self.path.lstat()
        except FileNotFoundError as exc:
            raise UpperDeckSubsetVerifyError(
                f"{self.label} pathname disappeared during verification"
            ) from exc
        require(stat.S_ISREG(path_info.st_mode) and not stat.S_ISLNK(path_info.st_mode)
                and (path_info.st_dev, path_info.st_ino) == self.identity,
                f"{self.label} pathname no longer names the pinned inode")


class BoundDirectory:
    """One output directory held open while its two children are verified."""

    def __init__(self, path: Path, label: str) -> None:
        self.path = path.expanduser().absolute()
        self.label = label
        flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                 | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0))
        try:
            self.fd = os.open(self.path, flags)
        except (FileNotFoundError, OSError) as exc:
            raise UpperDeckSubsetVerifyError(
                f"{label} cannot be opened as a no-follow directory: {self.path}"
            ) from exc
        info = os.fstat(self.fd)
        require(stat.S_ISDIR(info.st_mode), f"{label} is not a directory")
        self.identity = (info.st_dev, info.st_ino)

    def close(self) -> None:
        if getattr(self, "fd", -1) >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> "BoundDirectory":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def names(self) -> list[str]:
        return sorted(os.listdir(self.fd))

    def open_file(self, name: str, label: str) -> BoundFile:
        return BoundFile.from_dir(self.fd, self.path, name, label)

    def assert_stable(self, children: dict[str, BoundFile], *, exact: bool = True) -> None:
        info = os.fstat(self.fd)
        require(stat.S_ISDIR(info.st_mode)
                and (info.st_dev, info.st_ino) == self.identity,
                f"{self.label} descriptor identity changed")
        try:
            path_info = self.path.lstat()
        except FileNotFoundError as exc:
            raise UpperDeckSubsetVerifyError(
                f"{self.label} pathname disappeared during verification"
            ) from exc
        require(stat.S_ISDIR(path_info.st_mode) and not stat.S_ISLNK(path_info.st_mode)
                and (path_info.st_dev, path_info.st_ino) == self.identity,
                f"{self.label} pathname no longer names the pinned directory")
        if exact:
            require(self.names() == sorted(children),
                    f"{self.label} gained or lost an artifact during verification")
        for name, child in children.items():
            info = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            require(stat.S_ISREG(info.st_mode)
                    and (info.st_dev, info.st_ino) == child.identity
                    and info.st_size == child.size,
                    f"{self.label}/{name} no longer names the pinned file")


def _absolute(path: Path) -> Path:
    """Return a normalized absolute path without following its final component."""
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def preflight_report_path(output_dir: Path, report_path: Path | None) -> Path | None:
    """Reject a report that could become part of the verified output artifact."""
    if report_path is None:
        return None
    output = _absolute(output_dir)
    report = _absolute(report_path)
    require(not _is_within(report, output),
            "report path must be outside the verified output directory")
    require(report.name not in {"", ".", ".."}, "report filename is invalid")
    return report


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def regular(path: Path, label: str) -> Path:
    path = path.expanduser()
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise UpperDeckSubsetVerifyError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def require_distinct_files(left: Path, right: Path) -> None:
    a, b = left.stat(), right.stat()
    require(left != right and (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino),
            "output volume path or inode aliases the retail source")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path, label: str, maximum: int) -> tuple[dict[str, Any], bytes]:
    path = regular(path, label)
    size = path.stat().st_size
    require(0 < size <= maximum, f"{label} size is outside its limit")
    payload = path.read_bytes()
    require(len(payload) == size, f"{label} changed while reading")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                UpperDeckSubsetVerifyError(
                    f"non-finite JSON constant {token} is forbidden"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpperDeckSubsetVerifyError(f"{label} is not UTF-8 JSON: {exc}") from exc
    require(isinstance(value, dict) and payload == canonical_json(value),
            f"{label} must be canonical sorted JSON")
    return value, payload


def _parse_json_payload(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                UpperDeckSubsetVerifyError(
                    f"non-finite JSON constant {token} is forbidden"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpperDeckSubsetVerifyError(f"{label} is not UTF-8 JSON: {exc}") from exc
    require(isinstance(value, dict) and payload == canonical_json(value),
            f"{label} must be canonical sorted JSON")
    return value


def _load_json_bound(bound: BoundFile, label: str,
                     maximum: int) -> tuple[dict[str, Any], bytes]:
    payload = bound.read_all(maximum)
    return _parse_json_payload(payload, label), payload


def _load_json_source(source: Path | BoundFile, label: str,
                      maximum: int) -> tuple[dict[str, Any], bytes]:
    if isinstance(source, BoundFile):
        return _load_json_bound(source, label, maximum)
    return _load_json(source, label, maximum)


def load_authority(boundary_path: Path | BoundFile,
                   catalog_path: Path | BoundFile,
                   recipe_schema_path: Path | BoundFile) -> dict[str, Any]:
    boundary, boundary_payload = _load_json_source(
        boundary_path, "changed-count boundary", BOUNDARY_SIZE
    )
    require(len(boundary_payload) == BOUNDARY_SIZE
            and sha256(boundary_payload) == BOUNDARY_SHA256
            and boundary.get("schema") == BOUNDARY_SCHEMA,
            "changed-count boundary differs from the pinned authority")
    catalog, catalog_payload = _load_json_source(
        catalog_path, "static-target catalog", CATALOG_SIZE
    )
    require(len(catalog_payload) == CATALOG_SIZE
            and sha256(catalog_payload) == CATALOG_SHA256
            and catalog.get("schema") == CATALOG_SCHEMA,
            "static-target catalog differs from the pinned authority")
    recipe_schema, schema_payload = _load_json_source(
        recipe_schema_path, "source-subset recipe schema", RECIPE_SCHEMA_SIZE
    )
    require(len(schema_payload) == RECIPE_SCHEMA_SIZE
            and sha256(schema_payload) == RECIPE_SCHEMA_SHA256
            and recipe_schema.get("$id") == RECIPE_SCHEMA,
            "source-subset recipe schema differs from the pinned authority")

    flags = boundary.get("claim_flags", {})
    require(flags.get("target_structure_closed_for_prefix_shrink_probe") is True
            and flags.get("source_subset_record_copy_algorithm_specified") is True,
            "changed-count structural authority is not proved")
    for false_flag in (
        "changed_count_archive_writer_implemented",
        "independent_changed_count_verifier_implemented",
        "arbitrary_external_vertex_authoring_proved",
        "bounds_or_culling_serializer_proved",
        "runtime_visibility_proved",
        "original_xbox_hardware_proved",
        "production_ready",
    ):
        require(flags.get(false_flag) is False,
                f"frozen boundary overclaims {false_flag}")
    target = boundary.get("target_selection", {})
    topology = boundary.get("topology_contract", {})
    records = boundary.get("vertex_record_contract", {})
    require(target.get("target_id") == TARGET_ID
            and target.get("shape_index") == 1
            and target.get("shape_name") == "upper_deck",
            "changed-count target identity drifted")
    require(topology.get("changed_vertex_counts") == [4, 8]
            and topology.get("no_op_vertex_count") == SOURCE_VERTEX_COUNT
            and topology.get("primary_word_count") == 6
            and topology.get("secondary_word_count") == 0,
            "changed-count topology contract drifted")
    streams = records.get("streams")
    require(isinstance(streams, list) and len(streams) == 2,
            "changed-count stream contract drifted")
    expected_streams = [
        (0, STREAM0_STRIDE, STREAM0_OFFSET, STREAM0_END,
         "95164ce59e125ac1775003846a1eb780c63f001c65f2b3da8d2aebd20fbe67f7"),
        (1, STREAM1_STRIDE, STREAM1_OFFSET, STREAM1_END,
         "5ad69b6eff91ed58f1882d08f9f69b299d0ea32d53cf729a6c0fb8a2a7c7cabe"),
    ]
    for stream, expected in zip(streams, expected_streams):
        span = stream.get("source_physical_span", {})
        require((stream.get("stream_index"), stream.get("stride_bytes"),
                 span.get("offset"), span.get("end_offset"), span.get("sha256"))
                == expected,
                "changed-count physical stream contract drifted")
    targets = [row for row in catalog.get("targets", [])
               if isinstance(row, dict) and row.get("target_id") == TARGET_ID]
    require(len(targets) == 1
            and targets[0].get("shape", {}).get("vertex_count") == SOURCE_VERTEX_COUNT,
            "pinned catalog upper_deck row drifted")
    return {
        "boundary": boundary,
        "catalog": catalog,
        "recipe_schema": recipe_schema,
    }


def _request_ids_sha256(ids: list[int]) -> str:
    return sha256(canonical_json(ids))


def identity_request() -> dict[str, Any]:
    ids = list(range(SOURCE_VERTEX_COUNT))
    value = {
        "operation": "validated_identity_noop",
        "schema": IDENTITY_REQUEST_SCHEMA,
        "source_decoded_sha256": SOURCE_DECODED_SHA256,
        "source_vertex_ids": ids,
        "target_id": TARGET_ID,
        "vertex_count": SOURCE_VERTEX_COUNT,
    }
    payload = canonical_json(value)
    return {
        "kind": "identity_noop_flag",
        "schema": IDENTITY_REQUEST_SCHEMA,
        "sha256": sha256(payload),
        "new_count": SOURCE_VERTEX_COUNT,
        "ids": ids,
        "ids_sha256": _request_ids_sha256(ids),
    }


def load_recipe(path: Path | BoundFile) -> dict[str, Any]:
    value, payload = _load_json_source(
        path, "source-subset recipe", MAX_RECIPE_BYTES
    )
    require(set(value) == {
        "new_vertex_count", "schema", "source_decoded_sha256",
        "source_vertex_ids", "target_id",
    }, "source-subset recipe fields differ from v1")
    require(value.get("schema") == RECIPE_SCHEMA
            and value.get("target_id") == TARGET_ID
            and value.get("source_decoded_sha256") == SOURCE_DECODED_SHA256,
            "source-subset recipe authority differs")
    count = value.get("new_vertex_count")
    ids = value.get("source_vertex_ids")
    require(type(count) is int and count in (4, 8),
            "changed vertex count must be exactly four or eight")
    require(isinstance(ids, list) and len(ids) == count,
            "source vertex ID count differs from new vertex count")
    require(all(type(item) is int and 0 <= item < SOURCE_VERTEX_COUNT for item in ids),
            "source vertex IDs must be integers in [0,12)")
    require(len(set(ids)) == len(ids), "source vertex IDs must be distinct")
    return {
        "kind": "changed_source_subset_recipe",
        "schema": RECIPE_SCHEMA,
        "sha256": sha256(payload),
        "new_count": count,
        "ids": ids,
        "ids_sha256": _request_ids_sha256(ids),
    }


def _read(path: Path, offset: int, size: int) -> bytes:
    with path.open("rb") as stream:
        stream.seek(offset)
        data = stream.read(size)
    require(len(data) == size, f"short read at 0x{offset:x}")
    return data


def _read_source(source: Path | BoundFile, offset: int, size: int) -> bytes:
    if isinstance(source, BoundFile):
        return source.read(offset, size)
    return _read(source, offset, size)


def parse_index(path: Path | BoundFile) -> dict[str, int]:
    if isinstance(path, BoundFile):
        name = path.path.name
        size = path.size
        digest = path.digest()
        source: Path | BoundFile = path
    else:
        resolved = regular(path, "NFL archive index")
        name = resolved.name
        size = resolved.stat().st_size
        digest = sha256_file(resolved)
        source = resolved
    require(name == "0" and size == INDEX_SIZE and digest == INDEX_SHA256,
            "source index identity changed")
    head = _read_source(source, 0, 0x9C)
    entry_count, reserved, pack_count = struct.unpack_from("<III", head)
    require((entry_count, reserved, pack_count) == (4323, 0, 16),
            "index header changed")
    blocks = struct.unpack_from("<36I", head, 0x0C)
    require(blocks[9] * 0x800 == PACK_SIZE, "volume 9 extent changed")
    name_id, size, offset_blocks = struct.unpack(
        "<III", _read_source(source, 0x9C + ENTRY_INDEX * 12, 12)
    )
    require((name_id, size, offset_blocks)
            == (ENTRY_ID, ENTRY_SIZE, ENTRY_OFFSET_BLOCKS),
            "outer directory entry changed")
    virtual_start = sum(blocks[:9]) * 0x800
    require(offset_blocks * 0x800 == ENTRY_VIRTUAL_OFFSET
            and ENTRY_VIRTUAL_OFFSET - virtual_start == ENTRY_PACK_OFFSET,
            "outer physical mapping changed")
    return {
        "pack_offset": ENTRY_VIRTUAL_OFFSET - virtual_start,
        "entry_size": ENTRY_SIZE,
        "entry_id": name_id,
    }


def walk_outer_resources(outer: bytes) -> list[dict[str, Any]]:
    """Derive all inner resource offsets from their fixed 32-byte wrappers."""
    expected_offsets = [
        0x000000, 0x01C7F0, 0x021BF0, 0x04CB10, 0x04CB70, 0x05EA40,
        0x13C8B0, 0x13CAF0, 0x140000, 0x143510, 0x1489E0,
    ]
    resources: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(outer):
        require(cursor + 32 <= len(outer),
                "outer resource wrapper is truncated")
        magic, stored, system, video, marker, scratch, reserved0, reserved1 = (
            struct.unpack_from("<4s7I", outer, cursor)
        )
        require(magic in {b"SCNE", b"TXTR", b"Fldd"}
                and reserved0 == reserved1 == 0,
                "outer resource wrapper signature changed")
        if magic == b"SCNE":
            require(marker == 0xFEEDBEEF,
                    "SCNE resource wrapper marker changed")
        elif magic == b"TXTR":
            require(marker in {0, 0xFEEDBEEF},
                    "TXTR resource wrapper marker changed")
        else:
            require((system, video, marker, scratch) == (0, 0, 0, 0),
                    "Fldd resource wrapper fields changed")
        end = cursor + 32 + stored
        require(stored > 0 and end <= len(outer),
                "outer resource stored span escapes its entry")
        resources.append({
            "index": len(resources),
            "offset": cursor,
            "end": end,
            "stored": stored,
            "system": system,
            "video": video,
            "scratch": scratch,
        })
        cursor = end
    require(cursor == len(outer), "outer resource chain does not end at entry extent")
    require([row["offset"] for row in resources] == expected_offsets,
            "outer resource wrapper-chain offsets changed")
    require(len(resources) == 11,
            "outer resource wrapper-chain count changed")
    target = resources[5]
    require(target["offset"] == 0x5EA40
            and target["end"] - target["offset"] == CHUNK_SPAN,
            "derived upper_deck resource span changed")
    return resources


def decompress_vc_lz(body: bytes, expected: int) -> tuple[bytes, dict[str, int]]:
    require(len(body) >= 10, "VC-LZ body too short")
    declared, tag = struct.unpack_from("<II", body)
    bits = body[8]
    require((declared, tag, bits) == (expected, 1, 12), "VC-LZ prefix changed")
    output = bytearray(expected)
    source = 10
    flags = body[9]
    flag_bit = 1
    target = 0
    literals = matches = 0
    while target < expected:
        if flags & flag_bit:
            require(source + 2 <= len(body), "truncated VC-LZ match")
            word = struct.unpack_from("<H", body, source)[0]
            source += 2
            distance = word & 4095
            length = (word >> 12) + 3
            require(0 < distance <= target and target + length <= expected,
                    "invalid VC-LZ match")
            for index in range(length - 1, -1, -1):
                output[target + index] = output[target - distance + index]
            target += length
            matches += 1
        else:
            require(source < len(body), "truncated VC-LZ literal")
            output[target] = body[source]
            source += 1
            target += 1
            literals += 1
        flag_bit = (flag_bit << 1) & 0xFF
        if flag_bit == 0 and target < expected:
            require(source < len(body), "missing VC-LZ flag")
            flags = body[source]
            source += 1
            flag_bit = 1
    return bytes(output), {
        "consumed": source,
        "literals": literals,
        "matches": matches,
    }


def minimum_overlap_scratch(body: bytes, stored: int, expected: int) -> int:
    require(len(body) >= 10 and struct.unpack_from("<I", body)[0] == expected
            and body[8] == 12, "VC-LZ scratch prefix changed")
    source, flags, bit, target, maximum = 10, body[9], 1, 0, 0
    while target < expected:
        if flags & bit:
            require(source + 2 <= len(body), "truncated scratch match")
            word = struct.unpack_from("<H", body, source)[0]
            source += 2
            distance = word & 4095
            length = (word >> 12) + 3
            require(0 < distance <= target, "invalid scratch match")
        else:
            require(source < len(body), "truncated scratch literal")
            source += 1
            length = 1
        target += length
        require(target <= expected, "scratch token overrun")
        if target < expected:
            maximum = max(maximum, stored - expected + target - source)
        bit = (bit << 1) & 0xFF
        if bit == 0 and target < expected:
            require(source < len(body), "missing scratch flag")
            flags = body[source]
            source += 1
            bit = 1
    return maximum


def _s32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _resolve(data: bytes, field: int, label: str) -> int | None:
    require(0 <= field <= SYSTEM_BYTES - 4,
            f"{label} pointer field outside system buffer")
    relative = _s32(data, field)
    if relative == 0:
        return None
    target = field - 1 + relative
    require(0 <= target < SYSTEM_BYTES, f"{label} pointer outside system buffer")
    return target


def _utf16z(data: bytes, offset: int | None, label: str) -> str:
    require(offset is not None and offset % 2 == 0, f"{label} pointer unavailable")
    start = int(offset)
    cursor = start
    while cursor + 2 <= SYSTEM_BYTES and data[cursor:cursor + 2] != b"\0\0":
        cursor += 2
    require(cursor + 2 <= SYSTEM_BYTES, f"{label} string is unterminated")
    try:
        return data[start:cursor].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise UpperDeckSubsetVerifyError(f"{label} is invalid UTF-16LE") from exc


def _decode_header(header: int) -> tuple[int, int, int]:
    require((header & 0xE0030003) in (0, 0x40000000),
            "NV2A command header signature changed")
    return (header >> 29) & 7, (header >> 18) & 0x7FF, header & 0x1FFC


def inspect_target(decoded: bytes, new_count: int) -> dict[str, Any]:
    require(decoded[0x0C:0x10] == b"SCNE", "decoded object is not SCNE")
    require(_utf16z(decoded, _resolve(decoded, 0x10, "scene name"), "scene name")
            == "stadium", "scene name changed")
    descriptor = _resolve(decoded, 0x14, "scene descriptor")
    require(descriptor == 0x100 and _u32(decoded, descriptor + 0x2C) == 76,
            "stadium descriptor or shape count changed")
    shape_table = _resolve(decoded, descriptor + 0x30, "shape table")
    require(shape_table is not None and shape_table + 0x100 == SHAPE_OFFSET,
            "upper_deck shape-table position changed")
    require(_utf16z(decoded, _resolve(decoded, SHAPE_OFFSET + 0x40, "shape name"),
                    "shape name") == "upper_deck"
            and _u32(decoded, SHAPE_OFFSET + 0x44) == 2,
            "upper_deck shape identity changed")
    counts = struct.unpack_from("<5H", decoded, SHAPE_OFFSET + 0x4C)
    require(counts == (new_count, 0, 1, 0, 1),
            "upper_deck shape count tuple changed outside vertex count")
    declarations = struct.unpack_from("<16I", decoded, SHAPE_OFFSET + 0x84)
    strides = struct.unpack_from("<8H", decoded, SHAPE_OFFSET + 0xC4)
    require(declarations == (
        0x00000032, 0x00080115, 0x00000002, 0x00000140,
        0x00000002, 0x00000002, 0x00040121, 0x00000002,
        0x00000002, 0x00000002, 0x00000002, 0x00000002,
        0x00000002, 0x00000002, 0x00000002, 0x00000002,
    ) and strides == (12, 10, 0, 0, 0, 0, 0, 0),
            "upper_deck declarations or strides changed")
    require(_resolve(decoded, SHAPE_OFFSET + 0x60, "inactive blend pointer")
            == SUBMESH_OFFSET
            and _resolve(decoded, SHAPE_OFFSET + 0x64, "transform pointer")
            == TRANSFORM_OFFSET
            and _resolve(decoded, SHAPE_OFFSET + 0x70, "submesh pointer")
            == SUBMESH_OFFSET
            and _resolve(decoded, SHAPE_OFFSET + 0x74, "morph pointer") is None
            and _resolve(decoded, SHAPE_OFFSET + 0x78, "aux pointer 78") is None
            and _resolve(decoded, SHAPE_OFFSET + 0x7C, "aux pointer 7c") is None
            and _resolve(decoded, SHAPE_OFFSET + 0xD4, "stream 0") == STREAM0_OFFSET
            and _resolve(decoded, SHAPE_OFFSET + 0xD8, "stream 1") == STREAM1_OFFSET,
            "upper_deck nested pointers changed")
    material, auxiliary = struct.unpack_from("<HH", decoded, SUBMESH_OFFSET)
    primary, secondary = struct.unpack_from("<HH", decoded, SUBMESH_OFFSET + 0x7C)
    require((material, auxiliary, primary, secondary) == (1, 1, 6, 0)
            and _resolve(decoded, SUBMESH_OFFSET + 0x78, "push pointer") == PUSH_OFFSET,
            "upper_deck submesh/material/command allocation changed")
    words = struct.unpack_from("<6I", decoded, PUSH_OFFSET)
    first = _decode_header(words[0])
    draw = _decode_header(words[2])
    last = _decode_header(words[4])
    start = words[3] & 0x00FFFFFF
    draw_count = ((words[3] >> 24) & 0xFF) + 1
    require(first == (0, 1, 0x17FC) and words[1] == 8
            and draw == (0, 1, 0x1810) and start == 0 and draw_count == new_count
            and last == (0, 1, 0x17FC) and words[5] == 0,
            "upper_deck six-word QUADS/DRAW_ARRAYS grammar changed")
    selectors = [
        struct.unpack_from("<h", decoded, STREAM1_OFFSET + index * STREAM1_STRIDE + 8)[0]
        for index in range(new_count)
    ]
    require(selectors == [0] * new_count,
            "selected upper_deck records no longer use the sole transform")
    positions = [
        struct.unpack_from("<3f", decoded, STREAM0_OFFSET + index * STREAM0_STRIDE)
        for index in range(new_count)
    ]
    require(all(math.isfinite(component) for xyz in positions for component in xyz),
            "selected upper_deck positions are non-finite")
    degenerate = 0
    triangles = 0
    for base in range(0, new_count, 4):
        for ia, ib, ic in ((base, base + 1, base + 2),
                           (base, base + 2, base + 3)):
            a, b, c = positions[ia], positions[ib], positions[ic]
            ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            cross = (
                ab[1] * ac[2] - ab[2] * ac[1],
                ab[2] * ac[0] - ab[0] * ac[2],
                ab[0] * ac[1] - ab[1] * ac[0],
            )
            triangles += 1
            if cross == (0.0, 0.0, 0.0):
                degenerate += 1
    return {
        "vertex_count": new_count,
        "draw_vertex_count": draw_count,
        "maximum_vertex_index": new_count - 1,
        "quad_count": new_count // 4,
        "triangle_count": triangles,
        "nondegenerate_triangle_count": triangles - degenerate,
        "degenerate_triangle_count": degenerate,
        "material_index": material,
        "auxiliary_index": auxiliary,
        "primary_word_count": primary,
        "secondary_word_count": secondary,
        "selectors_all_zero": True,
    }


def _reconstruct(source: bytes, request: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    count = int(request["new_count"])
    ids = list(request["ids"])
    if count == SOURCE_VERTEX_COUNT:
        require(ids == list(range(SOURCE_VERTEX_COUNT)),
                "identity request source order changed")
        return source, {
            "stream_prefix_changed_byte_counts": [0, 0],
            "authorized_changed_offsets": [],
        }
    edited = bytearray(source)
    stream_changes: list[int] = []
    for offset, end, stride in (
        (STREAM0_OFFSET, STREAM0_END, STREAM0_STRIDE),
        (STREAM1_OFFSET, STREAM1_END, STREAM1_STRIDE),
    ):
        physical = source[offset:end]
        require(len(physical) == SOURCE_VERTEX_COUNT * stride,
                "source stream physical extent changed")
        rebuilt = bytearray(physical)
        for destination, source_id in enumerate(ids):
            left = source_id * stride
            rebuilt[destination * stride:(destination + 1) * stride] = (
                physical[left:left + stride]
            )
        logical_end = count * stride
        require(rebuilt[logical_end:] == physical[logical_end:],
                "independent stream reconstruction changed the physical tail")
        edited[offset:end] = rebuilt
        stream_changes.append(sum(a != b for a, b in zip(physical[:logical_end],
                                                          rebuilt[:logical_end])))
    struct.pack_into("<H", edited, VERTEX_COUNT_FIELD, count)
    source_parameter = struct.unpack_from("<I", source, DRAW_PARAMETER_OFFSET)[0]
    require((source_parameter & 0x00FFFFFF) == 0
            and ((source_parameter >> 24) & 0xFF) + 1 == SOURCE_VERTEX_COUNT,
            "source DRAW_ARRAYS parameter changed")
    struct.pack_into("<I", edited, DRAW_PARAMETER_OFFSET, (count - 1) << 24)
    allowed = {VERTEX_COUNT_FIELD, DRAW_COUNT_BYTE_OFFSET}
    allowed.update(range(STREAM0_OFFSET, STREAM0_OFFSET + count * STREAM0_STRIDE))
    allowed.update(range(STREAM1_OFFSET, STREAM1_OFFSET + count * STREAM1_STRIDE))
    changed = [index for index, (left, right) in enumerate(zip(source, edited))
               if left != right]
    require(all(index in allowed for index in changed),
            "independent intended edit escaped the authorized spans")
    require(VERTEX_COUNT_FIELD in changed and DRAW_COUNT_BYTE_OFFSET in changed,
            "changed-count request did not change both coupled count bytes")
    return bytes(edited), {
        "stream_prefix_changed_byte_counts": stream_changes,
        "authorized_changed_offsets": changed,
    }


def compare_packs(source: Path | BoundFile,
                  output: Path | BoundFile) -> dict[str, Any]:
    source_size = source.size if isinstance(source, BoundFile) else source.stat().st_size
    output_size = output.size if isinstance(output, BoundFile) else output.stat().st_size
    require(source_size == output_size == PACK_SIZE,
            "source/output volume sizes differ")
    outside = hashlib.sha256()
    changed = 0
    first = last = None
    cursor = 0
    while cursor < CHUNK_START:
        size = min(8 * 1024 * 1024, CHUNK_START - cursor)
        a = _read_source(source, cursor, size)
        b = _read_source(output, cursor, size)
        require(a == b, "output volume changed before target chunk")
        outside.update(b)
        cursor += size
    a = _read_source(source, CHUNK_START, CHUNK_SPAN)
    b = _read_source(output, CHUNK_START, CHUNK_SPAN)
    for local, (x, y) in enumerate(zip(a, b)):
        if x != y:
            changed += 1
            first = CHUNK_START + local if first is None else first
            last = CHUNK_START + local
    cursor = CHUNK_END
    while cursor < PACK_SIZE:
        size = min(8 * 1024 * 1024, PACK_SIZE - cursor)
        a = _read_source(source, cursor, size)
        b = _read_source(output, cursor, size)
        require(a == b, "output volume changed after target chunk")
        outside.update(b)
        cursor += size
    require(outside.hexdigest() == OUTSIDE_SHA256,
            "outside-target-chunk hash changed")
    return {
        "changed": changed,
        "first": first,
        "last": last,
        "outside": outside.hexdigest(),
    }


def _aligned16(value: int) -> int:
    return (value + 15) & ~15


def _mode(request: dict[str, Any]) -> str:
    if request["kind"] == "identity_noop_flag":
        return "identity_noop"
    if request["ids"] == list(range(int(request["new_count"]))):
        return "count_only_prefix"
    return "source_subset_remap"


def _ranges_complement(data: bytes, ranges: list[tuple[int, int]]) -> bytes:
    cursor = 0
    output = bytearray()
    for start, end in sorted(ranges):
        require(0 <= cursor <= start <= end <= len(data),
                "authorized decoded ranges overlap or escape the SCNE")
        output.extend(data[cursor:start])
        cursor = end
    output.extend(data[cursor:])
    return bytes(output)


def _expected_manifest(request: dict[str, Any], mode: str,
                       source_decoded: bytes, output_decoded: bytes,
                       output_body: bytes, consumed: int, padding: int,
                       alias: int, scratch: int, output_pack: Path | BoundFile,
                       output_sha256: str, changed_offsets: list[int],
                       reconstruction: dict[str, Any]) -> dict[str, Any]:
    new_count = int(request["new_count"])
    ranges = [
        (VERTEX_COUNT_FIELD, VERTEX_COUNT_FIELD + 2),
        (DRAW_COUNT_BYTE_OFFSET, DRAW_COUNT_BYTE_OFFSET + 1),
        (STREAM0_OFFSET, STREAM0_OFFSET + new_count * STREAM0_STRIDE),
        (STREAM1_OFFSET, STREAM1_OFFSET + new_count * STREAM1_STRIDE),
    ]
    prefixes: list[dict[str, Any]] = []
    tails: list[dict[str, Any]] = []
    streams = (
        (0, STREAM0_OFFSET, STREAM0_END, STREAM0_STRIDE,
         "95164ce59e125ac1775003846a1eb780c63f001c65f2b3da8d2aebd20fbe67f7"),
        (1, STREAM1_OFFSET, STREAM1_END, STREAM1_STRIDE,
         "5ad69b6eff91ed58f1882d08f9f69b299d0ea32d53cf729a6c0fb8a2a7c7cabe"),
    )
    stream_change_rows: list[dict[str, int]] = []
    for (stream_index, start, end, stride, _), changed in zip(
            streams, reconstruction["stream_prefix_changed_byte_counts"]):
        prefix_end = start + new_count * stride
        before_prefix = source_decoded[start:prefix_end]
        after_prefix = output_decoded[start:prefix_end]
        before_tail = source_decoded[prefix_end:end]
        after_tail = output_decoded[prefix_end:end]
        prefixes.append({
            "stream_index": stream_index,
            "span": [start, prefix_end],
            "source_sha256": sha256(before_prefix),
            "output_sha256": sha256(after_prefix),
            "changed_byte_count": changed,
        })
        tails.append({
            "stream_index": stream_index,
            "span": [prefix_end, end],
            "source_sha256": sha256(before_tail),
            "output_sha256": sha256(after_tail),
            "bit_exact": True,
        })
        stream_change_rows.append({
            "stream_index": stream_index,
            "changed_byte_count": changed,
        })
    complement_before = _ranges_complement(source_decoded, ranges)
    complement_after = _ranges_complement(output_decoded, ranges)
    require(complement_before == complement_after,
            "decoded complement changed outside authorized ranges")
    count_changed = sum(
        left != right for left, right in zip(
            source_decoded[VERTEX_COUNT_FIELD:VERTEX_COUNT_FIELD + 2],
            output_decoded[VERTEX_COUNT_FIELD:VERTEX_COUNT_FIELD + 2],
        )
    ) + int(
        source_decoded[DRAW_COUNT_BYTE_OFFSET]
        != output_decoded[DRAW_COUNT_BYTE_OFFSET]
    )
    return {
        "schema": MANIFEST_SCHEMA,
        "mode": mode,
        "authority": {
            "catalog": {
                "schema": CATALOG_SCHEMA,
                "size": CATALOG_SIZE,
                "sha256": CATALOG_SHA256,
                "authorized_target_count": 75,
            },
            "changed_count_boundary": {
                "schema": BOUNDARY_SCHEMA,
                "size": BOUNDARY_SIZE,
                "sha256": BOUNDARY_SHA256,
            },
            "recipe_schema": {
                "schema": RECIPE_SCHEMA,
                "size": RECIPE_SCHEMA_SIZE,
                "sha256": RECIPE_SCHEMA_SHA256,
            },
        },
        "request": {
            "kind": request["kind"],
            "schema": request["schema"],
            "sha256": request["sha256"],
            "new_vertex_count": new_count,
            "source_vertex_id_count": len(request["ids"]),
            "source_vertex_ids_sha256": request["ids_sha256"],
            "contains_external_vertex_or_attribute_values": False,
        },
        "target": {
            "target_id": TARGET_ID,
            "scene_index": 2648,
            "scene_name": "stadium",
            "shape_index": 1,
            "shape_name": "upper_deck",
            "source_vertex_count": SOURCE_VERTEX_COUNT,
            "output_vertex_count": new_count,
            "streams": [
                {
                    "stream_index": stream_index,
                    "physical_span": [start, end],
                    "stride_bytes": stride,
                    "source_sha256": source_hash,
                    "logical_prefix_bytes": new_count * stride,
                }
                for stream_index, start, end, stride, source_hash in streams
            ],
            "count_controls": [
                {
                    "kind": "shape_vertex_count_u16le",
                    "decoded_offset": VERTEX_COUNT_FIELD,
                    "source_count": SOURCE_VERTEX_COUNT,
                    "output_count": new_count,
                },
                {
                    "kind": "draw_arrays_high_count_byte",
                    "decoded_offset": DRAW_COUNT_BYTE_OFFSET,
                    "source_count": SOURCE_VERTEX_COUNT,
                    "output_count": new_count,
                },
            ],
        },
        "source": {
            "index": {
                "name": "0", "size_bytes": INDEX_SIZE,
                "sha256": INDEX_SHA256,
            },
            "volume": {
                "name": "9", "size_bytes": PACK_SIZE,
                "sha256_before": PACK_SHA256,
                "sha256_after": PACK_SHA256,
                "modified": False,
            },
            "outer_entry": {
                "outer_index": ENTRY_INDEX,
                "outer_id": "0xe4d6b0bc",
                "size_bytes": ENTRY_SIZE,
                "pack_offset": ENTRY_PACK_OFFSET,
                "source_sha256": ENTRY_SHA256,
            },
            "resource": {
                "chunk_index": 5,
                "entry_offset": 0x5EA40,
                "pack_span": [CHUNK_START, CHUNK_END],
                "fixed_span_bytes": CHUNK_SPAN,
                "source_span_sha256": SOURCE_SPAN_SHA256,
                "source_decoded_sha256": SOURCE_DECODED_SHA256,
            },
        },
        "edit": {
            "decoded_after_sha256": sha256(output_decoded),
            "decoded_changed_byte_count": len(changed_offsets),
            "count_control_changed_byte_count": count_changed,
            "stream_changed_byte_counts": stream_change_rows,
            "destination_prefixes": prefixes,
            "physical_tails": tails,
            "decoded_authorized_complement_source_sha256": sha256(complement_before),
            "decoded_authorized_complement_output_sha256": sha256(complement_after),
            "decoded_authorized_complement_bit_exact": True,
            "complete_records_copied_across_every_active_stream": True,
            "source_record_order_synchronized_across_streams": True,
            "source_vertex_ids_published": False,
        },
        "compression": {
            "codec": "VC-LZ",
            "stream_tag": 1,
            "offset_bits": 12,
            "retail_consumed_cap_bytes": RETAIL_CONSUMED,
            "rebuilt_consumed_bytes": consumed,
            "rebuilt_stream_sha256": sha256(output_body[:consumed]),
            "zero_gap_before_fixed_tail_bytes": RETAIL_CONSUMED - consumed,
            "total_stored_padding_bytes": padding,
            "minimum_alias_scratch_bytes": alias,
            "scratch_before": RETAIL_SCRATCH,
            "scratch_after": scratch,
            "retail_scne_observed_scratch_max": OBSERVED_SCRATCH_MAX,
            "fixed_final_tail_bytes": 16,
            "fixed_final_tail_sha256": TAIL_SHA256,
            "full_decode_exact": True,
            "identity_noop_returned_source_span_verbatim": mode == "identity_noop",
            "changed_path_recompressed": mode != "identity_noop",
        },
        "output": {
            "volume_name": "9",
            "volume_size_bytes": PACK_SIZE,
            "volume_sha256": output_sha256,
            "outer_entry_sha256": sha256(
                _read_source(output_pack, ENTRY_PACK_OFFSET, ENTRY_SIZE)
            ),
            "outside_target_resource_sha256": OUTSIDE_SHA256,
            "outside_target_resource_bit_exact": True,
            "fixed_resource_span_preserved": True,
            "directory_files": ["9", "manifest.json"],
            "manifest_contains_retail_records": False,
            "manifest_contains_source_vertex_ids": False,
        },
        "claims": {
            "offline_fixed_span_source_subset_writer_implemented": True,
            "runtime_visibility_proved": False,
            "original_xbox_hardware_proved": False,
            "bounds_or_culling_serializer_proved": False,
            "collision_or_lod_ownership_proved": False,
            "arbitrary_external_vertex_authoring_proved": False,
            "production_ready": False,
            "gui_exposed": False,
            "distribution_ready": False,
        },
    }


def _verify_bound(authority: dict[str, Any], request: dict[str, Any],
                  index: BoundFile, source_pack: BoundFile,
                  output_pack: BoundFile, manifest_file: BoundFile) -> dict[str, Any]:
    mapping = parse_index(index)
    require(source_pack.size == PACK_SIZE and source_pack.digest() == PACK_SHA256,
            "source volume 9 identity changed")
    source_outer = source_pack.read(mapping["pack_offset"], mapping["entry_size"])
    output_outer = output_pack.read(mapping["pack_offset"], mapping["entry_size"])
    require(sha256(source_outer) == ENTRY_SHA256,
            "source outer entry bytes changed")
    source_resources = walk_outer_resources(source_outer)
    output_resources = walk_outer_resources(output_outer)
    source_target = source_resources[5]
    output_target = output_resources[5]
    derived_chunk_start = mapping["pack_offset"] + source_target["offset"]
    require(derived_chunk_start == CHUNK_START
            and output_target["offset"] == source_target["offset"]
            and output_target["end"] == source_target["end"],
            "derived source/output upper_deck resource location changed")
    source_span = source_outer[source_target["offset"]:source_target["end"]]
    output_span = output_outer[output_target["offset"]:output_target["end"]]
    manifest, manifest_payload = _load_json_bound(
        manifest_file, "patch manifest", MAX_MANIFEST_BYTES
    )
    require(sha256(source_span) == SOURCE_SPAN_SHA256
            and sha256(source_span[:32]) == SOURCE_WRAPPER_SHA256,
            "source fixed SCNE span changed")
    source_fields = struct.unpack("<4s7I", source_span[:32])
    output_fields = struct.unpack("<4s7I", output_span[:32])
    require(source_fields == (b"SCNE", CHUNK_STORED, SYSTEM_BYTES, VIDEO_BYTES,
                              0xFEEDBEEF, RETAIL_SCRATCH, 0, 0),
            "source SCNE wrapper changed")
    require(output_fields[:5] == source_fields[:5]
            and output_fields[6:] == source_fields[6:]
            and all(left == right for index_byte, (left, right)
                    in enumerate(zip(source_span[:32], output_span[:32]))
                    if not 0x14 <= index_byte < 0x18),
            "output wrapper changed outside exact scratch field")
    source_body, output_body = source_span[32:], output_span[32:]
    source_decoded, source_lz = decompress_vc_lz(source_body, DECODED_SIZE)
    output_decoded, output_lz = decompress_vc_lz(output_body, DECODED_SIZE)
    require(source_lz == {"consumed": RETAIL_CONSUMED,
                          "literals": 508197, "matches": 158651}
            and sha256(source_body[:RETAIL_CONSUMED]) == RETAIL_STREAM_SHA256
            and sha256(source_decoded) == SOURCE_DECODED_SHA256,
            "source VC-LZ decode changed")
    require(source_body[RETAIL_CONSUMED:] == output_body[RETAIL_CONSUMED:]
            and len(output_body[RETAIL_CONSUMED:]) == 16
            and sha256(output_body[RETAIL_CONSUMED:]) == TAIL_SHA256,
            "fixed final tail changed")
    consumed = output_lz["consumed"]
    require(consumed <= RETAIL_CONSUMED
            and not any(output_body[consumed:RETAIL_CONSUMED]),
            "rebuilt stream exceeds cap or its fixed gap is nonzero")
    padding = CHUNK_STORED - consumed
    alias = minimum_overlap_scratch(output_body[:consumed], CHUNK_STORED, DECODED_SIZE)
    scratch = _aligned16(max(padding, alias))
    require(output_fields[5] == scratch and scratch <= OBSERVED_SCRATCH_MAX,
            "scratch differs from independently derived bounded value")

    boundary = authority["boundary"]
    stream_contracts = boundary["vertex_record_contract"]["streams"]
    for stream in stream_contracts:
        span = stream["source_physical_span"]
        require(sha256(source_decoded[span["offset"]:span["end_offset"]])
                == span["sha256"], "source physical stream hash changed")
    require(sha256(source_decoded[SHAPE_OFFSET:SHAPE_OFFSET + 0x100])
            == boundary["shape_and_coupled_fields"]["shape_record"]["sha256"],
            "source upper_deck shape record changed")
    require(sha256(source_decoded[SUBMESH_OFFSET:PUSH_OFFSET])
            == boundary["topology_contract"]["submesh_record"]["sha256"],
            "source upper_deck submesh record changed")
    require(sha256(source_decoded[PUSH_OFFSET:PUSH_OFFSET + PUSH_SIZE])
            == boundary["topology_contract"]["push"]["span"]["sha256"],
            "source upper_deck push record changed")
    inspect_target(source_decoded, SOURCE_VERTEX_COUNT)
    expected_decoded, reconstruction = _reconstruct(source_decoded, request)
    require(output_decoded == expected_decoded,
            "output decoded SCNE differs from independent whole-record reconstruction")
    parsed = inspect_target(output_decoded, int(request["new_count"]))
    changed_offsets = [index_byte for index_byte, (left, right)
                       in enumerate(zip(source_decoded, output_decoded)) if left != right]
    require(changed_offsets == reconstruction["authorized_changed_offsets"],
            "decoded changed-offset set differs from independent reconstruction")

    pack_diff = compare_packs(source_pack, output_pack)
    output_sha = output_pack.digest()
    mode = _mode(request)
    if mode == "identity_noop":
        require(output_span == source_span and output_sha == PACK_SHA256
                and pack_diff["changed"] == 0 and consumed == RETAIL_CONSUMED
                and scratch == RETAIL_SCRATCH,
                "identity no-op is not whole-volume byte-exact")
    else:
        require(output_sha != PACK_SHA256 and pack_diff["changed"] > 0,
                "changed-count request changed no copied-volume bytes")

    expected_manifest = _expected_manifest(
        request, mode, source_decoded, output_decoded, output_body, consumed,
        padding, alias, scratch, output_pack, output_sha, changed_offsets,
        reconstruction,
    )
    require(manifest == expected_manifest,
            "manifest differs from the independent complete reconstruction")

    require(index.digest() == INDEX_SHA256
            and source_pack.digest() == PACK_SHA256,
            "retail source changed during verification")
    return {
        "schema": VERIFY_SCHEMA,
        "mode": mode,
        "authority": {
            "boundary_sha256": BOUNDARY_SHA256,
            "catalog_sha256": CATALOG_SHA256,
            "recipe_schema_sha256": RECIPE_SCHEMA_SHA256,
        },
        "request": {
            "kind": request["kind"],
            "schema": request["schema"],
            "sha256": request["sha256"],
            "new_vertex_count": request["new_count"],
            "source_vertex_id_count": len(request["ids"]),
            "source_vertex_ids_sha256": request["ids_sha256"],
            "source_vertex_ids_embedded": False,
        },
        "source": {
            "index_sha256": INDEX_SHA256,
            "volume_sha256": PACK_SHA256,
            "decoded_sha256": SOURCE_DECODED_SHA256,
            "retail_unchanged": True,
        },
        "output": {
            "volume_sha256": output_sha,
            "pack_changed_byte_count": pack_diff["changed"],
            "first_changed_offset": pack_diff["first"],
            "last_changed_offset": pack_diff["last"],
            "outside_chunk_sha256": pack_diff["outside"],
            "outside_chunk_bit_exact": True,
        },
        "decoded": {
            "output_sha256": sha256(output_decoded),
            "decoded_changed_byte_count": len(changed_offsets),
            "authorized_changed_offsets_sha256": sha256(canonical_json(changed_offsets)),
            "outside_authorized_spans_bit_exact": True,
            "stream_prefix_changed_byte_counts":
                reconstruction["stream_prefix_changed_byte_counts"],
            "physical_stream_tails_bit_exact": True,
        },
        "compression": {
            "consumed_bytes": consumed,
            "retail_cap": RETAIL_CONSUMED,
            "zero_gap_bytes": RETAIL_CONSUMED - consumed,
            "padding_bytes": padding,
            "minimum_alias_scratch_bytes": alias,
            "scratch_bytes": scratch,
            "retail_observed_scratch_max": OBSERVED_SCRATCH_MAX,
            "fixed_tail_sha256": TAIL_SHA256,
        },
        "topology": parsed,
        "manifest_sha256": sha256(manifest_payload),
        "claims": {
            "source_subset_changed_vertex_count_write_back": mode != "identity_noop",
            "identity_noop_whole_volume_exact": mode == "identity_noop",
            "arbitrary_external_vertex_authoring": False,
            "bounds_culling_collision_or_lod_write_back": False,
            "runtime_proved": False,
            "hardware_proved": False,
            "production_ready": False,
            "public_editor_exposed": False,
        },
    }


def _publish_report(parent: BoundDirectory, name: str, payload: bytes) -> BoundFile:
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
             | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        fd = os.open(name, flags, 0o644, dir_fd=parent.fd)
    except FileExistsError as exc:
        raise UpperDeckSubsetVerifyError("refusing existing report") from exc
    try:
        cursor = 0
        while cursor < len(payload):
            written = os.write(fd, payload[cursor:])
            require(written > 0, "report write made no progress")
            cursor += written
        os.fsync(fd)
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size == len(payload),
                "published report extent changed")
    finally:
        os.close(fd)
    report = parent.open_file(name, "verification report")
    require(report.read_all(max(len(payload), 1)) == payload,
            "published report bytes differ from the verified result")
    return report


def verify(source_index: Path, boundary_path: Path, catalog_path: Path,
           recipe_schema_path: Path, output_dir: Path,
           recipe_path: Path | None = None, *, identity_noop: bool = False,
           report_path: Path | None = None) -> dict[str, Any]:
    require((recipe_path is None) != (not identity_noop),
            "choose exactly one recipe or identity-noop request")
    report_absolute = preflight_report_path(output_dir, report_path)
    source_index_absolute = _absolute(source_index)
    require(source_index_absolute.name == "0", "NFL archive index must be named 0")

    with ExitStack() as stack:
        source_directory = stack.enter_context(BoundDirectory(
            source_index_absolute.parent, "retail source directory"
        ))
        index = stack.enter_context(source_directory.open_file(
            source_index_absolute.name, "NFL archive index"
        ))
        source_pack = stack.enter_context(source_directory.open_file(
            "9", "source volume 9"
        ))

        boundary_file = stack.enter_context(BoundFile(
            boundary_path, "changed-count boundary"
        ))
        catalog_file = stack.enter_context(BoundFile(
            catalog_path, "static-target catalog"
        ))
        recipe_schema_file = stack.enter_context(BoundFile(
            recipe_schema_path, "source-subset recipe schema"
        ))
        authority = load_authority(
            boundary_file, catalog_file, recipe_schema_file
        )

        recipe_file: BoundFile | None = None
        if identity_noop:
            request = identity_request()
        else:
            require(recipe_path is not None, "changed request recipe is unavailable")
            recipe_file = stack.enter_context(BoundFile(
                recipe_path, "source-subset recipe"
            ))
            request = load_recipe(recipe_file)

        output_directory = stack.enter_context(BoundDirectory(
            output_dir, "output directory"
        ))
        require(output_directory.names() == ["9", "manifest.json"],
                "output directory must contain only 9 and manifest.json")
        output_pack = stack.enter_context(output_directory.open_file(
            "9", "output volume 9"
        ))
        manifest_file = stack.enter_context(output_directory.open_file(
            "manifest.json", "patch manifest"
        ))
        require(source_pack.identity != output_pack.identity,
                "output volume path or inode aliases the retail source")

        report_parent: BoundDirectory | None = None
        if report_absolute is not None:
            report_parent = stack.enter_context(BoundDirectory(
                report_absolute.parent, "report parent"
            ))
            require(report_parent.identity != output_directory.identity,
                    "report parent aliases the verified output directory")
            try:
                os.stat(report_absolute.name, dir_fd=report_parent.fd,
                        follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise UpperDeckSubsetVerifyError("refusing existing report")

        result = _verify_bound(
            authority, request, index, source_pack, output_pack, manifest_file
        )

        bound_inputs = [
            index, source_pack, boundary_file, catalog_file, recipe_schema_file,
            output_pack, manifest_file,
        ]
        if recipe_file is not None:
            bound_inputs.append(recipe_file)
        for bound in bound_inputs:
            bound.assert_stable()
        source_directory.assert_stable(
            {"0": index, "9": source_pack}, exact=False
        )
        output_children = {"9": output_pack, "manifest.json": manifest_file}
        output_directory.assert_stable(output_children)

        require(index.digest() == INDEX_SHA256
                and source_pack.digest() == PACK_SHA256
                and boundary_file.digest() == BOUNDARY_SHA256
                and catalog_file.digest() == CATALOG_SHA256
                and recipe_schema_file.digest() == RECIPE_SCHEMA_SHA256
                and output_pack.digest() == result["output"]["volume_sha256"]
                and manifest_file.digest() == result["manifest_sha256"],
                "a bound verification input changed before completion")
        if recipe_file is not None:
            require(recipe_file.digest() == request["sha256"],
                    "source-subset recipe changed before completion")

        if report_absolute is not None:
            require(report_parent is not None, "report parent binding is unavailable")
            published = stack.enter_context(_publish_report(
                report_parent, report_absolute.name, canonical_json(result)
            ))
            published.assert_stable()
            report_parent.assert_stable({report_absolute.name: published}, exact=False)
            output_directory.assert_stable(output_children)
            for bound in bound_inputs:
                bound.assert_stable()
            require(output_pack.digest() == result["output"]["volume_sha256"]
                    and manifest_file.digest() == result["manifest_sha256"],
                    "verified output changed while publishing its report")
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-index", required=True, type=Path)
    parser.add_argument("--boundary", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--recipe-schema", required=True, type=Path)
    request = parser.add_mutually_exclusive_group(required=True)
    request.add_argument("--recipe", type=Path)
    request.add_argument("--identity-noop", action="store_true")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    preflight_report_path(args.output_dir, args.report)
    report = verify(
        args.source_index,
        args.boundary,
        args.catalog,
        args.recipe_schema,
        args.output_dir,
        args.recipe,
        identity_noop=args.identity_noop,
        report_path=args.report,
    )
    print(
        "NFL_UPPER_DECK_SUBSET_VERIFY_PASS "
        f"mode={report['mode']} vertices={report['request']['new_vertex_count']} "
        f"consumed={report['compression']['consumed_bytes']} "
        f"scratch={report['compression']['scratch_bytes']} runtime=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UpperDeckSubsetVerifyError, struct.error, KeyError,
            IndexError, TypeError) as exc:
        raise SystemExit(f"error: {exc}") from exc
