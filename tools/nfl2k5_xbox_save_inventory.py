#!/usr/bin/env python3
"""Inventory NFL 2K5 FATX saves and map the observed slider snapshot.

This tool is deliberately read-only with respect to the supplied HDD image,
the retail XBE, and every save container.  It emits metadata, hashes, decoded
container names/types, and finite slider values; it never extracts or writes a
SAVEGAME.DAT/EXTRA/TYPE payload and it does not attempt to forge a signature.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
from typing import Any, BinaryIO

from fatx_dirent_rename import Dirent, FatXVolume, PARTITIONS
from xbe_info import Xbe


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "nfl2k5_xbox_save_inventory/v1"
TITLE_ID = "53450030"
IMAGE_SIZE = 8 * 1024**3
EXPECTED_XBE_SIZE = 11_948_032
EXPECTED_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
EXPECTED_LEDGER_SIZE = 9_431_836
EXPECTED_LEDGER_SHA256 = (
    "902eb0e5f504bcc24ee55aa895d8fa65e4cb3db05409eb8daaf147e3d74f28f7"
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")

DEFAULT_XBE = ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
DEFAULT_LEDGER = ROOT / "research/functions/nfl2k5/functions.tsv"
DEFAULT_JSON = ROOT / "reports/gameplay_tuning/nfl2k5_xbox_save_inventory.json"
DEFAULT_INVENTORY_TSV = (
    ROOT / "reports/gameplay_tuning/nfl2k5_xbox_save_inventory.tsv"
)
DEFAULT_SLIDER_TSV = (
    ROOT / "reports/gameplay_tuning/nfl2k5_xbox_save_slider_snapshot.tsv"
)

LABELS = (
    "Human Blocking", "Human Passing", "Human Running", "Human Catching",
    "Human Coverage", "Human Pursuit", "Human Tackling", "Human Kicking",
    "Human Fatigue", "CPU Blocking", "CPU Passing", "CPU Running",
    "CPU Catching", "CPU Coverage", "CPU Pursuit", "CPU Tackling",
    "CPU Kicking", "CPU Fatigue", "Injury", "Fumble", "Interception",
)

EXPECTED_GLOBALS = {
    "Human Blocking": 0x00E600D4,
    "Human Passing": 0x00E600D8,
    "Human Running": 0x00E600DC,
    "Human Catching": 0x00E600F4,
    "Human Coverage": 0x00E600E0,
    "Human Pursuit": 0x00E600E4,
    "Human Tackling": 0x00E600E8,
    "Human Kicking": 0x00E600EC,
    "Human Fatigue": 0x00E600F0,
    "CPU Blocking": 0x00E600F8,
    "CPU Passing": 0x00E600FC,
    "CPU Running": 0x00E60100,
    "CPU Catching": 0x00E60118,
    "CPU Coverage": 0x00E60104,
    "CPU Pursuit": 0x00E60108,
    "CPU Tackling": 0x00E6010C,
    "CPU Kicking": 0x00E60110,
    "CPU Fatigue": 0x00E60114,
    "Injury": 0x00E60204,
    "Fumble": 0x00E60208,
    "Interception": 0x00E6020C,
}

SLIDER_LAYOUT = (
    ("Injury", 0x284, "standalone"),
    ("Fumble", 0x288, "standalone"),
    ("Interception", 0x28C, "standalone"),
    *((label, 0x298 + index * 4, "cpu_vector")
      for index, label in enumerate(LABELS[9:18])),
    *((label, 0x2BC + index * 4, "human_vector")
      for index, label in enumerate(LABELS[:9])),
)

EXPECTED_SAVE_TYPE_COUNTS = {"USR": 1, "STG": 1, "FXG": 1, "TMM": 5}
EXPECTED_PRIMARY_IDS = {
    "Settings1": "83C3760943CB",
    "Franchise1": "256B40374FD6",
}

WITNESSES = {
    "container_filename_dispatch": (
        0x0004B1F0, 0x0004B291,
        "de6bf3a31e9ddb6fddd18ac58367e4f629fe6d68bbf0f778cee9acb8838efc33",
    ),
    "signature_begin": (
        0x0004B2A0, 0x0004B2F0,
        "b5d4bbcdfba146e16697d982421dfaaadc743fd0e4e24e2fd855cff34b0a0af4",
    ),
    "signature_read_compare": (
        0x0004D520, 0x0004D62B,
        "1134911b43c8abf692b1890fcfe05136d6a506526eeb52d9e63a447d769f1162",
    ),
    "signature_write_close": (
        0x0004C880, 0x0004C8DE,
        "1903039f9287fe5d892a217833205f3dbb72425d4b9b3a2628413c2447f41247",
    ),
    "slider_synchronizer": (
        0x000E3DC0, 0x000E3F05,
        "1847cb3768d1b71bef0d92e2154b69880a7ffde1adeefe1aa98eb343af1b8c18",
    ),
}


class SaveInventoryError(ValueError):
    """A source identity or recovered invariant differs."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SaveInventoryError(message)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def hx(value: int, width: int = 8) -> str:
    return f"0x{value:0{width}X}"


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_argument(value: str) -> str:
    """Accept only the canonical lowercase digest spelling used by reports."""

    if SHA256_RE.fullmatch(value) is None:
        raise argparse.ArgumentTypeError(
            "expected image SHA-256 must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def find_all(payload: bytes, needle: bytes) -> list[int]:
    offsets: list[int] = []
    cursor = 0
    while True:
        offset = payload.find(needle, cursor)
        if offset < 0:
            return offsets
        offsets.append(offset)
        cursor = offset + 1


def read_pinned_regular(path: Path, expected_size: int, expected_hash: str,
                        label: str) -> bytes:
    before = path.lstat()
    require(
        stat.S_ISREG(before.st_mode)
        and not stat.S_ISLNK(before.st_mode)
        and before.st_nlink == 1,
        f"{label} must be a single-link non-symlink regular file",
    )
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(descriptor)
        require(
            stat.S_ISREG(opened.st_mode)
            and opened.st_nlink == 1
            and opened.st_size == expected_size,
            f"{label} size, type, or link count differs",
        )
        require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
                f"{label} identity changed before open")
        chunks: list[bytes] = []
        remaining = expected_size
        while remaining:
            chunk = os.read(descriptor, min(16 * 1024 * 1024, remaining))
            require(bool(chunk), f"{label} shortened during read")
            chunks.append(chunk)
            remaining -= len(chunk)
        require(not os.read(descriptor, 1), f"{label} grew during read")
        payload = b"".join(chunks)
        require(sha256(payload) == expected_hash, f"{label} SHA-256 differs")
        after = os.fstat(descriptor)
        # ``opened`` and ``after`` are both os.fstat of this one descriptor: two
        # fd stats, which agree on st_ctime_ns on every platform, so it stays in.
        require(
            (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
                after.st_nlink,
            )
            == (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
                opened.st_ctime_ns,
                opened.st_nlink,
            ),
            f"{label} changed during read",
        )
        return payload
    finally:
        os.close(descriptor)


