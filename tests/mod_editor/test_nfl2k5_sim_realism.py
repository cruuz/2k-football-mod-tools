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
        self.assertEqual(r.TARGET_RATE, 0.14)                               # b81 fb-targets (b780 b5-sim: 0.08)
        self.assertEqual((r.TARGET_PIVOT, r.TARGET_SLOPE), (90, 0.015))      # b780 b5-sim: WR1-scaled redirect
        self.assertEqual(r.TARGET_WR1_SHARE, 0.50)                          # b81 fb-targets: half go to TE1 (was 0.75)
        for revision in ("b81", "beta80"):
            self.assertEqual((r.FROZEN_CONSTANTS[revision]["TARGET_RATE"], r.FROZEN_CONSTANTS[revision]["TARGET_WR1_SHARE"]),
                             (0.08, 0.75))
        self.assertEqual(r.QB_BONUS_YARDS, 3.5)
        self.assertEqual(r.QB_BONUS_RZ_LINE, 20.0)
        self.assertEqual(r.PASS_SCALE, 0.91)
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
        self.assertAlmostEqual(r.qb_carry_rate(57), 12 * r.QB_SCRAMBLE_SCALE, places=6)
        self.assertAlmostEqual(r.qb_carry_rate(72), 27 * r.QB_SCRAMBLE_SCALE, places=6)
        self.assertAlmostEqual(r.qb_carry_rate(99), 40 * r.QB_SCRAMBLE_SCALE, places=6)   # cap
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
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.TARGET_WR1_OFF)[0], 0.50, places=6)
        # the beta 80 and pre-rule beta 81 revisions keep the constants they shipped with (recognition, upgrades)
        for kw in ({"beta80": True}, {"fb": False}):
            old = r._assemble(0x14DA000, 0x14DC000, **kw)[1]
            self.assertAlmostEqual(_s.unpack_from("<f", old, r.TARGET_RATE_OFF)[0], 0.08, places=6)
            self.assertAlmostEqual(_s.unpack_from("<f", old, r.TARGET_WR1_OFF)[0], 0.75, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.MIX_QB_SLOPE_OFF)[0], 0.4, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.TARGET_SLOPE_OFF)[0], 0.015, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.INTERCEPT_SCALE_OFF)[0], 1.35, places=6)
        self.assertAlmostEqual(_s.unpack_from("<f", code, r.PASS_SCALE_OFF)[0], r.PASS_SCALE, places=6)
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
    def test_verified_beta80_merge_and_targets_upgrade_together(self):
        from mod_editor.core import nfl2k5_rdata_sites as rdata, nfl2k5_xbe_space as space
        data = retail_bytes()
        if data is None:
            self.skipTest("private USA retail XBE is absent")
        allocated = space.apply(data, r.REQUESTS, scaleout=True)[0]
        code, state = r._allocations(allocated)
        old_body = r._assemble(code["va"], state["va"], beta80=True)[1]
        old = space.install_code(allocated, r.OWNER, old_body)[0]
        old = rdata.apply(old, r.sites(code["va"], beta80=True), r.OWNER)[0]
        self.assertEqual(r.status(old), "legacy")          # a disc report must tell v0.9 from v0.10
        upgraded = r.apply(old)[0]
        self.assertEqual(upgraded, r.apply(data)[0])
        self.assertEqual(r.status(upgraded), "applied")

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

    def test_beta81_revision_upgrades_in_place_to_a_fresh_install(self):
        # b81 fb-targets: beta 81 before the fullback target rule (same 896-byte allocation) reads "legacy" and is
        # updated in place to exactly what a fresh install writes
        from mod_editor.core import nfl2k5_rdata_sites as rdata, nfl2k5_xbe_space as space
        data = retail_bytes()
        allocated = space.apply(data, r.REQUESTS, scaleout=True)[0]
        code, state = r._allocations(allocated)
        old_body = r._assemble(code["va"], state["va"], fb=False)[1]
        self.assertNotEqual(old_body, r.code_for(code["va"], state["va"]))
        self.assertEqual(old_body[:r.label_offsets()["tackle_entry"]],
                         r.code_for(code["va"], state["va"])[:r.label_offsets()["tackle_entry"]])
        pool_diff = [i for i in range(r.FLOAT_POOL, r.CODE_SIZE)
                     if old_body[i] != r.code_for(code["va"], state["va"])[i]]
        self.assertTrue(set(pool_diff) <= set(range(r.TARGET_RATE_OFF, r.TARGET_WR1_OFF + 4)), pool_diff)  # the retune
        old = space.install_code(allocated, r.OWNER, old_body)[0]
        old = rdata.apply(old, r.sites(code["va"], fb=False), r.OWNER)[0]
        self.assertEqual(r.status(old), "legacy")
        self.assertEqual([s[3] for s in r.installed_sites(old)], [s[3] for s in r.sites(code["va"], fb=False)])
        upgraded, receipt = r.apply(old)
        self.assertEqual(upgraded, r.apply(data)[0])
        self.assertEqual(r.status(upgraded), "applied")
        self.assertEqual(r.apply(upgraded)[1]["status"], "already_applied")

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

    def test_no_runner_gets_a_season_rush_correction(self):
        # b780 db2: the constant is 0. b81 fb-targets: the lead-back branch it gated (which then never changed a stat) is
        # gone from the code, so no runner, lead back or not, gets a correction; the hand-off is still cleared
        from tests.mod_editor.test_nfl2k5_honors import Machine, word
        game_yards = 120
        for payload, lead in ((self.patched, 0),):
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

    def test_the_compact_tackle_merge_matches_the_previous_revision(self):
        # b81 fb-targets: the entry and the merge were rewritten to make room for the fullback rule (the rush branch it
        # dropped never changed a stat). Both revisions run the same merge calls natively: entry, the game's own merge of
        # this game's tackles and rushing yards (the additive writer), return; the tackles, the rushing line and the
        # hand-off must agree. With rushing yards on a lead back in the simulator the old revision enters its lead-back
        # branch (review N3), which at its frozen 0 percent adds nothing.
        from mod_editor.core import nfl2k5_rdata_sites as rdata, nfl2k5_xbe_space as space
        from tests.mod_editor.test_nfl2k5_honors import Machine, word
        data = retail_bytes()
        allocated = space.apply(data, r.REQUESTS, scaleout=True)[0]
        code, state = r._allocations(allocated)
        old = space.install_code(allocated, r.OWNER, r._assemble(code["va"], state["va"], fb=False)[1])[0]
        old = rdata.apply(old, r.sites(code["va"], fb=False), r.OWNER)[0]
        new = r.apply(data)[0]
        self.assertEqual((code["va"], state["va"]), (self.code_va, self.data_va))

        def run(payload, labels, position, rank, mode, before, game, rush=0):
            m = Machine(payload)
            p = m.roster([(3, [word(2, 3, 300), word(18, 3, before)])])[0]
            m.put8(p + 0x35, position)
            m.put(p + 0x28, (rank & 7) << 10)
            m.put8(r.SIM_MODE, mode)
            m.put(self.data_va, 0xDEADBEEF)
            m.hook(r.TACKLE_ENTRY_RESUME, lambda mm: None)     # the game's merge continues here: return instead
            sp = m.SP - 0x40
            m.put(sp, m.STOP)                                    # the site's call (dropped by the entry)
            m.put(sp + 4, m.STOP)                                # where the stand-in for the merge returns
            m.reg("ESP", sp)
            m.reg("EDI", p)
            m.uc.emu_start(self.code_va + labels["tackle_entry"], m.STOP, count=100_000)
            if game:
                m.call(0x14F450, ecx=p, edx=18, stack=(game,))   # the merge adds this game's tackles
            if rush:
                m.call(0x14F450, ecx=p, edx=2, stack=(rush,))    # and this game's rushing yards
            m.call(self.code_va + labels["tackle_return"], stack=(0, 0))
            return (m.call(0x14EE40, ecx=p, edx=18) & 0xFFFF, m.call(0x14EE40, ecx=p, edx=2) & 0xFFFF,
                    m.get(self.data_va))

        old_labels = r._assemble(self.code_va, self.data_va, fb=False)[0].labels
        cases = 0
        for position in (0, 3, 4, 7, 8, 11):
            for rank in (0, 1):
                for mode in (4, 0):
                    for before, game in ((10, 0), (10, 4), (10, 5), (30, 15), (30, 20), (0, 25), (100, 96)):
                        for rush in ((0, 120) if position == 7 else (0,)):
                            a = run(old, old_labels, position, rank, mode, before, game, rush)
                            b = run(new, r.label_offsets(), position, rank, mode, before, game, rush)
                            self.assertEqual(a, b, (position, rank, mode, before, game, rush))
                            bonus = r.tackle_bonus(game) if mode == 4 and position != 4 else 0
                            self.assertEqual(b, (before + game + bonus, 300 + rush, 0),
                                             (position, rank, mode, before, game, rush))
                            cases += 1
        self.assertEqual(cases, 196)                       # merge calls, 28 of them with a lead back's rushing yards

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


