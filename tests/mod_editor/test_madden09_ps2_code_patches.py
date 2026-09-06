"""The Madden 09 (PS2) executable-patch lane, on synthetic sources only.

The lane translates one patch -- the create-a-playbook editor's five capacity
checks -- and refuses the other six by name.  These tests hold it to both
halves, and to the arithmetic in between: ``IMM = cap + 1``, and **only** the
16-bit immediate of each instruction ever changes.

The five addresses and five original words appear here because they are this
lane's translation table -- the deliverable itself, exactly as they would be in
a pnach.  **No other byte of any retail executable is in this file**, and no
test here opens a disc: the synthetic ELF is built from the lane's own table.
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
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.games._formats import ps2_elf  # noqa: E402
from mod_editor.games.contract import CodePatchLane, Refusal  # noqa: E402
from mod_editor.games.madden09_ps2 import IDENTITY, code_patches, containers  # noqa: E402

CAPS = {"formations_cap": 30, "sets_cap": 130, "plays_cap": 400, "plays_per_set_cap": 120}


class TranslationTableTests(unittest.TestCase):
    """The table itself: five sites, four parameters, and the shipped caps."""

    def test_the_lane_translates_exactly_one_patch(self) -> None:
        self.assertEqual(sorted(code_patches.TRANSLATIONS), [code_patches.PLAYBOOK_CAPS_PATCH_ID])
        self.assertEqual(sorted(code_patches.TRANSLATION_NOTES), [code_patches.PLAYBOOK_CAPS_PATCH_ID])

    def test_every_site_is_an_sltiu_whose_immediate_is_its_cap_plus_one(self) -> None:
        for site in code_patches.CAP_SITES:
            with self.subTest(site.table):
                self.assertEqual(site.original >> 26, 0x0B, "opcode 0x0B is sltiu")
                self.assertEqual(site.immediate, site.shipped_cap + 1)
                self.assertEqual(site.address % 4, 0, "an instruction is word-aligned")
                self.assertIn(site.parameter, code_patches.CAP_PARAMETERS)
                self.assertIn(f", {site.shipped_cap + 1}", site.disassembly)

    def test_the_declared_register_is_the_one_the_word_encodes(self) -> None:
        names = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
                 "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
                 "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
                 "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]
        for site in code_patches.CAP_SITES:
            with self.subTest(site.table):
                self.assertEqual(names[(site.original >> 16) & 31], site.register)

    def test_each_parameter_floors_at_the_largest_cap_it_drives(self) -> None:
        for name in code_patches.CAP_PARAMETERS:
            driven = [site.shipped_cap for site in code_patches.CAP_SITES if site.parameter == name]
            self.assertTrue(driven, f"{name} drives no site")
            self.assertEqual(code_patches._floor(name), max(driven))

    def test_sets_cap_drives_both_tables_of_the_same_conjunction(self) -> None:
        tables = [site.table for site in code_patches.CAP_SITES if site.parameter == "sets_cap"]
        self.assertEqual(tables, ["PBST", "SETL"])


class TranslationArithmeticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lane = code_patches.Madden09CodePatchLane(IDENTITY)

    def words(self, parameters):
        return {word.address: word for word
                in self.lane.translation(code_patches.PLAYBOOK_CAPS_PATCH_ID, parameters).words}

    def test_only_the_immediate_changes(self) -> None:
        for address, word in self.words(CAPS).items():
            with self.subTest(hex(address)):
                self.assertEqual(word.replacement >> 16, word.original >> 16,
                                 "opcode and both register fields must be carried through")

    def test_the_new_immediate_is_the_cap_plus_one(self) -> None:
        words = self.words(CAPS)
        for site in code_patches.CAP_SITES:
            with self.subTest(site.table):
                self.assertEqual(words[site.address].replacement & 0xFFFF,
                                 CAPS[site.parameter] + 1)

    def test_a_cap_left_at_its_shipped_value_writes_no_word(self) -> None:
        words = self.words({"plays_cap": 400})
        self.assertEqual(sorted(words), [0x0070955C])

    def test_raising_only_sets_writes_both_of_its_words(self) -> None:
        self.assertEqual(sorted(self.words({"sets_cap": 60})), [0x007094D4, 0x00709500])

    def test_the_largest_allowed_cap_still_fits_sixteen_bits(self) -> None:
        for word in self.words({"plays_cap": code_patches.MAX_CAP}).values():
            self.assertEqual(word.replacement & 0xFFFF, code_patches.MAX_IMMEDIATE)
            self.assertLessEqual(word.replacement, 0xFFFFFFFF)

    def test_the_note_names_every_cap_it_raised(self) -> None:
        note = code_patches.playbook_caps_note(CAPS)
        for site in code_patches.CAP_SITES:
            self.assertIn(f"{site.table} {site.shipped_cap}->{CAPS[site.parameter]}", note)
        self.assertIn("nothing here has been booted", note)

    def test_the_note_says_when_an_immediate_sign_extends_away_the_check(self) -> None:
        note = code_patches.playbook_caps_note({"plays_cap": code_patches.MAX_CAP})
        self.assertIn("sign-extends", note)
        self.assertIn("unconditional pass", note)
        self.assertNotIn("sign-extends", code_patches.playbook_caps_note({"plays_cap": 400}))


class ParameterRefusalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lane = code_patches.Madden09CodePatchLane(IDENTITY)

    def refuse(self, parameters):
        with self.assertRaises(Refusal) as caught:
            self.lane.translation(code_patches.PLAYBOOK_CAPS_PATCH_ID, parameters)
        return str(caught.exception)

    def test_a_cap_below_the_shipped_one_is_refused_and_says_why(self) -> None:
        message = self.refuse({"plays_cap": 99})
        self.assertIn("below the 100", message)
        self.assertIn("strand", message)

    def test_a_cap_past_the_sixteen_bit_immediate_is_refused(self) -> None:
        message = self.refuse({"sets_cap": code_patches.MAX_CAP + 1})
        self.assertIn("16 bits", message)
        self.assertIn(str(code_patches.MAX_CAP), message)

    def test_a_boolean_is_not_a_row_count(self) -> None:
        self.assertIn("whole number", self.refuse({"formations_cap": True}))

    def test_a_string_is_not_a_row_count(self) -> None:
        self.assertIn("whole number", self.refuse({"formations_cap": "130"}))

    def test_an_unknown_parameter_is_named_back(self) -> None:
        message = self.refuse({"formation_cap": 30})
        self.assertIn("formation_cap", message)
        self.assertIn("formations_cap", message)

    def test_a_recipe_that_raises_nothing_is_refused(self) -> None:
        self.assertIn("no word to write", self.refuse({}))
        self.assertIn("no word to write", self.refuse({"plays_cap": 100}))

    def test_check_cap_parameters_fills_in_the_shipped_defaults(self) -> None:
        values = code_patches.check_cap_parameters({"plays_cap": 400})
        self.assertEqual(values, {"formations_cap": 20, "sets_cap": 20,
                                  "plays_cap": 400, "plays_per_set_cap": 60})


class CatalogueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-code-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = code_patches.Madden09CodePatchLane(IDENTITY)
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)

    def target(self, key):
        return self.catalogue.target(key)

    def test_the_lane_answers_the_code_patch_protocol(self) -> None:
        self.assertIsInstance(self.lane, CodePatchLane)
        self.assertEqual(self.lane.page, "gameplay")
        self.assertEqual(self.lane.classification, "offline-writer-proved")
        self.assertFalse(self.lane.fixed_allocation,
                         "the default destination is a pnach, which is not the source's size")

    def test_the_classification_matches_the_registry_fragment_row(self) -> None:
        fragment = json.loads((ROOT / "mod_editor" / "games" / "madden09_ps2"
                               / "registry.fragment.json").read_text(encoding="utf-8"))
        row = next(r for r in fragment["capabilities"] if r["id"] == self.lane.capability_id)
        self.assertEqual(row["classification"], self.lane.classification)
        self.assertEqual(row["backend"]["operation"], "write")
        self.assertEqual(row["gui"]["mode"], "edit")
        self.assertEqual(row["runtime"]["status"], "not-tested",
                         "nothing has been booted, so runtime stays untested")

    def test_one_patch_is_translated_and_the_rest_are_proposals(self) -> None:
        rows = {row["patch_id"]: row for row in self.catalogue.document["patches"]}
        self.assertTrue(rows[code_patches.PLAYBOOK_CAPS_PATCH_ID]["mapped"])
        for patch_id, _title, _note in code_patches.PROPOSED_PATCHES:
            self.assertFalse(rows[patch_id]["mapped"], patch_id)
        self.assertEqual(self.catalogue.document["translations_available"], 1)

    def test_the_catalogue_reads_every_site_out_of_the_source_it_was_given(self) -> None:
        row = self.target(code_patches.PLAYBOOK_CAPS_PATCH_ID).raw
        self.assertTrue(row["sites_match"])
        self.assertEqual(len(row["sites"]), len(code_patches.CAP_SITES))
        for site, measured in zip(code_patches.CAP_SITES, row["sites"]):
            with self.subTest(site.table):
                self.assertEqual(measured["found"], measured["expected"])
                self.assertEqual(measured["found_cap"], site.shipped_cap)

    def test_the_synthetic_elf_holds_this_lane_s_own_original_words(self) -> None:
        elf, _boot = ps2_elf.read_boot_elf(self.source)
        segments = ps2_elf.parse_program_headers(elf, "synthetic")
        for site in code_patches.CAP_SITES:
            with self.subTest(site.table):
                self.assertEqual(ps2_elf.read_word(elf, segments, site.address), site.original)

    def test_every_proposed_patch_refuses_translation_by_name(self) -> None:
        for patch_id, _title, _note in code_patches.PROPOSED_PATCHES:
            with self.assertRaises(Refusal) as caught:
                self.lane.translation(patch_id, {})
            message = str(caught.exception)
            self.assertIn(patch_id, message)
            self.assertIn(containers.BOOT_FILE, message)
            self.assertIn("not mapped", message)
            self.assertIn(code_patches.PLAYBOOK_CAPS_PATCH_ID, message,
                          "the refusal names what the lane does translate")

    def test_an_unknown_patch_id_is_refused_with_the_choices(self) -> None:
        with self.assertRaises(Refusal) as caught:
            self.lane.translation("no-such-patch", {})
        self.assertIn("no-such-patch", str(caught.exception))
        self.assertIn("choose one of", str(caught.exception))

    def test_the_translated_target_draws_a_control_for_every_cap(self) -> None:
        fields = {item.key: item for item in self.target(code_patches.PLAYBOOK_CAPS_PATCH_ID).fields}
        for name in code_patches.CAP_PARAMETERS:
            self.assertEqual(fields[name].kind, "int")
            self.assertEqual(fields[name].minimum, code_patches._floor(name))
            self.assertEqual(fields[name].maximum, code_patches.MAX_CAP)
        self.assertTrue(fields["second_layer"].read_only)

    def test_check_edit_accepts_caps_and_refuses_the_ones_translation_refuses(self) -> None:
        target = self.target(code_patches.PLAYBOOK_CAPS_PATCH_ID)
        self.assertIsNone(self.lane.check_edit(target, {"parameters": CAPS}))
        self.assertIn("below the 100",
                      self.lane.check_edit(target, {"parameters": {"plays_cap": 99}}))
        self.assertIn("no word to write", self.lane.check_edit(target, {"parameters": {}}))

    def test_a_proposal_draws_no_switch_a_user_could_turn_on(self) -> None:
        target = self.target(code_patches.PROPOSED_PATCHES[0][0])
        for item in target.fields:
            self.assertTrue(item.read_only, item.key)

    def test_check_edit_refuses_an_unmapped_patch_and_accepts_hand_words(self) -> None:
        target = self.target(code_patches.PROPOSED_PATCHES[0][0])
        self.assertIn("not mapped", self.lane.check_edit(target, {"parameters": {}}))
        good = {"mips": [{"address": f"{code_patches.SYNTHETIC_BASE + 8:08X}",
                          "original": f"{code_patches.SYNTHETIC_WORDS[2]:08X}",
                          "replacement": "24020000"}]}
        self.assertIsNone(self.lane.check_edit(target, good))

    def test_check_edit_names_a_key_it_does_not_take(self) -> None:
        self.assertIn("colour", self.lane.check_edit(self.catalogue.targets[0], {"colour": "red"}))

    def test_check_edit_refuses_a_delivery_route_that_does_not_exist(self) -> None:
        problem = self.lane.check_edit(self.catalogue.targets[0], {"deliver": "memcard"})
        self.assertIn("memcard", problem)
        self.assertIn("pnach", problem)

    def test_check_edit_refuses_an_executable_that_is_not_the_one_translated(self) -> None:
        other = Path(tempfile.mkdtemp(prefix="madden09-other-"))
        self.addCleanup(shutil.rmtree, other, True)
        moved = list(code_patches.synthetic_elf_words())
        moved[(code_patches.CAP_SITES[0].address - code_patches.SYNTHETIC_BASE) // 4] ^= 0xFF
        elf = ps2_elf.build_synthetic_elf(moved, base_vaddr=code_patches.SYNTHETIC_BASE)
        import ps2_iso9660 as iso_lib

        image = iso_lib.build_synthetic_iso(
            files=[(b"SYSTEM.CNF;1", b"BOOT2 = cdrom0:\\SLUS_217.70;1\r\nVER = 1.00\r\n"),
                   (b"SLUS_217.70;1", elf)],
            sub_name=b"DATA", sub_files=[(b"GAMEDATA.DAT;1", bytes(2048))])
        path = other / "other.iso"
        path.write_bytes(image)
        catalogue = self.lane.build_catalogue(path)
        target = catalogue.target(code_patches.PLAYBOOK_CAPS_PATCH_ID)
        self.assertFalse(target.raw["sites_match"])
        problem = self.lane.check_edit(target, {"parameters": CAPS})
        self.assertIn("PBFM", problem)
        self.assertIn("not derived against the image you", problem)

    def test_the_catalogue_reports_the_elf_it_read(self) -> None:
        elf = self.catalogue.document["elf"]
        self.assertEqual(elf["serial"], containers.SERIAL)
        self.assertEqual(elf["boot_file"], containers.BOOT_FILE)
        self.assertEqual(elf["edition"], "unknown")
        self.assertFalse(elf["retail"], "a synthetic ELF must never pass as retail")

    def test_the_catalogue_states_what_the_patch_does_not_do(self) -> None:
        self.assertIn("packed exactly full", self.catalogue.document["second_layer"])
        self.assertIn("status 19", self.catalogue.document["second_layer"])


class PnachRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-code-pnach-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = code_patches.Madden09CodePatchLane(IDENTITY)
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)
        self.recipe = self.lane.compose_recipe(self.lane.conformance_edits(self.catalogue))

    def test_the_conformance_edit_drives_the_real_translation(self) -> None:
        self.assertEqual(self.recipe["patches"][0]["patch"], code_patches.PLAYBOOK_CAPS_PATCH_ID)
        self.assertNotIn("mips", self.recipe["patches"][0])

    def test_a_plan_checks_every_original_against_the_user_s_own_elf(self) -> None:
        plan = self.lane.plan(self.source, self.recipe, self.catalogue)
        self.assertEqual(plan.document["delivery"], "pnach")
        words = plan.document["patches"][0]["words"]
        self.assertEqual(len(words), len(code_patches.CAP_SITES))
        self.assertEqual({word["address"] for word in words},
                         {f"{site.address:08X}" for site in code_patches.CAP_SITES})

    def test_a_plan_refuses_words_derived_against_another_executable(self) -> None:
        wrong = {"schema": code_patches.RECIPE_SCHEMA, "patches": [{
            "patch": code_patches.PROPOSED_PATCHES[0][0],
            "mips": [{"address": f"{code_patches.SYNTHETIC_BASE + 8:08X}",
                      "original": "DEADBEEF", "replacement": "00000000"}],
        }]}
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, wrong, self.catalogue)
        self.assertIn("not derived against this executable", str(caught.exception))

    def test_a_plan_refuses_an_address_outside_the_elf(self) -> None:
        wrong = {"schema": code_patches.RECIPE_SCHEMA, "patches": [{
            "patch": code_patches.PROPOSED_PATCHES[0][0],
            "mips": [{"address": "0FFFFFF0", "original": "00000000", "replacement": "00000001"}],
        }]}
        with self.assertRaises(Refusal):
            self.lane.plan(self.source, wrong, self.catalogue)

    def test_two_edits_may_not_ask_for_two_different_routes(self) -> None:
        from mod_editor.games.contract import Edit

        edits = (Edit(code_patches.PLAYBOOK_CAPS_PATCH_ID,
                      {"parameters": CAPS, "deliver": "pnach"}),
                 Edit(code_patches.PROPOSED_PATCHES[0][0],
                      {"deliver": "disc",
                       "mips": [{"address": f"{code_patches.SYNTHETIC_BASE + 8:08X}",
                                 "original": f"{code_patches.SYNTHETIC_WORDS[2]:08X}",
                                 "replacement": "24020000"}]}))
        with self.assertRaises(Refusal) as caught:
            self.lane.compose_recipe(edits)
        self.assertIn("delivered one way", str(caught.exception))

    def test_a_recipe_naming_an_unknown_delivery_is_refused(self) -> None:
        recipe = dict(self.recipe)
        recipe["deliver"] = "memcard"
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, recipe, self.catalogue)
        self.assertIn("memcard", str(caught.exception))

    def test_build_writes_a_pnach_and_verify_passes_it(self) -> None:
        out = self.work / "madden09.pnach"
        receipt = self.lane.build(self.source, out, self.recipe, self.catalogue)
        self.assertEqual(receipt.document["delivery"], "pnach")
        self.assertEqual(len(receipt.artifacts), 1)
        text = out.read_text(encoding="utf-8")
        for site in code_patches.CAP_SITES:
            self.assertIn(f"patch=1,EE,{site.address:08X},word,"
                          f"{site.word_for(CAPS[site.parameter]):08X}", text)
        verdict = self.lane.verify(self.source, out, receipt)
        self.assertTrue(verdict.passed, verdict.summary)
        self.assertIn("verified against the boot ELF", verdict.summary)

    def test_verify_fails_a_tampered_pnach(self) -> None:
        out = self.work / "madden09.pnach"
        receipt = self.lane.build(self.source, out, self.recipe, self.catalogue)
        site = code_patches.CAP_SITES[0]
        tampered = self.work / "tampered.pnach"
        tampered.write_text(
            out.read_text(encoding="utf-8").replace(
                f"{site.word_for(CAPS[site.parameter]):08X}",
                f"{site.word_for(CAPS[site.parameter] + 1):08X}"),
            encoding="utf-8", newline="\n")
        self.assertFalse(self.lane.verify(self.source, tampered, receipt).passed)

    def test_verify_fails_when_the_pnach_declares_an_extra_address(self) -> None:
        out = self.work / "madden09.pnach"
        receipt = self.lane.build(self.source, out, self.recipe, self.catalogue)
        extra = self.work / "extra.pnach"
        extra.write_text(out.read_text(encoding="utf-8")
                         + f"patch=1,EE,{code_patches.SYNTHETIC_BASE:08X},word,00000000\n",
                         encoding="utf-8", newline="\n")
        verdict = self.lane.verify(self.source, extra, receipt)
        self.assertFalse(verdict.passed)
        self.assertIn("undeclared", verdict.summary)

    def test_verify_fails_when_the_pnach_names_another_crc(self) -> None:
        out = self.work / "madden09.pnach"
        receipt = self.lane.build(self.source, out, self.recipe, self.catalogue)
        wrong = self.work / "wrongcrc.pnach"
        wrong.write_text(out.read_text(encoding="utf-8").replace(receipt.document["crc"], "00000000"),
                         encoding="utf-8", newline="\n")
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


class DiscRouteTests(unittest.TestCase):
    """The optional on-disc delivery: same words, written into the executable."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-code-disc-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = code_patches.Madden09CodePatchLane(IDENTITY)
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)
        self.recipe = dict(self.lane.compose_recipe(self.lane.conformance_edits(self.catalogue)))
        self.recipe["deliver"] = "disc"

    def build(self, name="patched.iso"):
        out = self.work / name
        return out, self.lane.build(self.source, out, self.recipe, self.catalogue)

    def test_the_plan_declares_one_four_byte_range_per_word(self) -> None:
        plan = self.lane.plan(self.source, self.recipe, self.catalogue)
        self.assertEqual(plan.document["delivery"], "disc")
        self.assertEqual(len(plan.declared_ranges), len(code_patches.CAP_SITES))
        for item in plan.declared_ranges:
            self.assertEqual(item.length, 4)
        extent = plan.document["boot_extent"]
        self.assertTrue(extent["path"].upper().endswith(containers.BOOT_FILE))

    def test_the_words_land_in_the_executable_on_the_new_image(self) -> None:
        out, receipt = self.build()
        self.assertEqual(receipt.document["delivery"], "disc")
        self.assertEqual(receipt.artifacts, ())
        elf, _boot = ps2_elf.read_boot_elf(out)
        segments = ps2_elf.parse_program_headers(elf, "patched")
        for site in code_patches.CAP_SITES:
            with self.subTest(site.table):
                self.assertEqual(ps2_elf.read_word(elf, segments, site.address),
                                 site.word_for(CAPS[site.parameter]))

    def test_nothing_outside_the_declared_words_moved(self) -> None:
        out, receipt = self.build()
        before, after = self.source.read_bytes(), out.read_bytes()
        self.assertEqual(len(before), len(after), "the image keeps its exact length")
        allowed = {index for item in receipt.declared_ranges
                   for index in range(item.start, item.end)}
        changed = {index for index in range(len(before)) if before[index] != after[index]}
        self.assertTrue(changed, "the build must have changed something")
        self.assertTrue(changed <= allowed, sorted(changed - allowed)[:8])

    def test_the_source_image_is_never_touched(self) -> None:
        before = self.source.read_bytes()
        self.build()
        self.assertEqual(self.source.read_bytes(), before)

    def test_verify_passes_the_image_it_built(self) -> None:
        out, receipt = self.build()
        verdict = self.lane.verify(self.source, out, receipt)
        self.assertTrue(verdict.passed, verdict.summary)
        self.assertIn("every other byte", verdict.summary)
        self.assertEqual(verdict.document["words"], len(code_patches.CAP_SITES))

    def test_verify_fails_when_a_declared_word_is_not_what_the_receipt_names(self) -> None:
        out, receipt = self.build()
        image = bytearray(out.read_bytes())
        start = sorted(item.start for item in receipt.declared_ranges)[0]
        struct.pack_into("<I", image, start, 0x2C420001)
        out.write_bytes(bytes(image))
        verdict = self.lane.verify(self.source, out, receipt)
        self.assertFalse(verdict.passed)
        self.assertIn("not the", verdict.summary)

    def test_verify_fails_on_a_byte_changed_outside_every_declared_range(self) -> None:
        out, receipt = self.build()
        image = bytearray(out.read_bytes())
        declared = {index for item in receipt.declared_ranges for index in range(item.start, item.end)}
        elf_start = receipt.document["boot_extent"]["byte_offset"]
        stray = next(index for index in range(elf_start + 0x2000, elf_start + 0x3000)
                     if index not in declared)
        image[stray] ^= 0xFF
        out.write_bytes(bytes(image))
        verdict = self.lane.verify(self.source, out, receipt)
        self.assertFalse(verdict.passed)
        self.assertIn("outside the", verdict.summary)

    def test_build_refuses_an_existing_destination(self) -> None:
        out, _receipt = self.build()
        with self.assertRaises(Refusal):
            self.lane.build(self.source, out, self.recipe, self.catalogue)


class SelfTestTests(unittest.TestCase):
    def test_the_selftest_passes(self) -> None:
        self.assertEqual(code_patches.selftest(), 0)


if __name__ == "__main__":
    unittest.main()
