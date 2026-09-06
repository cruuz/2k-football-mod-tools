"""Reading NFL Blitz 2003 (PS2) off the user's own disc, and the synthetic disc CI proves lanes on.

Every lane in this module starts here.  The disc holds 36 files, and 2,426 of the
37 things a modder could want are inside **one** of them: ``/DATA/BERTHA.ZIP``,
a ZIP whose every member is stored, with ``/DATA/BERTHA.ZIH`` beside it -- the
Midway index that carries the same names, sizes, offsets and CRC-32s [M].  The
shared readers open both: :mod:`mod_editor.games._formats.blitz_zip` for the
pair and :mod:`~mod_editor.games._formats.rw_txd` for the RenderWare texture
dictionaries inside it.  This file is the *game-specific* half: which disc this
is, which members feed which page, how the pair is read in place off the image,
and how to build a synthetic image carrying every shape a lane touches.

**The three-place rule governs every writer here.**  A member is replaced at its
own byte range with a payload of its own length; its CRC-32 is then rewritten in
the local file header, the central directory and the ``.ZIH`` index.  Because
both files are whole ISO9660 files, a build is two file replacements handed to
the shared image writer, and the image's own length never changes.

What is on the disc, by member extension [M]::

    dff 1272   RenderWare clump streams        rtd  761   texture dictionaries
    wip  149   WIFF, big-endian RIFF           cap   85   CPTH camera paths
    trv   40   40-byte trivia line records     rsc   36   RYWM, unread
    ini   31   crowd tables, CRLF ASCII        wom   23   WIFF
    wmp   18   WIFF                            ban    4   EKAB, unread
    asd    2                                   ico    2   PS2 save icons
    ms2    1   Midway sound bank (out of scope) rst   1   the roster
    tab    1   field.tab, CRLF ASCII

**Evidence tags.**  **[M]** measured on the retail SLUS-20474 disc this box
holds, read-only; **[S]** sourced from ``docs/owner/scoping/BLITZ_AND1_FORMATS.md``
and the owner's disc map; **[A]** assumed.

**Retail-free.**  Names, offsets, lengths, counts and digests only.  Nothing
here writes to the user's image.

Standard library only; importable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from mod_editor.games._formats import blitz_zip, rw_txd
from mod_editor.games.contract import Refusal

_ROOT = Path(__file__).resolve().parents[3]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ps2_iso9660 as iso_lib  # noqa: E402

# --------------------------------------------------------------------------
# Identity [M]
# --------------------------------------------------------------------------

GAME_ID = "nflblitz2003_ps2"
TITLE = "NFL Blitz 2003 (USA, PlayStation 2)"
SERIAL = "SLUS-20474"
BOOT_FILE = "SLUS_204.74"
#: SHA-256 of the boot ELF on the USA disc: 2,417,112 bytes [M].
RETAIL_BOOT_ELF_SHA256 = "57cba3a86145a8c315e60b04089ba5d0e7c31d58859096fb0f85c4b2771039a0"
#: SHA-256 of the whole USA image: 1,029,144,576 bytes, 22 files / 2 dirs [M].
RETAIL_IMAGE_SHA256 = "7927f812724eb7c30d672903c5c277b5358d25d20b61b1590d376a796270d513"
#: PCSX2's CRC for that executable [S].  Recorded, never used as a key.
RETAIL_ELF_CRC = "49A00204"

#: The pair.  NFL Blitz 2002 names its ``BASSETS``; the name and the index's
#: record shape are the only differences a lane sees, which is why both are
#: constants and not literals [M].
ARCHIVE_PATH = "/DATA/BERTHA.ZIP"
INDEX_PATH = "/DATA/BERTHA.ZIH"

# --------------------------------------------------------------------------
# What feeds which page [M]
# --------------------------------------------------------------------------

#: The team crowd tables.  31 on the 2002 disc, one per NFL team of the 2001
#: season; the 2003 disc adds ``ht_`` for the Houston Texans [M].
CROWD_SUFFIX = "_crowd.ini"
#: The one gameplay table on the disc, a CRLF ASCII file whose first line is a
#: ``#`` comment [M].
FIELD_TABLE = "field.tab"
#: The trivia banks: 40 members of fixed 40-byte NUL-padded ASCII records [M].
TRIVIA_SUFFIX = ".trv"
#: The credits, on the 2003 disc only [M].
LOOSE_TEXT = ("credits.txt",)
#: The roster: 41 blocks of ``u32 18`` + 18 x 100-byte records [M].
ROSTER_MEMBER = "roster.rst"
ROSTER_BLOCK_BYTES = 1804
ROSTER_RECORDS_PER_BLOCK = 18
ROSTER_RECORD_BYTES = 100
#: The two 32-byte NUL-terminated name fields of a roster record [M].
ROSTER_FIRST_NAME_AT = 0
ROSTER_LAST_NAME_AT = 32
ROSTER_NAME_BYTES = 32
#: Byte +68 of a record equals its block's ordinal in 738 of 738 records on the
#: 2002 disc and 756 of 756 on the 2003 disc [M]: the team index.
ROSTER_TEAM_BYTE = 68
#: Uninitialised MSVC heap fill, which is what pads a short name [M].
ROSTER_FILL = 0xCD

#: A texture dictionary named ``<two letters>_...`` belongs to a team [M].
TEAM_TEXTURE_SUFFIXES = ("_glogo.rtd",)
TEXTURE_SUFFIX = ".rtd"
#: Camera paths.  The owner's scoping study names these ``HTPC``, which is the
#: little-endian *word* reading; the bytes on the disc are ``CPTH`` [M].
#: ``16 + records * 32 == the member`` on 85 of 85 and 88 of 88 [M].
CAMERA_SUFFIX = ".cap"
CAMERA_MAGIC = b"CPTH"
CAMERA_HEADER_BYTES = 16
CAMERA_RECORD_BYTES = 32
#: RenderWare clump streams [M].
MODEL_SUFFIX = ".dff"
#: ``WIFF``: a big-endian RIFF whose declared size + 8 is the member, on
#: 190 of 190 members of the 2002 disc and 209 of 209 of the 2003 disc [M].
WIFF_SUFFIXES = (".wip", ".wom", ".wmp")
WIFF_MAGIC = b"WIFF"
#: The Midway sound bank.  Another module owns the ``.MS2`` format; this one
#: names the member and never opens it.
SOUND_BANK_MEMBER = "mslasset.ms2"

#: How large a member this module reads whole into memory.  ``mslasset.ms2`` is
#: 137 MB and is never read; the largest member a lane touches is 1.1 MB [M].
MEMBER_SIZE_LIMIT = 8 * 1024 * 1024

#: Bounded output: a page lists at most this many rows while the catalogue
#: document's totals stay complete.
MAX_TARGETS = 3000


class DiscError(Refusal):
    """This module could not read what it was pointed at; the sentence says why."""


@dataclass(frozen=True)
class Pair:
    """The ZIP and its index, as byte ranges of one image."""

    archive_offset: int
    archive_bytes: int
    index_offset: int
    index_bytes: int


class Disc:
    """The user's image, opened read-only, with the stored ZIP read in place."""

    #: Overridden by the NFL Blitz 2003 module; every other member is shared.
    archive_path = ARCHIVE_PATH
    index_path = INDEX_PATH
    serial = SERIAL
    title = TITLE

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        try:
            self.image = iso_lib.open_image(str(self.path))
        except (iso_lib.Iso9660Error, OSError, ValueError) as exc:
            raise DiscError(str(exc).strip()
                            or f"{path} could not be opened as a PlayStation 2 disc "
                               f"image.") from exc
        self._handle = open(self.path, "rb")
        self._archive: Optional[blitz_zip.StoredZip] = None
        self._index: Optional[blitz_zip.ZihIndex] = None

    def close(self) -> None:
        try:
            self._handle.close()
        except OSError:
            pass

    def __enter__(self) -> "Disc":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    # -- the image ----------------------------------------------------------

    def _entry(self, path: str) -> Any:
        found = iso_lib.find(self.image, path)
        if found is None or found.is_dir:
            raise DiscError(
                f"this image holds no {path}; it is not an {self.title} disc, or the file "
                f"has been removed. Choose the {self.serial} image.")
        return found

    def read(self, offset: int, length: int) -> bytes:
        self._handle.seek(offset)
        return self._handle.read(length)

    def pair(self) -> Pair:
        archive = self._entry(self.archive_path)
        index = self._entry(self.index_path)
        return Pair(iso_lib.extent_byte_offset(self.image, archive.lba, 0), int(archive.length),
                    iso_lib.extent_byte_offset(self.image, index.lba, 0), int(index.length))

    # -- the pair -----------------------------------------------------------

    def archive(self) -> blitz_zip.StoredZip:
        """The stored ZIP, read through its central directory, never copied."""

        if self._archive is None:
            where = self.pair()
            base = where.archive_offset

            def read(offset: int, length: int) -> bytes:
                return self.read(base + offset, length)

            self._archive = blitz_zip.read_zip(read, where.archive_bytes)
        return self._archive

    def index(self) -> blitz_zip.ZihIndex:
        if self._index is None:
            where = self.pair()
            self._index = blitz_zip.read_index(
                self.read(where.index_offset, where.index_bytes))
        return self._index

    def archive_bytes(self) -> bytes:
        where = self.pair()
        return self.read(where.archive_offset, where.archive_bytes)

    def index_bytes(self) -> bytes:
        where = self.pair()
        return self.read(where.index_offset, where.index_bytes)

    def member_bytes(self, name: str, *, limit: Optional[int] = MEMBER_SIZE_LIMIT) -> bytes:
        member = self.archive().member(name)
        if limit is not None and member.size > limit:
            raise DiscError(
                f"{name} is {member.size:,} bytes; this lane reads a member into memory and "
                f"stops at {limit:,}. It is listed with its size and left unread.")
        return self.archive().member_bytes(name)

    def head(self, name: str, count: int = 16) -> bytes:
        member = self.archive().member(name)
        where = self.pair()
        return self.read(where.archive_offset + member.data_offset, min(count, member.size))

    # -- selections a page cares about --------------------------------------

    def members_named(self, *, suffix: str = "", prefix: str = "",
                      exact: Sequence[str] = ()) -> Tuple[blitz_zip.ZipMember, ...]:
        wanted = {name.lower() for name in exact}
        out = []
        for member in self.archive().members:
            lowered = member.name.lower()
            if wanted and lowered in wanted:
                out.append(member)
            elif suffix and lowered.endswith(suffix.lower()) and lowered.startswith(prefix.lower()):
                out.append(member)
        return tuple(sorted(out, key=lambda member: member.name))

    def texture_dictionary(self, name: str) -> rw_txd.Dictionary:
        try:
            return rw_txd.read_dictionary(self.member_bytes(name), name)
        except rw_txd.RwTxdError as exc:
            raise DiscError(str(exc)) from exc


