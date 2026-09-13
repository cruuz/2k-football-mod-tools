"""Native weather selection, shipped kickoff mapping and haze camera parameters."""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_weather as w, nfl2k5_weather_haze as h
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from tools.nfl2k5_weather_native_probe import Machine, uc

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)"


@unittest.skipUnless(uc is not None and (RETAIL/"default.xbe").is_file() and (RETAIL/"vc_53450030/0").is_file(),
                     "Unicorn or USA retail default.xbe/pack 0 absent; set NFL2K5_RETAIL_EXTRACTION")
class NativeWeatherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = (RETAIL/"default.xbe").read_bytes()
        if w.sha(cls.payload) != RETAIL_SHA256:
            raise AssertionError("Native fixture is not the pinned USA retail XBE")
        cls.resource = w.load_resource(RETAIL)
        cls.catalog = w.inspect_resource(cls.resource)
        at = cls.catalog["rows"][5]["offset"]
        cls.row = cls.resource[at:at+128]

    def test_climate_edits_reach_native_snow_and_stadium_suffix(self):
        draft = w.WeatherDraft(self.resource)
        for field, value in (("temperature_f", 15), ("precipitation_pct", 100), ("wind_mph", 12)):
            draft.set_value(5, 12, field, value)
        data, _ = w.apply(self.resource, draft.plan())
        at = self.catalog["rows"][5]["offset"]
        machine = Machine(self.payload, data[at:at+128])
        values = machine.schedule(12, 8, 20, week=8, game=3)
        self.assertEqual(values[0], 2)
        self.assertLessEqual(values[1], 15)
        self.assertGreater(values[2], 0)
        self.assertEqual(machine.suffixes(), ("n", "s"))
        self.assertEqual(machine.run(0x77BB0), 1)
        self.assertEqual(machine.run(0x77BE0), 0)
        for month in (1, 8, 11):
            retail = Machine(self.payload, self.row)
            machine.seed(47)
            retail.seed(47)
            self.assertEqual(machine.climate(month, 1), retail.climate(month, 1))

    def test_all_climate_rows_and_months_use_the_pinned_slots(self):
        machine = Machine(self.payload, self.row)
        for row in self.catalog["rows"]:
            at = row["offset"]
            machine.uc.mem_write(machine.STADIUM, self.resource[at:at+128])
            for values in row["months"]:
                for tod, (low, high) in enumerate(((-5, 15), (-10, 10), (-20, 0))):
                    machine.seed(47)
                    temperature, precipitation, wind, haze = machine.climate(values["month"], tod)
                    with self.subTest(row=row["index"], month=values["month"], tod=tod):
                        self.assertGreaterEqual(temperature, values["temperature_f"]+low-.0001)
                        self.assertLessEqual(temperature, values["temperature_f"]+high+.0001)
                        self.assertTrue(precipitation == 0 or .1 <= precipitation <= 1)
                        self.assertTrue(0 <= haze <= 1)
                        self.assertTrue(0 <= wind <= values["wind_mph"]*w.CM_PER_SECOND_PER_MPH*1.15+.001)

    def test_kickoff_hours_and_minutes_and_2026_template(self):
        machine = Machine(self.payload, self.row)
        for hour in range(13):
            expected = 0 if hour < 4 or hour >= 11 else (1 if hour < 6 else 2)
            for minute in (0, 5, 25, 59):
                machine.seed(7)
                actual = machine.schedule(9, hour, minute, week=2, game=3)
                self.assertEqual(actual[0], expected)
        schedule = json.loads((ROOT/"data/nfl_2026_schedule.json").read_text())
        games = schedule["games"]
        observed = set()
        for game in games:
            hour, minute = game["hour_field"], game["minute_field"]
            actual = machine.schedule(9, hour, minute)[0]
            expected = 0 if hour < 4 or hour >= 11 else (1 if hour < 6 else 2)
            self.assertEqual(actual, expected)
            observed.add(actual)
        self.assertEqual(observed, {0, 1, 2})

    def test_rain_snow_temperature_boundary_and_all_suffixes(self):
        machine = Machine(self.payload, self.row)
        for tod, letter in enumerate("dan"):
            for temperature, intensity, suffix in ((70, 0, "d"), (70, .5, "r"), (35, .5, "s"), (20, .5, "s")):
                machine.conditions(temperature=temperature, precipitation=intensity, tod=tod)
                self.assertEqual(machine.suffixes(), (letter, suffix))
        machine.conditions(temperature=35.01, precipitation=.5)
        self.assertEqual(machine.run(0x77BE0), 1)

    def test_play_now_all_six_choices(self):
        machine = Machine(self.payload, self.row)
        for option in range(6):
            machine.put(0xE601D0, option)
            machine.put(0xE60184, 0)
            machine.seed(7)
            machine.run(0xE3150)
            intensity = machine.readf(0xE5FFAC)
            if option == 0:
                self.assertEqual(intensity, 0)
            elif option in (1, 3):
                self.assertTrue(.25 <= intensity <= .45)
            elif option in (2, 4):
                self.assertTrue(.5 <= intensity <= 1)
            if option in (1, 2):
                self.assertEqual(machine.run(0x77BE0), 1)
            if option in (3, 4):
                self.assertEqual(machine.run(0x77BB0), 1)

    def test_precipitation_effective_rating_penalty_native_block(self):
        machine = Machine(self.payload, self.row)
        for temperature, precip, flag, expected in ((70, 0, 1, .8), (70, .5, 1, .75),
                                                   (20, .5, 1, .725), (20, .5, 0, .8)):
            machine.conditions(temperature=temperature, precipitation=precip)
            machine.f32(machine.STACK+0x10, .8)
            machine.run(0x17A84B, ebx=flag, stop=0x17A894)
            self.assertAlmostEqual(machine.readf(machine.STACK+0x10), expected, places=6)

    def test_weather_interpolates_contact_probability_before_rating_and_fumble_slider(self):
        machine = Machine(self.payload, self.row)
        for temperature, precip, expected in ((70, 0, .05), (70, .5, .065), (20, .5, .075)):
            machine.conditions(temperature=temperature, precipitation=precip)
            machine.f32(machine.STACK+0x18, .05)
            machine.run(0x1C75B7, stop=0x1C7659)
            self.assertAlmostEqual(machine.readf(machine.STACK+0x18), expected, places=6)

    def test_haze_writer_reparse_undo_foreign_and_no_code_changes(self):
        after, _ = h.apply(self.payload)
        self.assertEqual(h.status(after), "applied")
        self.assertEqual(h.verify(after)["coefficient"], 1)
        self.assertEqual(h.apply(after)[0], after)
        self.assertEqual(h.apply(after, enabled=False)[0], self.payload)
        for section in XbeImage(self.payload).sections:
            if section.name != ".data":
                self.assertEqual(after[section.raw:section.raw+section.raw_size],
                                 self.payload[section.raw:section.raw+section.raw_size])
        for va in (h.SITE_VA, h.TABLE_VA+12, 0x85EF0):
            bad = bytearray(after)
            bad[XbeImage(after).offset(va, 1)] ^= 1
            self.assertEqual(h.status(bytes(bad)), "foreign")
            with self.assertRaises(ValueError):
                h.apply(bytes(bad))

    def test_haze_reader_to_camera_and_unaffected_paths(self):
        after, _ = h.apply(self.payload)
        machines = (Machine(self.payload, self.row), Machine(after, self.row))
        for temperature, precip, haze, indoor, expected in (
            (70, 0, .25, False, (.2, .25)), (70, 0, 0, False, (0, 0)),
            (70, .8, .25, False, (.825, .825)), (20, .8, .25, False, (.65, .65)),
            (70, 0, .25, True, (0, 0)),
        ):
            for machine, value in zip(machines, expected):
                machine.conditions(temperature=temperature, precipitation=precip, haze=haze, indoor=indoor)
                reader = machine.haze()
                camera = machine.camera_haze()
                self.assertEqual(reader, camera)
                self.assertAlmostEqual(camera[0], value, places=6)

    def test_haze_composes_both_orders_with_clock_schedule_and_helmet(self):
        from tests import nfl2k5_allocator_stack as stack
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import prerequisites
        from mod_editor.core import nfl2k5_xbe_space as space
        seed, _ = space.apply(prerequisites(self.payload), stack.REQUESTS, scaleout=True)
        for owner in (stack.AcceleratedClockOn, stack.franchise_2026, stack.helmet_finish):
            with self.subTest(owner=owner.OWNER):
                baseline, _ = owner.apply(seed)
                left, _ = h.apply(baseline)
                right, _ = owner.apply(h.apply(seed)[0])
                self.assertEqual(left, right)
                self.assertEqual(owner.status(left), "applied")
                self.assertEqual(h.verify(left)["state"], "applied")
                self.assertEqual(h.apply(left, enabled=False)[0], baseline)
                self.assertEqual(space.apply(left, stack.REQUESTS, scaleout=True)[0], left)


if __name__ == "__main__":
    unittest.main()
