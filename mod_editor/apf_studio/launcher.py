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
            return (
                self.wine_path is not None
                and self.wine_path.is_file()
                and os.access(self.wine_path, os.X_OK)
            )
        return os.access(self.xenia_path, os.X_OK)

    def configure(self, xenia_path: Path, wine_path: Path | None = None) -> None:
        xenia = self._regular(xenia_path, "Xenia Canary")
        wine: Path | None = None
        if xenia.suffix.casefold() == ".exe":
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
        elif not os.access(xenia, os.X_OK):
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
        if xenia.suffix.casefold() == ".exe":
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
            # O_NOFOLLOW carries the whole no-follow guarantee here, and it is 0
            # on Windows -- so the open would follow a planted symlink and
            # O_TRUNC would destroy whatever it pointed at.  The truncation is
            # therefore split off the open: refuse a link by name first, open
            # WITHOUT O_TRUNC, prove the opened object is the same non-reparse
            # file that was named, and only then empty it through the
            # descriptor.  Nothing is destroyed before the identity is proven,
            # and on POSIX the O_NOFOLLOW refusal still fires exactly as before.
            try:
                named = os.lstat(log_path)
            except FileNotFoundError:
                named = None
            if named is not None and (
                stat.S_ISLNK(named.st_mode)
                or platform_compat.is_reparse_point(log_path)
            ):
                raise OSError(
                    errno.ELOOP,
                    "the Xenia log path is a symlink or reparse point",
                    os.fspath(log_path),
                )
            log_descriptor = os.open(
                log_path,
                os.O_WRONLY
                | os.O_CREAT
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
                0o600,
            )
            opened = os.fstat(log_descriptor)
            attributes = getattr(opened, "st_file_attributes", 0)
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            replaced = (
                named is not None
                and opened.st_ino
                and (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
            )
            if (attributes and reparse_flag and attributes & reparse_flag) or replaced:
                os.close(log_descriptor)
                raise OSError(
                    errno.ELOOP,
                    "the Xenia log path was replaced while it was being opened",
                    os.fspath(log_path),
                )
            os.ftruncate(log_descriptor, 0)
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
