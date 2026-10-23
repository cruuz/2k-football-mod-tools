"""QB accuracy writer: exact bytes, replay, refusal and late-owner placement. No game boot, no disc build.

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent); NFL2K5_B776_XBE
optionally names the extracted b776 test-disc default.xbe.
"""
import hashlib
import os
from pathlib import Path
import shutil
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_qb_accuracy as accuracy
from mod_editor.core import nfl2k5_qb_accuracy_code as assembly
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit

B776_SHA256 = "b00027f9196cd9c32be809e092970a317f4f4ccb758360266a556af48ec604c3"


def b776_xbe():
    path = os.environ.get("NFL2K5_B776_XBE")
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("NFL2K5_B776_XBE (the extracted b776 test-disc default.xbe) is not set")
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != B776_SHA256:
        raise unittest.SkipTest("NFL2K5_B776_XBE does not match the b776 evidence pin")
    return payload


class StaticTests(unittest.TestCase):
    def test_template_shape_and_symbols(self):
        self.assertLessEqual(len(assembly.CODE), accuracy.CODE_SIZE)
        self.assertEqual(assembly.LABELS["place"], 0)
        self.assertEqual({r[2] for r in assembly.RELOCATIONS}, {"code", "curve", "rng", "resume", "lead_resume"})
        self.assertEqual(accuracy.SYMBOLS, {"resume": 0x2D9F1F, "curve": 0x1B0AE0, "rng": 0x48B90,
                                            "lead_resume": 0x2DADBB})
        self.assertEqual(accuracy.LEAD[1] + len(accuracy.LEAD[2]), accuracy.SYMBOLS["lead_resume"])   # b777 qb4
        self.assertEqual(accuracy.HOOK[1] + len(accuracy.HOOK[2]), accuracy.SYMBOLS["resume"])
        # the cave's rating curve is monotone: a better passer never misses by more
        start = assembly.LABELS["k_acc_points"]
        points = struct.unpack_from("<12f", assembly.CODE, start)
        xs, ys = points[0::2], points[1::2]
        self.assertEqual(list(xs), sorted(xs))
        self.assertEqual(list(ys), sorted(ys, reverse=True))
        self.assertAlmostEqual(ys[0], 1.0)

    def test_late_owner_last_and_off_outside_the_experimental_preset(self):
        self.assertEqual(space.LATE_OWNERS[-4:], (accuracy.OWNER, "nfl2k5_formation_art_spacing", "nfl2k5_force_out", "nfl2k5_contract_college_guard"))  # b778-cr1 last
        self.assertIs(mod_build.BuildPlan(Path('source.iso'), Path('target.iso')).qb_accuracy, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["qb_accuracy"], name == "softdrink_experimental", name)
        self.assertNotIn("/home/noah", (ROOT / "mod_editor/core/nfl2k5_qb_accuracy.py").read_text(encoding="utf-8"))

    def test_assembler_reproduces_shipped_bytes(self):
        # Apple's assembler lacks GNU --32 and MinGW's emits COFF; the shipped byte template is the
        # runtime input, so those hosts skip the reproduction instead of failing on it.
        from _gnu_elf32_as import gnu_elf32_as
        if not shutil.which("as") or not gnu_elf32_as():
            self.skipTest("GNU as with ELF32 output is required for template reproduction")
        from nfl2k5_cpu_ai_assemble import template
        self.assertEqual((ROOT / "mod_editor/core/nfl2k5_qb_accuracy_code.py").read_text(encoding="utf-8"),
                         template("nfl2k5_qb_accuracy"))


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.receipt = accuracy.apply(cls.retail)

    def test_site_code_and_receipt(self):
        self.assertEqual(accuracy.status(self.retail), "retail")
        self.assertEqual(accuracy.status(self.final), "applied")
        image = XbeImage(self.final)
        code = accuracy.allocation(self.final)["va"]
        self.assertEqual(image.read(code, accuracy.CODE_SIZE), accuracy.code_for(code))
        raw = image.read(0x2D9F18, 7)
        self.assertEqual(raw[0], 0xE9)
        self.assertEqual(0x2D9F18 + 5 + struct.unpack_from("<i", raw, 1)[0], code + assembly.LABELS["place"])
        self.assertEqual(raw[5:], b"\x90\x90")
        self.assertEqual(self.receipt["runtime_witnessed"], False)
        self.assertEqual([e["label"] for e in self.receipt["edits"]], ["miss_store", "quick_lead", "screen_lead"])
        lead = image.read(0x2DAD97, 36)                                       # b777 qb4: quick-throw placement
        self.assertEqual(0x2DAD97 + 5 + struct.unpack_from("<i", lead, 1)[0], code + assembly.LABELS["lead"])
        self.assertEqual((lead[0], lead[5:]), (0xE9, b"\x90" * 31))
        self.assertEqual(image.read(0x226832, 3), bytes.fromhex("83fa20"))   # cmp edx, 0x20: kind 9 takes the lead path
        self.assertEqual(space.status(self.final), "applied")

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = accuracy.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        code = accuracy.allocation(self.final)["va"]
        for label, (va, content) in {"hook": (0x2D9F18, b"\xe9\x00\x00\x00\x00"),
                                     "nops": (0x2D9F1D, b"\xcc"),
                                     "screen operand": (0x226834, b"\x0a"),
                                     "quick lead nops": (0x2DADBA, b"\xcc"),
                                     "lead solver": (0x2DAC90, b"\x90"),
                                     "predictor": (0x226840, b"\x90"),
                                     "code": (code + 3, b"\x90"),
                                     "accuracy routine": (0x2D9E30, b"\x90"),
                                     "interpolator": (0x1B0B00, b"\x90"),
                                     "rng": (0x48BA0, b"\x90"),
                                     "miss curve": (0x50BE28, struct.pack("<f", 1.0))}.items():
            bad = repin_edit(self.final, va, content)
            self.assertEqual(accuracy.status(bad), "foreign", label)
            with self.assertRaises(ValueError):
                accuracy.apply(bad)
        retail_bad = repin_edit(self.retail, 0x2D9F1C, b"\x90")
        self.assertEqual(accuracy.status(retail_bad), "foreign")
        with self.assertRaises(ValueError):
            accuracy.apply(retail_bad)


class B776Tests(unittest.TestCase):
    def test_b776_late_append_keeps_every_allocation(self):
        b776 = b776_xbe()
        final, receipt = accuracy.apply(b776)
        before = {(a["owner"], a["kind"]): a for a in space.layout(b776)["allocations"]}
        after = {(a["owner"], a["kind"]): a for a in space.layout(final)["allocations"]}
        for key, row in before.items():
            if key[0] != space.DIRECTORY_OWNER:
                self.assertEqual(after[key], row, key)
        self.assertEqual(set(after) - set(before), {(accuracy.OWNER, "code")})
        self.assertEqual(accuracy.status(final), "applied")
        self.assertEqual(receipt["file_growth"], 0)
        self.assertEqual(accuracy.apply(final)[0], final)


if __name__ == "__main__":
    unittest.main()
