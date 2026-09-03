"""The overtime patch must stay pattern-driven, fail-closed and byte-exact.

Fixtures are synthetic: a minimal XBE with a valid 22-section table whose `.text` section
carries the retail bytes at every hook site plus the two dead functions that host the caves,
with a correct section digest.  No game file is touched; a retail-XBE smoke test runs only when
the private copy exists.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_overtime as ot  # noqa: E402

IMAGE_BASE = strength.IMAGE_BASE
TABLE_OFF = 0x200
HEADER_SIZE = 0xCC4
TEXT_VA = 0x11000
TEXT_RAW = 0x2000
TEXT_SIZE = 0x320000
RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")


def _section_digest(payload: bytes, raw: int, raw_size: int) -> bytes:
    return hashlib.sha1(  # nosec B324 - XBE section scheme, not security
        struct.pack("<I", raw_size) + payload[raw: raw + raw_size]
    ).digest()


def _text_off(va: int) -> int:
    return TEXT_RAW + (va - TEXT_VA)


def _retail_sites() -> list[tuple[int, bytes]]:
    return [(ot.MAIN_CAVE_VA, ot.RETAIL_MAIN_CAVE), (ot.AUX_CAVE_VA, ot.RETAIL_AUX_CAVE),
            (ot.INIT_SITE_VA, ot.RETAIL_INIT), (ot.OT_KICKOFF_SITE_VA, ot.RETAIL_OT_KICKOFF),
            (ot.KICKOFF_SITE_VA, ot.RETAIL_KICKOFF), (ot.PRED_SITE_VA, ot.RETAIL_PRED),
            (ot.EXPIRY_SITE_VA, ot.RETAIL_EXPIRY), (ot.EXPIRY2_SITE_VA, ot.RETAIL_EXPIRY2),
            (ot.SIM_RESET_SITE_VA, ot.RETAIL_SIM_RESET), (ot.SIM_ROLL_SITE_VA, ot.RETAIL_SIM_ROLL),
            (ot.SIM_TIE_SITE_VA, ot.RETAIL_SIM_TIE), (ot.SIM_PERIOD_SITE_VA, ot.RETAIL_SIM_PERIOD)]


def _build_synthetic_xbe() -> bytes:
    buf = bytearray(TEXT_RAW + TEXT_SIZE)
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
        struct.pack_into(strength.SECTION_TABLE_FIELDS, buf, header, *fields)
    for va, retail in _retail_sites():
        buf[_text_off(va): _text_off(va) + len(retail)] = retail
    header = TABLE_OFF
    buf[header + 36: header + 56] = _section_digest(bytes(buf), TEXT_RAW, TEXT_SIZE)
    return bytes(buf)


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


class ScaleTests(unittest.TestCase):
    def test_scale_is_nfl_minutes_over_a_quarter(self) -> None:
        self.assertAlmostEqual(ot.scale_for(10), 10 / 15)
        self.assertAlmostEqual(ot.scale_for(15), 1.0)
        self.assertEqual(ot.overtime_clock_seconds(15, 10), 600.0)      # 15-minute quarters: 10:00
        self.assertEqual(ot.overtime_clock_seconds(5, 10), 200.0)       # retail default 5-minute quarters: 3:20
        self.assertEqual(ot.overtime_clock_seconds(5, 15), 300.0)       # retail behaviour

    def test_minutes_are_validated(self) -> None:
        for bad in (0, 0.5, 16, -3, "x"):
            with self.assertRaises((ot.OvertimeError, ValueError, TypeError)):
                ot.scale_for(bad)


class CaveShapeTests(unittest.TestCase):
    def test_caves_fit_their_dead_functions(self) -> None:
        main = ot.main_cave_bytes()
        aux = ot.aux_cave_bytes()
        self.assertEqual(len(main), ot.MAIN_CAVE_SIZE)
        self.assertEqual(len(aux), ot.AUX_CAVE_SIZE)
        self.assertEqual(len(ot.RETAIL_MAIN_CAVE), ot.MAIN_CAVE_SIZE)
        self.assertEqual(len(ot.RETAIL_AUX_CAVE), ot.AUX_CAVE_SIZE)
        self.assertTrue(main.endswith(b"\xcc"))
        self.assertTrue(aux.endswith(b"\xcc"))
        for retail in (ot.RETAIL_MAIN_CAVE, ot.RETAIL_AUX_CAVE):
            self.assertEqual(retail[:3], bytes.fromhex("558bec"), "cave hosts start with push ebp / mov ebp, esp")
        self.assertEqual(ot.RETAIL_MAIN_CAVE[-1:], b"\xc3")
        self.assertEqual(ot.RETAIL_AUX_CAVE[-3:], bytes.fromhex("c20400"))

    def test_scale_float_is_the_only_setting_dependent_byte_run(self) -> None:
        default = ot.main_cave_bytes(10)
        other = ot.main_cave_bytes(12)
        self.assertNotEqual(default[:4], other[:4])
        self.assertEqual(default[4:], other[4:])
        self.assertEqual(struct.unpack("<f", default[:4])[0], _f32(10 / 15))
        self.assertEqual(ot.aux_cave_bytes(), ot.aux_cave_bytes())

    def test_labels_and_cross_cave_calls_resolve(self) -> None:
        labels = ot.cave_labels()
        for name in ("init", "flag_team", "ot_check", "not_over", "over", "ot_expiry", "exp_tied", "exp_differ"):
            self.assertTrue(ot.MAIN_CODE_VA <= labels[name] < ot.MAIN_CAVE_VA + ot.MAIN_CAVE_SIZE, name)
        for name in ("ot_kickoff", "kickoff_flag", "sim_reset", "sim_roll", "sim_tie", "sim_period"):
            self.assertTrue(ot.AUX_CAVE_VA <= labels[name] < ot.AUX_CAVE_VA + ot.AUX_CAVE_SIZE, name)
        aux = ot.aux_cave_bytes()
        # every call in the aux cave targets flag_team in the main cave or a kick-setup tail jump
        calls = []
        i = 0
        while i < len(aux) - 5:
            if aux[i] in (0xE8, 0xE9):
                rel = struct.unpack_from("<i", aux, i + 1)[0]
                target = ot.AUX_CAVE_VA + i + 5 + rel
                if target in (labels["flag_team"], ot.FN_KICK_SETUP):
                    calls.append((aux[i], target))
            i += 1
        self.assertIn((0xE8, labels["flag_team"]), calls)
        self.assertIn((0xE9, ot.FN_KICK_SETUP), calls)
        self.assertGreaterEqual(sum(1 for op, t in calls if op == 0xE9 and t == ot.FN_KICK_SETUP), 2)

    def test_main_cave_entry_points_have_the_expected_shape(self) -> None:
        labels = ot.cave_labels()
        main = ot.main_cave_bytes()
        init = labels["init"] - ot.MAIN_CAVE_VA
        self.assertEqual(main[init: init + 6], ot.RETAIL_INIT, "init replays the displaced fstp")
        self.assertEqual(main[init + 6: init + 16], bytes.fromhex("c705") + struct.pack("<I", ot.STATE_GLOBAL) + b"\0\0\0\0")
        self.assertEqual(main[init + 16], 0xC3)
        check = labels["ot_check"] - ot.MAIN_CAVE_VA
        self.assertEqual(main[check: check + 8], b"\xa1" + struct.pack("<I", ot.PERIOD_GLOBAL) + bytes.fromhex("83f805"))
        not_over = labels["not_over"] - ot.MAIN_CAVE_VA
        self.assertEqual(main[not_over: not_over + 9], b"\xa1" + struct.pack("<I", ot.PERIOD_GLOBAL) + bytes.fromhex("83fc00c3"))
        over = labels["over"] - ot.MAIN_CAVE_VA
        self.assertEqual(main[over: over + 8], b"\xa1" + struct.pack("<I", ot.PERIOD_GLOBAL) + bytes.fromhex("39c0c3"))
        expiry = labels["ot_expiry"] - ot.MAIN_CAVE_VA
        self.assertEqual(main[expiry: expiry + 3], bytes.fromhex("505152"), "expiry preserves eax/ecx/edx")
        tied = labels["exp_tied"] - ot.MAIN_CAVE_VA
        self.assertEqual(main[tied: tied + 6], bytes.fromhex("5a595839c0c3"))
        aux = ot.aux_cave_bytes()
        period = labels["sim_period"] - ot.AUX_CAVE_VA
        self.assertEqual(aux[period], 0x9C, "sim_period saves the flags of the compare it interrupts (pushfd)")
        self.assertEqual(aux[period + 1: period + 11], ot.RETAIL_SIM_PERIOD, "and replays the displaced 1.0 store")
        done = labels["sp_done"] - ot.AUX_CAVE_VA
        self.assertEqual(aux[done: done + 2], bytes.fromhex("9dc3"), "popfd; ret")
        for name in ("sim_reset", "sim_roll", "sim_tie"):
            off = labels[name] - ot.AUX_CAVE_VA
            self.assertNotEqual(aux[off], 0x9C, f"{name} has no flag consumer after it and stays cheap")


class SyntheticXbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _build_synthetic_xbe()

    def test_status_apply_round_trip(self) -> None:
        self.assertEqual(ot.status(self.payload), "retail")
        patched, receipt = ot.apply(self.payload)
        self.assertEqual(ot.status(patched), "applied")
        self.assertEqual(receipt["sections_repinned"], [0])
        settings = ot.read_settings(patched)
        self.assertEqual(settings, {"status": "applied", "regular_minutes": 10.0, "both_possessions": True,
                                    "postseason_no_ties": True, "sim_engine": True})
        with self.assertRaises(ot.OvertimeError):
            ot.apply(patched)

    def test_only_the_sites_and_the_text_digest_change(self) -> None:
        patched, receipt = ot.apply(self.payload)
        labels = ot.cave_labels()
        expected = {
            _text_off(ot.MAIN_CAVE_VA): ot.main_cave_bytes(10),
            _text_off(ot.AUX_CAVE_VA): ot.aux_cave_bytes(),
            _text_off(ot.INIT_SITE_VA): ot._rel32_call(ot.INIT_SITE_VA, labels["init"]) + b"\x90",
            _text_off(ot.OT_KICKOFF_SITE_VA): ot._rel32_call(ot.OT_KICKOFF_SITE_VA, labels["ot_kickoff"]),
            _text_off(ot.KICKOFF_SITE_VA): ot._rel32_call(ot.KICKOFF_SITE_VA, labels["kickoff_flag"]),
            _text_off(ot.SIM_RESET_SITE_VA): ot._rel32_call(ot.SIM_RESET_SITE_VA, labels["sim_reset"]) + b"\x90",
            _text_off(ot.SIM_ROLL_SITE_VA): ot._rel32_call(ot.SIM_ROLL_SITE_VA, labels["sim_roll"]) + b"\x90\x90",
            _text_off(ot.SIM_PERIOD_SITE_VA): ot._rel32_call(ot.SIM_PERIOD_SITE_VA, labels["sim_period"]) + b"\x90" * 5,
        }
        # the three multi-instruction sites: call + conditional jump to the retail targets + nops
        pred = patched[_text_off(ot.PRED_SITE_VA): _text_off(ot.PRED_SITE_VA) + len(ot.RETAIL_PRED)]
        self.assertEqual(pred[:5], ot._rel32_call(ot.PRED_SITE_VA, labels["ot_check"]))
        self.assertEqual(pred[5], 0x74)
        self.assertEqual(ot.PRED_SITE_VA + 7 + struct.unpack_from("<b", pred, 6)[0], ot.PRED_GAME_OVER_VA)
        self.assertEqual(pred[7:10], bytes.fromhex("83f804"))
        self.assertEqual(pred[10], 0x75)
        self.assertEqual(ot.PRED_SITE_VA + 12 + struct.unpack_from("<b", pred, 11)[0], ot.PRED_CONTINUE_VA)
        self.assertEqual(pred[12:], b"\x90" * (len(ot.RETAIL_PRED) - 12))
        for site, retail, target in ((ot.EXPIRY_SITE_VA, ot.RETAIL_EXPIRY, ot.EXPIRY_DIFFER_VA),
                                     (ot.EXPIRY2_SITE_VA, ot.RETAIL_EXPIRY2, ot.EXPIRY2_DIFFER_VA)):
            got = patched[_text_off(site): _text_off(site) + len(retail)]
            self.assertEqual(got[:5], ot._rel32_call(site, labels["ot_expiry"]))
            self.assertEqual(got[5], 0x75)
            self.assertEqual(site + 7 + struct.unpack_from("<b", got, 6)[0], target)
            self.assertEqual(got[7:], b"\x90" * (len(retail) - 7))
            expected[_text_off(site)] = got
        tie = patched[_text_off(ot.SIM_TIE_SITE_VA): _text_off(ot.SIM_TIE_SITE_VA) + len(ot.RETAIL_SIM_TIE)]
        self.assertEqual(tie[:5], ot._rel32_call(ot.SIM_TIE_SITE_VA, labels["sim_tie"]))
        self.assertEqual(tie[5], 0x75)
        self.assertEqual(ot.SIM_TIE_SITE_VA + 7 + struct.unpack_from("<b", tie, 6)[0], ot.SIM_TIE_CONTINUE_VA)
        self.assertEqual(tie[7:], b"\x90\x90")
        expected[_text_off(ot.PRED_SITE_VA)] = pred
        expected[_text_off(ot.SIM_TIE_SITE_VA)] = tie
        allowed = set()
        for off, blob in expected.items():
            self.assertEqual(patched[off: off + len(blob)], blob, hex(off))
            allowed.update(range(off, off + len(blob)))
        allowed.update(range(TABLE_OFF + 36, TABLE_OFF + 56))
        changed = {i for i, (a, b) in enumerate(zip(self.payload, patched)) if a != b}
        self.assertTrue(changed <= allowed, sorted(hex(i) for i in changed - allowed)[:10])
        self.assertEqual(patched[TABLE_OFF + 36: TABLE_OFF + 56], _section_digest(patched, TEXT_RAW, TEXT_SIZE))
        self.assertEqual(receipt["changed_bytes"], len(changed))

    def test_hook_lengths_match_the_displaced_retail_bytes(self) -> None:
        for _g, label, off, before, after in ot._sites(self.payload, 10, True, True, True):
            self.assertEqual(len(before), len(after), label)

    def test_optional_groups_can_stay_retail(self) -> None:
        patched, receipt = ot.apply(self.payload, 10, both_possessions=False, postseason_no_ties=False, sim_engine=False)
        self.assertEqual(ot.status(patched), "applied")
        settings = ot.read_settings(patched)
        self.assertEqual(settings["both_possessions"], False)
        self.assertEqual(settings["postseason_no_ties"], False)
        self.assertEqual(settings["sim_engine"], False)
        for va, retail in ((ot.PRED_SITE_VA, ot.RETAIL_PRED), (ot.KICKOFF_SITE_VA, ot.RETAIL_KICKOFF),
                           (ot.EXPIRY_SITE_VA, ot.RETAIL_EXPIRY), (ot.EXPIRY2_SITE_VA, ot.RETAIL_EXPIRY2),
                           (ot.SIM_RESET_SITE_VA, ot.RETAIL_SIM_RESET), (ot.SIM_ROLL_SITE_VA, ot.RETAIL_SIM_ROLL),
                           (ot.SIM_TIE_SITE_VA, ot.RETAIL_SIM_TIE), (ot.SIM_PERIOD_SITE_VA, ot.RETAIL_SIM_PERIOD)):
            self.assertEqual(patched[_text_off(va): _text_off(va) + len(retail)], retail, hex(va))
        labels = {e["label"] for e in receipt["edits"]}
        self.assertEqual(labels, {"main_cave", "aux_cave", "init_hook", "ot_kickoff_hook"})

    def test_other_minutes_change_only_the_scale_float(self) -> None:
        default, _ = ot.apply(self.payload, 10)
        other, _ = ot.apply(self.payload, 12)
        diff = {i for i, (a, b) in enumerate(zip(default, other)) if a != b}
        scale = set(range(_text_off(ot.SCALE_VA), _text_off(ot.SCALE_VA) + 4))
        digest = set(range(TABLE_OFF + 36, TABLE_OFF + 56))
        self.assertTrue(diff <= scale | digest)
        self.assertEqual(ot.read_settings(other)["regular_minutes"], 12.0)
        retail_length, _ = ot.apply(self.payload, 15)
        self.assertEqual(struct.unpack_from("<f", retail_length, _text_off(ot.SCALE_VA))[0], 1.0)

    def test_foreign_bytes_are_refused(self) -> None:
        for va, _retail in _retail_sites():
            broken = bytearray(self.payload)
            broken[_text_off(va)] ^= 0xFF
            self.assertEqual(ot.status(bytes(broken)), "foreign", hex(va))
            with self.assertRaises(ot.OvertimeError):
                ot.apply(bytes(broken))
        self.assertEqual(ot.status(b"\x00" * 0x1000), "foreign")

    def test_half_applied_group_is_foreign(self) -> None:
        patched, _ = ot.apply(self.payload)
        broken = bytearray(patched)
        off = _text_off(ot.KICKOFF_SITE_VA)
        broken[off: off + len(ot.RETAIL_KICKOFF)] = ot.RETAIL_KICKOFF
        self.assertEqual(ot.status(bytes(broken)), "foreign")

    def test_settings_are_validated(self) -> None:
        for bad in (0, 20, -1):
            with self.assertRaises(ot.OvertimeError):
                ot.apply(self.payload, bad)


@unittest.skipUnless(RETAIL_XBE.exists(), "private retail default.xbe not present")
class RetailXbeSmokeTests(unittest.TestCase):
    def test_retail_image_is_recognised_and_patches_cleanly(self) -> None:
        payload = RETAIL_XBE.read_bytes()
        self.assertEqual(ot.status(payload), "retail")
        patched, receipt = ot.apply(payload)
        self.assertEqual(ot.status(patched), "applied")
        self.assertEqual(receipt["sections_repinned"], [0])
        self.assertLess(receipt["changed_bytes"], 700)
        self.assertEqual(ot.read_settings(patched)["regular_minutes"], 10.0)
        # the state dword lives in .data's BSS tail: mapped at runtime, absent from the file
        sizes = {s.virtual_address: (s, struct.unpack_from("<I", payload, s.header_offset + 8)[0])
                 for s in strength._sections(payload)}
        data, vsize = next((s, v) for s, v in sizes.values() if s.virtual_address <= ot.STATE_GLOBAL < s.virtual_address + v)
        self.assertGreaterEqual(ot.STATE_GLOBAL - data.virtual_address, data.raw_size)
        self.assertLess(ot.STATE_GLOBAL + 4, data.virtual_address + vsize)


if __name__ == "__main__":
    unittest.main()
