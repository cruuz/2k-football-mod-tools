"""b81 league-aging (the "weekend version", coordinator rulings 11/25): ten simulated seasons aged and inflated the
league (CPU starters aged 30+ 19.7 -> 49.6 %, halfback starters +12 overall, first-round rookies starting a quarter as
often as real ones). Four in-place changes, each tested here against the code it replaces:

W1 classes one year younger: nfl2k5_season_length.rookie_birth_base = year - 1923 (retail and b780: year - 1924);
   older images still read applied and progression's apply moves them in place;
W2 retirement (nfl2k5_progression, 0x2BCF90 and 0xACEDB0): position ages a year or two earlier, a producer may go
   from one year before his position's age, stars still last longest, a flatter chance table, no franchise-year
   damping, and an age rule for unsigned kickers and punters (from 29 plus 0-3 years of their own);
W3 aging data: the growth years cut on the shared curves, the position tables on the real age clock (21 + years pro)
   with growth caps from 25 and quarterbacks growing at 25-28, the running-back production shift at 1,800 / 2,100;
W4 the class generator rolls one grade per prospect (nfl2k5_rookie_faces region C), so a class has real stars; merged
   on b81 rookie-faces (624ebc2c6) the roll is g + 0.25 (u - g) in the same slots, with the templates widened to match.
Every b780 executable (v0.9, the b81 integration) reads legacy and upgrades in place.
"""
from __future__ import annotations

import random
import statistics
import struct
import unittest

from mod_editor.core import nfl2k5_progression as pg
from mod_editor.core import nfl2k5_rookie_faces as rf
from mod_editor.core import nfl2k5_season_length as season
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC

POS = {name: i for i, name in enumerate(pg.POSITIONS)}


def _retail():
    from tests.nfl2k5_supersim_draft_fixture import retail_bytes
    return retail_bytes()


def _write_version(payload: bytes, version: str, *, retire: bool = True) -> bytes:
    """An image carrying one release of the progression owner (its sites written over retail, digests repinned)."""
    buf = bytearray(payload)
    sites = pg._data_sites(payload, version) + pg._career_sites(payload, version)
    if retire:
        sites += pg._retirement_sites(version)
    sections = _sections(payload)
    for _label, va, _before, after in sites:
        off = pg._offset(payload, va)
        buf[off:off + len(after)] = after
    for section in sections:
        d = section.header_offset + 36
        buf[d:d + 20] = section_digest(bytes(buf), section)
    return bytes(buf)


# ------------------------------------------------------------------------------------------------------------ W1
class ClassAgeTests(unittest.TestCase):
    def test_the_birth_base_is_one_year_later(self):
        # retail 2004: (season + 80..82) % 100 = born 1980-82, so a 2005 rookie was 23-25; 2026 -> born 2003-05
        self.assertEqual(season.rookie_birth_base(2026), 103)
        self.assertEqual(season.previous_rookie_birth_base(2026), 102)
        sites = {s.label: s for s in season.year_sites(2026)}
        self.assertEqual((sites["rookie_birth_base"].patched, sites["rookie_birth_base"].legacy), (b"\x67", b"\x66"))
        self.assertEqual((sites["rookie_birth_top"].patched, sites["rookie_birth_top"].legacy), (b"\x69", b"\x68"))

    def test_a_legacy_image_reads_applied_and_upgrades_two_bytes(self):
        retail = _retail()
        built, _ = season.apply(retail, groups=("year",))
        self.assertEqual(season.rookie_birth_state(built), "applied")
        self.assertEqual(season.group_status(built, "year"), "applied")
        legacy = bytearray(built)
        sections = _sections(built)
        for va, value in ((season.ROOKIE_BIRTH_BASE_VA, 0x66), (season.ROOKIE_BIRTH_TOP_VA, 0x68)):
            legacy[season._offset(built, va, sections)] = value
        legacy = bytes(legacy)
        self.assertEqual(season.group_status(legacy, "year"), "applied")     # older builds keep working everywhere
        self.assertEqual(season.rookie_birth_state(legacy), "legacy")
        upgraded, receipt = season.upgrade_rookie_birth(legacy)
        self.assertEqual(receipt["rookie_birth"], "upgraded")
        self.assertEqual(season.rookie_birth_state(upgraded), "applied")
        changed = [i for i in range(len(legacy)) if legacy[i] != upgraded[i]]
        self.assertTrue(all(i < 0x1000 for i in changed[2:]) and len([i for i in changed if i >= 0x1000]) == 2)
        self.assertEqual(season.upgrade_rookie_birth(retail)[0], retail)     # no year group: nothing to move

    @unittest.skipUnless(HAVE_UC, "unicorn is not installed")
    def test_the_native_class_is_born_a_year_later(self):
        """The game's own class turnover under Unicorn (test_b780_draft_class._class_turnover): every generated
        prospect's two-digit birth year is (franchise year 0 + base + 0..2) % 100, so in the 2027 draft they are
        22-24 on the calendar (the real 2026 rookies 21-24 on 1 September, 22.76 on average)."""
        from tests.mod_editor.test_b780_draft_class import _class_turnover
        from tests.nfl2k5_supersim_draft_fixture import Machine, retail_roster  # noqa: F401
        built, _ = season.apply(_retail(), groups=("year",))
        births = _class_births(built, retail_roster())
        self.assertGreater(len(births), 200)
        self.assertEqual(set(births), {3, 4, 5})
        self.assertTrue(all(c > len(births) / 5 for c in (births.count(3), births.count(4), births.count(5))))


