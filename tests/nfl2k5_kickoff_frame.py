"""Bounded 11A7C0 replay with synthetic player/clip/skeleton/roster objects.

Every dispatcher phase and player writer executes from the pinned retail XBE
plus the owner patch. No game, display, audio device, disc or pack is opened.
This fixture proves native CPU behavior for its stated inputs, not gameplay.
"""
from collections import Counter
import hashlib
import struct

from tests.mod_editor.test_nfl2k5_kickoff_v2 import NativeMachine
from tests.mod_editor.test_nfl2k5_dynamic_kickoff import Machine, x86, uni
from mod_editor.core import nfl2k5_dynamic_kickoff as dk
from tools import nfl2k5_kickoff_alignment as alignment


PHASES = (
    0xAF2C0, 0x28DFE0, 0x217C90, 0xA28C0, 0x75BD0, 0x5D830, 0x190D00,
    0x18C1F0, 0x156A80, 0x89BA0, 0xE9210, 0x214FC0, 0xF7C10, 0x1E08D0,
    0x2180D0, 0x28ECF0, 0x28CC30, 0x1CCFA0, 0x28F4F0, 0x1DFAA0,
    0x1D30F0, 0x17C2E0, 0xA7930, 0x1D1B80, 0x94AB0, 0x5DA70, 0x125BC0,
)
SITES = {
    0x11A7C0, 0x1CD5D0, 0x218010, 0x31BEB0, 0xDF9B0, 0xDFA50, 0xDFB40,
    0xE0110, 0x28E360, 0x93800, 0x28C5B0, 0x2CC570, 0x304F60,
    0x28CE90, 0x1DF430, 0x213310, 0x1E09D0, 0x214F60, 0x1A89E0,
    0x1E0280, 0x1DADD0, 0xA1530, 0x1DD720, 0xDF2F0, 0x217F90,
}
FIELDS = ('transform', 'primary_blend', 'secondary_blend', 'sampled_pose',
          'skeleton_root', 'skeleton_high_root')


