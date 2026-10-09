"""Final commentary pass and the retired "double zero" cue (beta 77, job c2).

Retail-free tests build their own tables and rosters. Tests marked "retail" need the user-owned USA disc folder (and unicorn):
they run the game's own instructions (the resolver ``FUN_00067150`` and the cue lookup ``FUN_000DB370``) on the real
executable and the real ``players`` cue table, and are skipped without them. Nothing here is a gameplay result.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_commentary_final as cf  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from test_nfl2k5_roster_records import synthetic_body, SAMPLE  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)"
HAVE_RETAIL = (RETAIL / "vc_53450030" / "0").is_file() and (RETAIL / "default.xbe").is_file()
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
SMALL_BODY = 0x80000                                   # a synthetic one-team-sized ROST body (below the main roster size)


# --------------------------------------------------------------------------------------------- fixtures
def roster_resource(pbp_by_index: dict[int, int] | None = None, *, size: int = SMALL_BODY) -> bytes:
    """A complete ROST resource (wrapper + body) of the synthetic sample players, with chosen pbp words."""
    body = bytearray(synthetic_body(SAMPLE, size=size))
    document = rr.load_body(bytes(body))
    for player in document.players:
        struct.pack_into("<H", body, player.offset + 4, (pbp_by_index or {}).get(player.index, 9100))
    return b"ROST" + struct.pack("<II", len(body), len(body)) + bytes(0x14) + bytes(body)


def synthetic_spci(*, retired: bool = False) -> bytes:
    """A players-shaped cue table: magic, size field, the name marker and a sorted id array holding 9100 at index 1371."""
    ids = list(range(2, 2 + cf.EXPECTED_ID_INDEX)) + [cf.OLD_CUE] + [9204 + n for n in range(cf.ID_COUNT - cf.EXPECTED_ID_INDEX - 1)]
    assert len(ids) == cf.ID_COUNT and ids == sorted(set(ids))
    if retired:
        ids[cf.EXPECTED_ID_INDEX] = cf.NEW_CUE
    table = bytearray(cf.SPCI_SIZE)
    table[0:4] = cf.SPCI_MAGIC
    struct.pack_into("<I", table, 4, cf.SPCI_BODY_SIZE)
    marker = "players".encode("utf-16-le")
    table[cf.SPCI_NAME_OFFSET: cf.SPCI_NAME_OFFSET + len(marker)] = marker
    struct.pack_into(f"<{cf.ID_COUNT}H", table, cf.ID_TABLE_OFFSET, *ids)
    return bytes(table)


def pinned_to_synthetic():
    return mock.patch.multiple(cf, RETAIL_SPCI_SHA256=hashlib.sha256(synthetic_spci()).hexdigest(),
                               APPLIED_SPCI_SHA256=hashlib.sha256(synthetic_spci(retired=True)).hexdigest())


# --------------------------------------------------------------------------------------------- the id rules
class CommentaryIdTests(unittest.TestCase):
    """c1's rules as one pure function; the writers that deferred the id call it."""

    def test_the_rules(self) -> None:
        bank = rr.recorded_surname_ids()
        harrison = bank["harrison"]
        for last, jersey, current, expected in (
                ("Mahomes", 15, 9100, 9015),            # the retired double zero becomes the live number
                ("Mahomes", 15, 0, 9015),               # missing becomes the number
                ("Mahomes", 15, 9101, 9015),            # the absent sentinel too
                ("Harrison", 18, 9100, harrison),       # an exact recorded surname beats the number
                ("Harrison Jr.", 18, 9100, harrison),   # a generational suffix does not matter
                ("Zdyrko", 42, 9100, 9042),             # the surname bank's two absent entries
                ("Mahomes", 15, 971, 9015),             # a retail selection with no recorded clip
                ("Mahomes", 15, 9008, 9015),            # an explicit number follows the stored uniform number
                ("Mahomes", 0, 9015, 9000),             # a real #0 player is "zero", the clip 9000
                ("Mahomes", 0, 9100, 9000),             # ... and never "double zero"
                ("Smith", 7, 3593, 3593),               # a recorded retail name is kept
                ("Smith", 7, harrison, harrison),       # a surname-bank cue is kept
        ):
            with self.subTest(last=last, jersey=jersey, current=current):
                self.assertEqual(rr.commentary_id(last, jersey, current), expected)
        self.assertEqual(rr.commentary_id("Mahomes", 15, 9008, sync_numbers=False), 9008)

    def test_every_number_zero_to_ninety_nine_is_a_number_call_and_never_the_double_zero(self) -> None:
        for jersey in range(100):
            for current in (0, 9100, 9101, 9000 + (jersey + 1) % 100):
                self.assertEqual(rr.commentary_id("Nobody", jersey, current), 9000 + jersey)
        with self.assertRaises(rr.RosterRecordError):
            rr.commentary_id("Nobody", 100, 9100)           # a "00" jersey is not storable by the Studio

    def test_agrees_with_the_player_level_rule_on_a_grid(self) -> None:
        document = rr.load_body(synthetic_body(SAMPLE, size=SMALL_BODY))
        bank = rr.recorded_surname_ids()
        for player in document.players:
            for current in (0, 150, 971, 3593, 9000, 9015, 9099, 9100, 9101, 9300, 9783, 9999):
                for sync in (False, True):
                    for last in (player.last, "Harrison", ""):
                        player.record.values["pbp_id"] = current
                        player.last = last
                        before = current
                        changed = rr.normalise_player_commentary(player, bank, sync_numbers=sync)
                        want = rr.commentary_id(last, player.record.values["jersey"], before,
                                                surname_ids=bank, sync_numbers=sync)
                        if not (player.first or player.last):
                            continue                          # unnamed records stay blank by design
                        self.assertEqual(player.record.values["pbp_id"], want, (last, before, sync))
                        self.assertEqual(changed, want != before)

    def test_resource_pass_changes_only_the_pbp_word_and_keeps_the_wrapper(self) -> None:
        resource = roster_resource({0: 9100, 1: 3593, 2: 9099})
        fixed, receipt = rr.repair_commentary_resource(resource)
        self.assertEqual(len(fixed), len(resource))
        self.assertEqual(fixed[:rr.RESOURCE_HEADER_SIZE], resource[:rr.RESOURCE_HEADER_SIZE])
        document = rr.load_body(fixed[rr.RESOURCE_HEADER_SIZE:])
        allowed = {rr.RESOURCE_HEADER_SIZE + p.offset + k for p in document.players for k in (4, 5)}
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(resource, fixed))))
        self.assertGreater(receipt["players_changed"], 0)
        self.assertEqual(rr.repair_commentary_resource(fixed)[0], fixed)            # idempotent
        self.assertEqual(rr.repair_commentary_resource(fixed)[1]["players_changed"], 0)
        by_index = {p.index: p for p in document.players}
        self.assertEqual(by_index[1].record.values["pbp_id"], 3593)                  # a recorded name is kept
        self.assertEqual(by_index[2].record.values["pbp_id"], 9000 + by_index[2].record.values["jersey"])
        self.assertTrue(all(p.record.values["pbp_id"] != 9100 for p in document.players))
        with self.assertRaises(rr.RosterRecordError):
            rr.repair_commentary_resource(b"NOPE" + bytes(100))


