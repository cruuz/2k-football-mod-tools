"""b791 h6-cache: a retry must not recompile 13,000 textures.

Coach Edwards' project stage takes 3.5 to 9 hours. Every build compiled all of it again because the compiled results lived inside the
working-session folder (a new folder each time a project is opened), under keys that held the session's own file paths, and because an
entry counted as valid only while every Python file the compile process had loaded was unchanged (every release changes the version
string and the provider pins). These tests pin the contracts of the replacement (nfl2k5_stage_cache + IndependentUnits +
nfl2k5_compile_cache): where the cache lives, what a key and a code identity cover, that a Studio update which leaves the encoders alone
keeps every result and an encoder change replaces exactly the results it can change, that a stale result cannot slip through (the canary),
that a build never evicts what it is using, and that a cache hit writes the bytes a cold compile writes.

Synthetic repositories and the b661 synthetic disc; no retail bytes. The last class runs the real compile on real bytes when the private
inputs are present (B791_H6_PROJECT_JSON, B791_H6_INDEX, B791_H6_INVENTORY) and is skipped otherwise.
"""
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).parent), str(ROOT / "tools" / "b77")]
from mod_editor.core import nfl2k5_stage_cache as stage_cache  # noqa: E402
from mod_editor.core.nfl2k5_compile_cache import CompileCache  # noqa: E402
from test_b774_fast_units import Harness, backend  # noqa: E402

TOOL = ROOT / "tools/nfl2k5_visual_mod_project.py"


def write_tree(root: Path, files: dict) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
    return root


