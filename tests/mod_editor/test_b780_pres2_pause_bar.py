"""b780 pres2 (Q51): the pause menu shows the score, under the 2026 bar.

On SOFTDRINK discs the Paused menu showed no score. The scorebug owner turns the retail play-call panel draw (0x8CA00) off
at 0x8CA18, and the Paused menu's backdrop (0x6BEF0 -> 0x64FE0) never calls the HUD draw (FC360, which only the in-game draw
0x646B0 calls), so neither bar drew. Revision 17 hooks the backdrop's one call to 0x8CA00 (0x65092): the stub makes that call
(the panel stays off) and then the engine draws the 2026 bar with the HUD draw, moved into the band above the menu panel
(the PAUSED banner sits where the bar draws in play).

Everything here that needs a retail executable runs on the pinned USA XBE; the engine cases run the real owner code in Unicorn.
"""
from __future__ import annotations

import hashlib
import importlib.util
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests/mod_editor')]
from mod_editor.core import nfl2k5_scorebug_runtime as owner  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_ingame as scene  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402
from test_nfl2k5_franchise_records import XBE, HAVE_UC, _Season, _retail  # noqa: E402

PAUSE_COUNTER, BACKDROP_FLAG, GATE, HUD_DRAW, PANEL_DRAW = 0xA83A14, 0xA83F14, 0xA95524, 0xFC360, 0x8CA00
PAUSE_TOP = 21845                      # packed scene y 380 = HUD line 44 (scene y = 424 - HUD line)
MAGIC, TABLE = 0x35525053, 16512
CODE_VA, DATA_VA, SCENE_VA = 0x5100000, 0x5200000, 0x3010000
GUARD = bytes.fromhex('e92205000090')  # the owner's jump at 0x8CA18 (retail: je 0x8CF3F)

# Retail spans the fix relies on (SHA-256 only).
PINS = {
    'IsPaused 0x64BE0 (the pause counter above zero)': (0x64be0, 0x0e, '561d264021ca63781f935e1a5f9183067aad46abd24f5792bdccdbb4d3651220'),
    'menu backdrop 0x6BEF0: IsPaused, [0xA83F14] == 1, call 0x64FE0': (0x6bef0, 0x29, '7018400ba106fe1be62cbf886de3595a4d83da8b54862afc6ddca386c3e9d0ab'),
    'paused backdrop 0x64FE0 end: camera, call 0x8CA00, epilogue': (0x65081, 0x1a, '5008bf5ef9e9a730ed8e19eb8e9513126fab8d4022ca67baa85e8b59a2e44795'),
    'in-game HUD draw 0x646B0: the only caller of FC360, and a call of 0x8CA00': (0x646b0, 0x5e, '4e61670836a6e13cfbf2a490ac036ffa0fabb0a8e9bde945e49a1d9d04fc06b3'),
    'HUD draw FC360 entry: [0xA95520], the draw gate [0xA95524], layer predicate': (0xfc36c, 0x2a, '3374b2e1a06bb4a258ea1f0c99ba90ac230137852c5a8cd9b5a7b8deb1703000'),
    'HUD hide FC6B0: clears the draw gate': (0xfc6b0, 0x0d, '743b31b02d89c4d0980271f20354f428e253fe851fc46c018346e608b67c72ef'),
    'panel draw 0x8CA00 exit': (0x8cf3f, 0x08, '4af066e9babe398f7a2680a76d6d195edcf6dd4d57fec3c2d0633d81f4339a07'),
}


def rel_target(site, call):
    return site + 5 + struct.unpack('<i', call[1:5])[0]


