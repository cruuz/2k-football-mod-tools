"""Edit APF 2K8 stock CPU playbooks (``SPLB``) in a copied volume.

These are the stock playbook resources the game ships.  A roster save's 36
offensive and 33 defensive playbook records are only *labels*: they carry a
name, a type string and a side, with no content pointer at all, and they resolve
to seven offensive and four defensive real types.  The stored membership lives
here, on the disc, as fifteen ``SPLB`` resources of exactly 32,288 bytes each.
Runtime CPU consumption of an edited membership list remains unproved.

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

``Y`` marks a small set of distinguished plays per formation, and across all 209
populated records of the fifteen retail books one rule is exact with zero
exceptions: a formation carries ``min(4, plays)`` tagged slots.  The eight
formations carrying fewer than four are exactly the eight with fewer than four
plays.  Which values those short formations use is a distribution rather than a
rule -- one play carries 1, two carry 0 and 1, three carry 0, 1 and 2 -- so this
writer only follows that order when it has to pick a slot the user did not.

Those tags are authored per formation, not a side effect of position.  In
``O-SinglebackAce`` the ``Ace`` and ``Ace Flip`` records hold byte-identical
77-play lists -- same play indices, same ``X`` values -- yet ``Ace`` tags entry
slots 70..73 while ``Ace Flip`` tags 0..3, and only 137 of the 209 records tag
their leading entries at all.

Three of the tags are the formation's **audibles**, proved in the game's own
code rather than inferred from the data's shape.  Community reporter Urianus
read it off the data first -- "the user only gets 3 per formation" -- and the
decompressed executable agrees.  The game does not merely read these bits, it
writes them::

    0x84864c70  rlwinm r11, r31, 1, 0, 30    ; entry index * 2
    0x84864c74  lhzx   r10, r11, r29         ; load the SPLB entry
    0x84864c78  rlwimi r10, r28, 10, 19, 21  ; insert r28 into bits 12..10
    0x84864c7c  sthx   r10, r11, r29         ; store it back
    0x84864c80  addi   r28, r28, 0x1
    0x84864c84  cmpwi  cr6, r28, 2
    0x84864c88  bngt   cr6, 0x84864bd4       ; counter runs 0, 1, 2
    0x84864c90  addi   r29, r29, -0xb0       ; -176: one record per formation

Three slots per formation, stepping exactly one record.  ``Y == 4`` is what an
untagged play carries and the loop scans for those as candidates.  The move
this writer performs is the game's own: ``0x84a8ab28`` takes a slot off one play
and puts it on another.  Supporting accessors: ``0x848630e8`` returns
``(entry >> 10) & 7``, ``0x848630f8`` writes it back with ``rlwimi``/``sthx``,
and ``0x84a8aa84`` returns the play whose ``Y`` equals a caller-supplied slot --
masking ``& 0x3FF``, skipping ``1023``, bounded at 84, every constant this
module already pins.

The **fourth** tag, ``Y == 3``, is a different matter: the assign loop never
writes it, and the only place the executable tests for it is a generic 3-bit
field clamp.  Its purpose is **not** established, so it is preserved and
movable but never explained.  A caution for whoever reads this next: the glyph
tokens ``|SQUARE|``/``|CROSS|``/``|CIRCLE|`` really are in the image, but
*nothing builds their addresses* -- they resolve by name through text
substitution.  String proximity is not a code path; find field access by
scanning for the instruction.  This writer
therefore edits the tags only in ways that keep the proved ``min(4, plays)``
rule exactly: a tag may be moved onto another play in the same formation, or
carried onto one when its play is removed, but it may never be dropped,
duplicated, or given a value the retail books never use.
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

#: The order retail spends tagged slots as a formation gains plays: the two
#: one-play formations carry only 1, the two two-play formations carry 0 and 1,
#: the four three-play formations carry 0, 1 and 2, and the other 201 carry all
#: four.  Used only to pick a slot the user has not picked; never to relabel one.
TAG_PRIORITY = (1, 0, 2, 3)
MAX_TAGS = len(TAG_PRIORITY)

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


def tag_selector(
    outer_index: int, record_index: int, from_play: int, to_play: int
) -> str:
    return f"splb:{outer_index}:r{record_index}:tag:{from_play}->{to_play}"


def required_tag_count(entry_count: int) -> int:
    """How many tagged slots a formation with this many plays carries in retail."""

    return min(MAX_TAGS, entry_count)


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
    """Add or remove one MASTER play from one record of one book.

    ``tag_heir`` answers the only question a removal can raise: when the play
    leaving holds a tagged slot the formation still needs, name the play in the
    same record that carries the slot on.  Leaving it ``None`` on such a removal
    is refused, because the writer will not pick a successor for the user.
    """

    outer_index: int
    record_index: int
    play_index: int
    member: bool
    tag_heir: int | None = None

    @property
    def selector(self) -> str:
        return entry_selector(self.outer_index, self.record_index, self.play_index)


@dataclass(frozen=True, slots=True)
class TagMove:
    """Move one tagged slot onto another play already in the same record.

    The two plays exchange their ``Y`` values, so the count of tagged slots is
    unchanged whether or not the destination already held one.
    """

    outer_index: int
    record_index: int
    from_play: int
    to_play: int

    @property
    def selector(self) -> str:
        return tag_selector(
            self.outer_index, self.record_index, self.from_play, self.to_play
        )


@dataclass(frozen=True, slots=True)
class _Request:
    outer_index: int
    memberships: tuple[MembershipChange, ...]
    moves: tuple[TagMove, ...]

    @property
    def record_indices(self) -> set[int]:
        return {change.record_index for change in self.memberships} | {
            move.record_index for move in self.moves
        }


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


def _normalize(changes: Iterable[MembershipChange | TagMove]) -> _Request:
    resolved: dict[tuple[int, int, int], MembershipChange] = {}
    moves: dict[tuple[int, int, int], TagMove] = {}
    for change in changes:
        if isinstance(change, MembershipChange):
            key = (change.outer_index, change.record_index, change.play_index)
            if key in resolved and resolved[key] != change:
                raise ValidationError(
                    "One stock-playbook slot is asked for twice with different "
                    "outcomes in a single request"
                )
            resolved[key] = change
        elif isinstance(change, TagMove):
            if change.from_play == change.to_play:
                raise ValidationError(
                    "A tagged slot cannot be moved onto the play that already holds it"
                )
            key = (change.outer_index, change.record_index, change.from_play)
            if key in moves and moves[key] != change:
                raise ValidationError(
                    "One tagged slot is moved to two different plays in a single request"
                )
            moves[key] = change
        else:
            raise ValidationError("A stock-playbook change is malformed")
    if not resolved and not moves:
        raise ValidationError("No stock-playbook changes were supplied")
    outers = {change.outer_index for change in resolved.values()}
    outers |= {move.outer_index for move in moves.values()}
    if len(outers) != 1:
        raise ValidationError("Compile one stock playbook at a time")
    # A move that names a play the same request deletes has no honest reading:
    # the user is asking for two different fates for one slot.
    dropped = {
        (change.record_index, change.play_index)
        for change in resolved.values()
        if not change.member
    }
    for move in moves.values():
        for play in (move.from_play, move.to_play):
            if (move.record_index, play) in dropped:
                raise ValidationError(
                    f"Play {play} is both removed and part of a tagged-slot move "
                    f"in record {move.record_index}"
                )
    return _Request(
        outers.pop(),
        tuple(resolved[key] for key in sorted(resolved)),
        tuple(moves[key] for key in sorted(moves)),
    )


def tags_of(entries: Iterable[SplbEntry]) -> list[int]:
    return [entry.y for entry in entries if entry.tagged]


def follows_tag_rule(entries: tuple[SplbEntry, ...]) -> bool:
    """Does this record obey the rule every retail record obeys?"""

    tags = tags_of(entries)
    return len(set(tags)) == len(tags) == required_tag_count(len(entries))


def retail_tag_shape(entries: tuple[SplbEntry, ...]) -> bool:
    """Is this record's tag *set* one of the four the retail books actually use?"""

    expected = TAG_PRIORITY[: required_tag_count(len(entries))]
    return sorted(tags_of(entries)) == sorted(expected)


