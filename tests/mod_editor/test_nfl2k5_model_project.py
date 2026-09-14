"""Model project records, the real project builder and offscreen Models replay.

Compact transport fixtures use temporary resources read from the user's retail
archive. No retail bytes are embedded here or retained after the tests.
"""
from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(ROOT/'tests'), str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from mod_editor.core import nfl2k5_models as M, nfl2k5_model_project as P
from mod_editor.core.nfl2k5_model_project_session import ModelProjectSession
from mod_editor.core.nfl2k5_source_cache import SourceCache
from mod_editor.core.model import SourceRecord
from mod_editor.core import nfl2k5_build_service as BS
from mod_editor.studio.facade import Nfl2k5StudioFacade
import nfl2k5_visual_mod_project as V
from nfl2k5_xiso_fixture import SyntheticXiso

PACK = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted'))/'ESPN NFL 2K5 (USA)/vc_53450030/0'
INVENTORY = Path(os.environ.get('NFL2K5_MODEL_INVENTORY',
                               ROOT/'reports/assets/nfl2k5_resource_chunks_v2.json'))


class RecordTests(unittest.TestCase):
    def test_sparse_changes_round_trip_and_refuse_unchanged_or_overlapping_bytes(self):
        before, after = b'abcd0123', b'aBCd0Z23'
        rows = P.changed_runs(before, after)
        self.assertEqual(P.apply_runs(before, rows), after)
        self.assertEqual(sum(len(__import__('base64').b64decode(r[1])) for r in rows), 3)
        with self.assertRaisesRegex(P.ValidationError, 'overlaps'):
            P.apply_runs(before, rows + rows)
        with self.assertRaisesRegex(P.ValidationError, 'unchanged'):
            P.apply_runs(before, [[0, 'YQ==']])

    def test_pair_refusal_names_missing_file_and_ui_omits_class_prefix(self):
        from test_nfl2k5_model_skeleton import body_set
        from mod_editor.core import nfl2k5_model_skeleton as S
        from mod_editor.gui.models_panel_qt import _Task
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with self.assertRaises(M.ModelsError) as error:
                S.compile_set(object(),body_set(),folder)
            message = str(error.exception)
            self.assertIn(str(folder/'lo_body_o3c113.gltf'),message)
            self.assertIn('Geometry only and Check model',message)
            self.assertIn('File > Export > glTF 2.0 > Include > Data > Custom Properties',message)
            emitted = []
            def fail():
                raise M.ModelsError(message)
            task = _Task(fail); task.signals.failed.connect(emitted.append); task.run()
            self.assertEqual(emitted,[message])
            self.assertNotIn('ModelsError:',emitted[0])

    def test_external_buffer_change_and_missing_file_name_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root/'lo.gltf'; binary = root/'lo.bin'
            path.write_text('{"buffers":[{"uri":"lo.bin","byteLength":1}]}')
            binary.write_bytes(b'x')
            record = {'sources': P.source_files([path])}
            self.assertFalse(P.recheck_files(record))
            binary.write_bytes(b'y')
            def names(target, messages):
                # the refusal names the file by its recorded path, which may be the resolved form (Windows 8.3 temp names, macOS /private/var)
                joined = '\n'.join(messages)
                return str(target) in joined or str(target.resolve()) in joined
            self.assertTrue(names(binary, P.recheck_files(record)))
            path.unlink()
            self.assertTrue(names(path, P.recheck_files(record)))

    def test_guardian_conflict_is_early_and_names_the_shared_resources(self):
        session = SimpleNamespace(model_records=({'target':'body', 'summary':'body', 'mode':'geometry',
            'changed_bytes':1, 'members':[{'key':'o3c113'}]},))
        with self.assertRaisesRegex(P.ValidationError, 'Guardian cap.*o3c113'):
            P.validate_build_plan(SimpleNamespace(guardian_cap=True), session)
        P.validate_build_plan(SimpleNamespace(guardian_cap=False), session)
        with self.assertRaisesRegex(P.ValidationError, 'Guardian cap/overlay'):
            P.validate_build_plan(SimpleNamespace(guardian_overlay=True), session)


