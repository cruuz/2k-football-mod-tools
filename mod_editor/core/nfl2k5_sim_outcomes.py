"""Simulated-game outcomes (beta 81): home field, game-day form, the simulator's two-point chart and its tie roll.

EXPERIMENTAL / UNWITNESSED.  Part of the Studio option "Simulated season realism" (``sim_realism``; it is installed
and removed with ``nfl2k5_sim_realism``).  Everything here acts inside the native scheduled simulator (``0x10B280``
and its state handlers), so it changes games the console simulates (franchise weeks, Gamecast, other simulations),
never a played game, a save or a roster.

What the simulator did (retail bytes, unchanged in the beta 81 standard edition; the lane's measurements are in
b81/game-outcomes/DESIGN.txt, 40 stored seasons):

* **No home field.**  The week simulator passes the home club (schedule cell byte +1, ``0xC4E00``) as side 0 and the
  away club as side 1 (``0xC7A89``..``0xC7B53`` -> ``0x10B280``); every later reference to the two sides is symmetric
  and the opening possession is a 0.5 draw (``0x10726E``).  Home clubs won 49.4% of 10,880 games (NFL 2021-25: 54.0%,
  +2.06 points).
* **No game-to-game form.**  Every play draws from fixed ratings, so a club's yards and points vary less from one game
  to the next than in the NFL (club-game yards SD 79.0 vs 83.9; residual margin SD 11.3 vs 12.2).
* **A 2004 two-point chart.**  ``0x103260`` (one caller, ``0x107874``) went for two only in the fourth quarter at six
  margins and otherwise on a 0.5% draw: 0.080 tries a club-game against the NFL's 0.244.
* **No ties after a franchise's first season.**  ``0x10B2E9`` rolls the game's tie allowance only when the caller's
  argument ``[0xE576C8]`` is set; franchise creation sets it (``0x13EE28``) and building the first playoff bracket clears
  it (``0x2A8154``), and no later season sets it again.  So from season two every simulated regular-season overtime
  repeated until someone scored (0 ties in 10,880 games; NFL about 0.8 a season), and the overtime owner's 10-minute
  regular-season period never applied.

The changes:

* **Commit hook** (``0x106480``, the one routine every scrimmage gain goes through, called from 0x107D0D, 0x1085BD,
  0x10921A, 0x1094E4 and 0x10A6AC): on a scrimmage play (``[0xA971C0]`` == 0), a positive gain short of the goal line is
  multiplied by the offense's game factor ``m``.  Gains that reach the goal line (every touchdown, breakaways included),
  losses and try plays are unchanged.  ``m`` is set once per fixture and side:
  ``m = (1 + HOME_EDGE) x (1 + FORM_SIGMA x z)`` for the home side and ``(1 - HOME_EDGE) x (1 + FORM_SIGMA x z)`` for the
  away side, clamped to ``[M_LOW, M_HIGH]``; ``z`` is a standard-normal draw (the sum of four bytes of a hash, Irwin-Hall)
  from a private hash of the fixture (season, week, both clubs) and the two match-generator words read once when the
  fixture is first seen.  Nothing is drawn from or written to the match generator.
* **Two-point chart** (``0x103260`` jumps to the page): the played game's Modern 2 chart
  (``nfl2k5_cpu_money_downs.two_point_decision``): go for two when the threshold for the margin after the touchdown is
  "always", or when the game time left is at most the threshold; in overtime at -2 or -1 (with the overtime owner's
  both-possessions rule a -1 margin only arises after both clubs have had the ball).  No draw.
* **Tie roll** (``0x10B2E9`` calls the page): the roll also happens in a franchise's regular season (mode word
  ``[0xE576A0]`` 2, stage ``[0xE576A4]`` 8), whatever the stale flag says.  With the overtime owner's simulator rule this
  gives every regular season its 10-minute overtime that can end tied; the postseason never ties.  One extra
  match-generator draw per such game (the roll itself).

* **End of regulation after the last play** (``0x106423`` and ``0x10B251`` call the page): a play's commit
  (``0x106480``) runs the clock routine ``0x1061F0`` before the handler has finished the play; when the clock ran out it
  ended regulation on the scores from before the play (state ``0x12``), and the handler then went on (an interception
  at ``0x108AC0`` writes state ``0xB``, a last kick credits its points), so the game continued into a phantom overtime
  and last-play points landed in the overtime column (85 of 10,880 stored games; some results flipped).  Now a
  regulation end reached from the commit (return address ``0x106A14``) is tentative: the period index goes back to the
  fourth quarter for the rest of the play and, before the next state handler, the result is decided on the scores after
  the play: different -> the game is over, level -> overtime (period 4, its kickoff, as ``0x106450``).  A regulation
  end before a play keeps the retail branch.  The tie roll's setup clears the flag for every game.

One fixed page at ``SIM_OUTCOMES_VA`` (``nfl2k5_xbe_space``), placed like the quarterback pages; every site is pinned
to its retail bytes; Retail (``remove``) restores the sites and empties the page.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_sim_outcomes"
LABEL = "EXPERIMENTAL / UNWITNESSED"
BUILD_CAPTION = "Simulated game outcomes"
HELP_TEXT = (
    "Part of Simulated season realism. In games the CPU simulates, home clubs get a home-field edge (they win about 54% "
    "of games, as in the modern NFL), clubs have better and worse days, CPU coaches use the same modern two-point chart "
    "in simulated games as in played ones, a regular-season game still tied after its 10-minute overtime ends as a tie "
    "in every season, not only the first, and a game decided on the last play of regulation ends there instead of going "
    "on into an overtime. Played games, ratings and rosters are unchanged.")
CODE_SIZE = 0x1000
PLACEHOLDER_VA = 0x1531000      # nfl2k5_xbe_space.SIM_OUTCOMES_VA (checked in apply)

# ---- calibration levers (game-outcomes DESIGN.txt; fitted on the calibration roots, frozen before the confirmation) --
HOME_EDGE = 0.045               # home gains x (1 + edge), away gains x (1 - edge)
FORM_SIGMA = 0.08               # SD of the per-game form factor
M_LOW, M_HIGH = 0.70, 1.30      # clamp of the game factor
IRWIN_HALL_MEAN = 510.0         # four bytes: mean 4 x 127.5
IRWIN_HALL_SD = 147.80          # four bytes: sqrt(4 x (256^2 - 1) / 12)

# ---- simulator globals (all read in the retail executable; see DESIGN.txt) -------------------------------------------
SIM_OFFENSE = 0x00A9719C
SIM_DEFENSE = 0x00A971A0
SIM_KIND = 0x00A971C0           # 0 scrimmage, 1 kickoff, 4 try
SIM_LINE_TO_GOAL = 0x00A97200
SIM_PERIOD_INDEX = 0x00A971F0   # 0..3 quarters, 4 overtime
SIM_CLOCK_FRACTION = 0x00A971F8
SIM_RECORD = 0x00A97210         # the replayed first instruction of 0x106480 reads it
HOME_SIDE = 0x00A96B68          # side 0 summary; [HOME_SIDE] = the home club's team object
AWAY_SIDE = 0x00A96E80
SEASON, WEEK = 0x00E576B8, 0x00E576B4
MODE, STAGE = 0x00E576A0, 0x00E576A4
MATCH_WORDS = (0x00E5FCA8, 0x00E5FCB0)
FN_TEAM_SCORE = 0x00102200      # eax = side summary -> st0 = its score
FN_FLOAT_TO_INT = 0x00100F00    # stdcall(float) -> eax

# ---- sites ------------------------------------------------------------------------------------------------------------
COMMIT_SITE = 0x00106480
COMMIT_RETAIL = bytes.fromhex("8b0d1072a900")       # mov ecx, [0xA97210]
COMMIT_RESUME = COMMIT_SITE + len(COMMIT_RETAIL)
TRY_SITE = 0x00103260
TRY_RETAIL = bytes.fromhex("51a19c71a900")          # push ecx; mov eax, [0xA9719C]
TIES_SITE = 0x0010B2E9
TIES_RETAIL = bytes.fromhex("395d107421")           # cmp [ebp+0x10], ebx; je 0x10B30F
TIES_SKIP = 0x0010B30F
REG_SITE = 0x00106423
REG_RETAIL = bytes.fromhex("3bfb7429c705b871a90012000000")   # cmp edi,ebx; je 0x106450; mov [state], 0x12
REG_OVERTIME = 0x00106450        # retail: tied at the end of regulation -> overtime kickoff (state 1), returns 4
COMMIT_CLOCK_RETURN = 0x00106A14  # 0x1061F0 called by the commit (mid-play)
STEP_SITE = 0x0010B251
STEP_RETAIL = bytes.fromhex("e8ca9dffff")                    # call 0x105020 (before every state handler)
FN_DISPATCH = 0x00105020
SIM_STATE = 0x00A971B8

# ---- page layout --------------------------------------------------------------------------------------------------------
COMMIT_OFF, TRY_OFF, TIES_OFF, REG_OFF = 0x000, 0x200, 0x300, 0x380
DATA_OFF = 0xE00
MARK = b"SIMOUT1\0"
D_MARK, D_HOME_UP, D_HOME_DOWN, D_FORM_UNIT, D_LOW, D_HIGH, D_MEAN, D_C90 = 0x00, 0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x20
D_THRESHOLDS = 0x24             # 33 bytes: margins -16..+16
STATE_OFF = 0xE80
S_KEY, S_FACTORS, S_SEED, S_FIXTURES, S_SCALED, S_TMP, S_PENDING = 0x00, 0x04, 0x0C, 0x10, 0x14, 0x18, 0x1C
S_DEFERRED, S_FINAL, S_OVERTIME = 0x20, 0x24, 0x28   # counters: deferred regulation ends, decided final, overtime
HOME_TAG, AWAY_TAG = 0x484F4D45, 0x41574159          # "HOME", "AWAY"
GOLDEN = 0x9E3779B1


class SimOutcomesError(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise SimOutcomesError(message)


def _u32(value: int) -> str:
    return struct.pack("<I", value & 0xFFFFFFFF).hex()


def _f32(value: float) -> bytes:
    return struct.pack("<f", value)


def two_point_thresholds() -> bytes:
    """Modern 2's threshold bytes for margins -16..+16 (units of 10 s of game time left; 255 always, 0 never), from
    the played game's owner so the two charts cannot drift apart."""
    from . import nfl2k5_cpu_money_downs as downs
    table = bytes(downs.m2_tables()[2])
    _require(len(table) == 33, "the Modern 2 two-point table has 33 margins")
    return table


