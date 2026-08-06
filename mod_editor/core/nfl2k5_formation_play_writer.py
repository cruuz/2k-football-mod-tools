"""Formation and play creation for NFL 2K5 PLAY resources.

This writer creates new formations and plays by reusing empty slots inside the
fixed 0x13390 PLAY body.  It mirrors the existing stock-route writer: shareable
projects store only logical selectors, Build resolves retail bytes from the
user's source and generates a fully reparsed replacement that changes only
owned formation/play slots and the formation/play counts.

Stage 1 is deliberately bounded: new formations/plays are exact clones of a
donor (same 0xB4 + 0x50 for formations, same 0x60 + 11 descriptors/pointers
for plays) and reuse the donor's name pointer.  That requires no string-pool
growth and no node allocation, keeps the body size exact, and is sufficient
to prove the creation pipeline loads and replaces real plays in-game.  Custom
names and node-chain authoring are the next bounded step once this clone
primitive is runtime-proved.

The writer preserves every byte outside the newly inhabited formation/play
records and the two count fields at 0x34/0x38.  Node bodies, string pools, and
all other tables remain exact.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import ValidationError
from .nfl2k5_playbook_inspector import (
    BODY_SIZE,
    CATEGORY_BASE,
    FORMATION_AUX_BASE,
    FORMATION_AUX_SIZE,
    FORMATION_BASE,
    FORMATION_CAPACITY,
    FORMATION_SIZE,
    NODE_BASE,
    PLAY_BASE,
    PLAY_CAPACITY,
    PLAY_SIZE,
    RESOURCE_HEADER_SIZE,
    parse_playbook_resource,
)

PROVIDER_KIND_FORMATION = "play_formation_create"
PROVIDER_KIND_PLAY = "play_create"
REPORT_SCHEMA = "nfl2k5_formation_play_create/v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def formation_selector(asset_id: str, new_index: int) -> str:
    return f"formation-create:{asset_id}:f{new_index}"


def play_selector(asset_id: str, new_index: int) -> str:
    return f"play-create:{asset_id}:p{new_index}"


@dataclass(frozen=True, slots=True)
class FormationCreateRequest:
    asset_id: str
    donor_formation_index: int

    @property
    def selector(self) -> str:
        # selector is resolved after compilation (needs new_index); placeholder
        return f"formation-create:{self.asset_id}:donor{self.donor_formation_index}"

    def provider_edit(self) -> dict[str, object]:
        return {"kind": PROVIDER_KIND_FORMATION, **asdict(self)}


@dataclass(frozen=True, slots=True)
class PlayCreateRequest:
    asset_id: str
    donor_play_index: int

    @property
    def selector(self) -> str:
        return f"play-create:{self.asset_id}:donor{self.donor_play_index}"

    def provider_edit(self) -> dict[str, object]:
        return {"kind": PROVIDER_KIND_PLAY, **asdict(self)}


@dataclass(frozen=True, slots=True)
class CompiledFormationPlayResource:
    asset_id: str
    selector: str
    source_sha256: str
    replacement_sha256: str
    changed_byte_count: int
    changed_ranges: tuple[tuple[int, int], ...]
    formation_requests: tuple[FormationCreateRequest, ...]
    play_requests: tuple[PlayCreateRequest, ...]
    new_formation_indices: tuple[int, ...]
    new_play_indices: tuple[int, ...]
    replacement: bytes
    parsed_replacement: Any
    report: Mapping[str, Any]


def _integer(value: object, label: str, *, maximum: int | None = None) -> int:
    if type(value) is not int or value < 0 or (maximum is not None and value > maximum):
        suffix = f" through {maximum}" if maximum is not None else " or greater"
        raise ValidationError(f"{label} must be an integer from 0{suffix}.")
    return value


def formation_request_from_mapping(value: Mapping[str, object]) -> FormationCreateRequest:
    fields = {"asset_id", "donor_formation_index"}
    if set(value) != fields:
        raise ValidationError("A formation create has unsupported fields.")
    asset_id = value.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id:
        raise ValidationError("A formation create needs a private asset selector.")
    return FormationCreateRequest(
        asset_id,
        _integer(value.get("donor_formation_index"), "Donor formation index"),
    )


def play_request_from_mapping(value: Mapping[str, object]) -> PlayCreateRequest:
    fields = {"asset_id", "donor_play_index"}
    if set(value) != fields:
        raise ValidationError("A play create has unsupported fields.")
    asset_id = value.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id:
        raise ValidationError("A play create needs a private asset selector.")
    return PlayCreateRequest(
        asset_id,
        _integer(value.get("donor_play_index"), "Donor play index"),
    )


def _difference_ranges(before: bytes, after: bytes) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    start: int | None = None
    for i, (l, r) in enumerate(zip(before, after)):
        if l != r and start is None:
            start = i
        elif l == r and start is not None:
            result.append((start, i))
            start = None
    if start is not None:
        result.append((start, len(before)))
    return tuple(result)


def compile_formation_play_creations(
    raw_resource: bytes,
    formation_requests: Iterable[FormationCreateRequest | Mapping[str, object]] = (),
    play_requests: Iterable[PlayCreateRequest | Mapping[str, object]] = (),
) -> CompiledFormationPlayResource:
    # Normalize requests
    norm_formations = tuple(
        r if isinstance(r, FormationCreateRequest) else formation_request_from_mapping(r)
        for r in formation_requests
    )
    norm_plays = tuple(
        r if isinstance(r, PlayCreateRequest) else play_request_from_mapping(r) for r in play_requests
    )
    if not norm_formations and not norm_plays:
        raise ValidationError("Choose at least one formation or play to create.")
    # All requests must target same asset
    asset_ids = {r.asset_id for r in norm_formations} | {r.asset_id for r in norm_plays}
    if len(asset_ids) != 1:
        raise ValidationError("One PLAY compiler call may edit only one playbook.")
    asset_id = next(iter(asset_ids))

    source = parse_playbook_resource(raw_resource, asset_id=asset_id)
    old_formation_count = len(source.formations)
    old_play_count = len(source.plays)
    new_formation_count = old_formation_count + len(norm_formations)
    new_play_count = old_play_count + len(norm_plays)

    if new_formation_count > FORMATION_CAPACITY:
        raise ValidationError(
            f"That would need {new_formation_count} formations but the PLAY capacity is {FORMATION_CAPACITY}."
        )
    if new_play_count > PLAY_CAPACITY:
        raise ValidationError(
            f"That would need {new_play_count} plays but the PLAY capacity is {PLAY_CAPACITY}."
        )
    # Validate donors
    for req in norm_formations:
        if not 0 <= req.donor_formation_index < old_formation_count:
            raise ValidationError("Donor formation index is outside this PLAY book.")
    for req in norm_plays:
        if not 0 <= req.donor_play_index < old_play_count:
            raise ValidationError("Donor play index is outside this PLAY book.")

    replacement = bytearray(raw_resource)
    body_off = RESOURCE_HEADER_SIZE  # wrapper is 0x20
    # Update counts in body (both in wrapper-proven body, not wrapper)
    struct.pack_into("<I", replacement, body_off + 0x34, new_formation_count)
    struct.pack_into("<I", replacement, body_off + 0x38, new_play_count)

    new_formation_indices: list[int] = []
    new_play_indices: list[int] = []
    allowed: list[range] = [
        range(body_off + 0x34, body_off + 0x38),  # formation count (4)
        range(body_off + 0x38, body_off + 0x3C),  # play count (4)
    ]

    def _reencode_relative(src_field_body: int, dst_field_body: int, stored_value: int) -> bytes:
        # Stored is signed i32 = target - field + 1
        target_body = src_field_body - 1 + stored_value
        # Re-encode for dst field
        new_stored = target_body - dst_field_body + 1
        return struct.pack("<i", new_stored)

    # Clone formations first (need to re-encode formation name pointer, which is at offset 0 of record)
    for i, req in enumerate(norm_formations):
        dst_idx = old_formation_count + i
        src_f = FORMATION_BASE + req.donor_formation_index * FORMATION_SIZE
        dst_f = FORMATION_BASE + dst_idx * FORMATION_SIZE
        src_aux = FORMATION_AUX_BASE + req.donor_formation_index * FORMATION_AUX_SIZE
        dst_aux = FORMATION_AUX_BASE + dst_idx * FORMATION_AUX_SIZE
        # Copy aux 0x50 verbatim (no relative fields inside awx – its entries are packed H not relative)
        replacement[body_off + dst_aux : body_off + dst_aux + FORMATION_AUX_SIZE] = raw_resource[
            body_off + src_aux : body_off + src_aux + FORMATION_AUX_SIZE
        ]
        # Copy formation 0xB4 but re-encode name pointer at +0
        src_name_field = src_f
        dst_name_field = dst_f
        stored_name = struct.unpack_from("<i", raw_resource, body_off + src_name_field)[0]
        # Copy full record first, then patch name pointer
        replacement[body_off + dst_f : body_off + dst_f + FORMATION_SIZE] = raw_resource[
            body_off + src_f : body_off + src_f + FORMATION_SIZE
        ]
        # Re-encode name pointer relative to new field
        replacement[body_off + dst_name_field : body_off + dst_name_field + 4] = _reencode_relative(
            src_name_field, dst_name_field, stored_name
        )
        new_formation_indices.append(dst_idx)
        allowed.append(range(body_off + dst_f, body_off + dst_f + FORMATION_SIZE))
        allowed.append(range(body_off + dst_aux, body_off + dst_aux + FORMATION_AUX_SIZE))

    # Clone plays – need to re-encode 1 name pointer + 11 route pointers (relative)
    for i, req in enumerate(norm_plays):
        dst_idx = old_play_count + i
        src_p = PLAY_BASE + req.donor_play_index * PLAY_SIZE
        dst_p = PLAY_BASE + dst_idx * PLAY_SIZE
        # Copy whole play then patch relatives
        replacement[body_off + dst_p : body_off + dst_p + PLAY_SIZE] = raw_resource[
            body_off + src_p : body_off + src_p + PLAY_SIZE
        ]
        # Name pointer at +0
        src_name_field = src_p
        dst_name_field = dst_p
        stored_name = struct.unpack_from("<i", raw_resource, body_off + src_name_field)[0]
        replacement[body_off + dst_name_field : body_off + dst_name_field + 4] = _reencode_relative(
            src_name_field, dst_name_field, stored_name
        )
        # 11 route pointers at +0x0C + slot*8
        for slot in range(11):
            src_ptr_field = src_p + 0x0C + slot * 8
            dst_ptr_field = dst_p + 0x0C + slot * 8
            stored_ptr = struct.unpack_from("<i", raw_resource, body_off + src_ptr_field)[0]
            replacement[body_off + dst_ptr_field : body_off + dst_ptr_field + 4] = _reencode_relative(
                src_ptr_field, dst_ptr_field, stored_ptr
            )
        new_play_indices.append(dst_idx)
        allowed.append(range(body_off + dst_p, body_off + dst_p + PLAY_SIZE))

    rebuilt = bytes(replacement)
    if rebuilt == raw_resource:
        raise ValidationError("Formation/play clone produced no byte change.")

    changed = _difference_ranges(raw_resource, rebuilt)
    allowed_set = {idx for r in allowed for idx in r}
    if any(idx not in allowed_set for s, e in changed for idx in range(s, e)):
        raise ValidationError("Formation/play compilation changed an unowned byte.")

    reparsed = parse_playbook_resource(rebuilt, asset_id=asset_id)
    # Sanity checks
    if len(reparsed.formations) != new_formation_count:
        raise ValidationError("Reparsed formation count did not match compiled count.")
    if len(reparsed.plays) != new_play_count:
        raise ValidationError("Reparsed play count did not match compiled count.")
    for i, req in enumerate(norm_formations):
        dst = new_formation_indices[i]
        src_name = source.formations[req.donor_formation_index].name
        dst_name = reparsed.formations[dst].name
        if dst_name != src_name:
            raise ValidationError("Cloned formation name did not match donor.")
        # Verify aux links preserved
        src_links = source.formations[req.donor_formation_index].play_links
        dst_links = reparsed.formations[dst].play_links
        if len(src_links) != len(dst_links) or any(
            s.play_index != d.play_index or s.group != d.group for s, d in zip(src_links, dst_links)
        ):
            raise ValidationError("Cloned formation links did not match donor.")
    for i, req in enumerate(norm_plays):
        dst = new_play_indices[i]
        src_play = source.plays[req.donor_play_index]
        dst_play = reparsed.plays[dst]
        if dst_play.name != src_play.name:
            raise ValidationError("Cloned play name did not match donor.")
        if dst_play.flags_or_id != src_play.flags_or_id:
            raise ValidationError("Cloned play flags did not match donor.")
        if len(dst_play.assignments) != len(src_play.assignments):
            raise ValidationError("Cloned play assignments did not match donor.")
        for sa, da in zip(src_play.assignments, dst_play.assignments):
            if sa.descriptor_word != da.descriptor_word or sa.chain_start_index != da.chain_start_index:
                raise ValidationError("Cloned play assignment did not match donor.")

    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "asset_id": asset_id,
        "source_sha256": _sha256(raw_resource),
        "replacement_sha256": _sha256(rebuilt),
        "old_formation_count": old_formation_count,
        "new_formation_count": new_formation_count,
        "old_play_count": old_play_count,
        "new_play_count": new_play_count,
        "new_formation_indices": tuple(new_formation_indices),
        "new_play_indices": tuple(new_play_indices),
        "formation_donors": tuple(r.donor_formation_index for r in norm_formations),
        "play_donors": tuple(r.donor_play_index for r in norm_plays),
        "changed_ranges": changed,
        "claims": {
            "source_and_replacement_fully_reparsed": True,
            "only_owned_formation_play_records_and_counts_changed": True,
        },
    }

    selector = f"formation-play-create:{asset_id}:f{new_formation_indices}-p{new_play_indices}"
    return CompiledFormationPlayResource(
        asset_id=asset_id,
        selector=selector,
        source_sha256=report["source_sha256"],
        replacement_sha256=report["replacement_sha256"],
        changed_byte_count=sum(e - s for s, e in changed),
        changed_ranges=changed,
        formation_requests=norm_formations,
        play_requests=norm_plays,
        new_formation_indices=tuple(new_formation_indices),
        new_play_indices=tuple(new_play_indices),
        replacement=rebuilt,
        parsed_replacement=reparsed,
        report=report,
    )


__all__ = [
    "FormationCreateRequest",
    "PlayCreateRequest",
    "CompiledFormationPlayResource",
    "compile_formation_play_creations",
    "formation_request_from_mapping",
    "play_request_from_mapping",
]
