"""Colour controls: calibrated prediction, parameters, fixed spans and custom receipts."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_color as mc
from mod_editor.core import mod_build, nfl2k5_build_settings as saved

RETAIL = Path(os.environ.get('NFL2K5_RETAIL_INDEX', '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'))
GAME = mc._game_folder(RETAIL)
XBE = GAME / 'default.xbe'


class SettingsModelTests(unittest.TestCase):
    def test_calibration_reproduces_captured_night_and_v21_prediction(self):
        beta70 = dict(ambient=(.94, .96, 1), ambient_intensity=.42,
                      lights=(((1, 1, 1), .72),) * 3)
        self.assertEqual(mc.predicted_on_screen((109, 130, 75), table=beta70), (51, 61, 32))
        self.assertEqual(mc.predicted_on_screen((181, 216, 102)), (102, 122, 52))
        self.assertEqual(mc.predicted_on_screen((181, 216, 102), 'day'), (89, 105, 61))
        doc = mc.default_settings()
        estimate = mc.preview(doc)
        doc['values']['rig_night_indoor.gain'] = .5
        self.assertTrue(all(a < b for a, b in zip(mc.preview(doc)['predicted'], estimate['predicted'])))
        doc['preview_class'] = 'material'
        self.assertFalse(mc.preview(doc)['map'])
        doc['preview_class'] = 'dome'
        self.assertEqual(mc.preview(doc)['target'], (102, 125, 78))
        self.assertIn('extrapolated', mc.preview(doc)['scope'])

    def test_day_afternoon_defaults_and_shadow_reset_keep_night_pinned(self):
        import colorsys
        doc = mc.default_settings()
        pins = {r['name']: r for r in mc._pins()['light_tables']}
        self.assertEqual(pins['night_indoor']['applied_sha256'],
                         '18c6d914b12edc22d092cea97b7839d4f4611e23b5a898cbceeb4d74222b9fb9')
        self.assertEqual(len(mc._pins()['bundles']), 477)
        for name, expected, strengths, shadow, target in (
                ('day', (89, 105, 61), (.44, 1.60, .99), .32, (88, 105, 61)),
                ('afternoon', (87, 103, 61), (.60, 1.20, 1.04), .22, (98, 119, 72))):
            with self.subTest(name=name):
                doc['preview_rig'] = name
                self.assertEqual(mc.preview(doc)['predicted'], expected)
                self.assertEqual(mc.preview(doc)['target'], target)
                _, saturation, value = colorsys.rgb_to_hsv(*(c/255 for c in expected))
                self.assertLess(saturation, .43)
                self.assertTrue(.40 <= value <= .42)
                for lever, strength in zip(('ambient', 'key', 'fill'), strengths):
                    self.assertEqual(doc['values'][f'rig_{name}.{lever}'], strength)
                retail = mc._retail_table(name)
                self.assertAlmostEqual(mc.read_rig(mc.modern_table(retail))['shadow'], shadow)
                doc['disabled'] = [f'rig_{name}.balance']
                self.assertEqual(mc.modern_table(retail, doc)[0x100:0x104], retail[0x100:0x104])
                doc['disabled'] = []
                doc['values'][f'rig_{name}.balance'] = .5
                mixed = mc.read_rig(mc.modern_table(retail, doc))['shadow']
                self.assertAlmostEqual(mixed, (mc.read_rig(retail)['shadow'] + shadow)/2)
                doc = mc.default_settings()

    def test_outside_calibration_link_custom_and_every_condition(self):
        import colorsys
        self.assertEqual(mc.predicted_on_screen(mc.OUTSIDE_REFERENCE_MAP, 'day', surface='outside'), (101, 151, 76))
        for stadium in mc.PREVIEW_CLASSES:
            for rig in mc.MODERN_RIGS:
                doc = mc.default_settings()
                doc.update(preview_class=stadium, preview_rig=rig)
                field, outside = mc.preview(doc), mc.preview(doc, surface='outside')
                f, o = field['predicted'], outside['predicted']
                self.assertEqual(outside['target'], f)
                self.assertTrue(.92 <= max(o)/max(f) <= 1, (stadium, rig, f, o))
                self.assertLessEqual(colorsys.rgb_to_hsv(*o)[1], colorsys.rgb_to_hsv(*f)[1], (stadium, rig, f, o))
        doc = mc.default_settings()
        teal = bytes((59, 72, 40, 255)) * 256  # s48 outside hue exceeds the old 150-degree mask
        self.assertNotEqual(mc.regrade_palette(teal, surface='outside'), teal)
        self.assertEqual(mc.regrade_palette(teal), teal, 'FIELD hue mask stays unchanged')
        self.assertEqual(mc._palette_mean(teal, [1]*256, hue_max=180), (40,72,59))
        matched = mc.match_outside_palette(teal, (181, 216, 102), [1]*256)
        self.assertNotEqual(matched, teal)
        self.assertEqual(mc.match_outside_palette(bytes((255,255,255,255))*256, (181,216,102), [1]*256), bytes((255,255,255,255))*256)
        for tint in ((204, 216, 216, 255), (255, 238, 205, 255), (178, 178, 178, 128)):
            corrected = mc.linked_outside_tint(tint, doc)
            self.assertEqual(len(set(corrected[:3])), 1)
            self.assertGreaterEqual(min(corrected[:3]), 246)
            self.assertEqual(corrected[3], tint[3])
            self.assertEqual(mc.linked_outside_tint(tint, mc.default_settings(retail=True)), tint)
        doc['linked']['outside'] = False
        baseline = mc.preview(doc, surface='outside')['predicted']
        doc['values']['outside.saturation'] = .5
        custom = mc.preview(doc, surface='outside')['predicted']
        self.assertNotEqual(custom, baseline)
        doc['values']['turf.value_lift'] = 1.5
        self.assertEqual(mc.preview(doc, surface='outside')['predicted'], custom)
        doc['linked']['outside'] = True
        self.assertNotEqual(mc.preview(doc, surface='outside')['predicted'], custom)
        doc['linked']['outside'] = False
        self.assertEqual(mc.preview(doc, surface='outside')['predicted'], custom)


    def test_all_controls_validate_and_roundtrip_without_changing_presets(self):
        doc = mc.default_settings()
        self.assertEqual(len(mc.control_specs()), 55)
        self.assertFalse(mc.is_custom(doc))
        legacy = {k: v for k, v in mc.normalize_settings().items() if not k.startswith('preview_')}
        old_id = mc.sha(json.dumps(legacy, sort_keys=True, separators=(',', ':')).encode())
        self.assertNotEqual(mc.settings_id(), old_id, 'C4 receipts/caches must not bypass the C5 transform')
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'old-disc.iso'
            mc._save_image_receipt(target, dict(schema=mc.RECEIPT_SCHEMA, settings=mc.normalize_settings(), settings_sha256=old_id))
            with self.assertRaisesRegex(ValueError, 'original retail source'):
                mc.read_image_receipt(target)
        displayed = deepcopy(doc)
        displayed['values'] = {k: round(v, 3) for k, v in doc['values'].items()}
        self.assertFalse(mc.is_custom(displayed), 'returning sliders to their displayed defaults restores Broadcast')
        for key, spec in mc.control_specs().items():
            for value in (spec['minimum'], spec['maximum']):
                changed = deepcopy(doc)
                changed['values'][key] = value
                self.assertEqual(mc.normalize_settings(changed)['values'][key], value)
            for invalid in (True, float('nan'), float('inf'), spec['minimum']-1, spec['maximum']+1):
                changed = deepcopy(doc)
                changed['values'][key] = invalid
                with self.assertRaises(ValueError, msg=key):
                    mc.normalize_settings(changed)
        doc['values']['turf.value_lift'] = 3.14
        plan = mod_build.BuildPlan('source', 'target', modern_color_settings=doc)
        self.assertEqual(saved.to_plan(saved.from_plan(plan), 'a', 'b').modern_color_settings, doc)
        for preset in mod_build.PRESETS:
            result = mod_build.apply_preset(plan, preset)
            self.assertFalse(result.modern_color)
            self.assertEqual(result.modern_color_settings, doc)
        self.assertEqual(mc.settings_id(doc), mc.settings_id(json.loads(json.dumps(doc))))
        doc['preview_class'] = 'dome'
        self.assertEqual(mc.settings_id(doc), mc.settings_id(plan.modern_color_settings))
        doc['disabled'] = ['missing']
        with self.assertRaises(ValueError):
            saved.build_settings({'modern_color_settings': doc})

    def test_palette_controls_linking_switches_and_paint_preservation(self):
        palette = bytes((66, 125, 100, 255),) * 128 + bytes((0, 0, 220, 255),) * 128
        retail = mc.default_settings(retail=True)
        self.assertEqual(mc.regrade_palette(palette, settings=retail), palette)
        baseline = mc.regrade_palette(palette)
        doc = mc.default_settings()
        for key, value in (('hue_target', 95), ('hue_pull', 0), ('saturation', .5), ('value_lift', 1)):
            changed = deepcopy(doc)
            changed['values']['turf.'+key] = value
            out = mc.regrade_palette(palette, settings=changed)
            self.assertNotEqual(out[:4], baseline[:4], key)
            self.assertEqual(out[512:], palette[512:])
            for group in ('endzones', 'outside'):
                self.assertEqual(out, mc.regrade_palette(palette, settings=changed, surface=group))
                changed['linked'][group] = False
                self.assertEqual(mc.regrade_palette(palette, settings=changed, surface=group), baseline)
        doc['enabled']['endzones'] = False
        self.assertEqual(mc.regrade_palette(palette, settings=doc, surface='endzones'), palette)
        doc = mc.default_settings()
        doc['disabled'] = ['turf.saturation']
        self.assertEqual(mc.control_value(doc, 'turf.saturation'), 1)
        self.assertEqual(doc['values']['turf.saturation'], 1.12)
        # A synthetic map with two green bands: contrast zero removes value differences.
        palette = bytes((30, 60, 48, 255)) * 128 + bytes((60, 120, 96, 255)) * 128
        doc['values']['turf.map_contrast'] = 0
        out = mc.regrade_palette(palette, settings=doc, mean_value=90/255)
        self.assertEqual(out[:4], out[512:516])

    def test_bump_tints_and_retail_reset_are_exact(self):
        palette = bytes((245, 145, 160, 200)) * 256
        retail = mc.default_settings(retail=True)
        self.assertEqual(mc.flatten_normal_palette(palette, retail), palette)
        doc = mc.default_settings()
        doc['values']['normal.flatten'] = 1
        self.assertEqual(mc.flatten_normal_palette(palette, doc)[:4], bytes((255, 128, 128, 200)))
        for word in mc.TINTS:
            self.assertEqual(mc.corrected_tint_word(word), mc.TINTS[word])
            self.assertEqual(mc.corrected_tint_word(word, retail), word)
        self.assertEqual(mc.corrected_tint((255, 255, 229, 255)), (255, 255, 240, 255))
        for name, _, _ in mc.LIGHT_TABLES:
            self.assertEqual(mc.modern_table(mc._retail_table(name), retail), mc._retail_table(name))


class RigParameterTests(unittest.TestCase):
    def test_every_rig_lever_writes_only_owned_floats_and_default_pins_hold(self):
        pins = {r['name']: r for r in mc._pins()['light_tables']}
        for name, _, _ in mc.LIGHT_TABLES:
            retail = mc._retail_table(name)
            baseline = mc.modern_table(retail)
            self.assertEqual(mc.sha(baseline), pins[name]['applied_sha256'])
            count = struct.unpack_from('<I', retail, 20)[0]
            allowed = set(range(0, 12)) | set(range(16, 20))
            if name in ("day", "afternoon"):
                allowed.update(range(0x100, 0x104))
            for i in range(count):
                base = 32 + 64*i
                allowed.update(range(base, base+12))
                allowed.update(range(base+32, base+36))
            for key, value in (('gain', .7), ('balance', .25), ('ambient', .9), ('key', .8), ('fill', .15)):
                doc = mc.default_settings()
                doc['values'][f'rig_{name}.{key}'] = value
                after = mc.modern_table(retail, doc)
                self.assertNotEqual(after, baseline, (name, key))
                self.assertTrue({i for i,(a,b) in enumerate(zip(retail,after)) if a!=b} <= allowed)
                self.assertEqual(mc.read_rig(after)['lights'].__len__(), count)

    @unittest.skipUnless(XBE.is_file(), 'retail executable not available')
    def test_custom_xbe_receipt_replay_restore_and_tamper(self):
        data = XBE.read_bytes()
        doc = mc.default_settings()
        doc['values']['rig_day.fill'] = .7
        after, receipt = mc.apply(data, settings=doc)
        self.assertEqual(receipt['state'], 'applied (custom)')
        self.assertEqual(mc.xbe_status(after), 'foreign')
        self.assertEqual(mc.xbe_status(after, doc), 'applied (custom)')
        self.assertEqual(mc.apply(after, settings=doc)[0], after)
        self.assertEqual(mc.apply(after, enabled=False, previous_settings=doc)[0], data)
        bad = deepcopy(doc); bad['values']['rig_day.fill'] = .6
        with self.assertRaises(ValueError):
            mc.verify(after, settings=bad)
        self.assertEqual(receipt['settings_sha256'], mc.settings_id(doc))
        image = mc.XbeImage(data)
        self.assertEqual(image.read(image.section(0x641c0).start, 32), mc.XbeImage(after).read(image.section(0x641c0).start, 32))


@unittest.skipUnless(RETAIL.is_file(), 'retail archive extraction not available')
class BundleParameterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pin = next(r for r in mc._pins()['bundles'] if r['name'] == 's13nd.iff')
        with mc._outer_image()(GAME / 'vc_53450030') as archive:
            entry = archive.entries[cls.pin['outer']]
            cls.data = archive.read(entry.virtual_offset, entry.size)

    def test_custom_refit_wrappers_mips_cache_and_retail_identity(self):
        custom = mc.default_settings()
        custom['values'].update({'turf.value_lift': 2.2, 'turf.map_contrast': .6,
                                'outside.match': .5, 'outside.falloff': .7,
                                'divots.contrast': .5, 'normal.flatten': .8, 'tints.night': .5})
        custom['linked']['endzones'] = False
        custom['values']['endzones.saturation'] = .8
        cache = {}
        after, edits = mc.modern_bundle(self.data, outer_index=self.pin['outer'], settings=custom, field_cache=cache)
        self.assertNotEqual(mc.sha(after), self.pin['applied_sha256'])
        self.assertEqual(len(after), len(self.data))
        tx, inv, R, H = mc._tools()
        for edit in edits:
            at, size = edit['offset'], edit['size']
            self.assertEqual(mc.sha(after[at:at+size]), edit['after_sha256'])
            if edit['kind'] == 'tint':
                continue
            before_span, after_span = self.data[at:at+size], after[at:at+size]
            self.assertEqual(before_span[:32], after_span[:32])
            before_chunk = tx.parse_chunks(before_span, allow_trailing=True)[0]
            after_chunk = tx.parse_chunks(after_span, allow_trailing=True)[0]
            before_raw, _ = tx.decode_chunk(before_span, before_chunk)
            after_raw, _ = tx.decode_chunk(after_span, after_chunk)
            self.assertEqual(len(before_raw), len(after_raw))
            if edit['kind'] == 'normal':
                info = tx.parse_texture(before_raw, before_chunk)
                palette_at = before_chunk.system_bytes + info.palette_offset
                self.assertEqual(before_raw[:palette_at], after_raw[:palette_at], 'all mip bytes remain retail')
                self.assertEqual(before_raw[palette_at+1024:], after_raw[palette_at+1024:])
        original, default_edits = mc.modern_bundle(self.data, outer_index=self.pin['outer'], field_cache=cache)
        self.assertEqual(mc.sha(original), self.pin['applied_sha256'], 'custom cache cannot pollute Broadcast')
        restored, retail_edits = mc.modern_bundle(self.data, settings=mc.default_settings(retail=True))
        self.assertEqual(restored, self.data)
        self.assertEqual(retail_edits[0]['vertex_tints'], 0)


    def test_unlinked_outside_palette_retains_own_custom_colour(self):
        def outside(doc):
            after, edits = mc.modern_bundle(self.data, settings=doc)
            tx, inv, R, H = mc._tools()
            rec, raw, _ = mc._scene(after, mc._chunks(after)[0])
            t = next(t for t in rec['embedded_textures'] if mc.OUTSIDE_MATERIAL in t['mapped_material_names'])
            at = rec['system_bytes'] + t['palette_offset']
            self.assertFalse(edits[0].get('unfit'))
            return raw[at:at+1024]
        doc = mc.default_settings()
        doc['linked']['outside'] = False
        doc['values']['outside.saturation'] = .6
        custom = outside(doc)
        doc['values']['turf.value_lift'] = 1.5
        self.assertEqual(outside(doc), custom, 'unlinked outside ignores field changes')
        doc['linked']['outside'] = True
        self.assertNotEqual(outside(doc), custom, 'link uses the changed field target')
        doc['linked']['outside'] = False
        self.assertEqual(outside(doc), custom, 'relinking retains the saved independent colour')


    def test_image_writer_receipt_replay_tamper_scope_and_regrade_refusal(self):
        pin = self.pin
        class Entry:
            name_id, size, virtual_offset = pin['name_id'], pin['size'], 0
        class Archive:
            entries = {pin['outer']: Entry()}
            blob = bytearray(self.data)
            writes = 0
            def __init__(self, *a, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self, at, size): return bytes(self.blob[at:at+size])
            def write(self, at, payload):
                self.blob[at:at+len(payload)] = payload
                type(self).writes += 1
                return len(payload)
        custom = mc.default_settings()
        custom['values']['divots.contrast'] = .5
        pins = dict(mc._pins(), bundles=[pin])
        with tempfile.TemporaryDirectory() as tmp, patch.object(mc, '_pins', return_value=pins), patch.object(mc, '_outer_image', return_value=Archive):
            target = Path(tmp) / 'memory.iso'
            receipt = mc.apply_to_image(target, settings=custom, workers=1)
            self.assertEqual(receipt['state'], 'applied (custom)')
            self.assertEqual(mc.read_image_receipt(target), receipt)
            self.assertEqual(mc.image_status(target), 'applied (custom)')
            self.assertEqual(mc.image_status(target, receipt=None), 'foreign')
            writes = Archive.writes
            again = mc.apply_to_image(target, settings=custom, workers=1)
            self.assertEqual(again['rewritten'], 0)
            self.assertEqual(mc.read_image_receipt(target), again)
            self.assertEqual(Archive.writes, writes)
            with self.assertRaisesRegex(ValueError, 'original retail'):
                mc.apply_to_image(target, settings=mc.default_settings(), workers=1)
            self.assertEqual(Archive.writes, writes)
            bad = deepcopy(receipt)
            bad['bundle_pins'][pin['name']]['sites'][0]['offset'] += 1
            with self.assertRaisesRegex(ValueError, 'pinned span'):
                mc.image_status(target, receipt=bad)
            # A foreign edit outside the owner sites also invalidates a custom receipt.
            Archive.blob[-1] ^= 1
            self.assertEqual(mc.image_status(target), 'foreign')
            with self.assertRaises(ValueError):
                mc.apply_to_image(target, settings=custom)
            self.assertEqual(Archive.writes, writes)


if __name__ == '__main__':
    unittest.main(verbosity=2)
