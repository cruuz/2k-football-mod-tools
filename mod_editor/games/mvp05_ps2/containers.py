"""Reading MVP Baseball 2005 (PS2) off the user's own disc, and the synthetic disc CI proves lanes on.

Every lane in this module starts here.  The disc is 211 EA ``BIG`` archives,
three ``LOCH`` string files and a tree of EA ``SCHl`` audio under ``/DATA``
[M]; the shared readers (:mod:`mod_editor.games._formats.ea_big`,
:mod:`~mod_editor.games._formats.ea_shps`, :mod:`~mod_editor.games._formats.ea_schl`,
:mod:`~mod_editor.games._formats.ea_csv_db`) open all of it, so this file is
only the *game-specific* half: which disc this is, which archives feed which
page, how an archive is read in place off the image, and how to build a
synthetic image carrying every shape a lane touches so the conformance
harness can prove a lane on a machine that owns no disc.

**Evidence tags.**  **[M]** measured on the retail SLUS-21135 disc this box
holds; **[S]** sourced from ``docs/product/MVP05_PS2_MODULE_PLAN.md`` and the
owner's disc map; **[A]** assumed.

**Retail-free.**  Names, offsets, lengths, counts and digests only.  Nothing
here writes to the user's image.

Standard library only; importable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import sys
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_big, ea_csv_db, ea_schl, ea_shps
from mod_editor.games.contract import Refusal

_ROOT = Path(__file__).resolve().parents[3]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ps2_iso9660 as iso_lib  # noqa: E402

# --------------------------------------------------------------------------
# Identity [M]
# --------------------------------------------------------------------------

SERIAL = "SLUS-21135"
BOOT_FILE = "SLUS_211.35"
#: SHA-256 of the boot ELF on the USA disc: 8,130,840 bytes [M].
RETAIL_BOOT_ELF_SHA256 = "14db3aa3660e526ce12423db8102ce138e34f252985543406ff67a753e5c4615"
#: SHA-256 of the whole USA image: 4,300,275,712 bytes, 434 files / 30 dirs [S].
RETAIL_IMAGE_SHA256 = "90ed5e7974fc6f4374b43f6de19a984609c75dde94bc632a2f0940f8267b6484"
#: PCSX2's CRC for that executable [S].  Recorded, never used as a key.
RETAIL_ELF_CRC = "0544E001"
RETAIL_EDITION = "retail"

DATA_DIRECTORY = "/DATA"

# --------------------------------------------------------------------------
# What feeds which page [M]
# --------------------------------------------------------------------------

#: The rosters: 18 RefPack-packed CSV tables [M].
DATABASE_ARCHIVE = "DATABASE.BIG"
#: The four tables in it that are team identity rather than players [M].
IDENTITY_TABLES = ("team.dat", "org.dat", "tstat.dat", "manager.dat")
#: The tuning archives: progression and contract curves (8 stored CSVs), the
#: draft-class generator (26 packed), the schedules (9 packed) and the two
#: audio event-table archives (33 stored) [M].
TUNING_ARCHIVES = ("PROGRESS.BIG", "ROOKIE.BIG", "SCHEDULE.BIG", "SPEECHDB.BIG", "AUDIOCSV.BIG")

UNIFORM_ARCHIVES = ("UNIFORMS.BIG", "COOPUNIS.BIG")
FACE_ARCHIVES = ("PORTRAIT.BIG", "GHEAD.BIG")
FIELD_ART_ARCHIVES = ("FIELDS.BIG", "BPSETUP.BIG", "BPITEMS.BIG", "BPUPGRAD.BIG",
                      "BPTICKET.BIG", "BPPROMOS.BIG", "BPVENDOR.BIG", "BPATTRAC.BIG")
#: The 87 ballpark archives live in this directory, one per park per lighting [M].
STADIUM_DIRECTORY = "STADIUM"
STADIUM_MENU_ARCHIVES = ("STADIUMS.BIG", "COOPSTAD.BIG")
PRESENTATION_ARCHIVES = ("IGONLY.BIG", "COOPOV.BIG", "HRSONLY.BIG")
PRESENTATION_SCRIPT_ARCHIVES = ("INGAME.BIG", "COOPLAY.BIG")
MENU_ARCHIVES = ("FEONLY.BIG", "FEONLYCM.BIG", "SHARED.BIG", "SUSHARED.BIG", "SUONLY.BIG",
                 "EASOART.BIG", "MINIBAT.BIG", "MINIPIT.BIG", "MINIGAME.BIG", "MISC.BIG",
                 "BKGNDS.BIG", "LOGOS.BIG", "AWARDS.BIG", "SPLASH.BIG", "TITLE.BIG",
                 "COOPPLYR.BIG", "COOPTEAM.BIG")
#: The 59 single-image loading screens, ``LOAD0.BIG`` .. ``LOAD58.BIG`` [M].
LOADING_SCREEN_PREFIX = "LOAD"
#: The three UI string files [M].
LOCH_FILES = ("FEENG.LOC", "IGENG.LOC", "MC_ENG.LOC")
AUDIO_DIRECTORY = "AUDIO"
#: The two ``BNKl`` sound banks [M].
BANK_FILES = ("ZSNDFRNT.GEN", "PAUSESFX.BNK")

#: How many bytes of an entry name its format.
HEAD_BYTES = ea_big.IDENTIFY_HEAD

#: How large a file this module reads whole into memory.  Chosen to cover
#: ``GHEAD.BIG`` (107 MB) and ``MODELS.BIG`` (123 MB) [M]; archives are read
#: in place through a ranged reader and never copied, so this bounds only the
#: loose files a lane asks for whole.
FILE_SIZE_LIMIT = 160 * 1024 * 1024


class DiscError(Refusal):
    """This module could not read what it was pointed at; the sentence says why."""


class Disc:
    """The user's image, opened read-only, with every file addressed by name or path."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        try:
            self.image = iso_lib.open_image(str(self.path))
        except (iso_lib.Iso9660Error, OSError, ValueError) as exc:
            raise DiscError(str(exc).strip()
                            or f"{path} could not be opened as a PlayStation 2 disc image.") from exc
        self._handle = open(self.path, "rb")
        self._entries: Optional[Tuple[Any, ...]] = None

    def close(self) -> None:
        try:
            self._handle.close()
        except OSError:
            pass

    def __enter__(self) -> "Disc":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    # -- the directory ------------------------------------------------------

    def entries(self) -> Tuple[Any, ...]:
        if self._entries is None:
            self._entries = tuple(entry for entry in iso_lib.iter_entries(self.image)
                                  if not entry.is_dir)
        return self._entries

    def find(self, name: str) -> Any:
        """The entry for an ISO path, or for a unique file name anywhere on the image."""
        if name.startswith("/"):
            found = iso_lib.find(self.image, name)
            if found is None or found.is_dir:
                raise DiscError(f"this image holds no {name}; it is not an MVP Baseball 2005 "
                                f"PlayStation 2 disc, or the file has been removed. Choose "
                                f"the {SERIAL} image.")
            return found
        wanted = name.upper()
        matches = [entry for entry in self.entries()
                   if entry.path.rsplit("/", 1)[-1].upper() == wanted]
        if not matches:
            raise DiscError(f"this image holds no file named {name}; it is not an MVP "
                            f"Baseball 2005 PlayStation 2 disc, or the file has been "
                            f"removed. Choose the {SERIAL} image.")
        if len(matches) > 1:
            raise DiscError(f"{len(matches)} files on this image are named {name} "
                            f"({', '.join(m.path for m in matches)}); address one by its "
                            f"full path.")
        return matches[0]

    def has(self, name: str) -> bool:
        try:
            self.find(name)
        except DiscError:
            return False
        return True

    def under(self, directory: str) -> Tuple[Any, ...]:
        """Every file inside a directory of that name, anywhere on the image."""
        wanted = "/" + directory.upper() + "/"
        return tuple(entry for entry in self.entries() if wanted in entry.path.upper())

    # -- bytes --------------------------------------------------------------

    def offset_of(self, entry: Any) -> int:
        return iso_lib.extent_byte_offset(self.image, entry.lba, 0)

    def read(self, offset: int, length: int) -> bytes:
        self._handle.seek(offset)
        return self._handle.read(length)

    def head(self, entry: Any, count: int = HEAD_BYTES) -> bytes:
        return self.read(self.offset_of(entry), min(count, int(entry.length)))

    def file_bytes(self, entry: Any, *, limit: Optional[int] = FILE_SIZE_LIMIT) -> bytes:
        if limit is not None and int(entry.length) > limit:
            raise DiscError(f"{entry.path} is {int(entry.length):,} bytes; this lane reads a "
                            f"file into memory and stops at {limit:,}. It is listed with its "
                            f"size and left unread.")
        return self.read(self.offset_of(entry), int(entry.length))

    def archive(self, entry: Any) -> ea_big.BigArchive:
        """The EA ``BIG`` archive at *entry*, opened in place through the image."""
        try:
            return ea_big.parse_big(self.read, size=int(entry.length), base=self.offset_of(entry),
                                    name=entry.path)
        except ea_big.BigError as exc:
            raise DiscError(f"{entry.path}: {exc}") from exc

    def is_big(self, entry: Any) -> bool:
        return int(entry.length) >= ea_big.BIG_HEADER_SIZE and self.head(entry, 4) == ea_big.BIGF_MAGIC

    def big_files(self) -> Tuple[Any, ...]:
        """Every file that starts an EA ``BIG`` archive, whatever it is named."""
        return tuple(entry for entry in self.entries()
                     if entry.path.upper().endswith(".BIG") and self.is_big(entry))

    def stadium_archives(self) -> Tuple[Any, ...]:
        return tuple(entry for entry in self.under(STADIUM_DIRECTORY)
                     if entry.path.upper().endswith(".BIG") and self.is_big(entry))

    def loading_screens(self) -> Tuple[Any, ...]:
        out = []
        for entry in self.entries():
            name = entry.path.rsplit("/", 1)[-1].upper()
            if name.startswith(LOADING_SCREEN_PREFIX) and name.endswith(".BIG") \
                    and name[len(LOADING_SCREEN_PREFIX):-4].isdigit() and self.is_big(entry):
                out.append(entry)
        return tuple(sorted(out, key=lambda e: int(e.path.rsplit("/", 1)[-1][4:-4])))

    def audio_files(self) -> Tuple[Any, ...]:
        """The files under an ``AUDIO`` directory; on an image without one, every file.

        The retail disc keeps all of its audio under ``/DATA/AUDIO`` [M].  The
        synthetic disc has one subdirectory and it is the ballpark one, so its
        audio sits in the root; either way each file is then classified by its
        own magic, never by its name.
        """
        found = self.under(AUDIO_DIRECTORY)
        return found if found else self.entries()


