"""b77-g2: which controller input makes which ball-carrier command, from the game's own decoder.

Native replay (Unicorn) of the retail controller decoder 0x120A20 and the analog element mapper 0x6FE60 on the
pinned USA retail executable. It proves the partition the abilities owner relies on: the right stick (four
flicks, the four sweeps and the stick click) produces exactly the owner's STICK_COMMANDS and nothing else does,
for all three controller layouts, and every other mapped command is a button or derived command. It does not
prove how the Xbox pad driver names a physical button; that comes from the XDK analog button order (A, B, X, Y,
Black, White, left trigger, right trigger) and is stated as such. UNWITNESSED in a played game.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_abilities_runtime as patch
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage

try:
    from tests.nfl2k5_input_decode_machine import DecoderMachine, ELEMENTS
except ImportError:      # Unicorn is not installed
    DecoderMachine = None

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", str(ROOT / "extracted"))) / "ESPN NFL 2K5 (USA)/default.xbe"

# Pad bits of the physical inputs (the game's own element table 0x4E95C0 and the XINPUT digital buttons).
BUTTON_BITS = {"A": 0x100, "B": 0x200, "X": 0x400, "Y": 0x800, "Black": 0x1000, "White": 0x2000,
               "Left trigger": 0x4000, "Right trigger": 0x8000, "Left stick click": 0x40, "Right stick click": 0x80,
               "D-pad up": 0x1, "D-pad down": 0x2, "D-pad left": 0x4, "D-pad right": 0x8,
               "Left trigger + White": 0x6000, "Right trigger + Black": 0x9000, "Left + right stick click": 0xC0,
               "Left trigger + Right trigger": 0xC000, "Black + White": 0x3000}
STICK_DIRECTIONS = {"up": ((0.0, 1.0), 0x40000), "down": ((0.0, -1.0), 0x80000),
                    "left": ((-1.0, 0.0), 0x10000), "right": ((1.0, 0.0), 0x20000)}
# Expected right-stick commands. A sweep from one cardinal direction to another is the gesture state 5.
SWEEP = {"up": 0x28, "left": 0x29, "down": 0x2A, "right": 0x2B}
RESTING_FLICK = {"up": 0x24, "left": 0x25, "right": 0x27, "down": 0x2A}   # down is the sector the decoder numbers 5


@unittest.skipUnless(DecoderMachine is not None and RETAIL.is_file(), "Unicorn and the pinned USA retail XBE are required")
class InputMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("USA retail hash mismatch")
        cls.machine = DecoderMachine(cls.retail)
        cls.stick = set(patch.STICK_COMMANDS)
        cls.button = set(patch.BUTTON_COMMANDS)

    def test_analog_elements_map_to_the_pad_bits_the_tables_use(self):
        m = self.machine
        expected = {0: (0, 0x100), 1: (0, 0x200), 2: (0, 0x400), 3: (0, 0x800), 4: (0, 0x1000), 5: (0, 0x2000),
                    6: (0, 0x4000), 7: (0, 0x8000), 8: (0x4100000, 0x8200000), 9: (0x2800000, 0x1400000),
                    10: (0x10000, 0x20000), 11: (0x80000, 0x40000)}
        for element, (negative, positive) in expected.items():
            with self.subTest(element=ELEMENTS[element]):
                self.assertEqual(m.element_bits(element, -1.0), negative)
                self.assertEqual(m.element_bits(element, 1.0), positive)

    def test_column_bits_and_the_four_stick_columns(self):
        bits = self.machine.column_bits()
        self.assertEqual(len(bits), 27)
        self.assertEqual([bits[i] for i in range(9)], [0x100, 0x200, 0x400, 0x800, 0x4000, 0x8000, 0x2000, 0x1000, 0x40])
        self.assertEqual(bits[9], 0x80)
        # columns 17..20 are the right stick up, down, left, right; 23..26 are the same four with the sweep flag
        self.assertEqual(bits[17:21], [0x40000, 0x80000, 0x10000, 0x20000])
        self.assertEqual(bits[23:27], [0x10040000, 0x10080000, 0x10010000, 0x10020000])

    def test_native_decoder_equals_the_static_tables_for_every_layout_and_running_context(self):
        """A single control whose pad bits are exactly one table column's bits: the native decoder must answer with
        that column's command from the same table (cross-checks the run against the data it reads)."""
        m = self.machine
        bits = m.column_bits()
        single = {name: pad for name, pad in BUTTON_BITS.items() if bin(pad).count("1") == 1 and pad in bits}
        self.assertEqual(len(single), 10)       # A B X Y Black White both triggers and both stick clicks
        for layout in range(3):
            m.set_layout(layout)
            for context in (8, 10):
                row = m.table_row(layout, context)
                for name, pad in single.items():
                    with self.subTest(layout=layout, context=context, input=name):
                        command, _state = m.frame(0, context, pad)
                        self.assertEqual(command, row[bits.index(pad)], (name, hex(command)))

    def test_right_stick_inputs_produce_exactly_the_owner_stick_commands(self):
        m = self.machine
        produced = set()
        for layout in range(3):
            m.set_layout(layout)
            for context in (8, 10):
                with self.subTest(layout=layout, context=context):
                    # a flick from rest
                    for direction, (analog, pad) in STICK_DIRECTIONS.items():
                        command, _ = m.frame(0, context, pad, stick=analog)
                        self.assertEqual(command, RESTING_FLICK[direction], direction)
                        produced.add(command)
                    # the stop-short flick when the digital bit is on but the stick tracker sees no sweep (0x26)
                    command, _ = m.frame(0, context, STICK_DIRECTIONS["down"][1], stick=(0.0, -0.1))
                    self.assertEqual(command, 0x26)
                    produced.add(command)
                    # a sweep from every cardinal direction to every other one
                    for first, (analog1, pad1) in STICK_DIRECTIONS.items():
                        for second, (analog2, pad2) in STICK_DIRECTIONS.items():
                            if first == second:
                                continue
                            m.frame(0, context, pad1, stick=analog1)
                            command, state = m.frame(0, context, pad2, stick=analog2, keep_state=True)
                            self.assertEqual((command, state), (SWEEP[second], 5), (first, second))
                            produced.add(command)
                    # the click of the right stick
                    command, _ = m.frame(0, context, BUTTON_BITS["Right stick click"])
                    self.assertEqual(command, 0x1A)
                    produced.add(command)
        self.assertEqual(produced, self.stick)
        self.assertEqual(self.stick, {0x1A, *range(0x24, 0x2C)})

    def test_no_other_input_produces_a_stick_command(self):
        m = self.machine
        for layout in range(3):
            m.set_layout(layout)
            for context in (8, 10):
                for name, pad in BUTTON_BITS.items():
                    if pad & 0x80:      # the right stick click, alone or in a chord, is the hurdle (a stick command)
                        continue
                    command, _ = m.frame(0, context, pad)
                    with self.subTest(layout=layout, context=context, input=name):
                        self.assertNotIn(command, self.stick)

    def test_button_commands_and_their_controls_per_layout(self):
        """Layout 0/1: B spin, Y truck, A sprint; layout 2 swaps A/B and X/Y. Stiff-arms and button jukes sit on
        the triggers and bumpers (which of the two pairs depends on the layout)."""
        m = self.machine
        expected = {
            (0, 10): {"B": 0x1B, "Y": 0x23, "A": 0x16, "White": 0x18, "Black": 0x19, "Left trigger": 0x21, "Right trigger": 0x22},
            (1, 10): {"B": 0x1B, "Y": 0x23, "A": 0x16, "White": 0x21, "Black": 0x22, "Left trigger": 0x18, "Right trigger": 0x19},
            (2, 10): {"A": 0x1B, "X": 0x23, "B": 0x16, "White": 0x21, "Black": 0x22, "Left trigger": 0x18, "Right trigger": 0x19},
            (0, 8): {"B": 0x1B, "Y": 0x23, "White": 0x21, "Black": 0x22},
            (1, 8): {"B": 0x1B, "Y": 0x23, "White": 0x21, "Black": 0x22},
            (2, 8): {"A": 0x1B, "X": 0x23, "White": 0x21, "Black": 0x22},
        }
        for (layout, context), controls in expected.items():
            m.set_layout(layout)
            for name, command in controls.items():
                with self.subTest(layout=layout, context=context, input=name):
                    self.assertEqual(m.frame(0, context, BUTTON_BITS[name])[0], command)
        # every mapped button command that a human can produce is in the owner's button class
        for command in (0x18, 0x19, 0x1B, 0x21, 0x22, 0x23):
            self.assertIn(command, self.button)

    def test_pocket_qb_context_six_uses_the_same_flick_numbers_but_is_outside_the_gated_contexts(self):
        """Context 6 (the quarterback with the ball behind the line) decodes the right stick to the same 0x24..0x27
        and the click to 0x2C. The owner only filters contexts 8 and 10, so the pocket evade is never gated."""
        m = self.machine
        for layout in range(3):
            m.set_layout(layout)
            row = m.table_row(layout, 6)
            self.assertEqual([row[17], row[19], row[18], row[20]], [0x24, 0x25, 0x26, 0x27])
            self.assertEqual(row[9], 0x2C)
            command, _ = m.frame(0, 6, STICK_DIRECTIONS["up"][1], stick=STICK_DIRECTIONS["up"][0])
            self.assertEqual(command, 0x24)
        running = [c for c in range(21) if any(patch_cmd in m.table_row(0, c) for patch_cmd in (0x1B, 0x23))]
        self.assertEqual(running, [8, 10])         # only the two running contexts carry spin and truck at all

    def test_commands_no_human_input_produces_are_button_class(self):
        """0x1C, 0x1D, 0x1E, 0x20, 0x5C and 0x5D are in no controller table. They come from the CPU carrier routine
        (0x1D/0x1E/0x20, plus 0x18/0x19/0x23) and from the game's own command rewrites (0x20 -> 0x21/0x22,
        0x5B -> 0x5C/0x5D); none of those paths can produce a right-stick command."""
        m = self.machine
        cells = set()
        for layout in range(3):
            for context in range(21):
                cells.update(m.table_row(layout, context))
        derived = {0x1C, 0x1D, 0x1E, 0x20, 0x5C, 0x5D}
        self.assertFalse(cells & derived)
        self.assertTrue(derived <= self.button)
        # the rewrite tables the callbacks use (0x18D430 for 0x20, 0x18D450 for 0x18/0x19, 0x18D480 for 0x5B)
        rewrites = [struct.unpack("<i", m.uc.mem_read(0x50A38C + 4 * i, 4))[0] for i in range(6)]
        self.assertEqual(rewrites, [0x21, 0x22, 0x18, 0x19, 0x5C, 0x5D])
        callbacks = {c: m.read(0xAABEF8 + 4 * c) for c in (0x18, 0x19, 0x1A, 0x20, 0x23, 0x24, 0x2B, 0x5B)}
        self.assertEqual(callbacks, {0x18: 0x18D470, 0x19: 0x18D470, 0x1A: 0x18D630, 0x20: 0x18D430, 0x23: 0x18D630,
                                     0x24: 0x18D1D0, 0x2B: 0x18D1D0, 0x5B: 0x18D480})

    def test_cpu_routine_writes_only_button_class_commands(self):
        """The CPU ball-carrier routine (0x2E3380..0x2E3650) stores its move straight into steer+0x1C. Every
        immediate it stores is a button-class command or an unmapped one; it never stores a stick command."""
        try:
            import capstone
            from capstone.x86_const import X86_OP_IMM, X86_OP_MEM
        except ImportError:                                     # pragma: no cover
            self.skipTest("capstone is required to list the stores")
        image = XbeImage(self.retail)
        code = image.read(0x2E3380, 0x2E3650 - 0x2E3380)
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        md.detail = True
        stored = set()
        for ins in md.disasm(code, 0x2E3380):
            if ins.mnemonic == "mov" and len(ins.operands) == 2:
                dest, source = ins.operands
                if dest.type == X86_OP_MEM and dest.size == 4 and dest.mem.disp == 0x1C and source.type == X86_OP_IMM:
                    stored.add(source.imm)
        self.assertTrue({0x23, 0x20, 0x1E, 0x1D, 0x18, 0x19} <= stored, sorted(map(hex, stored)))
        self.assertFalse(stored & self.stick)


if __name__ == "__main__":
    unittest.main()
