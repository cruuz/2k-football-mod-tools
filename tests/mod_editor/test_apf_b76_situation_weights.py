"""A3 format, project lifecycle, live mappings and consent transport."""
import struct
import tempfile
from pathlib import Path
import unittest

from mod_editor.core import apf2k8_situation_mask as mask
from mod_editor.core.apf2k8_situation_catalog import bucket_key, mapping_note
from mod_editor.core.apf2k8_offensive_schemes import BUCKETS
from mod_editor.core.errors import ValidationError
from mod_editor.apf_studio import situation_masks as transport
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture
from tests.mod_editor.test_apf_b71_situation_mask_install import InstallTests


def rows(key=8, values=None):
    result = {'O-ManBlock': [{} for _ in range(13)]}
    result['O-ManBlock'][key] = {'14': 4.} if values is None else values
    return result


class DataTests(unittest.TestCase):
    def test_write_sets_do_not_overlap_other_shipped_patches(self):
        from mod_editor.core import apf2k8_charge_abilities as charge
        from mod_editor.core import apf2k8_fourth_down as fourth
        from mod_editor.core import apf2k8_playcall_curves_patch as curves
        from mod_editor.core import apf2k8_playcall_patch as fetch
        for profile in mask.PROFILES:
            addresses = {a for a, _ in mask.SituationPatch(profile, mask.encode_data({}, {}, rows())).words}
            others = (charge.PatchDocument(profile), fourth.PatchDocument(profile),
                      curves.PatchDocument(profile, (1., .5, .1, .01, 0.), None),
                      fetch.PlaycallPatch(profile, fetch.assemble_cave(profile.hook), {}))
            for patch in others:
                self.assertFalse(addresses & {a for a, _ in patch.words})

    def test_v3_roundtrip_capacity_decode_and_legacy_identity(self):
        exclusions = {'O-ManBlock': [[] for _ in range(13)]}
        exclusions['O-ManBlock'][12] = [2]
        personnel = rows(12, {'6': 10})
        weights = rows()
        for profile in mask.PROFILES:
            data = mask.encode_data(exclusions, personnel, weights, version=3)
            self.assertEqual(mask.decode_data(data, include_weights=True), (exclusions, personnel, weights))
            patch = mask.SituationPatch(profile, data)
            self.assertEqual(patch.receipt['schema'], 'apf2k8_situation_mask/v3')
            self.assertEqual(mask.canonical_payload(patch.as_toml().encode()), (profile, True))
            self.assertEqual(len(mask.assemble(profile, 3)[0]), 3260)
            # Old authored TOML recognition and native code stay intact.
            self.assertEqual(len(mask.assemble(profile, 1)[0]), 2480)
            self.assertEqual(len(mask.assemble(profile, 2)[0]), 3156)
        self.assertEqual(mask.canonical_formation_weights(rows(values={'14': 1})), {})
        for value in (0, -1, 8, .1, True, '4', float('nan'), float('inf')):
            with self.assertRaises(ValidationError):
                mask.encode_data({}, {}, rows(values={'14': value}))
        for key in ('151', '014', 'x', 14):
            with self.assertRaises(ValidationError):
                mask.encode_data({}, {}, rows(values={key: 4}))
        data = mask.encode_data({}, {}, rows())
        # Header, weight count, all address fields, reserved byte, NaN, padding.
        for offset in (7, 11, 15, 16+288+4, 16+288+8, 16+288+9,
                       16+288+10, 16+288+11, 16+288+12, len(data)-1):
            changed = bytearray(data); changed[offset] = 255
            with self.assertRaises(ValidationError): mask.decode_data(bytes(changed))
        with self.assertRaisesRegex(ValidationError, 'storage is full'):
            mask.encode_data({}, {}, {f'Book{i}': [{str(f): 4 for f in range(151)} for _ in range(13)] for i in range(2)})

    def test_every_coaching_label_maps_explicitly(self):
        self.assertEqual(len(BUCKETS), 23)
        self.assertEqual(len(mask.KEY_LABELS), 13)
        expected = (2, 2, 4, 4, 5, 5, 7, 7, 8, 8, 9, 6, 2, 2, 2, 2, 0, 12, 2, 5, 2, 2, 2)
        self.assertEqual(tuple(map(bucket_key, BUCKETS)), expected)
        for bucket in BUCKETS:
            text = mapping_note(bucket)
            self.assertIn('try phase 3' if bucket.name == '2pt' else mask.KEY_LABELS[bucket_key(bucket)], text)

    def test_preview_decomposition_and_empty_draw_restore_native_weights(self):
        from tests.mod_editor.test_apf_b72_personnel_rows import ModelFixtureTests
        from mod_editor.core import apf2k8_playcall_model as model
        fixture = ModelFixtureTests(); fixture.setUp()
        s = model.Situation(3, 8, 50, 1, 900, 0, 3)
        original = model.situation_candidates(fixture.book, fixture.master, s)
        changed = model.situation_candidates(fixture.book, fixture.master, s,
                                            formation_multipliers={'0': 4.})
        for before, after in zip(original, changed):
            self.assertEqual(after['category_weight'], model.f32(before['category_weight'] * (4 if after['category'] == 6 else 1)))
        for before, after in zip(original, changed):
            factor = 4. if after['formation'] == 0 else 1.
            self.assertEqual(after['formation_multiplier'], factor)
            self.assertEqual(after['formation_retail_weight'], before['formation_weight'])
            self.assertEqual(after['formation_weight'], model.f32(before['formation_weight']*factor))
        fallback = model.situation_candidates(fixture.book, fixture.master, s,
                    exclusions=[0, 1], formation_multipliers={'0': 4.})
        self.assertEqual([c['formation_weight'] for c in original], [c['formation_weight'] for c in fallback])


