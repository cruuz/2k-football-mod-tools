"""PROVED OFFLINE mechanisms: moment-specific rules, composed over the modern owners.

Immutable profiles are indexed only when mode is 8 and the selected ordinal is
0..50. Saved displaced instructions preserve the modern owners outside that
domain. Recognizers use a sealed underlying view, never an unverified jump.
DESIGN: graphics, historical contact/replay semantics and lab acceptance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
from functools import lru_cache

from . import nfl2k5_era_rules_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_era_rules"
BUILD_CAPTION = UI_LABEL = "Anniversary rules by season"
CODE_SIZE, DATA_SIZE, RO_SIZE = 2048, 16, 2176
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16),
            (OWNER, "read_only", RO_SIZE, 16))
WRAPPERS, PROFILES, SAVED = 384, 0, 1632
SAVED_STRIDE = 12
PROFILE_COUNT = 51
LEGACY_PROFILE_SHA256 = "db5ee784c18f00af8ba842dc26dac33f863ec537a336fa578f7db22e347075cd"
ROOT = Path(__file__).resolve().parents[2]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def profiles():
    rows = json.loads((ROOT / "data/nfl2k5_era_rules.json").read_text())["mappings"]
    require(len(rows) == PROFILE_COUNT and [r["row"] for r in rows] == list(range(1, PROFILE_COUNT + 1)), "era profile ordinal table")
    out = bytearray()
    kinds = {"none": 0, "sudden_death": 1, "modified_sudden_death_first_TD_ends": 2, "both_possessions": 3}
    for row in rows:
        flags = sum(bit for key, bit in (("two_point_try", 1), ("defensive_try_return", 2), ("postseason", 4),
                     ("coin_toss_defer", 8), ("incidental_facemask_5_yards", 16), ("kickoff_fair_catch_to_25", 32))
                    if row[key])
        spot = lambda yard: (50 - yard) * 91.44
        out.extend(struct.pack("<5fHBBII", spot(row["kickoff_yard"]), -spot(row["kickoff_yard"]),
                   spot(row["free_kick_touchback_yard"]), spot(row["pat_kick_snap_yard"]),
                   row["overtime_minutes"] * 60, row["season"], flags, kinds[row["overtime"]],
                   row["row"], row.get("super_bowl_number", 0)))
    return bytes(out)


def specs():
    """name, VA, span, dispatch. Every span ends on an instruction boundary."""
    from . import nfl2k5_kick_rules as kr, nfl2k5_overtime as ot
    from . import nfl2k5_coin_defer as coin, nfl2k5_decided_clock as clock
    rows = [(name, va, 6, "fmul_" + kind) for name, va, _const, kind in kr.KICKOFF_SITES]
    rows += [("touchback", kr.TOUCHBACK_SITE_VA, 6, "touchback"),
             ("pat_record", kr.TRY_RECORD_SITE_VA, 6, "fmul_pat"),
             ("pat_store", kr.PAT_STORE_SITE_VA, 5, "pat_store"),
             ("pat_pick", kr.PAT_PICK_SITE_VA, 5, "pat_pick"),
             ("pat_audible", kr.PAT_AUDIBLE_SITE_VA, 5, "pat_audible"),
             ("pat_lineup", kr.PAT_LINEUP_ENTRY_VA, 5, "pat_lineup"),
             ("ot_pred", ot.PRED_SITE_VA, 5, "ot_pred"),
             ("ot_clock", ot.OT_KICKOFF_SITE_VA, 5, "ot_clock"),
             ("ot_init", ot.INIT_SITE_VA, 6, "ot_init"),
             ("ot_expiry", ot.EXPIRY_SITE_VA, 5, "ot_expiry"),
             ("ot_expiry2", ot.EXPIRY2_SITE_VA, 5, "ot_expiry"),
             ("regular_tie", 0xB8ADF, 9, "regular_tie"),
             ("no_ot", 0xB8AB0, 7, "no_ot"),
             ("try_points", 0xB8487, 6, "try_points"),
             ("try_ai", 0x208470, 6, "try_ai"),
             ("fair_catch", 0xB6989, 5, "fair_catch"),
             ("fair_spot", 0xB6685, 10, "fair_spot"),
             ("interception", 0xB9B9A, 12, "def_interception"),
             ("recovery", 0xB9E37, 12, "def_recovery"),
             ("blocked_pat", 0xB7B4B, 8, "def_blocked"),
             ("try_descriptor", 0x22EC11, 5, "def_descriptor"),
             ("penalty_finish", 0xB156C, 5, "penalty_finish")]
    rows += [("coin_" + n, va, len(raw), "coin_" + n) for n, va, raw, _op in coin.HOOKS]
    rows += [("clock_" + n, va, len(raw), "clock_" + n) for n, va, raw, _op in clock.HOOKS]
    return rows


def places(payload):
    found = {r["kind"]: r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER}
    if not found:
        return None
    require(set(found) == {"code", "data", "read_only"} and found["code"]["size"] == CODE_SIZE
            and found["data"]["size"] == DATA_SIZE and found["read_only"]["size"] == RO_SIZE, "era rules missing from complete owner union")
    found["coin_state"] = next((r["va"] for r in space.layout(payload)["allocations"]
        if r["owner"] == "nfl2k5_coin_defer" and r["kind"] == "data"), 0)
    return found


def _seal(buffer):
    for s in _sections(buffer):
        buffer[s.header_offset + 36:s.header_offset + 56] = section_digest(buffer, s)
    return bytes(buffer)


def imm(value):
    return struct.pack("<I", value & 0xFFFFFFFF).hex()


JUMPS = {"regular_tie", "no_ot", "try_points", "def_interception", "def_recovery", "def_blocked",
         "try_ai", "fair_catch", "fair_spot", "penalty_finish", "coin_choose", "coin_winner_result", "clock_huddle"}


def code_for(owned, saved, *, profile_data=None, saved_stride=SAVED_STRIDE):
    from . import nfl2k5_overtime as ot, nfl2k5_coin_defer as coin, nfl2k5_kick_rules as kr
    va, state = owned["code"]["va"], owned["data"]["va"]
    symbols = dict(code=va, profiles=owned["read_only"]["va"] + PROFILES, state=state, native_ot_check=ot.cave_labels()["ot_check"])
    core = bytearray(assembly.CODE)
    if profile_data is not None:
        # The sealed v0.4 table used 50 profiles and sixteen-byte displaced slots.
        require(len(profile_data) == 1600 and hashlib.sha256(profile_data).hexdigest() == LEGACY_PROFILE_SHA256,
                "foreign legacy era profiles")
        limit = core.index(bytes.fromhex("83f833")) + 2
        core[limit] = 50
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<i", core, offset)[0]
        if kind == 2:
            target -= va + offset
        struct.pack_into("<I", core, offset, target & 0xFFFFFFFF)
    require(len(core) < WRAPPERS, "era core budget")
    a = _Asm(va + WRAPPERS)
    edits = []
    for ordinal, (name, site, size, dispatch) in enumerate(specs()):
        before = saved[ordinal]
        require(len(before) == size, "era displaced span size")
        a.label(name)
        a.b("9c60")
        a.call(va + assembly.LABELS["profile"])
        # Game init always clears our OT latch, including Quick Game after a moment.
        if dispatch == "ot_init":
            a.b("c705" + imm(state) + "00000000c705" + imm(state + 8) + "00000000")
        if dispatch == "penalty_finish":
            # Restore the candidate's modern yardage before deciding this game's override.
            a.b("c70580a4a800" + struct.pack("<f", 1371.6).hex())
        a.b("85c0")
        a.j32("0f84", name + "_forward")
        if dispatch.startswith("fmul_") or dispatch == "touchback":
            offset = {"fmul_pos": 0, "fmul_neg": 4, "fmul_pat": 12, "touchback": 8}[dispatch]
            if dispatch == "touchback":
                a.b("833db402e60002")
                a.j32("0f85", name + "_scrimmage")
            a.b("d848" + f"{offset:02x}" + "619dc3")
            if dispatch == "touchback":
                a.label(name + "_scrimmage")
                a.b("d80d980f4f00619dc3")
        elif dispatch.startswith("pat_"):
            a.b("66817814df07")  # season >= 2015 uses modern split, including non-kick return to the 2
            a.j32("0f83", name + "_forward")
            a.b("619d")
            if dispatch == "pat_lineup":
                a.b("83c404" + kr.RETAIL_LINEUP_ENTRY.hex())
                a.jmp_abs(kr.LINEUP_RESUME_VA)
            else:
                a.jmp_abs({"pat_store": kr.STORE_TARGET_VA, "pat_pick": kr.PICK_TARGET_VA,
                           "pat_audible": kr.AUDIBLE_TARGET_VA}[dispatch])
        elif dispatch in ("ot_pred", "ot_expiry"):
            helper = "ot_check" if dispatch == "ot_pred" else "ot_expiry"
            a.call(va + assembly.LABELS[helper])
            a.b("85c0")
            a.j32("0f85", name + "_yes")
            a.b("619d")
            if dispatch == "ot_pred":
                a.b("a1c402e600")
            a.b("83fc00c3")
            a.label(name + "_yes")
            a.b("619d")
            if dispatch == "ot_pred":
                a.b("a1c402e600")
            a.b("39c0c3")
        elif dispatch == "ot_clock":
            a.call(va + assembly.LABELS["ot_clock"])
            a.b("619d")
            a.jmp_abs(ot.FN_KICK_SETUP)
        elif dispatch == "regular_tie":
            a.b("f6401604")
            a.j32("0f85", name + "_continue")
            a.b("837c241805")  # saved ECX (period index)
            a.j32("0f85", name + "_continue")
            a.b("619d")
            a.jmp_abs(0xB8B04)
            a.label(name + "_continue")
            a.b("619d")
            a.jmp_abs(0xB8AED)
        elif dispatch == "no_ot":
            a.b("80781700")
            a.j32("0f85", name + "_forward")
            a.b("8b0d28fce5008b118b0d68fce5003b11")
            a.j32("0f85", name + "_forward")
            a.b("619d")
            a.jmp_abs(0xB8B04)
        elif dispatch == "try_ai":
            a.b("f6401601")
            a.j32("0f85", name + "_forward")
            a.b("619d33c0c3")  # prefer the one-point kick; a human can still run/pass for one
        elif dispatch == "fair_catch":
            a.b("8b54241c")  # original EAX is the receiver
            a.call(va + assembly.LABELS["fair_catch"])
        elif dispatch == "fair_spot":
            a.b("833d" + imm(state + 8) + "00")
            a.j32("0f84", name + "_forward")
            a.b("8b15" + imm(state + 4) + "89542418")  # saved ECX, final longitudinal spot
            a.b("c705" + imm(state + 8) + "00000000")
        elif dispatch == "try_points":
            a.b("f6401601")
            a.j32("0f85", name + "_forward")
            a.b("619d8300018b4938")
            a.jmp_abs(site + size)
        elif dispatch.startswith("def_"):
            a.b("f6401602")
            a.j32("0f85", name + "_forward")
            a.b("619d")
            if dispatch == "def_descriptor":
                a.jmp_abs(0x22E050)
            else:
                # Replay the retail conditional rather than the modern unconditional live-ball branch.
                prefix = before[:-2]
                a.b(prefix.hex())
                a.b("7405")
                a.jmp_abs({"def_interception": 0xB9BCD, "def_recovery": 0xB9E61, "def_blocked": 0xB7B5D}[dispatch])
                a.jmp_abs(site + size)
        elif dispatch == "penalty_finish":
            a.b("f6401610")
            a.j32("0f84", name + "_disable")
            a.b("c70580a4a800" + struct.pack("<f", 457.2).hex())
            a.j32("e9", name + "_forward")
            a.label(name + "_disable")
            a.b("c70590a4a80000000000")  # idx 25 runtime enable word
            a.j32("e9", name + "_forward")
        elif dispatch.startswith("coin_"):
            a.b("f6401608")
            a.j32("0f85", name + "_forward")
            if dispatch == "coin_choose" and owned["coin_state"]:
                a.b("c705" + imm(owned["coin_state"]) + "00000000")
            a.b("619d")
            retail = next(raw for n, _at, raw, _ in coin.HOOKS if "coin_" + n == dispatch)
            _replay(a, site, retail, dispatch)
        elif dispatch.startswith("clock_"):
            a.b("619d")
            if dispatch == "clock_huddle":
                a.b("a1b402e600")
                a.jmp_abs(site + size)
            else:
                a.jmp_abs(0x189080)  # native line-up, from the pinned retail call
        elif dispatch != "ot_init":
            raise ValueError(dispatch)
        a.label(name + "_forward")
        a.b("619d")
        _replay(a, site, before, dispatch)
    body = a.assemble()
    require(WRAPPERS + len(body) <= CODE_SIZE, "era wrappers exceed allocation")
    result = bytes(core).ljust(WRAPPERS, b"\xcc") + body
    constants = bytearray(profiles() if profile_data is None else profile_data)
    require(len(constants) == (SAVED if profile_data is None else 1600), "era profile table layout")
    for raw in saved:
        require(len(raw) <= saved_stride, "era displaced instruction budget")
        constants.extend(raw.ljust(saved_stride, b"\0"))
    require(len(constants) <= RO_SIZE, "era saved-site budget")
    for name, site, size, dispatch in specs():
        opcode = b"\xe9" if dispatch in JUMPS else b"\xe8"
        after = (opcode + struct.pack("<i", va + WRAPPERS + a.labels[name] - site - 5)).ljust(size, b"\x90")
        edits.append((site, after))
    return bytes(result).ljust(CODE_SIZE, b"\xcc"), bytes(constants).ljust(RO_SIZE, b"\0"), edits


def _replay(a, site, raw, dispatch):
    if raw[0] in (0xE8, 0xE9):
        a.jmp_abs(site + 5 + struct.unpack_from("<i", raw, 1)[0])
    elif dispatch.startswith("def_") and dispatch != "def_descriptor":
        a.b(raw[:-2].hex())
        target = site + len(raw) + struct.unpack("<b", raw[-1:])[0]
        if raw[-2] == 0x75:
            a.b("7405")
            a.jmp_abs(target)
            a.jmp_abs(site + len(raw))
        else:
            require(raw[-2] == 0xEB, "foreign defensive live branch")
            a.jmp_abs(target)
    elif dispatch == "regular_tie":
        a.b(raw[:7].hex())
        a.b("7405")
        a.jmp_abs(0xB8AED)
        a.jmp_abs(site + len(raw))
    else:
        a.b(raw.hex())
        if dispatch == "penalty_finish":
            return  # the displaced epilogue includes RET
        if dispatch in JUMPS:
            a.jmp_abs(site + len(raw))
        else:
            a.b("c3")


def underlying_view(payload):
    """Inspect an immutable snapshot, including callers' mutable XBE buffers."""
    return _underlying_view(bytes(payload))