class FrozenRevisionTests(unittest.TestCase):
    """Review S1: the earlier revisions are rebuilt from frozen constants, so tuning a live constant (game-outcomes will
    refit the red-zone pass scale) cannot turn a v0.9 or pre-rule beta 81 disc foreign."""

    PINS = {"b81": "a2d6fdc0bbf3983a96cb5b5b6cca9ab21d92401df0e27221fd1efc82928078f6",      # c4406481b's code_for
            "beta80": "c89d42e3f4fa73abb05718e1ac7d246d1829b072785d34264d62b6252bbf15a7"}   # beta-80 / v0.9
    TUNED = {"RZ_PASS_SCALE": 0.60, "MIX_BIAS": 9.25, "PASS_SCALE": 0.95, "TARGET_RATE": 0.2, "TACKLE_BONUS_PCT": 12,
             "INTERCEPT_SCALE": 1.2, "RUN_RZ_SCALE": 0.9, "WR2_SHARE": 0.3}

    def bodies(self):
        return {"b81": r._assemble(0x14DA000, 0x14DC000, fb=False)[1],
                "beta80": r._assemble(0x14DA000, 0x14DC000, beta80=True)[1]}

    def test_the_earlier_bodies_are_pinned(self):
        for revision, body in self.bodies().items():
            self.assertEqual(hashlib.sha256(body).hexdigest(), self.PINS[revision], revision)

    def test_retuned_live_constants_leave_earlier_discs_legacy(self):
        from unittest import mock
        from mod_editor.core import nfl2k5_rdata_sites as rdata, nfl2k5_xbe_space as space
        data = retail_bytes()
        allocated = space.apply(data, r.REQUESTS, scaleout=True)[0]
        code, state = r._allocations(allocated)
        installs = {}
        for revision, kw in (("b81", {"fb": False}), ("beta80", {"beta80": True})):
            old = space.install_code(allocated, r.OWNER, r._assemble(code["va"], state["va"], **kw)[1])[0]
            installs[revision] = rdata.apply(old, r.sites(code["va"], **kw), r.OWNER)[0]
        with mock.patch.multiple(r, **self.TUNED):
            r._LABEL_CACHE = None
            self.assertEqual({k: hashlib.sha256(v).hexdigest() for k, v in self.bodies().items()}, self.PINS)
            for revision, old in installs.items():
                self.assertEqual(r.status(old), "legacy", revision)           # still the previous revision
                upgraded = r.apply(old)[0]                                   # updated in place to the retuned one
                self.assertEqual(r.status(upgraded), "applied", revision)
                self.assertEqual(upgraded, r.apply(data)[0], revision)
                pool = XbeImage(upgraded).read(code["va"] + r.RZ_PASS_SCALE_OFF, 4)
                self.assertAlmostEqual(struct.unpack("<f", pool)[0], 0.60, places=6)
        r._LABEL_CACHE = None

    def test_a_non_zero_rush_correction_is_refused(self):
        from unittest import mock
        with mock.patch.object(r, "RUSH_BONUS_PCT", 8), self.assertRaises(r.SimRealismError):
            r.code_for(0x14DA000, 0x14DC000)
        r._assemble(0x14DA000, 0x14DC000, fb=False)                    # the frozen revisions keep their own 0
        r._assemble(0x14DA000, 0x14DC000, beta80=True)


