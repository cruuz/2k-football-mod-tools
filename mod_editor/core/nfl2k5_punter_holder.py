"""The punter holds on field goals and extra points (executable patch, xemu-only).

Retail (proved offline in the retail and v0.5 ``default.xbe``, B77 job H1, 2026-10-08):

* The Field Goal formation (PAT and FG alike, in every one of the 36 retail playbooks and the SOFTDRINK
  books) lists the position kinds ``K, H, T, T2, C2, G, G2, ...``.  Slot 1 is kind 3, ``H``, the holder.
* Kind 3 is not a roster position.  The depth-chart builder ``FUN_000e7c50`` (0xE7C50, called by every
  chart (re)build: game start, substitutions, franchise depth changes) fills its single list (list 25) from
  the **team record byte +0x194**, a roster-slot index (retail rosters: second quarterback 82 times, the
  punter 24 times of 107 teams).  The read is ``mov bl,[eax+0x194]`` at 0xE8009; the result is stored in
  the builder's local array at ``[esp+0x1F8]`` (kind 3, row 0) and copied into the chart at the end.
* Nothing else re-derives that byte: the franchise auto depth chart ``FUN_002bdcf0`` and its ``FUN_00243790``
  tail fill +0x195/+0x196/+0x199 (kick/punt returners) only, and the roster-removal handlers only turn it into
  -1 or shift it down.  The user's depth chart has no holder row (its special-teams rows are KR, PR, K, P).
  So a pure data edit of +0x194 would be undone by the first roster move; code in the builder is the fix.

The patch: the nine bytes ``mov eax,[ebp] ; mov bl,[eax+0x194]`` at **0xE8006** become ``jmp cave`` plus four
nops.  The cave, in the dead vec4-subtract routine at **0x24B10** (no rel32 / rel8 / pointer reference lands
on it; retail and v0.5 bytes are identical), reads the builder's own sorted list of punters,
``[esp+0xD8]`` (kind 1, rank 0 = depth chart P1; 0xFF = none).  If there is a punter, and he is not also the
kicker's row 0 (``[esp+0x168]``, so one man never fills two formation slots), his roster index is stored as
the holder (``mov [esp+0x1F8],bl``) and the builder resumes at 0xE8037 exactly where the retail store would
have continued.  Otherwise the two displaced instructions are replayed and the builder resumes at 0xE800F:
the retail rule (the team record's holder byte, with its null-player and unit checks) runs unchanged.
That covers the user and CPU teams in every mode, because every mode builds its charts through this routine.

The punter is on the field for no other formation that has an H slot, and the retail Field Goal formation has
no P slot, so the punter appears once.  Fake field goals: the holder is now the punter, so a run or throw by the
holder uses the punter's ratings.  The animation, snap and hold assignment belong to the formation slot, not to
the player's position.  EXPERIMENTAL / UNWITNESSED in a played game.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

IMAGE_BASE = 0x10000
OWNER = "nfl2k5_punter_holder"

# --- the hook inside the depth-chart builder FUN_000e7c50 ------------------------------------------
HOOK_VA = 0x000E8006
RETAIL_HOOK = bytes.fromhex("8b45008a9894010000")          # mov eax,[ebp] ; mov bl,[eax+0x194]
HOOK_SIZE = len(RETAIL_HOOK)
RESUME_VA = HOOK_VA + HOOK_SIZE                             # 0xE800F: cmp bl,0xff ; jle ...  (retail holder rules)
STORE_DONE_VA = 0x000E8037                                  # test esi,esi ; jne 0xE8049  (after the retail store)
# context that must be retail on any image we touch: the whole retail tail of the holder block
RETAIL_TAIL = bytes.fromhex(
    "80fbff7e230fbed38b149085d2741985f6750e8b4d088bc7e8d4f8ffff85c0740b889c24f801000085f6750e47")
TAIL_VA = RESUME_VA
HOOK_JUMP_TARGETS = (0x000E8006, 0x000E8030, 0x000E8037, 0x000E803B)   # retail branch targets in the block
FRAME_STORE = bytes.fromhex("889c24f8010000")               # mov [esp+0x1f8],bl   (kind 3 row 0)

# local arrays of FUN_000e7c50: [esp + 0x48 + kind*0x90 + lane + 2*row]
LOCAL_PUNTER = 0xD8          # kind 1 (P) lane 0 row 0
LOCAL_KICKER = 0x168         # kind 2 (K) lane 0 row 0
LOCAL_HOLDER = 0x1F8         # kind 3 (H) lane 0 row 0
assert LOCAL_PUNTER == 0x48 + 1 * 0x90 and LOCAL_KICKER == 0x48 + 2 * 0x90 and LOCAL_HOLDER == 0x48 + 3 * 0x90
TEAM_HOLDER_BYTE = 0x194

# --- the cave: the dead vec4 subtract routine -------------------------------------------------------
CAVE_VA = 0x00024B10
CAVE_SIZE = 0x30             # 0x24B10..0x24B3F: the routine (34 bytes) and its 14 nop bytes
NEXT_ROUTINE_VA = 0x00024B40  # the dead vec4 scale routine, left alone
RETAIL_CAVE = bytes.fromhex(
    "d902d821d918d94204d86104d95804d94208d86108d95808d9420cd8610cd9580cc39090909090909090909090909090")
RETAIL_NEXT_ROUTINE_HEAD = bytes.fromhex("d9442404d809d918")
assert len(RETAIL_CAVE) == CAVE_SIZE


class PunterHolderError(ValueError):
    """The punter-holder patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PunterHolderError(message)


