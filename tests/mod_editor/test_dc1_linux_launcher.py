"""Linux launcher regressions from the Discord sweep (Zane and sakes, 10/11 to 10/16).

The 2K5 Linux archive told people to run ./2K5-Mod-Studio.sh and ./install.sh, but
shipped neither (install.sh belongs to APF 2K8), and a launch failure showed no
dialog at all because zenity read a traceback line such as `in <module>` as markup.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")


def _write_exec(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class ShippedFiles(unittest.TestCase):
    def test_wrapper_is_in_the_release_allowlist_and_executable(self):
        allow = (ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("2K5-Mod-Studio.sh", allow)
        wrapper = ROOT / "2K5-Mod-Studio.sh"
        self.assertTrue(wrapper.is_file())
        if os.name != "nt":
            self.assertTrue(os.access(wrapper, os.X_OK), "the wrapper must carry the executable bit")
        text = wrapper.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/usr/bin/env bash\n"))
        self.assertIn("--setup", text)
        self.assertIn("requirements-studio.txt", text)

    def test_readme_names_only_files_the_archive_ships(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        linux = readme.split("**Linux, SteamOS and Steam Deck", 1)[1].split("**Windows**", 1)[0]
        self.assertIn("./2K5-Mod-Studio.sh --setup", linux)
        self.assertNotIn("./install.sh ", linux)

    @unittest.skipUnless(BASH, "bash required")
    def test_scripts_parse(self):
        for relative in ("2K5-Mod-Studio.sh", "tools/launch_2k5_mod_studio.sh",
                         "tools/launch_apf2k8_mod_studio.sh"):
            with self.subTest(script=relative):
                done = subprocess.run([BASH, "-n", str(ROOT / relative)], capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)


@unittest.skipUnless(BASH and os.name != "nt", "POSIX bash required")
class WrapperBehaviour(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = Path(self._tmp.name) / "app"
        self.app.mkdir()
        shutil.copy2(ROOT / "2K5-Mod-Studio.sh", self.app / "2K5-Mod-Studio.sh")
        (self.app / "packaging").mkdir()
        shutil.copy2(ROOT / "packaging" / "requirements-studio.txt",
                     self.app / "packaging" / "requirements-studio.txt")
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("MOD_STUDIO_PYTHON", "DISPLAY", "WAYLAND_DISPLAY")}

    def run_wrapper(self, *args, env=None):
        return subprocess.run([BASH, str(self.app / "2K5-Mod-Studio.sh"), *args],
                              capture_output=True, text=True, env=env or self.env, timeout=60)

    def test_missing_launcher_says_to_extract_the_whole_archive(self):
        done = self.run_wrapper()
        self.assertEqual(done.returncode, 1)
        self.assertIn("launcher is missing", done.stderr)
        self.assertIn("Extract the whole archive", done.stderr)

    def test_arguments_reach_the_launcher(self):
        _write_exec(self.app / "tools" / "launch_2k5_mod_studio.sh",
                    "#!/usr/bin/env bash\nprintf 'ARGS:%s\\n' \"$*\"\n")
        # a private runtime already exists, so no first-run hint is printed
        _write_exec(self.app / ".venv" / "bin" / "python3", "#!/bin/sh\nexit 0\n")
        done = self.run_wrapper("--update-check", "x")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("ARGS:--update-check x", done.stdout)
        self.assertEqual(done.stderr, "")

    def test_launcher_without_the_executable_bit_still_starts(self):
        # zip extractors often drop the bit; the wrapper then runs the launcher through bash
        launcher = self.app / "tools" / "launch_2k5_mod_studio.sh"
        _write_exec(launcher, "#!/usr/bin/env bash\nprintf 'ARGS:%s\\n' \"$*\"\n")
        launcher.chmod(0o644)
        _write_exec(self.app / ".venv" / "bin" / "python3", "#!/bin/sh\nexit 0\n")
        done = self.run_wrapper("a")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("ARGS:a", done.stdout)

    def test_setup_without_the_venv_module_explains_the_apt_package(self):
        stub = Path(self._tmp.name) / "fakepython"
        _write_exec(stub, "#!/bin/sh\n"
                          "if [ \"$1\" = -m ] && [ \"$2\" = venv ]; then exit 1; fi\n"
                          "exit 0\n")
        env = dict(self.env, MOD_STUDIO_PYTHON=str(stub), PATH=f"{stub.parent}:{os.environ['PATH']}")
        # python3 must resolve for the pre-check; the stub is reached through MOD_STUDIO_PYTHON
        done = self.run_wrapper("--setup", env=env)
        self.assertEqual(done.returncode, 1)
        self.assertIn("python3-venv", done.stderr)
        self.assertFalse((self.app / ".venv").exists(), "a half-made runtime must not be left behind")

    def test_setup_success_creates_the_runtime_and_installs_the_pinned_set(self):
        log = Path(self._tmp.name) / "calls.log"
        # The base interpreter's `-m venv DIR` builds DIR/bin/python3, which records each call.
        stub = Path(self._tmp.name) / "basepython"
        _write_exec(stub, "#!/bin/sh\n"
                          "if [ \"$1\" = -m ] && [ \"$2\" = venv ]; then\n"
                          "  mkdir -p \"$3/bin\"\n"
                          f"  printf '#!/bin/sh\\necho \"$@\" >> {log}\\nexit 0\\n' > \"$3/bin/python3\"\n"
                          "  chmod +x \"$3/bin/python3\"\n"
                          "  exit 0\n"
                          "fi\n"
                          "exit 0\n")
        env = dict(self.env, MOD_STUDIO_PYTHON=str(stub))
        done = self.run_wrapper("--setup", env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Setup finished", done.stdout)
        calls = log.read_text(encoding="utf-8")
        self.assertIn("-m pip install -r", calls)
        self.assertIn("requirements-studio.txt", calls)
        self.assertIn("PyQt5", calls)  # the final import check

    def test_setup_failure_of_pip_is_repeatable_and_says_so(self):
        stub = Path(self._tmp.name) / "basepython"
        _write_exec(stub, "#!/bin/sh\n"
                          "if [ \"$1\" = -m ] && [ \"$2\" = venv ]; then\n"
                          "  mkdir -p \"$3/bin\"\n"
                          "  printf '#!/bin/sh\\nexit 1\\n' > \"$3/bin/python3\"\n"
                          "  chmod +x \"$3/bin/python3\"\n"
                          "fi\n"
                          "exit 0\n")
        env = dict(self.env, MOD_STUDIO_PYTHON=str(stub))
        done = self.run_wrapper("--setup", env=env)
        self.assertEqual(done.returncode, 1)
        self.assertIn("safe to repeat", done.stderr)

    def _versioned_stub(self, name, version, log):
        """A base interpreter that reports `version` and whose `-m venv DIR` builds a recording DIR/bin/python3."""
        stub = Path(self._tmp.name) / name
        _write_exec(stub, "#!/bin/sh\n"
                          f"if [ \"$1\" = -c ]; then echo {version}; exit 0; fi\n"
                          "if [ \"$1\" = -V ]; then echo Python " + version + "; exit 0; fi\n"
                          "if [ \"$1\" = -m ] && [ \"$2\" = venv ]; then\n"
                          "  mkdir -p \"$3/bin\"\n"
                          "  printf '#!/bin/sh\\n"
                          f"if [ \"$1\" = -c ] && [ \"$2\" != \"${{2#*version_info}}\" ]; then echo {version}; exit 0; fi\\n"
                          f"echo {name} \"$@\" >> {log}\\nexit 0\\n' > \"$3/bin/python3\"\n"
                          "  chmod +x \"$3/bin/python3\"\n"
                          "  exit 0\n"
                          "fi\n"
                          "exit 0\n")
        return stub

    def test_setup_rebuilds_an_old_runtime_with_mod_studio_python(self):
        """fx1 (pr67/pr68 review): a .venv made from Python 3.13 was kept, so MOD_STUDIO_PYTHON could never fix it."""
        log = Path(self._tmp.name) / "calls.log"
        old = self.app / ".venv" / "bin" / "python3"
        _write_exec(old, "#!/bin/sh\n"
                         "if [ \"$1\" = -c ]; then echo 3.13; exit 0; fi\n"
                         f"echo OLD \"$@\" >> {log}\nexit 1\n")
        good = self._versioned_stub("py312", "3.12", log)
        done = self.run_wrapper("--setup", env=dict(self.env, MOD_STUDIO_PYTHON=str(good)))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Rebuilding the private Python runtime", done.stdout)
        self.assertNotIn("this is Python", done.stderr)    # the version note checks MOD_STUDIO_PYTHON, not python3
        calls = log.read_text(encoding="utf-8")
        self.assertNotIn("OLD", calls)
        self.assertIn("py312 -m pip install -r", calls)

    def test_setup_keeps_a_working_runtime_when_rerun_without_the_variable(self):
        log = Path(self._tmp.name) / "calls.log"
        made = self._versioned_stub("py312", "3.12", log)
        done = self.run_wrapper("--setup", env=dict(self.env, MOD_STUDIO_PYTHON=str(made)))
        self.assertEqual(done.returncode, 0, done.stderr)
        newer = self._versioned_stub("python3", "3.13", log)   # the system python3 on PATH
        env = dict(self.env, PATH=f"{newer.parent}:{os.environ['PATH']}")
        done = self.run_wrapper("--setup", env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("Rebuilding", done.stdout)
        self.assertEqual(log.read_text(encoding="utf-8").count("py312 -m pip install"), 2)


@unittest.skipUnless(BASH and os.name != "nt", "POSIX bash required")
class ErrorDialogMarkup(unittest.TestCase):
    """zenity and kdialog parse their text as markup; angle brackets must be escaped."""

    def check(self, relative: str, tool: str, marker_prefix: str):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tools = tmp / "app" / "tools"
            tools.mkdir(parents=True)
            shutil.copy2(ROOT / relative, tools / Path(relative).name)
            (tmp / "app" / "mod_editor").mkdir()
            (tmp / "app" / "mod_editor" / "__main__.py").write_text("", encoding="utf-8")
            (tmp / "app" / "mod_editor" / "apf_studio").mkdir()
            (tmp / "app" / "mod_editor" / "apf_studio" / "__main__.py").write_text("", encoding="utf-8")
            captured = tmp / "dialog.txt"
            dialog = tmp / "bin" / tool
            _write_exec(dialog, "#!/bin/bash\n"
                                "for a in \"$@\"; do printf '%s\\n' \"$a\"; done > \"$CAPTURE\"\n")
            # A runtime whose package check passes but whose start-up fails with a traceback.
            fake_python = tmp / "py" / "python3"
            _write_exec(fake_python, "#!/bin/bash\n"
                                     "case \"$1\" in\n"
                                     "  -c) exit 0 ;;\n"
                                     "  *) printf 'Traceback (most recent call last):\\n"
                                     "  File \"<string>\", line 1, in <module>\\n"
                                     "ImportError: a & b\\n' >&2; exit 3 ;;\n"
                                     "esac\n")
            env = {k: v for k, v in os.environ.items() if k not in ("MOD_STUDIO_PYTHON",)}
            env.update(MOD_STUDIO_PYTHON=str(fake_python), DISPLAY=":99", CAPTURE=str(captured),
                       PATH=f"{dialog.parent}:{os.environ['PATH']}",
                       XDG_STATE_HOME=str(tmp / "state"), HOME=str(tmp / "home"))
            (tmp / "home").mkdir()
            done = subprocess.run([BASH, str(tools / Path(relative).name)],
                                  capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(done.returncode, 3, done.stderr)
            text = captured.read_text(encoding="utf-8")
            self.assertNotIn("<module>", text)
            self.assertIn("&lt;module&gt;", text)
            self.assertIn("a &amp; b", text)
            self.assertIn(marker_prefix, text)

    def test_2k5_launcher_escapes_zenity_text(self):
        self.check("tools/launch_2k5_mod_studio.sh", "zenity", "2K5 Mod Studio could not start.")

    def test_apf_launcher_escapes_zenity_text(self):
        self.check("tools/launch_apf2k8_mod_studio.sh", "zenity", "APF 2K8 Mod Studio could not start.")


if __name__ == "__main__":
    unittest.main()
