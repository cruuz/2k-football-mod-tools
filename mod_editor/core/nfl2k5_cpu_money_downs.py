"""CPU fourth-down and marker preferences. EXPERIMENTAL / UNWITNESSED.

Retail already accounts for distance in category/play selection and target
ranking. This opt-in owner strengthens bounded preferences, preserving
native eligibility, field-goal range, catchability and throw continuations.
Reserve REQUESTS with the complete allocator union before composing owners.

b77 p9 adds the level ``modern2`` (CPU decisions "Modern 2") inside the same owner and 2048-byte allocation: a fourth-down
table taken from published analytics (ESPN Analytics chart and the nfl4th model, see
``docs/mod_editor/nfl2k5_cpu_decisions_modern2_sources.json``), an overtime branch that reads the overtime owner's possession
byte, a late-lead field-goal rule, a sourced two-point chart at 0x206E70, a field-goal guard so a kick the policy forces is
never run as a fake, and defensive lottery exponents 3 -> 2. Levels Modern and Aggressive keep their beta-76.5 bytes.
The VIP-aware revision delegates fourth-down, two-point and field-goal policy
to retail while a matching CPU user VIP is in playback mode. The v0.6.1
Modern 2 template remains recognizable and upgrades within the same allocation.

b778 (beta-78 / pack v0.7) clock revision, still inside the same 2048 bytes: only a user VIP (the native
virtual-controller flag, team +0x38) delegates; automatic 2026 coach profiles clear that flag, so their fourth downs,
two-point tries and late-lead kicks use Modern 2. One 4-byte operand edit in the native timeout predicate 207050 lets a
CPU offense call its timeouts in the last 15 seconds of the first half whenever the game's own time estimate says it
still has a play to run (retail stopped at 15 seconds unless it was already in field goal range). The fourth-down
policy reads only the sign of the native direction value, as native 209CA0 does: a live game stores the end-line z
there (+/-5486.4 cm), and the beta-77.1 test that accepted only +/-1.0 sent every real fourth down back to the retail
chart (seen in the emulator, b778 ai4). The beta-77.1 templates (pre-VIP and VIP-aware) stay recognizable and
upgrade in place.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
from types import SimpleNamespace

from . import nfl2k5_cpu_money_downs_code as assembly
from . import nfl2k5_gameplay_lever as lever
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_cpu_money_downs"
CODE_SIZE = 2048
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
# b778 ai6: the late-game trailing rule lives in its own small late owner (xs1's growable pool in the integrated
# build), so Modern 2 keeps its 2,044 of 2,048 bytes. The companion is requested with the same feature. The companion
# sorts after nfl2k5_coach_ai in LATE_OWNERS, so a build reserves both in one request set; attaching coach_ai to a
# sealed image that already carries the companion would move it, and extend_scaleout must keep refusing that.
LATE_OWNER = "nfl2k5_cpu_money_downs_late"
LATE_CODE_SIZE = 400
LATE_STATE_OWNER = "nfl2k5_cpu_money_downs_late_state"
LATE_STATE_SIZE = 8
LATE_REQUESTS = ((LATE_OWNER, "code", LATE_CODE_SIZE, 16), (LATE_STATE_OWNER, "data", LATE_STATE_SIZE, 4))
LEVELS = ("retail", "modern", "aggressive", "modern2")
BUILD_CAPTION = "CPU fourth downs, two-point tries, overtime (experimental)"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: the CPU uses its original fourth-down "
    "choices, two-point chart and passing preferences. Patch: Modern adds measured fourth-down "
    "attempts and favors supported primary routes and viable targets reaching "
    "the first-down line. Aggressive increases those preferences. Modern 2 adds a wider "
    "fourth-down table from published analytics (ESPN Analytics chart, nfl4th model) that also reads the "
    "score and clock, an overtime branch for the modern both-teams-possess rule, a kick when a late "
    "lead of 1 to 3 faces a long fourth down inside field-goal range, a modern two-point chart, "
    "more varied defensive coverage calls, and end-of-half timeouts for a CPU offense that can still "
    "run a play. Automatic coach profiles follow it too. Catches and conversions are not "
    "guaranteed. Retail is the default in the Basic preset; Advanced and Experimental use Modern 2."
)
HOOKS = {
    "fourth": (0x20B180, bytes.fromhex("a18002e600")),
    "play": (0x20980D, bytes.fromhex("d95de88b45e8")),
    "target": (0x1987B5, bytes.fromhex("d95dfcd945fc")),
}
# b77 p9, level Modern 2: the three hooks above plus the two-point chart (its first call is displaced because the whole chart
# is replaced), the two calls of the field goal test and the two defensive lottery exponents (push 3 -> push 2).
HOOKS2 = {
    **HOOKS,
    "two_point": (0x206E70, bytes.fromhex("e8cbf0ffff")),
    "fg_dispatch": (0x20B1A4, bytes.fromhex("e8d7fdffff")),
    "fg_commit": (0x20B6DD, bytes.fromhex("e89ef8ffff")),
    "exponent_front": (0x20AA1F, b"\x03"),
    "exponent_cover": (0x20AC4E, b"\x03"),
}
# b778: the native CPU timeout predicate 207050, first-half branch: "fcomp [15.0]" at 2071FC..207205 becomes
# "fcomp [0.0]", so the first-half offense always takes the time-estimate test (half clock < estimate) that retail
# applied only above 15 seconds. The estimate (20A4D0) is non-zero only inside about 55 to 65 yards of the goal.
HOOKS3 = {"timeout_window": (0x207202, bytes.fromhex("74694e00"))}
HOOK3_AFTER = {"timeout_window": bytes.fromhex("80414e00")}
M2_VARIANTS = ("b778_late", "b778", "v061", "p9")  # ai6 late rule, ai4 no late owner, beta-77.1, b77 p9
HOOK2_LABEL = {"fourth": "fourth", "play": "play", "target": "target", "two_point": "two_point",
               "fg_dispatch": "fg_guard", "fg_commit": "fg_guard"}
EXPONENT_AFTER = b"\x02"
# Full pinned dependent routines from the USA XBE.
GUARDS = (
    (0x20b180, 340, "2e1863cbb711c990efb15e2d197f2fbd90848d2ec4977fbe2645806106a5fc5c"),
    (0x2096a0, 1526, "e319ca9c5160cef7bb18fadaccc745f52cfc4b132b6d59dfa908daa39269a641"),
    (0x1985e0, 633, "0956171e96f3dcb5f213c209d14459ba9bb9cd9b80bb6ca1a7704ed4cfc25413"),
    (0x209ca0, 831, "3f2d8ea31574e419ac45747e9d4cb139113fffd730615da1fa543037a8a8044a"),
    (0x20af80, 499, "e956a8d796ee1ea0e203edda765bce91c0e1e1ce13e737e5c5919c205dc009fb"),
    (0x205f80, 85, "f13f49dd43be5f9600a610544ea03a4a8871df044aed2e2e23754c05804e6365"),
    (0x209fe0, 593, "b461f207e33bfc9a6a6340a365d57a9b43aa5b385c11e7fddb86ea3c94bcfebc"),
    (0x17fe60, 191, "d668ae407996a71622fe17d443425cb3c5a934717cd041e9b32aa47d7d59b7e4"),
    # b77 p9: routines whose bytes Modern 2 edits (the edits themselves are restored before hashing).
    (0x206e70, 50, "fd736b3810aa270181f6357887a3c391acfdefdf7b7d60b4f4dbb394f4c7bd80"),
    (0x20b670, 421, "808e5f312ea504432b392298dff1db6a6c8e85c51b10448cb66ddd5eb67f425a"),
    (0x20a7f0, 570, "839344edda804dc83f1cf3d19f8bf19b2e9f2f823ef44a29b75938427b30a538"),
    (0x20aa40, 551, "ff89b39078bb4a2d99b30b24d41059b54476ebb5153278aed43f5a01cf904901"),
    (0x0f71e0, 19, "5c08a7153ba0c9a94ddeb94b8a76215462a00393acb1b490c146c15397ef10d5"),
    # b778: the timeout predicate whose 15-second operand the clock revision edits.
    (0x207050, 544, "145d564c5b6b184a9f8caef42314b5f1c355d22e787a22daa53724e3f6661f6b"),
)
FIELD_BANDS = ((0, 20), (20, 40), (40, 60), (60, 80), (80, 95), (95, 100))
GO_LIMITS = {"modern": (0, 1, 2, 3, 2, 2), "aggressive": (0, 2, 3, 5, 3, 3)}
SOURCES_FILE = "docs/mod_editor/nfl2k5_cpu_decisions_modern2_sources.json"
# Modern 2 decision classes (the tables live in the generated code blob, from SOURCES_FILE).
CLOCK_CLASSES = ((1800, 0), (900, 1), (600, 2), (300, 3), (120, 4))     # game seconds above this bound -> class
MARGIN_CLASSES = ((-9, 0), (-4, 1), (-1, 2), (0, 3), (3, 4), (8, 5))     # margin up to this bound -> class


def _level(value):
    if value not in LEVELS:
        raise ValueError(f"CPU money downs level must be one of {LEVELS}")
    return value


def _f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _m2(variant="b778"):
    """(code, relocations, labels) of a Modern 2 template variant."""
    if variant not in M2_VARIANTS:
        raise ValueError(f"Unknown Modern 2 variant {variant!r}")
    suffix = {"b778_late": "2_LATE", "b778": "2", "v061": "2_V061", "p9": "2_LEGACY"}[variant]
    return (getattr(assembly, "CODE" + suffix), getattr(assembly, "RELOCATIONS" + suffix),
            getattr(assembly, "LABELS" + suffix))


def m2_tables():
    """(limit_x[81], shift[126], thr10[33]) exactly as the Modern 2 machine code reads them."""
    code, _, labels = _m2()
    limit = tuple(code[labels["limit_x"]:labels["limit_x"] + 81])
    shift = tuple(b - 256 if b > 127 else b for b in code[labels["shift"]:labels["shift"] + 126])
    thr = tuple(code[labels["thr"]:labels["thr"] + 33])
    return limit, shift, thr


def _ot_state(ot_bits, home):
    """'none' (no possession tracking), 'unrecorded', 'first' (opponent has not possessed) or 'both'."""
    bits = ot_bits & 3
    if not bits:
        return "none"
    own = 1 if home else 2
    if not bits & own:
        return "unrecorded"
    return "both" if bits == 3 else "first"


def _game_seconds(quarter, seconds, quarter_seconds):
    """Game seconds left from the quarter clock: native 205F80 adds one quarter in periods 1 and 3 (half clock), and the
    first half counts both second-half quarters (floats as the machine code adds them)."""
    half = _f32(seconds + quarter_seconds) if quarter in (1, 3) else _f32(seconds)
    return _f32(_f32(half + quarter_seconds) + quarter_seconds) if quarter <= 2 else half


def _decision_modern2(down, own_yard, distance, score_margin, quarter, seconds, quarter_seconds, ot_bits, home,
                      kick_range, native_fg, hail_mary, timeouts=0, defense_points=None, punt_roll=None):
    result = _decision_modern2_core(down, own_yard, distance, score_margin, quarter, seconds, quarter_seconds, ot_bits, home,
                                    kick_range, native_fg, timeouts, defense_points, punt_roll)
    return "retail" if result == "go" and hail_mary else result      # the native Hail Mary call stays in charge


def _decision_modern2_core(down, own_yard, distance, score_margin, quarter, seconds, quarter_seconds, ot_bits, home,
                           kick_range, native_fg, timeouts=0, defense_points=None, punt_roll=None):
    limit_x, shift, _ = m2_tables()
    xi = math.floor(_f32(_f32(100 - own_yard) + _f32(.0001)))
    region = 0 if xi > 60 else 1 if xi > 40 else 2
    base = limit_x[xi] if xi <= 80 else 0
    if quarter >= 5:
        state = _ot_state(ot_bits, home)
        if state in ("none", "unrecorded"):
            return "retail"
        if state == "both":
            if score_margin >= 0:
                return "retail"              # sudden death or leading: retail
            if score_margin <= -4:
                return "go"                  # last possession, a field goal cannot save it
            return "retail" if native_fg else "go"
        return "go" if distance <= base + _f32(.0001) else "retail"
    if quarter == 2 and seconds <= 120:
        return "retail"
    if quarter == 4 and seconds <= 120 and score_margin < 0:
        # b778 ai6: trailing in the last two minutes. A field goal only ties or takes the lead; a punt needs all
        # three timeouts, more than 1:30, a defense that held the opponent to 7 or fewer second-half points, and a
        # one-in-three state hash. Everything else (4th-and-27 included) goes.
        if score_margin >= -3 and kick_range is not None and togo_in_range(own_yard, kick_range):
            return "fg"
        if (timeouts == 3 and seconds > 90 and defense_points is not None and defense_points <= 7 and
                punt_roll is not None and punt_roll < 1/3):
            return "punt"
        return "go"
    game = _game_seconds(quarter, seconds, quarter_seconds)
    clock = next((c for bound, c in CLOCK_CLASSES if game > bound), 5)
    margin = next((c for bound, c in MARGIN_CLASSES if score_margin <= bound), 6)
    limit = base + shift[(clock * 7 + margin) * 3 + region]
    if distance <= limit + _f32(.0001):
        return "go"
    if (quarter == 4 and seconds <= 120 and 1 <= score_margin <= 3 and distance >= _f32(6.9999) and
            kick_range is not None and togo_in_range(own_yard, kick_range)):
        return "fg"
    return "retail"


def togo_in_range(own_yard, kick_range):
    """Yards to goal <= kicker range - 5 yards (the late-lead field goal rule's range test)."""
    return _f32(100 - own_yard) <= _f32(kick_range) - 5 + _f32(0.0001)   # inclusive, same 0.0001 yard tolerance as the template


def decision(*, level="modern", down=4, own_yard=50, distance=2,
             score_margin=0, quarter=2, seconds=600, cpu=True, phase=4,
             quarter_seconds=0.0, ot_bits=0, home=False, kick_range=None, native_fg=False, hail_mary=False,
             vip_playback=False, timeouts=0, defense_points=None, punt_roll=None):
    """Reviewable policy: 'go' or 'retail' (delegate punt/FG/go to the game); level modern2 also returns 'fg'.

    Seconds means remaining time in this half, matching native 205F80 (Modern 2: the quarter clock, to which the half
    clock adds one quarter in periods 1 and 3).
    Own yard is measured from the offense's own goal, in either direction.
    Modern 2 extras: ``quarter_seconds`` is the period length (E602B0), ``ot_bits`` the overtime owner's byte E602A8,
    ``home`` whether the offense is the home team object, ``kick_range`` the kicker's 18B120 range in yards and
    ``native_fg`` what the native field goal test (20AF80) answers and ``hail_mary`` what the native Hail Mary test (206DD0)
    answers (a go never overrides it).
    This is a policy oracle, not a port of every retail decision branch.
    """
    _level(level)
    if level == "modern2" and vip_playback:
        return "retail"
    values = (own_yard, distance, seconds)
    if level == "modern2":
        if (not cpu or phase != 4 or down != 4 or quarter not in (1, 2, 3, 4) and quarter < 5 or
                any(isinstance(v, bool) or not isinstance(v, (float, int)) or
                    not math.isfinite(v) for v in values) or
                not isinstance(score_margin, int) or isinstance(score_margin, bool) or
                not 0 <= own_yard <= 100 or not 0 < distance <= 100 or not 0 <= seconds <= 10000):
            return "retail"
        return _decision_modern2(down, own_yard, distance, score_margin, quarter, seconds, quarter_seconds,
                                 ot_bits, home, kick_range, native_fg, hail_mary, timeouts, defense_points, punt_roll)
    if (level == "retail" or not cpu or phase != 4 or down != 4 or
            quarter not in (1, 2, 3, 4) or
            any(isinstance(v, bool) or not isinstance(v, (float, int)) or
                not math.isfinite(v) for v in values) or
            not isinstance(score_margin, int) or isinstance(score_margin, bool) or
            not 0 <= own_yard <= 100 or own_yard + .0001 < 20 or
            not 0 < distance <= 20 or
            not 0 <= seconds <= 10000):
        return "retail"
    if quarter == 2 and seconds <= 30:
        return "retail"
    if quarter == 4 and seconds <= 120 and score_margin >= -3:
        return "retail"
    band = min(5, next((i for i, (_, end) in enumerate(FIELD_BANDS) if own_yard + .0001 < end), 5))
    limit = GO_LIMITS[level][band]
    if quarter == 4 and seconds <= 300:
        if score_margin >= 9:
            limit -= 1
        elif score_margin <= -4 and seconds <= 120:
            limit += 4
        elif score_margin <= -9:
            limit += 2
    return "go" if distance <= limit + .0001 else "retail"


def two_point_decision(*, margin, quarter, seconds, quarter_seconds=0.0, ot_bits=0, home=False):
    """Modern 2 two-point chart (native 206E70): True = go for two. ``margin`` is offense minus defense after the
    touchdown; ``seconds`` is the half clock as native 205F80 reports it."""
    if quarter >= 5:
        return margin == -2 or (margin == -1 and _ot_state(ot_bits, home) == "both")
    if quarter < 1:
        return False
    game = _game_seconds(quarter, seconds, quarter_seconds)
    if not -16 <= margin <= 16:
        return False
    thr = m2_tables()[2][margin + 16]
    if thr == 0:
        return False
    return thr == 255 or game <= thr * 10


def mapping(level="modern"):
    _level(level)
    out = {"level": level, "levels": LEVELS, "field_bands_own_yard": FIELD_BANDS,
           "maximum_distance_yards": GO_LIMITS,
           "play_weight_multiplier": {"retail": 1, "modern": 1.5, "aggressive": 2, "modern2": 1.5}[level],
           "viable_target_bonus": {"retail": 0, "modern": .15, "aggressive": .3, "modern2": .15}[level],
           "presets": {"basic": "retail", "advanced": "modern2", "experimental": "modern2"},
           "runtime_state_bytes": 0,
           "unsupported_routes": "Keep retail weight; explicit first read and straight/lateral grammar required",
           "late_policy": "First-half last 30 seconds and fourth-quarter last 120 seconds when margin >= -3: retail",
           "native_marker_logic": "Already present in retail play and target selection"}
    if level == "modern2":
        limit_x, shift, thr = m2_tables()
        out.update(
            late_policy="Last two minutes of the first half: retail. Fourth-quarter clock and margin shift the go limit (nfl4th)",
            go_limit_by_yards_to_goal_0_to_80=limit_x, go_limit_zero_inside_own_20=True,
            shift_axes="[clock class 0..5][margin class 0..6][region own side/middle/opponent 40 and in]", shift=shift,
            two_point_threshold_seconds_by_margin={m: (None if v == 0 else "always" if v == 255 else v * 10)
                                                   for m, v in zip(range(-16, 17), thr)},
            overtime="Possession byte E602A8: first possession typical table, no early field goal; last possession behind: go",
            late_lead_field_goal="Fourth quarter, <= 120 s, leading by 1 to 3, 7+ yards to go, inside kicker range - 5 yd: kick",
            late_trailing_policy="Fourth quarter, <= 120 s, trailing: go at any distance (4th and 27 included); a field "
                                 "goal only when trailing by 1 to 3 and inside kicker range - 5 yd; a punt only with all "
                                 "three timeouts, more than 1:30 left, the opponent held to 7 or fewer second-half "
                                 "points (live 250DD0 category 7) and a one-in-three state hash (play count + drive index + clock bits)",
            late_helper={"owner": LATE_OWNER, "code_bytes": LATE_CODE_SIZE, "placement": "late owner after every b778 owner"},
            defensive_lottery_exponent={"front": 2, "coverage": 2, "retail": 3},
            vip_policy="Matching CPU user VIP playback (virtual-controller flag set): retail fourth-down/two-point/FG policy, "
                       "with native VIP optional rolls. Automatic coach profiles (flag clear) use Modern 2 (b778)",
            timeout_window="First half: a CPU offense with time left on the native estimate calls its timeouts below 15 s "
                           "too (207050 operand 15.0 -> 0.0, b778)",
            sources=SOURCES_FILE)
    return out


def _resolve(code, relocations, va, symbols):
    code = bytearray(code)
    for offset, kind, symbol, value in relocations:
        target = symbols[symbol] + value + struct.unpack_from("<I", code, offset)[0]
        if kind == 2:
            target -= va + offset
        struct.pack_into("<I", code, offset, target & 0xFFFFFFFF)
    return code


def late_code_for(va, state_va):
    """The late-game helper image at its allocated VA (late owners nfl2k5_cpu_money_downs_late and _late_state)."""
    symbols = {"code": va, "half_time": 0x205F80, "kicker_range": 0x18B120,
               "quarter_points": 0x250DD0, "hail_mary": 0x206DD0, "late_state": state_va}
    code = _resolve(assembly.CODE_LATE, assembly.RELOCATIONS_LATE, va, symbols)
    if len(code) > LATE_CODE_SIZE:
        raise ValueError("late fourth-down helper exceeds its reserved code budget")
    return bytes(code).ljust(LATE_CODE_SIZE, b"\xcc")


def code_for(va, level="modern", *, variant="b778", late_va=None, state_va=None):
    if _level(level) == "retail":
        raise ValueError("Retail has no installed code")
    symbols = {"code": va, "fourth_tail": 0x20B185, "play_tail": 0x209813,
               "target_tail": 0x1987BB, "native_category": 0x209FE0, "half_time": 0x205F80,
               "native_fg": 0x20AF80, "kicker_range": 0x18B120, "margin_fn": 0x205F40, "hail_mary": 0x206DD0,
               "native_vip": 0xF71E0, "two_point_tail": 0x206E75}
    if level == "modern2":
        if variant == "b778_late":
            if late_va is None or state_va is None:
                raise ValueError("the late fourth-down template needs the late owner allocations")
            symbols["late_decision"] = late_va
        code, relocations, _ = _m2(variant)
    else:
        code, relocations = assembly.CODE, assembly.RELOCATIONS
    code = _resolve(code, relocations, va, symbols)
    if level != "modern2":
        struct.pack_into("<I", code, assembly.LABELS["level"], LEVELS.index(level))
    if len(code) > CODE_SIZE:
        raise ValueError("CPU money downs exceeds its reserved code budget")
    return bytes(code).ljust(CODE_SIZE, b"\xcc")


def sites(va, level="modern", *, variant="b778"):
    if level == "modern2":
        labels = _m2(variant)[2]
        rows = []
        for name, (hook, before) in HOOKS2.items():
            if name in HOOK2_LABEL:
                rel = struct.pack("<i", va + labels[HOOK2_LABEL[name]] - hook - 5)
                opcode = b"\xe8" if name.startswith("fg_") else b"\xe9"
                after = opcode + rel + b"\x90" * (len(before) - 5)
            else:
                after = EXPONENT_AFTER
            rows.append((name, hook, before, after))
        if variant in ("b778", "b778_late"):
            rows += [(name, hook, before, HOOK3_AFTER[name]) for name, (hook, before) in HOOKS3.items()]
        return rows
    return [(name, hook, before,
             b"\xe9" + struct.pack("<i", va + assembly.LABELS[name] - hook - 5) +
             b"\x90" * (len(before) - 5)) for name, (hook, before) in HOOKS.items()]


def _neighbors(payload):
    """b76-vb3: the 25th Anniversary kickoff gate enters the pinned diagram reader FUN_0017FE60 through a 7-byte
    trampoline. Restore its retail entry for the hash only after that owner's complete recognizer accepts it."""
    from . import nfl2k5_anniversary_kickoff as anniversary
    from . import nfl2k5_playbook_pair as pair
    from . import nfl2k5_coach_ai as coach_ai
    from . import nfl2k5_cpu_third_down as third_down
    neighbors = []
    va, entry = dict(anniversary.READER_SITES)["reader_diagram"], anniversary.READER_ENTRY
    image = XbeImage(payload)
    if image.read(va, len(entry)) != entry:
        space._require(anniversary.status(payload) == "applied", "Foreign play-call diagram reader neighbor")
        neighbors.append((va, entry))
    # Paired sides intentionally return no VIP; unpaired sides retain the
    # native accessor. Normalize only the complete recognized pair owner.
    _, va, original, _ = next(row for row in pair.HOOKS if row[0] == "vip")
    entry = bytes.fromhex(original)
    if image.read(va, len(entry)) != entry:
        space._require(pair.status(payload) == "applied", "Foreign VIP accessor neighbor")
        neighbors.append((va, entry))
    # Automatic tendencies enter the ordinary CPU publication tail. Accept
    # that selector-boundary hook only when the entire owner is recognized.
    neighbors.extend((va, before) for _, va, before, _ in coach_ai.normalized_sites(payload))
    # b778-ai8: the third-down run weight hook sits in the same play selector (0x2096A0); normalize its five bytes
    # before hashing the function this owner guards.
    neighbors.extend((va, before) for _, va, before, _ in third_down.normalized_sites(payload))
    return tuple(neighbors)


def _adapter(level, *, variant="b778", late_va=None, state_va=None):
    return SimpleNamespace(OWNER=OWNER, CODE_SIZE=CODE_SIZE, REQUESTS=REQUESTS,
                           GUARDS=GUARDS, sites=lambda va: sites(va, level, variant=variant),
                           mapping=lambda: mapping(level),
                           code_for=lambda va: code_for(va, level, variant=variant, late_va=late_va,
                                                        state_va=state_va),
                           neighbors=_neighbors)


def _rows(payload, owner):
    try:
        rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == owner and a["kind"] == "code"]
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return None
    return rows[0] if len(rows) == 1 else None


