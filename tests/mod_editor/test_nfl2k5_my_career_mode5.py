"""Mode 5 native depth, navigation and per-play control boundaries.

EXPERIMENTAL / UNWITNESSED. Uses bounded retail ROST/PLAY/FONT/LAYT/MRKS;
scene inputs are declared, and no full game, display or GPU is executed.
"""
from pathlib import Path
import hashlib
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_my_career_cpu_boundary import Machine
from tests.nfl2k5_my_career_cpu_fixture import retail_playbook
from tests.nfl2k5_my_career_mode4_fixture import Machine as MenuMachine
from tests.nfl2k5_my_career_navigation_fixture import resources, install as navigation
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST, PLAY and Unicorn required')
class Mode5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16 * 1024**2:
            raise unittest.SkipTest('retail XBE exceeds 16 MiB')
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('USA retail XBE pin differs')
        cls.payload = mode.apply(cls.retail)[0]
        cls.roster, cls.book = retail_roster(), retail_playbook()

    def test_all_17_positions_sign_as_starter_restore_and_are_idempotent(self):
        for pos in range(17):
            with self.subTest(position=pos), Machine(self.payload) as m:
                p = m.create(self.roster, position=pos, club=22, preseason=False)
                team = m.get(m.state + 2588)
                peers = [m.get(team + 4*i) for i in range(m.uc.mem_read(team+0x11C,1)[0])]
                peers = [q for q in peers if m.uc.mem_read(q+53,1)[0] == pos]
                rank = lambda q: (m.uc.mem_read(q+41,1)[0] >> 2) & 7
                self.assertEqual(rank(p), 0)
                self.assertTrue(all(rank(q) > 0 for q in peers if q != p))
                self.assertTrue(any(rank(q) == 1 for q in peers if q != p))
                self.assertEqual(m.uc.mem_read(p+82,1)[0] & 3, 3)
                original = bytes(m.uc.mem_read(m.root, 0x91000))
                m.select(3)
                self.assertEqual(m.top(), m.labels['apartment'])
                self.assertEqual(m.uc.mem_read(m.root, len(original)), original)
                displaced = next(q for q in peers if q != p and rank(q) == 1)
                # Declared later manual depth edit. Restore through native A.
                m.uc.mem_write(p+41, bytes(((m.uc.mem_read(p+41,1)[0]&3)|0x24,)))
                m.uc.mem_write(displaced+41, bytes((m.uc.mem_read(displaced+41,1)[0]&3,)))
                m.select(3)
                self.assertEqual((rank(p), rank(displaced)), (0, 1))
                for q in peers:
                    if q not in (p, displaced):
                        self.assertEqual(m.uc.mem_read(q,84), original[q-m.root:q-m.root+84])

    def test_native_free_practice_starters_and_calling_on_both_units(self):
        for pos in (0, 3, 4, 16):
            with self.subTest(position=pos), Machine(self.payload) as m:
                m.create(self.roster, position=pos, club=22, preseason=False)
                m.child_services()
                m.cpu_scene(self.book, benched=False, practice=True)
                self.assertNotEqual(m.get(0xB30864), m.get(0xB30A58))
                m.call(0xA11F0, budget=20000000)
                body = m.call('mode_unit_present')
                self.assertNotEqual(body, 0)
                side = m.get(body + 0x38)
                self.assertEqual(side, m.defense if pos in (4, 16) else m.offense)
                self.assertEqual(m.call(0x1891B0, ecx=side), 1)
                self.assertEqual((m.get(0xE5FC50),m.get(0xE5FC90)), (0,0))
                self.assertEqual(m.get(m.get(body+12)), 0)

    def test_qb_each_play_native_hurry_predicates_and_retail_negative_control(self):
        for club in (2, 22):
            with self.subTest(club=club), Machine(self.payload) as m:
                m.create(self.roster, club=club, preseason=False)
                m.child_services()
                m.cpu_scene(self.book, benched=False)
                m.offense, m.defense = m.defense, m.offense
                m.put(0xE60280,m.offense); m.put(0xE60284,m.defense); m.put(0xE60288,m.offense)
                m.call(0xE9460,ecx=m.offense,edx=1 if m.offense == 0xE5FC20 else 0xFFFFFFFF)
                visits = m.observe((0x1531F0, 0x189DA6, 0x189270, 0xA3105))
                # Explicit block boundaries also stop previously cached TBs.
                for play in range(4):
                    m.call(0xA11F0, budget=20000000)
                    self.assertEqual(m.call(0x1891B0, ecx=m.offense), 1)
                    self.assertEqual(m.get(m.get(m.offense+12)+36)&8, 0)
                    self.assertNotIn(0x1531F0, visits)  # no automatic offense choice
                    for quarter in (1,2,4):
                        m.put(0xE602C4, quarter)
                        m.f32(m.get(0xE6028C)+16, 30)
                        self.assertEqual(m.call(0x189D10,ecx=m.offense,budget=1000000),0)
                    self.assertNotIn(0x189DA6, visits)  # CPU strategy never entered
                    self.assertNotIn(0x189270, visits)  # no forced hurry-up
                    halt = m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: m.uc.emu_stop(),
                                         begin=0xA3157, end=0xA3157)
                    try:
                        m.call(0xA30FE,esi=m.offense,stop=0xA3157)
                    finally:
                        m.uc.hook_del(halt)
                    self.assertNotIn(0xA3105, visits)
                    m.call(0x189080, ecx=m.offense,budget=1000000)
                # Revert just each missed mode-4 MOV/TEST in this fixture.
                # The real branch now takes the CPU path for the same bound QB.
                for site, stop in ((0x189D9B,0x189DA6),(0xA30FE,0xA3105)):
                    m.stubs.append(m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: m.uc.emu_stop(), begin=stop, end=stop))
                    m.uc.mem_write(site, XbeImage(self.retail).read(site,5))
                    m.uc.ctl_remove_cache(site,site+16)
                    m.call(site,esi=m.offense,stop=stop)
                    self.assertEqual(m.reg('EIP'), stop)
                self.assertEqual(m.call('mode_human',ecx=m.offense),1)

    def test_every_owned_list_uses_native_bindings_and_scopes_yellow(self):
        from nfl2k5_scorebug_projection import read_fonts
        try:
            fonts = read_fonts(XBE.parent / 'vc_53450030/0')
        except (OSError, ValueError) as exc:
            self.skipTest(f'pinned retail FONT evidence unavailable: {exc}')
        with MenuMachine(self.payload) as m:
            m.frontend(self.roster); m.fonts(fonts)
            m.call(0x6E390,ecx=m.manager,edx=0x5015CC); m.select(1)
            navigation(m, resources())
            # Native navigation displays seven rows at a time. Supersim is
            # the eighth Apartment row; its scroll/selection has its own test.
            for label, count in (('entry_menu',4),('apartment',7),('team_menu',2)):
                # Existing initialized owned descriptors, native stack replace.
                m.call(0x6E2E0,ecx=m.manager,edx=m.labels[label])
                m.put(m.manager+8*m.depth()+4,1)
                m.native_rows.clear(); m.draw()
                rows=[r for r in m.native_rows if r['text'] and r['color']>>24==255]
                self.assertEqual(len(rows),count)
                self.assertEqual(len({r['text'] for r in rows}),count)
                self.assertEqual(sum(r['color']==0xFFFFFF00 for r in rows),1)
                self.assertTrue(all(d['text'] not in {r['text'] for r in rows} for d in m.draws))
                m.put(m.labels[label]+8,0xF3E90)
                m.native_rows.clear(); m.draw()
                self.assertFalse(any(r['color']==0xFFFFFF00 for r in m.native_rows))
                m.put(m.labels[label]+8,m.labels['mode_handler'])


if __name__ == '__main__':
    unittest.main()
