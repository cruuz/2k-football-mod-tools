"""The Madden 09 (PS2) executable-patch lane, on a synthetic ELF only.

Every word in this file is written from the R5900 encoding, not lifted from any
image.  The lane's whole promise today is that it refuses every translation and
still proves the pipeline around one, and that is what these tests hold it to.
"""

from __future__ import annotations

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

from mod_editor.games.contract import Refusal  # noqa: E402
from mod_editor.games.madden09_ps2 import IDENTITY, code_patches, containers  # noqa: E402


class CatalogueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-code-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = code_patches.Madden09CodePatchLane(IDENTITY)
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)

    def test_nothing_is_mapped_and_the_lane_says_so(self) -> None:
        self.assertEqual(code_patches.TRANSLATIONS, {})
        self.assertEqual(self.catalogue.document["translations_available"], 0)
        self.assertEqual(self.lane.classification, "unknown")
        self.assertEqual(self.lane.page, "gameplay")

    def test_every_proposed_patch_refuses_translation_by_name(self) -> None:
        for patch in self.lane.patches():
            with self.assertRaises(Refusal) as caught:
                self.lane.translation(patch.patch_id, {})
            message = str(caught.exception)
            self.assertIn(patch.patch_id, message)
            self.assertIn(containers.BOOT_FILE, message)
            self.assertIn("not mapped", message)

    def test_an_unknown_patch_id_is_refused_with_the_choices(self) -> None:
        with self.assertRaises(Refusal) as caught:
            self.lane.translation("no-such-patch", {})
        self.assertIn("no-such-patch", str(caught.exception))
        self.assertIn("choose one of", str(caught.exception))

    def test_check_edit_refuses_an_unmapped_patch_and_accepts_hand_words(self) -> None:
        target = self.catalogue.targets[0]
        self.assertIn("not mapped", self.lane.check_edit(target, {"parameters": {}}))
        good = {"mips": [{"address": "00100008", "original": "24020001",
                          "replacement": "24020000"}]}
        self.assertIsNone(self.lane.check_edit(target, good))

    def test_check_edit_names_a_key_it_does_not_take(self) -> None:
        target = self.catalogue.targets[0]
        problem = self.lane.check_edit(target, {"colour": "red"})
        self.assertIn("colour", problem)

    def test_the_catalogue_reports_the_elf_it_read(self) -> None:
        elf = self.catalogue.document["elf"]
        self.assertEqual(elf["serial"], containers.SERIAL)
        self.assertEqual(elf["boot_file"], containers.BOOT_FILE)
        self.assertEqual(elf["edition"], "unknown")
        self.assertFalse(elf["retail"], "a synthetic ELF must never pass as retail")


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-code-pipe-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = code_patches.Madden09CodePatchLane(IDENTITY)
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)
        self.recipe = self.lane.compose_recipe(self.lane.conformance_edits(self.catalogue))

    def test_a_plan_checks_every_original_against_the_user_s_own_elf(self) -> None:
        plan = self.lane.plan(self.source, self.recipe, self.catalogue)
        self.assertEqual(len(plan.document["patches"]), 1)
        self.assertEqual(plan.document["patches"][0]["words"][0]["address"], "00100008")

    def test_a_plan_refuses_words_derived_against_another_executable(self) -> None:
        wrong = {"schema": code_patches.RECIPE_SCHEMA, "patches": [{
            "patch": self.catalogue.targets[0].key,
            "parameters": {},
            "mips": [{"address": "00100008", "original": "DEADBEEF",
                      "replacement": "00000000"}],
        }]}
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, wrong, self.catalogue)
        self.assertIn("not derived against this executable", str(caught.exception))

    def test_a_plan_refuses_an_address_outside_the_elf(self) -> None:
        wrong = {"schema": code_patches.RECIPE_SCHEMA, "patches": [{
            "patch": self.catalogue.targets[0].key,
            "parameters": {},
            "mips": [{"address": "0FFFFFF0", "original": "00000000",
                      "replacement": "00000001"}],
        }]}
        with self.assertRaises(Refusal):
            self.lane.plan(self.source, wrong, self.catalogue)

    def test_build_writes_a_pnach_and_verify_passes_it(self) -> None:
        out = self.work / "madden09.pnach"
        receipt = self.lane.build(self.source, out, self.recipe, self.catalogue)
        self.assertTrue(out.is_file())
        self.assertEqual(len(receipt.artifacts), 1)
        verdict = self.lane.verify(self.source, out, receipt)
        self.assertTrue(verdict.passed, verdict.summary)
        self.assertIn("verified against the boot ELF", verdict.summary)

    def test_verify_fails_a_tampered_pnach(self) -> None:
        out = self.work / "madden09.pnach"
        receipt = self.lane.build(self.source, out, self.recipe, self.catalogue)
        tampered = self.work / "tampered.pnach"
        tampered.write_text(
            out.read_text(encoding="utf-8").replace("24020000", "24020002"),
            encoding="utf-8", newline="\n")
        self.assertFalse(self.lane.verify(self.source, tampered, receipt).passed)

    def test_verify_fails_when_the_pnach_names_another_crc(self) -> None:
        out = self.work / "madden09.pnach"
        receipt = self.lane.build(self.source, out, self.recipe, self.catalogue)
        text = out.read_text(encoding="utf-8")
        crc = receipt.document["crc"]
        wrong = self.work / "wrongcrc.pnach"
        wrong.write_text(text.replace(crc, "00000000"), encoding="utf-8", newline="\n")
        verdict = self.lane.verify(self.source, wrong, receipt)
        self.assertFalse(verdict.passed)
        self.assertIn("CRC", verdict.summary)

    def test_build_never_overwrites_and_never_writes_over_the_source(self) -> None:
        out = self.work / "madden09.pnach"
        self.lane.build(self.source, out, self.recipe, self.catalogue)
        with self.assertRaises(Refusal) as caught:
            self.lane.build(self.source, out, self.recipe, self.catalogue)
        self.assertIn("refusing to overwrite", str(caught.exception))
        with self.assertRaises(Refusal) as caught:
            self.lane.build(self.source, self.source, self.recipe, self.catalogue)
        self.assertIn("NEW file beside it", str(caught.exception))

    def test_the_selftest_passes(self) -> None:
        self.assertEqual(code_patches.selftest(), 0)


if __name__ == "__main__":
    unittest.main()