# ------------------------------------------------------------------------------------------------ the page's code
def _commit_code(a: _Asm, page: int) -> None:
    data, state = page + DATA_OFF, page + STATE_OFF
    a.label("commit")
    a.b("833d" + _u32(SIM_KIND) + "00")             # cmp dword [kind], 0  (scrimmage plays only)
    a.j32("0f85", "commit_done")
    a.b("a1" + _u32(SIM_OFFENSE))                   # mov eax, [offense]
    a.b("31d2")                                     # xor edx, edx  (side 0, home)
    a.b("3d" + _u32(HOME_SIDE))
    a.j8("74", "commit_side")
    a.b("42")                                       # inc edx  (side 1, away)
    a.b("3d" + _u32(AWAY_SIDE))
    a.j32("0f85", "commit_done")
    a.label("commit_side")
    a.b("52")                                       # push edx
    a.call(page + _LABELS["fixture"])
    a.b("5a")                                       # pop edx
    a.b("d9442404")                                 # fld dword [esp+4]  (the gain)
    a.b("d9ee")                                     # fldz
    a.b("dff1")                                     # fcomip st, st(1)   0 vs gain
    a.j8("73", "commit_pop")                        # jae: gain <= 0 (or NaN) -> unchanged
    a.b("d905" + _u32(SIM_LINE_TO_GOAL))            # fld dword [line to goal]
    a.b("dff1")                                     # fcomip st, st(1)   line vs gain
    a.j8("76", "commit_pop")                        # jbe: the gain reaches the goal line -> unchanged
    a.b("d80c95" + _u32(state + S_FACTORS))         # fmul dword [factors + edx*4]
    a.b("d95c2404")                                 # fstp dword [esp+4]
    a.b("ff05" + _u32(state + S_SCALED))            # inc dword [scaled]
    a.j8("eb", "commit_done")
    a.label("commit_pop")
    a.b("ddd8")                                     # fstp st(0)
    a.label("commit_done")
    a.b(COMMIT_RETAIL.hex())                        # the replayed mov ecx, [0xA97210]
    a.jmp_abs(COMMIT_RESUME)

    # fixture(): keep this fixture's two factors current. Clobbers eax, ecx, edx.
    a.label("fixture")
    a.b("a1" + _u32(SEASON))
    a.b("69c0" + _u32(GOLDEN))                      # imul eax, eax, golden
    a.b("3305" + _u32(WEEK))
    a.call(page + _LABELS["mix32"])
    a.b("3305" + _u32(HOME_SIDE))                   # xor eax, [home team object]
    a.call(page + _LABELS["mix32"])
    a.b("3305" + _u32(AWAY_SIDE))
    a.call(page + _LABELS["mix32"])
    a.b("3b05" + _u32(state + S_KEY))
    a.j8("75", "fx_new")
    a.b("c3")
    a.label("fx_new")
    a.b("a3" + _u32(state + S_KEY))
    a.b("3305" + _u32(MATCH_WORDS[0]))              # read, never draw
    a.call(page + _LABELS["mix32"])
    a.b("3305" + _u32(MATCH_WORDS[1]))
    a.call(page + _LABELS["mix32"])
    a.b("a3" + _u32(state + S_SEED))
    a.b("ff05" + _u32(state + S_FIXTURES))
    a.b("35" + _u32(HOME_TAG))
    a.call(page + _LABELS["mix32"])
    a.call(page + _LABELS["form"])
    a.b("d80d" + _u32(data + D_HOME_UP))
    a.call(page + _LABELS["clamp"])
    a.b("d91d" + _u32(state + S_FACTORS))
    a.b("a1" + _u32(state + S_SEED))
    a.b("35" + _u32(AWAY_TAG))
    a.call(page + _LABELS["mix32"])
    a.call(page + _LABELS["form"])
    a.b("d80d" + _u32(data + D_HOME_DOWN))
    a.call(page + _LABELS["clamp"])
    a.b("d91d" + _u32(state + S_FACTORS + 4))
    a.b("c3")

    # form(eax = hash): st0 = 1 + sigma x z, z = (sum of the hash's four bytes - 510) / 147.80
    a.label("form")
    a.b("0fb6d0")                                   # movzx edx, al
    a.b("0fb6cc")                                   # movzx ecx, ah
    a.b("01ca")                                     # add edx, ecx
    a.b("c1e810")                                   # shr eax, 16
    a.b("0fb6c8")                                   # movzx ecx, al
    a.b("01ca")
    a.b("0fb6cc")                                   # movzx ecx, ah
    a.b("01ca")
    a.b("8915" + _u32(state + S_TMP))               # mov [tmp], edx
    a.b("db05" + _u32(state + S_TMP))               # fild dword [tmp]
    a.b("d825" + _u32(data + D_MEAN))               # fsub dword [510.0]
    a.b("d80d" + _u32(data + D_FORM_UNIT))          # fmul dword [sigma / 147.80]
    a.b("d9e8")                                     # fld1
    a.b("dec1")                                     # faddp
    a.b("c3")

    # clamp(st0) to [low, high]
    a.label("clamp")
    a.b("d905" + _u32(data + D_LOW))                # fld low ; low, x
    a.b("dff1")                                     # fcomip: low vs x
    a.j8("72", "clamp_high")                        # jb: low < x
    a.b("ddd8")                                     # fstp st(0)
    a.b("d905" + _u32(data + D_LOW))
    a.label("clamp_high")
    a.b("d905" + _u32(data + D_HIGH))               # fld high ; high, x
    a.b("dff1")                                     # fcomip: high vs x
    a.j8("73", "clamp_ret")                         # jae: high >= x
    a.b("ddd8")
    a.b("d905" + _u32(data + D_HIGH))
    a.label("clamp_ret")
    a.b("c3")

    # mix32: MurmurHash3's 32-bit finalizer (the same as tools/qb_sim_injuries/positions.S); clobbers eax, edx
    a.label("mix32")
    a.b("89c2" "c1ea10" "31d0")                     # mov edx,eax ; shr edx,16 ; xor eax,edx
    a.b("69c0" + _u32(0x85EBCA6B))
    a.b("89c2" "c1ea0d" "31d0")
    a.b("69c0" + _u32(0xC2B2AE35))
    a.b("89c2" "c1ea10" "31d0")
    a.b("c3")