def hash_descriptor(descriptor: int, size: int) -> str:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    remaining = size
    while remaining:
        chunk = os.read(descriptor, min(32 * 1024 * 1024, remaining))
        require(bool(chunk), "raw HDD image shortened while hashing")
        digest.update(chunk)
        remaining -= len(chunk)
    require(not os.read(descriptor, 1), "raw HDD image grew while hashing")
    return digest.hexdigest()


def open_image_read_only(path: Path, expected_hash: str) -> tuple[int, os.stat_result, str]:
    before = path.lstat()
    require(
        stat.S_ISREG(before.st_mode)
        and not stat.S_ISLNK(before.st_mode)
        and before.st_nlink == 1,
        "raw HDD image must be a single-link non-symlink regular file",
    )
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    opened = os.fstat(descriptor)
    try:
        require(
            stat.S_ISREG(opened.st_mode)
            and opened.st_nlink == 1
            and opened.st_size == IMAGE_SIZE,
            "raw HDD image must be a single-link regular file of exactly 8 GiB",
        )
        require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
                "raw HDD image identity changed before open")
        digest = hash_descriptor(descriptor, opened.st_size)
        require(digest == expected_hash, "raw HDD image SHA-256 differs")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor, opened, digest
    except Exception:
        os.close(descriptor)
        raise


