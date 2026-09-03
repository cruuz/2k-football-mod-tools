"""The kicking-rules patch must stay pattern-driven, fail-closed and byte-exact.

Fixtures are synthetic: a minimal XBE with a valid 22-section table whose `.text` section
carries the retail bytes at every hook site plus the dead function that hosts the cave, with
a correct section digest.  No game file is touched; a retail-XBE smoke test runs only when the
private copy exists.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_kick_rules as kick  # noqa: E402

IMAGE_BASE = strength.IMAGE_BASE
TABLE_OFF = 0x200
HEADER_SIZE = 0xCC4
TEXT_VA = 0x11000
TEXT_RAW = 0x2000
TEXT_SIZE = 0x320000
RDATA_VA = 0x4E3AE0          # the retail .rdata VA, so the curve tables land at their real VAs
RDATA_RAW = TEXT_RAW + TEXT_SIZE
RDATA_SIZE = 0x30000
RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")


def _section_digest(payload: bytes, raw: int, raw_size: int) -> bytes:
    return hashlib.sha1(  # nosec B324 - XBE section scheme, not security
        struct.pack("<I", raw_size) + payload[raw: raw + raw_size]
    ).digest()


def _text_off(va: int) -> int:
    return TEXT_RAW + (va - TEXT_VA)


def _rdata_off(va: int) -> int:
    return RDATA_RAW + (va - RDATA_VA)


def _retail_sites() -> list[tuple[int, bytes]]:
    sites = [(kick.CAVE_VA, kick.RETAIL_CAVE), (kick.TOUCHBACK_SITE_VA, kick.RETAIL_FMUL_TOUCHBACK),
             (kick.TRY_RECORD_SITE_VA, kick.RETAIL_FMUL_PAT), (kick.PAT_STORE_SITE_VA, kick.RETAIL_CALL_STORE),
             (kick.PAT_PICK_SITE_VA, kick.RETAIL_CALL_PICK), (kick.PAT_AUDIBLE_SITE_VA, kick.RETAIL_CALL_AUDIBLE),
             (kick.PAT_LINEUP_ENTRY_VA, kick.RETAIL_LINEUP_ENTRY)]
    for _label, va, const, _kind in kick.KICKOFF_SITES:
        sites.append((va, b"\xd8\x0d" + struct.pack("<I", const)))
    for _label, va, opcode, table_va in kick.CPU_RANGE_SITES:
        sites.append((va, opcode + struct.pack("<I", table_va)))
    return sites


def _retail_rdata_sites() -> list[tuple[int, bytes]]:
    return [(kick.FG_METER_TABLE_VA, kick.RETAIL_FG_METER_BYTES), (kick.FG_POWER_TABLE_VA, kick.RETAIL_FG_POWER_BYTES)]


def _build_synthetic_xbe() -> bytes:
    buf = bytearray(RDATA_RAW + RDATA_SIZE)
    buf[0:4] = strength.XBE_MAGIC
    struct.pack_into("<I", buf, 0x104, IMAGE_BASE)
    struct.pack_into("<I", buf, 0x108, HEADER_SIZE)
    struct.pack_into("<II", buf, 0x11C, strength.SECTION_COUNT, IMAGE_BASE + TABLE_OFF)
    for index in range(strength.SECTION_COUNT):
        header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
        fields = [0] * 9 + [b"\x00" * 20]
        if index == 0:
            fields[1] = TEXT_VA
            fields[3] = TEXT_RAW
            fields[4] = TEXT_SIZE
        if index == 1:
            fields[1] = RDATA_VA
            fields[3] = RDATA_RAW
            fields[4] = RDATA_SIZE
        struct.pack_into(strength.SECTION_TABLE_FIELDS, buf, header, *fields)
    for va, retail in _retail_sites():
        buf[_text_off(va): _text_off(va) + len(retail)] = retail
    for va, retail in _retail_rdata_sites():
        buf[_rdata_off(va): _rdata_off(va) + len(retail)] = retail
    buf[_rdata_off(kick.RETAIL_PAT_CONST): _rdata_off(kick.RETAIL_PAT_CONST) + 4] = struct.pack("<f", 4389.12)
    header = TABLE_OFF
    buf[header + 36: header + 56] = _section_digest(bytes(buf), TEXT_RAW, TEXT_SIZE)
    header = TABLE_OFF + strength.SECTION_HEADER_SIZE
    buf[header + 36: header + 56] = _section_digest(bytes(buf), RDATA_RAW, RDATA_SIZE)
    return bytes(buf)


class GeometryTests(unittest.TestCase):
    def test_spots_are_distances_from_midfield_in_centimetres(self) -> None:
        self.assertAlmostEqual(kick.spot_cm(30), 1828.8, places=3)     # retail kickoff constant
        self.assertAlmostEqual(kick.spot_cm(20), 2743.2, places=3)     # retail touchback constant
        self.assertAlmostEqual(kick.spot_cm(2), 4389.12, places=3)     # retail PAT constant
        self.assertAlmostEqual(kick.spot_cm(35), 1371.6, places=3)     # modern kickoff: 15 yd from midfield
        self.assertAlmostEqual(kick.spot_cm(15), 3200.4, places=3)     # modern PAT kick: 35 yd from midfield
        for yard in (2, 15, 20, 30, 35):
            self.assertEqual(kick.yard_line(kick.spot_cm(yard)), float(yard))
            self.assertEqual(kick.yard_line(-kick.spot_cm(yard)), float(yard))

    def test_retail_settings_reproduce_the_retail_constants(self) -> None:
        floats = struct.unpack("<4f", kick.float_bytes(30, 20, 2))
        self.assertEqual(floats[0], struct.unpack("<f", struct.pack("<f", 1828.8))[0])
        self.assertEqual(floats[1], -floats[0])
        self.assertEqual(floats[2], struct.unpack("<f", struct.pack("<f", 2743.2))[0])
        self.assertEqual(floats[3], struct.unpack("<f", struct.pack("<f", 4389.12))[0])
        self.assertEqual(kick.FLOAT_PAT_TWO, kick.RETAIL_PAT_CONST, "the two-point spot is the game's own constant")

    def test_2026_defaults(self) -> None:
        self.assertEqual((kick.MODERN_KICKOFF_YARD, kick.MODERN_TOUCHBACK_YARD, kick.MODERN_PAT_YARD), (35, 35, 15))
        self.assertEqual(kick.TOUCHBACK_2024_YARD, 30)
        floats = struct.unpack("<4f", kick.float_bytes())
        self.assertAlmostEqual(floats[2], 1371.6, places=2)    # touchback to the 35 = 15 yd from midfield

    def test_settings_are_validated(self) -> None:
        for bad in ((0, 30, 15), (35, 50, 15), (35, 30, -1)):
            with self.assertRaises(kick.KickRulesError):
                kick.float_bytes(*bad)


class CaveShapeTests(unittest.TestCase):
    def test_cave_fits_the_dead_function_and_is_parameter_independent_after_the_floats(self) -> None:
        default = kick.cave_bytes()
        other = kick.cave_bytes(40, 25, 10)
        self.assertEqual(len(default), kick.CAVE_SIZE)
        self.assertEqual(len(kick.RETAIL_CAVE), kick.CAVE_SIZE)
        self.assertNotEqual(default[:16], other[:16])
        self.assertEqual(default[16:], other[16:])
        self.assertTrue(default.endswith(b"\xcc"), "the tail of the dead function is int3-padded")
        self.assertEqual(kick.RETAIL_CAVE[:3], bytes.fromhex("558bec"), "cave host starts with push ebp / mov ebp, esp")
        self.assertEqual(kick.RETAIL_CAVE[-1:], b"\xc3", "cave host ends with ret")

    def test_labels_and_internal_calls_resolve_inside_the_cave(self) -> None:
        labels = kick.cave_labels()
        for name in ("stub_store", "stub_pick", "stub_audible", "stub_lineup", "fix_pat", "touchback", "end"):
            self.assertIn(name, labels)
            self.assertTrue(kick.CODE_VA <= labels[name] <= kick.CAVE_VA + kick.CAVE_SIZE, name)
        cave = kick.cave_bytes()
        code_off = kick.CODE_VA - kick.CAVE_VA
        # push-stubs: `push <retail callee>` then a short jump into the fixer, whose `ret` calls the callee
        for stub, target in (("stub_store", kick.STORE_TARGET_VA), ("stub_pick", kick.PICK_TARGET_VA),
                             ("stub_audible", kick.AUDIBLE_TARGET_VA)):
            off = labels[stub] - kick.CAVE_VA
            self.assertEqual(cave[off: off + 5], b"\x68" + struct.pack("<I", target), stub)
            self.assertEqual(cave[off + 5], 0xEB, stub)
            self.assertEqual(labels[stub] + 7 + struct.unpack_from("<b", cave, off + 6)[0], labels["fix_pat"], stub)
        # the line-up entry stub: call fix_pat, drop the return address, replay the three replaced
        # instructions, jump to the fourth instruction of FUN_001ceac0
        off = labels["stub_lineup"] - kick.CAVE_VA
        self.assertEqual(cave[off], 0xE8)
        self.assertEqual(labels["stub_lineup"] + 5 + struct.unpack_from("<i", cave, off + 1)[0], labels["fix_pat"])
        self.assertEqual(cave[off + 5: off + 8], bytes.fromhex("83c404"))
        self.assertEqual(cave[off + 8: off + 13], kick.RETAIL_LINEUP_ENTRY)
        self.assertEqual(cave[off + 13], 0xE9)
        self.assertEqual(labels["stub_lineup"] + 18 + struct.unpack_from("<i", cave, off + 14)[0], kick.LINEUP_RESUME_VA)
        # the touchback cave keeps the retail multiply on its non-kickoff path
        tb = labels["touchback"] - kick.CAVE_VA
        self.assertEqual(cave[tb: tb + 7], bytes.fromhex("803d") + struct.pack("<I", kick.PHASE_GLOBAL) + b"\x02")
        self.assertEqual(cave[tb + 9: tb + 15], b"\xd8\x0d" + struct.pack("<I", kick.FLOAT_TOUCHBACK))
        self.assertEqual(cave[tb + 16: tb + 22], kick.RETAIL_FMUL_TOUCHBACK)
        # the fixer starts with pushad and ends with popad / ret
        fix = labels["fix_pat"] - kick.CAVE_VA
        self.assertEqual(cave[fix], 0x60)
        self.assertEqual(cave[labels["touchback"] - kick.CAVE_VA - 2:labels["touchback"] - kick.CAVE_VA], b"\x61\xc3")
        self.assertEqual(code_off, 16)
        self.assertEqual(labels["stub_store"], kick.CODE_VA)


class FieldGoalCurveTests(unittest.TestCase):
    def test_retail_curves_encode_to_the_retail_table_bytes(self) -> None:
        meter = kick.RETAIL_FG_METER_BYTES
        self.assertEqual(struct.unpack_from("<I", meter, 0)[0], 4)
        self.assertEqual(struct.unpack_from("<ff", meter, 4 + 8 * 3), (1.0, struct.unpack("<f", struct.pack("<f", 5486.4))[0]))
        power = kick.RETAIL_FG_POWER_BYTES
        self.assertEqual(struct.unpack_from("<I", power, 0)[0], 5)
        self.assertEqual(struct.unpack_from("<ff", power, 4 + 8 * 2), (struct.unpack("<f", struct.pack("<f", 0.4))[0],
                                                                        struct.unpack("<f", struct.pack("<f", 0.8))[0]))
        self.assertEqual(kick.fg_tables(60), {"meter": kick.RETAIL_FG_METER, "power": kick.RETAIL_FG_POWER})

    def test_ceiling_is_a_scale_that_spares_mid_power_legs(self) -> None:
        tables = kick.fg_tables(70)
        self.assertEqual([x for x, _y in tables["meter"]], [x for x, _y in kick.RETAIL_FG_METER])
        self.assertEqual([x for x, _y in tables["power"]], [x for x, _y in kick.RETAIL_FG_POWER])
        self.assertEqual(tables["meter"][0], (0.0, 20.0), "a mis-hit still travels the retail 20 yd")
        self.assertEqual(tables["meter"][-1], (1.0, 70.0))
        self.assertEqual(tables["power"][-1], (1.0, 1.0))
        for name in ("meter", "power"):
            ys = [y for _x, y in tables[name]]
            self.assertEqual(ys, sorted(ys), name)
        for (x, retail), (_x, new) in zip(kick.RETAIL_FG_POWER, tables["power"]):
            self.assertLessEqual(new, retail + 1e-9, f"factor at {x} may only shrink")
        rows = {row["rating"]: row for row in kick.fg_preview(70)}
        self.assertGreaterEqual(rows[99]["max_yards"], 68.0)
        self.assertLessEqual(rows[99]["max_yards"], 70.0)
        self.assertLessEqual(rows[80]["max_yards"] - rows[80]["retail_yards"], 4.0)
        self.assertLessEqual(rows[70]["max_yards"] - rows[70]["retail_yards"], 3.0)
        self.assertLessEqual(rows[60]["max_yards"] - rows[60]["retail_yards"], 1.5)
        self.assertEqual(rows[99]["min_yards"], round(rows[99]["max_yards"] - 4.0, 1))

    def test_ceiling_is_validated_and_rounded(self) -> None:
        for bad in (59.9, 90.1, -1, "x"):
            with self.assertRaises((kick.KickRulesError, ValueError, TypeError)):
                kick.fg_tables(bad)
        self.assertEqual(kick.fg_tables(70.0004)["meter"][-1], (1.0, 70.0))

    def test_cave_carries_the_retail_curves_after_the_code(self) -> None:
        cave = kick.cave_bytes()
        meter_off = kick.CAVE_METER_TABLE_VA - kick.CAVE_VA
        power_off = kick.CAVE_POWER_TABLE_VA - kick.CAVE_VA
        self.assertEqual(meter_off % 4, 0)
        self.assertGreaterEqual(meter_off, 4 * kick.FLOAT_COUNT + len(kick._code(kick.CODE_VA)[0]))
        self.assertEqual(cave[meter_off: meter_off + len(kick.RETAIL_FG_METER_BYTES)], kick.RETAIL_FG_METER_BYTES)
        self.assertEqual(cave[power_off: power_off + len(kick.RETAIL_FG_POWER_BYTES)], kick.RETAIL_FG_POWER_BYTES)
        self.assertLessEqual(power_off + len(kick.RETAIL_FG_POWER_BYTES), kick.CAVE_SIZE)
        labels = kick.cave_labels()
        self.assertEqual(labels["retail_meter_table"], kick.CAVE_METER_TABLE_VA)
        self.assertLess(labels["end"], kick.CAVE_METER_TABLE_VA + 1)


class SyntheticXbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _build_synthetic_xbe()

    def test_status_apply_round_trip(self) -> None:
        self.assertEqual(kick.status(self.payload), "retail")
        patched, receipt = kick.apply(self.payload)
        self.assertEqual(kick.status(patched), "applied")
        self.assertEqual(receipt["sections_repinned"], [0, 1])
        self.assertEqual(kick.read_settings(patched)["kickoff_yard"], 35.0)
        self.assertEqual(kick.read_settings(patched)["touchback_yard"], 35.0)
        self.assertEqual(kick.read_settings(patched)["pat_yard"], 15.0)
        self.assertEqual(kick.read_settings(patched)["pat_two_yard"], 2.0)
        self.assertEqual(kick.read_settings(patched)["spots"], "applied")
        for va in (kick.PAT_STORE_SITE_VA, kick.PAT_PICK_SITE_VA, kick.PAT_AUDIBLE_SITE_VA, kick.PAT_LINEUP_ENTRY_VA):
            self.assertEqual(patched[_text_off(va)], 0xE8, hex(va))
        self.assertEqual(patched[_text_off(kick.TRY_RECORD_SITE_VA): _text_off(kick.TRY_RECORD_SITE_VA) + 6],
                         b"\xd8\x0d" + struct.pack("<I", kick.FLOAT_PAT_KICK))
        # the 9/3 y-disc hook sites are no longer touched
        for va in (0x0009FA91, 0x001D05A8, 0x001CF4F2, 0x000762B4, 0x00076393):
            self.assertEqual(patched[_text_off(va): _text_off(va) + 6], self.payload[_text_off(va): _text_off(va) + 6], hex(va))
        with self.assertRaises(kick.KickRulesError):
            kick.apply(patched)

    def test_only_the_sites_and_the_text_digest_change(self) -> None:
        patched, receipt = kick.apply(self.payload, 35, 30, 15)
        expected = {}
        for label, va, const, kind in kick.KICKOFF_SITES:
            slot = kick.FLOAT_KICKOFF_POS if kind == "pos" else kick.FLOAT_KICKOFF_NEG
            expected[_text_off(va)] = b"\xd8\x0d" + struct.pack("<I", slot)
        labels = kick.cave_labels()
        expected[_text_off(kick.TOUCHBACK_SITE_VA)] = kick._rel32_call(kick.TOUCHBACK_SITE_VA, labels["touchback"]) + b"\x90"
        expected[_text_off(kick.TRY_RECORD_SITE_VA)] = b"\xd8\x0d" + struct.pack("<I", kick.FLOAT_PAT_KICK)
        expected[_text_off(kick.PAT_STORE_SITE_VA)] = kick._rel32_call(kick.PAT_STORE_SITE_VA, labels["stub_store"])
        expected[_text_off(kick.PAT_PICK_SITE_VA)] = kick._rel32_call(kick.PAT_PICK_SITE_VA, labels["stub_pick"])
        expected[_text_off(kick.PAT_AUDIBLE_SITE_VA)] = kick._rel32_call(kick.PAT_AUDIBLE_SITE_VA, labels["stub_audible"])
        expected[_text_off(kick.PAT_LINEUP_ENTRY_VA)] = kick._rel32_call(kick.PAT_LINEUP_ENTRY_VA, labels["stub_lineup"])
        expected[_text_off(kick.CAVE_VA)] = kick.cave_bytes(35, 30, 15)
        tables = kick.fg_table_bytes(70)
        expected[_rdata_off(kick.FG_METER_TABLE_VA)] = tables["meter"]
        expected[_rdata_off(kick.FG_POWER_TABLE_VA)] = tables["power"]
        cave_va = {kick.FG_METER_TABLE_VA: kick.CAVE_METER_TABLE_VA, kick.FG_POWER_TABLE_VA: kick.CAVE_POWER_TABLE_VA}
        for _label, va, opcode, table_va in kick.CPU_RANGE_SITES:
            target = cave_va.get(table_va, cave_va.get(table_va - 4, 0) + 4)
            expected[_text_off(va)] = opcode + struct.pack("<I", target)
        allowed = set()
        for off, blob in expected.items():
            self.assertEqual(patched[off: off + len(blob)], blob, hex(off))
            allowed.update(range(off, off + len(blob)))
        allowed.update(range(TABLE_OFF + 36, TABLE_OFF + 56))     # .text digest
        rdata_header = TABLE_OFF + strength.SECTION_HEADER_SIZE
        allowed.update(range(rdata_header + 36, rdata_header + 56))   # .rdata digest
        changed = {i for i, (a, b) in enumerate(zip(self.payload, patched)) if a != b}
        self.assertTrue(changed <= allowed, sorted(hex(i) for i in changed - allowed)[:10])
        self.assertEqual(patched[TABLE_OFF + 36: TABLE_OFF + 56], _section_digest(patched, TEXT_RAW, TEXT_SIZE))
        self.assertEqual(patched[rdata_header + 36: rdata_header + 56], _section_digest(patched, RDATA_RAW, RDATA_SIZE))
        self.assertEqual(receipt["changed_bytes"], len(changed))

    def test_other_settings_change_only_the_floats(self) -> None:
        default, _ = kick.apply(self.payload)
        other, _ = kick.apply(self.payload, 40, 25, 10)
        diff = {i for i, (a, b) in enumerate(zip(default, other)) if a != b}
        floats = set(range(_text_off(kick.CAVE_VA), _text_off(kick.CAVE_VA) + 4 * kick.FLOAT_COUNT))
        digest = set(range(TABLE_OFF + 36, TABLE_OFF + 56))
        self.assertTrue(diff <= floats | digest)
        self.assertEqual(kick.read_settings(other)["kickoff_yard"], 40.0)
        self.assertEqual(kick.read_settings(other)["touchback_yard"], 25.0)
        self.assertEqual(kick.read_settings(other)["pat_yard"], 10.0)

    def test_foreign_bytes_are_refused(self) -> None:
        for va, retail in _retail_sites():
            broken = bytearray(self.payload)
            broken[_text_off(va)] ^= 0xFF
            self.assertEqual(kick.status(bytes(broken)), "foreign", hex(va))
            with self.assertRaises(kick.KickRulesError):
                kick.apply(bytes(broken))
        for va, retail in _retail_rdata_sites():
            broken = bytearray(self.payload)
            broken[_rdata_off(va) + 8] ^= 0x01      # first y value
            self.assertEqual(kick.status(bytes(broken)), "foreign", hex(va))
        self.assertEqual(kick.status(b"\x00" * 0x1000), "foreign")

    def test_fg_ceiling_round_trip_and_cpu_pin(self) -> None:
        patched, receipt = kick.apply(self.payload, max_fg_yards=70)
        self.assertEqual(kick.status(patched), "applied")
        settings = kick.read_settings(patched)
        self.assertEqual(settings["max_fg_yards"], 70.0)
        self.assertEqual(settings["cpu_fg_range"], "retail")
        tables = kick.fg_table_bytes(70)
        self.assertEqual(patched[_rdata_off(kick.FG_METER_TABLE_VA):][:len(tables["meter"])], tables["meter"])
        self.assertEqual(patched[_rdata_off(kick.FG_POWER_TABLE_VA):][:len(tables["power"])], tables["power"])
        # the CPU range routine now reads the retail copies that live in the cave
        cave = patched[_text_off(kick.CAVE_VA): _text_off(kick.CAVE_VA) + kick.CAVE_SIZE]
        meter_off = kick.CAVE_METER_TABLE_VA - kick.CAVE_VA
        power_off = kick.CAVE_POWER_TABLE_VA - kick.CAVE_VA
        self.assertEqual(cave[meter_off: meter_off + len(kick.RETAIL_FG_METER_BYTES)], kick.RETAIL_FG_METER_BYTES)
        self.assertEqual(cave[power_off: power_off + len(kick.RETAIL_FG_POWER_BYTES)], kick.RETAIL_FG_POWER_BYTES)
        for label, va, opcode, table_va in kick.CPU_RANGE_SITES:
            got = patched[_text_off(va): _text_off(va) + len(opcode) + 4]
            self.assertEqual(got[:len(opcode)], opcode, label)
            target = struct.unpack("<I", got[len(opcode):])[0]
            base = kick.CAVE_METER_TABLE_VA if "meter" in label else kick.CAVE_POWER_TABLE_VA
            self.assertEqual(target, base + (4 if label.endswith("_table") else 0), label)
        self.assertEqual(receipt["max_fg_yards"], 70.0)
        self.assertEqual(receipt["fg_meter_curve"]["applied"][-1], (1.0, 70.0))
        self.assertEqual(receipt["fg_preview"][0]["rating"], 99)
        self.assertGreaterEqual(receipt["fg_preview"][0]["max_yards"], 68.0)
        with self.assertRaises(kick.KickRulesError):
            kick.apply(patched, max_fg_yards=70)

    def test_cpu_scaled_leaves_the_cpu_operands_retail(self) -> None:
        patched, _receipt = kick.apply(self.payload, max_fg_yards=75, cpu_fg_range="scaled")
        self.assertEqual(kick.status(patched), "applied")
        for _label, va, opcode, table_va in kick.CPU_RANGE_SITES:
            self.assertEqual(patched[_text_off(va): _text_off(va) + len(opcode) + 4], opcode + struct.pack("<I", table_va))
        settings = kick.read_settings(patched)
        self.assertEqual(settings["cpu_fg_range"], "scaled")
        self.assertEqual(settings["max_fg_yards"], 75.0)

    def test_retail_ceiling_keeps_the_curve_tables_retail(self) -> None:
        patched, receipt = kick.apply(self.payload, max_fg_yards=60)
        self.assertEqual(kick.status(patched), "applied")
        self.assertEqual(kick.read_settings(patched)["max_fg_yards"], 60.0)
        for va, retail in _retail_rdata_sites():
            self.assertEqual(patched[_rdata_off(va): _rdata_off(va) + len(retail)], retail)
        self.assertEqual(receipt["sections_repinned"], [0], "no .rdata byte changed, so no .rdata digest")

    def test_hand_edited_curve_on_a_patched_image_is_foreign(self) -> None:
        patched, _receipt = kick.apply(self.payload, max_fg_yards=70)
        broken = bytearray(patched)
        broken[_rdata_off(kick.FG_POWER_TABLE_VA) + 8] ^= 0x01
        self.assertEqual(kick.status(bytes(broken)), "foreign")
        broken = bytearray(patched)
        struct.pack_into("<f", broken, _rdata_off(kick.FG_METER_TABLE_VA) + 4 + 8 * 3 + 4, 80 * kick.YARD_CM)
        self.assertEqual(kick.status(bytes(broken)), "foreign", "meter top edited without the power curve")

    def test_fg_settings_are_validated(self) -> None:
        for bad in ({"max_fg_yards": 59}, {"max_fg_yards": 91}, {"cpu_fg_range": "auto"}):
            with self.assertRaises(kick.KickRulesError):
                kick.apply(self.payload, **bad)

    def test_power_only_mode(self) -> None:
        power, receipt = kick.apply(self.payload, spots=False)
        self.assertEqual(kick.status(power), kick.STATUS_POWER_ONLY)
        self.assertEqual(receipt["status"], "power_only")
        self.assertFalse(receipt["spots"])
        settings = kick.read_settings(power)
        self.assertEqual(settings["status"], "power_only")
        self.assertEqual(settings["spots"], "retail")
        self.assertEqual((settings["kickoff_yard"], settings["touchback_yard"], settings["pat_yard"]), (30.0, 20.0, 2.0))
        self.assertEqual(settings["max_fg_yards"], 70.0)
        self.assertEqual(settings["cpu_fg_range"], "retail")
        # only the two live tables, the four CPU operands and the dead function's table tail changed
        allowed = set()
        tables = kick.fg_table_bytes(70)
        for va, blob in ((kick.FG_METER_TABLE_VA, tables["meter"]), (kick.FG_POWER_TABLE_VA, tables["power"])):
            allowed.update(range(_rdata_off(va), _rdata_off(va) + len(blob)))
        for _label, va, opcode, _table_va in kick.CPU_RANGE_SITES:
            allowed.update(range(_text_off(va), _text_off(va) + len(opcode) + 4))
        split = kick._cave_tables_offset()
        allowed.update(range(_text_off(kick.CAVE_VA) + split, _text_off(kick.CAVE_VA) + kick.CAVE_SIZE))
        allowed.update(range(TABLE_OFF + 36, TABLE_OFF + 56))
        rdata_header = TABLE_OFF + strength.SECTION_HEADER_SIZE
        allowed.update(range(rdata_header + 36, rdata_header + 56))
        changed = {i for i, (a, b) in enumerate(zip(self.payload, power)) if a != b}
        self.assertTrue(changed <= allowed, sorted(hex(i) for i in changed - allowed)[:10])
        self.assertEqual(power[_text_off(kick.CAVE_VA): _text_off(kick.CAVE_VA) + split], kick.RETAIL_CAVE[:split])
        cpu_sites = {va for _label, va, _opcode, _table in kick.CPU_RANGE_SITES}
        for va, retail in _retail_sites():
            if va != kick.CAVE_VA and va not in cpu_sites:
                self.assertEqual(power[_text_off(va): _text_off(va) + len(retail)], retail, hex(va))
        # upgrade to the full patch: byte-identical to a direct full apply
        full_direct, _ = kick.apply(self.payload)
        upgraded, up_receipt = kick.apply(power)
        self.assertEqual(upgraded, full_direct)
        self.assertEqual(kick.status(upgraded), "applied")
        self.assertLess(up_receipt["changed_bytes"], receipt["changed_bytes"] + 300)
        # refusals: downgrade, second power-only pass, mismatched upgrade, pointless power-only
        with self.assertRaises(kick.KickRulesError):
            kick.apply(full_direct, spots=False)
        with self.assertRaises(kick.KickRulesError):
            kick.apply(power, spots=False)
        with self.assertRaises(kick.KickRulesError):
            kick.apply(power, max_fg_yards=75)
        with self.assertRaises(kick.KickRulesError):
            kick.apply(power, cpu_fg_range="scaled")
        with self.assertRaises(kick.KickRulesError):
            kick.apply(self.payload, spots=False, max_fg_yards=60)
        # a hand edit on a power-only image is foreign
        broken = bytearray(power)
        broken[_rdata_off(kick.FG_POWER_TABLE_VA) + 8] ^= 1
        self.assertEqual(kick.status(bytes(broken)), "foreign")

    def test_power_only_scaled_touches_only_the_two_tables(self) -> None:
        power, receipt = kick.apply(self.payload, spots=False, max_fg_yards=75, cpu_fg_range="scaled")
        self.assertEqual(kick.status(power), kick.STATUS_POWER_ONLY)
        self.assertEqual(kick.read_settings(power)["cpu_fg_range"], "scaled")
        self.assertEqual(receipt["sections_repinned"], [1], "only .rdata changed")
        self.assertEqual(power[_text_off(kick.CAVE_VA): _text_off(kick.CAVE_VA) + kick.CAVE_SIZE], kick.RETAIL_CAVE)
        upgraded, _ = kick.apply(power, max_fg_yards=75, cpu_fg_range="scaled")
        self.assertEqual(upgraded, kick.apply(self.payload, max_fg_yards=75, cpu_fg_range="scaled")[0])

    def test_retail_settings_round_trip_to_retail_yard_lines(self) -> None:
        patched, receipt = kick.apply(self.payload, 30, 20, 2)
        settings = kick.read_settings(patched)
        self.assertEqual((settings["kickoff_yard"], settings["touchback_yard"], settings["pat_yard"]), (30.0, 20.0, 2.0))
        self.assertTrue(settings["kickoff_neg_consistent"])
        self.assertAlmostEqual(receipt["kickoff_spot_cm"], 1828.8, places=3)


@unittest.skipUnless(RETAIL_XBE.exists(), "private retail default.xbe not present")
class RetailXbeSmokeTests(unittest.TestCase):
    def test_retail_image_is_recognised_and_patches_cleanly(self) -> None:
        payload = RETAIL_XBE.read_bytes()
        self.assertEqual(kick.status(payload), "retail")
        patched, receipt = kick.apply(payload)
        self.assertEqual(kick.status(patched), "applied")
        rdata = next(s.index for s in strength._sections(payload)
                     if s.virtual_address <= kick.FG_METER_TABLE_VA < s.virtual_address + s.raw_size)
        self.assertEqual(receipt["sections_repinned"], sorted({0, rdata}))
        self.assertLess(receipt["changed_bytes"], 700)
        self.assertEqual(kick.read_settings(patched)["pat_yard"], 15.0)
        self.assertEqual(kick.read_settings(patched)["max_fg_yards"], 70.0)
        power, _ = kick.apply(payload, spots=False)
        self.assertEqual(kick.status(power), kick.STATUS_POWER_ONLY)
        self.assertEqual(kick.apply(power)[0], patched, "power-only upgrades to the very same full image")



HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None

# fake game objects for the emulator (a VA range the image never uses)
SCRATCH = 0x00F00000
CTX, TEAM, STATE, TEAM_DATA, SCORE, DIRECTION = SCRATCH, SCRATCH + 0x1000, SCRATCH + 0x2000, SCRATCH + 0x3000, SCRATCH + 0x3100, SCRATCH + 0x3200
OTHER_TEAM, OTHER_DATA, OTHER_SCORE, OTHER_STATE = SCRATCH + 0x4000, SCRATCH + 0x4100, SCRATCH + 0x4200, SCRATCH + 0x4300
FORMATION, BALL, TRANSFORM, RECORD, PLAYREC, PLAYER, ENTITY = (SCRATCH + 0x5000, SCRATCH + 0x6000, SCRATCH + 0x6100,
                                                                SCRATCH + 0x7000, SCRATCH + 0x7400, SCRATCH + 0x8000, SCRATCH + 0x9000)
TEAM_CLUB = SCRATCH + 0x3400
STACK_BASE, STACK_TOP = SCRATCH + 0x10000, SCRATCH + 0x1F000
SENTINEL = 0x00DEAD00
F_2YD = struct.unpack("<f", struct.pack("<f", 4389.12))[0]
F_15YD = struct.unpack("<f", struct.pack("<f", 3200.4))[0]
F_GOAL = 4572.0
CALL_SITES = {                  # every `call` inside the two pick handlers (from the capstone listing)
    "store": 0x000A328A, "pick": 0x000A333C, "marker": 0x000A3356, "f990_a": 0x000A33F4, "f990_b": 0x000A3408,
    "lineup_off": 0x000A3414, "plan": 0x000A341B, "def_cpu": 0x000A3436, "def_pick": 0x000A3453,
    "lineup_def": 0x000A3462, "fac0": 0x000A3469,
    "aud_f990": 0x000A24E7, "aud_lineup": 0x000A24F2, "aud_plan": 0x000A24F9,
}


@unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
class CaveDecodeTests(unittest.TestCase):
    def test_every_cave_instruction_decodes_and_every_branch_lands_on_an_instruction(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs

        code, labels = kick._code(kick.CODE_VA)
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        starts = set()
        branch_targets = []
        total = 0
        for ins in md.disasm(code, kick.CODE_VA):
            starts.add(ins.address)
            total += ins.size
            if ins.mnemonic.startswith("j") or ins.mnemonic == "call":
                branch_targets.append((ins.address, int(ins.op_str, 16)))
        self.assertEqual(total, len(code), "the whole blob decodes")
        outside = set()
        for site, target in branch_targets:
            if kick.CODE_VA <= target < kick.CODE_VA + len(code):
                self.assertIn(target, starts, f"branch at {site:#x} lands mid-instruction")
            else:
                outside.add(target)
        self.assertEqual(outside, {kick.LINEUP_RESUME_VA}, "the only branch out of the cave resumes FUN_001ceac0")
        self.assertIn(labels["fix_pat"], starts)
        self.assertIn(labels["touchback"], starts)


@unittest.skipUnless(RETAIL_XBE.is_file() and HAVE_UNICORN and HAVE_CAPSTONE, "retail default.xbe, unicorn and capstone needed")
class UnicornTests(unittest.TestCase):
    """The real code of the patched retail image with a mocked game state: the try record, both pick
    handlers (every call skipped except the ones under test), the line-up entry stub, the slot builder,
    the touchback cave and the fixer's guards."""

    @classmethod
    def setUpClass(cls) -> None:
        payload = RETAIL_XBE.read_bytes()
        cls.patched, _receipt = kick.apply(payload)     # 35 / 35 / 15, ceiling 70, CPU retail
        cls.labels = kick.cave_labels()

    # ------------------------------------------------------------------ machine
    def _machine(self):
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc

        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0x00010000, 0x00E61000 - 0x00010000)     # .text .. the end of .data's BSS tail
        for section in strength._sections(self.patched):
            if section.virtual_address in (0x11000, 0x4E3AE0, 0xA69980):
                uc.mem_write(section.virtual_address,
                             self.patched[section.raw_offset: section.raw_offset + section.raw_size])
        uc.mem_map(SCRATCH, 0x20000)
        return uc

    def _state(self, uc, *, sign=1.0, phase=3, formation_type=12, los_z=F_2YD, state_ptr=STATE, ball_held=0):
        u32 = lambda v: struct.pack("<I", v & 0xFFFFFFFF)   # noqa: E731
        f32 = lambda v: struct.pack("<f", v)                # noqa: E731
        z = sign * los_z
        uc.mem_write(CTX + 0x10, f32(0.0) + f32(0.0) + f32(z) + f32(1.0))
        uc.mem_write(CTX + 0x30, f32(0.0) + f32(0.0) + f32(z) + f32(1.0))
        uc.mem_write(CTX + 0x04, u32(1))
        uc.mem_write(CTX + 0x15C, u32(1))                               # FUN_000a31e0's "in a play" gate
        uc.mem_write(TEAM + 0x0C, u32(state_ptr))
        uc.mem_write(TEAM + 0x08, u32(TEAM_DATA))
        uc.mem_write(TEAM_DATA, u32(SCORE))
        uc.mem_write(TEAM_DATA + 0x0C, u32(DIRECTION))
        uc.mem_write(DIRECTION + 4, f32(sign))
        uc.mem_write(TEAM + 0x38, u32(TEAM_CLUB))
        uc.mem_write(TEAM_CLUB + 8, u32(TEAM_DATA))
        uc.mem_write(OTHER_TEAM + 0x08, u32(OTHER_DATA))
        uc.mem_write(OTHER_TEAM + 0x0C, u32(OTHER_STATE))
        uc.mem_write(OTHER_DATA, u32(OTHER_SCORE))
        uc.mem_write(OTHER_DATA + 0x0C, u32(DIRECTION))
        uc.mem_write(STATE + 0x08, u32(FORMATION))
        uc.mem_write(FORMATION + 0x04, u32(formation_type << 8))
        uc.mem_write(PLAYREC + 0x08, u32(FORMATION))                    # a play record whose +8 is the formation
        uc.mem_write(BALL, u32(ball_held))
        uc.mem_write(BALL + 0x14, u32(TRANSFORM))
        uc.mem_write(TRANSFORM, f32(0.0) + f32(0.0) + f32(z) + f32(1.0))
        uc.mem_write(kick.POSSESSION_GLOBAL, u32(TEAM))
        uc.mem_write(0x00E60284, u32(OTHER_TEAM))
        uc.mem_write(kick.CTX_GLOBAL, u32(CTX))
        uc.mem_write(kick.PHASE_GLOBAL, u32(phase))
        uc.mem_write(kick.BALL_GLOBAL, u32(BALL))
        uc.mem_write(0x00E5FF80, u32(5))                                # a real game mode (>= 4)
        uc.mem_write(0x00E60268, u32(0))                                # no controllers to walk
        uc.mem_write(0x00B616C0, u32(0))                                # not the in-game camera state (skips the scene work)

    @staticmethod
    def _f(uc, va):
        return struct.unpack("<f", bytes(uc.mem_read(va, 4)))[0]

    @staticmethod
    def _u(uc, va):
        return struct.unpack("<I", bytes(uc.mem_read(va, 4)))[0]

    def _regs(self, uc, **regs):
        from unicorn import x86_const
        for name, value in regs.items():
            uc.reg_write(getattr(x86_const, f"UC_X86_REG_{name.upper()}"), value)

    def _call_tracer(self, uc, allow):
        """Skip every `call` whose target is not allowed (EAX := 0), and record the LOS z the code saw
        at every call instruction: [(site, target, los_z)]."""
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        cache: dict[int, tuple[str, int, int | None]] = {}
        trace: list[tuple[int, int | None, float]] = []
        cave = range(kick.CAVE_VA, kick.CAVE_VA + kick.CAVE_SIZE)

        pops: dict[int, int] = {}

        def decode(address):
            if address not in cache:
                ins = next(md.disasm(bytes(uc.mem_read(address, 16)), address, count=1))
                target = int(ins.op_str, 16) if ins.mnemonic == "call" and ins.op_str.startswith("0x") else None
                cache[address] = (ins.mnemonic, ins.size, target)
            return cache[address]

        def stack_pop(target):
            # the callee's `ret imm16` (stdcall / fastcall stack arguments): first ret in a linear sweep
            if target not in pops:
                pops[target] = 0
                for ins in md.disasm(bytes(uc.mem_read(target, 0x1000)), target):
                    if ins.mnemonic == "ret":
                        pops[target] = int(ins.op_str, 16) if ins.op_str else 0
                        break
            return pops[target]

        def on_code(_uc, address, _size, _user):
            mnemonic, size, target = decode(address)
            if mnemonic != "call":
                return
            trace.append((address, target, self._f(uc, CTX + 0x18)))
            if target is None or not (target in allow or target in cave):
                from unicorn.x86_const import UC_X86_REG_ESP
                uc.reg_write(UC_X86_REG_EAX, 0)
                uc.reg_write(UC_X86_REG_ESP, uc.reg_read(UC_X86_REG_ESP) + (stack_pop(target) if target else 0))
                uc.reg_write(UC_X86_REG_EIP, address + size)

        uc.hook_add(UC_HOOK_CODE, on_code)
        return trace

    def _lineup_resume_hook(self, uc):
        """FUN_001ceac0's fourth instruction: record the LOS the line-up sees and return to the caller
        (undo the replayed sub esp,0x24 / push ebx / push ebp)."""
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP

        seen: list[float] = []

        def on_code(_uc, address, _size, _user):
            if address != kick.LINEUP_RESUME_VA:
                return
            seen.append(self._f(uc, CTX + 0x18))
            esp = uc.reg_read(UC_X86_REG_ESP) + 0x2C
            ret = self._u(uc, esp)
            uc.reg_write(UC_X86_REG_ESP, esp + 4)
            uc.reg_write(UC_X86_REG_EIP, ret)

        uc.hook_add(UC_HOOK_CODE, on_code, begin=kick.LINEUP_RESUME_VA, end=kick.LINEUP_RESUME_VA)
        return seen

    def _run(self, uc, start, until, **regs):
        from unicorn.x86_const import UC_X86_REG_ESP
        uc.mem_write(STACK_TOP - 4, struct.pack("<I", SENTINEL))
        uc.reg_write(UC_X86_REG_ESP, STACK_TOP - 4)
        self._regs(uc, **regs)
        uc.emu_start(start, until, count=400_000)

    # ------------------------------------------------------------------ the try record (both teams start at the 15)
    def test_try_record_and_its_application_put_the_whole_try_at_the_15(self) -> None:
        from unicorn.x86_const import UC_X86_REG_ESP
        for sign in (1.0, -1.0):
            uc = self._machine()
            self._state(uc, sign=sign, phase=4, los_z=F_GOAL)          # the TD play just ended on the goal line
            uc.mem_write(CTX + 0x178, struct.pack("<I", 1))            # dead-ball result: touchdown
            uc.mem_write(CTX + 0x19C, struct.pack("<I", TEAM))         # scoring team
            self._call_tracer(uc, allow={0x0022DFB0, 0x0022DAB0})       # rec+0 := 3 (next phase = point after); direction helper
            self._run(uc, 0x0022E050, SENTINEL, esi=RECORD, edi=TEAM)
            self.assertEqual(uc.reg_read(UC_X86_REG_ESP), STACK_TOP)
            self.assertEqual(self._u(uc, RECORD), 3, "next phase: point after")
            self.assertEqual(self._u(uc, RECORD + 8), 1)
            self.assertEqual(self._f(uc, RECORD + 0x48), sign * F_15YD, "the try spot is the 15")
            self.assertEqual(self._f(uc, RECORD + 0x38), sign * F_GOAL, "previous spot: the goal line")
            # apply the record: FUN_0022e4d0(rec, 0)
            uc.mem_write(RECORD + 0x14, struct.pack("<I", TEAM))
            uc.mem_write(kick.PHASE_GLOBAL, struct.pack("<I", 4))
            uc.mem_write(CTX + 0x10, b"\x00" * 16)
            self._run(uc, 0x0022E4D0, SENTINEL, ecx=RECORD, edx=0)
            self.assertEqual(self._u(uc, kick.PHASE_GLOBAL), 3)
            self.assertEqual(self._f(uc, CTX + 0x18), sign * F_15YD, "line of scrimmage")
            self.assertEqual(self._f(uc, CTX + 0x38), sign * F_15YD, "ball spot")
            self.assertEqual(self._f(uc, CTX + 0x28), sign * F_GOAL, "first-down marker = goal line")
            self.assertEqual(self._u(uc, CTX + 4), 1)

    # ------------------------------------------------------------------ the pick handler (FUN_000a31e0)
    def _pick(self, formation_type, los_z, *, sign=1.0, store_formation=True):
        uc = self._machine()
        self._state(uc, sign=sign, formation_type=formation_type, los_z=los_z)
        uc.mem_write(OTHER_TEAM + 4, struct.pack("<I", 1))         # the defense has a controller: its branch runs
        uc.mem_write(STATE + 0x24, struct.pack("<I", 0))
        trace = self._call_tracer(uc, allow={kick.STORE_TARGET_VA, kick.PICK_TARGET_VA, kick.AUDIBLE_TARGET_VA,
                                             0x0009CBD0, kick.PAT_LINEUP_ENTRY_VA})
        seen = self._lineup_resume_hook(uc)
        self._run(uc, 0x000A31E0, SENTINEL, ecx=0, edx=FORMATION if store_formation else 0)
        return uc, trace, seen

    def _los_at(self, trace, site):
        hits = [z for address, _t, z in trace if address == site]
        self.assertTrue(hits, f"call site {site:#x} was not reached")
        return hits

    def test_pick_of_the_kick_leaves_the_try_at_the_15(self) -> None:
        uc, trace, seen = self._pick(12, F_15YD)
        reached = 0
        for name, site in CALL_SITES.items():
            if name.startswith("aud_"):
                continue
            hits = [z for a, _t, z in trace if a == site]
            if not hits:
                self.assertIn(name, ("f990_a", "f990_b", "def_cpu", "def_pick"), f"{name} not reached")   # if/else branches
                continue
            reached += 1
            self.assertEqual(set(hits), {F_15YD}, name)
        self.assertGreaterEqual(reached, 8)
        self.assertEqual(seen, [F_15YD, F_15YD], "offense and defense line-ups both see the 15")
        self.assertEqual(self._f(uc, 0x00A873F8), F_15YD, "down-marker global")
        self.assertEqual(self._f(uc, TRANSFORM + 8), F_15YD)
        self.assertEqual(self._u(uc, STATE + 8), FORMATION)

    def test_pick_of_a_two_point_play_moves_everything_to_the_2_before_any_line_up(self) -> None:
        for sign in (1.0, -1.0):
            uc, trace, seen = self._pick(1, F_15YD, sign=sign)
            self.assertEqual(self._los_at(trace, CALL_SITES["store"]), [sign * F_15YD], "still the 15 when the store hook fires")
            for name in ("pick", "marker", "f990_a", "f990_b", "lineup_off", "plan", "def_cpu", "def_pick", "lineup_def", "fac0"):
                if name in ("f990_a", "f990_b", "def_cpu", "def_pick"):
                    hits = [z for a, _t, z in trace if a == CALL_SITES[name]]
                    if not hits:
                        continue           # the other branch of an if/else
                self.assertEqual(set(self._los_at(trace, CALL_SITES[name])), {sign * F_2YD}, name)
            self.assertEqual(seen, [sign * F_2YD, sign * F_2YD], "offense and defense line-ups both see the 2")
            self.assertEqual(self._f(uc, 0x00A873F8), sign * F_2YD, "down-marker global built from the 2")
            self.assertEqual(self._f(uc, CTX + 0x38), sign * F_2YD)
            self.assertEqual(self._f(uc, TRANSFORM + 8), sign * F_2YD)
            # the fixer ran inside the store stub: the very next call after it already saw the 2
            after_store = [z for a, _t, z in trace if a > CALL_SITES["store"] and a < 0x000A3480]
            self.assertTrue(after_store and all(z == sign * F_2YD for z in after_store))

    def test_pick_without_a_formation_argument_is_fixed_at_the_join_point(self) -> None:
        uc, trace, seen = self._pick(1, F_15YD, store_formation=False)
        self.assertFalse([a for a, _t, _z in trace if a == CALL_SITES["store"]], "the store block is skipped")
        self.assertEqual(self._los_at(trace, CALL_SITES["pick"]), [F_15YD], "the 15 when the join-point hook fires")
        for name in ("marker", "lineup_off", "plan", "lineup_def", "fac0"):
            self.assertEqual(set(self._los_at(trace, CALL_SITES[name])), {F_2YD}, name)
        self.assertEqual(seen, [F_2YD, F_2YD])
        self.assertEqual(self._f(uc, 0x00A873F8), F_2YD)

    def test_a_scrimmage_play_pick_never_touches_the_spot(self) -> None:
        uc = self._machine()
        self._state(uc, phase=4, formation_type=1, los_z=F_15YD)
        uc.mem_write(OTHER_TEAM + 4, struct.pack("<I", 1))
        uc.mem_write(STATE + 0x24, struct.pack("<I", 0))
        before = bytes(uc.mem_read(CTX, 0x40)) + bytes(uc.mem_read(TRANSFORM, 16))
        trace = self._call_tracer(uc, allow={kick.STORE_TARGET_VA, kick.PICK_TARGET_VA, 0x0009CBD0, kick.PAT_LINEUP_ENTRY_VA})
        seen = self._lineup_resume_hook(uc)
        self._run(uc, 0x000A31E0, SENTINEL, ecx=0, edx=FORMATION)
        self.assertEqual(bytes(uc.mem_read(CTX, 0x40)) + bytes(uc.mem_read(TRANSFORM, 16)), before)
        self.assertEqual(seen, [F_15YD, F_15YD])
        self.assertTrue(trace)

    # ------------------------------------------------------------------ the audible handler (FUN_000a24b0)
    def test_audible_to_a_two_point_play_moves_the_try_before_its_line_up(self) -> None:
        uc = self._machine()
        self._state(uc, formation_type=1, los_z=F_15YD)
        uc.mem_write(STATE + 0x24, struct.pack("<I", 0))
        trace = self._call_tracer(uc, allow={kick.AUDIBLE_TARGET_VA, kick.PAT_LINEUP_ENTRY_VA})
        seen = self._lineup_resume_hook(uc)
        self._run(uc, 0x000A24B0, 0x000A2531, ecx=PLAYREC, edx=0)      # stop at the tail jump into FUN_001ffd20
        self.assertEqual(self._u(uc, STATE + 8), FORMATION, "the audible stored the formation")
        self.assertEqual(self._los_at(trace, CALL_SITES["aud_f990"]), [F_15YD], "the 15 when the audible hook fires")
        self.assertEqual(self._los_at(trace, CALL_SITES["aud_lineup"]), [F_2YD])
        self.assertEqual(self._los_at(trace, CALL_SITES["aud_plan"]), [F_2YD])
        self.assertEqual(seen, [F_2YD])
        self.assertEqual(self._f(uc, TRANSFORM + 8), F_2YD)
        # and back: an audible to the kick from the 2 returns to the 15
        uc = self._machine()
        self._state(uc, formation_type=12, los_z=F_2YD)
        uc.mem_write(STATE + 0x24, struct.pack("<I", 0))
        trace = self._call_tracer(uc, allow={kick.AUDIBLE_TARGET_VA, kick.PAT_LINEUP_ENTRY_VA})
        seen = self._lineup_resume_hook(uc)
        self._run(uc, 0x000A24B0, 0x000A2531, ecx=PLAYREC, edx=0)
        self.assertEqual(seen, [F_15YD])
        self.assertEqual(self._f(uc, CTX + 0x18), F_15YD)

    # ------------------------------------------------------------------ the line-up entry stub
    def test_lineup_entry_stub_replays_the_prologue_and_keeps_the_registers(self) -> None:
        from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESP
        uc = self._machine()
        self._state(uc, formation_type=1, los_z=F_15YD)
        uc.mem_write(STACK_TOP - 4, struct.pack("<I", SENTINEL))
        uc.reg_write(UC_X86_REG_ESP, STACK_TOP - 4)
        self._regs(uc, ebx=0x1111, ebp=0x2222, ecx=TEAM, edx=1)
        uc.emu_start(kick.PAT_LINEUP_ENTRY_VA, kick.LINEUP_RESUME_VA, count=1000)
        self.assertEqual(uc.reg_read(UC_X86_REG_EIP), kick.LINEUP_RESUME_VA)
        esp = uc.reg_read(UC_X86_REG_ESP)
        self.assertEqual(esp, STACK_TOP - 4 - 0x24 - 8, "sub esp,0x24 / push ebx / push ebp replayed")
        self.assertEqual(self._u(uc, esp), 0x2222)
        self.assertEqual(self._u(uc, esp + 4), 0x1111)
        self.assertEqual(self._u(uc, STACK_TOP - 4), SENTINEL, "the caller's return address is intact")
        self.assertEqual((uc.reg_read(UC_X86_REG_ECX), uc.reg_read(UC_X86_REG_EDX)), (TEAM, 1))
        self.assertEqual((uc.reg_read(UC_X86_REG_EBX), uc.reg_read(UC_X86_REG_EBP)), (0x1111, 0x2222))
        self.assertEqual(self._f(uc, CTX + 0x18), F_2YD, "the fixer ran on the way in")

    # ------------------------------------------------------------------ the slot builder reads the live LOS
    def test_slot_builder_places_players_from_the_line_of_scrimmage_at_call_time(self) -> None:
        # FUN_00190e00(this=player, slot, out): out = LOS + slot offset * sign (FUN_00190d50); the slot reader
        # and the clamps are skipped and the offset zeroed, so out is exactly the LOS the routine read.
        for los_z in (F_2YD, F_15YD):
            uc = self._machine()
            self._state(uc, formation_type=12, los_z=los_z)
            uc.mem_write(PLAYER + 0x38, struct.pack("<I", TEAM))
            uc.mem_write(STACK_BASE, b"\x00" * (STACK_TOP - STACK_BASE))
            self._call_tracer(uc, allow={0x00190D50})
            out = SCRATCH + 0xA000
            uc.mem_write(STACK_TOP - 12, struct.pack("<III", SENTINEL, 0, out))     # ret, param_2 (slot), param_3 (out)
            from unicorn.x86_const import UC_X86_REG_ESP
            uc.reg_write(UC_X86_REG_ESP, STACK_TOP - 12)
            self._regs(uc, ecx=PLAYER)
            uc.emu_start(0x00190E00, SENTINEL, count=10_000)
            self.assertEqual(self._f(uc, out + 8), los_z, "target z = the line of scrimmage read at call time")
            self.assertEqual(self._f(uc, out + 12), 1.0)

    # ------------------------------------------------------------------ the fixer alone, the touchback cave
    def test_fixer_guards(self) -> None:
        labels = self.labels
        cases = {
            "scrimmage play": dict(phase=4, formation_type=1, los_z=F_15YD),
            "no play chosen yet": dict(state_ptr=0xFFFFFFFC, formation_type=1, los_z=F_15YD),
            "null play state": dict(state_ptr=0, formation_type=1, los_z=F_15YD),
            "penalty re-spot (the 3)": dict(formation_type=1, los_z=struct.unpack("<f", struct.pack("<f", 4297.68))[0]),
            "two-point play already at the 2": dict(formation_type=1, los_z=F_2YD),
            "kick already at the 15": dict(formation_type=12, los_z=F_15YD),
        }
        from unicorn.x86_const import UC_X86_REG_ESP
        for label, kwargs in cases.items():
            uc = self._machine()
            self._state(uc, **kwargs)
            before = bytes(uc.mem_read(CTX, 0x40)) + bytes(uc.mem_read(TRANSFORM, 16))
            uc.mem_write(STACK_TOP - 4, struct.pack("<I", SENTINEL))
            uc.reg_write(UC_X86_REG_ESP, STACK_TOP - 4)
            uc.emu_start(labels["fix_pat"], SENTINEL, count=1000)
            self.assertEqual(uc.reg_read(UC_X86_REG_ESP), STACK_TOP, label)
            self.assertEqual(bytes(uc.mem_read(CTX, 0x40)) + bytes(uc.mem_read(TRANSFORM, 16)), before, label)
        uc = self._machine()
        self._state(uc, formation_type=1, los_z=F_15YD, ball_held=0x1234)
        uc.mem_write(STACK_TOP - 4, struct.pack("<I", SENTINEL))
        uc.reg_write(UC_X86_REG_ESP, STACK_TOP - 4)
        uc.emu_start(labels["fix_pat"], SENTINEL, count=1000)
        self.assertEqual(self._f(uc, CTX + 0x18), F_2YD)
        self.assertEqual(self._f(uc, TRANSFORM + 8), F_15YD, "a held ball is not moved")

    def test_touchback_cave_uses_the_35_after_a_kickoff_and_the_retail_20_otherwise(self) -> None:
        from unicorn.x86_const import UC_X86_REG_ESP
        for phase, expected in ((2, 1371.6), (4, 2743.2), (1, 2743.2)):
            for sign in (1.0, -1.0):
                uc = self._machine()
                self._state(uc, phase=phase)
                uc.mem_write(CTX + 0x17C, struct.pack("<f", sign))
                uc.reg_write(UC_X86_REG_ESP, STACK_TOP - 0x40)
                self._regs(uc, edx=CTX)
                uc.emu_start(0x000B63A5, 0x000B63B5, count=1000)         # fld [edx+0x17c]; <hook>; fstp [esp+0x18]
                esp = uc.reg_read(UC_X86_REG_ESP)
                self.assertAlmostEqual(self._f(uc, esp + 0x18), sign * expected, places=2, msg=f"phase {phase} sign {sign}")


if __name__ == "__main__":
    unittest.main()