def _late_row(payload):
    return _rows(payload, LATE_OWNER)


def _late_state_row(payload):
    try:
        rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == LATE_STATE_OWNER]
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return None
    return rows[0] if len(rows) == 1 else None


def _main_row(payload):
    return _rows(payload, OWNER)


def read_settings(payload):
    """Installed level. Modern 2 also names its template: ``vip_policy`` (a user VIP delegates), ``clock_policy``
    (b778: automatic coach profiles use Modern 2, end-of-half timeout window) and ``late_policy`` (ai6: the
    trailing last-two-minutes rule in the companion late owner)."""
    result = []
    for level in ("modern", "aggressive"):
        if lever.status(payload, _adapter(level)) == "applied":
            return {"level": level, "vip_policy": False, "clock_policy": False, "late_policy": False,
                    "experimental": True, "runtime_witnessed": False}
    late, state = _late_row(payload), _late_state_row(payload)
    if late is not None and state is not None and lever.status(
            payload, _adapter("modern2", variant="b778_late", late_va=late["va"],
                              state_va=state["va"])) == "applied":
        return {"level": "modern2", "vip_policy": True, "clock_policy": True, "late_policy": True,
                "variant": "b778_late", "experimental": True, "runtime_witnessed": False}
    if lever.status(payload, _adapter("modern2", variant="b778")) == "applied":
        return {"level": "modern2", "vip_policy": True, "clock_policy": True, "late_policy": False,
                "variant": "b778", "experimental": True, "runtime_witnessed": False}
    for variant, vip in (("v061", True), ("p9", False)):
        if lever.status(payload, _adapter("modern2", variant=variant)) == "applied":
            return {"level": "modern2", "vip_policy": vip, "clock_policy": False, "late_policy": False,
                    "variant": variant, "experimental": True, "runtime_witnessed": False}
    return None


