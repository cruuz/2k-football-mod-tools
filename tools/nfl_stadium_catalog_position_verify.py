#!/usr/bin/env python3
"""Independently verify a catalog-backed NFL 2K5 stadium position patch.

This verifier is standard-library-only and intentionally imports neither the
writer nor its project parsers/codecs.  It independently parses the pinned
catalog/recipe/index, VC-LZ stream, SCNE shape pointers and copied-volume diff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import stat
import struct
from typing import Any


VERIFY_SCHEMA = "nfl2k5_catalog_static_position_verify/v2"
RECIPE_SCHEMA = "nfl2k5_catalog_static_position_recipe/v2"
PATCH_SCHEMA = "nfl2k5_catalog_static_position_patch/v2"
CATALOG_SCHEMA = "nfl2k5_stadium_static_target_catalog/v1"
CATALOG_SIZE = 858_600
CATALOG_SHA256 = "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa"
MAX_RECIPE_BYTES = 512 * 1024
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
CHUNK_ENTRY_OFFSET = 0x5EA40
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


class CatalogPositionVerifyError(ValueError):
    """Independent reconstruction found a contract violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CatalogPositionVerifyError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular(path: Path, label: str) -> Path:
    path = path.expanduser()
    try: info = path.lstat()
    except FileNotFoundError as exc:
        raise CatalogPositionVerifyError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def require_distinct_files(left: Path, right: Path) -> None:
    a, b = left.stat(), right.stat()
    require(left != right and (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino),
            "output volume path or inode aliases the retail source")


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}"); result[key] = value
    return result


def _load_json(path: Path, label: str, maximum: int) -> tuple[dict[str, Any], bytes]:
    path = regular(path, label); size = path.stat().st_size
    require(0 < size <= maximum, f"{label} size is outside its limit")
    payload = path.read_bytes(); require(len(payload) == size, f"{label} changed while reading")
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CatalogPositionVerifyError(f"non-finite JSON constant {token} is forbidden")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogPositionVerifyError(f"{label} is not UTF-8 JSON: {exc}") from exc
    require(isinstance(value, dict) and payload == canonical_json(value),
            f"{label} is not canonical sorted JSON")
    return value, payload


def load_catalog(path: Path) -> dict[str, Any]:
    value, payload = _load_json(path, "static-target catalog", CATALOG_SIZE)
    require(len(payload) == CATALOG_SIZE and sha256(payload) == CATALOG_SHA256
            and value.get("schema") == CATALOG_SCHEMA,
            "catalog differs from pinned authority")
    targets = value.get("targets")
    require(isinstance(targets, list) and len(targets) == 75, "catalog target count changed")
    by_id: dict[str, dict[str, Any]] = {}
    for row in targets:
        require(isinstance(row, dict) and type(row.get("target_id")) is str,
                "catalog target row invalid")
        require(row["target_id"] not in by_id, "catalog target_id duplicated")
        by_id[row["target_id"]] = row
    return {"value": value, "targets": by_id}


def _target_contract(row: dict[str, Any]) -> dict[str, int | str]:
    source, shape, position = row.get("source_identity"), row.get("shape"), row.get("position")
    require(isinstance(source, dict) and source.get("outer_index") == 3280
            and source.get("chunk_index") == 5 and source.get("scene_index") == 2648
            and source.get("scene_name") == "stadium"
            and source.get("decoded_sha256") == SOURCE_DECODED_SHA256,
            "target source identity changed")
    require(isinstance(shape, dict) and isinstance(position, dict), "target row incomplete")
    count = shape.get("vertex_count"); span = position.get("contiguous_decoded_span")
    require(type(count) is int and count > 0 and isinstance(span, dict), "target count/span invalid")
    offset, size, end = span.get("offset"), span.get("size"), span.get("end_offset")
    require(type(offset) is int and type(size) is int and type(end) is int
            and size == count * 12 and end == offset + size and end <= DECODED_SIZE,
            "target count/span mismatch")
    require(position.get("declaration") == {"byte_offset": 0, "byte_size": 12,
        "component_count": 3, "encoded": "0x00000032", "format_code": 50,
        "format_name": "FLOAT3", "register": 0, "stream_index": 0}
        and position.get("stream_stride") == 12,
        "target is not contiguous register-0 FLOAT3")
    require(row.get("eligibility", {}).get("mechanically_rigid_same_count_float3") is True,
            "target is not catalog-authorized")
    return {"offset": offset, "size": size, "end": end, "vertex_count": count,
            "shape_index": shape["index"], "shape_name": shape["name"]}


