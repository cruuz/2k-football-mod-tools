"""Integrated allocator, selection and UI contracts. No runtime gameplay claim."""
from pathlib import Path
import os
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import mod_build as build, nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_music_storage as music_storage
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_allocator_stack import REQUESTS, compose

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
OPTIONS = dict(xbe_space=True, kickoff_relocated=True, scorebug_runtime=True, momentum=100,
               momentum_contact=True, defensive_try=True, zone_drop_cap=True,
               music_policy="jukebox_menus", music_unlock=True)


class SelectionTests(unittest.TestCase):
    def test_presets_clear_every_new_opt_in_and_recipe_keeps_integer_level(self):
        for name in build.PRESETS:
            plan = build.apply_preset(build.BuildPlan("source", "target", momentum=100,
                momentum_contact=True, defensive_try=True, zone_drop_cap=True), name)
            self.assertEqual((plan.momentum, plan.momentum_contact, plan.defensive_try, plan.zone_drop_cap),
                             (0, False, False, False))
            self.assertIs(type(plan.to_recipe()["momentum"]), int)
        for key, value in (("momentum", 25), ("defensive_try", True), ("zone_drop_cap", True)):
            self.assertTrue(build.BuildPlan("s", "t", **{key: value}).wants_xbe_patch())
            self.assertTrue(build.availability()[key])

    def test_invalid_options_refuse_before_reading_foreign_bytes(self):
        for options in (dict(momentum=True), dict(momentum=-1), dict(momentum=101),
                        dict(momentum_contact=True), dict(defensive_try=1), dict(zone_drop_cap="yes")):
            with self.subTest(options=options), self.assertRaises(ValueError):
                tt._apply_all(b"not a game", None, False, **options)

    def test_build_and_gameplay_level_controls_and_preset_reset(self):
        from PyQt5.QtWidgets import QApplication
        from mod_editor.gui.build_panel_qt import BuildPanel
        from mod_editor.gui.gameplay_patches_panel_qt import GameplayPatchesPanel, PATCHES
        self.app = app = QApplication.instance() or QApplication([])
        for cls in (BuildPanel, GameplayPatchesPanel):
            panel = cls()
            self.addCleanup(panel.close)
            state = {key: "retail" for key, _label, _help in PATCHES}
            state.update(path="/tmp/source.iso", container="xiso", status="retail")
            panel.apply_state(state)
            panel.momentum_level.setCurrentIndex(3)
            boxes = panel._boxes() if isinstance(panel, BuildPanel) else panel.checks
            boxes["momentum_contact"].setChecked(True)
            self.assertEqual((panel.plan().momentum, panel.plan().momentum_contact), (100, True))
            boxes["momentum"].setChecked(False)
            self.assertEqual((panel.plan().momentum, panel.plan().momentum_contact), (0, False))
            boxes["momentum"].setChecked(True)
            self.assertEqual(panel.plan().momentum, 100)
            panel.momentum_level.setCurrentIndex(0)
            self.assertEqual(panel.plan().momentum, 0)
            self.assertFalse(boxes["accel_ramp"].isChecked())
            if isinstance(panel, BuildPanel):
                for name in build.PRESETS:
                    panel.apply_preset(name)
                    self.assertEqual(panel.plan().momentum, 0)
                    self.assertFalse(panel.plan().momentum_contact)
                    self.assertFalse(panel.plan().defensive_try)
                    self.assertFalse(panel.plan().zone_drop_cap)
                for key in ("momentum", "momentum_contact", "defensive_try", "zone_drop_cap"):
                    self.assertLessEqual(len(boxes[key].text()), 60)
        app.processEvents()


