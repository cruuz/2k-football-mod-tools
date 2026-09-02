"""Persistent Xenia configuration and safe detached launch integration."""

from __future__ import annotations

from dataclasses import dataclass
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tempfile
from typing import Mapping

from mod_editor.core import platform_compat


class LaunchError(ValueError):
    """A Xenia setup or launch problem a non-expert can correct."""


# Xbox 360 All-Pro Football 2K8 title update 1.1 (LIVE STFS installer).
# Never shipped for PS3. The bytes are not in this repository; the user
# supplies the package and launch copies it into this session's isolated
# Xenia content root. Hash-pinned so a wrong file cannot be installed.
APF_TITLE_ID = 0x54540807
APF_TITLE_UPDATE_CONTENT_TYPE = 0x000B0000
APF_TITLE_UPDATE_SIZE = 839_680
APF_TITLE_UPDATE_SHA256 = (
    "5f71cdf4ec679f8e33fd95e02ff2b67981fbf918d4d03a2099576734c5cfb42b"
)
APF_TITLE_UPDATE_FILENAME = "TU_1A58207_0000008000000.0000000000082"


def title_update_content_dir(content_root: Path) -> Path:
    return (
        content_root
        / f"{APF_TITLE_ID:08X}"
        / f"{APF_TITLE_UPDATE_CONTENT_TYPE:08X}"
    )


def inspect_title_update(path: Path) -> bytes:
    """Read and pin-check the APF 1.1 LIVE title-update package."""

    path = path.expanduser()
    try:
        info = path.lstat()
    except OSError as exc:
        raise LaunchError(f"Title update 1.1 could not be opened: {exc}") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise LaunchError("Title update 1.1 must be a regular, non-symlink file")
    if info.st_size != APF_TITLE_UPDATE_SIZE:
        raise LaunchError(
            "That file is not the APF 2K8 title update 1.1 package this studio "
            f"recognizes (expected {APF_TITLE_UPDATE_SIZE} bytes)."
        )
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != APF_TITLE_UPDATE_SHA256:
        raise LaunchError(
            "That file is not the hash-pinned APF 2K8 title update 1.1 package. "
            "On Xbox/Xenia this update is required; it never shipped for PS3. "
            "Install the LIVE STFS package (File → Install Content in Xenia, or "
            "choose it here) whose SHA-256 matches the pinned 1.1 installer."
        )
    if payload[:4] != b"LIVE":
        raise LaunchError("Title update 1.1 must be a LIVE STFS package")
    title_id = struct.unpack_from(">I", payload, 0x360)[0]
    content_type = struct.unpack_from(">I", payload, 0x344)[0]
    if title_id != APF_TITLE_ID or content_type != APF_TITLE_UPDATE_CONTENT_TYPE:
        raise LaunchError(
            "That LIVE package is not All-Pro Football 2K8 title update 1.1 "
            f"(title {APF_TITLE_ID:08X}, content type "
            f"{APF_TITLE_UPDATE_CONTENT_TYPE:08X})."
        )
    return payload


def install_title_update(content_root: Path, source: Path) -> Path:
    """Copy the pinned 1.1 package into a Xenia content root."""

    payload = inspect_title_update(source)
    destination_dir = title_update_content_dir(content_root)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / APF_TITLE_UPDATE_FILENAME
    if destination.exists() and not destination.is_symlink():
        try:
            if hashlib.sha256(destination.read_bytes()).hexdigest() == APF_TITLE_UPDATE_SHA256:
                return destination
        except OSError:
            pass
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{APF_TITLE_UPDATE_FILENAME}.",
        suffix=".tmp",
        dir=destination_dir,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


@dataclass(frozen=True)
class LaunchReceipt:
    pid: int
    log_path: Path
    emulator: Path
    game: Path


