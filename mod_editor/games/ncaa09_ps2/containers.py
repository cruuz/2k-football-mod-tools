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

from mod_editor.games._formats import ea_ql01, ea_terf, mmap_art
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

#: Player and coach face art [M]: 80 and 18 members in all, of which 64 and 18
#: carry an ``MMAP`` wrapper header the texture census reads.
FACE_CONTAINERS = ("PLYRFACE.DAT", "COACFACE.DAT")

#: Stadium art [M]: ``STADATA.DAT`` 1,289 members (1,195 ``MMAP``, 45 ``SMF``,
#: 4 ``DMF``) and ``UIS_STAD.DAT`` 245 stored members.
STADIUM_CONTAINERS = ("STADATA.DAT", "UIS_STAD.DAT")

#: Field and create-team art [M]: ``FLDDATA.DAT`` 1,422 members and
#: ``UIS_TMLO.DAT`` 399 school logos, all ``LZH1``.
FIELD_ART_CONTAINERS = ("FLDDATA.DAT", "UIS_TMLO.DAT")

#: Presentation art [M]: crowd (``FANDATA.DAT``, 257 stored members), the
#: mascot and trophy set (``MSCTDATA.DAT``, 641) and the load screens
#: (``LOADDATA.DAT``, 46, thirty of them 854x480).
PRESENTATION_CONTAINERS = ("FANDATA.DAT", "MSCTDATA.DAT", "LOADDATA.DAT")

#: The audio containers [M].  The first three carry ``SCHl`` streams, the
#: fourth the ``BNKl`` banks, and two of them are past
#: :data:`CONTAINER_SIZE_LIMIT` and are listed unread.
AUDIO_CONTAINERS = ("FESNDDAT.DAT", "SOUNDDAT.DAT", "SPCHDATA.DAT", "CMNTDATA.DAT")

#: The containers holding ``TEXT`` members [M]: 1,238 / 7 / 1 / 1.
TEXT_CONTAINERS = ("EXAMS.DAT", "JERSEY.DAT", "OSDKSTRN.DAT", "GAMEDATA.DAT")

#: The three preload caches.  NCAA 09 ships three where Madden 09 ships two [M].
PRELOAD_CACHES = ("FE.QKL", "GAME.QKL", "PL.QKL")

#: The ``QL01`` format itself is shared: :mod:`ea_ql01` reads both this disc's
#: three caches and Madden 09's two, and these names are re-exported so a lane
#: written against either game reads the same words.
QKL_MAGIC = ea_ql01.QL01_MAGIC
QKL_FILE_LIST = ea_ql01.QL01_FILS
QKL_DETAILS = ea_ql01.QL01_DTLS
QKL_DATA = ea_ql01.QL01_DATA_TAG
QKL_CHUNK_HEADER = ea_ql01.QL01_CHUNK_HEADER
QKL_ENTRY_STRIDE = ea_ql01.QL01_ENTRY_STRIDE
QKL_NAME_STRIDE = ea_ql01.QL01_NAME_STRIDE
QKL_MAX_NAMES = ea_ql01.QL01_MAX_FILES
PRELOAD_KIND_HEADER = ea_ql01.PRELOAD_KIND_HEADER
PRELOAD_KIND_MEMBER = ea_ql01.PRELOAD_KIND_MEMBER


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
# Writing: a container bounded to the space the disc gave it
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class WritableContainer:
    """One container, bounded to the space the disc gave it, ready to rewrite."""

    entry: DataFile
    #: Exactly ``entry.recorded_length`` bytes.
    data: bytes
    parsed: ea_terf.TerfContainer
    #: What the container's own chunk chain says its length is.
    declared_length: int

    @property
    def recorded_short(self) -> bool:
        """Whether the container declares more than the disc records for it."""

        return self.declared_length > len(self.data)

    def member_end(self, index: int) -> int:
        """Where member *index*'s stored bytes end, as a file offset."""

        member = self.parsed.members[index]
        return self.parsed.data_offset + member.offset + member.stored_size

    def require_member_inside(self, index: int) -> None:
        """Refuse a member whose bytes lie past what the disc records.

        No member on this disc does -- every container's recorded length equals
        the length it declares [M] -- but an edit that named one would be an
        edit the writer could only satisfy by growing the file, and the
        sentence says so with both sizes in it.
        """

        if not 0 <= index < self.parsed.member_count:
            raise DiscError(
                f"{self.entry.path} has no member {index}: it holds "
                f"{self.parsed.member_count} (0..{self.parsed.member_count - 1})."
            )
        end = self.member_end(index)
        if end > len(self.data):
            raise DiscError(
                f"{self.entry.path} member {index} ends at byte {end:,}, and this "
                f"image's own directory records the container as {len(self.data):,} "
                f"bytes against the {self.declared_length:,} it declares; rewriting a "
                f"member out there would have to grow the file, which this lane will "
                f"not do."
            )


