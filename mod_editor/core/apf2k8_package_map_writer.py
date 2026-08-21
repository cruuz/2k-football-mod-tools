"""Staged APF formation package-map edits (who lines up).

This is the product writer for MASTER formation ``+0x11``. Each formation's
11-byte map is a permutation of roles 0..10. Role 8 is TE and role 9 is WR.
The other nine roles are shown as numbers; their roster names are not proved.

A project stores formation index + the 11 role bytes. Build writes those
bytes into the copied MASTER PLAY. Whether the game's on-field look changes
at runtime is unproved. This does not change which formation the CPU picks
on 3rd-and-long.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Iterable, Mapping, Sequence

from .apf2k8_playbook_route_writer import (
    MASTER_ASSET_ID,
    RouteCloneRequest,
    compile_route_clones,
    encode_master_play_body,
    read_master_play_body,
)
from .errors import ValidationError


PROVIDER_KIND = "formation_package_map"
REPORT_SCHEMA = "apf2k8_formation_package_map/v1"
PAYLOAD_SCHEMA = "apf2k8_formation_package_map_replacement/v1"
MASTER_OUTER_INDEX = 180
PACKAGE_MAP_SIZE = 11
APF_PACKAGE_MAP_OFFSET_IN_FORMATION = 0x11
APF_FORMATION_SIZE = 0xB8
APF_FORMATION_BASE = 0x0244
APF_MASTER_BODY_SIZE = 0x2C750
APF_FORMATION_COUNT_OFFSET = 0x34
APF_FORMATION_COUNT_MAX = 176
APF_PACKAGE_MAP_ROLE_TE = 8
APF_PACKAGE_MAP_ROLE_WR3 = 9

PROVED_ROLE_NAMES = {
    APF_PACKAGE_MAP_ROLE_TE: "TE",
    APF_PACKAGE_MAP_ROLE_WR3: "WR",
}

HONESTY = (
    "This writes a formation's 11 role bytes. Whether the on-field look "
    "changes in the game is unproved. It does not change which formation the "
    "CPU picks on 3rd-and-long. Role 8 is TE and role 9 is WR. The other "
    "roles stay numbered until they are proved. After Build, check the "
    "formation in Xenia."
)


def _require_apf_master_body(raw: bytes) -> None:
    if len(raw) != APF_MASTER_BODY_SIZE:
        raise ValidationError(
            f"APF MASTER PLAY body is {len(raw):,} bytes; "
            f"{APF_MASTER_BODY_SIZE:,} were expected."
        )


def apf_formation_count(raw_body: bytes) -> int:
    _require_apf_master_body(raw_body)
    count = struct.unpack_from(">I", raw_body, APF_FORMATION_COUNT_OFFSET)[0]
    if not 1 <= count <= APF_FORMATION_COUNT_MAX:
        raise ValidationError(
            f"APF MASTER formation count {count} is outside 1.."
            f"{APF_FORMATION_COUNT_MAX}."
        )
    end = APF_FORMATION_BASE + count * APF_FORMATION_SIZE
    if end > len(raw_body):
        raise ValidationError("APF formation table overruns the MASTER body.")
    return count


def apf_formation_package_map_offset(formation_index: int) -> int:
    if formation_index < 0:
        raise ValidationError(
            f"formation_index must be non-negative; got {formation_index}."
        )
    return (
        APF_FORMATION_BASE
        + formation_index * APF_FORMATION_SIZE
        + APF_PACKAGE_MAP_OFFSET_IN_FORMATION
    )


def _apf_relative(raw_body: bytes, field: int) -> int:
    if field < 0 or field + 4 > len(raw_body):
        raise ValidationError("APF formation name pointer is out of range.")
    stored = struct.unpack_from(">i", raw_body, field)[0]
    target = field - 1 + stored
    if not 0 <= target < len(raw_body):
        raise ValidationError(
            f"APF formation name pointer at 0x{field:x} resolves outside the body."
        )
    return target


def read_apf_formation_name(raw_body: bytes, formation_index: int) -> str:
    count = apf_formation_count(raw_body)
    if not 0 <= formation_index < count:
        raise ValidationError(
            f"formation_index must be 0..{count - 1}; got {formation_index}."
        )
    field = APF_FORMATION_BASE + formation_index * APF_FORMATION_SIZE
    offset = _apf_relative(raw_body, field)
    if offset & 1:
        raise ValidationError(
            f"APF formation {formation_index} name is not UTF-16 aligned."
        )
    cursor = offset
    while cursor + 2 <= len(raw_body):
        if raw_body[cursor : cursor + 2] == b"\0\0":
            try:
                name = raw_body[offset:cursor].decode("utf-16be")
            except UnicodeDecodeError as exc:
                raise ValidationError(
                    f"APF formation {formation_index} name is not UTF-16BE."
                ) from exc
            if not name:
                raise ValidationError(
                    f"APF formation {formation_index} has an empty name."
                )
            return name
        cursor += 2
    raise ValidationError(
        f"APF formation {formation_index} name is unterminated."
    )


def read_apf_formation_package_map(
    raw_body: bytes, formation_index: int
) -> tuple[int, ...]:
    count = apf_formation_count(raw_body)
    if not 0 <= formation_index < count:
        raise ValidationError(
            f"formation_index must be 0..{count - 1}; got {formation_index}."
        )
    offset = apf_formation_package_map_offset(formation_index)
    chunk = raw_body[offset : offset + PACKAGE_MAP_SIZE]
    if len(chunk) != PACKAGE_MAP_SIZE:
        raise ValidationError("APF package map lies outside the MASTER body.")
    return tuple(chunk)


def build_apf_formation_package_map_patch(
    raw_body: bytes,
    formation_index: int,
    new_map: Sequence[int],
) -> bytes:
    _require_apf_master_body(raw_body)
    new_bytes = bytes(PackageMapChange(formation_index, tuple(new_map)).new_map)
    old = read_apf_formation_package_map(raw_body, formation_index)
    offset = apf_formation_package_map_offset(formation_index)
    out = bytearray(raw_body)
    out[offset : offset + PACKAGE_MAP_SIZE] = new_bytes
    result = bytes(out)
    changed = sum(1 for a, b in zip(raw_body, result, strict=True) if a != b)
    expected = sum(1 for a, b in zip(old, new_bytes) if a != b)
    if changed != expected:
        raise ValidationError(
            "APF package-map patch leaked outside the 11-byte map region."
        )
    return result


def verify_apf_formation_package_map_patch(
    source: bytes,
    patched: bytes,
    formation_index: int,
    expected_new_map: Sequence[int],
) -> None:
    _require_apf_master_body(source)
    _require_apf_master_body(patched)
    expected = bytes(PackageMapChange(formation_index, tuple(expected_new_map)).new_map)
    if len(source) != len(patched):
        raise ValidationError(
            f"Patched MASTER length {len(patched)} != source {len(source)}."
        )
    offset = apf_formation_package_map_offset(formation_index)
    if patched[offset : offset + PACKAGE_MAP_SIZE] != expected:
        raise ValidationError(
            f"APF formation {formation_index} map does not match the staged map."
        )
    for index, (left, right) in enumerate(zip(source, patched, strict=True)):
        if offset <= index < offset + PACKAGE_MAP_SIZE:
            continue
        if left != right:
            raise ValidationError(
                f"Byte {index} changed outside APF formation {formation_index} "
                "package-map region."
            )
    if read_apf_formation_package_map(patched, formation_index) != tuple(expected):
        raise ValidationError("Re-read APF package map does not match expected.")


def role_label(role: int) -> str:
    name = PROVED_ROLE_NAMES.get(int(role))
    if name is None:
        return f"role {int(role)}"
    return f"{name} (role {int(role)})"


def package_map_selector(formation_index: int) -> str:
    return f"apf:pkgmap:{MASTER_ASSET_ID}:f{int(formation_index)}"


@dataclass(frozen=True, slots=True)
class PackageMapChange:
    """One formation's replacement 11-byte role map."""

    formation_index: int
    new_map: tuple[int, ...]

    def __post_init__(self) -> None:
        if type(self.formation_index) is not int or self.formation_index < 0:
            raise ValidationError(
                f"formation_index must be a non-negative integer; got {self.formation_index!r}."
            )
        if len(self.new_map) != PACKAGE_MAP_SIZE:
            raise ValidationError(
                f"Package map must have {PACKAGE_MAP_SIZE} roles; got {len(self.new_map)}."
            )
        values: list[int] = []
        for item in self.new_map:
            if type(item) is not int:
                raise ValidationError(
                    f"Package map roles must be integers; got {item!r}."
                )
            values.append(item)
        if sorted(values) != list(range(PACKAGE_MAP_SIZE)):
            raise ValidationError(
                "Package map must be a permutation of 0..10 "
                f"(got {list(self.new_map)})."
            )
        object.__setattr__(self, "new_map", tuple(values))

    @property
    def selector(self) -> str:
        return package_map_selector(self.formation_index)

    def metadata(self) -> dict[str, object]:
        return {
            "formation_index": self.formation_index,
            "new_map": list(self.new_map),
        }


