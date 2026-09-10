"""Bounded native Settings, shared retail FPF word, masked star and saved choices.

Synthetic RAM / private pinned assets; no game boot or display. Menu fixtures
name their scene/GPU/input/heap seams. Save fixtures run every serializer and
capture the signed-transaction boundary; they do not write a physical save.
"""
from pathlib import Path
import hashlib
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_my_career_save as save
from mod_editor.core import nfl2k5_save_rost as roster
from mod_editor.core import nfl2k5_player_tags as tags
from mod_editor.core import nfl2k5_player_star as star
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import Machine as NativeMachine, retail_bytes, retail_roster
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC, draft_save
from tests.nfl2k5_my_career_mode_fixture import Machine
from tests.mod_editor.test_nfl2k5_my_career_inline import block_for


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA retail XBE/ROST and Unicorn required')
class SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.payload = mode.apply(cls.retail)[0]
        cls.source = draft_save()
        cls.footer = block_for(cls.source)

    def test_retail_row_toggles_display_and_fpf_entry_use_one_native_word(self):
        im = XbeImage(self.retail)
        row = struct.unpack('<13I', im.read(0x500B24, 52))
        self.assertEqual(row, (5, 0xE7D5C4, 0, 0x147EC0, 0x147ED0, 0x147EB0,
                               0x147E60, 0x147E80, 0x148960, 0x147EE0, 0, 0, 0))
        for va, size, digest in mode.GUARDS[:7]:
            self.assertEqual(hashlib.sha256(im.read(va, size)).hexdigest(), digest)
        m = NativeMachine(self.retail)
        for value in (0, 1):
            m.put(0xE5FFE4, value)
            self.assertEqual(m.call(row[5]), value)
            self.assertEqual(m.call(row[8]), struct.unpack('<I', im.read(0x4ED994+4*value, 4))[0])
            self.assertEqual(m.call(row[6]), 1)
            self.assertEqual(m.get(0xE5FFE4), 1-value)
            self.assertEqual(m.call(row[7]), 1)
            self.assertEqual(m.get(0xE5FFE4), value)
            self.assertEqual(m.call(0x627E0), value)
            m.put(0xE5FF80, 5)
            m.call(0x64530, stop=0xF53C0)
            normal = struct.unpack('<I', im.read(0x4E7CB0+4*5, 4))[0]
            self.assertEqual(m.reg('ECX'), 2 if value else normal)
        # Exact native FPP entry's setting write, before unrelated team/UI work.
        m.call(0x2C1FF1, stop=0x2C1FFB)
        self.assertEqual(m.get(0xE5FFE4), 1)
        self.assertEqual(m.leaves, [])

    def test_changed_first_person_prerequisites_refuse_before_install(self):
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import repin_edit
        image = XbeImage(self.retail)
        for va, _, _ in mode.GUARDS[:7]:
            damaged = repin_edit(self.retail, va, bytes((image.read(va, 1)[0] ^ 1,)))
            with self.subTest(va=hex(va)):
                self.assertEqual(mode.status(damaged), 'foreign')
                with patch.object(mode.space, 'install_code', side_effect=AssertionError('install before refusal')):
                    with self.assertRaises(mode.legacy.MyCareerError): mode.apply(damaged)
        self.assertEqual(mode.apply(self.payload)[0], self.payload)

    def test_all_footer_choices_match_host_and_native_and_reserved_bits_refuse(self):
        with Machine(self.payload) as m:
            m.native_load(self.source+self.footer)
            for flags in range(8):
                m.put(0xE5FFE4, flags & 1)
                m.put(m.state+2696, (flags >> 1) & 1)
                m.put(m.state+2700, (flags >> 2) & 1)
                m.call('inline_encode', ecx=m.OUT)
                block = bytes(m.uc.mem_read(m.OUT, 128))
                self.assertEqual(block[82], flags)
                self.assertEqual(save.validate(block), block)
                self.assertEqual(save.from_runtime(save.to_runtime(block)), block)
                self.assertEqual(save.from_runtime(bytes(m.uc.mem_read(m.state, 4096))), block)
                self.assertEqual(m.call('inline_valid', ecx=m.OUT, edx=0x91000), 1)
            for flags in (8, 128, 255):
                block = bytearray(self.footer); block[82] = flags; block = save.seal(block)
                with self.assertRaises(save.CareerSaveError): save.validate(block)
                m.uc.mem_write(m.OUT, block)
                self.assertEqual(m.call('inline_valid', ecx=m.OUT, edx=0x91000), 0)

    def test_old_footer_migrates_only_myplayer_star_preserving_other_tag_bits(self):
        source = bytearray(self.source)
        players = roster.decode(source).players
        record = roster.decode(source).by_key['primary', 0].offset
        source[record+0x53] = 0xA6
        with Machine(self.payload) as m:
            m.native_load(bytes(source)+self.footer)
            p = m.call('primary')
            self.assertEqual(m.uc.mem_read(p+0x53, 1), b'\xa7')
            self.assertEqual((m.get(0xE5FFE4), m.get(m.state+2696), m.get(m.state+2700)), (0, 0, 0))
            # The serializer's ROST body preserves every other player's tag.
            output = m.native_save()
            decoded = roster.decode(output)
            for player in players:
                old = source[player.offset+0x53]
                new = output[decoded.by_key[player.pool, player.index].offset+0x53]
                self.assertEqual(new, old | 1 if player.offset == record else old)

    def test_native_save_cold_relocation_preserves_settings_and_off_star(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        other = mode.apply(mode.space.apply(self.retail, REQUESTS, scaleout=True)[0])[0]
        with Machine(self.payload) as m:
            m.native_load(self.source+self.footer)
            m.put(0xE5FFE4, 1); m.put(m.state+2696, 1); m.put(m.state+2700, 1)
            output = m.native_save()
            self.assertEqual(save.read(output)[82], 7)
            with Machine(other) as cold:
                cold.native_load(output)
                self.assertNotEqual(cold.state, m.state)
                self.assertEqual((cold.get(0xE5FFE4), cold.get(cold.state+2696), cold.get(cold.state+2700)), (1, 1, 1))
                self.assertEqual(cold.uc.mem_read(cold.call('primary')+0x53, 1)[0] & 1, 0)
                # The original Franchise callback still changes the same word;
                # the next career save samples it, never a stale shadow flag.
                cold.call(0x147E80)
                cold.call('inline_encode', ecx=cold.OUT)
                self.assertEqual(cold.uc.mem_read(cold.OUT+82, 1), b'\x06')

    def test_settings_native_navigation_labels_selection_cancel_and_masked_star(self):
        from tests.mod_editor.test_nfl2k5_my_career_m3_menus import MenuTests, Machine as MenuMachine
        MenuTests.setUpClass(); checker = MenuTests()
        with MenuMachine(self.payload) as m:
            created = []
            def before_created(*_):
                pending = m.get(m.state+2676)
                if pending:
                    m.uc.mem_write(pending+0x53, b'\xa6')
            def after_created(*_):
                pending = m.get(m.state+2676)
                created.append(m.uc.mem_read(pending+0x53, 1)[0])
            m.uc.hook_add(m.u.UC_HOOK_CODE, before_created,
                          begin=m.labels['mode_created'], end=m.labels['mode_created'])
            m.uc.hook_add(m.u.UC_HOOK_CODE, after_created,
                          begin=m.labels['m3_creation_route'], end=m.labels['m3_creation_route'])
            p = m.create(checker.roster, preseason=False)
            self.assertEqual(created, [0xA7])  # before signing/capture
            self.assertEqual(m.uc.mem_read(p+0x53, 1)[0], 0xA7)  # after signing
            checker.install(m)
            m.select(5)
            self.assertEqual(m.top(), m.labels['m3_settings_menu'])
            texts = checker.rendered(m)
            self.assertIn('Spectate keeps all presentation. B returns to Apartment.', texts)
            for index, expected in ((0, 'First Person Football: On'), (1, 'Off-field play: Spectate'), (2, 'MyPlayer star: Off')):
                m.select(index)
                m.native_rows.clear(); checker.rendered(m)
                selected = [r['text'] for r in m.native_rows if r['color'] & 0xFFFFFF == 0xFFFF00]
                self.assertIn(expected, selected)
                self.assertEqual(m.get(m.manager+8*m.depth()+4), index)
            self.assertEqual(m.get(0xE5FFE4), 1)
            # Exhaust every high-bit combination through the real row callback.
            for high in range(0, 256, 2):
                m.uc.mem_write(p+0x53, bytes((high,)))
                before = bytes(m.uc.mem_read(p-84, 3*84))
                m.select(2)
                self.assertEqual(m.uc.mem_read(p+0x53, 1)[0], high | 1)
                m.select(2)
                self.assertEqual(bytes(m.uc.mem_read(p-84, 3*84)), before)
            # Existing roster reader recognizes exactly the bit written above.
            body = bytearray(retail_roster())
            parsed = tags.parse_body(body); chosen = parsed.players[0]
            body[chosen.offset+0x53] = high | 1
            self.assertTrue(tags.parse_body(body).players[0].tagged)
            body[chosen.offset+0x53] &= 0xFE
            self.assertFalse(tags.parse_body(body).players[0].tagged)
            m.frame(0x200)
            self.assertEqual(m.top(), m.labels['apartment'])
            before = (m.get(0xE5FFE4), m.get(m.state+2696), m.get(m.state+2700))
            m.call('mode_settings_toggle', ecx=m.manager)
            m.call('mode_settings_toggle', ecx=0)
            self.assertEqual((m.get(0xE5FFE4), m.get(m.state+2696), m.get(m.state+2700)), before)
            m.call(0x147E60)  # original Franchise row changed the native value
            m.select(5); m.native_rows.clear(); checker.rendered(m)
            self.assertIn('First Person Football: Off', [r['text'] for r in m.native_rows])

    def test_filled_star_native_match_copy_preserves_myplayer_tag(self):
        payload = star.apply(self.payload)[0]
        with Machine(payload) as m:
            m.native_load(self.source+self.footer)
            p = m.call('primary'); team = m.get(m.state+2588)
            # Load resolves a valid career team. The native team copier, with
            # the filled-star owner's full-record copy bridge, reaches +0x53.
            self.assertTrue(team)
            m.call(0xC3C60, ecx=team, edx=0xB30C4C)
            ordinal = next(i for i in range(m.uc.mem_read(team+0x11C, 1)[0]) if m.get(team+4*i) == p)
            self.assertEqual(m.uc.mem_read(0xB30C4C+84*ordinal+0x53, 1), m.uc.mem_read(p+0x53, 1))
            self.assertEqual(m.uc.mem_read(p+0x53, 1)[0] & 1, 1)


if __name__ == '__main__':
    unittest.main()
