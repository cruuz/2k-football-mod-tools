"""Bounded native toss/menu/period fixture, with declared presentation seams.

Accepted coin call and row selection are input boundaries. Native RNG,
winner assignment, controller membership, profile CPU default, two-row menu
construction, choice callbacks, kickoff records and halftime run unmodified
except the owner under test. No scene is rendered or physical kick simulated.
"""
from tests.nfl2k5_accelerated_clock_native import Machine as ClockMachine, uc, x86


class Machine(ClockMachine):
    HOME, AWAY, MENU = 0xE5FC20, 0xE5FC60, 0xC38490

    def __init__(self, payload):
        super().__init__(payload)
        for team, opponent, score, selection in (
                (self.HOME, self.AWAY, self.OFF+0x100, self.SELECT),
                (self.AWAY, self.HOME, self.DEF+0x100, self.DSELECT)):
            self.put(team, opponent)
            self.put(team+8, score)
            self.put(team+12, selection)
        self.put(0xE60280, self.HOME)
        self.put(0xE60284, self.AWAY)
        self.put(0xA83A18, 3)
        self.put(0xBA04B0, 0)  # no learned profile; native default receives
        self.put(0xBA04B4, 0)
        self.stubs.update({va: (0, 0) for va in (
            # Announcer, overlay registration, rendering and period scene services.
            0x67DF0, 0x1BB150, 0x1B3180, 0x8A3F0, 0x8A2E0, 0x8ACF0,
            0x8D340, 0x834F0, 0x1CEED0, 0x89440, 0x1D3210,
            0x100780, 0x1D1F80, 0xCECD0, 0x125C50, 0x84270,
            0x1CF4B0, 0xCD560, 0x1B12D0, 0x9FD90,
            0x11CE80, 0x11CE60, 0xDA4D0, 0x1BAEF0, 0xABEB0,
            0x188C50, 0x1CEE80, 0xCD4D0,
        )})
        self.stubs[0x12D610] = (0, 4)
        # Loaded team names, consumed by the native UTF-16 formatter.
        for team, at, name in ((0xB30864, self.OFF+0x800, 'Home'),
                               (0xB30A58, self.DEF+0x800, 'Away')):
            self.put(team+0x104, at)
            self.uc.mem_write(at, (name+'\0').encode('utf-16le'))

    def controllers(self, *sides):
        for index in range(8):
            self.run(0x77200, ecx=index, edx=sides[index] if index < len(sides) else 0)

    def toss(self, *, outcome=0, draw=0, human_side=1, period=1):
        self.controllers(human_side)
        self.put(0xE602C4, period)
        self.run(0xB8170, ecx=self.AUX)
        # Accepted away heads/tails input: tails (0). No winner is supplied.
        self.put(0xC39188, 0)
        self.run(0xB8260, ecx=0)
        # Seed the native additive RNG for the toss and next deferral roll.
        rng = 0xE5FCA0
        self.uc.mem_write(rng, bytes(8+55*8))
        self.put(rng, 0)
        self.put(rng+4, 1)
        self.put(rng+8, outcome)
        self.put(rng+8+54*8, draw-outcome)
        self.run(0x25E9B0, count=100000)

    def row(self, index):
        if not 0 <= index < self.get(self.MENU+8):
            raise AssertionError('requested row is absent from the native menu')
        return self.get(self.MENU+12+0x228*index)

    def choose_row(self, index):
        return self.run(self.row(index), count=200000)

    def next_half(self):
        # Supplied end-of-Q2 situation, then native end/halftime/start commands.
        self.put(0xE602C4, 2)
        self.f32(self.GAME+16, 0)
        self.run(0xB8B30, count=200000)
        self.run(0xB88C0, count=200000)

    def text(self, at):
        raw = bytes(self.uc.mem_read(at, 128))
        end = next(i for i in range(0, len(raw), 2) if raw[i:i+2] == b'\0\0')
        return raw[:end].decode('utf-16le')