class SourceTests(unittest.TestCase):
    def test_revision_allocation_and_state(self):
        self.assertEqual(owner.REVISION, 17)
        self.assertEqual(owner.CODE_SIZE, 6336)
        code, labels = owner.code_for(CODE_VA, DATA_VA)
        self.assertEqual(len(code), owner.CODE_SIZE)
        self.assertGreater(owner.CODE_SIZE - len(code.rstrip(b'\xcc')), 8)      # the older suites keep at least nine spare bytes
        # The engine's State is 124 bytes: 124..127 of the 128-byte page is the play-call strip flag.
        self.assertEqual(owner.playcall_layout.STRIP_FLAG_OFFSET, 124)
        source = (ROOT / 'tools/scorebug_sprite/runtime.c').read_text()
        self.assertIn('_Static_assert(sizeof(struct State)==124', source)

    def test_generated_engine_matches_its_source(self):
        import shutil
        if not shutil.which('gcc'):
            self.skipTest('gcc absent')
        spec = importlib.util.spec_from_file_location('b780_pres2_build_runtime', ROOT / 'tools/scorebug_sprite/build_runtime.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.TARGET.read_text(), module.generate(), 'rebuild with tools/scorebug_sprite/build_runtime.py')

    def test_the_panel_stays_off_and_the_gamecast_panel_stays_retail(self):
        self.assertEqual([(va, old.hex(), new.hex()) for va, old, new, _ in owner.PLAYCALL_EDITS],
                         [(0x8CA18, '0f8421050000', 'e92205000090')])
        self.assertEqual((owner.GAMECAST_PANEL_GATE[0], owner.GAMECAST_PANEL_GATE[1].hex()), (0x8C465, '0f8417050000'))

    def test_the_hook_is_the_backdrops_call_of_the_panel_draw(self):
        va, original = owner.PAUSE_HOOK
        self.assertEqual((va, original.hex()), (0x65092, 'e869790200'))
        self.assertEqual(rel_target(va, original), PANEL_DRAW)
        self.assertEqual(owner.hooks()[owner.PAUSE_HOOK_NAME], owner.PAUSE_HOOK)
        for earlier in owner.EARLIER_REVISIONS:
            self.assertNotIn(owner.PAUSE_HOOK_NAME, owner.hooks(earlier))

    def test_the_stub_calls_the_panel_draw_first_then_the_engine_and_returns(self):
        code, labels = owner.code_for(CODE_VA, DATA_VA)
        at = labels[owner.PAUSE_HOOK_NAME] - CODE_VA
        stub = code[at:at + 64]
        self.assertEqual(rel_target(labels[owner.PAUSE_HOOK_NAME], stub[:5]), PANEL_DRAW)
        self.assertEqual(stub[5:7].hex(), '9c60')                      # pushfd; pushad: the saved frame, as every owner hook
        end = stub.index(b'\xc3', 7)
        body = stub[:end + 1]
        self.assertIn(b'\x68' + struct.pack('<I', DATA_VA), body)        # push the owner's data page (the engine State)
        draw = labels['sprite_pause_draw']
        calls = [i for i in range(len(body) - 4) if body[i] == 0xE8 and rel_target(labels[owner.PAUSE_HOOK_NAME] + i, body[i:i + 5]) == draw]
        self.assertEqual(len(calls), 1)
        self.assertEqual(body[-1], 0xC3)

    def test_earlier_bodies_rebuild_at_their_size_and_engines_are_frozen(self):
        from mod_editor.core import nfl2k5_scorebug_sprite_code as now
        from mod_editor.core import nfl2k5_scorebug_sprite_code_r16 as r16
        from mod_editor.core import nfl2k5_scorebug_sprite_code_r15 as r15
        for earlier in owner.EARLIER_REVISIONS:
            body, labels = owner.code_for(CODE_VA, DATA_VA, earlier)
            self.assertEqual(len(body), owner.EARLIER_CODE_SIZE)
            self.assertNotIn(owner.PAUSE_HOOK_NAME, labels)
            self.assertNotIn('sprite_pause_draw', labels)
        self.assertNotIn('sprite_pause_draw', r16.LABELS)
        self.assertEqual(len(r16.CODE), len(r15.CODE))
        # Revision 15 -> 16 changed the play-call guard's address (0x8C465 -> 0x8CA18): two bytes of the engine.
        self.assertEqual(sum(a != b for a, b in zip(r15.CODE, r16.CODE)), 2)
        self.assertGreater(len(now.CODE), len(r16.CODE))
        with self.assertRaises(ValueError):
            owner.code_for(CODE_VA, DATA_VA, 14)


@unittest.skipUnless(XBE.is_file() and _retail() is not None, 'pinned USA XBE required')
class RetailPremiseTests(unittest.TestCase):
    def test_every_relied_on_span_matches_its_pin(self):
        from test_nfl2k5_franchise_records import XbeImage
        image = XbeImage(_retail())
        for name, (va, size, digest) in PINS.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256(image.read(va, size)).hexdigest(), digest)

    def test_the_paused_backdrop_never_draws_the_hud_and_the_in_game_draw_does(self):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        retail = _retail()
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.skipdata = True

        def calls(start, end):
            off = scene.layout.sbpos.va_to_off(retail, start)
            return [rel_target(i.address, bytes(i.bytes)) for i in md.disasm(retail[off:off + end - start], start)
                    if i.mnemonic == 'call' and len(i.bytes) == 5]
        paused = calls(0x64fe0, 0x6509b)                       # the whole of the paused backdrop 0x64FE0
        in_game = calls(0x646b0, 0x64710)
        self.assertIn(PANEL_DRAW, paused)
        self.assertNotIn(HUD_DRAW, paused)
        self.assertIn(HUD_DRAW, in_game)
        self.assertEqual(calls(0x64fe0, 0x6509b).count(PANEL_DRAW), 1)


