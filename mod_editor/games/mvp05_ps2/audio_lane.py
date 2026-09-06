"""Audio: the EA ``SCHl`` streams played, exported and replaced; the ``BNKl`` banks exported.

MVP Baseball 2005's audio is loose ISO9660 files under ``/DATA/AUDIO`` [M]:
31 bare ``SCHl`` files -- six ``*DAT.BIG`` that are streams rather than
archives, 14 ``.AST`` crowd and heckle beds, 9 ``.ASF`` menu tracks, plus the
two MicroTalk commentary containers ``PADAT.BIG`` and ``PBPDAT.BIG`` -- five
EA ``BIG`` archives of 9,123 MicroTalk speech entries, and two ``BNKl`` banks.

* EA-XA ADPCM (codec 10) decodes and encodes through the shared
  :mod:`mod_editor.games._formats.ea_schl`, proved on Madden NFL 09.
* MicroTalk (codec 4) is listed with its rate, channels and length and refused
  by name; no decoder for it exists that this project could check against.

The bare files are whole ISO9660 files, so a replacement needs no archive
writer at all: the stream is re-encoded to its own rate and channel count, must
fit the bytes it already occupies, is zero-padded to them, and the file goes
back inside its own extent.  **Evidence tags.**  **[M]** measured on the disc.
"""

from __future__ import annotations

import argparse
import json
import mmap
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_big, ea_schl
from mod_editor.games.contract import (
    Artifact, Catalogue, Edit, Field, Plan, Receipt, Refusal, Target, Verdict, require,
)

from . import containers, disc_write

MAX_TARGETS = 4000
WAV_SUFFIX = ".wav"
#: The lowest signal-to-noise a re-decoded replacement may show against the WAV
#: it was made from.  EA-XA is 4-bit ADPCM; a faithful encode lands well above.
MIN_SNR_DB = 12.0


class _DiscAudio:
    """The image memory-mapped read-only, with the audio files located."""

    def __init__(self, source: Path) -> None:
        self.disc = containers.Disc(Path(source))
        self._handle = open(self.disc.path, "rb")
        self.view = mmap.mmap(self._handle.fileno(), 0, access=mmap.ACCESS_READ)

    def close(self) -> None:
        try:
            self.view.close()
        finally:
            self._handle.close()
            self.disc.close()

    def __enter__(self) -> "_DiscAudio":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def span(self, entry: Any) -> Tuple[int, int]:
        start = self.disc.offset_of(entry)
        return start, start + int(entry.length)

    def bare_files(self) -> List[Any]:
        out = []
        for entry in self.disc.audio_files():
            if int(entry.length) >= 16 and self.disc.head(entry, 4) == ea_schl.SCHL_MAGIC:
                out.append(entry)
        return sorted(out, key=lambda e: e.path)

    def archives(self) -> List[Any]:
        out = []
        for entry in self.disc.audio_files():
            if entry.path.upper().endswith(".BIG") and self.disc.is_big(entry):
                out.append(entry)
        return sorted(out, key=lambda e: e.path)

    def banks(self) -> List[Any]:
        out = []
        for entry in self.disc.audio_files():
            if int(entry.length) >= 16 and self.disc.head(entry, 4) == ea_schl.BNKL_MAGIC:
                out.append(entry)
        return sorted(out, key=lambda e: e.path)

    def find(self, path: str) -> Any:
        return self.disc.find(path)


def parse_key(key: str) -> Tuple[str, str, int]:
    """``(path, kind, index)``: ``<path>:<stream>`` for a bare file, ``<path>!<entry>`` for an archive."""
    match = re.match(r"^(/.+?)([:!])(\d+)$", str(key))
    if match is None:
        raise Refusal(f"{key!r} does not name a sound: a key is <path>:<stream> or "
                      f"<path>!<entry>, as the catalogue writes it.")
    return match.group(1), ("stream" if match.group(2) == ":" else "entry"), int(match.group(3))


def _duration(rate: Optional[int], samples: int) -> str:
    if not rate:
        return "rate not declared"
    seconds = samples / float(rate)
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def encoded_size(samples: int, channels: int, block_samples: int, version: Optional[int]) -> int:
    """Bytes a stream of *samples* occupies once encoded -- arithmetic, not a trial encode."""
    total = 0
    preamble = 4 if version == ea_schl.EAXA_VERSION_PER_BLOCK_STATE else 0
    left = samples - samples % ea_schl.EAXA_SAMPLES_PER_FRAME
    while left > 0:
        count = min(block_samples, left)
        count -= count % ea_schl.EAXA_SAMPLES_PER_FRAME
        if count == 0:
            break
        frames = count // ea_schl.EAXA_SAMPLES_PER_FRAME
        run = preamble + frames * ea_schl.EAXA_FRAME_BYTES
        run += run % 2
        total += ea_schl.CHUNK_HEADER_SIZE + 4 + 4 * channels + channels * run
        left -= count
    return total + 40 + 12 + 8