def change_from_mapping(value: Mapping[str, object]) -> PackageMapChange:
    if set(value) != {"formation_index", "new_map"}:
        raise ValidationError("A package-map edit has unsupported fields.")
    formation_index = value.get("formation_index")
    if type(formation_index) is not int:
        raise ValidationError(
            f"formation_index must be an integer; got {formation_index!r}."
        )
    raw_map = value.get("new_map")
    if not isinstance(raw_map, (list, tuple)):
        raise ValidationError("Package map must be a list of 11 role ids.")
    return PackageMapChange(formation_index, tuple(raw_map))


def encode_package_map_payload(change: PackageMapChange) -> bytes:
    payload = {
        "schema": PAYLOAD_SCHEMA,
        "selector": change.selector,
        "formation_index": change.formation_index,
        "new_map": list(change.new_map),
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def decode_package_map_payload(raw: bytes, expected_selector: str) -> PackageMapChange:
    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError(
                    f"Package-map payload repeats JSON key {key!r}: {expected_selector}"
                )
            result[key] = value
        return result

    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except ValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("Package-map payload is not JSON.") from exc
    except RecursionError as exc:
        raise ValidationError(
            "Package-map payload is too deeply nested to be JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise ValidationError("Package-map payload is not an object.")
    if payload.get("schema") != PAYLOAD_SCHEMA:
        raise ValidationError("Package-map payload schema changed.")
    if payload.get("selector") != expected_selector:
        raise ValidationError("Package-map payload selector changed.")
    change = change_from_mapping(
        {
            "formation_index": payload.get("formation_index"),
            "new_map": payload.get("new_map"),
        }
    )
    if change.selector != expected_selector:
        raise ValidationError("Package-map payload formation index changed.")
    return change


def list_apf_formations(raw_body: bytes) -> tuple[tuple[int, str, tuple[int, ...]], ...]:
    """Every MASTER formation: index, name, current 11-byte map."""

    count = apf_formation_count(raw_body)
    rows = []
    for index in range(count):
        rows.append(
            (
                index,
                read_apf_formation_name(raw_body, index),
                read_apf_formation_package_map(raw_body, index),
            )
        )
    return tuple(rows)


def swap_map_slots(package_map: Sequence[int], left: int, right: int) -> tuple[int, ...]:
    """Exchange the roles in two on-field slots. Stays a permutation of 0..10."""

    values = [int(item) for item in package_map]
    if len(values) != PACKAGE_MAP_SIZE:
        raise ValidationError(
            f"Package map must have {PACKAGE_MAP_SIZE} roles; got {len(values)}."
        )
    if not 0 <= left < PACKAGE_MAP_SIZE or not 0 <= right < PACKAGE_MAP_SIZE:
        raise ValidationError("Slot index must be 0..10.")
    values[left], values[right] = values[right], values[left]
    return PackageMapChange(0, tuple(values)).new_map


def put_role_in_slot(package_map: Sequence[int], slot: int, role: int) -> tuple[int, ...]:
    """Move a role onto ``slot`` by swapping with wherever that role sits now."""

    values = [int(item) for item in package_map]
    if int(role) not in values:
        raise ValidationError(f"Role {role} is not in this formation map.")
    current = values.index(int(role))
    return swap_map_slots(values, int(slot), current)


def swap_te_and_wr(package_map: Sequence[int]) -> tuple[int, ...]:
    """Swap roles 8 and 9 wherever they sit. Runtime effect is unproved."""

    current = PackageMapChange(0, tuple(package_map)).new_map
    if (
        APF_PACKAGE_MAP_ROLE_TE not in current
        or APF_PACKAGE_MAP_ROLE_WR3 not in current
    ):
        raise ValidationError("This map needs both TE (role 8) and WR (role 9).")
    swapped = tuple(
        APF_PACKAGE_MAP_ROLE_WR3
        if value == APF_PACKAGE_MAP_ROLE_TE
        else APF_PACKAGE_MAP_ROLE_TE
        if value == APF_PACKAGE_MAP_ROLE_WR3
        else value
        for value in current
    )
    return PackageMapChange(0, swapped).new_map


def slot_summary(package_map: Sequence[int]) -> str:
    te_at = wr_at = None
    for slot, role in enumerate(package_map):
        if int(role) == APF_PACKAGE_MAP_ROLE_TE:
            te_at = slot
        elif int(role) == APF_PACKAGE_MAP_ROLE_WR3:
            wr_at = slot
    bits = []
    if te_at is not None:
        bits.append(f"TE is stored in map slot {te_at + 1}")
    if wr_at is not None:
        bits.append(f"WR is stored in map slot {wr_at + 1}")
    return "; ".join(bits) if bits else "No proved TE/WR roles in this map."


def compile_package_maps(
    raw_body: bytes,
    changes: Iterable[PackageMapChange],
) -> bytes:
    """Apply every map on a private MASTER body. Touches only +0x11 regions."""

    normalized = tuple(changes)
    seen: set[int] = set()
    working = raw_body
    applied = 0
    for change in normalized:
        if change.formation_index in seen:
            raise ValidationError(
                f"Two package-map edits name formation {change.formation_index}."
            )
        seen.add(change.formation_index)
        current = read_apf_formation_package_map(working, change.formation_index)
        if current == change.new_map:
            continue
        patched = build_apf_formation_package_map_patch(
            working, change.formation_index, change.new_map
        )
        verify_apf_formation_package_map_patch(
            working, patched, change.formation_index, change.new_map
        )
        working = patched
        applied += 1
    for change in normalized:
        got = read_apf_formation_package_map(working, change.formation_index)
        if got != change.new_map:
            raise ValidationError(
                f"Formation {change.formation_index} map did not stick."
            )
    if not seen:
        raise ValidationError("Select at least one formation package map to edit.")
    if applied == 0:
        raise ValidationError(
            "These who-lines-up maps already match the game; nothing would "
            f"change (formations {sorted(seen)})."
        )
    count = apf_formation_count(raw_body)
    for index in range(count):
        if index in seen:
            continue
        if read_apf_formation_package_map(working, index) != read_apf_formation_package_map(
            raw_body, index
        ):
            raise ValidationError(
                f"Package-map compile leaked onto formation {index}."
            )
    return working


def compile_master_play_edits_detailed(
    raw_body: bytes,
    *,
    package_maps: Iterable[PackageMapChange] = (),
    routes: Iterable[RouteCloneRequest] = (),
) -> tuple[bytes, tuple[tuple[int, int], ...], tuple[PackageMapChange, ...]]:
    """Apply package maps, then route clones. Returns body, byte ranges, and
    the maps that actually changed a byte."""

    maps = tuple(package_maps)
    route_requests = tuple(routes)
    if not maps and not route_requests:
        raise ValidationError("No MASTER PLAY edits were selected.")
    seen: set[int] = set()
    for change in maps:
        if change.formation_index in seen:
            raise ValidationError(
                f"Two package-map edits name formation {change.formation_index}."
            )
        seen.add(change.formation_index)
    effective_maps = tuple(
        change
        for change in maps
        if read_apf_formation_package_map(raw_body, change.formation_index)
        != change.new_map
    )
    if maps and not effective_maps and not route_requests:
        raise ValidationError(
            "These who-lines-up maps already match the game; nothing would "
            f"change (formations {sorted(seen)})."
        )
    ranges: list[tuple[int, int]] = []
    working = raw_body
    if effective_maps:
        working = compile_package_maps(working, effective_maps)
        for change in effective_maps:
            offset = apf_formation_package_map_offset(change.formation_index)
            ranges.append((offset, offset + PACKAGE_MAP_SIZE))
    if route_requests:
        compiled = compile_route_clones(working, route_requests)
        ranges.extend(compiled.changed_ranges)
        working = compiled.replacement
    return working, tuple(sorted(ranges)), effective_maps


def compile_master_play_edits(
    raw_body: bytes,
    *,
    package_maps: Iterable[PackageMapChange] = (),
    routes: Iterable[RouteCloneRequest] = (),
) -> bytes:
    """Apply package maps, then route clones, on one MASTER body."""

    body, _ranges, _effective = compile_master_play_edits_detailed(
        raw_body, package_maps=package_maps, routes=routes
    )
    return body


def build_master_play_edits(
    index_path: Path,
    *,
    package_maps: Iterable[PackageMapChange] = (),
    routes: Iterable[RouteCloneRequest] = (),
) -> tuple[int, bytes, dict[str, object]]:
    """Compile maps and/or routes into outer 180. Source 0A is not written."""

    maps = tuple(package_maps)
    route_requests = tuple(routes)
    original = read_master_play_body(index_path)
    body, ranges, effective_maps = compile_master_play_edits_detailed(
        original, package_maps=maps, routes=route_requests
    )
    entry_bytes, h7a = encode_master_play_body(index_path, body)
    changed = [
        {
            "formation_index": change.formation_index,
            "formation_name": read_apf_formation_name(original, change.formation_index),
            "old_map": list(read_apf_formation_package_map(original, change.formation_index)),
            "new_map": list(change.new_map),
            "resource_offset": apf_formation_package_map_offset(change.formation_index),
        }
        for change in effective_maps
    ]
    report: dict[str, object] = {
        "schema": REPORT_SCHEMA,
        "kind": "master_play_edits",
        "outer_index": MASTER_OUTER_INDEX,
        "honesty": HONESTY,
        "package_maps": changed,
        "package_maps_already_matching": len(maps) - len(effective_maps),
        "route_count": len(route_requests),
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "result_sha256": hashlib.sha256(body).hexdigest(),
        "changed_byte_count": sum(
            1 for left, right in zip(original, body, strict=True) if left != right
        ),
        "changed_ranges": [[start, end] for start, end in ranges],
        "h7a_transport": h7a.get("h7a_transport"),
        "output_entry_size": h7a.get("output_entry_size"),
        "output_entry_sha256": h7a.get("output_entry_sha256"),
        "writer_schema": REPORT_SCHEMA,
        "claims": {
            "package_map_bytes_edited": bool(effective_maps),
            "route_clones_edited": bool(route_requests),
            "third_and_long_director_changed": False,
            "runtime_proved": False,
            "source_0a_untouched": True,
        },
    }
    return MASTER_OUTER_INDEX, entry_bytes, report


__all__ = [
    "APF_FORMATION_BASE",
    "APF_FORMATION_COUNT_OFFSET",
    "APF_FORMATION_SIZE",
    "APF_MASTER_BODY_SIZE",
    "APF_PACKAGE_MAP_OFFSET_IN_FORMATION",
    "APF_PACKAGE_MAP_ROLE_TE",
    "APF_PACKAGE_MAP_ROLE_WR3",
    "HONESTY",
    "MASTER_OUTER_INDEX",
    "PAYLOAD_SCHEMA",
    "PROVED_ROLE_NAMES",
    "PROVIDER_KIND",
    "REPORT_SCHEMA",
    "PackageMapChange",
    "build_master_play_edits",
    "change_from_mapping",
    "compile_master_play_edits",
    "compile_master_play_edits_detailed",
    "compile_package_maps",
    "decode_package_map_payload",
    "encode_package_map_payload",
    "list_apf_formations",
    "package_map_selector",
    "put_role_in_slot",
    "role_label",
    "slot_summary",
    "swap_map_slots",
    "swap_te_and_wr",
]
