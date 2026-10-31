"""Job ch2 (beta 79, release review R2 BLOCKER 1 / MAJOR 1): the champions history is seeded on a grown roster, loudly.

R2 found the final disc's champions page empty: ``honors_history.apply`` tried to seed Super Bowls XXXIX to LX long before
the arena growth wrote the reserve block the history lives behind, and turned the refusal into a silent "skipped". These
tests pin the fix (pure Python, synthetic rosters, runs everywhere):

* the build seeds after the arena growth and after every main-roster writer, before the disc compaction (source order);
* a pack-recipe plan (Experimental preset + a roster-edits capacity request) asks for the seeds, writes exactly the 270
  block bytes, reads them back as XXXIX..LX, and its step is never "skipped";
* a grown roster that cannot take the seeds stops the build (no reserve block, spare bytes in use);
* a plain Advanced/Experimental build (no growth) does not grow anything: no roster byte changes, the build log and the
  Build summary say the champions page reads CHAMPIONS: NONE YET;
* the honors history step no longer pretends to seed the champions.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_champions as champions  # noqa: E402
from mod_editor.core import nfl2k5_champions_history as history  # noqa: E402
from mod_editor.core import nfl2k5_honors_history as honors_history  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as records  # noqa: E402
from mod_editor.core import nfl2k5_team_history as team_history  # noqa: E402
from tests.mod_editor.test_b779_hn1_champions_history import synthetic_body  # noqa: E402

GROWN_BODY = 0xCA040        # the SOFTDRINK v0.8 disc's main roster body (0x40 object + the 0xCA000 arena)
OUTER_BEFORE = 5            # entries 0..4 before the main roster (outer entry 5)


class FakeOuterImage:
    """The OuterImage interface the writers use, over an in-memory archive (path -> bytearray)."""

    archives: dict[str, bytearray] = {}
    layouts: dict[str, list] = {}

    def __init__(self, path, *, writable=False):
        self.path, self.writable = str(path), writable
        self.blob = self.archives[self.path]
        self.entries = self.layouts[self.path]

    def read(self, virtual_offset, size):
        return bytes(self.blob[virtual_offset:virtual_offset + size])

    def write(self, virtual_offset, data):
        if not self.writable:
            raise ValueError("read-only archive")
        self.blob[virtual_offset:virtual_offset + len(data)] = data
        return len(data)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None


def install(path: str, body: bytes) -> int:
    """Put ``body`` behind a 0x20-byte ROST wrapper as outer entry 5 of a fake archive; returns the body's offset."""

    filler = [bytes([i + 1]) * 0x40 for i in range(OUTER_BEFORE)]
    header = b"ROST" + len(body).to_bytes(4, "little") * 2 + bytes(0x14)
    blob, entries, at = bytearray(), [], 0
    for chunk in filler + [header + body]:
        entries.append(types.SimpleNamespace(virtual_offset=at, size=len(chunk)))
        blob += chunk
        at += len(chunk)
    FakeOuterImage.archives[path], FakeOuterImage.layouts[path] = blob, entries
    return entries[OUTER_BEFORE].virtual_offset + 0x20


def pack_plan(**changes):
    plan = mod_build.apply_preset(mod_build.BuildPlan("source.iso", "target.iso"), "softdrink_experimental")
    return mod_build.replace(plan, **changes) if changes else plan


class Harness(unittest.TestCase):
    def setUp(self):
        FakeOuterImage.archives.clear()
        FakeOuterImage.layouts.clear()
        patches = (mock.patch.object(history, "_outer_image", lambda: FakeOuterImage),
                   mock.patch.object(team_history, "_outer_image", lambda: FakeOuterImage),
                   mock.patch.object(mod_build.tt, "is_disc_image", lambda _path: True))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.lines = []

    def progress(self, message, *_):
        self.lines.append(message)

    def run_step(self, plan, path, capacity_records):
        receipt = {"steps": [], "result": {}}
        mod_build._apply_champions_history(plan, path, receipt, self.progress, capacity_records)
        return receipt


