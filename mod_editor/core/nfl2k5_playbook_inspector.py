"""Private-cache PLAY parser for the 2K5 Mod Studio playbook inspector.

The product release contains this parser and structural constants only.  The
37 stock playbooks, their names, descriptors, and route/action bytes are read
from the user's indexed XISO at runtime and are never bundled with the app or
stored in a shareable project.

This is deliberately an inspector, not a compiler.  Formation membership,
eleven assignment pointers, complete node-chain extents, and broad play-family
bits are exact.  Coordinate axes, player roles, opcode actions, and custom-play
save ownership remain unknown, so mutation is not exposed here.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Iterable

from .errors import ValidationError
from .nfl2k5_universal_asset_index import (
    Nfl2k5UniversalAssetIndex,
    UniversalAssetRecord,
)


try:
    # nfl_outer is placed on sys.path by nfl2k5_universal_asset_index.
    from nfl_outer import FormatError, read_entry_range
except ImportError as exc:  # pragma: no cover - installation failure boundary
    raise RuntimeError("The NFL archive reader is unavailable") from exc


RESOURCE_HEADER_SIZE = 0x20
BODY_SIZE = 0x13390
FORMATION_BASE = 0x0134
FORMATION_SIZE = 0x00B4
FORMATION_CAPACITY = 50
FORMATION_AUX_BASE = 0x245C
FORMATION_AUX_SIZE = 0x0050
FORMATION_PLAY_LINKS = 36
PLAY_BASE = 0x33FC
PLAY_SIZE = 0x0060
PLAY_CAPACITY = 270
CATEGORY_BASE = 0x993C
CATEGORY_SIZE = 0x0010
CATEGORY_CAPACITY = 26
NODE_BASE = 0x9ADC
NODE_SIZE = 8
STRING_BASE = 0x10840
ASSIGNMENT_COUNT = 11


PLAY_FAMILY_LABELS: tuple[str, ...] = (
    "Offense",
    "Defense",
    "Punt",
    "Punt return / defense",
    "Field goal",
    "Field-goal defense",
    "Kickoff",
    "Kickoff return",
)


@dataclass(frozen=True)
class PlaybookNode:
    """One still-opaque eight-byte assignment/action node."""

    index: int
    opcode: int
    flags: int
    operands_hex: str
    raw_hex: str

    @property
    def ends_chain(self) -> bool:
        """Corpus-proved candidate terminal marker (flags bit 1)."""

        return bool(self.flags & 0x02)


@dataclass(frozen=True)
class PlaybookChain:
    """An exact node extent inferred from all declared assignment starts."""

    start_index: int
    end_index: int
    nodes: tuple[PlaybookNode, ...]

    @property
    def node_count(self) -> int:
        return self.end_index - self.start_index


@dataclass(frozen=True)
class PlaybookAssignment:
    slot_index: int
    descriptor_word: int
    chain_start_index: int

    @property
    def declared_length(self) -> int:
        """Runtime reader 0x1A8C00 uses only the descriptor's low nibble."""
        return self.descriptor_word & 0xF


@dataclass(frozen=True)
class PlaybookPlay:
    index: int
    name: str
    flags_or_id: int
    family_id: int
    family_label: str
    assignments: tuple[PlaybookAssignment, ...]


@dataclass(frozen=True)
class FormationPlayLink:
    """One of the 36 fixed formation-menu references."""

    link_index: int
    play_index: int
    group: int
    packed_value: int


# Formation package role map — 11-byte permutation of 0..10 at formation+0x0D
# (o0308 G1 census: Nickel vs Dime differ here; see playbook_package_rule_spike).
PACKAGE_MAP_OFFSET_IN_FORMATION = 0x0D
PACKAGE_MAP_SIZE = 11


@dataclass(frozen=True)
class PlaybookFormation:
    index: int
    name: str
    play_links: tuple[FormationPlayLink, ...]
    # role-id order for the 11 assignment slots (body FORMATION+0x0D); empty if unknown
    package_map: tuple[int, ...] = ()


@dataclass(frozen=True)
class PlaybookCategory:
    index: int
    name: str