def earlier_install(retail, earlier):
    """What apply() wrote for an earlier revision (its allocation, body, hooks and edits), for the recognizer tests."""
    prepared, _ = scene.apply_xbe(retail)
    prepared, _ = space.apply(prepared, ((owner.OWNER, 'code', owner.EARLIER_CODE_SIZE, 16), (owner.OWNER, 'data', owner.DATA_SIZE, 16)))
    code, data = owner.sites(prepared, earlier)
    body, labels = owner.code_for(code['va'], data['va'], earlier)
    installed, _ = space.install_code(prepared, owner.OWNER, body)
    buf = bytearray(installed)
    for name in owner.hooks(earlier):
        va = owner.hooks(earlier)[name][0]
        off = scene.layout.sbpos.va_to_off(installed, va)
        buf[off:off + 5] = owner.hook_bytes(name, labels, earlier)
    for va, _old, new, _label in owner.override_edits(earlier):
        off = scene.layout.sbpos.va_to_off(installed, va)
        buf[off:off + len(new)] = new
    for s in _sections(buf):
        buf[s.header_offset + 36:s.header_offset + 56] = section_digest(buf, s)
    return bytes(buf)


@unittest.skipUnless(XBE.is_file() and _retail() is not None, 'pinned USA XBE required')
class StatusAndPreviousTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        cls.patched, cls.receipt = owner.apply(cls.retail)

    def at(self, payload, va, n):
        off = scene.layout.sbpos.va_to_off(payload, va)
        return payload[off:off + n]

    def test_this_release_applies_with_the_pause_hook_and_nothing_else_new(self):
        self.assertEqual(owner.status(self.patched), 'applied')
        code, data = owner.sites(self.patched)
        labels = owner.code_for(code['va'], data['va'])[1]
        self.assertEqual(self.at(self.patched, 0x65092, 5), b'\xe8' + struct.pack('<i', labels[owner.PAUSE_HOOK_NAME] - 0x65092 - 5))
        # The 2004 panel stays hidden (the jump at 0x8CA18), the Gamecast's panel draw stays retail.
        self.assertEqual(self.at(self.patched, 0x8CA18, 6), GUARD)
        self.assertEqual(self.at(self.patched, 0x8C465, 6).hex(), '0f8417050000')
        self.assertEqual({e['label'] for e in self.receipt['edits']} & {owner.PAUSE_HOOK_NAME}, {owner.PAUSE_HOOK_NAME})
        self.assertEqual(self.receipt['binding_revision'], 17)
        self.assertEqual(owner.apply(self.patched)[1]['status'], 'already_applied')

    def test_earlier_exact_installs_read_previous_and_are_refused_in_place(self):
        for earlier in owner.EARLIER_REVISIONS:
            with self.subTest(revision=earlier):
                payload = earlier_install(self.retail, earlier)
                self.assertEqual(owner._status(payload, earlier), 'applied')
                self.assertEqual(owner._status(payload), 'foreign')
                self.assertEqual(owner.status(payload), 'previous')
                with self.assertRaisesRegex(ValueError, 'cannot be updated in place'):
                    owner.apply(payload)
                # A flipped byte in the body or a hook is no revision at all.
                code, _data = owner.sites(payload, earlier)
                for off in (code['raw'] + 100, scene.layout.sbpos.va_to_off(payload, owner.HOOKS['update'][0])):
                    bad = bytearray(payload)
                    bad[off] ^= 1
                    for s in _sections(bad):
                        bad[s.header_offset + 36:s.header_offset + 56] = section_digest(bad, s)
                    self.assertEqual(owner.status(bytes(bad)), 'foreign')

    def test_revision_15_keeps_its_gamecast_jump_and_16_does_not(self):
        p15, p16 = (earlier_install(self.retail, n) for n in (15, 16))
        self.assertEqual(self.at(p15, 0x8C465, 6).hex(), 'e91805000090')
        self.assertEqual(self.at(p16, 0x8C465, 6).hex(), '0f8417050000')
        self.assertEqual(owner._status(p16, 15), 'foreign')
        self.assertEqual(owner._status(p15, 16), 'foreign')

    def test_beta_79_still_reads_previous(self):
        from mod_editor.core import nfl2k5_scorebug_runtime_b779 as b779
        self.assertEqual(b779.CODE_SIZE, 5376)
        self.assertIn('beta 79', owner.PREVIOUS_REFUSAL)


