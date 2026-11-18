"""Exercise both Finder entry points with real processes, environments, pip installs and CLI arguments."""
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import venv
import zipfile


ROOT = Path(__file__).resolve().parents[2]
PRODUCTS = {"2K5-Mod-Studio": ("2k5", "mod_editor"), "APF-2K8-Mod-Studio": ("apf2k8", "mod_editor.apf_studio")}


@unittest.skipIf(os.name == "nt", "Finder uses POSIX executables")
class FinderLaunch(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="Finder – ")
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name).resolve()
        self.app = self.temp / "Studio with spaces"
        packaging = self.app / "packaging"
        packaging.mkdir(parents=True)
        (self.app / "tools").mkdir()
        for name in ("macos_studio.sh", "posix_studio_setup.py"):
            shutil.copy2(ROOT / "packaging" / name, packaging / name)
        self.finder = self.temp / "Desktop"
        self.finder.mkdir()
        for name, (tool, module) in PRODUCTS.items():
            command = name + ".command"
            shutil.copy2(ROOT / command, self.app / command)
            (self.finder / command).symlink_to(Path("..") / self.app.name / command)
            (self.finder / ("Alias " + command)).symlink_to(command)
            launcher = f"launch_{tool}_mod_studio.sh"
            shutil.copy2(ROOT / "tools" / launcher, self.app / "tools" / launcher)
            package = self.app.joinpath(*module.split("."))
            package.mkdir(parents=True, exist_ok=True)
            (package / "__init__.py").write_text('__version__ = "receipt-version"')
            (package / "__main__.py").write_text(
                'import json, os, sys\nfrom pathlib import Path\nif __name__ == "__main__":\n'
                '    Path(os.environ["LAUNCH_RECEIPT"]).write_text(json.dumps([sys.prefix, __package__, *sys.argv[1:]]))\n')
            gui = package / "gui"
            gui.mkdir()
            (gui / "__init__.py").touch()
            (gui / "studio_qt.py").touch()
        self.wheel = self.temp / "studio_fixture-1.0-py3-none-any.whl"
        with zipfile.ZipFile(self.wheel, "w") as bundle:
            for name in ("PyQt5", "PIL", "numpy", "capstone", "unicorn"):
                bundle.writestr(name + "/__init__.py", "")
            bundle.writestr("PyQt5/QtWidgets.py", "")
            prefix = "studio_fixture-1.0.dist-info/"
            bundle.writestr(prefix + "METADATA", "Metadata-Version: 2.1\nName: studio_fixture\nVersion: 1.0\n")
            bundle.writestr(prefix + "WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
            bundle.writestr(prefix + "RECORD", "")
        self.requirements = packaging / "requirements-studio.txt"
        self.requirements.write_text(self.wheel.as_uri() + "\n")
        self.env = dict(os.environ, HOME=str(self.temp), XDG_STATE_HOME=str(self.temp / "state"),
                        PYTHONNOUSERSITE="1", PIP_NO_INDEX="1", MOD_STUDIO_NO_UPDATE_CHECK="1")
        self.env.pop("MOD_STUDIO_PYTHON", None)
        self.env.pop("DISPLAY", None)
        self.env.pop("WAYLAND_DISPLAY", None)

    def launch(self, name, *args, env=None, timeout=180):
        return subprocess.run([str(self.finder / ("Alias " + name + ".command")), *args],
                              cwd=self.temp, env=env or self.env, capture_output=True, text=True, timeout=timeout)

    def bare_runtime(self, path):
        venv.EnvBuilder(with_pip=False, symlinks=True).create(path)
        return path / "bin" / "python3"

    def ready_runtime(self, path):
        python = self.bare_runtime(path)
        site = subprocess.check_output([str(python), "-I", "-c", 'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True).strip()
        with zipfile.ZipFile(self.wheel) as bundle:
            bundle.extractall(site)
        return python

    def test_first_open_installs_only_into_private_runtime_and_concurrent_clicks_reuse_it(self):
        base = self.bare_runtime(self.temp / "base")
        jobs = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for name, (_, module) in PRODUCTS.items():
                receipt = self.temp / name
                env = dict(self.env, MOD_STUDIO_PYTHON=str(base), LAUNCH_RECEIPT=str(receipt))
                jobs.append((pool.submit(self.launch, name, env=env), receipt, module))
        for job, receipt, module in jobs:
            done = job.result()
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(json.loads(receipt.read_text())[:2], [str(self.app / ".venv"), module])
        self.assertNotEqual(subprocess.run([str(base), "-I", "-c", "import capstone"], capture_output=True).returncode, 0)
        for name in PRODUCTS:
            with self.subTest(name=name):
                done = self.launch(name, "--update-check")
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertIn("receipt-version", done.stdout)

    def test_configured_and_recorded_runtimes_take_precedence_and_cli_arguments_survive(self):
        explicit = self.ready_runtime(self.temp / "my Python")
        saved = self.ready_runtime(self.app / "saved runtime")
        self.ready_runtime(self.app / ".venv")
        marker = self.app / ".studio-python"
        marker.write_text("saved runtime/bin/python3\n")
        for name, (_, module) in PRODUCTS.items():
            receipt = self.temp / name
            for env, prefix in ((dict(self.env, MOD_STUDIO_PYTHON=str(explicit)), explicit.parent.parent),
                                (self.env, saved.parent.parent)):
                with self.subTest(name=name, prefix=prefix):
                    done = self.launch(name, "--project", "München 雪", "--dry-run", env=dict(env, LAUNCH_RECEIPT=str(receipt)))
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    self.assertEqual(json.loads(receipt.read_text()), [str(prefix), module, "--project", "München 雪", "--dry-run"])
        marker.write_text(str(saved) + "\n")
        self.assertEqual(self.launch("2K5-Mod-Studio", "--update-check").returncode, 0)
        marker.write_text("missing runtime/bin/python3\n")
        failed = self.launch("APF-2K8-Mod-Studio", "--update-check")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("selected Python", failed.stderr)

    def test_failed_setup_can_be_retried_and_setup_only_does_not_launch(self):
        base = self.bare_runtime(self.temp / "base")
        self.requirements.write_text((self.temp / "missing.whl").as_uri() + "\n")
        receipt = self.temp / "unexpected launch"
        env = dict(self.env, MOD_STUDIO_PYTHON=str(base), LAUNCH_RECEIPT=str(receipt))
        failed = self.launch("APF-2K8-Mod-Studio", "--setup", env=env)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("retry", failed.stderr)
        self.requirements.write_text(self.wheel.as_uri() + "\n")
        success = self.launch("APF-2K8-Mod-Studio", "--setup", env=env)
        self.assertEqual(success.returncode, 0, success.stdout + success.stderr)
        self.assertFalse(receipt.exists())
        self.assertTrue((self.app / ".venv" / "pyvenv.cfg").is_file())

    def test_finder_discovers_a_supported_version_when_default_python_is_too_old(self):
        python = self.ready_runtime(self.temp / "installed Python")
        bins = self.temp / "search path"
        bins.mkdir()
        unsupported = bins / "python3"
        unsupported.write_text("#!/bin/sh\nexit 1\n")
        unsupported.chmod(0o755)
        named = bins / "python3.13"
        named.write_text('#!/bin/sh\nexec "$FINDER_TEST_PYTHON" "$@"\n')
        named.chmod(0o755)
        env = dict(self.env, PATH=str(bins) + os.pathsep + os.environ["PATH"], FINDER_TEST_PYTHON=str(python))
        for name, (_, module) in PRODUCTS.items():
            receipt = self.temp / name
            done = self.launch(name, "--project", "one file", env=dict(env, LAUNCH_RECEIPT=str(receipt)))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(json.loads(receipt.read_text()), [str(python.parent.parent), module, "--project", "one file"])
        self.assertFalse((self.app / ".venv").exists())

    @unittest.skipUnless(sys.platform == "darwin" and os.environ.get("GITHUB_ACTIONS") == "true", "real hosted macOS runtime")
    def test_hosted_mac_installs_real_pinned_packages_and_imports_both_studio_guis(self):
        # Ship-ready inputs are hydrated on each macOS 3.11/3.12/3.13 job.
        for name, manifest in (("2K5-Mod-Studio", "release-allowlist.txt"),
                               ("APF-2K8-Mod-Studio", "apf2k8-release-allowlist.txt")):
            with self.subTest(name=name):
                app = self.temp / (name + " – released files")
                stage = subprocess.run([sys.executable, str(ROOT / "packaging/stage_release.py"),
                                        str(ROOT / "packaging" / manifest), str(app), str(ROOT)],
                                       capture_output=True, text=True, timeout=120)
                self.assertEqual(stage.returncode, 0, stage.stdout + stage.stderr)
                command = self.finder / ("Open " + name + ".command")
                command.symlink_to(app / (name + ".command"))
                env = dict(self.env, MOD_STUDIO_PYTHON=sys.executable)
                del env["PIP_NO_INDEX"]
                setup = subprocess.run([str(command), "--setup"], cwd=self.temp, env=env,
                                       capture_output=True, text=True, timeout=240)
                self.assertEqual(setup.returncode, 0, setup.stdout + setup.stderr)
                del env["MOD_STUDIO_PYTHON"]
                check = subprocess.run([str(command), "--update-check"], cwd=self.temp, env=env,
                                       capture_output=True, text=True, timeout=90)
                self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
                self.assertTrue(check.stdout.strip())
                ready = self.temp / (name + ".ready")
                process = subprocess.Popen([str(command)], cwd=self.temp,
                                           env=dict(env, MOD_STUDIO_UPDATE_READY=str(ready)),
                                           start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    end = time.monotonic() + 60
                    while not ready.exists() and process.poll() is None and time.monotonic() < end:
                        time.sleep(0.1)
                    runtime_log = self.temp / "state" / name.lower() / "last-launch.log"
                    detail = runtime_log.read_text(errors="replace")[-1800:] if runtime_log.exists() else name
                    self.assertIsNone(process.poll(), detail)
                    self.assertTrue(ready.is_file(), detail)
                    self.assertEqual(ready.read_text(), "ready\n")
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=15)


if __name__ == "__main__":
    unittest.main()
