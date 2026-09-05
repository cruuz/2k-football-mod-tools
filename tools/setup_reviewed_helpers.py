#!/usr/bin/env python3
"""Verify and normalize the one reviewed Linux H7A helper in a source worktree.

Run explicitly after checkout: python3 tools/setup_reviewed_helpers.py
Only the pinned tools/apf_h7a_optimal regular, single-link file is eligible.
Wrong contents, symlinks, foreign ownership and swapped files are refused.
The runtime security predicate is neither changed nor bypassed. No execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys


SIZE = 14472
SHA256 = '9061866e31f1a2930eceaa4fb8652ef1b7aa9b04cbce0174cc0eae125f8e49ab'


class SetupError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise SetupError(message)


def normalize(root: Path) -> dict[str, object]:
    """Hash first, chmod the same descriptor, then reverify identity and bytes."""
    _require(os.name == 'posix' and hasattr(os, 'fchmod'), 'Unix permission setup requires POSIX')
    path = Path(os.path.abspath(root)) / 'tools' / 'apf_h7a_optimal'
    for parent in reversed(path.parents):
        info = parent.lstat()
        _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                 f'non-directory or symlinked parent: {parent}')
    before = path.lstat()
    _require(stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode), 'helper must be a non-symlink regular file')
    _require(before.st_nlink == 1, 'helper must have exactly one link')
    _require(before.st_uid == os.geteuid(), 'helper must belong to the current user')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    # Pin each directory while walking. lstat-only ancestor checks have a
    # symlink-swap window before opening the leaf.
    directory_flags = flags | getattr(os, 'O_DIRECTORY', 0)
    parent_fd = os.open(path.anchor, directory_flags)
    try:
        for part in path.parts[1:-1]:
            child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child_fd
        fd = os.open(path.name, flags, dir_fd=parent_fd)
    except BaseException:
        os.close(parent_fd)
        raise
    try:
        opened = os.fstat(fd)
        _require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino), 'helper changed while opening')
        _require(opened.st_size == SIZE and opened.st_nlink == 1, 'helper size/link count is not reviewed')
        data = bytearray()
        while len(data) <= SIZE:
            block = os.read(fd, SIZE + 1 - len(data))
            if not block:
                break
            data.extend(block)
        _require(len(data) == SIZE and hashlib.sha256(data).hexdigest() == SHA256, 'reviewed helper SHA-256 mismatch; no permissions changed')
        os.fchmod(fd, 0o755)
        final = os.fstat(fd)
        named = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        current_path = path.lstat()
        _require((final.st_dev, final.st_ino) == (named.st_dev, named.st_ino)
                 == (current_path.st_dev, current_path.st_ino)
                 and final.st_nlink == 1 and stat.S_ISREG(named.st_mode), 'helper identity changed during setup')
        _require(stat.S_IMODE(final.st_mode) == 0o755, 'filesystem did not enforce mode 0755')
        os.lseek(fd, 0, os.SEEK_SET)
        verified = bytearray()
        while len(verified) <= SIZE:
            block = os.read(fd, SIZE + 1 - len(verified))
            if not block:
                break
            verified.extend(block)
        _require(bytes(verified) == bytes(data), 'helper contents changed during setup; runtime verification remains required')
    finally:
        os.close(fd)
        os.close(parent_fd)
    return {'path': str(path), 'sha256': SHA256, 'before_mode': f'{stat.S_IMODE(before.st_mode):04o}',
            'after_mode': '0755', 'changed': stat.S_IMODE(before.st_mode) != 0o755}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        print(json.dumps(normalize(args.root), indent=2))
    except (SetupError, OSError) as exc:
        print(f'REVIEWED_HELPER_SETUP_REFUSED: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
