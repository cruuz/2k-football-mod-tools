"""Shipped code must never write text in a mode Windows will rewrite.

This is the fourth thing to reach real users that our machines cannot produce,
and the most total: it stopped **every** Windows user at the same step, whatever
disc image they had.

``tools/nfl_resource_scan.py`` built the game index with ``Path.write_text()``.
That opens in *text* mode, and on Windows text mode turns every ``\\n`` into
``\\r\\n`` on the way to disk. The index is then required to equal a pinned size
and SHA-256:

    pinned INVENTORY_SIZE        : 55,746,414
    newlines in the index        :  2,289,506
    what Windows actually wrote  : 58,035,920

Identical pack bytes in, a different file out, and the user is told "The
generated game index did not match NFL 2K5" — which sounds like their game is
wrong when nothing about their game is wrong at all. On Linux and macOS text
mode is a no-op, so it was invisible to every test we ran and to CI.

The rule this file enforces is therefore about the *class*, not that one call:
no shipped module may write text without saying what a newline is. Anything
whose bytes are later hashed, size-checked, or byte-compared has to be identical
on every platform, and the only way to guarantee that is to stop letting the C
runtime decide.

Binary writes are unaffected and unrestricted — ``write_bytes``, ``"wb"`` and
``os.write`` never translate anything.
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALLOWLISTS = (
    _REPO_ROOT / "packaging" / "release-allowlist.txt",
    _REPO_ROOT / "packaging" / "apf2k8-release-allowlist.txt",
)


def _shipped_modules() -> list[Path]:
    """Everything that reaches a user: the whole product plus allowlisted tools."""
    modules: dict[Path, None] = {}
    for path in sorted((_REPO_ROOT / "mod_editor").rglob("*.py")):
        modules[path] = None
    for path in sorted((_REPO_ROOT / "packaging").glob("*.py")):
        modules[path] = None
    for allowlist in _ALLOWLISTS:
        if not allowlist.exists():
            continue
        for raw in allowlist.read_text(encoding="utf-8").splitlines():
            entry = raw.strip()
            if (
                not entry.endswith(".py")
                or entry.startswith("tools/vendor/")
                or not entry.startswith("tools/")
            ):
                continue
            path = _REPO_ROOT / entry
            if path.exists():
                modules[path] = None
    return sorted(modules)


def _unguarded_text_writes(path: Path) -> list[tuple[int, str]]:
    """Text-mode writes that let the platform choose the line ending."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
        return []
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        keywords = {keyword.arg for keyword in node.keywords}
        function = node.func
        if isinstance(function, ast.Attribute) and function.attr == "write_text":
            if "newline" not in keywords:
                found.append((node.lineno, "write_text"))
        elif isinstance(function, ast.Name) and function.id == "open":
            mode = None
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = node.args[1].value
            for keyword in node.keywords:
                if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                    mode = keyword.value.value
            if not isinstance(mode, str) or "b" in mode:
                continue          # binary, or a mode we cannot read statically
            if ("w" in mode or "a" in mode or "+" in mode) and "newline" not in keywords:
                found.append((node.lineno, f"open(..., {mode!r})"))
    return found


class GeneratedArtifactsAreLfTests(unittest.TestCase):
    def test_the_scan_covers_the_real_product(self) -> None:
        modules = _shipped_modules()
        self.assertGreater(len(modules), 100, "shipped module set looks too small")
        names = {path.name for path in modules}
        self.assertIn("nfl_resource_scan.py", names, "the module that caused this")
        self.assertIn("nfl2k5_source_cache.py", names)

    def test_no_shipped_module_lets_the_platform_pick_a_line_ending(self) -> None:
        offences: list[str] = []
        for path in _shipped_modules():
            for lineno, kind in _unguarded_text_writes(path):
                offences.append(
                    f"{path.relative_to(_REPO_ROOT)}:{lineno}: {kind}"
                )
        self.assertEqual(
            offences,
            [],
            "Shipped code writes text without pinning the line ending. On Windows "
            'every "\\n" becomes "\\r\\n", so any file later hashed or size-checked '
            'will not match. Pass newline="\\n" (or write bytes):\n  '
            + "\n  ".join(offences),
        )

    def test_the_detector_catches_the_original_defect(self) -> None:
        """Negative control: the exact pre-fix call must be reported."""
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / "probe.py"
            probe.write_text(
                "import json\n"
                "from pathlib import Path\n"
                "def main(path, result):\n"
                '    path.write_text(json.dumps(result, indent=2) + "\\n", encoding="utf-8")\n'
                '    with open("other.txt", "w", encoding="utf-8") as handle:\n'
                '        handle.write("x")\n',
                encoding="utf-8",
                newline="\n",
            )
            found = _unguarded_text_writes(probe)
        self.assertEqual([kind for _, kind in found], ["write_text", "open(..., 'w')"])

    def test_the_detector_accepts_the_repaired_forms(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / "probe.py"
            probe.write_text(
                "from pathlib import Path\n"
                "def main(path, text, payload):\n"
                '    path.write_text(text, encoding="utf-8", newline="\\n")\n'
                '    with open("a.txt", "w", encoding="utf-8", newline="\\n") as h:\n'
                '        h.write(text)\n'
                "    path.write_bytes(payload)\n"
                '    with open("b.bin", "wb") as h:\n'
                "        h.write(payload)\n",
                encoding="utf-8",
                newline="\n",
            )
            self.assertEqual(_unguarded_text_writes(probe), [])


if __name__ == "__main__":
    unittest.main()
