"""Bounded native-instruction fixture for the retail controller decoder (``0x120A20``) and its helpers.

b77-g2: used to prove which controller input produces which ball-carrier command, with the game's own code and
tables. Only peripheral notifications (menu feedback, the layout selector) are stubbed; the table walk, the stick
sector tracker (``0x1205C0``), the column search and the analog element mapper (``0x6FE60``) are the retail bytes.
No disc, no game loop, no graphics. UNWITNESSED in a played game.
"""
from __future__ import annotations

import struct

import unicorn as uc
from unicorn import x86_const as x86

from mod_editor.core.nfl2k5_cave_oracle import XbeImage

DECODER = 0x120A20            # (controller, steer) stdcall: writes the command to steer+0x1C
ELEMENT_MAPPER = 0x6FE60      # ECX=analog element, stack=value: the digital bit(s) for that element and sign
PAD_BLOCK = 0xA9B954          # per-controller input state, stride 0x2C: +0 pressed, +4 released, +8 held, +0xC context
COLUMN_BITS = 0x4FAAC0        # 27 dwords: the pad bits of each table column
TABLES = 0xA99EC0             # 3 layouts x 21 contexts x 27 command dwords (0x6C bytes per row)
ANALOG = 0xB37B00             # analog channel floats: controller*0x244 + channel*8

# Analog elements in the game's own element table (0x4E95C0), in the Xbox XDK analog button order.
ELEMENTS = {0: "A", 1: "B", 2: "X", 3: "Y", 4: "Black", 5: "White", 6: "Left trigger", 7: "Right trigger",
            8: "Left stick X", 9: "Left stick Y", 10: "Right stick X", 11: "Right stick Y"}


class DecoderMachine:
    STACK, STOP, STEER = 0x3108000, 0x3200000, 0x3004000

    def __init__(self, payload: bytes, layout: int = 0):
        self.uc = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        self.image = XbeImage(payload)
        end = max(s.end for s in self.image.sections)
        self.uc.mem_map(0x10000, ((end + 4095) & -4096) - 0x10000)
        self.uc.mem_write(0x10000, payload[:self.image.headers_size])
        for section in self.image.sections:
            self.uc.mem_write(section.start, payload[section.raw:section.raw + section.raw_size])
        for start, size in ((0x3000000, 0x10000), (0x3100000, 0x10000), (self.STOP, 0x1000)):
            self.uc.mem_map(start, size)
        # Menu / feedback notifications the decoder raises on some buttons: return at once.
        for va in (0x18E310, 0x87590, 0x87540, 0x873F0, 0x87470, 0x872A0, 0x87340, 0x156840, 0x156810, 0x7A6D0):
            self.uc.mem_write(va, b"\xc3")
        for va in (0x627C0, 0x771F0, 0x120580):
            self.uc.mem_write(va, b"\x31\xc0\xc3")                      # xor eax,eax ; ret
        self.set_layout(layout)
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        self.uc.reg_write(x86.UC_X86_REG_FPTAG, 0xFFFF)

    # -- memory helpers
    def u32(self, va: int, value: int) -> None:
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def f32(self, va: int, value: float) -> None:
        self.uc.mem_write(va, struct.pack("<f", value))

    def read(self, va: int) -> int:
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def set_layout(self, layout: int) -> None:
        """The layout selector (0x77230) is a setting lookup; the fixture answers with the layout under test."""
        self.layout = layout
        self.uc.mem_write(0x77230, b"\xb8" + struct.pack("<I", layout) + b"\xc3")
        self.uc.ctl_flush_tb()       # the stub may already have been translated; never run a stale block

    # -- the retail tables, read straight from the image
    def column_bits(self) -> list[int]:
        return [self.read(COLUMN_BITS + 4 * i) for i in range(27)]

    def table_row(self, layout: int, context: int) -> list[int]:
        base = TABLES + (layout * 21 + context) * 0x6C
        return [struct.unpack("<i", self.uc.mem_read(base + 4 * c, 4))[0] for c in range(27)]

    # -- native runs
    def element_bits(self, element: int, value: float) -> int:
        """Run the game's own element mapper 0x6FE60 (the analog axis or button -> digital bit)."""
        self.u32(self.STACK, self.STOP)
        self.f32(self.STACK + 4, value)
        self.uc.reg_write(x86.UC_X86_REG_ESP, self.STACK)
        self.uc.reg_write(x86.UC_X86_REG_ECX, element)
        self.uc.reg_write(x86.UC_X86_REG_FPTAG, 0xFFFF)
        self.uc.emu_start(ELEMENT_MAPPER, self.STOP, count=500)
        return self.uc.reg_read(x86.UC_X86_REG_EAX)

    def frame(self, controller: int, context: int, bits: int, *, stick=(0.0, 0.0), keep_state: bool = False):
        """One decoder pass with ``bits`` newly pressed and held. Returns (command, stick sector state).

        ``keep_state`` carries the stick sector from the previous frame, which is how a sweep from one cardinal
        direction to another becomes the gesture state 5 (commands 0x28..0x2B)."""
        block = PAD_BLOCK + 0x2C * controller
        self.u32(block + 0x00, bits)
        self.u32(block + 0x04, 0)
        self.u32(block + 0x08, bits)
        self.u32(block + 0x0C, context)
        if not keep_state:
            self.u32(block + 0x10, 0)
            self.u32(block + 0x28, 0)
        for channel, value in ((8, 0.0), (9, 0.0), (10, stick[0]), (11, stick[1])):
            self.f32(controller * 0x244 + channel * 8 + ANALOG, value)
        self.u32(self.STEER, controller)
        for offset in (0x10, 0x18, 0x1C):
            self.u32(self.STEER + offset, 0)
        self.u32(self.STACK, self.STOP)
        self.u32(self.STACK + 4, controller)
        self.u32(self.STACK + 8, self.STEER)
        self.uc.reg_write(x86.UC_X86_REG_ESP, self.STACK)
        self.uc.reg_write(x86.UC_X86_REG_FPTAG, 0xFFFF)
        self.uc.emu_start(DECODER, self.STOP, count=20000)
        return self.read(self.STEER + 0x1C), self.read(block + 0x28)
