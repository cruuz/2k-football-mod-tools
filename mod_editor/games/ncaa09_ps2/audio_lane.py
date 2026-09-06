"""NCAA Football 09's ``SCHl`` streams and ``BNKl`` banks: catalogue and export.

The disc carries **8,021 ``SCHl`` streams and 728 ``BNKl`` banks** across four
containers [M]:

===================  =======  ========================================
``SPCHDATA.DAT``     631 MB   7,609 streams, every one **MicroTalk**
``SOUNDDAT.DAT``     539 MB   408 streams (EA-XA) and 728 banks
``FESNDDAT.DAT``      44 MB   4 streams (EA-XA)
``CMNTDATA.DAT``     224 KB   no audio: 27 ``MMAP`` and 2 ``DMF`` members
===================  =======  ========================================

**412 of the 8,021 streams carry a codec that decodes here** -- EA-XA ADPCM,
all of them in ``SOUNDDAT.DAT`` and ``FESNDDAT.DAT`` -- and the other 7,609 are
EA's MicroTalk, which no decoder in this repository or in ffmpeg opens [M/S].
Those are listed with their rate, channels and length and their audio is refused
by name rather than guessed at.  All 728 banks open and hold **1,213 sounds**
[M], PlayStation ADPCM, and those export.

``extract-only``: a WAV comes out, nothing goes back in.  A writer would have to
re-encode into the bytes a sound already occupies and rewrite the three preload
caches that copy the container, and **no rebuilt NCAA Football 09 container has
ever been booted**.

The containers run to 631 MB, so the image is memory-mapped once and the lane
hands out offsets; no payload is copied to build a catalogue and nothing is
decoded until an export asks for it.

Run it without a window::

    python3 -m mod_editor.games.ncaa09_ps2.audio_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_schl, ea_terf
from mod_editor.games.contract import (
    Artifact, Catalogue, Edit, Field, Plan, Receipt, Refusal, Target, Verdict,
)

from . import containers

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "tools"))

import ps2_iso9660 as iso_lib  # noqa: E402

STREAMS_CAPABILITY = "ncaa09ps2.audio.streams"
STREAMS_LANE_ID = "audio.streams"
STREAMS_SCHEMA = "ncaa09_ps2_audio_streams/v1"

BANKS_CAPABILITY = "ncaa09ps2.audio.banks"
BANKS_LANE_ID = "audio.banks"
BANKS_SCHEMA = "ncaa09_ps2_audio_banks/v1"

#: Where the audio is, and what the glossary says each container is for [M].
STREAM_CONTAINERS = (
    ("FESNDDAT.DAT", "front-end sound"),
    ("SOUNDDAT.DAT", "sound effects and music"),
    ("SPCHDATA.DAT", "speech and commentary"),
)
BANK_CONTAINERS = (("SOUNDDAT.DAT", "sound banks"),)

#: How many rows a page lists.  8,021 stream rows is a dump; the document keeps
#: every count either way.
MAX_STREAM_TARGETS = 3000
MAX_BANK_TARGETS = 3000

#: How much of a member is handed to the header parser.  An ``SCHl`` header is
#: well under this and a bank's directory is measured at up to 712 KB on this
#: disc, so a bank is handed its whole stored length instead [M].
STREAM_HEAD_BYTES = 1 << 16

#: The recipe and receipt schemas an export writes.
STREAM_EXPORT_SCHEMA = "ncaa09_ps2_audio_stream_export/v1"
BANK_EXPORT_SCHEMA = "ncaa09_ps2_audio_bank_export/v1"


def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _require(condition: object, message: str) -> None:
    if not condition:
        raise Refusal(message)


def _safe_name(key: str) -> str:
    """A file name from a target key: only the characters a key is made of."""

    return "".join(character if character.isalnum() or character in "-._"
                   else "-" for character in key) + ".wav"


class _ExportMixin:
    """The half of an export lane that is the same for streams and for banks.

    ``build`` writes a NEW manifest and a NEW folder of WAVs beside it and never
    touches the source; ``verify`` re-decodes every exported file **from the
    user's own disc by key**, not through the catalogue that produced the
    receipt, so a tampered WAV and an undeclared file both fail.
    """

    def _rows_of(self, recipe):
        entries = list(recipe.get("edits") or ())
        _require(entries, "this recipe names no sound to export.")
        return entries

    @staticmethod
    def export_root_for(destination: Path) -> Path:
        destination = Path(destination)
        return destination.with_name(destination.name + "-audio")

    def plan(self, source: Path, recipe, catalogue) -> Plan:
        keys = []
        rows = []
        for entry in self._rows_of(recipe):
            key = str(entry.get("target"))
            target = catalogue.target(key)
            rows.append({"target": key, "file_name": _safe_name(key),
                         "sample_rate": target.raw.get("sample_rate"),
                         "channels": target.raw.get("channels")})
            keys.append(key)
        return Plan(self.lane_id, tuple(keys), (),
                    {"schema": self.recipe_schema, "exports": rows,
                     "writer_note": self.NO_WRITER})

    def build(self, source: Path, destination: Path, recipe, catalogue,
              *, work_dir=None) -> Receipt:
        source, destination = Path(source), Path(destination)
        _require(destination.resolve() != source.resolve(),
                 f"{destination} is the source image; an export writes a NEW manifest and "
                 f"never the disc.")
        _require(not os.path.lexists(destination),
                 f"destination {destination} already exists; refusing to overwrite it.")
        export_root = self.export_root_for(destination)
        _require(not os.path.lexists(export_root),
                 f"the export folder {export_root} already exists; choose a destination "
                 f"whose folder is free.")
        planned = self.plan(source, recipe, catalogue)
        export_root.mkdir(parents=True)
        artifacts = []
        rows = []
        for row in planned.document["exports"]:
            wav = self.export_wav(source, catalogue.target(str(row["target"])))
            path = export_root / str(row["file_name"])
            with open(path, "xb") as handle:
                handle.write(wav)
            digest = _sha256(wav)
            artifacts.append(Artifact(str(path), digest, "wav"))
            rows.append({**row, "sha256": digest, "bytes": len(wav)})
        readme = export_root / "HOW-TO.txt"
        readme.write_text(self._how_to(len(rows)), encoding="utf-8", newline="\n")
        artifacts.append(Artifact(str(readme), _sha256(readme.read_bytes()), "text"))
        document = {
            "schema": self.export_schema,
            "source": str(source),
            "destination": str(destination),
            "export_folder": export_root.as_posix(),
            "exports": rows,
            "writer_note": self.NO_WRITER,
            "note": "Exported WAVs. Your disc image was opened read-only and is unchanged.",
        }
        payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with open(destination, "xb") as handle:
            handle.write(payload)
        artifacts.insert(0, Artifact(str(destination), _sha256(payload), "export-manifest"))
        return Receipt(self.export_schema, self.lane_id, str(source), str(destination), (),
                       document, artifacts=tuple(artifacts))

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        """Re-decode every exported file from the user's disc, independently."""

        destination = Path(destination)
        if not destination.is_file():
            return Verdict(False,
                           f"Verification failed: the manifest {destination} is missing.")
        export_root = Path(str(receipt.document.get("export_folder") or "")
                           or self.export_root_for(destination))
        if not export_root.is_dir():
            return Verdict(False, f"Verification failed: the export folder {export_root} "
                                  f"is missing.")
        declared = {Path(artifact.path): artifact for artifact in receipt.artifacts}
        on_disk = {path for path in export_root.rglob("*") if path.is_file()}
        on_disk.add(destination)
        extra = sorted(str(path) for path in on_disk - set(declared))
        missing = sorted(str(path) for path in set(declared) - on_disk)
        if extra or missing:
            return Verdict(False, "Verification failed: the export folder holds "
                           + (f"undeclared file(s) {extra}" if extra else "")
                           + (" and " if extra and missing else "")
                           + (f"no {missing}" if missing else "") + ".")
        for path, artifact in declared.items():
            if _sha256(path.read_bytes()) != artifact.sha256:
                return Verdict(False, f"Verification failed: {path.name} on disk is not "
                                      f"the file the receipt recorded.")
        rows = list(receipt.document.get("exports") or ())
        if not rows:
            return Verdict(False, "Verification failed: the receipt declares no exports.")
        catalogue = self.build_catalogue(Path(source))
        checked = 0
        for row in rows:
            try:
                expected = _sha256(self.export_wav(
                    Path(source), catalogue.target(str(row["target"]))))
            except Refusal as exc:
                return Verdict(False, f"Verification failed: {exc}")
            if expected != row.get("sha256"):
                return Verdict(False, f"Verification failed: {row['file_name']} does not "
                                      f"re-decode to the bytes the receipt recorded; the "
                                      f"export or the source has changed.")
            checked += 1
        return Verdict(True, f"{checked} exported file(s) re-decoded from the source and "
                             f"matched, and no undeclared file is in the export folder. "
                             f"The source image is unchanged.")


