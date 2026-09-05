"""The PS2 executable-patch lane: interface real, every translation refused, pnach proved.

Nothing here needs a disc.  The ELF is synthetic, the ISO around it is
synthetic, and the only retail facts are identities (a serial, a CRC, a
digest).  What is proved: the host's patch catalogue is read as the host
stores it; every translation is refused with the reason; a hand-authored
recipe is planned against the ELF, emitted as a pnach and independently
verified; every way a pnach or a recipe can lie is caught; the conformance
harness covers the lane; and the lane stays off the module's capability list
until its registry row exists.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games import conformance, contract  # noqa: E402
from mod_editor.games._formats import ps2_elf  # noqa: E402
from mod_editor.games.nfl2k5_ps2 import CODE_PATCH_CAPABILITY_ID, CODE_PATCH_LANE, GAME, code_patches  # noqa: E402


class ElfAndPnachFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.words = code_patches.SYNTHETIC_WORDS
        self.elf = ps2_elf.build_synthetic_elf(self.words, base_vaddr=code_patches.SYNTHETIC_BASE)
        self.segments = ps2_elf.parse_program_headers(self.elf, "synthetic")

    def test_program_headers_and_address_mapping(self) -> None:
        [segment] = self.segments
        self.assertEqual(segment.vaddr, code_patches.SYNTHETIC_BASE)
        self.assertEqual(segment.filesz, 4 * len(self.words))
        self.assertTrue(segment.executable)
        for index, word in enumerate(self.words):
            self.assertEqual(ps2_elf.read_word(self.elf, self.segments, code_patches.SYNTHETIC_BASE + 4 * index), word)
        with self.assertRaisesRegex(ps2_elf.PnachError, r"\.bss"):
            ps2_elf.file_offset(self.segments, code_patches.SYNTHETIC_BASE + 4 * len(self.words))
        with self.assertRaisesRegex(ps2_elf.PnachError, "outside every loadable segment"):
            ps2_elf.file_offset(self.segments, 0x7FFFFFF0)

    def test_refuses_what_is_not_a_ps2_elf(self) -> None:
        with self.assertRaisesRegex(ps2_elf.PnachError, "not an ELF"):
            ps2_elf.parse_program_headers(b"MZ" + bytes(100), "junk")
        wrong_machine = bytearray(self.elf)
        struct.pack_into("<H", wrong_machine, 18, 3)  # EM_386
        with self.assertRaisesRegex(ps2_elf.PnachError, "not a MIPS executable"):
            ps2_elf.parse_program_headers(bytes(wrong_machine), "x86")
        big_endian = bytearray(self.elf)
        big_endian[5] = 2
        with self.assertRaisesRegex(ps2_elf.PnachError, "little-endian"):
            ps2_elf.parse_program_headers(bytes(big_endian), "be")

    def test_pcsx2_crc_is_the_xor_of_every_word(self) -> None:
        expected = 0
        for (word,) in struct.iter_unpack("<I", self.elf[: len(self.elf) - len(self.elf) % 4]):
            expected ^= word
        self.assertEqual(ps2_elf.pcsx2_crc(self.elf), f"{expected:08X}")
        self.assertEqual(ps2_elf.pcsx2_crc(b"\x01\x00\x00\x00\x02\x00\x00\x00\xff"), "00000003")

    def test_pnach_round_trip_and_strictness(self) -> None:
        text = ps2_elf.emit_pnach("Synthetic", "0000ABCD", [ps2_elf.PnachPatch(0x00100004, 0x1234)], ["note one"])
        self.assertEqual(text, "gametitle=Synthetic (CRC 0000ABCD)\ncomment=note one\npatch=1,EE,00100004,word,00001234\n")
        document = ps2_elf.parse_pnach(text)
        self.assertEqual(document.crc, "0000ABCD")
        self.assertEqual(document.patches, (ps2_elf.PnachPatch(0x00100004, 0x1234, True),))
        self.assertEqual(ps2_elf.parse_pnach("gametitle=Old style [42F9D5AF]\n").crc, "42F9D5AF")
        for bad, why in (
            ("patch=1,IOP,00100004,word,1\n", "only EE"),
            ("patch=1,EE,00100004,extended,1\n", "'extended'"),
            ("patch=1,EE,00100004,byte,1\n", "'byte'"),
            ("patch=1,EE,00100005,word,1\n", "not word-aligned"),
            ("patch=1,EE,00100004,word,1\npatch=1,EE,00100004,word,2\n", "patched twice"),
            ("cheatz=1\n", "unknown line"),
            ("patch=1,EE,zz,word,1\n", "not a patch line"),
        ):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ps2_elf.PnachError, why):
                    ps2_elf.parse_pnach(bad)
        skipped = ps2_elf.parse_pnach("[Section]\n// c\n# c\n; c\nauthor=me\npatch=0,EE,00100000,word,0\n")
        self.assertFalse(skipped.patches[0].enabled)
        with self.assertRaisesRegex(ps2_elf.PnachError, "at least one patch"):
            ps2_elf.emit_pnach("T", "00000000", [])
        with self.assertRaisesRegex(ps2_elf.PnachError, "eight-digit"):
            ps2_elf.emit_pnach("T", "xyz", [ps2_elf.PnachPatch(0, 0)])


class HostCatalogueTests(unittest.TestCase):
    def test_the_hosts_patches_are_read_as_stored_without_qt(self) -> None:
        patches = code_patches.host_patches()
        ids = [patch.patch_id for patch in patches]
        self.assertEqual(ids, sorted(ids))
        for expected in ("catch_slider", "accel_ramp", "draft_ai", "penalties", "edge_rename", "throw_tuning", "camera"):
            self.assertIn(expected, ids)
        by_id = {patch.patch_id: patch for patch in patches}
        self.assertEqual(by_id["penalties"].parameters["penalties"]["default"], "nfl")
        self.assertEqual(by_id["edge_rename"].host_site["kind"], "text")
        self.assertEqual(by_id["catch_slider"].host_site["kind"], "code")
        self.assertEqual(by_id["throw_tuning"].parameters["max_deep_yards"], {"type": "float", "min": 55.0, "max": 100.0, "default": 55.0})
        for patch in patches:
            self.assertEqual(patch.surface, code_patches.SURFACE)
            self.assertEqual(set(patch.host_site), {"executable", "executable_sha256", "flag", "kind", "catalogue", "applier"})
            self.assertTrue(patch.note)
        registry = json.loads((ROOT / "mod_editor/capabilities/registry.v1.json").read_text(encoding="utf-8"))
        [xbox] = [game for game in registry["games"] if game["id"] == "nfl2k5_xbox"]
        self.assertEqual(by_id["catch_slider"].host_site["executable_sha256"], xbox["retail_identity"]["executable_sha256"],
                         "the host site names the same retail executable the registry pins")
        self.assertNotIn("PyQt5", sys.modules.get("mod_editor.gui.gameplay_patches_panel_qt", None).__class__.__module__ if "mod_editor.gui.gameplay_patches_panel_qt" in sys.modules else "",
                         "reading the catalogue must not import the panel")


class LaneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lane = CODE_PATCH_LANE
        cls.work = Path(tempfile.mkdtemp(prefix="ps2-code-"))
        cls.source = cls.lane.synthetic_source(cls.work)
        cls.catalogue = cls.lane.build_catalogue(cls.source)
        cls.elf, _boot = ps2_elf.read_boot_elf(cls.source)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.work, ignore_errors=True)

    def _recipe(self, *rows):
        return {"schema": code_patches.RECIPE_SCHEMA, "patches": list(rows)}

    def _word(self, index: int, replacement: int) -> dict:
        return {"address": f"0x{code_patches.SYNTHETIC_BASE + 4 * index:08X}",
                "original": f"0x{code_patches.SYNTHETIC_WORDS[index]:08X}", "replacement": f"0x{replacement:08X}"}

    def test_the_lane_is_a_code_patch_lane_and_stays_unlisted_until_registered(self) -> None:
        self.assertIsInstance(self.lane, contract.CodePatchLane)
        self.assertIsInstance(self.lane, contract.Lane)
        self.assertEqual(self.lane.capability_id, CODE_PATCH_CAPABILITY_ID)
        self.assertEqual(self.lane.classification, "unknown")
        fragment = json.loads((ROOT / "mod_editor/games/nfl2k5_ps2/registry.fragment.json").read_text(encoding="utf-8"))
        registered = any(row["id"] == CODE_PATCH_CAPABILITY_ID for row in fragment["capabilities"])
        self.assertEqual(any(lane.lane_id == self.lane.lane_id for lane in GAME.lanes), registered,
                         "the lane is a capability the module claims exactly when its row is registered")
        for validator in self.lane.validators:
            self.assertTrue((ROOT / validator).is_file(), validator)
        self.assertIn(b"\r\n", (ROOT / self.lane.validators[1]).read_bytes())

    def test_catalogue_identity_and_targets(self) -> None:
        elf = self.catalogue.document["elf"]
        self.assertEqual(elf["serial"], "SLUS-20919")
        self.assertEqual(elf["boot_file"], "SLUS_209.19")
        self.assertFalse(elf["retail"], "a synthetic ELF is never retail")
        self.assertEqual(elf["pcsx2_crc"], ps2_elf.pcsx2_crc(self.elf))
        self.assertEqual(self.catalogue.document["translations_available"], 0)
        self.assertEqual([t.key for t in self.catalogue.targets], [p.patch_id for p in self.lane.patches()])
        self.assertTrue(all(t.label.endswith("not mapped to MIPS yet") for t in self.catalogue.targets))
        self.assertFalse(conformance.contains_payload(dict(self.catalogue.document)))

    def test_every_translation_is_refused_with_the_reason(self) -> None:
        for patch in self.lane.patches():
            with self.subTest(patch=patch.patch_id):
                with self.assertRaisesRegex(contract.Refusal, "not mapped to MIPS yet") as caught:
                    self.lane.translation(patch.patch_id, {})
                self.assertIn("SLUS_209.19", str(caught.exception))
                self.assertIn("PS2_CODE_PATCH_PIPELINE.md", str(caught.exception))
        with self.assertRaisesRegex(contract.Refusal, "not one of the host's"):
            self.lane.translation("no_such_patch", {})

    def test_check_edit_refuses_parameters_without_a_translation_and_accepts_words(self) -> None:
        target = self.catalogue.target("catch_slider")
        self.assertIn("not mapped to MIPS yet", self.lane.check_edit(target, {"parameters": {"enabled": True}}))
        self.assertIn("not something this lane takes", self.lane.check_edit(target, {"bogus": 1}))
        self.assertIn("must be a mapping", self.lane.check_edit(target, {"parameters": 3}))
        self.assertIn("non-empty list", self.lane.check_edit(target, {"mips": []}))
        self.assertIn("not word-aligned", self.lane.check_edit(target, {"mips": [{"address": "0x00100001", "original": 0, "replacement": 1}]}))
        self.assertIn("changes nothing", self.lane.check_edit(target, {"mips": [{"address": "0x00100000", "original": 1, "replacement": 1}]}))
        self.assertIsNone(self.lane.check_edit(target, {"mips": [self._word(2, 0x24020002)]}))

    def test_plan_build_verify_with_hand_authored_words(self) -> None:
        recipe = self._recipe({"patch": "catch_slider", "mips": [self._word(2, 0x24020002)], "note": "trial"},
                              {"patch": "accel_ramp", "mips": [self._word(5, 0x03E00009)]})
        plan = self.lane.plan(self.source, recipe, self.catalogue)
        self.assertEqual(plan.target_keys, ("catch_slider", "accel_ramp"))
        self.assertEqual(plan.declared_ranges, ())
        destination = self.work / "two.pnach"
        receipt = self.lane.build(self.source, destination, recipe, self.catalogue)
        text = destination.read_text(encoding="utf-8")
        self.assertIn(f"gametitle=ESPN NFL 2K5 (SLUS-20919) (CRC {self.catalogue.document['elf']['pcsx2_crc']})", text)
        self.assertIn(f"patch=1,EE,{code_patches.SYNTHETIC_BASE + 8:08X},word,24020002", text)
        self.assertIn("comment=catch_slider: trial", text)
        self.assertEqual(len([line for line in text.splitlines() if line.startswith("patch=")]), 2)
        [artifact] = receipt.artifacts
        self.assertEqual(artifact.kind, "pnach")
        self.assertEqual(Path(artifact.path), destination)
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)
        self.assertIn("2 word(s) verified", verdict.summary)
        self.assertEqual(receipt.document["delivery"], "pnach")
        self.assertNotIn("segments", receipt.document["elf"])

    def test_plan_refusals_name_the_condition(self) -> None:
        cases = (
            ({"patch": "catch_slider", "mips": [{"address": f"0x{code_patches.SYNTHETIC_BASE + 8:08X}", "original": "0x11111111", "replacement": "0x22222222"}]},
             "not derived against this executable"),
            ({"patch": "catch_slider", "mips": [{"address": f"0x{code_patches.SYNTHETIC_BASE + 4 * len(code_patches.SYNTHETIC_WORDS):08X}", "original": 0, "replacement": 1}]},
             r"\.bss"),
            ({"patch": "catch_slider", "mips": [{"address": "0x7FFFFFF0", "original": 0, "replacement": 1}]}, "outside every loadable segment"),
            ({"patch": "catch_slider", "parameters": {"enabled": True}}, "not mapped to MIPS yet"),
            ({"patch": "nothing_here", "mips": [self._word(2, 0x24020002)]}, "not a target this catalogue names"),
            ({"patch": "catch_slider", "surprise": 1, "mips": [self._word(2, 0x24020002)]}, "unknown keys"),
        )
        for row, why in cases:
            with self.subTest(why=why):
                with self.assertRaisesRegex(contract.Refusal, why):
                    self.lane.plan(self.source, self._recipe(row), self.catalogue)
        with self.assertRaisesRegex(contract.Refusal, "written twice"):
            self.lane.plan(self.source, self._recipe({"patch": "catch_slider", "mips": [self._word(2, 0x24020002)]},
                                                     {"patch": "accel_ramp", "mips": [self._word(2, 0x24020003)]}), self.catalogue)
        with self.assertRaisesRegex(contract.Refusal, "appears twice"):
            self.lane.plan(self.source, self._recipe({"patch": "catch_slider", "mips": [self._word(2, 0x24020002)]},
                                                     {"patch": "catch_slider", "mips": [self._word(5, 0x03E00009)]}), self.catalogue)
        with self.assertRaisesRegex(contract.Refusal, "recipe schema"):
            self.lane.plan(self.source, {"schema": "nope", "patches": []}, self.catalogue)
        other = Path(tempfile.mkdtemp(prefix="ps2-code-other-"))
        self.addCleanup(shutil.rmtree, other, True)
        different = ps2_elf.build_synthetic_elf((0x1, 0x2, 0x3), base_vaddr=code_patches.SYNTHETIC_BASE)
        other_iso = other / "other.iso"
        import ps2_iso9660 as iso_lib
        other_iso.write_bytes(iso_lib.build_synthetic_iso(files=[(b"SYSTEM.CNF;1", b"BOOT2 = cdrom0:\\SLUS_209.19;1\r\n"), (b"SLUS_209.19;1", different)],
                                                          sub_name=b"VC_20919", sub_files=[(b"0.;1", bytes(2048))]))
        with self.assertRaisesRegex(contract.Refusal, "changed since it was catalogued"):
            self.lane.plan(other_iso, self._recipe({"patch": "catch_slider", "mips": [self._word(2, 0x24020002)]}), self.catalogue)
        existing = self.work / "existing.pnach"
        existing.write_text("x", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(contract.Refusal, "already exists"):
            self.lane.build(self.source, existing, self._recipe({"patch": "catch_slider", "mips": [self._word(2, 0x24020002)]}), self.catalogue)
        with self.assertRaisesRegex(contract.Refusal, "is the source image"):
            self.lane.build(self.source, self.source, self._recipe({"patch": "catch_slider", "mips": [self._word(2, 0x24020002)]}), self.catalogue)

    def test_verify_fails_on_every_lie(self) -> None:
        recipe = self._recipe({"patch": "catch_slider", "mips": [self._word(2, 0x24020002)]})
        destination = self.work / "lies.pnach"
        receipt = self.lane.build(self.source, destination, recipe, self.catalogue)
        good = destination.read_text(encoding="utf-8")
        crc = self.catalogue.document["elf"]["pcsx2_crc"]
        address = f"{code_patches.SYNTHETIC_BASE + 8:08X}"
        lies = {
            "value": good.replace("word,24020002", "word,24020003"),
            "missing": "\n".join(line for line in good.splitlines() if not line.startswith("patch=")) + "\n",
            "extra": good + f"patch=1,EE,{code_patches.SYNTHETIC_BASE + 12:08X},word,00000000\n",
            "crc": good.replace(f"CRC {crc}", "CRC 00000000"),
            "disabled": good.replace(f"patch=1,EE,{address}", f"patch=0,EE,{address}"),
            "garbage": good + "not a line\n",
        }
        expected = self.lane._patches_from_rows(receipt.document["patches"], dict(receipt.document["elf"]))
        for name, text in lies.items():
            with self.subTest(lie=name):
                verdict = self.lane.verify_pnach(text, self.source, expected)
                self.assertFalse(verdict.passed, name)
                self.assertTrue(verdict.summary.startswith("Verification failed"), verdict.summary)
        tampered = self.work / "tampered.pnach"
        tampered.write_text(lies["value"], encoding="utf-8", newline="\n")
        self.assertFalse(self.lane.verify(self.source, tampered, receipt).passed, "the artifact digest catches a rewritten file")
        lying_receipt = contract.Receipt(receipt.schema, receipt.lane_id, receipt.source, receipt.destination, (), {
            **dict(receipt.document),
            "patches": [{"patch_id": "catch_slider", "note": "", "parameters": {},
                         "words": [{"address": f"0x{address}", "original": "0xDEADBEEF", "replacement": "0x24020002"}]}],
        }, receipt.artifacts)
        verdict = self.lane.verify(self.source, destination, lying_receipt)
        self.assertFalse(verdict.passed)
        self.assertIn("not the 0xDEADBEEF the recipe expects", verdict.summary)

    def test_the_conformance_harness_covers_the_lane_and_the_selftest_passes(self) -> None:
        checks = conformance.check_lane_behaviour(GAME, self.lane, self.work / "harness")
        self.assertTrue(all(check.passed for check in checks), "\n".join(c.line() for c in checks if not c.passed))
        names = {check.name.rsplit(".", 1)[-1] for check in checks}
        for required in ("identify_synthetic_is_not_retail", "catalogue_is_retail_free", "plan_refuses_unknown_target",
                         "receipt_declares_ranges_or_artifacts", "artifacts_match_their_digests", "verify_passes",
                         "build_refuses_existing_destination", "verify_fails_on_undeclared_change"):
            self.assertIn(required, names)
        self.assertEqual(code_patches.selftest(), 0)
        boundary = conformance.check_boundary(ROOT / "mod_editor/games/nfl2k5_ps2", "mod_editor.games.nfl2k5_ps2")
        self.assertTrue(all(check.passed for check in boundary), [c.detail for c in boundary])


if __name__ == "__main__":
    unittest.main()
