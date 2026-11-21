"""Stage 4b, quarterback-for-pick trades (DESIGN 4.2, qb34/evidence/trades/RISKS.md, DESIGN_CHANGES C20).

PickEncoding: the pick word (nfl2k5_trade_picks) against the game's own code on [validator]'s kept images, mapped on the
standard candidate p2-candidate-9edd1353 (the executable they were made with): the draft's owner lookup after the stage
advance's draft-order step, the executor's transfer, the post-draft roll and the Transactions text.

TradesImage (T9 and C20's conditions): the trades page linked at 0x152C000 against the image's room page at 0x1529000,
entered exactly as the site 0x247E1E enters it (ECX = 3 proposers, EDX = the menu, a plain return), on the kept stage-8
image no-qb-2505-2026-w10-kickoff (2026, week counter 9, the trade window open: the Trade Deadline option is off in it).
A buyer is made by the page's own signal: a D3 row (applied) for it in the room's ring with this week, as the previous
advance's room pass writes it. The expected package is computed here from the design (Python), not from trades.c.

TradesPage and TradesOwner: the byte interface with the room page and the owner (install with bit 16, Retail, needs).

Every class fails on b2672e398 (no nfl2k5_trade_picks, no trades page, the room refused bit 16):
evidence qb34/evidence/trades/tests-on-b2672e398.txt.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest

from tests.nfl2k5_supersim_draft_fixture import HAVE_UC

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(os.environ.get("QB_ROOM_TF_IMAGES", "/home/noah/2k-worktrees/.b77-scratch/b81/qb34/evidence/validator"))
IMAGES = {"no-qb-2505-2026-w10-kickoff.b81mem.gz": "1f725ff50fe01e920bd5043892b597901c8ce0665de8f56ab839522d1bef1b4e",
          "playoffs-2508-2026-w19.b81mem.gz": "7a3ac0eca31be817a3a29b9b0b800082a507dcd2e1a80d43de108350f4c001aa"}
P2A = Path(os.environ.get("QB_ROOM_P2A_REPLAY", "/home/noah/2k-worktrees/.b77-scratch/b81/qb34/evidence/p2a-replay"))
P2A_XBE = ("p2-candidate-9edd1353.xbe", "9edd1353bedfbca6b4ce35faa2acc3cb68b8a74521d3313e3b1873e6b12c7c3d")
CANDIDATE = Path(os.environ.get("QB_TRADES_CANDIDATE",
                                "/home/noah/2k-worktrees/.b77-scratch/b81/qb34/builds/direct-5ff30d9f8/p6-candidate/default.xbe"))
CANDIDATE_SHA = "f5270f4dd305564ad38b782d492f26a095434f11bd3b9627f159a1c6b109e284"
ROOM_VA, TRADES_VA = 0x1529000, 0x152C000
BOARD, RECORD = 0xE3C27C, 0x3C
PICKS = 0xE3C094
STAGE, WEEK, YEAR = 0xE576A4, 0xE576B4, 0xE576B8
USER_FLAG = 0xE5775C
PROBE = 0x3200000


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _need(path, digest):
    if not path.is_file() or _sha(path) != digest:
        raise unittest.SkipTest(f"{path.name} is absent or differs")


def fmix32(h):
    h ^= h >> 16
    h = h * 0x85EBCA6B & 0xFFFFFFFF
    h ^= h >> 13
    h = h * 0xC2B2AE35 & 0xFFFFFFFF
    return h ^ h >> 16


def draw(words):
    h = 0x51425233
    for w in words:
        h = fmix32(h ^ (w & 0xFFFFFFFF))
    return h % 100000


def overall_of_bits(u):
    """room.c overall() on the float's bits."""
    e = (u >> 23) & 255
    if u >> 31 or e < 119:
        return 0
    if e > 127:
        return 100
    s = 150 - e
    return (((u & 0x7FFFFF) | 0x800000) * 100 + (1 << (s - 1))) >> s


class ImageMachine:
    """A kept image on its executable (the method of test_b81_qb_room_floor.TF34)."""

    def __init__(self, name):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        from tools import franchise_invariants as fi
        _need(EVIDENCE / name, IMAGES[name])
        _need(P2A / P2A_XBE[0], P2A_XBE[1])
        self.fi = fi
        self.memory = fi.load_memory(EVIDENCE / name)
        self.m = m = Machine((P2A / P2A_XBE[0]).read_bytes(), trace_writes=False)
        for lo, data in self.memory.regions:
            if lo < 0x3000000:
                m.uc.mem_write(lo, data)
        m.uc.mem_map(PROBE, 0x1000)
        m.uc.ctl_flush_tb()
        self.root = m.get(0xB72918)
        self.teams = m.get(self.root + 0x1C)
        self.table = m.get(self.root + 4)

    def b(self, at):
        return self.m.uc.mem_read(at, 1)[0]

    def h(self, at):
        return struct.unpack("<H", bytes(self.m.uc.mem_read(at, 2)))[0]

    def club(self, i):
        return self.m.call(0xC4C50, ecx=i)

    def index(self, team):
        return next(i for i in range(32) if self.club(i) == team)

    def roster(self, i):
        team = self.club(i)
        return [self.m.get(team + 4 * k) for k in range(self.b(team + 0x11C))]

    def qbs(self, i):
        return [p for p in self.roster(i) if self.b(p + 0x35) == 0]

    def healthy(self, p):
        return not self.m.get(p + 0x20) & 0xBFC00000 and not self.m.get(p + 0x24) & 0x70000000

    def row(self, p):
        return self.h(p + 0x28) >> 10 & 7

    def ovr(self, p, flag=1):
        code = (b"\xb9" + struct.pack("<I", p) + b"\xba" + struct.pack("<I", flag) + b"\xb8\x80\x6d\x24\x00\xff\xd0"
                + b"\xd9\x1d" + struct.pack("<I", PROBE + 0x800) + b"\xc3")
        self.m.uc.mem_write(PROBE, code)
        self.m.uc.ctl_flush_tb()
        self.m.call(PROBE, budget=2_000_000)
        return overall_of_bits(self.m.get(PROBE + 0x800))

    def record(self, i):
        team = self.club(i)
        return tuple(self.m.call(at, ecx=team, budget=5_000_000) for at in (0xC7720, 0xC7750, 0xC7780))

    def board(self, slot):
        return BOARD + RECORD * slot

    def pick_owner(self, word):
        from mod_editor.core import nfl2k5_trade_picks as picks
        return self.b(picks.owner_address(word))


