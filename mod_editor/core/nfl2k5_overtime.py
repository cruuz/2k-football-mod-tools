"""Modern (2025-rule) overtime for ESPN NFL 2K5 (executable patch, xemu-only).

Retail rules, all proved in the retail ``default.xbe`` (see ``OVERTIME_2026-09-03.md``):

* the period number is ``DAT_00e602c4`` (1..4 quarters, 5 = overtime, 6+ further overtime
  periods); the period length is ``DAT_00e602b0`` = quarter-length option (``DAT_00e6000c``,
  minutes) x 60, written once per game at 0x55F5B in the game-init routine ``FUN_00055dd0``, and
  the running clock is ``[DAT_00e6028c + 0x10]`` (float seconds); every period start
  (``FUN_000b8910``) resets the clock to the period length, so retail overtime runs a full
  quarter length, not 15:00;
* **sudden death**: the post-play evaluator ``FUN_000a11f0`` (0xA130F..0xA132F) ends the game
  (state 10) after any play in period >= 5 whose end leaves the scores different;
* **end of a period** (``FUN_000b8a60``, called from the clock tick ``FUN_00157d40``): in
  period >= 5 with the scores different the game ends; tied it plays another overtime period
  unless the game mode ``DAT_00e5ff80`` is 7 (franchise pre/regular season) and the period is
  5, in which case it ends as a tie.  ``FUN_000b8b30`` restarts the next period after the
  presentation with the same test.  Modes 5 and 6 (tournament, franchise postseason) never
  tie; overtime timeouts are already 2 in mode 7 and 3 otherwise (``FUN_000b81c0``);
* the overtime kickoff is built by ``FUN_001587f0`` (period 5 only); ``FUN_000e9460`` leaves the
  kicking team in ``DAT_00e60280`` and the receiving team in ``DAT_00e60284``, and the kick
  dead-ball evaluator swaps them when the kick is fielded, so at the end of every play
  ``DAT_00e60280`` is the team in possession (turnovers swap it in the dead-ball pass);
* the franchise **simulator** is a separate statistical engine (``FUN_0010b280`` and the
  handler table at 0xA96930): it keeps its own period index ``DAT_00a971f0`` (4 = overtime),
  clock fraction ``DAT_00a971f8`` and its own sudden death (``FUN_001061f0``, scoring handlers
  ``return 5`` in period index >= 4); when an overtime period ends tied it plays another one
  unless a once-per-game 1-in-40 roll (``DAT_00a971d4``, only rolled when the caller allows
  ties) permits a tie.

The patch (two caves, both dead functions with no reference anywhere in the image):

* ``regular_minutes`` (10): at the overtime kickoff the period length ``DAT_00e602b0`` is scaled
  by ``regular_minutes / 15`` unless the mode is 5 or 6, and the clock is reloaded from it, so
  the scorebug, the AI's time-remaining maths and the simulator's overtime detection all see
  the same shorter period (a 15-minute quarter setting gives exactly 10:00; the default 5-minute
  setting gives 3:20).  The game-init store at 0x55F5B also clears the patch state.
* ``both_possessions``: the sudden-death test becomes "game over when the scores differ AND
  (a safety just happened, or the team in possession leads and its opponent has already had a
  possession)".  Possession flags (one bit per team in the unreferenced BSS dword 0xE602A8)
  are cleared at the overtime kickoff and set for the team in possession at the end of every
  play.  A kickoff is the receiving team's opportunity to possess (Art. 5(c)), but the kickoff
  after a score is built by ``FUN_0022e4d0`` in the same dead-ball pass that applies the score,
  BEFORE the post-play evaluator judges the scoring play (``FUN_000b95f0`` applies the
  descriptor, then sets state 0xb; the evaluator runs from the presentation state change and
  switches on that 0xb).  So the receiving team of every kickoff is only marked *pending*
  (bits 2/3) when the kickoff is built, and the pending bits become possession bits at the
  first post-play evaluation whose next play is not a kickoff (phase != 2), i.e. once the
  kickoff has actually been played.  The 2026-09-04 bug (a first-possession field goal ended
  the game) was the receiving team being flagged at build time and read as "has possessed" by
  the evaluator of the field-goal play itself.  The Situation screen (``FUN_0010bd80``) seeds
  the period, scores, clock and possession directly and never runs the overtime kickoff
  builder, so its possession store also clears the flags.
* ``postseason_no_ties``: in modes 5/6 an overtime period that expires with the trailing team
  still on its first possession continues into another period (the retail code only continues
  when tied); regular-season games keep retail's one-period-then-tie rule.
* ``sim_engine``: the simulator's overtime period gets the same ``regular_minutes / 15`` clock
  fraction and a regular-season game that is still tied after it ends as a tie instead of the
  1-in-40 roll; playoff simulations keep playing periods.  The simulator's sudden death and
  possession rule are NOT changed (documented follow-up).

Everything is pattern-checked against the retail bytes and the ``.text`` digest is recomputed.
Unverified at runtime.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_draft_ai import _Asm

IMAGE_BASE = 0x10000
NFL_QUARTER_MINUTES = 15.0
RETAIL_REGULAR_MINUTES = 15.0        # retail overtime = one full quarter length
MIN_REGULAR_MINUTES = 1.0
MAX_REGULAR_MINUTES = 15.0

# --- game globals ------------------------------------------------------------------------------
PERIOD_GLOBAL = 0x00E602C4          # 1..4, 5 = OT, 6+ = further OT periods
PERIOD_LENGTH_GLOBAL = 0x00E602B0   # float seconds, quarter length x 60 (written once at 0x55F5B)
CLOCK_OBJECT_GLOBAL = 0x00E6028C    # [+0x10] = running game clock (float seconds)
PHASE_GLOBAL = 0x00E602B4           # 0 pregame/OT toss, 1 safety kick, 2 kickoff, 3 point after, 4 scrimmage
MODE_GLOBAL = 0x00E5FF80            # 5 tournament, 6 franchise postseason, 7 franchise pre/regular season
POSSESSION_GLOBAL = 0x00E60280      # team with the ball (kicking team during a kickoff)
DEFENSE_GLOBAL = 0x00E60284         # the other team (receiving team during a kickoff)
HOME_TEAM = 0x00E5FC20              # the two team objects; [team+0] = opponent, [team+8] = score object
HOME_SCORE_PTR = 0x00E5FC28         # -> score object ([+0] = points, [+4] = timeouts)
AWAY_SCORE_PTR = 0x00E5FC68
NO_TIE_MODES = (5, 6)
STATE_GLOBAL = 0x00E602A8           # BSS dword with no reference in the image: our state
STATE_FLAGS = STATE_GLOBAL          # byte: bit0 home has possessed in OT, bit1 away; bit2/bit3 = pending
                                    #       (receiving team of a kickoff that has not been played yet)
FLAG_POSSESSED = 1                  # flag_team mask for "has possessed" (home bit; away = mask << 1)
FLAG_PENDING = 4                    # flag_team mask for "kickoff opportunity pending"
STATE_SCALED = STATE_GLOBAL + 1     # byte: 1 once the period length has been scaled this game
STATE_SIM_TIES = STATE_GLOBAL + 2   # byte: 1 when the simulator was told ties are allowed (regular season)

# simulator globals
SIM_PERIOD_INDEX = 0x00A971F0       # 0..3 quarters, 4 = overtime column
SIM_CLOCK_FRACTION = 0x00A971F8     # 1.0 at a period start, counts down to 0
SIM_TIE_ROLL = 0x00A971D4           # retail: 1 when the 1-in-40 roll allows a tie this game
SIM_SCRATCH_ZEROED = 0x00A971C4     # a sim global zeroed at every sim setup (our reset hook rides it)

FN_KICK_SETUP = 0x000E9380          # builds the kick spot for the kicking team (fastcall ecx = spot)
FN_SET_POSSESSION = 0x000E9460      # possession := ecx, defense := [ecx] (fastcall ecx = team, edx = direction)

# --- caves --------------------------------------------------------------------------------------
MAIN_CAVE_VA = 0x001AFDF0           # FUN_001afdf0: dead AI helper, 300 bytes (sibling of the kick-rules cave)
MAIN_CAVE_SIZE = 300
AUX_CAVE_VA = 0x0028B410            # FUN_0028b410: dead helper, 233 bytes, zero references
AUX_CAVE_SIZE = 233
SCALE_VA = MAIN_CAVE_VA             # float regular_minutes / 15
MAIN_CODE_VA = MAIN_CAVE_VA + 4

RETAIL_MAIN_CAVE = bytes.fromhex(
    "558bec83e4f083ec2856578bf9e8ae4bfaff8b0d00fce50085c9740c8b0185c0740683781c01740233c03bc775"
    "05e80de0f2ff8b4f2033d2e8c39c11008bf0c70660f41a00e8066ff8ff8946408b47388b48140f28010f294620"
    "d94620d81d80414e00b9a0fce500dfe0f6c4417519e82c8de9ffd82d84414e00d80d4c0f4f00d8054c0f4f00eb"
    "17e8138de9ffd82d84414e00d80d4c0f4f00d82d749b5000d95e20b9a0fce500e8f48ce9ffd82d84414e00d80d"
    "4c0f4f00d84628d95e28e88d6ef8ff85c0745fe8846ef8ffd946208b50180f2842300f29442410d86424108d44"
    "2420d95c2420d94624d8642414d95c2424d94628d8642418d95c2428d9462cd864241cd95c242ce8e3c5ffffd8"
    "1d5c0f4f00dfe0f6c4057a0cd94628d80524dd4e00d95e285f5e8be55dc3"
)
RETAIL_AUX_CAVE = bytes.fromhex(
    "558bec83e4f083ec448b450853568d34d28bd98b4b08c1e6028d5440128b040e578b3c9085ff0f84b40000008b"
    "cfe8fd64d9ff506a008bcfe83365d9ff8b4b08508b440e0483c0408bcf89442418e8cd64d9ff8b4c24188bd18b"
    "c8e8608fd9ff8b53088b04168d0c168b90b400000085d2746dd94038d81d80414e00dfe0f6c441755d8b51048d"
    "4424108d9b000000000f28020f290083c0108d74245083c2103bc672ec8b4104d94070d95c24408b5104d94278"
    "d95c24488b018b503452680000803f8bc2508d44241ce8a1f1ffff8b098b89b40000008d542410e8b080f3ff5f"
    "5e5b8be55dc20400"
)

# --- hook sites (VA, retail bytes) --------------------------------------------------------------
INIT_SITE_VA = 0x00055F5B           # FUN_00055dd0: fstp dword [0xE602B0]  (period length store)
RETAIL_INIT = bytes.fromhex("d91db002e600")
OT_KICKOFF_SITE_VA = 0x0015885E     # FUN_001587f0: call FUN_000e9380 (overtime kickoff builder)
RETAIL_OT_KICKOFF = bytes.fromhex("e81d0bf9ff")
KICKOFF_SITE_VA = 0x0022E588        # FUN_0022e4d0: call FUN_000e9380 (kickoff after a score)
RETAIL_KICKOFF = bytes.fromhex("e8f3adebff")
SITUATION_SITE_VA = 0x0010BDD4      # FUN_0010bd80 (Situation screen): call FUN_000e9460 (possession seed)
RETAIL_SITUATION = bytes.fromhex("e887d6fdff")
PRED_SITE_VA = 0x000A130F           # FUN_000a11f0: the sudden-death test, 33 bytes to 0xA1330
RETAIL_PRED = bytes.fromhex("a1c402e60083f8047e158b1528fce5008b0a8b1568fce5003b0a753983f804755e")
PRED_GAME_OVER_VA = 0x000A1364      # state 10 path
PRED_CONTINUE_VA = 0x000A138E       # state 11 path
EXPIRY_SITE_VA = 0x000B8ACF         # FUN_000b8a60 default case: home/away compare, 16 bytes
RETAIL_EXPIRY = bytes.fromhex("a128fce5008b10a168fce5003b10751c")
EXPIRY_DIFFER_VA = 0x000B8AFB
EXPIRY2_SITE_VA = 0x000B8B68        # FUN_000b8b30 default case: home/away compare, 18 bytes
RETAIL_EXPIRY2 = bytes.fromhex("8b0d28fce5008b118b0d68fce5003b117508")
EXPIRY2_DIFFER_VA = 0x000B8B82
SIM_RESET_SITE_VA = 0x0010B2B4      # FUN_0010b280: mov [0xA971C4], ebx (ebx == 0)
RETAIL_SIM_RESET = bytes.fromhex("891dc471a900")
SIM_ROLL_SITE_VA = 0x0010B2FA       # FUN_0010b280: mov ecx, 0x28 ; div ecx   (the 1-in-40 tie roll)
RETAIL_SIM_ROLL = bytes.fromhex("b928000000f7f1")
SIM_TIE_SITE_VA = 0x00106409        # FUN_001061f0: mov eax, [0xA971D4] ; test eax, eax ; jne +0x15
RETAIL_SIM_TIE = bytes.fromhex("a1d471a90085c07515")
SIM_TIE_CONTINUE_VA = 0x00106427    # "game over" path of that test
SIM_PERIOD_SITE_VA = 0x0010720C     # FUN_001071e0 (period kickoff handler): mov [0xA971F8], 1.0
RETAIL_SIM_PERIOD = bytes.fromhex("c705f871a9000000803f")

GROUPS = ("core", "possession", "postseason", "sim")


class OvertimeError(ValueError):
    """The overtime patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OvertimeError(message)