def open_for_rewrite(image: Any, entry: DataFile, *,
                     limit: Optional[int] = CONTAINER_SIZE_LIMIT) -> WritableContainer:
    """A container bounded to its ISO9660 record, or one sentence saying why not.

    The writer-side twin of :func:`read_file`.  ``read_file`` recovers a
    recorded-short container to its declared length so a *reader* sees every
    member; this stops at the record, because the record is the allocation a
    fixed-allocation writer has, and hands the caller everything it needs to
    stay inside it.
    """

    data = read_file(image, entry, limit=limit)
    try:
        declared = ea_terf.declared_length(data[:PROBE_BYTES])
    except ea_terf.TerfError:
        declared = len(data)
    if len(data) > entry.recorded_length:
        data = data[:entry.recorded_length]
    if len(data) < entry.recorded_length:
        raise DiscError(
            f"{entry.path} is {entry.recorded_length:,} bytes in this image's own "
            f"directory and only {len(data):,} could be read off it; the image is "
            f"truncated and nothing here writes into it."
        )
    try:
        parsed = ea_terf.parse_terf(data, allow_size_mismatch=True)
    except ea_terf.TerfError as exc:
        raise DiscError(
            f"{entry.path} is {entry.recorded_length:,} bytes in this image's own "
            f"directory and declares {declared:,}; reading it as a container inside "
            f"the recorded length failed: {exc}"
        ) from exc
    beyond = [member.index for member in parsed.members
              if member.stored_size
              and parsed.data_offset + member.offset + member.stored_size > len(data)]
    if beyond:
        raise DiscError(
            f"{entry.path} is {entry.recorded_length:,} bytes in this image's own "
            f"directory and declares {declared:,}, and member {beyond[0]} carries "
            f"bytes past the recorded end; a rewrite would have to grow the file, "
            f"which this lane will not do."
        )
    return WritableContainer(entry=entry, data=data, parsed=parsed,
                             declared_length=declared)


def members_of_format(container: ea_terf.TerfContainer, wanted: str, *,
                      progress: Optional[Any] = None):
    """``(index, payload)`` for every member whose decompressed bytes are *wanted*.

    Walks in index order and skips an empty member without unpacking it, so a
    455-member container costs one pass and no member is held twice.
    """

    for index in range(container.member_count):
        if container.members[index].stored_size == 0:
            continue
        try:
            payload = member_uncached(container, index)
        except (ea_terf.TerfError, ValueError):
            continue
        if ea_terf.identify_member(payload) != wanted:
            continue
        yield index, payload


# --------------------------------------------------------------------------
# The preload caches
# --------------------------------------------------------------------------
#
# ``FE.QKL``, ``GAME.QKL`` and ``PL.QKL`` are not containers: they are **byte
# copies** of things that already exist elsewhere on the disc, laid out so the
# game can stream them in one read.  Two kinds of copy are carried [M]: a
# container's first ``data_offset`` bytes (its header and directories), and a
# member exactly as it is stored.  Measured on this disc: **564 copies across
# the three caches** -- 81 container directories and 483 members, naming 47
# containers [M].
#
# **This is load-bearing for any writer.**  An edit that changes a member's
# stored size or codec moves the directory, and a cache that still carries the
# old directory hands the game the wrong offsets.  ``LEAGUE.DAT`` -- the
# container the roster and identity lanes write -- has **2 directory copies and
# 2 member copies** in ``PL.QKL`` [M], and ``PLYRFACE.DAT`` has 2 and 72, so on
# this disc the member path is the ordinary case and not the exception it is on
# Madden 09.
#
# The format is shared (:mod:`mod_editor.games._formats.ea_ql01`); what is here
# is which caches this disc ships and how to read one off this image.

