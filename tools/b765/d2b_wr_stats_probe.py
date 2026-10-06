#!/usr/bin/env python3
"""Read-only native receiving-stat production/cache/formatter evidence.

Requires the exact privately extracted retail and SOFTDRINK v0.4 XBEs. The
fixture supplies live record links, empty season records and event/drive rings;
it never seeds the receiving-TD counter. It is not a game or renderer witness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RETAIL_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
V04_SHA256 = "5a9dc534b50c7f13b5124bfff9e39c99f96f62be4cc1de33309895c330c75f29"
LIVE_PLAYERS = (0xB30C4C, 0xB321A0)
LIVE_TEAMS = (0xB30864, 0xB30A58)
EVENT_RING = 0xE53874
EVENT_COUNT = 0xE53804
DRIVE_RING = 0xE57474
WR_SLOT = 10
NATIVE_SPANS = (
    ("receiving_cache_builder", 0x1ED470, 0x33B),
    ("cache_dispatch_and_link", 0x1ECA20, 0xCE),
    ("cache_slot_allocation", 0x1ED9A0, 0xFA),
    ("cache_commit_and_current_event", 0x1EDAA0, 0x11A),
    ("cache_rebuild_and_invalidation", 0x1EDBC0, 0x9B),
    ("all_native_cache_kind_descriptors", 0x50EB78, 13 * 24),
    ("receiving_td_cached_and_fallback_dispatch", 0x24ED00, 0x33),
    ("receiving_td_uncached_event_query", 0x286CD0, 0xAE),
    ("generic_event_query", 0x240FB0, 0xE0),
    ("event_predicate_interpreter", 0x240C40, 0xD0),
    ("ordinary_td_event_predicate", 0x1EA5C0, 0x30),
    ("event_receiver_formatter", 0x1502B0, 0x380),
    ("receiving_today_formatter", 0x25B4E0, 0x250),
    ("stat_callback_registration", 0xCA7B0, 0x30),
    ("touchdown_snapshot_event_flag_producer", 0xCE56F, 0x2F),
    ("live_touchdown_drive_snapshot_writer", 0xCDB63, 0x49),
    ("native_commit_current_event_wrapper", 0x1D32B0, 0xC),
    ("event_stat_resource_callback_dispatch", 0xEBC70, 0x1B),
    ("event_stat_resource_callback_td_arm", 0xEBE23, 0x16),
    ("event_stat_resource_callback_table", 0xEBE50, 18 * 4),
)


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_inputs(retail: bytes, shipped: bytes) -> None:
    if sha(retail) != RETAIL_SHA256 or sha(shipped) != V04_SHA256:
        raise ValueError("Unexpected native evidence input hashes")


class Machine:
    """An empty native RAM fixture with real code, plus explicit object links."""

    STACK = 0x3108000
    STOP = 0x3200000
    OUT = 0x3003000

    def __init__(self, payload: bytes, side: int):
        import unicorn as uc
        from unicorn import x86_const as x
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage

        self.uc_api, self.x = uc, x
        self.image = XbeImage(payload)
        self.uc = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        image_end = max(s.end for s in self.image.sections)
        self.uc.mem_map(0x10000, ((image_end + 4095) & -4096) - 0x10000)
        self.uc.mem_write(0x10000, payload[:self.image.headers_size])
        for section in self.image.sections:
            self.uc.mem_write(section.start, payload[section.raw:section.raw + section.raw_size])
        self.uc.mem_map(0x3000000, 0x300000)
        self.side = side
        self.player = LIVE_PLAYERS[side] + WR_SLOT * 0x54
        self.calls: dict[int, int] = {}
        self.instruction_sizes: dict[int, int] = {}
        self.uc.hook_add(uc.UC_HOOK_CODE, self._trace)
        self.uc.reg_write(x.UC_X86_REG_FPCW, 0x37F)
        self.uc.reg_write(x.UC_X86_REG_FPTAG, 0xFFFF)
        # The real patched reset executes before contexts/caches exist.
        self.run(0x1ECAF0)
        for team_side, base in enumerate(LIVE_PLAYERS):
            for index in range(65):
                ordinal = team_side * 65 + index
                record = base + 0x54 * index
                link = 0x3020000 + ordinal * 0x100
                context = 0x3040000 + ordinal * 0x100
                progress = 0x3060000 + ordinal * 0x100
                self.u32(record + 0x30, link)
                self.u32(link, context)
                self.u32(link + 0x1C, progress)
                self.uc.mem_write(record + 0x34, bytes([team_side + 1]))
                self.uc.mem_write(record + 0x35, bytes([9 if index == WR_SLOT else 1]))
                self.u32(0x30A0000 + team_side * 0x1000 + index * 4,
                         0x30C0000 + ordinal * 0x200)
        for team_side, base in enumerate((0xE5FC20, 0xE5FC60)):
            data = 0x3080000 + 0x1000 * team_side
            self.u32(base + 0x18, data)
            self.u32(base, LIVE_TEAMS[team_side])
            self.u32(LIVE_TEAMS[team_side] + 0x18, data)
        self.u32(0xE5FE68, 0x30A0000)
        self.u32(0xE5FE6C, 0x30A1000)
        self.u32(0xE5FF80, 4)
        self.u32(0xE602C4, 1)
        self.u32(0xE53800, 0)
        self.run(0xCA7B0, args=(0, 0))
        self.count = 0

    def _trace(self, _machine, pc, size, _data):
        self.calls[pc] = self.calls.get(pc, 0) + 1
        self.instruction_sizes[pc] = size

    def u32(self, va: int, value: int) -> None:
        self.uc.mem_write(va, struct.pack("<I", value))

    def read32(self, va: int) -> int:
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def run(self, pc: int, *, ecx=0, edx=0, edi=0, ebx=0, ebp=0, args=(), stop=None) -> int:
        x = self.x
        self.u32(self.STACK, self.STOP)
        for i, value in enumerate(args):
            self.u32(self.STACK + 4 + i * 4, value)
        for reg, value in ((x.UC_X86_REG_ESP, self.STACK), (x.UC_X86_REG_ECX, ecx),
                           (x.UC_X86_REG_EDX, edx), (x.UC_X86_REG_EDI, edi),
                           (x.UC_X86_REG_EBX, ebx), (x.UC_X86_REG_EBP, ebp)):
            self.uc.reg_write(reg, value)
        stop = self.STOP if stop is None else stop
        self.uc.emu_start(pc, stop, count=300000)
        if self.uc.reg_read(x.UC_X86_REG_EIP) != stop:
            raise AssertionError(f"Native instruction budget exhausted at {self.uc.reg_read(x.UC_X86_REG_EIP):#x}")
        return self.uc.reg_read(x.UC_X86_REG_EAX)

    @property
    def context(self):
        return self.read32(self.read32(self.player + 0x30))

    @property
    def cache(self):
        return self.read32(self.context + 0x10)

    def add_event(self, *, kind=2, touchdown=False, receiver_slot=WR_SLOT):
        index = self.count
        drive = index
        receiver_id = 2 + 2 * receiver_slot + self.side
        passer_id = 2 + self.side
        header = kind | (1 << 4) | (drive << 7)
        if touchdown:
            header |= 1 << 28
        event = EVENT_RING + index * 20
        self.u32(event, header)
        self.uc.mem_write(event + 4, b"\x14")  # 20 yards
        self.uc.mem_write(event + 12, bytes([passer_id, receiver_id]))
        self.u32(DRIVE_RING + drive * 4,
                 (self.side << 21) | ((1 if touchdown else 0) << 26))
        self.count += 1
        self.u32(EVENT_COUNT, self.count)
        self.u32(0xE53800, drive)
        return index

    def produce_touchdown_snapshot(self, index):
        # Execute the actual event TD flag producer then the complete phase-4
        # drive snapshot writer. Stop before its caller's later scene callbacks.
        if index != self.count - 1:
            raise ValueError("Snapshot commit only updates the newest event")
        event = EVENT_RING + index * 20
        self.u32(event, self.read32(event) & ~(1 << 28))
        self.u32(DRIVE_RING + index * 4, self.side << 21)
        snapshot = 0xB6E800 + (index % 5) * 0x4B0
        self.u32(snapshot - 0x10, index)
        team = 0xE5FC20 + self.side * 0x40
        for offset, value in ((0, 4), (0x20, team), (0x330, team),
                              (0x354, 1), (0x358, team), (0x35C, self.player)):
            self.u32(snapshot + offset, value)
        self.u32(0xE57674, 0x30F0000)
        self.run(0xCE56F, ebx=index, ebp=0x30F1000, edi=snapshot, stop=0xCE59E)
        if not self.read32(event) & (1 << 28):
            raise AssertionError("Native TD producer did not set event flag")
        if (self.read32(DRIVE_RING + index * 4) >> 26) & 7 != 1:
            raise AssertionError("Native snapshot writer did not set drive TD outcome")

    def commit(self, start=0):
        # Full producer, including cache allocation/append, progress stats,
        # team accounting and actual defensive-try tail. Zero substituted code.
        self.run(0x1EDC60, ecx=start)

    def value(self):
        self.run(0xCB240, ecx=self.player, edx=0x3E, args=(0,))
        scratch = self.STOP + 0x100
        self.uc.mem_write(scratch, b"\xD9\x1D" + struct.pack("<I", self.OUT))
        self.uc.emu_start(scratch, scratch + 6, count=1)
        return struct.unpack("<f", self.uc.mem_read(self.OUT, 4))[0]

    def text(self, index=0):
        self.run(0x150490, ecx=self.OUT, edx=index, args=(0, 2))
        return bytes(self.uc.mem_read(self.OUT, 64)).decode("utf-16-le").split("\0")[0]

    def today(self):
        self.run(0x25B6F0, ecx=self.player, edx=self.OUT, args=(0x40,))
        return bytes(self.uc.mem_read(self.OUT, 128)).decode("utf-16-le").split("\0")[0]

    def resource_td(self, index):
        # Execute the real resource callback and its native jump-table TD arm.
        # This is a field callback witness, not identification of the tester's popup.
        self.u32(0xB9C278, index)
        self.run(0xEBC70, edx=16, args=(self.OUT, 0, 0))
        return bytes(self.uc.mem_read(self.OUT, 64)).decode("utf-16-le").split("\0")[0]

    def snapshot(self, name, expected, *, event_index=0, format_event=True):
        value = self.value()
        text = self.text(event_index) if format_event else None
        resource_td = self.resource_td(event_index) if format_event else None
        if value != expected or (format_event and (text != str(expected) or resource_td != str(expected))):
            raise AssertionError((name, self.side, value, text, resource_td, expected))
        return dict(case=name, side=self.side, expected_receiving_td=expected,
                    native_value=value, native_td_column=text, receiving_today=self.today(),
                    native_resource_td_column=resource_td,
                    native_cache_pointer=hex(self.cache),
                    native_validity=struct.unpack("<f", self.uc.mem_read(self.context + 12, 4))[0],
                    event_count=self.count, substituted_routines=[])


def scenarios(payload: bytes):
    rows, executed = [], {}
    for side in (0, 1):
        for tds in (0, 1, 2, 7):
            m = Machine(payload, side)
            for i in range(max(tds, 1)):
                m.add_event(touchdown=i < tds)
            m.commit()
            rows.append(m.snapshot(f"full_commit_{tds}_td", tds))
            if m.cache and m.uc.mem_read(m.cache + 0x13, 1)[0] != tds:
                raise AssertionError("Native cache receiving counter differs")
            # Actual no-cache fallback scans native events, never a seeded TD count.
            m.u32(m.context + 0x10, 0)
            m.u32(0xAC13D8, 1)
            rows.append(m.snapshot(f"uncached_fallback_{tds}_td", tds))
            executed.update(m.instruction_sizes)
        m = Machine(payload, side)
        first = m.add_event(touchdown=False)
        rows.append(m.snapshot("before_first_commit", 0))
        m.produce_touchdown_snapshot(first)
        rows.append(m.snapshot("td_event_recorded_before_stat_commit", 0))
        m.run(0x1D32B0)
        rows.append(m.snapshot("append_first_td", 1))
        second = m.add_event(touchdown=False)
        m.produce_touchdown_snapshot(second)
        rows.append(m.snapshot("second_td_before_stat_commit", 1, event_index=second))
        m.run(0x1D32B0)
        rows.append(m.snapshot("append_second_td", 2, event_index=second))
        # Remove the first TD flag/drive outcome as a supplied corrected ruling.
        m.u32(EVENT_RING, m.read32(EVENT_RING) & ~(1 << 28))
        m.u32(DRIVE_RING, side << 21)
        m.run(0x1EDBC0, edi=1, args=(m.count,))
        rows.append(m.snapshot("native_rebuild_after_td_retraction", 1))
        # Query another WR after its independent ordinary reception.
        other_index = m.add_event(receiver_slot=WR_SLOT + 1)
        m.commit(other_index)
        old_player = m.player
        m.player += 0x54
        rows.append(m.snapshot("different_receiver_zero_td", 0, event_index=other_index))
        m.player = old_player
        rows.append(m.snapshot("first_receiver_retains_td", 1))
        executed.update(m.instruction_sizes)
        for kind, title in ((1, "rushing_lateral_td"), (4, "interception_td")):
            m = Machine(payload, side)
            m.add_event(kind=kind, touchdown=True)
            m.commit()
            rows.append(m.snapshot(title, 0, format_event=False))
            executed.update(m.instruction_sizes)
    return rows, executed


def proof(retail: bytes, shipped: bytes):
    validate_inputs(retail, shipped)
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    from mod_editor.core import nfl2k5_defensive_try

    ri, si = XbeImage(retail), XbeImage(shipped)
    if nfl2k5_defensive_try.status(shipped) != "applied":
        raise ValueError("Unexpected defensive-try owner")
    spans = []
    for name, va, size in NATIVE_SPANS:
        original, installed = ri.read(va, size), si.read(va, size)
        if original != installed:
            raise AssertionError((name, hex(va)))
        spans.append(dict(name=name, va=hex(va), size=size, identical=True, sha256=sha(original)))
    decoder = Cs(CS_ARCH_X86, CS_MODE_32)
    decoder.skipdata = True
    text = si.sections[0]
    selectors = []
    for pc, _size, mnemonic, operands in decoder.disasm_lite(si.read(text.start, text.raw_size), text.start):
        if mnemonic == "mov" and operands in ("edx, 0x3e", "eax, 0x3e"):
            before, after = ri.read(pc - 64, 192), si.read(pc - 64, 192)
            if before != after:
                raise AssertionError((hex(pc), "Changed receiving TD selector neighborhood"))
            selectors.append(dict(instruction=hex(pc), compared_va=hex(pc - 64), size=192, sha256=sha(before)))
    rows = []
    executed = {}
    for name, payload in (("retail", retail), ("v04", shipped)):
        cases, instructions = scenarios(payload)
        rows.extend(dict(image=name, **case) for case in cases)
        executed.update(instructions)
    changed = []
    for pc, size in sorted(executed.items()):
        if not 0x11000 <= pc < 0x41FF14:
            continue
        a, b = ri.read(pc, size), si.read(pc, size)
        if a != b:
            changed.append(dict(va=hex(pc), size=size, retail=a.hex(), v04=b.hex()))
    return dict(retail_sha256=sha(retail), v04_sha256=sha(shipped),
                identical_complete_spans=spans, identical_selector_neighborhoods=selectors,
                native_scenarios=rows, native_scenario_count=len(rows),
                executed_original_text_instruction_count=sum(0x11000 <= pc < 0x41FF14 for pc in executed),
                changed_executed_original_text_instructions=changed,
                substituted_routines=[], runtime_witnessed=False, mutation_applied=False,
                boundary="Synthetic live object/season links plus event/drive rings. Actual stat reset, stat commit, cache allocation/append/rebuild/invalidation, getter, fallback event scanner, both text formatters and event-stat resource field callback execute. The actual event TD flag producer and complete phase-4 drive snapshot writer execute from supplied scored snapshots in the append cases. Ball/catch/score snapshot creation, exact tester popup identification, frontend save lifecycle, async presentation scheduling and GPU are outside the proof. No TD cache counter is seeded.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-xbe", required=True, type=Path)
    parser.add_argument("--v04-xbe", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Evidence output must be a new path")
    result = proof(args.retail_xbe.read_bytes(), args.v04_xbe.read_bytes())
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS: {result['native_scenario_count']} native stat lifecycle cases; no substituted routines; no gameplay witness")


if __name__ == "__main__":
    main()
