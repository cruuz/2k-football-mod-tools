"""Edit APF 2K8 stock CPU playbooks (``SPLB``) in a copied volume.

These are the books the CPU actually calls from.  A roster save's 36 offensive
and 33 defensive playbook records are only *labels*: they carry a name, a type
string and a side, with no content pointer at all, and they resolve to seven
offensive and four defensive real types.  The content lives here, on the disc,
as fifteen ``SPLB`` resources of exactly 32,288 bytes each.

Layout, established by decoding all fifteen books and checking every decoded
name against the MASTER ``PLAY`` resource:

* ``0x0C`` magic ``BLPS``; ``0x20`` inner name ``spb`` UTF-16BE; ``0x30`` book
  name UTF-16BE (``O-ZoneBlock``, ``X-43Cover2``, ...).
* A 176-record array covering ``0x0070``..``0x7970``, stride 176.  Record *k*
  is 168 bytes of entries at ``0x70 + 176k`` followed by an 8-byte trailer at
  ``0x118 + 176k``.  The trailer is a *trailer*, not a header: ``0x68..0x6F`` is
  zero in every book, and reading it as a leading header makes every book's
  record 0 claim formation 0.
* Trailer word A (``+0xA8``, big-endian u32): bits 31..24 are the MASTER
  formation index, bits 23..17 the primary category, and three 3-bit fields at
  16..14, 13..11 and 10..8 whose meaning is **not** established.  Trailer word
  B (``+0xAC``) is a category membership bitmask.
* Each entry is a big-endian u16: bits 15..13 ``X``, bits 12..10 ``Y``, bits
  9..0 the MASTER play index (0..585).  Entries are always a contiguous prefix
  followed by pure ``0x13FF`` filler -- no exceptions across 2,640 records --
  and ``0x13FF`` is simply an out-of-range play index used as a terminator.

Why the unproved fields do not block this writer: it only ever rewrites the
168-byte entry prefix of one record.  The trailer, both unmapped tail regions
(``0x7998``..``0x79E4`` and ``0x7D98``..``0x7E08``), every other record and
every other byte of the volume are preserved exactly, and an independent
verifier re-derives that before anything is published.

``Y`` marks four distinguished plays per formation: every populated record has
exactly one ``Y == 1`` entry, and at most one each of 0, 2 and 3, with the rest
``Y == 4``.  Which situation each tag denotes is unproved, so this writer
refuses to remove a tagged entry rather than guess what would break.
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
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_texture_patch  # type: ignore  # noqa: E402
import playbook_inventory  # type: ignore  # noqa: E402


PROVIDER_KIND = "splb_book_membership"
REPORT_SCHEMA = "apf2k8_splb_book_membership/v1"
PAYLOAD_SCHEMA = "apf2k8_splb_book_membership_replacement/v1"

RECORD_BASE = 0x0070
RECORD_STRIDE = 176
RECORD_COUNT = 176
ENTRY_BYTES = 168
ENTRY_CAPACITY = ENTRY_BYTES // 2          # 84
TRAILER_OFFSET = 0xA8
ARRAY_END = RECORD_BASE + RECORD_STRIDE * RECORD_COUNT   # 0x7970
RESOURCE_SIZE = 32_288
FILLER = 0x13FF
PLAY_MASK = 0x3FF
UNTAGGED_Y = 4
NEUTRAL_X = 2

#: outer entry -> book name, as shipped. Fifteen resources; four carry no name.
STOCK_BOOKS: Mapping[int, str] = {
    130: "O-ManBlock",
    134: "X-43Cover2",
    259: "O-TwoBack",
    293: "",
    369: "O-SinglebackAce",
    618: "X-34Base",
    656: "",
    767: "O-Singleback3WR",
    891: "O-WestCoast",
    943: "O-ZoneBlock",
    957: "X-43Blitz",
    1037: "",
    1405: "X-34ZoneBlitz",
    1411: "O-Shotgun",
    1439: "",
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def entry_selector(outer_index: int, record_index: int, play_index: int) -> str:
    return f"splb:{outer_index}:r{record_index}:p{play_index}"


@dataclass(frozen=True, slots=True)
class SplbEntry:
    x: int
    y: int
    play_index: int

    @property
    def tagged(self) -> bool:
        return self.y != UNTAGGED_Y

    def encode(self) -> int:
        return (self.x << 13) | (self.y << 10) | self.play_index


@dataclass(frozen=True, slots=True)
class SplbRecord:
    record_index: int
    formation_index: int
    category_index: int
    entries: tuple[SplbEntry, ...]
    trailer: bytes

    @property
    def populated(self) -> bool:
        return bool(self.entries)


@dataclass(frozen=True, slots=True)
class SplbBook:
    outer_index: int
    name: str
    body: bytes
    records: tuple[SplbRecord, ...]


@dataclass(frozen=True, slots=True)
class MembershipChange:
    """Add or remove one MASTER play from one record of one book."""

    outer_index: int
    record_index: int
    play_index: int
    member: bool

    @property
    def selector(self) -> str:
        return entry_selector(self.outer_index, self.record_index, self.play_index)


@dataclass(frozen=True, slots=True)
class CompiledBook:
    outer_index: int
    entry_bytes: bytes
    replacement: bytes
    report: Mapping[str, Any]


def _decode_entries(body: bytes, record_index: int) -> tuple[SplbEntry, ...]:
    base = RECORD_BASE + record_index * RECORD_STRIDE
    entries: list[SplbEntry] = []
    seen_filler = False
    for slot in range(ENTRY_CAPACITY):
        raw = struct.unpack_from(">H", body, base + slot * 2)[0]
        if raw == FILLER:
            seen_filler = True
            continue
        if seen_filler:
            raise ValidationError(
                f"SPLB record {record_index} has an entry after its terminator; "
                "this book does not match the proved layout"
            )
        entries.append(SplbEntry((raw >> 13) & 0x7, (raw >> 10) & 0x7, raw & PLAY_MASK))
    return tuple(entries)


def parse_book(body: bytes, outer_index: int) -> SplbBook:
    """Decode one stock playbook. Refuses anything that is not the proved shape."""

    if len(body) != RESOURCE_SIZE:
        raise ValidationError(
            f"An APF stock playbook is {RESOURCE_SIZE} bytes; this one is {len(body)}"
        )
    if body[0x0C:0x10] != b"BLPS":
        raise ValidationError("This resource is not an APF stock playbook (no BLPS)")
    name = body[0x30:0x68].decode("utf-16-be", errors="ignore").split("\x00")[0]
    records: list[SplbRecord] = []
    for index in range(RECORD_COUNT):
        trailer_at = RECORD_BASE + index * RECORD_STRIDE + TRAILER_OFFSET
        trailer = body[trailer_at : trailer_at + 8]
        word_a = struct.unpack_from(">I", trailer, 0)[0]
        records.append(
            SplbRecord(
                record_index=index,
                formation_index=word_a >> 24,
                category_index=(word_a >> 17) & 0x7F,
                entries=_decode_entries(body, index),
                trailer=trailer,
            )
        )
    return SplbBook(outer_index, name, body, tuple(records))


def read_book(index_path: Path, outer_index: int) -> SplbBook:
    """Read and validate one stock playbook out of the user's own game."""

    if outer_index not in STOCK_BOOKS:
        raise ValidationError(f"Outer entry {outer_index} is not a stock playbook")
    try:
        archive = apf_outer.parse_archive(Path(index_path))
        entry = archive.entries[outer_index]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            if record.block_count != 1 or record.file_count != 1:
                raise ValidationError("APF stock playbook IFF ownership changed")
            item = record.files[0]
            if item.name != "spb" or item.type_name != "SPLB":
                raise ValidationError("APF stock playbook inner ownership changed")
            part = item.parts[0]
            decoded = apf_inner.decode_block(reader, record, part.block_index, 64 * 1024 * 1024)
            body = decoded[part.offset : part.offset + part.length]
    except ValidationError:
        raise
    except (OSError, IndexError, apf_inner.FormatError, apf_outer.FormatError) as exc:
        raise ValidationError(f"Could not open the APF stock playbook: {exc}") from exc
    return parse_book(body, outer_index)


