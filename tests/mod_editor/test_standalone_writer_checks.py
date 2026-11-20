"""Retail-free command-line checks also exercised by hosted Studio CI."""
from pathlib import Path
import os
import stat
import subprocess
import sys
import tempfile
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


def _system_aliases():
    """Root-owned symlinks directly under / (macOS /var, /tmp and /etc; merged-/usr Linux /bin, /lib and /sbin)."""
    found = []
    if os.name != "posix":
        return found
    for name in ("var", "tmp", "etc", "bin", "lib", "sbin"):
        alias = Path("/") / name
        try:
            info = alias.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(info.st_mode) and info.st_uid == 0 and alias.resolve().is_dir():
            entries = sorted(p.name for p in alias.resolve().iterdir())
            if entries:
                found.append(alias / entries[0])
    return found


class PinnedPathAliasTests(unittest.TestCase):
    """The pinned-input verifiers refuse symlinks a user could plant, not the operating system's own aliases.

    macOS keeps its temporary and working folders under /var and /tmp, which are root-owned symlinks to
    /private/var and /private/tmp, so refusing every symlink component refused every macOS user (and hosted CI).
    """

    def verifiers(self):
        sys.path.insert(0, str(ROOT / "tools"))
        sys.path.insert(0, str(ROOT))
        try:
            import nfl_away_loader_safe_virtual_xiso_verify as away
            import nfl_qcow2_historical_chain_verify as chain
            import nfl_uniform_color_xiso_direct_verify as color
        finally:
            sys.path.remove(str(ROOT / "tools"))
            sys.path.remove(str(ROOT))
        return ((away.require_no_symlink_components, away.VirtualVerifyError),
                (chain._require_no_symlink_components, chain.ChainError),
                (color.require_no_symlink_components, ValueError))

    def test_a_system_alias_parent_is_accepted(self):
        aliases = _system_aliases()
        if not aliases:
            self.skipTest("this system has no root-owned symlink directly under /")
        for check, _error in self.verifiers():
            for path in aliases:
                with self.subTest(check=check.__module__, path=str(path)):
                    check(path)

    def test_the_system_temporary_folder_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "input.bin"
            target.write_bytes(b"x")
            for check, _error in self.verifiers():
                with self.subTest(check=check.__module__):
                    check(target)

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "needs POSIX symlinks")
    def test_a_symlink_a_user_planted_is_still_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            real = Path(folder) / "real"
            real.mkdir()
            (real / "input.bin").write_bytes(b"x")
            (Path(folder) / "alias").symlink_to(real, target_is_directory=True)
            for check, error in self.verifiers():
                with self.subTest(check=check.__module__):
                    with self.assertRaisesRegex(error, "symlink"):
                        check(Path(folder) / "alias" / "input.bin")


if __name__ == "__main__":
    unittest.main()
