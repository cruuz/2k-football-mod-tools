"""The throw-tuning writer must stay pattern-driven, fail-closed, copy-only.

Fixtures are synthetic: a minimal XBE with a valid 22-section table whose one
data section carries the five retail curve tables at their retail virtual
addresses, plus a correct section digest.  No game file is touched; a
retail-XBE / real-disc smoke test runs only when the private copies exist.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402

IMAGE_BASE = strength.IMAGE_BASE
TABLE_OFF = 0x200
DATA_VA = 0x50B000
DATA_RAW = 0x1000
DATA_SIZE = 0x1000
RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")
PRIVATE_IMAGE = Path.home() / "2K5 Mod Studio Builds" / "NFL 2K5 Create-a-Play Vick80.xiso.iso"


def _section_digest(payload: bytes, raw: int, raw_size: int) -> bytes:
    return hashlib.sha1(  # nosec B324 - XBE section scheme, not security
        struct.pack("<I", raw_size) + payload[raw: raw + raw_size]
    ).digest()


def _build_synthetic_xbe(curves: dict[str, tuple[tuple[float, float], ...]] | None = None) -> bytes:
    buf = bytearray(DATA_RAW + DATA_SIZE)
    buf[0:4] = strength.XBE_MAGIC
    struct.pack_into("<I", buf, 0x104, IMAGE_BASE)
    struct.pack_into("<II", buf, 0x11C, strength.SECTION_COUNT, IMAGE_BASE + TABLE_OFF)
    for index in range(strength.SECTION_COUNT):
        header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
        fields = [0] * 9 + [b"\x00" * 20]
        if index == 3:
            fields[1] = DATA_VA
            fields[3] = DATA_RAW
            fields[4] = DATA_SIZE
        struct.pack_into(strength.SECTION_TABLE_FIELDS, buf, header, *fields)
    for name, curve in tt.CURVES.items():
        pairs = (curves or {}).get(name, curve.retail)
        blob = curve.encode(pairs)
        offset = DATA_RAW + (curve.va - DATA_VA)
        buf[offset: offset + len(blob)] = blob
    digest = _section_digest(bytes(buf), DATA_RAW, DATA_SIZE)
    header = TABLE_OFF + 3 * strength.SECTION_HEADER_SIZE
    buf[header + 36: header + 56] = digest
    return bytes(buf)


class CurveMathTests(unittest.TestCase):
    def test_interpolator_clamps_and_is_linear(self) -> None:
        pairs = ((0.0, 10.0), (0.5, 20.0), (1.0, 40.0))
        self.assertEqual(tt.interpolate(pairs, -1.0), 10.0)
        self.assertEqual(tt.interpolate(pairs, 0.25), 15.0)
        self.assertEqual(tt.interpolate(pairs, 0.75), 30.0)
        self.assertEqual(tt.interpolate(pairs, 2.0), 40.0)

    def test_retail_settings_reproduce_retail_tables(self) -> None:
        curves = tt.curves_for(tt.TuningSettings())
        for name in tt.EDITABLE_CURVES:
            self.assertEqual(curves[name], tt.CURVES[name].retail, name)

    def test_eighty_yard_scale_matches_the_witnessed_disc(self) -> None:
        curves = tt.curves_for(tt.TuningSettings(80.0, 0.4))
        self.assertEqual(curves["bullet"], ((0.0, 25.0), (0.65, 38.0), (0.85, 52.0), (0.95, 66.0), (1.0, 80.0)))
        self.assertEqual(curves["lob"][-2:], ((0.95, 72.0), (1.0, 80.0)))
        self.assertEqual(curves["lobspeed"][-2:], ((55.0, 20.0), (80.0, 16.0)))

    def test_lob_stays_at_or_above_bullet_everywhere_that_matters(self) -> None:
        for ceiling in (55.0, 60.0, 72.5, 80.0, 90.0, 100.0):
            for arc in (0.0, 0.25, 1.0):
                curves = tt.curves_for(tt.TuningSettings(ceiling, arc))
                for arm in (0.5, 0.65, 0.85, 0.9, 0.95, 0.99, 1.0):
                    self.assertGreaterEqual(
                        tt.interpolate(curves["lob"], arm) + 1e-6,
                        tt.interpolate(curves["bullet"], arm), (ceiling, arc, arm),
                    )
                self.assertEqual(curves["bullet"][-1][1], ceiling)
                scaled_top = 75.0 + 5.0 * (ceiling - 55.0) / 25.0
                self.assertEqual(curves["lob"][-1][1], max(ceiling, round(scaled_top, 3)))

    def test_scale_is_monotonic_in_arm_and_in_ceiling(self) -> None:
        previous = None
        for ceiling in (55.0, 65.0, 75.0, 85.0, 95.0, 100.0):
            curves = tt.curves_for(tt.TuningSettings(ceiling, 0.0))
            ys = [y for _x, y in curves["bullet"]]
            self.assertEqual(ys, sorted(ys))
            if previous is not None:
                for a, b in zip(previous, ys):
                    self.assertLessEqual(a, b)
            previous = ys
        # a mid-league arm gains a little, an elite arm gains the ceiling
        eighty = tt.curves_for(tt.TuningSettings(80.0, 0.0))
        self.assertAlmostEqual(tt.interpolate(eighty["bullet"], 0.85), 52.0)
        self.assertAlmostEqual(tt.interpolate(eighty["bullet"], 0.70), 41.5)

    def test_arc_slider_shapes_only_the_speed_table(self) -> None:
        flat = tt.curves_for(tt.TuningSettings(80.0, 0.0))
        self.assertEqual(flat["lobspeed"], tt.CURVES["lobspeed"].retail)
        full = tt.curves_for(tt.TuningSettings(80.0, 1.0))
        self.assertEqual(full["lobspeed"][-1], (80.0, 10.0))
        self.assertEqual(full["bullet"], flat["bullet"])
        with self.assertRaises(tt.ThrowTuningError):
            tt.curves_for(tt.TuningSettings(80.0, 1.5))
        with self.assertRaises(tt.ThrowTuningError):
            tt.curves_for(tt.TuningSettings(40.0, 0.0))

    def test_preview_physics(self) -> None:
        retail = tt.preview({n: tt.CURVES[n].retail for n in tt.EDITABLE_CURVES})
        top = retail[-1]
        self.assertEqual(top.arm, 1.0)
        self.assertEqual(top.deep_cap_yards, 55.0)
        self.assertAlmostEqual(top.hang_seconds, 2.75, places=2)
        arc = tt.preview(tt.curves_for(tt.TuningSettings(80.0, 0.4)))[-1]
        self.assertEqual(arc.deep_cap_yards, 80.0)
        self.assertAlmostEqual(arc.hang_seconds, 5.0, places=2)
        self.assertGreater(arc.apex_yards, top.apex_yards * 3)

    def test_validate_pairs_refuses_bad_shapes(self) -> None:
        curve = tt.CURVES["bullet"]
        with self.assertRaises(tt.ThrowTuningError):
            tt.validate_pairs(curve, ((0.0, 25.0), (1.0, 80.0)))
        with self.assertRaises(tt.ThrowTuningError):
            tt.validate_pairs(curve, ((0.0, 25.0), (0.9, 35.0), (0.85, 45.0), (0.95, 50.0), (1.0, 55.0)))
        with self.assertRaises(tt.ThrowTuningError):
            tt.validate_pairs(curve, ((0.0, 25.0), (0.65, 35.0), (0.85, 45.0), (0.95, 50.0), (1.5, 55.0)))


class SyntheticXbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.source = self.work / "default.xbe"
        self.source.write_bytes(_build_synthetic_xbe())

    def test_read_finds_every_table_at_its_section_offset(self) -> None:
        report = tt.read_xbe(self.source)
        self.assertEqual(report["schema"], tt.READ_SCHEMA)
        self.assertFalse(report["matches_retail_sha256"])
        for name, curve in tt.CURVES.items():
            entry = report["curves"][name]
            self.assertTrue(entry["retail"], name)
            self.assertEqual(entry["points"], curve.retail, name)
            self.assertEqual(entry["file_offset"], f"0x{DATA_RAW + curve.va - DATA_VA:x}")
        self.assertEqual(report["settings"], tt.TuningSettings(55.0, 0.0))

    def test_write_copy_patches_only_tables_and_digest(self) -> None:
        target = self.work / "patched.xbe"
        receipt = tt.write_xbe_copy(self.source, target, settings=tt.TuningSettings(80.0, 0.4))
        original = self.source.read_bytes()
        patched = target.read_bytes()
        self.assertEqual(len(original), len(patched))
        self.assertEqual(receipt["schema"], tt.WRITE_SCHEMA)
        self.assertEqual({c["curve"] for c in receipt["changes"]}, {"bullet", "lob", "lobspeed"})
        self.assertEqual(len(receipt["section_digests"]), 1)
        changed = {i for i, (a, b) in enumerate(zip(original, patched)) if a != b}
        allowed: set[int] = set()
        for name in tt.EDITABLE_CURVES:
            offset = DATA_RAW + tt.CURVES[name].va - DATA_VA
            allowed.update(range(offset, offset + tt.CURVES[name].size))
        header = TABLE_OFF + 3 * strength.SECTION_HEADER_SIZE
        allowed.update(range(header + 36, header + 56))
        self.assertTrue(changed <= allowed)
        self.assertEqual(receipt["changed_byte_count"], len(changed))
        again = tt.read_xbe(target)
        self.assertEqual(again["settings"], tt.TuningSettings(80.0, 0.4))
        self.assertFalse(again["curves"]["bullet"]["retail"])
        self.assertTrue(again["curves"]["anim"]["retail"])
        self.assertTrue(again["curves"]["bulletspeed"]["retail"])
        sections = strength._sections(patched)
        self.assertEqual(strength.section_digest(patched, sections[3]), sections[3].stored_digest)

    def test_edited_copy_can_be_read_and_re_edited(self) -> None:
        first = self.work / "first.xbe"
        second = self.work / "second.xbe"
        tt.write_xbe_copy(self.source, first, settings=tt.TuningSettings(80.0, 0.4))
        tt.write_xbe_copy(first, second, settings=tt.TuningSettings(65.0, 0.0))
        report = tt.read_xbe(second)
        self.assertEqual(report["settings"], tt.TuningSettings(65.0, 0.0))
        self.assertEqual(report["curves"]["lobspeed"]["points"], tt.CURVES["lobspeed"].retail)

    def test_no_change_is_refused(self) -> None:
        with self.assertRaises(tt.ThrowTuningError):
            tt.write_xbe_copy(self.source, self.work / "same.xbe", settings=tt.TuningSettings())
        self.assertFalse((self.work / "same.xbe").exists())

    def test_source_is_never_the_target(self) -> None:
        with self.assertRaises(tt.ThrowTuningError):
            tt.write_xbe_copy(self.source, self.source, settings=tt.TuningSettings(80.0, 0.0), overwrite=True)
        self.assertEqual(self.source.read_bytes(), _build_synthetic_xbe())

    def test_existing_target_needs_overwrite(self) -> None:
        target = self.work / "exists.xbe"
        target.write_bytes(b"old")
        with self.assertRaises(tt.ThrowTuningError):
            tt.write_xbe_copy(self.source, target, settings=tt.TuningSettings(80.0, 0.0))
        self.assertEqual(target.read_bytes(), b"old")
        tt.write_xbe_copy(self.source, target, settings=tt.TuningSettings(80.0, 0.0), overwrite=True)
        self.assertEqual(tt.read_xbe(target)["settings"].max_deep_yards, 80.0)

    def test_symlink_source_is_refused(self) -> None:
        link = self.work / "link.xbe"
        try:
            link.symlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(tt.ThrowTuningError):
            tt.read_xbe(link)

    def test_tampered_table_is_refused(self) -> None:
        payload = bytearray(_build_synthetic_xbe())
        offset = DATA_RAW + tt.CURVES["bullet"].va - DATA_VA
        struct.pack_into("<I", payload, offset, 9)  # bogus count word
        bad = self.work / "bad.xbe"
        bad.write_bytes(bytes(payload))
        with self.assertRaises(tt.ThrowTuningError):
            tt.read_xbe(bad)

    def test_explicit_curves_route(self) -> None:
        target = self.work / "explicit.xbe"
        pairs = ((0.0, 25.0), (0.65, 35.0), (0.85, 45.0), (0.95, 60.0), (1.0, 70.0))
        receipt = tt.write_xbe_copy(self.source, target, curves={"bullet": pairs})
        self.assertEqual(receipt["verified_curves"]["bullet"], pairs)
        with self.assertRaises(tt.ThrowTuningError):
            tt.write_xbe_copy(self.source, self.work / "x.xbe", curves={"anim": tt.CURVES["anim"].retail})

    def test_is_disc_image_recognises_xbe(self) -> None:
        self.assertFalse(tt.is_disc_image(self.source))
        self.assertFalse(tt.is_disc_image(self.work / "missing"))


@unittest.skipUnless(RETAIL_XBE.exists(), "private retail XBE missing")
class RetailXbeSmokeTests(unittest.TestCase):
    def test_retail_reads_as_retail_and_patches_cleanly(self) -> None:
        report = tt.read_xbe(RETAIL_XBE)
        self.assertTrue(report["matches_retail_sha256"])
        self.assertTrue(all(entry["retail"] for entry in report["curves"].values()))
        with tempfile.TemporaryDirectory() as work:
            target = Path(work) / "default_patched.xbe"
            receipt = tt.write_xbe_copy(RETAIL_XBE, target, settings=tt.TuningSettings(80.0, 0.4))
            self.assertEqual(receipt["changed_byte_count"], receipt["changed_byte_count"])
            self.assertEqual(tt.read_xbe(target)["settings"], tt.TuningSettings(80.0, 0.4))


@unittest.skipUnless(PRIVATE_IMAGE.exists(), "private patched disc image missing")
class PrivateImageSmokeTests(unittest.TestCase):
    def test_image_read_reports_the_witnessed_curves(self) -> None:
        report = tt.read_image(PRIVATE_IMAGE)
        self.assertEqual(report["container"], "xiso")
        self.assertEqual(report["settings"], tt.TuningSettings(80.0, 0.4))
        self.assertTrue(tt.is_disc_image(PRIVATE_IMAGE))


if __name__ == "__main__":
    unittest.main()
