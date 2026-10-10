#!/usr/bin/env python3
"""Offline FRZ selection checks on pinned disc bytes. Never runs the game.

The native selector fixture supplies player ratings, lineup results, kicker
range, clock urgency and tendency history. It does not model a captured demo
RAM state, resource threads, GPU execution or the entire post-play transition.
"""
from __future__ import annotations

import argparse
from collections import Counter
import itertools
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from tools.b77 import frz_xbe_bisect as bisect
from tools.b77.p9_harness import Fixture
from tools.b77.a4_bins_probe import Probe
from mod_editor.core import nfl2k5_play_scoring as s
from mod_editor.core import nfl2k5_playbook_inspector as ip
from mod_editor.core import nfl2k5_stock_books as stock
from mod_editor.core import nfl2k5_moment_gun_weight as gun
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
from mod_editor.core.nfl2k5_playbook_pack import TEAM_BOOKS
from pb.v2 import selection_model as model

MODES = (*range(16), 255, 0xffffffff)
KEYS = tuple(key for key in BOOK_ENTRIES if key in TEAM_BOOKS)


def save(path, result):
    path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def extract(v05, safe, out):
    receipt = {}
    for version, path, expected in (("v05", v05, bisect.V05_HASH), ("v06", safe, bisect.V06_HASH)):
        directory = out / version
        directory.mkdir(parents=True, exist_ok=True)
        raw, offset = bisect.read_xbe(path)
        bisect.require(bisect.sha(raw) == expected, "unexpected executable")
        bisect.write_new(directory / "default.xbe", raw)
        rows = {"default.xbe": dict(sha256=bisect.sha(raw), image_offset=offset, size=len(raw))}
        with OuterImage(path) as image:
            for key in KEYS:
                raw = image.read_entry(BOOK_ENTRIES[key])
                bisect.write_new(directory / (key + ".play"), raw)
                rows[key] = dict(sha256=bisect.sha(raw), entry=BOOK_ENTRIES[key], size=len(raw))
        receipt[version] = dict(source=str(path), files=rows)
    return receipt


def key_state(m, key, category=0):
    for n, team in enumerate((s.TEAM, getattr(m, "defense", s.TEAM))):
        team_key = key[n] if isinstance(key, tuple) else key
        base = s.SOURCE + 0x1D000 + 0x400 * n
        roster = base + 0x200
        m.m.mem_write(base, bytes(0x200))
        # 207EF0 receives a live team. Roster fields live behind +0x1c.
        # The former hybrid fixture masked the shipped a4/a4pd pointer bug.
        m.put(team + 0x1C, roster)
        m.put(roster + 0x128, category)
        m.put(roster + 0x110, 0 if team_key is None else base)
        if team_key == "null_string":
            continue
        m.put(base + 4, base + 0x100)
        m.m.mem_write(base + 0x100, ((team_key or "") + "\0").encode("utf-16le"))


