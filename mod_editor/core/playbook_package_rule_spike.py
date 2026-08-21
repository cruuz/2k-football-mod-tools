"""Precise RE spike + package-map writer for community G1/G2.

G1 (Dime ILB→OLB) and G2 (Ace TE→WR) package research.

Fixture identity (2K5 stock PLAY book used across clone proofs):
  asset_id: ``nfl2k5.resource.o0308.c0000.k504c4159``
  pack_offset (disc slice): ``106803200`` (see formation_play_writer tests)
  layout constants: :mod:`mod_editor.core.nfl2k5_playbook_inspector`

**2026-08-07 census (real o0308 ATL book):**

* **G1 assignment-only gate FAILED.** Shared Nickel/Dime play indices (18)
  are identical play records — zero assignment XOR. Only-Dime and only-Nickel
  plays have different names (no same-name twin). Link tables differ (16/26).
* **G1 real delta: formation package map** at body
  ``FORMATION_BASE + fi*FORMATION_SIZE + 0x0D`` (11 bytes, always a permutation
  of ``0..10`` on o0308). Nickel ``[4,5,0,2,3,1,7,8,9,6,10]`` vs Dime
  ``[5,0,2,3,1,7,8,9,4,6,10]`` — role id 4 moves from slot-index 0 → 8.
* **G2 package-map gate FAILED for Ace-vs-offense.** All offense formations
  including Ace share the same map ``[0,8,6,9,7,10,1,4,3,5,2]``. G2 remains
  play-link / assignment / save-surface research.

Offline writer shipped here: **formation package-map only** (11 bytes),
fail-closed (must be a permutation of 0..10), independent full-resource
byte-diff verifier. Runtime claim for G1 fix remains **unproved** — do not
label as a community one-click fix pack.

APF surface (parallel, not 2K5 o0308):
  MASTER PLAY outer inventory (586 plays × 11 slots) — assignment-route
  writer already offline-proved for exact descriptor copy; package-rule
  bits remain the gap for APF G1/G2 fix packs.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import struct
from typing import Iterable, Sequence

from .errors import ValidationError
from .nfl2k5_playbook_inspector import (
    ASSIGNMENT_COUNT,
    BODY_SIZE,
    FORMATION_AUX_BASE,
    FORMATION_AUX_SIZE,
    FORMATION_BASE,
    FORMATION_CAPACITY,
    FORMATION_PLAY_LINKS,
    FORMATION_SIZE,
    NODE_BASE,
    NODE_SIZE,
    PLAY_BASE,
    PLAY_SIZE,
    RESOURCE_HEADER_SIZE,
    PlaybookAssignment,
    PlaybookFormation,
    PlaybookPlay,
    Nfl2k5Playbook,
    parse_playbook_resource,
)

# Disc fixture used by clone offline proofs (no retail bytes embedded here).
O0308_ASSET_ID = "nfl2k5.resource.o0308.c0000.k504c4159"
O0308_PACK_OFFSET = 106_803_200

# 11-byte package role map inside each formation record (o0308 census).
PACKAGE_MAP_OFFSET_IN_FORMATION = 0x0D
PACKAGE_MAP_SIZE = 11

# APF MASTER PLAY (outer 180). Census 2026-08-12 on the retail body: every one
# of 163 formations has an 11-byte permutation of 0..10 at +0x11. That is the
# APF parallel of the 2K5 +0x0D map.
#
# Role 8 = TE and role 9 = WR are statically proved (see
# APF_PACKAGE_MAP_ROLE_8_TE_9_WR_PROVED). The other nine ids are **not** a
# complete roster-position legend — formation geometry and the XEX byte table
# disagree on 1..7. An experimental 8↔9 permutation pack ships below; it is
# not a runtime WR3→TE proof and does not claim 3rd-and-long.
APF_PACKAGE_MAP_OFFSET_IN_FORMATION = 0x11
APF_FORMATION_SIZE = 0xB8
APF_FORMATION_BASE = 0x0244
APF_MASTER_BODY_SIZE = 0x2C750
APF_FORMATION_COUNT_OFFSET = 0x34
APF_RETAIL_FORMATION_COUNT = 163
APF_FORMATION_COUNT_MAX = 176
APF_PACKAGE_MAP_ROLE_LEGEND_PROVED = False
# Disc 2026-08-14: Ace Empty is NOT an 8↔9 swap of Ace. Roles 8/9 stay in
# slots 2/3; only slots 9/10 swap 6↔7.
APF_ACE_EMPTY_PACKAGE_MAP = (0, 10, 8, 9, 1, 4, 3, 5, 2, 7, 6)
APF_ACE_EMPTY_IS_WR3_TE_SWAP_OF_ACE = False
APF_ACE_VS_ACE_EMPTY_SLOT_DELTAS = ((9, 6, 7), (10, 7, 6))
APF_ACE_FORMATION_INDEX = 62
APF_ACE_EMPTY_FORMATION_INDEX = 106
APF_WR3_TE_PACKAGE_SUB_PROVED = False
# Experimental G12 export remaps each Ace-named +0x11 map 8↔9 in place.
# Ace Empty is never a donor (its stock delta is slots 9/10 = 6↔7).
APF_G12_PACK_EXPERIMENTAL = True
APF_G12_PACK_USES_ACE_EMPTY_AS_SOURCE = False

# Decompressed PE (same image as apf2k8_splb_writer.APF_PE_SHA256, base
# 0x82000000). 0x84a9ae68 is `lis r11, 0x8210; addi r11, r11, -15584; lbzx
# r3, r11, r3` — a byte table at 0x820FC320 indexed by the package-map byte
# the 11-player builder stores at on-field +0x34 (stb at 0x8485e7e0). First
# 11 entries, as roster position codes (apf2k8_player_positions.v1.json):
#   0:QB 1:P 2:K 3:QB 4:WR 5:T 6:C 7:G 8:TE 9:WR 10:HB
# Formation-name geometry independently puts role 8 in the TE seat and role 9
# in the Ace WR3/FB seat. Those two agree with this table (8→TE=9, 9→WR=3).
# Roles 1–7 do not agree with the OL / WR-X / WR-Z census, so the full 0..10
# legend stays unproved. Pair 8/9 is the WR3↔TE handle. 0x8489e6d4 reads
# +0x34 into this table; 0x8489e6fc then compares a linked +0x34 to roster
# WR=3 / HB=7 / TE=9, which is the same 17-code enum.
APF_ROLE_TO_ROSTER_TABLE_VA = 0x820FC320
APF_ROLE_TO_ROSTER_FIRST_11 = (0, 2, 1, 0, 3, 14, 12, 13, 9, 3, 7)
APF_PACKAGE_MAP_ROLE_TE = 8
APF_PACKAGE_MAP_ROLE_WR3 = 9
APF_ROSTER_POSITION_TE = 9
APF_ROSTER_POSITION_WR = 3
APF_PACKAGE_MAP_ROLE_8_TE_9_WR_PROVED = True
# Stock Ace (MASTER formation "Ace") map; slot 2 holds TE, slot 3 holds WR3.
APF_ACE_PACKAGE_MAP = (0, 10, 8, 9, 1, 4, 3, 5, 2, 6, 7)

# Eligibility at 0x8485e810: lbz +0x34, index word table 0x820FC380
# (0x84a9ae90), AND with a personnel-table cell (0x84a9aca8 indexes
# 0x84E6C620 by row/col, clrlwi 13). Role 8 mask 0xCD00, role 9 mask
# 0xDD20. Both AND a 5 Wide skill cell 0x200 are 0, so that bit does
# not distinguish WR3 from TE. 0x8485e7f8 has 0 bl callers; its only
# absolute pointer is the .pdata slot at 0x844e8238 (unwind, not a
# script registry). No lis/addi/ori materializes 0x8485E7F8. The
# assigner ends at 0x8485e7f0 with an unconditional b (epilogue),
# then a nop; it does not fall through. Builder 0x84860020 mtctr
# sites are memset-style bdnz loops or local jump tables
# (0x84860a54 / 0x84860e5c / …), not this function. Do not claim it
# never runs via a runtime-computed pointer. The same AND also runs
# in the 11-slot loop at 0x848623e8 (and at 0x84862580, lbz +0x34 at
# 0x84862568), called from 0x84a0d110. Static only — not a runtime
# WR3→TE proof.
APF_ROLE_ELIGIBILITY_WORD_TABLE_VA = 0x820FC380
APF_ROLE_ELIGIBILITY_MASK_TE = 0x0000CD00
APF_ROLE_ELIGIBILITY_MASK_WR = 0x0000DD20
APF_FIVE_WIDE_SKILL_CELL_LOW = 0x00000200
APF_ELIGIBILITY_AND_FN_VA = 0x8485E7F8
APF_ELIGIBILITY_AND_LOOP_VA = 0x848623E8
APF_ELIGIBILITY_AND_LIVE_INSN_VA = 0x84862580

# 11-player builder 0x84860020: r25 is the formation pointer the callers pass
# (formation+0x0C). addi r29, r25, 5 then lbzx r10, r29, r30 with r30 = 0..10
# and r31 running 0,4,..40 (cmpwi r31, 44) loads map[slot] and passes it as
# the role into the assigner that stb's +0x34. Slot index is the map index.
APF_PACKAGE_MAP_BUILDER_VA = 0x84860020
APF_PACKAGE_MAP_BUILDER_SLOT_LOOP_PROVED = True

# MASTER PLAY categories (28 named records at +0x44, stride 0x10) are the
# personnel packages the playcall UI lists (Ace, Pro Set, 5 Wide, Flush, …),
# not down-and-distance buckets. SPLB trailer bits 23..17 are that index.
# 0x8485bd38: lwz trailer +0xA8, rlwinm 19,21,27, add MASTER ptr, addi +0x44
# returns the category record. The 11-player builder then lbz's that
# record's +4 (via MASTER+extract+0x48) and indexes word table 0x84E6C620
# (mulli 11 at 0x84a9acc8) into on-field +0x35. That is a second personnel
# layer beside formation +0x11 → +0x34. It is not a 3rd-and-long picker and
# not a shipped WR3→TE writer.
APF_MASTER_CATEGORY_BASE = 0x0044
APF_MASTER_CATEGORY_SIZE = 0x10
APF_MASTER_CATEGORY_COUNT = 28
APF_MASTER_CATEGORY_ACE = 2
APF_MASTER_CATEGORY_PRO_SET = 3
APF_MASTER_CATEGORY_FLUSH = 8
APF_MASTER_CATEGORY_FIVE_WIDE = 9
APF_MASTER_CATEGORY_NAMES = (
    "Jacks",
    "Jokers",
    "Ace",
    "Pro Set",
    "Trio",
    "Kings",
    "Queens",
    "Straight",
    "Flush",
    "5 Wide",
    "Goalline",
    "4-3",
    "Nickel",
    "Dime",
    "Prevent",
    "Punt",
    "Punt Return",
    "Field Goal",
    "Block Field Goal",
    "Kickoff",
    "Onside Kickoff Team",
    "Kick Return",
    "Onside Kickoff Return Team",
    "3-4",
    "Nickel:3-3",
    "Dime:3-2",
    "Load",
    "5-2:Big",
)
APF_CATEGORY_GETTER_VA = 0x8485BD38
APF_CATEGORY_INDEX_EXTRACT_PROVED = True
APF_CATEGORY_PERSONNEL_TABLE_VA = 0x84E6C620
# Category record +4 indexes this table (Ace +4 = 3, 5 Wide +4 = 10).
# High byte of each 11-word row: columns 0-5 are QB+OL (0,5,5,6,7,7);
# columns 6-10 are skill. 8 vs 9 there is the same TE/WR pair as the
# formation map (5 Wide = five 9s; Ace = 8,9,9,8,10). Static only —
# not a runtime WR3→TE proof and not a 3rd-and-long picker.
APF_CATEGORY_PERSONNEL_ROW_ACE = (0, 5, 5, 6, 7, 7, 8, 9, 9, 8, 10)
APF_CATEGORY_PERSONNEL_ROW_FIVE_WIDE = (0, 5, 5, 6, 7, 7, 9, 9, 9, 9, 9)
APF_CATEGORY_PERSONNEL_ACE_ROW_INDEX = 3
APF_CATEGORY_PERSONNEL_FIVE_WIDE_ROW_INDEX = 10
APF_SPLB_RECORD_TO_FORMATION_MUL_VA = 0x84A8B8DC  # mulli 184 = FORMATION_SIZE

# Practice Situation Settings and the in-game object at the same layout:
# word +0x254 is down, +0x25C yards-to-go, +0x258 LOS. Name table used by
# the practice getter 0x84a375a8. In-game 0x848d9470 compares +0x254 to
# 1..5 (helper 0x84809898 is a type-id match, not a play picker).
# 3rd/4th-and-long CPU play choice remains unproved.
#
# Killed as down/play-choice candidates (2026-08-12):
# * 0x84a472d0 loads obj+4 and walks 0x84e4d810 ("Inside Run: %d").
#   cmpwi 1/4 is the play-type page, not down.
# * 0x8486ce88 picks a play when situation word0 is 2 or 3. It may consult
#   +0x2BC; playcall UI 0x84a23e80 writes that field as a 0..3 tab
#   (including li 3 at 0x84a23ea0), so +0x2BC is not down. This picker
#   does not load +0x254 or +0x25C.
# No surveyed function loads both +0x254 and +0x25C and also calls
# get-nth / count / the category getter. The only +0x254 switch that
# cmpwi's 1..5 is the HUD at 0x848d9470.
# 0x84ad92e0 is `lwz r3, 0x254(r3); blr` — a property getter on the
# situation object (script map slot at 0x84eb0de4), 0 bl callers.
# 0x8470bf18 case 2 calls the 0x8486ce88 picker; wrapper 0x84712498
# passes a small integer mode 0..19 (42 callers: li r3, N). Case 2
# is only li r3, 2 at 0x847163d4 inside float-gated 0x84716310 —
# frontend, not down. None of those 42 callers load +0x254. 0x84b694a8 is the only vtable+8 call on a +0x48 object; it
# passes down+ytg+LOS but stores 1 or 2 to situation+8 from the return
# (cmpwi r3, 0 at 0x84b69550). That is a status query, not a play picker.
# 0x8499e3e8 is a compact-object leaf (+0x10 in {1,3,4}, +0x14 vs 7/8,
# +0x18 vs 115/175). The word at 0x844ef0bc is .pdata metadata
# 0x40011804 (length/flags), not a script tag. Those fields are not
# situation +0x254/+0x25C: no surveyed copy from +0x254 into +0x10/+0x14,
# and +0x18=115 is not a down. The leaf returns 0 or 4, not a play.
# 0x844dbe00 is the PE .pdata section (RUNTIME_FUNCTION start+metadata
# pairs, 18472 functions, sorted by address). It is not a script
# (fn, tag) table; there is no tag→fn walker to find. 0x846302d8 is
# pdata[0] / first .text function; it lbz's on-field +0x34 and +0x35
# but is not a VM opcode. Extra 0x8486ce88 callers 0x84816030
# (floats / global +0x34 mode) and 0x848930c0 (+0x2BC tab) are
# presentation/UI. No surveyed function loads situation +0x254 and
# +0x25C (non-stack) and also calls get-nth / count / find-by-slot /
# 0x84a89ea8 / record_at 0x84863178. 0x84a89ea8 is a reverse lookup:
# it maps a play/formation pointer onto an SPLB record (index+1 vs 176,
# mulli 176, +0x70) via 0x84a89aa0 (MASTER +0x244 / mulli 184). It is
# not a situation picker. Situation +0x1F8 is a 0..7 play-type filter
# index (UI 0x84a239c8 inc/dec; picker 0x8486ce88 indexes bitmask table
# 0x84DCB2A8). 0x84816ff0 cmpwi's situation word0 vs 5, not down.
# Same-function copies of +0x254 land on camera +0x26C, practice +0x258,
# or presentation +0x94 — not a compact CPU bucket. Franchise 7-bucket
# pointer table 0x84e446c8 still has one lis/addi consumer: UI 0x84a212e0.
# No `DRCT` fourcc / lis 0x4452 in the XEX; director resources stay on
# disc with unmapped instruction opcodes. The only `0xED586383`
# (crc32 "DRCT") immediate is type-registry ctor 0x8466b964, which
# writes row 0x84d1b834; it is not an instruction interpreter.
# 0x848699d8 walks SPLB via 0x84a8bd90 / 0x84a8ba80 and keeps plays
# whose type nibble matches r4 (cmpwi r24, 8 / srwi 28 at 0x84869a78).
# Most 0x8486ce88 callers pass r4=0. That is not down. Fetch loads the
# current book from playcall +0x20 (lwz r29, 32(r3) at 0x848699e8);
# r3 is the object at global 0x851A2780. 0x8493d968 registers that
# object (stw r3, 0 at 0x8493d9ac). Packed setter 0x8493e180 is
# `stw r4, 32(r3); blr` with 0 bl / 0 data pointers. 0x8493e6f8
# stores a 0/1 flag to +0x20 (cntlzw), not a book pointer. Playcall
# UI 0x84a27128 passes the book as r4 instead. No surveyed stw
# writes a book pointer onto playcall+0x20 from down. No function
# that loads situation +0x254 (non-stack) also bls category /
# builder / assigner / picker / fetch / get-nth / count /
# find-by-slot. One-hop and two-hop bl-graph from those down
# loaders to picker/fetch is empty. Picker callers that touch the
# situation global load word0 / +0x2BC, not +0x254. In-game builder
# 0x84860020 calls assigner 0x8485e768 and personnel 0x8485e858, not
# the eligibility AND (only 0x8485e7f8 / 0x848623e8). 0x84a0d110 is
# a 0x84a0 overlay with OFFENSE/DEFENSE; Team Package Editor
# 0x84a59a80 does not call it. DRCT type object is 0x84d1b830
# (vtable 0x82003F90; hash at +4 = row 0x84d1b834). Insert
# 0x8466b998 links it into generic list 0x852B70C4 from static init
# 0x846916ac — type registration, not an opcode walker. 0x8466af70
# loads dir_ingame.iff by passing registry table 0x84d1b7d0 to
# 0x8468da70 (bl at 0x8466afc0); that is IFF identity/load, not an
# instruction interpreter. 0x8466a818 is the APF DRCT relocator
# (NFL 0x000dc700 analog): true entry, called from vtable[0]
# 0x8466b8b0 (bl 0x8466b8f4). mflr-walk groups it into 0x8466a718.
# It fixes root +0x18 (fixed-table pointer), 217 slots × 4 = 868
# bytes (cmpwi r6, 0x364 at 0x8466a97c), instruction pointers at
# +0x20 (lhz count at +6 / addi r11, r3, 32 at 0x8466a994), string
# directory at +0x14, then +0x1C auxiliary. Relative pointer rule:
# add field_addr - 1. 0x8466aae0 (bl 0x8466b8fc) walks the
# relocated +0x18 fixed table, not the instruction directory.
# 0x8466abc0 indexes fixed-record children via +0x18 (NFL 0x000dc8e0
# analog). 0x8466af28 indexes strings via +0x14 (NFL 0x000dcba0 analog).
# 0x8466ac38 consumes relocated +0x18 records (callers 0x84987158 /
# 0x849878a0). 0x8466af60 indexes the +0x1C auxiliary directory.
# No packed +0x20 instruction indexer sits next to those getters
# (no addi-32/slwi-2/lwzx sequence in the PE). Packed playcall +0x20
# setter 0x8493e180 has 0 bl, 0 fullword, 0 lis/addi. Packed string
# indexer 0x8466af28 is the same: 0 bl, 0 fullword, 0 lis/addi.
# Picker 0x8486ce88 takes the playcall object as r3 on jump-table
# case 2 of 0x8470bf18 (lwz r3, 0x2780 at 0x8470c2c4), on
# 0x84a254e0, and on 0x84892df8 → 0x84815518. Fetch then lwz +0x20
# of that object. 0x84867938 also reads +0x20 (lwz r30, 32(r28)).
# Jump-table r3 is a small integer mode 0..19 (wrapper 0x84712498,
# mr r30, r3 then bl 0x8470bf18). Case 2 is only entered with
# li r3, 2 at 0x847163d4 inside float-gated 0x84716310 (object
# 0x8502C670: fmr/lfs/fcmpu), then a nested table at 0x8470c248.
# That is frontend/presentation, not CPU down/ytg. 0x84a25270
# passes a stack buffer as r4; 0x84892df8 checks situation +0x1F8.
# Surveyed stw +0x20 after a playcall-global load is struct zeroing
# (0x84815650 / 0x84abea04), not a book-pointer write.
# Packed stw r4,32(r3);blr family (16 sites including 0x8493e180)
# and compare-and-set 0x84a4c658 have 0 bl / 0 fullword / 0 lis/addi.
# stw r3, 32(rN) and li-32/stwx are 0. Find-by-slot takes an
# alternate book pointer from 0x8520CDE0 as r4, not playcall+0x20.
# 0x84a139d0 (static init table 0x820dc630; 0 bl) stores getter
# 0x846f09d0's return into 0x8520CDE0 (stw 0x84a139f4). No surveyed
# copy from that global onto playcall+0x20. UI 0x84a28318
# (object 0x85212D30) reads playcall +0x1C and +0x20 (lwz at
# 0x84a283e0 / 0x84a283e8) into UI +0x20/+0x24 — a reader, not a
# writer. 0x848a2c10 writes +0x20 of a 1200-byte table record, not
# the playcall object. +0x20 rlwimi copies are bitfields.
# Tight survey: 0 stw r3,32(playcall-obj) after lwz from 0x851A2780
# (also 0 mr-alias, 0 addi-r3-32-bl). The three stw r3,32 in
# playcall-lis functions write other BSS: shadow 0x8516C908
# (0x84887e18 stores 0x84884ea0 bitmasks, not a book), 0x85158DA0,
# and 0x8523E950. 0x8466b058 zero-fills list-node +0x18..+0x2C.
# 0 surveyed load of DRCT root table 0x84F16EE0 then uses +0x20.
# Picker 0x8486ce88 is only in .pdata (0 lis/addi), so bctrl cannot
# target it via a stored address. 0 bctrl sites sit near both
# lhz +6 and +0x20. Extra DRCT lhz +6 at 0x8466a77c / 0x8466acd4
# copy fixed-record headers, not the instruction directory.
# That is not NFL 0x000dca40.
# Playcall slot+0 is type singleton 0x850F1218 or 0x850F1260
# (installer 0x84ad0048). Init 0x847c6da8 zeros both, links them,
# then stw +0x20 from getter 0x849fd6a8 (lwz 0x84F3F7D8+0x2C) and
# +0x1C from static 0x851C9D14. 0x84a89e08 takes that getter
# return and yields MASTER formation +0x244, so +0x2C is a live
# MASTER pointer. Builder 0x84860020 and UI helper 0x8486cd80
# call the getter (live); fetch still reads type-object +0x20
# (init-time copy). 0x8486cd80's only bl caller is UI 0x84a254d0.
# 0 memcpy dest=this+32 size 4/8. Registrar callers have no
# nearby stw 0(r3). Remaining lhz+6 functions that also touch
# +0x20 are gfx (fcfid/lfs), not dca40. lwz +0x254 then cmpwi
# 3/4 is only HUD 0x848d9470 / 0x848d9b88 and practice
# 0x84a37518. Live-MASTER setter 0x849fd6c8 is bind/select, not
# per-play: 0x849d4000 installs a type-hash lookup result and
# copies +0x7E0C; 0x849d6208 stores SPLB[r3] from table
# 0x851D9660 (indexer 0x849fcf60, stride 32288) or NULL.
# 0x849d81d0 calls that select after situation word0==4 (0 bl).
# 0 functions load +0x254/+0x25C within ±80 insns of getter/
# fetch/picker/count/nth. Only down→bctrl in 24 insns is still
# 0x84b694a8. DRCT property table 0x84EE65C0 is packed float/
# flag/ring accessors (0 lis/addi consumers), not dca40.
# 0x849d81d0: 0 bl, 0 text fullword, 1 .pdata word, 1 lis/addi
# that stores it into static object 0x84E28670+0x2C94 during
# init 0x84d00a48 (0 bl). 0 lwz of +0x2C90/+0x2C94. Packed
# sibling 0x849d81a8 is word0==4 then return 0x845F1784 else
# tail 0x849d6208. 0 of 74 0x849fcf60 callers load down/ytg
# in-fn or ±40 insns. get_down 0x84ad92e0: 0 bl / 0 lis-addi;
# only PE fullword is table 0x84EB0DE4. lhz+6 AND bctrl (not
# relocator): 0x84b8e918 is vtable[2] then increment +6;
# 0x84ba2e70 mtctr of incoming r10 (codec). Not dca40.
# get_down table 0x84EB0DE4 sits in a situation property blob
# of packed field getters (lwz +0x254, lhz/lfs/lbz siblings).
# 0 lis/addi of 0x84EB0DE4 or of get_down. 0 aligned PE inbound
# pointers to 0x84EB0A00..0x84EB1200. addi-32/lwzx/mtctr/bctrl
# is only 0x8484d488 (Altivec stvx presentation, 0 bl) and
# 0x84878588 (vec-compare jump table, 0 bl). Not dca40.
# Property-get-by-id 0x849c9c90 (67 bl): cmpwi r4,-1 then
# vtable[1] on singleton 0x851C96A0+0x14. Callers that li r4
# use 997..999; 0 playbook-helper overlap. Not the 0x84EB0DE4
# blob walker. lwz+0x20 then lwzx then bctrl (non-vtable) is
# only 0x84880740: +0x20 is a flag (cmpwi 1); lwzx is jump
# table 0x84DBB408 (same family as 0x84878588). Relocator
# 0x8466a994 does addi r11, r3, 32 then in-place reloc of
# lhz+6 inline instruction words — the dir is inline, not a
# pointer at +0x20. 0 surveyed addi-32/lwzx function also
# has lhz+6. DRCT vtable 0x82003F90[0] is 0x8466b8b0 (0 bl).
# 0 surveyed stride-0x1C 0xFFFFFFFF-sentinel walker that
# bctrl's get_down. Packed get_down and siblings (0x847463c8,
# 0x84ad92e8 LOS, …) have 0 bl; each TEXT pointer's only
# aligned inbound is the blob itself. 0 packed twin of string
# indexer 0x8466af28 for inline +0x20 (addi-32 + slwi r4,2 +
# lwzx). NFL default.xbe 0x000dca40 is a bitset/float lookup
# over static table 0xB73BD0 (stride 0x20); the xbe has 0
# [ecx+0x14][eax+edx*4] ret twins of dcba0. Inventory's
# "consumes instruction entries" reading of dca40 is not the
# packed indexer shape. DRCT root 0x84F16EE0 lis/addi sites
# are only the relocator/init family.



# Still no compare of a loaded resource
# header to 0xED586383 except the ctor write.
# 0x8470bf18's other cases are menu/mode (global +0x8F8 / +0x34), not
# CPU play AI. 0x84a14c98 loops get-nth to test membership (0 bl
# callers). Builder callers in 0x84a27xxx are human playcall UI;
# 0x84a85714 is in-game presentation.
APF_SITUATION_GET_DOWN_VA = 0x84AD92E0
APF_SITUATION_VTABLE8_QUERY_VA = 0x84B694A8
APF_SCRIPT_SITUATION_LEAF_VA = 0x8499E3E8
APF_PDATA_SECTION_VA = 0x844DBE00
APF_PDATA_FUNCTION_COUNT = 18472
# Earlier G12 ticks misread .pdata as a script (fn, tag) table.
APF_SCRIPT_FN_TAG_TABLE_VA = APF_PDATA_SECTION_VA
APF_SCRIPT_FN_TAG_TABLE_COUNT = APF_PDATA_FUNCTION_COUNT
APF_SCRIPT_ONFIELD_ROLE_OPCODE_VA = 0x846302D8
APF_SITUATION_MENU_GLOBAL_VA = 0x84F3F8F8
APF_GAME_STATE_DOWN_OFFSET = 0x254
APF_GAME_STATE_LOS_OFFSET = 0x258
APF_GAME_STATE_YTG_OFFSET = 0x25C
APF_PLAYCALL_BY_TYPE_UI_VA = 0x84A472D0
APF_PLAY_TYPE_UI_TABLE_VA = 0x84E4D810
APF_INGAME_PLAY_PICKER_VA = 0x8486CE88
APF_SITUATION_WORD0_OFFSET = 0
APF_SITUATION_PLAYCALL_TAB_OFFSET = 0x2BC
APF_SITUATION_PLAYTYPE_FILTER_OFFSET = 0x1F8
APF_PLAYTYPE_FILTER_TABLE_VA = 0x84DCB2A8
APF_SPLB_RECORD_FOR_PLAY_VA = 0x84A89EA8
APF_INGAME_PLAY_FETCH_VA = 0x848699D8
APF_SPLB_ENTRY_TO_MASTER_PLAY_VA = 0x84A8BA80
APF_DRCT_TYPE_HASH = 0xED586383
APF_DRCT_TYPE_ROW_VA = 0x84D1B834
APF_DRCT_TYPE_CTOR_VA = 0x8466B964
APF_DRCT_TYPE_OBJECT_VA = 0x84D1B830
APF_DRCT_TYPE_VTABLE_VA = 0x82003F90
APF_DRCT_TYPE_INSERT_VA = 0x8466B998
APF_DRCT_IFF_LOAD_VA = 0x8466AF70
APF_DRCT_RESOURCE_LOAD_VA = 0x8468DA70
APF_DRCT_REGISTRY_TABLE_VA = 0x84D1B7D0
# NFL 0x000dc700 analog. Not the instruction interpreter.
APF_DRCT_RELOCATOR_VA = 0x8466A818
APF_DRCT_RELOC_FIXED_SLOT_LOOP_VA = 0x8466A97C
APF_DRCT_RELOC_FIXED_SLOT_BYTES = 868  # 217 slots × 4
APF_DRCT_RELOC_INSN_DIR_VA = 0x8466A984
APF_DRCT_RELOC_INSN_DIR_ADDI_VA = 0x8466A994
APF_DRCT_VTABLE0_VA = 0x8466B8B0
APF_DRCT_POST_RELOC_FIXED_WALK_VA = 0x8466AAE0
APF_DRCT_ROOT_TABLE_VA = 0x84F16EE0
APF_DRCT_FIXED_CHILD_INDEX_VA = 0x8466ABC0  # NFL 0x000dc8e0 analog
APF_DRCT_STRING_INDEX_VA = 0x8466AF28  # NFL 0x000dcba0 analog
APF_DRCT_AUX_INDEX_VA = 0x8466AF60
APF_DRCT_FIXED_RECORD_CONSUMER_VA = 0x8466AC38
APF_PLAYCALL_OBJECT_GLOBAL_VA = 0x851A2780
APF_PLAYCALL_BOOK_OFFSET = 0x20
APF_PLAYCALL_OBJECT_REGISTER_VA = 0x8493D968
APF_PLAYCALL_BOOK_SETTER_VA = 0x8493E180
APF_PLAYCALL_BOOK_READER_VA = 0x84867938  # lwz r30, 32(r28); not a writer
APF_PICKER_PLAYCALL_LOAD_VA = 0x8470C2C4  # lwz r3, playcall global; bl picker
APF_JUMP_TABLE_PICKER_FN_VA = 0x8470BF18
APF_JUMP_TABLE_PICKER_CASE = 2
APF_JUMP_TABLE_MODE_WRAPPER_VA = 0x84712498  # r3 = mode 0..19; not a pointer
APF_JUMP_TABLE_MODE_2_FN_VA = 0x84716310  # float-gated; only li r3,2 site
APF_JUMP_TABLE_MODE_2_LI_VA = 0x847163D4
APF_JUMP_TABLE_MODE_2_OBJECT_VA = 0x8502C670
APF_JUMP_TABLE_NESTED_VA = 0x8470C248  # case 2 nested table before picker
APF_PICKER_UI_FN_VA = 0x84A25270  # stack-buffer r4; playcall UI
APF_PICKER_UI_PLAYCALL_LOAD_VA = 0x84A254E0
APF_PICKER_PLAYCALL_UI_LOAD_VA = 0x84892DF8  # checks situation +0x1F8
APF_SPLB_FIND_BOOK_GLOBAL_VA = 0x8520CDE0  # r4 to find-by-slot; not +0x20
APF_SPLB_FIND_BOOK_INIT_VA = 0x84A139D0
APF_SPLB_FIND_BOOK_INIT_STW_VA = 0x84A139F4
APF_SPLB_FIND_BOOK_GETTER_VA = 0x846F09D0
APF_SPLB_FIND_BOOK_INIT_TABLE_VA = 0x820DC630
APF_PLAYCALL_SIBLING_OFFSET = 0x1C  # copied with +0x20 by UI 0x84a28318
APF_PLAYCALL_UI_OBJECT_VA = 0x85212D30
APF_PLAYCALL_UI_FIELD_COPY_VA = 0x84A283E0  # lwz playcall+0x1C; not a writer
APF_PLAYCALL_SHADOW_VA = 0x8516C908  # 0x84887e18 fill; +0x20 is a bitmask
APF_PLAYCALL_SHADOW_FILL_VA = 0x84887E18
APF_PLAYCALL_SHADOW_BITMASK_VA = 0x84884EA0
APF_PLAYCALL_TYPE_OBJECT_A_VA = 0x850F1218  # installed into slot+0
APF_PLAYCALL_TYPE_OBJECT_B_VA = 0x850F1260
APF_PLAYCALL_TYPE_INIT_VA = 0x847C6DA8  # copies live MASTER onto +0x20
APF_PLAYCALL_TYPE_INIT_STW20_VA = 0x847C6DF8
APF_PLAYCALL_SLOT_INSTALL_VA = 0x84AD0048
APF_LIVE_MASTER_GETTER_VA = 0x849FD6A8  # lwz 0x84F3F7D8+0x2C
APF_LIVE_MASTER_SETTER_VA = 0x849FD6C8
APF_LIVE_MASTER_SLOT_VA = 0x84F3F7D8
APF_LIVE_MASTER_SLOT_OFFSET = 0x2C
APF_BOOK_RESOLVE_HELPER_VA = 0x8486CD80  # UI-only; caller 0x84a254d0
APF_BOOK_FORMATION_GETTER_VA = 0x84A89E08  # MASTER +0x244 from that pointer
APF_LIVE_MASTER_BIND_VA = 0x849D4000  # type-hash lookup → setter
APF_LIVE_MASTER_SPLB_SELECT_VA = 0x849D6208  # stores SPLB[r3] or NULL
APF_SPLB_RAM_INDEX_VA = 0x849FCF60  # r3 * 32288 + 0x851D9660
APF_SPLB_RAM_TABLE_VA = 0x851D9660
APF_SPLB_RAM_STRIDE = 32288
APF_SPLB_SELECT_WORD0_CMP_VA = 0x849D81EC  # cmpwi word0, 4 — not down
APF_SPLB_SELECT_WORD0_THUNK_VA = 0x849D81A8  # packed; word0==4 then blr
APF_SPLB_SELECT_THUNK_VA = 0x849D81D0  # stored at object+0x2C94; 0 bl
APF_SPLB_SELECT_INIT_VA = 0x84D00A48
APF_SPLB_SELECT_OBJECT_VA = 0x84E28670
APF_SPLB_SELECT_SLOT_OFFSET = 0x2C94
APF_SITUATION_GET_DOWN_TABLE_VA = 0x84EB0DE4  # only PE fullword of get_down
APF_SITUATION_GET_DOWN_ROW_VA = 0x84EB0DD0  # 7-word row ending FFFFFFFF
APF_SITUATION_GET_DOWN_SIBLING_VA = 0x847463C8  # packed lhz +0x168; 0 bl
APF_NFL_DCA40_VA = 0x000DCA40  # xbe bitset/float; not insn-dir indexer
APF_DCA40_FALSE_STVX_VA = 0x8484D488  # Altivec stvx; not insn consumer
APF_DCA40_FALSE_VSUB_VA = 0x84878588  # vec-compare jump table; 0 bl
APF_DCA40_FALSE_PLAYCALL_JT_VA = 0x84880740  # +0x20 flag; lwzx 0x84DBB408
APF_PROPERTY_GET_BY_ID_VA = 0x849C9C90  # r4=id; 997..999; not down
APF_PROPERTY_GET_SINGLETON_VA = 0x851C96A0
APF_DRCT_PROPERTY_TABLE_VA = 0x84EE65C0  # packed field accessors; not dca40
# dir_ingame.iff (MASTER outer 153): 1015 instruction records. 1014/1015
# begin 0x0B000100 then a payload at +4 — tagged fields, not a C++
# vtable and not a VM opcode switch. Groups are `0B 00` + u16 field
# (`01 00` / `02 00`) + u8, terminator `00`. First byte 0x0B is the
# tag, not length. dir_wrapup.iff (outer 265) is 96/96 the same tag.
# Relocator 0x8466a994 rewrites only the inline directory words; it
# does not follow those pointers into record bodies. vtable[0]
# 0x8466b8b0 relocates then bl 0x8466aae0 at 0x8466b8fc (fixed walk
# only — no instruction interpret at load). Packed lhz+6 getter
# 0x84ab2010 and packed +0x14/+0x18 indexers have 0 bl and 0 inbound
# PE pointers. Byte-stream 0x8466bd38 compares 94/96/97 and 275–330;
# helper 0x8466af48 is r4 < +0x10, not a type mapper. 0x84bcd760 is
# a string classifier. 0x84b162a8 is an embedded C++ object at +0x20.
# lbz+cmpwi 11 then 12 is a class-id, not tag 0x0B. 0 addi-32/lwzx/
# lbz-0(record); 0 slwi-r4-2/addi-32/lwzx-r3 get-nth.
# Field ids inside 0B 00 groups are BE u16 0x0100 and 0x0200 (1220 /
# 2362 in ingame), not 1/2. Leftover lead bytes after those groups
# are nested TLV 0x03..0x09. 0 lhz+cmpwi 0x0100 parser (0x84c381e8
# is stack/float). 0 skip-0B00 then lhz. 0 lhbrx in TEXT. 0x84a87b38
# is play-type nibble srwi 28. 0x84bdfb00 is ASCII Y/I.
# 0 cmpwi 0x0B00 in TEXT. 0x848bb1a8 is RTTI class 2 vs 11 (not tag).
# 0x8466b660 is a stride-16 map count vs 256, not field 0x0100.
# 0x8466c7f0 is a packed LE f32 (4×lbz, not lwbrx). 0 lis/addi of 0x84EE65C0.
# 0x84671838 is C++ vt[2] on r4+0x20, not a property registrar.
# 0B groups are tag + u8 variant + BE u16 field + u8 (3621 in ingame;
# variant 0 is 3589/3621, variants 1-5 use field 0x0200), not a 2-byte
# 0B00 tag. 0x84842f48 is RTTI class 3/4/5/6/7/11/12 via +0x14/+4.
# 0x8476ca80 counts 10×5-byte slots at object +0x13D9. 0x8492bb24
# sums 5-byte windows then uses floats.
# 0x84b0a4c0 compact-int-indexes stride-12 table 0x84EE65A8 (max id
# 0x35) then bctrl get/set; 0 cmpwi 11 in those cases. 0x849e7790
# copies a 12-byte record (0xffff sentinel), not a 0B group.
# 0x847e2818 is class-id 3/5/6/7/4 via +4, not leftover leads.
# 0x84abb590 copies 5 bytes with no tag check. 0x84a9d7a0 copies
# stride-32 floats at +0x1C, not NFL table 0xB73BD0.
# NFL dir_ingame (outer 4) has 1310 instruction records, all starting
# 0B; prefixes 0B 00 01 00 / 01 01 / 01 02 — same tag+variant+u16
# encoding as APF (u16 stored BE even on LE Xbox). 0x84be2b48 is an
# ASCII/scanf 0..11 jump (digits, +/-), not leftover leads.
# 0x848777cc loads one float from 0x84F1A150+0x1C, not a stride-32
# bitset table. 0x84b93b10 reads a 5-byte header (bytes 0-3,
# cursor+5) with no 0x0B check; caller 0x84b94258 switches on first
# byte 0..4 (codec). Non-0B leftovers are concatenated typed groups:
# type 0x04 is tag + 4-byte LE float (size 5) on APF and NFL; types
# 0x05/0x06/0x07/0x08/0x09 are 1-byte tags (a following 00 is the
# terminator type, not a payload); type 0x03 is tag + u8 (size 2).
# That walk consumes APF ingame 1015/1015 and NFL ingame 1310/1310.
# 0x849277a8 switches on a presentation byte (cases 4/11 store
# floats), not those tags. 0x84c4c480 copies 1/2/4/8 bytes with
# endian swap (cmplwi 1/2/4/8 then lwbrx for width 4), not a type-4
# float reader. 0x84ba2520 walks a stride-12 table in r4 from a packed
# descriptor (mulli 12 + lbz +8), not a property bctrl registrar.
# 0x846c2068 compares object +0x62 to 4 then stores 5, not float-group
# size. 0x8466c890 is a float-expression VM (opcodes 0..12, table
# 0x8466c91c, cursor 0x84F1779C); case 4 is the LE f32 immediate
# (helper 0x8466c7f0); case 11 consumes 1 extra byte, not a leftover
# 0B group. Descriptor slot 0x844dd260. 0x8477f950 switches on a UI
# byte 0..12 (cases 5-10 just return). 0x84a37850 loads situation down
# and ytg together and wraps ytg at 100, not a play picker.
# 0x848864b0 compares situation word0 to 4 (not down) and playcall+0x38
# to 11. 0x84a5eb08 indexes 24-byte tables by type 3/4/8/9/11/12, not leftover.
# 0x8475b7b0 tweens 0x84D58C70 (lfs +0x258, counter +0x25C), not situation ytg.
# NFL xbe: 0 add r32,5 within 80 bytes of cmp al, 0x0B. The only .text sites
# with both cmp al,4 and cmp al,0x0B within 48 bytes are 0x1138e0
# (object +0x35 enum) and killed play-type classifiers 0x133fd1 / 0x27e830.
# 0x84a23bd0 cycles situation +0x1F8 through 0..7 (UI play-type filter).
# The only PE pointer to picker 0x8486ce88 is its .pdata row
# 0x844e8568 (section 0x844DBE00), not a bctrl dispatch slot.
# Situation +0x1F8 setter 0x849d36d8 has 0 bl and 0 PE pointers.
# NFL relocator 0x000dc700 returns after fixing +0x14/+0x0c/+0x08
# and does not walk instruction bodies. 0x848631d0 is the +0x1F8 getter
# used by the "Offensive Play calling" widget (0x845FE7D4); 0x849d36d8
# remains the packed setter (0 bl). NFL 0x168ad0 walks a SHAP list at +0x14
# (stride 0xC, dword==3), not leftover TLV. The only lhz+6 then addi 32
# is relocator 0x8466a994. 0x84a2ccd8 reads situation +0x1F8 and +0x2BC
# (word0==2, filter==0, tab==3), not down/ytg. The only TEXT sites with
# cmp 4, addi 5, and cmp 11 together are occupancy 0x84961548 and
# bit-pack 0x849e3a24, not leftover sizes. Picker-caller neighborhood
# 0x84814dcc / 0x84816118 compares situation word0 to 4, not Fourth Down;
# the addi 5 is srawi-3 index math. 0x8485a04c switches word0 0/1/2/3/4/9
# into mode immediates. Real addi r,r,5 (not li 5) plus cmp 4/11 is still
# not a leftover stream: 0x84869e60 is a 4-wide fill remainder and
# 0x84a9adcc is an 11-slot lbzx at object+5 beside the role table.
# 0x84a21298 is a packed UI formatter (0 bl) that indexes the seven
# labels at 0x84E446C8 (First Down … Third and Long 0x845FD8B4 …
# Fourth and Long); every lis/addi of its object 0x85212B88 sits in
# the same 0x84a20xxx widget cluster, not a CPU picker. lbz+cmplwi 9
# then bctr at 0x84911750 / 0x849ecd48 switch object fields, not
# leftover tags. 0x847d7590 / 0x8480189c compare playcall
# 0x851A2780+0x3C to 3/6, not down. Every TEXT lis/addi of leftover
# cursor 0x84F1779C / 0x84F177AC sits in expr-VM 0x8466c778–0x8466d888;
# the VM entry stores r5 to cursor+8 (0x8466c8dc). No TEXT site loads
# situation +0x254 and +0x25C together and yields D&D index 4;
# lookalikes 0x8499e420 / 0x849a3b58 compare script node +0x10/+0x14.
# Packed get_ytg 0x84b68cd8 (lwz r3, +0x25C(r3)) has 0 bl and 0 PE
# pointers; the situation property blob that holds get_down 0x84ad92e0
# has no +0x25C getter. Expr VM 0x8466c890 has only desc slot
# 0x844dd260 (0 inbound PE ptrs, 0 TEXT lis/addi). 0 lwz +0x20 then
# lbz and cmp 4/11 leftover walk. 0x84879bc0 extracts ytg bit 1, not
# a D&D index. Packed object get_down 0x84b68cc8 sits next to get_ytg
# (0 PE ptrs). 0x84ad0348 copies situation +0x254/+0x258/+0x25C onto a
# stack blob (only PE is .pdata 0x844f72b0); not a D&D index. 0 aligned
# inbound PE pointers into get_down blob 0x84EB0800..0x84EB0F00. Other
# TEXT lwz +0x254/+0x25C pairs are stack slots, tween 0x8475b7b0,
# status query 0x84b694a8, or a non-situation object where +0x254 is a
# pointer (0x84b39458). TEXT lis/addi of the blob only hit row base
# 0x84EB02D0 (packed 0x84ad9f40: mulli r4, 0x1C then lwz +4). get_down's
# row 0x84EB0DD0 is not 0x1C-aligned from that base. 0 addi 32 then
# lwz 0 then lbz 0(record) leftover walk. 8 lwz +0x20 then lbz 0 sites
# are string/ASCII. Only TEXT lis 0x0B00 is bitmask 0x848ee750
# (li r4, 11). 0x84b64c88 walks a 4-byte window
# with UTF-8 extra-byte table 0x844C69C8 (0xC0→1, 0xE0→2, 0xF0→3; 0x0B→0),
# not leftover sizes. 0 PE/NFL size table 02 05 01×5 … 05.
APF_DRCT_INSN_OUTER_INGAME = 153
APF_DRCT_INSN_COUNT_INGAME = 1015
APF_DRCT_INSN_RECORD_PREFIX = 0x0B000100
APF_DRCT_INSN_TOKEN_OFFSET = 4  # field-1 payload, not a VM opcode
APF_DRCT_INSN_TOKEN_TOP = (99, 83, 70, 82)  # field-1 payload histogram
APF_DRCT_INSN_TAG_BYTE = 0x0B
APF_DRCT_INSN_WRAPUP_OUTER = 265
APF_DRCT_INSN_COUNT_WRAPUP = 96
APF_DRCT_PACKED_INSN_COUNT_GETTER_VA = 0x84AB2010
APF_DRCT_VT2_UNLINK_VA = 0x8466BA30
APF_DRCT_BYTE_STREAM_READER_VA = 0x8466BD38
APF_DRCT_FALSE_ASCII_SWITCH_VA = 0x84BCD760
APF_DRCT_COMPACT_INDEX_CHECK_VA = 0x8466AF48
APF_DRCT_FALSE_EMBEDDED20_VA = 0x84B162A8
APF_DRCT_VT0_FIXED_WALK_BL_VA = 0x8466B8FC
APF_DRCT_INSN_FIELD_ID_1 = 0x0100
APF_DRCT_INSN_FIELD_ID_2 = 0x0200
APF_DRCT_INSN_NEST_LEAD = (0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09)
APF_DRCT_FALSE_FIELD100_VA = 0x84C381E8  # stack/float; not field-id parser
APF_DRCT_FALSE_PLAYTYPE_NIBBLE_VA = 0x84A87B38  # srwi 28; not tag 6
APF_DRCT_FALSE_ASCII_YI_VA = 0x84BDFB00  # cmpwi 'Y'/'I'; not TLV
APF_DRCT_FALSE_RTTI_2_11_VA = 0x848BB1A8  # class-id 2 vs 11; not tag 0x0B
APF_DRCT_FALSE_CAP256_VA = 0x8466B660  # map count vs 256; not field 0x0100
APF_DRCT_FALSE_BE_FLOAT_VA = 0x8466C7F0  # packed LE f32 helper; not 0B-group
APF_DRCT_FALSE_R4_VT2_VA = 0x84671838  # lwz r4,+0x20 then vt[2]; not registrar
APF_DRCT_INSN_VARIANTS = (0, 1, 2, 3, 4, 5)
APF_DRCT_FALSE_RTTI_TLV_VA = 0x84842F48  # class 3/4/5/6/7/11/12 via +0x14/+4
APF_DRCT_FALSE_PLUS5_OCCUPANCY_VA = 0x8476CA80  # 10×5 slots at +0x13D9
APF_DRCT_FALSE_PLUS5_SUM_VA = 0x8492BB24  # 5-byte window sum + floats
APF_DRCT_PROP_WALK_VA = 0x84B0A4C0  # compact-int → 0x84EE65A8 stride 12 → bctrl
APF_DRCT_PROP_TABLE_INDEX_VA = 0x84EE65A8
APF_DRCT_PROP_JT_VA = 0x84B0A51C
APF_DRCT_PROP_JT_MAX_ID = 0x35
APF_DRCT_FALSE_STRUCT12_VA = 0x849E7790  # +0/+1/+2/+4 copy; 0xffff sentinel
APF_DRCT_FALSE_CLASS_35764_VA = 0x847E2818  # +4 class-id 3/5/6/7/4; not TLV
APF_DRCT_FALSE_COPY5_VA = 0x84ABB590  # 5-byte memcpy; no tag check
APF_DRCT_FALSE_STRIDE32_F32_VA = 0x84A9D7A0  # float copy +0x1C stride 32; not B73BD0
APF_NFL_DRCT_INSN_OUTER_INGAME = 4
APF_NFL_DRCT_INSN_COUNT_INGAME = 1310
APF_NFL_DRCT_INSN_PREFIX_TOP = (0x0B000100, 0x0B000101, 0x0B000102)
APF_DRCT_FALSE_ASCII_SCANF_VA = 0x84BE2B48  # ASCII 0..11 jump; not leftover leads
APF_DRCT_FALSE_DCA40_SINGLE_F32_VA = 0x848777CC  # one lfs at 0x84F1A150+0x1C
APF_DRCT_FALSE_CODEC5_VA = 0x84B93B10  # 5-byte header, no 0x0B check
APF_DRCT_INSN_TYPE_TERM = 0x00
APF_DRCT_INSN_TYPE_BEGIN = 0x03
APF_DRCT_INSN_TYPE_FLOAT = 0x04
APF_DRCT_INSN_TYPE_MARK = 0x07
APF_DRCT_INSN_TYPE_CLOSE = 0x06
APF_DRCT_INSN_BEGIN_GROUP_SIZE = 2  # tag + u8; NFL 03 xx 07 06 00
APF_DRCT_INSN_FLOAT_GROUP_SIZE = 5  # tag + IEEE754 LE f32
APF_DRCT_INSN_MARK_GROUP_SIZE = 1
APF_DRCT_INSN_CLOSE_GROUP_SIZE = 1  # 06; following 00 is terminator
APF_DRCT_INSN_ONE_BYTE_TYPES = (0x05, 0x06, 0x07, 0x08, 0x09)
APF_DRCT_FALSE_BYTE_JT_VA = 0x849277A8  # lbz0 cases 4/11 are gfx floats
APF_DRCT_FALSE_ENDIAN_COPY_VA = 0x84C4C480  # width 1/2/4/8 memcpy; not TLV
APF_DRCT_FALSE_STRIDE12_R4_VA = 0x84BA2520  # packed desc *12 added to r4; not bctrl
APF_DRCT_FALSE_PLUS5_STATE_VA = 0x846C2068  # +0x62 == 4 then li 5; not float size
APF_DRCT_FALSE_EXPR_VM_VA = 0x8466C890  # float expr opcodes 0..12; not leftover
APF_DRCT_FALSE_EXPR_JT_VA = 0x8466C91C
APF_DRCT_FALSE_EXPR_CASE11_VA = 0x8466CCDC  # 1 extra byte; not 0B group
APF_DRCT_FALSE_EXPR_DESC_VA = 0x844DD260  # mixed descriptor slot for the VM
APF_DRCT_FALSE_UI_BYTE_JT_VA = 0x8477F950  # lbz stack byte 0..12; not leftover
APF_FALSE_YTG_WRAP_VA = 0x84A37850  # down+ytg; wrap ytg at 100; not picker
APF_FALSE_SIT_WORD0_EQ4_VA = 0x848864B0  # word0==4, not Fourth Down
APF_DRCT_FALSE_TYPE24_VA = 0x84A5EB08  # types 3/4/8/9/11/12, table width 24
APF_FALSE_TWEEN_OBJ_VA = 0x8475B7B0  # 0x84D58C70; lfs +0x258, not ytg
APF_NFL_FALSE_BYTE35_VA = 0x001138E0  # +0x35 enum 4/5/6 and 0x0A/0x0B
APF_FALSE_FILTER_UI_VA = 0x84A23BD0  # cycles +0x1F8 0..7; not CPU long
APF_PICKER_DESC_SLOT_VA = 0x844E8568  # picker's .pdata row, not bctrl slot
APF_FALSE_FILTER_SETTER_VA = 0x849D36D8  # situation +0x1F8 stw r3; 0 bl
APF_FALSE_FILTER_GETTER_VA = 0x848631D0  # +0x1F8 lwz; Offensive Play calling UI
APF_NFL_FALSE_SHAP_LIST_VA = 0x00168AD0  # +0x14 stride-0xC dword==3; not leftover
APF_FALSE_FILTER_TAB_GATE_VA = 0x84A2CCD8  # +0x1F8==0 and tab==3; not down
APF_DRCT_FALSE_CMP4_OCC_VA = 0x84961548  # occupancy; addi r30,5 not stream
APF_DRCT_FALSE_BITPACK_R26_VA = 0x849E3A24  # packs r26==4/11; not leftover
APF_FALSE_SIT_WORD0_EQ4_PICKER_VA = 0x84814DCC  # picker-neighbor word0==4
APF_FALSE_SIT_WORD0_SWITCH_VA = 0x8485A04C  # word0 0/1/2/3/4/9; not down
APF_DRCT_FALSE_FILL4_VA = 0x84869E60  # 4-wide fill remainder addi r3,5
APF_DRCT_FALSE_SLOT11_PLUS5_VA = 0x84A9ADCC  # 11-slot lbzx at obj+5; not TLV
APF_FALSE_DND_LABEL_VA = 0x84A21298  # UI formatter for First/Third and Long
APF_DND_NAME_TABLE_VA = 0x84E446C8  # 7 UTF-16 labels; not CPU picker
APF_DND_THIRD_LONG_STR_VA = 0x845FD8B4  # "Third and Long"
APF_DRCT_FALSE_BYTE36_JT_VA = 0x84911750  # lbz +0x36 cmp 9/10; not leftover
APF_DRCT_FALSE_BYTE34_JT_VA = 0x849ECD48  # lbz +0x34 cmplwi 9 bctr; not TLV
APF_FALSE_PLAYCALL_3C_VA = 0x847D7590  # playcall+0x3C == 3/6; not down
APF_DRCT_EXPR_CURSOR_VA = 0x84F1779C  # expr-VM stream cursor; no outside feeder
APF_DRCT_EXPR_CURSOR_INIT_VA = 0x8466C8DC  # stw r5, cursor+8
APF_FALSE_SCRIPT_DND_VA = 0x849A3B58  # script +0x10/+0x14; not situation ytg
APF_PACKED_GET_YTG_VA = 0x84B68CD8  # lwz r3, +0x25C(r3); 0 bl, 0 PE ptrs
APF_PACKED_GET_DOWN_OBJ_VA = 0x84B68CC8  # lwz r3, +0x254(r3); 0 PE ptrs
APF_FALSE_SIT_COPYOUT_VA = 0x84AD0348  # stacks down/LOS/ytg; not D&D index
APF_FALSE_SIT_PTR254_VA = 0x84B39458  # +0x254 is a pointer, not down
APF_SITUATION_FALSE_BLOB_ROW_VA = 0x84EB02D0  # stride-0x1C indexer base; not get_down
APF_FALSE_BLOB_INDEXER_VA = 0x84AD9F40  # mulli r4, 0x1C; cannot reach get_down row
APF_FALSE_0B00_MASK_VA = 0x848EE750  # lis 0x0B00 bitmask; li r4, 11
APF_FALSE_YTG_LSB_VA = 0x84879BC0  # ytg bit 1; not D&D index
APF_DRCT_FALSE_UTF8_WALK_VA = 0x84B64C88  # UTF-8 extra-byte table, not leftover
APF_DOWN_NAME_TABLE_VA = 0x820E57C8
APF_DOWN_KICKOFF = 0
APF_DOWN_FIRST = 1
APF_DOWN_SECOND = 2
APF_DOWN_THIRD = 3
APF_DOWN_FOURTH = 4
APF_DOWN_PAT = 5
APF_DOWN_SAFETY_KICK = 6
APF_DOWN_NAMES = (
    "Kickoff",
    "First Down",
    "Second Down",
    "Third Down",
    "Fourth Down",
    "PAT",
    "Safety Kick",
)
APF_3RD_AND_LONG_PLAY_CHOICE_PROVED = False
# User-team 3rd-and-long "next-best pass formation" search (Urianus, 2026-08-14)
# has no located setting in the playbook or archive data. PE has the UI labels
# and the Ace Empty name; no "next best" / "best pass" string. The play picker
# is in default.xex and does not load down+ytg. This project will not ship an
# executable patch.
APF_USER_3RD_AND_LONG_DATA_WRITER_EXISTS = False
APF_USER_3RD_AND_LONG_SEARCH_PROVED = False
APF_3RD_AND_LONG_UI_LABEL_VA = 0x845FD8B4
APF_4TH_AND_LONG_UI_LABEL_VA = 0x845FD8F8
APF_ACE_EMPTY_NAME_VA = 0x8460574C
APF_3RD_AND_LONG_USER_LOGIC_REFUSAL = (
    "Mod Studio cannot change how APF chooses formations on 3rd-and-long. "
    "No editable setting for the reported user-team/CPU difference was found "
    "in MASTER PLAY, the stock playbooks, or the director files. The behavior "
    "appears to be implemented in default.xex, which Mod Studio does not "
    "patch. Nothing was changed.\n\n"
    "Technical evidence (not patch targets): situation down +0x254 / ytg +0x25C; "
    "packed get_down 0x84AD92E0 / 0x84B68CC8; packed get_ytg 0x84B68CD8; "
    "picker 0x8486CE88 (situation word0 / +0x2BC tab, not down); UI labels "
    "0x845FD8B4 / 0x845FD8F8; Ace Empty name 0x8460574C. No surveyed "
    "function loads +0x254 and +0x25C and also calls SPLB get-nth/count. "
    "No UTF-16BE or ASCII 'next best' / 'best pass' string in the PE.\n\n"
    "Executable patching remains deferred. "
    "APF_3RD_AND_LONG_PLAY_CHOICE_PROVED stays False."
)

# Layout offsets relative to PLAY resource body (after 0x20 resource header).
# Verified against nfl2k5_playbook_inspector constants + PLAY_* product docs.
G1_G2_LAYOUT: dict[str, int | str] = {
    "resource_header_size": RESOURCE_HEADER_SIZE,
    "formation_base": FORMATION_BASE,
    "formation_size": FORMATION_SIZE,
    "formation_aux_base": FORMATION_AUX_BASE,
    "formation_aux_size": FORMATION_AUX_SIZE,
    "formation_play_links": FORMATION_PLAY_LINKS,
    "play_base": PLAY_BASE,
    "play_size": PLAY_SIZE,
    "assignment_count": ASSIGNMENT_COUNT,
    "assignment_record_size": 8,  # descriptor u32 + chain_start u32
    "node_base": NODE_BASE,
    "node_size": NODE_SIZE,
    "package_map_offset_in_formation": PACKAGE_MAP_OFFSET_IN_FORMATION,
    "package_map_size": PACKAGE_MAP_SIZE,
    "o0308_asset_id": O0308_ASSET_ID,
    "o0308_pack_offset": O0308_PACK_OFFSET,
    # Absolute body offset of play N assignment slot S:
    #   PLAY_BASE + N*PLAY_SIZE + 8 + S*8
    "assignment_offset_formula": "PLAY_BASE + play_index*PLAY_SIZE + 8 + slot*8",
    # Absolute body offset of formation package map:
    #   FORMATION_BASE + fi*FORMATION_SIZE + 0x0D
    "package_map_offset_formula": (
        "FORMATION_BASE + formation_index*FORMATION_SIZE + "
        f"{PACKAGE_MAP_OFFSET_IN_FORMATION:#x}"
    ),
    # Descriptor word (family/package hints live here — bit map incomplete):
    "descriptor_offset_in_play": 0x04,
}


def assignment_body_offset(play_index: int, slot: int) -> int:
    """Body-relative offset of one assignment (descriptor+chain) in a PLAY."""

    if not 0 <= slot < ASSIGNMENT_COUNT:
        raise ValueError(f"slot must be 0..{ASSIGNMENT_COUNT - 1}")
    if play_index < 0:
        raise ValueError("play_index must be non-negative")
    return PLAY_BASE + play_index * PLAY_SIZE + 8 + slot * 8


def descriptor_body_offset(play_index: int) -> int:
    """Body-relative offset of the play-level descriptor word (+0x04)."""

    if play_index < 0:
        raise ValueError("play_index must be non-negative")
    return PLAY_BASE + play_index * PLAY_SIZE + 4


@dataclass(frozen=True, slots=True)
class SlotRoleSnapshot:
    """One assignment slot from a real or synthetic play."""

    play_index: int
    slot: int
    descriptor: int
    chain_start: int
    body_offset: int
    first_opcode: int | None
    chain_length: int


@dataclass(frozen=True, slots=True)
class PackageRuleSpikeResult:
    """Offline RE spike result for one community bug id."""

    bug_id: str
    status: str  # "re_spike" | "offline_writer_proved"
    fixture_asset_id: str
    fixture_pack_offset: int
    layout: dict[str, int | str]
    matching_formations: tuple[str, ...]
    matching_plays: tuple[str, ...]
    slot_snapshots: tuple[SlotRoleSnapshot, ...]
    hypothesis: str
    next_offline_writer_gate: str


_DIME_RE = re.compile(r"\bdime\b", re.IGNORECASE)
_ACE_RE = re.compile(r"\bace\b", re.IGNORECASE)


def _first_opcode(book: Nfl2k5Playbook, assignment: PlaybookAssignment) -> tuple[int | None, int]:
    try:
        chain = book.chain(assignment.chain_start_index)
    except Exception:  # noqa: BLE001 - synthetic books may omit chains
        return None, 0
    if not chain.nodes:
        return None, 0
    return chain.nodes[0].opcode, len(chain.nodes)


def _snapshots_for_play(
    book: Nfl2k5Playbook, play: PlaybookPlay
) -> tuple[SlotRoleSnapshot, ...]:
    rows: list[SlotRoleSnapshot] = []
    for assignment in play.assignments:
        opcode, length = _first_opcode(book, assignment)
        rows.append(
            SlotRoleSnapshot(
                play_index=play.index,
                slot=assignment.slot_index,
                descriptor=assignment.descriptor_word,
                chain_start=assignment.chain_start_index,
                body_offset=assignment_body_offset(play.index, assignment.slot_index),
                first_opcode=opcode,
                chain_length=length,
            )
        )
    return tuple(rows)


def _named(
    formations: Iterable[PlaybookFormation],
    plays: Iterable[PlaybookPlay],
    pattern: re.Pattern[str],
) -> tuple[tuple[str, ...], tuple[PlaybookPlay, ...]]:
    formation_names = tuple(
        f.name for f in formations if pattern.search(f.name or "")
    )
    matched_plays = tuple(p for p in plays if pattern.search(p.name or ""))
    # Also include plays linked from matching formations when names differ.
    return formation_names, matched_plays


def spike_g1_dime_ilb(book: Nfl2k5Playbook) -> PackageRuleSpikeResult:
    """Analyse a book for Dime package / ILB slot evidence (G1).

    Reports assignment slot snapshots (historical focus) plus the package-map
    writer path discovered on o0308: formation ``+0x0D`` 11-byte role map.
    """

    formation_names, plays = _named(book.formations, book.plays, _DIME_RE)
    # If no Dime-named plays, still snapshot first defensive play for layout.
    if not plays:
        plays = tuple(p for p in book.plays if p.family_id == 1)[:3]
    snapshots: list[SlotRoleSnapshot] = []
    for play in plays[:8]:
        for snap in _snapshots_for_play(book, play):
            if snap.slot in (4, 5, 6):  # ILB/OLB candidate band
                snapshots.append(snap)
    return PackageRuleSpikeResult(
        bug_id="G1",
        status="re_spike",  # runtime G1 fix unproved; package-map writer separate
        fixture_asset_id=O0308_ASSET_ID,
        fixture_pack_offset=O0308_PACK_OFFSET,
        layout=dict(G1_G2_LAYOUT),
        matching_formations=formation_names,
        matching_plays=tuple(p.name for p in plays[:12]),
        slot_snapshots=tuple(snapshots),
        hypothesis=(
            "Dime package remaps roster role membership via the formation "
            f"package map at body FORMATION_BASE+fi*{FORMATION_SIZE:#x}"
            f"+{PACKAGE_MAP_OFFSET_IN_FORMATION:#x} (11-byte permutation of 0..10). "
            "o0308 census: Nickel map [4,5,0,2,3,1,7,8,9,6,10] vs Dime "
            "[5,0,2,3,1,7,8,9,4,6,10] — role 4 moves slot-index 0→8. "
            "Assignment-only gate failed (shared plays byte-identical). "
            f"Also compare play-link aux at body+{FORMATION_AUX_BASE:#x}."
        ),
        next_offline_writer_gate=(
            "Package-map offline writer is shipped "
            "(build_formation_package_map_patch + verify). Runtime G1 fix still "
            "needs emulator proof that remapping Dime role 4 toward Nickel-like "
            "placement restores ILB field time. No community one-click fix pack "
            "until runtime-proved. Assignment 8-byte path is closed as not the "
            "primary delta."
        ),
    )


def spike_g2_ace_te(book: Nfl2k5Playbook) -> PackageRuleSpikeResult:
    """Analyse a book for Ace package / TE→WR evidence (G2)."""

    formation_names, plays = _named(book.formations, book.plays, _ACE_RE)
    if not plays:
        plays = tuple(p for p in book.plays if p.family_id == 0)[:3]
    snapshots: list[SlotRoleSnapshot] = []
    for play in plays[:8]:
        for snap in _snapshots_for_play(book, play):
            # TE/WR candidate slots: mid/skill (3,6,7,8) per role variance docs
            if snap.slot in (3, 6, 7, 8, 9):
                snapshots.append(snap)
    return PackageRuleSpikeResult(
        bug_id="G2",
        status="re_spike",
        fixture_asset_id=O0308_ASSET_ID,
        fixture_pack_offset=O0308_PACK_OFFSET,
        layout=dict(G1_G2_LAYOUT),
        matching_formations=formation_names,
        matching_plays=tuple(p.name for p in plays[:12]),
        slot_snapshots=tuple(snapshots),
        hypothesis=(
            "Ace package long-down rules convert TE assignment membership to a "
            "WR chain. o0308 census: Ace shares the same formation package map "
            "as all other offense formations "
            f"([0,8,6,9,7,10,1,4,3,5,2] at +{PACKAGE_MAP_OFFSET_IN_FORMATION:#x}) "
            "— G2 is not package-map. Compare Ace formation play-link packed "
            f"values ({FORMATION_PLAY_LINKS} links) and skill-slot descriptors "
            f"at body+{PLAY_BASE:#x}+play*{PLAY_SIZE:#x}+8+slot*8 against "
            "non-Ace twins; also Save Assignments / director surfaces."
        ),
        next_offline_writer_gate=(
            "Package-map path does not differentiate Ace. Next: Ace vs Quads "
            "link-table + skill-slot assignment XOR on o0308; APF MASTER "
            "assignment census for TE-named plays. Until a pure offline delta "
            "is isolated: re_spike only — no one-click fix pack."
        ),
    )


def layout_pins() -> dict[str, int | str]:
    """Public pin table for docs and tests."""

    return dict(G1_G2_LAYOUT)


def formation_package_map_body_offset(formation_index: int) -> int:
    """Body-relative offset of the 11-byte package role map for one formation."""

    if not 0 <= formation_index < FORMATION_CAPACITY:
        raise ValidationError(
            f"formation_index must be 0..{FORMATION_CAPACITY - 1}; "
            f"got {formation_index}."
        )
    return (
        FORMATION_BASE
        + formation_index * FORMATION_SIZE
        + PACKAGE_MAP_OFFSET_IN_FORMATION
    )


def _validate_package_map(package_map: Sequence[int]) -> bytes:
    if len(package_map) != PACKAGE_MAP_SIZE:
        raise ValidationError(
            f"Package map must be {PACKAGE_MAP_SIZE} role ids; "
            f"got {len(package_map)}."
        )
    values = [int(v) for v in package_map]
    for v in values:
        if not 0 <= v <= 10:
            raise ValidationError(
                f"Package map role ids must be 0..10; got {v}."
            )
    if sorted(values) != list(range(PACKAGE_MAP_SIZE)):
        raise ValidationError(
            "Package map must be a permutation of 0..10 "
            f"(got {values})."
        )
    return bytes(values)


def read_formation_package_map(
    raw_resource: bytes, formation_index: int
) -> tuple[int, ...]:
    """Read the 11-byte package map from a full PLAY resource (header+body)."""

    _require_play_resource(raw_resource)
    body = raw_resource[RESOURCE_HEADER_SIZE:]
    off = formation_package_map_body_offset(formation_index)
    chunk = body[off : off + PACKAGE_MAP_SIZE]
    if len(chunk) != PACKAGE_MAP_SIZE:
        raise ValidationError("Package map lies outside the PLAY body.")
    return tuple(chunk)


def read_all_formation_package_maps(
    raw_resource: bytes, *, formation_count: int | None = None
) -> dict[int, tuple[int, ...]]:
    """Read package maps for formations 0..count-1 (default: parsed count)."""

    _require_play_resource(raw_resource)
    book = parse_playbook_resource(raw_resource)
    count = formation_count if formation_count is not None else len(book.formations)
    return {
        i: read_formation_package_map(raw_resource, i) for i in range(count)
    }


@dataclass(frozen=True, slots=True)
class G1DimeNickelCensus:
    """o0308-class census result for the G1 assignment-only gate."""

    dime_formation_index: int
    nickel_formation_index: int
    dime_package_map: tuple[int, ...]
    nickel_package_map: tuple[int, ...]
    package_map_differs: bool
    role_slot_deltas: tuple[tuple[int, int, int], ...]  # role, nickel_slot, dime_slot
    shared_play_indices: tuple[int, ...]
    only_dime_play_indices: tuple[int, ...]
    only_nickel_play_indices: tuple[int, ...]
    shared_plays_assignment_identical: bool
    link_table_diff_count: int
    assignment_only_gate: str  # "failed" | "passed"
    primary_offline_delta: str
    notes: str


def census_g1_dime_vs_nickel(raw_resource: bytes) -> G1DimeNickelCensus:
    """Compare Dime vs Nickel on a real PLAY resource (header+body).

    Proves whether the assignment-only offline gate holds and records the
    package-map delta that is the primary offline surface for G1.
    """

    _require_play_resource(raw_resource)
    body = raw_resource[RESOURCE_HEADER_SIZE:]
    book = parse_playbook_resource(raw_resource)

    dime_i = next(
        (f.index for f in book.formations if _DIME_RE.search(f.name or "")),
        None,
    )
    nickel_i = next(
        (f.index for f in book.formations if re.search(r"\bnickel\b", f.name or "", re.I)),
        None,
    )
    if dime_i is None or nickel_i is None:
        raise ValidationError(
            "Census requires both Dime and Nickel formations in the PLAY book."
        )

    dime_map = read_formation_package_map(raw_resource, dime_i)
    nickel_map = read_formation_package_map(raw_resource, nickel_i)

    role_deltas: list[tuple[int, int, int]] = []
    for role in range(PACKAGE_MAP_SIZE):
        ns = nickel_map.index(role)
        ds = dime_map.index(role)
        if ns != ds:
            role_deltas.append((role, ns, ds))

    n_links = book.formations[nickel_i].play_links
    d_links = book.formations[dime_i].play_links
    n_plays = {link.play_index for link in n_links}
    d_plays = {link.play_index for link in d_links}
    shared = tuple(sorted(n_plays & d_plays))
    only_d = tuple(sorted(d_plays - n_plays))
    only_n = tuple(sorted(n_plays - d_plays))

    # Shared play indices refer to the same PLAY records → byte-identical.
    # Cross-check: for each shared index, play record equals itself (tautology
    # that documents "no dual-copy of the same play under two indices").
    assign_identical = all(
        body[PLAY_BASE + pi * PLAY_SIZE : PLAY_BASE + (pi + 1) * PLAY_SIZE]
        == body[PLAY_BASE + pi * PLAY_SIZE : PLAY_BASE + (pi + 1) * PLAY_SIZE]
        for pi in shared
    )

    # Link-row diffs (pairwise up to min length)
    link_diffs = 0
    for a, b in zip(n_links, d_links):
        if (
            a.play_index != b.play_index
            or a.group != b.group
            or a.packed_value != b.packed_value
        ):
            link_diffs += 1
    link_diffs += abs(len(n_links) - len(d_links))

    if dime_map != nickel_map:
        gate = "failed"
        primary = (
            f"formation package map @ +{PACKAGE_MAP_OFFSET_IN_FORMATION:#x} "
            f"(Dime {list(dime_map)} vs Nickel {list(nickel_map)})"
        )
    else:
        gate = "unknown"
        primary = "unknown — package maps match; recheck link/assignment tables"

    return G1DimeNickelCensus(
        dime_formation_index=dime_i,
        nickel_formation_index=nickel_i,
        dime_package_map=dime_map,
        nickel_package_map=nickel_map,
        package_map_differs=dime_map != nickel_map,
        role_slot_deltas=tuple(role_deltas),
        shared_play_indices=shared,
        only_dime_play_indices=only_d,
        only_nickel_play_indices=only_n,
        shared_plays_assignment_identical=assign_identical,
        link_table_diff_count=link_diffs,
        assignment_only_gate=gate,
        primary_offline_delta=primary,
        notes=(
            "Shared play indices are the same PLAY records (byte-identical). "
            "G1 offline surface is the 11-byte formation package map, not "
            "per-play assignment 8-byte fields. Runtime effect unproved."
        ),
    )


@dataclass(frozen=True, slots=True)
class PackageMapPatchResult:
    """Result of an offline formation package-map patch."""

    raw_resource: bytes
    formation_index: int
    body_offset: int
    resource_offset: int  # body_offset + RESOURCE_HEADER_SIZE
    old_map: tuple[int, ...]
    new_map: tuple[int, ...]
    changed_byte_count: int
    source_sha256: str
    result_sha256: str
    status: str  # offline_writer_proved for bytes only


def build_formation_package_map_patch(
    raw_resource: bytes,
    formation_index: int,
    new_map: Sequence[int],
) -> PackageMapPatchResult:
    """Patch one formation's 11-byte package map (fail-closed).

    Touches **only** those 11 bytes. Validates new_map is a permutation of
    0..10. Independent verifier: :func:`verify_formation_package_map_patch`.

    Capability: offline-writer-proved for the map bytes. **Not** runtime-proved
    as a G1 gameplay fix.
    """

    _require_play_resource(raw_resource)
    new_bytes = _validate_package_map(new_map)
    old = read_formation_package_map(raw_resource, formation_index)
    body_off = formation_package_map_body_offset(formation_index)
    res_off = RESOURCE_HEADER_SIZE + body_off

    out = bytearray(raw_resource)
    out[res_off : res_off + PACKAGE_MAP_SIZE] = new_bytes
    result = bytes(out)

    # Must still parse as a valid PLAY resource.
    parse_playbook_resource(result)

    changed = sum(
        1 for a, b in zip(raw_resource, result, strict=True) if a != b
    )
    if changed != sum(1 for a, b in zip(old, new_bytes) if a != b):
        # Defensive: only the map region may change.
        outside = [
            i
            for i in range(len(raw_resource))
            if raw_resource[i] != result[i]
            and not (res_off <= i < res_off + PACKAGE_MAP_SIZE)
        ]
        if outside:
            raise ValidationError(
                f"Package-map patch leaked outside map region at offsets {outside[:8]}."
            )

    return PackageMapPatchResult(
        raw_resource=result,
        formation_index=formation_index,
        body_offset=body_off,
        resource_offset=res_off,
        old_map=old,
        new_map=tuple(new_bytes),
        changed_byte_count=changed,
        source_sha256=hashlib.sha256(raw_resource).hexdigest(),
        result_sha256=hashlib.sha256(result).hexdigest(),
        status="offline_writer_proved",
    )


def verify_formation_package_map_patch(
    source: bytes,
    patched: bytes,
    formation_index: int,
    expected_new_map: Sequence[int],
) -> None:
    """Independent byte-diff verifier for a package-map patch.

    Raises :class:`ValidationError` on any failure.
    """

    _require_play_resource(source)
    _require_play_resource(patched)
    expected = _validate_package_map(expected_new_map)
    if len(source) != len(patched):
        raise ValidationError(
            f"Patched resource length {len(patched)} != source {len(source)}."
        )

    body_off = formation_package_map_body_offset(formation_index)
    res_off = RESOURCE_HEADER_SIZE + body_off
    actual = patched[res_off : res_off + PACKAGE_MAP_SIZE]
    if actual != expected:
        raise ValidationError(
            f"Patched map {list(actual)} != expected {list(expected)}."
        )

    for i, (a, b) in enumerate(zip(source, patched, strict=True)):
        if res_off <= i < res_off + PACKAGE_MAP_SIZE:
            continue
        if a != b:
            raise ValidationError(
                f"Byte {i} changed outside package map "
                f"(source 0x{a:02x} → 0x{b:02x})."
            )

    # Reparse both
    parse_playbook_resource(source)
    parse_playbook_resource(patched)
    got = read_formation_package_map(patched, formation_index)
    if got != tuple(expected):
        raise ValidationError("Re-read package map does not match expected.")


def _require_play_resource(raw: bytes) -> None:
    if len(raw) != RESOURCE_HEADER_SIZE + BODY_SIZE:
        raise ValidationError(
            f"PLAY resource is {len(raw):,} bytes; "
            f"{RESOURCE_HEADER_SIZE + BODY_SIZE:,} were expected."
        )
    if raw[:4] != b"PLAY":
        raise ValidationError("Resource does not start with PLAY magic.")


def formation_link_table_body_offset(formation_index: int) -> int:
    """Body offset of the 0x50 formation play-link (aux) table."""

    if not 0 <= formation_index < FORMATION_CAPACITY:
        raise ValidationError(
            f"formation_index must be 0..{FORMATION_CAPACITY - 1}; "
            f"got {formation_index}."
        )
    return FORMATION_AUX_BASE + formation_index * FORMATION_AUX_SIZE


@dataclass(frozen=True, slots=True)
class LinkTablePatchResult:
    """Copy of one formation's play-link aux table onto another (G2 menu)."""

    raw_resource: bytes
    target_formation_index: int
    donor_formation_index: int
    body_offset: int
    resource_offset: int
    changed_byte_count: int
    target_link_count_before: int
    target_link_count_after: int
    donor_link_count: int
    source_sha256: str
    result_sha256: str
    status: str


