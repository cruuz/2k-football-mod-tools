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
* **Targets** (``TARGET_HOOK``): the simulator preserves native picks for both starting receivers and the
  first tight end. Comparable starting receivers share additional targets.
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
* **Pass yards after conversion.** At three native pass-yard calculation sites, ``PASS_SCALE``
  multiplies the gain returned to the simulator. Changing this value affects credited yardage
  and can change subsequent plays and final scores.
* **Season rushing correction.** The postgame merge applies ``RUSH_BONUS_PCT`` to the lead
  halfback's rushing-yard delta and adds the result to his season total.

Round 5 calibration: two QL 15 seasons and one QL 5 season with the round-3 roster gave
22.65/22.35 points, 1.84/1.82 pass touchdowns, 0.50/0.52 rush touchdowns and 110.7/109.6 rush
yards a team-game at QL 15.  Round 6 restores most of the red-zone run yardage
(``RUN_RZ_SCALE`` 0.94) and moves the scoring cut to the red-zone pass conversion
(``RZ_PASS_SCALE`` 0.70, applied before the native conversion), so the touchdown mix returns to
pass 1.52/1.52 and rush 0.87/0.81 a team-game.  Points land at 22.49/22.11 and the rushing
touchdown leader at 16/14 with 9/6 players over 10.  The post-conversion pass scale is 0.96, the
target rate 0.14 and the tackle correction 10 percent.  CODE_SIZE stays 832 bytes; the
allocation is proven by the union test.

Integration rebalance (b779-int1, constants only): with every simulated-season owner installed together (the
cornerback credit and its injured-player guard, the RB injuries, this owner) two QL 15 seasons gave 23.1-23.3
points, 8-10 backs and 28-33 receivers over 1,000 yards.  ``PASS_SCALE`` 0.92 after conversion, ``RUSH_BONUS_PCT`` 20
(stat space), ``RZ_PASS_SCALE`` 0.64 and the RB owner's rotation at 2% give, over seeds 2501/2502/2503:
22.78/22.42/22.49 points, pass TD 1.57/1.55/1.60, rush TD 0.97/0.95/0.87, 18/18/12 backs and 24/22/26
receivers over 1,000 yards.

