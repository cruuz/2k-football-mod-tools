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
from mod_editor.core import nfl2k5_catch_slider as catch
from mod_editor.core import nfl2k5_accel_ramp as accel  # noqa: E402
from mod_editor.core import nfl2k5_draft_ai as draft  # noqa: E402
from mod_editor.core import nfl2k5_progression as progression  # noqa: E402
from mod_editor.core import nfl2k5_returner_fix as returner  # noqa: E402
from mod_editor.core import nfl2k5_team_column as team_column  # noqa: E402
from mod_editor.core import nfl2k5_seven_on_seven as seven  # noqa: E402
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


HEADER_SIZE = 0xCC4
TEXT_VA = 0x11000           # synthetic .text: covers the accel hook (0x75CD5), the catch hook and both menu ceilings
TEXT_RAW = 0x2000
TEXT_SIZE = 0x320000        # also covers the franchise draft wish builder at 0x324414
ROOKIE_SECTION = 11         # synthetic .data window (index 12-15 belong to the EDGE / modern / pools fixtures): the Rookie Report scouting-key tables (0xAE1D80..)
ROOKIE_VA = 0xAE1000
ROOKIE_RAW = TEXT_RAW + TEXT_SIZE
ROOKIE_SIZE = 0x1000
CARD_SECTION = 6            # synthetic .rdata window: the Player Card column lists and the Yr descriptor (0x535020..)
CARD_VA = 0x535000
CARD_RAW = ROOKIE_RAW + ROOKIE_SIZE
CARD_SIZE = 0x1000


