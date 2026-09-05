#!/usr/bin/env python3
"""Run the CI test-file matrix with the installer's Windows CPython under Wine.

The installer runtime is untouched. A private copy restores script/PYTHONPATH
lookup, including in child interpreters, through a runner-only sitecustomize.
No product APIs, file locking, or test assertions are patched.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
import fnmatch
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORK = Path.home() / ".cache/2k-football-mod-tools/winci"
ISOLATED = "test_apf_studio_installer.py"
EVIDENCE = "reports/assets/nfl2k5_all_txtr_inventory_v2.json"
LEAN_SKIPS = frozenset({
    "test_2k5_uniform_equipment_export.py", "test_all_textures_workspace.py",
    "test_apf_logo_surface_ownership.py", "test_apf_product_findings.py",
    "test_menu_modes.py", "test_nfl2k5_crib_geometry_writer.py",
    "test_nfl2k5_crib.py", "test_nfl2k5_face_shield_registry.py",
    "test_nfl2k5_stock_midfield_logo_boundary.py", "test_no_capability_is_invisible.py",
    "test_presentation_inspection.py", "test_uniform_sharing.py",
})
LEAN_REASON = "developer-only large evidence is intentionally absent"
HYDRATION_TREES = ("reports", "mod_editor/assets", "tools/vendor", "docs/research")
RELEASE_REPO = "cruuz/2k-football-mod-tools"
RELEASE_TAG = "beta-50"
RELEASE_ARCHIVES = {
    "2K5-Mod-Studio-v1.0-RC74-20260822.tar.gz":
        "1dd5762329203dcde152b48e8f1543c6eff26ad067f25ed1124642c48bdcba1f",
    "apf2k8-mod-studio-0.1.0-alpha.81-20260822.tar.gz":
        "8e4fe2ac2b0adc521dd2606e0cf5da67d357220e1ecc9904600d831c024bc8b7",
}
CLASSIFICATIONS = json.loads(Path(__file__).with_name("local_windows_ci_failures.json").read_text(encoding="utf-8"))
_cancelled = threading.Event()

# This is loaded by *every* child python.exe through the private ._pth file.
# Embedded CPython otherwise ignores PYTHONPATH, even when a child explicitly
# sets it to a staged release. Do not bake a checkout path into this file.
STARTUP = r'''
import os
import sys

script = sys.argv[0] if sys.argv else ""
first = os.path.dirname(os.path.abspath(script)) if script and not script.startswith("-") else os.getcwd()
paths = [first]
if "PYTHONPATH" in os.environ:
    paths.extend(os.path.abspath(p) for p in os.environ["PYTHONPATH"].split(os.pathsep))
sys.path[:0] = paths
sys.dont_write_bytecode = bool(os.environ.get("PYTHONDONTWRITEBYTECODE"))
if os.environ.get("PYTHONFAULTHANDLER"):
    import faulthandler
    faulthandler.enable()

# Windows DLLs can use different CRT environment tables. Set both tables as
# well as the Win32 environment before any Qt import. The preflight checks the
# resulting QPA name; failure must never silently fall back to a desktop.
_winci_qt_before = {"os.environ": os.environ.get("QT_QPA_PLATFORM")}
if os.name == "nt":
    import ctypes
    for name in ("msvcrt", "ucrtbase"):
        crt = ctypes.CDLL(name)
        crt.getenv.argtypes = [ctypes.c_char_p]
        crt.getenv.restype = ctypes.c_char_p
        before = crt.getenv(b"QT_QPA_PLATFORM")
        _winci_qt_before[name] = before.decode("utf-8", "replace") if before is not None else None
        crt._putenv_s.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        crt._putenv_s.restype = ctypes.c_int
        if crt._putenv_s(b"QT_QPA_PLATFORM", b"offscreen"):
            raise RuntimeError("cannot set Qt environment in " + name)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
'''

# Keep a Windows PID for taskkill /T: Wine-created descendants are not always
# members of the Unix launcher's process group. This file belongs to one test.
BOOTSTRAP = r'''
import os, pathlib, runpy, sys
script, pidfile = sys.argv[1:]
pathlib.Path(pidfile).write_text(str(os.getpid()), encoding="ascii")
sys.argv = [script]
sys.path[0] = str(pathlib.Path(script).resolve().parent)
runpy.run_path(script, run_name="__main__")
'''

OS_PROBE = r'''
import json, os, pathlib, platform, sitecustomize, sys, tempfile
from PyQt5.QtCore import QT_VERSION_STR
from PyQt5.QtWidgets import QApplication
app = QApplication(["winci-os-check"])
facts = dict(version=platform.python_version(), sys_platform=sys.platform,
             os_name=os.name, platform_system=platform.system(),
             O_BINARY=getattr(os, "O_BINARY", None), Qt=QT_VERSION_STR,
             qt_environment_before=sitecustomize._winci_qt_before,
             QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM"),
             temp_directory=tempfile.gettempdir(),
             qt_platform=app.platformName())
print(json.dumps(facts, sort_keys=True), flush=True)
assert facts["version"] == "3.12.10", facts
assert (sys.platform, os.name, platform.system()) == ("win32", "nt", "Windows"), facts
assert facts["O_BINARY"] is not None and app.platformName() == "offscreen", facts
assert pathlib.Path(facts["temp_directory"]) == pathlib.Path(os.environ["TEMP"]), facts
assert pathlib.Path(facts["temp_directory"]).is_relative_to(pathlib.Path(os.environ["LOCALAPPDATA"])), facts
'''

# Wine defaults to USERPROFILE/Temp, outside the private LOCALAPPDATA root
# required by the source-cache tests. Real Windows uses LOCALAPPDATA/Temp.
# Set this in the parent environment too so subprocesses inherit the same path.
TEMP_PROBE = r'''
import os, pathlib
root = pathlib.Path(os.environ["LOCALAPPDATA"]) / "Temp" / "winci"
root.mkdir(parents=True, exist_ok=True)
print(root.resolve(), flush=True)
'''


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def positive_seconds(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--only", action="extend", nargs="+", default=[], metavar="NAME",
                        help="repeatable test basename or glob; intersects --changed")
    parser.add_argument("--changed", action="store_true",
                        help="changed tests and tests mentioning changed module stems")
    parser.add_argument("-j", type=positive_int, default=1, dest="jobs")
    parser.add_argument("--work", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--prefix", type=Path, help="dedicated prefix; default: WORK/prefix")
    parser.add_argument("--timeout", type=positive_seconds, default=420)
    parser.add_argument("--os-check", action="store_true")
    hydration = parser.add_mutually_exclusive_group()
    hydration.add_argument("--hydrate-from", type=Path, metavar="DIR",
                           help="copy absent evidence paths from a sibling checkout")
    hydration.add_argument("--hydrate-release", action="store_true",
                           help="download and verify CI's two pinned beta-50 archives with gh")
    parser.add_argument("--keep-going", action="store_true",
                        help="explicit CI-compatible behavior (already the default)")
    return parser


def changed_paths(repo: Path) -> set[str]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True)
    base = git("merge-base", "HEAD", "origin/main").strip()
    # Diff against the working tree includes committed, staged and unstaged
    # changes. Include untracked edits and both sides of renames as well.
    tracked = git("diff", "--name-only", "--no-renames", "-z", base, "--")
    untracked = git("ls-files", "--others", "--exclude-standard", "-z")
    return set(filter(None, (tracked + untracked).split("\0")))


def plan(repo: Path, only: list[str], changed: set[str] | None = None) -> list[Path]:
    tests = sorted((repo / "tests/mod_editor").glob("test_*.py"))
    for pattern in only:
        if not any(fnmatch.fnmatchcase(p.name, pattern) for p in tests):
            raise ValueError(f"--only pattern matched no test files: {pattern}")
    if only:
        tests = [p for p in tests if any(fnmatch.fnmatchcase(p.name, pat) for pat in only)]
    if changed is not None:
        stems = {Path(p).stem for p in changed if p.endswith(".py") and not p.startswith("tests/")}
        tests = [p for p in tests if p.relative_to(repo).as_posix() in changed or
                 any(stem in p.read_text(encoding="utf-8") for stem in stems)]
    return tests


def skip_reason(repo: Path, name: str) -> str | None:
    if not (repo / EVIDENCE).is_file() and name in LEAN_SKIPS:
        return LEAN_REASON
    return None


def normalize_diagnostic(text: str) -> str:
    """Keep the exception/artifact exact while allowing user and temp names to vary."""
    text = text.replace("\\\\", "\\").replace("\\", "/")
    text = re.sub(r"[A-Za-z]:/users/[^/\r\n'\"]+/(?:AppData/Local/)?Temp/(?:winci/)?",
                  "<TEMP>/", text, flags=re.I)
    text = re.sub(r"(<TEMP>/)(?:tmp[a-z0-9_]+|[a-z0-9_-]+-[a-z0-9_]{8})(?=[/'\"])",
                  r"\1<case>", text)
    text = re.sub(r"[A-Za-z]:/[^'\"\r\n]*?/tests/fixtures/(?=nfl2k5_player_star_thin_v1\.json)",
                  "<REPO>/tests/fixtures/", text)
    return re.sub(r"(?<=\.apf-team-logo-build-)[a-z0-9_]{8}", "<random>", text)


def wine_gap_reason(name: str, rc: int, output: str) -> str | None:
    """Only skip observed failures, after executing the file and retaining its log.

    Every unittest failure block must match a reviewed case AND signature.
    A known gap alongside a missing input, new regression, truncated report or
    timeout remains a failure. In particular WinError 5 is never a skip rule.
    """
    if rc == 0 or rc in (124, 127) or "TIMED OUT" in output:
        return None
    row = next((r for r in CLASSIFICATIONS["files"] if r["name"] == name), None)
    if row is None:
        return None
    rules = row["wine_signatures"]
    reasons = set()
    blocks = re.split(r"(?=^(?:ERROR|FAIL): )", output, flags=re.M)[1:]
    if blocks:
        if rc not in (1, 5):
            return None
        final = re.search(r"^FAILED \(([^\n]+)\)\s*\Z", output, re.M)
        if final is None:
            return None
        counts = dict(re.findall(r"(failures|errors)=([0-9]+)", final[1]))
        if sum(int(n) for n in counts.values()) != len(blocks):
            return None
        for block in blocks:
            header = block.splitlines()[0]
            terminals = re.findall(r"^[\w.]+(?:Error|Exception):.*$", block, re.M)
            if not terminals:
                return None
            match = next((r for r in rules if header in r.get("headers", ())
                          and r["statement"] in block
                          and r["terminal"] == normalize_diagnostic(terminals[-1])), None)
            if match is None:
                return None
            reasons.add(match["gap"])
    else:
        for rule in rules:
            if "import_error" in rule:
                if (output.rstrip().endswith(rule["import_error"])
                        and rule["frame"] in output
                        and output.startswith("Traceback (most recent call last):")):
                    reasons.add(rule["gap"])
            elif "crash" in rule and rule["crash"] in output:
                # A crash can prevent unittest from printing earlier failures.
                # Only dots/skips before this fatal error are safe to classify.
                progress = output.split("wine: Call from", 1)[0].strip()
                if (re.fullmatch(r"[.s]*", progress) and rule["frame"] in output
                        and " in " + rule["case"] in output
                        and "Windows fatal exception: code 0x80000100" in output):
                    reasons.add(rule["gap"])
    if not reasons:
        return None
    return "Wine gap: " + "; ".join(CLASSIFICATIONS["gap_reasons"][key] for key in sorted(reasons))


def tracked_paths(repo: Path) -> set[str]:
    # Archive snapshots have no index. Existing paths remain protected there.
    if not (repo / ".git").exists():
        return set()
    output = subprocess.check_output(["git", "-C", str(repo), "ls-files", "-z"], text=True)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", "HEAD"],
                          capture_output=True, text=True, check=False)
    if head.returncode == 0:
        # A staged deletion is absent from the index, but still belongs to the
        # checkout's tracked source. Do not undo it by hydrating an older copy.
        output += subprocess.check_output(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "-z", "HEAD"], text=True)
    elif head.returncode != 1:
        raise RuntimeError(f"cannot inspect checkout HEAD: {head.stderr.strip()}")
    return set(filter(None, output.split("\0")))


def hydration_target(repo: Path, relative: PurePosixPath, tracked: set[str]) -> Path | None:
    """Refuse existing leaves, tracked deletions, links and obstructed parents."""
    if (relative.is_absolute() or not relative.parts
            or any(p in (".", "..", ".git") or ":" in p or "\\" in p for p in relative.parts)):
        raise ValueError(f"unsafe hydration path: {relative}")
    current = repo
    for index, part in enumerate(relative.parts):
        current = current / part
        key = PurePosixPath(*relative.parts[:index + 1]).as_posix()
        if key in tracked or current.is_symlink():
            return None
        if index < len(relative.parts) - 1 and current.exists() and not current.is_dir():
            return None
    return None if current.exists() else current


def copy_hydration_file(repo: Path, relative: PurePosixPath, tracked: set[str],
                        source, mode: int) -> bool:
    target = hydration_target(repo, relative, tracked)
    if target is None:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination = target.open("xb")
    except FileExistsError:
        return False
    try:
        with destination:
            shutil.copyfileobj(source, destination)
        target.chmod(mode & 0o777)
    except BaseException:
        target.unlink()
        raise
    print(f"HYDRATE + {relative.as_posix()}", flush=True)
    return True


def hydrate_from(repo: Path, source: Path) -> list[str]:
    source = source.expanduser().resolve(strict=True)
    repo = repo.resolve(strict=True)
    if not source.is_dir() or source == repo or source.is_relative_to(repo) or repo.is_relative_to(source):
        raise ValueError("--hydrate-from must be a separate checkout directory")
    tracked = tracked_paths(repo)
    copied = []
    for tree in HYDRATION_TREES:
        origin = source / tree
        before = len(copied)
        if any(p.is_symlink() for p in (origin, *origin.parents) if p.is_relative_to(source)):
            print(f"HYDRATE {tree}/: omitted source symlink", flush=True)
            continue
        if not origin.is_dir():
            print(f"HYDRATE {tree}/: source absent", flush=True)
            continue
        for parent, dirs, files in os.walk(origin, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not (Path(parent) / d).is_symlink())
            for name in sorted(files):
                path = Path(parent) / name
                if path.is_symlink() or not path.is_file():
                    continue
                relative = PurePosixPath(path.relative_to(source).as_posix())
                if hydration_target(repo, relative, tracked) is None:
                    continue
                with path.open("rb") as content:
                    if copy_hydration_file(repo, relative, tracked, content, path.stat().st_mode):
                        copied.append(relative.as_posix())
        print(f"HYDRATE {tree}/: copied {len(copied) - before} absent files from {origin}", flush=True)
    print(f"HYDRATED_LOCAL_INPUTS files={len(copied)}", flush=True)
    return copied


def hydrate_archives(repo: Path, inputs: Path) -> list[str]:
    # Verify BOTH pins before opening either archive or copying a single byte.
    for name, expected in RELEASE_ARCHIVES.items():
        with (inputs / name).open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"candidate archive hash mismatch: {name}")
    repo = repo.resolve(strict=True)
    tracked = tracked_paths(repo)
    copied = []
    for name in RELEASE_ARCHIVES:
        before = len(copied)
        with tarfile.open(inputs / name, "r:gz") as bundle:
            for member in bundle:
                parts = member.name.rstrip("/").split("/")
                if (len(parts) < 2 or any(p in ("", ".", "..", ".git") or ":" in p or "\\" in p for p in parts)):
                    raise ValueError(f"unsafe candidate member: {member.name}")
                relative = PurePosixPath(*parts[1:])
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError(f"non-regular candidate member: {member.name}")
                if hydration_target(repo, relative, tracked) is None:
                    continue
                source = bundle.extractfile(member)
                if source is None:
                    raise ValueError(f"candidate member cannot be read: {member.name}")
                with source:
                    if copy_hydration_file(repo, relative, tracked, source, member.mode):
                        copied.append(relative.as_posix())
        print(f"HYDRATE {name}: copied {len(copied) - before} absent files", flush=True)
    print(f"HYDRATED_RETAIL_FREE_BETA_INPUTS files={len(copied)}", flush=True)
    return copied


def hydrate_release(repo: Path, work: Path) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="hydrate-beta-50-", dir=work) as temporary:
        inputs = Path(temporary)
        command = ["gh", "release", "download", RELEASE_TAG, "--repo", RELEASE_REPO]
        for name in RELEASE_ARCHIVES:
            command.extend(["--pattern", name])
        command.extend(["--dir", str(inputs)])
        subprocess.run(command, check=True, timeout=600)
        return hydrate_archives(repo, inputs)


def test_count(output: str) -> int | None:
    matches = re.findall(r"Ran ([0-9]+) test", output)
    return int(matches[-1]) if matches else None


@dataclass
class Result:
    name: str
    rc: int = 0
    output: str = ""
    skipped: str | None = None


def summary(results: list[Result]) -> str:
    skipped = sum(r.skipped is not None for r in results)
    failed = sum(r.rc != 0 and r.skipped is None for r in results)
    total = sum((test_count(r.output) or 0) for r in results if r.skipped is None)
    return (f"SUMMARY: files={len(results)} passed={len(results) - failed - skipped} "
            f"failed={failed} skipped={skipped} tests={total}")


def wine_environment(prefix: Path, repo_windows: str | None = None) -> dict[str, str]:
    env = dict(os.environ)
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "PYTHONPATH", "PYTHONHOME", "WINEARCH",
                "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        env.pop(key, None)
    env.update(WINEPREFIX=str(prefix), WINEDEBUG="-all", QT_QPA_PLATFORM="offscreen",
               MOD_STUDIO_NO_UPDATE_CHECK="1", PYTHONFAULTHANDLER="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    # Prevent Wine's first-boot installers and desktop/audio integration.
    env["WINEDLLOVERRIDES"] = "winemenubuilder.exe,mscoree,mshtml,winealsa.drv,winepulse.drv=d"
    if repo_windows is not None:
        env["PYTHONPATH"] = repo_windows
    return env


def pth_text() -> str:
    return "winci-bootstrap\npython312.zip\n.\nLib\\site-packages\nimport site\n"


def installer_module():
    spec = importlib.util.spec_from_file_location(
        "_winci_installer", Path(__file__).with_name("build_windows_installer.py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ensure_runtime(work: Path) -> Path:
    builder = installer_module()
    key = hashlib.sha256(Path(builder.__file__).read_bytes()).hexdigest()
    marker = work / "runtime-key"
    runtime = work / "runtime"
    if not (marker.is_file() and marker.read_text() == key and (runtime / "python.exe").is_file()):
        marker.unlink(missing_ok=True)
        downloads = work / "dl"
        downloads.mkdir(exist_ok=True)
        print("Building the installer's hash-pinned Windows runtime...", flush=True)
        builder.build_runtime(work, downloads)
        marker.write_text(key)
    private = work / "runner-runtime"
    private_key = hashlib.sha256((key + STARTUP + pth_text()).encode()).hexdigest()
    private_marker = work / "runner-runtime-key"
    if not (private_marker.is_file() and private_marker.read_text() == private_key
            and (private / "python.exe").is_file()):
        private_marker.unlink(missing_ok=True)
        if private.exists():
            shutil.rmtree(private)
        shutil.copytree(runtime, private)
        (private / "python312._pth").write_text(pth_text(), encoding="utf-8")
        bootstrap = private / "winci-bootstrap"
        bootstrap.mkdir()
        (bootstrap / "sitecustomize.py").write_text(STARTUP, encoding="utf-8")
        private_marker.write_text(private_key)
    return private


@contextmanager
def exclusive(path: Path):
    import fcntl  # The runner executes on Linux; pure helpers also import on Windows.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f"another runner owns {path}") from None
        yield


def kill_group(process: subprocess.Popen) -> None:
    # Signal even if the launcher has already exited: children may remain.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def _pump(stream, output, lock: threading.Lock) -> None:
    # Wine's python.exe dies in init_sys_streams ("[WinError 6] Invalid handle")
    # when its stdout is a regular file, and runs fine on a pipe (verified
    # 2026-09-05 on wine-9.0 with the 3.12.10 embeddable build). So every child
    # writes to a pipe and this thread copies it into the log file. Reading to
    # EOF also cannot block forever: the timeout path kills the whole process
    # group, which closes every write end a grandchild may still hold.
    with stream:
        for chunk in iter(lambda: stream.read(4096), b""):
            with lock:
                output.write(chunk.decode("utf-8", "replace"))
                output.flush()


def run_process(command: list[str], env: dict[str, str], cwd: Path, log: Path,
                timeout: float, pidfile: Path | None = None) -> int:
    with log.open("w", encoding="utf-8") as output:
        if _cancelled.is_set():
            raise KeyboardInterrupt
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        lock = threading.Lock()
        pump = threading.Thread(target=_pump, args=(process.stdout, output, lock), daemon=True)
        pump.start()

        def note(text: str) -> None:
            with lock:
                output.write(text)
                output.flush()
        try:
            deadline = time.monotonic() + timeout
            while True:
                if _cancelled.is_set():
                    raise KeyboardInterrupt
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    rc = process.wait(timeout=min(remaining, 0.2))
                except subprocess.TimeoutExpired:
                    continue
                pump.join(timeout=30)
                return rc
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            # taskkill covers Win32 descendants; killpg covers the Unix Wine
            # launcher and same-group children. Never kill a shared wineserver.
            if pidfile and pidfile.is_file():
                pid = pidfile.read_text(encoding="ascii").strip()
                if pid.isdecimal():
                    try:
                        killer = subprocess.Popen(
                            ["wine", "taskkill", "/PID", pid, "/T", "/F"], env=env,
                            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                            start_new_session=True)
                        try:
                            kill_rc = killer.wait(timeout=30)
                            if kill_rc:
                                note(f"taskkill failed (rc={kill_rc}); killing Unix process group\n")
                        except subprocess.TimeoutExpired:
                            note("taskkill timed out; killing Unix process group\n")
                        finally:
                            kill_group(killer)
                    except OSError as exc:
                        note(f"taskkill could not start: {exc}\n")
            kill_group(process)
            pump.join(timeout=10)
            if isinstance(error, KeyboardInterrupt):
                raise
            note(f"\nTIMED OUT after {timeout:g}s (killed by local CI per-file timeout)\n")
            return 124


def checked(command: list[str], env: dict[str, str], cwd: Path, log: Path,
            timeout: float = 120) -> str:
    rc = run_process(command, env, cwd, log, timeout)
    output = log.read_text(encoding="utf-8", errors="replace")
    if rc:
        hint = " (SIGSYS: execution sandbox denied a system call)" if rc in (-31, 159) else ""
        raise RuntimeError(f"{command[0]} failed (rc={rc}){hint}; log: {log}\n{output[-6000:]}")
    return output.strip()


def windows_path(path: Path, env: dict[str, str], logs: Path) -> str:
    return checked(["winepath", "-w", str(path.resolve())], env, path.parent,
                   logs / "winepath.log").splitlines()[-1]


def ensure_prefix(prefix: Path, env: dict[str, str], logs: Path) -> None:
    marker = prefix / ".winci-prefix"
    if not marker.is_file():
        if prefix.exists() and any(prefix.iterdir()):
            raise RuntimeError(f"refusing an existing unowned Wine prefix: {prefix}; choose an empty dedicated directory")
        prefix.mkdir(parents=True, exist_ok=True)
        # Ownership survives interrupted wineboot so the next run can retry.
        marker.write_text("initializing\n")
    if marker.read_text() != "ready\n" or not (prefix / "system.reg").is_file():
        print(f"Initializing headless Wine prefix: {prefix}", flush=True)
        checked(["wineboot", "-u"], env, prefix, logs / "wineboot.log", 180)
        marker.write_text("ready\n")


def prove_imports(runtime: Path, repo_windows: str,
                 env: dict[str, str], logs: Path, work: Path) -> None:
    normal = dict(env, PYTHONPATH=repo_windows)
    probe = ("import mod_editor,pathlib; p=pathlib.Path(mod_editor.__file__).resolve(); "
             "print(p); assert p.is_relative_to(pathlib.Path(" + repr(repo_windows) + ").resolve())")
    print("IMPORT normal: " + checked(["wine", str(runtime / "python.exe"), "-c", probe],
                                     normal, work, logs / "import-normal.log"), flush=True)
    # A synthetic stage proves isolated child lookup without depending on
    # product release inputs. It has the same module name but a distinct path.
    stage = work / "import-probe-stage"
    package = stage / "mod_editor"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("# runner import-isolation probe\n")
    isolated_probe = ("import mod_editor,pathlib; p=pathlib.Path(mod_editor.__file__).resolve(); "
                      "print(p); assert p.parent.parent == pathlib.Path.cwd(); "
                      "assert p.parent != (pathlib.Path(" + repr(repo_windows) + ") / 'mod_editor').resolve()")
    child = "import subprocess,sys; subprocess.run([sys.executable, '-c', " + repr(isolated_probe) + "], check=True)"
    print("IMPORT isolated child: " + checked(["wine", str(runtime / "python.exe"), "-c", child],
                                             env, stage, logs / "import-isolated.log"), flush=True)


def run_file(test: Path, repo: Path, repo_windows: str, runtime: Path,
             env: dict[str, str], logs: Path, timeout: float, logs_windows: str) -> Result:
    log = logs / f"{test.name}.log"
    reason = skip_reason(repo, test.name)
    if reason:
        log.write_text(f"SKIP  {test.name}  ({reason})\n", encoding="utf-8")
        return Result(test.name, skipped=reason)
    file_env = dict(env)
    if test.name != ISOLATED:
        file_env["PYTHONPATH"] = repo_windows
    pidfile = logs / f"{test.name}.pid"
    pidfile.unlink(missing_ok=True)
    script = repo_windows.rstrip("\\") + "\\tests\\mod_editor\\" + test.name
    pid_windows = logs_windows.rstrip("\\") + "\\" + pidfile.name
    try:
        rc = run_process(["wine", str(runtime / "python.exe"), "-u", "-c", BOOTSTRAP,
                          script, pid_windows], file_env, repo, log, timeout, pidfile)
    except OSError as error:
        log.write_text(f"Could not launch test: {error}\n", encoding="utf-8")
        rc = 127
    finally:
        pidfile.unlink(missing_ok=True)
    output = log.read_text(encoding="utf-8", errors="replace")
    return Result(test.name, rc, output, wine_gap_reason(test.name, rc, output))


def report_result(result: Result) -> None:
    if result.skipped:
        print(f"SKIP {result.name} ({result.skipped})", flush=True)
    elif result.rc == 0:
        n = test_count(result.output)
        print(f"PASS  {result.name}  ({n if n is not None else '?'} tests)", flush=True)
    else:
        print(f"FAIL  {result.name}  (rc={result.rc})", flush=True)
        print("\n".join(result.output.splitlines()[-40:]))
        print("-" * 70, flush=True)


def main(argv: list[str] | None = None) -> int:
    _cancelled.clear()
    parser = argument_parser()
    args = parser.parse_args(argv)
    if sys.platform != "linux":
        parser.error("this runner requires a Linux host with Wine")
    repo = args.repo.expanduser().resolve()
    work = args.work.expanduser().resolve()
    prefix = (args.prefix or work / "prefix").expanduser().resolve()
    started = time.monotonic()
    try:
        if not (repo / "tests/mod_editor").is_dir():
            raise ValueError(f"not a test checkout: {repo}")
        tests = plan(repo, args.only, changed_paths(repo) if args.changed else None)
        if not tests and not args.os_check:
            if args.changed:
                print("No affected test files.")
                print(summary([]))
                print("ALL TEST FILES PASSED")
                return 0
            raise ValueError("no test files found under tests/mod_editor/test_*.py")
        for command in ("wine", "winepath", "wineboot"):
            if not shutil.which(command):
                raise RuntimeError(f"required command is absent: {command}")
        work.mkdir(parents=True, exist_ok=True)
        with exclusive(work / ".runner.lock"), exclusive(prefix.with_name(prefix.name + ".winci.lock")):
            logs = work / "logs"
            logs.mkdir(exist_ok=True)
            env = wine_environment(prefix)
            # Fail before downloads when Wine cannot even execute on this host.
            print("Wine: " + checked(["wine", "--version"], env, work, logs / "wine-version.log"), flush=True)
            if args.hydrate_from:
                hydrate_from(repo, args.hydrate_from)
            elif args.hydrate_release:
                hydrate_release(repo, work)
            runtime = ensure_runtime(work)
            ensure_prefix(prefix, env, logs)
            temp_windows = checked(["wine", str(runtime / "python.exe"), "-c", TEMP_PROBE],
                                   env, work, logs / "temp-check.log")
            env.update(TEMP=temp_windows, TMP=temp_windows)
            print(f"TEMP/TMP: {temp_windows}", flush=True)
            facts = checked(["wine", str(runtime / "python.exe"), "-c", OS_PROBE],
                            env, work, logs / "os-check.log")
            print("OS CHECK: " + facts, flush=True)
            repo_windows = windows_path(repo, env, logs)
            prove_imports(runtime, repo_windows, env, logs, work)
            if args.os_check:
                return 0
            logs_windows = windows_path(logs, env, logs)
            print(f"Running {len(tests)} files; jobs={args.jobs}; timeout={args.timeout:g}s; logs={logs}", flush=True)
            results = []
            # map preserves CI's filename/report ordering while workers run in
            # parallel. Continue after failures, just like the hosted loop.
            with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                try:
                    for result in pool.map(lambda test: run_file(test, repo, repo_windows, runtime,
                                                               env, logs, args.timeout, logs_windows), tests):
                        results.append(result)
                        report_result(result)
                except KeyboardInterrupt:
                    _cancelled.set()
                    pool.shutdown(wait=True, cancel_futures=True)
                    raise
            print("=" * 70)
            print(summary(results))
            failed = [r.name for r in results if r.rc and r.skipped is None]
            print("FAILED FILES: " + " ".join(failed) if failed else "ALL TEST FILES PASSED")
            print(f"WALL CLOCK: {time.monotonic() - started:.3f}s", flush=True)
            return int(bool(failed))
    except (OSError, ValueError, RuntimeError, tarfile.TarError, subprocess.SubprocessError) as error:
        print(f"SETUP FAILED: {error}", file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        print("INTERRUPTED", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
