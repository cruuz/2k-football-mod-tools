"""Cornerback tackle credit in the post-game stat merge (simulated and played games). EXPERIMENTAL.

Report (b778, v0.6.1): simulated right cornerbacks get too few tackles (Discord rjawn, 10/23:
``Rcbs in simulation seem to get too low tackles ex. Mitchell w 5 tackles in 5 games``).  The retail
merge is not a per-position table: every game stat is recorded in a per-player record and the
post-game merge ``FUN_001334b0`` copies it into the career stream.  A corner's record counts only
the plays on which the engine named him the tackler, so the left corner (rank chain) averages about
1.4 tackles a game and the right corner (side chain, the #2 corner) about 0.45, against 3.4 for an
NFL corner (nflverse 2018-2023, players with 8+ games).

This owner hooks *inside* the per-player merge at ``0x1334c3``, so it does not share the
``0x134e05`` call with the weekly-progression owner (b778-pg1).  For a cornerback who played this
game it draws a per-game tackle bonus from the game's own RNG (the subtract-with-borrow generator at
``0x48bc0``) and adds it to the career tackle field, so the season total moves off the engine's low
per-game attribution without replacing what the engine credited.  The bonus tables are calibrated
from the NFL per-game distribution of cornerbacks with at least eight games in 2018-2023 (nflverse
``stats_player_week``; 3.35 tackles a game, 6.2% zero-tackle games) against the measured retail
engine line (left corner about 1.4, right corner about 0.45, nickel and dime lower): the left-corner
bonus means 2.00 (10.9% zero), the right-corner 2.87 (7.8% zero), nickel 2.26 and dime 1.11, so the
season totals land near 3.4, 3.4, 2.5 and 1.2 a game with the spread of an NFL corner.  The two
starting corners are told apart by the depth rank/side word (rank 1 side 0 = right corner, rank 0
side 2 = left corner); every other rank 0/1 starter uses the left-corner bonus.  Rank 2 uses nickel;
rank 3 and deeper use dime.  Interceptions, forced fumbles, sacks and every other position are
unchanged.  The single-game box score keeps the engine's line; the franchise season stats (the
reported symptom) get the bonus.  Played and simulated games use the same merge.

The hook is inside the merge's prologue, after the merge saved EBP (the live player) and EDI (the
roster player); the tail replays the two displaced instructions and returns to ``0x1334c8``.  The
retail merge is not re-entered, so the hook cannot recurse, and the weekly-progression wrapper at
``0x134e05`` sees the credited line in its post-merge read.  The fix is a stat correction, not a
gameplay change: it does not move a player, alter a rating, or change a play.
"""

from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_sim_cb_tackles"
CODE_SIZE = 256
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Cornerback tackle credit (experimental)"
HELP_TEXT = ("EXPERIMENTAL. In simulated and played games a starting cornerback's season tackle total gets a "
             "per-game bonus drawn from the NFL distribution through the game's own RNG (about 3.4 a game in all, "
             "with rare zero-tackle games); the nickel and dime corners use lower bonus tables. The single-game box "
             "score keeps the engine's line. Interceptions, forced fumbles, sacks and every other position are "
             "unchanged.")

# The hook is the first two instructions of the merge body (after the prologue saved EBP = live player and
# EDI = roster player): `mov eax,[ebp+0x30] ; mov ebx,[eax]`.  It is inside FUN_001334b0, not at the
# 0x134e05 call, so it shares no byte with b778-pg1's weekly-progression wrapper or b778-f3's 0x134e0a hook.
SITE = 0x001334C3
SITE_BEFORE = bytes.fromhex("8b45308b18")       # mov eax,[ebp+0x30] ; mov ebx,[eax]
RETAIL_PG1_CALL = b"\xe8" + struct.pack("<i", 0x001334B0 - 0x00134E05 - 5)   # the call b778-pg1 replaces
RESUME = 0x001334C8
MERGE = 0x001334B0
MERGE_SIZE = 0x2E8                # 0x1334b0..0x133798 (ret 8)
MERGE_SHA256 = "8707a68d8dc6481ee3d01385cef25162a5715c5e656f383852b191ef35470ea5"
# v0.6.1 carries a 7-byte cave jump at 0x1336b2 from the team-column owner; the merge logic is intact.
V061_MERGE_SHA256 = "6ae07e90d515c3611b0eac54b0d11e52e1b888adb48794db9c2d9e7f07fd2204"

