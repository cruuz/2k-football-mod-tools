"""T10 (beta 81 qb34 DESIGN 4.4): the franchise invariant validator, tools/franchise_invariants.py.

Private inputs (never in git; each test skips when its file is absent, and every file is pinned by sha256):
- NFL2K5_B81_OWNERSHIP_FIXTURES (Codex's beta81 tree): the signed 61001 duplicate-ownership save and its memory image,
  and a clean signed standard closing save (phase1 standard 2501, the harness reproduces it byte for byte).
- NFL2K5_B81_QB34_FIXTURES (default: the qb34 lane's evidence/validator folder): the released v0.9 opening, signed
  natively on the released v0.9 executable and roster (qb34/harness/make_opening_save.py), and its memory image.
- NFL2K5_SAVE_FIXTURES: the retail franchise opening save f0.
- NFL2K5_B81_QB34_TRADE_XBE (default: qb34 evidence/p2a-replay/p2-candidate-9edd1353.xbe): the executable the week 10
  kick-off image ran on; the trade tests run its pending scan 0x2BC900 under Unicorn for a genuine before/after pair.
Each hand-broken copy changes the clean save in one way and must fail exactly the invariant it breaks; where the
game would have recounted the payroll after such a change, the copy stores the recount too (so I3 stays true).
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import pickle
import shutil
import struct
import tempfile
import unittest

from tools import franchise_invariants as fi

OWNERSHIP = os.environ.get("NFL2K5_B81_OWNERSHIP_FIXTURES")
QB34 = Path(os.environ.get("NFL2K5_B81_QB34_FIXTURES",
                           "/home/noah/2k-worktrees/.b77-scratch/b81/qb34/evidence/validator"))
SAVES = Path(os.environ.get("NFL2K5_SAVE_FIXTURES", str(Path.home() / "Desktop/2K5-8 Editors/save_fixtures")))
QUALIFICATION = "qb-system/evidence/quarterback-spread-review/holdout-37-310/qualification"
DUPLICATE_61001 = "baa9c0d2da0abb057c4f45c885f71d8798c138430c4f3898fd89174ec6c8e751"
CLEAN_CLOSING = "337b026e1798e8b74003ee97bcc57badf285aa0c63d428a6951a56206e2e1fcf"
V09_OPENING = "5336bf76e7a95a8acfcb6be0ffc5d2b737d5c0efb22894af0818815c3f151906"
RETAIL_F0 = "56926604e438bd47f1f94edf844a0ecd00d5a382a647526baec396ead5f1b1b8"
NO_QB_IMAGE = "fde2c34a02be6d219cf3b2291b0a9ffbe537771ee2dfa79cdc1a06cb479e906a"
MINNESOTA_KICKOFF = "1f725ff50fe01e920bd5043892b597901c8ce0665de8f56ab839522d1bef1b4e"
PLAYOFF_IMAGE = "7a3ac0eca31be817a3a29b9b0b800082a507dcd2e1a80d43de108350f4c001aa"
SECOND_SEASON = "2a7fa4ccef31f7f58872248b32e8a4b2aa2f1555e7c739f8b986f4501be33638"
DALLAS_SIGNED = "529bdac68b109bc833a2cfa81e63d7d0f2b8959cb993da03402206c06cb4aac6"
# the executable the kick-off image ran on (it carries the ownership owner at 0x2BC688); private, never in git
TRADE_XBE = Path(os.environ.get("NFL2K5_B81_QB34_TRADE_XBE", "/home/noah/2k-worktrees/.b77-scratch/b81/qb34/evidence/"
                                "p2a-replay/p2-candidate-9edd1353.xbe"))
TRADE_XBE_SHA = "9edd1353bedfbca6b4ce35faa2acc3cb68b8a74521d3313e3b1873e6b12c7c3d"
# RAM the trade tests read and edit (qb34 evidence/trades/RISKS.md), named here rather than taken from the tool under test
TRADE_OPTION, DEADLINE_BYTE, PICK_ROW1 = 0xE60124, 0x5151C5, 0xE3C0B4     # option word; stage_table[8].byte5; pick row 1
MIDWEEK = ["I8.boundary"]           # a state inside the advance (the kick-off hook), where the page's record may sit


def pinned(path: Path, digest: str) -> bytes:
    if not path.is_file():
        raise unittest.SkipTest(f"private fixture absent: {path}")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise unittest.SkipTest(f"private fixture pin differs: {path}")
    return raw


def owned(relative: str) -> Path:
    if not OWNERSHIP:
        raise unittest.SkipTest("NFL2K5_B81_OWNERSHIP_FIXTURES is not set")
    return Path(OWNERSHIP) / relative


def failing(report) -> set[str]:
    return {v["invariant"] for v in report.violations if v["severity"] == fi.FAIL}


def warned(report) -> set[str]:
    return {v["invariant"] for v in report.violations if v["severity"] == fi.WARN}


class Breaker:
    """Hand edits of a franchise save in its own (relative pointer) form."""

    def __init__(self, payload: bytes):
        from mod_editor.core import nfl2k5_franchise_save as fs
        self.fs = fs
        self.save = fs.FranchiseSave(payload)
        self.buf = self.save.buffer
        self.count, self.table = self.save.player_table
        self.view = fi.view_from_save(payload)

    def payload(self) -> bytes:
        return bytes(self.buf)

    def off(self, i):
        return self.table + fi.PLAYER_SIZE * i

    def word(self, i, at):
        return struct.unpack_from("<I", self.buf, self.off(i) + at)[0]

    def set_word(self, i, at, value):
        struct.pack_into("<I", self.buf, self.off(i) + at, value)

    def position(self, i):
        return self.buf[self.off(i) + 0x35]

    def row(self, i):
        return (struct.unpack_from("<H", self.buf, self.off(i) + 0x28)[0] >> 10) & 7

    def set_row(self, i, row):
        at = self.off(i) + 0x28
        value = struct.unpack_from("<H", self.buf, at)[0]
        struct.pack_into("<H", self.buf, at, (value & ~(7 << 10)) | (row << 10))

    def repack(self, club, active, reserves):
        from mod_editor.core import nfl2k5_practice_squad as ps
        base = self.save.team_offset(club)
        raw = bytes(self.buf[base:base + fi.TEAM_SIZE])
        new = ps.repack_team(raw, active, reserves, team_offset=base, player_pool_offset=self.table,
                             player_count=self.count, mark=raw[fi.PS_MARKER] == fi.PS_MARK)
        self.buf[base:base + fi.TEAM_SIZE] = new

    def ir_clubs(self):
        from mod_editor.core import nfl2k5_injured_reserve_save as irsave
        at = self.save.front_office_block + self.fs.F_INJURED_RESERVE
        return irsave.decode(bytes(self.buf[at:at + irsave.CELLS * 4]))

    def write_ir(self, clubs, returns, extension):
        from mod_editor.core import nfl2k5_injured_reserve_save as irsave
        at = self.save.front_office_block + self.fs.F_INJURED_RESERVE
        self.buf[at:at + irsave.CELLS * 4] = irsave.encode(clubs, returns, extension=extension)

    def recount(self, club):
        """The game's payroll recount (0xC3F00 + the IR charge) stored at +0x124, as each week's step 7 does."""
        view = fi.view_from_save(self.payload())
        c = view.clubs[club]
        total = sum(fi.player_salary(view.record(i)) for i in c.active)
        total += sum(fi.player_salary(view.record(i), active=False) for i, _ in view.ir.clubs[club])
        struct.pack_into("<I", self.buf, self.save.team_offset(club) + fi.PAYROLL, total)

    def report(self):
        return fi.check(fi.view_from_save(self.payload()))


class OfflineTests(unittest.TestCase):
    """No private file needed."""

    def test_memory_image_round_trip_and_reads(self):
        regions = [(0x10000, bytes(range(256)) * 16), (0x2000000, b"\x11\x22\x33\x44" * 8)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.b81mem.gz"
            fi.dump_memory(path, regions)
            memory = fi.load_memory(path)
        self.assertEqual(memory.read(0x10000 + 5, 3), bytes([5, 6, 7]))
        self.assertEqual(memory.read(0x2000004, 4), b"\x11\x22\x33\x44")
        with self.assertRaises(ValueError):
            memory.read(0x2000000 + 30, 4)
        self.assertEqual(list(memory.find(b"\x22\x33", 0x2000000, 0x2000010)), [0x2000001, 0x2000005, 0x2000009, 0x200000D])

    def test_a_pickled_image_that_names_code_is_refused(self):
        class Evil:
            def __reduce__(self):
                return (os.getcwd, ())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "native-memory.pkl.gz"
            path.write_bytes(gzip.compress(pickle.dumps(([(0, 3)], [Evil()]))))
            with self.assertRaises(pickle.UnpicklingError):
                fi.load_memory(path)
            plain = Path(tmp) / "plain.pkl.gz"
            plain.write_bytes(gzip.compress(pickle.dumps(([(0x1000, 0x1003)], [b"abcd"]))))
            self.assertEqual(fi.load_memory(plain).read(0x1001, 2), b"bc")


class SignedSaveTests(unittest.TestCase):
    def test_61001_duplicate_ownership_fails_I2(self):
        folder = owned(f"{QUALIFICATION}/runs/pair-causal-e/61001/signed/2026")
        pinned(folder / "SAVEGAME.DAT", DUPLICATE_61001)
        view, facts = fi.load_target(folder)
        report = fi.check(view)
        self.assertEqual(facts["signature"], "verified")
        self.assertIn("I2", failing(report))
        rows = [v for v in report.violations if v["invariant"] == "I2"]
        self.assertEqual([(r["player_index"], r["player_name"]) for r in rows], [(914, "Vernon Broughton")])
        self.assertEqual(rows[0]["values"]["holders"], [{"list": "active", "club": 16}, {"list": "ir", "club": 26}])
        self.assertEqual(report.status(), 2)

    def test_61001_memory_image_fails_I2_and_reads_like_its_save(self):
        folder = owned(f"{QUALIFICATION}/runs/pair-causal-e/61001/signed/2026")
        pinned(folder / "SAVEGAME.DAT", DUPLICATE_61001)
        image = folder / "native-memory.pkl.gz"
        if not image.is_file():
            self.skipTest("61001 memory image absent")
        memory = fi.load_memory(image)
        view = fi.view_from_memory(memory.read, search=lambda n: memory.find(n, 0x10000, 0x2000000))
        report = fi.check(view)
        self.assertEqual(view.ir.kind, "store")
        self.assertIn("I2", failing(report))
        self.assertEqual(failing(report), failing(fi.check(fi.load_target(folder)[0])))
        self.assert_same_league(fi.load_target(folder)[0], view)

    def assert_same_league(self, save, memory):
        for a, b in zip(save.clubs, memory.clubs):
            self.assertEqual((a.name, a.count, a.active, a.practice, a.payroll, a.human),
                             (b.name, b.count, b.active, b.practice, b.payroll, b.human), a.index)
        for field in ("mode", "stage", "week", "year_index", "player_count", "cpu_manages_depth", "auto_sign_cut",
                      "salary_cap", "free_agents", "ledger_cursor", "ledger_kinds", "pick_owners", "ledger_rows",
                      "trade_option", "deadline_week"):
            self.assertEqual(getattr(save, field), getattr(memory, field), field)
        self.assertEqual([sorted(r) for r in save.ir.clubs], [sorted(r) for r in memory.ir.clubs])
        self.assertEqual([o.key() for o in save.board], [o.key() for o in memory.board])
        pointer_fields = set(range(0, 4)) | set(range(0x10, 0x18)) | set(range(0x2C, 0x30))   # relative vs absolute
        for i in range(0, save.player_count, 7):
            a, b = save.record(i), memory.record(i)
            self.assertEqual([a[k] for k in range(84) if k not in pointer_fields],
                             [b[k] for k in range(84) if k not in pointer_fields], i)
            self.assertEqual(save.name(i), memory.name(i))

    def test_released_v09_opening_and_its_memory_image_pass(self):
        folder = QB34 / "v09-opening-2501/signed"
        pinned(folder / "SAVEGAME.DAT", V09_OPENING)
        view, facts = fi.load_target(folder)
        report = fi.check(view)
        self.assertEqual(facts["signature"], "verified")
        self.assertEqual((view.stage, view.week), (8, 0))
        self.assertEqual(report.violations, [])
        self.assertEqual(report.status(strict=True), 0)
        image = folder.parent / "memory.b81mem.gz"
        if image.is_file():
            memory = fi.load_memory(image)
            live = fi.view_from_memory(memory.read, search=lambda n: memory.find(n, 0x10000, 0x2000000))
            self.assertEqual(fi.check(live).violations, [])
            self.assert_same_league(view, live)

    def test_the_p0_no_quarterback_image_fails_I11(self):
        """P0 shadow root 2508, 2027 week 18: Dallas's three quarterbacks all on IR (memory image the harness kept)."""
        path = QB34 / "no-qb-2508-2027-w18.b81mem.gz"
        pinned(path, NO_QB_IMAGE)
        memory = fi.load_memory(path)
        view = fi.view_from_memory(memory.read, search=lambda n: memory.find(n, 0x10000, 0x2000000))
        boundary, kickoff = fi.check(view), fi.check(view, kickoff=True)
        # review of the floor F2: the end of an advance is judged like a kick-off for a club with a next game; at week 18
        # the bracket is not built yet, so every club the CPU signs for may still play and counts
        self.assertEqual(failing(boundary), {"I5", "I11"})
        self.assertEqual(failing(kickoff), {"I11"})                  # TF9: judged at kick-off it fails
        rows = [v for v in kickoff.violations if v["invariant"] == "I11"]
        self.assertEqual([(r["club"], r["club_name"], r["values"]["quarterbacks"], r["values"]["on_ir"]) for r in rows],
                         [(11, "DAL", 0, 3)])

    def test_the_minnesota_week_10_kickoff_image_fails_I11(self):
        """TF9: root 2505, 2026, the week 10 kick-off on the P0 Retail arm 6aef88eb: Minnesota's one active quarterback
        hurt, the other on IR (kept by the qb34 harness's kick-off check at 0x247DCF, runs/capture-min)."""
        path = QB34 / "no-qb-2505-2026-w10-kickoff.b81mem.gz"
        pinned(path, MINNESOTA_KICKOFF)
        memory = fi.load_memory(path)
        report = fi.check(fi.view_from_memory(memory.read, search=lambda n: memory.find(n, 0x10000, 0x2000000)),
                          kickoff=True)
        self.assertEqual([(r["club"], r["club_name"]) for r in report.violations if r["invariant"] == "I11"],
                         [(31, "MIN")])
        # the same state as an end-of-advance state (review of the floor F2): Minnesota has a next game, so it fails
        boundary = fi.check(fi.view_from_memory(memory.read, search=lambda n: memory.find(n, 0x10000, 0x2000000)))
        self.assertEqual([(r["club"], r["severity"]) for r in boundary.violations if r["invariant"] == "I11"],
                         [(31, fi.FAIL)])

    def playoff_view(self, *hurt_clubs):
        """P1 root 2508 after the 2026 wildcard round (stage 9 week 19; the bracket's divisional games are known): the
        quarterbacks of ``hurt_clubs`` made injured (3 weeks) in a copy of the image."""
        path = QB34 / "playoffs-2508-2026-w19.b81mem.gz"
        pinned(path, PLAYOFF_IMAGE)
        memory = fi.load_memory(path)
        view = fi.view_from_memory(memory.read, search=lambda n: memory.find(n, 0x10000, 0x2000000))
        root = struct.unpack("<I", memory.read(0xB72918, 4))[0]
        table = struct.unpack("<I", memory.read(root + 4, 4))[0]
        regions = [(a, bytearray(b)) for a, b in memory.regions]
        for club in hurt_clubs:
            for i in view.clubs[club].active:
                if view.record(i)[0x35] != fi.QB:
                    continue
                at = table + fi.PLAYER_SIZE * i + 0x20
                for start, data in regions:
                    if start <= at < start + len(data):
                        word = struct.unpack_from("<I", data, at - start)[0]
                        struct.pack_into("<I", data, at - start, word | fi.INJURED | 3 << 22)
        patched = fi.Regions((a, bytes(b)) for a, b in regions)
        return fi.view_from_memory(patched.read, search=lambda n: patched.find(n, 0x10000, 0x2000000))

    def i11(self, report):
        return {(r["club_name"], r["severity"]) for r in report.violations if r["invariant"] == "I11"}

    def test_an_end_of_advance_club_with_a_next_game_and_no_healthy_qb_fails_I11(self):
        view = self.playoff_view(21)                                  # NE: won its wildcard game, divisional game known
        self.assertEqual((view.stage, view.week), (9, 19))
        self.assertIn(("NE", fi.FAIL), self.i11(fi.check(view)))
        self.assertIn(("NE", fi.FAIL), self.i11(fi.check(view, kickoff=True)))

    def test_a_club_without_a_next_game_does_not_fail_I11(self):
        # LAC lost its wildcard game to NE; SF missed the playoffs (team 0 also fills the bracket's unknown cells);
        # MIN missed them too and is already without a healthy quarterback in the image
        view = self.playoff_view(8, 0)
        for report in (fi.check(view), fi.check(view, kickoff=True)):
            self.assertEqual({c for c, sev in self.i11(report) if sev == fi.FAIL}, set())
            self.assertEqual(self.i11(report), {("LAC", fi.WARN), ("SF", fi.WARN), ("MIN", fi.WARN)})

    def test_a_signed_save_with_a_club_without_a_healthy_qb_fails_I11(self):
        """Review F9: on a save (a closing save is week 18 or the playoffs) I11 is a failure, not a warning. pos2's
        9f435b38 run of root 2508 signed 2027 with Dallas holding no quarterback (copied to the qb34 fixtures)."""
        folder = QB34 / "dallas-2508-2027-signed"
        pinned(folder / "SAVEGAME.DAT", DALLAS_SIGNED)
        view, facts = fi.load_target(folder)
        report = fi.check(view)
        self.assertEqual((view.stage, view.week), (8, 18))
        self.assertEqual(failing(report), {"I5", "I11"})
        self.assertEqual([(r["club"], r["club_name"]) for r in report.violations
                          if r["invariant"] == "I11"], [(11, "DAL")])

    def test_retail_opening_passes(self):
        folder = SAVES / "f0/UDATA/53450030/0B8506889D40"
        pinned(folder / "SAVEGAME.DAT", RETAIL_F0)
        view, facts = fi.load_target(folder)
        report = fi.check(view)
        self.assertEqual(facts["signature"], "verified")
        self.assertEqual(report.violations, [])
        # its as-shipped human charts are reported, not judged (the correction recorded in the tool's docstring)
        self.assertTrue(view.info["human_club_row_anomalies"])


