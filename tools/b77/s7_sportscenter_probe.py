#!/usr/bin/env python3
"""Native emulation of the SportsCenter playoff screens on a real NFL 2K5 ``default.xbe``.

Job S7 (beta 77).  The 76.5 / v0.5 disc already carried the 9/5 seven-seed Playoff Picture work, yet
SportsCenter still looked like the old twelve-team playoffs.  This probe runs the *actual executable
instructions* of every SportsCenter routine that talks about the playoffs under Unicorn, on a synthetic
final-week seven-seed league, and prints exactly what each one produces:

* ``show_playoff_picture``: the field builder ``0x220960`` (both conferences), the focus selector
  ``0x220AE0``, the narration classifier ``0x220FE0`` and its predicates, the overlay formatter
  ``0x220C50`` running against the *real widget keys and positions* decoded from the disc's
  ``FRANCHISE_SHOW.IFF`` scene (so the printed screen shows which cell carries which text);
* the show banner ``0x2CD430`` (round titles) and the primetime card's "NEXT WEEK" override
  ``0x2641C0`` for every last-played week from the first postseason week back to week 15.

Only the league data layer (team list, standings, records, comparator) and the scene service calls are
replaced by hooks; every decision and every string copy is the game's own code.  Nothing here claims what
the game draws on a television: the output is "the text the game's own code would store in each widget".

Usage::

    python3 tools/b77/s7_sportscenter_probe.py --xbe default.xbe [--weeks 18] [--json out.json]
        [--scene-mrks show_playoff_picture.mrks]

The scene resource is optional.  Without it the widget keys come from the XBE's descriptor table and the
positions are left out.  Run it niced and one at a time (it takes a few seconds and ~100 MB).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_season_length as season  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections  # noqa: E402

# ----------------------------------------------------------------------------------------------
# constants taken from the executable (all virtual addresses)
# ----------------------------------------------------------------------------------------------
STACK_VA = 0x07F00000
SENTINEL = 0x00ABCD00
TEAMS_VA = 0x00D00000
TEAM_STRIDE = 0x300
STRINGS_VA = 0x00D40000          # scratch area for synthetic wide strings
SCENE_VA = 0x00D50000            # synthetic widget scene (header + 0x90-byte widgets)
CONF_BUFFER_VA = (0x00C146B0, 0x00C146D0)   # AFC, NFC eight-slot field buffers
CONF_PTR_VA = 0x00C146A0                      # active conference buffer pointer
FOCUS_TEAM_VA = 0x00C146A8
FOCUS_RANK_VA = 0x00C146AC
OVERLAY_SCENE_VA = 0x00C14388                 # show_playoff_picture scene pointer
DESCRIPTOR_TABLE_VA = 0x0050F8E0              # 41 x (key, kind, rank)
DESCRIPTOR_COUNT = 41
STAGE_VA = 0x00E576A4
STAGE_WEEKS_VA = 0x00E576B0                   # regular-season row count (17 retail, 18 with season_length)
CONFERENCE_OF_DIVISION = (1, 1, 1, 1, 0, 0, 0, 0)   # divisions 0-3 NFC, 4-7 AFC

FN = {
    "team_count": 0x000C6430, "team_at": 0x000C4C50, "team_conf": 0x000C4250, "team_div": 0x000C42C0,
    "compare": 0x002A7C00, "wins": 0x000C7720, "losses": 0x000C7750, "ties": 0x000C7780,
    "clinch_level": 0x00133CE0, "rng": 0x00048B50, "last_played": 0x0015DF10, "set_text": 0x001513D0,
    "scene_reset": 0x0002DE60, "printf": 0x0004A400,
    "builder": 0x00220960, "selector": 0x00220AE0, "overlay": 0x00220C50, "classifier": 0x00220FE0,
    "division_of_focus": 0x002210C0, "tied_conf": 0x002210D0, "tied_div": 0x00221160, "spot": 0x002211F0,
    "is_nfc": 0x00221200, "bubble_gap": 0x00221220, "title": 0x002CD430, "primetime": 0x002641C0,
}


class ProbeError(RuntimeError):
    pass


def wide_bytes(text: str) -> bytes:
    return (text + "\0").encode("utf-16le")


class Emu:
    """A Unicorn image of the executable with address hooks (fastcall/stdcall aware)."""

    def __init__(self, xbe: bytes):
        try:
            from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, Uc
        except ImportError as exc:  # pragma: no cover - environment guard
            raise ProbeError("the unicorn package is required") from exc
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.uc.mem_map(0, 0x01600000)
        self.uc.mem_map(STACK_VA, 0x100000)
        for section in _sections(xbe):
            if section.raw_size:
                self.uc.mem_write(section.virtual_address,
                                  xbe[section.raw_offset:section.raw_offset + section.raw_size])
        self.uc.mem_write(SENTINEL, b"\xc3")
        self.hooks: dict[int, object] = {}
        self.trace: list[tuple[str, tuple]] = []
        self.uc.hook_add(UC_HOOK_CODE, self._on_code)

    # -- plumbing -------------------------------------------------------------------------
    def _on_code(self, _uc, address, _size, _user):
        fn = self.hooks.get(address)
        if fn is not None:
            fn()

    def reg(self, name):
        from unicorn import x86_const as c
        return self.uc.reg_read(getattr(c, "UC_X86_REG_" + name.upper()))

    def setreg(self, name, value):
        from unicorn import x86_const as c
        self.uc.reg_write(getattr(c, "UC_X86_REG_" + name.upper()), value & 0xFFFFFFFF)

    def u32(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def put32(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def stack_arg(self, index):
        return self.u32(self.reg("esp") + 4 + 4 * index)

    def wide(self, va, limit=256):
        data = bytearray()
        for i in range(limit):
            word = bytes(self.uc.mem_read(va + 2 * i, 2))
            if word == b"\0\0":
                break
            data.extend(word)
        return data.decode("utf-16le", "replace")

    def ret(self, value=None, pops=0):
        if value is not None:
            self.setreg("eax", value)
        esp = self.reg("esp")
        self.setreg("eip", self.u32(esp))
        self.setreg("esp", esp + 4 + pops)

    def call(self, entry, *, ecx=0, edx=0, args=(), until=SENTINEL, budget=300_000):
        sp = STACK_VA + 0x80000
        self.uc.mem_write(sp, struct.pack("<" + "I" * (1 + len(args)), SENTINEL, *args))
        for reg, value in (("esp", sp), ("ecx", ecx), ("edx", edx), ("eax", 0), ("ebx", 0), ("esi", 0), ("edi", 0),
                           ("ebp", 0)):
            self.setreg(reg, value)
        self.uc.emu_start(entry, until, count=budget, timeout=5_000_000)
        if self.reg("eip") != until:
            raise ProbeError(f"instruction budget exhausted in {entry:#x} (eip {self.reg('eip'):#x})")
        return self.reg("eax")


# ----------------------------------------------------------------------------------------------
# the synthetic league
# ----------------------------------------------------------------------------------------------
class League:
    """32 teams.  Wins are distinct inside each conference so the seeding is unambiguous."""

    def __init__(self, emu: Emu, weeks_played: int, *, seed_variant: int = 0):
        self.emu = emu
        self.weeks_played = weeks_played
        self.division = {t: t // 4 for t in range(32)}
        self.name = {t: f"T{t:02d}" for t in range(32)}
        # record table: AFC/NFC get descending win totals along a fixed permutation so that a wild-card team
        # beats one division winner (the NFL still seeds division winners first)
        perm = {0: [3, 9, 14, 7, 1, 12, 5, 10, 2, 15, 8, 0, 13, 6, 11, 4],
                1: [5, 0, 11, 8, 2, 14, 7, 1, 12, 9, 4, 15, 10, 3, 13, 6]}[seed_variant % 2]
        self.wins, self.losses, self.ties = {}, {}, {}
        for conf in (0, 1):
            teams = [t for t in range(32) if self.conf(t) == conf]
            for rank, idx in enumerate(perm):
                team = teams[idx]
                wins18 = 16 - rank // 2 if rank < 12 else 4 - (rank - 12)      # an 18-game record
                ties = 1 if rank in (3, 4) else 0
                scale = weeks_played / 18.0
                wins = max(0, min(round(wins18 * scale), weeks_played - ties))
                self.wins[team] = wins
                self.ties[team] = ties if weeks_played else 0
                self.losses[team] = weeks_played - wins - self.ties[team]
        self.level = {}        # team -> clinch level (0..4)
        self._install()

    def conf(self, team):
        return CONFERENCE_OF_DIVISION[self.division[team]]

    def ptr(self, team):
        return TEAMS_VA + team * TEAM_STRIDE

    def team(self, ptr):
        return (ptr - TEAMS_VA) // TEAM_STRIDE

    def points(self, team):
        return self.wins[team] * 2 + self.ties[team]

    def key(self, team):
        return (self.points(team), -team)

    def better(self, a, b):
        return self.key(a) > self.key(b)

    # expected NFL seeding from the model (the oracle for the builder under test)
    def seeds(self, conf):
        winners = []
        for div in range(8):
            if CONFERENCE_OF_DIVISION[div] == conf:
                winners.append(max((t for t in range(32) if self.division[t] == div), key=self.key))
        winners.sort(key=self.key, reverse=True)
        rest = sorted((t for t in range(32) if self.conf(t) == conf and t not in winners), key=self.key, reverse=True)
        return winners + rest[:4]            # seeds 1-4 division winners, 5-7 wild cards, [7] first team out

    def set_final_flags(self, field_size=7):
        """Clinch flags at the end of the regular season under the seven-team bracket levels 4/2/1."""
        mem = self.emu.uc.mem_write
        for team in range(32):
            mem(self.ptr(team) + 0x1EA, bytes(4))
            self.level[team] = 0
        for conf in (0, 1):
            order = self.seeds(conf)
            for i, team in enumerate(order[:field_size]):
                level = 4 if i == 0 else 2 if i < 4 else 1
                self.level[team] = level
                week = max(self.weeks_played, 1)
                flags = [week if level >= 1 else 0, week if level >= 2 else 0, week if level >= 3 else 0,
                         week if level >= 4 else 0]
                mem(self.ptr(team) + 0x1EA, bytes(flags))

    def _install(self):
        emu = self.emu
        emu.uc.mem_write(TEAMS_VA, bytes(32 * TEAM_STRIDE))
        for team in range(32):
            name_va = STRINGS_VA + team * 0x40
            emu.uc.mem_write(name_va, wide_bytes(self.name[team]))
            base = self.ptr(team)
            emu.put32(base + 0x104, name_va)           # display name
            emu.put32(base + 0x108, name_va)           # abbreviation (helmet texture name)
            emu.put32(base + 0x10C, name_va)
            emu.uc.mem_write(base + 0x192, bytes([0]))
        emu.put32(STAGE_VA, 8)                          # franchise regular season
        emu.put32(STAGE_WEEKS_VA, 18)

        def team_count():
            emu.ret(32)

        def team_at():
            idx = emu.reg("ecx")
            emu.ret(self.ptr(idx) if idx < 32 else 0)

        def team_conf():
            emu.ret(self.conf(self.team(emu.reg("ecx"))))

        def team_div():
            emu.ret(self.division[self.team(emu.reg("ecx"))])

        def compare():
            a, b = self.team(emu.reg("ecx")), self.team(emu.reg("edx"))
            emu.ret(1 if self.better(a, b) else 0)

        def wins():
            emu.ret(self.wins[self.team(emu.reg("ecx"))])

        def losses():
            emu.ret(self.losses[self.team(emu.reg("ecx"))])

        def ties():
            emu.ret(self.ties[self.team(emu.reg("ecx"))])

        def clinch():
            emu.ret(self.level.get(self.team(emu.reg("ecx")), 0))

        for key, fn in (("team_count", team_count), ("team_at", team_at), ("team_conf", team_conf),
                        ("team_div", team_div), ("compare", compare), ("wins", wins), ("losses", losses),
                        ("ties", ties), ("clinch_level", clinch)):
            emu.hooks[FN[key]] = fn
        emu.hooks[FN["last_played"]] = lambda: emu.ret(self.weeks_played - 1)


# ----------------------------------------------------------------------------------------------
# scene widgets
# ----------------------------------------------------------------------------------------------
class Scene:
    """A runtime-shaped scene: [scene+4] = count, [scene+8] = array of 0x90-byte widgets with the key at
    +0x80, a static-text flag (0x10) at +0x74 and the static text pointer at +0x84."""

    def __init__(self, emu: Emu, widgets, base=SCENE_VA):
        self.emu, self.base = emu, base
        self.widgets = widgets            # list of dicts: key, x, y, static (str|None), label
        self.array = base + 0x100
        emu.uc.mem_write(base, bytes(0x100 + 0x90 * len(widgets) + 0x2000))
        emu.put32(base + 4, len(widgets))
        emu.put32(base + 8, self.array)
        text_va = base + 0x100 + 0x90 * len(widgets)
        for i, widget in enumerate(widgets):
            at = self.array + 0x90 * i
            emu.put32(at + 0x80, widget["key"])
            if widget.get("static") is not None:
                emu.uc.mem_write(text_va, wide_bytes(widget["static"]))
                emu.put32(at + 0x84, text_va)
                emu.uc.mem_write(at + 0x74, bytes([0x10]))
                text_va += 2 * (len(widget["static"]) + 1)
            widget["index"] = i
        self.by_addr = {self.array + 0x90 * i: w for i, w in enumerate(widgets)}
        self.text = {}                    # key -> last text stored by the game's setText

    def install_set_text(self):
        emu = self.emu

        def set_text():
            addr = emu.reg("ecx")
            widget = self.by_addr.get(addr)
            if widget is None:
                return emu.ret(0)
            if emu.uc.mem_read(addr + 0x74, 1)[0] & 0x10 and emu.u32(addr + 0x84):
                text = emu.wide(emu.u32(addr + 0x84))            # static widget keeps its own text
                widget["ignored"] = emu.wide(emu.reg("edx"))
            else:
                text = emu.wide(emu.reg("edx"))
            self.text[widget["key"]] = text
            emu.ret(0)

        emu.hooks[FN["set_text"]] = set_text


def install_printf(emu: Emu):
    """swprintf-like 0x4A400: ecx = destination, edx = format, one stack argument = pointer to the values."""
    def printf():
        dest, fmt_va = emu.reg("ecx"), emu.reg("edx")
        argp = emu.stack_arg(0)                                  # pointer to the argument block (a va_list)
        fmt = emu.wide(fmt_va)
        out, arg = "", 0
        i = 0
        while i < len(fmt):
            if fmt[i] == "%" and i + 1 < len(fmt):
                spec = fmt[i + 1]
                if spec == "d":
                    word = struct.unpack("<i", emu.uc.mem_read(argp + 4 * arg, 4))[0]
                    out += str(word)
                    arg += 1
                i += 2
                continue
            out += fmt[i]
            i += 1
        emu.uc.mem_write(dest, wide_bytes(out))
        emu.ret(0, pops=4)
    emu.hooks[FN["printf"]] = printf


# ----------------------------------------------------------------------------------------------
# decoding the real scene (optional)
# ----------------------------------------------------------------------------------------------
def decode_mrks_widgets(raw: bytes):
    """Return the text widget records of a presentation MRKS: key, x, y, static text (or None)."""
    pool = {}
    widgets = []
    for off in range(0, len(raw) - 0x90, 4):
        if struct.unpack_from("<II", raw, off + 8) == (0x005E13E0, 0x00683110):
            key = struct.unpack_from("<I", raw, off)[0]
            rel = struct.unpack_from("<i", raw, off + 4)[0]
            x, y = struct.unpack_from("<2f", raw, off + 0x50)
            static = None
            if rel:
                target = off + 3 + rel
                if 0 <= target < len(raw) - 2:
                    end = target
                    while end + 2 <= len(raw) and raw[end:end + 2] != b"\0\0":
                        end += 2
                    static = raw[target:end].decode("utf-16le", "replace")
            widgets.append({"key": key, "x": round(x, 2), "y": round(y, 2), "static": static, "offset": off})
            pool[key] = widgets[-1]
    return widgets


def descriptor_widgets(emu: Emu):
    """Fallback scene: just the 41 dynamic widgets named by the executable's own descriptor table."""
    widgets = []
    for i in range(DESCRIPTOR_COUNT):
        key, kind, rank = struct.unpack("<III", emu.uc.mem_read(DESCRIPTOR_TABLE_VA + 12 * i, 12))
        widgets.append({"key": key, "x": None, "y": None, "static": None, "kind": kind, "rank": rank})
    return widgets