def _normalize(changes: Iterable[MembershipChange]) -> tuple[MembershipChange, ...]:
    resolved: dict[tuple[int, int, int], MembershipChange] = {}
    for change in changes:
        if not isinstance(change, MembershipChange):
            raise ValidationError("A stock-playbook change is malformed")
        key = (change.outer_index, change.record_index, change.play_index)
        if key in resolved and resolved[key].member != change.member:
            raise ValidationError(
                "One stock-playbook slot is both added and removed in a single request"
            )
        resolved[key] = change
    if not resolved:
        raise ValidationError("No stock-playbook changes were supplied")
    outers = {change.outer_index for change in resolved.values()}
    if len(outers) != 1:
        raise ValidationError("Compile one stock playbook at a time")
    return tuple(resolved[key] for key in sorted(resolved))


def compile_book(book: SplbBook, changes: Iterable[MembershipChange]) -> CompiledBook:
    """Rewrite only the entry prefixes the changes touch."""

    normalized = _normalize(changes)
    if normalized[0].outer_index != book.outer_index:
        raise ValidationError("These changes belong to a different stock playbook")
    play_count = 586
    replacement = bytearray(book.body)
    applied: list[dict[str, Any]] = []
    by_record: dict[int, list[MembershipChange]] = {}
    for change in normalized:
        by_record.setdefault(change.record_index, []).append(change)

    for record_index, record_changes in sorted(by_record.items()):
        if not 0 <= record_index < RECORD_COUNT:
            raise ValidationError(f"Record {record_index} is outside this book")
        record = book.records[record_index]
        entries = list(record.entries)
        by_play = {entry.play_index: entry for entry in entries}
        for change in record_changes:
            if not 0 <= change.play_index < play_count:
                raise ValidationError(
                    f"Play {change.play_index} is outside MASTER's {play_count} plays"
                )
            present = change.play_index in by_play
            if change.member and present:
                continue
            if not change.member and not present:
                continue
            if change.member:
                # X is constant for a (book, play) pair wherever it already
                # appears; reuse it so an added play behaves like the same play
                # elsewhere in this book. Otherwise take the neutral default the
                # game itself writes into every unused record.
                existing = next(
                    (
                        other.x
                        for candidate in book.records
                        for other in candidate.entries
                        if other.play_index == change.play_index
                    ),
                    NEUTRAL_X,
                )
                if len(entries) >= ENTRY_CAPACITY:
                    raise ValidationError(
                        f"Record {record_index} already holds the maximum "
                        f"{ENTRY_CAPACITY} plays"
                    )
                entries.append(SplbEntry(existing, UNTAGGED_Y, change.play_index))
            else:
                victim = by_play[change.play_index]
                if victim.tagged:
                    raise ValidationError(
                        f"Play {change.play_index} is a tagged slot (Y={victim.y}) in "
                        f"record {record_index}. Those four per-formation tags have "
                        "an unproved meaning, so removing one is refused rather "
                        "than guessed."
                    )
                entries = [e for e in entries if e.play_index != change.play_index]
            by_play = {entry.play_index: entry for entry in entries}
            applied.append(
                {
                    "selector": change.selector,
                    "record_index": record_index,
                    "formation_index": record.formation_index,
                    "play_index": change.play_index,
                    "member_after": change.member,
                }
            )
        if len(entries) > ENTRY_CAPACITY:
            raise ValidationError(f"Record {record_index} overflowed its 84 entry slots")
        base = RECORD_BASE + record_index * RECORD_STRIDE
        for slot in range(ENTRY_CAPACITY):
            value = entries[slot].encode() if slot < len(entries) else FILLER
            struct.pack_into(">H", replacement, base + slot * 2, value)

    if len(replacement) != len(book.body):
        raise ValidationError("A stock-playbook edit changed the resource length")
    report = {
        "schema": REPORT_SCHEMA,
        "provider_kind": PROVIDER_KIND,
        "outer_index": book.outer_index,
        "book_name": book.name,
        "changes": applied,
        "claims": {
            "entry_prefix_only": True,
            "trailers_untouched": True,
            "unmapped_tail_untouched": True,
            "resource_length_unchanged": True,
            "tagged_slots_never_removed": True,
            "cpu_behaviour_runtime_proved": False,
        },
    }
    return CompiledBook(book.outer_index, b"", bytes(replacement), report)


