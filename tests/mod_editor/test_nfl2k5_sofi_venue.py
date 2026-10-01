"""SoFi Stadium venue rows (u6): the two stadium rows, their composition with the other ROST writers, the weather
editor's roof pin, and the native proof that the Chargers row now behaves as the retail dome does."""
import importlib.util
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_sofi_venue as sv  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"
XBE = EXTRACTED / "default.xbe"


def _retail_rost():
    from mod_editor.core import nfl2k5_modern_metlife as ml
    from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
    require_nfl_retail_packs(EXTRACTED)
    with ml._outer_image()(str(EXTRACTED)) as archive:
        entry = archive.entries[sv.ROST_OUTER_INDEX]
        return archive.read(entry.virtual_offset, entry.size)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class SofiRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail_rost()
        cls.sofi, cls.receipt = sv.rost_sofi(cls.retail)

    def test_retail_then_applied(self):
        self.assertEqual(sv.rost_state(self.retail), "retail")
        self.assertEqual(sv.rost_state(self.sofi), "applied")
        self.assertEqual(len(self.sofi), len(self.retail))
        again, receipt = sv.rost_sofi(self.sofi)
        self.assertEqual(again, self.sofi)
        self.assertEqual({r["state"] for r in receipt["records"]}, {"already_applied"})

    def test_rows_say_sofi(self):
        from mod_editor.core import nfl2k5_roster_records as rr
        body = self.sofi[rr.RESOURCE_HEADER_SIZE:]
        for code in sv.ROWS:
            offset, fields = sv._records(body)[code]
            texts = {name: text for name, (_t, text) in fields.items()}
            self.assertEqual(texts["name"], "Super Bowl LXI" if code == "s40" else "SoFi Stadium")
            self.assertEqual(texts["display_name"], "SoFi Stadium")
            self.assertEqual(texts["location"], "Inglewood, CA")
            self.assertEqual(texts["asset_code"], code)                 # the engine's file-name key stays
            self.assertEqual(sv._words(body, offset), (70240, 1, 0))     # capacity, indoor, turf

    def test_only_the_three_rows_change(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_roster_records as rr
        header = rr.RESOURCE_HEADER_SIZE
        rows = {fs["asset_code"][1]: off for off, fs in ml._stadium_records(self.retail[header:])}
        allowed = set()
        for rec in self.receipt["records"]:
            allowed.update(range(header + rec["block"][0], header + rec["block"][1]))
            off = header + rows[rec["venue"]]
            for field in (0x00, 0x08, 0x0C, 0x10, 0x14, 0x04, 0x18, 0x1C):
                allowed.update(range(off + field, off + field + 4))
            if rec["venue"] in ("s23", "s40"):             # the climate the Rams and Super Bowl rows take from s24
                allowed.update(range(off + sv.CLIMATE[0], off + sv.CLIMATE[1]))
        changed = {i for i, (a, b) in enumerate(zip(self.retail, self.sofi)) if a != b}
        self.assertTrue(changed)
        self.assertLessEqual(changed, allowed)

    def test_composes_with_the_other_name_writers_in_any_order(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        from mod_editor.core import nfl2k5_modern_metlife as ml
        self.assertEqual(mv.rost_state(self.sofi), "retail")
        self.assertEqual(ml.rost_status(self.sofi), "retail")
        u4_after, _ = mv.rost_rename(self.sofi)
        u4_first, _ = mv.rost_rename(self.retail)
        sofi_after, _ = sv.rost_sofi(u4_first)
        self.assertEqual(u4_after, sofi_after)
        self.assertEqual(sv.rost_state(u4_after), "applied")
        ml_after, _ = ml.rost_rename(sofi_after)
        self.assertEqual(ml.rost_status(ml_after), "applied")
        self.assertEqual(sv.rost_state(ml_after), "applied")

    def test_one_building_one_climate(self):
        """The Rams row takes the Chargers row's climate (main, 2026-09-24): San Diego's floats, never below the 35 F
        snow split, so neither row rolls snow; the copy is idempotent."""
        from mod_editor.core import nfl2k5_weather as w
        self.assertTrue(sv.climate_synced(self.sofi))
        self.assertFalse(sv.climate_synced(self.retail))
        rows = {r["asset_code"]: r for r in w.inspect_resource(self.sofi)["rows"]}
        self.assertEqual(rows["s23"]["months"], rows["s24"]["months"])
        self.assertEqual(rows["s40"]["months"], rows["s24"]["months"])
        self.assertGreater(min(m["temperature_f"] for m in rows["s23"]["months"]) - 20.0, 35.0)  # night offset [-20, 0)
        self.assertTrue(self.receipt["climate"]["changed"])

    def test_weather_editor_reads_the_sofi_rows(self):
        from mod_editor.core import nfl2k5_weather as w
        for data, s24_indoor in ((self.retail, False), (self.sofi, True)):
            rows = {r["asset_code"]: r for r in w.inspect_resource(data)["rows"]}
            self.assertTrue(rows["s23"]["indoor"])
            self.assertEqual(rows["s24"]["indoor"], s24_indoor)
        rows = {r["asset_code"]: r for r in w.inspect_resource(self.sofi)["rows"]}
        self.assertEqual(rows["s24"]["stadium"], "SoFi Stadium")
        self.assertTrue(rows["s40"]["indoor"])


def _probe_module():
    spec = importlib.util.spec_from_file_location("sofi_dome_probe", ROOT / "tools" / "nfl2k5_sofi_dome_probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unicorn():
    try:
        import unicorn  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(EXTRACTED.is_dir() and XBE.is_file() and _unicorn(), "needs the retail executable and unicorn")
class NativeDome(unittest.TestCase):
    """The retail routines, run natively: with the SoFi rows a rain roll at the Chargers' venue still names the rain
    bundle, then the indoor reset leaves no precipitation, wind or haze, the light rig is the night/indoor table and
    the player shadows use the turf scene, exactly as at the Rams' retail dome."""

    @classmethod
    def setUpClass(cls):
        cls.probe = _probe_module()
        cls.xbe = XBE.read_bytes()
        cls.retail = _retail_rost()
        cls.sofi, _ = sv.rost_sofi(cls.retail)

    def test_retail_chargers_row_rains(self):
        r = self.probe.probe(self.xbe, self.retail, 24)
        self.assertEqual(r["bundle"], "s24dr.iff")
        self.assertAlmostEqual(r["weather_after"]["precipitation"], 0.9, places=5)
        self.assertEqual(r["light_rig"], "rain")
        self.assertEqual(r["shadow_scene"], "shadow_200")
        self.assertEqual(r["team_package_weather"], "r")

    def test_sofi_rows_behave_as_the_dome(self):
        for index, code in ((24, "s24"), (23, "s23"), (35, "s40")):
            for tod, temp, weather in ((0, 60.0, "r"), (2, 20.0, "s")):
                r = self.probe.probe(self.xbe, self.sofi, index, tod=tod, temp=temp)
                self.assertEqual(r["stadium"], "Super Bowl LXI" if code == "s40" else "SoFi Stadium")
                self.assertEqual(r["bundle"], f"{code}{'dn'[tod // 2]}{weather}.iff")
                self.assertEqual(r["weather_after"], dict(temperature=70.0, precipitation=0.0, wind=0.0, haze=0.0))
                self.assertEqual(r["light_rig"], "night_indoor")
                self.assertEqual(r["shadow_scene"], "shadow_100")
                self.assertEqual(r["team_package_weather"], "d")


if __name__ == "__main__":
    unittest.main()