def _class_births(payload, body):
    import collections  # noqa: F401
    from tests.nfl2k5_supersim_draft_fixture import Machine
    m = Machine(payload, trace_writes=False)
    size = len(body) - 0x40
    m.uc.mem_write(m.ARENA + 0x300, body)
    m.put(0xB72804, m.ARENA + 0x300)
    m.put(0xB72808, size if size > 0x91000 else 0x91000)
    m.put(0xB7280C, size)
    m.fixup_roster(m.ARENA + 0x340)
    m.seed(12345)
    for address, value in ((0xE5FF80, 4), (0xE60120, 0), (0xE6000C, 5), (0xE60010, 5)):
        m.put(address, value)
    m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
    m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
    generated = []
    m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: generated.append(m.reg("ECX")), begin=0x2BE6F0, end=0x2BE6F0)
    m.call(0x13EE10, budget=2_000_000_000)
    m.call(0x2BDB00, budget=4_000_000_000)
    m.call(0x2BDA90, budget=2_000_000_000)
    generated.clear()
    m.call(0x2BE940, ecx=380, budget=4_000_000_000)
    return [((struct.unpack("<I", bytes(m.uc.mem_read(r + 0x18, 4)))[0] >> 21) & 127) % 100 for r in generated]


# ------------------------------------------------------------------------------------------------------------ W2
class RetirementModelTests(unittest.TestCase):
    """The decision as a probability (retirement_chance mirrors the native code; RetirementNativeTests compare)."""

    def chance(self, pos, age, overall, *, club=True, depth_row=0, games=16, year=0, version="b81", day=1):
        return pg.retirement_chance(position=POS[pos], age=age, overall=overall, year=year, club=club,
                                    depth_row=depth_row, games=games, version=version, birth_day=day)

    def test_good_veteran_starters_retire_in_their_thirties(self):
        # an 85 starting receiver at 33: today 0.02 x 0.6 in a franchise's first offseason; real starters ~22 %
        self.assertLess(self.chance("WR", 33, 0.85, version="b780"), 0.03)
        self.assertGreaterEqual(self.chance("WR", 33, 0.85), 0.139)
        self.assertGreaterEqual(self.chance("T", 34, 0.82), 0.189)
        self.assertGreaterEqual(self.chance("CB", 33, 0.81), 0.189)
        # stars still last longest: a 92 starting tackle goes less often than an 82 one at the same age
        self.assertLess(self.chance("T", 34, 0.92), self.chance("T", 34, 0.82))

    def test_producers_never_go_before_their_position_age_minus_one(self):
        # SWeaR 11/01 ("Chuba Hubbard ... rushed for 1600 yrds and 8TDs yet retired"): a producer in his twenties never
        for pos in pg.POSITIONS:
            age = pg.NFL_RETIRE_BASE[POS[pos]] + 24 + pg.RETIRE_FLOOR - 1
            self.assertEqual(self.chance(pos, age, 0.75), 0.0, pos)
        self.assertEqual(self.chance("RB", 27, 0.60), 0.0)

    def test_quarterbacks_kickers_and_punters_go_latest(self):
        self.assertEqual(self.chance("QB", 34, 0.88), 0.0)
        self.assertLessEqual(self.chance("QB", 36, 0.88), 0.071)
        self.assertGreater(self.chance("QB", 39, 0.85), self.chance("QB", 36, 0.85))
        self.assertEqual(self.chance("K", 35, 0.80), 0.0)
        self.assertGreater(self.chance("WR", 34, 0.82), self.chance("QB", 34, 0.82))

    def test_no_franchise_year_damping(self):
        self.assertEqual(self.chance("OLB", 34, 0.75, year=0), self.chance("OLB", 34, 0.75, year=4))
        self.assertLess(self.chance("OLB", 34, 0.75, year=0, version="b780"),
                        self.chance("OLB", 34, 0.75, year=4, version="b780"))

    def test_unsigned_specialists_retire_by_their_own_age(self):
        # Noah 10/28: retirement by age, never "because they're an older free agent nobody signed" (coordinator R13);
        # an unsigned kicker or punter's age is 29 plus his 0-3 years (birth day & 3)
        for pos in ("K", "P"):
            for day in range(1, 29):
                hold = day & 3
                self.assertEqual(self.chance(pos, 28 + hold, 0.75, club=False, day=day), 0.0, (pos, day))
                self.assertGreater(self.chance(pos, 29 + hold, 0.75, club=False, day=day), 0.0, (pos, day))
            self.assertEqual(self.chance(pos, 31, 0.75, club=False, version="b780"), 0.0)
        # a kicker on a club, and every other free agent, keep the general rule
        self.assertEqual(self.chance("K", 31, 0.75, club=True, depth_row=0), 0.0)
        self.assertEqual(self.chance("WR", 29, 0.75, club=False), pg.retirement_chance(
            position=POS["WR"], age=29, overall=0.75, year=0, club=False))

    def test_the_league_wide_rates_follow_real_starters(self):
        """A starter population shaped like the stored panels' (positions x ages 29-36, overall 72-94): modelled
        retirement each year at coming-season ages 29-30 / 31-32 / 33-34 / 35-36 sits between the installed rule
        and real starters' career ends (7.9 / 13.5 / 22.0 / 27.6 %, cuts included)."""
        rng = random.Random(81)
        bands = {(29, 30): [], (31, 32): [], (33, 34): [], (35, 36): []}
        for (lo, hi), out in bands.items():
            for _ in range(4000):
                pos = rng.choice([p for p in pg.POSITIONS if p not in ("K", "P")])
                out.append(self.chance(pos, rng.randint(lo, hi), rng.uniform(0.72, 0.94)))
        rates = [100 * statistics.mean(v) for v in bands.values()]
        self.assertTrue(1.5 <= rates[0] <= 8, rates)
        self.assertTrue(6 <= rates[1] <= 14, rates)
        self.assertTrue(12 <= rates[2] <= 23, rates)
        self.assertTrue(18 <= rates[3] <= 32, rates)


