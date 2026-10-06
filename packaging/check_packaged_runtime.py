"""Import the runtime closure from a finished Studio archive or Windows Setup.

Portable archives use --python (the interpreter users install requirements in).
Windows Setup uses its own embedded CPython, under a private Wine prefix on
Linux. No dependencies from the Linux host can satisfy a Windows import.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

try:
    from runtime_dependencies import third_party_imports
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from runtime_dependencies import third_party_imports

# Required even when an optional callback's import is not reached by the scan.
# Include QtWidgets to load Qt's binary DLLs, rather than its namespace shim.
RUNTIME_IMPORTS = ('PyQt5.QtWidgets', 'PIL.Image', 'numpy', 'capstone', 'unicorn')
REQUIREMENT_IMPORTS = {'pyqt5': 'PyQt5.QtWidgets', 'pillow': 'PIL.Image',
                       'numpy': 'numpy', 'capstone': 'capstone', 'unicorn': 'unicorn'}


def declared_imports(app: Path) -> set[str]:
    modules = set(RUNTIME_IMPORTS)
    requirements = app / 'packaging/requirements-studio.txt'
    for line in requirements.read_text(encoding='utf-8').splitlines():
        requirement = line.split('#', 1)[0].strip()
        if not requirement:
            continue
        distribution = requirement.split('==', 1)[0].lower()
        if distribution not in REQUIREMENT_IMPORTS:
            raise RuntimeError('Add an executable import probe for runtime requirement: ' + requirement)
        modules.add(REQUIREMENT_IMPORTS[distribution])
    return modules

PROBE = r'''
import importlib, json, os, sys
from pathlib import Path
request = json.loads(sys.argv[1])
out = {'platform': sys.platform, 'interpreter': sys.executable, 'imports': {}, 'errors': {}}
for name in request['imports']:
    try:
        module = importlib.import_module(name)
        origin = getattr(module, '__file__', '')
        if request['runtime'] and not Path(origin).resolve().is_relative_to(Path(request['runtime']).resolve()):
            raise RuntimeError('Dependency loaded outside the packaged runtime: ' + origin)
        out['imports'][name] = {'origin': origin, 'version': getattr(module, '__version__', None)}
    except Exception as exc:
        out['errors'][name] = type(exc).__name__ + ': ' + str(exc)
sys.path[:0] = [request['app'], str(Path(request['app']) / 'tools')]
if (Path(request['app']) / 'mod_editor/core/nfl2k5_throw_tuning.py').is_file():
    try:
        from mod_editor.core import mod_build, nfl2k5_throw_tuning as reader
        # Exercise the real file-opening/disc reader, without retail payloads.
        if request['disc']:
            state = mod_build.inspect(request['disc'])
            if state.get('container') != 'xiso':
                raise RuntimeError('Expected an XISO inspection')
            out['disc_reader'] = {'container': state['container'], 'options': len(state)}
        else:
            path = Path(request['probe_disc'])
            try:
                reader.read_image(path)
            except ValueError as exc:
                # An intentionally invalid file must reach the XDVDFS reader.
                if 'XDVDFS' not in str(exc) and 'disc image' not in str(exc):
                    raise
                out['disc_reader'] = {'invalid_image_refused': str(exc)}
            else:
                raise RuntimeError('Invalid disc probe was accepted')
    except Exception as exc:
        out['errors']['disc_reader'] = type(exc).__name__ + ': ' + str(exc)
print('PACKAGED_RUNTIME_JSON=' + json.dumps(out, sort_keys=True))
raise SystemExit(1 if out['errors'] else 0)
'''


def unpack(artifact: Path, destination: Path) -> Path:
    """Unpack only into a fresh gate-owned directory; reject archive links."""
    if artifact.is_dir():
        return artifact.resolve()
    if artifact.name.endswith('.exe'):
        subprocess.run(['7z', 'x', '-y', '-o' + str(destination), str(artifact.resolve())],
                       check=True, capture_output=True, timeout=120)
        return destination
    with tarfile.open(artifact, 'r:gz') as archive:
        for member in archive.getmembers():
            target = destination / member.name
            if not target.resolve().is_relative_to(destination.resolve()) or not (member.isdir() or member.isfile()):
                raise RuntimeError('Unsafe release archive member: ' + member.name)
        archive.extractall(destination, filter='data')
    roots = [p for p in destination.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise RuntimeError('Release archive must contain one application folder')
    return roots[0]


def wine_path(path: Path) -> str:
    return 'Z:' + str(path.resolve()).replace('/', '\\')


def check_layout(root: Path, *, python: Path | None = None,
                 wine_prefix: Path | None = None, disc: Path | None = None) -> dict:
    root = root.resolve()
    runtime = root / 'runtime'
    windows = (runtime / 'python.exe').is_file()
    app = root / 'app' if windows else root
    imports = sorted(set(third_party_imports(app)) | declared_imports(app))
    with tempfile.TemporaryDirectory(prefix='studio-runtime-probe-') as temporary:
        scratch = Path(temporary)
        probe_disc = scratch / 'invalid.iso'
        probe_disc.write_bytes(bytes(131072))
        path = wine_path if windows and os.name != 'nt' else lambda p: str(p.resolve())
        request = dict(imports=imports, app=path(app), runtime=path(runtime) if windows else '',
                       disc=path(disc) if disc else '', probe_disc=path(probe_disc))
        interpreter = runtime / 'python.exe' if windows else (python or Path(sys.executable))
        command = [str(interpreter), '-I', '-B', '-c', PROBE, json.dumps(request)]
        environment = os.environ.copy()
        environment.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', QT_QPA_PLATFORM='offscreen')
        environment.pop('PYTHONPATH', None)
        if windows and os.name != 'nt':
            if not shutil.which('wine'):
                raise RuntimeError('Wine is required to validate Windows binary dependencies')
            prefix = wine_prefix.resolve() if wine_prefix else scratch / 'wine-prefix'
            environment.update(WINEPREFIX=str(prefix), WINEDEBUG='-all',
                               WINEDLLOVERRIDES='winemenubuilder.exe,mscoree,mshtml,winealsa.drv,winepulse.drv=d')
            # The prefix and all Wine writes are gate-owned. No GUI is needed.
            environment.pop('DISPLAY', None)
            command.insert(0, 'wine')
        result = subprocess.run(command, env=environment, cwd=scratch, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
        marker = 'PACKAGED_RUNTIME_JSON='
        lines = [line[len(marker):] for line in result.stdout.splitlines() if line.startswith(marker)]
        if not lines:
            raise RuntimeError('Packaged interpreter did not finish its probe: ' + result.stderr.strip())
        receipt = json.loads(lines[-1])
        if result.returncode or receipt['errors']:
            raise RuntimeError('Packaged runtime import failed: ' + json.dumps(receipt['errors'], sort_keys=True))
        return receipt


def check_artifact(artifact: Path, *, python: Path | None = None,
                   wine_prefix: Path | None = None, disc: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix='studio-artifact-gate-') as temporary:
        root = unpack(artifact, Path(temporary))
        receipt = check_layout(root, python=python, wine_prefix=wine_prefix, disc=disc)
        if artifact.is_file():
            receipt['artifact'] = artifact.name
            with artifact.open('rb') as stream:
                receipt['sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--python', type=Path)
    parser.add_argument('--wine-prefix', type=Path, help='Dedicated gate prefix; never use your personal Wine prefix')
    parser.add_argument('--disc', type=Path, help='Optional read-only supported retail XISO inspection')
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    try:
        receipt = check_artifact(args.artifact, python=args.python, wine_prefix=args.wine_prefix, disc=args.disc)
        payload = json.dumps(receipt, indent=2, sort_keys=True)
        if args.receipt:
            args.receipt.write_text(payload + '\n', encoding='utf-8', newline="\n")
        print(payload)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print('PACKAGED_RUNTIME_REFUSED: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
