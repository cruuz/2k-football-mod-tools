"""Reading Madden NFL 09 (PS2) ``/DATA`` containers out of the user's own disc.

Every lane in this module starts here.  The disc's large ``/DATA/*.DAT`` files
are EA ``TERF`` containers -- the shared reader is
:mod:`mod_editor.games._formats.ea_terf`, which knows the container and nothing
about this game -- and this file is the game-specific half: which files to
walk, how big a container this module is willing to hold in memory, how to
recover a container the disc's own directory record understates, and how to
build a synthetic disc the conformance harness can prove a lane on without any
game data.

**Evidence tags.**  **[M]** measured on a disc this box holds; **[S]** sourced;
**[A]** assumed.

**Retail-free.**  Names, offsets, lengths, counts and digests only.  No member
payload and no decoded pixel reaches the repository, and nothing here writes to
the user's image.

Standard library only; importable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import struct
import sys
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_terf
from mod_editor.games.contract import Refusal

from . import mmap_art

_ROOT = Path(__file__).resolve().parents[3]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ps2_iso9660 as iso_lib  # noqa: E402

# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

#: The disc serial both supported images boot [M].
SERIAL = "SLUS-21770"

#: The boot file ``SYSTEM.CNF`` names, in ISO9660 spelling [M].
BOOT_FILE = "SLUS_217.70"

#: SHA-256 of the boot ELF on the retail USA disc [M].
RETAIL_BOOT_ELF_SHA256 = "adb400ba49702114876fb3f8e1d2d64dce1b1a57a9d25cd705d74ffcf9f68c4c"

#: SHA-256 of the whole retail USA image [M].
RETAIL_IMAGE_SHA256 = "b34e8a6acb4be6c92c238173e9c269bf42dfd3bb4231685052538f3aa82f6427"

#: SHA-256 of the boot ELF on the community's *Deluxe* disc -- a patched
#: executable, so it differs from retail by design [M].
DELUXE_BOOT_ELF_SHA256 = "d1cb5459c589d0dc28c9296c29940eaca161af152ea0b3c9825c012e7588a515"

#: SHA-256 of the whole *Deluxe* image [M].
DELUXE_IMAGE_SHA256 = "d331c5e40104317768a0ff100476082b2dd499d1758b9a04ba0e0efe4bc1be20"

#: PCSX2's CRC (the XOR of every 32-bit word of the boot ELF) for each image
#: [M].  Carried for the code-patch lane, which names a CRC in every pnach.
RETAIL_ELF_CRC = "38014255"
DELUXE_ELF_CRC = "084562FF"

#: What ``identify`` calls each image.  A disc that is neither is refused.
RETAIL_EDITION = "retail"
DELUXE_EDITION = "deluxe"

# --------------------------------------------------------------------------
# The containers
# --------------------------------------------------------------------------

#: Where every container lives on both images [M].
DATA_DIRECTORY = "/DATA"

#: How much of a container this module will hold in memory.  Madden 09's
#: speech and music containers run from 124 MB to 415 MB [M]; a lane names
#: them in its catalogue with their size and does not read them, rather than
#: swallowing half a gigabyte to count members nobody asked for.
CONTAINER_SIZE_LIMIT = 96 * 1024 * 1024

#: How much of a file is read to decide whether it is a container at all.
#: :func:`ea_terf.declared_length` needs the header and the chunk chain, which
#: is a few kilobytes; 64 KiB is generous and still one ranged read.
PROBE_BYTES = 1 << 16

#: The containers each lane names.  These are file names on the disc, not
#: payload: which member of which container a lane edits is the lane's own
#: business, and every count below is the census in
#: ``docs/product/EA_TERF_FORMAT.md`` §4.1 [M].
UNIFORM_CONTAINER = "UNIFORMS.DAT"
PLAYER_FACE_CONTAINER = "PLYRFACE.DAT"
COACH_FACE_CONTAINER = "COACFACE.DAT"
TATTOO_CONTAINER = "TATTOOS.DAT"
TEAM_DATABASE_CONTAINER = "DB_TEAMS.DAT"
TEMPLATE_CONTAINER = "TEMPLATE.DAT"
GAME_DATA_CONTAINER = "GAMEDATA.DAT"

#: The one ``/DATA`` file that is a bare EA TDB rather than a ``TERF``
#: container [M]: it carries no chunk chain and is parsed directly.
STREAM_DATABASE_FILE = "STRMDATA.DB"

# --------------------------------------------------------------------------
# The preload caches
# --------------------------------------------------------------------------
#
# ``/DATA/GAME.QKL`` and ``/DATA/FE.QKL`` are the game's and the front end's
# **preload caches**: a ``QL01`` header, a ``FILS`` chunk naming 29 and 28
# ``/DATA`` files respectively, and a body that carries at least some of those
# files verbatim -- the first 256 bytes of ``UIS_BANR.DAT``, ``UNIFORMS.DAT``,
# ``PLYRFACE.DAT``, ``GAMEDATA.DAT``, ``TEMPLATE.DAT`` and ``LOADDATA.DAT``
# each appear inside the cache that names them [M].  Not every named file
# does: ``STADATA.DAT`` is named in both and its head is in neither [M], so
# what a cache carries of a file it names is **not established** [A].
#
# That is enough for the rule a writer needs.  A lane that rewrites a file the
# cache names would leave a second copy of it behind that nobody updated, and
# which of the two the game reads is exactly the thing not established -- so
# **a file either cache names is not written**, and the refusal says so.  The
# files this module's writing lanes touch -- ``DB_TEAMS.DAT`` and the six
# story and online-string containers -- are named in neither [M].

#: The preload caches, in the order a refusal names them.
PRELOAD_FILES = ("GAME.QKL", "FE.QKL")

#: The header and the chunk that lists what a cache holds.
QKL_MAGIC = b"QL01"
QKL_FILE_LIST = b"FILS"

#: One name in that list: a NUL-padded file name in a fixed-width slot [M].
QKL_NAME_STRIDE = 48

#: A sanity ceiling on the count the chunk declares, so a misread header asks
#: for a list rather than a gigabyte.
QKL_MAX_NAMES = 4096


def preload_names(image: Any) -> Dict[str, Tuple[str, ...]]:
    """Which ``/DATA`` files each preload cache names, upper-cased.

    ``{"UNIFORMS.DAT": ("GAME.QKL", "FE.QKL"), ...}``.  A cache that is not on
    the image, or whose header this does not recognise, contributes nothing --
    an image without them is a different image, not a broken read -- so a
    caller that needs the rule to hold anyway keeps its own measured list as
    well.

    Only the first :data:`PROBE_BYTES` of a cache are read: the list sits in
    the second chunk, a kilobyte and a half in, and the caches themselves run
    to 11 MB.
    """

    found: Dict[str, List[str]] = {}
    for cache in PRELOAD_FILES:
        entry = iso_lib.find(image, f"{DATA_DIRECTORY}/{cache}")
        if entry is None:
            continue
        head = _read_extent(image, int(entry.lba), PROBE_BYTES)
        for name in _preload_names_in(head or b""):
            found.setdefault(name, []).append(cache)
    return {name: tuple(caches) for name, caches in sorted(found.items())}


def _preload_names_in(head: bytes) -> Tuple[str, ...]:
    """The file names a ``QL01`` cache's ``FILS`` chunk lists, or nothing."""

    if not head.startswith(QKL_MAGIC) or len(head) < 24:
        return ()
    header_length, = struct.unpack_from("<I", head, 4)
    if not 8 <= header_length <= len(head) - 12:
        return ()
    if head[header_length:header_length + 4] != QKL_FILE_LIST:
        return ()
    count, = struct.unpack_from("<I", head, header_length + 8)
    if not 0 < count <= QKL_MAX_NAMES:
        return ()
    base = header_length + 12
    if base + count * QKL_NAME_STRIDE > len(head):
        return ()
    out: List[str] = []
    for index in range(count):
        raw = head[base + index * QKL_NAME_STRIDE:
                   base + (index + 1) * QKL_NAME_STRIDE]
        name = raw.split(b"\x00", 1)[0].decode("latin-1", "replace").strip()
        if name:
            out.append(name.upper())
    return tuple(out)


