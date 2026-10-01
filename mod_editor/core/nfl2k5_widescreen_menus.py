"""Widescreen menus stay 4:3 (USA Xbox). EXPERIMENTAL / UNWITNESSED.

Noah's recording of 2026-09-23 [v1 1:17]: "the game's in widescreen now it's not perfect but as you can see it spills
over the left and right". Widescreen v3 (nfl2k5_widescreen) widens every full-width perspective camera (hor+) and
pillarboxes the 2D menu frames, so in the front end the 3D studio behind the menus fills 16:9 while the menu art,
drawn to bleed off the 4:3 edge, now ends in the middle of the picture.

This allocator owner makes the front end pillarbox those cameras too, so the menus look like the 4:3 original with
black bars; gameplay keeps hor+. The widescreen cave classifies every activated camera (FUN_0002AC80 copies the
source into the active camera A6AFC0, then calls the cave at 0x2ACA1); a camera stamped 'DIAG' at +0x24C is
pillarboxed. The call at 0x2ACA1 enters this owner first:
* front end: PLAY_STATE [0xE602B8] == 0 (measured in the lab: 0 at the main menu, Team Select and after quitting a
  moment; 5, 0xB, 0xD, 0xE or 0x12 in a game);
* the active camera is perspective ([+0x220] != 0) and full width (target x0 <= 40, 680 <= x1 <= 720, the
  cave's own "full" test);
unless the copy already carries the widescreen's 'NONE' exemption, it stamps the active copy 'DIAG' and continues
into the widescreen cave unchanged. Anything else goes straight
to the cave. The source camera is never written; the stamp pad is "written by the two constructors, read by
nothing" but the cave.

The word before the entry keeps the cave address the call replaced, so the widescreen recognizer reads the site
through ``views`` as its own hook.
"""
from __future__ import annotations

import struct

from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_widescreen_menus"
CODE_SIZE = 128
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
UI_LABEL = "Widescreen menus stay 4:3"
BUILD_CAPTION = "4:3 menus in widescreen"

PLAY_STATE_VA = 0xE602B8
ACTIVE_CAMERA_VA = 0xA6AFC0
PERSPECTIVE_VA = ACTIVE_CAMERA_VA + 0x220
TARGET_X0_VA = ACTIVE_CAMERA_VA + 0x250
TARGET_X1_VA = ACTIVE_CAMERA_VA + 0x260
STAMP_VA = ACTIVE_CAMERA_VA + 0x24C
X0_MAX = 0x42200000                  # 40.0f
X1_MIN = 0x442A0000                  # 680.0f
X1_MAX = 0x44340000                  # 720.0f
STAMP_DIAGRAM = 0x47414944           # 'DIAG' (nfl2k5_widescreen.STAMP_DIAGRAM)
STAMP_NONE = 0x454E4F4E              # 'NONE' (nfl2k5_widescreen.STAMP_NONE): exempt copies stay exempt


class WidescreenMenusError(ValueError):
    """Missing widescreen, a foreign hook, or a foreign allocation."""


def require(condition, message):
    if not condition:
        raise WidescreenMenusError(message)


def _widescreen():
    from . import nfl2k5_widescreen as widescreen
    return widescreen


def _u32(value):
    return struct.pack("<I", value & 0xFFFFFFFF)


def code_for(code_va, cave_va):
    """(bytes filling CODE_SIZE, entry VA). Layout: the replaced cave address, then the entry."""
    entry = code_va + 4
    body = bytearray(_u32(cave_va))
    tail = bytearray()
    # the conditional jumps land on the final `jmp cave`; sizes are fixed, so compute the offset at the end
    parts = [
        b"\x83\x3d" + _u32(PLAY_STATE_VA) + b"\x00", ("jne",),
        b"\x83\x3d" + _u32(PERSPECTIVE_VA) + b"\x00", ("je",),
        b"\x81\x3d" + _u32(TARGET_X0_VA) + _u32(X0_MAX), ("jg",),
        b"\x81\x3d" + _u32(TARGET_X1_VA) + _u32(X1_MIN), ("jl",),
        b"\x81\x3d" + _u32(TARGET_X1_VA) + _u32(X1_MAX), ("jg",),
        b"\x81\x3d" + _u32(STAMP_VA) + _u32(STAMP_NONE), ("je",),      # keep the fade tint's exemption
        b"\xc7\x05" + _u32(STAMP_VA) + _u32(STAMP_DIAGRAM),
    ]
    opcodes = {"jne": 0x75, "je": 0x74, "jg": 0x7F, "jl": 0x7C}
    size = sum(len(p) if isinstance(p, bytes) else 2 for p in parts)
    at = 0
    for p in parts:
        if isinstance(p, bytes):
            tail += p
            at += len(p)
        else:
            rel = size - (at + 2)
            tail += bytes((opcodes[p[0]], rel))
            at += 2
    jmp_at = entry + len(tail)
    tail += b"\xe9" + struct.pack("<i", cave_va - (jmp_at + 5))
    body += tail
    require(len(body) <= CODE_SIZE, "widescreen menus code exceeds its allocation")
    return bytes(body).ljust(CODE_SIZE, b"\xcc"), entry


