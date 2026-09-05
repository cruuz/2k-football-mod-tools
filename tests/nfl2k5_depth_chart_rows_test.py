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
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from mod_editor.core import nfl2k5_bump_strength as strength
from mod_editor.core import nfl2k5_depth_chart_rows as rows
from mod_editor.core import nfl2k5_depth_chart_storage as storage
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
    # Synthetic final section, with no private retail bytes. Only the test's
    # content hash is overridden; production still pins the real .XTLID data.
    buf.extend(bytes(storage.RETAIL_FILE_SIZE - len(buf)))
    table = struct.unpack_from("<I", buf, 0x120)[0] - 0x10000
    struct.pack_into("<5I", buf, table + 21 * 56, storage.RETAIL_FLAGS, storage.SECTION_VA,
                     storage.RETAIL_SIZE, storage.RETAIL_RAW, storage.RETAIL_SIZE)
    struct.pack_into("<I", buf, 0x10C, storage.RETAIL_IMAGE_SIZE)
    for unit, records in ((0, OFFENSE), (3, SPECIALS)):
        for slot, (abbrev, long_name, pos, chain) in enumerate(records):
            put(buf, modern.record_va(unit, slot), modern.slot_text(abbrev, long_name) + struct.pack("<II", pos, chain))
    put(buf, modern.record_va(3, 4), bytes(7 * rows.RECORD_SIZE))
    for site in (*rows.code_sites(), *rows.title_sites()):
        put(buf, site.va, site.befores[0])
    put(buf, rows.TABLE_END_VA, rows.RETAIL_RETURNER_POSITIONS)
    _repin(buf)
    return bytes(buf)