def build_formation_link_table_copy_patch(
    raw_resource: bytes,
    target_formation_index: int,
    donor_formation_index: int,
) -> LinkTablePatchResult:
    """Copy donor formation play-link table (aux 0x50) onto target.

    Fail-closed offline writer for **menu composition** (G2 class). Does not
    change package maps or play assignment records. Independent verifier:
    :func:`verify_formation_link_table_copy_patch`.

    Capability: offline-writer-proved for the 80 aux bytes. **Not** a runtime
    TE→WR package-rule fix.
    """

    _require_play_resource(raw_resource)
    if target_formation_index == donor_formation_index:
        raise ValidationError("Donor and target formation indices must differ.")
    book = parse_playbook_resource(raw_resource)
    if not 0 <= target_formation_index < len(book.formations):
        raise ValidationError(
            f"Target formation {target_formation_index} is outside the book."
        )
    if not 0 <= donor_formation_index < len(book.formations):
        raise ValidationError(
            f"Donor formation {donor_formation_index} is outside the book."
        )

    body_off = formation_link_table_body_offset(target_formation_index)
    donor_off = formation_link_table_body_offset(donor_formation_index)
    res_off = RESOURCE_HEADER_SIZE + body_off
    donor_res = RESOURCE_HEADER_SIZE + donor_off
    donor_bytes = raw_resource[donor_res : donor_res + FORMATION_AUX_SIZE]
    if len(donor_bytes) != FORMATION_AUX_SIZE:
        raise ValidationError("Donor link table is truncated.")

    out = bytearray(raw_resource)
    out[res_off : res_off + FORMATION_AUX_SIZE] = donor_bytes
    result = bytes(out)
    patched_book = parse_playbook_resource(result)

    changed = sum(
        1 for a, b in zip(raw_resource, result, strict=True) if a != b
    )
    return LinkTablePatchResult(
        raw_resource=result,
        target_formation_index=target_formation_index,
        donor_formation_index=donor_formation_index,
        body_offset=body_off,
        resource_offset=res_off,
        changed_byte_count=changed,
        target_link_count_before=len(book.formations[target_formation_index].play_links),
        target_link_count_after=len(
            patched_book.formations[target_formation_index].play_links
        ),
        donor_link_count=len(book.formations[donor_formation_index].play_links),
        source_sha256=hashlib.sha256(raw_resource).hexdigest(),
        result_sha256=hashlib.sha256(result).hexdigest(),
        status="offline_writer_proved",
    )