class RankLockTests(unittest.TestCase):
    """TD10 (DESIGN addendum 2, R2; coordinator's scope ruling 11/20): W12 and its repair apply from year index 1 on,
    never to a club whose depth chart the user manages, and the repair writes only when confirmed. The second-season
    save is the P2a paired control's root 2506 2027 closing save (no QB-room owner; evidence/validator/
    second-season-2506-2027/PROVENANCE.txt), holding a frozen shipped pair: IND Riley Leonard 78 at row 1 behind
    Anthony Richardson 70 at row 0, both rank-locked by the shipped 2026 roster."""

    @classmethod
    def setUpClass(cls):
        cls.folder = QB34 / "second-season-2506-2027/signed"
        cls.second = pinned(cls.folder / "SAVEGAME.DAT", SECOND_SEASON)
        cls.view = fi.view_from_save(cls.second)

    def w12(self, report):
        return [(r["club_name"], r["player_name"], r["values"]["row"], r["values"]["overall"],
                 r["values"]["row0_name"], r["values"]["row0_overall"], r["values"]["row0_locked"])
                for r in report.violations if r["invariant"] == "W12"]

    def benched(self, payload):
        """A D3-style room: a CPU club's healthy starter moved behind a healthy backup he leads by 6 or more, both
        rank-locked (bit 0 of +0x52), their rows swapped."""
        b = Breaker(payload)
        for c in b.view.clubs:
            if c.human or c.name in ("IND", "ARI"):
                continue
            qbs = sorted((i for i in c.active if b.position(i) == fi.QB), key=b.row)
            if len(qbs) < 2 or any(b.word(i, 0x20) & (fi.INJURED | fi.WEEKS_MASK) or b.word(i, 0x24) & fi.STATUS_MASK
                                   for i in qbs[:2]):
                continue
            best, second = qbs[0], qbs[1]
            if fi.native_overall(b.view.record(best)) - fi.native_overall(b.view.record(second)) >= 6:
                break
        else:
            self.fail("no room to bench")
        b.set_row(best, b.row(second))
        b.set_row(second, 0)
        for i in (best, second):
            b.buf[b.off(i) + 0x52] |= 1
        return b, c, best, second

    def signed(self, payload, where):
        from mod_editor.core import nfl2k5_roster_records as rr
        shutil.copytree(self.folder, where)
        (where / "SAVEGAME.DAT").write_bytes(payload)
        (where / "EXTRA").write_bytes(rr.sign_save(payload))
        return where

    def test_the_second_season_save_warns_on_its_frozen_shipped_pair(self):
        self.assertEqual((self.view.year_index, self.view.stage, self.view.week), (1, 8, 18))
        report = fi.check(self.view)
        self.assertEqual(self.w12(report), [("IND", "Riley Leonard", 1, 78, "Anthony Richardson", 70, True)])
        self.assertIn("W12", warned(report))
        self.assertNotIn("W12", failing(report))

    def test_year_one_saves_are_never_warned_or_repaired(self):
        folder = QB34 / "v09-opening-2501/signed"
        payload = pinned(folder / "SAVEGAME.DAT", V09_OPENING)
        view = fi.view_from_save(payload)
        self.assertEqual(view.year_index, 0)
        self.assertEqual(self.w12(fi.check(view)), [])                  # its shipped ARI/PHI pairs stand
        with tempfile.TemporaryDirectory() as tmp:
            receipt = fi.repair_rank_locks(folder, Path(tmp) / "repaired", confirm=True)
            self.assertEqual((receipt["pairs"], receipt["written"]), ([], None))
            self.assertFalse((Path(tmp) / "repaired").exists())
        b, club, best, second = self.benched(owned_or_skip_clean_closing())   # a year-one D3-style room: no W12
        self.assertEqual(self.w12(b.report()), [])

    def test_a_benched_better_quarterback_warns_from_the_second_season(self):
        b, club, best, second = self.benched(self.second)
        names = {r[1] for r in self.w12(b.report())}
        self.assertEqual(names, {"Riley Leonard", self.view.name(best)})
        row, = [r for r in b.report().violations if r.get("player_index") == best]
        self.assertEqual((row["club"], row["values"]["row"], row["values"]["row0_player"]), (club.index, 1, second))
        self.assertGreaterEqual(row["values"]["lead"], 6)

    def test_a_club_whose_chart_the_user_manages_is_never_warned_or_repaired(self):
        # the save's own user club: NYG (manual chart, 0xE60140 off) holds Jameis Winston 77, healthy and rank-locked
        # at row 1, behind J.J. McCarthy 70 at row 0 -- a W12 shape the user chose and the tool must leave alone
        view = fi.view_from_save(self.second)
        nyg = next(c for c in view.clubs if c.name == "NYG")
        self.assertTrue(nyg.human)
        self.assertFalse(view.cpu_manages_depth)
        rows = {view.name(i): (fi._row(fi._u16(view.record(i), 0x28)), fi.native_overall(view.record(i)),
                               view.record(i)[0x52] & 1) for i in nyg.active if view.record(i)[0x35] == fi.QB}
        self.assertEqual((rows["Jameis Winston"], rows["J.J. McCarthy"][:2]), ((1, 77, 1), (0, 70)))
        self.assertNotIn("NYG", {r[0] for r in self.w12(fi.check(view))})
        view.cpu_manages_depth = True                   # had the user handed the chart to the computer: warned
        self.assertIn(("NYG", "Jameis Winston"), {r[:2] for r in self.w12(fi.check(view))})
        b = Breaker(self.second)
        with tempfile.TemporaryDirectory() as tmp:
            receipt = fi.repair_rank_locks(self.folder, Path(tmp) / "repaired", confirm=True)
            self.assertEqual([p["club_name"] for p in receipt["pairs"]], ["IND"])
            after = (Path(tmp) / "repaired" / "SAVEGAME.DAT").read_bytes()
            for i in nyg.active:
                self.assertEqual(after[b.off(i) + 0x52], self.second[b.off(i) + 0x52], view.name(i))

    def test_without_confirm_the_repair_only_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repaired"
            receipt = fi.repair_rank_locks(self.folder, target)
            self.assertIs(receipt["confirmed"], False)
            self.assertEqual(receipt["written"], None)
            self.assertFalse(target.exists())
            pair, = receipt["pairs"]
            self.assertEqual((pair["club_name"], pair["player_name"], pair["overall"], pair["row"], pair["row0_name"],
                              pair["row0_overall"]), ("IND", "Riley Leonard", 78, 1, "Anthony Richardson", 70))
            self.assertEqual((self.folder / "SAVEGAME.DAT").read_bytes(), self.second)

    def test_the_confirmed_repair_clears_exactly_that_bit_and_the_copy_verifies(self):
        leonard = next(r["player_index"] for r in fi.check(self.view).violations if r["invariant"] == "W12")
        richardson = next(r["values"]["row0_player"] for r in fi.check(self.view).violations if r["invariant"] == "W12")
        b = Breaker(self.second)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "repaired"
            receipt = fi.repair_rank_locks(self.folder, target, confirm=True)
            self.assertIs(receipt["verified"], True)
            self.assertEqual([p["player_index"] for p in receipt["pairs"]], [leonard])
            view, facts = fi.load_target(target)
            self.assertEqual(facts["signature"], "verified")
            after = (target / "SAVEGAME.DAT").read_bytes()
            diff = [k for k in range(len(self.second)) if self.second[k] != after[k]]
            self.assertEqual(diff, [b.off(leonard) + 0x52])
            self.assertEqual(self.second[diff[0]] ^ after[diff[0]], 1)
            self.assertEqual(after[b.off(richardson) + 0x52] & 1, 1)     # the row 0 man keeps his lock
            before_rows = [r for r in fi.check(self.view).violations if r["invariant"] != "W12"]
            self.assertEqual(fi.check(view).violations, before_rows)
            self.assertEqual((self.folder / "SAVEGAME.DAT").read_bytes(), self.second)  # the source is never written

    def test_the_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, out = Path(tmp) / "repaired", Path(tmp) / "receipt.json"
            self.assertEqual(fi.main([str(self.folder), "--repair-rank-locks", str(target), "--out", str(out)]), 0)
            self.assertFalse(target.exists())
            self.assertEqual(json.loads(out.read_text())["confirmed"], False)
            self.assertEqual(fi.main([str(self.folder), "--repair-rank-locks", str(target), "--confirm",
                                      "--out", str(out)]), 0)
            self.assertEqual(fi.check(fi.load_target(target)[0], skip=["I6"]).violations,
                             [r for r in fi.check(self.view, skip=["I6"]).violations if r["invariant"] != "W12"])
            self.assertEqual(fi.main([str(self.folder), "--repair-rank-locks", str(target), "--confirm"]), 2)


