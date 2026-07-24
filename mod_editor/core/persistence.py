"""Strict JSON project persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from .errors import ValidationError
from .model import ModProject


def save_project(project: ModProject, destination: Path) -> Path:
    requested = destination.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    path = Path(os.path.abspath(os.fspath(requested)))
    if os.path.lexists(path) and (not path.is_file() or path.is_symlink()):
        raise ValidationError("Project destination must be a regular non-symlink file")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    payload = json.dumps(project.to_document(), indent=2, sort_keys=True) + "\n"
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    project.project_path = str(path)
    project.dirty = False
    return path


def load_project(source: Path) -> ModProject:
    path = source.expanduser().resolve(strict=True)
    if not path.is_file() or path.is_symlink():
        raise ValidationError("Project source must be a regular non-symlink file")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Cannot read project: {exc}") from exc
    project = ModProject.from_document(document)
    project.project_path = str(path)
    project.dirty = False
    return project