def stub_audit(final, old, directory):
    """Execute the installed stub, including its real yards-to-go callee."""
    m = Fixture(final)
    m.m.emu_start = lambda a, b, **kw: m.native_start(a, b, count=10000)
    image = XbeImage(final)
    alloc = stock.allocation(final)
    stub = alloc["va"] + stock.STUB_OFFSET
    table = gun.decode_bin_table(image.read(alloc["va"] + stock.BIN_TABLE_OFFSET, gun.BIN_TABLE_SIZE))
    moments = gun.decode_table(image.read(alloc["va"] + stock.WEIGHT_OFFSET, gun.TABLE_SIZE))
    code, out = s.SOURCE + 0x1B000, s.SOURCE + 0x1B100
    stats = dict(cases=0, faults=[], togo_calls=0, misaligned_togo_calls=0, table_reads=0,
                 out_of_table_reads=0, nonvolatile_register_errors=0, full_rule_cases=0,
                 full_rule_faults=[], budget=10000, modes=list(MODES))

    def togo(u, a, n, _):
        stats["togo_calls"] += 1
        stats["misaligned_togo_calls"] += int(bool((u.reg_read(m.r.UC_X86_REG_ECX) |
                                                  u.reg_read(m.r.UC_X86_REG_EDX)) & 15))

    m.m.hook_add(m.ucmod.UC_HOOK_CODE, togo, begin=gun.TOGO_FUNCTION, end=gun.TOGO_FUNCTION)
    bin_start = alloc["va"] + stock.BIN_TABLE_OFFSET

    # Count the fild read only, not the scan's UTF-16 reads.
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    fild_pc = next(i.address for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(
        image.read(stub, gun.STUB_SPACE), stub) if i.mnemonic == "fild")
    def fild_guard(u, a, n, _):
        addr = bin_start + u.reg_read(m.r.UC_X86_REG_ECX)
        stats["table_reads"] += 1
        stats["out_of_table_reads"] += int(not bin_start <= addr <= bin_start + gun.BIN_TABLE_SIZE - 2)
    m.m.hook_add(m.ucmod.UC_HOOK_CODE, fild_guard, begin=fild_pc, end=fild_pc)
    keys = (*stock.key_order(), "ZZZ", "BALX", "", None, "null_string")
    distances = (-1.0, 0.0, 1.0, 3.4, 3.6, 6.4, 6.6, 7.4, 7.6, 100.0, float("nan"), float("inf"), -float("inf"))
    downs = (0, 1, 2, 3, 4, 5, 0xffffffff)
    for key in keys:
        key_state(m, key)
        for mode, down, distance in itertools.product(MODES, downs, distances):
            stats["cases"] += 1
            shift = (stats["cases"] % 4) * 4
            m.state(down=down, distance=distance, yard=50, mode=mode)
            m.put(gun.ROW_WORD, 0)
            # Make the native callee's [esp+0x20] team argument, testing all
            # four possible incoming stack alignments. Restore it on return.
            program = b"\x83\xec" + bytes([shift]) + b"\x68" + struct.pack("<I", s.TEAM) + b"\x83\xec\x1c"
            program += b"\xe8" + struct.pack("<i", stub - (code + len(program) + 5))
            program += b"\xd9\x1d" + struct.pack("<I", out) + b"\x83\xc4" + bytes([32 + shift]) + b"\xc3"
            m.m.mem_write(code, program)
            m.m.ctl_remove_cache(code, code + len(program))
            try:
                m.call(code, ebx=0x12345678, esi=0x23456789, edi=0x3456789a, ebp=0x456789ab)
                got = struct.unpack("<f", m.m.mem_read(out, 4))[0]
                if mode == 8:
                    want = moments[0]
                elif key not in stock.key_order() or down not in (1, 2, 3, 4):
                    want = gun.RETAIL_WEIGHT
                else:
                    # Bitwise compare is what the actual code uses. Negative
                    # or non-finite distances take the long bin, safely.
                    bits = struct.unpack("<I", struct.pack("<f", distance * gun.YARD))[0]
                    if down == 1:
                        index = 0
                    else:
                        cuts = (gun.CUT_SHORT, gun.CUT_SECOND_MID if down == 2 else gun.CUT_THIRD_MID)
                        index = (1 if down == 2 else 4) + sum(bits > cut for cut in cuts)
                    want = table[stock.key_order().index(key)][index]
                bisect.require(math.isfinite(got) and abs(got - want) < 1e-5 * max(1, want), "wrong weight")
                for reg, val in ((m.r.UC_X86_REG_EBX, 0x12345678), (m.r.UC_X86_REG_ESI, 0x23456789),
                                 (m.r.UC_X86_REG_EDI, 0x3456789a), (m.r.UC_X86_REG_EBP, 0x456789ab)):
                    stats["nonvolatile_register_errors"] += int(m.m.reg_read(reg) != val)
            except Exception as exc:
                if len(stats["faults"]) < 25:
                    stats["faults"].append(dict(key=key, mode=mode, down=down, distance=str(distance), error=str(exc)))
        print("stub", key, stats["cases"], len(stats["faults"]), flush=True)
    # The caller path also executes 0x207E30 and the actual formation rule.
    for key in ("BAL", "PHI"):
        for version, raw in (("v05", old), ("v06", final)):
            probe = Probe(raw, (directory / (key + ".play")).read_bytes(), key)
            for mode, down, distance, category in itertools.product(MODES, (1, 2, 3, 4), (1., 5., 10.), (0, 4)):
                probe.m.put(probe.m.get(s.TEAM + 0x1C) + 0x128, category)
                stats["full_rule_cases"] += 1
                try:
                    got = probe.weight(down, distance, mode=mode)
                    bisect.require(math.isfinite(got) and got > 0, "non-positive full-rule weight")
                except Exception as exc:
                    stats["full_rule_faults"].append(dict(team=key, version=version, mode=mode,
                        down=down, distance=distance, category=category, error=str(exc)))
    return stats


