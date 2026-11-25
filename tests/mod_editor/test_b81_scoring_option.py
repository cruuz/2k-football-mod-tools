"""Beta 81 scoring slice through the real owners: retail pins, the kicking step and the simulator option.

The simulated kicking sites ride with ``sim_qb_injuries`` (Realistic and Custom install them, Retail restores the
original bytes); the CPU aim repair rides with the kicking fixes.  Executables come from the private fixtures.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from mod_editor.core import nfl2k5_cpu_kick_aim as aim
from mod_editor.core import nfl2k5_sim_scoring as scoring
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import retail_bytes


class RetailPins(unittest.TestCase):
    def test_the_pinned_original_bytes_are_the_retail_bytes(self):
        retail = retail_bytes()
        image = XbeImage(retail)
        self.assertEqual(image.read(aim.SITE_VA, aim.SITE_SIZE), aim.RETAIL_SITE)
        for name, va, before, _ in scoring.edits():
            with self.subTest(site=name):
                self.assertEqual(image.read(va, len(before)), before)
        self.assertEqual(aim.status(retail), "retail")
        self.assertEqual(scoring.status(retail), "retail")
        import struct
        for value, va in scoring.STOP_AT.items():
            self.assertEqual(struct.unpack("<f", image.read(va, 4))[0], value)
        self.assertEqual(image.read(scoring.BREAKAWAY_VA, scoring.BREAKAWAY_SIZE), scoring.RETAIL_BREAKAWAY)

    def test_cpu_aim_owner_round_trip_on_retail(self):
        retail = retail_bytes()
        patched, receipt = aim.apply(retail)
        self.assertEqual(aim.status(patched), "applied")
        self.assertEqual(len(patched), len(retail))
        self.assertEqual(XbeImage(patched).read(aim.SITE_VA, aim.SITE_SIZE), aim.site_bytes())
        self.assertLessEqual(receipt["changed_bytes"], aim.SITE_SIZE + 20)        # the site and its section digest
        self.assertEqual(aim.apply(patched)[0], patched)
        restored, _ = aim.restore(patched)
        self.assertEqual(restored, retail)

    def test_the_kicking_fixes_bring_the_cpu_aim_repair_and_other_builds_do_not(self):
        retail = retail_bytes()
        from mod_editor.core import nfl2k5_throw_tuning as tt
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "retail.xbe"
            source.write_bytes(retail)
            for flags, expected in (({"kick_rules": True}, "applied"), ({"kick_power": True}, "applied"),
                                    ({"returner_fix": True}, "retail")):
                with self.subTest(flags=flags):
                    target = Path(folder) / ("out-" + "-".join(flags) + ".xbe")
                    tt.write_xbe_copy(source, target, **flags)
                    built = target.read_bytes()
                    self.assertEqual(aim.status(built), expected)
                    self.assertEqual(tt.read_xbe(target)["cpu_kick_aim"], expected)
                    if expected == "applied":
                        # A second pass over the finished copy finds every kicking byte already right.
                        with self.assertRaisesRegex(tt.ThrowTuningError, "already match"):
                            tt.write_xbe_copy(target, Path(folder) / "again.xbe", **flags)


class SimulatorOption(unittest.TestCase):
    """The reviewed standard disc carries Simulated season realism and K128; the QB option is installed on it."""

    def standard(self):
        disc = os.environ.get("NFL2K5_B81_REVIEWED_TEST_DISC")
        if not disc or not Path(disc).is_file():
            self.skipTest("the private reviewed standard test disc is absent")
        from mod_editor.core import mod_build
        payload = mod_build._xbe_bytes(Path(disc))
        if hashlib.sha256(payload).hexdigest() != "98dd732945fb665a8d7fe771650d61c1098015cda4917ac83037059db477008e":
            self.skipTest("the reviewed standard test disc differs from the pinned executable")
        return payload

    def test_realistic_and_custom_install_the_kicking_sites_and_retail_restores_every_byte(self):
        from mod_editor.core import nfl2k5_sim_qb_injuries as qb
        source = self.standard()
        self.assertEqual(scoring.status(source), "retail")
        realistic, receipt = qb.apply(source, "realistic")
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(scoring.status(realistic), "applied")
        image = XbeImage(realistic)
        for name, va, _, enabled in scoring.edits():
            self.assertEqual(image.read(va, len(enabled)), enabled, name)
        custom, _ = qb.apply(realistic, "custom", custom_rate=0.0)
        self.assertEqual(scoring.status(custom), "applied")
        for start in (realistic, custom):
            retail, _ = qb.apply(start, "retail")
            self.assertEqual(scoring.status(retail), "retail")
            self.assertEqual(qb.apply(retail, "realistic")[0], realistic)
            # Retail equals the source plus the option's empty reservation, as before the scoring slice.
            self.assertEqual(qb.read_settings(retail)["status"], "retail")
        self.assertEqual(qb.apply(qb.apply(realistic, "retail")[0], "retail")[0], qb.apply(realistic, "retail")[0])

    def test_an_option_installed_before_the_scoring_slice_upgrades_in_place(self):
        from mod_editor.core import nfl2k5_sim_qb_injuries as qb
        source = self.standard()
        current, _ = qb.apply(source, "realistic")
        # Rebuild what the previous version wrote: every edit except the scoring sites.
        bank = qb._bank_allocation(current)
        setting = qb._Setting("realistic", qb.REALISTIC_RATE)
        physical = qb.physical_view(current)
        previous = qb._transform(physical, qb._edits(physical, bank, setting, kicking=False), restoring=False)
        self.assertEqual(scoring.status(previous), "retail")
        self.assertEqual(qb.read_settings(previous), qb.read_settings(current))
        upgraded, receipt = qb.apply(previous, "realistic")
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(upgraded, current)
        self.assertEqual(qb.apply(previous, "retail")[0], qb.apply(current, "retail")[0])

    def test_foreign_kicking_bytes_are_refused(self):
        from mod_editor.core import nfl2k5_sim_qb_injuries as qb
        source = self.standard()
        current, _ = qb.apply(source, "realistic")
        data = bytearray(current)
        at = XbeImage(current).offset(scoring.RAMP_VA, 1)
        data[at] ^= 0xFF
        self.assertEqual(scoring.status(bytes(data)), "foreign")
        self.assertEqual(qb.read_settings(bytes(data))["status"], "foreign")
        with self.assertRaises(ValueError):
            qb.apply(bytes(data), "retail")
        # Kicking bytes without the option (or beside its empty reservation after Retail) are foreign too.
        retail, _ = qb.apply(current, "retail")
        for image in (source, retail):
            stray = bytearray(image)
            for _, va, _, enabled in scoring.edits():
                at = XbeImage(image).offset(va, len(enabled))
                stray[at:at + len(enabled)] = enabled
            self.assertEqual(scoring.status(bytes(stray)), "applied")
            self.assertEqual(qb.read_settings(bytes(stray))["status"], "foreign")
            with self.assertRaises(ValueError):
                qb.apply(bytes(stray), "realistic")


if __name__ == "__main__":
    unittest.main()


class InPlaceRoutes(unittest.TestCase):
    """update-v09 and edit-sim-qb give a built disc the same kicking bytes as a full build (review F6)."""

    def test_the_single_option_edit_installs_the_cpu_aim_repair(self):
        disc = os.environ.get("NFL2K5_B81_REVIEWED_TEST_DISC")
        if not disc or not Path(disc).is_file():
            self.skipTest("the private reviewed standard test disc is absent")
        from mod_editor.core import mod_build, nfl2k5_kick_rules as kick_rules, nfl2k5_sim_qb_injuries as qb
        from mod_editor.core import nfl2k5_pass_protection as pressure
        source = mod_build._xbe_bytes(Path(disc))
        self.assertEqual(pressure.status(source), "legacy")
        self.assertEqual((kick_rules.status(source), aim.status(source)), ("applied", "retail"))
        repaired, receipt = mod_build._cpu_kick_aim_with_kicking(source)
        self.assertEqual(repaired, aim.apply(source)[0])
        self.assertEqual(mod_build._cpu_kick_aim_with_kicking(repaired)[0], repaired)
        self.assertEqual(mod_build._cpu_kick_aim_with_kicking(retail_bytes()), (retail_bytes(), None))
        with tempfile.TemporaryDirectory() as folder:
            for mode in ("realistic", "retail"):
                plan = mod_build.sim_qb_disc_edit(disc, str(Path(folder) / f"{mode}.iso"), mode)
                result = mod_build.preflight_plan(plan)["sim_qb_source_update"]["result_sha256"]
                # Realistic also updates the disc's legacy pass protection (combined lever 1, nine bytes), and (b81
                # fb-targets) the disc's season realism from before the fullback target rule, beneath the QB option
                from mod_editor.core import nfl2k5_sim_realism as realism
                upgraded = pressure.apply(realism.apply(source)[0])[0] if mode == "realistic" else source
                expected = aim.apply(qb.apply(upgraded, mode)[0])[0]
                # b81 history-pool: the copy also carries this release's career history pool (the disc has v0.9's)
                expected = mod_build._history_pool_upgrade(expected)[0]
                with self.subTest(mode=mode):
                    self.assertEqual(result, hashlib.sha256(expected).hexdigest())
                    self.assertEqual(XbeImage(expected).read(aim.SITE_VA, aim.SITE_SIZE), aim.site_bytes())

    def test_the_v09_update_installs_the_cpu_aim_repair(self):
        disc = os.environ.get("NFL2K5_V09_XISO")
        if not disc or not Path(disc).is_file():
            self.skipTest("the released v0.9 disc image is absent")
        from unittest.mock import patch
        from mod_editor.core import mod_build
        seen = []
        original = mod_build._cpu_kick_aim_with_kicking

        def keep(payload):
            result = original(payload)
            seen.append(result[0])
            return result
        with tempfile.TemporaryDirectory() as folder:
            plan = mod_build.v09_disc_update(disc, str(Path(folder) / "copy.iso"), backfield_cards=True)
            release = mod_build._v09_reference(Path(disc), mod_build._xbe_bytes(Path(disc)))
            with patch.object(mod_build, "_cpu_kick_aim_with_kicking", new=keep), \
                    patch("mod_editor.core.modpack.hash_file", return_value=release["image_sha256"]):
                mod_build._update_v09_disc(plan, lambda *_: None, preflight=True, project=False)
        self.assertEqual(len(seen), 1)
        self.assertEqual(aim.status(seen[0]), "applied")
        self.assertEqual(XbeImage(seen[0]).read(aim.SITE_VA, aim.SITE_SIZE), aim.site_bytes())


class BreakawayStopSetting(unittest.TestCase):
    """The simulated breakaway stop is one adjustable recipe value (review F3)."""

    def test_recipe_value_validation_and_round_trip(self):
        from mod_editor.core import mod_build, nfl2k5_build_settings as saved
        plan = mod_build.BuildPlan("src", "dst", sim_qb_injuries="realistic", sim_realism=True, k128_memory=True)
        self.assertEqual(plan.sim_breakaway_stop, 68)   # combined calibration freeze (was 72)
        self.assertEqual(plan.sim_breakaway_stop, mod_build.SIM_BREAKAWAY_STOP_DEFAULT)
        self.assertNotIn("sim_breakaway_stop", plan.to_recipe())
        plan.sim_breakaway_stop = 75
        self.assertEqual(plan.to_recipe()["sim_breakaway_stop"], 75)
        plan.sim_qb_injuries = "retail"
        self.assertNotIn("sim_breakaway_stop", plan.to_recipe())
        for bad in (19, 100, 72.5, "72", True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                saved.validate_sim_breakaway_stop(bad)
        self.assertEqual(scoring.parameters(breakaway_stop_beyond=75), {"breakaway_stop_beyond": 75.0})

    def test_the_option_installs_reads_back_and_retunes_the_stop(self):
        disc = os.environ.get("NFL2K5_B81_REVIEWED_TEST_DISC")
        if not disc or not Path(disc).is_file():
            self.skipTest("the private reviewed standard test disc is absent")
        from mod_editor.core import mod_build, nfl2k5_sim_qb_injuries as qb
        source = mod_build._xbe_bytes(Path(disc))
        shipped, _ = qb.apply(source, "realistic")
        self.assertEqual(scoring.installed(shipped), ("applied", {"breakaway_stop_beyond": 68.0}))  # frozen (was 72)
        fallback, receipt = qb.apply(shipped, "realistic", breakaway_stop=75)
        self.assertEqual(receipt["breakaway_stop"], 75.0)
        self.assertEqual(scoring.installed(fallback), ("applied", {"breakaway_stop_beyond": 75.0}))
        self.assertEqual(scoring.read_settings(fallback)["breakaway_stop_beyond"], 75.0)
        self.assertEqual(qb.apply(fallback, "realistic")[0], shipped)
        self.assertEqual(qb.apply(fallback, "retail")[0], qb.apply(shipped, "retail")[0])
        self.assertEqual(qb.apply(fallback, "realistic", breakaway_stop=75)[1]["status"], "already_applied")


class ShareExporter(unittest.TestCase):
    def test_a_non_default_installed_stop_is_frozen_into_the_exported_recipe(self):
        import json
        from unittest.mock import patch
        from mod_editor.core import mod_build, modpack_sources
        from mod_editor.core import nfl2k5_backfield_cards as cards
        # Since the combined freeze the default is 68, so a disc with the earlier 72 records it too.
        for installed, expected in ((("applied", {"breakaway_stop_beyond": 75.0}), 75),
                                    (("applied", {"breakaway_stop_beyond": 72.0}), 72),
                                    (("applied", {"breakaway_stop_beyond": 68.0}), None), (("retail", None), None)):
            with self.subTest(installed=installed), tempfile.TemporaryDirectory() as t:
                root = Path(t)
                project = root / "league.json"
                project.write_text('{"edits":[]}', encoding="utf-8")
                recipe = root / "frozen.json"
                recipe.write_text(json.dumps({"preset": "softdrink_basic", "overrides": {},
                                              "inputs": {"teams_2026": {"project": str(project)}}}), encoding="utf-8")
                with patch.object(mod_build, "_xbe_bytes", return_value=b"private standard executable"), \
                        patch.object(cards, "status", return_value="retail"), \
                        patch.object(mod_build, "_core_module") as core:
                    core.return_value.read_settings.return_value = {"status": "applied", "mode": "realistic",
                                                                    "custom_rate": 0.31}
                    core.return_value.installed.return_value = installed
                    portable, _ = modpack_sources.prepare(recipe, root / "work", patched_image=root / "copy.iso")
                self.assertEqual(portable["overrides"].get("sim_breakaway_stop"), expected)
        with self.assertRaises(ValueError):
            with tempfile.TemporaryDirectory() as t, \
                    patch.object(mod_build, "_xbe_bytes", return_value=b"x"), \
                    patch.object(cards, "status", return_value="retail"), \
                    patch.object(mod_build, "_core_module") as core:
                root = Path(t)
                (root / "league.json").write_text('{"edits":[]}', encoding="utf-8")
                (root / "frozen.json").write_text(json.dumps({"preset": "softdrink_basic", "overrides": {},
                    "inputs": {"teams_2026": {"project": str(root / "league.json")}}}), encoding="utf-8")
                core.return_value.read_settings.return_value = {"status": "applied", "mode": "realistic",
                                                                "custom_rate": 0.31}
                core.return_value.installed.return_value = ("foreign", None)
                modpack_sources.prepare(root / "frozen.json", root / "work", patched_image=root / "copy.iso")
