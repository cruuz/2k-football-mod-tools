"""EXPERIMENTAL / UNWITNESSED: the game's own Edit Player cycles all sixteen elbow pads.

X_Ray (#2k5-ideas, 2026-09-20): "If a player doesn't automatically have these equipment
options assigned to them in game you can't add them because they are just not available.
Or if they do have them on a player in-game and you toggle to another piece of equipment
the missing equipment options (High elbow and Turf) disappear and are not able to be
selected." Beta 74 fixed the Studio's list; this is the game's own screen.

Retail ``default.xbe``: Create Player and both Edit Player pages (the row lists at
.rdata 0x5672A0, 0x5674F0 and 0x567740) share one pair of equipment row descriptors,
"Left Elbow Pad" at 0x563520 and "Right Elbow Pad" at 0x5635D0. Each descriptor carries
a label getter at +0x08, a next handler at +0x20 and a previous handler at +0x38:

    left   get 0x3451F0   next 0x345210   prev 0x345250   field = bits 22..25 of [rec+0x1C]
    right  get 0x3452A0   next 0x3452C0   prev 0x345300   field = bits 26..29 of [rec+0x1C]

Both getters index the sixteen-entry option list at .rdata 0x555C78 with the raw stored
value, so a player who already carries White Turf or High Team reads back correctly. The
cycling handlers are the gate, and they are plain constants, not a per-player set:

    next   and edx, 0xf ; cmp dl, 9 ; jl <increment>    ; else clear the field to 0
    prev   test cl, 0xf ; jg <decrement>                ; else write 9 into the field

So the reachable range is 0..9 and the last six entries (White Turf, Black Turf, Taped,
High White, High Black, High Team) can never be selected, and stepping off one of them
drops to None. Every other equipment slot on the same page already reaches its whole
list (helmet 2, face mask 27, face shield 3, eyeblack 2, mouthpiece 2, gloves 10,
wristbands 14, sleeves 4, shoes 7, neck roll 5, turtleneck 4); elbow pads are the only
short one.

The patch raises the two ``cmp dl, 9`` immediates to 15 and retargets the two backward
wraps from 9 to 15. Four .text spans, ten changed bytes, no cave and no new data. The
field stays four bits wide and the stored value stays in 0..15, so a patched image and a
retail image read each other's rosters unchanged. Unwitnessed in game.
"""

from __future__ import annotations

from typing import Mapping

from . import nfl2k5_rdata_sites as rdata

# Descriptors and the option list the getters index (pinned for the report, not written).
LEFT_DESCRIPTOR_VA = 0x00563520
RIGHT_DESCRIPTOR_VA = 0x005635D0
OPTION_LIST_VA = 0x00555C78
ROW_LIST_VAS = (0x005672A0, 0x005674F0, 0x00567740)

RETAIL_LAST_INDEX = 9
PATCHED_LAST_INDEX = 15
OPTION_COUNT = PATCHED_LAST_INDEX + 1

# Each site starts at the field read and ends at the ret of the wrap path, so the shift
# (which of the two fields), the mask and the wrap constants are all pinned together.
LEFT_NEXT_VA = 0x0034521F
LEFT_PREV_VA = 0x0034525F
RIGHT_NEXT_VA = 0x003452CF
RIGHT_PREV_VA = 0x0034530F

LEFT_NEXT_RETAIL = bytes.fromhex("8b481cc1e9168bd183e20f80fa097c0881601cffff3ffcc3")
LEFT_PREV_RETAIL = bytes.fromhex("8b481cc1e916f6c10f7f138b481c81e1ffff7ffe81c90000400289481cc3")
RIGHT_NEXT_RETAIL = bytes.fromhex("8b481cc1e91a8bd183e20f80fa097c0881601cffffffc3c3")
RIGHT_PREV_RETAIL = bytes.fromhex("8b481cc1e91af6c10f7f138b481c81e1ffffffe781c90000002489481cc3")


