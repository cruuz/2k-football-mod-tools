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

Regular-season games only, and only a corner the game credits with a game (b780 n3).  Report (v0.8,
SWeaR, Discord 11/02): ``Players recording tackles before the first game of the season is played``
(Player Card: the new season's row with Games 0 and TKL 4, another with Games 0 and TKL 2).  The merge
runs for preseason (stage 7) and playoff (stage 9) games too; retail writes those games into the
postseason history class (``0x133634``: stage 7 or 9 -> ``FUN_0014edb0(1)``, back to 0 at ``0x1336b2``),
so the regular-season row never sees them.  This hook runs before that switch, so its bonus always
went into the regular-season row, and it decided "played this game" by ``games this season == week
or week - 1`` instead of asking the game.  Preseason week 1 (week index 1, every club plays) matched
``0 == week - 1`` for every corner on the roster: one bonus draw into the new season's row before
any regular-season game (the Hall of Fame pair also matched at week 0).  The Wild Card week (week
index 18 in the 18-week season) matched ``17 == week - 1`` for every corner who played all 17 games.
In the regular season a deep corner the engine never puts on the field (games 0) matched at weeks 0
and 1: the released v0.8 executable's simulated seasons had 51-57 players with tackles and 0 games,
every one a cornerback.  The tail now requires the regular-season stage (``[0xE576A4] == 8``) and the
game's own games-played value for this player (game stat 99 through ``0xCB240``, bank 0: the same
read and the same rounding by which the merge credits career field 0), so the bonus lands only in a
game the season row counts.  Existing rows keep what earlier versions wrote.

The hook is inside the merge's prologue, after the merge saved EBP (the live player) and EDI (the
roster player); the tail replays the two displaced instructions and returns to ``0x1334c8``.  The
retail merge is not re-entered, so the hook cannot recurse, and the weekly-progression wrapper at
``0x134e05`` sees the credited line in its post-merge read.  The fix is a stat correction, not a
gameplay change: it does not move a player, alter a rating, or change a play.

The same 256-byte cave carries a small second entry (``GUARD_OFFSET``) at the lineup picker's two depth
calls, written for the franchise scheduled-game simulator. Report (b779, v0.7): an injured running back scored a touchdown in a
simulated ("Game Cast") game. The simulator's lineup picker ``FUN_000e8790`` asks
``FUN_000e8340`` whether a player fills a depth slot.  That routine's own injured path keys on the
save's status (`+0x24` bits 28..30), so a player whose status is 0 or was cleared while the
injury report still shows weeks out (`+0x20` bits 22..29) is accepted.  In game mode
``[0xE5FF80] == 4`` the guard refuses any player with the injured bit (`+0x20` bit 31) or a nonzero
weeks field before retail's check runs, so the picker walks to the next depth player.