def _f32(value: object, label: str) -> float:
    require(type(value) in (int, float), f"{label} is not a JSON number")
    try: number = float(value)
    except OverflowError as exc: raise CatalogPositionVerifyError(f"{label} exceeds FLOAT32") from exc
    require(math.isfinite(number), f"{label} is non-finite")
    try: decoded = struct.unpack("<f", struct.pack("<f", number))[0]
    except (OverflowError, struct.error) as exc:
        raise CatalogPositionVerifyError(f"{label} exceeds FLOAT32") from exc
    require(number == decoded, f"{label} is not exactly binary32"); return decoded


def load_recipe(path: Path, catalog: dict[str, Any]) -> dict[str, Any]:
    value, payload = _load_json(path, "catalog position recipe", MAX_RECIPE_BYTES)
    require(set(value) == {"catalog", "positions", "schema", "target_id"}
            and value.get("schema") == RECIPE_SCHEMA, "recipe fields/schema changed")
    require(value.get("catalog") == {"schema": CATALOG_SCHEMA, "sha256": CATALOG_SHA256},
            "recipe catalog pin changed")
    target_id = value.get("target_id")
    require(type(target_id) is str and target_id in catalog["targets"],
            "recipe target_id is not authorized")
    row = catalog["targets"][target_id]; contract = _target_contract(row)
    rows = value.get("positions"); count = int(contract["vertex_count"])
    require(isinstance(rows, list) and len(rows) == count,
            f"recipe must contain exactly {count} positions")
    packed = bytearray()
    for vertex, xyz in enumerate(rows):
        require(isinstance(xyz, list) and len(xyz) == 3, f"positions[{vertex}] is not XYZ")
        packed.extend(struct.pack("<3f", *(_f32(v, f"positions[{vertex}]") for v in xyz)))
    return {"sha256": sha256(payload), "target_id": target_id, "row": row,
            "contract": contract, "packed": bytes(packed)}


def _read(path: Path, offset: int, size: int) -> bytes:
    with path.open("rb") as stream: stream.seek(offset); data = stream.read(size)
    require(len(data) == size, f"short read at 0x{offset:x}"); return data


def parse_index(path: Path) -> None:
    path = regular(path, "NFL archive index")
    require(path.name == "0" and path.stat().st_size == INDEX_SIZE
            and sha256_file(path) == INDEX_SHA256, "source index identity changed")
    head = _read(path, 0, 0x9C); entry_count, reserved, pack_count = struct.unpack_from("<III", head)
    require((entry_count, reserved, pack_count) == (4323, 0, 16), "index header changed")
    blocks = struct.unpack_from("<36I", head, 0x0C)
    require(blocks[9] * 0x800 == PACK_SIZE, "volume 9 extent changed")
    name_id, size, offset_blocks = struct.unpack("<III", _read(path, 0x9C + ENTRY_INDEX * 12, 12))
    require((name_id, size, offset_blocks) == (ENTRY_ID, ENTRY_SIZE, ENTRY_OFFSET_BLOCKS),
            "outer directory entry changed")
    virtual_start = sum(blocks[:9]) * 0x800
    require(offset_blocks * 0x800 == ENTRY_VIRTUAL_OFFSET
            and ENTRY_VIRTUAL_OFFSET - virtual_start == ENTRY_PACK_OFFSET,
            "outer physical mapping changed")