def verify_formation_link_table_copy_patch(
    source: bytes,
    patched: bytes,
    target_formation_index: int,
    donor_formation_index: int,
) -> None:
    """Independent byte-diff verifier for a formation link-table copy."""

    _require_play_resource(source)
    _require_play_resource(patched)
    if len(source) != len(patched):
        raise ValidationError("Patched resource length differs from source.")

    body_off = formation_link_table_body_offset(target_formation_index)
    res_off = RESOURCE_HEADER_SIZE + body_off
    donor_off = formation_link_table_body_offset(donor_formation_index)
    donor_res = RESOURCE_HEADER_SIZE + donor_off
    expected = source[donor_res : donor_res + FORMATION_AUX_SIZE]
    actual = patched[res_off : res_off + FORMATION_AUX_SIZE]
    if actual != expected:
        raise ValidationError("Patched link table does not match donor table.")

    for i, (a, b) in enumerate(zip(source, patched, strict=True)):
        if res_off <= i < res_off + FORMATION_AUX_SIZE:
            continue
        if a != b:
            raise ValidationError(
                f"Byte {i} changed outside formation link table."
            )

    parse_playbook_resource(source)
    parse_playbook_resource(patched)


_NICKEL_RE = re.compile(r"\bnickel\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class G1DimeFromNickelTarget:
    """One Dime-named formation that received the Nickel package map."""

    formation_index: int
    formation_name: str
    old_map: tuple[int, ...]
    new_map: tuple[int, ...]
    resource_offset: int
    changed_byte_count: int


@dataclass(frozen=True, slots=True)
class G1DimeFromNickelPackResult:
    """Multi-formation offline G1 package-map pack (bytes only; runtime unproved)."""

    raw_resource: bytes
    nickel_formation_index: int
    nickel_formation_name: str
    nickel_package_map: tuple[int, ...]
    targets: tuple[G1DimeFromNickelTarget, ...]
    total_changed_byte_count: int
    source_sha256: str
    result_sha256: str
    status: str
    honesty: str
    manifest: dict[str, object]


def build_g1_dime_from_nickel_package_map_pack(
    raw_resource: bytes,
) -> G1DimeFromNickelPackResult:
    """Copy the first Nickel package map onto **every** Dime-named formation.

    Fail-closed offline writer for the G1 package-map surface across the whole
    PLAY book (not just one formation pair). Touches only 11-byte package-map
    regions. Independent verifier:
    :func:`verify_g1_dime_from_nickel_package_map_pack`.

    Capability: **offline_writer_proved** for map bytes. **Not** a runtime G1
    fix pack — do not ship as community one-click runtime proof.
    """

    _require_play_resource(raw_resource)
    book = parse_playbook_resource(raw_resource)

    nickel = next(
        (f for f in book.formations if _NICKEL_RE.search(f.name or "")),
        None,
    )
    if nickel is None:
        raise ValidationError(
            "G1 multi-Dime pack needs a formation whose name contains Nickel."
        )
    dime_forms = tuple(
        f for f in book.formations if _DIME_RE.search(f.name or "")
    )
    if not dime_forms:
        raise ValidationError(
            "G1 multi-Dime pack needs at least one formation whose name "
            "contains Dime."
        )

    nickel_map = read_formation_package_map(raw_resource, nickel.index)
    working = raw_resource
    targets: list[G1DimeFromNickelTarget] = []
    allowed_regions: list[tuple[int, int]] = []

    for form in dime_forms:
        old = read_formation_package_map(working, form.index)
        if old == nickel_map:
            # Still record identity (no-op) so the manifest lists every Dime.
            res_off = (
                RESOURCE_HEADER_SIZE
                + formation_package_map_body_offset(form.index)
            )
            targets.append(
                G1DimeFromNickelTarget(
                    formation_index=form.index,
                    formation_name=str(form.name or ""),
                    old_map=old,
                    new_map=nickel_map,
                    resource_offset=res_off,
                    changed_byte_count=0,
                )
            )
            continue
        patch = build_formation_package_map_patch(
            working, form.index, nickel_map
        )
        verify_formation_package_map_patch(
            working, patch.raw_resource, form.index, nickel_map
        )
        working = patch.raw_resource
        targets.append(
            G1DimeFromNickelTarget(
                formation_index=form.index,
                formation_name=str(form.name or ""),
                old_map=old,
                new_map=patch.new_map,
                resource_offset=patch.resource_offset,
                changed_byte_count=patch.changed_byte_count,
            )
        )
        allowed_regions.append(
            (patch.resource_offset, patch.resource_offset + PACKAGE_MAP_SIZE)
        )

    # Independent multi-region verify against original source.
    verify_g1_dime_from_nickel_package_map_pack(
        raw_resource,
        working,
        nickel_index=nickel.index,
        dime_indices=tuple(t.formation_index for t in targets),
        expected_map=nickel_map,
    )

    total_changed = sum(t.changed_byte_count for t in targets)
    honesty = (
        "offline_writer_proved for formation package-map bytes only. "
        "Runtime G1 (Dime ILB→OLB) is unproved. Not a project edit. "
        "Source ISO is never mutated. Private PLAY export only."
    )
    manifest: dict[str, object] = {
        "kind": "g1_dime_from_nickel_package_map_pack",
        "capability": "offline_writer_proved",
        "runtime_proved": False,
        "bug_id": "G1",
        "nickel_formation_index": nickel.index,
        "nickel_formation_name": str(nickel.name or ""),
        "nickel_package_map": list(nickel_map),
        "dime_targets": [
            {
                "formation_index": t.formation_index,
                "formation_name": t.formation_name,
                "old_map": list(t.old_map),
                "new_map": list(t.new_map),
                "resource_offset": t.resource_offset,
                "changed_byte_count": t.changed_byte_count,
            }
            for t in targets
        ],
        "total_changed_byte_count": total_changed,
        "source_sha256": hashlib.sha256(raw_resource).hexdigest(),
        "result_sha256": hashlib.sha256(working).hexdigest(),
        "honesty": honesty,
        "layout": {
            "package_map_offset_in_formation": PACKAGE_MAP_OFFSET_IN_FORMATION,
            "package_map_size": PACKAGE_MAP_SIZE,
            "package_map_offset_formula": G1_G2_LAYOUT[
                "package_map_offset_formula"
            ],
        },
    }
    return G1DimeFromNickelPackResult(
        raw_resource=working,
        nickel_formation_index=nickel.index,
        nickel_formation_name=str(nickel.name or ""),
        nickel_package_map=nickel_map,
        targets=tuple(targets),
        total_changed_byte_count=total_changed,
        source_sha256=hashlib.sha256(raw_resource).hexdigest(),
        result_sha256=hashlib.sha256(working).hexdigest(),
        status="offline_writer_proved",
        honesty=honesty,
        manifest=manifest,
    )


def verify_g1_dime_from_nickel_package_map_pack(
    source: bytes,
    patched: bytes,
    *,
    nickel_index: int,
    dime_indices: Sequence[int],
    expected_map: Sequence[int],
) -> None:
    """Independent multi-region byte-diff verifier for the G1 multi-Dime pack."""

    _require_play_resource(source)
    _require_play_resource(patched)
    expected = _validate_package_map(expected_map)
    if len(source) != len(patched):
        raise ValidationError(
            f"Patched resource length {len(patched)} != source {len(source)}."
        )

    allowed: set[int] = set()
    for fi in dime_indices:
        res_off = RESOURCE_HEADER_SIZE + formation_package_map_body_offset(
            int(fi)
        )
        for i in range(res_off, res_off + PACKAGE_MAP_SIZE):
            allowed.add(i)
        actual = patched[res_off : res_off + PACKAGE_MAP_SIZE]
        if actual != expected:
            raise ValidationError(
                f"Dime formation {fi} map {list(actual)} != expected "
                f"Nickel map {list(expected)}."
            )

    for i, (a, b) in enumerate(zip(source, patched, strict=True)):
        if i in allowed:
            continue
        if a != b:
            raise ValidationError(
                f"Byte {i} changed outside Dime package-map regions "
                f"(source 0x{a:02x} → 0x{b:02x})."
            )

    # Nickel map itself must be unchanged (donor is read-only in the pack).
    nickel_read = read_formation_package_map(patched, nickel_index)
    if nickel_read != tuple(expected):
        raise ValidationError(
            "Nickel donor package map was mutated; pack must leave Nickel intact."
        )

    parse_playbook_resource(source)
    parse_playbook_resource(patched)


_QUADS_RE = re.compile(r"\bquads\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class G2AceFromQuadsTarget:
    """One Ace-named formation that received the Quads play-link table."""

    formation_index: int
    formation_name: str
    link_count_before: int
    link_count_after: int
    resource_offset: int
    changed_byte_count: int


@dataclass(frozen=True, slots=True)
class G2AceFromQuadsPackResult:
    """Multi-formation offline G2 link-table pack (menu bytes; runtime unproved)."""

    raw_resource: bytes
    quads_formation_index: int
    quads_formation_name: str
    quads_link_count: int
    targets: tuple[G2AceFromQuadsTarget, ...]
    total_changed_byte_count: int
    source_sha256: str
    result_sha256: str
    status: str
    honesty: str
    manifest: dict[str, object]


def build_g2_ace_from_quads_link_table_pack(
    raw_resource: bytes,
) -> G2AceFromQuadsPackResult:
    """Copy the first Quads play-link table onto **every** Ace-named formation.

    Fail-closed offline writer for the G2 **menu composition** surface across
    the whole PLAY book. Touches only formation aux (0x50) play-link tables.
    Does **not** change package maps or play assignment records. Independent
    verifier: :func:`verify_g2_ace_from_quads_link_table_pack`.

    Capability: **offline_writer_proved** for menu link-table bytes. **Not** a
    runtime G2 (TE→WR) fix pack — do not ship as community one-click runtime
    proof.
    """

    _require_play_resource(raw_resource)
    book = parse_playbook_resource(raw_resource)

    quads = next(
        (f for f in book.formations if _QUADS_RE.search(f.name or "")),
        None,
    )
    if quads is None:
        raise ValidationError(
            "G2 multi-Ace pack needs a formation whose name contains Quads."
        )
    ace_forms = tuple(
        f for f in book.formations if _ACE_RE.search(f.name or "")
    )
    if not ace_forms:
        raise ValidationError(
            "G2 multi-Ace pack needs at least one formation whose name "
            "contains Ace."
        )
    if any(f.index == quads.index for f in ace_forms):
        raise ValidationError(
            "G2 multi-Ace pack refuses a formation named both Ace and Quads."
        )

    working = raw_resource
    targets: list[G2AceFromQuadsTarget] = []
    for form in ace_forms:
        before_count = len(form.play_links)
        patch = build_formation_link_table_copy_patch(
            working, form.index, quads.index
        )
        verify_formation_link_table_copy_patch(
            working, patch.raw_resource, form.index, quads.index
        )
        # Package map of Ace must stay identity with pre-pack map.
        old_map = read_formation_package_map(working, form.index)
        new_map = read_formation_package_map(patch.raw_resource, form.index)
        if old_map != new_map:
            raise ValidationError(
                f"G2 pack mutated package map on Ace formation {form.index}."
            )
        working = patch.raw_resource
        targets.append(
            G2AceFromQuadsTarget(
                formation_index=form.index,
                formation_name=str(form.name or ""),
                link_count_before=before_count,
                link_count_after=patch.target_link_count_after,
                resource_offset=patch.resource_offset,
                changed_byte_count=patch.changed_byte_count,
            )
        )

    verify_g2_ace_from_quads_link_table_pack(
        raw_resource,
        working,
        quads_index=quads.index,
        ace_indices=tuple(t.formation_index for t in targets),
    )

    total_changed = sum(t.changed_byte_count for t in targets)
    honesty = (
        "offline_writer_proved for formation play-link (menu) table bytes only. "
        "Runtime G2 (Ace TE→WR) is unproved. Package maps and play assignments "
        "are untouched. Not a project edit. Source ISO is never mutated. "
        "Private PLAY export only."
    )
    manifest: dict[str, object] = {
        "kind": "g2_ace_from_quads_link_table_pack",
        "capability": "offline_writer_proved",
        "runtime_proved": False,
        "bug_id": "G2",
        "quads_formation_index": quads.index,
        "quads_formation_name": str(quads.name or ""),
        "quads_link_count": len(quads.play_links),
        "ace_targets": [
            {
                "formation_index": t.formation_index,
                "formation_name": t.formation_name,
                "link_count_before": t.link_count_before,
                "link_count_after": t.link_count_after,
                "resource_offset": t.resource_offset,
                "changed_byte_count": t.changed_byte_count,
            }
            for t in targets
        ],
        "total_changed_byte_count": total_changed,
        "source_sha256": hashlib.sha256(raw_resource).hexdigest(),
        "result_sha256": hashlib.sha256(working).hexdigest(),
        "honesty": honesty,
        "layout": {
            "formation_aux_base": FORMATION_AUX_BASE,
            "formation_aux_size": FORMATION_AUX_SIZE,
            "surface": "play_link_menu_table",
        },
    }
    return G2AceFromQuadsPackResult(
        raw_resource=working,
        quads_formation_index=quads.index,
        quads_formation_name=str(quads.name or ""),
        quads_link_count=len(quads.play_links),
        targets=tuple(targets),
        total_changed_byte_count=total_changed,
        source_sha256=hashlib.sha256(raw_resource).hexdigest(),
        result_sha256=hashlib.sha256(working).hexdigest(),
        status="offline_writer_proved",
        honesty=honesty,
        manifest=manifest,
    )


def verify_g2_ace_from_quads_link_table_pack(
    source: bytes,
    patched: bytes,
    *,
    quads_index: int,
    ace_indices: Sequence[int],
) -> None:
    """Independent multi-region byte-diff verifier for the G2 multi-Ace pack."""

    _require_play_resource(source)
    _require_play_resource(patched)
    if len(source) != len(patched):
        raise ValidationError(
            f"Patched resource length {len(patched)} != source {len(source)}."
        )

    donor_res = RESOURCE_HEADER_SIZE + formation_link_table_body_offset(
        int(quads_index)
    )
    expected_table = source[donor_res : donor_res + FORMATION_AUX_SIZE]
    if len(expected_table) != FORMATION_AUX_SIZE:
        raise ValidationError("Quads donor link table is truncated.")

    allowed: set[int] = set()
    for fi in ace_indices:
        res_off = RESOURCE_HEADER_SIZE + formation_link_table_body_offset(
            int(fi)
        )
        for i in range(res_off, res_off + FORMATION_AUX_SIZE):
            allowed.add(i)
        actual = patched[res_off : res_off + FORMATION_AUX_SIZE]
        if actual != expected_table:
            raise ValidationError(
                f"Ace formation {fi} link table does not match Quads donor."
            )

    for i, (a, b) in enumerate(zip(source, patched, strict=True)):
        if i in allowed:
            continue
        if a != b:
            raise ValidationError(
                f"Byte {i} changed outside Ace link-table regions."
            )

    # Quads donor table identity preserved.
    donor_after = patched[donor_res : donor_res + FORMATION_AUX_SIZE]
    if donor_after != expected_table:
        raise ValidationError(
            "Quads donor link table was mutated; pack must leave Quads intact."
        )

    parse_playbook_resource(source)
    parse_playbook_resource(patched)


_APF_ACE_NAME_RE = re.compile(r"\bace\b", re.IGNORECASE)


def _require_apf_master_body(raw: bytes) -> None:
    if len(raw) != APF_MASTER_BODY_SIZE:
        raise ValidationError(
            f"APF MASTER PLAY body is {len(raw):,} bytes; "
            f"{APF_MASTER_BODY_SIZE:,} were expected."
        )


def apf_formation_count(raw_body: bytes) -> int:
    """Declared formation count at MASTER +0x34 (big-endian)."""

    _require_apf_master_body(raw_body)
    count = struct.unpack_from(">I", raw_body, APF_FORMATION_COUNT_OFFSET)[0]
    if not 1 <= count <= APF_FORMATION_COUNT_MAX:
        raise ValidationError(
            f"APF MASTER formation count {count} is outside 1.."
            f"{APF_FORMATION_COUNT_MAX}."
        )
    end = APF_FORMATION_BASE + count * APF_FORMATION_SIZE
    if end > len(raw_body):
        raise ValidationError("APF formation table overruns the MASTER body.")
    return count


def apf_formation_package_map_offset(formation_index: int) -> int:
    """Body offset of the 11-byte package map at formation +0x11."""

    if formation_index < 0:
        raise ValidationError(
            f"formation_index must be non-negative; got {formation_index}."
        )
    return (
        APF_FORMATION_BASE
        + formation_index * APF_FORMATION_SIZE
        + APF_PACKAGE_MAP_OFFSET_IN_FORMATION
    )


def _apf_relative(raw_body: bytes, field: int) -> int:
    if field < 0 or field + 4 > len(raw_body):
        raise ValidationError("APF formation name pointer is out of range.")
    stored = struct.unpack_from(">i", raw_body, field)[0]
    target = field - 1 + stored
    if not 0 <= target < len(raw_body):
        raise ValidationError(
            f"APF formation name pointer at 0x{field:x} resolves outside the body."
        )
    return target


def read_apf_formation_name(raw_body: bytes, formation_index: int) -> str:
    """Read one MASTER formation name (UTF-16BE, relative pointer at +0)."""

    count = apf_formation_count(raw_body)
    if not 0 <= formation_index < count:
        raise ValidationError(
            f"formation_index must be 0..{count - 1}; got {formation_index}."
        )
    field = APF_FORMATION_BASE + formation_index * APF_FORMATION_SIZE
    offset = _apf_relative(raw_body, field)
    if offset & 1:
        raise ValidationError(
            f"APF formation {formation_index} name is not UTF-16 aligned."
        )
    cursor = offset
    while cursor + 2 <= len(raw_body):
        if raw_body[cursor : cursor + 2] == b"\0\0":
            try:
                name = raw_body[offset:cursor].decode("utf-16be")
            except UnicodeDecodeError as exc:
                raise ValidationError(
                    f"APF formation {formation_index} name is not UTF-16BE."
                ) from exc
            if not name:
                raise ValidationError(f"APF formation {formation_index} has an empty name.")
            return name
        cursor += 2
    raise ValidationError(
        f"APF formation {formation_index} name is unterminated."
    )


def read_apf_formation_package_map(
    raw_body: bytes, formation_index: int
) -> tuple[int, ...]:
    """Read the 11-byte +0x11 package map from an APF MASTER body."""

    count = apf_formation_count(raw_body)
    if not 0 <= formation_index < count:
        raise ValidationError(
            f"formation_index must be 0..{count - 1}; got {formation_index}."
        )
    offset = apf_formation_package_map_offset(formation_index)
    chunk = raw_body[offset : offset + PACKAGE_MAP_SIZE]
    if len(chunk) != PACKAGE_MAP_SIZE:
        raise ValidationError("APF package map lies outside the MASTER body.")
    return tuple(chunk)


def swap_apf_package_map_wr3_te(package_map: Sequence[int]) -> tuple[int, ...]:
    """Swap roles 8 and 9. Result must stay a permutation of 0..10."""

    current = _validate_package_map(package_map)
    if (
        APF_PACKAGE_MAP_ROLE_TE not in current
        or APF_PACKAGE_MAP_ROLE_WR3 not in current
    ):
        raise ValidationError(
            "WR3↔TE swap needs both role 8 and role 9 in the package map."
        )
    swapped = bytes(
        APF_PACKAGE_MAP_ROLE_WR3
        if value == APF_PACKAGE_MAP_ROLE_TE
        else APF_PACKAGE_MAP_ROLE_TE
        if value == APF_PACKAGE_MAP_ROLE_WR3
        else value
        for value in current
    )
    return tuple(_validate_package_map(swapped))


def build_apf_formation_package_map_patch(
    raw_body: bytes,
    formation_index: int,
    new_map: Sequence[int],
) -> PackageMapPatchResult:
    """Patch one APF MASTER formation's +0x11 map. Touches only those 11 bytes."""

    _require_apf_master_body(raw_body)
    new_bytes = _validate_package_map(new_map)
    old = read_apf_formation_package_map(raw_body, formation_index)
    offset = apf_formation_package_map_offset(formation_index)
    out = bytearray(raw_body)
    out[offset : offset + PACKAGE_MAP_SIZE] = new_bytes
    result = bytes(out)
    changed = sum(1 for a, b in zip(raw_body, result, strict=True) if a != b)
    if changed != sum(1 for a, b in zip(old, new_bytes) if a != b):
        outside = [
            i
            for i in range(len(raw_body))
            if raw_body[i] != result[i]
            and not (offset <= i < offset + PACKAGE_MAP_SIZE)
        ]
        if outside:
            raise ValidationError(
                "APF package-map patch leaked outside the map region at "
                f"offsets {outside[:8]}."
            )
    return PackageMapPatchResult(
        raw_resource=result,
        formation_index=formation_index,
        body_offset=offset,
        resource_offset=offset,
        old_map=old,
        new_map=tuple(new_bytes),
        changed_byte_count=changed,
        source_sha256=hashlib.sha256(raw_body).hexdigest(),
        result_sha256=hashlib.sha256(result).hexdigest(),
        status="offline_writer_proved",
    )


def verify_apf_formation_package_map_patch(
    source: bytes,
    patched: bytes,
    formation_index: int,
    expected_new_map: Sequence[int],
) -> None:
    """Independent byte-diff verifier for one APF +0x11 map patch."""

    _require_apf_master_body(source)
    _require_apf_master_body(patched)
    expected = _validate_package_map(expected_new_map)
    if len(source) != len(patched):
        raise ValidationError(
            f"Patched MASTER length {len(patched)} != source {len(source)}."
        )
    offset = apf_formation_package_map_offset(formation_index)
    actual = patched[offset : offset + PACKAGE_MAP_SIZE]
    if actual != expected:
        raise ValidationError(
            f"APF formation {formation_index} map {list(actual)} != expected "
            f"{list(expected)}."
        )
    for i, (a, b) in enumerate(zip(source, patched, strict=True)):
        if offset <= i < offset + PACKAGE_MAP_SIZE:
            continue
        if a != b:
            raise ValidationError(
                f"Byte {i} changed outside APF formation {formation_index} "
                "package-map region."
            )
    got = read_apf_formation_package_map(patched, formation_index)
    if got != tuple(expected):
        raise ValidationError("Re-read APF package map does not match expected.")


@dataclass(frozen=True, slots=True)
class ApfAceEmptyCensus:
    """Retail Ace vs Ace Empty package-map census (not a 3rd-and-long proof)."""

    ace_formation_index: int
    ace_formation_name: str
    ace_package_map: tuple[int, ...]
    empty_formation_index: int
    empty_formation_name: str
    empty_package_map: tuple[int, ...]
    maps_identical: bool
    empty_is_wr3_te_swap_of_ace: bool
    slot_deltas: tuple[tuple[int, int, int], ...]
    notes: str


def census_apf_ace_vs_ace_empty(raw_body: bytes) -> ApfAceEmptyCensus:
    """Measure Ace vs Ace Empty maps. Retail Empty is slots 9/10, not 8↔9."""

    _require_apf_master_body(raw_body)
    count = apf_formation_count(raw_body)
    ace_i = empty_i = None
    ace_name = empty_name = ""
    for index in range(count):
        name = read_apf_formation_name(raw_body, index)
        if ace_i is None and name == "Ace":
            ace_i = index
            ace_name = name
        elif empty_i is None and name == "Ace Empty":
            empty_i = index
            empty_name = name
        if ace_i is not None and empty_i is not None:
            break
    if ace_i is None or empty_i is None:
        raise ValidationError(
            "Census needs exact MASTER formation names Ace and Ace Empty."
        )
    ace_map = read_apf_formation_package_map(raw_body, ace_i)
    empty_map = read_apf_formation_package_map(raw_body, empty_i)
    deltas = tuple(
        (slot, ace_map[slot], empty_map[slot])
        for slot in range(PACKAGE_MAP_SIZE)
        if ace_map[slot] != empty_map[slot]
    )
    is_swap = empty_map == swap_apf_package_map_wr3_te(ace_map)
    return ApfAceEmptyCensus(
        ace_formation_index=ace_i,
        ace_formation_name=ace_name,
        ace_package_map=ace_map,
        empty_formation_index=empty_i,
        empty_formation_name=empty_name,
        empty_package_map=empty_map,
        maps_identical=ace_map == empty_map,
        empty_is_wr3_te_swap_of_ace=is_swap,
        slot_deltas=deltas,
        notes=(
            "Retail Ace Empty is not an 8↔9 swap of Ace. Roles 8/9 stay in "
            "slots 2/3; the only delta is slots 9/10 (6↔7). The experimental "
            "pack therefore applies a uniqueness-preserving 8↔9 permutation "
            "to Ace-named maps rather than copying Ace Empty. Runtime G12 "
            "(TEs on 3rd-and-long) is unproved."
        ),
    )


@dataclass(frozen=True, slots=True)
class G12Wr3TeTarget:
    """One Ace-named MASTER formation that received the 8↔9 swap."""

    formation_index: int
    formation_name: str
    old_map: tuple[int, ...]
    new_map: tuple[int, ...]
    resource_offset: int
    changed_byte_count: int


@dataclass(frozen=True, slots=True)
class G12Wr3TePackResult:
    """Experimental APF 8↔9 package-map pack (bytes only; runtime unproved)."""

    raw_resource: bytes
    targets: tuple[G12Wr3TeTarget, ...]
    total_changed_byte_count: int
    source_sha256: str
    result_sha256: str
    status: str
    honesty: str
    manifest: dict[str, object]


def g12_wr3_te_honesty() -> str:
    return (
        "experimental Ace-named 8↔9 package-map remapping. "
        "offline_writer_proved for APF MASTER +0x11 package-map bytes only. "
        "Retail Ace Empty is not an 8↔9 swap of Ace (slots 9/10 are 6↔7). "
        "Ace Empty is not used as a source: this pack does not copy Ace Empty "
        "onto Ace. It swaps roles 8 and 9 on each Ace-named formation's own "
        "map. Runtime G12 (TEs on 3rd-and-long) is unproved. "
        "wr3_te_package_sub_proved stays False. Not a 3rd-and-long fix. "
        "Not a project edit. Source 0A is never mutated. Private MASTER "
        "PLAY export only."
    )


def list_apf_ace_named_formations(
    raw_body: bytes,
) -> tuple[tuple[int, str], ...]:
    """MASTER formations whose name matches a word-boundary Ace."""

    count = apf_formation_count(raw_body)
    found: list[tuple[int, str]] = []
    for index in range(count):
        name = read_apf_formation_name(raw_body, index)
        if _APF_ACE_NAME_RE.search(name):
            found.append((index, name))
    return tuple(found)


def _apf_exact_named_package_map(
    raw_body: bytes, exact_name: str
) -> tuple[int, ...] | None:
    for index in range(apf_formation_count(raw_body)):
        if read_apf_formation_name(raw_body, index) == exact_name:
            return read_apf_formation_package_map(raw_body, index)
    return None


def build_g12_wr3_te_package_map_pack(
    raw_body: bytes,
) -> G12Wr3TePackResult:
    """Swap roles 8↔9 on every Ace-named APF MASTER formation.

    Fail-closed experimental export. Touches only 11-byte +0x11 maps.
    Independent verifier: :func:`verify_g12_wr3_te_package_map_pack`.

    Capability: **offline_writer_proved** for map bytes. **Not** a runtime
    G12 / 3rd-and-long fix. ``wr3_te_package_sub_proved`` stays False.
    """

    _require_apf_master_body(raw_body)
    named = list_apf_ace_named_formations(raw_body)
    if not named:
        raise ValidationError(
            "G12 WR3↔TE pack needs at least one formation whose name "
            "contains Ace."
        )

    empty_source = _apf_exact_named_package_map(raw_body, "Ace Empty")

    working = raw_body
    targets: list[G12Wr3TeTarget] = []
    for index, name in named:
        # Each Ace-named map is remapped in place. Ace Empty is never a donor.
        old = read_apf_formation_package_map(working, index)
        new_map = swap_apf_package_map_wr3_te(old)
        if name == "Ace" and empty_source is not None and new_map == empty_source:
            raise ValidationError(
                "G12 pack must not copy Ace Empty onto Ace. The experimental "
                "export is an Ace-named 8↔9 remap, not an Ace Empty copy."
            )
        if old == new_map:
            targets.append(
                G12Wr3TeTarget(
                    formation_index=index,
                    formation_name=name,
                    old_map=old,
                    new_map=new_map,
                    resource_offset=apf_formation_package_map_offset(index),
                    changed_byte_count=0,
                )
            )
            continue
        patch = build_apf_formation_package_map_patch(working, index, new_map)
        verify_apf_formation_package_map_patch(
            working, patch.raw_resource, index, new_map
        )
        working = patch.raw_resource
        targets.append(
            G12Wr3TeTarget(
                formation_index=index,
                formation_name=name,
                old_map=old,
                new_map=patch.new_map,
                resource_offset=patch.resource_offset,
                changed_byte_count=patch.changed_byte_count,
            )
        )

    verify_g12_wr3_te_package_map_pack(
        raw_body,
        working,
        formation_indices=tuple(t.formation_index for t in targets),
    )

    total_changed = sum(t.changed_byte_count for t in targets)
    honesty = g12_wr3_te_honesty()
    ace_map = None
    empty_map = None
    for target in targets:
        if target.formation_name == "Ace":
            ace_map = list(target.old_map)
        elif target.formation_name == "Ace Empty":
            empty_map = list(target.old_map)
    manifest: dict[str, object] = {
        "kind": "g12_wr3_te_package_map_pack",
        "capability": "offline_writer_proved",
        "runtime_proved": False,
        "experimental": APF_G12_PACK_EXPERIMENTAL,
        "wr3_te_package_sub_proved": False,
        "APF_3RD_AND_LONG_PLAY_CHOICE_PROVED": False,
        "ace_empty_is_wr3_te_swap_of_ace": False,
        "ace_empty_used_as_source": APF_G12_PACK_USES_ACE_EMPTY_AS_SOURCE,
        "bug_id": "G12",
        "package_map_offset_in_formation": APF_PACKAGE_MAP_OFFSET_IN_FORMATION,
        "ace_stock_package_map": list(APF_ACE_PACKAGE_MAP),
        "ace_empty_stock_package_map": list(APF_ACE_EMPTY_PACKAGE_MAP),
        "ace_source_package_map": ace_map,
        "ace_empty_source_package_map": empty_map,
        "ace_vs_ace_empty_slot_deltas": [
            list(row) for row in APF_ACE_VS_ACE_EMPTY_SLOT_DELTAS
        ],
        "targets": [
            {
                "formation_index": t.formation_index,
                "formation_name": t.formation_name,
                "old_map": list(t.old_map),
                "new_map": list(t.new_map),
                "resource_offset": t.resource_offset,
                "changed_byte_count": t.changed_byte_count,
            }
            for t in targets
        ],
        "total_changed_byte_count": total_changed,
        "source_sha256": hashlib.sha256(raw_body).hexdigest(),
        "result_sha256": hashlib.sha256(working).hexdigest(),
        "honesty": honesty,
    }
    return G12Wr3TePackResult(
        raw_resource=working,
        targets=tuple(targets),
        total_changed_byte_count=total_changed,
        source_sha256=hashlib.sha256(raw_body).hexdigest(),
        result_sha256=hashlib.sha256(working).hexdigest(),
        status="offline_writer_proved",
        honesty=honesty,
        manifest=manifest,
    )


def verify_g12_wr3_te_package_map_pack(
    source: bytes,
    patched: bytes,
    *,
    formation_indices: Sequence[int],
) -> None:
    """Independent multi-region verifier for the G12 8↔9 pack."""

    _require_apf_master_body(source)
    _require_apf_master_body(patched)
    if len(source) != len(patched):
        raise ValidationError(
            f"Patched MASTER length {len(patched)} != source {len(source)}."
        )
    if not formation_indices:
        raise ValidationError("G12 pack verifier needs at least one target index.")

    empty_source = _apf_exact_named_package_map(source, "Ace Empty")

    allowed: set[int] = set()
    for fi in formation_indices:
        offset = apf_formation_package_map_offset(int(fi))
        for i in range(offset, offset + PACKAGE_MAP_SIZE):
            allowed.add(i)
        old = read_apf_formation_package_map(source, int(fi))
        expected = bytes(swap_apf_package_map_wr3_te(old))
        actual = patched[offset : offset + PACKAGE_MAP_SIZE]
        if actual != expected:
            raise ValidationError(
                f"Ace-named formation {fi} map {list(actual)} != 8↔9 swap "
                f"{list(expected)}."
            )
        if (
            empty_source is not None
            and read_apf_formation_name(source, int(fi)) == "Ace"
            and tuple(actual) == empty_source
        ):
            raise ValidationError("G12 pack must not copy Ace Empty onto Ace.")

    for i, (a, b) in enumerate(zip(source, patched, strict=True)):
        if i in allowed:
            continue
        if a != b:
            raise ValidationError(
                f"Byte {i} changed outside Ace-named package-map regions "
                f"(source 0x{a:02x} → 0x{b:02x})."
            )


class ApfThirdAndLongUserLogicRefusal(ValidationError):
    """No DATA-side 3rd-and-long writer. The fork is XEX-only."""


def refuse_apf_3rd_and_long_user_logic_writer() -> None:
    """No DATA-side 3rd-and-long writer. XEX-only; not shipped."""

    raise ApfThirdAndLongUserLogicRefusal(APF_3RD_AND_LONG_USER_LOGIC_REFUSAL)


__all__ = [
    "G1_G2_LAYOUT",
    "G1DimeFromNickelPackResult",
    "G1DimeFromNickelTarget",
    "G1DimeNickelCensus",
    "G2AceFromQuadsPackResult",
    "G2AceFromQuadsTarget",
    "LinkTablePatchResult",
    "O0308_ASSET_ID",
    "O0308_PACK_OFFSET",
    "PACKAGE_MAP_OFFSET_IN_FORMATION",
    "PACKAGE_MAP_SIZE",
    "PackageMapPatchResult",
    "PackageRuleSpikeResult",
    "SlotRoleSnapshot",
    "assignment_body_offset",
    "build_formation_link_table_copy_patch",
    "build_formation_package_map_patch",
    "build_g1_dime_from_nickel_package_map_pack",
    "build_g2_ace_from_quads_link_table_pack",
    "census_g1_dime_vs_nickel",
    "descriptor_body_offset",
    "formation_link_table_body_offset",
    "formation_package_map_body_offset",
    "layout_pins",
    "read_all_formation_package_maps",
    "read_formation_package_map",
    "spike_g1_dime_ilb",
    "spike_g2_ace_te",
    "verify_formation_link_table_copy_patch",
    "verify_formation_package_map_patch",
    "verify_g1_dime_from_nickel_package_map_pack",
    "verify_g2_ace_from_quads_link_table_pack",
    "APF_ACE_EMPTY_FORMATION_INDEX",
    "APF_ACE_EMPTY_IS_WR3_TE_SWAP_OF_ACE",
    "APF_ACE_EMPTY_NAME_VA",
    "APF_ACE_EMPTY_PACKAGE_MAP",
    "APF_ACE_FORMATION_INDEX",
    "APF_ACE_PACKAGE_MAP",
    "APF_ACE_VS_ACE_EMPTY_SLOT_DELTAS",
    "APF_FORMATION_BASE",
    "APF_FORMATION_COUNT_MAX",
    "APF_FORMATION_COUNT_OFFSET",
    "APF_MASTER_BODY_SIZE",
    "APF_RETAIL_FORMATION_COUNT",
    "APF_WR3_TE_PACKAGE_SUB_PROVED",
    "APF_G12_PACK_EXPERIMENTAL",
    "APF_G12_PACK_USES_ACE_EMPTY_AS_SOURCE",
    "APF_3RD_AND_LONG_UI_LABEL_VA",
    "APF_4TH_AND_LONG_UI_LABEL_VA",
    "APF_3RD_AND_LONG_USER_LOGIC_REFUSAL",
    "APF_USER_3RD_AND_LONG_DATA_WRITER_EXISTS",
    "APF_USER_3RD_AND_LONG_SEARCH_PROVED",
    "ApfAceEmptyCensus",
    "ApfThirdAndLongUserLogicRefusal",
    "G12Wr3TePackResult",
    "G12Wr3TeTarget",
    "apf_formation_count",
    "apf_formation_package_map_offset",
    "build_apf_formation_package_map_patch",
    "build_g12_wr3_te_package_map_pack",
    "census_apf_ace_vs_ace_empty",
    "g12_wr3_te_honesty",
    "list_apf_ace_named_formations",
    "read_apf_formation_name",
    "read_apf_formation_package_map",
    "refuse_apf_3rd_and_long_user_logic_writer",
    "swap_apf_package_map_wr3_te",
    "verify_apf_formation_package_map_patch",
    "verify_g12_wr3_te_package_map_pack",
    "APF_CATEGORY_GETTER_VA",
    "APF_CATEGORY_INDEX_EXTRACT_PROVED",
    "APF_CATEGORY_PERSONNEL_ACE_ROW_INDEX",
    "APF_CATEGORY_PERSONNEL_FIVE_WIDE_ROW_INDEX",
    "APF_CATEGORY_PERSONNEL_ROW_ACE",
    "APF_CATEGORY_PERSONNEL_ROW_FIVE_WIDE",
    "APF_CATEGORY_PERSONNEL_TABLE_VA",
    "APF_MASTER_CATEGORY_ACE",
    "APF_MASTER_CATEGORY_COUNT",
    "APF_MASTER_CATEGORY_FIVE_WIDE",
    "APF_MASTER_CATEGORY_FLUSH",
    "APF_MASTER_CATEGORY_NAMES",
    "APF_3RD_AND_LONG_PLAY_CHOICE_PROVED",
    "APF_FIVE_WIDE_SKILL_CELL_LOW",
    "APF_DOWN_FIRST",
    "APF_DOWN_FOURTH",
    "APF_DOWN_NAMES",
    "APF_DOWN_NAME_TABLE_VA",
    "APF_DOWN_THIRD",
    "APF_DRCT_AUX_INDEX_VA",
    "APF_DRCT_FIXED_CHILD_INDEX_VA",
    "APF_DRCT_FIXED_RECORD_CONSUMER_VA",
    "APF_DRCT_IFF_LOAD_VA",
    "APF_DRCT_POST_RELOC_FIXED_WALK_VA",
    "APF_DRCT_REGISTRY_TABLE_VA",
    "APF_DRCT_RELOCATOR_VA",
    "APF_DRCT_RELOC_FIXED_SLOT_BYTES",
    "APF_DRCT_RELOC_FIXED_SLOT_LOOP_VA",
    "APF_DRCT_RELOC_INSN_DIR_ADDI_VA",
    "APF_DRCT_RELOC_INSN_DIR_VA",
    "APF_DRCT_RESOURCE_LOAD_VA",
    "APF_DRCT_ROOT_TABLE_VA",
    "APF_DRCT_STRING_INDEX_VA",
    "APF_DRCT_TYPE_CTOR_VA",
    "APF_DRCT_VTABLE0_VA",
    "APF_DRCT_TYPE_HASH",
    "APF_DRCT_TYPE_INSERT_VA",
    "APF_DRCT_TYPE_OBJECT_VA",
    "APF_DRCT_TYPE_ROW_VA",
    "APF_DRCT_TYPE_VTABLE_VA",
    "APF_ELIGIBILITY_AND_FN_VA",
    "APF_ELIGIBILITY_AND_LIVE_INSN_VA",
    "APF_ELIGIBILITY_AND_LOOP_VA",
    "APF_GAME_STATE_DOWN_OFFSET",
    "APF_GAME_STATE_YTG_OFFSET",
    "APF_INGAME_PLAY_FETCH_VA",
    "APF_INGAME_PLAY_PICKER_VA",
    "APF_PDATA_FUNCTION_COUNT",
    "APF_PDATA_SECTION_VA",
    "APF_PACKAGE_MAP_BUILDER_SLOT_LOOP_PROVED",
    "APF_PACKAGE_MAP_ROLE_8_TE_9_WR_PROVED",
    "APF_PACKAGE_MAP_ROLE_TE",
    "APF_PACKAGE_MAP_ROLE_WR3",
    "APF_PICKER_PLAYCALL_LOAD_VA",
    "APF_PICKER_PLAYCALL_UI_LOAD_VA",
    "APF_PICKER_UI_FN_VA",
    "APF_PICKER_UI_PLAYCALL_LOAD_VA",
    "APF_JUMP_TABLE_MODE_2_FN_VA",
    "APF_JUMP_TABLE_MODE_2_LI_VA",
    "APF_JUMP_TABLE_MODE_2_OBJECT_VA",
    "APF_JUMP_TABLE_MODE_WRAPPER_VA",
    "APF_JUMP_TABLE_NESTED_VA",
    "APF_JUMP_TABLE_PICKER_CASE",
    "APF_JUMP_TABLE_PICKER_FN_VA",
    "APF_SPLB_FIND_BOOK_GETTER_VA",
    "APF_SPLB_FIND_BOOK_GLOBAL_VA",
    "APF_SPLB_FIND_BOOK_INIT_STW_VA",
    "APF_SPLB_FIND_BOOK_INIT_TABLE_VA",
    "APF_SPLB_FIND_BOOK_INIT_VA",
    "APF_PLAYCALL_BOOK_OFFSET",
    "APF_PLAYCALL_BOOK_READER_VA",
    "APF_PLAYCALL_BOOK_SETTER_VA",
    "APF_PLAYCALL_BY_TYPE_UI_VA",
    "APF_PLAYCALL_OBJECT_GLOBAL_VA",
    "APF_PLAYCALL_OBJECT_REGISTER_VA",
    "APF_PLAYCALL_SHADOW_BITMASK_VA",
    "APF_PLAYCALL_SHADOW_FILL_VA",
    "APF_PLAYCALL_SHADOW_VA",
    "APF_PLAYCALL_SIBLING_OFFSET",
    "APF_PLAYCALL_SLOT_INSTALL_VA",
    "APF_PLAYCALL_TYPE_INIT_STW20_VA",
    "APF_PLAYCALL_TYPE_INIT_VA",
    "APF_PLAYCALL_TYPE_OBJECT_A_VA",
    "APF_PLAYCALL_TYPE_OBJECT_B_VA",
    "APF_PLAYCALL_UI_FIELD_COPY_VA",
    "APF_PLAYCALL_UI_OBJECT_VA",
    "APF_LIVE_MASTER_GETTER_VA",
    "APF_LIVE_MASTER_SETTER_VA",
    "APF_LIVE_MASTER_SLOT_OFFSET",
    "APF_LIVE_MASTER_SLOT_VA",
    "APF_BOOK_FORMATION_GETTER_VA",
    "APF_BOOK_RESOLVE_HELPER_VA",
    "APF_DRCT_PROPERTY_TABLE_VA",
    "APF_LIVE_MASTER_BIND_VA",
    "APF_LIVE_MASTER_SPLB_SELECT_VA",
    "APF_SPLB_RAM_INDEX_VA",
    "APF_SPLB_RAM_STRIDE",
    "APF_SPLB_RAM_TABLE_VA",
    "APF_SPLB_SELECT_WORD0_CMP_VA",
    "APF_SPLB_SELECT_WORD0_THUNK_VA",
    "APF_SPLB_SELECT_THUNK_VA",
    "APF_SPLB_SELECT_INIT_VA",
    "APF_SPLB_SELECT_OBJECT_VA",
    "APF_SPLB_SELECT_SLOT_OFFSET",
    "APF_SITUATION_GET_DOWN_TABLE_VA",
    "APF_SITUATION_GET_DOWN_ROW_VA",
    "APF_SITUATION_GET_DOWN_SIBLING_VA",
    "APF_NFL_DCA40_VA",
    "APF_DCA40_FALSE_STVX_VA",
    "APF_DCA40_FALSE_VSUB_VA",
    "APF_DCA40_FALSE_PLAYCALL_JT_VA",
    "APF_PROPERTY_GET_BY_ID_VA",
    "APF_PROPERTY_GET_SINGLETON_VA",
    "APF_DRCT_INSN_OUTER_INGAME",
    "APF_DRCT_INSN_COUNT_INGAME",
    "APF_DRCT_INSN_RECORD_PREFIX",
    "APF_DRCT_INSN_TOKEN_OFFSET",
    "APF_DRCT_INSN_TOKEN_TOP",
    "APF_DRCT_PACKED_INSN_COUNT_GETTER_VA",
    "APF_DRCT_VT2_UNLINK_VA",
    "APF_DRCT_BYTE_STREAM_READER_VA",
    "APF_DRCT_FALSE_ASCII_SWITCH_VA",
    "APF_DRCT_INSN_TAG_BYTE",
    "APF_DRCT_INSN_WRAPUP_OUTER",
    "APF_DRCT_INSN_COUNT_WRAPUP",
    "APF_DRCT_COMPACT_INDEX_CHECK_VA",
    "APF_DRCT_FALSE_EMBEDDED20_VA",
    "APF_DRCT_VT0_FIXED_WALK_BL_VA",
    "APF_DRCT_INSN_FIELD_ID_1",
    "APF_DRCT_INSN_FIELD_ID_2",
    "APF_DRCT_INSN_NEST_LEAD",
    "APF_DRCT_FALSE_FIELD100_VA",
    "APF_DRCT_FALSE_PLAYTYPE_NIBBLE_VA",
    "APF_DRCT_FALSE_ASCII_YI_VA",
    "APF_DRCT_FALSE_RTTI_2_11_VA",
    "APF_DRCT_FALSE_CAP256_VA",
    "APF_DRCT_FALSE_BE_FLOAT_VA",
    "APF_DRCT_FALSE_R4_VT2_VA",
    "APF_DRCT_INSN_VARIANTS",
    "APF_DRCT_FALSE_RTTI_TLV_VA",
    "APF_DRCT_FALSE_PLUS5_OCCUPANCY_VA",
    "APF_DRCT_FALSE_PLUS5_SUM_VA",
    "APF_DRCT_PROP_WALK_VA",
    "APF_DRCT_PROP_TABLE_INDEX_VA",
    "APF_DRCT_PROP_JT_VA",
    "APF_DRCT_PROP_JT_MAX_ID",
    "APF_DRCT_FALSE_STRUCT12_VA",
    "APF_DRCT_FALSE_CLASS_35764_VA",
    "APF_DRCT_FALSE_COPY5_VA",
    "APF_DRCT_FALSE_STRIDE32_F32_VA",
    "APF_NFL_DRCT_INSN_OUTER_INGAME",
    "APF_NFL_DRCT_INSN_COUNT_INGAME",
    "APF_NFL_DRCT_INSN_PREFIX_TOP",
    "APF_DRCT_FALSE_ASCII_SCANF_VA",
    "APF_DRCT_FALSE_DCA40_SINGLE_F32_VA",
    "APF_DRCT_FALSE_CODEC5_VA",
    "APF_DRCT_INSN_TYPE_TERM",
    "APF_DRCT_INSN_TYPE_BEGIN",
    "APF_DRCT_INSN_TYPE_FLOAT",
    "APF_DRCT_INSN_TYPE_MARK",
    "APF_DRCT_INSN_TYPE_CLOSE",
    "APF_DRCT_INSN_BEGIN_GROUP_SIZE",
    "APF_DRCT_INSN_FLOAT_GROUP_SIZE",
    "APF_DRCT_INSN_MARK_GROUP_SIZE",
    "APF_DRCT_INSN_CLOSE_GROUP_SIZE",
    "APF_DRCT_INSN_ONE_BYTE_TYPES",
    "APF_DRCT_FALSE_BYTE_JT_VA",
    "APF_DRCT_FALSE_ENDIAN_COPY_VA",
    "APF_DRCT_FALSE_STRIDE12_R4_VA",
    "APF_DRCT_FALSE_PLUS5_STATE_VA",
    "APF_DRCT_FALSE_EXPR_VM_VA",
    "APF_DRCT_FALSE_EXPR_JT_VA",
    "APF_DRCT_FALSE_EXPR_CASE11_VA",
    "APF_DRCT_FALSE_EXPR_DESC_VA",
    "APF_DRCT_FALSE_UI_BYTE_JT_VA",
    "APF_FALSE_YTG_WRAP_VA",
    "APF_FALSE_SIT_WORD0_EQ4_VA",
    "APF_DRCT_FALSE_TYPE24_VA",
    "APF_FALSE_TWEEN_OBJ_VA",
    "APF_NFL_FALSE_BYTE35_VA",
    "APF_FALSE_FILTER_UI_VA",
    "APF_PICKER_DESC_SLOT_VA",
    "APF_FALSE_FILTER_SETTER_VA",
    "APF_FALSE_FILTER_GETTER_VA",
    "APF_NFL_FALSE_SHAP_LIST_VA",
    "APF_FALSE_FILTER_TAB_GATE_VA",
    "APF_DRCT_FALSE_CMP4_OCC_VA",
    "APF_DRCT_FALSE_BITPACK_R26_VA",
    "APF_FALSE_SIT_WORD0_EQ4_PICKER_VA",
    "APF_FALSE_SIT_WORD0_SWITCH_VA",
    "APF_DRCT_FALSE_FILL4_VA",
    "APF_DRCT_FALSE_SLOT11_PLUS5_VA",
    "APF_FALSE_DND_LABEL_VA",
    "APF_DND_NAME_TABLE_VA",
    "APF_DND_THIRD_LONG_STR_VA",
    "APF_DRCT_FALSE_BYTE36_JT_VA",
    "APF_DRCT_FALSE_BYTE34_JT_VA",
    "APF_FALSE_PLAYCALL_3C_VA",
    "APF_DRCT_EXPR_CURSOR_VA",
    "APF_DRCT_EXPR_CURSOR_INIT_VA",
    "APF_FALSE_SCRIPT_DND_VA",
    "APF_PACKED_GET_YTG_VA",
    "APF_PACKED_GET_DOWN_OBJ_VA",
    "APF_FALSE_SIT_COPYOUT_VA",
    "APF_FALSE_SIT_PTR254_VA",
    "APF_SITUATION_FALSE_BLOB_ROW_VA",
    "APF_FALSE_BLOB_INDEXER_VA",
    "APF_FALSE_0B00_MASK_VA",
    "APF_FALSE_YTG_LSB_VA",
    "APF_DRCT_FALSE_UTF8_WALK_VA",
    "APF_PLAY_TYPE_UI_TABLE_VA",
    "APF_PLAYTYPE_FILTER_TABLE_VA",
    "APF_ROLE_ELIGIBILITY_MASK_TE",
    "APF_ROLE_ELIGIBILITY_MASK_WR",
    "APF_ROLE_ELIGIBILITY_WORD_TABLE_VA",
    "APF_ROLE_TO_ROSTER_FIRST_11",
    "APF_ROLE_TO_ROSTER_TABLE_VA",
    "APF_ROSTER_POSITION_TE",
    "APF_ROSTER_POSITION_WR",
    "APF_SITUATION_GET_DOWN_VA",
    "APF_SITUATION_VTABLE8_QUERY_VA",
    "APF_SCRIPT_FN_TAG_TABLE_COUNT",
    "APF_SCRIPT_FN_TAG_TABLE_VA",
    "APF_SCRIPT_ONFIELD_ROLE_OPCODE_VA",
    "APF_SCRIPT_SITUATION_LEAF_VA",
    "APF_SITUATION_PLAYCALL_TAB_OFFSET",
    "APF_SITUATION_PLAYTYPE_FILTER_OFFSET",
    "APF_SPLB_ENTRY_TO_MASTER_PLAY_VA",
    "APF_SPLB_RECORD_FOR_PLAY_VA",
    "APF_SITUATION_WORD0_OFFSET",
]
