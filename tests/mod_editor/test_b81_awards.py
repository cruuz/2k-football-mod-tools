"""Job b81-awards: the season award vote and the 24-man All-Pro team.

EXPERIMENTAL / UNWITNESSED in game. Static checks run everywhere. The native classes map the retail USA ``default.xbe``
with the honors owner (which now installs ``nfl2k5_awards``) and run the real code under Unicorn:

* the vote (site 0x116E5A) on synthetic leagues, against the plain-data twin ``nfl2k5_awards.choose_awards`` and on the
  two seasons the owner reported (a 15-interception linebacker and a 15-interception corner named MVP over a 40-touchdown
  quarterback): failing first on c4406481b, where the champions owner's "otherworldly" rule gives both the MVP;
* the All-Pro team: 24 men in the AP shape, nine through the retail best-at-position slots, fifteen written here;
* beta 81 ships no defensive credit (design R1 found inert in simulated games; see nfl2k5_awards): the club merge
  FUN_00134DD0 stays retail.

Boundaries: team records come from substituted record routines (as in the champions tests); the overall (0x246D80)
is supplied per player. The full simulated seasons are the lane's
paired panel (REVIEW_ME.txt), not here.
"""
from __future__ import annotations

import collections
import re
import shutil
import struct
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_awards as awards  # noqa: E402
from mod_editor.core import nfl2k5_awards_code as runtime  # noqa: E402
from mod_editor.core import nfl2k5_champions as champions  # noqa: E402
from mod_editor.core import nfl2k5_honors as honors  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tests.mod_editor.test_b779_hn1_champions import LeagueMachine  # noqa: E402
from tests.mod_editor.test_nfl2k5_honors import AWARDS, CLASS, HAVE_UC, LEAGUE_MODE, _retail, word  # noqa: E402

POS = awards.P
FIELD = {"pass_yds": 8, "pass_td": 9, "pass_int": 10, "rush_yds": 2, "rush_td": 3, "rec": 12, "rec_yds": 13, "rec_td": 14,
         "tackles": 18, "sacks2": 19, "def_int": 20, "ff": 21, "qbh": 107, "games": 0, "fgm": 61, "fga": 62,
         "punts": 32, "punt_yds": 33}
STATS = ("pass_yds", "pass_td", "pass_int", "rush_yds", "rush_td", "rec", "rec_yds", "rec_td", "tackles", "sacks2",
         "def_int", "ff", "qbh")
SOURCE = ROOT / "tools/nfl2k5_awards/runtime.c"


def line(**kw):
    out = {k: 0 for k in STATS}
    out.update(kw)
    return out


def man(name, pos, team, yrs=5, mvp_ago=(), **stats):
    return {"name": name, "pos": POS[pos], "team": team, "yrs": yrs, "mvp_ago": list(mvp_ago), **line(**stats)}