@dataclass(frozen=True)
class Nfl2k5Playbook:
    """One private, read-only NFL 2K5 PLAY resource."""

    asset_id: str
    outer_index: int
    book_name: str
    formations: tuple[PlaybookFormation, ...]
    plays: tuple[PlaybookPlay, ...]
    categories: tuple[PlaybookCategory, ...]
    chains: tuple[PlaybookChain, ...]
    node_count: int

    def chain(self, start_index: int) -> PlaybookChain:
        for chain in self.chains:
            if chain.start_index == start_index:
                return chain
        raise ValidationError(
            f"Playbook {self.book_name} has no chain beginning at node {start_index}."
        )

    def assignment_chain(self, assignment: PlaybookAssignment) -> PlaybookChain:
        """The runtime span, excluding orphan nodes in an inferred extent."""
        start = assignment.chain_start_index
        end = start + assignment.declared_length
        if not assignment.declared_length or end > self.node_count:
            raise ValidationError("PLAY assignment has an invalid declared length.")
        nodes = tuple(node for chain in self.chains
                      if chain.end_index > start and chain.start_index < end
                      for node in chain.nodes if start <= node.index < end)
        if len(nodes) != assignment.declared_length:
            raise ValidationError("PLAY assignment has a truncated declared chain.")
        return PlaybookChain(start, end, nodes)

    def plays_for_formation(
        self, formation: PlaybookFormation | int
    ) -> tuple[PlaybookPlay, ...]:
        index = formation if isinstance(formation, int) else formation.index
        if not 0 <= index < len(self.formations):
            raise ValidationError(
                f"Playbook {self.book_name} has no formation {index}."
            )
        return tuple(
            self.plays[link.play_index]
            for link in self.formations[index].play_links
        )