def open_disc(path: Path) -> Disc:
    return Disc(Path(path))


def archives_named(disc: Disc, names: Sequence[str]) -> List[Tuple[str, Any]]:
    """``(name, entry)`` for each of *names* present on the image, in the order given."""
    out = []
    for name in names:
        try:
            out.append((name, disc.find(name)))
        except DiscError:
            continue
    return out


# --------------------------------------------------------------------------
# The synthetic disc: every shape a lane touches, computed here
# --------------------------------------------------------------------------

SYNTHETIC_PLAYER_COLUMNS = ("first_name", "last_name", "playerattrib_jerseynum",
                            "playerattrib_bats", "playerattrib_throws", "playerattrib_height",
                            "playerattrib_weight", "playerattrib_contact")
SYNTHETIC_TEAM_COLUMNS = ("unique_team", "team_city", "team_name", "team_abbrev", "team_league")


def synthetic_player_table(rows: int = 6) -> bytes:
    """An indexed table shaped like the roster tables: a row id, numbered fields, a ``;`` trailer."""
    data = []
    for number in range(rows):
        data.append(("0%08x" % (0x1000 + number),
                     ("Fixture%d" % number, "Synthetic", str(10 + number), str(number % 2),
                      str((number + 1) % 2), str(70 + number), str(180 + number), str(40 + number))))
    return ea_csv_db.build_indexed_table(SYNTHETIC_PLAYER_COLUMNS, data)


