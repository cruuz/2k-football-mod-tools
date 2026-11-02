"""Protection-calls writer (b780 p1-slide): exact bytes, replay, refusal, composition and the build plan.

No game boot, no disc build. The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when
absent). Native behaviour (the slide value at the snap, the pass set, the at-line buttons) is in
test_nfl2k5_protection_calls_unicorn.
"""
from pathlib import Path
import hashlib
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_protection_calls as pc
from mod_editor.core import nfl2k5_protection_calls_code as assembly
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit


class TemplateTests(unittest.TestCase):
    def test_template_fits_and_carries_the_slide_values(self):
        code = pc.code_for(0x14F0000, 0x14F8000)
        self.assertEqual(len(code), pc.CODE_SIZE)
        self.assertLessEqual(assembly.LABELS["code_end"], pc.CODE_SIZE)
        k0, k1 = struct.unpack_from("<ff", code, assembly.LABELS["k_slide"])
        self.assertAlmostEqual(k0, 274.32, places=3)          # RIGHT with the offense attacking +z
        self.assertAlmostEqual(k1, -274.32, places=3)
        self.assertEqual(struct.pack("<f", pc.SLIDE_CM), struct.pack("<I", 0x438928F6))   # the retail maximum, bit for bit
        self.assertEqual(code[assembly.LABELS["code_end"]:], b"\xcc" * (pc.CODE_SIZE - assembly.LABELS["code_end"]))

    def test_relocations(self):
        code_va, state_va = 0x14F0000, 0x14F8000
        code = pc.code_for(code_va, state_va)
        symbols = dict(pc.SYMBOLS, code=code_va, state=state_va)
        for off, kind, symbol, value in assembly.RELOCATIONS:
            if kind == 2:
                self.assertEqual(code_va + off + 4 + struct.unpack_from("<i", code, off)[0], symbols[symbol], symbol)
            else:
                self.assertIn(struct.unpack_from("<I", code, off)[0] - symbols[symbol] - value, range(0, 16), symbol)
        self.assertEqual(pc.SYMBOLS, dict(slide_auto=0x23B6E0, select_play=0xFEFA0, case_resume=0x18FE6F,
                                          case_done=0x18FF1C))

    def test_world_slide_sign(self):
        # local +x is the offense's right; the world slide is the attack direction times the local slide
        self.assertEqual(pc.world_slide(pc.CALL_RIGHT, 4572.0), pc.SLIDE_CM)
        self.assertEqual(pc.world_slide(pc.CALL_RIGHT, -4572.0), -pc.SLIDE_CM)
        self.assertEqual(pc.world_slide(pc.CALL_LEFT, 4572.0), -pc.SLIDE_CM)
        self.assertEqual(pc.world_slide(pc.CALL_LEFT, -4572.0), pc.SLIDE_CM)
        with self.assertRaises(ValueError):
            pc.world_slide(pc.CALL_NONE, 4572.0)

    def test_site_shape(self):
        code_va = 0x14F0000
        rows = {name: (va, before, after) for name, va, before, after in pc.sites(code_va)}
        self.assertEqual(set(rows), {"snap_slide", "line_button"})
        va, before, after = rows["snap_slide"]
        self.assertEqual((va, before), (0x23BC4F, bytes.fromhex("e98cfaffff")))           # 0x23BC40's tail jump
        self.assertEqual(after[0], 0xE9)
        self.assertEqual(va + 5 + struct.unpack_from("<i", after, 1)[0], code_va + assembly.LABELS["snap_slide"])
        va, before, after = rows["line_button"]
        self.assertEqual((va, before), (0x18FE65, bytes.fromhex("8d51c98bcee831f1f6ff")))  # case 0x37..0x3B head
        self.assertEqual(after[0], 0xE9)
        self.assertEqual(va + 5 + struct.unpack_from("<i", after, 1)[0], code_va + assembly.LABELS["line_button"])
        self.assertEqual(after[5:], b"\x90" * 5)

    def test_user_text_is_plain(self):
        for text in (pc.BUILD_CAPTION, pc.HELP_TEXT):
            self.assertNotIn("—", text)
            self.assertNotIn("–", text)
            self.assertTrue(text.isascii())
        self.assertLessEqual(len(pc.BUILD_CAPTION), 60)
        self.assertIn("EXPERIMENTAL", pc.HELP_TEXT)


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.receipt = pc.apply(cls.retail)

    def test_sites_code_state_and_receipt(self):
        self.assertEqual(pc.status(self.retail), "retail")
        self.assertEqual(pc.status(self.final), "applied")
        self.assertEqual(pc.read_settings(self.final), {"status": "applied"})
        image = XbeImage(self.final)
        rows = pc.allocations(self.final)
        code_va, state_va = rows["code"]["va"], rows["data"]["va"]
        self.assertEqual(image.read(code_va, pc.CODE_SIZE), pc.code_for(code_va, state_va))
        self.assertEqual(image.read(state_va, pc.DATA_SIZE), bytes(pc.DATA_SIZE))
        for _name, at, _before, after in pc.sites(code_va):
            self.assertEqual(image.read(at, len(after)), after)
        self.assertEqual(self.receipt["runtime_witnessed"], False)
        self.assertEqual({e["label"] for e in self.receipt["edits"]}, {"snap_slide", "line_button"})
        self.assertEqual(self.receipt["code_va"], hex(code_va))
        self.assertEqual(self.receipt["state_va"], hex(state_va))
        self.assertEqual(space.status(self.final), "applied")
        self.assertTrue(image.runtime_writable(state_va, pc.DATA_SIZE))

    def test_only_the_two_sites_change_in_text(self):
        a, b = XbeImage(self.retail), XbeImage(self.final)
        allowed = set()
        for _name, at, before, _after in pc.sites(pc.allocations(self.final)["code"]["va"]):
            allowed.update(range(at, at + len(before)))
        for name in (".text", ".rdata", ".data"):
            section = next(s for s in a.sections if s.name == name)
            x, y = a.read(section.start, section.raw_size), b.read(section.start, section.raw_size)
            changed = {section.start + i for i in range(len(x)) if x[i] != y[i]}
            self.assertLessEqual(changed, allowed, name)
        # the audible panel code, its table fill and menu scan stay retail (b779 au2's pinned spans)
        for va, size in ((0xFEDB0, 0x8F0), (0x189F00, 0x15B), (0xE1960, 0x67), (0xE1320, 0x80)):
            self.assertEqual(b.read(va, size), a.read(va, size), hex(va))

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = pc.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        rows = pc.allocations(self.final)
        code_va, state_va = rows["code"]["va"], rows["data"]["va"]
        for label, (va, content) in {"snap hook": (0x23BC50, struct.pack("<i", 0)),
                                     "button hook": (0x18FE66, struct.pack("<i", 0)),
                                     "code": (code_va + 7, b"\x90"),
                                     "state block": (state_va + 8, b"\x01"),
                                     "slide call body": (0x23BC4A, b"\x90"),
                                     "ret 4 of the automatic read": (0x23BC39, b"\x08"),
                                     "case resume": (0x18FE6F, b"\x90"),
                                     "next controller": (0x18FF1C, b"\x90"),
                                     "switch slot": (0x18FF3C, b"\x90"),
                                     "event index": (0x18FFA0, b"\x04")}.items():
            bad = repin_edit(self.final, va, content)
            self.assertEqual(pc.status(bad), "foreign", label)
            with self.assertRaises(pc.ProtectionCallsError):
                pc.apply(bad)
        half = repin_edit(self.retail, 0x23BC4F, bytes.fromhex("e900000000"))
        self.assertEqual(pc.status(half), "foreign")
        with self.assertRaises(pc.ProtectionCallsError):
            pc.apply(half)

    def test_cli_status_and_apply(self):
        import io
        import json
        import tempfile
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "default.xbe", Path(tmp) / "out.xbe"
            src.write_bytes(self.retail)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(pc.main(["status", str(src)]), 0)
            self.assertEqual(json.loads(buf.getvalue())["status"], "retail")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(pc.main(["apply", str(src), "--output", str(out)]), 0)
            self.assertEqual(hashlib.sha256(out.read_bytes()).hexdigest(), hashlib.sha256(self.final).hexdigest())