def status(payload):
    main, late, late_state = _main_row(payload), _late_row(payload), _late_state_row(payload)
    if main is None:
        return "foreign" if late is not None else lever.status(payload, _adapter("modern"))
    for level in ("modern", "aggressive"):
        state = lever.status(payload, _adapter(level))
        if state != "foreign":
            return state
    if late is not None and late_state is not None and lever.status(
            payload, _adapter("modern2", variant="b778_late", late_va=late["va"],
                              state_va=late_state["va"])) != "foreign":
        return "applied"
    for variant in ("b778", "v061", "p9"):
        state = lever.status(payload, _adapter("modern2", variant=variant))
        if state != "foreign":
            return state
    return "foreign"


def _install_modern2(payload, *, allocation=None, allow_no_late=False):
    """Install the ai6 Modern 2 template and its late companion inside established allocations.

    ``allow_no_late`` keeps a test-only union without the companion on the ai4 template (late_policy False); a clean
    build reserves the companion and gets the late rule."""
    from . import nfl2k5_rdata_sites as rdata
    main, late, late_state = _main_row(payload), _late_row(payload), _late_state_row(payload)
    space._require(main is not None,
                   "CPU money downs: reserve the complete owner union on a clean base")
    if (late is None or late_state is None) and not allow_no_late:
        space._require(False, "CPU money downs needs its companion allocations "
                              "(nfl2k5_cpu_money_downs_late and _late_state)")
    variant = "b778_late" if late is not None and late_state is not None else "b778"
    late_va = late["va"] if variant == "b778_late" else None
    state_va = late_state["va"] if variant == "b778_late" else None
    installed = payload
    if variant == "b778_late":
        space._require(XbeImage(installed).read(state_va, LATE_STATE_SIZE) == bytes(LATE_STATE_SIZE),
                       "late fourth-down state must be zero at install")
        installed, _ = space.install_code(installed, LATE_OWNER, late_code_for(late_va, state_va))
    installed, _ = space.install_code(installed, OWNER,
                                      code_for(main["va"], "modern2", variant=variant, late_va=late_va,
                                               state_va=state_va))
    result, patch = rdata.apply(installed, sites(main["va"], "modern2", variant=variant), OWNER)
    space._require(status(result) == "applied", "gameplay lever postcondition failed")
    edits = [{"label": label, "va": hex(va), "file_offset": hex(rdata.offset_of(result, va)),
              "before": before.hex(), "after": after.hex()}
             for label, va, before, after in sites(main["va"], "modern2", variant=variant)]
    if variant == "b778_late":
        edits.append({"label": "late_owner", "va": hex(late["va"]),
                      "file_offset": hex(late["raw"]), "size": late["size"]})
        edits.append({"label": "late_state", "va": hex(state_va), "size": LATE_STATE_SIZE})
    edits.append({"label": "immutable_allocation", "va": hex(main["va"]), "file_offset": hex(main["raw"]),
                  "before": (b"\xcc" * CODE_SIZE).hex(),
                  "after": code_for(main["va"], "modern2", variant=variant, late_va=late_va,
                                     state_va=state_va).hex()})
    receipt = {"owner": OWNER, "level": "modern2", "vip_policy": True, "clock_policy": True,
               "late_policy": variant == "b778_late", "variant": variant, "edits": edits,
               "allocation": allocation,
               "reservations": space.reservations(result),
               "sections_repinned": patch["sections_repinned"],
               "changed_bytes": sum(x != y for x, y in zip(payload, result)) + len(result) - len(payload),
               "file_growth": len(result) - len(payload),
               "before_sha256": hashlib.sha256(payload).hexdigest(),
               "after_sha256": hashlib.sha256(result).hexdigest(),
               "experimental": True, "runtime_witnessed": False}
    return result, receipt


