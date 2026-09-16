"""Real tarball-to-tarball transactions, interpreters and headless launchers.

The tiny app fixture isolates the runtime-loss bug without depending on private
release files. reports/b71_u1/reproduce.py additionally runs the shipped pair.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import venv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from mod_editor.core import self_update as U
from mod_editor.core import update_check


def archive(path, version, *, bad_import=False, main=None):
    files = {
        "mod_editor/__init__.py": ("raise ImportError('broken release')\n" if bad_import
                                   else f"__version__ = {version!r}\n").encode(),
        "mod_editor/__main__.py": (main or "if __name__ == '__main__':\n    print('launched')\n").encode(),
        "mod_editor/gui/__init__.py": b"",
        "mod_editor/gui/studio_qt.py": b"",
        "tools/launch_2k5_mod_studio.sh": (REPO / "tools/launch_2k5_mod_studio.sh").read_bytes(),
        "tests/mod_editor/shipped_test.py": b"# the real releases also carry tests\n",
        "private-mode.txt": b"release permissions\n",
    }
    with tarfile.open(path, "w:gz") as tar:
        folder = tarfile.TarInfo(f"studio-{version}/private-dir")
        folder.type = tarfile.DIRTYPE
        folder.mode = 0o750
        tar.addfile(folder)
        for name, payload in files.items():
            member = tarfile.TarInfo(f"studio-{version}/{name}")
            member.size = len(payload)
            member.mode = 0o755 if name.endswith(".sh") else 0o640
            tar.addfile(member, io.BytesIO(payload))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")


@unittest.skipIf(os.name == "nt", "Linux portable runtime and executable-mode regression")
class LinuxUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="studio-update-test-")
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name).resolve()
        old = self.parent / "old.tar.gz"
        archive(old, "70")
        self.root = U.unpack_tarball(old, self.parent)
        renamed = self.parent / "Studio with spaces"
        self.root.rename(renamed)
        self.root = renamed
        self.root.chmod(0o750)
        self.new = self.parent / "2K5-Mod-Studio-v1.0-RC96-test.tar.gz"
        archive(self.new, "71.1")
        self.install = U.detect_install(self.root, executable=sys.executable)
        self.spawned = []

    def update(self, spawn=None):
        files = [self.new, self.new.with_name(self.new.name + ".sha256")]
        document = {"tag_name": "beta-71.1", "assets": [
            {"name": p.name, "browser_download_url": "https://local.invalid/" + p.name,
             "size": p.stat().st_size} for p in files]}
        def opener(url, timeout):
            return next(p for p in files if p.name == url.rsplit("/", 1)[1]).open("rb")
        return U.run_update(document, install=self.install, work=self.parent / "downloads",
                            opener=opener, spawn_tarball=spawn)

    def assert_old(self):
        self.assertIn("'70'", (self.root / "mod_editor/__init__.py").read_text())
        self.assertFalse(list(self.parent.glob(".*.new-*")))
        self.assertFalse(self.root.with_name(self.root.name + ".update-lock").exists())

    def confirmed(self, command, root):
        self.spawned.append((command, root))
        self.assertIn("'71.1'", (root / "mod_editor/__init__.py").read_text())

    def test_tarball_to_tarball_keeps_local_runtime_and_launcher_without_python_on_path(self):
        runtime = self.root / ".venv"
        venv.EnvBuilder(with_pip=False, symlinks=True).create(runtime)
        python = runtime / "bin/python3"
        self.install = U.detect_install(self.root, executable=str(python))
        stale = self.root / "mod_editor/__pycache__/stale.pyc"
        stale.parent.mkdir()
        stale.write_bytes(b"old cache")
        (self.root / "user-project.2k5mod").write_bytes(b"keep my project")
        # Ensure a dependency that only the local runtime has survives.
        site = subprocess.check_output([str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True).strip()
        (Path(site) / "only_in_this_runtime.py").write_text("VALUE = 71\n")
        with patch.object(U, "check_tarball_launch", wraps=U.check_tarball_launch) as check:
            self.update(self.confirmed)
        self.assertEqual(check.call_count, 2)
        self.assertNotEqual(check.call_args_list[0].args[0], self.root)
        self.assertTrue(python.exists())
        self.assertEqual((self.root / ".studio-python").read_text(), ".venv/bin/python3\n")
        self.assertFalse((self.root / "mod_editor/__pycache__").exists())
        self.assertFalse((self.root / "studio-71.1").exists())
        previous = self.root.with_name(self.root.name + ".previous")
        self.assertTrue((previous / ".venv/bin/python3").exists())
        self.assertTrue((previous / "mod_editor/__pycache__/stale.pyc").exists())
        self.assertEqual((previous / "user-project.2k5mod").read_bytes(), b"keep my project")
        self.assertEqual(subprocess.check_output([str(python), "-c", "import only_in_this_runtime; print(only_in_this_runtime.VALUE)"], text=True).strip(), "71")
        utility_bin = self.parent / "utilities"
        utility_bin.mkdir()
        for name in ("bash", "dirname", "readlink", "mkdir", "tail"):
            (utility_bin / name).symlink_to(shutil.which(name))
        env = dict(os.environ, PATH=str(utility_bin), XDG_STATE_HOME=str(self.parent / "state"))
        env.pop("MOD_STUDIO_PYTHON", None)
        launched = subprocess.run([str(self.root / "tools/launch_2k5_mod_studio.sh"), "--update-check"],
                                  cwd=self.parent, env=env, text=True, capture_output=True)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertEqual(launched.stdout.strip(), "71.1")
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o750)
        self.assertEqual((self.root / "private-dir").stat().st_mode & 0o777, 0o750)
        self.assertEqual((self.root / "private-mode.txt").stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.root / "tools/launch_2k5_mod_studio.sh").stat().st_mode & 0o777, 0o755)

    def test_failed_import_never_renames_current_or_calls_relaunch(self):
        archive(self.new, "71.1", bad_import=True)
        before = self.root.stat().st_ino
        with patch.object(U.os, "replace", wraps=os.replace) as replace:
            with self.assertRaisesRegex(U.SelfUpdateError, "broken release"):
                self.update(self.confirmed)
        self.assertEqual(self.root.stat().st_ino, before)
        self.assertFalse(any(Path(call.args[0]) == self.root for call in replace.call_args_list))
        self.assertFalse(self.spawned)
        self.assert_old()

    def test_failed_spawn_restores_original_tree_and_retains_failed_tree(self):
        before = self.root.stat().st_ino
        def fail(command, root):
            raise OSError("relaunch refused")
        with self.assertRaisesRegex(U.SelfUpdateError, "old version was restored") as caught:
            self.update(fail)
        self.assertIn(str(self.root), str(caught.exception))
        self.assertEqual(self.root.stat().st_ino, before)
        self.assertTrue(self.root.with_name(self.root.name + ".failed-update").is_dir())
        self.assert_old()

    def test_real_child_exit_and_silent_exit_both_roll_back(self):
        for status in (0, 7):
            with self.subTest(status=status):
                archive(self.new, "71.1", main=f"if __name__ == '__main__':\n    raise SystemExit({status})\n")
                with self.assertRaisesRegex(U.SelfUpdateError, f"exit {status}"):
                    self.update()
                self.assert_old()

    def test_real_child_timeout_is_stopped_and_rolled_back(self):
        archive(self.new, "71.1", main="if __name__ == '__main__':\n    import time; time.sleep(30)\n")
        with patch.object(U, "STARTUP_TIMEOUT_SECONDS", 0.2):
            with self.assertRaisesRegex(U.SelfUpdateError, "did not confirm"):
                self.update()
        self.assert_old()

    def test_real_child_acknowledgement_completes_transaction(self):
        archive(self.new, "71.1", main="""if __name__ == '__main__':
    import os, pathlib, time
    pathlib.Path(os.environ['MOD_STUDIO_UPDATE_READY']).write_text('ready\\n')
    time.sleep(30)
