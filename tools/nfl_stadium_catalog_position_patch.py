#!/usr/bin/env python3
"""Fail-closed catalog-backed same-count FLOAT3 writer for NFL 2K5 stadiums.

The recipe names one target in the pinned hashes-only stadium catalog and
contains only an exact number of authored binary32 XYZ triples.  This tool
copies volume 9, edits only that target's decoded register-0 FLOAT3 lane,
rebuilds the fixed SCNE span, and refuses relocation or allocation growth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
from typing import Any

from nfl_outer import parse_archive, read_entry_range
from nfl_scene_probe import ResourceRecord, decode_resource
from nfl_scne_inventory import parse_scene
from nfl_txtr import HEADER, TxtrError, compress_vc_lz, decompress_vc_lz
from nfl_txtr import minimum_vc_lz_overlap_scratch


RECIPE_SCHEMA = "nfl2k5_catalog_static_position_recipe/v2"
PATCH_SCHEMA = "nfl2k5_catalog_static_position_patch/v2"
CATALOG_SCHEMA = "nfl2k5_stadium_static_target_catalog/v1"
CATALOG_SIZE = 858_600
CATALOG_SHA256 = "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa"
MAX_RECIPE_BYTES = 512 * 1024

INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
PACK_SIZE = 634_941_440
PACK_SHA256 = "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a"
OUTER_INDEX = 3280
OUTER_ID = 0xE4D6B0BC
OUTER_SIZE = 1_390_448
OUTER_OFFSET_BLOCKS = 1_747_476
OUTER_VIRTUAL_OFFSET = 3_578_830_848
OUTER_PACK_OFFSET = 0x07E47000
OUTER_SHA256 = "3b2a505e2f0cab433fbe74c5211e4b370112e4e70a2ad45f1fa39a59af9a92cd"
CHUNK_INDEX = 5
CHUNK_ENTRY_OFFSET = 0x5EA40
CHUNK_PACK_OFFSET = 0x07EA5A40
CHUNK_STORED_SIZE = 908_880
CHUNK_SPAN_SIZE = 908_912
CHUNK_PACK_END = CHUNK_PACK_OFFSET + CHUNK_SPAN_SIZE
SYSTEM_BYTES = 577_792
VIDEO_BYTES = 947_072
DECODED_SIZE = 1_524_864
RETAIL_CONSUMED = 908_864
SOURCE_SCRATCH = 0x10
OPAQUE_TAIL_SIZE = 16
CHUNK_SPAN_SHA256 = "0cd1977a6097851f9366d935098bdd9e97144f3ffce0f8690593c2623fbbd73a"
WRAPPER_SHA256 = "d4049cd35f3588259072ff9d05952c6bd830f6c1cd6181fc1d72b25b8cdc41ae"
DECODED_SHA256 = "229db9f309bf69eaa28901ae6e2e15b26a279b3f1f37abed01e36041c5e5ead8"
RETAIL_STREAM_SHA256 = "beb71504d82a7634d73bf6603fb96d8d0ba33beb4fd0eaa870efd4007a8d3af8"
OPAQUE_TAIL_SHA256 = "cb57e42b9b8d9e1cba31e18c38dbc3347c8caa1361fcf7fe9cfad5b9f138fae4"
OUTSIDE_CHUNK_SHA256 = "8ef9522d0b4e4c5dfd9bb65c2e18d6ddf4c506ce5513f341701958666edc2bc6"


class CatalogPositionPatchError(ValueError):
    """A source, catalog, recipe, or output violates the fixed contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CatalogPositionPatchError(message)


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
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise CatalogPositionPatchError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _load_json(path: Path, label: str, maximum: int) -> tuple[dict[str, Any], bytes]:
    path = regular(path, label)
    size = path.stat().st_size
    require(0 < size <= maximum, f"{label} size is outside its limit")
    payload = path.read_bytes()
    require(len(payload) == size, f"{label} changed while reading")
    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CatalogPositionPatchError(f"non-finite JSON constant {token} is forbidden")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogPositionPatchError(f"{label} is not UTF-8 JSON: {exc}") from exc
    require(isinstance(value, dict), f"{label} root must be an object")
    require(payload == canonical_json(value), f"{label} must be canonical sorted JSON")
    return value, payload


