"""Scheduled-simulation season realism: play mix, targets, QB runs, interceptions and tackles.

EXPERIMENTAL / UNWITNESSED.  The scheduled-game simulator (``FUN_0010b280``) resolves every
scrimmage play through ``0x106a30``: ``0x105690`` picks the abstract play family and the tail of
``0x106a30`` decides run versus pass from a run score and a pass score, ``0x103360`` names the ball
carrier, ``0x1034c0`` the target receiver, ``0x103860`` the run yardage and ``0x102ad0`` the
interception contest.  The post-game merge ``FUN_001334b0`` copies the game line into the career
stream on the way out of the result processor ``0x135310``.

Measured against nflverse 2021-2025 (``stats_player_reg``, regular season) a simulated season
(round 3, Sim QL 15) had 28.8-28.9 pass and 31.4-31.5 rush attempts a team-game against 33.2/26.9,
a receiving leader of 1,173-1,282 yards against 1,811, a target leader of 113-119 against 183,
team interceptions 9.7-11.1 against 12.8, a tackle leader of 136-141 against 169.6, and a QB
rushing leader of 273-290 against 848.  This owner moves those five distributions with targeted
read-only code and leaves the played game alone:

* **Play mix** (``MIX_HOOK``): the run/pass comparison is biased by ``MIX_BIAS`` in favour of the
  pass.  The simulator's own down/distance/clock/score thresholds are untouched, so the mix still
  follows the situation.
* **Targets** (``TARGET_HOOK``): after the engine's target pick, a target that is neither the
  depth-chart WR1 nor TE1 is replaced by one of them at ``TARGET_RATE`` (WR1 3 times in 4).
* **QB runs** (``QB_HOOK``): after the engine's carrier pick, a QB with a mobile scramble byte is
  chosen at a rate that rises with the scramble rating; every mobile QB carry gains
  ``QB_BONUS_YARDS`` in the run outcome (``QB_BONUS_HOOKS``).  Pocket QBs keep the retail outcome.
* **Red-zone run scale** (``RUN_BONUS_SITE``): a run snapped inside the opponent 20 gains
  ``RUN_RZ_SCALE`` of its retail yardage.  Round 5 set this to 0.50 to cut scoring; round 6
  restores it to 0.94 so red-zone runs score again and the rushing-touchdown mix returns to the
  retail level.
* **Red-zone pass scale** (``PASS_SCALE_HOOK``): a completion snapped inside the opponent 20 has
  its yard value multiplied by ``RZ_PASS_SCALE`` before the native ``FN_YARD_CONVERT`` runs, so
  the engine moves the ball by fewer yards and some red-zone pass touchdowns become field goals
  or rushing touchdowns.  This is the round-6 scoring lever and a real play-outcome change.
* **Interceptions** (``INTERCEPT_HOOK``): the native interception probability ``0x102ad0`` (already
  built from the passer's and defender's ratings and clamped to 0.0015..0.035) is multiplied by
  ``INTERCEPT_SCALE`` just before its random draw.
* **Tackles** (``TACKLE_ENTRY_HOOK`` / ``TACKLE_RETURN_HOOK``): for a scheduled simulated game only,
  the career tackle delta of that game is read from the merge (career field 18 before/after) and
  ``TACKLE_BONUS_PCT`` of it is added back, so the single native tackle counter keeps its shape.
  Cornerbacks are skipped because the experimental cornerback tackle owner already calibrates them.
* **Stat-space scales** (``PASS_SCALE`` / ``RUSH_BONUS_PCT``): after the native conversion pass
  yards are multiplied by ``PASS_SCALE`` at the three completion commits and season rush yards of
  non-quarterbacks get ``RUSH_BONUS_PCT`` of each game's delta added back after the merge.  Both
  change the recorded season line only; the engine's field position and play outcomes are
  untouched.  The red-zone pass scale above is different: it runs before the conversion.

Round 5 calibration: two QL 15 seasons and one QL 5 season with the round-3 roster gave
22.65/22.35 points, 1.84/1.82 pass touchdowns, 0.50/0.52 rush touchdowns and 110.7/109.6 rush
yards a team-game at QL 15.  Round 6 restores most of the red-zone run yardage
(``RUN_RZ_SCALE`` 0.94) and moves the scoring cut to the red-zone pass conversion
(``RZ_PASS_SCALE`` 0.70, applied before the native conversion), so the touchdown mix returns to
pass 1.52/1.52 and rush 0.87/0.81 a team-game.  Points land at 22.49/22.11 and the rushing
touchdown leader at 16/14 with 9/6 players over 10.  The post-conversion pass scale is 0.96, the
target rate 0.14 and the tackle correction 10 percent.  CODE_SIZE stays 832 bytes; the
allocation is proven by the union test.

Every site is recognised by its pinned retail bytes; the module refuses a foreign executable.  The
data reservation (16 bytes) holds the temporary merge and run-outcome hand-offs and nothing else.
The played-game path (game mode other than 4 at the merge gate), the live playbook calls and every
roster byte are untouched.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_sim_realism"
CODE_SIZE = 832
DATA_SIZE = 16
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 4))
BUILD_CAPTION = "Simulated season realism (experimental)"
HELP_TEXT = (
    "EXPERIMENTAL. In franchise games the CPU simulates (not games you play) the play mix moves toward "
    "the modern NFL (about 33 passes and 27 runs a team), targets concentrate on the top receiver and "
    "tight end, mobile quarterbacks run for NFL-sized totals, team interceptions move toward 12.8, and "
    "tackle totals move toward the NFL leader and top-10 levels. Red-zone passes gain fewer yards so scoring "
    "and the touchdown mix land near the modern NFL, and season rush yards get a post-game correction. Played "
    "games, ratings and rosters are unchanged. The numbers are calibrated from nflverse 2021-2025 regular seasons."
)

SIM_MODE = 0x00E5FF80                # game mode word: 4 = the franchise scheduled-game simulator
MATCH_RNG = 0x00E5FCA0              # the match/subtract-with-borrow RNG state pointer
FN_RAND = 0x00048B90                 # ecx = RNG state; returns a uniform float in st0
FN_CARRIER = 0x00103360              # esi = sim team; returns the ball carrier pointer
FN_OUTCOME = 0x00103860              # carrier in arg1, float arg2; returns run yards in st0
FN_TARGET = 0x001034C0               # edi = sim team; returns the target receiver pointer
FN_STAT_READ = 0x0014EE40            # ecx = player, edx = field; returns the current-slot value
FN_HISTORY_ADD = 0x0014F450          # ecx = player, edx = field, push value; additive career write
TEAM_OFFENSE = 0x00A9719C            # the simulator's offense summary pointer

MIX_SITE, MIX_BEFORE, MIX_RUN, MIX_PASS = (
    0x00106FFD, bytes.fromhex("f6c4410f84f4fcffff"), 0x00106CFA, 0x00107006)
QB_SITE, QB_BEFORE = 0x00106CFF, bytes.fromhex("8b3da071a900")   # after the RB carrier guard, if present
QB_RESUME = 0x00106D05
TARGET_SITE, TARGET_BEFORE = 0x00107035, bytes.fromhex("e886c4ffff")
INTERCEPT_SITE, INTERCEPT_BEFORE = 0x00102C83, bytes.fromhex("b9a0fce500")
TACKLE_ENTRY_SITE, TACKLE_ENTRY_BEFORE = 0x001334D3, bytes.fromhex("8d9424dc000000")
TACKLE_ENTRY_RESUME = 0x001334DA
TACKLE_RETURN_SITE, TACKLE_RETURN_BEFORE = 0x00133798, bytes.fromhex("c208009090")
RUN_BONUS_SITE, RUN_BONUS_BEFORE = 0x00107CFE, bytes.fromhex("8b038b4c2410")
RUN_BONUS_RESUME = 0x00107D04
PASS_SITES = (
    (0x001085BD, bytes.fromhex("e8bedeffff")),
    (0x0010921A, bytes.fromhex("e861d2ffff")),
    (0x001094E4, bytes.fromhex("e897cfffff")),
)
FN_YARD_CONVERT = 0x00106480

MIX_BIAS = 8.5                       # run score must beat pass score by this much to stay a run
TARGET_RATE = 0.14                   # share of non-WR1/TE1 targets redirected
TARGET_WR1_SHARE = 0.75              # of the redirected targets, the rest go to the TE1
QB_SCRAMBLE_BASE = 45
QB_SCRAMBLE_SCALE = 0.0036           # extra QB-carry probability per scramble point above the base
QB_SCRAMBLE_CAP = 32                 # points, so the maximum is 0.1152
QB_MOBILE_SUM = 150                  # mobile family: scramble + agility > 150
QB_BONUS_YARDS = 3.0
QB_BONUS_RZ_LINE = 20.0              # inside the opponent 20 is the red zone for both yard scales
INTERCEPT_SCALE = 1.35
PASS_SCALE = 0.96
RUN_RZ_SCALE = 0.94              # red-zone run yardage (round 6: near-retail, small trim)
RZ_PASS_SCALE = 0.70             # red-zone pass yardage before the native conversion (scoring lever)
RUSH_BONUS_PCT = 13              # post-game season rush-yard correction (RBs and other non-QBs)
TACKLE_BONUS_PCT = 10
SKIP_TACKLE_POSITION = 4             # cornerbacks are calibrated by nfl2k5_sim_cb_tackles

# Fixed float-pool offsets inside the code cave (the assembler must not cross them).
MIX_BIAS_OFF = 704
TARGET_RATE_OFF = 708
TARGET_WR1_OFF = 712
QB_SCALE_OFF = 716
QB_BONUS_VALUE_OFF = 720
INTERCEPT_SCALE_OFF = 724
PASS_SCALE_OFF = 728
TACKLE_PCT_OFF = 732
QB_BONUS_RZ_OFF = 736
RUN_RZ_SCALE_OFF = 740
RUSH_BONUS_PCT_OFF = 744
RZ_PASS_SCALE_OFF = 748
RED_ZONE_OFF = 752
ZERO_OFF = 756
FLOAT_POOL = MIX_BIAS_OFF


class SimRealismError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise SimRealismError(message)


def tackle_bonus(game_tackles):
    """The integer bonus added to a scheduled game's career tackle line (0.21x, rounded)."""
    if game_tackles <= 0:
        return 0
    return (game_tackles * TACKLE_BONUS_PCT + 50) // 100