def synthetic_team_table(rows: int = 4) -> bytes:
    data = []
    for number in range(rows):
        data.append(("0%08x" % (0x2000 + number),
                     ("Ab%d" % number, "Fixture City %d" % number, "Fixtures %d" % number,
                      "FX%d" % number, str(number % 2))))
    return ea_csv_db.build_indexed_table(SYNTHETIC_TEAM_COLUMNS, data)


def synthetic_curve_table(rows: int = 5) -> bytes:
    """A plain CSV table shaped like the progression curves."""
    # One column name is empty and one row is blank, because the disc's own
    # curves have both [M] and a lane has to survive them.
    lines = [("Age", "Star Level", "", "High")]
    for number in range(rows):
        lines.append((str(18 + number), str(1 + number % 5), str(100 * (number + 1)),
                      str(150 * (number + 1))))
    lines.append(("", "", "", ""))
    return ea_csv_db.build_plain_table(lines)


#: The synthetic archives are packed with a one-deep match chain, so the
#: writer's default encoder has the same kind of margin over them that it
#: measures over EA's streams on the retail disc (10 to 8,687 bytes) [M].  A
#: synthetic disc packed by the writer's own encoder would leave a same-slot
#: rewrite no room at all, which is a property of the fixture, not the disc.
SYNTHETIC_CHAIN_LIMIT = 1