@unittest.skipUnless(HAVE_UC, "unicorn is not installed")
class RetirementNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_roster
        cls.retail = _retail()
        cls.roster = retail_roster()
        cls.applied, cls.receipt = pg.apply(cls.retail)

    def test_the_native_decision_matches_the_model_for_free_agent_specialists(self):
        from tests.mod_editor.test_b780_b4_economy import _machine, _player, _rate
        m = _machine(self.applied, self.roster)
        n = 600
        found = 0
        for slot in range(60):
            p = m.get(m.team_base + 4 * slot)
            pos = m.uc.mem_read(p + 0x35, 1)[0]
            if pos not in (POS["K"], POS["P"]):
                continue
            found += 1
            day = (struct.unpack("<I", bytes(m.uc.mem_read(p + 0x18, 4)))[0] >> 16) & 31
            for age in (27, 29 + (day & 3) - 1, 29 + (day & 3), 33, 36):
                _player(m, p, age=age, depth_row=6, games=0)
                chance = pg.retirement_chance(position=pos, age=age, overall=m.rating(p), year=0, club=False,
                                              birth_day=day)
                rate = _rate(m, p, 0, n)
                bound = 4.5 * (chance * (1 - chance) / n) ** 0.5 + 0.012
                self.assertLess(abs(rate - chance), bound, (slot, age, rate, chance))
            if found >= 2:
                break
        self.assertGreaterEqual(found, 2)

    def test_the_chance_table_is_written_and_the_damping_is_gone(self):
        off = pg._offset(self.applied, pg.RETIRE_P_VA)
        self.assertEqual(struct.unpack("<11f", self.applied[off:off + 44]),
                         struct.unpack("<11f", struct.pack("<11f", *pg.RETIRE_P)))
        code = pg.retirement_code()[0]
        self.assertNotIn(struct.pack("<I", pg.RETIRE_Y_VA), code)
        self.assertIn(struct.pack("<I", pg.RETIRE_Y_VA), pg.retirement_code("b780")[0])


