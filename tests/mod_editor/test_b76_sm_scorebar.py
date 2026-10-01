"""N6: measure the actual Experimental ESPN (static) bar, offline only.

Run with --report DIR to save before/after native rasters and measurements.
The requested uppercase examples and TIMEOUT are explicit glyph-fit probes;
the static formatter uses Goal/Inches and has no TIMEOUT label.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(Path(__file__).parent)]
from test_nfl2k5_scorebug_runtime import XBE, PACK, HAVE_UC
from mod_editor.core import nfl2k5_scorebug_exact as exact
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_scorebug_resources as art
import nfl2k5_scorebug_projection as projection


class Fixture:
    def __init__(self):
        self.payload = XBE.read_bytes()
        with PACK.open('rb') as stream:
            view = art.PackView.from_fd(stream.fileno(), 0, PACK.stat().st_size)
            self.spans = {n: view[v['pack_offset']:v['pack_offset'] + v['span_size']]
                          for n, v in art.RESOURCES.items()}
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACK.parents[1])
        self.fonts = projection.read_fonts(PACK)
        self.atlas = scene.apply(self.spans['score_buga'], 'score_buga')[0]
        self.after = scene.apply(self.spans['score_bug'], 'score_bug')[0]
        old_pill = (-52., exact.PILL[1], 52., exact.PILL[3])
        old_anchors = dict(exact.ANCHORS)
        for event in ('drop_ball_on', 'drop_yellow', 'drop_red', 'drop_hangtime'):
            old_anchors[event] = (0, 2.289, -8)
        with patch.multiple(exact, STATIC_PILL=old_pill, EVENT_ROW=old_pill, ANCHORS=old_anchors):
            mesh = exact.mesh(scene.pinned(self.spans['score_bug'], art.RESOURCES['score_bug']), live_timeouts=False)
            self.before = scene.layout.refit(self.spans['score_bug'], scene.serialize(mesh))[0]
        # Prove the negative control is exactly the stack-head resource.
        assert scene.digest(self.before) == '0588f2f49a0f3cf40ae179dd34d1a57b25748dbc993df34b020153fcd124d8cf'

    def measure(self, *, before=False, wide=False, text=None, phase=4, goal=False, field_goal=False,
                output=None, **state):
        import unicorn
        decoded = scene.decode(self.before if before else self.after)[1]
        capture = {}
        geometry = projection.native_geometry(self.payload, decoded, texture_span=self.atlas,
                                              fonts=self.fonts, capture=capture, widescreen=wide, **state)
        m = capture['machine']
        # native_geometry's phase/goal fixture is sprite-only. Supply the same
        # bounded state at static draw entry, after native_text_draw's setup.
        def draw_entry(*_):
            m.put(0xe602b4, phase)
            m.put(0xba2f10, int(field_goal))
            if before:
                m.uc.mem_write(0xe6c4c4, ('%d Yard Attempt\0').encode('utf-16le'))
            if goal:
                m.uc.mem_write(0xfc760, b'\xe9' + struct.pack('<i', 0xfbd50 - 0xfc765))
        hook = m.uc.hook_add(unicorn.UC_HOOK_CODE, draw_entry, begin=0xfc360, end=0xfc360)
        replacement = m.string(text) if text else None
        replaced = []
        def replace_label(*_):
            if replacement and not replaced:
                m.uc.reg_write(m.x.UC_X86_REG_EDX, replacement)
                replaced.append(True)
        probe = m.uc.hook_add(unicorn.UC_HOOK_CODE, replace_label, begin=0x47420, end=0x47420)
        try:
            geometry.update(projection.native_text_draw(capture))
            draws = [d for d in geometry['draws'] if d['vertices'] and
                     d['callback'] in ('0xfc7d0', '0xfbe90', '0xfbea0', '0xfbeb0', '0xfbe60')]
            label = draws[0] if draws else dict(text='', callback=None, font=None, align=None, vertices=[])
            points = [v['screen'] for v in label['vertices']]
            box = ([min(v[0] for v in points), min(v[1] for v in points),
                    max(v[0] for v in points), max(v[1] for v in points)] if points else None)
            row = dict(text=label['text'], callback=label['callback'], font=label['font'],
                       align=label['align'], glyph_box=box, down=geometry['down'], clock=geometry['clock'],
                       glyph_probe=text is not None, before=before, wide=wide)
            if output:
                projection.render_native(decoded, self.atlas, self.fonts, geometry, Path(output),
                                         texture_spans=capture['texture_spans'])
                row['image'] = Path(output).name
            return row
        finally:
            m.uc.hook_del(hook)
            m.uc.hook_del(probe)
            m.close()


CASES = {
    'goal': dict(down=2, goal=True),
    'inches': dict(down=4, distance_yards=.1),
    'widest-down': dict(down=2, distance_yards=.1),
    'flag': dict(visible_elements=(1, 3)),
    'fumble': dict(visible_elements=(1, 5)),
    'midfield': dict(visible_elements=(1, 4)),
    'ball-on': dict(visible_elements=(1, 4), ball_yards=49),
    'hangtime': dict(visible_elements=(1, 2)),
    'field-goal': dict(visible_elements=(1, 4), field_goal=True, ball_yards=1),
    'overtime': dict(phase=0, quarter=5),
    'wide-ball-name': dict(visible_elements=(1, 4), ball_yards=49,
                           identity=dict(home='WAS', away='WAS')),
    **{f'phase-{p}': dict(phase=p) for p in (0, 1, 2, 3, 5, 6, 7, 8, 9)},
    **{name: dict(text=text) for name, text in
       (('goal-caps', '2nd & GOAL'), ('inches-caps', '4th & INCHES'), ('timeout-probe', 'TIMEOUT'))},
}


@unittest.skipUnless(XBE.is_file() and PACK.is_file() and HAVE_UC, 'private retail input and Unicorn required')
class WidthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Fixture()

    def test_installed_width_matches_info_row_in_both_aspects_and_modes(self):
        for wide in (False, True):
            for mode in (0, 1):
                row = self.fixture.measure(wide=wide, mode=mode)
                self.assertEqual(row['down'][::2], row['clock'][::2])
                width = row['down'][2] - row['down'][0]
                self.assertAlmostEqual(width, 112 * (27 / 32 if wide else 1), delta=.01)
                old = self.fixture.measure(before=True, wide=wide, mode=mode)
                self.assertAlmostEqual(old['down'][2] - old['down'][0],
                                       104 * (27 / 32 if wide else 1), delta=.01)

    def test_all_long_states_remain_centred_and_fit_without_font_scaling(self):
        for wide in (False, True):
            for name, case in CASES.items():
                row = self.fixture.measure(wide=wide, **case)
                with self.subTest(wide=wide, name=name, text=row['text']):
                    if case.get('field_goal'):
                        self.assertEqual(row['text'], '116 yd FG')
                    if not row['text']:
                        self.assertIsNone(row['glyph_box'])
                        continue
                    self.assertEqual(row['align'], 3)
                    self.assertEqual(row['font'], 'font4')
                    a, _, c, _ = row['glyph_box']
                    lo, _, hi, _ = row['down']
                    self.assertGreaterEqual(a, lo - .02)
                    self.assertLessEqual(c, hi + .02)
                    self.assertLessEqual(abs((a+c-lo-hi)/2), 2)

    def test_static_timeout_marks_now_update_in_all_four_states(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'frame.png'
            for wide in (False, True):
                frames = []
                for count in range(4):
                    self.fixture.measure(wide=wide, timeouts=(count, 3-count), output=path)
                    frames.append(path.read_bytes())
                self.assertEqual(len(set(frames)), 4)

    def test_scene_still_fits_its_exact_retail_allocation_and_replays(self):
        f = self.fixture
        self.assertEqual(len(f.after), len(f.spans['score_bug']))
        self.assertEqual(f.after[:32], f.spans['score_bug'][:32])
        self.assertEqual(scene.apply(f.after, 'score_bug')[0], f.after)
        self.assertEqual(scene.digest(scene.decode(f.after)[1]), art.STATIC_SCENE_SHA256)


def report(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    f = Fixture()
    rows = []
    for before in (True, False):
        for wide in (False, True):
            for name, case in CASES.items():
                path = (directory / f'{"before" if before else "after"}-{"169" if wide else "43"}-{name}.png'
                        if name in ('goal', 'inches', 'midfield', 'field-goal') else None)
                rows.append(dict(case=name, **f.measure(before=before, wide=wide, output=path, **case)))
    # Both rows occupy all 64 columns; the coloured interiors occupy 62.
    atlas = exact.atlas()
    atlas.save(directory / 'static-template.png')
    cells = {}
    for name, y in (('down', 32), ('strip', 50)):
        pixels = [atlas.getpixel((x, y)) for x in range(64)]
        interior = [x for x, pixel in enumerate(pixels) if pixel != pixels[0]]
        cells[name] = dict(cell_width=64, interior=[min(interior), max(interior)+1],
                           interior_texels=len(interior))
    for row in rows:
        for role in ('down', 'clock'):
            row[role + '_interior_width'] = (row[role][2] - row[role][0]) * 62 / 64
    timeouts = []
    for count in range(4):
        path = directory / f'timeouts-{count}-{3-count}.png'
        f.measure(timeouts=(count, 3-count), output=path)
        timeouts.append(dict(home=count, away=3-count, raster_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    result = dict(evidence='PROVED OFFLINE', atlas=cells, rows=rows, timeouts=timeouts,
                  limitation='Native CPU and software raster only. glyph_probe rows inject the requested text at the native glyph boundary.')
    (directory / 'measurements.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(atlas=cells, cases=len(rows), widest=max(
        (r for r in rows if r['glyph_box']), key=lambda r:r['glyph_box'][2]-r['glyph_box'][0])['text'])))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--report':
        report(sys.argv[2])
    else:
        unittest.main()