def _rel32(source_end: int, target: int) -> bytes:
    return struct.pack("<i", target - source_end)


def _cave() -> tuple[bytes, dict[str, int]]:
    """The cave code.  Entered by ``jmp`` from the hook, so ``esp`` is the builder's own frame."""

    out = bytearray()
    labels: dict[str, int] = {}
    fixups: list[tuple[int, str]] = []

    def b(hexs: str) -> None:
        out.extend(bytes.fromhex(hexs))

    def j8(opcode: str, label: str) -> None:
        out.extend(bytes.fromhex(opcode) + b"\x00")
        fixups.append((len(out) - 1, label))

    labels["cave"] = 0
    b("8a9c24" + struct.pack("<I", LOCAL_PUNTER).hex())     # mov bl,[esp+0xd8]     P1 roster index (0xff = none)
    b("80fbff")                                             # cmp bl,0xff
    j8("74", "retail")                                      # je retail             no punter: retail rule
    b("3a9c24" + struct.pack("<I", LOCAL_KICKER).hex())     # cmp bl,[esp+0x168]    never the kicker's row 0
    j8("74", "retail")                                      # je retail
    b("889c24" + struct.pack("<I", LOCAL_HOLDER).hex())     # mov [esp+0x1f8],bl    holder := punter
    b("e9")                                                 # jmp 0xE8037
    out.extend(_rel32(CAVE_VA + len(out) + 4, STORE_DONE_VA))
    labels["retail"] = len(out)
    b("8b4500")                                             # mov eax,[ebp]         displaced
    b("8a98" + struct.pack("<I", TEAM_HOLDER_BYTE).hex())   # mov bl,[eax+0x194]    displaced
    b("e9")                                                 # jmp 0xE800F           retail holder rules
    out.extend(_rel32(CAVE_VA + len(out) + 4, RESUME_VA))
    for at, label in fixups:
        rel = labels[label] - (at + 1)
        _require(0 <= rel <= 127, "cave short jump out of range")
        out[at] = rel
    return bytes(out), {name: CAVE_VA + off for name, off in labels.items()}


CODE, CAVE_LABELS = _cave()
CODE_SIZE = len(CODE)
assert CODE_SIZE <= CAVE_SIZE, f"punter-holder cave is {CODE_SIZE} bytes, over the {CAVE_SIZE} of the dead routine"

PATCHED_HOOK = b"\xe9" + _rel32(HOOK_VA + 5, CAVE_VA) + b"\x90" * (HOOK_SIZE - 5)
assert len(PATCHED_HOOK) == HOOK_SIZE