def apply(payload, *, level="modern"):
    _level(level)
    if level == "retail":
        if status(payload) != "retail":
            raise ValueError("Rebuild from a verified base to select Retail; mixed/foreign bytes refuse")
        return payload, {"owner": OWNER, "level": "retail", "changed_bytes": 0,
                         "edits": [], "experimental": True, "runtime_witnessed": False}
    if level == "modern2":
        settings = read_settings(payload)
        if settings and settings["level"] == "modern2" and settings.get("late_policy"):
            return payload, {"owner": OWNER, "level": "modern2", "late_policy": True,
                             "already_applied": True, "changed_bytes": 0, "edits": [],
                             "experimental": True, "runtime_witnessed": False}
        if settings is not None:
            if settings["level"] == "modern2":
                return upgrade_to_modern2(payload)
            raise ValueError("CPU money downs: changing Modern or Aggressive to Modern 2 needs a rebuild from a verified base")
        # A clean standalone install reserves both the 2,048-byte Modern 2 code and the late companion. The
        # integrated build also carries the companion (it lands in xs1's growable pool).
        space._require(lever.status(payload, _adapter("modern2", variant="b778")) == "retail",
                       "CPU money downs: foreign or mixed bytes; refusing")
        if space.status(payload) == "retail":
            allocated, allocation_receipt = space.apply(payload, REQUESTS + LATE_REQUESTS, scaleout=True)
            result, receipt = _install_modern2(allocated, allocation=allocation_receipt)
            receipt.update(before_sha256=hashlib.sha256(payload).hexdigest(),
                           file_growth=len(result) - len(payload),
                           changed_bytes=sum(x != y for x, y in zip(payload, result)) + len(result) - len(payload))
            return result, receipt
        # An allocator image without the owner needs a rebuild; never allocate a second request set into a sealed image.
        space._require(_main_row(payload) is not None,
                       "CPU money downs: reserve the complete owner union on a clean base")
        return _install_modern2(payload, allow_no_late=True)
    adapter = _adapter(level)
    # A standalone new owner can still fit the allocator's legacy pages.
    # Explicitly request v3 as required by this owner's integration contract.
    # Validate the complete owner before allocating any bytes.
    if lever.status(payload, adapter) == "retail" and space.status(payload) == "retail":
        allocated, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        result, receipt = lever.apply(allocated, adapter)
        receipt.update(allocation=allocation_receipt,
                       before_sha256=hashlib.sha256(payload).hexdigest(),
                       file_growth=len(result)-len(payload),
                       changed_bytes=sum(x != y for x, y in zip(payload, result)) + len(result)-len(payload))
        return result, receipt
    return lever.apply(payload, adapter)