# NFL-calibrated bonus draws (1/128 cumulative): the engine already credits a starting corner some tackles, so
# the owner draws the shortfall as a bonus rather than a whole line.  Means are calibrated to the measured retail
# baseline (nflverse-style per-game engine line: LCB about 1.4, RCB about 0.45, nickel about 0.2, dime about 0.1)
# so the season total lands near the NFL starter mean (3.35), nickel (2.56) and dime (1.10).  The tables are
# cumulative counts out of 128, ending at 128; the first bin is the zero-bonus probability, so a zero-tackle game
# stays possible when the engine also credited none.
LCB_CDF = (14, 56, 92, 110, 119, 124, 126, 127, 128)                     # mean 2.00, 10.9% zero
RCB_CDF = (10, 34, 62, 86, 104, 115, 122, 125, 127, 128)                 # mean 2.87, 7.8% zero
NICKEL_CDF = (14, 44, 78, 103, 117, 124, 127, 128)                       # mean 2.26, 10.9% zero
DIME_CDF = (44, 90, 114, 123, 127, 128)                                  # mean 1.11, 34.4% zero
TABLES = bytes(LCB_CDF + RCB_CDF + NICKEL_CDF + DIME_CDF)
ROLE_OFFSETS = (0, len(LCB_CDF), len(LCB_CDF) + len(RCB_CDF),
                len(LCB_CDF) + len(RCB_CDF) + len(NICKEL_CDF))
TABLE_OFF = 192                   # fixed offset in the 256-byte cave; the assembler refuses to cross it
FN_RAND = 0x00048BC0              # () -> eax: the game's global subtract-with-borrow RNG
FN_GAMES, FN_HISTORY_ADD = 0x0014EE40, 0x0014F450   # current-slot stat read; additive history write (ret 4)
WEEK = 0x00E576B4


class SimCbTacklesError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise SimCbTacklesError(message)


