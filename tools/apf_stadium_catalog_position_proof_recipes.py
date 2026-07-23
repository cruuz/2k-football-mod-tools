#!/usr/bin/env python3
"""Derive a local-only exact no-op recipe for the APF catalog node3 proof.

Retail coordinates are written only to the caller's requested absent path.
No recipe values are printed and no checked artifact contains those values.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat
import struct
import sys

import apf_inner
import apf_outer
import apf_stadium_catalog_position_patch as writer


TARGET_ID = "outer14.inner8.node3"


class RecipeError(ValueError):
    pass


def derive(game_dir: Path) -> dict[str, object]:
    writer.container._source_file_identities(game_dir)
    _, targets = writer.load_catalog()
    target = targets[TARGET_ID]
    archive = apf_outer.parse_archive(game_dir / "0A")
    entry = archive.entries[writer.OUTER_INDEX]
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        block0 = apf_inner.decode_block(reader, record, 0, 1 << 30)
    system = block0[: writer.SYSTEM_LENGTH]
    writer._validate_source_target(system, target)
    count, start, stride, lane_offset = writer._target_layout(target)
    positions = [
        list(struct.unpack_from(">3f", system, start + vertex * stride + lane_offset))
        for vertex in range(count)
    ]
    recipe = dict(writer.RECIPE_CONSTANTS)
    recipe["target_id"] = TARGET_ID
    recipe["positions"] = positions
    return recipe


def write_absent(path: Path, data: bytes) -> None:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    requested = Path(os.path.normpath(requested))
    parent = requested.parent
    metadata = os.lstat(parent)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode) or parent.resolve(strict=True) != parent.absolute():
        raise RecipeError("output parent must be an existing real non-symlink directory")
    if os.path.lexists(requested):
        raise RecipeError("refusing existing recipe output")
    descriptor = os.open(requested, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    try:
        written = 0
        while written < len(data):
            count = os.write(descriptor, data[written:])
            if count <= 0:
                raise RecipeError("short recipe write")
            written += count
        os.fsync(descriptor)
        final = os.lstat(requested)
        if not stat.S_ISREG(final.st_mode) or (final.st_dev, final.st_ino) != identity:
            raise RecipeError("recipe pathname changed during publication")
    except Exception:
        try:
            final = os.lstat(requested)
            if stat.S_ISREG(final.st_mode) and (final.st_dev, final.st_ino) == identity:
                os.unlink(requested)
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--noop-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = writer.canonical_json_bytes(derive(args.game_dir.resolve(strict=True)))
        write_absent(args.noop_output, data)
        print(
            "APF_SCNE_CATALOG_PROOF_RECIPE_LOCAL_ONLY_PASS "
            f"target={TARGET_ID} vertices=24 sha256={hashlib.sha256(data).hexdigest()} committed=false"
        )
        return 0
    except (RecipeError, writer.PatchError, writer.container.PatchError, apf_outer.FormatError, apf_inner.FormatError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