def upgrade_to_modern2(payload):
    """Native repair core: an XBE that carries the owner at Modern or Aggressive (the beta-76.5 / SOFTDRINK 2K28 v0.5
    bytes), the beta-77.1 VIP-aware template, or the ai4 b778 template becomes the ai6 Modern 2 pair inside the
    owner's own allocation plus the late companion. The companion is appended with extend_scaleout when an installed
    image lacks it (xs1's pool / late placement); an image where that is impossible keeps the ai4 template and
    reports late_policy False. Idempotent; refuses foreign or mixed bytes. Returns (payload, receipt)."""
    from .nfl2k5_bump_strength import _sections, section_digest
    from . import nfl2k5_rdata_sites as rdata
    settings = read_settings(payload)
    if settings is not None and settings["level"] == "modern2" and settings.get("late_policy"):
        return payload, {"owner": OWNER, "level": "modern2", "late_policy": True,
                         "already_applied": True, "changed_bytes": 0, "edits": []}
    old = settings
    space._require(old is not None and old["level"] in ("modern", "aggressive", "modern2"),
                   "CPU money downs: only a verified installed owner upgrades to Modern 2")
    space._require(space.is_scaleout(payload), "CPU money downs upgrade needs the sealed scale-out allocator")
    late, late_state = _late_row(payload), _late_state_row(payload)
    if late is None or late_state is None:
        extend = getattr(space, "extend_scaleout", None)
        if extend is not None:
            try:
                payload, _extended = extend(payload, LATE_REQUESTS)
                late, late_state = _late_row(payload), _late_state_row(payload)
            except ValueError:
                # No room in this sealed image (the test-only union); keep the ai4 template. The integration build
                # reserves the companion in xs1's growable pool, so this path is not used there.
                late = late_state = None
    a = lever.allocation(payload, OWNER, CODE_SIZE)
    requests = space._read_scale_directory(payload)
    variant = old.get("variant", "b778")
    new_variant = "b778_late" if late is not None and late_state is not None else "b778"
    old_sites = {name: (hook, before, after) for name, hook, before, after
                 in sites(a["va"], old["level"], variant=variant)}
    new_sites = sites(a["va"], "modern2", variant=new_variant)
    buf = bytearray(payload)
    late_va = late["va"] if new_variant == "b778_late" else None
    state_va = late_state["va"] if new_variant == "b778_late" else None
    code = code_for(a["va"], "modern2", variant=new_variant, late_va=late_va, state_va=state_va)
    space._require(bytes(buf[a["raw"]:a["raw"] + a["size"]]) ==
                   code_for(a["va"], old["level"], variant=variant), "foreign owner code")
    buf[a["raw"]:a["raw"] + a["size"]] = code
    edits, touched = [], set()
    if new_variant == "b778_late":
        space._require(XbeImage(payload).read(state_va, LATE_STATE_SIZE) == bytes(LATE_STATE_SIZE),
                       "late fourth-down state must be zero at install")
        buf[late["raw"]:late["raw"] + late["size"]] = late_code_for(late_va, state_va)
        edits.append({"label": "late_owner", "va": hex(late["va"]), "file_offset": hex(late["raw"]),
                      "size": late["size"]})
        edits.append({"label": "late_state", "va": hex(state_va), "size": LATE_STATE_SIZE})
        touched.add(next(s.index for s in _sections(payload)
                         if s.raw_offset <= late["raw"] < s.raw_offset + s.raw_size))
    sections = _sections(payload)
    for name, hook, before, after in new_sites:
        off = rdata.offset_of(payload, hook)
        expected = old_sites[name][2] if name in old_sites else before
        space._require(payload[off:off + len(before)] == expected, f"CPU money downs upgrade: foreign bytes at {name}")
        buf[off:off + len(after)] = after
        touched.add(next(s.index for s in sections if s.raw_offset <= off < s.raw_offset + s.raw_size))
        edits.append({"label": name, "va": hex(hook), "file_offset": hex(off), "before": payload[off:off + len(before)].hex(),
                      "after": after.hex()})
    edits.append({"label": "owner_code", "va": hex(a["va"]), "file_offset": hex(a["raw"]), "size": a["size"]})
    space._seal_scaleout(buf, requests)
    for section in sections:
        if section.index in touched:
            buf[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(buf), section)
    result = bytes(buf)
    space._require(status(result) == "applied", "CPU money downs upgrade postcondition failed")
    return result, {"owner": OWNER, "level": "modern2", "vip_policy": True, "clock_policy": True,
                    "late_policy": new_variant == "b778_late", "variant": new_variant,
                    "from_level": old["level"], "from_vip_policy": old["vip_policy"],
                    "from_variant": old.get("variant"), "already_applied": False,
                    "edits": edits, "changed_bytes": sum(x != y for x, y in zip(payload, result)),
                    "before_sha256": hashlib.sha256(payload).hexdigest(), "after_sha256": hashlib.sha256(result).hexdigest(),
                    "sections_repinned": sorted(touched), "experimental": True, "runtime_witnessed": False}


