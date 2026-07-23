#!/usr/bin/env python3
"""Build a hash-pinned NFL 2K5 roster-portrait compatibility inventory."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
from typing import Any
import zlib

from nfl_outer import Entry, parse_archive, read_entry_bytes, read_entry_range
from nfl_txtr import (HEADER, decode_chunk, parse_chunks, parse_texture,
                      texture_to_rgba)
import nfl_uniform_color_xiso_direct_patch as xiso
from xbe_info import Xbe


SCHEMA = "nfl2k5_player_portrait_compatibility/v1"
ROOT = Path(__file__).resolve().parents[1]
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
TXTR_SHA256 = "5295168a4596b7be273e534b36efd2b53f44c7ed5f16893110a63413397f4929"
ROSTER_SHA256 = "3b25fee38f2a812f05b7c0815889153d871cd33bc97cd50257871138b4ab9972"
XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
PACK_SHA256 = {
    "3": "921a139a9fd1a9470cc77f78455a6282e426376d4c201635b97a512d1f947aa7",
    "4": "94e6f16dc53fe6e06a6357ecd23879244e6dd1854bd1b222e3a985f4611bf487",
    "C": "ce3af83768640230499f10d1d0a9799fc9ea56809a8a8a788679c78744f54090",
}
CACR_OUTER = 10
PORTRAIT_OUTER = 3105
FALLBACK_OUTER = 3
RESOURCE_COUNT = 4937
PORTRAIT_COUNT = 4303
HELM_CARD_COUNT = 634
SLOT_SIZE = 17664
SPAN_SIZE = 17568
STORED_SIZE = 17536
SYSTEM_BYTES = 128
VIDEO_BYTES = 17408
PALETTE_OFFSET = 16384
PACKED_FORMAT = 0x07710B29
PORTRAIT_NAME = re.compile(r"^\d{4}$")
HELM_CARD_NAME = re.compile(r"^helm_[ha]\d\d_\d+$")


class PortraitError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PortraitError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def pin(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    return {"path": str(resolved), "size": resolved.stat().st_size,
            "sha256": file_digest(resolved)}


def locate_range(entry: Entry, offset: int, size: int) -> list[dict[str, Any]]:
    require(offset >= 0 and size > 0 and offset + size <= entry.size,
            "range exceeds outer entry")
    result: list[dict[str, Any]] = []
    relative = offset
    remaining = size
    for segment in entry.segments:
        if relative >= segment.size:
            relative -= segment.size
            continue
        take = min(remaining, segment.size - relative)
        result.append({
            "pack_name": segment.pack_name,
            "pack_ordinal": segment.pack_ordinal,
            "pack_offset": segment.pack_offset + relative,
            "size": take,
        })
        remaining -= take
        relative = 0
        if remaining == 0:
            break
    require(remaining == 0, "range-to-pack mapping is incomplete")
    return result


def crc_name(value: str) -> int:
    return zlib.crc32(value.lower().encode("utf-16le")) & 0xFFFFFFFF


def validate_xbe(path: Path) -> dict[str, Any]:
    require(file_digest(path) == XBE_SHA256, "default.xbe SHA-256 mismatch")
    image = Xbe(path)

    strings = {
        "context": (0x00E6A3A0, "PORTRAIT"),
        "archive": (0x00E6A3B4, "Portrait.iff"),
        "selector_format": (0x00E6A3D0, "%04d"),
        "fallback": (0x00E6A3DC, "nophoto"),
        "wrapup_material": (0x00E80CFC, "WRAPUP_PORTRAIT"),
        "player_photo_material": (0x00E62C50, "z_playerPhoto"),
        "crib_name_variant_format": (0x00E8ED30, "%s_%02d"),
        "crib_team_name_format": (0x00E8ED40, "%02u_%s"),
        "crib_team_name_variant_format": (0x00E8ED50, "%02u_%s_%02d"),
        "crib_team_photo_scene": (0x00E8F83C, "team_photo"),
        "crib_team_photo_texture_base": (0x00E8F854, "photo"),
        "crib_team_photo_secondary_texture": (0x00E8F860, "cjersey"),
    }
    resolved: dict[str, Any] = {}
    for key, (address, expected) in strings.items():
        actual = image.utf16z_va(address)
        require(actual == expected, f"XBE portrait string changed at 0x{address:08x}")
        resolved[key] = {"address": f"0x{address:08x}", "value": actual}

    ranges = {
        "portrait_context_registration": (
            0x000E7140, 30,
            "74db638f31cca051c16a4ca7cecf6f44de4e8d3980672f3e6bf9906227bab51a"),
        "player_portrait_lookup": (
            0x000E7170, 104,
            "6763f2e35fd350f267dfd560f9ccc75ceb82ba5fed070d35c066c07dae199731"),
        "alternate_record_portrait_lookup": (
            0x000E71E0, 93,
            "9577c623ec5493b2adb22dccd34c92ebc6882d35cf3ed9cb49169fa9446034bc"),
        "wrapup_portrait_material_binder": (
            0x0015EF00, 235,
            "33418ba72c1ead20d390102734cdfae0dadf87d9e9a648fc0f887a7c4476cf71"),
        "wrapup_single_portrait_binder": (
            0x0015F020, 94,
            "63627aff477576d21d8d7d41490453fbd0438d3a49fbcb777eba47b50b5ad8f5"),
        "direct_portrait_material_writer": (
            0x0015F0B0, 44,
            "d8724902830ade51321bb48578705d332292789c0c1ed9d7cbedc16031cf07b0"),
        "crib_item_texture_lookup": (
            0x0026F4A0, 196,
            "985dc17739756114bdb1f2c441bbbfa8b29e877b24ced9f82c77d00a9222a749"),
        "crib_team_photo_catalog_row": (
            0x0051A1A8, 16,
            "48979d2ea2b39ba43aa27ee173ba93113acfee118cd180cf8d8b7f708cf77355"),
    }
    code: dict[str, Any] = {}
    for key, (address, size, expected) in ranges.items():
        offset = image.va_to_offset(address, size)
        payload = image.data[offset:offset + size]
        require(digest(payload) == expected, f"XBE portrait range {key} changed")
        code[key] = {"start": f"0x{address:08x}", "size": size,
                     "end_exclusive": f"0x{address + size:08x}",
                     "sha256": expected}

    player = image.data[image.va_to_offset(0x000E7170, 104):
                        image.va_to_offset(0x000E7170, 104) + 104]
    alternate = image.data[image.va_to_offset(0x000E71E0, 93):
                           image.va_to_offset(0x000E71E0, 93) + 93]
    require(b"\x0f\xb7\x42\x06" in player and
            b"\x0f\xb7\x42\x40" in alternate and
            struct.pack("<I", 0x52545854) in player and
            struct.pack("<I", 0x00E6A3DC) in player,
            "portrait selector/fallback instruction anchors changed")
    crib_offset = image.va_to_offset(0x0026F4A0, 196)
    crib = image.data[crib_offset:crib_offset + 196]
    require(struct.pack("<I", 0x00E8ED30) in crib and
            struct.pack("<I", 0x00E8ED40) in crib and
            struct.pack("<I", 0x00E8ED50) in crib and
            struct.pack("<I", 0x52545854) in crib and
            struct.unpack("<4I", image.data[image.va_to_offset(0x0051A1A8, 16):
                                           image.va_to_offset(0x0051A1A8, 16) + 16]) ==
            (0x00E8F83C, 0x00E8F854, 0x00E8F860, 0x00030201),
            "Crib Team Photo lookup/catalog anchors changed")
    return {
        "strings": resolved,
        "code_ranges": code,
        "player_record_selector_offset": "0x06",
        "player_record_selector_load": "MOVZX EAX,word ptr [EDX+0x06] at 0x000E7181",
        "selector_format_call": "0x000E7197 CALL 0x0004A400 with %04d",
        "resource_kind": "TXTR (0x52545854)",
        "fallback_branches": ["0x000E71B6", "0x000E721B"],
        "ui_material_binding": {
            "material_name": "WRAPUP_PORTRAIT",
            "texture_pointer_store": "material +0x30",
            "visibility_bit": "material +0x08 bit0",
        },
        "crib_team_photo_binding": {
            "classification": "Crib Team Photo object, not a roster portrait",
            "catalog_row_address": "0x0051A1A8",
            "catalog_row_index_from_0x00519F68": 36,
            "catalog_row_words": ["0x00e8f83c", "0x00e8f854",
                                  "0x00e8f860", "0x00030201"],
            "scene_name": "team_photo", "primary_texture_base": "photo",
            "secondary_texture_base": "cjersey",
            "lookup_function": "0x0026F4A0",
            "team_variant_format": "%02u_%s_%02d",
            "result_example": "00_photo_00",
            "resource_kind": "TXTR (0x52545854)",
        },
    }


def roster_rows(path: Path, portrait_names: set[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    require(file_digest(path) == ROSTER_SHA256, "roster-player TSV SHA-256 mismatch")
    result: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    require(len(rows) == 6522, "roster-player row count changed")
    for row in rows:
        raw = bytes.fromhex(row["raw_hex"])
        require(len(raw) == 84, "roster player record size changed")
        portrait_id = struct.unpack_from("<H", raw, 6)[0]
        resource_name = f"{portrait_id:04d}"
        available = resource_name in portrait_names
        result.append({
            "outer_index": int(row["outer_index"]),
            "outer_id": row["outer_id"],
            "resource_label": row["resource_label"],
            "pool": row["pool"],
            "player_index": int(row["player_index"]),
            "record_offset": row["record_offset"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "team_indices": row["team_indices"],
            "team_names": row["team_names"],
            "portrait_id_u16_at_plus_0x06": portrait_id,
            "portrait_resource_name": resource_name,
            "selector": f"portrait:{resource_name}",
            "portrait_present": available,
            "falls_back_to_nophoto": not available,
        })
    current = [row for row in result if row["outer_index"] == 5 and
               row["resource_label"] == "roster"]
    require(len(current) == 2547 and sum(row["portrait_present"] for row in current) == 2248,
            "current-roster portrait coverage changed")
    require(sum(row["portrait_present"] for row in result) == 2892,
            "all-roster portrait coverage changed")
    return result, {
        "all_roster_record_count": len(result),
        "all_roster_distinct_selector_count": len({row["portrait_resource_name"] for row in result}),
        "all_roster_portrait_hit_count": sum(row["portrait_present"] for row in result),
        "all_roster_fallback_count": sum(row["falls_back_to_nophoto"] for row in result),
        "current_roster_record_count": len(current),
        "current_roster_distinct_selector_count": len({row["portrait_resource_name"] for row in current}),
        "current_roster_portrait_hit_count": sum(row["portrait_present"] for row in current),
        "current_roster_fallback_count": sum(row["falls_back_to_nophoto"] for row in current),
    }


def run(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    index_path = root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
    txtr_path = root / "reports/assets/nfl2k5_all_txtr_inventory_v2.json"
    roster_path = root / "reports/assets/nfl2k5_roster_players.tsv"
    xbe_path = root / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
    source_path = root / "ESPN NFL 2K5 (USA).xiso.iso"
    require(file_digest(index_path) == INDEX_SHA256, "canonical index SHA-256 mismatch")
    require(file_digest(txtr_path) == TXTR_SHA256, "TXTR inventory SHA-256 mismatch")
    xbe_evidence = validate_xbe(xbe_path)
    archive = parse_archive(index_path)
    require(len(archive.entries) == 4323, "outer entry count changed")
    for name, expected in PACK_SHA256.items():
        pack = next(item for item in archive.packs if item.name == name)
        require(file_digest(pack.path) == expected, f"extracted pack {name} changed")

    txtr = json.loads(txtr_path.read_bytes())
    require(txtr.get("schema") == "nfl2k5_all_txtr_inventory/v1",
            "TXTR inventory schema changed")
    rows = [row for row in txtr["textures"]
            if int(row["outer_index"]) == PORTRAIT_OUTER]
    rows.sort(key=lambda row: int(row["chunk_index"]))
    require(len(rows) == RESOURCE_COUNT and
            [int(row["chunk_index"]) for row in rows] == list(range(RESOURCE_COUNT)),
            "portrait aggregate chunk coverage changed")
    portrait_rows = [row for row in rows if PORTRAIT_NAME.fullmatch(str(row["name"]))]
    helm_rows = [row for row in rows if HELM_CARD_NAME.fullmatch(str(row["name"]))]
    require(len(portrait_rows) == PORTRAIT_COUNT and len(helm_rows) == HELM_CARD_COUNT and
            len(portrait_rows) + len(helm_rows) == len(rows),
            "portrait/Team Select resource split changed")
    names = [str(row["name"]) for row in rows]
    name_hashes = [crc_name(name) for name in names]
    require(len(set(names)) == RESOURCE_COUNT and len(set(name_hashes)) == RESOURCE_COUNT and
            all(left < right for left, right in zip(name_hashes, name_hashes[1:])),
            "portrait aggregate resource hash ordering changed")

    cacr_entry = archive.entries[CACR_OUTER]
    cacr = read_entry_bytes(archive, cacr_entry, max_size=65536)
    require(cacr_entry.name_id == 0x3E59669F and cacr_entry.size == 19872 and
            cacr[:4] == b"CACR" and struct.unpack_from("<I", cacr, 4)[0] == 19840 and
            cacr[0x20:0x38].decode("utf-16le").rstrip("\0") == "portrait.cdf" and
            struct.unpack_from("<I", cacr, 0x60)[0] == RESOURCE_COUNT and
            struct.unpack_from("<I", cacr, 0x64)[0] == 0x4500 and
            list(struct.unpack_from(f"<{RESOURCE_COUNT}I", cacr, 0x68)) == name_hashes and
            cacr[0x68 + RESOURCE_COUNT * 4:] == bytes(20),
            "Portrait CACR name index changed")
    require(zlib.crc32("Portrait.iff".upper().encode("utf-16le")) & 0xFFFFFFFF ==
            cacr_entry.name_id, "Portrait.iff outer-ID derivation changed")

    portrait_entry = archive.entries[PORTRAIT_OUTER]
    require(portrait_entry.name_id == 0x35CB8D72 and portrait_entry.size == 87207168 and
            len(portrait_entry.segments) == 2 and
            [segment.pack_name for segment in portrait_entry.segments] == ["3", "4"] and
            [segment.size for segment in portrait_entry.segments] == [71424000, 15783168],
            "portrait TXTR aggregate identity/segments changed")

    source_lstat = source_path.lstat()
    require(stat.S_ISREG(source_lstat.st_mode) and not stat.S_ISLNK(source_lstat.st_mode),
            "source XISO must be a non-symlink regular file")
    source = source_path.resolve(strict=True)
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(source_fd)
        require((opened.st_dev, opened.st_ino, opened.st_size) ==
                (source_lstat.st_dev, source_lstat.st_ino, xiso.EXPECTED_XISO_SIZE),
                "source XISO identity/size changed")
        require(xiso.sha256_fd(source_fd) == xiso.EXPECTED_XISO_SHA256,
                "source XISO SHA-256 mismatch")
        xdvdfs, _ = xiso.parse_xdvdfs(source_fd, opened.st_size)
        pack_records: dict[str, Any] = {}
        for name, expected in PACK_SHA256.items():
            record = xdvdfs.get(f"vc_53450030/{name}".casefold())
            require(record is not None and record.size ==
                    next(pack.size for pack in archive.packs if pack.name == name) and
                    xiso.sha256_fd(source_fd, record.byte_offset, record.size) == expected,
                    f"source-XISO pack {name} identity changed")
            assert record is not None
            pack_records[name] = {
                "path": f"vc_53450030/{name}", "sector": record.sector,
                "byte_offset": record.byte_offset, "size": record.size,
                "sha256": expected,
            }

        targets: list[dict[str, Any]] = []
        cross_pack_count = 0
        for row in rows:
            index = int(row["chunk_index"])
            name = str(row["name"])
            require(int(row["chunk_offset"]) == index * SLOT_SIZE and
                    int(row["stored_size"]) == STORED_SIZE and
                    int(row["system_bytes"]) == SYSTEM_BYTES and
                    int(row["video_bytes"]) == VIDEO_BYTES and
                    row["compressed"] is False and row["format_name"] == "P8" and
                    int(row["width"]) == 128 and int(row["height"]) == 128 and
                    int(row["mip_levels"]) == 1 and
                    int(row["palette_offset"]) == PALETTE_OFFSET and
                    int(str(row["packed_format"]), 0) == PACKED_FORMAT and
                    int(row["descriptor_offset"]) ==
                    ((32 + (len(name) + 1) * 2 + 3) & ~3),
                    f"portrait aggregate row {index} layout changed")
            span = read_entry_range(archive, portrait_entry, index * SLOT_SIZE, SPAN_SIZE)
            padding = read_entry_range(
                archive, portrait_entry, index * SLOT_SIZE + SPAN_SIZE,
                SLOT_SIZE - SPAN_SIZE)
            require(padding == bytes(96), f"portrait slot {index} padding changed")
            chunks = parse_chunks(span)
            require(len(chunks) == 1 and chunks[0].offset == 0 and
                    chunks[0].kind == "TXTR" and not chunks[0].compressed and
                    chunks[0].stored_size == STORED_SIZE and
                    chunks[0].system_bytes == SYSTEM_BYTES and
                    chunks[0].video_bytes == VIDEO_BYTES,
                    f"portrait slot {index} wrapper changed")
            decoded, decode_info = decode_chunk(span, chunks[0])
            texture = parse_texture(decoded, chunks[0])
            rgba = texture_to_rgba(decoded, chunks[0], texture)
            require(decode_info is None and texture.name == name and
                    texture.pixel_offset == 0 and texture.palette_offset == PALETTE_OFFSET and
                    texture.packed_format == PACKED_FORMAT and texture.packed_size == 0 and
                    texture.descriptor_flags == 0x80000000 and
                    texture.width == texture.height == 128 and texture.depth == 1 and
                    digest(decoded) == row["decoded_sha256"] and
                    digest(rgba) == row["rgba_sha256"],
                    f"portrait slot {index} decoded identity changed")
            segments = locate_range(portrait_entry, index * SLOT_SIZE, SPAN_SIZE)
            xiso_segments: list[dict[str, Any]] = []
            cursor = 0
            for segment in segments:
                pack = pack_records[str(segment["pack_name"])]
                absolute = int(pack["byte_offset"]) + int(segment["pack_offset"])
                piece = span[cursor:cursor + int(segment["size"])]
                require(os.pread(source_fd, len(piece), absolute) == piece,
                        f"portrait slot {index} differs in source XISO")
                xiso_segments.append({**segment,
                    "pack_path": pack["path"], "pack_sector": pack["sector"],
                    "pack_size": pack["size"], "pack_sha256": pack["sha256"],
                    "span_relative_offset": cursor,
                    "xiso_absolute_offset": absolute,
                })
                cursor += len(piece)
            require(cursor == SPAN_SIZE, "portrait XISO segment coverage changed")
            if len(xiso_segments) > 1:
                cross_pack_count += 1
            if PORTRAIT_NAME.fullmatch(name):
                targets.append({
                    "selector": f"portrait:{name}", "portrait_id": int(name),
                    "name": name, "outer_index": PORTRAIT_OUTER,
                    "outer_id": "0x35cb8d72", "outer_size": portrait_entry.size,
                    "chunk_index": index, "chunk_offset": index * SLOT_SIZE,
                    "slot_size": SLOT_SIZE, "span_size": SPAN_SIZE,
                    "stored_size": STORED_SIZE, "system_bytes": SYSTEM_BYTES,
                    "video_bytes": VIDEO_BYTES,
                    "name_offset": texture.name_offset,
                    "descriptor_offset": texture.descriptor_offset,
                    "pixel_offset": texture.pixel_offset,
                    "palette_offset": texture.palette_offset,
                    "packed_format": f"0x{texture.packed_format:08x}",
                    "span_sha256": digest(span), "decoded_sha256": digest(decoded),
                    "rgba_sha256": digest(rgba), "post_span_padding_bytes": 96,
                    "post_span_padding_sha256": digest(padding),
                    "span_segments": xiso_segments,
                })
    finally:
        os.close(source_fd)

    require(len(targets) == PORTRAIT_COUNT and cross_pack_count == 1 and
            [target["name"] for target in targets if len(target["span_segments"]) == 2] ==
            ["4070"], "portrait target/cross-pack coverage changed")
    target_names = {target["name"] for target in targets}
    roster, roster_summary = roster_rows(roster_path, target_names)

    fallback = next(row for row in txtr["textures"] if row["name"] == "nophoto")
    require(int(fallback["outer_index"]) == FALLBACK_OUTER and
            fallback["format_name"] == "P8" and int(fallback["width"]) == 128 and
            int(fallback["height"]) == 128 and fallback["compressed"] is True,
            "nophoto fallback identity changed")
    action_photos = [row for row in txtr["textures"] if
                     re.fullmatch(r"\d\d_photo_\d\d?", str(row["name"]))]
    live_face_ids = {str(row["name"])[1:] for row in txtr["textures"]
                     if re.fullmatch(r"f\d{4}", str(row["name"]))}
    require(len(action_photos) == 128 and
            {int(row["outer_index"]) for row in action_photos} == {4274} and
            {str(row["name"])[:2] for row in action_photos} ==
            {f"{value:02d}" for value in range(31)} | {"37"} and
            {str(row["name"])[-2:] for row in action_photos} ==
            {"00", "01", "02", "03"} and
            len(live_face_ids) == 624,
            "portrait/action-photo/live-face distinction changed")
    action_entry = archive.entries[4274]
    require(action_entry.name_id == 0xD8B625DA and action_entry.size == 5_575_680 and
            len(action_entry.segments) == 1 and
            action_entry.segments[0].pack_name == "C" and
            action_entry.segments[0].pack_offset == 180_467_712 and
            action_entry.segments[0].size == action_entry.size,
            "Crib Team Photo aggregate identity changed")
    action_records: list[dict[str, Any]] = []
    action_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0))
    try:
        for row in sorted(action_photos, key=lambda item: int(item["chunk_index"])):
            index = int(row["chunk_index"])
            require(int(row["chunk_offset"]) == index * 23_040 and
                    int(row["stored_size"]) == 22_976 and
                    int(row["system_bytes"]) == 128 and
                    int(row["video_bytes"]) == 22_848 and
                    row["compressed"] is False and row["format_name"] == "P8" and
                    int(row["width"]) == int(row["height"]) == 128 and
                    int(row["mip_levels"]) == 5 and
                    int(row["palette_offset"]) == 21_824 and
                    int(str(row["packed_format"]), 0) == 0x07750B29 and
                    int(row["descriptor_offset"]) == 56,
                    f"Crib Team Photo row {index} layout changed")
            span = read_entry_range(archive, action_entry, index * 23_040, 23_008)
            padding = read_entry_range(archive, action_entry,
                                       index * 23_040 + 23_008, 32)
            chunks = parse_chunks(span)
            require(len(chunks) == 1 and chunks[0].kind == "TXTR" and
                    chunks[0].stored_size == 22_976 and not chunks[0].compressed and
                    padding == bytes(32),
                    f"Crib Team Photo row {index} wrapper/padding changed")
            decoded, info = decode_chunk(span, chunks[0])
            texture = parse_texture(decoded, chunks[0])
            rgba = texture_to_rgba(decoded, chunks[0], texture)
            require(info is None and texture.name == row["name"] and
                    texture.mip_levels == 5 and texture.palette_offset == 21_824 and
                    digest(decoded) == row["decoded_sha256"] and
                    digest(rgba) == row["rgba_sha256"],
                    f"Crib Team Photo row {index} decode changed")
            relative_pack = action_entry.segments[0].pack_offset + index * 23_040
            absolute = int(pack_records["C"]["byte_offset"]) + relative_pack
            require(os.pread(action_fd, len(span), absolute) == span,
                    f"Crib Team Photo row {index} differs in source XISO")
            action_records.append({
                "selector": f"crib_team_photo:{row['name']}", "name": row["name"],
                "asset_code": str(row["name"])[:2],
                "variant": int(str(row["name"])[-2:]),
                "outer_index": 4274, "outer_id": "0xd8b625da",
                "outer_size": action_entry.size, "chunk_index": index,
                "chunk_offset": index * 23_040, "slot_size": 23_040,
                "span_size": 23_008, "stored_size": 22_976,
                "system_bytes": 128, "video_bytes": 22_848,
                "mip_levels": 5, "mip_dimensions": [128, 64, 32, 16, 8],
                "mip_index_bytes": [16_384, 4_096, 1_024, 256, 64],
                "palette_offset": 21_824, "palette_bytes": 1_024,
                "packed_format": "0x07750b29", "span_sha256": digest(span),
                "decoded_sha256": digest(decoded), "rgba_sha256": digest(rgba),
                "post_span_zero_padding": 32, "pack_path": "vc_53450030/C",
                "pack_offset": relative_pack, "xiso_absolute_span_offset": absolute,
            })
    finally:
        os.close(action_fd)
    require(len(action_records) == 128, "Crib Team Photo record coverage changed")

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "inputs": {
            "canonical_index": pin(index_path), "txtr_inventory": pin(txtr_path),
            "roster_players": pin(roster_path), "default_xbe": pin(xbe_path),
            "retail_xiso": {"path": str(source), "size": xiso.EXPECTED_XISO_SIZE,
                            "sha256": xiso.EXPECTED_XISO_SHA256,
                            "opened_read_only": True},
            "packs": pack_records,
        },
        "summary": {
            "aggregate_resource_count": RESOURCE_COUNT,
            "numeric_portrait_count": len(targets),
            "team_select_helmet_card_count": len(helm_rows),
            "fixed_slot_count": RESOURCE_COUNT,
            "cross_pack_span_count": cross_pack_count,
            "cross_pack_resource_name": "4070",
            "unique_portrait_rgba_count": len({target["rgba_sha256"] for target in targets}),
            "portrait_ids_with_live_f_texture": len(target_names & live_face_ids),
            "portrait_ids_without_live_f_texture": len(target_names - live_face_ids),
            **roster_summary,
            "all_source_xiso_spans_match": True,
            "all_filename_hashes_match_cacr": True,
        },
        "layout_contract": {
            "format": "P8", "width": 128, "height": 128, "mip_levels": 1,
            "compression": "raw", "slot_size": SLOT_SIZE, "span_size": SPAN_SIZE,
            "wrapper_bytes": HEADER.size, "stored_size": STORED_SIZE,
            "system_bytes": SYSTEM_BYTES, "video_bytes": VIDEO_BYTES,
            "swizzled_index_bytes": PALETTE_OFFSET,
            "palette_bytes": VIDEO_BYTES - PALETTE_OFFSET,
            "palette_encoding": "256 BGRA8 entries",
            "post_span_zero_padding": SLOT_SIZE - SPAN_SIZE,
            "pixel_storage": "Xbox P8 Morton-swizzled 2D indices",
            "fixed_allocation_per_resource": True,
        },
        "portrait_cacr": {
            "outer_index": CACR_OUTER, "outer_id": "0x3e59669f",
            "outer_size": cacr_entry.size, "resource_name": "portrait.cdf",
            "runtime_filename": "Portrait.iff", "entry_count": RESOURCE_COUNT,
            "unknown_word_at_0x64": "0x00004500",
            "hash_algorithm": "CRC32(case-preserved/lowercase UTF-16LE resource name)",
            "hashes_sorted_strictly_ascending": True,
            "hash_list_exactly_matches_aggregate_names": True,
            "trailing_zero_bytes": 20,
        },
        "aggregate": {
            "outer_index": PORTRAIT_OUTER, "outer_id": "0x35cb8d72",
            "outer_size": portrait_entry.size,
            "logical_filename": None,
            "logical_filename_status": "not recovered; identity is outer index/ID plus CACR join",
            "segments": [{"pack_name": segment.pack_name,
                          "pack_offset": segment.pack_offset, "size": segment.size}
                         for segment in portrait_entry.segments],
        },
        "xbe_runtime_binding": xbe_evidence,
        "fallback": {**fallback,
                     "classification": "global nophoto TXTR used when numeric lookup misses"},
        "asset_family_distinction": {
            "numeric_roster_portraits": len(targets),
            "action_photo_names_like_00_photo_00": len(action_photos),
            "action_photo_outer_index": 4274,
            "action_photo_asset_codes": 32,
            "action_photo_variants_per_asset_code": 4,
            "action_photo_classification": "Crib Team Photo action art; not roster headshots",
            "action_photo_xbe_owner": "0x0026F4A0 plus catalog row 0x0051A1A8",
            "live_f_texture_ids": len(live_face_ids),
            "portrait_and_live_f_id_intersection": len(target_names & live_face_ids),
            "portrait_is_not_live_3d_face_texture": True,
        },
        "crib_action_photo_contract": {
            "outer_index": 4274, "outer_id": "0xd8b625da",
            "outer_size": action_entry.size, "resource_count": len(action_records),
            "format": "P8", "width": 128, "height": 128, "mip_levels": 5,
            "mip_dimensions": [128, 64, 32, 16, 8],
            "mip_index_bytes": [16_384, 4_096, 1_024, 256, 64],
            "palette_offset": 21_824, "palette_bytes": 1_024,
            "compression": "raw", "slot_size": 23_040, "span_size": 23_008,
            "stored_size": 22_976, "system_bytes": 128, "video_bytes": 22_848,
            "post_span_zero_padding": 32,
            "all_source_xiso_spans_match": True,
            "png_import_implemented": False,
            "portme": "PORTME(Crib Team Photo): implement five-mip P8 regeneration before editing 00_photo_00-style action art.",
        },
        "crib_action_photo_resources": action_records,
        "targets": targets,
        "roster_selector_mapping": roster,
        "claims": {
            "actual_roster_menu_portrait_resources": True,
            "player_record_plus_0x06_selector_proved": True,
            "deterministic_fixed_span_png_import_feasible": True,
            "action_photo_family_modified": False,
            "live_3d_face_family_modified": False,
            "originals_modified": False, "xemu_started": False,
            "title_executed": False, "runtime_visibility_proved": False,
            "portme": [
                "PORTME(runtime): capture an edited roster/wrap-up portrait before claiming visibility.",
                "PORTME(aggregate-name): recover the logical filename for outer 3105 if required by new archive builders.",
                "PORTME(roster-authoring): expose record +0x06 in the public roster editor and validate fallback policy.",
            ],
        },
    }
    return report, targets


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "selector", "portrait_id", "name", "outer_index", "outer_id", "outer_size",
        "chunk_index", "chunk_offset", "slot_size", "span_size", "stored_size",
        "system_bytes", "video_bytes", "name_offset", "descriptor_offset",
        "pixel_offset", "palette_offset", "packed_format", "span_sha256",
        "decoded_sha256", "rgba_sha256", "segment_count", "segment_description",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            segments = row["span_segments"]
            writer.writerow({**{field: row.get(field, "") for field in fields},
                "segment_count": len(segments),
                "segment_description": ";".join(
                    f"{item['pack_name']}@{item['pack_offset']}+{item['size']}"
                    for item in segments),
            })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", type=Path,
                        default=ROOT / "reports/assets/nfl2k5_player_portrait_compatibility.json")
    parser.add_argument("--tsv", type=Path,
                        default=ROOT / "reports/assets/nfl2k5_player_portrait_compatibility.tsv")
    args = parser.parse_args()
    try:
        report, targets = run(args.root.resolve(strict=True))
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        write_tsv(args.tsv, targets)
    except (OSError, ValueError, KeyError, struct.error, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "schema": report["schema"], "portraits": len(targets),
        "current_roster_hits": report["summary"]["current_roster_portrait_hit_count"],
        "cross_pack": report["summary"]["cross_pack_span_count"],
        "runtime_visibility_proved": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
