"""Pins and installation tests for the b779-sim2 round-6 simulated season realism owner."""

from __future__ import annotations

import ast
import hashlib
import struct
import unittest
from pathlib import Path

from tests.nfl2k5_supersim_draft_fixture import retail_bytes

from mod_editor.core import nfl2k5_sim_realism as r
from mod_editor.core.nfl2k5_cave_oracle import XbeImage


class ConstantTests(unittest.TestCase):
    def test_owner_and_allocation_request(self):
        self.assertEqual(r.OWNER, "nfl2k5_sim_realism")
        self.assertEqual(r.REQUESTS, (("nfl2k5_sim_realism", "code", 832, 16),
                                      ("nfl2k5_sim_realism", "data", 16, 4)))
        self.assertEqual((r.CODE_SIZE, r.DATA_SIZE), (832, 16))

    def test_calibration_constants(self):
        self.assertEqual(r.MIX_BIAS, 8.5)
        self.assertEqual(r.TARGET_RATE, 0.14)
        self.assertEqual(r.TARGET_WR1_SHARE, 0.75)
        self.assertEqual(r.QB_BONUS_YARDS, 3.0)
        self.assertEqual(r.QB_BONUS_RZ_LINE, 20.0)
        self.assertEqual(r.PASS_SCALE, 0.92)  # b779-int1 rebalance
        self.assertEqual(r.RUN_RZ_SCALE, 0.94)
        self.assertEqual(r.RZ_PASS_SCALE, 0.64)  # b779-int1 rebalance
        self.assertEqual(r.RUSH_BONUS_PCT, 20)  # b779-int1 rebalance
        self.assertEqual(r.INTERCEPT_SCALE, 1.35)
        self.assertEqual(r.TACKLE_BONUS_PCT, 10)
        self.assertEqual(r.SKIP_TACKLE_POSITION, 4)

    def test_tackle_bonus_is_rounded_10_percent(self):
        self.assertEqual(r.tackle_bonus(0), 0)
        self.assertEqual([r.tackle_bonus(n) for n in (1, 2, 3, 5, 10, 140)],
                         [0, 0, 0, 1, 1, 14])
        self.assertEqual(r.tackle_bonus(169), 17)          # 16.9 -> 17
        self.assertEqual(r.tackle_bonus(171), 17)          # 17.1 -> 17

    def test_rush_bonus_is_rounded_20_percent(self):
        # b779-int1 rebalance: 13 -> 20 percent (with every sim owner installed, 13 left 8-10 backs over 1,000 yards)
        self.assertEqual(r.rush_bonus(0), 0)
        self.assertEqual(r.rush_bonus(-3), 0)
        self.assertEqual([r.rush_bonus(n) for n in (1, 4, 10, 50, 100)],
                         [0, 1, 2, 10, 20])
        self.assertEqual(r.rush_bonus(152), 30)            # 30.4 -> 30
        self.assertEqual(r.rush_bonus(153), 31)            # 30.6 -> 31

    def test_red_zone_scales_split_run_and_pass(self):
        self.assertEqual([r.run_rz_scale(s) for s in (None, 1, 20, 21, 80)],
                         [1.0, 0.94, 0.94, 1.0, 1.0])        # round 6: near-retail red-zone runs
        self.assertEqual([r.pass_rz_scale(s) for s in (None, 1, 20, 21, 80)],
                         [1.0, 0.64, 0.64, 1.0, 1.0])        # the scoring cut is red-zone passes
        self.assertLess(r.pass_rz_scale(10), r.run_rz_scale(10))
        self.assertGreater(r.run_rz_scale(10), 0.9)

    def test_qb_carry_rate_follows_the_scramble_byte(self):
        self.assertEqual(r.qb_carry_rate(20), 0.0)
        self.assertEqual(r.qb_carry_rate(45), 0.0)
        self.assertAlmostEqual(r.qb_carry_rate(57), 12 * 0.0036, places=6)
        self.assertAlmostEqual(r.qb_carry_rate(72), 27 * 0.0036, places=6)
        self.assertAlmostEqual(r.qb_carry_rate(99), 32 * 0.0036, places=6)   # cap
        self.assertLess(r.qb_carry_rate(50), r.qb_carry_rate(65))


