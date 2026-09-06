"""The disc's ``SCHl`` streams and ``BNKl`` banks: catalogue, play, export, replace.

Two lanes, because the disc has two shapes of sound and they earn different
rungs:

* :class:`AudioStreamsLane` -- the 34,046 ``SCHl`` streams inside six
  containers.  295 of them (all of ``BGM.DAT`` and ``SOUNDDAT.DAT``) are EA-XA
  ADPCM and decode, encode and write back; the other 33,751 are EA's MicroTalk
  speech codec, which nothing here or in ffmpeg can decode, so they are
  catalogued with their rate, channels and length and their audio is refused
  by name.
* :class:`AudioBanksLane` -- the 301 ``BNKl`` banks of ``SOUNDDAT.DAT`` and the
  967 PlayStation-ADPCM sounds inside them.  **Extract only**, and the reason
  is on the page: 134 of those sounds carry loop points (tags ``0x86`` /
  ``0x87``, a frame-aligned start and an end inside the sound [M]) whose
  handling by the SPU this module has not established, and replacing a looped
  sound without knowing how the loop is played is how a sound effect ends up
  stuttering in a game nobody here has booted.  Stereo bank sounds are planar,
  the second run at the offset tag ``0x89`` carries [M].

**Nothing has been booted.**  The streams lane's classification is
``offline-writer-proved``: a destination image is built and an independent
verifier re-parses it, decodes the replaced sound and compares it with the
user's own WAV, and every byte outside the declared ranges is checked against
the source.  That is the whole claim.  Whether Madden NFL 09 plays the result
is a question only an emulator can answer, and no one has asked it.

Run either without a window::

    python3 -m mod_editor.games.madden09_ps2.audio_lane --source DISC.iso
    python3 -m mod_editor.games.madden09_ps2.audio_lane --source DISC.iso \\
        --export OUT.json --limit 8

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import sys
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_schl, ea_terf
from mod_editor.games.contract import (
    Artifact,
    Catalogue,
    DeclaredRange,
    Edit,
    Field,
    Plan,
    Receipt,
    Refusal,
    Target,
    Verdict,
    require,
)

from . import containers

_TOOLS = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ps2_iso9660 as iso_lib  # noqa: E402
import ps2_iso9660_writer as iso_writer  # noqa: E402

STREAMS_CAPABILITY = "madden09ps2.audio.streams"
STREAMS_LANE_ID = "audio.streams"
BANKS_CAPABILITY = "madden09ps2.audio.banks"
BANKS_LANE_ID = "audio.banks"

STREAM_CATALOG_SCHEMA = "madden09_ps2_audio_streams_catalog/v1"
STREAM_RECIPE_SCHEMA = "madden09_ps2_audio_streams_recipe/v1"
STREAM_WRITE_SCHEMA = "madden09_ps2_audio_streams_write/v1"
BANK_CATALOG_SCHEMA = "madden09_ps2_audio_banks_catalog/v1"
BANK_RECIPE_SCHEMA = "madden09_ps2_audio_banks_recipe/v1"
BANK_WRITE_SCHEMA = "madden09_ps2_audio_banks_export/v1"

#: The six containers that hold audio, in the order the page lists them: the
#: two that decode first, so a capped target list still carries every sound a
#: user can hear.  Counts are measured on the retail disc [M].
AUDIO_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("BGM.DAT", "Music",
     "47 members, one stream each, 22,050 Hz stereo EA-XA ADPCM. The file names none of "
     "them, so the member index is the only structure it offers and which track is which "
     "is not established here."),
    ("SOUNDDAT.DAT", "Sound effects",
     "449 members: 301 BNKl banks, 119 members carrying 248 SCHl streams between them, "
     "3 nested containers and 26 members this module does not classify. The streams are "
     "EA-XA ADPCM at 22,050 to 44,100 Hz."),
    ("SPCHFEDT.DAT", "Front-end speech",
     "167 members, one stream each, 36,000 Hz mono MicroTalk. Catalogued, not decoded."),
    ("SPCHDATA.DAT", "Speech",
     "7,725 stream members holding 16,626 streams, 14,000 to 36,000 Hz mono MicroTalk. "
     "Catalogued, not decoded."),
    ("SPCHMAD1.DAT", "Commentary (1)",
     "1,212 stream members holding 12,475 streams, almost all 36,000 Hz mono MicroTalk. "
     "Catalogued, not decoded."),
    ("SPCHMAD2.DAT", "Commentary (2)",
     "2,119 stream members holding 4,483 streams, 36,000 Hz mono MicroTalk. Catalogued, "
     "not decoded."),
)

#: Only ``SOUNDDAT.DAT`` carries banks [M]: 301 of them, and no other container
#: on the disc holds a single ``BNKl`` member.
BANK_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("SOUNDDAT.DAT", "Sound banks",
     "301 BNKl banks holding 967 sounds, every one Sony PlayStation ADPCM at 12,000 to "
     "48,000 Hz. 134 of them carry loop points this module has not decoded."),
)

#: How many sounds the catalogue lists as targets, and how many rows its
#: document carries.  The disc offers 34,046 streams; a table is a table, and a
#: document that carried every row would be tens of megabytes of offsets.  The
#: totals in the document stay complete either way.
MAX_TARGETS = 4000

#: A container this lane will not read into memory to write back.  ``BGM.DAT``
#: is 214 MB and ``SPCHMAD1.DAT`` is 415 MB; cataloguing walks them through a
#: memory map and never copies, but a *rewrite* has to hold one whole container,
#: so the writer says no above this rather than swapping the machine to death.
REWRITE_LIMIT = 512 * 1024 * 1024

#: The sound files a build writes beside its manifest.
WAV_SUFFIX = ".wav"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class _DiscAudio:
    """One open image, memory-mapped, with the audio containers located in it.

    The audio containers run from 3.9 MB to 415 MB and there are 1.1 GB of them.
    Reading one into memory to list its sounds would cost more than the whole
    catalogue is worth, so this maps the image once and hands out offsets; the
    catalogue never copies a payload and never decodes.
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
            entry.name: entry for entry in containers.data_files(self.image)
        }
        self._caches: Optional[Tuple["QklCache", ...]] = None
        self._copies: Optional[Dict[str, Dict[str, Any]]] = None
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
            raise Refusal(f"{name} is not on this image; choose the SLUS-21770 disc.")
        start = iso_lib.extent_byte_offset(self.image, entry.lba, 0)
        length = int(entry.recorded_length)
        require(0 <= start and start + length <= len(self.view),
                f"{name} runs past the end of this image; it is truncated.")
        return start, length

    def members(self, name: str) -> Tuple[Tuple[int, int, int], ...]:
        """``(index, absolute offset, stored size)`` for every member of a container."""

        base, length = self.span(name)
        view = self.view
        require(bytes(view[base:base + 4]) == ea_terf.TERF_MAGIC,
                f"{name} does not open with {ea_terf.TERF_MAGIC!r}; this disc's audio "
                f"containers all do.")
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
        require("DIR1" in chunks and "DATA" in chunks,
                f"{name} has no DIR1 or DATA chunk; it is not a container this lane reads.")
        directory = chunks["DIR1"][0] + ea_terf.CHUNK_HEADER_SIZE
        data_tag = chunks["DATA"][0]
        out: List[Tuple[int, int, int]] = []
        for index in range(count):
            offset, size = struct.unpack_from("<II", view, directory + 8 * index)
            start = data_tag + offset
            if start + size > base + length:
                continue
            out.append((index, start, size))
        return tuple(out)

    def caches(self) -> Tuple[QklCache, ...]:
        """Every ``QL01`` preload cache under ``/DATA``, parsed once and kept."""

        if self._caches is None:
            found: List[QklCache] = []
            for name, entry in sorted(self.entries.items()):
                if not name.upper().endswith(".QKL"):
                    continue
                base, length = self.span(name)
                if bytes(self.view[base:base + 4]) != QKL_MAGIC:
                    continue
                found.append(parse_qkl(self.view, base, length,
                                       f"{containers.DATA_DIRECTORY}/{name}"))
            self._caches = tuple(found)
        return self._caches

    def copies(self) -> Dict[str, Dict[str, Any]]:
        """What the preload caches carry, in the shape the integrator swaps.

        Answered once per open image.  This is the only door the lane's
        cache-coherence code goes through; see :data:`_preload_copies`.
        """

        if self._copies is None:
            self._copies = _preload_copies(self.image)
        return self._copies

    def cache_bytes(self, cache_path: str) -> Tuple[int, bytes]:
        """``(absolute offset, bytes)`` of a cache named by its ISO path."""

        name = cache_path.rsplit("/", 1)[-1]
        base, _length = self.span(name)
        return base, self.container_bytes(name)

    def header_block_bytes(self, name: str) -> int:
        """How many bytes a cache's kind-0 copy of *name* covers.

        The container's header block runs to the end of the ``DATA`` chunk's own
        8-byte header [M] -- everything the loader needs to find a member, and
        nothing of the members themselves.
        """

        base, length = self.span(name)
        position = base
        while position + ea_terf.CHUNK_HEADER_SIZE <= base + length:
            tag = bytes(self.view[position:position + 4])
            size, = struct.unpack_from("<I", self.view, position + 4)
            if tag == ea_terf.DATA_MAGIC:
                return position - base + ea_terf.CHUNK_HEADER_SIZE
            if size <= 0:
                break
            position += size
        raise Refusal(f"{name} has no DATA chunk, so its header block cannot be measured.")

    def container_bytes(self, name: str) -> bytes:
        base, length = self.span(name)
        require(length <= REWRITE_LIMIT,
                f"{name} is {length:,} bytes and this lane rewrites a container in memory, "
                f"which it stops doing at {REWRITE_LIMIT:,}.")
        return bytes(self.view[base:base + length])


