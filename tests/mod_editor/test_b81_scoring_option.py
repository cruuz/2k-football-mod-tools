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
        # Rebuild what the previous version wrote: every edit except the two kicking sites.
        bank = qb._bank_allocation(current)
        setting = qb._Setting("realistic", qb.REALISTIC_RATE)
        physical = qb.physical_view(current)
        previous = qb._transform(physical, qb._edits(physical, bank, setting, with_scoring=False), restoring=False)
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


if __name__ == "__main__":
    unittest.main()
