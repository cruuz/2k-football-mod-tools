"""Update the studio in place: download the new release, verify it, install it, reopen.

The update banner used to open the releases page and leave the rest to the
user.  This module does the rest, on every platform the editors ship for, with
the same discipline as everything else here: nothing is written that was not
verified first, and the user is told what is about to happen.

* **Windows installer** (``runtime\\pythonw.exe`` beside ``app\\``, the layout
  ``build_windows_installer.py`` produces): the new ``Setup.exe`` and its
  ``.sha256`` sidecar are downloaded, the digest is checked, and the installer
  is started detached with ``/S /WAITPID=<this pid> /RELAUNCH /D=<folder>``.
  The installer waits for this process to exit before it touches a file (it
  overwrites ``runtime\\`` and ``app\\``, so nothing from either may still be
  running), installs silently into the same folder, and starts the studio
  again.  Both switches are implemented in the installer template.
* **Tarball** (``tools/launch_<product>.sh`` or the ``.bat`` at the root):
  the archive and its sidecar are downloaded and verified, unpacked beside the
  install, the folders are swapped (the old one is kept as
  ``<name>.previous``), and the studio is relaunched from the new folder.
* **A git checkout** is never updated by this module: use ``git pull``.

Every step reports through a progress callback so the banner can show it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from typing import Callable, Mapping, Sequence
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
ProgressSink = Callable[[str, int, int], None]
USER_AGENT = "2k-football-mod-tools-self-update"
MAX_ASSET_BYTES = 400 * 1024 * 1024
CHUNK = 1 << 20
STARTUP_TIMEOUT_SECONDS = 60.0
UNSUPPORTED_LAYOUT_MESSAGE = (
    "This copy was not installed with the Setup or the portable archive; "
    "download the latest Setup.exe from the release page and run it. "
    "The release page is on GitHub."
)

# Release identities from BETA_RELEASE_NOTES.md, not an RC-minus-offset guess.
# Older RC labels can name more than one shared product release (notably RC62).
_RC_RELEASES = {77: 53, 78: 54, 79: 55, 80: 56, 81: 57,
                82: 58, 83: 59, 84: 60, 85: 61, 86: 62}


def canonical_release_tag(label: str) -> str:
    """Resolve known installed 2K5 version spellings to the published beta tag."""
    label = label.strip()
    match = re.fullmatch(r"(?:v?1\.0(?:\.0)?[- ]?)?rc[- ]?(\d+)", label, re.IGNORECASE)
    if match and int(match[1]) in _RC_RELEASES:
        return f"beta-{_RC_RELEASES[int(match[1])]}"
    return label

#: Asset name patterns per product and install kind.
PRODUCTS: dict[str, dict[str, object]] = {
    "2k5": {
        "installer": re.compile(r"^2K5-Mod-Studio-[^/]*-Setup\.exe$"),
        "tarball": re.compile(r"^2K5-Mod-Studio-v[^/]*\.tar\.gz$"),
        "launcher_sh": "tools/launch_2k5_mod_studio.sh",
        "launcher_bat": "2K5-Mod-Studio.bat",
        "module": "mod_editor",
        "args": ("-m", "mod_editor", "--studio"),
        "name": "2K5 Mod Studio",
    },
    "apf": {
        "installer": re.compile(r"^APF-2K8-Mod-Studio-[^/]*-Setup\.exe$"),
        "tarball": re.compile(r"^apf2k8-mod-studio-[^/]*\.tar\.gz$"),
        "launcher_sh": "tools/launch_apf2k8_mod_studio.sh",
        "launcher_bat": "APF-2K8-Mod-Studio.bat",
        "module": "mod_editor.apf_studio",
        "args": ("-m", "mod_editor.apf_studio"),
        "name": "APF 2K8 Mod Studio",
    },
}


class SelfUpdateError(RuntimeError):
    """A refusal with a message the banner can show."""


class _RestoreError(SelfUpdateError):
    """The original tree is safe but could not be renamed back automatically."""


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int


@dataclass(frozen=True)
class InstallKind:
    kind: str                       # "windows-installer" | "tarball" | "checkout" | "unknown"
    root: Path                      # the application root (the folder holding mod_editor/)
    relaunch: tuple[str, ...]       # the command that starts this install again
    detail: str = ""


@dataclass
class UpdatePlan:
    product: str
    tag: str
    install: InstallKind
    asset: ReleaseAsset
    sidecar: ReleaseAsset | None
    notes: list[str] = field(default_factory=list)

    @property
    def size_mb(self) -> float:
        return self.asset.size / (1024 * 1024)


# ------------------------------------------------------------------ where am I installed

def detect_install(root: Path | None = None, product: str = "2k5", *, platform: str | None = None,
                   executable: str | None = None) -> InstallKind:
    """What kind of install this process runs from, and how to start it again."""
    root = Path(root or ROOT).resolve()
    platform = platform or sys.platform
    executable = executable or sys.executable
    spec = PRODUCTS[product]
    args = tuple(str(a) for a in spec["args"])  # type: ignore[index]
    if (root / ".git").exists() or (root.parent / ".git").exists():
        return InstallKind("checkout", root, (executable, *args), "a git checkout updates with git pull")
    # GitHub's source ZIP contains the launchers too. It is not a portable
    # release and must never be swapped out as though it were one.
    # The release allowlist also ships a few tests. That directory alone does
    # not identify a source ZIP (beta 70's portable archive contains it).
    if (root / ".github").is_dir():
        return InstallKind("unknown", root, (executable, *args), UNSUPPORTED_LAYOUT_MESSAGE)
    runtime = root.parent / "runtime"
    pythonw = runtime / "pythonw.exe"
    if root.name.lower() == "app" and pythonw.is_file() and platform.startswith("win"):
        return InstallKind("windows-installer", root, (str(pythonw), *args), str(root.parent))
    if (root / str(spec["launcher_sh"])).is_file() or (root / str(spec["launcher_bat"])).is_file():
        if platform.startswith("win") and root.name.lower() == "app" and not pythonw.is_file():
            return InstallKind("unknown", root, (executable, *args), UNSUPPORTED_LAYOUT_MESSAGE)
        return InstallKind("tarball", root, (executable, *args), str(root))
    if (root / "mod_editor" / "__main__.py").exists():
        return InstallKind("unknown", root, (executable, *args), "the folder carries no launcher this updater knows")
    return InstallKind("unknown", root, (executable, *args), "not an installed studio")


# ------------------------------------------------------------------ what to fetch

def release_assets(document: Mapping[str, object]) -> list[ReleaseAsset]:
    out: list[ReleaseAsset] = []
    for item in document.get("assets", []) or []:
        if not isinstance(item, Mapping):
            continue
        name, url, size = item.get("name"), item.get("browser_download_url"), item.get("size")
        if isinstance(name, str) and isinstance(url, str) and url.startswith("https://") and isinstance(size, int):
            out.append(ReleaseAsset(name, url, size))
    return out


def plan_update(document: Mapping[str, object], install: InstallKind, product: str = "2k5") -> UpdatePlan:
    """Pick the right asset (and its .sha256) for this install from a release document."""
    spec = PRODUCTS[product]
    tag = str(document.get("tag_name") or "")
    assets = release_assets(document)
    if install.kind == "windows-installer":
        pattern = spec["installer"]
    elif install.kind == "tarball":
        pattern = spec["tarball"]
    elif install.kind == "checkout":
        raise SelfUpdateError("This is a git checkout: update it with git pull.")
    else:
        raise SelfUpdateError(UNSUPPORTED_LAYOUT_MESSAGE)
    assert isinstance(pattern, re.Pattern)
    candidates = [a for a in assets if pattern.match(a.name)]
    if not candidates:
        raise SelfUpdateError(f"Release {tag} has no {'installer' if install.kind == 'windows-installer' else 'archive'} for {spec['name']}.")
    asset = candidates[0]
    if asset.size <= 0 or asset.size > MAX_ASSET_BYTES:
        raise SelfUpdateError(f"{asset.name} has an unexpected size ({asset.size} bytes).")
    sidecar = next((a for a in assets if a.name == asset.name + ".sha256"), None)
    plan = UpdatePlan(product, tag, install, asset, sidecar)
    if sidecar is None:
        raise SelfUpdateError("The release has no .sha256 sidecar for this file; use Get the update or try again after it is published.")
    return plan


# ------------------------------------------------------------------ download + verify

def _open(url: str, timeout: float):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout)


def download(asset: ReleaseAsset, destination: Path, *, progress: ProgressSink | None = None,
             timeout: float = 30.0, opener: Callable[..., object] | None = None) -> Path:
    """Stream one asset to ``destination`` (written whole or not at all)."""
    progress = progress or (lambda *_a: None)
    opener = opener or _open
    part = destination.with_name(destination.name + ".part")
    done = 0
    try:
        with opener(asset.url, timeout) as response, open(part, "wb") as handle:  # type: ignore[misc]
            status = getattr(response, "status", 200)
            if status != 200:
                raise SelfUpdateError(f"GitHub answered {status} for {asset.name}")
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if done > MAX_ASSET_BYTES:
                    raise SelfUpdateError(f"{asset.name} is larger than allowed")
                progress(f"Downloading {asset.name}", done, asset.size)
            handle.flush()
            os.fsync(handle.fileno())
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        part.unlink(missing_ok=True)
        raise SelfUpdateError(f"Could not download {asset.name}: {exc}") from exc
    except SelfUpdateError:
        part.unlink(missing_ok=True)
        raise
    if asset.size and done != asset.size:
        part.unlink(missing_ok=True)
        raise SelfUpdateError(f"{asset.name}: downloaded {done} bytes, GitHub lists {asset.size}")
    os.replace(part, destination)
    return destination


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_sidecar(text: str, expected_name: str) -> str:
    """The digest out of a ``<hex>  <name>`` sidecar; refuses another file's line."""
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]) and parts[-1].lstrip("*") == expected_name:
            return parts[0].lower()
    raise SelfUpdateError(f"the .sha256 sidecar does not name {expected_name}")


