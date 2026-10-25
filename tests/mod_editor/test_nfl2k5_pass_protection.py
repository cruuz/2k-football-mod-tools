"""Pass-protection writer: exact bytes, replay, refusal and the build plan. No game boot, no disc build.

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent).
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_pass_protection as pp
from mod_editor.core import nfl2k5_pass_protection_code as assembly
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit


class TemplateTests(unittest.TestCase):
    def test_template_constants_and_size(self):
        code = pp.code_for(0x14F0000)
        self.assertEqual(len(code), pp.CODE_SIZE)
        self.assertLessEqual(assembly.LABELS["code_end"], pp.CODE_SIZE)
        for label, value in (("k_base", pp.DELAY_BASE), ("k_slope", pp.DELAY_SLOPE),
                             ("k_min", pp.DELAY_MIN), ("k_max", pp.DELAY_MAX)):
            self.assertAlmostEqual(struct.unpack_from("<f", code, assembly.LABELS[label])[0], value, places=6)
            self.assertAlmostEqual(struct.unpack_from("<f", assembly.CODE, assembly.LABELS[label])[0], value, places=6,
                                   msg=label)
        self.assertLess(pp.DELAY_MIN, pp.DELAY_BASE)
        self.assertLess(pp.DELAY_BASE, pp.DELAY_MAX)

    def test_calls_are_relocated(self):
        va = 0x14F0000
        code = pp.code_for(va)
        for off, kind, symbol, _value in assembly.RELOCATIONS:
            if kind == 2:
                target = va + off + 4 + struct.unpack_from("<i", code, off)[0]
                self.assertEqual(target, pp.SYMBOLS[symbol])

    def test_site_shape(self):
        va = 0x14F0000
        name, at, before, after = pp.sites(va)[0]
        self.assertEqual(name, "pass_delay")
        self.assertEqual(at, 0x233162)
        self.assertEqual(before, bytes.fromhex("c744241800000000"))
        self.assertEqual(after[0], 0xE8)
        self.assertEqual(at + 5 + struct.unpack_from("<i", after, 1)[0], va + assembly.LABELS["pass_delay"])
        self.assertEqual(after[5:], b"\x90" * (len(before) - 5))


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.receipt = pp.apply(cls.retail)

    def test_sites_code_and_receipt(self):
        self.assertEqual(pp.status(self.retail), "retail")
        self.assertEqual(pp.status(self.final), "applied")
        image = XbeImage(self.final)
        code = pp.allocation(self.final)["va"]
        self.assertEqual(image.read(code, pp.CODE_SIZE), pp.code_for(code))
        for _name, at, _before, after in pp.sites(code):
            self.assertEqual(image.read(at, len(after)), after)
        # the pass start roll and the run shed constant keep every retail byte
        self.assertEqual(image.read(0x230396, 6), bytes.fromhex("d8056c694e00"))
        self.assertEqual(image.read(0x23317A, 8), bytes.fromhex("c7442418cdcc4c3d"))
        self.assertEqual(image.read(0x4E696C, 4), struct.pack("<f", 0.25))
        self.assertEqual(self.receipt["runtime_witnessed"], False)
        self.assertEqual({e["label"] for e in self.receipt["edits"]}, {"pass_delay"})
        self.assertEqual(space.status(self.final), "applied")

    def test_only_owned_bytes_change_in_text(self):
        a, b = XbeImage(self.retail), XbeImage(self.final)
        text = next(s for s in a.sections if s.name == ".text")
        x, y = a.read(text.start, text.raw_size), b.read(text.start, text.raw_size)
        changed = [text.start + i for i in range(len(x)) if x[i] != y[i]]
        allowed = set()
        for _name, at, before, _after in pp.sites(pp.allocation(self.final)["va"]):
            allowed.update(range(at, at + len(before)))
        self.assertTrue(changed)
        self.assertLessEqual(set(changed), allowed)

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = pp.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        code = pp.allocation(self.final)["va"]
        for label, (va, content) in {"hook": (0x233163, struct.pack("<i", 0)),
                                     "code": (code + 3, b"\x90"),
                                     "shed decision": (0x2330D6, b"\x90"),
                                     "shed entry": (0x233041, b"\x90")}.items():
            bad = repin_edit(self.final, va, content)
            self.assertEqual(pp.status(bad), "foreign", label)
            with self.assertRaises(pp.PassProtectionError):
                pp.apply(bad)
        half = repin_edit(self.retail, 0x233162, bytes.fromhex("e80000000090909000"))
        self.assertEqual(pp.status(half), "foreign")


class PlanTests(unittest.TestCase):
    def test_presets_and_validation(self):
        from mod_editor.core import mod_build
        self.assertFalse(mod_build.PRESETS["softdrink_basic"]["pass_protection"])
        self.assertTrue(mod_build.PRESETS["softdrink_advanced"]["pass_protection"])
        self.assertTrue(mod_build.PRESETS["softdrink_experimental"]["pass_protection"])
        self.assertFalse(mod_build.BuildPlan.__dataclass_fields__["pass_protection"].default)

    def test_feature_key_and_studio_option(self):
        from mod_editor.core import nfl2k5_build_settings as settings
        self.assertIn("pass_protection", settings.FEATURE_KEYS)
        text = (ROOT / "mod_editor/gui/build_panel_qt.py").read_text(encoding="utf-8")
        self.assertIn('("pass_protection", _pass_protection.BUILD_CAPTION, _pass_protection.HELP_TEXT)', text)

    def test_late_owner_sits_before_the_module_loader(self):
        # b778-xs1: the module loader must stay the last late owner. Pass protection follows every other
        # b778 owner (pi1's practice injuries included) and comes immediately before the loader.
        self.assertEqual(space.LATE_OWNERS[-1], "nfl2k5_module_loader")
        self.assertEqual(space.LATE_OWNERS[-2], pp.OWNER)
        owners = list(space.LATE_OWNERS)
        self.assertLess(owners.index("nfl2k5_practice_injuries"), owners.index(pp.OWNER))
        self.assertLess(owners.index("nfl2k5_run_blocking"), owners.index(pp.OWNER))


if __name__ == "__main__":
    unittest.main()