# ------------------------------------------------------------------------------------------------------------ W3
class AgingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        cls.profiles = pg._profiles(cls.retail)

    def means(self, version):
        v = pg._version(version)
        curves, weights = pg.patched_tables(self.profiles, shape=v["shape"])
        native = pg._native_means(curves, weights, self.profiles)
        dd = pg.decline_tables(curves, weights, self.profiles, v["target"], v["age_at_year"])
        out = {}
        for ci, cls_ in enumerate(pg.CLASSES):
            for gi, group in enumerate(pg.GROUPS):
                out[(cls_, group)] = [native[(ci, gi)][y] + dd[(cls_, group)][y] for y in range(pg.CURVE_LEN)]
        return out

    def test_the_clock_is_the_real_rookie_age(self):
        self.assertEqual(pg.AGE_AT_YEAR, 21)
        new, old = self.means("b81"), self.means("b780")
        # the receivers' physical slide (-1.5 a year at 27-28) lands at years pro 6-7 now, at 7-8 before: a year earlier
        self.assertAlmostEqual(new[("WR", "physical")][6] + new[("WR", "physical")][7], -3.0, delta=0.8)
        self.assertAlmostEqual(old[("WR", "physical")][7] + old[("WR", "physical")][8], -3.0, delta=0.8)
        self.assertLess(new[("WR", "physical")][6], old[("WR", "physical")][6] - 0.5)     # age 27 now, 26 before

    def test_growth_years_are_cut_and_capped(self):
        new, old = self.means("b81"), self.means("b780")
        for cls_ in ("WR", "CB", "S", "TE", "LB", "OL", "DL"):
            early_new, early_old = sum(new[(cls_, "skill")][1:4]), sum(old[(cls_, "skill")][1:4])
            self.assertLess(early_new, 0.75 * early_old, cls_)
            self.assertLessEqual(sum(new[(cls_, "skill")][4:7]), 1.6, cls_)        # capped from 25: 0 or +0.5 a year
        # quarterbacks grow into starters at 25-28 (+1.5 a year on their skills)
        self.assertGreater(sum(new[("QB", "skill")][4:8]), sum(old[("QB", "skill")][4:8]) + 3.5)

    def test_backs_keep_the_b780_years_pro_placement(self):
        # retune r1 (paired-r0): moving the backs' slide a year earlier on top of the new clock made CPU halfback starters
        # fall 7.6 overall in ten seasons; their table keeps b780's years-pro placement, and the production shift and the
        # retirement ages do the rest (L6 in the lane's gates)
        new, old = self.means("b81"), self.means("b780")
        self.assertAlmostEqual(sum(new[("RB", "physical")][4:9]), sum(old[("RB", "physical")][4:9]), delta=1.2)
        self.assertLess(sum(new[("RB", "physical")][4:12]), -9.0)

    def test_the_rb_production_shift_is_for_outliers(self):
        code = pg.career_code(pg.career_layout(self.retail)[2])[0]
        self.assertIn(b"\x3d" + struct.pack("<I", 1800), code)
        self.assertIn(b"\x3d" + struct.pack("<I", 2100), code)
        self.assertNotIn(b"\x3d" + struct.pack("<I", 1200), code)

    def test_a_b780_image_reads_legacy_and_upgrades_in_place(self):
        for retire in (False, True):                 # beta-78/79 (retail decision) and b780 / v0.9 / b81 integration
            image = _write_version(self.retail, "b780", retire=retire)
            self.assertEqual(pg.status(image), "legacy")
            upgraded, receipt = pg.apply(image)
            self.assertTrue(receipt["upgraded_from_legacy"])
            self.assertEqual(pg.status(upgraded), "applied")
            fresh = pg.apply(self.retail)[0]
            self.assertEqual(upgraded, fresh, "an upgraded image equals a fresh install")

    def test_apply_moves_a_legacy_rookie_birth_base(self):
        built, _ = season.apply(self.retail, groups=("year",))
        legacy = bytearray(_write_version(built, "b780"))
        sections = _sections(bytes(legacy))
        for va, value in ((season.ROOKIE_BIRTH_BASE_VA, 0x66), (season.ROOKIE_BIRTH_TOP_VA, 0x68)):
            legacy[season._offset(bytes(legacy), va, sections)] = value
        legacy = bytes(legacy)
        self.assertEqual(pg.status(legacy), "legacy")
        out, receipt = pg.apply(legacy)
        self.assertEqual(receipt["rookie_birth"]["rookie_birth"], "upgraded")
        self.assertEqual((pg.status(out), season.rookie_birth_state(out)), ("applied", "applied"))
        current = pg.apply(_write_version(built, "b780"))[0]
        self.assertEqual(pg.status(current), "applied")      # a current base is left alone


