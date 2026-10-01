"""Jersey number kerning: a "1" inside a two-digit jersey number moves toward its partner. EXPERIMENTAL / UNWITNESSED.

The game draws one digit texture per value in three fixed cells (0x8E910): a single digit in material M, two digits in
L (tens) and R (ones), all bound through 0x8E8D0, which sets the texture (+0x30) and the U/V scales (+0x20 4.0, +0x24
2.0) of the material. The draw path (0x307FC..0x3083A) takes +0x20..+0x2C as (scale u, scale v, offset u, offset v);
nothing sets the U offset +0x28, and the model files store 0 there. The L and R cells stand 0.658 of a texture width
apart, which suits wide digits, so a narrow "1" (the 2026 Falcons, Rams, Cardinals, Broncos, Browns and Seahawks
fonts; flag, no base) leaves a gap that real jerseys do not have.

This owner rewrites the binder and the selector in place (0x8E8D0..0x8E9DF, no cave, no runtime state): the binder
gets a second entry (0x8E8D2) that also writes the U offset from edx, the retail entry (0x8E8D0) writes 0 (the file
value), and the two-digit path passes -KERN for a jersey "1" in the tens cell and +KERN for a jersey "1" in the ones
cell. Single digits, helmet and shoulder numbers, and every other pair are bound exactly as in retail. KERN is 0.0875
of a texture width (0.09 of the glyph height). Off in every preset.
"""
from __future__ import annotations

import hashlib
import struct

from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_number_kerning"
CAVES = REQUESTS = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_CAPTION = "Jersey numbers: kern the 1 in pairs (experimental)"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Off in every preset. A 1 inside a two-digit jersey number (10-19 and x1) moves "
    "toward the other digit by 0.09 of the number's height, as real jerseys space them, so narrow 1s (the 2026 "
    "Falcons, Rams, Cardinals, Broncos, Browns, Seahawks) no longer stand apart. The glyphs are unchanged. Single "
    "digits, helmet and shoulder numbers stay retail.")
BLOCK_VA, BLOCK_SIZE = 0x8E8D0, 0x110
SELECTOR_VA, KERN_ENTRY_VA = 0x8E910, 0x8E8D2
RETAIL_SHA256 = "506708e3fe73f45fd7d9351c9ba0ddc83c27e0d4bab9ebe5facd2fa45b5016e0"
TEXTURES, MATS_L, MATS_M, MATS_R = 0xA86C04, 0xA86D6C, 0xA86D6D, 0xA86D6E
KERN = 0.0875
# The three callers of the selector keep the retail calling convention (eax number, ecx row, edx family, 4 arguments).
GUARDS = ((0x8F05D, 5), (0x8F57B, 5), (0x8F5B4, 5))