# --------------------------------------------------------------------------------------------- the cue table
class CueTableTests(unittest.TestCase):
    def test_retire_changes_one_id_and_keeps_the_array_sorted(self) -> None:
        with pinned_to_synthetic():
            table = synthetic_spci()
            self.assertEqual(cf.table_status(table), "retail")
            patched, receipt = cf.patch_table(table)
            self.assertEqual(cf.table_status(patched), "applied")
            self.assertEqual(patched, synthetic_spci(retired=True))
            self.assertEqual((receipt["changed_bytes"], receipt["old_cue"], receipt["new_cue"]), (1, 9100, 9199))
            changed = [i for i, (a, b) in enumerate(zip(table, patched)) if a != b]
            self.assertEqual(changed, [cf.EXPECTED_ID_OFFSET])
            array = cf.ids(patched)
            self.assertEqual(list(array), sorted(set(array)))
            self.assertNotIn(9100, array)
            self.assertIn(9199, array)
            self.assertEqual(len(array), cf.ID_COUNT)
            again, receipt2 = cf.patch_table(patched)
            self.assertEqual((again, receipt2["already_applied"], receipt2["changed_bytes"]), (patched, True, 0))

    def test_foreign_tables_are_refused(self) -> None:
        with pinned_to_synthetic():
            table = bytearray(synthetic_spci())
            table[200] ^= 1
            self.assertEqual(cf.table_status(bytes(table)), "foreign")
            with self.assertRaises(cf.CommentaryFinalError):
                cf.patch_table(bytes(table))
            self.assertEqual(cf.table_status(b"SPCI"), "foreign")
            self.assertEqual(cf.table_status(bytes(cf.SPCI_SIZE)), "foreign")

    def test_the_pinned_retail_and_applied_tables_are_consistent(self) -> None:
        self.assertNotEqual(cf.RETAIL_SPCI_SHA256, cf.APPLIED_SPCI_SHA256)
        self.assertEqual(cf.EXPECTED_ID_OFFSET, 0xB2E)
        self.assertEqual(cf.EXPECTED_SPCI_OFFSET_IN_ENTRY + cf.EXPECTED_ID_OFFSET, 0x2419BE)
        self.assertTrue(cf.ID_TABLE_OFFSET + 2 * cf.ID_COUNT < cf.SPCI_SIZE)

    def test_find_table_needs_exactly_one_players_table(self) -> None:
        table = synthetic_spci()
        entry = bytes(100) + table + bytes(50)
        self.assertEqual(cf.find_table(entry), 100)
        with self.assertRaises(cf.CommentaryFinalError):
            cf.find_table(bytes(1000))
        with self.assertRaises(cf.CommentaryFinalError):
            cf.find_table(entry + table)
        other = bytearray(table)
        other[cf.SPCI_NAME_OFFSET: cf.SPCI_NAME_OFFSET + 14] = "teams!!".encode("utf-16-le")
        with self.assertRaises(cf.CommentaryFinalError):
            cf.find_table(bytes(other))

    @unittest.skipUnless(HAVE_RETAIL, "user-owned USA disc folder absent")
    def test_retail_table_pins_and_the_retired_id(self) -> None:
        table, _at = cf.read_table(RETAIL)
        self.assertEqual(cf.table_status(table), "retail")
        patched, receipt = cf.patch_table(table)
        self.assertEqual(hashlib.sha256(patched).hexdigest(), cf.APPLIED_SPCI_SHA256)
        self.assertEqual(receipt["changed_bytes"], 1)
        array = cf.ids(table)
        self.assertEqual((array.index(9100), array[1370], array[1372]), (cf.EXPECTED_ID_INDEX, 9099, 9204))
        self.assertEqual(cf.cue_status(RETAIL), "retail")