def owned_or_skip_clean_closing() -> bytes:
    folder = owned("qb-system/evidence/phase1-scheduled-nov19/runs/standard/2501/signed")
    return pinned(folder / "SAVEGAME.DAT", CLEAN_CLOSING)


class HandBrokenTests(unittest.TestCase):
    """Each copy of the clean closing save breaks one invariant and must fail exactly that one."""

    @classmethod
    def setUpClass(cls):
        folder = owned("qb-system/evidence/phase1-scheduled-nov19/runs/standard/2501/signed")
        cls.clean = pinned(folder / "SAVEGAME.DAT", CLEAN_CLOSING)
        cls.view = fi.view_from_save(cls.clean)

    def fresh(self):
        return Breaker(self.clean)

    def test_the_clean_save_is_clean(self):
        report = fi.check(self.view)
        self.assertEqual(report.violations, [])
        self.assertEqual(report.status(strict=True), 0)

    def board_players(self):
        return {p for o in self.view.board if o.kind for p in o.players_a + o.players_b if p is not None}

    def healthy(self, b, i):
        return not b.word(i, 0x20) & fi.INJURED

    def test_a_54th_active_player_fails_I1(self):
        b, v, named = self.fresh(), self.view, self.board_players()
        managed = [c for c in v.clubs if not c.human]
        for x in managed:
            p = x.active[-1]
            pos = b.position(p)
            mates = [i for i in x.active if b.position(i) == pos]
            if (p in named or not self.healthy(b, p) or len(mates) < 2 or b.row(p) != max(b.row(i) for i in mates)
                    or pos in (fi.QB, fi.K, fi.P)):
                continue
            y = next(c for c in managed if c.index != x.index and len(c.active) + len(c.practice) < fi.SLOTS
                     and sum(b.position(i) == pos for i in c.active) < 7)
            break
        b.repack(x.index, x.active[:-1], x.practice)
        b.set_row(p, sum(b.position(i) == pos for i in y.active))
        b.repack(y.index, y.active + [p], y.practice)
        b.recount(x.index)
        b.recount(y.index)
        report = b.report()
        self.assertEqual(failing(report), {"I1"})
        self.assertEqual(warned(report), set())
        self.assertEqual([(r["club"], r["values"]["count"]) for r in report.violations], [(y.index, 54)])

    def test_a_doubled_pointer_fails_I2(self):
        b, v, named = self.fresh(), self.view, self.board_players()
        pairs = ((a, k, x, c, y) for a in v.clubs if not a.human for k, x in enumerate(a.active)
                 for c in v.clubs if c.index != a.index for y in c.active
                 if x not in named and y not in named and b.position(x) == b.position(y) and b.row(x) == b.row(y)
                 and self.healthy(b, x) and self.healthy(b, y))
        a, k, x, c, y = next(pairs)
        active = list(a.active)
        active[k] = y
        b.repack(a.index, active, a.practice)
        b.recount(a.index)
        report = b.report()
        self.assertEqual(failing(report), {"I2"})
        rows = [r for r in report.violations if r["invariant"] == "I2"]
        self.assertEqual([(r["player_index"], r["values"]["holders"]) for r in rows],
                         [(y, sorted([{"list": "active", "club": a.index}, {"list": "active", "club": c.index}],
                                     key=lambda h: h["club"]))])

    def test_a_row_hole_at_quarterback_fails_I4(self):
        b, v = self.fresh(), self.view
        club, qb = next((c, max((i for i in c.active if b.position(i) == fi.QB), key=b.row)) for c in v.clubs
                        if not c.human and 3 <= sum(b.position(i) == fi.QB for i in c.active) < 7)
        b.set_row(qb, b.row(qb) + 1)
        report = b.report()
        self.assertEqual(failing(report), {"I4"})
        row, = report.violations
        self.assertEqual((row["club"], row["values"]["position"]), (club.index, "QB"))

    def test_a_zero_length_contract_fails_I6_and_an_expired_one_warns(self):
        b, v = self.fresh(), self.view
        club = next(c for c in v.clubs if not c.human)
        p = club.active[0]
        b.set_word(p, 0x24, b.word(p, 0x24) & 0xF0FFFFF0)        # what the release routine 0x2BCF60 leaves
        b.recount(club.index)
        report = b.report()
        self.assertEqual(failing(report), {"I6"})
        self.assertEqual([r["player_index"] for r in report.violations], [p])
        b = self.fresh()
        b.set_word(p, 0x24, b.word(p, 0x24) & ~0xF)               # no years left, length kept: base-game state
        b.recount(club.index)
        report = b.report()
        self.assertEqual(failing(report), set())
        self.assertEqual(warned(report), {"I6"})
        self.assertEqual((report.status(), report.status(strict=True)), (1, 2))

    def test_an_ir_player_also_active_fails_I7(self):
        b, v = self.fresh(), self.view
        extension, returns, clubs = b.ir_clubs()
        club = next(c for c in v.clubs if not c.human and len(clubs[c.index]) < 5)
        p = next(i for i in club.active if b.position(i) not in (fi.QB, fi.K, fi.P))
        clubs[club.index].append((p, 0, False))
        b.write_ir(clubs, returns, extension)
        b.recount(club.index)
        report = b.report()
        self.assertEqual(failing(report), {"I7"})
        row, = report.violations
        self.assertEqual((row["club"], row["player_index"], row["values"]["active_club"]), (club.index, p, club.index))

    def test_a_club_with_every_quarterback_hurt_fails_I11(self):
        b, v = self.fresh(), self.view
        club = next(c for c in v.clubs if not c.human and sum(b.position(i) == fi.QB for i in c.active) >= 2)
        for i in club.active:
            if b.position(i) == fi.QB:
                b.set_word(i, 0x20, b.word(i, 0x20) | fi.INJURED | 3 << 22)     # injured, three weeks left
        kickoff = fi.check(fi.view_from_save(b.payload()), kickoff=True)
        self.assertEqual(failing(kickoff), {"I11"})
        row, = kickoff.violations
        self.assertEqual(row["club"], club.index)
        on_save = b.report()                            # a save at a stage 8 or 9 week: the hard failure (F9)
        self.assertEqual(failing(on_save), {"I11"})

    def test_a_preseason_club_with_every_quarterback_hurt_is_the_W7_warning_not_I11(self):
        b, v = self.fresh(), self.view
        club = next(c for c in v.clubs if not c.human and sum(b.position(i) == fi.QB for i in c.active) >= 2)
        for i in club.active:
            if b.position(i) == fi.QB:
                b.set_word(i, 0x20, b.word(i, 0x20) | fi.INJURED | 3 << 22)
        view = fi.view_from_save(b.payload())
        view.stage = 7                                 # the same room in the preseason
        for kickoff in (True, False):
            report = fi.check(view, kickoff=kickoff)
            self.assertEqual(failing(report), set(), kickoff)
            self.assertEqual(warned(report), {"W7"}, kickoff)
            self.assertEqual([r["club"] for r in report.violations], [club.index])
        view.stage = 9                                 # and in the playoffs: the hard failure again
        self.assertEqual(failing(fi.check(view, kickoff=True)), {"I11"})

    def test_a_club_left_over_the_cap_after_an_over_cap_signing_fails_I3c(self):
        b, v = self.fresh(), self.view
        club = next(c for c in v.clubs if not c.human)
        star = club.active[0]
        cheap = min(club.active, key=lambda i: fi.player_salary(v.record(i)))
        word = struct.unpack_from("<H", b.buf, b.off(star) + 0x0A)[0]
        while True:                                    # raise one contract until the club's recount is over the cap
            word = min(0xFFFF, word + 500)
            struct.pack_into("<H", b.buf, b.off(star) + 0x0A, word)
            b.recount(club.index)
            if fi.view_from_save(b.payload()).clubs[club.index].payroll > v.salary_cap or word == 0xFFFF:
                break
        view = fi.view_from_save(b.payload())
        over = view.clubs[club.index].payroll - view.salary_cap
        self.assertGreater(over, 0)
        self.assertEqual(failing(fi.check(view)), set())          # over the cap alone is the I3 warning
        two = fi.check(view, over_cap_signings=[{"club": club.index, "player": cheap, "boundaries": 2}])
        self.assertEqual(failing(two), {"I3c"})
        self.assertGreater(over, fi.player_salary(view.record(cheap)))
        one_cheap = fi.check(view, over_cap_signings=[{"club": club.index, "player": cheap, "boundaries": 1}])
        self.assertEqual(failing(one_cheap), {"I3c"})
        one_star = fi.check(view, over_cap_signings=[{"club": club.index, "player": star, "boundaries": 1}])
        self.assertEqual(failing(one_star), set())                # over by less than that man's charge: allowed

    def test_a_board_record_naming_a_player_his_club_no_longer_has_fails_I8(self):
        b, v = self.fresh(), self.view
        offer = next(o for o in v.board if o.kind and o.club_a is not None and o.players_a[0] is not None)
        stranger = next(i for c in v.clubs if c.index != offer.club_a for i in c.active)
        at = b.save.front_office_block + b.fs.F_TRADES + offer.slot * b.fs.F_TRADE_SIZE
        struct.pack_into("<H", b.buf, at + 2, stranger)          # FUN_002d06d0: A's first player at record +2
        report = b.report()
        self.assertEqual(failing(report), {"I8"})
        row, = report.violations
        self.assertEqual((row["club"], row["player_index"], row["values"]["slot"]), (offer.club_a, stranger, offer.slot))

    def test_command_line_exit_status(self):
        b = self.fresh()
        club = next(c for c in self.view.clubs if not c.human)
        p = club.active[0]
        with tempfile.TemporaryDirectory() as tmp:
            clean, warn = Path(tmp) / "clean", Path(tmp) / "warn"
            clean.mkdir(), warn.mkdir()
            (clean / "SAVEGAME.DAT").write_bytes(self.clean)
            b.set_word(p, 0x24, b.word(p, 0x24) & ~0xF)
            b.recount(club.index)
            (warn / "SAVEGAME.DAT").write_bytes(b.payload())
            out = Path(tmp) / "r.json"
            self.assertEqual(fi.main([str(clean), "--out", str(out)]), 0)
            self.assertEqual(fi.main([str(warn), "--out", str(out)]), 1)
            self.assertEqual(fi.main([str(warn), "--strict", "--out", str(out)]), 2)
            import json
            document = json.loads(out.read_text())
            self.assertEqual((document["status"], document["counts"]), (2, {"failures": 0, "warnings": 1}))
            self.assertEqual(document["violations"][0]["player_index"], p)

    def test_a_save_holding_a_page_record_is_judged_by_I8_and_its_pick_table(self):
        """The save path of the 4b checks: a quarterback-for-pick record written into the save's board (loader
        FUN_002d06d0 layout) is not an I8.boundary failure on a save unless asked, and its pick is judged against the
        save's own pick table (F_ORDERS, rows 1..14)."""
        b, v = self.fresh(), self.view
        owner = lambda round_, slot: b.save.u32(b.save.front_office_block + b.fs.F_ORDERS + 4 * (32 * (round_ - 1) + slot)) & 0xFF
        seller = next(c for c in v.clubs if not c.human and sum(b.position(i) == fi.QB for i in c.active) >= 3)
        qb = next(i for i in seller.active if b.position(i) == fi.QB and b.row(i) == 1)
        buyer = next(c for c in v.clubs if not c.human and c.index != seller.index and owner(5, c.index) == c.index)
        other = next(s for s in range(32) if owner(5, s) != buyer.index)
        slot = next(o.slot for o in v.board if o.slot and not o.kind)
        at = b.save.front_office_block + b.fs.F_TRADES + slot * b.fs.F_TRADE_SIZE

        def post(word):
            raw = bytearray(b.fs.F_TRADE_SIZE)
            raw[0], raw[1], raw[0x0E] = 2, seller.index, buyer.index
            struct.pack_into("<3H", raw, 2, qb, 0xFFFF, 0xFFFF)
            struct.pack_into("<3H", raw, 0x10, 0xFFFF, 0xFFFF, 0xFFFF)
            struct.pack_into("<H", raw, 0x16, word)
            b.buf[at:at + len(raw)] = raw
            return fi.view_from_save(b.payload())

        view = post(5 | other << 6)                                           # a pick the buyer does not own
        self.assertEqual(failing(fi.check(view)), {"I8.pick_owner"})
        row, = fi.check(view).violations
        self.assertEqual((row["club"], row["values"]["owner"]), (buyer.index, owner(5, other)))
        view = post(5 | buyer.index << 6)
        self.assertTrue(fi.is_qb_for_pick(view, view.board[slot]))
        self.assertEqual(fi.check(view).violations, [])                       # a save: boundary off by default
        self.assertEqual(failing(fi.check(view, boundary=True)), {"I8.boundary"})


