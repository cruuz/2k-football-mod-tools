"""Scalar project persistence and a real offscreen opacity panel."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mod_editor.apf_studio import field_material_service as service
from mod_editor.apf_studio.models import ApfSource
from mod_editor.apf_studio.session import ApfSession
from mod_editor.apf_studio.project import load_project
from tests.mod_editor.test_apf_field_material_writer import scene_fixture


class FieldProjectTests(unittest.TestCase):
    def test_normal_build_composes_opacity_after_another_entry_writer(self):
        from contextlib import ExitStack
        from dataclasses import replace
        import json
        from mod_editor.apf_studio.build import ApfBuildService
        from mod_editor.apf_studio.models import Modification
        from tests.mod_editor import test_apf_build_raw_span_overlays as fixtures
        from tests.mod_editor.test_apf_book_unlock import iff
        w = service.writer
        original = iff(scene_fixture(), 'field', 'SCNE')
        textured_scene = bytearray(scene_fixture())
        textured_scene[0x90] = 99  # Another writer owns this scene byte.
        textured = iff(bytes(textured_scene), 'field', 'SCNE')
        self.assertEqual(len(original), len(textured))
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory); game = root/'game'; game.mkdir()
            source = fixtures._source(game)
            source.index_0a.write_bytes(source.index_0a.read_bytes()[:0x3000] + original)
            source = replace(source, source_sha256=w.sha(source.index_0a.read_bytes()),
                             source_size=source.index_0a.stat().st_size)
            tree = fixtures._complete_tree(game)
            stack.enter_context(patch.object(fixtures, 'OUTER_LAYOUT', (*fixtures.OUTER_LAYOUT[:2], (2, 0x3000, len(original)))))
            stack.enter_context(patch.dict(w.ENTRY_NAME_IDS, {2: 0x1002}))
            stack.enter_context(patch('mod_editor.apf_studio.build.EXPECTED_TREE', tree))
            stack.enter_context(patch('mod_editor.apf_studio.build.EXPECTED_0A_SHA256', source.source_sha256))
            stack.enter_context(patch.object(w.apf_outer, 'parse_archive', side_effect=fixtures._archive))
            stack.enter_context(patch('mod_editor.apf_studio.build.disc_book_identity_report', return_value={'synthetic': True}))
            stack.enter_context(patch.object(ApfBuildService, '_reject_any_source_audio_reuse'))
            stack.enter_context(patch.object(ApfBuildService, '_compile', return_value=(2, textured, 'synthetic_texture/v1')))
            texture_path = root/'texture.png'; texture_path.write_bytes(b'synthetic author input')
            texture = Modification('synthetic:texture', 'uniform', texture_path, w.sha(texture_path.read_bytes()), {})
            recipe_path = root/'opacity.json'; recipe_path.write_bytes(service.encode(2, {'ticks': 0.25}))
            recipe = Modification(service.selector(2), service.PROVIDER_KIND, recipe_path, w.sha(recipe_path.read_bytes()),
                                  {'schema': service.SCHEMA, 'outer_index': 2})
            receipt = ApfBuildService(source).build((recipe, texture), root/'output')
            output = (root/'output'/'0A').read_bytes()[0x3000:]
            entry = fixtures._archive(root/'output'/'0A').entries[2]
            _, part, decoded = w._parse_entry(entry, output)
            wanted, _ = w.compile_scene(bytes(textured_scene), {'ticks': 0.25})
            self.assertEqual(decoded[part.offset:part.offset+part.length], wanted)
            self.assertEqual(source.index_0a.read_bytes()[0x3000:], original)
            manifest = json.loads(receipt.manifest.read_text())
            self.assertEqual(manifest['compiled_entry_count'], 1)

    def test_stage_undo_save_load_and_reparse_recipe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); index = root/'0A'
            source = ApfSource(index, root, index, 'a'*64, 1, 'b'*64, 'Synthetic')
            session = ApfSession(source, SimpleNamespace(), cache_root=root/'cache')
            with patch.object(service.writer, 'build_patch', return_value=(b'compiled', {'reparsed': True})):
                session.apply_field_material(53, {'ticks': 0.25})
                project = root/'field.apf2k8mod'; session.save_project(project)
                _, loaded, _ = load_project(project, expected_source_sha256='a'*64, destination_dir=root/'load')
                self.assertEqual(service.read_profile(loaded[0])['alphas'], {'ticks': 0.25})
                self.assertTrue(session.undo()); self.assertEqual(session.modified_count, 0)
                self.assertEqual(session.load_project(project), 1)

    def test_failed_refit_does_not_stage_or_record_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = ApfSource(root/'0A',root,root/'0A','a'*64,1,'b'*64,'Synthetic')
            session = ApfSession(source,SimpleNamespace(),cache_root=root/'cache')
            with patch.object(service.writer, 'build_patch', side_effect=service.ValidationError('allocation full')):
                with self.assertRaisesRegex(ValueError, 'allocation full'):
                    session.apply_field_material(53, {'ticks': 0.25})
            self.assertFalse(session.undo()); self.assertEqual(session.modified_count, 0)

    def test_panel_stages_only_checked_materials_and_shows_receipt(self):
        from PyQt5.QtWidgets import QApplication
        from mod_editor.apf_studio.field_material_qt import FieldMaterialOpacityPanel
        app = QApplication.instance() or QApplication([])
        materials = service.writer.parse_scene(scene_fixture())
        calls = []
        def apply(outer, values, progress):
            calls.append((outer, values)); return service.writer.compile_scene(scene_fixture(), values)[1]
        facade = SimpleNamespace(source=object(), field_material_context=lambda o,p:(materials,{}), apply_field_material=apply)
        def run(title, work, done, modal): done(work(lambda *a:None)); return True
        panel = FieldMaterialOpacityPanel(facade,run); panel.set_context()
        self.assertTrue(all(not box.isChecked() for box,value in panel.controls.values()))
        box,value = panel.controls['graphic_overlay_4']; box.setChecked(True); value.setValue(25)
        panel.stage_button.click()
        self.assertEqual(calls,[(53,{'graphic_overlay_4':0.25})])
        self.assertIn('25%',panel.note.text()); self.assertIn('unwitnessed',panel.note.text())
        panel.close(); app.processEvents()


if __name__ == '__main__': unittest.main()