def lottery_audit(old, final):
    patterns = {"zero": lambda n: [0.] * n, "positive": lambda n: [1.] * n,
                "negative": lambda n: [-1.] * n, "tiny": lambda n: [1e-40] * n,
                "huge": lambda n: [3e38] * n, "nan": lambda n: [float("nan")] * n,
                "infinity": lambda n: [float("inf")] * n,
                "mixed_nan": lambda n: [float("nan")] + [1.] * (n - 1),
                "mixed_infinity": lambda n: [float("inf")] + [1.] * (n - 1)}
    result = dict(cases=0, faults=[], differences=[], rows=[], budget=10000)
    all_rows = {}
    for version, payload in (("v05", old), ("v06", final)):
        m = Fixture(payload)
        m.m.emu_start = lambda a, b, **kw: m.native_start(a, b, count=10000)
        for count, exponent, pattern, seed in itertools.product((0, 1, 2, 30), (1, 2, 3), patterns, (1, 27, 91)):
            values = patterns[pattern](max(1, count))
            at = s.SOURCE + 0x1B100
            m.m.mem_write(at, struct.pack("<" + "f" * len(values), *values) + bytes(16))
            m.seed(.5, seed)
            result["cases"] += 1
            try:
                picked = m.call(0x203440, args=(at, count, exponent))
                bisect.require(0 <= picked < max(count, 1), "index outside candidate table")
                key = (count, exponent, pattern, seed)
                if version == "v05":
                    all_rows[key] = picked
                elif picked != all_rows[key]:
                    result["differences"].append(list(key))
            except Exception as exc:
                result["faults"].append(dict(version=version, count=count, exponent=exponent, pattern=pattern, error=str(exc)))
    return result


