"""Native zone, steering, sampler and 27-phase dispatcher evidence fixture.

Synthetic 22-player objects, zone registrations and neutral 25-bone clips are
inputs. Real opcode decoders, task initialization, zone callbacks, steering
filter, directional row bank, rate/turn, sampler and transforms execute. Full
frames retain all 27 phases. Hardware/audio and roster-rating leaves from the
existing frame harness are substituted, and every reached such leaf is recorded.
Supplied object callbacks also include constant height and empty task handlers.
No Python moves the corner after initialization. This is UNWITNESSED gameplay.
"""
from __future__ import annotations

import gc
import math
import struct

from tests.nfl2k5_coverage_trail_frame import TrailFrame, DT, YARD, signed_angle
from tests.nfl2k5_kickoff_frame import PHASES
from tests.mod_editor.test_nfl2k5_dynamic_kickoff import uni, x86
from mod_editor.core import nfl2k5_deep_zone as patch, nfl2k5_play_codec as codec

NATIVE_SITES = (0x1A6220, 0x1A5790, 0x1A5090, 0x1A4170, 0x305870,
                0x2FC9F0, 0x217AE0, 0x2D6550, 0x2D5860, 0x2D5250,
                0x35AF40, 0x35AD60, 0xA0B90, 0xB7430, 0x1CB950,
                0x214820, 0x2149E0, 0x31BEB0)


