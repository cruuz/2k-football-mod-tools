"""b780 j23 J3: the franchise history capture (nfl2k5_history) under Unicorn on a synthetic league.

The capture blob and the footer host blob run as installed; the game's getters (team list, live stat readers, season
stat, coached team) are answered by the test from a synthetic league so every value is known. Checked against a Python
model of the published format: the season record of every club (W-L-T, points, division place, playoff result, bye,
coach), the champion, awards, franchise totals, single-game and single-season records, all-time leaders (a linked
leader adds the season), Hall of Fame candidates and the class, the box score of the user's games; and that the
capture writes nothing outside the footer body and its own stack.
"""

from __future__ import annotations

import random
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_franchise_extension as ext  # noqa: E402
from mod_editor.core import nfl2k5_franchise_footer as footer  # noqa: E402
from mod_editor.core import nfl2k5_history as history  # noqa: E402

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

HCODE, FCODE, FDATA = 0x03000000, 0x03010000, 0x03020000
TEAMS, PLAYERS, NAMES, STREAMS = 0x05000000, 0x05100000, 0x05300000, 0x05400000
STACK, SENTINEL, SCRATCH, FLD = 0x04000000, 0x04080000, 0x04090000, 0x04090100
LEAGUE_PAGES = ((0xE57000, 0x9000), (0xB30000, 0x4000), (0xB72000, 0x1000), (0xBD7000, 0x1000), (0x320000, 0x1000),
                (0x515000, 0x1000), (0x133000, 0x1000))
FUNCS = (0xCB2D0, 0xCB240, 0xCA810, 0x14EE40, 0x14EDB0, 0xC3E70, 0xC3E80, 0xC6430, 0xC4C50, 0xC4D70)
WEEKS, SB = 2, 5                     # two regular-season rows; wild card 2, divisional 3, conference 4, Super Bowl 5
YEAR_BASE = 2026                     # CARD_YEAR_IMM - 11
STAT_FIELDS = (8, 9, 7, 2, 3, 12, 13, 14, 19, 20, 18, 21, 10, 0)


def _wide(text):
    return text.encode("utf-16-le") + b"\0\0"


