"""Portable playlist Build settings, atomic project open and private-session save."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_music_playlist as playlist
from mod_editor.core.errors import ValidationError
from mod_editor.studio import project_archive as projects
from tests.mod_editor.test_nfl2k5_music_playlist_library import options
from tests.mod_editor.music_fixtures import MusicDisc,music_session


class PlaylistProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.document=options({('cribmusic',i) for i in range(100,200)})
        self.state=dict(music_shuffle=True,music_shuffle_selection=self.document)
        self.path=self.root/'choices.2k5mod'

    def save(self,state=None,**kwargs):
        return projects.save_project_archive(catalog=None,asset_io=None,edits=(),destination=self.path,
                 build_settings=self.state if state is None else state,**kwargs)

    def load(self):
        return projects.load_project_archive(source=self.path,catalog=None,asset_io=None,private_root=self.root)

    def test_playlist_only_project_roundtrip_and_legacy_empty_project(self):
        self.save()
        with zipfile.ZipFile(self.path) as z:
            self.assertEqual(z.namelist(),['project.json'])
            manifest=json.loads(z.read('project.json'))
        self.assertEqual(manifest['build_settings'],self.state)
        self.assertNotIn('empty_project',manifest)
        loaded=self.load()
        try:self.assertEqual(loaded.build_settings,self.state)
        finally:loaded.cleanup()
        self.save({},replace=True,allow_empty=True)
        loaded=self.load()
        try:self.assertEqual(loaded.build_settings,{})
        finally:loaded.cleanup()

    def test_invalid_build_choices_preserve_existing_project_and_import_cleans_up(self):
        self.save();before=self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.save(dict(self.state,music_shuffle=False),replace=True)
        self.assertEqual(self.path.read_bytes(),before)
        with zipfile.ZipFile(self.path) as z:manifest=json.loads(z.read('project.json'))
        manifest['build_settings']['music_shuffle_selection']['enabled']=[100]
        with zipfile.ZipFile(self.path,'w') as z:z.writestr('project.json',json.dumps(manifest))
        with self.assertRaises(ValidationError):self.load()
        self.assertFalse(list(self.root.glob('project-import-*')))

    def test_session_named_and_recovery_save_reopen_and_detached_state(self):
        source=self.root/'source';source.mkdir();disc=MusicDisc(source)
        service,_=music_session(source,disc);session=service.session
        session.set_build_settings(self.state)
        self.assertTrue(session.has_project_metadata)
        self.assertEqual(session.modified_count,0)
        snapshot=session.build_settings;snapshot['music_shuffle_selection']['checked'].clear()
        self.assertEqual(session.build_settings,self.state)
        session.save_shareable_project(self.path)
        destination=self.root/'new';destination.mkdir()
        restored_service,_=music_session(destination,disc);restored=restored_service.session
        restored.load_shareable_project(self.path)
        self.assertEqual(restored.build_settings,self.state)
        # Same API as quiet recovery: build-only preferences count as metadata.
        recovery=self.root/'recovery.2k5mod'
        restored.save_shareable_project(recovery,replace=True,allow_empty=True)
        with zipfile.ZipFile(recovery) as z:
            self.assertEqual(json.loads(z.read('project.json'))['build_settings'],self.state)
        with patch.object(session,'_write_manifest',side_effect=OSError('injected write failure')):
            with self.assertRaises(OSError):session.set_build_settings({})
        self.assertEqual(session.build_settings,self.state)
        failed=self.root/'failed';failed.mkdir();candidate=music_session(failed,disc)[0].session
        with patch.object(candidate,'_write_manifest',side_effect=OSError('injected import failure')):
            with self.assertRaises(ValidationError):candidate.load_shareable_project(self.path)
        self.assertEqual(candidate.build_settings,{})
        self.assertEqual(candidate.modified_count,0)

    def test_asset_revert_and_undo_keep_build_preferences(self):
        disc=MusicDisc(self.root)
        service,_=music_session(self.root,disc);session=service.session
        session.set_build_settings(self.state)
        cue=next(iter(service.catalog.rows)).primary.asset_id
        session.set_audio_annotation(cue,title='Personal label')
        session.revert_all()
        self.assertEqual(session.annotation_count,0)
        self.assertEqual(session.build_settings,self.state)
        session.undo()
        self.assertEqual(session.annotation_count,1)
        self.assertEqual(session.build_settings,self.state)


if __name__=='__main__':unittest.main()