class FrameMachine(NativeMachine):
    instruction_limit = 2_000_000
    frame_timeout_us = 0

    def __init__(self, payload, *, radius=30, tasks=True, **kwargs):
        self.visited = Counter()
        self.watches, self.writes, self.phase_entries = [], [], []
        self.watch_words = {}
        self.phase = 0
        super().__init__(payload, **kwargs)
        self.uc.mem_map(0x2050000, 0x200000)
        self.uc.mem_write(self.CALLBACK + 0x90, b'\xd9\xe8\xc3')
        # Remove the old slice's animation/planning leaves. Hardware input is
        # absent; final audio gain submission is an ABI leaf. None of PHASES,
        # pose math, collision resolution, ground/root or player planners is a leaf.
        for address in (0x217F90, 0x31BEB0, 0x2D6B70, 0x1E09D0, 0x213310, 0xAF4F0):
            self.stub_pops.pop(address, None)
        self.stub_pops.update({0x63810: 0, 0x65550: 0, 0x1C3E10: 4,
                               0x1C3E70: 4, 0x1C3ED0: 4, 0x1C3F30: 4})
        self.fpu_stubs[0x17B010] = 4  # roster attribute lookup, ST0=1
        self.uc.mem_write(0xAAB8C0, struct.pack('<20f', *([1] * 20)))
        self.put(0xE5FFA8, 1)  # native dispatcher dt scale = 1
        self.put(0xBA99DC, 0)  # full frame, not the paused early return
        self.put(0xB6FF64, -1)  # no presentation event selected
        self.put(0xE5FC28, self.KICK_TEAM + 0x600)
        self.put(0xE5FC68, self.RECEIVE_TEAM + 0x600)
        self.f32(self.CLOCK + 0x10, 600)
        for address in (0xE60290, 0xE60294, 0xE60298, 0xE602A0):
            self.put(address, self.CLOCK)
        for address in (0xE60274, 0xE537F4, 0xE537F0):
            self.put(address, 0)  # no officials / presentation actors
        self._skeletons()
        self.players = []
        for index in range(22):
            kicking, slot = index < 11, index % 11
            old = ((self.KICKER if slot == 0 else self.COVERAGE) if kicking
                   else (self.RETURNER if slot < 2 else self.BLOCKER))
            who = self.clone(old, 0x2060000 + index * 0x1000, slot)
            self.players.append(who)
            self._player(who, index, radius)
            x, z = (alignment.kickoff_xz_2026() if kicking
                    else alignment.KICK_RETURN_XZ_2026)[slot]
            # Both books are in the kicking team's field frame. Add the tee
            # LOS: coverage ends near receiving 40, setup near receiving 35-30.
            self.place(who, self.direction * x,
                       self.readf(self.CTX + 0x18) + self.direction * z)
            self.uc.mem_write(who + 0xB00, bytes(self.uc.mem_read(who + 0xB30, 48)))
        self.KICKER, self.COVERAGE = self.players[:2]
        self.RETURNER, self.BLOCKER = self.players[11], self.players[13]
        self.held = self.players[1:11] + self.players[13:]
        self.free = [self.players[i] for i in (0, 11, 12)]
        for who, nxt in zip(self.players, self.players[1:] + [0]):
            self.put(who + 0x30, nxt)
        for team, players in ((self.KICK_TEAM, self.players[:11]),
                              (self.RECEIVE_TEAM, self.players[11:])):
            self.put(team + 4, players[0])
            for who, nxt in zip(players, players[1:] + [0]):
                self.put(who + 0x34, nxt)
        self.put(0xE60268, self.players[0])
        self.put(0xC168B0, self.players[0])  # native blocking scheduler cursor
        self.put(0xC16BD0, self.players[0])
        self.put(self.CTX + 0x1C4, self.KICKER)
        self.put(dk.PLAY_STATE, 13)
        if tasks:
            for who in self.players[13:]:
                # A distinct script node per blocker keeps the kicker's 08
                # launch opcode intact when installing native 11 block tasks.
                saved_node, saved_ops = self.NODE, self.OPS
                self.NODE = 0x2103E00 + self.players.index(who) * 0x8000
                self.OPS = self.NODE + 0x20
                self.put(who + 0x61C, self.NODE)
                self.put(self.NODE + 4, self.OPS)
                self.block(who)  # native opcode decode and 2400B0 task installation
                self.NODE, self.OPS = saved_node, saved_ops
                self.put(who + 0x200, 1)  # native scheduler's first task group
        for who, kind, start, length in self.watches:
            for address in range(start, start + length, 4):
                self.watch_words[address] = (self.players.index(who), kind, start)
        # Narrow code hooks avoid a Python callback for every retail instruction.
        # Memory hooks still receive EVERY write in the watched object ranges.
        self.uc.hook_del(self.code_hook)
        self.uc.hook_del(self.write_hook)
        for site in sorted(set(PHASES) | SITES | set(self.stub_pops)
                           | set(self.fpu_stubs) | {dk.RAND}):
            self.uc.hook_add(uni.UC_HOOK_CODE, self._hook, begin=site, end=site)
        self.frame_write_hook = self.uc.hook_add(uni.UC_HOOK_MEM_WRITE, self._write,
                                                begin=0x2060000, end=0x21AFFFF)
        self.visited.clear()
        self.calls.clear()

    def _skeletons(self):
        # Synthetic 25-bone low / 62-bone high star hierarchies, parent 0 for
        # every child. Native quaternion decode, scaling and hierarchy math run.
        self.put(0xB65B78, 0x2050000)
        self.put(0x2050004, 0x2051000)
        self.uc.mem_write(0x2050010, struct.pack('<4f', 1, 0, 0, 1) * 25)
        self.uc.mem_write(0xB65BFC, bytes(range(25)))
        self.put(0xB65288, 0x2052000)
        self.put(0x205202C, 1)
        self.put(0x2052030, 0x2053000)
        for shape, count, nodes in ((0x2051000, 25, 0x2054000),
                                    (0x2053000, 62, 0x2055000)):
            self.uc.mem_write(shape + 0x50, struct.pack('<H', count))
            self.put(shape + 0x64, nodes)
            for n in range(count):
                self.put(nodes + n * 0x70 + 0x64, -1 if n == 0 else 0)

    def _player(self, who, index, radius):
        base = 0x2100000 + index * 0x8000
        clip = base + 0x100
        self.put(who + 0xDC4, clip)  # sole zero-speed clip selection entry
        self.uc.mem_write(clip, struct.pack('<BBH', 25, 0, 3))
        self.put(clip + 4, 1)  # looping, 60 fps, three packed quaternion keys
        self.uc.mem_write(clip + 0xC, b'\x3c')
        self.f32(clip + 0x10, 1)
        self.f32(clip + 0x14, 2 / 60)
        for field, offset in ((0x24, 0x200), (0x28, 0x400), (0x2C, 0x420)):
            self.put(clip + field, base + offset)
        self.put(base + 0x420, 0xFFFFFFFF)  # event sentinel
        identity = 0xE0080200
        keys = [identity] * 25 + [identity + 10] * 25 + [identity] * 25
        self.uc.mem_write(base + 0x200, struct.pack('<75I', *keys))
        self.uc.mem_write(base + 0x400, struct.pack('<12h',
                          0, 100, 0, 0, 200, 140, 300, 1024, 0, 100, 0, 0))
        for n, (field, off) in enumerate(((0xC58, 0), (0xC5C, 0x40),
                                          (0xC74, 0x80), (0xC78, 0xC0))):
            channel = base + off
            self.put(who + field, channel)
            self.put(channel, clip)
            self.f32(channel + 8, 1)
            for ptr, offset in ((0x24, 0), (0x28, 0x100), (0x2C, 0x2A0)):
                self.put(channel + ptr, base + 0x500 + n * 0x500 + offset)
        for field in (0xC30, 0xC34):
            self.put(who + field, base + 0x1900)
        self.uc.mem_write(base + 0x1900, struct.pack('<4f', 0, 0, 0, 1) * 25)
        self.put(who + 0xC04, 0x1FFFFFF)
        self.put(who + 0xC08, 0x1FFFFFF)
        self.put(who + 0xC1C, 1)
        for off in (0xB84, 0xB8C, 0xB94, 0xBA0):
            self.f32(who + off, 1)
        self.put(who + 4, base + 0x2000)
        self.put(who + 0x98C, 0x800)  # explicit post-sampler ground/height callback
        self.put(who + 0x91C, 0x510F08)  # retail idle descriptor group
        self.put(who + 0xA94, self.CALLBACK + 0x90)  # height attribute = 1
        self.put(who + 0x904, 0x50F4EC)
        self.put(who + 0x510, who + 0x150)  # empty task-stack sentinel
        self.uc.mem_write(who + 0xF2B, b'\x48')  # 72-inch roster height
        # Minimal valid fatigue and accessory clock objects for the late pass.
        self.put(who + 0xF30, base + 0x3D00)
        self.put(base + 0x3D04, base + 0x3D10)
        self.f32(base + 0x3D10, 1)
        self.f32(base + 0x3D14, 1)
        self.put(base + 0x3D0C, base + 0x3D20)
        # One native collision sphere at bone 0; the broadphase/resolver are real.
        self.put(who + 0xE38, 4)
        self.put(who + 0xE00, base + 0x3C00)
        self.put(who + 0xE04, base + 0x3C10)
        self.put(base + 0x3C00, 1)
        self.put(base + 0x3C04, base + 0x3C20)
        self.put(base + 0x3C14, base + 0x3C40)
        self.f32(base + 0x3C30, radius)
        self.uc.mem_write(who + 0x2F, bytes([index]))
        self.watches.extend((
            (who, 'transform', who + 0xB00, 96),
            (who, 'primary_blend', who + 0xC6C, 4),
            (who, 'secondary_blend', who + 0xC88, 4),
            (who, 'sampled_pose', base + 0x1900, 400),
            (who, 'skeleton_root', base + 0x2000, 64),
            (who, 'skeleton_high_root', base + 0x2640, 64),
        ))

    def seed_residuals(self, *, turn=True, separation=True):
        """One entry seed, never a frame-by-frame position or pose correction."""
        for who in self.held:
            transform, collision = self.get(who + 0x18), self.get(who + 0x24)
            if turn:
                self.put(transform + 0x6C, (700 << 16) | 600)
                self.put(transform + 0x74, 1800)
                self.put(transform + 0x78, -200)
            self.f32(transform + 0x7C, 100)
            self.f32(transform + 0x80, 20)
            if separation:
                self.f32(collision + 0x34, .2)
                self.f32(collision + 0xB0, 1)
                self.f32(collision + 0xB8, -1)
            self.put(who + 0xC1C, 7)
            self.f32(who + 0xC6C, .37)
            self.f32(who + 0xC88, .63)
            for field in (0xC58, 0xC74):
                self.f32(self.get(who + field) + 4, .02)

    def _hook(self, uc, address, size, data):
        self.visited[address] += 1
        if address in PHASES:
            self.phase = address
            self.phase_entries.append(address)
        Machine._hook(self, uc, address, size, data)

    def _write(self, uc, access, address, size, value, data):
        found = self.watch_words.get(address & ~3)
        if found:
            player, kind, start = found
            assert size <= 8, 'Unicorn write value cannot represent this access'
            old = bytes(uc.mem_read(address, size))
            new = (value & ((1 << (8 * size)) - 1)).to_bytes(size, 'little')
            # Include unchanged and intermediate writes, with both bit patterns.
            self.writes.append((player, kind, self.phase,
                                uc.reg_read(x86.UC_X86_REG_EIP), address - start,
                                old.hex(), new.hex()))

    def snapshot(self):
        return {(self.players.index(who), kind): bytes(self.uc.mem_read(start, size))
                for who, kind, start, size in self.watches}

    def frame(self):
        self.writes.clear()
        self.phase_entries.clear()
        self.uc.reg_write(x86.UC_X86_REG_ESP, self.STACK)
        self.put(self.STACK, self.STOP)
        self.f32(self.STACK + 4, 1 / 60)
        self.uc.emu_start(0x11A7C0, self.STOP, count=self.instruction_limit,
                          timeout=self.frame_timeout_us)
        assert self.uc.reg_read(x86.UC_X86_REG_EIP) == self.STOP, 'frame execution bound reached'
        assert tuple(self.phase_entries) == PHASES, self.phase_entries
        assert self.uc.reg_read(x86.UC_X86_REG_ESP) == self.STACK + 8, 'frame ABI imbalance'
        return self.snapshot()

    def outer_scene(self):
        """Run retail camera construction, as game setup does at 64991.

        The former 5F7BA fault was a missing A55A0 call, not a missing
        camera resource. 5F710 constructs the camera objects and A5490
        selects the CPU camera table. A5620 then installs its retail
        spring/configuration pointer through 60090 on the first update.
        Player clips and skeletons remain the declared synthetic inputs.
        """
        self.outer_manager = 0x205D000
        self.put(0xA83A18, 3)
        self.f32(self.outer_manager + 0x104, 1 / 60)
        # No active highlight in the fixture's replay slot.
        self.put(0xBB6DB8 + 0x190 + 0x188, -1)
        self.run(0xA55A0, budget=self.instruction_limit)

    def outer_frame(self):
        """Complete mixed game callback; rendering is a separate event."""
        self.writes.clear()
        self.phase_entries.clear()
        self.run(0x64CD0, ecx=self.outer_manager, budget=self.instruction_limit)
        assert tuple(self.phase_entries) == PHASES, self.phase_entries
        assert self.uc.reg_read(x86.UC_X86_REG_ESP) == self.STACK + 4
        return self.snapshot()