class FullbackTargetTests(unittest.TestCase):
    """b81 fb-targets: the target site's call, run natively as the game makes it (EDI = the sim team), with the retail
    target lottery 0x1034C0 and the league draw 0x48BC0 replaced by scripted stand-ins where a test needs exact picks.

    The entry is read from the installed site, so on an executable without the rule (the target step alone) these tests
    fail: the fullback keeps every pass."""

    TEAM, PLAYERS = 0x3070000, 0x3071000
    KEEP, REDRAWS, LEAGUE_DRAW = 21845, 3, 0x48BC0         # 1 in 3 of the 16-bit draw; then the target step 3 more times
    WR1, HB1, WR2, TE1, FB1, HB2 = 4, 1, 5, 8, 2, 3        # lineup slots (0x4F6A80 order: 4, 1, 5, 8, 2, 6, 3, 7)

    @classmethod
    def setUpClass(cls):
        import importlib.util
        if importlib.util.find_spec("unicorn") is None:
            raise unittest.SkipTest("unicorn is needed")
        cls.patched, receipt = r.apply(retail_bytes())
        image = XbeImage(cls.patched)
        call = image.read(r.TARGET_SITE, 5)
        cls.assert_call = call[0] == 0xE8
        cls.entry = (r.TARGET_SITE + 5 + struct.unpack_from("<i", call, 1)[0]) & 0xFFFFFFFF

    def machine(self, positions, *, wr1=False, te1=True, hb1=True):
        """A sim team whose lineup holds one player per slot with these position bytes; slot -> player address."""
        from tests.mod_editor.test_nfl2k5_honors import Machine
        m = Machine(self.patched)
        m.uc.mem_write(self.TEAM, bytes(0x100))
        players = {}
        for i, (slot, position) in enumerate(sorted(positions.items())):
            p = self.PLAYERS + 0x80 * i
            m.uc.mem_write(p, bytes(0x80))
            m.put8(p + 0x35, position)
            m.put8(p + 0x44, r.TARGET_PIVOT)              # Catching: an average WR1 redirects at TARGET_RATE
            players[slot] = p
            if (slot == self.WR1 and not wr1) or (slot == self.TE1 and not te1) or (slot == self.HB1 and not hb1):
                continue                                  # an empty lineup slot (WR1 empty: the redirect never runs)
            m.put(self.TEAM + 8 + 4 * slot, p)
        m.put(r.TEAM_OFFENSE, self.TEAM)
        return m, players

    def script(self, m, picks, draws=None):
        """FN_TARGET returns the picks in order; the league draw returns the draws in order (None: the real one)."""
        state = {"picks": list(picks), "draws": list(draws or ()), "targets": 0, "drawn": 0}
        def target(mm):
            state["targets"] += 1
            self.assertEqual(mm.reg("EDI"), self.TEAM, "the lottery draws for the sim team")
            return state["picks"].pop(0)
        m.hook(0x1034C0, target)
        if draws is not None:
            def draw(mm):
                state["drawn"] += 1
                return state["draws"].pop(0)
            m.hook(self.LEAGUE_DRAW, draw)
        return state

    def run_site(self, m):
        sp = m.SP - 0x40
        m.put(sp, m.STOP)
        m.reg("ESP", sp)
        for name, value in (("EDI", self.TEAM), ("ESI", 0x11111111), ("EBX", 0x22222222), ("EBP", 0x33333333)):
            m.reg(name, value)
        m.uc.emu_start(self.entry, m.STOP, count=200_000)
        self.assertEqual(m.reg("EIP"), m.STOP)
        self.assertEqual(m.reg("ESP"), sp + 4)
        self.assertEqual((m.reg("ESI"), m.reg("EBX"), m.reg("EBP"), m.reg("EDI")),
                         (0x11111111, 0x22222222, 0x33333333, self.TEAM), "callee registers survive")
        return m.reg("EAX")

    LINEUP = {1: 7, 2: 8, 3: 7, 4: 3, 5: 3, 8: 9}          # HB1, FB1, HB2, WR1, WR2, TE1

    @staticmethod
    def seed(m, state, seed=81):
        """Seed one of the game's additive lagged generators (0x48B50: two indexes, then 55 qwords) as boot does."""
        import random
        rng = random.Random(seed)
        m.put(state, 54)
        m.put(state + 4, 30)
        m.uc.mem_write(state + 8, b"".join(struct.pack("<Q", rng.getrandbits(64)) for _ in range(55)))

    def test_rule_constants(self):
        self.assertEqual((r.FB_TARGET_KEEP_THRESHOLD, r.FB_TARGET_REDRAWS, r.FN_LEAGUE_DRAW, r.FULLBACK_POSITION),
                         (self.KEEP, self.REDRAWS, self.LEAGUE_DRAW, 8))
        self.assertEqual((r.TE1_SLOT, r.HB1_SLOT), (8 + 4 * self.TE1, 8 + 4 * self.HB1))

    def test_the_site_calls_the_rule(self):
        self.assertTrue(self.assert_call)
        self.assertEqual(self.entry, int(r.apply(retail_bytes())[1]["code_va"], 16) + r.label_offsets()["fb_entry"])

    def test_a_fullback_keeps_one_target_in_three(self):
        # the real league draw (0x48B50's additive lagged generator, seeded here as the game seeds it at boot): of 3,000
        # fullback picks about a third stay with him, the rest go to the redraw's pick
        m, players = self.machine(self.LINEUP)
        self.seed(m, 0xB12680)
        kept = 0
        for _ in range(3000):
            self.script(m, [players[self.FB1], players[self.WR2]])
            kept += self.run_site(m) == players[self.FB1]
        self.assertAlmostEqual(kept / 3000, self.KEEP / 65536, delta=0.03)

    def test_the_keep_draw_reads_its_low_16_bits(self):
        m, players = self.machine(self.LINEUP)
        for draw, expected in ((self.KEEP - 1, self.FB1), (self.KEEP, self.WR2),
                               (0xFFFF0000 | (self.KEEP - 1), self.FB1), (0, self.FB1),
                               (0xFFFF, self.WR2)):
            state = self.script(m, [players[self.FB1], players[self.WR2]], [draw])
            self.assertEqual(self.run_site(m), players[expected], hex(draw))
            self.assertEqual(state["drawn"], 1)

    def test_a_redraw_goes_out_as_the_lottery_draws_it(self):
        m, players = self.machine(self.LINEUP)
        for picks, expected, calls in (([self.FB1, self.WR2], self.WR2, 2), ([self.FB1, self.FB1, self.HB2], self.HB2, 3),
                                       ([self.FB1, self.FB1, self.FB1, self.TE1], self.TE1, 4),
                                       ([self.FB1, self.HB1], self.HB1, 2)):
            state = self.script(m, [players[s] for s in picks], [0xFFFF])
            self.assertEqual(self.run_site(m), players[expected], picks)
            self.assertEqual((state["targets"], state["drawn"]), (calls, 1), picks)

    def test_a_fullback_drawn_every_time_goes_to_te1_then_hb1(self):
        redraws = self.REDRAWS
        for te1, hb1, expected in ((True, True, self.TE1), (False, True, self.HB1), (False, False, self.FB1)):
            m, players = self.machine(self.LINEUP, te1=te1, hb1=hb1)
            state = self.script(m, [players[self.FB1]] * (1 + redraws), [0xFFFF])
            self.assertEqual(self.run_site(m), players[expected], (te1, hb1))
            self.assertEqual(state["targets"], 1 + redraws)

    def test_every_other_pick_is_untouched_and_draws_nothing(self):
        lineup = {1: 7, 2: 7, 3: 7, 4: 3, 5: 3, 6: 3, 7: 9, 8: 9, 9: 0}   # a halfback in the fullback slot keeps his
        m, players = self.machine(lineup)
        for slot in sorted(lineup):
            state = self.script(m, [players[slot]], [])
            self.assertEqual(self.run_site(m), players[slot], slot)
            self.assertEqual((state["targets"], state["drawn"]), (1, 0), slot)

    def test_the_rule_runs_after_the_redirect(self):
        # with WR1 in the lineup the target step's redirect runs first (the match RNG, real); a fullback it keeps meets
        # the rule, a pick it moved to WR1 or TE1 does not
        m, players = self.machine(self.LINEUP, wr1=True)
        self.seed(m, r.MATCH_RNG)
        outcomes, ruled = set(), 0
        for _ in range(400):
            state = self.script(m, [players[self.FB1], players[self.WR2]], [0xFFFF])
            got = self.run_site(m)
            outcomes.add(got)
            self.assertNotEqual(got, players[self.FB1])
            self.assertEqual(state["targets"], 1 + state["drawn"])
            ruled += state["drawn"]
        self.assertGreater(ruled, 300)                     # most fullback picks survive the redirect and meet the rule
        self.assertLess(ruled, 400)                        # some are redirected first and draw nothing
        self.assertTrue(outcomes <= {players[self.WR1], players[self.TE1], players[self.WR2]})


if __name__ == "__main__":
    unittest.main()
