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
from typing import Callable, Mapping, Sequence
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
ProgressSink = Callable[[str, int, int], None]
USER_AGENT = "2k-football-mod-tools-self-update"
MAX_ASSET_BYTES = 400 * 1024 * 1024
CHUNK = 1 << 20

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
    runtime = root.parent / "runtime"
    pythonw = runtime / "pythonw.exe"
    if root.name.lower() == "app" and pythonw.exists() and platform.startswith("win"):
        return InstallKind("windows-installer", root, (str(pythonw), *args), str(root.parent))
    if (root / str(spec["launcher_sh"])).exists() or (root / str(spec["launcher_bat"])).exists():
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
        raise SelfUpdateError(f"This copy cannot update itself ({install.detail}). Download the release from GitHub instead.")
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
        plan.notes.append("no .sha256 sidecar was published for this asset; the download cannot be verified")
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
        members.append(member)
    return members


def unpack_tarball(tarball: Path, parent: Path, *, progress: ProgressSink | None = None) -> Path:
    """Unpack ``<top>/...`` from the archive into ``parent/<top>.new``; returns that folder."""
    progress = progress or (lambda *_a: None)
    with tarfile.open(tarball, "r:gz") as archive:
        first = archive.next()
        if first is None:
            raise SelfUpdateError("the archive is empty")
        top = first.name.split("/")[0]
        members = _safe_members(archive, top)
        staging = parent / f"{top}.new"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        for index, member in enumerate(members):
            relative = Path(member.name).relative_to(top) if member.name != top else Path(".")
            target = staging / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                assert source is not None
                with open(target, "wb") as handle:
                    shutil.copyfileobj(source, handle)
                if member.mode & 0o111:
                    target.chmod(target.stat().st_mode | 0o111)
            if index % 50 == 0:
                progress("Unpacking", index, len(members))
        progress("Unpacking", len(members), len(members))
    if not (staging / "mod_editor" / "__main__.py").exists():
        shutil.rmtree(staging, ignore_errors=True)
        raise SelfUpdateError("the archive does not contain the studio")
    return staging


def swap_install(current: Path, staging: Path) -> Path:
    """Replace ``current`` with ``staging``; the old folder stays as ``<current>.previous``."""
    previous = current.with_name(current.name + ".previous")
    if previous.exists():
        shutil.rmtree(previous)
    os.rename(current, previous)
    try:
        os.rename(staging, current)
    except OSError:
        os.rename(previous, current)
        raise
    return previous


def apply_tarball(plan: UpdatePlan, tarball: Path, *, progress: ProgressSink | None = None,
                  spawn: Callable[[Sequence[str], Path], object] | None = None) -> tuple[Path, list[str]]:
    """Unpack beside the install, swap the folders, start the new copy; the caller quits afterwards.

    Returns the folder the new version runs from and the command that started it. That folder is
    the current one when the swap succeeded, and a sibling named after the archive when something
    still held the current folder open (Windows refuses to rename a folder with an open file in it,
    and the ``.bat`` that started the studio is exactly that); the note on the plan says which."""
    progress = progress or (lambda *_a: None)
    root = plan.install.root
    parent = root.parent
    if not os.access(parent, os.W_OK):
        raise SelfUpdateError(f"{parent} is not writable, so the studio cannot replace itself there. "
                              "Move the folder somewhere you own, or download the release from GitHub.")
    staging = unpack_tarball(tarball, parent, progress=progress)
    progress("Switching to the new version", 0, 1)
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        cwd = None
    if cwd is not None and (cwd == root or root in cwd.parents):
        # a process whose working directory is inside the folder would block the rename (Windows refuses it)
        try:
            os.chdir(parent)
        except OSError:
            pass
    new_root = root
    try:
        swap_install(root, staging)
        plan.notes.append(f"installed over {root}; the previous version is kept beside it as {root.name}.previous")
    except OSError as exc:
        fallback = parent / staging.name[: -len(".new")]
        if fallback.exists():
            fallback = parent / f"{fallback.name}-{plan.tag}"
        try:
            os.rename(staging, fallback)
        except OSError as inner:
            raise SelfUpdateError(f"The new version was unpacked to {staging} but could not be moved into place "
                                  f"({inner}). Start it from there.") from inner
        new_root = fallback
        plan.notes.append(f"{root} could not be replaced while it was in use ({exc}); "
                          f"the new version is in {fallback}. Start it from there from now on; the old folder can be deleted.")
    progress("Switching to the new version", 1, 1)
    command = list(plan.install.relaunch)
    if spawn is None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(new_root)
        subprocess.Popen(command, cwd=str(new_root), env=env, close_fds=True,
                         start_new_session=not sys.platform.startswith("win"),
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        spawn(command, new_root)
    return new_root, command


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
    work = work or Path(tempfile.mkdtemp(prefix="2k-mod-studio-update-"))
    asset_path = fetch_update(plan, work, progress=progress, opener=opener)
    if install.kind == "windows-installer":
        progress("Handing over to the installer", 0, 1)
        apply_windows_installer(plan, asset_path, spawn=spawn_windows)
        plan.notes.append("the installer runs as soon as the studio closes, then reopens it")
    else:
        apply_tarball(plan, asset_path, progress=progress, spawn=spawn_tarball)
    return plan


__all__ = ["InstallKind", "ReleaseAsset", "SelfUpdateError", "UpdatePlan", "PRODUCTS", "detect_install",
           "release_assets", "plan_update", "download", "verify", "parse_sidecar", "fetch_update",
           "apply_windows_installer", "windows_install_command", "unpack_tarball", "swap_install", "apply_tarball",
           "run_update"]
