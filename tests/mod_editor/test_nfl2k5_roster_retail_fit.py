"""b780 m64a: the pack's 2026 roster edits at retail roster capacity (tools/nfl2k5_roster_retail_fit.py).

Portable tests check the plan surgery on small synthetic refreshes: the depth rows are the only rows the variant
re-addresses, a non-depth row in an appended record is refused, and the base pin is enforced. The private tests (read
only; each skips without its inputs) run the real tool on the SOFTDRINK v0.9 roster edits and the refresh's pinned
base with the build's own writers and pin the result: 19 of the 533 dated depth free agents fit retail capacity at
fa3's margin (the same 19 rows, on the same records, that v0.9 used), every club is identical to v0.9's capacity route
on the same base, and against the shipped v0.9 RC disc's roster the trim adds no club difference.

Private inputs:
  NFL2K5_B780_ROSTER_EDITS_V09  the v0.9 pack roster edits (ship10/inputs/roster-edits-v09.json)
  NFL2K5_B780_REFRESH_BASE      the refresh's pinned base body (i4/inputs/ro1/baseline.body, sha256 12701297...)
  NFL2K5_B780_RC_ROST           optional: the v0.9 RC disc's main ROST (outer entry 5, 827,488 B)
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_spare_capacity as capacity  # noqa: E402
from tools import nfl2k5_roster_retail_fit as fit  # noqa: E402

V09 = Path(os.environ.get("NFL2K5_B780_ROSTER_EDITS_V09",
                          "/home/noah/2k-worktrees/.b77-scratch/ship10/inputs/roster-edits-v09.json"))
BASE = Path(os.environ.get("NFL2K5_B780_REFRESH_BASE", "/home/noah/2k-worktrees/.b77-scratch/i4/inputs/ro1/baseline.body"))
RC_ROST = Path(os.environ.get("NFL2K5_B780_RC_ROST", "/media/noah/Storage/2K5-project/mem1/fixtures/rc_rost.bin"))
BASE_SHA256 = "12701297fd05f86ff513acad4363dbe059cdb499d95d13976acb16dd87f8c98e"


def depth_row(priority, index):
    return {"index": index, "new": True, "first": f"F{priority}", "last": f"L{priority}", "fa3_priority": priority,
            "fields": {"photo_id": 20000 + index, "jersey": priority}}


def refresh(depth_indices=(2554, 2619, 2700)):
    rows = [{"index": 2464, "new": True, "first": "Signed", "last": "Player", "fields": {}}]
    rows += [depth_row(p, i) for p, i in enumerate(depth_indices, 1)]
    return {"schema": "nfl2k5.roster_refresh.v1", "players": rows, "free_agents": [7, 2464] + list(depth_indices),
            "identity_guards": [[0, "A", "B", "2000-01-01"]],
            "teams": [{"index": 0, "team": "SF", "active": [1, 2, 3], "reserves": [4], "specialists": {"k": 3}}]}


class PlanSurgeryTests(unittest.TestCase):
    def test_split_takes_the_depth_rows_and_their_free_agent_pointers_only(self):
        stripped, rows = fit.split(refresh())
        self.assertEqual([r["fa3_priority"] for r in rows], [1, 2, 3])
        self.assertEqual([p["index"] for p in stripped["players"]], [2464])
        self.assertEqual(stripped["free_agents"], [7, 2464])
        self.assertEqual(stripped["teams"], refresh()["teams"])

    def test_kept_rows_take_the_vacancies_in_order_with_fa3_addressing(self):
        stripped, rows = fit.split(refresh())
        out = fit.plan_with(stripped, rows, [2554, 2555, 2556], 2)
        moved = out["players"][1:]
        self.assertEqual([(m["fa3_priority"], m["index"], m["fields"]["photo_id"]) for m in moved],
                         [(1, 2554, 22554), (2, 2555, 22555)])
        self.assertEqual(out["free_agents"], [7, 2464, 2554, 2555])
        self.assertEqual({k: v for k, v in moved[1].items() if k not in ("index", "fields")},
                         {k: v for k, v in rows[1].items() if k not in ("index", "fields")})
        with self.assertRaises(fit.RetailFitError):
            fit.plan_with(stripped, rows, [2554], 2)

    def test_only_non_depth_rows_in_appended_records_are_capacity_dependencies(self):
        document = {"edits": [{"index": 5}], "roster_refresh": refresh()}
        self.assertEqual(fit.capacity_dependencies(document), {})            # depth rows at 2619 and 2700 are the fit's
        grown = copy.deepcopy(document)
        grown["roster_refresh"]["teams"][0]["active"].append(2650)
        grown["edits"].append({"index": 2620, "pool": "primary"})
        grown["edits"].append({"index": 2621, "pool": "secondary"})           # another pool's numbering
        self.assertEqual(fit.capacity_dependencies(grown), {"edits": [2620], "roster_refresh.teams.active": [2650]})

    def test_the_base_must_be_the_refresh_pin(self):
        document = {"schema": rr.EDITS_SCHEMA, "edits": [], "roster_refresh": refresh(),
                    "fa3_free_agent_depth": {"base_sha256": "0" * 64}}
        with self.assertRaisesRegex(fit.RetailFitError, "pinned base"):
            fit.retail_variant(document, bytes(capacity.BODY_SIZE))
        document["free_agent_capacity"] = {"base_sha256": "1" * 64}
        with self.assertRaisesRegex(fit.RetailFitError, "different bases"):
            fit.recorded_base(document)


def _private_ready():
    return V09.is_file() and BASE.is_file() and BASE.stat().st_size == capacity.BODY_SIZE


@unittest.skipUnless(_private_ready(), "the retail fit proof needs the v0.9 roster edits and the refresh's pinned base")
class SoftdrinkV09RetailFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = V09.read_bytes()
        cls.source = json.loads(cls.raw.decode("utf-8"))
        cls.base = BASE.read_bytes()
        if hashlib.sha256(cls.base).hexdigest() != BASE_SHA256:
            raise unittest.SkipTest("the refresh base is not the pinned 12701297... body")
        cls.variant, cls.receipt = fit.retail_variant(cls.source, cls.base, source_sha256=hashlib.sha256(cls.raw).hexdigest())
        cls.folder = tempfile.TemporaryDirectory(prefix="retail-fit-")
        cls.path = Path(cls.folder.name) / "roster-edits-retail.json"
        cls.path.write_text(json.dumps(cls.variant, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        rost = RC_ROST.read_bytes() if RC_ROST.is_file() and RC_ROST.stat().st_size == 827488 else None
        cls.has_disc = rost is not None
        cls.report = fit.validate(cls.variant, cls.source, cls.base, compare_rost=rost, variant_path=cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_19_of_the_533_depth_free_agents_fit_retail_capacity(self):
        r = self.receipt
        self.assertEqual((r["depth_candidates"], r["depth_kept"], r["depth_dropped"]), (533, 19, 514))
        self.assertEqual((r["vacant_records"], r["import_vacancies_after_floor"], r["import_floor"]), (65, 116, 106))
        self.assertEqual((r["import_floor_added_records"], r["primary_after_floor"]), (70, 2689))
        self.assertEqual((r["free_agents_before"], r["free_agents_after"], r["removed_capacity_records"]), (879, 365, 612))

    def test_the_kept_rows_are_v09s_own_rows_on_the_same_records(self):
        kept = fit.depth_rows(self.variant["roster_refresh"])
        source = fit.depth_rows(self.source["roster_refresh"])
        self.assertEqual(kept, source[:19])                                 # byte for byte: 2554..2572 in both
        self.assertEqual([p["index"] for p in kept], list(range(2554, 2573)))
        self.assertNotIn("free_agent_capacity", self.variant)
        self.assertEqual(fit.capacity_dependencies(self.variant), {})

    def test_the_build_writers_accept_it_and_every_club_matches_v09(self):
        failed = [c for c in self.report["checks"] if not c["ok"]]
        self.assertEqual(failed, [])
        names = {c["check"] for c in self.report["checks"]}
        self.assertIn("every club identical to the source's capacity route (membership and depth order)", names)
        self.assertIn("mod_build reads no capacity records (no arena growth, no K128 demand)", names)
        s = self.report["summary"]
        self.assertEqual(s["body_bytes"], capacity.BODY_SIZE)
        self.assertEqual((s["club_players"], s["import_vacancies"], s["primary_records"]), (32 * 53, 116, 2689))
        self.assertEqual(s["created_history"]["players_not_in_roster"], 514)

    def test_against_the_shipped_rc_disc_the_trim_adds_no_club_difference(self):
        if not self.has_disc:
            self.skipTest("needs the v0.9 RC disc's main ROST (NFL2K5_B780_RC_ROST)")
        disc = self.report["summary"]["disc_comparison"]
        self.assertGreaterEqual(disc["clubs_identical_to_disc"], 28)
        self.assertIn("the trim adds no club difference to the disc built from the source",
                      {c["check"] for c in self.report["checks"] if c["ok"]})


if __name__ == "__main__":
    unittest.main()
