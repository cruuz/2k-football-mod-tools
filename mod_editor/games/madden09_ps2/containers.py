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

from dataclasses import dataclass
from pathlib import Path
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
SYNTHETIC_CONTAINERS = (UNIFORM_CONTAINER, TEAM_DATABASE_CONTAINER)


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
                   bits: int = 8, mips: int = 1, palette_only_extra: bool = False) -> bytes:
    """An ``MMAP`` member built from the format's own rules, not from a disc.

    ``MMAP`` is a table-of-tables -- an image table, a surface table (one row
    per mip level), a palette table and a name table, each addressed by an
    offset in the 40-byte header -- and this builds all of it.  See
    :mod:`.mmap_art` for the layout and the evidence behind it.

    *mips* adds halved levels after the base one, and *palette_only_extra*
    appends the second image entry the real containers carry: a row with no
    surfaces whose job is to hold an alternate CLUT for the first image.  Both
    exist so a lane's handling of them is exercised without a game.
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


def build_synthetic_disc(*, tdb_member: Optional[bytes] = None) -> bytes:
    """A tiny ``SLUS-21770``-shaped image carrying two synthetic containers.

    ``UNIFORMS.DAT`` is built as a ``COMP`` container whose members are stored
    -- the shape the retail disc itself ships for 270 of that container's 725
    members [M], so a lane proved here is proved on a layout the game loads --
    and ``DB_TEAMS.DAT`` as a plain ``DATA`` container.  Every byte comes from
    :func:`ea_terf.build_terf` and the builders above; no game data is
    involved, which is what lets the conformance harness run this on a machine
    that owns none of these discs.
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
    team_members = [
        tdb_member if tdb_member is not None else b"",
        synthetic_text_member(SYNTHETIC_TEXT_LINES),
    ]
    teams = ea_terf.build_terf([m for m in team_members], chunk="DATA")
    boot = b"BOOT2 = cdrom0:\\%s;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n" % BOOT_FILE.encode("ascii")
    return iso_lib.build_synthetic_iso(
        files=[
            (b"SYSTEM.CNF;1", boot),
            (BOOT_FILE.encode("ascii") + b";1", b"\x7fELF" + bytes(4092)),
        ],
        sub_name=b"DATA",
        sub_files=[
            (UNIFORM_CONTAINER.encode("ascii") + b";1", uniforms),
            (TEAM_DATABASE_CONTAINER.encode("ascii") + b";1", teams),
        ],
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
    "PROBE_BYTES",
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
    "classify",
    "data_files",
    "describe_container",
    "load_container",
    "member_uncached",
    "members_of_format",
    "open_disc",
    "read_file",
    "synthetic_indices",
    "synthetic_mmap",
    "synthetic_palette",
    "synthetic_text_member",
]
