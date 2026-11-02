"""Quicker deep and rollout throws (nfl2k5_quick_long_release): bytes, refusals, composition and build wiring.

The pinned USA retail default.xbe is read from the private fixtures and every test that needs it skips when it is
absent.  No allocator, cave or code is involved: nine constants in the three throw routines.  The native proof (the
game's own routines in Unicorn) is in test_nfl2k5_quick_long_release_unicorn.py.
"""
import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_quick_long_release as q
from mod_editor.core.nfl2k5_bump_strength import _section_for_offset, _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

RETAIL_ROLLOUT_CAP_BITS = 0x3F99999A     # 1.2f
EXPECTED_SITES = {
    "deep_lob_start_rate": 0x2DA52F, "rollout_rate_cap": 0x2DA539, "restart_rate": 0x2DA666,
    "restart_rate_stored": 0x2DA678, "ease_target_released": 0x2D8652, "ease_target_after_release": 0x2D8668,
    "ease_target_default": 0x2D86EC, "cpu_blend_minus_base": 0x2D86C0, "cpu_blend_plus_base": 0x2D86D6,
}


def retail_bytes():
    from tests.nfl2k5_supersim_draft_fixture import retail_bytes as _retail_bytes
    return _retail_bytes()


def flip(payload, va, mask=0x01):
    out = bytearray(payload)
    out[XbeImage(payload).offset(va, 1)] ^= mask
    return bytes(out)