#: Re-exported so a lane written against either game names the same type.
PreloadCopy = ea_ql01.PreloadCopy
ContainerPreload = ea_ql01.ContainerPreload


def parse_preload_cache(data: bytes, cache: str) -> Tuple[Any, ...]:
    """The copies a ``QL01`` cache carries, or a refusal naming what was found."""

    try:
        return ea_ql01.parse_cache(data, cache)
    except ea_ql01.Ql01Error as exc:
        raise DiscError(str(exc)) from exc


class _CopySource:
    """What :func:`ea_ql01.collect` asks of this image, answered read-only."""

    def __init__(self, image: Any) -> None:
        self._image = image
        self._entries = {entry.name.upper(): entry for entry in data_files(image)}

    def names(self) -> Tuple[str, ...]:
        return tuple(self._entries)

    def shape(self, name: str) -> Optional[Any]:
        entry = self._entries.get(name.upper())
        if entry is None:
            return None
        head = _read_extent(self._image, entry.lba,
                            min(PROBE_BYTES, entry.recorded_length))
        return None if head is None else ea_ql01.container_shape(head)

    def bytes_at(self, name: str, start: int, length: int) -> Optional[bytes]:
        entry = self._entries.get(name.upper())
        if entry is None:
            return None
        whole = _read_extent(self._image, entry.lba, start + length)
        return None if whole is None else whole[start:start + length]

    def cache_bytes(self, name: str) -> Optional[bytes]:
        entry = self._entries.get(name.upper())
        if entry is None:
            return None
        try:
            return read_file(self._image, entry, limit=None)
        except DiscError:
            return None


def preload_names(image: Any) -> Dict[str, Tuple[str, ...]]:
    """``{cache: (container name, ...)}`` read off the user's own image.

    The conservative floor a writer asks before it touches a container: a
    container a cache names is one whose directory the cache may be carrying a
    stale copy of.  :func:`preload_copies` is the exact answer; this is the one
    that still works when a cache cannot be walked.
    """

    out: Dict[str, Tuple[str, ...]] = {}
    for entry in data_files(image):
        if entry.name.upper() not in PRELOAD_CACHES:
            continue
        try:
            head = read_file(image, entry, limit=None)
            out[entry.name] = ea_ql01.cache_names(head, entry.name)
        except (DiscError, ea_ql01.Ql01Error):
            continue
    return out


def preload_copies(image: Any, *, caches: Sequence[str] = PRELOAD_CACHES
                   ) -> Dict[str, Any]:
    """``container name -> ContainerPreload`` for every cache on this image.

    The one function every lane that writes a container calls, so the coherence
    rule lives in one place.  Every copy is filed under the container whose
    bytes it **is**, which for a row at a container boundary is not always the
    one its ``DTLS`` row names; :func:`ea_ql01.attribute` measures rather than
    guesses.
    """

    try:
        return ea_ql01.collect(caches, _CopySource(image))
    except ea_ql01.Ql01Error as exc:
        raise DiscError(str(exc)) from exc


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

