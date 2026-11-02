"""Quicker deep and rollout throws, USA retail (b780 c-release). EXPERIMENTAL / UNWITNESSED.

What the game does (reverse-engineered for b780 r1-cpu, checked again here with the real routines in Unicorn):
every quarterback throw plays a throw clip from one of 20 tables built into the executable.  The throw start
(``0x2DA370``, its rate switch at ``0x2DA516``) sets the clip's playback rate from the clip's type, which sits in the low
three bits of the clip descriptor, and from ``t81``, the clip time of animation event 81 (the ball release):

    type 1  every short and medium throw from the pocket   rate = 3 x t81      ball out 1/3 s after the start, always
    type 2  every throw on the run (rollouts, scrambles)    rate = clamp(3 x t81, 1.0, 1.2)   0.33 to 0.96 s
    type 3  the two very long bomb clips                    rate = 1.5                       0.73 s
    type 0  three on-the-run rows                           rate = 1.0                       0.44 to 0.77 s (unchanged here)

A second start (``0x2DA5D0``, used when the target changes mid-throw) restarts the clip at 1.5.  Once the throw is
under way the throw task (``0x2D85D0``, 15 ticks a second) eases the playback rate DOWN, 0.05 a tick, toward 1.0: at
once for a human who let go of the button (a lob), or toward ``1 + (rate - 1) x hold`` for a CPU throw.  It never raises
the rate.  Short and medium throws are past event 81 within 5 ticks, so for them the ease barely matters.

This owner changes constants only, nine sites in those three routines, no code, no cave, no allocation:

    type 3 start rate            1.5 -> 2.0   (``mov eax, imm32`` at 0x2DA52F)
    type 2 rate cap              1.2 -> 1.6   (``push imm32`` at 0x2DA539)
    restart rate                 1.5 -> 2.0   (``push imm32`` at 0x2DA666 and the stored copy at 0x2DA678)
    ease target for lobs         1.0 -> 1.5   (three ``mov ebx, imm32`` at 0x2D8652, 0x2D8668, 0x2D86EC)
    CPU ease blend base          1.0 -> 1.5   (the ``fsub`` / ``fadd`` operands at 0x2D86C0 and 0x2D86D6 now point at
                                               the retail 1.5 at 0x4E6D0C instead of the 1.0 at 0x4E419C)

Type 1 and type 0 starts are untouched, so a short or medium throw from the pocket keeps its exact 1/3 s release.
The bullet hold (the clip is held at event 80 while a human holds the button), the hold fraction (counted in ticks), the
ball launch (solved at the release moment from the release position) and every rating are rate independent and
unchanged.  A faster clip only shortens the wind-up.  Seconds from the start of the throw to the ball leaving the hand,
from the real routines in Unicorn over all 204 clips (tests/mod_editor/test_nfl2k5_quick_long_release_unicorn.py; one
frame, 1/15 s, either way depending on whether the tick or the clip runs first in a frame):

    two bomb clips (type 3)   button held 0.73 -> 0.54   button tapped 0.91 -> 0.61   CPU lob 0.83 -> 0.58
    146 clips on the run      held, median 0.42 -> 0.33, slowest 0.96 -> 0.72   tapped, median 0.47 -> 0.34, slowest 1.12 -> 0.76
    pocket throws (type 1)    0.333 -> 0.333 held; a tapped one eases 0.35 -> 0.35 (at most 0.03 s sooner)
    plain on-the-run rows (type 0, 14 clips)   unchanged

No clip, hold or passer is ever slower.  Human and CPU passers share these routines.

Every site and every routine around it is pinned by SHA-256 against the retail bytes (the three throw routines, the
min and max helpers the rate clamp calls, and the constants 1.0, 1.5, 3.0 and 0.05 the sites read), so a foreign or
half-edited executable is refused instead of patched.  No other owner guards or edits these bytes (qb_accuracy guards the
lead solver at 0x2DA8E0 and the release at 0x2DAF10, which start after them).
"""
from __future__ import annotations

import hashlib
import struct