def _next_free_tag(entries: Iterable[SplbEntry]) -> int | None:
    used = set(tags_of(entries))
    return next((tag for tag in TAG_PRIORITY if tag not in used), None)


def _check_tag_rule(
    record_index: int, before: tuple[SplbEntry, ...], after: list[SplbEntry]
) -> None:
    """Refuse anything that would put this record outside the proved rule.

    Records that already broke the rule before the edit -- nothing retail does,
    but a hand-built resource might -- are only held to not getting worse.
    """

    for entry in after:
        if entry.y > UNTAGGED_Y:
            raise ValidationError(
                f"Record {record_index} would give play {entry.play_index} Y={entry.y}; "
                f"only 0-3 (tagged) and {UNTAGGED_Y} (untagged) occur in the retail books"
            )
    tags = tags_of(after)
    if len(set(tags)) != len(tags):
        raise ValidationError(
            f"Record {record_index} would carry one tagged slot twice; each of 0-3 "
            "appears at most once in every retail record"
        )
    required = required_tag_count(len(after))
    if follows_tag_rule(before):
        if len(tags) != required:
            raise ValidationError(
                f"Record {record_index} would carry {len(tags)} tagged slots for "
                f"{len(after)} plays, and every retail formation carries {required}. "
                "Move the slot to another play in this formation, or name a play to "
                "carry it, instead of dropping it."
            )
    elif len(tags) < min(len(tags_of(before)), required):
        raise ValidationError(
            f"Record {record_index} already broke the tagged-slot rule and this edit "
            "would drop yet another slot"
        )
    if after and 1 in tags_of(before) and 1 not in tags:
        raise ValidationError(
            f"Record {record_index} would lose its slot-1 play, and every populated "
            "retail record has exactly one. Carry slot 1 onto another play in this "
            "formation instead."
        )