@lru_cache(maxsize=2)
def _underlying_view(payload):
    """Restore only verified era-owned sites for the underlying owners' recognizers."""
    # Older owners also accept small synthetic XBE fixtures without an
    # allocator directory. Era requires the scale-out format. Owner names are
    # compressed in that directory, so testing raw ASCII presence is invalid.
    # Each caller still performs its original complete validation.
    if not space.is_scaleout(payload):
        return payload
    owned = places(payload)
    if owned is None:
        return payload
    image = XbeImage(payload)
    body = image.read(owned["code"]["va"], CODE_SIZE)
    constants = image.read(owned["read_only"]["va"], RO_SIZE)
    if body == b"\xcc" * CODE_SIZE:
        require(constants == bytes(RO_SIZE), "foreign dormant era constants")
        return payload
    limit = assembly.CODE.index(bytes.fromhex("83f833")) + 2
    legacy = body[limit] == 50 and hashlib.sha256(constants[:1600]).hexdigest() == LEGACY_PROFILE_SHA256
    saved_at, stride = (1600, 16) if legacy else (SAVED, SAVED_STRIDE)
    saved = [constants[saved_at + i * stride:saved_at + i * stride + size]
             for i, (_n, _va, size, _d) in enumerate(specs())]
    expected, expected_ro, edits = code_for(owned, saved, profile_data=constants[:1600] if legacy else None,
                                            saved_stride=stride)
    require(body == expected and constants == expected_ro, "foreign era rules code, profiles or displaced-site table")
    states = {"underlying" if image.read(site, len(raw)) == raw else
              "applied" if image.read(site, len(after)) == after else "foreign"
              for (site, after), raw in zip(edits, saved)}
    # An underlying owner can in turn normalize its own sites for its dependency.
    # Such a view has no jumps into us. Our own status below still checks every
    # displaced instruction when recognizing a disabled installation.
    if "applied" not in states:
        return payload
    require(states == {"applied"}, "mixed or foreign era rules hooks")
    out = bytearray(payload)
    for (site, _after), raw in zip(edits, saved):
        at = image.offset(site, len(raw))
        out[at:at + len(raw)] = raw
    return _seal(out)


