"""Draft pick words of the franchise trade board (beta 81; qb34/evidence/trades/RISKS.md (b), settled from the native
code and proved on kept images by tests/mod_editor/test_b81_qb_room_trades.py, class PickEncoding).

A pick is a u16 in a board record (+0x18 side A, +0x30 side B, three each):
- bits 0-5 ROUND, one-based 1..7; 0 means "no pick" (the executor tests `& 0x3F` at 0x2BC7E9 / 0x2BC7FA; a cancelled
  record keeps the other bits with round 0);
- bits 6-11 SLOT: in season the index of the club the pick originally belonged to (the rows are created as the identity
  by the post-draft roll 0x31E430); after the playoffs the stage advance's draft-order step 0x31E210(1) (called at
  0x247B74) re-indexes the coming draft's rows so the slot is the draft position;
- bits 12-15 YEAR: 0 the next draft, 1 the one after (the table holds two years).
The owner is the club index in the byte at 0xE3C094 + 32 * (7 * year + round) + slot (written by the executor's transfer
0x2BB1C0). The draft's own round counter 0xE3C0A8 is zero-based and indexes from 0xE3C0B4 (row 1): draft round r0 is
pick round r0 + 1 (0x3254D0). The Transactions screen prints the row's round through the ordinal table at 0xAF08F4
("1st" .. "7th"; 0 "Not Yet"), as "%s round draft pick".
"""
from __future__ import annotations

PICK_TABLE = 0xE3C094            # 15 rows of 32 bytes; rows 1-7 the next draft, 8-14 the one after; row 0 is not owners
DRAFT_ROUND, DRAFT_PICK = 0xE3C0A8, 0xE3C0A4     # the draft's zero-based round counter and pick within the round
DRAFT_ORDER = 0xE41BB8           # 32 club indices in draft order (written by 0x31E210)
ROUNDS, SLOTS, YEARS = 7, 32, 2


def word(round_: int, slot: int, year: int = 0) -> int:
    """The pick word for a one-based round, an original-club (in season) slot and a year (0 = the next draft)."""
    if not (1 <= round_ <= ROUNDS and 0 <= slot < SLOTS and 0 <= year < YEARS):
        raise ValueError(f"no such pick: round {round_}, slot {slot}, year {year}")
    return round_ | slot << 6 | year << 12


def decode(value: int) -> tuple[int, int, int] | None:
    """(round, slot, year), or None for "no pick" (round 0). Raises for a word the game cannot index."""
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"a pick word is 16 bits: {value!r}")
    round_, slot, year = value & 0x3F, value >> 6 & 0x3F, value >> 12
    if not round_:
        return None
    if round_ > ROUNDS or slot >= SLOTS or year >= YEARS:
        raise ValueError(f"pick word {value:#06x} names no row of the table")
    return round_, slot, year


def owner_address(value: int) -> int:
    """Address of the owner byte the game reads and the executor writes for this pick word."""
    picked = decode(value)
    if picked is None:
        raise ValueError("round 0 is no pick")
    round_, slot, year = picked
    return PICK_TABLE + 32 * (ROUNDS * year + round_) + slot


def ordinal(round_: int) -> str:
    """The Transactions screen's text for a round (the table at 0xAF08F4)."""
    return ("Not Yet", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th")[round_]
