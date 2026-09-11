"""Native 64-voice allocator/retirement with a counted DirectSound device.

The source, voice allocator and audio worker execute retail instructions.
Only device methods are replaced: no sound device is opened. Buffer cursors
are supplied by the fake device, independently of gain and simulation speed.
This proves this voice pool, not every upstream commentary/stream queue.
"""
from collections import Counter

from tests.nfl2k5_supersim_draft_fixture import Machine as NativeMachine


class Machine(NativeMachine):
    VOICES, COUNT, STRIDE = 0xA6D830, 64, 0xC0
    DEVICE_POPS = {
        0x445BC3: 12, 0x4482C1: 8, 0x4478C5: 8, 0x4459FF: 8,
        0x4478FD: 8, 0x445A6F: 8, 0x445BA7: 8, 0x445B0B: 4,
        0x4482DD: 12, 0x445B87: 12, 0x445BE3: 8, 0x445AC3: 16,
        0x445B47: 8,
    }

    def __init__(self, payload):
        super().__init__(payload, trace_writes=False)
        self.device_calls, self.volumes, self.mixbins = Counter(), [], []
        self.cursor = 0
        for va, pop in self.DEVICE_POPS.items():
            self.leaf(va, lambda va=va, pop=pop: self.device(va, pop),
                      reason="DirectSound device ABI; count without audio")
        self.call(0x3D810)  # complete retail voice-state constructor
        for i in range(self.COUNT):
            # The loader provides two device buffers and their cache storage
            # per voice. These are device-side objects, not football actors.
            for base in (0xA70A80, 0xA72480):
                cache = base + i * 0x68
                self.put(cache + 0x24, cache + 0x28)
            self.put(0xA70880 + 4*i, 0x70000000 + i)
            self.put(0xA70980 + 4*i, 0x70000100 + i)

    def device(self, va, pop):
        self.device_calls[va] += 1
        sp = self.reg('ESP')
        if va == 0x4459FF:
            self.volumes.append(self.get(sp + 8))
        elif va == 0x4478FD:
            bins = self.get(sp + 8)
            count, rows = self.get(bins), self.get(bins + 4)
            if count > 8:
                raise AssertionError("native mix-bin count exceeds its array")
            self.mixbins.append(tuple(self.get(rows + 8*i + 4) for i in range(count)))
        elif va == 0x445BC3:
            self.put(self.get(sp + 8), self.cursor)
        elif va == 0x445BA7:
            self.put(self.get(sp + 8), 0)
        self.ret(pop=pop)

    def allocate(self):
        return self.call(0x3DA90, args=(1, 0))

    def source(self):
        """Native source admission, including its full-pool failure return."""
        source, channel = self.ARENA + 0x2000, self.ARENA + 0x2100
        self.put(source + 4, 1)
        self.put(source + 8, channel)
        self.put(channel, 0x400)
        self.put(channel + 0x1C, self.ARENA)
        return self.call(0x3E7C0, ecx=source, edx=0,
                         args=(0xFFFFFFFF, 0))  # no mix group; finite source

    def worker(self):
        """Entire native worker, with a supplied hardware counter tick."""
        if not hasattr(self, 'worker_ticks'):
            self.worker_ticks = 0
            def counter():
                self.worker_ticks += 0xA00000
                self.reg('EDX', self.worker_ticks >> 32)
                self.ret(self.worker_ticks & 0xFFFFFFFF)
            self.leaf(0x3C5F0, counter, reason='hardware timestamp counter ABI')
        self.call(0x3E910, budget=3000000)

    def fill(self):
        for i in range(self.COUNT):
            voice = self.allocate()
            if voice != self.VOICES + i*self.STRIDE:
                raise AssertionError("native allocation left the voice pool")
            self.put(voice + 0x10, 1)  # locked, cannot evict to satisfy demand
            self.put(voice + 0x14, 1)  # live source
            self.put(voice + 0x64, self.ARENA)
            self.put(voice + 0x6C, self.ARENA + 0x400)
            self.f32(voice + 0x50, 1)
            self.f32(voice + 0x5C, 0)

    def used(self):
        return sum(self.get(self.VOICES + i*self.STRIDE + 12) != 0
                   for i in range(self.COUNT))

    def submit(self, *, mute):
        # Model the candidate's scoped master gain and cache invalidation.
        # Without invalidation, SetVolume's native cache skips unchanged voices.
        gain = self.get(0xA70830)
        for base in (0xA70A80, 0xA72480):
            for i in range(self.COUNT):
                self.put(base + i*0x68 + 0x10, 0xBF800000)
        if mute:
            self.f32(0xA70830, 0)
        self.call(0x3DBC0, budget=3000000)
        self.put(0xA70830, gain)
