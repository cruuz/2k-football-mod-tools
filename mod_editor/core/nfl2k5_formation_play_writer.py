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

Stage 3 (2026-09-02, authoring): a created formation may carry
``slot_positions`` (eleven ``(x_cm, depth_cm)`` pairs written into the slot
records the retail lineup reader ``FUN_0017fe60`` consumes, with mirror-partner
nibbles recomputed) and a ``category_index`` personnel swap; a created play may
carry ``assignments`` (per-slot node chains encoded with the retail opcode codec,
appended to the node pool with the count word at +0x40 bumped, descriptors
rebuilt) and must pass the ported game validator before it is written.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import ValidationError
from . import nfl2k5_play_codec as codec
from .nfl2k5_playbook_inspector import (
    BODY_SIZE,
    CATEGORY_BASE,
    CATEGORY_CAPACITY,
    CATEGORY_SIZE,
    FORMATION_AUX_BASE,
    FORMATION_AUX_SIZE,
    FORMATION_BASE,
    FORMATION_CAPACITY,
    FORMATION_PLAY_LINKS,
    FORMATION_SIZE,
    NODE_BASE,
    NODE_SIZE,
    PLAY_BASE,
    PLAY_CAPACITY,
    PLAY_SIZE,
    RESOURCE_HEADER_SIZE,
    STRING_BASE,
    parse_playbook_resource,
)
from .nfl2k5_source_cache import PACK0_RETAIL_BYTE_OFFSET, PACK0_RETAIL_SECTOR, PACK0_SHA256, PACK0_SIZE
from .nfl2k5_universal_asset_index import Nfl2k5UniversalAssetIndex

try:
    from nfl_outer import FormatError, read_entry_range
except ImportError as exc:  # pragma: no cover - installation boundary
    raise RuntimeError("The NFL archive reader is unavailable") from exc

PROVIDER_KIND_FORMATION = "play_formation_create"
PROVIDER_KIND_PLAY = "play_create"
PLAY_FLAGS_KEEP_MASK = 0x1FF   # play header bits 0-8: type code + family (game-validated)
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


def _payload_tag(payload: object) -> str:
    import json
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=list).encode()).hexdigest()[:10]


@dataclass(frozen=True, slots=True)
class FormationCreateRequest:
    asset_id: str
    donor_formation_index: int
    custom_name: str | None = None
    slot_positions: tuple[tuple[int, int], ...] | None = None
    category_index: int | None = None
    replace_index: int | None = None
    category_positions: tuple[int, ...] | None = None

    @property
    def selector(self) -> str:
        # selector is resolved after compilation (needs new_index); placeholder
        base = f"formation-create:{self.asset_id}:donor{self.donor_formation_index}"
        if (self.slot_positions is not None or self.category_index is not None or self.replace_index is not None
                or self.category_positions is not None):
            payload: list[object] = [self.slot_positions, self.category_index, self.custom_name, self.replace_index]
            if self.category_positions is not None:
                payload.append(list(self.category_positions))
            base += ":" + _payload_tag(payload)
        return base

    def provider_edit(self) -> dict[str, object]:
        row: dict[str, object] = {"kind": PROVIDER_KIND_FORMATION, "asset_id": self.asset_id,
                                  "donor_formation_index": self.donor_formation_index,
                                  "custom_name": self.custom_name}
        if self.slot_positions is not None:
            row["slot_positions"] = [list(pair) for pair in self.slot_positions]
        if self.category_index is not None:
            row["category_index"] = self.category_index
        if self.replace_index is not None:
            row["replace_index"] = self.replace_index
        if self.category_positions is not None:
            row["category_positions"] = list(self.category_positions)
        return row


