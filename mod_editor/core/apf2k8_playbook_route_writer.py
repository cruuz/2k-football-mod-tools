"""Format-preserving APF 2K8 PLAY assignment-route cloning.

APF's game-authored route/action nodes remain opaque.  This module therefore
owns one deliberately bounded operation: copy a donor assignment descriptor
and make the target assignment point at the donor's existing node chain in the
same MASTER PLAY resource.  The relative pointer is re-encoded for its target
field; route nodes, names, formations, membership masks, counts, and resource
extent are never rewritten or interpreted.

Shareable project data needs only the logical play/slot selectors.  No retail
descriptor, pointer, or route-node bytes are required by :class:`RouteCloneRequest`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
from typing import Any, Iterable, Mapping

from .errors import ValidationError

# Keep the product on the same strict grammar used by its live PLAY inspector.
from mod_editor.apf_studio.backend import ensure_tools_importable


ensure_tools_importable()
import playbook_inventory  # type: ignore  # noqa: E402
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_texture_patch  # type: ignore  # noqa: E402


PROVIDER_KIND = "play_assignment_route"
REPORT_SCHEMA = "apf2k8_play_assignment_route_clone/v1"
PAYLOAD_SCHEMA = "apf2k8_play_assignment_route_replacement/v1"
MASTER_ASSET_ID = "apf:playbook:180:0"
ROUTE_ORPHAN_MESSAGE = (
    "This route is only used on the target play, so Copy would delete it. "
    "Use Swap instead — that trades the two routes and keeps both."
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def route_selector(asset_id: str, play_index: int, slot_index: int) -> str:
    return f"play-route:{asset_id}:p{play_index}:s{slot_index}"


@dataclass(frozen=True, slots=True)
class RouteCloneRequest:
    """Logical same-resource donor and target coordinates only."""

    target_play_index: int
    target_slot_index: int
    donor_play_index: int
    donor_slot_index: int
    asset_id: str = MASTER_ASSET_ID

    @property
    def selector(self) -> str:
        return route_selector(
            self.asset_id, self.target_play_index, self.target_slot_index
        )

    def provider_edit(self) -> dict[str, object]:
        return {"kind": PROVIDER_KIND, **asdict(self)}


# Keep the cross-title spelling available to callers while the public UI uses
# the shorter neutral name above.
PlayRouteCloneRequest = RouteCloneRequest


@dataclass(frozen=True, slots=True)
class CompiledRouteClone:
    asset_id: str
    selector: str
    source_sha256: str
    replacement_sha256: str
    changed_byte_count: int
    changed_ranges: tuple[tuple[int, int], ...]
    requests: tuple[RouteCloneRequest, ...]
    replacement: bytes
    parsed_replacement: Mapping[str, object]
    report: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CompiledRouteCloneEntry:
    """Private fixed-allocation outer entry plus its retail-free receipt."""

    outer_index: int
    entry_bytes: bytes
    compiled_resource: CompiledRouteClone
    report: Mapping[str, Any]


def _integer(value: object, label: str, *, maximum: int | None = None) -> int:
    if type(value) is not int or value < 0 or (
        maximum is not None and value > maximum
    ):
        suffix = f" through {maximum}" if maximum is not None else " or greater"
        raise ValidationError(f"{label} must be an integer from 0{suffix}.")
    return value


def request_from_mapping(value: Mapping[str, object]) -> RouteCloneRequest:
    fields = {
        "asset_id",
        "target_play_index",
        "target_slot_index",
        "donor_play_index",
        "donor_slot_index",
    }
    if set(value) != fields:
        raise ValidationError("An APF PLAY route clone has unsupported fields.")
    asset_id = value.get("asset_id")
    if asset_id != MASTER_ASSET_ID:
        raise ValidationError("APF route cloning is limited to the MASTER PLAY resource.")
    return RouteCloneRequest(
        target_play_index=_integer(
            value.get("target_play_index"), "Target play index"
        ),
        target_slot_index=_integer(
            value.get("target_slot_index"),
            "Target assignment slot",
            maximum=playbook_inventory.SLOT_COUNT - 1,
        ),
        donor_play_index=_integer(
            value.get("donor_play_index"), "Donor play index"
        ),
        donor_slot_index=_integer(
            value.get("donor_slot_index"),
            "Donor assignment slot",
            maximum=playbook_inventory.SLOT_COUNT - 1,
        ),
        asset_id=asset_id,
    )


def encode_route_clone_payload(request: RouteCloneRequest) -> bytes:
    """Encode only logical selectors; never source-owned PLAY bytes."""

    normalized = request_from_mapping(asdict(request))
    return (
        json.dumps(
            {"schema": PAYLOAD_SCHEMA, "request": asdict(normalized)},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def decode_route_clone_payload(
    payload: bytes, target_id: str = "APF route clone"
) -> RouteCloneRequest:
    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError(
                    f"APF route-clone payload repeats JSON key {key!r}: {target_id}"
                )
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("utf-8"), object_pairs_hook=no_duplicates
        )
    except ValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(
            f"APF route-clone replacement is not valid UTF-8 JSON: {target_id}"
        ) from exc
    except RecursionError as exc:
        raise ValidationError(
            f"APF route-clone replacement is too deeply nested: {target_id}"
        ) from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema", "request"}
        or document.get("schema") != PAYLOAD_SCHEMA
        or not isinstance(document.get("request"), dict)
    ):
        raise ValidationError(f"APF route-clone payload is invalid: {target_id}")
    request = request_from_mapping(document["request"])
    if request.selector != target_id:
        raise ValidationError(
            f"APF route-clone payload target changed: {target_id}"
        )
    return request


def relay_candidates(
    body_or_parsed: bytes | Mapping[str, object],
    target_play: int,
    target_slot: int,
    donor_play: int,
    donor_slot: int,
) -> tuple[tuple[int, int], ...]:
    """Slots whose current chain start is shared by at least one other slot.

    The target slot itself, every slot on the donor play, and any slot routed
    to a unique chain are excluded; only the remaining assignments can carry a
    displaced chain without deleting it.
    """

    parsed = (
        body_or_parsed
        if isinstance(body_or_parsed, Mapping)
        else _parse(body_or_parsed)
    )
    _slot(parsed, target_play, target_slot, "Target")
    _slot(parsed, donor_play, donor_slot, "Donor")
    plays = parsed["plays"]
    assert isinstance(plays, list)
    multiplicity: dict[int, int] = {}
    for play in plays:
        assert isinstance(play, dict)
        for slot in play["slots"]:
            assert isinstance(slot, dict)
            node = int(slot["route_node_index"])
            multiplicity[node] = multiplicity.get(node, 0) + 1
    candidates: list[tuple[int, int]] = []
    for play_index, play in enumerate(plays):
        if play_index == donor_play:
            continue
        slots = play["slots"]
        assert isinstance(slots, list)
        for slot_index, slot in enumerate(slots):
            if play_index == target_play and slot_index == target_slot:
                continue
            if multiplicity[int(slot["route_node_index"])] >= 2:
                candidates.append((play_index, slot_index))
    return tuple(candidates)


def build_relayed_copy_requests(
    target: tuple[int, int],
    donor: tuple[int, int],
    relay: tuple[int, int],
) -> tuple[RouteCloneRequest, RouteCloneRequest]:
    """target <- donor plus relay <- target's original chain, as one batch."""

    return (
        RouteCloneRequest(target[0], target[1], donor[0], donor[1]),
        RouteCloneRequest(relay[0], relay[1], target[0], target[1]),
    )


