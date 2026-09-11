"""Budget review, worker boundary, saved policy and coupled cache, using synthetic art."""
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(Path(__file__).parent)]
from PIL import Image
from mod_editor.apf_studio import ps3_texture_bundle as bundle_api
from mod_editor.apf_studio.helmet_crest_design import RETAIL_CREST_PROFILE, metadata, validate_metadata, HelmetCrestDesignError
from mod_editor.apf_studio.build import ApfBuildService
from mod_editor.apf_studio.project import save_project, load_project
from mod_editor.apf_studio.session import ApfSession
from test_apf_helmet_crest_design_product import _source, _mask
import apf_logo_patch as writer


def inputs():
    layers = tuple(bundle_api.TextureLayer(f'logo_l{i}', Image.new('RGBA', (512, 512), color), f'l{i}.dds', {})
                   for i, color in enumerate(((119, 34, 187, 255), (51, 153, 238, 136))))
    pair = bundle_api.TexturePair('synthetic/logo', 'Chicago Bears', 'synthetic', 'logo', 'default', 42, layers)
    slots = tuple(bundle_api.DestinationSlot(f'logo:{outer}', f'Logo slot {number}', 'logo', outer, entry_hash,
                   (f'asset:{number}:0', f'asset:{number}:1'), (0, 1), number, True, budget)
                  for number, outer, budget, entry_hash in ((92, 621, 48609, 42), (23, 301, 165345, 43), (85, 192, 142817, 44)))
    sizes = ((16, 75249), (16, 72631), (8, 61000), (8, 60000), (4, 47912), (4, 47000), (2, 35000), (2, 34000))
    attempts = tuple({'shades_per_region': n, 'compressed_art_bytes': size,
                      'encoder': 'greedy H7A' if i % 2 == 0 else 'safe optimal H7A'} for i, (n, size) in enumerate(sizes))
    measurements = {pair.pair_id: {'pixel_hashes': tuple(hashlib.sha256(l.image.tobytes()).hexdigest() for l in layers),
                      'destinations': {slot.slot_id: attempts for slot in slots}}}
    return bundle_api.TextureBundle('synthetic', (pair,), ()), slots, measurements


