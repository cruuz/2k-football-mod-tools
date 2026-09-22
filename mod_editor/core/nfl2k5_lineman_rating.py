"""EXPERIMENTAL / UNWITNESSED: the1wam's lineman rating adjustment for the game's own OVERALL.

the1wam (#nfl2k28-softdrink-edition-mod, 2026-09-21/22) is building rosters and the game's
OVERALL moves with height and weight, "the only thing that's messing me up". His rule, for
offensive linemen and for the overall number only, never for gameplay:

    any offensive lineman 326 lb and above is calculated as 294 lb
    any offensive lineman 325 lb and below is calculated as 317 lb

Research: where the overall comes from
-------------------------------------
Retail ``default.xbe`` computes the displayed OVR in three routines. All addresses are Xbox
virtual addresses; the player record in memory is the 0x54-byte ROST record itself (position
at +0x35, weight at +0x2A stored as pounds minus 150, height at +0x2B in inches, the 28
rating bytes from +0x36).

``FUN_00246d90`` -> displayed integer::

    OVR = round(100 * FUN_00246d80(player))          ; fadd/fsub 0.5 then cvttss2si at 0x245960

``FUN_00246d80`` -> ``edx = [player+0x35]`` then ``FUN_00246d60``; ``FUN_00246d60`` looks the
position's rating profile up in the 17-entry pointer table at ``0x00AC4948`` (``mov ebx,
[edx*4+0xac4948]``) and tail-calls ``FUN_00246c00`` with it.

``FUN_00246c00`` -> the profile blend::

    profile = {float base, float span, int n, entry* rows}     ; rows are 4 bytes: w, lo, hi, attr
    avg     = SUM(w * (V(attr)*100 - lo) / (hi - lo)) / SUM(w)
    OVR01   = clamp01((avg - base) * 0.7 / span + 0.3)         ; 0.7 at 0x4EFE08, 0.3 at 0x4EFE0C

``FUN_00246a80`` -> one derived attribute ``V(attr)``, from the 15-entry descriptor table at
``0x00AC47C0`` (pairs of ``{int slots, descriptor*}``)::

    M  = (SUM(w_i * rating_i/100) - 0.25 * A * (1 - consistency/100)) / SUM(w_i)
    F  = G*s + (1 - s) when s >= 0, else G*s + 1               ; s and G are descriptor fields
    V  = F*M + 0.005 * max(0, height - Href) + 0.001 * max(0, (weight_raw + 150) - Wref)

The height coefficient 0.005 is at ``0x004EFE40`` and the weight coefficient 0.001 at
``0x004E63FC``; the reads are ``movzx eax,[ebx+0x2b]`` at ``0x00246B3F`` (height) and
``movzx edx,[ebx+0x2a]`` / ``add edx,0x96`` at ``0x00246B89`` (weight, +150).

So weight really does move the overall, and for the offensive line it is the only body term:

* ``C`` = 50% attribute 0 (lo 10, hi 74) + 50% attribute 1 (lo 10, hi 75), base 0.40 span 0.70
* ``G`` = 60% attribute 0 (10, 75) + 40% attribute 1 (10, 76)
* ``T`` = 40% attribute 0 (10, 78) + 60% attribute 1 (10, 80)
* attribute 0 = 0.1 agility + 0.4 strength + 0.5 run blocking, ``Href`` 1000, ``Wref`` 300
* attribute 1 = 0.05 speed + 0.15 agility + 0.3 strength + 0.5 pass blocking, ``Href`` 1000,
  ``Wref`` 290

``Href`` 1000 is larger than any legal height, so the height term is dead for C, G and T: an
offensive lineman's overall does not move with height at all. Weight above 300 (attribute 0)
and above 290 (attribute 1) adds 0.1 per pound to that attribute's 0-100 value, which is worth
roughly 0.15 OVR per pound once the profile divides by ``hi - lo`` and the base/span rescale
runs. A 72 strength / 68 run block / 66 pass block guard reads 69 at 294 lb, 72 at 317 lb and
73 at 326 lb; at 360 lb the same player reads 78.

The patch
---------
``FUN_00246c00`` has exactly one caller in the image, the ``call`` at ``0x00246D6E`` inside
``FUN_00246d60``, and every overall in the game goes through it. The patch retargets that one
call to a 47-byte wrapper in a dead cave. The wrapper, for the offensive line position codes
only, writes the substituted weight into the record, calls the retail routine unchanged, and
puts the real byte back before returning. A non-lineman takes a plain ``jmp`` to the retail
routine and no memory is read or written at all.

Nothing else reads the substituted value: collision physics, animation selection, commentary
and every other consumer of ``[player+0x2A]`` runs outside the window, which is what "only
the overall rating, not gameplay" asks for. The stored roster byte is never changed, so a
patched disc and a retail disc read each other's rosters unchanged.

Two pinned .text spans, no new data, no image growth. Unwitnessed in game.
"""