def _try_code(a: _Asm, page: int) -> None:
    data = page + DATA_OFF
    a.label("try")
    a.b("51")                                       # push ecx  (scratch at [esp])
    a.b("a1" + _u32(SIM_OFFENSE))
    a.call(FN_TEAM_SCORE)
    a.b("d91c24")                                   # fstp dword [esp]
    a.b("a1" + _u32(SIM_DEFENSE))
    a.call(FN_TEAM_SCORE)
    a.b("d82c24")                                   # fsubr dword [esp]   offense - defense
    a.b("51" "d91c24")                              # push ecx ; fstp dword [esp]
    a.call(FN_FLOAT_TO_INT)                         # eax = margin (callee pops)
    a.b("8b0d" + _u32(SIM_PERIOD_INDEX))
    a.b("83f904")                                   # cmp ecx, 4
    a.j8("7d", "try_ot")
    a.b("83c010")                                   # add eax, 16
    a.b("83f820")                                   # cmp eax, 32
    a.j8("77", "try_kick")
    a.b("0fb690" + _u32(data + D_THRESHOLDS))       # movzx edx, byte [thresholds + eax]
    a.b("85d2")
    a.j8("74", "try_kick")
    a.b("81faff000000")                             # cmp edx, 255
    a.j8("74", "try_go")
    a.b("b803000000")                               # mov eax, 3
    a.b("29c8")                                     # sub eax, ecx
    a.b("890424")                                   # mov [esp], eax
    a.b("db0424")                                   # fild dword [esp]
    a.b("d805" + _u32(SIM_CLOCK_FRACTION))          # fadd dword [clock fraction]
    a.b("d80d" + _u32(data + D_C90))                # fmul dword [90.0]  -> game time left in 10 s units
    a.b("891424")                                   # mov [esp], edx
    a.b("db0424")                                   # fild dword [esp] ; threshold, time
    a.b("dff1")                                     # fcomip: threshold vs time
    a.b("ddd8")                                     # fstp st(0) (flags kept)
    a.j8("72", "try_kick")                          # jb: threshold < time -> too early
    a.label("try_go")
    a.b("b801000000" "59" "c3")
    a.label("try_kick")
    a.b("31c0" "59" "c3")
    a.label("try_ot")
    a.b("83f8fe")                                   # cmp eax, -2
    a.j8("74", "try_go")
    a.b("83f8ff")                                   # cmp eax, -1
    a.j8("74", "try_go")
    a.j8("eb", "try_kick")


