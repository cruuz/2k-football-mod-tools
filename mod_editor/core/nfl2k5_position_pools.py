"""One-pool defensive positions for NFL 2K5 (EDGE / DT / LB), executable side (xemu-only, local research).

Why
---
Retail keeps four defensive-front roster positions (OLB 10, ILB 11, DT 15, DE 16) and the two
depth-chart tabs (4-3 / 3-4) are only two views of them.  A 3-4 outside backer is therefore an
OLB for the draft, free agency and the depth chart even though he is the team's edge rusher, and a
4-3 team's SAM/WILL are OLBs while its MIKE is an ILB.  "Option B" of
``MODERN_POSITIONS_2026-09-03.md`` (section 3.2) makes three scheme-independent pools out of the
four enums:

* ``16 = EDGE``  - 4-3 ends and 3-4 outside backers (the EDGE rename already labels the enum);
* ``15 = DT``    - every interior lineman (4-3 tackles, the 3-4 nose and the 3-4 ends);
* ``11 = LB``    - every off-ball linebacker (4-3 SAM/MIKE/WILL, 3-4 inside backers);
* ``10 = OLB``   - retired to an alias: it feeds the LB on-field lists, has a roster target of 0
  and no stock roster player carries it after the ROST pass.  It keeps its retail *name* (``OLB`` /
  ``Outside Linebacker(s)``) everywhere the game shows a roster position, see "One LB row" below.

This module is the XBE half.  The disc halves are ``tools/nfl2k5_playbook_position_recode.py``
(the category codes of the 37 stock playbooks) and ``tools/nfl2k5_roster_reclassify.py`` (the
ROST position bytes and rank/side fields).  The three compose on one disc copy in that order after
the Phase-1 labels (``nfl2k5_modern_positions``) and the EDGE rename (``nfl2k5_edge_rename``).

What this patch writes (every site pattern-checked, retail or already-applied bytes only)
-----------------------------------------------------------------------------------------
Data (``.rdata`` / ``.string_``), all addresses from the retail ``default.xbe``:

=========================================  ==========  ======================================================
site                                       VA          retail -> new
=========================================  ==========  ======================================================
enum->kind row for OLB (``FUN_00221ee0``)  0x510230    kind 15 (OLB) -> 14 (ILB): OLB-enum players join the LB lists
kind->enum byte for the OLB kind           0x5101FF    enum 10 -> 11: an OLB-kind slot counts as LB
OLB-kind list pair (``FUN_000e7530``)      0x4F59A8    lists (15, 16) -> (17, 18): OLB-kind codes read the LB lists
roster targets (``FUN_002bd410``)          0x521C68    OLB 3 / ILB 2 / DT 2 / DE 2 -> 0 / 5 / 4 / 4
roster maxima (``FUN_002bd400``)           0x521C20    OLB 5 / ILB 4 / DT 4 / DE 4 -> 0 / 7 / 6 / 6
enum abbreviation entry 11 (ILB)           0x4F26FC    -> the existing ``LB`` string at 0xE69C30 (entry 10 keeps ``OLB``)
long name (shrunk in place)                0xE69D68    ``Inside Linebacker`` -> ``Linebacker`` (0xE69D40 keeps ``Outside Linebacker``)
plural (shrunk in place)                   0xE69F10    ``Inside Linebackers`` -> ``Linebackers`` (0xE69EE8 keeps ``Outside Linebackers``)
HUD kind labels 14 / 15                    0xE6C2A0    ``ILB`` -> ``LB``; 0xE6C2A8 ``OLB`` -> ``LB``
franchise kind labels 14 / 15              0xE87EE0    ``ILB`` -> ``LB``; 0xE87EE8 ``OLB`` -> ``LB``
package legends                            0xE67820    ``|CIRCLE|SWAP ILB`` -> ``|CIRCLE|SWAP LB``; 0xE6779C ``|SQUARE|SWAP OLB`` -> ``|SQUARE|SWAP LB2``
package ``SWAP OLB`` (``FUN_00221f10``)    0x5102BC    OLB0<->OLB1 (0xC000BC3E) -> LB1<->LB2 (0xC00138BA)
depth-chart records (``0x5140D8`` table)   see below   pool fields only, the labels stay Phase 1's
=========================================  ==========  ======================================================

Depth-chart slot records (unit * retail stride 11 + slot;
``+0x40`` position enum, ``+0x44`` chain, see
``nfl2k5_modern_positions``): 4-3 SAM ``(10, 1) -> (11, 3)``, 4-3 WILL ``(10, 0) -> (11, 1)``, 3-4
right EDGE ``(10, 1) -> (16, 1)``, 3-4 left EDGE ``(10, 0) -> (16, 0)``, and the two 3-4 end records
become ``DE`` / LEFT|RIGHT DEFENSIVE END drawing ``(15, 1)`` and ``(15, 3)`` (the #2 and #3 interior
linemen; the nose keeps ``(15, 0)``).  ``chain = 3`` means "side chain, row 1" and only works with the
cave below; the other records (MIKE, NT, 3-4 MIKE/WILL, the 4-3 EDGE/DT slots) already point at the
right pool in retail and are asserted, never written.

Code, two optional sites (both on by default):

* ``linebacker_penalty_fix`` - one byte, ``FUN_0017a6d0`` at 0x17AA34: ``jne`` -> ``je``.  The
  out-of-position penalty switch handles the DL and DB kinds as "``je ok`` for every allowed enum,
  penalty otherwise" but the LB kinds as "``cmp esi,0xa; je ok; cmp esi,0xb; jne ok; penalty``",
  i.e. it penalises exactly the ILB enum in an LB slot and nobody else.  With the fix an LB slot
  accepts OLB and ILB and penalises everyone else like its siblings.  Under one pool every off-ball
  backer is enum 11, so this byte decides whether the whole corps loses 0.15 on twenty attributes.
  Unverified at runtime (needs a MLB's effective speed with the byte on/off).
* ``depth_chart_third_starter`` - the 29-byte cave of section 3.4.  ``FUN_00242ae0`` reads a record's
  ``+0x44`` as a boolean chain; the cave makes it ``chain = +0x44 & 1``, ``row += +0x44 >> 1`` so a tab
  can show a third starter from one pool (SAM = LB side row 1, the third 3-4 lineman = DT side row 1).
  The 13-byte scratch-clearing prologue at 0x242B07 becomes a ``jmp`` to the cave plus 8 ``nop``; the
  cave repeats the prologue, adds ``+0x44 >> 1`` to the row argument (``[esp+0x30]`` at that point,
  four pushes after the 0x1C frame), masks ``ebp`` to bit 0 and jumps back to 0x242B14.  The cave is
  hosted in the dead ``rand``-range helper at 0x2BA840 (21 code bytes + 11 ``nop``; no call, jump or
  pointer reference anywhere in the image, listed as dead in ``FRANCHISE_PROGRESSION_2026-09-03.md``).
  The swap ``FUN_00242ca0`` and bench move test ``+0x44`` as a boolean, so ``3`` still selects the
  side chain there. Tier 2 also introduces chain 2: it fixes those tests to use bit 0 and fixes
  the bench threshold to include the row shift. Getter callers pass the full selector to the
  cave. Without the cave the SAM record shows the WILL starter twice and the 3-4 tab shows
  the #2 interior lineman twice; the game still fields the right players (that is the playbooks' job).

Team ratings, the sim's unit strengths and the depth-chart row counts (2026-09-03 night, after Noah's
playtest: "defense is 19, overall 60, offense 80 for the Falcons, and most teams are similar"):

* The team OFFENSE / DEFENSE / OVERALL bars (team select ``FUN_0031f1d0`` -> ``FUN_000c4830`` /
  ``FUN_000c4860`` / ``FUN_000c48a0``, also the franchise sim ``FUN_001061f0``, the trade/strength
  helper ``FUN_00058330`` and the in-game ``FUN_001cf370``) are weighted averages over 20-byte
  ``.rdata`` entries ``{u16 weight, u8 starters, s8 position, getter, bench weight, lo, hi}``: for each
  entry ``FUN_000c4400`` averages the getter over every roster player at that position (starters
  weighted 1.0, the rest by the bench weight) and an entry whose position has no players contributes
  ZERO while its weight stays in the denominator.  The retired OLB enum carries 25/185 of the defense-A
  and 55/225 of the defense-B weight, so every one-pool team lost 60-75 defense points (emulated:
  Falcons 85.2 -> 19.4, exactly Noah's screen).  Fix (data): every OLB entry of the six defensive
  tables (``0x4F16A0`` defense A, ``0x4F17E0`` defense B, ``0x4F1208`` coverage, ``0x4F1388`` front vs
  run, ``0x4F1468`` run support, ``0x4F14D0`` front vs pass) now reads the LB pool (position 11) and
  every LB entry counts three starters (``starters`` 2 = rank/side < 2 = MIKE, WILL, SAM), the two
  jump-table bytes of ``FUN_000c40f0`` at 0xC4138 make LB and DT two-chain positions in both schemes
  (the one-pool depth chart uses both chains for both), and the sim's defensive consistency list
  ``0x4F1058`` (``FUN_000c4680``) reads LB #1/#2/#3 instead of OLB #1/#2 + ILB #2.  Emulated on the
  reclassified rosters: 32 teams within +4.3/-3.3 defense and +-2.5 overall of retail (retail was
  +-0.0 for the BASIC disc, which keeps the four enums).
* Depth-chart row counts: the tab init at 0x243D20 sizes a slot's list with ``FUN_000c3cb0(team,
  position)``; with the third-starter cave shifting every requested row by ``chain >> 1`` the last row
  of the SAM / third-lineman column asks for a row past the pool and renders as a blank player.  The
  count code at 0x243D50..0x243E0E is rewritten in place (same KR/PR sum, minus ``chain >> 1`` for the
  shifted records) when ``depth_chart_third_starter`` is on.
* Roster / draft / free-agency position filters: the thirteen ``Inside Linebackers`` ``.string_``
  copies read ``Linebackers``.  The ``Outside Linebackers`` rows are left exactly as retail, see
  "One LB row" below.

One LB row (2026-09-04, a user's report: "the roster view lists linebackers twice in a row")
--------------------------------------------------------------------------------------------
The home screen's Rosters -> Team Rosters, the draft, free agency, the trade block and scouting each
own a **position-filter record array** in ``.rdata``: 17-19 records of 0xB0 / 0xC8 / 0x110 / 0x118 /
0x120 / 0x128 bytes, one per roster position in football order (Quarterbacks, Halfbacks, Fullbacks,
Wide Receivers, Tight Ends, Centers, Guards, Tackles, Kickers, Punters, Defensive Tackles, Defensive
Ends, **Outside Linebackers, Inside Linebackers**, Cornerbacks, Free Safeties, Strong Safeties, and on
eight of the fifteen screens All Positions).  A record is ``{class ptr, flags, UTF-16 name ptr, ...,
roster enum at +0x18, ...}``; the count handler is ``FUN_0031AB20`` -> ``FUN_000C3CB0(team, position)``,
which counts players whose ``player+0x35`` equals the record's enum (17 = every player).  The
``Outside Linebackers`` record is always the one immediately before ``Inside Linebackers``: fifteen
arrays at 0x539520/0x5395E8, 0x53A1F8/0x53A2A8, 0x53AF90/0x53B058, 0x53DEF0/0x53E008,
0x53FBF0/0x53FD18, 0x5498E8/0x549998, 0x550F68/0x551078, 0x552798/0x5528B0, 0x5545E8/0x554700,
0x559450/0x559578, 0x55EFB0/0x55F078, 0x570D30/0x570E50, 0x57FD70/0x57FE90, 0x582658/0x582778,
0x588060/0x588178.

Beta 58 renamed **both** rows to ``Linebackers`` and pointed the OLB row's enum at 11, so every one of
those screens listed "Linebackers" twice in a row.  Removing a row is not a rename: the arrays have no
count word (they end at a record whose class pointer is NULL) and they abut each other in ``.rdata``,
so dropping an entry means moving every following record up one stride, re-terminating, and proving
that no screen indexes its array - fifteen arrays, four strides, and nothing in the image references a
record by address, so the shape can only be confirmed by running the game.  With one filter row per
roster enum being an invariant we cannot change safely, the duplicate is removed the other way: the
**retired enum 10 keeps its retail identity everywhere the game prints a roster position** - the
abbreviation table entry (``OLB``), the long name and plural (``Outside Linebacker(s)``), and the
fourteen filter records with their twelve ``Outside Linebackers`` string copies.  Enum 11 is the only
row named ``Linebackers``.  On a disc built with ``tools/nfl2k5_roster_reclassify.py`` (every preset
that turns pools on) no player carries enum 10, so the ``Outside Linebackers`` row lists nobody -
exactly what "Fullbacks" does for a team with no fullback - and on a custom roster that still carries
OLB players it lists them under their own name instead of hiding them inside a second "Linebackers".
The behaviour half of the merge (kind mapping, on-field lists, roster targets, the package swap, the
depth-chart pools, the rating tables) is unchanged: enum 10 still behaves exactly like an LB.
(Beta 58's OLB lists were also one short: the fifteenth record, 0x55EFB0 in the draft-board array, has
the retail typo ``outside Linebackers`` at 0xEAE8CC and never matched the exact-text search, so that
one screen kept a stray ``outside Linebackers`` next to ``Linebackers``.  Leaving every OLB row retail
makes the whole set consistent again.)

Not written here: the draft-value table of the draft-AI cave (``VALUE[OLB]``).  After the ROST pass no
stock player carries enum 10 and the class generator conserves positions, so the draft scorer never
sees an OLB prospect and the row is moot; leaving it keeps ``nfl2k5_draft_ai.status()`` truthful.

Composition: ``apply`` requires ``nfl2k5_modern_positions.status(payload) == "applied"`` (the labels
this rewires) and accepts the two 3-4 end records in their retail, EDGE-renamed or Phase-1
``three_four_line`` text.  ``nfl2k5_modern_positions`` recognises both pool profiles and
``nfl2k5_edge_rename`` accepts the ``DE`` text on those two records, so every module's ``status`` reads
"applied" on the finished executable. Record planning/assertions and ``tab_init_bytes(stride)``
use retail stride 11 and the active table base, including SPECIAL's thirteen rows.
``.text``, ``.rdata`` and ``.string_`` digests
are recomputed. Direct repeated apply still refuses, as before; orchestrators skip applied sites.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Mapping, Sequence

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_draft_ai import _Asm
from . import nfl2k5_modern_positions as modern

IMAGE_BASE = 0x10000

POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
ENUM_OLB, ENUM_ILB, ENUM_DT, ENUM_DE = 10, 11, 15, 16
KIND_DE, KIND_DT, KIND_ILB, KIND_OLB = 12, 13, 14, 15
LB_LIST_PAIR = (17, 18)          # the ILB kind's two on-field lists (rank order, side order)

# ---------------------------------------------------------------------------------------------
# .rdata tables
ENUM_TO_KIND_VA = 0x00510208      # 17 dwords, FUN_00221ee0
KIND_TO_ENUM_VA = 0x005101F0      # 19 bytes, FUN_00221ed0
KIND_LIST_PAIRS_VA = 0x004F5930   # 19 x (first list, second list) dwords, FUN_000e7530
ROSTER_TARGETS_VA = 0x00521C68    # 17 dwords, FUN_002bd410
ROSTER_MAXIMA_VA = 0x00521C20     # 17 dwords, FUN_002bd400
ABBREV_TABLE_VA = 0x004F26D0      # 17 string pointers, FUN_000e5f90
PACKAGES_VA = 0x0051029C          # 13 dwords, FUN_00221f10

RETAIL_ENUM_TO_KIND = (0, 2, 1, 9, 18, 16, 17, 10, 11, 8, 15, 14, 6, 7, 5, 13, 12)
RETAIL_KIND_TO_ENUM = bytes.fromhex("00020100030e0c0d09030708100f0b0a050604")
RETAIL_TARGETS = (2, 1, 1, 5, 5, 1, 1, 2, 1, 2, 3, 2, 2, 3, 3, 2, 2)
RETAIL_MAXIMA = (4, 1, 1, 7, 7, 3, 3, 4, 3, 4, 5, 4, 3, 4, 4, 4, 4)
NEW_TARGETS_BY_ENUM = {ENUM_OLB: 0, ENUM_ILB: 5, ENUM_DT: 4, ENUM_DE: 4}
NEW_MAXIMA_BY_ENUM = {ENUM_OLB: 0, ENUM_ILB: 7, ENUM_DT: 6, ENUM_DE: 6}

STRING_LB_VA = 0x00E69C30         # the retail "LB" string (the 16-way group table already uses it)
STRING_OLB_VA = 0x00E69C54
STRING_ILB_VA = 0x00E69C5C

RETAIL_PACKAGE_SWAP_OLB = 0xC000BC3E      # code OLB0 (0x0F) <-> alt OLB1 (0x2F), low bits 2, flags 0xC0000000
NEW_PACKAGE_SWAP_OLB = 0xC00138BA         # code LB1 (0x2E) <-> alt LB2 (0x4E)
PACKAGE_SWAP_OLB_VA = PACKAGES_VA + 8 * 4


def package_word(code: int, alt: int, low: int = 2, flags: int = 0xC0000000) -> int:
    return flags | (alt << 10) | (code << 2) | low


# ---------------------------------------------------------------------------------------------
# .string_ slots (UTF-16, NUL-terminated, 4-byte aligned; shrink in place only)
STRING_SITES: tuple[tuple[str, int, int, str, str], ...] = (
    ("long_ilb", 0x00E69D68, 36, "Inside Linebacker", "Linebacker"),
    ("plural_ilb", 0x00E69F10, 40, "Inside Linebackers", "Linebackers"),
    ("hud_ilb", 0x00E6C2A0, 8, "ILB", "LB"),
    ("hud_olb", 0x00E6C2A8, 8, "OLB", "LB"),
    ("franchise_ilb", 0x00E87EE0, 8, "ILB", "LB"),
    ("franchise_olb", 0x00E87EE8, 8, "OLB", "LB"),
    ("legend_swap_ilb", 0x00E67820, 36, "|CIRCLE|SWAP ILB", "|CIRCLE|SWAP LB"),
    ("legend_swap_olb", 0x00E6779C, 36, "|SQUARE|SWAP OLB", "|SQUARE|SWAP LB2"),
)

# The retired enum 10 keeps its retail name everywhere the game prints a roster position, so no
# screen shows two rows called "Linebackers" (see "One LB row" in the module docstring).  These are
# the sites this patch deliberately does NOT write; they are listed so the choice is greppable and
# so ``retail_olb_identity`` can assert it on a patched image.
# (label, VA, byte length, retail text or pointer target)
RETAINED_OLB_IDENTITY: tuple[tuple[str, int, int, object], ...] = (
    ("abbrev_enum_olb", ABBREV_TABLE_VA + 4 * ENUM_OLB, 4, STRING_OLB_VA),   # 0x4F26F8 -> "OLB" 0xE69C54
    ("long_olb", 0x00E69D40, 40, "Outside Linebacker"),
    ("plural_olb", 0x00E69EE8, 40, "Outside Linebackers"),
)

# ---------------------------------------------------------------------------------------------
# depth-chart records: (label, unit, slot, retail (position, chain), new (position, chain))
POOL_RECORDS: tuple[tuple[str, int, int, tuple[int, int], tuple[int, int]], ...] = (
    ("43_sam", modern.UNIT_43, 4, (ENUM_OLB, 1), (ENUM_ILB, 3)),
    ("43_will", modern.UNIT_43, 6, (ENUM_OLB, 0), (ENUM_ILB, 1)),
    ("34_edge_right", modern.UNIT_34, 5, (ENUM_OLB, 1), (ENUM_DE, 1)),
    ("34_edge_left", modern.UNIT_34, 6, (ENUM_OLB, 0), (ENUM_DE, 0)),
    ("34_de_left", modern.UNIT_34, 0, (ENUM_DE, 0), (ENUM_DT, 1)),
    ("34_de_right", modern.UNIT_34, 2, (ENUM_DE, 1), (ENUM_DT, 3)),
)
# the two 3-4 end records also get their text: accepted "before" texts and the new text
END_RECORD_TEXT: Mapping[str, tuple[tuple[tuple[str, str], ...], tuple[str, str]]] = {
    "34_de_left": ((("LDE", "LEFT DEF END"), ("EDGE", "LEFT EDGE RUSHER"), ("DE", "LEFT DEFENSIVE END")),
                   ("DE", "LEFT DEFENSIVE END")),
    "34_de_right": ((("RDE", "RIGHT DEF TACKLE"), ("EDGE", "RIGHT EDGE RUSHER"), ("DE", "RIGHT DEFENSIVE END")),
                    ("DE", "RIGHT DEFENSIVE END")),
}
# records that must already point at the right pool (asserted, never written)
ASSERTED_RECORDS: tuple[tuple[str, int, int, tuple[int, int]], ...] = (
    ("43_edge_left", modern.UNIT_43, 0, (ENUM_DE, 0)),
    ("43_dt_left", modern.UNIT_43, 1, (ENUM_DT, 0)),
    ("43_dt_right", modern.UNIT_43, 2, (ENUM_DT, 1)),
    ("43_edge_right", modern.UNIT_43, 3, (ENUM_DE, 1)),
    ("43_mike", modern.UNIT_43, 5, (ENUM_ILB, 0)),
    ("34_nt", modern.UNIT_34, 1, (ENUM_DT, 0)),
    ("34_will", modern.UNIT_34, 3, (ENUM_ILB, 1)),
    ("34_mike", modern.UNIT_34, 4, (ENUM_ILB, 0)),
)

# ---------------------------------------------------------------------------------------------
# code sites
PENALTY_JNE_VA = 0x0017AA34               # FUN_0017a6d0: cmp esi,0xb ; jne end  ->  je end
RETAIL_PENALTY_BYTES = bytes.fromhex("7559")
FIXED_PENALTY_BYTES = bytes.fromhex("7459")

ROW_LOOKUP_SITE_VA = 0x00242B07           # FUN_00242ae0: xor eax,eax; mov ecx,7; lea edi,[esp+0x10]; rep stosd
ROW_LOOKUP_RESUME_VA = 0x00242B14         # movzx edi, byte [edx+0x11c]
RETAIL_ROW_LOOKUP_PROLOGUE = bytes.fromhex("33c0b9070000008d7c2410f3ab")
CAVE_VA = 0x002BA840                      # dead rand-range helper (no callers), 21 bytes + 11 nop
RETAIL_CAVE_HELPER = bytes.fromhex("568bf0e878e3d8ff2bf74633d2f7f65e8bc203c7c3") + b"\x90" * 11
CAVE_SIZE = 29


# ---------------------------------------------------------------------------------------------
# team-rating tables (.rdata; 20-byte entries {u16 weight, u8 starters, s8 position, getter, bench, lo, hi})
RATING_ENTRY = 20
RATING_TABLES: Mapping[str, tuple[int, int, str]] = {
    # name: (VA, entry count, retail bytes)
    "defense_a": (0x004F16A0, 16, "2800011040380c00cdcc4c3ecdcccc3d295c4f3f1400010f40380c00cdcc4c3ecdcccc3df6285c3f0500010b40380c009a99193ecdcccc3dae47613f0a00010a40380c009a99193ecdcccc3d3d0a573f0500010540380c009a99193ecdcccc3dd7a3303f0500010640380c009a99193ecdcccc3d3333333f1400010490380c00cdcc4c3ecdcccc3db81e453f0a00010590380c009a99193ecdcccc3d5c8f423f0a00010690380c009a99193ecdcccc3d713d4a3f0500010a90380c009a99193ecdcccc3d14ae473f0500010b90380c009a99193ecdcccc3d713d4a3f0a00010450380c00cdcc4c3ecdcccc3d0000403f0a00010550380c009a99193ecdcccc3da4703d3f0a00010650380c009a99193ecdcccc3d14ae473f0a00010a50380c009a99193ecdcccc3d14ae473f0a00010b50380c009a99193ecdcccc3d14ae473f"),
    "defense_b": (0x004F17E0, 9, "3200011030380c00cdcc4c3ecdcccc3d3333333f2800010f30380c00cdcc4c3ecdcccc3d14ae473f0f00010b30380c009a99193ecdcccc3dae47613f1400010a30380c009a99193ecdcccc3d295c4f3f1e00010bb0390c009a99193ecdcccc3d6666663f2300010ab0390c009a99193ecdcccc3d0ad7633f0a000105b0390c009a99193ecdcccc3d1f852b3f14000106b0390c009a99193ecdcccc3db81e453f05000104b0390c00cdcc4c3e000000006666263f"),
    "coverage": (0x004F1208, 10, "1400010490380c00cdcc4c3ecdcccc3db81e453f0a00010590380c009a99193ecdcccc3d5c8f423f0a00010690380c009a99193ecdcccc3d713d4a3f0500010a90380c009a99193ecdcccc3d14ae473f0500010b90380c009a99193ecdcccc3d713d4a3f0a00010450380c00cdcc4c3ecdcccc3d0000403f0a00010550380c009a99193ecdcccc3da4703d3f0a00010650380c009a99193ecdcccc3d14ae473f0a00010a50380c009a99193ecdcccc3d14ae473f0a00010b50380c009a99193ecdcccc3d14ae473f"),
    "front_run": (0x004F1388, 6, "3c00011040380c00cdcc4c3ecdcccc3d295c4f3f1e00010f40380c00cdcc4c3ecdcccc3df6285c3f0a00010b40380c009a99193ecdcccc3dae47613f1400010a40380c009a99193ecdcccc3d3d0a573f0500010540380c009a99193ecdcccc3dd7a3303f0a00010640380c009a99193ecdcccc3d3333333f"),
    "run_support": (0x004F1468, 5, "1e00010bb0390c009a99193ecdcccc3d6666663f2300010ab0390c009a99193ecdcccc3d0ad7633f0a000105b0390c009a99193ecdcccc3d1f852b3f14000106b0390c009a99193ecdcccc3db81e453f05000104b0390c00cdcc4c3e000000006666263f"),
    "front_pass": (0x004F14D0, 4, "3200011030380c00cdcc4c3ecdcccc3d3333333f2800010f30380c00cdcc4c3ecdcccc3d14ae473f0f00010b30380c009a99193ecdcccc3dae47613f1400010a30380c009a99193ecdcccc3d295c4f3f"),
}
LB_STARTERS = 2                    # starters byte: rank/side < 2 -> three LB starters (MIKE, WILL, SAM)
CHAIN_INDEX_VA = 0x000C4138        # FUN_000c40f0 jump-table index bytes, one per position 0..15
RETAIL_CHAIN_INDEX = bytes.fromhex("00000003030000000003030100030302")
CHAIN_TWO_SIDED = 3                # index of the "return 0" arm: the position has a left/right (side) chain
CONSISTENCY_DEF_VA = 0x004F1058    # FUN_000c4680: 11 x (position, nth) for the sim's defensive consistency
RETAIL_CONSISTENCY_DEF = bytes.fromhex("0400000000000000040000000100000005000000000000000600000000000000100000000000000010000000010000000f000000000000000f000000010000000a000000000000000a000000010000000b00000001000000")
NEW_CONSISTENCY_DEF = RETAIL_CONSISTENCY_DEF[:64] + struct.pack("<6I", ENUM_ILB, 0, ENUM_ILB, 1, ENUM_ILB, 2)

# ---------------------------------------------------------------------------------------------
# depth-chart tab init (cb_00243d20): the row-count code, rewritten in place
TAB_INIT_VA = 0x00243D50
TAB_INIT_END_VA = 0x00243E0F       # retail tail: recompute the record pointer, jmp FUN_000f3670
RETAIL_TAB_INIT = bytes.fromhex(
    "a1b874c1006bc00b03c28d14c08b14d518415100568bf18b0db04051008bc22dfd000000c7058874c10001000000890d9474c1007415"
    "4874128b0d9c74c100e81cffe7ffa38474c100eb748b0d9c74c10057ba08000000e804ffe7ff8b0d9c74c100ba070000008bf8e8f2fe"
    "e7ff8b0d9c74c100ba0600000003f8e8e0fee7ff8b0d9c74c100ba0500000003f8e8cefee7ff8b0d9c74c100ba0400000003f8e8bcfe"
    "e7ff8b0d9c74c100ba0300000003f8e8aafee7ff03f8893d8474c1005f"
)
FN_COUNT_AT_POSITION = 0x000C3CB0  # fastcall(ecx=team, edx=position); preserves edx/edi
DC_UNIT_VA = 0x00C174B8
DC_SLOT_VA = 0x00C17478
DC_TEAM_VA = 0x00C1749C
DC_ROWS_VA = 0x00C17484
DC_PAGE_VA = 0x00C17488
DC_HEADER_VA = 0x00C17494
DC_HEADER_DEFAULT_VA = 0x005140B0
RECORD_POSITION_VA = 0x00514118    # 0x5140D8 + 0x40, indexed by (unit * 11 + slot) * 0x48
RECORD_CHAIN_VA = 0x0051411C

# ---------------------------------------------------------------------------------------------
# position-filter lists (home-screen Team Rosters, draft, free agency, trade...): the 0xB0 / 0xC8 /
# 0x110 / 0x118 / 0x120 / 0x128-byte records hold a string pointer at +0 and the roster enum at +0x18.
# The ILB records are renamed to "Linebackers"; the OLB records and their strings are listed only so
# ``filter_rows`` can read them back and prove they stay retail (see "One LB row" in the docstring).
FILTER_ILB_RECORDS = (0x5395E8, 0x53A2A8, 0x53B058, 0x53E008, 0x53FD18, 0x549998, 0x551078, 0x5528B0, 0x554700,
                      0x559578, 0x55F078, 0x570E50, 0x57FE90, 0x582778, 0x588178)
#: One per ILB record and always one stride ahead of it.  0x55EFB0 carries the retail typo
#: ``outside Linebackers`` (lower-case o) at 0xEAE8CC, which is why beta 58's exact-text sweep found
#: only fourteen.
FILTER_OLB_RECORDS = (0x539520, 0x53A1F8, 0x53AF90, 0x53DEF0, 0x53FBF0, 0x5498E8, 0x550F68, 0x552798, 0x5545E8,
                      0x559450, 0x55EFB0, 0x570D30, 0x57FD70, 0x582658, 0x588060)
FILTER_ILB_STRINGS = (0xEA4134, 0xEA4528, 0xEA4768, 0xEA9BA8, 0xEAB460, 0xEAB674, 0xEABA00, 0xEADA84, 0xEAE8F4,
                      0xEAF584, 0xEB3B04, 0xEB5860, 0xEBC000)
FILTER_OLB_STRINGS = (0xEA410C, 0xEA4500, 0xEA4740, 0xEA9B80, 0xEAB438, 0xEAB64C, 0xEAB9D8, 0xEADA5C, 0xEAE8CC,
                      0xEAF55C, 0xEB3ADC, 0xEB5838, 0xEBBFD8)
FILTER_STRING_SLOT = 40
FILTER_ENUM_OFFSET = 0x18
FILTER_OLB_RETAIL_TEXTS = ("Outside Linebackers", "outside Linebackers")


class PositionPoolsError(ValueError):
    """The one-pool position patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PositionPoolsError(message)


