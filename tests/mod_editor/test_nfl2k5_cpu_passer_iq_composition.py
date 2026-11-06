"""CPU quarterbacks throw on time with every gameplay owner, one pair at a time, and on the released v0.8 executable.

The owner is the last late allocator owner: a build installs it after every other executable writer. Each pair starts
from a seed that reserves the composed owners (the CPU AI composition seed), installs the existing owner, the CPU QB
reads and defender ball-play owners with every option on, then this owner. Every owner must keep its status and replay
byte-exactly. The optional v0.8 check (NFL2K5_V08_XBE, NFL2K5_SLOW_TESTS=1) reads every owner of the released executable
with the Studio's own reader before and after. Bounded XBE bytes only; no disc build.
"""
from pathlib import Path
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from tests import nfl2k5_allocator_stack as stack
from mod_editor.core import nfl2k5_cpu_passer_iq as passer
from mod_editor.core import nfl2k5_cpu_qb_reads as reads, nfl2k5_db_ball_play as ball
from mod_editor.core import nfl2k5_xbe_space as space
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, prerequisites
from tests.mod_editor.test_nfl2k5_cpu_ai_composition import GAMEPLAY
from tests.mod_editor.test_nfl2k5_cpu_passer_iq import v08_xbe


def cpu_ai(payload):
    payload, _ = reads.apply(payload, zone_windows=True, recheck=True, tiers=True)
    payload, _ = ball.apply(payload)
    return passer.apply(payload)[0]


class GameplayPairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        requests = sum((o.module.REQUESTS for _n, o in GAMEPLAY), stack.deep_zone.REQUESTS)
        cls.seed, _ = space.apply(prerequisites(retail_xbe()), requests, scaleout=True)

    def check(self, owner):
        result, _ = owner.apply(self.seed)
        before = owner.status(result)
        final = cpu_ai(result)
        self.assertEqual(before, "applied")
        self.assertEqual(owner.status(final), "applied", owner.OWNER)
        self.assertEqual(passer.status(final), "applied")
        self.assertEqual(reads.read_settings(final), {"status": "applied", "zone_windows": True, "recheck": True, "tiers": True})
        self.assertEqual(ball.status(final), "applied")
        self.assertEqual(passer.apply(final)[0], final)
        if owner.OWNER != stack.money_downs.OWNER:     # Modern 2's own native repair may append its late companion
            self.assertEqual(owner.apply(final)[0], final, owner.OWNER)
        self.assertEqual(space.status(final), "applied")


def pair_test(owner):
    def test(self):
        self.check(owner)
    return test


for _name, _owner in GAMEPLAY:
    setattr(GameplayPairTests, f"test_{_name}", pair_test(_owner))


class ReleaseReadBackTests(unittest.TestCase):
    def test_every_owner_of_the_release_executable_reads_the_same(self):
        v08 = v08_xbe()
        if not os.environ.get("NFL2K5_SLOW_TESTS"):
            raise unittest.SkipTest("set NFL2K5_SLOW_TESTS=1 for the two complete read-backs (several minutes)")
        with tempfile.TemporaryDirectory() as directory:
            before_path, after_path = Path(directory) / "before.xbe", Path(directory) / "after.xbe"
            before_path.write_bytes(v08)
            after_path.write_bytes(passer.apply(v08)[0])
            from mod_editor.core import mod_build
            before, after = mod_build.inspect(before_path), mod_build.inspect(after_path)
        skip = {"path", "xbe_sha256", "source", "source_sha256"}
        changed = {k for k in set(before) | set(after) if k not in skip and before.get(k) != after.get(k)}
        self.assertEqual((before.get("cpu_passer_iq"), after.get("cpu_passer_iq")), ("retail", "applied"))
        self.assertEqual(changed, {"cpu_passer_iq"}, sorted(changed))


if __name__ == "__main__":
    unittest.main()