def _allocation(payload):
    state = space.status(payload)
    if state == "retail":
        return None
    require(state == "applied", "the executable's extra-space layout is foreign")
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    if not rows:
        return None
    require(len(rows) == 1 and rows[0]["kind"] == "code" and rows[0]["size"] == CODE_SIZE,
            "foreign widescreen menus allocation")
    return rows[0]


def _hook(payload):
    w = _widescreen()
    image = XbeImage(payload)
    return image.read(w.HOOK_VA, 5)


def views(payload):
    """{0x2ACA1: the widescreen's own call bytes} when the call enters this owner, else {}."""
    try:
        alloc = _allocation(payload)
    except (ValueError, KeyError, IndexError, struct.error):
        return {}
    if alloc is None:
        return {}
    w = _widescreen()
    raw = _hook(payload)
    if raw[0] != 0xE8:
        return {}
    target = w.HOOK_VA + 5 + struct.unpack_from("<i", raw, 1)[0]
    if target != alloc["va"] + 4:
        return {}
    body = payload[alloc["raw"]:alloc["raw"] + CODE_SIZE]
    cave = struct.unpack_from("<I", body, 0)[0]
    expected, _entry = code_for(alloc["va"], cave)
    if body != expected:
        return {}
    return {w.HOOK_VA: b"\xe8" + struct.pack("<i", cave - (w.HOOK_VA + 5))}


def status(payload):
    """'retail' (no allocation contents, the call untouched), 'applied', or 'foreign'."""
    try:
        alloc = _allocation(payload)
        if alloc is None:
            return "retail"
        body = payload[alloc["raw"]:alloc["raw"] + CODE_SIZE]
        if body == b"\xcc" * CODE_SIZE:
            w = _widescreen()
            raw = _hook(payload)
            return "retail" if raw in (w.RETAIL_HOOK, w.PATCHED_HOOK) else "foreign"
        view = views(payload)
        if not view:
            return "foreign"
        w = _widescreen()
        return "applied" if view[w.HOOK_VA] == w.PATCHED_HOOK and w.status(payload) == "applied" else "foreign"
    except (WidescreenMenusError, ValueError, KeyError, IndexError, struct.error):
        return "foreign"


def apply(payload):
    """Install on an executable carrying widescreen v3, or replay an installed copy."""
    state = status(payload)
    require(state in ("retail", "applied"), f"widescreen menus are {state}")
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False, label=UI_LABEL, rx_bytes=CODE_SIZE)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    w = _widescreen()
    require(w.status(payload) == "applied", "install widescreen v3 first; the menus keep 4:3 only under widescreen")
    require(_hook(payload) == w.PATCHED_HOOK, "the camera activation call is not the widescreen's")
    if space.status(payload) == "retail":
        allocated, receipt = space.apply(payload, REQUESTS)
    else:
        require(_allocation(payload) is not None, "reserve the widescreen menus owner with the complete owner union")
        allocated, receipt = payload, {}
    alloc = _allocation(allocated)
    content, entry = code_for(alloc["va"], w.CODE_VA)
    result, _ = space.install_code(allocated, OWNER, content)
    image = XbeImage(result)
    buffer = bytearray(result)
    at = image.offset(w.HOOK_VA, 5)
    after = b"\xe8" + struct.pack("<i", entry - (w.HOOK_VA + 5))
    before = bytes(buffer[at:at + 5])
    buffer[at:at + 5] = after
    for section in _sections(buffer):
        buffer[section.header_offset + 36:section.header_offset + 56] = section_digest(buffer, section)
    result = bytes(buffer)
    require(status(result) == "applied", "widescreen menus postcondition failed")
    require(w.status(result) == "applied", "widescreen no longer reads as applied")
    return result, dict(common, status="applied", allocation=receipt,
                        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                        code_va=hex(alloc["va"]), entry=hex(entry),
                        edits=[dict(label="camera_activation_call", va=hex(w.HOOK_VA), size=5,
                                    before=before.hex(), after=after.hex()),
                               dict(label="owned_code", va=hex(alloc["va"]), size=CODE_SIZE)],
                        reservations=space.reservations(result))
