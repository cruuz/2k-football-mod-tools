"""Job b81-awards: the season award vote, the 24-man All-Pro team and the defensive credit in simulated games.

EXPERIMENTAL / UNWITNESSED in game. Static checks run everywhere. The native classes map the retail USA ``default.xbe``
with the honors owner (which now installs ``nfl2k5_awards``) and run the real code under Unicorn:

* the vote (site 0x116E5A) on synthetic leagues, against the plain-data twin ``nfl2k5_awards.choose_awards`` and on the
  two seasons the owner reported (a 15-interception linebacker and a 15-interception corner named MVP over a 40-touchdown
  quarterback): failing first on c4406481b, where the champions owner's "otherworldly" rule gives both the MVP;
* the All-Pro team: 24 men in the AP shape, nine through the retail best-at-position slots, fifteen written here;
* the credit (site 0x134DF1): totals per club kept, only defenders who played credited, whole sacks to one man, the
  gates (Franchise, simulated game, regular season or playoffs), determinism, and the position shares over many games.

Boundaries: team records come from substituted record routines (as in the champions tests); the derived ratings the
credit reads (0x246A80) and the overall (0x246D80) are supplied per player. The full simulated seasons are the lane's
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
from tests.mod_editor.test_nfl2k5_honors import AWARDS, CLASS, HAVE_UC, LEAGUE_MODE, Machine, _retail, word  # noqa: E402

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
        for entry in ("awards_vote_entry", "awards_credit_entry", "awards_vote", "awards_credit"):
            self.assertIn(entry, runtime.LABELS)

    def test_sites_are_jumps_into_the_entries_over_the_retail_bytes(self):
        at = awards.labels()
        rows = {label: (va, before, after) for label, va, before, after in awards.sites()}
        self.assertEqual(rows["vote"][:2], (0x116E5A, bytes.fromhex("5e5d83c41c")))
        self.assertEqual(rows["credit"][:2], (0x134DF1, bytes.fromhex("8bd88a871c010000")))
        for label, entry in (("vote", "awards_vote_entry"), ("credit", "awards_credit_entry")):
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
        self.assertEqual(table("power", 3), tuple(awards.CREDIT_POWER[k] for k in ("interceptions", "sacks", "tackles")))
        self.assertEqual(table("category", 3), tuple(awards.CREDIT_CATEGORY[k] for k in ("interceptions", "sacks", "tackles")))
        shares = re.search(r"static const u16 share\[4\]\[R_N\] = \{(.*?)\};", text, re.S).group(1)
        rows = [tuple(int(x) for x in row.split(",")) for row in re.findall(r"\{([^}]*)\}", shares)]
        self.assertEqual(rows, [awards.CREDIT_SHARES[k] for k in ("interceptions", "sacks", "tackles_with_cb", "tackles")])
        for row in rows:
            self.assertEqual(sum(row), 1000)
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
        # RBA's 2,400 scrimmage yards and 21 touchdowns pass the historic gate and beat QBA; QBB won last year (fatigue)
        self.assertEqual(want["mvp"]["name"], "RBA")

    def test_the_reported_seasons_go_to_the_quarterback(self):
        cases = (
            ("2029", [("Daniels", "QB", 0, 6, dict(pass_yds=4300, pass_td=40, pass_int=10, rush_yds=1000, rush_td=6), ()),
                      ("Reese", "ILB", 1, 4, dict(tackles=104, sacks2=9, def_int=15, ff=2, qbh=10), ())],
             {0: (13, 4, 0), 1: (11, 6, 0)}),
            ("2027", [("Good", "QB", 0, 6, dict(pass_yds=4500, pass_td=32, pass_int=11, rush_yds=400, rush_td=3), ()),
                      ("Emmanwori", "CB", 1, 3, dict(tackles=80, def_int=15, ff=2), ())],
             {0: (12, 5, 0), 1: (12, 5, 0)}),
        )
        for label, specs, records in cases:
            with self.subTest(label):
                m = self.machine()
                recs = self.run_vote(m, specs, records)
                self.assertEqual(self.slot(m, 0x5800), recs[0])
                self.assertEqual(self.slot(m, 0x5818), recs[1])          # the defender is the DPOY

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
class NativeCreditTests(unittest.TestCase):
    """FUN_00134DD0's club: live records at the side-0 array 0xB30C4C (0x54 each, count byte 0xB30980), each with a
    holder at +0x30 pointing to the stats object: +0 played, +0x1C/+0x20 interceptions, +0x24/+0x28 half sacks,
    +0x2C/+0x30 tackles (float flag, pointer to a record whose byte +4 is the count)."""

    LIVE0, COUNT0 = 0xB30C4C, 0xB30980
    GAME_MODE, STAGE, WEEK = 0xE5FF80, 0xE576A4, 0xE576B4

    @classmethod
    def setUpClass(cls):
        retail = _retail()
        if retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.patched, _ = honors.apply(retail)
        cls.at = awards.labels()

    def setUp(self):
        self.m = Machine(self.patched)
        self.ratings = {}
        NativeVoteTests._float_hook(self.m, 0x246A80, self._rating, pop=4)

    def _rating(self, m):
        cat = m.get(m.reg("ESP") + 4)
        return self.ratings.get((m.reg("ECX"), cat), 0.7)

    def club(self, men, stage=8, mode=4, league=2, week=3):
        """men: (pos, played, ints, half sacks, tackles, (v9, v4, v11)). Returns (club, [(player, int, sack, tkl)])."""
        m = self.m
        heap = m.HEAP
        club = heap + 0x100
        out = []
        for i, (pos, played, ints, sacks, tackles, ratings) in enumerate(men):
            player = heap + 0x1000 + i * 0x54
            m.uc.mem_write(player, bytes(0x54))
            m.put8(player + 0x35, POS[pos])
            m.put(club + 4 * i, player)
            live = self.LIVE0 + i * 0x54
            m.uc.mem_write(live, bytes(0x54))
            holder, stats = heap + 0x8000 + i * 16, heap + 0x9000 + i * 0x40
            m.put(live + 0x30, holder)
            m.put(holder, stats)
            m.uc.mem_write(stats, bytes(0x40))
            m.put(stats, 1 if played else 0)
            counters = []
            for flag, ptr, value in ((0x1C, 0x20, ints), (0x24, 0x28, sacks), (0x2C, 0x30, tackles)):
                rec = heap + 0xA000 + i * 0x40 + flag
                m.uc.mem_write(rec, bytes(8))
                m.put8(rec + 4, value)
                m.uc.mem_write(stats + flag, struct.pack("<f", 1.0))
                m.put(stats + ptr, rec)
                counters.append(rec + 4)
            for cat, value in zip((9, 4, 11), ratings):
                self.ratings[(player, cat)] = value
            out.append((player, counters))
        m.put8(self.COUNT0, len(men))
        m.put8(0xB30B74, 0)
        team = heap + 0x4000
        m.put8(team + 0x11C, len(men))
        m.put(LEAGUE_MODE, league)
        m.put(self.GAME_MODE, mode)
        m.put(self.STAGE, stage)
        m.put(self.WEEK, week)
        return club, team, out

    def counts(self, rows):
        return [tuple(self.m.uc.mem_read(c, 1)[0] for c in counters) for _p, counters in rows]

    def run_credit(self, club, team):
        self.m.call(self.at["awards_credit"], ecx=team, edx=club, stack=(self.LIVE0,))

    DEFENCE = [("CB", 1, 3, 0, 4, (0.85, 0.5, 0.7)), ("CB", 1, 0, 0, 3, (0.8, 0.5, 0.7)), ("FS", 1, 0, 0, 6, (0.8, 0.5, 0.75)),
               ("SS", 1, 0, 0, 7, (0.78, 0.55, 0.78)), ("ILB", 1, 2, 4, 12, (0.88, 0.8, 0.95)),
               ("ILB", 1, 0, 2, 9, (0.7, 0.75, 0.85)), ("DE", 1, 0, 1, 3, (0.4, 0.9, 0.7)), ("DE", 1, 0, 0, 2, (0.4, 0.85, 0.7)),
               ("DT", 1, 0, 1, 3, (0.3, 0.8, 0.7)), ("DT", 0, 0, 0, 0, (0.3, 0.8, 0.7)),
               ("WR", 1, 0, 0, 1, (0.7, 0.3, 0.4)), ("QB", 1, 0, 0, 0, (0.5, 0.3, 0.4))]

    def test_totals_are_kept_and_only_defenders_who_played_are_credited(self):
        club, team, rows = self.club(self.DEFENCE)
        before = self.counts(rows)
        self.run_credit(club, team)
        after = self.counts(rows)
        defenders = [i for i, row in enumerate(self.DEFENCE) if row[0] not in ("WR", "QB") and row[1]]
        for k in range(3):
            self.assertEqual(sum(after[i][k] for i in defenders), sum(before[i][k] for i in defenders), k)
        self.assertEqual(after[9], (0, 0, 0))                       # the DT who did not play
        self.assertEqual(after[10:], before[10:])                   # offence keeps the engine's line

    def test_a_counter_two_men_share_is_left_alone(self):
        club, team, rows = self.club(self.DEFENCE)
        m = self.m
        holder_a, holder_b = m.get(self.LIVE0 + 0 * 0x54 + 0x30), m.get(self.LIVE0 + 1 * 0x54 + 0x30)
        stats_a, stats_b = m.get(holder_a), m.get(holder_b)
        m.put(stats_b + 0x20, m.get(stats_a + 0x20))                     # both corners point at one interception record
        shared = m.get(stats_a + 0x20) + 4
        before = m.uc.mem_read(shared, 1)[0]
        others = sum(self.counts(rows)[i][0] for i in range(2, 9))
        self.run_credit(club, team)
        self.assertEqual(m.uc.mem_read(shared, 1)[0], before)
        self.assertEqual(sum(self.counts(rows)[i][0] for i in range(2, 9)), others)

    def test_whole_sacks_go_to_one_man_and_a_lone_half_last(self):
        men = [list(r) for r in self.DEFENCE]
        men[4][3], men[5][3], men[6][3], men[8][3] = 3, 0, 0, 0          # three half sacks in all
        club, team, rows = self.club([tuple(r) for r in men])
        self.run_credit(club, team)
        sacks = [c[1] for c in self.counts(rows)]
        self.assertEqual(sum(sacks), 3)
        self.assertIn(sorted(s for s in sacks if s), ([1, 2], [3]))

    def test_the_gates(self):
        for label, kwargs in (("not a franchise", dict(league=1)), ("a played game", dict(mode=5)),
                              ("preseason", dict(stage=7))):
            with self.subTest(label):
                self.setUp()
                club, team, rows = self.club(self.DEFENCE, **kwargs)
                before = self.counts(rows)
                self.run_credit(club, team)
                self.assertEqual(self.counts(rows), before)

    def test_the_same_game_gives_the_same_credit_and_another_week_another(self):
        results = []
        for week in (3, 3, 4):
            self.setUp()
            club, team, rows = self.club(self.DEFENCE, week=week)
            self.run_credit(club, team)
            results.append(self.counts(rows))
        self.assertEqual(results[0], results[1])
        self.assertNotEqual(results[0], results[2])

    def test_position_shares_over_many_games_follow_the_table(self):
        got = collections.defaultdict(collections.Counter)
        role = {"CB": "CB", "FS": "S", "SS": "S", "ILB": "LB", "DE": "DE", "DT": "DT"}
        men = [("CB", 1, 2, 0, 8, (0.85, 0.5, 0.7)), ("CB", 1, 0, 0, 0, (0.8, 0.5, 0.7)), ("FS", 1, 0, 0, 0, (0.8, 0.5, 0.75)),
               ("SS", 1, 0, 0, 0, (0.78, 0.55, 0.78)), ("ILB", 1, 0, 8, 12, (0.88, 0.8, 0.95)),
               ("ILB", 1, 0, 0, 0, (0.7, 0.75, 0.85)), ("DE", 1, 0, 0, 0, (0.4, 0.9, 0.7)), ("DE", 1, 0, 0, 0, (0.4, 0.85, 0.7)),
               ("DT", 1, 0, 0, 0, (0.3, 0.8, 0.7)), ("DT", 1, 0, 0, 0, (0.3, 0.8, 0.7))]
        for week in range(300):
            self.setUp()
            club, team, rows = self.club(men, week=week)
            self.run_credit(club, team)
            for (pos, *_r), counts in zip(men, self.counts(rows)):
                for k, name in enumerate(("interceptions", "sacks", "tackles")):
                    got[name][role[pos]] += counts[k]
        for k, name in enumerate(("interceptions", "sacks", "tackles")):
            total = sum(got[name].values())
            weights = awards.credit_weights([(role[pos], ratings[k]) for pos, *_x, ratings in men], name, cb_bonus=False)
            want = collections.Counter()
            for (pos, *_x), w in zip(men, weights):
                want[role[pos]] += w
            for r, share in want.items():
                with self.subTest(stat=name, role=r):
                    self.assertAlmostEqual(got[name][r] / total, share, delta=0.04)
        self.assertLess(got["interceptions"]["LB"] / sum(got["interceptions"].values()), 0.2)

    def test_with_the_cornerback_owner_the_corners_take_less_of_the_engine_tackles(self):
        self.assertEqual(self.m.uc.mem_read(0x1334C3, 1)[0], 0x8B)       # this image has no cornerback owner
        self.assertGreater(awards.CREDIT_SHARES["tackles"][0], awards.CREDIT_SHARES["tackles_with_cb"][0])


@unittest.skipUnless(_retail() is not None, "pinned USA XBE required")
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


if __name__ == "__main__":
    unittest.main()
