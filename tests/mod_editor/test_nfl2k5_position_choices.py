"""Beta 65: execute native CAP cycles/templates; verify every live picker site."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_position_pools as pools
from mod_editor.core import nfl2k5_edge_rename as edge, nfl2k5_modern_positions as modern
from mod_editor.core import nfl2k5_my_career as career, nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from tests import nfl2k5_position_pools_test as fixture
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC, prepared


class PickerApiTests(unittest.TestCase):
    def test_option_off_has_all_retail_codes_and_on_has_one_edge_one_lb(self):
        self.assertEqual([x[0] for x in career.position_choices()], list(range(17)))
        choices = career.position_choices('one_pool')
        self.assertEqual([x[0] for x in choices], [x for x in range(17) if x != 10])
        self.assertEqual([x for x in choices if x[1] in ('EDGE', 'LB')],
                         [(11, 'LB', 'Linebacker'), (16, 'EDGE', 'Edge Rusher')])
        self.assertFalse(any(x[1] in ('DE', 'OLB', 'ILB') for x in choices))
        self.assertEqual([t.label for t in career.templates_for(16, scheme='one_pool')],
                         ['Power EDGE', 'Speed EDGE', 'Balanced EDGE'])

    def test_pooled_setup_uses_edge_ratings_and_refuses_retired_enum(self):
        for variant in range(3):
            save, setup, receipt = prepared('EDGE', scheme='one_pool', template=variant)
            self.assertEqual(receipt['position'], 'EDGE')
            self.assertEqual(receipt['ratings'], 'merged EDGE template')
            self.assertEqual(career.read_setup(setup)[career.POSITION_OFFSET], 16)
            # The on-disk v2 label stays retail for old setup readers.
            self.assertEqual(setup['position'], 'DE')
        with self.assertRaises(rr.RosterRecordError):
            prepared(10, scheme='one_pool')


@unittest.skipUnless(XBE.is_file() and HAVE_UC, 'pinned USA retail XBE or Unicorn absent')
class NativeChoicesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('USA retail XBE evidence pin differs')
        cls.base = modern.apply(edge.apply(cls.retail)[0])[0]
        # The EDGE-only product profile is an explicit, certified choice (the Studio
        # passes it after the roster scan); a bare apply retains the rows.
        cls.patched, cls.receipt = pools.apply(cls.base, roster_has_olb=False)

    def boot(self, payload):
        runner = fixture.EmulationTests()
        uc = runner._boot(payload, [])
        # The retail .text remains RX during these native functions.
        from unicorn import UC_PROT_READ, UC_PROT_EXEC
        uc.mem_protect(0x11000, 0x410000, UC_PROT_READ | UC_PROT_EXEC)
        def put(va, n):
            uc.mem_write(va, struct.pack('<I', n))
        def call(va):
            from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP
            result = runner._call(uc, va, until=runner.SENT_VA)
            self.assertEqual(uc.reg_read(UC_X86_REG_EIP), runner.SENT_VA)
            self.assertEqual(uc.reg_read(UC_X86_REG_ESP), runner.STACK_VA + 0x80004)
            return result
        put(0xCB8B14, runner.TEAM_VA)
        return uc, runner.TEAM_VA, put, call

    def test_cycles_both_directions_every_position_off_and_on_no_dead_row(self):
        for payload, codes in ((self.retail, list(range(17))),
                               (self.patched, [i for i in range(17) if i != 10])):
            uc, player, put, call = self.boot(payload)
            for direction, va in ((1, pools.CREATE_POSITION_NEXT_VA), (-1, pools.CREATE_POSITION_PREVIOUS_VA)):
                seen = []
                uc.mem_write(player + 0x35, b'\0')
                for _ in codes:
                    put(0xCB8820, 0)
                    call(va)
                    seen.append(uc.mem_read(player + 0x35, 1)[0])
                    self.assertEqual(uc.mem_read(0xCB8820, 4), b'\1\0\0\0')
                self.assertEqual(len(seen), len(set(seen)))
                self.assertEqual(set(seen), set(codes))
                self.assertEqual(seen[-1], 0)
                for pos in range(17):
                    uc.mem_write(player + 0x35, bytes([pos]))
                    expected = (pos + direction) % 17
                    if payload is self.patched and expected == 10:
                        expected += direction
                    call(va)
                    self.assertEqual(uc.mem_read(player + 0x35, 1)[0], expected)

    def test_all_51_native_template_writes_and_live_label_getters(self):
        for payload, scheme in ((self.retail, 'retail'), (self.patched, 'one_pool')):
            uc, player, put, call = self.boot(payload)
            table = rr.read_templates(payload)
            if scheme == 'retail':
                self.assertEqual(table, rr.create_player_templates())
            put(0xCB8BA0, 0)
            for code in rr.live_position_codes(scheme):
                for variant in range(3):
                    uc.mem_write(player, bytes([0xA5]) * 84)
                    uc.mem_write(player + 0x35, bytes([code]))
                    put(0xCB8830, variant)
                    call(0x343460)
                    template = rr.create_player_templates(scheme)[3 * code + variant]
                    self.assertEqual(table[template.index], template)
                    for offset, raw in zip(rr.CREATE_PLAYER_TEMPLATE_SLOT_OFFSETS, template.slots):
                        self.assertEqual(uc.mem_read(player + offset, 1)[0], 75 if raw == -1 else max(0, min(100, raw)))
                    label_va = call(0x343FA0)
                    label = bytes(uc.mem_read(label_va, 64)).decode('utf-16le').split('\0')[0]
                    self.assertEqual(label, template.label)
                    if code == 16 and scheme == 'one_pool':
                        name_va = call(0x345540)
                        self.assertEqual(bytes(uc.mem_read(name_va, 24)).decode('utf-16le').rstrip('\0'), 'Edge Rusher')

    def test_all_string_sites_and_seventh_consumer(self):
        im = XbeImage(self.patched)
        self.assertEqual(len(edge.POINTER_SITES), 7)
        for label, va, _old, new in edge.POINTER_SITES:
            self.assertEqual(im.read(va, 4), struct.pack('<I', new), label)
        for va in edge.SINGULAR_SITES:
            self.assertEqual(im.read(va, edge.SINGULAR_SLOT), edge._utf16('Edge Rusher', edge.SINGULAR_SLOT))
        for va in edge.PLURAL_SITES:
            self.assertEqual(im.read(va, edge.PLURAL_SLOT), edge._utf16('Edge Rushers', edge.PLURAL_SLOT))
        for label, va, size, _old, new in pools.STRING_SITES:
            self.assertEqual(im.read(va, size), pools._utf16(new, size), label)
        # Exhaustive literal census: unused abbreviation literals may remain,
        # but no singular/plural long-name literal remains in the image.
        self.assertNotIn('defensive end'.encode('utf-16le'), self.patched.lower())

    def test_default_compacts_all_sixteen_lists_and_trade_need_enum_pairs(self):
        self.assertEqual(self.receipt['olb_filter_rows'], 'removed')
        self.assertEqual(pools.filter_list_status(self.patched), 'applied')
        im = XbeImage(self.patched)
        for site in pools.filter_list_sites():
            self.assertEqual(im.read(site.va, site.size), site.after)
        pairs = [struct.unpack('<II', im.read(0x557EC8 + 8 * i, 8)) for i in range(10)]
        self.assertEqual([enum for label, enum in pairs if label], [15, 16, 11, 4, 6, 5, 1, 2])
        self.assertEqual(pairs[-2:], [(0, 0), (0, 0)])

    def test_native_modal_count_stops_at_compacted_terminator(self):
        for payload, count in ((self.retail, 9), (self.patched, 8)):
            runner = fixture.EmulationTests()
            uc = runner._boot(payload, [])
            obj = runner.TEAM_VA
            uc.mem_write(obj + 0x10, struct.pack('<I', 0x557EC8))
            self.assertEqual(runner._call(uc, 0x14D4A0, ecx=obj, until=runner.SENT_VA), count)

    def test_every_new_write_site_refuses_foreign_and_all_section_digests_match(self):
        for site in pools.creation_sites():
            bad = bytearray(self.base)
            bad[pools._offset(bad, site.va)] ^= 0x20
            snapshot = bytes(bad)
            with self.assertRaises(pools.PositionPoolsError, msg=site.label):
                pools.apply(bad)
            self.assertEqual(bytes(bad), snapshot)
        for section in pools._sections(self.patched):
            if section.raw_size:
                self.assertEqual(section.stored_digest, pools.section_digest(self.patched, section))
        self.assertEqual(pools.apply(self.patched)[0], self.patched)
        self.assertEqual(edge.apply(self.patched)[0], self.patched)

    def test_native_creation_and_inline_mycareer_compose_both_orders(self):
        a = mode.apply(self.patched)[0]
        b = pools.apply(mode.apply(self.base)[0], roster_has_olb=False)[0]
        self.assertEqual(a, b)
        self.assertEqual(mode.status(a), 'applied')
        self.assertEqual(pools.status(a), 'applied')

    def test_evidence_metadata_matches_every_declared_write(self):
        path = Path(__file__).resolve().parents[2] / 'docs/mod_editor/nfl2k5_b65_positions_evidence.json'
        doc = json.loads(path.read_text())
        for row, site in zip(doc['edge_sites'], edge._sites(self.retail), strict=True):
            label, off, before, after = site
            self.assertEqual(row['name'], label)
            self.assertEqual(edge._offset(self.retail, int(row['va'], 0)), off)
            self.assertEqual(row['retail_sha256'], hashlib.sha256(before).hexdigest())
            self.assertEqual(row['written_sha256'], hashlib.sha256(after).hexdigest())
        for row, site in zip(doc['position_pool_sites'], pools._sites(True, True), strict=True):
            self.assertEqual((row['name'], int(row['va'], 0), row['size']), (site.label, site.va, site.size))
            self.assertEqual(row['written_sha256'], hashlib.sha256(site.after).hexdigest())
        self.assertEqual(doc['minimal_composition']['edge_modern_pools_sha256'], hashlib.sha256(self.patched).hexdigest())

    def test_contracts_position_editor_accepts_only_complete_pools_companion(self):
        from mod_editor.core import nfl2k5_franchise_edit_player as edit
        a = edit.apply(self.patched)[0]
        b = pools.apply(edit.apply(self.base)[0], roster_has_olb=False)[0]
        self.assertEqual(a, b)
        self.assertEqual(edit.status(a), 'applied')
        corrupt = bytearray(a)
        corrupt[pools._offset(corrupt, pools.CREATE_POSITION_PREVIOUS_VA + 20)] ^= 1
        self.assertEqual(edit.status(bytes(corrupt)), 'foreign')


if __name__ == '__main__':
    unittest.main()