def _ties_code(a: _Asm, page: int) -> None:
    a.label("ties")
    a.b("c605" + _u32(page + STATE_OFF + S_PENDING) + "00")   # a new game: no regulation end pending (R8)
    a.b("837d1000")                                 # cmp dword [ebp+0x10], 0  (the caller's own allowance)
    a.j8("75", "ties_roll")
    a.b("833d" + _u32(MODE) + "02")                 # franchise
    a.j8("75", "ties_skip")
    a.b("833d" + _u32(STAGE) + "08")                # regular season
    a.j8("74", "ties_roll")
    a.label("ties_skip")
    a.b("83c404")                                   # add esp, 4 (drop the return address)
    a.jmp_abs(TIES_SKIP)
    a.label("ties_roll")
    a.b("c3")                                       # back to 0x10B2EE, the roll


def _regulation_code(a: _Asm, page: int) -> None:
    state = page + STATE_OFF
    # Called at 0x106423 (cmp edi,ebx / je / mov [state],0x12 replaced; 9 nops follow, so `ret` lands on 0x106431, the
    # retail game-over tail). [esp+0x14] is 0x1061F0's return address (it pushed ecx, ebx, esi, edi).
    a.label("regulation")
    a.b("817c2414" + _u32(COMMIT_CLOCK_RETURN))     # cmp dword [esp+0x14], 0x106A14  (mid-play, from the commit)
    a.j8("74", "reg_mid_play")
    a.b("3bfb")                                     # cmp edi, ebx  (retail: before a play the scores are final)
    a.j8("75", "reg_over")
    a.b("83c404")                                   # add esp, 4
    a.jmp_abs(REG_OVERTIME)                         # tied: retail's overtime kickoff path
    a.label("reg_over")
    a.b("c705" + _u32(SIM_STATE) + "12000000")
    a.b("c3")
    a.label("reg_mid_play")
    a.b("c705" + _u32(SIM_STATE) + "12000000")      # tentative: the game is over unless the play ties it
    a.b("c705" + _u32(SIM_PERIOD_INDEX) + "03000000")   # the rest of this play is the fourth quarter's
    a.b("c605" + _u32(state + S_PENDING) + "01")
    a.b("ff05" + _u32(state + S_DEFERRED))
    a.b("c3")

    # Called at 0x10B251 in place of `call 0x105020`, before every state handler.
    a.label("step")
    a.b("803d" + _u32(state + S_PENDING) + "00")    # cmp byte [pending], 0
    a.j8("75", "step_decide")
    a.jmp_abs(FN_DISPATCH)
    a.label("step_decide")
    a.b("c605" + _u32(state + S_PENDING) + "00")
    a.b("b8" + _u32(HOME_SIDE))
    a.call(FN_TEAM_SCORE)
    a.b("b8" + _u32(AWAY_SIDE))
    a.call(FN_TEAM_SCORE)                           # st0 away, st1 home
    a.b("dfe9")                                     # fucomip st, st(1)
    a.b("ddd8")                                     # fstp st(0)
    a.j8("7a", "step_final")                        # unordered: treat as decided
    a.j8("75", "step_final")
    a.b("c705" + _u32(SIM_PERIOD_INDEX) + "04000000")   # level after the play: overtime
    a.b("c705" + _u32(SIM_STATE) + "01000000")          # its kickoff, as retail 0x106450
    a.b("ff05" + _u32(state + S_OVERTIME))
    a.jmp_abs(FN_DISPATCH)
    a.label("step_final")
    a.b("c705" + _u32(SIM_STATE) + "12000000")      # the game is over (whatever the play's handler wrote)
    a.b("ff05" + _u32(state + S_FINAL))
    a.jmp_abs(FN_DISPATCH)