def _f32(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def build_block(kern=KERN):
    """The 272 bytes written at BLOCK_VA (the binder, 0x90 padding, the selector, 0x90 padding)."""
    out, labels, fixups = bytearray(), {}, []

    def at():
        return BLOCK_VA + len(out)

    def emit(hexstr, imm=None):
        out.extend(bytes.fromhex(hexstr))
        if imm is not None:
            out.extend(struct.pack("<I", imm & 0xFFFFFFFF))

    def jump(opcode_hex, target, near=False):
        out.extend(bytes.fromhex(opcode_hex) + (b"\0" * (4 if near else 1)))
        fixups.append((len(out) - (4 if near else 1), near, target))

    emit("33d2")                                   # 0x8E8D0 retail entry: U offset 0
    labels["bind"] = at()                          # 0x8E8D2 kern entry: edx = U offset
    emit("3dff000000"); jump("74", "bind_ret")     # cmp eax, 0xff; je ret
    emit("3b411c"); jump("7c", "bind_ok")          # cmp eax, [ecx+0x1c]; jl ok
    emit("33c0"); jump("eb", "bind_store")         # xor eax, eax; jmp store (retail: entry address 0)
    labels["bind_ok"] = at()
    emit("c1e007"); emit("034120")                 # shl eax, 7; add eax, [ecx+0x20]
    labels["bind_store"] = at()
    emit("836008fe"); emit("8b4c2404"); emit("894830")   # and [eax+8], ~1; mov ecx, [esp+4]; mov [eax+0x30], ecx
    emit("c7402000008040"); emit("c7402400000040")       # U scale 4.0, V scale 2.0 (retail)
    emit("895028")                                 # mov [eax+0x28], edx   U offset
    labels["bind_ret"] = at()
    emit("c20400")                                 # ret 4
    out.extend(b"\x90" * (SELECTOR_VA - at()))
    emit("83ea0c"); emit("53"); emit("8b5c2414"); emit("57"); emit("8b7c2410")
    emit("83fa02"); jump("0f87", "exit", near=True)      # families 0xc..0xe only (retail)
    emit("83f80a"); jump("7d", "two")                    # cmp eax, 10; jge two
    emit("8d1492"); emit("8d0450"); emit("8d1443"); emit("03c2")
    emit("8b0485", TEXTURES)                       # mov eax, [eax*4+textures]
    emit("c1e104"); emit("8d147f"); emit("50")
    emit("0fb6840a", MATS_M)                       # movzx eax, byte [edx+ecx+mats_m]
    emit("8b4c2410"); jump("e8", BLOCK_VA, near=True)    # retail entry: single digits keep offset 0
    jump("eb", "exit")
    labels["two"] = at()
    emit("83f863"); jump("7e", "two_ok"); emit("33c0")
    labels["two_ok"] = at()
    emit("55"); emit("56"); emit("8d3492"); emit("99"); emit("bd0a000000"); emit("f7fd")   # idiv: eax tens, edx ones
    emit("c1e104"); emit("d1e6"); emit("8bea"); emit("8d147f"); emit("8d3c0a")
    for cell, mats, sign in (("l", MATS_L, -1.0), ("r", MATS_R, 1.0)):
        if cell == "l":
            emit("03c6")                           # add eax, esi       family*10 + tens
        else:
            emit("8d042e")                         # lea eax, [esi+ebp] family*10 + ones
        emit("33d2"); emit("83f801"); jump("75", cell + "_off")   # only family 0 (jersey) with digit 1
        emit("ba", _f32(sign * kern))
        labels[cell + "_off"] = at()
        emit("8d0c43"); emit("03c1")
        emit("ff3485", TEXTURES)                   # push dword [eax*4+textures]
        emit("0fb687", mats)                       # movzx eax, byte [edi+mats]
        emit("8b4c2418"); jump("e8", "bind", near=True)
    emit("5e"); emit("5d")
    labels["exit"] = at()
    emit("5f"); emit("5b"); emit("c21000")
    end = at()
    if end > BLOCK_VA + BLOCK_SIZE:
        raise ValueError("number kerning block overflows its routine")
    out.extend(b"\x90" * (BLOCK_VA + BLOCK_SIZE - end))
    for offset, near, target in fixups:
        address = labels[target] if isinstance(target, str) else target
        rel = address - (BLOCK_VA + offset + (4 if near else 1))
        if near:
            struct.pack_into("<i", out, offset, rel)
        else:
            if not -128 <= rel <= 127:
                raise ValueError("short jump out of range")
            out[offset] = rel & 0xFF
    return bytes(out)


APPLIED_BLOCK = build_block()


def _inspect(payload):
    image = XbeImage(payload)
    section = image.section(BLOCK_VA, BLOCK_SIZE)
    if section is None or section.name != ".text":  # a synthetic or foreign image reads "foreign", never a crash
        raise ValueError("Number binder is not in the expected code section")
    for va, size in GUARDS:
        raw = image.read(va, size)
        if raw[0] != 0xE8 or va + 5 + struct.unpack_from("<i", raw, 1)[0] != SELECTOR_VA:
            raise ValueError(f"Number selector caller changed at {va:#x}; rebuild from a supported base")
    block = image.read(BLOCK_VA, BLOCK_SIZE)
    if block == APPLIED_BLOCK:
        return True
    if hashlib.sha256(block).hexdigest() == RETAIL_SHA256:
        return False
    raise ValueError("Foreign number binder; rebuild from a supported base")


def status(payload):
    try:
        return "applied" if _inspect(payload) else "retail"
    except (ValueError, TypeError, IndexError, struct.error):
        return "foreign"


def verify(payload, *, enabled=True):
    if type(enabled) is not bool or _inspect(payload) != enabled:
        raise ValueError("Number kerning does not match the requested option")
    return dict(state="applied" if enabled else "retail", enabled=enabled, kern_texture_u=KERN if enabled else 0.0,
                label="EXPERIMENTAL / UNWITNESSED", runtime_witnessed=False)


def apply(payload, *, enabled=True):
    if type(enabled) is not bool:
        raise ValueError("Number kerning must be Off or On")
    applied = _inspect(payload)
    if applied == enabled:
        return payload, dict(verify(payload, enabled=enabled), changed_bytes=0, edits=[])
    if not enabled:
        raise ValueError("Number kerning cannot restore the retail routine; rebuild from the original source")
    image = XbeImage(payload)
    result = bytearray(payload)
    at = image.offset(BLOCK_VA, BLOCK_SIZE)
    result[at:at + BLOCK_SIZE] = APPLIED_BLOCK
    header = image.section(BLOCK_VA).header
    for section in _sections(result):
        if section.header_offset == header:
            result[section.header_offset + 36:section.header_offset + 56] = section_digest(result, section)
    result = bytes(result)
    return result, dict(verify(result, enabled=True), changed_bytes=sum(a != b for a, b in zip(payload, result)),
                        edits=[dict(va=hex(BLOCK_VA), size=BLOCK_SIZE)])


def reservations(payload):
    verify(payload)
    return [dict(owner=OWNER, start=hex(BLOCK_VA), end=hex(BLOCK_VA + BLOCK_SIZE), size=BLOCK_SIZE,
                 basis="pinned live routine rewritten in place: number binder and selector with the jersey 1 kern")]