class BytesTests(unittest.TestCase):
    def test_geometry_numbers_and_text(self):
        self.assertEqual(q.REQUESTS, ())
        self.assertEqual({name: va for name, va, _before, _after in q.SITES}, EXPECTED_SITES)
        self.assertEqual((q.DEEP_LOB_RATE, q.ROLLOUT_RATE_CAP, q.EASE_FLOOR), (2.0, 1.6, 1.5))
        for name, va, before, after in q.SITES:
            self.assertEqual(len(before), len(after), name)
            self.assertNotEqual(before, after, name)
        # no two sites overlap
        spans = sorted((va, va + len(before)) for _n, va, before, _a in q.SITES)
        for (_s0, e0), (s1, _e1) in zip(spans, spans[1:]):
            self.assertLessEqual(e0, s1)
        text = (ROOT / "mod_editor/core/nfl2k5_quick_long_release.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("—", q.HELP_TEXT + q.BUILD_CAPTION + text)
        self.assertTrue(q.BUILD_CAPTION.startswith("Quicker deep and rollout throws"))

    def test_every_site_carries_exactly_the_intended_number(self):
        by_name = {name: (before, after) for name, _va, before, after in q.SITES}
        f = lambda raw: struct.unpack("<f", raw)[0]  # noqa: E731
        # mov eax,imm32 / push imm32 / mov dword [edi+0xE0],imm32 / mov ebx,imm32
        for name, opcode_len, retail, patched in (
                ("deep_lob_start_rate", 1, 1.5, 2.0), ("rollout_rate_cap", 1, f(struct.pack("<I", RETAIL_ROLLOUT_CAP_BITS)), 1.6),
                ("restart_rate", 1, 1.5, 2.0), ("restart_rate_stored", 6, 1.5, 2.0),
                ("ease_target_released", 1, 1.0, 1.5), ("ease_target_after_release", 1, 1.0, 1.5),
                ("ease_target_default", 1, 1.0, 1.5)):
            before, after = by_name[name]
            self.assertAlmostEqual(f(before[opcode_len:]), retail, places=6, msg=name)
            self.assertAlmostEqual(f(after[opcode_len:]), patched, places=6, msg=name)
            self.assertEqual(before[:opcode_len], after[:opcode_len], name)           # the opcode is untouched
        self.assertEqual(by_name["restart_rate_stored"][0][:6], bytes.fromhex("c787e0000000"))
        # the CPU blend: fsub / fadd [abs32] now read the retail 1.5 at 0x4E6D0C instead of the 1.0 at 0x4E419C
        for name, opcode in (("cpu_blend_minus_base", b"\xd8\x25"), ("cpu_blend_plus_base", b"\xd8\x05")):
            before, after = by_name[name]
            self.assertEqual(before, opcode + struct.pack("<I", 0x4E419C), name)
            self.assertEqual(after, opcode + struct.pack("<I", 0x4E6D0C), name)

    def test_apply_replay_scope_and_digest(self):
        retail = retail_bytes()
        self.assertEqual(q.status(retail), "retail")
        self.assertEqual(q.read_settings(retail)["status"], "retail")
        patched, receipt = q.apply(retail)
        self.assertEqual(q.status(patched), "applied")
        self.assertEqual((receipt["code_bytes"], receipt["writable_bytes"], receipt["readonly_bytes"]), (0, 0, 0))
        self.assertEqual(len(patched), len(retail))
        self.assertEqual(len(receipt["edits"]), len(q.SITES))
        image = XbeImage(retail)
        spans = [(image.offset(va, len(before)), len(before)) for _n, va, before, _a in q.SITES]
        sections = _sections(patched)
        digests = set()
        for _offset, _size in spans:
            section = _section_for_offset(sections, _offset)
            digests.update(range(section.header_offset + 36, section.header_offset + 56))
            self.assertEqual(section_digest(patched, section), section.stored_digest)
        changed = [i for i, (a, b) in enumerate(zip(retail, patched)) if a != b]
        for offset in changed:
            self.assertTrue(any(s <= offset < s + n for s, n in spans) or offset in digests, hex(offset))
        self.assertEqual(receipt["changed_bytes"], len(changed))
        again, replay = q.apply(patched)
        self.assertEqual(again, patched)
        self.assertTrue(replay["already_applied"])
        self.assertEqual(replay["changed_bytes"], 0)

    def test_every_site_byte_is_pinned(self):
        retail = retail_bytes()
        patched, _ = q.apply(retail)
        for name, va, before, after in q.SITES:
            for index in range(len(before)):
                with self.subTest(site=name, byte=index, state="retail"):
                    bad = flip(retail, va + index, 0x40)
                    self.assertEqual(q.status(bad), "foreign")
                    with self.assertRaises(q.QuickLongReleaseError):
                        q.apply(bad)
                if before[index] != after[index]:
                    with self.subTest(site=name, byte=index, state="applied"):
                        self.assertEqual(q.status(flip(patched, va + index, 0x40)), "foreign")

    def test_a_half_applied_executable_refuses(self):
        retail = retail_bytes()
        image = XbeImage(retail)
        for name, va, before, after in q.SITES:
            with self.subTest(site=name):
                mixed = bytearray(retail)
                offset = image.offset(va, len(before))
                mixed[offset:offset + len(before)] = after
                self.assertEqual(q.status(bytes(mixed)), "foreign")
                with self.assertRaises(q.QuickLongReleaseError):
                    q.apply(bytes(mixed))

    def test_the_routines_and_constants_around_the_sites_are_pinned(self):
        retail = retail_bytes()
        patched, _ = q.apply(retail)
        site_bytes = {va + i for _n, va, before, _a in q.SITES for i in range(len(before))}
        for va, size, _digest in q.GUARDS:
            probes = {va, va + size - 1, va + size // 2}
            for probe in sorted(probes - site_bytes):
                with self.subTest(guard=hex(va), probe=hex(probe)):
                    self.assertEqual(q.status(flip(retail, probe)), "foreign")
                    self.assertEqual(q.status(flip(patched, probe)), "foreign")

    def test_a_foreign_executable_is_not_patched(self):
        retail = retail_bytes()
        self.assertEqual(q.status(retail[:0x1000]), "foreign")
        self.assertEqual(q.status(b"\x00" * 4096), "foreign")
        with self.assertRaises(q.QuickLongReleaseError):
            q.apply(b"\x00" * 4096)

    def test_released_v08_executable_reads_retail(self):
        path = Path(os.environ.get("NFL2K5_V08_XBE", "/nonexistent"))
        if not path.is_file():
            self.skipTest("the released v0.8 extraction is not in this scratch")
        data = path.read_bytes()
        self.assertEqual(q.status(data), "retail")
        patched, _ = q.apply(data)
        self.assertEqual(q.status(patched), "applied")

    def test_composes_with_the_neighbouring_throw_owners_in_both_orders(self):
        from mod_editor.core import nfl2k5_qb_accuracy as accuracy
        from mod_editor.core import nfl2k5_throw_tuning as tt
        retail = retail_bytes()
        mine, _ = q.apply(retail)
        # qb_accuracy owns the lead solver (0x2DA8E0) and the release (0x2DAF10): next to, not over, these sites
        for first, second in ((q, accuracy), (accuracy, q)):
            with self.subTest(order=f"{first.__name__} -> {second.__name__}"):
                result = second.apply(first.apply(retail)[0])[0]
                self.assertEqual((q.status(result), accuracy.status(result)), ("applied", "applied"))
                self.assertEqual(q.apply(result)[0], result)
                self.assertEqual(accuracy.apply(result)[0], result)
        orders = []
        for first, second in ((q, accuracy), (accuracy, q)):
            orders.append(hashlib.sha256(second.apply(first.apply(retail)[0])[0]).digest())
        self.assertEqual(orders[0], orders[1], "installation order changed the output")
        # the relocated lob-speed table (0x2D898B / 0x2D8992, the function right after the throw tick)
        arc, _ = tt.apply_arc_table(retail)
        both, _ = q.apply(arc)
        both2, _ = tt.apply_arc_table(mine)
        self.assertEqual(both, both2)
        self.assertEqual((q.status(both), tt.arc_table_status(both)), ("applied", "applied"))

    def test_build_options_and_presets(self):
        plan = mod_build.BuildPlan(Path("source.iso"), Path("target.iso"))
        self.assertIs(plan.quick_long_release, False)
        self.assertIs(plan.wants_xbe_patch(), False)
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso"), quick_long_release=True).wants_xbe_patch(), True)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["quick_long_release"], name in ("softdrink_advanced", "softdrink_experimental"), name)
        self.assertIn("quick_long_release", settings.FEATURE_KEYS)
        self.assertIs(settings.defaults()["quick_long_release"], False)
        self.assertIs(settings.build_settings({"quick_long_release": True})["quick_long_release"], True)
        with self.assertRaises(ValueError):
            settings.build_settings({"quick_long_release": "yes"})
        state = settings.from_plan(mod_build.BuildPlan(Path("a.iso"), Path("b.iso"), quick_long_release=True))
        self.assertIs(settings.to_plan(state, Path("a.iso"), Path("b.iso")).quick_long_release, True)
        self.assertIs(mod_build.availability()["quick_long_release"], True)

    def test_build_panel_lists_the_option_with_the_module_text(self):
        try:
            from mod_editor.gui import build_panel_qt as panel
        except ImportError:  # pragma: no cover - PyQt5 is optional for this module's other tests
            self.skipTest("PyQt5 is not installed")
        rows = [row for row in panel.BUILD_OPTIONS if row[0] == "quick_long_release"]
        self.assertEqual(rows, [("quick_long_release", q.BUILD_CAPTION, q.HELP_TEXT)])

    def test_build_writes_the_option_and_off_leaves_the_executable_retail(self):
        import tempfile
        retail = retail_bytes()
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "default.xbe"
            source.write_bytes(retail)
            # catch_slider rides along: a plan whose only executable change is applied by a later in-place step has
            # nothing for the first-pass writer to do (a limit it shares with sim_stats and the late owners)
            base = Path(temp) / "base.xbe"
            mod_build.build(mod_build.BuildPlan(str(source), str(base), catch_slider=True))
            target = Path(temp) / "built.xbe"
            receipt = mod_build.build(mod_build.BuildPlan(str(source), str(target), catch_slider=True,
                                                           quick_long_release=True))
            self.assertEqual(receipt["result"]["quick_long_release"], "applied")
            step = next(row for row in receipt["steps"] if row.get("step") == "quick_long_release")
            self.assertEqual(len(step["edits"]), len(q.SITES))
            self.assertEqual(target.read_bytes(), q.apply(base.read_bytes())[0])
            self.assertEqual(mod_build.inspect(target)["quick_long_release"], "applied")
            self.assertEqual(mod_build.inspect(base)["quick_long_release"], "retail")
            self.assertEqual(q.status(base.read_bytes()), "retail")

    def test_build_refuses_a_bad_value_and_a_foreign_executable_before_any_write(self):
        import tempfile
        from nfl2k5_throw_tuning_test import _build_synthetic_xbe
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "default.xbe"
            source.write_bytes(_build_synthetic_xbe())
            with self.assertRaisesRegex(ValueError, "Quicker deep and rollout throws must be Off or On"):
                mod_build.build(mod_build.BuildPlan(str(source), str(Path(temp) / "a.xbe"), quick_long_release=1))
            with self.assertRaisesRegex(ValueError, "throw routines in this source are not retail"):
                mod_build.build(mod_build.BuildPlan(str(source), str(Path(temp) / "b.xbe"), quick_long_release=True))
            self.assertFalse((Path(temp) / "a.xbe").exists())
            self.assertFalse((Path(temp) / "b.xbe").exists())


if __name__ == "__main__":
    unittest.main()
