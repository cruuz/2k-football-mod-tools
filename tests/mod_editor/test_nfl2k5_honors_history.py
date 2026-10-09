"""Job F5 (beta 77): sourced honors into the career-stat pool, and the shipped data file. EXPERIMENTAL / UNWITNESSED.

Synthetic disc ROST bodies (the history tests' builder) prove the writer: honors land in the season slot the card
reads (``years_pro - (2026 - season)``), at the stream head in the regular-season class, idempotently, with every
other word, pointer and byte outside the pool unchanged; wrong identities, unknown honors and unlisted sources are
refused. The data-file tests check the shipped ``data/nfl2k5_honors_2026.json``: schema, every honor cited by a
pinned source, counting rules, and a few well-known careers against the sources.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_career_stats as cs  # noqa: E402
from mod_editor.core import nfl2k5_honors as honors  # noqa: E402
from mod_editor.core import nfl2k5_honors_history as hh  # noqa: E402
from tests.mod_editor.test_nfl2k5_team_history import entry, games, synthetic_body  # noqa: E402

SHA = "a" * 64
V05_PACK0 = Path(os.environ.get("NFL2K5_V05_PACK0", "/home/noah/2k-worktrees/.b77-scratch/f5/disc_v05/vc_53450030/0"))


def body_with(players):
    body = bytearray(synthetic_body([dict(position=0, **p) for p in players]))
    struct.pack_into("<i", body, 0x14, 0x2D)     # the root pointer the general decoder expects (as test_franchise_history)
    return bytes(body)


def doc(players, sources=None):
    return {"schema": hh.SCHEMA, "base_year": 2026,
            "sources": sources if sources is not None else {"src": {"url": "https://example.invalid/x", "sha256": SHA}},
            "players": players}


def honors_of(body, key=("primary", 0)):
    words = cs.decode_body(body).history_words[key]
    return [(w >> 16 & 0x7F, w >> 23 & 31, w & 0xFFFF, bool(w & 0x20000000)) for w in words if 96 <= (w >> 16 & 0x7F) <= 105]


class WriterTests(unittest.TestCase):
    def setUp(self):
        self.body = body_with([
            dict(first="Pat", last="Star", birth=dt.date(1995, 9, 17), count=9, stream=games(range(9))),
            dict(first="New", last="Guy", birth=dt.date(2003, 1, 1), count=1, stream=None),
            dict(first="Old", last="Hand", birth=dt.date(1984, 1, 1), count=4, stream=games([1, 2, 3], extra=(entry(2, 87, 5),))),
        ])
        self.data = doc([
            {"pool": "primary", "index": 0, "first": "Pat", "last": "Star", "birth_date": "1995-09-17",
             "honors": [{"season": 2018, "honor": "mvp", "source": "src"}, {"season": 2022, "honor": "mvp", "source": "src"},
                        {"season": 2019, "honor": "super_bowl", "source": "src"},
                        {"season": 2019, "honor": "super_bowl_mvp", "source": "src"}]},
            {"pool": "primary", "index": 1, "first": "New", "last": "Guy", "birth_date": "2003-01-01",
             "honors": [{"season": 2025, "honor": "oroy", "source": "src"}]},
        ])

    def test_slots_follow_years_pro_and_class_is_regular(self):
        out, receipt = hh.apply_body(self.body, self.data)
        # years pro 9: 2026 is slot 9, so 2018 -> 1, 2019 -> 2, 2022 -> 5; years pro 1: 2025 -> slot 0
        self.assertEqual(sorted(honors_of(out)), [(96, 1, 1, False), (96, 5, 1, False), (101, 2, 1, False), (102, 2, 1, False)])
        self.assertEqual(honors_of(out, ("primary", 1)), [(99, 0, 1, False)])
        self.assertEqual(receipt["added"], 5)
        self.assertEqual(receipt["skipped"], [])
        self.assertTrue(receipt["changed"])

    def test_existing_words_and_other_players_are_unchanged(self):
        before = cs.decode_body(self.body)
        out, _ = hh.apply_body(self.body, self.data)
        after = cs.decode_body(out)
        self.assertEqual(after.history_words["primary", 2], before.history_words["primary", 2])
        old = list(before.history_words["primary", 0])
        new = list(after.history_words["primary", 0])
        self.assertEqual(new[len(new) - len(old):], old)                      # inserted at the head, like the game
        self.assertEqual(after.pool_used, before.pool_used + 5)

    def test_idempotent_and_partial_reapply(self):
        out, _ = hh.apply_body(self.body, self.data)
        again, receipt = hh.apply_body(out, self.data)
        self.assertEqual(again, out)
        self.assertFalse(receipt["changed"])
        self.assertEqual(receipt["already_present"], 5)

    def test_seasons_without_a_completed_slot_are_skipped(self):
        data = copy.deepcopy(self.data)
        data["players"][1]["honors"].append({"season": 2023, "honor": "pro_bowl", "source": "src"})   # before his rookie year
        out, receipt = hh.apply_body(self.body, data)
        self.assertEqual(len(receipt["skipped"]), 1)
        self.assertEqual(honors_of(out, ("primary", 1)), [(99, 0, 1, False)])

    def test_read_body_round_trip_and_csv(self):
        out, _ = hh.apply_body(self.body, self.data)
        rows = hh.read_body(out, 2026)
        got = sorted((r["index"], r["season"], r["honor"]) for r in rows)
        self.assertEqual(got, [(0, 2018, "mvp"), (0, 2019, "super_bowl"), (0, 2019, "super_bowl_mvp"), (0, 2022, "mvp"),
                               (1, 2025, "oroy")])
        text = hh.to_csv([{**r, "source": "src"} for r in rows])
        again = hh.from_csv(text, 2026, self.data["sources"])
        self.assertEqual(hh.apply_body(self.body, again)[0], out)

    def test_refusals(self):
        bad = []
        x = copy.deepcopy(self.data); x["players"][0]["first"] = "Wrong"; bad.append(x)
        x = copy.deepcopy(self.data); x["players"][0]["birth_date"] = "1990-01-01"; bad.append(x)
        x = copy.deepcopy(self.data); x["players"][0]["honors"][0]["honor"] = "heisman"; bad.append(x)
        x = copy.deepcopy(self.data); x["players"][0]["honors"][0]["source"] = "unlisted"; bad.append(x)
        x = copy.deepcopy(self.data); x["players"][0]["honors"][0]["season"] = 2026; bad.append(x)
        x = copy.deepcopy(self.data); x["players"][0]["honors"].append(dict(x["players"][0]["honors"][0])); bad.append(x)
        x = copy.deepcopy(self.data); x["sources"]["src"]["sha256"] = "bad"; bad.append(x)
        x = copy.deepcopy(self.data); x["players"][0]["index"] = 7; bad.append(x)
        for data in bad:
            with self.subTest(data=data), self.assertRaises(hh.HonorsHistoryError):
                hh.apply_body(self.body, data)

    def test_fields_match_the_page_owner(self):
        self.assertEqual(hh.FIELDS, honors.FIELDS)
        self.assertEqual(hh.HONORS, honors.HONORS)


class DataFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = hh.load()

    def test_schema_sources_and_rules(self):
        hh.validate(self.data)
        self.assertEqual(self.data["base_year"], 2026)
        self.assertEqual(set(self.data["rules"]), set(hh.HONORS))
        for key, pin in self.data["sources"].items():
            self.assertTrue(pin["url"].startswith(("https://en.wikipedia.org/w/index.php?title=",
                                                   "https://github.com/nflverse/")), key)
            if pin.get("publisher") == "Wikipedia":
                self.assertIn("oldid=", pin["url"])
        cited = {h["source"] for p in self.data["players"] for h in p["honors"]}
        self.assertTrue(cited <= set(self.data["sources"]))

    def test_counts_match_the_rows(self):
        from collections import Counter
        counts = Counter(h["honor"] for p in self.data["players"] for h in p["honors"])
        self.assertEqual(dict(counts), self.data["counts"])
        self.assertGreater(counts["pro_bowl"], 500)
        self.assertGreater(counts["super_bowl"], 150)

    def career(self, first, last):
        rows = [p for p in self.data["players"] if p["first"] == first and p["last"] == last]
        self.assertEqual(len(rows), 1, (first, last))
        out = {}
        for h in rows[0]["honors"]:
            out.setdefault(h["honor"], []).append(h["season"])
        return out

    def test_well_known_careers(self):
        mahomes = self.career("Patrick", "Mahomes")
        self.assertEqual(mahomes["mvp"], [2018, 2022])
        self.assertEqual(mahomes["super_bowl_mvp"], [2019, 2022, 2023])
        self.assertEqual(mahomes["super_bowl"], [2019, 2022, 2023])
        rodgers = self.career("Aaron", "Rodgers")
        self.assertEqual(rodgers["mvp"], [2011, 2014, 2020, 2021])
        self.assertEqual(rodgers["super_bowl"], [2010])
        self.assertEqual(self.career("Lamar", "Jackson")["mvp"], [2019, 2023])
        self.assertEqual(self.career("Josh", "Allen")["mvp"], [2024])
        self.assertEqual(self.career("Matthew", "Stafford")["mvp"], [2025])
        self.assertEqual(self.career("Kenneth", "Walker")["super_bowl_mvp"], [2025])
        self.assertEqual(self.career("Derrick", "Henry")["rushing_title"], [2019, 2020])

    @unittest.skipUnless(V05_PACK0.is_file(), "the v0.5 PACK0 extraction is absent")
    def test_applies_to_the_v05_roster(self):
        pack = V05_PACK0.read_bytes()
        _n, _size, blocks = struct.unpack_from("<3I", pack, 0x9C + 5 * 12)
        body = pack[blocks * 0x800 + 0x20: blocks * 0x800 + 0x20 + 0x90F60]
        out, receipt = hh.apply_body(body, self.data)
        self.assertEqual(receipt["added"] + len(receipt["skipped"]), sum(len(p["honors"]) for p in self.data["players"]))
        self.assertLessEqual(receipt["used_after"], receipt["capacity"])
        self.assertEqual(hh.apply_body(out, self.data)[0], out)


if __name__ == "__main__":
    unittest.main()
