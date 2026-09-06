"""Lane tests for NFL Street 3 (USA, PlayStation 2).  Synthetic sources only; no game data.

Every source these tests look at is built by ``containers.build_synthetic_disc``
from the formats' own rules, so the suite runs on a machine that owns no disc.
What is proved here and not by the generic harness:

* the schema difference between the two NFL Street discs is a fact this module
  states, and the fixture's own table shapes are the ones the retail disc
  declares -- so a fixture that drifted from the disc fails here rather than
  silently making a lane look correct;
* every writer refuses a destination that exists, refuses the source as its own
  destination, and leaves the source byte-identical;
* the independent verifier fails on a tampered destination;
* the refusal sentences name the fix, verbatim.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import ea_tdb  # noqa: E402
from mod_editor.games.contract import Edit, Refusal  # noqa: E402
from mod_editor.games.nflstreet3_ps2 import GAME, containers  # noqa: E402

GAME_ID = "nflstreet3_ps2"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SyntheticDiscTests(unittest.TestCase):
    """The fixture is this disc's shape, not a generic one."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix=f"{GAME_ID}-lanes-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.iso = self.work / "synthetic.iso"
        self.iso.write_bytes(containers.build_synthetic_disc())

    def test_the_disc_opens_and_lists_its_data_files(self) -> None:
        image = containers.open_disc(self.iso)
        names = {entry.name for entry in containers.data_files(image)}
        self.assertIn(containers.TEAM_DATABASE_CONTAINER, names)
        self.assertIn(containers.GAME_DATA_CONTAINER, names)
        self.assertIn(containers.UNIFORM_CONTAINERS[0], names)

    def test_a_non_disc_is_refused_by_one_sentence(self) -> None:
        junk = self.work / "not-a-disc.iso"
        junk.write_bytes(b"\x00" * 4096)
        with self.assertRaises(containers.DiscError):
            containers.open_disc(junk)

    def test_an_image_without_data_is_refused_by_name(self) -> None:
        from mod_editor.games._lanes import terf_discs

        empty = self.work / "empty.iso"
        empty.write_bytes(terf_discs.build_synthetic_iso(
            boot_file=containers.BOOT_FILE, sub_files=[], sub_name=b"OTHER"))
        image = containers.open_disc(empty)
        with self.assertRaises(containers.DiscError) as caught:
            containers.data_files(image)
        self.assertIn(containers.SERIAL, str(caught.exception))

    def test_the_team_fixture_has_this_discs_table_shape(self) -> None:
        """The fixture's PLAY/TEAM/DCHT widths are the ones the disc declares [M]."""

        database = ea_tdb.parse_tdb(containers.synthetic_team_database())
        tables = {table.name: table for table in database.tables}
        self.assertEqual(sorted(tables), ["DCHT", "PLAY", "TEAM"])
        dcht = tables["DCHT"]
        # DCHT is the one table byte-identical on both NFL Street discs [M]:
        # 4 fields, and PGID/TGID/PPOS/ddep at 15/10/5/5 bits.
        self.assertEqual(dcht.field_count, 4)
        self.assertEqual([(f.name, f.bit_width) for f in dcht.fields],
                         [("PGID", 15), ("TGID", 10), ("PPOS", 5), ("ddep", 5)])
        play = tables["PLAY"]
        self.assertEqual(play.field("PFNA").bit_width, 96)
        self.assertEqual(play.field("PLNA").bit_width, 112)
        self.assertEqual(play.field("PNKN").bit_width, 128)
        team = tables["TEAM"]
        self.assertEqual(team.field("TDNA").bit_width, 136)
        self.assertEqual(team.field("TLNA").bit_width, 120)
        self.assertEqual(team.field("TSNA").bit_width, 56)
        self.assertEqual(team.field("TLGL").bit_width, 8)

    def test_every_fixture_database_verifies_its_own_checksums(self) -> None:
        for build in (containers.synthetic_team_database,
                      containers.synthetic_playbook_database,
                      containers.synthetic_tdb):
            blob = build()
            bad = [site for site in ea_tdb.crc_sites(blob) if site.stored != site.computed]
            self.assertEqual(bad, [], f"{build.__name__} has wrong checksums")

    def test_the_preload_caches_carry_both_kinds_of_copy(self) -> None:
        image = containers.open_disc(self.iso)
        preload = containers.preload_copies(image)
        self.assertTrue(preload, "the fixture ships no preload copies")
        headers = sum(1 for row in preload.values() if row.header is not None)
        members = sum(len(row.members) for row in preload.values())
        self.assertGreater(headers, 0, "no cached container directory in the fixture")
        self.assertGreater(members, 0, "no cached member in the fixture")


