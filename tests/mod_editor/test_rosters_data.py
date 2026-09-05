"""Standalone style/DOB codec and explicit age-shift transactions, under 2 MB per fixture."""
import copy
import datetime as dt
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_roster_ages as ages
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body, SAMPLE, RETAIL_EXTRACTION
from tests.mod_editor.test_rosters_reserves_abilities import document as save_document


class StylesTests(unittest.TestCase):
    def test_boundaries_parity_and_only_owned_bytes(self):
        record = rr.RosterDocument(synthetic_body()).players[0].record
        for value in range(256):
            record.set("power_run_style", value)
            self.assertEqual(record.power_run_style_bucket, 0 if value < 33 else 1 if value < 66 else 2)
            record.set("scramble", value)
            before = record.encode()
            record.throw_style = 1 - (value & 1)
            after = record.encode()
            self.assertEqual(after[0x4F], value ^ 1)
            self.assertEqual(before[:0x4F] + before[0x50:], after[:0x4F] + after[0x50:])
            record.set_scramble_magnitude(100)
            self.assertEqual(record.values["scramble"], 100 | (after[0x4F] & 1))

    def test_csv_preserves_raw_style_values_and_reports_invalid_values(self):
        doc = rr.RosterDocument(synthetic_body())
        for key, value in (("power_run_style", 38), ("scramble", 97), ("kicking_style", 49)):
            doc.players[0].record.set(key, value)
        csv = rr.export_csv(doc)
        other = rr.RosterDocument(synthetic_body())
        rr.import_csv(other, csv)
        self.assertEqual(other.to_body(), doc.to_body())
        before = other.to_body()
        receipt = rr.import_csv(other, "pool,index,power_run_style,scramble,kicking_style\nprimary,0,-1,256,nope\n")
        self.assertEqual(len(receipt["log"]), 3)
        self.assertEqual(other.to_body(), before)
        for field in (*rr.STYLE_RATINGS, "throw_style", "power_run_style_bucket"):
            for value in (1.1, True, "1"):
                with self.assertRaises(rr.RosterRecordError):
                    other.players[0].record.set(field, value)

    def test_sparse_json_keeps_codec_keys(self):
        doc = rr.RosterDocument(synthetic_body())
        p = doc.players[0]
        p.record.power_run_style_bucket = 2
        p.record.throw_style = 0
        p.record.set("kicking_style", 1)
        fields = rr.edits_document(doc)["edits"][0]["fields"]
        self.assertEqual(set(fields), {"power_run_style", "scramble", "kicking_style"})


