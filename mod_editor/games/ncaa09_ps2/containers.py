"""Reading NCAA Football 09 (PS2) ``/DATA`` containers out of the user's own disc.

Every lane in this module starts here.  The disc's ``/DATA/*.DAT`` files are EA
``TERF`` containers -- the same family Madden NFL 09 ships, and the same shared
reader opens them (:mod:`mod_editor.games._formats.ea_terf`) -- so this file is
only the *game-specific* half: which disc this is, which files to walk, how big
a container this module will hold in memory, how to recover a container the
disc's own directory record understates, and how to build a synthetic disc the
conformance harness can prove a lane on without any game data.

A game never imports another game (``mod_editor/games/_formats/__init__.py``),
so nothing here reaches into the Madden 09 package; what the two discs share
they share through ``_formats``.

**Evidence tags.**  **[M]** measured on the disc this box holds; **[S]**
sourced; **[A]** assumed.

**Retail-free.**  Names, offsets, lengths, counts and digests only.  No member
payload and no decoded pixel reaches the repository, and nothing here writes to
the user's image.

Standard library only; importable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_terf
from mod_editor.games.contract import Refusal

_ROOT = Path(__file__).resolve().parents[3]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ps2_iso9660 as iso_lib  # noqa: E402

# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

#: The disc serial this module reads [M].
SERIAL = "SLUS-21752"

#: The boot file ``SYSTEM.CNF`` names, in ISO9660 spelling [M].
BOOT_FILE = "SLUS_217.52"

#: SHA-256 of the boot ELF on the USA disc [M]: 7,294,796 bytes.
RETAIL_BOOT_ELF_SHA256 = "dc1b30895ad548d1ee960368998bb0e61be3c8a611c54490f1599c6e9c1f71ee"

#: SHA-256 of the whole USA image [M]: 2,175,041,536 bytes, 166 files / 9 dirs.
RETAIL_IMAGE_SHA256 = "e15ba4d0a3a7139f4e60023c6e045c306d95aca62eb5d483cb8414b4b9fb7de8"

#: PCSX2's CRC for that executable [M].  Recorded, never used as a key.
RETAIL_ELF_CRC = "B0157E6C"

#: What this module calls the one image it recognises.
RETAIL_EDITION = "retail"

#: Where the containers live.
DATA_DIRECTORY = "/DATA"

#: How large a container this module will hold in memory.  Chosen to cover
#: ``UNIFORM.DAT`` -- 127,942,528 bytes, the kit art the Uniforms page is about
#: [M] -- and to stop short of the four the lanes do not need whole:
#: ``STADIUMS.DAT`` 197 MB, ``MOVIEDAT.DAT`` 333 MB, ``SOUNDDAT.DAT`` 539 MB and
#: ``SPCHDATA.DAT`` 631 MB [M].  Those four are listed with their size, unread;
#: the audio lane reaches the two it needs through a memory map instead, which
#: costs no copy at all.  "Listed but not read" is a state the catalogue names
#: rather than a silent gap.
CONTAINER_SIZE_LIMIT = 144 * 1024 * 1024

#: How much of a file is probed for the length its own chunk chain declares.
PROBE_BYTES = 1 << 16

# --------------------------------------------------------------------------
# The containers each page is about [M]
# --------------------------------------------------------------------------

#: The league database container: one league database plus 432 per-team roster
#: databases, ``RLE1``-packed [M].
LEAGUE_CONTAINER = "LEAGUE.DAT"

#: The playbook container: 137 databases at members 4..140 [M].
GAME_DATA_CONTAINER = "GAMEDATA.DAT"

#: The fresh-dynasty template container: 11 databases [M].
TEMPLATE_CONTAINER = "TEMPLATE.DAT"

#: The one bare database on the disc, with no container around it [M].
STREAM_DATABASE_FILE = "STRMDATA.DB"

#: Kit and equipment art [M]: 1,200 / 888 / 396 ``MMAP`` members.
UNIFORM_CONTAINERS = ("UNIFORM.DAT", "PLADATA.DAT", "UIS_GEAR.DAT")

#: Player and coach face art [M]: 64 and 18 ``MMAP`` members.
FACE_CONTAINERS = ("PLYRFACE.DAT", "COACFACE.DAT")

#: The audio containers [M].  The first three carry ``SCHl`` streams, the
#: fourth the ``BNKl`` banks, and two of them are past
#: :data:`CONTAINER_SIZE_LIMIT` and are listed unread.
AUDIO_CONTAINERS = ("FESNDDAT.DAT", "SOUNDDAT.DAT", "SPCHDATA.DAT", "CMNTDATA.DAT")

#: The containers holding ``TEXT`` members [M]: 1,238 / 7 / 1 / 1.
TEXT_CONTAINERS = ("EXAMS.DAT", "JERSEY.DAT", "OSDKSTRN.DAT", "GAMEDATA.DAT")

#: The three preload caches.  NCAA 09 ships three where Madden 09 ships two [M].
PRELOAD_CACHES = ("FE.QKL", "GAME.QKL", "PL.QKL")

QKL_MAGIC = b"QL01"
QKL_FILE_LIST = b"FILS"
QKL_DETAILS = b"DTLS"
QKL_DATA = b"DATA"
QKL_CHUNK_HEADER = 8
QKL_ENTRY_STRIDE = 12
QKL_NAME_STRIDE = 48
QKL_MAX_NAMES = 4096
PRELOAD_KIND_HEADER = 0
PRELOAD_KIND_MEMBER = 1


class DiscError(Refusal):
    """This module could not read what it was pointed at; the sentence says why."""


@dataclass(frozen=True)
class DataFile:
    """One file under ``/DATA``, as the disc's directory record describes it."""

    name: str
    path: str
    lba: int
    recorded_length: int


