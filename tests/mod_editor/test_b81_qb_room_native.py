"""The quarterback room page (beta 81 piece 3): module API, the real linked page in Unicorn, retail call sites.

Every Unicorn case installs page_bytes() at 0x1529000 and enters it through the installed 5-byte call at its retail
site inside the whole executable (retail plus the depth-lock and returner owners, as the depth-lock tests build it),
and compares with the same league entered through the retail call bytes (the old code). Only the native rating
(0x246D80, 0x246A80: the float at player +0x36, as the depth-lock tests stub it) and the club record getters
(0xC7720/0xC7750/0xC7780: a table per club) are stubbed, at their real addresses and with their real conventions.
The club accessor 0xC4C50, the season stat getter 0x14EE40, the standard depth swap 0x242CA0 and the weekly sort
0x2BDCF0 run as retail/standard code.

Retail facts this file relies on (capstone disassembly of the USA retail default.xbe, checked in RetailFacts):
- Weekly advance 0x247D40 (EBP = menu context from 0x247D50): 0x247D5C call 0x2BDCF0 (auto depth); per-club copy loop
  through 0xC4C50; 0x247DCA call 0x2BE020 (injured-reserve pass; site of opening_entry); stage switch through
  0x247AA0; trades 0x2BC960 and games 0xC7CB0 by stage; 0x248010 call 0x323870 (signings, ECX = EBP); 0x24801D
  week + 1 (0xC4E60); 0x248030..0x248073 per club payroll 0xC3F00 and cut 0x2BFBE0; 0x248075 call 0x2BDCF0;
  0x24807A call 0x27EB80 (site of room_entry), then pop edi/esi/ebp/ebx, mov esp,ebp, pop ebp, ret.
- 0x2BE020 begins `push ecx` (a local slot it zeroes at 0x2BE03C before reading) and `call 0xC4BB0`; 0x27EB80 begins
  `sub esp,8`. Neither reads a register or stack argument from its caller and both end in a plain ret, so a stub
  that restores every register and EFLAGS and jumps with the original return address on the stack is transparent.
- 0xC7720/0xC7750/0xC7780 (wins/losses/ties): ECX = club pointer -> EAX; push ebx/esi/edi, walk 22 weeks of the
  schedule grid through 0xC75A0/0xC7620/0xC76A0 (reads only; the one local is their own pushed ECX slot); ECX and
  EDX clobbered.
- 0x14EE40 (season stat): ECX = player, EDX = field -> EAX = movsx word (0 if absent); ESI saved; EDX becomes the
  player's years pro (+0x25 & 31); 0x14E800 walks the player's list at [+0x2C] and matches bit 29 of each word
  against [0xBD7F98] (0 = regular season); it writes nothing.
- 0x246D80 (native sort rating): `push edx; movzx edx,[ecx+0x35]; call 0x246D60; ret`; 0x246D60 ends `ret 4`,
  0x246C00 `ret 8`: ECX = player, EDX = 1 in, one float in ST0 out, EBX/ESI/EDI/EBP preserved, EAX/ECX/EDX
  clobbered; it clamps to 0..1.
- 0xC4C50 (club at index): mode [0xE576A0] 0 -> [root+0x1C] + 500 * index if index < [root+0x18]; other modes ->
  [0xE5786C + 4 * index]; 0 if none. 0x13EC30 = jmp 0xC4D50: the human flag [0xE5775C + 4 * index] (index found
  by 0xC4CA0), which room.c reads directly.
- 0x242CA0 retail exchanges only the row bits (+0x28 & 0x1C00, EAX = 0); the standard depth-lock owner's version
  (nfl2k5_depth_locks screen_swap) also sets bit 0 of +0x52 on both (`or [ecx+0x52],al; or [esi+0x52],al`).
"""
from __future__ import annotations

from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest

from mod_editor.core import nfl2k5_qb_room_code as room
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_bytes