@unittest.skipUnless(HAVE_UC, "Unicorn is required")
class PickEncoding(unittest.TestCase):
    def test_the_draft_gives_every_pick_to_the_owner_its_word_names(self):
        """Stage 9 image (P1 2508, 2026, 76 traded entries): the stage advance's own draft-order step 0x31E210(1), then the
        draft's owner lookup 0x3254D0 for each of the 7 x 32 picks of the coming draft: the club is the owner byte of
        word (r0 + 1) | order[p] << 6, year 0, read BEFORE the step (in season the slot is the original club)."""
        from mod_editor.core import nfl2k5_trade_picks as picks
        x = ImageMachine("playoffs-2508-2026-w19.b81mem.gz")
        m = x.m
        self.assertEqual((m.get(STAGE), m.get(YEAR)), (9, 0))
        before = {(r, s): x.b(picks.owner_address(picks.word(r, s))) for r in range(1, 8) for s in range(32)}
        m.call(0x31E210, ecx=1, budget=100_000_000)
        order = list(m.uc.mem_read(picks.DRAFT_ORDER, 32))
        self.assertEqual(sorted(order), list(range(32)))
        traded = 0
        for r0 in range(7):
            for p in range(32):
                m.put(picks.DRAFT_ROUND, r0)
                m.put(picks.DRAFT_PICK, p)
                club = x.index(m.call(0x3254D0, budget=200_000))
                self.assertEqual(club, before[(r0 + 1, order[p])], (r0, p))
                traded += club != order[p]
        self.assertGreaterEqual(traded, 50)          # 54 on this image: the proof is not about untraded picks only

    def test_year_1_words_and_the_post_draft_roll(self):
        from mod_editor.core import nfl2k5_trade_picks as picks
        x = ImageMachine("playoffs-2508-2026-w19.b81mem.gz")
        m = x.m
        w = picks.word(6, 3, 1)
        m.uc.mem_write(m.ARENA + 0x1C0000, struct.pack("<H", w))
        before = bytes(m.uc.mem_read(picks.PICK_TABLE, 15 * 32))
        m.call(0x2BB1C0, ecx=x.club(17), args=(m.ARENA + 0x1C0000,), budget=100_000)
        after = bytes(m.uc.mem_read(picks.PICK_TABLE, 15 * 32))
        self.assertEqual([i for i in range(15 * 32) if before[i] != after[i]], [picks.owner_address(w) - picks.PICK_TABLE])
        self.assertEqual(after[picks.owner_address(w) - picks.PICK_TABLE], 17)
        m.call(0x31E430, budget=500_000_000)
        rolled = bytes(m.uc.mem_read(picks.PICK_TABLE, 15 * 32))
        self.assertEqual(rolled[32:32 * 8], after[32 * 8:32 * 15])          # next year's rows are now the coming draft's
        self.assertTrue(all(rolled[32 * r + s] == s for r in range(8, 15) for s in range(32)))
        self.assertEqual(x.b(picks.owner_address(picks.word(6, 3, 0))), 17)

    def test_the_native_scan_moves_the_named_pick_and_the_screen_names_its_round(self):
        from mod_editor.core import nfl2k5_trade_picks as picks
        x = ImageMachine("no-qb-2505-2026-w10-kickoff.b81mem.gz")
        m = x.m
        seller, buyer = 0, 5
        qs = next(p for p in x.qbs(seller) if x.row(p) and x.healthy(p) and x.b(p + 0x25) & 31 >= 4 and x.b(p + 0x24) & 15)
        for rnd in (5, 7):
            with self.subTest(round=rnd):
                x = ImageMachine("no-qb-2505-2026-w10-kickoff.b81mem.gz")
                m = x.m
                w = picks.word(rnd, buyer)
                self.assertEqual(x.pick_owner(w), buyer)
                slot = next(i for i in range(1, 15) if not m.get(x.board(i)))
                rec = x.board(slot)
                m.uc.mem_write(rec + 4, bytes(0x30))
                m.put(rec + 8, x.club(seller))
                m.put(rec + 0xC, qs)
                m.put(rec + 0x20, x.club(buyer))
                m.uc.mem_write(rec + 0x30, struct.pack("<HHH", w, 0, 0))
                m.put(rec, 2)
                cursor = m.get(0xE3F06C)
                m.uc.mem_write(m.STACK, struct.pack("<II", m.STOP, m.ARENA + 0x1A0000))
                for k, v in dict(ESP=m.STACK, EBP=0x44444444, EFLAGS=0x202).items():
                    m.reg(k, v)
                m.uc.emu_start(0x2BC900, m.STOP, count=300_000_000)
                self.assertIn(qs, x.roster(buyer))
                self.assertEqual(x.pick_owner(w), seller)
                rows = [0xE3F070 + 12 * ((cursor + i) % 600) for i in range((m.get(0xE3F06C) - cursor) % 600)]
                ours = [r for r in rows if m.get(r + 4) == qs or (m.get(r) & 31 == 7 and not m.get(r + 4)
                                                                   and m.get(r + 8) == x.club(buyer))]
                self.assertEqual([m.get(r) & 31 for r in ours], [7, 7])
                self.assertEqual(m.get(ours[1]) >> 5 & 0xFFFF, rnd)           # the ledger keeps the one-based round
                out = m.ARENA + 0x1B0000
                m.uc.mem_write(out, bytes(0x800))
                m.uc.mem_write(m.STACK, struct.pack("<III", m.STOP, out, ours[0]))
                for k, v in dict(ESP=m.STACK, EBP=0x44444444, EFLAGS=0x202, EAX=x.club(buyer), EDI=x.club(buyer)).items():
                    m.reg(k, v)
                m.uc.emu_start(0x368C40, m.STOP, count=50_000_000)
                text = bytes(m.uc.mem_read(out, 0x400)).decode("utf-16le").split("\x00")[0]
                self.assertTrue(text.endswith(f"for {picks.ordinal(rnd)} round draft pick."), text)

    def test_the_word_helpers_refuse_what_the_table_cannot_index(self):
        from mod_editor.core import nfl2k5_trade_picks as picks
        self.assertEqual(picks.word(5, 2), 133)                    # the lab's "its own fifth" (qb-cpu-trade.json)
        self.assertEqual(picks.decode(966), (6, 15, 0))
        self.assertIsNone(picks.decode(0xFFC0))                    # a cancelled record's word: round 0
        for bad in (0x08, 0x3F, 0x800 | 1, 0x2001):
            with self.subTest(word=hex(bad)), self.assertRaises(ValueError):
                picks.decode(bad)
        self.assertEqual(picks.owner_address(picks.word(7, 31, 1)), PICKS + 32 * 14 + 31)


def _trades_code():
    from mod_editor.core import nfl2k5_qb_trades_code as code
    return code


def _room_code():
    from mod_editor.core import nfl2k5_qb_room_code as code
    return code