class AgesTests(unittest.TestCase):
    def setUp(self):
        self.doc = rr.RosterDocument(synthetic_body())

    def test_preview_copy_isolation_precise_masks_and_repeat(self):
        before = self.doc.to_body()
        plan = ages.preview(self.doc, 2004, 2026)
        self.assertEqual(self.doc.to_body(), before)
        receipt = ages.apply(self.doc, plan)
        self.assertEqual(receipt["changed"], 7)
        self.assertEqual(self.doc.reference_year, 2026)
        permitted = {row["offset"] + i for row in plan["changes"] for i in (0x1A, 0x1B)}
        after = self.doc.to_body()
        self.assertTrue(all(i in permitted for i, (a, b) in enumerate(zip(before, after)) if a != b))
        for row in plan["changes"]:
            off = row["offset"]
            self.assertEqual(before[off + 0x1A] & 0x1F, after[off + 0x1A] & 0x1F)
            self.assertEqual(before[off + 0x1B] & 0xF0, after[off + 0x1B] & 0xF0)
            self.assertEqual(row["age_before"], row["age_after"])
        self.assertFalse(receipt["saved"])
        self.assertEqual(ages.preview(self.doc, 2004, 2026)["changed"], 0)
        self.assertEqual(ages.preview(self.doc, 2026, 2026)["changed"], 0)
        with self.assertRaisesRegex(rr.RosterRecordError, "stale"):
            ages.apply(self.doc, plan)

    def test_leap_day_invalid_dates_implausible_dates_and_foreign_scope(self):
        p, invalid, young = self.doc.players[:3]
        p.record.birth_date = dt.date(1980, 2, 29)
        invalid.record.set("birth_month", 0)
        young.record.birth_date = dt.date(2002, 1, 1)
        plan = ages.preview(self.doc, 2004, 2026, [p, invalid, young])
        self.assertEqual(len(plan["changes"]), 1)
        self.assertEqual(len(plan["skipped"]), 2)
        row = plan["changes"][0]
        self.assertEqual(row["birth_after"], "2002-02-28")
        self.assertIn("February 29", row["note"])
        ages.apply(self.doc, plan)
        self.assertEqual(p.record.birth_date, dt.date(2002, 2, 28))
        for scope in ([p, p], [rr.RosterDocument(synthetic_body()).players[0]]):
            with self.assertRaises(rr.RosterRecordError):
                ages.preview(self.doc, 2004, 2026, scope)

    def test_altered_stale_plan_and_bad_seasons_are_atomic(self):
        plan = ages.preview(self.doc, 2004, 2026)
        altered = copy.deepcopy(plan)
        altered["changes"][-1]["after"]["birth_day"] = 0
        for candidate in (altered, {**plan, "target_year": 2027}):
            with self.assertRaises(rr.RosterRecordError):
                ages.apply(self.doc, candidate)
            self.assertEqual(self.doc.to_body(), self.doc.original)
        self.doc.players[-1].record.set("speed", 50)
        before = self.doc.to_body()
        with self.assertRaisesRegex(rr.RosterRecordError, "stale"):
            ages.apply(self.doc, plan)
        self.assertEqual(before, self.doc.to_body())
        for year in (None, 99, 10000, True, 2026.0):
            with self.assertRaises(rr.RosterRecordError):
                ages.preview(self.doc, 2004, year)

    def test_century_context_and_noncanonical_noop(self):
        p = self.doc.players[0]
        p.record.reference_year = 2126
        p.record.birth_date = dt.date(2104, 3, 24)
        self.doc.set_reference_year(2126)
        receipt = ages.apply(self.doc, ages.preview(self.doc, 2126, 2226, [p]))
        self.assertEqual(receipt["changed"], 0)  # same modulo-100 bytes; no hidden context mutation
        self.assertEqual(self.doc.reference_year, 2126)
        p.record.values.update(birth_year_low=6, birth_year_high=12)  # legacy raw 102
        self.doc.set_reference_year(2026)
        before = self.doc.to_body()
        ages.apply(self.doc, ages.preview(self.doc, 2026, 2026))
        self.assertEqual(before, self.doc.to_body())

    def test_save_reserve_membership_keeps_year_context(self):
        doc = save_document()
        doc.demote_active(0, 1)
        plan = ages.preview(doc, 2004, 2026)
        receipt = ages.apply(doc, plan)
        reserved = doc.reserve_players(0)[0]
        expected = reserved.record.birth_date
        doc.promote_reserve(0, reserved.index)
        self.assertEqual(doc.reference_year, 2026)
        self.assertEqual(reserved.record.birth_date, expected)
        self.assertEqual(ages.preview(doc, 2004, 2026)["changed"], 0)
        self.assertGreater(receipt["changed"], 0)

    def test_context_age_validation(self):
        self.doc.set_reference_year(2026)
        self.doc.players[0].record.birth_date = dt.date(2010, 1, 1)
        self.assertTrue(any(r["check"] == "season age" for r in rr.validate(self.doc)))


class RetailAgesTests(unittest.TestCase):
    def test_retail_2026_ages_and_context_csv_roundtrip(self):
        if not (RETAIL_EXTRACTION / "vc_53450030/0").is_file():
            self.skipTest("private retail extraction is absent")
        with rr._outer_image()(RETAIL_EXTRACTION) as archive:
            e = archive.entries[5]
            resource = archive.read(e.virtual_offset, e.size)
        doc = rr.RosterDocument(resource[32:])
        plan = ages.preview(doc, 2004, 2026)
        self.assertEqual(plan["changed"], 1944)
        ages.apply(doc, plan)
        other = rr.RosterDocument(resource[32:], reference_year=2026)
        receipt = rr.import_csv(other, rr.export_csv(doc))
        self.assertEqual(receipt["log"], [])
        self.assertEqual(other.to_body(), doc.to_body())
        for row in plan["changes"]:
            self.assertEqual(row["age_before"], row["age_after"])


if __name__ == "__main__":
    unittest.main()
