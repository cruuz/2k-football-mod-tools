"""SPECIAL regression: real spreadsheet layout, dispatch and text, without a GPU.

Also runs the original layout/storage/selection suite at its historical path.
The bounded probe constructs cell storage, as the retail allocator would, and
uses the retail LAYT frame and FONT metrics. Only GPU/font-state submission is
stubbed; layout, scrolling, descriptor dispatch, lookup and text formatting run.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tools")]
import nfl2k5_depth_chart_rows_test as legacy
from mod_editor.core import nfl2k5_depth_chart_rows as rows
from mod_editor.core import nfl2k5_modern_positions as modern

# The previous shipped records, independently captured from the branch base.
BEFORE_ROLES = ((3, 4, "SLOT", "SLOT RECEIVER", 3, 2),
                (3, 5, "NCB", "NICKEL CORNER", 4, 2),
                (3, 6, "DCB", "DIME CORNER", 4, 3),
                (3, 7, "GDGT", "GADGET", 3, 4),
                (3, 8, "GUN", "LEFT GUNNER", 3, 3),
                (3, 9, "GUNR", "RIGHT GUNNER", 4, 3),
                (3, 10, "LS", "LONG SNAPPER", 12, 2),
                (3, 11, "3DB", "3RD DOWN BACK", 7, 2),
                (3, 12, "PWR", "POWER BACK", 7, 4))
EXPECTED_ORDER = "KR PR K P LS LGUN RGUN NCB DCB SLWR GAD 3DRB PWRB".split()
EXPECTED_CHAINS = {"LS": (12, 2), "LGUN": (3, 3), "RGUN": (4, 3),
                   "NCB": (4, 2), "DCB": (4, 3), "SLWR": (3, 2),
                   "GAD": (3, 4), "3DRB": (7, 2), "PWRB": (7, 4)}


def before_special(patched):
    """Reconstruct the branch-base table/style; not an accepted apply input."""
    buf = bytearray(patched)
    for unit, slot, short, long, pos, chain in BEFORE_ROLES:
        legacy.put(buf, modern.record_va(unit, slot, table_va=rows.TABLE_VA),
                   modern.slot_text(short, long) + struct.pack("<II", pos, chain))
    legacy.put(buf, rows.SUMMARY_STYLE_VA, rows.RETAIL_SUMMARY_STYLE)
    legacy.put(buf, rows.SUMMARY_LABEL_WIDTH_VA, struct.pack('<f', 50))
    legacy._repin(buf)
    return bytes(buf)


class SpecialContractTests(legacy.LayoutTests):
    # This class intentionally extends the existing portable synthetic tests.
    def test_noahs_order_and_chain_contract_in_preview(self):
        units = modern.read_depth_chart_units(self.patched)
        self.assertEqual([len(v) for v in units.values()], [11, 11, 11, 13])
        self.assertEqual([r['abbreviation'] for r in units['SPECIAL']], EXPECTED_ORDER)
        self.assertEqual({r['abbreviation']: (r['position'], r['chain'])
                          for r in units['SPECIAL'][4:]}, EXPECTED_CHAINS)
        for r in units['SPECIAL']:
            self.assertLessEqual(len(r['long_name']), 26)
        self.assertEqual(len(modern.read_depth_chart_units(self.retail)['SPECIAL']), 4)

    def test_old_and_mixed_special_builds_refuse_without_mutation(self):
        old = before_special(self.patched)
        candidates = [old]
        for source, va, raw in ((old, rows.SUMMARY_STYLE_VA, rows.SUMMARY_STYLE_BYTES),
                               (self.patched, rows.SUMMARY_STYLE_VA, rows.RETAIL_SUMMARY_STYLE)):
            buf = bytearray(source)
            legacy.put(buf, va, raw)
            candidates.append(bytes(buf))
        for payload in candidates:
            snapshot = hashlib.sha256(payload).digest()
            self.assertEqual(rows.status(payload), 'foreign')
            with self.assertRaises(rows.DepthChartRowsError):
                rows.apply(payload)
            self.assertEqual(hashlib.sha256(payload).digest(), snapshot)

    def test_summary_descriptors_and_every_style_byte_are_pinned(self):
        for va, size, _ in rows.SUMMARY_PINS:
            for delta in (0, size // 2, size - 1):
                buf = bytearray(self.patched)
                buf[modern._offset(buf, va) + delta] ^= 1
                self.assertEqual(rows.status(bytes(buf)), 'foreign', (va, delta))
                with self.assertRaises(rows.DepthChartRowsError):
                    rows.apply(bytes(buf))
        for delta in range(48):
            buf = bytearray(self.patched)
            buf[modern._offset(buf, rows.SUMMARY_STYLE_VA) + delta] ^= 1
            self.assertEqual(rows.status(bytes(buf)), 'foreign', delta)


class DrawProbe(unittest.TestCase):
    """Reusable bounded harness, also used by the report's preview renderer."""
    TEAM, STACK, STOP = legacy.ExecutionTests.TEAM, legacy.ExecutionTests.STACK, legacy.ExecutionTests.STOP
    boot = legacy.ExecutionTests.boot
    player = legacy.ExecutionTests.player
    call = legacy.ExecutionTests.call
    unit = legacy.ExecutionTests.unit
    lookup = legacy.ExecutionTests.lookup
    SHEET, CELLS, POINTERS = TEAM + 0x8000, TEAM + 0xA000, TEAM + 0x9000

    def run_draw(self, payload, unit=3, *, spacing=None, names=None, selected=0, pool_count=6,
                 player_rows=None, returners=None):
        from unicorn import UC_HOOK_CODE, x86_const as x
        players = ([(p, i, (i + 3) % pool_count) for p in (0, 1, 2, 3, 4, 7, 8, 9)
                    for i in range(pool_count)] if player_rows is None else player_rows)
        self.assertLessEqual(len(players), 64)
        u = self.boot(players, payload=payload)
        self.unit(u, unit)
        def put(va, fmt, *args):
            u.mem_write(va, struct.pack('<' + fmt, *args))
        def utf16(va):
            result = bytearray()
            for offset in range(0, 512, 2):
                word = bytes(u.mem_read(va + offset, 2))
                if word == b'\0\0':
                    return result.decode('utf-16le')
                result.extend(word)
            self.fail('unterminated callback string')
        for i, p in enumerate(players):
            number, first, last = (10 + i, 'Alex', f'Player{i:02}') if names is None else names[i]
            first_va, last_va = self.TEAM + 0x2000 + i * 128, self.TEAM + 0x2040 + i * 128
            u.mem_write(first_va, (first + '\0').encode('utf-16le'))
            u.mem_write(last_va, (last + '\0').encode('utf-16le'))
            put(self.player(i) + 0x10, 'II', first_va, last_va)
            put(self.player(i) + 0x20, 'I', number << 3)
        if returners is not None:
            for off, value in zip((0x195, 0x196, 0x199), returners):
                put(self.TEAM + off, 'B', value)
        if player_rows is not None:
            # The real summary entry compacts the loaded team's depth lists.
            self.call(u, 0x243790, ecx=self.TEAM, limit=1000000)
        if spacing is not None:
            put(rows.SUMMARY_SPACING_VA, 'f', spacing)
        count = self.call(u, rows.COUNT_VA)
        style = rows._read(payload, rows.SUMMARY_STYLE_VA, 48)
        cell_height = struct.unpack_from('<I', style, 24)[0]
        for off, value in ((0xa0, 7), (0xa4, count), (0x8c, rows.SUMMARY_STYLE),
                           (0x3c, self.POINTERS), (0x74, 1), (0xcc, 6), (0x80, 1),
                           (0xc4, 7), (0x50, 1), (0xbc, selected)):
            put(self.SHEET + off, 'I', value)
        # Every depth-summary column has +0x64 == 1: all seven are frozen.
        put(self.SHEET, 'I', 7)
        for off, value in zip((0x90, 0x94, 0x98, 0x9c), rows.SUMMARY_FRAME):
            put(self.SHEET + off, 'f', value)
        widths = []
        for col, desc in enumerate(rows.SUMMARY_COLUMNS):
            fixed = struct.unpack('<f', rows._read(payload, desc + 0x50, 4))[0]
            # Private FONT test independently pins font3's two digits: 11+11,
            # plus the retail width getter 0x1737A0's six-pixel padding.
            widths.append(fixed or 28.0)
        for row in range(count):
            put(self.POINTERS + row * 4, 'I', self.CELLS + row * 7 * 44)
            for col, desc in enumerate(rows.SUMMARY_COLUMNS):
                cell = self.CELLS + (row * 7 + col) * 44
                put(cell, 'Iff', desc, widths[col], cell_height)
                put(cell + 0x20, 'I', 0x173840)
        # Runs the real two-pass scrollbar feedback loop, including row and
        # complete-column bounds. No hooks are installed during layout.
        self.call(u, 0x172120, esi=self.SHEET, limit=200000)
        layout = {k: struct.unpack('<' + fmt, u.mem_read(self.SHEET + off, 4))[0]
                  for k, off, fmt in [('visible_rows', 0x28, 'I'), ('visible_columns', 0x2c, 'I'),
                                     ('vertical_scroll', 0x34, 'I'), ('horizontal_scroll', 0x30, 'I'),
                                     ('left', 0x10, 'f'), ('right', 0x18, 'f'),
                                     ('top', 0x14, 'f'), ('bottom', 0x1c, 'f'), ('scroll_row', 0xc8, 'I')]}
        drawn = []
        def intercept(machine, address, _size, _data):
            if address not in (0x172a60, 0x16f680):
                return
            sp = machine.reg_read(x.UC_X86_REG_ESP)
            ret = struct.unpack('<I', machine.mem_read(sp, 4))[0]
            if address == 0x16f680:
                text = utf16(machine.reg_read(x.UC_X86_REG_EDX))
                row = struct.unpack('<I', machine.mem_read(self.SHEET + 0xb4, 4))[0]
                col = struct.unpack('<I', machine.mem_read(self.SHEET + 0xb8, 4))[0]
                drawn.append({'row': row, 'column': col, 'text': text})
            # The two intercepted routines only set font/GPU draw state and
            # submit final glyphs; their stack cleanup remains exact.
            machine.reg_write(x.UC_X86_REG_ESP, sp + (36 if address == 0x172a60 else 8))
            machine.reg_write(x.UC_X86_REG_EIP, ret)
        u.hook_add(UC_HOOK_CODE, intercept)
        bits = lambda value: struct.unpack('<I', struct.pack('<f', value))[0]
        self.call(u, 0x171b80, eax=self.SHEET,
                  stack=tuple(bits(layout[k]) for k in ('left', 'top', 'right', 'bottom')), limit=1000000)
        return {'unit': unit, 'row_count': count, 'layout': layout, 'column_widths': widths,
                'row_pitch': cell_height + (spacing if spacing is not None else struct.unpack_from('<f', style, 40)[0]),
                'font_slot': struct.unpack_from('<I', style, 32)[0], 'drawn': drawn}


