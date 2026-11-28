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
the NFL number at every setting.  The clock change applies only to the scheduled simulator.

The 54-byte rate computation at 0x10b89c is replaced in place. The two displaced instructions restore ESI
and the following branch's flags. The AI keeps the selected period length for its remaining-time decisions.

Revision 2 also fixes regular-season Games Played for reserves with recorded game statistics. Stock simulation
marks the initial 33 players per side at 0x103cab. A later substitution can record statistics while its raw
appearance flag remains zero. Updating that flag before postgame processing changes other consumers, including
the optional cornerback tackle bonus and its random draws. This owner corrects only the addition to the stored
Games Played field, after stat collection. The simulator's existing 33-player registration loop at 0x105060
is compacted in place to make room. Both original per-side writes remain in order, and the existing fallback
and its random draws begin at the original 0x1050d6. The only redirected call is the history add at 0x133446.

At the history add, field zero means Games Played. Mode 4 is scheduled franchise simulation, and stage 8 is
the regular season. Category aggregates 0..11 are present only when native stat collection recorded activity.
Category 12 is administrative and is attached to every processed player. The game computes a positive weight
for each attached category at 0x1eca80. A zero appearance gains one game when any activity category is present.
Previously saved records are read normally. This patch changes future additions to the existing save field.

Both editions share the same USA instructions. There is no cave, allocation, file growth or new save field.
Retail and the published pace-only revision can upgrade. A mixed or foreign preimage is refused.
"""
from __future__ import annotations

import struct

from .nfl2k5_bump_strength import _section_for_offset, _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_sim_stats"
REVISION = 2
BUILD_CAPTION = "Franchise sim pace and Games Played"
HELP_TEXT = ("Keep points and yardage at NFL-sized totals across Sim. Quarter Length settings. "
             "In simulated regular-season games, substitutes with recorded stats also earn a game "
             "on their Player Card. Existing saves pick up the correction from the next simulated game.")
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


# The leading 118 bytes of the unfinished/imported game's participation recorder. Its original follow-on
# path at 0x1050D6 retains all eligible-roster checks and random draws.
OPENING_SITE = 0x00105060
RETAIL_OPENING = bytes.fromhex(
    "51b8886ea900eb088da42400000000908b88e8fcffff8b51308b0ac701010000008b108b4a308b11c70201000000"
    "8b88ecfcffff8b51308b0ac701010000008b50048b4a308b11c702010000008b88f0fcffff8b51308b0ac7010100"
    "00008b50088b4a308b1183c00c3d0c6fa900c702010000007c9a"
)
# The first loop still writes 1 to each of the same 33 pairs, in the same order. After it jumps to the
# original continuation, the remaining space implements the guarded career-field addition.
APPLIED_OPENING = bytes.fromhex(
    "51b8886ea9006a2159"                    # preserve ECX, point EAX at the second list, ECX = 33
    "8b90e8fcffff8b52308b12c70201000000"    # first club: player -> stat container -> bank, set appearance
    "8b108b52308b12c70201000000"            # second club: same write
    "83c004e2dde945000000"                 # advance, repeat, continue at 0x1050D6
    "85d27538837c2404007531"               # only field zero and an original zero Games Played addition
    "833d80ffe500047528833da476e50008751f" # only scheduled sim (4), regular season (8)
    "51508b4d30e3168b0185c07410"           # preserve ECX/EAX and check both stat-bank pointers
    "6a0c59837cc8fc00e1f97404"             # scan twelve player categories, skipping the administrative record
    "ff44240c5859e97ea30400"               # add one to the argument and resume the original add routine
    "90909090"
)
assert len(RETAIL_OPENING) == len(APPLIED_OPENING) == 0x76

MERGE_REGION = 0x00133400
MERGE_SITE = 0x00133446
RETAIL_MERGE_REGION = bytes.fromhex(
    "516a00e8387ef9ffd95c2400d9442400d81d80414e00d9442400dfe0f6c4057a08d82584414e00eb06d80584414e00"
    "d95c24008b44240050e883f1ffff8b54240c8b4c240850e805c0010059c2080090"
)
RETAIL_MERGE_CALL = bytes.fromhex("e805c00100")   # call 0x14F450 (add to that player's season-history field)
APPLIED_MERGE_CALL = bytes.fromhex("e8461cfdff")  # call 0x105091 (the guarded tail-call to 0x14F450)
assert RETAIL_MERGE_REGION[MERGE_SITE-MERGE_REGION:MERGE_SITE-MERGE_REGION+5] == RETAIL_MERGE_CALL
APPLIED_MERGE_REGION = (RETAIL_MERGE_REGION[:MERGE_SITE-MERGE_REGION] + APPLIED_MERGE_CALL
                        + RETAIL_MERGE_REGION[MERGE_SITE-MERGE_REGION+5:])



class SimStatsError(ValueError):
    """The simulator sites are foreign or the patched executable does not read back."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SimStatsError(message)