def _build_synthetic_xbe(curves: dict[str, tuple[tuple[float, float], ...]] | None = None) -> bytes:
    buf = bytearray(TEXT_RAW + TEXT_SIZE)
    buf[0:4] = strength.XBE_MAGIC
    struct.pack_into("<I", buf, 0x104, IMAGE_BASE)
    struct.pack_into("<I", buf, 0x108, HEADER_SIZE)
    struct.pack_into("<II", buf, 0x11C, strength.SECTION_COUNT, IMAGE_BASE + TABLE_OFF)
    for index in range(strength.SECTION_COUNT):
        header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
        fields = [0] * 9 + [b"\x00" * 20]
        if index == 3:
            fields[1] = DATA_VA
            fields[3] = DATA_RAW
            fields[4] = DATA_SIZE
        if index == 0:
            fields[1] = TEXT_VA
            fields[3] = TEXT_RAW
            fields[4] = TEXT_SIZE
        if index == ROOKIE_SECTION:
            fields[1] = ROOKIE_VA
            fields[3] = ROOKIE_RAW
            fields[4] = ROOKIE_SIZE
        if index == CARD_SECTION:
            fields[1] = CARD_VA
            fields[3] = CARD_RAW
            fields[4] = CARD_SIZE
        struct.pack_into(strength.SECTION_TABLE_FIELDS, buf, header, *fields)
    # .data window for the Rookie Report key tables (retail scale words of the K / P / FB structs)
    buf.extend(b"\0" * (CARD_RAW + CARD_SIZE - len(buf)))
    # .rdata window for the Player Card TEAM column: the six column lists and the Yr descriptor it clones
    buf[CARD_RAW + (team_column.YR_DESCRIPTOR_VA - CARD_VA): CARD_RAW + (team_column.YR_DESCRIPTOR_VA - CARD_VA) + team_column.DESCRIPTOR_SIZE] = team_column.RETAIL_YR_DESCRIPTOR
    for _label, list_va, pointers in team_column.COLUMN_LISTS:
        off = CARD_RAW + (list_va + team_column.LIST_POINTERS_OFF - CARD_VA)
        buf[off: off + team_column.LIST_SLOTS * 4] = team_column.list_words(pointers, False)
    for va, retail in ((team_column.HOOK_VA, team_column.RETAIL_HOOK), (team_column.CAVE_VA, team_column.RETAIL_CAVE)):
        off = TEXT_RAW + (va - TEXT_VA)
        buf[off: off + len(retail)] = retail
    for _pos, struct_va, retail_bits in draft.ROOKIE_KEY_SITES:
        struct.pack_into("<I", buf, ROOKIE_RAW + (struct_va + draft.ROOKIE_KEY_SCALE_OFF - ROOKIE_VA), retail_bits)
    # retail bytes at the catch-slider sites: logo region (header), hook and ceilings (.text)
    buf[catch.CAVE_VA - IMAGE_BASE: catch.CAVE_VA - IMAGE_BASE + len(catch.RETAIL_CAVE)] = catch.RETAIL_CAVE
    buf[0xA48: 0xA48 + len(accel._RETAIL_LOGO_FROM_A48)] = accel._RETAIL_LOGO_FROM_A48
    buf[0xAF0: 0xAF0 + len(draft.RETAIL_LOGO_AF0)] = draft.RETAIL_LOGO_AF0
    buf[TEXT_RAW + (draft.BODY_VA - TEXT_VA): TEXT_RAW + (draft.BODY_VA - TEXT_VA) + len(draft.RETAIL_BODY)] = draft.RETAIL_BODY
    buf[TEXT_RAW + (draft.PICK_FN_VA - TEXT_VA): TEXT_RAW + (draft.PICK_FN_VA - TEXT_VA) + draft.PICK_FN_SIZE] = draft.RETAIL_PICK_FN
    buf[TEXT_RAW + (returner.SITE_VA - TEXT_VA): TEXT_RAW + (returner.SITE_VA - TEXT_VA) + returner.SITE_SIZE] = returner.RETAIL_SITE
    buf[TEXT_RAW + (accel.HOOK_VA - TEXT_VA): TEXT_RAW + (accel.HOOK_VA - TEXT_VA) + len(accel.RETAIL_HOOK)] = accel.RETAIL_HOOK
    for va, retail in ((catch.HOOK_VA, catch.RETAIL_HOOK), (catch.CEIL_SITES[0], catch.RETAIL_CEIL), (catch.CEIL_SITES[1], catch.RETAIL_CEIL)):
        off = TEXT_RAW + (va - TEXT_VA)
        buf[off: off + len(retail)] = retail
    for _label, va, retail, _patched in seven.sites():      # the 7-on-7 practice sites (all in .text)
        off = TEXT_RAW + (va - TEXT_VA)
        buf[off: off + len(retail)] = retail
    for name, curve in tt.CURVES.items():
        pairs = (curves or {}).get(name, curve.retail)
        blob = curve.encode(pairs)
        offset = DATA_RAW + (curve.va - DATA_VA)
        buf[offset: offset + len(blob)] = blob
    # arc-by-distance relocation sites: the certificate slot (header) and FUN_002d8970's two operands (.text)
    buf[tt.ARC_TABLE_VA - IMAGE_BASE: tt.ARC_TABLE_VA - IMAGE_BASE + len(tt.RETAIL_ARC_TABLE_SLOT)] = tt.RETAIL_ARC_TABLE_SLOT
    for va, retail in ((tt.LOBSPEED_COUNT_SITE_VA, tt.RETAIL_COUNT_OPERAND), (tt.LOBSPEED_PAIRS_SITE_VA, tt.RETAIL_PAIRS_OPERAND)):
        off = TEXT_RAW + (va - TEXT_VA)
        buf[off: off + len(retail)] = retail
    for index, (raw, size) in ((3, (DATA_RAW, DATA_SIZE)), (0, (TEXT_RAW, TEXT_SIZE)), (ROOKIE_SECTION, (ROOKIE_RAW, ROOKIE_SIZE)), (CARD_SECTION, (CARD_RAW, CARD_SIZE))):
        header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
        buf[header + 36: header + 56] = _section_digest(bytes(buf), raw, size)
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


class CatchSliderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.source = self.work / "default.xbe"
        self.source.write_bytes(_build_synthetic_xbe())

    def test_status_and_apply_round_trip(self) -> None:
        payload = self.source.read_bytes()
        self.assertEqual(catch.status(payload), "retail")
        patched, receipt = catch.apply(payload)
        self.assertEqual(catch.status(patched), "applied")
        self.assertTrue(50 <= receipt["changed_bytes"] <= 80, receipt["changed_bytes"])   # patch bytes + digest bytes that differ
        self.assertEqual(len(patched), len(payload))
        # the cave sits in the header logo region, the hook/ceilings in .text, digest of .text repinned
        self.assertEqual(patched[catch.CAVE_VA - IMAGE_BASE: catch.CAVE_VA - IMAGE_BASE + len(catch.cave_bytes())], catch.cave_bytes())
        sections = strength._sections(patched)
        self.assertEqual(strength.section_digest(patched, sections[0]), sections[0].stored_digest)
        with self.assertRaises(catch.CatchSliderError):
            catch.apply(patched)  # already applied

    def test_foreign_bytes_are_refused(self) -> None:
        payload = bytearray(_build_synthetic_xbe())
        payload[catch.CAVE_VA - IMAGE_BASE] ^= 0xFF
        self.assertEqual(catch.status(bytes(payload)), "foreign")
        with self.assertRaises(catch.CatchSliderError):
            catch.apply(bytes(payload))

    def test_write_copy_combines_curves_and_catch_patch(self) -> None:
        target = self.work / "combo.xbe"
        receipt = tt.write_xbe_copy(self.source, target, settings=tt.TuningSettings(80.0, 0.0, True), catch_slider=True)
        self.assertEqual(receipt["catch_slider"], "applied")
        again = tt.read_xbe(target)
        self.assertEqual(again["settings"], tt.TuningSettings(80.0, 0.0, True))
        self.assertEqual(again["catch_slider"], "applied")
        self.assertEqual(again["curves"]["lobspeed"]["points"], tt.REALISTIC_LOBSPEED)
        # a second write asking only for the (already applied) catch patch is a no-op and refused
        with self.assertRaises(tt.ThrowTuningError):
            tt.write_xbe_copy(target, self.work / "noop.xbe", catch_slider=True)
        # catch patch alone on retail works
        only = self.work / "only.xbe"
        r2 = tt.write_xbe_copy(self.source, only, catch_slider=True)
        self.assertEqual(r2["catch_slider"], "applied")
        self.assertTrue(tt.read_xbe(only)["curves"]["bullet"]["retail"])


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


class AccelRampTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _build_synthetic_xbe()

    def test_status_and_apply_round_trip(self) -> None:
        self.assertEqual(accel.status(self.payload), "retail")
        patched, receipt = accel.apply(self.payload)
        self.assertEqual(accel.status(patched), "applied")
        self.assertTrue(150 <= receipt["changed_bytes"] <= 185, receipt["changed_bytes"])
        self.assertEqual(len(accel.cave_bytes()), 131)
        off = TEXT_RAW + (accel.HOOK_VA - TEXT_VA)
        self.assertEqual(patched[off: off + 6], accel.PATCHED_HOOK)
        self.assertEqual(patched[accel.CAVE_VA - IMAGE_BASE: accel.CAVE_VA - IMAGE_BASE + 131], accel.cave_bytes())
        self.assertEqual(patched[accel.CONST_VA - IMAGE_BASE: accel.CONST_VA - IMAGE_BASE + 20], accel.const_bytes())
        with self.assertRaises(accel.AccelRampError):
            accel.apply(patched)

    def test_foreign_bytes_are_refused(self) -> None:
        payload = bytearray(self.payload)
        payload[accel.CAVE_VA - IMAGE_BASE + 3] ^= 0xFF
        self.assertEqual(accel.status(bytes(payload)), "foreign")
        with self.assertRaises(accel.AccelRampError):
            accel.apply(bytes(payload))

    def test_write_copy_applies_both_caves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(self.payload)
            target = Path(tmp) / "out.xbe"
            report = tt.write_xbe_copy(source, target, settings=tt.TuningSettings(80.0, 0.0, True),
                                       catch_slider=True, accel_ramp=True)
            self.assertEqual(report["catch_slider"], "applied")
            self.assertEqual(report["accel_ramp"], "applied")
            self.assertEqual(tt.read_xbe(target)["accel_ramp"], "applied")
            # the two caves and their constants never overlap inside the logo region
            self.assertLessEqual(catch.CAVE_VA + len(catch.cave_bytes()), 0x10A40)
            self.assertGreaterEqual(accel.CONST_VA, 0x10A48)
            self.assertLess(accel.CAVE_VA + len(accel.cave_bytes()), 0x10CC2)


PROG_SECTIONS = ((4, 0x004F2000, 0x00003000), (5, 0x00521000, 0x00001000))   # .rdata windows: profiles + curves, weights