def require_descriptor_unchanged(descriptor: int, opened: os.stat_result) -> None:
    """Re-check the pinned image descriptor against its open-time fstat.

    ``opened`` is the ``os.fstat`` :func:`open_image_read_only` took, so both
    sides are fd stats.  Two fd stats agree on st_ctime_ns on every platform,
    Windows included, so the change time stays in this fingerprint.
    """

    after = os.fstat(descriptor)
    require(
        (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        )
        == (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
            opened.st_nlink,
        ),
        "raw HDD image changed during analysis",
    )


def read_file(volume: FatXVolume, entry: Dirent, maximum: int = 16 * 1024 * 1024) -> bytes:
    require(not entry.is_directory, f"{entry.name} is a directory")
    require(0 <= entry.file_size <= maximum, f"{entry.name} exceeds analysis bound")
    if entry.file_size == 0:
        return b""
    chain = volume.cluster_chain(entry.first_cluster)
    required_clusters = (
        entry.file_size + volume.bytes_per_cluster - 1
    ) // volume.bytes_per_cluster
    require(len(chain) == required_clusters,
            f"{entry.name} FAT chain has unexpected slack clusters")
    payload = bytearray()
    remaining = entry.file_size
    for cluster in chain:
        volume.image.seek(volume.cluster_offset(cluster))
        chunk = volume.image.read(min(volume.bytes_per_cluster, remaining))
        require(len(chunk) == min(volume.bytes_per_cluster, remaining),
                f"short FATX file cluster for {entry.name}")
        payload.extend(chunk)
        remaining -= len(chunk)
    require(remaining == 0 and len(payload) == entry.file_size,
            f"short FATX file {entry.name}")
    return bytes(payload)


def dirent_metadata(entry: Dirent, cluster_count: int) -> dict[str, Any]:
    fields = struct.unpack("<BB42sLLLLL", entry.raw)
    require(fields[3] == entry.first_cluster and fields[4] == entry.file_size,
            "FATX dirent decoder disagreement")
    return {
        "attributes": hx(entry.attributes, 2),
        "dirent_offset": hx(entry.offset, 16),
        "first_cluster": entry.first_cluster,
        "cluster_count": cluster_count,
        "file_size": entry.file_size,
        "fatx_timestamps_raw": {
            "created": hx(fields[5]),
            "accessed": hx(fields[6]),
            "updated": hx(fields[7]),
        },
    }


def decode_save_meta(payload: bytes) -> str:
    require(payload.startswith(b"\xff\xfe"), "SaveMeta.xbx lacks UTF-16LE BOM")
    text = payload[2:].decode("utf-16le")
    require(text.startswith("Name=") and text.endswith("\r\n") and
            text.count("\r\n") == 1,
            "SaveMeta.xbx structure differs")
    name = text[5:-2]
    require(bool(name) and all(character.isprintable() for character in name),
            "SaveMeta.xbx name is invalid")
    return name


def decode_type(payload: bytes) -> str:
    require(len(payload) == 8 and payload[-2:] == b"\0\0",
            "TYPE structure differs")
    value = payload[:-2].decode("utf-16le")
    require(len(value) == 3 and value.isascii() and value.isupper(),
            "TYPE code is invalid")
    return value


def entry_payload(volume: FatXVolume, entry: Dirent) -> tuple[bytes, dict[str, Any]]:
    payload = read_file(volume, entry)
    chain_count = 0 if not payload else len(volume.cluster_chain(entry.first_cluster))
    metadata = dirent_metadata(entry, chain_count)
    metadata["sha256"] = sha256(payload)
    return payload, metadata