def _f32(value: float) -> bytes:
    return struct.pack("<f", value)


def _validate_minutes(regular_minutes: float) -> float:
    minutes = round(float(regular_minutes), 3)
    _require(MIN_REGULAR_MINUTES <= minutes <= MAX_REGULAR_MINUTES,
             f"regular_minutes {minutes} outside {MIN_REGULAR_MINUTES:g}..{MAX_REGULAR_MINUTES:g}")
    return minutes


def scale_for(regular_minutes: float) -> float:
    """The factor applied to the period length in overtime (NFL minutes over a 15-minute quarter)."""

    return _validate_minutes(regular_minutes) / NFL_QUARTER_MINUTES


def overtime_clock_seconds(quarter_minutes: float, regular_minutes: float = 10) -> float:
    """What the overtime clock reads for a given Quarter Length option (regular-season game)."""

    return round(float(quarter_minutes) * 60.0 * scale_for(regular_minutes), 3)


# --- cave code ----------------------------------------------------------------------------------

def _imm(va: int) -> str:
    return struct.pack("<I", va).hex()


def _main_code(base: int) -> tuple[bytes, dict[str, int]]:
    """Main cave: init store, the possession flag setter, the sudden-death test, the expiry test."""

    a = _Asm(base)
    # ---- init: replaces `fstp dword [period length]` in FUN_00055dd0; clears our state
    a.label("init")
    a.b("d91d" + _imm(PERIOD_LENGTH_GLOBAL))       # fstp dword [0xE602B0]
    a.b("c705" + _imm(STATE_GLOBAL) + "00000000")  # mov dword [state], 0
    a.b("c3")
    # ---- flag_team(ecx = team, dl = mask): or [flags], home ? mask : mask << 1   (ecx read, dl clobbered)
    a.label("flag_team")
    a.b("85c9")                                     # test ecx, ecx
    a.j8("74", "ft_ret")
    a.b("81f9" + _imm(HOME_TEAM))                   # cmp ecx, home team
    a.j8("75", "ft_away")
    a.b("0815" + _imm(STATE_FLAGS))                 # or byte [flags], dl
    a.b("c3")
    a.label("ft_away")
    a.b("00d2")                                     # add dl, dl           the away bit
    a.b("0815" + _imm(STATE_FLAGS))                 # or byte [flags], dl
    a.label("ft_ret")
    a.b("c3")
    # ---- ot_check: eax := period; ZF = 1 iff the overtime rule ends the game now.
    #      Called in place of the retail sudden-death compare; esi is live at the site (untouched).
    a.label("ot_check")
    a.b("a1" + _imm(PERIOD_GLOBAL))                 # mov eax, [period]
    a.b("83f805")                                   # cmp eax, 5
    a.j8("7c", "not_over")                          # jl: not overtime
    a.b("833d" + _imm(PHASE_GLOBAL) + "02")         # cmp dword [phase], 2  a kickoff is pending (a score
    a.j8("74", "scores")                            #   was just applied): its receiver has not possessed yet
    a.b("a0" + _imm(STATE_FLAGS))                   # mov al, [flags]       the kickoff has been played:
    a.b("8ac8")                                     # mov cl, al              pending bits -> possession bits
    a.b("c0e902")                                   # shr cl, 2
    a.b("0ac1")                                     # or al, cl
    a.b("2403")                                     # and al, 3
    a.b("a2" + _imm(STATE_FLAGS))                   # mov [flags], al
    a.b("8b0d" + _imm(POSSESSION_GLOBAL))           # mov ecx, [possession]
    a.b("85c9")
    a.j8("74", "not_over")                          # nobody in possession: leave it
    a.b("b2" + f"{FLAG_POSSESSED:02x}")             # mov dl, 1
    a.j32("e8", "flag_team")                        # this team has possessed the ball
    a.label("scores")
    a.b("8b15" + _imm(HOME_SCORE_PTR))              # mov edx, [home score obj]
    a.b("8b12")                                     # mov edx, [edx]        home points
    a.b("8b0d" + _imm(AWAY_SCORE_PTR))              # mov ecx, [away score obj]
    a.b("3b11")                                     # cmp edx, [ecx]        home vs away
    a.j8("74", "not_over")                          # tied: play on
    a.b("833d" + _imm(PHASE_GLOBAL) + "01")         # cmp dword [phase], 1  safety just scored?
    a.j8("74", "over")
    a.b("8b0d" + _imm(POSSESSION_GLOBAL))           # mov ecx, [possession]
    a.b("8b5108")                                   # mov edx, [ecx+8]      score object
    a.b("8b12")                                     # mov edx, [edx]        possessor's points
    a.b("8b01")                                     # mov eax, [ecx]        opponent
    a.b("8b4008")                                   # mov eax, [eax+8]
    a.b("8b00")                                     # mov eax, [eax]        opponent's points
    a.b("3bd0")                                     # cmp edx, eax
    a.j8("7e", "not_over")                          # possessor not leading: its drive goes on
    a.b("8b09")                                     # mov ecx, [ecx]        opponent team
    a.b("81f9" + _imm(HOME_TEAM))
    a.j8("75", "chk_away")
    a.b("f605" + _imm(STATE_FLAGS) + "01")          # test byte [flags], 1  opponent (home) possessed?
    a.j8("75", "over")
    a.j8("eb", "not_over")
    a.label("chk_away")
    a.b("f605" + _imm(STATE_FLAGS) + "02")
    a.j8("75", "over")
    a.label("not_over")
    a.b("a1" + _imm(PERIOD_GLOBAL))                 # mov eax, [period]
    a.b("83fc00")                                   # cmp esp, 0            ZF = 0
    a.b("c3")
    a.label("over")
    a.b("a1" + _imm(PERIOD_GLOBAL))
    a.b("39c0")                                     # cmp eax, eax          ZF = 1
    a.b("c3")
    # ---- ot_expiry: ZF = 1 iff "treat the period end as tied" (tied, or a no-tie mode with the
    #      trailing team still in possession).  Preserves every register.
    a.label("ot_expiry")
    a.b("50")                                       # push eax
    a.b("51")                                       # push ecx
    a.b("52")                                       # push edx
    a.b("8b15" + _imm(HOME_SCORE_PTR))
    a.b("8b12")
    a.b("8b0d" + _imm(AWAY_SCORE_PTR))
    a.b("3b11")
    a.j8("74", "exp_tied")
    a.b("833d" + _imm(MODE_GLOBAL) + f"{NO_TIE_MODES[1]:02x}")   # cmp dword [mode], 6
    a.j8("74", "exp_mode_ok")
    a.b("833d" + _imm(MODE_GLOBAL) + f"{NO_TIE_MODES[0]:02x}")   # cmp dword [mode], 5
    a.j8("75", "exp_differ")
    a.label("exp_mode_ok")
    a.b("833d" + _imm(PERIOD_GLOBAL) + "05")        # cmp dword [period], 5
    a.j8("7c", "exp_differ")
    a.b("8b0d" + _imm(POSSESSION_GLOBAL))
    a.b("85c9")
    a.j8("74", "exp_differ")
    a.b("8b5108")                                   # possessor's points
    a.b("8b12")
    a.b("8b01")                                     # opponent's points
    a.b("8b4008")
    a.b("8b00")
    a.b("3bd0")
    a.j8("7d", "exp_differ")                        # possessor not trailing: the game is decided
    a.label("exp_tied")
    a.b("5a")
    a.b("59")
    a.b("58")
    a.b("39c0")                                     # ZF = 1
    a.b("c3")
    a.label("exp_differ")
    a.b("5a")
    a.b("59")
    a.b("58")
    a.b("83fc00")                                   # ZF = 0
    a.b("c3")
    a.label("end")
    code = a.assemble()
    return code, {name: base + off for name, off in a.labels.items()}


