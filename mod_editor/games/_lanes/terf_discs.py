"""Reading an EA ``TERF`` disc's ``/DATA`` containers: the half that never varies.

Every module on the EA Tiburon/BIG PS2 stack needs the same twelve operations
before any lane of its own runs -- open the image, list ``/DATA``, read a file
to the length its own chunk chain declares rather than the length the ISO9660
directory record admits to, say what a file is, describe a container without
decoding a pixel, load one, take a member without poisoning the container's
cache, bound a container to the allocation the disc gave it, and read the
``QL01`` preload caches that decide what a write costs.

Those twelve are **not** game-specific.  What is game-specific is the four
constants they close over: the serial, the boot file, how large a container the
module will hold in memory, and which preload caches the disc ships.  So this
file is the operations, :class:`TerfDiscs` is the closure, and a game's own
``containers`` module is the constants plus its synthetic disc.

Why it is here rather than copied a fourth time.  ``ncaa09_ps2/containers.py``
is 981 lines and about six hundred of them are these operations verbatim;
``madden09_ps2/containers.py`` carries the same six hundred again.  Adding NFL
Street 1 and NFL Street 3 as two more copies would have made **four**, and the
next disc on this stack five.  The two Street modules instantiate this instead.
Madden 09 and NCAA 09 would collapse onto it with no behaviour change, and
deliberately have not been touched here: rewiring a shipped module is a change
to that module, and this branch's boundary is the two new ones.

**The `Discs` protocol is module-shaped**, not class-shaped -- a base reaches
``discs.open_disc(...)`` and ``discs.DiscError`` -- so a game binds these
methods onto its own module namespace.  A bound method satisfies the protocol
exactly as a module function does, and the game's module is still the thing a
lane names.

**Each game keeps its own** ``DiscError``.  It is passed in, so a refusal
raised from inside a shared operation reads as that game's refusal and a
``except containers.DiscError`` in a lane still catches it.

**Retail-free.**  Names, offsets, lengths, counts and digests.  Nothing here
reads a member's payload for any purpose but classifying it, nothing here
writes to the user's image, and no byte of any disc is in this file.

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_ql01, ea_terf

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TOOLS = _REPO_ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ps2_iso9660 as iso_lib  # noqa: E402

#: How much of a file is probed for the length its own chunk chain declares.
PROBE_BYTES = 1 << 16

#: What :meth:`TerfDiscs.classify` answers.
KIND_TERF = "TERF"
KIND_TDB = "TDB"
KIND_OTHER = "other"
KIND_UNREAD = "not-read"

#: Re-exported so a game names the shared types rather than its own aliases.
PreloadCopy = ea_ql01.PreloadCopy
ContainerPreload = ea_ql01.ContainerPreload
PRELOAD_KIND_HEADER = ea_ql01.PRELOAD_KIND_HEADER
PRELOAD_KIND_MEMBER = ea_ql01.PRELOAD_KIND_MEMBER


@dataclass(frozen=True)
class DataFile:
    """One file under ``/DATA``, as the disc's directory record describes it."""

    name: str
    path: str
    lba: int
    recorded_length: int


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


