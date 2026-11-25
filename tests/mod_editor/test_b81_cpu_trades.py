"""CPU trades at every position (beta 81, owner nfl2k5_cpu_trades; the trades-all lane's DESIGN.md and RULINGS.md).

Image tests (CpuTradesImage): the pages linked at 0x152E000 and the site 0x2BC96C patched into a kept regular-season
opening (a season-panel checkpoint of the 4b hand-over run: stage 8, week counter 0, the Trade Deadline option off, the
quarterback room at 383), entered as the game enters them: the native trade pass 0x2BC960 (ECX = 3 proposers, EDX = the
menu), whose pending scan call is the site. The packages are recomputed here from the design in Python (ratings by the
game's own 0x246D80 on the same image) and compared with the page's ring rows; every executed trade is then checked
against the hard rules (no club a person manages, no QB/K/P, healthy, 2+ years pro, not in the first contract year, the
seller's depth, roster counts, the pick changes owner from buyer to seller, nothing of ours left on the board).

Fixtures come from the environment only (no private paths in the repo): CPU_TRADES_IMAGE (a .b81mem.gz opening) and
CPU_TRADES_IMAGE_XBE (the executable it was made with). Without them the image classes skip.

PagesAndOwner: the byte interface and the owner (install, Retail, foreign, needs) on CPU_TRADES_STANDARD_XBE, a standard
executable carrying the needs (else skip). Allocation: the fixed pages and the step-over, no fixture.

Every class fails on c4406481b: there is no nfl2k5_cpu_trades owner, code module or allocation there.
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
import unittest

from tests.nfl2k5_supersim_draft_fixture import HAVE_UC

IMAGE = os.environ.get("CPU_TRADES_IMAGE", "")
IMAGE_XBE = os.environ.get("CPU_TRADES_IMAGE_XBE", "")
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
STARTERS = (0, 0, 0, 3, 2, 1, 1, 1, 1, 1, 2, 2, 1, 2, 2, 2, 2)
CUT_MIN = (2, 1, 1, 5, 5, 2, 2, 3, 0, 3, 0, 5, 2, 3, 3, 3, 4)
WEEK_WEIGHT = (1, 1, 1, 1, 2, 2, 2, 4, 8)


def _code():
    from mod_editor.core import nfl2k5_cpu_trades_code as code
    return code


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


def overall_of_bits(u):
    e = (u >> 23) & 255
    if u >> 31 or e < 119:
        return 0
    if e > 127:
        return 100
    s = 150 - e
    return (((u & 0x7FFFFF) | 0x800000) * 100 + (1 << (s - 1))) >> s


def _fixture(path):
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("CPU_TRADES_IMAGE / CPU_TRADES_IMAGE_XBE / CPU_TRADES_STANDARD_XBE not set or absent")
    return Path(path)


class Image:
    """A kept image on its executable with the CPU trades pages and site written in (the 4b tests' method)."""

    def __init__(self):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        from tools import franchise_invariants as fi
        image, xbe = _fixture(IMAGE), _fixture(IMAGE_XBE)
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
        at, _original, patched = code.site(VA)
        self.m.uc.mem_write(VA, code.page_bytes(VA, code.settings_record(stages, shadow=shadow, p8_ppm=p8, p7_ppm=p7)))
        self.m.uc.mem_write(at, patched)
        self.m.uc.ctl_flush_tb()

    def b(self, at):
        return self.m.uc.mem_read(at, 1)[0]

    def club(self, i):
        return self.teams + 500 * i

    def roster(self, i):
        team = self.club(i)
        return [self.m.get(team + 4 * k) for k in range(self.b(team + 0x11C))]

    def healthy(self, p):
        return not self.m.get(p + 0x20) & 0xBFC00000 and not self.m.get(p + 0x24) & 0x70000000

    def rating(self, p):
        if p not in self._ratings:
            code = (b"\xb9" + struct.pack("<I", p) + b"\xba\x00\x00\x00\x00\xb8\x80\x6d\x24\x00\xff\xd0"
                    + b"\xd9\x1d" + struct.pack("<I", PROBE + 0x800) + b"\xc3")
            self.m.uc.mem_write(PROBE, code)
            self.m.uc.ctl_flush_tb()
            self.m.call(PROBE, budget=2_000_000)
            self._ratings[p] = overall_of_bits(self.m.get(PROBE + 0x800))
        return self._ratings[p]

    def record(self, i):
        team = self.club(i)
        return tuple(self.m.call(at, ecx=team, budget=5_000_000) for at in (0xC7720, 0xC7750, 0xC7780))

    def salary(self, p):
        return self.m.call(0xE6380, ecx=p, budget=2_000_000)

    def pick_owner(self, word):
        from mod_editor.core import nfl2k5_trade_picks as picks
        return self.b(picks.owner_address(word))

    def board(self):
        return [bytes(self.m.uc.mem_read(BOARD + RECORD * s, RECORD)) for s in range(15)]

    def page(self):
        return bytes(self.m.uc.mem_read(VA, 0x2000))

    def open_places(self, clubs):
        """Give these clubs a vacancy the way the season does (the game's own release 0x2BD900 of their last-listed
        player outside QB, K and P, to the free-agent list): at the opening every club holds 53, and an in-season buyer
        needs 52 or fewer."""
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

    # ---- the design, in Python ------------------------------------------------------------------------------
    def ledger(self):
        """(load per club, players named by a signing or trade row)."""
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

    def scale(self):
        """eff[club][pos], best[club], q[pos] = (q25, q50, q75, q90)."""
        eff, best = [], []
        for i in range(32):
            top = [[] for _ in range(17)]
            b = 0
            for p in self.roster(i):
                pos = self.b(p + 0x35)
                if pos >= 17:
                    continue
                r = self.rating(p)
                b = max(b, r)
                if self.healthy(p):
                    top[pos].append(r)
            eff.append([sorted(top[pos], reverse=True)[STARTERS[pos] - 1] if STARTERS[pos] and
                        len(top[pos]) >= STARTERS[pos] else 0 for pos in range(17)])
            best.append(b)
        q = []
        for pos in range(17):
            v = sorted(eff[i][pos] for i in range(32))
            q.append((v[8], v[16], v[24], v[28]))
        return eff, best, q


def offer_of(x, s, pos, floor, above, room, q, eff, best, rebuild_ok, board_players, ledger_players):
    """The design's man from seller s (see trades.c offer_of), or None; returns (player, rating, rebuild sale)."""
    lb = pos in (10, 11)
    ros = x.roster(s)
    count = sum(1 for p in ros if x.b(p + 0x35) == pos or (lb and x.b(p + 0x35) in (10, 11)))
    healthy_at = sum(1 for p in ros if x.b(p + 0x35) == pos and x.healthy(p))
    if healthy_at < STARTERS[pos] + 1 or count < CUT_MIN[11 if lb else pos] + 1:
        return None
    out, best_r = None, above
    for p in ros:
        if x.b(p + 0x35) != pos or not x.healthy(p):
            continue
        pro, left, length = x.b(p + 0x25) & 31, x.b(p + 0x24) & 15, x.b(p + 0x27) & 15
        if pro < 2 or not left or (x.m.get(YEAR) and left == length) or x.b(p + 0x53) & 1:
            continue
        r = x.rating(p)
        if r < floor or r <= best_r or r >= best[s] or (r >= q[3] and pro <= 6):
            continue
        sale_rebuild = r >= eff[s][pos]
        if sale_rebuild and (not rebuild_ok or pro < 6):
            continue
        if room - x.salary(p) <= 10 or p in board_players or p in ledger_players:
            continue
        out, best_r = (p, r, sale_rebuild), r
    return out


def model(x, stage, rows, *, rebuild_bit=True):
    """Every buyer's package in the page's order: [(buyer, seller, player, position, word)]. `rows` are the page's
    before-scan rows: a row posted or would-post makes both clubs used, as in the page."""
    m = x.m
    eff, best, q = x.scale()
    load, ledger_players = x.ledger()
    board_clubs, board_players = x.board_names()
    year, week = m.get(YEAR), m.get(WEEK)
    clubs = []
    for i in range(32):
        team = x.club(i)
        active = x.b(team + 0x11C)
        out = m.get(USER_FLAG + 4 * i) != 0 or team in board_clubs
        w = l_ = t = 0
        if stage == 8:
            w, l_, t = x.record(i)
        c = dict(out=out, active=active, w=w, l=l_, t=t, seller=False, rebuild=False, need=None, used=False)
        if not out and load[i] < 3:
            if active >= 51:
                c["seller"] = True
                c["rebuild"] = stage == 8 and rebuild_bit and w + l_ + t >= 4 and l_ >= w + 3
            if not (active > (52 if stage == 8 else 64) or (stage == 8 and w + 1 < l_)):
                deficit = 0
                for pos in range(17):
                    if STARTERS[pos] and eff[i][pos] < q[pos][0] and q[pos][0] - eff[i][pos] > deficit:
                        deficit, c["need"] = q[pos][0] - eff[i][pos], pos
        elif not out:
            c["out"] = True
        clubs.append(c)
    start = fmix((year * 131 + week * 7 + stage) & 0xFFFFFFFF) % 32
    packages, by_buyer = [], {(r["buyer"]): r for r in rows}
    for k in range(32):
        b = (start + k) % 32
        c = clubs[b]
        if c["out"] or c["need"] is None or c["used"]:
            continue
        pos = c["need"]
        floor = max(eff[b][pos] + 3, q[pos][0])
        room = (m.get(CAP) - m.get(x.club(b) + 0x124)) & 0xFFFFFFFF
        room = room - (1 << 32) if room >= 1 << 31 else room
        choice, top = None, 0
        for s in range(32):
            if s == b or not clubs[s]["seller"] or clubs[s]["used"] or clubs[s]["out"]:
                continue
            got = offer_of(x, s, pos, floor, top, room, q[pos], eff, best, clubs[s]["rebuild"], board_players,
                           ledger_players)
            if got:
                choice, top = (s, *got), got[1]
        if choice is None:
            continue
        s, p, r, _sale = choice
        packages.append((b, s, p, pos))
        row = by_buyer.get(b)
        if row is not None and row["result"] in (1, 2):
            c["used"] = clubs[s]["used"] = True
    return packages, eff, q


@unittest.skipUnless(HAVE_UC, "Unicorn is required")
class CpuTradesImage(unittest.TestCase):
    PLACES = tuple(range(0, 32, 2))         # clubs given a vacancy (every second club; 15, a person's, is odd)

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

    def rows(self, after=False):
        events = _code().events(self.x.page())
        return [e for e in events if bool(e["flags"] & 0x40) == after]

    def counters(self):
        return _code().counters(self.x.page())

    def test_packages_follow_the_design_and_every_executed_trade_keeps_the_rules(self):
        x, m = self.x, self.x.m
        x.install(7)
        before = {i: x.roster(i) for i in range(32)}
        snapshot = {p: bytes(m.uc.mem_read(p, 0x54)) for i in range(32) for p in before[i]}
        owners = {}
        x.run()
        rows, after = self.rows(), self.rows(after=True)
        self.assertTrue(rows, "no buyer found a package on this image")
        # the design's packages (with the page's own posted/would results deciding which clubs were used)
        twin = self.fresh()                  # the same state before the call, for the model
        packages, eff, q = model(twin, 8, rows)
        self.assertEqual([(r["buyer"], r["seller"], r["player"], r["position"]) for r in rows],
                         [(b, s, (p - x.table) // 0x54, pos) for b, s, p, pos in packages])
        executed = [r for r in after if r["result"] == 1]
        self.assertTrue(executed, "nothing was executed")
        self.assertLessEqual(len(after), 6)
        for r in executed:
            p = x.table + 0x54 * r["player"]
            rec = snapshot[p]
            buyer, seller = r["buyer"], r["seller"]
            self.assertIn(p, x.roster(buyer))
            self.assertNotIn(p, x.roster(seller))
            self.assertEqual(m.get(USER_FLAG + 4 * buyer) | m.get(USER_FLAG + 4 * seller), 0)
            self.assertNotIn(rec[0x35], (0, 1, 2))
            self.assertGreaterEqual(rec[0x25] & 31, 2)
            if m.get(YEAR):                          # the first contract year counts from the second franchise season
                self.assertNotEqual(rec[0x24] & 15, rec[0x27] & 15)
            self.assertFalse(rec[0x53] & 1)
            self.assertFalse(struct.unpack_from("<I", rec, 0x20)[0] & 0xBFC00000)
            self.assertLessEqual(len(x.roster(buyer)), 53)
            self.assertGreaterEqual(len(x.roster(seller)), 50)
            healthy_left = sum(1 for o in x.roster(seller) if x.b(o + 0x35) == rec[0x35] and x.healthy(o))
            self.assertGreaterEqual(healthy_left, STARTERS[rec[0x35]])
            self.assertEqual(x.pick_owner(r["word"]), seller)
            owners[r["word"]] = seller
        # nothing of ours left on the board: no kind-2 record whose A player is one of our rows' men
        ours = {x.table + 0x54 * r["player"] for r in rows}
        for rec in x.board():
            kind, player = struct.unpack_from("<I", rec, 0)[0], struct.unpack_from("<I", rec, 0xC)[0]
            self.assertFalse(kind == 2 and player in ours)
        c = self.counters()
        self.assertEqual(c["posted"], c["executed"] + c["cancelled"] + c["gone"])

    def test_prices_follow_the_ladder_and_picks_were_the_buyers(self):
        x, m = self.x, self.x.m
        owner_before = {}
        x.install(7)
        rows_seen = []
        # pick owners before the call, for every word a row can name
        for rnd in range(1, 8):
            for s in range(32):
                owner_before[rnd | s << 6] = x.pick_owner(rnd | s << 6)
        eff, best, q = x.scale()
        before = {x.table + 0x54 * k: bytes(m.uc.mem_read(x.table + 0x54 * k, 0x54)) for k in range(m.get(x.root))}
        x.run()
        for r in self.rows():
            if r["result"] == 3:
                continue
            rows_seen.append(r)
            p = x.table + 0x54 * r["player"]
            rating = r["rating"]
            self.assertEqual(rating, x._ratings.get(p, rating))
            q25, q50, q75, q90 = q[r["position"]]
            ruled = 2 if rating >= q90 else 3 if rating >= q75 else 4 if rating >= q50 else 5 if rating >= q25 else 6
            ruled += (before[p][0x25] & 31) >= 9
            ruled += (before[p][0x24] & 15) == 1
            ruled = min(ruled, 7)
            rnd = r["word"] & 0x3F
            self.assertIn(rnd, (ruled, ruled - 1))
            self.assertEqual(owner_before[r["word"]], r["buyer"])
            self.assertEqual(r["word"] >> 12, 0)
        self.assertTrue(rows_seen)

    def test_a_club_a_person_manages_is_never_a_buyer_or_a_seller(self):
        x, m = self.x, self.x.m
        x.install(7)
        x.run()
        first = [(r["buyer"], r["seller"]) for r in self.rows(after=True) if r["result"] == 1]
        self.assertTrue(first)
        # a fresh image with those clubs managed by people
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
        board = x.board()
        m.put(WEEK, 9)                               # the deadline byte: the window's last open stored week is 8
        x.run()
        self.assertEqual(self.counters()["past_deadline"], 1)
        self.assertEqual(self.counters()["ticks"], 0)
        m.put(WEEK, 8)
        x.install(2 | 4)                             # regular season off
        x.run()
        self.assertEqual((self.counters()["inactive"], self.counters()["ticks"]), (1, 0))
        x.install(7)
        m.put(STAGE, 9)
        x.run()
        self.assertEqual((self.counters()["inactive"], self.counters()["ticks"]), (1, 0))
        self.assertEqual(_code().events(x.page()), [])
        del board

    def test_preseason_posts_with_bit_2_and_obeys_the_camp_limits(self):
        x, m = self.x, self.x.m
        m.put(STAGE, 7)
        x.install(1 | 4)                             # preseason bit off
        x.run()
        self.assertEqual(self.counters()["inactive"], 1)
        self.x = y = self.fresh()
        y.m.put(STAGE, 7)
        y.install(2)
        y.run()
        rows = [r for r in _code().events(y.page()) if not r["flags"] & 0x40]
        self.assertTrue(rows)
        self.assertTrue(all(r["stage"] == 7 and not r["flags"] & 1 for r in rows))   # no rebuild sales in stage 7
        twin = self.fresh()
        twin.m.put(STAGE, 7)
        packages, _eff, _q = model(twin, 7, rows)
        self.assertEqual([(r["buyer"], r["seller"], r["player"]) for r in rows],
                         [(b, s, (p - y.table) // 0x54) for b, s, p, _pos in packages])

    def test_shadow_writes_nothing_and_decides_the_same(self):
        x, m = self.x, self.x.m
        x.install(7, shadow=True)
        regions = {at: bytes(m.uc.mem_read(at, n)) for at, n in ((BOARD, 15 * RECORD), (PICKS, 15 * 32),
                                                                   (x.teams, 32 * 500))}
        x.run()
        shadow_rows = [(r["buyer"], r["seller"], r["player"], r["word"]) for r in self.rows()]
        self.assertTrue(all(r["result"] != 1 for r in self.rows()))
        self.assertEqual(self.counters()["posted"], 0)
        y = self.fresh()
        y.install(7)
        # the native pass itself still runs (its proposers post and list as retail): compare our own decisions
        y.run()
        acting = [(r["buyer"], r["seller"], r["player"], r["word"])
                  for r in _code().events(y.page()) if not r["flags"] & 0x40]
        self.assertEqual(shadow_rows, acting)
        del regions

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
        for k in range(3):                         # three one-row trade groups naming the club, the newest rows
            at = LEDGER + 12 * ((cursor + k) % 600)
            y.m.put(at, 7 | 0x80000000)
            y.m.put(at + 4, 0)
            y.m.put(at + 8, team)
        y.m.put(LEDGER_CURSOR, (cursor + 3) % 600)
        y.install(7)
        y.run()
        rows = _code().events(y.page())
        self.assertTrue(all(busy not in (r["buyer"], r["seller"]) for r in rows))
        self.assertGreaterEqual(_code().counters(y.page())["load_out"], 1)

    def test_the_draw_keeps_records_off_the_board(self):
        x, m = self.x, self.x.m
        x.install(7, p8=0)
        x.run()
        rows = self.rows()
        self.assertTrue(rows)
        self.assertTrue(all(r["result"] in (0, 3) for r in rows))
        self.assertEqual(self.counters()["posted"], 0)
        year, week = m.get(YEAR), m.get(WEEK)
        for r in rows:
            p = x.table + 0x54 * r["player"]
            w, l_, _t = x.record(r["buyer"])
            self.assertEqual(r["draw"], draw([9, r["buyer"], r["position"], year, 8, week, r["player"], w, l_]))
            self.assertEqual(r["threshold"], 0)
            del p

    def test_week_weights_scale_the_chance(self):
        x, m = self.x, self.x.m
        for week in range(9):
            m.put(WEEK, week)
            x.install(7, p8=200_000)
            x.run()
            rows = self.rows()
            if rows:
                self.assertEqual({r["threshold"] for r in rows}, {100_000 * WEEK_WEIGHT[week]})
            x = self.x = self.fresh()
            m = x.m


class PagesAndLayout(unittest.TestCase):

    def test_page_layout_settings_and_site(self):
        code = _code()
        self.assertLessEqual(code.CODE_BYTES, code.CODE_LIMIT)
        record = code.settings_record(7, p8_ppm=250_000, p7_ppm=400_000)
        page = code.page_bytes(VA, record)
        self.assertEqual(len(page), 0x2000)
        self.assertEqual(page[code.CODE_BYTES:code.CODE_LIMIT], b"\xcc" * (code.CODE_LIMIT - code.CODE_BYTES))
        self.assertEqual(page[0x1200:0x1220], record)
        self.assertEqual(page[0x1220:], bytes(0x2000 - 0x1220))
        self.assertEqual(code.parse_settings(record), {"stages": 7, "shadow": False, "p8_ppm": 250_000, "p7_ppm": 400_000})
        at, original, patched = code.site(VA)
        self.assertEqual((at, original), (0x2BC96C, bytes.fromhex("e88fffffff")))
        self.assertEqual(at + 5 + struct.unpack("<i", patched[1:])[0], VA + code.LABELS["trade_entry"])
        self.assertEqual(code.RING_EVENT.size, 24)
        self.assertEqual(code.RING_OFFSET + code.RING_COUNT * code.RING_EVENT.size, 0x2000)
        self.assertLessEqual(code.COUNTERS_OFFSET + 4 * len(code.COUNTER_NAMES), code.RING_CURSOR)
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