def _aux_code(base: int, flag_team_va: int) -> tuple[bytes, dict[str, int]]:
    """Aux cave: the two kickoff hooks and the simulator hooks."""

    a = _Asm(base)
    # ---- ot_kickoff: replaces `call FUN_000e9380` in the overtime kickoff builder (ecx = spot)
    a.label("ot_kickoff")
    a.b("803d" + _imm(STATE_SCALED) + "00")         # cmp byte [scaled], 0
    a.j8("75", "ok_clock")
    a.b("833d" + _imm(MODE_GLOBAL) + f"{NO_TIE_MODES[1]:02x}")
    a.j8("74", "ok_clock")                          # postseason: full length
    a.b("833d" + _imm(MODE_GLOBAL) + f"{NO_TIE_MODES[0]:02x}")
    a.j8("74", "ok_clock")
    a.b("d905" + _imm(PERIOD_LENGTH_GLOBAL))        # fld dword [period length]
    a.b("d80d" + _imm(SCALE_VA))                    # fmul dword [scale]
    a.b("d91d" + _imm(PERIOD_LENGTH_GLOBAL))        # fstp dword [period length]
    a.b("c605" + _imm(STATE_SCALED) + "01")         # mov byte [scaled], 1
    a.label("ok_clock")
    a.b("51")                                       # push ecx
    a.b("a1" + _imm(PERIOD_LENGTH_GLOBAL))          # mov eax, [period length]
    a.b("8b0d" + _imm(CLOCK_OBJECT_GLOBAL))         # mov ecx, [clock object]
    a.b("894110")                                   # mov [ecx+0x10], eax   clock := period length
    a.b("c605" + _imm(STATE_FLAGS) + "00")          # mov byte [flags], 0
    a.b("8b0d" + _imm(DEFENSE_GLOBAL))              # mov ecx, [receiving team]
    a.b("b2" + f"{FLAG_PENDING:02x}")               # mov dl, 4
    a.call(flag_team_va)                            # its opportunity to possess, pending until played
    a.b("59")                                       # pop ecx
    a.jmp_abs(FN_KICK_SETUP)                        # tail-call the replaced routine
    # ---- kickoff_flag: replaces `call FUN_000e9380` in the kickoff-after-score builder
    a.label("kickoff_flag")
    a.b("833d" + _imm(PERIOD_GLOBAL) + "05")        # cmp dword [period], 5
    a.j8("7c", "kf_done")
    a.b("51")
    a.b("8b0d" + _imm(DEFENSE_GLOBAL))
    a.b("b2" + f"{FLAG_PENDING:02x}")               # mov dl, 4             pending, not possessed: the
    a.call(flag_team_va)                            #   evaluator of the scoring play runs after this build
    a.b("59")
    a.label("kf_done")
    a.jmp_abs(FN_KICK_SETUP)
    # ---- situation: replaces `call FUN_000e9460` in the Situation screen's game seed (ecx = team, edx = dir)
    a.label("situation")
    a.b("c605" + _imm(STATE_FLAGS) + "00")          # mov byte [flags], 0   no overtime kickoff will run
    a.jmp_abs(FN_SET_POSSESSION)                    # tail-call the replaced routine
    # ---- sim_reset: replaces `mov [0xA971C4], ebx` (ebx == 0) at every simulator setup
    a.label("sim_reset")
    a.b("891d" + _imm(SIM_SCRATCH_ZEROED))          # mov [0xA971C4], ebx
    a.b("c605" + _imm(STATE_SIM_TIES) + "00")       # mov byte [sim ties], 0
    a.b("c3")
    # ---- sim_roll: replaces `mov ecx, 0x28 ; div ecx` (only reached when ties are allowed)
    a.label("sim_roll")
    a.b("c605" + _imm(STATE_SIM_TIES) + "01")       # mov byte [sim ties], 1
    a.b("b928000000")                               # mov ecx, 0x28
    a.b("f7f1")                                     # div ecx
    a.b("c3")
    # ---- sim_tie: replaces `mov eax, [0xA971D4] ; test eax, eax` in the period-advance routine
    a.label("sim_tie")
    a.b("0fb605" + _imm(STATE_SIM_TIES))            # movzx eax, byte [sim ties]
    a.b("85c0")                                     # test eax, eax
    a.b("c3")
    # ---- sim_period: replaces `mov [0xA971F8], 1.0` in the simulator's period-kickoff handler
    #      The site sits between `cmp eax, ecx` (0x1071FA) and its consumer, so the flags are kept.
    a.label("sim_period")
    a.b("9c")                                       # pushfd
    a.b("c705" + _imm(SIM_CLOCK_FRACTION) + "0000803f")   # mov dword [fraction], 1.0
    a.b("833d" + _imm(SIM_PERIOD_INDEX) + "04")     # cmp dword [period index], 4
    a.j8("7c", "sp_done")
    a.b("803d" + _imm(STATE_SIM_TIES) + "01")       # regular season (ties allowed)?
    a.j8("75", "sp_done")
    a.b("50")
    a.b("a1" + _imm(SCALE_VA))                      # mov eax, [scale]
    a.b("a3" + _imm(SIM_CLOCK_FRACTION))            # mov [fraction], eax
    a.b("58")
    a.label("sp_done")
    a.b("9d")                                       # popfd
    a.b("c3")
    a.label("end")
    code = a.assemble()
    return code, {name: base + off for name, off in a.labels.items()}