def verify(path: Path, sidecar_text: str) -> str:
    expected = parse_sidecar(sidecar_text, path.name)
    actual = sha256_file(path)
    if actual != expected:
        path.unlink(missing_ok=True)
        raise SelfUpdateError(f"{path.name} did not match its published SHA-256; the download was discarded")
    return actual


def fetch_update(plan: UpdatePlan, work: Path, *, progress: ProgressSink | None = None,
                 opener: Callable[..., object] | None = None) -> Path:
    """Download the planned asset into ``work`` and verify it against its sidecar."""
    if plan.sidecar is None:
        raise SelfUpdateError("The release has no .sha256 sidecar; refusing to download an unverifiable update.")
    progress = progress or (lambda *_a: None)
    work.mkdir(parents=True, exist_ok=True)
    target = work / plan.asset.name
    download(plan.asset, target, progress=progress, opener=opener)
    if plan.sidecar is not None:
        sidecar_path = work / plan.sidecar.name
        download(plan.sidecar, sidecar_path, progress=progress, opener=opener)
        progress("Verifying the download", 0, 1)
        verify(target, sidecar_path.read_text(encoding="utf-8", errors="replace"))
        progress("Verified", 1, 1)
    else:
        raise SelfUpdateError("The release has no .sha256 sidecar; refusing to install an unverified download.")
    return target