def synthetic_league_database() -> bytes:
    """A league database in this disc's shape: the identity tables, empty of data.

    ``TEAM``, ``CONF``, ``DIVI``, ``STAD`` and ``COCH`` at the widths this disc
    declares, so the identity lane's budgets and its bit packing are exercised
    on a fixture rather than on a game.  Names are invented, numbers are a
    counting ramp, and the four checksums are written from the result's own
    bytes.
    """

    from mod_editor.games._formats import ea_tdb

    return ea_tdb.recompute_crcs(ea_tdb.build_tdb((
        ("TEAM",
         (("TGID", ea_tdb.FIELD_UINT, 9),
          ("TDNA", ea_tdb.FIELD_STRING, 176),
          ("TMNA", ea_tdb.FIELD_STRING, 144),
          ("TSNA", ea_tdb.FIELD_STRING, 56),
          ("TPID", ea_tdb.FIELD_UINT, 7),
          ("CGID", ea_tdb.FIELD_UINT, 5),
          ("DGID", ea_tdb.FIELD_UINT, 4)),
         ({"TGID": 1, "TDNA": "SYNTHETIC ONE", "TMNA": "Synthetic A",
           "TSNA": "SYN", "TPID": 3, "CGID": 1, "DGID": 0},
          {"TGID": 2, "TDNA": "SYNTHETIC TWO", "TMNA": "Synthetic B",
           "TSNA": "SYB", "TPID": 9, "CGID": 1, "DGID": 1})),
        ("CONF",
         (("CGID", ea_tdb.FIELD_UINT, 5),
          ("LGID", ea_tdb.FIELD_UINT, 16),
          ("CNAM", ea_tdb.FIELD_STRING, 160),
          ("NCcl", ea_tdb.FIELD_UINT, 16)),
         ({"CGID": 1, "LGID": 0, "CNAM": "SYNTHETIC CONF", "NCcl": 2},)),
        ("DIVI",
         (("CGID", ea_tdb.FIELD_UINT, 5),
          ("DGID", ea_tdb.FIELD_UINT, 4),
          ("DNAM", ea_tdb.FIELD_STRING, 160)),
         ({"CGID": 1, "DGID": 0, "DNAM": "SYNTHETIC DIV"},)),
        ("STAD",
         (("SGID", ea_tdb.FIELD_UINT, 8),
          ("SNAM", ea_tdb.FIELD_STRING, 240),
          ("STNN", ea_tdb.FIELD_STRING, 144),
          ("SCIT", ea_tdb.FIELD_STRING, 168),
          ("SSTA", ea_tdb.FIELD_STRING, 120),
          ("SCAP", ea_tdb.FIELD_UINT, 17)),
         ({"SGID": 1, "SNAM": "SYNTHETIC FIELD", "STNN": "Synth",
           "SCIT": "Nowhere", "SSTA": "ZZ", "SCAP": 40000},)),
        ("COCH",
         (("CCID", ea_tdb.FIELD_UINT, 16),
          ("TGID", ea_tdb.FIELD_UINT, 9),
          ("CLFN", ea_tdb.FIELD_STRING, 80),
          ("CLLN", ea_tdb.FIELD_STRING, 104),
          ("COHT", ea_tdb.FIELD_UINT, 3)),
         ({"CCID": 1, "TGID": 1, "CLFN": "Synth", "CLLN": "Coach", "COHT": 0},)),
        ("PACL",
         (("PCID", ea_tdb.FIELD_UINT, 8),
          ("CRED", ea_tdb.FIELD_UINT, 8),
          ("CGRN", ea_tdb.FIELD_UINT, 8),
          ("CBLU", ea_tdb.FIELD_UINT, 8)),
         tuple({"PCID": n, "CRED": n * 5 & 0xFF, "CGRN": n * 9 & 0xFF,
                "CBLU": n * 17 & 0xFF} for n in range(4))),
    )))


def synthetic_texture_member(width: int = 16, height: int = 16, *, seed: int = 0,
                             mips: int = 1, images: int = 1,
                             retail_layout: bool = True) -> bytes:
    """One decodable ``MMAP`` member, built by the shared fixture builder.

    ``mod_editor.games._lanes.synthetic_art`` computes every byte from
    :mod:`mmap_art`'s own constants -- a CLUT whose three channels use
    different strides and an index ramp -- so a decode that swaps palette
    entries or mistakes a stride is visibly wrong rather than subtly off.  The
    same builder is what Madden 09's art lanes are proved on, which is the
    point: one ``MMAP`` format, one fixture, two discs.
    """

    from mod_editor.games._lanes import synthetic_art

    return synthetic_art.synthetic_mmap(width, height, seed=seed, mips=mips,
                                        images=images, retail_layout=retail_layout)