def main_cave_bytes(regular_minutes: float = 10) -> bytes:
    code, _labels = _main_code(MAIN_CODE_VA)
    body = _f32(scale_for(regular_minutes)) + code
    _require(len(body) <= MAIN_CAVE_SIZE, f"main overtime cave is {len(body)} bytes, over {MAIN_CAVE_SIZE}")
    return body + b"\xcc" * (MAIN_CAVE_SIZE - len(body))


def aux_cave_bytes() -> bytes:
    labels = cave_labels()
    code, _labels = _aux_code(AUX_CAVE_VA, labels["flag_team"])
    _require(len(code) <= AUX_CAVE_SIZE, f"aux overtime cave is {len(code)} bytes, over {AUX_CAVE_SIZE}")
    return code + b"\xcc" * (AUX_CAVE_SIZE - len(code))


def cave_labels() -> dict[str, int]:
    _code, main = _main_code(MAIN_CODE_VA)
    _code2, aux = _aux_code(AUX_CAVE_VA, main["flag_team"])
    labels = {name: va for name, va in main.items() if name != "end"}
    labels["main_end"] = main["end"]
    labels.update({name: va for name, va in aux.items() if name != "end"})
    labels["aux_end"] = aux["end"]
    return labels


def _rel32_call(site: int, target: int) -> bytes:
    return b"\xe8" + struct.pack("<i", target - (site + 5))


