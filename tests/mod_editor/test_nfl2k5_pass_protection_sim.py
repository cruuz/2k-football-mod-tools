"""Simulated pass rush (b779-pr1): the nine in-place edits of nfl2k5_pass_protection, byte tests and real native games.

The pinned USA retail default.xbe and the signed f0 franchise are read from the private fixtures; the native
tests skip when they are absent.  The native tests run whole simulated games (retail simulator, real step
callbacks, Unicorn) with the retail and the patched executable and watch three places:

* 0x108398 / 0x108473: the team line matchup x and the resulting sack-or-scramble chance of every dropback;
* 0x103837 / 0x103847: the defender picked by the sacker draw (a list slot);
* 0x1085db: the sack branch.

No game boot is claimed.
"""
import hashlib
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_pass_protection as pp
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None


def retail_bytes():
    from tests.nfl2k5_supersim_draft_fixture import retail_bytes as _retail_bytes
    return _retail_bytes()


FRONT = range(15, 23)       # list slots 15-18 defensive line, 19-22 linebackers
BACKS = range(23, 29)       # list slots 23-28 defensive backs


class BytesTests(unittest.TestCase):
    def test_edits_are_nine_in_place_sites_with_no_allocation(self):
        names = [name for name, *_ in pp.SIM_EDITS]
        self.assertEqual(names, ["sim_event_chance", "sim_event_centre", "sim_rusher_slots", "sim_rusher_leftover", "sim_rusher_list",
                                 "sim_rusher_speed", "sim_rusher_agility", "sim_rusher_strength",
                                 "sim_rusher_tackle"])
        for _name, _va, before, after in pp.SIM_EDITS:
            self.assertEqual(len(before), len(after))
        self.assertEqual(pp.REQUESTS, ((pp.OWNER, "code", pp.CODE_SIZE, 16),))   # the sim edits add no request

    def test_category_four_weights_still_sum_to_one(self):
        retail = sum(struct.unpack("<f", before)[0] for name, _va, before, _a in pp.SIM_EDITS if name.startswith("sim_rusher_") and len(before) == 4 and name in ("sim_rusher_speed", "sim_rusher_agility", "sim_rusher_strength", "sim_rusher_tackle"))
        new = sum(struct.unpack("<f", after)[0] for name, _va, _b, after in pp.SIM_EDITS if name in ("sim_rusher_speed", "sim_rusher_agility", "sim_rusher_strength", "sim_rusher_tackle"))
        self.assertAlmostEqual(retail, 0.6, places=5)         # 0.4 Pass Rush stays: 1.0 in all
        self.assertAlmostEqual(new, 0.6, places=5)

    def test_candidate_list_keeps_every_slot_and_puts_the_backs_last(self):
        self.assertEqual(sorted(pp.SIM_LIST_NEW[:-1]), sorted(pp.SIM_LIST_RETAIL[:-1]))
        self.assertEqual(pp.SIM_LIST_NEW[-1], -1)
        order = list(pp.SIM_LIST_NEW[:-1])
        self.assertEqual(order[:8], [15, 18, 19, 21, 17, 16, 20, 22])     # front seven-plus, same priority order
        self.assertTrue(all(slot in BACKS for slot in order[8:]))
        self.assertEqual(order[8], 27)                                    # the strong safety gets the leftover first

    def test_constants_land_on_existing_rdata_floats(self):
        retail = retail_bytes()
        image = XbeImage(retail)
        self.assertAlmostEqual(struct.unpack("<f", image.read(pp.SIM_GAIN_VA, 4))[0], 0.75, places=6)
        self.assertAlmostEqual(struct.unpack("<f", image.read(pp.SIM_CENTRE_VA, 4))[0], 0.866, places=4)
        self.assertAlmostEqual(struct.unpack("<f", image.read(pp.SIM_NORM_VA, 4))[0], 0.25, places=6)
        self.assertAlmostEqual(struct.unpack("<f", image.read(0x4F6BD4, 4))[0], 0.875, places=6)   # the shared one stays
        self.assertAlmostEqual(struct.unpack("<f", image.read(0x4E6D5C, 4))[0], 0.1, places=6)

    def test_retail_guards_match_and_sim_state(self):
        retail = retail_bytes()
        self.assertEqual(pp._sim_state(retail), "retail")
        image = XbeImage(retail)
        for va, size, digest in pp.SIM_GUARDS:
            self.assertEqual(hashlib.sha256(image.read(va, size)).hexdigest(), digest)

    def test_sim_edits_apply_replay_and_refuse_foreign_bytes(self):
        retail = retail_bytes()
        patched = pp._apply_sim(retail)
        self.assertEqual(pp._sim_state(patched), "applied")
        image = XbeImage(patched)
        for _name, va, _before, after in pp.SIM_EDITS:
            self.assertEqual(image.read(va, len(after)), after)
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import repin_edit
        for label, va, content in (("event block", 0x108400, b"\x90"), ("sacker draw", 0x103800, b"\x90"),
                                   ("normaliser", 0x104000, b"\x90"), ("site", 0x1083AF, b"\x75")):
            bad = repin_edit(patched, va, content)
            with self.assertRaises(pp.PassProtectionError, msg=label):
                pp._sim_state(bad)

    def test_apply_installs_both_halves_and_completes_a_partial_build(self):
        retail = retail_bytes()
        final, receipt = pp.apply(retail)
        self.assertEqual(pp.status(final), "applied")
        self.assertTrue(receipt["simulated_sacks"])
        labels = {e["label"] for e in receipt["edits"]}
        self.assertEqual(labels, {"pass_delay"} | {name for name, *_ in pp.SIM_EDITS})
        again, replay = pp.apply(final)
        self.assertEqual(again, final)
        self.assertEqual(replay["status"], "already_applied")
        # a build with only the played half installed is completed in place, never refused
        owner_only, _ = pp._apply_owner(retail)[0], None
        self.assertEqual(pp._recognize(owner_only), "partial")
        self.assertEqual(pp.status(owner_only), "partial")
        completed, receipt2 = pp.apply(owner_only)
        self.assertEqual(pp.status(completed), "applied")
        self.assertEqual({e["label"] for e in receipt2["edits"]}, {name for name, *_ in pp.SIM_EDITS})
        self.assertEqual(completed, final)


