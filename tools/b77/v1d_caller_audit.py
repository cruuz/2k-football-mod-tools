#!/usr/bin/env python3
"""Offline caller audit for the October 9 v0.6 shotgun stub.

Scan every file-backed XBE section for relative calls/jumps and absolute entry
references. Replay actual call instructions with reconstructed caller frames,
plus the native argument-setup blocks of all offense/defense selector callers.
This is not controller-event, animation, GPU or whole-frame emulation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core import nfl2k5_moment_gun_weight as gun, nfl2k5_stock_books as stock
from mod_editor.core import nfl2k5_play_scoring as s, nfl2k5_playbook_inspector as ip
from tools.b77.frz_stub_audit import LiveFixture, LIVE, OUT, fpu

# A graph of call sites, not a guessed list of gameplay feature names. Nodes
# reload a live-team global or forward the same object to the next node.
CALLS = {
    0x207EF0: (0x20814B, 0x2083A4),
    0x208120: (0x2094D7, 0x209662),
    0x2081B0: (0x20A32A,),
    0x2093F0: (0x17F771, 0x20B3BB, 0x20B43D, 0x20B453, 0x20B472, 0x20B488,
               0x20B4F3, 0x20B513, 0x20B595),
    0x20A240: (0x17F365, 0x17F785, 0x20B233, 0x20B370, 0x20B728, 0x20B79F,
               0x20B85B, 0x20B8BD, 0x20B8EE),
    0x20B2E0: (0x20B5F7, 0x20B6B1, 0x20B7A6),
    0x20B400: (0x20B5FE, 0x20B84E, 0x20B8C4, 0x20B8D2),
    0x20B5D0: (0x11E736, 0x11E77A),
    0x20B670: (0xA2E84, 0xAA7CA, 0x129ECE, 0x1531BB, 0x153ADD, 0x154D34, 0x17F7AC, 0x15323F),
    0x20B820: (0xA2EC5, 0xA3436, 0xAA67E, 0x152C27, 0x1531E2, 0x17E335, 0xB8C81),
    0x20B180: (0x20B393, 0x20B51B),
}
TEAM_FLOW = {
    0x207EF0: "stack arg1 live team; EDI formation; native +0x1c read at 0x207f43",
    0x208120: "stack arg1 forwarded at 0x208140/145; arg2 is book; ESI category",
    0x2081B0: "stack arg1 owns book +0x20; forwarded at 0x208399/3a1",
    0x2093F0: "ECX saved in EBX at 0x2093fc; EBX pushed at 0x2094d6 and 0x20965d",
    0x20A240: "ECX saved in EBP at 0x20a24a; EBP pushed at 0x20a329",
    0x20B2E0: "reloads offense global at 0x20b355, 0x20b3a4 and 0x20b3b2",
    0x20B400: "reloads defense global at each category branch; no incoming team argument",
    0x20B5D0: "ECX live team; compares with offense global, dispatches offense or defense category",
    0x20B670: "ECX live team saved at 0x20b680/686; EDX output record or zero for commit",
    0x20B820: "ECX live team saved in EBX at 0x20b837; EDX output record or zero for commit",
    0x20B180: "uses offense global, including the patched fourth-down dispatcher",
}


def references(payload, targets):
    """Raw exhaustive byte search avoids losing calls after embedded jump tables.

    Report candidates rather than pretend disassembling data proves execution.
    Known call sites are checked separately against executable instructions.
    """
    image = XbeImage(payload)
    result = {t: [] for t in targets}
    for sec in image.sections:
        buf = payload[sec.raw:sec.raw + sec.raw_size]
        for match in re.finditer(b"[\xe8\xe9]", buf):
            p = match.start()
            if p + 5 > len(buf):
                continue
            target = (sec.start + p + 5 + struct.unpack_from("<i", buf, p + 1)[0]) & 0xFFFFFFFF
            if target in result:
                result[target].append(dict(site=hex(sec.start + p), kind="call" if buf[p] == 0xE8 else "jmp", section=sec.name))
        for match in re.finditer(b"\x0f[\x80-\x8f]", buf):
            p = match.start()
            if p + 6 <= len(buf):
                target = (sec.start + p + 6 + struct.unpack_from("<i", buf, p + 2)[0]) & 0xFFFFFFFF
                if target in result:
                    result[target].append(dict(site=hex(sec.start + p), kind="conditional", section=sec.name))
        for target in targets:
            if sec.start <= target < sec.start + len(buf):
                for va in range(max(sec.start, target - 129), min(sec.start + len(buf) - 1, target + 128)):
                    p = va - sec.start
                    if (buf[p] in (0xEB, 0xE0, 0xE1, 0xE2, 0xE3, *range(0x70, 0x80))
                            and va + 2 + struct.unpack_from("<b", buf, p + 1)[0] == target):
                        result[target].append(dict(site=hex(va), kind="rel8_candidate", section=sec.name))
            pattern = struct.pack("<I", target)
            p = buf.find(pattern)
            while p != -1:
                result[target].append(dict(site=hex(sec.start + p), kind="absolute", section=sec.name))
                p = buf.find(pattern, p + 1)
    return result


def inventory(payload):
    image = XbeImage(payload)
    stub = stock.allocation(payload)["va"] + stock.STUB_OFFSET
    targets = (*CALLS, stub, gun.TOGO_FUNCTION, 0xE92E0, 0x153170, 0x1531F0, 0x17F1D0, 0xAA660)
    refs = references(payload, targets)
    failures = []
    for target, sites in CALLS.items():
        found = {int(row["site"], 16) for row in refs[target] if row["kind"] in ("call", "jmp")}
        if found != set(sites) or any(row["kind"] not in ("call", "jmp") for row in refs[target]):
            failures.append(dict(target=hex(target), expected=list(map(hex, sites)), found=refs[target]))
    if refs[stub] != [dict(site="0x207f99", kind="call", section=".text")]:
        failures.append(dict(target=hex(stub), expected=["0x207f99"], found=refs[stub]))
    return dict(xbe_sha256=hashlib.sha256(payload).hexdigest(), sections_scanned=len(image.sections),
                method=references.__doc__, references={hex(k): v for k, v in refs.items()},
                team_flow={hex(k): v for k, v in TEAM_FLOW.items()}, inventory_failures=failures,
                indirect_limit="No absolute references to the selector/rule entries were found; arbitrary computed or self-modified transfers are not proven absent.")


class CallerFixture(LiveFixture):
    def __init__(self, payload, home, away):
        super().__init__(payload, home, away)
        self.edge_visits = Counter()
        self.team_arguments = Counter()
        self.commit_leaves = Counter()
        self.selector_entries = []
        self.selector_frames = []
        self.m.hook_add(self.ucmod.UC_HOOK_CODE, self.record_rule, begin=0x207EF0, end=0x207EF0)
        for target, sites in CALLS.items():
            for pc in sites:
                self.m.hook_add(self.ucmod.UC_HOOK_CODE, self.edge, begin=pc, end=pc)
        for pc in (0x20B670, 0x20B820):
            self.m.hook_add(self.ucmod.UC_HOOK_CODE, self.selector_entry, begin=pc, end=pc)
        # Completion after the selected record has been produced belongs to
        # the live animation/gameplay controller. Do not fabricate its graph.
        for pc, pop in ((0x9F990, 0), (0xA2A60, 8)):
            def leaf(u, address, size, _, pop=pop):
                self.commit_leaves[hex(address)] += 1
                sp = u.reg_read(self.r.UC_X86_REG_ESP)
                u.reg_write(self.r.UC_X86_REG_EIP, self.get(sp))
                u.reg_write(self.r.UC_X86_REG_ESP, sp + 4 + pop)
            self.m.hook_add(self.ucmod.UC_HOOK_CODE, leaf, begin=pc, end=pc)
        consume = b"\xd9\x1d" + struct.pack("<I", OUT + 0x300) + b"\xc3"
        self.consume = s.SOURCE + 0x25000
        self.m.mem_write(self.consume, consume)

    def edge(self, u, pc, size, _):
        self.edge_visits[hex(pc)] += 1

    def record_rule(self, u, pc, size, _):
        sp = u.reg_read(self.r.UC_X86_REG_ESP)
        self.team_arguments[hex(self.get(sp + 4))] += 1

    def selector_entry(self, u, pc, size, _):
        self.selector_entries.append(dict(pc=hex(pc), team=hex(u.reg_read(self.r.UC_X86_REG_ECX)),
                                          output=hex(u.reg_read(self.r.UC_X86_REG_EDX))))
        self.selector_frames.append((u.reg_read(self.r.UC_X86_REG_ESP), self.registers()))

    def segment(self, start, end):
        self.problem = None
        self.native_start(start, end, count=20000000)
        pc = self.m.reg_read(self.r.UC_X86_REG_EIP)
        if pc != end or self.problem:
            raise RuntimeError(f"segment stopped at {pc:#x}: {self.problem}")

    def regs(self, **values):
        for name, value in values.items():
            self.m.reg_write(getattr(self.r, "UC_X86_REG_" + name.upper()), value)

    def rule_result(self):
        self.put(s.STACK, s.STOP)
        self.regs(esp=s.STACK)
        self.segment(self.consume, s.STOP)
        return bytes(self.m.mem_read(OUT + 0x300, 4)).hex()


def choices(m, team):
    bank = m.get(team + 0x20)
    # Native iterators establish the formation/category/play, not guessed IDs.
    book = m.books[LIVE.index(team)]
    fv = next(bank + ip.FORMATION_BASE + f.index * ip.FORMATION_SIZE for f in book.formations
              if m.get(bank + ip.FORMATION_BASE + f.index * ip.FORMATION_SIZE + 4) & 0xC0000 == 0x80000)
    # These helpers are used only during fixture construction, before the
    # persistent FPU stream starts.
    cv = m.call(0xE1A80, ecx=bank, edx=fv)
    pv = m.call(0xE1320, ecx=bank, edx=fv)
    return bank, cv, fv, pv


def replay_edges(payload, home, away):
    """Every listed direct edge executes its real CALL/JMP and entire callee.

    Caller-frame arguments are reconstructed from the disassembly contract.
    This deliberately does not claim that an entire UI event was replayed.
    """
    rows = []
    targets = dict(CALLS)
    inv = inventory(payload)
    targets[gun.TOGO_FUNCTION] = tuple(int(r["site"], 16) for r in inv["references"][hex(gun.TOGO_FUNCTION)] if r["kind"] == "call")
    targets[0xE92E0] = tuple(int(r["site"], 16) for r in inv["references"]["0xe92e0"] if r["kind"] == "call")
    visits, teams, leaves, commits = (Counter() for _ in range(4))
    errors, bad_weights = [], []
    totals = Counter()
    for target, sites in targets.items():
        # Different routines have different caller-owned state. Reconstruct
        # it at each routine boundary, rather than feed arbitrary standalone
        # routine results into an invented sequence of game events.
        m = CallerFixture(payload, home, away)
        forms = {team: choices(m, team) for team in LIVE}
        m.begin_stream()
        for site in sites:
            for side in (0, 1):
                m.side(side)
                defensive = target in (0x20B400, 0x20B820) or site in (0x11E77A, 0x20B43D, 0x20B453, 0x20B472,
                            0x20B488, 0x20B4F3, 0x20B513, 0x20B595, 0x20B85B, 0x20B8BD, 0x20B8EE)
                team = LIVE[1-side if defensive else side]
                bank, cv, fv, pv = forms[team]
                m.state(mode=0, down=2, distance=6, yard=50)
                args = ()
                regs = dict(ecx=team, edx=OUT)
                float_return = False
                if target == 0x207EF0:
                    args, regs, float_return = (team, cv), dict(edi=fv, eax=int(site == 0x20814B)), True
                elif target == 0x208120:
                    args, regs, float_return = (team, bank), dict(esi=cv), True
                elif target == 0x2081B0:
                    args, regs = (team, 14, 0, 0), dict(ebx=cv)
                elif target == 0x2093F0:
                    # The generic category path also covers 0x2094d7, which
                    # ordinary offense categories reach through 0x209662.
                    args, regs = (0,), dict(ecx=team, edx=0xFFFFFFFF)
                elif target == 0x20A240:
                    args, regs = (0, 0), dict(ecx=team, edx=cv)
                elif target == 0x20B2E0:
                    regs = dict(edi=0)
                elif target == 0x20B400:
                    regs = dict(eax=0)
                elif target == 0x20B5D0:
                    args, regs = (m.get(pv), m.get(pv)), dict(ecx=team, edx=m.get(cv))
                elif target == 0x20B820:
                    args = (0,)
                elif target == gun.TOGO_FUNCTION:
                    regs, float_return = dict(ecx=OUT + 0x200, edx=OUT + 0x210), True
                elif target == 0xE92E0:
                    m.m.mem_write(OUT + 0x200, bytes(m.m.mem_read(s.STATE + 0x10, 32)))
                    args = (0x3F800000,)
                    regs, float_return = dict(ecx=OUT + 0x200, edx=OUT + 0x210), True
                # Native CALL pushes the return address. A tail JMP retains
                # the caller return; supply that one slot only for tail sites.
                tail = XbeImage(payload).read(site, 1) == b"\xe9"
                stack = (s.STOP, *args) if tail else args
                m.m.mem_write(s.STACK - 0x400, bytes(0x800))
                if stack:
                    m.m.mem_write(s.STACK, struct.pack("<" + "I" * len(stack), *stack))
                m.regs(esp=s.STACK, **regs)
                saved, before = m.registers(), fpu(m)
                row = dict(site=hex(site), target=hex(target), offense_side=side, team=hex(team), fixture="reconstructed call-site frame")
                try:
                    m.segment(site, s.STOP if tail else site + 5)
                    expected_sp = s.STACK + 4 * len(stack)
                    if m.m.reg_read(m.r.UC_X86_REG_ESP) != expected_sp or m.registers() != saved:
                        raise RuntimeError("callee ESP/nonvolatile-register imbalance")
                    if float_return:
                        row["float32_hex"] = m.rule_result()
                    if fpu(m) != before:
                        raise RuntimeError(f"x87 imbalance {before} -> {fpu(m)}")
                    row["returned"] = True
                except Exception as exc:
                    row.update(returned=False, error=str(exc), fault=m.problem)
                    rows.append(row)
                    return dict(rows=rows, failed=True, inventory=inv)
                rows.append(row)
        visits.update(m.edge_visits); teams.update(m.team_arguments)
        leaves.update(m.environment_calls); commits.update(m.commit_leaves)
        errors.extend(m.rule_errors); bad_weights.extend(m.bad_weights)
        totals.update(stub_calls=m.stub_calls, togo_calls=m.togo_calls, bad_bin_reads=m.bad_bin_reads)
        print(f"edges {target:#x}: {len(sites)*2} returns", flush=True)
    return dict(rows=rows, failed=False, inventory=inv, visited_edges=dict(visits),
                rule_team_arguments=dict(teams), rule_balance_errors=errors,
                bad_weights=bad_weights, **totals, final_fpu=fpu(m),
                leaves=dict(leaves), commit_leaves=dict(commits))


def replay_selector_callers(payload, home, away):
    """Native argument setup, each external selector entry, and full selection."""
    m = CallerFixture(payload, home, away)
    m.begin_stream()
    ui = s.SOURCE + 0x26000
    rows = []
    for target in (0x20B670, 0x20B820):
        for site in CALLS[target]:
            for side in (0, 1):
                bins = ((1, 10), (2, 2), (2, 6), (2, 11), (3, 2), (3, 5), (3, 10)) if target == 0x20B670 else ((2, 6),)
                for down, distance in bins:
                    m.side(side)
                    team = LIVE[side if target == 0x20B670 else 1-side]
                    # Cached-choice creation is gated to modes >=4 (or mode 1)
                    # in the retail callers. Use franchise mode for those two.
                    mode = 7 if site in (0x15323F, 0x154D34) else 0
                    m.state(mode=mode, down=down, distance=distance, yard=50)
                    m.put(0xBD8080, 0)
                    m.put(0xE600CC, 1); m.put(0xE600C8, 1)
                    m.put(0xE601D4, 0)
                    for live in LIVE:
                        m.put(live + 0x38, 0)
                    m.m.mem_write(ui, bytes(0x200))
                    m.put(ui + 0x38, team)
                    m.put(ui + 0xC, int(target == 0x20B820))
                    m.m.mem_write(s.STACK - 0x400, bytes(0x800))
                    m.put(s.STACK, s.STOP)
                    m.regs(esp=s.STACK, ecx=team, edx=OUT, esi=team, ebp=team, eax=0, ebx=0)
                    blocks = []
                    if site in (0xAA7CA, 0xAA67E):
                        m.regs(esi=ui); blocks = [(0xAA660, site+5)]
                    elif site == 0xA2E84:
                        blocks = [(0xA2E5A, site+5)]
                    elif site == 0x129ECE:
                        blocks = [(0x129EC6, site+5)]
                    elif site == 0x1531BB:
                        blocks = [(0xA2AD3, 0xA2AD9), (0x153170, 0x15317C), (0x1531B7, site+5)]
                    elif site == 0x15323F:
                        blocks = [(0x72829, 0x7282F), (0x1531F0, s.STOP)]
                    elif site == 0x153ADD:
                        blocks = [(0x153AD5, site+5)]
                    elif site == 0x154D34:
                        m.regs(esi=ui); blocks = [(0x154CF5, site+5)]
                    elif site == 0x17F7AC:
                        m.regs(ecx=OUT + 0x100, edx=OUT + 0x104)
                        blocks = [(0x17F1D0, 0x17F1EE), (0x17F745, site+5)]
                    elif site == 0xA2EC5:
                        m.regs(esi=3); blocks = [(0xA2E9F, site+5)]
                    elif site == 0xA3436:
                        # ESI is the saved defense pointer in the outer frame;
                        # the shipped MyCareer thunk supplies the stack arg.
                        blocks = [(0x14E8436, site+5)]
                    elif site == 0x152C27:
                        blocks = [(0x152C1E, site+5)]
                    elif site == 0x1531E2:
                        blocks = [(0x1531DC, site+5)]
                    elif site == 0x17E335:
                        blocks = [(0x17DFC0, 0x17DFDA), (0x17E002, 0x17E003), (0x17E329, site+5)]
                    elif site == 0xB8C81:
                        blocks = [(0xB8C71, s.STOP)]
                    before = fpu(m)
                    old_count = len(m.selector_entries)
                    old_stub = m.stub_calls
                    row = dict(site=hex(site), target=hex(target), side=side, mode=mode, down=down, distance=distance,
                               blocks=[[hex(a), hex(b)] for a, b in blocks])
                    try:
                        for a, b in blocks:
                            m.segment(a, b)
                        entries = m.selector_entries[old_count:]
                        if len(entries) != 1 or entries[0]["team"] != hex(team):
                            raise RuntimeError(f"unexpected selector arguments: {entries}")
                        entry_sp, entry_regs = m.selector_frames[-1]
                        if (m.m.reg_read(m.r.UC_X86_REG_ESP) != entry_sp + (8 if target == 0x20B820 else 4)
                                or m.registers() != entry_regs):
                            raise RuntimeError("selector ESP/nonvolatile-register imbalance")
                        if fpu(m) != before:
                            raise RuntimeError(f"x87 imbalance {before} -> {fpu(m)}")
                        output = int(entries[0]["output"], 16) or m.get(team + 0xC) + 4
                        row.update(returned=True, entry=entries[0], output_hex=bytes(m.m.mem_read(output, 16)).hex(),
                                   stub_calls=m.stub_calls-old_stub)
                    except Exception as exc:
                        row.update(returned=False, error=str(exc), fault=m.problem)
                        rows.append(row)
                        return dict(rows=rows, failed=True)
                    rows.append(row)
            print(f"caller {site:#x}: both sides, {len(bins)} situations returned", flush=True)
    return dict(rows=rows, failed=False, rule_team_arguments=dict(m.team_arguments),
                rule_balance_errors=m.rule_errors, bad_weights=m.bad_weights, bad_bin_reads=m.bad_bin_reads,
                stub_calls=m.stub_calls, togo_calls=m.togo_calls, final_fpu=fpu(m),
                commit_leaves=dict(m.commit_leaves))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input-dir", type=Path, required=True)
    ap.add_argument("--xbe", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--part", choices=("inventory", "edges", "callers"), default="callers")
    args = ap.parse_args()
    payload = (args.xbe or args.input_dir / "default.xbe").read_bytes()
    if args.part == "inventory":
        result = inventory(payload)
    else:
        result = (replay_edges if args.part == "edges" else replay_selector_callers)(
            payload, (args.input_dir / "BAL.play").read_bytes(), (args.input_dir / "PHI.play").read_bytes())
    result["xbe_sha256"] = hashlib.sha256(payload).hexdigest()
    result["gameplay_witness"] = False
    failed = bool(result.get("failed") or result.get("inventory_failures")
                  or result.get("inventory", {}).get("inventory_failures")
                  or result.get("rule_balance_errors") or result.get("bad_weights")
                  or result.get("bad_bin_reads"))
    result["failed"] = failed
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(part=args.part, rows=len(result.get("rows", [])), failed=failed, out=str(args.out))))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
