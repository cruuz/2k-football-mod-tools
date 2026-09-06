"""Reading NFL Street (PS2) ``/DATA`` containers out of the user's own disc.

Every lane in this module starts here.  The disc's ``/DATA/*.DAT`` files are EA
``TERF`` containers -- the same family Madden NFL 09 and NCAA Football 09 ship,
and the same shared readers open them -- so this file is only the
*game-specific* half: which disc this is, which containers each page is about,
how large a container this module will hold in memory, and how to build a
synthetic disc the conformance harness can prove a lane on without game data.

The twelve generic operations (open, list, read to declared length, classify,
describe, load, take a member uncached, bound a container to its allocation,
read the preload caches) are :class:`mod_editor.games._lanes.terf_discs.TerfDiscs`
and are bound onto this module below, so ``containers.open_disc`` is still the
name a lane uses and the ``Discs`` protocol is still satisfied by this module.

A game never imports another game, so nothing here reaches into the Madden 09
or NCAA 09 packages; what the discs share they share through ``_formats`` and
``_lanes``.

What the disc holds, measured [M]: **48 ``TERF`` containers, 8,803 members**,
all of which the shared reader opens; **38 EA TDB databases** (32 in
``DB_TEAMS.DAT``, 4 in ``TEMPLATE.DAT``, 2 in ``IGDATA.DAT``) whose **570 of
570** checksum slots already hold the value they recompute to; **2,785 ``MMAP``
textures**; **531 ``TEXT`` string banks**; **679 ``SCHl`` streams** and **236
``BNKl`` banks** holding 1,031 sounds; and **9 ``QL01`` preload caches** naming
37 containers with **1,693 copies, every one byte-identical to what it copies**.

**Evidence tags.**  **[M]** measured on the disc this box holds; **[S]**
sourced; **[A]** assumed.

**Retail-free.**  Names, offsets, lengths, counts and digests only.  No member
payload and no decoded pixel reaches the repository, and nothing here writes to
the user's image.

Standard library only; importable without Qt.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_terf
from mod_editor.games._lanes import terf_discs
from mod_editor.games.contract import Refusal

# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

#: The disc serial this module reads [M].
SERIAL = "SLUS-20841"

#: What a refusal calls this game.
GAME_TITLE = "NFL Street (PlayStation 2)"

#: The boot file ``SYSTEM.CNF`` names, in ISO9660 spelling [M].
BOOT_FILE = "SLUS_208.41"

#: SHA-256 of the boot ELF on the USA disc [M]: 3,257,248 bytes.
RETAIL_BOOT_ELF_SHA256 = "1b5ceccd4e6bb7005320a93a24ee7614b7f5c03540ca9fc0a435b09c1da7728b"

#: SHA-256 of the whole USA image [M]: 2,077,655,040 bytes, 131 files / 6 dirs.
RETAIL_IMAGE_SHA256 = "cb197dbdd468f05c3099147aa802e8f4f315d1bb3a21e62b4a17fd34e6205613"

#: PCSX2's CRC for that executable [M].  Recorded, never used as a key.
RETAIL_ELF_CRC = "03C2C5B1"

#: What this module calls the one image it recognises.
RETAIL_EDITION = "retail"

#: Where the containers live.
DATA_DIRECTORY = "/DATA"

#: How large a container this module will hold in memory.  Chosen to cover
#: ``PLAFACE.DAT`` at 40,273,920 bytes -- the largest container any lane here
#: opens -- and to stop short of the five the lanes never need whole:
#: ``MOVIEDAT.DAT`` 1,043,585,600, ``CHATDATA.DAT`` 279,664,640,
#: ``PATHFIND.DAT`` 206,604,288, ``AMBSTRM.DAT`` 164,659,200 and
#: ``FEMUSIC.DAT`` 140,980,224 [M].  Those five are listed with their size,
#: unread; the audio lane reaches the four it needs through a memory map
#: instead, which costs no copy at all.  "Listed but not read" is a state the
#: catalogue names rather than a silent gap.
CONTAINER_SIZE_LIMIT = 48 * 1024 * 1024

# --------------------------------------------------------------------------
# The containers each page is about [M]
# --------------------------------------------------------------------------

#: The league database container: 32 EA TDB databases, one per team, each
#: carrying ``PLAY`` (65 fields), ``TEAM`` (41) and ``DCHT`` (4) [M].  This is
#: the roster and the team identity, and it is the container both record lanes
#: write.
TEAM_DATABASE_CONTAINER = "DB_TEAMS.DAT"

#: The fresh-profile template container: 4 databases at members 1..4, carrying
#: the ``PLAY``/``TEAM`` shapes a new save starts from [M].
TEMPLATE_CONTAINER = "TEMPLATE.DAT"

#: The in-game data container: 2 databases carrying the playbook tables
#: (``PBST``, ``PBPL``, ``PBFM``, ``PLYL``, ``SETL``, ``FORM``), plus 8
#: ``MMAP`` members and one ``TEXT`` bank [M].
GAME_DATA_CONTAINER = "IGDATA.DAT"

#: Player kit, skin and tattoo art [M]: 1,735 ``MMAP`` members, 1,731 of them
#: ``LZH1``-packed, in a 25,126,912-byte container.  NFL Street has no uniform
#: table -- a player's kit here *is* these textures.
UNIFORM_CONTAINERS = ("PLATEX.DAT",)

#: Player portrait art [M]: 549 stored ``MMAP`` members.
PORTRAIT_CONTAINERS = ("UIS_PORT.DAT",)

#: Team logo art [M]: 102 stored ``MMAP`` members.
LOGO_CONTAINERS = ("UIS_TMLO.DAT",)

#: Create-a-team and field-select art [M]: 56 and 41 stored ``MMAP`` members.
FIELD_ART_CONTAINERS = ("UIS_CRTM.DAT", "UIS_FSEL.DAT")

#: The playfield environments and their props [M]: ``ENVRNMT.DAT`` 112 members
#: (48 ``SMF``, 18 ``DMF``, 15 ``MMAP``, 8 ``TEXT``), ``OBJMODEL.DAT`` 92 (70
#: ``DMF``, 17 ``SKL1``, 3 ``SMF``, 2 ``MMAP``) and ``STATMOD.DAT`` 105 (19
#: ``MMAP``).  NFL Street's "stadiums" are street playfields.
STADIUM_CONTAINERS = ("ENVRNMT.DAT", "OBJMODEL.DAT", "STATMOD.DAT")

#: Presentation art [M]: load screens (``LOADDATA.DAT``, 12 ``LZH1`` ``MMAP``),
#: in-game overlay (``UIS_INGM.DAT``, 18), the movie frames
#: (``UIS_MOVI.DAT``, 22) and the online-results screens
#: (``UIS_ONRE.DAT``, 103).
PRESENTATION_CONTAINERS = ("LOADDATA.DAT", "UIS_INGM.DAT", "UIS_MOVI.DAT",
                           "UIS_ONRE.DAT")

#: Menu and front-end art [M]: 11 / 13 / 16 / 25 / 3 / 19 / 11 / 4 / 1 stored
#: ``MMAP`` members.
MENU_ART_CONTAINERS = ("UIS_FRON.DAT", "UIS_BUTT.DAT", "UIS_COMN.DAT",
                       "UIS_BGPL.DAT", "UIS_BGMP.DAT", "UIS_CHAL.DAT",
                       "UIS_GABR.DAT", "UIS_CTRL.DAT", "UIS_CWIN.DAT")

#: The containers holding ``TEXT`` string banks [M]: 393 / 129 / 8 / 1.
TEXT_CONTAINERS = ("OBJDEFS.DAT", "PLADYNCL.DAT", "ENVRNMT.DAT", "IGDATA.DAT")

#: Where the ``SCHl`` streams are, and what each container is for [M]:
#: 637 / 14 / 11 / 9 / 8 streams.
STREAM_CONTAINERS = (
    ("CHATDATA.DAT", "trash talk and commentary"),
    ("FEMUSIC.DAT", "front-end music"),
    ("UISOUND.DAT", "interface sound"),
    ("PATHFIND.DAT", "gameplay callouts"),
    ("AMBSTRM.DAT", "ambience"),
)

#: Where the ``BNKl`` banks are [M]: 233 and 3 banks, 1,031 sounds in all.
BANK_CONTAINERS = (
    ("FIELDSFX.DAT", "field sound effects"),
    ("UISOUND.DAT", "interface sound"),
)

#: The nine preload caches.  NFL Street ships one front-end cache and eight
#: numbered gameplay caches, where NCAA 09 ships three and Madden 09 two [M].
PRELOAD_CACHES = ("FE.QKL", "GAME0.QKL", "GAME1.QKL", "GAME2.QKL", "GAME3.QKL",
                  "GAME4.QKL", "GAME5.QKL", "GAME6.QKL", "GAME7.QKL")

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

#: The ``Discs`` protocol, satisfied by this module.  A bound method is a
#: module attribute exactly as a function is, and a lane base reaching
#: ``discs.open_disc`` gets this one.
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
        ("TEAM", [("TGID", ea_tdb.FIELD_UINT, 10), ("TDNA", ea_tdb.FIELD_STRING, 176),
                  ("TSNA", ea_tdb.FIELD_STRING, 56)],
         [{"TGID": 1, "TDNA": "SYNTHETIC", "TSNA": "SYN"},
          {"TGID": 2, "TDNA": "FIXTURE", "TSNA": "FIX"}]),
        ("PLAY", [("PGID", ea_tdb.FIELD_UINT, 15), ("PPOS", ea_tdb.FIELD_UINT, 5),
                  ("POVR", ea_tdb.FIELD_UINT, 7), ("PJEN", ea_tdb.FIELD_UINT, 7)],
         [{"PGID": 100, "PPOS": 0, "POVR": 70, "PJEN": 7},
          {"PGID": 101, "PPOS": 1, "POVR": 65, "PJEN": 22}]),
    ][:max(1, tables)]
    # ``build_tdb`` leaves the four checksum slots zero; a fixture whose CRCs
    # are wrong would let a CRC check pass by never being exercised.
    return ea_tdb.recompute_crcs(ea_tdb.build_tdb(described))


def synthetic_team_database() -> bytes:
    """One team database in this disc's shape: ``PLAY``, ``TEAM`` and ``DCHT``.

    The field names and widths are the ones ``DB_TEAMS.DAT`` declares [M], so
    the record lanes' budgets and their bit packing are exercised on a fixture
    rather than on a game.  Names are invented, numbers are a counting ramp,
    and the four checksums are written from the result's own bytes.
    """

    from mod_editor.games._formats import ea_tdb

    return ea_tdb.recompute_crcs(ea_tdb.build_tdb((
        ("TEAM",
         (("TDNA", ea_tdb.FIELD_STRING, 136),
          ("TLNA", ea_tdb.FIELD_STRING, 120),
          ("TSNA", ea_tdb.FIELD_STRING, 56),
          ("TGID", ea_tdb.FIELD_UINT, 10),
          ("TLGL", ea_tdb.FIELD_UINT, 7),
          ("TMC1", ea_tdb.FIELD_UINT, 7),
          ("TMC2", ea_tdb.FIELD_UINT, 7),
          ("TMC3", ea_tdb.FIELD_UINT, 7),
          ("TTYP", ea_tdb.FIELD_UINT, 5)),
         ({"TDNA": "SYNTHETIC ONE", "TLNA": "Synthetic A", "TSNA": "SYN",
           "TGID": 1, "TLGL": 3, "TMC1": 11, "TMC2": 22, "TMC3": 33, "TTYP": 1},)),
        ("PLAY",
         (("PFNA", ea_tdb.FIELD_STRING, 88),
          ("PLNA", ea_tdb.FIELD_STRING, 104),
          ("PNKN", ea_tdb.FIELD_STRING, 104),
          ("PWGT", ea_tdb.FIELD_UINT, 8),
          ("PGID", ea_tdb.FIELD_UINT, 15),
          ("TGID", ea_tdb.FIELD_UINT, 10),
          ("PJEN", ea_tdb.FIELD_UINT, 7),
          ("PPOS", ea_tdb.FIELD_UINT, 5),
          ("POVR", ea_tdb.FIELD_UINT, 7),
          ("PSPD", ea_tdb.FIELD_UINT, 7),
          ("PAGI", ea_tdb.FIELD_UINT, 7),
          ("PAWR", ea_tdb.FIELD_UINT, 7),
          ("PCTH", ea_tdb.FIELD_UINT, 7),
          ("PTAK", ea_tdb.FIELD_UINT, 7),
          ("PBLK", ea_tdb.FIELD_UINT, 7),
          ("PBTK", ea_tdb.FIELD_UINT, 7),
          ("PCOV", ea_tdb.FIELD_UINT, 7),
          ("PCEL", ea_tdb.FIELD_UINT, 7),
          ("PHGT", ea_tdb.FIELD_UINT, 7),
          ("PAGE", ea_tdb.FIELD_UINT, 6),
          ("PSKI", ea_tdb.FIELD_UINT, 3)),
         tuple({"PFNA": f"SYN{n}", "PLNA": f"FIXTURE{n}", "PNKN": f"NICK{n}",
                "PWGT": 200 + n, "PGID": 100 + n, "TGID": 1, "PJEN": (n * 7) % 100,
                "PPOS": n % 10, "POVR": 50 + n, "PSPD": 60 + n, "PAGI": 61 + n,
                "PAWR": 62 + n, "PCTH": 63 + n, "PTAK": 64 + n, "PBLK": 65 + n,
                "PBTK": 66 + n, "PCOV": 67 + n, "PCEL": 68 + n, "PHGT": 70 + n,
                "PAGE": 22 + n, "PSKI": n % 8} for n in range(8))),
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

    The field names and widths are the ones the disc declares, including
    ``PBST``'s eleven ``ax``/``ay`` route-grid pairs -- twenty-two fields whose
    Street 3 counterpart does not exist at all, which is the single largest
    schema difference between the two discs.
    """

    from mod_editor.games._formats import ea_tdb

    pbst_fields = [("PBST", ea_tdb.FIELD_UINT, 8),
                   ("PBFM", ea_tdb.FIELD_UINT, 8),
                   ("SETL", ea_tdb.FIELD_UINT, 8),
                   ("ord_", ea_tdb.FIELD_UINT, 8),
                   ("name", ea_tdb.FIELD_STRING, 192)]
    pbst_fields += [(f"ax{n}_" if n < 10 else "ax10", ea_tdb.FIELD_UINT, 16)
                    for n in range(11)]
    pbst_fields += [(f"ay{n}_" if n < 10 else "ay10", ea_tdb.FIELD_UINT, 8)
                    for n in range(11)]

    def pbst_row(n: int) -> dict:
        row = {"PBST": n, "PBFM": n % 3, "SETL": n % 2, "ord_": n,
               "name": f"SYNTHETIC SET {n}"}
        for slot in range(11):
            row["ax%s" % ("%d_" % slot if slot < 10 else "10")] = 100 * slot + n
            row["ay%s" % ("%d_" % slot if slot < 10 else "10")] = (10 * slot + n) & 0xFF
        return row

    return ea_tdb.recompute_crcs(ea_tdb.build_tdb((
        ("PBST", tuple(pbst_fields), tuple(pbst_row(n) for n in range(4))),
        ("PBPL",
         (("PBPL", ea_tdb.FIELD_UINT, 16),
          ("PLYL", ea_tdb.FIELD_UINT, 8),
          ("PBST", ea_tdb.FIELD_UINT, 8),
          ("ord_", ea_tdb.FIELD_UINT, 8)),
         tuple({"PBPL": n, "PLYL": n, "PBST": n % 4, "ord_": n} for n in range(6))),
        ("PLYL",
         (("PLF_", ea_tdb.FIELD_UINT, 32),
          ("SETL", ea_tdb.FIELD_UINT, 8),
          ("PLYL", ea_tdb.FIELD_UINT, 8),
          ("SITT", ea_tdb.FIELD_UINT, 8),
          ("PLYT", ea_tdb.FIELD_UINT, 8),
          ("name", ea_tdb.FIELD_STRING, 192),
          ("risk", ea_tdb.FIELD_UINT, 8),
          ("motn", ea_tdb.FIELD_UINT, 8),
          ("phlp", ea_tdb.FIELD_UINT, 8),
          ("vpos", ea_tdb.FIELD_UINT, 8)),
         tuple({"PLF_": 0x1000 + n, "SETL": n % 2, "PLYL": n, "SITT": n % 3,
                "PLYT": n % 4, "name": f"SYNTHETIC PLAY {n}", "risk": n,
                "motn": n, "phlp": n, "vpos": n} for n in range(6))),
        ("SETL",
         (("SLF_", ea_tdb.FIELD_UINT, 32),
          ("MOTN", ea_tdb.FIELD_UINT, 16),
          ("SETL", ea_tdb.FIELD_UINT, 8),
          ("FORM", ea_tdb.FIELD_UINT, 8),
          ("SETT", ea_tdb.FIELD_UINT, 8),
          ("SITT", ea_tdb.FIELD_UINT, 8),
          ("name", ea_tdb.FIELD_STRING, 192),
          ("poso", ea_tdb.FIELD_UINT, 8)),
         tuple({"SLF_": 0x2000 + n, "MOTN": n, "SETL": n, "FORM": n % 2,
                "SETT": n, "SITT": n % 3, "name": f"SYNTHETIC SETUP {n}",
                "poso": n} for n in range(3))),
        ("FORM",
         (("FORM", ea_tdb.FIELD_UINT, 8),
          ("FTYP", ea_tdb.FIELD_UINT, 8),
          ("name", ea_tdb.FIELD_STRING, 192)),
         tuple({"FORM": n, "FTYP": n % 2, "name": f"SYNTHETIC FORMATION {n}"}
               for n in range(2))),
        ("PBFM",
         (("grid", ea_tdb.FIELD_UINT, 32),
          ("PBFM", ea_tdb.FIELD_UINT, 8),
          ("FTYP", ea_tdb.FIELD_UINT, 8),
          ("ord_", ea_tdb.FIELD_UINT, 8),
          ("name", ea_tdb.FIELD_STRING, 400)),
         tuple({"grid": 0x3000 + n, "PBFM": n, "FTYP": n % 2, "ord_": n,
                "name": f"SYNTHETIC BOOK {n}"} for n in range(3))),
    )))


