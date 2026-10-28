"""Job hn1 (beta 79): the Super Bowl champion pop-up, the champions history and the modern award voting.

EXPERIMENTAL / UNWITNESSED in game. Static and model checks run everywhere. The native classes map the retail USA
``default.xbe`` with the honors owner (which installs ``nfl2k5_champions``) and run the real code under Unicorn:

* the stage-9 advance site (0x2485FA): the notice text for a Franchise Super Bowl, the history slot it writes, the retail
  retirement pass still running after it, and every case that must stay silent;
* the history: 36 seasons through the 32-slot ring, a corrupt or foreign byte reading as empty, the Player Card's third
  page drawing the ten newest seasons and the newest Super Bowl in the card's own fonts and positions;
* the award voting (0x116E55): ``champions_modern_awards`` on synthetic leagues, compared with the pure Python model
  ``nfl2k5_champions.choose_awards`` (the 10-season measurement uses the same model on the game's own simulated seasons).

Boundaries: the team records (wins, losses, ties) are supplied by substituting the three retail record routines
(0xC7720, 0xC7750, 0xC7780); the full retail advance and awards pass on a played season is covered by the simulated seasons
in the report, not here. Nothing here is an in-game result.
"""
from __future__ import annotations

import re
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_champions as champions  # noqa: E402
from mod_editor.core import nfl2k5_champions_code as runtime  # noqa: E402
from mod_editor.core import nfl2k5_honors as honors  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tests.mod_editor.test_nfl2k5_honors import (  # noqa: E402
    AWARDS, CLASS, HAVE_UC, LEAGUE_MODE, LEAGUE_TEAMS, SCORES, SEASONS, XBE, Machine, _retail, word,
)

POSITIONS = champions.POSITIONS
YEAR_IMM = 0x3204AD
SB_ROW = 0x133A41
NOTICE = 0x14E520
RETIRE = 0x2BDB00
AWARD_TAIL = 0x115FB0


class StaticTests(unittest.TestCase):
    """Run everywhere."""

    def test_template_fits_and_links_only_to_itself(self):
        self.assertLessEqual(len(runtime.CODE), champions.CODE_SIZE)
        self.assertEqual(champions.REQUESTS, (("nfl2k5_champions", "code", 4608, 16),))
        self.assertEqual(champions.CODE_SIZE % 16, 0)
        for offset, kind, symbol, _value in runtime.RELOCATIONS:
            self.assertIn(kind, (1, 2))
            self.assertEqual(symbol, "code")
            self.assertLessEqual(offset + 4, len(runtime.CODE))
        for entry in ("champions_advance", "champions_awards", "champions_ratings", "champions_bio",
                      "champions_advance_notice", "champions_modern_awards"):
            self.assertIn(entry, runtime.LABELS)

    def test_code_for_relocates_with_the_page(self):
        a, b = champions.code_for(0x1600000), champions.code_for(0x1601000)
        self.assertEqual(len(a), champions.CODE_SIZE)
        self.assertTrue(a.endswith(b"\xcc" * (champions.CODE_SIZE - len(runtime.CODE))))
        absolute = {off for off, kind, _s, _v in runtime.RELOCATIONS if kind == 1}
        differ = {i for i in range(len(a)) if a[i] != b[i]}
        self.assertTrue(differ)
        self.assertTrue(differ <= {off + k for off in absolute for k in range(4)})

    def test_sites_are_rel32_into_the_entries(self):
        code_va = 0x1600000
        at = champions.labels(code_va)
        rows = champions.sites(code_va)
        self.assertEqual([r[0] for r in rows], ["stage_advance", "season_awards"])
        for (label, va, before, after), (_l, _v, _b, entry, opcode, length) in zip(rows, champions.SITE_TABLE):
            self.assertEqual((len(before), len(after), after[0]), (5, length, opcode), label)
            self.assertEqual(va + 5 + struct.unpack_from("<i", after, 1)[0], at[entry])
        self.assertEqual({va: before for _l, va, before, _a in rows},
                         {0x2485FA: bytes.fromhex("e801550700"), 0x116E55: bytes.fromhex("e856f1ffff")})

    def test_trailing_owner_is_placed_after_the_module_loader(self):
        self.assertEqual(space.TRAILING_OWNERS, ("nfl2k5_champions",))
        self.assertEqual(space.LATE_OWNERS[-1], "nfl2k5_module_loader")        # nothing moved
        self.assertNotIn("nfl2k5_champions", space.LATE_OWNERS)
        self.assertTrue(set(champions.REQUESTS) <= set(honors.REQUESTS))
        rows = space._scale_allocations(list(honors.REQUESTS) + [("nfl2k5_module_loader", "code", 64, 16)])
        code = [r["owner"] for r in rows if r["kind"] == "code"]
        self.assertLess(code.index("nfl2k5_module_loader"), code.index("nfl2k5_champions"))

    def test_award_rule_weights_match_the_native_tables(self):
        source = (ROOT / "tools/nfl2k5_champions/runtime.c").read_text(encoding="utf-8")
        for name, key in (("mvp_weight", "mvp_weight_percent"), ("opoy_weight", "opoy_weight_percent"),
                          ("dpoy_weight", "dpoy_weight_percent")):
            found = re.search(r"static const u8 %s\[17\] = \{([^}]*)\};" % name, source)
            self.assertIsNotNone(found, name)
            self.assertEqual(tuple(int(x) for x in found.group(1).split(",")), champions.AWARD_RULE[key], name)
        for key in ("mvp_weight_percent", "opoy_weight_percent", "dpoy_weight_percent"):
            self.assertEqual(len(champions.AWARD_RULE[key]), 17)
        marks = dict(champions.OTHERWORLDLY_MARKS)
        self.assertEqual(marks, {"sacks2": 60, "tackles": 300, "rush_yds": 2500, "rec_yds": 2200, "pass_yds": 6000,
                                 "pass_td": 60, "def_int": 15})
        for fragment in ("/ 60;", "/ 300;", "/ 2500;", "/ 2200;", "/ 6000;", "/ 60;", "/ 15;"):
            self.assertIn(fragment, source)