_LABELS: dict[str, int] = {}


def _assemble(page: int) -> tuple[bytes, dict[str, int]]:
    blocks = []
    for offset, builder in ((COMMIT_OFF, lambda a: _commit_code(a, page)), (TRY_OFF, lambda a: _try_code(a, page)),
                            (TIES_OFF, lambda a: _ties_code(a, page)), (REG_OFF, lambda a: _regulation_code(a, page))):
        a = _Asm(page + offset)
        builder(a)
        blocks.append((offset, a))
    out = bytearray(b"\xcc" * DATA_OFF)
    labels = {}
    for offset, a in blocks:
        code = a.assemble()
        out[offset:offset + len(code)] = code
        labels.update({name: offset + at for name, at in a.labels.items()})
    return bytes(out), labels


def _labels() -> dict[str, int]:
    """Label offsets inside the page (they do not depend on the page address)."""
    if not _LABELS:
        _LABELS.update({"fixture": 0, "mix32": 0, "form": 0, "clamp": 0})
        _LABELS.update(_assemble(PLACEHOLDER_VA)[1])    # pass 1: sizes and offsets
        _LABELS.update(_assemble(PLACEHOLDER_VA)[1])    # pass 2: the calls resolved
    return dict(_LABELS)


def data_bytes(*, home_edge=HOME_EDGE, form_sigma=FORM_SIGMA) -> bytes:
    _require(0.0 <= home_edge < 0.2 and 0.0 <= form_sigma < 0.3, "home edge or form spread out of range")
    out = bytearray(STATE_OFF - DATA_OFF)
    out[D_MARK:D_MARK + 8] = MARK
    for at, value in ((D_HOME_UP, 1.0 + home_edge), (D_HOME_DOWN, 1.0 - home_edge),
                      (D_FORM_UNIT, form_sigma / IRWIN_HALL_SD), (D_LOW, M_LOW), (D_HIGH, M_HIGH),
                      (D_MEAN, IRWIN_HALL_MEAN), (D_C90, 90.0)):
        out[at:at + 4] = _f32(value)
    out[D_THRESHOLDS:D_THRESHOLDS + 33] = two_point_thresholds()
    return bytes(out)