# ------------------------------------------------------------------ apply: Windows installer

def windows_install_command(installer: Path, install_dir: Path, pid: int, *, relaunch: bool = True) -> str:
    """The exact command line, as ONE string: NSIS wants ``/D=`` last and unquoted, even with spaces."""
    parts = [f'"{installer}"', "/S", f"/WAITPID={pid}"]
    if relaunch:
        parts.append("/RELAUNCH")
    parts.append(f"/D={install_dir}")
    return " ".join(parts)


def apply_windows_installer(plan: UpdatePlan, installer: Path, *, pid: int | None = None,
                            spawn: Callable[[str], object] | None = None) -> str:
    """Start the installer detached; it waits for this process to exit (``/WAITPID``), installs
    silently into the same folder, and reopens the studio (``/RELAUNCH``). The caller quits."""
    install_dir = plan.install.root.parent
    command = windows_install_command(installer, install_dir, pid or os.getpid())
    if spawn is None:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(command, creationflags=flags, close_fds=True, cwd=str(installer.parent),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        spawn(command)
    return command


# ------------------------------------------------------------------ apply: tarball

def _safe_members(archive: tarfile.TarFile, top: str) -> list[tarfile.TarInfo]:
    members = []
    for member in archive.getmembers():
        name = member.name
        if name.startswith("/") or ".." in Path(name).parts or (not name.startswith(top + "/") and name != top):
            raise SelfUpdateError(f"the archive contains an unexpected path: {name}")
        if member.issym() or member.islnk():
            raise SelfUpdateError(f"the archive contains a link: {name}")
        if not (member.isdir() or member.isfile()):
            raise SelfUpdateError(f"the archive contains a special file: {name}")
        if "__pycache__" in Path(name).parts or name.endswith((".pyc", ".pyo")):
            continue
        members.append(member)
    return members


def unpack_tarball(tarball: Path, parent: Path, *, progress: ProgressSink | None = None) -> Path:
    """Strip one archive root into a fresh sibling; never merge with an install."""
    progress = progress or (lambda *_a: None)
    try:
        return _unpack_tarball(tarball, parent, progress)
    except (OSError, tarfile.TarError) as exc:
        raise SelfUpdateError(f"The release could not be unpacked: {exc}") from exc


def _unpack_tarball(tarball: Path, parent: Path, progress: ProgressSink) -> Path:
    with tarfile.open(tarball, "r:gz") as archive:
        first = archive.next()
        if first is None:
            raise SelfUpdateError("the archive is empty")
        top = first.name.split("/")[0]
        if not top or top in (".", ".."):
            raise SelfUpdateError("the archive has no application folder")
        members = _safe_members(archive, top)
        parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{top}.new-", dir=parent))
        try:
            directories = []
            for index, member in enumerate(members):
                relative = Path(member.name).relative_to(top)
                target = staging / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    directories.append((target, member.mode & 0o777))
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = archive.extractfile(member)
                    assert source is not None
                    with source, open(target, "xb") as handle:
                        shutil.copyfileobj(source, handle)
                    target.chmod(member.mode & 0o777)
                if index % 50 == 0:
                    progress("Unpacking", index, len(members))
            if not (staging / "mod_editor" / "__main__.py").is_file():
                raise SelfUpdateError("the archive does not contain the studio")
            for target, mode in reversed(directories):
                target.chmod(mode)
            progress("Unpacking", len(members), len(members))
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    return staging


def swap_install(current: Path, staging: Path) -> Path:
    """Two same-filesystem atomic renames, retaining every previous backup."""
    previous = _unused_sibling(current, ".previous")
    os.replace(current, previous)
    try:
        os.replace(staging, current)
    except OSError as exc:
        try:
            os.replace(previous, current)
        except OSError as restore_error:
            raise _RestoreError(f"The update could not be installed ({exc}) or restored ({restore_error}). "
                                f"Your old version is safe at {previous}. Move it back to {current} before reopening.") from exc
        raise
    return previous


def _unused_sibling(root: Path, suffix: str) -> Path:
    candidate = root.with_name(root.name + suffix)
    if os.path.lexists(candidate):
        candidate = root.with_name(root.name + suffix + "-" + uuid.uuid4().hex)
    return candidate


def _stage_python(plan: UpdatePlan, staging: Path) -> str:
    """Keep the active home-directory runtime, without moving the running copy.

    Do not resolve the executable's symlink: a venv's bin/python often links to
    an external Python but needs its local pyvenv.cfg and site-packages.
    """
    root = plan.install.root
    executable = Path(os.path.abspath(shutil.which(plan.install.relaunch[0])
                                     or plan.install.relaunch[0]))
    try:
        relative = executable.relative_to(root)
    except ValueError:
        staged_python = str(executable)
        saved_python = staged_python
    else:
        if len(relative.parts) < 3 or relative.parts[0] in {"mod_editor", "tools"}:
            raise SelfUpdateError("The local Python runtime layout is not supported. Keep this copy and install the release in a separate folder.")
        runtime = relative.parts[0]
        if (staging / runtime).exists():
            raise SelfUpdateError(f"The release conflicts with your Python runtime folder: {runtime}")
        shutil.copytree(root / runtime, staging / runtime, symlinks=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        # Absolute links into the old runtime must work in staging and after
        # either rename. Keep external base-Python links as they were.
        for link in (staging / runtime).rglob("*"):
            if link.is_symlink():
                target = Path(os.readlink(link))
                if target.is_absolute() and target.is_relative_to(root):
                    replacement = staging / target.relative_to(root)
                    link.unlink()
                    link.symlink_to(os.path.relpath(replacement, link.parent))
        staged_python = str(staging / relative)
        saved_python = str(relative)
    (staging / ".studio-python").write_text(saved_python + "\n", encoding="utf-8")
    return staged_python


def _launch_environment(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONSTARTUP", "MOD_STUDIO_UPDATE_READY"):
        env.pop(key, None)
    env.update(PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    return env


def check_tarball_launch(root: Path, executable: str, product: str) -> str:
    """Import the staged app and its GUI without creating a window; print version."""
    module = str(PRODUCTS[product]["module"])
    gui = "mod_editor.gui.studio_qt" if product == "2k5" else "mod_editor.apf_studio.gui"
    launcher = root / str(PRODUCTS[product]["launcher_sh"])
    if not sys.platform.startswith("win") and (not launcher.is_file() or not os.access(launcher, os.X_OK)):
        raise SelfUpdateError(f"The new release's launcher is missing or is not executable: {launcher}")
    code = (
        "import importlib, pathlib; "
        f"app = importlib.import_module({module!r}); "
        "assert pathlib.Path(app.__file__).resolve().is_relative_to(pathlib.Path.cwd()), 'wrong app imported'; "
        f"importlib.import_module({module + '.__main__'!r}); "
        f"importlib.import_module({gui!r}); "
        "print(app.__version__)"
    )
    result = subprocess.run([executable, "-B", "-s", "-c", code], cwd=root,
                            env=_launch_environment(root), capture_output=True,
                            text=True, timeout=60)
    if result.returncode or not result.stdout.strip():
        detail = result.stderr.strip().splitlines()
        raise SelfUpdateError(f"The new version failed its launch check (exit {result.returncode}). "
                              + (detail[-1][-1000:] if detail else "No version was printed."))
    return result.stdout.strip()


def notify_update_ready() -> None:
    """Called by the GUI after showing its main window, on its first event loop."""
    ready = os.environ.pop("MOD_STUDIO_UPDATE_READY", "")
    if ready:
        from PyQt5.QtCore import QTimer
        def acknowledge() -> None:
            try:
                Path(ready).write_text("ready\n", encoding="utf-8")
            except OSError:
                pass  # The waiting updater will restore the old version.
        QTimer.singleShot(0, acknowledge)


def _start_tarball(command: Sequence[str], root: Path) -> None:
    """Wait for the new window's event loop, retaining stderr on startup failure."""
    with tempfile.TemporaryDirectory(prefix=".studio-start-", dir=root.parent) as folder:
        ready = Path(folder) / "ready"
        env = _launch_environment(root)
        env["MOD_STUDIO_UPDATE_READY"] = str(ready)
        # Keep the logfile after the short-lived handshake directory is gone.
        log_path = root / ".update-launch.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen(command, cwd=root, env=env, close_fds=True,
                                       start_new_session=not sys.platform.startswith("win"),
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                status = process.poll()
                if status is not None:
                    detail = log_path.read_text(errors="replace").strip().splitlines()
                    raise SelfUpdateError(f"The new studio exited before opening (exit {status}). "
                                          + (detail[-1][-1000:] if detail else "No startup message was produced."))
                if ready.is_file():
                    return
                time.sleep(0.1)
            raise SelfUpdateError(f"The new studio did not confirm that its window opened within {STARTUP_TIMEOUT_SECONDS:g} seconds.")
        except Exception:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise


def apply_tarball(plan: UpdatePlan, tarball: Path, *, progress: ProgressSink | None = None,
                  spawn: Callable[[Sequence[str], Path], object] | None = None) -> tuple[Path, list[str]]:
    """Check a complete sibling before switching; restore the old copy on failure.

    ``spawn`` is a synchronous test/integration hook: it must return only after
    startup is confirmed, and raise if the new app fails to start.
    """
    progress = progress or (lambda *_a: None)
    root = plan.install.root
    parent = root.parent
    if not os.access(parent, os.W_OK):
        raise SelfUpdateError(f"{parent} is not writable, so the studio cannot replace itself there. "
                              "Move the folder somewhere you own, or download the release from GitHub.")
    lock = root.with_name(root.name + ".update-lock")
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise SelfUpdateError(f"Another update is using this folder. Your old version is at {root}. "
                              f"If no update is running, remove {lock} and try again.") from exc
    staging = None
    previous = None
    try:
        staging = unpack_tarball(tarball, parent, progress=progress)
        staging.chmod(root.stat().st_mode & 0o777)
        staged_python = _stage_python(plan, staging)
        progress("Checking that the new version can start", 0, 1)
        version = check_tarball_launch(staging, staged_python, plan.product)
        command = [staged_python, *map(str, PRODUCTS[plan.product]["args"])]
        if Path(staged_python).is_relative_to(staging):
            command[0] = str(root / Path(staged_python).relative_to(staging))
        progress(f"Checked version {version}; switching folders", 0, 1)
        previous = swap_install(root, staging)
        # Check again at its final path (venv relocation and absolute paths).
        check_tarball_launch(root, command[0], plan.product)
        progress("Waiting for the new studio to open", 0, 1)
        if spawn is None:
            _start_tarball(command, root)
        else:
            spawn(command, root)
        plan.notes.append(f"Installed {version}. The previous version is kept at {previous}.")
        progress(plan.notes[-1], 1, 1)
        return root, command
    except _RestoreError:
        raise
    except Exception as exc:
        if previous is None:
            raise SelfUpdateError(f"The update was not installed: {exc}\n"
                                  f"Your old version is unchanged at {root}. Keep using it or download the release again.") from exc
        failed = _unused_sibling(root, ".failed-update")
        try:
            os.replace(root, failed)
            os.replace(previous, root)
        except OSError as rollback_error:
            raise SelfUpdateError(f"The new version could not start: {exc}\n"
                                  f"Automatic restore failed: {rollback_error}. Your old version is at {previous}; "
                                  f"move it back to {root} before reopening. The failed update is at {failed}.") from exc
        raise SelfUpdateError(f"The new version could not start: {exc}\n"
                              f"Your old version was restored at {root}. Keep using it. "
                              f"The failed update and its startup log are at {failed}.") from exc
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        lock.rmdir()


# ------------------------------------------------------------------ one call for the banner

def run_update(document: Mapping[str, object], product: str = "2k5", *, progress: ProgressSink | None = None,
               install: InstallKind | None = None, work: Path | None = None,
               opener: Callable[..., object] | None = None,
               spawn_windows: Callable[[str], object] | None = None,
               spawn_tarball: Callable[[Sequence[str], Path], object] | None = None) -> UpdatePlan:
    """Plan, download, verify and hand off the install. Raises SelfUpdateError with a plain message."""
    progress = progress or (lambda *_a: None)
    install = install or detect_install(product=product)
    plan = plan_update(document, install, product)
    owned_work = work is None
    work = work or Path(tempfile.mkdtemp(prefix="2k-mod-studio-update-"))
    try:
        asset_path = fetch_update(plan, work, progress=progress, opener=opener)
        if install.kind == "windows-installer":
            progress("Handing over to the installer", 0, 1)
            apply_windows_installer(plan, asset_path, spawn=spawn_windows)
            plan.notes.append("the installer runs as soon as the studio closes, then reopens it")
        else:
            apply_tarball(plan, asset_path, progress=progress, spawn=spawn_tarball)
    finally:
        # NSIS still needs its downloaded installer after the caller exits.
        if owned_work and install.kind != "windows-installer":
            shutil.rmtree(work, ignore_errors=True)
    return plan


__all__ = ["InstallKind", "ReleaseAsset", "SelfUpdateError", "UpdatePlan", "PRODUCTS", "detect_install",
           "release_assets", "plan_update", "download", "verify", "parse_sidecar", "fetch_update",
           "apply_windows_installer", "windows_install_command", "unpack_tarball", "swap_install", "apply_tarball",
           "run_update"]