# --------------------------------------------------------------------------------------------- the image
class ImageTests(unittest.TestCase):
    def build(self, directory: Path, **entries):
        from nfl2k5_xiso_fixture import SyntheticXiso
        spci_entry = bytes(0x1000) + synthetic_spci() + bytes(0x800)
        main = b"ROST" + struct.pack("<II", rr.BODY_SIZE, rr.BODY_SIZE) + bytes(0x14) + synthetic_body(SAMPLE)
        items = [(100 + k, b"DUMY" + bytes(0x100)) for k in range(3)]
        items += [(200, spci_entry), (201, entries["team_a"]), (202, entries["team_b"]), (203, main),
                  (204, b"TAIL" + bytes(0x100))]
        return SyntheticXiso(directory, items, pack_sizes=(0x300000,), pack_sectors=(64,)), main

    def test_apply_retires_the_cue_and_finalizes_every_team_file_but_not_the_main_roster(self) -> None:
        team_a = roster_resource({0: 9100, 1: 3593, 2: 9099})
        team_b = roster_resource({i: 9000 + i for i in range(8)})                 # wrong numbers (jersey differs)
        with tempfile.TemporaryDirectory() as tmp, pinned_to_synthetic():
            fixture, main = self.build(Path(tmp), team_a=team_a, team_b=team_b)
            self.assertEqual(cf.status(fixture.path), "retail")
            self.assertEqual((cf.cue_status(fixture.path), cf.rosters_status(fixture.path)), ("retail", "pending"))
            receipt = cf.apply(fixture.path)
            self.assertEqual(receipt["status"], "applied")
            self.assertEqual(receipt["cue"]["changed_bytes"], 1)
            self.assertEqual(receipt["rosters"]["resources_scanned"], 2)
            self.assertEqual(receipt["rosters"]["resources_changed"], 2)
            self.assertEqual(cf.status(fixture.path), "applied")
            with rr._outer_image()(fixture.path) as archive:
                read = lambda n: archive.read(archive.entries[n].virtual_offset, archive.entries[n].size)  # noqa: E731
                self.assertEqual(read(4), rr.repair_commentary_resource(team_a)[0])
                self.assertEqual(read(5), rr.repair_commentary_resource(team_b)[0])
                self.assertEqual(read(6)[:len(main)], main)                         # the main roster is not ours
                spci = read(3)
            self.assertEqual(spci[0x1000: 0x1000 + cf.SPCI_SIZE], synthetic_spci(retired=True))
            self.assertEqual(spci[:0x1000] + spci[0x1000 + cf.SPCI_SIZE:], bytes(0x1000) + bytes(0x800))
            again = cf.apply(fixture.path)                                           # idempotent
            self.assertEqual((again["cue"]["already_applied"], again["rosters"]["resources_changed"]), (True, 0))

    def test_a_foreign_cue_table_is_skipped_by_the_build_step_and_refused_by_the_patch(self) -> None:
        team = roster_resource({0: 9100})
        with tempfile.TemporaryDirectory() as tmp, pinned_to_synthetic():
            fixture, _main = self.build(Path(tmp), team_a=team, team_b=team)
            with rr._outer_image()(fixture.path, writable=True) as archive:
                archive.write(archive.entries[3].virtual_offset + 0x1000 + 300, b"\xff")
            self.assertEqual(cf.cue_status(fixture.path), "foreign")
            with rr._outer_image()(fixture.path, writable=True) as archive:
                with self.assertRaises(cf.CommentaryFinalError):
                    cf.retire_cue(archive)
            receipt = cf.apply(fixture.path)                       # the build step does not break a build over it
            self.assertEqual((receipt["cue"]["status"], receipt["cue"]["changed_bytes"]), ("skipped", 0))
            self.assertEqual(receipt["rosters"]["resources_changed"], 2)       # the roster half still ran
            self.assertEqual(receipt["status"], "foreign")

    def test_an_unreadable_roster_is_skipped_by_the_build_step_and_refused_when_strict(self) -> None:
        junk = b"ROST" + struct.pack("<II", 0x200, 0x200) + bytes(0x14) + bytes(0x200)
        team = roster_resource({0: 9100})
        from nfl2k5_xiso_fixture import SyntheticXiso
        with tempfile.TemporaryDirectory() as tmp, pinned_to_synthetic():
            items = [(100 + k, b"DUMY" + bytes(0x100)) for k in range(3)]
            items += [(200, bytes(0x1000) + synthetic_spci() + bytes(0x800)), (201, team), (202, junk), (204, b"TAIL" + bytes(0x100))]
            fixture = SyntheticXiso(Path(tmp), items, pack_sizes=(0x300000,), pack_sectors=(64,))
            with rr._outer_image()(fixture.path) as archive:
                with self.assertRaises(cf.CommentaryFinalError):
                    cf.plan_resources(archive)
                skipped: list = []
                plans = cf.plan_resources(archive, strict=False, skipped=skipped)
            self.assertEqual((len(plans), len(skipped)), (1, 1))
            self.assertEqual(skipped[0]["outer_index"], 5)
            receipt = cf.apply(fixture.path)
            self.assertEqual((receipt["rosters"]["resources_changed"], len(receipt["rosters"]["unreadable_skipped"])), (1, 1))
            self.assertEqual(receipt["status"], "applied")