def line(**kw):
    base = dict(pass_yds=0, pass_td=0, pass_int=0, rush_yds=0, rush_td=0, rec=0, rec_yds=0, rec_td=0, tackles=0,
                sacks2=0, def_int=0, ff=0)
    base.update(kw)
    return base


def player(name, pos, team, yrs=5, **stats):
    return {"name": name, "pos": POSITIONS.index(pos), "team": team, "yrs": yrs, **line(**stats)}


class ModelTests(unittest.TestCase):
    """The voting rule on plain data."""

    RECORDS = {0: (14, 3, 0), 1: (12, 5, 0), 2: (6, 11, 0), 3: (9, 8, 0)}

    def winners(self, players):
        return champions.choose_awards(players, lambda t: self.RECORDS[t])

    def names(self, players):
        return {k: (v["name"] if v else None) for k, v in self.winners(players).items()}

    def test_a_quarterback_on_a_winner_takes_the_mvp_over_better_skill_numbers(self):
        qb = player("QB1", "QB", 0, pass_yds=4600, pass_td=38, pass_int=9, rush_yds=300, rush_td=3)
        rb = player("RB1", "HB", 1, rush_yds=1900, rush_td=18, rec=60, rec_yds=500, rec_td=3)
        wr = player("WR1", "WR", 1, rec=120, rec_yds=1700, rec_td=14)
        lb = player("LB1", "ILB", 0, tackles=170, sacks2=14, def_int=3, ff=4)
        got = self.names([lb, rb, wr, qb])
        self.assertEqual(got["mvp"], "QB1")
        self.assertIn(got["opoy"], ("RB1", "WR1"))
        self.assertEqual(got["dpoy"], "LB1")

    def test_team_record_matters_for_the_mvp_only(self):
        great_on_a_loser = player("QBLOSER", "QB", 2, pass_yds=4900, pass_td=40, pass_int=8)
        good_on_a_winner = player("QBWINNER", "QB", 0, pass_yds=4300, pass_td=32, pass_int=10)
        got = self.names([great_on_a_loser, good_on_a_winner])
        self.assertEqual(got["mvp"], "QBWINNER")
        self.assertEqual(got["opoy"], "QBLOSER")              # not the MVP, so he can still be offensive player of the year

    def test_otherworldly_seasons_win_mvp_at_any_position_and_on_any_team(self):
        qb = player("QB1", "QB", 0, pass_yds=5000, pass_td=45, pass_int=8)
        cases = {
            "edge": player("EDGE", "DE", 2, sacks2=62, tackles=60),                  # 31 sacks
            "linebacker": player("LB", "ILB", 2, tackles=305),
            "runner": player("RB", "HB", 2, rush_yds=2510, rush_td=20),
            "receiver": player("WR", "WR", 2, rec=150, rec_yds=2210, rec_td=15),
            "passer": player("QB2", "QB", 2, pass_yds=6001, pass_td=50, pass_int=5),
            "corner": player("CB", "CB", 2, def_int=15),
        }
        for label, wonder in cases.items():
            with self.subTest(label):
                self.assertEqual(self.names([qb, wonder])["mvp"], wonder["name"])
        near = player("NEAR", "DE", 2, sacks2=58, tackles=60)                       # 29 sacks: great, not otherworldly
        self.assertEqual(self.names([qb, near])["mvp"], "QB1")
        self.assertEqual(self.names([qb, near])["dpoy"], "NEAR")
        two = [player("A", "DE", 2, sacks2=61), player("B", "ILB", 2, tackles=450)]  # the bigger ratio wins
        self.assertEqual(self.names([qb] + two)["mvp"], "B")

    def test_the_mvp_cannot_also_win_a_position_award(self):
        wonder = player("WONDER", "DE", 2, sacks2=70, tackles=80, ff=5)
        other = player("OTHER", "DE", 1, sacks2=30, tackles=60)
        got = self.names([wonder, other])
        self.assertEqual((got["mvp"], got["dpoy"]), ("WONDER", "OTHER"))

    def test_rookie_awards_use_rookies_only_and_ignore_the_team(self):
        qb = player("VET", "QB", 0, pass_yds=4800, pass_td=40)
        rookie_qb = player("ROOKIEQB", "QB", 2, yrs=1, pass_yds=3500, pass_td=24, pass_int=12)
        rookie_wr = player("ROOKIEWR", "WR", 2, yrs=1, rec=70, rec_yds=900, rec_td=6)
        rookie_de = player("ROOKIEDE", "DE", 2, yrs=1, sacks2=18, tackles=40)
        rookie_cb = player("ROOKIECB", "CB", 2, yrs=1, def_int=2, tackles=40)
        got = self.names([qb, rookie_wr, rookie_qb, rookie_de, rookie_cb])
        self.assertEqual((got["oroy"], got["droy"]), ("ROOKIEQB", "ROOKIEDE"))

    def test_kickers_punters_and_linemen_never_win(self):
        for pos in ("K", "P", "C", "G", "T"):
            self.assertEqual(self.names([player("X", pos, 0, pass_yds=9999, tackles=999, sacks2=99)])["mvp"], None)

    def test_ties_go_to_the_first_player_and_empty_leagues_have_no_winner(self):
        a, b = player("FIRST", "WR", 0, rec_yds=1000), player("SECOND", "WR", 0, rec_yds=1000)
        qb = player("QB1", "QB", 0, pass_yds=4500, pass_td=35)
        self.assertEqual(self.names([qb, a, b])["opoy"], "FIRST")
        self.assertEqual(self.names([]), {k: None for k in ("mvp", "opoy", "dpoy", "oroy", "droy")})
        self.assertEqual(champions.team_factor(0, 0, 0), 35)
        self.assertEqual((champions.team_factor(13, 4, 0), champions.team_factor(8, 8, 1)), (100, 53))