def inventory_title(volume: FatXVolume) -> tuple[list[dict[str, Any]], dict[str, dict[str, bytes]]]:
    title = volume.resolve(["UDATA", TITLE_ID])
    require(title.is_directory, "NFL title path is not a directory")
    title_entries = volume.read_directory(title.first_cluster)
    require(len(title_entries) == 11, "NFL title entry count differs")
    containers: list[dict[str, Any]] = []
    payloads_by_id: dict[str, dict[str, bytes]] = {}
    title_files: list[dict[str, Any]] = []

    for entry in title_entries:
        if not entry.is_directory:
            payload, metadata = entry_payload(volume, entry)
            title_files.append({"name": entry.name, **metadata})
            continue
        children = volume.read_directory(entry.first_cluster)
        by_name = {child.name: child for child in children}
        require(len(by_name) == len(children) and set(by_name) == {
            "SaveMeta.xbx", "TYPE", "SAVEGAME.DAT", "EXTRA"
        }, f"save container {entry.name} child set differs")
        decoded: dict[str, bytes] = {}
        files: dict[str, dict[str, Any]] = {}
        for filename in ("SaveMeta.xbx", "TYPE", "SAVEGAME.DAT", "EXTRA"):
            decoded[filename], files[filename] = entry_payload(volume, by_name[filename])
        display_name = decode_save_meta(decoded["SaveMeta.xbx"])
        save_type = decode_type(decoded["TYPE"])
        require(len(decoded["EXTRA"]) == 20, f"{display_name} EXTRA size differs")
        container_chain_count = len(volume.cluster_chain(entry.first_cluster))
        containers.append({
            "directory_id": entry.name,
            "display_name": display_name,
            "type": save_type,
            "directory": dirent_metadata(entry, container_chain_count),
            "files": files,
        })
        payloads_by_id[entry.name] = decoded

    require({row["name"] for row in title_files} == {
        "TitleMeta.xbx", "TitleImage.xbx", "SaveImage.xbx"
    }, "NFL title-level file set differs")
    type_counts = {
        code: sum(row["type"] == code for row in containers)
        for code in EXPECTED_SAVE_TYPE_COUNTS
    }
    require(type_counts == EXPECTED_SAVE_TYPE_COUNTS,
            "NFL save type counts differ")
    containers.sort(key=lambda row: (row["type"], row["display_name"], row["directory_id"]))
    return containers, payloads_by_id


def normalized_slider(payload: bytes, offset: int, label: str) -> float:
    require(offset + 4 <= len(payload), f"{label} slider is outside payload")
    value = struct.unpack_from("<f", payload, offset)[0]
    require(math.isfinite(value) and 0.0 <= value <= 1.0,
            f"{label} slider is outside the proved stock range")
    normalized = round(value, 3)
    require(abs(normalized / 0.025 - round(normalized / 0.025)) < 1e-6,
            f"{label} slider is not on the stock 0.025 grid")
    return normalized


def extract_slider_snapshot(settings: bytes, franchise: bytes) -> dict[str, Any]:
    require(len(settings) == 0x2E0, "Settings1 SAVEGAME.DAT size differs")
    require(len(franchise) == 720_044, "Franchise1 SAVEGAME.DAT size differs")
    franchise_prefix = franchise[:len(settings)]
    rows: list[dict[str, Any]] = []
    for physical_index, (label, offset, group) in enumerate(SLIDER_LAYOUT):
        rows.append({
            "physical_index": physical_index,
            "semantic_index": LABELS.index(label),
            "label": label,
            "group": group,
            "offset": hx(offset, 3),
            "settings1": normalized_slider(settings, offset, label),
            "franchise1": normalized_slider(franchise_prefix, offset, label),
        })
    require(len(rows) == 21 and len({row["offset"] for row in rows}) == 21,
            "slider layout is not 21 unique slots")
    require(all(row["settings1"] == 0.5 for row in rows),
            "Settings1 slider snapshot is no longer the observed all-0.5 vector")
    return {
        "classification": (
            "exact observed save-field join; serializer function and safe writer remain unproved"
        ),
        "settings1_payload_size": len(settings),
        "settings1_sha256": sha256(settings),
        "franchise1_payload_size": len(franchise),
        "franchise1_sha256": sha256(franchise),
        "franchise1_settings_prefix_size": len(settings),
        "franchise1_settings_prefix_sha256": sha256(franchise_prefix),
        "franchise1_tail_size": len(franchise) - len(settings),
        "franchise1_tail_sha256": sha256(franchise[len(settings):]),
        "aligned_prefix_comparison": {
            "equal_byte_count": sum(left == right for left, right in
                                    zip(settings, franchise_prefix)),
            "differing_byte_count": sum(left != right for left, right in
                                        zip(settings, franchise_prefix)),
            "equal_u32_slot_count": sum(
                settings[offset:offset + 4] == franchise_prefix[offset:offset + 4]
                for offset in range(0, len(settings), 4)
            ),
            "u32_slot_count": len(settings) // 4,
        },
        "physical_storage_order": [row["label"] for row in rows],
        "semantic_order": list(LABELS),
        "rows": rows,
    }