def decompress_vc_lz(body: bytes, expected: int) -> tuple[bytes, dict[str, int]]:
    require(len(body) >= 10, "VC-LZ body too short")
    declared, tag = struct.unpack_from("<II", body); bits = body[8]
    require((declared, tag, bits) == (expected, 1, 12), "VC-LZ prefix changed")
    output = bytearray(expected); source = 10; flags = body[9]; flag_bit = 1; target = 0
    literals = matches = 0; distance_mask = (1 << bits) - 1; length_mask = 15
    while target < expected:
        if flags & flag_bit:
            require(source + 2 <= len(body), "truncated VC-LZ match")
            word = struct.unpack_from("<H", body, source)[0]; source += 2
            distance = word & distance_mask; length = ((word >> bits) & length_mask) + 3
            require(0 < distance <= target and target + length <= expected, "invalid VC-LZ match")
            for index in range(length - 1, -1, -1): output[target + index] = output[target - distance + index]
            target += length; matches += 1
        else:
            require(source < len(body), "truncated VC-LZ literal")
            output[target] = body[source]; source += 1; target += 1; literals += 1
        flag_bit = (flag_bit << 1) & 0xFF
        if flag_bit == 0 and target < expected:
            require(source < len(body), "missing VC-LZ flag"); flags = body[source]; source += 1; flag_bit = 1
    return bytes(output), {"consumed": source, "literals": literals, "matches": matches}


def minimum_overlap_scratch(body: bytes, stored: int, expected: int) -> int:
    require(len(body) >= 10 and struct.unpack_from("<I", body)[0] == expected and body[8] == 12,
            "VC-LZ scratch prefix changed")
    source, flags, bit, target, maximum = 10, body[9], 1, 0, 0
    while target < expected:
        if flags & bit:
            require(source + 2 <= len(body), "truncated scratch match")
            word = struct.unpack_from("<H", body, source)[0]; source += 2
            distance = word & 4095; length = (word >> 12) + 3
            require(0 < distance <= target, "invalid scratch match")
        else:
            require(source < len(body), "truncated scratch literal"); source += 1; length = 1
        target += length; require(target <= expected, "scratch token overrun")
        if target < expected: maximum = max(maximum, stored - expected + target - source)
        bit = (bit << 1) & 0xFF
        if bit == 0 and target < expected:
            require(source < len(body), "missing scratch flag"); flags = body[source]; source += 1; bit = 1
    return maximum


def _s32(data: bytes, offset: int) -> int: return struct.unpack_from("<i", data, offset)[0]
def _u32(data: bytes, offset: int) -> int: return struct.unpack_from("<I", data, offset)[0]


def _resolve(data: bytes, field: int, label: str) -> int | None:
    require(0 <= field <= SYSTEM_BYTES - 4, f"{label} pointer field outside system")
    relative = _s32(data, field)
    if relative == 0: return None
    target = field - 1 + relative
    require(0 <= target < SYSTEM_BYTES, f"{label} pointer outside system"); return target


def _utf16z(data: bytes, offset: int | None, label: str) -> str:
    require(offset is not None and offset % 2 == 0, f"{label} pointer unavailable")
    cursor = int(offset)
    while cursor + 2 <= SYSTEM_BYTES and data[cursor:cursor + 2] != b"\0\0": cursor += 2
    require(cursor + 2 <= SYSTEM_BYTES, f"{label} unterminated")
    try: return data[int(offset):cursor].decode("utf-16le")
    except UnicodeDecodeError as exc: raise CatalogPositionVerifyError(f"{label} invalid") from exc


def _hash_span(data: bytes, span: dict[str, Any], label: str) -> None:
    offset, size, end = span.get("offset"), span.get("size"), span.get("end_offset")
    require(type(offset) is int and type(size) is int and type(end) is int
            and end == offset + size and 0 <= offset < end <= len(data)
            and sha256(data[offset:end]) == span.get("sha256"), f"{label} hash/span changed")