def open_disc(path: Path) -> Any:
    """Open the user's image read-only, or refuse with one sentence."""

    try:
        return iso_lib.open_image(str(path))
    except (iso_lib.Iso9660Error, OSError, ValueError) as exc:
        raise DiscError(
            str(exc).strip()
            or f"{path} could not be opened as a PlayStation 2 disc image."
        ) from exc


def data_files(image: Any) -> Tuple[DataFile, ...]:
    """Every file under ``/DATA``, in the disc's own order.

    A disc with no ``/DATA`` directory is refused here rather than yielding an
    empty catalogue, because "there is nothing there" and "this is not the
    right disc" must not read the same.
    """

    found: List[DataFile] = []
    prefix = DATA_DIRECTORY + "/"
    for entry in iso_lib.iter_entries(image):
        if entry.is_dir or not entry.path.startswith(prefix):
            continue
        found.append(DataFile(
            name=entry.path[len(prefix):],
            path=entry.path,
            lba=int(entry.lba),
            recorded_length=int(entry.length),
        ))
    if not found:
        raise DiscError(
            f"this image holds no files under {DATA_DIRECTORY}, so it is not an "
            f"NCAA Football 09 PlayStation 2 disc. Choose the {SERIAL} image."
        )
    return tuple(found)


def _read_extent(image: Any, lba: int, wanted: int) -> Optional[bytes]:
    """*wanted* bytes from the extent at *lba*, or ``None`` if they are not there.

    Addressed through the reader rather than by multiplying by a sector size: a
    raw-CD image's logical blocks are not contiguous in the file.
    """

    out = bytearray()
    try:
        with open(image.path, "rb") as handle:
            block = 0
            while len(out) < wanted:
                handle.seek(iso_lib.extent_byte_offset(image, lba + block, 0))
                chunk = handle.read(min(iso_lib.SECTOR_USER_BYTES, wanted - len(out)))
                if not chunk:
                    return None
                out += chunk
                block += 1
    except (OSError, ValueError):
        return None
    return bytes(out[:wanted]) if len(out) >= wanted else None