class Machine(_Season):
    """The retail image, the owner's code and data page, and a synthetic SPR5 scene (statics, one event quad, the corner mark)."""
    QUADS = 5

    def __init__(self, payload, installed=False):
        """``installed``: the payload carries the applied owner (its real allocation); else the owner's code is mapped aside."""
        super().__init__(payload)
        if installed:
            code, data = owner.sites(payload)
            self.data_va = data['va']
            self.labels = owner.code_for(code['va'], self.data_va)[1]
        else:
            self.data_va = DATA_VA
            self.labels = owner.code_for(CODE_VA, DATA_VA)[1]
            self.uc.mem_map(CODE_VA, 0x2000)
            self.uc.mem_write(CODE_VA, owner.code_for(CODE_VA, DATA_VA)[0])
            self.uc.mem_map(DATA_VA, 0x1000)
        self.fc360 = []
        self.reset()

    def reset(self, bar_y=((-10017, -6457), (-10017, -6457), (-9000, -7000)), mark_y=(22000, 22858), event_y=(-8500, -7500)):
        """Three bar statics, the corner mark (a brand static) and one event quad that is no static."""
        self.uc.mem_write(self.data_va, bytes(128))
        self.uc.mem_write(SCENE_VA, bytes(0x6000))
        self.put(SCENE_VA + 0x60, MAGIC)
        self.put(SCENE_VA + 0x64, TABLE)
        head = SCENE_VA + TABLE
        statics = ((0, 0, 3, 0), (4, 0, 3, 0), (8, 0, 9, 0), (12, 0, 9, TABLE + 0x100))
        self.uc.mem_write(head, struct.pack('<8I', MAGIC, 1, 0, TABLE + 32, len(statics), TABLE + 32, 32 + 16 * len(statics), self.QUADS))
        for i, row in enumerate(statics):
            self.uc.mem_write(head + 32 + 16 * i, struct.pack('<4I', *row))
        ys = list(bar_y) + [mark_y, event_y]
        for q, (lo, hi) in enumerate(ys):
            for j in range(4):
                x = 100 * q + (50 if j & 1 else 0)
                self.uc.mem_write(SCENE_VA + 0x2660 + (4 * q + j) * 6, struct.pack('<3h', x, hi if j & 2 == 0 else lo, -5))
        self.put(0xA95528, SCENE_VA + 256)
        self.put(0xA95520, 0)                   # the bar's HUD is off here: the update runs its restore and timers only
        self.put(GATE, 0)
        self.put(self.data_va, SCENE_VA + 256)
        self.put(self.data_va + 4, 1)
        self.put(PAUSE_COUNTER, 0)
        self.put(BACKDROP_FLAG, 0)
        self.uc.mem_write(0x8CA18, GUARD)
        self.uc.ctl_remove_cache(0x8CA18, 0x8CA1E)
        self.watch()

    def watch(self):
        self.clear_stubs()
        self.fc360.clear()

        def draw(uc, _at, _size, _data):
            self.fc360.append(dict(gate=self.get(GATE), counter=self.get(PAUSE_COUNTER), vertices=self.vertices()))
            sp = self.reg('ESP')
            self.reg('EIP', self.get(sp))
            self.reg('ESP', sp + 4)
        self.hooks.append(self.uc.hook_add(self.u.UC_HOOK_CODE, draw, begin=HUD_DRAW, end=HUD_DRAW))
        self.uc.ctl_remove_cache(HUD_DRAW, HUD_DRAW + 1)

    def vertices(self):
        return [struct.unpack('<3h', bytes(self.uc.mem_read(SCENE_VA + 0x2660 + v * 6, 6))) for v in range(4 * self.QUADS)]

    def quad_tops(self):
        v = self.vertices()
        return [max(y for _x, y, _z in v[4 * q:4 * q + 4]) for q in range(self.QUADS)]

    def pause(self, counter=1, flag=1):
        self.put(PAUSE_COUNTER, counter)
        self.put(BACKDROP_FLAG, flag)

    def shift(self):
        return struct.unpack('<i', bytes(self.uc.mem_read(self.data_va + 120, 4)))[0]

    def state(self):
        return bytes(self.uc.mem_read(self.data_va, 128))

    def draw(self):
        self.call(self.labels['sprite_pause_draw'], args=(self.data_va,))

    def update(self):
        self.call(self.labels['sprite_update'], args=(self.data_va, 0))