from __future__ import annotations

import struct
from typing import Mapping

from . import nfl2k5_rdata_sites as rdata

# --- the research, pinned for the report and for the tests (never written) -------------------
OVERALL_DISPLAY_VA = 0x00246D90      # round(100 * overall)
OVERALL_ENTRY_VA = 0x00246D80        # overall(player): edx = [player+0x35]
OVERALL_DISPATCH_VA = 0x00246D60     # profile lookup + the only call to the blend
OVERALL_BLEND_VA = 0x00246C00        # the per-profile weighted blend
ATTRIBUTE_VA = 0x00246A80            # one derived attribute, where height and weight enter
POSITION_PROFILE_TABLE_VA = 0x00AC4948
ATTRIBUTE_TABLE_VA = 0x00AC47C0
HEIGHT_READ_VA = 0x00246B3F          # movzx eax, byte ptr [ebx+0x2b]
WEIGHT_READ_VA = 0x00246B89          # movzx edx, byte ptr [ebx+0x2a] ; add edx, 0x96
HEIGHT_COEFFICIENT_VA = 0x004EFE40   # 0.005 per inch over Href
WEIGHT_COEFFICIENT_VA = 0x004E63FC   # 0.001 per pound over Wref
HEIGHT_COEFFICIENT = 0.005
WEIGHT_COEFFICIENT = 0.001
# (attribute, Href inches, Wref pounds) for the two attributes an offensive line profile uses.
LINE_ATTRIBUTE_REFERENCES = ((0, 1000.0, 300.0), (1, 1000.0, 290.0))

# --- the record fields the wrapper touches ---------------------------------------------------
WEIGHT_FIELD = 0x2A                  # pounds - 150
POSITION_FIELD = 0x35
WEIGHT_BIAS = 150

# --- the1wam's rule --------------------------------------------------------------------------
LINE_POSITION_CODES = (12, 13, 14)   # C, G, T
HEAVY_FROM_LB = 326
HEAVY_READS_LB = 294
LIGHT_READS_LB = 317
HEAVY_FROM_RAW = HEAVY_FROM_LB - WEIGHT_BIAS     # 176
HEAVY_READS_RAW = HEAVY_READS_LB - WEIGHT_BIAS   # 144
LIGHT_READS_RAW = LIGHT_READS_LB - WEIGHT_BIAS   # 167


class LinemanRatingError(ValueError):
    """The executable does not carry the retail overall dispatch or the retail cave."""


def substituted_weight(position: int, weight: int) -> int:
    """The weight the patched overall reads, in pounds. Non-linemen keep their own weight."""

    if int(position) not in LINE_POSITION_CODES:
        return int(weight)
    return HEAVY_READS_LB if int(weight) >= HEAVY_FROM_LB else LIGHT_READS_LB


def substituted_weight_raw(position: int, weight_raw: int) -> int:
    """The same rule on the stored byte (pounds minus 150), which is what the cave compares."""

    if int(position) not in LINE_POSITION_CODES:
        return int(weight_raw)
    return HEAVY_READS_RAW if int(weight_raw) >= HEAVY_FROM_RAW else LIGHT_READS_RAW


# --- the two patched spans -------------------------------------------------------------------
# FUN_00246d60 as shipped. The whole routine is pinned so the profile table address and the
# calling convention are checked with the call target; only the call's rel32 moves.
HOOK_VA = OVERALL_DISPATCH_VA
RETAIL_HOOK = bytes.fromhex("8b442404538b1c954849ac005051e88dfeffff5bc20400")
HOOK_CALL_OFFSET = 0x0E              # the `call rel32` inside RETAIL_HOOK
assert RETAIL_HOOK[HOOK_CALL_OFFSET] == 0xE8 and len(RETAIL_HOOK) == 0x17

# 0x1D2400..0x1D2440: four 16-byte-aligned `mov eax,[eax+imm8]; ret` accessor stubs that no
# call, jump or dword anywhere in the image reaches (scan 2026-09-22: every E8/E9 rel32 in
# every section and every dword at every file offset). They sit inside a 464-byte dead run
# from 0x1D23C1 (the `ret 0xc` of FUN_001d2390 ends at 0x1D23C1) to 0x1D2591, and the cave
# reservation manifest claims none of it.
CAVE_VA = 0x001D2400
CAVE_SIZE = 0x40
RETAIL_CAVE = bytes.fromhex(
    "8b400cc3" "909090909090909090909090"       # mov eax,[eax+0x0c] ; ret ; alignment padding
    "8b4014c3" "909090909090909090909090"       # mov eax,[eax+0x14] ; ret ; alignment padding
    "8b4014c3" "909090909090909090909090"       # mov eax,[eax+0x14] ; ret ; alignment padding
    "8b4014c3" "909090909090909090909090"       # mov eax,[eax+0x14] ; ret ; alignment padding
)
assert len(RETAIL_CAVE) == CAVE_SIZE


