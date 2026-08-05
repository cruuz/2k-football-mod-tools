"""Stage one product's release tree from its retail-free allowlist.

This is the same copy step ``.github/workflows/ci.yml`` performs before it runs
the release gates, factored out so a release can be built the same way by hand.
Only allowlisted regular files are copied.  The complete manifest is preflighted
before the destination is created, and an existing destination is never merged
or overwritten.

Usage: stage_release.py <allowlist> <destination> [repo-root]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
from typing import Sequence


class StageError(ValueError):
    """The requested release stage is incomplete or unsafe."""


def _lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _reject_symlinked_destination_parent(dest: Path) -> None:
    current = dest.absolute().parent
    while True:
        if _lexists(current) and current.is_symlink():
            raise StageError(f"destination has a symlinked parent: {current}")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _regular_file_without_symlink(path: Path, root: Path, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise StageError(f"{label} is missing: {path}") from exc
    if stat.S_ISLNK(mode):
        raise StageError(f"{label} is a symlink: {path}")
    if not stat.S_ISREG(mode):
        raise StageError(f"{label} is not a regular file: {path}")

    current = path.parent
    while current != root:
        if current.is_symlink():
            raise StageError(f"{label} has a symlinked parent: {current}")
        parent = current.parent
        if parent == current:
            raise StageError(f"{label} escapes the repository root: {path}")
        current = parent


def _manifest_entries(allowlist: Path) -> tuple[str, ...]:
    try:
        mode = allowlist.lstat().st_mode
    except FileNotFoundError as exc:
        raise StageError(f"allowlist is missing: {allowlist}") from exc
    if stat.S_ISLNK(mode):
        raise StageError(f"allowlist is a symlink: {allowlist}")
    if not stat.S_ISREG(mode):
        raise StageError(f"allowlist is not a regular file: {allowlist}")

    entries: list[str] = []
    seen: set[str] = set()
    for number, raw in enumerate(
        allowlist.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        posix = PurePosixPath(line)
        if (
            posix.is_absolute()
            or ".." in posix.parts
            or "\\" in line
            or str(posix) != line
        ):
            raise StageError(
                f"allowlist line {number} is not a canonical relative path: {line}"
            )
        if line in seen:
            raise StageError(f"allowlist line {number} is duplicated: {line}")
        seen.add(line)
        entries.append(line)
    if not entries:
        raise StageError("allowlist has no file entries")
    return tuple(entries)


def _preflight(
    allowlist: Path, dest: Path, root: Path
) -> tuple[Path, tuple[tuple[str, Path], ...]]:
    if _lexists(dest):
        raise StageError(f"destination already exists: {dest}")
    _reject_symlinked_destination_parent(dest)
    try:
        root = root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise StageError(f"repository root is missing: {root}") from exc
    if not root.is_dir():
        raise StageError(f"repository root is not a directory: {root}")

    entries = _manifest_entries(allowlist)
    declared: list[tuple[str, Path]] = []
    failures: list[str] = []
    for relative in entries:
        source = root.joinpath(*PurePosixPath(relative).parts)
        try:
            _regular_file_without_symlink(source, root, "declared input")
        except StageError as exc:
            failures.append(str(exc))
        else:
            declared.append((relative, source))
    if failures:
        raise StageError("; ".join(failures))
    return root, tuple(declared)


def stage(allowlist: Path, dest: Path, root: Path) -> int:
    _root, declared = _preflight(allowlist, dest, root)
    dest.mkdir(parents=True, exist_ok=False)
    for relative, source in declared:
        output = dest.joinpath(*PurePosixPath(relative).parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output, follow_symlinks=False)
        # Be explicit about executable entry points even on unusual filesystems.
        source_mode = source.stat().st_mode
        if source_mode & 0o111:
            os.chmod(output, output.stat().st_mode | 0o111)
    print(f"staged {len(declared)} files; 0 declared inputs absent")
    return len(declared)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("allowlist", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "repo_root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        stage(args.allowlist, args.destination, args.repo_root)
    except (StageError, OSError, UnicodeError) as exc:
        print(f"RELEASE_STAGE_REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
