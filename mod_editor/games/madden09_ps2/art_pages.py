"""The other four texture pages: stadiums, field art, presentation and faces.

``UNIFORMS.DAT`` was never the only ``MMAP`` container on this disc.  The same
decoder, the same encoder and the same disc writer reach the stadium art, the
field art, every menu texture and the player and coach faces -- and this file
is what points them there.  Nothing here re-implements the lane: each row is
:class:`~.uniform_art.UniformDiscArtWriteLane` with a different
:attr:`~.uniform_art.UniformArtLane.art_containers`, a different page and its
own schemas, so a fix to the writer is a fix to all five rows at once.

Four rows, on four pages:

===========================================  =============  =========================
row                                          page           containers
===========================================  =============  =========================
``madden09ps2.stadiums.textures``            stadiums       2
``madden09ps2.field_art.textures``           field_art      1
``madden09ps2.presentation.ui_textures``     presentation   50
``madden09ps2.rosters.face_textures``        rosters        4
===========================================  =============  =========================

**One lane per row, not two.**  The uniform page carries two rows because its
exporter shipped first and earns a lower rung than the writer that followed
it.  These four ship with both halves at once, and one lane already *is* both:
the shell draws preview, Export PNG and a checked Import PNG out of
``decode_png`` and ``encode``, and Build writes the edited texture into a NEW
disc image.  A second row per page would name the same code twice and give a
user two places to do one thing.

**What is not a texture is listed, not hidden.**  Every one of these
containers carries members this lane cannot open: ``SMF`` static geometry
(stadium shells, field meshes), ``DMF`` animated models, ``FNTS`` font sets,
nested ``TERF`` containers, empty slots, and members whose first 32 bytes match
no format id this reader knows.  **No decoder for ``SMF`` or ``DMF`` is built
anywhere in this repository and no layout for either is documented here**, so
the catalogue counts them by format per container and leaves them alone.  The
same goes for two kinds of ``MMAP`` entry the decoder will not draw: the ones
that declare no palette or a pixel layout it does not implement -- 15 in
``STADIUMS.DAT``, 23 in ``STADATA.DAT``, 12 in ``PLYRFACE.DAT``, 140 in
``LOADDATA.DAT`` and 22 across the other UI containers -- and the **palette
banks**, members carrying alternate CLUTs and no surface at all, of which
``STADIUMS.DAT`` has five (828 to 832, 45 CLUTs each) [M].  All of them parse,
all of them are counted, and ``undecodable_reason`` refuses each by name rather
than drawing it wrong.

**Classification: ``offline-writer-proved``, and never more.**  Every step is
proved against the user's own bytes offline.  **No rebuilt Madden 09 container
has been booted**, so no row here says the game loads the result; the receipt,
the plan and the page all say so.

Run one without a window::

    python3 -m mod_editor.games.madden09_ps2.art_pages --page stadiums \\
        --source DISC.iso [--out catalogue.json] [--export DIR --limit 8]

**Evidence tags.**  **[M]** measured on the retail SLUS-21770 disc;
**[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

from mod_editor.games.contract import Catalogue, Edit, Refusal, Target, require

from mod_editor.games._formats import ea_terf

from . import containers
from .uniform_art import (
    DERIVED_PREFIX,
    UniformDiscArtWriteLane,
    _sha256,
    load_identities,
    read_rgba_png,
    write_rgba_png,
)

#: A second PCSX2 identity table, in the same schema and read alongside the
#: first.  ``tools/madden09_ps2_texture_identities.py``'s shipped document was
#: built over the six containers the uniform lane reads; extending its index to
#: the 34 further containers these four pages cover and pairing the same 33
#: dumped frames against them found **7 more textures, every one of them in
#: ``STADATA.DAT``** [M] -- and nothing new anywhere else, because the corpus is
#: 32 coin-toss screens and one pre-game frame and those are the only surfaces
#: they drew.  They are shipped beside the first document rather than folded
#: into it: the first is that tool's own output over its own container list,
#: and re-cutting it would move counts other rows quote.
ART_PAGE_IDENTITY_DOCUMENT = Path(
    "docs/product/measured/madden09_ps2/art-page-texture-identities.json")

#: A container this file points a lane at: ``(file name, group, structure)``.
#: The third column is what the container itself says, measured on the retail
#: disc by ``member_format`` over every member and ``mmap_art.parse`` over
#: every texture -- counts and sizes, never a pixel.
ContainerSpec = Tuple[str, str, str]

# --------------------------------------------------------------------------
# Stadiums
# --------------------------------------------------------------------------

#: The stadium art.  ``STADIUMS.DAT`` is the largest art container on the disc
#: at 68 MB and is two thirds geometry; ``STADATA.DAT`` is its small companion.
#: Neither names a stadium: which member belongs to which venue is **not
#: established here** [A], and the member index is the structure they offer.
STADIUM_CONTAINERS: Tuple[ContainerSpec, ...] = (
    ("STADIUMS.DAT", "STADIUMS",
     "1355 members (434 MMAP, 651 SMF, 270 empty); 490 decodable image(s); "
     "128x128 x410, 256x64 x49, 128x64 x21, 1728x73 x3; COMP container, "
     "alignment 64 [M]."),
    ("STADATA.DAT", "STADATA",
     "268 members (80 MMAP, 154 SMF, 2 DMF, 32 unclassified); 91 decodable "
     "image(s); 32x32 x23, 64x64 x19, 256x256 x16, 8x8 x8; COMP container, "
     "alignment 64 [M]."),
)

# --------------------------------------------------------------------------
# Field art
# --------------------------------------------------------------------------

#: The field art.  Nine members in ten are ``SMF`` geometry; the 73 textures
#: include four 1024x256 sheets, which is the shape a field's painted surface
#: takes.  Which member is which field is **not established here** [A].
FIELD_ART_CONTAINERS: Tuple[ContainerSpec, ...] = (
    ("FIELDART.DAT", "FIELDART",
     "715 members (73 MMAP, 642 SMF); 73 decodable image(s); 128x128 x69, "
     "1024x256 x4; COMP container, alignment 64 [M]."),
)

# --------------------------------------------------------------------------
# Presentation and the menus
# --------------------------------------------------------------------------

#: Every ``UIS_*.DAT`` on the retail disc, plus ``LOADDATA.DAT`` and
#: ``ICONS.DAT``.  48 ``UIS_*`` files are present; **33 of them carry ``MMAP``
#: members** and the other 15 carry fonts, nested containers or members whose
#: head matches no format id [M].  ``ICONS.DAT`` is listed and carries **no
#: ``MMAP`` member at all** -- 21 unclassified members -- which is a measured
#: answer rather than an empty page.
#:
#: ``UIS_PLYR.DAT`` is last on purpose: its 3,286 portraits would otherwise
#: fill the target list ahead of every other menu texture.  It is also on the
#: Names, Numbers & Faces page, which is where a player portrait belongs.
UI_CONTAINERS: Tuple[ContainerSpec, ...] = (
    ("UIS_ADAI.DAT", "UIS_ADAI",
     "21 members (21 MMAP); 21 decodable image(s); 128x128 x21; DATA "
     "container, alignment 64 [M]."),
    ("UIS_ALL.DAT", "UIS_ALL",
     "34 members (34 TERF); 0 decodable image(s); DATA container, alignment 4 "
     "[M]."),
    ("UIS_BANR.DAT", "UIS_BANR",
     "30 members (30 unclassified); 0 decodable image(s); COMP container, "
     "alignment 4 [M]."),
    ("UIS_BGIM.DAT", "UIS_BGIM",
     "101 members (101 MMAP); 101 decodable image(s); 512x256 x68, 1024x512 "
     "x32, 8x8 x1; DATA container, alignment 64 [M]."),
    ("UIS_BGLO.DAT", "UIS_BGLO",
     "7 members (7 MMAP); 7 decodable image(s); 64x64 x7; DATA container, "
     "alignment 64 [M]."),
    ("UIS_CCST.DAT", "UIS_CCST",
     "4 members (4 unclassified); 0 decodable image(s); DATA container, "
     "alignment 64 [M]."),
    ("UIS_COAC.DAT", "UIS_COAC",
     "239 members (239 MMAP); 239 decodable image(s); 96x96 x232, 96x98 x4, "
     "96x97 x2, 8x8 x1; DATA container, alignment 64 [M]."),
    ("UIS_COMN.DAT", "UIS_COMN",
     "98 members (98 MMAP); 98 decodable image(s); 32x32 x60, 64x64 x8, 8x8 "
     "x8, 128x128 x5; DATA container, alignment 64 [M]."),
    ("UIS_CSTY.DAT", "UIS_CSTY",
     "3 members (3 unclassified); 0 decodable image(s); DATA container, "
     "alignment 64 [M]."),
    ("UIS_CTLO.DAT", "UIS_CTLO",
     "239 members (239 MMAP); 239 decodable image(s); 256x128 x120, 128x128 "
     "x119; DATA container, alignment 64 [M]."),
    ("UIS_FE.DAT", "UIS_FE",
     "147 members (147 MMAP); 147 decodable image(s); 64x64 x34, 128x128 x30, "
     "128x64 x13, 32x32 x10; DATA container, alignment 64 [M]."),
    ("UIS_FONT.DAT", "UIS_FONT",
     "10 members (10 FNTS); 0 decodable image(s); DATA container, alignment 64 "
     "[M]."),
    ("UIS_FSTY.DAT", "UIS_FSTY",
     "1 members (1 unclassified); 0 decodable image(s); DATA container, "
     "alignment 64 [M]."),
    ("UIS_IG.DAT", "UIS_IG",
     "67 members (67 MMAP); 66 decodable image(s); 64x64 x11, 32x32 x10, "
     "128x128 x9, 128x64 x7; DATA container, alignment 64 [M]."),
    ("UIS_IGBN.DAT", "UIS_IGBN",
     "6 members (6 unclassified); 0 decodable image(s); COMP container, "
     "alignment 4 [M]."),
    ("UIS_IGMC.DAT", "UIS_IGMC",
     "3 members (3 MMAP); 3 decodable image(s); 128x128 x3; DATA container, "
     "alignment 64 [M]."),
    ("UIS_IGTU.DAT", "UIS_IGTU",
     "5 members (5 MMAP); 5 decodable image(s); 128x128 x5; DATA container, "
     "alignment 64 [M]."),
    ("UIS_LFLL.DAT", "UIS_LFLL",
     "10 members (10 MMAP); 10 decodable image(s); 128x128 x6, 256x256 x4; "
     "DATA container, alignment 64 [M]."),
    ("UIS_LOAD.DAT", "UIS_LOAD",
     "104 members (104 MMAP); 104 decodable image(s); 512x256 x95, 256x128 x9; "
     "DATA container, alignment 64 [M]."),
    ("UIS_MCFL.DAT", "UIS_MCFL",
     "1188 members (1188 MMAP); 0 decodable image(s); DATA container, "
     "alignment 64 [M]."),
    ("UIS_MCIC.DAT", "UIS_MCIC",
     "14 members (14 MMAP); 14 decodable image(s); 128x128 x13, 8x8 x1; DATA "
     "container, alignment 64 [M]."),
    ("UIS_MDRC.DAT", "UIS_MDRC",
     "11 members (11 unclassified); 0 decodable image(s); COMP container, "
     "alignment 4 [M]."),
    ("UIS_MEMC.DAT", "UIS_MEMC",
     "6 members (6 unclassified); 0 decodable image(s); COMP container, "
     "alignment 4 [M]."),
    ("UIS_NWPR.DAT", "UIS_NWPR",
     "158 members (122 MMAP, 36 empty); 122 decodable image(s); 512x64 x91, "
     "128x128 x31; DATA container, alignment 64 [M]."),
    ("UIS_OMG.DAT", "UIS_OMG",
     "77 members (77 MMAP); 77 decodable image(s); 64x64 x77; DATA container, "
     "alignment 64 [M]."),
    ("UIS_PAUC.DAT", "UIS_PAUC",
     "24 members (24 unclassified); 0 decodable image(s); COMP container, "
     "alignment 4 [M]."),
    ("UIS_PAUS.DAT", "UIS_PAUS",
     "28 members (28 unclassified); 0 decodable image(s); COMP container, "
     "alignment 4 [M]."),
    ("UIS_PDAI.DAT", "UIS_PDAI",
     "63 members (63 MMAP); 63 decodable image(s); 32x32 x58, 16x256 x2, "
     "24x24 x1, 256x32 x1; DATA container, alignment 64 [M]."),
    ("UIS_PDBI.DAT", "UIS_PDBI",
     "390 members (390 MMAP); 369 decodable image(s); 64x64 x135, 512x256 x85, "
     "32x32 x67, 256x256 x64; DATA container, alignment 64 [M]."),
    ("UIS_PERS.DAT", "UIS_PERS",
     "52 members (52 MMAP); 52 decodable image(s); 512x256 x16, 256x256 x9, "
     "64x64 x6, 128x128 x4; DATA container, alignment 64 [M]."),
    ("UIS_PMIL.DAT", "UIS_PMIL",
     "1 members (1 MMAP); 1 decodable image(s); 128x64 x1; DATA container, "
     "alignment 2048 [M]."),
    ("UIS_POPS.DAT", "UIS_POPS",
     "60 members (60 unclassified); 0 decodable image(s); COMP container, "
     "alignment 4 [M]."),
    ("UIS_PRGM.DAT", "UIS_PRGM",
     "2 members (2 MMAP); 2 decodable image(s); 256x128 x1, 512x512 x1; DATA "
     "container, alignment 64 [M]."),
    ("UIS_PROL.DAT", "UIS_PROL",
     "78 members (78 MMAP); 78 decodable image(s); 32x32 x39, 64x64 x39; DATA "
     "container, alignment 64 [M]."),
    ("UIS_PRPS.DAT", "UIS_PRPS",
     "16 members (16 unclassified); 0 decodable image(s); COMP container, "
     "alignment 4 [M]."),
    ("UIS_SBLD.DAT", "UIS_SBLD",
     "86 members (86 MMAP); 86 decodable image(s); 512x32 x21, 512x128 x15, "
     "512x256 x15, 256x128 x14; DATA container, alignment 64 [M]."),
    ("UIS_SETT.DAT", "UIS_SETT",
     "4 members (4 unclassified); 0 decodable image(s); COMP container, "
     "alignment 4 [M]."),
    ("UIS_SFPC.DAT", "UIS_SFPC",
     "3 members (3 unclassified); 0 decodable image(s); COMP container, "
     "alignment 4 [M]."),
    ("UIS_SLIV.DAT", "UIS_SLIV",
     "285 members (285 MMAP); 285 decodable image(s); 64x32 x283, 60x25 x1, "
     "8x8 x1; DATA container, alignment 64 [M]."),
    ("UIS_SMOD.DAT", "UIS_SMOD",
     "34 members (33 MMAP, 1 DMF); 33 decodable image(s); 128x128 x33; DATA "
     "container, alignment 2048 [M]."),
    ("UIS_SOLO.DAT", "UIS_SOLO",
     "161 members (161 MMAP); 161 decodable image(s); 256x256 x128, 128x256 "
     "x32, 8x8 x1; DATA container, alignment 64 [M]."),
    ("UIS_STAD.DAT", "UIS_STAD",
     "49 members (49 MMAP); 49 decodable image(s); 256x128 x47, 2x2 x1, 8x8 "
     "x1; DATA container, alignment 64 [M]."),
    ("UIS_TIRL.DAT", "UIS_TIRL",
     "84 members (52 MMAP, 32 empty); 52 decodable image(s); 128x64 x51, 8x8 "
     "x1; DATA container, alignment 64 [M]."),
    ("UIS_TIRN.DAT", "UIS_TIRN",
     "84 members (52 MMAP, 32 empty); 52 decodable image(s); 256x64 x51, 8x8 "
     "x1; DATA container, alignment 64 [M]."),
    ("UIS_TMFN.DAT", "UIS_TMFN",
     "60 members (60 MMAP); 60 decodable image(s); 128x64 x59, 8x8 x1; DATA "
     "container, alignment 64 [M]."),
    ("UIS_TMLL.DAT", "UIS_TMLL",
     "285 members (285 MMAP); 285 decodable image(s); 128x128 x284, 8x8 x1; "
     "DATA container, alignment 64 [M]."),
    ("UIS_TMLO.DAT", "UIS_TMLO",
     "285 members (285 MMAP); 285 decodable image(s); 64x64 x284, 8x8 x1; DATA "
     "container, alignment 64 [M]."),
    ("LOADDATA.DAT", "LOADDATA",
     "17 members (16 MMAP, 1 TEXT); 30 decodable image(s); 640x480 x14, "
     "128x32 x13, 32x32 x2, 96x32 x1; COMP container, alignment 64 [M]."),
    ("ICONS.DAT", "ICONS",
     "21 members (21 unclassified); 0 decodable image(s); DATA container, "
     "alignment 64 [M]."),
    ("UIS_PLYR.DAT", "UIS_PLYR",
     "3286 members (3286 MMAP); 3286 decodable image(s); 96x96 x3284, 16x16 "
     "x1, 8x8 x1; DATA container, alignment 64 [M]."),
)

# --------------------------------------------------------------------------
# Faces and tattoos
# --------------------------------------------------------------------------

#: The face art.  The first three are also on the Uniforms & Equipment page --
#: one texture, two pages, because a coach's face is face art *and* part of the
#: kit sheet a uniform editor wants beside it -- and ``UIS_PLYR.DAT`` is the
#: 96x96 portrait the menus draw for the same player.
FACE_CONTAINERS: Tuple[ContainerSpec, ...] = (
    ("PLYRFACE.DAT", "PLYRFACE",
     "532 members (532 MMAP); 520 decodable image(s); 128x128 x520; DATA "
     "container, alignment 2048 [M]."),
    ("COACFACE.DAT", "COACFACE",
     "711 members (711 MMAP); 711 decodable image(s); 128x128 x711; COMP "
     "container, alignment 2048 [M]."),
    ("TATTOOS.DAT", "TATTOOS",
     "82 members (82 MMAP); 82 decodable image(s); 128x64 x41, 64x32 x41; "
     "DATA container, alignment 64 [M]."),
    ("UIS_PLYR.DAT", "UIS_PLYR",
     "3286 members (3286 MMAP); 3286 decodable image(s); 96x96 x3284, 16x16 "
     "x1, 8x8 x1; DATA container, alignment 64 [M]."),
)


# --------------------------------------------------------------------------
# The synthetic sources CI proves these lanes on
# --------------------------------------------------------------------------

#: One container of a synthetic disc:
#: ``(file name, chunk, alignment, carries textures)``.  The chunk and the
#: alignment are the ones the *real* container of that name carries -- ``COMP``
#: where the retail file has a codec table, ``DATA`` where it has none --
#: because the two shapes take different code paths in the writer (a plain
#: ``DATA`` container has nowhere to record a codec, so a replacement there can
#: only be stored) and a fixture that quietly picked the easier one would prove
#: the wrong half.  ``carries textures`` is ``False`` for a container the real
#: disc lists with **no** ``MMAP`` member -- ``ICONS.DAT`` is that -- so the
#: walk over one is proved rather than assumed.
SyntheticSpec = Tuple[str, str, int, bool]


def build_synthetic_art_disc(specs: Sequence[SyntheticSpec]) -> bytes:
    """A tiny ``SLUS-21770``-shaped image carrying the containers named.

    Every byte is computed from the format's own rules by
    :func:`containers.synthetic_mmap` and :func:`ea_terf.build_terf`; no game
    data is involved, which is what lets the conformance harness run these
    lanes on a machine that owns none of these discs.

    The two preload caches carry the shape the retail disc carries [M]: a
    ``COMP`` container's **directory** is copied (once in ``GAME.QKL``, twice
    in ``FE.QKL``), and a ``DATA`` container has both its directory and one of
    its **members** copied -- which is the case ``STADATA.DAT`` (55 member
    copies in ``GAME.QKL``, 12 in ``FE.QKL``), ``PLYRFACE.DAT`` (16 and 13),
    ``UIS_COMN.DAT`` (43 and 43) and ``UIS_IG.DAT`` (36) actually present.
    Both coherence paths are therefore exercised by CI rather than assumed.
    """

    require(bool(specs), "a synthetic disc needs at least one container")
    built: List[Tuple[str, str, bool, bytes]] = []
    for index, (name, chunk, alignment, textures) in enumerate(specs):
        members = [
            containers.synthetic_mmap(16, 16, seed=index * 7 + 1, retail_layout=True),
            containers.synthetic_mmap(8, 8, seed=index * 7 + 2, retail_layout=True),
            containers.synthetic_mmap(32, 16, seed=index * 7 + 3, retail_layout=True),
        ] if textures else [
            containers.synthetic_text_member(containers.SYNTHETIC_TEXT_LINES),
            containers.synthetic_text_member(containers.SYNTHETIC_TEXT_LINES[:1]),
        ]
        if chunk == "COMP":
            # 270 of UNIFORMS.DAT's 725 members and 270 of STADIUMS.DAT's 1,355
            # are empty [M]; a fixture without one would not exercise the walk
            # that has to step over them.
            members.append(b"")
        blob = ea_terf.build_terf(
            members, chunk=chunk, alignment=alignment,
            **({"codecs": [ea_terf.CODEC_STORED] * len(members)} if chunk == "COMP" else {}))
        built.append((name, chunk, textures, blob))

    head_name, _head_chunk, _head_textures, head_blob = built[0]
    head_directory = head_blob[:ea_terf.parse_terf(head_blob).data_offset]
    game_payload = [(head_name, containers.PRELOAD_KIND_HEADER, None, head_directory)]
    fe_payload = [(head_name, containers.PRELOAD_KIND_HEADER, None, head_directory),
                  (head_name, containers.PRELOAD_KIND_HEADER, None, head_directory)]
    carried = _cached_member_container(built)
    if carried is not None:
        name, blob = carried
        parsed = ea_terf.parse_terf(blob)
        game_payload.append((name, containers.PRELOAD_KIND_MEMBER, 0, parsed.stored(0)))
        fe_payload.append((name, containers.PRELOAD_KIND_HEADER, None,
                           blob[:parsed.data_offset]))

    boot = (b"BOOT2 = cdrom0:\\%s;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n"
            % containers.BOOT_FILE.encode("ascii"))
    return containers.iso_lib.build_synthetic_iso(
        files=[
            (b"SYSTEM.CNF;1", boot),
            (containers.BOOT_FILE.encode("ascii") + b";1", b"\x7fELF" + bytes(4092)),
        ],
        sub_name=b"DATA",
        sub_files=[(name.encode("ascii") + b";1", blob)
                   for name, _chunk, _textures, blob in built]
        + [(containers.PRELOAD_CACHES[0].encode("ascii") + b";1",
            containers.build_synthetic_preload_cache(game_payload)),
           (containers.PRELOAD_CACHES[1].encode("ascii") + b";1",
            containers.build_synthetic_preload_cache(fe_payload))],
    )


def _cached_member_container(built: Sequence[Tuple[str, str, bool, bytes]]
                             ) -> Optional[Tuple[str, bytes]]:
    """The first plain ``DATA`` container of textures, whose member 0 is cached.

    A ``COMP`` container is left out of the member-copy fixture on purpose: a
    rewrite there may choose ``LZH1``, which changes the stored size, and a
    cached copy is a fixed slot -- so the lane refuses, by design, and a
    fixture that expected it to succeed would be testing the wrong outcome.
    """

    for name, chunk, textures, blob in built:
        if chunk == "DATA" and textures:
            return name, blob
    return None


# --------------------------------------------------------------------------
# The lane
# --------------------------------------------------------------------------

class ArtPageLane(UniformDiscArtWriteLane):
    """One art page: catalogue, preview, export, checked import, disc write-back.

    The whole of it is inherited.  What a subclass sets is *where it points* --
    the containers, the page, the surface, the ids and the schemas -- and the
    synthetic disc CI proves it on.  Overriding anything else would be a fork
    of the writer, which is the thing this file exists not to be.
    """

    classification = "offline-writer-proved"
    #: Every texture in the lane's containers is addressable.  The uniform
    #: lane's 4,000 is a table's worth of a container that holds 7,616 images;
    #: these four hold between 73 and 6,482 and a writer that can only write
    #: the first 4,000 of them would refuse the rest for no reason a user can
    #: see.
    max_targets = 12000

    #: ``(container name, chunk, alignment, carries textures)`` for the
    #: synthetic disc.  Each mirrors the real container of that name [M].
    synthetic_layout: Tuple[SyntheticSpec, ...] = ()

    #: The page's own sentence about what it does not edit.  Rendered beside
    #: the lane, and repeated in the catalogue.
    page_scope = ""

    # -- the PCSX2 replacement identity --------------------------------

    def replacement_identities(self, target) -> Dict[str, List[str]]:
        """Both identity tables, merged: the tool's own and this file's extension.

        A texture named by either is named; one named by neither comes back
        empty, and :meth:`replacement_identity` then answers ``None`` -- which
        is the answer for 8,215 of the 8,449 distinct textures these four pages
        list [M], because the only dump that exists is 32 coin-toss screens and
        one pre-game frame.
        """

        names = {convention: list(values)
                 for convention, values in super().replacement_identities(target).items()}
        extra = load_identities(ART_PAGE_IDENTITY_DOCUMENT).get(str(target.key), {})
        for convention, values in extra.items():
            merged = names.setdefault(convention, [])
            for value in values:
                if value not in merged:
                    merged.append(value)
        return names

    def build_catalogue(self, source: Path, *, progress=None) -> Catalogue:
        catalogue = super().build_catalogue(source, progress=progress)
        document = dict(catalogue.document)
        document["page"] = self.page
        document["page_scope"] = self.page_scope
        document["identity_coverage"] = self.identity_coverage(catalogue)
        return Catalogue(catalogue.schema, catalogue.lane_id, catalogue.source,
                         catalogue.targets, document)

    def identity_coverage(self, catalogue: Catalogue) -> Dict[str, Dict[str, int]]:
        """Per container: how many textures have a PCSX2 name, and where it came from.

        ``confirmed`` counts names a texture dump of the running game has shown
        PCSX2 writing; ``derived`` counts textures whose name is computed from
        their own bytes with no dump behind it; ``named`` is either.  Counted off
        the identity tables and the catalogue rather than claimed: a synthetic
        disc no emulator ever drew comes back with ``confirmed`` 0, which is the
        honest answer and the one the page shows.
        """

        out: Dict[str, Dict[str, int]] = {}
        blank = {"listed": 0, "named": 0, "confirmed": 0, "derived": 0}
        for row in catalogue.document.get("rows", ()):
            slot = out.setdefault(str(row["container"]), dict(blank))
            slot["listed"] += 1
        for target in catalogue.targets:
            names = self.replacement_identities(target)
            confirmed = any(not convention.startswith(DERIVED_PREFIX) for convention in names)
            derived = any(convention.startswith(DERIVED_PREFIX) for convention in names)
            if not (confirmed or derived):
                continue
            slot = out.setdefault(str(target.raw.get("container")), dict(blank))
            slot["named"] += 1
            slot["confirmed" if confirmed else "derived"] += 1
        return out

    def plan(self, source: Path, recipe, catalogue: Catalogue):
        """The writer's plan, plus what PCSX2 would call each texture.

        The disc writer's own plan does not carry it -- writing to the disc
        does not need a replacement filename -- but a user choosing between the
        two routes does, and a plan that stayed silent would read as "there is
        no such name" rather than "no dump has shown this one".
        """

        planned = super().plan(source, recipe, catalogue)
        document = dict(planned.document)
        rows = []
        for row in document.get("textures", ()):
            # The key is all an identity needs, and ``plan`` may be called
            # without a catalogue -- the lane CLI does exactly that.
            target = (catalogue.target(str(row["texture"])) if catalogue is not None
                      else Target(key=str(row["texture"]), label=str(row["texture"])))
            rows.append({**row,
                         "replacement_identity": self.replacement_identity(target),
                         "replacement_identities": self.replacement_identities(target),
                         "identity_note": self.identity_note(target)})
        document["textures"] = rows
        return type(planned)(planned.lane_id, planned.target_keys,
                             planned.declared_ranges, document)

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        """The synthetic disc, and beside it one PNG per conformance edit.

        Every edit is the texture flipped top to bottom: every pixel of a flip
        is a colour the texture's own palette already holds, so the edit is
        exactly representable and the check that it landed is about the write
        rather than about quantisation.
        """

        require(bool(self.synthetic_layout),
                f"{self.lane_id} declares no synthetic layout; CI has nothing to prove it on.")
        work_dir = Path(work_dir)
        path = work_dir / f"madden09-ps2-{self.page}-art-synthetic.iso"
        path.write_bytes(build_synthetic_art_disc(self.synthetic_layout))
        catalogue = self.build_catalogue(path)
        wanted = [name for name, _chunk, _alignment, textures in self.synthetic_layout
                  if textures]
        chosen: List[Tuple[str, Path]] = []
        for name in wanted:
            for target in catalogue.targets:
                if target.raw.get("container") != name:
                    continue
                width, height, rgba = read_rgba_png(self.decode_png(path, target))
                stride = width * 4
                flipped = b"".join(rgba[row * stride:(row + 1) * stride]
                                   for row in range(height - 1, -1, -1))
                png = work_dir / f"conformance-{name.split('.')[0].lower()}.png"
                png.write_bytes(write_rgba_png(flipped, width, height))
                chosen.append((target.key, png))
                break
        require(bool(chosen),
                f"the synthetic disc for {self.lane_id} carries no texture to edit.")
        self._conformance_edits = tuple(chosen)
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple:
        chosen = getattr(self, "_conformance_edits", ())
        require(bool(chosen) and all(Path(png).is_file() for _key, png in chosen),
                "conformance_edits needs the PNGs synthetic_source writes; call "
                "synthetic_source first.")
        return tuple(Edit(key, {"png": str(png)},
                          note="conformance: write this texture back, flipped")
                     for key, png in chosen)


class StadiumArtLane(ArtPageLane):
    """``STADIUMS.DAT`` and ``STADATA.DAT``, on the Stadiums page.

    What this page edits: the 514 ``MMAP`` texture members of the two stadium
    containers -- 490 and 91 decodable images [M].  What it does **not** edit:
    the 805 ``SMF`` geometry members those same two containers carry.  A
    stadium's shape, its stands, its scoreboard mesh and its crowd are in
    those, no ``SMF`` decoder exists here, and the page says so rather than
    offering a control that could only refuse.
    """

    lane_id = "stadiums.textures"
    capability_id = "madden09ps2.stadiums.textures"
    surface = "stadiums_fields"
    page = "stadiums"
    title = "Stadium textures"
    art_containers = STADIUM_CONTAINERS
    catalog_schema = "madden09_ps2_stadium_art_catalog/v1"
    recipe_schema = "madden09_ps2_stadium_art_recipe/v1"
    write_schema = "madden09_ps2_stadium_art_write/v1"
    validators = (
        "tools/validate_madden09_ps2_art_pages.sh",
        "tools/validate_madden09_ps2_art_pages.bat",
    )
    synthetic_layout = (("STADIUMS.DAT", "COMP", 64, True),
                        ("STADATA.DAT", "COMP", 64, True))
    page_scope = (
        "Edits the MMAP textures of STADIUMS.DAT and STADATA.DAT. It does not touch the 805 SMF "
        "geometry members in the same two containers -- no SMF decoder is built anywhere in "
        "this repository and no layout for it is documented here -- and it does not know which "
        "stadium a member belongs to: neither container names its members."
    )


class FieldArtLane(ArtPageLane):
    """``FIELDART.DAT``, on the Field Art & Create-Team Art page.

    73 textures against 642 ``SMF`` geometry members [M].  Four of the textures
    are 1024x256, which is the shape a painted field surface takes; which
    member is which field is **not established here** [A].
    """

    lane_id = "field_art.textures"
    capability_id = "madden09ps2.field_art.textures"
    surface = "stadiums_fields"
    page = "field_art"
    title = "Field-art textures"
    art_containers = FIELD_ART_CONTAINERS
    catalog_schema = "madden09_ps2_field_art_catalog/v1"
    recipe_schema = "madden09_ps2_field_art_recipe/v1"
    write_schema = "madden09_ps2_field_art_write/v1"
    validators = (
        "tools/validate_madden09_ps2_art_pages.sh",
        "tools/validate_madden09_ps2_art_pages.bat",
    )
    synthetic_layout = (("FIELDART.DAT", "COMP", 64, True),)
    page_scope = (
        "Edits the 73 MMAP textures of FIELDART.DAT. It does not touch the container's 642 SMF "
        "geometry members, and it does not create a team: the create-team art this page is "
        "named for has not been located on this disc by this project."
    )


class PresentationArtLane(ArtPageLane):
    """Every UI texture container, on the Presentation page.

    The scorebug and the broadcast overlays themselves are **drawn by the
    executable** and no data file on this disc has been mapped to them -- that
    was the whole of this page's note before, and it stays true.  What was
    wrong about it was the implication that the page had nothing: 50
    containers of menu, loading, logo and in-game overlay art sit under
    ``/DATA``, 33 of them carrying ``MMAP`` members, and this lane is them.
    """

    lane_id = "presentation.ui_textures"
    capability_id = "madden09ps2.presentation.ui_textures"
    surface = "scorebug_presentation"
    page = "presentation"
    title = "Menu, loading and overlay textures"
    art_containers = UI_CONTAINERS
    catalog_schema = "madden09_ps2_ui_art_catalog/v1"
    recipe_schema = "madden09_ps2_ui_art_recipe/v1"
    write_schema = "madden09_ps2_ui_art_write/v1"
    validators = (
        "tools/validate_madden09_ps2_art_pages.sh",
        "tools/validate_madden09_ps2_art_pages.bat",
    )
    synthetic_layout = (("LOADDATA.DAT", "COMP", 64, True),
                        ("UIS_COMN.DAT", "DATA", 64, True),
                        ("ICONS.DAT", "DATA", 64, False))
    page_scope = (
        "Edits the MMAP textures of the 48 UIS_*.DAT containers, LOADDATA.DAT and ICONS.DAT. "
        "The scorebug and the broadcast overlays are drawn by the executable from values it "
        "holds, not from a data file, and nothing on this disc has been mapped to them: this "
        "page edits the art the menus, the loading screens and the in-game overlays draw, not "
        "the layout that arranges them. ICONS.DAT carries 21 members and no MMAP member at all, "
        "and UIS_MCFL.DAT's 1,188 memory-card textures are stored under EA codec 4 (IPU1), "
        "which nothing here decodes; both are listed and refused by name."
    )


class FaceArtLane(ArtPageLane):
    """Player faces, coach faces, tattoos and the menu portraits.

    ``PLYRFACE``, ``COACFACE`` and ``TATTOOS`` are also on the Uniforms &
    Equipment page, which is where they have been since that lane shipped;
    they are here too because this is the page a user looking for a player's
    face opens.  ``UIS_PLYR.DAT`` -- 3,286 96x96 portraits -- is only here.
    Which player a member belongs to is **not established here** [A]: the
    containers name nothing but the image inside each member.
    """

    lane_id = "rosters.face_textures"
    capability_id = "madden09ps2.rosters.face_textures"
    surface = "portraits_faces"
    page = "rosters"
    title = "Player and coach face, tattoo and portrait textures"
    art_containers = FACE_CONTAINERS
    catalog_schema = "madden09_ps2_face_art_catalog/v1"
    recipe_schema = "madden09_ps2_face_art_recipe/v1"
    write_schema = "madden09_ps2_face_art_write/v1"
    validators = (
        "tools/validate_madden09_ps2_art_pages.sh",
        "tools/validate_madden09_ps2_art_pages.bat",
    )
    synthetic_layout = (("COACFACE.DAT", "COMP", 2048, True),
                        ("PLYRFACE.DAT", "DATA", 2048, True),
                        ("TATTOOS.DAT", "DATA", 64, True))
    page_scope = (
        "Edits the face, tattoo and portrait textures of PLYRFACE.DAT, COACFACE.DAT, "
        "TATTOOS.DAT and UIS_PLYR.DAT. It does not edit a player's name, number, team or "
        "ratings -- those are in the DB_TEAMS.DAT databases this page already lists, and there "
        "is no database writer -- and it does not know which player a face belongs to."
    )


#: The four rows this file adds, in page order.
ART_PAGE_LANES: Tuple[type, ...] = (
    FaceArtLane, FieldArtLane, PresentationArtLane, StadiumArtLane,
)

#: ``--page`` on the command line, and the lane it names.
LANES_BY_PAGE = {lane.page: lane for lane in ART_PAGE_LANES}


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """Catalogue one page's containers, and optionally export some of them."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.art_pages",
        description="Catalogue and export a Madden NFL 09 (PS2) art page's MMAP textures.")
    parser.add_argument("--page", required=True, choices=sorted(LANES_BY_PAGE),
                        help="which art page to walk")
    parser.add_argument("--source", required=True, help="the user's own SLUS-21770 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--export", metavar="DIR",
                        help="decode textures into this NEW folder as PNGs")
    parser.add_argument("--limit", type=int, default=8,
                        help="how many textures --export writes (default 8)")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = LANES_BY_PAGE[arguments.page]()
    source = Path(arguments.source)
    try:
        started = time.time()
        catalogue = lane.build_catalogue(
            source, progress=lambda line: print(line, file=sys.stderr))
        elapsed = time.time() - started
        document = dict(catalogue.document)
        if arguments.out:
            Path(arguments.out).write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n")
        if arguments.export:
            root = Path(arguments.export)
            require(not root.exists(), f"{root} already exists; choose a folder that is free")
            root.mkdir(parents=True)
            for target in catalogue.targets[:max(1, arguments.limit)]:
                png = lane.decode_png(source, target)
                path = root / str(target.raw["file_name"])
                path.write_bytes(png)
                # Re-decoded by key off the source, not through the catalogue
                # that chose it: a check that trusts the thing it is checking
                # is not an independent one.
                again = lane.decode_png_by_key(source, target.key)
                print(f"{path.name} {len(png):,}B sha256={_sha256(png)[:16]} "
                      f"{'re-decoded equal' if again == png else 'RE-DECODE DIFFERS'}")
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("ART_PAGE page=%s containers=%d members=%d images=%d decodable=%d listed=%d "
          "not_decodable=%d seconds=%.2f"
          % (lane.page, len(lane.art_containers), document["members_read"],
             document["images_seen"], document["images_decodable"],
             document["targets_listed"], sum(document["not_decodable"].values()), elapsed))
    return 0


__all__ = [
    "ART_PAGE_IDENTITY_DOCUMENT", "ART_PAGE_LANES", "ArtPageLane", "ContainerSpec", "FACE_CONTAINERS", "FIELD_ART_CONTAINERS",
    "FaceArtLane", "FieldArtLane", "LANES_BY_PAGE", "PresentationArtLane", "STADIUM_CONTAINERS",
    "StadiumArtLane", "SyntheticSpec", "UI_CONTAINERS", "build_synthetic_art_disc",
]


if __name__ == "__main__":
    raise SystemExit(_main())