ARCHIVE_INDEX = legacy.XBE.parent / 'vc_53450030/0'


@unittest.skipUnless(ARCHIVE_INDEX.is_file(), 'retail archive index and packs required for LAYT/FONT evidence')
class PrivateResourceTests(unittest.TestCase):
    def test_retail_frame_style_and_digit_metrics_independently_match_probe(self):
        from nfl_outer import parse_archive, read_entry_bytes
        from nfl_txtr import parse_chunks, decode_chunk
        from nfl_scene_probe import record_from_header
        from nfl_main_menu_font import parse_font
        from layout_inventory import relative, parse_chain, NFL_RECORD_SIZES
        archive = parse_archive(ARCHIVE_INDEX)
        raw = read_entry_bytes(archive, archive.entries[3], max_size=3_000_000)
        chunks = parse_chunks(raw)
        body, _ = decode_chunk(raw, chunks[73])
        self.assertEqual(hashlib.sha256(body).hexdigest(),
                         '7443c566c77317efa873a7394f5b800a95935f6f7b7d8a69325a86b1a9d8ac2e')
        descriptor = relative(body, 0x14, '<', 'LAYT descriptor', allow_null=False)
        records = parse_chain(body, relative(body, descriptor + 4, '<', 'head'),
                              '<', 'utf-16le', NFL_RECORD_SIZES, 'nfl2k5', {})
        node = next(r for r in records if r['source_name'] == 'dc_overviewsheet')
        off = node['record_offset']
        x, y = struct.unpack_from('<2f', body, off + 0x10)
        width, height, style = struct.unpack_from('<3I', body, off + 0x20)
        self.assertEqual((x, y, x + width, y + height), rows.SUMMARY_FRAME)
        self.assertEqual(style, rows.SUMMARY_STYLE)
        font_body, _ = decode_chunk(raw, chunks[2])
        digest = hashlib.sha256(font_body).hexdigest()
        self.assertEqual(digest, '330765bb8482457120520cdb9d354a91d6e615f2ae75c9fa93b4542a3882282c')
        resource = record_from_header(archive, 3, 2, chunks[2].offset, 'retail', None)
        font = parse_font(2, 'font3', resource, font_body, digest)
        self.assertEqual(font.line_advance, 24)
        self.assertEqual({g.advance for g in font.glyphs if chr(g.codepoint).isdigit()}, {11})
        advances = {chr(g.codepoint): g.advance for g in font.glyphs}
        maximum_label_width = max(sum(advances[c] for c in label) for label in EXPECTED_ORDER)
        self.assertEqual(maximum_label_width, 51)
        self.assertEqual(maximum_label_width + 6, rows.SUMMARY_LABEL_WIDTH)

    def test_all_retail_layouts_use_style_seventeen_only_for_depth_summary(self):
        inventory = list(Path.home().glob('.cache/2k5-mod-studio/*/indexes/nfl2k5_resource_chunks_v2.json'))
        if not inventory:
            self.skipTest('complete private resource inventory required for all-LAYT style census')
        from layout_inventory import parse_nfl
        layouts, records = parse_nfl(ARCHIVE_INDEX, inventory[0])
        self.assertEqual(len(layouts), 86)
        users = [(r['layout_name'], r['source_name']) for r in records
                 if r['record_type'] == 1 and int(r['raw_words'][10], 16) == rows.SUMMARY_STYLE]
        self.assertEqual(users, [('dc_overview', 'dc_overviewsheet')])


