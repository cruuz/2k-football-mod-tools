"""Pro Bowl Votes: list the positions in football order, kickers and punters last (executable patch).

Retail ``default.xbe``: the Front Office's Pro Bowl Votes screen (list-box record 0x54A160) takes its
tabs from a zero-terminated list of 17 descriptor pointers at .rdata 0x54A254: QB HB FB WR TE C G T
**K P** DT DE OLB ILB CB SS FS. Each tab descriptor carries its own position enum at +0x20, which the
vote scanner ``cb_003213e0`` reads directly; nothing indexes a tab by its ordinal and no other screen
shares the list (Player Stats, League Leaders and Rookie Watch hold stat categories; the depth chart
uses the unit slot records). Moving the two kicking pointers to the end therefore changes only the
order a player pages through: QB HB FB WR TE C G T DT DE OLB ILB CB SS FS K P. Unwitnessed in game.
"""

from __future__ import annotations

from typing import Mapping

from . import nfl2k5_rdata_sites as rdata

TAB_LIST_VA = 0x0054A254
TAB_COUNT = 17
RETAIL_TABS = (0x549150, 0x549200, 0x5492B0, 0x549360, 0x549C50, 0x549410, 0x5494C0, 0x549570,
               0x549620, 0x5496D0,                                                    # K, P
               0x549780, 0x549830, 0x5498E0, 0x549990, 0x549A40, 0x549BA0, 0x549AF0)
KICKING_TABS = (0x549620, 0x5496D0)
RETAIL_NAMES = ("QB", "HB", "FB", "WR", "TE", "C", "G", "T", "K", "P", "DT", "DE", "OLB", "ILB", "CB", "SS", "FS")


def _words(tabs) -> bytes:
    return b"".join(int(t).to_bytes(4, "little") for t in tabs) + b"\0\0\0\0"


PATCHED_TABS = tuple(t for t in RETAIL_TABS if t not in KICKING_TABS) + KICKING_TABS
RETAIL_LIST = _words(RETAIL_TABS)
PATCHED_LIST = _words(PATCHED_TABS)
PATCHED_NAMES = tuple(n for n in RETAIL_NAMES if n not in ("K", "P")) + ("K", "P")
assert len(RETAIL_LIST) == len(PATCHED_LIST) == (TAB_COUNT + 1) * 4


class ProBowlOrderError(ValueError):
    """The executable does not carry the retail Pro Bowl tab list."""


def sites() -> list[tuple[str, int, bytes, bytes]]:
    return [("probowl_tab_list", TAB_LIST_VA, RETAIL_LIST, PATCHED_LIST)]


def status(payload: bytes) -> str:
    return rdata.status(payload, sites())


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    try:
        patched, receipt = rdata.apply(payload, sites(), "Pro Bowl order")
    except rdata.RdataSiteError as exc:
        raise ProBowlOrderError(str(exc)) from exc
    return patched, {**receipt, "order": list(PATCHED_NAMES)}


__all__ = ["TAB_LIST_VA", "RETAIL_TABS", "PATCHED_TABS", "RETAIL_NAMES", "PATCHED_NAMES", "ProBowlOrderError",
           "apply", "sites", "status"]