def synthetic_texture_member(width: int = 16, height: int = 16, *, seed: int = 0,
                             mips: int = 1, images: int = 1,
                             retail_layout: bool = True) -> bytes:
    """One decodable ``MMAP`` member, built by the shared fixture builder."""

    from mod_editor.games._lanes import synthetic_art

    return synthetic_art.synthetic_mmap(width, height, seed=seed, mips=mips,
                                        images=images, retail_layout=retail_layout)


#: ``(name, chunk, codec)`` per art container, matching what the disc ships for
#: each [M]: ``PLATEX.DAT`` and ``LOADDATA.DAT`` are ``COMP``/``LZH1``, the
#: nine ``UIS_*`` ones and the three environment ones are stored.
ART_SHAPES: Tuple[Tuple[str, str, int], ...] = (
    (UNIFORM_CONTAINERS[0], "COMP", ea_terf.CODEC_LZH1),
    (PORTRAIT_CONTAINERS[0], "DATA", ea_terf.CODEC_STORED),
    (LOGO_CONTAINERS[0], "DATA", ea_terf.CODEC_STORED),
    (FIELD_ART_CONTAINERS[0], "DATA", ea_terf.CODEC_STORED),
    (FIELD_ART_CONTAINERS[1], "DATA", ea_terf.CODEC_STORED),
    (STADIUM_CONTAINERS[0], "DATA", ea_terf.CODEC_STORED),
    (STADIUM_CONTAINERS[1], "DATA", ea_terf.CODEC_STORED),
    (STADIUM_CONTAINERS[2], "DATA", ea_terf.CODEC_STORED),
    (PRESENTATION_CONTAINERS[0], "COMP", ea_terf.CODEC_LZH1),
    (PRESENTATION_CONTAINERS[1], "DATA", ea_terf.CODEC_STORED),
    (PRESENTATION_CONTAINERS[2], "DATA", ea_terf.CODEC_STORED),
    (PRESENTATION_CONTAINERS[3], "DATA", ea_terf.CODEC_STORED),
) + tuple((name, "DATA", ea_terf.CODEC_STORED) for name in MENU_ART_CONTAINERS)