def _rel32(source_end: int, target: int) -> bytes:
    return struct.pack("<i", target - source_end)


def cave_code(cave_va: int = CAVE_VA) -> bytes:
    """The wrapper, assembled at ``cave_va``.

    ``FUN_00246d60`` reaches it with ``ecx`` = the player, ``ebx`` = the rating profile,
    ``edx`` = the position the profile was chosen with, and the blend's two arguments already
    pushed (``[esp+4]`` player, ``[esp+8]`` the injury-mode flag). It must return the blend's
    float on the FPU stack and pop those two arguments, exactly like ``FUN_00246c00``.

        sub edx,12 ; cmp edx,2 ; ja .plain      ; C=12, G=13, T=14 and nothing else
        push ecx                                ; the player, for the restore
        mov al,[ecx+0x2a] ; push eax            ; the real stored weight byte
        mov dl,167 ; cmp al,176 ; jb .store     ; 317 lb unless the byte says 326 lb or more
        mov dl,144
      .store:
        mov [ecx+0x2a],dl                       ; the substitution, live only over the call
        push [esp+0x10] ; push ecx              ; the blend's own two arguments, unchanged
        call FUN_00246c00
        pop eax ; pop ecx ; mov [ecx+0x2a],al   ; the real byte back, byte for byte
        ret 8
      .plain:
        jmp FUN_00246c00                        ; not a lineman: retail, with nothing touched
    """

    body = bytearray()
    body += bytes.fromhex("83ea0c")                                   # sub edx, 12
    body += bytes.fromhex("83fa02")                                   # cmp edx, 2
    ja_at = len(body)
    body += b"\x77\x00"                                               # ja .plain (patched below)
    body += b"\x51"                                                   # push ecx
    body += bytes((0x8A, 0x41, WEIGHT_FIELD))                         # mov al, [ecx+0x2a]
    body += b"\x50"                                                   # push eax
    body += bytes((0xB2, LIGHT_READS_RAW))                            # mov dl, 167
    body += bytes((0x3C, HEAVY_FROM_RAW))                             # cmp al, 176
    body += b"\x72\x02"                                               # jb .store
    body += bytes((0xB2, HEAVY_READS_RAW))                            # mov dl, 144
    body += bytes((0x88, 0x51, WEIGHT_FIELD))                         # .store: mov [ecx+0x2a], dl
    body += bytes.fromhex("ff742410")                                 # push dword [esp+0x10]
    body += b"\x51"                                                   # push ecx
    body += b"\xe8" + _rel32(cave_va + len(body) + 5, OVERALL_BLEND_VA)
    body += b"\x58\x59"                                               # pop eax ; pop ecx
    body += bytes((0x88, 0x41, WEIGHT_FIELD))                         # mov [ecx+0x2a], al
    body += bytes.fromhex("c20800")                                   # ret 8
    plain_at = len(body)
    body[ja_at + 1] = plain_at - (ja_at + 2)
    body += b"\xe9" + _rel32(cave_va + len(body) + 5, OVERALL_BLEND_VA)
    if len(body) > CAVE_SIZE:
        raise LinemanRatingError(f"lineman-rating cave is {len(body)} bytes, over {CAVE_SIZE}")
    return bytes(body)


def cave_bytes(cave_va: int = CAVE_VA) -> bytes:
    code = cave_code(cave_va)
    return code + b"\xcc" * (CAVE_SIZE - len(code))


def patched_hook(cave_va: int = CAVE_VA) -> bytes:
    """The retail routine with its one call retargeted at the cave; four bytes move."""

    out = bytearray(RETAIL_HOOK)
    end = HOOK_VA + HOOK_CALL_OFFSET + 5
    out[HOOK_CALL_OFFSET + 1: HOOK_CALL_OFFSET + 5] = _rel32(end, cave_va)
    return bytes(out)


PATCHED_HOOK = patched_hook()
PATCHED_CAVE = cave_bytes()
CODE_BYTES = len(cave_code())

# Only the call target moves at the hook, and the retail call really did point at the blend.
assert PATCHED_HOOK[:HOOK_CALL_OFFSET + 1] == RETAIL_HOOK[:HOOK_CALL_OFFSET + 1]
assert PATCHED_HOOK[HOOK_CALL_OFFSET + 5:] == RETAIL_HOOK[HOOK_CALL_OFFSET + 5:]
assert (HOOK_VA + HOOK_CALL_OFFSET + 5
        + struct.unpack_from("<i", RETAIL_HOOK, HOOK_CALL_OFFSET + 1)[0]) == OVERALL_BLEND_VA
