"""Python mirror of tools/common/team_need.h, the shared team-need rule for computer clubs (beta 81).

Used by the season validator (tools/franchise_invariants.py), the trades lane's season observer and the team-building
lane's reducers, so the C pages and every check read one definition. tests/mod_editor/test_b81_team_need.py fails if
these tables differ from the header's. The header's comment states the rule; in short:

- pools: OLB (10) counts as LB (11); EDGE = 16, interior line = 15;
- starters: the first TN_SEATS[pool] present men of the pool in depth-row order (present = no status bits and out
  TN_PRESENT_WEEKS or fewer); a need is judged on the first TN_NEED_SEATS[pool] of them;
- rating: 0x246D80(p, 0) in whole points; league scale = every club's need-seat starters at the pool (32 x
  NEED_SEATS values, an empty need seat rates 0), sorted; percentile = mid-rank on it (values below plus half of
  those equal), in 256ths, so a tie at a cut line is not a hole;
- development asset: TN_YOUNG_YEARS or fewer years pro and rated above the pool's median starter.
"""
from __future__ import annotations

import struct

POSITIONS = 17
LB, FB = 11, 8
PRESENT_WEEKS = 2
YOUNG_YEARS = 3
SCALE = 256
POOL = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 11, 12, 13, 14, 15, 16)
SEATS = (1, 1, 1, 3, 3, 1, 1, 1, 1, 1, 0, 4, 1, 2, 2, 2, 2)
NEED_SEATS = (1, 0, 0, 2, 2, 1, 1, 1, 0, 1, 0, 2, 1, 2, 2, 2, 2)
PREMIUM = (1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1)
CUT_MIN = (2, 1, 1, 5, 5, 2, 2, 3, 0, 3, 0, 5, 2, 3, 3, 3, 4)
NAMES = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "LB", "C", "G", "T", "DT", "EDGE")
TABLES = {"TN_POOL": POOL, "TN_SEATS": SEATS, "TN_NEED_SEATS": NEED_SEATS, "TN_PREMIUM": PREMIUM, "TN_CUT_MIN": CUT_MIN}
CONSTANTS = {"TN_POSITIONS": POSITIONS, "TN_LB": LB, "TN_FB": FB, "TN_PRESENT_WEEKS": PRESENT_WEEKS,
             "TN_YOUNG_YEARS": YOUNG_YEARS, "TN_SCALE": SCALE}


def present(record: bytes) -> bool:
    medical, contract = struct.unpack_from("<II", record, 0x20)
    return not contract & 0x70000000 and (medical >> 22 & 255) <= PRESENT_WEEKS


def healthy(record: bytes) -> bool:
    medical, contract = struct.unpack_from("<II", record, 0x20)
    return not medical & 0xBFC00000 and not contract & 0x70000000


def row(record: bytes) -> int:
    return struct.unpack_from("<H", record, 0x28)[0] >> 10 & 7


def points(bits: int) -> int:
    e = bits >> 23 & 255
    if bits >> 31 or e < 119:
        return 0
    if e > 127:
        return 100
    s = 150 - e
    return (((bits & 0x7FFFFF) | 0x800000) * 100 + (1 << (s - 1))) >> s


def percentile(scale, rating: int) -> int:
    """Mid-rank of `rating` on the scale in 256ths: (values below + half of those equal) / length, rounded down
    (tn_percentile: (2 * below + equal) * 128 // n)."""
    scale = list(scale)
    below = sum(1 for v in scale if v < rating)
    equal = sum(1 for v in scale if v == rating)
    return (2 * below + equal) * (SCALE // 2) // len(scale) if scale else 0


def league_scale(clubs_need_seat_ratings) -> list[int]:
    """The league scale of a pool: every club's need-seat starter ratings (each club's list padded with 0 for an empty
    need seat), all clubs together, sorted."""
    return sorted(v for ratings in clubs_need_seat_ratings for v in ratings)


def starters(men, records, pool, *, need=False):
    """The present starters of one club at a pool, in depth-row order: `men` are player indices on the active list,
    `records` maps an index to its 0x54-byte record. The first NEED_SEATS (need=True) or SEATS of them."""
    seats = (NEED_SEATS if need else SEATS)[pool]
    at = [i for i in men if POOL[records[i][0x35]] == pool and present(records[i])] if pool < POSITIONS else []
    at.sort(key=lambda i: row(records[i]))
    return at[:seats]
