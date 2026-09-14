"""Climate edits, reparse verifier, Undo and supported retail composition."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_weather as w

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)"


def synthetic():
    """Original, non-retail records; production geometry pin stays strict."""
    data = bytearray(0x9000)
    data[:4] = data[0x2C:0x30] = b"ROST"
    struct.pack_into("<II", data, 4, len(data)-32, len(data)-32)
    struct.pack_into("<II", data, 0x30, 17, 0x60-0x34+1)
    struct.pack_into("<II", data, 0x70, 82, 0xD0-0x74+1)
    tail = 0x4000
    for i in range(82):
        at = 0xD0+128*i
        for field, text in ((0, f"Stadium {i}"), (8, f"City {i}"), (12, f"s{i:02}")):
            raw = text.encode("utf-16le")+b"\0\0"
            struct.pack_into("<i", data, at+field, tail-(at+field)+1)
            data[tail:tail+len(raw)] = raw
            tail += len(raw)
        struct.pack_into("<I", data, at+0x18, int(i == 1))
        data[at+124] = i
        for offset, value in ((0x28, 50), (0x44, 25), (0x60, 447.04)):
            struct.pack_into("<7f", data, at+offset, *([value]*7))
    digest = w.sha(b"".join(data[a+24:a+40]+data[a+124:a+128] for a in range(0xD0, 0xD0+82*128, 128)))
    return bytes(data), digest


class ClimateTests(unittest.TestCase):
    def setUp(self):
        self.data, digest = synthetic()
        self.pin = patch.object(w, "SHAPE_SHA256", digest)
        self.pin.start()
        self.addCleanup(self.pin.stop)
        self.draft = w.WeatherDraft(self.data)

    def plan(self):
        self.draft.set_value(5, 12, "temperature_f", 15)
        self.draft.set_value(5, 12, "precipitation_pct", 100)
        self.draft.set_value(5, 12, "wind_mph", 12)
        return self.draft.plan()

    def test_roundtrip_and_complete_diff(self):
        plan = self.plan()
        self.assertEqual(w.status(self.data, plan), "ready")
        after, receipt = w.apply(self.data, plan)
        self.assertFalse(receipt["runtime_witnessed"])
        self.assertEqual(w.verify(after, plan, before=self.data)["fields"], 3)
        self.assertEqual(w.status(after, plan), "applied")
        self.assertEqual(w.apply(after, plan)[0], after)
        row = w.inspect_resource(after)["rows"][5]["months"][4]
        self.assertEqual(row["temperature_f"], 15)
        self.assertEqual(row["precipitation_pct"], 100)
        self.assertAlmostEqual(row["wind_mph"], 12, places=5)

    def test_verifier_rejects_unowned_mutation(self):
        plan = self.plan()
        after, _ = w.apply(self.data, plan)
        bad = bytearray(after)
        bad[0x8900] = 1
        with self.assertRaisesRegex(w.WeatherError, "outside"):
            w.verify(bytes(bad), plan, before=self.data)

    def test_stale_partial_and_foreign_plans_refuse(self):
        plan = self.plan()
        bad = copy.deepcopy(plan)
        bad["changes"][0]["before"] += 1
        self.assertEqual(w.status(self.data, bad), "foreign")
        partial, _ = w.apply(self.data, dict(schema=w.SCHEMA, changes=plan["changes"][:1]))
        with self.assertRaisesRegex(w.WeatherError, "Partly applied"):
            w.apply(partial, plan)
        bad = copy.deepcopy(plan)
        bad["changes"][0]["asset_code"] = "s99"
        self.assertEqual(w.status(self.data, bad), "foreign")

    def test_large_json_integers_refuse_with_climate_validation_error(self):
        for field in w.FIELDS:
            for value in (10**1000, -(10**1000)):
                with self.subTest(field=field, sign=value > 0):
                    with self.assertRaisesRegex(w.WeatherError, "finite value"):
                        self.draft.set_value(5, 12, field, value)
        for member in ("before", "after"):
            for value in (10**1000, -(10**1000)):
                with self.subTest(member=member, sign=value > 0):
                    plan = self.plan()
                    plan["changes"][0][member] = value
                    plan = json.loads(json.dumps(plan))
                    self.assertEqual(w.status(self.data, plan), "foreign")
                    with self.assertRaisesRegex(w.WeatherError, "finite value"):
                        w.apply(self.data, plan)

    def test_validation_and_month_alias(self):
        for value in (True, float("nan"), float("inf"), -1, 101, "20"):
            with self.subTest(value=value), self.assertRaises(w.WeatherError):
                self.draft.set_value(5, 12, "precipitation_pct", value)
        for month in (0, 3, 6, 13, True):
            with self.subTest(month=month), self.assertRaises(w.WeatherError):
                self.draft.set_value(5, month, "temperature_f", 60)
        self.draft.set_value(5, 7, "temperature_f", 60)
        self.draft.set_value(5, 8, "temperature_f", 61)
        plan = self.draft.plan()
        self.assertEqual(len(plan["changes"]), 1)
        plan["changes"].append({**plan["changes"][0], "month": 7})
        with self.assertRaisesRegex(w.WeatherError, "Duplicate"):
            w.apply(self.data, plan)

    def test_undo_preset_is_one_action_and_does_not_accumulate(self):
        self.draft.set_value(5, 12, "precipitation_pct", 75)
        previous = self.draft.plan()
        self.draft.milder_outdoor_preset()
        once = self.draft.plan()
        self.assertFalse(any(c["stadium_index"] == 1 for c in once["changes"]))
        self.assertFalse(any(c["stadium_index"] >= 32 for c in once["changes"]))
        self.draft.milder_outdoor_preset()
        self.assertEqual(self.draft.plan(), once)
        self.assertTrue(self.draft.undo())
        self.assertEqual(self.draft.plan(), previous)
        self.assertTrue(self.draft.undo())
        self.assertEqual(self.draft.plan()["changes"], [])
        self.assertFalse(self.draft.undo())

    def test_noop_has_no_undo_and_export_is_detached(self):
        self.draft.set_value(5, 12, "temperature_f", 50)
        self.assertFalse(self.draft.undo())
        exported = self.plan()
        exported["changes"].clear()
        self.assertEqual(len(self.draft.plan()["changes"]), 3)

    def test_corrupt_geometry_and_truncated_pointer_refuse(self):
        for at, value in ((0x70, 83), (0x74, 0xFFFFFFF0), (0xD0+0x18, 2)):
            bad = bytearray(self.data)
            struct.pack_into("<I", bad, at, value)
            with self.subTest(at=at), self.assertRaises(w.WeatherError):
                w.inspect_resource(bytes(bad))

    def test_other_roster_edits_compose_and_moved_table_reparses(self):
        plan = self.plan()
        before = bytearray(self.data)
        before[0x8800] = 123
        # Move all stadium records while adjusting their field-relative pointers.
        table = bytearray(before[0xD0:0xD0+82*128])
        delta = 128
        for i in range(82):
            for field in (0, 8, 12):
                at = i*128+field
                struct.pack_into("<i", table, at, struct.unpack_from("<i", table, at)[0]-delta)
        before[0x150:0x150+len(table)] = table
        struct.pack_into("<I", before, 0x74, 0x150-0x74+1)
        before = bytes(before)
        after, _ = w.apply(before, plan)
        self.assertEqual(w.inspect_resource(after)["table_offset"], 0x150)
        self.assertEqual(after[0x8800], 123)
        w.verify(after, plan, before=before)

    def test_json_rejects_duplicate_and_nan(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/"plan.json"
            for text in ('{"schema":1,"schema":2}', '{"x":NaN}'):
                p.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    w.read_json(p)

    def test_final_image_pass_resolves_outer_offset_and_refuses_before_mutation(self):
        # A non-retail outer-container fixture: moved resource, unrelated neighbors.
        origin = 0x2500
        backing = bytearray(b"p"*origin + self.data + b"s"*128)
        entry = SimpleNamespace(virtual_offset=origin, size=len(self.data))
        writes = []

        class Archive:
            _fd = None
            entries = [None]*5 + [entry]

            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, at, size):
                return bytes(backing[at:at+size])

            def write(self, at, content):
                writes.append((at, len(content)))
                backing[at:at+len(content)] = content
                return len(content)

        plan = self.plan()
        with patch.object(w.rr, "_outer_image", return_value=Archive):
            w.apply_to_image("disposable-image.iso", plan)
            self.assertEqual(writes, [(origin, len(self.data))])
            self.assertEqual(backing[:origin], b"p"*origin)
            self.assertEqual(backing[-128:], b"s"*128)
            w.verify(w.load_resource("disposable-image.iso"), plan, before=self.data)
            w.apply_to_image("disposable-image.iso", plan)
            self.assertEqual(len(writes), 1)
            stale = copy.deepcopy(plan)
            stale["changes"][0]["before"] = 16
            stale["changes"][0]["after"] = 17
            snapshot = bytes(backing)
            with self.assertRaises(w.WeatherError):
                w.apply_to_image("disposable-image.iso", stale)
            self.assertEqual(bytes(backing), snapshot)
            self.assertEqual(len(writes), 1)


@unittest.skipUnless((RETAIL/"vc_53450030/0").is_file(), "USA retail vc_53450030/0 is absent; set NFL2K5_RETAIL_EXTRACTION")
class RetailClimateTests(unittest.TestCase):
    def test_real_resource_and_all_wind_values_roundtrip(self):
        data = w.load_resource(RETAIL)
        draft = w.WeatherDraft(data)
        for row in draft.catalog["rows"]:
            for slot in row["months"]:
                for field in w.FIELDS:
                    draft.set_value(row["index"], slot["month"], field, slot[field])
        self.assertEqual(draft.plan()["changes"], [])
        self.assertEqual(draft.catalog["table_offset"], 0xD0)
        draft.milder_outdoor_preset()
        after, _ = w.apply(data, draft.plan())
        w.verify(after, draft.plan(), before=data)


if __name__ == "__main__":
    unittest.main()