def code_for(page_va: int, **levers) -> bytes:
    """The whole page for ``page_va``: code, constants, then the zeroed per-fixture state."""
    _labels()
    code, _ = _assemble(page_va)
    state = bytearray(CODE_SIZE - STATE_OFF)
    state[S_FACTORS:S_FACTORS + 8] = _f32(1.0) * 2   # neutral until the first fixture is seen
    page = code + data_bytes(**levers) + bytes(state)
    _require(len(page) == CODE_SIZE, "the outcomes page overflows")
    return page


def labels() -> dict[str, int]:
    return _labels()


def sites(page_va: int) -> list[tuple[str, int, bytes, bytes]]:
    lab = _labels()

    def rel(kind: int, at: int, target: int) -> bytes:
        return bytes([kind]) + struct.pack("<i", target - (at + 5))
    return [
        ("commit_entry", COMMIT_SITE, COMMIT_RETAIL, rel(0xE9, COMMIT_SITE, page_va + lab["commit"]) + b"\x90"),
        ("two_point_chooser", TRY_SITE, TRY_RETAIL, rel(0xE9, TRY_SITE, page_va + lab["try"]) + b"\xcc"),
        ("tie_roll_gate", TIES_SITE, TIES_RETAIL, rel(0xE8, TIES_SITE, page_va + lab["ties"])),
        ("regulation_end", REG_SITE, REG_RETAIL, rel(0xE8, REG_SITE, page_va + lab["regulation"]) + b"\x90" * 9),
        ("state_step", STEP_SITE, STEP_RETAIL, rel(0xE8, STEP_SITE, page_va + lab["step"])),
    ]