# --------------------------------------------------------------------------------------------- build wiring
class WiringTests(unittest.TestCase):
    def test_the_pass_runs_exactly_when_a_build_writes_rosters(self) -> None:
        plan = mod_build.BuildPlan(source=Path("a"), target=Path("b"))
        self.assertFalse(mod_build._commentary_final_wanted(plan, None))
        for field, value in (("roster_edits", "edits.json"), ("prospect_names", "modern"), ("espn25_rosters", True),
                             ("espn25_more_moments", True), ("historic_rosters_2026", True)):
            with self.subTest(field=field):
                self.assertTrue(mod_build._commentary_final_wanted(
                    mod_build.BuildPlan(source=Path("a"), target=Path("b"), **{field: value}), None))
        self.assertTrue(mod_build._commentary_final_wanted(plan, object()))

    def test_the_module_is_available_to_the_build(self) -> None:
        self.assertIs(mod_build._core_module("nfl2k5_commentary_final"), cf)

    def test_the_step_runs_after_the_last_roster_writer_and_before_the_stadium_steps(self) -> None:
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        step = source.index('"step": "commentary_final"')
        for earlier in ('"step": "espn25_rosters"', '"step": "espn25_more_moments"', '"step": "historic_rosters_2026"',
                        '"step": "espn25_plan"', '"step": "prospect_names"', '"step": "modern_helmets"'):
            self.assertLess(source.index(earlier), step, earlier)
        # before the passes that lay the outer archive out again and compact the image
        self.assertLess(step, source.index('"step": "trim_intro_videos"'))
        self.assertLess(step, source.index('"step": "custom_intro"'))


