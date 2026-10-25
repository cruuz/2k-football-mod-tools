"""Windows first-run setup for the Studio launchers (Spooky, 10/23-24).

The 2K5 and APF Windows launchers used to stop with "Studio runtime package is
missing" when the Studio was run from the source ZIP. They now build a private
``.venv`` and install ``packaging/requirements-studio.txt`` on first run, with
plain progress text and a clear message when Python itself is missing.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packaging" / "windows"))

import studio_bootstrap  # noqa: E402


class FakeRun:
    """A Command interpreter that records calls and simulates a Windows Python."""

    def __init__(
        self,
        *,
        version: str = "3.12 64",
        imports: Iterable[bool] = (),
        venv_ok: bool = True,
        pip_ok: bool = True,
        hydrate_ok: bool = True,
        hydrate_fills: Iterable[Path] = (),
        launch_rc: int = 0,
        probe_error: BaseException | None = None,
    ) -> None:
        self.version = version
        self.imports = list(imports)
        self.venv_ok = venv_ok
        self.pip_ok = pip_ok
        self.hydrate_ok = hydrate_ok
        self.hydrate_fills = list(hydrate_fills)
        self.launch_rc = launch_rc
        self.probe_error = probe_error
        self.commands: list[list[str]] = []

    def __call__(self, command, **kwargs):
        command = [str(part) for part in command]
        self.commands.append(command)
        if any("struct.calcsize" in part for part in command):
            if self.probe_error is not None:
                raise self.probe_error
            return subprocess.CompletedProcess(command, 0, stdout=self.version + "\n", stderr="")
        if "-m" in command and "venv" in command:
            if self.venv_ok:
                venv = Path(command[command.index("venv") + 1])
                (venv / "Scripts").mkdir(parents=True, exist_ok=True)
                (venv / "Scripts" / "python.exe").write_text("fake runtime\n", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="venv failed")
        if "-m" in command and "pip" in command:
            return subprocess.CompletedProcess(
                command, 0 if self.pip_ok else 1, stdout="", stderr=""
            )
        if any("hydrate_release_inputs.py" in part for part in command):
            if self.hydrate_ok:
                for path in self.hydrate_fills:
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    Path(path).write_text("{}\n", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="download failed")
        if "-c" in command:
            ok = self.imports.pop(0) if self.imports else True
            return subprocess.CompletedProcess(command, 0 if ok else 1, stdout="", stderr="")
        if "-m" in command:
            return subprocess.CompletedProcess(command, self.launch_rc, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def commands_with(self, *parts: str) -> list[list[str]]:
        return [command for command in self.commands if all(part in command for part in parts)]


def make_app(temporary: str, *, doubled: bool = True, spaces: bool = True,
             data: bool = True) -> Path:
    base = Path(temporary)
    if doubled:
        base = base / "2k-football-mod-tools-main" / "2k-football-mod-tools-main"
    if spaces:
        base = base / "2K5 Studio Folder"
    (base / "packaging" / "windows").mkdir(parents=True, exist_ok=True)
    (base / "packaging" / "requirements-studio.txt").write_text(
        "PyQt5==5.15.11\nPillow==11.3.0\nnumpy==1.26.4\ncapstone==5.0.7\nunicorn==2.1.4\n",
        encoding="utf-8",
        newline="\n",
    )
    for relative in studio_bootstrap.REQUIRED_DATA_FILES:
        path = base / relative
        if data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
    return base


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory(prefix="pk1 studio ")
        self.addCleanup(self._temporary.cleanup)
        self.app = make_app(self._temporary.name)
        self.requirements = self.app / "packaging" / "requirements-studio.txt"

    def test_first_run_creates_a_private_venv_and_installs_the_pinned_set(self):
        run = FakeRun(imports=[True])
        output: list[str] = []
        python = studio_bootstrap.ensure_runtime(
            self.app,
            "python",
            requirements=self.requirements,
            run=run,
            echo=output.append,
        )
        self.assertEqual(python, self.app / ".venv" / "Scripts" / "python.exe")
        self.assertTrue(python.is_file())
        pip_calls = run.commands_with("pip", "install")
        self.assertEqual(len(pip_calls), 1)
        self.assertIn(str(self.requirements), pip_calls[0])
        self.assertIn("--only-binary=:all:", pip_calls[0])
        self.assertEqual(len(run.commands_with("venv", str(self.app / ".venv"))), 1)
        joined = "\n".join(output)
        self.assertIn("Creating a private Python runtime", joined)
        self.assertIn("Installing the Studio packages", joined)
        self.assertIn("private Studio runtime is ready", joined)

    def test_paths_with_spaces_and_doubled_folders_stay_single_arguments(self):
        self.assertIn(" ", str(self.app))
        self.assertEqual(self.app.name, "2K5 Studio Folder")
        self.assertEqual(self.app.parent.name, "2k-football-mod-tools-main")
        run = FakeRun(imports=[True])
        studio_bootstrap.ensure_runtime(
            self.app, "python", requirements=self.requirements, run=run, echo=lambda _: None
        )
        for command in run.commands:
            self.assertTrue(all(isinstance(part, str) for part in command))
        self.assertIn(str(self.app / ".venv"), run.commands_with("venv")[0])
        self.assertIn(str(self.requirements), run.commands_with("pip", "install")[0])

    def test_an_existing_working_runtime_is_reused_without_reinstalling(self):
        python = self.app / ".venv" / "Scripts" / "python.exe"
        python.parent.mkdir(parents=True)
        python.write_text("fake runtime\n", encoding="utf-8")
        run = FakeRun(imports=[True])
        output: list[str] = []
        found = studio_bootstrap.ensure_runtime(
            self.app, "python", requirements=self.requirements, run=run, echo=output.append
        )
        self.assertEqual(found, python)
        self.assertEqual(run.commands_with("pip"), [])
        self.assertEqual(run.commands_with("venv"), [])
        self.assertIn("already in", "\n".join(output))

    def test_an_existing_runtime_still_restores_missing_source_data(self):
        python = self.app / ".venv" / "Scripts" / "python.exe"
        python.parent.mkdir(parents=True)
        python.write_text("fake runtime\n", encoding="utf-8")
        make_app(self._temporary.name, data=False)
        hydration = self.app / "packaging" / "hydrate_release_inputs.py"
        hydration.write_text("# fixture\n", encoding="utf-8")
        fills = [self.app / relative for relative in studio_bootstrap.REQUIRED_DATA_FILES]
        run = FakeRun(imports=[True], hydrate_fills=fills)
        output: list[str] = []
        found = studio_bootstrap.ensure_runtime(
            self.app, "python", requirements=self.requirements, run=run, echo=output.append
        )
        self.assertEqual(found, python)
        self.assertEqual(len(run.commands_with(str(hydration))), 1)
        self.assertIn("already in", "\n".join(output))
        self.assertTrue(all(path.is_file() for path in fills))

    def test_a_broken_runtime_is_rebuilt(self):
        python = self.app / ".venv" / "Scripts" / "python.exe"
        python.parent.mkdir(parents=True)
        python.write_text("old runtime\n", encoding="utf-8")
        run = FakeRun(imports=[False, True])
        output: list[str] = []
        found = studio_bootstrap.ensure_runtime(
            self.app, "python", requirements=self.requirements, run=run, echo=output.append
        )
        self.assertEqual(found, python)
        self.assertIn("Rebuilding it now", "\n".join(output))
        self.assertEqual(len(run.commands_with("venv")), 1)
        self.assertEqual(len(run.commands_with("pip", "install")), 1)

    def test_missing_python_says_where_to_get_it(self):
        run = FakeRun(probe_error=FileNotFoundError("python"))
        with self.assertRaises(studio_bootstrap.BootstrapError) as found:
            studio_bootstrap.ensure_runtime(
                self.app, "python", requirements=self.requirements, run=run, echo=lambda _: None
            )
        message = str(found.exception)
        self.assertIn("Python was not found", message)
        self.assertIn("https://www.python.org/downloads/windows/", message)
        self.assertIn("Add python.exe to PATH", message)
        self.assertIn("No administrator rights", message)

    def test_unsupported_python_version_names_python_312(self):
        run = FakeRun(version="3.13 64")
        with self.assertRaises(studio_bootstrap.BootstrapError) as found:
            studio_bootstrap.ensure_runtime(
                self.app, "python", requirements=self.requirements, run=run, echo=lambda _: None
            )
        message = str(found.exception)
        self.assertIn("Python 3.13 is not supported", message)
        self.assertIn("Python 3.12", message)
        self.assertIn("https://www.python.org/downloads/windows/", message)
        self.assertEqual(run.commands_with("venv"), [])

    def test_32_bit_python_is_refused_before_installing(self):
        run = FakeRun(version="3.12 32")
        with self.assertRaises(studio_bootstrap.BootstrapError) as found:
            studio_bootstrap.ensure_runtime(
                self.app, "python", requirements=self.requirements, run=run, echo=lambda _: None
            )
        self.assertIn("64-bit Python", str(found.exception))
        self.assertEqual(run.commands_with("venv"), [])

    def test_failed_pip_is_safe_to_repeat_and_keeps_the_runtime(self):
        run = FakeRun(pip_ok=False)
        with self.assertRaises(studio_bootstrap.BootstrapError) as found:
            studio_bootstrap.ensure_runtime(
                self.app, "python", requirements=self.requirements, run=run, echo=lambda _: None
            )
        message = str(found.exception)
        self.assertIn("safe to repeat", message)
        self.assertIn("internet connection", message)
        self.assertTrue((self.app / ".venv" / "Scripts" / "python.exe").is_file())

    def test_missing_requirements_says_to_extract_the_whole_archive(self):
        missing = self.app / "packaging" / "requirements-studio.txt"
        missing.unlink()
        with self.assertRaises(studio_bootstrap.BootstrapError) as found:
            studio_bootstrap.ensure_runtime(
                self.app, "python", run=FakeRun(), echo=lambda _: None
            )
        self.assertIn("Extract the whole archive again", str(found.exception))

    def test_source_zip_without_data_files_downloads_them_once(self):
        app = make_app(self._temporary.name, data=False)
        requirements = app / "packaging" / "requirements-studio.txt"
        hydration = app / "packaging" / "hydrate_release_inputs.py"
        hydration.write_text("# fixture\n", encoding="utf-8")
        fills = [app / relative for relative in studio_bootstrap.REQUIRED_DATA_FILES]
        run = FakeRun(imports=[True], hydrate_fills=fills)
        output: list[str] = []
        studio_bootstrap.ensure_runtime(
            app, "python", requirements=requirements, run=run, echo=output.append
        )
        self.assertEqual(len(run.commands_with(str(hydration))), 1)
        self.assertTrue(all(path.is_file() for path in fills))
        self.assertIn("reviewed Studio data files", "\n".join(output))

    def test_release_layout_with_data_files_does_not_download_them(self):
        run = FakeRun(imports=[True])
        studio_bootstrap.ensure_runtime(
            self.app, "python", requirements=self.requirements, run=run, echo=lambda _: None
        )
        hydration = str(self.app / "packaging" / "hydrate_release_inputs.py")
        self.assertEqual(run.commands_with(hydration), [])

    def test_source_zip_without_the_hydration_script_points_to_setup(self):
        app = make_app(self._temporary.name, data=False)
        run = FakeRun(imports=[True])
        with self.assertRaises(studio_bootstrap.BootstrapError) as found:
            studio_bootstrap.ensure_runtime(
                app,
                "python",
                requirements=app / "packaging" / "requirements-studio.txt",
                run=run,
                echo=lambda _: None,
            )
        self.assertIn("Setup.exe", str(found.exception))

    def test_failed_data_download_says_check_internet_and_use_setup(self):
        app = make_app(self._temporary.name, data=False)
        (app / "packaging" / "hydrate_release_inputs.py").write_text("# fixture\n", encoding="utf-8")
        run = FakeRun(imports=[True], hydrate_ok=False)
        with self.assertRaises(studio_bootstrap.BootstrapError) as found:
            studio_bootstrap.ensure_runtime(
                app,
                "python",
                requirements=app / "packaging" / "requirements-studio.txt",
                run=run,
                echo=lambda _: None,
            )
        message = str(found.exception)
        self.assertIn("Check the internet connection", message)
        self.assertIn("Setup.exe", message)

    def test_unwritable_folder_does_not_ask_for_administrator_rights(self):
        run = FakeRun(venv_ok=False)
        with self.assertRaises(studio_bootstrap.BootstrapError) as found:
            studio_bootstrap.ensure_runtime(
                self.app, "python", requirements=self.requirements, run=run, echo=lambda _: None
            )
        message = str(found.exception)
        self.assertIn("Desktop or Documents", message)
        self.assertIn("do not run as administrator", message)

    def test_setup_only_installs_and_does_not_launch(self):
        run = FakeRun(imports=[True])
        output: list[str] = []
        status = studio_bootstrap.main(
            [
                "--app-root",
                str(self.app),
                "--python",
                "python",
                "--requirements",
                str(self.requirements),
                "--",
                "--setup",
            ],
            run=run,
            echo=output.append,
        )
        self.assertEqual(status, 0)
        self.assertEqual(run.commands_with("-m", "mod_editor"), [])
        self.assertIn("Setup finished", "\n".join(output))

    def test_launch_uses_the_private_runtime_and_passes_the_app_arguments(self):
        run = FakeRun(imports=[True], launch_rc=7)
        status = studio_bootstrap.main(
            [
                "--app-root",
                str(self.app),
                "--python",
                "python",
                "--requirements",
                str(self.requirements),
                "--",
                "--check-registry",
            ],
            run=run,
            echo=lambda _: None,
        )
        self.assertEqual(status, 7)
        launches = run.commands_with("-m", "mod_editor")
        self.assertEqual(len(launches), 1)
        self.assertEqual(launches[0][-1], "--check-registry")


class LauncherTextTests(unittest.TestCase):
    def test_both_windows_launchers_use_the_bootstrap_and_never_elevate(self):
        for relative in ("2K5-Mod-Studio.bat", "APF-2K8-Mod-Studio.bat"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(launcher=relative):
                self.assertIn("packaging\\windows\\studio_bootstrap.py", text)
                self.assertIn("..\\runtime\\python.exe", text)
                self.assertIn(".venv", text)
                self.assertIn("requirements-studio.txt", text)
                self.assertIn("https://www.python.org/downloads/windows/", text)
                self.assertIn("--setup", text)
                for name in ("numpy", "capstone", "unicorn"):
                    self.assertIn("import " + name, text)
                lowered = text.lower()
                self.assertNotIn("runas", lowered)
                self.assertNotIn("start-process", lowered)
                self.assertNotIn("administrator:true", lowered.replace(" ", ""))

    def test_bootstrap_module_uses_only_the_standard_library(self):
        tree = ast.parse(
            (ROOT / "packaging/windows/studio_bootstrap.py").read_text(encoding="utf-8")
        )
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        self.assertTrue(names <= set(sys.stdlib_module_names), names)

    def test_release_allowlists_ship_the_bootstrap(self):
        for relative in ("packaging/release-allowlist.txt", "packaging/apf2k8-release-allowlist.txt"):
            lines = (ROOT / relative).read_text(encoding="utf-8").splitlines()
            with self.subTest(allowlist=relative):
                self.assertIn("packaging/windows/studio_bootstrap.py", lines)
                self.assertIn("2K5-Mod-Studio.bat" if "apf" not in relative
                              else "APF-2K8-Mod-Studio.bat", lines)


class DocumentationTests(unittest.TestCase):
    def test_readme_says_release_asset_not_source_zip(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Download the release asset, not the source ZIP", readme)
        self.assertIn("Code > Download ZIP", readme)
        self.assertIn("If you downloaded the source ZIP", readme)
        self.assertIn("2K5-Mod-Studio-*-Setup.exe", readme)
        self.assertIn("2K5-Mod-Studio.bat --setup", readme)

    def test_start_here_says_release_asset_not_source_zip(self):
        text = (ROOT / "docs/START_HERE.md").read_text(encoding="utf-8")
        self.assertIn("Code > Download ZIP", text)
        self.assertIn("If you downloaded the source ZIP", text)
        self.assertIn("2K5-Mod-Studio-*-Setup.exe", text)
        self.assertIn("2K5-Mod-Studio.bat --setup", text)

    def test_faq_answers_the_source_zip_report(self):
        text = (ROOT / "docs/mod_editor/2k5_mod_studio_faq.md").read_text(encoding="utf-8")
        self.assertIn("Code > Download ZIP", text)
        self.assertIn("2K5-Mod-Studio.bat", text)
        self.assertIn("https://www.python.org/downloads/windows/", text)


if __name__ == "__main__":
    unittest.main()
