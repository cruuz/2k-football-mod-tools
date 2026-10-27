"""b778 ai6: the late-game fourth-down rule for a CPU team trailing in the last two minutes.

Bounded Unicorn replay of the installed Modern 2 pair plus the real native second-half scoring reader 0x250DD0.
The defense-strength branch is exercised both with the real reader entry (call arguments recorded) and with a
value stub on that one retail address; the RNG is the game's own match PRNG (0x48B90, state 0xE5FCA0).
"""
from __future__ import annotations

import struct
import unittest

from mod_editor.core import nfl2k5_cpu_money_downs as patch
from mod_editor.core import nfl2k5_xbe_space as space
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe

try:
    from tests.nfl2k5_cpu_money_downs_native import Machine, uc, x86
except ImportError:      # pragma: no cover
    uc = None


def _points_stub(machine, points):
    machine.uc.mem_write(0x250DD0, b"\xb8" + struct.pack("<I", points) + b"\xc3")
    machine.uc.ctl_flush_tb()


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class LateFourthNativeTests(unittest.TestCase):
    RANGE = 38

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.payload = patch.apply(cls.retail, level="modern2")[0]
        cls.state_va = next(a["va"] for a in space.layout(cls.payload)["allocations"]
                            if a["owner"] == patch.LATE_STATE_OWNER)
        cls.m = Machine(cls.payload)
        cls.m.supply_fg_range(cls.RANGE)
        # The ai4 template, installed in the same allocation without the companion: the before case.
        allocated, _ = space.apply(cls.retail, patch.REQUESTS, scaleout=True)
        cls.before = patch._install_modern2(allocated, allow_no_late=True)[0]
        cls.base = Machine(cls.before)
        cls.base.supply_fg_range(cls.RANGE)

    def state(self, **changes):
        state = dict(quarter=4, seconds=100, score_margin=-7, own_yard=65, distance=27,
                     quarter_seconds=300, timeouts=3)
        state.update(changes)
        return state

    def decide(self, *, counter=1, points=0, machine=None, **changes):
        machine = machine or self.m
        machine.configure(**self.state(**changes))
        if points is not None:
            _points_stub(machine, points)
        if machine is self.m:
            machine.u32(self.state_va, counter - 1)
            machine.u32(self.state_va + 4, 0xFFFFFFFF)
        return machine.run_policy()

    def test_companion_is_a_late_owner_and_modern2_fits_2048(self):
        self.assertEqual(patch.CODE_SIZE, 2048)
        self.assertEqual(patch.LATE_CODE_SIZE, 400)
        self.assertEqual(len(patch.assembly.CODE2_LATE), 2044)
        self.assertLessEqual(len(patch.assembly.CODE2_LATE), patch.CODE_SIZE)
        self.assertGreater(len(patch.assembly.CODE_LATE), 0)
        self.assertIn(patch.LATE_OWNER, space.LATE_OWNERS)
        self.assertGreater(space.LATE_OWNERS.index(patch.LATE_OWNER),
                           space.LATE_OWNERS.index("nfl2k5_force_out"))
        self.assertNotIn(patch.LATE_OWNER, {owner for owner, _kind, _size, _align in patch.REQUESTS})
        rows = [a for a in space.layout(self.payload)["allocations"] if a["owner"].startswith(patch.OWNER)]
        self.assertEqual([(a["owner"], a["size"]) for a in rows],
                         [(patch.OWNER, 2048), (patch.LATE_OWNER, patch.LATE_CODE_SIZE),
                          (patch.LATE_STATE_OWNER, patch.LATE_STATE_SIZE)])
        self.assertEqual(patch.read_settings(self.payload)["late_policy"], True)
        self.assertEqual(patch.status(self.payload), "applied")

    def test_trailing_go_at_any_distance_and_rare_punt(self):
        # Down 7, 4th and 27, 1:40, three timeouts, strong defense: the 4-byte counter cycles 1,2 go / 3 punt.
        self.assertEqual(self.decide(counter=3, points=0), 0)    # retail punts at 4th and 27
        self.assertEqual(self.decide(counter=1, points=0), 1)
        self.assertEqual(self.decide(counter=2, points=0), 1)
        # Weak defense (8+ second-half points) never punts even on the punt counter.
        self.assertEqual(self.decide(counter=3, points=8), 1)
        self.assertEqual(self.decide(counter=3, points=12), 1)
        # Down 10 at any distance goes.
        self.assertEqual(self.decide(counter=1, points=0, score_margin=-10, distance=27), 1)
        # 0:50 with three timeouts is outside the punt window.
        self.assertEqual(self.decide(counter=3, points=0, seconds=50), 1)
        self.assertEqual(self.decide(counter=3, points=0, seconds=90), 1)
        # Three timeouts are required.
        self.assertEqual(self.decide(counter=3, points=0, timeouts=2), 1)
        # Past the two-minute window the table decides: this is the retail punt at 4th and 27.
        self.assertEqual(self.decide(counter=3, points=0, seconds=121), 0)

    def test_field_goal_only_ties_or_takes_the_lead_in_range(self):
        # Down 3 at the opponent 20: the kick ties; no rare punt once the kick is chosen.
        self.assertEqual(self.decide(counter=1, points=0, score_margin=-3, own_yard=80, distance=2), 2)
        self.assertEqual(self.decide(counter=1, points=0, score_margin=-1, own_yard=80, distance=1), 2)
        # Down 4 in the same spot: go (no kick; timeouts 0 isolates the rule from the rare punt).
        self.assertEqual(self.decide(counter=1, points=0, score_margin=-4, own_yard=80, distance=2, timeouts=0), 1)
        # Down 4 in range on the punt counter: retail, because the 2,048-byte main template cannot carry the
        # extra category path; the native chart punts at long yardage and this case is outside the kick rule.
        self.assertEqual(self.decide(counter=3, points=0, score_margin=-4, own_yard=80, distance=2), 0)
        # Down 3 out of range: go.
        self.assertEqual(self.decide(counter=1, points=0, score_margin=-3, own_yard=40, distance=2, timeouts=0), 1)

    def test_real_second_half_reader_is_called_with_the_defense_side(self):
        seen = []
        hook = self.m.uc.hook_add(uc.UC_HOOK_CODE,
                                  lambda _uc, address, _size, _data: seen.append(
                                      (self.m.uc.reg_read(x86.UC_X86_REG_ECX),
                                       self.m.uc.reg_read(x86.UC_X86_REG_EDX))),
                                  begin=0x250DD0, end=0x250DD0)
        try:
            self.m.configure(**self.state(score_margin=-7))
            self.m.seed(1)                      # high roll: the reader runs before the RNG
            self.m.run_policy()
        finally:
            self.m.uc.hook_del(hook)
        self.assertEqual(seen, [(0, 7)])        # away offense -> home defense: drive-ring side 0

    def test_before_template_has_no_late_rule(self):
        # The ai4 bytes (no companion) punt and delegate: 4th and 27 late returns retail, not go.
        self.assertEqual(self.decide(machine=self.base, counter=1, points=None), 0)
        self.assertEqual(self.decide(machine=self.base, counter=1, points=None, score_margin=-3, own_yard=80,
                                     distance=2), 0)
        self.assertEqual(patch.read_settings(self.before)["late_policy"], False)


