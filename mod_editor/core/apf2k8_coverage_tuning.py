"""Bounded, opt-in APF PLAY zone geometry editing; in-game UNWITNESSED.

Opcode 0x0D is decoded by base 0x84A92148 / TU 0x84A93118. Its
coordinates and extents feed base 0x847F0A08 / TU 0x847F16A8.
These controls edit shared nodes, not an individual defender's matching rule.
No executable patch, receiver-carry promise, or automatic stock change is made.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Iterable, Mapping

from .apf2k8_playbook_route_writer import (
    encode_master_play_body, read_master_play_body, playbook_inventory as inventory,
)
from .errors import ValidationError


SCHEMA = "apf2k8_coverage_tuning/v1"
PROVIDER_KIND = "coverage_geometry"
PROFILE_SCHEMA = "apf2k8_coverage_geometry_profile/v1"
PROFILE_ASSET_ID = "apf:coverage:geometry"
MASTER_SHA256 = "2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891"
# SHA-256 with only the proved geometry bits in all zone payloads zeroed.
# This admits prior coverage edits while pinning every other bit to retail.
MASKED_MASTER_SHA256 = "ca1f83e389e9c6705438f5e05230fdc820c77c76c08e2828888121a9ee4aad28"
EDITABLE_MASK = 0xFFFF00FF
ZONE_OPCODE = 0x0D
KNOB_RANGES = {
    "landmark_x_feet": (-128, 127),
    "drop_depth_feet": (-64, 191),
    "lateral_extent_yards": (0, 15),
    "depth_extent_yards": (0, 15),
}


def status() -> dict[str, object]:
    return {"schema": SCHEMA, "status": "offline writer and reparse verifier; in-game UNWITNESSED",
            "provider_kind": PROVIDER_KIND, "runtime_witnessed": False,
            "registered": True, "rendered": True, "lane": "MASTER PLAY pack data",
            "scope": "shared opcode-0x0D coordinates and extents; no carry/match rule",
            "base_and_tu": "same proved decoder layout; no XEX patch required"}


@dataclass(frozen=True)
class ZoneEdit:
    node_index: int
    landmark_x_feet: int | None = None
    drop_depth_feet: int | None = None
    lateral_extent_yards: int | None = None
    depth_extent_yards: int | None = None


def edit_from_mapping(value: Mapping[str, object]) -> ZoneEdit:
    if not isinstance(value, Mapping) or set(value) - {"node_index", *KNOB_RANGES}:
        raise ValidationError("Coverage edit has unknown fields.")
    if "node_index" not in value:
        raise ValidationError("Coverage edit needs a shared node index.")
    edit = ZoneEdit(**value)
    _validate_edits((edit,))
    return edit


def encode_profile(edits: Iterable[ZoneEdit]) -> bytes:
    """Shareable project payload: authored selectors/values only."""
    requests = tuple(edits)
    _validate_edits(requests)
    if len(requests) > 368:
        raise ValidationError("Coverage profile exceeds the retail zone-node count.")
    return (json.dumps({"schema": PROFILE_SCHEMA, "edits": [asdict(e) for e in requests]},
                       sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def decode_profile(payload: bytes) -> tuple[ZoneEdit, ...]:
    if not isinstance(payload, bytes) or len(payload) > 131072:
        raise ValidationError("Coverage profile exceeds its bounded JSON size.")
    def unique_object(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValidationError("Duplicate coverage profile JSON key.")
            result[key] = value
        return result
    try:
        value = json.loads(payload, object_pairs_hook=unique_object)
        if (not isinstance(value, dict) or set(value) != {"schema", "edits"}
                or value["schema"] != PROFILE_SCHEMA or not isinstance(value["edits"], list)
                or len(value["edits"]) > 368):
            raise ValidationError("Invalid coverage profile schema.")
        requests = tuple(edit_from_mapping(v) for v in value["edits"])
        _validate_edits(requests)
        return requests
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ValidationError(f"Invalid coverage profile JSON: {exc}") from exc


def _validate_edits(edits: tuple[ZoneEdit, ...]) -> None:
    seen = set()
    for edit in edits:
        if not isinstance(edit, ZoneEdit) or type(edit.node_index) is not int or edit.node_index < 0:
            raise ValidationError("Coverage node index must be a nonnegative integer.")
        if edit.node_index in seen:
            raise ValidationError("Duplicate coverage node edit; merge its knobs into one request.")
        seen.add(edit.node_index)
        if all(getattr(edit, name) is None for name in KNOB_RANGES):
            raise ValidationError("Select at least one geometry knob.")
        for name, (low, high) in KNOB_RANGES.items():
            v = getattr(edit, name)
            if v is not None and (type(v) is not int or not low <= v <= high):
                raise ValidationError(f"{name} must be an integer in {low}..{high}.")


def _word(body: bytes, offset: int) -> int:
    return struct.unpack_from(">I", body, offset)[0]


def decode_geometry(payload: int) -> dict[str, int]:
    if type(payload) is not int or not 0 <= payload <= 0xFFFFFFFF:
        raise ValidationError("Zone payload must be an unsigned 32-bit integer.")
    return {"landmark_x_feet": (payload >> 24) - 128,
            "drop_depth_feet": ((payload >> 16) & 255) - 64,
            "lateral_extent_yards": payload & 15,
            "depth_extent_yards": (payload >> 4) & 15}


def _parsed(body: bytes) -> tuple[dict, dict[int, dict]]:
    if not isinstance(body, bytes):
        raise ValidationError("Coverage input must be immutable MASTER PLAY bytes.")
    try:
        book = inventory.parse_apf_body(body, 180, 0)
        count = book["root_counts"]["route_node_count"]
        zones = {}
        for index in range(count):
            off = inventory.APF_ROUTE_BASE + index * 8
            if body[off] == ZONE_OPCODE:
                w = _word(body, off + 4)
                zones[index] = {"node_index": index, "body_offset": off,
                                **decode_geometry(w), "mode": (w >> 8) & 15,
                                "operand_f": (w >> 12) & 1, "operand_g": (w >> 13) & 7,
                                "uses": []}
        # The descriptor's top nibble is the chain length (0x84A87980),
        # not a sentinel search and not a guessed next-pointer extent.
        for play in book["plays"]:
            po = inventory.APF_PLAY_BASE + play["index"] * inventory.APF_PLAY_SIZE
            for slot in range(11):
                desc = po + 0x0C + slot * 8
                n = _word(body, desc) >> 28
                target = inventory.relative(body, desc + 4, ">", "coverage chain")
                start, rem = divmod(target - inventory.APF_ROUTE_BASE, 8)
                if rem or start < 0 or start + n > count:
                    raise ValidationError("Assignment chain exceeds the PLAY node pool.")
                for node in range(start, start + n):
                    if node in zones:
                        zones[node]["uses"].append({"play_index": play["index"], "slot_index": slot,
                                                   "chain_step": node - start})
        return book, zones
    except (inventory.PlaybookError, KeyError, struct.error) as exc:
        raise ValidationError(f"Invalid coverage PLAY resource: {exc}") from exc


def _masked_hash(body: bytes, zones: Mapping[int, dict]) -> str:
    masked = bytearray(body)
    for zone in zones.values():
        off = zone["body_offset"] + 4
        struct.pack_into(">I", masked, off, _word(body, off) & ~EDITABLE_MASK)
    return hashlib.sha256(masked).hexdigest()


def _pin(body: bytes, zones: Mapping[int, dict]) -> None:
    if _masked_hash(body, zones) != MASKED_MASTER_SHA256:
        raise ValidationError("Unsupported MASTER PLAY: non-geometry data differs from the retail pin. "
                              "Apply coverage before other MASTER edits.")


def inspect_zones(body: bytes) -> tuple[dict, ...]:
    """Return derived values and every affected assignment; never raw nodes."""
    _, zones = _parsed(body)
    _pin(body, zones)
    return tuple(zones.values())


def _expected(body: bytes, edits: tuple[ZoneEdit, ...], zones: Mapping[int, dict]) -> bytes:
    _validate_edits(edits)
    out = bytearray(body)
    for edit in edits:
        if edit.node_index not in zones:
            raise ValidationError(f"Node {edit.node_index} is not a zone-drop node.")
        off = zones[edit.node_index]["body_offset"] + 4
        old = _word(body, off)
        v = decode_geometry(old)
        v.update({k: getattr(edit, k) for k in KNOB_RANGES if getattr(edit, k) is not None})
        packed = ((v["landmark_x_feet"] + 128) << 24 | (v["drop_depth_feet"] + 64) << 16
                  | v["depth_extent_yards"] << 4 | v["lateral_extent_yards"])
        struct.pack_into(">I", out, off, (old & ~EDITABLE_MASK) | packed)
    return bytes(out)


def verify_geometry(source: bytes, candidate: bytes, edits: Iterable[ZoneEdit]) -> dict[str, object]:
    """Reparse both resources, enforce the retail invariant, and check all bits."""
    requests = tuple(edits)
    _, before = _parsed(source)
    _, after = _parsed(candidate)
    _pin(source, before)
    _pin(candidate, after)
    if candidate != _expected(source, requests, before):
        raise ValidationError("Coverage verification found an unexpected value or unrelated write.")
    for edit in requests:
        for name in KNOB_RANGES:
            value = getattr(edit, name)
            if value is not None and after[edit.node_index][name] != value:
                raise ValidationError("Reparsed coverage value does not match the request.")
    changed = [i for i, (a, b) in enumerate(zip(source, candidate)) if a != b]
    return {"schema": SCHEMA, "runtime_witnessed": False, "verifier": "full PLAY reparse and exact allowed-bit comparison",
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "replacement_sha256": hashlib.sha256(candidate).hexdigest(),
            "changed_byte_count": len(changed), "changed_body_offsets": changed,
            "edits": [asdict(e) for e in requests],
            "affected_nodes": [after[e.node_index] for e in requests]}


def apply_geometry(body: bytes, edits: Iterable[ZoneEdit]) -> tuple[bytes, dict[str, object]]:
    """Idempotently edit the pinned MASTER body; original bytes are untouched."""
    requests = tuple(edits)
    _, zones = _parsed(body)
    _pin(body, zones)
    result = _expected(body, requests, zones)
    return result, verify_geometry(body, result, requests)


def compose_geometry(body: bytes, edits: Iterable[ZoneEdit], *, package_maps=(), routes=()) -> tuple[bytes, dict[str, object]]:
    """Apply coverage first, then existing validated package maps/route clones.

    Each writer verifies its own step. A final PLAY reparse and whole node-pool
    equality gate prove the downstream writers preserved the tuned geometry.
    Final uses are recomputed because a route clone can change node ownership.
    """
    requests, maps, route_requests = tuple(edits), tuple(package_maps), tuple(routes)
    tuned, receipt = apply_geometry(body, requests)
    if not maps and not route_requests:
        return tuned, receipt
    from .apf2k8_package_map_writer import compile_master_play_edits_detailed
    final, ranges, effective_maps = compile_master_play_edits_detailed(
        tuned, package_maps=maps, routes=route_requests)
    _, zones = _parsed(final)
    start, end = inventory.APF_ROUTE_BASE, inventory.APF_STRING_BASE
    if final[start:end] != tuned[start:end]:
        raise ValidationError("A composed MASTER edit changed the tuned node pool.")
    changed = [i for i, (a, b) in enumerate(zip(body, final)) if a != b]
    return final, {**receipt, "geometry_stage_sha256": receipt["replacement_sha256"],
                   "replacement_sha256": hashlib.sha256(final).hexdigest(),
                   "changed_body_offsets": changed, "changed_byte_count": len(changed),
                   "affected_nodes": [zones[e.node_index] for e in requests],
                   "composition": {"order": ["coverage", "package_maps", "route_clones"],
                                   "effective_package_maps": len(effective_maps), "route_requests": len(route_requests),
                                   "downstream_changed_ranges": [list(r) for r in ranges],
                                   "final_play_reparsed": True, "tuned_node_pool_preserved": True}}


def compile_outer_entry(index_path: Path, edits: Iterable[ZoneEdit], *, package_maps=(), routes=()) -> tuple[bytes, dict[str, object]]:
    """Return fixed-allocation outer 180 for the existing pack lane.

    The existing encoder checks H7A round trips and IFF structure and fails
    closed on allocation overflow. No input pack or retail file is written.
    """
    body = read_master_play_body(index_path)
    result, receipt = compose_geometry(body, edits, package_maps=package_maps, routes=routes)
    entry, container_receipt = encode_master_play_body(index_path, result)
    return entry, {**receipt, "outer_index": 180, "container": container_receipt}
