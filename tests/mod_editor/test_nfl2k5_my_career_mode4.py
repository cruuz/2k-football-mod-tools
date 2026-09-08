"""Native list glyphs, selection, presentation and abandoned-fixture proofs.

EXPERIMENTAL / UNWITNESSED. GPU/model submissions and scene services are
bounded fixture boundaries. No display, game boot, whole pack or disc copy.
"""
from pathlib import Path
import hashlib
import json
import math
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_my_career_mode4_fixture import Machine
from tests.nfl2k5_my_career_navigation_fixture import install as navigation, resources
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST, FONT and Unicorn required')
class Mode4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16 * 1024**2:
            raise unittest.SkipTest('retail XBE exceeds 16 MiB')
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('USA retail XBE pin differs')
        cls.roster = retail_roster()
        cls.navigation = resources()
        from nfl2k5_scorebug_projection import read_fonts
        try:
            cls.fonts = read_fonts(XBE.parent / 'vc_53450030/0')
        except (OSError, ValueError) as exc:
            raise unittest.SkipTest(f'pinned bounded retail FONT evidence unavailable: {exc}') from exc
        cls.payload = mode.apply(cls.retail)[0]
        union = json.loads((ROOT / 'tests/fixtures/nfl2k5_allocator_beta62_requests.json').read_text())
        cls.union = mode.apply(mode.space.apply(cls.retail, union, scaleout=True)[0])[0]

    def glyphs(self, draws):
        draws = [d for d in draws if d['text'].strip()]
        for draw in draws:
            self.assertEqual(draw['color'], 0xFFFFFFFF)
            self.assertTrue(draw['vertices'], draw['text'])
            self.assertTrue(all(math.isfinite(v) for p in draw['vertices'] for v in p))
            self.assertTrue(all(20 <= p[0] <= 620 and 20 <= p[1] <= 475
                                for p in draw['vertices']), draw['text'])
        return draws

    def team_screen(self, m):
        m.frontend(self.roster)
        for rng in (0xB12680, 0xE5FCA0):
            m.call(0x48BE0, ecx=rng, edx=12345)
        m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
        m.select(1)
        m.select(1)
        for _ in range(4):
            m.frame(0x10)
        self.assertEqual(m.top(), m.labels['team_menu'])
        m.fonts(self.fonts)
        navigation(m, self.navigation)

    def test_club_native_draw_all_32_back_and_confirmed_club_signed(self):
        for payload in (self.payload, self.union):
            with self.subTest(layout=mode.legacy.allocations(payload)[0]['va']), Machine(payload) as m:
                self.team_screen(m)
                m.select(0)
                self.assertEqual(m.top(), m.labels['club_menu'])
                draws = self.glyphs(m.draw())
                names = [m.string(m.get(m.get(m.root + 0x1C) + i * 500 + 0x104)) for i in range(32)]
                self.assertEqual(draws, [])  # no second owned list
                self.assertEqual({r['text'] for r in m.native_rows}, set(names[:7]))
                self.assertEqual(m.get(0xC8E1D0), 7)  # retail scrolling window
                m.frame(0x200)
                self.assertEqual(m.top(), m.labels['team_menu'])
                self.assertEqual(m.get(m.state + 2680), 2)
                # Every choice uses A and the native stack, including the last.
                for club in range(32):
                    m.select(0)
                    m.draw()  # native MRKS establishes the visible row count
                    m.put(m.manager + 8*m.depth() + 4, club)
                    m.frame()
                    m.native_rows.clear()
                    self.assertEqual(m.draw(), [])
                    opaque = [r for r in m.native_rows if r['color'] >> 24 == 255 and r['text']]
                    self.assertEqual(len({r['text'] for r in opaque}), len(opaque))
                    self.assertEqual([r['text'] for r in opaque if r['color'] == 0xFFFFFF00], [names[club]])
                    m.select(club)
                    self.assertEqual(m.top(), m.labels['team_menu'])
                    self.assertEqual(m.get(m.state + 2684), club)
                player = m.get(m.state + 2676)
                m.select(1, budget=500000000)
                self.assertEqual(m.top(), m.labels['apartment'])
                self.assertEqual(m.get(m.state + 56), 31)
                team = m.get(m.root + 0x1C) + 31 * 500
                self.assertEqual(sum(m.get(team + 4*i) == player for i in range(65)), 1)
                self.assertEqual(m.call('primary'), player)

    def test_apartment_draw_before_and_after_native_quit_and_first_fixture(self):
        with Machine(self.payload) as m:
            m.create(self.roster, club=0)
            m.fonts(self.fonts)
            navigation(m, self.navigation)
            self.assertEqual(m.get(0xE576A4), 7)
            slot = m.call('mode_next_fixture')
            self.assertEqual(slot // 17, 1)
            self.assertEqual(m.get(0xE576B4), 0)
            expected = ['Play next game', 'Practice', 'MyPlayer', 'Start MyPlayer', 'Save', 'Quit to main menu']
            draws = self.glyphs(m.draw())
            self.assertEqual({r['text'] for r in m.native_rows if r['text']}, set(expected))
            self.assertEqual(len(draws), 1)  # fixture footer only
            self.assertIn('49ers', draws[-1]['text'])
            self.assertIn('Off field: CPU plays', draws[-1]['text'])
            # Negative control: removing our callback removes only the
            # footer. Native rows still submit through the loaded layout.
            m.put(m.labels['apartment'] + 8, 0xF3E90)
            m.native_rows.clear()
            self.assertEqual(m.draw(), [])
            self.assertEqual({r['text'] for r in m.native_rows if r['text']}, set(expected))
            m.put(m.labels['apartment'] + 8, m.labels['mode_handler'])
            m.child_services()
            for va in (0x771F0, 0x77200):
                m.replace_stub(va, None)
            grid = bytes(m.uc.mem_read(0xE57C40, 374 * 8))
            simulated = []
            m.stubs.append(m.uc.hook_add(m.u.UC_HOOK_CODE,
                lambda *_: simulated.append((m.reg('ECX'), m.reg('EDX'))),
                begin=0xC7A20, end=0xC7A20))
            m.replace_stub(0x177990, lambda: m.ret(pop=4))  # progress text only
            m.launch(budget=3000000000)
            self.assertEqual(m.get(0xE576B4) * 17 + m.get(0xE576BC), slot)
            self.assertTrue(all(0 not in grid[136*w+8*s+1:136*w+8*s+3] for w, s in simulated))
            self.assertEqual(m.uc.mem_read(0xE57C40 + 8*slot, 8), grid[8*slot:8*slot+8])
            grid = bytes(m.uc.mem_read(0xE57C40, len(grid)))
            # C73B0 imports row[1] with home setter 77AE0, row[2] with
            # away setter 77B20. Check the actual native match identity too.
            own_side = 1 if grid[8*slot+1] == 0 else 2
            self.assertEqual(m.call(0x771F0, ecx=0), own_side)
            self.assertEqual(1 if m.get(m.state + 2564) < 0xB321A0 else 2, own_side)
            m.frame(0x10)
            m.select(12)
            m.select(2)
            m.frame()
            m.frame()
            self.assertEqual(m.top(), m.labels['apartment'])
            self.assertEqual(m.uc.mem_read(0xE57C40, len(grid)), grid)
            self.assertEqual(m.call('mode_next_fixture'), slot)
            m.native_rows.clear()
            self.assertEqual(len(self.glyphs(m.draw())), 1)
            self.assertEqual({r['text'] for r in m.native_rows if r['text']}, set(expected))
            m.select(0)
            self.assertEqual(m.top(), 0x51B908)
            self.assertEqual(m.get(0xE576B4) * 17 + m.get(0xE576BC), slot)

    def test_native_running_result_refusal_and_team_select_defaults_both_sides(self):
        for club, side in ((2, 2), (3, 1)):
            with self.subTest(club=club), Machine(self.payload) as m:
                m.create(self.roster, club=club, preseason=False)
                m.child_services()
                for va in (0x771F0, 0x77200):
                    m.replace_stub(va, None)
                slot = m.call('mode_next_fixture')
                m.launch()
                self.assertEqual(m.call(0x771F0, ecx=0), side)
                self.assertEqual(1 if m.get(m.state + 2564) < 0xB321A0 else 2, side)
                grid = bytes(m.uc.mem_read(0xE57C40, 374 * 8))
                # Explicit boundary hook also works when Unicorn cached the
                # native menu-pop block during earlier stack construction.
                m.stubs.append(m.uc.hook_add(m.u.UC_HOOK_CODE,
                    lambda *_: m.uc.emu_stop(), begin=0xC751B, end=0xC751B))
                for signal in (0, 1, 3):
                    m.put(0xA83A18, signal)
                    m.call(0xC5D60)
                    m.call(0xC74E0, ecx=m.manager, stop=0xC751B)
                    self.assertEqual(m.reg('EAX'), 0)
                    self.assertEqual(m.uc.mem_read(0xE57C40, len(grid)), grid)
                    self.assertEqual(m.get(m.state + 64), 0)
                self.assertEqual(m.call('mode_next_fixture'), slot)

    def test_native_marker_receiver_icons_art_input_and_cpu_flags_both_sides(self):
        for away in (False, True):
            with self.subTest(away=away), Machine(self.payload) as m:
                body, receiver, side = m.presentation(away=away)
                self.assertEqual(m.call(0x75D40, ecx=body), 0)
                m.call(0x75D90)
                self.assertEqual([r[3] for r in m.models], [0, 0])
                self.assertEqual(m.models[1][1], 5)  # native hidden-icon sentinel
                m.models.clear()
                m.call('mode_visuals')
                self.assertEqual([r[3] for r in m.models], [1, 0])
                self.assertEqual(m.models[1][1], 2)
                self.assertEqual((m.get(0xE5FC50), m.get(0xE5FC90)), (0, 0))
                self.assertEqual(m.get(m.get(body + 12)), 0)
                self.assertEqual(m.get(m.get(receiver + 12)), 0xFFFFFFFF)
                self.assertEqual(m.get(side + 0x24), 0)
                m.put(0xA9B95C, 0x6000)
                m.call(0x120A20, args=(0, m.get(body + 12)))
                self.assertEqual(m.get(0xE60264), 0)  # native raw-mask refusal
                m.call(0x1211E0, ecx=0, edx=m.get(receiver + 12))
                self.assertEqual(m.get(0xE60264), 0)  # wrong controller refused
                m.call(0x1211E0, ecx=0, edx=m.get(body + 12))
                self.assertEqual(m.get(0xE60264), 1)
                self.assertEqual(m.get(side + 0x24), 0)
                m.art.clear()
                m.call('mode_visuals')
                self.assertIn(0x182480, m.art)
                self.assertEqual((m.get(0xE5FC50), m.get(0xE5FC90)), (0, 0))

    def test_off_field_footer_and_completion_signal_admission(self):
        with Machine(self.payload) as m:
            body, _, _ = m.presentation()
            m.fonts(self.fonts)
            m.put(body + 0x48, 1)
            m.call('mode_visuals', budget=1000000)
            draws = self.glyphs(m.draws)
            self.assertEqual(draws, [])  # no floating prompt over a live wait
            for signal in range(4):
                m.put(0xA83A18, signal)
                self.assertEqual(m.call('mode_result'), 2 if signal == 2 else 0)
            m.put(m.state, 0)
            for signal in range(4):
                m.put(0xA83A18, signal)
                self.assertEqual(m.call('mode_result'), signal)

    def test_presentation_focus_preserves_retail_and_gameplay_keeps_myplayer(self):
        with Machine(self.payload) as m:
            body, _, _ = m.presentation()
            # These are the actual descriptors selected by A5620's phase table.
            image = XbeImage(self.retail)
            self.assertEqual(struct.unpack('<II', image.read(0x4F0430, 8)), (0x1B, 0xA88460))
            focus = m.BODIES + 0x1D000
            original = (0x3C888889, focus, focus + 16, focus + 32, focus + 48, 0x3F800000)
            for phase in (7, 9, 11, 14, 16):
                m.put(0xB616C0, phase)
                m.call('mode_camera_focus', args=original, stop=0x5F760)
                sp = m.reg('ESP')
                actual = tuple(m.get(sp + 4 + 4*i) for i in range(6))
                expected = list(original)
                if phase != 7:
                    expected[1] = m.get(body + 0x18) + 0x30
                self.assertEqual(actual, tuple(expected))

    def test_native_camera_choice_uses_human_branch_only_while_present(self):
        for away in (False, True):
            with self.subTest(away=away), Machine(self.payload) as m:
                body, _, _ = m.presentation(away=away)
                self.assertEqual((m.get(0xE5FC50), m.get(0xE5FC90)), (0, 0))
                m.call(0x8970B, stop=0x89722)  # native human camera branch
                m.put(body + 0x48, 1)
                m.call(0x8970B, stop=0x8973A)  # native all-CPU presentation
                m.put(m.state, 0)
                m.put(0xE5FC50, 1)
                m.call(0x8970B, stop=0x89722)  # ordinary retail human unchanged

    def test_new_boundaries_refuse_foreign_bytes_and_budget_stays_fixed(self):
        for va in (0x6BC30, 0x75D40, 0x1212A5, 0xC74E3, 0xA88460):
            with self.subTest(va=hex(va)):
                bad = bytearray(self.payload)
                offset = XbeImage(bad).offset(va)
                bad[offset] ^= 1
                # Keep section checks valid so the dependency/hook pin,
                # rather than a stale section digest, must reject this byte.
                from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
                for section in _sections(bad):
                    bad[section.header_offset + 36:section.header_offset + 56] = section_digest(bad, section)
                before = bytes(bad)
                self.assertEqual(mode.status(before), 'foreign')
                with self.assertRaises(ValueError):
                    mode.apply(before)
                self.assertEqual(bytes(bad), before)
        for payload in (self.payload, self.union):
            code, data = mode.legacy.allocations(payload)
            emitted, labels = mode.code_for(code['va'], data['va'])
            self.assertEqual((len(emitted), data['size']), (8192, 4096))
            self.assertLessEqual(labels['content_end'] - code['va'], mode.TAG_OFFSET)
            self.assertEqual(mode.apply(payload)[0], payload)


if __name__ == '__main__':
    unittest.main()