class PlanTests(unittest.TestCase):
    def test_rows_show_first_fit_and_explicit_alternatives(self):
        bundle, slots, measurements = inputs()
        plan = bundle_api.build_plan(bundle, slots, measurements=measurements)
        fit = plan.receipt['assignments'][0]['fit']
        self.assertEqual(fit['status'], 'fits after simplification to 4 shades')
        self.assertEqual(fit['compressed_art_bytes'], 47912)
        self.assertEqual(fit['budget_bytes'], 48609)
        self.assertEqual([p['slot'] for p in fit['packages_with_room']], [23, 85, 92])
        self.assertEqual(plan.assignments[0][1].crest_asset_index, 92)
        roomy = bundle_api.build_plan(bundle, slots, [bundle_api.Assignment(bundle.pairs[0].pair_id, slots[1].slot_id)], measurements=measurements)
        self.assertEqual(roomy.receipt['assignments'][0]['fit']['status'], 'fits as is')
        strict = bundle_api.build_plan(bundle, slots, measurements=measurements, allow_simplification=False)
        fit = strict.receipt['assignments'][0]['fit']
        self.assertEqual(fit['status'], 'does not fit (needs 24,022 more bytes)')
        self.assertIn('simplification disabled', fit['refusal'])
        self.assertEqual(strict.assignments[0][1], slots[0])

    def test_overflow_is_refused_before_any_staging(self):
        bundle, slots, measurements = inputs()
        plan = bundle_api.build_plan(bundle, slots, measurements=measurements, allow_simplification=False)
        session = SimpleNamespace(source=SimpleNamespace(index_0a=Path('synthetic')), modifications=(),
                                  replace_helmet_crest_design=Mock())
        with patch.object(bundle_api, 'destination_slots', return_value=slots), patch.object(bundle_api, 'measure_bundle_logos', return_value=measurements):
            with self.assertRaisesRegex(bundle_api.BundleError, 'holds 48,609.*needs 72,631.*Choose a package with room.*flatten the art'):
                bundle_api.stage_plan(session, plan)
        session.replace_helmet_crest_design.assert_not_called()

    def test_staging_carries_opt_out_and_source_images_are_preserved(self):
        bundle, slots, measurements = inputs()
        plan = bundle_api.build_plan(bundle, slots, [bundle_api.Assignment(bundle.pairs[0].pair_id, slots[1].slot_id)],
                                     measurements=measurements, allow_simplification=False)
        session = SimpleNamespace(source=SimpleNamespace(index_0a=Path('synthetic')), modifications=(),
                                  replace_helmet_crest_design=Mock(return_value='staged'))
        def stage(path, **kwargs):
            self.assertFalse(kwargs['allow_simplification'])
            with Image.open(path) as image:
                self.assertEqual(image.tobytes(), bundle.pairs[0].layers[0].image.tobytes())
            return 'staged'
        session.replace_helmet_crest_design.side_effect = stage
        with patch.object(bundle_api, 'destination_slots', return_value=slots), patch.object(bundle_api, 'measure_bundle_logos', return_value=measurements):
            self.assertEqual(bundle_api.stage_plan(session, plan), ('staged',))

    def test_mutated_pixels_invalidate_measured_rows(self):
        bundle, slots, measurements = inputs()
        bundle.pairs[0].layers[0].image.putpixel((0, 0), (0, 0, 0, 255))
        with self.assertRaisesRegex(bundle_api.BundleError, 'changed since budget measurement'):
            bundle_api.build_plan(bundle, slots, measurements=measurements)

    def test_policy_defaults_and_project_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _source(root)
            session = ApfSession(source, Mock(), cache_root=root / 'cache')
            try:
                with patch('mod_editor.apf_studio.session.apf_team_crests.crest_slots', return_value=(SimpleNamespace(asset_index=92, outer_entry_index=621),)):
                    mod = session.replace_helmet_crest_design(_mask(root / 'mask.png'), profile=RETAIL_CREST_PROFILE,
                          crest_asset_index=92, crest_outer_entry_index=621, allow_simplification=False)
                project = root / 'fit.apf2k8mod'
                save_project(project, source_sha256=source.source_sha256, modifications=(mod,))
                _, loaded, _ = load_project(project, expected_source_sha256=source.source_sha256, destination_dir=root / 'loaded')
                self.assertFalse(loaded[0].metadata['allow_simplification'])
                legacy = dict(mod.metadata)
                legacy.pop('allow_simplification')
                self.assertTrue(validate_metadata(mod.asset_id, mod.kind, legacy).get('allow_simplification', True))
                with self.assertRaises(HelmetCrestDesignError):
                    validate_metadata(mod.asset_id, mod.kind, {**legacy, 'allow_simplification': 'false'})
            finally:
                session.close()

    def test_linked_cache_uses_reduced_masks_and_preserves_alpha(self):
        bundle, _, _ = inputs()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [root / f'l{i}.png' for i in range(2)]
            for layer, path in zip(bundle.pairs[0].layers, paths):
                layer.image.save(path)
            modification = SimpleNamespace(replacement_path=paths[0], metadata={'crest_asset_index': 92})
            package = SimpleNamespace(manifest={'fit': {'shades_per_region': 4, 'changed_layers': ['logo_l0', 'logo_l1']}})
            fitted = ApfBuildService._fitted_crest_cache_paths(modification, paths[1], package, root)
            for layer, path, original in zip(bundle.pairs[0].layers, fitted, paths):
                with Image.open(path) as image:
                    self.assertEqual(image.tobytes(), writer.simplify_regions(layer.image.tobytes(), 4))
                with Image.open(original) as image:
                    self.assertEqual(image.tobytes(), layer.image.tobytes())


