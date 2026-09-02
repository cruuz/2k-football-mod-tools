"""Format-preserving NFL 2K5 PLAY assignment-route cloning.

The game-authored route/action nodes are still opaque.  This writer therefore
does one operation whose byte ownership is exact: point a target assignment at
an existing assignment chain in the *same* PLAY resource, while copying that
donor assignment's descriptor word.  No node, formation, string, play name, or
resource extent is authored, relocated, or interpreted.

Shareable projects store only logical book/play/slot selectors.  Retail
descriptor words, relative pointers, and node bytes are recovered from the
user's recognized source at build time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import struct
from typing import Any, Iterable, Mapping

from .errors import ValidationError
from .nfl2k5_playbook_inspector import (
    ASSIGNMENT_COUNT,
    NODE_BASE,
    NODE_SIZE,
    PLAY_BASE,
    PLAY_SIZE,
    Nfl2k5Playbook,
    parse_playbook_resource,
)
from .nfl2k5_source_cache import PACK0_SHA256, PACK0_SIZE
from .nfl2k5_universal_asset_index import Nfl2k5UniversalAssetIndex

try:
    from nfl_outer import FormatError, read_entry_range
except ImportError as exc:  # pragma: no cover - installation boundary
    raise RuntimeError("The NFL archive reader is unavailable") from exc


PROVIDER_KIND = "play_assignment_route"
REPORT_SCHEMA = "nfl2k5_play_assignment_route_clone/v1"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def route_selector(asset_id: str, play_index: int, slot_index: int) -> str:
    return f"play-route:{asset_id}:p{play_index}:s{slot_index}"


@dataclass(frozen=True, slots=True)
class PlayRouteCloneRequest:
    asset_id: str
    target_play_index: int
    target_slot_index: int
    donor_play_index: int
    donor_slot_index: int

    @property
    def selector(self) -> str:
        return route_selector(
            self.asset_id, self.target_play_index, self.target_slot_index
        )

    def provider_edit(self) -> dict[str, object]:
        return {"kind": PROVIDER_KIND, **asdict(self)}


@dataclass(frozen=True, slots=True)
class CompiledPlayRouteResource:
    asset_id: str
    selector: str
    source_sha256: str
    replacement_sha256: str
    changed_byte_count: int
    changed_ranges: tuple[tuple[int, int], ...]
    requests: tuple[PlayRouteCloneRequest, ...]
    replacement: bytes
    parsed_replacement: Nfl2k5Playbook
    report: Mapping[str, Any]


def _integer(value: object, label: str, *, maximum: int | None = None) -> int:
    if type(value) is not int or value < 0 or (
        maximum is not None and value > maximum
    ):
        suffix = f" through {maximum}" if maximum is not None else " or greater"
        raise ValidationError(f"{label} must be an integer from 0{suffix}.")
    return value


def request_from_mapping(value: Mapping[str, object]) -> PlayRouteCloneRequest:
    fields = {
        "asset_id", "target_play_index", "target_slot_index",
        "donor_play_index", "donor_slot_index",
    }
    if set(value) != fields:
        raise ValidationError("A PLAY route clone has unsupported fields.")
    asset_id = value.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id:
        raise ValidationError("A PLAY route clone needs a private asset selector.")
    return PlayRouteCloneRequest(
        asset_id,
        _integer(value.get("target_play_index"), "Target play index"),
        _integer(value.get("target_slot_index"), "Target slot", maximum=10),
        _integer(value.get("donor_play_index"), "Donor play index"),
        _integer(value.get("donor_slot_index"), "Donor slot", maximum=10),
    )


def _assignment_fields(play_index: int, slot_index: int) -> tuple[int, int]:
    play = PLAY_BASE + play_index * PLAY_SIZE
    descriptor = play + 8 + slot_index * 8
    return descriptor, descriptor + 4


def _signed_relative(field: int, target: int) -> bytes:
    delta = target - field + 1
    if not -(1 << 31) <= delta < (1 << 31):
        raise ValidationError("The donor PLAY chain pointer cannot be represented.")
    return struct.pack("<i", delta)


def _difference_ranges(before: bytes, after: bytes) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    start: int | None = None
    for index, (left, right) in enumerate(zip(before, after)):
        if left != right and start is None:
            start = index
        elif left == right and start is not None:
            result.append((start, index))
            start = None
    if start is not None:
        result.append((start, len(before)))
    return tuple(result)


def compile_play_route_clones(
    raw_resource: bytes,
    requests: Iterable[PlayRouteCloneRequest | Mapping[str, object]],
) -> CompiledPlayRouteResource:
    normalized = tuple(
        item if isinstance(item, PlayRouteCloneRequest)
        else request_from_mapping(item)
        for item in requests
    )
    if not normalized:
        raise ValidationError("Choose at least one assignment route to copy.")
    asset_ids = {item.asset_id for item in normalized}
    if len(asset_ids) != 1:
        raise ValidationError("One PLAY compiler call may edit only one playbook.")
    asset_id = next(iter(asset_ids))
    source = parse_playbook_resource(raw_resource, asset_id=asset_id)
    targets = {
        (item.target_play_index, item.target_slot_index) for item in normalized
    }
    if len(targets) != len(normalized):
        raise ValidationError("A PLAY project repeats one target assignment slot.")

    replacement = bytearray(raw_resource)
    allowed: list[range] = []
    report_rows: list[dict[str, object]] = []
    for item in normalized:
        if not 0 <= item.target_play_index < len(source.plays):
            raise ValidationError("Target play index is outside this PLAY book.")
        if not 0 <= item.donor_play_index < len(source.plays):
            raise ValidationError("Donor play index is outside this PLAY book.")
        if not 0 <= item.target_slot_index < ASSIGNMENT_COUNT \
                or not 0 <= item.donor_slot_index < ASSIGNMENT_COUNT:
            raise ValidationError("PLAY assignment slots must be between 0 and 10.")
        if (
            item.target_play_index == item.donor_play_index
            and item.target_slot_index == item.donor_slot_index
        ):
            raise ValidationError("Choose a different donor assignment route.")

        donor_play = source.plays[item.donor_play_index]
        target_play = source.plays[item.target_play_index]
        donor = donor_play.assignments[item.donor_slot_index]
        target = target_play.assignments[item.target_slot_index]
        descriptor_body, pointer_body = _assignment_fields(
            item.target_play_index, item.target_slot_index
        )
        descriptor = 0x20 + descriptor_body
        pointer = 0x20 + pointer_body
        struct.pack_into("<I", replacement, descriptor, donor.descriptor_word)
        node_target = NODE_BASE + donor.chain_start_index * NODE_SIZE
        replacement[pointer:pointer + 4] = _signed_relative(pointer_body, node_target)
        allowed.extend((range(descriptor, descriptor + 4), range(pointer, pointer + 4)))
        report_rows.append({
            "selector": item.selector,
            "target": {
                "play_index": item.target_play_index,
                "play_name": target_play.name,
                "slot_index": item.target_slot_index,
                "source_chain_start_index": target.chain_start_index,
            },
            "donor": {
                "play_index": item.donor_play_index,
                "play_name": donor_play.name,
                "slot_index": item.donor_slot_index,
                "chain_start_index": donor.chain_start_index,
                "chain_node_count": source.chain(donor.chain_start_index).node_count,
            },
        })

    rebuilt = bytes(replacement)
    if rebuilt == raw_resource:
        raise ValidationError(
            "Every selected donor already matches its target assignment route."
        )
    original_starts = {
        assignment.chain_start_index
        for play in source.plays for assignment in play.assignments
    }
    replacements_by_target = {
        (item.target_play_index, item.target_slot_index):
        source.plays[item.donor_play_index].assignments[
            item.donor_slot_index
        ].chain_start_index
        for item in normalized
    }
    resulting_starts = {
        replacements_by_target.get(
            (play.index, assignment.slot_index), assignment.chain_start_index
        )
        for play in source.plays for assignment in play.assignments
    }
    if resulting_starts != original_starts:
        raise ValidationError(
            "That copy would orphan an existing route chain. Choose a target "
            "whose current chain is also used by another assignment, or copy "
            "routes as a balanced multi-slot swap."
        )
    changed = _difference_ranges(raw_resource, rebuilt)
    allowed_offsets = {index for span in allowed for index in span}
    if any(index not in allowed_offsets for start, end in changed for index in range(start, end)):
        raise ValidationError("PLAY route compilation changed an unowned byte.")
    reparsed = parse_playbook_resource(rebuilt, asset_id=asset_id)
    for item in normalized:
        actual = reparsed.plays[item.target_play_index].assignments[item.target_slot_index]
        donor = source.plays[item.donor_play_index].assignments[item.donor_slot_index]
        if (
            actual.descriptor_word != donor.descriptor_word
            or actual.chain_start_index != donor.chain_start_index
        ):
            raise ValidationError("Compiled PLAY assignment did not resolve to its donor.")

    changed_count = sum(end - start for start, end in changed)
    selector = (
        normalized[0].selector
        if len(normalized) == 1 else f"play-route-bundle:{asset_id}"
    )
    report = {
        "schema": REPORT_SCHEMA,
        "asset_id": asset_id,
        "selector": selector,
        "source_sha256": _sha256(raw_resource),
        "replacement_sha256": _sha256(rebuilt),
        "resource_size": len(rebuilt),
        "changed_byte_count": changed_count,
        "changed_ranges": [[start, end] for start, end in changed],
        "edits": report_rows,
        "claims": {
            "same_play_resource_donors_only": True,
            "descriptor_and_relative_chain_pointer_only": True,
            "existing_game_authored_node_chains_reused": True,
            "declared_chain_start_partition_preserved": True,
            "resource_extent_preserved": True,
            "source_and_replacement_fully_reparsed": True,
            "names_formations_nodes_and_non_target_bytes_preserved": True,
            "waypoint_coordinate_or_opcode_semantics_claimed": False,
            "custom_play_save_container_claimed": False,
            "contains_retail_bytes": False,
        },
    }
    return CompiledPlayRouteResource(
        asset_id, selector, report["source_sha256"], report["replacement_sha256"],
        changed_count, changed, normalized, rebuilt, reparsed, report,
    )


def build_unified_play_route_import(
    index_path: Path,
    inventory_path: Path,
    asset_id: str,
    requests: Iterable[PlayRouteCloneRequest | Mapping[str, object]],
) -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]:
    """Resolve, compile, and locate one fixed PLAY resource in archive pack 0."""

    sidecar = inventory_path.parent / "universal-assets-v1.sqlite3"
    index = Nfl2k5UniversalAssetIndex(inventory_path, index_path, sidecar)
    record = index.get(asset_id)
    if record.kind != "PLAY" or record.raw_size != 0x20 + 0x13390:
        raise ValidationError("That logical selector is not a fixed NFL 2K5 PLAY resource.")
    entry = index.archive.entries[record.outer_index]
    try:
        raw = read_entry_range(index.archive, entry, record.chunk_offset, record.raw_size)
    except (OSError, FormatError) as exc:
        raise ValidationError(f"Could not read the selected PLAY resource: {exc}") from exc
    compiled = compile_play_route_clones(raw, requests)
    absolute_archive = entry.virtual_offset + record.chunk_offset
    pack = next(
        (row for row in index.archive.packs
         if row.virtual_start <= absolute_archive
         and absolute_archive + record.raw_size <= row.virtual_end),
        None,
    )
    if pack is None or pack.name != "0":
        raise ValidationError("The selected PLAY resource no longer belongs to archive pack 0.")
    pack_offset = absolute_archive - pack.virtual_start
    target = {
        "selector": compiled.selector,
        "asset_id": asset_id,
        "outer_index": record.outer_index,
        "chunk_index": record.chunk_index,
        "resource_size": record.raw_size,
        "xiso_pack_path": "vc_53450030/0",
        "xiso_pack_sector": 796_479,
        "xiso_pack_size": PACK0_SIZE,
        "xiso_pack_sha256": PACK0_SHA256,
        "pack_offset": pack_offset,
        "xiso_absolute_span_offset": 1_631_188_992 + pack_offset,
        "span_sha256": compiled.source_sha256,
    }
    report = dict(compiled.report)
    report["target"] = target
    return compiled.replacement, [], report, compiled.selector, target


__all__ = [
    "CompiledPlayRouteResource",
    "PROVIDER_KIND",
    "PlayRouteCloneRequest",
    "build_unified_play_route_import",
    "compile_play_route_clones",
    "request_from_mapping",
    "route_selector",
]