def _assignment_fields(play_index: int, slot_index: int) -> tuple[int, int]:
    play = (
        playbook_inventory.APF_PLAY_BASE
        + play_index * playbook_inventory.APF_PLAY_SIZE
    )
    descriptor = play + 0x0C + slot_index * 8
    return descriptor, descriptor + 4


def _signed_relative(field: int, target: int) -> bytes:
    delta = target - field + 1
    if not -(1 << 31) <= delta < (1 << 31):
        raise ValidationError("The donor APF PLAY chain pointer cannot be represented.")
    return struct.pack(">i", delta)


def _difference_ranges(before: bytes, after: bytes) -> tuple[tuple[int, int], ...]:
    if len(before) != len(after):
        raise ValidationError("APF PLAY route compilation changed the resource size.")
    result: list[tuple[int, int]] = []
    start: int | None = None
    for index, (left, right) in enumerate(zip(before, after, strict=True)):
        if left != right and start is None:
            start = index
        elif left == right and start is not None:
            result.append((start, index))
            start = None
    if start is not None:
        result.append((start, len(before)))
    return tuple(result)


def _normalize_requests(
    requests: Iterable[RouteCloneRequest | Mapping[str, object]],
) -> tuple[RouteCloneRequest, ...]:
    normalized = tuple(
        item if isinstance(item, RouteCloneRequest) else request_from_mapping(item)
        for item in requests
    )
    if not normalized:
        raise ValidationError("Choose at least one APF assignment route to copy.")
    if {item.asset_id for item in normalized} != {MASTER_ASSET_ID}:
        raise ValidationError("One APF route compiler call may edit only MASTER PLAY.")
    targets = {
        (item.target_play_index, item.target_slot_index) for item in normalized
    }
    if len(targets) != len(normalized):
        raise ValidationError("An APF PLAY project repeats one target assignment slot.")
    return normalized