def parse_target(decoded: bytes, row: dict[str, Any], expected: bytes) -> dict[str, Any]:
    contract = _target_contract(row)
    require(decoded[0x0C:0x10] == b"SCNE", "decoded object is not SCNE")
    require(_utf16z(decoded, _resolve(decoded, 0x10, "scene name"), "scene name") == "stadium",
            "scene name changed")
    descriptor = _resolve(decoded, 0x14, "scene descriptor")
    require(descriptor == 0x100 and _u32(decoded, descriptor + 0x2C) == 76,
            "stadium descriptor/shape count changed")
    shape_table = _resolve(decoded, descriptor + 0x30, "shape table")
    shape_offset = int(shape_table) + int(contract["shape_index"]) * 0x100
    shape_span = row["shape"]["record"]
    require(shape_offset == shape_span["offset"], "shape table offset differs from catalog")
    _hash_span(decoded, shape_span, "shape record")
    require(_utf16z(decoded, _resolve(decoded, shape_offset + 0x40, "shape name"), "shape name")
            == contract["shape_name"] and _u32(decoded, shape_offset + 0x44) == 2,
            "shape name/version changed")
    vertex, morph, transforms, blends, submeshes = struct.unpack_from("<5H", decoded, shape_offset + 0x4C)
    require((vertex, morph, transforms, blends, submeshes) ==
            (contract["vertex_count"], 0, 1, 0, row["topology_and_materials"]["submesh_count"]),
            "shape count tuple changed")
    declarations = struct.unpack_from("<16I", decoded, shape_offset + 0x84)
    strides = struct.unpack_from("<8H", decoded, shape_offset + 0xC4)
    require(declarations[0] == 0x32 and declarations[1] == 0x00080115
            and strides[0] == 12 and strides[1] == 10,
            "position/selector declarations changed")
    position = _resolve(decoded, shape_offset + 0xD4, "position stream")
    selector_stream = _resolve(decoded, shape_offset + 0xD8, "selector stream")
    transform = _resolve(decoded, shape_offset + 0x64, "transform table")
    submesh = _resolve(decoded, shape_offset + 0x70, "submesh table")
    require(position == contract["offset"] and selector_stream == row["selectors"]["stream"]["offset"]
            and transform == row["transform"]["table"]["offset"]
            and submesh == row["topology_and_materials"]["submesh_table"]["offset"],
            "shape nested pointers differ from catalog")
    require(decoded[int(contract["offset"]):int(contract["end"])] == expected,
            "decoded positions differ from recipe")
    _hash_span(decoded, row["shape"]["node"]["record"], "node record")
    _hash_span(decoded, row["transform"]["table"], "transform table")
    _hash_span(decoded, row["selectors"]["stream"], "selector stream")
    _hash_span(decoded, row["topology_and_materials"]["submesh_table"], "submesh table")
    for push in row["topology_and_materials"]["push_streams"]:
        _hash_span(decoded, push["record"], "push record"); _hash_span(decoded, push["commands"], "push commands")
    transform_offset = int(transform)
    require(struct.unpack_from("<4f", decoded, transform_offset + 0x40) == (0., 0., 0., 1.)
            and struct.unpack_from("<4f", decoded, transform_offset + 0x50) == (0., 0., 0., 1.)
            and _s32(decoded, transform_offset + 0x64) == -1,
            "target transform is not one zero root")
    selector_offset = int(selector_stream); count = int(contract["vertex_count"])
    selectors = [struct.unpack_from("<h", decoded, selector_offset + i * 10 + 8)[0] for i in range(count)]
    require(selectors == [0] * count, "target selectors are not all zero")
    return {"selector_count": count, "submesh_count": submeshes,
            "primitive_mode_counts": row["topology_and_materials"]["primitive_mode_counts"]}


