"""Audit third-party imports in every staged product module, including callbacks.

Run with the release interpreter, or pass --runtime for an assembled Windows
runtime on a cross-build host. The latter inspects that tree only; it never
borrows packages from the build host. Executable import checks still belong in
the platform's runtime gate. Scripts launched in external applications (for
example Blender) are not product packages. Product callbacks that load a
third-party dependency through a tool must mark it in LAZY_RUNTIME_IMPORTS.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys


def third_party_imports(root: Path) -> dict[str, list[str]]:
    root = Path(root)
    found: dict[str, list[str]] = {}
    local = {p.stem for p in root.glob('*.py')} | {p.name for p in root.iterdir() if p.is_dir()}
    local.update(p.stem for p in (root / 'tools').glob('*.py'))
    paths = sorted((root / 'mod_editor').rglob('*.py'))
    if not paths:
        raise RuntimeError('No staged product modules to scan')
    for path in paths:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                names = [node.module]
            elif isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
                if name in ('import_module', '__import__') and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    names = [node.args[0].value]
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(t, ast.Name) and t.id == 'LAZY_RUNTIME_IMPORTS' for t in targets):
                    try:
                        names = list(ast.literal_eval(node.value))
                    except (TypeError, ValueError) as exc:
                        raise RuntimeError(f'{path}: LAZY_RUNTIME_IMPORTS must be a literal tuple of module names') from exc
                    if any(not isinstance(name, str) or not name for name in names):
                        raise RuntimeError(f'{path}: invalid lazy import marker')
            for name in names:
                top = name.split('.')[0]
                if not top or top in sys.stdlib_module_names or top in local:
                    continue
                found.setdefault(name, []).append(f'{path.relative_to(root)}:{node.lineno}')
    return {name: sorted(set(sites)) for name, sites in sorted(found.items())}


def _windows_module(site: Path, name: str) -> Path | None:
    # Do not use host find_spec: Linux cannot resolve Windows .pyd files, and
    # find_spec could accidentally satisfy a missing package from host Python.
    target = site.joinpath(*name.split('.'))
    if target.is_dir() and (target / '__init__.py').is_file():
        return target / '__init__.py'
    for suffix in ('.py', '.pyd'):
        path = target.with_name(target.name + suffix)
        if path.is_file():
            return path
    for path in sorted(target.parent.glob(target.name + '.*.pyd')):
        if path.is_file():
            return path
    return None


def check_runtime_dependencies(root: Path, runtime: Path | None = None) -> dict:
    imports = third_party_imports(root)
    if runtime is not None:
        runtime = Path(runtime).resolve()
        site = runtime / 'Lib/site-packages'
        if not (runtime / 'python.exe').is_file():
            raise RuntimeError('Staged Windows interpreter is missing')
        pth = list(runtime.glob('python*._pth'))
        if len(pth) != 1 or 'Lib\\site-packages' not in pth[0].read_text().splitlines():
            raise RuntimeError('Staged Windows interpreter cannot see its site-packages')
        origins = {name: str(path) if (path := _windows_module(site, name)) else None for name in imports}
        # NumPy's Python shim alone does not constitute a usable installation.
        if 'numpy' in imports:
            binaries = list((site/'numpy/core').glob('_multiarray_umath*.pyd'))
            if not binaries or not list((site/'numpy.libs').glob('*.dll')):
                origins['numpy'] = None
    else:
        # -I excludes the checkout, PYTHONPATH and user site. Check the selected
        # runtime, not the developer's incidental pip --user installation.
        code = '''import importlib, json, sys
out = {}
for name in json.loads(sys.argv[1]):
    try:
        module = importlib.import_module(name)
        out[name] = getattr(module, '__file__', None) or '<built-in>'
    except Exception as exc:
        out[name] = {'error': str(exc)}
print(json.dumps(out))
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, json.dumps(list(imports))],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError('Dependency probe failed: ' + result.stderr.strip())
        origins = json.loads(result.stdout)
    missing = [f'{name} (used at {", ".join(imports[name])})' for name, origin in origins.items()
               if not origin or isinstance(origin, dict)]
    if missing:
        raise RuntimeError('Staged runtime is missing third-party dependencies: ' + '; '.join(missing))
    return dict(imports=imports, origins=origins, interpreter=str(runtime or sys.executable))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', type=Path)
    parser.add_argument('--runtime', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(check_runtime_dependencies(args.stage, args.runtime), indent=2))
    except (OSError, RuntimeError, SyntaxError, ValueError) as exc:
        print(f'RUNTIME_DEPENDENCIES_REFUSED: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