def _parse(raw_resource: bytes) -> Mapping[str, object]:
    try:
        return playbook_inventory.parse_apf_body(raw_resource, 180, 0)
    except playbook_inventory.PlaybookError as exc:
        raise ValidationError(f"APF MASTER PLAY validation failed: {exc}") from exc


def _slot(
    parsed: Mapping[str, object], play_index: int, slot_index: int, role: str
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    plays = parsed["plays"]
    assert isinstance(plays, list)
    if not 0 <= play_index < len(plays):
        raise ValidationError(f"{role} play index is outside APF MASTER PLAY.")
    if not 0 <= slot_index < playbook_inventory.SLOT_COUNT:
        raise ValidationError("APF assignment slots must be between 0 and 10.")
    play = plays[play_index]
    assert isinstance(play, dict)
    slots = play["slots"]
    assert isinstance(slots, list)
    slot = slots[slot_index]
    assert isinstance(slot, dict)
    return play, slot


def verify_route_clones(
    source: bytes,
    replacement: bytes,
    requests: Iterable[RouteCloneRequest | Mapping[str, object]],
) -> Mapping[str, object]:
    """Independently verify source-derived semantics and the exact write mask."""

    normalized = _normalize_requests(requests)
    source_book = _parse(source)
    rebuilt_book = _parse(replacement)
    if len(source) != len(replacement):
        raise ValidationError("APF PLAY route clone changed the fixed body extent.")

    allowed_offsets: set[int] = set()
    verified: list[dict[str, object]] = []
    for item in normalized:
        if (
            item.target_play_index == item.donor_play_index
            and item.target_slot_index == item.donor_slot_index
        ):
            raise ValidationError("Choose a different APF donor assignment route.")
        donor_play, donor = _slot(
            source_book, item.donor_play_index, item.donor_slot_index, "Donor"
        )
        target_play, source_target = _slot(
            source_book, item.target_play_index, item.target_slot_index, "Target"
        )
        _rebuilt_play, rebuilt_target = _slot(
            rebuilt_book, item.target_play_index, item.target_slot_index, "Target"
        )
        descriptor, pointer = _assignment_fields(
            item.target_play_index, item.target_slot_index
        )
        allowed_offsets.update(range(descriptor, pointer + 4))
        if (
            rebuilt_target["descriptor_word"] != donor["descriptor_word"]
            or rebuilt_target["route_node_offset"] != donor["route_node_offset"]
        ):
            raise ValidationError(
                "Compiled APF assignment does not resolve to its selected donor."
            )
        verified.append(
            {
                "selector": item.selector,
                "target": {
                    "play_index": item.target_play_index,
                    "play_name": target_play["name"],
                    "slot_index": item.target_slot_index,
                    "source_route_node_index": source_target["route_node_index"],
                },
                "donor": {
                    "play_index": item.donor_play_index,
                    "play_name": donor_play["name"],
                    "slot_index": item.donor_slot_index,
                    "route_node_index": donor["route_node_index"],
                },
            }
        )

    source_starts = {
        int(slot["route_node_index"])
        for play in source_book["plays"]
        for slot in play["slots"]
    }
    replacement_starts = {
        int(slot["route_node_index"])
        for play in rebuilt_book["plays"]
        for slot in play["slots"]
    }
    if replacement_starts != source_starts:
        raise ValidationError(ROUTE_ORPHAN_MESSAGE)

    changed = _difference_ranges(source, replacement)
    if not changed:
        raise ValidationError(
            "Every selected APF donor already matches its target assignment route."
        )
    for start, end in changed:
        if any(index not in allowed_offsets for index in range(start, end)):
            raise ValidationError("APF route compilation changed an unowned byte.")
    # These hashes come from two fresh parses and independently ensure the
    # opaque node pool and newly decoded formation-membership table stayed put.
    if (
        source_book["route_node_blob_sha256"]
        != rebuilt_book["route_node_blob_sha256"]
        or source_book["formation_play_membership_table"]
        != rebuilt_book["formation_play_membership_table"]
    ):
        raise ValidationError("APF route cloning changed a protected PLAY table.")
    return {
        "source_sha256": _sha256(source),
        "replacement_sha256": _sha256(replacement),
        "resource_size": len(replacement),
        "changed_ranges": [[start, end] for start, end in changed],
        "changed_byte_count": sum(end - start for start, end in changed),
        "edits": verified,
        "parsed_replacement": rebuilt_book,
    }


def compile_route_clones(
    raw_resource: bytes,
    requests: Iterable[RouteCloneRequest | Mapping[str, object]],
) -> CompiledRouteClone:
    """Compile exact stock route assignments into one fixed MASTER body."""

    normalized = _normalize_requests(requests)
    source = _parse(raw_resource)
    replacement = bytearray(raw_resource)
    for item in normalized:
        if (
            item.target_play_index == item.donor_play_index
            and item.target_slot_index == item.donor_slot_index
        ):
            raise ValidationError("Choose a different APF donor assignment route.")
        _target_play, _target = _slot(
            source, item.target_play_index, item.target_slot_index, "Target"
        )
        _donor_play, donor = _slot(
            source, item.donor_play_index, item.donor_slot_index, "Donor"
        )
        donor_descriptor = int(str(donor["descriptor_word"]), 16)
        donor_node_offset = int(donor["route_node_offset"])
        descriptor, pointer = _assignment_fields(
            item.target_play_index, item.target_slot_index
        )
        struct.pack_into(">I", replacement, descriptor, donor_descriptor)
        replacement[pointer : pointer + 4] = _signed_relative(
            pointer, donor_node_offset
        )

    rebuilt = bytes(replacement)
    verified = verify_route_clones(raw_resource, rebuilt, normalized)
    changed = tuple(tuple(row) for row in verified["changed_ranges"])
    selector = (
        normalized[0].selector
        if len(normalized) == 1
        else f"play-route-bundle:{MASTER_ASSET_ID}"
    )
    report = {
        "schema": REPORT_SCHEMA,
        "asset_id": MASTER_ASSET_ID,
        "selector": selector,
        **{key: value for key, value in verified.items() if key != "parsed_replacement"},
        "claims": {
            "same_master_play_resource_donors_only": True,
            "descriptor_and_relative_chain_pointer_only": True,
            "existing_game_authored_node_chains_reused": True,
            "resource_extent_preserved": True,
            "source_and_replacement_fully_reparsed": True,
            "names_formations_memberships_nodes_and_non_target_bytes_preserved": True,
            "assignment_chain_start_set_preserved": True,
            "waypoint_coordinate_or_opcode_semantics_claimed": False,
            "custom_play_save_container_claimed": False,
            "contains_retail_bytes": False,
        },
    }
    return CompiledRouteClone(
        MASTER_ASSET_ID,
        selector,
        str(verified["source_sha256"]),
        str(verified["replacement_sha256"]),
        int(verified["changed_byte_count"]),
        changed,
        normalized,
        rebuilt,
        verified["parsed_replacement"],
        report,
    )


compile_play_route_clones = compile_route_clones


def read_master_play_body(index_path: Path) -> bytes:
    """Read and fully validate the private MASTER body from a selected game."""

    try:
        archive = apf_outer.parse_archive(Path(index_path))
        entry = archive.entries[180]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            if (
                entry.name_id != 487_346_054
                or len(entry.segments) != 1
                or entry.segments[0].pack_name != "0A"
                or record.warnings
                or record.block_count != 1
                or record.file_count != 1
                or len(record.files) != 1
            ):
                raise ValidationError("APF MASTER PLAY IFF/outer ownership changed.")
            target = record.files[0]
            if (
                target.name != "mpb"
                or target.type_name != "PLAY"
                or target.file_id != 0x33CDF8E3
                or target.type_hash != 0x681C330E
                or len(target.parts) != 1
            ):
                raise ValidationError("APF MASTER PLAY inner-file ownership changed.")
            part = target.parts[0]
            decoded = apf_inner.decode_block(
                reader, record, part.block_index, 256 * 1024 * 1024
            )
            body = decoded[part.offset : part.offset + part.length]
    except ValidationError:
        raise
    except (OSError, IndexError, apf_inner.FormatError, apf_outer.FormatError) as exc:
        raise ValidationError(f"Could not open APF MASTER PLAY: {exc}") from exc
    _parse(body)
    return body


def build_play_route_patch(
    index_path: Path,
    requests: Iterable[RouteCloneRequest | Mapping[str, object]],
) -> CompiledRouteCloneEntry:
    """Compile logical route clones into APF outer 180 without touching source."""

    normalized = _normalize_requests(requests)
    try:
        archive = apf_outer.parse_archive(Path(index_path))
        entry = archive.entries[180]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            original_entry = reader.read(entry, 0, entry.size)
            original_blocks = [
                apf_inner.decode_block(reader, record, index, 256 * 1024 * 1024)
                for index in range(record.block_count)
            ]
            original_stored = [
                reader.read(entry, block.start_offset, block.stored_length)
                for block in record.blocks
            ]
    except (OSError, IndexError, apf_inner.FormatError, apf_outer.FormatError) as exc:
        raise ValidationError(f"Could not open APF MASTER PLAY: {exc}") from exc
    if (
        entry.name_id != 487_346_054
        or len(entry.segments) != 1
        or entry.segments[0].pack_name != "0A"
        or record.warnings
        or record.footer is None
        or record.block_count != 1
        or record.file_count != 1
        or len(record.files) != 1
    ):
        raise ValidationError("APF MASTER PLAY IFF/outer ownership changed.")
    target_file = record.files[0]
    if (
        target_file.name != "mpb"
        or target_file.type_name != "PLAY"
        or target_file.file_id != 0x33CDF8E3
        or target_file.type_hash != 0x681C330E
        or len(target_file.parts) != 1
        or target_file.parts[0].block_index != 0
    ):
        raise ValidationError("APF MASTER PLAY inner-file ownership changed.")
    target_part = target_file.parts[0]
    original_body = original_blocks[0][
        target_part.offset : target_part.offset + target_part.length
    ]
    compiled = compile_route_clones(original_body, normalized)
    patched_block = bytearray(original_blocks[0])
    patched_block[target_part.offset : target_part.offset + target_part.length] = (
        compiled.replacement
    )
    new_block = bytes(patched_block)
    descriptor = record.blocks[0]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise ValidationError("APF MASTER PLAY block is no longer H7A-compressed.")
    try:
        compressed, preservation = apf_inner.encode_h7a_preserving_tokens(
            original_stored[0][apf_inner.H7A_HEADER_SIZE :],
            original_blocks[0],
            new_block,
            descriptor.wrapper.shift,
        )
        stored = struct.pack(
            ">5I",
            apf_inner.H7A_MAGIC,
            len(new_block),
            apf_inner.H7A_HEADER_SIZE + len(compressed),
            descriptor.unknown_10,
            descriptor.wrapper.shift,
        ) + compressed
        roundtrip = apf_inner.decompress_h7a(
            compressed, len(new_block), descriptor.wrapper.shift
        )
    except apf_inner.FormatError as exc:
        raise ValidationError(f"Could not encode APF MASTER PLAY H7A: {exc}") from exc
    if roundtrip != new_block:
        raise ValidationError("APF MASTER PLAY H7A round trip changed the edit.")

    header = bytearray(original_entry[: record.header_size])
    block_start = record.header_size
    struct.pack_into(
        ">8I",
        header,
        apf_inner.IFF_HEADER_SIZE,
        descriptor.name_hash,
        descriptor.type_hash,
        descriptor.unknown_08,
        descriptor.uncompressed_length,
        descriptor.unknown_10,
        block_start,
        len(stored),
        descriptor.indexed,
    )
    file_length = record.header_size + len(stored)
    struct.pack_into(">I", header, 0x08, file_length)
    footer_size = 8 + record.footer.payload_size
    footer = original_entry[record.file_length : record.file_length + footer_size]
    tail = original_entry[record.file_length + footer_size :]
    if any(tail):
        raise ValidationError("APF MASTER PLAY outer allocation has a nonzero tail.")
    active = bytes(header) + stored + footer
    if len(active) > entry.size:
        raise ValidationError(
            "Edited APF routes do not fit the game's fixed compressed allocation."
        )
    rebuilt = active + b"\0" * (entry.size - len(active))

    memory = apf_texture_patch.BytesReader(rebuilt)
    try:
        reparsed = apf_inner.parse_iff(memory, entry)
        decoded = apf_inner.decode_block(memory, reparsed, 0, 256 * 1024 * 1024)
    except apf_inner.FormatError as exc:
        raise ValidationError(f"Rebuilt APF MASTER PLAY IFF is invalid: {exc}") from exc
    if reparsed.warnings or decoded != new_block:
        raise ValidationError("Rebuilt APF MASTER PLAY changed its decoded block.")
    rebuilt_part = reparsed.files[0].parts[0]
    verified_body = decoded[
        rebuilt_part.offset : rebuilt_part.offset + rebuilt_part.length
    ]
    verification = verify_route_clones(original_body, verified_body, normalized)
    if verification["replacement_sha256"] != compiled.replacement_sha256:
        raise ValidationError("Rebuilt APF MASTER PLAY differs from its compiler output.")
    report = {
        **dict(compiled.report),
        "outer_index": 180,
        "output_entry_size": len(rebuilt),
        "output_entry_sha256": _sha256(rebuilt),
        "h7a_transport": {
            "strategy": "retail-token-preserving",
            **preservation,
            "compressed_block_size": len(stored),
            "file_length": file_length,
        },
        "claims": {
            **dict(compiled.report["claims"]),
            "fixed_outer_allocation_preserved": True,
            "h7a_round_trip_exact": True,
            "manifest_contains_retail_or_replacement_bytes": False,
        },
    }
    return CompiledRouteCloneEntry(180, rebuilt, compiled, report)


def encode_master_play_body(index_path: Path, new_body: bytes) -> tuple[bytes, dict[str, object]]:
    """Pack a decoded MASTER PLAY body into outer 180 without touching source."""

    try:
        archive = apf_outer.parse_archive(Path(index_path))
        entry = archive.entries[180]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            original_entry = reader.read(entry, 0, entry.size)
            original_blocks = [
                apf_inner.decode_block(reader, record, index, 256 * 1024 * 1024)
                for index in range(record.block_count)
            ]
            original_stored = [
                reader.read(entry, block.start_offset, block.stored_length)
                for block in record.blocks
            ]
    except (OSError, IndexError, apf_inner.FormatError, apf_outer.FormatError) as exc:
        raise ValidationError(f"Could not open APF MASTER PLAY: {exc}") from exc
    if (
        entry.name_id != 487_346_054
        or len(entry.segments) != 1
        or entry.segments[0].pack_name != "0A"
        or record.warnings
        or record.footer is None
        or record.block_count != 1
        or record.file_count != 1
        or len(record.files) != 1
    ):
        raise ValidationError("APF MASTER PLAY IFF/outer ownership changed.")
    target_file = record.files[0]
    if (
        target_file.name != "mpb"
        or target_file.type_name != "PLAY"
        or target_file.file_id != 0x33CDF8E3
        or target_file.type_hash != 0x681C330E
        or len(target_file.parts) != 1
        or target_file.parts[0].block_index != 0
    ):
        raise ValidationError("APF MASTER PLAY inner-file ownership changed.")
    target_part = target_file.parts[0]
    original_body = original_blocks[0][
        target_part.offset : target_part.offset + target_part.length
    ]
    if len(new_body) != len(original_body):
        raise ValidationError(
            f"APF MASTER PLAY body is {len(new_body):,} bytes; "
            f"{len(original_body):,} were expected."
        )
    patched_block = bytearray(original_blocks[0])
    patched_block[target_part.offset : target_part.offset + target_part.length] = (
        new_body
    )
    new_block = bytes(patched_block)
    descriptor = record.blocks[0]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise ValidationError("APF MASTER PLAY block is no longer H7A-compressed.")
    try:
        compressed, preservation = apf_inner.encode_h7a_preserving_tokens(
            original_stored[0][apf_inner.H7A_HEADER_SIZE :],
            original_blocks[0],
            new_block,
            descriptor.wrapper.shift,
        )
        stored = struct.pack(
            ">5I",
            apf_inner.H7A_MAGIC,
            len(new_block),
            apf_inner.H7A_HEADER_SIZE + len(compressed),
            descriptor.unknown_10,
            descriptor.wrapper.shift,
        ) + compressed
        roundtrip = apf_inner.decompress_h7a(
            compressed, len(new_block), descriptor.wrapper.shift
        )
    except apf_inner.FormatError as exc:
        raise ValidationError(f"Could not encode APF MASTER PLAY H7A: {exc}") from exc
    if roundtrip != new_block:
        raise ValidationError("APF MASTER PLAY H7A round trip changed the edit.")

    header = bytearray(original_entry[: record.header_size])
    block_start = record.header_size
    struct.pack_into(
        ">8I",
        header,
        apf_inner.IFF_HEADER_SIZE,
        descriptor.name_hash,
        descriptor.type_hash,
        descriptor.unknown_08,
        descriptor.uncompressed_length,
        descriptor.unknown_10,
        block_start,
        len(stored),
        descriptor.indexed,
    )
    file_length = record.header_size + len(stored)
    struct.pack_into(">I", header, 0x08, file_length)
    footer_size = 8 + record.footer.payload_size
    footer = original_entry[record.file_length : record.file_length + footer_size]
    tail = original_entry[record.file_length + footer_size :]
    if any(tail):
        raise ValidationError("APF MASTER PLAY outer allocation has a nonzero tail.")
    active = bytes(header) + stored + footer
    if len(active) > entry.size:
        raise ValidationError(
            "Edited APF MASTER PLAY does not fit the game's fixed compressed allocation."
        )
    rebuilt = active + b"\0" * (entry.size - len(active))

    memory = apf_texture_patch.BytesReader(rebuilt)
    try:
        reparsed = apf_inner.parse_iff(memory, entry)
        decoded = apf_inner.decode_block(memory, reparsed, 0, 256 * 1024 * 1024)
    except apf_inner.FormatError as exc:
        raise ValidationError(f"Rebuilt APF MASTER PLAY IFF is invalid: {exc}") from exc
    if reparsed.warnings or decoded != new_block:
        raise ValidationError("Rebuilt APF MASTER PLAY changed its decoded block.")
    rebuilt_part = reparsed.files[0].parts[0]
    verified_body = decoded[
        rebuilt_part.offset : rebuilt_part.offset + rebuilt_part.length
    ]
    if verified_body != new_body:
        raise ValidationError("Rebuilt APF MASTER PLAY differs from its compiled body.")
    report = {
        "outer_index": 180,
        "output_entry_size": len(rebuilt),
        "output_entry_sha256": _sha256(rebuilt),
        "h7a_transport": {
            "strategy": "retail-token-preserving",
            **preservation,
            "compressed_block_size": len(stored),
            "file_length": file_length,
        },
    }
    return rebuilt, report


def _write_new(path: Path, payload: bytes) -> Path:
    target = path.expanduser().absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(target, flags, 0o600)
    completed = False
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
        completed = True
    finally:
        os.close(descriptor)
        if not completed:
            target.unlink(missing_ok=True)
    return target


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True, help="selected APF 0A")
    parser.add_argument("--target-play", type=int, required=True)
    parser.add_argument("--target-slot", type=int, required=True)
    parser.add_argument("--donor-play", type=int, required=True)
    parser.add_argument("--donor-slot", type=int, required=True)
    parser.add_argument(
        "--swap",
        action="store_true",
        help="also copy the original target assignment back to the donor",
    )
    parser.add_argument("--output-entry", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser


def main() -> int:
    args = _argument_parser().parse_args()
    request = RouteCloneRequest(
        args.target_play,
        args.target_slot,
        args.donor_play,
        args.donor_slot,
    )
    requests = [request]
    if args.swap:
        requests.append(
            RouteCloneRequest(
                args.donor_play,
                args.donor_slot,
                args.target_play,
                args.target_slot,
            )
        )
    output = args.output_entry.expanduser().absolute()
    receipt = args.receipt.expanduser().absolute()
    source = args.index.expanduser().absolute()
    if output == receipt or output == source or receipt == source:
        raise ValidationError("Source, output entry, and receipt paths must differ.")
    result = build_play_route_patch(source, requests)
    _write_new(output, result.entry_bytes)
    try:
        _write_new(
            receipt,
            (json.dumps(result.report, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
        )
    except BaseException:
        # The output was exclusively created by this invocation and has not
        # been returned as success, so bounded cleanup cannot touch user data.
        output.unlink(missing_ok=True)
        raise
    return 0


__all__ = [
    "CompiledRouteClone",
    "CompiledRouteCloneEntry",
    "MASTER_ASSET_ID",
    "PROVIDER_KIND",
    "PAYLOAD_SCHEMA",
    "ROUTE_ORPHAN_MESSAGE",
    "PlayRouteCloneRequest",
    "RouteCloneRequest",
    "build_relayed_copy_requests",
    "compile_play_route_clones",
    "compile_route_clones",
    "build_play_route_patch",
    "relay_candidates",
    "encode_master_play_body",
    "request_from_mapping",
    "read_master_play_body",
    "decode_route_clone_payload",
    "encode_route_clone_payload",
    "route_selector",
    "verify_route_clones",
]


if __name__ == "__main__":
    raise SystemExit(main())