class CompositionTests(unittest.TestCase):
    """The owners next to this one in the game's blocking and audible code, in both orders."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()

    def _late_pair(self, other):
        a, _ = pc.apply(self.retail)
        a, _ = other.apply(a)
        b, _ = other.apply(self.retail)
        b, _ = pc.apply(b)
        for payload in (a, b):
            self.assertEqual(pc.status(payload), "applied")
            self.assertEqual(other.status(payload), "applied")
            self.assertEqual(space.status(payload), "applied")
            self.assertEqual(pc.apply(payload)[0], payload)
            self.assertEqual(other.apply(payload)[0], payload)

    def test_pass_protection_both_orders(self):
        from mod_editor.core import nfl2k5_pass_protection as pp
        self._late_pair(pp)

    def test_run_blocking_both_orders(self):
        from mod_editor.core import nfl2k5_run_blocking as rb
        self._late_pair(rb)

    def test_screen_hooks_both_orders_on_one_union(self):
        from mod_editor.core import nfl2k5_screen_hooks as sh
        union, _ = space.apply(self.retail, sh.REQUESTS + pc.REQUESTS, scaleout=True)
        a, _ = pc.apply(union); a, _ = sh.apply(a)
        b, _ = sh.apply(union); b, _ = pc.apply(b)
        self.assertEqual(a, b)
        for owner in (pc, sh):
            self.assertEqual(owner.status(a), "applied")

    def test_dynamic_kickoff_both_orders(self):
        from mod_editor.core import nfl2k5_dynamic_kickoff as dk
        a, _ = dk.apply(self.retail); a, _ = pc.apply(a)
        b, _ = pc.apply(self.retail); b, _ = dk.apply(b)
        for payload in (a, b):
            self.assertEqual(pc.status(payload), "applied")
            self.assertEqual(dk.status(payload), "applied")


class PlanTests(unittest.TestCase):
    def test_presets_and_validation(self):
        from mod_editor.core import mod_build
        self.assertFalse(mod_build.PRESETS["softdrink_basic"]["protection_calls"])
        self.assertFalse(mod_build.PRESETS["softdrink_advanced"]["protection_calls"])
        self.assertTrue(mod_build.PRESETS["softdrink_experimental"]["protection_calls"])
        self.assertFalse(mod_build.BuildPlan.__dataclass_fields__["protection_calls"].default)

    def test_feature_key_studio_option_and_late_owner_options(self):
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_build_settings as settings
        self.assertIn("protection_calls", settings.FEATURE_KEYS)
        text = (ROOT / "mod_editor/gui/build_panel_qt.py").read_text(encoding="utf-8")
        self.assertIn('("protection_calls", _protection_calls.BUILD_CAPTION, _protection_calls.HELP_TEXT)', text)
        self.assertIn(pc.OWNER, [owner for owner, _label, _wanted in mod_build._LATE_OWNER_OPTIONS])

    def test_late_owner_and_space_union(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        owners = list(space.LATE_OWNERS)
        self.assertIn(pc.OWNER, owners)          # appended after every b779 late owner, so it moves none of them
        for earlier in ("nfl2k5_pass_protection", "nfl2k5_pass_rush_stats", "nfl2k5_module_loader", "nfl2k5_sim_realism_state"):
            self.assertLess(owners.index(earlier), owners.index(pc.OWNER), earlier)
        self.assertLessEqual(set(pc.REQUESTS), set(tt._selected_space_requests(protection_calls=True)))
        self.assertNotIn(pc.OWNER, {r[0] for r in tt._selected_space_requests()})


if __name__ == "__main__":
    unittest.main()