def _build_progression_xbe() -> bytes:
    """The throw fixture plus two .rdata windows seeded with the retail aging curves and archetype weights
    and a synthetic archetype-profile table (row k -> curve index k mod 14 in every family)."""

    buf = bytearray(_build_synthetic_xbe())
    table = struct.unpack_from("<I", buf, 0x120)[0] - IMAGE_BASE
    raw_cursor = (len(buf) + 0xFFF) & ~0xFFF
    layout = {}
    for index, va, size in PROG_SECTIONS:
        layout[index] = (va, raw_cursor, size)
        raw_cursor += size
    buf.extend(b"\0" * (raw_cursor - len(buf)))
    for index, (va, raw, size) in layout.items():
        header = table + index * strength.SECTION_HEADER_SIZE
        fields = list(struct.unpack_from(strength.SECTION_TABLE_FIELDS, buf, header))
        fields[1], fields[3], fields[4] = va, raw, size
        struct.pack_into(strength.SECTION_TABLE_FIELDS, buf, header, *fields)

    def off(target_va: int) -> int:
        for va, raw, size in layout.values():
            if va <= target_va < va + size:
                return raw + (target_va - va)
        raise AssertionError(f"VA 0x{target_va:x} outside the synthetic windows")

    buf[off(progression.CURVES_VA): off(progression.CURVES_VA) + progression.CURVES_SIZE] = progression.retail_curves()
    weights = progression.retail_weights()
    buf[off(progression.WEIGHTS_VA): off(progression.WEIGHTS_VA) + progression.WEIGHTS_SIZE] = weights
    for k, row in enumerate(progression.decode_weights(weights)):
        p = off(progression.PROFILES_VA) + k * 16
        struct.pack_into("<IBB", buf, p, row["position"], row["profile"], row["sub"])
        buf[p + 6: p + 16] = bytes([k % 14] * 10)
    for index, (va, raw, size) in layout.items():
        header = table + index * strength.SECTION_HEADER_SIZE
        buf[header + 36: header + 56] = _section_digest(bytes(buf), raw, size)
    return bytes(buf)


class ReturnerFixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _build_synthetic_xbe()

    def test_status_and_apply_round_trip(self) -> None:
        self.assertEqual(returner.status(self.payload), "retail")
        patched, receipt = returner.apply(self.payload)
        self.assertEqual(returner.status(patched), "applied")
        self.assertEqual(receipt["sections_repinned"], [0])
        site = TEXT_RAW + (returner.SITE_VA - TEXT_VA)
        self.assertEqual(patched[site: site + returner.SITE_SIZE], returner.site_bytes())
        self.assertEqual(len(returner.site_bytes()), returner.SITE_SIZE)
        # the loop still hands off to the retail re-rank call and continues the team loop
        body = returner.site_bytes()
        code_end = receipt["code_bytes"] - 34
        self.assertEqual(body[code_end - 5: code_end], b"\xe9" + struct.pack("<i", returner.SITE_END_VA - (returner.SITE_VA + code_end)))
        self.assertEqual(body[code_end - 10: code_end - 5], b"\xe8" + struct.pack("<i", returner.FN_FINISH_DEPTH - (returner.SITE_VA + code_end - 5)))
        with self.assertRaises(returner.ReturnerFixError):
            returner.apply(patched)

    def test_masks_keep_quarterbacks_kickers_and_linemen_off_the_return_units(self) -> None:
        masks = returner.mask_bytes()
        kr, pr = masks[:17], masks[17:]
        for banned in ("QB", "K", "P", "C", "G", "T", "DT", "DE", "OLB", "ILB", "TE"):
            i = returner.POSITIONS.index(banned)
            self.assertEqual((kr[i], pr[i]), (0, 0), banned)
        self.assertEqual(kr[returner.POSITIONS.index("WR")], 1)
        self.assertEqual(pr[returner.POSITIONS.index("CB")], 1)
        self.assertEqual(pr[returner.POSITIONS.index("FB")], 0)
        # the masks are the last live bytes of the patched region, right after the code
        body = returner.site_bytes()
        live = len(body) - body.count(b"\xcc")
        self.assertEqual(body[live - 34: live], masks)

    def test_foreign_bytes_are_refused(self) -> None:
        payload = bytearray(self.payload)
        payload[TEXT_RAW + (returner.SITE_VA - TEXT_VA) + 40] ^= 0xFF
        self.assertEqual(returner.status(bytes(payload)), "foreign")
        with self.assertRaises(returner.ReturnerFixError):
            returner.apply(bytes(payload))


class ProgressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _build_progression_xbe()

    def test_embedded_retail_tables_decode(self) -> None:
        curves = progression.decode_curves(progression.retail_curves())
        for family, _va, count in progression.TABLES:
            self.assertEqual(len(curves[family]), count)
            for curve in curves[family]:
                self.assertEqual(len(curve), 21)
        self.assertEqual(curves["speed_agility"][5][:6], [4, 4, 5, 5, 6, 6])
        rows = progression.decode_weights(progression.retail_weights())
        self.assertEqual(len(rows), 162)
        self.assertEqual(sum(r["weight"] for r in rows if r["position"] == 0), 100)   # QB: two profiles x 50
        self.assertEqual(sum(r["weight"] for r in rows if r["position"] == 1), 50)    # K: one profile

    def test_reshape_keeps_rookies_and_bends_the_curve(self) -> None:
        curve = [0] * 21
        out = progression.reshape_curve(curve, "routes_passrush_coverage")
        self.assertEqual(out[0], 0)
        self.assertEqual(out[5], 6)                      # full growth by year 5
        self.assertEqual(out[10], 6)                     # the plateau
        self.assertEqual(out[15], 1)                     # 5 extra years of decline at 1/yr
        self.assertTrue(all(-127 <= v <= 127 for v in progression.reshape_curve([120] * 21, "consistency")))
        self.assertEqual(progression.reshape_curve([3] * 21, "hidden_4f"), [3] * 21)

    def test_spread_preserves_position_totals(self) -> None:
        retail = progression.retail_weights()
        rows = progression.decode_weights(retail)
        profiles = bytearray(162 * 16)
        for k, row in enumerate(rows):
            struct.pack_into("<IBB", profiles, k * 16, row["position"], row["profile"], row["sub"])
            profiles[k * 16 + 6: k * 16 + 16] = bytes([k % 14] * 10)
        tables = progression.reshape_curves(progression.decode_curves(progression.retail_curves()))
        out = progression.spread_weights(rows, bytes(profiles), tables)
        for pos in range(17):
            before = sum(r["weight"] for r in rows if r["position"] == pos)
            after = sum(r["weight"] for r in out if r["position"] == pos)
            self.assertEqual(before, after, pos)
        self.assertTrue(all(r["weight"] >= 1 for r in out))
        self.assertNotEqual([r["weight"] for r in rows], [r["weight"] for r in out])

    def test_status_and_apply_round_trip(self) -> None:
        self.assertEqual(progression.status(self.payload), "retail")
        patched, receipt = progression.apply(self.payload)
        self.assertEqual(progression.status(patched), "applied")
        self.assertEqual(receipt["sections_repinned"], [4, 5])
        self.assertEqual([e["label"] for e in receipt["edits"]], ["aging_curves", "archetype_weights"])
        with self.assertRaises(progression.ProgressionError):
            progression.apply(patched)
        # year-0 bytes (draft-day ratings) are untouched in every curve
        before = progression.decode_curves(progression.retail_curves())
        off = progression._offset(patched, progression.CURVES_VA)
        after = progression.decode_curves(patched[off: off + progression.CURVES_SIZE])
        for family in before:
            for a, b in zip(before[family], after[family]):
                self.assertEqual(a[0], b[0])

    def test_foreign_and_missing_tables_are_refused(self) -> None:
        self.assertEqual(progression.status(_build_synthetic_xbe()), "foreign")   # no .rdata windows
        payload = bytearray(self.payload)
        payload[progression._offset(bytes(payload), progression.CURVES_VA) + 30] ^= 0x7F
        self.assertEqual(progression.status(bytes(payload)), "foreign")

    def test_write_copy_applies_returner_and_progression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(self.payload)
            target = Path(tmp) / "patched.xbe"
            receipt = tt.write_xbe_copy(source, target, returner_fix=True, progression=True)
            self.assertEqual(receipt["returner_fix"], "applied")
            self.assertEqual(receipt["progression"], "applied")
            self.assertIn("returner_fix_patch", receipt)
            self.assertIn("progression_patch", receipt)
            report = tt.read_xbe(target)
            self.assertEqual((report["returner_fix"], report["progression"]), ("applied", "applied"))
            self.assertEqual(report["draft_ai"], "retail")


class DraftAiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _build_synthetic_xbe()

    def test_status_and_apply_round_trip(self) -> None:
        self.assertEqual(draft.status(self.payload), "retail")
        patched, receipt = draft.apply(self.payload)
        self.assertEqual(draft.status(patched), "applied")
        self.assertEqual(receipt["sections_repinned"], [0, ROOKIE_SECTION])
        for pos, struct_va, retail_bits in draft.ROOKIE_KEY_SITES:
            off = ROOKIE_RAW + (struct_va + draft.ROOKIE_KEY_SCALE_OFF - ROOKIE_VA)
            retail_scale = struct.unpack("<f", struct.pack("<I", retail_bits))[0]
            self.assertAlmostEqual(struct.unpack_from("<f", patched, off)[0], retail_scale / draft.ROOKIE_KEY_SCALE[pos], places=5, msg=pos)
            self.assertEqual(struct.unpack_from("<I", self.payload, off)[0], retail_bits, pos)
        self.assertEqual(receipt["rookie_key_scale"], {"FB": 0.6, "K": 0.3, "P": 0.3})
        cave = draft.cave_bytes()
        self.assertLessEqual(draft.CAVE_VA + len(cave), 0x10CC2)
        self.assertGreaterEqual(draft.CAVE_VA, 0x10B40)
        self.assertEqual(patched[draft.CAVE_VA - IMAGE_BASE: draft.CAVE_VA - IMAGE_BASE + len(cave)], cave)
        self.assertEqual(patched[draft.VALUE_VA - IMAGE_BASE: draft.VALUE_VA - IMAGE_BASE + 80], draft.const_bytes())
        body = TEXT_RAW + (draft.BODY_VA - TEXT_VA)
        self.assertEqual(patched[body: body + 5], b"\xe9" + struct.pack("<i", draft.CAVE_VA - (draft.BODY_VA + 5)))
        head, tail = draft.pick_fn_bytes()
        self.assertEqual(len(head), draft.PICK_FN_SIZE)
        self.assertLessEqual(5 + len(tail), len(draft.RETAIL_BODY))
        self.assertEqual(patched[body + 5: body + 5 + len(tail)], tail)
        pick = TEXT_RAW + (draft.PICK_FN_VA - TEXT_VA)
        self.assertEqual(patched[pick: pick + draft.PICK_FN_SIZE], head)
        # the head ends by jumping into the tail; the tail returns to the caller
        head_code = head[:draft.PICK_CONST_OFF].rstrip(b"\xcc")
        self.assertEqual(head_code[-5:], b"\xe9" + struct.pack("<i", draft.PICK_TAIL_VA - (draft.PICK_FN_VA + len(head_code))))
        self.assertEqual(tail[-1:], b"\xc3")
        self.assertEqual(head[draft.PICK_CONST_OFF: draft.PICK_CONST_OFF + 8],
                         struct.pack("<2f", draft.NEED_STEP, draft.PICK_JITTER / 256.0))
        with self.assertRaises(draft.DraftAiError):
            draft.apply(patched)

    def test_value_table_matches_position_order(self) -> None:
        self.assertEqual(len(draft.POSITIONS), 17)
        self.assertEqual(draft.POSITIONS[0], "QB")
        self.assertEqual(draft.POSITIONS[16], "DE")
        self.assertLess(draft.VALUE["K"], draft.VALUE["RB"])
        self.assertGreater(draft.VALUE["T"], draft.VALUE["G"])

    def test_foreign_bytes_are_refused(self) -> None:
        payload = bytearray(self.payload)
        payload[draft.CAVE_VA - IMAGE_BASE + 7] ^= 0xFF
        self.assertEqual(draft.status(bytes(payload)), "foreign")

    def test_write_copy_applies_all_three_caves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(self.payload)
            target = Path(tmp) / "out.xbe"
            report = tt.write_xbe_copy(source, target, catch_slider=True, accel_ramp=True, draft_ai=True)
            self.assertEqual(report["draft_ai"], "applied")
            self.assertEqual(report["accel_ramp"], "applied")
            self.assertEqual(report["catch_slider"], "applied")
            self.assertEqual(tt.read_xbe(target)["draft_ai"], "applied")


if __name__ == "__main__":
    unittest.main()


