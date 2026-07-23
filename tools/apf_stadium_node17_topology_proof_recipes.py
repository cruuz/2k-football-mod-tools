#!/usr/bin/env python3
"""Derive local-only APF node17 topology proof recipes from user data.

The no-op recipe contains the source retail index sequence and must remain in
a temporary directory.  The changed recipe uses the public nonretail
permutation.  Both paths must be absent and are created exclusively.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import os
from pathlib import Path
import stat
import struct
import sys

import apf_inner
import apf_stadium_node17_topology_patch as writer


class ProofRecipeError(ValueError):
    pass


def _write_new(path: Path, data: bytes) -> None:
    if os.path.lexists(path):
        raise ProofRecipeError(f"refusing existing proof recipe: {path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, 0o600)
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    try:
        written = 0
        while written < len(data):
            count = os.write(descriptor, data[written:])
            if count <= 0:
                raise ProofRecipeError("short proof recipe write")
            written += count
        os.fsync(descriptor)
        metadata = os.lstat(path)
        if not stat.S_ISREG(metadata.st_mode) or (metadata.st_dev, metadata.st_ino) != identity:
            raise ProofRecipeError("proof recipe pathname changed during write")
    except Exception:
        try:
            metadata = os.lstat(path)
            if (metadata.st_dev, metadata.st_ino) == identity:
                os.unlink(path)
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)


def derive(game_dir: Path) -> tuple[dict[str, object], dict[str, object]]:
    game_dir = game_dir.expanduser().resolve(strict=True)
    writer.container._source_file_identities(game_dir)
    archive, entry = writer.container._validate_archive(game_dir)
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        block0 = apf_inner.decode_block(reader, record, 0, 1 << 30)
    system = block0[: writer.container.SYSTEM_LENGTH]
    writer.container._validate_scene(system)
    writer._draw_semantics(system)
    source = list(struct.unpack_from(">4H", system, writer.INDEX_OFFSET))
    if sorted(source) != [0, 1, 2, 3]:
        raise ProofRecipeError("source index sequence is outside the pinned permutation profile")
    noop = copy.deepcopy(writer.RECIPE_CONSTANTS)
    noop["indices"] = source
    changed = copy.deepcopy(writer.RECIPE_CONSTANTS)
    changed["indices"] = [0, 2, 1, 3]
    return noop, changed


def write_recipes(game_dir: Path, noop_path: Path, changed_path: Path) -> tuple[str, str]:
    noop_path = noop_path.expanduser()
    changed_path = changed_path.expanduser()
    if noop_path.resolve(strict=False) == changed_path.resolve(strict=False):
        raise ProofRecipeError("proof recipe output paths collide")
    for path in (noop_path, changed_path):
        parent = path.parent.resolve(strict=True)
        if parent != path.parent.absolute():
            raise ProofRecipeError("proof recipe parent contains a symlink")
    noop, changed = derive(game_dir)
    noop_bytes = writer.canonical_json_bytes(noop)
    changed_bytes = writer.canonical_json_bytes(changed)
    _write_new(noop_path, noop_bytes)
    try:
        _write_new(changed_path, changed_bytes)
    except Exception:
        try:
            noop_path.unlink()
        except OSError:
            pass
        raise
    return hashlib.sha256(noop_bytes).hexdigest(), hashlib.sha256(changed_bytes).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--noop-output", type=Path, required=True)
    parser.add_argument("--changed-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        noop_hash, changed_hash = write_recipes(args.game_dir, args.noop_output, args.changed_output)
        print(
            "APF_SCNE_NODE17_TOPOLOGY_PROOF_RECIPES_PASS "
            f"noop_sha256={noop_hash} changed_sha256={changed_hash} committed=false"
        )
        return 0
    except (
        ProofRecipeError,
        writer.PatchError,
        writer.container.PatchError,
        apf_inner.FormatError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