def rush_bonus(game_yards):
    """The integer season rush-yard correction added after a scheduled simulated game."""
    if game_yards <= 0:
        return 0
    return (game_yards * RUSH_BONUS_PCT + 50) // 100


def pass_rz_scale(spot):
    """The pass-yard multiplier for a completion snapped this many yards from the goal."""
    if spot is None:
        return 1.0
    return RZ_PASS_SCALE if spot <= QB_BONUS_RZ_LINE else 1.0


def run_rz_scale(spot):
    """The run-yard multiplier for a carry snapped this many yards from the goal."""
    if spot is None:
        return 1.0
    return RUN_RZ_SCALE if spot <= QB_BONUS_RZ_LINE else 1.0


def qb_carry_rate(scramble):
    """The extra chance that a simulated run is handed to this quarterback."""
    if scramble is None or scramble <= QB_SCRAMBLE_BASE:
        return 0.0
    return min(QB_SCRAMBLE_CAP, scramble - QB_SCRAMBLE_BASE) * QB_SCRAMBLE_SCALE


def _u32(value):
    return struct.pack("<I", value)


def _flt(value):
    return struct.pack("<f", value)


def _assemble(code_va, data_va):
    from .nfl2k5_draft_ai import _Asm
    a = _Asm(code_va)
    state, state_out = data_va, data_va + 8

    # ---- play mix ---------------------------------------------------------------------------
    a.label("mix")
    a.b("d905" + _u32(0x00A97200).hex())                  # fld [spot]
    a.b("d81d" + _u32(code_va + RED_ZONE_OFF).hex())      # fcomp 79.5
    a.b("dfe0")                                           # fnstsw ax
    a.b("f6c441")                                         # test ah,0x41
    a.j8("74", "mix_red")                                 # spot > 79.5: own side, retail call
    a.b("d9442414")                                       # fld [esp+0x14]
    a.b("d8642418")                                       # fsub [esp+0x18]
    a.b("d81d" + _u32(code_va + MIX_BIAS_OFF).hex())      # fcomp bias
    a.j8("eb", "mix_decide")
    a.label("mix_red")
    a.b("d9442414")                                       # red zone keeps the retail call
    a.b("d8642418")                                       # fsub [esp+0x18]
    a.b("d81d" + _u32(code_va + ZERO_OFF).hex())          # fcomp 0.0
    a.label("mix_decide")
    a.b("dfe0")                                           # fnstsw ax
    a.b("f6c441")                                         # test ah,0x41
    a.j8("74", "mix_run")
    a.b("83c404")
    a.jmp_abs(MIX_PASS)
    a.label("mix_run")
    a.b("83c404")
    a.jmp_abs(MIX_RUN)

    # ---- QB carrier -------------------------------------------------------------------------
    a.label("qb")
    a.b("60")                                             # pushad (saved EAX = carrier)
    a.b("a1" + _u32(TEAM_OFFENSE).hex())                  # mov eax,[offense]
    a.b("8b4008")                                         # mov eax,[eax+8]  slot 0 = QB
    a.b("85c0")                                           # test eax,eax
    a.j8("74", "qb_done")
    a.b("80783500")                                       # cmp byte [eax+0x35],0
    a.j8("75", "qb_done")
    a.b("8be8")                                           # mov ebp,eax      QB pointer
    a.b("0fb6484f")                                       # movzx ecx,byte [eax+0x4f]
    a.b("83e92d")                                         # sub ecx,45
    a.j8("7e", "qb_done")
    a.b("83f928")                                         # cmp ecx,40
    a.j8("7e", "qb_ok")
    a.b("b928000000")                                     # mov ecx,40
    a.label("qb_ok")
    a.b("890d" + _u32(state_out).hex())                   # mov [state],ecx
    a.b("db05" + _u32(state_out).hex())                   # fild dword [state]
    a.b("d80d" + _u32(code_va + QB_SCALE_OFF).hex())      # fmul scale
    a.b("d91d" + _u32(state_out).hex())                   # fstp dword [state]
    a.b("b9" + _u32(MATCH_RNG).hex())
    a.call(FN_RAND)
    a.b("d81d" + _u32(state_out).hex())                   # fcomp p
    a.b("dfe0")                                           # fnstsw ax
    a.b("f6c401")                                         # test ah,1 (rand < p)
    a.j8("74", "qb_done")
    a.b("896c241c")                                       # mov [esp+0x1c],ebp  saved EAX = QB
    a.label("qb_done")
    a.b("61")                                             # popad
    a.b("8b3da071a900")                                   # mov edi,[defense]  (displaced)
    a.b("83c404")                                         # add esp,4
    a.jmp_abs(QB_RESUME)

    # ---- target concentration ---------------------------------------------------------------
    a.label("target")
    a.b("60")                                             # pushad
    a.call(FN_TARGET)                                     # eax = retail target
    a.b("8bd8")                                           # mov ebx,eax
    a.b("a1" + _u32(TEAM_OFFENSE).hex())
    a.b("8bf0")                                           # mov esi,eax      sim team
    a.b("8b4618")                                         # mov eax,[esi+0x18] WR1 (slot 4)
    a.b("85c0")
    a.j8("74", "target_done")
    a.b("39d8")                                           # cmp eax,ebx
    a.j8("74", "target_done")
    a.b("8b5628")                                         # mov edx,[esi+0x28] TE1 (slot 8)
    a.b("85d2")
    a.j8("74", "target_done")
    a.b("39da")                                           # cmp edx,ebx
    a.j8("74", "target_done")
    a.b("b9" + _u32(MATCH_RNG).hex())
    a.call(FN_RAND)
    a.b("d81d" + _u32(code_va + TARGET_RATE_OFF).hex())
    a.b("dfe0")
    a.b("f6c401")
    a.j8("74", "target_done")
    a.b("b9" + _u32(MATCH_RNG).hex())
    a.call(FN_RAND)
    a.b("d81d" + _u32(code_va + TARGET_WR1_OFF).hex())
    a.b("dfe0")
    a.b("f6c401")
    a.j8("74", "target_te")
    a.b("8b5e18")                                         # mov ebx,[esi+0x18] WR1
    a.j8("eb", "target_done")
    a.label("target_te")
    a.b("8b5e28")                                         # mov ebx,[esi+0x28] TE1
    a.label("target_done")
    a.b("895c241c")                                       # mov [esp+0x1c],ebx  saved EAX slot
    a.b("61")                                             # popad
    a.b("c3")

    # ---- interception scale (inside the ratings-driven contest 0x102ad0) --------------------
    a.label("int")
    a.b("d9442404")                                       # fld [esp+4]  interception probability
    a.b("d80d" + _u32(code_va + INTERCEPT_SCALE_OFF).hex())
    a.b("d95c2404")                                       # fstp [esp+4]
    a.b("b9" + _u32(MATCH_RNG).hex())
    a.b("c3")

    # ---- run yardage scale and mobile-QB bonus (scrimmage run commit) ----------------------
    a.label("qb_bonus")
    a.b("d905" + _u32(0x00A97200).hex())                  # fld [spot]  yards to the opponent goal
    a.b("d81d" + _u32(code_va + QB_BONUS_RZ_OFF).hex())   # fcomp 20.0
    a.b("dfe0")                                           # fnstsw ax
    a.b("f6c441")                                         # test ah,0x41
    a.j8("74", "qb_bonus_out")                            # spot > 20: not a red-zone carry
    a.b("d9442414")                                       # fld dword [esp+0x14]
    a.b("d80d" + _u32(code_va + RUN_RZ_SCALE_OFF).hex())
    a.b("d95c2414")                                       # fstp dword [esp+0x14]
    a.label("qb_bonus_out")
    a.b("a1" + _u32(0x00A971A4).hex())                    # mov eax,[ball carrier]
    a.b("80783500")                                       # cmp byte [eax+0x35],0
    a.j8("75", "qb_bonus_done")
    a.b("0fb6484f")                                       # movzx ecx,byte [eax+0x4f]
    a.b("0fb65037")                                       # movzx edx,byte [eax+0x37]
    a.b("03ca")                                           # add ecx,edx
    a.b("81f9" + struct.pack("<I", QB_MOBILE_SUM).hex())
    a.j8("7e", "qb_bonus_done")
    a.b("d9442414")                                       # fld dword [esp+0x14]
    a.b("d805" + _u32(code_va + QB_BONUS_VALUE_OFF).hex())
    a.b("d95c2414")                                       # fstp dword [esp+0x14]
    a.label("qb_bonus_done")
    a.b("8b03")                                           # mov eax,[ebx]     (displaced)
    a.b("8b4c2414")                                       # mov ecx,[esp+0x14] (displaced +4)
    a.b("83c404")                                         # add esp,4
    a.jmp_abs(RUN_BONUS_RESUME)

    # ---- pass yardage scale (three completion commits) -------------------------------------
    a.label("pass_scale")
    a.b("d905" + _u32(0x00A97200).hex())                  # fld [spot]  yards to the opponent goal
    a.b("d81d" + _u32(code_va + QB_BONUS_RZ_OFF).hex())   # fcomp 20.0
    a.b("dfe0")                                           # fnstsw ax
    a.b("f6c441")                                         # test ah,0x41
    a.j8("74", "pass_scale_out")                          # spot > 20: keep the retail yards
    a.b("d9442404")                                       # fld dword [esp+4]  pushed yard arg
    a.b("d80d" + _u32(code_va + RZ_PASS_SCALE_OFF).hex())
    a.b("d95c2404")                                       # fstp dword [esp+4]
    a.label("pass_scale_out")
    a.b("8b0424")                                         # mov eax,[esp]   hook return
    a.b("a3" + _u32(state_out + 4).hex())
    a.b("58")                                             # pop eax
    a.call(FN_YARD_CONVERT)
    a.b("d80d" + _u32(code_va + PASS_SCALE_OFF).hex())
    a.b("8b15" + _u32(state_out + 4).hex())
    a.b("52")                                             # push return
    a.b("c3")                                             # ret

    # ---- tackle scale: save the career line before the merge --------------------------------
    a.label("tackle_entry")
    a.b("60")                                             # pushad
    a.b("31c0")                                           # xor eax,eax
    a.b("a3" + _u32(state).hex())                         # [state]=0
    a.b("803d" + _u32(SIM_MODE).hex() + "04")             # cmp byte [mode],4
    a.j8("75", "tackle_entry_skip")
    a.b("89f8")                                           # mov eax,edi
    a.b("a3" + _u32(state).hex())
    a.b("ba12000000")                                     # mov edx,18
    a.b("89f9")                                           # mov ecx,edi
    a.call(FN_STAT_READ)
    a.b("a3" + _u32(state + 4).hex())
    a.b("ba02000000")                                     # mov edx,2
    a.b("89f9")                                           # mov ecx,edi
    a.call(FN_STAT_READ)
    a.b("a3" + _u32(state + 8).hex())
    a.label("tackle_entry_skip")
    a.b("61")                                             # popad
    a.b("8d9424e0000000")                                 # lea edx,[esp+0xe0] (replayed +4)
    a.b("83c404")                                         # add esp,4
    a.jmp_abs(TACKLE_ENTRY_RESUME)

    # ---- tackle scale: add 21% of this game's delta back ------------------------------------
    a.label("tackle_return")
    a.b("60")                                             # pushad
    a.b("a1" + _u32(state).hex())
    a.b("85c0")
    a.j32("0f84", "tackle_done")
    a.b("80783500")                                       # cmp byte [eax+0x35],0  quarterbacks keep their line
    a.j8("74", "rush_done")
    a.b("8bc8")                                           # mov ecx,eax
    a.b("ba02000000")                                     # mov edx,2
    a.call(FN_STAT_READ)
    a.b("8b0d" + _u32(state + 8).hex())
    a.b("2bc1")                                           # sub eax,ecx
    a.b("85c0")
    a.j8("7e", "rush_done")
    a.b("69c0" + struct.pack("<I", RUSH_BONUS_PCT).hex())
    a.b("0532000000")                                     # add eax,50
    a.b("99")                                             # cdq
    a.b("b964000000")                                     # mov ecx,100
    a.b("f7f9")                                           # idiv ecx
    a.b("85c0")
    a.j8("7e", "rush_done")
    a.b("50")                                             # push bonus
    a.b("6a02")                                           # push 2
    a.b("5a")                                             # pop edx
    a.b("8b0d" + _u32(state).hex())
    a.call(FN_HISTORY_ADD)
    a.label("rush_done")
    a.b("8b0d" + _u32(state).hex())                       # mov ecx,[state]
    a.b("ba12000000")                                     # mov edx,18
    a.call(FN_STAT_READ)
    a.b("8b0d" + _u32(state + 4).hex())
    a.b("2bc1")                                           # sub eax,ecx
    a.b("85c0")
    a.j8("7e", "tackle_done")
    a.b("8b0d" + _u32(state).hex())
    a.b("80793504")                                       # cmp byte [ecx+0x35],4
    a.j8("74", "tackle_done")
    a.b("69c015000000")                                   # imul eax,eax,21
    a.b("0532000000")                                     # add eax,50
    a.b("99")                                             # cdq
    a.b("b964000000")                                     # mov ecx,100
    a.b("f7f9")                                           # idiv ecx
    a.b("85c0")
    a.j8("7e", "tackle_done")
    a.b("50")                                             # push bonus
    a.b("6a12")                                           # push 18
    a.b("5a")                                             # pop edx
    a.b("8b0d" + _u32(state).hex())
    a.call(FN_HISTORY_ADD)
    a.label("tackle_done")
    a.b("c705" + _u32(state).hex() + "00000000")          # [state]=0
    a.b("61")                                             # popad
    a.b("c20800")                                         # ret 8
    body = bytearray(a.assemble())
    require(len(body) <= FLOAT_POOL, f"sim realism code is {len(body)} bytes, float pool {FLOAT_POOL}")
    body = body.ljust(FLOAT_POOL, b"\xcc")
    pool = (_flt(MIX_BIAS) + _flt(TARGET_RATE) + _flt(TARGET_WR1_SHARE) + _flt(QB_SCRAMBLE_SCALE)
            + _flt(QB_BONUS_YARDS) + _flt(INTERCEPT_SCALE) + _flt(PASS_SCALE) + _flt(TACKLE_BONUS_PCT)
            + _flt(QB_BONUS_RZ_LINE) + _flt(RUN_RZ_SCALE) + _flt(RUSH_BONUS_PCT)
            + _flt(RZ_PASS_SCALE))
    pool = pool.ljust(RED_ZONE_OFF - FLOAT_POOL, b"\xcc") + _flt(79.5) + _flt(0.0)
    body += pool.ljust(CODE_SIZE - FLOAT_POOL, b"\xcc")
    require(len(body) == CODE_SIZE, "sim realism code size")
    return a, bytes(body)


