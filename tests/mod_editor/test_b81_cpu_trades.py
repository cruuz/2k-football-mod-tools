"""CPU trades at every position (beta 81, owner nfl2k5_cpu_trades; the trades-all lane's DESIGN.md, RULINGS.md and the
design-review rulings M1-M3, S1-S10, N1-N8).

Image tests (CpuTradesImage): the pages linked at 0x152E000 and both sites (0x2BC96C, 0x2BB296) patched into a kept
regular-season opening (a season-panel checkpoint of the 4b hand-over run: 2027, stage 8, week counter 0, the Trade
Deadline option off, the quarterback room at 383), entered as the game enters them: the native trade pass 0x2BC960
(ECX = 3 proposers, EDX = the menu), whose pending-scan call is the site. The packages are recomputed here from the
design in Python (the shared need header's Python mirror; ratings, charges and the release choice from the game's own
routines on an untouched twin of the same state) and compared with the page's ring rows; every executed trade is then
checked against the hard rules (no club a person manages, no QB/K/P, healthy, 2+ years pro, the seller keeps its seats
and its cut minimum, roster counts, the buyer's cap after the trade (M1), the pick changes owner from buyer to seller,
the rows of both clubs repaired (S9), nothing of ours left on the board).

Fixtures come from the environment only (no private paths in the repo): CPU_TRADES_IMAGE (a .b81mem.gz opening) and
CPU_TRADES_IMAGE_XBE (the executable it was made with). Without them the image classes skip.

SignedRoundTrip (N8): a signed franchise in its third season (NFL2K5_B81_STABILITY_FIXTURES, the pinned save of
test_b81_sim_pos_injury_signed.py) cold-loaded natively on CPU_TRADES_STANDARD_XBE with the pages installed; one trade
pass executes trades, the game writes and signs the franchise, a second machine cold-loads that save, and the next pass
on the live machine and on the cold load must decide the same trades and leave the same players, clubs, picks, ledger
and board (ledger rows are pointers in RAM; the save stores them as indices).

PagesAndOwner: the byte interface and the owner (install, Retail, foreign, needs, the unowned range) on
CPU_TRADES_STANDARD_XBE, a standard executable carrying the needs (else skip). Allocation: the fixed pages and the
step-over, no fixture. Every class fails on c4406481b: there is no nfl2k5_cpu_trades owner, code module or allocation.
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
import unittest

from tests.nfl2k5_supersim_draft_fixture import HAVE_UC

IMAGE = os.environ.get("CPU_TRADES_IMAGE", "")
IMAGE_XBE = os.environ.get("CPU_TRADES_IMAGE_XBE", "")
MIDSEASON = os.environ.get("CPU_TRADES_MIDSEASON_IMAGE", "")
MIDSEASON_XBE = os.environ.get("CPU_TRADES_MIDSEASON_XBE", "")
STANDARD_XBE = os.environ.get("CPU_TRADES_STANDARD_XBE", "")
VA = 0x152E000
BOARD, RECORD = 0xE3C27C, 0x3C
PICKS = 0xE3C094
STAGE, WEEK, YEAR = 0xE576A4, 0xE576B4, 0xE576B8
USER_FLAG = 0xE5775C
LEDGER, LEDGER_CURSOR = 0xE3F070, 0xE3F06C
DEADLINE_BYTE = 0x5151C5
CAP = 0xE3C278
PROBE = 0x3200000
CUT_MAX = (3, 30, 30, 30, 30, 30, 30, 30, 2, 30, 0, 30, 30, 30, 30, 30, 30)
CUT_KEEP = (2, 30, 30, 6, 6, 2, 2, 3, 1, 3, 0, 5, 2, 3, 4, 4, 4)
WEEK_WEIGHT = (1, 1, 1, 1, 2, 2, 2, 4, 8)
POOL_WEIGHT = ((0, 0, 0, 16, 16, 16, 16, 16, 0, 10, 0, 16, 5, 5, 5, 16, 16),
               (0, 0, 0, 12, 16, 16, 16, 4, 0, 8, 0, 14, 12, 12, 12, 10, 10))


def _code():
    from mod_editor.core import nfl2k5_cpu_trades_code as code
    return code


def _tn():
    from mod_editor.core import nfl2k5_team_need as tn
    return tn


def fmix(h):
    h ^= h >> 16
    h = h * 0x85EBCA6B & 0xFFFFFFFF
    h ^= h >> 13
    h = h * 0xC2B2AE35 & 0xFFFFFFFF
    return h ^ h >> 16


def draw(words):
    h = 0x43505454
    for w in words:
        h = fmix(h ^ (w & 0xFFFFFFFF))
    return h % 1000000


def _fixture(path):
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("CPU_TRADES_IMAGE / CPU_TRADES_IMAGE_XBE / CPU_TRADES_STANDARD_XBE not set or absent")
    return Path(path)


class Image:
    """A kept image on its executable with the CPU trades pages and both sites written in (the 4b tests' method)."""

    def __init__(self, image=None, xbe=None):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        from tools import franchise_invariants as fi
        image, xbe = _fixture(image or IMAGE), _fixture(xbe or IMAGE_XBE)
        self.memory = fi.load_memory(image)
        self.m = m = Machine(xbe.read_bytes(), trace_writes=False)
        for lo, data in self.memory.regions:
            if lo < 0x3000000:
                m.uc.mem_write(lo, data)
        try:
            m.uc.mem_map(VA, 0x2000)
        except Exception:                                  # the executable's pool already covers the pages
            pass
        m.uc.mem_map(PROBE, 0x1000)
        self.root = m.get(0xB72918)
        self.teams = m.get(self.root + 0x1C)
        self.table = m.get(self.root + 4)
        self._ratings = {}

    def install(self, stages=7, *, shadow=False, p8=1_000_000, p7=1_000_000):
        code = _code()
        self.m.uc.mem_write(VA, code.page_bytes(VA, code.settings_record(stages, shadow=shadow, p8_ppm=p8, p7_ppm=p7)))
        for at, _original, patched in code.sites(VA):
            self.m.uc.mem_write(at, patched)
        self.m.uc.ctl_flush_tb()

    def b(self, at):
        return self.m.uc.mem_read(at, 1)[0]

    def h(self, at):
        return struct.unpack("<H", bytes(self.m.uc.mem_read(at, 2)))[0]

    def rec(self, p):
        return bytes(self.m.uc.mem_read(p, 0x54))

    def club(self, i):
        return self.teams + 500 * i

    def roster(self, i):
        team = self.club(i)
        return [self.m.get(team + 4 * k) for k in range(self.b(team + 0x11C))]

    def _float_call(self, address, p, flag):
        code = (b"\xb9" + struct.pack("<I", p) + b"\xba" + struct.pack("<I", flag) + b"\xb8" + struct.pack("<I", address)
                + b"\xff\xd0\xd9\x1d" + struct.pack("<I", PROBE + 0x800) + b"\xc3")
        self.m.uc.mem_write(PROBE, code)
        self.m.uc.ctl_flush_tb()
        self.m.call(PROBE, budget=2_000_000)
        return struct.unpack("<f", bytes(self.m.uc.mem_read(PROBE + 0x800, 4)))[0], self.m.get(PROBE + 0x800)

    def rating(self, p):
        if p not in self._ratings:
            self._ratings[p] = _tn().points(self._float_call(0x246D80, p, 0)[1])
        return self._ratings[p]

    def rating1(self, p):
        return self._float_call(0x246D80, p, 1)[0]

    def record(self, i):
        team = self.club(i)
        return tuple(self.m.call(at, ecx=team, budget=5_000_000) for at in (0xC7720, 0xC7750, 0xC7780))

    def charge_after(self, p):
        """M1: 0x2BB360's contract (owed bonus folded into the value, bonus cleared) on a copy; 0xE6380 on the copy."""
        m = self.m
        money = (m.call(0xE5FF0, ecx=self.h(p + 0xA), budget=2_000_000) - m.call(0x13ED00, ecx=p, budget=2_000_000)) \
            & 0xFFFFFFFF
        copy = bytearray(self.rec(p))
        struct.pack_into("<I", copy, 0x24, struct.unpack_from("<I", copy, 0x24)[0] & 0xFF0FFFFF)
        struct.pack_into("<H", copy, 0xA, m.call(0xE6000, ecx=money, budget=2_000_000) & 0xFFFF)
        m.uc.mem_write(PROBE + 0x400, bytes(copy))
        return m.call(0xE6380, ecx=PROBE + 0x400, budget=2_000_000)

    def pick_owner(self, word):
        from mod_editor.core import nfl2k5_trade_picks as picks
        return self.b(picks.owner_address(word))

    def board(self):
        return [bytes(self.m.uc.mem_read(BOARD + RECORD * s, RECORD)) for s in range(15)]

    def page(self):
        return bytes(self.m.uc.mem_read(VA, 0x2000))

    def open_places(self, clubs):
        """Give these clubs a vacancy the way the season does (the game's own release 0x2BD900 of their last-listed
        player outside QB, K and P, to the free-agent list)."""
        for i in clubs:
            team = self.club(i)
            p = next(p for p in reversed(self.roster(i)) if self.b(p + 0x35) > 2)
            self.m.call(0x2BD900, ecx=team, edx=p, args=(1, 1), budget=20_000_000)
            assert p not in self.roster(i)

    def run(self):
        """The native trade pass, as the weekly advance calls it (ECX = 3, EDX = the menu); our site is inside it."""
        m = self.m
        m.uc.mem_write(m.STACK, struct.pack("<I", m.STOP))
        for k, v in dict(ESP=m.STACK, ECX=3, EDX=m.ARENA + 0x1A0000, EBX=0x11111111, ESI=0x22222222, EDI=0x33333333,
                         EBP=0x44444444, EFLAGS=0x202).items():
            m.reg(k, v)
        m.uc.emu_start(0x2BC960, m.STOP, count=2_000_000_000)
        assert m.reg("EIP") == m.STOP
        assert [m.reg(r) for r in ("EBX", "ESI", "EDI", "EBP", "ESP")] == [0x11111111, 0x22222222, 0x33333333,
                                                                           0x44444444, m.STACK + 4]

    # ---- the design, in Python (the header's mirror) ---------------------------------------------------------------
    def ledger(self):
        """(trade groups per club, players named by a signing or trade row)."""
        m = self.m
        cursor, mask, load, named = m.get(LEDGER_CURSOR), 0, [0] * 32, set()
        for k in range(600):
            at = LEDGER + 12 * ((cursor + k) % 600)
            word, player, team = m.get(at), m.get(at + 4), m.get(at + 8)
            if word & 31 in (1, 7):
                named.add(player)
            if word & 31 != 7:
                mask = 0
                continue
            if team >= self.teams and (team - self.teams) % 500 == 0 and (team - self.teams) // 500 < 32:
                mask |= 1 << ((team - self.teams) // 500)
            if word & 0x80000000:
                for i in range(32):
                    if mask >> i & 1:
                        load[i] += 1
                mask = 0
        return load, named

    def board_names(self):
        m, clubs, players = self.m, set(), set()
        for s in range(15):
            rec = BOARD + RECORD * s
            kind = m.get(rec)
            if not kind:
                continue
            players |= {m.get(rec + o) for o in (0xC, 0x10, 0x14, 0x24, 0x28, 0x2C)}
            if kind > 1:
                clubs |= {m.get(rec + 8), m.get(rec + 0x20)}
        return clubs, players

    def pool(self, p):
        pos = self.b(p + 0x35)
        return _tn().POOL[pos] if pos < 17 else None

    def seated(self, i, p):
        tn, ros = _tn(), self.roster(i)
        pool = self.pool(p)
        if pool is None or not tn.present(self.rec(p)):
            return False
        mine = ros.index(p)
        before = sum(1 for j, o in enumerate(ros) if o != p and self.pool(o) == pool and tn.present(self.rec(o))
                     and (tn.row(self.rec(o)) < tn.row(self.rec(p))
                          or (tn.row(self.rec(o)) == tn.row(self.rec(p)) and j < mine)))
        return before < tn.SEATS[pool]

    def scan(self, i):
        """(weak per pool, present per pool, best, healthy quarterbacks, need-seat ratings per pool) as the page's
        scan(); the need-seat ratings are the first NEED_SEATS present men by row, an empty seat 0."""
        tn = _tn()
        weak, present, best, qbs = [0] * 17, [0] * 17, 0, 0
        lists = [[] for _ in range(17)]
        for o in self.roster(i):
            pool = self.pool(o)
            if pool is None:
                continue
            r = self.rating(o)
            best = max(best, r)
            if pool == 0 and tn.healthy(self.rec(o)):
                qbs += 1
            if not tn.present(self.rec(o)):
                continue
            present[pool] += 1
            lists[pool].append((tn.row(self.rec(o)), r))
        need = [[] for _ in range(17)]
        for p in range(17):
            seats = tn.NEED_SEATS[p]
            men = sorted(lists[p], key=lambda t: t[0])[:4]          # stable: ties keep list order, as the page
            need[p] = ([r for _row, r in men] + [0, 0])[:seats]
            weak[p] = min(need[p]) if seats else 0
        return weak, present, best, qbs, need

    def release_of(self, i, pool, ledger_players, board_players):
        tn, ros = _tn(), self.roster(i)
        counts = {}
        for o in ros:
            counts[self.pool(o)] = counts.get(self.pool(o), 0) + 1
        for tier in range(3):
            best = None
            for p in ros:
                at = self.pool(p)
                if at is None or at <= 2:
                    continue
                count = counts[at] + (at == pool)
                limit = (CUT_MAX, CUT_KEEP, tn.CUT_MIN)[tier][at]
                if count <= limit or self.seated(i, p) or p in board_players or p in ledger_players:
                    continue
                length = self.b(p + 0x27) & 15
                small = self.h(p + 0xA) <= 60 * (length or 1)
                key = (not small, self.rating1(p))
                if best is None or key < best[0]:
                    best = (key, p)
            if best:
                return best[1]
        return None


def offer_of(x, s, stage, pool, floor, above, room, q, club, rebuild_ok, board_players, ledger_players):
    """The design's man from seller s, or None; returns (player, rating, rebuild sale)."""
    tn = _tn()
    ros = x.roster(s)
    count = sum(1 for p in ros if x.pool(p) == pool)
    top = max([x.rating(p) for p in ros if x.pool(p) == pool] or [0])
    if count < tn.CUT_MIN[pool] + 1 or club["present"][pool] < tn.SEATS[pool] + 1:
        return None
    margin = 2 * ((885 + 45 * min(x.m.get(YEAR), 4) + 3) // 4)
    out, best_r = None, above
    for p in ros:
        if x.pool(p) != pool:
            continue
        rec = x.rec(p)
        pro, left, length = rec[0x25] & 31, rec[0x24] & 15, rec[0x27] & 15
        if not tn.healthy(rec) or pro < 2 or not left:
            continue
        if stage == 7 and x.m.get(YEAR) and left == length:
            continue
        r = x.rating(p)
        if rec[0x53] & 1 or r >= club["best"] or (tn.PREMIUM[pool] and r >= top) or r >= q[3] \
                or (pro <= tn.YOUNG_YEARS and r > q[1]):
            continue
        sale_rebuild = x.seated(s, p)
        if sale_rebuild and (not rebuild_ok or pro < 8):
            continue
        if r < floor or r <= best_r:
            continue
        if room - x.charge_after(p) < margin:
            continue
        if p in board_players or p in ledger_players:
            continue
        out, best_r = (p, r, sale_rebuild), r
    return out


def model(x, stage, rows, *, round2=0, rebuild_bit=True, p8=1_000_000, p7=1_000_000):
    """Every buyer's package in the page's order that the draw lets through: [(buyer, seller, player, pool, hash)].
    `rows` are the page's before-scan rows of this round: a posted or would-post row makes both clubs used."""
    tn, m = _tn(), x.m
    year, week = m.get(YEAR), m.get(WEEK)
    kind = 1 if stage == 7 else 0
    load, ledger_players = x.ledger()
    board_clubs, board_players = x.board_names()
    clubs = []
    for i in range(32):
        team = x.club(i)
        weak, present, best, qbs, need = x.scan(i)
        paid = sum(1 for r in range(1, 8) if x.b(PICKS + 32 * r + i) != i)
        c = dict(weak=weak, need=need, present=present, best=best, qbs=qbs, paid=paid, active=x.b(team + 0x11C),
                 out=bool(m.get(USER_FLAG + 4 * i)) or team in board_clubs, seller=False, rebuild=False, buyer=False,
                 used=False, w=0, l=0, t=0)
        clubs.append(c)
    q, pct = [], [[0] * 17 for _ in range(32)]
    for p in range(17):
        if not tn.NEED_SEATS[p]:
            q.append((0, 0, 0, 0))
            continue
        v = tn.league_scale(c["need"][p] for c in clubs)              # the header's scale: every need-seat starter
        n = len(v)
        q.append((v[n // 4], v[n // 2], v[3 * n // 4], v[9 * n // 10]))
        for i, c in enumerate(clubs):
            pct[i][p] = tn.percentile(v, c["weak"][p])
    for i, c in enumerate(clubs):
        if c["out"]:
            continue
        if load[i] >= 3:
            c["out"] = True
            continue
        if stage == 8:
            c["w"], c["l"], c["t"] = x.record(i)
        if c["active"] >= 51:
            c["seller"] = True
            c["rebuild"] = stage == 8 and rebuild_bit and c["w"] + c["l"] + c["t"] >= 4 and c["l"] >= c["w"] + 3
        if (stage == 8 and c["w"] + 1 < c["l"]) or c["paid"] >= 3 or c["qbs"] < 2:
            continue
        c["buyer"] = True
    threshold = p8 // 2 * WEEK_WEIGHT[min(week, 8)] if stage == 8 else p7
    start = fmix((year * 131 + week * 7 + stage + round2 * 977) & 0xFFFFFFFF) % 32
    packages, by_buyer = [], {r["buyer"]: r for r in rows}
    for k in range(32):
        b = (start + k) % 32
        c = clubs[b]
        if not c["buyer"] or c["used"]:
            continue
        room = (m.get(CAP) - m.get(x.club(b) + 0x124)) & 0xFFFFFFFF
        room = room - (1 << 32) if room >= 1 << 31 else room
        tried, choice, top = set(), None, 0
        for _n in range(3):
            if choice:
                break
            need, low, depth = None, 256, False
            for p in range(1, 17):
                thin = stage == 7 and tn.NEED_SEATS[p] and c["present"][p] < tn.SEATS[p] + 1
                if not tn.NEED_SEATS[p] or p in tried or not POOL_WEIGHT[kind][p]:
                    continue
                if (pct[b][p] < 64 or thin) and pct[b][p] < low:
                    need, low, depth = p, pct[b][p], pct[b][p] >= 64
            if need is None:
                break
            tried.add(need)
            floor = max(q[need][0] - 8, 0) if depth else max(c["weak"][need] + 3, q[need][0])
            for s in range(32):
                sc = clubs[s]
                if s == b or not sc["seller"] or sc["used"] or sc["out"]:
                    continue
                got = offer_of(x, s, stage, need, floor, top, room, q[need], sc, sc["rebuild"], board_players,
                               ledger_players)
                if got:
                    choice, top = (s, got[0], need), got[1]
        if not choice:
            continue
        s, p, pool = choice
        rec = x.rec(p)
        r = x.rating(p)
        ruled = 3 if r >= q[pool][2] else 4 if r >= q[pool][1] else 5 if r >= q[pool][0] else 6
        ruled = min(ruled + ((rec[0x25] & 31) >= 9) + ((rec[0x24] & 15) == 1) + (stage == 7), 7)
        has_pick = any(x.b(PICKS + 32 * rnd + b) == b for rnd in (ruled, ruled - 1) if rnd >= 2)
        h = draw([9, b, pool, year, stage, week, (p - x.table) // 0x54, c["w"], c["l"]])
        if has_pick and h >= threshold // 16 * POOL_WEIGHT[kind][pool]:
            continue                                                    # KEPT: counted only, no row
        packages.append((b, s, p, pool, h))
        row = by_buyer.get(b)
        if row is not None and row["result"] in (1, 2):
            c["used"] = clubs[s]["used"] = True
    return packages, q


@unittest.skipUnless(HAVE_UC, "Unicorn is required")
class CpuTradesImage(unittest.TestCase):
    PLACES = tuple(range(0, 32, 4))         # some clubs with a vacancy, the rest at 53 (they release a man: M3)

    def fresh(self):
        x = Image()
        x.m.put(WEEK, 8)                    # the last open week (weight 8: every draw fires at p8 = 1,000,000)
        x.open_places(self.PLACES)
        return x

    def setUp(self):
        self.x = self.fresh()
        m = self.x.m
        self.assertEqual(m.get(STAGE), 8)
        self.assertEqual(self.x.b(DEADLINE_BYTE), 9)
        self.assertGreaterEqual(m.get(YEAR), 1)

    def rows(self, after=False, page=None):
        events = _code().events(page or self.x.page())
        return [e for e in events if bool(e["flags"] & 0x40) == after]

    def counters(self, page=None):
        return _code().counters(page or self.x.page())

    def test_packages_follow_the_design_and_every_executed_trade_keeps_the_rules(self):
        x, m = self.x, self.x.m
        tn = _tn()
        x.install(7)
        before = {i: x.roster(i) for i in range(32)}
        records = {p: x.rec(p) for i in range(32) for p in before[i]}
        twin = self.fresh()
        x.run()
        rows, after = self.rows(), self.rows(after=True)
        self.assertTrue(rows, "no buyer found a package on this image")
        first = [r for r in rows if not r["flags"] & 8]
        packages, q = model(twin, 8, first)
        self.assertEqual([(r["buyer"], r["seller"], r["player"], r["position"]) for r in first],
                         [(b, s, (p - x.table) // 0x54, pool) for b, s, p, pool, _h in packages])
        executed = [r for r in after if r["result"] == 1]
        self.assertTrue(executed, "nothing was executed")
        for r in executed:
            p = x.table + 0x54 * r["player"]
            rec = records[p]
            buyer, seller = r["buyer"], r["seller"]
            self.assertIn(p, x.roster(buyer))
            self.assertNotIn(p, x.roster(seller))
            self.assertEqual(m.get(USER_FLAG + 4 * buyer) | m.get(USER_FLAG + 4 * seller), 0)
            self.assertNotIn(rec[0x35], (0, 1, 2))
            self.assertGreaterEqual(rec[0x25] & 31, 2)
            self.assertFalse(rec[0x53] & 1)
            self.assertTrue(tn.healthy(rec))
            self.assertLessEqual(len(x.roster(buyer)), 53)
            self.assertGreaterEqual(len(x.roster(seller)), 50)
            pool = tn.POOL[rec[0x35]]
            present = [o for o in x.roster(seller) if x.pool(o) == pool and tn.present(x.rec(o))]
            self.assertGreaterEqual(len(present), tn.SEATS[pool])
            self.assertGreaterEqual(sum(1 for o in x.roster(seller) if x.pool(o) == pool), tn.CUT_MIN[pool])
            # S8: nothing else moved at either club in this call (one trade per club per call, a native swap included)
            self.assertEqual(set(x.roster(buyer)) - set(before[buyer]), {p})
            self.assertLessEqual(len(set(before[buyer]) - set(x.roster(buyer))), 1)
            self.assertEqual((set(before[seller]) - set(x.roster(seller)), set(x.roster(seller)) - set(before[seller])),
                             ({p}, set()))
            self.assertEqual(x.pick_owner(r["word"]), seller)
            self.assertNotEqual(r["word"] & 0x3F, 1)                          # never a 1st (N3)
            self.assertLessEqual(m.get(x.club(buyer) + 0x124), m.get(CAP))    # M1: never over the cap
            for club in (buyer, seller):                                       # S9: rows 0..n-1 at the pool, no gap
                was = sorted(tn.row(records[o]) for o in before[club] if o != p and tn.POOL[records[o][0x35]] == pool)
                if club == seller:
                    was = sorted(tn.row(records[o]) for o in before[club] if tn.POOL[records[o][0x35]] == pool)
                if was != [min(k, 7) for k in range(len(was))]:
                    continue                                                   # the chart had a gap already
                rows_now = sorted(tn.row(x.rec(o)) for o in x.roster(club) if x.pool(o) == pool)
                self.assertEqual(rows_now, [min(k, 7) for k in range(len(rows_now))], (club, rows_now))
            gone = [o for o in before[buyer] if o not in x.roster(buyer)]
            for o in gone:                                                     # M3: the released man
                self.assertNotIn(records[o][0x35], (0, 1, 2))
                vpool = tn.POOL[records[o][0x35]]                              # S9: his pool's rows closed up too
                was = sorted(tn.row(records[k]) for k in before[buyer] if tn.POOL[records[k][0x35]] == vpool)
                if was == [min(k, 7) for k in range(len(was))]:
                    rows_now = sorted(tn.row(x.rec(k)) for k in x.roster(buyer) if x.pool(k) == vpool)
                    self.assertEqual(rows_now, [min(k, 7) for k in range(len(rows_now))], (buyer, vpool, rows_now))
        clubs = [k for r in executed for k in (r["buyer"], r["seller"])]
        self.assertEqual(len(clubs), len(set(clubs)), "a club in two of our trades in one call")
        ours = {x.table + 0x54 * r["player"] for r in rows}
        for rec in x.board():
            kind, player = struct.unpack_from("<I", rec, 0)[0], struct.unpack_from("<I", rec, 0xC)[0]
            self.assertFalse(kind == 2 and player in ours)
        c = self.counters()
        self.assertEqual(c["posted"], c["executed"] + c["cancelled"] + c["gone"])
        self.assertEqual(c["stories_forced"], c["executed"])                  # S7: every executed trade of ours

    def test_the_post_trade_charge_is_what_the_buyer_pays(self):
        """M1: the buyer's payroll rises by the predicted charge (0x2BB360's contract) for every executed trade."""
        x, m = self.x, self.x.m
        x.install(7)
        twin = self.fresh()
        payroll = {i: m.get(x.club(i) + 0x124) for i in range(32)}
        rosters = {i: set(x.roster(i)) for i in range(32)}
        predicted = {}
        x.run()
        for r in self.rows(after=True):
            if r["result"] != 1:
                continue
            p = twin.table + 0x54 * r["player"]
            if set(x.roster(r["buyer"])) == rosters[r["buyer"]] | {p}:      # nothing else moved (a release, a native trade)
                predicted[r["buyer"]] = twin.charge_after(p)
        self.assertTrue(predicted)
        for buyer, charge in predicted.items():
            self.assertEqual(m.get(x.club(buyer) + 0x124) - payroll[buyer], charge, buyer)

    def test_the_cap_test_charges_the_contract_the_trade_writes(self):
        """M1: a buyer whose room covers this season's salary but not the contract the executor writes (owed bonus folded
        in) does not get the man; the model with the same payroll agrees."""
        x = self.x
        x.install(7)
        twin = self.fresh()
        x.run()
        found = None
        for r in [r for r in self.rows() if r["result"] == 1 and not r["flags"] & 8]:
            p = twin.table + 0x54 * r["player"]
            fold, base = twin.charge_after(p), twin.m.call(0xE6380, ecx=p, budget=2_000_000)
            if fold > base:
                found = r, fold, base
                break
        if found is None:
            self.skipTest("no man posted on this image has an owed bonus to fold")
        r, fold, base = found
        y, z = self.fresh(), self.fresh()
        margin = 2 * ((885 + 45 * min(y.m.get(YEAR), 4) + 3) // 4)
        for image in (y, z):
            image.m.put(image.club(r["buyer"]) + 0x124, image.m.get(CAP) - (fold + margin - 1))
        y.install(7)
        y.run()
        first = [e for e in _code().events(y.page()) if not e["flags"] & 0x48]
        self.assertNotIn((r["buyer"], r["player"]), [(e["buyer"], e["player"]) for e in first if e["result"] in (1, 2)])
        packages, _q = model(z, 8, first)
        self.assertEqual([(e["buyer"], e["player"]) for e in first],
                         [(b, (p - z.table) // 0x54) for b, _s, p, _pool, _h in packages])

    def test_prices_follow_the_ladder_and_picks_were_the_buyers(self):
        x, m = self.x, self.x.m
        owner_before = {rnd | s << 6: x.pick_owner(rnd | s << 6) for rnd in range(1, 8) for s in range(32)}
        records = {x.table + 0x54 * k: x.rec(x.table + 0x54 * k) for k in range(m.get(x.root))}
        twin = self.fresh()
        x.install(7)
        x.run()
        _packages, q = model(twin, 8, [r for r in self.rows() if not r["flags"] & 8])
        seen = 0
        for r in self.rows():
            if r["result"] == 3:
                continue
            seen += 1
            rec = records[x.table + 0x54 * r["player"]]
            q25, q50, q75, _q90 = q[r["position"]]
            rating = r["rating"]
            ruled = 3 if rating >= q75 else 4 if rating >= q50 else 5 if rating >= q25 else 6
            ruled = min(ruled + ((rec[0x25] & 31) >= 9) + ((rec[0x24] & 15) == 1), 7)
            own = lambda rnd: owner_before[rnd | r["buyer"] << 6] == r["buyer"]
            expected = ruled if own(ruled) else ruled - 1                       # the ruled round, else one earlier
            self.assertEqual(r["word"] & 0x3F, expected, (r, ruled))
            self.assertTrue(own(expected))
            self.assertGreaterEqual(r["word"] & 0x3F, 2)
            self.assertEqual(r["word"] >> 6 & 0x3F, r["buyer"])               # its own pick
            self.assertEqual(owner_before[r["word"]], r["buyer"])
            self.assertEqual(r["word"] >> 12, 0)
        self.assertTrue(seen)

    def test_a_club_a_person_manages_is_never_a_buyer_or_a_seller(self):
        x, m = self.x, self.x.m
        x.install(7)
        x.run()
        first = [(r["buyer"], r["seller"]) for r in self.rows(after=True) if r["result"] == 1]
        self.assertTrue(first)
        self.x = y = self.fresh()
        managed = {c for pair in first for c in pair}
        for c in managed:
            y.m.put(USER_FLAG + 4 * c, 1)
        y.install(7)
        y.run()
        for r in _code().events(y.page()):
            self.assertNotIn(r["buyer"], managed)
            self.assertNotIn(r["seller"], managed)

    def test_nothing_at_or_after_the_deadline_week_or_in_the_playoffs_or_with_the_bit_off(self):
        x, m = self.x, self.x.m
        x.install(7)
        m.put(WEEK, 9)
        x.run()
        self.assertEqual((self.counters()["past_deadline"], self.counters()["rounds"]), (1, 0))
        m.put(WEEK, 8)
        x.install(2 | 4)
        x.run()
        self.assertEqual((self.counters()["inactive"], self.counters()["rounds"]), (1, 0))
        x.install(7)
        m.put(STAGE, 9)
        x.run()
        self.assertEqual((self.counters()["inactive"], self.counters()["rounds"]), (1, 0))
        self.assertEqual(_code().events(x.page()), [])

    def test_no_trades_in_the_opening_preseason_of_a_new_franchise(self):
        """S10: stage 7 of year index 0 posts nothing (the opening rosters stay the real ones)."""
        x, m = self.x, self.x.m
        m.put(STAGE, 7)
        m.put(YEAR, 0)
        x.install(7)
        x.run()
        self.assertEqual((self.counters()["opening_preseason"], self.counters()["rounds"]), (1, 0))

    def test_preseason_posts_with_bit_2_depth_deals_and_obeys_the_camp_limits(self):
        x, m = self.x, self.x.m
        m.put(STAGE, 7)
        x.install(1 | 4)
        x.run()
        self.assertEqual(self.counters()["inactive"], 1)
        self.x = y = self.fresh()
        y.m.put(STAGE, 7)
        twin = self.fresh()
        twin.m.put(STAGE, 7)
        y.install(2)
        y.run()
        rows = [r for r in _code().events(y.page()) if not r["flags"] & 0x40]
        self.assertTrue(rows)
        self.assertTrue(all(r["stage"] == 7 and not r["flags"] & 1 for r in rows))   # no rebuild sales in stage 7
        first = [r for r in rows if not r["flags"] & 8]
        packages, _q = model(twin, 7, first)
        self.assertEqual([(r["buyer"], r["seller"], r["player"]) for r in first],
                         [(b, s, (p - y.table) // 0x54) for b, s, p, _pool, _h in packages])

    def test_a_sale_from_a_full_chart_fills_row_6_from_the_overflow(self):
        """S9 with men sharing the overflow row 7 (a deep pool, or a camp roster): closing the seller's gap empties row
        6; the best of the overflow men takes it, so the rows stay 0..6 then 7 (P1 2027: TT.rows at a camp DT sale)."""
        tn = _tn()
        x = self.fresh()
        x.install(7)
        x.run()
        sales = [r for r in self.rows(page=x.page()) if r["result"] == 1 and not r["flags"] & 8]
        self.assertTrue(sales)
        sale = sales[0]
        y = self.fresh()
        p = y.table + 0x54 * sale["player"]
        code = y.b(p + 0x35)
        mates = [o for o in y.roster(sale["seller"]) if y.pool(o) == sale["position"]]
        # deepen the pool to 9: the seller's last-row men of its deepest other pools play this position (rated low)
        others = sorted((o for o in y.roster(sale["seller"]) if y.pool(o) not in (None, 0, 1, 2, sale["position"])),
                        key=lambda o: -_tn().row(y.rec(o)))
        for o in others[:max(0, 9 - len(mates))]:
            y.m.uc.mem_write(o + 0x35, bytes([code]))
            mates.append(o)
        old = {o: tn.row(y.rec(o)) for o in mates}
        order = sorted(mates, key=lambda o: (old[o], mates.index(o)))
        order.remove(p)
        order.insert(min(old[p], 6), p)                              # his own row (below 7), the rest 0..6 then 7
        for k, o in enumerate(order):
            word = y.h(o + 0x28)
            y.m.uc.mem_write(o + 0x28, struct.pack("<H", (word & ~0x1C00) | min(k, 7) << 10))
        y.install(7)
        y.run()
        if sale["player"] not in [r["player"] for r in _code().events(y.page()) if r["flags"] & 0x40 and r["result"] == 1]:
            self.skipTest("the edited chart changed the decision")
        rows = sorted(tn.row(y.rec(o)) for o in y.roster(sale["seller"]) if y.pool(o) == sale["position"])
        self.assertEqual(rows, [min(k, 7) for k in range(len(rows))])

    def test_shadow_writes_nothing_and_decides_the_same(self):
        x, m = self.x, self.x.m
        x.install(7, shadow=True)
        rosters = {i: x.roster(i) for i in range(32)}
        x.run()
        shadow_rows = [(r["buyer"], r["seller"], r["player"], r["word"]) for r in self.rows()]
        self.assertTrue(shadow_rows)
        self.assertTrue(any(r["result"] == 2 for r in self.rows()))
        self.assertFalse(any(r["result"] in (1, 4) for r in self.rows()))
        self.assertEqual((self.counters()["posted"], self.counters()["releases"]), (0, 0))
        control = self.fresh()                                            # the same call with the retail sites
        control.run()
        self.assertEqual({i: x.roster(i) for i in range(32)}, {i: control.roster(i) for i in range(32)})
        self.assertEqual({p: x.rec(p) for i in range(32) for p in x.roster(i)},
                         {p: control.rec(p) for i in range(32) for p in control.roster(i)})
        self.assertEqual(bytes(x.m.uc.mem_read(PICKS, 448)), bytes(control.m.uc.mem_read(PICKS, 448)))
        self.assertEqual(bytes(x.m.uc.mem_read(LEDGER - 4, 4 + 600 * 12)), bytes(control.m.uc.mem_read(LEDGER - 4, 4 + 600 * 12)))
        del rosters
        y = self.fresh()
        y.install(7)
        y.run()
        acting = [(r["buyer"], r["seller"], r["player"], r["word"])
                  for r in _code().events(y.page()) if not r["flags"] & 0x48]
        self.assertEqual(shadow_rows[0], acting[0])                       # the same first decision

    def test_the_same_state_gives_the_same_trades(self):
        x = self.x
        x.install(7)
        x.run()
        first = _code().events(x.page())
        y = self.fresh()
        y.install(7)
        y.run()
        self.assertEqual(first, _code().events(y.page()))

    def test_a_club_in_three_trade_groups_of_the_ledger_is_out(self):
        x, m = self.x, self.x.m
        x.install(7)
        x.run()
        executed = [r for r in self.rows(after=True) if r["result"] == 1]
        self.assertTrue(executed)
        busy = executed[0]["buyer"]
        y = self.fresh()
        cursor = y.m.get(LEDGER_CURSOR)
        team = y.club(busy)
        for k in range(3):
            at = LEDGER + 12 * ((cursor + k) % 600)
            y.m.put(at, 7 | 0x80000000)
            y.m.put(at + 4, 0)
            y.m.put(at + 8, team)
        y.m.put(LEDGER_CURSOR, (cursor + 3) % 600)
        y.install(7)
        y.run()
        self.assertTrue(all(busy not in (r["buyer"], r["seller"]) for r in _code().events(y.page())))
        self.assertGreaterEqual(_code().counters(y.page())["out_load"], 1)

    def test_a_man_the_ledger_shows_just_signed_or_traded_is_never_offered(self):
        """A signing row (kind 1) or a trade row (kind 7) naming a man keeps him off the market while it is in the
        ledger (R4 'just signed'); the model with the same rows agrees."""
        x = self.x
        x.install(7)
        x.run()
        first = [r for r in self.rows() if r["result"] == 1 and not r["flags"] & 8]
        self.assertGreaterEqual(len(first), 2)
        y, z = self.fresh(), self.fresh()
        marked = {}
        for image in (y, z):
            cursor = image.m.get(LEDGER_CURSOR)
            for k, (r, kind) in enumerate(zip(first[:2], (1, 7))):
                at = LEDGER + 12 * ((cursor + k) % 600)
                image.m.put(at, kind | 0x80000000)
                image.m.put(at + 4, image.table + 0x54 * r["player"])
                image.m.put(at + 8, image.club(r["seller"]))
                marked[r["player"]] = kind
            image.m.put(LEDGER_CURSOR, (cursor + 2) % 600)
        y.install(7)
        y.run()
        rows = [e for e in _code().events(y.page()) if not e["flags"] & 0x48]
        self.assertFalse({e["player"] for e in rows if e["result"] in (1, 2)} & set(marked))
        packages, _q = model(z, 8, rows)
        self.assertEqual([(e["buyer"], e["player"]) for e in rows],
                         [(b, (p - z.table) // 0x54) for b, _s, p, _pool, _h in packages])

    def test_a_buyer_with_three_picks_gone_is_out(self):
        """S3: at most 3 of a club's own picks of the coming draft paid."""
        x, m = self.x, self.x.m
        x.install(7)
        x.run()
        executed = [r for r in self.rows(after=True) if r["result"] == 1]
        self.assertTrue(executed)
        busy = executed[0]["buyer"]
        y = self.fresh()
        other = (busy + 1) % 32
        for rnd in (5, 6, 7):
            y.m.uc.mem_write(PICKS + 32 * rnd + busy, bytes([other]))
        y.install(7)
        y.run()
        self.assertTrue(all(r["buyer"] != busy for r in _code().events(y.page())))
        self.assertGreaterEqual(_code().counters(y.page())["out_picks"], 1)

    def test_the_draw_keeps_records_off_the_board(self):
        x, m = self.x, self.x.m
        x.install(7, p8=0)
        x.run()
        self.assertEqual([r for r in self.rows() if r["result"] in (1, 2)], [])
        c = self.counters()
        self.assertEqual(c["posted"], 0)
        self.assertGreater(c["kept"], 0)

    def test_week_weights_and_pool_weights_scale_the_chance(self):
        x, m = self.x, self.x.m
        twin = self.fresh()
        twin.m.put(WEEK, 3)
        m.put(WEEK, 3)
        x.install(7, p8=200_000)
        x.run()
        first = [r for r in self.rows() if not r["flags"] & 8]
        packages, _q = model(twin, 8, first, p8=200_000)
        self.assertEqual([(r["buyer"], r["player"]) for r in first],
                         [(b, (p - x.table) // 0x54) for b, _s, p, _pool, _h in packages])
        self.assertGreater(self.counters()["kept"], 0)

    def test_a_full_board_posts_nothing_and_a_second_round_uses_the_freed_slots(self):
        """S8: with every CPU slot holding a native listing nothing is written (no_slot); with two slots free, the first
        round posts two and, the board being full again, runs a second round after the pending scan."""
        x, m = self.x, self.x.m
        listing = lambda slot, club: (m.put(BOARD + RECORD * slot + 8, x.club(club)), m.put(BOARD + RECORD * slot, 1))
        for slot in range(1, 15):
            if not m.get(BOARD + RECORD * slot):
                listing(slot, 15)                                # a listing by the person's club (names no CPU club)
        before = x.board()
        x.install(7)
        x.run()
        c = self.counters()
        first = [r for r in self.rows() if not r["flags"] & 8]
        self.assertFalse([r for r in first if r["result"] == 1])             # nothing of ours in the first round
        self.assertGreater(c["no_slot"], 0)
        posted = [r for r in self.rows() if r["result"] == 1]                # a second round after native pending trades
        self.assertEqual(c["releases"], sum(1 for r in posted if r["flags"] & 2))   # released only for a posted record
        y = self.fresh()
        free = [slot for slot in range(1, 15) if not y.m.get(BOARD + RECORD * slot)]
        for slot in free[2:]:
            y.m.put(BOARD + RECORD * slot + 8, y.club(15))
            y.m.put(BOARD + RECORD * slot, 1)
        y.install(7)
        y.run()
        c = _code().counters(y.page())
        self.assertEqual(c["second_rounds"], 1)
        self.assertGreaterEqual(c["posted"], 2)
        rows = [r for r in _code().events(y.page()) if not r["flags"] & 0x40 and r["result"] == 1]
        one = {k for r in rows if not r["flags"] & 8 for k in (r["buyer"], r["seller"])}
        two = {k for r in rows if r["flags"] & 8 for k in (r["buyer"], r["seller"])}
        self.assertFalse(one & two)                                          # one trade per club per call
        del before

    def test_a_star_tagged_man_is_never_offered(self):
        """MyCareer's man (and every star-tagged man) carries +0x53 bit 0: never offered."""
        x, m = self.x, self.x.m
        x.install(7)
        x.run()
        first = [r for r in self.rows() if r["result"] in (1, 2)]
        self.assertTrue(first)
        y = self.fresh()
        tagged = {y.table + 0x54 * r["player"] for r in first}
        for p in tagged:
            y.m.uc.mem_write(p + 0x53, bytes([y.b(p + 0x53) | 1]))
        y.install(7)
        y.run()
        self.assertFalse({y.table + 0x54 * r["player"] for r in _code().events(y.page())} & tagged)

    def test_the_story_gate_lets_our_records_through_and_leaves_others_native(self):
        """S7: the gate's flags for a record of ours read "greater"; for another record they are the native compare."""
        x, m = self.x, self.x.m
        x.install(7)
        code = _code()
        entry = VA + code.LABELS["story_entry"]
        stub = PROBE + 0x900                          # call story_entry; pushfd; pop eax into PROBE+0x800; ret
        m.uc.mem_write(stub, b"\xe8" + struct.pack("<i", entry - (stub + 5)) + b"\x9c\x58\xa3"
                       + struct.pack("<I", PROBE + 0x800) + b"\xc3")
        m.uc.ctl_flush_tb()

        def flags(value, ours):                       # Machine.call sets EBP = 0x44444444: that is "the record"
            m.put(VA + code.CURRENT, 0x44444444 if ours else 0)
            m.call(stub, eax=value, budget=200_000)
            return m.get(PROBE + 0x800)

        greater = lambda f: not f & 0x40 and bool(f & 0x80) == bool(f & 0x800)     # ZF clear, SF == OF
        self.assertTrue(greater(flags(500, True)))
        self.assertFalse(greater(flags(500, False)))
        self.assertTrue(greater(flags(1500, False)))
        self.assertFalse(greater(flags(1000, False)))
        self.assertEqual(self.counters()["stories_forced"], 1)


class CpuTradesMidSeason(CpuTradesImage):
    """Every image test again on a regular-season image with real records (CPU_TRADES_MIDSEASON_IMAGE: a season-panel
    checkpoint in a later franchise year, stage 8, week 7; its executable CPU_TRADES_MIDSEASON_XBE), where the race
    test (W + 1 < L: out), losing clubs' veteran sales (R3) and the q90 line under them are live."""

    def fresh(self):
        x = Image(MIDSEASON, MIDSEASON_XBE)
        x.open_places(self.PLACES)
        return x

    def test_races_and_rebuild_sales_are_live_here(self):
        x = self.x
        x.install(7)
        x.run()
        c = self.counters()
        self.assertGreater(c["out_race"], 0)
        self.assertGreater(c["rebuild_packages"], 0)
        _packages, q = model(self.fresh(), 8, self.rows())
        for r in self.rows():
            if r["flags"] & 1 and r["result"] in (1, 2):          # a rebuild sale: a veteran below his pool's q90
                p = x.table + 0x54 * r["player"]
                self.assertGreaterEqual(x.b(p + 0x25) & 31, 8)
                self.assertLess(r["rating"], q[r["position"]][3])


THIRD_SEASON = {"rost.body": "70813bd95d1265b40009fb611569e2e1ffcce02bf17a5f73476e8f55ffa3d157",
                "third-season/SAVEGAME.DAT": "b836dcef8c6c5e67092d0d595e175ea43c2912fe96b4a45cfd065009ff09d305"}


@unittest.skipUnless(HAVE_UC, "Unicorn is required for the native franchise save and load")
class SignedRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import hashlib
        from mod_editor.core import nfl2k5_cpu_trades as ct
        fixtures = os.environ.get("NFL2K5_B81_STABILITY_FIXTURES", "")
        if not fixtures or not all((Path(fixtures) / name).is_file() for name in (*THIRD_SEASON, "third-season/EXTRA")):
            raise unittest.SkipTest("the third-season signed franchise is absent (NFL2K5_B81_STABILITY_FIXTURES)")
        data = {name: (Path(fixtures) / name).read_bytes() for name in THIRD_SEASON}
        wrong = {n: hashlib.sha256(raw).hexdigest() for n, raw in data.items() if hashlib.sha256(raw).hexdigest() != THIRD_SEASON[n]}
        if wrong:
            raise AssertionError(f"private inputs differ from their pins: {wrong}")
        cls.roster, cls.save = data["rost.body"], data["third-season/SAVEGAME.DAT"]
        cls.xbe, _ = ct.install(_fixture(STANDARD_XBE).read_bytes(), 7, p8_ppm=1_000_000, p7_ppm=1_000_000)

    def boot(self, raw):
        """Cold-load a signed franchise as test_b81_sim_pos_injury_signed does (frontend, game PRNGs, native load)."""
        from tests.nfl2k5_my_career_mode_fixture import Machine
        m = Machine(self.xbe)
        self.addCleanup(m.close)
        m.frontend(self.roster)
        m.call(0x77D20, stop=0x77D45, budget=2_000_000)
        m.live_league_prng()
        for generator in (0xB12680, 0xE5FCA0):
            m.call(0x48BE0, ecx=generator, edx=2501)
        m.put(0xE5FF80, 4)
        m.native_load(raw, requested=False)
        m.loaded_menu()
        return m

    @staticmethod
    def page(m):
        return bytes(m.uc.mem_read(VA, 0x2000))

    def tick(self, m):
        """One native trade pass; (its ring rows, its counters) as the difference to the pages before it."""
        code = _code()
        before = self.page(m)
        m.call(0x2BC960, ecx=3, edx=m.ARENA + 0xF0000, budget=2_000_000_000)
        after = self.page(m)
        old, new = code.counters(before), code.counters(after)
        rows = [{k: v for k, v in r.items() if k != "n"} for r in code.events(after)[len(code.events(before)):]]
        return rows, {k: new[k] - old[k] for k in new}

    @staticmethod
    def state(m):
        read = lambda at, n: bytes(m.uc.mem_read(at, n))
        root = m.get(0xB72918)
        count, pool, teams = m.get(root), m.get(root + 4), m.get(root + 0x1C)
        ledger = []
        for i in range(600):
            word, player, club = struct.unpack("<III", read(LEDGER + 12 * i, 12))
            ledger.append((word, (player - pool) // 0x54 if player else None, (club - teams) // 500 if club else None))
        return {"players": read(pool, count * 0x54), "clubs": [read(teams + 500 * k, 500) for k in range(32)],
                "picks": read(PICKS, 448), "cursor": m.get(LEDGER_CURSOR), "ledger": ledger,
                "board": read(BOARD, 15 * RECORD), "when": [m.get(STAGE), m.get(WEEK), m.get(YEAR)]}

    def test_a_signed_save_after_our_trades_reloads_to_the_same_next_pass(self):
        from mod_editor.core import nfl2k5_roster_records as records
        live = self.boot(self.save)
        self.assertEqual([live.get(STAGE), live.get(YEAR)], [8, 2])
        live.put(WEEK, 3)                                     # the saved franchise ended its season; trade week 3
        rows, counts = self.tick(live)
        self.assertGreater(counts["executed"], 0)
        self.assertEqual(counts["stories_forced"], counts["executed"])
        raw = live.native_save(budget=500_000_000)
        extra = live.native_signature(raw)
        self.assertTrue(records.verify_extra(raw, extra or b""), "the native signature does not verify")
        cold = self.boot(raw)
        self.assertEqual(self.state(cold), self.state(live), "the cold load differs from the live franchise")
        # The game's random streams are not part of a save (a cold load seeds them at boot); the native proposers of
        # the trade pass draw from them, so both machines get the same seed before the next pass.
        for machine in (live, cold):
            for generator in (0xB12680, 0xE5FCA0):
                machine.call(0x48BE0, ecx=generator, edx=4242)
        rows_live, counts_live = self.tick(live)
        rows_cold, counts_cold = self.tick(cold)
        self.assertGreater(counts_live["executed"], 0)
        self.assertEqual(rows_cold, rows_live)
        self.assertEqual(counts_cold, counts_live)
        self.assertEqual(self.state(cold), self.state(live))
        # what the first pass executed is in the reloaded ledger as trade rows, so the second pass cannot repeat it
        code = _code()
        traded = {r["player"] for r in rows if r["flags"] & code.F_AFTER and r["result"] == code.RESULT_EXECUTED}
        self.assertTrue(traded)
        self.assertFalse(traded & {r["player"] for r in rows_cold if not r["flags"] & code.F_AFTER})


class PagesAndLayout(unittest.TestCase):

    def test_page_layout_settings_and_site(self):
        code = _code()
        self.assertLessEqual(code.CODE_BYTES, code.CODE_LIMIT)
        record = code.settings_record(7, p8_ppm=250_000, p7_ppm=400_000)
        page = code.page_bytes(VA, record)
        self.assertEqual(len(page), 0x2000)
        self.assertEqual(page[code.CODE_BYTES:code.CODE_LIMIT], b"\xcc" * (code.CODE_LIMIT - code.CODE_BYTES))
        self.assertEqual(page[code.SETTINGS_OFFSET:code.SETTINGS_OFFSET + 0x20], record)
        self.assertEqual(page[code.SETTINGS_OFFSET + 0x20:], bytes(0x2000 - code.SETTINGS_OFFSET - 0x20))
        self.assertEqual(code.parse_settings(record), {"stages": 7, "shadow": False, "p8_ppm": 250_000, "p7_ppm": 400_000})
        (at, original, patched), (story, story_original, story_patched) = code.sites(VA)
        self.assertEqual((at, original), (0x2BC96C, bytes.fromhex("e88fffffff")))
        self.assertEqual(at + 5 + struct.unpack("<i", patched[1:])[0], VA + code.LABELS["trade_entry"])
        self.assertEqual((story, story_original), (0x2BB296, bytes.fromhex("3de8030000")))
        self.assertEqual(story + 5 + struct.unpack("<i", story_patched[1:])[0], VA + code.LABELS["story_entry"])
        self.assertEqual(code.RING_EVENT.size, 16)
        self.assertEqual(code.RING_OFFSET + code.RING_COUNT * code.RING_EVENT.size, 0x2000)
        self.assertLessEqual(len(code.COUNTER_NAMES), code.COUNTERS_LIMIT)
        self.assertEqual(code.COUNTERS_OFFSET + 4 * code.COUNTERS_LIMIT, code.RING_CURSOR)
        self.assertEqual(code.CURRENT + 4 * code.MAX_POSTS, code.ROUND_MASK)
        self.assertLessEqual(code.ROUND_MASK + 4, code.RING_OFFSET)
        for bad in (0, 8, 15):
            with self.assertRaises(ValueError):
                code.settings_record(bad, p8_ppm=1, p7_ppm=1)
        with self.assertRaises(ValueError):
            code.parse_settings(b"CPUTRDv2" + record[8:])

    def test_template_is_the_built_source(self):
        import shutil
        import subprocess
        import sys
        root = Path(__file__).resolve().parents[2]
        if not (shutil.which("gcc") and shutil.which("as") and shutil.which("ld")):
            raise unittest.SkipTest("GNU gcc/as/ld are needed to rebuild the template")
        subprocess.run([sys.executable, "-B", str(root / "tools/cpu_trades/build.py"), "--check"], check=True)

    def test_fixed_pages_and_every_pool_owner_steps_over_them(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        self.assertEqual((space.CPU_TRADES_VA, space.CPU_TRADES_SIZE), (0x152E000, 0x2000))
        self.assertEqual(space.CPU_TRADES_VA, space.HELMET_SIDES_VA + space.HELMET_SIDES_SIZE)
        self.assertEqual(space.FIXED_SPAN_END, 0x1530000)
        self.assertIn(space.CPU_TRADES_OWNER, space.FIXED_PAGE_OWNERS)
        self.assertIn(space.CPU_TRADES_REQUEST, space.dormant_union())
        placed = space._scale_allocations([space.CPU_TRADES_REQUEST])
        self.assertEqual([(r["owner"], r["va"], r["size"]) for r in placed if r["owner"] == space.CPU_TRADES_OWNER],
                         [(space.CPU_TRADES_OWNER, 0x152E000, 0x2000)])
        with self.assertRaises(ValueError):
            space._scale_allocations([(space.CPU_TRADES_OWNER, "code", 0x1000, 0x1000)])


class Owner(unittest.TestCase):
    """The owner on a standard executable that carries the needs (CPU_TRADES_STANDARD_XBE)."""

    @classmethod
    def setUpClass(cls):
        cls.source = _fixture(STANDARD_XBE).read_bytes()

    def test_realistic_then_retail_is_the_source_plus_an_empty_reservation(self):
        from mod_editor.core import nfl2k5_cpu_trades as ct, nfl2k5_xbe_space as space
        self.assertEqual(ct.read_settings(self.source)["status"], "retail")
        self.assertEqual(ct.requirements(self.source), [])
        out, receipt = ct.apply(self.source, "realistic")
        settings = ct.read_settings(out)
        self.assertEqual((settings["status"], settings["stages"], settings["shadow"]), ("applied", ct.REALISTIC_STAGES, False))
        self.assertEqual((settings["p8_ppm"], settings["p7_ppm"]), (ct.P8_PPM, ct.P7_PPM))
        row = ct.allocation(out)
        self.assertEqual((row["va"], row["size"]), (0x152E000, 0x2000))
        back, _ = ct.apply(out, "retail")
        self.assertEqual(ct.read_settings(back)["status"], "retail")
        empty, _ = ct.install(self.source, 7)
        self.assertEqual(ct.apply(empty, "retail")[0], back)
        again, receipt = ct.apply(out, "realistic")
        self.assertEqual((again, receipt["status"]), (out, "already_applied"))
        # every other owner's allocation is where it was
        before = {(r["owner"], r["kind"]): r["va"] for r in space.layout(self.source)["allocations"]}
        after = {(r["owner"], r["kind"]): r["va"] for r in space.layout(out)["allocations"]}
        self.assertEqual({k: v for k, v in after.items() if k[0] != ct.OWNER}, before)

    def test_foreign_bytes_are_refused(self):
        from mod_editor.core import nfl2k5_cpu_trades as ct
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        out, _ = ct.apply(self.source, "realistic")
        image = XbeImage(out)
        data = bytearray(out)
        at = image.offset(ct.VA + 0x10, 1)
        data[at] ^= 0xFF
        self.assertEqual(ct.read_settings(bytes(data))["status"], "foreign")
        with self.assertRaises(ct.CpuTradesError):
            ct.apply(bytes(data), "retail")
        site = bytearray(self.source)
        at = XbeImage(self.source).offset(0x2BC96C, 5)
        site[at:at + 5] = b"\xe8\x00\x00\x00\x00"
        self.assertEqual(ct.read_settings(bytes(site))["status"], "foreign")
        half = bytearray(out)                       # one site restored, the other installed: foreign
        at = XbeImage(out).offset(0x2BB296, 5)
        half[at:at + 5] = bytes.fromhex("3de8030000")
        self.assertEqual(ct.read_settings(bytes(half))["status"], "foreign")

    def test_an_owner_already_in_the_range_is_refused(self):
        """N7: the install checks that nothing else is allocated in 0x152E000..0x152FFFF."""
        from unittest.mock import patch
        from mod_editor.core import nfl2k5_cpu_trades as ct, nfl2k5_xbe_space as space
        layout = space.layout(self.source)
        fake = dict(layout, allocations=layout["allocations"] + [dict(owner="zz_squatter", kind="code", size=0x100,
                                                                           align=16, va=0x152F000, raw=0,
                                                                           owner_offset=0)])
        with patch.object(space, "layout", lambda payload: fake):
            self.assertIn("zz_squatter", ct.unowned_problem(self.source))
            with self.assertRaises(ct.CpuTradesError):
                ct.apply(self.source, "realistic")

    def test_calibration_records_and_shadow(self):
        from mod_editor.core import nfl2k5_cpu_trades as ct
        out, receipt = ct.install(self.source, 3, shadow=True, p8_ppm=123_000, p7_ppm=456_000)
        self.assertEqual(ct.read_settings(out)["shadow"], True)
        self.assertEqual((receipt["p8_ppm"], receipt["p7_ppm"], receipt["stages"]), (123_000, 456_000, 3))
        moved, _ = ct.install(out, 7)
        self.assertEqual(ct.read_settings(moved)["stages"], 7)
        with self.assertRaises(ValueError):
            ct.install(self.source, 8)

    def test_needs_are_named_when_missing(self):
        from mod_editor.core import nfl2k5_cpu_trades as ct
        retail = os.environ.get("NFL2K5_RETAIL_XBE", "")
        if not retail or not Path(retail).is_file():
            raise unittest.SkipTest("NFL2K5_RETAIL_XBE is not set")
        missing = ct.requirements(Path(retail).read_bytes())
        for word in ("128 MB", "deadline", "economy", "practice squad", "injured reserve", "ownership"):
            self.assertTrue(any(word in m for m in missing), word)
        with self.assertRaises(ct.CpuTradesError):
            ct.apply(Path(retail).read_bytes(), "realistic")


if __name__ == "__main__":
    unittest.main()
