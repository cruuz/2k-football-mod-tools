"""The PCSX2 replacement identities of NCAA Football 09 (PS2), and the tool that pairs them.

Two things are under test and they are different in kind.

The **matcher** is proved here on data these tests make: a synthetic disc, PNGs
written by the lane's own writer under names PCSX2's grammar allows, and the
precedence rule a lane applies when a texture has both a confirmed name and a
derived one.  No disc and no emulator is involved.

The **document** is not proved here -- it was measured, once, by pairing a real
capture with the owner's own image -- so what runs against it is what a reader
of it may rely on: that it declares the schema the lane loads, that every key
names a container member and image, that every filename is one PCSX2 would have
written, and that it carries names and numbers rather than pixels.

No byte of any disc is in this repository.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import ps2_texture_identities as tool  # noqa: E402
from mod_editor.games._formats import ea_terf, mmap_art, xxhash3_64  # noqa: E402
from mod_editor.games._formats import pcsx2_texture_name as names  # noqa: E402
from mod_editor.games._lanes import terf_art  # noqa: E402
from mod_editor.games.ncaa09_ps2 import art_pages  # noqa: E402
from mod_editor.games.ncaa09_ps2 import containers  # noqa: E402
from mod_editor.games.ncaa09_ps2 import texture_lane  # noqa: E402

KEY = r"^[A-Z0-9_.]+:\d+:\d+$"


class ProfileTests(unittest.TestCase):
    """One engine, two discs: the profile is what tells them apart."""

    def test_both_discs_are_registered_and_point_at_their_own_documents(self) -> None:
        madden = tool.profile("madden09_ps2")
        ncaa = tool.profile("ncaa09_ps2")
        self.assertNotEqual(madden.identity_document, ncaa.identity_document)
        self.assertNotEqual(madden.identity_schema, ncaa.identity_schema)
        self.assertNotEqual(madden.derivation_document, ncaa.derivation_document)
        self.assertNotEqual(madden.selftest_token, ncaa.selftest_token)
        # The lane is what reads the table, so the profile must name the path
        # and the schema the lane itself declares -- not a second copy of them.
        self.assertEqual(ncaa.identity_document, texture_lane.IDENTITY_DOCUMENT)
        self.assertEqual(ncaa.identity_schema, texture_lane.IDENTITY_SCHEMA)

    def test_an_unknown_disc_is_refused_by_name_with_the_choices(self) -> None:
        with self.assertRaises(tool.IdentityError) as caught:
            tool.profile("nfl2k5_ps2")
        self.assertIn("ncaa09_ps2", str(caught.exception))
        self.assertIn("madden09_ps2", str(caught.exception))

    def test_the_ncaa_profile_indexes_every_container_the_six_rows_read(self) -> None:
        wanted = set(tool.profile("ncaa09_ps2").default_containers)
        lanes = [texture_lane.TextureLane, texture_lane.UniformDiscArtWriteLane]
        lanes += list(art_pages.ART_PAGE_LANES)
        read = {name for lane in lanes for name, _group, _note in lane.art_containers}
        self.assertEqual(read - wanted, set(),
                         "a container a row reads that the pairing never indexes can "
                         "never have a confirmed name")

    def test_the_selftest_passes_for_this_disc(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/ps2_texture_identities.py"),
             "--game", "ncaa09_ps2", "--selftest"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NCAA09_PS2_TEXTURE_IDENTITIES_SELFTEST_PASS", result.stdout)

    def test_the_madden_door_still_opens_on_madden(self) -> None:
        import madden09_ps2_texture_identities as door

        self.assertEqual(door.GAME.game_id, "madden09_ps2")
        self.assertEqual(door.DEFAULT_CONTAINERS[0], "UNIFORMS.DAT")
        self.assertIs(door.scan_dump, tool.scan_dump)
        self.assertIs(door.pair, tool.pair)


class CoverageTests(unittest.TestCase):
    """The coverage block is computed from the pairing, never typed in."""

    def test_a_container_with_no_named_texture_still_gets_a_row(self) -> None:
        disc = [tool.DiscTexture("A.DAT", 0, 0, 0, 8, 8, "rgba", "rgb")]
        report = tool.MatchReport()
        coverage = tool.coverage_by_container(disc, report, ("A.DAT", "B.DAT"))
        self.assertEqual(coverage["B.DAT"],
                         {"textures_indexed": 0, "textures_named": 0,
                          "frames_that_drew_one": 0})
        self.assertEqual(coverage["A.DAT"]["textures_indexed"], 1)

    def test_frames_are_counted_per_container_not_per_texture(self) -> None:
        report = tool.MatchReport()
        report.matched = {"A.DAT:0:0": {"container": "A.DAT"},
                          "A.DAT:1:0": {"container": "A.DAT"}}
        report.by_frame = {"f1": ["A.DAT:0:0", "A.DAT:1:0"], "f2": ["A.DAT:1:0"]}
        coverage = tool.coverage_by_container([], report, ("A.DAT",))
        self.assertEqual(coverage["A.DAT"]["textures_named"], 2)
        self.assertEqual(coverage["A.DAT"]["frames_that_drew_one"], 2)


class ReplacementIdentityTests(unittest.TestCase):
    """A confirmed name wins; a derived one is the fallback and says so."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ncaa09-identity-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = texture_lane.TextureLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)
        self.target = self.catalogue.targets[0]

    def _document(self, names: dict) -> Path:
        path = self.work / "identities.json"
        path.write_text(json.dumps({
            "schema": texture_lane.IDENTITY_SCHEMA,
            "identities": {self.target.key: {"container": "UNIFORM.DAT", "member": 0,
                                             "image": 0, "names": names}},
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        terf_art._IDENTITY_CACHE.clear()
        self.addCleanup(terf_art._IDENTITY_CACHE.clear)
        return path

    def test_without_a_document_the_name_is_derived_and_the_note_says_so(self) -> None:
        lane = texture_lane.TextureLane()
        lane.identity_document = None
        name = lane.replacement_identity(self.target)
        self.assertIsNotNone(name)
        self.assertIsNotNone(tool._NAME.match(name), name)
        self.assertIn("Derived from this texture's own bytes", lane.identity_note(self.target))
        self.assertNotIn("Confirmed by a PCSX2 dump", lane.identity_note(self.target))

    def test_a_dumped_name_wins_over_the_derived_one_and_classic_wins_over_modern(self) -> None:
        lane = texture_lane.TextureLane()
        lane.identity_document = self._document({
            "classic": ["1111-2222-00005113.png"],
            "modern": ["1111-2222-00001113.png"],
        })
        self.assertEqual(lane.replacement_identity(self.target), "1111-2222-00005113.png")
        note = lane.identity_note(self.target)
        self.assertIn("Confirmed by a PCSX2 dump", note)
        # The derived names stay on the row: a pack writer wants the draws no
        # frame captured as well as the one it did.
        names = lane.replacement_identities(self.target)
        self.assertTrue(names[terf_art.DERIVED_PREFIX + "modern"])

    def test_a_document_declaring_another_schema_is_not_read(self) -> None:
        path = self._document({"classic": ["1111-2222-00005113.png"]})
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["schema"] = "madden09_ps2_pcsx2_texture_identities/v1"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
        terf_art._IDENTITY_CACHE.clear()
        lane = texture_lane.TextureLane()
        lane.identity_document = path
        self.assertEqual(terf_art.load_identities(path, texture_lane.IDENTITY_SCHEMA), {})
        self.assertNotIn("Confirmed by a PCSX2 dump", lane.identity_note(self.target))


class ShippedDocumentTests(unittest.TestCase):
    """What a reader of the measured table may rely on."""

    def setUp(self) -> None:
        self.path = ROOT / texture_lane.IDENTITY_DOCUMENT
        if not self.path.is_file():
            self.skipTest("no identity document in this tree")
        self.payload = json.loads(self.path.read_text(encoding="utf-8"))

    def test_it_declares_the_schema_the_lane_loads(self) -> None:
        self.assertEqual(self.payload["schema"], texture_lane.IDENTITY_SCHEMA)
        loaded = texture_lane.load_identities()
        self.assertEqual(len(loaded), len(self.payload["identities"]))
        self.assertGreater(len(loaded), 0)

    def test_every_key_names_a_member_and_image_and_every_name_is_pcsx2s(self) -> None:
        for key, names in texture_lane.load_identities().items():
            self.assertRegex(key, KEY)
            for values in names.values():
                for name in values:
                    self.assertIsNotNone(tool._NAME.match(name), name)

    def test_it_carries_names_and_numbers_and_no_pixel(self) -> None:
        self.assertNotIn("pixels", self.payload)
        self.assertNotIn("rgba", json.dumps(self.payload["identities"])[:200000])

    def test_the_coverage_block_agrees_with_the_identities(self) -> None:
        coverage = self.payload["coverage"]
        self.assertEqual(sum(row["textures_named"] for row in coverage.values()),
                         len(self.payload["identities"]))
        for name, row in coverage.items():
            self.assertLessEqual(row["textures_named"], row["textures_indexed"], name)
            self.assertLessEqual(row["frames_that_drew_one"], self.payload["counts"]["frames"])

    def test_every_container_the_six_rows_read_has_a_coverage_row(self) -> None:
        lanes = [texture_lane.TextureLane, texture_lane.UniformDiscArtWriteLane]
        lanes += list(art_pages.ART_PAGE_LANES)
        read = {name for lane in lanes for name, _group, _note in lane.art_containers}
        self.assertEqual(read - set(self.payload["coverage"]), set())

    def test_the_four_art_pages_read_the_same_table_as_the_uniform_rows(self) -> None:
        for lane in art_pages.ART_PAGE_LANES:
            self.assertEqual(lane.identity_document, texture_lane.IDENTITY_DOCUMENT)
            self.assertEqual(lane.identity_schema, texture_lane.IDENTITY_SCHEMA)


class ShippedDerivationTests(unittest.TestCase):
    """The derivation document is a check on the rule, and its counts must add up."""

    def setUp(self) -> None:
        self.path = ROOT / tool.profile("ncaa09_ps2").derivation_document
        if not self.path.is_file():
            self.skipTest("no derivation document in this tree")
        self.payload = json.loads(self.path.read_text(encoding="utf-8"))

    def test_it_declares_its_own_schema_and_not_maddens(self) -> None:
        self.assertEqual(self.payload["schema"],
                         tool.profile("ncaa09_ps2").derivation_schema)
        self.assertNotEqual(self.payload["schema"],
                            tool.profile("madden09_ps2").derivation_schema)

    def test_the_reproduced_and_not_reproduced_names_account_for_every_name(self) -> None:
        counts = self.payload["dump_check"]["counts"]
        self.assertEqual(counts["names_tex0_reproduced"] + counts["names_tex0_not_reproduced"],
                         counts["names"])
        self.assertEqual(counts["identities_checked"] + counts["identities_not_derivable"],
                         counts["identities"])
        self.assertLessEqual(counts["identities_confirmed"], counts["identities_checked"])

    def test_the_lane_quotes_this_documents_numbers_and_not_maddens(self) -> None:
        counts = self.payload["dump_check"]["counts"]
        evidence = texture_lane.TextureLane.derivation_evidence
        self.assertIn(f"{counts['names_tex0_reproduced']:,}", evidence)
        self.assertIn(f"{counts['names']:,}", evidence)

    def test_the_dump_carried_no_high_byte_name_so_the_second_reading_answered_nothing(self):
        """The measured answer to "is any of this a ``PSMT8H`` draw": no.

        The check tries the high-byte reading for every 8-bit surface now, so
        the document records the GS mode of every dumped name it saw.  On this
        disc's two frames those modes are 19 and 20 only, which is why the
        high-byte counts are zero and why nothing in the shipped numbers moved
        when the second reading was added [M].
        """

        check = self.payload["dump_check"]
        by_psm = check["dumped_names_by_psm"]
        counts = check["counts"]
        self.assertNotIn(str(names.PSMT8H), by_psm)
        self.assertEqual(sorted(by_psm, key=int), [str(names.PSMT8), str(names.PSMT4)])
        self.assertEqual(counts["names_high_byte_checked"], 0)
        self.assertEqual(counts["names_high_byte_reproduced"], 0)
        self.assertEqual(sum(row["names"] for row in by_psm.values()), counts["names"])
        self.assertEqual(sum(row["not a reading of this surface"] for row in by_psm.values()),
                         counts["names_psm_disagrees"])
        self.assertEqual(sum(row["tex0 reproduced"] for row in by_psm.values()),
                         counts["names_tex0_reproduced"])
        self.assertEqual(sum(row["tex0 not reproduced"] for row in by_psm.values()),
                         counts["names_tex0_not_reproduced"])

    def test_the_cross_member_chain_probe_accounts_for_every_unreproduced_name(self) -> None:
        chain = self.payload["dump_check"]["cross_member_chain"]
        self.assertEqual(chain["names_explained"] + chain["names_still_unexplained"],
                         self.payload["dump_check"]["counts"]["names_tex0_not_reproduced"])
        for row in chain["chains"]:
            self.assertGreaterEqual(row["levels"], 2)
            self.assertEqual(row["last_member"], row["member"] + row["levels"] - 1)


class HighByteAndChainTests(unittest.TestCase):
    """Two readings and one probe, proved on a disc these tests build.

    ``derivation_check`` used to dismiss a name whose ``bits`` word declared a
    GS mode other than the surface's own as "another surface's", which silently
    hid the high-byte ``PSMT8H`` reading of an 8-bit texture -- a different
    ``bits`` word *and* a different TEX0 hash for the same pixels.  It also had
    one hypothesis for a name it could not reproduce and no way to test it: a
    mip pyramid stored as a run of consecutive one-level members, which PCSX2
    hashes as one chain.  Both are exercised here on a synthetic disc.
    """

    def setUp(self) -> None:
        self.room = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.room, ignore_errors=True)
        run = [containers.synthetic_texture_member(64, 64, seed=3),
               containers.synthetic_texture_member(32, 32, seed=3),
               containers.synthetic_texture_member(16, 16, seed=3)]
        self.disc = self.room / "synthetic.iso"
        self.disc.write_bytes(containers.build_synthetic_disc(art_members=run))
        self.container = "UIS_GEAR.DAT"
        image = containers.open_disc(self.disc)
        entry = {row.name: row for row in containers.data_files(image)}[self.container]
        terf = ea_terf.parse_terf(containers.read_file(image, entry), allow_size_mismatch=True)
        self.streams = []
        for member in range(3):
            payload = terf.member(member)
            texture = mmap_art.parse(payload)
            picture = texture.images[0]
            surface = texture.surfaces[picture.first_surface]
            indices = mmap_art.unpack_indices(mmap_art.surface_pixels(payload, surface), surface)
            self.streams.append(indices)
            if member == 0:
                self.clut = names.clut_hash(
                    mmap_art.read_palette(payload, texture.palettes[picture.first_palette]))

    def _document(self, filenames):
        return {"identities": {f"{self.container}:0:0": {
            "container": self.container, "member": 0, "image": 0,
            "names": {"modern": list(filenames)}}}}

    def _name(self, tex0: int, psm: int) -> str:
        return names.replacement_name(tex0, self.clut, names.texture_bits(psm, 6, 6, 0))

    def test_a_high_byte_name_is_checked_against_the_linear_reading_not_dismissed(self) -> None:
        level = names.TextureLevel(64, 64, 8, self.streams[0])
        high = self._name(names.tex0_hash((level,), psm=names.PSMT8H), names.PSMT8H)
        low = self._name(names.tex0_hash((level,)), names.PSMT8)
        check = tool.derivation_check(self.disc, self._document([high, low]),
                                      discs=containers)
        counts = check["counts"]
        self.assertEqual(counts["names_high_byte_checked"], 1)
        self.assertEqual(counts["names_high_byte_reproduced"], 1)
        self.assertEqual(counts["names_psm_disagrees"], 0)
        self.assertEqual(counts["names_tex0_reproduced"], 2)
        self.assertEqual(counts["names_tex0_not_reproduced"], 0)
        self.assertEqual(check["dumped_names_by_psm"], {
            str(names.PSMT8): {"names": 1, "tex0 reproduced": 1, "tex0 not reproduced": 0,
                               "not a reading of this surface": 0},
            str(names.PSMT8H): {"names": 1, "tex0 reproduced": 1, "tex0 not reproduced": 0,
                                "not a reading of this surface": 0}})

    def test_a_name_of_a_mode_this_surface_has_no_reading_for_still_disagrees(self) -> None:
        """A 4-bit name on an 8-bit surface is the sibling's, and stays counted as one."""

        level = names.TextureLevel(64, 64, 8, self.streams[0])
        check = tool.derivation_check(
            self.disc, self._document([self._name(names.tex0_hash((level,)), names.PSMT4)]),
            discs=containers)
        self.assertEqual(check["counts"]["names_psm_disagrees"], 1)
        self.assertEqual(check["counts"]["names"], 0)
        self.assertEqual(check["dumped_names_by_psm"][str(names.PSMT4)]
                         ["not a reading of this surface"], 1)

    def test_a_pyramid_split_across_members_is_named_by_the_chain_probe(self) -> None:
        """Member 0 hashed alone reproduces nothing; members 0..2 as one chain do."""

        chained = xxhash3_64.xxh3_64(b"".join(
            names.hashed_stream(indices, 64 >> step, 64 >> step, 8)[0]
            for step, indices in enumerate(self.streams)))
        check = tool.derivation_check(self.disc,
                                      self._document([self._name(chained, names.PSMT8)]),
                                      discs=containers)
        self.assertEqual(check["counts"]["names_tex0_not_reproduced"], 1)
        chain = check["cross_member_chain"]
        self.assertEqual(chain["names_explained"], 1)
        self.assertEqual(chain["names_still_unexplained"], 0)
        self.assertEqual(chain["chains"][0]["member"], 0)
        self.assertEqual(chain["chains"][0]["levels"], 3)
        self.assertEqual(chain["chains"][0]["base"], "64x64")

    def test_a_name_no_chain_explains_is_counted_as_still_unexplained(self) -> None:
        check = tool.derivation_check(self.disc, self._document([self._name(0x1234, names.PSMT8)]),
                                      discs=containers)
        self.assertEqual(check["counts"]["names_tex0_not_reproduced"], 1)
        self.assertEqual(check["cross_member_chain"]["names_explained"], 0)
        self.assertEqual(check["cross_member_chain"]["names_still_unexplained"], 1)


if __name__ == "__main__":
    unittest.main()