# --------------------------------------------------------------------------------------------- the Anniversary builder
@unittest.skipUnless(HAVE_RETAIL, "user-owned USA disc folder absent")
class CompileTeamTests(unittest.TestCase):
    """compile_team copies a matched person's play-by-play id from the main roster: it must not copy a stale one."""

    @classmethod
    def setUpClass(cls) -> None:
        import test_nfl2k5_espn25_more_moments as moments_tests
        cls.tests = moments_tests
        cls.mm = moments_tests.mm
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = moments_tests.write_dataset(cls.tmp.name, copies=1)
        with moments_tests.outer_image() as archive:
            cls.main = archive.read(archive.entries[5].virtual_offset, archive.entries[5].size)
            by_id = {e.name_id: e for e in archive.entries}
            cls.templates = {k: archive.read(by_id[cls.mm.name_id(t["template"])].virtual_offset,
                                             by_id[cls.mm.name_id(t["template"])].size)
                             for k, t in moments_tests.TEAMS.items()}
        cls.colleges = rr.RosterDocument(cls.main[32:]).colleges

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def compile(self, key: str, people: dict | None):
        entry = next(e for e in self.mm.table_entries(self.data) if e[0] == key)
        return self.mm.compile_team(self.templates[key], self.data.teams[key], self.data.rosters[key], self.colleges,
                                    entry[4], people)

    @staticmethod
    def person_key(row: dict) -> tuple:
        import datetime
        return (row["first"].casefold(), row["last"].casefold(), datetime.date.fromisoformat(row["birth_date"]).year % 100)

    def test_a_matched_persons_stale_id_is_resolved_against_this_seasons_jersey(self) -> None:
        key = "falcons_1998"
        rows = self.data.rosters[key]
        jersey = [int(r["jersey"]) for r in rows]
        stale = {self.person_key(rows[0]): (9100, 7101),                                   # the retired double zero
                 self.person_key(rows[1]): (9000 + (jersey[1] + 1) % 100, 7102),           # another season's number
                 self.person_key(rows[2]): (3593, 7103),                                   # a recorded name
                 self.person_key(rows[3]): (0, 7104)}                                      # never assigned
        raw = self.compile(key, stale)
        doc = rr.RosterDocument(raw[32:])
        ids = [p.record.values["pbp_id"] for p in sorted(doc.players, key=lambda p: p.index)]
        self.assertEqual(ids[0], rr.commentary_id(rows[0]["last"], jersey[0], 9100))
        self.assertEqual(ids[1], 9000 + jersey[1])
        self.assertEqual(ids[2], 3593)
        self.assertEqual(ids[3], rr.commentary_id(rows[3]["last"], jersey[3], 0))
        for n in range(4, len(rows)):
            self.assertEqual(ids[n], 9000 + jersey[n], n)
        self.assertNotIn(9100, ids)
        # a finished file needs no further pass
        self.assertEqual(rr.repair_commentary_resource(raw)[1]["players_changed"], 0)

    def test_the_result_does_not_depend_on_whether_the_main_roster_was_already_repaired(self) -> None:
        key = "vikings_1998"
        rows = self.data.rosters[key]
        old = {self.person_key(r): (9100, 7100 + n) for n, r in enumerate(rows[:12])}
        fixed = {self.person_key(r): (rr.commentary_id(r["last"], 40 + n, 9100), 7100 + n) for n, r in enumerate(rows[:12])}
        a = rr.RosterDocument(self.compile(key, old)[32:])
        b = rr.RosterDocument(self.compile(key, fixed)[32:])
        self.assertEqual([p.record.values["pbp_id"] for p in sorted(a.players, key=lambda p: p.index)],
                         [p.record.values["pbp_id"] for p in sorted(b.players, key=lambda p: p.index)])

    def test_without_matches_every_call_is_the_stored_number(self) -> None:
        for key in ("falcons_1998", "vikings_1998"):
            rows = self.data.rosters[key]
            doc = rr.RosterDocument(self.compile(key, None)[32:])
            for player, row in zip(sorted(doc.players, key=lambda p: p.index), rows):
                self.assertEqual(player.record.values["pbp_id"], 9000 + int(row["jersey"]), key)