class DiscError(Refusal):
    """This module could not read what it was pointed at; the sentence says why."""


@dataclass(frozen=True)
class DataFile:
    """One file under ``/DATA``, as the disc's directory record describes it."""

    name: str
    path: str
    lba: int
    #: What the ISO9660 directory record says.  Not always the truth: six
    #: containers on the *Deluxe* image are recorded 4 to 26,168 bytes short of
    #: what they carry [M], which is what :func:`read_container` recovers.
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
            f"this image holds no files under {DATA_DIRECTORY}, so it is not a "
            f"Madden NFL 09 PlayStation 2 disc. Choose the {SERIAL} image."
        )
    return tuple(found)


def _read_extent(image: Any, lba: int, wanted: int) -> Optional[bytes]:
    """*wanted* bytes from the extent at *lba*, or ``None`` if they are not there.

    Addressed through the reader rather than by multiplying by a sector size:
    a raw-CD image's logical blocks are not contiguous in the file.
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


def read_file(image: Any, entry: DataFile, *, limit: Optional[int] = CONTAINER_SIZE_LIMIT) -> bytes:
    """One ``/DATA`` file's bytes, honouring what the container declares.

    ISO9660 extents are whole sectors, so a container recorded short is still
    entirely on the disc; reading the directory record's length loses every
    member past the cut.  When the file's own chunk chain declares more than
    the record does, the extent is re-read to the declared length and that is
    what comes back.  A file too large for *limit* is refused by name and size,
    never truncated.
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
# The preload caches
# --------------------------------------------------------------------------
#
# ``GAME.QKL`` and ``FE.QKL`` are not containers: they are **byte copies** of
# things that already exist elsewhere on the disc, laid out so the game can
# stream them in one read.  Two kinds of copy are carried [M]:
#
# * a **container header** -- the first ``data_offset`` bytes of a ``TERF``
#   file, which is its header plus the ``DIR1`` and ``COMP`` directories;
# * a **member**, byte for byte as that member is stored in its container.
#
# **This is load-bearing for any writer.**  ``UNIFORMS.DAT``'s directory is
# copied three times (once in ``GAME.QKL``, twice in ``FE.QKL``) and none of
# its members is copied at all [M].  So rewriting a member is free *as long as
# the first ``data_offset`` bytes do not move* -- and they move the moment a
# member changes stored size or codec, because both live in the directory.  An
# edit that leaves three stale directories behind is an edit the game reads
# against the wrong offsets.
#
# ## The format [M]
#
# ```
# QL01 chunk   8-byte tag+size, then u32 payload offset at +0x08
# FILS chunk   tag, size, u32 count, then count x 48-byte NUL-padded names
# DTLS chunk   tag, size, u32 count, then count x 12-byte entries
# DATA chunk   tag, size 0; the payload runs from the QL01 offset to EOF
# ```
#
# A ``DTLS`` entry is ``u8 kind, u8, u8 file index, u8, u32 member, u32
# offset``: *kind* 0 is a header copy and 1 a member copy, *file index* points
# into ``FILS``, and *offset* is relative to the payload.  Measured against the
# retail disc: 6,247 copies across the two caches, every one byte-identical to
# what it copies, zero mismatches [M].

