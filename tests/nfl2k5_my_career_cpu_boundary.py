"""Native off-field rule boundaries with explicit game/presentation inputs.

These fixtures do not replace rule, stat, lineup, clock or CPU-choice callees.
The halftime pool is a bounded backing allocation, not a loaded presentation.
"""
import struct

from tests.nfl2k5_my_career_cpu_fixture import Machine as ChoiceMachine


class Machine(ChoiceMachine):
    def f32(self, address, value=None):
        if value is None:
            return struct.unpack('<f', self.uc.mem_read(address, 4))[0]
        self.uc.mem_write(address, struct.pack('<f', value))

    def period_inputs(self, period):
        # A declared previous kickoff result, omitted by the direct scene
        # fixture: the current offense kicked first, toward positive Z.
        self.put(0xE602F0, self.offense)
        self.put(0xE602F4, 1)
        self.put(0xE602C4, period)
        self.f32(self.get(0xE6028C) + 16, .001)
        self.put(self.get(0xE602EC) + 4, 1)

    def halftime_pool(self):
        # Native F6070/12F030 obtain the 0x148000-byte halftime heap from
        # this valid free-list node; DA4D0/48640 construct it unchanged.
        self.uc.mem_map(0x2D00000, 0x200000)
        for va, value in (
                (0xB9E230, 0x2D00000), (0xB9E234, 1), (0xBB8360, 1),
                (0xBB8370, 1), (0xBB8374, 0x2E90000), (0xBB8378, 0x2E90000),
                (0x2E90004, 0xBB8370), (0x2E90008, 0xBB8370),
                (0x2E9077C, 0x2D00000)):
            self.put(va, value)

    def control_frame(self):
        self.call(0xAF2C0, args=(0x3C888889,))
        self.call(0x18C1F0, budget=2000000)
        self.call(0x89BA0, budget=2000000)
        self.call(0xE9210, args=(0x3C888889,), budget=2000000)

    def observe(self, addresses):
        calls = []
        for va in addresses:
            self.stubs.append(self.uc.hook_add(
                self.u.UC_HOOK_CODE, lambda _uc, address, *_: calls.append(address),
                begin=va, end=va))
        return calls

    def next_choice(self):
        self.offense, self.defense = self.get(0xE60280), self.get(0xE60284)
        return self.cpu_choice()