def cave_bytes() -> bytes:
    """The code, int3 fill to the end of the dead routine's 48 bytes."""

    body = CODE + b"\xcc" * (CAVE_SIZE - CODE_SIZE)
    _require(len(body) == CAVE_SIZE, "cave layout error")
    return body


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise PunterHolderError(f"VA 0x{va:x} is in no section")


def sites() -> list[tuple[str, int, bytes, bytes]]:
    """``(label, va, retail bytes, patched bytes)`` for the hook and the cave."""

    return [("holder_hook", HOOK_VA, RETAIL_HOOK, PATCHED_HOOK),
            ("holder_cave", CAVE_VA, RETAIL_CAVE, cave_bytes())]


# context that must be retail on any image we touch: the retail holder rules the cave resumes into, and the
# first bytes of the routine after the dead host
PINS = ((TAIL_VA, RETAIL_TAIL), (NEXT_ROUTINE_VA, RETAIL_NEXT_ROUTINE_HEAD))


def _pins_are_retail(payload: bytes) -> bool:
    for va, expected in PINS:
        off = _offset(payload, va)
        if payload[off: off + len(expected)] != expected:
            return False
    return True


def status(payload: bytes) -> str:
    """'retail', 'applied' or 'foreign' (bytes match neither; refuse to touch)."""

    try:
        if not _pins_are_retail(payload):
            return "foreign"
        hook = payload[_offset(payload, HOOK_VA):][:HOOK_SIZE]
        cave = payload[_offset(payload, CAVE_VA):][:CAVE_SIZE]
    except (PunterHolderError, ValueError, struct.error):
        return "foreign"
    hook_state = "retail" if hook == RETAIL_HOOK else "applied" if hook == PATCHED_HOOK else "foreign"
    cave_state = "retail" if cave == RETAIL_CAVE else "applied" if cave == cave_bytes() else "foreign"
    if hook_state == cave_state == "retail":
        return "retail"
    if hook_state == cave_state == "applied":
        return "applied"
    return "foreign"


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Return the patched XBE bytes plus a receipt; refuses anything but retail sites.

    An applied image is returned unchanged with ``already_applied``.
    """

    state = status(payload)
    if state == "applied":
        return payload, {"already_applied": True, "edits": [], "changed_bytes": 0, "status": "applied"}
    _require(state == "retail", f"punter-holder sites are {state}, not retail; refusing")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched: set[int] = set()
    edits = []
    for label, va, before, after in sites():
        off = _offset(payload, va)
        _require(payload[off: off + len(before)] == before, f"{label}: retail bytes missing")
        buf[off: off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "va": f"0x{va:x}", "file_offset": f"0x{off:x}", "bytes": len(after),
                      "before": before.hex(), "after": after.hex()})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied", "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {
        "edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched), "status": "applied",
        "hook_va": f"0x{HOOK_VA:x}", "hook_bytes": PATCHED_HOOK.hex(),
        "cave_va": f"0x{CAVE_VA:x}", "cave_size": CAVE_SIZE, "cave_code_bytes": CODE_SIZE,
        "cave_labels": {name: f"0x{va:x}" for name, va in CAVE_LABELS.items()},
        "rule": "holder := depth chart P1 (builder local [esp+0xd8]) unless none or the kicker's row 0; else retail +0x194",
    }


__all__ = ["CAVE_LABELS", "CAVE_SIZE", "CAVE_VA", "CODE", "CODE_SIZE", "HOOK_SIZE", "HOOK_VA", "LOCAL_HOLDER",
           "LOCAL_KICKER", "LOCAL_PUNTER", "NEXT_ROUTINE_VA", "OWNER", "PATCHED_HOOK", "PINS", "PunterHolderError",
           "RESUME_VA", "RETAIL_CAVE", "RETAIL_HOOK", "RETAIL_TAIL", "STORE_DONE_VA", "apply", "cave_bytes", "sites",
           "status"]
