"""Private FONT provenance, native relocation and scoped descriptor binding."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from mod_editor.core import nfl2k5_scorebug_fonts as fonts
from mod_editor.core import nfl2k5_scorebug_runtime as runtime
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from test_nfl2k5_scorebug_runtime import XBE, PACK, HAVE_UC
import nfl2k5_scorebug_projection as projection

HAVE_IMAGES = all(importlib.util.find_spec(name) for name in ('PIL', 'numpy'))


class PublicTests(unittest.TestCase):
    def test_foreign_donors_settings_and_owner_budget_refuse(self):
        with self.assertRaises(ValueError): fonts.source_spans(bytes(1024))
        for name, slot, x, y, weight in ((fonts.NAMES[0], 3, float('nan'), 1, 0),
                                      ('font4', 3, 1, 1, 0),
                                      (fonts.NAMES[0], 0, 1, 1, 0),
                                      (fonts.NAMES[0], 3, 1, 1, True)):
            with self.assertRaises(ValueError): fonts.compile_font(b'', name, slot, x, y, weight)
        code, labels = runtime.code_for(0x14da000, 0x14f2000)
        self.assertEqual(len(code), 1408)
        self.assertEqual(runtime.DATA_SIZE, 128)
        self.assertLess(runtime.FONT_COMPACT + 4, runtime.DATA_SIZE)
        self.assertLess(labels['setup'], labels['update'])


@unittest.skipUnless(XBE.is_file() and PACK.is_file() and HAVE_UC and HAVE_IMAGES,
                     'pinned USA XBE/pack, Unicorn, Pillow and numpy required')
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_scorebug_exact import Build, reference, reference_text_boxes
        cls.build = Build(PACK, XBE)
        cls.addClassCleanup(cls.build.close)
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.out = Path(cls.temp.name).resolve()
        source, cls.reference = reference()
        cls.text_boxes = reference_text_boxes(source)

    def test_native_registry_field_relative_relocation_and_global_fonts_unchanged(self):
        m = projection.StaticMachine(self.build.payload)
        self.addCleanup(m.close)
        m.load_fonts(self.build.fonts)
        global_slots = bytes(m.uc.mem_read(0xa90ecc, 9*4))
        originals = {obj: bytes(m.uc.mem_read(obj, len(font.decoded) - font.object_offset))
                     for obj, font in m.fonts.items()}
        self.assertEqual(tuple(map(len, self.build.font_spans)), fonts.SPAN_SIZES)
        for span, parsed in zip(self.build.font_spans, self.build.private_fonts):
            receipt = m.load_private_font(span, parsed)
            self.assertFalse(receipt['global_slot_changed'])
            obj = int(receipt['object'], 16)
            self.assertEqual(m.get(obj+4), len(parsed.ranges))
            for index, row in enumerate(parsed.ranges):
                native = m.get(obj+8) + 8*index
                self.assertEqual(bytes(m.uc.mem_read(native, 4)), struct.pack('<HH', row['first_codepoint'], row['last_codepoint']))
                glyph = m.get(native+4)
                self.assertEqual(bytes(m.uc.mem_read(glyph, 96)),
                                 parsed.decoded[row['glyph_records_offset']:row['glyph_records_offset']+96])
            # TXTR and FONT names can coincide; FOURCC lookup picks FONT.
            m.run(0x449e0, (m.string(parsed.name),), ecx=0, edx=int.from_bytes(b'FONT', 'little'))
            self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_EAX), obj)
        self.assertEqual(bytes(m.uc.mem_read(0xa90ecc, 9*4)), global_slots)
        for obj, before in originals.items():
            self.assertEqual(bytes(m.uc.mem_read(obj, len(before))), before)
        for source in fonts.source_spans(self.build.view).values():
            corrupted = bytearray(source); corrupted[32] ^= 1
            with self.assertRaises((ValueError, RuntimeError)):
                fonts.compile_font(bytes(corrupted), fonts.NAMES[0], 3, 1, 1)

    def test_foreign_native_font_loader_or_name_refuses_before_installation(self):
        for va in [row[0] for row in fonts.CODE_GUARDS] + list(fonts.NAME_VAS) + [0xa95884, 0xa958ac]:
            damaged = bytearray(self.build.payload)
            offset = scene.layout.sbpos.va_to_off(damaged, va)
            damaged[offset] ^= 1
            self.assertEqual(runtime.status(bytes(damaged)), 'foreign', hex(va))
            with self.assertRaises(ValueError): runtime.apply(bytes(damaged))

    def test_weight_variants_keep_all_numerals_and_clock_punctuation_visible(self):
        from PIL import Image
        from nfl_main_menu_font import rgba_from_font
        for weight in (-1,1):
            spans = fonts.compile_collection(self.build.view, weight=weight)
            for index in (0,1,2,3,5,6):
                parsed = projection.private_font(spans[index], self.build.fonts[fonts.SCALES[index][0]])
                alpha = Image.frombytes('RGBA',(parsed.width,parsed.height),rgba_from_font(parsed)).getchannel('A')
                glyphs = {chr(g.codepoint):g for g in parsed.glyphs}
                for character in '0123456789:&st':
                    u,v,a,b = glyphs[character].uv
                    tile = alpha.crop(tuple(round(k) for k in (u*parsed.width,v*parsed.height,a*parsed.width,b*parsed.height)))
                    self.assertIsNotNone(tile.getbbox(), (weight,index,character))

    def capture(self, private=True, cleanup=True, **kwargs):
        span = scene.stage_binding_scene(self.build.spans['score_bug'], runtime=True)[0]
        atlas = scene.encode_atlas(self.build.spans['score_buga'], scene.atlas())[0]
        capture = {}
        geometry = projection.native_geometry(self.build.payload, scene.decode(span)[1],
            fonts=self.build.fonts, texture_span=atlas, runtime_textures=self.build.panels,
            runtime_fonts=self.build.font_spans if private else (), capture=capture, **kwargs)
        if cleanup:
            self.addCleanup(capture['machine'].close)
        return geometry, capture

    def test_native_setup_binds_only_scoped_roles_and_null_lookup_retains_fallback(self):
        expected = {0xa95a10: 0, 0xa95918: 1, 0xa95940: 1, 0xa95968: 2,
                    0xa959a0: 2, 0xa958f0: 5, 0xa95a80: 6}
        geometry, capture = self.capture()
        m = capture['machine']
        for pointer, index in expected.items():
            self.assertEqual(m.fonts[m.get(pointer)].name, fonts.NAMES[index], hex(pointer))
        self.assertTrue(all(not row['global_slot_changed'] for row in geometry['private_fonts']))
        _geometry, fallback = self.capture(private=False)
        m = fallback['machine']
        for pointer in expected:
            self.assertIn(m.fonts[m.get(pointer)].name, ('font4', 'font8'))

    def test_possession_is_one_scoped_glyph_on_the_correct_side_and_reload_hides_missing_font(self):
        if not fonts.CHEVRON:
            self.skipTest('possession compiler stage has not been enabled')
        geometry, capture = self.capture()
        m = capture['machine']
        callback = m.get(0xa95884)
        self.assertEqual(callback, m.get(0xa958ac))
        patched = projection._runtime_payload(scene.apply_xbe(self.build.payload)[0], runtime.code_for(0,0)[0])
        code, _data = runtime.sites(patched)
        self.assertTrue(code['va'] <= callback < code['va'] + code['size'])
        self.assertEqual(bytes(m.uc.mem_read(callback, 7)), bytes.fromhex('c70176000000c3'))
        # City-name length must have no effect on glyph count or marker opacity.
        for home, away in (('HOU','LV'), ('San Francisco','Tampa Bay')):
            m.identity(home=home,away=away)
            for side, pointer in (('home',0xe5fc20), ('away',0xe5fc60)):
                m.put(0xe60280,pointer)
                drawn = projection.native_text_draw(capture)
                cues = [d for d in drawn['draws'] if d['font'] == fonts.NAMES[4]]
                visible = [d for d in cues if any(int(v['color'],16) >> 24 for v in d['vertices'])]
                self.assertEqual(len(visible),1,(home,away,side))
                self.assertTrue(all(d['text'] == 'v' and len(d['vertices']) == 4 for d in cues))
                xs = [v['screen'][0] for v in visible[0]['vertices']]
                self.assertTrue(min(xs) > 320 if side == 'home' else max(xs) < 320)
                self.assertEqual(visible[0]['color'],'0xffffffff')
                self.assertEqual(projection.containment_failures({**geometry,**drawn},geometry['frame'],.02),{})
        # Renaming the registered private resource makes the real lookup fail.
        # Setup must clear its previous white alternate colour before lookup.
        obj = next(obj for obj,font in m.fonts.items() if font.name == fonts.NAMES[4])
        name = obj - self.build.private_fonts[4].object_offset + 32
        m.uc.mem_write(name,b'X\0')
        m.run(0x449e0,(m.string(fonts.NAMES[4]),),ecx=0,edx=int.from_bytes(b'FONT','little'))
        self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_EAX),0)
        m.run(0xfccd0,limit=500000)
        self.assertEqual((m.get(0xa95898),m.get(0xa958c0)),(0,0))
        native_slots = set(struct.unpack('<9I',m.uc.mem_read(0xa90ecc,9*4)))
        # Suppressed city labels retain their own retail selector, which need
        # not be the FONT4/FONT8 selectors used by the visible clock and scores.
        self.assertTrue(all(m.get(va) in native_slots for va in (0xa958a0,0xa958c8)))

    def test_native_glyph_caps_positions_and_uvs_match_measured_sizes(self):
        from PIL import Image
        from nfl2k5_scorebug_exact import compare
        path = self.out / 'private.png'
        geometry = self.build.render(path, runtime=True)
        with Image.open(path) as image:
            measured = compare(self.reference, image, geometry, self.text_boxes, runtime=True)
        for callback, row in measured['text'].items():
            self.assertLessEqual(row['max_error_px'], 1.0, callback)
        self.assertFalse(measured['exact_match'])  # Residual pixels remain visible.
        self.assertEqual(measured['containment'], {})
        for row in geometry['draws']:
            if row['callback'] in self.text_boxes:
                self.assertIn(row['font'], fonts.NAMES)
                for vertex in row['vertices']:
                    self.assertTrue(all(0 <= v <= 1 for v in vertex['uv']))

    def test_compact_fonts_follow_each_current_and_cached_score_and_restore_with_null_fallback(self):
        if not fonts.COMPACT_SCORES:
            self.skipTest('compact score compiler stage has not been enabled')
        _geometry, capture = self.capture()
        m = capture['machine']
        patched = projection._runtime_payload(scene.apply_xbe(self.build.payload)[0],runtime.code_for(0,0)[0])
        code, data = runtime.sites(patched)
        update = runtime.code_for(code['va'],data['va'])[1]['update']
        normal, compact = (m.get(data['va'] + off) for off in (runtime.FONT_SCORE,runtime.FONT_COMPACT))
        self.assertNotEqual(normal,compact)
        # Native string writes terminate but need not clear trailing cache bytes.
        cases = (((100,99),(99,99)), ((999,100),(100,99)), ((99,999),(333,100)),
                 ((9,99),(9,99)), ((99,9),(99,9)))
        for values, previous in cases:
            for index, pointer in enumerate((m.home,m.away)):
                m.put(pointer,values[index])
                m.uc.mem_write(runtime.SCORE_FONTS[index]+4,(str(previous[index])+'\0').encode('utf-16le'))
            m.run(update,(0,))
            for index, pointer in enumerate(runtime.SCORE_FONTS):
                self.assertEqual(m.get(pointer),compact if max(values[index],previous[index]) >= 100 else normal,
                                 (values,previous,index))
        m.put(data['va']+runtime.FONT_COMPACT,0)
        m.put(m.home,999);m.run(update,(0,))
        self.assertEqual(m.get(runtime.SCORE_FONTS[0]),normal)
        m.put(data['va']+runtime.FONT_SCORE,0)
        retail = m.get(0xa90ecc+7*4)
        m.put(runtime.SCORE_FONTS[0],retail);m.run(update,(0,))
        self.assertEqual(m.get(runtime.SCORE_FONTS[0]),retail)

    def test_widest_three_digit_scores_clear_the_pill_through_native_flip_phases(self):
        if not fonts.COMPACT_SCORES:
            self.skipTest('compact score compiler stage has not been enabled')
        from nfl2k5_scorebug_exact import box_of
        glyphs = {chr(g.codepoint):g for g in self.build.private_fonts[3].glyphs}
        widths = {}
        for value in range(100,1000):
            cursor, lefts, rights = 0, [], []
            for character in str(value):
                glyph = glyphs[character]
                lefts.append(cursor+glyph.left);rights.append(cursor+glyph.right)
                cursor += glyph.advance
            widths[value] = max(rights)-min(lefts)
        self.assertEqual(widths[333],max(widths.values()))
        for wide in (False,True):
            for mode in (0,1):
                for phase in (0,.001,.25,.5,.75,.999):
                    values,previous = ((99,333),(333,99)) if phase else ((333,333),(99,99))
                    geometry, capture = self.capture(cleanup=False,widescreen=wide,mode=mode,score_phase=phase,
                        score_values=values,previous_scores=previous)
                    try:
                        drawn = projection.native_text_draw(capture)
                        self.assertEqual(projection.containment_failures({**geometry,**drawn},geometry['frame'],.02),{})
                        left,_,right,_ = geometry['down']
                        for row in drawn['draws']:
                            if row['callback'] not in ('0xfc050','0xfc070') or not row['vertices']:
                                continue
                            self.assertEqual(row['font'],fonts.NAMES[3])
                            a,_,b,_ = box_of([v['screen'] for v in row['vertices']])
                            gap = a-right if row['callback'] == '0xfc050' else left-b
                            self.assertGreaterEqual(gap,3*(27/32 if wide else 1)-.02,(wide,mode,phase,row['text']))
                    finally:
                        capture['machine'].close()


if __name__ == '__main__':
    unittest.main()