def xbe_bytes(xbe: Xbe, start: int, end_inclusive: int) -> bytes:
    size = end_inclusive - start + 1
    offset = xbe.va_to_offset(start, size)
    return xbe.data[offset:offset + size]


def rel32_call_target(xbe: Xbe, call_va: int) -> int:
    encoded = xbe_bytes(xbe, call_va, call_va + 4)
    require(encoded[0] == 0xE8, f"expected x86 CALL at {hx(call_va)}")
    return call_va + 5 + struct.unpack_from("<i", encoded, 1)[0]


def parse_ledger(payload: bytes) -> dict[int, dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8")), delimiter="\t"))
    require(len(rows) == 20_131, "NFL function ledger row count differs")
    result = {
        int(row["address"], 16): row
        for row in rows if row["address"].startswith("0x")
    }
    require(len(result) == 19_971, "NFL function ledger address set is incomplete")
    return result


def split_calls(value: str) -> list[str]:
    return value.split(";") if value else []


def analyze_executable(xbe_path: Path, xbe_payload: bytes,
                       ledger_payload: bytes) -> dict[str, Any]:
    xbe = Xbe(xbe_path)
    require(xbe.data == xbe_payload and xbe.data[:4] == b"XBEH",
            "retail executable changed between pinned read and parse")

    strings = {
        "SAVEGAME.DAT": 0x00E60B24,
        "EXTRA": 0x00E60B40,
        "TYPE": 0x00E60B4C,
    }
    for expected, address in strings.items():
        require(xbe.utf16z_va(address) == expected,
                f"save filename string differs at {hx(address)}")
    references = (
        (0x0004B254, "SAVEGAME.DAT"),
        (0x0004B27E, "EXTRA"),
        (0x0004B269, "TYPE"),
    )
    for site, name in references:
        encoded_pointer = struct.pack("<I", strings[name])
        require(xbe_bytes(xbe, site, site + 3) == encoded_pointer,
                f"save filename reference differs at {hx(site)}")
        occurrences = find_all(xbe.data, encoded_pointer)
        require(occurrences == [xbe.va_to_offset(site, 4)],
                f"save filename pointer occurrence set differs for {name}")

    witness_rows: dict[str, Any] = {}
    for name, (start, end, expected_hash) in WITNESSES.items():
        payload = xbe_bytes(xbe, start, end)
        require(sha256(payload) == expected_hash, f"{name} code witness differs")
        witness_rows[name] = {
            "range": f"{hx(start)}-{hx(end)}",
            "size": len(payload),
            "sha256": expected_hash,
        }

    require(rel32_call_target(xbe, 0x0004B2BB) == 0x0001FE1F,
            "save signature-begin call target differs")
    require(xbe_bytes(xbe, 0x0004B2AE, 0x0004B2AF) == b"\x57\x89",
            "save signature-begin mode witness differs")

    slider_globals: dict[str, int] = {}
    table = 0x00501F54
    stride = 0x34
    for index, expected_label in enumerate(LABELS):
        row_va = table + index * stride
        row = xbe_bytes(xbe, row_va, row_va + stride - 1)
        kind, label_pointer = struct.unpack_from("<II", row)
        require(kind == 4 and xbe.utf16z_va(label_pointer) == expected_label,
                f"slider descriptor {index} differs")
        current_getter = struct.unpack_from("<I", row, 0x14)[0]
        getter = xbe_bytes(xbe, current_getter, current_getter + 6)
        require(getter[:2] == b"\xD9\x05" and getter[6] == 0xC3,
                f"slider getter differs for {expected_label}")
        slider_globals[expected_label] = struct.unpack_from("<I", getter, 2)[0]
    require(slider_globals == EXPECTED_GLOBALS,
            "slider global map differs")

    ledger = parse_ledger(ledger_payload)
    api_rows = {
        "XCalculateSignatureBegin": 0x0001FE1F,
        "XCalculateSignatureUpdate": 0x0001FE33,
        "XCalculateSignatureEnd": 0x0001FE81,
    }
    save_owner_expectations = {
        "XCalculateSignatureBegin": {"0x0004B2A0:FUN_0004b2a0"},
        "XCalculateSignatureUpdate": {"0x0004D520:FUN_0004d520"},
        "XCalculateSignatureEnd": {
            "0x0004C880:FUN_0004c880", "0x0004D520:FUN_0004d520"
        },
    }
    api_ownership: dict[str, Any] = {}
    for name, address in api_rows.items():
        row = ledger.get(address)
        require(row is not None and row["name"] == name,
                f"ledger signature API row differs for {name}")
        callers = split_calls(row["callers"])
        expected = save_owner_expectations[name]
        require(expected.issubset(set(callers)),
                f"save-container caller missing for {name}")
        api_ownership[name] = {
            "address": hx(address),
            "direct_caller_count": len(callers),
            "save_container_direct_callers": sorted(expected),
            "other_direct_caller_count": len(callers) - len(expected),
        }

    return {
        "filename_dispatch": {
            "owner": "0x0004B1F0",
            "calls_XCreateSaveGame": True,
            "selector": {
                "0": "EXTRA", "1": "TYPE", "other": "SAVEGAME.DAT"
            },
            "utf16_filename_addresses": {
                name: hx(address) for name, address in strings.items()
            },
            "only_pointer_immediates": [
                {"reference": hx(site), "filename": name,
                 "target": hx(strings[name])}
                for site, name in references
            ],
        },
        "signature_owner": {
            "begin": {
                "owner": "0x0004B2A0",
                "call": "0x0004B2BB",
                "XCalculateSignatureBegin_mode": 0,
            },
            "stream_update_and_read_validation": {
                "owner": "0x0004D520",
                "updates_with_transferred_SAVEGAME_DAT_bytes": True,
                "ends_at_read_boundary": True,
                "reads_EXTRA_size": 20,
                "compares_calculated_result_to_EXTRA": True,
            },
            "write_close": {
                "owner": "0x0004C880",
                "ends_signature": True,
                "writes_EXTRA_size": 20,
            },
            "api_call_ownership": api_ownership,
            "current_EXTRA_cryptographically_recomputed": False,
            "reason_not_recomputed": (
                "XCalculateSignature mode 0 uses Xbox platform key state; this audit "
                "does not extract keys or implement a signature writer"
            ),
        },
        "slider_runtime_join": {
            "descriptor_table": hx(table),
            "descriptor_count": 21,
            "synchronizer_owner": "0x000E3DC0",
            "synchronizer_order": [*LABELS[9:18], *LABELS[:9]],
            "save_vector_order_matches_synchronizer": True,
            "standalone_globals": {
                label: hx(slider_globals[label])
                for label in LABELS[18:21]
            },
            "vector_globals": {
                label: hx(slider_globals[label])
                for label in (*LABELS[9:18], *LABELS[:9])
            },
        },
        "code_witnesses": witness_rows,
    }


def build_report(image: Path, expected_image_sha256: str,
                 xbe_path: Path, ledger_path: Path) -> dict[str, Any]:
    xbe_payload = read_pinned_regular(
        xbe_path, EXPECTED_XBE_SIZE, EXPECTED_XBE_SHA256, "NFL retail XBE"
    )
    ledger_payload = read_pinned_regular(
        ledger_path, EXPECTED_LEDGER_SIZE, EXPECTED_LEDGER_SHA256,
        "NFL function ledger"
    )
    descriptor, opened, image_hash = open_image_read_only(
        image, expected_image_sha256
    )
    try:
        stream: BinaryIO = os.fdopen(os.dup(descriptor), "rb", closefd=True)
        try:
            partition_offset, partition_length = PARTITIONS["E"]
            partition_length = min(partition_length, opened.st_size - partition_offset)
            volume = FatXVolume(stream, partition_offset, partition_length)
            require(volume.bytes_per_cluster == 0x4000 and not volume.fat16,
                    "E partition FATX geometry differs")
            containers, payloads = inventory_title(volume)
        finally:
            stream.close()
        by_display_name = {row["display_name"]: row for row in containers}
        require(len(by_display_name) == len(containers),
                "save display names are not unique")
        for display_name, directory_id in EXPECTED_PRIMARY_IDS.items():
            require(by_display_name.get(display_name, {}).get("directory_id") == directory_id,
                    f"{display_name} directory identity differs")
        settings = payloads[EXPECTED_PRIMARY_IDS["Settings1"]]["SAVEGAME.DAT"]
        franchise = payloads[EXPECTED_PRIMARY_IDS["Franchise1"]]["SAVEGAME.DAT"]
        slider_snapshot = extract_slider_snapshot(settings, franchise)
        executable = analyze_executable(xbe_path, xbe_payload, ledger_payload)
        require_descriptor_unchanged(descriptor, opened)
    finally:
        os.close(descriptor)

    return {
        "schema": SCHEMA,
        "inputs": {
            "raw_hdd": {
                "path": str(image),
                "size": opened.st_size,
                "sha256": image_hash,
                "opened_read_only": True,
                "partition": "E",
                "fatx_serial": hx(volume.serial),
                "bytes_per_cluster": volume.bytes_per_cluster,
            },
            "retail_xbe": {
                "path": str(DEFAULT_XBE.relative_to(ROOT)),
                "size": len(xbe_payload),
                "sha256": EXPECTED_XBE_SHA256,
            },
            "function_ledger": {
                "path": str(DEFAULT_LEDGER.relative_to(ROOT)),
                "size": len(ledger_payload),
                "sha256": EXPECTED_LEDGER_SHA256,
            },
        },
        "scope": {
            "read_only": True,
            "retail_or_save_bytes_emitted": False,
            "save_writer_exposed": False,
            "signature_writer_exposed": False,
            "platform_keys_read_or_emitted": False,
            "runtime_load_test_performed": False,
            "source_image_modified": False,
        },
        "summary": {
            "title_id": TITLE_ID,
            "save_container_count": len(containers),
            "save_type_counts": EXPECTED_SAVE_TYPE_COUNTS,
            "settings_payload_size": len(settings),
            "franchise_payload_size": len(franchise),
            "slider_field_count": 21,
            "settings_prefix_join_proved": True,
            "signature_owner_proved": True,
            "safe_writer_proved": False,
        },
        "containers": containers,
        "slider_snapshot": slider_snapshot,
        "executable_evidence": executable,
        "modding_boundary": {
            "read_only_slider_inspector_ready": True,
            "stock_range_writer_ready": False,
            "blocking_items": [
                "prove the exact settings/franchise serializer and load precedence",
                "perform controlled one-slider save deltas and runtime reload tests",
                "use the game's XCalculateSignature mode-0 owner or another authorized "
                "platform-backed signing path without extracting platform keys",
                "verify changed SAVEGAME.DAT and EXTRA together on a copied HDD image",
            ],
        },
    }


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _open_real_directory(path: Path, label: str) -> tuple[int, Path]:
    """Bind an existing directory without traversing any symlink component."""

    absolute = _absolute_lexical(path)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open(absolute.anchor, flags)
    try:
        for component in absolute.parts[1:]:
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except OSError as exc:
                raise SaveInventoryError(
                    f"{label} parent must be an existing real directory: {absolute}"
                ) from exc
            os.close(descriptor)
            descriptor = child
        opened = os.fstat(descriptor)
        require(stat.S_ISDIR(opened.st_mode), f"{label} parent is not a directory")
        return descriptor, absolute
    except BaseException:
        os.close(descriptor)
        raise


def _write_descriptor(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        require(written > 0, "report output write made no progress")
        view = view[written:]
    os.fsync(descriptor)


def write_outputs(
    outputs: tuple[tuple[Path, bytes, str], ...], protected: set[Path]
) -> None:
    """Publish all outputs exclusively, removing only partials we created."""

    require(len(outputs) == 3, "exactly three report outputs are required")
    protected_paths = {_absolute_lexical(path) for path in protected}
    records: list[dict[str, Any]] = []
    success = False
    try:
        for path, payload, label in outputs:
            absolute = _absolute_lexical(path)
            require(
                absolute not in protected_paths,
                f"{label} output overlaps a protected input",
            )
            require(absolute.name not in {"", ".", ".."}, f"{label} output name is invalid")
            parent_fd, parent_path = _open_real_directory(absolute.parent, label)
            parent_stat = os.fstat(parent_fd)
            records.append(
                {
                    "path": absolute,
                    "parent_path": parent_path,
                    "parent_fd": parent_fd,
                    "parent_identity": (parent_stat.st_dev, parent_stat.st_ino),
                    "name": absolute.name,
                    "payload": payload,
                    "label": label,
                    "fd": None,
                    "identity": None,
                }
            )

        identities = [
            (*record["parent_identity"], record["name"]) for record in records
        ]
        require(
            len(set(identities)) == len(identities),
            "report outputs must be three distinct real paths",
        )

        output_flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        for record in records:
            try:
                descriptor = os.open(
                    record["name"],
                    output_flags,
                    0o600,
                    dir_fd=record["parent_fd"],
                )
            except OSError as exc:
                raise SaveInventoryError(
                    f"{record['label']} output must be absent and cannot be a link: "
                    f"{record['path']}"
                ) from exc
            record["fd"] = descriptor
            opened = os.fstat(descriptor)
            record["identity"] = (opened.st_dev, opened.st_ino)
            os.fchmod(descriptor, 0o600)
            opened = os.fstat(descriptor)
            require(
                stat.S_ISREG(opened.st_mode)
                and opened.st_nlink == 1
                and stat.S_IMODE(opened.st_mode) == 0o600,
                f"{record['label']} output is not a private single-link regular file",
            )

        for record in records:
            _write_descriptor(record["fd"], record["payload"])
            after = os.fstat(record["fd"])
            at_path = os.stat(
                record["name"], dir_fd=record["parent_fd"], follow_symlinks=False
            )
            require(
                stat.S_ISREG(after.st_mode)
                and after.st_nlink == 1
                and stat.S_IMODE(after.st_mode) == 0o600
                and after.st_size == len(record["payload"])
                and (after.st_dev, after.st_ino) == record["identity"]
                and (at_path.st_dev, at_path.st_ino) == record["identity"],
                f"{record['label']} output changed during publication",
            )
        success = True
    finally:
        for record in records:
            descriptor = record.get("fd")
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                record["fd"] = None
        if not success:
            for record in records:
                identity = record.get("identity")
                if identity is None:
                    continue
                try:
                    current = os.stat(
                        record["name"],
                        dir_fd=record["parent_fd"],
                        follow_symlinks=False,
                    )
                    if (current.st_dev, current.st_ino) == identity:
                        os.unlink(record["name"], dir_fd=record["parent_fd"])
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
        for record in records:
            try:
                os.close(record["parent_fd"])
            except OSError:
                pass


def inventory_tsv(report: dict[str, Any]) -> bytes:
    stream = io.StringIO(newline="")
    fields = (
        "directory_id", "display_name", "type", "savegame_size",
        "savegame_sha256", "extra_size", "extra_sha256", "first_cluster"
    )
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t",
                            lineterminator="\n")
    writer.writeheader()
    for row in report["containers"]:
        writer.writerow({
            "directory_id": row["directory_id"],
            "display_name": row["display_name"],
            "type": row["type"],
            "savegame_size": row["files"]["SAVEGAME.DAT"]["file_size"],
            "savegame_sha256": row["files"]["SAVEGAME.DAT"]["sha256"],
            "extra_size": row["files"]["EXTRA"]["file_size"],
            "extra_sha256": row["files"]["EXTRA"]["sha256"],
            "first_cluster": row["directory"]["first_cluster"],
        })
    return stream.getvalue().encode("utf-8")


def slider_tsv(report: dict[str, Any]) -> bytes:
    stream = io.StringIO(newline="")
    fields = (
        "physical_index", "semantic_index", "label", "group", "offset",
        "settings1", "franchise1"
    )
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t",
                            lineterminator="\n")
    writer.writeheader()
    writer.writerows(report["slider_snapshot"]["rows"])
    return stream.getvalue().encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument(
        "--expected-image-sha256", type=sha256_argument, required=True
    )
    parser.add_argument("--xbe", type=Path, default=DEFAULT_XBE)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--inventory-tsv-out", type=Path,
                        default=DEFAULT_INVENTORY_TSV)
    parser.add_argument("--slider-tsv-out", type=Path, default=DEFAULT_SLIDER_TSV)
    args = parser.parse_args()

    report = build_report(
        args.image, args.expected_image_sha256, args.xbe, args.ledger
    )
    protected = {args.image, args.xbe, args.ledger}
    write_outputs(
        (
            (args.json_out, canonical_json(report), "JSON report"),
            (args.inventory_tsv_out, inventory_tsv(report), "inventory TSV"),
            (args.slider_tsv_out, slider_tsv(report), "slider TSV"),
        ),
        protected,
    )
    print(
        "NFL2K5_XBOX_SAVE_INVENTORY_OK "
        f"containers={report['summary']['save_container_count']} "
        f"sliders={report['summary']['slider_field_count']} "
        "signature_owner=true writer=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