def _rel32(target: int, next_ip: int) -> bytes:
    return struct.pack("<i", target - next_ip)


def cave_bytes() -> bytes:
    """The 29-byte cave: retail prologue, then ``row += chain >> 1; chain &= 1``, jump back."""

    code = bytearray(RETAIL_ROW_LOOKUP_PROLOGUE)
    code += bytes.fromhex("8bc5")            # mov eax, ebp          ; ebp = record +0x44
    code += bytes.fromhex("d1e8")            # shr eax, 1
    code += bytes.fromhex("01442430")        # add [esp+0x30], eax   ; the row argument
    code += bytes.fromhex("83e501")          # and ebp, 1            ; the chain proper
    code += b"\xe9" + _rel32(ROW_LOOKUP_RESUME_VA, CAVE_VA + len(code) + 5)
    _require(len(code) == CAVE_SIZE, f"cave is {len(code)} bytes, not {CAVE_SIZE}")
    return bytes(code)


def row_lookup_hook_bytes() -> bytes:
    hook = b"\xe9" + _rel32(CAVE_VA, ROW_LOOKUP_SITE_VA + 5)
    return hook + b"\x90" * (len(RETAIL_ROW_LOOKUP_PROLOGUE) - len(hook))


def rating_table_edit(name: str) -> tuple[int, bytes, bytes]:
    """(VA, retail bytes, patched bytes) of one team-rating table: OLB entries -> the LB pool,
    every LB entry counts three starters; nothing else in the table moves."""

    va, count, retail_hex = RATING_TABLES[name]
    retail = bytes.fromhex(retail_hex)
    _require(len(retail) == count * RATING_ENTRY, f"{name}: retail transcript is {len(retail)} bytes")
    out = bytearray(retail)
    for i in range(count):
        pos = struct.unpack_from("<b", retail, i * RATING_ENTRY + 3)[0]
        if pos in (ENUM_OLB, ENUM_ILB):
            out[i * RATING_ENTRY + 2] = LB_STARTERS
            out[i * RATING_ENTRY + 3] = ENUM_ILB
    return va, retail, bytes(out)


