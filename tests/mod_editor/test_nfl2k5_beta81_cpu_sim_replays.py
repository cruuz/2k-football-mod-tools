"""Native regression replay of simulated receiver selection."""
import struct
import unittest

from mod_editor.core import nfl2k5_sim_realism as realism
from tests.mod_editor.test_nfl2k5_cave_oracle import synthetic
from tests.nfl2k5_supersim_draft_fixture import Machine, retail_bytes

try:
    import unicorn
except ImportError:
    unicorn = None


class ReceiverReplay:
    def __init__(self, machine, code_va):
        self.machine = m = machine
        self.team, self.wr1, self.wr2, self.te, self.other = (m.ARENA + i * 0x100 for i in range(1, 6))
        self.rng_pointer, self.draws = m.ARENA + 0x600, m.ARENA + 0x700
        m.put(realism.TEAM_OFFENSE, self.team)
        for slot, player in ((0x18, self.wr1), (0x1c, self.wr2), (0x28, self.te)):
            m.put(self.team + slot, player)
        self.entry = code_va + realism.label_offsets()["target"]
        # Supply only the retail target and random draws. The whole owner entry runs.
        m.leaf(realism.FN_TARGET, lambda: m.ret(self.native_target), reason="input selected by the unmodified game")
        pointer = struct.pack("<I", self.rng_pointer)
        m.uc.mem_write(realism.FN_RAND, b"\xa1" + pointer + b"\xd9\x00\x83\xc0\x04\xa3" + pointer + b"\xc3")

    def target(self, chosen, *, catching=93, position=3, draws=(0.0, 0.0, 0.0)):
        m = self.machine
        self.native_target = chosen
        m.uc.mem_write(self.wr1 + 0x44, bytes((96,)))
        m.uc.mem_write(self.wr2 + 0x44, bytes((catching,)))
        m.uc.mem_write(self.wr2 + 0x35, bytes((position,)))
        m.put(self.rng_pointer, self.draws)
        m.uc.mem_write(self.draws, struct.pack("<3f", *draws))
        return m.call(self.entry, edi=self.team)


class ReceiverChoices:
    def test_second_receiver_keeps_native_targets_and_shares_eligible_redirects(self):
        r = self.replay()
        for starter in (r.wr1, r.wr2, r.te):
            self.assertEqual(r.target(starter), starter)
        self.assertEqual(r.target(r.other), r.wr2)
        self.assertEqual(r.target(r.other, draws=(0.0, 0.0, 0.75)), r.wr1)
        self.assertEqual(r.target(r.other, draws=(0.0, 0.8, 0.0)), r.te)
        self.assertEqual(r.target(r.other, draws=(0.9, 0.0, 0.0)), r.other)
        self.assertEqual(r.target(r.other, catching=87), r.wr1)
        self.assertEqual(r.target(r.other, position=7), r.wr1)
        self.assertEqual(r.target(r.wr2, catching=70), r.wr2)


@unittest.skipUnless(unicorn is not None, "Unicorn is required for native CPU decision replays")
class GeneratedReceiverTests(ReceiverChoices, unittest.TestCase):
    def replay(self):
        # Execute the emitted production handler, including its rating and RNG branches.
        code_va, data_va = 0x14DA000, 0x14DC000
        m = Machine(synthetic(), trace_writes=False)
        m.uc.mem_write(code_va, realism.code_for(code_va, data_va))
        return ReceiverReplay(m, code_va)


@unittest.skipUnless(unicorn is not None, "Unicorn is required for native CPU decision replays")
class NativeReplays(ReceiverChoices, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = realism.apply(retail_bytes())[0]

    def replay(self):
        return ReceiverReplay(Machine(self.image, trace_writes=False), realism._allocations(self.image)[0]["va"])


if __name__ == "__main__":
    unittest.main()