def apply_record_changes(
    book: SplbBook,
    record: SplbRecord,
    memberships: Iterable[MembershipChange] = (),
    moves: Iterable[TagMove] = (),
) -> tuple[SplbEntry, ...]:
    """Return one record's entries after the requested edits, or raise.

    Adds land first, then tagged-slot moves, then removals, so a play added in
    the same request can be named as the heir of a slot the request removes.
    """

    play_count = 586
    before = record.entries
    entries = list(before)

    def index_of(play: int) -> int | None:
        return next(
            (slot for slot, entry in enumerate(entries) if entry.play_index == play),
            None,
        )

    for change in memberships:
        if not 0 <= change.play_index < play_count:
            raise ValidationError(
                f"Play {change.play_index} is outside MASTER's {play_count} plays"
            )
        if not change.member or index_of(change.play_index) is not None:
            continue
        if len(entries) >= ENTRY_CAPACITY:
            raise ValidationError(
                f"Record {record.record_index} already holds the maximum "
                f"{ENTRY_CAPACITY} plays"
            )
        # X is constant for a (book, play) pair wherever it already appears;
        # reuse it so an added play behaves like the same play elsewhere in this
        # book. Otherwise take the neutral default the game writes into unused
        # records.
        x = next(
            (
                other.x
                for candidate in book.records
                for other in candidate.entries
                if other.play_index == change.play_index
            ),
            NEUTRAL_X,
        )
        # A formation short of plays is also short of tagged slots, so growing it
        # has to hand the new play the next slot or the min(4, plays) rule breaks.
        y = UNTAGGED_Y
        if len(tags_of(entries)) < required_tag_count(len(entries) + 1):
            free = _next_free_tag(entries)
            y = UNTAGGED_Y if free is None else free
        entries.append(SplbEntry(x, y, change.play_index))

    for move in moves:
        source = index_of(move.from_play)
        target = index_of(move.to_play)
        if source is None or target is None:
            missing = move.from_play if source is None else move.to_play
            raise ValidationError(
                f"Play {missing} is not in record {record.record_index}, so a tagged "
                "slot cannot be moved to or from it"
            )
        if not entries[source].tagged:
            raise ValidationError(
                f"Play {move.from_play} holds no tagged slot in record "
                f"{record.record_index}"
            )
        origin, destination = entries[source], entries[target]
        entries[source] = SplbEntry(origin.x, destination.y, origin.play_index)
        entries[target] = SplbEntry(destination.x, origin.y, destination.play_index)

    for change in memberships:
        if change.member:
            continue
        victim_at = index_of(change.play_index)
        if victim_at is None:
            continue
        victim = entries[victim_at]
        if victim.tagged and change.tag_heir is not None:
            heir_at = index_of(change.tag_heir)
            if heir_at is None or heir_at == victim_at:
                raise ValidationError(
                    f"Play {change.tag_heir} cannot carry tagged slot {victim.y}: it is "
                    f"not another play in record {record.record_index}"
                )
            heir = entries[heir_at]
            entries[heir_at] = SplbEntry(heir.x, victim.y, heir.play_index)
        elif victim.tagged and follows_tag_rule(before):
            surviving = len(tags_of(entries)) - 1
            if surviving != required_tag_count(len(entries) - 1):
                raise ValidationError(
                    f"Play {change.play_index} holds tagged slot {victim.y} in record "
                    f"{record.record_index}, and this formation has to keep "
                    f"{required_tag_count(len(entries) - 1)} tagged slots. Name another "
                    "play in the same formation to carry the slot, or move the slot "
                    "first — the studio offers both."
                )
        entries.pop(victim_at)

    if len(entries) > ENTRY_CAPACITY:
        raise ValidationError(
            f"Record {record.record_index} overflowed its {ENTRY_CAPACITY} entry slots"
        )
    _check_tag_rule(record.record_index, before, entries)
    return tuple(entries)