def rating_table_rows(payload: bytes, name: str) -> list[dict[str, object]]:
    """Decode a rating table as the game reads it (for receipts, tests and the report)."""

    va, count, _ = RATING_TABLES[name]
    off = _offset(payload, va)
    rows = []
    for i in range(count):
        e = off + i * RATING_ENTRY
        weight, starters, pos = struct.unpack_from("<HBb", payload, e)
        getter, bench, lo, hi = struct.unpack_from("<Ifff", payload, e + 4)
        rows.append({"weight": weight, "starters": starters, "position": POSITIONS[pos] if 0 <= pos < 17 else pos,
                     "getter": f"0x{getter:x}", "bench": round(bench, 3), "lo": round(lo, 3), "hi": round(hi, 3)})
    return rows


def chain_index_bytes() -> bytes:
    out = bytearray(RETAIL_CHAIN_INDEX)
    out[ENUM_ILB] = CHAIN_TWO_SIDED
    out[ENUM_DT] = CHAIN_TWO_SIDED
    return bytes(out)


def tab_init_bytes(slots_per_unit: int = modern.SLOTS_PER_UNIT,
                   table_va: int = modern.SLOT_TABLE_VA) -> bytes:
    """The rewritten row-count code of the depth-chart tab init (0x243D50..0x243E0E, 191 bytes):
    same globals, same KR/PR sum over FB HB SS FS CB WR, and ``rows -= record.chain >> 1`` so a
    record that the third-starter cave shifts by one row lists one row fewer (no blank player at
    the bottom).  Falls through into the retail tail at 0x243E0F with esi pushed as retail does."""

    _require(slots_per_unit == modern.SLOTS_PER_UNIT, "unknown slot stride")
    _require(table_va in (modern.SLOT_TABLE_VA, modern.SPECIAL_TABLE_VA), "unknown slot table")
    a = _Asm(TAB_INIT_VA)
    imm = lambda va: struct.pack("<I", va).hex()  # noqa: E731
    a.b("a1" + imm(DC_UNIT_VA))                     # mov eax,[unit]
    a.b(bytes((0x6B, 0xC0, slots_per_unit)).hex())    # imul eax,eax,unit stride
    a.b("03c2")                                     # add eax,edx           ; edx = [slot] (loaded at 0x243D20)
    a.b("8d14c0")                                   # lea edx,[eax+eax*8]   ; record index * 9 (* 8 below = 0x48)
    a.b("56")                                       # push esi
    a.b("57")                                       # push edi
    a.b("8bf1")                                     # mov esi,ecx           ; this (the retail tail wants it)
    a.b("8b3cd5" + imm(table_va + 0x44))            # mov edi,[edx*8+chain]
    a.b("8b14d5" + imm(table_va + 0x40))            # mov edx,[edx*8+position]
    a.b("8b0d" + imm(DC_HEADER_DEFAULT_VA))         # mov ecx,[0x5140b0]
    a.b("c705" + imm(DC_PAGE_VA) + "01000000")      # mov dword [page],1
    a.b("890d" + imm(DC_HEADER_VA))                 # mov [header],ecx
    a.b("d1ef")                                     # shr edi,1             ; rows the cave shifts by
    a.b("8d8203ffffff")                             # lea eax,[edx-0xfd]
    a.b("83f801")                                   # cmp eax,1
    a.j8("77", "normal")                            # ja normal             ; not KR (0xfe) / PR (0xfd)
    a.b("ba08000000")                               # mov edx,8             ; FB HB SS FS CB WR = 8..3
    a.b("33ff")                                     # xor edi,edi
    a.label("returners")
    a.b("8b0d" + imm(DC_TEAM_VA))                   # mov ecx,[team]
    a.call(FN_COUNT_AT_POSITION)                    # eax = count at edx (edx, edi preserved)
    a.b("03f8")                                     # add edi,eax
    a.b("4a")                                       # dec edx
    a.b("83fa03")                                   # cmp edx,3
    a.j8("7d", "returners")                         # jge returners
    a.b("8bc7")                                     # mov eax,edi
    a.j8("eb", "store")                             # jmp store
    a.label("normal")
    a.b("8b0d" + imm(DC_TEAM_VA))                   # mov ecx,[team]
    a.call(FN_COUNT_AT_POSITION)                    # eax = count at the record's position
    a.b("2bc7")                                     # sub eax,edi
    a.j8("79", "store")                             # jns store
    a.b("33c0")                                     # xor eax,eax
    a.label("store")
    a.b("a3" + imm(DC_ROWS_VA))                     # mov [rows],eax
    a.b("5f")                                       # pop edi
    a.jmp_abs(TAB_INIT_END_VA)                      # jmp the retail tail (pops esi, jmp FUN_000f3670)
    code = a.assemble()
    size = TAB_INIT_END_VA - TAB_INIT_VA
    _require(len(code) <= size, f"tab init rewrite is {len(code)} bytes, over {size}")
    return code + b"\xcc" * (size - len(code))


