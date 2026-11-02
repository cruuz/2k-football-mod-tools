"""Coach career counters: stop every winning season from counting as a Super Bowl trip.

Retail's season rollover (FUN_00247B40, called only when a franchise advances to the offseason, 0x248632) updates each
club's head coach once a year: seasons with the club (+0x1C) and total seasons (+0x1E) go up, and when his season wins
beat his season losses both the winning-seasons counter (+0x30, which the Coach's Card shows) and the word at +0x32 go up
by one.  The roster data (retail and SOFTDRINK alike: Gibbs 4, Reid 6, Belichick 2) keeps the coach's Super Bowl
appearances in +0x32, and the game updates the Super Bowl wins and losses (+0x38, +0x3A) itself at the final, so the
extra increment is a retail slip: every winning season in a franchise adds a Super Bowl trip to the coach (a coach on
a 10-year winning streak would show 10 more).  Nothing in the game's own screens prints +0x32 (the Coach's Card reads
+0x30, +0x34, +0x36, +0x38, +0x3A and +0x3C), so the damage shows in saved data, the Studio's Franchise editor and any
history page that reads it.

The fix is one instruction: ``inc word ptr [eax+0x32]`` (4 bytes) at 0x247CDA becomes a 4-byte no-op.  The 8 bytes
pinned here are that instruction and the ``inc word ptr [eax+0x30]`` before it, so a build that moved either is refused.
After the fix +0x32 keeps the appearances the roster wrote and no longer grows; a coach's trips from now on are
Super Bowl wins + losses (+0x38 + +0x3A), which the game does count.

Proved in tests/mod_editor/test_b780_c1_coach_career_fix.py by running the game's own rollover loop in Unicorn on the
retail and the patched executable: every counter agrees except +0x32.
"""
from __future__ import annotations

from . import nfl2k5_rdata_sites as rdata

OWNER = "nfl2k5_coach_career_fix"
BUILD_CAPTION = "Stop winning seasons counting as coach Super Bowl trips"
HELP_TEXT = ("Retail adds one Super Bowl trip to a head coach's record for every winning season he has. This stops that, so "
             "a coach's Super Bowl count only changes when his own numbers do. No change to games, ratings or "
             "play-calling; it only keeps franchise records honest.")

#: (label, virtual address, retail bytes, patched bytes): inc [eax+0x30] (kept) then inc [eax+0x32] -> nop dword [eax+0]
SITES = (("rollover: Super Bowl trip per winning season", 0x247CD6,
          bytes.fromhex("66ff403066ff4032"), bytes.fromhex("66ff40300f1f4000")),)
COACH_SUPER_BOWLS = 0x32


def status(payload: bytes) -> str:
    """``retail`` | ``applied`` | ``foreign`` for a default.xbe image."""
    return rdata.status(payload, SITES)


def apply(payload: bytes):
    """(patched payload, receipt).  Refuses an executable whose site is neither retail nor already patched."""
    return rdata.apply(payload, SITES, "coach career counter fix")


def verify(payload: bytes) -> dict:
    state = status(payload)
    return {"owner": OWNER, "status": state, "sites": [{"label": s[0], "va": f"0x{s[1]:x}"} for s in SITES],
            "experimental": False, "runtime_witnessed": False}
