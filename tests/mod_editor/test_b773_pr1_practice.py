"""N12: retire the fifth practice type without disturbing the retail choices."""
from pathlib import Path
import contextlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_seven_on_seven as seven
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from tests.mod_editor import test_nfl2k5_seven_on_seven as original
from tools.b77 import pr1_repair as repair


class RemovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = original._seed(original._build_synthetic_xbe())
        cls.installed = seven.apply(cls.retail)[0]

    def test_round_trip_restores_every_original_byte_and_replay_is_empty(self):
        removed, receipt = seven.remove(self.installed)
        self.assertEqual(removed, self.retail)
        self.assertEqual(len(receipt["edits"]), 8)
        self.assertEqual(seven.remove(removed)[1]["changed_bytes"], 0)

    def test_unknown_and_partial_install_refused_even_with_valid_digest(self):
        for label, offset, before, after in seven._located(self.installed):
            for value in (before, bytes([after[0] ^ 1]) + after[1:]):
                with self.subTest(site=label):
                    bad = bytearray(self.installed)
                    bad[offset:offset + len(value)] = value
                    for section in _sections(bad):
                        at = section.header_offset + 36
                        bad[at:at + 20] = section_digest(bad, section)
                    with self.assertRaises(seven.SevenOnSevenError):
                        seven.remove(bytes(bad))

    def test_unrelated_valid_changes_survive(self):
        buf = bytearray(self.installed)
        section = _sections(buf)[0]
        at = section.raw_offset + 0x100
        buf[at] ^= 1
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
        after, receipt = seven.remove(bytes(buf))
        self.assertEqual(after[at], buf[at])
        repair.spans(bytes(buf), after, receipt)

    def test_studio_base_build_ignores_old_opt_in_and_removes_installed_patch(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "source.xbe", Path(folder) / "out.xbe"
            source.write_bytes(self.installed)
            plan = mod_build.BuildPlan(str(source), str(target), seven_on_seven=True)
            receipt = mod_build.build(plan)
            self.assertEqual(target.read_bytes(), self.retail)
            self.assertEqual(source.read_bytes(), self.installed)
            self.assertTrue(receipt["seven_on_seven_opt_in_ignored"])
            self.assertFalse(receipt["plan"]["seven_on_seven"])
            self.assertTrue(plan.seven_on_seven)  # caller's settings are not mutated

    def test_studio_removes_patch_with_option_already_off(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "source.xbe", Path(folder) / "out.xbe"
            source.write_bytes(self.installed)
            mod_build.build(mod_build.BuildPlan(str(source), str(target)))
            self.assertEqual(target.read_bytes(), self.retail)

    def test_studio_retail_base_plan_does_not_change_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "source.xbe", Path(folder) / "out.xbe"
            source.write_bytes(self.retail)
            mod_build.build(mod_build.BuildPlan(str(source), str(target), seven_on_seven=True))
            self.assertEqual(target.read_bytes(), self.retail)

    def test_release_gate_and_presets(self):
        self.assertFalse(mod_build.SEVEN_ON_SEVEN_RELEASED)
        self.assertFalse(mod_build.availability()["seven_on_seven"])
        for name, preset in mod_build.PRESETS.items():
            self.assertFalse(preset.get("seven_on_seven", False), name)

    def test_transport_writes_replays_and_refuses_unknown_spans(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.bin"
            path.write_bytes(b"abcdefgh")
            fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                rows = [(2, b"cd", b"XY", "test")]
                self.assertEqual(repair.write_spans(fd, rows), dict(writes=1, written_bytes=2))
                self.assertEqual(repair.write_spans(fd, rows), dict(writes=0, written_bytes=0))
                with self.assertRaises(ValueError):
                    repair.write_spans(fd, [(2, b"!!", b"??", "unknown")])
            finally:
                os.close(fd)
            self.assertEqual(path.read_bytes(), b"abXYefgh")

    def test_complete_disc_transport_hash_guard_scope_and_replay(self):
        # Small synthetic carrier, not a copied game disc. Only the extent
        # lookup, menu text (not present here), and fixture identities differ.
        prefix = b"synthetic header" * 16
        before, after = prefix + self.installed, prefix + self.retail
        with tempfile.TemporaryDirectory() as folder:
            path, receipt = Path(folder) / "carrier.bin", Path(folder) / "receipt.json"
            path.write_bytes(before)
            with mock.patch.object(repair, "BASE_SHA256", repair.sha(before)), \
                 mock.patch.object(repair, "OUTPUT_SHA256", repair.sha(after)), \
                 mock.patch.object(repair.tt, "image_xbe_extent", return_value=(len(prefix), len(self.installed))), \
                 mock.patch.object(repair.mod_build, "_xbe_bytes", side_effect=lambda p: p.read_bytes()[len(prefix):]), \
                 mock.patch.object(repair, "menu", return_value={"fixture": "synthetic"}), \
                 contextlib.redirect_stdout(io.StringIO()):
                repair.apply(path, receipt)
                self.assertEqual(path.read_bytes(), after)
                result = json.loads(receipt.read_text())
                self.assertEqual(result["scope"]["bytes_compared"], len(before))
                self.assertEqual(result["replay"]["written_bytes"], 0)
                self.assertEqual(result["scope"]["outside_span_changes"], 0)
                repair.apply(path, receipt)
                self.assertEqual(json.loads(receipt.read_text())["write"]["written_bytes"], 0)
                # Unknown hash, despite entirely recognized seven-on-seven spans.
                unknown = b"?" + before[1:]
                path.write_bytes(unknown)
                with self.assertRaisesRegex(ValueError, "unknown input disc hash"):
                    repair.apply(path, receipt)
                self.assertEqual(path.read_bytes(), unknown)


@unittest.skipUnless(original.HAVE_UNICORN and os.environ.get("NFL2K5_PR1_BASE"),
                     "set NFL2K5_PR1_BASE for native checks on the feedback disc")
class NativePracticeTests(unittest.TestCase):
    _load = original.RetailTests._load
    _run = original.RetailTests._run
    _u32 = staticmethod(original.RetailTests._u32)
    STACK, SENTINEL = original.RetailTests.STACK, original.RetailTests.SENTINEL

    @classmethod
    def setUpClass(cls):
        cls.before = mod_build._xbe_bytes(Path(os.environ["NFL2K5_PR1_BASE"]))
        cls.after = seven.remove(cls.before)[0]

    def test_native_menu_wraps_only_four_choices_both_directions(self):
        from unicorn.x86_const import UC_X86_REG_EIP
        uc = self._load(self.after)
        for callback, sequence in ((0x148860, (1, 2, 3, 0) * 3), (0x148890, (3, 2, 1, 0) * 3)):
            uc.mem_write(seven.PRACTICE_TYPE_VA, struct.pack("<I", 0))
            for expected in sequence:
                self._run(uc, callback)
                self.assertEqual(uc.reg_read(UC_X86_REG_EIP), self.SENTINEL)
                self.assertEqual(self._u32(uc, seven.PRACTICE_TYPE_VA), expected)

    def test_four_remaining_modes_and_kick_word_match_installed_disc(self):
        from unicorn.x86_const import UC_X86_REG_EIP
        for value, expected in enumerate(((0, 4), (1, 4), (2, 4), (1, 2))):
            for payload in (self.before, self.after):
                uc = self._load(payload)
                uc.mem_write(seven.PRACTICE_TYPE_VA, struct.pack("<I", value))
                self._run(uc, seven.SWITCH_SITE_VA - 15)
                self.assertEqual(uc.reg_read(UC_X86_REG_EIP), self.SENTINEL)
                self.assertEqual((self._u32(uc, seven.MODE_VA), self._u32(uc, seven.KICK_WORD_VA)), expected)

    def test_basic_training_and_normal_book_loader_ignore_stale_flag(self):
        for mode in range(5):
            for flag in (0, 1):
                uc = self._load(self.after)
                uc.mem_write(seven.MODE_VA, struct.pack("<I", mode))
                uc.mem_write(seven.FLAG_VA, bytes([flag]))
                hit = self._run(uc, seven.LOADER_SITE_VA,
                                stop_at=(seven.LOADER_PRACTICE_VA, seven.LOADER_TEAMS_VA))
                self.assertEqual(hit, [seven.LOADER_PRACTICE_VA if mode == 3 else seven.LOADER_TEAMS_VA])


if __name__ == "__main__":
    unittest.main(verbosity=2)
