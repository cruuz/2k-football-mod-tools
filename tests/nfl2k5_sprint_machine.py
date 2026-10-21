"""Native sprint replay. Pad frames and an unobstructed animation are inputs.

Runs the real pad decoder/layout lookup, command dispatcher (including owner
hooks), charge routines, sprint initializer and speed arithmetic. Rendering,
collision response, VIP counters and notifications are peripheral boundaries.
The full animation state machine/game loop and physical displacement are not
simulated. No burst/charge/speed result is supplied by a stub.
"""
import struct
from unicorn import x86_const as x86
from tests.nfl2k5_abilities_machine import Machine
from tests.nfl2k5_input_decode_machine import PAD_BLOCK, ANALOG


class SprintMachine(Machine):
    GRAPHICS, ACTOR, LIVE_TEAM = 0x3007000, 0x3008000, 0x3009000
    SELECTOR, CLIP, ANIM1, ANIM2 = 0x300A000, 0x300B000, 0x300C000, 0x300D000

    def __init__(self, payload):
        super().__init__(payload)
        # Menu feedback, statistics and sound; never replace 0x120580 (the
        # actual context test for the held charge button), or layout lookup.
        for va in (0x18E310, 0x87590, 0x87540, 0x873F0, 0x87470, 0x872A0,
                   0x87340, 0x156840, 0x156810, 0x7A6D0, 0x1B32C0,
                   0x1B3340, 0xA20D0):
            self.uc.mem_write(va, b'\xc3')
        for va in (0x627C0, 0x771F0, 0x2F6150):
            self.uc.mem_write(va, b'\x31\xc0\xc3')
        self.previous_bits = 0

    def setup(self, *, carrier=True, controller=0, layout=0, team=0, abilities=0, speed=90):
        self.uc.mem_write(self.P, bytes(0xE000))
        self.player(controller=controller, context=10 if carrier else 9,
                    abilities=abilities, speed=speed)
        self.u32(self.P, team)
        self.u32(self.P + 0x14, self.GRAPHICS)
        self.u32(self.P + 0x20, self.ACTOR)
        self.u32(self.P + 0x38, self.LIVE_TEAM)
        self.f32(self.P + 8, 1)
        self.u32(self.S + 0x38, self.SELECTOR)
        self.u32(self.SELECTOR + 8, self.CLIP)
        self.u32(self.GRAPHICS + 0x58, self.ANIM1)
        self.u32(self.GRAPHICS + 0x74, self.ANIM2)
        for obj in (self.ANIM1, self.ANIM2):
            self.u32(obj, self.CLIP)
        self.f32(self.S + 0x190, 1)
        self.f32(self.S + 0x1B0, .9)
        self.u32(self.S + 0x28, 0)
        self.u32(self.S + 0x90, 0)
        self.u32(self.T + 0x18, 0)
        self.f32(self.T + 0x10, 1)
        self.u32(0xE60268, self.P)
        self.u32(0xE5FC00, self.BALL)
        self.u32(self.BALL, self.P if carrier else self.P + 0xE000)
        self.u32(0xE5FF80, 0)
        self.u32(0xE601E0, 0)
        self.controller, self.context, self.layout = controller, 10 if carrier else 9, layout
        self.previous_bits = 0
        if controller >= 0:
            self.u32(0xE5FE90 + controller * 0x1C, layout)
            self.uc.mem_write(PAD_BLOCK + controller * 0x2C, bytes(0x2C))
            self.u32(PAD_BLOCK + controller * 0x2C + 12, self.context)
        self.seed_native_speed_cache()
        # Execute the actual installed call instruction, including both
        # native attribute clamps; stop immediately after its x87 return.
        self.run(0x75CC8, ecx=self.R, return_address=0x184, stop=0x75CCD)
        self.rating = self.pop_float()
        self.f32(self.S + 0x1B4, self.rating)
        # Input to the native throttle update: already running straight at
        # the player's ordinary speed, with a full analog stick request.
        self.u32(0xE6029C, self.P + 0xE000)
        self.f32(self.P + 0xE010, 1)
        self.u32(self.P + 0x18, self.P + 0xE100)
        self.f32(self.P + 0xE140, self.normal_speed())

    def frame(self, held=False, *, bits=None, cpu_command=0):
        if self.controller < 0:
            self.u32(self.T + 0x1C, cpu_command)
            self.u32(self.T + 0x18, 4 if held else 0)
        else:
            if bits is None:
                bits = (0x200 if self.layout == 2 else 0x100) if held else 0
            block = PAD_BLOCK + self.controller * 0x2C
            self.u32(block, bits & ~self.previous_bits)
            self.u32(block + 4, self.previous_bits & ~bits)
            self.u32(block + 8, bits)
            self.u32(block + 12, self.context)
            for channel in (8, 9, 10, 11):
                self.f32(ANALOG + self.controller * 0x244 + channel * 8, 0)
            self.u32(self.T + 0x18, 0)
            self.u32(self.T + 0x1C, 0)
            self.run(0x120A20, args=(self.controller, self.T), count=20000)
            self.previous_bits = bits
        decoded = self.read(self.T + 0x1C)
        self.run(0x18EC40, count=20000)
        command = self.read(self.T + 0x1C)
        self.run(0x2D43F0, count=20000)
        return decoded, command, self.number(self.S + 0x44)

    def enter_burst(self):
        command = self.read(self.T + 0x1C)
        if command != 0x16:
            raise AssertionError(f'no native sprint command: {command:#x}')
        descriptor = self.read(0xAD67F0 + 4 * command)
        # State-machine selection is an explicit boundary: use its real
        # command table and run the complete native initializer, including
        # charge consumption. The engine's animation selection is supplied.
        if self.read(descriptor + 4) != 0x30ED50:
            raise AssertionError('foreign sprint descriptor')
        self.run(0x30ED50, count=20000)
        self.u32(self.S + 4, descriptor)
        return self.number(self.S + 0xE0), self.number(self.S + 0xD8)

    def sprint_rate(self):
        """Run the burst's real movement update through its animation-rate
        stores at elapsed 0.1 s. Native throttle, curves and Speed all execute;
        stop before rotation/graphics work. This is not world displacement.
        """
        self.f32(self.S + 8, .1)
        self.f32(self.S + 0x58, 1)
        self.u32(self.S + 0x8C, self.read(self.S + 0x8C) | 0x8000000)
        self.run(0x30EF60, stop=0x30F17A, count=20000)
        return self.number(self.ANIM1 + 8)

    def normal_speed(self):
        self.run(0x238020, args=(0x3F800000,), count=20000)
        return self.pop_float()