class ElbowOptionsError(ValueError):
    """The executable does not carry the retail elbow cycling handlers."""


_CAP_INDEX = 0x0D          # the imm8 of `cmp dl, 9`
_WRAP_AND_INDEX = 0x10     # the imm32 of `and ecx, <clear the field>`
_WRAP_OR_INDEX = 0x16      # the imm32 of `or ecx, <field = 9>`


def _with_cap(span: bytes, last_index: int) -> bytes:
    out = bytearray(span)
    out[_CAP_INDEX] = last_index
    return bytes(out)


def _with_wrap(span: bytes, mask: int, last_index: int) -> bytes:
    """Rewrite the backward wrap so it lands on ``last_index`` instead of 9.

    Retail clears only the two bits it then does not set (``and 0xFE7FFFFF`` with
    ``or 0x02400000`` is 9 for any prior value); the patch writes the plain form,
    clearing the whole field and setting ``last_index``. Same two immediates, same
    instruction lengths.
    """

    out = bytearray(span)
    out[_WRAP_AND_INDEX:_WRAP_AND_INDEX + 4] = ((~mask) & 0xFFFFFFFF).to_bytes(4, "little")
    out[_WRAP_OR_INDEX:_WRAP_OR_INDEX + 4] = ((last_index << _shift(mask)) & mask).to_bytes(4, "little")
    return bytes(out)


def _shift(mask: int) -> int:
    return (mask & -mask).bit_length() - 1


def wrap_target(span: bytes, mask: int) -> int:
    """The index the backward wrap in ``span`` writes, read back from its immediates.

    ``and`` then ``or`` is bitwise, so the landed field depends only on the field bits
    that were there before; sixteen priors cover every case. Raises if the pair is not
    a constant write.
    """

    and_imm = int.from_bytes(span[_WRAP_AND_INDEX:_WRAP_AND_INDEX + 4], "little")
    or_imm = int.from_bytes(span[_WRAP_OR_INDEX:_WRAP_OR_INDEX + 4], "little")
    shift = _shift(mask)
    landed = {((((prior << shift) & and_imm) | or_imm) & mask) >> shift for prior in range(16)}
    if len(landed) != 1:
        raise ElbowOptionsError("elbow wrap immediates do not write one fixed index")
    return landed.pop()


LEFT_FIELD_MASK = 0x03C00000    # bits 22..25 of [rec+0x1C]
RIGHT_FIELD_MASK = 0x3C000000   # bits 26..29 of [rec+0x1C]

LEFT_NEXT_PATCHED = _with_cap(LEFT_NEXT_RETAIL, PATCHED_LAST_INDEX)
RIGHT_NEXT_PATCHED = _with_cap(RIGHT_NEXT_RETAIL, PATCHED_LAST_INDEX)
LEFT_PREV_PATCHED = _with_wrap(LEFT_PREV_RETAIL, LEFT_FIELD_MASK, PATCHED_LAST_INDEX)
RIGHT_PREV_PATCHED = _with_wrap(RIGHT_PREV_RETAIL, RIGHT_FIELD_MASK, PATCHED_LAST_INDEX)

# The only difference is the reachable index: retail caps at 9 and wraps back to 9,
# the patch caps at 15 and wraps back to 15, and every span keeps its length.
assert LEFT_NEXT_RETAIL[_CAP_INDEX] == RIGHT_NEXT_RETAIL[_CAP_INDEX] == RETAIL_LAST_INDEX
assert LEFT_NEXT_PATCHED[_CAP_INDEX] == RIGHT_NEXT_PATCHED[_CAP_INDEX] == PATCHED_LAST_INDEX
assert wrap_target(LEFT_PREV_RETAIL, LEFT_FIELD_MASK) == RETAIL_LAST_INDEX
assert wrap_target(RIGHT_PREV_RETAIL, RIGHT_FIELD_MASK) == RETAIL_LAST_INDEX
assert wrap_target(LEFT_PREV_PATCHED, LEFT_FIELD_MASK) == PATCHED_LAST_INDEX
assert wrap_target(RIGHT_PREV_PATCHED, RIGHT_FIELD_MASK) == PATCHED_LAST_INDEX

