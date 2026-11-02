"""PROVED OFFLINE: native play-call placement; DESIGN: 54 units above the sprite bar.

Owned by nfl2k5_scorebug_runtime, not a separate Build option. The initializer
sets the roots of the four offense nodes, four defense nodes and six coach
nodes. Native animation evaluation propagates those roots to the diagrams,
their viewport corners, the page/sub/flip strip and labels. The independent
LAST PLAY/Offense Chose cameras and the live preview rect move by the same
amount. No shared font, global HUD camera, resource or allocation is changed.
See PC_REPORT.md and tools/nfl2k5_playcall_projection.py for bounded proofs.

b780 p2-playcall, page strip: the strip of page boxes (FUN_000AAFD0) is left-anchored at the page text node (HUD x 42 + 65)
and draws one 10x14 box every 15 units. A 30-link formation has ten pages, so the strip ran 145 units and covered the
left of a long formation name ("SINGLEBACK BUNCH" starts at about x 190). From six pages up the call below moves the strip
45 units left (the 77 units between the arrow icon and the strip start are empty) and tightens the pitch so the whole
strip is at most about 116 units (pitch = the largest of 15 down to 4 with pitch * pages <= 116, box width = pitch - 4 kept
between 6 and 10). Five pages and fewer are exactly retail. Only the one `call 0x6D170` of the box loop is replaced.
"""
from __future__ import annotations

import hashlib
import struct

from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

SHIFT = 54.0
HOOK_NAME = "playcall_layout_init"
HOOK = (0xAC40C, bytes.fromhex("e8fff5f7ff"))  # final view setter in ABF60
STRIP_HOOK_NAME = "playcall_strip_fit"
STRIP_HOOK = (0xAB0C5, bytes.fromhex("e8a620fcff"))  # the page box draw (call 0x6D170) in FUN_000AAFD0's loop
# Page strip fit (b780 p2): retail pitch 15 and width 10 are kept up to FIT_FROM pages.
FIT_FROM = 6          # pages (last index + 1) from which the strip is fitted
STRIP_SHIFT = 45      # units the fitted strip moves left of its retail start
STRIP_TOTAL = 116     # pitch * pages never exceeds this; the strip ends about 170 units from the left edge
PITCH_MIN, PITCH_RETAIL = 4, 15
WIDTH_MIN, WIDTH_MAX, WIDTH_GAP = 6, 10, 4
# Global descriptor, exact retail node count, settled node root y before shift.
SCENES = ((0xB70C74, 4, 240.0), (0xB71988, 4, 240.0), (0xB719B8, 6, 240.0))
GUARDS = (
    (0xABED0, 133, "dfbcc7b57ec32d455bdb602dc868fd687d3b6e66edb2eaa2c59ae9d92c416a18", "offense and defense root initializer"),
    (0x69030, 334, "a1809f8c66f0100f0fb265740796e19916b951197682d8e11e7b4cf6628f217b", "menu camera initializer"),
    (0x5F460, 659, "2772897ae0d0b7ed2669bae3eeb70bb59e17ea86913ba0b6dbc0e82e00b4221a", "preview target mapping"),
    (0x66670, 160, "5e2680d7dfd2a5a146f95a8721c88df67c696d878fc9eb513a12755b3cc12673", "active picture inset"),
    (0x4F0318, 4, "7860020e90116183228640760ff7502f4df0088992b456e3f0d7b44c9950db7e", "retail root y"),
    (0xABF60, 1205, "32daf767df8af0fef76882c0e461d7e2053f2624eb6c261810d0120a34a06a20", "scene initializer"),
    (0xAA440, 75, "599d1697be97636d999ccf271f115de0cae90e36f37414dfcc24fd19523a72c6", "coach root initializer"),
    (0x71BB0, 97, "41d31ec2a9730a660a5dfbb8cec1272c4f11f37888a3ffec3935c5f66bd8a215", "card initializer"),
    (0x72266, 214, "c1223f05e694022971131c84cf7a9938883a54d908ab1447085b42b06aa964c1", "preview rectangle"),
    (0x2BA10, 160, "4eff56204ee57a5d0eb8052c71e2db9446447277ba8899561233ea49a71b683d", "camera view setter"),
    (0x2F010, 32, "17438e39b4ff9845f28c889cb1f358f6b7e1d09944760049e77cb095d7a40628", "animation setter"),
    (0xAAFD0, 340, "d4b7845f9340cf3c68246181bac5bed03c9b12e23a015df12e16a53f4d8c6028", "page strip drawer"),
    (0x4E9630, 64, "8326b5e476d2cad39b7dcdf25ee6248d0bd906e60cd3f7a292b27e31a3e47183", "card camera basis"),
    (0x4F0DF0, 64, "8326b5e476d2cad39b7dcdf25ee6248d0bd906e60cd3f7a292b27e31a3e47183", "choose camera basis"),
    (0xA84AD0, 48, "9a19eff36ec473dbc46472f52ded82985eb9afcb164e95d88e1636b2f3f687f4", "preview rect table"),
)