class SiteTests(unittest.TestCase):
    def test_every_retail_site_is_pinned(self):
        edits = r.sites(0x14DA000)
        self.assertEqual(len(edits), 10)
        self.assertEqual(edits[0][0], "mix")
        self.assertEqual(edits[0][1], 0x106FFD)
        self.assertEqual(edits[0][2], bytes.fromhex("f6c4410f84f4fcffff"))
        self.assertEqual(edits[1][:3], ("qb", 0x106CFF, bytes.fromhex("8b3da071a900")))
        self.assertEqual(edits[2][:3], ("target", 0x107035, bytes.fromhex("e886c4ffff")))
        self.assertEqual(edits[3][:3], ("intercept", 0x102C83, bytes.fromhex("b9a0fce500")))
        self.assertEqual(edits[4][:3], ("tackle_entry", 0x1334D3, bytes.fromhex("8d9424dc000000")))
        self.assertEqual(edits[5][:3], ("tackle_return", 0x133798, bytes.fromhex("c208009090")))
        self.assertEqual(edits[6][:3], ("run_bonus", 0x107CFE, bytes.fromhex("8b038b4c2410")))
        self.assertEqual([e[0] for e in edits[7:]], ["pass_scale_0", "pass_scale_1", "pass_scale_2"])

    def test_sites_are_the_same_length_and_hook_the_code(self):
        for label, va, before, after in r.sites(0x14DA000):
            self.assertEqual(len(after), len(before), label)
            if label == "tackle_return":
                rel = struct.unpack_from("<i", after, 1)[0]
                self.assertEqual((va + 5 + rel) & 0xFFFFFFFF, 0x14DA000 + r.label_offsets()["tackle_return"])
            elif label.startswith("pass_scale"):
                rel = struct.unpack_from("<i", after, 1)[0]
                self.assertEqual((va + 5 + rel) & 0xFFFFFFFF,
                                 0x14DA000 + r.label_offsets()["pass_scale"])
            elif label == "run_bonus":
                rel = struct.unpack_from("<i", after, 1)[0]
                self.assertEqual((va + 5 + rel) & 0xFFFFFFFF,
                                 0x14DA000 + r.label_offsets()["qb_bonus"])
            elif label == "mix":
                rel = struct.unpack_from("<i", after, 1)[0]
                self.assertEqual((va + 5 + rel) & 0xFFFFFFFF, 0x14DA000)
            else:
                rel = struct.unpack_from("<i", after, 1)[0]
                target = (va + 5 + rel) & 0xFFFFFFFF
                self.assertGreaterEqual(target, 0x14DA000, label)
                self.assertLess(target, 0x14DA000 + r.CODE_SIZE, label)


class CodeTests(unittest.TestCase):
    def test_code_is_fixed_size_and_starts_with_the_mix_hook(self):
        code = r.code_for(0x14DA000, 0x14DC000)
        self.assertEqual(len(code), r.CODE_SIZE)
        self.assertEqual(code[:6], bytes.fromhex("d9050072a900"))
        # the QB carrier tail starts with pushad and reads the offense summary
        self.assertEqual(code[r.label_offsets()["qb"]:r.label_offsets()["qb"] + 6], bytes.fromhex("60a19c71a900"))
        # the float pool carries the calibrated constants
        import struct as _s
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.MIX_BIAS_OFF)[0], 8.5, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.TARGET_RATE_OFF)[0], 0.14, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.INTERCEPT_SCALE_OFF)[0], 1.35, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.PASS_SCALE_OFF)[0], 0.92, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.RUN_RZ_SCALE_OFF)[0], 0.94, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.RZ_PASS_SCALE_OFF)[0], 0.64, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.RUSH_BONUS_PCT_OFF)[0], 20.0, places=6)

    def test_code_has_no_self_reference_shortcut(self):
        # A different data VA must move every scratch reference.
        a = r.code_for(0x14DA000, 0x14DC000)
        b = r.code_for(0x14DA000, 0x14DE000)
        self.assertNotEqual(a, b)
        self.assertEqual(a[:0x20], b[:0x20])       # the mix path has no state reference

    def test_source_has_no_comments_or_docstring_shortcuts(self):
        # The implementation must stay uncompiled, readable and free of build-time dependencies.
        path = Path(r.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        mods = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)}
        self.assertIn("hashlib", mods)
        self.assertIn("struct", mods)


class InstallTests(unittest.TestCase):
    def test_apply_is_read_back_and_idempotent(self):
        data = retail_bytes()
        if data is None:
            self.skipTest("private USA retail XBE is absent")
        self.assertEqual(r.status(data), "retail")
        patched, receipt = r.apply(data)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(r.status(patched), "applied")
        image = XbeImage(patched)
        code_va = int(receipt["code_va"], 16)
        data_va = int(receipt["data_va"], 16)
        self.assertEqual(image.read(0x106FFD, 9)[0], 0xE8)
        self.assertEqual(image.read(0x133798, 5)[0], 0xE9)
        self.assertEqual(hashlib.sha256(image.read(code_va, r.CODE_SIZE)).digest(),
                         hashlib.sha256(r.code_for(code_va, data_va)).digest())
        self.assertEqual(bytes(image.read(data_va, r.DATA_SIZE)), b"\0" * r.DATA_SIZE)
        again, second = r.apply(patched)
        self.assertEqual(again, patched)
        self.assertEqual(second["status"], "already_applied")

    def test_apply_reuses_the_allocation_a_full_build_made(self):
        # b779-int1: the build allocates the owner with the selected request set before this step installs it
        from mod_editor.core import nfl2k5_xbe_space as space
        data = retail_bytes()
        allocated, _ = space.apply(data, r.REQUESTS, scaleout=True)
        self.assertEqual(r.status(allocated), "retail")
        patched, receipt = r.apply(allocated)
        self.assertEqual(r.status(patched), "applied")
        self.assertEqual(r.apply(patched)[1]["status"], "already_applied")

    def test_foreign_site_is_refused(self):
        data = retail_bytes()
        if data is None:
            self.skipTest("private USA retail XBE is absent")
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        image = XbeImage(data)
        buf = bytearray(data)
        off = image.offset(0x106FFD, 4)
        buf[off:off + 4] = b"\x90" * 4
        for section in _sections(buf):
            buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
        self.assertEqual(r.status(bytes(buf)), "foreign")
        with self.assertRaises(r.SimRealismError):
            r.apply(bytes(buf))


if __name__ == "__main__":
    unittest.main()
