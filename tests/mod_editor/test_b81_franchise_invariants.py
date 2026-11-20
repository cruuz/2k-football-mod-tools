"""T10 (beta 81 qb34 DESIGN 4.4): the franchise invariant validator, tools/franchise_invariants.py.

Private inputs (never in git; each test skips when its file is absent, and every file is pinned by sha256):
- NFL2K5_B81_OWNERSHIP_FIXTURES (Codex's beta81 tree): the signed 61001 duplicate-ownership save and its memory image,
  and a clean signed standard closing save (phase1 standard 2501, the harness reproduces it byte for byte).
- NFL2K5_B81_QB34_FIXTURES (default: the qb34 lane's evidence/validator folder): the released v0.9 opening, signed
  natively on the released v0.9 executable and roster (qb34/harness/make_opening_save.py), and its memory image.
- NFL2K5_SAVE_FIXTURES: the retail franchise opening save f0.
Each hand-broken copy changes the clean save in one way and must fail exactly the invariant it breaks; where the
game would have recounted the payroll after such a change, the copy stores the recount too (so I3 stays true).
"""
from __future__ import annotations

import gzip
import hashlib
import io
import os
from pathlib import Path
import pickle
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
                      "salary_cap", "free_agents", "ledger_cursor", "ledger_kinds"):
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

    def test_retail_opening_passes(self):
        folder = SAVES / "f0/UDATA/53450030/0B8506889D40"
        pinned(folder / "SAVEGAME.DAT", RETAIL_F0)
        view, facts = fi.load_target(folder)
        report = fi.check(view)
        self.assertEqual(facts["signature"], "verified")
        self.assertEqual(report.violations, [])
        # its as-shipped human charts are reported, not judged (the correction recorded in the tool's docstring)
        self.assertTrue(view.info["human_club_row_anomalies"])


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


if __name__ == "__main__":
    unittest.main()