# ----------------------------------------------------------------------------------------------
# the probes
# ----------------------------------------------------------------------------------------------
KIND_NAMES = {0: "name", 1: "wins", 2: "losses", 3: "ties", 4: "status", 5: "bubble sticker"}


def probe_picture(xbe: bytes, weeks: int, mrks: bytes | None, *, played: int | None = None):
    """Run the playoff-picture pipeline on a seven-seed league.

    ``weeks`` is the regular-season length (17 or 18).  ``played`` is how many weeks are complete (default: all of
    them, the final picture shown before the playoffs, with every clinch flag set); a smaller number gives a
    mid-season picture with no clinch flags yet.
    """
    played = weeks if played is None else played
    emu = Emu(xbe)
    league = League(emu, weeks_played=played)
    emu.put32(STAGE_WEEKS_VA, weeks)
    if played >= weeks:
        league.set_final_flags()
    install_printf(emu)
    emu.hooks[FN["scene_reset"]] = lambda: emu.ret(1)
    result = {"xbe_sha256": hashlib.sha256(xbe).hexdigest(), "weeks": weeks, "weeks_played": played,
              "conferences": {}}

    descriptor = {}
    for i in range(DESCRIPTOR_COUNT):
        key, kind, rank = struct.unpack("<III", emu.uc.mem_read(DESCRIPTOR_TABLE_VA + 12 * i, 12))
        descriptor[key] = (kind, rank)
    result["descriptor"] = [{"key": f"{k:#010x}", "kind": KIND_NAMES.get(v[0], v[0]), "rank": v[1]}
                            for k, v in descriptor.items()]

    for conf in (0, 1):
        buf = CONF_BUFFER_VA[conf]
        emu.uc.mem_write(buf, bytes(0x20))
        emu.setreg("ebx", buf)
        # the builder is called with ebx = buffer and the conference as its stack argument
        sp = STACK_VA + 0x80000
        emu.uc.mem_write(sp, struct.pack("<II", SENTINEL, conf))
        for reg, value in (("esp", sp), ("ebx", buf), ("ecx", 0), ("edx", 0), ("esi", 0), ("edi", 0), ("ebp", 0)):
            emu.setreg(reg, value)
        emu.uc.emu_start(FN["builder"], SENTINEL, count=400_000)
        teams = struct.unpack("<8I", emu.uc.mem_read(buf, 32))
        built = [league.team(p) for p in teams]
        expected = league.seeds(conf)
        entry = {"buffer_va": hex(buf), "field": built, "expected_seven_plus_one": expected,
                 "builder_matches_model": built == expected}
        result["conferences"][conf] = entry

        # selector: which focus teams can occur (random remainder 0..9)
        emu.hooks[0x000CEE10] = lambda: emu.ret(0)
        emu.hooks[0x00067DF0] = lambda: emu.ret(0)
        pool = []
        for r in range(10):
            emu.hooks[FN["rng"]] = (lambda value: (lambda: emu.ret(value)))(r)
            emu.setreg("ecx", buf)
            sp = STACK_VA + 0x80000
            emu.uc.mem_write(sp, struct.pack("<I", SENTINEL))
            emu.setreg("esp", sp)
            emu.setreg("ecx", buf)
            emu.uc.emu_start(FN["selector"], SENTINEL, count=100_000)
            pool.append(emu.u32(FOCUS_RANK_VA))
        entry["selector_rank_pool"] = sorted(set(pool))
        entry["selector_modulus"] = len(set(pool))

        # classifier and predicates for every rank
        rows = []
        emu.put32(CONF_PTR_VA, buf)
        for rank in range(8):
            emu.put32(FOCUS_TEAM_VA, teams[rank])
            emu.put32(FOCUS_RANK_VA, rank)
            case = emu.call(FN["classifier"])
            rows.append({"rank": rank, "team": built[rank], "wins": league.wins[built[rank]],
                         "losses": league.losses[built[rank]], "ties": league.ties[built[rank]],
                         "flags": [int(b) for b in emu.uc.mem_read(teams[rank] + 0x1EA, 4)],
                         "narration_case": case, "spot": emu.call(FN["spot"]),
                         "is_nfc": emu.call(FN["is_nfc"])})
        entry["ranks"] = rows

    # the overlay formatter against the real widget keys/positions
    if mrks is not None:
        widgets = decode_mrks_widgets(mrks)
    else:
        widgets = descriptor_widgets(emu)
    for conf in (0, 1):
        buf = CONF_BUFFER_VA[conf]
        scene = Scene(emu, [dict(w) for w in widgets])
        scene.install_set_text()
        emu.put32(OVERLAY_SCENE_VA, scene.base)
        emu.put32(CONF_PTR_VA, buf)
        teams = struct.unpack("<8I", emu.uc.mem_read(buf, 32))
        emu.put32(FOCUS_TEAM_VA, teams[0])
        emu.put32(FOCUS_RANK_VA, 0)
        emu.call(FN["overlay"])
        cells = []
        for w in scene.widgets:
            text = scene.text.get(w["key"], w.get("static") or "")
            kind_rank = descriptor.get(w["key"])
            cells.append({"key": f"{w['key']:#010x}", "x": w["x"], "y": w["y"], "static": w.get("static"),
                          "dynamic": kind_rank is not None,
                          "kind": KIND_NAMES.get(kind_rank[0]) if kind_rank else None,
                          "rank": kind_rank[1] if kind_rank else None,
                          "text": text, "game_text_ignored": w.get("ignored")})
        result["conferences"][conf]["overlay_cells"] = cells
    return result