def read_file(image: Any, entry: DataFile,
              *, limit: Optional[int] = CONTAINER_SIZE_LIMIT) -> bytes:
    """One ``/DATA`` file's bytes, honouring what the container declares.

    ISO9660 extents are whole sectors, so a container recorded short is still
    entirely on the disc; reading the directory record's length loses every
    member past the cut.  When the file's own chunk chain declares more than the
    record does, the extent is re-read to the declared length.  A file too large
    for *limit* is refused by name and size, never truncated.
    """

    if limit is not None and entry.recorded_length > limit:
        raise DiscError(
            f"{entry.path} is {entry.recorded_length:,} bytes; this lane reads a "
            f"container into memory and stops at {limit:,}. It is listed with its "
            f"size and left unread."
        )
    iso_entry = iso_lib.find(image, entry.path)
    if iso_entry is None:
        raise DiscError(f"{entry.path} is no longer on this image; re-open the disc.")
    try:
        data = iso_lib.read_file(image, iso_entry)
    except (iso_lib.Iso9660Error, OSError, ValueError) as exc:
        raise DiscError(
            str(exc).strip() or f"{entry.path} could not be read off this image."
        ) from exc
    try:
        wanted = ea_terf.declared_length(data[:PROBE_BYTES])
    except ea_terf.TerfError:
        return data
    if wanted <= len(data):
        return data
    if limit is not None and wanted > limit:
        raise DiscError(
            f"{entry.path} declares itself {wanted:,} bytes; this lane stops at "
            f"{limit:,}. It is listed with its size and left unread."
        )
    recovered = _read_extent(image, entry.lba, wanted)
    return data if recovered is None else recovered


# --------------------------------------------------------------------------
# What a file is
# --------------------------------------------------------------------------

KIND_TERF = "TERF"
KIND_TDB = "TDB"
KIND_OTHER = "other"
KIND_UNREAD = "not-read"


def classify(image: Any, entry: DataFile) -> str:
    """``TERF``, ``TDB``, ``other`` or ``not-read``, from the file's first bytes."""

    iso_entry = iso_lib.find(image, entry.path)
    if iso_entry is None:
        return KIND_UNREAD
    head = _read_extent(image, entry.lba, 16)
    if head is None:
        return KIND_UNREAD
    if head[:4] == ea_terf.TERF_MAGIC:
        return KIND_TERF
    if head[:2] == b"DB":
        return KIND_TDB
    return KIND_OTHER


@dataclass(frozen=True)
class ContainerReport:
    """One ``/DATA`` file as a lane catalogues it: metadata, never payload."""

    name: str
    path: str
    kind: str
    recorded_length: int
    read_length: Optional[int] = None
    chunk_chain: str = ""
    alignment: int = 0
    member_count: int = 0
    codec_histogram: Optional[Dict[str, int]] = None
    format_histogram: Optional[Dict[str, int]] = None
    layout_violations: Tuple[str, ...] = ()
    note: str = ""

    def document(self) -> Dict[str, Any]:
        """A JSON-safe row.  Sizes and counts; nothing read out of a member."""

        return {
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
            "recorded_length": self.recorded_length,
            "read_length": self.read_length,
            "chunk_chain": self.chunk_chain,
            "alignment": self.alignment,
            "member_count": self.member_count,
            "codecs": dict(self.codec_histogram or {}),
            "formats": dict(self.format_histogram or {}),
            "layout_violations": list(self.layout_violations),
            "note": self.note,
        }


def describe_container(
    image: Any,
    entry: DataFile,
    *,
    limit: Optional[int] = CONTAINER_SIZE_LIMIT,
    with_formats: bool = True,
) -> Tuple[ContainerReport, Optional[ea_terf.TerfContainer]]:
    """Walk one ``/DATA`` file and say what it holds, without reading a pixel.

    Returns the report and, when the file was a container small enough to read,
    the parsed container so a caller can go on to its members without a second
    read.  A refusal from the reader becomes a ``note`` on the row: one
    unreadable container must not empty the whole catalogue.
    """

    kind = classify(image, entry)
    if kind != KIND_TERF:
        note = ""
        if kind == KIND_TDB:
            note = "a bare EA TDB database rather than a TERF container."
        return ContainerReport(name=entry.name, path=entry.path, kind=kind,
                               recorded_length=entry.recorded_length, note=note), None
    try:
        data = read_file(image, entry, limit=limit)
    except DiscError as exc:
        return ContainerReport(name=entry.name, path=entry.path, kind=KIND_UNREAD,
                               recorded_length=entry.recorded_length,
                               note=str(exc)), None
    try:
        container = ea_terf.parse_terf(data, allow_size_mismatch=True)
    except ea_terf.TerfError as exc:
        return ContainerReport(name=entry.name, path=entry.path, kind=KIND_UNREAD,
                               recorded_length=entry.recorded_length,
                               read_length=len(data), note=str(exc)), None
    formats: Dict[str, int] = {}
    note_formats = ""
    if with_formats:
        try:
            formats = container.format_histogram()
        except ea_terf.TerfError as exc:
            formats = {}
            note_formats = str(exc)
    return ContainerReport(
        name=entry.name,
        path=entry.path,
        kind=KIND_TERF,
        recorded_length=entry.recorded_length,
        read_length=len(data),
        chunk_chain=container.chunk_chain,
        alignment=int(container.alignment),
        member_count=len(container),
        codec_histogram=container.codec_histogram(),
        format_histogram=formats,
        layout_violations=tuple(container.layout_violations()),
        note=note_formats,
    ), container