assert (HOOK_VA + HOOK_CALL_OFFSET + 5
        + struct.unpack_from("<i", PATCHED_HOOK, HOOK_CALL_OFFSET + 1)[0]) == CAVE_VA

UI_LABEL = "the1wam lineman rating adjustment"
HELP_TEXT = ("Retail: the game's own OVERALL adds 0.1 rating point per pound over 300 lb (run "
             "blocking) and over 290 lb (pass blocking), so a heavier lineman reads higher for "
             "nothing but his weight. Patch: while the overall for a Center, Guard or Tackle is "
             "being computed, a lineman of 326 lb or more counts as 294 lb and a lineman of "
             "325 lb or less counts as 317 lb. Only the overall changes: the stored weight, "
             "blocking, collisions, animation and commentary all keep the real number, and the "
             "roster file is untouched. EXPERIMENTAL / UNWITNESSED.")
BUILD_CAPTION = "the1wam lineman rating adjustment"


def sites() -> list[tuple[str, int, bytes, bytes]]:
    return [("overall_dispatch", HOOK_VA, RETAIL_HOOK, PATCHED_HOOK),
            ("lineman_weight_cave", CAVE_VA, RETAIL_CAVE, PATCHED_CAVE)]


def revert_sites() -> list[tuple[str, int, bytes, bytes]]:
    """The exact inverse: patched bytes back to retail, same two spans."""

    return [(label, va, after, before) for label, va, before, after in sites()]


def status(payload: bytes) -> str:
    return rdata.status(payload, sites())


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    try:
        patched, receipt = rdata.apply(payload, sites(), "lineman-rating")
    except rdata.RdataSiteError as exc:
        raise LinemanRatingError(str(exc)) from exc
    return patched, {**receipt, "experimental": True, "witnessed": False, "label": UI_LABEL,
                     "rule": (f"position {LINE_POSITION_CODES}: >= {HEAVY_FROM_LB} lb reads as "
                              f"{HEAVY_READS_LB} lb, <= {HEAVY_FROM_LB - 1} lb reads as {LIGHT_READS_LB} lb"),
                     "scope": "the overall rating only; no gameplay reader of the weight changes",
                     "overall_dispatch": f"0x{HOOK_VA:x}", "overall_blend": f"0x{OVERALL_BLEND_VA:x}",
                     "attribute_routine": f"0x{ATTRIBUTE_VA:x}",
                     "weight_read": f"0x{WEIGHT_READ_VA:x}", "height_read": f"0x{HEIGHT_READ_VA:x}",
                     "cave": f"0x{CAVE_VA:x}..0x{CAVE_VA + CAVE_SIZE:x}", "cave_code_bytes": CODE_BYTES}


def revert(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Put the retail dispatch and the retail dead stubs back byte for byte."""

    state = status(payload)
    if state == "retail":
        return bytes(payload), {"already_applied": True, "edits": [], "changed_bytes": 0}
    try:
        reverted, receipt = rdata.apply(payload, revert_sites(), "lineman-rating revert")
    except rdata.RdataSiteError as exc:
        raise LinemanRatingError(str(exc)) from exc
    if status(reverted) != "retail":
        raise LinemanRatingError("lineman-rating revert did not restore the retail dispatch")
    return reverted, {**receipt, "reverted": True}


__all__ = ["ATTRIBUTE_TABLE_VA", "ATTRIBUTE_VA", "BUILD_CAPTION", "CAVE_SIZE", "CAVE_VA",
           "CODE_BYTES", "HEAVY_FROM_LB", "HEAVY_FROM_RAW", "HEAVY_READS_LB", "HEAVY_READS_RAW",
           "HEIGHT_COEFFICIENT", "HEIGHT_COEFFICIENT_VA", "HEIGHT_READ_VA", "HELP_TEXT",
           "HOOK_CALL_OFFSET", "HOOK_VA", "LIGHT_READS_LB", "LIGHT_READS_RAW",
           "LINE_ATTRIBUTE_REFERENCES", "LINE_POSITION_CODES", "LinemanRatingError",
           "OVERALL_BLEND_VA", "OVERALL_DISPATCH_VA", "OVERALL_DISPLAY_VA", "OVERALL_ENTRY_VA",
           "PATCHED_CAVE", "PATCHED_HOOK", "POSITION_FIELD", "POSITION_PROFILE_TABLE_VA",
           "RETAIL_CAVE", "RETAIL_HOOK", "UI_LABEL", "WEIGHT_BIAS", "WEIGHT_COEFFICIENT",
           "WEIGHT_COEFFICIENT_VA", "WEIGHT_FIELD", "WEIGHT_READ_VA", "apply", "cave_bytes",
           "cave_code", "patched_hook", "revert", "revert_sites", "sites", "status",
           "substituted_weight", "substituted_weight_raw"]
