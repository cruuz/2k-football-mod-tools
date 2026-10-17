"""b77 db1: deep balls led past the arm ceiling (Noah 10/17: "under threw one ... he's forcing it again").

The pure tests pin the arc-by-distance profile's deep band. The native test runs the game's own target solver,
accuracy pass, launch and flight (tools/b77/db1_deep_ball_probe.py) on the retail XBE with the Studio's 80-yard
scale, realistic flight and arc by distance, once with the beta 76.2 touch band and once with the current profile.
It skips when the retail USA default.xbe is not on this machine.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from tools.b77 import db1_deep_ball_probe as probe  # noqa: E402
from tools.nfl2k5_back_throws_replay import DEFAULT_XBE, RETAIL_SHA256  # noqa: E402


class DeepBandProfileTests(unittest.TestCase):
    def test_no_deep_lob_flies_slower_than_retail(self) -> None:
        retail = tt.CURVES["lobspeed"].retail
        for tenth in range(400, 801):
            yards = tenth / 10
            self.assertGreaterEqual(tt.interpolate(tt.ARC_BY_DISTANCE_LOBSPEED, yards),
                                    tt.interpolate(retail, yards) - 1e-9, yards)
        # The 76.2 band did, by 2.5 yd/s at 45 yd.
        self.assertAlmostEqual(tt.interpolate(tt.TOUCH_BAND_20261002_LOBSPEED, 45.0), 17.5)

    def test_short_game_and_flat_bomb_are_kept(self) -> None:
        self.assertEqual(tt.ARC_BY_DISTANCE_LOBSPEED[:5], tt.CURVES["lobspeed"].retail)
        self.assertEqual(tt.ARC_BY_DISTANCE_LOBSPEED[:5], tt.TOUCH_BAND_20261002_LOBSPEED[:5])
        self.assertEqual(tt.ARC_BY_DISTANCE_LOBSPEED[-1], tt.TOUCH_BAND_20261002_LOBSPEED[-1])

    def test_hang_never_drops_with_distance_in_the_deep_band(self) -> None:
        hangs = [yards / tt.interpolate(tt.ARC_BY_DISTANCE_LOBSPEED, yards) for yards in range(40, 81)]
        self.assertEqual(hangs, sorted(hangs))
        # 76.2 jumped 0.57 s between 40 and 45 yd; the current profile adds 0.25 s like retail.
        self.assertAlmostEqual(hangs[5] - hangs[0], 0.25, places=6)

    def test_cpu_grid_estimate_gap_back_to_retail(self) -> None:
        current = {r["yards"]: r["gap_s"] for r in probe.cpu_gap_table(tt.ARC_BY_DISTANCE_LOBSPEED)}
        touch = {r["yards"]: r["gap_s"] for r in probe.cpu_gap_table(tt.TOUCH_BAND_20261002_LOBSPEED)}
        retail = {r["yards"]: r["gap_s"] for r in probe.cpu_gap_table(tt.CURVES["lobspeed"].retail)}
        for yards in (45, 50, 55, 60, 65):
            self.assertLessEqual(current[yards], retail[yards] + 1e-9, yards)
            self.assertGreater(touch[yards] - current[yards], 0.15, yards)


@unittest.skipUnless(Path(DEFAULT_XBE).is_file(), "needs the retail USA default.xbe")
class NativeDeepBallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        retail = probe.read_retail(DEFAULT_XBE)
        cls.result = probe.compare(probe.studio_scale_80(retail, touch_band=True),
                                   after=probe.studio_scale_80(retail, touch_band=False))

    def test_inputs_are_the_two_profiles(self) -> None:
        self.assertEqual(self.result["profiles"]["before"]["arc_table"], "arc by distance (2026-10-02 touch band)")
        self.assertEqual(self.result["profiles"]["after"]["arc_table"], "arc by distance (realistic deep flight)")

    def test_deep_balls_land_in_stride_far_more_often(self) -> None:
        before = self.result["profiles"]["before"]["deep"]
        after = self.result["profiles"]["after"]["deep"]
        self.assertLess(before["in_stride_pct"], 90.0)
        self.assertGreaterEqual(after["in_stride_pct"], 95.0)
        self.assertLessEqual(after["short_2yd_plus_pct"], 5.0)
        self.assertLess(after["mean_short_yd"], 0.3)
        for arm, row in self.result["profiles"]["after"]["deep_by_arm"].items():
            old = self.result["profiles"]["before"]["deep_by_arm"][arm]
            self.assertGreaterEqual(row["in_stride_pct"], old["in_stride_pct"], arm)

    def test_no_overthrow_trade(self) -> None:
        # Fixing short balls must not push them past the receiver.
        for name in ("before", "after"):
            self.assertGreaterEqual(self.result["profiles"][name]["deep"]["mean_short_yd"], -0.5, name)

    def test_short_and_intermediate_game_is_bit_identical(self) -> None:
        self.assertEqual(self.result["short_intermediate_identical"], self.result["short_intermediate_cases"])
        self.assertEqual(self.result["short_intermediate_cases"], 120)
        self.assertLessEqual(self.result["profiles"]["after"]["short_max_release_to_land_yd"], 40.0)


if __name__ == "__main__":
    unittest.main()