@unittest.skipUnless(XBE.is_file(), "pinned USA XBE required")
class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        if cls.retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.patched, cls.receipt = honors.apply(cls.retail)

    def test_the_guards_are_the_retail_bytes(self):
        digests = champions.guard_digests(self.retail)
        for name, va, size, digest in champions.GUARDS:
            self.assertEqual(digests[name], digest, name)

    def test_both_owners_install_together(self):
        self.assertEqual(honors.status(self.patched), "applied")
        self.assertEqual(champions.status(self.patched), "applied")
        self.assertEqual(champions.status(self.retail), "retail")
        found = champions.allocations(self.patched)
        self.assertEqual((found["code"]["size"], found["code"]["align"]), (4608, 16))
        self.assertEqual(self.receipt["champions"]["code_va"], hex(found["code"]["va"]))
        again, receipt = honors.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt["already_applied"])

    def test_the_card_links_to_the_champions_pages(self):
        code_va = honors.allocations(self.patched)["code"]["va"]
        champ_va = champions.allocations(self.patched)["code"]["va"]
        at = champions.labels(champ_va)
        code = XbeImage(self.patched).read(code_va, honors.CODE_SIZE)
        absolute = [struct.unpack_from("<I", code, off)[0] for off, kind, sym, _v in honors.runtime.RELOCATIONS
                    if kind == 1 and sym.startswith("champ_")]
        self.assertEqual(set(absolute), {at["champions_ratings"], at["champions_bio"]})

    def test_a_single_foreign_site_is_refused(self):
        champ_va = champions.allocations(self.patched)["code"]["va"]
        for label, va, before, _after in champions.sites(champ_va):
            with self.subTest(site=label):
                buf = bytearray(self.patched)
                buf[va - 0x10000:va - 0x10000 + len(before)] = before
                self.assertEqual(champions.status(bytes(buf)), "foreign")
                self.assertEqual(honors.status(bytes(buf)), "foreign")

    def test_a_changed_dependency_is_refused(self):
        buf = bytearray(self.retail)
        buf[0x14E520 - 0x10000] ^= 0xFF                               # the notice routine's first byte
        self.assertEqual(champions.status(bytes(buf)), "foreign")
        self.assertEqual(honors.status(bytes(buf)), "foreign")

    def test_champions_code_without_the_honors_owner_is_not_applied(self):
        champ_va = champions.allocations(self.patched)["code"]["va"]
        raw = XbeImage(self.patched).offset(champ_va, champions.CODE_SIZE)
        buf = bytearray(self.patched)
        buf[raw:raw + champions.CODE_SIZE] = b"\xcc" * champions.CODE_SIZE
        self.assertEqual(honors.status(bytes(buf)), "foreign")          # mixed: sites patched, code empty

    def test_the_two_award_and_advance_sites_are_the_only_retail_changes_outside_the_owners(self):
        retail_image, image = XbeImage(self.retail), XbeImage(self.patched)
        for label, va, before, after in champions.sites(champions.allocations(self.patched)["code"]["va"]):
            self.assertEqual(retail_image.read(va, 5), before)
            self.assertEqual(image.read(va, 5), after)


