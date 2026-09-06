"""The four Madden 09 (PS2) art pages, on synthetic data only.

Every disc these tests touch is built by ``art_pages.build_synthetic_art_disc``
out of the format's own rules -- computed palettes, counting ramps of indices,
a preload cache carrying copies of exactly the shape the retail caches carry.
No game byte, no palette entry and no decoded pixel is here.  The evidence that
the same code reads *real* art is
``docs/product/MADDEN09_PS2_ART_PAGES.md``; what these tests hold is that the
rules are implemented as written, that each refusal names its fix, and that the
uniform lanes these four are built out of did not change shape underneath them.
"""

from __future__ import annotations

import json
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
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.games.contract import Edit, Refusal, lane_page  # noqa: E402
from mod_editor.games._formats import ea_terf  # noqa: E402
from mod_editor.games.madden09_ps2 import art_pages, containers, uniform_art  # noqa: E402


class LaneShapeTests(unittest.TestCase):
    """Where each row lands, and that it is the uniform writer, not a copy of it."""

    def test_every_lane_is_the_uniform_writer_pointed_somewhere_else(self) -> None:
        for cls in art_pages.ART_PAGE_LANES:
            with self.subTest(lane=cls.__name__):
                self.assertTrue(issubclass(cls, uniform_art.UniformDiscArtWriteLane),
                                "an art page must reuse the writer, never fork it")
                for name in ("_compose", "build", "verify", "encode", "decode_png",
                             "_patch_preload", "_check_one_texture"):
                    self.assertIs(getattr(cls, name),
                                  getattr(uniform_art.UniformDiscArtWriteLane, name),
                                  f"{cls.__name__} overrides {name}; that is a fork")

    def test_each_row_lands_on_the_page_it_names(self) -> None:
        wanted = {
            "madden09ps2.stadiums.textures": "stadiums",
            "madden09ps2.field_art.textures": "field_art",
            "madden09ps2.presentation.ui_textures": "presentation",
            "madden09ps2.rosters.face_textures": "rosters",
        }
        found = {cls.capability_id: lane_page(cls()) for cls in art_pages.ART_PAGE_LANES}
        self.assertEqual(found, wanted)

    def test_every_row_is_offline_writer_proved_and_never_more(self) -> None:
        for cls in art_pages.ART_PAGE_LANES:
            with self.subTest(lane=cls.__name__):
                self.assertEqual(cls.classification, "offline-writer-proved")
                self.assertIn("NOT_BOOTED", dir(cls))
                self.assertIn("no rebuilt madden 09 container has been booted",
                              cls.NOT_BOOTED.lower())

    def test_each_page_has_its_own_recipe_schema(self) -> None:
        schemas = [cls.recipe_schema for cls in art_pages.ART_PAGE_LANES]
        schemas += [uniform_art.RECIPE_SCHEMA, uniform_art.DISC_RECIPE_SCHEMA]
        self.assertEqual(len(schemas), len(set(schemas)),
                         "a recipe for one page must not be accepted by another")

    def test_the_containers_are_the_ones_the_pages_claim(self) -> None:
        names = {cls.page: [name for name, _group, _note in cls.art_containers]
                 for cls in art_pages.ART_PAGE_LANES}
        self.assertEqual(names["stadiums"], ["STADIUMS.DAT", "STADATA.DAT"])
        self.assertEqual(names["field_art"], ["FIELDART.DAT"])
        self.assertEqual(names["rosters"],
                         ["PLYRFACE.DAT", "COACFACE.DAT", "TATTOOS.DAT", "UIS_PLYR.DAT"])
        ui = names["presentation"]
        self.assertEqual(len([name for name in ui if name.startswith("UIS_")]), 48)
        self.assertIn("LOADDATA.DAT", ui)
        self.assertIn("ICONS.DAT", ui)
        self.assertEqual(ui[-1], "UIS_PLYR.DAT",
                         "the 3,286 portraits go last so they do not fill the target list")
        for page, listed in names.items():
            with self.subTest(page=page):
                self.assertEqual(len(listed), len(set(listed)), "a container listed twice")
                self.assertTrue(all(name.endswith(".DAT") for name in listed))

    def test_a_synthetic_layout_only_names_containers_the_lane_owns(self) -> None:
        for cls in art_pages.ART_PAGE_LANES:
            with self.subTest(lane=cls.__name__):
                owned = {name for name, _group, _note in cls.art_containers}
                self.assertTrue(cls.synthetic_layout, "CI needs something to prove it on")
                for name, chunk, alignment, _textures in cls.synthetic_layout:
                    self.assertIn(name, owned)
                    self.assertIn(chunk, ("COMP", "DATA"))
                    self.assertTrue(alignment > 0 and not alignment & (alignment - 1))

    def test_both_container_shapes_are_proved_across_the_four_pages(self) -> None:
        chunks = {chunk for cls in art_pages.ART_PAGE_LANES
                  for _name, chunk, _alignment, _textures in cls.synthetic_layout}
        self.assertEqual(chunks, {"COMP", "DATA"})

    def test_the_uniform_rows_kept_their_own_containers_and_schemas(self) -> None:
        self.assertIs(uniform_art.UniformArtLane.art_containers, uniform_art.ART_CONTAINERS)
        self.assertIs(uniform_art.UniformDiscArtWriteLane.art_containers,
                      uniform_art.ART_CONTAINERS)
        self.assertEqual(uniform_art.UniformArtLane.catalog_schema, uniform_art.CATALOG_SCHEMA)
        self.assertEqual(uniform_art.UniformArtLane.page, "uniforms")
        self.assertEqual(uniform_art.UniformArtLane.classification, "extract-only")