def load_container(image: Any, name: str, *,
                   limit: Optional[int] = CONTAINER_SIZE_LIMIT) -> ea_terf.TerfContainer:
    """One named ``/DATA`` container, parsed, or a refusal naming the fix."""

    wanted = f"{DATA_DIRECTORY}/{name}"
    for entry in data_files(image):
        if entry.path == wanted:
            data = read_file(image, entry, limit=limit)
            try:
                return ea_terf.parse_terf(data, allow_size_mismatch=True)
            except ea_terf.TerfError as exc:
                raise DiscError(str(exc)) from exc
    raise DiscError(
        f"this image holds no {wanted}; it is not an NCAA Football 09 PlayStation 2 "
        f"disc, or the container has been removed. Choose the {SERIAL} image."
    )


def member_uncached(container: ea_terf.TerfContainer, index: int) -> bytes:
    """One member, whole, without putting it in the container's cache.

    :meth:`TerfContainer.member` caches what it unpacks, which is right for a
    lane that comes back to the same member and wrong for one walking 455
    members in a row, where the cache is a pile nobody reads twice.  Asking for
    exactly the declared size returns the whole member and skips the cache.
    """

    return container.member(index, max_output=container.members[index].decompressed_size)


# --------------------------------------------------------------------------
# The preload caches
# --------------------------------------------------------------------------
#
# ``FE.QKL``, ``GAME.QKL`` and ``PL.QKL`` are not containers: they are **byte
# copies** of things that already exist elsewhere on the disc, laid out so the
# game can stream them in one read.  Two kinds of copy are carried [M]: a
# container's first ``data_offset`` bytes (its header and directories), and a
# member exactly as it is stored.  Measured on this disc: 552 copies across the
# three caches, every one byte-identical to what it copies [M].
#
# **This is load-bearing for any writer.**  An edit that changes a member's
# stored size or codec moves the directory, and a cache that still carries the
# old directory hands the game the wrong offsets.


@dataclass(frozen=True)
class PreloadCopy:
    """One ``DTLS`` entry: what is copied, from where, to where in the payload."""

    cache: str
    kind: int
    container: str
    member: Optional[int]
    offset: int

    @property
    def is_header(self) -> bool:
        return self.kind == PRELOAD_KIND_HEADER

    def document(self) -> Dict[str, Any]:
        return {"cache": self.cache, "kind": self.kind, "container": self.container,
                "member": self.member, "offset": self.offset}


def parse_preload_cache(data: bytes, cache: str) -> Tuple[PreloadCopy, ...]:
    """The copies a ``QL01`` cache carries, or a refusal naming what was found.

    The format, measured on this disc [M]::

        QL01 chunk   8-byte tag+size, then a u32 payload offset at +0x08
        FILS chunk   tag, size, u32 count, then count x 48-byte NUL-padded names
        DTLS chunk   tag, size, u32 count, then count x 12-byte entries
        DATA chunk   tag, size 0; the payload runs from the QL01 offset to EOF

    A ``DTLS`` entry is ``u8 kind, u8, u8 file index, u8, u32 member, u32
    offset``: *kind* 0 is a header copy and 1 a member copy, *file index* points
    into ``FILS``, and *offset* is relative to the payload.
    """

    if len(data) < 16 or data[:4] != QKL_MAGIC:
        raise DiscError(
            f"{cache} starts with {bytes(data[:4])!r}, not {QKL_MAGIC!r}; it is not "
            f"one of this disc's preload caches."
        )
    names: List[str] = []
    entries: List[PreloadCopy] = []
    position = 0
    while position + QKL_CHUNK_HEADER <= len(data):
        tag = bytes(data[position:position + 4])
        size, = struct.unpack_from("<I", data, position + 4)
        body = position + QKL_CHUNK_HEADER
        if tag == QKL_FILE_LIST:
            count, = struct.unpack_from("<I", data, body)
            if count > QKL_MAX_NAMES:
                raise DiscError(
                    f"{cache} declares {count} preloaded file name(s); this reader "
                    f"stops at {QKL_MAX_NAMES}, so the cache is being read at the "
                    f"wrong offset."
                )
            for index in range(count):
                start = body + 4 + index * QKL_NAME_STRIDE
                raw = bytes(data[start:start + QKL_NAME_STRIDE])
                names.append(raw.split(b"\x00", 1)[0].decode("latin-1"))
        elif tag == QKL_DETAILS:
            count, = struct.unpack_from("<I", data, body)
            for index in range(count):
                start = body + 4 + index * QKL_ENTRY_STRIDE
                if start + QKL_ENTRY_STRIDE > len(data):
                    break
                kind = data[start]
                file_index = data[start + 2]
                member, offset = struct.unpack_from("<II", data, start + 4)
                entries.append(PreloadCopy(
                    cache=cache,
                    kind=int(kind),
                    container=names[file_index] if file_index < len(names) else "",
                    member=None if kind == PRELOAD_KIND_HEADER else int(member),
                    offset=int(offset),
                ))
        elif tag == QKL_DATA:
            break
        if size < QKL_CHUNK_HEADER:
            break
        position += size
    return tuple(entries)


