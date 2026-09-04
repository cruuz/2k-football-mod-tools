"""Tier 2 layout, composition, refusal gates, and bounded native-code checks.

No game or GUI is launched. Private-XBE tests skip when the extraction is
absent; all fixture/status/composition checks also run without game files.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from mod_editor.core import nfl2k5_bump_strength as strength
from mod_editor.core import nfl2k5_depth_chart_rows as rows
from mod_editor.core import nfl2k5_edge_rename as edge
from mod_editor.core import nfl2k5_modern_positions as modern
from mod_editor.core import nfl2k5_position_pools as pools
from nfl2k5_position_pools_test import build_synthetic_xbe as pool_fixture, _repin

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None
OFFENSE = (("QB", "QUARTERBACK", 0, 0), ("HB", "HALF BACK", 7, 0), ("FB", "FULL BACK", 8, 0),
           ("LWR", "LEFT WIDE RECEIVER", 3, 0), ("RWR", "RIGHT WIDE RECEIVER", 3, 1),
           ("TE", "TIGHT END", 9, 0), ("LT", "LEFT TACKLE", 14, 0), ("LG", "LEFT GUARD", 13, 0),
           ("C", "CENTER", 12, 0), ("RG", "RIGHT GUARD", 13, 1), ("RT", "RIGHT TACKLE", 14, 1))
SPECIALS = (("KR", "KICK RETURN", 254, 0), ("PR", "PUNT RETURN", 253, 0),
            ("K", "KICKER", 1, 0), ("P", "PUNTER", 2, 0))


def put(buf, va, raw):
    off = modern._offset(buf, va)
    buf[off:off + len(raw)] = raw


def fixture():
    buf = bytearray(pool_fixture())
    for unit, records in ((0, OFFENSE), (3, SPECIALS)):
        for slot, (abbrev, long_name, pos, chain) in enumerate(records):
            put(buf, modern.record_va(unit, slot), modern.slot_text(abbrev, long_name) + struct.pack("<II", pos, chain))
    put(buf, modern.record_va(3, 4), bytes(7 * rows.RECORD_SIZE))
    for site in rows.code_sites():
        put(buf, site.va, site.befores[0])
    put(buf, rows.TABLE_END_VA, rows.RETAIL_RETURNER_POSITIONS)
    _repin(buf)
    return bytes(buf)


def prepare(payload):
    return pools.apply(modern.apply(edge.apply(payload)[0])[0])[0]


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = fixture()
        cls.prepared = prepare(cls.retail)
        cls.patched, cls.receipt = rows.apply(cls.prepared)

    def test_full_table_pin_and_counts(self):
        original = rows._read(self.retail, rows.TABLE_VA, rows.TABLE_SIZE)
        self.assertEqual(hashlib.sha256(original).hexdigest(), rows.RETAIL_TABLE_SHA256)
        self.assertEqual(rows.status(self.retail), "retail")
        self.assertEqual(modern.SLOTS_PER_UNIT, 11)
        self.assertEqual(modern.layout_stride(self.patched), 13)
        self.assertEqual(rows.ROW_COUNTS, (12, 13, 13, 4))
        self.assertEqual(rows.TABLE_END_VA, 0x514D38)
        self.assertEqual(rows._read(self.patched, rows.TABLE_END_VA, 24), rows.RETAIL_RETURNER_POSITIONS)
        for index in (12, 43):
            self.assertEqual(rows._read(self.patched, rows.TABLE_VA + index * 72, 72), bytes(72))
        self.assertEqual([len(u) for u in modern.read_units(self.retail).values()], [11, 11])
        self.assertEqual([len(u) for u in modern.read_units(self.patched).values()], [13, 13])
        with self.assertRaises(modern.ModernPositionsError):
            modern.record_va(3, 5, 13)  # past the allocation, although slot < stride

    def test_records_preserve_original_order_fields_and_specials(self):
        for unit in range(4):
            for slot in range(11 if unit < 3 else 4):
                before = modern.read_record(self.prepared, unit, slot)
                after = modern.read_record(self.patched, unit, slot)
                for key in ("position", "chain"):
                    self.assertEqual(before[key], after[key])
                if (unit, slot) not in ((0, 3), (0, 4)):
                    self.assertEqual(before["abbreviation"], after["abbreviation"])
                    self.assertEqual(before["long_name"], after["long_name"])
        for unit, slot, abbrev, long_name, position, chain in rows.ROLE_ROWS:
            record = modern.read_record(self.patched, unit, slot)
            self.assertEqual(tuple(record[k] for k in ("abbreviation", "long_name", "position", "chain")),
                             (abbrev, long_name, position, chain))
            self.assertLessEqual(len(abbrev), 4)
        self.assertEqual([modern.read_record(self.patched, 0, s)["abbreviation"] for s in (3, 4)], ["X", "Z"])

    def test_idempotence_digest_and_write_ownership(self):
        repeated, receipt = rows.apply(self.patched)
        self.assertEqual(repeated, self.patched)
        self.assertTrue(receipt["already_applied"])
        self.assertEqual(receipt["changed_bytes"], 0)
        allowed = set()
        for entry in self.receipt["edits"]:
            off = int(entry["file_offset"], 16)
            allowed.update(range(off, off + entry["size"]))
        for section in strength._sections(self.patched):
            if section.raw_size:
                self.assertEqual(section.stored_digest, strength.section_digest(self.patched, section))
            if section.index in self.receipt["sections_repinned"]:
                allowed.update(range(section.header_offset + 36, section.header_offset + 56))
        diff = {i for i, (a, b) in enumerate(zip(self.prepared, self.patched)) if a != b}
        self.assertEqual(len(self.prepared), len(self.patched))
        self.assertLessEqual(diff, allowed)
        self.assertEqual(len(diff), self.receipt["changed_bytes"])
        for mod in (rows, modern, pools, edge):
            self.assertEqual(mod.status(self.patched), "applied")

    def test_rows_alone_and_disabled_third_starter_are_refused(self):
        with self.assertRaisesRegex(rows.DepthChartRowsError, "position_pools"):
            rows.apply(self.retail)
        no_cave = pools.apply(modern.apply(self.retail)[0], depth_chart_third_starter=False)[0]
        with self.assertRaisesRegex(rows.DepthChartRowsError, "position_pools"):
            rows.apply(no_cave)
        for va in (pools.ROW_LOOKUP_SITE_VA, pools.CAVE_VA, pools.TAB_INIT_VA):
            broken = bytearray(self.patched)
            broken[modern._offset(broken, va)] ^= 1
            self.assertEqual(rows.status(bytes(broken)), "foreign")

    def test_every_code_instruction_is_pinned_and_partial_layouts_refuse(self):
        for payload in (self.prepared, self.patched):
            for site in rows.code_sites():
                # Corrupt opcode, interior and final bytes, including whole-block pins.
                for delta in {0, len(site.after) // 2, len(site.after) - 1}:
                    broken = bytearray(payload)
                    broken[modern._offset(broken, site.va) + delta] ^= 0x40
                    self.assertEqual(rows.status(bytes(broken)), "foreign", (site.label, delta))
                    with self.assertRaises(rows.DepthChartRowsError):
                        rows.apply(bytes(broken))
        for va, size in ((rows.TABLE_VA, rows.TABLE_SIZE), (rows.COUNT_VA, len(rows.RETAIL_COUNT))):
            broken = bytearray(self.prepared)
            put(broken, va, rows._read(self.patched, va, size))
            self.assertEqual(rows.status(bytes(broken)), "foreign")

    def test_table_padding_pool_fields_boundary_and_truncation_refuse(self):
        for payload in (self.prepared, self.patched):
            for index in range(44):
                for delta in (8, 62, 67, 71):
                    broken = bytearray(payload)
                    broken[modern._offset(broken, rows.TABLE_VA) + index * 72 + delta] ^= 0x80
                    self.assertEqual(rows.status(bytes(broken)), "foreign", (index, delta))
            broken = bytearray(payload)
            broken[modern._offset(broken, rows.TABLE_END_VA)] ^= 1
            self.assertEqual(rows.status(bytes(broken)), "foreign")
        for cut in (0, 4, 0x120, modern._offset(self.patched, rows.TABLE_END_VA) - 1):
            self.assertEqual(rows.status(self.patched[:cut]), "foreign")

    def test_all_dependency_valid_orders_and_replay(self):
        finals = []
        for order in itertools.permutations((edge, modern, pools, rows)):
            if not order.index(modern) < order.index(pools) < order.index(rows):
                continue
            for optional in (False, True):
                payload = self.retail
                for mod in order:
                    payload, _ = mod.apply(payload, **({"three_four_line": optional} if mod is modern else {}))
                for mod in order:
                    self.assertEqual(mod.status(payload), "applied", (order, optional, mod))
                    # Existing modules intentionally refuse a repeated direct apply;
                    # preset orchestrators skip them when status is applied.
                self.assertEqual(rows.apply(payload)[0], payload)
                finals.append(payload)
        self.assertEqual(len(finals), 8)
        self.assertTrue(all(p == self.patched for p in finals))

    def test_modern_labels_can_be_written_on_expanded_pools(self):
        buf = bytearray(self.patched)
        for site in modern.selected_sites():
            put(buf, site.va_for(13), modern.slot_text(*site.before[0]))
        _repin(buf)
        self.assertEqual(modern.status(bytes(buf)), "retail")
        self.assertEqual(rows.status(bytes(buf)), "applied")
        renamed, _ = modern.apply(bytes(buf))
        self.assertEqual(renamed, self.patched)
        self.assertEqual(pools.status(renamed), "applied")


@unittest.skipUnless(XBE.is_file(), "private retail ESPN NFL 2K5 (USA)/default.xbe not present")
class RetailTests(unittest.TestCase):
    @unittest.skipUnless(HAVE_CAPSTONE, "Capstone required for whole-instruction and table-reader audit")
    def test_whole_instruction_pins_and_all_retail_stride_sites(self):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        retail = XBE.read_bytes()
        patched = rows.apply(prepare(retail))[0]
        # Independent search of the complete retail .text distinguishes the
        # eleven depth-chart uses from six unrelated eleven-player loops.
        sec = strength._sections(retail)[0]
        code = retail[sec.raw_offset:sec.raw_offset + sec.raw_size]
        hits, start = [], 0
        while (off := code.find(bytes.fromhex("6bc00b"), start)) >= 0:
            hits.append(sec.virtual_address + off)
            start = off + 1
        self.assertEqual(set(hits), set(rows.STRIDE_VAS) | {0xF7621, 0xF764C, 0x163936, 0x1D9302, 0x1E2FD4, 0x1E3042})
        for va in set(hits) - set(rows.STRIDE_VAS):
            self.assertEqual(rows._read(retail, va, 3), rows._read(patched, va, 3))
        for site in rows.code_sites():
            for block in (*site.befores, site.after):
                self.assertEqual(sum(i.size for i in md.disasm(block, site.va)), len(block), site.label)
        # Complete mov instructions at the operand addresses named in the brief.
        self.assertEqual(rows._read(patched, 0x243AB0, 5), bytes.fromhex("b804000000"))
        self.assertEqual(rows._read(patched, 0x243AB7, 5), bytes.fromhex("b80d000000"))

    def test_retail_pins_composition_and_shared_xbe_pass_replay(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        retail = XBE.read_bytes()
        self.assertEqual(hashlib.sha256(retail).hexdigest(), "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9")
        for site in rows.code_sites():
            self.assertEqual(rows._read(retail, site.va, len(site.after)), site.befores[0], site.label)
        patched, receipt = rows.apply(prepare(retail))
        self.assertEqual(receipt["sections_repinned"], [0, 12])
        replay, _ = tt._apply_all(patched, None, False, edge_rename=True, scheme_labels=True)
        for mod in (edge, modern, pools, rows):
            self.assertEqual(mod.status(replay), "applied")
        self.assertEqual(rows.apply(replay)[0], replay)
        for section in strength._sections(replay):
            self.assertEqual(section.stored_digest, strength.section_digest(replay, section))


@unittest.skipUnless(XBE.is_file() and HAVE_UNICORN,
                     "private retail default.xbe and Unicorn required for bounded native-code tests")
class ExecutionTests(unittest.TestCase):
    TEAM, STACK, STOP = 0x2000000, 0x7000000, 0x7F00000

    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.patched = rows.apply(prepare(cls.retail))[0]

    def boot(self, players=(), payload=None):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_PROT_READ, UC_PROT_EXEC
        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0, 0x1000000)
        uc.mem_map(self.TEAM, 0x10000)
        uc.mem_map(self.STACK, 0x10000)
        uc.mem_map(self.STOP, 0x1000)
        payload = self.patched if payload is None else payload
        for section in strength._sections(payload):
            if section.raw_size:
                uc.mem_write(section.virtual_address, payload[section.raw_offset:section.raw_offset + section.raw_size])
        # Code pages are actually read-only during execution, including the reused cave.
        text = strength._sections(payload)[0]
        start, end = text.virtual_address, text.virtual_address + text.raw_size
        uc.mem_protect(start & ~0xFFF, (end & ~0xFFF) - (start & ~0xFFF), UC_PROT_READ | UC_PROT_EXEC)
        team = bytearray(0x1F4)
        for i, (position, rank, side) in enumerate(players):
            ptr = self.player(i)
            rec = bytearray(0x54)
            rec[8], rec[0x35], rec[0x50] = 4, position, 100
            struct.pack_into("<H", rec, 0x28, (min(rank, 7) << 10) | (min(side, 7) << 13) | 0x155)
            uc.mem_write(ptr, bytes(rec))
            struct.pack_into("<I", team, i * 4, ptr)
        team[0x11C] = len(players)
        team[0x195:0x197] = bytes((0, min(1, max(0, len(players) - 1))))
        uc.mem_write(self.TEAM, bytes(team))
        uc.mem_write(pools.DC_TEAM_VA, struct.pack("<I", self.TEAM))
        return uc

    def player(self, i):
        return self.TEAM + 0x400 + i * 0x54

    def call(self, uc, entry, *, stack=(), until=None, limit=100000, **registers):
        from unicorn import x86_const as x
        esp = self.STACK + 0x8000
        uc.mem_write(esp, struct.pack(f"<{1 + len(stack)}I", self.STOP, *stack))
        uc.reg_write(x.UC_X86_REG_ESP, esp)
        for name, value in registers.items():
            uc.reg_write(getattr(x, "UC_X86_REG_" + name.upper()), value)
        stop = self.STOP if until is None else until
        uc.emu_start(entry, stop, count=limit)
        self.assertEqual(uc.reg_read(x.UC_X86_REG_EIP), stop, f"instruction budget exhausted at {entry:#x}")
        return uc.reg_read(x.UC_X86_REG_EAX)

    def unit(self, uc, unit, slot=0):
        uc.mem_write(pools.DC_UNIT_VA, struct.pack("<I", unit))
        uc.mem_write(pools.DC_SLOT_VA, struct.pack("<I", slot))

    def lookup(self, uc, row, pos, chain):
        return self.call(uc, 0x242AE0, edx=self.TEAM, stack=(row, pos, chain))

    def test_counts_getters_and_blank_zero_guard(self):
        uc = self.boot()
        for unit, count in enumerate(rows.ROW_COUNTS):
            self.unit(uc, unit)
            self.assertEqual(self.call(uc, rows.COUNT_VA, limit=20), count)
            for slot in range(count):
                ptr = self.call(uc, 0x243AE0, ecx=slot, limit=10)
                self.assertEqual(ptr, modern.record_va(unit, slot, 13))
                self.assertNotEqual(bytes(uc.mem_read(ptr, 2)), b"\0\0")
        for unit, slot in ((0, 12), (3, 4)):
            self.unit(uc, unit)
            for column in range(1, 7):
                self.assertEqual(self.call(uc, 0x242C00, ecx=column, edx=slot, limit=16), 0)
        self.assertEqual(self.call(uc, 0x243AC0, ecx=1, edx=4), 0xE88994)
        self.assertEqual(self.call(uc, 0x243B00, ecx=1, edx=4), 0xE88994)

    def test_summary_and_detail_lists_include_only_valid_shifted_rows(self):
        from unicorn import x86_const as x
        for count in (0, 1, 2, 3, 7, 8, 9):
            players = [(p, i, {0: 2, 1: 0, 2: 1}.get(i, i)) for p in (3, 4) for i in range(count)]
            uc = self.boot(players)
            # The screen entry at 0x2439B0 invokes this retail compactor before
            # showing rows. In particular, a two-player side list starts with a
            # hole (side 2/0); compaction makes its indices dense (1/0).
            self.call(uc, 0x243790, ecx=self.TEAM, limit=1000000)
            for unit, slot, _abbr, _long, pos, chain in rows.ROLE_ROWS:
                self.unit(uc, unit, slot)
                self.call(uc, 0x243D20, ecx=self.TEAM + 0x8000, until=0x243E2C)
                actual_count = struct.unpack("<I", uc.mem_read(pools.DC_ROWS_VA, 4))[0]
                self.assertEqual(actual_count, max(0, count - 1))
                self.assertEqual(uc.reg_read(x.UC_X86_REG_EDX), modern.record_va(unit, slot, 13) + 10)
                for row in range(actual_count):
                    got = self.lookup(uc, row, pos, chain)
                    self.assertNotEqual(got, 0, (count, unit, slot, row))
                    self.assertEqual(got, self.lookup(uc, row + 1, pos, chain & 1))
                for column in range(1, 7):
                    got = self.call(uc, 0x242C00, ecx=column, edx=slot)
                    self.assertEqual(got, self.lookup(uc, (column - 1) // 2, pos, chain))

    def test_all_detail_selection_getters_use_expanded_record_and_encoded_chain(self):
        players = [(p, i, (i + 3) % 6) for p in (3, 4) for i in range(6)]
        uc = self.boot(players)
        paths = ((0x242D10, 0x242D48), (0x242E00, 0x242E3C), (0x243514, 0x24353E),
                 (0x2436D6, 0x24370E), (0x244284, 0x2442C3))
        for unit, slot, _a, _l, pos, chain in rows.ROLE_ROWS:
            self.unit(uc, unit, slot)
            uc.mem_write(0xC17480, struct.pack("<I", 1))  # scrolled row base
            uc.mem_write(0xC1747C, struct.pack("<I", 0))
            expected = self.lookup(uc, 1, pos, chain)
            for entry, stop in paths:
                # 0x243514 begins after adding the scroll base; others load it themselves.
                got = self.call(uc, entry, until=stop, ecx=1 if entry == 0x243514 else 0,
                                edx=0, esi=slot, edi=self.TEAM + 0x8000)
                self.assertEqual(got, expected, (hex(entry), unit, slot))

    def test_swap_path_changes_only_the_correct_chain_field(self):
        for unit, slot in ((0, 3), (0, 4), (0, 11), (1, 11), (1, 12), (2, 11), (2, 12)):
            uc = self.boot([(3, 1, 2), (3, 4, 5)])
            self.unit(uc, unit, slot)
            record = modern.read_record(self.patched, unit, slot)
            before = [struct.unpack("<H", uc.mem_read(self.player(i) + 0x28, 2))[0] for i in range(2)]
            self.call(uc, 0x2442E8, until=0x244308, ecx=self.player(0), esi=self.player(1), edi=self.TEAM)
            after = [struct.unpack("<H", uc.mem_read(self.player(i) + 0x28, 2))[0] for i in range(2)]
            mask = 0xE000 if record["chain"] & 1 else 0x1C00
            self.assertEqual(after, [(before[i] & ~mask) | (before[1 - i] & mask) for i in range(2)])

    def test_bench_threshold_bit_mask_confirmation_and_stack(self):
        from unicorn import UC_HOOK_CODE, x86_const as x
        for unit, slot in ((0, 3), (0, 4), (0, 11), (1, 11), (1, 12)):
            chain = modern.read_record(self.patched, unit, slot)["chain"]
            for display_row in (6, 7, 8):
                for answer in (0, 1):
                    uc = self.boot([(3, 7, 7)])
                    self.unit(uc, unit, slot)
                    calls = []

                    def intercept(machine, address, _size, _data):
                        if address not in (0x14E540, 0x243790):
                            return
                        calls.append(address)
                        if address == 0x14E540:
                            self.assertEqual(machine.reg_read(x.UC_X86_REG_ECX), 0x12345678)
                        sp = machine.reg_read(x.UC_X86_REG_ESP)
                        ret = struct.unpack("<I", machine.mem_read(sp, 4))[0]
                        machine.reg_write(x.UC_X86_REG_ESP, sp + 4)
                        machine.reg_write(x.UC_X86_REG_EAX, answer)
                        machine.reg_write(x.UC_X86_REG_EIP, ret)

                    uc.hook_add(UC_HOOK_CODE, intercept)
                    promote = display_row + (chain >> 1) > 7
                    stop = 0x244499 if promote else 0x244478
                    before = struct.unpack("<H", uc.mem_read(self.player(0) + 0x28, 2))[0]
                    eax = self.call(uc, rows.BENCH_VA, eax=display_row, ecx=0, esi=self.player(0), edi=self.TEAM,
                                    stack=(0, 0, 0, 0, 0, 0x12345678), until=stop, limit=100)
                    self.assertEqual(uc.reg_read(x.UC_X86_REG_ESP), self.STACK + 0x8000)
                    after = struct.unpack("<H", uc.mem_read(self.player(0) + 0x28, 2))[0]
                    if promote and answer:
                        mask, value = (0xE000, 5 << 13) if chain & 1 else (0x1C00, 5 << 10)
                        self.assertEqual(after, (before & ~mask) | value)
                        self.assertEqual(calls, [0x14E540, 0x243790])
                    else:
                        self.assertEqual(after, before)
                        self.assertEqual(calls, [0x14E540] if promote else [])
                        if not promote:
                            self.assertEqual(eax, display_row)  # saved selection uses UI-relative index

    def test_specials_counts_and_lookup_match_retail(self):
        players = [(p, i, i) for p in (8, 7, 3, 4, 6, 5, 1, 2) for i in range(2)]
        old, new = self.boot(players, self.retail), self.boot(players)
        for slot in range(4):
            for uc in (old, new):
                self.unit(uc, 3, slot)
                self.call(uc, 0x243D20, ecx=self.TEAM + 0x8000, until=0x243E2C)
            self.assertEqual(old.mem_read(pools.DC_ROWS_VA, 4), new.mem_read(pools.DC_ROWS_VA, 4))
            for column in range(1, 7):
                self.assertEqual(self.call(old, 0x242C00, ecx=column, edx=slot),
                                 self.call(new, 0x242C00, ecx=column, edx=slot))

    def test_duplicate_warning_ignores_role_aliases_but_keeps_original_starter_check(self):
        from unicorn import UC_HOOK_CODE
        # X rank0 != Z side0; SLOT rank1 deliberately aliases Z. New aliases must
        # not trigger the duplicate warning every time the screen opens.
        uc = self.boot([(3, 0, 2), (3, 1, 0), (3, 2, 1)])
        self.unit(uc, 0)
        visited = []
        uc.hook_add(UC_HOOK_CODE, lambda _uc, va, _s, _u: visited.append(va) if va == 0x243BEB else None)
        self.call(uc, 0x243B50, ecx=self.TEAM + 0x8000)
        self.assertEqual(visited, [])
        # A true X/Z duplicate still enters the same retail warning path.
        uc = self.boot([(3, 0, 0), (3, 1, 1)])
        self.unit(uc, 0)
        self.call(uc, 0x243B50, ecx=self.TEAM + 0x8000, until=0x243BEB)


if __name__ == "__main__":
    unittest.main()