class XeniaSettings:
    SCHEMA = "apf2k8_mod_studio_xenia_settings/v1"

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or (
            Path.home() / ".config" / "apf2k8-mod-studio" / "settings.json"
        )
        self.xenia_path: Path | None = None
        self.wine_path: Path | None = None
        self.title_update_path: Path | None = None
        self._load()

    @property
    def configured(self) -> bool:
        if self.xenia_path is None or not self.xenia_path.is_file():
            return False
        if self.xenia_path.suffix.casefold() == ".exe":
            # A ``.exe`` is the native direct mode on Windows, where Xenia
            # Canary only ships as one; demanding a Wine loader there would
            # make the emulator unconfigurable on its primary OS.  Wine stays
            # mandatory for a ``.exe`` on every other platform.
            if platform_compat.IS_WINDOWS:
                return True
            return (
                self.wine_path is not None
                and self.wine_path.is_file()
                and os.access(self.wine_path, os.X_OK)
            )
        return os.access(self.xenia_path, os.X_OK)

    def configure(self, xenia_path: Path, wine_path: Path | None = None) -> None:
        xenia = self._regular(xenia_path, "Xenia Canary")
        wine: Path | None = None
        if xenia.suffix.casefold() == ".exe" and not platform_compat.IS_WINDOWS:
            candidate = wine_path
            if candidate is None:
                found = shutil.which("wine")
                candidate = Path(found) if found else None
            if candidate is None:
                raise LaunchError(
                    "Xenia Canary is a Windows program. Install Wine or choose the Wine executable."
                )
            wine = self._regular(candidate, "Wine")
            if not os.access(wine, os.X_OK):
                raise LaunchError("The selected Wine file is not executable")
        elif not platform_compat.IS_WINDOWS and not os.access(xenia, os.X_OK):
            # Windows has no executable permission bit to check; CreateProcess
            # reports an unloadable image at launch time instead.
            raise LaunchError("The selected Xenia file is not executable")
        self.xenia_path = xenia
        self.wine_path = wine
        self._save()

    def configure_title_update(self, path: Path) -> None:
        payload_path = self._regular(path, "Title update 1.1")
        inspect_title_update(payload_path)
        self.title_update_path = payload_path
        self._save()

    def _load(self) -> None:
        if not self.config_path.is_file():
            return
        try:
            value = json.loads(self.config_path.read_text(encoding="utf-8"))
            if value.get("schema") != self.SCHEMA:
                return
            xenia = value.get("xenia_path")
            wine = value.get("wine_path")
            if not isinstance(xenia, str):
                return
            xenia_candidate = self._regular(Path(xenia), "Xenia Canary")
            if xenia_candidate.suffix.casefold() == ".exe":
                # On Windows a ``.exe`` loads natively and no Wine loader is
                # persisted; elsewhere the saved Wine path is mandatory.
                if not platform_compat.IS_WINDOWS:
                    if not isinstance(wine, str):
                        return
                    wine_candidate = self._regular(Path(wine), "Wine")
                    if not os.access(wine_candidate, os.X_OK):
                        return
                    self.wine_path = wine_candidate
            elif not os.access(xenia_candidate, os.X_OK):
                return
            self.xenia_path = xenia_candidate
            update = value.get("title_update_path")
            if isinstance(update, str) and update:
                try:
                    update_path = self._regular(Path(update), "Title update 1.1")
                    inspect_title_update(update_path)
                    self.title_update_path = update_path
                except LaunchError:
                    self.title_update_path = None
        except (OSError, ValueError, TypeError, LaunchError):
            self.xenia_path = None
            self.wine_path = None
            self.title_update_path = None

    def _save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.config_path.name}.",
            suffix=".tmp",
            dir=self.config_path.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(
                    (
                        json.dumps(
                            {
                                "schema": self.SCHEMA,
                                "xenia_path": str(self.xenia_path)
                                if self.xenia_path
                                else None,
                                "wine_path": str(self.wine_path)
                                if self.wine_path
                                else None,
                                "title_update_path": str(self.title_update_path)
                                if self.title_update_path
                                else None,
                            },
                            indent=2,
                        )
                        + "\n"
                    ).encode("utf-8")
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.config_path)
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _regular(path: Path, label: str) -> Path:
        path = path.expanduser()
        try:
            value = path.lstat()
        except OSError as exc:
            raise LaunchError(f"{label} could not be opened: {exc}") from exc
        if not stat.S_ISREG(value.st_mode) or stat.S_ISLNK(value.st_mode):
            raise LaunchError(f"{label} must be a regular, non-symlink file")
        return path.resolve(strict=True)