# --------------------------------------------------------------------------
# The preload caches: GAME.QKL and FE.QKL carry byte copies of some members
# --------------------------------------------------------------------------

#: Magic of the disc's two preload caches [M].
QKL_MAGIC = b"QL01"

#: What a ``DTLS`` entry's first byte means [M].
QKL_KIND_HEADER = 0
QKL_KIND_MEMBER = 1

#: One ``DTLS`` row is twelve bytes [M].
QKL_ENTRY_BYTES = 12

#: One ``FILS`` name is 48 bytes, NUL-padded [M].
QKL_NAME_BYTES = 48


@dataclass(frozen=True)
class QklCopy:
    """One thing a preload cache carries a byte copy of."""

    cache: str
    kind: int
    container: str
    member: int
    #: Absolute byte offset of the copy inside the image.
    offset: int


@dataclass(frozen=True)
class QklCache:
    """One ``QL01`` preload cache: which files it names and what it copies."""

    path: str
    base: int
    length: int
    payload_offset: int
    files: Tuple[str, ...]
    copies: Tuple[QklCopy, ...]

    def members_of(self, container: str) -> Dict[int, Tuple[QklCopy, ...]]:
        wanted = container.upper()
        out: Dict[int, List[QklCopy]] = {}
        for copy in self.copies:
            if copy.kind == QKL_KIND_MEMBER and copy.container.upper() == wanted:
                out.setdefault(copy.member, []).append(copy)
        return {member: tuple(items) for member, items in out.items()}

    def headers_of(self, container: str) -> Tuple[QklCopy, ...]:
        wanted = container.upper()
        return tuple(copy for copy in self.copies
                     if copy.kind == QKL_KIND_HEADER and copy.container.upper() == wanted)


def preload_copies(image: Any) -> Dict[str, Dict[str, Any]]:
    """Every byte copy the disc's ``QL01`` preload caches carry, by container.

    ``image`` is an opened disc (:func:`containers.open_disc`'s result).  The
    answer is::

        {"BGM.DAT": {"directory": ((cache, offset), ...),
                     "members": {0: ((cache, offset), ...), ...}}, ...}

    where *cache* is the cache's ISO path and *offset* the absolute byte offset
    of the copy inside the image.  Every container either cache names is
    present, not only the audio ones: a caller that rewrites a copy has to know
    whether some **other** container's entry points at the same offset, because
    the copies are deduplicated [M].

    Reads only.  The caches are 5.7 MB and 10.7 MB on the retail disc and are
    walked through a memory map rather than read into memory.
    """

    out: Dict[str, Dict[str, Any]] = {}
    entries = {entry.name: entry for entry in containers.data_files(image)}
    wanted = sorted(name for name in entries if name.upper().endswith(".QKL"))
    if not wanted:
        return out
    require(image.sector_size == iso_lib.SECTOR_USER_BYTES and not image.data_offset,
            f"{Path(image.path).name} is a raw-CD image; the preload caches are read "
            f"through a memory map, which needs the 2048-byte layout every PlayStation 2 "
            f"DVD uses.")
    with open(image.path, "rb") as handle:
        view = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            for name in wanted:
                entry = entries[name]
                base = iso_lib.extent_byte_offset(image, entry.lba, 0)
                length = int(entry.recorded_length)
                if base + length > len(view) or bytes(view[base:base + 4]) != QKL_MAGIC:
                    continue
                cache = parse_qkl(view, base, length,
                                  f"{containers.DATA_DIRECTORY}/{name}")
                for copy in cache.copies:
                    container = copy.container.upper()
                    row = out.setdefault(container, {"directory": [], "members": {}})
                    if copy.kind == QKL_KIND_HEADER:
                        row["directory"].append((copy.cache, copy.offset))
                    else:
                        row["members"].setdefault(copy.member, []).append(
                            (copy.cache, copy.offset))
        finally:
            view.close()
    return {container: {"directory": tuple(row["directory"]),
                        "members": {member: tuple(items)
                                    for member, items in sorted(row["members"].items())}}
            for container, row in sorted(out.items())}


#: The one name in this file that reads the preload caches.  The art branch has
#: landed a shared ``containers.preload_copies(image)`` with the same shape --
#: take the opened image, return, per container, the directory copies and the
#: member copies as ``(cache, offset)``.  When the two are merged this line
#: becomes ``_preload_copies = containers.preload_copies`` and nothing else in
#: this file changes: every call site goes through it.
_preload_copies = preload_copies


def parse_qkl(view: Any, base: int, length: int, path: str) -> QklCache:
    """The ``QL01`` cache at *base*: its file table and every copy it declares.

    The chain is ``QL01``, a ``u32`` offset of the first chunk, a ``u32`` offset
    of the payload, then ``FILS`` (48-byte names) and ``DTLS`` (12-byte rows)
    chunks, each ``tag`` + ``u32`` total size + ``u32`` count [M].
    """

    require(length >= 12 and bytes(view[base:base + 4]) == QKL_MAGIC,
            f"{path} does not open with {QKL_MAGIC!r}; it is not a preload cache.")
    first, payload = struct.unpack_from("<II", view, base + 4)
    require(12 <= first < payload <= length,
            f"{path} declares a chunk chain at {first} and a payload at {payload}, which "
            f"do not fit its {length} bytes.")
    names: List[str] = []
    copies: List[QklCopy] = []
    position = base + first
    while position + 12 <= base + payload:
        tag = bytes(view[position:position + 4])
        size, count = struct.unpack_from("<II", view, position + 4)
        if size <= 0 or position + size > base + payload:
            break
        if tag == b"FILS":
            for index in range(count):
                at = position + 12 + QKL_NAME_BYTES * index
                if at + QKL_NAME_BYTES > base + payload:
                    break
                raw = bytes(view[at:at + QKL_NAME_BYTES]).split(b"\x00")[0]
                names.append(raw.decode("latin-1"))
        elif tag == b"DTLS":
            for index in range(count):
                at = position + 12 + QKL_ENTRY_BYTES * index
                if at + QKL_ENTRY_BYTES > base + payload:
                    break
                kind = view[at]
                file_index = view[at + 2]
                member, offset = struct.unpack_from("<II", view, at + 4)
                if file_index >= len(names):
                    continue
                copies.append(QklCopy(path, int(kind), names[file_index], int(member),
                                      base + payload + int(offset)))
        position += size
    return QklCache(path, base, length, base + payload, tuple(names), tuple(copies))


# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------

def parse_key(key: str, what: str) -> Tuple[str, int, int]:
    """``container:member:index`` back into its three parts."""

    parts = str(key).split(":")
    if len(parts) != 3 or not parts[0]:
        raise Refusal(
            f"{key!r} does not name a {what}: a key is <container>:<member>:<index>, as "
            f"the catalogue writes it.")
    try:
        return parts[0], int(parts[1]), int(parts[2])
    except ValueError as exc:
        raise Refusal(
            f"{key!r} does not name a {what}: its member and index must be whole numbers, "
            f"as the catalogue writes them.") from exc


def _duration(rate: Optional[int], samples: int) -> str:
    if not rate:
        return f"{samples:,} samples"
    seconds = samples / float(rate)
    if seconds >= 60:
        return f"{int(seconds) // 60}m {seconds % 60:04.1f}s"
    return f"{seconds:.2f}s"


# --------------------------------------------------------------------------
# The streams lane
# --------------------------------------------------------------------------