@unittest.skipIf(uc is None, "Unicorn is required")
class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(7)
        self.m = m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        for base, size in ((HCODE, 0x4000), (FCODE, 0x2000), (FDATA, 0x20000), (TEAMS, 0x10000), (PLAYERS, 0x40000),
                           (NAMES, 0x40000), (STREAMS, 0x40000), (STACK, 0x10000), (SCRATCH, 0x1000),
                           *LEAGUE_PAGES):
            m.mem_map(base, size)
        for va in FUNCS:
            page = va & ~0xFFF
            try:
                m.mem_map(page, 0x1000)
            except uc.UcError:
                pass
            m.mem_write(va, b"\xc3")
        fconfig = {"state": FDATA, "static_body": FDATA + footer.STATE_SIZE, "chain_size": 0, "chain_save": 0,
                   "chain_load": 0, "chain_franchise": 0}
        m.mem_write(FCODE, footer.code_for(FCODE, fconfig, bytes.fromhex("e856feffffeb13")))
        hconfig = {"body_fn": FCODE + footer.runtime.LABELS["xt_body"], "chain_close": 0x13ED70,
                   "flags": history.ALL_PARTS, "hall_bar": 100, "hall_wait": 1, "hall_window": 15, "hall_class": 2}
        m.mem_write(HCODE, history.code_for(HCODE, hconfig))
        m.mem_write(FLD, b"\xd9\x05" + struct.pack("<I", SCRATCH) + b"\xc2\x04\x00")   # fld [scratch]; ret 4
        self.put(0xE576A0, 2)
        self.put(0xE576A4, 8)
        self.put(0x3204AD, YEAR_BASE + 11)
        self.put(0xE576B8, 1)                                   # second franchise season: 2027
        m.mem_write(0x5151C4, bytes([WEEKS]))
        m.mem_write(0x133A41, bytes([SB]))
        self.put(0xBD7F98, 1)
        self.build_league()
        self.writes = []
        m.hook_add(uc.UC_HOOK_CODE, self.on_func, begin=0xC0000, end=0x14F000)
        m.hook_add(uc.UC_HOOK_MEM_WRITE, self.on_write)

    # ------------------------------------------------------------------------------------------------ the league
    def put(self, va, value):
        self.m.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def get(self, va):
        return struct.unpack("<I", self.m.mem_read(va, 4))[0]

    def build_league(self):
        m, rng = self.m, self.rng
        self.text_at = NAMES
        self.players = {}                    # pointer -> dict
        self.roster = {t: [] for t in range(32)}
        for t in range(32):
            team = TEAMS + t * 500
            self.put(0xE576D4 + 4 * t, t // 4)                  # divisions of four clubs in index order
            coach = PLAYERS + 0x30000 + t * 0xA8
            self.put(coach, self.text(f"Coach{t}"))
            self.put(coach + 4, self.text(f"Hc{chr(65 + t // 26)}{chr(65 + t % 26)}"))
            self.put(team + 0x14C, coach)
            for k in range(6):
                pos = (0, 7, 3, 9, 16, 4)[k]
                p = PLAYERS + (t * 6 + k) * 0x54
                self.put(p + 0x10, self.text("P"))
                self.put(p + 0x14, self.text(f"Last{chr(65 + t // 26)}{chr(65 + t % 26)}{chr(65 + k)}"))
                m.mem_write(p + 0x35, bytes([pos]))
                m.mem_write(p + 6, struct.pack("<H", 1000 + t * 6 + k))
                self.put(p + 0x24, 4 << 8)                       # years pro 4: current season slot 4
                season = {f: rng.randint(0, 60) for f in STAT_FIELDS}
                season[8] = rng.randint(2000, 4900) if pos == 0 else 0
                season[2] = rng.randint(200, 1500) if pos == 7 else rng.randint(0, 60)
                season[13] = rng.randint(300, 1500) if pos in (3, 9) else 0
                season[19] = rng.randint(0, 30) if pos == 16 else 0
                retired = t in (1, 2) and k == 0
                self.players[p] = dict(team=t, pos=pos, season=season, retired=retired, index=t * 6 + k)
                m.mem_write(p + 8, bytes([8 if retired else 0]))
                # history stream: three older seasons with this club, one with another club, the end word
                words = []
                for slot in range(4):
                    club = t if slot != 1 else (t + 1) % 32
                    words.append(slot << 23 | 87 << 16 | (club + 1))
                    words.append(slot << 23 | 0 << 16 | 16)            # games
                    for f, v in ((8, season[8] // 2), (2, season[2] // 2), (13, season[13] // 2), (19, season[19]),
                                 (9, 20 if pos == 0 else 0), (96, 1 if retired and slot == 2 else 0)):
                        if v:
                            words.append(slot << 23 | f << 16 | (v & 0xFFFF))
                for f in (8, 2, 13, 19, 9):                              # the current season (slot 4)
                    v = season.get(f, 0)
                    if v:
                        words.append(4 << 23 | f << 16 | (v & 0xFFFF))
                words.append(4 << 23 | 0 << 16 | 16)
                words[-1] |= 0x80000000
                stream = STREAMS + (t * 6 + k) * 0x200
                m.mem_write(stream, struct.pack(f"<{len(words)}I", *words))
                self.put(p + 0x2C, stream)
                self.players[p]["stream"] = words
                self.roster[t].append(p)
        self.put(0xB72918, TEAMS + 0x8000)                       # the roster root: +4 = the primary pool
        self.put(TEAMS + 0x8000 + 4, PLAYERS)
        # awards: MVP club 3's QB, OPOY club 5's HB, Super Bowl MVP the champion's QB (set after the playoffs)
        self.put(0xE5A2F0 + 0x5800, self.roster[3][0]); self.put(0xE5A2F0 + 0x5804, TEAMS + 3 * 500)
        self.put(0xE5A2F0 + 0x5810, self.roster[5][1]); self.put(0xE5A2F0 + 0x5814, TEAMS + 5 * 500)
        self.user = 9

    def text(self, value):
        at = self.text_at
        self.m.mem_write(at, _wide(value))
        self.text_at += (len(value) + 1) * 2 + 2
        return at

    # ------------------------------------------------------------------------------------------------ mocks
    def ret(self, value=0, pop=0):
        sp = self.m.reg_read(x86.UC_X86_REG_ESP)
        self.m.reg_write(x86.UC_X86_REG_EAX, value & 0xFFFFFFFF)
        self.m.reg_write(x86.UC_X86_REG_EIP, self.get(sp))
        self.m.reg_write(x86.UC_X86_REG_ESP, sp + 4 + pop)

    def ret_float(self, value):
        self.m.mem_write(SCRATCH, struct.pack("<f", float(value)))
        self.m.reg_write(x86.UC_X86_REG_EIP, FLD)

    def on_func(self, _uc, address, _size, _data):
        ecx, edx = self.m.reg_read(x86.UC_X86_REG_ECX), self.m.reg_read(x86.UC_X86_REG_EDX)
        if address == 0xC4C50:
            self.ret(TEAMS + ecx * 500 if ecx < 32 else 0)
        elif address == 0xC6430:
            self.ret(32)
        elif address == 0xC3E70:
            team = (ecx - TEAMS) // 500
            self.ret(self.roster[team][0] if self.roster.get(team) else 0)
        elif address == 0xC3E80:
            team = (ecx - TEAMS) // 500
            lst = self.roster[team]
            i = lst.index(edx)
            self.ret(lst[i + 1] if i + 1 < len(lst) else 0)
        elif address == 0xC4D70:
            self.ret(TEAMS + self.user * 500)
        elif address == 0x14EDB0:
            self.put(0xBD7F98, ecx)
            self.ret()
        elif address == 0x14EE40:
            self.assertEqual(self.get(0xBD7F98), 0, "season lines are read in the regular-season class")
            self.ret(self.players[ecx]["season"].get(edx, 0) if ecx in self.players else 0)
        elif address == 0xCA810:
            self.ret(self.live_roster.get(ecx, 0))
        elif address == 0xCB240:
            self.ret_float(self.live_player.get(ecx, {}).get(edx, 0))
        elif address == 0xCB2D0:
            self.ret_float(self.live_club.get(ecx, {}).get(edx, 0))

    def on_write(self, _uc, _access, address, size, _value, _data):
        body = FDATA + footer.STATE_SIZE                          # the static body (also before its pointer is set)
        inside = body <= address < body + ext.BODY_SIZE or STACK <= address < STACK + 0x10000 \
            or FDATA <= address < FDATA + 64 or address == SCRATCH or address == 0xBD7F98
        if not inside:
            self.writes.append(hex(address))

    def call(self, label, ecx=0):
        sp = STACK + 0x8000
        self.m.mem_write(sp, struct.pack("<I", SENTINEL))
        self.m.reg_write(x86.UC_X86_REG_ESP, sp)
        self.m.reg_write(x86.UC_X86_REG_ECX, ecx)
        self.m.emu_start(HCODE + history.runtime.LABELS[label], SENTINEL, count=50_000_000)
        self.assertEqual(self.m.reg_read(x86.UC_X86_REG_EIP), SENTINEL)

    def body(self):
        pointer = self.get(FDATA + 4)
        self.assertNotEqual(pointer, 0)
        return ext.seal(bytes(self.m.mem_read(pointer, ext.BODY_SIZE)))

    # ------------------------------------------------------------------------------------------------ a season
    def play(self, row, slot, home, away, hp, ap):
        cell = row * 17 + slot
        self.m.mem_write(0xE57C40 + cell * 8, bytes([3, home, away, 0, 0, 0, 0, 0]))
        self.m.mem_write(0xE587F0 + cell * 10, bytes([hp, 0, 0, 0, 0, ap, 0, 0, 0, 0]))
        self.put(0xE576B4, row)
        self.put(0xE576BC, slot)
        # live objects of this game: two clubs, six nodes each (the clubs' players in order)
        self.live_roster, self.live_player, self.live_club = {}, {}, {}
        for side, club in ((0, home), (1, away)):
            obj = (0xB30864, 0xB30A58)[side]
            base = (0xB30BF8, 0xB3214C)[side]
            self.m.mem_write(obj + 0x11C, bytes([6]))
            yards = 0
            for k, p in enumerate(self.roster[club]):
                node = base + (k + 1) * 0x54
                self.live_roster[node] = p
                pos = self.players[p]["pos"]
                stats = {35: 30, 4: 20, 76: 250 + row * 10 + k, 64: 2, 22: 1} if pos == 0 else \
                        {3: 18, 80: 90 + row, 63: 1, 46: 2, 79: 15} if pos == 7 else \
                        {46: 6, 79: 80 + slot, 62: 1} if pos in (3, 9) else \
                        {50: 7, 47: 2, 23: 0, 17: 1}
                self.live_player[node] = stats
                yards += stats.get(76, 0)
            self.live_club[obj] = {91: hp if side == 0 else ap, 76: yards, 80: 100, 14: 18, 208: 350}
        self.call("history_game", ecx=4)

    def run_season(self):
        rng = self.rng
        games = []
        for row in range(WEEKS):                                # every club plays each regular week
            order = list(range(32))
            rng.shuffle(order)
            for slot in range(16):
                home, away = order[2 * slot], order[2 * slot + 1]
                hp, ap = rng.randint(0, 40), rng.randint(0, 40)
                self.play(row, slot, home, away, hp, ap)
                games.append((row, slot, home, away, hp, ap))
        # playoffs: two wild card games, two divisional (the two byes enter), conference, Super Bowl
        bracket = [(WEEKS, 0, 1, 2, 24, 17), (WEEKS, 1, 9, 8, 10, 13),       # 1 and 8 win
                   (WEEKS + 1, 0, 0, 1, 31, 7), (WEEKS + 1, 1, 3, 8, 14, 21),  # 0 and 8 win (0 and 3 had byes)
                   (WEEKS + 2, 0, 0, 8, 27, 20),                              # 0 wins the conference
                   (SB, 0, 0, 4, 30, 29)]                                    # 0 beats 4 (no earlier games for 4)
        for row, slot, home, away, hp, ap in bracket:
            self.play(row, slot, home, away, hp, ap)
            games.append((row, slot, home, away, hp, ap))
        self.put(0xE5A2F0 + 0x5888, self.roster[0][0]); self.put(0xE5A2F0 + 0x588C, TEAMS)
        self.put(0xE576A4, 9)
        self.call("history_season_close")
        return games

    def model(self, games):
        L = [dict(w=0, l=0, t=0, pf=0, pa=0, dw=0, dl=0, dt=0, result=0, bye=0, wc=0) for _ in range(32)]
        div = [t // 4 for t in range(32)]
        for row, slot, h, a, hp, ap in games:
            if row < WEEKS:
                k = "w" if hp > ap else "l" if hp < ap else "t"
                ka = {"w": "l", "l": "w", "t": "t"}[k]
                L[h][k] += 1; L[a][ka] += 1
                L[h]["pf"] += hp; L[h]["pa"] += ap; L[a]["pf"] += ap; L[a]["pa"] += hp
                if div[h] == div[a]:
                    L[h]["d" + k] += 1; L[a]["d" + ka] += 1
                continue
            rnd = row + 4 - SB
            win, lose = (h, a) if hp > ap else (a, h)
            if rnd == 1:
                L[h]["wc"] = L[a]["wc"] = 1
            if rnd == 2:
                for t in (h, a):
                    if not L[t]["wc"]:
                        L[t]["bye"] = 1
            L[lose]["result"] = max(L[lose]["result"], rnd)
            L[win]["result"] = max(L[win]["result"], 5 if rnd == 4 else rnd)

        def pct(x):
            g = x["w"] + x["l"] + x["t"]
            return (2 * x["w"] + x["t"]) * 500 // g if g else 0

        def dpct(x):
            g = x["dw"] + x["dl"] + x["dt"]
            return (2 * x["dw"] + x["dt"]) * 500 // g if g else 0

        def key(i):
            x = L[i]
            return (pct(x), dpct(x), x["pf"] - x["pa"], -i)
        place = [min(4, 1 + sum(1 for o in range(32) if o != i and div[o] == div[i] and key(o) > key(i)))
                 for i in range(32)]
        return L, place

    # ------------------------------------------------------------------------------------------------ tests
    def test_a_season_is_recorded_like_the_model(self):
        games = self.run_season()
        view = ext.read_body(self.body())
        self.assertEqual(view["bad"], [])
        seasons = ext.decode_seasons(view["blocks"][1])
        self.assertEqual(len(seasons), 1)
        season = seasons[0]
        self.assertEqual(season["year"], 2027)
        L, place = self.model(games)
        for club in range(32):
            got, want = season["clubs"][club], L[club]
            self.assertEqual((got["wins"], got["losses"], got["ties"], got["points_for"], got["points_against"],
                              got["playoff_code"], got["bye"], got["place"], got["division_champion"]),
                             (want["w"], want["l"], want["t"], want["pf"], want["pa"], want["result"],
                              bool(want["bye"]), place[club], place[club] == 1), club)
            self.assertEqual(got["coach"]["last"], f"HC{chr(65 + club // 26)}{chr(65 + club % 26)}")
            self.assertEqual(got["coach"]["position_code"], 31)
        self.assertEqual((season["champion"], season["runner_up"], season["champion_points"],
                          season["runner_up_points"]), (0, 4, 30, 29))
        self.assertEqual(season["user_club"], self.user)
        self.assertEqual(season["awards"]["mvp"]["last"], "LASTADA")
        self.assertEqual(season["awards"]["mvp"]["club"], 3)
        self.assertEqual(season["awards"]["opoy"]["club"], 5)
        self.assertEqual(season["awards"]["sb_mvp"]["club"], 0)
        totals = ext.decode_totals(view["blocks"][2])
        self.assertEqual((totals["first_year"], totals["seasons"]), (2027, 1))
        self.assertEqual(totals["clubs"][0]["sb_wins"], 1)
        self.assertEqual(totals["clubs"][4]["sb_appearances"], 1)
        self.assertEqual(sum(c["wins"] for c in totals["clubs"]), sum(L[c]["w"] for c in range(32)))
        self.assertEqual(self.writes, [])
        self.assertEqual(view["info"]["closes"], 1)
        self.assertEqual(view["info"]["captures"], len(games))

    def test_records_leaders_and_hall_of_fame(self):
        games = self.run_season()
        view = ext.read_body(self.body())
        records = ext.decode_records(view["blocks"][3])
        # single-season passing yards: the best QB season in the league is the league record
        qbs = [(p, d) for p, d in self.players.items() if d["pos"] == 0]
        best = max(qbs, key=lambda pd: (pd[1]["season"][8], -pd[1]["index"]))
        league = records["league"][("passing_yards", "season")]
        self.assertEqual(league["value"], best[1]["season"][8])
        self.assertEqual(league["club"], best[1]["team"])
        self.assertEqual(league["year"], 2027)
        # single-game passing yards: 250 + row*10 + k is highest in the last playoff row for a QB (k = 0)
        game_best = records["league"][("passing_yards", "game")]
        self.assertEqual(game_best["value"], 250 + SB * 10)
        self.assertEqual(game_best["week_row"], SB)
        # club leaders: club 7's rushing leader is its HB with his seasons at the club (the slot-1 season was elsewhere)
        leaders = ext.decode_leaders(view["blocks"][4])
        hb = self.roster[7][1]
        d = self.players[hb]
        with_club = sum(d["season"][2] // 2 for slot in (0, 2, 3)) + d["season"][2]
        rows = leaders["clubs"][(7, "rushing_yards")]
        self.assertEqual(rows[0]["value"], with_club)
        self.assertTrue(rows[0]["linked"] and rows[0]["new"])
        self.assertEqual(rows[0]["player"], d["index"])
        # the league career leaders count every season, the other club's included: the model's top five
        careers = sorted((x["season"][2] // 2 * 4 + x["season"][2] for x in self.players.values()), reverse=True)
        self.assertEqual([r["value"] for r in leaders["league"]["rushing_yards"]], careers[:5])
        # Hall of Fame: the two retirees are candidates (retired 2027, wait 1 season)
        hall = ext.decode_hall(view["blocks"][5])
        self.assertEqual(sorted(c["club"] for c in hall["candidates"]), [1, 2])
        self.assertEqual(hall["inductees"], [])
        self.assertEqual(self.writes, [])

    def test_box_scores_follow_the_users_games(self):
        games = self.run_season()
        view = ext.read_body(self.body())
        box = ext.decode_boxscores(view["blocks"][6])
        mine = [g for g in games if self.user in (g[2], g[3])]
        self.assertEqual(box["year"], 2027)
        self.assertEqual(len(box["games"]), len(mine))
        for stored, (row, slot, home, away, hp, ap) in zip(box["games"], mine):
            self.assertEqual((stored["week_row"], stored["slot"], stored["home"], stored["away"],
                              stored["home_points"], stored["away_points"]), (row, slot, home, away, hp, ap))
            side = stored["user_side"]
            self.assertEqual(side, 0 if home == self.user else 1)
            self.assertEqual(stored["team_stats"][side]["points"], hp if side == 0 else ap)
            passing = [l for l in stored["lines"] if l["kind"] == "passing"]
            self.assertEqual(sum(l["values"]["yards"] for l in passing), stored["team_stats"][side]["passing_yards"])
            self.assertEqual(len(stored["lines"]), 6)
            self.assertTrue(stored["simulated"])
            kinds = {l["kind"] for l in stored["opponent_leaders"]}
            self.assertEqual(kinds, {"passing", "rushing", "receiving", "defense"})

    def test_a_second_season_adds_to_linked_leaders_and_inducts_a_class(self):
        self.run_season()
        first = ext.read_body(self.body())
        hb = self.roster[7][1]
        v1 = ext.decode_leaders(first["blocks"][4])["clubs"][(7, "rushing_yards")][0]["value"]
        # next season: the grid starts over, the HB adds a season line
        self.m.mem_write(0xE57C40, bytes(374 * 8))
        self.m.mem_write(0xE587F0, bytes(374 * 10))
        self.put(0xE576B8, 2)
        self.put(0xE576A4, 8)
        self.players[hb]["season"][2] = 1111
        self.run_season()
        view = ext.read_body(self.body())
        rows = ext.decode_leaders(view["blocks"][4])["clubs"][(7, "rushing_yards")]
        self.assertEqual(rows[0]["value"], v1 + 1111)
        seasons = ext.decode_seasons(view["blocks"][1])
        self.assertEqual([s["year"] for s in seasons], [2028, 2027])
        hall = ext.decode_hall(view["blocks"][5])
        # retired 2027, wait one season: eligible for the 2028 class if the score clears the test's bar of 100
        eligible = [c for c in ext.decode_hall(first["blocks"][5])["candidates"] if c["score"] >= 100]
        self.assertEqual(len(hall["inductees"]), min(2, len(eligible)))
        for inductee in hall["inductees"]:
            self.assertEqual(inductee["inducted"], 2028)
            self.assertTrue(inductee["new"])
        totals = ext.decode_totals(view["blocks"][2])
        self.assertEqual(totals["seasons"], 2)
        box = ext.decode_boxscores(view["blocks"][6])
        self.assertEqual(box["year"], 2028)                      # last season's box scores were replaced

    def test_preseason_pro_bowl_and_outside_franchise_record_nothing(self):
        self.put(0xE576A4, 7)                                    # preseason
        self.play(0, 0, 9, 10, 21, 3)
        self.assertEqual(self.get(FDATA + 4), 0)                 # not even the body was made
        self.put(0xE576A4, 9)
        self.play(SB + 1, 0, 9, 10, 21, 3)                       # the Pro Bowl row
        self.assertEqual(self.get(FDATA + 4), 0)
        self.put(0xE576A0, 1)
        self.put(0xE576A4, 8)
        self.play(0, 0, 9, 10, 21, 3)
        self.call("history_season_close")
        self.assertEqual(self.get(FDATA + 4), 0)


class StaticTests(unittest.TestCase):
    def test_install_on_the_footer_host_and_beside_the_champions(self):
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
        from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_honors as honors, nfl2k5_champions as champions
        retail = retail_xbe()
        payload, _ = space.apply(retail, (), scaleout=True)
        with self.assertRaises(ValueError):
            history.apply(payload)                               # the footer host comes first
        payload, _ = honors.apply(payload)
        payload, _ = footer.apply(payload, static_body=True)
        installed, receipt = history.apply(payload)
        self.assertEqual(history.status(installed), "applied")
        self.assertEqual(champions.status(installed), "applied")
        self.assertEqual(honors.status(installed), "applied")
        self.assertEqual(footer.status(installed), "applied")
        self.assertEqual([s["va"] for s in receipt["sites"]], ["0x1356c8", "0x1356ff", "0x248601"])
        self.assertEqual(history.apply(installed)[1]["status"], "already_applied")
        self.assertEqual(len(history.runtime.CODE) <= history.CODE_SIZE, True)


if __name__ == "__main__":
    unittest.main()