@unittest.skipUnless(HAVE_UC, "Unicorn is required")
class TradesImage(unittest.TestCase):
    """T9 in the full image (see the module docstring). Seller 0 (52 active, 3 healthy quarterbacks), buyer chosen per
    case; stages 64 | 16 (the floor and trades) unless a case says otherwise."""

    MENU_OFFSET = 0x1A0000

    def setUp(self):
        self.x = x = ImageMachine("no-qb-2505-2026-w10-kickoff.b81mem.gz")
        m = x.m
        self.assertEqual((m.get(STAGE), m.get(WEEK), m.get(0xE60124)), (8, 9, 0))
        m.put(WEEK, 8)                    # C22 (c): before the native deadline week (the image is at its byte, 9)
        m.uc.mem_map(TRADES_VA, 0x1000)
        from tools import franchise_invariants as fi
        read = lambda a, n: bytes(m.uc.mem_read(a, n))

        def search(needle):                                   # the IR owner's config inside the image's own bytes
            for lo, data in x.memory.regions:
                at = data.find(needle)
                while at >= 0:
                    yield lo + at
                    at = data.find(needle, at + 1)
        self.ir = fi.find_ir_store(read, search) or 0
        # The cases below run with the IR unlinked (no lost-starter need; on this image club 24's IR man would make it
        # a buyer); link_ir() links it for the cases about that need.
        m.uc.mem_write(TRADES_VA, _trades_code().page_bytes(TRADES_VA, ROOM_VA))
        self.settings(64 | 16)
        # The image's room page is an earlier revision's: the counters 4b appends start at zero, as in a page file.
        for name, at in _room_code().COUNTERS.items():
            if name.startswith("trade"):
                m.put(ROOM_VA + at, 0)
        m.uc.ctl_flush_tb()

    # -- helpers
    def link_ir(self):
        self.x.m.uc.mem_write(TRADES_VA, _trades_code().page_bytes(TRADES_VA, ROOM_VA, ir_store_va=self.ir))
        self.x.m.uc.ctl_flush_tb()

    def settings(self, stages, shadow=False):
        room = _room_code()
        self.x.m.uc.mem_write(ROOM_VA + room.SETTINGS_OFFSET, room.settings_record(stages, shadow=shadow))

    def cursor(self):
        return self.x.m.get(ROOM_VA + 0x2E00)

    def counters(self):
        room = _room_code()
        return room.counters(bytes(self.x.m.uc.mem_read(ROOM_VA, room.PAGE_SIZE)))

    def rows(self, since):
        room = _room_code()
        page = bytes(self.x.m.uc.mem_read(ROOM_VA, room.PAGE_SIZE))
        return [room.RING_EVENT.unpack_from(page, 0x2400 + 20 * (n % 128)) for n in range(since, self.cursor())]

    def bench(self, club):
        """The previous advance's room pass benched this club's starter (a D3 row, applied, with this week)."""
        m = self.x.m
        n = self.cursor()
        row = _room_code().RING_EVENT.pack(m.get(YEAR), m.get(WEEK), club, 3, 1, 0, 0, 0, 0, 0, 0, 0, 0)
        m.uc.mem_write(ROOM_VA + 0x2400 + 20 * (n % 128), row)
        m.put(ROOM_VA + 0x2E00, n + 1)

    def board(self):
        m = self.x.m
        return [bytes(m.uc.mem_read(self.x.board(i), RECORD)) for i in range(15)]

    def enter(self):
        """The site's call: ECX = 3, EDX = the menu, the return address on the stack."""
        m = self.x.m
        m.uc.mem_write(m.STACK, struct.pack("<I", m.STOP))
        for k, v in dict(ESP=m.STACK, ECX=3, EDX=m.ARENA + self.MENU_OFFSET, EBX=0x11111111, ESI=0x22222222,
                         EDI=0x33333333, EBP=0x44444444, EFLAGS=0x202).items():
            m.reg(k, v)
        m.uc.emu_start(TRADES_VA + _trades_code().LABELS["trade_entry"], m.STOP, count=2_000_000_000)
        self.assertEqual(m.reg("EIP"), m.STOP)
        self.assertEqual([m.reg(r) for r in ("EBX", "ESI", "EDI", "EBP", "ESP")],
                         [0x11111111, 0x22222222, 0x33333333, 0x44444444, m.STACK + 4])

    def native_only(self):
        """The same state through the retail call (the old code): 0x2BC960 alone."""
        m = self.x.m
        m.uc.mem_write(m.STACK, struct.pack("<I", m.STOP))
        for k, v in dict(ESP=m.STACK, ECX=3, EDX=m.ARENA + self.MENU_OFFSET, EFLAGS=0x202).items():
            m.reg(k, v)
        m.uc.emu_start(0x2BC960, m.STOP, count=2_000_000_000)

    def named_clubs(self):
        x, m = self.x, self.x.m
        out = set()
        for slot in range(15):
            rec = x.board(slot)
            if m.get(rec):
                for at in (8, 0x20):
                    if m.get(rec + at):
                        out.add(x.index(m.get(rec + at)))
        return out

    def expected(self, buyer):
        """DESIGN 4.2's package for this buyer, from the design: (Qs, seller, word) or None."""
        x, m = self.x, self.x.m
        named_players = {m.get(x.board(s) + o) for s in range(15) if m.get(x.board(s))
                         for o in (0xC, 0x10, 0x14, 0x24, 0x28, 0x2C)}
        named = self.named_clubs()
        sp = [p for p in x.qbs(buyer) if x.healthy(p)]
        best = max((x.ovr(p) for p in sp), default=0)
        team = x.club(buyer)
        room = m.get(0xE3C278) - m.get(team + 0x124)
        top, choice = best + 2, None
        for c in range(32):
            if c == buyer or c in named or m.get(USER_FLAG + 4 * c) or c in self.buyers:
                continue
            ros, qbs = x.roster(c), x.qbs(c)
            if not 51 <= len(ros) <= 65 or len(qbs) < 3 or sum(map(x.healthy, qbs)) < 3:
                continue
            seller_best = max(x.ovr(q) for q in qbs if x.healthy(q))          # C22 (a): never the seller's best man
            best_man = next(q for q in ros if x.b(q + 0x35) == 0 and x.healthy(q) and x.ovr(q) == seller_best)
            for p in ros:
                if (x.b(p + 0x35) or not x.healthy(p) or not x.row(p) or x.b(p + 0x25) & 31 < 4
                        or not x.b(p + 0x24) & 15 or p in named_players):
                    continue
                o = x.ovr(p)
                if o <= top or o >= seller_best or room - m.call(0xE6380, ecx=p) <= 10:
                    continue
                backup = max((x.ovr(q) for q in qbs if q not in (best_man, p) and x.healthy(q)), default=0)
                if backup < 60:                                                  # C24 F3
                    continue
                top, choice = o, (p, c)
        if choice is None:
            return None
        rnd = 2 if top >= 95 else 3 if top >= 90 else 4 if top >= 82 else 5 if top >= 76 else 6 if top >= 70 else 7
        while rnd >= 1 and x.pick_owner(rnd | buyer << 6) != buyer:          # C24: an earlier round, never a later
            rnd -= 1
        return (*choice, rnd | buyer << 6 if rnd >= 1 else 0)

    def year_that_fires(self, buyer, qs):
        x, m = self.x, self.x.m
        w, l, t = x.record(buyer)
        sp = max((p for p in x.qbs(buyer) if x.healthy(p)), key=x.ovr)
        att, yds = (m.call(0x14EE40, ecx=sp, edx=f) & 0xFFFF for f in (6, 8))
        index = (qs - x.table) // 0x54
        for year in range(64):
            if draw([8, buyer, year, w, l, t, index, att, yds]) < 35000:
                return year
        self.fail("no year fires")

    def ready_buyer(self, buyer):
        """Bench `buyer`, find its package and choose the season-year index at which the draw posts it."""
        x, m = self.x, self.x.m
        self.buyers = {buyer}
        self.bench(buyer)
        package = self.expected(buyer)
        self.assertIsNotNone(package)
        m.put(YEAR, self.year_that_fires(buyer, package[0]))
        self.bench(buyer)                                 # the row must carry this season's year
        return package

    BUYER = 5                                             # 52 active, two healthy quarterbacks, W + 1 >= L

    # -- T9: a legal package, accepted by the native scan inside the call; nothing of ours left after it
    def test_a_legal_package_is_posted_executed_by_the_native_scan_and_leaves_nothing(self):
        x, m = self.x, self.x.m
        qs, seller, word = self.ready_buyer(self.BUYER)
        self.assertTrue(word)
        start = self.cursor()
        seller_before = len(x.roster(seller))
        self.enter()
        self.assertIn(qs, x.roster(self.BUYER))
        self.assertNotIn(qs, x.roster(seller))
        self.assertEqual(len(x.roster(seller)), seller_before - 1)
        self.assertEqual(x.pick_owner(word), seller)
        ours = [r for r in self.rows(start) if r[3] & 15 == 8]
        self.assertEqual([(r[2], r[3], r[4], r[5], r[9]) for r in ours],
                         [(self.BUYER, 8 | 0x10, 1, (qs - x.table) // 0x54, word), (self.BUYER, 8 | 0x40, 1,
                                                                                     (qs - x.table) // 0x54, word)])
        self.assertTrue(all(not (x.board(s) and self.is_ours(s, qs)) for s in range(15)))
        c = self.counters()
        self.assertEqual((c["trades_posted"], c["trades_executed"], c["trades_cancelled"]), (1, 1, 0))
        self.assertGreaterEqual(sum(x.healthy(p) for p in x.qbs(seller)), 2)
        self.assertTrue(50 <= len(x.roster(self.BUYER)) <= 53 and len(x.roster(seller)) >= 50)

    def is_ours(self, slot, qs):
        m = self.x.m
        rec = self.x.board(slot)
        return m.get(rec) == 2 and m.get(rec + 0xC) == qs

    def test_the_old_code_never_trades_a_quarterback_here(self):
        x = self.x
        qs, seller, word = self.ready_buyer(self.BUYER)
        self.native_only()
        self.assertNotIn(qs, x.roster(self.BUYER))
        self.assertEqual(x.pick_owner(word), self.BUYER)

    # -- C20 (3): refused by the executor: cancelled by us before the call returns
    def test_a_record_the_executor_refuses_is_cancelled_before_the_call_returns(self):
        x, m = self.x, self.x.m
        qs, seller, word = self.ready_buyer(self.BUYER)
        team = x.club(self.BUYER)
        # The practice-squad owner's room test (ps_trade_room, 0x2BC670 -> 0x3DCB20) refuses an incoming player when the
        # active list plus the reserves would pass 65; our evaluator pre-check does not read the reserves.
        m.uc.mem_write(team + 0x1F2, bytes([13]))
        start = self.cursor()
        self.enter()
        self.assertNotIn(qs, x.roster(self.BUYER))
        self.assertEqual(x.pick_owner(word), self.BUYER)
        self.assertFalse(any(self.is_ours(s, qs) for s in range(15)))
        after = [r for r in self.rows(start) if r[3] == 8 | 0x40]
        self.assertEqual([r[4] for r in after], [7])
        self.assertEqual(self.counters()["trades_cancelled"], 1)

    # -- C20 (3): stale: the man is no longer only the seller's (the ownership guard cancels it itself)
    def test_a_stale_record_is_gone_before_the_call_returns(self):
        x, m = self.x, self.x.m
        qs, seller, word = self.ready_buyer(self.BUYER)
        other = next(c for c in range(32) if c not in (self.BUYER, seller) and len(x.roster(c)) < 53
                     and not m.get(USER_FLAG + 4 * c))
        team = x.club(other)
        n = x.b(team + 0x11C)
        m.put(team + 4 * n, qs)                           # Qs also on another club's active list
        m.uc.mem_write(team + 0x11C, bytes([n + 1]))
        start = self.cursor()
        self.enter()
        self.assertNotIn(qs, x.roster(self.BUYER))
        self.assertEqual(x.pick_owner(word), self.BUYER)
        self.assertFalse(any(self.is_ours(s, qs) for s in range(15)))
        after = [r for r in self.rows(start) if r[3] == 8 | 0x40]
        self.assertEqual(len(after), 1)
        self.assertIn(after[0][4], (0, 7))

    # -- T9's must-never cases: nothing written
    def assert_nothing_posted(self, start, board):
        c = self.counters()
        self.assertEqual(c["trades_posted"], 0)
        self.assertEqual([r for r in self.rows(start) if r[3] & 15 == 8 and r[4] in (1, 2)], [])

    def run_case(self, prepare, *, only_seller=False, why):
        """ready_buyer, then `prepare` breaks one rule; nothing may be posted, for the reason the counter `why` names.
        With only_seller every other club that could sell is made human first, so no other package can stand in."""
        x, m = self.x, self.x.m
        qs, seller, word = self.ready_buyer(self.BUYER)
        if only_seller:
            self.close_other_sellers(seller)
        prepare(qs, seller, word)
        start, board = self.cursor(), self.board()
        self.enter()
        self.assert_nothing_posted(start, board)
        self.assertNotIn(qs, x.roster(self.BUYER))
        c = self.counters()
        self.assertEqual({k: c[k] for k in ("trade_buyers", "trade_no_package", "trade_no_pick")}, why)
        return qs, seller, word

    def close_other_sellers(self, seller):
        """Every other club that could sell (51+ active, 3+ quarterbacks of whom 3+ healthy) made human."""
        x = self.x
        for c in range(32):
            qbs = x.qbs(c)
            if c != seller and len(x.roster(c)) >= 51 and len(qbs) >= 3 and sum(map(x.healthy, qbs)) >= 3:
                x.m.put(USER_FLAG + 4 * c, 1)

    def hurt(self, p, weeks=3):
        self.x.m.put(p + 0x20, self.x.m.get(p + 0x20) | 0x80000000 | weeks << 22)

    def test_must_never_1_a_human_club_as_buyer(self):
        self.run_case(lambda qs, s, w: self.x.m.put(USER_FLAG + 4 * self.BUYER, 1),
                      why={"trade_buyers": 0, "trade_no_package": 0, "trade_no_pick": 0})

    def test_must_never_1_a_human_club_as_seller(self):
        """Multi-user: the seller is a second user's club (its own human flag)."""
        self.run_case(lambda qs, s, w: self.x.m.put(USER_FLAG + 4 * s, 1), only_seller=True,
                      why={"trade_buyers": 1, "trade_no_package": 1, "trade_no_pick": 0})

    def test_must_never_3_a_seller_left_with_fewer_than_2_healthy_quarterbacks(self):
        x = self.x

        def prepare(qs, seller, word):
            self.hurt(next(p for p in x.qbs(seller) if p != qs and x.healthy(p)))
        self.run_case(prepare, only_seller=True, why={"trade_buyers": 1, "trade_no_package": 1, "trade_no_pick": 0})

    def test_must_never_4_an_injured_out_expired_rookie_or_starting_quarterback(self):
        """Every man the seller could give (healthy, off row 0) is spoiled the same way; with the seller's third healthy
        quarterback kept, the seller still has its 3 healthy men except in the injury case."""
        cases = {
            "injured": lambda x, p: self.hurt(p),
            "out status": lambda x, p: x.m.put(p + 0x24, x.m.get(p + 0x24) | 0x40000000),
            "expired": lambda x, p: x.m.uc.mem_write(p + 0x24, bytes([x.b(p + 0x24) & 0xF0])),
            "rookie": lambda x, p: x.m.uc.mem_write(p + 0x25, bytes([(x.b(p + 0x25) & 0xE0) | 1])),
            "three years pro": lambda x, p: x.m.uc.mem_write(p + 0x25, bytes([(x.b(p + 0x25) & 0xE0) | 3])),
        }
        for name, spoil in cases.items():
            with self.subTest(case=name):
                self.setUp()

                def prepare(qs, seller, word):
                    for p in self.x.qbs(seller):
                        if self.x.row(p):
                            spoil(self.x, p)
                self.run_case(prepare, only_seller=True, why={"trade_buyers": 1, "trade_no_package": 1, "trade_no_pick": 0})
        with self.subTest(case="row 0"):
            self.setUp()

            def prepare(qs, seller, word):
                x = self.x
                starter = next(p for p in x.qbs(seller) if not x.row(p))
                wa, wb = x.h(qs + 0x28), x.h(starter + 0x28)
                ra, rb = x.row(qs), x.row(starter)
                x.m.uc.mem_write(qs + 0x28, struct.pack("<H", (wa & ~0x1C00) | rb << 10))
                x.m.uc.mem_write(starter + 0x28, struct.pack("<H", (wb & ~0x1C00) | ra << 10))
                for p in x.qbs(seller):                   # every other off-row-0 man out of the market (status Out)
                    if p not in (qs, starter):
                        x.m.put(p + 0x24, x.m.get(p + 0x24) | 0x40000000)
            self.run_case(prepare, only_seller=True, why={"trade_buyers": 1, "trade_no_package": 1, "trade_no_pick": 0})

    def set_count(self, club, want):
        x = self.x
        team = x.club(club)
        roster = x.roster(club)
        if want > len(roster):
            donor = [p for p in x.roster(31) if x.b(p + 0x35) != 0]
            for k in range(want - len(roster)):
                x.m.put(team + 4 * (len(roster) + k), donor[k])
        else:
            keep = [p for p in roster if x.b(p + 0x35) == 0]
            keep += [p for p in roster if x.b(p + 0x35) != 0][:want - len(keep)]
            for k, p in enumerate(keep):
                x.m.put(team + 4 * k, p)
        x.m.uc.mem_write(team + 0x11C, bytes([want]))

    def test_must_never_5_a_buyer_at_53_or_48_before_or_a_seller_at_50(self):
        for count in (53, 48):
            with self.subTest(buyer=count):
                self.setUp()
                self.run_case(lambda qs, s, w, count=count: self.set_count(self.BUYER, count),
                              why={"trade_buyers": 0, "trade_no_package": 0, "trade_no_pick": 0})
        with self.subTest(seller=50):
            self.setUp()
            self.run_case(lambda qs, s, w: self.set_count(s, 50), only_seller=True,
                          why={"trade_buyers": 1, "trade_no_package": 1, "trade_no_pick": 0})

    def test_must_never_6_a_pick_the_buyer_does_not_own(self):
        x, m = self.x, self.x.m

        def prepare(qs, seller, word):
            for rnd in range(1, 8):
                m.uc.mem_write(PICKS + 32 * rnd + self.BUYER, bytes([seller]))
        self.run_case(prepare, why={"trade_buyers": 1, "trade_no_package": 0, "trade_no_pick": 1})

    def test_must_never_7_slot_0_and_non_empty_records_are_never_written(self):
        x, m = self.x, self.x.m

        def prepare(qs, seller, word):
            for s in range(1, 15):
                if not m.get(x.board(s)):
                    m.put(x.board(s), 1)                  # a listing in every free CPU slot
        qs, seller, word = self.ready_buyer(self.BUYER)
        prepare(qs, seller, word)
        before = self.board()
        self.native_only_snapshot = before
        start = self.cursor()
        self.enter_without_native()
        self.assertEqual(self.board()[0], before[0])
        self.assertEqual(self.counters()["trade_no_slot"], 1)
        self.assert_nothing_posted(start, before)

    def enter_without_native(self):
        """trade_call with the native pass stubbed out (so the board can be compared byte for byte)."""
        m = self.x.m
        m.uc.mem_write(0x2BC960, b"\xc3")
        m.uc.ctl_flush_tb()
        self.enter()

    def test_must_never_8_nothing_in_stage_7_or_9_and_bit_16_off_changes_nothing(self):
        for case in ("stage 7", "stage 9", "bit 16 off"):
            with self.subTest(case=case):
                self.setUp()
                x, m = self.x, self.x.m
                qs, seller, word = self.ready_buyer(self.BUYER)
                if case == "bit 16 off":
                    self.settings(64)
                else:
                    m.put(STAGE, int(case.split()[1]))
                start, board = self.cursor(), self.board()
                m.uc.mem_write(0x2BC960, b"\xc3")
                m.uc.ctl_flush_tb()
                self.enter()
                self.assertEqual(self.board(), board)
                self.assertEqual([r for r in self.rows(start) if r[3] & 15 == 8], [])
                c = self.counters()
                self.assertEqual(c["trade_inactive"], 1 if case.startswith("stage") else 0)

    def test_must_never_9_no_record_for_a_club_another_record_names(self):
        x, m = self.x, self.x.m

        def prepare(qs, seller, word):
            free = next(s for s in range(1, 15) if not m.get(x.board(s)))
            m.put(x.board(free) + 8, x.club(seller))      # the seller already lists someone (kind 1)
            m.put(x.board(free), 1)
        self.run_case(prepare, only_seller=True, why={"trade_buyers": 1, "trade_no_package": 1, "trade_no_pick": 0})

    def test_must_never_9_two_buyers_never_share_a_seller(self):
        """Two benched buyers whose best package is the same seller's: one record for that seller, the other buyer gets
        nothing (the native pass stubbed, so our record stays until the clear-up cancels it)."""
        x, m = self.x, self.x.m
        qs, seller, word = self.ready_buyer(self.BUYER)
        self.close_other_sellers(seller)
        named = self.named_clubs()
        second = None
        for c in range(32):
            w, l, t = x.record(c)
            if (c in (self.BUYER, seller) or c in named or m.get(USER_FLAG + 4 * c) or not 49 <= len(x.roster(c)) <= 52
                    or not any(map(x.healthy, x.qbs(c))) or w + l + t < 2 or w + 1 < l):
                continue
            self.buyers = {self.BUYER, c}
            package = self.expected(c)
            if package and package[1] == seller and package[2]:
                second = c
                break
        if second is None:
            self.skipTest("no second buyer with the same seller on this image")
        self.bench(second)
        m.uc.mem_write(0x2BC960, b"\xc3")
        m.uc.ctl_flush_tb()
        start = self.cursor()
        self.enter()
        before_pass = [r for r in self.rows(start) if r[3] & 0x4F == 8]
        self.assertEqual(sorted(r[2] for r in before_pass if r[4] == 1), [min(self.BUYER, second)])
        self.assertEqual(self.counters()["trade_no_package"], 1)
        self.assertEqual(self.counters()["trades_cancelled"], 1)

    # -- C22 (lead's rulings, 2026-11-20): each fails on 9b1a13342
    def test_c22a_a_seller_never_gives_up_its_best_healthy_quarterback(self):
        """A seller whose best healthy quarterback would pass every other test (4+ years, a contract, 3+ better than the
        buyer's best, within the buyer's cap room) is given a chart with that man on row 1 (rows exchanged with its row
        1 man; native rows can sit a better man lower). With it the only seller, the old rule ("not row 0") posts its best
        man; C22 (a) never offers him."""
        x, m = self.x, self.x.m
        team = x.club(self.BUYER)
        room = m.get(0xE3C278) - m.get(team + 0x124)
        floor = max(x.ovr(p) for p in x.qbs(self.BUYER) if x.healthy(p)) + 3
        named = self.named_clubs()
        found = None
        for c in range(32):
            qbs = x.qbs(c)
            if (c == self.BUYER or c in named or m.get(USER_FLAG + 4 * c) or not 51 <= len(x.roster(c)) <= 65
                    or len(qbs) < 3 or sum(map(x.healthy, qbs)) < 3):
                continue
            best = max((p for p in qbs if x.healthy(p)), key=x.ovr)
            if (x.b(best + 0x25) & 31 >= 4 and x.b(best + 0x24) & 15 and x.ovr(best) >= floor
                    and room - m.call(0xE6380, ecx=best) > 10):
                found = (c, best)
                break
        if found is None:
            self.skipTest("no seller on this image has a tradable best man")
        seller, best = found
        second = next(p for p in x.qbs(seller) if x.row(p) == (1 if x.row(best) == 0 else 0))
        if x.row(best) == 0:                                    # put the best man on row 1, the other on row 0
            wb, ws = x.h(best + 0x28), x.h(second + 0x28)
            m.uc.mem_write(best + 0x28, struct.pack("<H", (wb & ~0x1C00) | 1 << 10))
            m.uc.mem_write(second + 0x28, struct.pack("<H", ws & ~0x1C00))
        self.close_other_sellers(seller)
        self.buyers = {self.BUYER}
        self.bench(self.BUYER)
        m.put(YEAR, self.year_that_fires(self.BUYER, best))     # the old rule's package would be posted
        self.bench(self.BUYER)
        start = self.cursor()
        m.uc.mem_write(0x2BC960, b"\xc3")
        m.uc.ctl_flush_tb()
        self.enter()
        named_rows = [r for r in self.rows(start) if r[3] & 15 == 8]
        self.assertNotIn((best - x.table) // 0x54, [r[5] for r in named_rows])
        self.assertIn(best, x.roster(seller))

    def test_c22b_a_quarterback_rated_90_or_more_costs_the_buyers_3rd(self):
        x, m = self.x, self.x.m
        seller = 25
        backup = next(p for p in x.qbs(seller) if x.row(p) == 1)             # Mariota, 85, behind a 100
        while x.ovr(backup) < 90:                                            # +0x42 raises his overall
            m.uc.mem_write(backup + 0x42, bytes([x.b(backup + 0x42) + 1]))
        self.assertLess(x.ovr(backup), max(x.ovr(p) for p in x.qbs(seller) if x.healthy(p)))
        qs, chosen, word = self.ready_buyer(self.BUYER)
        self.assertEqual((qs, chosen, word & 0x3F), (backup, seller, 3))
        self.enter()
        self.assertIn(backup, x.roster(self.BUYER))
        self.assertEqual(x.pick_owner(word), seller)

    def test_c22c_no_posting_from_the_deadline_week_even_with_the_option_off(self):
        """The image's Trade Deadline option is off, so the native window is open in every week; 4b posts only while
        the week counter is below the deadline byte 0x5151C5 (9)."""
        x, m = self.x, self.x.m
        self.assertEqual((m.get(0xE60124), x.b(0x5151C5)), (0, 9))
        for week, posted in ((9, 0), (8, 1)):
            with self.subTest(week=week):
                self.setUp()
                x, m = self.x, self.x.m
                qs, seller, word = self.ready_buyer(self.BUYER)
                m.put(WEEK, week)
                self.bench(self.BUYER)
                m.uc.mem_write(0x2BC960, b"\xc3")
                m.uc.ctl_flush_tb()
                self.enter()
                c = self.counters()
                self.assertEqual(c["trades_posted"], posted)
                self.assertEqual(c.get("trade_past_deadline"), 1 - posted)

    # -- C22 addenda (lead, 2026-11-20 after the acting run): each fails on e877f2e7f
    def test_c22_addendum1_a_club_with_three_quarterbacks_is_never_a_buyer(self):
        """The acting run's club 28 (2503/2031) bought a fourth quarterback on a D3 benching. A D3-benched club with 3
        active quarterbacks is not a buyer now (at most 2 before the trade, as E1's "never above 3")."""
        x, m = self.x, self.x.m
        named = self.named_clubs()
        club = next((c for c in range(32) if c not in named and not m.get(USER_FLAG + 4 * c)
                     and 49 <= len(x.roster(c)) <= 52 and len(x.qbs(c)) == 3 and any(map(x.healthy, x.qbs(c)))
                     and sum(x.record(c)) >= 2 and x.record(c)[0] + 1 >= x.record(c)[1]), None)
        if club is None:
            self.skipTest("no 3-quarterback club that could buy on this image")
        m.uc.mem_write(0x2BC960, b"\xc3")
        m.uc.ctl_flush_tb()
        self.enter()                                            # the baseline: the image's own buyers
        baseline = self.counters()["trade_buyers"]
        self.setUp()
        x, m = self.x, self.x.m
        self.bench(club)
        start = self.cursor()
        m.uc.mem_write(0x2BC960, b"\xc3")
        m.uc.ctl_flush_tb()
        self.enter()
        self.assertEqual(self.counters()["trade_buyers"], baseline)      # the benched 3-QB club is not one more
        self.assertFalse([r for r in self.rows(start) if r[3] & 15 == 8 and r[2] == club])

    def test_c22_addendum2_a_lost_starter_on_ir_is_rated_at_full_strength(self):
        """L is a hurt man. The image's most discounted hurt quarterback (flag 0 90, flag 1 42: C21's discount) is put on
        club 5's IR, out for the season; club 5's best healthy is 82. With flag 0 he is 3+ better and club 5 needs a
        quarterback; with flag 1 (e877f2e7f) he is not and club 5 is no buyer."""
        x, m = self.x, self.x.m
        if not self.ir:
            self.skipTest("this image has no modern IR store")
        hurt = min((p for c in range(32) for p in x.qbs(c) if not x.healthy(p)), key=lambda p: x.ovr(p, 1) - x.ovr(p, 0))
        best = max(x.ovr(p) for p in x.qbs(self.BUYER) if x.healthy(p))
        self.assertGreaterEqual(x.ovr(hurt, 0) - best, 3)
        self.assertLess(x.ovr(hurt, 1) - best, 3)
        club = self.ir + 0x40 + 0xA4 * self.BUYER
        n = x.b(club)
        m.uc.mem_write(club + 4 + 8 * n, struct.pack("<IhBB", hurt, 0, 1, 0))      # flags bit 0: out for the season
        m.uc.mem_write(club, bytes([n + 1]))
        self.link_ir()
        m.uc.mem_write(0x2BC960, b"\xc3")
        m.uc.ctl_flush_tb()
        self.enter()                                            # club 5 is now a buyer (no other change to the image)
        with_l = self.counters()["trade_buyers"]
        self.setUp()
        x, m = self.x, self.x.m
        self.link_ir()
        m.uc.mem_write(0x2BC960, b"\xc3")
        m.uc.ctl_flush_tb()
        self.enter()
        self.assertEqual(with_l - self.counters()["trade_buyers"], 1)

    # -- C24 (coordinator's rulings on the independent review, 2026-11-21): each fails on c01237d67
    def set_overall(self, p, target):
        """Move a man's overall (0x246D80(p, 1)) to `target` through his quarterback rating bytes (+0x42 first, as
        test_c22b does, then +0x38, +0x50, +0x43, +0x4E, +0x41; each kept within 0..99), one step at a time."""
        x, m = self.x, self.x.m
        step = 1 if x.ovr(p) < target else -1
        for at in (0x42, 0x38, 0x50, 0x43, 0x4E, 0x41):
            while x.ovr(p) != target and 1 < x.b(p + at) < 99 and (x.ovr(p) < target) == (step > 0):   # 0..99
                m.uc.mem_write(p + at, bytes([x.b(p + at) + step]))
            if x.ovr(p) == target:
                return p
        self.skipTest(f"cannot move this man's overall to {target}")

    def without_native_pass(self):
        self.x.m.uc.mem_write(0x2BC960, b"\xc3")
        self.x.m.uc.ctl_flush_tb()

    def post_for(self, qs):
        """Bench the buyer and choose the season-year at which the draw posts Qs (no oracle)."""
        self.buyers = {self.BUYER}
        self.bench(self.BUYER)
        self.x.m.put(YEAR, self.year_that_fires(self.BUYER, qs))
        self.bench(self.BUYER)

    def test_c24_f3_a_seller_keeps_a_healthy_backup_rated_60_or_more(self):
        """Seller 25 (100, Mariota 85, a 63 third man) sells Mariota only if the man left behind its best rates 60+: at
        59 no package (the review's Brosmer 28 case), at 60 the trade is made."""
        for backup_overall, posted in ((59, 0), (60, 1)):
            with self.subTest(backup=backup_overall):
                self.setUp()
                x = self.x
                mariota = next(p for p in x.qbs(25) if x.row(p) == 1)
                third = next(p for p in x.qbs(25) if x.row(p) == 2)
                self.set_overall(third, backup_overall)
                self.close_other_sellers(25)
                self.post_for(mariota)
                self.without_native_pass()
                self.enter()
                c = self.counters()
                self.assertEqual((c["trades_posted"], c["trade_no_package"]), (posted, 1 - posted))

    def test_c24_f4_no_purchase_when_the_buyers_best_healthy_quarterback_rates_85_or_more(self):
        """Club 5's best healthy quarterback (82, benched by D3) moved to 85: no buyer; at 84 still a buyer. The relative
        tests (Qs 3+ above S'; L 3+ above S') still apply on top."""
        for best, buyers in ((85, 0), (84, 1)):
            with self.subTest(best=best):
                self.setUp()
                x = self.x
                starter = max((p for p in x.qbs(self.BUYER) if x.healthy(p)), key=x.ovr)
                self.set_overall(starter, best)
                self.bench(self.BUYER)
                self.without_native_pass()
                self.enter()
                self.assertEqual(self.counters()["trade_buyers"], buyers)

    def test_c24_price_95_or_more_costs_the_buyers_2nd(self):
        x, m = self.x, self.x.m
        mariota = self.set_overall(next(p for p in x.qbs(25) if x.row(p) == 1), 95)   # behind a 100
        qs, seller, word = self.ready_buyer(self.BUYER)
        self.assertEqual((qs, seller, word & 0x3F), (mariota, 25, 2))
        self.enter()
        self.assertIn(mariota, x.roster(self.BUYER))
        self.assertEqual(x.pick_owner(2 | self.BUYER << 6), 25)
        self.assertEqual(x.pick_owner(3 | self.BUYER << 6), self.BUYER)

    def test_c24_price_an_earlier_round_when_that_pick_is_gone_never_a_later_one(self):
        """Mariota (85) costs a 4th. Club 5's 4th traded away: it pays its 3rd. Its 1st to 4th all gone: no trade (its 5th
        is never offered)."""
        for gone, round_paid in (((4,), 3), ((1, 2, 3, 4), None)):
            with self.subTest(gone=gone):
                self.setUp()
                x, m = self.x, self.x.m
                for r in gone:
                    m.uc.mem_write(0xE3C094 + 32 * r + self.BUYER, bytes([29]))
                mariota = next(p for p in x.qbs(25) if x.row(p) == 1)
                self.post_for(mariota)
                start = self.cursor()
                self.enter()
                c = self.counters()
                if round_paid is None:
                    self.assertEqual((c["trades_posted"], c["trade_no_pick"]), (0, 1))
                    self.assertEqual(x.pick_owner(5 | self.BUYER << 6), self.BUYER)
                    self.assertNotIn(mariota, x.roster(self.BUYER))
                else:
                    self.assertEqual(c["trades_posted"], 1)
                    self.assertIn(mariota, x.roster(self.BUYER))
                    self.assertEqual(x.pick_owner(round_paid | self.BUYER << 6), 25)
                    self.assertEqual(x.pick_owner(5 | self.BUYER << 6), self.BUYER)

    def test_c24_f5_no_trade_when_a_free_agent_as_good_is_within_the_buyers_reach(self):
        """The best free-agent quarterback (78, valued far below club 5's cap room) moved to 85, Mariota's overall: no
        trade (E1/E2 would sign him); at 84 the trade is made."""
        for fa_overall, posted in ((85, 0), (84, 1)):
            with self.subTest(free_agent=fa_overall):
                self.setUp()
                x, m = self.x, self.x.m
                root = m.get(0xB72918)
                listing = [m.get(m.get(root + 0x3C) + 4 * i) for i in range(m.get(root + 0x38))]
                best = max((p for p in listing if p and x.b(p + 0x35) == 0 and x.healthy(p)), key=x.ovr)
                self.set_overall(best, fa_overall)
                mariota = next(p for p in x.qbs(25) if x.row(p) == 1)
                self.post_for(mariota)
                self.without_native_pass()
                self.enter()
                c = self.counters()
                self.assertEqual((c["trades_posted"], c.get("trade_free_agent", 0)), (posted, 1 - posted))

    def test_c24_f6_no_trade_after_an_emergency_signing_this_week_or_last(self):
        """An applied E1 row (decision 5, result 1) for the buyer logged with this week's number or the previous one
        keeps it out; two weeks back it is a buyer again (the review's mutation MS deletes this guard)."""
        for back, buyers in ((0, 0), (1, 0), (2, 1)):
            with self.subTest(weeks_back=back):
                self.setUp()
                m = self.x.m
                self.bench(self.BUYER)
                n = self.cursor()
                row = _room_code().RING_EVENT.pack(m.get(YEAR), m.get(WEEK) - back, self.BUYER, 5, 1, 0, 0, 0, 0, 0, 0,
                                                   0, 0)
                m.uc.mem_write(ROOM_VA + 0x2400 + 20 * (n % 128), row)
                m.put(ROOM_VA + 0x2E00, n + 1)
                self.without_native_pass()
                self.enter()
                self.assertEqual(self.counters()["trade_buyers"], buyers)

    def test_must_never_10_a_buyer_never_cuts(self):
        x, m = self.x, self.x.m
        qs, seller, word = self.ready_buyer(self.BUYER)
        before = set(x.roster(self.BUYER))
        self.enter()
        self.assertEqual(set(x.roster(self.BUYER)) - {qs}, before)

    def test_shadow_computes_and_logs_but_writes_nothing_to_the_board(self):
        x, m = self.x, self.x.m
        qs, seller, word = self.ready_buyer(self.BUYER)
        self.settings(64 | 16, shadow=True)
        self.bench(self.BUYER)
        start, board = self.cursor(), self.board()
        m.uc.mem_write(0x2BC960, b"\xc3")
        m.uc.ctl_flush_tb()
        self.enter()
        self.assertEqual(self.board(), board)
        rows = [r for r in self.rows(start) if r[3] & 15 == 8]
        self.assertEqual([(r[2], r[4], r[9]) for r in rows], [(self.BUYER, 2, word)])
        self.assertEqual(self.counters()["trade_shadow"], 1)


    def test_after_the_native_deadline_the_site_is_not_reached(self):
        """The weekly advance's own stage-8 code from 0x247E0E to 0x247E23 with the site installed in RAM: with the Trade
        Deadline option on and the week counter at the deadline byte (0x5151C5, 9 with the deadline owner) the native
        window 0x247D10 is closed and 0x247E15 jumps over the site: no trade pass, no row; one week earlier it runs."""
        x, m = self.x, self.x.m
        qs, seller, word = self.ready_buyer(self.BUYER)
        at, _original, patched = _trades_code().site(TRADES_VA)
        m.uc.mem_write(at, patched)
        m.uc.mem_write(0x2BC960, b"\xc3")                 # the native pass itself is not under test here
        m.uc.ctl_flush_tb()
        deadline = x.b(0x5151C5)
        self.assertEqual(deadline, 9)
        m.put(0xE60124, 1)
        for week, reached in ((deadline, False), (deadline - 1, True)):
            with self.subTest(week=week):
                m.put(WEEK, week)
                self.bench(self.BUYER)
                calls, start = self.counters()["trade_calls"], self.cursor()
                m.uc.mem_write(m.STACK, struct.pack("<I", m.STOP))
                for k, v in dict(ESP=m.STACK, EBP=m.ARENA + self.MENU_OFFSET, EFLAGS=0x202).items():
                    m.reg(k, v)
                m.uc.emu_start(0x247E0E, 0x247E23, count=50_000_000)
                self.assertEqual(m.reg("EIP"), 0x247E23)
                self.assertEqual(self.counters()["trade_calls"] - calls, int(reached))
                self.assertEqual(bool([r for r in self.rows(start) if r[3] & 15 == 8]), reached)

    def test_the_trades_page_alone_in_shadow_writes_nothing_while_the_room_acts(self):
        """The 4b shadow panel's setting: the trades page's flag word (+0xF04) set, the room's own shadow flag off."""
        x, m = self.x, self.x.m
        qs, seller, word = self.ready_buyer(self.BUYER)
        m.uc.mem_write(TRADES_VA, _trades_code().page_bytes(TRADES_VA, ROOM_VA, ir_store_va=self.ir, shadow=True))
        m.uc.ctl_flush_tb()
        start, board = self.cursor(), self.board()
        self.enter()
        self.assertNotIn(qs, x.roster(self.BUYER))
        self.assertEqual(x.pick_owner(word), self.BUYER)
        rows = [r for r in self.rows(start) if r[3] & 15 == 8]
        self.assertEqual([(r[2], r[4], r[9]) for r in rows], [(self.BUYER, 2, word)])
        self.assertEqual((self.counters()["trade_shadow"], self.counters()["trades_posted"]), (1, 0))


class TradesPage(unittest.TestCase):
    def test_the_room_page_is_byte_for_byte_the_room_branchs(self):
        """C20: 4b does not change the room page (only counter names were appended to room.h). The room's own head is
        b1d283e79 (job/b81-qb34-e, merged here: the C23 relayout); before, a3c8ff69c and b2672e398."""
        try:
            old = subprocess.run(["git", "-C", str(ROOT), "show", "b1d283e79:mod_editor/core/nfl2k5_qb_room_code.py"],
                                 check=True, capture_output=True).stdout
        except (OSError, subprocess.CalledProcessError):
            raise unittest.SkipTest("git history is not available")
        spec = importlib.util.spec_from_loader("room_b1d283e79", loader=None)
        module = importlib.util.module_from_spec(spec)
        exec(compile(old, "room_b1d283e79", "exec"), module.__dict__)
        room = _room_code()
        self.assertEqual(room._TEMPLATE, module._TEMPLATE)
        self.assertEqual(room._RELOCATIONS, module._RELOCATIONS)
        self.assertEqual(room.LABELS, module.LABELS)
        self.assertEqual({k: v for k, v in room.COUNTERS.items() if k in module.COUNTERS}, module.COUNTERS)
        self.assertEqual((room.RING_COUNT, room.RING_OFFSET, room.RING_CURSOR), (128, 0x2400, 0x2E00))

    def test_the_trades_page_reaches_the_room_only_at_its_exported_offsets(self):
        room, trades = _room_code(), _trades_code()
        self.assertEqual(trades.ROOM_OFFSETS, {"settings": room.SETTINGS_OFFSET, "counters": room.COUNTERS_OFFSET,
                                               "ring": room.RING_OFFSET, "ring_cursor": room.RING_CURSOR})
        self.assertEqual(trades.RING_COUNT, room.RING_COUNT)
        allowed = set(range(room.SETTINGS_OFFSET, room.SETTINGS_OFFSET + room.SETTINGS.size))
        allowed |= set(room.COUNTERS.values())
        allowed |= {room.RING_OFFSET, room.RING_CURSOR}
        targets = {addend for _o, _rel, family, addend in trades._RELOCATIONS if family == "room"}
        self.assertTrue(targets and targets <= allowed, sorted(hex(t) for t in targets - allowed))
        names = {v: k for k, v in room.COUNTERS.items()}
        self.assertLessEqual({names[t] for t in targets if t in names},
                             {"events_logged", "trades_posted", "trades_cancelled"} | {n for n in room.COUNTERS
                                                                                       if n.startswith("trade")})
        self.assertTrue(all(family in ("page", "room", "stock") for _o, _r, family, _a in trades._RELOCATIONS))

    def test_the_room_and_trades_counters_are_disjoint_inside_the_counter_area(self):
        """C22 addendum (3): C21 ([native]) puts sign_skip_protected at +0x219C, after season_locks_cleared (+0x2198); 4b's
        own counters follow every room counter, from +0x21A0, below the middle code piece (+0x2200). On e877f2e7f
        4b's trade_calls sat at +0x219C."""
        room, trades = _room_code(), _trades_code()
        offsets = list(room.COUNTERS.values())
        self.assertEqual(len(offsets), len(set(offsets)))
        self.assertTrue(all(room.COUNTERS_OFFSET <= o < room.CODE_RESERVED[0] and o % 4 == 0 for o in offsets))
        self.assertEqual((room.COUNTERS["season_locks_cleared"], room.COUNTERS.get("sign_skip_protected")),
                         (0x2198, 0x219C))
        own = {n: o for n, o in room.COUNTERS.items() if n.startswith("trade") and n not in ("trades_posted",
                                                                                         "trades_cancelled")}
        rest = {n: o for n, o in room.COUNTERS.items() if n not in own}
        self.assertGreaterEqual(min(own.values()), 0x21A0)
        self.assertGreater(min(own.values()), max(rest.values()))
        written = {a for _o, _r, family, a in trades._RELOCATIONS if family == "room"
                   and room.COUNTERS_OFFSET <= a < room.CODE_RESERVED[0]}
        self.assertLessEqual(written, set(own.values()) | {room.COUNTERS[n] for n in
                                                           ("events_logged", "trades_posted", "trades_cancelled")})

    def test_page_layout_site_and_relocation(self):
        trades = _trades_code()
        page = trades.page_bytes(TRADES_VA, ROOM_VA, ir_store_va=0x14FD6D0)
        self.assertEqual(len(page), 0x1000)
        self.assertEqual(page[trades.CODE_BYTES:trades.CODE_LIMIT], b"\xcc" * (trades.CODE_LIMIT - trades.CODE_BYTES))
        self.assertEqual(page[0xF00:], struct.pack("<I", 0x14FD6D0) + bytes(0xFC))
        at, original, patched = trades.site(TRADES_VA)
        self.assertEqual((at, original), (0x247E1E, bytes.fromhex("e83d4b0700")))
        self.assertEqual(at + 5 + struct.unpack("<i", patched[1:])[0], TRADES_VA + trades.LABELS["trade_entry"])
        moved = trades.page_bytes(TRADES_VA, ROOM_VA + 0x10000)
        self.assertTrue({n for n in range(0x1000) if moved[n] != trades.page_bytes(TRADES_VA, ROOM_VA)[n]})

    def test_the_template_rebuilds_with_its_development_toolchain(self):
        if not all(importlib.util.find_spec(m) for m in ("elftools",)):
            raise unittest.SkipTest("pyelftools is absent")
        result = subprocess.run([sys.executable, str(ROOT / "tools/qb_trades/build.py"), "--check"], capture_output=True)
        if result.returncode and b"No such file" in result.stderr:
            raise unittest.SkipTest("GNU as/ld or gcc is absent")
        self.assertEqual(result.returncode, 0, result.stderr.decode()[-400:])

    def test_the_retail_site_is_the_stage_8_trade_pass_behind_the_window(self):
        """0x247E1E is reached only from the stage-8 case 0x247E0E and only when 0x247D10 returns nonzero."""
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(retail_bytes())
        self.assertEqual(image.read(0x247E0E, 21), bytes.fromhex("e8fdfeffff85c0740c8bd5b903000000e83d4b0700"))
        table = struct.unpack("<9I", image.read(0x248088, 36))
        self.assertEqual(table[7], 0x247E0E)                         # stage 8 (the switch takes stage - 1)
        self.assertEqual(table.count(0x247E0E), 1)


@lru_cache(maxsize=1)
def _candidate():
    _need(CANDIDATE, CANDIDATE_SHA)
    return CANDIDATE.read_bytes()


class TradesAllocation(unittest.TestCase):
    """C20 (1b): 0x152C000..0x152CFFF is the trades page's in every order; the room never moves; nothing else moves."""

    def test_trades_sits_at_its_fixed_page_with_or_without_the_room_in_any_order(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        union = [r for r in space.dormant_union() if r[0] not in space.QB_FIXED_OWNERS]
        base = {(r["owner"], r["kind"]): r["va"] for r in space.plan(union)["allocations"]}
        for extra in ([space.QB_ROOM_REQUEST], [space.QB_TRADES_REQUEST], [space.QB_ROOM_REQUEST, space.QB_TRADES_REQUEST],
                      [space.QB_TRADES_REQUEST, space.QB_ROOM_REQUEST]):
            with self.subTest(extra=[r[0] for r in extra]):
                rows = {(r["owner"], r["kind"]): r["va"] for r in space.plan(union + extra)["allocations"]}
                self.assertEqual({k: rows[k] for k in base if k[0] != space.DIRECTORY_OWNER},
                                 {k: v for k, v in base.items() if k[0] != space.DIRECTORY_OWNER})
                if space.QB_ROOM_REQUEST in extra:
                    self.assertEqual(rows[(space.QB_ROOM_OWNER, "code")], 0x1529000)
                if space.QB_TRADES_REQUEST in extra:
                    self.assertEqual(rows[(space.QB_TRADES_OWNER, "code")], 0x152C000)
        alone = space.plan([space.QB_TRADES_REQUEST])["allocations"]
        self.assertEqual(next(r["va"] for r in alone if r["owner"] == space.QB_TRADES_OWNER), 0x152C000)

    def test_no_other_owner_lands_in_the_span_in_any_order(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        filler = ("aa_synthetic_filler", "code", 0x152C000 - 0x80 - space.POOL_VA - space.PAGE, space.PAGE)
        straddle = ("ab_synthetic_straddle", "code", 0x800, 16)
        for fixed in ([], [space.QB_ROOM_REQUEST], [space.QB_TRADES_REQUEST], [space.QB_ROOM_REQUEST, space.QB_TRADES_REQUEST]):
            with self.subTest(fixed=[r[0] for r in fixed]):
                rows = space.plan([filler, straddle] + fixed)["allocations"]
                for row in rows:
                    if row["owner"] not in space.QB_FIXED_OWNERS and row["owner"] != filler[0]:
                        self.assertFalse(row["va"] < 0x152D000 and row["va"] + row["size"] > 0x1529000, row)

    def test_a_foreign_trades_request_is_refused(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        for request in ((space.QB_TRADES_OWNER, "code", 0x2000, 0x1000), (space.QB_TRADES_OWNER, "data", 0x1000, 0x1000)):
            with self.subTest(request=request), self.assertRaisesRegex(ValueError, "trades"):
                space.plan([request])


class TradesOwner(unittest.TestCase):
    def test_bit_16_installs_the_trades_page_at_0x152c000_and_retail_restores_both(self):
        from mod_editor.core import nfl2k5_qb_room as room, nfl2k5_qb_trades as trades, nfl2k5_xbe_space as space
        # f5270f4d carries b2672e398's page, a previous revision since C21: Realistic brings it to this page first.
        source, _ = room.apply(_candidate(), "realistic", stages=67)
        self.assertEqual((room.status(source), trades.status(source)), ("applied", "retail"))
        out, receipt = room.install_stages(source, 67 | 16, shadow=True)
        self.assertEqual(room.read_settings(out)["trades"], "applied")
        self.assertEqual(trades.status(out), "applied")
        rows = {(r["owner"], r["kind"]): r for r in space.layout(out)["allocations"]}
        self.assertEqual(rows[(trades.OWNER, "code")]["va"], 0x152C000)
        before = {(r["owner"], r["kind"]): r["va"] for r in space.layout(source)["allocations"]}
        self.assertEqual({k: rows[k]["va"] for k in before}, before)          # no row moves, the room included
        self.assertIn("0x247e1e", receipt["sites"])
        back, _ = room.apply(out, "retail")
        self.assertEqual(trades.status(back), "retail")
        self.assertEqual(room.status(back), "retail")
        again, _ = room.install_stages(back, 67)
        self.assertEqual(again[:len(source)], source[:len(source)] if len(again) == len(source) else again[:len(source)])
        self.assertEqual(trades.status(again), "retail")

    def test_trades_bytes_without_bit_16_or_bit_16_without_trades_read_foreign(self):
        from mod_editor.core import nfl2k5_qb_room as room, nfl2k5_qb_trades as trades
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        source = _candidate()
        out, _ = room.install_stages(source, 67 | 16)
        image = XbeImage(out)
        at, original, _patched = trades._code().site(trades.VA)
        site_back = bytearray(out)                                  # bit 16 in the room, the trades site retail
        site_back[image.offset(at, 5):image.offset(at, 5) + 5] = original
        self.assertEqual(room.status(bytes(site_back)), "foreign")
        self.assertEqual(trades.status(bytes(site_back)), "foreign")
        page_gone = bytearray(out)                                  # bit 16 in the room, the trades page emptied
        page_gone[image.offset(trades.VA, trades.SIZE):image.offset(trades.VA, trades.SIZE) + trades.SIZE] = \
            b"\xcc" * trades.SIZE
        self.assertEqual(room.status(bytes(page_gone)), "foreign")
        without, _ = room.install_stages(source, 67)                # trades bytes while the room has no bit 16
        both = bytearray(without)
        extended, _ = room.install_stages(source, 67 | 16)
        self.assertEqual(room.status(without), "applied")
        bad, _ = room.apply(extended, "retail")
        bad = bytearray(bad)
        image = XbeImage(bytes(bad))
        bad[image.offset(trades.VA, trades.SIZE):image.offset(trades.VA, trades.SIZE) + trades.SIZE] = trades.page(0)
        self.assertEqual(room.status(bytes(bad)), "foreign")

    def test_bit_16_needs_the_deadline_ownership_ir_economy_and_practice_squad(self):
        from mod_editor.core import nfl2k5_qb_room as room
        from unittest import mock
        source = _candidate()
        self.assertEqual(room.requirements(source, 67 | 16), [])
        with mock.patch("mod_editor.core.nfl2k5_trade_deadline.status", return_value="retail"):
            self.assertIn("Quarterback trades need the NFL week 9 trade deadline.", room.requirements(source, 67 | 16))
        with self.assertRaises(ValueError):
            with mock.patch("mod_editor.core.nfl2k5_trade_deadline.status", return_value="retail"):
                room.install_stages(source, 67 | 16)

    def test_the_trades_shadow_flag_installs_reads_back_and_restores(self):
        from mod_editor.core import nfl2k5_qb_room as room, nfl2k5_qb_trades as trades
        source = _candidate()
        out, receipt = room.install_stages(source, 67 | 16, trades_shadow=True)
        settings = room.read_settings(out)
        self.assertEqual((settings["shadow"], settings["trades_shadow"], receipt["trades_shadow"]), (False, True, True))
        self.assertEqual(trades.state(out)[2], True)
        acting, _ = room.install_stages(out, 67 | 16)
        self.assertEqual(room.read_settings(acting)["trades_shadow"], False)
        back, _ = room.apply(out, "retail")
        self.assertEqual((room.status(back), trades.status(back)), ("retail", "retail"))
        with self.assertRaises(ValueError):
            room.install_stages(source, 67, trades_shadow=True)

    def test_the_studio_never_writes_bit_16(self):
        from mod_editor.core import nfl2k5_qb_room as room
        self.assertFalse(room.realistic_stages() & 16)
        self.assertFalse(room.studio_stages(True, True) & 16)
        self.assertFalse(room.REALISTIC_STAGES & 16)


if __name__ == "__main__":
    unittest.main()
