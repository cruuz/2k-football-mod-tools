"""Version 1 inline MyCareer footer. EXPERIMENTAL / UNWITNESSED.

The 128-byte block follows the COMPLETE native franchise container. Neither
ROST version nor any byte of the four native blocks is repurposed. The native
save transaction signs this footer together with the other serialized bytes.
FNV is a corruption check, not authentication. This module performs no I/O.
Byte 82 uses three formerly reserved bits: first person On, Spectate, star Off.
Old zero-filled footers retain the defaults Off / Skip presentation / star On.
"""
from __future__ import annotations

import hashlib
import struct

MAGIC = b"MCPL0001"
SIZE = 128
BASE_SIZES = (720044, 724140)
SIZES = tuple(n + SIZE for n in BASE_SIZES)
BALANCE_CAP = 1000000
BIRTH_MASK = 0x0FFFF000


class CareerSaveError(ValueError):
    """Unknown framing, corrupt state or identity mismatch."""


def require(ok, message):
    if not ok:
        raise CareerSaveError(message)


def word(data, at):
    return struct.unpack_from("<I", data, at)[0]


def checksum(data):
    value = 0x811C9DC5
    for b in data:
        value = ((value ^ b) * 0x01000193) & 0xFFFFFFFF
    return value


def seal(block):
    require(len(block) == SIZE, "career block must contain 128 bytes")
    result = bytearray(block)
    struct.pack_into("<I", result, 12, checksum(result[16:]))
    return bytes(result)


def validate(block, *, arena_size=0x92000):
    require(isinstance(block, (bytes, bytearray)) and len(block) == SIZE,
            "career block must contain 128 bytes")
    require(block[:8] == MAGIC and block[8:12] == struct.pack("<HH", 1, SIZE),
            "unknown MyCareer save version")
    require(word(block, 12) == checksum(block[16:]), "damaged MyCareer save")
    require(any(block[16:32]), "missing MyPlayer creation token")
    require(word(block, 32) < 4096, "MyPlayer ordinal exceeds its bound")
    require(2 <= block[36] <= 6 and block[37] < 8 and block[38] < 2 and block[39] < 17,
            "invalid MyPlayer phase, controller, camera or position")
    require(word(block, 40) < 32 or word(block, 40) == 0xFFFFFFFF, "invalid club")
    require(all(0x70 <= word(block, at) < arena_size for at in (44, 48, 52)),
            "identity reference leaves the roster arena")
    require(word(block, 60) & ~BIRTH_MASK == 0, "unmasked birth identity")
    require(word(block, 64) <= BALANCE_CAP and word(block, 84) <= BALANCE_CAP,
            "upgrade points exceed their bound")
    require(word(block, 68) <= 0x7F92B1, "invalid committed fixture watermark")
    require(block[72] <= 2 and block[73] == 0 and (block[74] < 32 or block[74] == 255)
            and block[75] == 0 and block[80] <= 1 and block[81] <= 1,
            "invalid request or starter preference")
    require(block[82] <= 7 and block[83] == 0 and not any(block[88:]),
            "unknown settings or nonzero reserved career bytes")
    require(word(block, 76) <= 0x7F92B1, "invalid request week key")
    require(block[72] != 0 or (block[74] == 255 and word(block, 76) == 0),
            "inactive request has a destination or due week")
    return bytes(block)


def native_size(payload):
    """Validate framing without assuming that all suffix bytes are arena growth."""
    n = len(payload)
    require(n in BASE_SIZES + SIZES, "unsupported franchise container length")
    base = n - SIZE if n in SIZES else n
    growth = base - BASE_SIZES[0]
    require(payload[0x2E0:0x2E4] == b"ROST" and word(payload, 0x2E4) == 0x91020 + growth
            and payload[0x30C:0x310] == b"ROST" and word(payload, 0x310) == int(bool(growth))
            and word(payload, 0x314) == 13,
            "ROST framing and franchise size disagree")
    require(payload[0x91320 + growth] == 2, "MyCareer requires a Franchise save")
    if n in SIZES:
        validate(payload[base:], arena_size=0x91000 + growth)
    return base