# ------------------------------------------------------------------------------------------------ owner state
def _space():
    from . import nfl2k5_xbe_space as space
    return space


def allocation(payload: bytes) -> dict | None:
    space = _space()
    if not space.is_scaleout(payload) or space.status(payload) != "applied":
        return None
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not rows:
        return None
    _require(len(rows) == 1 and tuple(rows[0][k] for k in ("owner", "kind", "size", "align"))
             == space.SIM_OUTCOMES_REQUEST and rows[0]["va"] == space.SIM_OUTCOMES_VA
             and rows[0].get("owner_offset", 0) == 0, "foreign simulated outcomes allocation")
    return rows[0]


def _installed_levers(page: bytes) -> dict | None:
    """The levers a page carries, or None when its code or fixed constants are not this revision's."""
    data = page[DATA_OFF:STATE_OFF]
    if data[D_MARK:D_MARK + 8] != MARK:
        return None
    up = struct.unpack_from("<f", data, D_HOME_UP)[0]
    unit = struct.unpack_from("<f", data, D_FORM_UNIT)[0]
    levers = {"home_edge": round(up - 1.0, 6), "form_sigma": round(unit * IRWIN_HALL_SD, 6)}
    try:
        expected = code_for(PLACEHOLDER_VA, **levers)
    except SimOutcomesError:
        return None
    if page[:STATE_OFF] != expected[:STATE_OFF]:
        return None
    return levers


def _state(payload: bytes) -> tuple[str, dict | None, dict | None]:
    from . import nfl2k5_rdata_sites as rdata
    from .nfl2k5_cave_oracle import XbeImage
    space = _space()
    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    found = allocation(payload)
    if found is None:
        _require(rdata.status(payload, sites(PLACEHOLDER_VA)) == "retail",
                 "a simulated outcomes site changed without its page")
        return "retail", None, None
    image = XbeImage(payload)
    section = image.section(found["va"], CODE_SIZE)
    _require(section is not None and section.flags & 1 and section.flags & 4,
             "the simulated outcomes page is not in a writable executable section")
    page = image.read(found["va"], CODE_SIZE)
    site = rdata.status(payload, sites(found["va"]))
    if page == b"\xcc" * CODE_SIZE:
        _require(site == "retail", "a simulated outcomes site changed with an empty page")
        return "retail", found, None
    _require(site == "applied", "mixed simulated outcomes sites and page")
    levers = _installed_levers(page)
    _require(levers is not None, "foreign simulated outcomes page")
    return "applied", found, levers


def status(payload: bytes) -> str:
    """retail / applied / foreign."""
    try:
        return _state(bytes(payload))[0]
    except (SimOutcomesError, ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError):
        return "foreign"


