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

Revision 2 (b780 hunt6, the beta-80 fix wave) adds two more in-place franchise record fixes to this owner, which is on
in every preset (tests/mod_editor/test_b780_hunt6_franchise_records.py runs each routine in Unicorn on both executables):

* **Playoff games stay out of the coach's career and season W-L** (FUN_00135260, the per-game coach update, 176 bytes
  rewritten in place). Retail added every postseason game to the career W-L (+0x20/+0x22) and to this season's W-L
  (+0x26/+0x28), which the rollover compares for a winning season: a 9-8 club that lost its first playoff game (9-9)
  got no winning season, and the roster's regular-season career records started mixing in playoff games. In stage 9
  the win and loss paths now skip those four words; the streaks, the playoff W-L (+0x34/+0x36) and the Super Bowl
  W-L (+0x38/+0x3A) are counted exactly as before, and like retail the routine changes no register but eax. The
  coaching carousel's owner model reads +0x26/+0x28/+0x2A as the season record on a 17-game scale, so it now reads
  the regular season it was calibrated on.
* **The Owner Firing row reads any nonzero value as On** (the retail text callback 0x148A40, 16 bytes). A franchise
  saved on a coaching-carousel build with All Teams (2) read the retail Off/On table at index 2, a NULL label, on
  every build without the carousel. ``(value + 1) >> 1`` gives Off, On, On (the retail owner check already treats any
  nonzero value as On). A carousel build replaces the row's text callback pointer, so it never runs this one.

Revision 3 honors Off when an existing franchise already carries the owner's last-warning mark. The ordinary firing
branch checks the saved option before posting a dismissal. The optional carousel still chooses which modes may enter
that branch. Recognized revision-1 and revision-2 installations upgrade in place.
"""
from __future__ import annotations

from . import nfl2k5_rdata_sites as rdata

OWNER = "nfl2k5_coach_career_fix"
BUILD_CAPTION = "Coach records and Owner Firing"
HELP_TEXT = ("Count a coach's regular-season, playoff and Super Bowl records separately. "
             "Show a carousel save's All Teams setting as On in a standard build. "
             "When an existing franchise has Owner Firing set to Off, a previous owner warning can no longer end the coach's job.")

#: (label, virtual address, retail bytes, patched bytes): inc [eax+0x30] (kept) then inc [eax+0x32] -> nop dword [eax+0]
SITES_V1 = (("rollover: Super Bowl trip per winning season", 0x247CD6,
             bytes.fromhex("66ff403066ff4032"), bytes.fromhex("66ff40300f1f4000")),)
# Revision 2 (b780 hunt6). The annotated source is docs/mod_editor/nfl2k5_coach_career_fix.S (GNU as, linked at the
# two retail addresses); the test checks that it reproduces these bytes.
RETAIL_RESULT = bytes.fromhex(
    "e84bf9f8ff83f8070f849f0000003bfb7d4d66ff462066ff462666837e2c00750fb8010000006689462c6689462eeb0466ff462e668b"
    "462e663b463c7e046689463ce809f9f8ff83f8097561e87fe7ffff85c0740566ff4638c366ff4634c37e3e66ff462266ff462866837e"
    "2c00740e66c7462c000066c7462e0100eb0466ff462ee8c9f8f8ff83f8097521e83fe7ffff85c0740566ff463ac366ff4636c366ff46"
    "2466ff462a66c7462e0000c39090")
PATCHED_RESULT = bytes.fromhex(
    "e84bf9f8ff83f8070f849900000039df7f5d7c0f66ff462466ff462a66c7462e0000c383f809740866ff462066ff462666837e2c0075"
    "09c7462c01000100eb0466ff462e668b462e663b463c7e046689463ce8f9f8f8ff83f809754be86fe7ffff85c0740566ff4638c366ff"
    "4634c383f809740866ff462266ff462866837e2c007409c7462c00000100eb0466ff462e83f8097512e836e7ffff85c0740566ff463a"
    "c366ff4636c3").ljust(len(RETAIL_RESULT), b"\x90")
RETAIL_OWNER_TEXT = bytes.fromhex("a14401e6008b048594d94e00c3909090")
PATCHED_OWNER_TEXT = bytes.fromhex("a14401e60040d1e88b048594d94e00c3")
RESULT_VA, OWNER_TEXT_VA = 0x135260, 0x148A40
SITES_V2 = (("game result: playoff games stay out of the coach's career and season W-L", RESULT_VA,
             RETAIL_RESULT, PATCHED_RESULT),
            ("franchise options: the Owner Firing text reads any nonzero value as On", OWNER_TEXT_VA,
             RETAIL_OWNER_TEXT, PATCHED_OWNER_TEXT))
WARNING_ACTION_VA = 0x2BA67B
RETAIL_WARNING_ACTION = bytes.fromhex(
    "e840e5d8ff84c38bcf7518e815a6e0ffba290000008bc8e8293dfcff5f5e5d33c05bc3"
    "e8fda5e0ffba2a0000008bc8e8113dfcff5f5e5d33c05bc3")
PATCHED_WARNING_ACTION = bytes.fromhex(
    "833d4401e600007432e837e5d8ff84c389f9750ce80ca6e0ffba29000000eb0ae800a6e0ff"
    "ba2a00000089c1e8143dfcff5f5e5d31c05bc3909090")
SITES_V3 = (("owner firing: honor Off after a previous warning", WARNING_ACTION_VA,
             RETAIL_WARNING_ACTION, PATCHED_WARNING_ACTION),)
SITES = SITES_V1 + SITES_V2 + SITES_V3
REVISION = 3
COACH_SUPER_BOWLS = 0x32


def _installed_revision(payload: bytes) -> int | None:
    states = tuple(rdata.status(payload, group) for group in (SITES_V1, SITES_V2, SITES_V3))
    for revision in range(REVISION + 1):
        if states == ("applied",) * revision + ("retail",) * (REVISION - revision):
            return revision
    return None


def status(payload: bytes) -> str:
    """Recognize the original executable and each complete historical revision."""
    return {None: "foreign", 0: "retail", 1: "previous", 2: "previous", 3: "applied"}[_installed_revision(payload)]


def apply(payload: bytes):
    revision = _installed_revision(payload)
    if revision is None:
        raise rdata.RdataSiteError("unrecognized coach record or Owner Firing instructions")
    sites = {0: SITES, 1: SITES_V2 + SITES_V3, 2: SITES_V3, 3: SITES}[revision]
    patched, receipt = rdata.apply(payload, sites, "coach records and Owner Firing")
    if 0 < revision < REVISION:
        receipt = {**receipt, "upgraded_from": revision}
    return patched, {**receipt, "revision": REVISION}


def restore_previous(payload: bytes):
    """Restore the recognized revision-2 rule while retaining the coach records and other installed owners."""
    revision = _installed_revision(payload)
    if revision not in (2, 3):
        raise rdata.RdataSiteError("an installed revision-2 or revision-3 coach record fix is required")
    undo = tuple((label, va, after, before) for label, va, before, after in SITES_V3)
    return rdata.apply(payload, undo, "restore the previous Owner Firing rule")


def verify(payload: bytes) -> dict:
    state = status(payload)
    return {"owner": OWNER, "status": state, "sites": [{"label": s[0], "va": f"0x{s[1]:x}"} for s in SITES],
            "experimental": False, "runtime_witnessed": False}
