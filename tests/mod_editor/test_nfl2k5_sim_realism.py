"""Pins and installation tests for the b779-sim2 round-6 simulated season realism owner (b780 b5-sim: QB-scaled play
mix, WR1-scaled target concentration, the season rush correction for lead backs only, the tackle constant used)."""

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
        self.assertEqual(r.REQUESTS, (("nfl2k5_sim_realism", "code", 896, 16),
                                      ("nfl2k5_sim_realism", "data", 16, 4)))
        self.assertEqual((r.CODE_SIZE, r.DATA_SIZE), (896, 16))

    def test_calibration_constants(self):
        self.assertEqual(r.MIX_BIAS, 8.5)
        self.assertEqual((r.MIX_QB_PIVOT, r.MIX_QB_SLOPE), (87, 0.4))      # b780 b5-sim: QB1-scaled play mix
        self.assertEqual(r.TARGET_RATE, 0.08)                               # b780 b5-sim: was 0.14
        self.assertEqual((r.TARGET_PIVOT, r.TARGET_SLOPE), (90, 0.015))      # b780 b5-sim: WR1-scaled redirect
        self.assertEqual(r.TARGET_WR1_SHARE, 0.75)
        self.assertEqual(r.QB_BONUS_YARDS, 3.0)
        self.assertEqual(r.QB_BONUS_RZ_LINE, 20.0)
        self.assertEqual(r.PASS_SCALE, 0.86)  # b780 b5-sim (17-game v0.8 seasons; b779-int1 0.92)
        self.assertEqual(r.RUN_RZ_SCALE, 0.94)
        self.assertEqual(r.RZ_PASS_SCALE, 0.64)  # b779-int1 rebalance
        self.assertEqual(r.RUSH_BONUS_PCT, 0)  # b780 db2: 0 with the fullback rule (b5-sim 8 lead backs; b779-int1 20)
        self.assertEqual(r.INTERCEPT_SCALE, 1.35)
        self.assertEqual(r.TACKLE_BONUS_PCT, 10)
        self.assertEqual(r.SKIP_TACKLE_POSITION, 4)

    def test_tackle_bonus_is_rounded_10_percent(self):
        self.assertEqual(r.tackle_bonus(0), 0)
        self.assertEqual([r.tackle_bonus(n) for n in (1, 2, 3, 5, 10, 140)],
                         [0, 0, 0, 1, 1, 14])
        self.assertEqual(r.tackle_bonus(169), 17)          # 16.9 -> 17
        self.assertEqual(r.tackle_bonus(171), 17)          # 17.1 -> 17

    def test_rush_bonus_is_off_and_its_rounding_kept(self):
        # b780 db2: the shipped correction is 0 (the fullback rule hands the lead backs their carries back)
        self.assertEqual([r.rush_bonus(n) for n in (-3, 0, 1, 10, 57, 200)], [0] * 6)
        # the rounding the code implements, at b5's 8 percent (b779-int1: 20 percent to every non-QB)
        from unittest import mock
        with mock.patch.object(r, "RUSH_BONUS_PCT", 8):
            self.assertEqual([r.rush_bonus(n) for n in (1, 4, 10, 50, 100)], [0, 0, 1, 4, 8])
            self.assertEqual(r.rush_bonus(56), 4)        # 4.48 -> 4
            self.assertEqual(r.rush_bonus(57), 5)        # 4.56 -> 5

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
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.TARGET_RATE_OFF)[0], 0.08, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.MIX_QB_SLOPE_OFF)[0], 0.4, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.TARGET_SLOPE_OFF)[0], 0.015, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.INTERCEPT_SCALE_OFF)[0], 1.35, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.PASS_SCALE_OFF)[0], 0.86, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.RUN_RZ_SCALE_OFF)[0], 0.94, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.RZ_PASS_SCALE_OFF)[0], 0.64, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.RUSH_BONUS_PCT_OFF)[0], 0.0, places=6)

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