def read_settings(payload: bytes) -> dict:
    try:
        state, found, levers = _state(bytes(payload))
    except (SimOutcomesError, ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError):
        return {"status": "foreign"}
    out = {"status": state}
    if found is not None:
        out["page_va"] = hex(found["va"])
    if levers:
        out.update(levers)
    return out


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in _space().reservations(payload) if r["owner"] == OWNER]
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(retail)), size=len(retail),
                        basis=f"pinned live site ({label}); not a cave")
                   for label, va, retail, _after in sites(PLACEHOLDER_VA)]


def apply(payload: bytes, *, home_edge=HOME_EDGE, form_sigma=FORM_SIGMA) -> tuple[bytes, Mapping[str, object]]:
    """Install the owner (its fixed page, reserved now when the image lacks it, a late owner that moves nobody) and the
    three sites, or re-set the levers of an installed page. Idempotent."""
    from . import nfl2k5_rdata_sites as rdata
    space = _space()
    _require(space.SIM_OUTCOMES_VA == PLACEHOLDER_VA, "the outcomes page address changed")
    state, found, levers = _state(bytes(payload))
    wanted = {"home_edge": round(home_edge, 6), "form_sigma": round(form_sigma, 6)}
    common = {"owner": OWNER, "label": LABEL, "experimental": True, "runtime_witnessed": False, **wanted}
    if state == "applied" and levers == wanted:
        return payload, {**common, "status": "applied", "already_applied": True, "changed_bytes": 0}
    before = payload
    if found is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, (space.SIM_OUTCOMES_REQUEST,), scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, (space.SIM_OUTCOMES_REQUEST,))
        found = allocation(payload)
    _require(found is not None, "reserve the simulated outcomes page first")
    page_va = found["va"]
    from .nfl2k5_cave_oracle import XbeImage
    previous = XbeImage(payload).read(page_va, CODE_SIZE)
    payload, code_receipt = space.install_code(payload, OWNER, code_for(page_va, home_edge=home_edge,
                                                                       form_sigma=form_sigma),
                                               previous=None if previous == b"\xcc" * CODE_SIZE else previous)
    if state != "applied":
        payload, _ = rdata.apply(payload, sites(page_va), OWNER)
    _require(status(payload) == "applied" and read_settings(payload).get("home_edge") == wanted["home_edge"],
             "simulated outcomes postcondition failed")
    return payload, {**common, "status": "applied", "already_applied": False, "from": state,
                     "page_va": hex(page_va), "sites": [hex(va) for _l, va, _r, _a in sites(page_va)],
                     "changed_bytes": space.count_differing_bytes(before, payload) + abs(len(payload) - len(before)),
                     "before_sha256": hashlib.sha256(before).hexdigest(),
                     "after_sha256": hashlib.sha256(payload).hexdigest()}


def remove(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Retail: the three sites back to their retail bytes and the page back to its int3 fill (the reservation stays;
    nothing moves)."""
    from . import nfl2k5_rdata_sites as rdata
    from .nfl2k5_cave_oracle import XbeImage
    space = _space()
    state, found, _levers = _state(bytes(payload))
    if state == "retail":
        return payload, {"owner": OWNER, "status": "retail", "already_retail": True, "changed_bytes": 0}
    before = payload
    page_va = found["va"]
    installed = XbeImage(payload).read(page_va, CODE_SIZE)
    back = [(label, va, after, retail) for label, va, retail, after in sites(page_va)]
    payload, _ = rdata.apply(payload, back, OWNER + " removal")
    payload, _ = space.install_code(payload, OWNER, b"\xcc" * CODE_SIZE, previous=installed)
    _require(status(payload) == "retail", "the simulated outcomes did not come off cleanly")
    return payload, {"owner": OWNER, "status": "retail", "already_retail": False,
                     "changed_bytes": space.count_differing_bytes(before, payload)}


__all__ = ["OWNER", "BUILD_CAPTION", "HELP_TEXT", "CODE_SIZE", "HOME_EDGE", "FORM_SIGMA", "M_LOW", "M_HIGH",
           "COMMIT_SITE", "TRY_SITE", "TIES_SITE", "REG_SITE", "STEP_SITE", "SimOutcomesError", "two_point_thresholds", "code_for", "labels",
           "sites", "allocation", "status", "read_settings", "reservations", "apply", "remove"]