@dataclass(frozen=True, slots=True)
class PlayCreateRequest:
    """``assignments``: eleven entries, each ``None`` (keep the donor chain) or a
    tuple of ``(opcode, operands)`` nodes in retail units (cm / seconds / ints)."""

    asset_id: str
    donor_play_index: int
    custom_name: str | None = None
    assignments: tuple[tuple[tuple[int, tuple[float, ...]], ...] | None, ...] | None = None
    replace_index: int | None = None
    play_flags: int | None = None   # header word (+4); None keeps the donor's

    @property
    def selector(self) -> str:
        base = f"play-create:{self.asset_id}:donor{self.donor_play_index}"
        if self.assignments is not None or self.replace_index is not None or self.play_flags is not None:
            payload: list[object] = [self.assignments, self.custom_name, self.replace_index]
            if self.play_flags is not None:
                payload.append(self.play_flags)
            base += ":" + _payload_tag(payload)
        return base

    def provider_edit(self) -> dict[str, object]:
        row: dict[str, object] = {"kind": PROVIDER_KIND_PLAY, "asset_id": self.asset_id,
                                  "donor_play_index": self.donor_play_index,
                                  "custom_name": self.custom_name}
        if self.assignments is not None:
            row["assignments"] = [
                None if chain is None else [[int(op), list(vals)] for op, vals in chain]
                for chain in self.assignments
            ]
        if self.replace_index is not None:
            row["replace_index"] = self.replace_index
        if self.play_flags is not None:
            row["play_flags"] = self.play_flags
        return row


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


def _slot_positions_from(value: object) -> tuple[tuple[int, int], ...] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 11:
        raise ValidationError("slot_positions needs exactly eleven (x, depth) pairs.")
    out: list[tuple[int, int]] = []
    for pair in value:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValidationError("Each slot position must be an (x_cm, depth_cm) pair.")
        x, z = pair
        if type(x) is bool or type(z) is bool or not all(isinstance(v, (int, float)) for v in (x, z)):
            raise ValidationError("Slot positions must be numbers (centimetres).")
        xi, zi = int(round(x)), int(round(z))
        if not -3000 <= xi <= 3000 or not -3000 <= zi <= 3000:
            raise ValidationError("A slot position is outside the field (±30 m).")
        out.append((xi, zi))
    return tuple(out)


def _assignments_from(value: object) -> tuple | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 11:
        raise ValidationError("assignments needs exactly eleven entries (None keeps the donor chain).")
    chains: list = []
    for chain in value:
        if chain is None:
            chains.append(None)
            continue
        if not isinstance(chain, (list, tuple)) or not 1 <= len(chain) <= 15:
            raise ValidationError("An authored chain needs 1 through 15 nodes.")
        nodes: list = []
        for node in chain:
            if not isinstance(node, (list, tuple)) or len(node) != 2:
                raise ValidationError("Each node must be [opcode, [operands...]].")
            op, vals = node
            if type(op) is bool or not isinstance(op, int) or not 0 <= op < codec.OPCODE_COUNT or op == 0x19:
                raise ValidationError(f"Opcode {op!r} is not a usable PLAY node opcode.")
            if not isinstance(vals, (list, tuple)) or any(
                type(v) is bool or not isinstance(v, (int, float)) for v in vals
            ):
                raise ValidationError("Node operands must be numbers.")
            specs = codec.OPERAND_SCHEMAS.get(op, ())
            if len(vals) > len(specs):
                raise ValidationError(f"Opcode {op:#x} takes at most {len(specs)} operands.")
            nodes.append((op, tuple(float(v) for v in vals)))
        chains.append(tuple(nodes))
    return tuple(chains)


def _position_codes_from(value: object) -> tuple[int, ...] | None:
    """Eleven personnel codes (kind | rank << 5) for one category record."""
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 11:
        raise ValidationError("Personnel codes must list exactly eleven positions.")
    codes: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 255:
            raise ValidationError("Each personnel code must be a byte.")
        if (item & 0x1F) not in codec.POSITION_KINDS:
            raise ValidationError(f"Personnel code 0x{item:02x} names no known position.")
        codes.append(item)
    return tuple(codes)


