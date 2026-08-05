"""Persistent Xenia configuration and safe detached launch integration."""

from __future__ import annotations

from dataclasses import dataclass
import errno
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from typing import Mapping

from mod_editor.core import platform_compat


class LaunchError(ValueError):
    """A Xenia setup or launch problem a non-expert can correct."""


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
        except (OSError, ValueError, TypeError, LaunchError):
            self.xenia_path = None
            self.wine_path = None

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