def status(payload: bytes) -> str:
    try:
        image = XbeImage(payload)
        pace = image.read(REGION, REGION_SIZE)
        opening = image.read(OPENING_SITE, len(RETAIL_OPENING))
        merge = image.read(MERGE_REGION, len(RETAIL_MERGE_REGION))
    except (ValueError, struct.error, IndexError, OSError):
        return "foreign"
    if opening == RETAIL_OPENING and merge == RETAIL_MERGE_REGION:
        if pace == RETAIL_REGION:
            return "retail"
        if pace == APPLIED_REGION:
            return "previous"
    if pace == APPLIED_REGION and opening == APPLIED_OPENING and merge == APPLIED_MERGE_REGION:
        return "applied"
    return "foreign"


def _repin(payload: bytes, offset: int) -> tuple[bytes, int]:
    sections = _sections(payload)
    section = _section_for_offset(sections, offset)
    out = bytearray(payload)
    digest_at = section.header_offset + 36
    out[digest_at:digest_at + 20] = section_digest(bytes(out), section)
    return bytes(out), section.index if hasattr(section, "index") else 0


def _write_sites(payload: bytes, edits: list[tuple[str, int, bytes]]) -> bytes:
    image = XbeImage(payload)
    sections = _sections(payload)
    out = bytearray(payload)
    changed_sections = {}
    for _, address, data in edits:
        offset = image.offset(address, len(data))
        section = _section_for_offset(sections, offset)
        changed_sections[section.header_offset] = offset
        out[offset:offset + len(data)] = data
    result = bytes(out)
    for offset in changed_sections.values():
        result, _ = _repin(result, offset)
    return result


def apply(payload: bytes) -> tuple[bytes, dict]:
    state = status(payload)
    _require(state != "foreign", "foreign franchise simulator or player-stat history instructions; "
                                 "rebuild from a supported USA source")
    if state == "applied":
        return payload, {"already_applied": True, "changed_bytes": 0, "sim_rate": RATE, "revision": REVISION}
    edits = []
    if state == "retail":
        edits.append(("simulator_clock_decrement", SITE, APPLIED_SITE))
    edits.extend([("simulator_appearance_registration", OPENING_SITE, APPLIED_OPENING),
                  ("games_played_history_add", MERGE_SITE, APPLIED_MERGE_CALL)])
    result = _write_sites(payload, edits)
    _require(status(result) == "applied", "franchise simulator pace and Games Played read-back failed")
    return result, {
        "sim_rate": RATE, "revision": REVISION, "source_state": state,
        "site_va": hex(SITE), "site_bytes": SITE_SIZE,
        "edits": [{"label": label, "va": hex(address), "bytes": len(data)} for label, address, data in edits],
        "code_bytes": 0, "writable_bytes": 0, "readonly_bytes": 0,
        "changed_bytes": sum(a != b for a, b in zip(payload, result)),
    }


def restore_pace_only(payload: bytes) -> bytes:
    """Remove revision 2's appearance changes while retaining the established simulator pace."""
    state = status(payload)
    _require(state in ("previous", "applied"), "restoring the pace-only revision requires a recognized patched source")
    if state == "previous":
        return payload
    result = _write_sites(payload, [("simulator_appearance_registration", OPENING_SITE, RETAIL_OPENING),
                                    ("games_played_history_add", MERGE_SITE, RETAIL_MERGE_CALL)])
    _require(status(result) == "previous", "the pace-only revision did not read back")
    return result


def rate() -> float:
    """The installed per-event clock fraction (the number of events in a quarter is about 1/rate)."""
    return RATE


__all__ = ["APPLIED_REGION", "APPLIED_SITE", "BUILD_CAPTION", "HELP_TEXT", "OWNER", "RATE", "REGION",
           "REGION_SIZE", "REQUESTS", "RETAIL_REGION", "RETAIL_SITE", "SITE", "SITE_SIZE", "SimStatsError",
           "REVISION", "apply", "rate", "restore_pace_only", "status"]