# ------------------------------------------------------------------------------------------------------------ W4
@unittest.skipUnless(HAVE_UC, "unicorn is not installed")
class GradeRollTests(unittest.TestCase):
    """Region C under Unicorn with the b779-rf3 test's stand-ins (NativeRf3Ratings.run_region)."""

    @classmethod
    def setUpClass(cls):
        from tests.mod_editor.test_b778_rh1_rookie_faces import NativeRf3Ratings
        case = NativeRf3Ratings("test_code_fits")
        cls.res = case.run_region(n=1200, seed=81)

    def test_one_grade_per_prospect(self):
        """Every rating's r is g + GRADEW (u - g) = 0.75 g + 0.25 u for the prospect's one grade g (b779-rf3 and b81
        rookie-faces: each rating drew its own r), so his ratings move together and a class has real stars and busts."""
        spreads, grades = [], []
        for r, g_bits in self.res:
            g = struct.unpack("<f", struct.pack("<i", g_bits))[0]
            grades.append(g)
            pos = []
            for i in range(29):
                off = 0x36 + i
                if off in (0x4E, 0x50, 0x51):
                    continue
                lo, hi = (40, 80) if off % 2 else (20, 60)
                x = (r[off] - lo) / (hi - lo)
                pos.append(x)
                self.assertTrue(0.75 * g - 0.03 <= x <= 0.75 * g + 0.25 + 0.03, (g, off, r[off]))
            spreads.append(statistics.mean(pos))
        self.assertGreater(statistics.pstdev(spreads), 0.19)     # 0.75 sd(g) = 0.22; one draw per rating: about 0.06
        self.assertTrue(all(0.0 <= g < 1.0 for g in grades))
        upper = sum(1 for g in grades if g >= 0.5) / len(grades)
        self.assertTrue(0.44 < upper < 0.56, upper)               # no blue-chip draw (the rare-face pick took its bytes)

    def test_the_weight_is_the_retail_quarter(self):
        """GRADEW is a retail .rdata literal (0.25f, read by 186 retail sites), not a byte this release writes."""
        payload = _retail()
        off = pg._offset(payload, 0x4E696C)
        self.assertEqual(struct.unpack_from("<f", payload, off)[0], 0.25)
        self.assertIn(struct.pack("<I", 0x4E696C), rf.CODE_C)

    def test_region_c_upgrade(self):
        pad = lambda code: code + b"\xcc" * (rf.REGION_C_END - rf.REGION_C - len(code))  # noqa: E731
        self.assertNotEqual(pad(rf.CODE_C), pad(rf.CODE_C_FACES))
        self.assertEqual(len(rf.CODE_C), len(rf.CODE_C_FACES))
        # only the two slots (0xA2..0xCB) and the loop's call to qrand (one displacement byte at 0x2B) changed against
        # b81 rookie-faces; everything after the slots keeps its address
        diff = [i for i in range(len(rf.CODE_C_FACES)) if rf.CODE_C[i] != rf.CODE_C_FACES[i]]
        self.assertEqual(diff[0], 0x2B)
        self.assertTrue(0xA2 <= min(diff[1:]) and max(diff) <= 0xCB, (hex(min(diff[1:])), hex(max(diff))))


class MergedRevisionTests(unittest.TestCase):
    """The merge with b81 rookie-faces (624ebc2c6): each side's earlier region C is a recognised revision. b81
    rookie-faces' own ("faces": one draw per rating) reads applied and upgrade_xbe moves region C only; league-aging's
    first roll on GEN1 ("gen1_aging", the paired-r2 candidate discs) reads previous and upgrades like GEN1."""

    def setUp(self):
        from pathlib import Path
        from tests.mod_editor.test_b778_rh1_rookie_faces import RETAIL_XBE, shipped_pool, toy_bank
        if not (RETAIL_XBE and Path(RETAIL_XBE).is_file()):
            self.skipTest("set NFL2K5_RETAIL_XBE to the retail default.xbe")
        firsts, lasts = shipped_pool()
        self.bank = toy_bank()
        self.table = rf.tables(firsts, lasts, self.bank)
        self.out, _ = rf.xbe_apply(Path(RETAIL_XBE).read_bytes(), self.table)

    @staticmethod
    def put(data, va, value):
        buf = bytearray(data)
        at = rf._offset(data, va, len(value))
        buf[at:at + len(value)] = value
        return bytes(buf)

    def pad(self, code):
        return code + b"\xcc" * (rf.REGION_C_END - rf.REGION_C - len(code))

    def test_current(self):
        self.assertEqual((rf.xbe_status(self.out), rf.xbe_revision(self.out), rf.region_c_state(self.out)),
                         ("applied", "applied", "current"))
        self.assertEqual(rf.upgrade_xbe(self.out, self.bank), (self.out, None))

    def test_rookie_faces_region_c_is_upgraded_in_place(self):
        faces = self.put(self.out, rf.REGION_C, self.pad(rf.CODE_C_FACES))
        self.assertEqual((rf.xbe_status(faces), rf.xbe_revision(faces), rf.region_c_state(faces)),
                         ("applied", "faces", "faces"))
        up, receipt = rf.upgrade_xbe(faces, self.bank)
        self.assertEqual(up[rf._offset(up, rf.REGION_C, 4):], self.out[rf._offset(up, rf.REGION_C, 4):])
        self.assertEqual((rf.xbe_revision(up), receipt["upgraded_from"], receipt["changed_bytes"]),
                         ("applied", "faces", 42))
        self.assertEqual(rf.xbe_apply(faces, self.table)[0], self.out, "a full write over it gives the same bytes")

    def test_league_aging_first_roll_on_gen1_reads_previous(self):
        tail = rf.TABLE_END - rf.TABLE_VA - rf.TABLE_DATA
        pad = lambda code, size: code + b"\xcc" * (size - len(code))  # noqa: E731
        gen1 = self.put(self.put(self.out, rf.REGION_A, pad(rf.CODE_A_GEN1, rf.REGION_A_END - rf.REGION_A)),
                        rf.REGION_B, pad(rf.CODE_B_GEN1, rf.REGION_B_END - rf.REGION_B))
        gen1 = self.put(gen1, rf.TABLE_VA + rf.TABLE_DATA, pad(rf.CODE_D_GEN1, tail - 4))
        aging = self.put(gen1, rf.REGION_C, self.pad(rf.CODE_C_GEN1_AGING))
        self.assertEqual((rf.xbe_status(aging), rf.xbe_revision(aging), rf.region_c_state(aging)),
                         ("previous", "gen1_aging", "gen1_aging"))
        self.assertEqual(rf.xbe_revision(self.put(gen1, rf.REGION_C, self.pad(rf.CODE_C_GEN1))), "gen1")
        up, receipt = rf.xbe_apply(aging, self.table)
        self.assertEqual((up, receipt["from"]), (self.out, "previous"))
        # a mix (this release's region A with the first roll) is nobody's revision
        mixed = self.put(aging, rf.REGION_A, pad(rf.CODE_A, rf.REGION_A_END - rf.REGION_A))
        self.assertEqual(rf.xbe_status(mixed), "foreign")