class InlineBackend:
    """Run the actual build and receipt verifier against a compact test identity."""
    def __init__(self):
        self.commands = []

    def run(self, argv, cwd):
        argv = list(argv); self.commands.append(argv)
        command = argv[2]
        fields = dict(zip(argv[3::2], argv[4::2]))
        args = [Path(fields[n]) for n in ('--project','--source-xiso','--output-xiso','--manifest','--artifact-dir')]
        stream = io.StringIO()
        with redirect_stdout(stream):
            if command == 'build':
                result = V.build(*args, Path(fields['--index']), Path(fields['--inventory']))
                print('NFL2K5_VISUAL_MOD_BUILD_PASS receipt_sha256=' + V.file_digest(args[3]))
            else:
                result = V.verify_written(*args, fields['--receipt-sha256'])
                print('NFL2K5_VISUAL_MOD_VERIFY_PASS runtime=false')
        return BS.CommandResult(tuple(argv), 0, stream.getvalue(), '')


class RetailProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path in (PACK, INVENTORY):
            if not path.is_file():
                raise unittest.SkipTest(f'Private model round-trip input absent: {path}')
        cls.retail = M.ModelSource(PACK, INVENTORY)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        originals = [P._resource(self.retail, key) for key in ('o3c113','o3c114','o3c115','o3c116')]
        spans = [self.retail.span(resource) for resource in originals]
        body = b''.join(spans)
        pack_size = ((len(body)+0x10000-1)//0x10000+1)*0x10000
        self.fixture = SyntheticXiso(self.root, [(0,b'x'),(1,b'x'),(2,b'x'),(3,body),(4,b'tail')],
                                     pack_sizes=(pack_size,), pack_sectors=(64,))
        rows, offset = [], 0
        for resource, span in zip(originals,spans):
            row = asdict(resource); row.update(chunk_offset=offset, outer_size=len(body), outer_id='0x00000003')
            rows.append(row); offset += len(span)
        self.inventory = self.root/'inventory.json'
        self.inventory.write_bytes(P.canonical({'schema':'nfl2k5_resource_chunk_inventory/v1','chunks':rows}))
        self.pack = self.fixture.retail_packs/'0'
        self.source = M.ModelSource(self.pack, self.inventory)
        self.export = M.export_model(self.source, 'o3c113', self.root/'lo_body_o3c113.gltf')
        doc = json.loads(self.export.gltf_path.read_bytes())
        a = doc['accessors'][doc['meshes'][0]['primitives'][0]['attributes']['POSITION']]
        view = doc['bufferViews'][a['bufferView']]
        blob = bytearray(self.export.bin_path.read_bytes())
        at = view.get('byteOffset',0)+a.get('byteOffset',0)
        xyz = struct.unpack_from('<3f',blob,at)
        struct.pack_into('<3f',blob,at,xyz[0]+.1,*xyz[1:])
        self.export.bin_path.write_bytes(blob)
        self.compiled = M.compile_import(self.source,'o3c113',self.export.gltf_path)
        self.record = P.make_record(self.source,self.compiled,[self.export.gltf_path])
        source = SourceRecord(selected_path=str(self.fixture.path), inspected_path=str(self.fixture.path),
            kind='xiso',sha256=P.sha(self.fixture.image),size=len(self.fixture.image),recognized=True,
            fingerprint_id=BS.EXPECTED_FINGERPRINT,detected_game='nfl2k5',note='compact model transport test')
        self.cache = SourceCache(source,self.root,self.pack,self.inventory,self.root,1,5,{'SCNE':1})
        self.catalog = SimpleNamespace(uniform_sets=())
        self.session = ModelProjectSession(self.cache,self.catalog,root=self.root/'sessions')
        self.facade = Nfl2k5StudioFacade(uniform_catalog=self.catalog, xemu_command=(),
            session_factory=lambda c,u: ModelProjectSession(c,u,root=self.root/'sessions'))
        self.facade._cache,self.facade._session = self.cache,self.session
        self.facade._playbook_inspector = SimpleNamespace()

    def build_context(self):
        stack = ExitStack()
        def validate(path, *, hash_image=True):
            fd = os.open(path,os.O_RDONLY|getattr(os,'O_BINARY',0))
            entries, directory = V.common.parse_xdvdfs(fd,path.stat().st_size)
            return path.resolve(),fd,V.common.fd_identity(fd),V.common.sha256_fd(fd) if hash_image else '',entries,directory,entries['default.xbe']
        stack.enter_context(patch.object(V,'validate_source',side_effect=validate))
        for module, name, value in ((V,'INDEX_SIZE',self.pack.stat().st_size),(V,'INDEX_SHA256',P.sha(self.pack.read_bytes())),
                (V,'INVENTORY_SIZE',self.inventory.stat().st_size),(V,'INVENTORY_SHA256',P.sha(self.inventory.read_bytes())),
                (BS,'PACK0_SIZE',self.pack.stat().st_size),(BS,'INVENTORY_SIZE',self.inventory.stat().st_size),
                (V.common,'EXPECTED_XBE_SHA256',P.sha(b'XBEH'+bytes(12)))):
            stack.enter_context(patch.object(module,name,value))
        return stack

    def test_facade_save_reopen_stale_sources_build_compiled_bytes_and_revert(self):
        result = self.facade.stage_model_edit(self.source,self.compiled,[self.export.gltf_path])
        self.assertIn('Added model edit',result.message)
        self.assertEqual(self.facade.modified_count,1)
        self.assertEqual(self.facade.model_project_plan[0]['changed_bytes'],self.record['changed_bytes'])
        project = self.root/'models.2k5mod'
        self.facade.save_project(project,lambda *a:None)
        with zipfile.ZipFile(project) as archive:
            rows = json.loads(archive.read('model-edits.json'))
            self.assertEqual(rows[0],self.record)
            self.assertNotIn(self.source.span(self.source.resource('o3c113')),archive.read('model-edits.json'))
        self.export.bin_path.unlink()
        opened = self.facade.load_project(project,lambda *a:None)
        self.assertIn(str(self.export.bin_path),opened.message)
        self.assertIn('Re-check refused',opened.message)
        with self.assertRaisesRegex(P.ValidationError,'Re-check refused'):
            self.facade._session.stage_model(self.record)
        runner = InlineBackend(); self.facade.build_service = BS.Nfl2k5BuildService(runner=runner)
        with self.build_context():
            built = self.facade.build_iso(self.root/'project.xiso.iso',lambda *a:None)
        quick = self.root/'quick.xiso.iso'
        M.write_import_copy(self.source,self.compiled,self.fixture.path,quick)
        self.assertEqual(built.output_xiso.read_bytes(),quick.read_bytes())
        self.assertEqual(self.fixture.path.read_bytes(),self.fixture.image)
        self.assertEqual(built.changed_byte_count,self.record['changed_bytes'])
        self.assertEqual(len(runner.commands),2)
        print('MODEL_PROJECT_PROOF ' + json.dumps({'mode':'geometry','source_sha256':P.sha(self.fixture.image),
              'quick_sha256':P.sha(quick.read_bytes()),'project_sha256':built.output_sha256,
              'disc_size':len(self.fixture.image),'changed_bytes':built.changed_byte_count,
              'external_buffer_missing_at_build':True,'source_unchanged':True,'witnessed':False},sort_keys=True))
        self.facade.revert_all(lambda *a:None)
        self.assertEqual(self.facade.modified_count,0)

    def test_offscreen_add_undo_readd_project_build(self):
        from PyQt5.QtWidgets import QApplication, QLabel
        from mod_editor.gui.models_panel_qt import ModelsPanel
        app = QApplication.instance() or QApplication([])
        panel = ModelsPanel(self.facade); bottom = QLabel()
        panel.project_changed.connect(lambda:bottom.setText(f'{self.facade.modified_count} project edits'))
        try:
            panel.apply_catalog(self.source,self.source.catalog())
            panel.select_key('o3c113'); panel.wait_idle(); app.processEvents()
            panel.compile_edited(self.export.gltf_path); panel.wait_idle(); app.processEvents()
            self.assertTrue(panel.add_project_button.isEnabled())
            self.assertIn(f"{self.record['changed_bytes']:,} bytes change on disc", panel.status_label.text())
            panel.add_project_button.click(); panel.wait_idle(); app.processEvents()
            self.assertEqual(bottom.text(),'1 project edits')
            self.facade.undo(lambda *a:None)
            self.assertEqual(self.facade.modified_count,0)
            panel.add_project_button.click(); panel.wait_idle(); app.processEvents()
            self.assertEqual(self.facade.modified_count,1)
            self.facade.build_service = BS.Nfl2k5BuildService(runner=InlineBackend())
            with self.build_context():
                result = self.facade.build_iso(self.root/'offscreen.xiso.iso',lambda *a:None)
            self.assertGreater(result.changed_byte_count,0)
            self.assertIn('same',panel.write_button.toolTip())
        finally:
            panel.wait_idle(); panel.deleteLater(); bottom.deleteLater(); app.processEvents()

    def test_paired_skeleton_project_is_identical_to_quick_path_and_historical_replay(self):
        from mod_editor.core import nfl2k5_model_skeleton as S
        from test_nfl2k5_model_skeleton import body_set, author
        folder = self.root/'paired'; folder.mkdir()
        bs = body_set()
        exports = M.export_body_set(self.source,bs,folder)
        bone = next(b for b in S.BONES if b.name == 'left_forearm')
        for key in ('o3c113','o3c114'):
            path = folder/M.body_set_file_name(next(e for e in bs.entries if e.key == key))
            doc = json.loads(path.read_bytes())
            transforms = S._skin(self.source,key)[-1].transforms
            author(doc,transforms,S.target_positions(transforms,bone,1.01))
            path.write_bytes(P.canonical(doc))
        compiled = M.compile_body_set_import(self.source,bs,folder,import_skeleton=True)
        record = P.make_record(self.source,compiled,[e.gltf_path for e in exports])
        self.session.stage_model(record)
        project = self.session.write_canonical_project(self.root/'paired.json')
        quick, built = self.root/'paired-quick.iso', self.root/'paired-project.iso'
        M.write_import_set_copy(self.source,compiled,self.fixture.path,quick)
        manifest, artifacts = self.root/'paired-receipt.json',self.root/'paired-artifacts'
        with self.build_context():
            V.build(project,self.fixture.path,built,manifest,artifacts,self.pack,self.inventory)
            checked = V.verify(project,self.fixture.path,built,manifest,artifacts,self.pack,self.inventory)
        self.assertEqual(quick.read_bytes(),built.read_bytes())
        self.assertEqual(checked['changed_byte_count'],record['changed_bytes'])
        receipt = json.loads(manifest.read_bytes())
        self.assertEqual({row['kind'] for row in receipt['edits']},{P.KIND})
        self.assertEqual(len(record['members']),4)
        self.assertNotIn('before_hex',json.dumps(record))
        print('MODEL_PROJECT_PROOF ' + json.dumps({'mode':'skeleton','source_sha256':P.sha(self.fixture.image),
              'quick_sha256':P.sha(quick.read_bytes()),'project_sha256':P.sha(built.read_bytes()),
              'disc_size':len(self.fixture.image),'changed_bytes':record['changed_bytes'],
              'guarded_resources':4,'historical_receipt_replay':True,'witnessed':False},sort_keys=True))

    def test_decoded_composition_keeps_disjoint_changes_and_names_conflict(self):
        resource, before, after = P.restore_member(self.source,self.record['members'][0])
        decoded, _ = self.source._probe.decode_resource(before,resource)
        model, _ = self.source._probe.decode_resource(after,resource)
        # A second checked model supplies a real disjoint position lane change.
        second = M.export_model(self.source,'o3c113',self.root/'second.gltf')
        doc = json.loads(second.gltf_path.read_bytes()); blob = bytearray(second.bin_path.read_bytes())
        a = doc['accessors'][doc['meshes'][0]['primitives'][0]['attributes']['POSITION']]
        view = doc['bufferViews'][a['bufferView']]
        at = view.get('byteOffset',0)+a.get('byteOffset',0)+12
        xyz = struct.unpack_from('<3f',blob,at)
        struct.pack_into('<3f',blob,at,xyz[0]+.1,*xyz[1:]); second.bin_path.write_bytes(blob)
        other = M.compile_import(self.source,'o3c113',second.gltf_path).rebuilt_span
        merged = P.merge_decoded(self.source,resource,before,after,other,'lo_body and artwork')
        composed, _ = self.source._probe.decode_resource(merged,resource)
        other_decoded, _ = self.source._probe.decode_resource(other,resource)
        self.assertEqual(composed,bytes(b if b != a else c for a,b,c in zip(decoded,model,other_decoded)))
        conflicting = bytearray(model)
        offset = next(i for i,(a,b) in enumerate(zip(decoded,model)) if a != b)
        conflicting[offset] = next(v for v in range(256) if v not in (decoded[offset],model[offset]))
        replacement, _ = M._tools_module('nfl_vc_lz_fill').rebuild_fixed_span_filled(before,bytes(conflicting),encoder='auto')
        with self.assertRaisesRegex(P.ValidationError,'lo_body and artwork.*conflicting'):
            P.merge_decoded(self.source,resource,before,after,replacement,'lo_body and artwork')

    def test_mixed_texture_model_undo_and_revert_all_are_one_history(self):
        from test_studio_session import _Asset, _Catalog, _AssetIO
        asset = _Asset(); self.session.catalog = _Catalog(asset)
        artwork = _AssetIO(self.cache)
        artwork.original = self.root/'original.png'; artwork.original.write_bytes(b'ORIGINAL-CONTAINER')
        self.session.asset_io = artwork
        first = self.root/'first.png'; first.write_bytes(b'USER-A-CONTAINER')
        second = self.root/'second.png'; second.write_bytes(b'USER-B-CONTAINER')
        self.session.replace(asset,first)
        self.session.stage_model(self.record)
        self.session.replace(asset,second)
        self.assertEqual(self.session.modified_count,2)
        self.session.undo()
        self.assertEqual(self.session.modified_count,2)
        self.assertEqual({r['kind'] for r in self.session.canonical_document()['edits']},{'torso','model_edit'})
        self.session.undo()
        self.assertEqual(self.session.modified_count,1)
        self.session.stage_model(self.record)
        self.assertEqual(self.session.revert_all(),2)
        self.assertEqual(self.session.modified_count,0)
        self.session.undo()
        self.assertEqual(self.session.modified_count,2)
        document = json.loads((self.session.root/'session.json').read_bytes())
        self.assertEqual(len(document['model_edits']),1)
        self.session.undo()
        self.assertEqual(self.session.modified_count,1)

    def test_model_recipe_tamper_and_source_foreign_refuse(self):
        row = self.record['members'][0]
        changed = json.loads(json.dumps(row)); changed['after_sha256'] = '0'*64
        with self.assertRaisesRegex(P.ValidationError,'stored compiled model bytes changed'):
            P.restore_member(self.source,changed)
        self.assertEqual(P.restore_member(self.source,row)[2],self.compiled.rebuilt_span)
        resource, before, _ = P.restore_member(self.source,row)
        decoded, _ = self.source._probe.decode_resource(before,resource)
        bad = bytearray(decoded); bad[0x20] ^= 1
        packed, _ = M._tools_module('nfl_vc_lz_fill').rebuild_fixed_span_filled(before,bytes(bad),encoder='auto')
        forged = {**row,'after_sha256':P.sha(packed),'decoded_sha256':P.sha(bad),
                  'changes':P.changed_runs(before,packed),'decoded_changes':P.changed_runs(decoded,bad)}
        with self.assertRaisesRegex(P.ValidationError,'outside the checked geometry/bind lanes'):
            P.restore_member(self.source,forged)


if __name__ == '__main__':
    unittest.main()