def probe_title(xbe: bytes, weeks: int):
    """The show banner 0x2CD430: its three text lines for every last-played week."""
    out = []
    for last_played in range(weeks - 3, weeks + 6):
        emu = Emu(xbe)
        install_printf(emu)
        emu.hooks[FN["last_played"]] = lambda lp=last_played: emu.ret(lp)
        keys = (0x2402E113, 0x9AEDE3D4, 0xBB8F6FE1)
        scene = Scene(emu, [{"key": k, "x": 0, "y": 0, "static": None} for k in keys], base=0x00D60000)
        scene.install_set_text()
        emu.put32(0x00C8E7F0, scene.base)
        emu.put32(0x00C8E7F4, scene.base)          # non-zero root pointer
        emu.put32(0x00C8E7F8, 0)
        emu.hooks[0x0002DE30] = lambda: emu.ret(0, pops=4)     # stdcall(root, table, buffer)
        emu.hooks[0x0002AC80] = lambda: emu.ret(0)
        emu.hooks[0x0002DE60] = lambda: emu.ret(1)
        emu.call(FN["title"], budget=500_000)
        out.append({"last_played_index": last_played, "weeks_played": last_played + 1,
                    "line_1": scene.text.get(0x9AEDE3D4), "line_2": scene.text.get(0x2402E113),
                    "single_line": scene.text.get(0xBB8F6FE1)})
    return out