#: The two preload caches, in the order a report lists them.
PRELOAD_CACHES = ("GAME.QKL", "FE.QKL")

QL01_MAGIC = b"QL01"
QL01_FILS = b"FILS"
QL01_DTLS = b"DTLS"
QL01_PAYLOAD_OFFSET = 8
QL01_NAME_STRIDE = 48
QL01_ENTRY_STRIDE = 12
QL01_CHUNK_HEADER = 8
QL01_COUNT_OFFSET = 8

#: A ``DTLS`` entry copies a container's header, or one of its members.
PRELOAD_KIND_HEADER = 0
PRELOAD_KIND_MEMBER = 1

#: Guard rails, so a malformed cache is refused rather than walked forever.
QL01_MAX_FILES = 4096
QL01_MAX_ENTRIES = 1 << 20


@dataclass(frozen=True)
class PreloadCopy:
    """One byte-for-byte copy a preload cache carries, and where it lives."""

    cache: str
    container: str
    kind: int
    #: The member copied, or ``None`` for a header copy.
    member: Optional[int]
    #: Absolute byte offset inside the cache file.
    offset: int

    @property
    def is_header(self) -> bool:
        return self.kind == PRELOAD_KIND_HEADER

    def length_in(self, parsed: ea_terf.TerfContainer) -> int:
        """How many bytes this copy is, given the container it copies."""

        if self.is_header:
            return parsed.data_offset
        if self.member is None or not 0 <= self.member < parsed.member_count:
            raise DiscError(
                f"{self.cache} carries a copy of {self.container} member "
                f"{self.member}, which that container does not have.")
        return parsed.members[self.member].stored_size

    def as_dict(self) -> Dict[str, Any]:
        return {"cache": self.cache, "container": self.container,
                "kind": "header" if self.is_header else "member",
                "member": self.member, "offset": self.offset}


@dataclass(frozen=True)
class ContainerPreload:
    """Every copy of one container the caches carry."""

    container: str
    header: Tuple[PreloadCopy, ...] = ()
    members: Mapping[int, Tuple[PreloadCopy, ...]] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.header and not self.members

    def for_member(self, index: int) -> Tuple[PreloadCopy, ...]:
        return tuple(self.members.get(index, ()))


