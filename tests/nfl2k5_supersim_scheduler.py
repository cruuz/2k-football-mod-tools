"""Installed scheduler decisions with declared boundary inputs.

Native roster deserialization, binder, manager dispatch, input/RNG, readiness
and snap event queue execute. The outer football update is a counted ABI
boundary here; uninterrupted scene execution is a separate series fixture.
"""
from collections import Counter

from tests.nfl2k5_my_career_mode_fixture import Machine as CareerMachine
from tests.mod_editor.test_nfl2k5_my_career_control import ControlTests


class Machine(CareerMachine):
    def setup(self, position=0, away=False):
        self.body, self.side = ControlTests().load(self, position, away)
        self.manager = self.OUT + 0x90000
        self.put(self.manager, 0x4E7EC0)
        self.put(self.manager + 0x100, 0)
        self.put(0xA83A18, 3)
        self.put(0xB616C0, 11)
        self.put(0xB37A70, 1)
        self.put(self.state + 2696, 2)
        self.put(0xE602B8, 13)
        self.put(0xE60294, self.ARENA + 0x91000)
        self.put(0xE602AC, 0x42200000)  # native initial play clock: 40 seconds
        self.put(self.get(0xE60294) + 0x18, 1)
        self.actors = [self.body + 0x100*i for i in range(22)]
        for i, actor in enumerate(self.actors):
            task, phase = self.ARENA + 0xA0000 + i*0x1000, self.ARENA + 0xA0800 + i*0x1000
            self.put(actor + 0x20, task)
            self.put(actor + 0x10, phase)
            self.put(actor + 0x1C, 1)
            self.put(task + 0x3E4, 13)
            self.put(phase + 4, 0x50F1E4)
            self.put(phase + 0xD4, phase + 0x180)
        self.counts = Counter()
        self.on_update = lambda: None
        def update():
            self.counts['updates'] += 1
            self.on_update()
            self.ret()
        self.replace_stub(0x64CD0, update)
        self.replace_stub(0xF3E90, lambda: self.ret())  # native menu/input callback ABI
        self.replace_stub(0xF3970, lambda: self.ret())  # menu animation/input completion
        self.replace_stub(0x710E0, lambda: (self.counts.update(['polls']), self.ret()))
        self.replace_stub(0x70FC0, lambda: self.ret(1))
        self.replace_stub(0x12DDC0, lambda: self.ret(pop=4))
        self.replace_stub(0x71240, lambda: self.ret(pop=4))
        # The decoded input bank itself remains native. Only the device poll,
        # completion fence and network input packet service are substituted.
        self.call(0x48BE0, ecx=0xE5FCA0, edx=12345)

    def presented_frame(self):
        self.call(0x74730, args=(0x3C888889,))
        hook = self.uc.hook_add(self.u.UC_HOOK_CODE,
            lambda *_: self.put(self.STACK, 0x3C888889), begin=0x747CC, end=0x747CC)
        try:
            self.call(0x747CC, ecx=self.manager, stop=0x747D1, budget=3000000)
        finally:
            self.uc.hook_del(hook)
        if self.reg('ESP') != self.STACK + 4:
            raise AssertionError('installed frame CALL stack differs')
        # Count the real present CALL site, without opening a renderer.
        self.replace_stub(0x27CA0, lambda: (self.counts.update(['presents']), self.ret()))
        self.call(0x7488D, stop=0x74892)

    def absent(self):
        self.put(self.body + 0x48, 1)

    def present(self):
        self.put(self.body + 0x48, 0)
