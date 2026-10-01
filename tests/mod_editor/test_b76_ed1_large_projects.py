"""Coach Edwards regressions, synthetic packs and artwork; never build a disc."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from b71_t5_project_probe import Corpus
from b70_equipment_fixture import SizedFixture
from mod_editor.core import equipment_reporting as reporting
from mod_editor.core import equipment_palette as palette
from mod_editor.core import nfl2k5_project_fit as fit
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.nfl2k5_model_project_session import ModelProjectSession, _read_models
from mod_editor.core.errors import ValidationError
from mod_editor.studio import project_archive as archive
from mod_editor.studio.project_manifest import recover_manifest
import nfl2k5_visual_mod_project as visual


def measurements(corpus):
    return [dict(asset_id=r.asset_id, set_selector=r.set_selector, fit_status='fits',
                 encoded_dimensions=[32, 32], used_palette_entries=16, encoded_bytes=800)
            for r in corpus.rows]


class LargeProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_beta75_over_16mib_opens_and_saves_smaller_without_losing_art(self):
        corpus = Corpus(self.root, 600)
        corpus.catalog.get_uniform_set = lambda selector: SimpleNamespace(selector=selector)
        rows = measurements(corpus)
        # Beta 75 kept every digest after inputs changed. Reproduce 100 fits of
        # 200 uniform sets, each with three equipment textures, within its
        # 25,000-key count limit. The schema and pretty JSON match that writer.
        receipts = {fit.digest([generation, n]): rows[n:n+3]
                    for generation in range(100) for n in range(0, len(rows), 3)}
        with zipfile.ZipFile(corpus.project) as old:
            document = json.loads(old.read('project.json'))
            payloads = {n: old.read(n) for n in old.namelist() if n != 'project.json'}
        document['uniform_colors'] = [dict(selector=f'{n%32:02}H{n//32}',
            facemask='FF112233', turtleneck='FF445566') for n in range(200)]
        document['fit_receipts'] = receipts
        payload = archive._canonical_json(document)
        self.assertGreater(len(payload), 16 * 1024**2)
        legacy_size = len(payload)
        legacy = self.root / 'beta75.2k5mod'
        with zipfile.ZipFile(legacy, 'w', compression=zipfile.ZIP_DEFLATED) as out:
            out.writestr('project.json', payload)
            for name, data in payloads.items():
                out.writestr(name, data)
        original_hash = hashlib.sha256(legacy.read_bytes()).hexdigest()
        del payload, document, receipts
        # This is the precheck that used to fail even for projects with no models.
        _read_models(legacy)
        session = corpus.session()
        from mod_editor.studio.facade import Nfl2k5StudioFacade
        facade = object.__new__(Nfl2k5StudioFacade)
        facade._lock = threading.RLock()
        facade._cache, facade._session = corpus.cache, object()
        facade._text_catalog = facade._audio_service = None
        facade._crib_catalog = facade._crib_io = facade._stadium_cache_result = None
        facade._uniform_catalog = corpus.catalog
        facade._attach_visual_catalog = lambda candidate: None
        facade._require_playbook_inspector = lambda: None
        facade.session_factory = lambda cache, catalog: session
        with (corpus.context(), patch.object(writer, '_compile_group', side_effect=AssertionError('open encoded')),
              patch('mod_editor.core.nfl2k5_unif_color_writer.resolve_uniform_color_record',
                    return_value=SimpleNamespace(pair=('FF000000', 'FF000000')))):
            result = facade.load_project(legacy, lambda *args: None)
            self.assertTrue(result.project_migrated)
            self.assertIn('Recovered a large project', result.message)
            self.assertEqual(session.modified_count, 800)
            self.assertIn('Save', ' '.join(session.project_open_notes))
            saved = self.root / 'recovered.2k5mod'
            session.save_shareable_project(saved)
            reopened = corpus.session(name='reopened')
            self.assertEqual(reopened.load_shareable_project(saved), 800)
        self.assertEqual(hashlib.sha256(legacy.read_bytes()).hexdigest(), original_hash)
        with zipfile.ZipFile(saved) as out:
            size = out.getinfo('project.json').file_size
            self.assertLess(size, archive.MAX_MANIFEST_BYTES)
            self.assertLess(size, legacy_size // 10)
            for name, data in payloads.items():
                self.assertEqual(out.read(name), data)
            self.assertEqual(len(json.loads(out.read('project.json'))['uniform_colors']), 200)
        print(f'N1 legacy manifest={legacy_size} saved={size}, 600 PNGs and 200 colours preserved', flush=True)

    def test_repeated_equipment_fits_prune_old_keys(self):
        corpus = Corpus(self.root, 60)
        session = corpus.session()
        with corpus.context():
            session.load_shareable_project(corpus.project)
            for generation in range(8):
                corpus.cache.source.sha256 = fit.digest(generation)
                fit.remember(session, measurements(corpus))
            self.assertEqual(len(session._project_fit_receipts), 20)
            current = dict(session._project_fit_receipts)
            saved = self.root/'current.2k5mod'
            session.save_shareable_project(saved)
            reopened = corpus.session(name='current')
            reopened.load_shareable_project(saved)
            self.assertEqual(reopened._project_fit_receipts, current)

    def test_art_receipts_store_shared_body_once_and_prune_changed_inputs(self):
        pack = self.root/'pack'
        pack.write_bytes(b'synthetic source span')
        edits = [SimpleNamespace(asset_id=f'jersey-{n}', replacement_path=self.root/f'{n}.png',
                                 replacement_sha256=fit.digest(n)) for n in range(80)]
        session = SimpleNamespace(cache=SimpleNamespace(pack0=self.root/'0',
            source=SimpleNamespace(sha256='a'*64)), iter_project_png_edits=lambda: iter(edits))
        view = SimpleNamespace(packs=[SimpleNamespace(name='pack', path=pack, size=pack.stat().st_size)])
        # NFL2K5_ART_FIT emits resolved paths, including macOS /private temp
        # aliases and Windows' canonical path spelling.
        record = dict(paths=[str(e.replacement_path.resolve()) for e in edits], targets=[dict(pack='pack',
            offset=0, size=pack.stat().st_size, sha256=hashlib.sha256(pack.read_bytes()).hexdigest())])
        with patch.object(writer, 'parse_archive', return_value=view):
            for generation in range(10):
                edits[0].replacement_sha256 = fit.digest(generation)
                fit.remember_art(session, [record])
            self.assertEqual(len(session._project_fit_receipts), 1)
            self.assertEqual(len(next(iter(session._project_fit_receipts.values()))), 1)
            self.assertEqual(len(fit.art_fit_labels(session)), 80)
            self.assertTrue(all('checked' in label for label in fit.art_fit_labels(session).values()))
            pack.write_bytes(b'changed source bytes')
            fit.restore_art(session, session._project_fit_receipts)
            self.assertFalse(session._project_fit_receipts)

    def test_receipt_byte_budget_cannot_make_a_saved_project_unreadable(self):
        corpus = Corpus(self.root, 3)
        row = measurements(corpus)[0]
        receipts = {fit.digest(n): [dict(row, fit_error='diagnostic ' * 8000)] for n in range(100)}
        receipts[fit.digest('huge')] = [dict(row, attempts=['x' * (5 * 1024**2)])]
        clean = archive._fit_receipts(receipts)
        self.assertLessEqual(len(archive._canonical_json(clean)), archive.MAX_FIT_RECEIPTS_BYTES)
        saved = self.root/'bounded.2k5mod'
        archive.save_project_archive(catalog=corpus.catalog, asset_io=corpus.io(),
            edits=corpus.edits, destination=saved, fit_receipts=receipts)
        with corpus.context():
            self.assertEqual(corpus.session().load_shareable_project(saved), 3)
        # Advisory metadata is omitted when a tighter manifest leaves no room.
        document = dict(edits=[], fit_receipts=clean)
        with patch.object(archive, 'MAX_MANIFEST_BYTES', 100):
            self.assertEqual(json.loads(archive.manifest_payload(document)), {'edits': []})

    def test_save_refuses_oversize_authored_metadata_before_replacing_file(self):
        corpus = Corpus(self.root, 3)
        original = corpus.project.read_bytes()
        with patch.object(archive, 'MAX_MANIFEST_BYTES', 128):
            with self.assertRaisesRegex(ValidationError, 'manifest|metadata'):
                archive.save_project_archive(catalog=corpus.catalog, asset_io=corpus.io(),
                    edits=corpus.edits, destination=corpus.project, replace=True)
        self.assertEqual(corpus.project.read_bytes(), original)

    def test_equipment_receipt_detailed_art_stays_below_parent_read_bound(self):
        fixture = SizedFixture(self.root, width=256, margin=4000)
        rgba = b''.join(bytes((x, y, (x+y) % 256, 255)) for y in range(256) for x in range(256))
        edits = [fixture.png(n, rgba=rgba, independent=False) for n in range(3)]
        # Real palette projection, quality report, normalization and parent
        # readback. Only synthetic pack/catalog I/O is substituted by fixture.
        _, _, report, _, _ = fixture.build(edits)
        effective = dict(edits=[dict(target=key, png=str(path)) for key, path in edits])
        normalized = visual.normalized_import_report(report, effective, 'uniform_equipment_texture')
        payload = visual.canonical_json(normalized)
        receipt = self.root / '05162_import.json'
        receipt.write_bytes(payload)
        self.assertEqual(reporting._read_receipt(receipt), payload)
        self.assertLess(len(payload), 256 * 1024)
        for row in normalized['edits']:
            quality = row['palette_quality']
            self.assertGreater(quality['merged_colour_count'], 65000)
            self.assertLessEqual(len(quality['merged_colours']), 64)
            self.assertEqual(quality['merged_colour_count'],
                             len(quality['merged_colours']) + quality['merged_colours_omitted'])
        manifest = self.root/'manifest.json'
        descriptor = dict(kind='uniform_equipment_texture', import_report=dict(
            file_name=receipt.name, sha256=hashlib.sha256(payload).hexdigest()))
        manifest.write_text(json.dumps(dict(output=dict(artifact_directory=str(self.root)), edits=[descriptor])))
        verified = reporting.load_verified_reports(manifest)
        self.assertTrue(reporting.verified_build_texture_lines(manifest, verified.reports))
        receipt.write_bytes(payload + b' ')
        with self.assertRaisesRegex(ValidationError, 'hash|checksum|changed'):
            reporting.load_verified_reports(manifest)
        print(f'N2 three 256x256 textures, import receipt={len(payload)} bytes', flush=True)

    def test_legacy_quality_cache_is_compacted_with_exact_counts(self):
        merges = [dict(from_rgba=[n, 0, 0, 255], to_rgba=[0, 0, 0, 255], pixels=n+1) for n in range(256)]
        original = dict(merged_colours=merges, maximum_channel_error=255, mean_delta_e76=12.5,
                        maximum_delta_e76=22.5, merge_reason='to fit the palette')
        compact = palette.compact_quality(original)
        self.assertEqual(len(original['merged_colours']), 256)
        self.assertEqual(compact['merged_pixel_count'], sum(range(1, 257)))
        self.assertEqual(compact['mean_delta_e76'], 12.5)
        self.assertIn('Showing 64 of 256', palette.merge_message(compact))
        self.assertEqual(palette.compact_quality(compact), compact)

    def test_catalog_group_size_supports_the_existing_receipt_budget(self):
        targets, groups = writer.load_targets()
        self.assertEqual(len(targets), 28530)
        self.assertEqual(max(map(len, groups.values())), 14)
        self.assertEqual(max(row.width*row.height for row in targets.values()), 65536)
        self.assertEqual(14 * palette.MAX_MERGED_COLOUR_EXAMPLES, 896)

    def test_recovery_validates_json_including_discarded_metadata(self):
        for broken in (
            b'{"fit_receipts":{"x":1,"x":2}}', b'{"edits":[],"edits":[]}',
            b'{"fit_receipts":[1,]}', b'{"fit_receipts":{"x":NaN}}',
            b'{"fit_receipts":{"x":"\\q"}}', b'{"fit_receipts":"\x01"}',
            b'{"fit_receipts":01}', b'{"fit_receipts":true} trailing',
            b'{"fit_receipts":{"x":1}', b'{"fit_receipts":' + b'['*66 + b']'*66 + b'}',
            b'{"fit_receipts":"\xff"}', b'{"fit_receipts":"unterminated}',
        ):
            with self.subTest(broken=broken[:80]), self.assertRaises((ValidationError, UnicodeError)):
                recover_manifest(io.BytesIO(broken), 1024)
        history = {'big': 'quote " backslash \\ unicode \u2603 ' * 50000,
                   'nested': [True, None, 12.5, {'escaped': '\t\n'}]}
        document = dict(edits=[], fit_receipts=history, schema='test')
        result = recover_manifest(io.BytesIO(json.dumps(document).encode()), 1024)
        self.assertEqual(result, dict(edits=[], schema='test'))

    def test_model_archive_copy_obeys_save_manifest_limit(self):
        from mod_editor.core.nfl2k5_model_project_session import _copy_archive
        corpus = Corpus(self.root, 3)
        destination = self.root/'model.2k5mod'
        with patch.object(archive, 'MAX_MANIFEST_BYTES', 100):
            with self.assertRaisesRegex(ValidationError, 'metadata'):
                _copy_archive(corpus.project, destination, dict(model_edits='x'*1024))
        self.assertFalse(destination.exists())

    def test_models_extension_preserves_record_and_migration_note(self):
        from mod_editor.core import nfl2k5_model_project as models
        from mod_editor.core import nfl2k5_model_project_session as model_session
        corpus = Corpus(self.root, 3)
        corpus.cache.inventory = self.root/'synthetic-inventory.json'
        authored = self.root/'authored.gltf'
        authored.write_bytes(b'synthetic model authoring input')
        record = dict(schema=models.SCHEMA, target='o3c113', mode='geometry', summary='Synthetic model',
            sources=[dict(path=str(authored), sha256=models.sha(authored.read_bytes()), size=authored.stat().st_size)],
            options={}, check={}, changed_bytes=1, witnessed=False,
            members=[dict(key='o3c113', size=64, before_sha256='a'*64, after_sha256='b'*64,
                          decoded_sha256='c'*64, changes=[[32, 'eA==']], decoded_changes=[[0, 'eA==']])])
        model_payload = models.canonical([record])
        with zipfile.ZipFile(corpus.project) as old:
            document = json.loads(old.read('project.json'))
            members = {n: old.read(n) for n in old.namelist() if n != 'project.json'}
        document['model_edits'] = dict(file=model_session.MEMBER, count=1,
                                      size=len(model_payload), sha256=models.sha(model_payload))
        document['fit_receipts'] = {fit.digest(n): measurements(corpus) for n in range(10)}
        legacy = self.root/'legacy-model.2k5mod'
        with zipfile.ZipFile(legacy, 'w', compression=zipfile.ZIP_DEFLATED) as out:
            out.writestr('project.json', archive._canonical_json(document))
            out.writestr(model_session.MEMBER, model_payload)
            for name, data in members.items():
                out.writestr(name, data)
        before = legacy.read_bytes()
        with patch('mod_editor.studio.session.Nfl2k5ProductVisualIO', corpus.io):
            session = ModelProjectSession(corpus.cache, corpus.catalog, root=self.root/'sessions', session_id='model')
        session.attach_visual_catalog(corpus.catalog)
        with (corpus.context(), patch.object(archive, 'MAX_MANIFEST_BYTES', 4096),
              patch.object(model_session.M, 'ModelSource'), patch.object(models, 'restore_member') as restore):
            self.assertEqual(session.load_shareable_project(legacy), 4)
            restore.assert_called_once()
            self.assertTrue(session.project_open_notes)
            self.assertEqual(session.model_records, (record,))
            saved = self.root/'model-saved.2k5mod'
            session.save_shareable_project(saved)
            with zipfile.ZipFile(saved) as out:
                self.assertLess(out.getinfo('project.json').file_size, 4096)
                self.assertEqual(out.read(model_session.MEMBER), model_payload)
        self.assertEqual(legacy.read_bytes(), before)

    def test_migration_enables_save_in_the_project_open_callback(self):
        from mod_editor.gui.studio_qt import StudioMainWindow
        from mod_editor.studio.facade import StudioOperationResult
        path = self.root/'recovered.2k5mod'
        archive.save_project_archive(catalog=None, asset_io=None, edits=(), destination=path, allow_empty=True)
        callbacks = []
        owner = SimpleNamespace(_music_panel=None, _audio_panel=None, workspace_store=None,
            _refuse_while_audio_busy=lambda *a: False, _clear_texture_master_drafts=lambda: None,
            _set_status=lambda *a: None, _refresh_edit_state=lambda **k: None,
            _restore_music_build_settings=lambda: None, _defer_until_blocking_task_finished=lambda *a: None,
            _refresh_build_includes=lambda **k: None, _start_task=lambda operation, callback, **k: callbacks.append(callback))
        StudioMainWindow._load_project_path(owner, path)
        callbacks[0](StudioOperationResult('Recovered', path, archive.project_target_identity(path), project_migrated=True))
        self.assertTrue(owner._workspace_dirty)


if __name__ == '__main__':
    unittest.main()