def _utf16(text: str, slot: int) -> bytes:
    raw = text.encode("utf-16le") + b"\0\0"
    _require(len(raw) <= slot, f"{text!r} does not fit a {slot}-byte slot")
    return raw + b"\0" * (slot - len(raw))


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise PositionPoolsError(f"VA 0x{va:x} is in no section")


def new_targets() -> tuple[int, ...]:
    return tuple(NEW_TARGETS_BY_ENUM.get(i, v) for i, v in enumerate(RETAIL_TARGETS))


def new_maxima() -> tuple[int, ...]:
    return tuple(NEW_MAXIMA_BY_ENUM.get(i, v) for i, v in enumerate(RETAIL_MAXIMA))


@dataclass(frozen=True)
class Site:
    label: str
    va: int
    befores: tuple[bytes, ...]
    after: bytes
    group: str          # "data", "records", "penalty", "cave"

    @property
    def size(self) -> int:
        return len(self.after)


def _sites(linebacker_penalty_fix: bool, depth_chart_third_starter: bool,
           slots_per_unit: int = modern.SLOTS_PER_UNIT,
           table_va: int = modern.SLOT_TABLE_VA) -> list[Site]:
    sites: list[Site] = []

    def add(label: str, va: int, before: bytes | Sequence[bytes], after: bytes, group: str = "data") -> None:
        befores = (before,) if isinstance(before, bytes) else tuple(before)
        for b in befores:
            _require(len(b) == len(after), f"{label}: replacement length differs")
        sites.append(Site(label, va, befores, after, group))

    add("enum_to_kind_olb", ENUM_TO_KIND_VA + 4 * ENUM_OLB, struct.pack("<I", KIND_OLB), struct.pack("<I", KIND_ILB))
    add("kind_to_enum_olb", KIND_TO_ENUM_VA + KIND_OLB, bytes([ENUM_OLB]), bytes([ENUM_ILB]))
    add("olb_kind_lists", KIND_LIST_PAIRS_VA + 8 * KIND_OLB, struct.pack("<II", 15, 16), struct.pack("<II", *LB_LIST_PAIR))
    add("roster_targets", ROSTER_TARGETS_VA, struct.pack("<17I", *RETAIL_TARGETS), struct.pack("<17I", *new_targets()))
    add("roster_maxima", ROSTER_MAXIMA_VA, struct.pack("<17I", *RETAIL_MAXIMA), struct.pack("<17I", *new_maxima()))
    add("abbrev_enum_ilb", ABBREV_TABLE_VA + 4 * ENUM_ILB, struct.pack("<I", STRING_ILB_VA), struct.pack("<I", STRING_LB_VA))
    add("package_swap_olb", PACKAGE_SWAP_OLB_VA, struct.pack("<I", RETAIL_PACKAGE_SWAP_OLB), struct.pack("<I", NEW_PACKAGE_SWAP_OLB))
    for label, va, slot, old, new in STRING_SITES:
        add(label, va, _utf16(old, slot), _utf16(new, slot))
    for label, unit, slot, old_pool, new_pool in POOL_RECORDS:
        va = modern.record_va(unit, slot, slots_per_unit, table_va=table_va)
        if label in END_RECORD_TEXT:
            befores_text, after_text = END_RECORD_TEXT[label]
            befores = tuple(modern.slot_text(*t) + struct.pack("<II", *old_pool) for t in befores_text)
            after = modern.slot_text(*after_text) + struct.pack("<II", *new_pool)
            add(label, va, befores, after, "records")
        else:
            add(label, va + modern.SLOT_TEXT_BYTES, struct.pack("<II", *old_pool), struct.pack("<II", *new_pool), "records")
    for name in RATING_TABLES:
        va, before, after = rating_table_edit(name)
        add(f"rating_{name}", va, before, after, "ratings")
    add("chain_index", CHAIN_INDEX_VA, RETAIL_CHAIN_INDEX, chain_index_bytes(), "ratings")
    add("consistency_defense", CONSISTENCY_DEF_VA, RETAIL_CONSISTENCY_DEF, NEW_CONSISTENCY_DEF, "ratings")
    for i, va in enumerate(FILTER_ILB_STRINGS):
        add(f"filter_ilb_string_{i}", va, _utf16("Inside Linebackers", FILTER_STRING_SLOT), _utf16("Linebackers", FILTER_STRING_SLOT), "filters")
    # The Outside Linebackers rows (FILTER_OLB_RECORDS / FILTER_OLB_STRINGS) are NOT written: one
    # row per roster enum is the arrays' invariant, so renaming them too is what put two
    # "Linebackers" rows next to each other on every roster screen.
    if linebacker_penalty_fix:
        add("linebacker_penalty_jne", PENALTY_JNE_VA, RETAIL_PENALTY_BYTES, FIXED_PENALTY_BYTES, "penalty")
    if depth_chart_third_starter:
        add("row_lookup_hook", ROW_LOOKUP_SITE_VA, RETAIL_ROW_LOOKUP_PROLOGUE, row_lookup_hook_bytes(), "cave")
        add("row_lookup_cave", CAVE_VA, RETAIL_CAVE_HELPER[:CAVE_SIZE], cave_bytes(), "cave")
        add("tab_init_rows", TAB_INIT_VA, RETAIL_TAB_INIT, tab_init_bytes(slots_per_unit, table_va), "cave")
    return sites


