"""Speed separation (nfl2k5_speed_threshold, b780-cv5): exact bytes, replay, refusal, presets, settings, Build page, build
dispatcher and cave-manifest registration. No game boot, no emulator.

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (tests that need it skip when it is absent).
The slow Unicorn frame replays are in test_nfl2k5_speed_threshold_unicorn.py.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_cave_manifest as manifest
from mod_editor.core import nfl2k5_speed_threshold as patch
from mod_editor.core import nfl2k5_speed_threshold_code as assembly
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import repin_edit, retail_xbe

GOOD_STRENGTHS = (0, 1, 35, 50, 100)
BAD_STRENGTHS = (True, False, -1, 101, 50.0, "50", None)


class StaticTests(unittest.TestCase):
    def test_template_reproduction(self):
        from tests.mod_editor._gnu_elf32_as import gnu_elf32_as
        if not gnu_elf32_as():
            self.skipTest("GNU ELF32 assembler unavailable")
        from tools.nfl2k5_speed_threshold_assemble import TARGET, generate
        self.assertEqual(generate(), TARGET.read_text())
        self.assertLessEqual(len(assembly.CODE), patch.SETTING_OFFSET)

    def test_cave_layout_hook_and_return(self):
        va = 0x150D9E0
        code = patch.code_for(va, 35)
        self.assertEqual(len(code), patch.CODE_SIZE)
        self.assertEqual(code[patch.SETTING_OFFSET], 35)
        self.assertEqual(code[patch.SETTING_OFFSET + 1:], b"\xcc" * 3)
        # The entry saves the flags and registers, then reads its own setting byte.
        self.assertEqual(code[:2], b"\x9c\x60")
        self.assertEqual(code[2:5], b"\x0f\xb6\x1d")
        self.assertEqual(struct.unpack_from("<I", code, 5)[0], va + patch.SETTING_OFFSET)
        # The last instruction jumps back to the stolen epilogue's successor, the instruction after the 7 bytes.
        tail = patch.HOOK_VA + len(patch.RETAIL_HOOK)
        native_tail = [offset for offset, _kind, symbol, _addend in assembly.RELOCATIONS if symbol == "native_tail"]
        self.assertEqual(len(native_tail), 1)
        offset = native_tail[0]
        self.assertEqual(code[offset - 1], 0xE9)
        self.assertEqual(va + offset + 4 + struct.unpack_from("<i", code, offset)[0], tail)
        # The hook is one near jump to the cave plus two NOPs over the displaced fld [esp] / add esp, 20.
        (label, hook_va, before, after), = patch.sites(va)
        self.assertEqual((label, hook_va, before), ("vertical_man_speed", 0x2381B1, bytes.fromhex("d944240083c414")))
        self.assertEqual(len(after), len(before))
        self.assertEqual(after[0], 0xE9)
        self.assertEqual(hook_va + 5 + struct.unpack_from("<i", after, 1)[0], va)
        self.assertEqual(after[5:], b"\x90\x90")

    def test_request_and_late_owner_registration(self):
        self.assertEqual(patch.REQUESTS, (("nfl2k5_speed_threshold", "code", 1024, 16),))
        self.assertEqual(space.LATE_OWNERS.count(patch.OWNER), 1)
        # b780-int: several wave owners append after the b779 tail; each must come after every owner v0.8 carries
        self.assertEqual(space.LATE_OWNERS.count(patch.OWNER), 1)
        self.assertGreater(space.LATE_OWNERS.index(patch.OWNER), space.LATE_OWNERS.index("nfl2k5_sim_realism_state"))
        self.assertIn(("nfl2k5_speed_threshold", "Speed separation"),
                      [(owner, label) for owner, label, _wanted in mod_build._LATE_OWNER_OPTIONS])
        wanted = {owner: wanted for owner, _label, wanted in mod_build._LATE_OWNER_OPTIONS}[patch.OWNER]
        self.assertFalse(wanted(mod_build.BuildPlan("", "")))
        self.assertTrue(wanted(mod_build.BuildPlan("", "", speed_threshold=1)))
        self.assertIs(tt.speed_threshold_patch, patch)  # imported so the cave manifest recorder observes it
        self.assertIn("speed_threshold", settings.FEATURE_KEYS)
        self.assertIn("speed_threshold", mod_build.availability())

    def test_defaults_presets_and_portable_settings(self):
        self.assertEqual(mod_build.BuildPlan("", "").speed_threshold, 0)
        self.assertEqual(patch.SOFTDRINK, 35)
        self.assertEqual({name: preset["speed_threshold"] for name, preset in mod_build.PRESETS.items()},
                         {"softdrink_basic": 0, "softdrink_advanced": 0, "softdrink_experimental": 0})  # b780-int: off until gated
        for value in GOOD_STRENGTHS:
            saved = settings.build_settings({"speed_threshold": value})
            self.assertEqual(settings.to_plan(saved, "", "").speed_threshold, value)
            self.assertEqual(settings.from_plan(mod_build.BuildPlan("", "", speed_threshold=value))["speed_threshold"], value)
        for value in BAD_STRENGTHS:
            with self.subTest(value=value), self.assertRaises(ValueError):
                settings.build_settings({"speed_threshold": value})
        # an older project file that never heard of the key restores to off
        self.assertEqual(settings.to_plan(settings.build_settings({}), "", "").speed_threshold, 0)

    def test_owner_validation_and_foreign_inputs_refuse_before_allocation(self):
        for value in GOOD_STRENGTHS:
            self.assertEqual(patch.validate(value), value)
        for value in BAD_STRENGTHS:
            with self.subTest(value=value), self.assertRaises(ValueError):
                patch.validate(value)
        for payload in (None, b"", b"XBEH", bytes(4096)):
            self.assertEqual(patch.status(payload), "foreign")
            with mock.patch.object(space, "apply", side_effect=AssertionError("premature write")):
                with self.assertRaises(ValueError):
                    patch.apply(payload)

    def test_user_text_is_plain(self):
        for text in (patch.BUILD_CAPTION, patch.HELP_TEXT):
            self.assertNotIn("—", text)  # no em dashes in public text
            self.assertNotIn("–", text)
        self.assertIn("EXPERIMENTAL / UNWITNESSED", patch.HELP_TEXT)
        self.assertIn("35", patch.HELP_TEXT)
        self.assertIn("0 keeps the stock feel", patch.HELP_TEXT)

    def test_manifest_builder_observes_the_owner_on_the_late_owner_probe(self):
        text = inspect.getsource(manifest.build_manifest)
        for needle in ("nfl2k5_speed_threshold as speed_threshold",
                       "speed_threshold.REQUESTS",
                       "speed_threshold.apply(cpu_ai_probe, value=speed_threshold.SOFTDRINK)",
                       '"nfl2k5_speed_threshold"',
                       "speed_threshold=0"):  # the dormant-owner probe build must leave the preset's strength off
            self.assertIn(needle, text, needle)


class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()

    def test_install_every_strength_idempotently_and_refuse_a_different_one(self):
        for value in (0, 35, 100):
            with self.subTest(value=value):
                result, receipt = patch.apply(self.retail, value=value)
                self.assertEqual(patch.status(result), "applied")
                self.assertEqual(patch.verify(result, value=value)["value"], value)
                self.assertEqual(space.status(result), "applied")
                again, replay = patch.apply(result)
                self.assertEqual(again, result)
                self.assertEqual(patch.apply(result, value=value)[1]["changed_bytes"], 0)
                self.assertEqual(replay["status"], "already_applied")
                self.assertTrue(all(row in space.layout(result)["allocations"] for row in space.layout(self.retail)["allocations"]))
                with self.assertRaisesRegex(ValueError, "rebuild"):
                    patch.apply(result, value=100 if value == 0 else 0)
                self.assertEqual(receipt["file_growth"], len(result) - len(self.retail))

    def test_only_the_hook_changes_in_retail_sections_and_the_cave_holds_the_code(self):
        result, _ = patch.apply(self.retail, value=35)
        a, b = XbeImage(self.retail), XbeImage(result)
        changed = []
        for section in a.sections:
            if section.raw_size:
                x, y = a.read(section.start, section.raw_size), b.read(section.start, section.raw_size)
                changed += [section.start + i for i in range(len(x)) if x[i] != y[i]]
        # retail d9 44 24 00 83 c4 14 (fld [esp]; add esp, 20) becomes e9 rel32 90 90: at most those 7 bytes change
        self.assertTrue(set(changed) <= set(range(patch.HOOK_VA, patch.HOOK_VA + 7)))
        self.assertIn(patch.HOOK_VA, changed)
        row = patch.allocation(result)
        self.assertEqual(b.read(row["va"], patch.CODE_SIZE), patch.code_for(row["va"], 35))
        for _label, va, _before, after in patch.sites(row["va"]):
            self.assertEqual(b.read(va, len(after)), after)

    @staticmethod
    def flipped(payload, address):
        """The same image with the byte at ``address`` inverted (never a no-op) and the section digests re-sealed."""
        return repin_edit(payload, address, bytes([XbeImage(payload).read(address, 1)[0] ^ 0xFF]))

    def test_resealed_foreign_hook_native_constant_code_and_setting_refuse(self):
        base, _ = patch.apply(self.retail, value=50)
        # the hook, a mapper instruction and every constant the mapper reads (the guard list covers them all)
        guarded = (patch.HOOK_VA, 0x238045, 0x513E2C, *(start for start, _size, _digest in patch.GUARDS if start != 0x238020))
        for address in guarded:
            bad = self.flipped(base, address)
            self.assertEqual(patch.status(bad), "foreign", hex(address))
            with self.assertRaises(ValueError):
                patch.apply(bad)
        for address in (0x238045, 0x513E2C, *(start for start, _size, _digest in patch.GUARDS if start != 0x238020)):
            bad = self.flipped(self.retail, address)  # a retail image with a changed mapper byte or constant
            self.assertEqual(patch.status(bad), "foreign", hex(address))
            with self.assertRaises(ValueError):
                patch.apply(bad)
        row = patch.allocation(base)
        for offset, value in ((0, 0), (patch.SETTING_OFFSET, 101), (patch.SETTING_OFFSET + 1, 0)):
            code = bytearray(patch.code_for(row["va"], 50))
            code[offset] = value
            allocated, _ = space.apply(self.retail, patch.REQUESTS, scaleout=True)
            bad, _ = space.install_code(allocated, patch.OWNER, bytes(code))
            self.assertEqual(patch.status(bad), "foreign")
            with self.assertRaises(ValueError):
                patch.apply(bad)

    def test_composes_with_the_man_coverage_and_speed_owners(self):
        """The owners that act near this one (turn integrator, momentum, QB spy, deep zone, abilities) keep their
        statuses and replays, whatever order they go on in, and the cave does not overlap any of them."""
        from tests import nfl2k5_allocator_stack as stack
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import prerequisites
        # the speed owner is appended to the installed image, the way the build does it (a late owner)
        seed, _ = space.apply(prerequisites(self.retail), stack.REQUESTS, scaleout=True)
        near = (stack.coverage_trail, stack.momentum, stack.qb_spy, stack.deep_zone, stack.abilities, stack.zone_drop,
                stack.coverage, stack.scramble)
        owners = [(m, k) for m, k in stack.owner_calls() if m in near]
        self.assertEqual(len(owners), len(near))
        digests = []
        for order in (owners, list(reversed(owners))):
            result = seed
            for module, kwargs in order:
                result, _ = module.apply(result, **kwargs)
            result, _ = patch.apply(result, value=35)
            for module, kwargs in owners:
                self.assertEqual(module.status(result), "applied", module.OWNER)
            self.assertEqual(patch.status(result), "applied")
            self.assertEqual(patch.verify(result, value=35)["value"], 35)
            self.assertEqual(patch.apply(result)[0], result)
            digests.append(result)
        self.assertEqual(digests[0], digests[1], "owner order changed the bytes")

    def test_cave_manifest_recorder_accounts_for_every_write(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        # like the manifest builder's late-owner probe copy: the request is in the allocation, the apply installs code
        allocated, allocation_receipt = space.apply(self.retail, tuple(space.dormant_union()) + patch.REQUESTS, scaleout=True)
        record = Recorder(self.retail)
        record.observe(space, "apply", self.retail, allocated, allocation_receipt)
        result, receipt = patch.apply(allocated, value=patch.SOFTDRINK)
        record.observe(patch, "apply", allocated, result, receipt)
        document = record.finish(result)
        self.assertIsInstance(document, list)
        self.assertTrue(any(row["owner"] == patch.OWNER for row in record.spans))
        hook_end = patch.HOOK_VA + len(patch.RETAIL_HOOK)
        self.assertTrue(any(int(row["start"], 0) <= patch.HOOK_VA and hook_end <= int(row["end"], 0)
                            and row["owner"] == patch.OWNER for row in record.spans))

    def test_reservations_name_the_cave_and_the_hook(self):
        result, _ = patch.apply(self.retail, value=35)
        rows = patch.reservations(result)
        self.assertTrue(all(row["owner"] == patch.OWNER for row in rows))
        cave = patch.allocation(result)
        self.assertTrue(any(row["start"] == hex(cave["va"]) and row["size"] == patch.CODE_SIZE for row in rows))
        self.assertTrue(any(row["start"] == hex(patch.HOOK_VA) and row["end"] == hex(patch.HOOK_VA + 7) and row["size"] == 7
                            for row in rows))


class BuildDispatcherTests(unittest.TestCase):
    """The real build dispatcher on a bounded XDVDFS image (the unrelated automatic uniform and PLAY-resource passes have
    no assets there and are mocked; the allocator, the writer and the image read-back are real)."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()

    def build(self, source, target, **kwargs):
        with mock.patch("mod_editor.core.nfl2k5_unc_bowl_uniforms.apply_to_image", return_value={"synthetic": True}), \
                mock.patch.object(mod_build, "_check_playbook_scoring", return_value={"synthetic": True}):
            return mod_build.build(mod_build.BuildPlan(str(source), str(target), throw=False, **kwargs))

    def test_zero_is_byte_identical_positive_installs_and_a_built_disc_is_not_re_strengthened(self):
        from tests.mod_editor.test_nfl2k5_xbe_space import image_with_xbe
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.iso"
            source.write_bytes(image_with_xbe(self.retail))
            zero = Path(directory) / "zero.iso"
            self.build(source, zero, speed_threshold=0)
            self.assertEqual(mod_build._xbe_bytes(zero), self.retail)
            thirty_five = Path(directory) / "thirty-five.iso"
            result = self.build(source, thirty_five, speed_threshold=35)
            output = mod_build._xbe_bytes(thirty_five)
            self.assertEqual(patch.verify(output, value=35)["value"], 35)
            self.assertEqual(result["result"]["speed_threshold"], "applied")
            self.assertEqual(result["result"]["speed_threshold_value"], 35)
            self.assertEqual([step["step"] for step in result["steps"]][-1], "speed_threshold")
            self.assertEqual(mod_build._xbe_bytes(source), self.retail)
            # inspect reports the installed strength for the Build page
            state = mod_build.inspect(thirty_five)
            self.assertEqual(state["speed_threshold"], "applied")
            self.assertEqual(state["speed_threshold_settings"]["value"], 35)
            self.assertEqual(mod_build.inspect(source)["speed_threshold"], "retail")
            # the same strength again is a no-op replay; another strength is refused before anything is written
            again = Path(directory) / "again.iso"
            self.build(thirty_five, again, speed_threshold=35)
            self.assertEqual(patch.verify(mod_build._xbe_bytes(again), value=35)["value"], 35)
            refused = Path(directory) / "refused.iso"
            with self.assertRaisesRegex(ValueError, "already has Speed separation set to 35"):
                self.build(thirty_five, refused, speed_threshold=50)
            self.assertFalse(refused.exists())
            with self.assertRaisesRegex(ValueError, "whole number from 0 to 100"):
                self.build(source, Path(directory) / "bad.iso", speed_threshold=101)

    def test_a_foreign_speed_mapper_refuses_before_any_write(self):
        from tests.mod_editor.test_nfl2k5_xbe_space import image_with_xbe
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "foreign.iso"
            source.write_bytes(image_with_xbe(repin_edit(self.retail, 0x238045, b"\x00")))
            target = Path(directory) / "target.iso"
            with self.assertRaisesRegex(ValueError, "speed code in this source is not retail"):
                self.build(source, target, speed_threshold=35)
            self.assertFalse(target.exists())


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest("PyQt5 required for the offscreen Build page")
        cls.app = QApplication.instance() or QApplication([])

    def panel(self):
        from mod_editor.gui.build_panel_qt import BuildPanel
        panel = BuildPanel(available={})
        self.addCleanup(panel.deleteLater)
        return panel

    def test_default_off_and_disc_state_gates(self):
        panel = self.panel()
        spin = panel.speed_threshold_spin
        self.assertEqual(panel.plan().speed_threshold, 0)
        self.assertFalse(spin.isEnabled())
        panel.apply_state({"path": "default.xbe", "container": "xbe", "speed_threshold": "retail"})
        self.assertFalse(spin.isEnabled())
        self.assertIn("Full disc required", spin.badge_label.text())
        panel.apply_state({"path": "default.iso", "container": "xiso", "speed_threshold": "retail"})
        self.assertTrue(spin.isEnabled())
        spin.setValue(75)
        self.assertEqual(panel.plan().speed_threshold, 75)
        panel.apply_state({"path": "default.iso", "container": "xiso", "speed_threshold": "foreign"})
        self.assertFalse(spin.isEnabled())
        self.assertEqual(panel.plan().speed_threshold, 0)
        self.assertIn("Unrecognized", spin.badge_label.text())
        panel.apply_state({"path": "default.iso", "container": "xiso", "speed_threshold": "applied",
                           "speed_threshold_settings": {"status": "applied", "value": 25}})
        self.assertEqual(spin.value(), 25)
        self.assertFalse(spin.isEnabled())
        self.assertEqual(panel.plan().speed_threshold, 25)  # the installed strength, locked
        self.assertIn("strength 25", spin.badge_label.text())

    def test_presets_set_the_strength_where_the_disc_can_take_it(self):
        panel = self.panel()
        panel.apply_state({"path": "default.iso", "container": "xiso", "speed_threshold": "retail"})
        from mod_editor.core import mod_build
        # b780-int: every shipped preset keeps 0 until the gate passes; a preset that sets the strength (as the
        # Experimental one did on cv5's branch) still sets it on a disc and is skipped on a bare executable
        with mock.patch.dict(mod_build.PRESETS["softdrink_experimental"], {"speed_threshold": patch.SOFTDRINK}):
            for name, expected in (("softdrink_experimental", 35), ("softdrink_advanced", 0), ("softdrink_basic", 0)):
                result = panel.apply_preset(name)
                self.assertEqual(panel.speed_threshold_spin.value(), expected, name)
                self.assertEqual(panel.plan().speed_threshold, expected, name)
                self.assertEqual("speed_threshold" in result["applied"], bool(expected), name)
            panel.apply_state({"path": "default.xbe", "container": "xbe", "speed_threshold": "retail"})
            result = panel.apply_preset("softdrink_experimental")
            self.assertIn("speed_threshold", result["skipped"])
            self.assertEqual(panel.plan().speed_threshold, 0)
        panel.apply_state({"path": "default.iso", "container": "xiso", "speed_threshold": "retail"})
        panel.apply_preset("softdrink_experimental")
        self.assertEqual(panel.plan().speed_threshold, 0)
        self.assertEqual(panel._short_label("speed_threshold"), "Speed separation")

    def test_project_round_trip_and_a_new_disc_starts_clean(self):
        from mod_editor.gui.gameplay_project_ui import capture, restore
        panel = self.panel()
        panel.apply_state({"path": "default.iso", "container": "xiso", "speed_threshold": "retail"})
        panel.speed_threshold_spin.setValue(60)
        state = capture(panel)
        self.assertEqual(state["speed_threshold"], 60)
        panel.speed_threshold_spin.setValue(0)
        restore(panel, state)
        self.assertEqual(panel.plan().speed_threshold, 60)
        panel.apply_state({"path": "other.iso", "container": "xiso", "speed_threshold": "retail"})
        self.assertEqual(panel.plan().speed_threshold, 0)
        # an older project that never saved the key restores to off
        legacy = dict(state)
        del legacy["speed_threshold"]
        restore(panel, legacy)
        self.assertEqual(panel.plan().speed_threshold, 0)


if __name__ == "__main__":
    unittest.main()
