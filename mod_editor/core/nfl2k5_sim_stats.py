"""Franchise simulation pace: NFL-like game totals at every Sim. Quarter Length (b778 sim1).

Report (b778, released v0.6.1): "the franchise simming stats seems pretty unrealistic for 5 min quarters.
Teams dropping a ton of points and yards per game."  The franchise has **two** quarter-length options:
Game Options > Quarter Length (``DAT_00e6000c``, the played game, written into the live period length
``DAT_00e602b0`` at 0x55f5b) and Franchise Settings > Sim. Quarter Length (``DAT_00e60010``, the option row's
getter 0x2c6f60 and setter 0x2c6f69..).  The scheduled-game simulator reads the Sim. Quarter Length, not the
played Quarter Length: at ``0x10b315`` the initializer takes ``0xE60010`` for a fresh simulation (the live-import
path takes ``0xE6000C``), multiplies by 60 and floors the period at 180 seconds.  At the end of the same
routine (``0x10b89c``) it converts that period into the **per-event clock decrement** stored at ``0xA97204``:

    decrement = sqrt(300 / period_seconds) * 0.03

so a simulated game's number of plays grows with the square root of the Sim. Quarter Length.  Measured on the
USA retail executable, eight simulated weeks (Unicorn, full native fixtures and stat commits, same seed and
roster):

    Sim QL   plays/team-game   points/team-game   pass+rush yards/team-game
    5        54.7              20.0               294.8
    10       ~70               ~26                ~390
    15       ~95               ~35                ~530

An NFL game is about 63 plays, 22 points and 330 yards per team.  At the retail default (5) the engine is
close; at 10 and 15 it is progressively inflated, and a 15-minute Sim. Quarter Length produces the reported
"ton of points and yards".  The released modern roster is more productive per play than the 2004 roster, so
the installed rate is calibrated on it: eight simulated weeks of a fresh modern league give 23.0 / 33.4 / 41.1
points and 343.7 / 491.9 / 605.7 yards a team at Sim QL 5 / 10 / 15 before the patch, and 21.9 / 22.7 / 22.8
points and 329.6 / 338.6 / 341.0 yards after it.  The play count is about 55-58 a team rather than 63 because
the modern ratings already produce more yards per play; points and yards are the reported symptoms and are on
the NFL number at every setting.  The played game is untouched: this patch changes only the simulator's abstract
clock pace.

The fix replaces the whole 54-byte rate computation at ``0x10b89c..0x10b8d1`` in place with an immediate
clock decrement (``0.0315`` per event) and replays the two displaced instructions (``mov esi,[esp+0x18]`` and
``cmp esi,ebx``) so the following ``jne`` still sees its flags and ``esi``.  The simulator then runs an
NFL-sized game (about 55-58 plays, 22 points and 330-340 yards per team on the released modern roster) at
every Sim. Quarter Length from 3 to 15, because the per-event decrement no longer depends on the setting.  The AI's own remaining-time maths still
uses the user's Sim. Quarter Length, so a longer setting still feels like a longer game; only the number of
plays is normalised.  No cave, allocation, save field, roster byte or played-game path is touched: 0 code,
0 writable and 0 read-only bytes requested; 54 in-place bytes plus the containing section digest.  The module
refuses any executable whose bytes around the site are not the pinned retail bytes (or an identical replay of
this patch).
"""
from __future__ import annotations

import hashlib
import struct

from .nfl2k5_bump_strength import _section_for_offset, _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_sim_stats"
BUILD_CAPTION = "Franchise sim pace (NFL totals at any Sim Quarter Length)"
HELP_TEXT = ("Fixed: simulated franchise games now score and gain NFL-sized totals at every Sim. Quarter Length "
             "(Franchise Settings), instead of inflating points and yards at 10 and 15 minutes. The simulator "
             "runs an NFL-sized game whatever the setting; games you play are unchanged.")
REQUESTS = ()                     # in place: no executable cave, data or file growth

SITE = 0x0010B89C                 # inside FUN_0010b280, the scheduled-game simulator initializer
SITE_SIZE = 0x36                  # 0x10b89c..0x10b8d1, ending before `fld [0xA96BF4]`
REGION = 0x0010B880               # recognition window around the site (overtime hooks are at 0x10b2b4/0x10b2fa)
REGION_SIZE = 0x90
RATE = 0.0315                     # clock fraction per simulated event: NFL points/yards a team