def _site_state(payload: bytes, site: Site) -> str:
    off = _offset(payload, site.va)
    got = payload[off: off + site.size]
    if got == site.after:
        return "applied"
    if got in site.befores:
        return "retail"
    return "foreign"


def _asserted_records_ok(payload: bytes) -> bool:
    stride = modern.layout_stride(payload)
    for _label, unit, slot, pool in ASSERTED_RECORDS:
        off = _offset(payload, modern.record_va(unit, slot, stride, table_va=modern.layout_table(payload))) + modern.SLOT_TEXT_BYTES
        if struct.unpack_from("<II", payload, off) != pool:
            return False
    return True


def site_states(payload: bytes, *, linebacker_penalty_fix: bool = True,
                depth_chart_third_starter: bool = True) -> dict[str, str]:
    try:
        sites = _sites(linebacker_penalty_fix, depth_chart_third_starter, modern.layout_stride(payload), modern.layout_table(payload))
        states = {site.label: _site_state(payload, site) for site in sites}
        if not _asserted_records_ok(payload):
            return {label: "foreign" for label in states}
        return states
    except (PositionPoolsError, ValueError, struct.error):
        return {site.label: "foreign" for site in _sites(linebacker_penalty_fix, depth_chart_third_starter)}


def status(payload: bytes, *, linebacker_penalty_fix: bool = True, depth_chart_third_starter: bool = True) -> str:
    """'retail', 'applied', or 'foreign' (bytes match neither; refuse to touch)."""

    states = set(site_states(payload, linebacker_penalty_fix=linebacker_penalty_fix,
                             depth_chart_third_starter=depth_chart_third_starter).values())
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"