def _money_downs_two_point(payload):
    """b77-i2: CPU money downs at Modern 2 (b77 p9) replaces the first call of the CPU two-point chart at 0x206E70 with a
    5-byte call into its own code. Era rules depend on that chart only through try_ai (0x208470), which forwards to it in
    eras whose flags allow a two-point try and returns the one-point kick otherwise; the chart is then the owner's sourced
    Modern 2 chart. That one site is restored to retail before the dependency guard is hashed, and only while the complete
    money-downs owner validates as applied at Modern 2. Any other change in the guard still reads foreign."""
    from . import nfl2k5_cpu_money_downs as money_downs
    try:
        if money_downs.status(payload) != "applied" or (money_downs.read_settings(payload) or {}).get("level") != "modern2":
            return ()
    except (ValueError, KeyError, IndexError, TypeError, struct.error):
        return ()
    va, retail = money_downs.HOOKS2["two_point"]
    if XbeImage(payload).read(va, len(retail)) == retail:
        return ()
    return ((va, retail),)


def _prerequisites(payload):
    from . import nfl2k5_anniversary_kickoff as gate, nfl2k5_kick_rules as kr, nfl2k5_overtime as ot
    from . import nfl2k5_defensive_try as dt, nfl2k5_coin_defer as coin, nfl2k5_decided_clock as clock
    for module in (gate, kr, ot, dt):
        require(module.status(payload) == "applied", f"era rules require installed {module.__name__}")
    settings = ot.read_settings(payload)
    require(settings["both_possessions"] and settings["postseason_no_ties"], "era OT requires complete modern OT base")
    for module in (coin, clock):
        require(module.status(payload) in ("applied", "retail"), "foreign optional era neighbor")
    image = XbeImage(payload)
    manifest = json.loads((ROOT / "data/nfl2k5_era_rules.json").read_text())
    pins = manifest["retail_sites"]
    tolerated = _money_downs_two_point(payload)
    for guard in manifest["retail_guards"]:
        raw = bytearray(image.read(guard["va"], guard["size"]))
        for va, retail in tolerated:
            if guard["va"] <= va and va + len(retail) <= guard["va"] + guard["size"]:
                raw[va - guard["va"]:va - guard["va"] + len(retail)] = retail
        require(hashlib.sha256(raw).hexdigest() == guard["sha256"],
                "foreign era dependency at " + hex(guard["va"]))
    for name, site, size, dispatch in specs():
        if dispatch in ("regular_tie", "no_ot", "try_points", "try_ai", "fair_catch", "fair_spot", "penalty_finish"):
            require(image.read(site, size).hex() == pins[name], "foreign era live site " + name)
        if dispatch in ("def_interception", "def_recovery", "def_blocked"):
            expected = bytearray.fromhex(pins[name]); expected[-2] = 0xEB
            require(image.read(site, size) == expected, "foreign era defensive site " + name)


