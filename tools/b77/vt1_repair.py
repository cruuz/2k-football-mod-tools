#!/usr/bin/env python3
"""Install automatic coach AI and Modern 2 on an exact co2 disc copy.

The source is read only. Only known base/final full-image hashes are accepted;
every write is prepared from the Studio compiler before the copy is opened.
Receipts include exact spans, replay, full byte scope and Studio equality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from tools.b77 import vp2_repair as prior
from mod_editor.core import nfl2k5_coach_ai as ai, nfl2k5_throw_tuning as tt
from mod_editor.core import platform_compat as io
from mod_editor.core.nfl2k5_cave_manifest import changed_runs
from nfl2k5_playbook_position_recode import OuterImage

BASE_SHA256 = "d735215760ff08bceeff2a3860baccf0a84885422a4205e966154e948812103e"
DISC_SIZE = 6004408320
MIN_FREE = 25_000_000_000


def binary(path, *, writable=False, new=False):
    flags = os.O_RDWR if writable else os.O_RDONLY
    if new:
        flags |= os.O_CREAT | os.O_EXCL
    return os.fdopen(os.open(path, flags | getattr(os, "O_BINARY", 0) |
                            getattr(os, "O_NOFOLLOW", 0), 0o644), "r+b" if writable else "rb")


def emit(path, data):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def guard(reserve=0):
    ai.require(shutil.disk_usage("/").free >= MIN_FREE + reserve,
               "Insufficient free disk space for the 25 GB reserve")


def plan(base):
    ai.require(base.is_file() and not base.is_symlink(), "Expected a regular base image")
    ai.require(base.stat().st_size == DISC_SIZE, "Unexpected base image size")
    ai.require(prior.hashes(base)[0] == BASE_SHA256, "Unknown base disc SHA-256")
    with binary(base) as stream:
        off, length = tt.image_xbe_extent(stream.fileno(), DISC_SIZE)
        source = io.pread(stream.fileno(), length, off)
    result, xbe = prior.repair_xbe(source)
    # Compare with Studio's component writers on this already configured
    # release. A fresh full BuildPlan would also need every existing option;
    # unrelated options must not be inferred or reset by this additive repair.
    modern, _ = prior.money.upgrade_to_modern2(source)
    studio, _ = ai.apply(modern)
    ai.require(studio == result, "Native executable differs from Studio component writers")
    edits = [(off + a, source[a:b], result[a:b], "default.xbe")
             for a, b in changed_runs(source, result)]
    prepared = ai.plan_profiles(base, progress=lambda line: print(line, flush=True))
    with OuterImage(base) as archive:
        for index, before, after, receipt in prepared:
            pos = 32 + ai.PROFILE_OFFSET
            virtual = archive.entries[index].virtual_offset + pos
            for pack, offset, count in archive._segments(virtual, ai.PROFILE_SIZE):
                edits.append((pack.image_offset + offset, before[pos:pos + count],
                              after[pos:pos + count], receipt["team"]))
                pos += count
    edits.sort()
    ai.require(all(a[0] + len(a[1]) <= b[0] for a, b in zip(edits, edits[1:])), "Overlapping spans")
    return edits, result, xbe, prepared


def patched_digest(path, edits):
    digest, at = hashlib.sha256(), 0
    with binary(path) as stream:
        for offset, before, after, _ in edits:
            ai.require(len(before) == len(after) and offset >= at, "Invalid fixed span")
            left = offset - at
            while left:
                chunk = stream.read(min(left, 8 << 20))
                ai.require(bool(chunk), "Short source image")
                digest.update(chunk)
                left -= len(chunk)
            ai.require(stream.read(len(before)) == before, "Source span changed")
            digest.update(after)
            at = offset + len(before)
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compare(base, image, edits):
    """Compare every byte, without treating unmodified XBE bytes as owned."""
    changed = outside = 0
    with binary(base) as original, binary(image) as final:
        at = 0
        while a := original.read(1 << 20):
            b = final.read(len(a))
            ai.require(len(a) == len(b), "Short output image")
            if a != b:
                expected = bytearray(a)
                for offset, before, after, _ in edits:
                    lo, hi = max(at, offset), min(at + len(a), offset + len(before))
                    if lo < hi:
                        expected[lo - at:hi - at] = after[lo - offset:hi - offset]
                changed += sum(x != y for x, y in zip(a, b))
                outside += sum(x != y for x, y in zip(expected, b))
            at += len(a)
        ai.require(not final.read(1), "Output image grew")
    ai.require(outside == 0, "Unexpected bytes outside the exact planned changes")
    return dict(bytes_compared=at, changed_bytes=changed, outside_spans_changed_bytes=outside)


def repair(base, image, evidence):
    ai.require(base.resolve() != image.resolve(), "Base and private copy must differ")
    ai.require(not image.is_symlink(), "Private image must not be a symlink")
    ai.require(not image.exists() or not base.samefile(image), "Private copy is a hard link to the base")
    guard()
    edits, candidate, xbe, prepared = plan(base)
    expected = patched_digest(base, edits)
    evidence.mkdir(parents=True, exist_ok=True)
    if not image.exists():
        guard(DISC_SIZE)
        with binary(base) as source, binary(image, writable=True, new=True) as target:
            while chunk := source.read(8 << 20):
                guard()
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
    ai.require(image.stat().st_size == DISC_SIZE, "Unexpected private image size")
    before_hash = prior.hashes(image)[0]
    ai.require(before_hash in (BASE_SHA256, expected), "Unknown private disc SHA-256")
    written = 0
    with binary(image, writable=True) as stream:
        for offset, before, after, _ in edits:
            actual = io.pread(stream.fileno(), len(before), offset)
            ai.require(actual == (before if before_hash == BASE_SHA256 else after), "Span changed since preflight")
        for offset, before, after, _ in edits:
            if before_hash != expected and before != after:
                guard()
                ai.require(io.pwrite(stream.fileno(), after, offset) == len(after), "Short write")
                written += len(after)
        stream.flush()
        os.fsync(stream.fileno())
        for offset, _, after, _ in edits:
            ai.require(io.pread(stream.fileno(), len(after), offset) == after, "Readback mismatch")
    ai.require(prior.hashes(image)[0] == expected, "Output disc digest mismatch")
    scope = compare(base, image, edits)
    equality = []
    with OuterImage(image) as archive:
        for index, _, after, receipt in prepared:
            equality.append(dict(team=receipt["team"], equal=archive.read_entry(index) == after,
                                 sha256=prior.sha(after), portrait=receipt["roster_portrait"]))
    ai.require(all(row["equal"] for row in equality), "Studio resource equality failed")
    result = dict(schema="b772/vt1-disc-repair/v1", before_sha256=before_hash,
                  after_sha256=expected, size=DISC_SIZE, bytes_written=written,
                  changed_bytes=scope["changed_bytes"], xbe=xbe, readback_verified=True,
                  spans=[dict(offset=o, size=len(a), owner=n, before_sha256=prior.sha(a),
                              after_sha256=prior.sha(b)) for o, a, b, n in edits])
    if written or not (evidence / "disc-write.json").exists():
        emit(evidence / "disc-write.json", result)
    else:
        emit(evidence / "disc-replay.json", result)
    emit(evidence / "disc-scope.json", scope)
    emit(evidence / "disc-studio-equality.json", dict(xbe_equal=True, resources=equality, all_equal=True))
    emit(evidence / "xbe-install.json", xbe)
    (evidence / "candidate.xbe").write_bytes(candidate)
    print(json.dumps(dict(disc_sha256=expected, bytes_written=written, **scope)), flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        repair(args.base, args.image, args.evidence)
        return 0
    except (ValueError, OSError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