def read_tables(payload: bytes) -> dict[str, object]:
    """The bridged tables as the game would read them (for receipts and tests)."""

    e2k = struct.unpack_from("<17I", payload, _offset(payload, ENUM_TO_KIND_VA))
    k2e = payload[_offset(payload, KIND_TO_ENUM_VA): _offset(payload, KIND_TO_ENUM_VA) + 19]
    pairs = list(struct.iter_unpack("<II", payload[_offset(payload, KIND_LIST_PAIRS_VA): _offset(payload, KIND_LIST_PAIRS_VA) + 19 * 8]))
    targets = struct.unpack_from("<17I", payload, _offset(payload, ROSTER_TARGETS_VA))
    maxima = struct.unpack_from("<17I", payload, _offset(payload, ROSTER_MAXIMA_VA))
    abbrev_ptrs = struct.unpack_from("<17I", payload, _offset(payload, ABBREV_TABLE_VA))
    packages = struct.unpack_from("<13I", payload, _offset(payload, PACKAGES_VA))

    return {
        "enum_to_kind": list(e2k), "kind_to_enum": list(k2e), "kind_list_pairs": [tuple(p) for p in pairs],
        "roster_targets": dict(zip(POSITIONS, targets)), "roster_maxima": dict(zip(POSITIONS, maxima)),
        "abbreviations": [_string_at(payload, p) for p in abbrev_ptrs],
        "packages": [f"0x{w:08x}" for w in packages],
        "package_swap_olb": {"code": (packages[8] >> 2) & 0xFF, "alt": (packages[8] >> 10) & 0xFF},
        "records": {label: modern.read_record(payload, unit, slot)
                    for label, unit, slot, *_ in POOL_RECORDS + tuple((l, u, s, p) for l, u, s, p in ASSERTED_RECORDS)},
    }


