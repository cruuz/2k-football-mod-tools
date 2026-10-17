"""b775 mo1: Anniversary moments with both sides the same team (Noah's 10/17 video of the i4 test disc).

Native (Unicorn) replay of the game's own select handler 20CB30, Load Historic Team 2D17B0 and the practice-squad
importer on a built disc's executable, SITU and team files, with its main ROST as built and after the import floor.
Also the Studio's roster path: the dated refresh plan on the Oct 13 pack roster, with and without the floor.
Private inputs (read only): the played discs and the refresh plan; every test skips without them.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_spare_capacity as capacity  # noqa: E402

DISCS = Path(os.environ.get("NFL2K5_DISC_FOLDER", "/media/noah/Storage/2K5 Discs"))
I4_DISC = DISCS / "SOFTDRINK 2K28 v0.6.1 i4 test (2026-10-17).xiso.iso"
OCT13_DISC = DISCS / "SOFTDRINK 2K28 v0.6.1 fixes (2026-10-13).xiso.iso"
REFRESH_PLAN = Path(os.environ.get(
    "NFL2K5_REFRESH_PLAN",
    "/home/noah/2k-worktrees/.b77-scratch/i4/studio-work/sources/assets/files/"
    "29c4ba3bf96967ecb8f6_roster-edits-hback-2026-10-14.json"))
# physical row -> (away, home) the moment names; every one was home-versus-home on the i4 disc
ROWS = {1: ("Cowboys '71", "Packers '66"), 27: ("Giants '07", "Patriots '07"), 28: ("Steelers '08", "Cardinals '08"),
        35: ("Saints '09", "Colts '09"), 36: ("Eagles '10", "Giants '10")}


def main_rost(disc):
    from mod_editor.core import nfl2k5_music_archive as archive
    with archive.Disc(disc, descriptors=()) as d:
        entry = d.archive_entries[5]
        return d.read_entry_range(entry, 0, entry.size)


def body_of(resource):
    return resource[32:32 + struct.unpack_from("<I", resource, 4)[0]]


def with_body(resource, body):
    size = struct.unpack_from("<I", resource, 4)[0]
    return resource[:32] + body + resource[32 + size:]


def native_select(disc, rost, rows):
    """{row: (import results, away name, home name)} from the game's own code on this disc."""
    from mod_editor.core import nfl2k5_espn25_more_moments as mm
    from mod_editor.core import nfl2k5_espn25_rosters as e
    from mod_editor.core import nfl2k5_music_archive as archive
    from tools.b77 import frz_xbe_bisect as bisect
    from nfl2k5_espn25_more_moments_native import FastMomentsCPU
    payload, _ = bisect.read_xbe(disc)
    manifest, _ = e.dataset()
    data = mm.Data.load()
    with archive.Disc(disc, descriptors=()) as d:
        entries = d.archive_entries
        resources = {i: d.read_entry_range(entries[i], 0, entries[i].size)
                     for i in (5, 22, *(t["outer"] for t in manifest["resources"]))}
        resources[5] = rost
        by_id = {x.name_id: x for x in entries}
        extra = {name: d.read_entry_range(by_id[mm.name_id(name)], 0, by_id[mm.name_id(name)].size)
                 for _k, name, _e, _s, _i in mm.table_entries(data)}
        listing = [type("Entry", (), dict(index=i, name_id=x.name_id, size=x.size))() for i, x in enumerate(entries)]
        identities = {x.name_id for x in entries}
    context = e.describe_context(resources[5], resources[22], listing)
    situ = resources[22]
    cpu = FastMomentsCPU(payload, resources, context, identities,
                         situ_chunk=situ[:32 + mm.sc.u32(situ, 4)], extra_files=extra)
    order = mm.display_order(data)
    out = {}
    for row in rows:
        before = len(cpu.imports)
        cpu.select(order.index(row - 1))
        sel = cpu.selected()
        out[row] = ([i.get("result") for i in cpu.imports[before:]], sel["away"]["name"], sel["home"]["name"])
        cpu.run(0x20C3C0)
    return out


@unittest.skipUnless(I4_DISC.is_file(), "the i4 test disc is absent")
class PlayedDiscTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest(f"Unicorn unavailable: {exc}")
        cls.rost = main_rost(I4_DISC)
        body, cls.receipt = capacity.restore_import_floor(body_of(cls.rost))
        cls.repaired = with_body(cls.rost, body)

    def test_the_played_disc_has_one_import_of_vacancies(self):
        self.assertEqual(capacity.import_vacancies(body_of(self.rost)), 65)
        self.assertGreaterEqual(self.receipt["vacancies_after"], capacity.IMPORT_FLOOR)

    def test_the_game_gives_both_sides_the_home_team_on_the_played_disc(self):
        for row, (imports, away, home) in native_select(I4_DISC, self.rost, ROWS).items():
            with self.subTest(row=row):
                self.assertEqual(imports, [1, 0])               # the away file is refused
                self.assertEqual((away, home), (ROWS[row][1], ROWS[row][1]))

    def test_the_import_floor_gives_every_moment_its_two_teams(self):
        for row, (imports, away, home) in native_select(I4_DISC, self.repaired, ROWS).items():
            with self.subTest(row=row):
                self.assertEqual(imports, [1, 1])
                self.assertEqual((away, home), ROWS[row])


@unittest.skipUnless(OCT13_DISC.is_file() and REFRESH_PLAN.is_file(), "Oct 13 disc or the dated refresh plan absent")
class StudioRosterPathTests(unittest.TestCase):
    """The build's own roster writer on the Oct 13 pack roster (the refresh's pinned base)."""

    @classmethod
    def setUpClass(cls):
        cls.base = body_of(main_rost(OCT13_DISC))
        plan = json.loads(REFRESH_PLAN.read_text(encoding="utf-8"))["roster_refresh"]
        cls.directive = {"schema": rr.EDITS_SCHEMA, "edits": [], "roster_refresh": plan}

    def test_the_refresh_alone_falls_below_the_two_team_floor(self):
        self.assertEqual(capacity.import_vacancies(self.base), 155)
        out, _ = rr.apply_body(self.base, self.directive, scheme="one_pool")
        self.assertLess(capacity.import_vacancies(out), capacity.IMPORT_FLOOR)

    def test_the_refresh_with_the_floor_keeps_two_imports_and_replays(self):
        directive = dict(self.directive, restore_import_floor=True)
        out, receipt = rr.apply_body(self.base, directive, scheme="one_pool")
        floor = receipt["roster_refresh"]["import_floor"]
        self.assertGreaterEqual(capacity.import_vacancies(out), capacity.IMPORT_FLOOR)
        self.assertEqual(floor["vacancies_after"], capacity.import_vacancies(out))
        again, receipt = rr.apply_body(out, directive, scheme="one_pool")
        self.assertEqual(again, out)
        self.assertTrue(receipt["roster_refresh"]["import_floor"]["already_applied"])


if __name__ == "__main__":
    unittest.main()
