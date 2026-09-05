"""Strict JSON project persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import platform_compat
from .errors import ValidationError
from .model import ModProject


def save_project(project: ModProject, destination: Path) -> Path:
    requested = destination.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    path = Path(os.path.abspath(os.fspath(requested)))
    io_path = Path(platform_compat.long_path(path))
    if os.path.lexists(io_path) and (not io_path.is_file() or io_path.is_symlink()):
        raise ValidationError("Project destination must be a regular non-symlink file")
    io_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = platform_compat.temporary_sibling(path)
    payload = json.dumps(project.to_document(), indent=2, sort_keys=True) + "\n"
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(
            platform_compat.long_path(temporary), flags | getattr(os, "O_BINARY", 0), 0o600
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(platform_compat.long_path(temporary), platform_compat.long_path(path))
    finally:
        io_temporary = Path(platform_compat.long_path(temporary))
        if io_temporary.exists():
            io_temporary.unlink()
    project.project_path = str(path)
    project.dirty = False
    return path


def load_project(source: Path) -> ModProject:
    extended = Path(platform_compat.long_path(source.expanduser()))
    try:
        path = extended.resolve(strict=True)
    except OSError:
        # Windows' final-path lookup can fail on extended (\\?\) paths past 260 characters (seen as
        # WinError 234 under Wine); the file is still addressable, so canonicalise without realpath.
        path = Path(os.path.abspath(extended))
        if not path.exists():
            raise
    io_path = Path(platform_compat.long_path(path))
    if not io_path.is_file() or io_path.is_symlink():
        raise ValidationError("Project source must be a regular non-symlink file")
    try:
        document = json.loads(io_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Cannot read project: {exc}") from exc
    project = ModProject.from_document(document)
    project.project_path = str(path)
    project.dirty = False
    return project