def compile_book(
    book: SplbBook, changes: Iterable[MembershipChange | TagMove]
) -> CompiledBook:
    """Rewrite only the entry prefixes the changes touch."""

    request = _normalize(changes)
    if request.outer_index != book.outer_index:
        raise ValidationError("These changes belong to a different stock playbook")
    replacement = bytearray(book.body)
    applied: list[dict[str, Any]] = []
    off_distribution: list[int] = []

    for record_index in sorted(request.record_indices):
        if not 0 <= record_index < RECORD_COUNT:
            raise ValidationError(f"Record {record_index} is outside this book")
        record = book.records[record_index]
        memberships = tuple(
            change
            for change in request.memberships
            if change.record_index == record_index
        )
        moves = tuple(
            move for move in request.moves if move.record_index == record_index
        )
        entries = apply_record_changes(book, record, memberships, moves)
        if not retail_tag_shape(entries):
            off_distribution.append(record_index)
        present = {entry.play_index for entry in record.entries}
        for change in memberships:
            if change.member == (change.play_index in present):
                continue    # asked for what the record already said
            applied.append(
                {
                    "kind": "membership",
                    "selector": change.selector,
                    "record_index": record_index,
                    "formation_index": record.formation_index,
                    "play_index": change.play_index,
                    "member_after": change.member,
                    "tag_heir": change.tag_heir,
                }
            )
        for move in moves:
            applied.append(
                {
                    "kind": "tag_move",
                    "selector": move.selector,
                    "record_index": record_index,
                    "formation_index": record.formation_index,
                    "from_play": move.from_play,
                    "to_play": move.to_play,
                }
            )
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
        # Every retail record's tag set is a prefix of 1, 0, 2, 3. An edit can
        # leave a legal set that is still not one retail uses; say so rather than
        # quietly refusing or quietly shipping it.
        "records_outside_retail_tag_sets": off_distribution,
        "claims": {
            "entry_prefix_only": True,
            "trailers_untouched": True,
            "unmapped_tail_untouched": True,
            "resource_length_unchanged": True,
            "tag_count_rule_held": True,
            "tag_meaning_proved": False,
            "cpu_behaviour_runtime_proved": False,
        },
    }
    return CompiledBook(book.outer_index, b"", bytes(replacement), report)