""")
        processes = []
        popen = subprocess.Popen
        def record(*args, **kwargs):
            child = popen(*args, **kwargs)
            processes.append(child)
            return child
        try:
            with patch.object(U.subprocess, "Popen", record):
                plan = self.update()
            self.assertIn("previous", plan.notes[-1])
            self.assertTrue(any(p.poll() is None for p in processes))
        finally:
            for child in processes:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=5)

    def test_second_rename_failure_restores_old_install(self):
        replace = os.replace
        def fail(source, dest):
            if Path(source).name.startswith(".studio-71.1.new-"):
                raise OSError("rename refused")
            return replace(source, dest)
        with patch.object(U.os, "replace", fail):
            with self.assertRaisesRegex(U.SelfUpdateError, "unchanged"):
                self.update(self.confirmed)
        self.assert_old()

    def test_check_at_final_path_can_roll_back(self):
        check = U.check_tarball_launch
        def fail_final(root, executable, product):
            if root == self.root:
                raise U.SelfUpdateError("runtime does not work at final path")
            return check(root, executable, product)
        with patch.object(U, "check_tarball_launch", fail_final):
            with self.assertRaisesRegex(U.SelfUpdateError, "old version was restored"):
                self.update(self.confirmed)
        self.assertFalse(self.spawned)
        self.assert_old()

    def test_failed_restore_names_the_retained_old_tree(self):
        replace = os.replace
        previous = self.root.with_name(self.root.name + ".previous")
        def fail(source, dest):
            if Path(source).name.startswith(".studio-71.1.new-") or Path(source) == previous:
                raise OSError("filesystem refused rename")
            return replace(source, dest)
        with patch.object(U.os, "replace", fail):
            with self.assertRaisesRegex(U.SelfUpdateError, "old version is safe") as caught:
                self.update(self.confirmed)
        self.assertIn(str(previous), str(caught.exception))
        self.assertTrue((previous / "mod_editor/__main__.py").is_file())
        self.assertFalse(self.spawned)

    def test_incomplete_archive_never_changes_old_install(self):
        self.new.write_bytes(self.new.read_bytes()[:100])
        # A valid sidecar does not make a truncated gzip a valid application.
        digest = hashlib.sha256(self.new.read_bytes()).hexdigest()
        self.new.with_name(self.new.name + ".sha256").write_text(f"{digest}  {self.new.name}\n")
        with self.assertRaises(U.SelfUpdateError):
            self.update(self.confirmed)
        self.assert_old()

    def test_launch_check_runs_while_old_runtime_and_tree_still_exist(self):
        check = U.check_tarball_launch
        def inspect(root, python, product):
            if root != self.root:
                self.assertIn("'70'", (self.root / "mod_editor/__init__.py").read_text())
                self.assertFalse(self.root.with_name(self.root.name + ".previous").exists())
            return check(root, python, product)
        with patch.object(U, "check_tarball_launch", inspect):
            self.update(self.confirmed)

    def test_shipped_tests_directory_does_not_hide_update_button(self):
        self.assertEqual(self.install.kind, "tarball")

    def test_concurrent_update_lock_preserves_original(self):
        lock = self.root.with_name(self.root.name + ".update-lock")
        lock.mkdir()
        with self.assertRaisesRegex(U.SelfUpdateError, "Another update"):
            self.update(self.confirmed)
        lock.rmdir()
        self.assert_old()


class HotfixDiscoveryTests(unittest.TestCase):
    def test_shipped_tag_forms_order_numerically_in_release_list(self):
        releases = [{"tag_name": tag} for tag in ("beta-71", "beta-70", "beta-71.1")]
        with patch.object(update_check, "_read", return_value=releases):
            for current in ("beta-69", "beta-70", "beta-71"):
                result = update_check.check(current)
                self.assertTrue(result.available)
                self.assertEqual(result.latest_tag, "beta-71.1")
            self.assertFalse(update_check.check("beta-71.1").available)
            self.assertFalse(update_check.check("beta-72").available)
        self.assertEqual(update_check._beta_number("beta-71"), (71, 0))
        self.assertEqual(update_check._beta_number("beta-71.1"), (71, 1))
        self.assertIsNone(update_check._beta_number("beta-71.1.1"))


if __name__ == "__main__":
    unittest.main()