def _packed(payload: bytes) -> bytes:
    return ea_big.refpack_compress(payload, chain_limit=SYNTHETIC_CHAIN_LIMIT)


def synthetic_database_archive() -> bytes:
    """``DATABASE.BIG``'s shape: packed indexed tables, 4-byte alignment [M]."""
    return ea_big.build_big([
        ("attrib.dat", _packed(synthetic_player_table(40))),
        ("team.dat", _packed(synthetic_team_table(12))),
        ("org.dat", _packed(synthetic_team_table(6))),
    ], alignment=4)


def synthetic_progress_archive() -> bytes:
    """``PROGRESS.BIG``'s shape: stored plain CSV, 4-byte alignment [M]."""
    return ea_big.build_big([
        ("contract.csv", synthetic_curve_table()),
        ("progbinc.csv", synthetic_curve_table(3)),
    ], alignment=4)


def _shps_block(code: int, width: int, height: int, payload: bytes,
                misc: Tuple[int, int, int, int] = (0, 0, 0, 0), declared: Optional[int] = None) -> bytes:
    size = ea_shps.BLOCK_HEADER_SIZE + len(payload) if declared is None else declared
    return (bytes((code,)) + size.to_bytes(3, "little") + struct.pack("<HH", width, height)
            + struct.pack("<HHHH", *misc) + payload)


def _shps_palette(entries: Sequence[Tuple[int, int, int, int]]) -> bytes:
    payload = b"".join(bytes(entry) for entry in entries)
    return _shps_block(ea_shps.CODE_PALETTE32, len(entries), 1, payload,
                       misc=(len(entries), 0, 0x2000, 0))