# --------------------------------------------------------------------------------------------- the game's own code
@unittest.skipUnless(HAVE_RETAIL and HAVE_UNICORN, "retail disc folder and unicorn required")
class NativeResolverTests(unittest.TestCase):
    """The shipped resolver and cue lookup on the real executable and the real players cue table (synthetic RAM)."""

    @classmethod
    def setUpClass(cls) -> None:
        import c2_native_probe as probe
        cls.probe_module = probe
        table, _at = cf.read_table(RETAIL)
        cls.xbe = (RETAIL / "default.xbe").read_bytes()
        cls.retail = probe.Probe(cls.xbe, probe.spci_variant(table, "retail"))
        cls.applied = probe.Probe(cls.xbe, probe.spci_variant(table, "applied"))

    @staticmethod
    def record(pbp: int, jersey: int) -> bytes:
        raw = bytearray(rr.PLAYER_SIZE)
        struct.pack_into("<H", raw, 4, pbp)
        struct.pack_into("<I", raw, 0x20, jersey << 3)
        return bytes(raw)

    def resolve(self, probe, pbp, jersey, a0, a1, line_cue=None):
        return probe.resolve(self.record(pbp, jersey), a0, a1, line_cue=line_cue)[1]

    def test_with_the_cue_present_a_stored_9100_is_announced_as_double_zero_everywhere(self) -> None:
        for a0, a1 in self.probe_module.MODES:
            for jersey in (0, 1, 15, 99):
                self.assertEqual(self.resolve(self.retail, 9100, jersey, a0, a1), 9100, (a0, a1, jersey))

    def test_with_the_cue_retired_it_is_the_live_number_in_every_mode(self) -> None:
        for a0, a1 in self.probe_module.MODES:
            for jersey in range(100):
                self.assertEqual(self.resolve(self.applied, 9100, jersey, a0, a1), 9000 + jersey, (a0, a1, jersey))

    def test_a_real_number_zero_player_is_zero_not_double_zero(self) -> None:
        for probe in (self.retail, self.applied):
            for a0, a1 in self.probe_module.MODES:
                for pbp in (9000, 0, 9101, 9100 if probe is self.applied else 9000):
                    self.assertEqual(self.resolve(probe, pbp, 0, a0, a1), 9000, (pbp, a0, a1))
        self.assertTrue(self.applied.recorded(9000, 6) and self.retail.recorded(9000, 6))
        self.assertFalse(self.applied.recorded(9100, 6))
        self.assertTrue(self.retail.recorded(9100, 6))

    def test_nothing_else_changes_for_any_player_who_does_not_hold_the_double_zero(self) -> None:
        """Retail table against the retired one over many line cues, ids and uniform numbers (the resolver's whole input grid)."""
        lines = (0, 100, 1499, 1500, 1899, 1996, 2000, 5999, 6000, 6999, 7000, 9000, 9100, 9999, 10000, 20000, 37499,
                 37500, 38000, 39999, 40000, 47000, 48000, 51000, 51999, 52000, 53999, 54000)
        ids = (0, 150, 971, 3593, 6664, 8999, 9000, 9015, 9099, 9101, 9204, 9300, 9350, 9783, 9999)
        for line in lines:
            for pbp in ids:
                for jersey in (0, 1, 15, 99):
                    for a0, a1 in self.probe_module.MODES:
                        self.assertEqual(self.resolve(self.retail, pbp, jersey, a0, a1, line),
                                         self.resolve(self.applied, pbp, jersey, a0, a1, line),
                                         (line, pbp, jersey, a0, a1))

    def test_only_the_two_ids_change_availability(self) -> None:
        for cue in list(range(8990, 9320)) + [9999, 20000, 65535]:
            for kind in range(1, 10):
                if cue in (9100, 9199):
                    continue
                self.assertEqual(self.retail.recorded(cue, kind), self.applied.recorded(cue, kind), (cue, kind))
        self.assertTrue(any(self.retail.recorded(9100, k) for k in range(1, 10)))
        self.assertFalse(any(self.retail.recorded(9199, k) for k in range(1, 10)))
        self.assertTrue(any(self.applied.recorded(9199, k) for k in range(1, 10)))
        self.assertEqual(self.retail.machine.leaves, [])
        self.assertEqual(self.applied.machine.leaves, [])

    def test_the_retail_rosters_never_resolve_to_the_double_zero(self) -> None:
        resources, table = self.probe_module.read_pack_resources({0: RETAIL / "vc_53450030" / "0"})
        probe = self.probe_module.Probe(self.xbe, table)
        result = self.probe_module.audit_resources(resources, probe)
        self.assertEqual(result["double_zero_players"], 0)
        self.assertEqual(result["no_call_players"], 0)
        self.assertGreater(result["players"], 5000)
        # retail itself leaves five main-roster players on a number that is not the one they wear (c1 syncs them)
        self.assertEqual(result["wrong_number_players"], 5)