def read(payload, *, identity=True):
    base = native_size(payload)
    require(len(payload) == base + SIZE, "this Franchise has no inline MyCareer block")
    block = validate(payload[base:], arena_size=0x91000 + base - BASE_SIZES[0])
    if identity:
        from . import nfl2k5_save_rost as codec
        doc = codec.decode(payload)
        player = doc.by_key.get(("primary", word(block, 32)))
        require(player is not None, "MyPlayer ordinal is absent")
        p = player.offset
        require(payload[p + 0x35] == block[39] and word(payload, p + 4) == word(block, 56)
                and word(payload, p + 0x18) & BIRTH_MASK == word(block, 60),
                "MyPlayer identity no longer matches its saved record")
        for field, stored in ((0, 44), (16, 48), (20, 52)):
            target = doc.rel(p + field)
            require(target is not None and target - doc.layout.root == word(block, stored),
                    "MyPlayer name or college reference changed")
    return block


def append(payload, block):
    """Copy-only native-envelope extension with exact preservation receipts.

    Intended for tests/import tooling. The in-game serializer creates new
    career saves itself; this is never a required external setup operation.
    """
    base = native_size(payload)
    validate(block, arena_size=0x91000 + base - BASE_SIZES[0])
    result = bytes(payload[:base]) + bytes(block)
    read(result)
    return result, {"experimental": True, "runtime_witnessed": False,
                    "format": "MyCareer/1", "career_offset": base, "career_bytes": SIZE,
                    "native_bytes_preserved": base, "file_growth": len(result) - len(payload),
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                    "before_sha256": hashlib.sha256(payload).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


def from_runtime(state):
    """Encode pointer-free fields; +2704 is the native encoder's FPF snapshot.

    Short legacy binder snapshots have the three default settings. The runtime
    refreshes +2704 from the authoritative retail word before each save.
    """
    require(len(state) >= 212, "short binder state")
    b = bytearray(SIZE)
    b[:8] = MAGIC
    struct.pack_into("<HH", b, 8, 1, SIZE)
    b[16:32] = state[40:56]
    b[32:36] = state[28:32]
    b[36:40] = bytes((word(state, 24), word(state, 32), word(state, 36), state[149]))
    b[40:44], b[44:56] = state[56:60], state[84:96]
    b[56:60] = state[100:104]
    struct.pack_into("<I", b, 60, word(state, 120) & BIRTH_MASK)
    b[64:72], b[72:80] = state[64:72], state[188:196]
    b[80:82] = bytes((word(state, 180), word(state, 184)))
    b[84:88] = state[196:200]
    if len(state) >= 2708:
        settings = [word(state, at) for at in (2704, 2696, 2700)]
        require(all(v <= 1 for v in settings), "invalid runtime settings")
        b[82] = sum(v << bit for bit, v in enumerate(settings))
    return validate(seal(b))


def to_runtime(block):
    """Reconstruct pointer-free binder fields. Native load resolves live objects."""
    b = validate(block)
    s = bytearray(4096)
    s[:8] = b"MCQB0001"
    struct.pack_into("<I", s, 8, 1280)
    for at, value in ((24, b[36]), (32, b[37]), (36, b[38]), (180, b[80]), (184, b[81])):
        struct.pack_into("<I", s, at, value)
    s[40:56], s[28:32], s[56:60] = b[16:32], b[32:36], b[40:44]
    s[84:96], s[100:104], s[120:124] = b[44:56], b[56:60], b[60:64]
    s[96:100], s[112:116], s[116:120] = b[44:48], b[48:52], b[52:56]
    s[149] = b[39]
    s[64:72], s[188:196], s[196:200] = b[64:72], b[72:80], b[84:88]
    for bit, at in enumerate((2704, 2696, 2700)):
        struct.pack_into("<I", s, at, (b[82] >> bit) & 1)
    return bytes(s)
