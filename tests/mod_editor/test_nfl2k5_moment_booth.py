"""Static checks for the Super Bowl booth welcome (b776 sbc): code, hook bytes, mask and the retail cave pin.

No emulator. The code must decode completely, every branch must land on an instruction of the cave or on a declared
retail target, the row mask must be the moment context's Super Bowl mask, and (with the retail executable present)
the cave must still be an unreferenced retail function and the install must replay to nothing.
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mod_editor.core import nfl2k5_moment_booth as b
from mod_editor.core import nfl2k5_moment_context as mc

try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    Cs = None

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) \
    / "ESPN NFL 2K5 (USA)" / "default.xbe"
EXTERNAL = {b.HOOK_BACK, b.ENQUEUE}


def instructions():
    code, labels = b.code_for()
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    body = code[:labels["mask"] - b.CAVE_VA]
    return list(md.disasm(body, b.CAVE_VA)), code, labels


class Code(unittest.TestCase):
    def test_layout_and_mask(self):
        code, labels = b.code_for()
        self.assertEqual(len(code), b.CAVE_SIZE)
        self.assertLessEqual(labels["code_bytes"], b.CAVE_SIZE)
        self.assertEqual(set(code[labels["code_bytes"]:]), {0xCC})
        mask = struct.unpack_from("<Q", code, labels["mask"] - b.CAVE_VA)[0]
        self.assertEqual(mask, mc.super_bowl_mask())
        self.assertEqual([r for r in range(1, 65) if mask >> (r - 1) & 1], list(mc.SUPER_BOWL_ROWS))
        self.assertEqual(len(mc.SUPER_BOWL_ROWS), 17)

    def test_hook_bytes(self):
        self.assertEqual(b.HOOK_RETAIL, bytes.fromhex("a180ffe500"))
        hook = b.hook_bytes()
        self.assertEqual(hook[0], 0xE9)
        self.assertEqual(b.HOOK_VA + 5 + struct.unpack("<i", hook[1:])[0], b.CAVE_VA)

    @unittest.skipIf(Cs is None, "capstone unavailable")
    def test_code_decodes_and_every_branch_lands(self):
        ins, code, labels = instructions()
        ends = sum(i.size for i in ins)
        self.assertEqual(ends, labels["mask"] - b.CAVE_VA, "code must decode completely up to the mask")
        starts = {i.address for i in ins}
        seen_enqueue = seen_key = False
        for i in ins:
            if i.mnemonic.startswith("j") or i.mnemonic == "call":
                target = int(i.op_str, 16)
                self.assertTrue(target in starts or target in EXTERNAL, f"{i.address:#x} {i.mnemonic} {i.op_str}")
                if i.mnemonic == "call":
                    self.assertEqual(target, b.ENQUEUE)
                    seen_enqueue = True
            if i.mnemonic == "push" and i.op_str == hex(b.WELCOME_KEY):
                seen_key = True
            if i.mnemonic == "bt":
                self.assertIn(hex(labels["mask"]), i.op_str)
        self.assertTrue(seen_enqueue and seen_key)
        # the first exit (any mode other than 8) runs nothing but the displaced retail load
        self.assertEqual((ins[0].mnemonic, ins[1].mnemonic, ins[2].mnemonic), ("mov", "cmp", "jne"))
        self.assertEqual(int(ins[2].op_str, 16), b.HOOK_BACK)
        # the welcome is enqueued exactly as the director's say command: push -1, push -1, push key, edx = 0
        pushes = [i.op_str for i in ins if i.mnemonic == "push"]
        self.assertIn(pushes, (["-1", "-1", hex(b.WELCOME_KEY)], ["0xffffffff", "0xffffffff", hex(b.WELCOME_KEY)]))
        self.assertEqual(code[labels["done"] - b.CAVE_VA:][:5], b"\xb8\x08\x00\x00\x00")


@unittest.skipUnless(RETAIL.is_file(), "retail executable not present")
class Retail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()

    def test_retail_status_apply_and_replay(self):
        self.assertEqual(b.status(self.retail), "retail")
        out, receipt = b.apply(self.retail)
        self.assertEqual(b.status(out), "applied")
        self.assertEqual(len(out), len(self.retail))
        again, receipt2 = b.apply(out)
        self.assertEqual(again, out)
        self.assertEqual(receipt2["changed_bytes"], 0)
        self.assertEqual(b.view_edits(out), [("hook", b.HOOK_VA, b.HOOK_RETAIL, b.hook_bytes())])
        self.assertEqual(b.view_edits(self.retail), [])

    def test_cave_is_an_unreferenced_retail_function(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.retail)
        start, end = b.CAVE_VA, b.CAVE_VA + b.CAVE_SIZE
        # a whole function: the previous one returns and pads up to it; nops follow it
        self.assertEqual(image.read(start - 7, 7), bytes.fromhex("c3") + b"\x90" * 6)
        self.assertEqual(image.read(end, 6), b"\x90" * 6)
        for s in image.sections:
            raw = image.data[s.raw:s.raw + min(s.raw_size, s.size)]
            # absolute dwords (all alignments) into the cave
            for i in range(len(raw) - 3):
                if raw[i + 3] == 0 and raw[i + 2] == 0x20 and 0x1D <= raw[i + 1] <= 0x1E:
                    v = struct.unpack_from("<I", raw, i)[0]
                    self.assertFalse(start <= v < end, f"absolute reference at {s.start + i:#x}")
            if not s.executable:
                continue
            for i in range(len(raw) - 5):
                op = raw[i]
                src = s.start + i
                if start <= src < end:
                    continue
                if op in (0xE8, 0xE9):
                    t = src + 5 + struct.unpack_from("<i", raw, i + 1)[0]
                elif op == 0x0F and 0x80 <= raw[i + 1] <= 0x8F:
                    t = src + 6 + struct.unpack_from("<i", raw, i + 2)[0]
                elif 0x70 <= op <= 0x7F or op == 0xEB:
                    t = src + 2 + struct.unpack_from("<b", raw, i + 1)[0]
                else:
                    continue
                self.assertFalse(start <= t < end, f"relative transfer at {src:#x}")


if __name__ == "__main__":
    unittest.main()