class _DiscAudio:
    """One open image, memory-mapped, with the audio containers located in it.

    ``SPCHDATA.DAT`` alone is 631 MB and the four containers come to 1.2 GB [M].
    Reading one into memory to list its sounds costs more than the catalogue is
    worth, so this maps the image once and hands out offsets: the catalogue
    never copies a payload and never decodes.
    """

    def __init__(self, source: Path) -> None:
        self.path = Path(source)
        self.image = containers.open_disc(self.path)
        if self.image.sector_size != iso_lib.SECTOR_USER_BYTES or self.image.data_offset:
            raise containers.DiscError(
                f"{self.path.name} is a raw-CD image ({self.image.sector_size}-byte "
                f"sectors); this lane reads the big audio containers through a memory "
                f"map, which needs the 2048-byte layout every PlayStation 2 DVD uses. "
                f"Convert the image to a plain ISO and open it again.")
        self.entries: Dict[str, containers.DataFile] = {
            entry.name: entry for entry in containers.data_files(self.image)}
        self._handle = open(self.path, "rb")
        try:
            self.view = mmap.mmap(self._handle.fileno(), 0, access=mmap.ACCESS_READ)
        except (OSError, ValueError) as exc:  # pragma: no cover - platform specific
            self._handle.close()
            raise containers.DiscError(
                f"{self.path.name} could not be memory-mapped ({exc}).") from exc

    def close(self) -> None:
        try:
            self.view.close()
        finally:
            self._handle.close()

    def __enter__(self) -> "_DiscAudio":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def has(self, name: str) -> bool:
        return name in self.entries

    def span(self, name: str) -> Tuple[int, int]:
        """``(byte offset, length)`` of ``/DATA/<name>`` inside the image."""

        entry = self.entries.get(name)
        if entry is None:
            raise Refusal(f"{name} is not on this image; choose the "
                          f"{containers.SERIAL} disc.")
        start = iso_lib.extent_byte_offset(self.image, entry.lba, 0)
        length = int(entry.recorded_length)
        if start < 0 or start + length > len(self.view):
            raise Refusal(f"{name} runs past the end of this image; it is truncated.")
        return start, length

    def members(self, name: str) -> Tuple[Tuple[int, int, int], ...]:
        """``(index, absolute offset, stored size)`` for every member."""

        base, length = self.span(name)
        view = self.view
        if bytes(view[base:base + 4]) != ea_terf.TERF_MAGIC:
            raise Refusal(f"{name} does not open with {ea_terf.TERF_MAGIC!r}; this "
                          f"disc's audio containers all do.")
        _alignment, count = struct.unpack_from("<HH", view, base + 12)
        chunks: Dict[str, Tuple[int, int]] = {}
        position = base
        while position + ea_terf.CHUNK_HEADER_SIZE <= base + length:
            tag = bytes(view[position:position + 4]).decode("latin-1")
            size, = struct.unpack_from("<I", view, position + 4)
            chunks.setdefault(tag, (position, size))
            if size <= 0:
                break
            position += size
        if "DIR1" not in chunks or "DATA" not in chunks:
            raise Refusal(f"{name} has no DIR1 or DATA chunk; it is not a container "
                          f"this lane reads.")
        directory = chunks["DIR1"][0] + ea_terf.CHUNK_HEADER_SIZE
        data_tag = chunks["DATA"][0]
        out: List[Tuple[int, int, int]] = []
        for index in range(count):
            offset, size = struct.unpack_from("<II", view, directory + 8 * index)
            start = data_tag + offset
            if size <= 0 or start + size > base + length:
                continue
            out.append((index, start, size))
        return tuple(out)


