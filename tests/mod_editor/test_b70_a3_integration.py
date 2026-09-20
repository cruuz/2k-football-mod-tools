"""Exercise T2's landed session, GUI and verified-build paths alongside T1."""
from copy import deepcopy
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from mod_editor.core import equipment_reporting, nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_build_service import BuildResult, Nfl2k5BuildService
from mod_editor.gui import studio_qt
import test_b70_t2_wiring as proposed
import test_nfl2k5_build_service as build_fixtures
import test_nfl2k5_equipment_import as import_fixtures
import test_nfl2k5_equipment_import_wiring as gui_fixtures


class AppliedWiringTests(unittest.TestCase):
    def test_live_project_rows_use_cached_measurements_and_hide_stale_fits(self):
        source = textwrap.dedent(inspect.getsource(studio_qt.StudioMainWindow._refresh_build_includes))
        with patch.object(proposed, 'snippet', return_value=source):
            proposed.WiringTests().test_project_rows_take_returned_preflight_measurements_without_recompiling()

    def test_live_build_message_keeps_t1_grouping_and_t2_measurements(self):
        row = dict(kind='live_number_nameplate', selector='arm:1', family='arm', digit=1,
                   asset_code='26', side='A', variant=0, shortfall_bytes=42,
                   suggestion=dict(width=32, height=32, colours=16), message='old wall ' * 20)
        rows = (row, deepcopy(row))
        original = deepcopy(rows)
        caption = 'Equipment socks00 (05H0): fitted at 64 x 64, 16 colours.'
        result = BuildResult(Path('user-game.iso'), 100, 'a' * 64, 1, 20,
                             kept_retail=rows, texture_summary=(caption,))
        self.assertEqual(result.message.count('42 bytes over; 32 x 32 at 16 colours fits'), 1)
        self.assertIn('Kept retail for 1 uniform slot:', result.message)
        self.assertNotIn('old wall', result.message)
        self.assertTrue(result.message.endswith(caption))
        self.assertTrue(result.message.startswith('Build complete: user-game.iso is ready.'))
        self.assertEqual(rows, original)
        self.assertEqual(BuildResult(Path('plain.iso'), 100, 'a' * 64, 1, 20).message, '')
        only_texture = BuildResult(Path('texture.iso'), 100, 'a' * 64, 1, 20, texture_summary=(caption,))
        self.assertIn(caption, only_texture.message)

    def test_reopened_project_remembers_the_existing_preflight_result_once(self):
        fixture = import_fixtures.EquipmentSessionTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.stage()
        archive = fixture.root / 'reopen.2k5mod'
        fixture.a.save_shareable_project(archive)
        with patch.object(writer, 'build_unified_uniform_equipment_imports',
                          side_effect=AssertionError('Captions must not compile')):
            expected_labels = equipment_reporting.project_fit_labels(fixture.a)
        reopened = fixture.session('reopened')
        measured = []
        preflight = writer.preflight_project_equipment

        def capture(*args, **kwargs):
            rows = preflight(*args, **kwargs)
            measured.extend(rows)
            return rows

        # Beta 71.1 (T5): opening a project no longer fits anything at all. The saved receipts
        # carry the measurements, so preflight must not be called even once on reopen.
        with fixture.f.context(), patch.object(writer, 'preflight_project_equipment', side_effect=capture) as checked:
            self.assertEqual(reopened.load_shareable_project(archive), 1)
        checked.assert_not_called()
        self.assertFalse(measured)
        with patch.object(writer, 'build_unified_uniform_equipment_imports',
                          side_effect=AssertionError('Captions must not compile')):
            self.assertEqual(equipment_reporting.project_fit_labels(reopened), expected_labels)

    def test_arm_dialog_runs_before_fitting_and_cancel_keeps_the_project(self):
        fixture_type = gui_fixtures.EquipmentWiringTests
        fixture_type.setUpClass()
        for accepted in (False, True):
            with self.subTest(accepted=accepted):
                fixture = fixture_type()
                try:
                    fixture.setUp()
                    fixture.asset.family = 'arm'
                    fixture.asset.kind = 'live_number_nameplate'
                    dialog = SimpleNamespace(Accepted=1, exec_=lambda: int(accepted))
                    with patch.object(fixture.dialog_module, 'ArmDigitImportDialog', return_value=dialog) as constructor:
                        fixture.invoke()
                    constructor.assert_called_once_with(fixture.asset, fixture.host)
                    fixture.constructor.assert_not_called()
                    fixture.facade.replace_equipment_texture.assert_not_called()
                    if accepted:
                        fixture.host._fit_for_slot.assert_called_once()
                        fixture.facade.replace_asset.assert_called_once_with(
                            fixture.asset, Path('fitted.png'), fixture.progress)
                    else:
                        fixture.host._fit_for_slot.assert_not_called()
                        fixture.host._prepare_texture_master_draft.assert_not_called()
                        fixture.host._start_task.assert_not_called()
                        fixture.host._mark_workspace_changed.assert_not_called()
                finally:
                    fixture.doCleanups()