class DeepFrame(TrailFrame):
    def __init__(self, payload, *, depth=6, direction=1, mode=9, deep_count=3,
                 heading=32768, full=False, presnap_node=None, audit_writes=False):
        gc.collect()  # Unicorn bound hooks form cycles; reclaim each old arena.
        super().__init__(payload, defender=(0, depth*YARD), heading=heading, direction=direction)
        self.gameplay = self.p+0x200
        self.qb = self.players[0]
        self.hits, self.owner_writes = [], []
        self.record = (patch.allocations(payload)["data"]["va"]
                       if patch.status(payload) == "applied" else None)
        for va in NATIVE_SITES:
            self.uc.hook_add(uni.UC_HOOK_CODE, self._native_hit, begin=va, end=va)
        if self.record is not None and audit_writes:
            code = patch.allocations(payload)["code"]
            self.code_range = range(code["va"], code["va"]+code["size"])
            self.uc.hook_add(uni.UC_HOOK_MEM_WRITE, self._owner_write)
        self.assets()
        self.put(0xBE4F8C, self.qb)
        self.put(self.BALL, self.qb)
        self.put(self.qb, self.BALL)
        self.uc.mem_write(self.qb+0x2C, b'\0')
        self.uc.mem_write(self.get(self.qb+0x3C)+0x35, b'\0')
        self.place(self.qb, 0, -5*YARD*direction)
        self.place(self.target, 5*YARD*direction, -YARD*direction)
        self.f32(self.GAME+0x10, 0)
        self.f32(self.GAME+0x18, 0)
        self.f32(self.GAME+0x1C, 1)
        self.put(0xE5FF80, 3)  # offline practice-like mode, no network diagnostics
        self.put(self.NODE, 1)
        self.put(self.gameplay+0x41C, self.NODE)
        self.put(self.gameplay+0x310, self.p+0x150)
        self.put(self.p+0xD80, 0x511070)  # native bank source, not the kickoff idle fixture
        self.put(self.state+0x14, 0)
        self.component(0x305920, ecx=self.p, edx=0x511070)
        for i, who in enumerate(self.players):
            self.put(who+0x40, 0x2058000+i*0x100)  # bounded native event statistics
        if presnap_node is not None:
            self.put(0xE602B8, 13)
            self.command(presnap_node)
            self.component(0x2D6550, ecx=self.p)
            task = self.get(self.gameplay+0x310)
            self.presnap_aim = (self.readf(task+0x20), self.readf(task+0x28))
            self.presnap_heading = self.get(task+0x30)
            # Native presnap positioning, using the actual computed point.
            # This is the last fixture position write before all snap frames.
            self.place(self.p, *self.presnap_aim)
            self.heading(self.presnap_heading)
        self.put(0xE602B8, 14)
        self.put(0xBE4D40, deep_count | (deep_count << 10))
        for i in range(deep_count):
            va = 0xBE4B60+i*16
            self.put(va, self.p if i == 0 else self.players[12+i])
            self.f32(va+4, self.readf(self.transform+0x30))
            self.f32(va+8, 20*YARD*direction)
            self.put(va+12, mode)
        self.zone_node = codec.Node(0x0D, 6, [0, 20*YARD, 9, 0, 0, 0, 0])
        self.initialize()
        self.full = full
        if full:
            self.put(self.gameplay, 1)
            for who, nxt in zip(self.players, self.players[1:]+[0]):
                self.put(who+0x30, nxt)
            self.put(0xE60268, self.players[0])
        self.owner_writes.clear()

    def flags(self):
        return self.uc.mem_read(self.record+patch.FLAGS_OFFSET,1)[0]

    def _native_hit(self, uc, address, size, data):
        self.hits.append(address)

    def _owner_write(self, uc, access, address, size, value, data):
        pc = uc.reg_read(x86.UC_X86_REG_EIP)
        if pc in self.code_range:
            self.owner_writes.append((pc, address, size, value))

    def assets(self):
        self.uc.mem_map(0x2500000, 0x40000)
        for ix, row in enumerate([0x510E88+i*40 for i in range(9)]+[0x5105C8, 0x510CD0]):
            clip, asset = self.get(row+4), 0x2500000+ix*0x4000
            nominal = struct.unpack('<i', self.uc.mem_read(row+0x10, 4))[0]
            self.uc.mem_write(clip, struct.pack('<BBH', 25, 0, 61))
            self.put(clip+4, 1)
            self.uc.mem_write(clip+0xC, b'\x3c')
            for field, value in ((0x10, 1), (0x14, 1), (0x18, YARD), (0x20, YARD)):
                self.f32(clip+field, value)
            for field, offset in ((0x24, 0), (0x28, 0x2000), (0x2C, 0x2200)):
                self.put(clip+field, asset+offset)
            self.put(asset+0x2200, -1)
            self.uc.mem_write(asset, struct.pack('<1525I', *([0xE0080200]*1525)))
            angle = nominal*math.tau/65536
            self.uc.mem_write(asset+0x2000, b''.join(struct.pack('<4h',
                round(math.sin(angle)*n*YARD/60*8), 100,
                round(math.cos(angle)*n*YARD/60*8), 0) for n in range(61)))

    def command(self, node):
        raw = node.to_bytes()
        self.uc.mem_write(self.OPS, raw)
        decoder = self.get(0x521078+node.op*20+4)
        self.component(decoder, ecx=0x2018000, edx=int.from_bytes(raw[4:], 'little'), args=(node.flags,))
        for i in range(len(node.operands)):
            self.f32(self.gameplay+0x430+4*i, self.readf(0x2018000+12*i+4))

    def initialize(self):
        self.command(self.zone_node)
        self.component(0x1A6220, ecx=self.p)
        self.task = self.get(self.gameplay+0x310)

    def pass_event(self, actor=None):
        """Execute the real animation callback, trajectory, release and event writer."""
        self.component(0x35AF40, args=(0, actor or self.qb))

    def step(self, frame):
        self.owner_writes.clear()
        self.f32(0xB71D00, frame*DT)
        self.f32(0xB71D0C, DT)
        self.put(0xB71D10, frame+1)
        if self.full:
            self.frame()
        else:
            self.component(self.get(self.task), ecx=self.p)
            self.component(0x1CD5D0, ecx=self.p)
            self.component(0x28DFE0)
            self.component(0x218010, esi=self.p)
            self.component(0x28E360)
        self.component(0x217AE0, ecx=self.p)
        x, z = self.readf(self.transform+0x30), self.readf(self.transform+0x38)
        qx, qz = self.readf(self.qb+0xB30), self.readf(self.qb+0xB38)
        desired = round(math.atan2(qx-x, qz-z)*65536/math.tau)
        facing = self.uc.reg_read(x86.UC_X86_REG_EAX)&65535
        return dict(frame=frame, x=x, z=z, depth=z*self.direction/YARD,
                    effective_facing=facing, heading=self.get(self.transform+0x50),
                    facing_error=abs(signed_angle(facing-desired))*360/65536,
                    throttle=self.readf(self.steer+0x10), direction=self.get(self.steer+0x14),
                    row=hex(self.get(self.state+0x1C)), bank=hex(self.get(self.state+0x14)),
                    callback=hex(self.get(self.task)), target=hex(self.get(self.task+0x40)),
                    policy=self.flags() if self.record else 0,
                    fast_latch=bool(self.get(self.gameplay+0x584)&0x40000))