@unittest.skipUnless(legacy.XBE.is_file() and legacy.HAVE_UNICORN,
                     'retail default.xbe and Unicorn required for bounded spreadsheet draw')
class NativeDrawTests(DrawProbe):
    @classmethod
    def setUpClass(cls):
        cls.retail = legacy.XBE.read_bytes()
        cls.patched = rows.apply(legacy.prepare(cls.retail))[0]
        cls.before = before_special(cls.patched)

    def test_reproduces_missing_third_names_and_draws_all_thirteen_after(self):
        old, new = self.run_draw(self.before), self.run_draw(self.patched)
        self.assertEqual((old['layout']['visible_rows'], old['layout']['visible_columns']), (11, 6))
        self.assertTrue(old['layout']['vertical_scroll'])
        self.assertTrue(old['layout']['horizontal_scroll'])
        self.assertEqual({c['column'] for c in old['drawn']}, set(range(6)))
        self.assertEqual((new['layout']['visible_rows'], new['layout']['visible_columns']), (13, 7))
        self.assertFalse(new['layout']['vertical_scroll'])
        self.assertFalse(new['layout']['horizontal_scroll'])
        self.assertEqual(len(new['drawn']), 13 * 7)
        self.assertEqual(new['column_widths'], [57, 28, 145, 28, 145, 28, 145])
        self.assertLessEqual(sum(new['column_widths']), new['layout']['right'] - new['layout']['left'])
        self.assertEqual([c['text'] for c in new['drawn'] if c['column'] == 0], EXPECTED_ORDER)
        for row in (5, 6, 7, 8, 9, 10, 11, 12):
            with self.subTest(row=row):
                number = next(c['text'] for c in new['drawn'] if (c['row'], c['column']) == (row, 5))
                name = next(c['text'] for c in new['drawn'] if (c['row'], c['column']) == (row, 6))
                self.assertTrue(number.strip())
                self.assertTrue(name.startswith('A. Player'), name)
                self.assertEqual(name, f'A. Player{int(number) - 10:02}')

    def test_spacing_one_is_largest_integral_fit_and_font_is_unchanged(self):
        for gap in (4, 3, 2, 1):
            result = self.run_draw(self.patched, spacing=gap)
            self.assertEqual(result['layout']['visible_rows'] == 13, gap == 1)
            self.assertEqual(result['layout']['visible_columns'] == 7, gap == 1)
            self.assertEqual(result['font_slot'], 2)
        for unit in (0, 1, 2):
            result = self.run_draw(self.patched, unit)
            self.assertEqual(result['layout']['visible_rows'], 11)
            self.assertEqual(result['layout']['visible_columns'], 7)

    def test_last_row_selection_and_empty_short_pools(self):
        for count in (0, 1, 2, 3):
            result = self.run_draw(self.patched, selected=12, pool_count=count)
            self.assertEqual(result['layout']['scroll_row'], 0)
            self.assertEqual(len(result['drawn']), 91)
            for row in range(4, 13):
                for number_col in (1, 3, 5):
                    pair = [c['text'] for col in (number_col, number_col + 1)
                            for c in result['drawn'] if (c['row'], c['column']) == (row, col)]
                    self.assertEqual(bool(pair[0].strip()), bool(pair[1].strip()))

    def test_spacing_write_is_data_and_all_other_style_fields_match(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.patched)
        section = image.section(rows.SUMMARY_STYLE_VA, 48)
        self.assertEqual(section.name, '.data')
        # Retail .data has flags 7 (including execute permission), just like
        # .rdata. Section identity and descriptor consumers prove DATA use.
        self.assertNotEqual(section.name, '.text')
        before = rows._read(self.retail, rows.SUMMARY_STYLE_VA, 48)
        after = rows._read(self.patched, rows.SUMMARY_STYLE_VA, 48)
        self.assertEqual(before[:40] + before[44:], after[:40] + after[44:])
        self.assertEqual(struct.unpack_from('<f', after, 40)[0], 1)

    def test_every_tab_uses_the_same_screen_and_resolver_chains_are_unchanged(self):
        for va in (0x243C30, 0x243C60, 0x243C90, 0x243CC0):
            self.assertEqual(rows._read(self.patched, va, 8), bytes.fromhex('568bf2ba88305300'))
        # Existing native ordinal/picker tests check these preserved contracts
        # against the on-field PLAY reader as well as the chart resolver.
        old = {long: (pos, chain) for _, _, _, long, pos, chain in BEFORE_ROLES}
        for _, _, short, long, pos, chain in rows.ROLE_ROWS:
            key = '3RD DOWN BACK' if short == '3DRB' else long
            self.assertEqual((pos, chain), old[key])


def load_tests(loader, tests, pattern):
    # Synthetic LayoutTests are already inherited above; retain the old
    # private-XBE and bounded selection/storage checks in standalone CI too.
    for cls in (legacy.RetailTests, legacy.ExecutionTests):
        tests.addTests(loader.loadTestsFromTestCase(cls))
    return tests


if __name__ == '__main__':
    unittest.main()