def verify_book(before: bytes, after: bytes, changes: Iterable[MembershipChange]) -> Mapping[str, Any]:
    """Re-derive every changed byte without trusting the compiler.

    Every difference must fall inside the 168-byte entry region of a record a
    change named. A trailer byte, either unmapped tail region, or any other
    record fails here rather than in someone's game.
    """

    normalized = _normalize(changes)
    if len(before) != len(after):
        raise ValidationError("Stock-playbook verification: resource length changed")
    touched = {change.record_index for change in normalized}
    allowed: set[int] = set()
    for record_index in touched:
        base = RECORD_BASE + record_index * RECORD_STRIDE
        allowed.update(range(base, base + ENTRY_BYTES))
    differing = [i for i in range(len(before)) if before[i] != after[i]]
    for offset in differing:
        if offset not in allowed:
            raise ValidationError(
                f"Stock-playbook verification: byte 0x{offset:x} changed outside the "
                "entry region of any record a change named"
            )
    # The decoded result must actually say what was asked.
    parsed_before = parse_book(before, normalized[0].outer_index)
    parsed_after = parse_book(after, normalized[0].outer_index)
    for change in normalized:
        record = parsed_after.records[change.record_index]
        present = any(e.play_index == change.play_index for e in record.entries)
        if present != change.member:
            raise ValidationError(
                "Stock-playbook verification: the reparsed book disagrees with the "
                f"request for record {change.record_index} play {change.play_index}"
            )
    for index, (a, b) in enumerate(zip(parsed_before.records, parsed_after.records)):
        if a.trailer != b.trailer:
            raise ValidationError(
                f"Stock-playbook verification: record {index} trailer changed"
            )
        if index not in touched and a.entries != b.entries:
            raise ValidationError(
                f"Stock-playbook verification: untouched record {index} changed"
            )
    return {
        "schema": REPORT_SCHEMA,
        "changed_byte_count": len(differing),
        "changed_records": sorted(touched),
        "independent_reparse": True,
    }


