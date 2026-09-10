"""Bounded field-material alpha edits and token-preserving fixed-allocation refit.

Derived from SCNE entries 53/252/578/1333. +0x20 points to a material command
payload; tint is +0x70, or +0x100 for endzone grass. Never search compressed
bytes for floats. Appearance in play remains UNWITNESSED.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import struct
from typing import Mapping

from .apf2k8_playbook_route_writer import apf_inner, apf_outer, apf_texture_patch
from .errors import ValidationError

SCHEMA = "apf_field_material_alpha/v1"
PROVIDER_KIND = "field_material_alpha"
ENTRY_NAME_IDS = {53: 0x09478873, 252: 0x2A1C6B95, 578: 0x5F132F88, 1333: 0xDE584911}
MATERIALS = {
    "field_grass": 0, "endzone_grass": 1, "ticks": 2, "chalk_lines": 3,
    "graphic_overlay_4": 4, "graphic_overlay_5": 5, "graphic_overlay_7": 7,
    "graphic_overlay_8": 8, "graphic_overlay_9": 9,
    "outside_grass_10": 10, "outside_grass_11": 11,
}
OVERLAYS = tuple(k for k in MATERIALS if k.startswith("graphic_overlay"))
# Stable material identifiers and shader families across all four retail scenes.
MATERIAL_IDS = (0xA79767ED, 0x54BC251C, 0x480BC10C, 0x8EC0A392,
                0xF39C0592, 0xDD1BE078, 0x4FB516F7, 0xBEBC5993,
                0xC0596E41, 0x5AF39102, 0x553CEC26, 0xE351C786)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValidationError(reason)


def _u32(data: bytes, at: int) -> int:
    _require(0 <= at <= len(data) - 4, "Field material word exceeds its scene")
    return struct.unpack_from(">I", data, at)[0]


def _relative(data: bytes, at: int) -> int:
    raw = _u32(data, at)
    _require(raw != 0, "Field material pointer is null")
    signed = raw - 0x100000000 if raw & 0x80000000 else raw
    target = at + signed - 1
    _require(0 <= target < len(data), "Field material pointer leaves its scene")
    return target


@dataclass(frozen=True)
class MaterialAlpha:
    name: str
    index: int
    record_offset: int
    payload_offset: int
    alpha_offset: int
    alpha: float


def parse_scene(scene: bytes) -> tuple[MaterialAlpha, ...]:
    """Bound the tables, pin identifiers and reparse each independent tint."""
    _require(len(scene) >= 0x64, "Field SCNE header is truncated")
    count = _u32(scene, 0x30)
    table = _relative(scene, 0x38)
    _require(13 <= count <= 16 and table >= 0x64 and table % 4 == 0
             and table + count * 0x28 <= len(scene), "Unsupported field material table")
    payloads = [_relative(scene, table + i * 0x28 + 0x20) for i in range(count)]
    _require(payloads == sorted(set(payloads)) and payloads[0] >= table + count * 0x28,
             "Field material payloads overlap or are unordered")
    result = []
    for name, index in MATERIALS.items():
        record = table + index * 0x28
        _require(_u32(scene, record) == MATERIAL_IDS[index], "Field material identifier changed")
        _require(_u32(scene, record + 8) == (0x868B853C if index == 1 else 0xAB01CC7A),
                 "Field material shader family changed")
        payload = payloads[index]
        tint = payload + (0x100 if index == 1 else 0x70)
        _require(tint + 16 <= payloads[index + 1], "Field tint exceeds its material payload")
        _require(scene[payload:payload + 16] == struct.pack(">4I", 0xFFFFFFFF, 0, 0xFFFFFFFF, 0),
                 "Field command payload header changed")
        rgb = struct.unpack_from(">3f", scene, tint)
        alpha = struct.unpack_from(">f", scene, tint + 12)[0]
        _require(rgb == (1.0, 1.0, 1.0) and math.isfinite(alpha) and 0 <= alpha <= 1,
                 "Field tint is not a supported (1,1,1,alpha) constant")
        result.append(MaterialAlpha(name, index, record, payload, tint + 12, alpha))
    return tuple(result)


def normalize_alphas(alphas: Mapping[str, float]) -> dict[str, float]:
    _require(isinstance(alphas, Mapping) and bool(alphas), "Choose at least one field material")
    result = {}
    for name, value in alphas.items():
        _require(name in MATERIALS, f"Unknown field material: {name}")
        _require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1,
                 "Field opacity must be a finite number from 0 to 1")
        result[name] = struct.unpack(">f", struct.pack(">f", value))[0]
    return dict(sorted(result.items()))


def verify_scene(before: bytes, after: bytes, alphas: Mapping[str, float]) -> dict:
    values = normalize_alphas(alphas)
    original, reparsed = parse_scene(before), parse_scene(after)
    _require(len(before) == len(after), "Field material edit changed scene length")
    allowed = set()
    changes = []
    for a, b in zip(original, reparsed):
        _require((a.name, a.record_offset, a.payload_offset, a.alpha_offset) ==
                 (b.name, b.record_offset, b.payload_offset, b.alpha_offset),
                 "Field material ownership changed")
        expected = values.get(a.name, a.alpha)
        _require(b.alpha == expected, f"Field alpha reparse differs for {a.name}")
        if a.name in values:
            allowed.update(range(a.alpha_offset, a.alpha_offset + 4))
            changes.append({"material": a.name, "index": a.index, "alpha_offset": a.alpha_offset,
                            "before": a.alpha, "after": b.alpha})
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    _require(set(changed) <= allowed, "Field edit changed a byte outside selected alpha words")
    return {"schema": SCHEMA, "changes": changes, "changed_byte_count": len(changed),
            "layout": {"scene_bytes": len(before), "material_count": _u32(before, 0x30),
                       "table_offset": _relative(before, 0x38), "record_stride": 0x28,
                       "constants_pointer_offset": 0x20,
                       "pointer_rule": "target = field + signed stored - 1",
                       "tint_from_payload": {"endzone_grass": 0x100, "other_named_materials": 0x70}},
            "reparsed": True, "source_sha256": sha(before), "output_sha256": sha(after),
            "runtime_status": "UNWITNESSED", "preset": "ADVANCED; off by default"}


def compile_scene(scene: bytes, alphas: Mapping[str, float]) -> tuple[bytes, dict]:
    values = normalize_alphas(alphas)
    result = bytearray(scene)
    for material in parse_scene(scene):
        if material.name in values:
            struct.pack_into(">f", result, material.alpha_offset, values[material.name])
    output = bytes(result)
    return output, verify_scene(scene, output, values)


def _parse_entry(entry, original: bytes):
    _require(len(original) == entry.size, "Field outer allocation size changed")
    reader = apf_texture_patch.BytesReader(original)
    record = apf_inner.parse_iff(reader, entry)
    _require(not record.warnings and record.block_count == 1 and record.footer is not None,
             "Field edit requires one warning-free IFF block")
    files = [f for f in record.files if f.name == "field" and f.type_name == "SCNE"]
    _require(len(files) == 1 and len(files[0].parts) >= 1, "Field SCNE ownership changed")
    part = files[0].parts[0]
    block = record.blocks[0]
    _require(part.block_index == 0 and block.is_compressed and block.wrapper is not None,
             "Field scene must reside in the H7A block")
    decoded = apf_inner.decode_block(reader, record, 0, 16 * 1024 * 1024)
    _require(0 <= part.offset < part.offset + part.length <= len(decoded), "Field scene part exceeds block")
    parse_scene(decoded[part.offset:part.offset + part.length])
    return record, part, decoded


def compile_entry(entry, original: bytes, alphas: Mapping[str, float]) -> tuple[bytes, dict]:
    """Compose into an existing entry, preserving all sibling textures and parts."""
    record, part, decoded = _parse_entry(entry, original)
    scene = decoded[part.offset:part.offset + part.length]
    replacement, receipt = compile_scene(scene, alphas)
    wanted = decoded[:part.offset] + replacement + decoded[part.offset + part.length:]
    block = record.blocks[0]
    stream = original[block.start_offset + 20:block.start_offset + block.stored_length]
    encoded, preservation = apf_inner.encode_h7a_preserving_tokens(stream, decoded, wanted, block.wrapper.shift)
    tokens, _ = apf_inner._parse_h7a_tokens(encoded, len(wanted), block.wrapper.shift)
    _require(all(t.distance is None or t.length <= t.distance for t in tokens), "Field H7A has an overlapping match")
    stored = struct.pack(">5I", apf_inner.H7A_MAGIC, len(wanted), 20 + len(encoded),
                         block.unknown_10, block.wrapper.shift) + encoded
    header = bytearray(original[:record.header_size])
    struct.pack_into(">8I", header, apf_inner.IFF_HEADER_SIZE, block.name_hash, block.type_hash,
                     block.unknown_08, len(wanted), block.unknown_10, record.header_size, len(stored), block.indexed)
    struct.pack_into(">I", header, 8, len(header) + len(stored))
    end = record.file_length + 8 + record.footer.payload_size
    _require(end <= len(original) and not any(original[end:]), "Field allocation tail is not free")
    active = bytes(header) + stored + original[record.file_length:end]
    _require(len(active) <= entry.size, f"Field opacity needs {len(active)} bytes; allocation is {entry.size}")
    output = active.ljust(entry.size, b"\0")
    after_record, after_part, after = _parse_entry(entry, output)
    _require(after_record.files == record.files and after_part == part and after == wanted,
             "Field H7A reparse changed scene or sibling data")
    verify_scene(scene, after[part.offset:part.offset + part.length], alphas)
    receipt["transport"] = {"strategy": "token preserving", "stored_growth": len(stored) - block.stored_length,
                            "allocation_bytes": entry.size, "free_bytes": entry.size - len(active),
                            "overlapping_matches": 0, "reparsed": True, **preservation}
    receipt["outer_index"] = entry.table_index
    receipt["entry_sha256"] = sha(output)
    return output, receipt


def build_patch(index: Path, outer_index: int, alphas: Mapping[str, float], *,
                current_entry: bytes | None = None) -> tuple[bytes, dict]:
    """Read only; current_entry permits composition after field texture edits."""
    _require(outer_index in ENTRY_NAME_IDS, "Choose field entry 53, 252, 578 or 1333")
    archive = apf_outer.parse_archive(Path(index))
    entry = archive.entries[outer_index]
    _require(entry.name_id == ENTRY_NAME_IDS[outer_index], "Field entry name/number changed")
    if current_entry is None:
        with apf_inner.ArchiveReader(archive) as reader:
            current_entry = reader.read(entry, 0, entry.size)
    return compile_entry(entry, current_entry, alphas)