class WriterTests(unittest.TestCase):
    """Every writing lane, on the synthetic disc: build, verify, refuse, tamper."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix=f"{GAME_ID}-writers-"))
        self.addCleanup(shutil.rmtree, self.work, True)

    def writers(self):
        return [lane for lane in GAME.lanes
                if getattr(lane, "classification", "") == "offline-writer-proved"]

    def test_there_are_writers(self) -> None:
        self.assertEqual(len(self.writers()), 11)

    def test_each_writer_builds_verifies_and_leaves_the_source_alone(self) -> None:
        for lane in self.writers():
            with self.subTest(lane=lane.lane_id):
                room = self.work / lane.lane_id.replace(".", "-")
                room.mkdir(parents=True)
                source = lane.synthetic_source(room)
                before = digest(source)
                catalogue = lane.build_catalogue(source)
                edits = lane.conformance_edits(catalogue)
                destination = room / "out.iso"
                receipt = lane.build(source, destination,
                                     lane.compose_recipe(edits), catalogue)
                verdict = lane.verify(source, destination, receipt)
                self.assertTrue(verdict.passed, verdict.summary)
                self.assertEqual(before, digest(source), "the source moved")
                self.assertNotEqual(before, digest(destination),
                                    "the destination is identical to the source")

    def test_each_writer_refuses_an_existing_destination_by_name(self) -> None:
        for lane in self.writers():
            with self.subTest(lane=lane.lane_id):
                room = self.work / ("x-" + lane.lane_id.replace(".", "-"))
                room.mkdir(parents=True)
                source = lane.synthetic_source(room)
                catalogue = lane.build_catalogue(source)
                edits = lane.conformance_edits(catalogue)
                destination = room / "already.iso"
                destination.write_bytes(b"occupied")
                with self.assertRaises(Refusal) as caught:
                    lane.build(source, destination, lane.compose_recipe(edits), catalogue)
                self.assertIn("already exists", str(caught.exception))
                self.assertEqual(destination.read_bytes(), b"occupied")

    def test_each_writer_refuses_the_source_as_its_own_destination(self) -> None:
        for lane in self.writers():
            with self.subTest(lane=lane.lane_id):
                room = self.work / ("s-" + lane.lane_id.replace(".", "-"))
                room.mkdir(parents=True)
                source = lane.synthetic_source(room)
                before = digest(source)
                catalogue = lane.build_catalogue(source)
                edits = lane.conformance_edits(catalogue)
                with self.assertRaises(Refusal):
                    lane.build(source, source, lane.compose_recipe(edits), catalogue)
                self.assertEqual(before, digest(source))

    def test_the_verifier_fails_on_a_tampered_destination(self) -> None:
        for lane in self.writers():
            with self.subTest(lane=lane.lane_id):
                room = self.work / ("t-" + lane.lane_id.replace(".", "-"))
                room.mkdir(parents=True)
                source = lane.synthetic_source(room)
                catalogue = lane.build_catalogue(source)
                edits = lane.conformance_edits(catalogue)
                destination = room / "out.iso"
                receipt = lane.build(source, destination,
                                     lane.compose_recipe(edits), catalogue)
                blob = bytearray(destination.read_bytes())
                blob[len(blob) // 2] ^= 0xFF
                destination.write_bytes(bytes(blob))
                verdict = lane.verify(source, destination, receipt)
                self.assertFalse(verdict.passed,
                                 "a flipped byte was not caught by the verifier")


class ReadOnlyAndExportTests(unittest.TestCase):
    """The lanes that do not write, and the sentences they refuse with."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix=f"{GAME_ID}-readonly-"))
        self.addCleanup(shutil.rmtree, self.work, True)

    def test_the_inventory_lane_refuses_all_three_write_entry_points(self) -> None:
        lane = next(l for l in GAME.lanes if l.lane_id == "textures.container_inventory")
        source = lane.synthetic_source(self.work)
        catalogue = lane.build_catalogue(source)
        for call in (lambda: lane.plan(source, {}, catalogue),
                     lambda: lane.build(source, self.work / "x.iso", {}, catalogue),
                     lambda: lane.verify(source, self.work / "x.iso", None)):
            with self.assertRaises(Refusal) as caught:
                call()
            self.assertEqual(str(caught.exception), lane.REFUSAL)

    def test_the_inventory_cap_is_per_container_as_well_as_per_disc(self) -> None:
        """A flat cap would list one archive and nothing after it."""

        lane = next(l for l in GAME.lanes if l.lane_id == "textures.container_inventory")
        self.assertLess(lane.max_members_per_container, lane.max_member_targets)
        source = lane.synthetic_source(self.work)
        document = lane.build_catalogue(source).document
        self.assertEqual(document["member_rows_cap_per_container"],
                         lane.max_members_per_container)

    def test_the_kit_census_says_why_it_has_no_writer(self) -> None:
        lane = next(l for l in GAME.lanes if l.lane_id == "uniforms.texture_census")
        self.assertEqual(lane.classification, "extract-only")
        source = lane.synthetic_source(self.work)
        document = lane.build_catalogue(source).document
        self.assertIn("pixel layout 5 or 6", document["no_writer"])
        self.assertIn("no kit table", document["no_kit_table"].lower())

    def test_the_kit_census_declares_no_extra_psm(self) -> None:
        """Measured on this disc's own capture: every dumped name is PSM 0."""

        lane = next(l for l in GAME.lanes if l.lane_id == "uniforms.texture_census")
        self.assertEqual(tuple(lane.extra_psms), ())

    def test_each_audio_lane_exports_and_re_decodes(self) -> None:
        for lane_id in ("audio.streams", "audio.banks"):
            with self.subTest(lane=lane_id):
                lane = next(l for l in GAME.lanes if l.lane_id == lane_id)
                room = self.work / lane_id.replace(".", "-")
                room.mkdir(parents=True)
                source = lane.synthetic_source(room)
                catalogue = lane.build_catalogue(source)
                edits = lane.conformance_edits(catalogue)
                manifest = room / "export" / "manifest.json"
                receipt = lane.build(source, manifest,
                                     lane.compose_recipe(edits), catalogue)
                verdict = lane.verify(source, manifest, receipt)
                self.assertTrue(verdict.passed, verdict.summary)

    def test_an_audio_export_verifier_catches_an_undeclared_file(self) -> None:
        lane = next(l for l in GAME.lanes if l.lane_id == "audio.banks")
        source = lane.synthetic_source(self.work)
        catalogue = lane.build_catalogue(source)
        edits = lane.conformance_edits(catalogue)
        manifest = self.work / "export" / "manifest.json"
        receipt = lane.build(source, manifest, lane.compose_recipe(edits), catalogue)
        folder = lane.export_root_for(manifest)
        (folder / "sneaked.wav").write_bytes(b"x")
        verdict = lane.verify(source, manifest, receipt)
        self.assertFalse(verdict.passed)


