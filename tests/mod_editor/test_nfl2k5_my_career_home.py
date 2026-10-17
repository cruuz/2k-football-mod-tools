"""ui1: MyCareer Career Home (Noah 2026-10-17: "a test MyCareer new menu system/screen to push the limits").

Static: the extra-section install, exact replay, mutual exclusion with the music section, the unchanged
MyCareer bytes when Career Home is off, and the static checker over every descriptor, row and pointer.
Native (Unicorn, pinned USA XBE, retail ROST/FONT/LAYT/MRKS): opening Career Home, every row, the
Settings + Save sub-list, the Classic Apartment, B and quit, port 2, and the panel draw with real text,
glyph and vertex submission. No game boot, display, xemu or controller.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_my_career_home as home
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_supersim_draft_fixture import retail_bytes

MAIN_MENU, TEAM_SELECT, SAVE_LOAD = 0x515660, 0x51B908, 0x507EC8
HOME_ROWS = ['Play next game', 'Practice', 'MyPlayer', 'Upgrades', 'Settings + Save', 'Quit to Menu']
OPTION_ROWS = ['Settings', 'Save', 'Sim to next appearance', 'Start MyPlayer', 'Classic Apartment', 'Back']
CLASSIC_ROWS = ['Play next game', 'Practice', 'MyPlayer', 'Start MyPlayer', 'Upgrades', 'Settings', 'Save']
PANEL = (290, 84, 620, 310)  # x0, y0, x1, y1 in HUD text space


def reseal(buf):
    from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    return bytes(buf)


@unittest.skipUnless(XBE.is_file(), 'pinned USA XBE required')
class CareerHomeStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.career = mode.apply(retail_bytes())[0]
        cls.payload, cls.receipt = home.apply(cls.career)

    def test_section_geometry_status_and_replay(self):
        p = self.payload
        self.assertEqual(struct.unpack_from('<I', p, 0x11C)[0], space.SCALE_COUNT + 1)
        self.assertEqual(len(p), len(self.career))
        self.assertTrue(space.has_home_section(p))
        self.assertFalse(space.has_music(p))
        self.assertEqual((space.status(p), mode.status(p), home.status(p)), ('applied',) * 3)
        section = XbeImage(p).section(home.VA)
        self.assertEqual((section.start, section.raw, section.raw_size, section.flags),
                         (home.VA, home.RAW, home.SIZE, home.FLAGS))
        self.assertTrue(section.writable and section.executable)
        # Outside its own pages the old music gap stays zero; the header slot and names are the music slot's.
        self.assertFalse(any(p[home.RAW + home.SIZE:space.CODE2_RAW]))
        region = [r for r in space.layout(p)['regions'] if r.get('home')]
        self.assertEqual([(r['va'], r['size'], r['flags']) for r in region], [(home.VA, home.SIZE, home.FLAGS)])
        # Every byte that changed is in MyCareer's code allocation, the section, the header metadata or the
        # allocator directory page (its sealed code digest covers MyCareer's re-pointed template).
        code, _ = mode.legacy.allocations(p)
        image = XbeImage(p)
        lo = image.offset(code['va'])
        changed = [i for i, (a, b) in enumerate(zip(self.career, p)) if a != b]
        outside = [i for i in changed if not (lo <= i < lo + 20480 or home.RAW <= i < home.RAW + home.SIZE
                                              or i < 0x1000 or space.SCALE_DIRECTORY <= i < space.SCALE_DIRECTORY + 0x1000)]
        self.assertEqual(outside, [])
        again, receipt = home.apply(p)
        self.assertEqual((again, receipt['already_applied']), (p, True))
        self.assertGreater(self.receipt['spare_bytes'], 1024)

    def test_off_leaves_mycareer_and_the_image_unchanged(self):
        self.assertEqual(struct.unpack_from('<I', self.career, 0x11C)[0], space.SCALE_COUNT)
        self.assertEqual(home.status(self.career), 'retail')
        code, data = mode.legacy.allocations(self.career)
        self.assertEqual(XbeImage(self.career).read(code['va'], 20480), mode.code_for(code['va'], data['va'])[0])
        self.assertFalse(any(self.career[home.RAW:space.CODE2_RAW]))

    def test_static_checker_covers_every_descriptor_row_and_pointer(self):
        receipt = home.check_static(self.payload)
        self.assertEqual(receipt['descriptors'], {'apartment': 'Career Home', 'home_classic': 'Apartment',
                                                  'home_options': 'Settings + Save'})
        self.assertEqual(receipt['rows']['apartment'], HOME_ROWS)
        self.assertEqual(receipt['rows']['home_options'], OPTION_ROWS)
        self.assertEqual(receipt['rows']['home_classic'][:7], CLASSIC_ROWS)
        self.assertEqual(receipt['rows']['home_classic'][-1], 'Quit to main menu')
        self.assertGreaterEqual(receipt['mycareer_spare_bytes'], 0)
        labels = home.code_for(home.career_labels(self.payload))[1]
        # Negative controls: a row action, a row label and a descriptor handler pointing anywhere else refuse.
        for name, offset in (('home_rows', 40), ('home_rows', 4), ('home_options', 8)):
            with self.subTest(field=(name, offset)):
                bad = bytearray(self.payload)
                at = home.RAW + labels[name] - home.VA + offset
                bad[at:at + 4] = struct.pack('<I', 0x11000)
                self.assertEqual(home.status(reseal(bad)), 'foreign')
                with self.assertRaises(ValueError):
                    home.check_static(reseal(bad))

    def test_foreign_section_and_template_bytes_refuse(self):
        bad = bytearray(self.payload)
        bad[home.RAW + home.HEADER + 100] ^= 1
        self.assertEqual(home.status(reseal(bad)), 'foreign')
        with self.assertRaises(ValueError):
            home.apply(reseal(bad))
        # A Career Home section without MyCareer's re-pointed Apartment is mixed, and the reverse too.
        mixed = bytearray(self.career)
        mixed[home.RAW:home.RAW + home.SIZE] = self.payload[home.RAW:home.RAW + home.SIZE]
        header = space.scale_music_slots()[0]
        mixed[header:header + 56] = self.payload[header:header + 56]
        mixed[0x11C:0x120] = self.payload[0x11C:0x120]
        self.assertEqual(home.status(bytes(mixed)), 'foreign')
        self.assertEqual(mode.status(bytes(mixed)), 'foreign')

    def test_code_writes_only_stack_buffers_and_the_descriptor_handler_word(self):
        """The memory-writes gate for this section: no absolute store anywhere in the machine code (it keeps all state
        on the stack); register-relative stores are the string builders' caller buffers and the two handler-word
        stores in home_handler (its own RWX descriptors and MyCareer's RW Apartment descriptor)."""
        from mod_editor.core import nfl2k5_my_career_home_code as assembly
        from mod_editor.core.nfl2k5_cave_oracle import absolute_writes
        end = assembly.LABELS['home_rodata']
        findings = absolute_writes(self.payload, [(home.CONTENT_VA, home.CONTENT_VA + end)])
        self.assertFalse([f for f in findings if f['detail'] == 'undecoded trailing bytes'])
        self.assertEqual([f for f in findings if f['target'] is not None], [])
        starts = sorted((v, k) for k, v in assembly.LABELS.items() if v < end)
        def owner(va):
            offset = va - home.CONTENT_VA
            return [k for v, k in starts if v <= offset][-1]
        other = {owner(int(f['instruction'], 16)) for f in findings
                 if 'esp' not in f['detail'] and 'ebp' not in f['detail']}
        self.assertLessEqual(other, {'home_handler', 'put', 'ascii', 'number', 'stat_line', 'home_panel'})
        handler = [f['detail'] for f in findings if owner(int(f['instruction'], 16)) == 'home_handler']
        labels = home.code_for(home.career_labels(self.payload))[1]
        self.assertEqual(handler, [f'mov dword ptr [eax + 8], {home.career_labels(self.payload)["mode_handler"]:#x}',
                                   f'mov dword ptr [eax + 8], {labels["home_handler"]:#x}'])

    def test_music_section_and_career_home_are_exclusive(self):
        from mod_editor.core import nfl2k5_music_storage as music
        with_music, _ = music.install(self.career, b'synthetic music records')
        self.assertTrue(space.has_music(with_music))
        self.assertEqual(home.status(with_music), 'retail')
        with self.assertRaises(ValueError):
            home.apply(with_music)
        with self.assertRaises(ValueError):
            music.install(self.payload, b'synthetic music records')


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST, FONT and Unicorn required')
class CareerHomeNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_my_career_navigation_fixture import resources
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        from nfl2k5_scorebug_projection import read_fonts
        cls.payload = home.apply(mode.apply(retail_bytes())[0])[0]
        cls.labels = home.code_for(home.career_labels(cls.payload))[1]
        cls.roster, cls.evidence = retail_roster(), resources()
        try:
            cls.fonts = read_fonts(XBE.parent / 'vc_53450030/0')
        except (OSError, ValueError) as exc:
            raise unittest.SkipTest(f'pinned retail FONT evidence unavailable: {exc}') from exc

    def machine(self, *, club=15, position=0, textures=True):
        from tests.nfl2k5_my_career_home_fixture import Machine
        m = Machine(self.payload)
        player = m.create(self.roster, club=club, position=position)
        m.capture(self.fonts, self.evidence, textures=textures)
        return m, player

    def dialogs(self, m):
        texts = []

        def ask():
            raw = bytes(m.uc.mem_read(m.reg('EDX'), 200))
            end = next(i for i in range(0, len(raw), 2) if raw[i:i + 2] == b'\0\0')
            texts.append(raw[:end].decode('utf-16le'))
            m.ret(m.dialog_answer, pop=24)
        m.replace_stub(0x14E440, ask)
        return texts

    def inside(self, shot):
        x0, y0, x1, y1 = PANEL
        for strip in shot['quads'] + shot['glyphs']:
            for x, y, *_ in strip['verts']:
                self.assertTrue(x0 <= x <= x1 and y0 <= y <= y1, (x, y))

    def test_opening_career_home_draws_rows_tint_and_the_live_panel(self):
        m, player = self.machine()
        with m:
            self.assertEqual(m.top(), m.labels['apartment'])
            m.season_stats({4: 187, 35: 289, 76: 2214, 64: 17, 22: 6})
            m.put(m.manager + 8 * m.depth() + 4, 0)
            shot = m.screen()
            # Five sections and Quit, all inside the native seven-row window, the cursor tinted by MyCareer's hook.
            self.assertEqual(shot['rows'], HOME_ROWS)
            self.assertEqual(shot['selected'], ['Play next game'])
            self.assertEqual(m.get(m.labels['apartment'] + 8), self.labels['home_handler'])
            texts = [t['text'] for t in shot['texts']]
            team = m.get(m.root + 0x1C) + 15 * 500
            self.assertEqual(texts[1], 'QB  New York Giants')
            self.assertEqual(texts[2], str(m.call(0x246D90, ecx=player, edx=0)))
            self.assertEqual(texts[3:8], ['OVERALL', '0', 'XP', 'QB1', 'STARTER'])
            self.assertEqual(texts[8], 'NEXT GAME')
            slot = m.call('mode_next_fixture')
            row = bytes(m.uc.mem_read(0xE57C40 + 8 * slot, 8))
            nick = lambda i: m.string(m.get(m.get(0xE5786C + 4 * i) + 0x104))
            self.assertEqual(texts[9], f'{nick(row[2])} at {nick(row[1])}')
            self.assertTrue(texts[10].startswith(f'Week {slot // 17 + 1}. {row[3]}/{row[4]}/'))
            self.assertEqual(texts[11:], ['THIS SEASON', '187/289  2214 YDS  17 TD  6 INT'])
            self.inside(shot)
            # Club colours come from the retail accessors; every owned quad keeps the font's registered draw key.
            primary, secondary = m.call(0x68D70, ecx=team), m.call(0x68DC0, ecx=team)
            header = shot['quads'][0]
            self.assertEqual([v[4] & 0xFFFFFF for v in header['verts']],
                             [primary & 0xFFFFFF, secondary & 0xFFFFFF] * 2)
            key = m.get(m.get(0xA90ECC) + 0x44)
            self.assertTrue(all(q['key'] == key and q['primitive'] == 6 and q['vertex_mode'] == 0
                                and q['matrix'] == 0 and len(q['verts']) == 4 for q in shot['quads']))
            # Full-colour art: resident front-end textures found by name; nothing else is loaded.
            self.assertEqual(set(m.lookups), {'ghostlogo_h', 'position_photos_qb'})
            textured = {q['texture'] for q in shot['quads'] if q['texture']}
            self.assertEqual(textured, set(m.lookups.values()))
            photo = next(q for q in shot['quads'] if q['texture'] == m.lookups['position_photos_qb'])
            self.assertEqual([(v[5], v[6]) for v in photo['verts']], [(0, 0), (1, 0), (0, 1), (1, 1)])

    def test_every_career_home_row(self):
        m, player = self.machine()
        with m:
            pushed, cards = [], []
            m.select(0)
            self.assertEqual(m.top(), TEAM_SELECT)
        m, player = self.machine()
        with m:
            m.replace_stub(0x6E390, lambda: (pushed.append(m.reg('EDX')), m.ret()))
            m.select(1)
            self.assertEqual(pushed, [m.labels['practice_menu']])
            m.replace_stub(0x6E390, None)
            m.replace_stub(0x320E90, lambda: (cards.append(m.reg('EDX')), m.ret(pop=4)))
            m.select(2)
            self.assertEqual(cards, [player])
            m.select(3)
            self.assertEqual(m.top(), m.labels['m3_upgrade_menu'])
            m.frame(0x200)  # B: native back (with Career Home, Upgrades has the back flag)
            self.assertEqual(m.top(), m.labels['apartment'])
            m.select(4)
            self.assertEqual(m.top(), self.labels['home_options'])
            self.assertEqual(m.screen()['rows'], OPTION_ROWS)
            m.frame(0x200)
            self.assertEqual(m.top(), m.labels['apartment'])
            texts = self.dialogs(m)
            m.dialog_answer = 3  # No
            m.select(5)
            self.assertEqual((m.top(), len(texts)), (m.labels['apartment'], 1))
            m.dialog_answer = 2  # Yes
            m.select(5)
            self.assertEqual((m.depth(), m.top()), (0, MAIN_MENU))
            self.assertEqual(m.get(m.state + 2672), 0)

    def test_settings_save_sub_list_and_classic_apartment(self):
        m, player = self.machine()
        with m:
            m.select(4)
            m.select(0)
            self.assertEqual(m.top(), m.labels['m3_settings_menu'])
            m.frame(0x200)
            self.assertEqual(m.top(), self.labels['home_options'])
            pushed = []
            m.replace_stub(0x6E390, lambda: (pushed.append(m.reg('EDX')), m.ret()))
            m.select(1)
            self.assertEqual(pushed, [SAVE_LOAD])
            m.replace_stub(0x6E390, None)
            started = []
            m.replace_stub(m.labels['start_player'], lambda: (started.append(1), m.ret()))
            m.select(3)
            self.assertEqual(started, [1])
            m.replace_stub(m.labels['start_player'], None)
            m.select(4)
            self.assertEqual(m.top(), self.labels['home_classic'])
            shot = m.screen()
            self.assertEqual(shot['rows'], CLASSIC_ROWS)  # the old nine-row Apartment, seven visible
            texts = [t['text'] for t in shot['texts']]
            self.assertEqual(len(texts), 2)
            self.assertIn('Off field: CPU plays', texts[0])
            self.assertTrue(texts[1].startswith('Week '))
            self.assertEqual(shot['quads'], [])
            m.frame(0x200)  # B from the Classic Apartment returns to the sub-list
            self.assertEqual(m.top(), self.labels['home_options'])
            m.select(5)  # Back
            self.assertEqual(m.top(), m.labels['apartment'])
            m.select(4)
            m.frame(0x200)  # B from the sub-list returns to Career Home
            self.assertEqual(m.top(), m.labels['apartment'])
            m.select(4)
            m.select(2)  # Sim to next appearance
            self.assertEqual(m.top(), TEAM_SELECT)
            self.assertEqual((m.get(m.state + 2696), m.get(m.state + 2708)), (2, 1))

    def test_b_on_career_home_asks_then_quits(self):
        m, _ = self.machine()
        with m:
            texts = self.dialogs(m)
            m.dialog_answer = 3
            m.frame(0x200)
            self.assertEqual(m.top(), m.labels['apartment'])
            m.dialog_answer = 2
            m.frame(0x200)
            self.assertEqual((m.depth(), m.top()), (0, MAIN_MENU))
            # The native quit question both times, then the game's own default-roster restore notice.
            self.assertEqual(texts[0], texts[1])
            self.assertIn('Quit now?', texts[0])

    def test_a_pad_in_port_2_drives_career_home_and_owns_myplayer(self):
        m, _ = self.machine()
        with m:
            port = 1  # Noah's pad: port 2; port 1 stays connected but idle
            m.replace_stub(0x709B0, lambda: m.ret(int(m.reg('ECX') in (0, port))))
            for va in (0xF3750, 0xF3780, 0xF3720):
                m.replace_stub(va, lambda: m.ret(m.inputs if m.reg('EDX') == port else 0, pop=4))
            for va in (0x70A10, 0x70A30, 0x709F0):
                m.replace_stub(va, lambda: m.ret(m.inputs if m.reg('ECX') == port else 0))
            m.select(4)
            self.assertEqual(m.top(), self.labels['home_options'])
            m.frame(0x200)
            self.assertEqual(m.top(), m.labels['apartment'])
            m.select(0)
            self.assertEqual(m.top(), TEAM_SELECT)
            self.assertEqual(m.get(m.state + 32), port)

    def test_backup_depth_long_name_and_other_positions_fit_the_panel(self):
        for club, position, stats, last in ((0, 0, {}, 'Abcdefghijklmnop'), (19, 3, {46: 64, 79: 911, 62: 7}, None),
                                            (28, 11, {50: 188, 47: 19, 23: 12}, None), (4, 13, {99: 17}, None)):
            with self.subTest(club=club, position=position):
                m, player = self.machine(club=club, position=position)
                with m:
                    m.season_stats(stats)
                    if last:
                        name = m.get(player + 20)
                        m.uc.mem_write(name, (last + '\0').encode('utf-16le'))
                    if position == 0:
                        m.put(m.state + 2744, 1)
                        m.put(m.state + 184, 1)
                        m.uc.mem_write(player + 41, bytes(((m.uc.mem_read(player + 41, 1)[0] & 3) | 0x24,)))
                    shot = m.screen()
                    self.assertEqual(shot['rows'], HOME_ROWS)
                    self.inside(shot)
                    texts = [t['text'] for t in shot['texts']]
                    if position == 0:
                        self.assertEqual(texts[6:8], ['QB2', 'BACKUP'])
                        self.assertEqual(texts[0], 'F. ' + last)
                    if position == 13:  # linemen have no position photo
                        self.assertNotIn('position_photos', ' '.join(m.lookups))
                    if position == 11:
                        self.assertEqual(texts[-1], '188 TKL  9.5 SACK  12 INT')

    def test_missing_art_or_font_skips_without_faulting(self):
        m, _ = self.machine(textures=False)
        with m:
            shot = m.screen()
            self.assertEqual(shot['rows'], HOME_ROWS)
            self.assertFalse(any(q['texture'] for q in shot['quads']))
            self.assertTrue(shot['quads'])
            m.put(0xA90ECC, 0)  # the panel's material source (font slot 0) absent: no quads, text still drawn
            shot = m.screen()
            self.assertEqual(shot['quads'], [])
            self.assertTrue(shot['texts'])
            self.assertEqual(m.get(m.labels['apartment'] + 8), self.labels['home_handler'])


if __name__ == '__main__':
    unittest.main()