# ---------------------------------------------------------------------------------------------------------------
class LeagueMachine(Machine):
    """The F5 harness with room for a full league: the club table is wired into the roster object."""

    TEAMS = Machine.HEAP + 0x10000
    STRINGS = Machine.HEAP + 0x50000

    def __init__(self, payload):
        super().__init__(payload)
        self._string_at = self.STRINGS
        self.notices = []
        self.records = {}
        self.hook(NOTICE, self._notice)
        self.hook(0xC7720, lambda m: self.records.get(m.reg("ECX"), (0, 0, 0))[0])
        self.hook(0xC7750, lambda m: self.records.get(m.reg("ECX"), (0, 0, 0))[1])
        self.hook(0xC7780, lambda m: self.records.get(m.reg("ECX"), (0, 0, 0))[2])

    def wide(self, va, limit=120):
        # stack buffers hold stale bytes after the terminator: decode up to the first NUL only
        raw = bytes(self.uc.mem_read(va, limit * 2))
        end = next(i for i in range(0, len(raw), 2) if raw[i:i + 2] == b"\0\0")
        return raw[:end].decode("utf-16le")

    def _notice(self, m):
        self.notices.append((m.reg("ECX"), m.wide(m.reg("EDX"), 400)))
        self.calls.append("notice")

    def string(self, text):
        at = self._string_at
        self.uc.mem_write(at, text.encode("utf-16le") + b"\0\0")
        self._string_at += (len(text) + 1) * 2 + 2
        return at

    def team_ptr(self, index):
        return self.TEAMS + index * 0x1F4

    def club(self, index, city, nick, abbr, members=(), record=(0, 0, 0)):
        base = self.team_ptr(index)
        history = bytes(self.uc.mem_read(base + 0xE4, 32))     # the champions history lives in the club record
        self.uc.mem_write(base, bytes(0x1F4))
        self.uc.mem_write(base + 0xE4, history)
        self.put(base + 0x138, self.string(city))
        self.put(base + 0x104, self.string(nick))
        self.put(base + 0x108, self.string(abbr))
        for i, p in enumerate(members):
            self.put(base + 4 * i, p)
        self.put8(base + 0x11C, len(members))
        self.records[base] = record

    def wire(self, players):
        self.put(self.ROOT + 0x1C, self.TEAMS)
        self.put(self.ROOT + 0x18, 52)
        self.put(LEAGUE_MODE, 2)
        for i in range(34):                               # the league's club table (mode 2 reads it, not the roster)
            self.put(LEAGUE_TEAMS + 4 * i, self.team_ptr(i))

    def person(self, record, first, last, pos):
        self.put(record + 0x10, self.string(first))
        self.put(record + 0x14, self.string(last))
        self.put8(record + 0x35, POSITIONS.index(pos))

    def super_bowl(self, home, away, home_points, away_points, row=None):
        row = self.uc.mem_read(SB_ROW, 1)[0] if row is None else row
        cell = 0xE57C40 + (row * 17) * 8
        self.uc.mem_write(cell, bytes([3, home, away, 2, 8, 0, 6, 30]))
        scores = SCORES + (row * 17) * 10
        self.uc.mem_write(scores, bytes([home_points, 0, 0, 0, 0, away_points, 0, 0, 0, 0]))

    def set_year(self, season_index, base=2026):
        self.put(YEAR_IMM, base + 11)
        self.put(SEASONS, season_index)

    def slot(self, n):
        return bytes(self.uc.mem_read(self.team_ptr(n % 32) + 0xE4, 32))


