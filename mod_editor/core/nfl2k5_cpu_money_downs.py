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
    "and more varied defensive coverage calls. Catches and conversions are not "
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


def m2_tables():
    """(limit_x[81], shift[126], thr10[33]) exactly as the Modern 2 machine code reads them."""
    code, labels = assembly.CODE2, assembly.LABELS2
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
                      kick_range, native_fg, hail_mary):
    result = _decision_modern2_core(down, own_yard, distance, score_margin, quarter, seconds, quarter_seconds, ot_bits, home,
                                    kick_range, native_fg)
    return "retail" if result == "go" and hail_mary else result      # the native Hail Mary call stays in charge


def _decision_modern2_core(down, own_yard, distance, score_margin, quarter, seconds, quarter_seconds, ot_bits, home,
                           kick_range, native_fg):
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
             quarter_seconds=0.0, ot_bits=0, home=False, kick_range=None, native_fg=False, hail_mary=False):
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
    values = (own_yard, distance, seconds)
    if level == "modern2":
        if (not cpu or phase != 4 or down != 4 or quarter not in (1, 2, 3, 4) and quarter < 5 or
                any(isinstance(v, bool) or not isinstance(v, (float, int)) or
                    not math.isfinite(v) for v in values) or
                not isinstance(score_margin, int) or isinstance(score_margin, bool) or
                not 0 <= own_yard <= 100 or not 0 < distance <= 25 or not 0 <= seconds <= 10000):
            return "retail"
        return _decision_modern2(down, own_yard, distance, score_margin, quarter, seconds, quarter_seconds,
                                 ot_bits, home, kick_range, native_fg, hail_mary)
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
            defensive_lottery_exponent={"front": 2, "coverage": 2, "retail": 3},
            sources=SOURCES_FILE)
    return out


def code_for(va, level="modern"):
    if _level(level) == "retail":
        raise ValueError("Retail has no installed code")
    symbols = {"code": va, "fourth_tail": 0x20B185, "play_tail": 0x209813,
               "target_tail": 0x1987BB, "native_category": 0x209FE0, "half_time": 0x205F80,
               "native_fg": 0x20AF80, "kicker_range": 0x18B120, "margin_fn": 0x205F40, "hail_mary": 0x206DD0}
    if level == "modern2":
        code, relocations = bytearray(assembly.CODE2), assembly.RELOCATIONS2
    else:
        code, relocations = bytearray(assembly.CODE), assembly.RELOCATIONS
    for offset, kind, symbol, value in relocations:
        target = symbols[symbol] + value + struct.unpack_from("<I", code, offset)[0]
        if kind == 2:
            target -= va + offset
        struct.pack_into("<I", code, offset, target & 0xFFFFFFFF)
    if level != "modern2":
        struct.pack_into("<I", code, assembly.LABELS["level"], LEVELS.index(level))
    if len(code) > CODE_SIZE:
        raise ValueError("CPU money downs exceeds its reserved code budget")
    return bytes(code).ljust(CODE_SIZE, b"\xcc")


def sites(va, level="modern"):
    if level == "modern2":
        rows = []
        for name, (hook, before) in HOOKS2.items():
            if name in HOOK2_LABEL:
                rel = struct.pack("<i", va + assembly.LABELS2[HOOK2_LABEL[name]] - hook - 5)
                opcode = b"\xe8" if name.startswith("fg_") else b"\xe9"
                after = opcode + rel + b"\x90" * (len(before) - 5)
            else:
                after = EXPONENT_AFTER
            rows.append((name, hook, before, after))
        return rows
    return [(name, hook, before,
             b"\xe9" + struct.pack("<i", va + assembly.LABELS[name] - hook - 5) +
             b"\x90" * (len(before) - 5)) for name, (hook, before) in HOOKS.items()]


def _neighbors(payload):
    """b76-vb3: the 25th Anniversary kickoff gate enters the pinned diagram reader FUN_0017FE60 through a 7-byte
    trampoline. Restore its retail entry for the hash only after that owner's complete recognizer accepts it."""
    from . import nfl2k5_anniversary_kickoff as anniversary
    va, entry = dict(anniversary.READER_SITES)["reader_diagram"], anniversary.READER_ENTRY
    if XbeImage(payload).read(va, len(entry)) == entry:
        return ()
    space._require(anniversary.status(payload) == "applied", "Foreign play-call diagram reader neighbor")
    return ((va, entry),)


def _adapter(level):
    return SimpleNamespace(OWNER=OWNER, CODE_SIZE=CODE_SIZE, REQUESTS=REQUESTS,
                           GUARDS=GUARDS, sites=lambda va: sites(va, level), mapping=lambda: mapping(level),
                           code_for=lambda va: code_for(va, level), neighbors=_neighbors)


def read_settings(payload):
    for level in LEVELS[1:]:
        if lever.status(payload, _adapter(level)) == "applied":
            return {"level": level, "experimental": True, "runtime_witnessed": False}
    return None


def status(payload):
    for level in LEVELS[1:]:
        state = lever.status(payload, _adapter(level))
        if state != "foreign":
            return state
    return "foreign"


def apply(payload, *, level="modern"):
    _level(level)
    if level == "retail":
        if status(payload) != "retail":
            raise ValueError("Rebuild from a verified base to select Retail; mixed/foreign bytes refuse")
        return payload, {"owner": OWNER, "level": "retail", "changed_bytes": 0,
                         "edits": [], "experimental": True, "runtime_witnessed": False}
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
    """b77 p9 native repair core: an XBE that carries the owner at Modern or Aggressive (the beta-76.5 / SOFTDRINK 2K28 v0.5
    bytes) becomes Modern 2 inside the owner's own allocation. Only the owner's 2048 code bytes, the three existing hooks,
    the five new sites, the allocator seals/directory descriptors of the scale-out code region and the .text digest change.
    Idempotent; refuses foreign or mixed bytes. Returns (payload, receipt)."""
    from .nfl2k5_bump_strength import _sections, section_digest
    from . import nfl2k5_rdata_sites as rdata
    if lever.status(payload, _adapter("modern2")) == "applied":
        return payload, {"owner": OWNER, "level": "modern2", "already_applied": True, "changed_bytes": 0, "edits": []}
    old = read_settings(payload)
    space._require(old is not None and old["level"] in ("modern", "aggressive"),
                   "CPU money downs: only an installed Modern or Aggressive owner upgrades to Modern 2")
    space._require(space.is_scaleout(payload), "CPU money downs upgrade needs the sealed scale-out allocator")
    a = lever.allocation(payload, OWNER, CODE_SIZE)
    requests = space._read_scale_directory(payload)
    old_sites = {name: (hook, before, after) for name, hook, before, after in sites(a["va"], old["level"])}
    new_sites = sites(a["va"], "modern2")
    buf = bytearray(payload)
    code = code_for(a["va"], "modern2")
    space._require(bytes(buf[a["raw"]:a["raw"] + a["size"]]) == code_for(a["va"], old["level"]), "foreign owner code")
    buf[a["raw"]:a["raw"] + a["size"]] = code
    edits, touched = [], set()
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
    space._require(lever.status(result, _adapter("modern2")) == "applied" and space.status(result) == "applied",
                   "CPU money downs upgrade postcondition failed")
    return result, {"owner": OWNER, "level": "modern2", "from_level": old["level"], "already_applied": False,
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
