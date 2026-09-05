"""Runner contracts; no Wine download, GUI, or product modifications required."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "local_windows_ci_tested", ROOT / "packaging/windows/local_windows_ci.py")
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="winci plan ")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.tests = self.repo / "tests/mod_editor"
        self.tests.mkdir(parents=True)
        for name, content in {"test_alpha.py": "import alpha\n", "test_beta.py": "# beta\n",
                              "test_gamma.py": "from alpha import x\n"}.items():
            (self.tests / name).write_text(content)

    def names(self, **kwargs):
        return [p.name for p in runner.plan(self.repo, kwargs.get("only", []), kwargs.get("changed"))]

    def test_default_and_repeatable_globs(self):
        args = runner.argument_parser().parse_args(["--only", "test_b*", "--only", "test_alpha.py", "-j", "2"])
        self.assertEqual(args.jobs, 2)
        self.assertEqual(self.names(only=args.only), ["test_alpha.py", "test_beta.py"])
        self.assertEqual(len(self.names()), 3)

    def test_only_multiple_names_and_deduplication(self):
        args = runner.argument_parser().parse_args(["--only", "test_alpha.py", "test_*", "--keep-going"])
        self.assertTrue(args.keep_going)
        self.assertEqual(len(self.names(only=args.only)), 3)

    def test_unmatched_only_is_an_error_even_with_other_matches(self):
        with self.assertRaisesRegex(ValueError, "matched no test"):
            self.names(only=["test_alpha.py", "missing.py"])

    def test_changed_direct_modules_deleted_modules_and_intersection(self):
        changed = {"tests/mod_editor/test_beta.py", "mod_editor/alpha.py"}
        self.assertEqual(len(self.names(changed=changed)), 3)
        self.assertEqual(self.names(only=["test_g*"], changed=changed), ["test_gamma.py"])
        self.assertEqual(self.names(changed={"mod_editor/alpha.py"}), ["test_alpha.py", "test_gamma.py"])
        self.assertEqual(self.names(changed={"README.md"}), [])

    def test_argument_limits(self):
        for argv in (["-j", "0"], ["--timeout", "-1"], ["--timeout", "nan"], ["--timeout", "inf"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                runner.argument_parser().parse_args(argv)

    def test_ci_skip_list_and_isolated_rule_stay_in_parity(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        case = workflow.split('case "$name" in', 1)[1].split('skipped=$((skipped + 1))', 1)[0]
        self.assertEqual(runner.LEAN_SKIPS, set(re.findall(r"test_[\w]+\.py", case)))
        self.assertIn(f'isolated="{runner.ISOLATED}"', workflow)
        self.assertIn(runner.EVIDENCE, workflow)
        self.assertEqual(runner.argument_parser().parse_args([]).timeout, 420)

    def test_evidence_controls_skips_even_when_explicitly_selected(self):
        name = next(iter(runner.LEAN_SKIPS))
        self.assertEqual(runner.skip_reason(self.repo, name), runner.LEAN_REASON)
        self.assertIsNone(runner.skip_reason(self.repo, "test_modpack.py"))
        evidence = self.repo / runner.EVIDENCE
        evidence.parent.mkdir(parents=True)
        evidence.write_text("{}")
        self.assertIsNone(runner.skip_reason(self.repo, name))

    @unittest.skipUnless(shutil.which("git"), "git is absent")
    def test_changed_paths_include_staged_unstaged_untracked_and_deleted(self):
        def git(*args):
            return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.STDOUT)
        git("init")
        git("add", "tests/mod_editor/test_alpha.py", "tests/mod_editor/test_beta.py", "tests/mod_editor/test_gamma.py")
        git("-c", "user.name=Runner Test", "-c", "user.email=runner@example.invalid", "commit", "-m", "fixture")
        git("update-ref", "refs/remotes/origin/main", "HEAD")
        (self.tests / "test_alpha.py").write_text("# unstaged\n")
        (self.tests / "test_beta.py").unlink()
        (self.repo / "new_module.py").write_text("# untracked\n")
        (self.tests / "test_gamma.py").write_text("# staged\n")
        git("add", "tests/mod_editor/test_gamma.py")
        self.assertEqual(runner.changed_paths(self.repo), {
            "tests/mod_editor/test_alpha.py", "tests/mod_editor/test_beta.py",
            "tests/mod_editor/test_gamma.py", "new_module.py"})


class OutputTests(unittest.TestCase):
    def test_last_unittest_count_like_ci(self):
        self.assertEqual(runner.test_count("Ran 90 tests\nchild\nRan 1 test in 0.1s\nOK"), 1)
        self.assertIsNone(runner.test_count("no unittest report"))
        self.assertEqual(runner.test_count("Ran 0 tests"), 0)

    def test_summary_counts_failed_tests_and_file_skips(self):
        results = [runner.Result("a", output="Ran 4 tests\nOK (skipped=1)"),
                   runner.Result("b", 1, "Ran 2 tests\nFAILED"),
                   runner.Result("c", skipped="lean"), runner.Result("d", 124, "TIMED OUT")]
        self.assertEqual(runner.summary(results), "SUMMARY: files=4 passed=1 failed=2 skipped=1 tests=6")

    def test_failure_tail_and_unknown_count(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            runner.report_result(runner.Result("bad.py", 1, "first line\n" + "tail\n" * 40))
            runner.report_result(runner.Result("good.py"))
        self.assertNotIn("first line", output.getvalue())
        self.assertIn("FAIL  bad.py  (rc=1)", output.getvalue())
        self.assertIn("PASS  good.py  (? tests)", output.getvalue())


class PathTests(unittest.TestCase):
    def test_environment_clears_display_and_isolated_pythonpath(self):
        with patch.dict(os.environ, {"DISPLAY": ":99", "WAYLAND_DISPLAY": "socket", "PYTHONPATH": "wrong", "PYTHONHOME": "wrong"}):
            isolated = runner.wine_environment(Path("/tmp/prefix"))
            normal = runner.wine_environment(Path("/tmp/prefix"), r"Z:\repo with spaces")
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "PYTHONPATH", "PYTHONHOME"):
            self.assertNotIn(key, isolated)
        self.assertEqual(normal["PYTHONPATH"], r"Z:\repo with spaces")
        self.assertEqual(isolated["QT_QPA_PLATFORM"], "offscreen")
        self.assertEqual(isolated["MOD_STUDIO_NO_UPDATE_CHECK"], "1")
        self.assertEqual(isolated["PYTHONFAULTHANDLER"], "1")

    def test_private_pth_does_not_pin_a_checkout_or_installer_app(self):
        self.assertEqual(runner.pth_text().splitlines(), [
            "winci-bootstrap", "python312.zip", ".", "Lib\\site-packages", "import site"])

    def test_startup_resolves_repo_and_isolated_stage(self):
        with tempfile.TemporaryDirectory(prefix="winci import ") as temp:
            root = Path(temp)
            for name in ("repo", "stage"):
                package = root / name / "mod_editor"
                package.mkdir(parents=True)
                (package / "__init__.py").write_text("")
            # -I -S removes host startup/PYTHONPATH. Execute the exact private
            # startup source to check its path decisions using real imports.
            code = runner.STARTUP + "\nimport mod_editor; print(mod_editor.__file__)\n"
            env = dict(os.environ, PYTHONPATH=str(root / "repo"))
            normal = subprocess.check_output([sys.executable, "-I", "-S", "-c", code], cwd=root, env=env, text=True)
            self.assertEqual(Path(normal.strip()), root / "repo/mod_editor/__init__.py")
            env.pop("PYTHONPATH")
            isolated = subprocess.check_output([sys.executable, "-I", "-S", "-c", code], cwd=root / "stage", env=env, text=True)
            self.assertEqual(Path(isolated.strip()), root / "stage/mod_editor/__init__.py")

    def test_startup_restores_script_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "sibling.py").write_text("value = 42\n")
            code = "import sys; sys.argv = [" + repr(str(root / "script.py")) + "]\n"
            code += runner.STARTUP + "\nimport sibling; print(sibling.value)\n"
            result = subprocess.check_output([sys.executable, "-I", "-S", "-c", code], text=True)
            self.assertEqual(result.strip(), "42")

    def test_run_file_selects_environment_and_records_windows_pid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            seen = []
            def execute(command, env, cwd, log, timeout, pidfile):
                seen.append((command, env))
                log.write_text("Ran 2 tests\nOK\n")
                return 0
            env = runner.wine_environment(root / "prefix")
            with patch.object(runner, "run_process", side_effect=execute):
                for name in (runner.ISOLATED, "test_modpack.py"):
                    result = runner.run_file(root / name, root, r"Z:\repo space", root / "runtime", env, root, 420, r"Z:\logs")
                    self.assertEqual(result.rc, 0)
            self.assertNotIn("PYTHONPATH", seen[0][1])
            self.assertEqual(seen[1][1]["PYTHONPATH"], r"Z:\repo space")
            self.assertEqual(seen[1][0][-2], r"Z:\repo space\tests\mod_editor\test_modpack.py")
            self.assertEqual(seen[1][0][-1], r"Z:\logs\test_modpack.py.pid")
            self.assertNotIn("PYTHONPATH", env)


class CacheTests(unittest.TestCase):
    def test_build_once_private_copy_and_builder_invalidation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            builder_file = root / "builder.py"
            builder_file.write_text("version 1")
            calls = []
            class Builder:
                __file__ = str(builder_file)
                @staticmethod
                def build_runtime(work, downloads):
                    calls.append(work)
                    runtime = work / "runtime"
                    runtime.mkdir(exist_ok=True)
                    (runtime / "python.exe").write_bytes(b"pinned executable")
                    (runtime / "python312._pth").write_text("installer pth")
            with patch.object(runner, "installer_module", return_value=Builder), contextlib.redirect_stdout(io.StringIO()):
                private = runner.ensure_runtime(root)
                runner.ensure_runtime(root)
                self.assertEqual(len(calls), 1)
                self.assertEqual((root / "runtime/python312._pth").read_text(), "installer pth")
                self.assertEqual((private / "python312._pth").read_text(), runner.pth_text())
                self.assertEqual((private / "python.exe").read_bytes(), b"pinned executable")
                builder_file.write_text("version 2")
                runner.ensure_runtime(root)
                self.assertEqual(len(calls), 2)

    def test_existing_unowned_prefix_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "system.reg").write_text("unrelated prefix")
            with self.assertRaisesRegex(RuntimeError, "unowned Wine prefix"):
                runner.ensure_prefix(root, {}, root)


@unittest.skipUnless(sys.platform == "linux", "Unix process groups require Linux")
class ProcessTests(unittest.TestCase):
    def test_timeout_targets_only_the_recorded_windows_process_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pidfile = root / "test.pid"
            pidfile.write_text("77")
            parent, killer = Mock(), Mock()
            killer.wait.return_value = 0
            env = {"WINEPREFIX": str(root / "dedicated")}
            with patch.object(runner.subprocess, "Popen", side_effect=[parent, killer]) as popen, \
                 patch.object(runner, "kill_group") as kill, \
                 patch.object(runner.time, "monotonic", side_effect=[0, 1]):
                rc = runner.run_process(["wine", "python.exe"], env, root, root / "log", 0.5, pidfile)
            self.assertEqual(rc, 124)
            self.assertEqual(popen.call_args_list[1].args[0], ["wine", "taskkill", "/PID", "77", "/T", "/F"])
            self.assertEqual(popen.call_args_list[1].kwargs["env"], env)
            self.assertEqual([call.args[0] for call in kill.call_args_list], [killer, parent])

    def test_hung_taskkill_still_kills_the_launcher_group(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pidfile = root / "test.pid"
            pidfile.write_text("77")
            parent, killer = Mock(), Mock()
            killer.wait.side_effect = subprocess.TimeoutExpired("taskkill", 30)
            with patch.object(runner.subprocess, "Popen", side_effect=[parent, killer]), \
                 patch.object(runner, "kill_group") as kill, \
                 patch.object(runner.time, "monotonic", side_effect=[0, 1]):
                rc = runner.run_process(["wine", "python.exe"], {}, root, root / "log", 0.5, pidfile)
            self.assertEqual(rc, 124)
            self.assertEqual([call.args[0] for call in kill.call_args_list], [killer, parent])
            self.assertIn("taskkill timed out", (root / "log").read_text())

    def test_actual_pth_startup_and_child_import_isolation(self):
        # Native CPython also implements ._pth. Exercise the actual site hook
        # and a child interpreter without pretending these are Windows tests.
        with tempfile.TemporaryDirectory(prefix="winci pth ") as temp:
            root = Path(temp)
            python = root / "python"
            shutil.copy2(sys.executable, python)
            (root / "python._pth").write_text("\n".join([
                str(root), sysconfig.get_path("stdlib"), sysconfig.get_config_var("DESTSHARED"), "import site", ""]))
            (root / "sitecustomize.py").write_text(runner.STARTUP)
            for name in ("repo", "stage"):
                package = root / name / "mod_editor"
                package.mkdir(parents=True)
                (package / "__init__.py").write_text("")
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "sibling.py").write_text("value = 42\n")
            child_probe = "import mod_editor; print(mod_editor.__file__)"
            script = scripts / "check.py"
            script.write_text(
                "import os,subprocess,sys,sibling,mod_editor\n"
                "assert sibling.value == 42\nprint(mod_editor.__file__, flush=True)\n"
                "env=dict(os.environ); env.pop('PYTHONPATH',None)\n"
                "subprocess.run([sys.executable,'-c'," + repr(child_probe) + "], env=env, cwd="
                + repr(str(root / "stage")) + ", check=True)\n")
            env = dict(os.environ, PYTHONPATH=str(root / "repo"))
            result = subprocess.check_output([str(python), str(script)], cwd=root, env=env, text=True)
            self.assertEqual([Path(p) for p in result.splitlines()], [
                root / "repo/mod_editor/__init__.py", root / "stage/mod_editor/__init__.py"])

    def test_timeout_kills_child_and_grandchild_and_records_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pid = root / "descendant"
            child = "import os,time,pathlib; pathlib.Path(" + repr(str(pid)) + ").write_text(str(os.getpid())); time.sleep(60)"
            parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); time.sleep(60)"
            log = root / "test.log"
            started = time.monotonic()
            rc = runner.run_process([sys.executable, "-c", parent], dict(os.environ), root, log, 1)
            self.assertEqual(rc, 124)
            self.assertLess(time.monotonic() - started, 5)
            self.assertIn("TIMED OUT after 1s", log.read_text())
            descendant = int(pid.read_text())
            # A killed child can briefly remain a zombie until PID 1 reaps it.
            status = Path(f"/proc/{descendant}/stat")
            deadline = time.monotonic() + 2
            while status.exists():
                try:
                    state = status.read_text().split(") ", 1)[1].split()[0]
                except FileNotFoundError:
                    break
                if state == "Z":
                    break
                self.assertLess(time.monotonic(), deadline, "timed-out descendant is still running")
                time.sleep(0.01)

    def test_lock_refuses_a_second_runner(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "lock"
            with runner.exclusive(lock), self.assertRaisesRegex(RuntimeError, "another runner"):
                with runner.exclusive(lock):
                    self.fail("second lock acquired")


class WineAvailabilityTests(unittest.TestCase):
    def test_wine_can_start_without_a_display(self):
        if sys.platform != "linux" or not shutil.which("wine"):
            self.skipTest("Wine is absent; pure runner contracts were still tested")
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(["wine", "--version"], capture_output=True, text=True, timeout=15,
                                    env=runner.wine_environment(Path(temp) / "prefix"))
        if result.returncode in (-31, 159):
            self.skipTest("execution sandbox denies Wine startup (SIGSYS); Windows acceptance is unverified")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("wine-", result.stdout)


if __name__ == "__main__":
    unittest.main()