def edits():
    """Six private data words. Preview order is y0,x0,y1,x1, NOT x0,y0,x1,y1."""
    rows = [(0x4E9664, 0.0, -SHIFT, "LAST PLAY / offense_chose_a camera y"),
            (0x4F0E24, 0.0, -SHIFT, "playcallframe_choose camera y")]
    # 66670 gives the world camera a 448-high physical target at y=16.
    # 72266..72337 preserves rect height and 5F634 maps y0 into that target.
    for va, value in ((0xA84AE0, .143), (0xA84AE8, .57),
                      (0xA84AF0, .56), (0xA84AF8, 1.0)):
        old = struct.unpack("<f", struct.pack("<f", value))[0]
        rows.append((va, old, old - SHIFT / 448.0, "play-call preview y endpoint"))
    return tuple((va, struct.pack("<f", old), struct.pack("<f", new), label)
                 for va, old, new, label in rows)


def valid(payload, *, applied, strip=True):
    """Pins plus exact six-word state; normalization never accepts a mixed edit.

    ``strip`` also normalizes the page strip hook (b780 p2): the retail XBE, a build with the strip fit and a build
    without it all read the same retail function there. The hook bytes themselves are checked by the owner's status.
    """
    image = XbeImage(payload)
    rows = edits()
    if any(image.read(va, 4) != (new if applied else old) for va, old, new, _ in rows):
        return False
    normal = [(HOOK[0], HOOK[1])] + [(va, old) for va, old, _, _ in rows]
    if strip:
        normal.append((STRIP_HOOK[0], STRIP_HOOK[1]))
    for start, size, digest, _ in GUARDS:
        buf = bytearray(image.read(start, size))
        for va, old in normal:
            if start <= va and va + len(old) <= start + size:
                buf[va-start:va-start+len(old)] = old
        if hashlib.sha256(buf).hexdigest() != digest:
            return False
    return True


def code_for(va):
    """Integer-only initializer, preserves GPRs/flags and tail-calls RET 12 native ABI.

    Absolute root assignments make reinitialization idempotent. Null or changed
    node-count scenes are skipped rather than walking a foreign resource layout.
    The native setter still runs exactly once with its original three arguments.
    """
    a = _Asm(va)
    a.b("9c 60")
    for i, (glob, count, original_y) in enumerate(SCENES):
        a.b("a1" + struct.pack("<I", glob).hex() + " 85c0")
        a.j8("74", f"next{i}")
        a.b("837824" + bytes([count]).hex())
        a.j8("75", f"next{i}")
        a.b("8b4028 85c0")
        a.j8("74", f"next{i}")
        a.b("b9" + struct.pack("<I", count).hex())
        a.label(f"node{i}")
        # 69030's menu camera maps world y to screen y + 16 (positive DOWN).
        # AA440 initializes ALL fourteen roots at y=240, including ABED0's nodes.
        a.b("c74054" + struct.pack("<f", original_y - SHIFT).hex())
        a.b("83c060 49")
        a.j8("75", f"node{i}")
        a.label(f"next{i}")
    a.b("61 9d")
    # A local call followed by RET would consume the original stack incorrectly.
    end = va + sum(a._size(item) for item in a.items)
    a.b("e9" + struct.pack("<i", 0x2BA10 - end - 5).hex())
    return a.assemble()