@unittest.skipUnless(RETAIL.is_file(), "private USA executable absent")
class CompleteOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        cls.full, _ = compose(cls.retail)

    def test_capacity_permissions_metadata_and_stable_existing_addresses(self):
        layout = space.layout(self.full)
        regions = layout["regions"]
        self.assertEqual([r["size"] for r in regions if r["kind"] == "code"], [4096, 4096])
        self.assertEqual(sum(a["size"] for a in layout["allocations"] if a["kind"] == "code"), 6501)
        self.assertEqual(sum(a["size"] for a in layout["allocations"] if a["kind"] == "data"), 3242)
        image = XbeImage(self.full)
        for a in layout["allocations"]:
            section = image.section(a["va"], a["size"])
            self.assertNotEqual(section.name, ".text")
            self.assertEqual(section.writable, a["kind"] == "data")
            self.assertEqual(section.executable, a["kind"] == "code")
            if a["kind"] == "data":
                self.assertEqual(image.read(a["va"], a["size"]), bytes(a["size"]))
        self.assertEqual(image.section(music_storage.VA).raw, music_storage.RAW)
        self.assertEqual(self.full[space.LIB_COPY:space.LIB_COPY + space.LIB_END-space.LIB_START],
                         self.retail[space.LIB_START:space.LIB_END])
        for index, original in enumerate(XbeImage(self.retail).sections):
            self.assertEqual(image.sections[index].header, original.header)
            self.assertEqual(image.sections[index].start, original.start)
            self.assertEqual(image.sections[index].raw, original.raw)
        legacy_requests = tt.kickoff_relocated_patch.REQUESTS + tt.scorebug_runtime_patch.REQUESTS
        legacy = space.apply(self.retail, legacy_requests)[0]
        self.assertEqual(len(legacy), space.FILE_SIZE)
        self.assertEqual([a["va"] for a in space.layout(legacy)["allocations"]],
                         [space.CODE_VA, space.CODE_VA+704, space.DATA_VA,
                          space.CODE_VA+2656, space.DATA_VA+16])
        full_sites = {(a["owner"], a["kind"]): a for a in layout["allocations"]}
        for a in space.layout(legacy)["allocations"]:
            self.assertEqual(a, full_sites[a["owner"], a["kind"]])
        self.assertEqual(compose(self.retail, reverse=True)[0], self.full)

    def test_extension_corruption_and_reconfiguration_fail_closed(self):
        for offset in (space.LIB_COPY, 0x164, space.CODE2_NAME, space.CODE2_REFS,
                       space.META_START+112, space.DIRECTORY+12, space.CODE2_RAW,
                       music_storage.RAW, space.DATA_RAW):
            bad = bytearray(self.full); bad[offset] ^= 1
            with self.subTest(offset=hex(offset)):
                self.assertEqual(space.status(bad), "foreign")
                with self.assertRaises(ValueError):
                    space.apply(bad, REQUESTS)
        with self.assertRaisesRegex(ValueError, "differ"):
            space.apply(self.full, tt.momentum_patch.REQUESTS)
        with self.assertRaisesRegex(ValueError, "capacity exceeded"):
            space.apply(self.retail, REQUESTS + (("extra", "code", 4096, 16),))

    def test_dispatcher_and_raw_writer_status_roundtrip(self):
        patched, receipt = tt._apply_all(self.retail, None, False, accel_ramp=True, **OPTIONS)
        self.assertTrue(receipt["legacy_accel_ramp_disabled_by_momentum_profile"])
        self.assertEqual(tt.accel_ramp_patch.status(patched), "retail")
        self.assertEqual(tt._apply_all(patched, None, False, **OPTIONS)[0], patched)
        with self.assertRaisesRegex(ValueError, "different Momentum"):
            tt._apply_all(patched, None, False, **{**OPTIONS, "momentum": 50})
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/"source.xbe", Path(folder)/"target.xbe"
            source.write_bytes(self.retail)
            report = tt.write_xbe_copy(source, target, **OPTIONS)
            read = tt.read_xbe(target)
            for key in ("momentum", "momentum_contact", "defensive_try", "zone_drop_cap"):
                self.assertEqual(report[key], "applied")
                self.assertEqual(read[key], "applied")
            self.assertEqual(read["momentum_settings"]["momentum"], 100)
            self.assertEqual(source.read_bytes(), self.retail)

    def test_image_writer_and_reader_roundtrip_with_all_new_owners(self):
        from tests.mod_editor.test_nfl2k5_xbe_space import image_with_xbe
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/"source.iso", Path(folder)/"target.iso"
            original = image_with_xbe(self.retail)
            source.write_bytes(original)
            report = tt.write_image_copy(source, target, **{**OPTIONS, "scorebug_runtime": False})
            read = tt.read_image(target)
            for key in ("momentum", "momentum_contact", "defensive_try", "zone_drop_cap"):
                self.assertEqual(report[key], "applied")
                self.assertEqual(read[key], "applied")
            self.assertEqual(read["momentum_settings"]["momentum"], 100)
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