class AudioStreamsLane:
    """Every ``SCHl`` stream: play and export what decodes, replace it in a bare file."""

    lane_id = "audio.streams"
    capability_id = "mvp05ps2.audio.streams"
    surface = "audio"
    page = "audio"
    title = "Music, crowd, effects and commentary streams"
    classification = "offline-writer-proved"
    recipe_schema = "mvp05_ps2_audio_streams_recipe/v1"
    catalogue_schema = "mvp05_ps2_audio_streams_catalogue/v1"
    write_schema = "mvp05_ps2_audio_streams_write/v1"
    validators = ("tools/validate_mvp05_ps2_audio.sh", "tools/validate_mvp05_ps2_audio.bat")
    fixed_allocation = True

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        targets: List[Target] = []
        files: List[Dict[str, Any]] = []
        refusals: List[Dict[str, str]] = []
        totals = {"bare_files": 0, "streams": 0, "decodable": 0, "archives": 0, "entries": 0}
        codecs: Dict[str, int] = {}
        with _DiscAudio(Path(source)) as disc:
            for entry in disc.bare_files():
                if progress is not None:
                    progress(f"{entry.path}…")
                start, end = disc.span(entry)
                try:
                    streams = ea_schl.iter_streams(disc.view, start, end)
                except ea_schl.SchlError as exc:
                    refusals.append({"where": entry.path, "sentence": str(exc)})
                    continue
                summary = {"path": entry.path, "bytes": int(entry.length), "streams": len(streams),
                           "decodable": 0, "listed": 0, "kind": "bare"}
                totals["bare_files"] += 1
                for stream in streams:
                    header = stream.header
                    codecs[header.codec_name] = codecs.get(header.codec_name, 0) + 1
                    totals["streams"] += 1
                    decodable = header.decodable and bool(header.sample_rate) and stream.complete
                    if decodable:
                        summary["decodable"] += 1
                        totals["decodable"] += 1
                    row = {"path": entry.path, "kind": "stream", "index": stream.index,
                           "offset": stream.offset - start, "length": stream.length,
                           "codec": header.codec, "codec_name": header.codec_name,
                           "channels": header.channels, "sample_rate": header.sample_rate,
                           "samples": header.sample_count, "blocks": len(stream.blocks),
                           "version": header.version, "big_endian": header.big_endian,
                           "complete": stream.complete, "decodable": decodable,
                           "writable": decodable, "duration": _duration(header.sample_rate, header.sample_count)}
                    if len(targets) < MAX_TARGETS:
                        targets.append(self._target(row))
                        summary["listed"] += 1
                files.append(summary)
            for entry in disc.archives():
                if progress is not None:
                    progress(f"{entry.path}…")
                try:
                    archive = disc.disc.archive(entry)
                except containers.DiscError as exc:
                    refusals.append({"where": entry.path, "sentence": str(exc)})
                    continue
                summary = {"path": entry.path, "bytes": int(entry.length), "streams": 0,
                           "decodable": 0, "listed": 0, "kind": "archive", "entries": len(archive)}
                totals["archives"] += 1
                base = disc.disc.offset_of(entry)
                for row_entry in archive.entries:
                    if row_entry.size < 16 or archive.is_compressed(row_entry.index):
                        continue
                    head = disc.view[base + row_entry.offset:base + row_entry.offset + 4]
                    if bytes(head) != ea_schl.SCHL_MAGIC:
                        continue
                    try:
                        header = ea_schl.parse_stream_header(disc.view, base + row_entry.offset,
                                                             base + row_entry.end)
                    except ea_schl.SchlError as exc:
                        refusals.append({"where": f"{entry.path}!{row_entry.name}", "sentence": str(exc)})
                        continue
                    codecs[header.codec_name] = codecs.get(header.codec_name, 0) + 1
                    totals["entries"] += 1
                    summary["streams"] += 1
                    decodable = header.decodable and bool(header.sample_rate)
                    if decodable:
                        summary["decodable"] += 1
                    row = {"path": entry.path, "kind": "entry", "index": row_entry.index,
                           "entry_name": row_entry.name, "offset": row_entry.offset,
                           "length": row_entry.size, "codec": header.codec,
                           "codec_name": header.codec_name, "channels": header.channels,
                           "sample_rate": header.sample_rate, "samples": header.sample_count,
                           "version": header.version, "big_endian": header.big_endian,
                           "decodable": decodable, "writable": False,
                           "duration": _duration(header.sample_rate, header.sample_count)}
                    if len(targets) < MAX_TARGETS:
                        targets.append(self._target(row))
                        summary["listed"] += 1
                files.append(summary)
        document = {"schema": self.catalogue_schema, "source": str(source), "files": files,
                    **totals, "codecs": codecs, "targets_listed": len(targets),
                    "targets_cap": MAX_TARGETS, "refusals": refusals,
                    "speech_refusal": ea_schl.SPEECH_REFUSAL, "runtime_note": disc_write.NOT_BOOTED,
                    "note": "Directory only: offsets, lengths, rates, channels and codecs. Audio is "
                            "decoded when you play or export a sound."}
        return Catalogue(self.catalogue_schema, self.lane_id, str(source), tuple(targets), document)

    @staticmethod
    def _key(row: Mapping[str, Any]) -> str:
        return f"{row['path']}{':' if row['kind'] == 'stream' else '!'}{row['index']}"

    def _target(self, row: Mapping[str, Any]) -> Target:
        name = row["path"].rsplit("/", 1)[-1]
        label = f"{name} · {'stream' if row['kind'] == 'stream' else 'entry'} {row['index']}"
        if row.get("entry_name"):
            label = f"{name}!{row['entry_name']}"
        detail = [row["duration"], f"{row['sample_rate']:,} Hz" if row["sample_rate"] else "rate not declared",
                  "stereo" if row["channels"] == 2 else ("mono" if row["channels"] == 1 else f"{row['channels']} ch"),
                  row["codec_name"], f"{row['length']:,} bytes"]
        if row["writable"]:
            fields: Tuple[Field, ...] = (
                Field("wav", "wav", "Replacement WAV",
                      "An uncompressed WAV; it is mixed to this sound's channels, resampled to its "
                      "rate, encoded as EA-XA and must fit the bytes the sound already occupies."),)
            budget = f"A replacement must encode to at most {row['length']:,} bytes; the file keeps its length."
        elif row["decodable"]:
            fields = (Field("writer", "note", "Why there is no replace",
                            "This stream sits inside an EA BIG archive; export it, the writer here "
                            "replaces the bare stream files only.", read_only=True),)
            budget = "Export only for an archived stream."
        else:
            fields = (Field("codec", "note", "Why there is no play or export",
                            ea_schl.SPEECH_REFUSAL if row["codec"] == ea_schl.CODEC_SPEECH
                            else f"codec {row['codec']} is not decoded here", read_only=True),)
            budget = "Listed and refused by name."
        return Target(key=self._key(row), label=label, detail=" · ".join(detail), budget=budget,
                      searchable=f"{row['path']} {row.get('entry_name', '')} {row['codec_name']} {row['sample_rate']}",
                      raw=dict(row), fields=fields)

    # -- reading ----------------------------------------------------------------

    def _locate(self, disc: _DiscAudio, path: str, kind: str, index: int
                ) -> Tuple[int, int, ea_schl.Stream]:
        entry = disc.find(path)
        start, end = disc.span(entry)
        if kind == "stream":
            streams = ea_schl.iter_streams(disc.view, start, end)
            require(0 <= index < len(streams),
                    f"{path} holds {len(streams)} stream(s), so there is no stream {index}.")
            return start, end, streams[index]
        archive = disc.disc.archive(entry)
        row = archive.entry(index)
        base = start + row.offset
        streams = ea_schl.iter_streams(disc.view, base, base + row.size)
        require(bool(streams), f"{path}!{index} holds no SCHl stream.")
        return base, base + row.size, streams[0]

    def decode_wav(self, source: Path, target: Target) -> bytes:
        return self.decode_wav_by_key(Path(source), target.key)

    def decode_wav_by_key(self, source: Path, key: str) -> bytes:
        path, kind, index = parse_key(key)
        with _DiscAudio(Path(source)) as disc:
            _start, _end, stream = self._locate(disc, path, kind, index)
            header = stream.header
            if header.codec == ea_schl.CODEC_SPEECH:
                raise Refusal(f"{key}: {ea_schl.SPEECH_REFUSAL}")
            require(header.decodable, f"{key}: this sound declares codec {header.codec}, which is not decoded here.")
            require(bool(header.sample_rate), f"{key}: this sound's header declares no sample rate.")
            pcm = ea_schl.decode_eaxa(disc.view, stream.blocks, header.channels, header.big_endian,
                                      header.version)
            return ea_schl.wav_bytes(pcm, int(header.sample_rate), header.channels)

    # -- the edit rule ----------------------------------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - {"wav"})
        if unknown:
            return (f"{target.key}: {', '.join(unknown)} is not something this lane takes; give a "
                    f"WAV, or nothing at all to export this sound as it is.")
        path = values.get("wav")
        if path in (None, ""):
            if not target.raw.get("decodable"):
                return f"{target.key}: {ea_schl.SPEECH_REFUSAL}"
            return None
        if not target.raw.get("writable"):
            if not target.raw.get("decodable"):
                return f"{target.key}: this sound cannot be replaced because it cannot be read: {ea_schl.SPEECH_REFUSAL}"
            return f"{target.key}: this stream sits inside an archive; the writer replaces bare stream files only."
        try:
            payload = Path(str(path)).read_bytes()
        except OSError as exc:
            return f"{target.key}: {path} could not be read ({exc}); choose a WAV file."
        try:
            rate, channels, pcm = ea_schl.read_wav(payload)
        except (Refusal, ea_schl.SchlError) as exc:
            return f"{target.key}: {exc}"
        wanted_rate = int(target.raw.get("sample_rate") or 0)
        wanted_channels = int(target.raw.get("channels") or 1)
        samples = len(pcm) // (2 * channels)
        resampled = samples * wanted_rate // max(1, rate)
        size = encoded_size(resampled, wanted_channels, ea_schl.DEFAULT_BLOCK_SAMPLES,
                            target.raw.get("version"))
        limit = int(target.raw.get("length") or 0)
        if size > limit:
            return (f"{target.key}: that WAV encodes to about {size:,} bytes and this sound has "
                    f"{limit:,} to give; trim it by roughly {(size - limit) / max(1, size) * 100:.0f}%.")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: Dict[str, Any] = {"sound": edit.target_key, "wav": str(edit.values.get("wav", ""))}
            if edit.note:
                row["note"] = edit.note
            rows.append(row)
        return {"schema": self.recipe_schema, "sounds": rows}

    def _entries(self, recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == self.recipe_schema,
                f"recipe schema is {recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, "
                f"expected {self.recipe_schema}")
        rows = recipe.get("sounds")
        require(isinstance(rows, list) and rows,
                "a recipe must carry a non-empty 'sounds' list; choose at least one sound")
        out = []
        seen = set()
        for number, row in enumerate(rows):
            require(isinstance(row, Mapping) and isinstance(row.get("sound"), str),
                    f"sound {number} must name the sound it replaces")
            require(set(row) <= {"sound", "wav", "note"}, f"sound {number} carries unknown keys")
            require(isinstance(row.get("wav"), str) and row["wav"],
                    f"sound {number} ({row['sound']}) names no WAV; this lane writes a disc, so "
                    f"every sound in the recipe must name the file that replaces it")
            require(row["sound"] not in seen, f"{row['sound']} appears twice")
            seen.add(row["sound"])
            out.append({"sound": row["sound"], "wav": row["wav"], "note": row.get("note")})
        return out

    def _replacement(self, stream: ea_schl.Stream, wav_path: Path) -> Tuple[bytes, Dict[str, Any]]:
        header = stream.header
        payload = Path(wav_path).read_bytes()
        rate, channels, pcm = ea_schl.read_wav(payload)
        wanted_rate = int(header.sample_rate or 0)
        require(wanted_rate > 0, "this sound's header declares no sample rate, so a replacement has no rate to be resampled to.")
        mixed = ea_schl.remix(pcm, channels, header.channels)
        resampled = ea_schl.resample(mixed, header.channels, rate, wanted_rate)
        built = ea_schl.build_stream(resampled, channels=header.channels, sample_rate=wanted_rate,
                                     big_endian=header.big_endian, version=header.version or 3,
                                     codec=header.codec)
        require(len(built) <= stream.length,
                f"that WAV encodes to {len(built):,} bytes and this sound has {stream.length:,} to "
                f"give; trim it. The disc writer never grows a file.")
        padded = built + bytes(stream.length - len(built))
        return padded, {"wav": str(wav_path), "wav_sha256": disc_write.sha256(payload),
                        "source_rate": rate, "source_channels": channels, "target_rate": wanted_rate,
                        "target_channels": header.channels, "encoded_bytes": len(built),
                        "padded_to": stream.length,
                        "samples_written": len(resampled) // (2 * header.channels)}

    def _compose(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Dict[str, Any]:
        entries = self._entries(recipe)
        grouped: Dict[str, List[Tuple[int, str, str]]] = {}
        for entry in entries:
            target = catalogue.target(entry["sound"])
            problem = self.check_edit(target, {"wav": entry["wav"]})
            require(problem is None, str(problem))
            path, kind, index = parse_key(entry["sound"])
            require(kind == "stream", f"{entry['sound']}: only a bare stream file is replaced.")
            grouped.setdefault(path, []).append((index, entry["wav"], entry["sound"]))
        written: Dict[str, bytes] = {}
        sounds: List[Dict[str, Any]] = []
        with _DiscAudio(Path(source)) as disc:
            for path, items in grouped.items():
                entry = disc.find(path)
                start, end = disc.span(entry)
                current = bytearray(disc.view[start:end])
                streams = ea_schl.iter_streams(disc.view, start, end)
                for index, wav, key in items:
                    require(0 <= index < len(streams), f"{key}: {path} holds {len(streams)} stream(s).")
                    stream = streams[index]
                    padded, report = self._replacement(stream, Path(wav))
                    local = stream.offset - start
                    current[local:local + stream.length] = padded
                    sounds.append({"sound": key, "path": path, "index": index, "offset": local,
                                   "length": stream.length, **report})
                written[path] = bytes(current)
        return {"edits": entries, "sounds": sounds, "written": written}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        composed = self._compose(Path(source), recipe, catalogue)
        ranges = disc_write.plan_ranges(Path(source), composed["written"])
        return Plan(self.lane_id, tuple(e["sound"] for e in composed["edits"]), ranges,
                    {"schema": self.recipe_schema, "sounds": composed["sounds"],
                     "declared_bytes": sum(r.length for r in ranges), "runtime_note": disc_write.NOT_BOOTED})

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        disc_write.check_destination(source, destination)
        composed = self._compose(source, recipe, catalogue)
        report, ranges = disc_write.replace_files(source, destination, composed["written"])
        document = {"schema": self.write_schema, "source": str(source), "destination": str(destination),
                    "edits": composed["edits"], "sounds": composed["sounds"],
                    "files": [{"path": p, "bytes": len(b), "sha256": disc_write.sha256(b)}
                              for p, b in sorted(composed["written"].items())],
                    "iso_report": report, "runtime_note": disc_write.NOT_BOOTED}
        return Receipt(self.write_schema, self.lane_id, str(source), str(destination), ranges, document)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        source, destination = Path(source), Path(destination)
        problem = disc_write.verify_image(source, destination, receipt.document.get("iso_report"))
        if problem:
            return Verdict(False, f"Verification failed {problem}")
        sounds = receipt.document.get("sounds") or []
        if not sounds:
            return Verdict(False, "Verification failed: the receipt declares no sounds.")
        wanted: Dict[str, Dict[int, Dict[str, Any]]] = {}
        for row in sounds:
            wanted.setdefault(row["path"], {})[int(row["index"])] = row
        checked = 0
        try:
            with _DiscAudio(source) as before, _DiscAudio(destination) as after:
                for path, items in wanted.items():
                    b_start, b_end = before.span(before.find(path))
                    a_start, a_end = after.span(after.find(path))
                    old = ea_schl.iter_streams(before.view, b_start, b_end)
                    new = ea_schl.iter_streams(after.view, a_start, a_end)
                    if len(old) != len(new):
                        return Verdict(False, f"Verification failed: {path} went from {len(old)} to {len(new)} streams.")
                    for o, n in zip(old, new):
                        if o.offset - b_start != n.offset - a_start:
                            return Verdict(False, f"Verification failed: {path} stream {o.index} moved.")
                        if o.index not in items:
                            if o.length != n.length:
                                return Verdict(False, f"Verification failed: {path} stream {o.index} was not in the recipe and changed length.")
                            if before.view[o.offset:o.offset + o.length] != after.view[n.offset:n.offset + n.length]:
                                return Verdict(False, f"Verification failed: {path} stream {o.index} was not in the recipe and changed.")
                            continue
                        row = items[o.index]
                        if n.length > o.length:
                            return Verdict(False, f"Verification failed: {path} stream {o.index} grew past the bytes it owned.")
                        tail = after.view[n.offset + n.length:n.offset + o.length]
                        if bytes(tail).strip(b"\x00"):
                            return Verdict(False, f"Verification failed: {path} stream {o.index} leaves non-zero bytes after its end.")
                        header = n.header
                        if header.channels != o.header.channels or header.sample_rate != o.header.sample_rate:
                            return Verdict(False, f"Verification failed: {path} stream {o.index} changed its rate or channels.")
                        made = ea_schl.decode_eaxa(after.view, n.blocks, header.channels, header.big_endian, header.version)
                        payload = Path(str(row["wav"])).read_bytes()
                        if disc_write.sha256(payload) != row.get("wav_sha256"):
                            return Verdict(False, f"Verification failed: {row['wav']} is not the WAV the receipt recorded.")
                        rate, channels, pcm = ea_schl.read_wav(payload)
                        reference = ea_schl.resample(ea_schl.remix(pcm, channels, header.channels), header.channels, rate, int(header.sample_rate))
                        frame = 2 * header.channels
                        count = min(len(reference), len(made)) // frame * frame
                        if count == 0 or abs(len(reference) - len(made)) > frame * ea_schl.EAXA_SAMPLES_PER_FRAME * 2:
                            return Verdict(False, f"Verification failed: {path} stream {o.index} decodes to {len(made) // frame} samples, not the {len(reference) // frame} the WAV holds.")
                        snr = ea_schl.signal_to_noise(reference[:count], made[:count])
                        if snr is not None and snr < MIN_SNR_DB:
                            return Verdict(False, f"Verification failed: {path} stream {o.index} decodes at {snr:.1f} dB against the WAV, below {MIN_SNR_DB} dB.")
                        checked += 1
        except (containers.DiscError, ea_schl.SchlError, Refusal, OSError) as exc:
            return Verdict(False, f"Verification failed: {exc}")
        return Verdict(True, f"{len(wanted)} file(s) re-read from both images: {checked} replaced stream(s) "
                             f"decode against the WAV they came from, every other stream is byte-identical, "
                             f"and the image-level ranges hold.", {"result": "PASS", "streams": checked})

    def synthetic_source(self, work_dir: Path) -> Path:
        work_dir = Path(work_dir)
        path = work_dir / "mvp05-ps2-audio-synthetic.iso"
        if not path.exists():
            path.write_bytes(containers.build_synthetic_disc())
        wav = work_dir / "mvp05-ps2-audio-fixture.wav"
        if not wav.exists():
            wav.write_bytes(ea_schl.wav_bytes(ea_schl.synthetic_pcm(2240, 2, sample_rate=24000), 24000, 2))
        self._fixture_wav = wav
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        wav = getattr(self, "_fixture_wav", None)
        if wav is None:
            wav = Path(catalogue.source).parent / "mvp05-ps2-audio-fixture.wav"
        require(Path(wav).is_file(), "the conformance WAV is missing; call synthetic_source first")
        for target in catalogue.targets:
            if target.raw.get("writable") and int(target.raw.get("length") or 0) >= 4000:
                return (Edit(target.key, {"wav": str(wav)}, note="conformance: replace one stream"),)
        raise Refusal("this catalogue lists no replaceable stream, so there is no edit to prove")


class AudioBanksLane:
    """The two ``BNKl`` banks: catalogue and export.  Nothing is written back."""

    lane_id = "audio.banks"
    capability_id = "mvp05ps2.audio.banks"
    surface = "audio"
    page = "audio"
    title = "Sound banks"
    classification = "extract-only"
    recipe_schema = "mvp05_ps2_audio_banks_recipe/v1"
    catalogue_schema = "mvp05_ps2_audio_banks_catalogue/v1"
    write_schema = "mvp05_ps2_audio_banks_write/v1"
    validators = ("tools/validate_mvp05_ps2_audio.sh", "tools/validate_mvp05_ps2_audio.bat")
    fixed_allocation = False
    NO_WRITER = ("A bank sound is not replaced here: the two banks hold 11 sounds between them, "
                 "their loop points are not mapped, and no rebuilt MVP Baseball 2005 file has been "
                 "booted. Export the WAV.")

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        targets: List[Target] = []
        files: List[Dict[str, Any]] = []
        refusals: List[Dict[str, str]] = []
        with _DiscAudio(Path(source)) as disc:
            for entry in disc.banks():
                start, end = disc.span(entry)
                try:
                    bank = ea_schl.parse_bank(disc.view, start, end - start)
                except (Refusal, ea_schl.SchlError) as exc:
                    refusals.append({"where": entry.path, "sentence": str(exc)})
                    continue
                summary = {"path": entry.path, "bytes": int(entry.length), "version": bank.version,
                           "sounds": len(bank.sounds), "playable": 0}
                for sound in bank.sounds:
                    playable = sound.data_length > 0 and bool(sound.sample_rate)
                    summary["playable"] += int(playable)
                    row = {"path": entry.path, "sound": sound.index, "bytes": sound.data_length,
                           "channels": sound.channels, "sample_rate": sound.sample_rate,
                           "samples": sound.sample_count, "playable": playable,
                           "duration": _duration(sound.sample_rate, sound.sample_count),
                           "file_name": f"{entry.path.rsplit('/', 1)[-1].lower().replace('.', '-')}-s{sound.index:02d}{WAV_SUFFIX}"}
                    targets.append(Target(
                        key=f"{entry.path}:{sound.index}", label=f"{entry.path.rsplit('/', 1)[-1]} · sound {sound.index}",
                        detail=" · ".join([row["duration"], f"{sound.sample_rate:,} Hz" if sound.sample_rate else "rate not declared",
                                           "stereo" if sound.channels == 2 else "mono", "Sony PlayStation ADPCM"]),
                        budget=f"Export writes {row['file_name']}. Nothing is written to your disc.",
                        searchable=f"{entry.path} {sound.index}", raw=dict(row),
                        fields=(Field("writer", "note", "Why there is no replace here", self.NO_WRITER, read_only=True),)))
                files.append(summary)
        document = {"schema": self.catalogue_schema, "source": str(source), "files": files,
                    "sounds": sum(f["sounds"] for f in files), "playable": sum(f["playable"] for f in files),
                    "refusals": refusals, "writer_note": self.NO_WRITER}
        return Catalogue(self.catalogue_schema, self.lane_id, str(source), tuple(targets), document)

    def decode_wav(self, source: Path, target: Target) -> bytes:
        return self.decode_wav_by_key(Path(source), target.key)

    def decode_wav_by_key(self, source: Path, key: str) -> bytes:
        match = re.match(r"^(/.+):(\d+)$", str(key))
        require(match is not None, f"{key!r} does not name a bank sound: a key is <path>:<sound>.")
        path, index = match.group(1), int(match.group(2))
        with _DiscAudio(Path(source)) as disc:
            entry = disc.find(path)
            start, end = disc.span(entry)
            bank = ea_schl.parse_bank(disc.view, start, end - start)
            for sound in bank.sounds:
                if sound.index != index:
                    continue
                require(sound.data_length > 0 and bool(sound.sample_rate),
                        f"{key}: this sound declares no data or no rate, so there is nothing to decode.")
                pcm = ea_schl.decode_bank_sound(disc.view, bank, sound)
                return ea_schl.wav_bytes(pcm, int(sound.sample_rate), sound.channels)
            raise Refusal(f"{path} holds {len(bank.sounds)} sound(s), so there is no sound {index}.")

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        if values:
            return f"{target.key}: {', '.join(sorted(values))} is not something this lane takes. {self.NO_WRITER}"
        if not target.raw.get("playable"):
            return f"{target.key}: this sound declares no data or no rate, so it cannot be exported."
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        return {"schema": self.recipe_schema,
                "sounds": [dict(sound=e.target_key, **({"note": e.note} if e.note else {})) for e in edits]}

    def _entries(self, recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == self.recipe_schema,
                f"recipe schema is {recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, expected {self.recipe_schema}")
        rows = recipe.get("sounds")
        require(isinstance(rows, list) and rows, "a recipe must carry a non-empty 'sounds' list")
        out = []
        seen = set()
        for number, row in enumerate(rows):
            require(isinstance(row, Mapping) and isinstance(row.get("sound"), str) and set(row) <= {"sound", "note"},
                    f"sound {number} must name the sound it exports and nothing else")
            require(row["sound"] not in seen, f"{row['sound']} appears twice")
            seen.add(row["sound"])
            out.append(dict(row))
        return out

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        rows = []
        for entry in self._entries(recipe):
            target = catalogue.target(entry["sound"])
            problem = self.check_edit(target, {})
            require(problem is None, str(problem))
            rows.append({"sound": entry["sound"], "file_name": target.raw.get("file_name")})
        return Plan(self.lane_id, tuple(r["sound"] for r in rows), (),
                    {"schema": self.recipe_schema, "sounds": rows, "writer_note": self.NO_WRITER})

    @staticmethod
    def export_root_for(destination: Path) -> Path:
        destination = Path(destination)
        return destination.with_name(destination.name + "-sounds")

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        disc_write.check_destination(source, destination)
        export_root = self.export_root_for(destination)
        require(not os.path.lexists(export_root), f"the export folder {export_root} already exists")
        planned = self.plan(source, recipe, catalogue)
        export_root.mkdir(parents=True)
        artifacts: List[Artifact] = []
        rows = []
        for row in planned.document["sounds"]:
            wav = self.decode_wav_by_key(source, str(row["sound"]))
            path = export_root / str(row["file_name"])
            with open(path, "xb") as handle:
                handle.write(wav)
            digest = disc_write.sha256(wav)
            artifacts.append(Artifact(str(path), digest, "wav"))
            rows.append({**row, "sha256": digest, "bytes": len(wav)})
        document = {"schema": self.write_schema, "source": str(source), "destination": str(destination),
                    "export_folder": export_root.as_posix(), "sounds": rows, "writer_note": self.NO_WRITER,
                    "note": "Exported WAVs. Your disc image was opened read-only and is unchanged."}
        payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with open(destination, "xb") as handle:
            handle.write(payload)
        artifacts.insert(0, Artifact(str(destination), disc_write.sha256(payload), "export-manifest"))
        return Receipt(self.write_schema, self.lane_id, str(source), str(destination), (), document,
                       artifacts=tuple(artifacts))

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        destination = Path(destination)
        if not destination.is_file():
            return Verdict(False, f"Verification failed: the manifest {destination} is missing.")
        declared = {Path(a.path): a for a in receipt.artifacts}
        export_root = Path(str(receipt.document.get("export_folder") or self.export_root_for(destination)))
        if not export_root.is_dir():
            return Verdict(False, f"Verification failed: the export folder {export_root} is missing.")
        on_disk = {p for p in export_root.rglob("*") if p.is_file()} | {destination}
        if on_disk != set(declared):
            return Verdict(False, "Verification failed: the export folder does not hold exactly the declared files.")
        for path, artifact in declared.items():
            if disc_write.sha256(path.read_bytes()) != artifact.sha256:
                return Verdict(False, f"Verification failed: {path.name} is not the file the receipt recorded.")
        checked = 0
        for row in receipt.document.get("sounds", []):
            try:
                expected = disc_write.sha256(self.decode_wav_by_key(Path(source), str(row["sound"])))
            except Refusal as exc:
                return Verdict(False, f"Verification failed: {exc}")
            if expected != row.get("sha256"):
                return Verdict(False, f"Verification failed: {row['sound']} decodes to a different sound.")
            checked += 1
        if not checked:
            return Verdict(False, "Verification failed: the receipt declares no sounds.")
        return Verdict(True, f"{checked} sound(s) re-decoded from the source and matched byte for byte; "
                             f"{len(declared)} declared file(s) present and nothing else.",
                       {"result": "PASS", "sounds": checked})

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "mvp05-ps2-audio-banks-synthetic.iso"
        if not path.exists():
            path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        for target in catalogue.targets:
            if target.raw.get("playable"):
                return (Edit(target.key, {}, note="conformance: export this bank sound"),)
        raise Refusal("this catalogue lists no playable bank sound")


STREAMS_LANE = AudioStreamsLane()
BANKS_LANE = AudioBanksLane()


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="mod_editor.games.mvp05_ps2.audio_lane",
                                     description="Catalogue the audio of an MVP Baseball 2005 (PS2) disc.")
    parser.add_argument("--source")
    parser.add_argument("--lane", default="streams", choices=("streams", "banks"))
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane: Any = STREAMS_LANE if arguments.lane == "streams" else BANKS_LANE
    if not arguments.selftest and not arguments.source:
        parser.error("give --source a disc image, or --selftest")
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                src = lane.synthetic_source(Path(room))
                catalogue = lane.build_catalogue(src)
                recipe = lane.compose_recipe(lane.conformance_edits(catalogue))
                dest = Path(room) / "out.iso"
                receipt = lane.build(src, dest, recipe, catalogue)
                verdict = lane.verify(src, dest, receipt)
                require(verdict.passed, verdict.summary)
                print(f"SELFTEST ok: {verdict.summary}")
                return 0
        catalogue = lane.build_catalogue(Path(arguments.source),
                                         progress=lambda line: print(line, file=sys.stderr))
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8", newline="\n")
    if arguments.lane == "streams":
        print("AUDIO files=%d streams=%d decodable=%d archives=%d entries=%d codecs=%s" % (
            document["bare_files"], document["streams"], document["decodable"],
            document["archives"], document["entries"], document["codecs"]))
    else:
        print("BANKS files=%d sounds=%d playable=%d" % (len(document["files"]), document["sounds"], document["playable"]))
    return 0


__all__ = ["AudioBanksLane", "AudioStreamsLane", "BANKS_LANE", "MAX_TARGETS", "MIN_SNR_DB",
           "STREAMS_LANE", "encoded_size", "parse_key"]


if __name__ == "__main__":
    raise SystemExit(_main())