def p9_audit(old, final, book):
    """Fast policy/try replay, including modes and late/overtime boundaries."""
    from mod_editor.core import nfl2k5_cpu_money_downs as cpu
    result = dict(cases=0, faults=[], policy_results=Counter(), try_results=Counter(),
                  budget=100000, modes=list(MODES))
    states = [dict(quarter=q, seconds=t, margin=margin, yard=yard, distance=distance,
                   quarter_seconds=period, ot_bits=bits)
              for q, t, margin, yard, distance, period, bits in (
                  (1, 240, 0, 25, 1, 300, 0), (1, 240, 0, 25, 9, 300, 0),
                  (4, 119, 1, 80, 7, 300, 0), (4, 120, 3, 85, 12, 300, 0),
                  (4, 121, 3, 85, 12, 300, 0), (4, 0, -8, 50, 10, 300, 0),
                  (5, 420, -7, 50, 10, 600, 3), (5, 420, -3, 80, 10, 600, 3),
                  (5, 420, 0, 80, 10, 600, 0), (5, 420, 0, 80, 10, 600, 2),
                  (0, 240, 0, 50, 1, 0, 0), (255, 240, -1, 50, 1, 0, 255),
                  (4, float("nan"), 1, 80, 7, 300, 0), (4, float("inf"), 1, 80, 7, 300, 0),
                  (4, 120, 1, 80, float("nan"), 300, 0), (4, 120, 1, 80, -1, 300, 0),
                  (4, 120, 1, -1, 7, 300, 0), (4, 120, 1, 101, 7, 300, 0),
                  (4, 120, 1, 80, 7, 0, 0), (4, 120, 1, 80, 7, float("nan"), 0))]
    for version, payload in (("v05", old), ("v06", final)):
        m = Fixture(payload)
        m.load_book(book)
        m.m.emu_start = lambda a, b, **kw: m.native_start(a, b, count=100000)
        entry = next(a["va"] for a in bisect.space.layout(payload)["allocations"] if a["owner"] == cpu.OWNER)
        labels = cpu.assembly.LABELS2 if version == "v06" else cpu.assembly.LABELS
        pc = entry + labels["policy"]
        for mode, state, direction in itertools.product(MODES, states, (-1, 1)):
            clean = {k: str(v) if isinstance(v, float) and not math.isfinite(v) else v for k, v in state.items()}
            try:
                m.state(mode=mode, **state)
                # Apply direction consistently to both native marker vectors.
                m.fput(s.DIRECTION + 4, direction)
                m.fput(s.STATE + 0x18, (state["yard"] - 50) * 91.44 * direction)
                m.fput(s.STATE + 0x28, (state["yard"] - 50 + state["distance"]) * 91.44 * direction)
                result["cases"] += 1
                choice = m.call(pc, ecx=s.TEAM)
                bisect.require(choice in (0, 1, 2), "policy returned an invalid category action")
                result["policy_results"][version + ":" + str(choice)] += 1
                m.put(0xE602B4, 3)
                result["cases"] += 1
                choice = m.call(0x206E70, ecx=s.TEAM)
                bisect.require(choice in (0, 1), "try chart returned an invalid action")
                result["try_results"][version + ":" + str(choice)] += 1
            except Exception as exc:
                result["faults"].append(dict(version=version, mode=mode, state=clean, direction=direction, error=str(exc)))
    return result


def static_audit(old, final):
    """Pin inherited loop bodies and census bounded read-order operands."""
    spans = (("weighted_lottery", 0x203440, 294), ("yards_to_go", 0x207950, 91),
             ("formation_iterator", 0xE0670, 28), ("play_iterator", 0xE06F0, 25),
             ("unweighted_fallback", 0x204930, 212), ("gameplan", 0x281D90, 930))
    a, b = XbeImage(old), XbeImage(final)
    rows = []
    for label, va, size in spans:
        before, after = a.read(va, size), b.read(va, size)
        rows.append(dict(label=label, va=va, size=size, identical=before == after,
                         v05_sha256=bisect.sha(before), v06_sha256=bisect.sha(after)))
    return dict(spans=rows, note="Byte comparisons do not substitute for a captured live game state.")


def reads_audit(directory):
    from mod_editor.core import nfl2k5_playbook_lint as lint
    result = dict(teams=[], faults=[])
    for key in KEYS:
        row = dict(team=key, pass_links=0, read_nodes=0, modes=Counter(), direct_nodes=0, faults=[])
        for view in lint.resource_views((directory / (key + ".play")).read_bytes()):
            if not lint.is_pass(view):
                continue
            row["pass_links"] += 1
            for node in view.chains[lint.qb_slot(view)]:
                if node.op != 6:
                    continue
                row["read_nodes"] += 1
                row["modes"][int(node.operands[0])] += 1
                if int(node.operands[0]) != 0:
                    continue
                row["direct_nodes"] += 1
                reads = [int(v) for v in node.operands[1:5]]
                if any(v < 0 or v > 5 for v in reads):
                    row["faults"].append(dict(reason="direct read index outside slots 6..10/zero", reads=reads))
        result["teams"].append(row)
    return result


