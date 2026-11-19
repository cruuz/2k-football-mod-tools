"""Retail-free command-line checks also exercised by hosted Studio CI."""
from pathlib import Path
import os
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
POSITIONAL_IO = hasattr(os, "pread") and hasattr(os, "pwrite")


class StandaloneWriterChecks(unittest.TestCase):
    def check_script(self, filename, marker):
        result = subprocess.run([sys.executable, str(ROOT / "tests" / filename)], cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(marker, result.stdout)

    def test_guest_instruction_counter(self):
        self.check_script("apf_instruction_budget_instrumenter_test.py", "APF_INSTRUCTION_BUDGET_INSTRUMENTER_TEST_PASS")

    @unittest.skipUnless(POSITIONAL_IO, "Native archive writer requires positioned file I/O")
    def test_apf_output_paths(self):
        self.check_script("apf_writer_path_safety_test.py", "APF_WRITER_PATH_SAFETY_PASS")

    @unittest.skipUnless(POSITIONAL_IO, "Native archive writer requires positioned file I/O")
    def test_uniform_color_overlay(self):
        self.check_script("nfl_uniform_color_patch_test.py", "NFL_UNIFORM_COLOR_PATCH_TEST_PASS")

    @unittest.skipUnless(POSITIONAL_IO, "Virtual disc verifier requires positioned file I/O")
    def test_virtual_away_disc(self):
        self.check_script("test_nfl_away_loader_safe_virtual_xiso_verify.py", "NFL_AWAY_LOADER_SAFE_VIRTUAL_XISO_TEST_PASS")

    def test_shadow_screenshot_checker(self):
        self.check_script("apf_player_shadow_screenshot_test.py", "\nOK\n")


if __name__ == "__main__":
    unittest.main()