def synthetic_palette(count: int = 256, seed: int = 0) -> List[Tuple[int, int, int, int]]:
    return [((index * 5 + seed) & 0xFF, (index * 3 + seed * 7) & 0xFF,
             (255 - index) & 0xFF, ea_shps.PS2_ALPHA_OPAQUE) for index in range(count)]


def synthetic_indexed_image(width: int, height: int, *, seed: int = 0,
                            palette_entries: int = 256, tag: str = "img") -> Tuple[str, bytes]:
    """One 8-bit indexed image whose indices are a ramp, with its palette and the usual terminator."""
    pixels = bytes(((x * 7 + y * 13 + seed) % palette_entries) for y in range(height)
                   for x in range(width))
    entries = synthetic_palette(palette_entries, seed)
    if palette_entries == ea_shps.CSM1_ENTRIES:
        # Store it the way the GS wants it, so the reader's un-swap is exercised.
        stored = ea_shps.deinterleave_csm1(entries)
    else:
        stored = entries
    body = (_shps_block(ea_shps.CODE_INDEXED8, width, height, pixels)
            + _shps_palette(stored) + _shps_block(0x70, 0, 0, b"", declared=0))
    return tag, body


def synthetic_direct_image(width: int, height: int, *, seed: int = 0, tag: str = "rgba") -> Tuple[str, bytes]:
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            pixels += bytes(((x * 9 + seed) & 0xFF, (y * 11) & 0xFF, ((x + y) * 5) & 0xFF,
                             ea_shps.PS2_ALPHA_OPAQUE))
    return tag, (_shps_block(ea_shps.CODE_RGBA32, width, height, bytes(pixels))
                 + _shps_block(0x70, 0, 0, b"", declared=0))