class TextureReceiptRunner(build_fixtures.FakeBackendRunner):
    def __init__(self, *, tamper=False):
        super().__init__()
        self.tamper = tamper

    def run(self, argv, cwd):
        result = super().run(argv, cwd)
        artifact_dir = self._argument(tuple(argv), '--artifact-dir')
        if argv[2] == 'build':
            manifest = self._argument(tuple(argv), '--manifest')
            value = json.loads(manifest.read_text())
            value['output']['artifact_directory'] = str(artifact_dir)
            equipment = dict(edits=[dict(name='socks00', set_selector=selector,
                                        encoded_dimensions=[64, 64], used_palette_entries=16)
                                    for selector in ('05H0', '05A0')])
            stadium = dict(compiled_textures=[dict(target=dict(
                selector='nfl2k5.stadium.o3141.c0006.scene1998.texture0042', scene_id='scene1998',
                stadium_package=dict(label='Chicago Field / Day / Dry (s05dd.iff)'),
                mapped_material_names=['banner_corp']))])
            value['edits'] = []
            for kind, report in (('uniform_equipment_texture', equipment), ('stadium_texture', stadium)):
                name = kind + '.json'
                payload = json.dumps(report).encode()
                (artifact_dir / name).write_bytes(payload)
                value['edits'].append(dict(kind=kind, import_report=dict(
                    file_name=name, sha256=hashlib.sha256(payload).hexdigest())))
            manifest.write_text(json.dumps(value))
            if self.tamper:
                # Changed after the manifest recorded its hash. Beta 74 reads
                # the receipts the moment the builder exits, so this is where
                # a tamper still has to be caught; one during the verifier's
                # minutes of hashing no longer reaches the summary at all
                # (test_b74_receipts_read_before_verify).
                path = artifact_dir / 'uniform_equipment_texture.json'
                path.write_bytes(path.read_bytes() + b' ')
        return result


class VerifiedBuildTests(unittest.TestCase):
    def test_build_returns_equipment_and_stadium_measurements_after_stage_cleanup(self):
        with tempfile.TemporaryDirectory(prefix='b70-a3-build-') as directory:
            fixture = build_fixtures.SyntheticFixture(Path(directory))
            runner = TextureReceiptRunner()
            with patch.object(writer, 'build_unified_uniform_equipment_imports',
                              side_effect=AssertionError('Reporting must not compile')):
                result = Nfl2k5BuildService(runner=runner).build(fixture.cache, fixture.project, fixture.output)
            self.assertTrue(fixture.output.is_file())
            self.assertEqual(fixture.stage_paths(), [])
            self.assertEqual([call[2] for call in runner.calls], ['build', 'verify'])
            self.assertEqual(result.texture_summary[0],
                             'Equipment socks00 (05A0, 05H0): fitted at 64 x 64, 16 colours.')
            self.assertEqual(len(result.texture_summary), 2)
            for phrase in ('Chicago Field / Day / Dry', 'texture0042', 'banner_corp', 'UNWITNESSED'):
                self.assertIn(phrase, result.texture_summary[1])
            self.assertTrue(result.message.endswith('\n'.join(result.texture_summary)))

    def test_changed_measurement_receipt_is_refused_before_publication(self):
        with tempfile.TemporaryDirectory(prefix='b70-a3-tamper-') as directory:
            fixture = build_fixtures.SyntheticFixture(Path(directory))
            with self.assertRaisesRegex(ValidationError, 'measured texture receipt changed after the build wrote it') as caught:
                Nfl2k5BuildService(runner=TextureReceiptRunner(tamper=True)).build(
                    fixture.cache, fixture.project, fixture.output)
            self.assertFalse(fixture.output.exists())
            # Beta 74: a refused build no longer destroys its evidence. The stage
            # is renamed aside with the manifest and the receipts kept and the
            # staged disc dropped, and the refusal names that folder. Before
            # this, a week of Windows receipt failures had to be read off phone
            # photos of the dialog because rmtree ran on every exit.
            kept = sorted(fixture.output.parent.glob(f'.{fixture.output.name}.2k5mod-failed-*'))
            self.assertEqual(len(kept), 1, kept)
            self.assertIn(str(kept[0]), str(caught.exception))
            self.assertTrue((kept[0] / 'build-manifest.json').is_file())
            self.assertTrue((kept[0] / 'build-artifacts' / 'uniform_equipment_texture.json').is_file())
            self.assertFalse((kept[0] / 'modded.xiso').exists())
            # And nothing else of the stage is left behind under its live name.
            live = [p for p in fixture.output.parent.glob(f'.{fixture.output.name}.2k5mod-*')
                    if '-failed-' not in p.name]
            self.assertEqual(live, [])


if __name__ == '__main__':
    unittest.main()