def preload_names(image: Any) -> Dict[str, Tuple[str, ...]]:
    """``{cache: (container name, …)}`` read off the user's own image.

    A writer asks this before it touches a container: a container a cache names
    is one whose directory the cache may be carrying a stale copy of.
    """

    out: Dict[str, Tuple[str, ...]] = {}
    for entry in data_files(image):
        if entry.name.upper() not in PRELOAD_CACHES:
            continue
        try:
            head = read_file(image, entry)
        except DiscError:
            continue
        try:
            copies = parse_preload_cache(head, entry.name)
        except DiscError:
            continue
        seen: List[str] = []
        for copy in copies:
            if copy.container and copy.container not in seen:
                seen.append(copy.container)
        out[entry.name] = tuple(seen)
    return out


# --------------------------------------------------------------------------
# What CI proves a lane on: a synthetic disc, built from the formats' own rules
# --------------------------------------------------------------------------
#
# No game data may enter this repository, so every lane's conformance run works
# off an image built here.  Each piece is computed, never sampled: an ``MMAP``
# whose indices are a ramp (a wrong stride shows as a diagonal), a ``TEXT``
# member of NUL-separated ASCII, an ``SCHl`` stream and a ``BNKl`` bank from
# ``ea_schl``'s own builders, and a TDB from ``ea_tdb.build_tdb``.

SYNTHETIC_TEXT_LINES = (
    "SYNTHETIC STRING BANK ENTRY NUMBER ONE",
    "SYNTHETIC STRING BANK ENTRY NUMBER TWO",
    "SYNTHETIC STRING BANK ENTRY NUMBER THREE",
)


def synthetic_text_member(lines: Sequence[str] = SYNTHETIC_TEXT_LINES) -> bytes:
    """A ``TEXT`` member: NUL-terminated printable strings, as the format has them."""

    body = b"".join(line.encode("latin-1", "replace") + b"\x00" for line in lines)
    return body if body else b"\x00"