class ArcByDistanceTests(unittest.TestCase):
    """The short game stays retail, 45..60-yard lobs hang high, 63+ keep the flat bomb; the table is
    relocated (eight points in the certificate slot, FUN_002d8970's operands repointed) and the read
    side recognises both the relocation and the superseded five-point in-place profile."""

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.source = self.work / "default.xbe"
        self.source.write_bytes(_build_synthetic_xbe())

    def test_profile_is_retail_through_forty_yards_then_the_band_then_the_flat_bomb(self) -> None:
        profile = tt.ARC_BY_DISTANCE_LOBSPEED
        self.assertEqual(profile[:5], tt.CURVES["lobspeed"].retail)      # points 1..5 ARE the retail table
        retail = tt.CURVES["lobspeed"].retail
        for yards in (2, 6, 8, 10, 12.5, 15, 20, 25, 30, 35, 38, 40):
            self.assertAlmostEqual(tt.interpolate(profile, yards), tt.interpolate(retail, yards), places=6, msg=yards)
        speed = dict(profile)
        self.assertEqual(speed[45.0], tt.HIGH_ARC_BAND_SPEED_YD_S)
        self.assertEqual(speed[60.0], tt.HIGH_ARC_BAND_SPEED_YD_S)
        self.assertEqual(tt.interpolate(profile, 52.0), tt.HIGH_ARC_BAND_SPEED_YD_S)
        self.assertGreater(speed[63.0], tt.RETAIL_LOB_SPEED_YD_S)
        self.assertEqual(tt.interpolate(profile, 80.0), 21.0)
        self.assertEqual(tt.interpolate(profile, 10.0), 12.0)              # the point the five-point table lost
        # it fills the certificate slot exactly and never overlaps the widescreen cave
        self.assertEqual(len(tt.ARC_TABLE_CURVE.encode(profile)), len(tt.RETAIL_ARC_TABLE_SLOT))
        from mod_editor.core import nfl2k5_widescreen as ws
        self.assertGreaterEqual(tt.ARC_TABLE_VA, ws.CAVE_VA + len(ws.cave_bytes()))
        self.assertLessEqual(tt.ARC_TABLE_VA + len(tt.RETAIL_ARC_TABLE_SLOT), ws.CAVE_END_VA)

    def test_curves_for_keeps_the_in_place_table_and_effective_lobspeed_is_the_profile(self) -> None:
        settings = tt.TuningSettings(80.0, 0.0, True, True)
        curves = tt.curves_for(settings)
        self.assertEqual(curves["lobspeed"], tt.REALISTIC_LOBSPEED)        # in place: what the other flags say
        self.assertEqual(tt.effective_lobspeed(settings, curves), tt.ARC_BY_DISTANCE_LOBSPEED)
        self.assertEqual(tt.effective_lobspeed(tt.TuningSettings(80.0, 0.0, True)), tt.REALISTIC_LOBSPEED)
        self.assertGreaterEqual(curves["lob"][-1][1], 80.0)
        plain = tt.curves_for(tt.TuningSettings(55.0, 0.0, False, True))
        self.assertEqual(plain["lobspeed"], tt.CURVES["lobspeed"].retail)

    def test_apply_relocates_the_table_and_repoints_the_reader(self) -> None:
        payload = self.source.read_bytes()
        self.assertEqual(tt.arc_table_status(payload), "retail")
        patched, receipt = tt.apply_arc_table(payload)
        self.assertEqual(tt.arc_table_status(patched), "applied")
        self.assertEqual([e["label"] for e in receipt["edits"]], ["arc_table", "lobspeed_count_operand", "lobspeed_pairs_operand"])
        self.assertEqual(receipt["sections_repinned"], [0])
        slot = patched[tt.ARC_TABLE_VA - IMAGE_BASE: tt.ARC_TABLE_VA - IMAGE_BASE + len(tt.RETAIL_ARC_TABLE_SLOT)]
        self.assertEqual(slot, tt.ARC_TABLE_CURVE.encode(tt.ARC_BY_DISTANCE_LOBSPEED))
        self.assertEqual(struct.unpack_from("<I", slot, 0)[0], 8)
        count = TEXT_RAW + (tt.LOBSPEED_COUNT_SITE_VA - TEXT_VA)
        pairs = TEXT_RAW + (tt.LOBSPEED_PAIRS_SITE_VA - TEXT_VA)
        self.assertEqual(patched[count: count + 6], b"\x8b\x15" + struct.pack("<I", tt.ARC_TABLE_VA))
        self.assertEqual(patched[pairs: pairs + 5], b"\xb9" + struct.pack("<I", tt.ARC_TABLE_VA + 4))
        # the in-place table is untouched by the relocation
        off = DATA_RAW + (tt.CURVES["lobspeed"].va - DATA_VA)
        self.assertEqual(patched[off: off + tt.CURVES["lobspeed"].size], tt.CURVES["lobspeed"].retail_bytes)
        sections = strength._sections(patched)
        self.assertEqual(strength.section_digest(patched, sections[0]), sections[0].stored_digest)
        self.assertEqual(tt.read_arc_table(patched)["points"], tt.ARC_BY_DISTANCE_LOBSPEED)
        with self.assertRaises(tt.ThrowTuningError):
            tt.apply_arc_table(patched)
        # foreign bytes anywhere in the three sites are refused
        buf = bytearray(payload)
        buf[tt.ARC_TABLE_VA - IMAGE_BASE] ^= 0xFF
        self.assertEqual(tt.arc_table_status(bytes(buf)), "foreign")
        buf = bytearray(payload)
        buf[count + 2] ^= 0x01
        self.assertEqual(tt.arc_table_status(bytes(buf)), "foreign")
        with self.assertRaises(tt.ThrowTuningError):
            tt.apply_arc_table(bytes(buf))

    def test_write_copy_carries_the_relocation_and_reads_back(self) -> None:
        target = self.work / "arc.xbe"
        receipt = tt.write_xbe_copy(self.source, target, settings=tt.TuningSettings(80.0, 0.0, True, True))
        self.assertEqual(receipt["arc_table"], "applied")
        self.assertIn("arc_table_patch", receipt)
        again = tt.read_xbe(target)
        self.assertEqual(again["settings"], tt.TuningSettings(80.0, 0.0, True, True))
        self.assertEqual(again["arc_table"]["state"], "applied")
        self.assertEqual(again["curves"]["lobspeed"]["points"], tt.REALISTIC_LOBSPEED)
        # the receipt preview is computed with the effective (relocated) table: a 52-yd ball hangs
        deep = [row for row in receipt["preview"] if row["deep_cap_yards"] >= 60.0]
        self.assertTrue(deep)
        self.assertAlmostEqual(deep[-1]["hang_seconds"], 80.0 / 21.0, places=2)
        # arc by distance alone at the retail ceiling is a real change (the relocation), not a no-op
        only = self.work / "arc55.xbe"
        r2 = tt.write_xbe_copy(self.source, only, settings=tt.TuningSettings(55.0, 0.0, False, True))
        self.assertEqual(r2["arc_table"], "applied")
        self.assertEqual(r2["changes"], [])
        self.assertTrue(tt.read_xbe(only)["curves"]["lobspeed"]["retail"])
        self.assertEqual(tt.read_xbe(only)["settings"], tt.TuningSettings(55.0, 0.0, False, True))
        # asking again for the same thing on the result is refused as a no-op
        with self.assertRaises(tt.ThrowTuningError):
            tt.write_xbe_copy(only, self.work / "noop.xbe", settings=tt.TuningSettings(55.0, 0.0, False, True))

    def test_read_side_recognises_the_relocation_and_the_legacy_profile(self) -> None:
        curves = tt.curves_for(tt.TuningSettings(80.0, 0.0, False, True))
        read = {name: {"points": pts} for name, pts in curves.items()}
        self.assertFalse(tt.infer_settings(read).arc_by_distance)                 # in place alone says nothing
        inferred = tt.infer_settings(read, "applied")
        self.assertTrue(inferred.arc_by_distance)
        self.assertEqual(inferred.arc, 0.0)
        self.assertFalse(inferred.realistic_flight)
        self.assertAlmostEqual(inferred.max_deep_yards, 80.0, places=1)
        legacy = dict(read)
        legacy["lobspeed"] = {"points": tt.LEGACY_ARC_BY_DISTANCE_LOBSPEED}
        old = tt.infer_settings(legacy, "retail")
        self.assertTrue(old.arc_by_distance)
        self.assertEqual(old.arc, 0.0)
        self.assertFalse(old.realistic_flight)

    def test_default_settings_do_not_pick_the_profile(self) -> None:
        self.assertFalse(tt.TuningSettings().arc_by_distance)
        self.assertEqual(tt.curves_for(tt.TuningSettings(80.0, 0.0, True))["lobspeed"], tt.REALISTIC_LOBSPEED)
        self.assertEqual(tt.arc_table_status(self.source.read_bytes()), "retail")
        target = self.work / "plain.xbe"
        tt.write_xbe_copy(self.source, target, settings=tt.TuningSettings(80.0, 0.0, True))
        self.assertEqual(tt.arc_table_status(target.read_bytes()), "retail")