class CatalogueTests(unittest.TestCase):
    """One page's catalogue on its own synthetic disc."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="m09-art-pages-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = art_pages.PresentationArtLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)

    def test_the_catalogue_carries_shape_and_no_pixels(self) -> None:
        document = self.catalogue.document
        self.assertEqual(document["schema"], self.lane.catalog_schema)
        self.assertEqual(document["page"], "presentation")
        self.assertTrue(document["page_scope"])
        self.assertTrue(self.catalogue.targets)
        blob = json.dumps(document, default=dict)
        self.assertNotIn("data:", blob)
        for row in document["rows"]:
            self.assertEqual(set(row) & {"pixels", "palette", "payload"}, set())

    def test_a_container_with_no_texture_is_counted_not_dropped(self) -> None:
        census = self.catalogue.document["members_by_format"]
        self.assertIn("ICONS.DAT", census, "a container with no MMAP member must still be listed")
        self.assertNotIn("MMAP", census["ICONS.DAT"])
        self.assertEqual(sum(census["ICONS.DAT"].values()), 2)

    def test_members_that_are_not_textures_are_listed_with_the_reason(self) -> None:
        document = self.catalogue.document
        self.assertIn("ICONS.DAT", document["members_not_texture"])
        note = document["members_not_texture_note"]
        self.assertIn("SMF", note)
        self.assertIn("DMF", note)
        self.assertIn("no layout for either is documented", note)

    def test_identity_coverage_counts_every_container_it_listed(self) -> None:
        coverage = self.catalogue.document["identity_coverage"]
        listed = {row["container"] for row in self.catalogue.document["rows"]}
        self.assertEqual(set(coverage), listed)
        for container, counts in coverage.items():
            with self.subTest(container=container):
                self.assertEqual(counts["confirmed"], 0,
                                 "a synthetic texture was never drawn by any emulator")
                self.assertEqual(counts["named"], counts["derived"],
                                 "every name on a synthetic disc is derived from the texture's own bytes")
                self.assertLessEqual(counts["named"], counts["listed"])

    def test_a_texture_no_dump_has_shown_gets_a_derived_name_and_says_so(self) -> None:
        target = self.catalogue.targets[0]
        name = self.lane.replacement_identity(target)
        names = self.lane.replacement_identities(target)
        self.assertTrue(name and name.endswith(".png"))
        self.assertTrue(all(convention.startswith("derived:") for convention in names),
                        "a synthetic texture has only derived names, never a dump-confirmed one")
        self.assertIn(name, names["derived:modern"])
        self.assertIn("Derived from this texture's own bytes", self.lane.identity_note(target))


class IdentityTableTests(unittest.TestCase):
    """The second identity table, and that the lane reads both."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="m09-art-identity-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = art_pages.StadiumArtLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)

    def test_a_name_in_the_second_table_is_answered(self) -> None:
        target = self.catalogue.targets[0]
        table = self.work / "extra-identities.json"
        table.write_text(json.dumps({
            "schema": uniform_art.IDENTITY_SCHEMA,
            "identities": {target.key: {"names": {"classic": ["aaaa-bbbb-00001dd3.png"],
                                                  "modern": ["aaaa-bbbb-00001dd3.png"]}}},
        }), encoding="utf-8")
        original = art_pages.ART_PAGE_IDENTITY_DOCUMENT
        art_pages.ART_PAGE_IDENTITY_DOCUMENT = table
        uniform_art._IDENTITY_CACHE.pop(str(table), None)
        try:
            self.assertEqual(self.lane.replacement_identity(target), "aaaa-bbbb-00001dd3.png")
            self.assertEqual(self.lane.replacement_identities(target)["modern"],
                             ["aaaa-bbbb-00001dd3.png"])
        finally:
            art_pages.ART_PAGE_IDENTITY_DOCUMENT = original
            uniform_art._IDENTITY_CACHE.pop(str(table), None)

    def test_a_table_of_the_wrong_schema_is_ignored_rather_than_trusted(self) -> None:
        target = self.catalogue.targets[0]
        table = self.work / "wrong-schema.json"
        table.write_text(json.dumps({
            "schema": "something_else/v1",
            "identities": {target.key: {"names": {"classic": ["nope.png"]}}},
        }), encoding="utf-8")
        original = art_pages.ART_PAGE_IDENTITY_DOCUMENT
        art_pages.ART_PAGE_IDENTITY_DOCUMENT = table
        uniform_art._IDENTITY_CACHE.pop(str(table), None)
        try:
            name = self.lane.replacement_identity(target)
            self.assertNotEqual(name, "nope.png", "a table of another schema is never trusted")
            self.assertIn(name, self.lane.replacement_identities(target)["derived:modern"],
                          "with the table ignored, the derived name is what remains")
        finally:
            art_pages.ART_PAGE_IDENTITY_DOCUMENT = original
            uniform_art._IDENTITY_CACHE.pop(str(table), None)

    def test_the_shipped_second_table_is_the_one_the_lane_reads(self) -> None:
        path = ROOT / art_pages.ART_PAGE_IDENTITY_DOCUMENT
        self.assertTrue(path.is_file(), f"{path} is missing")
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], uniform_art.IDENTITY_SCHEMA)
        owned = {name for cls in art_pages.ART_PAGE_LANES
                 for name, _group, _note in cls.art_containers}
        for key, entry in document["identities"].items():
            container, member, image = key.split(":")
            self.assertIn(container, owned)
            self.assertEqual(int(member), entry["member"])
            self.assertEqual(int(image), entry["image"])
            self.assertTrue(entry["names"])
        self.assertEqual(len(document["identities"]),
                         document["counts"]["textures_new_here"])

    def test_the_shipped_inventory_is_counts_and_digests_only(self) -> None:
        path = ROOT / "docs/product/measured/madden09_ps2/art-page-textures.json"
        self.assertTrue(path.is_file(), f"{path} is missing")
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], "madden09_ps2_art_page_textures/v1")
        self.assertEqual(set(document["pages"]),
                         {cls.page for cls in art_pages.ART_PAGE_LANES})
        for page, row in document["pages"].items():
            with self.subTest(page=page):
                self.assertEqual(len(row["catalogue_sha256"]), 64)
                self.assertGreater(row["texture_members"], 0)
                self.assertGreaterEqual(row["images"], row["images_decodable"])


