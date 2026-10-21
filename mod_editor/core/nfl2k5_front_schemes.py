"""Which authored team-seasons ran a 3-4, and which roster rule their ROST file takes (b776-de1).

Why this exists (Noah, 2026-10-18, 22 Giants classic team: "Kayvon Thibodeaux is in that middle linebacker and
Leonard Williams is at edge even though he's a D tackle"). Under One-pool positions the roster position byte means
EDGE (16), interior (15) or LB (11), and the books ask each pool for the right slot kind. The classic and moment files
are compiled from retail position labels (DE / DT / OLB / ILB). The historic rule turns OLB into LB and keeps DE as
EDGE, which is right for a 4-3 team and wrong for a 3-4 team: its OLBs are the pass rushers and its ends are the
interior linemen, so a four-down book fielded the rusher as a linebacker and the 300 lb end on the edge.

Rule (``mapping_scheme``): a team-season listed in ``data/nfl2k5_front_schemes.json`` as a 3-4 takes the 3-4 rule
(``tools/nfl2k5_roster_reclassify``: OLB to EDGE, DE to the interior pool) when the book that will play it asks the pools
for roles: every Anniversary moment and every classic team from 2010 on (b776; moments from 2005 before) (the franchise's
current book, ``nfl2k5_stock_books``) and every stock
bank book except the five pure 3-4 books. The "retail" group (b776-de2) is the 75 retail historic ROST files of the
disc (outer entries 113 to 187), which tools/nfl2k5_roster_reclassify reclassifies with the same rule choice; they are
played by the preserved bank, so the franchise's stock book decides (``retail_books``). The five pure 3-4 stock books (BAL HOU NE PIT SD) keep their retail slot
meaning (the end slots are the ends, the outside backer slots are the OLBs, merged into the LB pool), which the 4-3 rule
feeds correctly, so those keep the 4-3 rule. Every unlisted team-season keeps the 4-3 rule exactly as before.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/nfl2k5_front_schemes.json"
MODERN_FIRST_SEASON = 2010          # nfl2k5_stock_books.MODERN_FIRST_SEASON: this season on, the franchise's current book (b776: was 2005)
STOCK_ODD_BOOKS = ("BAL", "HOU", "NE", "PIT", "SD")   # retail books whose base front is the 3-4 (reclassify.PURE_THREE_FOUR_BOOKS)
GROUPS = ("classic", "moments", "retail")
MIN_LB = 3


class SchemeError(ValueError):
    pass


def load(path: Path = DATA) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != "nfl2k5_front_schemes/v1" or set(data["three_four"]) != set(GROUPS):
        raise SchemeError("front scheme data: unexpected shape")
    return data


def base_front(group: str, key: str, data: dict | None = None) -> str:
    """The team-season's own base front: ``"3-4"`` when listed, else ``"4-3"``."""
    if group not in GROUPS:
        raise SchemeError(f"unknown group {group!r}")
    data = load() if data is None else data
    return "3-4" if key in data["three_four"][group] else "4-3"


def roles_book(group: str, abbreviation: str, season: int) -> bool:
    """True when the book that plays this team-season asks the pools for roles (EDGE / interior / LB)."""
    if group in ("moments", "classic") and season >= MODERN_FIRST_SEASON:
        return True                                    # the franchise's current (modern) book (b776: classic teams of 2010 on too)
    return abbreviation not in STOCK_ODD_BOOKS          # the preserved retail bank: only the pure 3-4 books are literal


def mapping_scheme(group: str, key: str, abbreviation: str, season: int, data: dict | None = None) -> str:
    """The roster rule (``"3-4"`` or ``"4-3"``) the ROST compile of this authored team-season uses."""
    if base_front(group, key, data) == "3-4" and roles_book(group, abbreviation, int(season)):
        return "3-4"
    return "4-3"


def retail_three_four_entries(data: dict | None = None) -> dict[int, str]:
    """{outer entry: key} of the retail historic ROST files that take the 3-4 rule: listed as a 3-4 and played by a
    franchise book that asks the pools for roles (``mapping_scheme``).  Their season is read from the key."""
    data = load() if data is None else data
    out = {}
    for key in data["three_four"]["retail"]:
        season = int(key.rsplit("_", 1)[1])
        if mapping_scheme("retail", key, data["retail_books"][key], season, data) == "3-4":
            out[int(data["retail_entries"][key])] = key
    return out
