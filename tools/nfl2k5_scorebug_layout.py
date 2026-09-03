#!/usr/bin/env python3
"""Re-lay the NFL 2K5 field scorebug into one horizontal, ESPN-style bar (static, local, xemu-only).

What the retail bug is (outer 346 chunk 78 ``score_bug``, one shape, 286 NORMSHORT3 vertices,
11 material submeshes, 29 named transforms):

  transform            role                                   vertex group (material)
  T0  bug_skeleton     root; frame (yscore_buga/1), ESPN logo (zz_ESPN_bug/1)
  T1/T2 away_city      text anchor "TB"        (left-aligned)   -
  T3/T4 home_city      text anchor "AFC"       (left-aligned)   -
  T5/T6 Quarter        text anchor "1st"       (centred)        -
  T7-T10 Gameclock     text anchors "3:30"     (right-aligned)  -
  T11 drop_down        down & distance box + text               dscore_buga
  T13 drop_yellow      play-clock warning flash box             bscore_buga2
  T15 drop_clock       play-clock box + text                    cscore_buga
  T17 drop_ball_on     "Ball on ATL 30" box (child text T18)    bscore_buga1
  T19 drop_hangtime    punt hang-time box                       hscore_buga
  T21 drop_red         penalty box                              bscore_buga
  T23/T24 away_box/score  team-colour cell + away score text    zscore_buga
  T26/T27 home_box/score  team-colour cell + home score text    zscore_buga

Every vertex carries a matrix-palette index (register 1 SHORT1 = transform*3).  At runtime the
node matrices are reset to identity every frame (FUN_000FBBC0) and only the six "drop_*"
element records in the XBE (0xA959C8 + i*0x70) add animated offsets, so the visible layout is
the mesh-space vertex positions plus the transforms' serialized world positions for text.
Editing the vertices (int16, requantized against a new scale/offset at shape +0x10/+0x20) and
the transform positions (+0x40 world, +0x50 local) therefore re-lays the bug with no code.

The horizontal layout (mesh units, y up, bar body y -5.4..16.6):
  [ESPN] [AWAY city][away score] [HOME city][home score] [1st & 10] [Qtr] [clock] [:25]
Row 2 and the top strip of the retail frame are collapsed to zero height; the three boxes that
have no place on a modern bar (ball-on, hang time, penalty) are collapsed off-screen; the drop
animations are frozen by zeroing the element records' direction vectors.  The root is placed at
the bottom centre through the position patch, clear of the bottom ticker band.

Placement modes (FUN_000fc9c0 -> FUN_000fc700(mode) -> FUN_000fc200): the game keeps TWO copies
of the frame and of the ESPN mark and shows one pair per mode by exact node name (FUN_00030c40 is
wcscmp-equality): mode 0 shows ``yscore_buga`` + ``zz_ESPN_bug1``, mode 1 shows ``yscore_buga1`` +
``zz_ESPN_bug``; mode 2 is never selected (FUN_000fc700 has one caller).  The mode follows the
offense's drive direction, so v5 (which parked ``zz_ESPN_bug1`` off-screen) lost the mark on
every other drive.  v6 lays both copies identically.

Commands:
  preview  OUT.png                       mockup of the planned bar (approximate colours/font)
  scne     RETAIL.scne OUT.scne          write the edited decoded SCNE and test the fixed-span refit
  apply    SRC.xiso DST.xiso [--overwrite]  copy the disc, refit chunk 78, patch the XBE
                                         (element records + bottom-centre root position)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os


def _pread(fd: int, count: int, offset: int) -> bytes:
    """Positional read; Windows has no os.pread, so seek/read/restore there."""
    preader = getattr(os, "pread", None)
    if preader is not None:
        return preader(fd, count, offset)
    here = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, offset, os.SEEK_SET)
        return os.read(fd, count)
    finally:
        os.lseek(fd, here, os.SEEK_SET)


def _pwrite(fd: int, data: bytes, offset: int) -> int:
    """Positional write; Windows has no os.pwrite, so seek/write/restore there."""
    pwriter = getattr(os, "pwrite", None)
    if pwriter is not None:
        return pwriter(fd, data, offset)
    here = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, offset, os.SEEK_SET)
        return os.write(fd, data)
    finally:
        os.lseek(fd, here, os.SEEK_SET)
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import nfl_txtr  # noqa: E402
from mod_editor.core import nfl2k5_bump_strength as bs  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
import nfl2k5_scorebug_position_patch as sbpos  # noqa: E402

# ---- decoded SCNE layout (score_bug, 16,512 bytes) --------------------------------------
SCNE_SIZE = 16512
SCNE_SHA = "fc22e6caab35bc0f0b61d3a1014de9dfa0acfa6b8228fccf014f5ce0a17d1735"
SHAPE = 1856            # shape record; +0x10 float scale, +0x20 float3 offset
TBASE, TSTRIDE, TCOUNT = 4096, 0x70, 29
VCOUNT = 286
S0, S0_STRIDE = 0x2660, 6      # NORMSHORT3 position
S1, S1_STRIDE = 0x2D20, 10     # D3DCOLOR @0, NORMSHORT2 uv @4, SHORT1 palette index @8
SUBMESHES = [(0, 15, "bscore_buga"), (16, 31, "bscore_buga1"), (32, 47, "bscore_buga2"),
             (48, 63, "cscore_buga"), (64, 79, "dscore_buga"), (80, 95, "hscore_buga"),
             (96, 165, "yscore_buga"), (166, 229, "yscore_buga1"), (230, 261, "zscore_buga"),
             (262, 273, "zz_ESPN_bug"), (274, 285, "zz_ESPN_bug1")]
T = {"root": 0, "away_city": 1, "away_city_l": 2, "home_city": 3, "home_city_l": 4,
     "quarter": 5, "quarter_l": 6, "clock_a": 7, "clock_a_l": 8, "clock_b": 9, "clock_b_l": 10,
     "drop_down": 11, "drop_down_l": 12, "drop_yellow": 13, "drop_yellow_l": 14,
     "drop_clock": 15, "drop_clock_l": 16, "drop_ball_on": 17, "drop_ball_on_l": 18,
     "drop_hangtime": 19, "drop_hangtime_l": 20, "drop_red": 21, "drop_red_l": 22,
     "away_box": 23, "away_score": 24, "away_score_l": 25, "home_box": 26, "home_score": 27,
     "home_score_l": 28}

# ---- disc / XBE facts --------------------------------------------------------------------
PACK_PATH = "vc_53450030/0"
XISO_PACK_BYTE_OFFSET = 1_631_188_992     # audit: xiso_pack_byte_offset of vc_53450030/0
CHUNK78_PACK_OFFSET = 110_486_272         # outer 346 (pack offset 109,895,680) + chunk 590,592
SPAN_SIZE = 0x20 + 4800
SPAN_SHA = "3b1d7c8f0d5f3d6c1c6f0f0b8a8f8e5a3f4e9b2c7d6a5b4c3d2e1f0a9b8c7d6e"  # replaced at first read
ELEMENT_RECORDS = 0x00A959C8               # six 0x70 records; +0x18/+0x1C/+0x20 = direction xyz
ELEMENT_NAMES = ("drop_down", "drop_clock", "drop_hangtime", "drop_yellow", "drop_ball_on", "drop_red")
RETAIL_ELEMENT_DIR = struct.pack("<3f", 0.0, -1.0, 0.0)

# ---- the ESPN horizontal layout (mesh units) --------------------------------------------
BAR_LEFT, BAR_RIGHT = -240.0, 240.0        # frame body span (480 of the 640-unit HUD, TV-safe)
ROW_BOTTOM, ROW_TOP = -5.4, 16.6           # retail row-1 body, kept as the bar height
TEXT_Y, SCORE_Y = -2.5, -4.8               # retail baseline offsets inside a row
LAYOUT_VERSION = 6
# x ranges of the eight fields (the ESPN mark sits in MARK_BOX).  v6: the down & distance pill grew
# from 85 to 112 units so the widest strings the game emits ("1st & Goal", "4th & Inches":
# FUN_000fc7d0 formats "%s & %s" from 1st/2nd/3rd/4th and %d/Goal/Inches) fit with a margin; the
# team cells gave up 6 units each (three-letter abbreviations measure ~43 units, scores ~25).
CELLS = {
    "away_city": (-182.0, -132.0), "away_score": (-132.0, -98.0),
    "home_city": (-98.0, -48.0), "home_score": (-48.0, -14.0),
    "down": (-14.0, 98.0), "quarter": (98.0, 138.0), "clock": (138.0, 196.0),
    "playclock": (196.0, 236.0),
}
# v6: the ESPN mark keeps the retail two-triangle geometry (scaled into this box, white layer
# bounds) and the retail UVs.  The 128x64 shield_espn texture stores the logo wrapped in two rows
# and the triangle pair reassembles it; the replay overlay and the presentation overlays (the
# sideline-reporter cut-in among them) bind the same texture by name and draw it the same way,
# so the art must stay in the retail wrap and the bar must sample it like the other scenes do.
MARK_BOX = (-238.0, -4.6, -184.0, 16.2)
MARK_RETAIL_WHITE = ((-137.55, 7.37), (-3.12, 57.51))   # retail copy A white layer bounds (x, y)
MARK_COPY_B_SHIFT = 96.37                                # retail copy B = copy A shifted +x (same UVs)
# the team cells sample one atlas pixel.  Retail sampled a grey gradient (palette indices 43/148,
# 91..217 grey): they are plain grey boxes, not team-tinted.  v2 pointed them at a reserved white
# pixel and the game showed them pure white, hiding the white abbreviations and scores; v3 keeps
# the UV at the reserved block (62,62), which the atlas now paints slate.
TEAM_CELL_UV = (62.5 / 64.0 * 2.0 - 1.0, 62.5 / 64.0 * 2.0 - 1.0)
# In this scene smaller z is nearer the camera: the frame sits at 0, the ESPN mark at -2.5..-1,
# the team cells at -63..-61 (visible over the frame in game).  The retail drop boxes hide at +2
# behind the frame and slide out below it; a modern bar shows down & distance and the play clock
# permanently, so v3 parks those boxes in front of everything.
# v3 put the drop boxes' text at -66 and the ESPN mark vanished; v4 keeps everything within the
# retail depth band: text just in front of its box, boxes just in front of the frame, cells just in
# front of the frame and behind the city text, scores where retail keeps them (-59).
# v4 witness: box quads at -3 and their text at -4 rendered; cells moved to -1.5 vanished and took
# the scores (-59) and the city text (-3) with them, and the ESPN mark (-2.5..-1) has been missing
# since v3.  v5 uses only depths seen working: cells stay at retail -63..-61, scores at -59, the city
# text goes just in front of the cells, and the ESPN mark moves to the same front band.
FRONT_Z = -4.0      # text of the down / play-clock boxes (v4: rendered)
BOX_Z = -3.0        # the box quads themselves (v4: rendered)
CITY_Z = -64.0      # city abbreviations, in front of the cells (-63..-61)
MARK_Z = -64.0      # ESPN mark layer (v5: rendered); its drop shadow sits half a unit behind it
MARK_SHADOW_Z = -63.5

# The executable colours each text field for the retail panel it sat on: scores, quarter and the
# down box are opaque black (they sat on light grey), clock and cities are light grey.  On the
# charcoal bar the black fields vanish, so the copy gets them in the clock's light grey.
TEXT_COLOUR_SITES = {                 # .data VA -> (field, retail D3DCOLOR)
    0x00A958E4: ("quarter", 0xFF000000), 0x00A958E8: ("quarter shadow", 0xFF000000),
    0x00A95958: ("home score", 0xFF000000), 0x00A95990: ("away score", 0xFF000000),
    0x00A959D8: ("drop_down text", 0xFF000000), 0x00A95AB8: ("drop_hangtime text", 0xFF000000),
    0x00A95B28: ("drop_yellow text", 0xFF000000),
}
TEXT_COLOUR_NEW = 0xFFC0C0C0

# Persistent bug (Noah: "should stay mid play; only vanish for replays or full-screen graphics").
# FUN_000fc6b0 hides the bug (clears DAT_00a95524, the draw gate of FUN_000fc360, and the auto-hide
# timer flag DAT_00a957e0).  Its eleven callers, classified from the disassembly:
#   0xFC9F6  FUN_000fc9c0  play phase 10 (play call)               -> NOP (v5)
#   0xFCEC7  FUN_000fce70  timed show (FUN_000fc6c0) ran out        -> NOP (v5)
#   0x9FEAB  FUN_0009fe50  ball goes live / new carrier: hides unless the play type is 10
#                          (kickoff).  Called from FUN_0009ff80 (the snap: sets phase 0xE via
#                          FUN_000b6f30) and from 0xA0210 (possession change, e.g. the kick
#                          being fielded).  This is the mid-play hide            -> NOP (v6)
#   0xFC6D5  FUN_000fc6c0  "timed show" = flag + timer + this hide (the hide clears the flag,
#                          so the timer is dead code in retail).  Reached from FUN_000b9990
#                          (carrier update) via FUN_000a0ab0 whenever play+0x134 is set, which
#                          0xA0210's FUN_000b7050 does on a possession change   -> NOP (v6)
#   0x8BEA0  FUN_0008bea0  per frame while a replay or menu is up (FUN_0008c0c0)  keep
#   0xACAC3  FUN_000aca80  play-call overlay entry (time scale 0)                 keep
#   0x7DBAB  FUN_0007db80  option DAT_00e5ffe4 view toggle (FUN_0007d9d0)         keep
#   0xA29DC  FUN_000a2970  clock expiry / end of quarter (FUN_00157d40)           keep
#   0xA3097  FUN_000a2d40  camera state 0x1b = cut-scene                          keep
#   0x84098  cb_00084098   menu/overlay open (pair of FUN_00082e60's show)        keep
#   0xFCE4B  FUN_000fccd0  scene init                                             keep
# Replays additionally gate the draw through FUN_0008ab40 (cinematic players) in FUN_000fc360.
PERSIST_SITES = {                     # .text VA -> retail bytes of `call FUN_000fc6b0`
    0x000FC9F6: bytes.fromhex("e8b5fcffff"),   # FUN_000fc9c0: state 10 -> hide
    0x000FCEC7: bytes.fromhex("e8e4f7ffff"),   # FUN_000fce70: auto-hide timer expiry -> hide
    0x0009FEAB: bytes.fromhex("e800c80500"),   # FUN_0009fe50: ball live (snap / kick fielded) -> hide
    0x000FC6D5: bytes.fromhex("e8d6ffffff"),   # FUN_000fc6c0: possession-change "timed show" -> hide
}
OFFSCREEN = (-300.0, -150.0)
NEW_SCALE, NEW_OFFSET = 290.0, (-40.0, 0.0, -29.5)   # covers x -330..250, z -319..260
ROOT_X, ROOT_Y = 320.0, 424.0              # bar centred on a 640 screen; bottom edge at ~429
TICKER_TOP = 440.0


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Mesh:
    def __init__(self, data: bytes):
        if len(data) != SCNE_SIZE or sha(data) != SCNE_SHA:
            raise SystemExit(f"not the retail decoded score_bug SCNE ({len(data)} bytes, {sha(data)[:12]})")
        self.buf = bytearray(data)
        self.scale = struct.unpack_from("<f", data, SHAPE + 0x10)[0]
        self.offset = struct.unpack_from("<3f", data, SHAPE + 0x20)
        self.pos = []
        self.uv = []
        self.tindex = []
        for v in range(VCOUNT):
            q = struct.unpack_from("<3h", data, S0 + v * S0_STRIDE)
            self.pos.append([c / 32767.0 * self.scale + o for c, o in zip(q, self.offset)])
            u, vv = struct.unpack_from("<2h", data, S1 + v * S1_STRIDE + 4)
            self.uv.append((u / 32767.0, vv / 32767.0))
            self.tindex.append(struct.unpack_from("<h", data, S1 + v * S1_STRIDE + 8)[0] // 3)
        self.world = [list(struct.unpack_from("<3f", data, TBASE + i * TSTRIDE + 0x40)) for i in range(TCOUNT)]
        self.parent = [struct.unpack_from("<i", data, TBASE + i * TSTRIDE + 0x64)[0] for i in range(TCOUNT)]
        self.uv_edit: dict[int, tuple[float, float]] = {}   # vertex -> (u, v) in -1..1 to rewrite

    def material(self, v: int) -> str:
        for a, b, m in SUBMESHES:
            if a <= v <= b:
                return m
        raise IndexError(v)

    def group(self, v: int) -> tuple[int, str]:
        return self.tindex[v], self.material(v)

    def serialize(self) -> bytes:
        buf = bytearray(self.buf)
        struct.pack_into("<f", buf, SHAPE + 0x10, NEW_SCALE)
        struct.pack_into("<3f", buf, SHAPE + 0x20, *NEW_OFFSET)
        for v, p in enumerate(self.pos):
            q = []
            for c, o in zip(p, NEW_OFFSET):
                n = int(round((c - o) / NEW_SCALE * 32767.0))
                if not -32767 <= n <= 32767:
                    raise SystemExit(f"vertex {v} out of range after requantize: {p}")
                q.append(n)
            struct.pack_into("<3h", buf, S0 + v * S0_STRIDE, *q)
        for v, (u, vv) in self.uv_edit.items():
            struct.pack_into("<2h", buf, S1 + v * S1_STRIDE + 4, int(round(u * 32767.0)), int(round(vv * 32767.0)))
        for i in range(TCOUNT):
            w = self.world[i]
            p = self.parent[i]
            local = w if p < 0 else [a - b for a, b in zip(w, self.world[p])]
            struct.pack_into("<3f", buf, TBASE + i * TSTRIDE + 0x40, *w)
            struct.pack_into("<3f", buf, TBASE + i * TSTRIDE + 0x50, *local)
        return bytes(buf)


def _lin(x: float, a: float, b: float, c: float, d: float) -> float:
    return (x - a) / (b - a) * (d - c) + c


def espn_layout(m: Mesh) -> None:
    """Move vertices and text anchors into the horizontal bar (in place)."""

    xl = BAR_LEFT - (-107.3)   # shift for the left edge pieces
    xr = BAR_RIGHT - 62.5      # shift for the right edge pieces
    for v in range(VCOUNT):
        ti, mat = m.group(v)
        x, y, z = m.pos[v]
        if ti == 0 and mat in ("yscore_buga", "yscore_buga1"):
            if x <= -99.3 + 0.05:
                nx = x + xl
            elif x >= 54.5 - 0.05:
                nx = x + xr
            else:
                nx = _lin(x, -99.3, 54.5, -99.3 + xl, 54.5 + xr)
            ny = min(max(y, ROW_BOTTOM), ROW_TOP)
            m.pos[v] = [nx, ny, z]
        elif ti == 0 and 262 <= v <= 285:   # ESPN mark: both copies, retail triangles scaled into MARK_BOX
            # copy B (274..285, zz_ESPN_bug1, shown in mode 0) is copy A shifted +x in retail; both
            # land on the same spot so either placement mode shows the mark.  Retail UVs are kept.
            if v >= 274:                       # copy A (262..273) was placed earlier in this loop
                m.pos[v] = list(m.pos[v - 12])
                continue
            sx, sy = x, y
            (ax0, ay0), (ax1, ay1) = MARK_RETAIL_WHITE
            bx0, by0, bx1, by1 = MARK_BOX
            scale = min((bx1 - bx0) / (ax1 - ax0), (by1 - by0) / (ay1 - ay0))
            nx = bx0 + (sx - ax0) * scale
            ny = by0 + (sy - ay0) * scale
            shadow = (v - 262) % 12 <= 5      # retail colour 0x7f000000: the drop-shadow layer
            m.pos[v] = [nx, ny, MARK_SHADOW_Z if shadow else MARK_Z]
        elif ti == T["drop_down"]:
            a, b = CELLS["down"]
            m.pos[v] = [_lin(x, -103.1, 16.0, a, b), _lin(y, -24.2, 7.4, ROW_BOTTOM + 1.4, ROW_TOP - 1.6), BOX_Z]
        elif ti in (T["drop_yellow"], T["drop_clock"]):
            a, b = CELLS["playclock"]
            x0 = -3.8 if ti == T["drop_yellow"] else 16.0
            m.pos[v] = [_lin(x, x0, 58.7, a, b), _lin(y, -24.2, 7.4, ROW_BOTTOM + 1.4, ROW_TOP - 1.6), BOX_Z]
        elif ti in (T["drop_ball_on"], T["drop_hangtime"], T["drop_red"]):
            m.pos[v] = [OFFSCREEN[0], OFFSCREEN[1], z]
        elif ti == T["away_box"]:
            a, b = CELLS["away_city"][0], CELLS["away_score"][1]
            m.pos[v] = [_lin(x, -32.7, 2.4, a, b), _lin(y, -4.4, 16.1, ROW_BOTTOM, ROW_TOP), z]
            m.uv_edit[v] = TEAM_CELL_UV
        elif ti == T["home_box"]:
            a, b = CELLS["home_city"][0], CELLS["home_score"][1]
            m.pos[v] = [_lin(x, -32.7, 2.4, a, b), _lin(y, -26.1, -6.1, ROW_BOTTOM, ROW_TOP), z]
            m.uv_edit[v] = TEAM_CELL_UV
        else:
            raise SystemExit(f"unplaced vertex {v} group {ti} {mat}")

    def anchor(name: str, x: float, y: float, z: float | None = None) -> None:
        i = T[name]
        leaf = T.get(name + "_l")
        # the shadow/outline leaf keeps its retail offset from the text (scores: +10 z, i.e. behind
        # the glyphs); v2 collapsed it onto the text and the shadow z-fought the white digits
        delta = [b - a for a, b in zip(m.world[i], m.world[leaf])] if leaf is not None else None
        m.world[i] = [x, y, m.world[i][2] if z is None else z]
        if leaf is not None:
            m.world[leaf] = [a + d for a, d in zip(m.world[i], delta)]

    def center(cell: str) -> float:
        a, b = CELLS[cell]
        return (a + b) / 2

    anchor("away_city", CELLS["away_city"][0] + 4.0, TEXT_Y, CITY_Z)
    anchor("home_city", CELLS["home_city"][0] + 4.0, TEXT_Y, CITY_Z)
    anchor("quarter", center("quarter"), TEXT_Y)
    anchor("clock_a", CELLS["clock"][1] - 3.0, TEXT_Y)
    anchor("clock_b", CELLS["clock"][1] - 1.0, TEXT_Y)
    anchor("drop_down", center("down"), TEXT_Y, FRONT_Z)
    anchor("drop_yellow", center("playclock"), TEXT_Y, FRONT_Z)
    anchor("drop_clock", center("playclock"), TEXT_Y, FRONT_Z)
    for name in ("drop_ball_on", "drop_hangtime", "drop_red"):
        anchor(name, OFFSCREEN[0], OFFSCREEN[1])
    m.world[T["drop_ball_on_l"]] = [OFFSCREEN[0], OFFSCREEN[1], m.world[T["drop_ball_on_l"]][2]]
    anchor("away_box", center("away_city"), 5.9)
    anchor("away_score", center("away_score"), SCORE_Y)
    anchor("home_box", center("home_city"), 5.9)
    anchor("home_score", center("home_score"), SCORE_Y)


# ---- preview -------------------------------------------------------------------------------
COLOURS = {"yscore_buga": (38, 38, 46), "yscore_buga1": (38, 38, 46), "zz_ESPN_bug": (196, 26, 26),
           "zz_ESPN_bug1": (196, 26, 26), "dscore_buga": (208, 2, 27), "cscore_buga": (28, 28, 32),
           "bscore_buga2": (214, 180, 0), "zscore_buga": None, "bscore_buga1": (70, 70, 70),
           "hscore_buga": (70, 70, 70), "bscore_buga": (150, 30, 30)}
TEAM_AWAY, TEAM_HOME = (167, 25, 48), (0, 34, 68)


def strips() -> list[tuple[int, list[int]]]:
    g = json.loads((ROOT / "assets/intermediate/nfl2k5/models/0346_0078_score_bug.gltf").read_text())
    b = (ROOT / "assets/intermediate/nfl2k5/models/0346_0078_score_bug.bin").read_bytes()
    out = []
    for k, p in enumerate(g["meshes"][0]["primitives"]):
        acc = g["accessors"][p["indices"]]
        bv = g["bufferViews"][acc["bufferView"]]
        off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        idx = list(struct.unpack_from("<%dH" % acc["count"], b, off))
        out.append((k, idx))
    return out


WIDEST_SAMPLES = {"away_city": "WAS", "home_city": "NYG", "quarter": "OT2", "clock_a": "15:00",
                  "drop_down": "4th & Inches", "drop_clock": ":40", "away_score": "38", "home_score": "35"}


def _textured_triangle(im, tex, pts, uvs) -> None:
    """Paste ``tex`` onto ``im`` through the affine map that sends the three screen points to the
    three UV corners (-1..1 -> texture pixels); used to preview the wrapped ESPN mark."""

    from PIL import Image, ImageDraw
    w, h = tex.size
    px = [((u + 1.0) / 2.0 * w, (v + 1.0) / 2.0 * h) for u, v in uvs]
    (x0, y0), (x1, y1), (x2, y2) = pts
    (u0, v0), (u1, v1), (u2, v2) = px
    det = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    if abs(det) < 1e-6:
        return
    # solve u = a*x + b*y + c, v = d*x + e*y + f
    a = ((u1 - u0) * (y2 - y0) - (u2 - u0) * (y1 - y0)) / det
    b = ((u2 - u0) * (x1 - x0) - (u1 - u0) * (x2 - x0)) / det
    c = u0 - a * x0 - b * y0
    d = ((v1 - v0) * (y2 - y0) - (v2 - v0) * (y1 - y0)) / det
    e = ((v2 - v0) * (x1 - x0) - (v1 - v0) * (x2 - x0)) / det
    f = v0 - d * x0 - e * y0
    warped = tex.transform(im.size, Image.AFFINE, (a, b, c, d, e, f), resample=Image.BILINEAR)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).polygon([(x0, y0), (x1, y1), (x2, y2)], fill=255)
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    layer.paste(warped, (0, 0), mask)
    im.alpha_composite(layer)


def preview(m: Mesh, path: Path, *, scale: int = 2, widest: bool = False) -> None:
    """Mockup of the bar; ``widest`` substitutes the longest strings the game emits per field."""

    from PIL import Image, ImageDraw, ImageFont

    W, H = 640 * scale, 480 * scale
    im = Image.new("RGBA", (W, H), (34, 92, 40, 255))
    dr = ImageDraw.Draw(im, "RGBA")
    dr.rectangle([0, int(TICKER_TOP) * scale, W, H], fill=(20, 20, 20, 160))
    dr.text((8 * scale, (TICKER_TOP + 12) * scale), "ticker band (reserved)", fill=(200, 200, 200, 255))

    def sp(v: int) -> tuple[float, float]:
        x, y, _ = m.pos[v]
        return ((ROOT_X + x) * scale, (ROOT_Y - y) * scale)

    order = {"zscore_buga": 0, "yscore_buga": 1, "yscore_buga1": 1, "zz_ESPN_bug": 2, "zz_ESPN_bug1": 2,
             "dscore_buga": 3, "bscore_buga2": 3, "cscore_buga": 4}
    tris = []
    for k, idx in strips():
        mat = SUBMESHES[k][2]
        for i in range(len(idx) - 2):
            a, b, c = idx[i], idx[i + 1], idx[i + 2]
            if a == b or b == c or a == c:
                continue
            tris.append((order.get(mat, 5), mat, (a, b, c)))
    mark_png = ESPN_TEXTURES / "shield_espn_modern.png"
    mark_tex = Image.open(mark_png).convert("RGBA") if mark_png.exists() else None
    for _, mat, (a, b, c) in sorted(tris, key=lambda t: t[0]):
        col = COLOURS.get(mat)
        if col is None:
            col = TEAM_AWAY if m.tindex[a] == T["away_box"] else TEAM_HOME
        if any(m.pos[v][0] <= OFFSCREEN[0] + 1 for v in (a, b, c)):
            continue
        if mat.startswith("zz_ESPN_bug") and mark_tex is not None and (a - 262) % 12 >= 6:
            _textured_triangle(im, mark_tex, [sp(v) for v in (a, b, c)], [m.uv[v] for v in (a, b, c)])
            continue
        if mat.startswith("zz_ESPN_bug") and mark_tex is not None:
            continue      # the shadow layer is not previewed
        dr.polygon([sp(a), sp(b), sp(c)], fill=col + (255,))
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 9 * scale)
    except OSError:
        font = ImageFont.load_default()
    samples = {"away_city": ("ATL", "l"), "home_city": ("KC", "l"), "quarter": ("4th", "c"),
               "clock_a": ("2:00", "r"), "drop_down": ("1st & 10", "c"), "drop_clock": (":25", "c"),
               "away_score": ("21", "c"), "home_score": ("17", "c")}
    for name, (text, align) in samples.items():
        if widest:
            text = WIDEST_SAMPLES.get(name, text)
        x, y, _ = m.world[T[name]]
        px, py = (ROOT_X + x) * scale, (ROOT_Y - y) * scale
        w = dr.textlength(text, font=font)
        if align == "c":
            px -= w / 2
        elif align == "r":
            px -= w
        dr.text((px, py - 11 * scale), text, fill=(240, 240, 240, 255), font=font)
    if mark_tex is None:
        ex, ey = (MARK_BOX[0] + MARK_BOX[2]) / 2, (MARK_BOX[1] + MARK_BOX[3]) / 2
        dr.text(((ROOT_X + ex) * scale - 14 * scale, (ROOT_Y - ey) * scale - 6 * scale), "ESPN",
                fill=(255, 255, 255, 255), font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(path)


# ---- disc -----------------------------------------------------------------------------------
def refit(template_span: bytes, decoded: bytes) -> tuple[bytes, object]:
    """Refit with the wrapper kept byte-identical (no raised scratch word): the retail loader
    places the stored body at decoded_size + scratch - stored_size, so the stream is filled to
    the retail span instead of zero-padded (see tools/nfl_vc_lz_fill.py)."""

    import nfl_vc_lz_fill
    span, info = nfl_vc_lz_fill.rebuild_fixed_span_filled(template_span, decoded)
    chunks = nfl_txtr.parse_chunks(span, allow_trailing=True)
    back, _ = nfl_txtr.decode_chunk(span, chunks[0])
    if back != decoded or len(span) != len(template_span) or span[:0x20] != template_span[:0x20]:
        raise SystemExit("fixed-span refit did not round-trip with a retail wrapper")
    return span, info


def read_retail_span(xiso: Path) -> tuple[int, bytes]:
    absolute = XISO_PACK_BYTE_OFFSET + CHUNK78_PACK_OFFSET
    with xiso.open("rb") as f:
        f.seek(absolute)
        span = f.read(SPAN_SIZE)
    chunks = nfl_txtr.parse_chunks(span, allow_trailing=True)
    decoded, _ = nfl_txtr.decode_chunk(span, chunks[0])
    if sha(decoded) != SCNE_SHA:
        raise SystemExit(f"disc chunk 78 at {absolute:#x} is not the retail score_bug (decoded {sha(decoded)[:12]})")
    return absolute, span


def patch_text_colours(payload: bytes) -> tuple[bytes, list[dict]]:
    """Recolour the black scorebug text fields light grey (verified retail bytes first)."""

    buf = bytearray(payload)
    edits = []
    for va, (field, retail) in sorted(TEXT_COLOUR_SITES.items()):
        off = sbpos.va_to_off(payload, va)
        have = struct.unpack_from("<I", payload, off)[0]
        if have == TEXT_COLOUR_NEW:
            edits.append({"field": field, "va": f"{va:#x}", "state": "already"})
            continue
        if have != retail:
            raise SystemExit(f"text colour for {field} at {va:#x} is neither retail nor patched: {have:#010x}")
        struct.pack_into("<I", buf, off, TEXT_COLOUR_NEW)
        edits.append({"field": field, "va": f"{va:#x}", "colour": f"{retail:#010x} -> {TEXT_COLOUR_NEW:#010x}"})
    return bytes(buf), edits


def patch_persistent(payload: bytes) -> tuple[bytes, list[dict]]:
    """NOP the two calls that hide the bug during the play / after the timed show."""

    buf = bytearray(payload)
    edits = []
    for va, retail in sorted(PERSIST_SITES.items()):
        off = sbpos.va_to_off(payload, va)
        have = payload[off: off + 5]
        if have == b"\x90" * 5:
            edits.append({"va": f"{va:#x}", "state": "already"})
            continue
        if have != retail:
            raise SystemExit(f"hide call at {va:#x} is neither retail nor patched: {have.hex()}")
        buf[off: off + 5] = b"\x90" * 5
        edits.append({"va": f"{va:#x}", "call": "FUN_000fc6b0 -> nop5"})
    return bytes(buf), edits


def patch_xbe(payload: bytes, *, freeze_elements: bool, persistent: bool = True) -> tuple[bytes, dict]:
    patched, receipt = sbpos.apply(payload, ROOT_X, ROOT_Y)
    buf = bytearray(patched)
    sections = bs._sections(patched)
    edits = []
    touched = set()
    recoloured, colour_edits = patch_text_colours(patched)
    if recoloured != patched:
        buf = bytearray(recoloured)
        for va in TEXT_COLOUR_SITES:
            touched.add(bs._section_for_offset(sections, sbpos.va_to_off(patched, va)).index)
    receipt["text_colours"] = colour_edits
    if persistent:
        persisted, persist_edits = patch_persistent(bytes(buf))
        if persisted != bytes(buf):
            buf = bytearray(persisted)
            for va in PERSIST_SITES:
                touched.add(bs._section_for_offset(sections, sbpos.va_to_off(patched, va)).index)
        receipt["persistent"] = persist_edits
    # HUD neighbours of the bar: the kick meter is lifted clear of y 400..440 and the pre-snap lineup
    # strip (which drew across the bar) is switched off (mod_editor.core.nfl2k5_hud_layout).
    from mod_editor.core import nfl2k5_hud_layout as hud
    hud_state = hud.status(bytes(buf))
    wants_margin = hud_state["kick_meter_margin"] == "retail"
    wants_lineup = hud_state["lineup_insert"] == "retail"
    # kick_meter_margin reads 'retail', the applied margin as text (e.g. '150.0'), or 'foreign'
    if hud_state["kick_meter_margin"] == "foreign" or hud_state["lineup_insert"] not in ("retail", "off"):
        raise SystemExit(f"HUD layout sites are neither retail nor patched: {hud_state}")
    if wants_margin or wants_lineup:
        moved, hud_receipt = hud.apply(bytes(buf), kick_margin=hud.DEFAULT_KICK_MARGIN if wants_margin else None,
                                       lineup_insert_off=wants_lineup)
        buf = bytearray(moved)
        for va in (hud.KICK_MARGIN_SITE_VA, hud.LINEUP_GATE_VA):
            touched.add(bs._section_for_offset(sections, sbpos.va_to_off(patched, va)).index)
        receipt["hud_layout"] = dict(hud_receipt)
    else:
        receipt["hud_layout"] = {"already_applied": True, **hud_state}
    for i, name in enumerate(ELEMENT_NAMES if freeze_elements else ()):
        va = ELEMENT_RECORDS + i * 0x70 + 0x18
        off = sbpos.va_to_off(patched, va)
        if patched[off: off + 12] != RETAIL_ELEMENT_DIR:
            raise SystemExit(f"element record {i} ({name}) direction is not retail: {patched[off: off + 12].hex()}")
        buf[off: off + 12] = struct.pack("<3f", 0.0, 0.0, 0.0)
        touched.add(bs._section_for_offset(sections, off).index)
        edits.append({"element": name, "va": f"{va:#x}", "direction": "0,-1,0 -> 0,0,0"})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = bs.section_digest(bytes(buf), section)
    receipt["element_records"] = edits
    return bytes(buf), receipt


ESPN_TEXTURES = ROOT / "mod_editor" / "assets" / "nfl2k5_scorebug_espn"


def status(xiso: Path) -> str:
    """'retail' (chunk 78 + placement untouched), 'applied' (this layout), or 'foreign'."""

    try:
        fd = os.open(xiso, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    except OSError:
        return "foreign"
    try:
        size = os.fstat(fd).st_size
        absolute = XISO_PACK_BYTE_OFFSET + CHUNK78_PACK_OFFSET
        if absolute + SPAN_SIZE > size:
            return "foreign"
        span = _pread(fd, SPAN_SIZE, absolute)
        try:
            chunks = nfl_txtr.parse_chunks(span, allow_trailing=True)
            decoded, _ = nfl_txtr.decode_chunk(span, chunks[0])
        except Exception:  # noqa: BLE001
            return "foreign"
        xoff, xlen = tt.image_xbe_extent(fd, size)
        xbe = _pread(fd, xlen, xoff)
    finally:
        os.close(fd)
    edited = Mesh(retail_scne_bytes()) if sha(decoded) == SCNE_SHA else None
    if edited is not None:
        # chunk is retail; the placement must be retail too
        try:
            sbpos.apply(xbe, ROOT_X, ROOT_Y)
        except SystemExit:
            return "foreign"
        return "retail"
    m = Mesh(retail_scne_bytes())
    espn_layout(m)
    if decoded == m.serialize():
        return "applied"
    return "foreign"


def retail_scne_bytes() -> bytes:
    for candidate in (ESPN_TEXTURES / "score_bug_retail.scne", Path("/tmp/opencode/scorebug/score_bug.scne")):
        if candidate.exists():
            data = candidate.read_bytes()
            if sha(data) == SCNE_SHA:
                return data
    raise SystemExit("retail decoded score_bug SCNE not found")


def apply_in_place(xiso: Path, *, textures: bool = True, freeze_elements: bool = True) -> dict:
    """Re-lay the scorebug inside an existing (already copied) image: chunk 78, XBE, textures."""

    absolute, span = read_retail_span(xiso)
    m = Mesh(retail_scne_bytes())
    espn_layout(m)
    decoded = m.serialize()
    new_span, info = refit(span, decoded)
    fd = os.open(xiso, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        size = os.fstat(fd).st_size
        xoff, xlen = tt.image_xbe_extent(fd, size)
        xbe = _pread(fd, xlen, xoff)
        new_xbe, receipt = patch_xbe(xbe, freeze_elements=freeze_elements)
        _pwrite(fd, new_span, absolute)
        _pwrite(fd, new_xbe, xoff)
        os.fsync(fd)
    finally:
        os.close(fd)
    receipt.update({"chunk78_absolute": absolute, "filled_bytes": info.filled_bytes, "padding_bytes": info.padding_bytes, "wrapper_identical": info.wrapper_identical,
                    "root": [ROOT_X, ROOT_Y], "layout": f"espn-horizontal-v{LAYOUT_VERSION}", "textures": []})
    if textures:
        import subprocess
        argv = [sys.executable, str(ROOT / "tools" / "nfl2k5_scorebug_textures_into_xiso.py"), str(xiso),
                "--score-buga", str(ESPN_TEXTURES / "score_buga_modern.png"),
                "--shield-espn", str(ESPN_TEXTURES / "shield_espn_modern.png")]
        font_png = ESPN_TEXTURES / "digital_font_modern.png"
        if font_png.exists():
            argv += ["--digital-font", str(font_png)]
        done = subprocess.run(argv, capture_output=True, text=True, check=False)
        if done.returncode != 0:
            raise SystemExit(f"texture import failed: {done.stderr[-400:]}")
        receipt["textures"] = ["score_buga", "shield_espn"] + (["digital_font"] if font_png.exists() else [])
        ticker_png = ESPN_TEXTURES / "NAVTEXTURE_modern.png"
        if ticker_png.exists():
            argv = [sys.executable, str(ROOT / "tools" / "nfl2k5_fieldpack_texture_into_xiso.py"), str(xiso),
                    "--chunk", "34", "--png", str(ticker_png)]
            done = subprocess.run(argv, capture_output=True, text=True, check=False)
            if done.returncode != 0:
                raise SystemExit(f"ticker atlas import failed: {done.stderr[-400:]}")
            receipt["textures"].append("NAVTEXTURE")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preview"); p.add_argument("out"); p.add_argument("--retail", action="store_true")
    p.add_argument("--widest", action="store_true", help="use the widest strings per field (4th & Inches, 15:00, OT2)")
    s = sub.add_parser("scne"); s.add_argument("retail_scne"); s.add_argument("out_scne"); s.add_argument("--span")
    a = sub.add_parser("apply"); a.add_argument("source"); a.add_argument("target"); a.add_argument("--overwrite", action="store_true")
    a.add_argument("--keep-drop-animation", action="store_true")
    args = ap.parse_args()

    if args.cmd == "preview":
        m = Mesh(retail_scne_bytes())
        if not args.retail:
            espn_layout(m)
        preview(m, Path(args.out), widest=args.widest)
        print(f"wrote {args.out}")
        return 0
    if args.cmd == "scne":
        m = Mesh(Path(args.retail_scne).read_bytes())
        espn_layout(m)
        out = m.serialize()
        Path(args.out_scne).write_bytes(out)
        print(f"edited SCNE {len(out)} bytes sha {sha(out)[:16]}")
        if args.span:
            span = Path(args.span).read_bytes()
            new_span, info = refit(span, out)
            print("refit OK:", {k: getattr(info, k) for k in ("filled_bytes", "padding_bytes", "stored_size", "scratch_bytes", "wrapper_identical")})
        return 0
    src, dst = Path(args.source), Path(args.target)
    if dst.exists() and not args.overwrite:
        raise SystemExit(f"{dst} exists (use --overwrite)")
    absolute, span = read_retail_span(src)
    m = Mesh(retail_scne_bytes())
    espn_layout(m)
    decoded = m.serialize()
    new_span, info = refit(span, decoded)
    print("refit:", {k: getattr(info, k) for k in ("filled_bytes", "padding_bytes", "stored_size", "scratch_bytes", "wrapper_identical")})
    # XBE inside the image
    fd = os.open(src, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        size = os.fstat(fd).st_size
        xoff, xlen = tt.image_xbe_extent(fd, size)
        xbe = _pread(fd, xlen, xoff)
    finally:
        os.close(fd)
    new_xbe, receipt = patch_xbe(xbe, freeze_elements=not args.keep_drop_animation)
    print(f"copying {src.name} -> {dst.name} ...", flush=True)
    shutil.copyfile(src, dst)
    fd = os.open(dst, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        if _pread(fd, SPAN_SIZE, absolute) != span:
            raise SystemExit("copy does not hold the retail span")
        _pwrite(fd, new_span, absolute)
        _pwrite(fd, new_xbe, xoff)
        os.fsync(fd)
    finally:
        os.close(fd)
    receipt.update({"chunk78_absolute": absolute, "span_sha256_before": sha(span), "span_sha256_after": sha(new_span),
                    "decoded_sha256_after": sha(decoded), "xbe_sha256_after": sha(new_xbe),
                    "root": [ROOT_X, ROOT_Y], "layout": f"espn-horizontal-v{LAYOUT_VERSION}"})
    print(json.dumps(receipt, indent=1)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