class Repo(unittest.TestCase):
    """A synthetic repository: tools/ is on the path, mod_editor/core is a package."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()

    def identity(self, *roots, **options):
        return stage_cache.CodeIdentity(self.root).identity(roots, **options)


class CodeIdentityTests(Repo):
    def test_the_closure_follows_every_kind_of_import_and_nothing_else(self):
        write_tree(self.root, {
            "tools/a.py": ('import b\nfrom c import thing\nimport os, json\n'
                           'ADAPTER = "mod_editor/core/adapter.py"\nDATA = "mod_editor/data/table.json"\n'
                           'HELPER = "tools/helper_bin"\nREPORT = "reports/assets/r.json"\n'
                           'def f():\n    import lazy_mod\n    return lazy_mod\n'),
            "tools/b.py": "VALUE = 1\n", "tools/c.py": "thing = 2\n", "tools/lazy_mod.py": "X = 3\n",
            "tools/never.py": "import nothing_imports_this\n", "tools/helper_bin": b"\x7fELF",
            "mod_editor/__init__.py": '__version__ = "1"\nfrom .core.world import World\n',
            "mod_editor/core/__init__.py": "from .world import World\n",
            "mod_editor/core/world.py": "class World: ...\n",
            "mod_editor/core/adapter.py": "A = 1\n",
            "mod_editor/core/x.py": ("from . import y\nfrom .z import q\nfrom mod_editor.core import w\n"
                                     "from mod_editor.core.v import thing\n"),
            "mod_editor/core/y.py": "Y = 1\n", "mod_editor/core/z.py": "q = 1\n", "mod_editor/core/w.py": "W = 1\n",
            "mod_editor/core/v.py": "thing = 1\n",
            "mod_editor/data/table.json": '{"rows": []}',
            "reports/assets/r.json": "{}",
        })
        modules, data = stage_cache.CodeIdentity(self.root).closure(["tools/a.py", "mod_editor/core/x.py"])
        self.assertEqual(modules, (
            "mod_editor/core/adapter.py", "mod_editor/core/v.py", "mod_editor/core/w.py", "mod_editor/core/x.py",
            "mod_editor/core/y.py", "mod_editor/core/z.py", "tools/a.py", "tools/b.py", "tools/c.py", "tools/lazy_mod.py"))
        # Package re-export files carry the version and import the world; a report a module names is data it reads.
        self.assertEqual(data, ("mod_editor/data/table.json", "reports/assets/r.json", "tools/helper_bin"))

    def test_comments_docstrings_and_whitespace_do_not_count_but_code_does(self):
        write_tree(self.root, {"tools/m.py": '"""Doc."""\n# comment\ndef f(x):\n    """Why."""\n    return x + 1\n'})
        before = self.identity("tools/m.py")
        write_tree(self.root, {"tools/m.py": '"""A different doc."""\n\n\n# another comment\ndef f(x):\n'
                                             '    """Another why."""\n\n    return x   +   1\n'})
        self.assertEqual(self.identity("tools/m.py"), before)
        write_tree(self.root, {"tools/m.py": '"""Doc."""\ndef f(x):\n    return x + 2\n'})
        self.assertNotEqual(self.identity("tools/m.py"), before)

    def test_a_change_in_an_imported_file_counts_and_an_unrelated_file_does_not(self):
        write_tree(self.root, {"tools/root.py": "import dep\n", "tools/dep.py": "V = 1\n", "tools/other.py": "V = 1\n"})
        before = self.identity("tools/root.py")
        write_tree(self.root, {"tools/other.py": "V = 2\n"})
        self.assertEqual(self.identity("tools/root.py"), before)
        write_tree(self.root, {"tools/dep.py": "V = 2\n"})
        after = self.identity("tools/root.py")
        self.assertNotEqual(after, before)
        self.assertEqual(stage_cache.changed_files(before, after), ["tools/dep.py"])

    def test_a_leaf_counts_by_its_own_source_and_what_it_imports_does_not(self):
        write_tree(self.root, {"tools/root.py": "V = 1\n", "tools/plumbing.py": "import deep\nP = 1\n", "tools/deep.py": "D = 1\n"})
        before = self.identity("tools/root.py", leaves=("tools/plumbing.py",))
        self.assertEqual(sorted(before["modules"]), ["tools/plumbing.py", "tools/root.py"])
        write_tree(self.root, {"tools/deep.py": "D = 2\n"})
        self.assertEqual(self.identity("tools/root.py", leaves=("tools/plumbing.py",)), before)
        write_tree(self.root, {"tools/plumbing.py": "import deep\nP = 2\n"})
        self.assertNotEqual(self.identity("tools/root.py", leaves=("tools/plumbing.py",)), before)
        self.assertIsNone(self.identity("tools/root.py", leaves=("tools/missing.py",)))     # a leaf that cannot be read: no cache

    def test_a_data_file_the_code_names_counts(self):
        write_tree(self.root, {"tools/root.py": 'PATH = "mod_editor/data/t.json"\n', "mod_editor/data/t.json": "[1]"})
        before = self.identity("tools/root.py")
        write_tree(self.root, {"mod_editor/data/t.json": "[2]"})
        after = self.identity("tools/root.py")
        self.assertEqual(stage_cache.changed_files(before, after), ["mod_editor/data/t.json"])

    def test_a_file_that_cannot_be_read_or_parsed_means_no_identity_and_so_no_cache(self):
        write_tree(self.root, {"tools/root.py": "import broken\nimport dep\n", "tools/dep.py": "V = 1\n"})
        self.assertIsNotNone(self.identity("tools/root.py"))
        write_tree(self.root, {"tools/broken.py": "def (:\n"})
        self.assertIsNone(self.identity("tools/root.py"))
        self.assertIsNone(self.identity("tools/does_not_exist.py"))

    def test_the_python_minor_version_is_part_of_the_identity(self):
        write_tree(self.root, {"tools/root.py": "V = 1\n"})
        identity = self.identity("tools/root.py")
        self.assertEqual(identity["python"], f"{sys.version_info[0]}.{sys.version_info[1]}")
        self.assertEqual(stage_cache.changed_files(dict(identity, python="2.7"), identity), ["(python)"])

    def test_the_dispatch_digest_counts_only_what_the_entry_points_reach_by_name(self):
        tool = ('import sys\nLIMIT = 5\nOTHER = 9\n\n'
                'def helper(x):\n    return x + LIMIT\n\n'
                'def unit(x):\n    return helper(x)\n\n'
                'def unrelated(x):\n    return OTHER\n\n'
                'class Thing:\n    value = LIMIT\n\n'
                'def uses_thing():\n    return Thing\n\n'
                'if __name__ == "__main__":\n    unit(1)\n')
        write_tree(self.root, {"tools/tool.py": tool})

        def digest():
            return stage_cache.CodeIdentity(self.root).dispatch_digest("tools/tool.py", ["unit"])
        base = digest()
        self.assertIsNotNone(base)
        write_tree(self.root, {"tools/tool.py": tool.replace("return OTHER", "return OTHER + 1")})
        self.assertEqual(digest(), base, "an unreached function changed")
        write_tree(self.root, {"tools/tool.py": tool.replace("OTHER = 9", "OTHER = 10")})
        self.assertEqual(digest(), base, "an unreached constant changed")
        write_tree(self.root, {"tools/tool.py": tool.replace("x + LIMIT", "x + LIMIT + 1")})
        self.assertNotEqual(digest(), base)
        write_tree(self.root, {"tools/tool.py": tool.replace("LIMIT = 5", "LIMIT = 6")})
        self.assertNotEqual(digest(), base, "a reached constant changed")
        write_tree(self.root, {"tools/tool.py": tool.replace("unit(1)", "unit(2)")})
        self.assertEqual(digest(), base, "the __main__ block is not import-time")
        self.assertIsNone(stage_cache.CodeIdentity(self.root).dispatch_digest("tools/tool.py", ["not_there"]))

    def test_helpers_that_only_word_a_failure_can_be_left_out(self):
        tool = ('def describe(x):\n    return f"edit {x}"\n\n'
                'def helper(x):\n    return x + 1\n\n'
                'def unit(x):\n    try:\n        return helper(x)\n    except ValueError as exc:\n'
                '        raise RuntimeError(describe(x)) from exc\n')
        write_tree(self.root, {"tools/tool.py": tool})

        def digest(ignore=()):
            return stage_cache.CodeIdentity(self.root).dispatch_digest("tools/tool.py", ["unit"], ignore)
        everything, quiet = digest(), digest(["describe"])
        self.assertNotEqual(everything, quiet)
        write_tree(self.root, {"tools/tool.py": tool.replace('f"edit {x}"', 'f"edit number {x}"')})
        self.assertNotEqual(digest(), everything, "counted when not ignored")
        self.assertEqual(digest(["describe"]), quiet, "a better message keeps every saved result")
        write_tree(self.root, {"tools/tool.py": tool.replace("x + 1", "x + 2")})
        self.assertNotEqual(digest(["describe"]), quiet, "the code that decides the result still counts")

    def test_statements_that_run_when_the_tool_is_imported_always_count(self):
        tool = 'import sys\nsys.path.insert(0, "x")\nREADY = []\n\ndef unit():\n    return 1\n'
        write_tree(self.root, {"tools/tool.py": tool})
        base = stage_cache.CodeIdentity(self.root).dispatch_digest("tools/tool.py", ["unit"])
        write_tree(self.root, {"tools/tool.py": tool.replace('"x"', '"y"')})
        self.assertNotEqual(stage_cache.CodeIdentity(self.root).dispatch_digest("tools/tool.py", ["unit"]), base)

    def test_changed_files_says_what_differs(self):
        old = {"python": "3.12", "modules": {"a.py": "1", "b.py": "2"}, "data": {"d.json": "3"}, "dispatch": "x"}
        new = {"python": "3.12", "modules": {"a.py": "1", "b.py": "9", "c.py": "4"}, "data": {"d.json": "3"}, "dispatch": "y"}
        self.assertEqual(stage_cache.changed_files(old, new), ["b.py", "c.py", "(dispatch)"])
        self.assertEqual(stage_cache.changed_files(old, old), [])
        self.assertEqual(stage_cache.changed_files(None, new), ["(unknown)"])


class RealRepositoryTests(unittest.TestCase):
    """The identities of the real unit kinds: complete, small, and blind to the version string and the provider pins."""

    @classmethod
    def setUpClass(cls):
        cls.tool = backend()
        cls.index = stage_cache.CodeIdentity(ROOT)

    def identity(self, kind):
        return self.index.identity(self.tool._UNIT_CODE_ROOTS[kind], tool=self.tool._UNIT_DISPATCH[0],
                                   entry_points=self.tool._UNIT_DISPATCH[1], ignore=self.tool._UNIT_DISPATCH_WORDING,
                                   leaves=self.tool._UNIT_PLUMBING)

    def test_every_unit_kind_has_an_identity_that_ignores_what_every_release_changes(self):
        self.assertEqual(set(self.tool._UNIT_CODE_ROOTS), set(self.tool.UNIT_KINDS))
        for kind in sorted(self.tool.UNIT_KINDS):
            identity = self.identity(kind)
            self.assertIsNotNone(identity, kind)
            self.assertLess(len(identity["modules"]), 40, kind)
            for forbidden in ("mod_editor/__init__.py", "mod_editor/core/__init__.py", "mod_editor/core/providers.py",
                              "tools/nfl2k5_visual_mod_project.py", "mod_editor/core/nfl2k5_build_service.py",
                              "mod_editor/core/mod_build.py", "mod_editor/core/platform_compat.py"):
                self.assertNotIn(forbidden, identity["modules"], f"{kind}: {forbidden}")
            self.assertTrue(identity["dispatch"])

    def test_the_package_init_files_only_re_export_so_skipping_them_is_sound(self):
        for name in ("mod_editor/__init__.py", "mod_editor/core/__init__.py"):
            tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
            for node in tree.body:
                allowed = isinstance(node, (ast.Import, ast.ImportFrom)) or (
                    isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)) or (
                    isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and t.id in {"__version__", "__all__"}
                                                         for t in node.targets))
                self.assertTrue(allowed, f"{name} line {node.lineno} does more than re-export")

    def test_the_helmets_and_the_digits_do_not_depend_on_the_equipment_stadium_or_crib_code(self):
        for kind in ("live_helmet", "live_number_nameplate", "team_select", "torso"):
            for name in self.identity(kind)["modules"]:
                for foreign in ("equipment", "stadium", "crib"):
                    self.assertNotIn(foreign, name, f"{kind}: {name}")

    def test_the_table_covers_every_module_the_tool_calls_for_each_kind(self):
        """Pin _UNIT_CODE_ROOTS to the tool's own dispatch: the modules a kind's branch of build_one_import (or the portrait,
        P8 and kept-retail builders) reaches through a module alias must be inside the kind's identity."""
        tree = ast.parse(TOOL.read_text(encoding="utf-8"))
        constants = {}
        aliases = {}
        loader_files = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                    and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                constants[node.targets[0].id] = node.value.value
            if isinstance(node, ast.Import):
                for alias in node.names:
                    aliases[alias.asname or alias.name.split(".")[0]] = self.index._module_file(alias.name.split("."))
            if isinstance(node, ast.ImportFrom):
                parts = node.module.split(".") if node.module else []
                for alias in node.names:
                    aliases[alias.asname or alias.name] = self.index._module_file(parts + [alias.name])
            if isinstance(node, ast.FunctionDef) and node.name.startswith("_load_") and node.name.endswith("_adapter"):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and sub.value.endswith(".py"):
                        loader_files[node.name] = sub.value
        for node in tree.body:     # p8_texture_adapter = _load_p8_texture_adapter()
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                    and getattr(node.value.func, "id", "") in loader_files:
                aliases[node.targets[0].id] = loader_files[node.value.func.id]
        functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}

        def used(nodes):
            found = set()
            for node in nodes:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and aliases.get(sub.id):
                        found.add(aliases[sub.id])
            return found

        def kinds_of(test):
            kinds = set()
            for sub in ast.walk(test):
                if isinstance(sub, ast.Compare) and isinstance(sub.left, ast.Name) and sub.left.id == "kind":
                    for comparator in sub.comparators:
                        for item in (comparator.elts if isinstance(comparator, ast.Set) else [comparator]):
                            if isinstance(item, ast.Constant):
                                kinds.add(item.value)
                            elif isinstance(item, ast.Name) and item.id in constants:
                                kinds.add(constants[item.id])
            return kinds

        branches: dict[str, set] = {}
        for statement in functions["build_one_import"].body:
            if isinstance(statement, ast.If):
                for kind in kinds_of(statement.test):
                    branches.setdefault(kind, set()).update(used(statement.body))    # not the elif chain behind it
        branches.setdefault("player_portrait", set()).update(used([functions["build_player_portrait_imports"]]))
        branches.setdefault(self.tool.P8_TEXTURE_KIND, set()).update(used([functions["_build_p8_unit"]]))
        branches.setdefault("live_number_nameplate", set()).update(used([functions["kept_retail_record"]]))
        for kind in sorted(self.tool.UNIT_KINDS):
            self.assertIn(kind, branches, f"{kind}: no branch found in the dispatch (did it move?)")
            self.assertTrue(branches[kind], kind)
            covered = set(self.identity(kind)["modules"])
            self.assertEqual(sorted(branches[kind] - covered), [], f"{kind}: the dispatch calls modules its identity lacks")


