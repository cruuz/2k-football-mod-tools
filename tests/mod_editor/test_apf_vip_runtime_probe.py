"""Pinned owned-image gate for the native VIP attachment research probe."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import json
import os
import tempfile
import unittest

from tools import apf_vip_runtime_probe as probe


class ProbeGuardTests(unittest.TestCase):
    def test_foreign_image_rejected_before_execution(self):
        with self.assertRaisesRegex(ValueError, "exact pinned"):
            probe.attach_prefix(b"foreign", opponent_slot=0,
                                side_zero_human=True, side_one_human=False)

    def test_bounded_image_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.pe"
            path.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "bound"):
                probe.read_image(path)
            path.write_bytes(b"fixture")
            self.assertEqual(probe.read_image(path), b"fixture")


class NativeAttachmentTests(unittest.TestCase):
    def _image(self, name):
        value = os.environ.get("APF_D4_" + name.upper() + "_IMAGE")
        if not value:
            self.skipTest("Set APF_D4_" + name.upper() + "_IMAGE to an owned pinned image")
        return probe.read_image(Path(value))

    def _sweep(self, name):
        data = self._image(name)
        report = probe.sweep(data)
        self.assertEqual(report["profile"], name)
        self.assertEqual(len(report["cases"]), 16)
        self.assertEqual(report["game_files_touched"], [])
        self.assertFalse(report["gameplay_witnessed"])
        for case in report["cases"]:
            with self.subTest(slot=case["opponent_slot"], sides=case["human_side_flags"]):
                pointers = case["side_playback_pointers"]
                self.assertEqual(pointers, case["saved_side_playback_pointers"])
                left, right = case["human_side_flags"]
                slot = case["opponent_slot"]
                if slot is None or left == right:
                    self.assertEqual(pointers, [0, 0])
                else:
                    self.assertEqual(pointers[int(left)], probe.PLAYBACK_BASE + slot * probe.PLAYBACK_STRIDE)
                    self.assertEqual(pointers[int(right)], 0)
        output = os.environ.get("APF_D4_VIP_" + name.upper() + "_RECEIPT")
        if output:
            with Path(output).open("x", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2)
        for slot in (-1, 8, True, "3"):
            with self.assertRaisesRegex(ValueError, "slot"):
                probe.attach_prefix(data, opponent_slot=slot,
                                    side_zero_human=True, side_one_human=False)

    def test_base_native_sweep(self):
        self._sweep("base")

    def test_tu_native_sweep(self):
        self._sweep("tu_1_1")


if __name__ == "__main__":
    unittest.main()