def probe_primetime_override(xbe: bytes, weeks: int):
    """The primetime card's NEXT WEEK override (the 'Playoffs' / 'Season Begins' pointer at 0x2641C0)."""
    out = []
    for stage, last_played in [(8, lp) for lp in range(weeks - 3, weeks + 2)] + [(7, 4)]:
        emu = Emu(xbe)
        emu.put32(STAGE_VA, stage)
        emu.put32(STAGE_WEEKS_VA, weeks)
        emu.hooks[FN["last_played"]] = lambda lp=last_played: emu.ret(lp)
        emu.put32(0x00C39AC4, 0x00D70000)          # non-zero scene
        emu.hooks[0x000C4E00] = lambda: emu.ret(0)
        emu.hooks[0x000C4E20] = lambda: emu.ret(0)
        emu.hooks[0x000C5C00] = lambda: emu.ret(0x00D71000)
        sp = STACK_VA + 0x80000
        emu.uc.mem_write(sp, struct.pack("<I", SENTINEL))
        for reg, value in (("esp", sp), ("ecx", 0), ("edx", 0), ("esi", 0), ("edi", 0), ("ebp", 0), ("ebx", 0)):
            emu.setreg(reg, value)
        emu.uc.emu_start(FN["primetime"], 0x00264252, count=100_000)
        override = emu.u32(emu.reg("esp") + 0x14)
        out.append({"stage": stage, "last_played_index": last_played,
                    "next_week_text": emu.wide(override) if override else "(none: shows the next matchup)"})
    return out


