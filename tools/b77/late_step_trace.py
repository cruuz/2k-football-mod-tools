"""b77.5 fast2: which repository code and data does a late build step actually use?

``trace(function)`` runs it with a profile hook and an audit hook and returns the repository files whose
functions ran and the non-code repository files or ``data/`` folders it opened. ``declaration(trace_result)`` widens that by one hop of
module-body imports (constants a used module takes from another), which is how nfl2k5_late_steps.STEP_CODE was
written. The test suite re-traces each step on real inputs and fails if a step runs a file or opens data that
STEP_CODE does not list.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def _relative(filename: str) -> str | None:
    if filename.startswith("<"):
        return None     # <frozen os>, <string>: not repository files
    try:
        relative = Path(filename).resolve().relative_to(ROOT)
    except (OSError, ValueError):
        return None
    if relative.parts[0] in ("tests", "reports") or "__pycache__" in relative.parts:
        return None
    return relative.as_posix()


def trace(function, *args, **kwargs):
    """(result, {"code": sorted files whose functions ran, "data": sorted files or data/ folders it opened})."""
    files: set[str] = set()
    data: set[str] = set()
    seen: dict[str, str | None] = {}

    def profile(frame, event, _arg):
        if event != "call":
            return
        code = frame.f_code
        if code.co_name == "<module>":
            return
        name = code.co_filename
        if name not in seen:
            seen[name] = _relative(name)
        if seen[name]:
            files.add(seen[name])

    def audit(event, arguments):
        if event == "open" and arguments and isinstance(arguments[0], str | Path):
            relative = _relative(str(arguments[0]))
            if relative and not relative.endswith((".py", ".pyc", ".so", ".pyd")) and not relative.startswith(".git/"):
                # a folder under data/ stands for all its files (the art a step reads varies with its input)
                data.add("/".join(relative.split("/")[:2]) if relative.startswith("data/") and relative.count("/") >= 2
                         else relative)

    sys.addaudithook(audit)
    sys.setprofile(profile)
    try:
        result = function(*args, **kwargs)
    finally:
        sys.setprofile(None)
    return result, {"code": sorted(files), "data": sorted(data)}


def _module_file(name: str) -> str | None:
    parts = name.split(".")
    for base in (ROOT, ROOT / "tools"):
        path = base.joinpath(*parts)
        if path.with_suffix(".py").is_file():
            return path.with_suffix(".py").relative_to(ROOT).as_posix()
    return None


def body_imports(relative: str) -> set[str]:
    """Repository files a source file imports at module level (not inside functions)."""
    path = ROOT / relative
    tree = ast.parse(path.read_bytes())
    parts = list(Path(relative).with_suffix("").parts)
    package = parts[:-1]
    found: set[str] = set()

    def visit(nodes):
        for node in nodes:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _module_file(alias.name)
                    if target:
                        found.add(target)
            elif isinstance(node, ast.ImportFrom):
                base = (node.module or "").split(".") if node.module else []
                if node.level:
                    keep = package[:len(package) - (node.level - 1)] if node.level > 1 else package
                    base = keep + base
                for alias in node.names:
                    for candidate in (".".join(base + [alias.name]), ".".join(base)):
                        target = _module_file(candidate) if candidate else None
                        if target:
                            found.add(target)
            elif isinstance(node, ast.ClassDef | ast.If | ast.Try | ast.With):
                for field in ("body", "orelse", "finalbody", "handlers"):
                    inner = getattr(node, field, None)
                    if inner:
                        visit(inner if field != "handlers" else [stmt for h in inner for stmt in h.body])
    visit(tree.body)
    found.discard(relative)
    return found


def declaration(traced: dict) -> dict:
    code = set(traced["code"])
    for relative in list(code):
        code |= body_imports(relative)
    return {"code": tuple(sorted(code)), "data": tuple(traced["data"])}
