"""NFL 2K5 PLAY codec: formation slots, assignment nodes, descriptors, validator.

Everything here is a port of the retail default.xbe consumers (reverse-engineered
2026-09-02 from the XBE; addresses are Xbox virtual addresses):

* opcode table ``0x521078`` (29 entries x 0x14: flags, decode, encode, draw,
  validate callbacks) -> :data:`OPCODE_FLAGS`, :func:`decode_operands`,
  :func:`encode_operands`;
* formation reader ``FUN_0017fe60``: per-slot 14-byte records at ``+0x1A``
  holding three x and three depth columns in centimetres plus a mirror-partner
  nibble -> :class:`FormationRecord`;
* play validator ``FUN_001a9840`` / ``FUN_001a91a0`` / ``FUN_001a96b0`` /
  ``FUN_001a8fb0`` -> :func:`validate_play`.  The port accepts all 9,251 stock
  plays and mirrors every refusal path, so a play it accepts is one the game
  marks callable (play flag bit 31) at load.

Units: node coordinates are stored as 1-foot integers with a bias; formation
coordinates are signed centimetres (91.44 cm = 1 yard).  X is lateral (positive
= offense's right), Y/Z is along the field (positive = downfield for offense).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

FT_CM = 30.48
YD_CM = 91.44
NODE_SIZE = 8
SLOT_COUNT = 11
FORMATION_SLOT_BASE = 0x1A
FORMATION_SLOT_STRIDE = 14
FORMATION_FLAG_HAS_MIRROR = 0x100000
FORMATION_FLAG_UNDER_CENTER = 0x40000
FORMATION_FLAG_SHOTGUN = 0x80000
FORMATION_FLAG_QB_MASK = 0xC0000
SHOTGUN_DEPTH_THRESHOLD_CM = -250
NO_MIRROR = 0xB

# Opcode table entry flags (retail 0x521078, +0 of each 0x14 entry).
OPCODE_FLAGS: tuple[int, ...] = (
    0x200F, 0x000F, 0x08C5, 0x1805, 0x3081, 0x20C4, 0x20C1, 0x20C4, 0x2044,
    0x2348, 0x2004, 0x2002, 0x2008, 0x210A, 0x210A, 0x210A, 0x2008, 0x200D,
    0x2101, 0x20C1, 0x2481, 0x2089, 0x2141, 0x2501, 0x200F, 0x220A, 0x2205,
    0x080A, 0x080A,
)
OPCODE_COUNT = len(OPCODE_FLAGS)

OPCODE_NAMES: dict[int, str] = {
    0x00: "None",
    0x01: "Start",
    0x02: "Snap To",
    0x03: "Ball Action",
    0x04: "Special Move",
    0x05: "Hold For Kick",
    0x06: "Dropback / Pass",
    0x07: "Punt Kick",
    0x08: "Place Kick",
    0x09: "Run To Point",
    0x0A: "Coverage Sprint",
    0x0B: "Rush Lane",
    0x0C: "Rush Lane B",
    0x0D: "Zone Coverage",
    0x0E: "Man Coverage",
    0x0F: "Move",
    0x10: "Rush Direction",
    0x11: "Block Leg",
    0x12: "Route Segment",
    0x13: "Handoff To",
    0x14: "Fake Handoff To",
    0x15: "Follow / Run Path",
    0x16: "Take Handoff",
    0x17: "Fake Take Handoff",
    0x18: "Release Downfield",
    0x19: "(invalid)",
    0x1A: "Motion / Link",
    0x1B: "Defense Start",
    0x1C: "Defense Align",
}

# Lateral lane table (retail 0x520fe8), centimetres, index 0..15; 17 = none.
LANE_TABLE_CM: tuple[float, ...] = (
    -685.8, -533.4, -457.2, -381.0, -304.8, -228.6, -152.4, -76.2, 0.0, 76.2,
    152.4, 228.6, 304.8, 381.0, 457.2, 533.4,
)
LANE_NONE = 17
# Named spot tables (retail 0xaabb30 / 0xaabb3c) used by Block Leg type 9.
NAMED_SPOT_X_FT: tuple[int, ...] = (11, -14, 2, -6, 7, -11, -2, 8, -9, 37, -36, 0)
NAMED_SPOT_Y_FT: tuple[int, ...] = (2, 2, 2, 2, 11, 11, 11, 30, 30, 10, 9, 0)

ROUTE_SEGMENT_TYPES: dict[int, str] = {
    0: "Straight (distance)",
    1: "Straight then 30° break",
    2: "Straight then 45° break (post/corner)",
    3: "Straight then 60° break",
    4: "Lateral in (distance)",
    5: "Lateral out (distance)",
    6: "Straight then 45° opposite break",
    7: "Comeback (2ft back, 4ft in)",
    8: "Chip block (4ft)",
    9: "Pass block (side)",
    10: "Straight then block",
    11: "Comeback (opposite side)",
}
BLOCK_LEG_TYPES: dict[int, str] = {
    0: "Drive to offset (run block)",
    1: "Set to offset (pass block)",
    2: "Pull / trap path",
    3: "Release to offset then block",
    4: "Lead block to offset",
    5: "Move to offset (5)",
    6: "Release (special teams)",
    7: "Return to formation spot",
    8: "Move to absolute point",
    9: "Move to named spot",
}
LEG_TURN: dict[int, str] = {0: "turn +45°", 1: "turn -45°", 2: "no turn", 3: "(3)"}
BALL_ACTIONS: dict[int, str] = {0: "Take snap", 1: "Hold for kick", 2: "Kickoff", 3: "Punt catch"}
START_ROLES: dict[int, str] = {2: "Snapper", 3: "Blocker / receiver", 4: "Ball handler", 6: "Kicker"}

# Category position codes: low 5 bits = kind, high 3 bits = variant (side / depth-chart ordinal).
# Verified against the stock personnel groups (Ace = two kind-8 tight on the line,
# 5 Wide = five kind-9, Nickel/Dime = three/four kind-18): 8 is TE, 9 is WR,
# 14 MLB, 15 OLB, 16 SS, 18 CB.
POSITION_KINDS: dict[int, str] = {
    0: "QB", 1: "P", 2: "K", 3: "H", 4: "KR", 5: "T", 6: "C", 7: "G", 8: "TE",
    9: "WR", 10: "HB", 11: "FB", 12: "DE", 13: "DT", 14: "MLB", 15: "OLB",
    16: "SS", 17: "FS", 18: "CB",
}
OFFENSIVE_LINE_KINDS = frozenset({5, 6, 7})
ELIGIBLE_KINDS = frozenset({0, 8, 9, 10, 11, 1, 2, 3, 4})


def position_label(code: int) -> str:
    kind = code & 0x1F
    variant = code >> 5
    base = POSITION_KINDS.get(kind, f"P{kind}")
    return base if variant == 0 else f"{base}{variant + 1}"


# ---------------------------------------------------------------------------
# Operand codec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OperandSpec:
    key: str
    kind: str          # "int", "x_ft", "y_ft", "time", "lane", "slot", "angle", "yards_signed"
    bits: int
    label: str
    choices: Mapping[int, str] | None = None


def _int(key: str, bits: int, label: str, choices: Mapping[int, str] | None = None) -> OperandSpec:
    return OperandSpec(key, "int", bits, label, choices)


X = OperandSpec("x", "x_ft", 8, "X offset (ft, + = right)")
Y = OperandSpec("y", "y_ft", 8, "Y offset (ft, + = downfield)")
T = OperandSpec("time", "time", 6, "Delay (s)")
LANE = OperandSpec("lane", "lane", 5, "Lane (0-15, 17 = none)")
SLOT = OperandSpec("slot", "slot", 4, "Target slot (0-10)")
ANGLE = OperandSpec("angle", "angle", 5, "Angle (°)")

OPERAND_SCHEMAS: dict[int, tuple[OperandSpec, ...]] = {
    0x00: (),
    0x01: (_int("mode", 2, "Mode"), _int("role", 4, "Role", START_ROLES), _int("k", 2, "Flag"), T, X, Y),
    0x02: (SLOT,),
    0x03: (_int("action", 4, "Ball action", BALL_ACTIONS),),
    0x04: (_int("mode", 2, "Mode"), X, Y, _int("flag", 1, "Flag")),
    0x05: (),
    0x06: (_int("a", 3, "A"), _int("drop", 4, "Drop"), _int("c", 4, "C"), _int("d", 4, "D"), _int("e", 4, "E"), T),
    0x07: (_int("mode", 3, "Mode"), X, Y, ANGLE),
    0x08: (_int("mode", 3, "Mode"), X, Y, ANGLE),
    0x09: (_int("mode", 4, "Mode"), X, Y, _int("k", 3, "K")),
    0x0A: (_int("type", 4, "Type"), X, Y),
    0x0B: (_int("mode", 4, "Mode"), LANE, T),
    0x0C: (_int("mode", 4, "Mode"), LANE, T),
    0x0D: (X, Y, _int("a", 4, "A"), _int("b", 4, "B"), _int("side", 4, "Side"), _int("f", 1, "F"), _int("g", 3, "G")),
    0x0E: (_int("flag", 1, "Flag"), OperandSpec("depth", "y_ft", 8, "Cushion (ft)"), _int("a", 4, "A"), _int("b", 4, "B"), _int("side", 4, "Side"), _int("c", 4, "C"), _int("d", 3, "D"), _int("e", 1, "E")),
    0x0F: (_int("a", 4, "A"), _int("b", 4, "B"), _int("c", 4, "C"), X, Y),
    0x10: (_int("type", 4, "Type"), X, Y),
    0x11: (_int("type", 4, "Leg type", BLOCK_LEG_TYPES), T, _int("f", 1, "Relative"), _int("end", 2, "End style"), _int("turn", 2, "Turn", LEG_TURN), X, Y, _int("group", 2, "Group")),
    0x12: (_int("type", 4, "Segment type", ROUTE_SEGMENT_TYPES), _int("flag", 1, "Flag"), OperandSpec("dist", "y_ft", 8, "Distance (ft)"), _int("k", 4, "K")),
    0x13: (SLOT, _int("k", 4, "K")),
    0x14: (SLOT, _int("k", 4, "K")),
    0x15: (_int("mode", 2, "Mode (2 = follow slot)"), X, Y, _int("a", 2, "A"), _int("b", 4, "B"), _int("slot", 4, "Follow slot"), _int("c", 4, "C")),
    0x16: (_int("a", 4, "A"), T, _int("lane", 4, "Aim lane")),
    0x17: (_int("a", 4, "A"), T, _int("lane", 4, "Aim lane")),
    0x18: (_int("mode", 2, "Mode"), X, Y, _int("a", 2, "A"), _int("b", 4, "B"), _int("c", 4, "C"), _int("d", 4, "D")),
    0x19: (_int("a", 3, "A"), X, Y, _int("b", 4, "B"), _int("c", 3, "C"), _int("d", 1, "D"), _int("e", 4, "E")),
    0x1A: (_int("kind", 3, "Kind"), X, Y, _int("slot", 4, "Slot"), _int("k", 3, "K"), _int("f", 1, "F"), _int("node", 4, "Node"), _int("h", 1, "H")),
    0x1B: (_int("a", 2, "A"), _int("b", 2, "B"), X, Y, LANE, _int("f", 1, "F")),
    0x1C: (_int("a", 2, "A"), LANE, _int("b", 2, "B"), _int("z", 0, "0"), _int("c", 4, "C"), _int("z2", 0, "0")),
}


def _round_half_away(v: float) -> int:
    return int(v + 0.5) if v >= 0 else int(v - 0.5)


def _enc_x(v_cm: float) -> int:
    return (_round_half_away(v_cm / FT_CM) + 0x80) & 0xFF


def _enc_y(v_cm: float) -> int:
    return (_round_half_away(v_cm / FT_CM) + 0x40) & 0xFF


def _dec_x(byte: int, mirror: bool) -> float:
    v = byte - 0x80
    return float(-v if mirror else v) * FT_CM


def _dec_y(byte: int) -> float:
    return float(byte - 0x40) * FT_CM


def _enc_time(seconds: float) -> int:
    return max(0, min(63, _round_half_away(seconds * 10.0)))


def _dec_lane(v: int, mirror: bool) -> int:
    if v == 0x11:
        return LANE_NONE
    return (0x10 - v) if mirror else v


def _enc_lane(v: int) -> int:
    return 0x11 if v == LANE_NONE else v & 0x1F


def decode_operands(op: int, packed: int, mirror: bool = False) -> list:
    """Port of the per-opcode decode callbacks (values in cm / seconds / ints)."""
    b = lambda lo, n: (packed >> lo) & ((1 << n) - 1)
    if op == 0x00 or op == 0x05:
        return []
    if op == 0x01:
        return [b(0, 2), b(8, 4), b(12, 2), b(2, 6) * 0.1, _dec_x(b(24, 8), mirror), _dec_y(b(16, 8))]
    if op in (0x02, 0x03):
        return [b(0, 4)]
    if op == 0x04:
        return [b(0, 2), _dec_x(b(24, 8), mirror), _dec_y(b(16, 8)), b(2, 1)]
    if op == 0x06:
        return [b(0, 3), b(4, 4), b(8, 4), b(12, 4), b(16, 4), b(20, 6) * 0.1]
    if op in (0x07, 0x08):
        return [b(0, 3), _dec_x(b(24, 8), mirror), _dec_y(b(16, 8)), b(3, 5) * 3 - 30]
    if op == 0x09:
        return [b(0, 4), _dec_x(b(24, 8), mirror), _dec_y(b(16, 8)), b(4, 3)]
    if op in (0x0A, 0x10):
        t = b(0, 4)
        y = _dec_y(b(16, 8))
        return [t, _dec_x(b(24, 8), mirror), -y if t in (2, 3) else y]
    if op in (0x0B, 0x0C):
        return [b(0, 4), _dec_lane(b(27, 5), mirror), b(4, 6) * 0.1]
    if op == 0x0D:
        side = b(8, 4)
        if mirror and (side & 3) == 1:
            side = (side & ~3) | 2
        elif mirror and (side & 3) == 2:
            side = (side & ~3) | 1
        return [_dec_x(b(24, 8), mirror), _dec_y(b(16, 8)), b(0, 4), b(4, 4), side, b(12, 1), b(13, 3)]
    if op == 0x0E:
        side = b(20, 4)
        if mirror and (side & 3) == 1:
            side = (side & ~3) | 2
        elif mirror and (side & 3) == 2:
            side = (side & ~3) | 1
        return [b(0, 1), _dec_y(b(4, 8)), b(12, 4), b(16, 4), side, b(24, 4), b(1, 3), b(28, 1)]
    if op == 0x0F:
        return [b(0, 4), b(4, 4), b(8, 4), _dec_x(b(24, 8), mirror), _dec_y(b(16, 8))]
    if op == 0x11:
        v = b(0, 5)
        leg = v % 10
        group = v // 10
        turn = b(14, 2)
        if mirror and turn == 0:
            turn = 1
        elif mirror and turn == 1:
            turn = 0
        if leg == 9:
            xy = [float(b(24, 8)), float(b(16, 8))]
        else:
            xy = [_dec_x(b(24, 8), mirror), _dec_y(b(16, 8))]
        return [leg, b(6, 6) * 0.1, b(5, 1), b(12, 2), turn, xy[0], xy[1], group]
    if op == 0x12:
        t = b(0, 4)
        d = _dec_y(b(24, 8))
        if t == 9 and mirror:
            d = -d
        return [t, b(4, 1), d, b(20, 4)]
    if op in (0x13, 0x14):
        return [b(0, 4), b(4, 4)]
    if op == 0x15:
        return [b(14, 2), _dec_x(b(24, 8), mirror), _dec_y(b(16, 8)), b(8, 2), b(0, 4), b(4, 4), b(10, 4)]
    if op in (0x16, 0x17):
        v = b(28, 4)
        return [b(0, 4), b(4, 6) * 0.1, 0 if v == 0 else ((9 - v) if mirror else v)]
    if op == 0x18:
        return [b(14, 2), _dec_x(b(24, 8), mirror), _dec_y(b(16, 8)), b(12, 2), b(0, 4), b(4, 4), b(8, 4)]
    if op == 0x19:
        return [b(0, 3), _dec_x(b(24, 8), mirror), _dec_y(b(16, 8)), b(4, 4), b(8, 3), b(3, 1), b(12, 4)]
    if op == 0x1A:
        return [b(0, 3), _dec_x(b(24, 8), mirror), _dec_y(b(16, 8)), b(12, 4), b(8, 3), b(3, 1), b(4, 4), b(11, 1)]
    if op == 0x1B:
        return [b(0, 2), b(2, 2), _dec_x(b(24, 8), mirror), _dec_y(b(16, 8)), _dec_lane(b(4, 5), mirror), b(9, 1)]
    if op == 0x1C:
        return [b(0, 2), _dec_lane(b(2, 5), mirror), b(8, 2), 0, b(16, 4), 0]
    return []


def encode_operands(op: int, values: Sequence) -> int:
    """Port of the per-opcode encode callbacks (inverse of decode, unmirrored)."""
    v = list(values)
    n = len(OPERAND_SCHEMAS.get(op, ()))
    if len(v) < n:
        v = v + [0] * (n - len(v))
    i = lambda k, bits: int(round(float(v[k]))) & ((1 << bits) - 1)
    if op in (0x00, 0x05):
        return 0
    if op == 0x01:
        return (i(0, 2) | (i(1, 4) << 8) | (i(2, 2) << 12) | (_enc_time(v[3]) << 2)
                | (_enc_x(v[4]) << 24) | (_enc_y(v[5]) << 16))
    if op in (0x02, 0x03):
        return i(0, 4)
    if op == 0x04:
        return i(0, 2) | (_enc_x(v[1]) << 24) | (_enc_y(v[2]) << 16) | (i(3, 1) << 2)
    if op == 0x06:
        return (i(0, 3) | (i(1, 4) << 4) | (i(2, 4) << 8) | (i(3, 4) << 12) | (i(4, 4) << 16)
                | (_enc_time(v[5]) << 20))
    if op in (0x07, 0x08):
        a = max(0, min(31, _round_half_away((float(v[3]) + 30.0) / 3.0)))
        return i(0, 3) | (_enc_x(v[1]) << 24) | (_enc_y(v[2]) << 16) | (a << 3)
    if op == 0x09:
        return i(0, 4) | (_enc_x(v[1]) << 24) | (_enc_y(v[2]) << 16) | (i(3, 3) << 4)
    if op in (0x0A, 0x10):
        t = i(0, 4)
        y = -float(v[2]) if t in (2, 3) else float(v[2])
        return t | (_enc_x(v[1]) << 24) | (_enc_y(y) << 16)
    if op in (0x0B, 0x0C):
        return i(0, 4) | (_enc_lane(int(v[1])) << 27) | (_enc_time(v[2]) << 4)
    if op == 0x0D:
        return ((_enc_x(v[0]) << 24) | (_enc_y(v[1]) << 16) | i(2, 4) | (i(3, 4) << 4)
                | (i(4, 4) << 8) | (i(5, 1) << 12) | (i(6, 3) << 13))
    if op == 0x0E:
        return (i(0, 1) | (_enc_y(v[1]) << 4) | (i(2, 4) << 12) | (i(3, 4) << 16) | (i(4, 4) << 20)
                | (i(5, 4) << 24) | (i(6, 3) << 1) | (i(7, 1) << 28))
    if op == 0x0F:
        return i(0, 4) | (i(1, 4) << 4) | (i(2, 4) << 8) | (_enc_x(v[3]) << 24) | (_enc_y(v[4]) << 16)
    if op == 0x11:
        leg = int(v[0]) % 10
        group = int(v[7]) if len(v) > 7 else 0
        code = (leg + 10 * group) & 0x1F
        if leg == 9:
            xy = ((int(v[5]) & 0xFF) << 24) | ((int(v[6]) & 0xFF) << 16)
        else:
            xy = (_enc_x(v[5]) << 24) | (_enc_y(v[6]) << 16)
        return code | (_enc_time(v[1]) << 6) | (i(2, 1) << 5) | (i(3, 2) << 12) | (i(4, 2) << 14) | xy
    if op == 0x12:
        return i(0, 4) | (i(1, 1) << 4) | (i(3, 4) << 20) | (_enc_y(v[2]) << 24)
    if op in (0x13, 0x14):
        return i(0, 4) | (i(1, 4) << 4)
    if op == 0x15:
        return ((i(0, 2) << 14) | (_enc_x(v[1]) << 24) | (_enc_y(v[2]) << 16) | (i(3, 2) << 8)
                | i(4, 4) | (i(5, 4) << 4) | (i(6, 4) << 10))
    if op in (0x16, 0x17):
        return i(0, 4) | (_enc_time(v[1]) << 4) | (i(2, 4) << 28)
    if op == 0x18:
        return ((i(0, 2) << 14) | (_enc_x(v[1]) << 24) | (_enc_y(v[2]) << 16) | (i(3, 2) << 12)
                | i(4, 4) | (i(5, 4) << 4) | (i(6, 4) << 8))
    if op == 0x19:
        return (i(0, 3) | (_enc_x(v[1]) << 24) | (_enc_y(v[2]) << 16) | (i(3, 4) << 4) | (i(4, 3) << 8)
                | (i(5, 1) << 3) | (i(6, 4) << 12))
    if op == 0x1A:
        return (i(0, 3) | (_enc_x(v[1]) << 24) | (_enc_y(v[2]) << 16) | (i(3, 4) << 12) | (i(4, 3) << 8)
                | (i(5, 1) << 3) | (i(6, 4) << 4) | (i(7, 1) << 11))
    if op == 0x1B:
        return (i(0, 2) | (i(1, 2) << 2) | (_enc_x(v[2]) << 24) | (_enc_y(v[3]) << 16)
                | (_enc_lane(int(v[4])) << 4) | (i(5, 1) << 9))
    if op == 0x1C:
        return i(0, 2) | (_enc_lane(int(v[1])) << 2) | (i(2, 2) << 8) | (i(4, 4) << 16)
    raise ValueError(f"unknown opcode {op:#x}")


NODE_FLAG_TERM = 0x02
NODE_FLAG_ACTION = 0x04
NODE_FLAG_CARRIER = 0x10


@dataclass
class Node:
    op: int
    flags: int
    operands: list

    @classmethod
    def from_bytes(cls, raw: bytes, mirror: bool = False) -> "Node":
        if len(raw) != NODE_SIZE:
            raise ValueError("node must be 8 bytes")
        packed = struct.unpack_from("<I", raw, 4)[0]
        return cls(raw[0], raw[1], decode_operands(raw[0], packed, mirror))

    def to_bytes(self) -> bytes:
        return bytes((self.op & 0xFF, self.flags & 0xFF, 0, 0)) + struct.pack("<I", encode_operands(self.op, self.operands))

    @property
    def name(self) -> str:
        return OPCODE_NAMES.get(self.op, f"op{self.op:#04x}")

    def describe(self) -> str:
        specs = OPERAND_SCHEMAS.get(self.op, ())
        parts = []
        for spec, val in zip(specs, self.operands):
            if spec.kind in ("x_ft", "y_ft"):
                parts.append(f"{spec.key}={val / YD_CM:+.1f}yd")
            elif spec.kind == "time":
                parts.append(f"{spec.key}={val:.1f}s")
            elif spec.choices and int(val) in spec.choices:
                parts.append(f"{spec.key}={spec.choices[int(val)]}")
            else:
                parts.append(f"{spec.key}={int(val)}")
        return f"{self.name} [{', '.join(parts)}]"


def entry_flags(op: int) -> int:
    return OPCODE_FLAGS[op if 0 <= op < OPCODE_COUNT else 0]


CARRIER_OPS = frozenset({0x13, 0x14, 0x16, 0x17, 0x07, 0x08})


def chain_is_carrier(nodes: Sequence[Node]) -> bool:
    """Retail sets the CARRIER flag on chains that give, take or kick the ball."""
    return any(nd.op in CARRIER_OPS for nd in nodes)


def assign_node_flags(nodes: Sequence[Node], ball_carrier: bool | None = None) -> None:
    """Apply the stock flag-byte convention in place.

    Retail chains carry: TERM (0x02) on the last node; ACTION (0x04) on the
    first node after index 0 that is not Ball Action (the last node when the
    chain has one node); CARRIER (0x10) from the first node through the last
    give / take / kick node of chains that handle the ball.  Bit 0 (alternate
    branch) is preserved when already present.  Checked against 94,169 stock
    offense/defense chains: the rule reproduces every chain except a handful
    of mixed handoff/pitch specials.
    """
    n = len(nodes)
    if n == 0:
        return
    if ball_carrier is None:
        ball_carrier = chain_is_carrier(nodes)
    for nd in nodes:
        nd.flags &= 0x01
    nodes[-1].flags |= NODE_FLAG_TERM
    action_idx = next((k for k in range(1, n) if nodes[k].op != 0x03), n - 1)
    nodes[action_idx].flags |= NODE_FLAG_ACTION
    if ball_carrier:
        last = max((k for k, nd in enumerate(nodes) if nd.op in CARRIER_OPS), default=-1)
        for k in range(last + 1):
            nodes[k].flags |= NODE_FLAG_CARRIER


# ---------------------------------------------------------------------------
# Descriptor + validator (port of FUN_001a9840 and helpers)
# ---------------------------------------------------------------------------

def _opget(node_raw: bytes, idx: int) -> float:
    vals = decode_operands(node_raw[0], struct.unpack_from("<I", node_raw, 4)[0])
    return vals[idx] if idx < len(vals) else 0.0


def _validate_cb(op: int, node_raw: bytes, slot: int, play_flags: int) -> bool:
    p = struct.unpack_from("<I", node_raw, 4)[0]
    if op in (0x02, 0x13, 0x14):
        v = p & 0xF
        return 0 <= v <= 10 and v != slot
    if op == 0x03:
        v = p & 0xF
        fam = (play_flags >> 6) & 7
        return {0: v != 2, 2: v == 3, 4: v == 1, 6: v == 2}.get(fam, False)
    if op == 0x12:
        t = p & 0xF
        if t == 9:
            return True
        return not (((p >> 24) - 0x40) * FT_CM < 0)
    return True


@dataclass
class ChainCheck:
    ok: bool
    reason: str
    and_nibble: int
    feature_byte: int


def analyze_chain(play_flags: int, assignments: Sequence[tuple[int, Sequence[bytes]]], slot: int,
                  descriptor_override: int | None = None) -> ChainCheck:
    """Port of FUN_001a91a0 for one assignment; also yields the AND nibble and feature byte."""
    desc, nodes = assignments[slot]
    if descriptor_override is not None:
        desc = descriptor_override
    count = desc & 0xF
    if count == 0 or count > len(nodes):
        return ChainCheck(False, "node count is 0 or exceeds chain", 0xF, 0)
    if not (nodes[count - 1][1] & 0x02):
        return ChainCheck(False, "last node lacks the TERM flag", 0xF, 0)
    and_nib = 0xF
    feat = 0
    saw_action_flag = False
    terminal = False
    saw_dstart = False
    for i in range(count - 1, -1, -1):
        n = nodes[i]
        op = n[0]
        ef = entry_flags(op)
        u16 = n[0] | (n[1] << 8)
        if (desc & 0x10000) and (u16 & 0x200) and not (ef & 0x2000):
            return ChainCheck(False, f"node {i} ({OPCODE_NAMES.get(op, op)}) may not end an assigned chain", and_nib, feat)
        if not _validate_cb(op, n, slot, play_flags):
            return ChainCheck(False, f"node {i} ({OPCODE_NAMES.get(op, op)}) has an invalid operand", and_nib, feat)
        if u16 & 0x400:
            saw_action_flag = True
        and_nib &= ef
        if ef & 0x80:
            feat |= 1
        if op == 0x01:
            if saw_action_flag and not terminal:
                if int(_opget(n, 0)) == 1:
                    o1 = int(_opget(n, 1))
                    if o1 in (1, 3, 6):
                        terminal = True
                    elif o1 == 2:
                        terminal = (feat & 2) == 2
                else:
                    terminal = False
        elif op == 0x02:
            feat |= 0x22
        elif op in (0x05, 0x13):
            feat |= 0x20
        elif op == 0x03:
            feat |= 8
            terminal = True
        elif op == 0x04:
            if int(_opget(n, 0)) == 2:
                feat |= 4
        elif op == 0x06:
            feat |= 0x24
        elif op in (0x07, 0x08):
            feat |= 4
        elif op == 0x09:
            feat |= 1
        elif op == 0x0B:
            feat |= 0x10 if int(_opget(n, 0)) != 0 else 0x20
        elif op in (0x0C, 0x12):
            feat |= 0x10
        elif op == 0x0D:
            feat |= 2
        elif op == 0x0E:
            feat |= 8
        elif op == 0x11:
            feat |= 0x40
        elif op in (0x15, 0x18):
            if op == 0x18 and terminal:
                feat |= 0x80
            if int(_opget(n, 0)) == 2:
                t = int(_opget(n, 5))
                if t == slot or t < 0 or t > 10:
                    return ChainCheck(False, f"node {i}: follow target slot {t} is invalid", and_nib, feat)
                if int(_opget(n, 6)) >= (assignments[t][0] & 0xF):
                    return ChainCheck(False, f"node {i}: follow node index exceeds slot {t}'s chain", and_nib, feat)
        elif op == 0x19:
            return ChainCheck(False, f"node {i}: opcode 0x19 is rejected by the game", and_nib, feat)
        elif op == 0x1A:
            t = int(_opget(n, 3))
            if int(_opget(n, 7)) >= count:
                return ChainCheck(False, f"node {i}: motion node index exceeds chain", and_nib, feat)
            kind = int(_opget(n, 0))
            if kind in (2, 3, 5):
                if t == slot or t < 0 or t > 10:
                    return ChainCheck(False, f"node {i}: motion target slot {t} is invalid", and_nib, feat)
            elif kind == 6:
                if int(_opget(n, 5)) != 0 or int(_opget(n, 7)) != 0 or t == slot or t < 0 or t > 10:
                    return ChainCheck(False, f"node {i}: motion link fields are invalid", and_nib, feat)
                idx = int(_opget(n, 6))
                if idx >= (assignments[t][0] & 0xF) or assignments[t][1][idx][0] != 0x1A:
                    return ChainCheck(False, f"node {i}: motion link must point at a Motion node of slot {t}", and_nib, feat)
        elif op == 0x1B:
            if saw_action_flag and not terminal:
                terminal = True
            saw_dstart = True
        elif op == 0x1C:
            if saw_dstart and saw_action_flag and not terminal:
                terminal = True
    err = _ball_sim(play_flags, assignments, slot, desc)
    if err:
        return ChainCheck(False, err, and_nib, feat)
    if not terminal:
        return ChainCheck(False, "chain has no terminal action (needs Ball Action, or an ACTION-flagged node after a Start role 1/3/6 or Defense Start)", and_nib, feat)
    if not (saw_dstart or (play_flags & 0x1C0) != 0x40 or count < 3):
        return ChainCheck(False, "defensive chains with 3+ nodes must start with Defense Start", and_nib, feat)
    if and_nib != ((desc >> 4) & 0xF):
        return ChainCheck(False, f"descriptor side nibble {(desc >> 4) & 0xF:#x} != computed {and_nib:#x}", and_nib, feat)
    if feat != ((desc >> 8) & 0xFF):
        return ChainCheck(False, f"descriptor feature byte {(desc >> 8) & 0xFF:#04x} != computed {feat:#04x}", and_nib, feat)
    return ChainCheck(True, "", and_nib, feat)


def _ball_sim(play_flags: int, assignments: Sequence[tuple[int, Sequence[bytes]]], slot: int, desc: int) -> str | None:
    """Port of FUN_001a8fb0: ball possession simulation for carrier chains."""
    nodes = assignments[slot][1]
    count = desc & 0xF
    if (desc & 0xF0) != 0x10:
        return None
    has_ball = bool(desc & 0x200)
    got_snap = False
    branch_state = False
    branch_idx = 9999
    for i in range(count):
        n = nodes[i]
        op = n[0]
        ef = entry_flags(op)
        if i == branch_idx:
            has_ball = branch_state
        if not has_ball and not got_snap:
            for j in range(SLOT_COUNT):
                d2, nodes2 = assignments[j]
                if d2 & 0x200:
                    for k in range(d2 & 0xF):
                        if nodes2[k][0] == 0x02:
                            if int(_opget(nodes2[k], 0)) == slot and k <= i:
                                has_ball = True
                                got_snap = True
                            break
        if op == 0x1A:
            branch_idx = int(_opget(n, 4))
            branch_state = has_ball
        if ef & 0x80:
            if not has_ball:
                return f"node {i} ({OPCODE_NAMES.get(op, op)}) needs the ball but nobody gave it to slot {slot}"
        elif has_ball:
            if op not in (0x00, 0x01, 0x03, 0x1A, 0x1B):
                return f"node {i} ({OPCODE_NAMES.get(op, op)}) cannot run while holding the ball"
        if ef & 0x40:
            if op in (0x02, 0x06, 0x07, 0x08, 0x13):
                if not has_ball:
                    return f"node {i} ({OPCODE_NAMES.get(op, op)}) gives the ball away without having it"
                has_ball = False
            elif op in (0x05, 0x09, 0x16):
                if has_ball:
                    return f"node {i} ({OPCODE_NAMES.get(op, op)}) takes the ball while already holding it"
                has_ball = True
            else:
                return f"node {i} ({OPCODE_NAMES.get(op, op)}) unexpected ball flag"
    return None


def _handoff_sums(assignments: Sequence[tuple[int, Sequence[bytes]]], slot: int) -> tuple[int, int] | None:
    desc, nodes = assignments[slot]
    count = desc & 0xF
    a = [0] * count
    b = [0] * count
    for i in range(count - 1, -1, -1):
        n = nodes[i]
        op = n[0]
        if op == 0x13:
            t = int(_opget(n, 0))
            if t == slot:
                return None
            a[i] = t
        elif op == 0x14:
            t = int(_opget(n, 0))
            if t == slot:
                return None
            b[i] = t
        elif op == 0x16:
            a[i] = -slot
        elif op == 0x17:
            b[i] = -slot
    for hi in range(count - 1, -1, -1):
        for lo in range(hi - 1, -1, -1):
            if a[hi] == a[lo] and ((nodes[hi][1] & 1) == 1) != ((nodes[lo][1] & 1) == 1):
                a[lo] = 0
            if b[hi] == b[lo] and ((nodes[hi][1] & 1) == 1) != ((nodes[lo][1] & 1) == 1):
                b[lo] = 0
    return sum(a), sum(b)


def validate_play(play_flags: int, assignments: Sequence[tuple[int, Sequence[bytes]]]) -> str | None:
    """Return None when the game would accept the play, else a human-readable reason."""
    fam = (play_flags >> 6) & 7
    cat = play_flags & 0x3F
    if cat != 0xE:
        ok = {0: cat <= 3 or cat in (0xC, 0xA), 1: 4 <= cat <= 7, 2: cat == 10, 3: cat == 11,
              4: cat == 12, 5: cat == 13, 6: cat == 8, 7: cat == 9}[fam]
        if not ok:
            return f"play type code {cat} is invalid for family {fam}"
    sum_a = sum_b = 0
    need1 = need2 = need3 = False
    for s in range(SLOT_COUNT):
        chk = analyze_chain(play_flags, assignments, s)
        if not chk.ok:
            return f"slot {s}: {chk.reason}"
        sums = _handoff_sums(assignments, s)
        if sums is None:
            return f"slot {s}: handoff targets itself"
        sum_a += sums[0]
        sum_b += sums[1]
        desc = assignments[s][0]
        if fam == 0:
            side_ok = (desc & 0x10) == 0x10
            if (desc >> 8) & 2:
                need1 = True
            if (desc >> 8) & 8:
                need3 = True
            need2 = True
        elif fam == 1:
            side_ok = (desc & 0x20) == 0x20
            need1 = need2 = need3 = True
        elif fam in (2, 4, 6):
            if fam in (2, 4) and desc & 0x200:
                need1 = True
            side_ok = (desc & 0x40) == 0x40
            if need1 or fam == 6:
                need1 = True
            if (desc >> 8) & 4:
                need2 = True
            if (desc >> 8) & 8:
                need3 = True
        else:
            side_ok = (desc & 0x80) == 0x80
            need1 = need2 = need3 = True
        if not side_ok:
            return f"slot {s}: chain contains an opcode not allowed for this play family"
    if sum_a != 0 or sum_b != 0:
        return "every Handoff To must be matched by a Take Handoff in the target slot (and fakes likewise)"
    if not (need2 and need3):
        return "play needs a ball handler (Ball Action / Man Coverage feature) somewhere"
    if not need1:
        return "play needs a snapper (Snap To) somewhere"
    return None


def build_descriptor(play_flags: int, assignments: Sequence[tuple[int, Sequence[bytes]]], slot: int,
                     high_byte: int) -> int:
    """Compute the 32-bit descriptor for a chain the way the game expects it.

    Layout (retail): bits 0-3 node count, 4-7 AND of the opcode-table side
    nibbles, 8-15 feature byte (bit 9 doubles as "starts with the ball"),
    16-23 ``0xB0`` | ends-with-action, 24-31 the donor's high byte.
    """
    nodes = assignments[slot][1]
    count = len(nodes)
    if not 1 <= count <= 15:
        raise ValueError("a chain needs 1-15 nodes")
    probe = count | (0xB0 << 16)
    chk = analyze_chain(play_flags, assignments, slot, descriptor_override=probe)
    l_byte = 0xB0 | (1 if entry_flags(nodes[-1][0]) & 0x2000 else 0)
    return count | (chk.and_nibble << 4) | (chk.feature_byte << 8) | (l_byte << 16) | ((high_byte & 0xFF) << 24)


# ---------------------------------------------------------------------------
# Formation record
# ---------------------------------------------------------------------------

@dataclass
class FormationSlot:
    stance_byte: int      # signed byte at +0 (always 0 in retail)
    mirror_partner: int   # high nibble at +1 (0xB = none)
    stance: int           # low nibble at +1 (retail: 1, 2 or 3)
    x: list[int]          # three lateral columns (cm)
    z: list[int]          # three depth columns (cm); the game reads column 0


@dataclass
class FormationRecord:
    name_field: int
    flags: int
    eligible: bytes
    package_map: bytes
    header_word: int
    slots: list[FormationSlot]

    @classmethod
    def from_bytes(cls, raw: bytes) -> "FormationRecord":
        if len(raw) != 0xB4:
            raise ValueError("formation record must be 0xB4 bytes")
        slots = []
        for s in range(SLOT_COUNT):
            r = FORMATION_SLOT_BASE + s * FORMATION_SLOT_STRIDE
            sbyte = struct.unpack_from("<b", raw, r)[0]
            nib = raw[r + 1]
            x = list(struct.unpack_from("<hhh", raw, r + 2))
            z = list(struct.unpack_from("<hhh", raw, r + 8))
            slots.append(FormationSlot(sbyte, nib >> 4, nib & 0xF, x, z))
        return cls(
            struct.unpack_from("<i", raw, 0)[0],
            struct.unpack_from("<I", raw, 4)[0],
            raw[8:0xD],
            raw[0xD:0x18],
            struct.unpack_from("<H", raw, 0x18)[0],
            slots,
        )

    def to_bytes(self) -> bytes:
        out = bytearray(0xB4)
        struct.pack_into("<i", out, 0, self.name_field)
        struct.pack_into("<I", out, 4, self.flags)
        out[8:0xD] = self.eligible
        out[0xD:0x18] = self.package_map
        struct.pack_into("<H", out, 0x18, self.header_word)
        for s, slot in enumerate(self.slots):
            r = FORMATION_SLOT_BASE + s * FORMATION_SLOT_STRIDE
            struct.pack_into("<b", out, r, slot.stance_byte)
            out[r + 1] = ((slot.mirror_partner & 0xF) << 4) | (slot.stance & 0xF)
            struct.pack_into("<hhh", out, r + 2, *[max(-32768, min(32767, int(v))) for v in slot.x])
            struct.pack_into("<hhh", out, r + 8, *[max(-32768, min(32767, int(v))) for v in slot.z])
        return bytes(out)

    @property
    def type_code(self) -> int:
        return (self.flags >> 8) & 0x3F

    @property
    def qb_alignment(self) -> int:
        """1 = under center, 2 = shotgun (formation flag bits 18-19; retail: every gun
        formation has bit 19 set and every under-center formation bit 18)."""
        return (self.flags >> 18) & 3

    def set_qb_alignment(self, shotgun: bool) -> None:
        self.flags = (self.flags & ~FORMATION_FLAG_QB_MASK) | (FORMATION_FLAG_SHOTGUN if shotgun else FORMATION_FLAG_UNDER_CENTER)

    def set_position(self, slot: int, x_cm: float, z_cm: float) -> None:
        xi = int(round(x_cm))
        zi = int(round(z_cm))
        self.slots[slot].x = [xi, xi, xi]
        self.slots[slot].z = [zi, zi, zi]

    def recompute_mirrors(self, position_codes: Sequence[int] | None = None) -> None:
        """Pair slots whose base coordinates mirror across the centre line."""
        used = set()
        for s, slot in enumerate(self.slots):
            slot.mirror_partner = NO_MIRROR
        for s, slot in enumerate(self.slots):
            if slot.mirror_partner != NO_MIRROR:
                continue
            x0, z0 = slot.x[0], slot.z[0]
            if abs(x0) <= 30:
                slot.mirror_partner = s
                continue
            best = None
            for t, other in enumerate(self.slots):
                if t == s or other.mirror_partner != NO_MIRROR:
                    continue
                if position_codes is not None and (position_codes[t] & 0x1F) != (position_codes[s] & 0x1F):
                    continue
                if abs(other.x[0] + x0) <= 60 and abs(other.z[0] - z0) <= 60:
                    best = t
                    break
            if best is not None:
                slot.mirror_partner = best
                self.slots[best].mirror_partner = s
        self.flags |= FORMATION_FLAG_HAS_MIRROR


@dataclass
class CategoryRecord:
    name_field: int
    id_byte: int
    positions: bytes

    @classmethod
    def from_bytes(cls, raw: bytes) -> "CategoryRecord":
        return cls(struct.unpack_from("<i", raw, 0)[0], raw[4], raw[5:16])

    @property
    def category_id(self) -> int:
        return self.id_byte & 0x3F


def formation_legality(slots: Sequence[FormationSlot], position_codes: Sequence[int], offense: bool = True) -> list[str]:
    """NFL alignment rules for an offensive formation (base column, cm)."""
    issues: list[str] = []
    if not offense:
        for s, slot in enumerate(slots):
            if slot.z[0] < 0:
                issues.append(f"{position_label(position_codes[s])} (slot {s}) is across the line of scrimmage")
        return issues
    on_line = [s for s, slot in enumerate(slots) if abs(slot.z[0]) <= 15]
    backfield = [s for s, slot in enumerate(slots) if slot.z[0] < -15]
    for s, slot in enumerate(slots):
        if slot.z[0] > 15:
            issues.append(f"{position_label(position_codes[s])} (slot {s}) is past the line of scrimmage")
        if abs(slot.x[0]) > 2400:
            issues.append(f"{position_label(position_codes[s])} (slot {s}) is out of bounds")
    if len(on_line) < 7:
        issues.append(f"only {len(on_line)} players on the line of scrimmage (need 7)")
    if len(backfield) > 4:
        issues.append(f"{len(backfield)} players in the backfield (max 4)")
    for s, slot in enumerate(slots):
        kind = position_codes[s] & 0x1F
        if kind in OFFENSIVE_LINE_KINDS and abs(slot.z[0]) > 15:
            issues.append(f"{position_label(position_codes[s])} (slot {s}) must be on the line")
    if on_line:
        left = min(on_line, key=lambda s: slots[s].x[0])
        right = max(on_line, key=lambda s: slots[s].x[0])
        for end in (left, right):
            if (position_codes[end] & 0x1F) in OFFENSIVE_LINE_KINDS:
                issues.append(f"{position_label(position_codes[end])} (slot {end}) is covering the end of the line and is ineligible")
    coords = [(slot.x[0], slot.z[0]) for slot in slots]
    for a in range(SLOT_COUNT):
        for b in range(a + 1, SLOT_COUNT):
            if abs(coords[a][0] - coords[b][0]) < 40 and abs(coords[a][1] - coords[b][1]) < 40:
                issues.append(f"slots {a} and {b} overlap")
    return issues


# ---------------------------------------------------------------------------
# Play-art geometry (port of the draw handlers, enough for a faithful preview)
# ---------------------------------------------------------------------------

@dataclass
class ArtSegment:
    points: list[tuple[float, float]]
    style: str = "solid"      # solid / dashed / arrow / block / zone / man
    end_marker: str = ""


def _rot(dx: float, dy: float, deg: float) -> tuple[float, float]:
    import math
    a = math.radians(deg)
    return (dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a))


def play_art(nodes: Sequence[Node], start_xy: tuple[float, float], side: int = 1,
             wide_left: bool = False) -> list[ArtSegment]:
    """Approximate the play-call art for one chain. Coordinates in cm, offense-relative."""
    segs: list[ArtSegment] = []
    x, y = start_xy
    heading = 0.0  # degrees from straight downfield; positive turns toward +x
    for nd in nodes:
        v = nd.operands
        op = nd.op
        if op == 0x11:
            leg, _t, rel, end, turn, dx, dy, _g = v
            if leg == 9:
                dx = NAMED_SPOT_X_FT[int(dx) % 12] * FT_CM
                dy = NAMED_SPOT_Y_FT[int(dy) % 12] * FT_CM
            if leg == 7:
                nx, ny = start_xy
            elif leg == 8:
                nx, ny = dx, dy
            elif leg == 2:
                segs.append(ArtSegment([(x, y), (x, y - 152.4)]))
                x, y = x, y - 152.4
                nx, ny = x + dx * side, y
                segs.append(ArtSegment([(x, y), (nx, ny)]))
                x, y = nx, ny
                nx, ny = x, y + dy + 152.4
            else:
                nx, ny = x + dx * side, y + dy
            segs.append(ArtSegment([(x, y), (nx, ny)], end_marker="block" if leg in (0, 1, 3, 4) else ""))
            x, y = nx, ny
            if turn == 0:
                heading = 45.0
            elif turn == 1:
                heading = -45.0
        elif op == 0x12:
            t, _f, dist, _k = v
            dist = float(dist)
            s = -1.0 if wide_left else 1.0
            if t == 0:
                nx, ny = x, y + dist
                segs.append(ArtSegment([(x, y), (nx, ny)], end_marker="arrow"))
                x, y = nx, ny
            elif t in (1, 2, 3, 6):
                nx, ny = x, y + dist
                segs.append(ArtSegment([(x, y), (nx, ny)]))
                x, y = nx, ny
                ang = {1: 30, 2: 45, 3: 60, 6: -45}[t] * s
                dx, dy = _rot(0, 457.2, -ang)
                segs.append(ArtSegment([(x, y), (x + dx, y + dy)], end_marker="arrow"))
                x, y = x + dx, y + dy
            elif t in (4, 5):
                d = dist * s * (1 if t == 4 else -1)
                segs.append(ArtSegment([(x, y), (x - d, y)], end_marker="arrow"))
                x -= d
            elif t in (7, 11):
                d = -60.96 * s if t == 7 else 60.96 * s
                segs.append(ArtSegment([(x, y), (x + d, y - 121.92)], end_marker="arrow"))
                x, y = x + d, y - 121.92
            elif t == 8:
                segs.append(ArtSegment([(x, y), (x + 121.92 * s, y)], style="block"))
            elif t == 9:
                segs.append(ArtSegment([(x, y), (x + (243.84 if dist >= 0 else -243.84), y)], style="block"))
            elif t == 10:
                segs.append(ArtSegment([(x, y), (x, y + dist)]))
                y += dist
                segs.append(ArtSegment([(x, y), (x + 60.96 * s, y)], style="block"))
        elif op == 0x0D:
            zx, zy = v[0], v[1]
            segs.append(ArtSegment([(x, y), (zx, zy)], style="zone", end_marker="zone"))
            x, y = zx, zy
        elif op == 0x0E:
            depth = v[1]
            segs.append(ArtSegment([(x, y), (x, y - 182.88)], style="man", end_marker="man"))
        elif op in (0x0B, 0x0C):
            lane = int(v[1])
            lx = LANE_TABLE_CM[lane] if 0 <= lane < 16 else x
            segs.append(ArtSegment([(x, y), (lx, y - 213.36)], style="dashed" if op == 0x0C else "solid", end_marker="arrow"))
            x, y = lx, y - 213.36
        elif op in (0x0A, 0x10):
            t, dx, dy = v
            segs.append(ArtSegment([(x, y), (x + dx * side, y + dy)], end_marker="arrow"))
            x, y = x + dx * side, y + dy
        elif op == 0x09:
            _m, dx, dy, _k = v
            segs.append(ArtSegment([(x, y), (x + dx * side, y + dy)], end_marker="arrow"))
            x, y = x + dx * side, y + dy
        elif op in (0x15, 0x18):
            mode, dx, dy = v[0], v[1], v[2]
            segs.append(ArtSegment([(x, y), (x + dx * side, y + dy)], end_marker="arrow" if op == 0x18 else ""))
            x, y = x + dx * side, y + dy
        elif op == 0x08:
            segs.append(ArtSegment([(x, y), (x, y + 182.88)], end_marker="arrow"))
        elif op == 0x14:
            segs.append(ArtSegment([(x, y), (x, y - 182.88)], style="dashed"))
        elif op == 0x0F:
            dx, dy = v[3], v[4]
            segs.append(ArtSegment([(x, y), (x + dx * side, y + dy)]))
            x, y = x + dx * side, y + dy
    return segs


__all__ = [
    "ArtSegment", "BALL_ACTIONS", "BLOCK_LEG_TYPES", "CategoryRecord", "ChainCheck",
    "FORMATION_FLAG_SHOTGUN", "FORMATION_FLAG_UNDER_CENTER", "FT_CM", "FormationRecord", "FormationSlot", "LANE_NONE", "LANE_TABLE_CM", "NO_MIRROR",
    "Node", "OPCODE_FLAGS", "OPCODE_NAMES", "OPERAND_SCHEMAS", "OperandSpec", "POSITION_KINDS",
    "ROUTE_SEGMENT_TYPES", "START_ROLES", "YD_CM", "CARRIER_OPS", "analyze_chain", "assign_node_flags", "chain_is_carrier",
    "build_descriptor", "decode_operands", "encode_operands", "entry_flags", "formation_legality",
    "play_art", "position_label", "validate_play",
]