class Ram:
    """A writable copy of a kept memory image, with the league layout the board checks need."""

    def __init__(self, regions):
        self.regions = [(a, bytearray(b)) for a, b in regions]

    def _at(self, address, size):
        for start, data in self.regions:
            if start <= address and address + size <= start + len(data):
                return data, address - start
        raise ValueError(f"unmapped {address:#x}")

    def get(self, address, size=4):
        data, k = self._at(address, size)
        return int.from_bytes(data[k:k + size], "little")

    def put(self, address, value, size=4):
        data, k = self._at(address, size)
        data[k:k + size] = value.to_bytes(size, "little")

    def view(self, **kw):
        regions = fi.Regions((a, bytes(b)) for a, b in self.regions)
        return fi.view_from_memory(regions.read, search=lambda n: regions.find(n, 0x10000, 0x2000000), **kw)

    def team(self, club):
        return self.get(self.get(fi.LEAGUE_ROOT) + 0x1C) + fi.TEAM_SIZE * club

    def player(self, index):
        return self.get(self.get(fi.LEAGUE_ROOT) + 4) + fi.PLAYER_SIZE * index

    def post(self, seller, qb, buyer, *words, b_player=None):
        """Write a record of the 4b page's shape into the first kind-0 slot of 1..14 (kind written last)."""
        slot = next(s for s in range(1, fi.BOARD_SLOTS) if not self.get(fi.BOARD + fi.BOARD_SIZE * s))
        at = fi.BOARD + fi.BOARD_SIZE * slot
        data, k = self._at(at, fi.BOARD_SIZE)
        data[k:k + fi.BOARD_SIZE] = bytes(fi.BOARD_SIZE)
        self.put(at + 8, self.team(seller))
        self.put(at + 0x0C, self.player(qb))
        self.put(at + 0x20, self.team(buyer))
        if b_player is not None:
            self.put(at + 0x24, self.player(b_player))
        for j, word in enumerate(words):
            self.put(at + 0x30 + 2 * j, word, 2)
        self.put(at, 2)
        return slot

    def drop(self, club, players):
        """Take players off a club's active list (the practice squad shifts down) and store the payroll recount."""
        base = self.team(club)
        n, ps = self.get(base + fi.ACTIVE_COUNT, 1), 0
        if self.get(base + fi.PS_MARKER, 1) == fi.PS_MARK:
            ps = self.get(base + fi.PS_COUNT, 1)
        gone = {self.player(i) for i in players}
        active = [self.get(base + 4 * s) for s in range(n)]
        kept = [p for p in active if p not in gone] + [self.get(base + 4 * s) for s in range(n, min(n + ps, fi.SLOTS))]
        for s in range(min(n + ps, fi.SLOTS)):
            self.put(base + 4 * s, kept[s] if s < len(kept) else 0)
        self.put(base + fi.ACTIVE_COUNT, n - len(gone & set(active)), 1)
        view = self.view()
        total = sum(fi.player_salary(view.record(i)) for i in view.clubs[club].active)
        total += sum(fi.player_salary(view.record(i), active=False) for i, _ in view.ir.clubs[club] if i >= 0)
        self.put(base + fi.PAYROLL, total)

    def native_pending_scan(self):
        """The game's own pending scan 0x2BC900 (the trade tick's executor loop: every kind 2 record in slots 1-14 between
        CPU clubs goes through 0x2BC670), run on this state; returns the state after it."""
        xbe = pinned(TRADE_XBE, TRADE_XBE_SHA)
        from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, Machine
        if not HAVE_UC:
            raise unittest.SkipTest("unicorn is not installed")
        m = Machine(xbe, trace_writes=False)
        for start, data in self.regions:
            m.uc.mem_write(start, bytes(data))
        m.uc.ctl_flush_tb()
        m.uc.mem_write(m.STACK, struct.pack("<II", m.STOP, m.ARENA + 0x1A0000))    # return address, menu argument
        for reg, value in dict(ESP=m.STACK, EBP=0x44444444, EFLAGS=0x202).items():
            m.reg(reg, value)
        m.uc.emu_start(0x2BC900, m.STOP, count=200_000_000)
        if m.reg("EIP") != m.STOP:
            raise AssertionError(f"pending scan stopped at {m.reg('EIP'):#x}")
        return Ram((start, bytes(m.uc.mem_read(start, len(data)))) for start, data in self.regions)


