"""Music organization over the shared StudioSession audio transaction owner.

This adapter owns derived caches and fit metadata only. Authoritative edits,
source originals, build-project WAVs and Undo remain in StudioSession. The
portable music project is an authored-only subset; loading it is one ordinary
session batch and preserves unrelated edits. No original audio is transported.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import ExitStack
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import re
import tempfile
import threading
import zipfile
import uuid

from mod_editor.core import audio_conform, platform_compat
from mod_editor.core.nfl2k5_audio_catalog import _wav_info, read_entry_range
from mod_editor.core.nfl2k5_ausb_fixed_slots import (
    encode_strict_pcm16_wav, verify_xbox_ima_stream, decode_xbox_ima_time_block,
)
from mod_editor.core.nfl2k5_music_catalog import MusicCatalog
from mod_editor.core.nfl2k5_music_build import (
    EncodedMusicEdit, build_copy, export_patch, song_library_recipe, encode_library_song,
)
from mod_editor.core.nfl2k5_music_policy import POLICIES
from .audio_bundle import AudioBundleRow, export_audio_bundle

SCHEMA = "nfl2k5_music_project/v1"
LIBRARY_PROJECT_SCHEMA = "nfl2k5_music_project/v2"
ENCODER = "nfl2k5_ausb_fixed_slots/pcm16-v1"
MAX_PROJECT_BYTES = 2*1024**3


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(data):
    return (json.dumps(data, sort_keys=True, indent=2, allow_nan=False)+"\n").encode()


def _fit_metadata(record, row):
    """Validate portable display data before it can enter a GUI refresh."""
    value = record.get("metadata")
    if value is None:
        return None
    required = {"row_id", "source_name", "source_sha256", "fit", "notes", "targets", "encoder"}
    if not isinstance(value, dict) or set(value) != required or value["row_id"] != row.row_id or value["encoder"] != ENCODER:
        raise ValueError("Music project fit metadata is invalid")
    if not isinstance(value["source_name"], str) or not 0 < len(value["source_name"]) <= 4096 or "\0" in value["source_name"]:
        raise ValueError("Music project source name is invalid")
    if not isinstance(value["source_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["source_sha256"]):
        raise ValueError("Music project dropped-file fingerprint is invalid")
    fit = value["fit"]
    fields = set(audio_conform.MusicConformReport.__dataclass_fields__)
    if not isinstance(fit, dict) or set(fit) != fields:
        raise ValueError("Music project fit report fields differ")
    for key in fields - {"notes", "peak_limited", "gain_capped", "match_volume"}:
        if type(fit[key]) not in (float, int) or not math.isfinite(fit[key]) or (key != "gain_db" and fit[key] < 0):
            raise ValueError("Music project fit numbers are invalid")
    if abs(fit["slot_seconds"]-row.duration_seconds) > 1e-8:
        raise ValueError("Music project fit length differs from the slot")
    for key in ("peak_limited", "gain_capped", "match_volume"):
        if type(fit[key]) is not bool:
            raise ValueError("Music project fit switches must be booleans")
    for notes in (value["notes"], fit["notes"]):
        if not isinstance(notes, list) or len(notes) > 32 or any(not isinstance(n, str) or len(n) > 2000 for n in notes):
            raise ValueError("Music project fit notes are invalid")
    if not isinstance(value["targets"], list) or len(value["targets"]) != len(record["targets"]):
        raise ValueError("Music project fit targets differ")
    for actual, expected in zip(value["targets"], record["targets"]):
        if not isinstance(actual, dict) or any(actual.get(key) != expected[key]
            for key in ("asset_id", "wav_sha256", "encoded_sha256", "original_sha256")):
            raise ValueError("Music project fit metadata belongs to other audio")
    return value


@dataclass
class PreparedMusicBatch:
    directory: Path
    token: object
    replacements: tuple
    rows: tuple
    adopted: bool = False

    def close(self):
        if not self.adopted:
            shutil.rmtree(self.directory, ignore_errors=True)


class MusicService:
    """Pass the active StudioSession, and its facade lock when sharing threads.

    Invalidate before a source/session change. Worker work carries a token and
    rejects stale delivery. Ordinary session changes invalidate pending batches.
    """

    def __init__(self, session, *, lock=None):
        if session.audio_service is None:
            raise ValueError("Open a game source to add music")
        self.session = session
        self.audio = session.audio_service
        self.catalog = MusicCatalog(self.audio.catalog)
        self.lock = lock or threading.RLock()
        self.root = (session.root/"music-cache").resolve()
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.generation = 0
        self.closed = False
        self._metadata = {}
        self._original_hashes = {}
        self._originals = {}
        self._redo = None
        self.policy = {"music_policy": "retail", "music_unlock": False, "music_userlist": False}
        self._songs = []
        self._library_recipe = None
        self.library_playlist = None
        self._reference_rms = None
        self._library_state = self.root/"songs.json"
        if self._library_state.exists():
            from mod_editor.core.json_stream import read_bounded_regular_file
            _, payload = read_bounded_regular_file(self._library_state, "Music library", maximum=1024**2)
            state = json.loads(payload)
            if state.get("source_sha256") != self.source_identity:
                raise ValueError("These songs belong to another game source; reopen the Music project.")
            self._songs = self._validate_songs(state["songs"])
            self._library_recipe = state["recipe"]
            if self._library_recipe is not None:
                self._owned_song_path(self._library_recipe)

    def _owned_song_path(self, value):
        path = Path(value)
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError("Music project contains an unsafe audio path")
        return path.resolve()

    def _validate_songs(self, rows):
        if not isinstance(rows, list) or len(rows) > 134:
            raise ValueError("The game can hold 200 songs here, including its 66.")
        seen = set()
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {"id", "title", "artist", "source_name", "wav",
                    "encoded", "preview", "wav_sha256", "encoded_sha256", "decoded_pcm_sha256", "fit"}
                    or not isinstance(row["id"], str) or not re.fullmatch(r"[0-9a-f]{32}", row["id"])
                    or row["id"] in seen):
                raise ValueError("Music project contains an invalid song")
            seen.add(row["id"])
            for key in ("wav", "encoded", "preview"):
                self._owned_song_path(row[key])
            for key in ("wav_sha256", "encoded_sha256", "decoded_pcm_sha256"):
                if not isinstance(row[key], str) or not re.fullmatch(r"[0-9a-f]{64}", row[key]):
                    raise ValueError("Music project contains an invalid song fingerprint")
            fit = row["fit"]
            if (not isinstance(fit, dict) or type(fit.get("seconds")) not in (int, float)
                    or not 0 < fit["seconds"] <= 600 or not isinstance(fit.get("notes"), list)
                    or len(fit["notes"]) > 32 or any(not isinstance(n, str) or len(n) > 2000 for n in fit["notes"])
                    or not isinstance(row["source_name"], str) or len(row["source_name"]) > 4096):
                raise ValueError("Music project contains an invalid song description")
            if (set(fit) != {"seconds", "frames", "sample_rate", "bits", "bit_rate", "input_rms", "reference_rms",
                            "gain_db", "gain_capped", "notes"}
                    or any(type(fit[k]) is not int or fit[k] < 0 for k in ("frames", "sample_rate", "bits", "bit_rate"))
                    or not 0 < fit["frames"] <= 600*22050 or abs(fit["seconds"]-fit["frames"]/22050) > 1e-9
                    or type(fit["gain_capped"]) is not bool
                    or any(type(fit[k]) not in (int, float) or not math.isfinite(fit[k])
                           for k in ("input_rms", "reference_rms", "gain_db"))):
                raise ValueError("Music project contains an invalid song fit")
        song_library_recipe(rows)
        return json.loads(json.dumps(rows))

    def library_songs(self):
        with self.lock:
            return json.loads(json.dumps(self._songs))

    def library_recipe_path(self):
        """Signal payload for the existing Build music_library field, or None."""
        return self._library_recipe

    def _publish_songs(self, rows, *, commit=None):
        """One atomic manifest publication; recipes are immutable per revision."""
        rows = self._validate_songs(rows)
        recipe = self.root/f"library-{uuid.uuid4().hex}.json" if rows else None
        temporary = self.root/f"songs-{uuid.uuid4().hex}.tmp"
        rollback = self.root/f"songs-{uuid.uuid4().hex}.rollback"
        had_state, published = self._library_state.exists(), False
        try:
            if had_state:
                shutil.copyfile(self._library_state, rollback)
            if recipe:
                recipe.write_bytes(_json(song_library_recipe(rows)))
            with temporary.open("xb") as out:
                out.write(_json(dict(source_sha256=self.source_identity, songs=rows,
                                     recipe=str(recipe) if recipe else None)))
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, self._library_state)
            published = True
            if commit:
                commit()
        except BaseException:
            if published:
                if had_state:
                    os.replace(rollback, self._library_state)
                else:
                    self._library_state.unlink(missing_ok=True)
            if recipe:
                recipe.unlink(missing_ok=True)
            raise
        finally:
            temporary.unlink(missing_ok=True)
            rollback.unlink(missing_ok=True)
        self._songs, self._library_recipe = rows, str(recipe) if recipe else None
        self.generation += 1

    def library_reference_rms(self, *, cancelled=None, progress=None):
        """Median RMS of three original game songs, independent of replacements."""
        if self._reference_rms is None:
            import statistics
            values = []
            for index in (0, 1, 2):
                target = self.catalog.get(f"cribmusic:{index}").primary
                path = self.original_path(target, cancelled=cancelled, progress=progress)
                value = audio_conform.music_rms(_wav_info(path.read_bytes())[3])
                if value > 1/32768:
                    values.append(value)
            self._reference_rms = statistics.median(values) if values else 0.0
        return self._reference_rms

    def prepare_songs(self, paths, *, cancelled=None, progress=None):
        """Stage a whole drop without exposing partially prepared songs."""
        paths, token = tuple(Path(p) for p in paths), self.token()
        self._check(token, cancelled)
        if not paths:
            raise ValueError("Choose at least one song.")
        if len(self._songs)+len(paths)+66 > 200:
            raise ValueError("The game can hold 200 songs here, including its 66; remove a song before adding more.")
        directory = Path(tempfile.mkdtemp(prefix="songs-", dir=self.root)).resolve()
        rows = []
        cancel = lambda: bool(cancelled and cancelled()) or token != self.token()
        try:
            baseline = self.library_reference_rms(cancelled=cancel, progress=progress)
            for number, supplied in enumerate(paths):
                self._check(token, cancelled)
                if not audio_conform.is_supported_suffix(supplied):
                    raise ValueError(f"{supplied.name}: choose a music file.")
                source = audio_conform._convert_module()._open_source(supplied)
                def stamp():
                    stat = source.stat()
                    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns
                before = stamp()
                snapshot = directory/("source"+source.suffix.lower())
                shutil.copyfile(source, snapshot)
                if stamp() != before:
                    raise ValueError(f"{supplied.name}: the file changed; add it again.")
                key = uuid.uuid4().hex
                wav, encoded, preview = (directory/f"{key}{suffix}" for suffix in (".wav", ".bin", "-preview.wav"))
                if progress:
                    progress(f"Adding {number+1} of {len(paths)}: {supplied.name}", number, len(paths))
                try:
                    fit = audio_conform.conform_song(snapshot, wav, reference_rms=baseline, cancelled=cancel)
                    result = encode_library_song(wav, encoded, preview, cancelled=cancel, progress=progress)
                except ValueError as exc:
                    raise ValueError(f"{supplied.name}: {exc}") from exc
                finally:
                    snapshot.unlink(missing_ok=True)
                title = "".join(c if ord(c) >= 32 else " " for c in supplied.stem).strip()[:120] or "My song"
                rows.append(dict(id=key, title=title, artist="", source_name=supplied.name,
                    wav=str(wav), encoded=str(encoded), preview=str(preview), wav_sha256=sha(wav.read_bytes()),
                    fit=fit, **result))
            self._check(token, cancelled)
            return PreparedMusicBatch(directory, token, (), tuple(rows))
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def commit_songs(self, batch, *, cancelled=None):
        try:
            with self.lock:
                self._check(batch.token, cancelled)
                for row in batch.rows:
                    self._verify_song(row, cancelled=cancelled)
                self._publish_songs(self._songs+list(batch.rows))
                batch.adopted = True
                return self.library_songs()
        except BaseException:
            batch.close()
            raise
        # Successful batch directory becomes owned library storage.

    def add_songs(self, paths, **kwargs):
        return self.commit_songs(self.prepare_songs(paths, **kwargs), cancelled=kwargs.get("cancelled"))

    def _verify_song(self, row, *, cancelled=None):
        from mod_editor.core.nfl2k5_music_archive import file_hash
        for key, digest in (("wav", "wav_sha256"), ("encoded", "encoded_sha256")):
            self._check(cancelled=cancelled)
            path = self._owned_song_path(row[key])
            if not path.is_file() or path.stat().st_size > 64*1024**2:
                raise ValueError("The prepared sound is missing or oversized; add the song again.")
            if file_hash(path) != row[digest]:
                raise ValueError(f"{row['title']}: prepared sound changed; add the song again.")
        path = self._owned_song_path(row["preview"])
        if not path.is_file() or path.stat().st_size > 64*1024**2:
            raise ValueError("The prepared preview is missing or oversized; add the song again.")
        from mod_editor.core.json_stream import read_bounded_regular_file
        _, payload = read_bounded_regular_file(path, "Song preview", maximum=64*1024**2)
        if sha(_wav_info(payload)[3]) != row["decoded_pcm_sha256"]:
            raise ValueError(f"{row['title']}: prepared preview changed; add the song again.")

    def song_playback_path(self, song_id, *, cancelled=None, progress=None):
        token = self.token()
        row = next(r for r in self.library_songs() if r["id"] == song_id)
        self._verify_song(row, cancelled=cancelled)
        self._check(token, cancelled)
        return Path(row["preview"])

    def edit_song(self, song_id, *, title=None, artist=None, move=0, remove=False):
        with self.lock:
            self._check()
            rows = self.library_songs()
            index = next(i for i, r in enumerate(rows) if r["id"] == song_id)
            row = rows.pop(index)
            if not remove:
                if title is not None:
                    row["title"] = title.strip()
                if artist is not None:
                    row["artist"] = artist.strip()
                rows.insert(max(0, min(len(rows), index+move)), row)
            self._publish_songs(rows)

    @property
    def source_identity(self):
        return self.session.cache.source.sha256

    def token(self):
        with self.lock:
            return (self.generation, self.closed, len(self.session._undo_order),
                    tuple(sorted((key, edit.replacement_sha256)
                                 for key, edit in self.session._audio_edits.items())))

    def _check(self, token=None, cancelled=None):
        if self.closed or (token is not None and token != self.token()):
            raise ValueError("Music source or session changed; repeat the operation")
        if cancelled and cancelled():
            raise ValueError("Music operation cancelled; nothing was changed")

    def invalidate(self):
        with self.lock:
            self.generation += 1
            self.closed = True
            self._redo = None

    def set_policy(self, *, music_policy="retail", music_unlock=False, music_userlist=False):
        if (music_policy not in POLICIES or type(music_unlock) is not bool or
                type(music_userlist) is not bool or (music_userlist and music_policy != "jukebox_menus")):
            raise ValueError("Select jukebox menus before replacing user playlists")
        with self.lock:
            self._check()
            self.policy = dict(music_policy=music_policy, music_unlock=music_unlock,
                               music_userlist=music_userlist)
            self.generation += 1

    def original_path(self, target, *, cancelled=None, progress=None):
        self._check(cancelled=cancelled)
        def stamp():
            return tuple((p.name, s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                         for p in self.audio.archive.packs for s in (p.path.stat(),))
        before = stamp()
        if target.asset_id in self._originals:
            path, digest, source_stamp = self._originals[target.asset_id]
            if before != source_stamp or path.is_symlink() or sha(path.read_bytes()) != digest:
                raise ValueError("Music original or source cache changed; reopen the source")
            return path
        def report(done, total):
            self._check(cancelled=cancelled)
            if progress:
                progress("Decode original music", done, total)
        path = self.audio.ensure_streaming_range_wav(target, progress=report)
        if target.asset_id not in self._original_hashes:
            entry = self.audio.archive.entries[target.external_outer_index]
            original = read_entry_range(self.audio.archive, entry, target.start, target.stored_size)
            # Authenticate all IMA headers as well as the shape on first capture.
            slot = self.audio.resolve_streaming_slot(target)
            verify_xbox_ima_stream(io.BytesIO(original), slot, cancelled=cancelled)
            self._original_hashes[target.asset_id] = sha(original)
        if stamp() != before:
            raise ValueError("Music source changed while capturing the original")
        self._originals[target.asset_id] = (path, sha(path.read_bytes()), before)
        return path

    def row_state(self, row_id):
        row = self.catalog.get(row_id)
        with self.lock:
            states = [self.session._audio_state_id(target) in self.session._audio_edits
                      for target in row.targets]
            if any(states) and not all(states):
                return "Needs attention"
            return "Replaced" if any(states) else "Original"

    def _encode(self, target, wav_path, *, cancelled=None, progress=None,
                expected_sha256=None, authorize=False):
        # The final encoder consumes this exact owned snapshot. Never reopen
        # an authorized caller WAV and silently encode different bytes.
        snapshot = self.audio.read_replacement_snapshot(target, Path(wav_path))
        payload = snapshot.wav_bytes
        key = sha(payload)
        if expected_sha256 is not None and key != expected_sha256:
            raise ValueError("Staged music changed before encoding")
        if authorize:
            issued = self.audio.authorize_replacement_snapshot(target, snapshot)
            if issued.wav_bytes is not payload:
                raise ValueError("Music authorization did not preserve its immutable snapshot")
        # Include geometry in the key; mono and stereo never share a cache.
        stem = self.root/f"{key}-{target.channels}-{target.frame_count}"
        encoded_path = stem.with_suffix(".bin")
        preview = stem.with_suffix(".wav")
        input_path = stem.with_suffix(".input.wav")
        slot = self.audio.resolve_streaming_slot(target)
        if encoded_path.exists() and preview.exists() and input_path.exists():
            with encoded_path.open("rb") as stream:
                checked = verify_xbox_ima_stream(stream, slot, cancelled=cancelled)
            if sha(_wav_info(preview.read_bytes())[3]) == checked.decoded_pcm_sha256 and sha(input_path.read_bytes()) == key:
                return input_path, encoded_path, preview, checked
            raise ValueError("Music preview cache changed; reopen the source")
        with tempfile.TemporaryDirectory(prefix="encode-", dir=self.root) as folder:
            folder = Path(folder).resolve()
            encoded = folder/"encoded.bin"
            with encoded.open("w+b") as out:
                result = encode_strict_pcm16_wav(io.BytesIO(payload), out, slot,
                    cancelled=cancelled,
                    progress=(lambda event: progress("Encode music", event.completed_blocks,
                                                      event.total_blocks)) if progress else None)
            # Preview exactly what the Xbox decoder receives, not input PCM.
            pcm = bytearray()
            with encoded.open("rb") as stream:
                for index in range(slot.block_count):
                    if index % 1024 == 0:
                        self._check(cancelled=cancelled)
                    pcm.extend(decode_xbox_ima_time_block(stream.read(36*slot.channels), slot.channels))
            if sha(pcm) != result.decoded_pcm_sha256:
                raise ValueError("Music encoded preview hash differs")
            shape = audio_conform.shape_for(slot.channels, slot.sample_rate, slot.frame_count)
            audio_conform._convert_module().write_pcm16_wav(bytes(pcm), shape, folder/"preview.wav")
            (folder/"input.wav").write_bytes(payload)
            self._check(cancelled=cancelled)
            os.replace(encoded, encoded_path)
            os.replace(folder/"preview.wav", preview)
            os.replace(folder/"input.wav", input_path)
        return input_path, encoded_path, preview, result

    def prepare_batch(self, assignments, *, match_volume=True, cancelled=None, progress=None):
        assignments = tuple(assignments)
        if not assignments or len({key for key, _ in assignments}) != len(assignments):
            raise ValueError("Music batch needs unique slot assignments")
        token = self.token()
        directory = Path(tempfile.mkdtemp(prefix="import-", dir=self.root)).resolve()
        replacements, rows = [], []
        try:
            for number, (row_id, source) in enumerate(assignments):
                self._check(token, cancelled)
                row = self.catalog.get(row_id)
                if not audio_conform.is_supported_suffix(source):
                    raise ValueError(f"Unsupported audio file: {Path(source).name}")
                # Snapshot before conversion, so edits to the dropped file cannot
                # race fit/encode/authorization or mislabel the recorded input.
                from mod_editor.core.json_stream import read_bounded_regular_file
                _source, source_bytes = read_bounded_regular_file(Path(source), "Dropped music",
                    maximum=512*1024**2)
                snapshot = directory/f"source-{number}{Path(source).suffix.lower()}"
                snapshot.write_bytes(source_bytes)
                original = _wav_info(self.original_path(row.primary, cancelled=cancelled, progress=progress).read_bytes())[3]
                shape = audio_conform.shape_for(row.primary.channels, 22050, row.primary.frame_count)
                pcm, fit = audio_conform.conform_music(snapshot, shape, original,
                    match_volume=match_volume, cancelled=lambda: bool(cancelled and cancelled()) or token != self.token())
                notes, targets = list(fit.notes), []
                for target in row.targets:
                    self._check(token, cancelled)
                    self.original_path(target, cancelled=cancelled, progress=progress)
                    target_pcm = pcm
                    if target is row.twin:
                        target_pcm, cancellation = audio_conform.music_downmix(pcm)
                        if cancellation:
                            notes.append("The mono stadium version is nearly silent because the stereo channels cancel.")
                    target_shape = audio_conform.shape_for(target.channels, 22050, target.frame_count)
                    wav = directory/f"{number}-{target.channels}.wav"
                    audio_conform._convert_module().write_pcm16_wav(target_pcm, target_shape, wav)
                    input_path, encoded_path, preview, encoded = self._encode(target, wav,
                        cancelled=cancelled, progress=progress)
                    replacements.append((target, input_path))
                    targets.append({"asset_id": target.asset_id, "stream_id": f"{target.bank.name}:{target.range_index}",
                        "wav_sha256": sha(input_path.read_bytes()), "encoded_sha256": encoded.encoded_sha256,
                        "original_sha256": self._original_hashes[target.asset_id],
                        "decoded_pcm_sha256": encoded.decoded_pcm_sha256})
                fit_document = asdict(fit)
                fit_document["notes"] = list(fit.notes)
                rows.append({"row_id": row_id, "source_name": Path(source).name,
                             "source_sha256": sha(source_bytes), "fit": fit_document,
                             "notes": notes, "targets": targets, "encoder": ENCODER})
                if progress:
                    progress("Prepare music", number+1, len(assignments))
            self._check(token, cancelled)
            # The same source-containment authorization used by Audio Cues.
            self.session.preflight_audio_batch(replacements)
            self._check(token, cancelled)
            return PreparedMusicBatch(directory, token, tuple(replacements), tuple(rows))
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def commit_batch(self, batch, *, cancelled=None):
        try:
            with self.lock:
                self._check(batch.token, cancelled)
                result = self.session.replace_audio_batch(batch.replacements, label="Replace music and linked stadium versions")
                for row in batch.rows:
                    self._metadata[tuple(t["wav_sha256"] for t in row["targets"])] = row
                self._redo = None
                return result
        finally:
            batch.close()

    def replace_batch(self, assignments, **kwargs):
        batch = self.prepare_batch(assignments, **kwargs)
        return self.commit_batch(batch, cancelled=kwargs.get("cancelled"))

    def restore(self, row_id):
        row = self.catalog.get(row_id)
        paths = [(target, self.original_path(target)) for target in row.targets]
        with self.lock:
            self._check()
            if self.row_state(row_id) == "Original":
                return None
            self._redo = None
            return self.session.replace_audio_batch(paths, label="Restore original music and stadium version")

    def undo(self):
        # Save only authored/current input copies for a local Redo. The shared
        # session remains the sole Undo owner; other tab actions are visible.
        with self.lock:
            self._check()
            if not self.session._undo_order or self.session._undo_order[-1].source != "audio":
                self._redo = None
                return self.session.undo()
            action = self.session._audio_undo[-1]
            music_ids = {t.asset_id: t for r in self.catalog.rows for t in r.targets}
            selected = []
            for item in action.items:
                target = music_ids.get(item.asset_id) or music_ids.get(getattr(item, "logical_asset_id", None))
                if target is None:
                    self._redo = None
                    return self.session.undo()
                path = self.session.current_audio_path(target)
                cached = self.root/f"redo-{sha(path.read_bytes())}.wav"
                if not cached.exists():
                    cached.write_bytes(path.read_bytes())
                selected.append((target, cached))
            result = self.session.undo()
            self._redo = (self.token(), tuple(selected))
            return result

    def redo(self):
        with self.lock:
            if self._redo is None:
                return None
            token, replacements = self._redo
            self._check(token)
            result = self.session.replace_audio_batch(replacements, label="Redo music")
            self._redo = None
            return result

    def metadata(self, row_id):
        row = self.catalog.get(row_id)
        if self.row_state(row_id) == "Original":
            return None
        # Rendering must never decode/authorize audio on the GUI thread.
        keys = tuple(self.session._audio_edits[self.session._audio_state_id(t)].replacement_sha256
                     if self.session._audio_state_id(t) in self.session._audio_edits else ""
                     for t in row.targets)
        return self._metadata.get(keys)

    def playback_path(self, row_id, *, original=False, mono=False, cancelled=None, progress=None):
        row = self.catalog.get(row_id)
        target = row.twin if mono and row.twin else row.primary
        token = self.token()
        if original or self.session.audio_content_origin(target) != "user_replacement":
            result = self.original_path(target, cancelled=cancelled, progress=progress)
        else:
            path = self.session.current_audio_path(target)
            expected = self.session._audio_edits[self.session._audio_state_id(target)].replacement_sha256
            result = self._encode(target, path, cancelled=cancelled, progress=progress,
                                  expected_sha256=expected, authorize=True)[2]
        self._check(token, cancelled)
        return result

    def export_wav(self, row_id, destination, *, original=False, mono=False, cancelled=None, progress=None):
        token = self.token()
        source = self.playback_path(row_id, original=original, mono=mono, cancelled=cancelled, progress=progress)
        destination = Path(destination).expanduser().absolute().resolve()
        with tempfile.TemporaryDirectory(prefix=".music-export-", dir=destination.parent) as folder:
            stage = Path(folder).resolve()/"audio.wav"
            shutil.copyfile(source, stage)
            self._check(token, cancelled)
            platform_compat.publish_no_replace(stage, destination)
        return destination

    def export_set(self, destination, row_ids, *, cancelled=None, progress=None):
        token = self.token()
        rows = []
        for row_id in row_ids:
            row = self.catalog.get(row_id)
            rows.append(AudioBundleRow(row_id, row.display_name, row.title, ".wav",
                44+row.primary.frame_count*row.primary.channels*2,
                self.session.audio_content_origin(row.primary),
                {"duration_seconds": row.duration_seconds, "context": row.context,
                 "linked_mono": row.twin is not None, "runtime_witnessed": False}))
        def write(row, path):
            self._check(token, cancelled)
            return self.export_wav(row.stable_id, path, cancelled=cancelled, progress=progress)
        return export_audio_bundle(rows, Path(destination), bundle_name="Current music",
            payload_writer=write, progress=lambda done,total: self._check(token, cancelled))

    def encoded_edits(self, *, cancelled=None, progress=None):
        token = self.token()
        edits = []
        for row in self.catalog.rows:
            state = self.row_state(row.row_id)
            if state == "Needs attention":
                raise ValueError(f"{row.title}: only one jukebox version changed. Replace or Restore this row first.")
            if state == "Original":
                continue
            for target in row.targets:
                self._check(token, cancelled)
                self.original_path(target, cancelled=cancelled, progress=progress)
                current = self.session.current_audio_path(target)
                expected = self.session._audio_edits[self.session._audio_state_id(target)].replacement_sha256
                _input, encoded, _preview, result = self._encode(target, current, cancelled=cancelled,
                    progress=progress, expected_sha256=expected, authorize=True)
                edits.append(EncodedMusicEdit(f"{target.bank.name}:{target.range_index}", encoded,
                    result.encoded_sha256, self._original_hashes[target.asset_id]))
        self._check(token, cancelled)
        return tuple(edits)

    def build_copy(self, source, destination, *, cancelled=None, progress=None):
        token = self.token()
        edits = self.encoded_edits(cancelled=cancelled, progress=progress)
        if self._songs:
            from mod_editor.core import nfl2k5_music_banks as banks
            songs = self.library_songs()
            for song in songs:
                self._verify_song(song, cancelled=cancelled)
            recipe = song_library_recipe(songs)
            destination = Path(destination).resolve()
            if destination.exists():
                raise ValueError("Music output already exists; choose a new copy")
            def report(stage, done, total):
                self._check(token, cancelled)
                if progress:
                    progress(stage, done, total)
            with tempfile.TemporaryDirectory(prefix=".songs-build-", dir=destination.parent) as directory:
                directory = Path(directory).resolve()
                fixed = directory/"fixed.iso"
                fixed_receipt = build_copy(source, fixed, edits, progress=report,
                    cancelled=lambda: bool(cancelled and cancelled()) or self.token() != token, **self.policy)
                result = directory/"songs.iso"
                receipt = banks.rebuild(fixed, result, recipe, progress=report)
                self._check(token, cancelled)
                platform_compat.publish_no_replace(result, destination)
            receipt.update(output=str(destination), fixed_music=fixed_receipt)
            return receipt
        return build_copy(source, destination, edits, progress=progress,
            cancelled=lambda: bool(cancelled and cancelled()) or self.token() != token, **self.policy)

    def export_patch(self, source, destination, *, cancelled=None, progress=None):
        if self._songs:
            raise ValueError("To share added songs, save a Music project or export your finished build from Build & Share.")
        token = self.token()
        edits = self.encoded_edits(cancelled=cancelled, progress=progress)
        cancel = lambda: bool(cancelled and cancelled()) or self.token() != token
        with tempfile.TemporaryDirectory(prefix="music-patch-", dir=self.root) as folder:
            built = Path(folder).resolve()/"music.iso"
            build_copy(source, built, edits, cancelled=cancel, progress=progress, **self.policy)
            return export_patch(source, built, destination, edits, cancelled=cancel,
                                progress=progress, **self.policy)

    def save_project(self, destination, *, cancelled=None, progress=None, playlist_options=None):
        """Music subset: exact authored PCM/encoded hashes plus source identity.

        Originals are recovered from the recipient's verified selected source.
        The fixed encoder is reproduced and checked on import, so no binary
        encoded copy needs to be duplicated in the portable project.
        """
        token, rows = self.token(), []
        from mod_editor.core import nfl2k5_music_playlist as playlist
        choices = playlist.copy_options(playlist_options if playlist_options is not None else self.library_playlist)
        destination = Path(destination).expanduser().absolute().resolve()
        with tempfile.TemporaryDirectory(prefix=".music-project-", dir=destination.parent) as folder:
            stage = Path(folder).resolve()/"project.zip"
            with zipfile.ZipFile(stage, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for row in self.catalog.rows:
                    state = self.row_state(row.row_id)
                    if state == "Needs attention":
                        raise ValueError(f"{row.title}: restore or replace both versions before saving")
                    if state == "Original":
                        continue
                    targets = []
                    for target in row.targets:
                        self._check(token, cancelled)
                        self.original_path(target, cancelled=cancelled, progress=progress)
                        # Authorization is rechecked by current_audio_path.
                        current = self.session.current_audio_path(target)
                        expected = self.session._audio_edits[self.session._audio_state_id(target)].replacement_sha256
                        path, _encoded, _preview, result = self._encode(target, current, cancelled=cancelled,
                            progress=progress, expected_sha256=expected, authorize=True)
                        snapshot = self.audio.read_replacement_snapshot(target, path)
                        if snapshot.metadata.wav_sha256 != expected:
                            raise ValueError("Music changed before project export")
                        issued = self.audio.authorize_replacement_snapshot(target, snapshot)
                        member = f"audio/{issued.wav_sha256}.wav"
                        if member not in archive.namelist():
                            archive.writestr(member, issued.wav_bytes)
                        targets.append({"asset_id": target.asset_id, "member": member,
                            "wav_sha256": issued.wav_sha256, "encoded_sha256": result.encoded_sha256,
                            "original_sha256": self._original_hashes[target.asset_id]})
                    rows.append({"row_id": row.row_id, "targets": targets,
                                 "metadata": self.metadata(row.row_id)})
                document = {"schema": SCHEMA, "encoder": ENCODER,
                    "source_sha256": self.source_identity, "policy": self.policy, "rows": rows}
                if self._songs or choices is not None:
                    songs = []
                    for row in self.library_songs():
                        self._check(token, cancelled)
                        self._verify_song(row, cancelled=cancelled)
                        member = f"songs/{row['wav_sha256']}.wav"
                        if member not in archive.namelist():
                            from mod_editor.core.json_stream import read_bounded_regular_file
                            _, payload = read_bounded_regular_file(Path(row["wav"]), "Prepared song", maximum=44+600*22050*4)
                            if sha(payload) != row["wav_sha256"]:
                                raise ValueError("The prepared song changed before project export")
                            archive.writestr(member, payload)
                        songs.append({k: v for k, v in row.items() if k not in ("wav", "encoded", "preview")})
                    document.update(schema=LIBRARY_PROJECT_SCHEMA, songs=songs, playlist=choices)
                if sum(i.file_size for i in archive.infolist()) > MAX_PROJECT_BYTES-1024**2:
                    raise ValueError("This Music project exceeds the portable project size limit.")
                archive.writestr("music.json", _json(document))
            self._check(token, cancelled)
            platform_compat.publish_no_replace(stage, destination)
        return destination

    def load_project(self, source, *, cancelled=None, progress=None):
        token, replacements, metadata = self.token(), [], []
        with tempfile.TemporaryDirectory(prefix="project-", dir=self.root) as folder, ExitStack() as cleanup:
            folder = Path(folder).resolve()
            with zipfile.ZipFile(source, "r") as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if (len(names) != len(set(names)) or len(names) > 280 or
                    sum(i.file_size for i in infos) > MAX_PROJECT_BYTES or "music.json" not in names or
                    archive.getinfo("music.json").file_size > 1024**2):
                    raise ValueError("Music project is duplicated, oversized or lacks its manifest")
                document = json.loads(archive.read("music.json"))
                version = document.get("schema") if isinstance(document, dict) else None
                fields = {"schema", "encoder", "source_sha256", "policy", "rows"}
                if version == LIBRARY_PROJECT_SCHEMA:
                    fields |= {"songs", "playlist"}
                if (not isinstance(document, dict) or set(document) != fields or
                        version not in (SCHEMA, LIBRARY_PROJECT_SCHEMA) or document.get("encoder") != ENCODER or
                        document.get("source_sha256") != self.source_identity):
                    raise ValueError("Music project needs its original source and supported encoder")
                policy = document["policy"]
                if (not isinstance(policy, dict) or set(policy) != set(self.policy) or policy["music_policy"] not in POLICIES or
                    type(policy["music_unlock"]) is not bool or type(policy["music_userlist"]) is not bool or
                    (policy["music_userlist"] and policy["music_policy"] != "jukebox_menus")):
                    raise ValueError("Music project policy is invalid")
                used, seen = {"music.json"}, set()
                songs, choices = [], None
                if version == LIBRARY_PROJECT_SCHEMA:
                    from mod_editor.core import nfl2k5_music_playlist as playlist
                    choices = playlist.copy_options(document["playlist"])
                    records = document["songs"]
                    if not isinstance(records, list) or len(records) > 134:
                        raise ValueError("Music project contains too many songs")
                    song_dir = Path(tempfile.mkdtemp(prefix="restored-songs-", dir=self.root)).resolve()
                    cleanup.callback(shutil.rmtree, song_dir, ignore_errors=True)
                    for number, record in enumerate(records):
                        self._check(token, cancelled)
                        if not isinstance(record, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("wav_sha256", ""))):
                            raise ValueError("Music project contains an invalid song fingerprint")
                        member = f"songs/{record['wav_sha256']}.wav"
                        if not 44 < archive.getinfo(member).file_size <= 44+600*22050*4:
                            raise ValueError("Music project song is empty or over 10 minutes")
                        wav, encoded, preview = (song_dir/f"{number}{suffix}" for suffix in (".wav", ".bin", "-preview.wav"))
                        with archive.open(member) as incoming, wav.open("xb") as out:
                            shutil.copyfileobj(incoming, out, 1024*1024)
                        if sha(wav.read_bytes()) != record["wav_sha256"]:
                            raise ValueError("Music project song fingerprint differs")
                        import wave
                        with wave.open(str(wav)) as reader:
                            if record.get("fit", {}).get("frames") != reader.getnframes():
                                raise ValueError("Music project song length differs")
                        result = encode_library_song(wav, encoded, preview, cancelled=cancelled, progress=progress)
                        if any(record.get(k) != v for k, v in result.items()):
                            raise ValueError("Music project song encoder outcome differs")
                        songs.append(dict(record, wav=str(wav), encoded=str(encoded), preview=str(preview)))
                        used.add(member)
                    self._validate_songs(songs)
                if not isinstance(document["rows"], list) or len(document["rows"]) > 86:
                    raise ValueError("Music project rows must be a bounded list")
                for record in document["rows"]:
                    if not isinstance(record, dict) or set(record) != {"row_id", "targets", "metadata"} or not isinstance(record["targets"], list):
                        raise ValueError("Music project row is invalid")
                    row = self.catalog.get(record["row_id"])
                    if row.row_id in seen or [t["asset_id"] for t in record["targets"]] != [t.asset_id for t in row.targets]:
                        raise ValueError("Music project has duplicated rows or a missing/wrong twin")
                    seen.add(row.row_id)
                    fit_metadata = _fit_metadata(record, row)
                    for target, value in zip(row.targets, record["targets"]):
                        self._check(token, cancelled)
                        self.original_path(target, cancelled=cancelled, progress=progress)
                        if value["original_sha256"] != self._original_hashes[target.asset_id]:
                            raise ValueError("Music project original slot fingerprint differs")
                        member = f"audio/{value['wav_sha256']}.wav"
                        if value["member"] != member or len(value["wav_sha256"]) != 64:
                            raise ValueError("Unsafe music asset path")
                        if archive.getinfo(member).file_size != 44+target.frame_count*target.channels*2:
                            raise ValueError("Music project WAV length differs from its slot")
                        payload = archive.read(member)
                        if sha(payload) != value["wav_sha256"]:
                            raise ValueError("Music project authored WAV hash differs")
                        path = folder/f"{len(replacements)}.wav"
                        path.write_bytes(payload)
                        current, _encoded, _preview, result = self._encode(target, path, cancelled=cancelled,
                            progress=progress, expected_sha256=value["wav_sha256"], authorize=True)
                        if result.encoded_sha256 != value["encoded_sha256"]:
                            raise ValueError("Music project encoder outcome differs")
                        replacements.append((target, current))
                        used.add(member)
                    if fit_metadata is not None:
                        metadata.append(fit_metadata)
                if used != set(names):
                    raise ValueError("Music project contains unreferenced assets")
            # Music projects replace the music subset, including explicit source
            # restoration for rows absent from the project. Other tabs survive.
            for row in self.catalog.rows:
                if row.row_id not in seen and self.row_state(row.row_id) != "Original":
                    replacements.extend((t, self.original_path(t)) for t in row.targets)
            with self.lock:
                self._check(token, cancelled)
                changed = [(t,p) for t,p in replacements
                           if p.read_bytes() != self.session.current_audio_path(t).read_bytes()]
                self._publish_songs(songs, commit=(lambda: self.session.replace_audio_batch(
                    replacements, label="Open music project")) if changed else None)
                self.policy = dict(policy)
                self.library_playlist = choices
                self.generation += 1
                for value in metadata:
                    self._metadata[tuple(t["wav_sha256"] for t in value["targets"])] = value
                self._redo = None
                cleanup.pop_all()  # The validated song files now belong to this session.
        return len(seen)+len(songs)