VA = 0x1529000
OPENING_SITE, ROOM_SITE = 0x247DCA, 0x24807A
OPENING_TARGET, ROOM_TARGET = 0x2BE020, 0x27EB80
ROOT, CLUBS, COACHES, FIX = 0x2000000, 0x2010000, 0x2020000, 0x2030000
PLAYERS, STATS = 0x2100000, 0x2200000
STACK, STOP = 0x3008000, 0x3100000
CLUB_SIZE, PLAYER_SIZE, COACH_SIZE = 500, 0x54, 0xA8
LEAGUE_CLUBS = 34                       # 32 league clubs and the two all-star sides
GENERATORS = ((0xB12680, 448), (0xE5FCA0, 448))
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# ---- Python reference of the rules (DESIGN 2.2 to 2.8), written from the design, not from room.c ----------------
def fmix32(h):
    h ^= h >> 16
    h = h * 0x85EBCA6B & 0xFFFFFFFF
    h ^= h >> 13
    h = h * 0xC2B2AE35 & 0xFFFFFFFF
    return h ^ h >> 16


def draw(words):
    h = 0x51425233
    for word in words:
        h = fmix32(h ^ (word & 0xFFFFFFFF))
    return h % 100000


def tdiv(a, b):
    """C division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def rating10(att, cmp, yds, td, ints):
    if att <= 0:
        return 0
    clamp = lambda v: max(0, min(2375, v))
    a = clamp((tdiv(cmp * 1000, att) - 300) * 5)
    b = clamp(tdiv(tdiv(yds * 1000, att) - 3000, 4))
    c = clamp(tdiv(td * 20000, att))
    e = clamp(2375 - tdiv(ints * 25000, att))
    return (a + b + c + e) // 6


def coach1000(leadership):
    return 1350 - 600 * (min(99, max(61, leadership)) - 61) // 38


def overall(value):
    return int(struct.unpack("<f", struct.pack("<f", value))[0] * 100 + .5)


# The design's tables as written (hundredths / millionths), and the integer chain of 2.8.
FORM = ((650, 160), (750, 130), (850, 100), (950, 45), (None, 12))
RECORD = {-1: 10, 0: 50, 1: 100, 5: 170}
D2_BASE = {-1: 4000, 0: 12000, 1: 35000, 2: 70000, 3: 100000, 4: 130000, 5: 160000}


def form_of(r10):
    return next(value for limit, value in FORM if limit is None or r10 < limit)


def record_of(d):
    return RECORD[-1] if d <= -1 else RECORD[0] if d == 0 else RECORD[1] if d <= 4 else RECORD[5]


def gapf_of(gap):
    return 150 if gap <= 5 else 100 if gap <= 10 else 50 if gap <= 15 else 15


def d3_threshold(h0, r10, d, g, gap, coach):
    p = h0
    for factor in (form_of(r10), record_of(d), 60 if g <= 3 else 100, gapf_of(gap)):
        p = p * factor // 100
    return p * coach // 1000 // 10


def d2_threshold(d, g, coach, scale=1000):
    p = D2_BASE[max(-1, min(5, d))] * scale // 1000
    p = p * (50 if g == 1 else 100 if g <= 7 else 30) // 100
    return p * coach // 1000 // 10


# ---- module interface -------------------------------------------------------------------------------------------
class PageInterface(unittest.TestCase):
    def test_settings_record_layout_and_refusals(self):
        record = room.settings_record(room.STAGE_D1 | room.STAGE_D4, shadow=True, h0_ppm=12345, d2_scale_milli=900)
        self.assertEqual(record, struct.pack("<8sIIIIII", b"QBROOMv1", 1, 5, 1, 12345, 900, 0))
        self.assertEqual(room.settings_record(0), struct.pack("<8sIIIIII", b"QBROOMv1", 1, 0, 0, 15000, 1000, 0))
        self.assertEqual((room.H0_PPM, room.D2_SCALE_MILLI), (15000, 1000))
        self.assertEqual(room.parse_settings(record), {"mode": 1, "stages": 5, "shadow": True, "h0_ppm": 12345,
                                                       "d2_scale_milli": 900})
        for bad in ({"stages": 32}, {"stages": -1}, {"stages": True}, {"stages": 1, "shadow": 1},
                    {"stages": 1, "h0_ppm": 1_000_001}, {"stages": 1, "d2_scale_milli": -1},
                    {"stages": 1, "h0_ppm": 1.5}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                room.settings_record(**bad)
        for bad in (record[:31], b"QBROOMv2" + record[8:], record[:8] + b"\2" + record[9:],
                    record[:28] + b"\1\0\0\0"):
            with self.subTest(record=bad.hex()), self.assertRaises(ValueError):
                room.parse_settings(bad)

    def test_page_layout_relocation_and_sites(self):
        settings = room.settings_record(7)
        page = room.page_bytes(VA, settings, ir_store_va=0x14FD6D0)
        self.assertEqual(len(page), room.PAGE_SIZE)
        self.assertEqual(page[0x2000:0x2020], settings)
        self.assertEqual(page[0x2020:0x2040], struct.pack("<I", 0x14FD6D0) + bytes(28))
        self.assertEqual(page[0x2040:], bytes(0x1000 - 0x40))
        self.assertLess(room.CODE_BYTES, 0x2000)
        self.assertEqual(page[room.CODE_BYTES:0x2000], b"\xcc" * (0x2000 - room.CODE_BYTES))
        other = room.page_bytes(VA + 0x10000, settings, ir_store_va=0x14FD6D0)
        differ = {n for n in range(room.PAGE_SIZE) if page[n] != other[n]}
        fields = set()
        for offset, relative, family, _ in room._RELOCATIONS:
            self.assertIn(family, ("page", "stock"))
            if family == "page" and not relative or family == "stock" and relative:
                fields.update(range(offset, offset + 4))
        self.assertTrue(differ <= fields)
        self.assertEqual(room.COUNTERS["opening_passes"], 0x2040)
        self.assertEqual(len(set(room.COUNTERS.values())), len(room.COUNTERS))
        self.assertTrue(all(0x2040 <= at < 0x2400 and at % 4 == 0 for at in room.COUNTERS.values()))
        self.assertEqual(room.RING_EVENT.size, 20)
        self.assertEqual(room.RING_OFFSET + room.RING_COUNT * room.RING_EVENT.size, 0x2E00)
        for bad in ((VA + 4, settings), (VA, settings[:31]), (0, settings), (VA, b"\0" * 32)):
            with self.subTest(args=bad), self.assertRaises(ValueError):
                room.page_bytes(*bad)
        listed = list(room.sites(VA, 7))
        self.assertEqual([(name, at, old) for name, at, old, _ in listed],
                         [("opening_entry", OPENING_SITE, bytes.fromhex("e851620700")),
                          ("room_entry", ROOM_SITE, bytes.fromhex("e8016b0300"))])
        for name, at, old, new in listed:
            self.assertEqual(new[0], 0xE8)
            self.assertEqual(at + 5 + struct.unpack("<i", new[1:])[0], VA + room.LABELS[name])
        self.assertEqual(list(room.sites(VA, 0)), listed)
        with self.assertRaises(ValueError):
            list(room.sites(VA, room.STAGE_SIGN))

    def test_authored_template_rebuilds_with_its_development_toolchain(self):
        if not all(shutil.which(tool) for tool in ("gcc", "as", "ld")) or not importlib.util.find_spec("elftools"):
            self.skipTest("development build needs GNU i386 gcc/binutils and pyelftools")
        version = subprocess.run(["gcc", "-dumpfullversion"], capture_output=True, text=True)
        assembler = subprocess.run(["as", "--version"], capture_output=True, text=True)
        if version.stdout.strip() != "13.3.0" or "2.42" not in assembler.stdout.partition("\n")[0]:
            self.skipTest("the checked-in i386 template was generated with GCC 13.3 and GNU binutils 2.42")
        tool = Path(__file__).resolve().parents[2] / "tools/qb_room/build.py"
        subprocess.run([sys.executable, str(tool), "--check"], check=True)

    def test_reference_rating_and_coach_against_the_design_examples(self):
        self.assertEqual(rating10(584, 371, 3781, 26, 12), 882)        # Purdy 88.278 (DESIGN 2.2)
        self.assertEqual(rating10(436, 244, 2337, 16, 20), 641)        # McCarthy 64.17 (FRANCHISE.md: 64.2)
        self.assertEqual([coach1000(x) for x in (40, 61, 83, 99, 120)], [1350, 1350, 1003, 750, 750])


# ---- retail facts -----------------------------------------------------------------------------------------------
class RetailFacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        cls.image = XbeImage(retail_bytes())

    def calls(self, start, end):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        return [(i.address, int(i.op_str, 16)) for i in md.disasm(bytes(self.image.read(start, end - start)), start)
                if i.mnemonic == "call" and i.op_str.startswith("0x")]

    def test_weekly_advance_call_order_and_both_sites(self):
        if not importlib.util.find_spec("capstone"):
            self.skipTest("capstone is required")
        calls = dict(self.calls(0x247D40, 0x248087))
        for at, target in ((0x247D5C, 0x2BDCF0), (0x247DCA, 0x2BE020), (0x247DCF, 0x247AA0),
                           (0x247DFF, 0xC7CB0), (0x248010, 0x323870), (0x24801D, 0xC4E60),
                           (0x248032, 0xC4C50), (0x24803B, 0xC3F00), (0x24806A, 0x2BFBE0),
                           (0x248075, 0x2BDCF0), (0x24807A, 0x27EB80)):
            self.assertEqual(calls.get(at), target, hex(at))
        order = [at for at in sorted(calls) if calls[at] in (0x2BDCF0, 0x2BE020, 0x323870, 0xC4E60, 0x27EB80)]
        self.assertEqual(order, [0x247D5C, 0x247DCA, 0x248010, 0x24801D, 0x248075, 0x24807A])
        self.assertEqual(bytes(self.image.read(0x24807F, 8)), bytes.fromhex("5f5e5d5b8be55dc3"))
        for at, old, _, _ in room.HOOKS:
            self.assertEqual(bytes(self.image.read(at, 5)), old)

    def test_targets_and_getters_have_the_conventions_room_c_declares(self):
        for at, expected in (
                (0x2BE020, "51e88a6be0ff83f808740e"),            # push ecx; call 0xC4BB0; cmp eax,8; je
                (0x2BE03C, "89742404"),                          # the pushed slot is written before any read
                (0x27EB80, "83ec08535657e85560e4ff"),            # sub esp,8; push ebx/esi/edi; call 0xC4BE0
                (0xC7720, "53565733ff8bd933f6"), (0xC7750, "53565733ff8bd933f6"), (0xC7780, "53565733ff8bd933f6"),
                (0xC7741, "8bc75f5e5bc3"), (0xC7771, "8bc75f5e5bc3"), (0xC77A1, "8bc75f5e5bc3"),
                (0x14EE40, "568bf28bc18b5024c1ea0883e21fe84dfaffff85c05e74040fbf00c333c0c3"),
                (0x14E806, "8b3d987fbd00"),                      # mov edi,[0xBD7F98]: the stat class
                (0x246D80, "520fb65135e8d6ffffffc3"),
                (0x246D74, "c20400"), (0x246D17, "c20800"),
                (0xC4C50, "e82bffffffff2485904c0c00"),
                (0x13EC30, "e91b61f8ff"), (0xC4D5F, "8b04855c77e500c3"),
                (0x242CA0, "5733ff85c0668b79287434")):
            with self.subTest(at=hex(at)):
                self.assertEqual(bytes(self.image.read(at, len(expected) // 2)).hex(), expected)


# ---- the league in Unicorn ----------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def standard_image():
    """Retail plus the depth-lock and returner owners: the standard sort, release rule and screen swap."""
    from mod_editor.core import nfl2k5_depth_locks as locks
    from mod_editor.core import nfl2k5_returner_fix as returners
    return locks.apply(returners.apply(retail_bytes())[0])[0]


class QB:
    def __init__(self, ovr, row, *, years=5, locked=True, line=(0, 0, 0, 0, 0, 0), injury=0, status=0, position=0):
        self.ovr, self.row, self.years, self.locked = ovr, row, years, locked
        self.line, self.injury, self.status, self.position = tuple(line), injury, status, position
        self.address = self.index = None


def stub_record_getter(table):
    # mov eax,ecx; sub eax,CLUBS; xor edx,edx; mov ecx,500; div ecx; mov eax,[eax*4+table]; ret
    return (b"\x8b\xc1\x2d" + struct.pack("<I", CLUBS) + b"\x33\xd2\xb9\xf4\x01\x00\x00\xf7\xf1\x8b\x04\x85"
            + struct.pack("<I", table) + b"\xc3")


@unittest.skipUnless(HAVE_UC, "Unicorn is required for the native quarterback room cases")
class League(unittest.TestCase):
    """The whole standard executable with the room page, a synthetic 34-club league and both entries."""

    def setUp(self):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_PROT_READ, UC_PROT_EXEC, x86_const
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage

        data = standard_image()
        image = XbeImage(data)
        self.x = x86_const
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0x10000, 0xFF0000)
        for s in image.sections:
            if s.raw_size:
                uc.mem_write(s.start, data[s.raw:s.raw + s.raw_size])
        uc.mem_write(0x246D80, bytes.fromhex("d94136c3"))        # fld dword [ecx+0x36]; ret
        uc.mem_write(0x246A80, bytes.fromhex("d94136c20400"))
        for k, at in enumerate((0xC7720, 0xC7750, 0xC7780)):
            uc.mem_write(at, stub_record_getter(FIX + 0x100 * k))
        for s in image.sections:
            if not s.writable:
                lo, hi = s.start & ~4095, (s.end + 4095) & ~4095
                uc.mem_protect(lo, hi - lo, UC_PROT_READ | UC_PROT_EXEC)
        uc.mem_map(VA, room.PAGE_SIZE)
        uc.mem_map(ROOT, 0x400000)
        uc.mem_map(STACK & ~0xFFFF, 0x10000)
        uc.mem_map(STOP, 0x1000)
        self.registers = tuple(getattr(self.x, "UC_X86_REG_" + r)
                               for r in ("EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP", "ESP", "EFLAGS"))
        self.sites = {}
        self.install(room.settings_record(7))
        self.clubs = {}
        self.players = []
        for at, value in ((0xB72918, ROOT), (ROOT + 0x18, LEAGUE_CLUBS), (ROOT + 0x1C, CLUBS),
                          (0xE576A0, 2), (0xE576AC, LEAGUE_CLUBS), (0xE576A4, 8), (0xE576B8, 3), (0xE576B4, 5),
                          (0xE60140, 0), (0xBD7F98, 0), (0xE5FCA8, 0x1234567), (0xE5FCB0, 0x89ABCDEF)):
            self.write(at, value)
        for club in range(LEAGUE_CLUBS):
            self.write(0xE5786C + 4 * club, CLUBS + CLUB_SIZE * club)
            self.write(0xE5775C + 4 * club, 0)
            raw = bytearray(CLUB_SIZE)
            raw[0x194:0x19A] = b"\xff" * 6
            struct.pack_into("<I", raw, 0x128, 1 if club >= 32 else 0)
            struct.pack_into("<I", raw, 0x14C, COACHES + COACH_SIZE * club)
            uc.mem_write(CLUBS + CLUB_SIZE * club, bytes(raw))
            self.coach(club, 83)
            self.record(club, 0, 0, 0)

    # -- memory helpers
    def write(self, at, value):
        self.uc.mem_write(at, struct.pack("<I", value & 0xFFFFFFFF))

    def word(self, at):
        return struct.unpack("<I", self.uc.mem_read(at, 4))[0]

    def page(self):
        return bytes(self.uc.mem_read(VA, room.PAGE_SIZE))

    def counters(self):
        return room.counters(self.page())

    def events(self):
        return room.events(self.page())

    def install(self, settings):
        self.uc.mem_write(VA, room.page_bytes(VA, settings))

    def settings(self, stages, **kwargs):
        self.uc.mem_write(VA + room.SETTINGS_OFFSET, room.settings_record(stages, **kwargs))

    def coach(self, club, leadership):
        self.uc.mem_write(COACHES + COACH_SIZE * club + 0x56, bytes([leadership]))

    def record(self, club, w, l, t):
        for k, value in enumerate((w, l, t)):
            self.write(FIX + 0x100 * k + 4 * club, value)

    # -- league
    def add_player(self, q, club):
        q.index = len(self.players)
        q.address = PLAYERS + PLAYER_SIZE * q.index
        self.players.append(q)
        self.write(ROOT, len(self.players))
        self.write(ROOT + 4, PLAYERS)
        self.write_player(q)
        stats = STATS + 0x100 * q.index
        words = []
        for field, value in zip((0, 6, 7, 8, 9, 10), q.line):
            # A decoy with the playoff class first: reading it would mean the stat class was not set to 0.
            words.append((value + 777) & 0xFFFF | field << 16 | q.years << 23 | 1 << 29)
            words.append(value & 0xFFFF | field << 16 | q.years << 23)
        words.append(0x80000000 | 0x7F << 16)
        self.uc.mem_write(stats, struct.pack(f"<{len(words)}I", *words))
        return q

    def write_player(self, q):
        raw = bytearray(PLAYER_SIZE)
        struct.pack_into("<I", raw, 0x20, q.injury)
        struct.pack_into("<I", raw, 0x24, (q.years & 31) << 8 | q.status)
        struct.pack_into("<H", raw, 0x28, 0x2A5 | q.row << 10 | 0 << 13)
        struct.pack_into("<I", raw, 0x2C, STATS + 0x100 * q.index)
        raw[0x35] = q.position
        struct.pack_into("<f", raw, 0x36, q.ovr / 100)
        raw[0x52] = (3 if q.locked else 0) | 0x80
        raw[0x53] = 0xA1
        self.uc.mem_write(q.address, bytes(raw))

    def club(self, index, qbs, *, others=3):
        """Club `index` with the given quarterbacks (QB objects) and a few players at other positions."""
        roster = list(qbs)
        for n in range(others):
            roster.insert(n + 1, QB(60, n, position=1 + n % 3, locked=False))
        for q in roster:
            self.add_player(q, index)
        base = CLUBS + CLUB_SIZE * index
        self.uc.mem_write(base, struct.pack(f"<{len(roster)}I", *(q.address for q in roster)))
        self.uc.mem_write(base + 0x11C, bytes([len(roster)]))
        self.clubs[index] = roster
        return qbs

    def rows(self, qbs):
        return [(struct.unpack("<H", self.uc.mem_read(q.address + 0x28, 2))[0] >> 10) & 7 for q in qbs]

    def locks(self, qbs):
        return [self.uc.mem_read(q.address + 0x52, 1)[0] & 1 for q in qbs]

    def reset(self, qbs):
        for q in qbs:
            self.write_player(q)

    def table(self):
        return bytes(self.uc.mem_read(PLAYERS, PLAYER_SIZE * len(self.players)))

    # -- entries
    def enter(self, entry, *, installed=True):
        site, target = {"opening": (OPENING_SITE, OPENING_TARGET), "room": (ROOM_SITE, ROOM_TARGET)}[entry]
        call = dict((at, new) for _, at, _, new in room.sites(VA, 0))[site] if installed else \
            dict((at, old) for at, old, _, _ in room.HOOKS)[site]
        if self.sites.get(site) != call:
            self.uc.mem_write(site, call)
            self.uc.ctl_flush_tb()          # the site's previous translation must not be reused
            self.sites[site] = call
        incoming = (0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, STACK, 0x8D7)
        for register, value in zip(self.registers, incoming, strict=True):
            self.uc.reg_write(register, value)
        self.uc.emu_start(site, target, count=3_000_000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), target)
        expected = list(incoming)
        expected[7] -= 4
        self.assertEqual(tuple(self.uc.reg_read(r) for r in self.registers), tuple(expected))
        self.assertEqual(self.word(STACK - 4), site + 5)

    def native_sort(self):
        """The standard weekly auto depth 0x2BDCF0 (sort, release rule, compactor) over every club."""
        self.write(STACK, STOP)
        self.uc.reg_write(self.x.UC_X86_REG_ESP, STACK)
        self.uc.emu_start(0x2BDCF0, STOP, count=5_000_000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), STOP)

    def native_swap(self, a, b, club):
        """The installed depth swap 0x242CA0: ECX, ESI players, EAX = 0 (the rank chain), the club on the stack."""
        self.uc.mem_write(STACK, struct.pack("<II", STOP, CLUBS + CLUB_SIZE * club))
        for register, value in ((self.x.UC_X86_REG_ESP, STACK), (self.x.UC_X86_REG_EAX, 0),
                                (self.x.UC_X86_REG_ECX, a.address), (self.x.UC_X86_REG_ESI, b.address)):
            self.uc.reg_write(register, value)
        self.uc.emu_start(0x242CA0, STOP, count=1000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_ESP), STACK + 8)

    def last(self):
        return self.events()[-1]

    def key_d1d4(self, decision, club, a, b, row0):
        return [decision, club, self.word(0xE576B8), self.word(0xE576B4), a.index, b.index, a.ovr, b.ovr,
                row0.line[1], row0.line[3], self.word(0xE5FCA8), self.word(0xE5FCB0)]


# ---- T1, T2: D1 -------------------------------------------------------------------------------------------------
class D1Rookie(League):
    third_locked = True

    def setUp(self):
        super().setUp()
        self.settings(room.STAGE_D1)

    def room_for(self, x):
        """The room the native sort leaves: the locked veteran V (80) and an unlocked rookie U (80 + x) with no
        attempts; the release rule has seated U on row 0 when he leads by 3 or more."""
        veteran = QB(80, 0 if x < 3 else 1)
        rookie = QB(80 + x, 1 if x < 3 else 0, years=1, locked=False)
        third = QB(65, 2, years=8, locked=self.third_locked)
        self.club(4, [veteran, rookie, third])
        return veteran, rookie, third

    def test_t1_veteran_first_share_follows_the_table_for_gaps_0_to_5(self):
        keys = 20_000
        for x in range(6):
            with self.subTest(gap=x):
                self.setUp()
                veteran, rookie, third = self.room_for(x)
                room_qbs = [veteran, rookie, third]
                row0 = veteran if x < 3 else rookie
                # Old code: whoever the sort put on row 0 starts, every time (+0..+2 never, +3..+5 always).
                self.enter("opening", installed=False)
                self.assertEqual(self.rows(room_qbs), [0, 1, 2] if x < 3 else [1, 0, 2])
                self.assertEqual(self.locks(room_qbs), [1, 0, 1])
                self.assertEqual(self.counters()["opening_passes"], 0)
                first = 0
                for k in range(keys):
                    self.write(0xE5FCA8, k * 0x9E3779B1)
                    self.write(0xE5FCB0, k)
                    expected = draw(self.key_d1d4(1, 4, veteran, rookie, row0)) < (85 - 5 * x) * 1000
                    self.enter("opening")
                    rows = self.rows(room_qbs)
                    self.assertEqual(rows[0] < rows[1], expected, k)
                    self.assertEqual(sorted(rows), [0, 1, 2])
                    self.assertEqual(self.locks(room_qbs), [1, 1, 1])
                    first += expected
                    self.reset(room_qbs)
                share = 100 * first / keys
                self.assertLess(abs(share - (85 - 5 * x)), 1.5, share)
                counts = self.counters()
                self.assertEqual((counts["d1_drawn"], counts["d1_veteran_first"]), (keys, first))
                self.assertEqual(counts["d1_exchanged"], keys - first if x < 3 else first)

    def test_t1_outside_the_window_no_draw_and_the_order_is_fixed(self):
        for x, veteran_ahead in ((-1, True), (-7, True), (6, False), (9, False)):
            with self.subTest(gap=x):
                self.setUp()
                veteran, rookie, third = self.room_for(x)
                # Put the wrong man ahead so the decision must write the order it names.
                veteran.row, rookie.row = (1, 0) if veteran_ahead else (0, 1)
                self.reset([veteran, rookie])
                self.enter("opening")
                rows = self.rows([veteran, rookie])
                self.assertEqual(rows[0] < rows[1], veteran_ahead)
                self.assertEqual(self.locks([veteran, rookie, third]), [1, 1, 1])
                event = self.last()
                self.assertEqual(event[3], 1 if veteran_ahead else 0x41)
                self.assertEqual(event[4], room.RESULT_APPLIED)
                self.assertEqual(event[12], 100000 if veteran_ahead else 0)
                self.assertEqual(self.counters()["d1_drawn"], 0)

    def test_t2_d1_locks_both_and_later_passes_and_a_native_sort_change_nothing(self):
        for stage in (7, 8):
            for k in (1, 2, 5):
                with self.subTest(stage=stage, key=k):
                    self.setUp()
                    self.write(0xE576A4, stage)
                    self.settings(7)
                    self.third_locked = False
                    veteran, rookie, third = self.room_for(2)
                    qbs = [veteran, rookie, third]
                    self.write(0xE5FCA8, k)
                    self.enter("opening")
                    decided = self.rows([veteran, rookie, third])
                    self.assertEqual(self.locks([veteran, rookie]), [1, 1])
                    event = self.last()
                    self.assertEqual((event[3] & 0x2F), 1 | (0x20 if stage == 7 else 0))
                    before = [bytes(self.uc.mem_read(q.address, PLAYER_SIZE)) for q in qbs]
                    count = len(self.events())
                    for week in range(3):
                        self.write(0xE5FCA8, 1000 + week)
                        self.write(0xE576B4, 6 + week)
                        self.native_sort()
                        self.enter("room")
                        self.enter("opening")
                    self.assertEqual(self.rows([veteran, rookie, third]), decided)
                    self.assertEqual(self.locks([veteran, rookie]), [1, 1])
                    self.assertFalse([e for e in self.events()[count:] if e[3] & 0x0F == 1])
                    # The unlocked third man was judged once by the first room pass (case c) and locked where he
                    # is. (The native sort assigns the side field, bits 13..15 of +0x28, on its own; the room code
                    # writes only the row field and the lock bit, T5 and T6.)
                    after = [bytes(self.uc.mem_read(q.address, PLAYER_SIZE)) for q in qbs]
                    self.assertEqual([r[0x52] for r in after], [r[0x52] for r in before[:2]] + [before[2][0x52] | 1])
                    self.assertEqual(self.counters()["newcomer_locked"], 1)
                    self.assertEqual(self.counters()["room_passes"], 3)

    def test_t2_old_code_leaves_the_rookie_unlocked_and_a_sort_reseats_him(self):
        veteran, rookie, third = self.room_for(4)
        self.enter("opening", installed=False)
        self.enter("room", installed=False)
        self.assertEqual(self.rows([veteran, rookie]), [1, 0])
        self.assertEqual(self.locks([veteran, rookie]), [1, 0])
        self.assertEqual(self.counters()["opening_passes"], 0)


# ---- T3: D4 -----------------------------------------------------------------------------------------------------
class D4Return(League):
    def setUp(self):
        super().setUp()
        self.settings(room.STAGE_D4)

    def room_for(self, x, hot):
        line = (8, 260, 180, 2300, 20, 3) if hot else (8, 260, 150, 1700, 8, 9)     # rating 116.0 / 70.7
        starter = QB(80, 0, line=line)
        returning = QB(80 + x, 1, locked=False, line=(6, 200, 120, 1400, 9, 6))
        third = QB(60, 2, years=3)
        self.club(9, [starter, returning, third])
        self.record(9, 6, 2, 0) if hot else self.record(9, 4, 4, 0)
        return starter, returning, third

    def test_t3_return_shares_follow_the_table(self):
        keys = 20_000
        for x, hot, chance in ((0, False, 80), (2, False, 80), (-1, False, 35), (0, True, 30), (2, True, 30),
                               (-1, True, 10), (-3, False, 0), (-3, True, 0)):
            with self.subTest(gap=x, hot=hot):
                self.setUp()
                starter, returning, third = self.room_for(x, hot)
                qbs = [starter, returning, third]
                self.enter("room", installed=False)
                self.assertEqual(self.rows(qbs), [0, 1, 2])        # old code: the replacement keeps the job
                took = 0
                for k in range(keys if chance else 50):
                    self.write(0xE5FCA8, k * 0x9E3779B1)
                    self.write(0xE5FCB0, k ^ 0x5A5A)
                    expected = chance and draw(self.key_d1d4(4, 9, starter, returning, starter)) < chance * 1000
                    self.enter("room")
                    rows = self.rows(qbs)
                    self.assertEqual(rows, [1, 0, 2] if expected else [0, 1, 2], k)
                    self.assertEqual(self.locks(qbs), [1, 1, 1])
                    event = self.last()
                    self.assertEqual(event[3], 4 | (0x10 if hot else 0) | (0x40 if expected else 0))
                    self.assertEqual(event[-1], chance * 1000)
                    took += bool(expected)
                    self.reset(qbs)
                if chance:
                    share = 100 * took / keys
                    self.assertLess(abs(share - chance), 1.5, share)
                    self.assertEqual(self.counters()["d4_fired"], took)
                else:
                    self.assertEqual(took, 0)
                    self.assertEqual(self.counters()["d4_lock_only"], 50)


if __name__ == "__main__":
    unittest.main()