def fit(pages):
    """(shift, pitch, width) in HUD units for a strip of ``pages`` boxes, as the cave computes them."""
    if pages < FIT_FROM:
        return 0, PITCH_RETAIL, WIDTH_MAX
    pitch = PITCH_RETAIL
    while pitch * pages > STRIP_TOTAL and pitch > PITCH_MIN:
        pitch -= 1
    return STRIP_SHIFT, pitch, min(WIDTH_MAX, max(WIDTH_MIN, pitch - WIDTH_GAP))


def strip_code_for(va):
    """Replaces the page box draw's `call 0x6D170`; position x and width are rewritten, everything else is the native call.

    At entry: [esp] the return into the loop, [esp+4] x, +8 y, +12 z, +16 width, +20 height (floats), EBX the last page
    index, EDI the box index, ECX/EDX the two colours (kept). Pages below FIT_FROM go straight to the native box. For
    more, x moves left by STRIP_SHIFT + index * (15 - pitch) and the width becomes the fitted one. Integer EAX/ECX/EDX
    are saved; the native call keeps its stack and registers, and the tail jump leaves its RET to the loop.
    """
    a = _Asm(va)
    a.b("8d4301 83f8" + f"{FIT_FROM - 1:02x}")          # lea eax,[ebx+1]; cmp eax,5
    a.j8("76", "native")                                  # jbe: five pages or fewer are retail
    a.b("51 52")                                          # push ecx; push edx
    a.b("b9" + struct.pack("<I", PITCH_RETAIL).hex())     # mov ecx,15
    a.label("again")
    a.b("89ca 0faf d0 83fa" + f"{STRIP_TOTAL:02x}")      # mov edx,ecx; imul edx,eax; cmp edx,116
    a.j8("76", "fitted")                                  # jbe
    a.b("83f9" + f"{PITCH_MIN:02x}")                      # cmp ecx,4
    a.j8("76", "fitted")                                  # jbe: never tighter than 4
    a.b("49")                                             # dec ecx
    a.j8("eb", "again")
    a.label("fitted")                                     # ECX = pitch
    a.b("8d51" + f"{(-WIDTH_GAP) & 255:02x}")             # lea edx,[ecx-4]
    a.b("83fa" + f"{WIDTH_MAX:02x}")
    a.j8("76", "min")                                     # jbe: at most 10
    a.b("ba" + struct.pack("<I", WIDTH_MAX).hex())
    a.label("min")
    a.b("83fa" + f"{WIDTH_MIN:02x}")
    a.j8("73", "width")                                   # jae: at least 6
    a.b("ba" + struct.pack("<I", WIDTH_MIN).hex())
    a.label("width")                                      # EDX = width
    a.b("b8" + struct.pack("<I", PITCH_RETAIL).hex() + "29c8 0faf c7 83c0" + f"{STRIP_SHIFT:02x}")
    #   mov eax,15; sub eax,ecx; imul eax,edi; add eax,45     (the left shift of this box)
    a.b("50 d9442410 da2424 d95c2410 58")                 # push eax; fld [x]; fisub [esp]; fstp [x]; pop eax
    a.b("52 db0424 d95c241c 5a")                          # push edx; fild [esp]; fstp [width]; pop edx
    a.b("5a 59")                                          # pop edx; pop ecx
    a.label("native")
    a.jmp_abs(0x6D170)
    return a.assemble()
