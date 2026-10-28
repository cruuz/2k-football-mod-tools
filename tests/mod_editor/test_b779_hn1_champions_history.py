"""Job hn1 (beta 79): the champions history block and the pre-franchise Super Bowls (pure Python, runs everywhere).

The block layout is the one the native owner reads and writes (``tools/nfl2k5_champions/runtime.c``; the native side is
tested in ``test_b779_hn1_champions``). Here: the data file and its sources, the club names, the packing, the checks, the
ring, and writing the seeds into a roster body.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_champions_history as history  # noqa: E402

REL_BODY = Path(os.environ.get("B779_HN1_REL_ROSTER",
                               "/home/noah/2k-worktrees/.b77-scratch/b779/rc1/work/rel_body.bin"))


def synthetic_body(size: int = 0xB0040) -> bytes:
    """A roster body ending like the Studio's arena: the reserve block, 448 spare zero bytes, the game's 224-byte tail."""

    body = bytearray(size)
    start = size - 0x400
    body[start:start + 8] = history.RESERVE_MAGIC
    body[start + 8:start + 352] = bytes((i % 251) + 1 for i in range(344))
    body[start + 800:] = bytes(((i * 3) % 255) + 1 for i in range(224))
    return bytes(body)


class DataTests(unittest.TestCase):
    def test_the_data_file_is_sourced_and_complete(self):
        data = history.load()
        self.assertEqual(data["schema"], history.SCHEMA)
        self.assertEqual([r["super_bowl"] for r in data["seasons"]], list(range(29, 61)))
        for key, pin in data["sources"].items():
            self.assertRegex(pin["sha256"], r"^[0-9a-f]{64}$", key)
            self.assertIn("oldid=%d" % pin["revision"], pin["url"], key)
        for row in data["seasons"]:
            self.assertEqual(row["season"], row["super_bowl"] + 1965)
            self.assertTrue(set(row["sources"]) <= set(data["sources"]) and row["sources"], row["super_bowl"])
            self.assertGreater(row["champion_points"], row["runner_up_points"], row["super_bowl"])
            self.assertNotEqual(row["champion"], row["runner_up"])
            self.assertTrue(row["super_bowl_mvp"] and row["season_mvp"], row["super_bowl"])

    def test_well_known_games(self):
        by = {r["super_bowl"]: r for r in history.load()["seasons"]}
        sixty = by[60]
        self.assertEqual((sixty["champion"], sixty["champion_points"], sixty["runner_up"], sixty["runner_up_points"]),
                         ("Seattle Seahawks", 29, "New England Patriots", 13))
        self.assertEqual(sixty["super_bowl_mvp"], {"name": "Kenneth Walker III", "position": "HB",
                                                   "team": "Seattle Seahawks"})
        self.assertEqual((sixty["season_mvp"]["name"], sixty["season_mvp"]["position"]), ("Matthew Stafford", "QB"))
        self.assertEqual((by[52]["champion"], by[52]["champion_points"], by[52]["super_bowl_mvp"]["name"]),
                         ("Philadelphia Eagles", 41, "Nick Foles"))
        self.assertEqual((by[53]["champion_points"], by[53]["runner_up_points"]), (13, 3))
        self.assertEqual((by[35]["champion"], by[35]["super_bowl_mvp"]["position"]), ("Baltimore Ravens", "ILB"))
        self.assertEqual((by[47]["season_mvp"]["name"], by[47]["season_mvp"]["position"]), ("Adrian Peterson", "HB"))

    def test_every_team_name_is_one_club(self):
        names = set()
        for row in history.load()["seasons"]:
            names |= {row["champion"], row["runner_up"], row["super_bowl_mvp"]["team"], row["season_mvp"]["team"]}
        for name in names:
            self.assertIn(history.club_index(name), range(32), name)
        self.assertEqual(history.club_index("St. Louis Rams"), history.CLUBS.index("Rams"))
        self.assertEqual(history.club_index("Los Angeles Rams"), history.club_index("St. Louis Rams"))
        self.assertEqual(history.club_index("Oakland Raiders"), history.CLUBS.index("Raiders"))
        self.assertEqual(history.club_index("San Diego Chargers"), history.CLUBS.index("Chargers"))
        self.assertEqual(history.club_index("Washington Commanders"), history.CLUBS.index("Redskins"))
        with self.assertRaises(history.ChampionsHistoryError):
            history.club_index("Brooklyn Dodgers")

    def test_validate_refuses_bad_data(self):
        good = history.load()
        for mutate in (lambda d: d.update(schema="x"),
                       lambda d: d["seasons"][0].update(champion_points=64),
                       lambda d: d["seasons"][0].update(sources=["nope"]),
                       lambda d: d["seasons"][0]["season_mvp"].update(position="LS"),
                       lambda d: d["seasons"].append(dict(d["seasons"][0])),
                       lambda d: d["sources"]["wiki_sbmvp"].update(sha256="12")):
            data = json.loads(json.dumps(good))
            mutate(data)
            with self.assertRaises(history.ChampionsHistoryError):
                history.validate(data)


class PackingTests(unittest.TestCase):
    def test_people_round_trip(self):
        for name, pos, want in (("Kenneth Walker III", "HB", ("K", "WALKER", "HB")),
                                ("Matthew Stafford", "QB", ("M", "STAFFORD", "QB")),
                                ("Jaxon Smith-Njigba", "WR", ("J", "SMITH-NJI", "WR")),
                                ("Amon-Ra St. Brown", "WR", ("A", "ST. BROWN", "WR")),
                                ("Marvin Harrison Jr.", "WR", ("M", "HARRISON", "WR")),
                                ("Tom O'Neil", "DE", ("T", "O'NEIL", "DE"))):
            person = history.unpack_person(history.pack_person(name, pos))
            self.assertEqual((person["initial"], person["last"], person["position"]), want, name)
        self.assertIsNone(history.unpack_person(bytes(7)))
        self.assertEqual(len(history.pack_person("A B", "QB")), 7)
        self.assertEqual(history.split_name("Kenneth Walker III"), ("Kenneth", "Walker"))
        self.assertEqual(history.split_name("Michael Pittman Jr."), ("Michael", "Pittman"))
        self.assertEqual(history.split_name("Cooper Kupp"), ("Cooper", "Kupp"))

    def test_entries_and_block(self):
        e = history.entry_bytes(60, 27, 21, 29, 13, ("Kenneth Walker III", "HB"), ("Matthew Stafford", "QB"), 23)
        self.assertEqual(len(e), history.ENTRY)
        block = history.block_bytes({60: e})
        self.assertEqual(len(block), history.USED)
        self.assertEqual(block[:10], b"2K5CHMP\0\x01\x16")
        rows = history.read_block(block)
        self.assertEqual(rows, [{"super_bowl": 60, "champion": 27, "runner_up": 21, "champion_points": 29,
                                 "runner_up_points": 13,
                                 "super_bowl_mvp": {"initial": "K", "last": "WALKER", "position": "HB"},
                                 "season_mvp": {"initial": "M", "last": "STAFFORD", "position": "QB"},
                                 "season_mvp_club": 23}])

    def test_checks_make_damage_read_as_empty(self):
        e = history.entry_bytes(60, 27, 21, 29, 13, None, None, None)
        block = bytearray(history.block_bytes({60: e}))
        for at in (0, 8, 9, 12, history.ENTRIES_AT + (60 % 22) * 19 + 2, history.USED - 1):
            damaged = bytearray(block)
            damaged[at] ^= 0x40
            self.assertEqual(history.read_block(bytes(damaged)), [], at)
        self.assertEqual(history.read_block(bytes(history.USED)), [])
        self.assertEqual(history.read_block(b"short"), [])
        # an entry stored in the wrong ring slot is skipped even with a good checksum
        wrong = bytearray(block)
        slot = history.ENTRIES_AT + (60 % 22) * 19
        wrong[history.ENTRIES_AT + 3 * 19:history.ENTRIES_AT + 4 * 19] = wrong[slot:slot + 19]
        wrong[slot:slot + 19] = bytes(19)
        wrong[12:16] = history.checksum(bytes(wrong)).to_bytes(4, "little")
        self.assertEqual(history.read_block(bytes(wrong)), [])

    def test_the_ring_keeps_22(self):
        entries = {n: history.entry_bytes(n, n % 32, (n + 1) % 32, n % 60, 3, None, None, None) for n in range(1, 60)}
        rows = history.read_block(history.block_bytes(entries))
        self.assertEqual([r["super_bowl"] for r in rows], list(range(59, 37, -1)))
        self.assertEqual(len(rows), history.RING)


class SeedTests(unittest.TestCase):
    def test_the_seeds_are_the_newest_22_before_2026(self):
        entries = history.entries_for(history.load())
        self.assertEqual(sorted(entries), list(range(39, 61)))
        rows = history.read_block(history.block_bytes(entries))
        self.assertEqual([r["super_bowl"] for r in rows], list(range(60, 38, -1)))
        self.assertEqual(rows[0]["champion"], history.CLUBS.index("Seahawks"))
        self.assertEqual(rows[0]["runner_up"], history.CLUBS.index("Patriots"))

    def test_apply_to_a_roster_body(self):
        body = synthetic_body()
        out, receipt = history.apply_body(body)
        at = len(body) - 0x400 + 352
        self.assertEqual(receipt["seasons"], 22)
        self.assertEqual((receipt["newest_super_bowl"], receipt["oldest_super_bowl"]), (60, 39))
        diff = [i for i in range(len(body)) if body[i] != out[i]]
        self.assertTrue(diff and all(at <= i < at + history.USED for i in diff))
        self.assertEqual(out[at + history.USED:at + history.SPARE], bytes(history.SPARE - history.USED))
        self.assertEqual(len(history.read_body(out)), 22)
        again, receipt2 = history.apply_body(out)                       # idempotent
        self.assertEqual(again, out)
        self.assertTrue(receipt2["unchanged"])

    def test_spare_bytes_in_use_and_missing_blocks_are_refused(self):
        body = bytearray(synthetic_body())
        at = len(body) - 0x400 + 352
        body[at + 100] = 1
        with self.assertRaises(history.ChampionsHistoryError):
            history.apply_body(bytes(body))
        with self.assertRaises(history.ChampionsHistoryError):
            history.apply_body(bytes(0xB0040))                           # no reserve block: the history is off

    @unittest.skipUnless(REL_BODY.is_file(), "the released v0.7 roster is a private fixture")
    def test_the_released_roster_takes_the_seeds_and_still_parses(self):
        from mod_editor.core import nfl2k5_roster_records as rr
        body = REL_BODY.read_bytes()
        out, receipt = history.apply_body(body)
        self.assertEqual(receipt["seasons"], 22)
        document = rr.RosterDocument(out)                                 # the Studio's parser accepts the changed arena
        self.assertEqual(len(document.teams), len(rr.RosterDocument(body).teams))
        self.assertEqual(len(history.read_body(out)), 22)
        diff = [i for i in range(len(body)) if body[i] != out[i]]
        at = len(body) - 0x400 + 352
        self.assertTrue(all(at <= i < at + history.USED for i in diff))


if __name__ == "__main__":
    unittest.main()