class StaticTests(unittest.TestCase):
    def test_template_fits_its_page_and_links_only_to_itself(self):
        self.assertLessEqual(len(runtime.CODE), awards.CODE_SIZE)
        self.assertEqual(awards.REQUESTS, (("nfl2k5_awards", "code", 4096, 4096),))
        self.assertEqual((awards.CODE_VA, space.AWARDS_VA), (0x1531000, 0x1531000))
        for offset, kind, symbol, _value in runtime.RELOCATIONS:
            self.assertIn(kind, (1, 2))
            self.assertEqual(symbol, "code")
        for entry in ("awards_vote_entry", "awards_vote"):
            self.assertIn(entry, runtime.LABELS)
        self.assertFalse([name for name in runtime.LABELS if "credit" in name])   # no R1 code ships

    def test_sites_are_jumps_into_the_entries_over_the_retail_bytes(self):
        at = awards.labels()
        rows = {label: (va, before, after) for label, va, before, after in awards.sites()}
        self.assertEqual(list(rows), ["vote"])          # beta 81: the vote only
        self.assertEqual(rows["vote"][:2], (0x116E5A, bytes.fromhex("5e5d83c41c")))
        for label, entry in (("vote", "awards_vote_entry"),):
            va, before, after = rows[label]
            self.assertEqual((after[0], len(after)), (0xE9, len(before)))
            self.assertEqual(va + 5 + struct.unpack_from("<i", after, 1)[0], at[entry])
            self.assertEqual(after[5:], b"\x90" * (len(before) - 5))

    def test_the_fixed_page_is_placed_and_stepped_over(self):
        rows = space._scale_allocations([space.AWARDS_REQUEST])
        mine = [r for r in rows if r["owner"] == "nfl2k5_awards"]
        self.assertEqual([(r["va"], r["size"]) for r in mine], [(0x1531000, 4096)])
        self.assertIn("nfl2k5_awards", space.LATE_OWNERS)
        self.assertIn("nfl2k5_awards", space.FIXED_PAGE_OWNERS)
        self.assertEqual(space._awards_at("nfl2k5_other", space.AWARDS_VA - space.POOL_VA - 16, 64, 16),
                         space.AWARDS_VA - space.POOL_VA + 4096)
        self.assertFalse(set(awards.REQUESTS) & set(honors.REQUESTS))      # appended by awards.install, not in the set

    def test_a_build_accepts_an_installed_set_holding_the_appended_page_and_nothing_else(self):
        # the build path re-checks an installed image against its own requests (honors.REQUESTS has no awards page)
        wanted = space._requests(honors.REQUESTS)
        with_page = space._requests(list(honors.REQUESTS) + [space.AWARDS_REQUEST])
        self.assertTrue(space._same_installed_requests(wanted, wanted))
        self.assertTrue(space._same_installed_requests(wanted, with_page))
        self.assertFalse(space._same_installed_requests(with_page, wanted))       # asked for but not installed
        other = space._requests(list(honors.REQUESTS) + [("nfl2k5_other", "code", 4096, 16)])
        self.assertFalse(space._same_installed_requests(wanted, other))
        both = space._requests(list(honors.REQUESTS) + [space.AWARDS_REQUEST, ("nfl2k5_other", "code", 4096, 16)])
        self.assertFalse(space._same_installed_requests(wanted, both))

    def test_the_twin_uses_the_native_tables(self):
        text = SOURCE.read_text(encoding="utf-8")

        def table(name, n):
            found = re.search(r"static const u(?:8|16) %s\[[A-Z_0-9]+\] = \{([^}]*)\};" % name, text)
            self.assertIsNotNone(found, name)
            values = tuple(int(x) for x in found.group(1).split(","))
            self.assertEqual(len(values), n, name)
            return values

        self.assertEqual(table("opoy_ref", 17), tuple(awards.OPOY_REF.get(i, 0) for i in range(17)))
        self.assertEqual(table("oroy_ref", 17), tuple(awards.OROY_REF.get(i, 0) for i in range(17)))
        self.assertEqual(table("role_weight", 17), tuple(awards.ROLE_WEIGHT.get(i, 0) for i in range(17)))
        self.assertEqual(table("ap_size", 15), tuple(n for _c, n in awards.ALL_PRO))
        self.assertEqual(awards.ALL_PRO_SIZE, 24)

    @unittest.skipUnless(shutil.which("gcc") and shutil.which("ld"), "GNU gcc/binutils needed to rebuild the template")
    def test_the_template_rebuilds_from_the_source(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools/nfl2k5_awards_build.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TwinTests(unittest.TestCase):
    """The rule on plain data."""

    RECORDS = {0: (13, 4, 0), 1: (11, 6, 0), 2: (9, 8, 0), 3: (12, 5, 0)}

    def vote(self, players, records=None):
        records = records or self.RECORDS
        return awards.choose_awards(players, lambda t: records[t])

    def test_the_reported_2029_season_gives_the_quarterback_the_mvp(self):
        daniels = man("Daniels", "QB", 0, pass_yds=4300, pass_td=40, pass_int=10, rush_yds=1000, rush_td=6)
        reese = man("Reese", "ILB", 1, tackles=104, sacks2=9, def_int=15, ff=2, qbh=10)
        edge = man("Edge", "DE", 2, tackles=60, sacks2=36, ff=3, qbh=38)
        got = self.vote([daniels, reese, edge])
        self.assertIs(got["mvp"], daniels)
        self.assertIs(got["dpoy"], reese)              # "thats DPOY numbers"
        # the shipped champions vote names the linebacker MVP
        old = champions.choose_awards([{**p, "pos": p["pos"]} for p in (daniels, reese, edge)],
                                      lambda t: self.RECORDS[t])
        self.assertEqual(old["mvp"]["name"], "Reese")

    def test_the_owners_line_a_great_quarterback_on_a_500_club_keeps_the_mvp(self):
        # review S6: "not when a qb plays like that ... plus team success"; 4,300 yds, 40 TD, 1,000 rushing (44,800 offence
        # points) on 10-7 against a 15-INT linebacker on 13-4
        daniels = man("Daniels", "QB", 0, pass_yds=4300, pass_td=40, pass_int=10, rush_yds=1000, rush_td=6)
        reese = man("Reese", "ILB", 1, tackles=104, sacks2=9, def_int=15, ff=2, qbh=10)
        self.assertGreaterEqual(awards.mvp_base(daniels), awards.MVP_CALIBRE)
        self.assertIs(self.vote([daniels, reese], {0: (10, 7, 0), 1: (13, 4, 0)})["mvp"], daniels)
        self.assertIs(self.vote([daniels, reese], {0: (8, 8, 1), 1: (13, 4, 0)})["mvp"], daniels)     # .500 exactly
        self.assertIs(self.vote([daniels, reese], {0: (7, 10, 0), 1: (13, 4, 0)})["mvp"], reese)     # a losing club
        # the threshold: just under it the team factor decides as before
        under = man("Under", "QB", 0, pass_yds=4000, pass_td=35, pass_int=10, rush_yds=500, rush_td=2)
        self.assertLess(awards.mvp_base(under), awards.MVP_CALIBRE)
        self.assertIs(self.vote([under, reese], {0: (10, 7, 0), 1: (13, 4, 0)})["mvp"], reese)

    def test_a_record_breaking_defender_still_wins_in_a_year_without_a_standout_quarterback(self):
        qb = man("Average", "QB", 1, pass_yds=3900, pass_td=24, pass_int=12, rush_yds=200, rush_td=1)
        corner = man("Ballhawk", "CB", 0, tackles=70, def_int=15, ff=2)
        self.assertIs(self.vote([qb, corner])["mvp"], corner)
        corner12 = man("Ballhawk", "CB", 0, tackles=70, def_int=12, ff=2)
        self.assertIs(self.vote([qb, corner12])["mvp"], qb)
        good = man("Good", "QB", 3, pass_yds=4500, pass_td=32, pass_int=11, rush_yds=400, rush_td=3)
        self.assertIs(self.vote([good, corner])["mvp"], good)

    def test_a_historic_back_can_win_and_an_ordinary_one_cannot(self):
        qb = man("QB", "QB", 3, pass_yds=4400, pass_td=33, pass_int=9, rush_yds=250, rush_td=2)
        back = man("Back", "HB", 0, rush_yds=2100, rush_td=19, rec=40, rec_yds=350, rec_td=2)
        self.assertIs(self.vote([qb, back])["mvp"], back)
        back["rush_yds"] = 1900
        self.assertIs(self.vote([qb, back])["mvp"], qb)

    def test_fatigue_hands_a_close_race_to_the_other_quarterback(self):
        a = man("A", "QB", 0, mvp_ago=[1], pass_yds=4600, pass_td=36, pass_int=9, rush_yds=300, rush_td=2)
        b = man("B", "QB", 3, pass_yds=4400, pass_td=34, pass_int=9, rush_yds=300, rush_td=2)
        self.assertIs(self.vote([a, b], {0: (13, 4, 0), 3: (13, 4, 0)})["mvp"], b)
        a["mvp_ago"] = []
        self.assertIs(self.vote([a, b], {0: (13, 4, 0), 3: (13, 4, 0)})["mvp"], a)
        self.assertEqual([awards.fatigue(x) for x in ([], [1], [0, 1], [1, 1, 1, 1, 1])], [100, 85, 92, 70])

    def test_pass_rushers_beat_a_tackle_pile(self):
        lb = man("LB", "ILB", 0, tackles=150, sacks2=12, def_int=3, ff=2, qbh=14)
        de = man("DE", "DE", 1, tackles=60, sacks2=36, ff=3, qbh=40)
        self.assertIs(self.vote([lb, de])["dpoy"], de)

    def test_all_pro_has_the_ap_shape(self):
        players, i = [], 0
        for pos, n in (("QB", 2), ("HB", 2), ("FB", 2), ("WR", 4), ("TE", 2), ("T", 3), ("G", 3), ("C", 2), ("DE", 3),
                       ("DT", 3), ("ILB", 3), ("CB", 3), ("SS", 2), ("FS", 2), ("K", 2), ("P", 2)):
            for k in range(n):
                i += 1
                players.append({**man(f"{pos}{k}", pos, k % 4, rush_yds=100 + i, rec_yds=100 + i, pass_yds=1000 + i,
                                     tackles=50 + i, sacks2=i), "games": 17, "overall": 0.5 + i / 1000, "fga": 30,
                                "fgm": 20 + k, "punts": 60, "punt_yds": 2700 + i})
        ap = awards.all_pro(players, lambda t: self.RECORDS[t])
        self.assertEqual({c: len(v) for c, v in ap.items()}, dict(awards.ALL_PRO))
        self.assertEqual(sum(len(v) for v in ap.values()), 24)


@unittest.skipUnless(HAVE_UC, "unicorn required")
class NativeVoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = _retail()
        if retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.patched, _ = honors.apply(retail)
        cls.at = awards.labels()

    def machine(self):
        m = LeagueMachine(self.patched)
        m.reserve_block()
        self.overall = {}
        self._float_hook(m, 0x246D80, lambda m: self.overall.get(m.reg("ECX"), 0.0), pop=0)
        return m

    @staticmethod
    def _float_hook(m, va, fn, pop):
        """Replace a float-returning routine: the value goes to a scratch word and a stub loads it (fld) and returns."""
        scratch, stub = m.STOP + 0x100, m.STOP + 0x200 + 0x20 * pop
        m.uc.mem_write(stub, bytes.fromhex("d905") + struct.pack("<I", scratch) + (b"\xc2" + struct.pack("<H", pop) if pop
                                                                                    else b"\xc3"))

        def hook(uc, address, _size, _data):
            if address == va:
                uc.mem_write(scratch, struct.pack("<f", fn(m)))
                uc.reg_write(m.x.UC_X86_REG_EIP, stub)
        m.uc.hook_add(m.u.UC_HOOK_CODE, hook, begin=va, end=va)

    def league(self, m, specs, records):
        """specs: (name, pos, team, years pro, stats, mvp seasons ago); returns the records in the game's order."""
        rows = []
        for _n, _p, _t, yrs, stats, ago in specs:
            words = [word(FIELD[k], yrs, v) for k, v in stats.items() if k in FIELD]
            words += [word(96, yrs - n, 1) for n in ago if yrs - n >= 0]
            rows.append((yrs, words))
        recs = m.roster(rows)
        teams = {}
        for rec, (name, pos, team, *_rest) in zip(recs, specs):
            m.person(rec, name, "Player", pos)
            teams.setdefault(team, []).append(rec)
        for team, members in teams.items():
            m.club(team, f"City{team}", f"Nick{team}", f"A{team}", members, records[team])
        m.wire(recs)
        return recs

    def twin_players(self, recs, specs):
        out = []
        for rec, (name, pos, team, yrs, stats, ago) in zip(recs, specs):
            mvp_ago = [1 if n in ago else 0 for n in range(1, 6)]
            out.append({**man(name, pos, team, yrs, mvp_ago, **{k: v for k, v in stats.items() if k in STATS}),
                        "ptr": rec, "overall": self.overall.get(rec, 0.0),
                        **{k: stats.get(k, 0) for k in ("games", "fgm", "fga", "punts", "punt_yds")}})
        return sorted(out, key=lambda p: (p["team"], recs.index(p["ptr"])))

    def run_vote(self, m, specs, records, mode=2):
        recs = self.league(m, specs, records)
        m.put(LEAGUE_MODE, mode)
        for off in range(0x5800, 0x5890, 4):
            m.put(AWARDS + off, 0)
        m.put(AWARDS + 0x5878, 0xDEAD)
        m.put(CLASS, 1)
        m.call(self.at["awards_vote"])
        self.assertEqual(m.get(CLASS), 1)
        return recs

    def slot(self, m, off):
        return m.get(AWARDS + off)

    SPECS = [
        ("QBA", "QB", 0, 6, dict(pass_yds=4600, pass_td=38, pass_int=9, rush_yds=300, rush_td=3), ()),
        ("RBA", "HB", 0, 4, dict(rush_yds=1900, rush_td=18, rec=60, rec_yds=500, rec_td=3), ()),
        ("WRA", "WR", 1, 5, dict(rec=120, rec_yds=1700, rec_td=14), ()),
        ("QBB", "QB", 1, 8, dict(pass_yds=4900, pass_td=41, pass_int=7), (1,)),
        ("LBA", "ILB", 0, 7, dict(tackles=170, sacks2=14, def_int=3, ff=4, qbh=12), ()),
        ("DEA", "DE", 2, 6, dict(sacks2=40, tackles=60, ff=4, qbh=40), ()),
        ("CBA", "CB", 3, 5, dict(def_int=9, tackles=70), ()),
        ("RQB", "QB", 2, 1, dict(pass_yds=3400, pass_td=22, pass_int=14), ()),
        ("RWR", "WR", 3, 1, dict(rec=80, rec_yds=1050, rec_td=7), ()),
        ("RDE", "DE", 3, 1, dict(sacks2=22, tackles=38, qbh=20), ()),
        ("TEA", "TE", 1, 4, dict(rec=90, rec_yds=1100, rec_td=9), ()),
        ("KKA", "K", 0, 4, dict(pass_yds=9999), ()),
    ]
    RECORDS = {0: (14, 3, 0), 1: (12, 5, 0), 2: (6, 11, 0), 3: (9, 8, 0)}

    def test_the_native_vote_matches_the_twin(self):
        m = self.machine()
        recs = self.run_vote(m, self.SPECS, self.RECORDS)
        want = awards.choose_awards(self.twin_players(recs, self.SPECS), lambda t: self.RECORDS.get(t, (0, 0, 0)),
                                    clubs=list(range(32)))
        for key, off in (("mvp", 0x5800), ("opoy", 0x5810), ("dpoy", 0x5818), ("oroy", 0x5820), ("droy", 0x5828)):
            expected = want[key]
            self.assertEqual(self.slot(m, off), expected["ptr"] if expected else 0, key)
            if expected:
                self.assertEqual(self.slot(m, off + 4), m.team_ptr(expected["team"]), key)
        # RBA's 2,400 scrimmage yards and 21 touchdowns pass the historic gate, but QBA's 36,600 offence points on a
        # 14-3 club are an MVP-calibre season (review S6), so the exception cannot take it; QBB won last year (fatigue)
        self.assertEqual(want["mvp"]["name"], "QBA")

    def test_the_reported_seasons_go_to_the_quarterback(self):
        cases = (
            ("2029", [("Daniels", "QB", 0, 6, dict(pass_yds=4300, pass_td=40, pass_int=10, rush_yds=1000, rush_td=6), ()),
                      ("Reese", "ILB", 1, 4, dict(tackles=104, sacks2=9, def_int=15, ff=2, qbh=10), ())],
             {0: (13, 4, 0), 1: (11, 6, 0)}),
            ("2027", [("Good", "QB", 0, 6, dict(pass_yds=4500, pass_td=32, pass_int=11, rush_yds=400, rush_td=3), ()),
                      ("Emmanwori", "CB", 1, 3, dict(tackles=80, def_int=15, ff=2), ())],
             {0: (12, 5, 0), 1: (12, 5, 0)}),
            # review S6: the 40-TD, 1,000-rushing-yard quarterback on a 10-7 club against the 15-INT linebacker on 13-4
            ("S6", [("Daniels", "QB", 0, 6, dict(pass_yds=4300, pass_td=40, pass_int=10, rush_yds=1000, rush_td=6), ()),
                    ("Reese", "ILB", 1, 4, dict(tackles=104, sacks2=9, def_int=15, ff=2, qbh=10), ())],
             {0: (10, 7, 0), 1: (13, 4, 0)}),
        )
        for label, specs, records in cases:
            with self.subTest(label):
                m = self.machine()
                recs = self.run_vote(m, specs, records)
                self.assertEqual(self.slot(m, 0x5800), recs[0])
                self.assertEqual(self.slot(m, 0x5818), recs[1])          # the defender is the DPOY

    def test_the_exception_still_wins_without_a_great_quarterback_on_a_500_club(self):
        cases = (
            # a 15-INT corner on 13-4 against a 3,900-yard, 24-TD quarterback (25,400 offence points) on 11-6
            ("ordinary QB", [("Average", "QB", 0, 6, dict(pass_yds=3900, pass_td=24, pass_int=12, rush_yds=200, rush_td=1), ()),
                             ("Ballhawk", "CB", 1, 3, dict(tackles=70, def_int=15, ff=2), ())],
             {0: (11, 6, 0), 1: (13, 4, 0)}, 1),
            # the reviewer's 40-TD quarterback, but on a 7-10 club: no longer protected, the linebacker on 13-4 wins
            ("losing club", [("Daniels", "QB", 0, 6, dict(pass_yds=4300, pass_td=40, pass_int=10, rush_yds=1000, rush_td=6), ()),
                             ("Reese", "ILB", 1, 4, dict(tackles=104, sacks2=9, def_int=15, ff=2, qbh=10), ())],
             {0: (7, 10, 0), 1: (13, 4, 0)}, 1),
        )
        for label, specs, records, winner in cases:
            with self.subTest(label):
                m = self.machine()
                recs = self.run_vote(m, specs, records)
                self.assertEqual(self.slot(m, 0x5800), recs[winner])
                want = awards.choose_awards(self.twin_players(recs, specs), lambda t: records.get(t, (0, 0, 0)),
                                            clubs=list(range(32)))
                self.assertEqual(want["mvp"]["name"], specs[winner][0])

    def test_all_pro_writes_twenty_four_in_the_ap_shape(self):
        m = self.machine()
        specs = []
        for team in range(4):
            for pos, n in (("QB", 1), ("HB", 1), ("FB", 1), ("WR", 3), ("TE", 1), ("T", 2), ("G", 2), ("C", 1),
                           ("DE", 2), ("DT", 2), ("ILB", 2), ("CB", 2), ("SS", 1), ("FS", 1), ("K", 1), ("P", 1)):
                for k in range(n):
                    v = 10 * team + k + 1
                    specs.append((f"{pos}{team}{k}", pos, team, 5, dict(
                        games=17, pass_yds=3000 + v, rush_yds=500 + v, rec=40 + v, rec_yds=600 + v, tackles=40 + v,
                        sacks2=v, def_int=v % 5, qbh=v, fgm=20 + v, fga=30 + v, punts=60, punt_yds=2600 + v), ()))
        recs = self.league(m, specs, self.RECORDS)
        for i, rec in enumerate(recs):
            self.overall[rec] = 0.6 + i / 1000
        m.put(LEAGUE_MODE, 2)
        for off in range(0x5800, 0x5890, 4):
            m.put(AWARDS + off, 0)
        m.put(AWARDS + 0x5878, 0xDEAD)
        m.call(self.at["awards_vote"])
        honored = {rec for rec in recs if any((w >> 16) & 127 == 104 for w in m.stream(rec))}
        slots = {self.slot(m, 0x5830 + 8 * i) for i in range(9)}
        self.assertEqual(len(slots - {0}), 9)
        self.assertEqual((self.slot(m, 0x5878), self.slot(m, 0x587C)), (0, 0))
        self.assertEqual(len(honored), 15)
        self.assertFalse(honored & slots)
        by_pos = collections.Counter(specs[recs.index(r)][1] for r in honored | slots)
        self.assertEqual(by_pos, {"QB": 1, "HB": 1, "FB": 1, "WR": 3, "TE": 1, "T": 2, "G": 2, "C": 1, "DE": 2,
                                  "DT": 2, "ILB": 2, "CB": 2, "SS": 1, "FS": 1, "K": 1, "P": 1})
        twin = awards.all_pro(self.twin_players(recs, specs), lambda t: self.RECORDS[t])
        want = {p["ptr"] for picks in twin.values() for p in picks}
        self.assertEqual(honored | slots, want)

    def test_outside_a_franchise_no_honor_is_written(self):
        m = self.machine()
        recs = self.run_vote(m, self.SPECS, self.RECORDS, mode=1)
        self.assertTrue(self.slot(m, 0x5800))                       # the season object still gets the vote
        self.assertFalse(any((w >> 16) & 127 == 104 for rec in recs for w in m.stream(rec)))


@unittest.skipUnless(HAVE_UC, "unicorn required")
class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        cls.patched, cls.receipt = honors.apply(cls.retail)

    def test_honors_installs_the_vote_and_both_read_applied(self):
        self.assertEqual(awards.status(self.retail), "retail")
        self.assertEqual((honors.status(self.patched), awards.status(self.patched)), ("applied", "applied"))
        self.assertTrue(honors.read_settings(self.patched)["awards_vote"])
        self.assertEqual(self.receipt["awards"]["code_va"], hex(0x1531000))
        again, receipt = honors.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt["already_applied"])

    def test_an_install_without_the_vote_reads_previous_and_is_upgraded_in_place(self):
        from unittest import mock
        # the honors install as it was before this owner: its own requests and the champions owner, no award vote
        with mock.patch.object(honors, "REQUESTS", honors.HONORS_REQUESTS + champions.REQUESTS), \
                mock.patch.object(awards, "install", lambda payload: (payload, {})), \
                mock.patch.object(honors, "status", lambda payload: "applied"):
            older, _ = honors.apply(self.retail)
        self.assertEqual(awards.status(older), "retail")
        self.assertEqual(honors.status(older), "previous")
        self.assertEqual(honors.read_settings(older)["revision"], "beta-81 without the award vote")
        upgraded, receipt = honors.apply(older)
        self.assertEqual((honors.status(upgraded), awards.status(upgraded)), ("applied", "applied"))
        self.assertEqual(receipt["upgraded_from"], "beta-81")
        code = honors.allocations(older)["code"]
        self.assertEqual(XbeImage(upgraded).read(code["va"], code["size"]), XbeImage(older).read(code["va"], code["size"]))
        self.assertEqual(honors.apply(upgraded)[0], upgraded)

    def test_the_club_merge_stays_retail(self):
        # beta 81 ships the vote only: FUN_00134DD0 (design R1's site 0x134DF1) is not touched by this owner
        self.assertEqual(XbeImage(self.patched).read(0x134DF1, 8), bytes.fromhex("8bd88a871c010000"))
        self.assertEqual(XbeImage(self.patched).read(0x134DD0, 0x35), XbeImage(self.retail).read(0x134DD0, 0x35))

    def test_a_single_foreign_site_is_refused(self):
        for label, va, before, after in awards.sites():
            with self.subTest(site=label):
                buf = bytearray(self.patched)
                off = va - 0x10000
                buf[off] ^= 0xFF
                self.assertEqual(awards.status(bytes(buf)), "foreign")
                self.assertEqual(honors.status(bytes(buf)), "foreign")

    def test_the_vote_alone_on_retail_leaves_honors_retail_only_when_both_agree(self):
        alone, _ = awards.install(self.retail)
        self.assertEqual(awards.status(alone), "applied")
        self.assertEqual(honors.status(alone), "foreign")            # mixed: the vote without the honors owner
        self.assertEqual(rdata.status(alone, awards.sites()), "applied")