def status(payload):
    try:
        base = underlying_view(payload)
        if base == payload:
            owned = places(payload)
            if owned:
                image = XbeImage(payload)
                body = image.read(owned["code"]["va"], CODE_SIZE)
                if body != b"\xcc" * CODE_SIZE:
                    for i, (_name, site, size, _dispatch) in enumerate(specs()):
                        require(image.read(site, size) == image.read(owned["read_only"]["va"] + SAVED + i * SAVED_STRIDE, size),
                                "foreign disabled era hook")
            return "retail"
        _prerequisites(base)
        return "applied"
    except (ValueError, KeyError, IndexError, TypeError, struct.error):
        return "foreign"


def apply(payload, *, enabled=True):
    before = status(payload)
    require(before != "foreign", "foreign era rules installation")
    if not enabled:
        result = underlying_view(payload)
        return result, dict(status="retail", owner=OWNER)
    if before == "applied":
        image = XbeImage(payload)
        owned = places(payload)
        if image.read(owned["read_only"]["va"], SAVED) == profiles():
            return payload, dict(status="already_applied", owner=OWNER, changed_bytes=0)
        # Restore only validated era sites, then install the expanded table in the same allocation.
        payload = underlying_view(payload)
        clear = bytearray(payload)
        for kind, padding in (("code", b"\xcc"), ("read_only", b"\0")):
            region = owned[kind]
            clear[region["raw"]:region["raw"] + region["size"]] = padding * region["size"]
        space._seal_scaleout(clear, space._read_scale_directory(payload))
        payload = _seal(clear)
    _prerequisites(payload)
    owned = places(payload)
    require(owned is not None, "reserve era rules in the complete owner union")
    image = XbeImage(payload)
    saved = [image.read(site, size) for _name, site, size, _kind in specs()]
    body, constants, edits = code_for(owned, saved)
    result, _ = space.install_code(payload, OWNER, body)
    result, _ = space.install_read_only(result, OWNER, constants)
    buffer = bytearray(result)
    for site, raw in edits:
        at = image.offset(site, len(raw))
        buffer[at:at + len(raw)] = raw
    result = _seal(buffer)
    require(status(result) == "applied", "era rules postcondition")
    return result, dict(status="applied", owner=OWNER, classification="PROVED OFFLINE", profiles=PROFILE_COUNT,
                        hooks=len(edits), changed_bytes=sum(a != b for a, b in zip(payload, result)), profile_sha256=hashlib.sha256(profiles()).hexdigest(), runtime_witnessed=False)


def routing_info(payload):
    """DESIGN: stable metadata for the later field/uniform routing owner; no art writes."""
    owned = places(payload)
    require(owned is not None and status(payload) == "applied", "era routing is not installed")
    return dict(mode_va=0xE5FF80, required_mode=8, ordinal_va=0xBF1858, count=PROFILE_COUNT,
                profiles_va=owned["read_only"]["va"] + PROFILES, stride=32,
                season_offset=20, season_bytes=2, super_bowl_offset=28, super_bowl_bytes=4)
