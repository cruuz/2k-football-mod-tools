"""What makes the project (texture) stage's compile cache safe to keep between builds, sessions and Studio updates.

The project stage compiles every edit of a project (a league project has more than 13,000 textures; 3.5 to 9 hours). Before b791 the
compiled results lived inside the working-session folder (a new folder every time a project is opened), under keys that contained
the session's own file paths, and an entry was valid only while every Python file the compile process had loaded was unchanged (every
release changes at least ``mod_editor/__init__.py`` and ``providers.py``). So a retry in a new session, or after any Studio update,
compiled everything again. This module holds the parts that fix that without ever serving a stale result:

* :func:`stage_cache_root` - one cache next to the private source cache (``<cache root>/project-stage``), never in a session or a project;
* :class:`CodeIdentity` - the digest of the source an edit's compile can execute: the importers of its kind and everything they import
  (read from the source, never from what happened to be loaded), plus the project tool's own dispatch functions. Comments, docstrings
  and whitespace do not count; any other change to any of those files does. A Studio update that touches none of them keeps every
  result, an update that touches one of them replaces the results that depend on it, and a file it cannot read means no caching;
* :func:`edit_shape` - an edit is its parameters and the bytes of its inputs, never a file name or folder.

The entry format, the key and the check that runs before any saved result is trusted live with the compile loop
(``tools/nfl2k5_visual_mod_project.py``, ``IndependentUnits``); the eviction rule lives in ``nfl2k5_compile_cache``.

Nothing here executes project content or loads code from the cache; entries are JSON with a digest (``nfl2k5_compile_cache``).
"""
from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
import sys
from typing import Iterable

CACHE_DIRNAME = "project-stage"
#: Where a repository's data files live; a compile that reads one depends on its bytes. ``reports/`` holds the compatibility reports
#: (the project tool also pins and keys the ones it hands to a kind, but a writer can read another: the P8 inventory), ``tools/`` the
#: native helpers.
DATA_PREFIXES = ("mod_editor/data/", "mod_editor/assets/", "reports/", "tools/")
#: Edit fields that name a file. A cache key holds the file's content digest instead.
PATH_FIELDS = ("png", "clean_png", "mud_png", "wav", "recipe")
#: Default size cap of the stage cache. A build never evicts what it is using, so a bigger project simply keeps what it needs.
STAGE_CACHE_MAX_BYTES = 3 * 1024 ** 3


def stage_cache_max_bytes(environ=None) -> int:
    """The size cap: ``NFL2K5_COMPILE_CACHE_MAX_MB`` (the switch every compile cache honours) when set, else 3 GiB."""
    environ = os.environ if environ is None else environ
    configured = str(environ.get("NFL2K5_COMPILE_CACHE_MAX_MB", "")).strip()
    if configured:
        try:
            return max(1, int(configured)) * 1024 * 1024
        except ValueError:
            pass
    return STAGE_CACHE_MAX_BYTES


