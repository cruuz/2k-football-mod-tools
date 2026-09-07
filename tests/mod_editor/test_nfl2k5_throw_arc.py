"""Flatter flight: fixed bytes, equal-height model, source safety and streaming."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_throw_arc as arc
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_rdata_sites as rdata
from tests.nfl2k5_throw_tuning_test import _build_synthetic_xbe
from tests.nfl2k5_gameplay_levers_fixture import XBE, replace


class FlightTests(unittest.TestCase):
    def setUp(self):
        self.retail = _build_synthetic_xbe()

    def test_flatter_flight_keeps_eighty_yard_reach_and_short_speeds(self):
        old = tt.curves_for(tt.TuningSettings(80))
        new = arc.curves_for(tt.TuningSettings(80))
        for key in ("bullet", "lob"):
            self.assertEqual(old[key], new[key])
        for distance in (1, 6, 8, 10, 15, 20, 25, 30, 35):
            self.assertEqual(tt.interpolate(old["lobspeed"], distance), tt.interpolate(new["lobspeed"], distance))
        for distance in (36, 40, 55, 65, 80):
            self.assertGreater(tt.interpolate(new["lobspeed"], distance), tt.interpolate(old["lobspeed"], distance))
        before, after = tt.preview(old)[-1], tt.preview(new)[-1]
        self.assertEqual(before.deep_cap_yards, after.deep_cap_yards)
        self.assertEqual((after.deep_cap_yards, after.hang_seconds, after.apex_yards), (80, 3.2, 13.7))
        self.assertLess(after.apex_yards, before.apex_yards)

    def test_preview_curve_uses_the_same_ballistic_model(self):
        points = arc.flight_points(80, 25)
        self.assertEqual(points[0], (0, 0))
        self.assertEqual(points[-1], (80, 0))
        self.assertAlmostEqual(max(y for _, y in points), tt.GRAVITY_YD_S2 * 3.2 ** 2 / 8)
        for bad in ((0, 25), (80, float("nan")), (80, 0), (101, 25)):
            with self.assertRaises(ValueError):
                arc.flight_points(*bad)

    def test_apply_changes_one_ordinate_and_no_instructions_or_distance_tables(self):
        out, receipt = arc.apply(self.retail)
        self.assertEqual(arc.status(out), "applied")
        self.assertEqual(arc.apply(out)[0], out)
        self.assertEqual(arc.apply(out)[1]["changed_bytes"], 0)
        allowed = set()
        off = rdata.offset_of(out, 0x50BCB8)
        allowed.update(range(off + 40, off + 44))
        from mod_editor.core.nfl2k5_bump_strength import _sections
        for section in _sections(out):
            allowed.update(range(section.header_offset + 36, section.header_offset + 56))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(self.retail, out))))
        self.assertFalse(receipt["distance_curves_changed"])

    def test_mixed_foreign_and_relocated_reader_refuse(self):
        out, _ = arc.apply(self.retail)
        inputs = [b"", replace(out, 0x50BCB8, struct.pack("<I", 4)),
                  replace(out, 0x50BCB8 + 40, b"\xab"),
                  replace(out, tt.LOBSPEED_PAIRS_SITE_VA, b"\x90")]
        relocated, _ = tt.apply_arc_table(self.retail)
        inputs.append(relocated)
        for payload in inputs:
            self.assertEqual(arc.status(payload), "foreign")
            with self.assertRaises(ValueError):
                arc.apply(payload)

    def test_conflicting_flight_selections_refuse(self):
        for settings in (tt.TuningSettings(80, .1), tt.TuningSettings(80, 0, True), tt.TuningSettings(80, 0, False, True)):
            with self.assertRaises(tt.ThrowTuningError):
                arc.curves_for(settings)

    def test_transactional_copy_round_trip_and_source_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder).resolve() / "default.xbe", Path(folder).resolve() / "new.xbe"
            source.write_bytes(self.retail)
            receipt = arc.write_copy(source, target)
            self.assertEqual(source.read_bytes(), self.retail)
            self.assertEqual(arc.status(target.read_bytes()), "applied")
            read = arc.read_any(target)
            self.assertEqual(read["settings"], tt.TuningSettings(80))
            self.assertEqual(read["flight_arc"], "applied")
            self.assertEqual(receipt["preview"][-1]["deep_cap_yards"], 80)
            self.assertEqual(receipt["target"]["path"], str(target))
            with self.assertRaises(ValueError):
                arc.write_copy(source, source, overwrite=True)
            with self.assertRaises(ValueError):
                arc.write_copy(source, target)

    def test_copy_failure_preserves_existing_destination_and_cleans_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder).resolve()
            source, target = folder / "source.xbe", folder / "target.xbe"
            source.write_bytes(self.retail)
            target.write_bytes(b"keep this output")
            def fail(_source, stage, **_kwargs):
                Path(stage).write_bytes(b"partial")
                raise OSError("synthetic write failure")
            with patch.object(tt, "write_copy", side_effect=fail):
                with self.assertRaises(OSError):
                    arc.write_copy(source, target, overwrite=True)
            self.assertEqual(target.read_bytes(), b"keep this output")
            self.assertEqual(sorted(p.name for p in folder.iterdir()), ["source.xbe", "target.xbe"])

    def test_already_flatter_copy_can_add_an_independent_patch(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder).resolve()
            source, flat, combined = [folder / name for name in ("source.xbe", "flat.xbe", "combined.xbe")]
            source.write_bytes(self.retail)
            arc.write_copy(source, flat)
            receipt = arc.write_copy(flat, combined, catch_slider=True)
            self.assertEqual(receipt["catch_slider"], "applied")
            self.assertEqual(arc.status(combined.read_bytes()), "applied")

    def test_disc_reader_reads_only_the_embedded_extent(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder).resolve() / "sparse.iso"
            offset, length = 32 * 1024 ** 2, len(self.retail)
            with image.open("wb") as stream:
                stream.seek(offset)
                stream.write(self.retail)
                stream.truncate(64 * 1024 ** 2)
            with patch.object(tt, "is_disc_image", return_value=True), \
                    patch.object(tt, "image_xbe_extent", return_value=(offset, length)) as extent, \
                    patch.object(arc.io, "pread", wraps=arc.io.pread) as bounded_read:
                self.assertEqual(arc._payload(image), self.retail)
                self.assertEqual(extent.call_args.args[1], 64 * 1024 ** 2)
                self.assertEqual(bounded_read.call_args.args[1:], (length, offset))

    @unittest.skipUnless(XBE.is_file(), "pinned retail default.xbe extraction is absent")
    def test_real_distance_and_flight_edits_commute(self):
        retail = XBE.read_bytes()
        a, _ = tt.plan_patch(retail, tt.curves_for(tt.TuningSettings(80)))
        a, _ = arc.apply(a)
        b, _ = arc.apply(retail)
        curves = tt.curves_for(tt.TuningSettings(80))
        curves.pop("lobspeed")
        b, _ = tt.plan_patch(b, curves)
        self.assertEqual(a, b)
        decoded = tt.read_curves(a)
        self.assertEqual(tt.preview({key: decoded[key]["points"] for key in tt.EDITABLE_CURVES})[-1].deep_cap_yards, 80)


if __name__ == "__main__":
    unittest.main()