PREKICK_SITES = {
    0x1853D0, 0x183D30, 0x2111D0, 0x186160, 0x183CD0, 0x1ABCF0,
    0x1881E0, 0x1FF940, 0x1580F0, 0x158C90, 0xB6F30, 0xB45A0,
    0x1211E0, 0x70AF0, 0x201E70, 0x202160, 0x2D6CD0,
    0x28F310, 0x1DF3B0, 0x2176B0,
}
PREKICK_FIELDS = FIELDS + ('turn_spring', 'primary_clock', 'secondary_clock',
                          'head_rotation', 'head_mode', 'skeleton_low', 'skeleton_high')


class PreKickMachine(FrameMachine):
    """Native lineup-completion handoff, readiness aggregation and input replay.

    Initial task targets and arrival counters describe players at their marks.
    1853D0 checks facing/arrival and calls 183D30 -> 2111D0; Python never writes
    the completed player state or a later global play state. The two free deep
    players finish later, giving a long state-12 window. The approach command
    is delivered at B6F30's ABI, not by simulating the game's CPU decision loop.
    Synthetic ready clips and decoded controller axes are external inputs.
    """
    def __init__(self, payload, **kwargs):
        super().__init__(payload, tasks=False, **kwargs)
        self.state_writes = []
        self.input_frames = []
        self.put(dk.PLAY_STATE, 12)
        self.put(self.CTX + 0x1C4, 0)
        self.put(0xE602D8, self.GAME + 0x400)
        self.put(0xE602DC, self.GAME + 0x800)
        self.put(0xE602E8, self.GAME + 0xC00)
        for team, book in ((self.KICK_TEAM, self.KICK_BOOK),
                           (self.RECEIVE_TEAM, self.RECEIVE_BOOK)):
            self.put(team + 0x30C, book + 0x400)  # valid selected-play operands
        for index, who in enumerate(self.players):
            self.run(0x2C9AB0, ecx=self.get(who + 0x20), edx=0)
            task = self.get(who + 0x510)
            self.uc.mem_write(task + 0x20, bytes(self.uc.mem_read(who + 0xB30, 16)))
            self.put(task + 0x30, self.get(who + 0xB50))
            self.put(task + 0x38, 3)  # native arrival band; facing is rechecked
            self.put(task + 0x3C, 1)
            self.put(who + 0x5E4, 12)  # initial lineup input, before observation
            # Retail ready descriptor, valid matching group, synthetic clip.
            # Its normal planner and both skeletal LODs execute in the old case.
            self.put(who + 0x904, 0x50F1E4)
            self.put(who + 0x9D0, 0x510F08)
            self.put(who + 0x9D4, 0x205F000)
            base = 0x2100000 + index * 0x8000
            self.watches.extend((
                (who, 'turn_spring', who + 0xB68, 28),
                (who, 'primary_clock', base + 4, 8),
                (who, 'secondary_clock', base + 0x84, 8),
                (who, 'head_rotation', who + 0x9B0, 16),
                (who, 'head_mode', who + 0xAA8, 4),
                (who, 'skeleton_low', base + 0x2000, 25 * 64),
                (who, 'skeleton_high', base + 0x2640, 62 * 64),
                (who, 'lineup_state', who + 0x5E4, 4),
            ))
        # A selected coverage man and setup blocker receive held diagonal input.
        # The native 70AF0 -> 1211E0 path reads these decoded hardware samples.
        for controller, who in enumerate((self.COVERAGE, self.BLOCKER)):
            self.put(who + 0x100, controller)
            self.f32(0xB37B00 + controller * 0x244 + 8 * 8, .8)
            self.f32(0xB37B00 + controller * 0x244 + 9 * 8, -.6)
        self.watch_words.clear()
        for who, kind, start, length in self.watches:
            for address in range(start, start + length, 4):
                self.watch_words[address] = (self.players.index(who), kind, start)
        for site in sorted(PREKICK_SITES | {0x2180D0}):
            if site not in set(PHASES) | SITES | set(self.stub_pops) | set(self.fpu_stubs):
                self.uc.hook_add(uni.UC_HOOK_CODE, self._hook, begin=site, end=site)
        self.uc.hook_add(uni.UC_HOOK_MEM_WRITE, self._state_write,
                         begin=dk.PLAY_STATE, end=dk.PLAY_STATE + 3)
        self.visited.clear()
        self.calls.clear()
        self.writes.clear()

    def _state_write(self, uc, access, address, size, value, data):
        self.state_writes.append([self.phase, uc.reg_read(x86.UC_X86_REG_EIP),
                                  self.get(dk.PLAY_STATE), value])

    def _hook(self, uc, address, size, data):
        if address == 0x2180D0 and hasattr(self, 'input_frames'):
            self.input_frames.append([self.readf(who + 0x110)
                                      for who in (self.COVERAGE, self.BLOCKER)])
        super()._hook(uc, address, size, data)

    def complete_lineup(self, players):
        self.phase = 0  # an explicit native handoff outside the frame dispatcher
        self.writes.clear()
        for who in players:
            assert self.get(who + 0x5E4) == 12
            self.run(0x1853D0, ecx=who)
            assert self.uc.reg_read(x86.UC_X86_REG_EAX) == 1
            assert self.get(who + 0x5E4) == 13
            self.run(0x186160, ecx=who)  # native pending-event ready task
            self.put(who + 0x620, 0x4000)  # external wait-for-event script operand
            self.put(who + 0x200, 1)  # native task scheduler's first group
        return self.snapshot()

    def approach(self):
        self.phase = 0
        self.writes.clear()
        self.run(0xB6F30)  # complete native transition, including history and clocks
        assert self.get(dk.PLAY_STATE) == 14

    def native_state(self):
        return dict(play_state=self.get(dk.PLAY_STATE), flags=self.flags(),
                    team_ready=[self.get(team + 0x324) for team in
                                (self.KICK_TEAM, self.RECEIVE_TEAM)],
                    players=[[self.get(who + 0x5E4), self.get(who + 0x904)]
                             for who in self.players])