b780 b5-sim, calibrated on the released v0.8 executable itself (a 17-game regular season; the earlier rounds ran the
retail 16-game harness, which understated season totals): the season rush correction goes to each team's lead back
only (HB, depth rank 0) at 8 percent; the play mix bias moves with the QB1's Pass Accuracy (0.4 a point around 87), the
redirect share with the WR1's Catching (0.08 + 0.015 a point around 90); the pass scale after conversion is 0.86 because every
simulated QB1 plays all 17 games (19 and 13 passers over 4,000 yards at 0.92 against the NFL's 8.2); the tackle
correction uses its constant (10 percent; the code had a hard-coded 21).

b780 db2: ``RUSH_BONUS_PCT`` 8 -> 0. The 8 percent lead-back correction made up for the carries fullbacks took (the retail
lottery gave the modern roster's fullbacks 9.6-9.9% of simulated carries). With the fullback rule in
``nfl2k5_sim_rb_injuries`` (a fullback keeps 1 in 16 of his carries, the rest are drawn again) the lead backs carry
219-226 times a season (NFL 218), and the correction put them at 1,002-1,042 yards with 16-20 backs over 1,000
(NFL 958 and 13.4). Without it, the same two v0.8-executable seasons (seeds 2502/2501; the correction is stat space only,
so the games are identical) give lead backs 928/965 yards, 10/17 backs over 1,000 (mean 13.5), RB top-10 1,236/1,310
(NFL 1,269) and top-32 960/1,006 (NFL 985). The beta 80 correction code stays in place and adds nothing. A custom build with this
option but without Simulated RB short injuries keeps the retail fullback carries and loses the old correction.

b81 fb-targets: fullback targets. Report (beta 81, from a played franchise): "patric ricard, h back for giants, dominated
the stats for the year?? they never use him". The retail target lottery ``0x1034C0`` draws from the lineup slots at
``0x4F6A80`` (4, 1, 5, 8, 2, 6, 3, 7: WR1, HB1, WR2, TE1, FB1, WR3, HB2, WR4), each weighted by its receiving composite
squared, so the FB1 slot always competes. The b780 db2 rule thinned fullback carries, never targets: on the stored beta 81
panels fullbacks caught 500-540 passes a league season (20-24% of the backfield's catches, 4.4-4.8% of all), the starters
10-50 each and Ricard about 40, where the same players caught about 125 in the 2025 NFL season and Ricard 1. The target
site now enters ``fb_entry``: the target step runs as before (the lottery and the redirect above), and a pick with
position byte 8 (fullbacks and the authored H-backs) keeps the pass when the 16-bit league draw is below
``FB_TARGET_KEEP_THRESHOLD`` (1 in 3); otherwise the step runs again, up to ``FB_TARGET_REDRAWS`` times, and the first
other pick takes it (the TE1 slot, else the HB1 slot, if every draw is a fullback). A halfback in the FB slot is not
touched. The room came from the season merge: the lead-back rush correction had a constant of 0 since b780 db2 and never
changed a stat, so its branch and the rushing-yard read at the tackle entry are gone; the tackle correction is the same
arithmetic, inlined. Everything before the tackle entry and the float pool keep their offsets (the simulated QB injury
option links ``pass_scale`` and the pool, and edits the mix block), and the size stays 896, so the beta 81 revision
before this rule reads "legacy" and is updated in place in its own allocation, under the QB injury option too.

Every site is recognised by its pinned retail bytes; the module refuses a foreign executable.  The
data reservation (16 bytes) holds the temporary merge and run-outcome hand-offs and nothing else.
The played-game path (game mode other than 4 at the merge gate), the live playbook calls and every
roster byte are untouched.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_sim_realism"
CODE_SIZE = 896                      # b780 b5-sim: 832 -> 896 (QB-scaled mix, WR1-scaled targets, lead-back rush rule)
DATA_SIZE = 16
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 4))
BUILD_CAPTION = "Simulated season realism (experimental)"
HELP_TEXT = (
    "EXPERIMENTAL. In franchise games the CPU simulates (not games you play) the play mix moves toward "
    "the modern NFL (about 33 passes and 27 runs a team), and better passers call more passes than weaker ones; "
    "both starting receivers keep the targets the game gives them. Strong receiving pairs share extra targets, fullbacks and "
    "H-backs keep about one in three of the passes the game aims at them, and mobile quarterbacks "
    "carry more often. Team interceptions move toward 12.8, and tackle totals move toward the NFL leader and "
    "top-10 levels. Red-zone passes gain fewer yards so scoring and the touchdown mix land near the modern NFL. "
    "Played games, ratings and rosters are unchanged. The numbers are calibrated from nflverse 2021-2025 regular "
    "seasons on 17-game simulated seasons."
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

MIX_BIAS = 8.5                       # run score must beat pass score by this much to stay a run (average QB)
MIX_QB_PIVOT = 87                    # b780 b5-sim: QB1 Pass Accuracy of the league-average starter (SOFTDRINK roster)
MIX_QB_SLOPE = 0.4                   # extra bias per accuracy point above the pivot (fewer passes below it)
TARGET_RATE = 0.08                   # share of eligible targets redirected with an average WR1
TARGET_PIVOT = 90                    # b780 b5-sim: WR1 Catching of the league-average WR1 (SOFTDRINK roster)
TARGET_SLOPE = 0.015                 # extra redirect share per Catching point above the pivot (less below it)
TARGET_WR1_SHARE = 0.75              # receiver share of redirects, with the rest going to TE1
WR2_MIN_CATCH = 80
WR2_MAX_CATCH_GAP = 8
WR2_SHARE = 0.28                     # share of receiver redirects for a competitive WR2
QB_SCRAMBLE_BASE = 45
QB_SCRAMBLE_SCALE = 0.0056           # extra QB-carry probability per scramble point above the base
QB_SCRAMBLE_CAP = 40                 # cap used by the game for scramble points above the base
QB_MOBILE_SUM = 150                  # mobile family: scramble + agility > 150
QB_BONUS_YARDS = 3.5
QB_BONUS_RZ_LINE = 20.0              # inside the opponent 20 is the red zone for both yard scales
INTERCEPT_SCALE = 1.35
PASS_SCALE = 0.91                    # returned-yard scale across the three pass-yard calls
RUN_RZ_SCALE = 0.94              # red-zone run yardage (round 6: near-retail, small trim)
RZ_PASS_SCALE = 0.64             # red-zone pass yardage before the native conversion (scoring lever)
RUSH_BONUS_PCT = 0               # post-game season rush-yard correction, lead backs only (b780 db2: 0, was 8 in b780 b5-sim,
                                 # 20 for every non-QB in b779-int1): it made up for the carries the fullbacks took, which
                                 # nfl2k5_sim_rb_injuries now hands back (see the docstring)
LEAD_BACK_POSITION = 7               # HB, depth rank 0 (player +0x28 bits 10-12) at the merge
TACKLE_BONUS_PCT = 10                # b780 b5-sim: the code added a hard-coded 21% (imul 21) while this constant, the helper
                                     # and the round-5 notes said 10%; the code now uses the constant (17-game seasons put
                                     # the 21% tackle leader at 171-190 against the NFL's 155-180)
SKIP_TACKLE_POSITION = 4             # cornerbacks are calibrated by nfl2k5_sim_cb_tackles
# b81 fb-targets: a fullback (position byte 8: fullbacks and the authored H-backs) picked as the target keeps the pass
# when the 16-bit league draw is below this (21845/65536 = 1 in 3); otherwise the whole target step (the retail lottery
# and the redirect above) draws again, up to FB_TARGET_REDRAWS times, and then the TE1 lineup slot, else the HB1 slot,
# takes it. Measured before the rule (stored b81 panels): fullbacks caught 500-540 passes a league season, 20-24% of the
# backfield's catches; the same players caught about 125 in the 2025 NFL season.
FULLBACK_POSITION = 8
FB_TARGET_KEEP_THRESHOLD = 21845
FB_TARGET_REDRAWS = 3
FN_LEAGUE_DRAW = 0x00048BC0          # mov ecx,0xB12680; jmp 0x48B50: the league RNG (the carry rule's draw), dword in EAX
TE1_SLOT, HB1_SLOT = 0x28, 0x0C      # sim team offense summary (EDI at the target call): TE1 (slot 8), HB1 (slot 1)

# Fixed float-pool offsets inside the code cave (the assembler must not cross them). b780 b5-sim moved the pool from
# 704 to 816 for the longer mix, target and lead-back code.
MIX_BIAS_OFF = 816
TARGET_RATE_OFF = 820
TARGET_WR1_OFF = 824
QB_SCALE_OFF = 828
QB_BONUS_VALUE_OFF = 832
INTERCEPT_SCALE_OFF = 836
PASS_SCALE_OFF = 840
TACKLE_PCT_OFF = 844
QB_BONUS_RZ_OFF = 848
RUN_RZ_SCALE_OFF = 852
RUSH_BONUS_PCT_OFF = 856
RZ_PASS_SCALE_OFF = 860
RED_ZONE_OFF = 864
ZERO_OFF = 868
MIX_QB_SLOPE_OFF = 872
TARGET_SLOPE_OFF = 876
WR2_SHARE_OFF = 880
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


def _beta80_merge(a, state):
    """Exact season-merge instructions retained to recognize installed beta 80 copies."""
    a.label("tackle_return")
    a.b("60")                                             # pushad
    a.b("a1" + _u32(state).hex())
    a.b("85c0")
    a.j32("0f84", "tackle_done")
    # b780 b5-sim: the season rush correction goes to the lead back only (HB, depth rank 0); every other runner keeps the
    # engine's line, so team rushing is not inflated by backups, fullbacks and receivers
    a.b("807835" + bytes([LEAD_BACK_POSITION]).hex())      # cmp byte [eax+0x35],7  a halfback
    a.j8("75", "rush_done")
    a.b("f74028001c0000")                                 # test dword [eax+0x28],0x1C00  depth rank 0
    a.j8("75", "rush_done")
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
    a.b("69c0" + struct.pack("<I", TACKLE_BONUS_PCT).hex())  # imul eax,eax,TACKLE_BONUS_PCT
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


def _season_merge(a, state):
    """Apply each eligible runner or defender's percentage to this game's stat delta."""
    a.label("tackle_return")
    a.b("60")                                             # pushad
    a.b("8b3d" + _u32(state).hex())                       # edi = player
    a.b("85ff")
    a.j8("74", "merge_done")
    a.b("807f35" + bytes([LEAD_BACK_POSITION]).hex())
    a.j8("75", "merge_tackles")
    a.b("f74728001c0000")                                 # test depth rank bits
    a.j8("75", "merge_tackles")
    a.b("6a025e")                                         # esi = rushing yards field
    a.b("6a" + bytes([RUSH_BONUS_PCT]).hex() + "5d")     # ebp = correction percent
    a.b("8b1d" + _u32(state + 8).hex())                   # ebx = prior rushing yards
    a.j32("e8", "correct_delta")
    a.label("merge_tackles")
    a.b("807f35" + bytes([SKIP_TACKLE_POSITION]).hex())
    a.j8("74", "merge_done")
    a.b("6a125e")                                         # esi = tackles field
    a.b("6a" + bytes([TACKLE_BONUS_PCT]).hex() + "5d")
    a.b("8b1d" + _u32(state + 4).hex())                   # ebx = prior tackles
    a.j32("e8", "correct_delta")
    a.label("merge_done")
    a.b("31c0a3" + _u32(state).hex())                     # clear the hand-off
    a.b("61c20800")                                       # popad; ret 8
    a.label("correct_delta")
    a.b("85ed")                                           # disabled correction
    a.j8("74", "delta_done")
    a.b("89f289f9")                                       # edx = stat, ecx = player
    a.call(FN_STAT_READ)
    a.b("29d8")                                           # sub eax,ebx
    a.j8("7e", "delta_done")
    a.b("0fafc583c03299")                                 # (delta * percent + 50) / 100
    a.b("6a6459f7f9")
    a.b("85c0")
    a.j8("7e", "delta_done")
    a.b("5089f289f9")                                     # add bonus to this player's stat
    a.call(FN_HISTORY_ADD)
    a.label("delta_done")
    a.b("c3")


def _tackle_merge(a, state):
    """b81 fb-targets: the tackle correction alone (cornerbacks skipped), inlined.

    The lead-back rush correction is gone: its constant has been 0 since b780 db2, so that branch never changed a stat
    (correct_delta returned at ``test ebp,ebp``). Its 32 bytes and the rushing-yard read at the entry make the room for the
    fullback target rule; the tackle arithmetic is the same: (delta * TACKLE_BONUS_PCT + 50) / 100 when delta > 0."""
    a.label("tackle_return")
    a.b("60")                                             # pushad
    a.b("8b3d" + _u32(state).hex())                       # edi = player
    a.b("85ff")
    a.j8("74", "merge_done")
    a.b("807f35" + bytes([SKIP_TACKLE_POSITION]).hex())   # cornerbacks: nfl2k5_sim_cb_tackles
    a.j8("74", "merge_done")
    a.b("6a125a89f9")                                     # edx = tackles field, ecx = player
    a.call(FN_STAT_READ)
    a.b("2b05" + _u32(state + 4).hex())                   # sub eax,[prior tackles]
    a.j8("7e", "merge_done")
    a.b("6bc0" + bytes([TACKLE_BONUS_PCT]).hex())        # imul eax,eax,percent
    a.b("83c03299")                                       # add eax,50; cdq
    a.b("6a6459f7f9")                                     # idiv 100
    a.b("85c0")
    a.j8("7e", "merge_done")
    a.b("506a125a89f9")                                   # push bonus; edx = tackles field, ecx = player
    a.call(FN_HISTORY_ADD)
    a.label("merge_done")
    a.b("31c0a3" + _u32(state).hex())                     # clear the hand-off
    a.b("61c20800")                                       # popad; ret 8


def _fullback_target(a):
    """b81 fb-targets: the target site's entry. The target step (retail lottery plus the redirect) runs first; a pick
    with position byte 8 keeps the pass 1 time in 3 (the 16-bit league draw, as the carry rule), otherwise the step runs
    again (up to FB_TARGET_REDRAWS times) and a non-fullback pick goes out as drawn. A fullback drawn every time gives
    the pass to the TE1 lineup slot, else the HB1 slot, else he keeps it. EDI is the sim team at this call (0x10702A:
    mov edi,[0xA9719C]); the target step and the league draw keep EDI and EBP."""
    a.label("fb_entry")
    a.j32("e8", "target")                                 # eax = the target step's pick
    a.b("807835" + bytes([FULLBACK_POSITION]).hex())     # cmp byte [eax+0x35],8
    a.j8("75", "fb_ret")
    a.b("60")                                             # pushad (saved EAX = the fullback)
    a.call(FN_LEAGUE_DRAW)
    a.b("663d" + struct.pack("<H", FB_TARGET_KEEP_THRESHOLD).hex())  # cmp ax,threshold
    a.j8("72", "fb_out")                                  # below: he keeps this pass
    a.b("6a" + bytes([FB_TARGET_REDRAWS]).hex() + "5d")  # ebp = redraws
    a.label("fb_redraw")
    a.j32("e8", "target")
    a.b("807835" + bytes([FULLBACK_POSITION]).hex())
    a.j8("75", "fb_store")                                # not a fullback: this pick
    a.b("4d")                                             # dec ebp
    a.j8("75", "fb_redraw")
    a.b("8b47" + bytes([TE1_SLOT]).hex())                 # mov eax,[edi+0x28]  TE1
    a.b("85c0")
    a.j8("75", "fb_store")
    a.b("8b47" + bytes([HB1_SLOT]).hex())                 # mov eax,[edi+0xc]   HB1
    a.b("85c0")
    a.j8("74", "fb_out")                                  # neither: the fullback keeps it
    a.label("fb_store")
    a.b("8944241c")                                       # mov [esp+0x1c],eax
    a.label("fb_out")
    a.b("61")                                             # popad
    a.label("fb_ret")
    a.b("c3")


def _assemble(code_va, data_va, *, beta80=False, fb=True):
    """beta80: the beta 80 / v0.9 revision. fb=False: the beta 81 revision before the fullback target rule (same
    896 bytes; everything before the tackle entry and the float pool are the same in both)."""
    fb = fb and not beta80
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
    # b780 b5-sim: bias = MIX_BIAS + MIX_QB_SLOPE * (QB1 Pass Accuracy - MIX_QB_PIVOT), so better passers call more passes
    # and weaker ones fewer around the same league mix (eax, ecx and edx are dead here: both paths reload them)
    a.b("a1" + _u32(TEAM_OFFENSE).hex())                  # mov eax,[offense]
    a.b("8b4008")                                         # mov eax,[eax+8]  slot 0 = QB
    a.b("85c0")                                           # test eax,eax
    a.j8("74", "mix_flat")
    a.b("80783500")                                       # cmp byte [eax+0x35],0  a quarterback
    a.j8("75", "mix_flat")
    a.b("0fb64842")                                       # movzx ecx,byte [eax+0x42]  Pass Accuracy
    a.b("83e9" + struct.pack("<b", MIX_QB_PIVOT).hex())   # sub ecx,pivot
    a.b("890d" + _u32(state_out).hex())                   # mov [tmp],ecx
    a.b("db05" + _u32(state_out).hex())                   # fild dword [tmp]
    a.b("d80d" + _u32(code_va + MIX_QB_SLOPE_OFF).hex())  # fmul slope
    a.b("d805" + _u32(code_va + MIX_BIAS_OFF).hex())      # fadd bias
    a.b("d91d" + _u32(state_out).hex())                   # fstp dword [tmp]
    a.b("d9442414")                                       # fld [esp+0x14]
    a.b("d8642418")                                       # fsub [esp+0x18]
    a.b("d81d" + _u32(state_out).hex())                   # fcomp [tmp]  QB-scaled bias
    a.j8("eb", "mix_decide")
    a.label("mix_flat")
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
    a.b("83f9" + bytes([QB_SCRAMBLE_CAP]).hex())                                         # cmp ecx,40
    a.j8("7e", "qb_ok")
    a.b("b9" + _u32(QB_SCRAMBLE_CAP).hex())                                     # mov ecx,40
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

    early_exit = "target_done" if beta80 else "target_native"
    a.b("8b4618")                                         # mov eax,[esi+0x18] WR1 (slot 4)
    a.b("85c0")
    a.j8("74", early_exit)
    a.b("39d8")                                           # cmp eax,ebx
    a.j8("74", early_exit)
    a.b("8b5628")                                         # mov edx,[esi+0x28] TE1 (slot 8)
    a.b("85d2")
    a.j8("74", early_exit)
    a.b("39da")                                           # cmp edx,ebx
    a.j8("74", early_exit)
    if not beta80:
        a.b("395e1c")                                     # cmp [esi+0x1c],ebx: preserve the native WR2 selection
        a.j8("75", "target_rate")
        a.label("target_native")
        a.b("895c241c61c3")                               # return the original receiver
        a.label("target_rate")
    # b780 b5-sim: rate = TARGET_RATE + TARGET_SLOPE * (WR1 Catching - TARGET_PIVOT): an elite WR1 draws more of the other
    # targets, a weaker one fewer (a rate below 0 never redirects; the WR1 pointer is still in eax)
    a.b("0fb64844")                                       # movzx ecx,byte [eax+0x44]  Catching
    a.b("83e9" + struct.pack("<b", TARGET_PIVOT).hex())   # sub ecx,pivot
    a.b("890d" + _u32(state_out).hex())                   # mov [tmp],ecx
    a.b("db05" + _u32(state_out).hex())                   # fild dword [tmp]
    a.b("d80d" + _u32(code_va + TARGET_SLOPE_OFF).hex())  # fmul slope
    a.b("d805" + _u32(code_va + TARGET_RATE_OFF).hex())   # fadd rate
    a.b("d91d" + _u32(state_out).hex())                   # fstp dword [tmp]
    a.b("b9" + _u32(MATCH_RNG).hex())
    a.call(FN_RAND)
    a.b("d81d" + _u32(state_out).hex())                   # fcomp [tmp]
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
    if not beta80:
        # Share receiver redirects only when the second depth slot holds a competitive WR.
        a.b("8b7e1c")                                     # mov edi,[esi+0x1c] WR2 (slot 5)
        a.b("85ff")
        a.j8("74", "target_done")
        a.b("807f3503")                                   # cmp byte [edi+0x35],WR
        a.j8("75", "target_done")
        a.b("0fb64f44")                                   # movzx ecx,byte [edi+0x44] WR2 Catching
        a.b("83f9" + bytes([WR2_MIN_CATCH]).hex())
        a.j8("72", "target_done")
        a.b("83c1" + bytes([WR2_MAX_CATCH_GAP]).hex())
        a.b("0fb64344")                                   # movzx eax,byte [ebx+0x44] WR1 Catching
        a.b("39c1")
        a.j8("72", "target_done")
        a.b("b9" + _u32(MATCH_RNG).hex())
        a.call(FN_RAND)
        a.b("d81d" + _u32(code_va + WR2_SHARE_OFF).hex())
        a.b("dfe0")
        a.b("f6c401")
        a.j8("74", "target_done")
        a.b("89fb")                                       # mov ebx,edi
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
    if fb:
        # b81 fb-targets: [state] = the player (0 outside the scheduled sim) and [state+4] = his tackles; the rushing
        # yards read went with the lead-back correction (see _tackle_merge)
        a.b("31c0")                                       # xor eax,eax
        a.b("803d" + _u32(SIM_MODE).hex() + "04")         # cmp byte [mode],4
        a.j8("75", "tackle_entry_store")
        a.b("6a125a89f9")                                 # edx = 18, ecx = player
        a.call(FN_STAT_READ)
        a.b("a3" + _u32(state + 4).hex())
        a.b("89f8")                                       # mov eax,edi
        a.label("tackle_entry_store")
        a.b("a3" + _u32(state).hex())
        a.b("61")                                         # popad
        a.b("8d9424e0000000")                             # lea edx,[esp+0xe0] (replayed +4)
        a.b("83c404")                                     # add esp,4
        a.jmp_abs(TACKLE_ENTRY_RESUME)
        _tackle_merge(a, state)
        _fullback_target(a)
        return _finish(a, code_va, beta80)
    a.b("31c0")                                           # xor eax,eax
    a.b("a3" + _u32(state).hex())                         # [state]=0
    a.b("803d" + _u32(SIM_MODE).hex() + "04")             # cmp byte [mode],4
    a.j8("75", "tackle_entry_skip")
    a.b("89f8")                                           # mov eax,edi
    a.b("a3" + _u32(state).hex())
    a.b("ba12000000" if beta80 else "6a125a")                                     # mov edx,18
    a.b("89f9")                                           # mov ecx,edi
    a.call(FN_STAT_READ)
    a.b("a3" + _u32(state + 4).hex())
    a.b("ba02000000" if beta80 else "6a025a")                                     # mov edx,2
    a.b("89f9")                                           # mov ecx,edi
    a.call(FN_STAT_READ)
    a.b("a3" + _u32(state + 8).hex())
    a.label("tackle_entry_skip")
    a.b("61")                                             # popad
    a.b("8d9424e0000000")                                 # lea edx,[esp+0xe0] (replayed +4)
    a.b("83c404")                                         # add esp,4
    a.jmp_abs(TACKLE_ENTRY_RESUME)

    if beta80:
        _beta80_merge(a, state)
    else:
        _season_merge(a, state)
    return _finish(a, code_va, beta80)


def _finish(a, code_va, beta80):
    body = bytearray(a.assemble())
    require(len(body) <= FLOAT_POOL, f"sim realism code is {len(body)} bytes, float pool {FLOAT_POOL}")
    body = body.ljust(FLOAT_POOL, b"\xcc")
    qb_scale, qb_yards, pass_scale = (0.0036, 3.0, 0.86) if beta80 else (QB_SCRAMBLE_SCALE, QB_BONUS_YARDS, PASS_SCALE)
    pool = (_flt(MIX_BIAS) + _flt(TARGET_RATE) + _flt(TARGET_WR1_SHARE) + _flt(qb_scale)
            + _flt(qb_yards) + _flt(INTERCEPT_SCALE) + _flt(pass_scale) + _flt(TACKLE_BONUS_PCT)
            + _flt(QB_BONUS_RZ_LINE) + _flt(RUN_RZ_SCALE) + _flt(RUSH_BONUS_PCT)
            + _flt(RZ_PASS_SCALE))
    pool = (pool.ljust(RED_ZONE_OFF - FLOAT_POOL, b"\xcc") + _flt(79.5) + _flt(0.0) + _flt(MIX_QB_SLOPE)
            + _flt(TARGET_SLOPE))
    if not beta80:
        pool += _flt(WR2_SHARE)
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


def sites(code_va, *, beta80=False, fb=True):
    """fb=False: the beta 81 revision before the fullback target rule (its target site calls the target step itself)."""
    fb = fb and not beta80
    offs = (_assemble(code_va, 0, beta80=True)[0].labels if beta80 else label_offsets() if fb
            else _assemble(code_va, 0, fb=False)[0].labels)
    hook = lambda label, site, before, off: (label, site, before,
                                             b"\xe8" + struct.pack("<i", code_va + off - site - 5))
    mix = ("mix", MIX_SITE, MIX_BEFORE, b"\xe8" + struct.pack("<i", code_va - MIX_SITE - 5) + b"\x90" * 4)
    tackle_return = ("tackle_return", TACKLE_RETURN_SITE, TACKLE_RETURN_BEFORE,
                     b"\xe9" + struct.pack("<i", code_va + offs["tackle_return"] - TACKLE_RETURN_SITE - 5))
    out = [mix,
           ("qb", QB_SITE, QB_BEFORE, b"\xe8" + struct.pack("<i", code_va + offs["qb"] - QB_SITE - 5) + b"\x90"),
           hook("target", TARGET_SITE, TARGET_BEFORE, offs["fb_entry" if fb else "target"]),
           hook("intercept", INTERCEPT_SITE, INTERCEPT_BEFORE, offs["int"]),
           ("tackle_entry", TACKLE_ENTRY_SITE, TACKLE_ENTRY_BEFORE,
            b"\xe8" + struct.pack("<i", code_va + offs["tackle_entry"] - TACKLE_ENTRY_SITE - 5) + b"\x90\x90"),
           tackle_return,
           ("run_bonus", RUN_BONUS_SITE, RUN_BONUS_BEFORE,
            b"\xe8" + struct.pack("<i", code_va + offs["qb_bonus"] - RUN_BONUS_SITE - 5) + b"\x90")]
    out += [hook(f"pass_scale_{i}", site, before, offs["pass_scale"]) for i, (site, before) in enumerate(PASS_SITES)]
    return out


# b780 n6: beta-79 / v0.8 carries the 832-byte revision (frozen in nfl2k5_sim_realism_b779). It reads "previous";
# this release's 896 bytes do not fit its allocation, so apply() refuses to update it in place (rebuild from retail).
PREVIOUS_REVISION = "beta-79"
PREVIOUS_REFUSAL = ("Simulated season realism on this disc is the beta 79 revision. This release's version is larger "
                    "than the room the earlier build gave it, so it cannot be updated in place. Rebuild from your "
                    "retail game, or turn Simulated season realism off to keep the beta 79 version.")


def _previous_module():
    from . import nfl2k5_sim_realism_b779 as previous
    return previous


def _revision(payload):
    """(code size, code_for, sites) of the revision whose allocation this image carries (this release by default)."""
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER and r["kind"] == "code"]
    previous = _previous_module()
    if len(rows) == 1 and rows[0]["size"] == previous.CODE_SIZE:
        return previous.CODE_SIZE, previous.code_for, previous.sites, "previous"
    if rows and rows[0]["size"] == CODE_SIZE:
        from .nfl2k5_cave_oracle import XbeImage
        code, data = _allocations(payload)
        def old_code(va, state):
            return _assemble(va, state, beta80=True)[1]
        raw = XbeImage(payload).read(code["va"], CODE_SIZE)
        if raw == old_code(code["va"], data["va"]):
            return CODE_SIZE, old_code, lambda va: sites(va, beta80=True), "beta80"
        # b81 fb-targets: the revision before the fullback target rule. It differs from this one only from the tackle
        # entry to the float pool, bytes the simulated QB injury option never edits (it edits the mix block and the
        # pool), so the choice is right on an executable with that option installed too.
        def b81_code(va, state):
            return _assemble(va, state, fb=False)[1]
        tail = slice(label_offsets()["tackle_entry"], FLOAT_POOL)
        if raw[tail] == b81_code(code["va"], data["va"])[tail]:
            return CODE_SIZE, b81_code, lambda va: sites(va, fb=False), "b81"
    return CODE_SIZE, code_for, sites, "applied"


def installed_sites(payload):
    """The installed revision's sites (this release's or the beta-79 one), [] without the owner's allocation. Owners
    that restore this one's hooks before hashing a shared context (nfl2k5_sim_cb_tackles) use this."""
    code, _data = _allocations(payload)
    return _revision(payload)[2](code["va"])


def _allocations(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    code = [r for r in rows if r["kind"] == "code"]
    data = [r for r in rows if r["kind"] == "data"]
    require(len(code) == 1 and (code[0]["size"], code[0]["align"]) in ((CODE_SIZE, 16), (_previous_module().CODE_SIZE, 16)),
            "Missing or foreign sim realism code allocation")
    require(len(data) == 1 and (data[0]["size"], data[0]["align"]) == (DATA_SIZE, 4),
            "Missing or foreign sim realism data allocation")
    return code[0], data[0]


def _recognize(payload):
    from . import nfl2k5_sim_qb_injuries as quarterback
    return _recognize_physical(quarterback.physical_view(payload))


def _recognize_physical(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    code = data = None
    size, make_code, make_sites, installed = CODE_SIZE, code_for, sites, "applied"
    if present:
        code, data = _allocations(payload)
        size, make_code, make_sites, installed = _revision(payload)
    edits = make_sites(code["va"] if code else 0)
    states = set()
    for _label, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if code and raw == after else "foreign")
    if code:
        raw = image.read(code["va"], size)
        expected = make_code(code["va"], data["va"])
        states.add("retail" if raw == b"\xcc" * size else "applied" if raw == expected else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed sim realism site/code")
    state = next(iter(states))
    if state == "applied" and installed in ("previous", "beta80", "b81"):
        return installed
    require(state == "applied" or size == CODE_SIZE, "an empty beta-79 sim realism allocation; rebuild from retail")
    return state


def apply(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    state = _recognize(payload)
    require(state != "foreign", "sim realism: foreign bytes")
    require(state != "previous", PREVIOUS_REFUSAL)
    if state == "applied":
        code, data = _allocations(payload)
        return payload, {"owner": OWNER, "status": "already_applied", "code_va": hex(code["va"]),
                         "data_va": hex(data["va"]), "changed_bytes": 0}
    if state == "b81":
        # b81 fb-targets: a beta 81 executable with the simulated QB injury option installed carries that option's
        # edits inside this owner's code (the mix block and the float pool). Update the physical executable beneath
        # it, then write the option again exactly as it was; none of its bytes is one this update changes.
        from . import nfl2k5_sim_qb_injuries as quarterback
        physical = quarterback.physical_view(payload)
        if physical != payload:
            upgraded, receipt = apply(physical)
            result = quarterback.reinstall_on(payload, upgraded)
            require(_recognize(result) == "applied" and quarterback.physical_view(result) == upgraded,
                    "Simulated season realism update beneath the QB injury option failed")
            return result, {**receipt, "simulated_qb_injuries_kept": True,
                            "changed_bytes": space.count_differing_bytes(payload, result),
                            "file_growth": len(result) - len(payload)}
    before = payload
    receipt = {}
    # b779-int1: a full build allocates this owner with the selected request set (nfl2k5_throw_tuning) before this
    # step installs the code; reuse that allocation, as the RB injury owner does ("owner already allocated in this
    # image" stopped the observed cave build and would have stopped the release build).
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "Simulated season realism needs the scale-out allocator")
            payload, receipt = space.extend_scaleout(payload, REQUESTS)
    code, data = _allocations(payload)
    # In-place updates in the same allocation: the beta 80 / v0.9 revision and the beta 81 one before the fullback
    # target rule (b81 fb-targets).
    revision = {"beta80": {"beta80": True}, "b81": {"fb": False}}.get(state)
    previous = _assemble(code["va"], data["va"], **revision)[1] if revision else None
    old_hooks = {va: after for _, va, _, after in sites(code["va"], **revision)} if revision else {}
    payload, _ = space.install_code(payload, OWNER, code_for(code["va"], data["va"]), previous=previous)
    image = XbeImage(payload)
    buf = bytearray(payload)
    edits = [(label, va, old_hooks.get(va, old), new) for label, va, old, new in sites(code["va"])]
    for _label, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"Unrecognized sim realism site {va:#x}")
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
    """retail | applied | legacy (the beta 80 / v0.9 revision, or beta 81's before the fullback target rule; apply()
    updates both in place) | previous (beta 79; rebuild from retail) | foreign. Beta 81 review: the beta 80 revision used
    to read "applied", so a disc report could not tell v0.9 from v0.10."""
    try:
        state = _recognize(payload)
        return "legacy" if state in ("beta80", "b81") else state
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError):
        return "foreign"


__all__ = ["OWNER", "CODE_SIZE", "DATA_SIZE", "REQUESTS", "BUILD_CAPTION", "HELP_TEXT",
           "MIX_BIAS", "TARGET_RATE", "TARGET_WR1_SHARE", "QB_BONUS_YARDS", "QB_BONUS_RZ_LINE",
           "INTERCEPT_SCALE", "PASS_SCALE", "RUN_RZ_SCALE", "RZ_PASS_SCALE",
           "TACKLE_BONUS_PCT", "RUSH_BONUS_PCT", "tackle_bonus", "rush_bonus", "pass_rz_scale",
           "run_rz_scale", "qb_carry_rate", "code_for", "sites", "apply",
           "status", "SimRealismError", "installed_sites", "PREVIOUS_REVISION", "PREVIOUS_REFUSAL"]
