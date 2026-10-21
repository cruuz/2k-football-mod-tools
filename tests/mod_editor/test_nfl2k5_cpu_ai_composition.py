"""The b776 CPU AI owners with every existing gameplay owner, one pair at a time, plus the b775 executable.

Both CPU AI owners are late allocator owners: a build installs them after every other executable writer, in the
order cpu_qb_reads then db_ball_play. Each pair therefore starts from the complete gate union (the same seed as the
pairwise matrix), installs the existing owner, then both CPU AI owners with every option on. Every existing owner
must keep its status and replay byte-exactly, and so must the CPU AI owners. The throw-tuning tables (throw ceiling,
realistic flight, arc by distance) and the catch slider are written by the throw-tuning writer on retail bytes
before any allocation, so they are composed the same way, in build order. Bounded XBE bytes only.
"""
from pathlib import Path
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from tests import nfl2k5_allocator_stack as stack
from mod_editor.core import nfl2k5_cpu_qb_reads as reads, nfl2k5_db_ball_play as ball
from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_catch_slider as catch
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, prerequisites
from tests.mod_editor.test_nfl2k5_cpu_qb_reads import b775_xbe


class _Owner:
    def __init__(self, module, **options):
        self.OWNER, self.module, self.options = module.OWNER, module, options

    def apply(self, payload):
        return self.module.apply(payload, **self.options)

    def status(self, payload):
        return self.module.status(payload)


GAMEPLAY = (
    ("coverage_slider", _Owner(stack.coverage)),
    ("coverage_trail", _Owner(stack.coverage_trail)),
    ("zone_drop_cap", _Owner(stack.zone_drop)),
    ("qb_spy", _Owner(stack.qb_spy)),
    ("screen_hooks", _Owner(stack.screen_hooks)),
    ("cpu_scrambles", _Owner(stack.cpu_scrambles)),
    ("cpu_money_downs", _Owner(stack.money_downs, level="modern2")),
    ("scramble_tuning", _Owner(stack.scramble)),
    ("momentum", _Owner(stack.momentum, momentum=100, momentum_contact=True, momentum_collisions=True,
                        momentum_collision_level=100)),
)


def cpu_ai(payload):
    payload, _ = reads.apply(payload, zone_windows=True, recheck=True)
    payload, _ = ball.apply(payload)
    return payload


class GameplayPairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The complete gate union (stack.REQUESTS) already holds the allocator's 95-request ceiling, so it cannot
        # take a late owner (see the report). The seed reserves the union of the owners composed here instead.
        requests = sum((o.module.REQUESTS for _n, o in GAMEPLAY), stack.deep_zone.REQUESTS)
        cls.seed, _ = space.apply(prerequisites(retail_xbe()), requests, scaleout=True)

    def check(self, owner, before=()):
        result = self.seed
        for prior in before:
            result, _ = prior.apply(result)
        result, _ = owner.apply(result)
        status = {o.OWNER: o.status(result) for o in (*before, owner)}
        final = cpu_ai(result)
        self.assertEqual({o.OWNER: o.status(final) for o in (*before, owner)}, status)
        self.assertTrue(all(value == "applied" for value in status.values()), status)
        self.assertEqual(reads.read_settings(final), {"status": "applied", "zone_windows": True, "recheck": True})
        self.assertEqual(ball.status(final), "applied")
        for o in (*before, owner):
            self.assertEqual(o.apply(final)[0], final, o.OWNER)
        self.assertEqual(cpu_ai(final), final)
        self.assertEqual(space.status(final), "applied")

    def test_deep_zone_facing_and_bail(self):
        # deep zone composes over its native partners, as in its own suite
        partners = (_Owner(stack.zone_drop), _Owner(stack.coverage_trail), _Owner(stack.qb_spy))
        self.check(_Owner(stack.deep_zone, facing=True, bail=True), before=partners)


def pair_test(owner):
    def test(self):
        self.check(owner)
    return test


for _name, _owner in GAMEPLAY:
    setattr(GameplayPairTests, f"test_{_name}", pair_test(_owner))


class CeilingTests(unittest.TestCase):
    def test_complete_gate_union_is_at_the_request_ceiling(self):
        seed, _ = space.apply(prerequisites(retail_xbe()), stack.REQUESTS, scaleout=True)
        with self.assertRaisesRegex(ValueError, "request count"):
            reads.apply(seed, recheck=True)
        # the data-only option needs no allocation, so it still installs on the complete union
        self.assertEqual(reads.read_settings(reads.apply(seed, zone_windows=True)[0])["zone_windows"], True)


class ThrowTuningTests(unittest.TestCase):
    """Throw ceiling 80 yd, realistic flight, arc by distance and the catch slider (throw-tuning writer)."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()

    def check(self, settings, *, arc_table):
        wanted = tt.curves_for(settings)
        tuned, _ = tt._apply_all(self.retail, wanted, catch_slider=True, arc_table=arc_table)
        curves, arc, catch_state = tt.read_curves(tuned), tt.arc_table_status(tuned), catch.status(tuned)
        final = cpu_ai(tuned)
        self.assertEqual((tt.read_curves(final), tt.arc_table_status(final), catch.status(final)),
                         (curves, arc, catch_state))
        self.assertEqual(catch_state, "applied")
        self.assertEqual((reads.status(final), ball.status(final)), ("applied", "applied"))

    def test_max_deep_yards_and_realistic_flight(self):
        self.check(tt.TuningSettings(max_deep_yards=80.0, realistic_flight=True), arc_table=False)

    def test_arc_by_distance(self):
        self.check(tt.TuningSettings(max_deep_yards=80.0, arc_by_distance=True), arc_table=True)


class B775StudioReadTests(unittest.TestCase):
    """Every status the Studio reads (throw-tuning read_xbe) is the same after both CPU AI owners on b775."""

    def test_every_installed_owner_reads_the_same(self):
        b775 = b775_xbe()
        if not os.environ.get("NFL2K5_SLOW_TESTS"):
            raise unittest.SkipTest("set NFL2K5_SLOW_TESTS=1 for the two complete read-backs (about four minutes)")
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            before_path, after_path = Path(directory) / "before.xbe", Path(directory) / "after.xbe"
            before_path.write_bytes(b775)
            after_path.write_bytes(cpu_ai(b775))
            before, after = tt.read_xbe(before_path), tt.read_xbe(after_path)
        skip = {"path", "xbe_sha256"}
        self.assertEqual({k: v for k, v in before.items() if k not in skip},
                         {k: v for k, v in after.items() if k not in skip})


if __name__ == "__main__":
    unittest.main()