def _u32(data: bytes, offset: int, label: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ValidationError(f"PLAY {label} lies outside the resource body.")
    return struct.unpack_from("<I", data, offset)[0]


def _relative(data: bytes, field: int, label: str) -> int:
    raw = _u32(data, field, label)
    signed = raw if raw < 0x80000000 else raw - 0x100000000
    target = field - 1 + signed
    if not 0 <= target < len(data):
        raise ValidationError(
            f"PLAY {label} resolves outside the resource body (0x{target:x})."
        )
    return target


def _utf16le(data: bytes, offset: int, label: str) -> str:
    if offset < STRING_BASE or offset & 1:
        raise ValidationError(f"PLAY {label} has an invalid string pointer.")
    cursor = offset
    while cursor + 2 <= len(data):
        if data[cursor:cursor + 2] == b"\0\0":
            try:
                value = data[offset:cursor].decode("utf-16le")
            except UnicodeDecodeError as exc:
                raise ValidationError(f"PLAY {label} is not valid text.") from exc
            if not value:
                raise ValidationError(f"PLAY {label} is empty.")
            return value
        cursor += 2
    raise ValidationError(f"PLAY {label} is not terminated.")


def _name(data: bytes, pointer_field: int, label: str) -> str:
    return _utf16le(data, _relative(data, pointer_field, label), label)


def _require_count(value: int, maximum: int, label: str) -> int:
    if not 1 <= value <= maximum:
        raise ValidationError(
            f"PLAY declares {value} {label}; supported range is 1–{maximum}."
        )
    return value


def _parse_body(
    body: bytes, *, asset_id: str, outer_index: int
) -> Nfl2k5Playbook:
    if len(body) != BODY_SIZE:
        raise ValidationError(
            f"PLAY body is {len(body):,} bytes; {BODY_SIZE:,} were expected."
        )
    if body[0x0C:0x10] != b"PLAY" or body[0x20:0x28] != b"p\0l\0b\0\0\0":
        raise ValidationError("That resource is not a recognized NFL 2K5 playbook.")

    formation_count = _require_count(
        _u32(body, 0x34, "formation count"), FORMATION_CAPACITY, "formations"
    )
    play_count = _require_count(
        _u32(body, 0x38, "play count"), PLAY_CAPACITY, "plays"
    )
    category_count = _require_count(
        _u32(body, 0x3C, "category count"), CATEGORY_CAPACITY, "categories"
    )
    node_capacity = (STRING_BASE - NODE_BASE) // NODE_SIZE
    node_count = _require_count(
        _u32(body, 0x40, "node count"), node_capacity, "nodes"
    )
    expected_targets = (
        (0x44, FORMATION_BASE, "formation table"),
        (0x48, FORMATION_AUX_BASE, "formation-link table"),
        (0x60, PLAY_BASE, "play table"),
        (0x64, CATEGORY_BASE, "category table"),
        (0x68, NODE_BASE, "node table"),
    )
    for field, expected, label in expected_targets:
        actual = _relative(body, field, label)
        if actual != expected:
            raise ValidationError(
                f"PLAY {label} begins at 0x{actual:x}; 0x{expected:x} was expected."
            )

    book_name = _name(body, 0x30, "book name")
    play_rows: list[PlaybookPlay] = []
    chain_starts: set[int] = set()
    for play_index in range(play_count):
        offset = PLAY_BASE + play_index * PLAY_SIZE
        play_name = _name(body, offset, f"play {play_index} name")
        flags_or_id = _u32(body, offset + 4, f"play {play_index} flags")
        family_id = (flags_or_id >> 6) & 0x7
        assignments: list[PlaybookAssignment] = []
        for slot_index in range(ASSIGNMENT_COUNT):
            descriptor_field = offset + 8 + slot_index * 8
            pointer_field = offset + 0x0C + slot_index * 8
            descriptor = _u32(
                body, descriptor_field,
                f"play {play_index} assignment {slot_index} descriptor",
            )
            target = _relative(
                body, pointer_field,
                f"play {play_index} assignment {slot_index} node pointer",
            )
            if not NODE_BASE <= target < NODE_BASE + node_count * NODE_SIZE \
                    or (target - NODE_BASE) % NODE_SIZE:
                raise ValidationError(
                    f"PLAY assignment points outside its declared node table: "
                    f"play {play_index}, slot {slot_index}."
                )
            start = (target - NODE_BASE) // NODE_SIZE
            count = descriptor & 0xF
            if not count or start + count > node_count:
                raise ValidationError(
                    f"PLAY assignment has an invalid declared length: "
                    f"play {play_index}, slot {slot_index}."
                )
            chain_starts.add(start)
            assignments.append(PlaybookAssignment(slot_index, descriptor, start))
        play_rows.append(PlaybookPlay(
            play_index,
            play_name,
            flags_or_id,
            family_id,
            PLAY_FAMILY_LABELS[family_id],
            tuple(assignments),
        ))

    if not chain_starts or min(chain_starts) != 0:
        raise ValidationError("PLAY node chains do not begin at node zero.")
    ordered_starts = sorted(chain_starts)
    node_rows: list[PlaybookNode] = []
    for node_index in range(node_count):
        offset = NODE_BASE + node_index * NODE_SIZE
        raw = body[offset:offset + NODE_SIZE]
        node_rows.append(PlaybookNode(
            node_index, raw[0], raw[1], raw[2:].hex(), raw.hex()
        ))
    chains: list[PlaybookChain] = []
    for chain_index, start in enumerate(ordered_starts):
        end = (
            ordered_starts[chain_index + 1]
            if chain_index + 1 < len(ordered_starts) else node_count
        )
        if end <= start:
            raise ValidationError("PLAY contains an empty or overlapping node chain.")
        nodes = tuple(node_rows[start:end])
        if nodes[0].flags & 0x07:
            raise ValidationError(
                f"PLAY chain {start} has unsupported start flags 0x{nodes[0].flags:02x}."
            )
        if not nodes[-1].ends_chain:
            raise ValidationError(
                f"PLAY chain {start} has no recognized terminal marker."
            )
        chains.append(PlaybookChain(start, end, nodes))

    formation_rows: list[PlaybookFormation] = []
    for formation_index in range(formation_count):
        offset = FORMATION_BASE + formation_index * FORMATION_SIZE
        formation_name = _name(
            body, offset, f"formation {formation_index} name"
        )
        aux = FORMATION_AUX_BASE + formation_index * FORMATION_AUX_SIZE
        links: list[FormationPlayLink] = []
        for link_index in range(FORMATION_PLAY_LINKS):
            packed = struct.unpack_from("<H", body, aux + link_index * 2)[0]
            play_index = packed & 0x01FF
            if play_index == 0x01FF:
                continue
            if play_index >= play_count:
                raise ValidationError(
                    f"PLAY formation {formation_index} references missing play "
                    f"{play_index}."
                )
            links.append(FormationPlayLink(
                link_index, play_index, (packed >> 9) & 0x3, packed
            ))
        map_off = offset + PACKAGE_MAP_OFFSET_IN_FORMATION
        package_map = tuple(body[map_off : map_off + PACKAGE_MAP_SIZE])
        if len(package_map) != PACKAGE_MAP_SIZE:
            raise ValidationError(
                f"PLAY formation {formation_index} package map is truncated."
            )
        formation_rows.append(PlaybookFormation(
            formation_index, formation_name, tuple(links), package_map
        ))

    categories = tuple(
        PlaybookCategory(
            index,
            _name(
                body,
                CATEGORY_BASE + index * CATEGORY_SIZE,
                f"category {index} name",
            ),
        )
        for index in range(category_count)
    )
    return Nfl2k5Playbook(
        asset_id=asset_id,
        outer_index=outer_index,
        book_name=book_name,
        formations=tuple(formation_rows),
        plays=tuple(play_rows),
        categories=categories,
        chains=tuple(chains),
        node_count=node_count,
    )


def parse_playbook_resource(
    raw: bytes, *, asset_id: str = "private.PLAY", outer_index: int = -1
) -> Nfl2k5Playbook:
    """Parse one exact 0x20-byte resource wrapper plus fixed PLAY body."""

    if len(raw) != RESOURCE_HEADER_SIZE + BODY_SIZE:
        raise ValidationError(
            f"PLAY resource is {len(raw):,} bytes; "
            f"{RESOURCE_HEADER_SIZE + BODY_SIZE:,} were expected."
        )
    if raw[:4] != b"PLAY" or _u32(raw, 4, "stored size") != BODY_SIZE:
        raise ValidationError("That indexed resource is not a fixed NFL 2K5 PLAY body.")
    return _parse_body(raw[RESOURCE_HEADER_SIZE:], asset_id=asset_id,
                       outer_index=outer_index)


def _read_indexed_resource(
    index: Nfl2k5UniversalAssetIndex, record: UniversalAssetRecord
) -> bytes:
    canonical = index.get(record.asset_id)
    if canonical != record or record.kind != "PLAY":
        raise ValidationError("That row does not match the private PLAY index.")
    if not 0 <= record.outer_index < len(index.archive.entries):
        raise ValidationError("A PLAY row names an unknown outer archive entry.")
    entry = index.archive.entries[record.outer_index]
    if (
        entry.size != record.outer_size
        or f"0x{entry.name_id:08x}" != record.outer_id
        or entry.head_ascii != record.outer_head
    ):
        raise ValidationError("The private archive no longer matches its PLAY index.")
    try:
        raw = read_entry_range(
            index.archive, entry, record.chunk_offset, record.raw_size
        )
    except (OSError, FormatError) as exc:
        raise ValidationError(f"Could not read that private playbook: {exc}") from exc
    if len(raw) != record.raw_size:
        raise ValidationError("The private archive returned a short PLAY resource.")
    return raw


class Nfl2k5PlaybookInspector:
    """Lazy, read-only product service backed by the universal private index."""

    def __init__(self, index: Nfl2k5UniversalAssetIndex) -> None:
        self.index = index
        rows = index.query(kind="PLAY", limit=2000)
        if len(rows) != 37:
            raise ValidationError(
                f"The supported XISO should contain 37 playbooks; {len(rows)} were found."
            )
        self._records = rows
        self._cache: dict[str, Nfl2k5Playbook] = {}

    @property
    def count(self) -> int:
        return len(self._records)

    def records(self) -> tuple[UniversalAssetRecord, ...]:
        return self._records

    def load(self, asset_or_id: UniversalAssetRecord | str) -> Nfl2k5Playbook:
        asset_id = (
            asset_or_id.asset_id
            if isinstance(asset_or_id, UniversalAssetRecord) else asset_or_id
        )
        cached = self._cache.get(asset_id)
        if cached is not None:
            return cached
        record = next(
            (row for row in self._records if row.asset_id == asset_id), None
        )
        if record is None:
            raise ValidationError(f"Unknown indexed playbook: {asset_id}")
        result = parse_playbook_resource(
            _read_indexed_resource(self.index, record),
            asset_id=record.asset_id,
            outer_index=record.outer_index,
        )
        self._cache[asset_id] = result
        return result

    def load_all(self) -> tuple[Nfl2k5Playbook, ...]:
        return tuple(self.load(record) for record in self._records)

    def search(self, query: str) -> tuple[Nfl2k5Playbook, ...]:
        words = tuple(word for word in query.casefold().split() if word)
        books = self.load_all()
        if not words:
            return books
        result: list[Nfl2k5Playbook] = []
        for book in books:
            haystack = " ".join((
                book.book_name,
                *(row.name for row in book.formations),
                *(row.name for row in book.plays),
                *(row.name for row in book.categories),
            )).casefold()
            if all(word in haystack for word in words):
                result.append(book)
        return tuple(result)


def corpus_counts(books: Iterable[Nfl2k5Playbook]) -> dict[str, int]:
    rows = tuple(books)
    return {
        "books": len(rows),
        "formations": sum(len(row.formations) for row in rows),
        "plays": sum(len(row.plays) for row in rows),
        "categories": sum(len(row.categories) for row in rows),
        "chains": sum(len(row.chains) for row in rows),
        "nodes": sum(row.node_count for row in rows),
        "slot_references": sum(
            len(play.assignments) for row in rows for play in row.plays
        ),
    }


__all__ = [
    "FormationPlayLink",
    "Nfl2k5Playbook",
    "Nfl2k5PlaybookInspector",
    "PLAY_FAMILY_LABELS",
    "PlaybookAssignment",
    "PlaybookCategory",
    "PlaybookChain",
    "PlaybookFormation",
    "PlaybookNode",
    "PlaybookPlay",
    "corpus_counts",
    "parse_playbook_resource",
]
