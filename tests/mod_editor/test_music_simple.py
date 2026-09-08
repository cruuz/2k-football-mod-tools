"""Add songs through real conform/encoder/project code. No audio is played."""
import io
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.mod_editor.music_fixtures import MusicDisc, music_session, wav_bytes
from mod_editor.core import audio_conform as conform
from mod_editor.core import nfl2k5_music_build as build
from mod_editor.core import nfl2k5_music_banks as banks
from mod_editor.core.nfl2k5_audio_catalog import _wav_info
from mod_editor.studio.music_service import MusicService, sha
from mod_editor.studio.session import StudioSession


def tone(path, *, rate=22050, bits=16, frames=4097, amplitude=7000):
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((2, bits//8, rate, frames, 'NONE', 'not compressed'))
        if bits == 8:
            pcm = bytes(round(128+amplitude/256*math.sin(i*.12)) for i in range(frames) for _ in range(2))
        else:
            pcm = b''.join(struct.pack('<h', round(amplitude*math.sin(i*.12)))*2 for i in range(frames))
        wav.writeframes(pcm)
    return path


def mp3(source, destination, bitrate='128k'):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise unittest.SkipTest('FFmpeg and FFprobe are absent; generated MP3 conversion unavailable')
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(source), '-b:a', bitrate,
                    '-y', str(destination)], check=True, capture_output=True)
    return destination


class SongServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.disc = MusicDisc(self.root)
        self.service, self.fixture = music_session(self.root, self.disc)
        self.wav = tone(self.root/'First song.wav')

    def test_full_length_native_volume_and_preview_are_exact_library_encoder(self):
        tone(self.wav, frames=9001)
        with patch.object(conform._convert_module(), 'ffmpeg_available', return_value=False):
            rows = self.service.add_songs([self.wav])
        row = rows[0]
        self.assertEqual(row['title'], 'First song')
        self.assertEqual(row['artist'], '')
        self.assertEqual(row['fit']['frames'], 9001)
        self.assertGreater(row['fit']['gain_db'], 0)
        prepared = _wav_info(Path(row['wav']).read_bytes())[3]
        source = _wav_info(self.wav.read_bytes())[3]
        self.assertNotEqual(source, prepared)
        # Same chunk boundaries and last-frame repetition as the actual builder.
        pcm = prepared+prepared[-4:]*((-9001) % 64)
        encoded = b''.join(banks.encode_stream(pcm[i:i+banks.ENCODE_FRAMES*4], 2)
                           for i in range(0, len(pcm), banks.ENCODE_FRAMES*4))
        self.assertEqual(Path(row['encoded']).read_bytes(), encoded)
        preview = self.service.song_playback_path(row['id'])
        self.assertNotEqual(preview, self.wav)
        self.assertEqual(sha(_wav_info(preview.read_bytes())[3]), row['decoded_pcm_sha256'])
        recipe = json.loads(Path(self.service.library_recipe_path()).read_text())
        self.assertEqual(recipe['tracks'][:59], [{'source_index': i} for i in range(59)])
        self.assertEqual(recipe['tracks'][59], {'wav': row['wav'], 'title': 'First song'})
        self.assertFalse(self.service.session._audio_edits)

    def test_new_songs_do_not_need_fixed_replacement_preparation_and_batch_is_adopted(self):
        with patch.object(self.service.audio, 'load_private_origin_inventories',
                          side_effect=AssertionError('fixed replacement preparation should not run')):
            batch = self.service.prepare_songs([self.wav])
            self.service.commit_songs(batch)
        batch.close()
        self.assertTrue(batch.directory.is_dir())
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.service.commit_songs(batch)
        self.assertTrue(batch.directory.is_dir())
        self.assertTrue(self.service.song_playback_path(batch.rows[0]['id']).is_file())

    def test_edit_remove_reorder_and_service_recreation(self):
        rows = self.service.add_songs([self.wav, self.wav])
        self.service.edit_song(rows[1]['id'], title='Second', artist='A person', move=-1)
        current = self.service.library_songs()
        self.assertEqual(current[0]['title'], 'Second')
        recipe = json.loads(Path(self.service.library_recipe_path()).read_text())
        self.assertEqual(recipe['tracks'][59]['artist'], 'A person')
        reopened = MusicService(self.service.session)
        self.assertEqual(reopened.library_songs(), current)
        self.assertEqual(reopened.library_recipe_path(), self.service.library_recipe_path())
        self.service.edit_song(rows[0]['id'], remove=True)
        self.service.edit_song(rows[1]['id'], remove=True)
        self.assertIsNone(self.service.library_recipe_path())
        self.assertEqual(self.service.library_songs(), [])

    def test_bad_later_file_cancel_stale_batch_and_publication_failure_are_atomic(self):
        bad = self.root/'broken.wav'; bad.write_bytes(b'broken')
        with self.assertRaises(ValueError):
            self.service.add_songs([self.wav, bad])
        self.assertEqual(self.service.library_songs(), [])
        self.assertFalse(list(self.service.root.glob('songs-*')))
        with self.assertRaisesRegex(ValueError, 'cancelled'):
            self.service.prepare_songs([self.wav], cancelled=lambda: True)
        batch = self.service.prepare_songs([self.wav])
        self.service.set_policy(music_unlock=True)
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.service.commit_songs(batch)
        self.assertFalse(batch.directory.exists())
        batch = self.service.prepare_songs([self.wav])
        with patch('mod_editor.studio.music_service.os.replace', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.service.commit_songs(batch)
        self.assertFalse(batch.directory.exists())
        self.assertEqual(self.service.library_songs(), [])
        self.assertFalse(list(self.service.root.glob('library-*.json')))

    def test_warnings_are_advisories_including_real_low_rate_8bit_and_low_bitrate(self):
        if not conform.conversion_available():
            self.skipTest('FFmpeg/FFprobe absent; low-quality format conversion unavailable')
        low = tone(self.root/'Low quality.wav', rate=11025, bits=8, amplitude=256)
        row = self.service.add_songs([low])[0]
        notes = row['fit']['notes']
        self.assertTrue(any('little sound detail' in n for n in notes))
        self.assertTrue(any('8-bit' in n for n in notes))
        self.assertIn(conform.QUIET_MUSIC_WARNING, notes)
        compressed = mp3(self.wav, self.root/'Tiny.mp3', '32k')
        row = self.service.add_songs([compressed])[-1]
        self.assertTrue(any('heavily compressed' in n for n in row['fit']['notes']))
        self.assertEqual(len(self.service.library_songs()), 2)

    def test_m4a_flac_ogg_convert_automatically_and_peak_protection_is_bounded(self):
        if not conform.conversion_available():
            self.skipTest('FFmpeg/FFprobe absent; M4A, FLAC and OGG conversion unavailable')
        sources = []
        for suffix in ('.m4a', '.flac', '.ogg'):
            path = self.root/('Original'+suffix)
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(self.wav), '-y', str(path)],
                           check=True, capture_output=True)
            sources.append(path)
        rows = self.service.add_songs(sources)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r['fit']['frames'] > 0 for r in rows))
        spike = self.root/'Sharp transient.wav'
        with wave.open(str(spike), 'wb') as wav:
            wav.setparams((2, 2, 22050, 1024, 'NONE', 'not compressed'))
            wav.writeframes(struct.pack('<hh', 32760, 32760)+bytes(1023*4))
        row = self.service.add_songs([spike])[-1]
        samples = conform._pcm_samples(_wav_info(Path(row['wav']).read_bytes())[3])
        self.assertLessEqual(max(abs(x) for x in samples)/32768, 10**(-1/20)+1/32768)
        self.assertLessEqual(row['fit']['gain_db'], 12)

    def test_missing_ffmpeg_one_sentence_and_limits_before_conversion(self):
        supplied = self.root/'a.mp3'; supplied.write_bytes(b'mp3')
        with patch.object(conform._convert_module(), 'ffmpeg_available', return_value=False):
            with self.assertRaisesRegex(ValueError, 'ffmpeg.org/download.html') as error:
                self.service.add_songs([supplied])
        self.assertIn(conform.FFMPEG_INSTALL, str(error.exception))
        with patch.object(self.service, 'library_reference_rms') as baseline:
            with self.assertRaisesRegex(ValueError, '200 songs'):
                self.service.add_songs([self.wav]*135)
            baseline.assert_not_called()
        # Small sparse WAV header proves duration refusal without decoding 10 minutes.
        long = self.root/'Too long.wav'
        long.write_bytes(wav_bytes(frames=1))
        with long.open('r+b') as out:
            out.seek(40); out.write(struct.pack('<I', (600*22050+1)*4))
        with self.assertRaisesRegex(ValueError, 'over 10 minutes'):
            self.service.add_songs([long])

    def test_project_roundtrip_preserves_songs_titles_order_warnings_and_encoded_result(self):
        rows = self.service.add_songs([self.wav, self.wav])
        self.service.edit_song(rows[1]['id'], title='Renamed', artist='Someone', move=-1)
        project = self.root/'songs.2k5music'
        self.service.save_project(project)
        with zipfile.ZipFile(project) as z:
            doc = json.loads(z.read('music.json'))
            self.assertEqual(doc['schema'], 'nfl2k5_music_project/v2')
            self.assertEqual(len(z.namelist()), 2)  # identical authored audio deduplicated
            self.assertNotIn(str(self.root), z.read('music.json').decode())
        # Original source file can disappear; project owns the prepared sound.
        self.wav.unlink()
        session = StudioSession(self.fixture.cache, object(), root=self.root/'sessions', session_id='reopened')
        session.attach_audio_service(self.service.audio)
        other = MusicService(session)
        self.assertEqual(other.load_project(project), 2)
        actual = other.library_songs()
        self.assertEqual([r['title'] for r in actual], ['Renamed', 'First song'])
        self.assertEqual([r['encoded_sha256'] for r in actual], [r['encoded_sha256'] for r in self.service.library_songs()])
        self.assertEqual(len(json.loads(Path(other.library_recipe_path()).read_text())['tracks']), 61)

    def test_tampered_project_and_preview_refuse_without_partial_library(self):
        row = self.service.add_songs([self.wav])[0]
        project = self.root/'music.2k5music'; self.service.save_project(project)
        before = self.service.library_songs()
        with zipfile.ZipFile(project) as z:
            members = {n: z.read(n) for n in z.namelist()}
        doc = json.loads(members['music.json']); doc['songs'][0]['encoded_sha256'] = '0'*64
        bad = self.root/'bad.2k5music'
        with zipfile.ZipFile(bad, 'w') as z:
            for name, payload in members.items():
                z.writestr(name, json.dumps(doc).encode() if name == 'music.json' else payload)
        with self.assertRaisesRegex(ValueError, 'encoder outcome'):
            self.service.load_project(bad)
        self.assertEqual(self.service.library_songs(), before)
        self.assertFalse(list(self.service.root.glob('restored-songs-*')))
        Path(row['preview']).write_bytes(wav_bytes())
        with self.assertRaisesRegex(ValueError, 'preview changed'):
            self.service.song_playback_path(row['id'])

    def test_project_fixed_and_added_songs_roll_back_together_on_session_failure(self):
        self.service.add_songs([self.wav])
        self.service.replace_batch([('cribmusic:0', self.wav)])
        project = self.root/'both.2k5music'; self.service.save_project(project)
        session = StudioSession(self.fixture.cache, object(), root=self.root/'sessions', session_id='rollback')
        session.attach_audio_service(self.service.audio)
        other = MusicService(session)
        other.add_songs([self.wav])
        before = other.library_songs(), other._library_state.read_bytes()
        with patch.object(other.session, '_write_manifest', side_effect=OSError('session full')):
            with self.assertRaisesRegex(OSError, 'session full'):
                other.load_project(project)
        self.assertEqual((other.library_songs(), other._library_state.read_bytes()), before)
        self.assertFalse(other.session._audio_edits)

    def test_generated_wav_mp3_recipe_runs_through_real_library_writer(self):
        from tests.mod_editor.test_nfl2k5_music_playlist import XBE
        from tests.mod_editor.test_nfl2k5_music_banks import fixture
        from mod_editor.core import nfl2k5_music_archive as archive
        from mod_editor.core import platform_compat
        if not XBE.is_file():
            self.skipTest('USA retail XBE absent; real metadata writer evidence unavailable')
        compressed = mp3(self.wav, self.root/'Second.mp3')
        rows = self.service.add_songs([self.wav, compressed])
        folder = self.root/'bank-fixture'; folder.mkdir()
        disc = fixture(folder)
        # Only executable evidence is read; every bank and song is generated.
        payload = XBE.read_bytes()
        with archive.Disc(disc.path) as parsed:
            partition = parsed.partition
        fd = os.open(disc.path, os.O_RDWR | getattr(os, 'O_BINARY', 0))
        try:
            archive.write_named(fd, lambda n, at: platform_compat.pread(fd, n, at), partition,
                                'default.xbe', lambda n, at: payload[at:at+n], len(payload))
        finally:
            os.close(fd)
        recipe = self.service.library_recipe_path()
        planned = banks.plan(disc.path, recipe)
        self.assertEqual(planned['count'], 61)
        output = folder/'built.iso'
        receipt = banks.rebuild(disc.path, output, recipe, expected_plan=planned)
        self.assertFalse(receipt['runtime_witnessed'])
        with archive.Disc(disc.path) as before, archive.Disc(output) as after:
            self.assertEqual(after.banks['femusic'].boundaries, before.banks['femusic'].boundaries)
            self.assertEqual(len(after.banks['cribmusic'].boundaries)-1, 61)
            for name in ('cribmusic', 'crib22'):
                old, new = before.banks[name], after.banks[name]
                for index in range(59):
                    a, b = old.boundaries[index:index+2]
                    c, d = new.boundaries[index:index+2]
                    self.assertEqual(before.read_entry_range(before.archive_entries[old.external], a, b-a),
                                     after.read_entry_range(after.archive_entries[new.external], c, d-c))
            bank = after.banks['cribmusic']
            for index, song in enumerate(rows, 59):
                a, b = bank.boundaries[index:index+2]
                data = after.read_entry_range(after.archive_entries[bank.external], a, b-a)
                self.assertEqual(sha(data), song['encoded_sha256'])
        self.assertEqual(receipt['track_sha256']['cribmusic'][59:], [r['encoded_sha256'] for r in rows])

    def test_200_total_recipe_boundary(self):
        row = {'title': 'Song', 'wav': str(self.wav)}
        self.assertEqual(len(build.song_library_recipe([row]*134)['tracks']), 193)
        with self.assertRaisesRegex(ValueError, '200 songs'):
            build.song_library_recipe([row]*135)


if __name__ == '__main__':
    unittest.main()