def code_for(code_va, data_va):
    return _assemble(code_va, data_va)[1]


_LABEL_CACHE = None


def label_offsets():
    global _LABEL_CACHE
    if _LABEL_CACHE is None:
        _LABEL_CACHE = dict(_assemble(0x1000000, 0x2000000)[0].labels)
    return _LABEL_CACHE


def sites(code_va):
    offs = label_offsets()
    hook = lambda label, site, before, off: (label, site, before,
                                             b"\xe8" + struct.pack("<i", code_va + off - site - 5))
    mix = ("mix", MIX_SITE, MIX_BEFORE, b"\xe8" + struct.pack("<i", code_va - MIX_SITE - 5) + b"\x90" * 4)
    tackle_return = ("tackle_return", TACKLE_RETURN_SITE, TACKLE_RETURN_BEFORE,
                     b"\xe9" + struct.pack("<i", code_va + offs["tackle_return"] - TACKLE_RETURN_SITE - 5))
    out = [mix,
           ("qb", QB_SITE, QB_BEFORE, b"\xe8" + struct.pack("<i", code_va + offs["qb"] - QB_SITE - 5) + b"\x90"),
           hook("target", TARGET_SITE, TARGET_BEFORE, offs["target"]),
           hook("intercept", INTERCEPT_SITE, INTERCEPT_BEFORE, offs["int"]),
           ("tackle_entry", TACKLE_ENTRY_SITE, TACKLE_ENTRY_BEFORE,
            b"\xe8" + struct.pack("<i", code_va + offs["tackle_entry"] - TACKLE_ENTRY_SITE - 5) + b"\x90\x90"),
           tackle_return,
           ("run_bonus", RUN_BONUS_SITE, RUN_BONUS_BEFORE,
            b"\xe8" + struct.pack("<i", code_va + offs["qb_bonus"] - RUN_BONUS_SITE - 5) + b"\x90")]
    out += [hook(f"pass_scale_{i}", site, before, offs["pass_scale"]) for i, (site, before) in enumerate(PASS_SITES)]
    return out


