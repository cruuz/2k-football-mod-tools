"""Native M3 navigation, retail FONT glyphs, calendar and exit ordering.

The GPU submission leaf is captured, with no display or game boot.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_supersim_draft_fixture import retail_bytes, signed_save
from tests.nfl2k5_my_career_draft_fixture import Machine as DraftMachine
from tests.nfl2k5_my_career_mode4_fixture import Machine as FontMachine
from tests.nfl2k5_my_career_navigation_fixture import resources, install as navigation
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


class Machine(DraftMachine, FontMachine):
    pass


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST, FONT, LAYT, MRKS and Unicorn required')
class MenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload, cls.roster = mode.apply(retail_bytes())[0], retail_roster()
        cls.navigation = resources()
        from nfl2k5_scorebug_projection import read_fonts
        try:
            cls.fonts = read_fonts(XBE.parent / 'vc_53450030/0')
        except (OSError, ValueError) as exc:
            raise unittest.SkipTest(f'pinned bounded FONT evidence unavailable: {exc}') from exc

    def install(self, m):
        m.fonts(self.fonts)
        navigation(m, self.navigation)

    def rendered(self, m):
        draws = [d for d in m.draw() if d['text'].strip()]
        for d in draws:
            self.assertTrue(d['vertices'], d['text'])
            self.assertTrue(all(20 <= p[0] <= 620 and 20 <= p[1] <= 475 for p in d['vertices']), d['text'])
        return [d['text'] for d in draws]

    def test_boot_start_and_quit_process_input_before_another_native_week(self):
        with Machine(self.payload) as m:
            m.frontend(self.roster)
            m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
            m.select(1)
            m.select(0, budget=500000000)
            self.assertEqual(m.top(), m.labels['m3_progress_menu'])
            self.assertEqual(m.get(mode.EXTRA_VA), 1)
            self.assertEqual(m.get(0xE576B4), 0)
            def no_week():
                raise AssertionError('Quit processed after another league week')
            m.replace_stub(0x247D40, no_week)
            m.select(0)
            self.assertEqual(m.top(), 0x515660)
            self.assertEqual(m.get(mode.EXTRA_VA), 0)
            self.assertEqual(m.get(0xE576A0), 0)

    def test_calendar_uses_the_next_row_date_and_upgrade_rows_render_once(self):
        with Machine(self.payload) as m:
            p=m.create(self.roster, preseason=False)
            self.install(m)
            slot=m.call('mode_next_fixture')
            for date, expected in ((bytes((12,31,26,23,5)), '12/31/2026 at 23:05'),
                                   (bytes((1,1,27,0,5)), '1/1/2027 at 00:05')):
                m.uc.mem_write(0xE57C40+8*slot+3,date)  # supplied schedule dates
                self.assertTrue(any(expected in t for t in self.rendered(m)))
            m.select(6)
            self.assertEqual(m.top(),m.labels['m3_upgrade_menu'])
            self.rendered(m)
            rows={r['text'] for r in m.native_rows if r['text']}
            self.assertTrue({'Previous attribute','Next attribute','Buy one point','Back'} <= rows)
            selected=m.get(mode.EXTRA_VA+72)
            m.select(1)
            self.assertEqual(m.get(mode.EXTRA_VA+72),(selected+1)%25)
            self.rendered(m)
            m.select(0)
            self.assertEqual(m.get(mode.EXTRA_VA+72),selected)
            m.select(3)
            self.assertEqual(m.top(),m.labels['apartment'])
            self.assertEqual(m.call('primary'),p)

    def test_cancel_creation_retries_existing_class_without_another_season(self):
        signed_save()
        with Machine(self.payload) as m:
            m.prepare_draft(self.roster,complete=False)
            m.frame(0x200)
            self.assertEqual(m.top(),m.labels['entry_menu'])
            self.assertEqual(m.get(mode.EXTRA_VA),2)
            self.assertEqual(bytes(m.uc.mem_read(m.root,0x91000)),m.creation_before)
            def no_restart():
                raise AssertionError('CAP retry restarted the franchise or league')
            for va in (0x13EE10,0x247D40,0x2480B0):m.replace_stub(va,no_restart)
            m.select(0,budget=10000000)
            self.assertEqual(m.top(),0x56F050)
            for _ in range(4):m.frame(0x10)
            self.assertEqual(m.top(),m.labels['m3_prep_menu'])
            self.assertEqual(m.get(m.state+24),2)

    def test_preparation_text_has_real_glyphs_and_save_precedes_next_pick(self):
        signed_save()
        with Machine(self.payload) as m:
            m.prepare_draft(self.roster)
            self.install(m)
            texts=self.rendered(m)
            self.assertTrue(any('MyPlayer is selected' in t for t in texts))
            m.select(0,budget=200000000)
            self.assertEqual(m.top(),m.labels['m3_draft_menu'])
            self.rendered(m)
            def no_pick():
                raise AssertionError('Save processed after an extra draft pick')
            m.replace_stub(0x325B90,no_pick)
            m.select(0)
            self.assertEqual(m.top(),0x507EC8)


if __name__ == '__main__':
    unittest.main()