def code_for(code_va):
    """The owner's tail at the merge-body hook.

    Entry (0x1334c3): EBP = live player, EDI = roster player; the merge prologue has run.  The tail
    runs under pushad, so it may use every register, and ends by replaying the two displaced
    instructions and returning to 0x1334c8.  A cornerback whose current-season games count is this
    game's week (before or after the games credit) played this game.  It draws a per-game bonus from
    the role's cumulative table with the game's RNG and adds it to the native career field 18 (season
    tackles); the engine's own game line is untouched, so a zero-bonus draw is a zero-tackle game
    when the engine also credited none.
    """
    from .nfl2k5_draft_ai import _Asm
    a = _Asm(code_va)
    a.b("60")                     # pushad
    a.b("8b7530")                 # mov esi, [ebp+0x30]      ; game tackle record
    a.b("85f6")                   # test esi, esi
    a.j32("0f84", "done")
    a.b("807f3504")               # cmp byte [edi+0x35], 4   ; cornerback
    a.j32("0f85", "done")
    a.b("33d2")                   # xor edx, edx
    a.b("89f9")                   # mov ecx, edi
    a.call(FN_GAMES)              # eax = games this season in the current slot
    a.b("0fb60db476e500")         # movzx ecx, byte [WEEK]
    a.b("49")                     # dec ecx                  ; week-1
    a.b("39c8")                   # cmp eax, ecx             ; played this game?
    a.j8("74", "addpath")
    a.b("41")                     # inc ecx                  ; or week (after the games credit)
    a.b("39c8")                   # cmp eax, ecx
    a.j32("0f85", "done")
    a.label("addpath")
    a.b("8b4728")                 # mov eax, [edi+0x28]      ; depth rank/side word
    a.b("89c1")                   # mov ecx, eax
    a.b("c1e90a")                 # shr ecx, 10
    a.b("83e107")                 # and ecx, 7               ; rank
    a.b("bb" + struct.pack("<I", (code_va + TABLE_OFF) & 0xFFFFFFFF).hex())  # mov ebx, tables
    a.b("83f901")                 # cmp ecx, 1
    a.j8("77", "deep")
    a.b("c1e80d")                 # shr eax, 13
    a.b("83e007")                 # and eax, 7               ; side
    a.b("85c0")                   # test eax, eax
    a.j8("75", "role")            # rank 0 or 1, side != 0: the left-corner table
    a.b("83f901")                 # cmp ecx, 1
    a.j8("75", "role")
    a.b("83c3%02x" % ROLE_OFFSETS[1])  # add ebx, 9          ; right corner table
    a.j8("eb", "role")
    a.label("deep")
    a.b("83f902")                 # cmp ecx, 2
    a.j8("75", "dime")
    a.b("83c3%02x" % ROLE_OFFSETS[2])  # add ebx, 19         ; nickel table
    a.j8("eb", "role")
    a.label("dime")
    a.b("83c3%02x" % ROLE_OFFSETS[3])  # add ebx, 27         ; dime table
    a.label("role")
    a.call(FN_RAND)               # eax = rand
    a.b("257f000000")             # and eax, 0x7f
    a.b("33c9")                   # xor ecx, ecx
    a.label("scan")
    a.b("0fb6140b")               # movzx edx, byte [ebx+ecx]
    a.b("83fa80")                 # cmp edx, 128             ; end of this role's table
    a.j8("73", "found")
    a.b("39d0")                   # cmp eax, edx
    a.j8("72", "found")
    a.b("41")                     # inc ecx
    a.j8("eb", "scan")
    a.label("found")              # ecx = drawn bonus
    a.b("51")                     # push ecx                 ; the bonus
    a.b("6a12")                   # push 18
    a.b("5a")                     # pop edx                  ; field 18: tackles
    a.b("89f9")                   # mov ecx, edi
    a.call(FN_HISTORY_ADD)        # ret 4 cleans the bonus
    a.label("done")
    a.b("61")                     # popad
    a.b("8b4530")                 # mov eax, [ebp+0x30]      ; displaced
    a.b("8b18")                   # mov ebx, [eax]           ; displaced
    a.b("c3")                     # ret to 0x1334c8
    body = a.assemble()
    require(len(body) <= TABLE_OFF, f"cornerback tackle tail is {len(body)} bytes, table offset {TABLE_OFF}")
    return (body.ljust(TABLE_OFF, b"\xcc") + TABLES).ljust(CODE_SIZE, b"\xcc")


def sites(code_va):
    return [("merge_body", SITE, SITE_BEFORE,
             b"\xe8" + struct.pack("<i", code_va - SITE - 5))]


def _recognize(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocation(payload) if present else None
    edits = sites(owned["va"] if owned else 0)
    states = set()
    for _name, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if owned and raw == after else "foreign")
    if owned:
        raw = image.read(owned["va"], CODE_SIZE)
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == code_for(owned["va"]) else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed cornerback tackle site/code")
    context = image.read(MERGE, MERGE_SIZE)
    require(len(context) == MERGE_SIZE, "short retail merge context")
    content = bytearray(context)
    content[SITE - MERGE:SITE - MERGE + len(SITE_BEFORE)] = SITE_BEFORE   # our own hook back to retail
    merge_hash = hashlib.sha256(content).hexdigest()
    require(merge_hash in (MERGE_SHA256, V061_MERGE_SHA256), "Foreign post-game merge context")
    return next(iter(states))


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign cornerback tackle allocation")
    return rows[0]


def status(payload):
    try:
        return _recognize(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError):
        return "foreign"


def apply(payload):
    """Install, or replay an identical installation."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    state = status(payload)
    if state == "foreign":
        raise SimCbTacklesError("the source executable is not retail or Cornerback tackle credit")
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "Cornerback tackle credit needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _name, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"cornerback tackle site {va:#x} is not retail")
        buf[off:off + len(new)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied", "cornerback tackle postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va),
                        before_sha256=hashlib.sha256(before).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result),
                        file_growth=len(result) - len(before), allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex())
                               for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "SITE", "SITE_BEFORE", "RESUME", "RETAIL_PG1_CALL", "BUILD_CAPTION", "HELP_TEXT",
           "code_for", "sites", "allocation", "status", "apply", "SimCbTacklesError"]
