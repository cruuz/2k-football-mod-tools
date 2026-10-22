"""Lossless APF MASTER PLAY codec. See docs/research/apf_play_format.md.

The NFL operand vocabulary is useful, but its flags, descriptors, validator and
opcode 1C are NOT APF's. Unknown bits survive inspection. Authoring is limited
to explicitly supported fields; a round trip is not a gameplay validation.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct

from .errors import ValidationError
from . import nfl2k5_play_codec as nfl
from .apf2k8_formation_alignment_writer import SlotAlignment
from .apf2k8_playbook_route_writer import _parse

BODY_SIZE = 0x2C750
CATEGORY_BASE, CATEGORY_SIZE = 0x44, 0x10
FORMATION_BASE, FORMATION_SIZE, FORMATION_CAPACITY = 0x244, 0xB8, 176
PLAY_BASE, PLAY_SIZE = 0x80C4, 0x64
# 640 record slots physically fit, but the existing inspector only supports
# 592 bits in the unidentified trailing relation. Do not silently widen it.
PLAY_CAPACITY = 592
NODE_BASE, NODE_SIZE, NODE_CAPACITY = 0x17AC4, 8, 5400
STRING_BASE, STRING_END = 0x22384, 0x28D84
RELATION_BASE, RELATION_STRIDE = 0x28D84, 84
NODE_ALTERNATE, NODE_ACTION, NODE_TERMINAL = 0x80, 0x40, 0x20
NATIVE_ALIGN_MASK = 0xC00F3F3F
MASTER_SHA256 = "2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891"


def bounded(value: object, lo: int, hi: int, label: str) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise ValidationError(f"{label} must be an integer from {lo} through {hi}.")
    return value


def relative_token(field: int, target: int) -> int:
    return bounded(target - field + 1, -(1 << 31), (1 << 31) - 1, "Relative pointer")


def decode_align(packed: int, mirror: bool = False) -> tuple[int, ...]:
    """APF 84A90EC0: mode, two (flag,lane) pairs, selector, reserved zero."""
    a, left, b, right = (packed >> 5) & 1, packed & 31, (packed >> 13) & 1, (packed >> 8) & 31
    if mirror:
        a, left, b, right = b, 17 if right == 17 else 16 - right, a, 17 if left == 17 else 16 - left
    return (packed >> 30, a, left, b, right, (packed >> 16) & 15, 0)


def encode_align(v: tuple) -> int:
    if len(v) != 7 or v[6] != 0:
        raise ValidationError("APF 1C needs six fields and a reserved zero.")
    for value, maximum in zip(v[:6], (3, 1, 31, 1, 31, 15)):
        bounded(value, 0, maximum, "APF 1C operand")
    return v[0] << 30 | v[1] << 5 | v[2] | v[3] << 13 | v[4] << 8 | v[5] << 16


#: Opcodes whose X byte (bits 24..31, integer feet + 128) the engine negates when a play is mirrored.
MIRROR_X_OPS = (0x01, 0x04, 0x09, 0x11, 0x15, 0x18)
#: Opcodes that carry a side-dependent operand this tool does not rewrite (defence, kicking, links).
MIRROR_UNSUPPORTED_OPS = (0x07, 0x08, 0x0A, 0x0D, 0x0E, 0x0F, 0x10, 0x19, 0x1A, 0x1B)


def mirror_chain_edits(chain) -> tuple[list[tuple[int, str, int]], list[str]]:
    """Field edits that turn one assignment into its mirror image, plus notes for what cannot be mirrored.

    Rules are the engine's own (``nfl2k5_play_codec.decode_operands(..., mirror=True)``): X offsets
    negate, a block leg's turn swaps +45/-45, a pass-block segment's distance changes sign, a handoff hole
    h becomes 9-h, rush lanes become 16-lane, and the dual-lane 1C swaps and reflects its two lanes.
    Inside/outside route segments are relative to where the player lines up, so they stay as they are:
    the mirror image of a route belongs to a player on the other side of the formation.

    Returns ``([(node index, field, value), ...], [note, ...])``.  Edits are absolute values for
    ``Node.with_field``; mirroring the result again gives the original back.
    """

    edits: list[tuple[int, str, int]] = []
    notes: list[str] = []
    for index, node in enumerate(chain):
        packed = struct.unpack_from(">I", node.to_bytes(), 4)[0]
        field_bits = lambda lo, width: (packed >> lo) & ((1 << width) - 1)
        op = node.op

        def mirror_x():
            feet = field_bits(24, 8) - 128
            if feet == 0:
                return
            if not -128 <= -feet <= 127:
                notes.append(f"Node {index} ({node.name}): X offset {feet} ft has no mirror in range")
                return
            edits.append((index, "x_ft", -feet))

        if op in MIRROR_X_OPS:
            if op == 0x11:
                if field_bits(0, 5) % 10 != 9:  # leg type 9 uses absolute coordinates
                    mirror_x()
                turn = field_bits(14, 2)
                if turn in (0, 1):
                    edits.append((index, "turn", 1 - turn))
            else:
                mirror_x()
        elif op == 0x12 and field_bits(0, 4) == 9:  # pass block: the distance sign is the side
            distance = field_bits(24, 8) - 64
            if distance:
                if -64 <= -distance <= 191:
                    edits.append((index, "distance_ft", -distance))
                else:
                    notes.append(f"Node {index} ({node.name}): pass-block distance {distance} ft has no mirror in range")
        elif op in (0x16, 0x17):
            hole = field_bits(28, 4)
            if hole:
                edits.append((index, "hole", 9 - hole))
        elif op in (0x0B, 0x0C):
            lane = field_bits(27, 5)
            if lane <= 16 and 16 - lane != lane:
                edits.append((index, "lane", 16 - lane))
        elif op == 0x1C:
            before, after = decode_align(packed), decode_align(packed, mirror=True)
            for name, position in (("first_flag", 1), ("first_lane", 2), ("second_flag", 3), ("second_lane", 4)):
                if before[position] != after[position]:
                    edits.append((index, name, after[position]))
        elif op in MIRROR_UNSUPPORTED_OPS:
            notes.append(f"Node {index} ({node.name}): not mirrored by this tool")
    return edits, notes


@dataclass(frozen=True)
class Node:
    op: int
    flags: int
    operands: tuple
    opaque_bits: int = 0
    reserved: int = 0

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Node":
        if len(raw) != 8:
            raise ValidationError("An APF node must contain eight bytes.")
        op, flags, reserved, packed = struct.unpack(">BBHI", raw)
        if not 0 <= op < 29:
            raise ValidationError(f"Unsupported APF opcode {op}.")
        operands = decode_align(packed) if op == 0x1C else tuple(nfl.decode_operands(op, packed))
        encoded = encode_align(operands) if op == 0x1C else nfl.encode_operands(op, operands)
        if encoded & ~packed:
            raise ValidationError("Operand decode changed a represented bit.")
        return cls(op, flags, operands, packed & ~encoded, reserved)

    def to_bytes(self) -> bytes:
        packed = encode_align(self.operands) if self.op == 0x1C else nfl.encode_operands(self.op, self.operands)
        return struct.pack(">BBHI", self.op, self.flags, self.reserved, packed | self.opaque_bits)

    @property
    def name(self) -> str:
        return {0x06: "Pass / first read (APF)", 0x1C: "Dual lane assignment (APF)"}.get(self.op, nfl.OPCODE_NAMES[self.op])

    def with_field(self, field: str, value: int) -> "Node":
        """Patch one proved numeric field, preserving every other operand bit.

        Coordinates are integer feet, not floats; no wrapping or clamping.
        The 06 read selector is intentionally never named 'drop'.
        """
        specifications = {
            (0x04, "x_ft"): (24, 8, -128, 127, 128),
            (0x04, "y_ft"): (16, 8, -64, 191, 64),
            (0x12, "distance_ft"): (24, 8, -64, 191, 64),
            (0x12, "segment_type"): (0, 4, 0, 14, 0),
            (0x0D, "x_ft"): (24, 8, -128, 127, 128),
            (0x0D, "y_ft"): (16, 8, -64, 191, 64),
            (0x0E, "cushion_ft"): (4, 8, -64, 191, 64),
            (0x06, "first_read"): (4, 4, 1, 5, 0),
        }
        for op in (0x0B, 0x0C):
            specifications[op, "lane"] = (27, 5, 0, 17, 0)
        # Fake/take handoff pairs (QB 0x13 "Handoff To" / 0x14 "Fake Handoff To", HB 0x16 "Take Handoff" /
        # 0x17 "Fake Take Handoff"; layouts from nfl2k5_play_codec.decode_operands).  K selects the fake
        # style (retail uses 0,1,2,5,7,8); A is the take-handoff variant bit; the hole is 0..8 and the
        # engine mirrors it as 9 - hole.  Only retail-observed meaning is documented here.
        for op in (0x13, 0x14):
            specifications[op, "slot"] = (0, 4, 0, 10, 0)
            specifications[op, "k"] = (4, 4, 0, 15, 0)
        for op in (0x16, 0x17):
            specifications[op, "a"] = (0, 4, 0, 15, 0)
            specifications[op, "hole"] = (28, 4, 0, 8, 0)
        for op in MIRROR_X_OPS:
            specifications.setdefault((op, "x_ft"), (24, 8, -128, 127, 128))
        # Block leg: the turn (0 = +45 deg, 1 = -45 deg, 2 = none) and offsets.  Leg type 9 stores raw
        # coordinates instead of feet, so its offsets are not editable here.
        specifications[0x11, "turn"] = (14, 2, 0, 2, 0)
        specifications[0x11, "x_ft"] = (24, 8, -128, 127, 128)
        specifications[0x11, "y_ft"] = (16, 8, -64, 191, 64)
        specifications[0x12, "flag"] = (4, 1, 0, 1, 0)
        specifications[0x12, "k"] = (20, 4, 0, 15, 0)
        for name, shift, width, maximum in (
            ("mode", 30, 2, 3), ("first_flag", 5, 1, 1),
            ("first_lane", 0, 5, 17), ("second_flag", 13, 1, 1),
            ("second_lane", 8, 5, 17), ("selector", 16, 4, 15),
        ):
            specifications[0x1C, name] = (shift, width, 0, maximum, 0)
        spec = specifications.get((self.op, field))
        if spec is None:
            raise ValidationError(f"Field {field!r} is not writable on opcode {self.op:#x}.")
        if self.op == 0x11 and field in ("x_ft", "y_ft") and self.operands[0] == 9:
            raise ValidationError("Block leg type 9 stores raw coordinates; its offsets are not editable.")
        shift, width, lo, hi, bias = spec
        bounded(value, lo, hi, field)
        raw = self.to_bytes()
        packed = struct.unpack_from(">I", raw, 4)[0]
        packed = (packed & ~(((1 << width) - 1) << shift)) | ((value + bias) << shift)
        return Node.from_bytes(raw[:4] + struct.pack(">I", packed))


@dataclass(frozen=True)
class Assignment:
    descriptor: int
    pointer: int

    @property
    def count(self) -> int:
        return self.descriptor >> 28

    def start(self, pointer_field: int) -> int:
        target = pointer_field - 1 + self.pointer
        if (target - NODE_BASE) % 8:
            raise ValidationError("APF assignment pointer is not node aligned.")
        return (target - NODE_BASE) // 8


@dataclass(frozen=True)
class PlayRecord:
    name_pointer: int
    flags: int
    features: int
    assignments: tuple[Assignment, ...]

    @classmethod
    def from_bytes(cls, raw: bytes) -> "PlayRecord":
        if len(raw) != PLAY_SIZE:
            raise ValidationError("APF play record size changed.")
        p, flags, features = struct.unpack_from(">iII", raw)
        return cls(p, flags, features, tuple(Assignment(*struct.unpack_from(">Ii", raw, 12 + s * 8)) for s in range(11)))

    def to_bytes(self) -> bytes:
        return struct.pack(">iII", self.name_pointer, self.flags, self.features) + b"".join(struct.pack(">Ii", a.descriptor, a.pointer) for a in self.assignments)

    @property
    def type_nibble(self) -> int:
        return self.flags >> 28


@dataclass(frozen=True)
class FormationRecord:
    name_pointer: int
    flags: int
    extra: int
    eligible_order: tuple[int, ...]
    slot_order: tuple[int, ...]
    reserved: int
    slots: tuple[SlotAlignment, ...]

    @classmethod
    def from_bytes(cls, raw: bytes) -> "FormationRecord":
        if len(raw) != FORMATION_SIZE:
            raise ValidationError("APF formation record size changed.")
        return cls(*struct.unpack_from(">iII", raw), tuple(raw[12:17]), tuple(raw[17:28]), struct.unpack_from(">H", raw, 28)[0], tuple(SlotAlignment.from_bytes(raw[30 + s * 14:44 + s * 14]) for s in range(11)))

    def to_bytes(self) -> bytes:
        return struct.pack(">iII", self.name_pointer, self.flags, self.extra) + bytes(self.eligible_order) + bytes(self.slot_order) + struct.pack(">H", self.reserved) + b"".join(s.to_bytes() for s in self.slots)

    @property
    def category_index(self) -> int:
        return (self.flags >> 18) & 63


@dataclass(frozen=True)
class Book:
    header: bytes
    book_name_pointer: int
    categories: tuple[tuple[int, bytes], ...]
    formations: tuple[FormationRecord, ...]
    plays: tuple[PlayRecord, ...]
    nodes: tuple[Node, ...]
    names: tuple[tuple[int, str], ...]
    opaque_relation: bytes

    @classmethod
    def from_bytes(cls, body: bytes) -> "Book":
        parsed = _parse(body)
        counts = parsed["root_counts"]
        book = cls(body[:48], struct.unpack_from(">i", body, 48)[0],
            tuple((struct.unpack_from(">i", body, CATEGORY_BASE + i * 16)[0], body[CATEGORY_BASE + i * 16 + 4:CATEGORY_BASE + (i + 1) * 16]) for i in range(counts["category_count"])),
            tuple(FormationRecord.from_bytes(body[FORMATION_BASE + i * FORMATION_SIZE:FORMATION_BASE + (i + 1) * FORMATION_SIZE]) for i in range(counts["formation_count"])),
            tuple(PlayRecord.from_bytes(body[PLAY_BASE + i * PLAY_SIZE:PLAY_BASE + (i + 1) * PLAY_SIZE]) for i in range(counts["play_count"])),
            tuple(Node.from_bytes(body[NODE_BASE + i * 8:NODE_BASE + (i + 1) * 8]) for i in range(counts["route_node_count"])),
            tuple((n["offset"], n["text"]) for n in parsed["name_pool"]), body[RELATION_BASE:])
        for pi, play in enumerate(book.plays):
            for si, assignment in enumerate(play.assignments):
                start = assignment.start(PLAY_BASE + pi * PLAY_SIZE + 16 + si * 8)
                if not 1 <= assignment.count <= 15 or not 0 <= start < start + assignment.count <= len(book.nodes):
                    raise ValidationError(f"Play {pi} slot {si} exceeds its declared node pool.")
        if book.to_bytes() != body:
            raise ValidationError("APF codec did not reproduce the complete source body.")
        return book

    def to_bytes(self) -> bytes:
        body = bytearray(BODY_SIZE)
        body[:48] = self.header
        struct.pack_into(">i4I", body, 48, self.book_name_pointer, len(self.formations), len(self.plays), len(self.categories), len(self.nodes))
        for i, (pointer, payload) in enumerate(self.categories):
            body[CATEGORY_BASE + i * 16:CATEGORY_BASE + (i + 1) * 16] = struct.pack(">i", pointer) + payload
        for base, stride, records in ((FORMATION_BASE, FORMATION_SIZE, self.formations), (PLAY_BASE, PLAY_SIZE, self.plays), (NODE_BASE, 8, self.nodes)):
            for i, record in enumerate(records):
                body[base + i * stride:base + (i + 1) * stride] = record.to_bytes()
        for offset, name in self.names:
            encoded = name.encode("utf-16be") + b"\0\0"
            body[offset:offset + len(encoded)] = encoded
        body[RELATION_BASE:] = self.opaque_relation
        return bytes(body)

    def name_at(self, field: int, pointer: int) -> str:
        return dict(self.names)[field - 1 + pointer]

    def play_name(self, index: int) -> str:
        return self.name_at(PLAY_BASE + index * PLAY_SIZE, self.plays[index].name_pointer)

    def formation_name(self, index: int) -> str:
        return self.name_at(FORMATION_BASE + index * FORMATION_SIZE, self.formations[index].name_pointer)

    def chain(self, play: int, slot: int) -> tuple[Node, ...]:
        assignment = self.plays[play].assignments[slot]
        start = assignment.start(PLAY_BASE + play * PLAY_SIZE + 16 + slot * 8)
        return self.nodes[start:start + assignment.count]

    def references(self, node: int) -> tuple[tuple[int, int], ...]:
        refs = []
        for pi, play in enumerate(self.plays):
            for si, assignment in enumerate(play.assignments):
                start = assignment.start(PLAY_BASE + pi * PLAY_SIZE + 16 + si * 8)
                if start <= node < start + assignment.count:
                    refs.append((pi, si))
        return tuple(refs)