V09_SHA256 = "d78088f9ba47c6197e99ea540d0bc3d2c9255f7cd49152a77946be70dacab866"   # the released v0.9 default.xbe


def _v09() -> bytes:
    import hashlib
    import os
    path = os.environ.get("NFL2K5_V09_RELEASED_XBE")
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("NFL2K5_V09_RELEASED_XBE (the released v0.9 default.xbe) is not set")
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != V09_SHA256:
        raise unittest.SkipTest("NFL2K5_V09_RELEASED_XBE does not match the v0.9 release pin")
    return data


class ReleaseV09UpdateTests(unittest.TestCase):
    """Review M1: the Studio's v0.9 update brings the released disc's honors owner (beta-80, with the champions rule that
    named 15-interception linebackers MVP) to this release's, award vote included, on the real v0.9 executable."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import mod_build
        cls.build = mod_build
        cls.v09 = _v09()
        cls.upgraded, cls.receipt = mod_build._season_awards_upgrade(cls.v09)

    def test_the_release_reads_previous_and_the_update_makes_it_current(self):
        self.assertEqual((honors.status(self.v09), champions.status(self.v09), awards.status(self.v09)),
                         ("previous", "previous", "retail"))
        self.assertEqual((honors.status(self.upgraded), champions.status(self.upgraded), awards.status(self.upgraded)),
                         ("applied", "applied", "applied"))
        self.assertEqual(self.receipt["upgraded_from"], "beta-80")
        self.assertEqual(self.build._season_awards_upgrade(self.upgraded), (self.upgraded, None))   # once
        self.assertEqual(self.build._season_awards_upgrade(_retail()), (_retail(), None))           # never adds honors

    def test_no_allocation_moves_and_the_page_is_the_only_growth(self):
        from mod_editor.core import nfl2k5_memory_budget as budget
        before = [r for r in space.layout(self.v09)["allocations"] if r["owner"] != space.DIRECTORY_OWNER]
        after = space.layout(self.upgraded)["allocations"]
        self.assertEqual([r for r in after if r["owner"] not in (awards.OWNER, space.DIRECTORY_OWNER)], before)
        self.assertEqual([(r["owner"], r["va"]) for r in after if r["owner"] == awards.OWNER],
                         [(awards.OWNER, space.AWARDS_VA)])
        self.assertEqual(len(self.upgraded) - len(self.v09), budget.V09_UPDATE_GROWTH)
        # the memory model charges the updated pack at least the measured growth (the anchor plan stays as measured)
        self.assertIn("awards", budget.owners(budget.v09_update_plan(), 128))
        self.assertNotIn("awards", budget.owners(budget.rc_plan(), 128))
        self.assertGreaterEqual(budget.xbe_resident(budget.v09_update_plan(), 128) - budget.xbe_resident(budget.rc_plan(), 128),
                                budget.V09_UPDATE_GROWTH)

    def test_the_history_pool_step_gives_the_same_bytes_in_either_order(self):
        first = self.build._history_pool_upgrade(self.upgraded)[0]
        second = self.build._season_awards_upgrade(self.build._history_pool_upgrade(self.v09)[0])[0]
        self.assertEqual(first, second)
        self.assertEqual(awards.status(first), "applied")

    def test_every_other_owner_reads_the_same(self):
        import importlib
        names = [o for o in space.LATE_OWNERS if o not in (honors.OWNER, champions.OWNER, awards.OWNER)]
        names += ["nfl2k5_defensive_try", "nfl2k5_history_pool", "nfl2k5_history", "nfl2k5_franchise_economy"]
        checked = 0
        for name in dict.fromkeys(names):
            try:
                module = importlib.import_module("mod_editor.core." + name)
            except ImportError:
                continue
            if not callable(getattr(module, "status", None)):
                continue
            with self.subTest(owner=name):
                self.assertEqual(module.status(self.upgraded), module.status(self.v09))
                checked += 1
        self.assertGreater(checked, 30)

    def test_the_route_writes_it_before_the_gadget_and_history_pool_steps(self):
        import inspect
        source = inspect.getsource(inspect.unwrap(self.build._update_v09_disc))
        self.assertLess(source.index("_season_awards_upgrade(expected)"), source.index("expected, _ = gadget.apply(expected"))
        self.assertLess(source.index("_season_awards_upgrade(expected)"), source.index("_history_pool_upgrade(expected)"))
        self.assertIn('receipt["v09_update"].append("season_awards")', source)
        self.assertLess(source.index("_apply_season_awards_in_place(target"), source.index("_apply_gadget_play(plan, target"))
        self.assertLess(source.index("_apply_season_awards_in_place(target"), source.index("_apply_history_pool_in_place(target"))
        # the in-place write on a copy of the executable reads back and is recorded
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "default.xbe"
            target.write_bytes(self.v09)
            receipt = {"steps": [], "result": {}}
            self.build._apply_season_awards_in_place(target, receipt, lambda *_: None)
            self.assertEqual(target.read_bytes(), self.upgraded)
            self.assertEqual(receipt["result"]["season_awards"], "applied")
            self.assertEqual([s["step"] for s in receipt["steps"]], ["season_awards"])


if __name__ == "__main__":
    unittest.main()