def synthetic_mmap(width: int, height: int, *, seed: int = 0, version: int = 2) -> bytes:
    """An ``MMAP`` member whose wrapper header is what the shared reader reads.

    Only the fields :func:`ea_terf.parse_mmap_header` names are modelled --
    magic, version, the ``00 01 02 03`` marker, the payload and header sizes,
    the three ascending sizes and the dimensions that follow the header --
    because that is all this module's texture census asks of a member.  The
    pixel decoder that would make this a PNG lives in the Madden 09 package,
    and a game never imports another game, so nothing here pretends to decode
    it and nothing here needs real pixels.
    """

    body = bytes((seed + x * 7 + y * 13) & 0xFF
                 for y in range(height) for x in range(width))
    header = bytearray(0x40)
    header[0:4] = ea_terf.MMAP_MAGIC
    struct.pack_into("<I", header, 0x04, int(version))
    header[0x08:0x0C] = b"\x00\x01\x02\x03"
    struct.pack_into("<I", header, 0x14, len(body))
    struct.pack_into("<I", header, 0x18, ea_terf.MMAP_HEADER_SIZE)
    struct.pack_into("<III", header, 0x1C, 0x40, 0x40 + len(body) // 2, 0x40 + len(body))
    struct.pack_into("<HH", header, 0x28, int(width), int(height))
    struct.pack_into("<I", header, 0x30, int(width) * int(height))
    return bytes(header) + body


def build_synthetic_preload_cache(
        payload: Sequence[Tuple[str, int, Optional[int], bytes]],
        *, alignment: int = 64) -> bytes:
    """A ``QL01`` cache carrying the copies given, in the shape the disc has.

    *payload* is ``(container name, kind, member or None, bytes)`` per copy.
    Built from the format's rules so CI proves the cache-coherence step without
    a game: a container whose directory a cache copies cannot be rewritten
    without rewriting the copy.
    """

    names: List[str] = []
    for container, _kind, _member, _blob in payload:
        if container.upper() not in names:
            names.append(container.upper())
    files = struct.pack("<I", len(names)) + b"".join(
        name.encode("latin-1").ljust(QKL_NAME_STRIDE, b"\x00") for name in names)
    files_chunk = QKL_FILE_LIST + struct.pack("<I", QKL_CHUNK_HEADER + len(files)) + files

    body = bytearray()
    offsets: List[int] = []
    for _container, _kind, _member, blob in payload:
        while len(body) % alignment:
            body.append(0)
        offsets.append(len(body))
        body += blob
    entries = struct.pack("<I", len(payload))
    for (container, kind, member, _blob), offset in zip(payload, offsets):
        entries += struct.pack("<BBBBII", kind, 0, names.index(container.upper()), 0,
                               0 if member is None else member, offset)
    entries_chunk = QKL_DETAILS + struct.pack("<I", QKL_CHUNK_HEADER + len(entries)) + entries

    head_length = 12 + len(files_chunk) + len(entries_chunk) + QKL_CHUNK_HEADER
    out = bytearray()
    out += QKL_MAGIC + struct.pack("<II", 12, head_length)
    out += files_chunk
    out += entries_chunk
    out += QKL_DATA + struct.pack("<I", 0)
    out += body
    return bytes(out)


def synthetic_tdb(*, tables: int = 2) -> bytes:
    """A small EA TDB, built by the shared writer, with its four CRCs correct."""

    from mod_editor.games._formats import ea_tdb

    described = [
        ("TEAM", [("TGID", ea_tdb.FIELD_UINT, 9), ("TDNA", ea_tdb.FIELD_STRING, 176),
                  ("TSNA", ea_tdb.FIELD_STRING, 56)],
         [{"TGID": 1, "TDNA": "SYNTHETIC", "TSNA": "SYN"},
          {"TGID": 2, "TDNA": "FIXTURE", "TSNA": "FIX"}]),
        ("PLAY", [("PGID", ea_tdb.FIELD_UINT, 16), ("PPOS", ea_tdb.FIELD_UINT, 5),
                  ("POVR", ea_tdb.FIELD_UINT, 5), ("PJEN", ea_tdb.FIELD_UINT, 7)],
         [{"PGID": 100, "PPOS": 0, "POVR": 20, "PJEN": 7},
          {"PGID": 101, "PPOS": 1, "POVR": 18, "PJEN": 22}]),
    ][:max(1, tables)]
    # ``build_tdb`` leaves the four checksum slots zero; a fixture whose CRCs
    # are wrong would let a CRC check pass by never being exercised.
    return ea_tdb.recompute_crcs(ea_tdb.build_tdb(described))


def build_synthetic_disc(*, tdb_members: Optional[Sequence[bytes]] = None,
                         stream_database: Optional[bytes] = None,
                         preload_caches: bool = True,
                         audio_members: Optional[Sequence[bytes]] = None) -> bytes:
    """A tiny ``SLUS-21752``-shaped image carrying this module's containers.

    ``LEAGUE.DAT`` is built as a ``COMP`` container whose members are stored --
    the chain the real container uses, with the codec this module does not
    re-encode -- and ``GAMEDATA.DAT``, ``UNIFORM.DAT`` and ``SOUNDDAT.DAT`` as
    plain ``DATA`` containers.  Every byte comes from ``ea_terf.build_terf`` and
    the builders above; no game data is involved, which is what lets the
    conformance harness run a lane on a machine that owns no disc.
    """

    from mod_editor.games._formats import ea_schl

    league_members = list(tdb_members) if tdb_members is not None else [
        synthetic_tdb(tables=2), synthetic_tdb(tables=1)]
    league = ea_terf.build_terf(league_members, chunk="COMP",
                                codecs=[ea_terf.CODEC_STORED] * len(league_members))
    playbooks = ea_terf.build_terf([synthetic_tdb(tables=1),
                                    synthetic_text_member()], chunk="DATA")
    templates = ea_terf.build_terf([synthetic_tdb(tables=2), b""], chunk="DATA")
    uniforms = ea_terf.build_terf([synthetic_mmap(16, 16, seed=1),
                                   synthetic_mmap(8, 8, seed=2),
                                   b""], chunk="DATA")
    if audio_members is None:
        audio_members = [ea_schl.synthetic_stream(), ea_schl.synthetic_bank()]
    sounds = ea_terf.build_terf(list(audio_members), chunk="DATA")
    texts = ea_terf.build_terf([synthetic_text_member()], chunk="DATA")

    directory = league[:ea_terf.parse_terf(league).data_offset]
    caches = [
        (PRELOAD_CACHES[0], build_synthetic_preload_cache([
            (LEAGUE_CONTAINER, PRELOAD_KIND_HEADER, None, directory)])),
        (PRELOAD_CACHES[1], build_synthetic_preload_cache([
            (LEAGUE_CONTAINER, PRELOAD_KIND_HEADER, None, directory),
            (GAME_DATA_CONTAINER, PRELOAD_KIND_MEMBER, 1,
             ea_terf.parse_terf(playbooks).stored(1))])),
        (PRELOAD_CACHES[2], build_synthetic_preload_cache([
            (LEAGUE_CONTAINER, PRELOAD_KIND_HEADER, None, directory)])),
    ]

    boot = b"BOOT2 = cdrom0:\\%s;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n" % BOOT_FILE.encode("ascii")
    sub_files = [
        (LEAGUE_CONTAINER.encode("ascii") + b";1", league),
        (GAME_DATA_CONTAINER.encode("ascii") + b";1", playbooks),
        (TEMPLATE_CONTAINER.encode("ascii") + b";1", templates),
        (UNIFORM_CONTAINERS[0].encode("ascii") + b";1", uniforms),
        (AUDIO_CONTAINERS[1].encode("ascii") + b";1", sounds),
        (TEXT_CONTAINERS[0].encode("ascii") + b";1", texts),
    ]
    if preload_caches:
        sub_files += [(name.encode("ascii") + b";1", blob) for name, blob in caches]
    if stream_database is not None:
        sub_files.append((STREAM_DATABASE_FILE.encode("ascii") + b";1", stream_database))
    return iso_lib.build_synthetic_iso(
        files=[(b"SYSTEM.CNF;1", boot),
               (BOOT_FILE.encode("ascii") + b";1", b"\x7fELF" + bytes(4092))],
        sub_name=b"DATA",
        sub_files=sub_files,
    )


__all__ = [
    "AUDIO_CONTAINERS", "BOOT_FILE", "CONTAINER_SIZE_LIMIT", "ContainerReport",
    "DATA_DIRECTORY", "DataFile", "DiscError", "FACE_CONTAINERS",
    "GAME_DATA_CONTAINER", "KIND_OTHER", "KIND_TDB", "KIND_TERF", "KIND_UNREAD",
    "LEAGUE_CONTAINER", "PRELOAD_CACHES", "PRELOAD_KIND_HEADER",
    "PRELOAD_KIND_MEMBER", "PreloadCopy", "RETAIL_BOOT_ELF_SHA256",
    "RETAIL_EDITION", "RETAIL_ELF_CRC", "RETAIL_IMAGE_SHA256", "SERIAL",
    "STREAM_DATABASE_FILE", "TEMPLATE_CONTAINER", "TEXT_CONTAINERS",
    "UNIFORM_CONTAINERS", "classify", "data_files", "describe_container",
    "load_container", "member_uncached", "open_disc", "parse_preload_cache",
    "preload_names", "read_file", "build_synthetic_disc",
    "build_synthetic_preload_cache", "synthetic_mmap", "synthetic_tdb",
    "synthetic_text_member", "SYNTHETIC_TEXT_LINES",
]