def _rel8(opcode: int, site: int, target: int) -> bytes:
    rel = target - (site + 2)
    _require(-128 <= rel <= 127, "rel8 out of range")
    return bytes([opcode]) + struct.pack("<b", rel)


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise OvertimeError(f"VA 0x{va:x} is in no section")


def _sites(payload: bytes, regular_minutes: float, both_possessions: bool, postseason_no_ties: bool,
           sim_engine: bool) -> list[tuple[str, str, int, bytes, bytes]]:
    """(group, label, file offset, retail bytes, patched bytes) for every site."""

    labels = cave_labels()
    pred = (_rel32_call(PRED_SITE_VA, labels["ot_check"])
            + _rel8(0x74, PRED_SITE_VA + 5, PRED_GAME_OVER_VA)          # je game over
            + bytes.fromhex("83f804")                                   # cmp eax, 4
            + _rel8(0x75, PRED_SITE_VA + 10, PRED_CONTINUE_VA))         # jne continue
    pred += b"\x90" * (len(RETAIL_PRED) - len(pred))
    expiry = _rel32_call(EXPIRY_SITE_VA, labels["ot_expiry"]) + _rel8(0x75, EXPIRY_SITE_VA + 5, EXPIRY_DIFFER_VA)
    expiry += b"\x90" * (len(RETAIL_EXPIRY) - len(expiry))
    expiry2 = _rel32_call(EXPIRY2_SITE_VA, labels["ot_expiry"]) + _rel8(0x75, EXPIRY2_SITE_VA + 5, EXPIRY2_DIFFER_VA)
    expiry2 += b"\x90" * (len(RETAIL_EXPIRY2) - len(expiry2))
    sim_tie = _rel32_call(SIM_TIE_SITE_VA, labels["sim_tie"]) + _rel8(0x75, SIM_TIE_SITE_VA + 5, SIM_TIE_CONTINUE_VA)
    sim_tie += b"\x90" * (len(RETAIL_SIM_TIE) - len(sim_tie))
    sites: list[tuple[str, str, int, bytes, bytes]] = [
        ("core", "main_cave", _offset(payload, MAIN_CAVE_VA), RETAIL_MAIN_CAVE, main_cave_bytes(regular_minutes)),
        ("core", "aux_cave", _offset(payload, AUX_CAVE_VA), RETAIL_AUX_CAVE, aux_cave_bytes()),
        ("core", "init_hook", _offset(payload, INIT_SITE_VA), RETAIL_INIT,
         _rel32_call(INIT_SITE_VA, labels["init"]) + b"\x90"),
        ("core", "ot_kickoff_hook", _offset(payload, OT_KICKOFF_SITE_VA), RETAIL_OT_KICKOFF,
         _rel32_call(OT_KICKOFF_SITE_VA, labels["ot_kickoff"])),
        ("core", "situation_hook", _offset(payload, SITUATION_SITE_VA), RETAIL_SITUATION,
         _rel32_call(SITUATION_SITE_VA, labels["situation"])),
        ("possession", "sudden_death_hook", _offset(payload, PRED_SITE_VA), RETAIL_PRED, pred),
        ("possession", "kickoff_hook", _offset(payload, KICKOFF_SITE_VA), RETAIL_KICKOFF,
         _rel32_call(KICKOFF_SITE_VA, labels["kickoff_flag"])),
        ("postseason", "expiry_hook", _offset(payload, EXPIRY_SITE_VA), RETAIL_EXPIRY, expiry),
        ("postseason", "expiry_restart_hook", _offset(payload, EXPIRY2_SITE_VA), RETAIL_EXPIRY2, expiry2),
        ("sim", "sim_reset_hook", _offset(payload, SIM_RESET_SITE_VA), RETAIL_SIM_RESET,
         _rel32_call(SIM_RESET_SITE_VA, labels["sim_reset"]) + b"\x90"),
        ("sim", "sim_roll_hook", _offset(payload, SIM_ROLL_SITE_VA), RETAIL_SIM_ROLL,
         _rel32_call(SIM_ROLL_SITE_VA, labels["sim_roll"]) + b"\x90\x90"),
        ("sim", "sim_tie_hook", _offset(payload, SIM_TIE_SITE_VA), RETAIL_SIM_TIE, sim_tie),
        ("sim", "sim_period_hook", _offset(payload, SIM_PERIOD_SITE_VA), RETAIL_SIM_PERIOD,
         _rel32_call(SIM_PERIOD_SITE_VA, labels["sim_period"]) + b"\x90" * 5),
    ]
    wanted = {"core": True, "possession": both_possessions, "postseason": postseason_no_ties, "sim": sim_engine}
    return [(g, label, off, before, after if wanted[g] else before) for g, label, off, before, after in sites]