from .nfl2k5_bump_strength import _section_for_offset, _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_quick_long_release"
BUILD_CAPTION = "Quicker deep and rollout throws (experimental)"
HELP_TEXT = ("EXPERIMENTAL / UNWITNESSED. Quarterbacks get the ball out faster on the longest bombs and on throws "
             "while running: rollouts, scrambles and throws on the move. A very long bomb leaves the hand a fifth to "
             "a third of a second sooner, and a throw on the run that took up to a full second or more now takes at "
             "most about three quarters of one, most of them the same third of a second a pocket throw already takes. "
             "Short and medium throws from the pocket, how far and how accurately the ball goes, catching and every "
             "rating are unchanged. Human and CPU passers both get the quicker arm. Not yet tested in the game by a player.")
REQUESTS = ()                     # constants only: no executable cave, data or file growth

# The four numbers this owner picks (everything else is retail).
DEEP_LOB_RATE = 2.0               # type 3 start rate and the restart rate (retail 1.5)
ROLLOUT_RATE_CAP = 1.6            # type 2 rate clamp maximum (retail 1.2)
EASE_FLOOR = 1.5                  # the rate a lob eases down to (retail 1.0); must equal the retail constant at 0x4E6D0C
RETAIL_DEEP_LOB_RATE, RETAIL_ROLLOUT_RATE_CAP, RETAIL_EASE_FLOOR = 1.5, 1.2, 1.0

ONE_VA, SHARED_ONE_AND_A_HALF_VA, THREE_VA, EASE_STEP_VA = 0x004E419C, 0x004E6D0C, 0x004E6D4C, 0x004E6D10


def _f32(value):
    return struct.pack("<f", value)


def _site(name, va, retail, patched):
    assert len(retail) == len(patched)
    return (name, va, retail, patched)


SITES = (
    # throw start 0x2DA370: the rate switch (type 3: 1.5; type 2: clamp(3 x t81, 1.0, 1.2))
    _site("deep_lob_start_rate", 0x002DA52F, b"\xb8" + _f32(RETAIL_DEEP_LOB_RATE), b"\xb8" + _f32(DEEP_LOB_RATE)),
    _site("rollout_rate_cap", 0x002DA539, b"\x68" + _f32(RETAIL_ROLLOUT_RATE_CAP), b"\x68" + _f32(ROLLOUT_RATE_CAP)),
    # throw restart 0x2DA5D0: the clip restarts at 1.5 and remembers it
    _site("restart_rate", 0x002DA666, b"\x68" + _f32(RETAIL_DEEP_LOB_RATE), b"\x68" + _f32(DEEP_LOB_RATE)),
    _site("restart_rate_stored", 0x002DA678, b"\xc7\x87\xe0\x00\x00\x00" + _f32(RETAIL_DEEP_LOB_RATE),
          b"\xc7\x87\xe0\x00\x00\x00" + _f32(DEEP_LOB_RATE)),
    # throw task tick 0x2D85D0: where a lob eases to (human let go of the button; the default branch)
    _site("ease_target_released", 0x002D8652, b"\xbb" + _f32(RETAIL_EASE_FLOOR), b"\xbb" + _f32(EASE_FLOOR)),
    _site("ease_target_after_release", 0x002D8668, b"\xbb" + _f32(RETAIL_EASE_FLOOR), b"\xbb" + _f32(EASE_FLOOR)),
    _site("ease_target_default", 0x002D86EC, b"\xbb" + _f32(RETAIL_EASE_FLOOR), b"\xbb" + _f32(EASE_FLOOR)),
    # the CPU's ease target is 1 + (rate - 1) x hold; the 1.0 is read from 0x4E419C in two instructions
    _site("cpu_blend_minus_base", 0x002D86C0, b"\xd8\x25" + struct.pack("<I", ONE_VA),
          b"\xd8\x25" + struct.pack("<I", SHARED_ONE_AND_A_HALF_VA)),
    _site("cpu_blend_plus_base", 0x002D86D6, b"\xd8\x05" + struct.pack("<I", ONE_VA),
          b"\xd8\x05" + struct.pack("<I", SHARED_ONE_AND_A_HALF_VA)),
)

