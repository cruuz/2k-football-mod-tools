"""Add and remove plays inside APF 2K8 MASTER formations.

Swapping which of the stock books a team calls from was the only playbook edit
this product offered, and it is also the only one APF's community editor
offers.  It is a coarse control: the 36 offensive and 33 defensive book records
in a roster save are *labels*, and they collapse to a handful of distinct types
(seven offensive and four defensive in the two real saves measured, plus the
user-created ``USER-o``/``USER-d`` books), so "changing playbook" often changes
nothing at all.

This module edits the level below that.  APF's MASTER ``PLAY`` resource stores,
for each of its 163 formations, a fixed 74-byte bitmap over the book's 586
plays: play ``n`` belongs to a formation when
``row[n // 8] & (0x80 >> (n % 8))`` is set.  ``playbook_inventory`` already
parses and names that table; this writer flips exactly those bits.

Why that is safe to write when route nodes are not: a membership bit is one bit
in a fixed-size row of a fixed-capacity table.  Nothing moves, no pointer is
re-encoded, no count changes, and the resource's byte extent is identical --
so the edit is provable by byte-diff rather than by interpreting game logic.
Formation and play *records themselves*, route nodes, names, categories, and
the ten opaque bytes trailing each membership row are never touched.

What is proved and what is not: the changed bytes, their exact positions, and
that everything else in the volume is byte-identical.  Whether the CPU's
play-calling reads this same table is NOT established here -- the CPU book
types are named only inside a roster save, and appear in neither the disc's
single MASTER resource nor the decrypted executable.  This edits the book the
game selects plays from; it does not claim to retune the AI.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Any, Iterable, Mapping

from .errors import ValidationError
from mod_editor.apf_studio.backend import ensure_tools_importable


ensure_tools_importable()
import playbook_inventory  # type: ignore  # noqa: E402
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_texture_patch  # type: ignore  # noqa: E402


PROVIDER_KIND = "play_formation_membership"
REPORT_SCHEMA = "apf2k8_play_formation_membership/v1"
PAYLOAD_SCHEMA = "apf2k8_play_formation_membership_replacement/v1"
MASTER_ASSET_ID = "apf:playbook:180:0"
MASTER_OUTER_INDEX = 180

#: Mirrored from ``playbook_inventory`` so a layout change there fails this
#: writer closed rather than silently moving which bytes it edits.
MEMBERSHIP_BASE = playbook_inventory.APF_FORMATION_MEMBERSHIP_BASE
MEMBERSHIP_ROW = playbook_inventory.APF_FORMATION_MEMBERSHIP_SIZE
MEMBERSHIP_MASK = playbook_inventory.APF_FORMATION_MEMBERSHIP_MASK_SIZE
MEMBERSHIP_CAPACITY = playbook_inventory.APF_FORMATION_MEMBERSHIP_CAPACITY


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def membership_selector(formation_index: int, play_index: int) -> str:
    return f"play-membership:{MASTER_ASSET_ID}:f{formation_index}:p{play_index}"


@dataclass(frozen=True, slots=True)
class MembershipEdit:
    """One formation gains or loses one play. Logical selectors only."""

    formation_index: int
    play_index: int
    member: bool

    @property
    def selector(self) -> str:
        return membership_selector(self.formation_index, self.play_index)


@dataclass(frozen=True, slots=True)
class CompiledMembership:
    replacement: bytes
    replacement_sha256: str
    report: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CompiledMembershipEntry:
    outer_index: int
    entry_bytes: bytes
    compiled: CompiledMembership
    report: Mapping[str, Any]


def _integer(value: object, label: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{label} must be an integer")
    if not 0 <= value < maximum:
        raise ValidationError(f"{label} must be within 0..{maximum - 1}")
    return int(value)


def edit_from_mapping(value: Mapping[str, object]) -> MembershipEdit:
    if not isinstance(value, Mapping):
        raise ValidationError("A membership edit must be a mapping")
    unknown = set(value) - {"formation_index", "play_index", "member"}
    if unknown:
        raise ValidationError(
            f"Unknown membership edit fields: {', '.join(sorted(unknown))}"
        )
    member = value.get("member")
    if not isinstance(member, bool):
        raise ValidationError("member must be true or false")
    return MembershipEdit(
        formation_index=_integer(
            value.get("formation_index"), "formation_index", maximum=MEMBERSHIP_CAPACITY
        ),
        play_index=_integer(
            value.get("play_index"), "play_index", maximum=MEMBERSHIP_MASK * 8
        ),
        member=member,
    )


def encode_membership_payload(edits: Iterable[MembershipEdit]) -> bytes:
    document = {
        "schema": PAYLOAD_SCHEMA,
        "asset_id": MASTER_ASSET_ID,
        "edits": [
            {
                "formation_index": edit.formation_index,
                "play_index": edit.play_index,
                "member": edit.member,
            }
            for edit in _normalize(edits)
        ],
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def decode_membership_payload(payload: bytes) -> tuple[MembershipEdit, ...]:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Membership payload is not valid JSON: {exc}") from exc
    if (
        not isinstance(document, Mapping)
        or document.get("schema") != PAYLOAD_SCHEMA
        or document.get("asset_id") != MASTER_ASSET_ID
        or not isinstance(document.get("edits"), list)
    ):
        raise ValidationError("Membership payload schema is not recognised")
    return _normalize(edit_from_mapping(row) for row in document["edits"])


def _normalize(
    edits: Iterable[MembershipEdit | Mapping[str, object]]
) -> tuple[MembershipEdit, ...]:
    resolved: dict[tuple[int, int], MembershipEdit] = {}
    for candidate in edits:
        edit = (
            candidate
            if isinstance(candidate, MembershipEdit)
            else edit_from_mapping(candidate)
        )
        key = (edit.formation_index, edit.play_index)
        if key in resolved and resolved[key].member != edit.member:
            raise ValidationError(
                f"Formation {edit.formation_index} play {edit.play_index} is both "
                "added and removed in one request"
            )
        resolved[key] = edit
    if not resolved:
        raise ValidationError("No playbook membership edits were supplied")
    return tuple(resolved[key] for key in sorted(resolved))


def _parse(body: bytes) -> Mapping[str, Any]:
    return playbook_inventory.parse_apf_body(body, MASTER_OUTER_INDEX, 0)


def _row_offset(formation_index: int) -> int:
    return MEMBERSHIP_BASE + formation_index * MEMBERSHIP_ROW


def _bit(mask: bytes, play_index: int) -> bool:
    return bool(mask[play_index // 8] & (0x80 >> (play_index % 8)))


def compile_membership_edits(
    body: bytes, edits: Iterable[MembershipEdit | Mapping[str, object]]
) -> CompiledMembership:
    """Flip the requested membership bits in a copy of the MASTER body."""

    normalized = _normalize(edits)
    parsed = _parse(body)
    formations = list(parsed["formations"])  # type: ignore[index]
    plays = list(parsed["plays"])  # type: ignore[index]
    formation_count = len(formations)
    play_count = len(plays)

    replacement = bytearray(body)
    applied: list[dict[str, Any]] = []
    for edit in normalized:
        if edit.formation_index >= formation_count:
            raise ValidationError(
                f"This game has {formation_count} formations; "
                f"{edit.formation_index} is not one of them"
            )
        if edit.play_index >= play_count:
            raise ValidationError(
                f"This game has {play_count} plays; {edit.play_index} is not one of them"
            )
        offset = _row_offset(edit.formation_index)
        byte_offset = offset + edit.play_index // 8
        bit = 0x80 >> (edit.play_index % 8)
        before = bool(replacement[byte_offset] & bit)
        if edit.member:
            replacement[byte_offset] |= bit
        else:
            replacement[byte_offset] &= 0xFF ^ bit
        applied.append(
            {
                "selector": edit.selector,
                "formation_index": edit.formation_index,
                "formation_name": formations[edit.formation_index]["name"],
                "play_index": edit.play_index,
                "play_name": plays[edit.play_index]["name"],
                "member_before": before,
                "member_after": edit.member,
                "changed": before != edit.member,
                "byte_offset": byte_offset,
                "bit_mask": f"0x{bit:02x}",
            }
        )

    if len(replacement) != len(body):
        raise ValidationError("A membership edit changed the resource length")
    updated = _parse(bytes(replacement))
    for key in ("formation_count", "play_count", "category_count", "route_node_count"):
        if updated["root_counts"][key] != parsed["root_counts"][key]:  # type: ignore[index]
            raise ValidationError(f"A membership edit changed {key}")

    report = {
        "schema": REPORT_SCHEMA,
        "asset_id": MASTER_ASSET_ID,
        "provider_kind": PROVIDER_KIND,
        "edits": applied,
        "changed_bit_count": sum(1 for row in applied if row["changed"]),
        "formation_count": formation_count,
        "play_count": play_count,
        "claims": {
            "membership_bits_only": True,
            "resource_length_unchanged": True,
            "counts_unchanged": True,
            "route_nodes_untouched": True,
            "names_and_pointers_untouched": True,
            "cpu_play_calling_proved": False,
            "runtime_visibility_proved": False,
        },
    }
    return CompiledMembership(bytes(replacement), _sha256(bytes(replacement)), report)


def verify_membership_edits(
    before: bytes,
    after: bytes,
    edits: Iterable[MembershipEdit | Mapping[str, object]],
) -> Mapping[str, Any]:
    """Independently re-derive what changed, without trusting the compiler.

    Every differing byte must sit inside a membership mask, must belong to a
    formation an edit named, and must differ only in bits those edits asked
    for.  Anything else -- a moved pointer, a touched route node, a changed
    opaque row tail -- fails here rather than in a user's game.
    """

    normalized = _normalize(edits)
    if len(before) != len(after):
        raise ValidationError("Membership verification: resource length changed")
    wanted: dict[int, int] = {}
    for edit in normalized:
        byte_offset = _row_offset(edit.formation_index) + edit.play_index // 8
        wanted[byte_offset] = wanted.get(byte_offset, 0) | (
            0x80 >> (edit.play_index % 8)
        )
    differing = [index for index in range(len(before)) if before[index] != after[index]]
    for index in differing:
        if index not in wanted:
            raise ValidationError(
                f"Membership verification: byte 0x{index:x} changed but no edit "
                "named it"
            )
        changed_bits = before[index] ^ after[index]
        if changed_bits & ~wanted[index]:
            raise ValidationError(
                f"Membership verification: byte 0x{index:x} changed bits no edit "
                "asked for"
            )
        row_start = MEMBERSHIP_BASE + (
            (index - MEMBERSHIP_BASE) // MEMBERSHIP_ROW
        ) * MEMBERSHIP_ROW
        if not row_start <= index < row_start + MEMBERSHIP_MASK:
            raise ValidationError(
                f"Membership verification: byte 0x{index:x} is outside the "
                "membership mask"
            )
    parsed_before = _parse(before)
    parsed_after = _parse(after)
    if parsed_before["root_counts"] != parsed_after["root_counts"]:
        raise ValidationError("Membership verification: root counts changed")
    for edit in normalized:
        row = parsed_after["formations"][edit.formation_index]  # type: ignore[index]
        if (edit.play_index in row["play_membership_indices"]) != edit.member:
            raise ValidationError(
                "Membership verification: the reparsed book disagrees with the "
                f"requested state for formation {edit.formation_index} play "
                f"{edit.play_index}"
            )
    return {
        "schema": REPORT_SCHEMA,
        "replacement_sha256": _sha256(after),
        "changed_byte_count": len(differing),
        "changed_byte_offsets": [f"0x{index:x}" for index in differing],
        "independent_reparse": True,
    }


def build_membership_patch(
    index_path: Path,
    edits: Iterable[MembershipEdit | Mapping[str, object]],
) -> CompiledMembershipEntry:
    """Compile membership edits into a rebuilt outer 180 without touching source."""

    normalized = _normalize(edits)
    try:
        archive = apf_outer.parse_archive(Path(index_path))
        entry = archive.entries[MASTER_OUTER_INDEX]
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
    compiled = compile_membership_edits(original_body, normalized)
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
            "Edited playbook membership does not fit the game's fixed "
            "compressed allocation."
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
    verification = verify_membership_edits(original_body, verified_body, normalized)
    if verification["replacement_sha256"] != compiled.replacement_sha256:
        raise ValidationError(
            "Rebuilt APF MASTER PLAY differs from its compiler output."
        )
    report = {
        **dict(compiled.report),
        "outer_index": MASTER_OUTER_INDEX,
        "output_entry_size": len(rebuilt),
        "output_entry_sha256": _sha256(rebuilt),
        "verification": dict(verification),
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
    return CompiledMembershipEntry(MASTER_OUTER_INDEX, rebuilt, compiled, report)


__all__ = [
    "MASTER_ASSET_ID",
    "MASTER_OUTER_INDEX",
    "PAYLOAD_SCHEMA",
    "PROVIDER_KIND",
    "REPORT_SCHEMA",
    "CompiledMembership",
    "CompiledMembershipEntry",
    "MembershipEdit",
    "build_membership_patch",
    "compile_membership_edits",
    "decode_membership_payload",
    "edit_from_mapping",
    "encode_membership_payload",
    "membership_selector",
    "verify_membership_edits",
]