def _string_at(payload: bytes, va: int) -> str:
    off = _offset(payload, va)
    end = off
    while payload[end: end + 2] != b"\0\0":
        end += 2
    return payload[off: end].decode("utf-16le", "replace")


def filter_rows(payload: bytes) -> list[dict[str, object]]:
    """The two linebacker rows of every position-filter array, as a screen would print them.

    Fifteen screens, one ``Outside Linebackers`` record immediately followed by one
    ``Inside Linebackers`` record.  After ``apply`` the second reads ``Linebackers`` and the first is
    untouched, so no screen shows the same row name twice.
    """

    rows: list[dict[str, object]] = []
    for olb_va, ilb_va in zip(FILTER_OLB_RECORDS, FILTER_ILB_RECORDS):
        entry: dict[str, object] = {"olb_record": f"0x{olb_va:x}", "ilb_record": f"0x{ilb_va:x}"}
        for key, va in (("olb", olb_va), ("ilb", ilb_va)):
            off = _offset(payload, va)
            pointer, enum = struct.unpack_from("<I", payload, off)[0], struct.unpack_from("<I", payload, off + FILTER_ENUM_OFFSET)[0]
            entry[f"{key}_name"] = _string_at(payload, pointer)
            entry[f"{key}_enum"] = enum
        entry["duplicate"] = entry["olb_name"] == entry["ilb_name"]
        rows.append(entry)
    return rows