def primary_depth_cm(body, play_index, formation_index, *, mirrored=False):
    """Host counterpart of the conservative native route classifier.

    Only reads a fixed PLAY body. Unsupported or ambiguous routes return None.
    Native tests compare this result after the actual retail loader relocates
    descriptors, including both team buffers and mirrored formation partners.
    """
    from . import nfl2k5_playbook_inspector as book
    if len(body) != book.BODY_SIZE or not 0 <= play_index < 270 or not 0 <= formation_index < 50:
        return None
    play = book.PLAY_BASE + play_index * 96
    flags = struct.unpack_from("<I", body, play + 4)[0]
    if flags & 0x1C0:
        return None

    def chain(slot):
        descriptor = play + 8 + slot * 8
        count, relative = struct.unpack_from("<Ii", body, descriptor)
        count &= 15
        start = descriptor + 3 + relative
        if (count < 2 or start < book.NODE_BASE or (start - book.NODE_BASE) % 8 or
                start + count * 8 > book.NODE_BASE + 3500 * 8 or
                struct.unpack_from("<H", body, start)[0] != 1):
            return None
        return [body[i:i + 8] for i in range(start, start + count * 8, 8)]

    qb = chain(0)
    if not qb or struct.unpack_from("<H", qb[-1])[0] & 0xFBFF != 0x0206:
        return None
    first = qb[-1][4] >> 4
    if not 1 <= first <= 5:
        return None
    slot = first + 5
    route = chain(slot)
    if not route or len(route) not in (2, 3) or route[0][4:] != bytes.fromhex("01034080"):
        return None
    header = lambda node: struct.unpack_from("<H", node)[0] & 0xFBFF
    if header(route[1]) != (0x0212 if len(route) == 2 else 0x0012) or route[1][4] & 31:
        return None
    if len(route) == 3 and (header(route[2]) != 0x0212 or route[2][4] & 31 not in (4, 5)):
        return None
    feet = route[1][7] - 64
    if feet < 0:
        return None
    form = book.FORMATION_BASE + formation_index * 180
    if mirrored and struct.unpack_from("<I", body, form + 4)[0] & 0x100000:
        partner = body[form + 0x1B + slot * 14] >> 4
        if partner != 11:
            if partner > 10:
                return None
            slot = partner
    depth = struct.unpack_from("<h", body, form + 0x22 + slot * 14)[0]
    return depth + feet * 3048 // 100


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--level", choices=LEVELS, default="modern")
    parser.add_argument("--output", type=Path, help="new output file only")
    args = parser.parse_args(argv)
    if args.apply != (args.output is not None):
        parser.error("--apply and --output must be supplied together")
    try:
        with args.xbe.open("rb") as stream:
            payload = stream.read(16 * 1024**2 + 1)
        if len(payload) > 16 * 1024**2:
            raise ValueError("Expected a supported executable, not a disc or archive")
        state = status(payload)
        if state == "foreign":
            raise ValueError("Foreign or mixed CPU money downs bytes")
        if args.apply:
            result, receipt = apply(payload, level=args.level)
            created = False
            try:
                with args.output.open("xb") as stream:
                    created = True
                    stream.write(result)
            except BaseException:
                if created:
                    args.output.unlink(missing_ok=True)
                raise
            print(json.dumps(receipt, indent=2))
        else:
            print(json.dumps({"status": state, "settings": read_settings(payload),
                              "experimental": True, "runtime_witnessed": False,
                              "policy": mapping(args.level)}, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
