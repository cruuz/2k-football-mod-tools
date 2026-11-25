"""CPU team building (beta 81, owner nfl2k5_team_building; the team-building lane's DESIGN.txt and the coordinator's
rulings of 2026-11-25): the draft's need order and the free-agent wishes judged by the shared team-need rule.

Every class fails on c4406481b: there is no nfl2k5_team_building owner, code template or window proof there.

- Windows: the thirty code windows are proven unreferenced on the retail executable (tools/team_building/dead_code.py:
  references, digests, return + padding, decode synchronisation, entry/TLS), clear of the reservation inventory and
  of the economy's windows; the template reproduces from runtime.c (when gcc is present); its tables equal the draft
  AI's VALUE and the economy's aging line.
- Oracle: the Python mirror of runtime.c on built rosters: holes first by key, premium 3:2, QB in, a position drafted
  this draft out, a development asset out in rounds 1 and 2 only, aging read in, a person's club keeps the retail order.
- Owner (TEAM_BUILDING_STANDARD_XBE, a standard executable with the draft AI and the economy; else skip): install,
  Retail, foreign, needs, and the draft AI reading applied with the branches retargeted.
- Image (TEAM_BUILDING_IMAGE, a kept .b81mem.gz, and TEAM_BUILDING_IMAGE_XBE, its executable; else skip): the code runs
  natively in Unicorn on a real league: the native view equals the oracle's for every club, tb_order equals the
  oracle's order for every CPU club and round, a club a person runs keeps the retail order byte for byte, hole clubs
  get their hole first where the retail need had it lower, and the wish routine wishes for a hole first.
Fixtures come from the environment only (no private paths in the repo).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import unittest

from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, XBE as RETAIL_XBE

ROOT = Path(__file__).resolve().parents[2]
STANDARD_XBE = os.environ.get("TEAM_BUILDING_STANDARD_XBE", "")
IMAGE = os.environ.get("TEAM_BUILDING_IMAGE", "")
IMAGE_XBE = os.environ.get("TEAM_BUILDING_IMAGE_XBE", "")
NAMES = "QB K P WR CB FS SS HB FB TE OLB LB C G T DT EDGE".split()
P = {n: i for i, n in enumerate(NAMES)}


def _tb():
    from mod_editor.core import nfl2k5_team_building as tb
    return tb


def _with_economy_9(payload: bytes) -> bytes:
    """The franchise economy at revision 9 (a revision-8 or -7 executable upgrades in place, as the Studio does)."""
    from mod_editor.core import nfl2k5_franchise_economy as economy
    return economy.apply(payload)[0] if economy.status(payload) == "legacy" else payload


def _fixture(path):
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("TEAM_BUILDING_* fixture not set or absent")
    return Path(path).read_bytes()


class Windows(unittest.TestCase):
    def test_proof_on_retail(self):
        if not RETAIL_XBE.is_file():
            self.skipTest("retail extraction required")
        from tools.team_building import dead_code
        report = dead_code.verify(RETAIL_XBE.read_bytes())
        self.assertEqual(len(report["windows"]), 29)
        self.assertEqual(report["references"], 0)
        self.assertEqual(dead_code.reservations_clear(), [])

    def test_windows_clear_of_the_economy_and_each_other(self):
        from tools.franchise_economy import dead_code as economy
        from tools.team_building.dead_code import WINDOWS
        spans = sorted((va, va + n) for va, (n, _) in WINDOWS.items())
        self.assertTrue(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])))
        for lo, hi in spans:
            for elo, (en, _) in economy.WINDOWS.items():
                self.assertFalse(lo < elo + en and elo < hi, hex(lo))

    def test_template_matches_the_proof_and_the_inputs(self):
        from mod_editor.core import nfl2k5_draft_ai as draft
        from mod_editor.core import nfl2k5_team_building_code as code
        from tools.team_building.dead_code import WINDOWS
        self.assertEqual({va: len(b) for va, b in code.WINDOWS.items()}, {va: n for va, (n, _) in WINDOWS.items()})
        self.assertEqual(code.RETAIL_SHA256, {va: d for va, (_, d) in WINDOWS.items()})
        self.assertEqual(code.INPUTS["value_x100"], [round(draft.VALUE[p] * 100) for p in draft.POSITIONS])
        data = json.loads((ROOT / "data/nfl2k5_franchise_economy.json").read_text())
        self.assertEqual(code.INPUTS["decline_after"], data["model"]["decline_after_years_pro"])
        from mod_editor.core import nfl2k5_franchise_economy_code as economy
        self.assertEqual(economy.SYMBOLS["economy_room_for_signing"], 0x2D82F0)   # the economy's pinned entry
        self.assertIn("tb_order", code.SYMBOLS)
        self.assertIn("tb_wish_entry", code.SYMBOLS)

    @unittest.skipUnless(shutil.which("gcc") and shutil.which("ld") and shutil.which("objcopy"), "GNU i386 tools")
    def test_template_reproduces(self):
        from tools.team_building import assemble
        self.assertEqual(assemble.generate(), assemble.TARGET.read_text())


def man(pos, points, row=0, pro=5, present=True, ref=0):
    from mod_editor.core.nfl2k5_team_building import Man
    return Man(ref, P[pos], points, row, pro, present)


BASE = (("QB", 85, 0), ("WR", 86, 0), ("WR", 84, 1), ("WR", 80, 2), ("T", 82, 0), ("T", 81, 1), ("EDGE", 80, 0),
        ("EDGE", 79, 1), ("CB", 82, 0), ("CB", 80, 1), ("DT", 78, 0), ("DT", 77, 1), ("TE", 80, 0), ("HB", 85, 0),
        ("FS", 80, 0), ("SS", 80, 0), ("LB", 82, 0), ("LB", 81, 1), ("C", 85, 0), ("G", 84, 0), ("G", 83, 1))


def club(spread=0):
    """An average club; `spread` moves every starter (the 31 others use -8..+7 so a club at 0 sits mid-league)."""
    return [man(pos, pts + spread, row) for pos, pts, row in BASE]


def league(own_roster):
    """31 clubs spread around the average and one under test (index 0)."""
    return [own_roster] + [club(i % 16 - 8) for i in range(31)]


RETAIL = [16, 7, 14, 3, 4, 6, 9, 11, 13, 5, 15, 0, 8, 12, 1, 2, 10]      # the round-1 board (picks 6-32), OLB last


class Oracle(unittest.TestCase):
    def setUp(self):
        self.tb = _tb()
        self.decline = [12, 14, 14, 7, 7, 8, 8, 5, 8, 8, 7, 7, 10, 10, 10, 9, 8]

    def _order(self, roster, rnd=0, human=False):
        v = self.tb.view(league(roster), 0)
        return self.tb.order(RETAIL, v, rnd, self.decline, human=human)

    def average(self, **change):
        roster = club(0)
        for pos, pts in change.items():
            roster = [m for m in roster if m.pos != P[pos]] + [man(pos, pts[0], 0), man(pos, pts[1], 1)] \
                if isinstance(pts, tuple) else [m for m in roster if m.pos != P[pos]] + [man(pos, pts)]
        return roster

    def test_no_hole_keeps_the_retail_order(self):
        self.assertEqual(self._order(self.average()), RETAIL)

    def test_a_wr_hole_goes_first_every_round(self):
        roster = self.average(WR=(85, 70))
        for rnd in range(7):
            self.assertEqual(self._order(roster, rnd)[0], P["WR"], rnd)

    def test_premium_holes_before_a_deeper_non_premium_hole(self):
        roster = self.average(WR=(86, 75), TE=66)                 # WR2 under the line; TE further under
        order = self._order(roster)
        self.assertLess(order.index(P["WR"]), order.index(P["TE"]))

    def test_quarterback_is_in_the_draft_need(self):
        self.assertEqual(self._order(self.average(QB=70))[0], P["QB"])

    def test_a_position_drafted_this_draft_is_not_a_hole(self):
        roster = self.average(WR=(85, 70)) + [man("WR", 72, 3, pro=1)]
        self.assertEqual(self._order(roster, 2), RETAIL)

    def test_a_development_asset_waits_until_round_three(self):
        roster = self.average(WR=(86, 70)) + [man("WR", 86, 4, pro=2)]    # above the WR median starter (85)
        self.assertEqual(self._order(roster, 0)[0], RETAIL[0])
        self.assertEqual(self._order(roster, 2)[0], P["WR"])

    def test_aging_reads_the_next_season(self):
        base = [m for m in self.average() if m.pos != P["WR"]]
        old = base + [man("WR", 86, 0), man("WR", 81, 1, pro=11)]      # 81 at eleven years pro reads as 77 next season
        young = base + [man("WR", 86, 0), man("WR", 81, 1, pro=4)]
        self.assertEqual(self._order(old)[0], P["WR"])
        self.assertEqual(self._order(young), RETAIL)

    def test_a_person_keeps_the_retail_order(self):
        self.assertEqual(self._order(self.average(WR=(85, 60)), human=True), RETAIL)

    def test_fullback_kicker_punter_never_holes(self):
        roster = [m for m in self.average() if m.pos not in (P["FB"], P["K"], P["P"])]
        self.assertEqual(self._order(roster), RETAIL)

    def test_new_score_tiers(self):
        v = self.tb.view(league(self.average(WR=(86, 70))), 0)
        hole = self.tb.new_score(v, P["WR"], 80, 0)
        deficit = self.tb.new_score(v, P["CB"], 0, 1)
        upgrade = self.tb.new_score(v, P["CB"], 90, 0)
        nothing = self.tb.new_score(v, P["CB"], 81, 0)           # CB's weakest need seat is 80: 81 is not 3 better
        self.assertGreater(hole, 100000)
        self.assertEqual(deficit, 51200)
        self.assertTrue(0 < upgrade < 50000)
        self.assertEqual(nothing, -1)
        self.assertEqual(self.tb.new_score(v, P["WR"], 72, 0), -1)  # not 3 points better: no wish even at a hole


class Owner(unittest.TestCase):
    def setUp(self):
        self.payload = _with_economy_9(_fixture(STANDARD_XBE))
        self.tb = _tb()

    def test_economy_revision_9(self):
        """A revision-8 economy reads legacy and upgrades in place by its one new window; team building needs it."""
        from mod_editor.core import nfl2k5_franchise_economy as economy
        old = _fixture(STANDARD_XBE)
        self.assertEqual(economy.REVISION, 9)
        if economy.status(old) == "legacy":
            self.assertFalse(self.tb.needs_met(old))
            with self.assertRaises(self.tb.TeamBuildingError):
                self.tb.apply(old)
            upgraded, receipt = economy.apply(old)
            changed = [i for i, (a, b) in enumerate(zip(old, upgraded)) if a != b]
            window = self.tb._offset(old, economy.ROOM_FOR_SIGNING_WINDOW)
            self.assertTrue(all(window <= i < window + 110 or i < 0x1000 for i in changed))
        self.assertEqual(economy.status(self.payload), "applied")
        self.assertTrue(self.tb.needs_met(self.payload))

    def test_install_restore_and_the_draft_ai(self):
        from mod_editor.core import nfl2k5_draft_ai as draft
        tb = self.tb
        self.assertEqual(tb.status(self.payload), "retail")
        self.assertTrue(tb.needs_met(self.payload))
        patched, receipt = tb.apply(self.payload)
        self.assertEqual(tb.status(patched), "applied")
        self.assertEqual(draft.status(patched), "applied")
        self.assertEqual(tb.apply(patched)[0], patched)
        e = tb.entries()
        self.assertEqual(tb._rel(patched, tb.HEAD_CALL_VA, 0xE8), e["order"])
        self.assertEqual(tb._rel(patched, tb.WISH_JUMP_VA, 0xE9), e["wish"])
        self.assertEqual(tb.as_draft_ai(patched)[tb._offset(patched, tb.HEAD_CALL_VA):][:5],
                         self.payload[tb._offset(self.payload, tb.HEAD_CALL_VA):][:5])
        if RETAIL_XBE.is_file():
            restored, _ = tb.restore(patched, RETAIL_XBE.read_bytes())
            self.assertEqual(restored, self.payload)
        self.assertLessEqual(receipt["code_bytes"], 3727)

    def test_foreign_and_needs(self):
        tb = self.tb
        patched, _ = tb.apply(self.payload)
        broken = bytearray(patched)
        off = tb._offset(patched, 0x2CE070)
        broken[off] ^= 0xFF
        self.assertEqual(tb.status(bytes(broken)), "foreign")
        with self.assertRaises(tb.TeamBuildingError):
            tb.apply(bytes(broken))
        if RETAIL_XBE.is_file():
            retail = RETAIL_XBE.read_bytes()
            self.assertEqual(tb.status(retail), "retail")
            self.assertFalse(tb.needs_met(retail))
            with self.assertRaises(tb.TeamBuildingError):
                tb.apply(retail)


class Studio(unittest.TestCase):
    """The option: plan field, presets, settings key, availability row, wording, and the build step itself."""

    def test_plan_presets_and_settings(self):
        from mod_editor.core import mod_build, nfl2k5_build_settings as settings
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).team_building, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["team_building"], name == "softdrink_experimental", name)
        self.assertIn("team_building", settings.FEATURE_KEYS)
        self.assertIn(("nfl2k5_team_building", "CPU team building"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        tb = _tb()
        self.assertNotIn("\u2014", tb.HELP_TEXT + tb.BUILD_CAPTION)
        for path in ("mod_editor/core/nfl2k5_team_building.py", "tools/team_building/runtime.c",
                     "tests/mod_editor/test_b81_team_building.py"):
            self.assertNotIn("/" + "home/", (ROOT / path).read_text(encoding="utf-8"), path)

    def test_build_step_installs_or_leaves_out_with_a_note(self):
        import tempfile
        from mod_editor.core import mod_build
        payload = _fixture(STANDARD_XBE)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "default.xbe"
            plan = mod_build.BuildPlan(Path("source.iso"), target, team_building=True)
            target.write_bytes(payload)
            receipt = {"steps": [], "result": {}}
            mod_build._apply_team_building(plan, target, receipt, lambda *a: None)
            if not _tb().needs_met(payload):              # a revision-8 economy: left out with the note, nothing written
                self.assertEqual(receipt["result"]["team_building"], "left_out")
                self.assertIn(mod_build.TEAM_BUILDING_LEFT_OUT, receipt["user_notes"])
                self.assertEqual(target.read_bytes(), payload)
            target.write_bytes(_with_economy_9(payload))
            receipt = {"steps": [], "result": {}}
            mod_build._apply_team_building(plan, target, receipt, lambda *a: None)
            self.assertEqual(receipt["result"]["team_building"], "applied")
            self.assertEqual(_tb().status(target.read_bytes()), "applied")
            before = target.read_bytes()
            off = mod_build.BuildPlan(Path("source.iso"), target, team_building=False)
            mod_build._apply_team_building(off, target, {"steps": [], "result": {}}, lambda *a: None)
            self.assertEqual(target.read_bytes(), before)


def code_economy_cap():
    from mod_editor.core import nfl2k5_franchise_economy_code as economy
    return economy.SYMBOLS["economy_cap"]


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class Image(unittest.TestCase):
    """The code runs natively on a kept league image (the executable it was made with plus this owner)."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        from tools import franchise_invariants as fi
        from mod_editor.core import nfl2k5_team_building_code as code
        tb = _tb()
        xbe, image = _with_economy_9(_fixture(IMAGE_XBE)), IMAGE
        if not image or not Path(image).is_file():
            raise unittest.SkipTest("TEAM_BUILDING_IMAGE not set or absent")
        cls.tb, cls.code = tb, code
        original = _fixture(IMAGE_XBE)
        patched, _ = tb.apply(xbe)
        cls.m = m = Machine(patched, trace_writes=False)
        for lo, data in fi.load_memory(Path(image)).regions:
            if lo < 0x3000000:
                m.uc.mem_write(lo, data)
        # The image holds the code it was made with: write back every byte the economy upgrade and this owner changed.
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        new, old = XbeImage(patched), XbeImage(original)
        for section in new.sections:
            if not section.raw_size or not section.start < 0x420000:
                continue
            a, b = old.read(section.start, section.raw_size), new.read(section.start, section.raw_size)
            i = 0
            while i < len(b):
                if a[i] != b[i]:
                    j = i
                    while j < len(b) and a[j] != b[j]:
                        j += 1
                    m.uc.mem_write(section.start + i, b[i:j])
                    i = j
                else:
                    i += 1
        cls.PROBE = 0x3200000
        m.uc.mem_map(cls.PROBE, 0x1000)
        m.uc.ctl_flush_tb()
        root = m.get(0xB72918)
        cls.teams = [m.get(root + 0x1C) + 500 * i for i in range(32)]
        cls.user = [i for i in range(32) if m.call(0x13EC30, ecx=cls.teams[i], budget=100000)]
        cls._points = {}
        cls.league = [[cls._man(m.get(t + 4 * k)) for k in range(m.uc.mem_read(t + 0x11C, 1)[0])] for t in cls.teams]

    @classmethod
    def _rating(cls, p, flag):
        m = cls.m
        code = (b"\xb9" + struct.pack("<I", p) + b"\xba" + struct.pack("<I", flag) + b"\xb8" +
                struct.pack("<I", 0x246D80) + b"\xff\xd0\xd9\x1d" + struct.pack("<I", cls.PROBE + 0x800) + b"\xc3")
        m.uc.mem_write(cls.PROBE, code)
        m.uc.ctl_flush_tb()
        m.call(cls.PROBE, budget=2_000_000)
        return m.get(cls.PROBE + 0x800)

    @classmethod
    def _man(cls, p):
        from mod_editor.core import nfl2k5_team_need as tn
        rec = bytes(cls.m.uc.mem_read(p, 0x54))
        if p not in cls._points:
            cls._points[p] = tn.points(cls._rating(p, 0))
        return cls.tb.Man(p, rec[0x35], cls._points[p], tn.row(rec), rec[0x25] & 31, tn.present(rec))

    def _native_order(self, fn, club, rnd, pick=15):
        need = 0x3000800
        self.m.uc.mem_write(need, bytes(68))
        self.m.put(0xE3C0A8, rnd)
        self.m.call(fn, ecx=self.teams[club], edx=rnd, args=(pick, need), budget=200_000_000)
        return list(struct.unpack("<17i", bytes(self.m.uc.mem_read(need, 68))))

    def test_native_view_equals_the_oracle(self):
        tb, m = self.tb, self.m
        x = 0x3001000
        for club in (0, 9, 14, 21):
            m.call(self.code.SYMBOLS["tb_view"], args=(x, self.teams[club]), budget=200_000_000)
            raw = bytes(m.uc.mem_read(x, 17 * 5 + 17 * 64))
            v = tb.view(self.league, club)
            self.assertEqual(list(raw[0:17]), v.weak, club)
            self.assertEqual(list(raw[17:34]), v.wpro, club)
            self.assertEqual(list(raw[34:51]), v.young, club)
            self.assertEqual(list(raw[51:68]), v.drafted, club)
            for pool in range(17):
                n = raw[68 + pool]
                self.assertEqual(list(raw[85 + 64 * pool: 85 + 64 * pool + n]), v.scale[pool], (club, pool))

    def test_native_order_equals_the_oracle_for_every_cpu_club(self):
        tb, decline = self.tb, self.tb.decline_after()
        holes_first = 0
        for club in range(32):
            human = club in self.user
            v = tb.view(self.league, club)
            for rnd in (0, 1, 3, 6):
                retail = self._native_order(0x31DEA0, club, rnd)
                ours = self._native_order(self.code.SYMBOLS["tb_order"], club, rnd)
                self.assertEqual(ours, tb.order(retail, v, rnd, decline, human=human), (club, rnd))
                if human:
                    self.assertEqual(ours, retail, club)
                elif ours[0] != retail[0]:
                    holes_first += 1
        self.assertGreater(holes_first, 0)     # fails on the retail need (it never puts a hole first by quality)

    def test_hole_first_where_the_retail_need_had_it_lower(self):
        tb, decline = self.tb, self.tb.decline_after()
        moved = []
        for club in range(32):
            if club in self.user:
                continue
            v = tb.view(self.league, club)
            holes = [p for p in range(17) if p != 10 and tb.key(v, tb.tn.POOL[p], 0, decline) < 255]
            if not holes:
                continue
            retail = self._native_order(0x31DEA0, club, 0)
            ours = self._native_order(self.code.SYMBOLS["tb_order"], club, 0)
            self.assertIn(ours[0], holes, club)
            if retail.index(ours[0]) > 0:
                moved.append((club, NAMES[ours[0]], retail.index(ours[0])))
        self.assertTrue(moved)

    def test_wishes_go_to_holes_first(self):
        """Hole scores carry no jitter: the routine tries the holes whose affordable 3-point upgrade scores above 100000
        first, in score order, before any other position (the native wish may still refuse one)."""
        m, code = self.m, self.code
        root = m.get(0xB72918)
        count, table = m.get(root + 0x38), m.get(root + 0x3C)
        best, top = [0] * 17, [-1.0] * 17
        for i in range(count):
            p = m.get(table + 4 * i)
            pos = m.uc.mem_read(p + 0x35, 1)[0]
            if pos < 17:
                r = struct.unpack("<f", struct.pack("<I", self._rating(p, 1)))[0]
                if r > top[pos]:
                    top[pos], best[pos] = r, p
        m.uc.mem_write(0x3001000, struct.pack("<17I", *best))
        view, target = 0x3002000, 0x3001100
        clubs_with_holes = 0
        for club in range(32):
            if club in self.user:
                continue
            team = self.teams[club]
            m.call(code.SYMBOLS["tb_view"], args=(view, team), budget=200_000_000)
            room = m.call(0x2D82F0, ecx=team, budget=50_000_000)       # economy_room_for_signing (revision 9)
            cap = m.call(code_economy_cap(), ecx=team, edx=1, args=(0,), budget=50_000_000)
            self.assertEqual(room, (cap - m.get(team + 0x124) - 10) & 0xFFFFFFFF, club)
            room = room - (1 << 32) if room >= 1 << 31 else room
            holes = []
            for p in range(17):
                score = m.call(code.SYMBOLS["tb_score"], args=(view, team, p, best[p], room & 0xFFFFFFFF, target),
                               budget=200_000_000)
                score = score - (1 << 32) if score >= 1 << 31 else score
                if score > 100000:
                    holes.append((score, m.get(target)))
            tried = []
            hook = m.uc.hook_add(__import__("unicorn").UC_HOOK_CODE, lambda uc, a, n, _: tried.append(m.get(m.reg("ESP") + 4)),
                                 begin=code.SYMBOLS["tb_wish"], end=code.SYMBOLS["tb_wish"])
            m.call(code.SYMBOLS["tb_wishes"], ecx=team, edx=0x3001000, args=(0,), budget=400_000_000)
            m.uc.hook_del(hook)
            if holes:
                clubs_with_holes += 1
                wanted = [t for _s, t in sorted(holes, key=lambda h: -h[0])]
                self.assertEqual(tried[:min(len(wanted), len(tried))], wanted[:len(tried)], club)
                self.assertGreaterEqual(len(tried), min(4, len(wanted)), club)
        self.assertGreater(clubs_with_holes, 0)

    def _bids(self, team):
        out = []
        for i in range(100):
            s = self.m.call(0x322840, ecx=i, budget=100000)
            if self.m.call(0x322BA0, ecx=s, budget=100000) and self.m.get(s + 4) == team:
                out.append(self.m.get(s))
        return out


if __name__ == "__main__":
    unittest.main()
