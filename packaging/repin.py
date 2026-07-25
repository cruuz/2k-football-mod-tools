#!/usr/bin/env python3
"""Re-sync SHA-256 self-integrity pins after editing pinned modules.

Two pin shapes are handled, both located with `ast` so that class-scoped
attributes never leak across classes:

  A. dict entry   "path/to/file.py": "<64hex>",
  B. attribute    <name>_sha256 = "<64hex>"   paired with a sibling
                  <name> = "path/to/file.py"  in the SAME class/module scope.

A pin is only rewritten when its path resolves to a real file inside the
repo *and* the recomputed digest differs.  Hashes with no resolvable repo
path (retail ISO/XBE pins, negative-test fixtures) are left alone.

It only ever recomputes a pin from the bytes the pin covers; it never relaxes,
removes or widens one.  Run it with no arguments first to see what WOULD change,
then with ``--apply``.

Usage:  python3 packaging/repin.py [--apply] [--root DIR] [--include-tests]
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import sys
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-f]{64}$")
PATHISH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:py|json|sh|txt|schema\.json)$")

Replacement = tuple[int, int, int, int, str, str, str]  # positions, old, new, label


def digest(path: Path, cache: dict[str, str]) -> str | None:
    rel = path.as_posix()
    if rel not in cache:
        try:
            handle = open(path, "rb")
        except OSError:
            cache[rel] = ""
        else:
            with handle:
                h = hashlib.sha256()
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    h.update(chunk)
            cache[rel] = h.hexdigest()
    return cache[rel] or None


def string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def scope_assignments(body: list[ast.stmt]) -> dict[str, str]:
    """name -> string literal, for simple assignments directly in this body."""
    found: dict[str, str] = {}
    for stmt in body:
        targets: list[ast.expr] = []
        if isinstance(stmt, ast.Assign):
            targets = list(stmt.targets)
            value = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets = [stmt.target]
            value = stmt.value
        else:
            continue
        text = string_value(value)
        if text is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                found[target.id] = text
    return found


def collect(source: Path, root: Path, cache: dict[str, str]) -> list[Replacement]:
    text = source.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        print(f"!! cannot parse {source}: {exc}", file=sys.stderr)
        return []

    out: list[Replacement] = []

    def want(rel: str) -> str | None:
        if not PATHISH.match(rel):
            return None
        return digest(root / rel, cache)

    # --- shape A: dict entries keyed by a repo-relative path ------------
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if key is None:
                continue
            rel = string_value(key)
            current = string_value(value)
            if rel is None or current is None or not HEX64.match(current):
                continue
            fresh = want(rel)
            if fresh is None or fresh == current:
                continue
            out.append(
                (
                    value.lineno,
                    value.col_offset,
                    value.end_lineno or value.lineno,
                    value.end_col_offset or 0,
                    current,
                    fresh,
                    rel,
                )
            )

    # --- shape B: <name>_sha256 paired with sibling <name> --------------
    scopes: list[list[ast.stmt]] = [tree.body]
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            scopes.append(node.body)

    for body in scopes:
        names = scope_assignments(body)
        for stmt in body:
            if isinstance(stmt, ast.Assign):
                targets, value = list(stmt.targets), stmt.value
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                targets, value = [stmt.target], stmt.value
            else:
                continue
            current = string_value(value)
            if current is None or not HEX64.match(current):
                continue
            for target in targets:
                if not isinstance(target, ast.Name) or not target.id.endswith("_sha256"):
                    continue
                rel = names.get(target.id[: -len("_sha256")])
                if rel is None:
                    continue
                fresh = want(rel)
                if fresh is None or fresh == current:
                    continue
                out.append(
                    (
                        value.lineno,
                        value.col_offset,
                        value.end_lineno or value.lineno,
                        value.end_col_offset or 0,
                        current,
                        fresh,
                        f"{target.id} -> {rel}",
                    )
                )
    return out


def apply_replacements(source: Path, reps: list[Replacement]) -> None:
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    # Apply bottom-up so earlier offsets stay valid.
    for lineno, col, end_lineno, end_col, old, new, _label in sorted(reps, reverse=True):
        if lineno != end_lineno:
            raise SystemExit(f"multi-line pin literal at {source}:{lineno}; refusing")
        line = lines[lineno - 1]
        segment = line[col:end_col]
        if old not in segment:
            raise SystemExit(f"pin text drift at {source}:{lineno}: {segment!r}")
        lines[lineno - 1] = line[:col] + segment.replace(old, new, 1) + line[end_col:]
    source.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parent.parent),
        help="repository root (defaults to the tree this script lives in)",
    )
    parser.add_argument("--include-tests", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    targets: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        # Skipped: dot-directories (.git, scratch trees) and tools/vendor/,
        # which holds third-party sources -- Ghidra ships Python 2 scripts that
        # will not parse here. Nothing under either carries one of our pins; the
        # vendored extract-xiso binaries are pinned from packaging/, which is
        # scanned.
        if (
            rel.startswith(".")
            or rel.startswith(("build/", "dist/", "tools/vendor/"))
            or "__pycache__" in rel
        ):
            continue
        if not args.include_tests and (rel.startswith("tests/") or "_test" in Path(rel).name):
            continue
        targets.append(path)

    total = 0
    for round_number in range(1, 9):
        cache: dict[str, str] = {}
        round_total = 0
        for path in targets:
            reps = collect(path, root, cache)
            if not reps:
                continue
            for *_pos, old, new, label in reps:
                print(f"[{round_number}] {path.relative_to(root)}: {label}\n    {old}\n -> {new}")
            round_total += len(reps)
            if args.apply:
                apply_replacements(path, reps)
        total += round_total
        if round_total == 0 or not args.apply:
            break
    print(f"\n{'applied' if args.apply else 'would apply'} {total} pin update(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

