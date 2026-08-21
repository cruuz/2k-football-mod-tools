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
to prove the creation pipeline loads and replaces real plays in-game.

Stage 2 (this revision) stays inside the same proved empty capacity: an
optional custom name appends to the name pool's verified zero tail (the pool
count word at 0x1083C is checked against the retail invariant and kept
consistent), and a menu link lists a play in one currently-empty 0x1FF aux
slot, inheriting the formation's existing selection group unless one is
chosen explicitly.  Node-chain authoring and group-bit semantics remain
unproved and are never claimed; freehand node synthesis stays refused.

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
    CATEGORY_SIZE,
    FORMATION_AUX_BASE,
    FORMATION_AUX_SIZE,
    FORMATION_BASE,
    FORMATION_CAPACITY,
    FORMATION_PLAY_LINKS,
    FORMATION_SIZE,
    NODE_BASE,
    PLAY_BASE,
    PLAY_CAPACITY,
    PLAY_SIZE,
    RESOURCE_HEADER_SIZE,
    STRING_BASE,
    parse_playbook_resource,
)
from .nfl2k5_source_cache import PACK0_SHA256, PACK0_SIZE
from .nfl2k5_universal_asset_index import Nfl2k5UniversalAssetIndex

try:
    from nfl_outer import FormatError, read_entry_range
except ImportError as exc:  # pragma: no cover - installation boundary
    raise RuntimeError("The NFL archive reader is unavailable") from exc

PROVIDER_KIND_FORMATION = "play_formation_create"
PROVIDER_KIND_PLAY = "play_create"
PROVIDER_KIND_LINK = "play_formation_link"
REPORT_SCHEMA = "nfl2k5_formation_play_create/v1"

POOL_COUNT_WORD = 0x1083C
MAX_CUSTOM_NAME_CHARS = 40
EMPTY_LINK = 0x1FF


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def formation_selector(asset_id: str, new_index: int) -> str:
    return f"formation-create:{asset_id}:f{new_index}"


def play_selector(asset_id: str, new_index: int) -> str:
    return f"play-create:{asset_id}:p{new_index}"