def synthetic_block_codec_image(width: int, height: int, *, tag: str = "blk") -> Tuple[str, bytes]:
    """A code-0x0E image: 6 bytes per 4x4 block, a 256-entry palette, undecoded on purpose."""
    payload = bytes((index * 37) & 0xFF for index in range(width * height * 3 // 8))
    return tag, (_shps_block(0x0E, width, height, payload, misc=(0, 0, 0x2000, 0))
                 + _shps_palette(ea_shps.deinterleave_csm1(synthetic_palette(256, 3)))
                 + _shps_block(0x70, 0, 0, b"", declared=0))


def synthetic_bank(images: Sequence[Tuple[str, bytes]]) -> bytes:
    """An ``SHPS`` bank from ``(tag, block chain)`` pairs, in the disc's little-endian shape."""
    head = ea_shps.SHPS_HEADER_SIZE + ea_shps.SHPS_ROW_SIZE * len(images)
    offsets = []
    cursor = head
    for _tag, body in images:
        offsets.append(cursor)
        cursor += len(body)
    directory = b"".join(tag.encode("ascii")[:4].ljust(4, b" ") + struct.pack("<I", offset)
                         for (tag, _body), offset in zip(images, offsets))
    return (b"SHPS" + struct.pack("<II", cursor, len(images)) + b"G359" + directory
            + b"".join(body for _tag, body in images))


def synthetic_art_archive(banks: Sequence[Tuple[str, bytes]], *, packed: bool = True,
                          alignment: int = 4) -> bytes:
    entries = [(name, _packed(bank) if packed else bank) for name, bank in banks]
    return ea_big.build_big(entries, alignment=alignment)


def synthetic_decodable_archive(seed: int = 0) -> bytes:
    """Banks of 8-bit and direct-colour images, the shape the export lanes decode."""
    return synthetic_art_archive([
        ("widget.ssh", synthetic_bank([synthetic_indexed_image(16, 16, seed=seed, tag="wid0"),
                                       synthetic_indexed_image(32, 16, seed=seed + 1,
                                                               palette_entries=17, tag="wid1")])),
        ("logo.ssh", synthetic_bank([synthetic_direct_image(8, 8, seed=seed, tag="logo")])),
        ("mixed.ssh", synthetic_bank([synthetic_block_codec_image(16, 16, tag="crwd"),
                                      synthetic_indexed_image(64, 32, seed=seed + 2, tag="ok")])),
    ])


def synthetic_block_codec_archive() -> bytes:
    """Banks that are all code 0x0E: the shape of the uniform, portrait and field-art archives."""
    return synthetic_art_archive([
        ("001.ssh", synthetic_bank([synthetic_block_codec_image(128, 128, tag="001a"),
                                    synthetic_block_codec_image(64, 64, tag="001b")])),
        ("002.ssh", synthetic_bank([synthetic_block_codec_image(32, 32, tag="002")])),
    ])


def synthetic_stadium_archive() -> bytes:
    """A ballpark archive's shape: ``.ord``/``.orl`` objects, banks, text [M]."""
    return ea_big.build_big([
        ("model.ord", b"\x7fELF" + bytes(60)),
        ("model.orl", bytes(32)),
        ("cram.ssh", _packed(synthetic_bank([
            synthetic_indexed_image(64, 64, seed=5, tag="cram"),
            synthetic_block_codec_image(64, 64, tag="crwd")]))),
        ("field0.ssh", _packed(synthetic_bank([
            synthetic_indexed_image(32, 32, seed=6, palette_entries=137, tag="fld")]))),
        ("park.csv", ea_csv_db.build_plain_table([("Name", "Value"), ("Fixture", "1")])),
    ], alignment=4)


# -- LOCH ---------------------------------------------------------------------

LOCH_MAGIC = b"LOCH"
LOCI_MAGIC = b"LOCI"
LOCL_MAGIC = b"LOCL"
LOCH_HEADER_SIZE = 20


def synthetic_loch(strings: Sequence[str]) -> bytes:
    """A ``LOCH`` file in the disc's shape: ``LOCH`` header, ``LOCI`` id table, ``LOCL`` strings [M]."""
    count = len(strings)
    loci_size = 16 + 4 * count
    loci = LOCI_MAGIC + struct.pack("<III", loci_size, count, 0)
    for index in range(count):
        loci += struct.pack("<HH", index + 1, index)
    encoded = [text.encode("utf-16-le") + b"\x00\x00" for text in strings]
    offsets = []
    cursor = 16 + 4 * count
    for blob in encoded:
        offsets.append(cursor)
        cursor += len(blob)
    locl = LOCL_MAGIC + struct.pack("<III", cursor, 0, count)
    locl += b"".join(struct.pack("<I", offset) for offset in offsets)
    locl += b"".join(encoded)
    header = LOCH_MAGIC + struct.pack("<IIII", LOCH_HEADER_SIZE, 1, 1,
                                      LOCH_HEADER_SIZE + loci_size)
    return header + loci + locl


# -- audio ----------------------------------------------------------------------

def synthetic_bare_stream_file() -> bytes:
    """A bare ``SCHl`` file holding two EA-XA streams back to back, zero-padded apart [M]."""
    first = ea_schl.synthetic_stream(samples=4480, channels=2, sample_rate=24000)
    second = ea_schl.synthetic_stream(samples=2240, channels=1, sample_rate=24000)
    return first + bytes(64) + second


def synthetic_speech_file() -> bytes:
    return ea_schl.synthetic_speech_stream(samples=4480, sample_rate=24000)


def synthetic_speech_archive() -> bytes:
    """A speech archive's shape: stored ``SCHl`` MicroTalk entries, 64-byte alignment [M]."""
    return ea_big.build_big([
        ("0003.dat", synthetic_speech_file()),
        ("0004.dat", synthetic_speech_file()),
    ], alignment=64)


def build_synthetic_disc() -> bytes:
    """A tiny ``SLUS-21135``-shaped image carrying every container shape the lanes read.

    The ISO builder nests one subdirectory, so the archives sit in the root and
    the one ballpark archive under ``STADIUM``; every lane addresses a file by
    its unique name, which is how it finds ``/DATA/DATABASE/DATABASE.BIG`` on
    the retail disc and ``/DATABASE.BIG`` here.  Every byte is computed.
    """
    boot = b"BOOT2 = cdrom0:\\%s;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n" % BOOT_FILE.encode("ascii")
    files = [
        (b"SYSTEM.CNF;1", boot),
        (BOOT_FILE.encode("ascii") + b";1", b"\x7fELF" + bytes(4092)),
        (b"DATABASE.BIG;1", synthetic_database_archive()),
        (b"PROGRESS.BIG;1", synthetic_progress_archive()),
        (b"UNIFORMS.BIG;1", synthetic_block_codec_archive()),
        (b"PORTRAIT.BIG;1", synthetic_block_codec_archive()),
        (b"FIELDS.BIG;1", synthetic_block_codec_archive()),
        (b"IGONLY.BIG;1", synthetic_decodable_archive(1)),
        (b"FEONLY.BIG;1", synthetic_decodable_archive(2)),
        (b"LOGOS.BIG;1", synthetic_decodable_archive(3)),
        (b"STADIUMS.BIG;1", synthetic_block_codec_archive()),
        (b"LOAD0.BIG;1", synthetic_art_archive([("load0.ssh", synthetic_bank([
            synthetic_block_codec_image(32, 32, tag="load")]))])),
        (b"MC_ENG.LOC;1", synthetic_loch(("FIXTURE ONE", "FIXTURE TWO", "A LONGER FIXTURE STRING"))),
        (b"CHANTDAT.BIG;1", synthetic_bare_stream_file()),
        (b"PADAT.BIG;1", synthetic_speech_file()),
        (b"PNAMEDAT.BIG;1", synthetic_speech_archive()),
        (b"PAUSESFX.BNK;1", ea_schl.synthetic_bank()),
    ]
    sub_files = [(b"A001DAY.BIG;1", synthetic_stadium_archive())]
    return iso_lib.build_synthetic_iso(files=files, sub_name=STADIUM_DIRECTORY.encode("ascii"),
                                       sub_files=sub_files)


__all__ = [
    "AUDIO_DIRECTORY", "BANK_FILES", "BOOT_FILE", "DATABASE_ARCHIVE", "DATA_DIRECTORY", "Disc",
    "DiscError", "FACE_ARCHIVES", "FIELD_ART_ARCHIVES", "FILE_SIZE_LIMIT", "HEAD_BYTES",
    "IDENTITY_TABLES", "LOADING_SCREEN_PREFIX", "LOCH_FILES", "LOCH_HEADER_SIZE", "LOCH_MAGIC",
    "LOCI_MAGIC", "LOCL_MAGIC", "MENU_ARCHIVES", "PRESENTATION_ARCHIVES",
    "PRESENTATION_SCRIPT_ARCHIVES", "RETAIL_BOOT_ELF_SHA256", "RETAIL_EDITION", "RETAIL_ELF_CRC",
    "RETAIL_IMAGE_SHA256", "SERIAL", "STADIUM_DIRECTORY", "SYNTHETIC_CHAIN_LIMIT", "STADIUM_MENU_ARCHIVES",
    "TUNING_ARCHIVES", "UNIFORM_ARCHIVES", "archives_named", "build_synthetic_disc", "open_disc",
    "synthetic_art_archive", "synthetic_bank", "synthetic_bare_stream_file",
    "synthetic_block_codec_archive", "synthetic_block_codec_image", "synthetic_curve_table",
    "synthetic_database_archive", "synthetic_decodable_archive", "synthetic_direct_image",
    "synthetic_indexed_image", "synthetic_loch", "synthetic_palette", "synthetic_player_table",
    "synthetic_progress_archive", "synthetic_speech_archive", "synthetic_speech_file",
    "synthetic_stadium_archive", "synthetic_team_table",
]