try:
    from PyQt5.QtWidgets import QApplication, QDialog, QDialogButtonBox, QWidget
    from mod_editor.apf_studio import ps3_texture_bundle_qt as qt
    from mod_editor.apf_studio.team_art_qt import TeamArtReplaceDialog
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, 'PyQt5 unavailable')
class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_rows_tooltips_opt_out_and_explicit_room_action(self):
        bundle, slots, measurements = inputs()
        with patch.object(writer, 'compress_h7a', side_effect=AssertionError('encoder on UI thread')):
            dialog = qt.Ps3BundleMappingDialog(bundle, slots, measurements=measurements)
            self.addCleanup(dialog.close)
            self.assertTrue(dialog.allow_simplification.isChecked())
            self.assertEqual(dialog.table.item(0, 4).text(), 'fits after simplification to 4 shades')
            self.assertIn('Logo slot 23', dialog.table.item(0, 4).toolTip())
            self.assertIn('165,345', dialog.rows[0][2].itemText(2))
            dialog.allow_simplification.setChecked(False)
            self.assertFalse(dialog.buttons.button(QDialogButtonBox.Ok).isEnabled())
            self.assertEqual(dialog.rows[0][2].currentData(), 'logo:621')
            dialog.accept()
            self.assertIsNone(dialog.plan)
            dialog.room_button.click()
            self.assertEqual(dialog.rows[0][2].currentData(), 'logo:301')
            self.assertEqual(dialog.table.item(0, 4).text(), 'fits as is')
            dialog.accept()
            self.assertFalse(dialog.plan.receipt['allow_simplification'])

    def test_known_budgets_cannot_accept_without_worker_measurement(self):
        bundle, slots, _ = inputs()
        dialog = qt.Ps3BundleMappingDialog(bundle, slots)
        self.addCleanup(dialog.close)
        self.assertFalse(dialog.buttons.button(QDialogButtonBox.Ok).isEnabled())
        dialog.accept()
        self.assertIsNone(dialog.plan)

    def test_import_action_measures_inside_worker_before_review(self):
        bundle, slots, measurements = inputs()
        session = SimpleNamespace(source=SimpleNamespace(index_0a=Path('synthetic')))
        facade = SimpleNamespace(source_ready=True, require_session=lambda: session, session=session)
        parent = QWidget()
        self.addCleanup(parent.close)
        main_thread = threading.get_ident()
        tasks, calls = [], []
        def run_task(title, task, completed, blocking):
            tasks.append((task, completed))
        def measure(*args):
            self.assertNotEqual(threading.get_ident(), main_thread)
            calls.append('measured')
            return measurements
        with patch.object(qt.QFileDialog, 'getOpenFileName', return_value=('synthetic.zip', '')), \
             patch.object(qt, 'read_bundle', return_value=bundle), patch.object(qt, 'destination_slots', return_value=slots), \
             patch.object(qt, 'measure_bundle_logos', side_effect=measure):
            button = qt.import_button(parent, facade, run_task, Mock())
            button.menu().actions()[0].trigger()
            self.assertEqual(calls, [])
            task, completed = tasks.pop()
            results = []
            thread = threading.Thread(target=lambda: results.append(task(lambda *_: None)))
            thread.start(); thread.join()
            self.assertEqual(calls, ['measured'])
            with patch.object(qt.Ps3BundleMappingDialog, 'exec_', return_value=QDialog.Rejected) as review:
                completed(results[0])
                review.assert_called_once()

    def test_completed_build_displays_exact_fit_status(self):
        import json
        from mod_editor.apf_studio.gui import ApfStudioMainWindow
        status = "Logo slot 92: 16 shades reduced to 4 per region to fit 48,609 bytes; 47,912 used"
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / 'receipt.json'
            manifest.write_text(json.dumps({'edits': [{'fit_status': [status]}]}))
            receipt = SimpleNamespace(modified_assets=('crest',), manifest=manifest)
            self.assertIn(status, ApfStudioMainWindow._build_edit_detail(receipt))

    def test_team_art_setting_defaults_on_and_explains_saved_policy(self):
        layer = SimpleNamespace(name='logo_l0', width=512, height=512, codec='4444')
        package = SimpleNamespace(label='Logo slot 92', outer_index=621, family='logo', layers=(layer,))
        dialog = TeamArtReplaceDialog(package)
        self.addCleanup(dialog.close)
        self.assertTrue(dialog.allow_simplification.isChecked())
        self.assertIn('project', dialog.allow_simplification.toolTip())
        self.assertIn('alpha', dialog.allow_simplification.toolTip())


if __name__ == '__main__':
    unittest.main()