# --------------------------------------------------------------------------------------------- the real v0.5 packs
V05_PACKS = Path(os.environ.get("B77_C2_V05_PACKS", ""))          # a folder holding the extracted v0.5 files 0, E, F and default.xbe
REPAIRED = Path(os.environ.get("B77_C2_REPAIR_OUT", ""))         # tools/b77/c2_repair.py output: vc_53450030/0, E, F


def _packs(folder: Path, names=("vc_53450030__0", "vc_53450030__E", "vc_53450030__F")) -> dict[int, Path] | None:
    paths = {0: folder / names[0], 14: folder / names[1], 15: folder / names[2]}
    return paths if all(p.is_file() for p in paths.values()) else None


@unittest.skipUnless(HAVE_UNICORN and os.environ.get("B77_C2_V05_PACKS") and _packs(V05_PACKS) and (V05_PACKS / "default.xbe").is_file(),
                     "set B77_C2_V05_PACKS to a folder with the v0.5 files vc_53450030__0/E/F and default.xbe")
class V05DiscTests(unittest.TestCase):
    """The shipped v0.5 files: where the double zero lives, and that the repair removes it (the game's own resolver)."""

    @classmethod
    def setUpClass(cls) -> None:
        import c2_native_probe as probe
        cls.probe = probe
        cls.xbe = V05_PACKS / "default.xbe"
        cls.before = probe.audit_packs(_packs(V05_PACKS), cls.xbe, spci="retail")

    def test_the_shipped_files_still_hold_the_double_zero_in_the_anniversary_team_files_only(self) -> None:
        self.assertEqual(self.before["double_zero_players"], 144)
        self.assertEqual(self.before["by_pack"]["14"]["double_zero"], 144)
        self.assertNotIn("double_zero", self.before["by_pack"]["0"])
        self.assertNotIn("double_zero", self.before["by_pack"]["15"])
        self.assertEqual(self.before["wrong_number_players"], 1271 + 5)

    def test_retiring_the_cue_alone_removes_every_double_zero(self) -> None:
        after = self.probe.audit_packs(_packs(V05_PACKS), self.xbe, spci="applied")
        self.assertEqual(after["double_zero_players"], 0)
        self.assertEqual(after["wrong_number_players"], 1271 + 5)             # the numbers need the data repair

    @unittest.skipUnless(REPAIRED.is_dir() and (REPAIRED / "vc_53450030" / "0").is_file(), "set B77_C2_REPAIR_OUT to the repair output")
    def test_the_repair_leaves_no_double_zero_and_no_wrong_number_with_or_without_the_retired_cue(self) -> None:
        packs = {0: REPAIRED / "vc_53450030" / "0", 14: REPAIRED / "vc_53450030" / "E", 15: REPAIRED / "vc_53450030" / "F"}
        for spci in ("retail", "applied", "as_is"):
            result = self.probe.audit_packs(packs, self.xbe, spci=spci)
            self.assertEqual((result["double_zero_players"], result["wrong_number_players"], result["no_call_players"]), (0, 0, 0), spci)
            self.assertEqual(result["native_leaf_substitutions"], [])
            self.assertEqual(result["players"], 12201)


if __name__ == "__main__":
    unittest.main()