def _allocations(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    code = [r for r in rows if r["kind"] == "code"]
    data = [r for r in rows if r["kind"] == "data"]
    require(len(code) == 1 and (code[0]["size"], code[0]["align"]) == (CODE_SIZE, 16),
            "Missing or foreign sim realism code allocation")
    require(len(data) == 1 and (data[0]["size"], data[0]["align"]) == (DATA_SIZE, 4),
            "Missing or foreign sim realism data allocation")
    return code[0], data[0]


def _recognize(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    code = data = None
    if present:
        code, data = _allocations(payload)
    edits = sites(code["va"] if code else 0)
    states = set()
    for _label, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if code and raw == after else "foreign")
    if code:
        raw = image.read(code["va"], CODE_SIZE)
        expected = code_for(code["va"], data["va"])
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == expected else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed sim realism site/code")
    return next(iter(states))


def apply(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    state = _recognize(payload)
    require(state != "foreign", "sim realism: foreign bytes")
    if state == "applied":
        code, data = _allocations(payload)
        return payload, {"owner": OWNER, "status": "already_applied", "code_va": hex(code["va"]),
                         "data_va": hex(data["va"]), "changed_bytes": 0}
    before = payload
    if space.status(payload) == "retail":
        payload, receipt = space.apply(payload, REQUESTS, scaleout=True)
    else:
        require(space.is_scaleout(payload), "Simulated season realism needs the scale-out allocator")
        payload, receipt = space.extend_scaleout(payload, REQUESTS)
    code, data = _allocations(payload)
    payload, _ = space.install_code(payload, OWNER, code_for(code["va"], data["va"]))
    image = XbeImage(payload)
    buf = bytearray(payload)
    edits = sites(code["va"])
    for _label, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"sim realism site {va:#x} is not retail")
        buf[off:off + len(new)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    payload = bytes(buf)
    require(_recognize(payload) == "applied" and space.status(payload) == "applied",
            "Simulated season realism postcondition failed")
    return payload, {"owner": OWNER, "status": "applied", "code_va": hex(code["va"]),
                     "data_va": hex(data["va"]), "allocation": receipt,
                     "reservations": [r for r in space.reservations(payload) if r["owner"] == OWNER],
                     "edits": [dict(label=label, va=hex(va), before=old.hex(), after=new.hex())
                               for label, va, old, new in edits],
                     "changed_bytes": space.count_differing_bytes(before, payload),
                     "file_growth": len(payload) - len(before)}


def status(payload):
    try:
        return _recognize(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError):
        return "foreign"


__all__ = ["OWNER", "CODE_SIZE", "DATA_SIZE", "REQUESTS", "BUILD_CAPTION", "HELP_TEXT",
           "MIX_BIAS", "TARGET_RATE", "TARGET_WR1_SHARE", "QB_BONUS_YARDS", "QB_BONUS_RZ_LINE",
           "INTERCEPT_SCALE", "PASS_SCALE", "RUN_RZ_SCALE", "RZ_PASS_SCALE",
           "TACKLE_BONUS_PCT", "RUSH_BONUS_PCT", "tackle_bonus", "rush_bonus", "pass_rz_scale",
           "run_rz_scale", "qb_carry_rate", "code_for", "sites", "apply",
           "status", "SimRealismError"]