class StageRootTests(unittest.TestCase):
    def test_the_cache_sits_beside_the_private_source_cache(self):
        class Cache:
            root = Path("/cache/2k5-mod-studio/0123abcd")
        self.assertEqual(stage_cache.stage_cache_root(Cache, {}), Path("/cache/2k5-mod-studio/project-stage"))
        self.assertEqual(stage_cache.stage_cache_root(Cache, {"NFL2K5_PROJECT_STAGE_CACHE_ROOT": "/elsewhere"}),
                         Path("/elsewhere"))
        self.assertIsNone(stage_cache.stage_cache_root(None, {}))
        self.assertIsNone(stage_cache.stage_cache_root(object(), {"NFL2K5_PROJECT_STAGE_CACHE_ROOT": "  "}))

    def test_the_size_cap_is_three_gib_unless_the_usual_switch_is_set(self):
        self.assertEqual(stage_cache.stage_cache_max_bytes({}), 3 * 1024 ** 3)
        self.assertEqual(stage_cache.stage_cache_max_bytes({"NFL2K5_COMPILE_CACHE_MAX_MB": "200"}), 200 * 1024 ** 2)
        self.assertEqual(stage_cache.stage_cache_max_bytes({"NFL2K5_COMPILE_CACHE_MAX_MB": "  "}), 3 * 1024 ** 3)
        self.assertEqual(stage_cache.stage_cache_max_bytes({"NFL2K5_COMPILE_CACHE_MAX_MB": "lots"}), 3 * 1024 ** 3)

    def test_edit_shape_drops_every_field_that_names_a_file(self):
        edit = {"kind": "torso", "asset_code": "18", "clean_png": "/s/1/a.png", "mud_png": None, "png": "/s/1/b.png",
                "wav": "w", "recipe": "r", "side": "H"}
        self.assertEqual(stage_cache.edit_shape(edit), {"kind": "torso", "asset_code": "18", "side": "H"})


