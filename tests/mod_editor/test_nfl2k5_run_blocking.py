"""Run-blocking writer: exact bytes, replay, refusal and the build plan. No game boot, no disc build.

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent); NFL2K5_B776_XBE
optionally names the extracted b776 test-disc default.xbe.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_run_blocking as rb
from mod_editor.core import nfl2k5_run_blocking_code as assembly
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit
from tests.mod_editor.test_nfl2k5_run_blocking_unicorn import b776_xbe


class TemplateTests(unittest.TestCase):
    def test_template_constants_and_size(self):
        code = rb.code_for(0x14EBFB0)
        self.assertEqual(len(code), rb.CODE_SIZE)
        self.assertLessEqual(assembly.LABELS["code_end"], rb.CODE_SIZE)
        for label, value in (("k_roll", rb.ROLL_ADD), ("k_base", rb.DELAY_BASE), ("k_slope", rb.DELAY_SLOPE),
                             ("k_min", rb.DELAY_MIN), ("k_max", rb.DELAY_MAX), ("k_shed_inv", rb.SHED_DIVISOR)):
            self.assertAlmostEqual(struct.unpack_from("<f", code, assembly.LABELS[label])[0], value, places=6)
        # the template's own floats equal the module constants, so the assembly source documents the shipped values
        # (fx1, review r1-native M3: this used to compare code_for() with itself, which overwrites the floats)
        for label, value in (("k_roll", rb.ROLL_ADD), ("k_base", rb.DELAY_BASE), ("k_slope", rb.DELAY_SLOPE),
                             ("k_min", rb.DELAY_MIN), ("k_max", rb.DELAY_MAX), ("k_shed_inv", rb.SHED_DIVISOR)):
            self.assertAlmostEqual(struct.unpack_from("<f", assembly.CODE, assembly.LABELS[label])[0], value, places=6,
                                   msg=label)
        self.assertLess(rb.ROLL_ADD, 0.25)
        self.assertLess(rb.DELAY_MIN, rb.DELAY_BASE)
        self.assertLess(rb.DELAY_BASE, rb.DELAY_MAX)

    def test_calls_are_relocated(self):
        va = 0x14EBFB0
        code = rb.code_for(va)
        for off, kind, symbol, _value in assembly.RELOCATIONS:
            if kind == 2:
                target = va + off + 4 + struct.unpack_from("<i", code, off)[0]
                self.assertEqual(target, rb.SYMBOLS[symbol])

    def test_sites_shape(self):
        va = 0x14EBFB0
        rows = {name: (at, before, after) for name, at, before, after in rb.sites(va)}
        at, before, after = rows["start_roll"]
        self.assertEqual(after[:2], before[:2])                       # still "fadd dword ptr [...]"
        self.assertEqual(struct.unpack_from("<I", after, 2)[0], va + assembly.LABELS["k_roll"])
        for name, label in (("shed_delay", "delay"), ("shed_on_run", "shed_rand")):
            at, before, after = rows[name]
            self.assertEqual(after[0], 0xE8)
            self.assertEqual(at + 5 + struct.unpack_from("<i", after, 1)[0], va + assembly.LABELS[label])
            self.assertEqual(after[5:], b"\x90" * (len(before) - 5))


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.receipt = rb.apply(cls.retail)

    def test_sites_code_and_receipt(self):
        self.assertEqual(rb.status(self.retail), "retail")
        self.assertEqual(rb.status(self.final), "applied")
        image = XbeImage(self.final)
        code = rb.allocation(self.final)["va"]
        self.assertEqual(image.read(code, rb.CODE_SIZE), rb.code_for(code))
        for _name, at, _before, after in rb.sites(code):
            self.assertEqual(image.read(at, len(after)), after)
        self.assertEqual(image.read(0x230396, 6), bytes.fromhex("d8056c694e00"))   # pass branch keeps 0.25
        self.assertEqual(image.read(0x4E696C, 4), struct.pack("<f", 0.25))
        self.assertEqual(self.receipt["runtime_witnessed"], False)
        self.assertEqual({e["label"] for e in self.receipt["edits"]}, {"start_roll", "shed_delay", "shed_on_run"})
        self.assertEqual(space.status(self.final), "applied")

    def test_only_owned_bytes_change_in_text(self):
        a, b = XbeImage(self.retail), XbeImage(self.final)
        text = next(s for s in a.sections if s.name == ".text")
        x, y = a.read(text.start, text.raw_size), b.read(text.start, text.raw_size)
        changed = [text.start + i for i in range(len(x)) if x[i] != y[i]]
        allowed = set()
        for _name, at, before, _after in rb.sites(rb.allocation(self.final)["va"]):
            allowed.update(range(at, at + len(before)))
        self.assertTrue(changed)
        self.assertLessEqual(set(changed), allowed)

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = rb.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        code = rb.allocation(self.final)["va"]
        for label, (va, content) in {"roll operand": (0x230351, b"\x00"),
                                     "delay hook": (0x23317B, struct.pack("<i", 0)),
                                     "shed hook": (0x2331C6, struct.pack("<i", 0)),
                                     "code": (code + 3, b"\x90"),
                                     "shed decision": (0x2330D6, b"\x90"),
                                     "start roll": (0x230400, b"\x90"),
                                     "random": (0x48B99, b"\x90")}.items():
            bad = repin_edit(self.final, va, content)
            self.assertEqual(rb.status(bad), "foreign", label)
            with self.assertRaises(rb.RunBlockingError):
                rb.apply(bad)
        half = repin_edit(self.retail, 0x23317A, bytes.fromhex("e800000000909090"))
        self.assertEqual(rb.status(half), "foreign")


class B776Tests(unittest.TestCase):
    def test_late_owner_on_the_b776_image(self):
        base = b776_xbe()
        before = {r["owner"]: r["va"] for r in space.layout(base)["allocations"]}
        patched, receipt = rb.apply(base)
        after = {r["owner"]: r["va"] for r in space.layout(patched)["allocations"]}
        self.assertEqual({k: v for k, v in after.items() if k != rb.OWNER}, before)   # nothing else moves
        self.assertEqual(receipt["file_growth"], 0)
        self.assertEqual(rb.status(patched), "applied")
        image = XbeImage(patched)
        va = rb.allocation(patched)["va"]
        section = next(s for s in image.sections if s.start <= va < s.start + s.raw_size)
        self.assertLessEqual(va + rb.CODE_SIZE, section.start + section.raw_size)   # inside an already loaded section
        self.assertIn(rb.OWNER, space.LATE_OWNERS)
        # fx1 (review pr68 nit): qb_accuracy is the last late owner, directly after run blocking
        self.assertEqual(space.LATE_OWNERS[-19:-3], (rb.OWNER, "nfl2k5_qb_accuracy", "nfl2k5_formation_art_spacing", "nfl2k5_force_out", "nfl2k5_practice_injuries", "nfl2k5_ball_carrier_ai", "nfl2k5_star_retention", "nfl2k5_star_career", "nfl2k5_cpu_money_downs_late", "nfl2k5_cpu_money_downs_late_state", "nfl2k5_draft_clock", "nfl2k5_weekly_progression", "nfl2k5_player_progress_screen", "nfl2k5_contract_college_guard", "nfl2k5_sim_cb_tackles", "nfl2k5_clock_led"))  # b778-fo1 last


class PlanTests(unittest.TestCase):
    def test_presets_and_validation(self):
        from mod_editor.core import mod_build
        self.assertFalse(mod_build.PRESETS["softdrink_basic"]["run_blocking"])
        self.assertTrue(mod_build.PRESETS["softdrink_advanced"]["run_blocking"])
        self.assertTrue(mod_build.PRESETS["softdrink_experimental"]["run_blocking"])
        self.assertFalse(mod_build.BuildPlan.__dataclass_fields__["run_blocking"].default)

    def test_feature_key_and_studio_option(self):
        from mod_editor.core import nfl2k5_build_settings as settings
        self.assertIn("run_blocking", settings.FEATURE_KEYS)
        text = (ROOT / "mod_editor/gui/build_panel_qt.py").read_text(encoding="utf-8")
        self.assertIn('("run_blocking", _run_blocking.BUILD_CAPTION, _run_blocking.HELP_TEXT)', text)


if __name__ == "__main__":
    unittest.main()