class BuildOrderTests(unittest.TestCase):
    def test_the_seed_runs_after_the_growth_and_every_main_roster_writer_before_compaction(self):
        source = Path(mod_build.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        build = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_build")
        body = ast.get_source_segment(source, build)
        seed = body.index("_apply_champions_history(plan, target, receipt, progress, capacity_records)")
        self.assertEqual(body.count("_apply_champions_history("), 1)
        for writer in ("tt._finish_roster_arena_image(", "_apply_roster_refresh(plan, target", "_apply_team_ratings(plan, target",
                       "qb_module.apply_image(", "classic.apply_to_image(", "metlife.apply_to_image(",
                       '_core_module("nfl2k5_real_portraits")', "_apply_sim_realism(plan, target"):
            self.assertLess(body.index(writer), seed, writer)
        self.assertLess(seed, body.index("finish_private(target"))
        # and the survival gate reads it again on the compacted copy
        self.assertLess(body.index("finish_private(target"), body.index('read_image(target)'))

    def test_the_honors_history_step_no_longer_touches_the_champions(self):
        source = Path(honors_history.__file__).read_text(encoding="utf-8")
        self.assertNotIn("champions_history.apply_body", source)
        self.assertNotIn('"skipped", "reason": str(exc)', source)


class PlanTests(unittest.TestCase):
    def test_the_presets(self):
        basic = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_basic")
        self.assertEqual(mod_build._champions_history_plan(basic, 0), {"status": "off"})
        for name in ("softdrink_advanced", "softdrink_experimental"):
            plan = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), name)
            decision = mod_build._champions_history_plan(plan, 0)
            self.assertEqual(decision["status"], "no_room", name)
            self.assertFalse(decision["grows_arena"])
            self.assertIn("CHAMPIONS: NONE YET", decision["note"])
        self.assertEqual(mod_build._champions_history_plan(pack_plan(), 612),
                         {"status": "seed", "grows_arena": True, "seed_requested": True})
        self.assertEqual(mod_build._champions_history_plan(pack_plan(reserves_16=True), 0)["status"], "seed")
        self.assertEqual(mod_build._champions_history_plan(pack_plan(created_teams_extra=2), 0)["status"], "seed")
        self.assertEqual(mod_build._champions_history_plan(pack_plan(honors_history=""), 612)["status"], "empty")
        self.assertEqual(mod_build._champions_history_plan(pack_plan(season_2026=False), 612)["status"], "empty")

    def test_a_pack_recipe_roster_edits_document_asks_for_the_seeds(self):
        with tempfile.TemporaryDirectory() as folder:
            edits = Path(folder) / "roster-edits.json"
            edits.write_text(json.dumps({"schema": records.EDITS_SCHEMA, "edits": [],
                                         "free_agent_capacity": {"schema": "nfl2k5.free_agent_capacity.v1",
                                                                 "records": 612}}), encoding="utf-8")
            plan = pack_plan(roster_edits=str(edits))
            self.assertEqual(mod_build._roster_capacity_records(plan), 612)
            self.assertEqual(mod_build._champions_history_plan(plan)["status"], "seed")