# ---------------------------------------------------------------------- review fixes (11/26: M1, M2, S1, S2, S3)
def _fixture_xbe(variable: str, what: str) -> bytes:
    import os
    from pathlib import Path
    path = Path(os.environ.get(variable, "") or "missing")
    if not path.is_file():
        raise unittest.SkipTest(f"{what} is absent ({variable})")
    return path.read_bytes()


def _qualifying(payload: bytes, threshold: int) -> int:
    from mod_editor.core import nfl2k5_star_career as sc
    return sum(1 for value in sc.row_potentials(payload) if value >= threshold)


class StarCareerGemTests(unittest.TestCase):
    """Review M2 (coordinator ruling 11/26): star_career's later-round gems need an archetype whose growth reaches the
    gem threshold. The fixed 70 was the top 20 of the 162 archetype rows on the b780 curves; b81's curves halve the
    growth ramps, so 70 left 1 row. The threshold is now taken from the installed table by rank: the potential at which
    GEM_ROWS (20) rows qualify, ties included. A full build installs it from the b81 curves; the earlier revision
    (fixed 70) reads "previous" and is upgraded in place."""

    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        cls.b81, _ = pg.apply(cls.retail)

    def test_the_gem_threshold_keeps_twenty_archetype_rows(self):
        from mod_editor.core import nfl2k5_star_career as sc
        self.assertEqual((sc.GEM_ROWS, sc.PREVIOUS_GEM_POTENTIAL), (20, 70))
        for name, payload, want in (("b81 curves", self.b81, 47), ("retail curves", self.retail, 65)):
            with self.subTest(curves=name):
                threshold = sc.gem_threshold(payload)
                self.assertEqual(threshold, want)
                self.assertGreaterEqual(_qualifying(payload, threshold), sc.GEM_ROWS)
                self.assertLess(_qualifying(payload, threshold + 1), sc.GEM_ROWS)
        self.assertEqual(_qualifying(self.b81, sc.PREVIOUS_GEM_POTENTIAL), 1, "the fixed 70 on the b81 curves")

    def test_the_released_v09_install_is_this_revision(self):
        from mod_editor.core import nfl2k5_star_career as sc
        v09 = _fixture_xbe("NFL2K5_V09_RELEASED_XBE", "the released v0.9 executable")
        self.assertEqual((sc.gem_threshold(v09), _qualifying(v09, 70)), (70, 20))   # the b780 curves: rank 20 is 70
        self.assertEqual(sc.status(v09), "applied")

    def test_a_full_build_installs_the_table_from_the_b81_curves(self):
        import inspect
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_star_career as sc
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        built, _ = sc.apply(self.b81)
        code_a, _data = sc._owned(built)
        code = XbeImage(built).read(code_a["va"], sc.CODE_SIZE)
        self.assertEqual(code[sc.K_POT:sc.K_POT + 17 * 16], sc.potential_table(self.b81))
        self.assertEqual(struct.unpack_from("<i", code, sc.K_CONST2 + 12)[0], 47)
        self.assertEqual(sc.read_settings(built)["gem_potential"], 47)
        # a full build runs progression (the "xbe" step) before star_career's late step builds its table
        source = inspect.getsource(mod_build._build)
        self.assertLess(source.index('"progression": plan.progression'),
                        source.index("_apply_star_career(plan, target, receipt, progress)"))

    def test_the_fixed_70_revision_reads_previous_and_upgrades_in_place(self):
        from mod_editor.core import nfl2k5_star_career as sc
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        built, _ = sc.apply(self.retail)                       # star_career on the retail curves: threshold 65
        code_a, data_a = sc._owned(built)
        installed = XbeImage(built).read(code_a["va"], sc.CODE_SIZE)
        old, _ = sc.code_for(built, code_a["va"], data_a["va"], revision="previous")
        self.assertEqual(struct.unpack_from("<i", old, sc.K_CONST2 + 12)[0], 70)
        previous, _ = space.install_code(built, sc.OWNER, old, previous=installed)
        self.assertEqual(sc.status(previous), "previous")
        # neighbours accept it: the MyCareer guards see the class-loop hooks through it
        hook = sc.HOOKS[0]
        raw = XbeImage(previous).read(hook[1], hook[3])
        self.assertEqual(sc.canonical_context(previous, hook[1], raw), hook[2])
        upgraded, receipt = sc.apply(previous)
        self.assertEqual((sc.status(upgraded), receipt["upgraded_from"], upgraded), ("applied", "previous", built))

    def test_refresh_follows_curves_rewritten_after_install(self):
        from mod_editor.core import nfl2k5_star_career as sc
        v09 = _fixture_xbe("NFL2K5_V09_RELEASED_XBE", "the released v0.9 executable")
        body = sc.installed_body(v09)
        aged, _ = pg.apply(v09)
        self.assertEqual(sc.status(aged), "foreign", "the installed table no longer matches the curves")
        refreshed, receipt = sc.refresh(aged, body)
        self.assertEqual((sc.status(refreshed), sc.read_settings(refreshed)["gem_potential"]), ("applied", 47))
        self.assertEqual(sc.refresh(refreshed, sc.installed_body(refreshed)), (refreshed, None))