def build_book_patch(
    index_path: Path, changes: Iterable[MembershipChange]
) -> CompiledBook:
    """Compile changes into a rebuilt outer entry without touching the source."""

    normalized = _normalize(changes)
    outer_index = normalized[0].outer_index
    book = read_book(Path(index_path), outer_index)
    compiled = compile_book(book, normalized)

    try:
        archive = apf_outer.parse_archive(Path(index_path))
        entry = archive.entries[outer_index]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            original_entry = reader.read(entry, 0, entry.size)
            original_blocks = [
                apf_inner.decode_block(reader, record, i, 64 * 1024 * 1024)
                for i in range(record.block_count)
            ]
            original_stored = [
                reader.read(entry, block.start_offset, block.stored_length)
                for block in record.blocks
            ]
    except (OSError, IndexError, apf_inner.FormatError, apf_outer.FormatError) as exc:
        raise ValidationError(f"Could not open the APF stock playbook: {exc}") from exc

    target_part = record.files[0].parts[0]
    patched_block = bytearray(original_blocks[target_part.block_index])
    patched_block[target_part.offset : target_part.offset + target_part.length] = (
        compiled.replacement
    )
    new_block = bytes(patched_block)
    descriptor = record.blocks[target_part.block_index]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise ValidationError("The APF stock playbook block is no longer H7A-compressed")
    try:
        compressed, preservation = apf_inner.encode_h7a_preserving_tokens(
            original_stored[target_part.block_index][apf_inner.H7A_HEADER_SIZE :],
            original_blocks[target_part.block_index],
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
        raise ValidationError(f"Could not encode the stock playbook H7A: {exc}") from exc
    if roundtrip != new_block:
        raise ValidationError("Stock-playbook H7A round trip changed the edit")

    header = bytearray(original_entry[: record.header_size])
    struct.pack_into(
        ">8I",
        header,
        apf_inner.IFF_HEADER_SIZE,
        descriptor.name_hash,
        descriptor.type_hash,
        descriptor.unknown_08,
        descriptor.uncompressed_length,
        descriptor.unknown_10,
        record.header_size,
        len(stored),
        descriptor.indexed,
    )
    file_length = record.header_size + len(stored)
    struct.pack_into(">I", header, 0x08, file_length)
    footer_size = 8 + record.footer.payload_size
    footer = original_entry[record.file_length : record.file_length + footer_size]
    if any(original_entry[record.file_length + footer_size :]):
        raise ValidationError("The stock-playbook outer allocation has a nonzero tail")
    active = bytes(header) + stored + footer
    if len(active) > entry.size:
        raise ValidationError(
            "The edited stock playbook does not fit the game's fixed allocation"
        )
    rebuilt = active + b"\0" * (entry.size - len(active))

    memory = apf_texture_patch.BytesReader(rebuilt)
    try:
        reparsed = apf_inner.parse_iff(memory, entry)
        decoded = apf_inner.decode_block(
            memory, reparsed, target_part.block_index, 64 * 1024 * 1024
        )
    except apf_inner.FormatError as exc:
        raise ValidationError(f"The rebuilt stock playbook is invalid: {exc}") from exc
    if reparsed.warnings or decoded != new_block:
        raise ValidationError("The rebuilt stock playbook changed its decoded block")
    rebuilt_part = reparsed.files[0].parts[0]
    verified = decoded[rebuilt_part.offset : rebuilt_part.offset + rebuilt_part.length]
    verification = verify_book(book.body, verified, normalized)

    report = {
        **dict(compiled.report),
        "output_entry_size": len(rebuilt),
        "output_entry_sha256": _sha256(rebuilt),
        "verification": dict(verification),
        "h7a_transport": {"strategy": "retail-token-preserving", **preservation},
        "claims": {
            **dict(compiled.report["claims"]),
            "fixed_outer_allocation_preserved": True,
            "h7a_round_trip_exact": True,
        },
    }
    return CompiledBook(outer_index, rebuilt, compiled.replacement, report)


__all__ = [
    "ARRAY_END",
    "ENTRY_CAPACITY",
    "FILLER",
    "PAYLOAD_SCHEMA",
    "PROVIDER_KIND",
    "RECORD_BASE",
    "RECORD_COUNT",
    "RECORD_STRIDE",
    "REPORT_SCHEMA",
    "STOCK_BOOKS",
    "CompiledBook",
    "MembershipChange",
    "SplbBook",
    "SplbEntry",
    "SplbRecord",
    "build_book_patch",
    "compile_book",
    "entry_selector",
    "parse_book",
    "read_book",
    "verify_book",
]
