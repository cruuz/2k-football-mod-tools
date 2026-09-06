"""Reading NFL Street 3 (PS2) ``/DATA`` containers out of the user's own disc.

Every lane in this module starts here.  The disc's ``/DATA/*.DAT`` files are EA
``TERF`` containers -- the same family NFL Street, Madden NFL 09 and NCAA
Football 09 ship, and the same shared readers open them -- so this file is only
the *game-specific* half: which disc this is, which containers each page is
about, how large a container this module will hold in memory, and how to build
a synthetic disc the conformance harness can prove a lane on without game data.

The twelve generic operations are
:class:`mod_editor.games._lanes.terf_discs.TerfDiscs` and are bound onto this
module below, so ``containers.open_disc`` is still the name a lane uses and the
``Discs`` protocol is still satisfied by this module.

**NFL Street 3 is not a re-skin of NFL Street.**  The container *formats* are
identical and every shared reader opens both with nothing changed, but no
record schema survives except one: measured on the two discs [M], ``PLAY`` goes
from 65 fields / 671 bits to **84 fields / 831 bits** with 64 names in common,
49 of those at the same width and **none at the same bit offset**; ``TEAM``
goes from 41 fields / 575 bits to **22 / 447**; and ``DCHT`` -- 4 fields, 63
bits, same names, same widths, same offsets -- is the only table that ports
byte for byte.  ``docs/product/NFLSTREET3_PS2_MODULE.md`` §2 is the census.

What the disc holds, measured [M]: **80 ``TERF`` containers, 27,178 members**,
all of which the shared reader opens; **47 EA TDB databases plus one bare
database** (``/DATA/STREAMED.DB``, 26 tables, 361 fields) whose **1,038 of
1,038** checksum slots already hold the value they recompute to; **17,986
``MMAP`` textures**; **813 ``TEXT`` string banks**; **920 ``SCHl`` streams** and
**197 ``BNKl`` banks** holding 691 sounds; **143 nested ``TERF`` members**; and
**11 ``QL01`` preload caches** naming 49 containers with **2,295 copies, 2,294
of them byte-identical to what they copy and one unresolved** -- ``FE.QKL``
names ``PLAROSTERHAIR.DAT``, which is not a file on this disc, so that copy
cannot be checked against anything [M].

**Evidence tags.**  **[M]** measured on the disc this box holds; **[S]**
sourced; **[A]** assumed.

**Retail-free.**  Names, offsets, lengths, counts and digests only.  No member
payload and no decoded pixel reaches the repository, and nothing here writes to
the user's image.

Standard library only; importable without Qt.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_terf
from mod_editor.games._lanes import terf_discs
from mod_editor.games.contract import Refusal

# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

#: The disc serial this module reads [M].
SERIAL = "SLUS-21482"

#: What a refusal calls this game.
GAME_TITLE = "NFL Street 3 (PlayStation 2)"

#: The boot file ``SYSTEM.CNF`` names, in ISO9660 spelling [M].
BOOT_FILE = "SLUS_214.82"

#: SHA-256 of the boot ELF on the USA disc [M]: 4,623,328 bytes.
RETAIL_BOOT_ELF_SHA256 = "88fd27455a031f053cccb81b0e97ca32e2ea69fe0a941d4f5d21771d739aedfa"

#: SHA-256 of the whole USA image [M]: 4,695,883,776 bytes, 158 files / 6 dirs.
RETAIL_IMAGE_SHA256 = "d80064ae58cb4da7a1f4cdc04b2bedcfb4fee6d91c0562bc1dc7a6670295124c"

#: PCSX2's CRC for that executable [M].  Recorded, never used as a key.
RETAIL_ELF_CRC = "E31B62CC"

#: What this module calls the one image it recognises.
RETAIL_EDITION = "retail"

#: Where the containers live.
DATA_DIRECTORY = "/DATA"

#: How large a container this module will hold in memory.  Chosen to cover
#: ``PLATEX.DAT`` at 87,709,696 bytes -- the kit art the Uniforms page is
#: about, and 3.5x the size of NFL Street's [M] -- and to stop short of the two
#: the lanes never need whole: ``CHATDATA.DAT`` 550,961,152 and
#: ``MOVIEDAT.DAT`` 282,628,160 [M].  Those two are listed with their size,
#: unread; the audio lane reaches ``CHATDATA.DAT`` through a memory map
#: instead, which costs no copy at all.  "Listed but not read" is a state the
#: catalogue names rather than a silent gap.
CONTAINER_SIZE_LIMIT = 96 * 1024 * 1024

# --------------------------------------------------------------------------
# The containers each page is about [M]
# --------------------------------------------------------------------------

#: The league database container: 32 EA TDB databases, one per team, each
#: carrying ``PLAY`` (84 fields), ``TEAM`` (22) and ``DCHT`` (4) [M].
TEAM_DATABASE_CONTAINER = "DB_TEAMS.DAT"

#: The fresh-profile template container: 4 databases [M].
TEMPLATE_CONTAINER = "TEMPLATE.DAT"

#: The in-game data container: 11 databases carrying the playbook tables, plus
#: 8 ``MMAP`` members and one ``TEXT`` bank [M].  NFL Street ships 2 databases
#: here; Street 3 ships 11.
GAME_DATA_CONTAINER = "IGDATA.DAT"

#: The one bare database on the disc, with no container around it [M]: 26
#: tables, 361 fields, 54 checksum slots, all of which already verify.
STREAM_DATABASE_FILE = "STREAMED.DB"

#: Player kit, skin and tattoo art [M]: 16,259 ``MMAP`` members, 16,231 of them
#: ``LZH1``-packed, in an 87,709,696-byte container -- **9.4x the member count
#: of NFL Street's** 1,735.
UNIFORM_CONTAINERS = ("PLATEX.DAT",)

#: Player portrait art [M]: 693 stored ``MMAP`` members.
PORTRAIT_CONTAINERS = ("UIS_PORT.DAT",)

#: Team logo and banner art [M]: 173 and 173 stored ``MMAP`` members.
LOGO_CONTAINERS = ("UIS_TMLO.DAT", "UIS_BNRT.DAT")

#: Create-a-team, field-select and field-marking art [M]: 56 / 24 / 51 / 9
#: stored ``MMAP`` members.
FIELD_ART_CONTAINERS = ("UIS_CRTM.DAT", "UIS_FSEL.DAT", "UIS_FOOT.DAT",
                        "UIS_CMAP.DAT")

#: The playfield environments and their props [M]: ``ENVRNMT.DAT`` 117 members
#: (71 ``SMF``, 18 ``DMF``, 9 ``TEXT``, 8 ``MMAP``), ``OBJMODEL.DAT`` 171 (72
#: ``DMF``, 45 ``SMF``, 28 ``SKL1``, 26 ``MMAP``) and ``STATMOD.DAT`` 181 (79
#: ``MMAP``).
STADIUM_CONTAINERS = ("ENVRNMT.DAT", "OBJMODEL.DAT", "STATMOD.DAT")

#: Presentation art [M]: load screens (``LOADDATA.DAT``, 68 ``LZH1`` ``MMAP``,
#: where NFL Street has 12), in-game overlay (``UIS_INGM.DAT``, 30), post-game
#: (``UIS_POST.DAT``, 90), the movie frames (``UIS_MOVI.DAT``, 22) and the
#: online-results screens (``UIS_ONRE.DAT``, 103).
PRESENTATION_CONTAINERS = ("LOADDATA.DAT", "UIS_INGM.DAT", "UIS_POST.DAT",
                           "UIS_MOVI.DAT", "UIS_ONRE.DAT")

#: Menu and front-end art [M].
MENU_ART_CONTAINERS = ("UIS_FRON.DAT", "UIS_BUTT.DAT", "UIS_COMN.DAT",
                       "UIS_CHAL.DAT", "UIS_CTRL.DAT", "UIS_MPIC.DAT",
                       "MINIGAMP.DAT", "CHNL_IMG.DAT")

#: The containers holding ``TEXT`` string banks [M]: 617 / 159 / 17 / 9 / 3 / 3.
TEXT_CONTAINERS = ("OBJDEFS.DAT", "PLADYNCL.DAT", "MAINFLOW.DAT", "ENVRNMT.DAT",
                   "GAMEOPTI.DAT", "MINIGAME.DAT")

#: Where the ``SCHl`` streams are, and what each container is for [M]:
#: 893 / 15 / 10 / 2 streams.
STREAM_CONTAINERS = (
    ("CHATDATA.DAT", "trash talk and commentary"),
    ("MUSIC.DAT", "soundtrack"),
    ("AMBSTRM.DAT", "ambience"),
    ("UISOUND.DAT", "interface sound"),
)

#: Where the ``BNKl`` banks are [M]: 194 and 3 banks, 691 sounds in all.
BANK_CONTAINERS = (
    ("FIELDSFX.DAT", "field sound effects"),
    ("UISOUND.DAT", "interface sound"),
)

#: The eleven preload caches.  NFL Street 3 ships one front-end cache and ten
#: numbered gameplay caches, where NFL Street ships eight [M].
PRELOAD_CACHES = ("FE.QKL", "GAME0.QKL", "GAME1.QKL", "GAME2.QKL", "GAME3.QKL",
                  "GAME4.QKL", "GAME5.QKL", "GAME6.QKL", "GAME7.QKL",
                  "GAME8.QKL", "GAME9.QKL")

#: The one cache copy on this disc that resolves to nothing: ``FE.QKL`` names
#: ``PLAROSTERHAIR.DAT`` and no file of that name is on the disc, so its copies
#: cannot be checked against anything [M].  Recorded here because a coherence
#: check that silently ignored it would be claiming more than it measured.
UNRESOLVED_CACHE_NAME = "PLAROSTERHAIR.DAT"

# --------------------------------------------------------------------------
# The generic half, closed over this disc's constants
# --------------------------------------------------------------------------


class DiscError(Refusal):
    """This module could not read what it was pointed at; the sentence says why."""


_DISCS = terf_discs.TerfDiscs(
    serial=SERIAL,
    title=GAME_TITLE,
    error=DiscError,
    container_size_limit=CONTAINER_SIZE_LIMIT,
    preload_caches=PRELOAD_CACHES,
    data_directory=DATA_DIRECTORY,
)

#: Re-exported so a lane in this package names one module, not two.
DataFile = terf_discs.DataFile
ContainerReport = terf_discs.ContainerReport
WritableContainer = terf_discs.WritableContainer
PreloadCopy = terf_discs.PreloadCopy
ContainerPreload = terf_discs.ContainerPreload
PROBE_BYTES = terf_discs.PROBE_BYTES
KIND_TERF = terf_discs.KIND_TERF
KIND_TDB = terf_discs.KIND_TDB
KIND_OTHER = terf_discs.KIND_OTHER
KIND_UNREAD = terf_discs.KIND_UNREAD
PRELOAD_KIND_HEADER = terf_discs.PRELOAD_KIND_HEADER
PRELOAD_KIND_MEMBER = terf_discs.PRELOAD_KIND_MEMBER
SYNTHETIC_TEXT_LINES = terf_discs.SYNTHETIC_TEXT_LINES
synthetic_text_member = terf_discs.synthetic_text_member
build_synthetic_preload_cache = terf_discs.build_synthetic_preload_cache

#: The ``Discs`` protocol, satisfied by this module.
open_disc = _DISCS.open_disc
data_files = _DISCS.data_files
read_file = _DISCS.read_file
classify = _DISCS.classify
describe_container = _DISCS.describe_container
load_container = _DISCS.load_container
member_uncached = _DISCS.member_uncached
members_of_format = _DISCS.members_of_format
open_for_rewrite = _DISCS.open_for_rewrite
parse_preload_cache = _DISCS.parse_preload_cache
preload_names = _DISCS.preload_names
preload_copies = _DISCS.preload_copies

# --------------------------------------------------------------------------
# What CI proves a lane on: a synthetic disc built from the formats' own rules
# --------------------------------------------------------------------------


def synthetic_tdb(*, tables: int = 2) -> bytes:
    """A small EA TDB, built by the shared writer, with its four CRCs correct."""

    from mod_editor.games._formats import ea_tdb

    described = [
        ("TEAM", [("TGID", ea_tdb.FIELD_UINT, 10), ("TDNA", ea_tdb.FIELD_STRING, 136),
                  ("TSNA", ea_tdb.FIELD_STRING, 56)],
         [{"TGID": 1, "TDNA": "SYNTHETIC", "TSNA": "SYN"},
          {"TGID": 2, "TDNA": "FIXTURE", "TSNA": "FIX"}]),
        ("PLAY", [("PGID", ea_tdb.FIELD_UINT, 15), ("PPOS", ea_tdb.FIELD_UINT, 5),
                  ("POVR", ea_tdb.FIELD_UINT, 7), ("PJEN", ea_tdb.FIELD_UINT, 7)],
         [{"PGID": 100, "PPOS": 0, "POVR": 70, "PJEN": 7},
          {"PGID": 101, "PPOS": 1, "POVR": 65, "PJEN": 22}]),
    ][:max(1, tables)]
    return ea_tdb.recompute_crcs(ea_tdb.build_tdb(described))


def synthetic_team_database() -> bytes:
    """One team database in this disc's shape: ``PLAY``, ``TEAM`` and ``DCHT``.

    The field names and widths are the ones ``DB_TEAMS.DAT`` declares [M] --
    including the eight-bit ``PATO``/``PLTO``/``PRAT``/``PRLT``/``PSRT`` this
    disc widened from NFL Street's six, and the ``PF*`` face-customisation
    block Street 3 added -- so the record lanes' budgets and their bit packing
    are exercised on a fixture rather than on a game.
    """

    from mod_editor.games._formats import ea_tdb

    return ea_tdb.recompute_crcs(ea_tdb.build_tdb((
        ("TEAM",
         (("TDNA", ea_tdb.FIELD_STRING, 136),
          ("TLNA", ea_tdb.FIELD_STRING, 120),
          ("TSNA", ea_tdb.FIELD_STRING, 56),
          ("TGID", ea_tdb.FIELD_UINT, 10),
          ("TLGL", ea_tdb.FIELD_UINT, 8),
          ("TMC1", ea_tdb.FIELD_UINT, 7),
          ("TMC2", ea_tdb.FIELD_UINT, 7),
          ("TMC3", ea_tdb.FIELD_UINT, 7),
          ("CTDL", ea_tdb.FIELD_UINT, 1),
          ("TTYP", ea_tdb.FIELD_UINT, 5)),
         ({"TDNA": "SYNTHETIC ONE", "TLNA": "Synthetic A", "TSNA": "SYN",
           "TGID": 1, "TLGL": 3, "TMC1": 11, "TMC2": 22, "TMC3": 33,
           "CTDL": 0, "TTYP": 1},)),
        ("PLAY",
         (("PFNA", ea_tdb.FIELD_STRING, 96),
          ("PLNA", ea_tdb.FIELD_STRING, 112),
          ("PNKN", ea_tdb.FIELD_STRING, 128),
          ("PMED", ea_tdb.FIELD_STRING, 8),
          ("PWGT", ea_tdb.FIELD_UINT, 8),
          ("PATO", ea_tdb.FIELD_UINT, 8),
          ("PLTO", ea_tdb.FIELD_UINT, 8),
          ("PRAT", ea_tdb.FIELD_UINT, 8),
          ("PRLT", ea_tdb.FIELD_UINT, 8),
          ("PSRT", ea_tdb.FIELD_UINT, 8),
          ("PGID", ea_tdb.FIELD_UINT, 15),
          ("TGID", ea_tdb.FIELD_UINT, 10),
          ("TGTI", ea_tdb.FIELD_UINT, 10),
          ("PJEN", ea_tdb.FIELD_UINT, 7),
          ("PPOS", ea_tdb.FIELD_UINT, 5),
          ("POVR", ea_tdb.FIELD_UINT, 7),
          ("PSPD", ea_tdb.FIELD_UINT, 7),
          ("PAGI", ea_tdb.FIELD_UINT, 7),
          ("PCTH", ea_tdb.FIELD_UINT, 7),
          ("PTAK", ea_tdb.FIELD_UINT, 7),
          ("PBLK", ea_tdb.FIELD_UINT, 7),
          ("PBTK", ea_tdb.FIELD_UINT, 7),
          ("PCOV", ea_tdb.FIELD_UINT, 7),
          ("PCEL", ea_tdb.FIELD_UINT, 7),
          ("PJUM", ea_tdb.FIELD_UINT, 7),
          ("PHGT", ea_tdb.FIELD_UINT, 7),
          ("PAGE", ea_tdb.FIELD_UINT, 6),
          ("PSKI", ea_tdb.FIELD_UINT, 4),
          ("PFEA", ea_tdb.FIELD_UINT, 3),
          ("PFEY", ea_tdb.FIELD_UINT, 5),
          ("PFHC", ea_tdb.FIELD_UINT, 7)),
         tuple({"PFNA": f"SYN{n}", "PLNA": f"FIXTURE{n}", "PNKN": f"NICK{n}",
                "PMED": "", "PWGT": 200 + n, "PATO": 30 + n, "PLTO": 31 + n,
                "PRAT": 32 + n, "PRLT": 33 + n, "PSRT": 34 + n,
                "PGID": 100 + n, "TGID": 1, "TGTI": 1, "PJEN": (n * 7) % 100,
                "PPOS": n % 10, "POVR": 50 + n, "PSPD": 60 + n, "PAGI": 61 + n,
                "PCTH": 63 + n, "PTAK": 64 + n, "PBLK": 65 + n, "PBTK": 66 + n,
                "PCOV": 67 + n, "PCEL": 68 + n, "PJUM": 69 + n, "PHGT": 70 + n,
                "PAGE": 22 + n, "PSKI": n % 16, "PFEA": n % 8, "PFEY": n % 32,
                "PFHC": n % 128} for n in range(8))),
        ("DCHT",
         (("PGID", ea_tdb.FIELD_UINT, 15),
          ("TGID", ea_tdb.FIELD_UINT, 10),
          ("PPOS", ea_tdb.FIELD_UINT, 5),
          ("ddep", ea_tdb.FIELD_UINT, 5)),
         tuple({"PGID": 100 + n, "TGID": 1, "PPOS": n % 10, "ddep": n % 3}
               for n in range(6))),
    )))


def synthetic_playbook_database() -> bytes:
    """A playbook database in ``IGDATA.DAT``'s shape [M]: the six play tables.

    Street 3's ``PBST`` is 5 fields and 127 bits against NFL Street's 27 and
    511: the eleven ``ax``/``ay`` route-grid pairs are gone, and ``PBFM`` gained
    ``FAU1``..``FAU4`` instead.  The fixture carries what this disc declares.
    """

    from mod_editor.games._formats import ea_tdb

    return ea_tdb.recompute_crcs(ea_tdb.build_tdb((
        ("PBST",
         (("PBST", ea_tdb.FIELD_UINT, 8),
          ("name", ea_tdb.FIELD_STRING, 80),
          ("SETL", ea_tdb.FIELD_UINT, 6),
          ("PBFM", ea_tdb.FIELD_UINT, 6),
          ("ord_", ea_tdb.FIELD_UINT, 4)),
         tuple({"PBST": n, "name": f"SYN SET {n}", "SETL": n % 2,
                "PBFM": n % 3, "ord_": n} for n in range(4))),
        ("PBPL",
         (("PBST", ea_tdb.FIELD_UINT, 8),
          ("name", ea_tdb.FIELD_STRING, 192),
          ("PBPL", ea_tdb.FIELD_UINT, 10),
          ("PLYL", ea_tdb.FIELD_UINT, 9),
          ("ord_", ea_tdb.FIELD_UINT, 7)),
         tuple({"PBST": n % 4, "name": f"SYNTHETIC PLAY CALL {n}", "PBPL": n,
                "PLYL": n, "ord_": n} for n in range(6))),
        ("PLYL",
         (("name", ea_tdb.FIELD_STRING, 200),
          ("SETL", ea_tdb.FIELD_UINT, 6),
          ("PLYL", ea_tdb.FIELD_UINT, 9),
          ("SITT", ea_tdb.FIELD_UINT, 2),
          ("PLYT", ea_tdb.FIELD_UINT, 6),
          ("PLF_", ea_tdb.FIELD_UINT, 18),
          ("risk", ea_tdb.FIELD_UINT, 1),
          ("motn", ea_tdb.FIELD_UINT, 1),
          ("phlp", ea_tdb.FIELD_UINT, 3),
          ("vpos", ea_tdb.FIELD_UINT, 3)),
         tuple({"name": f"SYNTHETIC PLAY {n}", "SETL": n % 2, "PLYL": n,
                "SITT": n % 4, "PLYT": n % 8, "PLF_": 0x1000 + n,
                "risk": n % 2, "motn": n % 2, "phlp": n % 8, "vpos": n % 8}
               for n in range(6))),
        ("SETL",
         (("name", ea_tdb.FIELD_STRING, 144),
          ("SETL", ea_tdb.FIELD_UINT, 6),
          ("FORM", ea_tdb.FIELD_UINT, 3),
          ("MOTN", ea_tdb.FIELD_UINT, 1),
          ("SETT", ea_tdb.FIELD_UINT, 4),
          ("SITT", ea_tdb.FIELD_UINT, 2),
          ("SLF_", ea_tdb.FIELD_UINT, 1),
          ("poso", ea_tdb.FIELD_UINT, 1)),
         tuple({"name": f"SYNTHETIC SETUP {n}", "SETL": n, "FORM": n % 8,
                "MOTN": n % 2, "SETT": n % 16, "SITT": n % 4, "SLF_": n % 2,
                "poso": n % 2} for n in range(3))),
        ("FORM",
         (("name", ea_tdb.FIELD_STRING, 80),
          ("FORM", ea_tdb.FIELD_UINT, 4),
          ("FTYP", ea_tdb.FIELD_UINT, 4)),
         tuple({"name": f"SYN FORM {n}", "FORM": n, "FTYP": n % 2}
               for n in range(2))),
        ("PBFM",
         (("name", ea_tdb.FIELD_STRING, 136),
          ("FAU1", ea_tdb.FIELD_UINT, 6),
          ("FAU2", ea_tdb.FIELD_UINT, 6),
          ("FAU3", ea_tdb.FIELD_UINT, 6),
          ("FAU4", ea_tdb.FIELD_UINT, 6),
          ("PBFM", ea_tdb.FIELD_UINT, 6),
          ("FTYP", ea_tdb.FIELD_UINT, 4),
          ("ord_", ea_tdb.FIELD_UINT, 1),
          ("grid", ea_tdb.FIELD_UINT, 1)),
         tuple({"name": f"SYNTHETIC BOOK {n}", "FAU1": n, "FAU2": n + 1,
                "FAU3": n + 2, "FAU4": n + 3, "PBFM": n, "FTYP": n % 2,
                "ord_": n % 2, "grid": n % 2} for n in range(3))),
    )))


def synthetic_texture_member(width: int = 16, height: int = 16, *, seed: int = 0,
                             mips: int = 1, images: int = 1,
                             retail_layout: bool = True) -> bytes:
    """One decodable ``MMAP`` member, built by the shared fixture builder."""

    from mod_editor.games._lanes import synthetic_art

    return synthetic_art.synthetic_mmap(width, height, seed=seed, mips=mips,
                                        images=images, retail_layout=retail_layout)


#: ``(name, chunk, codec)`` per art container, matching what the disc ships for
#: each [M].  ``PLATEX.DAT`` and ``LOADDATA.DAT`` are ``COMP``/``LZH1``;
#: ``STATMOD.DAT`` is ``COMP`` with almost every member stored; the rest are
#: stored ``DATA``.
ART_SHAPES: Tuple[Tuple[str, str, int], ...] = (
    (UNIFORM_CONTAINERS[0], "COMP", ea_terf.CODEC_LZH1),
    (PORTRAIT_CONTAINERS[0], "DATA", ea_terf.CODEC_STORED),
    (LOGO_CONTAINERS[0], "DATA", ea_terf.CODEC_STORED),
    (LOGO_CONTAINERS[1], "DATA", ea_terf.CODEC_STORED),
    (FIELD_ART_CONTAINERS[0], "DATA", ea_terf.CODEC_STORED),
    (FIELD_ART_CONTAINERS[1], "DATA", ea_terf.CODEC_STORED),
    (FIELD_ART_CONTAINERS[2], "DATA", ea_terf.CODEC_STORED),
    (FIELD_ART_CONTAINERS[3], "DATA", ea_terf.CODEC_STORED),
    (STADIUM_CONTAINERS[0], "DATA", ea_terf.CODEC_STORED),
    (STADIUM_CONTAINERS[1], "DATA", ea_terf.CODEC_STORED),
    (STADIUM_CONTAINERS[2], "COMP", ea_terf.CODEC_STORED),
    (PRESENTATION_CONTAINERS[0], "COMP", ea_terf.CODEC_LZH1),
    (PRESENTATION_CONTAINERS[1], "DATA", ea_terf.CODEC_STORED),
    (PRESENTATION_CONTAINERS[2], "DATA", ea_terf.CODEC_STORED),
    (PRESENTATION_CONTAINERS[3], "DATA", ea_terf.CODEC_STORED),
    (PRESENTATION_CONTAINERS[4], "DATA", ea_terf.CODEC_STORED),
) + tuple((name, "DATA", ea_terf.CODEC_STORED) for name in MENU_ART_CONTAINERS)


def build_synthetic_disc(*, tdb_members: Optional[Sequence[bytes]] = None,
                         stream_database: Optional[bytes] = None,
                         preload_caches: bool = True,
                         audio_members: Optional[Sequence[bytes]] = None,
                         art_members: Optional[Sequence[bytes]] = None,
                         playbook_members: Optional[Sequence[bytes]] = None) -> bytes:
    """A tiny ``SLUS-21482``-shaped image carrying this module's containers.

    Built exactly as NFL Street's is, with this disc's own container names,
    chunk chains and codecs [M], plus the bare ``STREAMED.DB`` this disc ships
    and NFL Street does not.  The eleven ``QL01`` caches are built **last**,
    from the containers' own bytes, and carry both kinds of copy the retail
    caches carry.

    Every byte comes from ``ea_terf.build_terf`` and the builders above; no
    game data is involved, which is what lets the conformance harness run a
    lane on a machine that owns no disc.
    """

    from mod_editor.games._formats import ea_schl

    teams = list(tdb_members) if tdb_members is not None else [
        synthetic_team_database(), synthetic_team_database(), synthetic_tdb(tables=2)]
    team_db = ea_terf.build_terf(teams, chunk="DATA")
    playbooks = ea_terf.build_terf(
        (list(playbook_members) if playbook_members is not None
         else [synthetic_playbook_database()]) + [synthetic_text_member()],
        chunk="COMP",
        codecs=[ea_terf.CODEC_STORED, ea_terf.CODEC_STORED])
    templates = ea_terf.build_terf([synthetic_tdb(tables=2), b""], chunk="DATA")
    if art_members is None:
        art_members = [synthetic_texture_member(16, 16, seed=1),
                       synthetic_texture_member(8, 8, seed=2),
                       synthetic_texture_member(16, 8, seed=3)]
    art_members = list(art_members)
    if audio_members is None:
        audio_members = [ea_schl.synthetic_stream(), ea_schl.synthetic_bank()]
    audio = ea_terf.build_terf(list(audio_members), chunk="DATA")
    texts = ea_terf.build_terf([synthetic_text_member()], chunk="DATA")

    art: List[Tuple[str, bytes]] = []
    for name, chunk, codec in ART_SHAPES:
        art.append((name, ea_terf.build_terf(
            art_members, chunk=chunk,
            codecs=([codec] * len(art_members)) if chunk == "COMP" else None)))
    art_by_name = dict(art)

    sub_files: List[Tuple[bytes, bytes]] = [
        (TEAM_DATABASE_CONTAINER.encode("ascii") + b";1", team_db),
        (GAME_DATA_CONTAINER.encode("ascii") + b";1", playbooks),
        (TEMPLATE_CONTAINER.encode("ascii") + b";1", templates),
        (STREAM_CONTAINERS[0][0].encode("ascii") + b";1", audio),
        (BANK_CONTAINERS[0][0].encode("ascii") + b";1", audio),
        (TEXT_CONTAINERS[0].encode("ascii") + b";1", texts),
        (TEXT_CONTAINERS[1].encode("ascii") + b";1", texts),
    ]
    sub_files += [(name.encode("ascii") + b";1", blob) for name, blob in art]
    if stream_database is None:
        stream_database = synthetic_tdb(tables=2)
    sub_files.append((STREAM_DATABASE_FILE.encode("ascii") + b";1", stream_database))
    if preload_caches:
        kits = art_by_name[UNIFORM_CONTAINERS[0]]
        logos = art_by_name[LOGO_CONTAINERS[0]]
        caches = (
            (PRELOAD_CACHES[0], [
                (TEAM_DATABASE_CONTAINER, PRELOAD_KIND_HEADER, None,
                 terf_discs.container_directory(team_db)),
                (TEAM_DATABASE_CONTAINER, PRELOAD_KIND_MEMBER, 0,
                 ea_terf.parse_terf(team_db).stored(0)),
                (LOGO_CONTAINERS[0], PRELOAD_KIND_HEADER, None,
                 terf_discs.container_directory(logos)),
            ]),
            (PRELOAD_CACHES[1], [
                (UNIFORM_CONTAINERS[0], PRELOAD_KIND_HEADER, None,
                 terf_discs.container_directory(kits)),
                (UNIFORM_CONTAINERS[0], PRELOAD_KIND_MEMBER, 1,
                 ea_terf.parse_terf(kits).stored(1)),
                (GAME_DATA_CONTAINER, PRELOAD_KIND_HEADER, None,
                 terf_discs.container_directory(playbooks)),
            ]),
        )
        sub_files += [(name.encode("ascii") + b";1",
                       build_synthetic_preload_cache(rows)) for name, rows in caches]
    return terf_discs.build_synthetic_iso(boot_file=BOOT_FILE, sub_files=sub_files)


__all__ = [
    "ART_SHAPES", "BANK_CONTAINERS", "BOOT_FILE", "CONTAINER_SIZE_LIMIT",
    "ContainerPreload", "ContainerReport", "DATA_DIRECTORY", "DataFile",
    "DiscError", "FIELD_ART_CONTAINERS", "GAME_DATA_CONTAINER", "GAME_TITLE",
    "KIND_OTHER", "KIND_TDB", "KIND_TERF", "KIND_UNREAD", "LOGO_CONTAINERS",
    "MENU_ART_CONTAINERS", "PORTRAIT_CONTAINERS", "PRELOAD_CACHES",
    "PRELOAD_KIND_HEADER", "PRELOAD_KIND_MEMBER", "PRESENTATION_CONTAINERS",
    "PROBE_BYTES", "PreloadCopy", "RETAIL_BOOT_ELF_SHA256", "RETAIL_EDITION",
    "RETAIL_ELF_CRC", "RETAIL_IMAGE_SHA256", "SERIAL", "STADIUM_CONTAINERS",
    "STREAM_CONTAINERS", "STREAM_DATABASE_FILE", "SYNTHETIC_TEXT_LINES",
    "TEAM_DATABASE_CONTAINER", "TEMPLATE_CONTAINER", "TEXT_CONTAINERS",
    "UNIFORM_CONTAINERS", "UNRESOLVED_CACHE_NAME", "WritableContainer",
    "build_synthetic_disc", "build_synthetic_preload_cache", "classify",
    "data_files", "describe_container", "load_container", "member_uncached",
    "members_of_format", "open_disc", "open_for_rewrite", "parse_preload_cache",
    "preload_copies", "preload_names", "read_file", "synthetic_playbook_database",
    "synthetic_tdb", "synthetic_team_database", "synthetic_text_member",
    "synthetic_texture_member",
]