def probe_teaser(xbe: bytes, weeks: int):
    """SportsCenter menu teaser FUN_002cf4b0: the line offered after N weeks played, for every random draw."""
    out = []
    for played in range(10, weeks + 4):
        texts, types = [], set()
        for draw in range(3):
            emu = Emu(xbe)
            install_printf(emu)
            emu.hooks[FN["last_played"]] = lambda lp=played - 1: emu.ret(lp)
            emu.hooks[FN["rng"]] = lambda d=draw: emu.ret(d)                  # cdecl: the caller's pushed type stays
            seen = []

            def teaser_text(seen=seen, emu=emu):
                seen.append((emu.wide(emu.stack_arg(0)), emu.stack_arg(1)))
                emu.ret(1, pops=8)                                              # stdcall(text, type)
            emu.hooks[0x002CEB60] = teaser_text
            emu.call(0x002CF4B0, budget=100_000)
            texts.extend(t for t, _ in seen)
            types.update(k for _, k in seen)
        out.append({"weeks_played": played, "teaser_types": sorted(types), "lines": sorted(set(texts))})
    return out


def probe_idle_label(xbe: bytes, weeks: int):
    """FUN_0024c8a0: the label of a team with no game in a given row (bye / idle in a round)."""
    out = []
    for row in range(weeks - 2, weeks + 5):
        for stage in (8, 9):
            emu = Emu(xbe)
            emu.put32(STAGE_VA, stage)
            emu.hooks[0x000C6920] = lambda: emu.ret(0xFFFF)
            ptr = emu.call(0x0024C8A0, ecx=0, edx=row)
            out.append({"row": row, "week": row + 1, "stage": stage, "label": emu.wide(ptr)})
    return out


