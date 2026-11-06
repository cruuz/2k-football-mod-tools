"""b780 FC2: every repo module the released Studio can import is in packaging/release-allowlist.txt.

ship10's packaged-runtime check (build_archive.py) and REV2S's built tarball found the Studio failing at start with
"ImportError: cannot import name 'nfl2k5_coin_defer_code_b779' from 'mod_editor.core'": seven modules that release
code imports were never allowlisted (the coin_defer, decided_clock and weekly_prep *_code_b779 modules,
historic_teams_quick_game_code_b778, injured_reserve, injured_reserve_code and injured_reserve_save), and an eighth
(tools/b77/b778_fa4_capacity.py) is reached by the allowlisted roster retail fit's validate command.

This test walks the static import closure of every allowlisted non-test Python file and fails on any repo module
outside the allowlist. A dependency is:
- an ``import`` or ``from ... import`` anywhere in the file (module level or inside a function, so runtime-only and
  lazy imports count), absolute or relative, including ``from package import module``;
- a bare top-level import of a tools/ module (the Studio puts tools/ on sys.path, e.g. ``import nfl_txtr``);
- ``importlib.import_module("...")`` and mod_build's ``_core_module("...")`` / ``_tools_module("...")`` with a
  constant name (both return None when the module is missing, so a missing owner silently turns a feature off);
- in mod_build.py and build_steps.py, every string constant that names a mod_editor/core (else tools) nfl2k5_*
  module (the build steps' owner tables load their owners by name);
- a repo .py path handed to a file loader (``spec_from_file_location``, ``run_path``, ``SourceFileLoader``).
Provider ``backend_module`` / ``module_pins`` path strings are pins, not imports; the capability registry gates
providers whose backend is not shipped (packaging/check_build_data_allowlist.py).
The walk continues through a missing module, so a whole missing chain is reported at once. The only modules that may
stay out are EXEMPT, each reached from exactly the importers named there.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("_b780_release_check", ROOT / "packaging/check_2k5_mod_studio_release.py")
release_check = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = release_check
_spec.loader.exec_module(release_check)

ALLOWLIST = ROOT / "packaging/release-allowlist.txt"

#: modules the released 2K5 Studio may name without shipping, and the only allowlisted files allowed to import them
EXEMPT = {
    "mod_editor/apf_studio/__init__.py": (
        {"mod_editor/gui/crash_report.py"},
        "crash_report reads the APF Studio's version inside try/except, only for an APF app name (2K5 reports 'unknown'"
        " otherwise); the APF Studio ships separately"),
    "tools/b77/p13_handoff_probe.py": (
        {"tools/nfl2k5_playbook_lint.py"},
        "playbook_lint's --xbe research option only (since beta-77); the Studio never imports it"),
}
#: the 8 entries b780 FC2 added; the scanner must report exactly these when they are taken out again
B780_FC2_ADDED = {
    "mod_editor/core/nfl2k5_coin_defer_code_b779.py",
    "mod_editor/core/nfl2k5_decided_clock_code_b779.py",
    "mod_editor/core/nfl2k5_weekly_prep_code_b779.py",
    "mod_editor/core/nfl2k5_historic_teams_quick_game_code_b778.py",
    "mod_editor/core/nfl2k5_injured_reserve.py",
    "mod_editor/core/nfl2k5_injured_reserve_code.py",
    "mod_editor/core/nfl2k5_injured_reserve_save.py",
    "tools/b77/b778_fa4_capacity.py",
}
FILE_LOADERS = {"spec_from_file_location", "run_path", "SourceFileLoader", "load_source"}
OWNER_TABLE_FILES = {"mod_editor/core/mod_build.py", "mod_editor/core/build_steps.py"}
OWNER_NAME = re.compile(r"nfl2k5_[a-z0-9_]+")


def _tracked() -> frozenset[str]:
    try:
        listed = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        listed = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.py")]
    return frozenset(p for p in listed if p.endswith(".py"))


TRACKED = _tracked()


def allowed_files(exact: frozenset[str], prefixes: tuple[str, ...]) -> set[str]:
    return {p for p in TRACKED if p in exact or any(p.startswith(prefix) for prefix in prefixes)}


def module_file(name: str) -> str | None:
    base = name.replace(".", "/")
    for candidate in (base + ".py", base + "/__init__.py", f"tools/{base}.py"):   # tools/ is on the Studio's sys.path
        if candidate in TRACKED:
            return candidate
    return None


def _package(path: str) -> str:
    dotted = path[:-3].replace("/", ".")
    return dotted[:-len(".__init__")] if dotted.endswith(".__init__") else dotted.rsplit(".", 1)[0]


def _docstrings(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def dependencies(path: str) -> set[str]:
    """Repo .py files ``path`` can import or load (see the module docstring for what counts)."""
    try:
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    names: set[str] = set()
    package = _package(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                parent = ".".join(parts[:len(parts) - (node.level - 1)] if node.level > 1 else parts)
                module = parent + ("." + node.module if node.module else "")
            else:
                module = node.module or ""
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        first = node.args[0] if node.args else None
        constant = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
        if called == "import_module" and constant:
            names.add(constant)
        elif called == "_core_module" and constant:
            names.add(f"mod_editor.core.{constant}")
        elif called == "_tools_module" and constant:
            names.add(f"tools.{constant}")
        elif called in FILE_LOADERS:
            found.update(c.value for arg in node.args for c in ast.walk(arg)
                         if isinstance(c, ast.Constant) and isinstance(c.value, str) and c.value in TRACKED)
    found |= {f for f in (module_file(name) for name in names) if f}
    if path in OWNER_TABLE_FILES:
        skip = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip \
                    and OWNER_NAME.fullmatch(node.value):
                owner = module_file(f"mod_editor.core.{node.value}") or module_file(f"tools.{node.value}")
                if owner:
                    found.add(owner)
    found.discard(path)
    return {f for f in found if not f.startswith("tests/")}


def missing_modules(allowed: set[str]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """({missing file: importers}, {exempt file: importers}) over the closure of every allowlisted non-test file."""
    missing: dict[str, set[str]] = {}
    exempt: dict[str, set[str]] = {}
    stack = sorted(p for p in allowed if not p.startswith("tests/"))
    seen: set[str] = set()
    while stack:
        path = stack.pop()
        if path in seen:
            continue
        seen.add(path)
        for dep in dependencies(path):
            if dep in EXEMPT:
                exempt.setdefault(dep, set()).add(path)
                continue
            if dep not in allowed:
                missing.setdefault(dep, set()).add(path)
            stack.append(dep)
    return missing, exempt


class ReleaseImportClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        exact, prefixes = release_check.read_allowlist(ALLOWLIST)
        cls.allowed = allowed_files(exact, prefixes)
        cls.missing, cls.exempt = missing_modules(cls.allowed)

    def test_every_module_release_code_imports_is_allowlisted(self):
        self.assertEqual({k: sorted(v) for k, v in self.missing.items()}, {},
                         "release code imports repo modules absent from packaging/release-allowlist.txt")

    def test_exempt_modules_stay_unshipped_and_reached_only_from_their_named_importers(self):
        for path, (importers, reason) in EXEMPT.items():
            with self.subTest(path=path):
                self.assertNotIn(path, self.allowed, f"{path} is now shipped; drop its exemption ({reason})")
                self.assertEqual(self.exempt.get(path, set()), importers,
                                 f"{path} is imported from new release files; the exemption ({reason}) no longer covers it")

    def test_the_scanner_finds_the_eight_fc2_gaps_when_they_are_removed(self):
        self.assertTrue(B780_FC2_ADDED <= self.allowed)
        missing, _ = missing_modules(self.allowed - B780_FC2_ADDED)
        self.assertEqual(set(missing), B780_FC2_ADDED)
        # runtime-only (function-level) imports count: the save module and MyCareer's companion check import the IR
        # owners inside functions, and IR's runtime code is found through the (then missing) IR module itself.
        self.assertIn("mod_editor/core/nfl2k5_franchise_save.py", missing["mod_editor/core/nfl2k5_injured_reserve_save.py"])
        self.assertIn("mod_editor/core/nfl2k5_my_career_mode.py", missing["mod_editor/core/nfl2k5_injured_reserve.py"])
        self.assertEqual(missing["mod_editor/core/nfl2k5_injured_reserve_code.py"], {"mod_editor/core/nfl2k5_injured_reserve.py"})
        self.assertIn("mod_editor/core/mod_build.py", missing["mod_editor/core/nfl2k5_injured_reserve.py"])

    def test_dynamic_loads_and_file_loads_are_dependencies(self):
        build = dependencies("mod_editor/core/mod_build.py")
        self.assertIn("mod_editor/core/nfl2k5_save_list_type_guard.py", build)   # an owner loaded by name
        self.assertIn("tools/nfl2k5_roster_retail_fit.py", dependencies("mod_editor/core/nfl2k5_console_memory.py"))
        self.assertIn("tools/b77/b778_fa3_free_agent_depth.py", dependencies("tools/b77/b778_fa4_capacity.py"))


if __name__ == "__main__":
    unittest.main()
