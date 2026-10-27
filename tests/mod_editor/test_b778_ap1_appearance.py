"""b778 ap1: every real player the dated refresh creates gets a measured appearance.

The table is the b778 fa5 method measured on the 2026 nfl.com headshots: YuNet face box, cheek/forehead/nose
ITA -> native tone 0..5, body from height/weight BMI, a native generic face of that tone, and the dreads bit only
from a checked hanging-locs list.  The high-key 2026 photo set made the raw ITA tones too light for several dark
faces, so each headshot was reviewed by eye; the raw measurement, the reviewed tone and the confidence stay in
the data file, and every disagreement is listed for review.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_created_appearance as appearance  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_roster_refresh as refresh  # noqa: E402
import test_nfl2k5_roster_records as fixture  # noqa: E402

SCRATCH = Path(os.environ.get("NFL2K5_B778_SCRATCH", ""))
DISCS = Path(os.environ.get("NFL2K5_DISC_FOLDER", ""))
OCT13_DISC = DISCS / "SOFTDRINK 2K28 v0.6.1 fixes (2026-10-13).xiso.iso"
REFRESH_PLAN = SCRATCH / "rt1/out/roster-edits-b778-rt1.json"
GOULD = "00-0039816"
ZEITLER = "00-0029592"
DREADS = {"Deatrich Wise", "K'Von Wallace", "Ifeatu Melifonwu", "Terell Smith", "Nate Lynn", "Kenneth Grant",
          "Torricelli Simpkins",
          # coordinator 10/25 (viewed the headshot sheets): hanging locs the first pass missed
          "Larrell Murchison", "Michael Carter", "Cam Jones", "Starling Thomas", "Mitchell Tinsley", "Theo Wease",
          "Shemar Turner", "Kayden McDonald"}


def blank_player(document, index):
    player = document.by_pool("primary")[index]
    player.record = rr.PlayerRecord.decode(bytes(rr.PLAYER_SIZE), scheme="one_pool", reference_year=2026)
    player.record.set("player_type", rr.FLAG_NFL_PLAYER)
    return player


class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = appearance.load_data()

    def test_the_table_covers_the_90_dated_refresh_players_with_measure_and_confidence(self):
        players = self.data["players"]
        self.assertEqual(len(players), 90)
        self.assertEqual(len(set(players)), 90)
        for gsis, entry in players.items():
            self.assertRegex(gsis, r"^\d{2}-\d{7}$")
            self.assertTrue(entry["name"])
            self.assertTrue(entry["method"].startswith("nflverse players.csv headshot"))
            self.assertEqual(entry["measure"]["detector"], "yunet-2023mar")
            self.assertIn("ita", entry["measure"])
            self.assertIn("bmi", entry["measure"])
            self.assertIn(entry["confidence"], ("measured", "reviewed", "low"))
            self.assertTrue(entry["appearance_reviewed"])
            self.assertTrue((entry["measure"].get("source_url") or "").startswith("https://"))
        counts = self.data["counts"]
        self.assertEqual(counts["players"], 90)
        self.assertEqual(counts["measured"] + counts["reviewed"] + counts["low"], 90)
        self.assertEqual(counts["dreads"], len(DREADS))

    def test_every_non_measured_face_is_listed_for_review(self):
        players = self.data["players"]
        listed = {(r["gsis_id"], r["confidence"]) for r in self.data["review"]}
        for gsis, entry in players.items():
            if entry["confidence"] != "measured":
                self.assertIn((gsis, entry["confidence"]), listed)
            if entry["confidence"] == "low":
                self.assertTrue(entry.get("review_reason"))

    def test_tone_ranges_faces_and_the_hair_list(self):
        players = self.data["players"]
        for entry in players.values():
            self.assertIn(entry["skin"], range(6))
            self.assertIn(entry["face"], range(7))
            self.assertIn(entry["body"], range(4))
            self.assertIn(entry["dreads"], (0, 1))
        self.assertEqual({p["name"] for p in players.values() if p["dreads"]}, DREADS)
        # long-haired white players keep the dreads bit off; the hs1 hair style stays their own
        for name in ("Kristian Welch", "Brenden Schooler", "Carson Steele"):
            self.assertEqual(next(p for p in players.values() if p["name"] == name)["dreads"], 0)
        # the high-key 2026 photos are exactly why the table records a visual correction
        self.assertEqual(players[GOULD]["measure"]["ita_skin"], 1)
        self.assertEqual(players[GOULD]["skin"], 3)
        self.assertEqual(players[ZEITLER]["skin"], 0)
        self.assertEqual(players[ZEITLER]["body"], 3)      # 6-4, 315 lb -> Extra Large


class ApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = appearance.load_data()
        cls.body = fixture.synthetic_body()

    def test_a_created_player_takes_the_measured_skin_face_body_and_checked_dreads(self):
        document = rr.RosterDocument(self.body, scheme="one_pool", reference_year=2026)
        player = blank_player(document, 0)
        written = appearance.apply(player, {}, GOULD, self.data)
        self.assertEqual(written, {"skin": 3, "face": 3, "body": 1, "dreads": 0})
        for name, value in written.items():
            self.assertEqual(player.record.get(name), value)
        self.assertEqual(player.record.get("hair_style"), 0)
        self.assertEqual(player.record.get("photo_id"), 0)

    def test_a_dreads_player_keeps_hair_style_and_photo(self):
        document = rr.RosterDocument(self.body, scheme="one_pool", reference_year=2026)
        player = blank_player(document, 0)
        player.record.set("hair_style", 2)
        player.record.set("photo_id", 7100)
        written = appearance.apply(player, {}, "00-0033947", self.data)   # Deatrich Wise
        self.assertEqual(written["dreads"], 1)
        self.assertEqual(player.record.get("hair_style"), 2)
        self.assertEqual(player.record.get("photo_id"), 7100)

    def test_an_authored_appearance_wins_even_when_the_identity_is_known(self):
        document = rr.RosterDocument(self.body, scheme="one_pool", reference_year=2026)
        player = blank_player(document, 0)
        player.record.set("skin", 0)
        player.record.set("face", 5)
        before = player.record.encode()
        self.assertEqual(appearance.apply(player, {"skin": 0, "face": 5, "dreads": 0}, GOULD, self.data), {})
        self.assertEqual(player.record.encode(), before)

    def test_a_real_portrait_or_authored_face_is_never_replaced(self):
        document = rr.RosterDocument(self.body, scheme="one_pool", reference_year=2026)
        player = blank_player(document, 0)
        before = player.record.encode()
        self.assertEqual(appearance.apply(player, {"photo_id": 4000}, GOULD, self.data), {})
        self.assertEqual(player.record.encode(), before)

    def test_an_all_zero_appearance_is_treated_as_created_and_measured(self):
        document = rr.RosterDocument(self.body, scheme="one_pool", reference_year=2026)
        player = blank_player(document, 0)
        written = appearance.apply(player, {"skin": 0, "face": 0, "body": 0, "dreads": 0}, GOULD, self.data)
        self.assertEqual(written, {"skin": 3, "face": 3, "body": 1, "dreads": 0})

    def test_the_measured_body_replaces_a_generic_row_body(self):
        document = rr.RosterDocument(self.body, scheme="one_pool", reference_year=2026)
        player = blank_player(document, 0)
        written = appearance.apply(player, {"body": 2}, ZEITLER, self.data)
        self.assertEqual(written["body"], 3)
        self.assertEqual(player.record.get("body"), 3)

    def test_an_unmeasured_identity_is_left_alone(self):
        document = rr.RosterDocument(self.body, scheme="one_pool", reference_year=2026)
        player = blank_player(document, 0)
        before = player.record.encode()
        self.assertEqual(appearance.apply(player, {}, "id0000", self.data), {})
        self.assertEqual(player.record.encode(), before)

    def test_the_receipt_separates_measured_reviewed_low_and_missing(self):
        players = self.data["players"]
        measured = next(g for g, p in players.items() if p["confidence"] == "measured")
        reviewed = next(g for g, p in players.items() if p["confidence"] == "reviewed")
        low = next(g for g, p in players.items() if p["confidence"] == "low")
        rec = appearance.receipt([measured, reviewed, low, "missing-id"],
                                 {measured: {}, reviewed: {}, low: {}}, self.data)
        self.assertEqual(rec["created"], 4)
        self.assertEqual(rec["filled"], 3)
        self.assertEqual(rec["missing_from_table"], ["missing-id"])
        self.assertEqual(len(rec["reviewed"]), 1)
        self.assertEqual(len(rec["low_confidence"]), 1)
        self.assertEqual(rec["measured"], 1)


@unittest.skipUnless(OCT13_DISC.is_file() and REFRESH_PLAN.is_file(),
                     "Oct 13 disc or the dated refresh plan absent")
class RealPlanTests(unittest.TestCase):
    """The build's own refresh on its pinned base: exactly the 90 created records gain the measured appearance."""

    @classmethod
    def setUpClass(cls):
        cls.data = appearance.load_data()
        cls.base = rr.load_image(OCT13_DISC).to_body()
        cls.plan = json.loads(REFRESH_PLAN.read_text(encoding="utf-8"))["roster_refresh"]
        cls.out, cls.receipt = refresh.apply_body(cls.base, cls.plan)
        cls.before = rr.RosterDocument(cls.base, scheme="one_pool", reference_year=2026)
        cls.after = rr.RosterDocument(cls.out, scheme="one_pool", reference_year=2026)

    def test_all_90_created_players_get_their_measured_appearance(self):
        created = [row for row in self.plan["players"] if row.get("new")]
        self.assertEqual(len(created), 90)
        self.assertEqual(self.receipt["appearance"]["filled"], 90)
        self.assertEqual(self.receipt["appearance"]["missing_from_table"], [])
        self.assertEqual(self.receipt["appearance"]["not_measured"], [])
        for row in created:
            expected = self.data["players"][row["gsis_id"]]
            player = self.after.by_pool("primary")[row["index"]]
            self.assertEqual(player.first, row["first"])
            self.assertEqual(player.last, row["last"])
            for name in appearance.APPEARANCE_FIELDS:
                self.assertEqual(player.record.get(name), expected[name], (row["first"], row["last"], name))
            self.assertEqual(player.record.get("photo_id"), 7100)

    def test_no_existing_player_appearance_changes(self):
        created = {row["index"] for row in self.plan["players"] if row.get("new")}
        for old in self.before.by_pool("primary"):
            if old.index in created:
                continue
            new = self.after.by_pool("primary")[old.index]
            for name in appearance.APPEARANCE_FIELDS + ("hair_style", "photo_id"):
                self.assertEqual(old.record.get(name), new.record.get(name), (old.index, name))

    def test_every_measured_entry_is_a_created_row_never_a_draft_bank_record(self):
        draft = {p.index for p in self.after.by_pool("primary") if p.group == "draft_class"}
        created = {row["index"] for row in self.plan["players"] if row.get("new")}
        self.assertFalse(created & draft)
        names = {(row["first"], row["last"]) for row in self.plan["players"] if row.get("new")}
        self.assertEqual({(p["name"].split(" ", 1)[0], p["name"].split(" ", 1)[1])
                          for p in self.data["players"].values()}, names)

    def test_a_replay_keeps_the_first_appearance(self):
        again, receipt = refresh.apply_body(self.out, self.plan)
        self.assertEqual(again, self.out)
        self.assertEqual(receipt["appearance"]["filled"], 0)
        self.assertEqual(receipt["appearance"]["created"], 0)


if __name__ == "__main__":
    unittest.main()