def new_failures(report, base) -> set[str]:
    """Failures the report adds to its base report's (which it must keep: nothing may disappear)."""
    if failing(base) - failing(report):
        raise AssertionError(f"failures disappeared: {failing(base) - failing(report)}")
    return failing(report) - failing(base)


class TradeBoardTests(unittest.TestCase):
    """4b's board invariants (DESIGN 4.2/4.3 I8) on the week 10 kick-off image (root 2505, 2026, stage 8 week 9, the Trade
    Deadline option off, kept at 0x247DCF: before the stage switch's trade tick, where the page's record legitimately
    sits). The record is the [trades] proof's: SF (0) gives its backup Mac Jones for CLE (5)'s own fifth, word
    5 | 5 << 6 (RISKS.md (b)). Each case changes that record or the state in one way and must add exactly one failure
    to the image's own (I4 on three clubs, I11 Minnesota)."""

    SELLER, BUYER, HUMAN = 0, 5, 15

    @classmethod
    def setUpClass(cls):
        path = QB34 / "no-qb-2505-2026-w10-kickoff.b81mem.gz"
        pinned(path, MINNESOTA_KICKOFF)
        cls.image = fi.load_memory(path).regions
        base = Ram(cls.image)
        cls.base_view = base.view()
        cls.qb = next(i for i in cls.base_view.clubs[cls.SELLER].active if cls.base_view.name(i) == "Mac Jones")
        cls.word = 5 | cls.BUYER << 6
        cls.base = fi.check(cls.base_view, skip=MIDWEEK)

    def posted(self, *words, seller=None, buyer=None, edit=None, **view_kw):
        ram = Ram(self.image)
        slot = ram.post(self.SELLER if seller is None else seller, self.qb, self.BUYER if buyer is None else buyer,
                        *(words or (self.word,)))
        if edit:
            edit(ram)
        return ram.view(**view_kw), slot

    def test_the_page_record_is_clean_mid_advance_and_fails_I8_boundary_at_a_boundary(self):
        base = Ram(self.image)
        self.assertEqual((base.get(fi.STAGE), base.get(fi.WEEK), base.get(TRADE_OPTION), base.get(DEADLINE_BYTE, 1)),
                         (8, 9, 0, 9))
        self.assertEqual(base.get(PICK_ROW1 + 32 * 4 + self.BUYER, 1), self.BUYER)   # the buyer owns its fifth
        view, slot = self.posted()
        self.assertTrue(fi.is_qb_for_pick(view, view.board[slot]))
        at_boundary = fi.check(view)                                              # a memory view: boundary by default
        self.assertEqual(new_failures(at_boundary, self.base), {"I8.boundary"})
        row, = [r for r in at_boundary.violations if r["invariant"] == "I8.boundary"]
        self.assertEqual((row["values"]["slot"], row["player_index"], row["values"]["seller"], row["club"]),
                         (slot, self.qb, self.SELLER, self.BUYER))
        self.assertEqual(new_failures(fi.check(self.base_view), self.base), set())     # no record, no failure
        self.assertEqual(new_failures(fi.check(view, boundary=False), self.base), set())
        self.assertEqual(new_failures(fi.check(view, skip=MIDWEEK), self.base), set())

    def test_a_pick_word_the_table_cannot_index_fails_I8_pick_word(self):
        for word in (self.word | 2 << 12, 8 | self.BUYER << 6, 5 | 32 << 6):          # year 2, round 8, slot 32
            view, slot = self.posted(word)
            report = fi.check(view, skip=MIDWEEK)
            self.assertEqual(new_failures(report, self.base), {"I8.pick_word"}, hex(word))
            row, = [r for r in report.violations if r["invariant"] == "I8.pick_word"]
            self.assertEqual((row["values"]["slot"], row["values"]["word"]), (slot, hex(word)))

    def test_a_pick_the_buyer_does_not_own_fails_I8_pick_owner(self):
        word = 5 | 6 << 6                                                             # club 6's own fifth
        self.assertEqual(Ram(self.image).get(PICK_ROW1 + 32 * 4 + 6, 1), 6)
        view, slot = self.posted(word)
        report = fi.check(view, skip=MIDWEEK)
        self.assertEqual(new_failures(report, self.base), {"I8.pick_owner"})
        row, = [r for r in report.violations if r["invariant"] == "I8.pick_owner"]
        self.assertEqual((row["club"], row["values"]["owner"], row["values"]["qb_for_pick"]), (self.BUYER, 6, True))
        # the same pick on a record of another shape (a buyer's player too) is the native board's business: a warning
        buyer_player = self.base_view.clubs[self.BUYER].active[-1]
        ram = Ram(self.image)
        ram.post(self.SELLER, self.qb, self.BUYER, word, b_player=buyer_player)
        report = fi.check(ram.view(), skip=MIDWEEK)
        self.assertEqual(new_failures(report, self.base), set())
        self.assertIn("I8.pick_owner", warned(report))

    def test_a_human_club_fails_I8_human(self):
        self.assertTrue(self.base_view.clubs[self.HUMAN].human)
        word = 6 | self.HUMAN << 6
        self.assertEqual(Ram(self.image).get(PICK_ROW1 + 32 * 5 + self.HUMAN, 1), self.HUMAN)   # NYG owns its sixth
        view, slot = self.posted(word, buyer=self.HUMAN)
        report = fi.check(view, skip=MIDWEEK)
        self.assertEqual(new_failures(report, self.base), {"I8.human"})
        row, = [r for r in report.violations if r["invariant"] == "I8.human"]
        self.assertEqual((row["club"], row["values"]["slot"]), (self.HUMAN, slot))

    def test_a_record_while_the_window_is_closed_fails_I8_window(self):
        option_on = lambda ram: ram.put(TRADE_OPTION, 1)
        view, slot = self.posted(edit=option_on)                                      # week 9, deadline 9: closed
        report = fi.check(view, skip=MIDWEEK)
        self.assertEqual(new_failures(report, self.base), {"I8.window"})
        row, = [r for r in report.violations if r["invariant"] == "I8.window"]
        self.assertEqual((row["values"]["week"], row["values"]["deadline_week"], row["values"]["option"]), (9, 9, 1))
        view, _ = self.posted(edit=option_on, deadline_week=10)                       # week 9 < 10: open
        self.assertEqual(new_failures(fi.check(view, skip=MIDWEEK), self.base), set())

    def test_a_round_zero_word_is_no_pick(self):
        """is_qb_for_pick counts a pick by its round (w & 0x3F): a cancelled pick keeps its slot and year bits."""
        stale = 0 | 7 << 6 | 1 << 12
        view, slot = self.posted(self.word, stale)                                   # one real pick, one stale word
        self.assertTrue(fi.is_qb_for_pick(view, view.board[slot]))
        self.assertEqual(new_failures(fi.check(view), self.base), {"I8.boundary"})
        view, slot = self.posted(stale)                                              # only the stale word: no pick
        self.assertFalse(fi.is_qb_for_pick(view, view.board[slot]))
        self.assertEqual(new_failures(fi.check(view), self.base), set())

    def test_the_command_line_boundary_and_deadline_arguments(self):
        ram = Ram(self.image)
        ram.post(self.SELLER, self.qb, self.BUYER, self.word)
        ram.put(TRADE_OPTION, 1)
        with tempfile.TemporaryDirectory() as tmp:
            image, out = Path(tmp) / "posted.b81mem.gz", Path(tmp) / "r.json"
            fi.dump_memory(image, [(a, bytes(b)) for a, b in ram.regions])
            names = lambda *args: (fi.main(["--memory", str(image), "--out", str(out), *args]),
                                   {r["invariant"] for r in json.loads(out.read_text())["violations"]} & {
                                       "I8.boundary", "I8.window"})
            self.assertEqual(names(), (2, {"I8.boundary", "I8.window"}))
            self.assertEqual(names("--no-boundary"), (2, {"I8.window"}))
            self.assertEqual(names("--no-boundary", "--deadline-week", "10"), (2, set()))