def parse_preload_cache(data: bytes, cache: str) -> Tuple[PreloadCopy, ...]:
    """Every copy a ``QL01`` cache declares.  Refuses; never guesses."""

    if len(data) < QL01_CHUNK_HEADER + 4 or data[:4] != QL01_MAGIC:
        raise DiscError(
            f"{cache} starts with {bytes(data[:4])!r}, not {QL01_MAGIC!r}, so it is not a "
            f"preload cache. Nothing here reads it.")
    chunks: Dict[bytes, Tuple[int, int]] = {}
    cursor = 0
    while cursor + QL01_CHUNK_HEADER <= len(data):
        tag = bytes(data[cursor:cursor + 4])
        size, = struct.unpack_from("<I", data, cursor + 4)
        chunks[tag] = (cursor, size)
        if size <= 0 or cursor + size > len(data):
            break
        cursor += size
    for wanted in (QL01_FILS, QL01_DTLS):
        if wanted not in chunks:
            raise DiscError(
                f"{cache} carries no {wanted.decode('ascii')} chunk, so it does not say what "
                f"it copies. Nothing here reads it.")
    payload, = struct.unpack_from("<I", data, QL01_PAYLOAD_OFFSET)
    if not 0 < payload <= len(data):
        raise DiscError(
            f"{cache} puts its payload at byte {payload} and the file is {len(data)} bytes.")

    files_offset, _files_size = chunks[QL01_FILS]
    file_count, = struct.unpack_from("<I", data, files_offset + QL01_COUNT_OFFSET)
    if not 0 <= file_count <= QL01_MAX_FILES:
        raise DiscError(f"{cache} declares {file_count} file name(s); that is not a cache.")
    names: List[str] = []
    base = files_offset + QL01_COUNT_OFFSET + 4
    for index in range(file_count):
        start = base + QL01_NAME_STRIDE * index
        if start + QL01_NAME_STRIDE > len(data):
            raise DiscError(f"{cache}'s file-name table runs past the end of the file.")
        names.append(bytes(data[start:start + QL01_NAME_STRIDE]).split(b"\x00")[0]
                     .decode("latin-1").upper())

    entries_offset, _entries_size = chunks[QL01_DTLS]
    entry_count, = struct.unpack_from("<I", data, entries_offset + QL01_COUNT_OFFSET)
    if not 0 <= entry_count <= QL01_MAX_ENTRIES:
        raise DiscError(f"{cache} declares {entry_count} copies; that is not a cache.")
    out: List[PreloadCopy] = []
    base = entries_offset + QL01_COUNT_OFFSET + 4
    for index in range(entry_count):
        start = base + QL01_ENTRY_STRIDE * index
        if start + QL01_ENTRY_STRIDE > len(data):
            raise DiscError(f"{cache}'s copy table runs past the end of the file.")
        kind = data[start]
        file_index = data[start + 2]
        member, offset = struct.unpack_from("<II", data, start + 4)
        if file_index >= len(names):
            raise DiscError(
                f"{cache} copy {index} names file {file_index} and the cache lists "
                f"{len(names)}.")
        if kind not in (PRELOAD_KIND_HEADER, PRELOAD_KIND_MEMBER):
            continue
        out.append(PreloadCopy(
            cache=cache, container=names[file_index], kind=kind,
            member=None if kind == PRELOAD_KIND_HEADER else int(member),
            offset=payload + int(offset)))
    return tuple(out)


def preload_copies(image: Any, *, caches: Sequence[str] = PRELOAD_CACHES
                   ) -> Dict[str, ContainerPreload]:
    """``container name -> ContainerPreload`` for every cache on this image.

    The one function every lane that writes a container calls, so the
    coherence rule lives in one place: a member edit that changes a
    container's directory has to change the copies of that directory too, and
    a member that is itself copied has to be rewritten in the cache as well or
    refused.
    """

    present = {entry.name.upper(): entry for entry in data_files(image)}
    found: Dict[str, Dict[str, Any]] = {}
    for cache in caches:
        entry = present.get(cache.upper())
        if entry is None:
            continue
        copies = parse_preload_cache(read_file(image, entry, limit=None), cache)
        for copy in copies:
            row = found.setdefault(copy.container, {"header": [], "members": {}})
            if copy.is_header:
                row["header"].append(copy)
            else:
                row["members"].setdefault(copy.member, []).append(copy)
    return {
        name: ContainerPreload(
            container=name, header=tuple(row["header"]),
            members={index: tuple(items) for index, items in sorted(row["members"].items())})
        for name, row in sorted(found.items())
    }


#: What :func:`classify` answers for a file that is not a container this
#: module reads.  Each is a state, not a failure: "there is nothing there" and
#: "this reader cannot open it" must not render the same.
KIND_TERF = "TERF"
KIND_TDB = "TDB"
KIND_OTHER = "other"
KIND_UNREAD = "not-read"


def classify(image: Any, entry: DataFile) -> str:
    """Whether ``/DATA/<name>`` is a ``TERF`` container, a bare TDB, or neither.

    Answered from the file's first bytes, so a 415 MB speech container costs a
    single ranged read.
    """

    iso_entry = iso_lib.find(image, entry.path)
    if iso_entry is None:
        return KIND_OTHER
    head = b""
    for chunk in iso_lib.iter_file_chunks(image, iso_entry):
        head = bytes(chunk[:64])
        break
    if head.startswith(ea_terf.TERF_MAGIC):
        return KIND_TERF
    if ea_terf.identify_member(head) == ea_terf.FORMAT_TDB:
        return KIND_TDB
    return KIND_OTHER