Correction (b780 modes2, Q28): mode 4 is not only the scheduled simulator. A live Play Now game runs in
mode 4 too, and ``FUN_000e8790`` is also the CPU's live lineup picker: ``FUN_000e89f0`` calls it at
``0xE8B20``, and its callers ``0x18A641``, ``0x204F82`` and ``0x2056E2`` are live-game CPU personnel
paths. So the guard also runs in live Play Now lineups. The shipped roster has no player with those
fields set (0 of 4,164 after boot), so live Play Now picks the same players as retail; a franchise
roster carried into Play Now would skip injured players the same way the simulator does. Played
franchise games (modes 5..7), practice, and every other caller of ``FUN_000e8340`` keep retail.  This
is a lineup eligibility guard only; no injury field is written and no retail routine is changed.
"""

from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_sim_cb_tackles"
CODE_SIZE = 256
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Cornerback tackle credit and sim injuries (experimental)"
HELP_TEXT = ("EXPERIMENTAL. In simulated and played regular-season games a starting cornerback's season tackle "
             "total gets a per-game bonus drawn from the NFL distribution through the game's own RNG (about 3.4 a "
             "game in all, with rare zero-tackle games); the nickel and dime corners use lower bonus tables. Only a "
             "corner who played the game gets it, and preseason and playoff games never add to the season row. The "
             "single-game box score keeps the engine's line. Interceptions, forced fumbles, sacks and every other "
             "position are unchanged. Simulated franchise games also leave out any player whose injury report shows "
             "weeks out, including a probable player or one whose status field was cleared.")

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

# The simulator's lineup picker FUN_000e8790 asks FUN_000e8340 at two call sites (forward and reverse depth
# search). The surrounding code, after restoring those two retail calls, is byte-identical in the USA retail,
# v0.6.1 and v0.7 executables. The guard is gated on game mode 4 (the scheduled sim, and live Play Now: see the
# docstring's b780 correction) so played franchise games and every other caller keep retail.
PICKER = 0x000E8790
PICKER_PIN = (0x000E87F0, 0x110, "e9ca4dc737e13b19b200884c27c353a287a6c7f8b0601f3a0b2cf3e7d64d1598")
GUARD_HOOKS = ((0x000E8864, bytes.fromhex("e8d7faffff")),   # call 0xe8340, forward depth search
               (0x000E88EC, bytes.fromhex("e84ffaffff")))  # call 0xe8340, reverse depth search
SIM_MODE = 0x00E5FF80             # game-mode word: 4 = the franchise scheduled-game simulator and live Play Now
INJURY_WEEKS = 0xBFC00000         # +0x20 bit 31 (injured) plus bits 22..29 (weeks out)
GUARD_OFFSET = 160                # second entry inside the 256-byte cave, before TABLE_OFF (192)

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
WEEK = 0x00E576B4                 # kept for callers; the tail no longer reads the week (b780 n3)
# b780 n3: the bonus is a regular-season credit for a corner who played this game.
STAGE = 0x00E576A4                # league stage word (FUN_000c4bb0): 7 preseason, 8 regular season, 9 playoffs
REGULAR_SEASON = 8                # the only stage whose games the merge writes into the regular-season class
FN_GAME_STAT = 0x000CB240         # (ecx = live player, edx = game stat, push bank) -> st0, ret 4
GAME_PLAYED = 99                  # game stat the merge credits to career field 0 (games) through 0x133400
HALF = 0x3F000000                 # 0.5f: 0x133400 rounds half up, so a credit of 1 or more needs >= 0.5


class SimCbTacklesError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise SimCbTacklesError(message)


def code_for(code_va):
    """The owner's tail at the merge-body hook.

    Entry (0x1334c3): EBP = live player, EDI = roster player; the merge prologue has run.  The tail
    runs under pushad, so it may use every register, and ends by replaying the two displaced
    instructions and returning to 0x1334c8.  A cornerback gets the bonus only in a regular-season game
    (stage 8: the merge writes preseason and playoff games into the postseason class after this hook)
    that the game credits him with (game stat 99, bank 0, at least 0.5: exactly when the merge adds a
    game to career field 0).  It draws a per-game bonus from the role's cumulative table with the
    game's RNG and adds it to the native career field 18 (season tackles); the engine's own game line is
    untouched, so a zero-bonus draw is a zero-tackle game when the engine also credited none.
    """
    from .nfl2k5_draft_ai import _Asm
    a = _Asm(code_va)
    a.b("60")                     # pushad
    a.b("8b7530")                 # mov esi, [ebp+0x30]      ; game tackle record
    a.b("85f6")                   # test esi, esi
    a.j32("0f84", "done")
    a.b("807f3504")               # cmp byte [edi+0x35], 4   ; cornerback
    a.j32("0f85", "done")
    # b780 n3: a regular-season game only (preseason 7 and playoffs 9 go to the postseason class at 0x133634)
    a.b("833d" + struct.pack("<I", STAGE).hex() + "%02x" % REGULAR_SEASON)  # cmp dword [stage], 8
    a.j32("0f85", "done")
    # b780 n3: only a corner this game credits with a game played (the merge's own read of game stat 99)
    a.b("6a00")                   # push 0                   ; bank 0: this game's line
    a.b("6a%02x5a" % GAME_PLAYED) # push 99 ; pop edx        ; games played in this game
    a.b("89e9")                   # mov ecx, ebp             ; the live player
    a.call(FN_GAME_STAT)          # st0 = 0.0 / 1.0 (ret 4 pops the bank)
    a.b("50")                     # push eax                 ; scratch slot
    a.b("d91c24")                 # fstp dword [esp]         ; keeps the x87 stack balanced
    a.b("58")                     # pop eax                  ; the float's bits
    a.b("3d" + struct.pack("<I", HALF).hex())  # cmp eax, 0.5f (signed: negative floats are below)
    a.j8("7c", "done")            # jl done                  ; no game credited, no bonus
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
    used = len(a.assemble())
    require(used <= GUARD_OFFSET, f"merge body is {used} bytes, guard offset {GUARD_OFFSET}")
    a.b("cc" * (GUARD_OFFSET - used))
    a.label("sim_guard")
    # Entry from the two picker call sites: EDX = the player record, ECX and the stack args are the
    # caller's slot request. Mode 4 only (the scheduled sim and live Play Now); any injured bit or weeks value is refused.
    a.b("803d" + struct.pack("<I", SIM_MODE).hex() + "04")   # cmp byte [mode], 4
    a.j8("75", "guard_retail")                                # not the scheduled sim: retail
    a.b("f74220" + struct.pack("<I", INJURY_WEEKS).hex())     # test dword [edx+0x20], injured | weeks
    a.j8("74", "guard_retail")                                # healthy: retail
    a.b("31c0")                                               # xor eax, eax  -> does not fill the slot
    # b779-int1: FUN_000e8340 is callee-clean (every exit is `ret 0xc`), so the refusal must pop the caller's three
    # stack arguments too; a plain `ret` left 12 bytes on the picker's stack and the scheduled sim crashed in its
    # first week (Unicorn season run: a null-ish team pointer read at 0xE0890).
    a.b("c20c00")                                             # ret 0xc
    a.label("guard_retail")
    a.jmp_abs(0x000E8340)                                     # tail-jump: keep the caller's stack args
    body = a.assemble()
    require(a.labels["sim_guard"] == GUARD_OFFSET,
            f"sim guard is at {a.labels['sim_guard']}, expected {GUARD_OFFSET}")
    require(len(body) <= TABLE_OFF, f"cornerback tackle tail is {len(body)} bytes, table offset {TABLE_OFF}")
    return (body.ljust(TABLE_OFF, b"\xcc") + TABLES).ljust(CODE_SIZE, b"\xcc")


def sites(code_va):
    guard = code_va + GUARD_OFFSET
    return [("merge_body", SITE, SITE_BEFORE,
             b"\xe8" + struct.pack("<i", code_va - SITE - 5)),
            ("sim_guard_forward", GUARD_HOOKS[0][0], GUARD_HOOKS[0][1],
             b"\xe8" + struct.pack("<i", guard - GUARD_HOOKS[0][0] - 5)),
            ("sim_guard_reverse", GUARD_HOOKS[1][0], GUARD_HOOKS[1][1],
             b"\xe8" + struct.pack("<i", guard - GUARD_HOOKS[1][0] - 5))]


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
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == code_for(owned["va"])
                   else "previous" if raw == _previous_code_for(owned["va"]) else "foreign")
    if states == {"applied", "previous"}:
        states = {"previous"}   # b780-int: the same hooks with the beta-79 tail (a v0.8 executable)
    require(states in ({"retail"}, {"applied"}, {"previous"}), "Foreign or mixed cornerback tackle site/code")
    context = image.read(MERGE, MERGE_SIZE)
    require(len(context) == MERGE_SIZE, "short retail merge context")
    content = bytearray(context)
    content[SITE - MERGE:SITE - MERGE + len(SITE_BEFORE)] = SITE_BEFORE   # our own hook back to retail
    # b779-int1: b779-sim2's season realism owner hooks the same merge (its tackle entry at 0x1334d3). When that
    # owner is installed, its exact hook bytes inside the merge are put back to retail before hashing; any other
    # byte, or a different hook, still makes the context foreign ("cornerback tackle credit did not survive the
    # final passes" stopped the observed full build once both were on).
    from . import nfl2k5_sim_realism as realism
    realism_rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == realism.OWNER and r["kind"] == "code"]
    if realism_rows:
        # b780 n6: the installed revision's hooks (a v0.8 executable carries the beta-79 one, at other code offsets)
        for _name, va, before, after in realism.installed_sites(payload):
            if MERGE <= va and va + len(before) <= MERGE + MERGE_SIZE and bytes(content[va - MERGE:va - MERGE + len(after)]) == after:
                content[va - MERGE:va - MERGE + len(before)] = before
    # b779-int1: the defensive try owner (era rules) jumps out of the merge at 0x1336B2 to its own code. The v0.6.1
    # pin above holds that jump at v0.6.1's cave address only; wherever the allocator now puts that code, its exact
    # installed jump reads as the retail instructions it replaced (RC build try 9 stopped: "the source executable is
    # not retail or Cornerback tackle credit"). Any other byte there still reads foreign.
    from . import nfl2k5_defensive_try as defensive_try
    va, before, _kind = defensive_try.HOOKS["season_merge"]
    before = bytes.fromhex(before)
    at = va - MERGE
    if bytes(content[at:at + len(before)]) != before and defensive_try.status(payload) == "applied":
        labels = defensive_try.assembled(payload)[3]
        if bytes(content[at:at + len(before)]) == defensive_try._hook_bytes("season_merge", labels):
            content[at:at + len(before)] = before
    merge_hash = hashlib.sha256(content).hexdigest()
    require(merge_hash in (MERGE_SHA256, V061_MERGE_SHA256), "Foreign post-game merge context")
    picker_va, picker_size, picker_digest = PICKER_PIN
    picker = bytearray(image.read(picker_va, picker_size))
    for hook_va, retail in GUARD_HOOKS:            # our own two hooks back to retail
        picker[hook_va - picker_va:hook_va - picker_va + len(retail)] = retail
    require(hashlib.sha256(picker).hexdigest() == picker_digest, "Foreign scheduled-sim lineup picker")
    return next(iter(states))


def _previous_code_for(code_va):
    """b780-int: the beta-79 / v0.8 tail (before n3's regular-season gate), from the frozen beta-79 module."""
    from . import nfl2k5_sim_cb_tackles_b779 as b779
    return b779.code_for(code_va)


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
    if state == "previous":
        # b780-int: a beta-79 / v0.8 install (same cave, hooks and tables) is upgraded in place to the
        # regular-season tail (b780 n3): only the owner's own code bytes change
        code_va = allocation(payload)["va"]
        result, _ = space.install_code(payload, OWNER, code_for(code_va), previous=_previous_code_for(code_va))
        require(status(result) == "applied", "cornerback tackle credit upgrade postcondition failed")
        return result, dict(common, status="applied", upgraded_from="previous",
                            changed_bytes=space.count_differing_bytes(payload, result), edits=[])
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