class EvictionTests(unittest.TestCase):
    def test_a_build_never_evicts_what_it_is_using_and_older_entries_go_first(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "cache"
            older = CompileCache(root)
            for number in range(4):
                older.put("%064x" % number, {"blob": "x" * 2000})
            entry = older._bytes // 4
            build = CompileCache(root, max_bytes=entry * 6, protect_used=True)
            self.assertIsNotNone(build.get("%064x" % 3))                        # in use by this build
            for number in range(10, 18):                                         # this build compiles eight more
                build.put("%064x" % number, {"blob": "x" * 2000})
            names = sorted(path.stem for path in root.glob("*.json"))
            self.assertEqual(names, ["%064x" % n for n in [3] + list(range(10, 18))],
                             "the entries this build read or wrote stay, even though the cap is smaller than they are")
            # The next build starts clean: its own entries are protected, the previous build's are not.
            after = CompileCache(root, max_bytes=entry * 6, protect_used=True)
            after.put("%064x" % 99, {"blob": "x" * 2000})
            self.assertEqual(len(list(root.glob("*.json"))), 6)
            self.assertIsNotNone(after.get("%064x" % 99))

    def test_without_protection_the_oldest_entry_is_evicted_exactly_as_before(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "cache"
            cache = CompileCache(root, max_bytes=3000)
            for number in range(5):
                cache.put("%064x" % number, {"blob": "x" * 1000})
            self.assertLessEqual(sum(p.stat().st_size for p in root.glob("*.json")), 3000)
            self.assertIsNone(CompileCache(root).get("%064x" % 0))
            self.assertIsNotNone(CompileCache(root).get("%064x" % 4))

    def test_a_cache_full_of_protected_entries_does_not_rescan_for_every_write(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = CompileCache(Path(folder) / "c", max_bytes=1, protect_used=True)
            for number in range(300):
                cache.put("%064x" % number, {"blob": number})
            self.assertEqual(len(list((Path(folder) / "c").glob("*.json"))), 300)
            self.assertTrue(cache._all_in_use)


class UnitCacheContracts(unittest.TestCase):
    def setUp(self):
        self.tool = backend()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name).resolve()
        (self.base / "one").mkdir()
        self.harness = Harness(self.tool, self.base / "one")
        self.cache = CompileCache(self.base / "cache", protect_used=True)

    def second_session(self, name="two", **options):
        """The same project opened again: the same bytes in a new folder, which holds its own copy of the compile source."""
        folder = self.base / name
        folder.mkdir()
        return Harness(self.tool, folder, **options)

    def test_a_reopened_project_in_another_folder_hits_what_the_first_session_stored(self):
        with self.harness.patched():
            self.harness.run(self.cache)
            first_calls = len(self.harness.calls)
        again = self.second_session()
        with again.patched():
            units, results = again.run(CompileCache(self.base / "cache", protect_used=True))
        self.assertEqual((units.hits, units.misses), (6, 0))
        self.assertEqual(again.calls, [], "the new session compiled something the first one had stored")
        self.assertGreater(first_calls, 0)
        self.assertEqual(dict(units.reasons), {})

    def test_the_key_names_no_file_and_no_folder(self):
        again = self.second_session()
        one, two = self.harness.units(CompileCache(None)), again.units(CompileCache(None))
        for number in range(6):
            self.assertEqual(one.key(number), two.key(number))
        self.assertNotIn(str(self.base), json.dumps(one._context, default=str))

    def test_another_kind_of_edit_in_the_project_does_not_change_a_units_key(self):
        units = self.harness.units(CompileCache(None))
        before = units.key(0)
        units._context["reports"] = dict(units._context["reports"], torso="e" * 64, team_select="f" * 64)
        self.assertEqual(units.key(0), before)
        units._context["reports"] = dict(units._context["reports"], live_face="0" * 64)
        self.assertNotEqual(units.key(0), before)

    def test_a_release_that_leaves_the_encoders_alone_keeps_every_result(self):
        with self.harness.patched():
            self.harness.run(self.cache)
            (self.base / "one/code/unrelated.py").write_text("UNRELATED = 'a release changed this'\n", encoding="utf-8", newline="\n")
            (self.base / "one/code/version.py").write_text("__version__ = 'rc115'\n", encoding="utf-8", newline="\n")
            units, _ = self.harness.run(self.cache)
        self.assertEqual((units.hits, units.misses), (6, 0))

    def test_an_encoder_change_replaces_exactly_the_kinds_it_can_change(self):
        card = self.second_session("cards", count=6, kind="team_select")
        table = {"live_face": ("code/loaded.py",), "team_select": ("code/card.py",)}
        (self.base / "cards/code/card.py").write_text("CARD = 1\n", encoding="utf-8", newline="\n")
        (self.base / "one/code/card.py").write_text("CARD = 1\n", encoding="utf-8", newline="\n")
        with self.harness.patched(table), card.patched(table):
            self.harness.run(self.cache)
            card.run(self.cache)
            self.assertEqual((self.harness.run(self.cache)[0].hits, card.run(self.cache)[0].hits), (6, 6))
            (self.base / "cards/code/card.py").write_text("CARD = 2\n", encoding="utf-8", newline="\n")
            (self.base / "one/code/card.py").write_text("CARD = 2\n", encoding="utf-8", newline="\n")
            faces, _ = self.harness.run(self.cache)
            cards, _ = card.run(self.cache)
        self.assertEqual((faces.hits, faces.misses), (6, 0), "the face encoder did not change")
        self.assertEqual((cards.hits, cards.misses), (0, 6), "the card encoder did")
        self.assertEqual(dict(cards.reasons), {"compiler code changed": 6})
        self.assertEqual(dict(cards.changed_code), {"code/card.py": 6})

    def test_a_kind_with_no_identity_is_never_cached(self):
        with self.harness.patched(), patch.object(self.tool, "_UNIT_CODE_ROOTS", {}):
            units, _ = self.harness.run(self.cache)
            units, _ = self.harness.run(self.cache)
        self.assertEqual((units.hits, units.misses), (0, 0))
        self.assertEqual(list((self.base / "cache").glob("*.json")), [])

    def test_why_a_result_was_compiled_again_is_counted(self):
        with self.harness.patched():
            cold, _ = self.harness.run(self.cache)
            (self.base / "one/code/loaded.py").write_text("LOADED = 2\n", encoding="utf-8", newline="\n")
            changed, _ = self.harness.run(self.cache)
            first = next((self.base / "cache").glob("*.json"))
            first.write_bytes(b"damaged")
            damaged, _ = self.harness.run(self.cache)
        self.assertEqual(dict(cold.reasons), {"no usable earlier result": 6})
        self.assertEqual(dict(changed.reasons), {"compiler code changed": 6})
        self.assertEqual(dict(changed.changed_code), {"code/loaded.py": 6})
        self.assertEqual(dict(damaged.reasons), {"no usable earlier result": 1})   # the envelope check cannot tell absent from damaged
        self.assertEqual(cold.plain_summary(), [])      # a first build has nothing to say about reuse
        self.assertEqual(changed.plain_summary(), ["Compiled 6 textures: 6 because the studio's encoder changed (loaded.py)"])
        self.assertEqual(damaged.plain_summary(), ["Reused 5 of 6 compiled textures from earlier builds",
                                                   "Compiled 1 texture: 1 new or changed artwork"])
        # The files a change is named by are plain words in the build log, never a bracketed internal token.
        changed.changed_code.clear()
        changed.changed_code.update({"(dispatch)": 4, "(python)": 1, "(unknown)": 1})
        self.assertEqual(changed.plain_summary(), [
            "Compiled 6 textures: 6 because the studio's encoder changed "
            "(the project builder, the Python version, an older saved format)"])
        changed.changed_code.clear()
        changed.changed_code.update({"code/loaded.py": 6})
        summary = changed.summary()
        self.assertEqual(summary["misses_by_kind"], {"live_face": 6})
        self.assertGreater(summary["stored_bytes_by_kind"]["live_face"], 0)
        json.dumps(summary)     # it is printed as one JSON line for the build log

    def test_a_compile_that_imports_something_its_identity_does_not_list_is_not_remembered(self):
        with self.harness.patched():
            units = self.harness.units(self.cache)
            try:
                value = self.harness.fake_compile("live_face", 0, self.harness.project.value["edits"][0],
                                                  self.harness.project, self.harness.pins, {}, None, None,
                                                  SimpleNamespace(path=self.base), [])[1]
                key = units.key(0)
                units._remember(key, "ok", value, "live_face", imported=("code/surprise.py",))
                self.assertEqual(list((self.base / "cache").glob("*.json")), [])
                self.assertEqual(dict(units.reasons), {"not remembered: imports its identity does not list": 1})
                self.assertEqual(dict(units.unlisted), {"code/surprise.py": 1})
                self.assertEqual(dict(units.changed_code), {})
                # What the identity lists, and a package __init__ (it only re-exports), are not a surprise.
                units._remember(key, "ok", value, "live_face", imported=("code/loaded.py", "code/__init__.py"))
                self.assertEqual(len(list((self.base / "cache").glob("*.json"))), 1)
            finally:
                units.close()

    def test_a_worker_reports_only_what_this_compile_imported_for_the_first_time(self):
        calls = iter([("code/loaded.py", "tools/early.py"), ("code/loaded.py", "tools/early.py", "tools/late.py")])
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(self.tool, "_unit_compile", return_value=("ok", [])), \
                patch.object(self.tool, "_loaded_code_files", side_effect=lambda: next(calls)):
            outcome, value, imported, console = self.tool._unit_worker(
                ("live_face", 0, {"kind": "live_face"}, None, {}, {}, Path(folder), Path(folder), Path(folder)))
        self.assertEqual((outcome, imported), ("ok", ("tools/late.py",)))


class GroupResultTests(unittest.TestCase):
    """A saved result of a grouped compile (equipment, stadium, crib) names the files of the session that made it."""

    def setUp(self):
        self.tool = backend()

    def test_the_saved_effective_edit_is_pointed_at_this_projects_own_files(self):
        saved = ("built", {"kind": "uniform_equipment_texture", "tset": "t:1:2",
                           "edits": [{"target": "a", "png": "/old/session/a.png"}, {"target": "b", "png": "/old/session/b.png"}]},
                 {"a": "1" * 64}, "uniform_equipment_texture", ["/old/session/a.png", "/old/session/b.png"])
        built, effective, hashes, kind = self.tool._repathed(saved, ["/new/s/a.png", "/new/s/b.png"])
        self.assertEqual((built, hashes, kind), ("built", {"a": "1" * 64}, "uniform_equipment_texture"))
        self.assertEqual(effective["edits"], [{"target": "a", "png": "/new/s/a.png"}, {"target": "b", "png": "/new/s/b.png"}])
        self.assertEqual(effective["tset"], "t:1:2")

    def test_a_record_that_cannot_say_which_files_it_used_or_would_be_ambiguous_is_not_used(self):
        edit = {"kind": "k", "edits": [{"png": "/old/a.png"}]}
        self.assertIsNone(self.tool._repathed(("built", edit, {}, "k"), ["/new/a.png"]))                    # the older record shape
        self.assertIsNone(self.tool._repathed(("built", edit, {}, "k", ["/old/a.png"]), []))                # a different group
        self.assertIsNone(self.tool._repathed(("built", edit, {}, "k", ["/old/a.png", "/old/a.png"]),
                                              ["/new/a.png", "/new/b.png"]))                               # one name, two files
        self.assertIsNone(self.tool._repathed(None, ["/new/a.png"]))
        # The same file used twice maps to the same file twice: fine.
        self.assertIsNotNone(self.tool._repathed(("built", edit, {}, "k", ["/old/a.png", "/old/a.png"]),
                                                 ["/new/a.png", "/new/a.png"]))

    def test_group_paths_follow_the_order_the_key_reads_them(self):
        project = SimpleNamespace(value={"edits": [
            {"kind": "torso", "clean_png": "c0", "mud_png": None, "png": None},
            {"kind": "stadium_geometry", "recipe": "r1"},
            {"kind": "x", "png": "p2", "recipe": "r2"}]})
        self.assertEqual(self.tool._group_paths(project, [0, 1, 2]), ["c0", "r1", "p2", "r2"])


class CanaryTests(unittest.TestCase):
    def setUp(self):
        self.tool = backend()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name).resolve()
        (self.base / "one").mkdir()
        self.harness = Harness(self.tool, self.base / "one", count=8)
        self.cache = CompileCache(self.base / "cache", protect_used=True)

    def test_good_entries_pass_and_are_counted(self):
        with self.harness.patched():
            self.harness.run(self.cache)
            calls = len(self.harness.calls)
            units = self.harness.units(self.cache)
            try:
                report = units.canary()
            finally:
                units.close()
        self.assertEqual(report, {"checked": 2, "mismatched": []})
        self.assertTrue(units.trusted)
        self.assertEqual(len(self.harness.calls), calls + 2, "the canary compiles exactly the units it checks")

    def test_a_check_that_cannot_run_costs_the_saved_results_never_the_build(self):
        with self.harness.patched():
            self.harness.run(self.cache)
            units = self.harness.units(self.cache)
            try:
                with patch.object(units, "_task", side_effect=RuntimeError("boom")):
                    report = units.canary()                      # does not raise
                self.assertFalse(units.trusted)
                self.assertEqual(report, {"checked": 1, "mismatched": [], "error": "RuntimeError: boom"})
                self.assertIsNone(units._recall(units.key(0), "live_face"), "nothing saved is used for the rest of this build")
                self.assertEqual(dict(units.reasons), {"the check of saved results could not run": 1})
                units.misses = 3
                self.assertEqual(units.plain_summary(), [
                    "Compiled 3 textures: the check of the saved results could not run, so none were used"])
            finally:
                units.close()

    def test_nothing_is_checked_on_a_cold_cache_or_without_a_cache(self):
        with self.harness.patched():
            for cache in (self.cache, CompileCache(None)):
                units = self.harness.units(cache)
                try:
                    self.assertEqual(units.canary(), {"checked": 0, "mismatched": []})
                finally:
                    units.close()
            self.harness.run(self.cache)
            units = self.harness.units(self.cache)
            try:
                self.assertEqual(units.canary(per_kind=0), {"checked": 0, "mismatched": []})
            finally:
                units.close()

    def test_a_stale_result_the_key_could_not_see_is_caught_and_replaced(self):
        original = self.harness.fake_compile

        def newer(kind, order, edit, project, pins, report_paths, index, inventory, temp_root, temp_files):
            outcome, built = original(kind, order, edit, project, pins, report_paths, index, inventory, temp_root, temp_files)
            span, previews, report, selector, target = built[0]
            return outcome, [(b"NEWER" + span, previews, report, selector, target)]

        with self.harness.patched():
            self.harness.run(self.cache)                   # stored with the old encoder, under keys that will not change
            with patch.object(self.tool, "_unit_compile", side_effect=newer):
                units = self.harness.units(self.cache)
                try:
                    report = units.canary()
                    self.assertFalse(units.trusted)
                    self.assertEqual(len(report["mismatched"]), 1)
                    self.assertIn("a cached result differed from a fresh compile", units.reasons)
                    # Nothing cached is used for the rest of the build: every unit compiles with the new encoder.
                    results = [units.take(number, number) for number in range(8)]
                finally:
                    units.close()
                self.assertEqual((units.hits, units.misses), (0, 8))
                self.assertTrue(all(row[1][0][0].startswith(b"NEWER") for row in results))
            # The stale entries were replaced by the fresh results, so the next build trusts them and hits.
            again, rerun = self.harness.run(self.cache)
        self.assertEqual((again.hits, again.misses), (8, 0))
        self.assertTrue(all(row[1][0][0].startswith(b"NEWER") for row in rerun))

    def test_a_fresh_compile_that_now_fails_counts_as_a_difference(self):
        with self.harness.patched():
            self.harness.run(self.cache)
            with patch.object(self.tool, "_unit_compile", side_effect=ValueError("the encoder refuses it now")):
                units = self.harness.units(self.cache)
                try:
                    report = units.canary()
                finally:
                    units.close()
        self.assertFalse(units.trusted)
        self.assertTrue(report["mismatched"])


class FixtureBuildTests(unittest.TestCase):
    """The real backend on the b661 synthetic disc: a cache hit writes the bytes a cold compile writes."""

    def setUp(self):
        import b661_build_fixture as fixture
        self.fixture = fixture
        folder = tempfile.TemporaryDirectory(prefix="b791-h6-")
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name).resolve()
        self.tool = backend()
        # The fixture points the shared importer modules at its synthetic disc; put them back afterwards so a test that
        # compiles real bytes in the same process (RealBytesTests) sees the real targets.
        for owner, name in ((self.tool.jersey_targets, "select_target"), (self.tool.jersey_import, "select_target"),
                            (self.tool.common, "EXPECTED_XBE_SIZE"), (self.tool.common, "EXPECTED_XBE_SHA256")):
            patcher = patch.object(owner, name, getattr(owner, name))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.session_one = self.session("one")
        fixture.configure(self.tool, self.base / "one")
        self.cache_root = self.base / "stage-cache"

    def session(self, name):
        from nfl_txtr import encode_rgba_png
        root = self.base / name
        root.mkdir()
        equipment, _ = self.fixture.create(root)
        asset, png = equipment.png(independent=False, rgba=bytes((20, 150, 80, 255)) * 1024)
        torso = root / "jersey.png"
        torso.write_bytes(encode_rgba_png(512, 256, bytes((20, 190, 220, 255)) * (512 * 256)))
        return root, asset, png, torso

    def project(self, session, name="project.json"):
        root, asset, png, torso = session
        path = root / name
        path.write_bytes(self.tool.canonical_json(dict(schema=self.tool.SCHEMA, purpose="b791 h6 cache", edits=[
            dict(kind="torso", asset_code="18", side="H", variant=0, clean_png=str(torso), mud_png=None, mud_mode="darken_60"),
            dict(kind=self.tool.UNIFORM_EQUIPMENT_KIND, asset_id=asset, png=str(png))])))
        return path

    def prepare(self, project_path, root, *, use_cache=True):
        tool = self.tool
        project = tool.read_project(project_path)
        reports = tool.pin_reports({edit["kind"] for edit in project.value["edits"]})
        index_pin = tool.ownership.pin_large_file(root / "0", "pack", tool.INDEX_SIZE, tool.INDEX_SHA256)
        inventory_pin = tool.ownership.pin_large_file(root / "inventory.json", "inventory",
                                                      tool.INVENTORY_SIZE, tool.INVENTORY_SHA256)
        source = root / "source.iso"
        descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            entries, _ = tool.common.parse_xdvdfs(descriptor, source.stat().st_size)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                prepared = tool.prepare_project(project, index_pin, inventory_pin, reports, root, descriptor, entries,
                                                None, None, None, compile_cache_root=self.cache_root,
                                                use_compile_cache=use_cache, parallelism=1)
            rows = []
            for edit in prepared.edits:
                report = json.loads(edit.import_report_path.read_bytes())
                rows.append((edit.kind, edit.selector, edit.replacement_sha256,
                             [(name, digest) for name, _, _, digest in edit.preview_paths],
                             tool.canonical_json(report).decode("utf-8")))
            tool.ownership.cleanup_owned(prepared.temp_files, [prepared.temp_root])
        finally:
            os.close(descriptor)
            os.close(index_pin.descriptor)
            os.close(inventory_pin.descriptor)
        return rows, out.getvalue()

    @staticmethod
    def without_session(rows, root):
        """The receipts name the project's own PNGs by design; compare everything else (as data: on Windows the JSON text
        doubles every backslash of a path)."""
        def walk(value):
            if isinstance(value, str):
                return value.replace(str(root), "$SESSION")
            if isinstance(value, list):
                return [walk(item) for item in value]
            if isinstance(value, dict):
                return {key: walk(item) for key, item in value.items()}
            return value
        return [(kind, selector, span, previews, json.dumps(walk(json.loads(report)), sort_keys=True))
                for kind, selector, span, previews, report in rows]

    @staticmethod
    def counters(output):
        found = {}
        for line in output.splitlines():
            if line.startswith(("NFL2K5_UNIT_COMPILE", "NFL2K5_COMPILE_CACHE")):
                name, *fields = line.split()
                found[name] = {key: int(value) for key, value in (field.split("=") for field in fields)}
        return found

    def test_a_cold_compile_a_warm_one_and_a_reopened_project_write_the_same_bytes(self):
        root = self.session_one[0]
        project = self.project(self.session_one)
        uncached, _ = self.prepare(project, root, use_cache=False)
        cold, cold_out = self.prepare(project, root)
        warm, warm_out = self.prepare(project, root)
        self.assertEqual(cold, uncached)
        self.assertEqual(warm, cold)
        self.assertEqual(self.counters(cold_out)["NFL2K5_COMPILE_CACHE"]["hits"], 0)
        self.assertEqual(self.counters(warm_out)["NFL2K5_COMPILE_CACHE"]["hits"], 2,
                         "the unit and the equipment group both come from the cache")
        # The project opened again: another session folder, the same files.
        second = self.session("two")
        reopened, reopened_out = self.prepare(self.project(second), second[0])
        self.assertEqual(self.without_session(reopened, second[0]), self.without_session(cold, root))
        counters = self.counters(reopened_out)
        self.assertEqual((counters["NFL2K5_COMPILE_CACHE"]["hits"], counters["NFL2K5_COMPILE_CACHE"]["misses"]), (2, 0))
        summary = json.loads(next(line for line in reopened_out.splitlines()
                                  if line.startswith("NFL2K5_STAGE_CACHE ")).split(" ", 1)[1])
        self.assertEqual((summary["hits"], summary["misses"]), (1, 0))
        self.assertEqual(summary["canary"], {"checked": 1, "mismatched": []})

    def test_changing_one_pixel_of_one_input_compiles_just_that_edit_again(self):
        from nfl_txtr import encode_rgba_png
        root = self.session_one[0]
        project = self.project(self.session_one)
        self.prepare(project, root)
        self.session_one[3].write_bytes(encode_rgba_png(512, 256, bytes((21, 190, 220, 255)) * (512 * 256)))
        _, out = self.prepare(project, root)
        counters = self.counters(out)
        self.assertEqual((counters["NFL2K5_UNIT_COMPILE"]["hits"], counters["NFL2K5_UNIT_COMPILE"]["misses"]), (0, 1))
        self.assertEqual(counters["NFL2K5_COMPILE_CACHE"]["hits"], 1, "the equipment group did not change")

    def test_two_builds_through_one_cache_publish_the_same_disc_and_receipts(self):
        root = self.session_one[0]
        project = self.project(self.session_one)
        outputs = []
        for number in range(2):
            work = root / f"build{number}"
            work.mkdir()
            with contextlib.redirect_stdout(io.StringIO()):
                result = self.tool.build(project, root / "source.iso", work / "out.iso", work / "manifest.json",
                                         work / "artifacts", root / "0", root / "inventory.json",
                                         compile_cache_root=self.cache_root)
            outputs.append((result["output"]["xiso_sha256"], result["patch"]["changed_byte_count"],
                            sorted(result["output"]["artifact_sha256"].values())))
        self.assertEqual(outputs[0], outputs[1])