class CompanionComposition(unittest.TestCase):
    """The companion is a late owner after nfl2k5_coach_ai (LATE_OWNERS order): a build must reserve both in one
    request set. A sealed image that already carries the companion cannot accept a coach_ai append, because that
    would move the companion; the allocator refuses and leaves the image untouched (its never-move guarantee)."""

    def test_a_build_that_reserves_the_union_installs_both_owners(self):
        from mod_editor.core import nfl2k5_coach_ai as ai
        allocated, _ = space.apply(retail_xbe(), patch.REQUESTS + patch.LATE_REQUESTS + ai.REQUESTS, scaleout=True)
        payload, _ = patch.apply(allocated, level="modern2")
        payload, _ = ai.apply(payload)
        self.assertEqual((patch.status(payload), ai.status(payload)), ("applied", "applied"))
        self.assertEqual(patch.read_settings(payload)["late_policy"], True)

    def test_appending_coach_ai_after_the_companion_is_refused_and_moves_nothing(self):
        from mod_editor.core import nfl2k5_coach_ai as ai
        standalone, _ = patch.apply(retail_xbe(), level="modern2")
        before = space.layout(standalone)["allocations"]
        with self.assertRaisesRegex(ValueError, "would move an existing allocation"):
            ai.apply(standalone)
        self.assertEqual(space.layout(standalone)["allocations"], before)


if __name__ == "__main__":
    unittest.main()