def verify_book(
    before: bytes, after: bytes, changes: Iterable[MembershipChange | TagMove]
) -> Mapping[str, Any]:
    """Re-derive every changed byte without trusting the compiler.

    Every difference must fall inside the 168-byte entry region of a record a
    change named. A trailer byte, either unmapped tail region, or any other
    record fails here rather than in someone's game. The tagged-slot rule is
    re-derived from the output bytes too, so a compiler that lost or duplicated
    a slot cannot ship it.
    """

    request = _normalize(changes)
    if len(before) != len(after):
        raise ValidationError("Stock-playbook verification: resource length changed")
    touched = request.record_indices
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
    parsed_before = parse_book(before, request.outer_index)
    parsed_after = parse_book(after, request.outer_index)
    for change in request.memberships:
        record = parsed_after.records[change.record_index]
        present = any(e.play_index == change.play_index for e in record.entries)
        if present != change.member:
            raise ValidationError(
                "Stock-playbook verification: the reparsed book disagrees with the "
                f"request for record {change.record_index} play {change.play_index}"
            )
        if change.tag_heir is None:
            continue
        was = next(
            e.y
            for e in parsed_before.records[change.record_index].entries
            if e.play_index == change.play_index
        )
        heir = next(
            (e for e in record.entries if e.play_index == change.tag_heir), None
        )
        if heir is None or heir.y != was:
            raise ValidationError(
                f"Stock-playbook verification: play {change.tag_heir} did not inherit "
                f"tagged slot {was} in record {change.record_index}"
            )
    for move in request.moves:
        source = parsed_before.records[move.record_index]
        target = parsed_after.records[move.record_index]
        was = {e.play_index: e.y for e in source.entries}
        now = {e.play_index: e.y for e in target.entries}
        if now.get(move.to_play) != was.get(move.from_play) or now.get(
            move.from_play
        ) != was.get(move.to_play):
            raise ValidationError(
                "Stock-playbook verification: the reparsed book does not show tagged "
                f"slot {was.get(move.from_play)} moved from play {move.from_play} to "
                f"{move.to_play} in record {move.record_index}"
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
        if index in touched:
            _check_tag_rule(index, a.entries, list(b.entries))
    return {
        "schema": REPORT_SCHEMA,
        "changed_byte_count": len(differing),
        "changed_records": sorted(touched),
        "tag_rule_reverified": True,
        "independent_reparse": True,
    }


def build_book_patch(
    index_path: Path, changes: Iterable[MembershipChange | TagMove]
) -> CompiledBook:
    """Compile changes into a rebuilt outer entry without touching the source."""

    normalized = tuple(changes)
    outer_index = _normalize(normalized).outer_index
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
    "MAX_TAGS",
    "PAYLOAD_SCHEMA",
    "PROVIDER_KIND",
    "RECORD_BASE",
    "RECORD_COUNT",
    "RECORD_STRIDE",
    "REPORT_SCHEMA",
    "STOCK_BOOKS",
    "TAG_PRIORITY",
    "CompiledBook",
    "MembershipChange",
    "SplbBook",
    "SplbEntry",
    "SplbRecord",
    "TagMove",
    "apply_record_changes",
    "build_book_patch",
    "compile_book",
    "entry_selector",
    "follows_tag_rule",
    "parse_book",
    "read_book",
    "required_tag_count",
    "retail_tag_shape",
    "tag_selector",
    "tags_of",
    "verify_book",
]