class LeagueAgingUpgradeTests(unittest.TestCase):
    """Review M1: the in-place routes' league-aging step refreshes star_career after progression rewrites the curves
    (tests/mod_editor/test_b81_league_aging_routes.py sweeps every owner through the three routes)."""

    def test_the_upgrade_refreshes_star_career(self):
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_star_career as sc
        for variable, what in (("NFL2K5_V09_RELEASED_XBE", "the released v0.9 executable"),
                               ("B81_HISTORY_POOL_FULL_XBE", "the 8b180ed5 candidate executable")):
            with self.subTest(executable=what):
                payload = _fixture_xbe(variable, what)
                self.assertEqual(sc.status(payload), "applied")
                out, receipt = mod_build._league_aging_upgrade(payload)
                self.assertEqual((pg.status(out), sc.status(out)), ("applied", "applied"))
                self.assertEqual(receipt["star_career"]["gem_potential"], 47)
                self.assertEqual(mod_build._league_aging_upgrade(out), (out, None))

    def test_the_in_place_write_reads_star_career_back(self):
        from unittest.mock import patch
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_star_career as sc
        payload = _fixture_xbe("NFL2K5_V09_RELEASED_XBE", "the released v0.9 executable")

        def write(stale: bool):
            store = {"t": payload}
            receipt = {"steps": [], "result": {}}
            with patch.object(mod_build, "_xbe_bytes", side_effect=lambda _t: store["t"]), \
                    patch.object(mod_build, "_write_xbe_bytes", side_effect=lambda _t, data: store.update(t=data)):
                if stale:   # a refresh that claims success but leaves the b780 table: the read-back refuses it
                    with patch.object(sc, "refresh", side_effect=lambda p, _body: (p, {"gem_potential": 47})):
                        mod_build._apply_league_aging_in_place("t", receipt, lambda *_: None)
                else:
                    mod_build._apply_league_aging_in_place("t", receipt, lambda *_: None)
            return store["t"], receipt
        out, receipt = write(stale=False)
        self.assertEqual(sc.status(out), "applied")
        self.assertEqual(receipt["steps"][-1]["star_career"]["gem_potential"], 47)
        with self.assertRaisesRegex(RuntimeError, "player development update"):
            write(stale=True)