class AudioStreamsLane:
    """Every ``SCHl`` stream on the disc: play, export, and replace what decodes."""

    lane_id = STREAMS_LANE_ID
    capability_id = STREAMS_CAPABILITY
    surface = "audio"
    page = "audio"
    title = "Music, effects and speech streams"
    classification = "offline-writer-proved"
    recipe_schema = STREAM_RECIPE_SCHEMA
    validators = (
        "tools/validate_madden09_ps2_audio.sh",
        "tools/validate_madden09_ps2_audio.bat",
    )
    #: A replacement is written into the container member it replaces and the
    #: image keeps its exact length, so the lane declares byte ranges.
    fixed_allocation = True

    # -- catalogue -----------------------------------------------------

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        started = time.monotonic()
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        totals = {"members": 0, "streams": 0, "decodable": 0, "speech": 0}
        per_container: Dict[str, Dict[str, Any]] = {}
        skipped: Dict[str, str] = {}
        refusals: Dict[str, int] = {}
        with _DiscAudio(Path(source)) as disc:
            for name, group, note in AUDIO_CONTAINERS:
                if not disc.has(name):
                    skipped[name] = "not on this image"
                    continue
                if progress is not None:
                    progress(f"{name}…")
                seen = {"members": 0, "streams": 0, "decodable": 0, "speech": 0,
                        "bytes": 0, "samples": 0}
                try:
                    members = disc.members(name)
                except Refusal as exc:
                    skipped[name] = str(exc)
                    continue
                for index, start, size in members:
                    if size < ea_schl.CHUNK_HEADER_SIZE:
                        continue
                    if bytes(disc.view[start:start + 4]) != ea_schl.SCHL_MAGIC:
                        continue
                    seen["members"] += 1
                    totals["members"] += 1
                    if progress is not None and totals["members"] % 512 == 0:
                        progress(f"{name}: {totals['members']} member(s) read…")
                    try:
                        streams = ea_schl.iter_streams(disc.view, start, start + size)
                    except ea_schl.SchlError as exc:
                        refusals[str(exc)[:120]] = refusals.get(str(exc)[:120], 0) + 1
                        continue
                    for stream in streams:
                        header = stream.header
                        seen["streams"] += 1
                        totals["streams"] += 1
                        seen["bytes"] += stream.length
                        seen["samples"] += header.sample_count
                        decodable = header.decodable and bool(header.sample_rate)
                        if decodable:
                            seen["decodable"] += 1
                            totals["decodable"] += 1
                        elif header.codec == ea_schl.CODEC_SPEECH:
                            seen["speech"] += 1
                            totals["speech"] += 1
                        row = {
                            "container": name,
                            "group": group,
                            "member": index,
                            "stream": stream.index,
                            "offset": stream.offset - start,
                            "bytes": stream.length,
                            "platform": header.platform,
                            "big_endian": header.big_endian,
                            "codec": header.codec,
                            "codec_name": header.codec_name,
                            "version": header.version,
                            "channels": header.channels,
                            "sample_rate": header.sample_rate,
                            "samples": header.sample_count,
                            "blocks": len(stream.blocks),
                            "declared_blocks": stream.declared_blocks,
                            "complete": stream.complete,
                            "decodable": decodable,
                            "duration": _duration(header.sample_rate, header.sample_count),
                            "file_name": self._file_name(name, index, stream.index),
                        }
                        if len(rows) < MAX_TARGETS:
                            rows.append(row)
                            targets.append(self._target(row, note))
                per_container[name] = seen
        elapsed = time.monotonic() - started
        document = {
            "schema": STREAM_CATALOG_SCHEMA,
            "source": str(source),
            "containers": [{"name": name, "group": group, "structure": note}
                           for name, group, note in AUDIO_CONTAINERS],
            "per_container": per_container,
            "members_read": totals["members"],
            "streams_seen": totals["streams"],
            "streams_decodable": totals["decodable"],
            "streams_speech_codec": totals["speech"],
            "rows_listed": len(rows),
            "targets_listed": len(targets),
            "targets_cap": MAX_TARGETS,
            "catalogue_seconds": round(elapsed, 3),
            "skipped": skipped,
            "not_read": refusals,
            "rows": rows,
            "speech_note": ea_schl.SPEECH_REFUSAL,
            "note": "Headers only: rates, channel counts, lengths and offsets. A sound is "
                    "decoded when you ask to hear or export one, and no audio is ever "
                    "stored in this catalogue.",
        }
        return Catalogue(STREAM_CATALOG_SCHEMA, self.lane_id, str(source),
                         tuple(targets), document)

    @staticmethod
    def _file_name(container: str, member: int, stream: int) -> str:
        stem = container.split(".")[0].lower()
        return f"{stem}-m{member:05d}-s{stream:02d}{WAV_SUFFIX}"

    def _target(self, row: Mapping[str, Any], structure: str) -> Target:
        detail = [row["duration"],
                  f"{row['sample_rate']:,} Hz" if row["sample_rate"] else "rate not declared",
                  "stereo" if row["channels"] == 2 else
                  ("mono" if row["channels"] == 1 else f"{row['channels']} channels"),
                  row["codec_name"]]
        if row["decodable"]:
            budget = (f"A replacement is re-encoded to {row['sample_rate']:,} Hz, "
                      f"{row['channels']} channel(s), and must fit this sound's "
                      f"{row['bytes']:,} stored bytes.")
            fields: Tuple[Field, ...] = (
                Field("wav", "wav", "Replacement sound",
                      "A WAV file. It is mixed to this sound's channel count and resampled "
                      "to its rate by linear interpolation, re-encoded as EA-XA ADPCM, and "
                      "must fit the bytes this sound already occupies; anything longer is "
                      "refused with the length it had to fit."),
                Field("codec", "note", "Codec", "How the disc stores this sound.",
                      read_only=True),
                Field("format", "note", "Format", "Rate, channels and length.",
                      read_only=True),
                Field("structure", "note", "What the container says",
                      "How this container organises its sounds, and what it does not say.",
                      read_only=True),
            )
        else:
            budget = ("This sound is not decoded here. Its rate, channels and length are "
                      "read from the disc; its audio is not.")
            fields = (
                Field("codec", "note", "Codec", ea_schl.SPEECH_REFUSAL, read_only=True),
                Field("format", "note", "Format", "Rate, channels and length.",
                      read_only=True),
                Field("structure", "note", "What the container says",
                      "How this container organises its sounds, and what it does not say.",
                      read_only=True),
            )
        return Target(
            key=f"{row['container']}:{row['member']}:{row['stream']}",
            label=f"{row['group']} · member {row['member']} · stream {row['stream']}",
            detail=" · ".join(detail),
            budget=budget,
            searchable=f"{row['container']} {row['group']} {row['member']} "
                       f"{row['codec_name']} {row['sample_rate']}",
            raw=dict(row, structure=structure),
            fields=fields,
        )

    # -- reading a sound -----------------------------------------------

    @staticmethod
    def _locate(disc: _DiscAudio, container: str, member: int, index: int
                ) -> Tuple[int, int, ea_schl.Stream]:
        for candidate, start, size in disc.members(container):
            if candidate != member:
                continue
            streams = ea_schl.iter_streams(disc.view, start, start + size)
            for stream in streams:
                if stream.index == index:
                    return start, size, stream
            raise Refusal(
                f"member {member} of {container} holds {len(streams)} stream(s), so there "
                f"is no stream {index}; re-run the catalogue.")
        raise Refusal(f"{container} on this image has no member {member}; re-run the "
                      f"catalogue.")

    def decode_wav(self, source: Path, target: Target) -> bytes:
        """The target's sound from the user's own disc, as 16-bit PCM WAV bytes."""

        return self.decode_wav_by_key(Path(source), target.key)

    def decode_wav_by_key(self, source: Path, key: str) -> bytes:
        """The same, addressed by key alone -- no catalogue needed."""

        container, member, index = parse_key(key, "sound")
        with _DiscAudio(Path(source)) as disc:
            _start, _size, stream = self._locate(disc, container, member, index)
            header = stream.header
            if header.codec == ea_schl.CODEC_SPEECH:
                raise Refusal(f"{key}: {ea_schl.SPEECH_REFUSAL}")
            require(header.decodable,
                    f"{key}: this sound declares codec {header.codec}, which this module "
                    f"does not decode.")
            require(bool(header.sample_rate),
                    f"{key}: this sound's header declares no sample rate, so there is no "
                    f"honest rate to write into a WAV.")
            pcm = ea_schl.decode_eaxa(disc.view, stream.blocks, header.channels,
                                      header.big_endian, header.version)
            return ea_schl.wav_bytes(pcm, int(header.sample_rate), header.channels)

    # -- the edit rule -------------------------------------------------

    @staticmethod
    def encoded_size(samples: int, channels: int, block_samples: int,
                     version: Optional[int] = None) -> int:
        """Exactly how many bytes a stream of *samples* would occupy once encoded.

        EA-XA's frame is a fixed 15 bytes for 28 samples, so this is arithmetic
        rather than a trial encode -- which is what lets ``check_edit`` answer
        instantly on a file the user has only just chosen.  A version-2 stream
        pays four more bytes per channel per block for the predictor values its
        blocks carry [M].
        """

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
            total += (ea_schl.CHUNK_HEADER_SIZE + 4 + 4 * channels + channels * run)
            left -= count
        #: header (worst case 40) + SCCl (12) + SCEl (8)
        return total + 40 + 12 + 8

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - {"wav"})
        if unknown:
            return (f"{target.key}: {', '.join(unknown)} is not something this lane takes; "
                    f"give a WAV, or nothing at all to export this sound as it is.")
        path = values.get("wav")
        if path in (None, ""):
            if not target.raw.get("decodable", False):
                return (f"{target.key}: {ea_schl.SPEECH_REFUSAL}")
            return None
        if not target.raw.get("decodable", False):
            return (f"{target.key}: this sound cannot be replaced, because it cannot be "
                    f"read: {ea_schl.SPEECH_REFUSAL}")
        try:
            payload = Path(str(path)).read_bytes()
        except OSError as exc:
            return f"{target.key}: {path} could not be read ({exc}); choose a WAV file."
        try:
            rate, channels, pcm = ea_schl.read_wav(payload)
        except Refusal as exc:
            return f"{target.key}: {exc}"
        wanted_rate = int(target.raw.get("sample_rate") or 0)
        wanted_channels = int(target.raw.get("channels") or 1)
        budget = int(target.raw.get("bytes") or 0)
        if not wanted_rate or not budget:
            return (f"{target.key}: this sound's header does not declare a rate or a "
                    f"length, so there is nothing to fit a replacement to.")
        samples = len(pcm) // (2 * channels)
        if samples <= 0:
            return f"{target.key}: that WAV carries no samples."
        converted = max(1, int(round(samples * wanted_rate / float(rate))))
        needed = self.encoded_size(converted, wanted_channels,
                                   ea_schl.DEFAULT_BLOCK_SAMPLES,
                                   target.raw.get("version"))
        if needed > budget:
            fits = budget * converted // max(1, needed)
            return (f"{target.key}: that WAV is {samples / float(rate):.2f}s and encodes to "
                    f"{needed:,} bytes, and this sound has {budget:,} to give. Trim it to "
                    f"about {fits / float(wanted_rate):.2f}s; the disc writer never grows "
                    f"a file.")
        return None

    # -- recipe / plan -------------------------------------------------

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: Dict[str, Any] = {"sound": edit.target_key}
            path = edit.values.get("wav")
            if path:
                row["wav"] = str(path)
            if edit.note:
                row["note"] = edit.note
            rows.append(row)
        return {"schema": STREAM_RECIPE_SCHEMA, "sounds": rows}

    def _entries(self, recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == STREAM_RECIPE_SCHEMA,
                f"recipe schema is "
                f"{recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, "
                f"expected {STREAM_RECIPE_SCHEMA}")
        rows = recipe.get("sounds")
        require(isinstance(rows, list) and rows,
                "a recipe must carry a non-empty 'sounds' list; choose at least one sound")
        seen: set = set()
        out = []
        for number, row in enumerate(rows):
            require(isinstance(row, Mapping) and isinstance(row.get("sound"), str)
                    and row["sound"], f"sound {number} must name the sound it replaces")
            require(set(row) <= {"sound", "wav", "note"},
                    f"sound {number} carries unknown keys")
            require(row["sound"] not in seen,
                    f"{row['sound']} appears twice; one sound is written once")
            seen.add(row["sound"])
            out.append(dict(row))
        return out

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        entries = self._entries(recipe)
        rows: List[Dict[str, Any]] = []
        ranges: List[DeclaredRange] = []
        by_container: Dict[str, int] = {}
        with _DiscAudio(Path(source)) as disc:
            for entry in entries:
                target = catalogue.target(entry["sound"])  # the catalogue's own refusal
                problem = self.check_edit(target, {k: v for k, v in entry.items()
                                                   if k in ("wav",)})
                require(problem is None, str(problem))
                container, member, index = parse_key(entry["sound"], "sound")
                base, _size, stream = self._locate(disc, container, member, index)
                start, length = disc.span(container)
                by_container[container] = length
                rows.append({
                    "sound": entry["sound"],
                    "container": container,
                    "member": member,
                    "stream": index,
                    "container_path": f"{containers.DATA_DIRECTORY}/{container}",
                    "stream_bytes": stream.length,
                    "sample_rate": stream.header.sample_rate,
                    "channels": stream.header.channels,
                    "samples": stream.header.sample_count,
                    "replacement": entry.get("wav"),
                    "file_name": target.raw.get("file_name"),
                })
            touched: Dict[str, set] = {}
            for row in rows:
                touched.setdefault(str(row["container"]), set()).add(int(row["member"]))
            cache_work = self._cache_work(disc, touched)
            for container, length in sorted(by_container.items()):
                self._declare(disc, ranges, container,
                              f"the container the replaced sound lives in")
            for path in sorted({cache for cache, _c, _m, _o in cache_work}):
                self._declare(disc, ranges, path.rsplit("/", 1)[-1],
                              "a preload cache carrying a byte copy of a replaced member")
        return Plan(self.lane_id, tuple(entry["sound"] for entry in entries),
                    tuple(ranges),
                    {"schema": STREAM_RECIPE_SCHEMA, "sounds": rows,
                     "preload_copies": [{"cache": cache, "container": container,
                                         "member": member, "offset": offset}
                                        for cache, container, member, offset in cache_work],
                     "note": "The image keeps its exact length; a member is replaced inside "
                             "the container's own extent, and every byte copy of that "
                             "member in GAME.QKL or FE.QKL is rewritten with it."})

    @staticmethod
    def _declare(disc: "_DiscAudio", ranges: List[DeclaredRange], name: str,
                 reason: str) -> None:
        """Declare a whole ``/DATA`` file's extent and its directory record's length."""

        start, length = disc.span(name)
        path = f"{containers.DATA_DIRECTORY}/{name}"
        ranges.append(DeclaredRange(start, length, f"extent:{path}: {reason}"))
        entry = iso_lib.find(disc.image, path)
        if entry is not None:
            # The writer rewrites the declared data length in the file's ISO9660
            # directory record: eight both-endian bytes at offset 10 of the
            # record [M].  Same value, same length -- but a range a build
            # touches is a range a plan declares.
            ranges.append(DeclaredRange(
                iso_lib.extent_byte_offset(disc.image, entry.parent_lba,
                                           entry.record_offset) + 10,
                8, f"dirrec_length:{path}"))

    @staticmethod
    def _cache_work(disc: "_DiscAudio",
                    touched: Mapping[str, Any]) -> Tuple[Tuple[str, str, int, int], ...]:
        """Every preload-cache copy that has to change with these members.

        The disc's two ``QL01`` caches carry byte copies of some container
        members and of some container header blocks [M], and the game loads the
        copy: an edit to a carried member that leaves the copy alone is an edit
        the game never sees.

        On the retail disc this fires on nothing, and that was measured rather
        than hoped for: ``BGM.DAT`` has a header copy and no member copies at
        all, and of ``SOUNDDAT.DAT``'s 43 carried members **not one** is among
        its 119 stream members -- 17 are ``BNKl`` banks, which this lane does
        not write, and 26 are neither [M].  The path is here because the
        measurement could have gone the other way and because a Deluxe rebuild
        may lay the caches out differently; CI proves it on a synthetic cache
        that does carry a replaced member.

        Copies are **deduplicated** -- two entries can share one offset [M] -- so
        an offset that another, untouched member also points at is refused
        rather than written: rewriting it would corrupt the sound that shares it.
        """

        everything = disc.copies()
        claims: Dict[int, List[Tuple[str, int]]] = {}
        for container, row in everything.items():
            for _cache, offset in row["directory"]:
                claims.setdefault(offset, []).append((container, -1))
            for member, items in row["members"].items():
                for _cache, offset in items:
                    claims.setdefault(offset, []).append((container, member))
        wanted: List[Tuple[str, str, int, int]] = []
        for container, members in sorted(touched.items()):
            carried = everything.get(container.upper(), {}).get("members", {})
            for member in sorted(members):
                for cache, offset in carried.get(int(member), ()):
                    others = [item for item in claims.get(offset, ())
                              if item != (container.upper(), int(member))]
                    if others:
                        raise Refusal(
                            f"{cache} stores its copy of {container} member {member} at "
                            f"the same offset as {others[0][0]} member {others[0][1]}, "
                            f"which this build does not change; rewriting it would "
                            f"corrupt that one. Nothing was written.")
                    wanted.append((cache, container.upper(), int(member), int(offset)))
        return tuple(wanted)

    # -- build ---------------------------------------------------------

    def _replacement_stream(self, disc: _DiscAudio, stream: ea_schl.Stream,
                            wav_path: Path) -> Tuple[bytes, Dict[str, Any]]:
        """The bytes that replace *stream*, padded to its exact stored length."""

        header = stream.header
        rate, channels, pcm = ea_schl.read_wav(Path(wav_path).read_bytes())
        wanted_rate = int(header.sample_rate or 0)
        require(wanted_rate > 0,
                "this sound's header declares no sample rate, so a replacement has no rate "
                "to be resampled to.")
        mixed = ea_schl.remix(pcm, channels, header.channels)
        resampled = ea_schl.resample(mixed, header.channels, rate, wanted_rate)
        built = ea_schl.build_stream(resampled, channels=header.channels,
                                     sample_rate=wanted_rate,
                                     big_endian=header.big_endian,
                                     version=header.version or 3,
                                     codec=header.codec)
        require(len(built) <= stream.length,
                f"that WAV encodes to {len(built):,} bytes and this sound has "
                f"{stream.length:,} to give; trim it. The disc writer never grows a file.")
        # The disc itself zero-pads between streams inside a member [M], so the
        # tail is written the way the game already finds it.
        padded = built + b"\x00" * (stream.length - len(built))
        report = {
            "wav": str(wav_path),
            "wav_sha256": _sha256(Path(wav_path).read_bytes()),
            "source_rate": rate,
            "source_channels": channels,
            "target_rate": wanted_rate,
            "target_channels": header.channels,
            "encoded_bytes": len(built),
            "padded_to": stream.length,
            "samples_written": len(resampled) // (2 * header.channels),
        }
        return padded, report

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        require(destination.resolve() != source.resolve(),
                f"{destination} is the source image; a build writes a NEW image and never "
                f"the disc it read.")
        require(not os.path.lexists(destination),
                f"destination {destination} already exists; refusing to overwrite")
        entries = self._entries(recipe)
        rows: List[Dict[str, Any]] = []
        replacements: Dict[str, Any] = {}
        room = Path(work_dir) if work_dir else destination.parent
        room.mkdir(parents=True, exist_ok=True)
        staged: List[Path] = []
        with _DiscAudio(source) as disc:
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for entry in entries:
                target = catalogue.target(entry["sound"])
                problem = self.check_edit(target, {k: v for k, v in entry.items()
                                                   if k in ("wav",)})
                require(problem is None, str(problem))
                container, member, index = parse_key(entry["sound"], "sound")
                require(entry.get("wav"),
                        f"{entry['sound']}: this lane writes a disc image, so every sound "
                        f"in the recipe must name the WAV that replaces it.")
                grouped.setdefault(container, []).append(
                    {"member": member, "stream": index, "wav": entry["wav"],
                     "sound": entry["sound"]})
            changed: Dict[str, Dict[int, Tuple[int, int]]] = {}
            rebuilt: Dict[str, bytes] = {}
            for container, jobs in sorted(grouped.items()):
                payload = bytearray(disc.container_bytes(container))
                header_block = disc.header_block_bytes(container)
                before = bytes(payload[:header_block])
                base, _length = disc.span(container)
                for job in sorted(jobs, key=lambda item: (item["member"], item["stream"])):
                    start, size, stream = self._locate(disc, container, job["member"],
                                                       job["stream"])
                    replacement, report = self._replacement_stream(
                        disc, stream, Path(job["wav"]))
                    at = (stream.offset - base)
                    payload[at:at + stream.length] = replacement
                    changed.setdefault(container.upper(), {})[int(job["member"])] = (
                        start - base, size)
                    rows.append({"sound": job["sound"], "container": container,
                                 "member": job["member"], "stream": job["stream"],
                                 "offset_in_container": at, **report})
                # A same-size replacement leaves the TERF header and directory
                # alone; the preload caches carry a copy of exactly those bytes,
                # so this is checked rather than assumed [M].
                require(bytes(payload[:header_block]) == before,
                        f"{container}'s header block changed, and GAME.QKL / FE.QKL carry "
                        f"a byte copy of it that this lane does not rewrite. Nothing was "
                        f"written.")
                rebuilt[container.upper()] = bytes(payload)
            cache_rows: List[Dict[str, Any]] = []
            cache_work = self._cache_work(disc, {name: set(members)
                                                 for name, members in changed.items()})
            caches: Dict[str, bytearray] = {}
            cache_bases: Dict[str, int] = {}
            for cache_path, container, member, offset in cache_work:
                cache = caches.get(cache_path)
                if cache is None:
                    base_at, blob = disc.cache_bytes(cache_path)
                    cache = bytearray(blob)
                    caches[cache_path] = cache
                    cache_bases[cache_path] = base_at
                cache_base = cache_bases[cache_path]
                offset_in_container, size = changed[container][member]
                fresh = rebuilt[container][offset_in_container:offset_in_container + size]
                at = offset - cache_base
                require(0 <= at and at + size <= len(cache),
                        f"{cache_path}'s copy of {container} member {member} runs past "
                        f"the end of the cache; nothing was written.")
                cache[at:at + size] = fresh
                cache_rows.append({"cache": cache_path, "container": container,
                                   "member": member, "offset": offset, "bytes": size})
            for container, blob in sorted(rebuilt.items()):
                path = room / f"{container}.rebuilt"
                require(not os.path.lexists(path),
                        f"the staging file {path} already exists; choose a clean work "
                        f"folder.")
                with open(path, "xb") as handle:
                    handle.write(blob)
                staged.append(path)
                replacements[f"{containers.DATA_DIRECTORY}/{container}"] = path
            for cache_path, blob in sorted(caches.items()):
                name = cache_path.rsplit("/", 1)[-1]
                path = room / f"{name}.rebuilt"
                require(not os.path.lexists(path),
                        f"the staging file {path} already exists; choose a clean work "
                        f"folder.")
                with open(path, "xb") as handle:
                    handle.write(bytes(blob))
                staged.append(path)
                replacements[cache_path] = path
        try:
            report = iso_writer.replace_files(source, destination, replacements)
        finally:
            for path in staged:
                try:
                    path.unlink()
                except OSError:  # pragma: no cover - best effort
                    pass
        declared = tuple(DeclaredRange(int(item.start), int(item.length), str(item.reason))
                         for item in report["declared_ranges"])
        document = {
            "schema": STREAM_WRITE_SCHEMA,
            "source": str(source),
            "destination": str(destination),
            "sounds": rows,
            "preload_copies": cache_rows,
            "writer": iso_writer.report_to_json(report),
            "note": "The source image was opened read-only. The destination is the same "
                    "length, byte for byte outside the ranges declared here.",
        }
        return Receipt(STREAM_WRITE_SCHEMA, self.lane_id, str(source), str(destination),
                       declared, document)

    # -- verify: independent of the writer -----------------------------

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        """Re-parse the destination, decode what was replaced, and compare.

        Nothing in here imports the writer or trusts the receipt's own numbers
        beyond the ranges it declares: the destination is opened as a disc in
        its own right, the replaced sound is found by key, decoded with the
        decoder, and matched against the user's WAV by signal-to-noise ratio.
        Every byte outside the declared ranges is compared with the source.
        """

        source, destination = Path(source), Path(destination)
        if not destination.is_file():
            return Verdict(False, f"Verification failed: {destination} is missing.")
        if source.stat().st_size != destination.stat().st_size:
            return Verdict(False,
                           f"Verification failed: the destination is "
                           f"{destination.stat().st_size:,} bytes and the source is "
                           f"{source.stat().st_size:,}; a bounded write never changes the "
                           f"length.")
        ranges = [(item.start, item.length) for item in receipt.declared_ranges]
        if not ranges:
            return Verdict(False, "Verification failed: the receipt declares no ranges.")
        outside = self._compare_outside(source, destination, ranges)
        if outside is not None:
            return Verdict(False,
                           f"Verification failed: byte 0x{outside:x} of the destination "
                           f"differs from the source and is outside every declared range.")
        rows = list(receipt.document.get("sounds", []))
        if not rows:
            return Verdict(False, "Verification failed: the receipt declares no sounds.")
        checked = []
        for row in rows:
            key = str(row.get("sound"))
            wav_path = row.get("wav")
            try:
                made = self.decode_wav_by_key(destination, key)
            except Refusal as exc:
                return Verdict(False, f"Verification failed: {key} could not be read back "
                                      f"from the destination ({exc}).")
            try:
                _rate, _channels, decoded = ea_schl.read_wav(made)
            except Refusal as exc:  # pragma: no cover - decode_wav always writes a WAV
                return Verdict(False, f"Verification failed: {exc}")
            if not wav_path or not Path(str(wav_path)).is_file():
                return Verdict(False, f"Verification failed: the WAV the receipt names for "
                                      f"{key} is not there to compare against.")
            rate, channels, wanted = ea_schl.read_wav(Path(str(wav_path)).read_bytes())
            wanted = ea_schl.resample(
                ea_schl.remix(wanted, channels, int(row.get("target_channels") or channels)),
                int(row.get("target_channels") or channels), rate,
                int(row.get("target_rate") or rate))
            length = min(len(wanted), len(decoded))
            ratio = ea_schl.signal_to_noise(wanted[:length], decoded[:length])
            if ratio is None:
                return Verdict(False, f"Verification failed: {key} decoded to silence.")
            if ratio < SNR_THRESHOLD_DB:
                return Verdict(False,
                               f"Verification failed: {key} decodes from the destination at "
                               f"{ratio:.1f} dB against the WAV that was written, below the "
                               f"{SNR_THRESHOLD_DB:.0f} dB this lane requires of its own "
                               f"encoder.")
            checked.append({"sound": key, "snr_db": round(ratio, 2),
                            "samples": length // 2})
        touched: Dict[str, set] = {}
        for row in rows:
            container = str(row.get("container") or parse_key(str(row.get("sound")),
                                                              "sound")[0])
            member = row.get("member")
            if member is None:
                member = parse_key(str(row.get("sound")), "sound")[1]
            touched.setdefault(container.upper(), set()).add(int(member))
        problem, copies = self._check_caches(destination, touched)
        if problem is not None:
            return Verdict(False, f"Verification failed: {problem}")
        return Verdict(
            True,
            f"{len(checked)} sound(s) decoded from the destination and matched the WAV that "
            f"was written (lowest {min(item['snr_db'] for item in checked):.1f} dB); "
            f"{copies} preload-cache copy or copies agree with the container they copy; "
            f"every byte outside the {len(ranges)} declared range(s) is identical to the "
            f"source.",
            {"result": "PASS", "sounds": checked, "declared_ranges": len(ranges),
             "preload_copies_checked": copies, "snr_threshold_db": SNR_THRESHOLD_DB})

    @staticmethod
    def _check_caches(destination: Path, touched: Mapping[str, Any]
                      ) -> Tuple[Optional[str], int]:
        """Every preload copy of a changed member, re-derived from the destination.

        The offsets are read out of the destination's own ``QL01`` caches rather
        than out of the receipt: a check that takes its addresses from the thing
        it is checking is not an independent one.  Both kinds are checked -- the
        member copies of everything this build changed, and the header-block
        copies of every container it touched, because a directory that moved
        would leave those stale.
        """

        checked = 0
        with _DiscAudio(destination) as disc:
            blocks: Dict[str, bytes] = {}
            members: Dict[str, Dict[int, Tuple[int, int]]] = {}
            for name in touched:
                try:
                    base, _length = disc.span(name)
                except Refusal:
                    return f"{name} is not on the destination image", checked
                blocks[name] = bytes(disc.view[base:base + disc.header_block_bytes(name)])
                members[name] = {index: (start, size)
                                 for index, start, size in disc.members(name)}
            for container, row in disc.copies().items():
                if container not in touched:
                    continue
                want = blocks[container]
                for cache_path, offset in row["directory"]:
                    if bytes(disc.view[offset:offset + len(want)]) != want:
                        return (f"{cache_path} carries a stale copy of {container}'s "
                                f"header block"), checked
                    checked += 1
                for member, items in row["members"].items():
                    if member not in touched[container]:
                        continue
                    start, size = members[container][member]
                    body = bytes(disc.view[start:start + size])
                    for cache_path, offset in items:
                        if bytes(disc.view[offset:offset + size]) != body:
                            return (f"{cache_path} carries a stale copy of {container} "
                                    f"member {member}"), checked
                        checked += 1
        return None, checked

    @staticmethod
    def _compare_outside(source: Path, destination: Path,
                         ranges: Sequence[Tuple[int, int]]) -> Optional[int]:
        """The first byte outside *ranges* that differs, or ``None``.

        Streamed a megabyte at a time: the images are 1.6 GB and reading two of
        them into memory to compare would cost more than the check.
        """

        spans = sorted((int(start), int(start) + int(length)) for start, length in ranges)
        merged: List[List[int]] = []
        for start, end in spans:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        block = 1 << 20
        with open(source, "rb") as left, open(destination, "rb") as right:
            position = 0
            while True:
                first = left.read(block)
                second = right.read(block)
                if not first and not second:
                    return None
                if first != second:
                    for index in range(min(len(first), len(second))):
                        if first[index] != second[index]:
                            offset = position + index
                            if not any(start <= offset < end for start, end in merged):
                                return offset
                position += len(first)

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "madden09-ps2-audio-synthetic.iso"
        path.write_bytes(build_synthetic_audio_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        room = Path(catalogue.source).parent
        target = None
        for candidate in catalogue.targets:
            if candidate.raw.get("decodable"):
                target = candidate
                break
        require(target is not None,
                "this catalogue lists no decodable sound, so there is no edit to prove")
        rate = int(target.raw.get("sample_rate") or 22050)
        channels = int(target.raw.get("channels") or 1)
        samples = max(ea_schl.EAXA_SAMPLES_PER_FRAME,
                      int(target.raw.get("samples") or 0) // 2)
        samples -= samples % ea_schl.EAXA_SAMPLES_PER_FRAME
        wav = room / "conformance-tone.wav"
        wav.write_bytes(ea_schl.wav_bytes(
            ea_schl.synthetic_pcm(samples, channels, sample_rate=rate, frequency=440.0),
            rate, channels))
        return (Edit(target.key, {"wav": str(wav)},
                     note="conformance: replace this sound with a computed tone"),)


#: How close a re-decoded replacement has to be to the WAV that made it before
#: :meth:`AudioStreamsLane.verify` will pass.  EA-XA is a 4-bit ADPCM: 30 dB is
#: comfortably below what it achieves on the retail streams (the synthetic tone
#: round-trips at 54 dB [M]) and comfortably above what a wrong decode, a wrong
#: byte order or a truncated write would ever reach.
SNR_THRESHOLD_DB = 30.0


# --------------------------------------------------------------------------
# The banks lane
# --------------------------------------------------------------------------

class AudioBanksLane:
    """The ``BNKl`` sound banks: catalogue and export. Nothing is written back."""

    lane_id = BANKS_LANE_ID
    capability_id = BANKS_CAPABILITY
    surface = "audio"
    page = "audio"
    title = "Sound banks"
    classification = "extract-only"
    recipe_schema = BANK_RECIPE_SCHEMA
    validators = (
        "tools/validate_madden09_ps2_audio.sh",
        "tools/validate_madden09_ps2_audio.bat",
    )
    #: The lane publishes WAV files rather than rewriting the source, so it
    #: declares artifacts instead of byte ranges.
    fixed_allocation = False

    NO_WRITER = (
        "A bank sound is not replaced here. 134 of the 967 sounds carry loop points (tags "
        "0x86 and 0x87: a frame-aligned start and an end inside the sound) whose handling "
        "by the PlayStation SPU no one here has mapped, 459 sounds declare no sample rate, "
        "and no rebuilt Madden 09 container has ever been booted. Export the WAV; a writer "
        "needs those three things first."
    )

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        started = time.monotonic()
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        totals = {"banks": 0, "sounds": 0, "playable": 0}
        skipped: Dict[str, str] = {}
        refusals: Dict[str, int] = {}
        with _DiscAudio(Path(source)) as disc:
            for name, group, note in BANK_CONTAINERS:
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
                        refusals[str(exc)[:120]] = refusals.get(str(exc)[:120], 0) + 1
                        continue
                    totals["banks"] += 1
                    if progress is not None and totals["banks"] % 64 == 0:
                        progress(f"{name}: {totals['banks']} bank(s) read…")
                    for sound in bank.sounds:
                        totals["sounds"] += 1
                        playable = sound.data_length > 0 and bool(sound.sample_rate)
                        if playable:
                            totals["playable"] += 1
                        row = {
                            "container": name,
                            "group": group,
                            "member": index,
                            "sound": sound.index,
                            "sounds_in_bank": len(bank.sounds),
                            "bank_version": bank.version,
                            "data_offset": sound.data_offset,
                            "bytes": sound.data_length,
                            "channels": sound.channels,
                            "sample_rate": sound.sample_rate,
                            "samples": sound.sample_count,
                            "codec_name": "Sony PlayStation ADPCM",
                            "loops": sound.header.value(ea_schl.TAG_LOOP_START) is not None,
                            "playable": playable,
                            "duration": _duration(sound.sample_rate, sound.sample_count),
                            "file_name": self._file_name(name, index, sound.index),
                        }
                        if len(rows) < MAX_TARGETS:
                            rows.append(row)
                            targets.append(self._target(row, note))
        elapsed = time.monotonic() - started
        document = {
            "schema": BANK_CATALOG_SCHEMA,
            "source": str(source),
            "containers": [{"name": name, "group": group, "structure": note}
                           for name, group, note in BANK_CONTAINERS],
            "banks_read": totals["banks"],
            "sounds_seen": totals["sounds"],
            "sounds_playable": totals["playable"],
            "rows_listed": len(rows),
            "targets_listed": len(targets),
            "targets_cap": MAX_TARGETS,
            "catalogue_seconds": round(elapsed, 3),
            "skipped": skipped,
            "not_read": refusals,
            "rows": rows,
            "writer_note": self.NO_WRITER,
            "note": "Directory only: offsets, lengths, rates and channel counts. A sound is "
                    "decoded when you ask to hear or export one.",
        }
        return Catalogue(BANK_CATALOG_SCHEMA, self.lane_id, str(source),
                         tuple(targets), document)

    @staticmethod
    def _file_name(container: str, member: int, sound: int) -> str:
        stem = container.split(".")[0].lower()
        return f"{stem}-bank{member:05d}-s{sound:02d}{WAV_SUFFIX}"

    def _target(self, row: Mapping[str, Any], structure: str) -> Target:
        detail = [row["duration"],
                  f"{row['sample_rate']:,} Hz" if row["sample_rate"] else "rate not declared",
                  "stereo" if row["channels"] == 2 else
                  ("mono" if row["channels"] == 1 else f"{row['channels']} channels"),
                  row["codec_name"]]
        if row["loops"]:
            detail.append("carries loop points")
        return Target(
            key=f"{row['container']}:{row['member']}:{row['sound']}",
            label=f"{row['group']} · bank {row['member']} · sound {row['sound']}",
            detail=" · ".join(detail),
            budget=f"Export writes {row['file_name']}. Nothing is written to your disc.",
            searchable=f"{row['container']} {row['group']} {row['member']} "
                       f"{row['sample_rate']}",
            raw=dict(row, structure=structure),
            fields=(
                Field("codec", "note", "Codec", "How the disc stores this sound.",
                      read_only=True),
                Field("format", "note", "Format", "Rate, channels and length.",
                      read_only=True),
                Field("writer", "note", "Why there is no replace here", self.NO_WRITER,
                      read_only=True),
                Field("structure", "note", "What the container says", structure,
                      read_only=True),
            ),
        )

    # -- reading a sound -----------------------------------------------

    def decode_wav(self, source: Path, target: Target) -> bytes:
        return self.decode_wav_by_key(Path(source), target.key)

    def decode_wav_by_key(self, source: Path, key: str) -> bytes:
        container, member, index = parse_key(key, "bank sound")
        with _DiscAudio(Path(source)) as disc:
            for candidate, start, size in disc.members(container):
                if candidate != member:
                    continue
                bank = ea_schl.parse_bank(disc.view, start, size)
                for sound in bank.sounds:
                    if sound.index != index:
                        continue
                    require(sound.data_length > 0 and bool(sound.sample_rate),
                            f"{key}: this sound declares no data offset or no rate, so "
                            f"there is nothing to decode.")
                    pcm = ea_schl.decode_bank_sound(disc.view, bank, sound)
                    return ea_schl.wav_bytes(pcm, int(sound.sample_rate), sound.channels)
                raise Refusal(f"bank {member} of {container} holds {len(bank.sounds)} "
                              f"sound(s), so there is no sound {index}.")
        raise Refusal(f"{container} on this image has no member {member}.")

    # -- plan / build / verify: an export, like the art lane -----------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values))
        if unknown:
            return (f"{target.key}: {', '.join(unknown)} is not something this lane takes. "
                    f"{self.NO_WRITER}")
        if not target.raw.get("playable", False):
            return (f"{target.key}: this sound declares no data offset or no rate, so it "
                    f"cannot be exported.")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: Dict[str, Any] = {"sound": edit.target_key}
            if edit.note:
                row["note"] = edit.note
            rows.append(row)
        return {"schema": BANK_RECIPE_SCHEMA, "sounds": rows}

    def _entries(self, recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == BANK_RECIPE_SCHEMA,
                f"recipe schema is "
                f"{recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, "
                f"expected {BANK_RECIPE_SCHEMA}")
        rows = recipe.get("sounds")
        require(isinstance(rows, list) and rows,
                "a recipe must carry a non-empty 'sounds' list; choose at least one sound "
                "to export")
        seen: set = set()
        out = []
        for number, row in enumerate(rows):
            require(isinstance(row, Mapping) and isinstance(row.get("sound"), str)
                    and row["sound"], f"sound {number} must name the sound it exports")
            require(set(row) <= {"sound", "note"}, f"sound {number} carries unknown keys")
            require(row["sound"] not in seen,
                    f"{row['sound']} appears twice; one sound is exported once")
            seen.add(row["sound"])
            out.append(dict(row))
        return out

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        entries = self._entries(recipe)
        rows = []
        for entry in entries:
            target = catalogue.target(entry["sound"])
            problem = self.check_edit(target, {})
            require(problem is None, str(problem))
            rows.append({"sound": entry["sound"],
                         "file_name": target.raw.get("file_name"),
                         "sample_rate": target.raw.get("sample_rate"),
                         "channels": target.raw.get("channels"),
                         "samples": target.raw.get("samples")})
        return Plan(self.lane_id, tuple(entry["sound"] for entry in entries), (),
                    {"schema": BANK_RECIPE_SCHEMA, "sounds": rows,
                     "writer_note": self.NO_WRITER})

    @staticmethod
    def export_root_for(destination: Path) -> Path:
        destination = Path(destination)
        return destination.with_name(destination.name + "-sounds")

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        require(destination.resolve() != source.resolve(),
                f"{destination} is the source image; a build writes a NEW manifest and "
                f"never the disc.")
        require(not os.path.lexists(destination),
                f"destination {destination} already exists; refusing to overwrite")
        export_root = self.export_root_for(destination)
        require(not os.path.lexists(export_root),
                f"the export folder {export_root} already exists; choose a destination "
                f"whose folder is free")
        planned = self.plan(source, recipe, catalogue)
        export_root.mkdir(parents=True)
        artifacts: List[Artifact] = []
        rows: List[Dict[str, Any]] = []
        for row in planned.document["sounds"]:
            wav = self.decode_wav_by_key(source, str(row["sound"]))
            path = export_root / str(row["file_name"])
            with open(path, "xb") as handle:
                handle.write(wav)
            digest = _sha256(wav)
            artifacts.append(Artifact(str(path), digest, "wav"))
            rows.append({**row, "sha256": digest, "bytes": len(wav),
                         "measure": ea_schl.measure(wav[44:])})
        readme = export_root / "HOW-TO.txt"
        readme.write_text(self._how_to(len(rows)), encoding="utf-8", newline="\n")
        artifacts.append(Artifact(str(readme), _sha256(readme.read_bytes()), "text"))
        document = {
            "schema": BANK_WRITE_SCHEMA,
            "source": str(source),
            "destination": str(destination),
            "export_folder": export_root.as_posix(),
            "sounds": rows,
            "writer_note": self.NO_WRITER,
            "note": "Exported WAVs. Your disc image was opened read-only and is unchanged.",
        }
        payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with open(destination, "xb") as handle:
            handle.write(payload)
        artifacts.insert(0, Artifact(str(destination), _sha256(payload), "export-manifest"))
        return Receipt(BANK_WRITE_SCHEMA, self.lane_id, str(source), str(destination), (),
                       document, artifacts=tuple(artifacts))

    def _how_to(self, count: int) -> str:
        return (
            "Madden NFL 09 (PlayStation 2) — exported sound-bank audio\n"
            "=========================================================\n"
            "\n"
            f"{count} WAV file(s), decoded from your own disc image. Your image was\n"
            "opened read-only and is unchanged.\n"
            "\n"
            "These are 16-bit PCM at the rate the disc declares for each sound. They\n"
            "were Sony PlayStation ADPCM on the disc; the decoder that read them\n"
            "matches ffmpeg sample for sample on every bank sound of the retail disc.\n"
            "\n"
            "What you cannot do yet, and why:\n"
            "\n"
            "  * Put one back. " + self.NO_WRITER + "\n"
            "\n"
            "The Music page's streams are a different matter: those can be replaced,\n"
            "and the studio builds a new image and checks it for you.\n"
        )

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        """Re-decode every exported sound from the user's disc, independently."""

        destination = Path(destination)
        if not destination.is_file():
            return Verdict(False, f"Verification failed: the manifest {destination} is "
                                  f"missing.")
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
        rows = receipt.document.get("sounds", [])
        if not rows:
            return Verdict(False, "Verification failed: the receipt declares no sounds.")
        checked = 0
        for row in rows:
            try:
                expected = _sha256(self.decode_wav_by_key(Path(source), str(row["sound"])))
            except Refusal as exc:
                return Verdict(False, f"Verification failed: {exc}")
            if expected != row.get("sha256"):
                return Verdict(False, f"Verification failed: {row['sound']} decodes from "
                                      f"this disc to a different sound than the receipt "
                                      f"recorded.")
            checked += 1
        return Verdict(True,
                       f"{checked} sound(s) re-decoded from the source and matched byte for "
                       f"byte; {len(declared)} declared file(s) present and nothing else.",
                       {"result": "PASS", "sounds": checked, "files": len(declared)})

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "madden09-ps2-audio-synthetic.iso"
        if not path.exists():
            path.write_bytes(build_synthetic_audio_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        for target in catalogue.targets:
            if target.raw.get("playable"):
                return (Edit(target.key, {},
                             note="conformance: export this bank sound as it is"),)
        raise Refusal("this catalogue lists no playable bank sound, so there is no edit to "
                      "prove")


# --------------------------------------------------------------------------
# The synthetic disc CI proves both lanes on
# --------------------------------------------------------------------------

def build_synthetic_audio_disc() -> bytes:
    """A tiny ``SLUS-21770``-shaped image carrying computed audio containers.

    ``BGM.DAT`` gets three ``SCHl`` members -- a big-endian stereo stream, a
    little-endian mono one, and a member holding **two** streams back to back,
    because a member with more than one stream is the shape 11,342 of the
    disc's members have and a lane that only ever saw one would not be proved
    on it.  ``SOUNDDAT.DAT`` gets two ``BNKl`` banks and a stream that declares
    the speech codec, so the refusal has something real to refuse.  Every byte
    is computed here; nothing is copied from a disc.
    """

    return _synthetic_disc()


def _synthetic_container_header_block(blob: bytes) -> int:
    position = 0
    while position + ea_terf.CHUNK_HEADER_SIZE <= len(blob):
        tag = blob[position:position + 4]
        size, = struct.unpack_from("<I", blob, position + 4)
        if tag == ea_terf.DATA_MAGIC:
            return position + ea_terf.CHUNK_HEADER_SIZE
        if size <= 0:
            break
        position += size
    raise Refusal("that synthetic container has no DATA chunk")


def build_synthetic_qkl(copies: Sequence[Tuple[int, str, int, bytes]]) -> bytes:
    """A ``QL01`` preload cache carrying *copies*, in the shape the disc's have.

    ``copies`` is ``(kind, container file name, member index, bytes)``.  CI needs
    one so the cache-rewriting half of the writer is proved rather than
    described: without it the synthetic disc has no cache, and the check that
    catches a stale copy never runs.
    """

    names = sorted({name for _kind, name, _member, _blob in copies})
    files = b"".join(name.encode("ascii").ljust(QKL_NAME_BYTES, b"\x00") for name in names)
    payload = bytearray()
    rows = bytearray()
    for kind, name, member, blob in copies:
        rows += bytes([kind, 0, names.index(name), 0])
        rows += struct.pack("<II", member, len(payload))
        payload += blob
        while len(payload) % 16:
            payload += b"\x00"
    fils = b"FILS" + struct.pack("<II", 12 + len(files), len(names)) + files
    dtls = b"DTLS" + struct.pack("<II", 12 + len(rows), len(copies)) + bytes(rows)
    head = QKL_MAGIC + struct.pack("<II", 12, 12 + len(fils) + len(dtls))
    return head + fils + dtls + bytes(payload)


def _synthetic_disc() -> bytes:
    first = ea_schl.synthetic_stream(samples=4480, channels=2, sample_rate=22050,
                                     big_endian=True, codec=None)
    # Version 2 on purpose: its blocks carry their own predictor values and 13
    # streams of the retail disc are shaped that way [M], so CI decodes both.
    second = ea_schl.synthetic_stream(samples=2240, channels=1, sample_rate=28000,
                                      big_endian=False, codec=ea_schl.CODEC_EAXA,
                                      version=2)
    third = ea_schl.synthetic_stream(samples=1120, channels=1, sample_rate=22050,
                                     big_endian=True, codec=ea_schl.CODEC_EAXA)
    fourth = ea_schl.synthetic_stream(samples=1680, channels=2, sample_rate=44100,
                                      big_endian=True, codec=ea_schl.CODEC_EAXA)
    pair = third + b"\x00" * ((-len(third)) % 64) + fourth
    music = ea_terf.build_terf([first, second, pair], chunk="DATA")
    effects = ea_terf.build_terf(
        [ea_schl.synthetic_bank(sounds=2, samples=1120, sample_rate=24000, channels=1),
         ea_schl.synthetic_bank(sounds=1, samples=560, sample_rate=32000, channels=2),
         ea_schl.synthetic_speech_stream(samples=2240, sample_rate=36000)],
        chunk="DATA")
    # The retail disc's GAME.QKL and FE.QKL carry byte copies of some members
    # and of some container header blocks [M]; the synthetic disc carries a
    # cache of the same shape so the writer's obligation to keep those copies
    # in step is proved here rather than only described.
    parsed = ea_terf.parse_terf(music)
    header_block = _synthetic_container_header_block(music)
    member_zero = music[parsed.data_offset + parsed.members[0].offset:
                        parsed.data_offset + parsed.members[0].offset
                        + parsed.members[0].stored_size]
    cache = build_synthetic_qkl((
        (QKL_KIND_HEADER, "bgm.dat", 0, music[:header_block]),
        (QKL_KIND_MEMBER, "bgm.dat", 0, member_zero),
    ))
    boot = (b"BOOT2 = cdrom0:\\%s;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n"
            % containers.BOOT_FILE.encode("ascii"))
    return iso_lib.build_synthetic_iso(
        files=[(b"SYSTEM.CNF;1", boot),
               (containers.BOOT_FILE.encode("ascii") + b";1", b"\x7fELF" + bytes(4092))],
        sub_name=b"DATA",
        sub_files=[(b"BGM.DAT;1", music), (b"SOUNDDAT.DAT;1", effects),
                   (b"GAME.QKL;1", cache)],
    )


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.audio_lane",
        description="Catalogue and export a Madden NFL 09 (PS2) disc's SCHl streams and "
                    "BNKl sound banks.")
    parser.add_argument("--source", required=True, help="the user's own SLUS-21770 image")
    parser.add_argument("--banks", action="store_true",
                        help="catalogue the BNKl banks instead of the SCHl streams")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--export", metavar="MANIFEST.json",
                        help="write this NEW manifest and the WAVs beside it (banks only)")
    parser.add_argument("--limit", type=int, default=6,
                        help="how many sounds --export writes (default 6)")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane: Any = AudioBanksLane() if arguments.banks else AudioStreamsLane()
    try:
        catalogue = lane.build_catalogue(
            Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
        if arguments.export:
            require(arguments.banks, "--export writes WAVs and only the banks lane exports; "
                                     "add --banks.")
            playable = [target for target in catalogue.targets if target.raw.get("playable")]
            edits = tuple(Edit(target.key, {})
                          for target in playable[:max(1, arguments.limit)])
            recipe = lane.compose_recipe(edits)
            manifest = Path(arguments.export)
            receipt = lane.build(Path(arguments.source), manifest, recipe, catalogue)
            verdict = lane.verify(Path(arguments.source), manifest, receipt)
            print(f"EXPORT files={len(receipt.artifacts)} "
                  f"verify={'PASS' if verdict.passed else 'FAIL'} — {verdict.summary}")
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8", newline="\n")
    if arguments.banks:
        print("AUDIO_BANKS banks=%d sounds=%d playable=%d listed=%d seconds=%.1f"
              % (document["banks_read"], document["sounds_seen"],
                 document["sounds_playable"], document["targets_listed"],
                 document["catalogue_seconds"]))
    else:
        print("AUDIO_STREAMS members=%d streams=%d decodable=%d speech=%d listed=%d "
              "seconds=%.1f"
              % (document["members_read"], document["streams_seen"],
                 document["streams_decodable"], document["streams_speech_codec"],
                 document["targets_listed"], document["catalogue_seconds"]))
    return 0


__all__ = [
    "AUDIO_CONTAINERS",
    "BANKS_CAPABILITY",
    "BANKS_LANE_ID",
    "BANK_CATALOG_SCHEMA",
    "BANK_RECIPE_SCHEMA",
    "BANK_WRITE_SCHEMA",
    "BANK_CONTAINERS",
    "AudioBanksLane",
    "AudioStreamsLane",
    "MAX_TARGETS",
    "REWRITE_LIMIT",
    "SNR_THRESHOLD_DB",
    "STREAMS_CAPABILITY",
    "STREAMS_LANE_ID",
    "STREAM_CATALOG_SCHEMA",
    "STREAM_RECIPE_SCHEMA",
    "STREAM_WRITE_SCHEMA",
    "QKL_KIND_HEADER",
    "QKL_KIND_MEMBER",
    "QKL_MAGIC",
    "QklCache",
    "QklCopy",
    "build_synthetic_audio_disc",
    "build_synthetic_qkl",
    "preload_copies",
    "parse_qkl",
    "parse_key",
]


if __name__ == "__main__":
    raise SystemExit(_main())