# --------------------------------------------------------------------------
# Text members: the line slots a writer edits
# --------------------------------------------------------------------------

#: The two shapes of text member on the disc [M]: ``.trv`` is a run of fixed
#: 40-byte NUL-padded records, and every other text member is CRLF ASCII.
TRIVIA_RECORD_BYTES = 40
KIND_FIXED = "fixed"
KIND_CRLF = "crlf"


@dataclass(frozen=True)
class LineSlot:
    """One editable line: where it is, how many bytes it owns, and what pads it."""

    number: int
    offset: int
    span: int
    text: str
    kind: str

    @property
    def budget(self) -> str:
        return f"{self.span} bytes, padded with " + (
            "NUL" if self.kind == KIND_FIXED else "spaces")


def text_kind(name: str) -> str:
    return KIND_FIXED if name.lower().endswith(TRIVIA_SUFFIX) else KIND_CRLF


def read_line_slots(name: str, payload: bytes) -> Tuple[LineSlot, ...]:
    """The line slots of a text member, in file order.

    A ``.trv`` member is ``size % 40 == 0`` on 40 of 40 members of each disc and
    every record is printable ASCII padded with NUL [M]; every other text member
    is printable ASCII with CRLF endings, 32 of 32 on the 2002 disc and 34 of 34
    on the 2003 disc [M].  A line's span is its own bytes, never the terminator.
    """

    kind = text_kind(name)
    slots: List[LineSlot] = []
    if kind == KIND_FIXED:
        if len(payload) % TRIVIA_RECORD_BYTES:
            raise DiscError(
                f"{name} is {len(payload)} bytes, which is not a whole number of "
                f"{TRIVIA_RECORD_BYTES}-byte records; it is not a Blitz trivia bank.")
        for number in range(len(payload) // TRIVIA_RECORD_BYTES):
            start = number * TRIVIA_RECORD_BYTES
            raw = payload[start:start + TRIVIA_RECORD_BYTES]
            slots.append(LineSlot(number, start, TRIVIA_RECORD_BYTES,
                                  raw.split(b"\x00", 1)[0].decode("latin-1"), kind))
        return tuple(slots)
    position = 0
    number = 0
    while position < len(payload):
        end = payload.find(b"\r\n", position)
        if end < 0:
            end = len(payload)
        slots.append(LineSlot(number, position, end - position,
                              payload[position:end].decode("latin-1"), kind))
        number += 1
        position = end + 2
    return tuple(slots)


def write_line_slot(payload: bytes, slot: LineSlot, text: str) -> bytes:
    """``payload`` with one slot's text replaced, padded to the slot's own span."""

    raw = text.encode("latin-1", "strict")
    if len(raw) > slot.span:
        raise DiscError(
            f"line {slot.number} owns {slot.span} bytes and the replacement is {len(raw)}; "
            f"shorten it to {slot.span} characters or fewer.")
    pad = b"\x00" if slot.kind == KIND_FIXED else b" "
    out = bytearray(payload)
    out[slot.offset:slot.offset + slot.span] = raw + pad * (slot.span - len(raw))
    return bytes(out)


# --------------------------------------------------------------------------
# The roster
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RosterPlayer:
    """One roster record: which block it is in, and where its two names live."""

    block: int
    slot: int
    offset: int
    first: str
    last: str
    team_byte: int


def read_roster(payload: bytes, name: str = ROSTER_MEMBER) -> Tuple[RosterPlayer, ...]:
    """The roster's blocks and records, refusing anything that is not the measured shape.

    ``roster.rst`` is 73,964 bytes on the 2002 disc and 75,768 on the 2003 disc,
    which is exactly 41 and 42 blocks of 1,804 [M].  Every block opens with the
    word 18 -- 41 of 41 and 42 of 42 -- and every one of the 738 and 756 records
    carries two NUL-terminated ASCII name fields [M].
    """

    if len(payload) == 0 or len(payload) % ROSTER_BLOCK_BYTES:
        raise DiscError(
            f"{name} is {len(payload)} bytes, which is not a whole number of "
            f"{ROSTER_BLOCK_BYTES}-byte blocks; it is not the Blitz roster.")
    out: List[RosterPlayer] = []
    for block in range(len(payload) // ROSTER_BLOCK_BYTES):
        base = block * ROSTER_BLOCK_BYTES
        declared = struct.unpack_from("<I", payload, base)[0]
        if declared != ROSTER_RECORDS_PER_BLOCK:
            raise DiscError(
                f"{name}: block {block} declares {declared} records and every block of the "
                f"Blitz roster declares {ROSTER_RECORDS_PER_BLOCK}; this is not that file.")
        for slot in range(ROSTER_RECORDS_PER_BLOCK):
            at = base + 4 + slot * ROSTER_RECORD_BYTES
            first = _name_field(payload, at + ROSTER_FIRST_NAME_AT, name, block, slot)
            last = _name_field(payload, at + ROSTER_LAST_NAME_AT, name, block, slot)
            out.append(RosterPlayer(block, slot, at, first, last,
                                    payload[at + ROSTER_TEAM_BYTE]))
    return tuple(out)


def _name_field(payload: bytes, at: int, name: str, block: int, slot: int) -> str:
    raw = payload[at:at + ROSTER_NAME_BYTES]
    end = raw.find(b"\x00")
    if end <= 0:
        raise DiscError(
            f"{name}: block {block} record {slot} has a name field that is not NUL-terminated "
            f"ASCII; this is not the Blitz roster.")
    text = raw[:end]
    if any(byte < 0x20 or byte > 0x7E for byte in text):
        raise DiscError(
            f"{name}: block {block} record {slot} has a name field carrying a byte outside "
            f"printable ASCII; this is not the Blitz roster.")
    return text.decode("latin-1")


def write_roster_name(payload: bytes, player: RosterPlayer, which: str, text: str) -> bytes:
    """``payload`` with one 32-byte name field replaced, NUL-terminated and 0xCD-padded."""

    at = player.offset + (ROSTER_FIRST_NAME_AT if which == "first" else ROSTER_LAST_NAME_AT)
    raw = text.encode("latin-1", "strict")
    if len(raw) + 1 > ROSTER_NAME_BYTES:
        raise DiscError(
            f"a name field holds {ROSTER_NAME_BYTES} bytes including its terminator and "
            f"{text!r} needs {len(raw) + 1}; shorten it to {ROSTER_NAME_BYTES - 1} characters "
            f"or fewer.")
    out = bytearray(payload)
    out[at:at + ROSTER_NAME_BYTES] = (
        raw + b"\x00" + bytes([ROSTER_FILL]) * (ROSTER_NAME_BYTES - len(raw) - 1))
    return bytes(out)


# --------------------------------------------------------------------------
# The synthetic disc: what CI proves lanes on, with no game data
# --------------------------------------------------------------------------

#: The team prefixes the synthetic disc carries.  Invented here, not read off
#: any disc: two of them, so a lane that groups by prefix has something to group.
SYNTHETIC_TEAMS = ("aa", "bb")
SYNTHETIC_ROSTER_BLOCKS = 2


def _synthetic_roster() -> bytes:
    out = bytearray()
    for block in range(SYNTHETIC_ROSTER_BLOCKS):
        out += struct.pack("<I", ROSTER_RECORDS_PER_BLOCK)
        for slot in range(ROSTER_RECORDS_PER_BLOCK):
            record = bytearray(bytes([ROSTER_FILL]) * ROSTER_RECORD_BYTES)
            for at, text in ((ROSTER_FIRST_NAME_AT, f"Fixture{slot}"),
                             (ROSTER_LAST_NAME_AT, f"Block{block}")):
                raw = text.encode("latin-1")
                record[at:at + ROSTER_NAME_BYTES] = (
                    raw + b"\x00" + bytes([ROSTER_FILL]) * (ROSTER_NAME_BYTES - len(raw) - 1))
            record[ROSTER_TEAM_BYTE] = block
            out += record
    return bytes(out)


def _synthetic_trivia(lines: int = 6) -> bytes:
    out = bytearray()
    for number in range(lines):
        raw = ("fixture trivia line %d" % number).encode("latin-1")
        out += raw + bytes(TRIVIA_RECORD_BYTES - len(raw))
    return bytes(out)


def _synthetic_crowd(team: str) -> bytes:
    lines = ["8,16", f"# {team} fixture crowd table", "0,0,0,0", "1,1,1,1"]
    return "\r\n".join(lines).encode("latin-1") + b"\r\n"


def _synthetic_camera(records: int = 4) -> bytes:
    head = CAMERA_MAGIC + struct.pack("<3I", 5, records, 0)
    return head + bytes(records * CAMERA_RECORD_BYTES)


def _synthetic_wiff(form: bytes = b"WIPS", body: int = 32) -> bytes:
    return WIFF_MAGIC + struct.pack(">I", 4 + body) + form + bytes(body)


def synthetic_members() -> List[Tuple[str, bytes]]:
    """Every member shape a lane in this module touches, built here byte by byte."""

    palette = [(index, (index * 3) & 0xFF, (255 - index) & 0xFF, 0x80) for index in range(256)]
    indices = bytes(((x * 7 + y * 3) & 0xFF) for y in range(32) for x in range(64))
    members: List[Tuple[str, bytes]] = [
        (ROSTER_MEMBER, _synthetic_roster()),
        (FIELD_TABLE, b"# Fixture field table\r\n1,2,3\r\n4,5,6\r\n"),
        ("tr2002000" + TRIVIA_SUFFIX, _synthetic_trivia()),
        ("tr2002001" + TRIVIA_SUFFIX, _synthetic_trivia(4)),
        ("afterplay_cam" + CAMERA_SUFFIX, _synthetic_camera()),
        ("halftime" + WIFF_SUFFIXES[0], _synthetic_wiff()),
        ("fixture" + MODEL_SUFFIX, struct.pack("<3I", rw_txd.ID_STRUCT, 4, 0x0401FFFF) + bytes(4)),
        ("menu_screen" + TEXTURE_SUFFIX,
         rw_txd.build_synthetic_dictionary([("menu_a", 64, 32, indices, palette)])),
    ]
    for team in SYNTHETIC_TEAMS:
        members.append((team + CROWD_SUFFIX, _synthetic_crowd(team)))
        members.append((team + TEAM_TEXTURE_SUFFIXES[0],
                        rw_txd.build_synthetic_dictionary(
                            [(team + "_logo", 64, 32, indices, palette)])))
    return members


def build_synthetic_disc(*, archive_path: str = ARCHIVE_PATH, index_path: str = INDEX_PATH,
                         shape: str = blitz_zip.SHAPE_TABLE,
                         boot_file: str = BOOT_FILE) -> bytes:
    """A PS2-shaped image carrying the ZIP pair, in either index shape.

    Retail-free by construction: every byte comes from :func:`synthetic_members`
    or from the shared ISO9660 builder.
    """

    archive = blitz_zip.build_synthetic_zip(synthetic_members())
    index = blitz_zip.build_synthetic_index(archive, shape=shape)
    system_cnf = (f"BOOT2 = cdrom0:\\{boot_file};1\r\nVER = 1.00\r\nVMODE = NTSC\r\n"
                  ).encode("latin-1")
    directory = archive_path.strip("/").split("/")[0]
    return iso_lib.build_synthetic_iso(
        files=[(f"{boot_file};1".encode("latin-1"), b"\x7fELF" + bytes(60)),
               (b"SYSTEM.CNF;1", system_cnf)],
        sub_name=directory.encode("latin-1"),
        sub_files=[(archive_path.rsplit("/", 1)[-1].encode("latin-1") + b";1", archive),
                   (index_path.rsplit("/", 1)[-1].encode("latin-1") + b";1", index)])


__all__ = [
    "ARCHIVE_PATH", "CAMERA_HEADER_BYTES", "CAMERA_MAGIC", "CAMERA_RECORD_BYTES",
    "CAMERA_SUFFIX", "CROWD_SUFFIX", "Disc", "DiscError", "FIELD_TABLE", "GAME_ID",
    "INDEX_PATH", "KIND_CRLF", "KIND_FIXED", "LineSlot", "LOOSE_TEXT", "MAX_TARGETS",
    "MEMBER_SIZE_LIMIT", "MODEL_SUFFIX", "Pair", "RETAIL_BOOT_ELF_SHA256",
    "RETAIL_IMAGE_SHA256", "ROSTER_BLOCK_BYTES", "ROSTER_MEMBER", "ROSTER_NAME_BYTES",
    "ROSTER_RECORDS_PER_BLOCK", "ROSTER_RECORD_BYTES", "RosterPlayer", "SERIAL",
    "SOUND_BANK_MEMBER", "TEAM_TEXTURE_SUFFIXES", "TEXTURE_SUFFIX", "TITLE",
    "TRIVIA_RECORD_BYTES", "TRIVIA_SUFFIX", "WIFF_MAGIC", "WIFF_SUFFIXES",
    "build_synthetic_disc", "read_line_slots", "read_roster", "synthetic_members",
    "text_kind", "write_line_slot", "write_roster_name",
]