def unpack_person(blob):
    def get(at, count):
        return sum(((blob[(at + b) >> 3] >> ((at + b) & 7)) & 1) << b for b in range(count))
    def chr6(s):
        return (" ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz -.'?" + " " * 7)[s]
    first = get(0, 6)
    last = "".join(chr6(get(6 + 6 * i, 6)) for i in range(12)).rstrip()
    return (chr6(first) if first else "", last, POSITIONS[get(78, 5)])


@unittest.skipUnless(XBE.is_file() and HAVE_UC, "pinned USA XBE and unicorn required")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = _retail()
        if retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.retail = retail
        cls.patched, _ = honors.apply(retail)
        cls.champ = champions.labels(champions.allocations(cls.patched)["code"]["va"])
        cls.state = honors.allocations(cls.patched)["data"]["va"]

    def machine(self):
        return LeagueMachine(self.patched)

    def season(self, m, *, winner=4, loser=9, high=31, low=24, mvp=True, sb_mvp=True, season_index=34, home_wins=True):
        """A finished Super Bowl in a 2026-based franchise: 2026 + 34 = 2060 -> Super Bowl 95; players on the winner."""
        qb = m.roster([(5, []), (3, []), (6, [])])
        m.club(winner, "Seattle", "Seahawks", "SEA", qb[:2])
        m.club(loser, "New England", "Patriots", "NE", qb[2:])
        m.person(qb[0], "Kenneth", "Walker III", "HB")
        m.person(qb[1], "Matthew", "Stafford", "QB")
        m.person(qb[2], "Drake", "Maye", "QB")
        m.wire(qb)
        m.set_year(season_index)
        m.super_bowl(winner if home_wins else loser, loser if home_wins else winner,
                     high if home_wins else low, low if home_wins else high)
        m.put(AWARDS + 0x5888, qb[0] if sb_mvp else 0)
        m.put(AWARDS + 0x5800, qb[1] if mvp else 0)
        m.put(AWARDS + 0x5804, m.team_ptr(winner))
        return qb

    # --- the pop-up -------------------------------------------------------------------------------------------
    def test_the_advance_shows_the_champion_and_records_it(self):
        m = self.machine()
        m.record(RETIRE, "retirement pass")
        self.season(m)
        m.call(self.champ["champions_advance"])
        self.assertEqual(m.calls, ["notice", "retirement pass"])        # the notice first, then the retail pass
        self.assertEqual(m.notices, [(0x0BADF00D, "Seattle Seahawks won Super Bowl XCV, 31-24 over the New England "
                                      "Patriots.\nSuper Bowl MVP: Kenneth Walker III, HB\nSeason MVP: Matthew "
                                      "Stafford, QB")])
        slot = m.slot(95)
        self.assertEqual(slot[:5], bytes([95, 5, 10, 31, 24]))
        self.assertEqual(unpack_person(slot[5:16]), ("K", "Walker III", "HB"))
        self.assertEqual(unpack_person(slot[16:27]), ("M", "Stafford", "QB"))
        self.assertEqual(slot[27], 5)                                    # the MVP's club + 1 (Seattle is club 4)
        check = 0xA5
        for b in slot[:28]:
            check ^= b
        self.assertEqual(slot[28], check)
        self.assertEqual(slot[29:], bytes(3))

    def test_a_road_winner_and_a_missing_mvp(self):
        m = self.machine()
        m.record(RETIRE, "retirement pass")
        self.season(m, home_wins=False, mvp=False, sb_mvp=False)
        m.call(self.champ["champions_advance"])
        self.assertEqual(m.notices[0][1], "Seattle Seahawks won Super Bowl XCV, 31-24 over the New England Patriots.")
        slot = m.slot(95)
        self.assertEqual(slot[:5], bytes([95, 5, 10, 31, 24]))
        self.assertEqual(slot[5:27], bytes(22))

    def test_it_stays_silent_outside_a_franchise_or_without_a_played_final(self):
        for label, change in (("not a franchise", lambda m: m.put(LEAGUE_MODE, 1)),
                              ("final not played", lambda m: m.super_bowl(4, 9, 0, 0)),
                              ("a tie", lambda m: m.super_bowl(4, 9, 20, 20)),
                              ("same club twice", lambda m: m.super_bowl(4, 4, 20, 10)),
                              ("no club", lambda m: m.super_bowl(40, 9, 20, 10)),
                              ("before Super Bowl I", lambda m: m.set_year(0, base=1960))):
            with self.subTest(label):
                m = self.machine()
                m.record(RETIRE, "retirement pass")
                self.season(m)
                change(m)
                m.call(self.champ["champions_advance"])
                self.assertEqual(m.calls, ["retirement pass"])
                self.assertEqual(m.notices, [])
                self.assertEqual(m.slot(95), bytes(32))

    def test_the_site_runs_the_retail_pass_with_its_registers(self):
        # the stub restores every register before the retail routine: the retirement pass sees what it saw before
        m = self.machine()
        seen = {}
        def retire(mm):
            seen.update({r: mm.reg(r) for r in ("EBX", "ESI", "EDI", "EBP")})
        m.hook(RETIRE, retire)
        self.season(m)
        m.call(self.champ["champions_advance"])
        self.assertEqual(seen, {r: 0x0BADF00D for r in ("EBX", "ESI", "EDI", "EBP")})

    # --- the history ------------------------------------------------------------------------------------------
    def fill(self, m, first, last):
        """Seasons first..last (Super Bowl numbers), clubs rotating, one advance each."""
        for n in range(first, last + 1):
            winner, loser = n % 31, (n + 7) % 31
            if winner == loser:
                loser += 1
            for idx in (winner, loser):
                m.club(idx, f"City{idx}", f"Nick{idx}", f"A{idx:02d}")
            m.wire(None)
            m.set_year(n - 61)
            m.super_bowl(winner, loser, 20 + n % 15, 7 + n % 6)
            m.put(AWARDS + 0x5888, 0)
            m.put(AWARDS + 0x5800, 0)
            m.call(self.champ["champions_advance"])

    def test_the_ring_keeps_the_last_32_seasons(self):
        m = self.machine()
        m.record(RETIRE, "retirement pass")
        self.fill(m, 60, 95)                                              # 36 seasons
        for n in range(64, 96):
            slot = m.slot(n)
            self.assertEqual(slot[0], n, n)
        for n in range(60, 64):                                           # 60..63 were overwritten by 92..95
            self.assertEqual(m.slot(n)[0], n + 32)

    def test_nothing_outside_the_32_bytes_changes(self):
        m = self.machine()
        m.record(RETIRE, "retirement pass")
        self.season(m)
        before = {i: bytes(m.uc.mem_read(m.team_ptr(i), 0x1F4)) for i in range(32)}
        m.call(self.champ["champions_advance"])
        for i in range(32):
            after = bytes(m.uc.mem_read(m.team_ptr(i), 0x1F4))
            diff = [k for k in range(0x1F4) if after[k] != before[i][k]]
            self.assertTrue(all(0xE4 <= k < 0x104 for k in diff), (i, diff))
        self.assertEqual(m.slot(95)[0], 95)

    # --- the Player Card page ---------------------------------------------------------------------------------
    def draw_card(self, m, page):
        for name, va in (("header", 0x3208E0), ("ratings", 0x320500), ("bio", 0x320760), ("photo", 0x320640),
                         ("model", 0x35B9C0)):
            m.record(va, name)
        m.capture_text()
        m.put(self.state, page)
        card = m.roster([(1, [])])[0]
        m.put(0xC90248, card)
        m.calls.clear()
        m.text.clear()
        m.call(0x320B70)
        return list(m.calls), list(m.text)

    def test_page_three_lists_the_ten_newest_seasons_and_the_latest_final(self):
        m = self.machine()
        m.record(RETIRE, "retirement pass")
        self.fill(m, 86, 94)
        self.season(m, winner=4, loser=9, high=31, low=24, season_index=34)   # Super Bowl 95
        m.call(self.champ["champions_advance"])
        calls, text = self.draw_card(m, 2)
        self.assertEqual(calls, ["header", "photo", "model"])
        counts = text[:20]
        labels = [t[0] for t in counts[0::2]]
        values = [t[0] for t in counts[1::2]]
        self.assertEqual(labels[0], "2060 SEA")                             # Super Bowl 95 = the 2060 season
        self.assertEqual(values[0], "31-24 NE")
        self.assertEqual(len(labels), 10)
        xs = (310.0,) * 5 + (490.0,) * 5
        ys = (318.0, 333.0, 347.0, 362.0, 377.0) * 2
        for (label, value, x, y) in zip(counts[0::2], counts[1::2], xs, ys):
            self.assertEqual(label[1:], (3, 2, 0xFF101010, (x - 8.0, y, 20.0)))
            self.assertEqual(value[1:], (3, 1, 0xFF101010, (x, y, 20.0)))
        lines = text[20:]
        self.assertEqual([t[0] for t in lines], ["SUPER BOWL XCV: SEA 31-24 NE", "SB MVP: K. Walker III, HB",
                                                 "MVP: M. Stafford, QB (SEA)"])
        for i, y in enumerate((137.0, 154.0, 171.0)):
            self.assertEqual(lines[i][1:], (8, 1, 0xFF101010, (198.0, y, 20.0)))

    def test_page_three_skips_missing_seasons_and_ignores_the_ones_outside_the_ring(self):
        m = self.machine()
        m.record(RETIRE, "retirement pass")
        self.fill(m, 60, 60)                                               # 35 seasons before the newest: outside the ring
        self.fill(m, 70, 70)
        self.fill(m, 91, 93)
        self.season(m, season_index=34)                                    # Super Bowl 95; 94 is missing
        m.call(self.champ["champions_advance"])
        _calls, text = self.draw_card(m, 2)
        wanted = ["2060 SEA"] + [f"{n + 1965} A{n % 31:02d}" for n in (93, 92, 91, 70)]
        self.assertEqual([t[0] for t in text[0:10:2]], wanted)
        self.assertEqual(len(text), 5 * 2 + 3)

    def test_page_three_of_an_old_save_is_empty_and_a_corrupt_slot_reads_as_empty(self):
        m = self.machine()
        m.wire(None)
        calls, text = self.draw_card(m, 2)
        self.assertEqual([t[0] for t in text], ["CHAMPIONS: NONE YET"])
        m = self.machine()
        m.record(RETIRE, "retirement pass")
        self.season(m)
        m.call(self.champ["champions_advance"])
        base = m.team_ptr(95 % 32) + 0xE4
        m.uc.mem_write(base + 3, bytes([m.uc.mem_read(base + 3, 1)[0] ^ 1]))       # break the check
        _calls, text = self.draw_card(m, 2)
        self.assertEqual([t[0] for t in text], ["CHAMPIONS: NONE YET"])

    def test_pages_one_and_two_are_unchanged_by_the_third(self):
        m = self.machine()
        m.wire(None)
        calls, text = self.draw_card(m, 0)
        self.assertEqual((calls, text), (["header", "ratings", "bio", "photo", "model"], []))
        calls, text = self.draw_card(m, 1)
        self.assertEqual(calls, ["header", "photo", "model"])
        self.assertEqual([t[0] for t in text[1:20:2]], ["0"] * 10)             # the honors page, as in beta 77

    # --- the award voting -------------------------------------------------------------------------------------
    def league(self, m, specs, records):
        """specs: (name, pos, team, years pro, stat dict); returns the records in iteration order."""
        field = {"pass_yds": 8, "pass_td": 9, "pass_int": 10, "rush_yds": 2, "rush_td": 3, "rec": 12, "rec_yds": 13,
                 "rec_td": 14, "tackles": 18, "sacks2": 19, "def_int": 20, "ff": 21}
        rows = [(yrs, [word(field[k], yrs, v) for k, v in stats.items()]) for _n, _p, _t, yrs, stats in specs]
        recs = m.roster(rows)
        teams = {}
        for rec, (name, pos, team, yrs, stats) in zip(recs, specs):
            m.person(rec, name, "Player", pos)
            teams.setdefault(team, []).append(rec)
        for team, members in teams.items():
            m.club(team, f"City{team}", f"Nick{team}", f"A{team}", members, records[team])
        m.wire(recs)
        return recs

    def model_players(self, recs, specs):
        out = []
        for rec, (name, pos, team, yrs, stats) in zip(recs, specs):
            out.append({"name": name, "pos": POSITIONS.index(pos), "team": team, "yrs": yrs, **line(**stats), "ptr": rec})
        # the game visits clubs in index order, each club's players in roster order
        return sorted(out, key=lambda p: (p["team"], recs.index(p["ptr"])))

    def run_awards(self, m, specs, records):
        recs = self.league(m, specs, records)
        for off in range(0x5800, 0x5890, 4):
            m.put(AWARDS + off, 0)
        m.put(AWARDS + 0x5808, 0xC0AC4)                                      # the coach of the year is not touched
        m.put(CLASS, 1)
        m.record(AWARD_TAIL, "award tail")
        m.call(self.champ["champions_awards"])
        self.assertEqual(m.calls, ["award tail"])
        self.assertEqual(m.get(CLASS), 1)
        self.assertEqual(m.get(AWARDS + 0x5808), 0xC0AC4)
        got = {k: m.get(AWARDS + off) for k, off in (("mvp", 0x5800), ("opoy", 0x5810), ("dpoy", 0x5818),
                                                       ("oroy", 0x5820), ("droy", 0x5828))}
        teams = {k: m.get(AWARDS + off + 4) for k, off in (("mvp", 0x5800), ("opoy", 0x5810), ("dpoy", 0x5818),
                                                              ("oroy", 0x5820), ("droy", 0x5828))}
        players = self.model_players(recs, specs)
        want = champions.choose_awards(players, lambda t: records[t])
        for key in got:
            expected = want[key]
            self.assertEqual(got[key], expected["ptr"] if expected else 0, key)
            if expected:
                self.assertEqual(teams[key], m.team_ptr(expected["team"]), key)
        return got, recs, want

    SPECS = [
        ("QBA", "QB", 0, 6, dict(pass_yds=4600, pass_td=38, pass_int=9, rush_yds=300, rush_td=3)),
        ("RBA", "HB", 0, 4, dict(rush_yds=1900, rush_td=18, rec=60, rec_yds=500, rec_td=3)),
        ("WRA", "WR", 1, 5, dict(rec=120, rec_yds=1700, rec_td=14)),
        ("QBB", "QB", 1, 8, dict(pass_yds=4900, pass_td=41, pass_int=7)),
        ("LBA", "ILB", 0, 7, dict(tackles=170, sacks2=14, def_int=3, ff=4)),
        ("DEA", "DE", 2, 6, dict(sacks2=40, tackles=60, ff=4)),
        ("CBA", "CB", 3, 5, dict(def_int=9, tackles=70)),
        ("RQB", "QB", 2, 1, dict(pass_yds=3400, pass_td=22, pass_int=14)),
        ("RWR", "WR", 3, 1, dict(rec=80, rec_yds=1050, rec_td=7)),
        ("RDE", "DE", 3, 1, dict(sacks2=22, tackles=38)),
        ("KKA", "K", 0, 4, dict(pass_yds=9999)),
    ]
    RECORDS = {0: (14, 3, 0), 1: (12, 5, 0), 2: (6, 11, 0), 3: (9, 8, 0)}

    def test_the_native_vote_matches_the_model(self):
        m = self.machine()
        got, recs, want = self.run_awards(m, self.SPECS, self.RECORDS)
        names = {k: (v["name"] if v else None) for k, v in want.items()}
        self.assertEqual(names["mvp"], "QBA")
        self.assertEqual(names["oroy"], "RQB")
        self.assertEqual(names["droy"], "RDE")

    def test_otherworldly_seasons_win_mvp_natively(self):
        for label, spec in (("edge", ("WONDER", "DE", 2, 6, dict(sacks2=62, tackles=50))),
                            ("linebacker", ("WONDER", "ILB", 2, 6, dict(tackles=305))),
                            ("runner", ("WONDER", "HB", 2, 6, dict(rush_yds=2510, rush_td=19))),
                            ("receiver", ("WONDER", "WR", 2, 6, dict(rec=150, rec_yds=2210, rec_td=15)))):
            with self.subTest(label):
                m = self.machine()
                got, recs, want = self.run_awards(m, self.SPECS + [spec], self.RECORDS)
                self.assertEqual(got["mvp"], recs[-1])
                self.assertEqual(want["mvp"]["name"], "WONDER")
                self.assertNotEqual(got["opoy"], recs[-1])
                self.assertNotEqual(got["dpoy"], recs[-1])

    def test_a_league_without_candidates_keeps_the_retail_winners(self):
        m = self.machine()
        recs = m.roster([(5, [])])
        m.person(recs[0], "Nobody", "Home", "K")
        m.club(0, "A", "B", "C", recs, (8, 8, 0))
        m.wire(recs)
        for off in range(0x5800, 0x5890, 4):
            m.put(AWARDS + off, 0x1000 + off)
        m.record(AWARD_TAIL, "award tail")
        m.call(self.champ["champions_awards"])
        for off in (0x5800, 0x5804, 0x5810, 0x5818, 0x5820, 0x5828):
            self.assertEqual(m.get(AWARDS + off), 0x1000 + off)


if __name__ == "__main__":
    unittest.main()
