"""CPU fourth-down and marker preferences. EXPERIMENTAL / UNWITNESSED.

Retail already accounts for distance in category/play selection and target
ranking. This opt-in owner strengthens bounded preferences, preserving
native eligibility, field-goal range, catchability and throw continuations.
Reserve REQUESTS with the complete allocator union before composing owners.
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

OWNER = "nfl2k5_cpu_money_downs"
CODE_SIZE = 2048
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
LEVELS = ("retail", "modern", "aggressive")
BUILD_CAPTION = "CPU fourth downs and first downs (experimental)"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: the CPU uses its original fourth-down "
    "choices and passing preferences. Patch: Modern adds measured fourth-down "
    "attempts and favors supported primary routes and viable targets reaching "
    "the first-down line. Aggressive increases those preferences. Late tying "
    "and winning kicks keep retail decisions. Catches and conversions are not "
    "guaranteed. Retail is the default in every preset."
)
HOOKS = {
    "fourth": (0x20B180, bytes.fromhex("a18002e600")),
    "play": (0x20980D, bytes.fromhex("d95de88b45e8")),
    "target": (0x1987B5, bytes.fromhex("d95dfcd945fc")),
}
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
)
FIELD_BANDS = ((0, 20), (20, 40), (40, 60), (60, 80), (80, 95), (95, 100))
GO_LIMITS = {"modern": (0, 1, 2, 3, 2, 2), "aggressive": (0, 2, 3, 5, 3, 3)}


def _level(value):
    if value not in LEVELS:
        raise ValueError(f"CPU money downs level must be one of {LEVELS}")
    return value


def decision(*, level="modern", down=4, own_yard=50, distance=2,
             score_margin=0, quarter=2, seconds=600, cpu=True, phase=4):
    """Reviewable policy: 'go' or 'retail' (delegate punt/FG/go to the game).

    Seconds means remaining time in this half, matching native 205F80.
    Own yard is measured from the offense's own goal, in either direction.
    This is a policy oracle, not a port of every retail decision branch.
    """
    _level(level)
    values = (own_yard, distance, seconds)
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


def mapping(level="modern"):
    _level(level)
    return {"level": level, "levels": LEVELS, "field_bands_own_yard": FIELD_BANDS,
            "maximum_distance_yards": GO_LIMITS,
            "play_weight_multiplier": {"retail": 1, "modern": 1.5, "aggressive": 2}[level],
            "viable_target_bonus": {"retail": 0, "modern": .15, "aggressive": .3}[level],
            "presets": dict.fromkeys(("basic", "advanced", "experimental"), "retail"),
            "runtime_state_bytes": 0,
            "unsupported_routes": "Keep retail weight; explicit first read and straight/lateral grammar required",
            "late_policy": "First-half last 30 seconds and fourth-quarter last 120 seconds when margin >= -3: retail",
            "native_marker_logic": "Already present in retail play and target selection"}


def code_for(va, level="modern"):
    if _level(level) == "retail":
        raise ValueError("Retail has no installed code")
    symbols = {"code": va, "fourth_tail": 0x20B185, "play_tail": 0x209813,
               "target_tail": 0x1987BB, "native_category": 0x209FE0, "half_time": 0x205F80}
    code = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", code, offset)[0]
        if kind == 2:
            target -= va + offset
        struct.pack_into("<I", code, offset, target & 0xFFFFFFFF)
    struct.pack_into("<I", code, assembly.LABELS["level"], LEVELS.index(level))
    if len(code) > CODE_SIZE:
        raise ValueError("CPU money downs exceeds its reserved code budget")
    return bytes(code).ljust(CODE_SIZE, b"\xcc")


def sites(va):
    return [(name, hook, before,
             b"\xe9" + struct.pack("<i", va + assembly.LABELS[name] - hook - 5) +
             b"\x90" * (len(before) - 5)) for name, (hook, before) in HOOKS.items()]


def _adapter(level):
    return SimpleNamespace(OWNER=OWNER, CODE_SIZE=CODE_SIZE, REQUESTS=REQUESTS,
                           GUARDS=GUARDS, sites=sites, mapping=lambda: mapping(level),
                           code_for=lambda va: code_for(va, level))


def read_settings(payload):
    for level in LEVELS[1:]:
        if lever.status(payload, _adapter(level)) == "applied":
            return {"level": level, "experimental": True, "runtime_witnessed": False}
    return None


def status(payload):
    first = lever.status(payload, _adapter("modern"))
    if first != "foreign":
        return first
    return lever.status(payload, _adapter("aggressive"))


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