#: Which synthetic container carries what, so a lane names its own fixture
#: rather than an index.  Every name is one this disc really ships [M].
SYNTHETIC_ART_CONTAINERS = (
    UNIFORM_CONTAINERS[0],      # UNIFORM.DAT   - LZH1 kits, cached directory
    UNIFORM_CONTAINERS[2],      # UIS_GEAR.DAT  - stored gear, named by no cache
    FACE_CONTAINERS[0],         # PLYRFACE.DAT  - stored faces, cached members
    FACE_CONTAINERS[1],         # COACFACE.DAT
    STADIUM_CONTAINERS[0],      # STADATA.DAT
    STADIUM_CONTAINERS[1],      # UIS_STAD.DAT
    FIELD_ART_CONTAINERS[0],    # FLDDATA.DAT
    FIELD_ART_CONTAINERS[1],    # UIS_TMLO.DAT
    PRESENTATION_CONTAINERS[0],  # FANDATA.DAT
    PRESENTATION_CONTAINERS[1],  # MSCTDATA.DAT
    PRESENTATION_CONTAINERS[2],  # LOADDATA.DAT
)


def build_synthetic_disc(*, tdb_members: Optional[Sequence[bytes]] = None,
                         stream_database: Optional[bytes] = None,
                         preload_caches: bool = True,
                         audio_members: Optional[Sequence[bytes]] = None,
                         art_members: Optional[Sequence[bytes]] = None,
                         playbook_members: Optional[Sequence[bytes]] = None) -> bytes:
    """A tiny ``SLUS-21752``-shaped image carrying this module's containers.

    ``LEAGUE.DAT`` is built as a ``COMP`` container whose members are
    ``RLE1``-packed -- the chain and the codec the real container uses, so a
    writer that re-packs a member is proved against the encoder it will really
    use -- and the art and text containers as the disc has them: ``UNIFORM.DAT``
    and the ``LZH1`` ones compressed, ``UIS_GEAR.DAT``, ``PLYRFACE.DAT`` and
    ``FANDATA.DAT`` stored.

    The three ``QL01`` caches are built **last**, from the containers' own
    bytes, and carry the copies the retail caches carry [M]: ``LEAGUE.DAT``'s
    directory twice and its member 0, ``UNIFORM.DAT``'s directory and one of
    its members, ``PLYRFACE.DAT``'s directory and a member.  So the coherence
    rule -- rewrite every stale copy or refuse -- is exercised on a fixture,
    and ``preload_caches=False`` builds the same disc without them for a lane
    that wants to prove the uncached path.

    Every byte comes from ``ea_terf.build_terf`` and the builders above; no
    game data is involved, which is what lets the conformance harness run a
    lane on a machine that owns no disc.
    """

    from mod_editor.games._formats import ea_schl

    league_members = list(tdb_members) if tdb_members is not None else [
        synthetic_league_database(), synthetic_tdb(tables=2), synthetic_tdb(tables=1)]
    league = ea_terf.build_terf(league_members, chunk="COMP",
                                codecs=[ea_terf.CODEC_RLE1] * len(league_members))
    playbooks = ea_terf.build_terf(
        list(playbook_members) + [synthetic_text_member()]
        if playbook_members is not None
        else [synthetic_tdb(tables=1), synthetic_text_member()], chunk="DATA")
    templates = ea_terf.build_terf([synthetic_tdb(tables=2), b""], chunk="DATA")
    if art_members is None:
        art_members = [synthetic_texture_member(16, 16, seed=1),
                       synthetic_texture_member(8, 8, seed=2),
                       synthetic_texture_member(16, 8, seed=3)]
    art_members = list(art_members)
    if audio_members is None:
        audio_members = [ea_schl.synthetic_stream(), ea_schl.synthetic_bank()]
    sounds = ea_terf.build_terf(list(audio_members), chunk="DATA")
    texts = ea_terf.build_terf([synthetic_text_member()], chunk="DATA")

    #: ``(name, chunk, codec)`` per art container, matching what the disc ships
    #: for each [M]: the four ``COMP``/``LZH1`` ones and the stored ones.
    art_shapes = (
        (UNIFORM_CONTAINERS[0], "COMP", ea_terf.CODEC_LZH1),
        (UNIFORM_CONTAINERS[1], "COMP", ea_terf.CODEC_LZH1),
        (UNIFORM_CONTAINERS[2], "DATA", ea_terf.CODEC_STORED),
        (FACE_CONTAINERS[0], "DATA", ea_terf.CODEC_STORED),
        (FACE_CONTAINERS[1], "DATA", ea_terf.CODEC_STORED),
        (STADIUM_CONTAINERS[0], "COMP", ea_terf.CODEC_LZH1),
        (STADIUM_CONTAINERS[1], "DATA", ea_terf.CODEC_STORED),
        (FIELD_ART_CONTAINERS[0], "COMP", ea_terf.CODEC_LZH1),
        (FIELD_ART_CONTAINERS[1], "COMP", ea_terf.CODEC_LZH1),
        (PRESENTATION_CONTAINERS[0], "DATA", ea_terf.CODEC_STORED),
        (PRESENTATION_CONTAINERS[1], "COMP", ea_terf.CODEC_LZH1),
        (PRESENTATION_CONTAINERS[2], "COMP", ea_terf.CODEC_LZH1),
    )
    art: List[Tuple[str, bytes]] = []
    for name, chunk, codec in art_shapes:
        art.append((name, ea_terf.build_terf(
            art_members, chunk=chunk,
            codecs=([codec] * len(art_members)) if chunk == "COMP" else None)))
    art_by_name = dict(art)

    boot = b"BOOT2 = cdrom0:\\%s;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n" % BOOT_FILE.encode("ascii")
    sub_files: List[Tuple[bytes, bytes]] = [
        (LEAGUE_CONTAINER.encode("ascii") + b";1", league),
        (GAME_DATA_CONTAINER.encode("ascii") + b";1", playbooks),
        (TEMPLATE_CONTAINER.encode("ascii") + b";1", templates),
        (AUDIO_CONTAINERS[1].encode("ascii") + b";1", sounds),
        (TEXT_CONTAINERS[0].encode("ascii") + b";1", texts),
    ]
    sub_files += [(name.encode("ascii") + b";1", blob) for name, blob in art]
    if preload_caches:
        def directory(blob: bytes) -> bytes:
            return blob[:ea_terf.parse_terf(blob).data_offset]

        uniforms = art_by_name[UNIFORM_CONTAINERS[0]]
        faces = art_by_name[FACE_CONTAINERS[0]]
        caches = (
            (PRELOAD_CACHES[0], [
                (LEAGUE_CONTAINER, PRELOAD_KIND_HEADER, None, directory(league)),
                (UNIFORM_CONTAINERS[0], PRELOAD_KIND_HEADER, None, directory(uniforms)),
                (UNIFORM_CONTAINERS[0], PRELOAD_KIND_MEMBER, 1,
                 ea_terf.parse_terf(uniforms).stored(1)),
            ]),
            (PRELOAD_CACHES[1], [
                (GAME_DATA_CONTAINER, PRELOAD_KIND_HEADER, None, directory(playbooks)),
                (GAME_DATA_CONTAINER, PRELOAD_KIND_MEMBER, 1,
                 ea_terf.parse_terf(playbooks).stored(1)),
                (FACE_CONTAINERS[0], PRELOAD_KIND_HEADER, None, directory(faces)),
                (FACE_CONTAINERS[0], PRELOAD_KIND_MEMBER, 0,
                 ea_terf.parse_terf(faces).stored(0)),
            ]),
            (PRELOAD_CACHES[2], [
                (LEAGUE_CONTAINER, PRELOAD_KIND_HEADER, None, directory(league)),
                (LEAGUE_CONTAINER, PRELOAD_KIND_MEMBER, 0,
                 ea_terf.parse_terf(league).stored(0)),
            ]),
        )
        sub_files += [(name.encode("ascii") + b";1", build_synthetic_preload_cache(rows))
                      for name, rows in caches]
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