def _site_state(payload: bytes, label: str, off: int, before: bytes, after: bytes) -> str:
    got = payload[off: off + len(before)]
    if got == before:
        return "retail"
    if label == "main_cave":
        return "applied" if got[4:] == after[4:] else "foreign"   # the scale float varies
    return "applied" if got == after else "foreign"


def _group_states(payload: bytes) -> dict[str, set[str]]:
    states: dict[str, set[str]] = {g: set() for g in GROUPS}
    for group, label, off, before, after in _sites(payload, 10, True, True, True):
        states[group].add(_site_state(payload, label, off, before, after))
    return states


def status(payload: bytes) -> str:
    """'retail', 'applied' (any settings), or 'foreign' (bytes match neither; refuse to touch).

    The core group decides; each optional group must be wholly retail or wholly applied.
    """

    try:
        states = _group_states(payload)
    except (OvertimeError, ValueError, struct.error):
        return "foreign"
    if all(states[g] == {"retail"} for g in GROUPS):
        return "retail"
    if states["core"] == {"applied"} and all(states[g] in ({"retail"}, {"applied"}) for g in GROUPS[1:]):
        return "applied"
    return "foreign"


def read_settings(payload: bytes) -> dict[str, object]:
    """The overtime rules currently encoded (retail values when the patch is not applied)."""

    state = status(payload)
    if state != "applied":
        return {"status": state, "regular_minutes": RETAIL_REGULAR_MINUTES, "both_possessions": False,
                "postseason_no_ties": False, "sim_engine": False}
    scale = struct.unpack_from("<f", payload, _offset(payload, SCALE_VA))[0]
    states = _group_states(payload)
    return {"status": state, "regular_minutes": round(scale * NFL_QUARTER_MINUTES, 3),
            "both_possessions": states["possession"] == {"applied"},
            "postseason_no_ties": states["postseason"] == {"applied"},
            "sim_engine": states["sim"] == {"applied"}}


