"""Real StudioSession paired transactions, caches and authored project round trips."""
from pathlib import Path
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.music_fixtures import MusicDisc,music_session,wav_bytes
from mod_editor.core.nfl2k5_audio_catalog import _wav_info
from mod_editor.studio.music_service import MusicService

class MusicServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.disc=MusicDisc(self.root)
        self.service,self.fixture=music_session(self.root,self.disc)
        self.session=self.service.session
        self.wav=self.root/'authored.wav';self.wav.write_bytes(wav_bytes(sample=2500))
    def tearDown(self): self.temp.cleanup()
    def put(self,row='cribmusic:28'):
        return self.service.replace_batch([(row,self.wav)],match_volume=False)
    def snapshot(self):
        return (dict(self.session._audio_edits),tuple(self.session._undo_order),
                {p.name:p.read_bytes() for p in self.session.replacements.iterdir()})

    def test_pair_replace_repeat_restore_undo_redo_and_original_identity(self):
        row=self.service.catalog.get('cribmusic:28')
        originals=tuple(self.service.original_path(t).read_bytes() for t in row.targets)
        result=self.put()
        self.assertEqual(len(result.changed_asset_ids),2)
        self.assertEqual(len(self.session._undo_order),1)
        with self.assertRaisesRegex(Exception,'already matches'): self.put()
        self.assertEqual(len(self.session._undo_order),1)
        self.assertEqual(tuple(self.service.original_path(t).read_bytes() for t in row.targets),originals)
        self.service.restore(row.row_id)
        self.assertEqual(self.service.row_state(row.row_id),'Original')
        self.service.undo(); self.assertEqual(self.service.row_state(row.row_id),'Replaced')
        self.service.redo(); self.assertEqual(self.service.row_state(row.row_id),'Original')
        self.service.undo(); self.assertEqual(self.service.row_state(row.row_id),'Replaced')
        self.assertEqual(self.service.metadata(row.row_id)['source_name'],'authored.wav')

    def test_first_middle_last_pairs_plus_all_presentation_families_one_undo(self):
        ids=('femusic:0','cribmusic:0','cribmusic:28','cribmusic:58','loadm:0','wrapupm:0','halftimeaudio:0','drafta:0')
        self.service.replace_batch([(i,self.wav) for i in ids],match_volume=False)
        self.assertEqual(len(self.session._audio_edits),11)
        self.assertEqual(len(self.session._undo_order),1)
        self.service.undo()
        self.assertFalse(self.session._audio_edits)

    def test_prepare_cancel_and_generation_change_leave_no_edits(self):
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'cancelled'):
            self.service.prepare_batch([('cribmusic:0',self.wav)],cancelled=lambda:True)
        self.assertEqual(self.snapshot(),before)
        batch=self.service.prepare_batch([('cribmusic:0',self.wav)],match_volume=False)
        self.service.set_policy(music_policy='jukebox_menus')
        with self.assertRaisesRegex(ValueError,'changed'): self.service.commit_batch(batch)
        self.assertFalse(batch.directory.exists())
        self.assertEqual(self.snapshot(),before)

    def test_failed_later_file_or_second_twin_and_manifest_roll_back(self):
        before=self.snapshot()
        bad=self.root/'bad.wav';bad.write_bytes(b'bad')
        with self.assertRaises(Exception):
            self.service.prepare_batch([('femusic:0',self.wav),('cribmusic:0',bad)])
        self.assertEqual(self.snapshot(),before)
        original=self.service.audio.authorize_replacement_snapshot
        def fail_mono(target,snapshot):
            if target.channels==1: raise ValueError('second twin refused')
            return original(target,snapshot)
        with patch.object(self.service.audio,'authorize_replacement_snapshot',side_effect=fail_mono):
            with self.assertRaisesRegex(ValueError,'second twin'): self.put()
        self.assertEqual(self.snapshot(),before)
        batch=self.service.prepare_batch([('cribmusic:0',self.wav)],match_volume=False)
        with patch.object(self.session,'_write_manifest',side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError,'disk full'): self.service.commit_batch(batch)
        self.assertEqual(self.snapshot(),before)

    def test_encoded_preview_export_and_local_set_use_decoded_output(self):
        self.put()
        preview=self.service.playback_path('cribmusic:28')
        exported=self.root/'current.wav'
        self.service.export_wav('cribmusic:28',exported)
        self.assertEqual(exported.read_bytes(),preview.read_bytes())
        fit=self.service.metadata('cribmusic:28')
        import hashlib
        self.assertEqual(hashlib.sha256(_wav_info(preview.read_bytes())[3]).hexdigest(),fit['targets'][0]['decoded_pcm_sha256'])
        bundle=self.root/'listening.zip'
        self.service.export_set(bundle,['femusic:0','cribmusic:28'])
        with zipfile.ZipFile(bundle) as z:
            self.assertTrue(any(n.endswith('.m3u') or n.endswith('.m3u8') for n in z.namelist()))
            self.assertEqual(sum(n.endswith('.wav') for n in z.namelist()),2)
        with self.assertRaises(Exception): self.service.export_wav('cribmusic:28',exported)

    def test_project_roundtrip_reproduces_encoded_bytes_and_originals_from_source(self):
        self.put()
        self.service.set_policy(music_policy='jukebox_menus',music_unlock=True,music_userlist=True)
        edits=self.service.encoded_edits()
        project=self.root/'music.2k5music';self.service.save_project(project)
        with zipfile.ZipFile(project) as z:
            doc=json.loads(z.read('music.json'))
            self.assertEqual(len(doc['rows']),1)
            self.assertEqual(len(z.namelist()),3)
            self.assertFalse(any('original' in n for n in z.namelist()))
            for target in self.service.catalog.get('cribmusic:28').targets:
                original=self.service.original_path(target).read_bytes()
                self.assertTrue(all(z.read(n)!=original for n in z.namelist()))
        from mod_editor.studio.session import StudioSession
        other=StudioSession(self.fixture.cache,object(),root=self.root/'sessions',session_id='reopen')
        other.attach_audio_service(self.service.audio)
        reopened=MusicService(other)
        self.assertEqual(reopened.load_project(project),1)
        actual=reopened.encoded_edits()
        self.assertEqual([e.encoded_path.read_bytes() for e in edits],[e.encoded_path.read_bytes() for e in actual])
        self.assertEqual(reopened.policy,self.service.policy)
        self.assertEqual(reopened.metadata('cribmusic:28'),self.service.metadata('cribmusic:28'))
        self.assertEqual(reopened.load_project(project),1)
        self.assertEqual(len(other._undo_order),1)
        reopened.restore('cribmusic:28')
        self.assertFalse(reopened.encoded_edits())

    def test_normal_studio_project_and_canonical_build_project_keep_both_twins(self):
        self.put()
        project=self.root/'normal.2k5mod'
        self.session.save_shareable_project(project)
        from mod_editor.studio.session import StudioSession
        other=StudioSession(self.fixture.cache,object(),root=self.root/'sessions',session_id='normal')
        other.attach_audio_service(self.service.audio)
        self.assertEqual(other.load_shareable_project(project),2)
        row=self.service.catalog.get('cribmusic:28')
        for target in row.targets:
            self.assertEqual(other.current_audio_path(target).read_bytes(),self.session.current_audio_path(target).read_bytes())
        self.assertEqual(len(other._audio_edits),2)
        canonical=other.canonical_document()
        self.assertEqual(sum(edit.get('kind')=='ausb_audio' for edit in canonical['edits']),2)

    def test_project_wrong_source_missing_twin_bad_hash_encoder_and_extra_payload_refuse_atomically(self):
        self.put();project=self.root/'music.2k5music';self.service.save_project(project)
        with zipfile.ZipFile(project) as z: members={n:z.read(n) for n in z.namelist()}
        before=self.snapshot()
        mutations=(lambda d:d.update(source_sha256='0'*64),
                   lambda d:d['rows'][0]['targets'].pop(),
                   lambda d:d['rows'][0]['targets'][1].update(encoded_sha256='0'*64),
                   lambda d:d['rows'][0]['targets'][0].update(member='../escape.wav'),
                   lambda d:d['rows'].append(d['rows'][0]),
                   lambda d:d.update(encoder='unknown/v2'),
                   lambda d:d['rows'][0]['metadata']['fit'].update(source_seconds=float('nan')),
                   lambda d:d['rows'][0]['metadata']['fit'].pop('notes'))
        for i,mutate in enumerate(mutations):
            d=json.loads(members['music.json']);mutate(d)
            bad=self.root/f'bad-{i}.2k5music'
            with zipfile.ZipFile(bad,'w') as z:
                for n,b in members.items(): z.writestr(n,json.dumps(d).encode() if n=='music.json' else b)
            with self.assertRaises(Exception):self.service.load_project(bad)
            self.assertEqual(self.snapshot(),before)

    def test_one_twin_edited_in_audio_cues_needs_attention_and_restore_repairs(self):
        row=self.service.catalog.get('cribmusic:28')
        self.session.replace_audio(row.primary,self.wav)
        self.assertEqual(self.service.row_state(row.row_id),'Needs attention')
        with self.assertRaisesRegex(ValueError,'one jukebox version'): self.service.encoded_edits()
        self.service.restore(row.row_id)
        self.assertEqual(self.service.row_state(row.row_id),'Original')

    def test_replacement_supplied_file_and_encoded_cache_tampering_refused(self):
        batch=self.service.prepare_batch([('cribmusic:0',self.wav)],match_volume=False)
        # Dropped input may disappear after preparation; pinned private PCM survives.
        self.wav.unlink();self.service.commit_batch(batch)
        edit=self.service.encoded_edits()[0]
        bad=bytearray(edit.encoded_path.read_bytes());bad[2]=89;edit.encoded_path.write_bytes(bad)
        with self.assertRaises(ValueError):self.service.playback_path('cribmusic:0')

if __name__=='__main__': unittest.main()