def compare_packs(source: Path, output: Path) -> dict[str, Any]:
    require(source.stat().st_size == output.stat().st_size == PACK_SIZE, "volume sizes differ")
    outside = hashlib.sha256(); changed = 0; first = last = None
    with source.open("rb") as left, output.open("rb") as right:
        remaining = CHUNK_START
        while remaining:
            size = min(8 * 1024 * 1024, remaining); a, b = left.read(size), right.read(size)
            require(len(a) == len(b) == size and a == b, "pack changed before target chunk")
            outside.update(b); remaining -= size
        a, b = left.read(CHUNK_SPAN), right.read(CHUNK_SPAN)
        require(len(a) == len(b) == CHUNK_SPAN, "short target span")
        for local, (x, y) in enumerate(zip(a, b)):
            if x != y:
                changed += 1; first = CHUNK_START + local if first is None else first; last = CHUNK_START + local
        remaining = PACK_SIZE - CHUNK_END
        while remaining:
            size = min(8 * 1024 * 1024, remaining); a, b = left.read(size), right.read(size)
            require(len(a) == len(b) == size and a == b, "pack changed after target chunk")
            outside.update(b); remaining -= size
        require(left.read(1) == right.read(1) == b"", "pack trailing bytes differ")
    require(outside.hexdigest() == OUTSIDE_SHA256, "outside-chunk hash differs")
    return {"changed": changed, "first": first, "last": last, "outside": outside.hexdigest()}


def _aligned16(value: int) -> int: return (value + 15) & ~15