def retail_olb_identity(payload: bytes) -> bool:
    """True when every place the game prints the retired enum 10 still reads its retail name."""

    try:
        for _label, va, size, expected in RETAINED_OLB_IDENTITY:
            off = _offset(payload, va)
            if isinstance(expected, int):
                if struct.unpack_from("<I", payload, off)[0] != expected:
                    return False
            elif payload[off: off + size] != _utf16(str(expected), size):
                return False
        for va in FILTER_OLB_STRINGS:
            if _string_at(payload, va) not in FILTER_OLB_RETAIL_TEXTS:
                return False
        for va in FILTER_OLB_RECORDS:
            if struct.unpack_from("<I", payload, _offset(payload, va) + FILTER_ENUM_OFFSET)[0] != ENUM_OLB:
                return False
    except (PositionPoolsError, ValueError, struct.error):
        return False
    return True


def apply(payload: bytes, *, linebacker_penalty_fix: bool = True,
          depth_chart_third_starter: bool = True) -> tuple[bytes, Mapping[str, object]]:
    """Return the patched XBE bytes plus a receipt; refuses anything but retail sites."""

    _require(modern.status(payload) == "applied",
             "apply the Phase-1 scheme labels (nfl2k5_modern_positions) before the position pools")
    state = status(payload, linebacker_penalty_fix=linebacker_penalty_fix,
                   depth_chart_third_starter=depth_chart_third_starter)
    _require(state == "retail", f"position-pool sites are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    header = _header_size(payload)
    touched: set[int] = set()
    edits = []
    for site in _sites(linebacker_penalty_fix, depth_chart_third_starter, modern.layout_stride(payload), modern.layout_table(payload)):
        off = _offset(payload, site.va)
        before = bytes(buf[off: off + site.size])
        buf[off: off + site.size] = site.after
        if off >= header:
            touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": site.label, "group": site.group, "va": f"0x{site.va:x}", "file_offset": f"0x{off:x}",
                      "before": before.hex(), "after": site.after.hex()})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched, linebacker_penalty_fix=linebacker_penalty_fix,
                    depth_chart_third_starter=depth_chart_third_starter) == "applied", "post-apply verification failed")
    _require(modern.status(patched) == "applied", "the Phase-1 labels no longer read applied after the pool rewrite")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {"edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched),
                     "linebacker_penalty_fix": linebacker_penalty_fix,
                     "depth_chart_third_starter": depth_chart_third_starter,
                     "cave_va": f"0x{CAVE_VA:x}" if depth_chart_third_starter else None,
                     "tables": read_tables(patched), "units": modern.read_units(patched),
                     "rating_tables": {name: rating_table_rows(patched, name) for name in RATING_TABLES},
                     "filter_rows": filter_rows(patched),
                     "retail_olb_identity": retail_olb_identity(patched)}


__all__ = [
    "ASSERTED_RECORDS", "CAVE_SIZE", "CAVE_VA", "END_RECORD_TEXT", "ENUM_TO_KIND_VA", "KIND_LIST_PAIRS_VA",
    "KIND_TO_ENUM_VA", "NEW_PACKAGE_SWAP_OLB", "PACKAGES_VA", "PENALTY_JNE_VA", "POOL_RECORDS", "POSITIONS",
    "PositionPoolsError", "RETAIL_CAVE_HELPER", "RETAIL_ENUM_TO_KIND", "RETAIL_KIND_TO_ENUM", "RETAIL_MAXIMA",
    "RETAIL_PACKAGE_SWAP_OLB", "RETAIL_PENALTY_BYTES", "RETAIL_ROW_LOOKUP_PROLOGUE", "RETAIL_TARGETS",
    "RETAINED_OLB_IDENTITY", "FILTER_OLB_RETAIL_TEXTS", "filter_rows", "retail_olb_identity",
    "ROSTER_MAXIMA_VA", "ROSTER_TARGETS_VA", "ROW_LOOKUP_RESUME_VA", "ROW_LOOKUP_SITE_VA", "STRING_LB_VA",
    "STRING_SITES", "Site", "apply", "cave_bytes", "new_maxima", "new_targets", "package_word", "read_tables",
    "row_lookup_hook_bytes", "site_states", "status",
    "RATING_TABLES", "CHAIN_INDEX_VA", "CONSISTENCY_DEF_VA", "TAB_INIT_VA", "TAB_INIT_END_VA", "RETAIL_TAB_INIT",
    "FILTER_ILB_RECORDS", "FILTER_OLB_RECORDS", "FILTER_ILB_STRINGS", "FILTER_OLB_STRINGS", "LB_STARTERS",
    "chain_index_bytes", "rating_table_edit", "rating_table_rows", "tab_init_bytes",
]
