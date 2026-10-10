#!/usr/bin/env python3
"""FRZ4 native selection replay with the game's two distinct team object types.

Uses real executable/book bytes and native selector, RNG, rule and distance
functions. Ratings/lineup/clock leaves retain the explicit World fixtures.
These are reconstructed between-play states, not captured attract-demo RAM.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from tools.b77.p9_harness import Fixture
from tools.b77 import frz_xbe_bisect as b
from mod_editor.core import nfl2k5_play_scoring as s
from mod_editor.core import nfl2k5_playbook_inspector as ip
from mod_editor.core import nfl2k5_stock_books as stock
from mod_editor.core import nfl2k5_moment_gun_weight as gun

LIVE = (0xE5FC20, 0xE5FC60)
ROSTER = (0xB30864, 0xB30A58)
OUT = s.SOURCE + 0x19100
CODE = s.SOURCE + 0x1B000
SENTINELS = dict(EBX=0x12345678, ESI=0x23456789, EDI=0x3456789A, EBP=0x456789AB)
REGS = tuple(SENTINELS)


def fpu(m):
    tag = m.m.reg_read(m.r.UC_X86_REG_FPTAG)
    sw = m.m.reg_read(m.r.UC_X86_REG_FPSW)
    return dict(tag=tag, top=(sw >> 11) & 7, depth=sum((tag >> (2 * i)) & 3 != 3 for i in range(8)),
                exceptions=sw & 0x7F, control=m.m.reg_read(m.r.UC_X86_REG_FPCW))


class LiveFixture(Fixture):
    def __init__(self, payload, home_book, away_book):
        super().__init__(payload)
        self.load_book(home_book)
        self.books = [self.book, ip.parse_playbook_resource(away_book)]
        self.m.mem_write(s.SOURCE, away_book[32:])
        self.call(0x161E30, ecx=s.SOURCE, edx=1)
        self.banks = (s.BOOK, s.BOOK + 0x13390)
        self.put(self.defense + 0x20, self.banks[1])
        for play in self.books[1].plays:
            self.call(0x1A9A80, ecx=self.banks[1] + ip.PLAY_BASE + play.index * ip.PLAY_SIZE)
        self.call(0x204C80, eax=self.defense)
        for source, target in zip((s.TEAM, self.defense), LIVE):
            self.m.mem_write(target, bytes(self.m.mem_read(source, 0x3C)))
        self.put(LIVE[0], LIVE[1])
        self.put(LIVE[1], LIVE[0])
        # Run the actual constructor's getter/store pairs, not a guessed link.
        for start, end in ((0x87197, 0x871A1), (0x871C4, 0x871CE)):
            self.m.reg_write(self.r.UC_X86_REG_ESP, s.STACK)
            self.native_start(start, end, count=100)
            b.require(self.m.reg_read(self.r.UC_X86_REG_EIP) == end, "native roster link did not finish")
        b.require(tuple(self.get(t + 0x1C) for t in LIVE) == ROSTER, "native roster layout differs")
        self.defense = LIVE[1]
        self.set_keys("BAL", "PHI")
        self.side(0)
        self.seed(.5, 1)
        self.rule_calls = Counter()
        self.rule_errors = []
        self.rule_pending = None
        self.lottery_calls = 0
        self.bad_weights = []
        self.stub_calls = 0
        self.togo_calls = 0
        self.bin_reads = 0
        self.bad_bin_reads = 0
        self.max_depth = 0
        self.trace = []
        self.m.hook_add(self.ucmod.UC_HOOK_CODE, self.rule_entry, begin=0x207EF0, end=0x207EF0)
        for pc in (0x208150, 0x2083A9):
            self.m.hook_add(self.ucmod.UC_HOOK_CODE, self.rule_exit, begin=pc, end=pc)
        self.m.hook_add(self.ucmod.UC_HOOK_CODE, self.lottery, begin=0x203440, end=0x203440)
        self.m.hook_add(self.ucmod.UC_HOOK_CODE, self.togo, begin=gun.TOGO_FUNCTION, end=gun.TOGO_FUNCTION)
        self.stub = stock.allocation(payload)["va"] + stock.STUB_OFFSET
        self.m.hook_add(self.ucmod.UC_HOOK_CODE, self.stub_entry, begin=self.stub, end=self.stub)
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for insn in Cs(CS_ARCH_X86, CS_MODE_32).disasm(bytes(self.m.mem_read(self.stub, gun.STUB_SPACE)), self.stub):
            if insn.mnemonic == "fild":
                self.m.hook_add(self.ucmod.UC_HOOK_CODE, self.bin_read, begin=insn.address, end=insn.address)

    def set_keys(self, home, away, category=0):
        for n, (record, key) in enumerate(zip(ROSTER, (home, away))):
            at = s.SOURCE + 0x1D000 + n * 0x400
            self.m.mem_write(at, bytes(0x200))
            self.put(record + 0x128, category)
            self.put(record + 0x110, at if key is not None else 0)
            self.put(at + 4, at + 0x100)
            self.m.mem_write(at + 0x100, ((key or "") + "\0").encode("utf-16le"))

    def side(self, index):
        self.offense_index = index
        self.put(0xE60280, LIVE[index])
        self.put(0xE60284, LIVE[1 - index])

    def registers(self):
        return {name: self.m.reg_read(getattr(self.r, "UC_X86_REG_" + name)) for name in REGS}

    def begin_stream(self):
        # Once per stream, never between plays or selector calls.
        for name, value in dict(SENTINELS, ESP=s.STACK + 4, FPCW=0x37F, FPTAG=0xFFFF, FPSW=0, EFLAGS=0x202).items():
            self.m.reg_write(getattr(self.r, "UC_X86_REG_" + name), value)

    def persistent_call(self, pc, *, args=(), **registers):
        before_sp = self.m.reg_read(self.r.UC_X86_REG_ESP)
        before_regs = self.registers()
        before_fpu = fpu(self)
        sp = before_sp - 4 * (1 + len(args))
        self.m.mem_write(sp, struct.pack("<" + "I" * (1 + len(args)), s.STOP, *args))
        self.m.reg_write(self.r.UC_X86_REG_ESP, sp)
        for name, value in registers.items():
            self.m.reg_write(getattr(self.r, "UC_X86_REG_" + name.upper()), value)
        self.problem = None
        try:
            self.native_start(pc, s.STOP, count=20000000, timeout=5000000)
        except self.ucmod.UcError as exc:
            if not self.problem:
                self.problem = dict(error=str(exc), pc=hex(self.m.reg_read(self.r.UC_X86_REG_EIP)))
        if self.problem:
            raise RuntimeError(json.dumps(self.problem))
        b.require(self.m.reg_read(self.r.UC_X86_REG_EIP) == s.STOP,
                  f"native budget expired at {self.m.reg_read(self.r.UC_X86_REG_EIP):#x}")
        b.require(self.m.reg_read(self.r.UC_X86_REG_ESP) == before_sp, "ESP imbalance")
        b.require(self.registers() == before_regs, "nonvolatile register imbalance")
        after = fpu(self)
        b.require(after == before_fpu, f"x87 state imbalance: {before_fpu} -> {after}")
        return self.m.reg_read(self.r.UC_X86_REG_EAX)

    def rule_entry(self, u, pc, n, _):
        sp = u.reg_read(self.r.UC_X86_REG_ESP)
        caller = self.get(sp)
        self.rule_calls[hex(caller)] += 1
        self.rule_pending = (sp, self.registers(), fpu(self), caller)

    def rule_exit(self, u, pc, n, _):
        if self.rule_pending is None:
            return
        sp, registers, before, caller = self.rule_pending
        after = fpu(self)
        self.max_depth = max(self.max_depth, after["depth"])
        if not (pc == caller and u.reg_read(self.r.UC_X86_REG_ESP) == sp + 12
                and registers == self.registers() and after["depth"] == before["depth"] + 1
                and after["top"] == (before["top"] - 1) % 8 and not after["exceptions"]):
            self.rule_errors.append(dict(caller=hex(pc), before=before, after=after))
        self.rule_pending = None

    def lottery(self, u, pc, n, _):
        sp = u.reg_read(self.r.UC_X86_REG_ESP)
        caller, address, count, exponent = struct.unpack("<4I", u.mem_read(sp, 16))
        self.lottery_calls += 1
        if count > 30:
            self.bad_weights.append(dict(caller=hex(caller), count=count))
            u.emu_stop()
        elif count:
            weights = struct.unpack("<" + "f" * count, u.mem_read(address, 4 * count))
            if any(not math.isfinite(v) or v < 0 for v in weights) or sum(weights) <= 0:
                self.bad_weights.append(dict(caller=hex(caller), weights=[str(v) for v in weights]))

    def stub_entry(self, u, pc, n, _):
        self.stub_calls += 1
        if len(self.trace) < 4:
            team = self.get(u.reg_read(self.r.UC_X86_REG_ESP) + 0x20)
            self.trace.append(dict(team=hex(team), roster=hex(self.get(team + 0x1C)),
                                   wrong_key_field=hex(team + 0x110), wrong_key_value=hex(self.get(team + 0x110)),
                                   wrong_category_value=hex(self.get(team + 0x128))))

    def togo(self, u, pc, n, _):
        self.togo_calls += 1
        b.require(not ((u.reg_read(self.r.UC_X86_REG_ECX) | u.reg_read(self.r.UC_X86_REG_EDX)) & 15),
                  "unaligned yards-to-go buffers")

    def bin_read(self, u, pc, size, _):
        # Guard the effective address BEFORE the read, including mapped
        # neighbors. A memory hook limited to the table cannot catch those.
        self.bin_reads += 1
        first = self.stub + gun.STUB_SPACE + 208
        address = first + u.reg_read(self.r.UC_X86_REG_ECX)
        self.bad_bin_reads += int(not first <= address <= first + gun.BIN_TABLE_SIZE - 2)


def replay(payload, home_book, away_book, *, mode=0, plays=400, include_defense=True, progress=None):
    m = LiveFixture(payload, home_book, away_book)
    # Modes 1/2 select cached plays. Seed those from native ordinary choices.
    m.state(mode=0, down=1, distance=10, yard=25, quarter=1, seconds=240)
    m.begin_stream()
    out = dict(mode=mode, requested_plays=plays, completed_plays=0, selector_calls=0, faults=[],
               includes_defense=include_defense,
               fpu_resets_between_calls=0, rng_reseeds_between_calls=0)
    try:
        if mode in (1, 2):
            for pc, team, args in ((0x20B670, LIVE[0], ()), (0x20B820, LIVE[1], (0,))):
                m.persistent_call(pc, ecx=team, edx=OUT, args=args)
                picked = struct.unpack("<4I", m.m.mem_read(OUT, 16))
                if pc == 0x20B670:
                    m.put(0xB3426C, picked[2])
                else:
                    m.put(0xB34264, picked[2]); m.put(0xB34268, picked[3])
        for play in range(plays):
            side = (play // 8) % 2 if mode not in (1, 2) else 0
            m.side(side)
            # All seven bins, red zone, goal line, both field directions and
            # early/late clocks. RNG advances in the real native lotteries.
            down, distance = ((1, 10), (2, 2), (2, 6), (2, 11), (3, 2), (3, 5), (3, 10), (4, 1))[play % 8]
            yard = (25, 50, 70, 85, 92, 98)[(play // 8) % 6]
            m.state(mode=mode, down=down, distance=distance, yard=yard,
                    quarter=1 if play % 32 < 24 else 4, seconds=240 if play % 32 < 24 else 80)
            direction = -1 if (play // 16) % 2 else 1
            m.fput(s.DIRECTION + 4, direction)
            m.fput(s.STATE + 0x18, (yard - 50) * gun.YARD * direction)
            m.fput(s.STATE + 0x28, (yard - 50 + distance) * gun.YARD * direction)
            m.put(gun.ROW_WORD, (play // 8) % 51)
            calls = [(0x20B670, LIVE[side], side, ())]
            if include_defense:
                calls.append((0x20B820, LIVE[1 - side], 1 - side, (0,)))
            for pc, team, index, args in calls:
                out["selector_calls"] += 1
                m.persistent_call(pc, ecx=team, edx=OUT, args=args)
                pointers = struct.unpack("<4I", m.m.mem_read(OUT, 16))
                bank = m.banks[index]
                b.require(all(bank <= p < bank + 0x13390 for p in pointers[:3]), "selection outside team book")
            out["completed_plays"] += 1
            if progress and (play + 1) % 25 == 0:
                progress(play + 1)
    except (ValueError, RuntimeError) as exc:
        out["faults"].append(dict(play=out["completed_plays"], error=str(exc), native=m.problem))
    out.update(rule_calls=dict(m.rule_calls), rule_balance_errors=m.rule_errors,
               lottery_calls=m.lottery_calls, bad_weights=m.bad_weights, stub_calls=m.stub_calls,
               togo_calls=m.togo_calls, bin_reads=m.bin_reads, bad_bin_reads=m.bad_bin_reads,
               final_fpu=fpu(m), stub_entries=m.trace)
    return out


def rule_grid(payload, home_book, away_book, *, patched=True):
    """Full 207EF0 on real-address live teams, without resetting the FPU."""
    m = LiveFixture(payload, home_book, away_book)
    m.begin_stream()
    result = dict(cases=0, failures=[], modes=list(range(16)))
    bin_rows = gun.team_bin_weights(keys=stock.key_order())
    for side, key in enumerate(("BAL", "PHI")):
        m.side(side)
        bank = m.banks[side]
        formation = next(bank + ip.FORMATION_BASE + f.index * ip.FORMATION_SIZE
                         for f in m.books[side].formations
                         if m.get(bank + ip.FORMATION_BASE + f.index * ip.FORMATION_SIZE + 4) & 0xC0000 == 0x80000)
        # Save the caller's EDI, supply both callee-cleaned arguments, then
        # consume ST0 exactly once. The rule's two real callers do the same.
        code = b"\x57\x68" + struct.pack("<I", s.SOURCE + 0x1E200)
        code += b"\x68" + struct.pack("<I", LIVE[side])
        code += b"\xbf" + struct.pack("<I", formation) + b"\xb8\x01\x00\x00\x00"
        code += b"\xe8" + struct.pack("<i", 0x207EF0 - (CODE + len(code) + 5))
        return_pc = CODE + len(code)
        code += b"\xd9\x1d" + struct.pack("<I", OUT) + b"\x5f\xc3"
        m.m.mem_write(CODE, code)
        m.m.ctl_remove_cache(CODE, CODE + len(code))
        hook = m.m.hook_add(m.ucmod.UC_HOOK_CODE, m.rule_exit, begin=return_pc, end=return_pc)
        for mode in range(16):
            for down in (0, 1, 2, 3, 4, 5):
                for distance in (1., 3.4, 3.6, 5., 6.4, 6.6, 7.4, 7.6, 10., 25.):
                    m.state(mode=mode, down=down, distance=distance, yard=50)
                    m.put(gun.ROW_WORD, 38)
                    result["cases"] += 1
                    try:
                        m.persistent_call(CODE)
                        got = struct.unpack("<f", m.m.mem_read(OUT, 4))[0]
                        if not patched or down not in (1, 2, 3, 4) and mode != 8:
                            expected = gun.RETAIL_WEIGHT
                        elif mode == 8:
                            expected = gun.weights()[38]
                        else:
                            from tools.b77.a4_bins_probe import expected_bin
                            expected = bin_rows[stock.key_order().index(key)][expected_bin(down, distance)]
                        b.require(math.isfinite(got) and abs(got - expected) < 1e-5 * max(1, expected),
                                  f"weight {got} differs from {expected}")
                    except (ValueError, RuntimeError) as exc:
                        result["failures"].append(dict(side=side, mode=mode, down=down, distance=distance, error=str(exc)))
        m.m.hook_del(hook)
    result.update(rule_balance_errors=m.rule_errors, final_fpu=fpu(m), togo_calls=m.togo_calls,
                  bin_reads=m.bin_reads, bad_bin_reads=m.bad_bin_reads)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixtures", type=Path, required=True, help="FRZ3 v05/v06 bounded extractions")
    ap.add_argument("--variants", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--plays", type=int, default=400)
    ap.add_argument("--modes", default="0,7")
    ap.add_argument("--offense-only", action="store_true", help="stress full 20B670, which includes both affected rule callers")
    args = ap.parse_args()
    rows = []
    for version, file, books in (
            ("v05", args.fixtures / "v05/default.xbe", args.fixtures / "v05"),
            ("v06", args.fixtures / "v06/default.xbe", args.fixtures / "v06"),
            ("X4", args.variants / "X4.default.xbe", args.fixtures / "v06"),
            ("X5", args.variants / "X5.default.xbe", args.fixtures / "v06")):
        for mode in map(int, args.modes.split(",")):
            print("start", version, mode, flush=True)
            row = replay(file.read_bytes(), (books / "BAL.play").read_bytes(), (books / "PHI.play").read_bytes(),
                         mode=mode, plays=args.plays, include_defense=not args.offense_only,
                         progress=lambda n: print("progress", version, mode, n, flush=True))
            row.update(version=version, xbe_sha256=b.sha(file.read_bytes()))
            rows.append(row)
            print(version, mode, row["completed_plays"], "plays", len(row["faults"]), "faults",
                  len(row["rule_balance_errors"]), "rule balance errors", flush=True)
            args.out.write_text(json.dumps(dict(fixture=__doc__, rows=rows), indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