def formation_request_from_mapping(value: Mapping[str, object]) -> FormationCreateRequest:
    if value.get("kind") == PROVIDER_KIND_FORMATION:
        value = {k: v for k, v in value.items() if k != "kind"}
    fields = {"asset_id", "donor_formation_index", "custom_name", "slot_positions", "category_index", "replace_index",
              "category_positions"}
    if not set(value) <= fields or not {"asset_id", "donor_formation_index"} <= set(value):
        raise ValidationError("A formation create has unsupported fields.")
    asset_id = value.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id:
        raise ValidationError("A formation create needs a private asset selector.")
    category = value.get("category_index")
    if category is not None:
        category = _integer(category, "Category index", maximum=CATEGORY_CAPACITY - 1)
    replace = value.get("replace_index")
    if replace is not None:
        replace = _integer(replace, "Replace formation index", maximum=FORMATION_CAPACITY - 1)
    codes = _position_codes_from(value.get("category_positions"))
    if codes is not None and category is None:
        raise ValidationError("Personnel codes need the personnel group (category index) they are written into.")
    return FormationCreateRequest(
        asset_id,
        _integer(value.get("donor_formation_index"), "Donor formation index"),
        _clean_custom_name(value.get("custom_name")),
        _slot_positions_from(value.get("slot_positions")),
        category,
        replace,
        codes,
    )


def play_request_from_mapping(value: Mapping[str, object]) -> PlayCreateRequest:
    if value.get("kind") == PROVIDER_KIND_PLAY:
        value = {k: v for k, v in value.items() if k != "kind"}
    fields = {"asset_id", "donor_play_index", "custom_name", "assignments", "replace_index", "play_flags"}
    if not set(value) <= fields or not {"asset_id", "donor_play_index"} <= set(value):
        raise ValidationError("A play create has unsupported fields.")
    asset_id = value.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id:
        raise ValidationError("A play create needs a private asset selector.")
    replace = value.get("replace_index")
    if replace is not None:
        replace = _integer(replace, "Replace play index", maximum=PLAY_CAPACITY - 1)
    play_flags = value.get("play_flags")
    if play_flags is not None:
        play_flags = _integer(play_flags, "Play flags", maximum=0xFFFFFFFF)
    return PlayCreateRequest(
        asset_id,
        _integer(value.get("donor_play_index"), "Donor play index"),
        _clean_custom_name(value.get("custom_name")),
        _assignments_from(value.get("assignments")),
        replace,
        play_flags,
    )


