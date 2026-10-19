"""Super Bowl booth welcome for the 17 Super Bowl Anniversary moments. EXPERIMENTAL / UNWITNESSED.

Noah, 2026-10-17 and 2026-10-18: "the commentary should be aware that these specific moments are the Super Bowl."

How the booth picks Super Bowl lines (static RE, b776 job sbc)
-------------------------------------------------------------
* Speech is keyed. The SPCI index resource "lines" (outer 3, next to the lines AUSB bank) maps a 16-bit phrase key to
  a lines.bin stream; 0x13CBA0 is the lookup. The in-game director (DRCT outer 4) says a key with command 0x9F
  (big-endian u16 operand, handler 0x59010 -> 0x582F0 -> enqueue 0xC3540 on the booth queue 0xB28A70).
* Each director event (fixed slot) chooses among its children with a decision tree (0x269750) over DRCT
  expressions. Expression 107 of the in-game director is variable 429, the game type 0x65D30.
* The in-game Super Bowl lines and their gates (game type == 8 is required in every case):
  slot 46 child 12 "kicks it off and the Super Bowl is underway" (also needs the opening kickoff),
  slot 62 child 10 "fields the opening kick of the Super Bowl" (opening kickoff return),
  slot 113 (the booth intro) children 13/29/30/31 "welcome to ... Super Bowl XXXIX/XL/XLI/XLII" (year from the
  franchise) and 23/26/27/28 the coin-toss lead-ins,
  slot 169 child 28 the end-of-game sequence "and this one is in the books / a couple class acts down there, great
  coaches / and there he is, our Super Bowl MVP / let the party begin / it's official, that wraps it up for this year".
  No play-by-play or colour line during play depends on the game type except the Pro Bowl ("all stars") names.
* mo2 (nfl2k5_moment_context) makes 0x65D30 return 8 in the 17 Super Bowl rows, so the end-of-game sequence already
  plays there (heard in Noah's 10/18 video at the end of SB XLII). A moment never has an opening kickoff, and the
  presentation start 0x67E80 skips the booth intro event 113 in game mode 8, so a moment never gets a welcome.

This owner adds the one Super Bowl line that fits a moment start: at 0x67E80, for game mode 8 with the situation flag
0 (an Anniversary moment) and one of the 17 Super Bowl rows, and only while the booth is on (0xB28A60), it queues
phrase key 14051 (lines.bin 1483, Dan Stevens: "Hi there, I'm Dan Stevens, and welcome to the Super Bowl, here on
ESPN") exactly the way the director's own say command does. Every other mode, every other moment and the Situation
mode run the retail instructions unchanged. No director data, speech bank or franchise state changes.

XBE space: the code lives in an unreferenced retail function (0x201D50..0x201E2A: no rel8/rel32 encoding at any byte
offset of any executable section and no absolute dword in any section points into it, on the retail and the b775
executables), pinned by its retail sha256. No allocator request.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct

from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_moment_context import SUPER_BOWL_ROWS, super_bowl_mask

OWNER = "nfl2k5_moment_booth"
REQUESTS = ()
CAVE_VA = 0x201D50
CAVE_SIZE = 0xDA
RETAIL_CAVE_SHA256 = "763d04c13276690634c53eb360e0737672ea6a64eb04832beb7e1a6cb693de01"

HOOK_VA = 0x67EE6
HOOK_RETAIL = bytes.fromhex("a180ffe500")    # mov eax,[0xE5FF80]  (presentation start, before the mode-8 skip)
HOOK_BACK = 0x67EEB                          # cmp eax,8; je 0x67F2C
MODE, SITUATION_FLAG, MOMENT = 0xE5FF80, 0xE6014C, 0xBF1858
BOOTH_ON, BOOTH_QUEUE, ENQUEUE = 0xB28A60, 0xB28A70, 0xC3540
WELCOME_KEY = 14051                          # lines.bin 1483
WELCOME_LINE = 1483
UI_TEXT = ("EXPERIMENTAL / UNWITNESSED. With the more moments: the 17 Super Bowl moments open with Dan Stevens' "
           "\"welcome to the Super Bowl\" booth line.")


class MomentBoothError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise MomentBoothError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _imm(v):
    return struct.pack("<I", v & 0xFFFFFFFF)


def _rel(src_end, target):
    return struct.pack("<i", target - src_end)


def code_for(cave=CAVE_VA):
    """The cave bytes (padded with 0xCC to CAVE_SIZE) and its labels."""
    out = bytearray()
    labels = {}

    def emit(raw):
        out.extend(raw)

    def jcc8(op):
        emit(bytes([op, 0]))
        return len(out) - 1

    def here():
        return cave + len(out)

    labels["entry"] = here()
    emit(b"\xa1" + _imm(MODE))                          # mov eax,[mode]
    emit(b"\x83\xf8\x08")                               # cmp eax,8
    emit(b"\x0f\x85" + _rel(here() + 6, HOOK_BACK))     # jne retail (EAX = mode, nothing else touched)
    fix = []
    emit(b"\x83\x3d" + _imm(SITUATION_FLAG) + b"\x00")  # cmp dword [situation flag],0
    fix.append(jcc8(0x75))                              # jne done (the Situation mode)
    emit(b"\x8b\x0d" + _imm(MOMENT))                    # mov ecx,[selected row]
    emit(b"\x83\xf9\x40")                               # cmp ecx,64
    fix.append(jcc8(0x73))                              # jae done
    bt_at = len(out)
    emit(b"\x0f\xa3\x0d" + _imm(0))                     # bt [mask],ecx (patched below)
    fix.append(jcc8(0x73))                              # jnc done (not a Super Bowl row)
    emit(b"\x83\x3d" + _imm(BOOTH_ON) + b"\x00")        # cmp dword [booth on],0
    fix.append(jcc8(0x74))                              # je done (commentary off)
    emit(b"\x6a\xff\x6a\xff")                           # push -1; push -1
    emit(b"\x68" + _imm(WELCOME_KEY))                   # push key
    emit(b"\x33\xd2")                                   # xor edx,edx
    emit(b"\xb9" + _imm(BOOTH_QUEUE))                   # mov ecx,booth queue
    emit(b"\xe8" + _rel(here() + 5, ENQUEUE))           # call enqueue (ret 0xC), as the director's say command
    labels["done"] = here()
    for at in fix:
        rel = labels["done"] - (cave + at + 1)
        require(-128 <= rel <= 127, "rel8 out of range")
        out[at] = rel & 0xFF
    emit(b"\xb8" + _imm(8))                             # mov eax,8 (the mode the retail mode-8 path indexes)
    emit(b"\xe9" + _rel(here() + 5, HOOK_BACK))         # back to cmp eax,8; je 0x67F2C
    labels["mask"] = here()
    emit(struct.pack("<Q", super_bowl_mask()))
    out[bt_at + 3:bt_at + 7] = _imm(labels["mask"])
    require(len(out) <= CAVE_SIZE, "moment booth code exceeds its cave")
    labels["code_bytes"] = len(out)
    return bytes(out).ljust(CAVE_SIZE, b"\xcc"), labels


def hook_bytes():
    return b"\xe9" + _rel(HOOK_VA + 5, CAVE_VA)


def status(payload):
    try:
        image = XbeImage(payload)
        cave = image.read(CAVE_VA, CAVE_SIZE)
        hook = image.read(HOOK_VA, len(HOOK_RETAIL))
        if sha(cave) == RETAIL_CAVE_SHA256:
            require(hook == HOOK_RETAIL, "foreign moment booth hook")
            return "retail"
        require(cave == code_for()[0], "foreign moment booth cave")
        require(hook == hook_bytes(), "moment booth cave without its hook")
        return "applied"
    except (MomentBoothError, ValueError, KeyError, struct.error):
        return "foreign"


def view_edits(payload):
    """[(label, va, retail, installed)] once applied, for owners that hash a span containing one of these sites."""
    if status(payload) != "applied":
        return []
    return [("hook", HOOK_VA, HOOK_RETAIL, hook_bytes())]


def seal(out):
    for section in _sections(out):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(out, section)
    return bytes(out)


def apply(payload):
    initial = status(payload)
    require(initial != "foreign", "foreign moment booth installation; rebuild from base")
    if initial == "applied":
        return payload, dict(status="already_applied", changed_bytes=0)
    code, labels = code_for()
    out, image = bytearray(payload), XbeImage(payload)
    at = image.offset(CAVE_VA, CAVE_SIZE)
    out[at:at + CAVE_SIZE] = code
    at = image.offset(HOOK_VA, len(HOOK_RETAIL))
    require(bytes(out[at:at + len(HOOK_RETAIL)]) == HOOK_RETAIL, "moment booth hook site is not retail")
    out[at:at + len(HOOK_RETAIL)] = hook_bytes()
    result = seal(out)
    require(status(result) == "applied" and len(result) == len(payload), "moment booth readback")
    return result, dict(status="applied", changed_bytes=sum(x != y for x, y in zip(payload, result)),
                        cave_va=hex(CAVE_VA), hook_va=hex(HOOK_VA), code_bytes=labels["code_bytes"],
                        welcome_key=WELCOME_KEY, welcome_line=WELCOME_LINE, super_bowl_rows=list(SUPER_BOWL_ROWS))


def image_plan(target):
    """[(offset, bytes)] that install this owner in the disc image's default.xbe (only the differing runs)."""
    from .nfl2k5_music_archive import Disc
    with Disc(target, descriptors=()) as disc:
        e = disc.entries["default.xbe"]
        before = disc.read(e.size, e.byte_offset)
        after, receipt = apply(before)
        writes, i = [], 0
        while i < len(before):
            if before[i] == after[i]:
                i += 1
                continue
            start = i
            while i < len(before) and before[i] != after[i]:
                i += 1
            writes.append((e.byte_offset + start, after[start:i]))
    receipt["writes"] = [dict(offset=at, size=len(raw), sha256=sha(raw)) for at, raw in writes]
    return writes, receipt


def apply_to_image(target):
    """Install on a built copy; every write is read back and the replay must be empty."""
    from .nfl2k5_music_archive import write_all
    from . import platform_compat as io
    writes, receipt = image_plan(target)
    with Path(target).open("r+b") as f:
        for at, raw in writes:
            write_all(f.fileno(), raw, at)
            require(io.pread(f.fileno(), len(raw), at) == raw, "moment booth image readback")
        os.fsync(f.fileno())
    replay, _ = image_plan(target)
    require(not replay, "moment booth image replay must be empty")
    receipt["bytes_written"] = sum(len(raw) for _, raw in writes)
    return receipt


def image_status(target):
    from .nfl2k5_music_archive import Disc
    with Disc(target, descriptors=()) as disc:
        e = disc.entries["default.xbe"]
        return status(disc.read(e.size, e.byte_offset))


__all__ = ["OWNER", "REQUESTS", "CAVE_VA", "CAVE_SIZE", "HOOK_VA", "HOOK_RETAIL", "WELCOME_KEY", "WELCOME_LINE",
           "UI_TEXT", "apply", "status", "view_edits", "code_for", "hook_bytes", "image_plan", "apply_to_image",
           "image_status"]
