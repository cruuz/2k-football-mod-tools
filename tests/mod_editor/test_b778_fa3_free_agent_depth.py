"""b778 fa3: real unsigned, unretired NFL free agents (Kaepernick first) for the disc and for existing franchises.

Portable tests check the sourced data and the refresh-plan writer. Private inputs (read only: the Oct 13 pack disc,
the dated refresh plan, the released disc and a copy of Noah's MyNFL3 franchise) prove the capacity rule on the real
roster writer and the Franchise > Upgrade step on a real save; each skips without them.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_spare_capacity as capacity  # noqa: E402
from mod_editor.core import nfl2k5_franchise_upgrade as up  # noqa: E402
from mod_editor.core import nfl2k5_franchise_upgrade_io as service  # noqa: E402
from tools.b77 import b778_fa3_free_agent_depth as depth  # noqa: E402

SCRATCH = Path(os.environ.get("NFL2K5_B778_SCRATCH", "/home/noah/2k-worktrees/.b77-scratch/b778"))
DISCS = Path(os.environ.get("NFL2K5_DISC_FOLDER", "/media/noah/Storage/2K5 Discs"))
OCT13_DISC = DISCS / "SOFTDRINK 2K28 v0.6.1 fixes (2026-10-13).xiso.iso"
RELEASED_DISC = DISCS / "SOFTDRINK 2K28 v0.6.1 (2026-10-20).xiso.iso"
REFRESH_PLAN = SCRATCH / "rt1/out/roster-edits-b778-rt1.json"
NOAH_SAVE = SCRATCH / "fa1/noah_save/w9"
KAEPERNICK = "00-0027974"


def tiny_plan():
    return {"schema": "nfl2k5.roster_refresh.v1", "players": [{"index": 2464, "gsis_id": "x", "new": True}],
            "identity_guards": [[0, "A", "B", "2000-01-01"]], "free_agents": [5], "teams": []}


class DataTests(unittest.TestCase):
    def test_every_player_is_sourced_rated_and_kaepernick_is_first(self):
        data = depth.load()
        players = data["players"]
        self.assertGreaterEqual(len(players), 20)
        self.assertEqual(players[0]["gsis_id"], KAEPERNICK)
        self.assertEqual(players[0]["fields"]["hand"], 0)            # he throws left-handed
        for p in players:
            with self.subTest(player=p["name"]):
                self.assertEqual(p["status"], "unsigned_not_retired")
                self.assertTrue(p["sources"][1]["basis"])
                self.assertIn(rr.POSITIONS[p["fields"]["position"]], rr.POSITIONS)
                self.assertTrue(all(0 <= p["fields"][k] <= 99 for k in rr.RATING_BYTE_ORDER))
                self.assertGreaterEqual(p["fields"]["years_pro"], 1)

    def test_a_retired_or_unsourced_player_is_refused(self):
        data = depth.load()
        bad = copy.deepcopy(data)
        bad["players"][3]["status"] = "officially_retired"
        with self.assertRaises(depth.DepthError):
            depth.validate(bad)
        bad = copy.deepcopy(data)
        bad["players"][3]["sources"] = bad["players"][3]["sources"][:1]
        with self.assertRaises(depth.DepthError):
            depth.validate(bad)
        bad = copy.deepcopy(data)
        bad["players"][3]["fields"]["pbp_id"] = 9999      # neither a verified clip nor the number
        with self.assertRaises(depth.DepthError):
            depth.validate(bad)

    def test_the_upgrade_cohort_is_the_same_data(self):
        cohort = up.free_agent_cohort()
        self.assertEqual([c["name"] for c in cohort], [p["name"] for p in depth.load()["players"]])


class PlanTests(unittest.TestCase):
    def test_new_rows_take_free_vacancies_in_priority_order_and_join_the_free_agents(self):
        data = depth.load()
        plan = tiny_plan()
        out = depth.extend_plan(plan, data, 3)
        self.assertEqual(plan, tiny_plan())                          # the caller's plan is untouched
        rows = out["players"][1:]
        self.assertEqual([r["index"] for r in rows], [2465, 2466, 2467])
        self.assertEqual(out["free_agents"], [5, 2465, 2466, 2467])
        self.assertEqual([r["source_name"] for r in rows], [p["name"] for p in data["players"][:3]])
        for row in rows:
            self.assertTrue(row["new"])
            self.assertEqual(row["fields"]["photo_id"], depth.PHOTO_BASE + row["index"])
            self.assertTrue(set(rr.RATING_BYTE_ORDER) <= set(row["fields"]))

    def test_a_player_already_in_the_refresh_is_refused(self):
        data = depth.load()
        plan = tiny_plan()
        plan["players"][0]["gsis_id"] = data["players"][0]["gsis_id"]
        with self.assertRaises(depth.DepthError):
            depth.extend_plan(plan, data, 1)


@unittest.skipUnless(OCT13_DISC.is_file() and REFRESH_PLAN.is_file(), "Oct 13 disc or the dated refresh plan absent")
class RosterWriterTests(unittest.TestCase):
    """The build's own refresh and import floor on the refresh's pinned base (the Oct 13 pack roster)."""

    @classmethod
    def setUpClass(cls):
        cls.base = rr.load_image(OCT13_DISC).to_body()
        cls.plan = json.loads(REFRESH_PLAN.read_text(encoding="utf-8"))["roster_refresh"]
        cls.data = depth.load()

    def test_the_fit_keeps_two_imports_and_ten_created_players_and_lists_everyone(self):
        count, body, floor = depth.fit(self.base, self.plan, self.data, margin=10)
        self.assertGreaterEqual(count, 15)
        self.assertGreaterEqual(floor["vacancies_after"], capacity.IMPORT_FLOOR + 10)
        self.assertEqual(capacity.import_vacancies(body), floor["vacancies_after"])
        doc = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
        listed = {(doc.by_offset[o].first, doc.by_offset[o].last) for o in doc.free_agents}
        for p in self.data["players"][:count]:
            self.assertIn((p["first"], p["last"]), listed)
        self.assertEqual(len(doc.free_agents), len(self.plan["free_agents"]) + count)
        # one more player would cost the margin: the count is the largest that fits
        if count < len(self.data["players"]):
            more, _ = depth.apply_with_floor(self.base, depth.extend_plan(self.plan, self.data, count + 1, self.base))
            self.assertLess(capacity.import_vacancies(more), capacity.IMPORT_FLOOR + 10)

    def test_the_written_plan_replays_byte_identically(self):
        plan = depth.extend_plan(self.plan, self.data, 5, self.base)
        once, _ = depth.apply_with_floor(self.base, plan)
        twice, receipt = depth.apply_with_floor(once, plan)
        self.assertEqual(twice, once)
        self.assertTrue(receipt["roster_refresh"]["import_floor"]["already_applied"])


def released_with_depth(count):
    """The released main roster plus the first ``count`` players, written as the refresh writes a new row."""
    from mod_editor.core import nfl2k5_college_check as college
    body = rr.load_image(RELEASED_DISC).to_body()
    doc = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
    listed = set(doc.free_agents)
    vacant = [p for p in doc.by_pool("primary") if p.index >= depth.FIRST_VACANT and p.group == "pool"
              and p.offset not in listed and body[p.offset + 8] & 5 == 1 and p.first == p.last == up.BLANK_NAME]
    for p, row in zip(vacant, depth.load()["players"][:count]):
        names = {k: p.record.values[k] for k in ("first_name_pointer", "last_name_pointer")}
        p.record = rr.PlayerRecord.decode(bytes(rr.PLAYER_SIZE), scheme="one_pool", reference_year=2026)
        p.record.values.update(names)
        for key, value in dict(row["fields"], photo_id=depth.PHOTO_BASE + p.index).items():
            p.record.set(key, value)
        p.record.set("player_type", rr.FLAG_NFL_PLAYER)
        doc.set_name(p, "first", row["first"])
        doc.set_name(p, "last", row["last"])
        doc.set_college(p, college.resolve_index(doc.colleges, row["college"]))
        doc.free_agents.append(p.offset)
    doc._reindex_membership()
    return doc.to_body(normalise_commentary=False)


@unittest.skipUnless(RELEASED_DISC.is_file() and (NOAH_SAVE / "SAVEGAME.DAT").is_file(),
                     "released disc or the MyNFL3 copy absent")
class FranchiseUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.disc = released_with_depth(19)
        cls.container = rr.SaveContainer.load(NOAH_SAVE, require_signature=True)

    def test_an_existing_franchise_gains_the_new_free_agents_inside_its_own_records(self):
        payload = self.container.savegame
        out, step = up.sync_free_agents(payload, self.disc)
        self.assertEqual(len(out), len(payload))
        self.assertGreater(len(step["changes"]), 0)
        self.assertEqual(step["changes"][0]["player"], "Colin Kaepernick")
        self.assertEqual(step["vacant_records_after"], up.SAVE_KEEP_VACANCIES)
        self.assertEqual(step["free_agents_after"], step["free_agents_before"] + len(step["changes"]))
        up.validate_save(out)
        again, second = up.sync_free_agents(out, self.disc)
        self.assertEqual((again, second["changes"]), (out, []))          # replay is a no-op
        self.assertEqual(len(second["already_in_franchise"]), len(step["changes"]))

    def test_no_room_refuses_the_free_agents_command_and_skips_inside_upgrade(self):
        payload = self.container.savegame
        out, step = up.sync_free_agents(payload, self.disc, keep=10_000)
        self.assertEqual((out, step["changes"]), (payload, []))
        with self.assertRaises(up.UpgradeRefused):
            up.sync_free_agents(payload, self.disc, keep=10_000, strict=True)

    def test_free_agents_is_a_command_and_part_of_upgrade(self):
        self.assertIn("free-agents", service.COMMANDS)
        import tools.nfl2k5_franchise_upgrade as cli
        self.assertEqual(cli.COMMANDS, service.COMMANDS)
        with tempfile.TemporaryDirectory() as td:
            disc = Path(td) / "disc.iso"
            disc.write_bytes(b"synthetic disc fingerprint")
            with patch.object(service, "load_disc", return_value=(self.disc, {})):
                plan = service.plan_upgrade(NOAH_SAVE, disc, command="free-agents")
            self.assertEqual([s["operation"] for s in plan.receipt["steps"]], ["free_agents"])
            self.assertEqual(plan.receipt["changed_fields"], len(plan.receipt["steps"][0]["changes"]))


if __name__ == "__main__":
    unittest.main()