class AudioStreamsLane(_ExportMixin):
    """The ``SCHl`` streams: catalogue and export.  Nothing is written back."""

    export_schema = STREAM_EXPORT_SCHEMA
    lane_id = STREAMS_LANE_ID
    capability_id = STREAMS_CAPABILITY
    surface = "audio"
    page = "audio"
    title = "Speech, music and sound-effect streams"
    classification = "extract-only"
    recipe_schema = STREAMS_SCHEMA
    validators = (
        "tools/validate_ncaa09_ps2_audio.sh",
        "tools/validate_ncaa09_ps2_audio.bat",
    )
    fixed_allocation = False

    NO_WRITER = (
        "A stream is not replaced here. 7,609 of this disc's 8,021 streams are EA "
        "MicroTalk, which no decoder in this repository or in ffmpeg opens, a writer for "
        "the other 412 would have to keep the three QL01 preload caches in step with the "
        "container it rewrites, and no rebuilt NCAA Football 09 container has ever been "
        "booted. Export the WAV instead."
    )

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        refusals: Dict[str, int] = {}
        skipped: Dict[str, str] = {}
        codecs: Dict[str, int] = {}
        platforms: Dict[str, int] = {}
        total = decodable = 0
        with _DiscAudio(Path(source)) as disc:
            for name, note in STREAM_CONTAINERS:
                if not disc.has(name):
                    skipped[name] = "not on this image"
                    continue
                if progress is not None:
                    progress(f"{name}…")
                try:
                    members = disc.members(name)
                except Refusal as exc:
                    skipped[name] = str(exc)
                    continue
                for index, start, size in members:
                    if bytes(disc.view[start:start + 4]) != ea_schl.SCHL_MAGIC:
                        continue
                    total += 1
                    if progress is not None and total % 512 == 0:
                        progress(f"{name}: {total} stream(s) read…")
                    window = min(size, STREAM_HEAD_BYTES)
                    try:
                        header = ea_schl.parse_stream_header(
                            disc.view[start:start + window], 0, window)
                    except (Refusal, ea_schl.SchlError) as exc:
                        key = str(exc)[:160]
                        refusals[key] = refusals.get(key, 0) + 1
                        continue
                    codecs[header.codec_name] = codecs.get(header.codec_name, 0) + 1
                    platforms[header.platform] = platforms.get(header.platform, 0) + 1
                    if header.decodable:
                        decodable += 1
                    row = {
                        "container": name,
                        "container_note": note,
                        "member": index,
                        "stored_bytes": size,
                        "codec": header.codec_name,
                        "codec_id": header.codec,
                        "platform": header.platform,
                        "channels": header.channels,
                        "sample_rate": header.sample_rate,
                        "samples": header.sample_count,
                        "seconds": round(header.seconds, 3) if header.seconds else None,
                        "decodable": bool(header.decodable),
                    }
                    rows.append(row)
                    if len(targets) < MAX_STREAM_TARGETS:
                        targets.append(self._stream_target(row))
        document = {
            "schema": STREAMS_SCHEMA,
            "source": str(source),
            "containers": [name for name, _note in STREAM_CONTAINERS],
            "streams": total,
            "streams_decodable": decodable,
            "codecs": codecs,
            "platforms": platforms,
            "stream_rows_listed": len(targets),
            "stream_rows_cap": MAX_STREAM_TARGETS,
            "containers_skipped": skipped,
            "refusals": refusals,
            "rows": rows,
        }
        return Catalogue(schema=STREAMS_SCHEMA, lane_id=self.lane_id, source=str(source),
                         targets=tuple(targets), document=document)

    @staticmethod
    def _stream_target(row: Mapping[str, Any]) -> Target:
        detail = [row["codec"], f"{row['channels']} channel(s)"]
        if row["sample_rate"]:
            detail.append(f"{row['sample_rate']:,} Hz")
        if row["seconds"]:
            detail.append(f"{row['seconds']:.2f} s")
        detail.append(f"{row['stored_bytes']:,} bytes")
        if not row["decodable"]:
            detail.append("no decoder here")
        return Target(
            key=f"stream:{row['container']}:{row['member']}",
            label=f"{row['container']} member {row['member']}",
            detail=" · ".join(detail),
            budget="Export only: this lane writes a WAV and never touches your disc.",
            searchable=f"{row['container']} {row['member']} {row['codec']} "
                       f"{row['platform']}",
            raw=dict(row),
            fields=(
                Field("codec", "note", "Codec",
                      "Which EA codec this stream carries.", read_only=True),
                Field("sample_rate", "note", "Sample rate",
                      "What the stream's own header declares.", read_only=True),
                Field("channels", "note", "Channels", "Mono or stereo.", read_only=True),
                Field("seconds", "note", "Length",
                      "Samples divided by the declared rate.", read_only=True),
                Field("decodable", "note", "Decodes here",
                      "Whether this module's shared reader opens this codec.",
                      read_only=True),
            ),
        )

    def export_wav(self, source: Path, target: Target) -> bytes:
        """One stream as a WAV, decoded now, or a refusal naming the codec.

        Nothing decoded here is written to this repository: the bytes go to the
        file the user asked for.
        """

        raw = dict(target.raw or {})
        with _DiscAudio(Path(source)) as disc:
            wanted = raw.get("member")
            wanted = -1 if wanted is None else int(wanted)
            base = None
            for index, start, size in disc.members(str(raw.get("container"))):
                if index == wanted:
                    base = (start, size)
                    break
            if base is None:
                raise Refusal(
                    f"{raw.get('container')} has no member {raw.get('member')} on this "
                    f"image; rebuild the catalogue from the disc you have open.")
            start, size = base
            header = ea_schl.parse_stream_header(disc.view, start, start + size)
            if not header.decodable:
                raise Refusal(
                    f"{raw.get('container')} member {raw.get('member')} is "
                    f"{header.codec_name}; no decoder for it exists in this repository "
                    f"or in ffmpeg, so its audio is listed and not guessed at.")
            streams = ea_schl.iter_streams(disc.view, start, start + size)
            if not streams:
                raise Refusal(
                    f"{raw.get('container')} member {raw.get('member')} declares no "
                    f"audio block; there is nothing to export.")
            stream = streams[0]
            pcm = ea_schl.decode_eaxa(disc.view, stream.blocks, header.channels,
                                      header.big_endian)
            return ea_schl.wav_bytes(pcm, header.sample_rate or 22050, header.channels)

    def _how_to(self, count: int) -> str:
        return (
            "NCAA Football 09 (PlayStation 2) - exported audio streams\n"
            "=========================================================\n"
            "\n"
            f"{count} WAV file(s), decoded from your own disc image. Your image was\n"
            "opened read-only and is unchanged.\n"
            "\n"
            "These are 16-bit PCM at the rate the disc declares for each stream. They\n"
            "were EA-XA ADPCM on the disc.\n"
            "\n"
            "What you cannot do yet, and why:\n"
            "\n"
            "  * Put one back. " + self.NO_WRITER + "\n"
            "  * Export the speech. 7,609 of this disc's 8,021 streams are EA\n"
            "    MicroTalk, and no decoder for it exists in this repository or in\n"
            "    ffmpeg. They are listed with their rate and length instead.\n"
        )

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        if not target.raw.get("decodable"):
            return (f"{target.raw.get('container')} member {target.raw.get('member')} is "
                    f"{target.raw.get('codec')}; no decoder for it exists in this "
                    f"repository or in ffmpeg, so it is listed and not exported.")
        if any(str(key) != "note" for key in values):
            return self.NO_WRITER
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        return {"schema": self.recipe_schema,
                "edits": [{"target": edit.target_key, "note": edit.note}
                          for edit in edits]}

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "ncaa09-ps2-audio-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        for target in catalogue.targets:
            if target.raw.get("decodable"):
                return (Edit(target.key, {},
                             note="conformance: export this stream as it is"),)
        raise Refusal("this catalogue lists no decodable stream, so there is no export "
                      "to prove.")


