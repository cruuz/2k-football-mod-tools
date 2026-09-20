"""Down sprites follow the native draw decision across retained HUD updates."""
from pathlib import Path
import importlib.util
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from mod_editor.core import nfl2k5_scorebug_runtime as owner
from mod_editor.core import nfl2k5_scorebug_ingame as scene
import nfl2k5_scorebug_projection as projection

RETAIL = ROOT / 'extracted/ESPN NFL 2K5 (USA)/default.xbe'
NATIVE = RETAIL.is_file() and importlib.util.find_spec('unicorn') is not None
DT = struct.unpack('<I', struct.pack('<f', 1 / 60))[0]


class Sequence:
    """Retain one machine; only gameplay/world query boundaries are supplied.

    Never seed request/slide/material words between stages. FC330/FC340 are
    the real gameplay latch entry points. FC9C0, the entire FCE70 integrator,
    the sprite owner and FC360's element walk execute from installed bytes.
    """
    def __init__(self, preview, wide):
        self.preview, self.wide = preview, wide
        self.mode = preview.modes[wide]
        self.capture = {}
        self.geometry = projection.native_geometry(
            preview.payload, self.mode['scene'], fonts=preview.fonts,
            texture_span=self.mode['atlas'], runtime_textures=self.mode['textures'],
            capture=self.capture, widescreen=wide, identity=dict(home='KC', away='DAL'),
            possession='away', game_seconds=300, visibility_state='kickoff', visible_elements=())
        self.machine = self.capture['machine']
        # Frame assertions read native output, not full instruction histories.
        self.machine.record = False
        self.rows = [q for q in self.mode['compiled'].quads if q['name'].startswith('down:')]
        self.frame = 0

    def configure(self, state, *, down=1, latch=None):
        m = self.machine
        saved = m.get(0xba2f14)
        # The retained kick/punt world query supplies play kind 10 and phase 14.
        # Requests and slide history are still computed by FC9C0/FCE70.
        projection.configure_visibility(m, 'kickoff' if state == 'punt' else state)
        # The stock single-state fixture writes this latch. Preserve history.
        m.put(0xba2f14, saved)
        m.put(0xe602b4, 2 if state == 'kickoff' else 4)
        m.put(m.play + 4, down)
        if latch is not None:
            m.run(0xfc330 if latch else 0xfc340)

    def step(self):
        m = self.machine
        m.run(0xfce70, (DT,), limit=500000)
        self.frame += 1
        return self.read()

    def read(self):
        m = self.machine
        colors = [m.get(self.capture['body'] + scene.layout.S1 + q['vertex'] * 10) for q in self.rows]
        events = []
        for index in range(2, 6):
            record = 0xa959c8 + index * 112
            material = m.get(record + 0x44)
            events.append(dict(index=index, material=material,
                minimum=m.floats(record + 0x2c, 1)[0],
                slide=m.floats(record + 0x3c, 1)[0], binding=m.get(record + 0x58),
                visible=not bool(m.get(material + 8) & 1)))
        return dict(frame=self.frame, events=events,
                    requests=[m.get(0xa95a00 + i * 112) for i in range(6)],
                    slides=[m.floats(0xa95a04 + i * 112, 1)[0] for i in range(6)],
                    bindings=[m.get(0xa95a20 + i * 112) for i in range(6)],
                    latch=m.get(0xba2f14), colors=colors,
                    visible_glyphs=sum(bool(v) for v in colors))

    def native_draw(self):
        """Observe the real FC360 branch, independent of the owner's gate."""
        import unicorn
        m = self.machine
        entered = []
        def trace(_uc, va, _size, _data):
            if va == 0xfc416:
                entered.append((m.uc.reg_read(m.x.UC_X86_REG_ESI) - 0xa95a04) // 112)
        hook = m.uc.hook_add(unicorn.UC_HOOK_CODE, trace)
        try:
            draw = projection.native_text_draw(self.capture)
        finally:
            m.uc.hook_del(hook)
        return entered, draw

    def close(self):
        self.machine.close()


@unittest.skipUnless(NATIVE, 'Pinned USA retail XBE/pack and Unicorn required')
class DownVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preview = sprite.NativePreview()
        patched = owner.apply(cls.preview.payload)[0]
        code, data = owner.sites(patched)
        cls.data = data['va']
        cls.update = owner.code_for(code['va'], data['va'])[1]['sprite_update']

    def sequence(self, wide):
        seq = Sequence(self.preview, wide)
        self.addCleanup(seq.close)
        return seq

    def test_real_draw_gate_not_pending_requests(self):
        for wide in (False, True):
            seq = self.sequence(wide)
            seq.configure('pre_snap', latch=False)
            for _ in range(40): seq.step()
            m = seq.machine
            # The C engine is cdecl; the fixture runner expects its caller to
            # consume arguments. Execute that small caller as native code.
            call = m.alloc(32)
            m.uc.mem_write(call, b'\x68' + struct.pack('<I', self.data) + b'\xe8' +
                           struct.pack('<i', self.update - call - 10) + b'\x83\xc4\x04\xc3')
            # Isolated gate cases include a one-frame pending event, the
            # closing down slide, and an unavailable binding. These are not
            # claimed to be captured live-game memory values.
            for request, slide, binding, events, event_slide, event_binding, expected in (
                    (1, 30, 1, 0, 0, 1, True), (0, 30, 1, 0, 0, 1, True),
                    (1, 0, 1, 0, 0, 1, False), (1, 30, 0, 0, 0, 1, False),
                    (1, 30, 1, 1, 0, 1, True),  # pending, not yet drawable
                    (1, 30, 1, 0, 30, 1, False),  # request ended; event still closing
                    (1, 30, 1, 1, 30, 0, True)):  # unavailable event cannot hide the label
                m.put(0xa95a00, request); m.float(0xa95a04, slide); m.put(0xa95a20, binding)
                for va in (0xa95ae0, 0xa95b50, 0xa95bc0, 0xa95c30):
                    m.put(va, events); m.float(va + 4, event_slide); m.put(va + 0x20, event_binding)
                    # Reproduce stale flags at the owner boundary independently
                    # of the earlier retail material writer, in both directions.
                    material = m.get(va + 12)
                    m.put(material + 8, (m.get(material + 8) & ~1) | int(event_slide > 0))
                m.run(call, limit=500000)
                entered, _ = seq.native_draw()
                self.assertEqual(0 in entered and not any(i in entered for i in (2, 3, 4, 5)), expected)
                self.assertEqual(seq.read()['visible_glyphs'], 5 if expected else 0)
                for event in seq.read()['events']:
                    self.assertEqual(event['visible'], bool(event_binding and event_slide > event['minimum']))
            # An unavailable native binding may have no material pointer.
            # The owner must not write through address zero or hide the down.
            for record in range(0xa95aa8, 0xa95c68, 0x70):
                m.put(record + 0x44, 0)
                m.put(record + 0x58, 0)
            m.run(call, limit=500000)
            self.assertEqual(sum(bool(m.get(seq.capture['body'] + scene.layout.S1 + q['vertex'] * 10))
                                 for q in seq.rows), 5)

    def test_all_event_plates_follow_records_through_punt_and_next_snap(self):
        for wide in (False, True):
            seq = self.sequence(wide)
            # One retained machine per aspect. No event/slide/flag writes here.
            for state, latch, frames, active in (
                    ('pre_snap', False, 120, None), ('punt', None, 60, 2),
                    ('pre_snap', False, 120, None), ('after_play', True, 45, 4),
                    ('pre_snap', False, 80, None), ('flag', None, 45, 3),
                    ('pre_snap', False, 80, None), ('fumble', None, 45, 5),
                    ('pre_snap', False, 80, None)):
                seq.configure(state, latch=latch)
                for frame in range(frames):
                    result = seq.step()
                    for event in result['events']:
                        self.assertEqual(event['visible'], bool(event['binding'] and
                            not event['slide'] <= event['minimum']), (wide, state, result))
                    if state == 'pre_snap' and not any(e['visible'] for e in result['events']):
                        self.assertEqual(result['visible_glyphs'], 5, (wide, state, result))
                self.assertEqual([e['index'] for e in result['events'] if e['visible']],
                                 [] if active is None else [active])
                entered, _ = seq.native_draw()
                self.assertEqual([i for i in entered if i >= 2], [] if active is None else [active])
                self.assertEqual(result['visible_glyphs'], 5 if active is None else 0)

    def test_compact_material_mapping_matches_all_used_native_slots(self):
        seq = self.sequence(False)
        m = seq.machine
        mats = m.get(seq.capture['body'] + 256 + 0x20)
        self.assertEqual({e['material'] for e in seq.mode['compiled'].spec['events']}, {0, 1, 2, 10})
        self.assertEqual(m.get(0xa95aec), mats + 8 * 128)  # logical 10
        for native in (2, 4, 3, 9, 7, 10, 6):  # logical 3..9
            m.put(mats + native * 128 + 8, 0x80000001)
            m.put(mats + native * 128 + 24, 0)
        seq.configure('pre_snap', latch=False)
        seq.step()
        for native in (2, 4, 3, 9, 7, 10, 6):
            self.assertEqual(m.get(mats + native * 128 + 8), 0x80000000)
            self.assertEqual(m.get(mats + native * 128 + 24), 0xffffffff)
        for index, native in ((2, 8), (3, 1), (4, 0), (5, 5)):
            self.assertEqual(m.get(0xa959c8 + index * 112 + 0x44), mats + native * 128)

    def test_kickoff_ball_on_flag_and_every_down_keep_native_history(self):
        for wide in (False, True):
            seq = self.sequence(wide)
            for state, latch in (('kickoff', None), ('after_play', True), ('pre_snap', False),
                                 ('flag', None), ('pre_snap', None)):
                seq.configure(state, latch=latch)
                for _ in range(45): result = seq.step()
                entered, _ = seq.native_draw()
                if state == 'kickoff':
                    self.assertEqual(result['visible_glyphs'], 0)  # native Kickoff literal has no down tokens
                else:
                    self.assertEqual(result['visible_glyphs'] > 0, 0 in entered and not any(i in entered for i in (2, 3, 4, 5)))
                if state == 'after_play':
                    # Retail requests/draws both elements. The event plate is
                    # ordered over down; its computed visibility occupies that slot.
                    self.assertEqual(result['requests'], [1, 1, 0, 0, 1, 0])
                    self.assertIn(0, entered); self.assertIn(4, entered)
                if state == 'pre_snap':
                    self.assertEqual(result['requests'], [1, 1, 0, 0, 0, 0])
                    for down in range(1, 5):
                        seq.configure('pre_snap', down=down)
                        result = seq.step()
                        self.assertEqual(result['visible_glyphs'], 5)
                        self.assertTrue(all(v in (0, 0xffffffff) for v in result['colors']))


if __name__ == '__main__':
    unittest.main()