class Calendar2004Tests(unittest.TestCase):
    """Review S1: a 2004-base calendar (season "year" group) written before this release keeps the birth base at
    year - 1924 = 80, which equals retail. Those bytes read as the earlier release ("legacy"), the group and the calendar
    engine's prerequisites read applied (as at 624ebc2c6), and progression's apply moves them to 81."""

    @staticmethod
    def _earlier_release(payload: bytes) -> bytes:
        """The 2004 year group as 624ebc2c6 wrote it (review-probes/y2004_build.py): this release's group with the
        birth bytes left retail (that release's 2004 base was year - 1924 = retail)."""
        sections = _sections(payload)
        buf = bytearray(payload)
        for va, value in ((season.ROOKIE_BIRTH_BASE_VA, season.RETAIL_ROOKIE_BIRTH_BASE),
                          (season.ROOKIE_BIRTH_TOP_VA, season.RETAIL_ROOKIE_BIRTH_BASE + 2)):
            buf[pg._offset(payload, va)] = value
        for section in sections:
            d = section.header_offset + 36
            buf[d:d + 20] = section_digest(bytes(buf), section)
        return bytes(buf)

    def test_an_earlier_2004_calendar_reads_applied_and_upgrades(self):
        from mod_editor.core import nfl2k5_calendar_engine as ce
        retail = _retail()
        for groups in (("year",), tuple(season.CALENDAR_GROUPS)):
            with self.subTest(groups=groups):
                fresh, _ = season.apply(retail, groups=groups, year=2004)
                earlier = self._earlier_release(fresh)
                self.assertNotEqual(earlier, fresh)
                self.assertEqual(ce._prerequisites(earlier, 2004)["year"], "applied")
                self.assertNotEqual(ce.status(earlier), "foreign")
                self.assertEqual(season.group_status(earlier, "year", year=2004), "applied")
                self.assertEqual(season.rookie_birth_state(earlier), "legacy")
                moved, _ = season.upgrade_rookie_birth(earlier)
                self.assertEqual(moved, fresh)
        self.assertEqual(season.rookie_birth_state(retail), "retail")
        self.assertEqual(ce._prerequisites(retail, 2004)["year"], "retail")


class ClassTemplatesInPlaceTests(unittest.TestCase):
    """Review S2: the in-place routes write the widened templates into the disc's main roster, as a full build's rookie
    faces step does, so an updated disc's class generator has the templates the merged roll was tuned with."""

    def test_v09_update_templates_equal_a_full_build(self):
        import os
        from pathlib import Path
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_roster_records as rr
        disc = Path(os.environ.get("NFL2K5_V09_XISO", "") or "missing")
        if not disc.is_file():
            self.skipTest("the released v0.9 disc is absent (NFL2K5_V09_XISO)")
        try:
            from tests.nfl2k5_supersim_draft_fixture import retail_roster
            body = retail_roster()
        except unittest.SkipTest:
            raise
        with rr._outer_image()(disc) as archive:
            entry = archive.entries[rf.MAIN_ROST_OUTER]
            v09 = archive.read(entry.virtual_offset, entry.size)
        full = b"ROST" + struct.pack("<I", len(body)) + bytes(24) + body
        full = mod_build._class_templates_roster(full)               # what a full build's apply_templates writes
        updated = mod_build._class_templates_roster(v09)              # what the in-place routes write
        self.assertNotEqual(updated, v09, "the released disc carries the b779-rf3 templates")
        self.assertEqual(self._region(updated), self._region(full))
        self.assertEqual(rf.template_writes(updated), [])

    @staticmethod
    def _region(raw: bytes) -> list[tuple[int, str, int]]:
        from mod_editor.core import nfl2k5_roster_records as rr
        doc = rr.RosterDocument(raw[rf.ROST_WRAPPER:rf.ROST_WRAPPER + struct.unpack_from("<I", raw, 4)[0]])
        sec = doc.by_pool("secondary")
        order = list(rr.RATING_BYTE_ORDER)
        return [(row["index"], name, raw[rf.ROST_WRAPPER + sec[row["index"]].offset + 0x36 + order.index(name)])
                for row in rf.load_templates()["templates"] for name in row["ratings"]]

    def test_every_in_place_route_writes_them(self):
        import inspect
        from mod_editor.core import mod_build
        for route in (mod_build._update_v09_disc, mod_build._edit_installed_sim_qb, mod_build._edit_installed_gadget):
            with self.subTest(route=route.__name__):
                self.assertIn("_apply_class_templates_in_place(", inspect.getsource(route))


class TemplateFitTests(unittest.TestCase):
    """The refitted templates against the real 2026 class's top (rank-matched; out of the lane's la_template_fit)."""

    def test_the_best_rookies_can_start(self):
        doc = rf.load_templates()
        by = {r["index"]: r["ratings"] for r in doc["templates"]}
        self.assertIn("b81 league-aging", doc["note"])
        for pos in ("K", "P"):                         # the economy lane's supply; widened with the rest at the merge
            for k in range(4):
                self.assertTrue(by[4 * rf.POSITIONS.index(pos) + k])
        for row in doc["templates"]:
            self.assertTrue(all(0 <= v <= 99 for v in row["ratings"].values()))


if __name__ == "__main__":
    unittest.main()