@dataclass(frozen=True)
class ContainerReport:
    """One ``/DATA`` file as a lane catalogues it: metadata, never payload."""

    name: str
    path: str
    kind: str
    recorded_length: int
    #: ``None`` when the file was not read (too large, or not a container).
    read_length: Optional[int] = None
    chunk_chain: str = ""
    alignment: int = 0
    member_count: int = 0
    codec_histogram: Dict[str, int] = None  # type: ignore[assignment]
    format_histogram: Dict[str, int] = None  # type: ignore[assignment]
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

    Returns the report and, when the file was a container small enough to
    read, the parsed container itself so a caller can go on to its members
    without a second read.  A refusal from the reader becomes a ``note`` on the
    row: one unreadable container must not empty the whole catalogue.
    """

    kind = classify(image, entry)
    if kind != KIND_TERF:
        note = ""
        if kind == KIND_TDB:
            note = "a bare EA TDB database rather than a TERF container."
        return ContainerReport(
            name=entry.name,
            path=entry.path,
            kind=kind,
            recorded_length=entry.recorded_length,
            note=note,
        ), None
    try:
        data = read_file(image, entry, limit=limit)
    except DiscError as exc:
        return ContainerReport(
            name=entry.name,
            path=entry.path,
            kind=KIND_UNREAD,
            recorded_length=entry.recorded_length,
            note=str(exc),
        ), None
    try:
        # The Deluxe image records six containers short of their own DATA
        # chunk and under-counts a trailing empty member in three of them, and
        # the game ships and plays it; a reader that refuses those loses five
        # of the containers this module's lanes are about.
        container = ea_terf.parse_terf(data, allow_size_mismatch=True)
    except ea_terf.TerfError as exc:
        return ContainerReport(
            name=entry.name,
            path=entry.path,
            kind=KIND_UNREAD,
            recorded_length=entry.recorded_length,
            read_length=len(data),
            note=str(exc),
        ), None
    formats: Dict[str, int] = {}
    if with_formats:
        try:
            formats = container.format_histogram()
        except ea_terf.TerfError as exc:
            formats = {}
            note_formats = str(exc)
        else:
            note_formats = ""
    else:
        note_formats = ""
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


def load_container(
    image: Any, name: str, *, limit: Optional[int] = CONTAINER_SIZE_LIMIT
) -> ea_terf.TerfContainer:
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
        f"this image holds no {wanted}; it is not a Madden NFL 09 PlayStation 2 "
        f"disc, or the container has been removed. Choose the {SERIAL} image."
    )


def member_uncached(container: ea_terf.TerfContainer, index: int) -> bytes:
    """One member, whole, without putting it in the container's cache.

    :meth:`TerfContainer.member` caches what it unpacks, which is right for a
    lane that comes back to the same member -- and wrong for one walking a
    455-member container whose members unpack to 350 KB each, where the cache
    is a 160 MB pile nobody reads twice.  Asking for exactly the declared size
    returns the whole member and skips the cache.
    """

    return container.member(index, max_output=container.members[index].decompressed_size)


def members_of_format(
    container: ea_terf.TerfContainer,
    wanted: str,
    *,
    progress: Optional[Callable[[str], None]] = None,
    limit: Optional[int] = None,
) -> Iterator[Tuple[int, bytes]]:
    """Every member whose *decompressed* bytes carry format *wanted*.

    A packed member's stored magic says nothing about its format, so each
    member has to be unpacked before it can be classified -- but only its
    **first 32 bytes**, which is what :meth:`TerfContainer.member_format` asks
    for and what the codec stops at.  Only a member that matches is then
    unpacked in full.  Classifying by full decompression instead costs minutes
    on a retail disc: 36,195 members, 4,269 of them ``LZH1`` streams decoded in
    pure Python, for an answer the first 32 bytes already gave.

    A member the codec cannot open is skipped rather than failing the walk,
    because one unreadable member must not empty a catalogue of hundreds.
    """

    yielded = 0
    for index in range(len(container)):
        if limit is not None and yielded >= limit:
            return
        try:
            if container.member_format(index) != wanted:
                continue
            payload = container.member(index)
        except ea_terf.TerfError:
            continue
        if ea_terf.identify_member(payload) != wanted:
            # The head said one thing and the whole member says another: a
            # truncated or malformed member, not one of these.
            continue
        yielded += 1
        if progress is not None and yielded % 64 == 0:
            progress(f"{yielded} {wanted} member(s) read…")
        yield index, payload


# --------------------------------------------------------------------------
# The synthetic disc
# --------------------------------------------------------------------------

#: The container names the synthetic disc carries.  They are the real ones so
#: a lane's own name filter is exercised, and every byte inside them is
#: computed here from the format's rules -- nothing is copied from a disc.
#: Every ``/DATA`` file :func:`build_synthetic_disc` writes.  The two preload
#: caches are there so CI proves the cache-coherence rule a writer has to
#: follow, not because a reader needs them.
SYNTHETIC_CONTAINERS = (UNIFORM_CONTAINER, TEAM_DATABASE_CONTAINER) + PRELOAD_CACHES


def synthetic_palette(entries: int = 256) -> List[Tuple[int, int, int, int]]:
    """A CLUT of *entries* colours, computed rather than sampled.

    Every channel is a different stride so a decode that swaps or shifts
    palette entries produces obviously wrong colours instead of a subtle
    shift.  Alpha is PS2's 0..128 scale.
    """

    return [((index * 5) & 0xFF, (index * 9) & 0xFF, (index * 17) & 0xFF,
             0x80 if index % 4 else 0x40)
            for index in range(entries)]


def synthetic_indices(width: int, height: int, *, seed: int = 0, bits: int = 8) -> bytes:
    """Index bytes for a *width* x *height* surface: a deterministic ramp.

    A wrong stride turns this into a visible diagonal, which is the point:
    a fixture whose failure mode is invisible proves nothing.
    """

    modulus = 256 if bits == 8 else 16
    values = [(seed + x * 7 + y * 13) % modulus
              for y in range(height) for x in range(width)]
    if bits == 8:
        return bytes(values)
    packed = bytearray(len(values) // 2)
    for position in range(0, len(values) - 1, 2):
        packed[position // 2] = values[position] | (values[position + 1] << 4)
    return bytes(packed)


def synthetic_mmap(width: int, height: int, *, version: int = 2, seed: int = 0,
                   bits: int = 8, mips: int = 1, palette_only_extra: bool = False,
                   retail_layout: bool = False) -> bytes:
    """An ``MMAP`` member built from the format's own rules, not from a disc.

    ``MMAP`` is a table-of-tables -- an image table, a surface table (one row
    per mip level), a palette table and a name table, each addressed by an
    offset in the 40-byte header -- and this builds all of it.  See
    :mod:`.mmap_art` for the layout and the evidence behind it.

    *mips* adds halved levels after the base one, and *palette_only_extra*
    appends the second image entry the real containers carry: a row with no
    surfaces whose job is to hold an alternate CLUT for the first image.  Both
    exist so a lane's handling of them is exercised without a game.

    The default puts all four tables at the front, which is a **legal member
    the disc does not contain**: only the surface table's position is fixed,
    so a fixture in this shape proves the reader follows the header's offsets
    instead of assuming the disc's arrangement.  *retail_layout* runs the
    result through :func:`mmap_art.encode` with nothing replaced, which lays
    the same member out the way every measured member is laid out -- tables
    behind the pixels, 16-byte aligned -- and is what a writer's fixture wants.
    """

    import struct

    header_size = mmap_art.HEADER_SIZE
    levels = []
    level_width, level_height = width, height
    for level in range(max(1, mips)):
        levels.append((level_width, level_height,
                       synthetic_indices(level_width, level_height,
                                         seed=seed + level, bits=bits)))
        level_width = max(1, level_width // 2)
        level_height = max(1, level_height // 2)

    # A 256-entry CLUT is stored in the GS's CSM1 interleave, and undoing it is
    # an involution -- so storing the de-interleaved form makes the decoder
    # hand back exactly the palette this function names.
    wanted = synthetic_palette(256 if bits == 8 else 16)
    stored = mmap_art.deinterleave_csm1(wanted) if len(wanted) == 256 else list(wanted)
    clut = b"".join(bytes(entry) for entry in stored)

    image_count = 2 if palette_only_extra else 1
    palette_count = 2 if palette_only_extra else 1
    surface_offset = header_size
    image_offset = surface_offset + mmap_art.SURFACE_STRIDE * len(levels)
    palette_offset = image_offset + mmap_art.IMAGE_STRIDE * image_count
    name_offset = palette_offset + mmap_art.PALETTE_STRIDE * palette_count
    data_offset = name_offset + mmap_art.NAME_STRIDE * image_count

    surfaces = bytearray()
    cursor = data_offset
    layout = (mmap_art.PIXELS_INDEXED_8 if bits == 8 else mmap_art.PIXELS_INDEXED_4)
    for level_w, level_h, pixels in levels:
        surfaces += struct.pack("<HHIII", level_w, level_h, layout, len(pixels), cursor)
        cursor += len(pixels)
    palettes = bytearray()
    palette_cursor = cursor
    for _ in range(palette_count):
        palettes += struct.pack("<HHII", 0, mmap_art.PALETTE_RGBA8888,
                                len(clut), palette_cursor)
        palette_cursor += len(clut)

    images = bytearray()
    images += struct.pack("<HHII", 1, len(levels), 0, 0)
    if palette_only_extra:
        images += struct.pack("<HHII", 1, 0, 0, 1)
    names = b"".join(name.ljust(mmap_art.NAME_STRIDE, b"\x00")
                     for name in ([b"SYNTH"] + ([b"SYNTHALT"] if palette_only_extra else [])))

    payload = bytearray()
    payload += mmap_art.MMAP_MAGIC
    payload += struct.pack("<I", version)
    payload += bytes((0x00, 0x01, 0x02, 0x03))
    payload += struct.pack("<HH", image_count, len(levels))
    payload += struct.pack("<IIIIII", palette_count, image_offset, surface_offset,
                           palette_offset, name_offset, 0)
    assert len(payload) == header_size, len(payload)
    payload += surfaces
    payload += images
    payload += palettes
    payload += names
    for _level_w, _level_h, pixels in levels:
        payload += pixels
    payload += clut * palette_count
    if retail_layout:
        return mmap_art.encode(bytes(payload))
    return bytes(payload)


#: The strings the synthetic disc's ``TEXT`` member carries.  Each is over 32
#: characters on purpose: :func:`ea_terf.identify_member` calls a member
#: ``TEXT`` only when its first 32 bytes are all printable, so a fixture built
#: of short strings would be classified as something else and prove nothing.
SYNTHETIC_TEXT_LINES = (
    "SYNTHETIC STRING BANK ENTRY NUMBER ONE",
    "SYNTHETIC STRING BANK ENTRY NUMBER TWO",
    "SYNTHETIC STRING BANK ENTRY NUMBER THREE",
)


def synthetic_text_member(lines: Sequence[str]) -> bytes:
    """A ``TEXT`` member: NUL-separated printable strings, as the format has them."""

    body = b"".join(line.encode("latin-1", "replace") + b"\x00" for line in lines)
    return body if body else b"\x00"


def build_synthetic_preload_cache(payload: Sequence[Tuple[str, int, Optional[int], bytes]],
                                  *, alignment: int = 64) -> bytes:
    """A ``QL01`` preload cache carrying the copies given, in the disc's shape.

    *payload* is ``(container name, kind, member or None, bytes)`` per copy.
    Built from the format's own rules so CI can prove the cache-coherence step
    -- the one that keeps a container's three cached directories in step with
    the container -- without a game.
    """

    names: List[str] = []
    for container, _kind, _member, _bytes in payload:
        if container.upper() not in names:
            names.append(container.upper())
    files = struct.pack("<I", len(names)) + b"".join(
        name.encode("latin-1").ljust(QL01_NAME_STRIDE, b"\x00") for name in names)
    files_chunk = QL01_FILS + struct.pack("<I", QL01_CHUNK_HEADER + len(files)) + files

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
    entries_chunk = QL01_DTLS + struct.pack("<I", QL01_CHUNK_HEADER + len(entries)) + entries

    head_length = 12 + len(files_chunk) + len(entries_chunk) + QL01_CHUNK_HEADER
    out = bytearray()
    out += QL01_MAGIC + struct.pack("<II", 12, head_length)
    out += files_chunk
    out += entries_chunk
    out += b"DATA" + struct.pack("<I", 0)
    assert len(out) == head_length, (len(out), head_length)
    out += body
    return bytes(out)


def build_synthetic_disc(*, tdb_member: Optional[bytes] = None,
                         tdb_members: Optional[Sequence[bytes]] = None,
                         stream_database: Optional[bytes] = None,
                         preload_caches: bool = True) -> bytes:
    """A tiny ``SLUS-21770``-shaped image carrying two synthetic containers.

    ``UNIFORMS.DAT`` is built as a ``COMP`` container whose members are stored
    -- the shape the retail disc itself ships for 270 of that container's 725
    members [M], so a lane proved here is proved on a layout the game loads --
    and ``DB_TEAMS.DAT`` as a plain ``DATA`` container.  Every byte comes from
    :func:`ea_terf.build_terf` and the builders above; no game data is
    involved, which is what lets the conformance harness run this on a machine
    that owns none of these discs.

    ``tdb_members`` puts several databases in ``DB_TEAMS.DAT`` where
    ``tdb_member`` puts one, for a lane whose targets are one per member.
    ``stream_database`` adds ``/DATA/STRMDATA.DB``, which on the retail disc is
    a bare database with no container around it [M], for a lane that writes
    the second copy of a record living there.  Both default to absent, so a
    caller that wants what this built before gets exactly that.
    ``preload_caches=False`` leaves out the two ``QL01`` caches, for a test that
    needs an image with no cache at all.
    ``preload_caches=False`` leaves out the two ``QL01`` caches, for a test of
    what a reader answers on an image that has none.
    """

    uniform_members = [
        synthetic_mmap(16, 16, seed=1),
        synthetic_mmap(8, 8, seed=2),
        b"",
        synthetic_mmap(32, 16, seed=3),
    ]
    uniforms = ea_terf.build_terf(
        uniform_members,
        chunk="COMP",
        codecs=[ea_terf.CODEC_STORED] * len(uniform_members),
    )
    if tdb_members is not None:
        team_members = list(tdb_members)
    else:
        team_members = [tdb_member if tdb_member is not None else b""]
    team_members.append(synthetic_text_member(SYNTHETIC_TEXT_LINES))
    teams = ea_terf.build_terf([m for m in team_members], chunk="DATA")
    teams_member_one = ea_terf.parse_terf(teams).stored(1)
    # The preload caches carry byte copies of a container's directory, so a
    # writer that moves one has to move them too.  The synthetic disc carries
    # the same shape the retail disc does for this container -- one copy of
    # UNIFORMS.DAT's directory in GAME.QKL and two in FE.QKL, and none of its
    # members [M] -- so CI proves the coherence step rather than assuming it.
    directory = uniforms[:ea_terf.parse_terf(uniforms).data_offset]
    game_cache = build_synthetic_preload_cache([
        (UNIFORM_CONTAINER, PRELOAD_KIND_HEADER, None, directory),
        (TEAM_DATABASE_CONTAINER, PRELOAD_KIND_MEMBER, 1, teams_member_one),
    ])
    fe_cache = build_synthetic_preload_cache([
        (UNIFORM_CONTAINER, PRELOAD_KIND_HEADER, None, directory),
    ])
    boot = b"BOOT2 = cdrom0:\\%s;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n" % BOOT_FILE.encode("ascii")
    sub_files = [
        (UNIFORM_CONTAINER.encode("ascii") + b";1", uniforms),
        (TEAM_DATABASE_CONTAINER.encode("ascii") + b";1", teams),
    ]
    if preload_caches:
        sub_files += [
            (PRELOAD_CACHES[0].encode("ascii") + b";1", game_cache),
            (PRELOAD_CACHES[1].encode("ascii") + b";1", fe_cache),
        ]
    if stream_database is not None:
        sub_files.append((STREAM_DATABASE_FILE.encode("ascii") + b";1", stream_database))
    return iso_lib.build_synthetic_iso(
        files=[
            (b"SYSTEM.CNF;1", boot),
            (BOOT_FILE.encode("ascii") + b";1", b"\x7fELF" + bytes(4092)),
        ],
        sub_name=b"DATA",
        sub_files=sub_files,
    )


__all__ = [
    "BOOT_FILE",
    "CONTAINER_SIZE_LIMIT",
    "COACH_FACE_CONTAINER",
    "ContainerReport",
    "DATA_DIRECTORY",
    "DELUXE_BOOT_ELF_SHA256",
    "DELUXE_EDITION",
    "DELUXE_ELF_CRC",
    "DELUXE_IMAGE_SHA256",
    "DataFile",
    "DiscError",
    "GAME_DATA_CONTAINER",
    "KIND_OTHER",
    "KIND_TDB",
    "KIND_TERF",
    "KIND_UNREAD",
    "PLAYER_FACE_CONTAINER",
    "PRELOAD_CACHES",
    "PRELOAD_KIND_HEADER",
    "PRELOAD_KIND_MEMBER",
    "PROBE_BYTES",
    "PRELOAD_FILES",
    "QKL_FILE_LIST",
    "QKL_MAGIC",
    "QKL_MAX_NAMES",
    "QKL_NAME_STRIDE",
    "ContainerPreload",
    "PreloadCopy",
    "RETAIL_BOOT_ELF_SHA256",
    "RETAIL_EDITION",
    "RETAIL_ELF_CRC",
    "RETAIL_IMAGE_SHA256",
    "SERIAL",
    "STREAM_DATABASE_FILE",
    "SYNTHETIC_CONTAINERS",
    "SYNTHETIC_TEXT_LINES",
    "TATTOO_CONTAINER",
    "TEAM_DATABASE_CONTAINER",
    "TEMPLATE_CONTAINER",
    "UNIFORM_CONTAINER",
    "build_synthetic_disc",
    "build_synthetic_preload_cache",
    "classify",
    "data_files",
    "describe_container",
    "load_container",
    "member_uncached",
    "members_of_format",
    "open_disc",
    "preload_names",
    "parse_preload_cache",
    "preload_copies",
    "read_file",
    "synthetic_indices",
    "synthetic_mmap",
    "synthetic_palette",
    "synthetic_text_member",
]
