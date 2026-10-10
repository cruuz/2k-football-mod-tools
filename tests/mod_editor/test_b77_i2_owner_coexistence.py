"""b77-i2: owners that share a pinned span read applied together, in either install order.

Found by the integrator's owner scan of the stacked v0.6 executable: w1's rain fog row (nfl2k5_modern_color) lies
inside nfl2k5_weather_haze's pinned table, and p9's Modern 2 two-point hook lies inside nfl2k5_era_rules' retail
dependency guard at 0x206E70. Each tolerates exactly the other owner's bytes and nothing else.
"""
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_weather_haze as haze
from mod_editor.core import nfl2k5_modern_color as color
from mod_editor.core import nfl2k5_era_rules as era
from mod_editor.core import nfl2k5_cpu_money_downs as money_downs
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_anniversary_kickoff as gate
from mod_editor.core import nfl2k5_dynamic_kickoff as dk
from mod_editor.core import nfl2k5_kick_rules as kr
from mod_editor.core import nfl2k5_overtime as ot
from mod_editor.core import nfl2k5_defensive_try as dt
from mod_editor.core import nfl2k5_coin_defer as coin
from mod_editor.core import nfl2k5_decided_clock as clock
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

SOURCE = Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")
XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")


def edit(payload, va, data):
    out = bytearray(payload)
    at = XbeImage(payload).offset(va, len(data))
    out[at:at + len(data)] = data
    return bytes(out)


class Constants(unittest.TestCase):
    def test_haze_knows_the_colour_owners_rain_row(self):
        self.assertEqual(haze.RAIN_ROW_VA, color.RAIN_FOG[1])
        self.assertEqual(haze.RAIN_DISTANCES_RETAIL, color.RETAIL_FOG[8:16])
        self.assertTrue(haze.TABLE_VA <= haze.RAIN_ROW_VA and
                        haze.RAIN_ROW_VA + color.FOG_SIZE <= haze.TABLE_VA + haze.TABLE_SIZE)

    def test_the_two_point_site_is_the_only_money_downs_hook_inside_an_era_guard(self):
        import json
        guards = json.loads((era.ROOT / "data/nfl2k5_era_rules.json").read_text())["retail_guards"]
        inside = [name for name, (va, raw) in money_downs.HOOKS2.items()
                  if any(g["va"] < va + len(raw) and va < g["va"] + g["size"] for g in guards)]
        self.assertEqual(inside, ["two_point"])


@unittest.skipUnless(XBE.is_file(), "private USA retail XBE required")
class HazeAndRainFog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()

    def both(self, first, second):
        payload = first(self.retail)
        return second(payload)

    def test_either_order_reads_applied_and_gives_the_same_image(self):
        a = color.apply(haze.apply(self.retail)[0])[0]
        b = haze.apply(color.apply(self.retail)[0])[0]
        self.assertEqual(a, b)
        self.assertEqual(haze.status(a), "applied")
        self.assertIn(color.status(a), ("applied", "applied (custom)"))

    def test_only_the_two_distances_are_tolerated(self):
        payload = haze.apply(color.apply(self.retail)[0])[0]
        image = XbeImage(payload)
        row = bytearray(image.read(haze.RAIN_ROW_VA, 20))
        flipped_colour = bytearray(row); flipped_colour[16] ^= 1
        self.assertEqual(haze.status(edit(payload, haze.RAIN_ROW_VA, bytes(flipped_colour))), "foreign")
        flipped_density = bytearray(row); flipped_density[0] ^= 1
        self.assertEqual(haze.status(edit(payload, haze.RAIN_ROW_VA, bytes(flipped_density))), "foreign")
        backwards = bytearray(row); struct.pack_into("<2f", backwards, 8, 9000.0, 4000.0)
        self.assertEqual(haze.status(edit(payload, haze.RAIN_ROW_VA, bytes(backwards))), "foreign")
        other = bytearray(image.read(haze.TABLE_VA, 4)); other[0] ^= 1
        self.assertEqual(haze.status(edit(payload, haze.TABLE_VA, bytes(other))), "foreign")


def era_base(with_money_downs):
    payload = XBE.read_bytes()
    requests = era.REQUESTS + gate.REQUESTS + dt.REQUESTS + coin.REQUESTS + clock.REQUESTS
    payload, _ = space.apply(payload, requests + (money_downs.REQUESTS if with_money_downs else ()))
    for module in (kr, dk, ot, dt, coin, clock):
        payload, _ = module.apply(payload)
    payload, _ = gate.apply(payload, gate.disc_tables(SOURCE))
    return payload


@unittest.skipUnless(XBE.is_file() and SOURCE.is_file(), "private USA retail source required")
class EraRulesAndModern2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = era_base(True)
        cls.era_first = money_downs.apply(era.apply(base)[0], level="modern2")[0]
        cls.money_first = era.apply(money_downs.apply(base, level="modern2")[0])[0]

    def test_either_order_reads_applied_and_gives_the_same_image(self):
        self.assertEqual(self.era_first, self.money_first)
        for payload in (self.era_first, self.money_first):
            self.assertEqual(era.status(payload), "applied")
            self.assertEqual(money_downs.status(payload), "applied")
            self.assertEqual(money_downs.read_settings(payload)["level"], "modern2")

    def test_the_two_point_site_holds_the_owner_call_not_retail(self):
        va, retail = money_downs.HOOKS2["two_point"]
        self.assertNotEqual(XbeImage(self.era_first).read(va, len(retail)), retail)

    def test_any_other_change_in_the_guard_reads_foreign(self):
        va, retail = money_downs.HOOKS2["two_point"]
        image = XbeImage(self.era_first)
        for at in (va + len(retail), va + 20, va + 49):
            raw = bytearray(image.read(at, 1)); raw[0] ^= 0xFF
            self.assertEqual(era.status(edit(self.era_first, at, bytes(raw))), "foreign", hex(at))

    def test_a_foreign_hook_at_the_site_reads_foreign(self):
        va, retail = money_downs.HOOKS2["two_point"]
        site = bytearray(XbeImage(self.era_first).read(va, len(retail)))
        site[1] ^= 0x10   # the call now lands elsewhere: money downs is no longer exactly applied
        damaged = edit(self.era_first, va, bytes(site))
        self.assertNotEqual(money_downs.status(damaged), "applied")
        self.assertEqual(era.status(damaged), "foreign")


@unittest.skipUnless(os.environ.get("B77_V6_XBE"), "set B77_V6_XBE to the stacked v0.6 default.xbe")
class StackedExecutable(unittest.TestCase):
    def test_all_four_owners_read_applied(self):
        payload = Path(os.environ["B77_V6_XBE"]).read_bytes()
        self.assertEqual(haze.status(payload), "applied")
        self.assertEqual(color.status(payload), "applied")
        self.assertEqual(era.status(payload), "applied")
        self.assertEqual(money_downs.status(payload), "applied")


if __name__ == "__main__":
    unittest.main()