def prepare(payload):
    return pools.apply(modern.apply(edge.apply(payload)[0])[0])[0]


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage_pin = patch.object(storage, "RETAIL_CONTENT_SHA256", hashlib.sha256(bytes(storage.RETAIL_SIZE)).hexdigest())
        cls.storage_pin.start()
        cls.addClassCleanup(cls.storage_pin.stop)
        cls.retail = fixture()
        cls.prepared = prepare(cls.retail)
        cls.patched, cls.receipt = rows.apply(cls.prepared)

    def test_full_table_pin_and_counts(self):
        original = rows._read(self.retail, rows.RETAIL_TABLE_VA, rows.RETAIL_TABLE_SIZE)
        self.assertEqual(hashlib.sha256(original).hexdigest(), rows.RETAIL_TABLE_SHA256)
        self.assertEqual(rows.status(self.retail), "retail")
        self.assertEqual(modern.SLOTS_PER_UNIT, 11)
        self.assertEqual(modern.layout_stride(self.patched), 11)
        self.assertEqual(rows.ROW_COUNTS, (11, 11, 11, 13))
        self.assertEqual(rows.TABLE_END_VA, 0x514D38)
        self.assertEqual(rows._read(self.patched, rows.TABLE_END_VA, 24), rows.RETAIL_RETURNER_POSITIONS)
        self.assertEqual(rows._read(self.prepared, rows.RETAIL_TABLE_VA, rows.RETAIL_TABLE_SIZE),
                         rows._read(self.patched, rows.RETAIL_TABLE_VA, rows.RETAIL_TABLE_SIZE))
        self.assertEqual([len(u) for u in modern.read_units(self.retail).values()], [11, 11])
        self.assertEqual([len(u) for u in modern.read_units(self.patched).values()], [11, 11])
        with self.assertRaises(modern.ModernPositionsError):
            modern.record_va(3, 5, 13)  # obsolete unit stride
        for site in rows.title_sites():
            self.assertEqual(rows._read(self.patched, site.va, len(site.after)), site.after)

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
        self.assertEqual(len(self.patched) - len(self.prepared), storage.FILE_SIZE - storage.RETAIL_FILE_SIZE)
        self.assertLessEqual(diff, allowed)
        self.assertEqual(len(diff) + self.receipt["file_growth"], self.receipt["changed_bytes"])
        self.assertEqual(self.patched[storage.TABLE_RAW + storage.TABLE_SIZE:], bytes(storage.FILE_SIZE - storage.TABLE_RAW - storage.TABLE_SIZE))
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
            for site in (*rows.code_sites(), *rows.title_sites()):
                # Corrupt opcode, interior and final bytes, including whole-block pins.
                for delta in {0, len(site.after) // 2, len(site.after) - 1}:
                    broken = bytearray(payload)
                    broken[modern._offset(broken, site.va) + delta] ^= 0x40
                    self.assertEqual(rows.status(bytes(broken)), "foreign", (site.label, delta))
                    with self.assertRaises(rows.DepthChartRowsError):
                        rows.apply(bytes(broken))
        for va, size in ((0x243AED, 7), (rows.COUNT_VA, len(rows.RETAIL_COUNT))):
            broken = bytearray(self.prepared)
            put(broken, va, rows._read(self.patched, va, size))
            self.assertEqual(rows.status(bytes(broken)), "foreign")

    def test_table_padding_pool_fields_boundary_and_truncation_refuse(self):
        for payload in (self.prepared, self.patched):
            table_va, records = (rows.RETAIL_TABLE_VA, 44) if payload is self.prepared else (rows.TABLE_VA, 46)
            for index in range(records):
                for delta in (8, 62, 67, 71):
                    broken = bytearray(payload)
                    broken[modern._offset(broken, table_va) + index * 72 + delta] ^= 0x80
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
        # Label toggles after relocation touch the live copy. The retired
        # original records remember the labels present when it was copied.
        allowed = set(range(modern._offset(self.patched, rows.RETAIL_TABLE_VA),
                            modern._offset(self.patched, rows.TABLE_END_VA)))
        sec = strength._section_for_offset(strength._sections(self.patched), modern._offset(self.patched, rows.RETAIL_TABLE_VA))
        allowed.update(range(sec.header_offset + 36, sec.header_offset + 56))
        for payload in finals:
            self.assertLessEqual({i for i, (a, b) in enumerate(zip(payload, self.patched)) if a != b}, allowed)

    def test_storage_and_titles_are_pinned_and_obsolete_layout_refuses(self):
        for payload in (self.prepared, self.patched):
            for off in (storage.RETAIL_RAW, storage.RETAIL_RAW + storage.RETAIL_SIZE,
                        storage._section(payload).header_offset, 0x10C):
                broken = bytearray(payload)
                broken[off] ^= 1
                self.assertEqual(rows.status(bytes(broken)), "foreign")
        broken = bytearray(self.prepared)
        put(broken, modern.STRIDE_INSTRUCTION_VA, bytes.fromhex("6bc00d"))
        self.assertEqual(rows.status(bytes(broken)), "foreign")

    def test_disc_growth_relinks_only_xbe_preserves_neighbour_and_replays(self):
        self._disc_storage_case(False)

    def test_disc_growth_rolls_back_a_short_directory_write(self):
        self._disc_storage_case(True)

    def _disc_storage_case(self, fail):
        from nfl2k5_xiso_fixture import dir_node, xiso
        from mod_editor.core import platform_compat as io
        root = dir_node([(64, len(self.prepared), 0x80, "default.xbe"),
                         (64 + len(self.prepared) // 2048, 8, 0x80, "neighbour")])
        image = bytearray(64 * 2048 + len(self.prepared) + 2048)
        image[0x10000:0x10014] = image[0x107EC:0x10800] = xiso.XDVDFS_MAGIC
        struct.pack_into("<II", image, 0x10014, 33, len(root))
        image[33 * 2048:33 * 2048 + len(root)] = root
        image[64 * 2048:64 * 2048 + len(self.prepared)] = self.prepared
        image[-2048:-2040] = b"KEEPTHIS"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "copy.iso"
            path.write_bytes(image)
            fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                if fail:
                    real_write = io.pwrite
                    failed = False

                    def short_directory(descriptor, data, offset):
                        nonlocal failed
                        if len(data) == 8 and not failed:
                            failed = True
                            real_write(descriptor, data[:3], offset)
                            return 3
                        return real_write(descriptor, data, offset)

                    with patch.object(io, "pwrite", side_effect=short_directory):
                        with self.assertRaisesRegex(ValueError, "short SPECIAL"):
                            storage.write_image_xbe(fd, self.patched)
                    self.assertEqual(path.read_bytes(), image)
                else:
                    receipt = storage.write_image_xbe(fd, self.patched)
                    self.assertTrue(receipt["relocated"])
                    self.assertEqual(xiso.xbe_extent(fd, os.fstat(fd).st_size), (receipt["offset"], len(self.patched)))
                    updated = path.read_bytes()
                    self.assertEqual(updated[receipt["offset"]:], self.patched)
                    changed = {i for i, (a, b) in enumerate(zip(image, updated)) if a != b}
                    self.assertLessEqual(changed, set(range(receipt["directory_offset"], receipt["directory_offset"] + 8)))
                    self.assertFalse(storage.write_image_xbe(fd, self.patched)["relocated"])
                    self.assertEqual(path.read_bytes(), updated)
            finally:
                os.close(fd)

    def test_modern_labels_can_be_written_on_expanded_pools(self):
        buf = bytearray(self.patched)
        for site in modern.selected_sites():
            put(buf, site.va_for(11, rows.TABLE_VA), modern.slot_text(*site.before[0]))
        _repin(buf)
        self.assertEqual(modern.status(bytes(buf)), "retail")
        self.assertEqual(rows.status(bytes(buf)), "applied")
        renamed, _ = modern.apply(bytes(buf))
        self.assertEqual(renamed, self.patched)
        self.assertEqual(pools.status(renamed), "applied")


@unittest.skipUnless(XBE.is_file(), "private retail ESPN NFL 2K5 (USA)/default.xbe not present")
class RetailTests(unittest.TestCase):
    def test_reservation_recorder_accounts_for_every_appended_byte(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        from mod_editor.core.nfl2k5_cave_oracle import ReservationManifest, XbeImage, MANIFEST_SCHEMA
        prepared = prepare(XBE.read_bytes())
        patched, receipt = rows.apply(prepared)
        recorder = Recorder(prepared)
        recorder.observe(rows, "apply", prepared, patched, receipt)
        spans = recorder.finish(patched)
        # In-memory ownership fixture only; the distributed manifest is never
        # regenerated or replaced by this test.
        doc = {"schema": MANIFEST_SCHEMA, "retail_sha256": hashlib.sha256(prepared).hexdigest(),
               "complete": True, "stack_image_size": XbeImage(patched).image_size, "spans": spans}
        manifest = ReservationManifest(doc, XbeImage(prepared))
        self.assertTrue(manifest.overlaps(rows.TABLE_VA, rows.TABLE_VA + rows.TABLE_SIZE))
        self.assertTrue(all(recorder.covered[len(prepared):]))

    def test_all_retail_table_constants_are_accounted_for(self):
        retail = XBE.read_bytes()
        for field, expected in ((0, 2), (10, 1), (64, 7), (68, 8)):
            word = struct.pack("<I", rows.RETAIL_TABLE_VA + field)
            hits = [i for i in range(len(retail) - 3) if retail[i:i + 4] == word]
            self.assertEqual(len(hits), expected, field)
            covered = [(site.va, site.va + len(site.after)) for site in rows.code_sites()]
            self.assertTrue(all(any(a <= off + 0x10000 < b for a, b in covered) for off in hits))

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
        self.assertEqual(rows._read(patched, 0x243AB0, 5), bytes.fromhex("b80d000000"))
        self.assertEqual(rows._read(patched, 0x243AB7, 5), bytes.fromhex("b80b000000"))

    def test_retail_pins_composition_and_shared_xbe_pass_replay(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        retail = XBE.read_bytes()
        self.assertEqual(hashlib.sha256(retail).hexdigest(), "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9")
        for site in rows.code_sites():
            self.assertEqual(rows._read(retail, site.va, len(site.after)), site.befores[0], site.label)
        patched, receipt = rows.apply(prepare(retail))
        self.assertEqual(receipt["sections_repinned"], [0, 14, 21])
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
        uc.mem_protect(rows.TABLE_VA, 0x1000, UC_PROT_READ)
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
                self.assertEqual(ptr, modern.record_va(unit, slot, table_va=rows.TABLE_VA))
                self.assertNotEqual(bytes(uc.mem_read(ptr, 2)), b"\0\0")
        self.assertEqual(self.call(uc, 0x243AC0, ecx=1, edx=4), 0xE88994)
        self.assertEqual(self.call(uc, 0x243B00, ecx=1, edx=4), 0xE88994)

    def test_summary_and_detail_lists_include_only_valid_shifted_rows(self):
        from unicorn import x86_const as x
        for count in (0, 1, 2, 3, 7, 8, 9):
            players = [(p, i, {0: 2, 1: 0, 2: 1}.get(i, i)) for p in (3, 4, 7, 12) for i in range(count)]
            uc = self.boot(players)
            # The screen entry at 0x2439B0 invokes this retail compactor before
            # showing rows. In particular, a two-player side list starts with a
            # hole (side 2/0); compaction makes its indices dense (1/0).
            self.call(uc, 0x243790, ecx=self.TEAM, limit=1000000)
            for unit, slot, _abbr, _long, pos, chain in rows.ROLE_ROWS:
                self.unit(uc, unit, slot)
                self.call(uc, 0x243D20, ecx=self.TEAM + 0x8000, until=0x243E2C)
                actual_count = struct.unpack("<I", uc.mem_read(pools.DC_ROWS_VA, 4))[0]
                self.assertEqual(actual_count, max(0, count - (chain >> 1)))
                self.assertEqual(uc.reg_read(x.UC_X86_REG_EDX), modern.record_va(unit, slot, table_va=rows.TABLE_VA) + 10)
                for row in range(actual_count):
                    got = self.lookup(uc, row, pos, chain)
                    self.assertNotEqual(got, 0, (count, unit, slot, row))
                    self.assertEqual(got, self.lookup(uc, row + (chain >> 1), pos, chain & 1))
                for column in range(1, 7):
                    got = self.call(uc, 0x242C00, ecx=column, edx=slot)
                    self.assertEqual(got, self.lookup(uc, (column - 1) // 2, pos, chain))

    def test_native_on_field_picker_matches_role_view_and_skips_an_assigned_player(self):
        # Exercise the real e8790 picker, e7530 ordinal decoder, e7810 list
        # reader, e7580 dedup and e8340 starter gate. No calls are stubbed.
        # The lineup context contains dense synthetic rank/side lists; this
        # isolates selection from the separately unwitnessed lineup builder.
        players = [(p, i, (i + 3) % 6) for p in (3, 4, 7, 12) for i in range(6)]
        uc = self.boot(players)
        context, lists, assigned = self.TEAM + 0x8000, self.TEAM + 0x9000, self.TEAM + 0x9800
        uc.mem_write(context, struct.pack("<II", self.TEAM, 0))
        kinds = {3: 9, 4: 18, 7: 10, 12: 6}
        channels = {1: (7, 1), 4: (3, 1), 5: (3, 2), 10: (12, 1), 21: (4, 1), 22: (4, 2)}
        cursor = lists
        for channel in range(29):
            uc.mem_write(context + 0x9C + channel * 4, struct.pack("<I", cursor))
            if channel in channels:
                position, field = channels[channel]
                indices = sorted((i for i, p in enumerate(players) if p[0] == position), key=lambda i: players[i][field])
                uc.mem_write(cursor, bytes(indices))
                cursor += len(indices)
        uc.mem_write(cursor, b"\xff")  # empty returner list sentinel
        uc.mem_write(0xAC26B8, bytes(4))  # no saved formation substitution
        for unit, slot, abbreviation, _name, pos, chain in rows.ROLE_ROWS:
            ordinal = chain >> 1 if pos in (7, 12) else chain
            expected = self.lookup(uc, 0, pos, chain)
            self.assertNotEqual(expected, 0)
            args = (0, 0, assigned, 0, 0, kinds[pos], ordinal)
            got = self.call(uc, 0xE8790, ecx=context, edx=0, stack=args, limit=50000)
            self.assertEqual(got, expected, abbreviation)
            uc.mem_write(assigned, struct.pack("<I", expected))
            args = (0, 0, assigned, 1, 0, kinds[pos], ordinal)
            got = self.call(uc, 0xE8790, ecx=context, edx=0, stack=args, limit=50000)
            self.assertEqual(got, self.lookup(uc, 1, pos, chain), abbreviation)

    def test_all_detail_selection_getters_use_expanded_record_and_encoded_chain(self):
        players = [(p, i, (i + 3) % 6) for p in (3, 4, 7, 12) for i in range(6)]
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
        for unit, slot in ((0, 3), (0, 4), *((u, s) for u, s, *_ in rows.ROLE_ROWS)):
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
        for unit, slot in ((0, 3), (0, 4), *((u, s) for u, s, *_ in rows.ROLE_ROWS)):
            chain = modern.read_record(self.patched, unit, slot)["chain"]
            for display_row in (5, 6, 7, 8):
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
        # SPECIAL bypasses the ordinary duplicate-starter warning, as retail
        # already did for KR/PR. GUNR and DCB intentionally share a list view.
        uc = self.boot([(4, 0, 0), (4, 1, 1)])
        self.unit(uc, 3)
        self.call(uc, 0x243B50, ecx=self.TEAM + 0x8000)


if __name__ == "__main__":
    unittest.main()
