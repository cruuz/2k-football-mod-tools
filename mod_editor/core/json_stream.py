"""Small constant-memory helpers for the product's generated JSON indexes.

The research scanners intentionally emit plain JSON so their output remains
easy to audit.  Some of those files are large enough that a desktop browser
must not call :func:`json.load` on them.  This module streams one named,
top-level array and materializes only its current item.

It is deliberately narrow: the input must be a regular, non-symlink JSON file
and the requested member must use the canonical ``"name": [`` spelling
emitted by the project's scanners (arbitrary whitespace is accepted).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
from typing import Iterator

from . import platform_compat
from .errors import ValidationError


READ_SIZE = 1024 * 1024
MAX_MARKER_CARRY = 4096


def require_regular_file(path: Path, label: str) -> os.stat_result:
    """Return ``lstat`` data for a regular, non-symlink file."""

    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} is missing: {path}") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValidationError(f"{label} must be a regular file: {path}")
    return info


def read_bounded_regular_file(
    path: Path,
    label: str,
    *,
    maximum: int,
    error_type: type[ValidationError] = ValidationError,
) -> tuple[Path, bytes]:
    """Return stable bytes from a bounded, singly-linked regular-file descriptor."""

    if maximum <= 0:
        raise error_type(f"{label} has an invalid size limit")
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    try:
        supplied = requested.lstat()
    except FileNotFoundError as exc:
        raise error_type(f"{label} is missing: {requested}") from exc
    if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
        raise error_type(
            f"{label} must be a regular file, not a folder or link: {requested}"
        )
    if supplied.st_nlink != 1:
        raise error_type(f"{label} must not be a hard-linked file: {requested}")
    if not 0 < supplied.st_size <= maximum:
        raise error_type(f"{label} is empty or too large: {requested}")
    try:
        resolved = requested.resolve(strict=True)
        descriptor = os.open(
            requested,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        )
    except OSError as exc:
        raise error_type(f"{label} could not be opened safely: {requested}") from exc
    try:
        opened = os.fstat(descriptor)
        # Three identity comparisons happen below and they are not all the same
        # shape.  ``supplied`` and ``current`` are PATH stats of the name;
        # ``opened`` and ``after`` are FD stats of the descriptor.  Windows
        # reaches st_ctime through a different Win32 information class for each
        # family, so the two disagree for a file nothing touched: the
        # path-against-fd comparisons drop that field there (via
        # change_time_identity) and the fd-against-fd comparison keeps it on
        # every platform.  Hence two spellings of the ``opened`` fingerprint.
        supplied_identity = (
            supplied.st_dev,
            supplied.st_ino,
            supplied.st_size,
            supplied.st_mtime_ns,
            *platform_compat.change_time_identity(supplied),
            supplied.st_nlink,
        )
        opened_cross_identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            *platform_compat.change_time_identity(opened),
            opened.st_nlink,
        )
        opened_identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
            opened.st_nlink,
        )
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened_cross_identity != supplied_identity
            or not 0 < opened.st_size <= maximum
        ):
            raise error_type(f"{label} changed before it could be opened: {requested}")
        try:
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                descriptor = -1
                payload = stream.read(maximum + 1)
                after = os.fstat(stream.fileno())
        except OSError as exc:
            raise error_type(f"{label} could not be read safely: {requested}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    try:
        current = requested.lstat()
    except FileNotFoundError as exc:
        raise error_type(f"{label} changed while it was read: {requested}") from exc
    # fd against fd: the change time stays in, on every platform.
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_nlink,
    )
    # path against fd: the change time is dropped where the two cannot agree.
    current_identity = (
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
        *platform_compat.change_time_identity(current),
        current.st_nlink,
    )
    if len(payload) > maximum:
        raise error_type(f"{label} is empty or too large: {requested}")
    if (
        len(payload) != opened.st_size
        or after_identity != opened_identity
        or current_identity != opened_cross_identity
        or not stat.S_ISREG(current.st_mode)
        or stat.S_ISLNK(current.st_mode)
    ):
        raise error_type(f"{label} changed while it was read: {requested}")
    return resolved, payload


def file_contains_bytes(path: Path, needle: bytes, *, label: str) -> bool:
    """Search a file with bounded memory, including cross-block matches."""

    require_regular_file(path, label)
    if not needle:
        return True
    carry = b""
    with path.open("rb") as stream:
        while True:
            block = stream.read(READ_SIZE)
            if not block:
                return False
            combined = carry + block
            if needle in combined:
                return True
            carry = combined[-max(0, len(needle) - 1):]


def iter_top_level_array(path: Path, key: str, *, label: str) -> Iterator[object]:
    """Yield items from one canonical top-level JSON array.

    At most the current JSON value plus roughly one input block is retained.
    A malformed item, a missing member, or trailing junk in the selected array
    fails closed with a user-facing :class:`ValidationError`.
    """

    require_regular_file(path, label)
    if not key or any(ord(character) < 0x20 for character in key):
        raise ValidationError("JSON array key is invalid")
    marker = re.compile(rf'"{re.escape(key)}"\s*:\s*\[')
    decoder = json.JSONDecoder()
    buffer = ""
    position = 0
    eof = False
    found = False

    try:
        stream = path.open("r", encoding="utf-8", newline="")
    except OSError as exc:
        raise ValidationError(f"Could not open {label}: {exc}") from exc

    with stream:
        while not found:
            block = stream.read(READ_SIZE)
            if not block:
                raise ValidationError(
                    f"{label} does not contain the expected {key!r} array"
                )
            buffer += block
            match = marker.search(buffer)
            if match is not None:
                position = match.end()
                found = True
                break
            if len(buffer) > MAX_MARKER_CARRY:
                buffer = buffer[-MAX_MARKER_CARRY:]

        first_item = True
        while True:
            while True:
                while position < len(buffer) and buffer[position].isspace():
                    position += 1
                if position < len(buffer):
                    break
                block = stream.read(READ_SIZE)
                if not block:
                    eof = True
                    break
                buffer = block
                position = 0
            if eof:
                raise ValidationError(f"{label} ended inside its {key!r} array")

            if first_item:
                if buffer[position] == "]":
                    return
            else:
                if buffer[position] == "]":
                    return
                if buffer[position] != ",":
                    raise ValidationError(
                        f"{label} is missing a separator in its {key!r} array"
                    )
                position += 1
                while True:
                    while position < len(buffer) and buffer[position].isspace():
                        position += 1
                    if position < len(buffer):
                        break
                    block = stream.read(READ_SIZE)
                    if not block:
                        raise ValidationError(
                            f"{label} ended inside its {key!r} array"
                        )
                    buffer = block
                    position = 0
                if buffer[position] == "]":
                    raise ValidationError(
                        f"{label} has a trailing comma in its {key!r} array"
                    )

            while True:
                try:
                    value, end = decoder.raw_decode(buffer, position)
                except json.JSONDecodeError as exc:
                    block = stream.read(READ_SIZE)
                    if not block:
                        raise ValidationError(
                            f"{label} has malformed JSON in its {key!r} array: {exc}"
                        ) from exc
                    # Discard only text known to precede the current value.
                    buffer = buffer[position:] + block
                    position = 0
                    continue
                position = end
                yield value
                first_item = False
                if position > READ_SIZE:
                    buffer = buffer[position:]
                    position = 0
                break


__all__ = [
    "file_contains_bytes",
    "iter_top_level_array",
    "read_bounded_regular_file",
    "require_regular_file",
]
