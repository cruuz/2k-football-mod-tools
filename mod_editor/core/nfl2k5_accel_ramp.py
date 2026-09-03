"""Give NFL 2K5 players an acceleration ramp (executable patch, xemu-only, local research).

Retail has no acceleration model: every locomotion consumer (top speed ``FUN_00238020``, the
run-animation rate, pursuit maths) reads the player's *effective Speed rating* that
``FUN_00075bd0`` caches into ``state+0x1b4`` every frame from the attribute accessor.  A
lineman and a receiver therefore both reach their top speed on the first frame, which is why
"everyone goes step for step" at high Pursuit.

This patch redirects that one cache write (``0x00075CD5``: ``mov [esi+0x1b4], edx``) into a
code cave in the XBE boot-logo bitmap.  The cave ramps the cached value instead of copying it:

    throttle = [[player+0x0C]+0x10]           (the steer record's speed command, 0..1)
    idle  (throttle < 0.15):  cached = 0.6 * rating
    moving:                   cached = min(rating, max(prev + step, 0.6 * rating))
    step  = rating * 0.006667 / (2.5 - 1.5 * agility)       per 60 Hz frame

so a 99-agility receiver climbs from 60 % to 100 % of his rating in about one second, a
50-agility lineman in about 1.75 s, a 30-agility one in two seconds; slow, low-agility
quarterbacks cannot burst out of the pocket.  If the steer record is missing (0 or -1) the
retail value is stored unchanged, so nothing can break for players the game does not steer.
The ramp also lowers the run-animation rate while accelerating (it reads the same cache), which
is the visible "winding up".

Everything is pattern-checked (retail or already-applied bytes only), the ``.text`` digest is
recomputed, the header logo bytes carry no digest.  Constants live in the logo region too.
Unverified at runtime (Noah tests): the human steer record is assumed to hold the stick
magnitude at +0x10 like the AI's throttle does.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

IMAGE_BASE = 0x10000
HOOK_VA = 0x00075CD5                 # mov dword ptr [esi+0x1b4], edx  (6 bytes)
CONST_VA = 0x00010A48                # five floats: 0.15, 1.5, 2.5, 0.006667, 0.6
CAVE_VA = 0x00010A60                 # code
CONSTS = (0.15, 1.5, 2.5, 0.4 / 60.0, 0.6)
STATE_SPEED = 0x1B4
STATE_AGILITY = 0x1B8
PLAYER_STEER = 0x0C
STEER_THROTTLE = 0x10

RETAIL_HOOK = bytes.fromhex("8996b4010000")
# retail boot-logo bytes from file 0xA48 (VA 0x10A48) onward
_RETAIL_LOGO_FROM_A48 = bytes.fromhex(
    "03ff0305ff332e00037a00035200f93303f9030f33ff030343ff13f913050393a3f7730773a7632353a30513a3d3f7"
    "7303071373e3f7e3a3130903a3f7e39313054353f95373f9b333032363030593ff4303e3ff33f9030343e3fdb305f9"
    "d3f5d303a3ffe303037326f0130523e3ff630336f0132333c36305d3ff45ffa393f7e3036326f04303ff73d3f9b3f9"
    "7313f95313e3f7930323f9e3d3f9d336f00323638363030322f043e3ff43d3f79323f9a30323f7b33332f0"
)


class AccelRampError(ValueError):
    """The acceleration-ramp patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AccelRampError(message)


def _rel32(src: int, dst: int) -> bytes:
    return struct.pack("<i", dst - (src + 5))


def const_bytes() -> bytes:
    return struct.pack("<5f", *CONSTS)