class ProjectTests(FacadeFixture):
    def test_weights_try_rows_save_replay_cache_undo_and_export(self):
        engine, session = self.facade._playcalling, self.facade.session
        original = engine.state(session)
        self.assertFalse(original.situation_masks_enabled)
        weight = dict(kind='situation_weight', book='O-ManBlock', key=8, formation=62, value=4.)
        for request in (dict(kind='situation_masks_enabled', enabled=True), weight,
                        dict(kind='situation_personnel_row', book='O-ManBlock', key=12, category=6, value=10),
                        dict(kind='situation_mask', book='O-ManBlock', key=12, formation=62, exclude=True)):
            self.stage(request)
        state = engine.state(session)
        self.assertEqual(state.books, original.books)
        self.assertEqual(state.master, original.master)
        self.assertEqual(state.situation_formation_weights['O-ManBlock'][8], {'62': 4.})
        self.assertEqual(state.situation_personnel_rows['O-ManBlock'][12], {'6': 10})
        self.assertEqual(state.situation_masks['O-ManBlock'][12], [62])
        saved = session.save_project(self.root/'weights.apf2k8mod')
        self.stage({**weight, 'value': 1.})
        self.assertEqual(engine.state(session).situation_formation_weights, {})
        session.undo()
        self.assertEqual(engine.state(session).situation_formation_weights, state.situation_formation_weights)
        session.load_project(saved)
        self.assertEqual(engine.state(session).situation_formation_weights, state.situation_formation_weights)
        with tempfile.TemporaryDirectory() as directory:
            receipt = transport.export_build(directory, state)
            for patch in receipt['patches']:
                self.assertEqual(patch['formation_weights'], state.situation_formation_weights)
                self.assertEqual(patch['personnel_rows'], state.situation_personnel_rows)
                mask.canonical_payload((Path(directory)/patch['file']).read_bytes())
        self.stage(dict(kind='situation_masks_enabled', enabled=False))
        disabled = engine.state(session)
        self.assertEqual(transport.prepare(disabled, 'base')['receipt']['formation_weights'], {})
        self.assertIsNone(transport.export_build(self.root/'disabled', disabled))
        self.assertFalse(self.facade.launcher.pass_fetch_status(kind='situations')['installed'])


class WeightInstallTests(InstallTests):
    """Run the existing consent, sync, removal and failure rollback contract on v3."""
    def setUp(self):
        super().setUp()
        self.payload = mask.SituationPatch(mask.PROFILES[0], mask.encode_data({}, {}, rows())).as_toml().encode()
        self.source.write_bytes(self.payload)

    def test_v3_install_refused_but_existing_patch_can_be_replaced_or_removed(self):
        from mod_editor.apf_studio import launcher
        legacy = mask.SituationPatch(mask.PROFILES[0], mask.encode_data({}, {}, rows(), version=3)).as_toml().encode()
        self.source.write_bytes(legacy)
        with self.assertRaisesRegex(launcher.LaunchError, 'export revision 4'):
            self.launcher.install_pass_fetch_patch(self.source, kind='situations', consent=True)
        installed = self.settings.patches_folder / transport.FILENAME
        installed.parent.mkdir(parents=True, exist_ok=True)
        installed.write_bytes(legacy)
        status = self.launcher.pass_fetch_status(kind='situations')
        self.assertTrue(status['installed'])
        self.assertIn('personnel weights unchanged', status['message'])
        self.source.write_bytes(self.payload)
        result = self.launcher.install_pass_fetch_patch(self.source, kind='situations', consent=True)
        self.assertTrue(result['installed'] and result['enabled'])
        self.assertIn('revision 4', result['message'])
        installed.write_bytes(legacy)
        self.launcher.remove_pass_fetch_patch(kind='situations')
        self.assertFalse(installed.exists())


if __name__ == '__main__': unittest.main(verbosity=2)