def load_catalog(path: Path) -> dict[str, Any]:
    catalog, payload = _load_json(path, "static-target catalog", CATALOG_SIZE)
    require(len(payload) == CATALOG_SIZE and sha256(payload) == CATALOG_SHA256,
            "catalog size or SHA-256 differs from the pinned authority")
    require(catalog.get("schema") == CATALOG_SCHEMA, "catalog schema changed")
    targets = catalog.get("targets")
    require(isinstance(targets, list) and len(targets) == 75,
            "catalog must contain exactly 75 authorized targets")
    by_id: dict[str, dict[str, Any]] = {}
    for row in targets:
        require(isinstance(row, dict) and isinstance(row.get("target_id"), str),
                "catalog target row is invalid")
        target_id = row["target_id"]
        require(target_id not in by_id, f"duplicate catalog target_id: {target_id}")
        by_id[target_id] = row
    return {"value": catalog, "targets": by_id, "sha256": CATALOG_SHA256,
            "size": CATALOG_SIZE}


def _f32(value: object, label: str) -> float:
    require(type(value) in (int, float), f"{label} must be a JSON number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise CatalogPositionPatchError(f"{label} is outside FLOAT32") from exc
    require(math.isfinite(number), f"{label} must be finite")
    try:
        decoded = struct.unpack("<f", struct.pack("<f", number))[0]
    except (OverflowError, struct.error) as exc:
        raise CatalogPositionPatchError(f"{label} is outside FLOAT32") from exc
    require(number == decoded, f"{label} must be exactly representable as binary32")
    return decoded


def _validate_target_row(row: dict[str, Any]) -> dict[str, int | str]:
    source = row.get("source_identity")
    shape = row.get("shape")
    position = row.get("position")
    eligibility = row.get("eligibility")
    require(isinstance(source, dict) and source == {
        "chunk_index": 5, "decoded_sha256": DECODED_SHA256,
        "outer_id": "0xe4d6b0bc", "outer_index": 3280,
        "resource_contract_sha256": "6df96f18ce86c4c8c3cc744ae5c00d6c64bdf06f658dc3c2c635bee79d93261b",
        "scene_index": 2648, "scene_name": "stadium",
    }, "catalog target source identity changed")
    require(isinstance(shape, dict) and isinstance(position, dict)
            and isinstance(eligibility, dict), "catalog target contract is incomplete")
    require(eligibility.get("mechanically_rigid_same_count_float3") is True,
            "catalog target is not mechanically eligible")
    vertex_count = shape.get("vertex_count")
    require(type(vertex_count) is int and vertex_count > 0, "target vertex count is invalid")
    declaration = position.get("declaration")
    require(declaration == {
        "byte_offset": 0, "byte_size": 12, "component_count": 3,
        "encoded": "0x00000032", "format_code": 50, "format_name": "FLOAT3",
        "register": 0, "stream_index": 0,
    }, "target register-0 declaration is not contiguous FLOAT3")
    require(position.get("stream_stride") == 12 and position.get("lane_size") == 12
            and position.get("lane_offset_within_stride") == 0,
            "target position lane is not packed FLOAT3")
    span = position.get("contiguous_decoded_span")
    require(isinstance(span, dict), "target position span is missing")
    offset, size, end = span.get("offset"), span.get("size"), span.get("end_offset")
    require(type(offset) is int and type(size) is int and type(end) is int
            and size == vertex_count * 12 and end == offset + size
            and 0 <= offset < end <= DECODED_SIZE,
            "target position span/count relationship changed")
    return {"offset": offset, "size": size, "end": end,
            "vertex_count": vertex_count, "shape_index": shape["index"],
            "shape_name": shape["name"]}


def load_recipe(path: Path, catalog: dict[str, Any]) -> dict[str, Any]:
    value, payload = _load_json(path, "catalog position recipe", MAX_RECIPE_BYTES)
    require(set(value) == {"catalog", "positions", "schema", "target_id"},
            "recipe fields differ from v2")
    require(value.get("schema") == RECIPE_SCHEMA, "recipe schema differs from v2")
    require(value.get("catalog") == {"schema": CATALOG_SCHEMA, "sha256": CATALOG_SHA256},
            "recipe catalog identity changed")
    target_id = value.get("target_id")
    require(type(target_id) is str and target_id in catalog["targets"],
            "recipe target_id is not authorized by the pinned catalog")
    row = catalog["targets"][target_id]
    contract = _validate_target_row(row)
    rows = value.get("positions")
    count = int(contract["vertex_count"])
    require(isinstance(rows, list) and len(rows) == count,
            f"recipe positions must contain exactly {count} vertices")
    positions: list[tuple[float, float, float]] = []
    for vertex, xyz in enumerate(rows):
        require(isinstance(xyz, list) and len(xyz) == 3,
                f"positions[{vertex}] must contain exactly XYZ")
        positions.append(tuple(_f32(item, f"positions[{vertex}][{axis}]")
                               for axis, item in enumerate(xyz)))
    packed = b"".join(struct.pack("<3f", *xyz) for xyz in positions)
    require(len(packed) == contract["size"], "packed position byte count changed")
    return {"sha256": sha256(payload), "target_id": target_id, "row": row,
            "contract": contract, "packed": packed}


def _hash_span(data: bytes, span: dict[str, Any], label: str) -> None:
    offset, size, end = span.get("offset"), span.get("size"), span.get("end_offset")
    require(type(offset) is int and type(size) is int and type(end) is int
            and end == offset + size and 0 <= offset < end <= len(data),
            f"{label} span is invalid")
    require(sha256(data[offset:end]) == span.get("sha256"), f"{label} hash changed")


def _validate_row_bytes(decoded: bytes, row: dict[str, Any]) -> None:
    contract = _validate_target_row(row)
    _hash_span(decoded, row["shape"]["record"], "shape record")
    _hash_span(decoded, row["shape"]["node"]["record"], "node record")
    _hash_span(decoded, row["position"]["contiguous_decoded_span"], "position stream")
    _hash_span(decoded, row["transform"]["table"], "transform table")
    _hash_span(decoded, row["selectors"]["stream"], "selector stream")
    _hash_span(decoded, row["topology_and_materials"]["submesh_table"], "submesh table")
    for push in row["topology_and_materials"]["push_streams"]:
        _hash_span(decoded, push["record"], "push record")
        _hash_span(decoded, push["commands"], "push commands")
    shape = row["shape"]
    require(shape["version"] == 2 and shape["index"] == contract["shape_index"],
            "catalog shape version/index changed")
    require(row["transform"]["base_count"] == 1
            and row["transform"]["blended_palette_entry_count"] == 0
            and row["transform"]["one_zero_root_parent_minus_one"] is True,
            "target no longer has one unblended zero root")
    require(row["morph"]["count"] == 0
            and row["selectors"]["all_select_sole_transform"] is True
            and row["topology_and_materials"]["all_vertex_references_in_bounds"] is True,
            "target rigid-static catalog invariants changed")


def _validate_source(index_path: Path, catalog: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    index = regular(index_path, "NFL archive index")
    require(index.name == "0" and index.stat().st_size == INDEX_SIZE
            and sha256_file(index) == INDEX_SHA256, "source index identity changed")
    pack = regular(index.parent / "9", "NFL source volume 9")
    require(pack.stat().st_size == PACK_SIZE and sha256_file(pack) == PACK_SHA256,
            "source volume 9 identity changed")
    archive = parse_archive(index)
    entry = archive.entries[OUTER_INDEX]
    require(entry.name_id == OUTER_ID and entry.size == OUTER_SIZE
            and entry.offset_blocks == OUTER_OFFSET_BLOCKS
            and entry.virtual_offset == OUTER_VIRTUAL_OFFSET,
            "outer entry 3280 identity changed")
    require(len(entry.segments) == 1 and entry.segments[0].pack_name == "9"
            and entry.segments[0].pack_offset == OUTER_PACK_OFFSET
            and entry.segments[0].size == OUTER_SIZE,
            "outer entry 3280 mapping changed")
    outer = read_entry_range(archive, entry, 0, entry.size)
    require(sha256(outer) == OUTER_SHA256, "outer entry bytes changed")
    span = outer[CHUNK_ENTRY_OFFSET:CHUNK_ENTRY_OFFSET + CHUNK_SPAN_SIZE]
    require(sha256(span) == CHUNK_SPAN_SHA256 and sha256(span[:32]) == WRAPPER_SHA256,
            "source SCNE span changed")
    require(HEADER.unpack_from(span) == (b"SCNE", CHUNK_STORED_SIZE, SYSTEM_BYTES,
            VIDEO_BYTES, 0xFEEDBEEF, SOURCE_SCRATCH, 0, 0),
            "source SCNE wrapper fields changed")
    record = ResourceRecord(outer_index=OUTER_INDEX, outer_id="0xe4d6b0bc",
        outer_size=OUTER_SIZE, chunk_index=CHUNK_INDEX, chunk_offset=CHUNK_ENTRY_OFFSET,
        kind="SCNE", stored_size=CHUNK_STORED_SIZE, word_08=SYSTEM_BYTES,
        word_0c=VIDEO_BYTES, word_10=0xFEEDBEEF, word_14=SOURCE_SCRATCH)
    decoded, detail = decode_resource(span, record)
    require(len(decoded) == DECODED_SIZE and sha256(decoded) == DECODED_SHA256,
            "source decoded SCNE changed")
    require(detail.get("lz", {}).get("consumed_bytes") == RETAIL_CONSUMED,
            "source VC-LZ consumed length changed")
    require(sha256(span[32:32 + RETAIL_CONSUMED]) == RETAIL_STREAM_SHA256,
            "source compressed stream changed")
    tail = span[32 + RETAIL_CONSUMED:]
    require(len(tail) == 16 and sha256(tail) == OPAQUE_TAIL_SHA256,
            "source fixed final tail changed")
    _validate_row_bytes(decoded, row)
    scene, _, _, _ = parse_scene(2648, record, decoded, {})
    require(scene["name"] == "stadium", "scene name changed")
    shape = scene["shapes"][row["shape"]["index"]]
    contract = _validate_target_row(row)
    require(shape["name"] == contract["shape_name"] and shape["version"] == 2
            and shape["vertex_count"] == contract["vertex_count"]
            and shape["morph_channel_count"] == 0 and shape["transform_count"] == 1,
            "parsed target shape differs from catalog")
    position = next(item for item in shape["attribute_descriptors"] if item["register"] == 0)
    require(position["format_name"] == "FLOAT3" and position["stream_index"] == 0
            and position["byte_offset"] == 0 and shape["vertex_streams"][0]["stride"] == 12
            and shape["vertex_streams"][0]["offset"] == contract["offset"],
            "parsed register-0 stream differs from catalog")
    return {"index": index, "pack": pack, "span": span, "decoded": decoded,
            "retail_stream": span[32:32 + RETAIL_CONSUMED], "tail": tail}


def _aligned16(value: int) -> int:
    return (value + 15) & ~15


def build_span(source: dict[str, Any], recipe: dict[str, Any], catalog: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    decoded = bytes(source["decoded"])
    contract = recipe["contract"]
    offset, end = int(contract["offset"]), int(contract["end"])
    packed = bytes(recipe["packed"])
    before = decoded[offset:end]
    edited = decoded[:offset] + packed + decoded[end:]
    require(len(edited) == len(decoded) and decoded[:offset] == edited[:offset]
            and decoded[end:] == edited[end:], "decoded edit escaped target lane")
    try:
        encoded, metrics = compress_vc_lz(edited, stream_tag=1, offset_bits=12,
            max_encoded_size=RETAIL_CONSUMED, verify_roundtrip=True)
    except TxtrError as exc:
        raise CatalogPositionPatchError(
            "replacement exceeds the 908864-byte consumed-stream cap"
        ) from exc
    decoded_back, info = decompress_vc_lz(encoded, DECODED_SIZE)
    require(decoded_back == edited and info.consumed_bytes == len(encoded),
            "writer-side independent VC-LZ decode differs")
    gap = RETAIL_CONSUMED - len(encoded)
    padding = CHUNK_STORED_SIZE - len(encoded)
    alias = minimum_vc_lz_overlap_scratch(encoded, CHUNK_STORED_SIZE, DECODED_SIZE)
    scratch = _aligned16(max(padding, alias))
    observed_max = catalog["value"]["resource_contract"]["vc_lz"][
        "scratch_field_observed_corpus"]["maximum"]
    require(type(observed_max) is int and scratch <= observed_max,
            "derived scratch exceeds the pinned retail SCNE observed maximum")
    header = bytearray(bytes(source["span"])[:32])
    struct.pack_into("<I", header, 0x14, scratch)
    rebuilt = bytes(header) + encoded + bytes(gap) + bytes(source["tail"])
    require(len(rebuilt) == CHUNK_SPAN_SIZE and rebuilt[-16:] == source["tail"],
            "rebuilt fixed span or final tail changed")
    mode = "no_op" if packed == before else "patched"
    if mode == "no_op":
        require(encoded == source["retail_stream"] and rebuilt == source["span"]
                and scratch == SOURCE_SCRATCH, "no-op is not byte-identical")
    changed = sum(a != b for a, b in zip(decoded, edited))
    return rebuilt, {"mode": mode, "decoded": edited, "before_sha256": sha256(before),
        "after_sha256": sha256(packed), "decoded_sha256": sha256(edited),
        "changed_bytes": changed, "encoded_bytes": len(encoded),
        "encoded_sha256": sha256(encoded), "gap": gap, "padding": padding,
        "alias": alias, "scratch": scratch, "observed_max": observed_max,
        "literals": metrics.literal_count, "matches": metrics.match_count}


def _outside_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        remaining = CHUNK_PACK_OFFSET
        while remaining:
            block = stream.read(min(8 * 1024 * 1024, remaining))
            require(bool(block), "short output before target chunk")
            digest.update(block); remaining -= len(block)
        stream.seek(CHUNK_PACK_END)
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest(recipe: dict[str, Any], output: Path, build: dict[str, Any]) -> dict[str, Any]:
    contract, row = recipe["contract"], recipe["row"]
    output_sha, outside = sha256_file(output), _outside_hash(output)
    require(outside == OUTSIDE_CHUNK_SHA256, "output changed outside target chunk")
    return {
        "schema": PATCH_SCHEMA, "mode": build["mode"],
        "catalog": {"schema": CATALOG_SCHEMA, "size": CATALOG_SIZE,
                    "sha256": CATALOG_SHA256, "authorized_target_count": 75},
        "recipe": {"schema": RECIPE_SCHEMA, "sha256": recipe["sha256"],
                   "contains_only_target_id_catalog_pin_and_positions": True},
        "target": {"target_id": recipe["target_id"], "scene_index": 2648,
            "scene_name": "stadium", "shape_index": contract["shape_index"],
            "shape_name": contract["shape_name"], "vertex_count": contract["vertex_count"],
            "encoding": "contiguous_3xf32le", "position_span": [contract["offset"], contract["end"]],
            "source_position_sha256": row["position"]["contiguous_decoded_span"]["sha256"]},
        "source": {"index_sha256": INDEX_SHA256, "volume_9_sha256_before": PACK_SHA256,
            "volume_9_sha256_after": PACK_SHA256, "source_modified": False,
            "outer_entry_sha256": OUTER_SHA256, "resource_span_sha256": CHUNK_SPAN_SHA256,
            "decoded_sha256": DECODED_SHA256},
        "edit": {"position_before_sha256": build["before_sha256"],
            "position_after_sha256": build["after_sha256"],
            "decoded_after_sha256": build["decoded_sha256"],
            "decoded_changed_byte_count": build["changed_bytes"],
            "every_decoded_byte_outside_position_span_bit_exact": True,
            "count_topology_material_transform_selector_and_other_streams_preserved": True},
        "compression": {"codec": "VC-LZ", "retail_consumed_cap": RETAIL_CONSUMED,
            "rebuilt_consumed_bytes": build["encoded_bytes"],
            "rebuilt_stream_sha256": build["encoded_sha256"],
            "zero_gap_bytes": build["gap"], "stored_padding_bytes": build["padding"],
            "minimum_alias_scratch_bytes": build["alias"], "scratch_before": SOURCE_SCRATCH,
            "scratch_after": build["scratch"],
            "scratch_policy": "align16(max(stored_size-consumed,minimum_alias_scratch))",
            "retail_scne_observed_scratch_max": build["observed_max"],
            "fixed_final_tail_bytes": 16, "fixed_final_tail_sha256": OPAQUE_TAIL_SHA256,
            "independent_decode_exact": True},
        "output": {"volume_name": "9", "volume_size": PACK_SIZE,
            "volume_sha256": output_sha, "outside_target_chunk_sha256": outside,
            "outside_target_chunk_bit_exact": True, "directory_files": ["9", "manifest.json"],
            "manifest_contains_positions_or_replacement_bytes": False},
        "claims": {"catalog_dispatcher_implemented": True,
            "authorized_catalog_targets": 75, "same_count_float3_write_back": True,
            "changed_count_or_topology_write_back": False, "runtime_visibility_proved": False,
            "semantic_rigidity_proved": False, "hardware_visibility_proved": False,
            "production_ready": False},
    }


def _inode(path: Path) -> tuple[int, int]:
    info = path.lstat(); return info.st_dev, info.st_ino


def _is_regular_inode(path: Path, expected: tuple[int, int]) -> bool:
    try: info = path.lstat()
    except FileNotFoundError: return False
    return stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode) and _inode(path) == expected


def _publish_staged_no_replace(reservation: Path, reservation_inode: tuple[int, int],
        staging: Path, staging_inode: tuple[int, int], known: dict[str, tuple[int, int]]) -> None:
    require(_inode(reservation) == reservation_inode and _inode(staging) == staging_inode,
            "output or staging directory inode changed")
    require(sorted(p.name for p in reservation.iterdir()) == [staging.name],
            "output reservation gained an unexpected raced artifact")
    require(sorted(p.name for p in staging.iterdir()) == ["9", "manifest.json"],
            "staging directory is not exclusive")
    for name in ("9", "manifest.json"):
        require(_is_regular_inode(staging / name, known[name]), f"staged {name} inode changed")
    try:
        for name in ("9", "manifest.json"):
            os.link(staging / name, reservation / name, follow_symlinks=False)
            require(_is_regular_inode(reservation / name, known[name]),
                    f"published {name} inode changed")
    except FileExistsError as exc:
        raise CatalogPositionPatchError("refusing publication race replacement") from exc
    for name in ("9", "manifest.json"):
        require(_is_regular_inode(staging / name, known[name]), f"staged {name} inode changed before cleanup")
        (staging / name).unlink()
    require(_inode(staging) == staging_inode and not any(staging.iterdir()),
            "staging directory changed before cleanup")
    staging.rmdir()
    require(sorted(p.name for p in reservation.iterdir()) == ["9", "manifest.json"],
            "published directory is not exclusive")


def _cleanup(reservation: Path, reservation_inode: tuple[int, int] | None,
        staging: Path | None, staging_inode: tuple[int, int] | None,
        known: dict[str, tuple[int, int]]) -> None:
    if reservation_inode is None:
        return
    try:
        if _inode(reservation) != reservation_inode: return
    except FileNotFoundError: return
    for base in (reservation, staging):
        if base is None: continue
        for name, inode in known.items():
            path = base / name
            if _is_regular_inode(path, inode): path.unlink()
    if staging is not None:
        try:
            if _inode(staging) == staging_inode and not any(staging.iterdir()): staging.rmdir()
        except FileNotFoundError: pass
    try:
        if _inode(reservation) == reservation_inode and not any(reservation.iterdir()): reservation.rmdir()
    except FileNotFoundError: pass


def _copy_and_patch_owned_volume(source_pack: Path, output: Path,
        rebuilt: bytes) -> tuple[int, int]:
    """Copy and patch one exclusive-created inode without reopening its path."""
    require(len(rebuilt) == CHUNK_SPAN_SIZE, "rebuilt fixed span size changed")
    with source_pack.open("rb") as left, output.open("x+b") as right:
        info = os.fstat(right.fileno()); owned = (info.st_dev, info.st_ino)
        require(_inode(output) == owned, "staged volume pathname changed after creation")
        for block in iter(lambda: left.read(8 * 1024 * 1024), b""):
            right.write(block)
        right.flush()
        require(os.fstat(right.fileno()).st_size == PACK_SIZE,
                "copied staged volume size changed")
        right.seek(CHUNK_PACK_OFFSET); right.write(rebuilt); right.flush(); os.fsync(right.fileno())
        require(os.fstat(right.fileno()).st_size == PACK_SIZE,
                "patched staged volume size changed")
        require(_inode(output) == owned,
                "staged volume pathname changed during copy/patch")
    return owned


def patch(index: Path, catalog_path: Path, recipe_path: Path, output_dir: Path) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    recipe = load_recipe(recipe_path, catalog)
    output_dir = output_dir.expanduser()
    parent_info = output_dir.parent.lstat()
    require(stat.S_ISDIR(parent_info.st_mode) and not stat.S_ISLNK(parent_info.st_mode),
            "output parent must be a real non-symlink directory")
    requested = output_dir.parent.resolve(strict=True) / output_dir.name
    index = regular(index, "NFL archive index")
    source_pack = regular(index.parent / "9", "NFL source volume 9")
    require(requested != source_pack.parent, "refusing retail source directory as output")
    try: requested.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise CatalogPositionPatchError("refusing existing output directory") from exc
    reservation_inode = _inode(requested)
    staging: Path | None = None; staging_inode: tuple[int, int] | None = None
    known: dict[str, tuple[int, int]] = {}
    try:
        source = _validate_source(index, catalog, recipe["row"])
        rebuilt, build = build_span(source, recipe, catalog)
        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=requested)); staging_inode = _inode(staging)
        output = staging / "9"
        known["9"] = _copy_and_patch_owned_volume(source_pack, output, rebuilt)
        require(_is_regular_inode(output, known["9"]),
                "staged volume pathname changed before manifest construction")
        require(output.stat().st_size == PACK_SIZE, "output volume size changed")
        require(sha256_file(source_pack) == PACK_SHA256, "source volume changed during copy")
        manifest = _manifest(recipe, output, build)
        manifest_path = staging / "manifest.json"
        with manifest_path.open("xb") as stream:
            info = os.fstat(stream.fileno()); known["manifest.json"] = (info.st_dev, info.st_ino)
            stream.write(canonical_json(manifest)); stream.flush(); os.fsync(stream.fileno())
        _publish_staged_no_replace(requested, reservation_inode, staging, staging_inode, known)
        return manifest
    except Exception:
        _cleanup(requested, reservation_inode, staging, staging_inode, known)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest = patch(args.index, args.catalog, args.recipe, args.output_dir)
    print("NFL_CATALOG_POSITION_PATCH_COMPLETE "
          f"target={manifest['target']['target_id']} mode={manifest['mode']} "
          f"vertices={manifest['target']['vertex_count']} "
          f"sha256={manifest['output']['volume_sha256']}")
    return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (OSError, CatalogPositionPatchError, TxtrError, struct.error, KeyError,
            IndexError, TypeError) as exc: raise SystemExit(f"error: {exc}") from exc