# Retail bytes, USA default.xbe (sha256 73105b17...).  The site is the rate computation; the region also holds
# the function epilogue and is checked so a foreign initializer cannot be rewritten.
RETAIL_REGION = bytes.fromhex(
    "71a90051e8d763f5ff50e8c163f5ff8b157c6ea9008bc8e814effbffdb44240cd95c241cd944241cd83d88414e"
    "00d91d0472a9008b150472a90052e85057ffffd80d480f4f008b7424183bf3d91d0472a900d905f46ba900d805"
    "5c6d4e00d91df46ba9007515395d147410e8409dffff85c07407e8f7a8ffff8bf08bc65f5e5b8be55dc21800"
    "8bff81b51000a1b51000"
)
assert len(RETAIL_REGION) == REGION_SIZE
RETAIL_SITE = bytes.fromhex(
    "db44240cd95c241cd944241cd83d88414e00d91d0472a9008b150472a90052e85057ffffd80d480f4f008b74"
    "24183bf3d91d0472a900"
)
assert len(RETAIL_SITE) == SITE_SIZE
assert RETAIL_REGION[SITE - REGION:SITE - REGION + SITE_SIZE] == RETAIL_SITE


def _applied_site(rate: float = RATE) -> bytes:
    """The replacement: immediate decrement, then the two displaced instructions, then NOP padding."""
    body = bytearray()
    body += b"\xc7\x05" + struct.pack("<I", 0x00A97204) + struct.pack("<f", rate)   # mov [0xA97204], rate
    body += bytes.fromhex("8b742418")                                                # mov esi,[esp+0x18]
    body += bytes.fromhex("3bf3")                                                    # cmp esi,ebx
    assert len(body) <= SITE_SIZE
    return bytes(body) + b"\x90" * (SITE_SIZE - len(body))


APPLIED_SITE = _applied_site()
APPLIED_REGION = RETAIL_REGION[:SITE - REGION] + APPLIED_SITE + RETAIL_REGION[SITE - REGION + SITE_SIZE:]
assert len(APPLIED_REGION) == REGION_SIZE


class SimStatsError(ValueError):
    """The simulator pace site is foreign or the patched executable does not read back."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SimStatsError(message)


def _region(payload: bytes) -> bytes:
    return XbeImage(payload).read(REGION, REGION_SIZE)


def status(payload: bytes) -> str:
    try:
        region = _region(payload)
    except (ValueError, struct.error, IndexError, OSError):
        return "foreign"
    if region == RETAIL_REGION:
        return "retail"
    if region == APPLIED_REGION:
        return "applied"
    return "foreign"


def _repin(payload: bytes, offset: int) -> tuple[bytes, int]:
    sections = _sections(payload)
    section = _section_for_offset(sections, offset)
    out = bytearray(payload)
    digest_at = section.header_offset + 36
    out[digest_at:digest_at + 20] = section_digest(bytes(out), section)
    return bytes(out), section.index if hasattr(section, "index") else 0


def apply(payload: bytes) -> tuple[bytes, dict]:
    state = status(payload)
    _require(state != "foreign",
             "foreign simulator initializer around 0x10b89c; rebuild from a supported USA retail source")
    if state == "applied":
        return payload, {"already_applied": True, "changed_bytes": 0, "sim_rate": RATE}
    image = XbeImage(payload)
    offset = image.offset(SITE, SITE_SIZE)
    out = bytearray(payload)
    out[offset:offset + SITE_SIZE] = APPLIED_SITE
    result = bytes(out)
    result, _ = _repin(result, offset)
    _require(status(result) == "applied", "simulator pace read-back failed")
    _require(hashlib.sha256(_region(result)).hexdigest() == hashlib.sha256(APPLIED_REGION).hexdigest(),
             "simulator pace region changed")
    return result, {
        "sim_rate": RATE,
        "site_va": hex(SITE), "site_bytes": SITE_SIZE,
        "edits": [{"label": "simulator_clock_decrement", "va": hex(SITE), "bytes": SITE_SIZE}],
        "code_bytes": 0, "writable_bytes": 0, "readonly_bytes": 0,
        "changed_bytes": sum(a != b for a, b in zip(payload, result)),
    }


def rate() -> float:
    """The installed per-event clock fraction (the number of events in a quarter is about 1/rate)."""
    return RATE


__all__ = ["APPLIED_REGION", "APPLIED_SITE", "BUILD_CAPTION", "HELP_TEXT", "OWNER", "RATE", "REGION",
           "REGION_SIZE", "REQUESTS", "RETAIL_REGION", "RETAIL_SITE", "SITE", "SITE_SIZE", "SimStatsError",
           "apply", "rate", "status"]
