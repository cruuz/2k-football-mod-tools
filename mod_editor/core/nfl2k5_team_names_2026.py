"""Opt-in fixed-span 2026 team text. EXPERIMENTAL / UNWITNESSED.

The main ROST has separate team identity and team-label strings. Both are
patched; historic ROSTs, stadiums, art codes, XBE literals and audio are not.
The two retail STRG banks contain no affected names (1,115 allocations audited).
No allocation or pointer moves. Full modern names that do not fit have explicit
short forms in the checked-in manifest, shared by Build and Team Identity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
from typing import Any, Callable

from . import nfl2k5_roster_records as rr
from .nfl2k5_text_catalog import encode_fixed_utf16le

MANIFEST = Path(__file__).resolve().parents[2] / "data/nfl2k5_team_names_2026.json"
MANIFEST_SHA256 = "fea1e37b7fb23887b8231d3e971b5113eeecef1d815001b9032da6b0eac8d13b"
ROST_OUTER_INDEX = 5


class TeamNamesError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TeamNamesError(message)


def manifest() -> dict[str, Any]:
    raw = MANIFEST.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256,
             "2026 team-name manifest differs from its verified allocation map")
    return json.loads(raw)


def _relative(body: bytes, field: int) -> int | None:
    _require(0 <= field <= len(body) - 4, "team-name pointer field outside ROST")
    value = struct.unpack_from("<i", body, field)[0]
    target = field + value - 1 if value else None
    _require(target is None or 0 <= target < len(body), "team-name pointer outside ROST")
    return target


def _text_references(body: bytes) -> list[tuple[int, int]]:
    # Same proved UTF-16 pointer domains as roster_text_reference_counts. All
    # known readers are checked, including interior aliases, before any write.
    domains = ((0x00, 0x54, (0x10, 0x14)), (0x08, 0x54, (0x10, 0x14)),
               (0x10, 0x80, (0, 8, 12, 16, 20)),
               (0x18, 0x1F4, (0x104, 0x108, 0x10C, 0x138, 0x13C)),
               (0x20, 8, (0,)), (0x30, 0xA8, (0, 4, 8, 12, 16)),
               (0x48, 8, (0, 4)), (0x50, 8, (0, 4)), (0x58, 16, (12,)))
    refs = []
    for offset, stride, fields in domains:
        count = struct.unpack_from("<I", body, 0x40 + offset)[0]
        table = _relative(body, 0x44 + offset)
        _require(count <= 100000 and (not count or table is not None and
                 table + count * stride <= len(body)), "ROST text table outside its fixed body")
        for index in range(count):
            for relative in fields:
                field = table + index * stride + relative
                target = _relative(body, field)
                if target is not None:
                    refs.append((field, target))
    return refs


def _inspect(payload: bytes, data: dict[str, Any]) -> str:
    _require(len(payload) == data["resource_size"], "not the main disc ROST resource")
    _require(payload[:32].hex() == data["resource_header_hex"], "foreign ROST wrapper")
    body = payload[32:]
    _require(body[:64].hex() == data["body_prefix_hex"], "foreign ROST preamble")
    for pin in data["structure_pins"]:
        raw = bytes.fromhex(pin["hex"])
        _require(body[pin["offset"]:pin["offset"] + len(raw)] == raw,
                 "foreign team or team-label table")
    refs = _text_references(body)
    states = set()
    for cell in data["cells"]:
        start, size, pointer = cell["body_offset"], cell["allocation_bytes"], cell["pointer_offset"]
        _require(_relative(body, pointer) == start, "foreign team-name string pointer")
        users = [(field, target) for field, target in refs if start <= target < start + size]
        _require(users == [(pointer, start)], "team-name allocation has a shared or interior reference")
        before = encode_fixed_utf16le(cell["retail"], size, cell["field"])
        after = encode_fixed_utf16le(cell["written"], size, cell["field"])
        raw = body[start:start + size]
        _require(raw in (before, after), f"foreign {cell['domain']} {cell['team_index']} {cell['field']}")
        if before != after:
            states.add("retail" if raw == before else "applied")
    _require(len(states) == 1, "mixed retail and 2026 team-name strings")
    return states.pop()


def status(payload: bytes) -> str:
    """retail / applied / foreign for a complete main ROST resource."""
    try:
        return _inspect(payload, manifest())
    except (ValueError, OSError, KeyError, struct.error):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, dict[str, Any]]:
    """Validate every owned span before returning a modified private byte copy."""
    data = manifest()
    state = _inspect(payload, data)
    out = bytearray(payload)
    writes = []
    for cell in data["cells"]:
        if cell["retail"] == cell["written"]:
            continue
        start, size = 32 + cell["body_offset"], cell["allocation_bytes"]
        out[start:start + size] = encode_fixed_utf16le(cell["written"], size, cell["field"])
        writes.append({**cell, "resource_offset": start,
                       "character_limit": size // 2 - 1,
                       "fallback": cell["desired"] != cell["written"]})
    result = bytes(out)
    _require(_inspect(result, data) == "applied", "2026 team-name readback failed")
    return result, {"schema": data["schema"], "status": "applied", "already_applied": state == "applied",
                    "experimental": True, "witnessed": False, "outer_index": ROST_OUTER_INDEX,
                    "before_sha256": hashlib.sha256(payload).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest(),
                    "writes": writes, "changed_spans": 0 if state == "applied" else len(writes),
                    "growth_bytes": 0, "strg_writes": 0,
                    "note": "Short forms use the existing name space. New disc rosters only; existing saves keep their names."}


def read_team_identities(payload: bytes, *, enabled: bool = False) -> list[dict[str, Any]]:
    """Team Identity reads actual source or planned strings, never display-only aliases."""
    if enabled:
        payload, _receipt = apply(payload)
    _require(len(payload) == rr.RESOURCE_SIZE and payload[:4] == b"ROST", "not a disc ROST")
    doc = rr.RosterDocument(payload[32:])
    return [{"index": team.index, "city": team.city, "nickname": team.nickname,
             "abbreviation": team.abbreviation, "display": f"{team.city} {team.nickname}"}
            for team in doc.teams[:32]]


def catalog_overrides(catalog, *, enabled: bool = False,
                      value_lookup: Callable[[Any], str] | None = None) -> dict[str, str]:
    """Values for the protected Studio facade's text_value() when the option is on.

    The catalog already maps Team Identity to these same ROST cells. Conflicting
    manual edits refuse explicitly. Historic resources never receive aliases.
    This is a preview; the grouped Build pass owns both identity and label writes.
    """
    if not enabled:
        return {}
    assets = {asset.asset_id: asset for asset in catalog.assets}
    values = {}
    states = set()
    for cell in manifest()["cells"]:
        key = f"nfl2k5.text.rost.5.{cell['domain']}.{cell['team_index']}.{cell['field']}"
        asset = assets.get(key)
        _require(asset is not None, f"Team Identity lacks {key}")
        current = value_lookup(asset) if value_lookup else asset.value
        _require(current in (cell["retail"], cell["written"]), f"2026 names conflict with a manual edit to {asset.label}")
        if cell["retail"] != cell["written"]:
            states.add("retail" if current == cell["retail"] else "applied")
        values[key] = cell["written"]
    _require(len(states) == 1, "mixed retail and 2026 catalog names")
    return values


def image_status(path: Path | str) -> str:
    with rr._outer_image()(path) as archive:
        entry = archive.entries[ROST_OUTER_INDEX]
        if entry.size != rr.RESOURCE_SIZE:
            return "foreign"
        return status(archive.read(entry.virtual_offset, entry.size))


def apply_to_image(path: Path | str, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Build adapter: write only the caller's disposable image copy, never a save.

    OuterImage resolves relocated packs and closes all descriptors on failure.
    Only the 593,792-byte ROST is read, even on multi-gigabyte images.
    """
    with rr._outer_image()(path, writable=True) as archive:
        entry = archive.entries[ROST_OUTER_INDEX]
        _require(entry.size == rr.RESOURCE_SIZE, "not the main roster allocation")
        before = archive.read(entry.virtual_offset, entry.size)
        after, receipt = apply(before)
        if after != before:
            if progress:
                progress("Writing 2026 team names with fixed-length short forms")
            _require(archive.read(entry.virtual_offset, entry.size) == before,
                     "roster changed after team-name preview")
            _require(archive.write(entry.virtual_offset, after) == len(after), "short team-name write")
            _require(archive.read(entry.virtual_offset, entry.size) == after, "team-name image readback differs")
    return {**receipt, "virtual_offset": entry.virtual_offset}