def verify(index_path: Path, catalog_path: Path, recipe_path: Path, output_dir: Path) -> dict[str, Any]:
    catalog = load_catalog(catalog_path); recipe = load_recipe(recipe_path, catalog)
    parse_index(index_path); index = regular(index_path, "NFL archive index")
    source_pack = regular(index.parent / "9", "source volume 9")
    require(source_pack.stat().st_size == PACK_SIZE and sha256_file(source_pack) == PACK_SHA256,
            "source volume identity changed")
    info = output_dir.expanduser().lstat()
    require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), "output directory invalid")
    output_dir = output_dir.resolve(strict=True)
    require(sorted(p.name for p in output_dir.iterdir()) == ["9", "manifest.json"],
            "output directory must contain only 9 and manifest.json")
    output_pack = regular(output_dir / "9", "output volume 9"); require_distinct_files(source_pack, output_pack)
    manifest, manifest_payload = _load_json(output_dir / "manifest.json", "patch manifest", MAX_MANIFEST_BYTES)
    require(sha256(_read(source_pack, ENTRY_PACK_OFFSET, ENTRY_SIZE)) == ENTRY_SHA256,
            "source outer bytes changed")
    source_span = _read(source_pack, CHUNK_START, CHUNK_SPAN)
    output_span = _read(output_pack, CHUNK_START, CHUNK_SPAN)
    require(sha256(source_span) == SOURCE_SPAN_SHA256
            and sha256(source_span[:32]) == SOURCE_WRAPPER_SHA256, "source SCNE span changed")
    source_fields = struct.unpack("<4s7I", source_span[:32]); output_fields = struct.unpack("<4s7I", output_span[:32])
    require(source_fields == (b"SCNE", CHUNK_STORED, SYSTEM_BYTES, VIDEO_BYTES,
            0xFEEDBEEF, 0x10, 0, 0), "source wrapper changed")
    require(output_fields[:5] == source_fields[:5] and output_fields[6:] == source_fields[6:]
            and all(a == b for i, (a, b) in enumerate(zip(source_span[:32], output_span[:32]))
                    if not 0x14 <= i < 0x18), "output wrapper changed outside scratch")
    source_body, output_body = source_span[32:], output_span[32:]
    source_decoded, source_lz = decompress_vc_lz(source_body, DECODED_SIZE)
    output_decoded, output_lz = decompress_vc_lz(output_body, DECODED_SIZE)
    require(source_lz == {"consumed": RETAIL_CONSUMED, "literals": 508197, "matches": 158651}
            and sha256(source_body[:RETAIL_CONSUMED]) == RETAIL_STREAM_SHA256
            and sha256(source_decoded) == SOURCE_DECODED_SHA256, "source VC-LZ decode changed")
    require(source_body[RETAIL_CONSUMED:] == output_body[RETAIL_CONSUMED:]
            and len(output_body[RETAIL_CONSUMED:]) == 16
            and sha256(output_body[RETAIL_CONSUMED:]) == TAIL_SHA256, "fixed final tail changed")
    consumed = output_lz["consumed"]
    require(consumed <= RETAIL_CONSUMED and not any(output_body[consumed:RETAIL_CONSUMED]),
            "rebuilt stream exceeds cap or gap is nonzero")
    padding = CHUNK_STORED - consumed
    alias = minimum_overlap_scratch(output_body[:consumed], CHUNK_STORED, DECODED_SIZE)
    scratch = _aligned16(max(padding, alias))
    observed_max = catalog["value"]["resource_contract"]["vc_lz"]["scratch_field_observed_corpus"]["maximum"]
    require(output_fields[5] == scratch and scratch <= observed_max,
            "scratch does not equal exact independently derived bounded value")
    contract, row, expected = recipe["contract"], recipe["row"], recipe["packed"]
    offset, end = int(contract["offset"]), int(contract["end"])
    source_position = source_decoded[offset:end]
    require(sha256(source_position) == row["position"]["contiguous_decoded_span"]["sha256"],
            "source target position hash changed")
    require(output_decoded[offset:end] == expected and source_decoded[:offset] == output_decoded[:offset]
            and source_decoded[end:] == output_decoded[end:], "decoded diff escaped target position lane")
    parsed = parse_target(output_decoded, row, expected)
    diff = compare_packs(source_pack, output_pack); output_sha = sha256_file(output_pack)
    mode = "no_op" if expected == source_position else "patched"
    if mode == "no_op": require(output_sha == PACK_SHA256 and diff["changed"] == 0
            and output_span == source_span, "no-op is not whole-volume exact")
    else: require(output_sha != PACK_SHA256 and diff["changed"] > 0, "changed recipe changed no bytes")
    changed_decoded = sum(a != b for a, b in zip(source_decoded, output_decoded))
    expected_manifest = {
        "schema": PATCH_SCHEMA, "mode": mode,
        "catalog": {"schema": CATALOG_SCHEMA, "size": CATALOG_SIZE,
                    "sha256": CATALOG_SHA256, "authorized_target_count": 75},
        "recipe": {"schema": RECIPE_SCHEMA, "sha256": recipe["sha256"],
                   "contains_only_target_id_catalog_pin_and_positions": True},
        "target": {"target_id": recipe["target_id"], "scene_index": 2648,
            "scene_name": "stadium", "shape_index": contract["shape_index"],
            "shape_name": contract["shape_name"], "vertex_count": contract["vertex_count"],
            "encoding": "contiguous_3xf32le", "position_span": [offset, end],
            "source_position_sha256": row["position"]["contiguous_decoded_span"]["sha256"]},
        "source": {"index_sha256": INDEX_SHA256, "volume_9_sha256_before": PACK_SHA256,
            "volume_9_sha256_after": PACK_SHA256, "source_modified": False,
            "outer_entry_sha256": ENTRY_SHA256, "resource_span_sha256": SOURCE_SPAN_SHA256,
            "decoded_sha256": SOURCE_DECODED_SHA256},
        "edit": {"position_before_sha256": sha256(source_position),
            "position_after_sha256": sha256(expected), "decoded_after_sha256": sha256(output_decoded),
            "decoded_changed_byte_count": changed_decoded,
            "every_decoded_byte_outside_position_span_bit_exact": True,
            "count_topology_material_transform_selector_and_other_streams_preserved": True},
        "compression": {"codec": "VC-LZ", "retail_consumed_cap": RETAIL_CONSUMED,
            "rebuilt_consumed_bytes": consumed, "rebuilt_stream_sha256": sha256(output_body[:consumed]),
            "zero_gap_bytes": RETAIL_CONSUMED - consumed, "stored_padding_bytes": padding,
            "minimum_alias_scratch_bytes": alias, "scratch_before": 16, "scratch_after": scratch,
            "scratch_policy": "align16(max(stored_size-consumed,minimum_alias_scratch))",
            "retail_scne_observed_scratch_max": observed_max, "fixed_final_tail_bytes": 16,
            "fixed_final_tail_sha256": TAIL_SHA256, "independent_decode_exact": True},
        "output": {"volume_name": "9", "volume_size": PACK_SIZE,
            "volume_sha256": output_sha, "outside_target_chunk_sha256": OUTSIDE_SHA256,
            "outside_target_chunk_bit_exact": True, "directory_files": ["9", "manifest.json"],
            "manifest_contains_positions_or_replacement_bytes": False},
        "claims": {"catalog_dispatcher_implemented": True, "authorized_catalog_targets": 75,
            "same_count_float3_write_back": True, "changed_count_or_topology_write_back": False,
            "runtime_visibility_proved": False, "semantic_rigidity_proved": False,
            "hardware_visibility_proved": False, "production_ready": False},
    }
    require(manifest == expected_manifest, "manifest differs from independent reconstruction")
    def contains_authored_payload(item: object) -> bool:
        if isinstance(item, dict):
            return any(
                key in {"positions", "replacement_bytes"}
                or contains_authored_payload(value)
                for key, value in item.items()
            )
        if isinstance(item, list):
            return any(contains_authored_payload(value) for value in item)
        return isinstance(item, (bytes, bytearray))

    require(not contains_authored_payload(manifest),
            "manifest embeds authored positions or replacement bytes")
    require(sha256_file(index) == INDEX_SHA256 and sha256_file(source_pack) == PACK_SHA256,
            "retail source changed during verification")
    return {"schema": VERIFY_SCHEMA, "mode": mode, "catalog_sha256": CATALOG_SHA256,
        "target_id": recipe["target_id"], "vertex_count": contract["vertex_count"],
        "recipe_sha256": recipe["sha256"], "manifest_sha256": sha256(manifest_payload),
        "source": {"index_sha256": INDEX_SHA256, "volume_sha256": PACK_SHA256,
                   "retail_unchanged": True},
        "output": {"volume_sha256": output_sha, "pack_changed_byte_count": diff["changed"],
            "first_changed_offset": diff["first"], "last_changed_offset": diff["last"],
            "outside_chunk_sha256": diff["outside"], "outside_chunk_bit_exact": True},
        "decoded": {"source_sha256": SOURCE_DECODED_SHA256,
            "output_sha256": sha256(output_decoded), "position_before_sha256": sha256(source_position),
            "position_after_sha256": sha256(expected), "decoded_changed_byte_count": changed_decoded,
            "outside_position_bit_exact": True},
        "compression": {"consumed_bytes": consumed, "retail_cap": RETAIL_CONSUMED,
            "zero_gap_bytes": RETAIL_CONSUMED - consumed, "padding_bytes": padding,
            "minimum_alias_scratch_bytes": alias, "scratch_bytes": scratch,
            "retail_observed_scratch_max": observed_max, "fixed_tail_sha256": TAIL_SHA256},
        "rigid_static": {"mechanical_only": True, **parsed},
        "claims": {"catalog_dispatcher": True, "same_count_position_write_back": True,
            "topology_write_back": False, "runtime_proved": False,
            "semantic_rigidity_proved": False, "production_ready": False}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-index", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.source_index, args.catalog, args.recipe, args.output_dir)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        parent = args.report.parent.lstat()
        require(stat.S_ISDIR(parent.st_mode) and not stat.S_ISLNK(parent.st_mode),
                "report parent must be a real non-symlink directory")
        try:
            with args.report.open("xb") as stream:
                stream.write(canonical_json(report)); stream.flush()
        except FileExistsError as exc:
            raise CatalogPositionVerifyError("refusing existing report") from exc
    print("NFL_CATALOG_POSITION_VERIFY_PASS "
          f"target={report['target_id']} mode={report['mode']} vertices={report['vertex_count']} "
          f"consumed={report['compression']['consumed_bytes']} "
          f"scratch={report['compression']['scratch_bytes']} runtime=false")
    return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (OSError, CatalogPositionVerifyError, struct.error, KeyError, IndexError,
            TypeError) as exc: raise SystemExit(f"error: {exc}") from exc