class WriteReceipt:
    """Lossless dictionary encoding of every held-player write and final state.

    An event is [player, field, phase PC, writer PC, offset, before hex, after
    hex]; its byte count is len(after)/2. Each frame refers to an ordered event
    sequence. Repeated frames reuse a sequence, never omit writes. State entries
    contain all watched bytes, including fields with no writes that frame.
    """
    def __init__(self):
        self.events, self.sequences, self.states, self.frames = [], [], [], []
        self._events, self._sequences, self._states = {}, {}, {}
        self.writer_counts = Counter()

    @staticmethod
    def _intern(value, index, items):
        if value not in index:
            index[value] = len(items)
            items.append(value)
        return index[value]

    def add(self, machine, snapshot):
        held = {machine.players.index(who) for who in machine.held}
        events = []
        for event in machine.writes:
            if event[0] in held:
                events.append(self._intern(event, self._events, self.events))
                self.writer_counts[event[1], event[2], event[3]] += 1
        sequence = self._intern(tuple(events), self._sequences, self.sequences)
        state = tuple((player, kind, raw.hex()) for (player, kind), raw in sorted(snapshot.items())
                      if player in held)
        state_id = self._intern(state, self._states, self.states)
        self.frames.append([sequence, state_id])

    def result(self):
        return {'event_columns': ['player', 'field', 'phase_pc', 'writer_pc',
                                 'offset', 'before', 'after'],
                'events': self.events, 'sequences': self.sequences,
                'states': self.states, 'frames': self.frames,
                'writer_counts': [[kind, phase, pc, count]
                                  for (kind, phase, pc), count in sorted(self.writer_counts.items())]}

    def digest(self):
        import json
        return hashlib.sha256(json.dumps(self.result(), separators=(',', ':')).encode()).hexdigest()