class IdentityTests(unittest.TestCase):
    """The disc identifier, on files it should and should not accept."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix=f"{GAME_ID}-identity-"))
        self.addCleanup(shutil.rmtree, self.work, True)

    def test_the_synthetic_disc_is_recognised_as_this_serial(self) -> None:
        iso = self.work / "synthetic.iso"
        iso.write_bytes(containers.build_synthetic_disc())
        found = GAME.identifier.identify(iso)
        self.assertEqual(found.serial, containers.SERIAL)
        self.assertTrue(found.serial_matches)
        self.assertFalse(found.retail_executable,
                         "a synthetic ELF must not read as the retail one")
        self.assertIn("unknown edition", found.headline)

    def test_a_file_that_is_not_a_disc_is_refused(self) -> None:
        junk = self.work / "junk.iso"
        junk.write_bytes(b"\x00" * 4096)
        with self.assertRaises(Refusal):
            GAME.identifier.identify(junk)


class RegistryTests(unittest.TestCase):
    """What the module claims, against what its lanes are."""

    def test_every_lane_has_a_row_and_the_rungs_agree(self) -> None:
        import json

        fragment = json.loads(
            (ROOT / "mod_editor" / "games" / GAME_ID / "registry.fragment.json")
            .read_text(encoding="utf-8"))
        rows = {row["id"]: row for row in fragment["capabilities"]}
        self.assertEqual(len(GAME.lanes), len(rows))
        for lane in GAME.lanes:
            with self.subTest(lane=lane.lane_id):
                row = rows[lane.capability_id]
                self.assertEqual(row["classification"], lane.classification)
                self.assertEqual(row["surface"], lane.surface)

    def test_no_row_claims_a_runtime_it_has_not_witnessed(self) -> None:
        import json

        fragment = json.loads(
            (ROOT / "mod_editor" / "games" / GAME_ID / "registry.fragment.json")
            .read_text(encoding="utf-8"))
        for row in fragment["capabilities"]:
            with self.subTest(row=row["id"]):
                self.assertEqual(row["runtime"]["status"], "not-applicable")
                self.assertNotEqual(row["classification"], "runtime-proved")


if __name__ == "__main__":
    unittest.main()
