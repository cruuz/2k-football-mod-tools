"""Heal Player: the game's own recovery write for one player record (b81 lane finn-r2, parity row E8).

Finn's Heal only rewrites +0x27 and +0x28.  The game keeps counting injury weeks after it (retail weekly pass
0x133BD0 still sees the injured bit and the weeks), so the Studio does not copy it.  It writes exactly what the
game's natural recovery routine 0xE6680 writes (RE_FACTS section 2, receipts game-tick.json):

* the u16 at +0x28 ``&= 0xFC00``: injury id bits 0..9 cleared, depth rank and side bits 10..15 kept.
  Studio fields ``injured_reserve`` (+0x28 bits 0..7) and ``unknown_29_low`` (+0x28 bits 8..9) become 0.
* the dword at +0x24 ``&= 0x8FFFFFFF``: injury status bits 28..30 (+0x27 bits 4..6) cleared, bit 31 kept.
  Studio field ``unknown_27_high`` (+0x27 bits 4..7) keeps only its top bit.
* the dword at +0x20: bits 22..31 become bit 30 only (weeks and the injured bit 31 cleared, "injury known" bit 30
  set).  Studio field ``unknown_20_high`` (10 bits from bit 22) becomes 0x100.  That is what the game does, and in a
  franchise save every player the weekly pass has touched has bit 30 set.  A roster save (and a disc roster) keeps
  bit 30 clear on every healthy player, so there the field becomes 0.

Only bytes +0x22, +0x23, +0x27, +0x28 and +0x29 can change.  A player on injured reserve is refused: IR has its
own return rules in this mod (Franchise > Injured Reserve > Activate).
"""

from __future__ import annotations

from typing import Any, Mapping

IR_MARKER = 0xEE                 # Finn's IR marker in the injury id low byte (+0x28)
INJURED_BIT = 0x200              # unknown_20_high bit 9 = +0x20 bit 31
KNOWN_BIT = 0x100                # unknown_20_high bit 8 = +0x20 bit 30
WEEKS_MASK = 0xFF                # unknown_20_high bits 0..7 = +0x20 bits 22..29
STATUS_MASK = 0x7                # unknown_27_high bits 0..2 = +0x27 bits 4..6
STATUS_KEEP = 0x8                # unknown_27_high bit 3 = +0x27 bit 7
HEAL_FIELDS = ("unknown_20_high", "unknown_27_high", "injured_reserve", "unknown_29_low")

REASON_HEALTHY = "He is not hurt."
REASON_IR = ("He is on injured reserve. Injured reserve has its own return rules in this mod: "
             "use Franchise > Injured Reserve > Activate.")


def _values(record: Any) -> Mapping[str, int]:
    return record if isinstance(record, Mapping) else record.values


def injury_state(record: Any) -> dict[str, int]:
    """The injury fields of a record, in plain numbers."""

    values = _values(record)
    high = int(values["unknown_20_high"])
    return {
        "injured": 1 if high & INJURED_BIT else 0,
        "known": 1 if high & KNOWN_BIT else 0,
        "weeks": high & WEEKS_MASK,
        "status": int(values["unknown_27_high"]) & STATUS_MASK,
        "injury_id": int(values["injured_reserve"]) | (int(values["unknown_29_low"]) << 8),
    }


def hurt(record: Any) -> bool:
    """Hurt when any of the injured bit, the weeks, the status bits or the injury id is non-zero."""

    state = injury_state(record)
    return bool(state["injured"] or state["weeks"] or state["status"] or state["injury_id"])


def on_ir_marker(record: Any) -> bool:
    return int(_values(record)["injured_reserve"]) == IR_MARKER


def heal_refusal(record: Any, *, on_listed_ir: bool = False) -> str:
    """Why this player cannot be healed here ('' when he can).  ``on_listed_ir``: the franchise save's injured
    reserve lists him (legacy cell or modern extension)."""

    if on_listed_ir or on_ir_marker(record):
        return REASON_IR
    if not hurt(record):
        return REASON_HEALTHY
    return ""


def heal_values(record: Any, franchise: bool) -> dict[str, int]:
    """The new values of the four injury fields, exactly the game's 0xE6680 result.

    ``franchise`` selects bit 30 (set in a franchise save, clear in a roster save or disc roster)."""

    values = _values(record)
    return {
        "unknown_20_high": KNOWN_BIT if franchise else 0,
        "unknown_27_high": int(values["unknown_27_high"]) & STATUS_KEEP,
        "injured_reserve": 0,
        "unknown_29_low": 0,
    }


def describe(record: Any) -> str:
    """One plain line about the injury, for tooltips and the changes list."""

    state = injury_state(record)
    if not hurt(record):
        return "healthy"
    parts = []
    if state["injured"] or state["weeks"]:
        parts.append(f"{state['weeks']} week{'' if state['weeks'] == 1 else 's'} left")
    if state["status"]:
        parts.append(f"status {state['status']}")
    if state["injury_id"]:
        parts.append(f"injury id {state['injury_id']}")
    return ", ".join(parts) or "hurt"