@dataclass(frozen=True)
class WritableContainer:
    """One container, bounded to the space the disc gave it, ready to rewrite."""

    entry: DataFile
    #: Exactly ``entry.recorded_length`` bytes.
    data: bytes
    parsed: ea_terf.TerfContainer
    #: What the container's own chunk chain says its length is.
    declared_length: int
    #: The game's refusal type, so :meth:`require_member_inside` speaks as it.
    error: type

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

        An edit that named one would be an edit the writer could only satisfy
        by growing the file, and the sentence says so with both sizes in it.
        """

        if not 0 <= index < self.parsed.member_count:
            raise self.error(
                f"{self.entry.path} has no member {index}: it holds "
                f"{self.parsed.member_count} (0..{self.parsed.member_count - 1})."
            )
        end = self.member_end(index)
        if end > len(self.data):
            raise self.error(
                f"{self.entry.path} member {index} ends at byte {end:,}, and this "
                f"image's own directory records the container as {len(self.data):,} "
                f"bytes against the {self.declared_length:,} it declares; rewriting a "
                f"member out there would have to grow the file, which this lane will "
                f"not do."
            )


class TerfDiscs:
    """The twelve generic ``/DATA`` operations, closed over one disc's constants.

    A game builds one of these and binds its methods onto its own module, so
    ``containers.open_disc`` is this ``open_disc`` and a lane base reaching
    ``discs.open_disc`` gets it without knowing this class exists.
    """

    def __init__(self, *, serial: str, title: str, error: type,
                 container_size_limit: int,
                 preload_caches: Sequence[str] = (),
                 data_directory: str = "/DATA") -> None:
        #: The disc serial a refusal names when the image is the wrong one.
        self.serial = serial
        #: What a sentence calls this game.
        self.title = title
        #: The game's own :class:`~mod_editor.games.contract.Refusal` subclass.
        self.error = error
        #: How large a container this module will hold in memory.
        self.container_size_limit = int(container_size_limit)
        #: The ``QL01`` caches this disc ships, upper-cased for lookup.
        self.preload_caches = tuple(name.upper() for name in preload_caches)
        #: Where the containers live.
        self.data_directory = data_directory

    # -- reading ---------------------------------------------------------

    def open_disc(self, path: Path) -> Any:
        """Open the user's image read-only, or refuse with one sentence."""

        try:
            return iso_lib.open_image(str(path))
        except (iso_lib.Iso9660Error, OSError, ValueError) as exc:
            raise self.error(
                str(exc).strip()
                or f"{path} could not be opened as a PlayStation 2 disc image."
            ) from exc

    def data_files(self, image: Any) -> Tuple[DataFile, ...]:
        """Every file under ``/DATA``, in the disc's own order.

        A disc with no ``/DATA`` directory is refused here rather than yielding
        an empty catalogue, because "there is nothing there" and "this is not
        the right disc" must not read the same.
        """

        found: List[DataFile] = []
        prefix = self.data_directory + "/"
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
            raise self.error(
                f"this image holds no files under {self.data_directory}, so it is not "
                f"a {self.title} disc. Choose the {self.serial} image."
            )
        return tuple(found)

    def read_extent(self, image: Any, lba: int, wanted: int) -> Optional[bytes]:
        """*wanted* bytes from the extent at *lba*, or ``None`` if not there.

        Addressed through the reader rather than by multiplying by a sector
        size: a raw-CD image's logical blocks are not contiguous in the file.
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

    def read_file(self, image: Any, entry: DataFile, *,
                  limit: Optional[int] = -1) -> bytes:
        """One ``/DATA`` file's bytes, honouring what the container declares.

        ISO9660 extents are whole sectors, so a container recorded short is
        still entirely on the disc; reading the directory record's length loses
        every member past the cut.  When the file's own chunk chain declares
        more than the record does, the extent is re-read to the declared
        length.  A file too large for *limit* is refused by name and size,
        never truncated.  ``limit=-1`` means this disc's own limit; ``None``
        means no limit.
        """

        if limit == -1:
            limit = self.container_size_limit
        if limit is not None and entry.recorded_length > limit:
            raise self.error(
                f"{entry.path} is {entry.recorded_length:,} bytes; this lane reads a "
                f"container into memory and stops at {limit:,}. It is listed with its "
                f"size and left unread."
            )
        iso_entry = iso_lib.find(image, entry.path)
        if iso_entry is None:
            raise self.error(f"{entry.path} is no longer on this image; re-open the disc.")
        try:
            data = iso_lib.read_file(image, iso_entry)
        except (iso_lib.Iso9660Error, OSError, ValueError) as exc:
            raise self.error(
                str(exc).strip() or f"{entry.path} could not be read off this image."
            ) from exc
        try:
            wanted = ea_terf.declared_length(data[:PROBE_BYTES])
        except ea_terf.TerfError:
            return data
        if wanted <= len(data):
            return data
        if limit is not None and wanted > limit:
            raise self.error(
                f"{entry.path} declares itself {wanted:,} bytes; this lane stops at "
                f"{limit:,}. It is listed with its size and left unread."
            )
        recovered = self.read_extent(image, entry.lba, wanted)
        return data if recovered is None else recovered

    def classify(self, image: Any, entry: DataFile) -> str:
        """``TERF``, ``TDB``, ``other`` or ``not-read``, from the first bytes."""

        iso_entry = iso_lib.find(image, entry.path)
        if iso_entry is None:
            return KIND_UNREAD
        head = self.read_extent(image, entry.lba, 16)
        if head is None:
            return KIND_UNREAD
        if head[:4] == ea_terf.TERF_MAGIC:
            return KIND_TERF
        if head[:2] == b"DB":
            return KIND_TDB
        return KIND_OTHER

    def describe_container(self, image: Any, entry: DataFile, *,
                           limit: Optional[int] = -1,
                           with_formats: bool = True
                           ) -> Tuple[ContainerReport, Optional[ea_terf.TerfContainer]]:
        """Walk one ``/DATA`` file and say what it holds, without a pixel.

        Returns the report and, when the file was a container small enough to
        read, the parsed container so a caller can go on to its members without
        a second read.  A refusal from the reader becomes a ``note`` on the
        row: one unreadable container must not empty the whole catalogue.
        """

        kind = self.classify(image, entry)
        if kind != KIND_TERF:
            note = "a bare EA TDB database rather than a TERF container." \
                if kind == KIND_TDB else ""
            return ContainerReport(name=entry.name, path=entry.path, kind=kind,
                                   recorded_length=entry.recorded_length,
                                   note=note), None
        try:
            data = self.read_file(image, entry, limit=limit)
        except Exception as exc:  # the game's own DiscError
            if not isinstance(exc, self.error):
                raise
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

    def load_container(self, image: Any, name: str, *,
                       limit: Optional[int] = -1) -> ea_terf.TerfContainer:
        """One named ``/DATA`` container, parsed, or a refusal naming the fix."""

        wanted = f"{self.data_directory}/{name}"
        for entry in self.data_files(image):
            if entry.path == wanted:
                data = self.read_file(image, entry, limit=limit)
                try:
                    return ea_terf.parse_terf(data, allow_size_mismatch=True)
                except ea_terf.TerfError as exc:
                    raise self.error(str(exc)) from exc
        raise self.error(
            f"this image holds no {wanted}; it is not a {self.title} disc, or the "
            f"container has been removed. Choose the {self.serial} image."
        )

    @staticmethod
    def member_uncached(container: ea_terf.TerfContainer, index: int) -> bytes:
        """One member, whole, without putting it in the container's cache.

        :meth:`TerfContainer.member` caches what it unpacks, which is right for
        a lane that comes back to the same member and wrong for one walking
        thousands in a row, where the cache is a pile nobody reads twice.
        Asking for exactly the declared size returns the whole member and skips
        the cache.
        """

        return container.member(index,
                                max_output=container.members[index].decompressed_size)

    def members_of_format(self, container: ea_terf.TerfContainer, wanted: str):
        """``(index, payload)`` for every member whose bytes are *wanted*.

        Walks in index order and skips an empty member without unpacking it, so
        a large container costs one pass and no member is held twice.
        """

        for index in range(container.member_count):
            if container.members[index].stored_size == 0:
                continue
            try:
                payload = self.member_uncached(container, index)
            except (ea_terf.TerfError, ValueError):
                continue
            if ea_terf.identify_member(payload) != wanted:
                continue
            yield index, payload

    # -- writing ---------------------------------------------------------

    def open_for_rewrite(self, image: Any, entry: DataFile, *,
                         limit: Optional[int] = -1) -> WritableContainer:
        """A container bounded to its ISO9660 record, or one sentence saying why not.

        The writer-side twin of :meth:`read_file`.  ``read_file`` recovers a
        recorded-short container to its declared length so a *reader* sees
        every member; this stops at the record, because the record is the
        allocation a fixed-allocation writer has, and hands the caller
        everything it needs to stay inside it.
        """

        data = self.read_file(image, entry, limit=limit)
        try:
            declared = ea_terf.declared_length(data[:PROBE_BYTES])
        except ea_terf.TerfError:
            declared = len(data)
        if len(data) > entry.recorded_length:
            data = data[:entry.recorded_length]
        if len(data) < entry.recorded_length:
            raise self.error(
                f"{entry.path} is {entry.recorded_length:,} bytes in this image's own "
                f"directory and only {len(data):,} could be read off it; the image is "
                f"truncated and nothing here writes into it."
            )
        try:
            parsed = ea_terf.parse_terf(data, allow_size_mismatch=True)
        except ea_terf.TerfError as exc:
            raise self.error(
                f"{entry.path} is {entry.recorded_length:,} bytes in this image's own "
                f"directory and declares {declared:,}; reading it as a container inside "
                f"the recorded length failed: {exc}"
            ) from exc
        beyond = [member.index for member in parsed.members
                  if member.stored_size
                  and parsed.data_offset + member.offset + member.stored_size > len(data)]
        if beyond:
            raise self.error(
                f"{entry.path} is {entry.recorded_length:,} bytes in this image's own "
                f"directory and declares {declared:,}, and member {beyond[0]} carries "
                f"bytes past the recorded end; a rewrite would have to grow the file, "
                f"which this lane will not do."
            )
        return WritableContainer(entry=entry, data=data, parsed=parsed,
                                 declared_length=declared, error=self.error)

    # -- the preload caches ----------------------------------------------

    def parse_preload_cache(self, data: bytes, cache: str) -> Tuple[Any, ...]:
        """The copies a ``QL01`` cache carries, or a refusal naming what was found."""

        try:
            return ea_ql01.parse_cache(data, cache)
        except ea_ql01.Ql01Error as exc:
            raise self.error(str(exc)) from exc

    def preload_names(self, image: Any) -> Dict[str, Tuple[str, ...]]:
        """``{cache: (container name, ...)}`` read off the user's own image.

        The conservative floor a writer asks before it touches a container: a
        container a cache names is one whose directory the cache may be
        carrying a stale copy of.  :meth:`preload_copies` is the exact answer;
        this is the one that still works when a cache cannot be walked.
        """

        out: Dict[str, Tuple[str, ...]] = {}
        for entry in self.data_files(image):
            if entry.name.upper() not in self.preload_caches:
                continue
            try:
                head = self.read_file(image, entry, limit=None)
                out[entry.name] = ea_ql01.cache_names(head, entry.name)
            except (ea_ql01.Ql01Error, Exception) as exc:  # noqa: B014
                if not isinstance(exc, (ea_ql01.Ql01Error, self.error)):
                    raise
                continue
        return out

    def preload_copies(self, image: Any, *,
                       caches: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        """``container name -> ContainerPreload`` for every cache on this image.

        The one method every lane that writes a container calls, so the
        coherence rule lives in one place.  Every copy is filed under the
        container whose bytes it **is**, which for a row at a container
        boundary is not always the one its ``DTLS`` row names;
        :func:`ea_ql01.attribute` measures rather than guesses.
        """

        wanted = self.preload_caches if caches is None else tuple(caches)
        try:
            return ea_ql01.collect(wanted, _CopySource(self, image))
        except ea_ql01.Ql01Error as exc:
            raise self.error(str(exc)) from exc


class _CopySource:
    """What :func:`ea_ql01.collect` asks of an image, answered read-only."""

    def __init__(self, discs: TerfDiscs, image: Any) -> None:
        self._discs = discs
        self._image = image
        self._entries = {entry.name.upper(): entry for entry in discs.data_files(image)}

    def names(self) -> Tuple[str, ...]:
        return tuple(self._entries)

    def shape(self, name: str) -> Optional[Any]:
        entry = self._entries.get(name.upper())
        if entry is None:
            return None
        head = self._discs.read_extent(self._image, entry.lba,
                                       min(PROBE_BYTES, entry.recorded_length))
        return None if head is None else ea_ql01.container_shape(head)

    def bytes_at(self, name: str, start: int, length: int) -> Optional[bytes]:
        entry = self._entries.get(name.upper())
        if entry is None:
            return None
        whole = self._discs.read_extent(self._image, entry.lba, start + length)
        return None if whole is None else whole[start:start + length]

    def cache_bytes(self, name: str) -> Optional[bytes]:
        entry = self._entries.get(name.upper())
        if entry is None:
            return None
        try:
            return self._discs.read_file(self._image, entry, limit=None)
        except Exception as exc:  # the game's own DiscError
            if not isinstance(exc, self._discs.error):
                raise
            return None


# ----------------------------------------------------------------------
# What CI proves a lane on: the pieces of a synthetic disc
# ----------------------------------------------------------------------
#
# No game data may enter this repository, so every lane's conformance run works
# off an image built here.  Each piece is computed, never sampled.

SYNTHETIC_TEXT_LINES = (
    "SYNTHETIC STRING BANK ENTRY NUMBER ONE",
    "SYNTHETIC STRING BANK ENTRY NUMBER TWO",
    "SYNTHETIC STRING BANK ENTRY NUMBER THREE",
)


def synthetic_text_member(lines: Sequence[str] = SYNTHETIC_TEXT_LINES) -> bytes:
    """A ``TEXT`` member: NUL-terminated printable strings, as the format has them."""

    body = b"".join(line.encode("latin-1", "replace") + b"\x00" for line in lines)
    return body if body else b"\x00"


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
        name.encode("latin-1").ljust(ea_ql01.QL01_NAME_STRIDE, b"\x00") for name in names)
    files_chunk = (ea_ql01.QL01_FILS
                   + struct.pack("<I", ea_ql01.QL01_CHUNK_HEADER + len(files)) + files)

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
    entries_chunk = (ea_ql01.QL01_DTLS
                     + struct.pack("<I", ea_ql01.QL01_CHUNK_HEADER + len(entries)) + entries)

    head_length = (12 + len(files_chunk) + len(entries_chunk) + ea_ql01.QL01_CHUNK_HEADER)
    out = bytearray()
    out += ea_ql01.QL01_MAGIC + struct.pack("<II", 12, head_length)
    out += files_chunk
    out += entries_chunk
    out += ea_ql01.QL01_DATA_TAG + struct.pack("<I", 0)
    out += body
    return bytes(out)


def container_directory(blob: bytes) -> bytes:
    """A container's first ``data_offset`` bytes: what a cache copies as a header."""

    return blob[:ea_terf.parse_terf(blob).data_offset]


def build_synthetic_iso(*, boot_file: str,
                        sub_files: Sequence[Tuple[bytes, bytes]],
                        sub_name: bytes = b"DATA") -> bytes:
    """A tiny image with a ``SYSTEM.CNF``, a stub boot ELF and the files given."""

    boot = (b"BOOT2 = cdrom0:\\%s;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n"
            % boot_file.encode("ascii"))
    return iso_lib.build_synthetic_iso(
        files=[(b"SYSTEM.CNF;1", boot),
               (boot_file.encode("ascii") + b";1", b"\x7fELF" + bytes(4092))],
        sub_name=sub_name,
        sub_files=list(sub_files),
    )


__all__ = [
    "ContainerPreload", "ContainerReport", "DataFile", "KIND_OTHER", "KIND_TDB",
    "KIND_TERF", "KIND_UNREAD", "PROBE_BYTES", "PRELOAD_KIND_HEADER",
    "PRELOAD_KIND_MEMBER", "PreloadCopy", "SYNTHETIC_TEXT_LINES", "TerfDiscs",
    "WritableContainer", "build_synthetic_iso", "build_synthetic_preload_cache",
    "container_directory", "synthetic_text_member",
]
