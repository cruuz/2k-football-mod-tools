"""Bounded native coverage/pursuit frame components with supplied routes.

Reuses the kickoff frame fixture's synthetic skeleton and native root sampler.
The man planner (1A4830), close pursuit planner (2E8730), ordinary dispatcher,
acceleration, animation rate, turn integrator, sampler and world transform all
execute XBE instructions. The receiver/carrier path is supplied input; it is
not an executed route script. Contact/tackles, full task scheduling and real
animation assets are outside this fixture. A straight synthetic clip is the
same on both sides. No Python writes the defender's position after setup.
"""
from __future__ import annotations

import math
import struct

from tests.nfl2k5_kickoff_frame import FrameMachine
from tests.mod_editor.test_nfl2k5_dynamic_kickoff import uni, x86
from mod_editor.core import nfl2k5_accel_ramp as ramp

YARD = 91.44
DT = 1 / 60


def signed_angle(value):
    return (value + 32768) % 65536 - 32768


class TrailFrame(FrameMachine):
    def __init__(self, payload, *, planner="man", direction=1, acceleration=False,
                 defender=(100, 1000), heading=32768, speed=.9, agility=.8):
        self.frame_rolls = []
        self.frame_lapses = 0
        self.turn_budget = None
        self.native_aim = None
        super().__init__(payload, tasks=False, direction=direction)
        # Unicorn starts with control word zero (unmasked, reserved precision),
        # unlike an initialized x87. Supply the architectural FNINIT control
        # word. The hook separately proves preservation of 0x27F caller state.
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        # The legacy mapping omitted the header, where the shipped ramp lives.
        self.uc.mem_write(0x10000, payload[:0x1000])
        self.uc.mem_protect(0x10000, 0x1000, uni.UC_PROT_READ | uni.UC_PROT_EXEC)
        self.acceleration = acceleration
        self.planner = planner
        self.rating = speed
        self.p, self.target = self.players[12], self.players[1]
        self.state, self.transform, self.steer = self.p + 0x900, self.p + 0xB00, self.p + 0x100
        self.task = 0x2041000
        self.uc.mem_map(0x2400000, 0x10000)
        for who, slot in ((self.p, 0), (self.target, 1)):
            self.put(who + 0x30, 0)
            self.put(who + 0x510, self.task + slot * 0x1000)
            self.put(who + 0x904, 0x50F4EC)
            self.put(who + 0x928, 0)
            self.f32(who + 0xAB4, speed)
            self.f32(who + 0xAB8, agility)
            self.f32(who + 0xA90, 1)
            self.f32(who + 0x954, 1)
            self.f32(who + 0x958, 1)
            table = 0x2043000 + slot * 0x1000
            clip = self.get(self.get(who + 0xC74))
            self.put(who + 0x914, table)
            self.put(who + 0x918, table + 4)
            self.put(who + 0x91C, table + 0x20)
            self.f32(table + 4, -1)
            self.f32(table + 8, 2)
            self.put(table + 12, table + 0x20)
            self.put(table + 0x20, 1)
            self.put(table + 0x24, clip)
            self.put(table + 0x28, -32768)
            self.put(table + 0x2C, 32767)
            self.f32(table + 0x34, 0)
            self.f32(table + 0x38, 100)
            self.put(table + 0x40, 0x2382E0)
            self.put(table + 0x44, 0x237C90)
            self.f32(clip + 0x18, YARD)
            self.f32(clip + 0x20, YARD)
            asset = 0x2400000 + slot * 0x8000
            self.uc.mem_write(clip, struct.pack("<BBH", 25, 0, 61))
            self.f32(clip + 0x14, 1)
            self.put(clip + 0x24, asset)
            self.put(clip + 0x28, asset + 0x2000)
            self.uc.mem_write(asset, struct.pack("<1525I", *([0xE0080200] * 1525)))
            # The native compressed root keys have an eighth-unit scale.
            self.uc.mem_write(asset + 0x2000, b"".join(
                struct.pack("<4h", 0, 100, round(n * YARD / 60 * 8), 0)
                for n in range(61)))
            self.f32(who + 8, 1)
        self.put(0xE60268, self.p)
        self.put(self.task, 0x1A4830 if planner == "man" else 0x2EAB60)
        self.put(self.task + 0x40, self.target)
        self.f32(self.task + 0x34, 1)
        self.put(self.p + 0x200 + 0x584, 0x40000)
        self.put(0xE602EC, self.GAME)
        self.put(self.GAME + 0x1C4, 0)
        self.put(self.GAME + 0x1C8, 0)
        self.put(self.GAME + 0x130, 0)
        self.put(0xE602B4, 0)
        self.put(0xE602B8, 14)
        self.uc.mem_write(self.p + 0x2C, bytes([18 if planner == "man" else 16]))
        self.place(self.p, defender[0] * direction, defender[1] * direction)
        self.place(self.target, 0, 800 * direction, 0, 400 * direction)
        self.heading((heading + (32768 if direction < 0 else 0)) & 65535)
        self.seed_rng()
        self.uc.mem_write(self.CALLBACK + 0xE0,
                          b"\xd9\x1d" + struct.pack("<I", self.SCALAR) + b"\xc3")
        for va in (0x1ADB80, 0x48B90, 0x48B50, 0x2FC9F0, 0x2FCA07, 0x2E8854, 0x1ADF90):
            self.uc.hook_add(uni.UC_HOOK_CODE, self._observe, begin=va, end=va)
        self.executed_leaves = set()
        self.visited.clear()

    def heading(self, value):
        for off in (self.state + 0xC, self.state + 0x10,
                    self.p + 0xC28, self.transform + 0x50):
            self.put(off, value)

    def seed_rng(self, seed=0x600000):
        self.uc.mem_write(0xE5FCA0, bytes(448))
        self.put(0xE5FCA4, 1)
        self.put(0xE5FCA8, seed)

    def _hook(self, uc, address, size, data):
        if address == 0x48BC0:
            # Execute the real integer-roll wrapper instead of the kickoff leaf.
            self.visited[address] += 1
            return
        if hasattr(self, "executed_leaves") and (address in self.stub_pops or address in self.fpu_stubs):
            self.executed_leaves.add(address)
        super()._hook(uc, address, size, data)

    def _observe(self, uc, address, size, data):
        if address == 0x1ADB80:
            self.frame_lapses += 1
        elif address == 0x48B50:
            # Native additive RNG's next word; the generator still executes.
            base = uc.reg_read(x86.UC_X86_REG_ECX)
            i, j = self.get(base), self.get(base + 4)
            if i < 55 and j < 55:
                word = (self.get(base + 8 + i * 8) + self.get(base + 8 + j * 8)) & 0xFFFFFFFF
                self.frame_rolls.append(word)
        elif address == 0x2FCA07:
            self.turn_budget = self.readf(uc.reg_read(x86.UC_X86_REG_ESP) + 4)
        elif address == 0x2E8854:
            sp = uc.reg_read(x86.UC_X86_REG_ESP)
            self.native_aim = (self.readf(sp + 0x50), self.readf(sp + 0x58))
        elif address == 0x1ADF90:
            point = uc.reg_read(x86.UC_X86_REG_EDX)
            self.native_aim = (self.readf(point), self.readf(point + 8))

    def component(self, address, **kwargs):
        self.run(address, budget=2_000_000, **kwargs)
        expected = self.STACK + 4 + 4 * len(kwargs.get("args", ()))
        if self.uc.reg_read(x86.UC_X86_REG_ESP) != expected:
            raise AssertionError(f"native component {address:#x} changed the stack contract")

    def step(self, frame, point):
        self.writes.clear()
        self.frame_rolls.clear()
        self.frame_lapses = 0
        self.turn_budget = None
        self.native_aim = None
        old_x, old_z = self.readf(self.transform + 0x30), self.readf(self.transform + 0x38)
        old_heading = self.get(self.transform + 0x50)
        x, z, vx, vz = (value * self.direction for value in point)
        self.uc.mem_write(self.target + 0xB30, struct.pack("<8f", x, 0, z, 1, vx, 0, vz, 0))
        self.put(0xB71D10, frame + 1)
        self.f32(0xB71D00, frame * DT)
        self.f32(0xB71D0C, DT)
        if self.acceleration:
            # The complete shipped hook/cave, at its original cache-write ABI.
            self.uc.reg_write(x86.UC_X86_REG_EBX, self.p)
            self.run(ramp.HOOK_VA, stop=ramp.HOOK_VA + 6, esi=self.state,
                     edx=struct.unpack("<I", struct.pack("<f", self.rating))[0])
        if self.planner == "man":
            self.component(0x1A4830, ecx=self.p)
        else:
            self.component(0x2E8730, ecx=self.p, edx=self.target, args=(0,))
            self.component(self.CALLBACK + 0xE0)  # save/pop native arrival estimate
        target_point = self.native_aim
        if target_point is None:
            raise AssertionError("fixture never observed a native steering target")
        command = self.get(self.steer + 0x14)
        throttle = self.readf(self.steer + 0x10)
        self.component(0x1CD5D0, ecx=self.p)
        self.component(0x28DFE0)
        self.component(0x218010, esi=self.p)
        self.component(0x28E360)
        px, pz = self.readf(self.transform + 0x30), self.readf(self.transform + 0x38)
        heading = self.get(self.transform + 0x50)
        return dict(frame=frame, defender_x=px, defender_z=pz, target_x=x, target_z=z,
                    aim_x=target_point[0], aim_z=target_point[1], heading=heading,
                    heading_degrees=signed_angle(heading) * 360 / 65536,
                    requested_heading=command,
                    turn_degrees=signed_angle(heading - old_heading) * 360 / 65536,
                    turn_rate=self.readf(self.state + 0x1AC), turn_budget=self.turn_budget,
                    throttle=throttle, final_throttle=self.readf(self.steer + 0x10),
                    movement_command=self.readf(self.state + 0x54),
                    cached_speed=self.readf(self.state + 0x1B4),
                    speed_yards_s=math.hypot(px - old_x, pz - old_z) / DT / YARD,
                    distance_yards=math.hypot(px - x, pz - z) / YARD,
                    lapse_words=list(self.frame_rolls), lapse_calls=self.frame_lapses,
                    descriptor=self.get(self.state + 4),
                    clip=self.get(self.get(self.p + 0xC74)))


def route(name, frame):
    if frame < 60:
        return (0, 800 + frame * 10, 0, 600)
    n = frame - 60
    if name == "crossing":
        return (-min(n, 100) * 8, 1400, -480 if n < 100 else 0, 0)
    if name == "comeback":
        return (0, 1400 - min(n, 35) * 8, 0, -480 if n < 35 else 0)
    if name == "cutback":
        return (min(n, 25) * 6, 1400 - min(n, 25) * 8,
                360 if n < 25 else 0, -480 if n < 25 else 0)
    raise ValueError(name)


def replay(payload, *, name, planner, frames=240, **kwargs):
    machine = TrailFrame(payload, planner=planner, **kwargs)
    rows = [machine.step(i, route(name, i)) for i in range(frames)]
    return rows, sorted(machine.executed_leaves)