class RealBytesTests(unittest.TestCase):
    """The real compile on real bytes (private inputs): what actually runs is inside the declared identity.

    B791_H6_PROJECT_JSON is a canonical backend project (what the build service stages), B791_H6_INDEX and B791_H6_INVENTORY are
    the opened retail disc's pack 0 and chunk inventory. The module-load trace of one compile of each unit kind (the late-step
    tracer, tools/b77/late_step_trace.py) must stay inside the kind's identity. Skipped when any of them is absent.
    """

    PROJECT = os.environ.get("B791_H6_PROJECT_JSON", "")
    INDEX = os.environ.get("B791_H6_INDEX", "")
    INVENTORY = os.environ.get("B791_H6_INVENTORY", "")

    @unittest.skipUnless(all(value and Path(value).exists() for value in (PROJECT, INDEX, INVENTORY)),
                         "needs a canonical project and an opened retail source cache")
    def test_the_traced_compile_of_each_unit_kind_stays_inside_its_identity(self):
        import late_step_trace
        tool = backend()
        project_doc = json.loads(Path(self.PROJECT).read_text(encoding="utf-8"))
        first = {}
        for edit in project_doc["edits"]:
            if edit["kind"] in tool.UNIT_KINDS:
                first.setdefault(edit["kind"], edit)
        self.assertTrue(first)
        index = stage_cache.CodeIdentity(ROOT)
        for kind, edit in sorted(first.items()):
            result, traced = late_step_trace.trace(self.compile_one, tool, edit)
            self.assertIn(result[0], {"ok", "kept"}, kind)
            identity = index.identity(tool._UNIT_CODE_ROOTS[kind], tool=tool._UNIT_DISPATCH[0],
                                      entry_points=tool._UNIT_DISPATCH[1], ignore=tool._UNIT_DISPATCH_WORDING,
                                      leaves=tool._UNIT_PLUMBING)
            outside = sorted(name for name in traced["code"]
                             if name not in identity["modules"] and name != "tools/nfl2k5_visual_mod_project.py")
            self.assertEqual(outside, [], f"{kind}: executed code outside the identity")
            opened = sorted(name for name in traced["data"] if not name.startswith(("reports/", "tests/"))
                            and name not in identity["data"])
            self.assertEqual(opened, [], f"{kind}: opened data outside the identity")

    @unittest.skipUnless(all(value and Path(value).exists() for value in (PROJECT, INDEX, INVENTORY)),
                         "needs a canonical project and an opened retail source cache")
    def test_the_tool_functions_a_compile_runs_are_all_reached_by_the_dispatch_digest(self):
        tool = backend()
        project_doc = json.loads(Path(self.PROJECT).read_text(encoding="utf-8"))
        first = {}
        for edit in project_doc["edits"]:
            if edit["kind"] in tool.UNIT_KINDS:
                first.setdefault(edit["kind"], edit)
        reached = stage_cache.CodeIdentity(ROOT).dispatch_names(
            tool._UNIT_DISPATCH[0], tool._UNIT_DISPATCH[1], tool._UNIT_DISPATCH_WORDING)
        tool_file = str(TOOL)
        for kind, edit in sorted(first.items()):
            ran = set()

            def profile(frame, event, _argument):
                if event == "call" and frame.f_code.co_filename == tool_file:
                    ran.add(frame.f_code.co_name)
            sys.setprofile(profile)
            try:
                self.compile_one(tool, edit)
            finally:
                sys.setprofile(None)
            module_level = {name for name in ran if callable(getattr(tool, name, None))
                            and getattr(getattr(tool, name), "__module__", None) == tool.__name__
                            and getattr(getattr(tool, name), "__qualname__", "") == name}
            outside = sorted(module_level - reached - set(tool._UNIT_DISPATCH_WORDING) - {"_unit_worker"})
            self.assertEqual(outside, [], f"{kind}: tool functions that ran but the dispatch digest does not cover")

    def compile_one(self, tool, edit):
        pins = {}
        for field in ("png", "clean_png", "mud_png"):
            if edit.get(field):
                path = Path(edit[field]).resolve()
                payload = path.read_bytes()
                pins[path] = tool.InputPin(path, payload, len(payload), hashlib.sha256(payload).hexdigest(), (0, 0))
        project = tool.ProjectFile(Path(self.PROJECT), b"", dict(schema="s", purpose="p", edits=[edit]), (0, 0))
        reports = {edit["kind"]: Path(tool.REPORTS[edit["kind"]])} if edit["kind"] in tool.REPORTS else {}
        with tempfile.TemporaryDirectory() as folder:
            root = tool.ownership.track_existing(Path(folder), True)
            files = []
            try:
                return tool._unit_compile(edit["kind"], 7, edit, project, pins, reports, Path(self.INDEX),
                                          Path(self.INVENTORY), root, files)
            finally:
                tool.ownership.cleanup_owned(files, [])


if __name__ == "__main__":
    unittest.main()
