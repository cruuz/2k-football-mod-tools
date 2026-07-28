"""Every shipped tool must import when its own directory is not on sys.path.

This exists because of a failure that only ever appeared on installed Windows
copies. The product shells out to ``app\\tools\\*.py``, and those scripts import
each other (``from nfl_outer import ...``). On a normal interpreter that works
for free, because Python prepends a script's own directory to ``sys.path``.

The shipped Windows runtime is an *embeddable* CPython, and an embeddable build
with a ``._pth`` file behaves differently in exactly one way that matters here:
``sys.path`` becomes what the ``._pth`` lists and **the script directory is not
added**. ``..\\app`` was listed, so ``mod_editor`` imported; ``..\\app\\tools``
was not, so the subprocess died with::

    Could not catalog the game files: ModuleNotFoundError: No module named 'nfl_outer'

Nothing we ran could have caught it. The tarball works, CI works, the source
tree works -- every one of those launches Python the ordinary way. Only the
installer does not, and the installer is what most people use.

So this asserts the property directly rather than the packaging detail: with the
tool's own directory absent from ``sys.path``, importing it still succeeds. That
holds however it is launched, on every platform, and it will keep holding for a
tool added next year without anyone remembering this note.
"""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOLS = _REPO_ROOT / "tools"
_ALLOWLISTS = (
    _REPO_ROOT / "packaging" / "release-allowlist.txt",
    _REPO_ROOT / "packaging" / "apf2k8-release-allowlist.txt",
)


def _shipped_tools() -> list[Path]:
    shipped: dict[Path, None] = {}
    for allowlist in _ALLOWLISTS:
        if not allowlist.exists():
            continue
        for raw in allowlist.read_text(encoding="utf-8").splitlines():
            entry = raw.strip()
            if (
                not entry.startswith("tools/")
                or not entry.endswith(".py")
                or entry.startswith("tools/vendor/")
            ):
                continue
            path = _REPO_ROOT / entry
            if path.exists():
                shipped[path] = None
    return sorted(shipped)


def _sibling_importers() -> list[Path]:
    """Shipped tools that import another module from tools/."""
    siblings = {path.stem for path in _TOOLS.glob("*.py")}
    found: list[Path] = []
    for path in _shipped_tools():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module in siblings
            ) or (
                isinstance(node, ast.Import)
                and any(alias.name in siblings for alias in node.names)
            ):
                found.append(path)
                break
    return found


class ShippedToolSelfSufficiencyTests(unittest.TestCase):
    def test_there_are_sibling_importers_to_check(self) -> None:
        self.assertGreater(
            len(_sibling_importers()), 30, "expected many shipped tools to import siblings"
        )

    def test_each_imports_without_its_own_directory_on_sys_path(self) -> None:
        """The exact condition the embeddable runtime creates.

        ``-I`` isolates the interpreter and, crucially, the child never receives
        ``tools/`` on ``sys.path`` from us -- so a tool only imports if it puts
        its own directory back itself.
        """
        broken: list[str] = []
        for path in _sibling_importers():
            probe = (
                "import importlib.util, sys\n"
                f"spec = importlib.util.spec_from_file_location('probe_{path.stem}', r'{path}')\n"
                "module = importlib.util.module_from_spec(spec)\n"
                f"sys.modules['probe_{path.stem}'] = module\n"
                "spec.loader.exec_module(module)\n"
            )
            result = subprocess.run(
                [sys.executable, "-I", "-c", probe],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(_REPO_ROOT),
            )
            if result.returncode != 0 and "ModuleNotFoundError" in result.stderr:
                last = result.stderr.strip().splitlines()[-1]
                broken.append(f"{path.name}: {last}")
        self.assertEqual(
            broken,
            [],
            "Shipped tools cannot import with their own directory off sys.path, "
            "which is exactly how the installed Windows runtime launches them:\n  "
            + "\n  ".join(broken),
        )


class InstallerPathFileTests(unittest.TestCase):
    """The ._pth must also list tools/, as the second of two independent guards."""

    def test_the_generated_pth_lists_the_tools_directory(self) -> None:
        builder = _REPO_ROOT / "packaging" / "windows" / "build_windows_installer.py"
        if not builder.exists():  # pragma: no cover - builder always ships
            self.skipTest("installer builder not present")
        source = builder.read_text(encoding="utf-8")
        self.assertIn('"..\\\\app"', source)
        self.assertIn(
            '"..\\\\app\\\\tools"',
            source,
            "the embeddable runtime's ._pth must list app\\tools, or the "
            "subprocess that catalogs the game cannot import its own siblings",
        )


if __name__ == "__main__":
    unittest.main()