def failure_count(value):
    lists = {"faults", "full_rule_faults", "differences", "invalid_ownership", "empty_owned_categories",
             "distribution_faults", "lottery_bad_weights"}
    scalars = {"misaligned_togo_calls", "nonvolatile_register_errors", "out_of_table_reads"}
    if isinstance(value, dict):
        return sum(len(v) if k in lists else int(v) if k in scalars else 1 if k == "error" else failure_count(v)
                   for k, v in value.items())
    if isinstance(value, list):
        return sum(failure_count(v) for v in value)
    return 0


def books_audit(directory, payload):
    rows = []
    for key in KEYS:
        raw = (directory / (key + ".play")).read_bytes()
        book = model.book_from(raw)
        native = Fixture(payload)
        native.load_book(raw)
        rec = native.get(s.TEAM + 0xC)
        native_special = {native.get(rec + off) for off in (0x44, 0x4C, 0x54)} - {0}
        special = {(v - s.BOOK - ip.FORMATION_BASE) // ip.FORMATION_SIZE for v in native_special}
        special_cats = {native.get(rec + off) for off in (0x48, 0x50, 0x58)} - {0}
        book.special_forms = special
        book.special_cats = {(v - s.BOOK - ip.CATEGORY_BASE) // 16 for v in special_cats}
        row = dict(team=key, sha256=bisect.sha(raw), categories=[], invalid_ownership=[],
                   empty_owned_categories=[], distribution_faults=[], formations=len(book.forms),
                   plays=len(book.book.plays), native_special_forms=sorted(special))
        for form in book.forms:
            if form["own"] not in book.cats or form["mask"] >> len(book.cats):
                row["invalid_ownership"].append(form)
        for ci, category in book.cats.items():
            if category["id"] > 10 or ci in book.special_cats or not book.members(ci):
                continue
            eligible = [f for f in book.forms if f["mask"] >> ci & 1 and f["index"] not in special
                        and not f["flags"] & 0x40000000 and f["type"] < 4]
            if any(f["own"] == ci for f in book.forms if f["index"] not in special):
                eligible = [f for f in eligible if f["own"] == ci]
            if not eligible:
                row["empty_owned_categories"].append(ci)
            row["categories"].append(dict(index=ci, id=category["id"], name=category["name"], eligible=len(eligible)))
        for down, distance, yard in itertools.product((1, 2, 3, 4), (0, 1, 3, 5, 7, 10, 25, 99), (1, 50, 95, 99)):
            try:
                pc, pf, means = book.distribution(dict(down=down, distance=distance, yard=yard))
                bisect.require(pc and pf and all(math.isfinite(v) and v > 0 for v in means.values()), "zero/invalid category mean")
                bisect.require(abs(sum(pc.values()) - 1) < 1e-6 and abs(sum(pf.values()) - 1) < 1e-6, "lost lottery mass")
            except Exception as exc:
                row["distribution_faults"].append(dict(down=down, distance=distance, yard=yard, error=str(exc)))
        # Fallback is unweighted and depends on a nonempty callable-play set.
        row["fallback_results"] = []
        for filter_kind in (0, 8):
            native.state(down=2, distance=9, mode=0)
            try:
                choice = native.call(0x204930, eax=s.TEAM, args=(filter_kind, 0))
                row["fallback_results"].append(dict(filter=filter_kind, choice=hex(choice)))
            except Exception as exc:
                row["fallback_results"].append(dict(filter=filter_kind, error=str(exc)))
        rows.append(row)
        print("book", directory.name, key, len(row["empty_owned_categories"]), len(row["distribution_faults"]), flush=True)
    return dict(teams=rows, distribution_cases=len(rows) * 128,
                note="Analytic mass check uses retail positive shotgun constant; native commits below use final a4pd weights.")


def selectors(old_dir, final_dir, keys):
    result = dict(teams=[], budget=20000000, fixture=__doc__, modes=list(MODES))
    early = [dict(down=d, distance=dist, yard=25, quarter=1, seconds=240)
             for d, dist in ((1, 10), (2, 9), (3, 5), (3, 10), (4, 1), (4, 12))]
    early += [dict(phase=2, quarter=1, seconds=240), dict(phase=3, quarter=1, seconds=240)]
    for team in keys:
        for version, xbe_dir, book_dir in (("v05", old_dir, old_dir), ("v06", final_dir, final_dir),
                                           ("v05_code_v06_book", old_dir, final_dir)):
            m = Fixture((xbe_dir / "default.xbe").read_bytes())
            m.load_book((book_dir / (team + ".play")).read_bytes())
            # A return hook records count and weight sum before the lottery
            # mutates the weights with its exponent.
            lotteries = Counter()
            bad_weights = []
            def lottery(u, a, n, _):
                sp = u.reg_read(m.r.UC_X86_REG_ESP)
                caller, weights, count, exponent = struct.unpack("<4I", u.mem_read(sp, 16))
                lotteries[(hex(caller), count, exponent)] += 1
                if count > 30:
                    bad_weights.append(dict(caller=hex(caller), count=count, reason="over 30"))
                    u.emu_stop()
                elif count:
                    values = struct.unpack("<" + "f" * count, u.mem_read(weights, 4 * count))
                    if any(not math.isfinite(v) or v < 0 for v in values) or sum(values) <= 0:
                        bad_weights.append(dict(caller=hex(caller), count=count, weights=[str(v) for v in values]))
            m.m.hook_add(m.ucmod.UC_HOOK_CODE, lottery, begin=0x203440, end=0x203440)
            row = dict(team=team, version=version, cases=0, faults=[], lottery_bad_weights=bad_weights,
                       native_environment={}, calls={})
            for mode, key, state in itertools.product(MODES, (team, "ZZZ", None), early):
                key_state(m, key)
                m.state(mode=mode, **state)
                m.put(gun.ROW_WORD, 0)
                m.seed(.5, 123 + row["cases"])
                for pc, side, args in ((0x20B670, s.TEAM, ()), (0x20B820, m.defense, (0,))):
                    row["cases"] += 1
                    out = s.SOURCE + 0x19100
                    m.m.mem_write(out, bytes(16))
                    try:
                        m.call(pc, ecx=side, edx=out, args=args)
                    except Exception as exc:
                        row["faults"].append(dict(mode=mode, key=key, state=state, routine=hex(pc), error=str(exc)))
            row["lotteries"] = [dict(caller=k[0], count=k[1], exponent=k[2], visits=v) for k, v in sorted(lotteries.items())]
            row["native_environment"] = dict(m.environment_calls)
            row["calls"] = dict(m.counts)
            result["teams"].append(row)
            print("selectors", team, version, row["cases"], len(row["faults"]), len(bad_weights), flush=True)
    return result


def paired_audit(old_dir, final_dir):
    """BAL versus PHI, with separate native book banks, in both directions."""
    result = dict(rows=[], modes=list(MODES), budget=20000000,
                  fixture="World rating/lineup leaves retained; independent book banks at 0xB75A40 and 0xB88DD0; modes 1/2 cached play pointers initialized by ordinary native commits.")
    for version, directory in (("v05", old_dir), ("v06", final_dir)):
        for offense, defense in (("BAL", "PHI"), ("PHI", "BAL")):
            m = Fixture((directory / "default.xbe").read_bytes())
            m.load_book((directory / (offense + ".play")).read_bytes())
            raw = (directory / (defense + ".play")).read_bytes()
            defensive_book = ip.parse_playbook_resource(raw)
            m.m.mem_write(s.SOURCE, raw[32:])
            m.call(0x161E30, ecx=s.SOURCE, edx=1)
            bank = s.BOOK + 0x13390
            m.put(m.defense + 0x20, bank)
            for play in defensive_book.plays:
                m.call(0x1A9A80, ecx=bank + ip.PLAY_BASE + play.index * ip.PLAY_SIZE)
            rec = m.get(m.defense + 0xC)
            m.m.mem_write(rec + 0x2C, bytes(0x30))
            m.call(0x204C80, eax=m.defense)
            key_state(m, (offense, defense))
            # Modes 1/2 have a separate cached-play branch. The old World
            # fixture leaves these globals null. Fill them with real native
            # choices from the corresponding team's bank before exercising
            # that branch; do not treat an uninitialized fixture as a hang.
            m.state(mode=0, down=1, distance=10, yard=25, quarter=1, seconds=240)
            cached_out = s.SOURCE + 0x19100
            m.call(0x20B670, ecx=s.TEAM, edx=cached_out)
            offense_choice = struct.unpack("<4I", m.m.mem_read(cached_out, 16))
            m.call(0x20B820, ecx=m.defense, edx=cached_out, args=(0,))
            defense_choice = struct.unpack("<4I", m.m.mem_read(cached_out, 16))
            m.put(0xB3426C, offense_choice[2])
            m.put(0xB34264, defense_choice[2])
            m.put(0xB34268, defense_choice[3])
            row = dict(version=version, offense=offense, defense=defense, cases=0, faults=[])
            for mode, direction, down, distance in itertools.product(MODES, (-1, 1), (1, 2), (9, 10)):
                m.state(mode=mode, down=down, distance=distance, yard=25, quarter=1, seconds=240)
                m.fput(s.DIRECTION + 4, direction)
                m.fput(s.STATE + 0x18, -25 * 91.44 * direction)
                m.fput(s.STATE + 0x28, (-25 + distance) * 91.44 * direction)
                m.put(gun.ROW_WORD, 0)
                m.seed(.5, 317 + row["cases"])
                for pc, side, args in ((0x20B670, s.TEAM, ()), (0x20B820, m.defense, (0,))):
                    row["cases"] += 1
                    out = s.SOURCE + 0x19100
                    values = ()
                    try:
                        m.call(pc, ecx=side, edx=out, args=args)
                        values = struct.unpack("<4I", m.m.mem_read(out, 16))
                        expected_bank = s.BOOK if pc == 0x20B670 else bank
                        bisect.require(all(expected_bank <= v < expected_bank + 0x13390 for v in values[:3]),
                                       "commit returned a pointer outside its team's book")
                    except Exception as exc:
                        row["faults"].append(dict(mode=mode, direction=direction, down=down, distance=distance,
                                                  routine=hex(pc), output=[hex(v) for v in values], error=str(exc)))
            result["rows"].append(row)
            print("paired", version, offense, defense, row["cases"], len(row["faults"]), flush=True)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("extract", "stub", "lottery", "books", "selectors", "p9", "static", "reads", "paired"))
    ap.add_argument("--scratch", type=Path, required=True)
    ap.add_argument("--v05", type=Path)
    ap.add_argument("--safe", type=Path)
    ap.add_argument("--teams", default="BAL,PHI")
    args = ap.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    before_dir, final_dir = args.scratch / "v05", args.scratch / "v06"
    if args.mode == "extract":
        result = extract(args.v05, args.safe, args.scratch)
    else:
        old = (before_dir / "default.xbe").read_bytes()
        final = (final_dir / "default.xbe").read_bytes()
        bisect.require(bisect.sha(old) == bisect.V05_HASH and bisect.sha(final) == bisect.V06_HASH, "unexpected input executables")
        if args.mode == "stub":
            result = stub_audit(final, old, final_dir)
        elif args.mode == "lottery":
            result = lottery_audit(old, final)
        elif args.mode == "books":
            result = {"v05": books_audit(before_dir, old), "v06": books_audit(final_dir, final)}
        elif args.mode == "p9":
            result = p9_audit(old, final, (final_dir / "BAL.play").read_bytes())
        elif args.mode == "static":
            result = static_audit(old, final)
        elif args.mode == "reads":
            result = {"v05": reads_audit(before_dir), "v06": reads_audit(final_dir)}
        elif args.mode == "paired":
            result = paired_audit(before_dir, final_dir)
        else:
            result = selectors(before_dir, final_dir, args.teams.split(","))
    save(args.scratch / (args.mode + ".json"), result)
    failures = failure_count(result)
    print("saved", args.mode + ".json", "failures", failures, flush=True)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