class AudioBanksLane(_ExportMixin):
    """The ``BNKl`` sound banks: catalogue and export.  Nothing is written back."""

    export_schema = BANK_EXPORT_SCHEMA
    lane_id = BANKS_LANE_ID
    capability_id = BANKS_CAPABILITY
    surface = "audio"
    page = "audio"
    title = "Sound banks"
    classification = "extract-only"
    recipe_schema = BANKS_SCHEMA
    validators = (
        "tools/validate_ncaa09_ps2_audio.sh",
        "tools/validate_ncaa09_ps2_audio.bat",
    )
    fixed_allocation = False

    NO_WRITER = (
        "A bank sound is not replaced here. A writer would re-encode into the bytes the "
        "sound already occupies and rewrite the three QL01 preload caches that copy this "
        "container, and no rebuilt NCAA Football 09 container has ever been booted. "
        "Export the WAV instead."
    )

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        refusals: Dict[str, int] = {}
        skipped: Dict[str, str] = {}
        banks = sounds = playable = 0
        with _DiscAudio(Path(source)) as disc:
            for name, note in BANK_CONTAINERS:
                if not disc.has(name):
                    skipped[name] = "not on this image"
                    continue
                if progress is not None:
                    progress(f"{name}…")
                try:
                    members = disc.members(name)
                except Refusal as exc:
                    skipped[name] = str(exc)
                    continue
                for index, start, size in members:
                    if size < 0x18 or bytes(disc.view[start:start + 4]) != ea_schl.BNKL_MAGIC:
                        continue
                    try:
                        bank = ea_schl.parse_bank(disc.view, start, size)
                    except (Refusal, ea_schl.SchlError) as exc:
                        key = str(exc)[:160]
                        refusals[key] = refusals.get(key, 0) + 1
                        continue
                    banks += 1
                    if progress is not None and banks % 64 == 0:
                        progress(f"{name}: {banks} bank(s) read…")
                    for position, sound in enumerate(bank.sounds):
                        sounds += 1
                        ok = sound.data_length > 0 and bool(sound.sample_rate)
                        playable += 1 if ok else 0
                        row = {
                            "container": name,
                            "container_note": note,
                            "member": index,
                            "sound": position,
                            "bank_version": bank.version,
                            "channels": sound.channels,
                            "sample_rate": sound.sample_rate,
                            "bytes": sound.data_length,
                            "playable": bool(ok),
                        }
                        rows.append(row)
                        if len(targets) < MAX_BANK_TARGETS:
                            targets.append(self._bank_target(row))
        document = {
            "schema": BANKS_SCHEMA,
            "source": str(source),
            "containers": [name for name, _note in BANK_CONTAINERS],
            "banks": banks,
            "sounds": sounds,
            "sounds_playable": playable,
            "sound_rows_listed": len(targets),
            "sound_rows_cap": MAX_BANK_TARGETS,
            "containers_skipped": skipped,
            "refusals": refusals,
            "rows": rows,
        }
        return Catalogue(schema=BANKS_SCHEMA, lane_id=self.lane_id, source=str(source),
                         targets=tuple(targets), document=document)

    @staticmethod
    def _bank_target(row: Mapping[str, Any]) -> Target:
        detail = [f"{row['channels']} channel(s)"]
        if row["sample_rate"]:
            detail.append(f"{row['sample_rate']:,} Hz")
        detail.append(f"{row['bytes']:,} bytes")
        if not row["playable"]:
            detail.append("declares no rate")
        return Target(
            key=f"bank:{row['container']}:{row['member']}:{row['sound']}",
            label=f"{row['container']} member {row['member']} sound {row['sound']}",
            detail=" · ".join(detail),
            budget="Export only: this lane writes a WAV and never touches your disc.",
            searchable=f"{row['container']} {row['member']} {row['sound']} bank",
            raw=dict(row),
            fields=(
                Field("sample_rate", "note", "Sample rate",
                      "What the bank's directory declares for this sound.", read_only=True),
                Field("channels", "note", "Channels", "Mono or stereo.", read_only=True),
                Field("bytes", "note", "Size",
                      "How many bytes of PlayStation ADPCM this sound holds.",
                      read_only=True),
                Field("playable", "note", "Exports",
                      "Whether the directory gives this sound a length and a rate.",
                      read_only=True),
            ),
        )

    def export_wav(self, source: Path, target: Target) -> bytes:
        """One bank sound as a WAV, decoded now, or a refusal naming why not."""

        raw = dict(target.raw or {})
        with _DiscAudio(Path(source)) as disc:
            wanted = raw.get("member")
            wanted = -1 if wanted is None else int(wanted)
            for index, start, size in disc.members(str(raw.get("container"))):
                if index != wanted:
                    continue
                bank = ea_schl.parse_bank(disc.view, start, size)
                position = int(raw.get("sound") or 0)  # sound 0 and no sound both mean 0
                if position >= len(bank.sounds):
                    raise Refusal(
                        f"{raw.get('container')} member {index} holds "
                        f"{len(bank.sounds)} sound(s); there is no sound {position}.")
                sound = bank.sounds[position]
                if not sound.sample_rate:
                    raise Refusal(
                        f"{raw.get('container')} member {index} sound {position} "
                        f"declares no sample rate, so a WAV written from it would "
                        f"play at a rate nobody measured.")
                pcm = ea_schl.decode_bank_sound(disc.view, bank, sound)
                return ea_schl.wav_bytes(pcm, sound.sample_rate, sound.channels)
        raise Refusal(f"{raw.get('container')} has no member {raw.get('member')} on this "
                      f"image; rebuild the catalogue from the disc you have open.")

    def _how_to(self, count: int) -> str:
        return (
            "NCAA Football 09 (PlayStation 2) - exported sound-bank audio\n"
            "============================================================\n"
            "\n"
            f"{count} WAV file(s), decoded from your own disc image. Your image was\n"
            "opened read-only and is unchanged.\n"
            "\n"
            "These are 16-bit PCM at the rate the disc declares for each sound. They\n"
            "were Sony PlayStation ADPCM on the disc.\n"
            "\n"
            "What you cannot do yet, and why:\n"
            "\n"
            "  * Put one back. " + self.NO_WRITER + "\n"
            "  * Export a sound that declares no rate. 460 of this disc's 1,213 bank\n"
            "    sounds do not, and a WAV written from one would play at a rate\n"
            "    nobody measured.\n"
        )

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        if not target.raw.get("playable"):
            return (f"{target.raw.get('container')} member {target.raw.get('member')} "
                    f"sound {target.raw.get('sound')} declares no sample rate, so a WAV "
                    f"written from it would play at a rate nobody measured.")
        if any(str(key) != "note" for key in values):
            return self.NO_WRITER
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        return {"schema": self.recipe_schema,
                "edits": [{"target": edit.target_key, "note": edit.note}
                          for edit in edits]}

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "ncaa09-ps2-banks-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        for target in catalogue.targets:
            if target.raw.get("playable"):
                return (Edit(target.key, {},
                             note="conformance: export this bank sound as it is"),)
        raise Refusal("this catalogue lists no playable bank sound, so there is no export "
                      "to prove.")


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.ncaa09_ps2.audio_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.ncaa09_ps2.audio_lane",
        description="Catalogue the SCHl streams and BNKl banks on an NCAA Football 09 "
                    "(PS2) disc. Read-only; a WAV export writes only where you ask.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21752 disc image")
    parser.add_argument("--out", help="write the catalogue documents to this JSON file")
    parser.add_argument("--selftest", action="store_true",
                        help="run both lanes on their synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    if not arguments.selftest and not arguments.source:
        parser.error("give --source a disc image, or --selftest")
    streams, banks = AudioStreamsLane(), AudioBanksLane()
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                source = streams.synthetic_source(Path(room))
                first = streams.build_catalogue(source)
                second = banks.build_catalogue(source)
        else:
            source = Path(arguments.source)
            report = lambda line: print(line, file=sys.stderr)  # noqa: E731
            first = streams.build_catalogue(source, progress=report)
            second = banks.build_catalogue(source, progress=report)
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if arguments.out:
        Path(arguments.out).write_text(
            json.dumps({"streams": dict(first.document), "banks": dict(second.document)},
                       indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    print("AUDIO streams=%d decodable=%d banks=%d sounds=%d playable=%d codecs=%s"
          % (first.document["streams"], first.document["streams_decodable"],
             second.document["banks"], second.document["sounds"],
             second.document["sounds_playable"],
             ",".join(f"{k}:{v}" for k, v in sorted(first.document["codecs"].items()))))
    return 0


__all__ = ["AudioBanksLane", "AudioStreamsLane", "BANKS_CAPABILITY", "BANKS_LANE_ID",
           "BANK_EXPORT_SCHEMA", "STREAM_EXPORT_SCHEMA",
           "BANKS_SCHEMA", "BANK_CONTAINERS", "MAX_BANK_TARGETS", "MAX_STREAM_TARGETS",
           "STREAMS_CAPABILITY", "STREAMS_LANE_ID", "STREAMS_SCHEMA",
           "STREAM_CONTAINERS", "STREAM_HEAD_BYTES"]


if __name__ == "__main__":
    raise SystemExit(_main())