class PackSeedTests(Harness):
    def test_a_grown_roster_takes_xxxix_to_lx_and_only_the_block_changes(self):
        body = synthetic_body(GROWN_BODY)
        at = install("pack.iso", body) + len(body) - 0x400 + 352
        before = bytes(FakeOuterImage.archives["pack.iso"])
        receipt = self.run_step(pack_plan(), "pack.iso", 612)
        step = receipt["steps"][-1]
        self.assertEqual(step["step"], "champions_history")
        self.assertEqual(step["status"], "applied")
        self.assertNotIn("skipped", json.dumps(receipt))
        self.assertTrue(step["seeded"])
        self.assertEqual((step["seasons"], step["seasons_read_back"]), (22, 22))
        self.assertEqual((step["oldest_super_bowl"], step["newest_super_bowl"]), (39, 60))
        self.assertEqual(receipt["result"]["champions_history"], "applied")
        after = bytes(FakeOuterImage.archives["pack.iso"])
        diff = [i for i in range(len(before)) if before[i] != after[i]]
        self.assertTrue(diff)
        self.assertTrue(all(at <= i < at + history.USED for i in diff), (hex(diff[0]), hex(diff[-1]), hex(at)))
        self.assertEqual(after[at:at + history.USED], history.seeded_block())
        self.assertEqual([r["super_bowl"] for r in history.read_image("pack.iso")], list(range(60, 38, -1)))
        # a rebuild from an already seeded copy is a no-op
        again = self.run_step(pack_plan(), "pack.iso", 612)
        self.assertEqual(again["steps"][-1]["status"], "applied")
        self.assertTrue(again["steps"][-1]["unchanged"])
        self.assertEqual(bytes(FakeOuterImage.archives["pack.iso"]), after)

    def test_a_reserve_schema_roster_takes_them_too(self):
        body = synthetic_body(0x92040)      # 16 reserves: the 0x92000 arena, reserve block 0x400 before its end
        install("reserves.iso", body)
        receipt = self.run_step(pack_plan(reserves_16=True), "reserves.iso", 0)
        self.assertEqual(receipt["steps"][-1]["status"], "applied")

    def test_a_grown_plan_without_the_reserve_block_stops_the_build(self):
        install("broken.iso", bytes(GROWN_BODY))
        before = bytes(FakeOuterImage.archives["broken.iso"])
        with self.assertRaisesRegex(RuntimeError, "no reserve block"):
            self.run_step(pack_plan(), "broken.iso", 612)
        self.assertEqual(bytes(FakeOuterImage.archives["broken.iso"]), before)

    def test_spare_bytes_in_use_stop_the_build(self):
        body = bytearray(synthetic_body(GROWN_BODY))
        body[len(body) - 0x400 + 352 + 40] = 7
        install("used.iso", bytes(body))
        before = bytes(FakeOuterImage.archives["used.iso"])
        with self.assertRaisesRegex(RuntimeError, "could not be written"):
            self.run_step(pack_plan(), "used.iso", 612)
        self.assertEqual(bytes(FakeOuterImage.archives["used.iso"]), before)

    def test_a_grown_build_without_the_2026_history_starts_empty(self):
        install("empty.iso", synthetic_body(GROWN_BODY))
        before = bytes(FakeOuterImage.archives["empty.iso"])
        receipt = self.run_step(pack_plan(honors_history=""), "empty.iso", 612)
        self.assertEqual(receipt["steps"][-1]["status"], "empty")
        self.assertEqual(bytes(FakeOuterImage.archives["empty.iso"]), before)


class PlainPresetTests(Harness):
    def test_advanced_and_experimental_without_growth_say_so_and_change_nothing(self):
        for name in ("softdrink_advanced", "softdrink_experimental"):
            self.lines.clear()
            path = f"{name}.iso"
            install(path, bytes(records.BODY_SIZE))      # the game's own roster size: no reserve block
            before = bytes(FakeOuterImage.archives[path])
            plan = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), name)
            receipt = self.run_step(plan, path, 0)
            step = receipt["steps"][-1]
            self.assertEqual((step["step"], step["status"], step["seeded"]), ("champions_history", "no_room", False))
            self.assertIn(history.NO_ROOM_NOTE, receipt["user_notes"])
            self.assertIn(history.NO_ROOM_NOTE, self.lines)
            self.assertEqual(receipt["result"]["champions_history"], "no_room")
            self.assertEqual(bytes(FakeOuterImage.archives[path]), before, name)

    def test_basic_does_nothing(self):
        install("basic.iso", bytes(records.BODY_SIZE))
        plan = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_basic")
        receipt = self.run_step(plan, "basic.iso", 0)
        self.assertEqual(receipt, {"steps": [], "result": {}})

    def test_the_help_text_says_what_happens(self):
        text = champions.HELP_TEXT
        self.assertNotIn("32 champions", text)
        self.assertNotIn("team records", text)
        self.assertIn("22 Super Bowls", text)
        self.assertIn("CHAMPIONS: NONE YET", text)
        self.assertIn("XXXIX to LX", text)
        self.assertNotIn("—", text + history.NO_ROOM_NOTE)


class HonorsHistoryTests(Harness):
    def test_the_award_history_receipt_has_no_champions_part(self):
        from tests.mod_editor.test_nfl2k5_honors_history import body_with
        body = body_with([dict(first="Pat", last="Star", birth=dt.date(1995, 9, 17), count=9, stream=None)])
        self.assertEqual(len(body), team_history.BODY_SIZE)
        install("retail.iso", body)
        receipt = honors_history.apply("retail.iso", "builtin", base_year=2026)
        self.assertNotIn("champions", receipt)


if __name__ == "__main__":
    unittest.main()