def stage_cache_root(source_cache=None, environ=None) -> Path | None:
    """``<private cache root>/project-stage`` for the loaded source cache, or None when there is no place for one.

    The root of a loaded source cache is ``<cache root>/<disc sha256>``; the compile results (game-derived like the source cache itself,
    and just as private) sit beside it, so they follow it on every platform. ``NFL2K5_PROJECT_STAGE_CACHE_ROOT`` overrides the place
    (tests, a bigger drive); the build tool is started with a clean environment, so the Studio passes the result on the command line.
    """
    environ = os.environ if environ is None else environ
    configured = environ.get("NFL2K5_PROJECT_STAGE_CACHE_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser()
    root = getattr(source_cache, "root", None)
    if root is None:
        return None
    return Path(root).parent / CACHE_DIRNAME


def edit_shape(edit: dict) -> dict:
    """The edit without the fields that name files (their content digests are keyed separately)."""
    return {name: value for name, value in edit.items() if name not in PATH_FIELDS}


def _strip_docstrings(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]


def _dump(node: ast.AST) -> str:
    return ast.dump(node, annotate_fields=True, include_attributes=False)


class CodeIdentity:
    """Static view of one repository: which files an edit's compile can execute, and the digest of each.

    ``roots`` are repository-relative importer modules (``tools/nfl_pants_tset_png_import.py``). The closure follows every ``import`` in
    a file, including those inside functions, plus string literals that name a repository file (the adapters the project tool loads by
    path). Package ``__init__`` files re-export and carry the version string; they are not part of any compile and are skipped.
    Anything that cannot be read or parsed makes the identity unavailable (None): nothing is cached for it.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self._search = (self.root, self.root / "tools")
        self._trees: dict[str, ast.Module | None] = {}
        self._digests: dict[str, str | None] = {}
        self._links: dict[str, tuple[frozenset[str], frozenset[str]] | None] = {}
        self._data_digests: dict[tuple[str, int, int], str] = {}
        self._closures: dict[tuple[str, ...], tuple[tuple[str, ...], tuple[str, ...]] | None] = {}
        self._dispatch: dict[tuple[str, tuple[str, ...]], str | None] = {}

    # -- reading ---------------------------------------------------------
    def _tree(self, relative: str) -> ast.Module | None:
        """The parsed file with its docstrings removed (they are neither behaviour nor, for a path mentioned in one, a dependency)."""
        if relative not in self._trees:
            tree = None
            try:
                tree = ast.parse((self.root / relative).read_text(encoding="utf-8-sig"))
                _strip_docstrings(tree)
            except (OSError, UnicodeError, SyntaxError, ValueError, RecursionError):
                tree = None
            self._trees[relative] = tree
        return self._trees[relative]

    def module_digest(self, relative: str) -> str | None:
        if relative not in self._digests:
            tree = self._tree(relative)
            self._digests[relative] = (None if tree is None
                                       else hashlib.sha256(_dump(tree).encode("utf-8")).hexdigest())
        return self._digests[relative]

    def data_digest(self, relative: str) -> str | None:
        path = self.root / relative
        try:
            info = path.stat()
            key = (relative, info.st_size, info.st_mtime_ns)
            if key not in self._data_digests:
                self._data_digests[key] = hashlib.sha256(path.read_bytes()).hexdigest()
            return self._data_digests[key]
        except OSError:
            return None

    # -- imports ---------------------------------------------------------
    def _module_file(self, parts: list[str]) -> str | None:
        if not parts:
            return None
        for base in self._search:
            stem = base.joinpath(*parts)
            candidate = stem.with_name(stem.name + ".py")
            if candidate.is_file():
                return candidate.relative_to(self.root).as_posix()
        return None

    def _package_parts(self, relative: str) -> list[str]:
        parts = relative[:-3].split("/")
        if parts and parts[0] == "tools":
            parts = parts[1:]
        return parts[:-1]

    def _links_of(self, relative: str) -> tuple[frozenset[str], frozenset[str]] | None:
        """(python files, data files) one file refers to; None when the file cannot be read."""
        if relative in self._links:
            return self._links[relative]
        tree = self._tree(relative)
        if tree is None:
            self._links[relative] = None
            return None
        modules: set[str] = set()
        data: set[str] = set()
        package = self._package_parts(relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found = self._module_file(alias.name.split("."))
                    if found:
                        modules.add(found)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = package[:len(package) - (node.level - 1)] if node.level > 1 else package
                    parts = base + (node.module.split(".") if node.module else [])
                else:
                    parts = node.module.split(".") if node.module else []
                found = self._module_file(parts)
                if found:
                    modules.add(found)
                for alias in node.names:
                    found = self._module_file(parts + [alias.name])
                    if found:
                        modules.add(found)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
                if 4 < len(text) < 240 and "/" in text and not text.startswith(("/", ".", "~")) \
                        and not any(c in text for c in "\n\r\t*?<>|\"") and ".." not in text:
                    # A repository file named by a literal: an adapter loaded by path, a data file read at run time.
                    if text.endswith(".py"):
                        if (self.root / text).is_file():
                            modules.add(text)
                    elif text.startswith(DATA_PREFIXES) and (self.root / text).is_file():
                        data.add(text)
        modules.discard(relative)
        self._links[relative] = (frozenset(m for m in modules if not m.endswith("__init__.py")), frozenset(data))
        return self._links[relative]

    def closure(self, roots: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
        """(python files, data files), sorted, reachable from ``roots``; None when any of them cannot be read."""
        key = tuple(sorted(roots))
        if key in self._closures:
            return self._closures[key]
        seen: set[str] = set()
        data: set[str] = set()
        stack = list(key)
        result = None
        ok = True
        while stack:
            relative = stack.pop()
            if relative in seen:
                continue
            seen.add(relative)
            links = self._links_of(relative)
            if links is None:
                ok = False
                break
            modules, files = links
            data.update(files)
            stack.extend(modules - seen)
        if ok:
            result = (tuple(sorted(seen)), tuple(sorted(data)))
        self._closures[key] = result
        return result

    # -- the tool's own dispatch ----------------------------------------
    def dispatch_digest(self, tool: str, entry_points: Iterable[str], ignore: Iterable[str] = ()) -> str | None:
        """Digest of the functions, classes and constants of ``tool`` that the entry points can reach by name.

        Everything else in the file (the other build steps, the command line, the audio and stadium kinds) does not count, so a change
        to it keeps the compiled results. Module-level statements that run on import (calls, ``if`` blocks) always count.
        ``ignore`` names helpers that only word a failure (they cannot change what a successful compile produces, and only successful
        compiles are cached): they are left out, so a better error message never discards a day of compiled textures.
        """
        key = (tool, tuple(sorted(entry_points)), tuple(sorted(ignore)))
        if key in self._dispatch:
            return self._dispatch[key]
        tree = self._tree(tool)
        digest = None
        if tree is not None:
            digest = self._reach(tree, key[1], frozenset(key[2]))
        self._dispatch[key] = digest
        return digest

    @staticmethod
    def _targets(node: ast.stmt) -> list[str]:
        names: list[str] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.extend(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            names.extend(n.id for n in ast.walk(node.target) if isinstance(n, ast.Name))
        return names

    @staticmethod
    def _is_main_guard(node: ast.stmt) -> bool:
        if not isinstance(node, ast.If):
            return False
        test = node.test
        return (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__"
                and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in test.comparators))

    def dispatch_names(self, tool: str, entry_points: Iterable[str], ignore: Iterable[str] = ()) -> frozenset[str] | None:
        """The top-level names of ``tool`` the entry points reach (what :meth:`dispatch_digest` covers); None when unreadable."""
        tree = self._tree(tool)
        found = None if tree is None else self._reach(tree, tuple(sorted(entry_points)), frozenset(ignore), names_only=True)
        return found

    def _reach(self, tree: ast.Module, entry_points: tuple[str, ...], ignore: frozenset[str] = frozenset(),
               names_only: bool = False):
        defined: dict[str, list[ast.stmt]] = {}
        always: list[ast.stmt] = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue            # the module docstring
            names = self._targets(node)
            if names:
                for name in names:
                    defined.setdefault(name, []).append(node)
            elif not self._is_main_guard(node):
                always.append(node)  # runs on import and has no name: it always counts
        missing = [name for name in entry_points if name not in defined]
        if missing:
            return None
        picked: dict[int, ast.stmt] = {}
        needed: set[str] = set()
        stack = list(entry_points) + [n.id for stmt in always for n in ast.walk(stmt) if isinstance(n, ast.Name)]
        for stmt in always:
            picked[id(stmt)] = stmt
        while stack:
            name = stack.pop()
            if name in needed or name not in defined or name in ignore:
                continue
            needed.add(name)
            for stmt in defined[name]:
                picked[id(stmt)] = stmt
                for node in ast.walk(stmt):
                    if isinstance(node, ast.Name) and node.id in defined and node.id not in needed:
                        stack.append(node.id)
        if names_only:
            return frozenset(needed)
        ordered = sorted(picked.values(), key=lambda stmt: (stmt.lineno, stmt.col_offset))
        return hashlib.sha256("\n".join(_dump(stmt) for stmt in ordered).encode("utf-8")).hexdigest()

    # -- the identity of one kind of compile ----------------------------
    def identity(self, roots: Iterable[str], *, tool: str | None = None, entry_points: Iterable[str] = (),
                 ignore: Iterable[str] = (), leaves: Iterable[str] = ()) -> dict | None:
        """``{"python": ..., "modules": {file: digest}, "data": {file: digest}, "dispatch": digest}`` or None (cache nothing).

        ``leaves`` are files that run during every compile without belonging to one kind (the project tool's file-ownership and
        pinning helpers): each counts by its own source, and what it imports does not (the traced compile shows nothing beyond
        them runs, and ``tests/mod_editor/test_b791_h6_stage_cache.py`` fails if that ever stops being true).
        """
        closed = self.closure(roots)
        if closed is None:
            return None
        modules, data = closed
        modules = tuple(sorted(set(modules) | set(leaves)))
        record: dict = {"python": f"{sys.version_info[0]}.{sys.version_info[1]}", "modules": {}, "data": {}}
        for relative in modules:
            digest = self.module_digest(relative)
            if digest is None:
                return None
            record["modules"][relative] = digest
        for relative in data:
            digest = self.data_digest(relative)
            if digest is None:
                return None
            record["data"][relative] = digest
        if tool is not None:
            dispatch = self.dispatch_digest(tool, entry_points, ignore)
            if dispatch is None:
                return None
            record["dispatch"] = dispatch
        return record


def changed_files(stored: dict | None, current: dict | None) -> list[str]:
    """Names of the files whose digest differs between two identities (for the build log); [] when equal."""
    if not isinstance(stored, dict) or not isinstance(current, dict):
        return ["(unknown)"]
    names: list[str] = []
    for group in ("modules", "data"):
        old, new = stored.get(group) or {}, current.get(group) or {}
        for name in sorted(set(old) | set(new)):
            if old.get(name) != new.get(name):
                names.append(name)
    if stored.get("dispatch") != current.get("dispatch"):
        names.append("(dispatch)")
    if stored.get("python") != current.get("python"):
        names.append("(python)")
    return names