def build_synthetic_disc(*, tdb_members: Optional[Sequence[bytes]] = None,
                         preload_caches: bool = True,
                         audio_members: Optional[Sequence[bytes]] = None,
                         art_members: Optional[Sequence[bytes]] = None,
                         playbook_members: Optional[Sequence[bytes]] = None) -> bytes:
    """A tiny ``SLUS-20841``-shaped image carrying this module's containers.

    ``DB_TEAMS.DAT`` is built as a stored ``DATA`` container, which is what the
    disc ships [M] -- so the record writer is proved against a member whose
    stored size is its decompressed size, the case where a re-pack cannot move
    the directory.  ``PLATEX.DAT`` and ``LOADDATA.DAT`` are ``COMP``/``LZH1``,
    which is where a re-pack *can* move it.

    The nine ``QL01`` caches are built **last**, from the containers' own
    bytes, and carry the two kinds of copy the retail caches carry [M]: a
    container's directory, and a member exactly as stored.  So the coherence
    rule -- rewrite every stale copy or refuse -- is exercised on a fixture,
    and ``preload_caches=False`` builds the same disc without them for a lane
    that wants to prove the uncached path.

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
    "STREAM_CONTAINERS", "SYNTHETIC_TEXT_LINES", "TEAM_DATABASE_CONTAINER",
    "TEMPLATE_CONTAINER", "TEXT_CONTAINERS", "UNIFORM_CONTAINERS",
    "WritableContainer", "build_synthetic_disc", "build_synthetic_preload_cache",
    "classify", "data_files", "describe_container", "load_container",
    "member_uncached", "members_of_format", "open_disc", "open_for_rewrite",
    "parse_preload_cache", "preload_copies", "preload_names", "read_file",
    "synthetic_playbook_database", "synthetic_tdb", "synthetic_team_database",
    "synthetic_text_member", "synthetic_texture_member",
]