class XeniaLauncher:
    def __init__(
        self,
        settings: XeniaSettings | None = None,
        data_root: Path | None = None,
    ):
        self.settings = settings or XeniaSettings()
        self.data_root = data_root or (
            Path.home() / ".local" / "share" / "apf2k8-mod-studio" / "xenia"
        )

    def launch(self, game_root: Path, *, extra_env: Mapping[str, str] | None = None) -> LaunchReceipt:
        if not self.settings.configured or self.settings.xenia_path is None:
            raise LaunchError("Configure Xenia Canary first, then click Launch again")
        game_root = game_root.expanduser().resolve(strict=True)
        game = game_root / "default.xex"
        try:
            game_stat = game.lstat()
        except OSError:
            raise LaunchError("The selected modded game folder is missing default.xex")
        if not stat.S_ISREG(game_stat.st_mode) or stat.S_ISLNK(game_stat.st_mode):
            raise LaunchError("The modded game's default.xex must be a regular file")
        xenia = self.settings._regular(self.settings.xenia_path, "Xenia Canary")
        if not os.access(xenia, os.X_OK) and xenia.suffix.casefold() != ".exe":
            raise LaunchError("The configured Xenia file is no longer executable")
        run_root = self.data_root / hashlib_sha256_path(game_root)
        storage = run_root / "storage"
        content = run_root / "content"
        cache = run_root / "cache"
        logs = run_root / "logs"
        for path in (storage, content, cache, logs):
            path.mkdir(parents=True, exist_ok=True)
        if self.settings.title_update_path is not None:
            install_title_update(content, self.settings.title_update_path)
        log_path = logs / "xenia-latest.log"
        environment = os.environ.copy()
        if extra_env:
            environment.update(extra_env)
        if xenia.suffix.casefold() == ".exe" and not platform_compat.IS_WINDOWS:
            wine = self.settings.wine_path
            if wine is None:
                raise LaunchError("Wine is not configured")
            wine = self.settings._regular(wine, "Wine")
            if not os.access(wine, os.X_OK):
                raise LaunchError("The configured Wine file is no longer executable")
            wine_prefix = run_root / "wine-prefix"
            wine_prefix.mkdir(parents=True, exist_ok=True)
            environment["WINEPREFIX"] = str(wine_prefix)
            converted = {
                "storage": self._winepath(wine, storage, environment),
                "content": self._winepath(wine, content, environment),
                "cache": self._winepath(wine, cache, environment),
                "game": self._winepath(wine, game, environment),
            }
            command = [
                str(wine),
                str(xenia),
                "--gpu=vulkan",
                "--apu=sdl",
                "--hid=sdl",
                "--fullscreen=false",
                "--license_mask=1",
                "--readback_resolve=fast",
                "--apply_title_update=true",
                f"--storage_root={converted['storage']}",
                f"--content_root={converted['content']}",
                f"--cache_root={converted['cache']}",
                converted["game"],
            ]
        else:
            command = [
                str(xenia),
                "--gpu=vulkan",
                "--apu=sdl",
                "--hid=sdl",
                "--fullscreen=false",
                "--license_mask=1",
                "--readback_resolve=fast",
                "--apply_title_update=true",
                f"--storage_root={storage}",
                f"--content_root={content}",
                f"--cache_root={cache}",
                str(game),
            ]
        try:
            # A real non-following open on both platforms.  The previous
            # attempt here -- lstat, then os.open, then inspect the fstat --
            # did NOT close the hole on Windows: with the log absent at lstat
            # time an attacker could plant a symlink before the open, and the
            # fstat would then describe the innocent target it was redirected
            # to.  open_no_follow refuses the reparse point on the handle it
            # opened to check, and the truncation stays split off the open so
            # nothing is destroyed before that refusal can fire.
            #
            # Residual, stated rather than implied: on Windows the descriptor
            # that comes back is not proven to name the object that was checked
            # (see open_no_follow), so a same-user process replacing the name in
            # that gap has ITS file truncated instead.  This log lives under
            # this app's own per-user data root, where such a process could
            # already overwrite the log directly.
            log_descriptor = platform_compat.open_no_follow(
                log_path,
                os.O_WRONLY | os.O_CREAT,
                0o600,
            )
            try:
                os.ftruncate(log_descriptor, 0)
            except BaseException:
                # The descriptor is owned by this frame until fdopen below takes
                # it; anything raised between the open and that handover has to
                # close it here or it leaks for the process's lifetime.
                os.close(log_descriptor)
                raise
            with os.fdopen(log_descriptor, "wb") as log:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=environment,
                    start_new_session=True,
                    close_fds=True,
                )
        except OSError as exc:
            raise LaunchError(f"Xenia could not be started: {exc}") from exc
        return LaunchReceipt(process.pid, log_path, xenia, game)

    @staticmethod
    def _winepath(wine: Path, path: Path, environment: Mapping[str, str]) -> str:
        winepath = wine.with_name("winepath")
        command = [str(winepath if winepath.is_file() else "winepath"), "-w", str(path)]
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=dict(environment),
            check=False,
        )
        value = completed.stdout.strip()
        if completed.returncode != 0 or not value:
            raise LaunchError(
                "Wine could not translate the Xenia game path. Check the Wine installation."
            )
        return value


def hashlib_sha256_path(path: Path) -> str:
    import hashlib

    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:20]