class TradeExecutionTests(unittest.TestCase):
    """4b's trade invariants T1 (DESIGN 4.2's "must never" list) on a GENUINE trade: the record of TradeBoardTests posted
    on the kick-off image and run through the game's own pending scan 0x2BC900 (p2-candidate-9edd1353, which the image
    ran on). The scan executes it (Mac Jones to CLE, the pick table's (round 5, slot 5) 5 -> 0, the ledger rows
    0x7 [Mac Jones, SF] and 0x800000A7 [no player, CLE]) and four native player-for-player records already on the
    board. previous = the image before the post, view = the state after the scan."""

    SELLER, BUYER = TradeBoardTests.SELLER, TradeBoardTests.BUYER

    @classmethod
    def setUpClass(cls):
        TradeBoardTests.setUpClass.__func__(cls)
        before = Ram(cls.image)
        before.post(cls.SELLER, cls.qb, cls.BUYER, cls.word)
        cls.after = before.native_pending_scan()
        cls.previous = Ram(cls.image).view()
        cls.after_view = cls.after.view()
        cls.after_base = fi.check(cls.after_view)                                     # the state after, alone

    def judged(self, previous=None, after=None):
        view = after.view() if after is not None else self.after_view
        return fi.check(view, previous=previous or self.previous), view

    def test_the_genuine_trade_passes_every_T1_check(self):
        report, view = self.judged()
        self.assertEqual(new_failures(report, self.after_base), set())
        self.assertFalse([r for r in report.violations if r["invariant"].startswith(("T1", "I8."))])
        t1 = view.info["trades_since_previous"]
        self.assertEqual((t1["groups"], t1["pick_changes"]), (5, 1))
        q, = t1["qb_for_pick"]
        self.assertEqual((q["seller"], q["buyer"], q["player"], q["round"], q["year"]), (self.SELLER, self.BUYER, self.qb, 5, 0))
        self.assertIn(self.qb, view.clubs[self.BUYER].active)
        self.assertEqual((self.after.get(PICK_ROW1 + 32 * 4 + self.BUYER, 1), view.clubs[self.SELLER].count,
                          view.clubs[self.BUYER].count), (self.SELLER, 51, 53))
        self.assertFalse(any(o.kind and fi.is_qb_for_pick(view, o) for o in view.board))   # executed, then cancelled

    def test_trades_in_an_advance_without_a_cpu_trade_tick_fail_T1_window(self):
        closed = Ram(self.image)
        closed.put(TRADE_OPTION, 1)                                                   # week 9 is past the deadline
        report, _ = self.judged(previous=closed.view())
        self.assertEqual(new_failures(report, self.after_base), {"T1.window"})
        self.assertEqual(len([r for r in report.violations if r["invariant"] == "T1.window"]), 5)   # every group
        report, _ = self.judged(previous=closed.view(deadline_week=10))                # open: nothing
        self.assertEqual(new_failures(report, self.after_base), set())
        for stage, judged in ((7, False), (9, True)):   # 0x247D40's stage 7 case runs the tick with no window test;
            other = Ram(self.image)                         # stage 9 (the playoffs) runs none
            other.put(fi.STAGE, stage)
            report, _ = self.judged(previous=other.view())
            self.assertEqual("T1.window" in failing(report), judged, stage)

    def test_a_trade_naming_a_human_club_fails_T1_human(self):
        after = Ram(self.after.regions)
        after.put(fi.USER_CONTROL + 4 * self.BUYER, 1)
        report, _ = self.judged(after=after)
        self.assertEqual(new_failures(report, fi.check(after.view())), {"T1.human"})
        row, = [r for r in report.violations if r["invariant"] == "T1.human"]
        self.assertEqual((row["club"], row["player_index"]), (self.BUYER, self.qb))

    def test_a_buyer_left_under_50_fails_T1_counts(self):
        """The native evaluator lets side B finish at 44 or more in season (0x2BB161): a buyer at 48 takes the trade."""
        before = Ram(self.image)
        buyer = self.previous.clubs[self.BUYER]
        named = {p for o in self.previous.board if o.kind for p in o.players_a + o.players_b if p is not None}
        rows = lambda i: (self.previous.record(i)[0x35], fi._row(fi._u16(self.previous.record(i), 0x28)))
        drop, used = [], set()
        for i in reversed(buyer.active):                 # one bottom-row man at each of four deep positions
            pos, row = rows(i)
            mates = [j for j in buyer.active if rows(j)[0] == pos]
            if (pos not in (fi.QB, fi.K, fi.P) and pos not in used and i not in named and len(mates) >= 3
                    and row == max(rows(j)[1] for j in mates)):
                drop.append(i)
                used.add(pos)
            if len(drop) == 4:
                break
        before.drop(self.BUYER, drop)
        previous = before.view()
        self.assertEqual(previous.clubs[self.BUYER].count, 48)
        before.post(self.SELLER, self.qb, self.BUYER, self.word)
        after = before.native_pending_scan()
        report, view = self.judged(previous=previous, after=after)
        self.assertIn(self.qb, view.clubs[self.BUYER].active)                         # the game took it
        self.assertEqual(new_failures(report, fi.check(after.view())), {"T1.counts"})
        row, = [r for r in report.violations if r["invariant"] == "T1.counts"]
        self.assertEqual((row["club"], row["values"]["count"], row["values"]["role"]), (self.BUYER, 49, "buyer"))

    def test_a_seller_left_with_one_healthy_quarterback_fails_T1_seller_depth(self):
        """The CPU path checks no seller depth (RISKS (a) 5). SF's third quarterback hurt before the trade: the game
        still trades its backup and leaves it one healthy quarterback."""
        rourke = next(i for i in self.previous.clubs[self.SELLER].active if self.previous.name(i) == "Kurtis Rourke")
        hurt = lambda ram: ram.put(ram.player(rourke) + 0x20, ram.get(ram.player(rourke) + 0x20) | fi.INJURED | 2 << 22)
        before = Ram(self.image)
        hurt(before)
        previous = before.view()
        before.post(self.SELLER, self.qb, self.BUYER, self.word)
        after = before.native_pending_scan()
        report, view = self.judged(previous=previous, after=after)
        self.assertIn(self.qb, view.clubs[self.BUYER].active)
        self.assertEqual(new_failures(report, fi.check(after.view())), {"T1.seller_depth"})
        row, = [r for r in report.violations if r["invariant"] == "T1.seller_depth"]
        self.assertEqual((row["club"], row["values"]["quarterbacks"], row["values"]["healthy"]), (self.SELLER, 2, 1))
        # hurt only after the trade (this week's game): not the trade's doing
        after = Ram(self.after.regions)
        hurt(after)
        report, _ = self.judged(after=after)
        self.assertEqual(new_failures(report, fi.check(after.view())), set())

    def test_a_pick_that_did_not_change_owner_fails_T1_pick(self):
        after = Ram(self.after.regions)
        after.put(PICK_ROW1 + 32 * (5 - 1) + self.BUYER, self.BUYER, 1)                # the transfer undone
        report, _ = self.judged(after=after)
        self.assertEqual(new_failures(report, fi.check(after.view())), {"T1.pick"})
        after.put(PICK_ROW1 + 32 * (5 - 1) + self.BUYER, 9, 1)                          # or given to a third club
        report, _ = self.judged(after=after)
        self.assertEqual(new_failures(report, fi.check(after.view())), {"T1.pick"})     # the buyer's row explains it

    def test_a_pick_that_changed_owner_without_a_trade_row_fails_T1_unexplained_pick(self):
        after = Ram(self.after.regions)
        self.assertEqual(after.get(PICK_ROW1 + 32 * (3 - 1) + 7, 1), 7)
        after.put(PICK_ROW1 + 32 * (3 - 1) + 7, 9, 1)                                   # club 7's own third to club 9
        report, _ = self.judged(after=after)
        self.assertEqual(new_failures(report, fi.check(after.view())), {"T1.unexplained_pick"})
        row, = [r for r in report.violations if r["invariant"] == "T1.unexplained_pick"]
        self.assertEqual((row["values"]["round"], row["values"]["pick_slot"], row["values"]["owner_after"]), (3, 7, 9))
        # no trade at all, one entry moved by hand
        quiet = Ram(self.image)
        quiet.put(PICK_ROW1 + 32 * (3 - 1) + 7, 9, 1)
        report = fi.check(quiet.view(), previous=self.previous)
        self.assertEqual(new_failures(report, fi.check(quiet.view())), {"T1.unexplained_pick"})


if __name__ == "__main__":
    unittest.main()