UI_LABEL = "Edit Player offers every elbow pad"
HELP_TEXT = ("Retail: the game's own Edit Player cycles only the first ten elbow pads, so White Turf, "
             "Black Turf, Taped, High White, High Black and High Team cannot be chosen, and stepping "
             "off one a player already wears drops to None. Patch: both elbow rows cycle all sixteen, "
             "forward and backward. Nothing else changes; the saved value is the same four bits. "
             "EXPERIMENTAL / UNWITNESSED.")
BUILD_CAPTION = "all sixteen elbow pads in Edit Player"


def sites() -> list[tuple[str, int, bytes, bytes]]:
    return [("left_elbow_next", LEFT_NEXT_VA, LEFT_NEXT_RETAIL, LEFT_NEXT_PATCHED),
            ("left_elbow_prev", LEFT_PREV_VA, LEFT_PREV_RETAIL, LEFT_PREV_PATCHED),
            ("right_elbow_next", RIGHT_NEXT_VA, RIGHT_NEXT_RETAIL, RIGHT_NEXT_PATCHED),
            ("right_elbow_prev", RIGHT_PREV_VA, RIGHT_PREV_RETAIL, RIGHT_PREV_PATCHED)]


def revert_sites() -> list[tuple[str, int, bytes, bytes]]:
    """The exact inverse: patched bytes back to retail, same four spans."""

    return [(label, va, after, before) for label, va, before, after in sites()]


def status(payload: bytes) -> str:
    return rdata.status(payload, sites())


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    try:
        patched, receipt = rdata.apply(payload, sites(), "elbow-options")
    except rdata.RdataSiteError as exc:
        raise ElbowOptionsError(str(exc)) from exc
    return patched, {**receipt, "experimental": True, "witnessed": False,
                     "label": UI_LABEL, "option_count": OPTION_COUNT,
                     "retail_last_index": RETAIL_LAST_INDEX,
                     "patched_last_index": PATCHED_LAST_INDEX,
                     "option_list": f"0x{OPTION_LIST_VA:x}",
                     "descriptors": [f"0x{LEFT_DESCRIPTOR_VA:x}", f"0x{RIGHT_DESCRIPTOR_VA:x}"]}


def revert(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Put the retail handlers back byte for byte."""

    state = status(payload)
    if state == "retail":
        return bytes(payload), {"already_applied": True, "edits": [], "changed_bytes": 0}
    try:
        reverted, receipt = rdata.apply(payload, revert_sites(), "elbow-options revert")
    except rdata.RdataSiteError as exc:
        raise ElbowOptionsError(str(exc)) from exc
    if status(reverted) != "retail":
        raise ElbowOptionsError("elbow-options revert did not restore the retail handlers")
    return reverted, {**receipt, "reverted": True}


__all__ = ["BUILD_CAPTION", "ElbowOptionsError", "HELP_TEXT", "LEFT_DESCRIPTOR_VA", "LEFT_FIELD_MASK",
           "LEFT_NEXT_PATCHED", "LEFT_NEXT_RETAIL", "LEFT_NEXT_VA", "LEFT_PREV_PATCHED",
           "LEFT_PREV_RETAIL", "LEFT_PREV_VA", "OPTION_COUNT", "OPTION_LIST_VA", "PATCHED_LAST_INDEX",
           "RETAIL_LAST_INDEX", "RIGHT_DESCRIPTOR_VA", "RIGHT_FIELD_MASK", "RIGHT_NEXT_PATCHED",
           "RIGHT_NEXT_RETAIL", "RIGHT_NEXT_VA", "RIGHT_PREV_PATCHED", "RIGHT_PREV_RETAIL",
           "RIGHT_PREV_VA", "ROW_LIST_VAS", "UI_LABEL", "apply", "revert", "revert_sites", "sites",
           "status"]
