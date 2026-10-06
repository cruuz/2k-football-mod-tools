"""Prevent a helmet/shoulder family swap from corrupting visual evidence."""
import importlib.util
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[2] / "tools/b765/u1_audit.py"
SPEC = importlib.util.spec_from_file_location("u1_audit_test", PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class NativeDigitLabels(unittest.TestCase):
    def test_jersey_ascii_names(self):
        for n in range(10):
            self.assertEqual(audit.digit_filename(13 + n, str(48 + n)), f"digit_jersey_{n}.png")

    def test_helmet_hn_names(self):
        for n in range(10):
            self.assertEqual(audit.digit_filename(23 + n, f"hn{48 + n}"), f"digit_helmet_{n}.png")

    def test_shoulder_an_names(self):
        for n in range(10):
            self.assertEqual(audit.digit_filename(33 + n, f"an{48 + n}"), f"digit_arm_{n}.png")

    def test_family_swap_refused(self):
        for chunk, name in ((23, "an48"), (33, "hn48"), (12, "48"), (43, "an48")):
            with self.assertRaises(ValueError):
                audit.digit_filename(chunk, name)


if __name__ == "__main__":
    unittest.main()