def cave_bytes() -> bytes:
    c_idle, c_15, c_25, c_step, c_floor = (CONST_VA + 4 * i for i in range(5))
    m = lambda va: struct.pack("<I", va)  # noqa: E731
    code = b""
    code += b"\x52"                                   # push edx              ; [esp] = rating bits
    code += b"\x8b\x43" + bytes([PLAYER_STEER])       # mov eax,[ebx+0xc]     ; steer record
    code += b"\x85\xc0"                               # test eax,eax
    code += b"\x74\x00"                               # jz fallback (patched below)
    j_fallback_1 = len(code) - 1
    code += b"\x83\xf8\xff"                           # cmp eax,-1
    code += b"\x74\x00"                               # je fallback (patched below)
    j_fallback_2 = len(code) - 1
    code += b"\x83\x38\xff"                           # cmp dword [eax],-1    ; the game's "not steered" marker
    code += b"\x74\x00"                               # je fallback (patched below)
    j_fallback_3 = len(code) - 1
    code += b"\xd9\x04\x24"                           # fld dword [esp]       ; st0 = rating (T)
    code += b"\xd9\x40" + bytes([STEER_THROTTLE])     # fld dword [eax+0x10]  ; st0 = throttle, st1 = T
    code += b"\xd9\x05" + m(c_idle)                   # fld [0.15]            ; st0 = 0.15, st1 = thr, st2 = T
    code += b"\xde\xd9"                               # fcompp                ; 0.15 ? thr ; pops both
    code += b"\xdf\xe0"                               # fnstsw ax
    code += b"\xf6\xc4\x01"                           # test ah,1             ; C0 = (0.15 < thr) -> moving
    code += b"\x74\x00"                               # jz idle (patched below)
    j_idle = len(code) - 1
    # moving: st0 = T
    code += b"\xd9\x86" + struct.pack("<I", STATE_SPEED)     # fld [esi+0x1b4]   ; st0 = prev, st1 = T
    code += b"\xd9\x05" + m(c_15)                     # fld 1.5               ; st0 = 1.5, st1 = prev, st2 = T
    code += b"\xd8\x8e" + struct.pack("<I", STATE_AGILITY)   # fmul [esi+0x1b8]  ; 1.5*ag
    code += b"\xd8\x2d" + m(c_25)                     # fsubr [2.5]           ; 2.5 - 1.5*ag
    code += b"\xd8\x3d" + m(c_step)                   # fdivr [0.006667]      ; 0.006667 / (...)
    code += b"\xd8\xca"                               # fmul st0,st2          ; * T = step
    code += b"\xde\xc1"                               # faddp st1,st0         ; st0 = prev+step, st1 = T
    code += b"\xdb\xf1"                               # fcomi st0,st1         ; CF = (prev+step < T)
    code += b"\x72\x04"                               # jb keep (+4)
    code += b"\xdd\xd8"                               # fstp st0              ; drop -> st0 = T
    code += b"\xd9\xc0"                               # fld st0               ; st0 = T, st1 = T
    # keep: st0 = new, st1 = T
    code += b"\xd9\xc1"                               # fld st1               ; st0 = T, st1 = new, st2 = T
    code += b"\xd8\x0d" + m(c_floor)                  # fmul [0.6]            ; st0 = 0.6T
    code += b"\xdb\xf1"                               # fcomi st0,st1         ; CF = (0.6T < new)
    code += b"\x72\x04"                               # jb usenew (+4)
    code += b"\xdd\xd9"                               # fstp st1              ; st0 = 0.6T, st1 = T
    code += b"\xeb\x02"                               # jmp store (+2)
    code += b"\xdd\xd8"                               # usenew: fstp st0      ; st0 = new, st1 = T
    code += b"\xd9\x9e" + struct.pack("<I", STATE_SPEED)     # store: fstp [esi+0x1b4]
    code += b"\xdd\xd8"                               # fstp st0              ; pop T
    code += b"\x5a"                                   # pop edx
    code += b"\xc3"                                   # ret
    idle = len(code)
    code += b"\xd8\x0d" + m(c_floor)                  # idle: fmul [0.6]      ; st0 = 0.6T
    code += b"\xd9\x9e" + struct.pack("<I", STATE_SPEED)     # fstp [esi+0x1b4]
    code += b"\x5a"                                   # pop edx
    code += b"\xc3"                                   # ret
    fallback = len(code)
    code += b"\x5a"                                   # fallback: pop edx
    code += b"\x89\x96" + struct.pack("<I", STATE_SPEED)     # mov [esi+0x1b4], edx (retail behaviour)
    code += b"\xc3"                                   # ret
    code = bytearray(code)
    code[j_fallback_1] = fallback - (j_fallback_1 + 1)
    code[j_fallback_2] = fallback - (j_fallback_2 + 1)
    code[j_fallback_3] = fallback - (j_fallback_3 + 1)
    code[j_idle] = idle - (j_idle + 1)
    return bytes(code)


PATCHED_HOOK = b"\xe8" + _rel32(HOOK_VA, CAVE_VA) + b"\x90"


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise AccelRampError(f"VA 0x{va:x} is in no section")


def _retail_logo(va: int, length: int) -> bytes:
    start = va - 0x10A48
    _require(0 <= start and start + length <= len(_RETAIL_LOGO_FROM_A48), "cave outside the recorded logo bytes")
    return _RETAIL_LOGO_FROM_A48[start: start + length]


def _sites(payload: bytes) -> list[tuple[str, int, bytes, bytes]]:
    cave = cave_bytes()
    consts = const_bytes()
    _require(CONST_VA + len(consts) <= CAVE_VA, "constants overlap the cave")
    _require(CAVE_VA + len(cave) <= 0x10CC2, "cave overruns the boot-logo bitmap")
    return [
        ("constants", _offset(payload, CONST_VA), _retail_logo(CONST_VA, len(consts)), consts),
        ("cave", _offset(payload, CAVE_VA), _retail_logo(CAVE_VA, len(cave)), cave),
        ("hook", _offset(payload, HOOK_VA), RETAIL_HOOK, PATCHED_HOOK),
    ]


def status(payload: bytes) -> str:
    """'retail', 'applied', or 'foreign'."""

    try:
        sites = _sites(payload)
    except (AccelRampError, ValueError, struct.error):
        return "foreign"
    states = set()
    for _label, off, before, after in sites:
        got = payload[off: off + len(before)]
        states.add("retail" if got == before else "applied" if got == after else "foreign")
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    state = status(payload)
    _require(state == "retail", f"acceleration-ramp sites are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    edits = []
    header = _header_size(payload)
    for label, off, before, after in _sites(payload):
        buf[off: off + len(after)] = after
        if off >= header:
            touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "file_offset": f"0x{off:x}", "before": before.hex(), "after": after.hex()})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied", "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {"edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched),
                     "cave_bytes": len(cave_bytes())}


__all__ = ["AccelRampError", "CAVE_VA", "CONST_VA", "HOOK_VA", "apply", "cave_bytes", "const_bytes", "status"]
