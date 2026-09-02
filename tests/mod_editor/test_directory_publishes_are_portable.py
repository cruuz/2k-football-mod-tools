"""A folder must be published through the platform layer, never by hand.

Exporting a Team Kit as a folder failed on Windows for everyone, with::

    [WinError 5] Access is denied:
      'G:\\.ARZ-style-0-HOME-AWAY-Team-Kit.team-kit-24e58b02...'
      -> 'G:\\ARZ-style-0-HOME-AWAY-Team-Kit'

The export had hand-rolled its own publish: reserve the destination name with
``mkdir``, then ``os.replace`` the finished staging directory onto it. That is a
POSIX idiom. ``rename(2)`` there replaces an existing *empty* directory, so the
reservation both claims the name and gets swapped away. Windows ``MoveFileEx``
**cannot replace a directory at all** -- documented, not a quirk -- so the second
step always failed, and it failed with a permissions error that reads like a
drive problem rather than a bug.

``platform_compat.publish_no_replace`` already existed and already knew the right
primitive for each platform: ``renameat2(RENAME_NOREPLACE)`` on Linux,
``renamex_np(RENAME_EXCL)`` on macOS, and a plain ``os.rename`` on Windows, where
refusing to overwrite is exactly what os.rename does for directories. One call
site simply did not use it.

So this asserts the rule rather than the symptom: no shipped module reserves a
directory with ``mkdir`` and then renames onto it. That check runs on any
platform, which matters because the failure it prevents cannot be reproduced on
the one we develop on -- ``os.replace`` of a directory onto an empty directory
simply works on Linux.

Publishing a *file* with ``os.replace`` is untouched and legitimate: replacing a
file works identically on every platform, and several editors deliberately
overwrite a previous replacement when an asset is re-edited.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALLOWLISTS = (
    _REPO_ROOT / "packaging" / "release-allowlist.txt",
    _REPO_ROOT / "packaging" / "apf2k8-release-allowlist.txt",
)
_MKDIR_RESERVE = re.compile(r"\.mkdir\(\s*mode\s*=")
_RENAME = re.compile(r"\bos\.(?:replace|rename)\(")
# How far a reserve and its swap may sit apart and still be the same idiom.
_WINDOW = 16


def _shipped_modules() -> list[Path]:
    modules: dict[Path, None] = {}
    for path in sorted((_REPO_ROOT / "mod_editor").rglob("*.py")):
        modules[path] = None
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
                modules[path] = None
    return sorted(modules)


def _hand_rolled_directory_publishes(path: Path) -> list[int]:
    """Lines where a mkdir-reserved name is then renamed onto."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:  # pragma: no cover - defensive
        return []
    found: list[int] = []
    for index, line in enumerate(lines):
        if line.lstrip().startswith("#") or not _MKDIR_RESERVE.search(line):
            continue
        window = "\n".join(
            candidate for candidate in lines[index:index + _WINDOW]
            if not candidate.lstrip().startswith("#")
        )
        if _RENAME.search(window):
            found.append(index + 1)
    return found


class DirectoryPublishPortabilityTests(unittest.TestCase):
    def test_the_scan_covers_the_export_that_broke(self) -> None:
        names = {path.name for path in _shipped_modules()}
        self.assertIn("uniform_bundle.py", names, "the module this bug was in")
        self.assertGreater(len(_shipped_modules()), 100)

    def test_no_shipped_module_hand_rolls_a_directory_publish(self) -> None:
        offences: list[str] = []
        for path in _shipped_modules():
            for lineno in _hand_rolled_directory_publishes(path):
                offences.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}")
        self.assertEqual(
            offences,
            [],
            "A directory is being published by reserving its name with mkdir and "
            "renaming onto it. That is POSIX-only -- Windows cannot rename a "
            "directory onto an existing one and fails with WinError 5. Use "
            "platform_compat.publish_no_replace(..., is_directory=True):\n  "
            + "\n  ".join(offences),
        )

    def test_the_team_kit_export_publishes_through_the_platform_layer(self) -> None:
        source = (_REPO_ROOT / "mod_editor" / "studio" / "uniform_bundle.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "publish_no_replace",
            source,
            "the Team Kit export must publish through platform_compat",
        )
        tree = ast.parse(source)
        directory_publish = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "publish_no_replace"
            and any(
                keyword.arg == "is_directory" and keyword.value.value is True
                for keyword in node.keywords
                if isinstance(keyword.value, ast.Constant)
            )
            for node in ast.walk(tree)
        )
        self.assertTrue(
            directory_publish,
            "the folder export must call publish_no_replace(is_directory=True)",
        )

    def test_the_detector_catches_the_original_shape(self) -> None:
        """Negative control: the pre-fix code must be reported."""
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / "probe.py"
            probe.write_text(
                "import os\n"
                "def publish(stage, requested):\n"
                "    requested.mkdir(mode=0o700)\n"
                "    if not any(requested.iterdir()):\n"
                "        os.replace(stage, requested)\n",
                encoding="utf-8",
                newline="\n",
            )
            self.assertEqual(_hand_rolled_directory_publishes(probe), [3])

    def test_the_detector_leaves_file_publishes_alone(self) -> None:
        """Replacing a FILE is portable and must not be flagged."""
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / "probe.py"
            probe.write_text(
                "import os\n"
                "def commit(staged, destination):\n"
                "    os.replace(staged, destination)\n"
                "def make(root):\n"
                "    root.mkdir(mode=0o700)\n",
                encoding="utf-8",
                newline="\n",
            )
            self.assertEqual(_hand_rolled_directory_publishes(probe), [])


if __name__ == "__main__":
    unittest.main()