class WriteBackTests(unittest.TestCase):
    """The disc write-back, on a synthetic disc of both container shapes."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="m09-art-write-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = art_pages.FaceArtLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)
        self.edits = self.lane.conformance_edits(self.catalogue)
        self.recipe = self.lane.compose_recipe(self.edits)

    def _build(self, name: str = "out.iso"):
        destination = self.work / name
        receipt = self.lane.build(self.source, destination, self.recipe, self.catalogue)
        return destination, receipt

    def test_a_build_writes_the_textures_and_verify_passes(self) -> None:
        destination, receipt = self._build()
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)
        self.assertIn("No rebuilt Madden 09 container has been booted", verdict.summary)
        self.assertEqual(len(receipt.document["textures"]), len(self.edits))
        for row in receipt.document["textures"]:
            self.assertEqual(row["exact_pixels"], row["total_pixels"],
                             "a flip is exactly representable in the texture's own palette")
            self.assertEqual(row["max_channel_error"], 0)

    def test_a_data_container_is_rewritten_stored_and_a_comp_one_may_compress(self) -> None:
        _destination, receipt = self._build()
        codecs = {row["container"]: row.get("codec_name")
                  for row in receipt.document["members"] if row["member"] is not None}
        self.assertEqual(codecs["PLYRFACE.DAT"], "NONE (stored)",
                         "a plain DATA container has no codec table to record LZH1 in")
        self.assertEqual(codecs["TATTOOS.DAT"], "NONE (stored)")
        self.assertIn(codecs["COACFACE.DAT"], ("LZH1", "NONE (stored)"))

    def test_a_cached_directory_and_a_cached_member_are_both_kept_in_step(self) -> None:
        _destination, receipt = self._build()
        copies = receipt.document["preload_copies"]
        self.assertTrue(any(copy["kind"] == "header" for copy in copies),
                        "a moved directory must be mirrored into every cached copy")
        self.assertTrue(any(copy["kind"] == "member" for copy in copies),
                        "a carried member that was rewritten must be rewritten in the cache")

    def test_verify_fails_when_a_cached_copy_goes_stale(self) -> None:
        destination, receipt = self._build()
        copy = next(item for item in receipt.document["preload_copies"]
                    if item["kind"] == "header")
        disc = containers.open_disc(destination)
        entry = next(item for item in containers.data_files(disc) if item.name == copy["cache"])
        blob = bytearray(containers.read_file(disc, entry, limit=None))
        blob[copy["offset"]] ^= 0xFF
        with open(destination, "r+b") as handle:
            handle.seek(containers.iso_lib.extent_byte_offset(disc, entry.lba, 0))
            handle.write(bytes(blob[:2048]))
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertFalse(verdict.passed)
        self.assertIn(copy["cache"], verdict.summary)

    def test_the_preload_check_fails_when_a_cache_disagrees_with_its_container(self) -> None:
        """The guard itself, handed a container the cache no longer matches.

        Driven directly rather than through a tampered image: the image-level
        verifier digests every file the build wrote, so it catches a poked byte
        first and this check would never be reached -- and a guard nothing can
        reach is a guard nobody has tested.
        """

        destination, _receipt = self._build()
        disc = containers.open_disc(destination)
        files = {entry.name: entry for entry in containers.data_files(disc)}
        blob = containers.read_file(disc, files["PLYRFACE.DAT"])
        replacement = containers.synthetic_mmap(16, 16, seed=500, retail_layout=True)
        self.assertEqual(len(replacement),
                         ea_terf.parse_terf(blob).members[0].decompressed_size,
                         "the stand-in must be the same size, so only its bytes differ")
        drifted = ea_terf.rewrite_member(blob, 0, replacement, codec=ea_terf.CODEC_STORED)
        verdict, checked = self.lane._check_preload(disc, files, drifted, "PLYRFACE.DAT")
        self.assertIsNotNone(verdict)
        self.assertFalse(verdict.passed)
        self.assertIn("preloads from that copy", verdict.summary)
        self.assertIn("GAME.QKL", verdict.summary)

    def test_a_carried_member_that_changes_size_is_refused_by_name(self) -> None:
        disc = containers.open_disc(self.source)
        present = {entry.name: entry for entry in containers.data_files(disc)}
        preload = containers.preload_copies(disc)
        before = containers.read_file(disc, present["PLYRFACE.DAT"])
        bigger = containers.synthetic_mmap(32, 32, seed=99, retail_layout=True)
        after = ea_terf.rewrite_member(before, 0, bigger, codec=ea_terf.CODEC_STORED)
        with self.assertRaises(Refusal) as caught:
            self.lane._patch_preload(disc, present, preload, {}, [], "PLYRFACE.DAT",
                                     before, after, [0])
        message = str(caught.exception)
        self.assertIn("is copied into", message)
        self.assertIn("changed its stored size", message)
        self.assertIn("nothing was written", message.lower())

    def test_a_texture_from_another_page_is_refused_by_name(self) -> None:
        recipe = {"schema": self.lane.recipe_schema,
                  "textures": [{"texture": "STADIUMS.DAT:0:0",
                                "png": str(self.edits[0].values["png"])}]}
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, recipe, None)
        self.assertIn("is not one of the art containers this lane writes",
                      str(caught.exception))

    def test_a_recipe_from_another_page_is_refused_by_schema(self) -> None:
        other = art_pages.StadiumArtLane()
        recipe = dict(self.recipe, schema=other.recipe_schema)
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, recipe, self.catalogue)
        self.assertIn(self.lane.recipe_schema, str(caught.exception))

    def test_a_png_of_the_wrong_size_is_refused_naming_the_size_it_wanted(self) -> None:
        target = self.catalogue.targets[0]
        wrong = self.work / "wrong.png"
        wrong.write_bytes(uniform_art.write_rgba_png(bytes(4 * 5 * 4), 5, 4))
        problem = self.lane.check_edit(target, {"png": str(wrong)})
        self.assertIn(f"{target.raw['width']}x{target.raw['height']}", str(problem))

    def test_an_edit_with_no_png_is_refused_with_what_to_do(self) -> None:
        target = self.catalogue.targets[0]
        problem = self.lane.check_edit(target, {})
        self.assertIn("this lane writes a texture, so it needs a PNG", str(problem))

    def test_build_refuses_the_source_as_the_destination(self) -> None:
        with self.assertRaises(Refusal):
            self.lane.build(self.source, self.source, self.recipe, self.catalogue)


class ValidatorTests(unittest.TestCase):
    """The shipped validators: runnable in a shipped tree, and cmd.exe-safe."""

    def test_both_validators_exist_and_name_the_pass_line(self) -> None:
        for name in ("tools/validate_madden09_ps2_art_pages.sh",
                     "tools/validate_madden09_ps2_art_pages.bat"):
            with self.subTest(validator=name):
                path = ROOT / name
                self.assertTrue(path.is_file(), f"{name} is missing")
                text = path.read_text(encoding="utf-8")
                self.assertIn("MADDEN09_PS2_ART_PAGES_VALIDATION_PASS", text)
                self.assertNotIn("unittest", text,
                                 "a shipped validator must not import the test tree")

    def test_the_batch_validator_keeps_parentheses_out_of_its_echo_lines(self) -> None:
        text = (ROOT / "tools/validate_madden09_ps2_art_pages.bat").read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.lower().startswith("echo"):
                with self.subTest(line=number):
                    self.assertNotIn("(", stripped, "cmd.exe reads it as the end of an if block")
                    self.assertNotIn(")", stripped)

    def test_every_lane_names_the_validator_that_proves_it(self) -> None:
        for cls in art_pages.ART_PAGE_LANES:
            with self.subTest(lane=cls.__name__):
                self.assertEqual(cls.validators,
                                 ("tools/validate_madden09_ps2_art_pages.sh",
                                  "tools/validate_madden09_ps2_art_pages.bat"))


class RegistryTests(unittest.TestCase):
    """The four rows say what the lanes do, and nothing above it."""

    def setUp(self) -> None:
        self.fragment = json.loads(
            (ROOT / "mod_editor/games/madden09_ps2/registry.fragment.json")
            .read_text(encoding="utf-8"))
        self.rows = {row["id"]: row for row in self.fragment["capabilities"]}

    def test_every_lane_has_a_row_that_matches_it(self) -> None:
        for cls in art_pages.ART_PAGE_LANES:
            with self.subTest(lane=cls.__name__):
                row = self.rows.get(cls.capability_id)
                self.assertIsNotNone(row, f"{cls.capability_id} has no registry row")
                self.assertEqual(row["classification"], cls.classification)
                self.assertEqual(row["surface"], cls.surface)
                self.assertEqual(row["backend"]["module"],
                                 "mod_editor/games/madden09_ps2/art_pages.py")
                self.assertEqual(row["backend"]["operation"], "write")
                self.assertEqual(row["gui"]["mode"], "edit")
                self.assertIn(cls.lane_id, row["backend"]["command"])

    def test_no_row_claims_a_runtime_it_does_not_have(self) -> None:
        for cls in art_pages.ART_PAGE_LANES:
            row = self.rows[cls.capability_id]
            with self.subTest(lane=cls.__name__):
                self.assertEqual(row["runtime"]["status"], "not-applicable")
                self.assertEqual(row["runtime"]["evidence"], [])
                self.assertIn("NO rebuilt Madden 09 container has ever been booted",
                              row["runtime"]["scope"])
                self.assertIn("NOT booted", row["summary"])


if __name__ == "__main__":
    unittest.main()