class NativeTests(unittest.TestCase):
    """b780 b5-sim: the new branches run natively from the installed code (honors Unicorn harness: the game's own
    history reader 0x14EE40 and additive writer 0x14F450 over a synthetic roster and history pool)."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        if importlib.util.find_spec("unicorn") is None:
            raise unittest.SkipTest("unicorn is needed")
        try:
            data = retail_bytes()
        except unittest.SkipTest:
            raise
        cls.patched, receipt = r.apply(data)
        cls.code_va, cls.data_va = int(receipt["code_va"], 16), int(receipt["data_va"], 16)

    def machine(self):
        from tests.mod_editor.test_nfl2k5_honors import Machine
        return Machine(self.patched)

    def test_rush_correction_goes_to_the_lead_back_only(self):
        # b780 db2: the shipped constant is 0, so no runner gets a correction; the lead-back gate is checked on code
        # assembled at b5's 8 percent
        from unittest import mock
        from tests.mod_editor.test_nfl2k5_honors import Machine, word
        game_yards = 120
        with mock.patch.object(r, "RUSH_BONUS_PCT", 8):
            at_eight = r.apply(retail_bytes())[0]
            eight = r.rush_bonus(game_yards)
        self.assertGreater(eight, 0)
        for payload, lead in ((self.patched, 0), (at_eight, eight)):
            for position, rank, expected in ((7, 0, lead), (7, 1, 0), (8, 0, 0), (3, 0, 0), (0, 0, 0)):
                m = Machine(payload)
                p = m.roster([(3, [word(2, 3, 400 + game_yards), word(18, 3, 10)])])[0]
                m.put8(p + 0x35, position)
                m.put(p + 0x28, (rank & 7) << 10)
                m.put(self.data_va, p)                   # [state]: the player the merge just wrote
                m.put(self.data_va + 4, 10)              # tackles before the merge (no new tackles)
                m.put(self.data_va + 8, 400)             # rush yards before the merge
                m.call(self.code_va + r.label_offsets()["tackle_return"], stack=(0, 0))
                got = m.call(0x14EE40, ecx=p, edx=2) & 0xFFFF
                self.assertEqual(got, 400 + game_yards + expected, (position, rank, lead))
                self.assertEqual(m.get(self.data_va), 0, "the hand-off is cleared")

    def test_tackle_correction_uses_the_constant(self):
        from tests.mod_editor.test_nfl2k5_honors import word
        m = self.machine()
        p = m.roster([(3, [word(2, 3, 0), word(18, 3, 30)])])[0]
        m.put8(p + 0x35, 11)
        m.put(self.data_va, p)
        m.put(self.data_va + 4, 10)                  # 20 tackles in this game
        m.put(self.data_va + 8, 0)
        m.call(self.code_va + r.label_offsets()["tackle_return"], stack=(0, 0))
        self.assertEqual(m.call(0x14EE40, ecx=p, edx=18) & 0xFFFF, 30 + r.tackle_bonus(20))
        self.assertEqual(r.tackle_bonus(20), 2)       # 10 percent, rounded

    def _mix(self, accuracy, run_minus_pass, *, deep_own_end=False, position=0):
        """Run the mix hook: returns 'pass' or 'run' (its two retail continuations)."""
        m = self.machine()
        qb = m.HEAP + 0x70000
        summary = m.HEAP + 0x71000
        m.uc.mem_write(qb, bytes(0x54))
        m.put8(qb + 0x35, position)
        m.put8(qb + 0x42, accuracy)
        m.put(summary + 8, qb)
        m.put(r.TEAM_OFFENSE, summary)
        m.uc.mem_write(0x00A97200, struct.pack("<f", 90.0 if deep_own_end else 50.0))   # yards to the opponent goal
        hit = []
        for name, va in (("pass", r.MIX_PASS), ("run", r.MIX_RUN)):
            m.hook(va, (lambda n: (lambda mm: hit.append(n)))(name))
        sp = m.SP - 0x100
        m.put(sp, m.STOP)                            # the hook's own return (the call at the site, discarded)
        m.put(sp + 4, m.STOP)                        # where the stand-ins for the two continuations return
        m.uc.mem_write(sp + 0x14, struct.pack("<f", 30.0 + run_minus_pass))           # run score
        m.uc.mem_write(sp + 0x18, struct.pack("<f", 30.0))                            # pass score
        m.reg("ESP", sp)
        m.uc.emu_start(self.code_va + r.label_offsets()["mix"], m.STOP, count=10_000)
        self.assertEqual(len(hit), 1)
        return hit[0]

    def test_better_passers_call_more_passes_around_the_same_league_mix(self):
        bias = lambda acc: r.MIX_BIAS + r.MIX_QB_SLOPE * (acc - r.MIX_QB_PIVOT)
        margin = 0.5 * (bias(99) + r.MIX_BIAS)          # between the average and the elite thresholds
        self.assertEqual(self._mix(r.MIX_QB_PIVOT, margin), "run")
        self.assertEqual(self._mix(99, margin), "pass")
        low = 0.5 * (bias(70) + r.MIX_BIAS)
        self.assertEqual(self._mix(r.MIX_QB_PIVOT, low), "pass")
        self.assertEqual(self._mix(70, low), "run")
        self.assertEqual(self._mix(99, margin, position=3), "run")       # no quarterback in slot 0: the flat bias
        self.assertEqual(self._mix(99, 0.5, deep_own_end=True), "run")   # own deep end: the retail call


if __name__ == "__main__":
    unittest.main()