def probe_week_header(xbe: bytes, weeks: int):
    """FUN_00358bf0 dispatch (the by-week schedule browser header): which label its jump table selects per row."""
    from unicorn import UC_HOOK_CODE
    cases = {0x00358C9E: "Wildcard", 0x00358CD1: "Division Championship", 0x00358D04: "Conference Championship",
             0x00358D3C: "Super Bowl", 0x00358D6C: "Pro Bowl", 0x00358D9C: "Week N"}
    out = []
    for row in range(weeks - 2, weeks + 6):
        emu = Emu(xbe)
        emu.put32(0x00CBFAF8, row)
        hit = []
        for va, name in cases.items():
            emu.hooks[va] = lambda n=name: (hit.append(n), emu.uc.emu_stop())
        sp = STACK_VA + 0x80000
        for reg, value in (("esp", sp), ("ecx", 0), ("edx", 0), ("eax", 0), ("esi", 0), ("edi", 0), ("ebp", 0)):
            emu.setreg(reg, value)
        emu.uc.emu_start(0x00358C85, SENTINEL, count=1000)
        out.append({"row": row, "week": row + 1, "header": hit[0] if hit else "(none)"})
    return out


def render_screen(cells, conf_label):
    """A plain-text sketch of the picture: rows sorted by y (largest first), columns by x."""
    rows = {}
    for c in cells:
        if c["x"] is None or not c["text"]:
            continue
        rows.setdefault(c["y"], []).append(c)
    lines = [f"--- {conf_label}: each row is one y value in the scene; columns left to right ---"]
    for y in sorted(rows, reverse=True):
        parts = []
        for c in sorted(rows[y], key=lambda c: c["x"]):
            tag = "" if c["dynamic"] else "*"
            parts.append(f"[{c['text']}{tag}]")
        lines.append(f"y={y:8.2f}  " + " ".join(parts))
    lines.append("(* = static widget text from the scene resource; the others are filled by the game's code)")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--weeks", type=int, default=18, help="regular-season length (17 or 18)")
    parser.add_argument("--played", type=int, help="weeks completed for the picture (default: all, i.e. the final picture)")
    parser.add_argument("--scene-mrks", type=Path, help="decoded show_playoff_picture MRKS resource")
    parser.add_argument("--json", type=Path, help="write the result here (new file)")
    args = parser.parse_args(argv)
    fd = os.open(args.xbe, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as handle:
        xbe = handle.read()
    mrks = None
    if args.scene_mrks:
        fd = os.open(args.scene_mrks, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        with os.fdopen(fd, "rb") as handle:
            mrks = handle.read()
    picture = probe_picture(xbe, args.weeks, mrks, played=args.played)
    result = {"picture": picture, "title": probe_title(xbe, args.weeks),
              "primetime_next_week": probe_primetime_override(xbe, args.weeks),
              "menu_teaser": probe_teaser(xbe, args.weeks), "idle_team_label": probe_idle_label(xbe, args.weeks),
              "week_browser_header": probe_week_header(xbe, args.weeks)}
    for conf, label in ((0, "AFC"), (1, "NFC")):
        entry = picture["conferences"][conf]
        print(f"{label}: builder field {entry['field']}  model {entry['expected_seven_plus_one']}  "
              f"match={entry['builder_matches_model']}  selector ranks {entry['selector_rank_pool']}")
        for row in entry["ranks"]:
            print(f"   rank {row['rank']} team {row['team']:2d}  flags {row['flags']}  narration case "
                  f"{row['narration_case']}  spot {row['spot']}")
        if "overlay_cells" in entry:
            print(render_screen(entry["overlay_cells"], label))
    print("show banner by last-played week:")
    for row in result["title"]:
        print("  ", row)
    print("primetime NEXT WEEK line:")
    for row in result["primetime_next_week"]:
        print("  ", row)
    for key in ("menu_teaser", "idle_team_label", "week_browser_header"):
        print(key + ":")
        for row in result[key]:
            print("  ", row)
    if args.json:
        fd = os.open(args.json, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