def link_request_from_mapping(value: Mapping[str, object]) -> FormationLinkRequest:
    if value.get("kind") == PROVIDER_KIND_LINK:
        value = {k: v for k, v in value.items() if k != "kind"}
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
    appended_formations = [r for r in norm_formations if r.replace_index is None]
    appended_plays = [r for r in norm_plays if r.replace_index is None]
    new_formation_count = old_formation_count + len(appended_formations)
    new_play_count = old_play_count + len(appended_plays)
    for req in norm_formations:
        if req.replace_index is not None and not 0 <= req.replace_index < old_formation_count:
            raise ValidationError("The formation chosen for replacement does not exist in this book.")
    for req in norm_plays:
        if req.replace_index is not None and not 0 <= req.replace_index < old_play_count:
            raise ValidationError("The play chosen for replacement does not exist in this book.")
    if len({r.replace_index for r in norm_formations if r.replace_index is not None}) != len([r for r in norm_formations if r.replace_index is not None]):
        raise ValidationError("Two designed formations replace the same stock formation.")
    if len({r.replace_index for r in norm_plays if r.replace_index is not None}) != len([r for r in norm_plays if r.replace_index is not None]):
        raise ValidationError("Two designed plays replace the same stock play.")

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
    next_formation_index = old_formation_count
    for i, req in enumerate(norm_formations):
        if req.replace_index is None:
            dst_idx = next_formation_index
            next_formation_index += 1
        else:
            dst_idx = req.replace_index
        src_f = FORMATION_BASE + req.donor_formation_index * FORMATION_SIZE
        dst_f = FORMATION_BASE + dst_idx * FORMATION_SIZE
        src_aux = FORMATION_AUX_BASE + req.donor_formation_index * FORMATION_AUX_SIZE
        dst_aux = FORMATION_AUX_BASE + dst_idx * FORMATION_AUX_SIZE
        if req.replace_index is None:
            # Copy aux 0x50 verbatim (no relative fields inside aux – its entries are packed H not relative)
            replacement[body_off + dst_aux : body_off + dst_aux + FORMATION_AUX_SIZE] = raw_resource[
                body_off + src_aux : body_off + src_aux + FORMATION_AUX_SIZE
            ]
        else:
            # Replacing in place keeps the target's play menu but takes the donor's personnel words.
            replacement[body_off + dst_aux + 0x48 : body_off + dst_aux + 0x50] = raw_resource[
                body_off + src_aux + 0x48 : body_off + src_aux + 0x50
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
    next_play_index = old_play_count
    for i, req in enumerate(norm_plays):
        if req.replace_index is None:
            dst_idx = next_play_index
            next_play_index += 1
        else:
            dst_idx = req.replace_index
        src_p = PLAY_BASE + req.donor_play_index * PLAY_SIZE
        dst_p = PLAY_BASE + dst_idx * PLAY_SIZE
        # Copy whole play then patch relatives
        replacement[body_off + dst_p : body_off + dst_p + PLAY_SIZE] = raw_resource[
            body_off + src_p : body_off + src_p + PLAY_SIZE
        ]
        if req.play_flags is not None:
            # The header word carries the class the game plays the play as (bits 12-15:
            # 0x6000 pass, 0x8000 run); the type code and family (bits 0-8) are what the
            # validator checks and must stay the donor's.
            src_flags = struct.unpack_from("<I", raw_resource, body_off + src_p + 4)[0]
            if (req.play_flags & PLAY_FLAGS_KEEP_MASK) != (src_flags & PLAY_FLAGS_KEEP_MASK):
                raise ValidationError(
                    "Play flags must keep the donor play's family and type code (bits 0-8)."
                )
            struct.pack_into("<I", replacement, body_off + dst_p + 4, req.play_flags)
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

    # ---- Stage 3: authoring (formation geometry, personnel, node chains) ----
    node_count = struct.unpack_from("<I", raw_resource, body_off + 0x40)[0]
    node_cursor = node_count
    node_capacity = (STRING_BASE - NODE_BASE) // NODE_SIZE
    authored_node_start = NODE_BASE + node_count * NODE_SIZE
    category_positions: dict[int, bytes] = {}
    for cat_index in range(len(source.categories)):
        c_off = CATEGORY_BASE + cat_index * CATEGORY_SIZE
        category_positions[cat_index] = bytes(raw_resource[body_off + c_off + 5: body_off + c_off + 16])
    authored_formations: list[dict[str, Any]] = []
    authored_plays: list[dict[str, Any]] = []

    # Personnel groups written by designed formations (an unused / replaced group
    # gets the designer's eleven position codes; the record's name stays).
    written_categories: dict[int, tuple[int, ...]] = {}
    for req in norm_formations:
        if req.category_positions is None:
            continue
        cat = req.category_index
        assert cat is not None
        if cat >= len(source.categories):
            raise ValidationError(
                f"This book has {len(source.categories)} personnel groups; "
                f"index {cat} does not exist."
            )
        if cat in written_categories and written_categories[cat] != tuple(req.category_positions):
            raise ValidationError("Two designed formations write different personnel into the same group.")
        written_categories[cat] = tuple(req.category_positions)
        c_off = CATEGORY_BASE + cat * CATEGORY_SIZE
        replacement[body_off + c_off + 5: body_off + c_off + 16] = bytes(req.category_positions)
        category_positions[cat] = bytes(req.category_positions)
        allowed.append(range(body_off + c_off + 5, body_off + c_off + 16))

    for i, req in enumerate(norm_formations):
        if req.slot_positions is None and req.category_index is None:
            continue
        dst_idx = new_formation_indices[i]
        dst_f = FORMATION_BASE + dst_idx * FORMATION_SIZE
        dst_aux = FORMATION_AUX_BASE + dst_idx * FORMATION_AUX_SIZE
        if req.category_index is not None:
            if req.category_index >= len(source.categories):
                raise ValidationError(
                    f"This book has {len(source.categories)} personnel groups; "
                    f"index {req.category_index} does not exist."
                )
            word = struct.unpack_from("<I", replacement, body_off + dst_aux + 0x48)[0]
            struct.pack_into("<I", replacement, body_off + dst_aux + 0x48, (word & ~0x3F) | req.category_index)
            struct.pack_into("<I", replacement, body_off + dst_aux + 0x4C, 1 << req.category_index)
        cat_index = struct.unpack_from("<I", replacement, body_off + dst_aux + 0x48)[0] & 0x3F
        poscodes = category_positions.get(cat_index)
        if req.slot_positions is not None:
            record = codec.FormationRecord.from_bytes(
                bytes(replacement[body_off + dst_f: body_off + dst_f + FORMATION_SIZE])
            )
            for slot_index, (x_cm, z_cm) in enumerate(req.slot_positions):
                record.set_position(slot_index, x_cm, z_cm)
            record.recompute_mirrors(poscodes)
            if record.type_code < 4 and record.qb_alignment in (1, 2):
                # The lineup places the QB (and picks the snap) from this flag, not from
                # the depth alone: every retail gun formation carries bit 19, every
                # under-center one bit 18.
                record.set_qb_alignment(record.slots[0].z[0] <= codec.SHOTGUN_DEPTH_THRESHOLD_CM)
            replacement[body_off + dst_f: body_off + dst_f + FORMATION_SIZE] = record.to_bytes()
            authored_formations.append({
                "formation_index": dst_idx,
                "slot_positions": [list(pair) for pair in req.slot_positions],
                "mirror_partners": [slot.mirror_partner for slot in record.slots],
                "category_index": cat_index,
                "position_codes": list(poscodes) if poscodes else None,
                "qb_alignment": record.qb_alignment,
                "flags": f"0x{record.flags:08x}",
            })
        else:
            authored_formations.append({"formation_index": dst_idx, "category_index": cat_index})

    for i, req in enumerate(norm_plays):
        if req.assignments is None:
            continue
        dst_idx = new_play_indices[i]
        dst_p = PLAY_BASE + dst_idx * PLAY_SIZE
        play_flags = struct.unpack_from("<I", replacement, body_off + dst_p + 4)[0]
        assignments: list[tuple[int, list[bytes]]] = []
        donor_descriptors: list[int] = []
        for slot_index in range(11):
            desc_field = dst_p + 8 + slot_index * 8
            ptr_field = dst_p + 0x0C + slot_index * 8
            desc = struct.unpack_from("<I", replacement, body_off + desc_field)[0]
            stored = struct.unpack_from("<i", replacement, body_off + ptr_field)[0]
            target = ptr_field - 1 + stored
            count = desc & 0xF
            nodes = [
                bytes(replacement[body_off + target + k * NODE_SIZE: body_off + target + (k + 1) * NODE_SIZE])
                for k in range(count)
            ]
            assignments.append((desc, nodes))
            donor_descriptors.append(desc)
        for slot_index, chain in enumerate(req.assignments):
            if chain is None:
                continue
            nodes = []
            for op, vals in chain:
                specs = codec.OPERAND_SCHEMAS.get(op, ())
                operands = list(vals) + [0.0] * (len(specs) - len(vals))
                nodes.append(codec.Node(op, 0, operands))
            codec.assign_node_flags(nodes)
            raw_nodes = [node.to_bytes() for node in nodes]
            need = len(raw_nodes)
            if node_cursor + need > node_capacity:
                raise ValidationError(
                    f"This book's node pool is full ({node_capacity} nodes); the authored "
                    "chains do not fit. Shorten routes or pick another book."
                )
            start_off = NODE_BASE + node_cursor * NODE_SIZE
            if any(replacement[body_off + start_off: body_off + start_off + need * NODE_SIZE]):
                raise ValidationError(
                    "The node pool tail is not the expected zero padding, so new "
                    "chains cannot be appended safely."
                )
            replacement[body_off + start_off: body_off + start_off + need * NODE_SIZE] = b"".join(raw_nodes)
            ptr_field = dst_p + 0x0C + slot_index * 8
            struct.pack_into("<i", replacement, body_off + ptr_field, start_off - ptr_field + 1)
            assignments[slot_index] = (donor_descriptors[slot_index], raw_nodes)
            node_cursor += need
        for slot_index, chain in enumerate(req.assignments):
            if chain is None:
                continue
            desc = codec.build_descriptor(
                play_flags, assignments, slot_index, donor_descriptors[slot_index] >> 24
            )
            assignments[slot_index] = (desc, assignments[slot_index][1])
            struct.pack_into("<I", replacement, body_off + dst_p + 8 + slot_index * 8, desc)
        error = codec.validate_play(play_flags, assignments)
        if error:
            raise ValidationError(
                f"The game would reject the authored play “{req.custom_name or source.plays[req.donor_play_index].name}”: {error}"
            )
        authored_plays.append({
            "play_index": dst_idx,
            "authored_slots": [k for k, chain in enumerate(req.assignments) if chain is not None],
            "descriptors": [f"0x{d:08x}" for d, _ in assignments],
            "node_counts": [len(n) for _, n in assignments],
        })

    if node_cursor != node_count:
        struct.pack_into("<I", replacement, body_off + 0x40, node_cursor)
        allowed.append(range(body_off + 0x40, body_off + 0x44))
        allowed.append(range(body_off + authored_node_start, body_off + NODE_BASE + node_cursor * NODE_SIZE))

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
        link_source = req.replace_index if req.replace_index is not None else req.donor_formation_index
        src_links = source.formations[link_source].play_links
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
        expected_flags = req.play_flags if req.play_flags is not None else src_play.flags_or_id
        if dst_play.flags_or_id != expected_flags:
            raise ValidationError("Cloned play flags did not match the request.")
        if len(dst_play.assignments) != len(src_play.assignments):
            raise ValidationError("Cloned play assignments did not match donor.")
        for slot_index, (sa, da) in enumerate(zip(src_play.assignments, dst_play.assignments)):
            authored = req.assignments is not None and req.assignments[slot_index] is not None
            if authored:
                if da.chain_start_index < node_count:
                    raise ValidationError("Authored chain did not land in the appended node region.")
                continue
            if sa.descriptor_word != da.descriptor_word or sa.chain_start_index != da.chain_start_index:
                raise ValidationError("Cloned play assignment did not match donor.")
    for i, req in enumerate(norm_formations):
        if req.slot_positions is None:
            continue
        dst = new_formation_indices[i]
        rec = codec.FormationRecord.from_bytes(
            rebuilt[RESOURCE_HEADER_SIZE + FORMATION_BASE + dst * FORMATION_SIZE:
                    RESOURCE_HEADER_SIZE + FORMATION_BASE + (dst + 1) * FORMATION_SIZE]
        )
        for slot_index, (x_cm, z_cm) in enumerate(req.slot_positions):
            if rec.slots[slot_index].x[0] != int(round(x_cm)) or rec.slots[slot_index].z[0] != int(round(z_cm)):
                raise ValidationError("Authored formation position did not survive reparse.")

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
        "new_formation_indices": list(new_formation_indices),
        "new_play_indices": list(new_play_indices),
        "replaced_formation_indices": [r.replace_index for r in norm_formations if r.replace_index is not None],
        "replaced_play_indices": [r.replace_index for r in norm_plays if r.replace_index is not None],
        "formation_donors": [r.donor_formation_index for r in norm_formations],
        "play_donors": [r.donor_play_index for r in norm_plays],
        "links": [
            [l["formation_index"], l["play_index"], l["group"], l["slot_index"]]
            for l in applied_links
        ],
        "custom_names": [
            r.custom_name for r in (*norm_formations, *norm_plays) if r.custom_name
        ],
        "authored_formations": list(authored_formations),
        "authored_plays": list(authored_plays),
        "old_node_count": node_count,
        "new_node_count": node_cursor,
        "changed_ranges": [list(pair) for pair in changed],
        "claims": {
            "source_and_replacement_fully_reparsed": True,
            "only_owned_formation_play_records_and_counts_changed": True,
            "aux_link_group_semantics_claimed": False,
            "custom_name_runtime_visibility_claimed": False,
            "node_or_opcode_authoring_claimed": bool(authored_plays),
            "authored_plays_pass_ported_game_validator": bool(authored_plays),
            "formation_geometry_authored": bool(authored_formations),
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
        # retail-rip provenance; the build re-derives the absolute from the target image's directory
        "xiso_pack_sector": PACK0_RETAIL_SECTOR,
        "xiso_pack_size": PACK0_SIZE,
        "xiso_pack_sha256": PACK0_SHA256,
        "pack_offset": pack_offset,
        "xiso_absolute_span_offset": PACK0_RETAIL_BYTE_OFFSET + pack_offset,
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
