"""Exclusive source-copy staging; this module never patches source data."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import stat
from typing import Callable

from .errors import OutputRefusedError
from .model import SourceRecord


CopyProgress = Callable[[int, int], None]


@dataclass(frozen=True)
class CopyResult:
    source: str
    output: str
    bytes_copied: int
    verified_identical: bool
    replacements_applied: int = 0
    note: str = "Unmodified staging copy; no queued replacements were applied."


def _lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def validate_copy_destination(source: Path, output: Path) -> None:
    source_real = source.resolve(strict=True)
    requested = output.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if _lexists(requested):
        raise OutputRefusedError(f"Output already exists; overwrite refused: {requested}")
    output_real = requested.resolve(strict=False)
    if _lexists(output_real):
        raise OutputRefusedError(f"Output already exists; overwrite refused: {output_real}")
    if output_real == source_real:
        raise OutputRefusedError("Output must differ from the selected source")
    if source_real.is_dir() and source_real in output_real.parents:
        raise OutputRefusedError("A directory source cannot be copied inside itself")
    if not output_real.parent.is_dir():
        raise OutputRefusedError(f"Output parent directory does not exist: {output_real.parent}")


def create_source_copy(
    record: SourceRecord, output: Path, progress: CopyProgress | None = None
) -> CopyResult:
    source = Path(record.selected_path).resolve(strict=True)
    requested = output.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    validate_copy_destination(source, requested)
    destination = requested.resolve(strict=False)
    if source.is_dir():
        return _copy_directory(source, destination)
    return _copy_file(source, destination, progress)


def _copy_file(source: Path, output: Path, progress: CopyProgress | None) -> CopyResult:
    total = source.stat().st_size
    copied = 0
    source_digest = hashlib.sha256()
    output_digest = hashlib.sha256()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(output, flags, stat.S_IMODE(source.stat().st_mode))
        with source.open("rb") as reader, os.fdopen(descriptor, "wb") as writer:
            while True:
                block = reader.read(4 * 1024 * 1024)
                if not block:
                    break
                source_digest.update(block)
                writer.write(block)
                output_digest.update(block)
                copied += len(block)
                if progress:
                    progress(copied, total)
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        if _lexists(output):
            output.unlink()
        raise
    verified = copied == total and source_digest.digest() == output_digest.digest()
    if not verified:
        output.unlink(missing_ok=True)
        raise OutputRefusedError("Staging copy verification failed; partial output removed")
    return CopyResult(str(source), str(output), copied, True)


def _copy_directory(source: Path, output: Path) -> CopyResult:
    try:
        shutil.copytree(source, output, symlinks=True, dirs_exist_ok=False)
    except BaseException:
        if output.exists() and output.is_dir():
            shutil.rmtree(output)
        raise
    source_manifest, source_bytes = _directory_manifest(source)
    output_manifest, output_bytes = _directory_manifest(output)
    if source_manifest != output_manifest or source_bytes != output_bytes:
        shutil.rmtree(output)
        raise OutputRefusedError("Directory staging-copy verification failed; output removed")
    return CopyResult(
        str(source),
        str(output),
        output_bytes,
        True,
        note="Unmodified directory staging copy; no queued replacements were applied.",
    )


def _directory_manifest(root: Path) -> tuple[tuple[tuple[str, str, str], ...], int]:
    rows: list[tuple[str, str, str]] = []
    byte_count = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            rows.append(("symlink", relative, os.readlink(path)))
        elif path.is_dir():
            rows.append(("directory", relative, ""))
        elif path.is_file():
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as source:
                while True:
                    block = source.read(4 * 1024 * 1024)
                    if not block:
                        break
                    digest.update(block)
                    size += len(block)
            byte_count += size
            rows.append(("file", relative, f"{size}:{digest.hexdigest()}"))
        else:
            rows.append(("special", relative, ""))
    return tuple(rows), byte_count