# (va, size, sha256 of the retail bytes).  The three routines are hashed with their own sites put back to retail.
GUARDS = (
    (0x002DA370, 0x260, "2f66ea73e6aac23b0b2749a67f379370aa37365c79ce362cacf4044f5662d469"),   # throw start
    (0x002DA5D0, 0x0CE, "9a8c56983096b58e99f20af6cf0811ca5b08b7700db5c954b5ac3c473cadb896"),   # throw restart
    (0x002D85D0, 0x181, "ac3b08be990964f94e0c234a8fea30193928b27fd8d19be1cf646317f40485fb"),   # throw task tick
    (0x002D72C0, 0x02D, "0f6d660c536407f94180939ee9a0a2054ca064dff5b206c5e8869d8360218279"),   # max(a, b) helper
    (0x002D7290, 0x02E, "253012a9d68059062540297d632af4eb9e2d9209dac72b8ffa96c5724f10da0f"),   # min(a, b) helper
    (ONE_VA, 4, "e00e5eb9444182f352323374ef4e08ebcb784725fdd4fd612d7730540b3e0c8c"),           # retail 1.0
    (SHARED_ONE_AND_A_HALF_VA, 4, "c0e336a5f371ef22cd534e094269f2c1a9635cd080b71ffa671086832d3b60b7"),   # retail 1.5
    (THREE_VA, 4, "ea2845900b5856c9bf354b1aa9761b5aa6888e5ed61738fe9579ca42bc0f6054"),         # retail 3.0 (3 x t81)
    (EASE_STEP_VA, 4, "0b9d79ff0fc4d0a77ef398763bbe45c445501e826219f2b6a1aa709411ab631d"),     # retail 0.05 (ease step)
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError)


class QuickLongReleaseError(ValueError):
    """The throw routines are foreign or the patched executable does not read back."""


def _require(condition, message):
    if not condition:
        raise QuickLongReleaseError(message)


def sites():
    return [dict(label=name, va=va, before=before, after=after) for name, va, before, after in SITES]


def _recognize(payload):
    image = XbeImage(payload)
    states = set()
    for _name, va, before, after in SITES:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if raw == after else "foreign")
    _require(states in ({"retail"}, {"applied"}), "Foreign or mixed quick-release sites")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _name, at, before, _after in SITES:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        _require(hashlib.sha256(content).hexdigest() == digest, f"Foreign throw prerequisite at {va:#x}")
    return next(iter(states))


def status(payload):
    """'retail', 'applied' or 'foreign' (a changed site, a mixed set of sites or a changed routine around them)."""
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def read_settings(payload):
    return {"status": status(payload), "deep_lob_rate": DEEP_LOB_RATE, "rollout_rate_cap": ROLLOUT_RATE_CAP,
            "ease_floor": EASE_FLOOR}


def apply(payload):
    """Write the nine constants and repin the touched section digests; an identical replay changes nothing."""
    try:
        state = _recognize(payload)
    except _ERRORS as exc:
        raise QuickLongReleaseError(f"foreign/mixed quick-release input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False, code_bytes=0, writable_bytes=0,
                  readonly_bytes=0, deep_lob_rate=DEEP_LOB_RATE, rollout_rate_cap=ROLLOUT_RATE_CAP,
                  ease_floor=EASE_FLOOR)
    if state == "applied":
        return payload, dict(common, status="already_applied", already_applied=True, changed_bytes=0, edits=[])
    image = XbeImage(payload)
    buf = bytearray(payload)
    all_sections = _sections(payload)
    touched = {}
    edits = []
    for name, va, before, after in SITES:
        offset = image.offset(va, len(before))
        _require(bytes(buf[offset:offset + len(before)]) == before, f"quick-release site {va:#x} is not retail")
        buf[offset:offset + len(before)] = after
        section = _section_for_offset(all_sections, offset)
        touched[section.header_offset] = section
        edits.append(dict(label=name, va=hex(va), file_offset=hex(offset), before=before.hex(), after=after.hex()))
    for header_offset, section in touched.items():
        buf[header_offset + 36:header_offset + 56] = section_digest(bytes(buf), section)
    result = bytes(buf)
    _require(_recognize(result) == "applied", "quick-release postcondition failed")
    return result, dict(common, status="applied", already_applied=False,
                        before_sha256=hashlib.sha256(payload).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=sum(a != b for a, b in zip(payload, result)), edits=edits,
                        sections_repinned=sorted(section.index for section in touched.values()))


__all__ = ["BUILD_CAPTION", "DEEP_LOB_RATE", "EASE_FLOOR", "GUARDS", "HELP_TEXT", "OWNER", "QuickLongReleaseError",
           "REQUESTS", "ROLLOUT_RATE_CAP", "SITES", "apply", "read_settings", "sites", "status"]
