"""Modern LED play-clock digits for the goal-post and scoreboard displays (USA retail).

The stadium loader (0x99840) loads ten textures named ``clock_font_000`` .. ``clock_font_009``
after it binds the ``digit_clock_1`` .. ``digit_away_score_R`` nodes.  All ten textures share one
128x128 P8 atlas (four mip levels) and differ only in their palette; the atlas is a 6 x 7 grid of
round bulbs, one bulb per cell, and each bulb carries the palette indices that select the digits
lit in that cell.  The same atlas feeds the game clock, the play clock and both scores, so it is
what players see as the light-bulb digits.  The atlas is generated at load; there is no texture
file to patch.

This owner hooks the end of the loader's clock-font loop (0x9999A) and rewrites the generated
atlas in place: clear it to the transparent index, fill the 42 bulb cells as 15 x 15 square LED
tiles using a static table of the original bulb mask indices, rebuild the four mip levels, and
map the ten palettes to one warm white (bright entries) and black (everything else).  The result
is the same 6 x 7 digit shapes in a solid LED matrix, in the clock colour, for every stadium and
every weather variant.  It runs once per stadium load, never per frame.

EXPERIMENTAL / UNWITNESSED in game unless a report says otherwise.  The static mask table comes
from the USA retail clock-font atlas; a foreign loader or atlas is refused.  The clock colon is a
separate ``digit_colen`` material and keeps its retail look.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_clock_led"
CODE_SIZE = 576
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
HOOK = ("clock_led_font", 0x9999A, bytes.fromhex("895c240c8b"))   # mov [esp+0xc], ebx ; first byte of the nop
RESUME = 0x999A0
ARRAY = 0xB66288
ATLAS_SIZE = 21824                    # 128x128 base + 64/32/16/8 mips
PALETTE_SIZE = 1024
BUILD_CAPTION = "Modern LED clock digits (experimental)"
HELP_TEXT = ("The goal-post play clock and the stadium score digits become a solid warm-white LED "
             "matrix instead of the retail round bulbs. Every stadium and weather variant is "
             "covered; the clock colon keeps its retail look. EXPERIMENTAL / UNWITNESSED.")
# 0x99960..0x999B0, the clock-font lookup loop and the hook site (retail USA executable).
GUARD = (0x99960, 80, "4d3f264b6ae29ed7f3a0c702bfd4c7d06267cf583ef8264e39ce97a44a41c57d")
# One index per 6x7 bulb cell (row-major, gy then gx).  Each index is a palette entry whose
# visible-digit mask equals the cells's digit mask in the retail clock-font palettes.
BODY = bytes([127, 0, 15, 15, 127, 127, 60, 3, 126, 126, 7, 7, 60, 60, 126, 126, 7, 7,
              16, 16, 19, 19, 127, 127, 4, 4, 126, 126, 31, 31, 4, 4, 126, 126, 31, 31,
              47, 47, 48, 48, 127, 127])
CX = bytes([10, 32, 53, 74, 96, 117])
CY = bytes([9, 27, 45, 64, 82, 100, 119])
TABLE_OFF = 0x200
WARM_WHITE = 0xFFFFF8E8             # BGRA: E8 F8 FF FF


class ClockLedError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ClockLedError(message)


def _asm():
    from .nfl2k5_draft_ai import _Asm
    return _Asm


def code_for(code_va):
    """The stadium-loader cave: clear the atlas, draw 42 LED tiles, rebuild the mips, retint the ten palettes."""
    a = _asm()(code_va)
    imm = lambda va: struct.pack("<I", va).hex()  # noqa: E731
    a.b("895c240c")                              # re-run the hook's original mov [esp+0xc], ebx
    a.b("9c60")                                  # pushfd; pushad
    a.b("83ec10")                                # local gy/gx/cx/cy
    a.b("8b35" + imm(ARRAY))
    a.b("85f6")
    a.j32("0f84", "done")
    a.b("8b5e04")                                # ebx = first clock-font texture's pixels
    a.b("85db")
    a.j32("0f84", "done")
    a.b("89df")                                  # clear atlas (base and mips) to 0xAA
    a.b("b940550000")                            # mov ecx, 21824
    a.b("b0aa")
    a.b("f3aa")
    a.b("c7042400000000")                        # gy = 0
    a.b("c744240400000000")                      # gx = 0
    a.label("gy")
    a.label("gx")
    a.b("8b442404")                              # eax = gx
    a.b("0fb680" + struct.pack("<I", code_va + TABLE_OFF + len(BODY)).hex())
    a.b("89442408")                              # cx
    a.b("8b0424")                                # eax = gy
    a.b("0fb680" + struct.pack("<I", code_va + TABLE_OFF + len(BODY) + len(CX)).hex())
    a.b("8944240c")                              # cy
    a.b("8b0424")                                # i = gy*6 + gx
    a.b("6bc006")
    a.b("03442404")
    a.b("0fb688" + struct.pack("<I", code_va + TABLE_OFF).hex())   # body = BODY[i]
    a.b("8b54240c")                              # edx = cy
    a.b("83ea07")
    a.b("c1e207")
    a.b("8b442408")                              # eax = cx
    a.b("83e807")
    a.b("01d0")
    a.b("01d8")
    a.b("89c7")                                  # edi = atlas + (cy-7)*128 + (cx-7)
    a.b("89c8")                                  # eax = body
    a.b("bd0f000000")                            # 15 rows
    a.label("fillrow")
    a.b("b90f000000")
    a.b("f3aa")                                  # 15 bytes of body
    a.b("83c771")                                # add edi, 0x71
    a.b("4d")
    a.j8("75", "fillrow")
    a.b("ff442404")
    a.b("837c240406")
    a.j32("0f8c", "gx")
    a.b("c744240400000000")
    a.b("ff0424")
    a.b("833c2407")
    a.j32("0f8c", "gy")
    for k, (src_off, dst_off, size) in enumerate(((0, 0x4000, 64), (0x4000, 0x5000, 32),
                                                  (0x5000, 0x5400, 16), (0x5400, 0x5500, 8))):
        a.b("8db3" + struct.pack("<I", src_off).hex())
        a.b("8dbb" + struct.pack("<I", dst_off).hex())
        a.b("ba" + struct.pack("<I", size).hex())
        a.label(f"mrow{k}")
        a.b("b9" + struct.pack("<I", size).hex())
        a.label(f"mcol{k}")
        a.b("8a06")
        a.b("8807")
        a.b("83c602")
        a.b("47")
        a.b("49")
        a.j8("75", f"mcol{k}")
        a.b("81c6" + struct.pack("<I", size * 2).hex())
        a.b("4a")
        a.j8("75", f"mrow{k}")
    a.b("31ed")                                  # ebp = 0
    a.label("pal")
    a.b("8b04ad" + imm(ARRAY))
    a.b("85c0")
    a.j8("74", "palnext")
    a.b("8b7808")                                # palette
    a.b("85ff")
    a.j8("74", "palnext")
    a.b("b900010000")                            # 256 entries
    a.label("entry")
    a.b("8b07")
    a.b("89c2")
    a.b("c1ea18")                                # alpha
    a.b("85d2")
    a.j8("74", "black")
    a.b("89c2")
    a.b("81e2ffffff00")                          # RGB
    a.b("85d2")
    a.j8("74", "black")
    a.b("0fb6ca")                                # ecx = B
    a.b("89c3")
    a.b("c1eb08")
    a.b("0fb6db")
    a.b("01d9")                                  # + G
    a.b("89c3")
    a.b("c1eb10")
    a.b("0fb6db")
    a.b("01d9")                                  # + R
    a.b("83f93c")                                # > 60
    a.j8("76", "black")
    a.b("c707e8f8ffff")                          # warm white
    a.j8("eb", "entrynext")
    a.label("black")
    a.b("c707000000ff")                          # opaque black
    a.label("entrynext")
    a.b("83c704")
    a.b("49")
    a.j8("75", "entry")
    a.label("palnext")
    a.b("45")
    a.b("83fd0a")
    a.j8("7c", "pal")
    a.label("done")
    a.b("83c410")
    a.b("61")
    a.b("9d")
    a.jmp_abs(RESUME)
    body = a.assemble()
    require(len(body) <= TABLE_OFF, f"clock LED cave is {len(body)} bytes, over its data offset")
    return (body.ljust(TABLE_OFF, b"\xcc") + BODY + CX + CY).ljust(CODE_SIZE, b"\xcc")


def sites(code_va=0):
    name, va, before = HOOK
    return [(name, va, before, (b"\xe9" + struct.pack("<i", code_va - va - 5)).ljust(len(before), b"\x90"))]


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign clock LED allocation")
    return rows[0]


def _recognize(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocation(payload) if present else None
    edits = sites(owned["va"] if owned else 0)
    states = set()
    for _name, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if owned and raw == after else "foreign")
    if owned:
        raw = image.read(owned["va"], CODE_SIZE)
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == code_for(owned["va"]) else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed clock LED site/code")
    va, size, digest = GUARD
    content = bytearray(image.read(va, size))
    for _name, at, before, _after in edits:
        if va <= at and at + len(before) <= va + size:
            content[at - va:at - va + len(before)] = before
    require(hashlib.sha256(content).hexdigest() == digest, "Foreign clock LED prerequisite")
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except Exception:
        return "foreign"


def apply(payload):
    """Install, or replay an identical installation."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    try:
        state = _recognize(payload)
    except Exception as exc:
        raise ClockLedError(f"foreign/mixed clock LED input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "Modern clock digits need the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"clock LED site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied", "clock LED postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va),
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "HOOK", "GUARD", "BODY", "CX", "CY", "code_for", "sites", "allocation",
           "status", "apply"]