def _setup(payload, save, seed):
    from tests.nfl2k5_supersim_draft_fixture import Machine
    m = Machine(payload, trace_writes=False)
    m.load_franchise(save)
    m.seed(seed)
    for address, value in ((0xE5FF80, 4), (0xE576A4, 8), (0xE6000C, 5), (0xE60010, 5)):
        m.put(address, value)
    m.call(0x77AE0, ecx=m.team_base)
    m.call(0x77B20, ecx=m.team_base + 500)
    return m


@unittest.skipUnless(uc is not None, "unicorn is not installed")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.patched, _ = pp.apply(cls.retail)
        from tests.nfl2k5_supersim_draft_fixture import signed_save
        try:
            cls.save = signed_save()
        except unittest.SkipTest:
            raise unittest.SkipTest("private signed f0 franchise is absent")
        cls.logs = {}

    def watch(self, payload, seed):
        m = _setup(payload, self.save, seed)
        rows, picks, state = [], [], {}

        def f32(addr):
            return struct.unpack("<f", bytes(m.uc.mem_read(addr, 4)))[0]

        def at_x(u, _a, _s, _d):
            state["x"] = f32(u.reg_read(x86.UC_X86_REG_ESP) + 0x18)

        def at_threshold(u, _a, _s, _d):
            rows.append((state.get("x"), f32(u.reg_read(x86.UC_X86_REG_ESP) + 0x14)))

        def at_pick(u, address, _s, _d):
            if address == 0x103837:
                index = u.reg_read(x86.UC_X86_REG_ESI)
                picks.append(struct.unpack("<i", bytes(u.mem_read(0x4F6B08 + index * 4, 4)))[0])
            else:
                picks.append(-2)         # the default rusher

        m.uc.hook_add(uc.UC_HOOK_CODE, at_x, begin=0x108398, end=0x108398)
        m.uc.hook_add(uc.UC_HOOK_CODE, at_threshold, begin=0x108473, end=0x108473)
        m.uc.hook_add(uc.UC_HOOK_CODE, at_pick, begin=0x103837, end=0x103837)
        m.uc.hook_add(uc.UC_HOOK_CODE, at_pick, begin=0x103847, end=0x103847)
        m.uc.ctl_flush_tb()
        m.call(0x10B280, ecx=m.team_base, edx=m.team_base + 500, args=(0, 1, 0, 0, 0, 0), budget=3_000_000)
        m.call(0x10B250, budget=20_000_000)
        for steps in range(5000):
            if m.call(0x10B250, budget=20_000_000) in (5, -1):
                break
        else:
            self.fail("simulator did not finish")
        return rows, picks

    def collect(self, name, payload):
        if name not in self.logs:
            rows, picks = [], []
            for seed in (12345, 777, 4242):
                r, p = self.watch(payload, seed)
                rows += r
                picks += p
            self.logs[name] = (rows, picks)
        return self.logs[name]

    @staticmethod
    def correlation(pairs):
        xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sx = sum((a - mx) ** 2 for a in xs) ** 0.5
        sy = sum((b - my) ** 2 for b in ys) ** 0.5
        return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / (sx * sy)

    def test_sack_chance_follows_the_two_lines_only_after_the_patch(self):
        retail_rows, _ = self.collect("retail", self.retail)
        patched_rows, _ = self.collect("patched", self.patched)
        for rows in (retail_rows, patched_rows):
            self.assertGreater(len(rows), 150)
            self.assertTrue(all(x is not None for x, _ in rows))
        retail_corr = self.correlation(retail_rows)
        patched_corr = self.correlation(patched_rows)
        # retail: only |x| > 0.1 (about 3.5% of dropbacks) moves the chance; the rest is a uniform draw
        self.assertGreater(retail_corr, -0.45, retail_corr)
        # patched: the chance is 1 - clamp(0.866 + 0.75 * x) - 0.005 * QB term, so it falls as the blockers win
        self.assertLess(patched_corr, -0.6, patched_corr)
        thresholds = [t for _, t in patched_rows]
        self.assertLessEqual(max(thresholds), 0.175 + 1e-6)         # 1 - 0.825 with no QB term

    def test_defensive_backs_get_only_the_leftover_of_the_sacker_draw(self):
        _, retail_picks = self.collect("retail", self.retail)
        _, patched_picks = self.collect("patched", self.patched)
        for picks in (retail_picks, patched_picks):
            self.assertGreater(len(picks), 200)
        retail_backs = sum(1 for slot in retail_picks if slot in BACKS) / len(retail_picks)
        patched_backs = sum(1 for slot in patched_picks if slot in BACKS) / len(patched_picks)
        self.assertGreater(retail_backs, 0.15, retail_backs)             # NFL: 5.6% of sacks
        self.assertLess(patched_backs, 0.09, patched_backs)
        self.assertGreater(patched_backs, 0.015)                         # safeties still blitz now and then
        self.assertTrue(all(slot in FRONT for slot in patched_picks if slot not in BACKS and slot != -2))


if __name__ == "__main__":
    unittest.main()