def _clean_custom_name(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise ValidationError("A custom name must be text.")
    name = value.strip()
    if not 1 <= len(name) <= MAX_CUSTOM_NAME_CHARS:
        raise ValidationError(
            f"A custom name must be 1 through {MAX_CUSTOM_NAME_CHARS} characters."
        )
    if any(ord(ch) < 0x20 or ord(ch) > 0x7E for ch in name):
        raise ValidationError("A custom name may use printable ASCII only.")
    return name


@dataclass(frozen=True, slots=True)
class FormationCreateRequest:
    asset_id: str
    donor_formation_index: int
    custom_name: str | None = None

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
    custom_name: str | None = None

    @property
    def selector(self) -> str:
        return f"play-create:{self.asset_id}:donor{self.donor_play_index}"

    def provider_edit(self) -> dict[str, object]:
        return {"kind": PROVIDER_KIND_PLAY, **asdict(self)}


@dataclass(frozen=True, slots=True)
class FormationLinkRequest:
    """List one play in one formation's empty 36-slot menu table.

    ``group=None`` inherits the selection group of the formation's first
    populated slot; the group bits' gameplay meaning stays unproved, so the
    writer only ever reuses values the book already uses (or an explicit
    0-3 the caller accepts responsibility for).
    """

    asset_id: str
    formation_index: int
    play_index: int
    group: int | None = None

    @property
    def selector(self) -> str:
        return (
            f"formation-link:{self.asset_id}:f{self.formation_index}:"
            f"p{self.play_index}"
        )

    def provider_edit(self) -> dict[str, object]:
        return {"kind": PROVIDER_KIND_LINK, **asdict(self)}


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
    fields = {"asset_id", "donor_formation_index", "custom_name"}
    if not set(value) <= fields or not {"asset_id", "donor_formation_index"} <= set(value):
        raise ValidationError("A formation create has unsupported fields.")
    asset_id = value.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id:
        raise ValidationError("A formation create needs a private asset selector.")
    return FormationCreateRequest(
        asset_id,
        _integer(value.get("donor_formation_index"), "Donor formation index"),
        _clean_custom_name(value.get("custom_name")),
    )


def play_request_from_mapping(value: Mapping[str, object]) -> PlayCreateRequest:
    fields = {"asset_id", "donor_play_index", "custom_name"}
    if not set(value) <= fields or not {"asset_id", "donor_play_index"} <= set(value):
        raise ValidationError("A play create has unsupported fields.")
    asset_id = value.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id:
        raise ValidationError("A play create needs a private asset selector.")
    return PlayCreateRequest(
        asset_id,
        _integer(value.get("donor_play_index"), "Donor play index"),
        _clean_custom_name(value.get("custom_name")),
    )


def link_request_from_mapping(value: Mapping[str, object]) -> FormationLinkRequest:
    fields = {"asset_id", "formation_index", "play_index", "group"}
    if not set(value) <= fields or not {"asset_id", "formation_index", "play_index"} <= set(value):
        raise ValidationError("A formation link has unsupported fields.")
    asset_id = value.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id:
        raise ValidationError("A formation link needs a private asset selector.")
    group = value.get("group")
    if group is not None:
        group = _integer(group, "Selection group", maximum=3)
    return FormationLinkRequest(
        asset_id,
        _integer(value.get("formation_index"), "Formation index"),
        _integer(value.get("play_index"), "Play index"),
        group,
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


def _string_end(body: bytes, field: int) -> int:
    target = field - 1 + struct.unpack_from("<i", body, field)[0]
    if not STRING_BASE <= target < len(body) or target & 1:
        raise ValidationError("PLAY name pool pointer is invalid.")
    cursor = target
    while cursor + 2 <= len(body):
        if body[cursor:cursor + 2] == b"\0\0":
            return cursor + 2
        cursor += 2
    raise ValidationError("PLAY name pool string is not terminated.")


def _pool_end(
    body: bytes, formation_count: int, play_count: int, category_count: int
) -> int:
    ends = [_string_end(body, 0x30)]
    for i in range(formation_count):
        ends.append(_string_end(body, FORMATION_BASE + i * FORMATION_SIZE))
    for j in range(play_count):
        ends.append(_string_end(body, PLAY_BASE + j * PLAY_SIZE))
    for k in range(category_count):
        ends.append(_string_end(body, CATEGORY_BASE + k * CATEGORY_SIZE))
    return max(ends)


def compile_formation_play_creations(
    raw_resource: bytes,
    formation_requests: Iterable[FormationCreateRequest | Mapping[str, object]] = (),
    play_requests: Iterable[PlayCreateRequest | Mapping[str, object]] = (),
    link_requests: Iterable[FormationLinkRequest | Mapping[str, object]] = (),
) -> CompiledFormationPlayResource:
    # Normalize requests
    norm_formations = tuple(
        r if isinstance(r, FormationCreateRequest) else formation_request_from_mapping(r)
        for r in formation_requests
    )
    norm_plays = tuple(
        r if isinstance(r, PlayCreateRequest) else play_request_from_mapping(r) for r in play_requests
    )
    norm_links = tuple(
        r if isinstance(r, FormationLinkRequest) else link_request_from_mapping(r)
        for r in link_requests
    )
    if not norm_formations and not norm_plays and not norm_links:
        raise ValidationError("Choose at least one formation or play to create.")
    # All requests must target same asset
    asset_ids = (
        {r.asset_id for r in norm_formations}
        | {r.asset_id for r in norm_plays}
        | {r.asset_id for r in norm_links}
    )
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

    body = raw_resource[RESOURCE_HEADER_SIZE:]
    # Custom names append to the UTF-16LE pool's proven zero tail.  The pool is
    # sequential and fully referenced in every retail book, and the u32 at
    # 0x1083C equals the pool's u16 count in 37/37 books, so both facts are
    # verified before use and kept consistent after.
    appended_offsets: dict[object, int] = {}
    pool_tail_range: range | None = None
    pool_word_range: range | None = None
    custom_requests = [r for r in (*norm_formations, *norm_plays) if r.custom_name]
    if custom_requests:
        old_pool_end = _pool_end(body, old_formation_count, old_play_count, len(source.categories))
        if any(body[old_pool_end:]):
            raise ValidationError(
                "This book's name pool tail is not the proven zero padding, so "
                "a custom name cannot be appended safely. Clone with the "
                "donor's name instead."
            )
        declared = struct.unpack_from("<I", body, POOL_COUNT_WORD)[0]
        if declared != (old_pool_end - STRING_BASE) // 2:
            raise ValidationError(
                "This book's pool count word does not match its name pool, so "
                "a custom name cannot be appended safely. Clone with the "
                "donor's name instead."
            )
        cursor = old_pool_end
        for req in custom_requests:
            need = (len(req.custom_name or "") + 1) * 2
            if cursor + need > BODY_SIZE:
                raise ValidationError(
                    f"The name “{req.custom_name}” does not fit this book's "
                    "remaining name pool. Shorten it or reuse the donor name."
                )
            appended_offsets[id(req)] = cursor
            cursor += need
        pool_tail_range = range(old_pool_end, cursor)
        pool_word_range = range(POOL_COUNT_WORD, POOL_COUNT_WORD + 4)

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
        if req.custom_name:
            name_off = appended_offsets[id(req)]
            encoded = req.custom_name.encode("utf-16le") + b"\0\0"
            replacement[body_off + name_off : body_off + name_off + len(encoded)] = encoded
            struct.pack_into(
                "<i", replacement, body_off + dst_name_field,
                name_off - dst_name_field + 1,
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
        if req.custom_name:
            name_off = appended_offsets[id(req)]
            encoded = req.custom_name.encode("utf-16le") + b"\0\0"
            replacement[body_off + name_off : body_off + name_off + len(encoded)] = encoded
            struct.pack_into(
                "<i", replacement, body_off + dst_name_field,
                name_off - dst_name_field + 1,
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

    if pool_tail_range is not None and pool_word_range is not None:
        struct.pack_into(
            "<I", replacement, body_off + POOL_COUNT_WORD,
            (pool_tail_range.stop - STRING_BASE) // 2,
        )
        allowed.append(range(body_off + pool_tail_range.start, body_off + pool_tail_range.stop))
        allowed.append(range(body_off + pool_word_range.start, body_off + pool_word_range.stop))

    # Menu links: inhabit one currently-empty 0x1FF slot per request.
    applied_links: list[dict[str, int]] = []
    for req in norm_links:
        if not 0 <= req.formation_index < new_formation_count:
            raise ValidationError(
                "That formation index is outside this PLAY book."
            )
        if not 0 <= req.play_index < new_play_count:
            raise ValidationError("That play index is outside this PLAY book.")
        aux = FORMATION_AUX_BASE + req.formation_index * FORMATION_AUX_SIZE
        slot_ofs = None
        inherit_group = None
        for slot in range(FORMATION_PLAY_LINKS):
            packed = struct.unpack_from(
                "<H", replacement, body_off + aux + slot * 2
            )[0]
            populated = (packed & EMPTY_LINK) != EMPTY_LINK
            if populated and inherit_group is None:
                inherit_group = (packed >> 9) & 0x3
            if not populated and slot_ofs is None:
                slot_ofs = aux + slot * 2
        if slot_ofs is None:
            raise ValidationError(
                "That formation's 36 menu slots are all populated, so the play "
                "cannot be listed there. Choose another formation."
            )
        if req.group is not None:
            group = req.group
        elif inherit_group is not None:
            group = inherit_group
        else:
            raise ValidationError(
                "That formation lists no plays yet, so there is no selection "
                "group to inherit. Set one explicitly (0-3) or link into a "
                "formation that already lists plays."
            )
        struct.pack_into(
            "<H", replacement, body_off + slot_ofs, (group << 9) | req.play_index
        )
        allowed.append(range(body_off + slot_ofs, body_off + slot_ofs + 2))
        applied_links.append(
            {
                "formation_index": req.formation_index,
                "play_index": req.play_index,
                "group": group,
                "slot_index": (slot_ofs - aux) // 2,
            }
        )

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
        expected_name = req.custom_name or src_name
        dst_name = reparsed.formations[dst].name
        if dst_name != expected_name:
            raise ValidationError("Cloned formation name did not match its request.")
        # Verify aux links preserved (plus any links this call applied here)
        src_links = source.formations[req.donor_formation_index].play_links
        expected_links = sorted(
            [(s.link_index, s.play_index, s.group) for s in src_links]
            + [
                (l["slot_index"], l["play_index"], l["group"])
                for l in applied_links
                if l["formation_index"] == dst
            ]
        )
        dst_links = sorted(
            (d.link_index, d.play_index, d.group)
            for d in reparsed.formations[dst].play_links
        )
        if expected_links != dst_links:
            raise ValidationError("Cloned formation links did not match donor.")
    for i, req in enumerate(norm_plays):
        dst = new_play_indices[i]
        src_play = source.plays[req.donor_play_index]
        dst_play = reparsed.plays[dst]
        if dst_play.name != (req.custom_name or src_play.name):
            raise ValidationError("Cloned play name did not match its request.")
        if dst_play.flags_or_id != src_play.flags_or_id:
            raise ValidationError("Cloned play flags did not match donor.")
        if len(dst_play.assignments) != len(src_play.assignments):
            raise ValidationError("Cloned play assignments did not match donor.")
        for sa, da in zip(src_play.assignments, dst_play.assignments):
            if sa.descriptor_word != da.descriptor_word or sa.chain_start_index != da.chain_start_index:
                raise ValidationError("Cloned play assignment did not match donor.")

    for link in applied_links:
        rep_links = reparsed.formations[link["formation_index"]].play_links
        if not any(
            rl.link_index == link["slot_index"]
            and rl.play_index == link["play_index"]
            and rl.group == link["group"]
            for rl in rep_links
        ):
            raise ValidationError("Compiled menu link did not survive reparse.")

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
        "links": tuple(
            (l["formation_index"], l["play_index"], l["group"], l["slot_index"])
            for l in applied_links
        ),
        "custom_names": tuple(
            r.custom_name for r in (*norm_formations, *norm_plays) if r.custom_name
        ),
        "changed_ranges": changed,
        "claims": {
            "source_and_replacement_fully_reparsed": True,
            "only_owned_formation_play_records_and_counts_changed": True,
            "aux_link_group_semantics_claimed": False,
            "custom_name_runtime_visibility_claimed": False,
            "node_or_opcode_authoring_claimed": False,
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


def build_unified_formation_play_import(
    index_path: Path,
    inventory_path: Path,
    asset_id: str,
    formation_requests: Iterable[FormationCreateRequest | Mapping[str, object]] = (),
    play_requests: Iterable[PlayCreateRequest | Mapping[str, object]] = (),
    link_requests: Iterable[FormationLinkRequest | Mapping[str, object]] = (),
) -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]:
    """Resolve, compile, and locate one fixed PLAY resource for formation/play creates."""

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
    compiled = compile_formation_play_creations(
        raw, formation_requests, play_requests, link_requests
    )
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
    "FormationCreateRequest",
    "PlayCreateRequest",
    "FormationLinkRequest",
    "CompiledFormationPlayResource",
    "compile_formation_play_creations",
    "build_unified_formation_play_import",
    "formation_request_from_mapping",
    "play_request_from_mapping",
    "link_request_from_mapping",
]