def apply(payload: bytes, regular_minutes: float = 10, both_possessions: bool = True,
          postseason_no_ties: bool = True, sim_engine: bool = True) -> tuple[bytes, Mapping[str, object]]:
    """Return the patched XBE bytes plus a receipt; refuses anything but retail sites."""

    minutes = _validate_minutes(regular_minutes)
    state = status(payload)
    _require(state == "retail", f"overtime sites are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched: set[int] = set()
    edits = []
    for group, label, off, before, after in _sites(payload, minutes, both_possessions, postseason_no_ties, sim_engine):
        if after == before:
            continue
        buf[off: off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        big = label.endswith("_cave")
        edits.append({"group": group, "label": label, "file_offset": f"0x{off:x}", "bytes": len(after),
                      "before": f"<{len(before)} retail bytes>" if big else before.hex(),
                      "after": f"<{len(after)} bytes>" if big else after.hex()})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied", "post-apply verification failed")
    back = read_settings(patched)
    _require(back["regular_minutes"] == minutes and back["both_possessions"] == both_possessions
             and back["postseason_no_ties"] == postseason_no_ties and back["sim_engine"] == sim_engine,
             "post-apply read-back failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    main_code, _m = _main_code(MAIN_CODE_VA)
    aux_code, _a = _aux_code(AUX_CAVE_VA, cave_labels()["flag_team"])
    return patched, {
        "edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched),
        "regular_minutes": minutes, "scale": scale_for(minutes),
        "both_possessions": both_possessions, "postseason_no_ties": postseason_no_ties, "sim_engine": sim_engine,
        "overtime_clock_by_quarter_length": {q: overtime_clock_seconds(q, minutes) for q in (5, 8, 10, 12, 15)},
        "main_cave_va": f"0x{MAIN_CAVE_VA:x}", "main_cave_code_bytes": len(main_code),
        "aux_cave_va": f"0x{AUX_CAVE_VA:x}", "aux_cave_code_bytes": len(aux_code),
        "state_global": f"0x{STATE_GLOBAL:x}",
        "cave_labels": {name: f"0x{va:x}" for name, va in cave_labels().items()},
    }


__all__ = ["OvertimeError", "MAIN_CAVE_VA", "MAIN_CAVE_SIZE", "AUX_CAVE_VA", "AUX_CAVE_SIZE", "RETAIL_MAIN_CAVE",
           "RETAIL_AUX_CAVE", "STATE_GLOBAL", "INIT_SITE_VA", "OT_KICKOFF_SITE_VA", "KICKOFF_SITE_VA", "PRED_SITE_VA",
           "SITUATION_SITE_VA", "RETAIL_SITUATION", "FN_KICK_SETUP", "FN_SET_POSSESSION", "FLAG_POSSESSED", "FLAG_PENDING",
           "EXPIRY_SITE_VA", "EXPIRY2_SITE_VA", "SIM_RESET_SITE_VA", "SIM_ROLL_SITE_VA", "SIM_TIE_SITE_VA",
           "SIM_PERIOD_SITE_VA", "RETAIL_INIT", "RETAIL_OT_KICKOFF", "RETAIL_KICKOFF", "RETAIL_PRED", "RETAIL_EXPIRY",
           "RETAIL_EXPIRY2", "RETAIL_SIM_RESET", "RETAIL_SIM_ROLL", "RETAIL_SIM_TIE", "RETAIL_SIM_PERIOD", "GROUPS",
           "NO_TIE_MODES", "RETAIL_REGULAR_MINUTES", "apply", "aux_cave_bytes", "cave_labels", "main_cave_bytes",
           "overtime_clock_seconds", "read_settings", "scale_for", "status"]