@unittest.skipUnless(HAVE_UC and XBE.is_file() and _retail() is not None, 'pinned USA XBE and Unicorn required')
class PauseDrawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = Machine(_retail())

    def setUp(self):
        self.m.reset()

    def test_paused_the_bar_draws_once_with_the_gate_on_at_the_top_and_the_gate_returns(self):
        m = self.m
        before = m.vertices()
        for gate in (0, 1):
            m.reset()
            m.put(GATE, gate)
            m.pause()
            m.draw()
            self.assertEqual(len(m.fc360), 1, 'the HUD draw runs exactly once')
            self.assertEqual(m.fc360[0]['gate'], 1, 'the draw gate is on for that call')
            self.assertEqual(m.get(GATE), gate, 'and goes back to what retail left it')
            tops = m.quad_tops()
            self.assertEqual(max(tops[:3]), PAUSE_TOP, 'the bar sits at the paused top')
            delta = PAUSE_TOP + 6457                          # the bar's own top was -6457
            self.assertEqual(m.shift(), delta)
            moved = m.fc360[0]['vertices']
            for q in (0, 1, 2, 4):                           # three bar statics and the event quad
                for j in range(4):
                    x, y, z = before[4 * q + j]
                    self.assertEqual(moved[4 * q + j], (x, y + delta, z), (q, j))
            self.assertEqual(moved[12:16], before[12:16], 'the corner mark does not move')

    def test_the_bar_lies_in_the_band_above_the_menu_panel(self):
        m = self.m
        m.pause()
        m.draw()
        v = m.fc360[0]['vertices']
        # scene y (packed units -> scene units, then HUD line = 424 - scene y): the bar's quads 0..2 and the event quad
        lines = [424 - (100 + y * 420 / 32767) for q in (0, 1, 2, 4) for _x, y, _z in v[4 * q:4 * q + 4]]
        self.assertGreaterEqual(min(lines), 40)                    # room for the 17-line TIMEOUT tab above it, inside the picture
        self.assertLessEqual(max(lines), 91)                       # the menu panel starts at line 102
        self.assertAlmostEqual(min(lines), 44, delta=0.2)

    def test_not_paused_draws_nothing_and_changes_nothing(self):
        m = self.m
        before, state = m.vertices(), m.state()
        for counter, flag in ((0, 0), (0, 1), (-1, 1), (1, 0), (2, 0)):    # not paused, or paused on the Gamecast's backdrop
            m.watch()
            m.pause(counter, flag)
            m.draw()
            self.assertEqual(m.fc360, [], (counter, flag))
            self.assertEqual((m.vertices(), m.state(), m.get(GATE)), (before, state, 0), (counter, flag))

    def test_no_scene_no_draw(self):
        m = self.m
        m.pause()
        m.put(m.data_va + 4, 0)                                   # the engine's scene is not active
        m.draw()
        self.assertEqual(m.fc360, [])
        m.put(m.data_va + 4, 1)
        m.put(0xA95528, 0)                                        # no scene resource
        m.draw()
        self.assertEqual(m.fc360, [])

    def test_a_second_paused_frame_does_not_move_the_bar_again(self):
        m = self.m
        m.pause()
        m.draw()
        once = m.vertices()
        m.draw()
        self.assertEqual(m.vertices(), once)
        self.assertEqual(len(m.fc360), 2)

    def test_the_update_keeps_the_bar_while_paused_and_puts_it_back_the_first_frame_after(self):
        m = self.m
        original = m.vertices()
        m.pause()
        m.draw()
        moved = m.vertices()
        self.assertNotEqual(moved, original)
        m.update()
        self.assertEqual(m.vertices(), moved, 'paused: the update leaves the bar')
        m.pause(1, 0)                                             # into the Gamecast: the frozen-game backdrop is gone
        m.update()
        self.assertEqual(m.vertices(), original)
        self.assertEqual(m.shift(), 0)
        m.pause()
        m.draw()
        m.pause(0, 1)                                             # resume
        m.update()
        self.assertEqual(m.vertices(), original)
        self.assertEqual(m.shift(), 0)
        m.update()
        self.assertEqual(m.vertices(), original, 'and it stays')

    def test_a_scene_loaded_since_the_pause_is_left_alone(self):
        m = self.m
        m.put(m.data_va + 120, 12345)                             # state says moved, the scene says otherwise (a fresh load)
        original = m.vertices()
        m.update()
        self.assertEqual(m.vertices(), original)
        self.assertEqual(m.shift(), 0)

    def test_a_bar_already_above_the_paused_top_is_not_moved(self):
        m = self.m
        m.reset(bar_y=((20000, 24000), (20000, 24000), (21000, 23000)))
        before = m.vertices()
        m.pause()
        m.draw()
        self.assertEqual(len(m.fc360), 1)
        self.assertEqual(m.vertices(), before)
        self.assertEqual(m.shift(), 0)

    def test_the_stub_at_the_hook_site_runs_the_retail_panel_off_and_the_bar_on(self):
        """The applied executable: the backdrop's tail (call at 0x65092, then its epilogue) reaches the stub; the panel draw
        exits at the owner's jump (none of its body runs) and the bar draws only while paused."""
        patched, _ = owner.apply(_retail())
        m = Machine(patched, installed=True)
        site = scene.layout.sbpos.va_to_off(patched, 0x65092)
        self.assertEqual(rel_target(0x65092, patched[site:site + 5]), m.labels[owner.PAUSE_HOOK_NAME])
        panel_body = []
        m.hooks.append(m.uc.hook_add(m.u.UC_HOOK_CODE, lambda _u, at, _s, _d: panel_body.append(at), begin=0x8CA1E, end=0x8CF3E))
        for paused in (False, True, False):
            m.reset()
            m.uc.mem_write(0x8CA18, patched[scene.layout.sbpos.va_to_off(patched, 0x8CA18):][:6])
            m.uc.ctl_remove_cache(0x8CA18, 0x8CA1E)
            if paused:
                m.pause()
            m.fc360.clear()
            panel_body.clear()
            m.put(m.SP, m.STOP)
            m.reg('ESP', m.SP)
            m.reg('EBP', m.SP - 4)
            m.uc.emu_start(0x65092, m.STOP, count=200000)
            self.assertEqual(m.reg('EIP'), m.STOP)
            self.assertEqual(panel_body, [], 'the retail play-call panel never draws')
            self.assertEqual(len(m.fc360), 1 if paused else 0, paused)
            self.assertEqual(m.get(GATE), 0)
            self.assertEqual(max(m.quad_tops()[:3]), PAUSE_TOP if paused else -6457)


if __name__ == '__main__':
    unittest.main()
