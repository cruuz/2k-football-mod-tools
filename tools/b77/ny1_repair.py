#!/usr/bin/env python3
"""Fix Giants home shoulders on ONE copy of the pinned base disc.

  ny1_repair.py --input BASE.iso --output NY1.iso --receipts DIR

The input is always read-only. An existing output is accepted only if every
unowned byte equals the base and its owned spans match the input/output pins.
The Studio's uniform finish pass performs the writes. Receipts cover the
write, zero-byte replay, complete disc comparison and Studio byte equality.
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
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_nyg_numbers as numbers
from mod_editor.core import nfl2k5_modern_metlife as native

BASE_SHA256 = "d735215760ff08bceeff2a3860baccf0a84885422a4205e966154e948812103e"
BASE_SIZE = 6004408320
BLOCK = 4 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def binary(path, flags):
    return os.open(path, flags | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0), 0o644)


def file_sha(path):
    with os.fdopen(binary(path, os.O_RDONLY), "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, document):
    require(not path.is_symlink(), "receipt is a symlink")
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, indent=2)
        stream.write("\n")


def read_resource(path):
    with native._outer_image()(path) as image:
        entries = [e for e in image.entries if e.name_id == native.name_id(numbers.RESOURCE)]
        require(len(entries) == 1, "Giants home package absent or duplicated")
        entry = entries[0]
        raw = image.read(entry.virtual_offset, entry.size)
        ranges = []
        for p in numbers.pins()["digits"]:
            for pack, offset, length in image._segments(entry.virtual_offset + p["offset"], p["length"]):
                start = pack.image_offset + offset
                ranges.append(dict(start=start, end=start + length, digit=p["digit"]))
        return raw, sorted(ranges, key=lambda r: r["start"])


def compare_scope(before, after, ranges):
    """Read every byte of both files, including the XDVDFS and unused tail."""
    import numpy as np
    require(before.stat().st_size == after.stat().st_size == BASE_SIZE, "disc length changed")
    changed = outside = 0
    hashes = [hashlib.sha256(), hashlib.sha256()]
    with os.fdopen(binary(before, os.O_RDONLY), "rb") as fb, os.fdopen(binary(after, os.O_RDONLY), "rb") as fa:
        offset = 0
        while True:
            b, a = fb.read(BLOCK), fa.read(BLOCK)
            if not b:
                require(not a, "output has extra bytes")
                break
            hashes[0].update(b); hashes[1].update(a)
            require(len(b) == len(a), "short output read")
            if b != a:
                diff = np.frombuffer(b, np.uint8) != np.frombuffer(a, np.uint8)
                changed += int(diff.sum())
                for r in ranges:
                    lo, hi = max(offset, r["start"]), min(offset + len(b), r["end"])
                    if lo < hi:
                        diff[lo - offset:hi - offset] = False
                outside += int(diff.sum())
            offset += len(b)
    return dict(schema="b772/ny1/disc-scope/v1", compared_bytes=offset,
                before_sha256=hashes[0].hexdigest(), after_sha256=hashes[1].hexdigest(),
                changed_bytes=changed, changed_outside_owned=outside,
                owned_ranges=ranges, owned_bytes=sum(r["end"] - r["start"] for r in ranges))


def run(args):
    source, output = args.input.resolve(strict=True), args.output.absolute()
    require(not args.input.is_symlink() and not output.is_symlink(), "disc symlinks are refused")
    require(source != output.resolve(), "input and output must differ")
    require(source.stat().st_size == BASE_SIZE and file_sha(source) == BASE_SHA256, "unknown input disc hash/size")
    raw, ranges = read_resource(source)
    parts, _ = numbers.compile_resource(raw)
    require(len(parts) == 10, "base disc is not the pinned unrepaired input")
    needed = 0 if output.exists() else BASE_SIZE
    require(shutil.disk_usage("/").free - needed >= 25 * 1024**3, "copy would cross the 25 GiB root floor")
    receipt_dir = args.receipts.resolve()
    require(receipt_dir not in (source, output.resolve()), "receipt directory overlaps a disc")
    receipt_dir.mkdir(parents=True, exist_ok=True)
    if output.exists():
        old_scope = compare_scope(source, output, ranges)
        require(old_scope["changed_outside_owned"] == 0, "existing output differs outside owned spans")
        current, output_ranges = read_resource(output)
        require(ranges == output_ranges, "output resource mapping differs")
        numbers.compile_resource(current)
    else:
        with os.fdopen(binary(source, os.O_RDONLY), "rb") as src, os.fdopen(
                binary(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "wb") as dst:
            shutil.copyfileobj(src, dst, BLOCK)
            dst.flush(); os.fsync(dst.fileno())
        require(file_sha(output) == BASE_SHA256, "new copy differs from base")
    receipt = numbers.apply_to_image(output, strict=True)
    write_json(receipt_dir / "disc_write.json", dict(schema="b772/ny1/disc-write/v1",
               input=str(source), output=str(output), base_sha256=BASE_SHA256, **receipt))
    replay = numbers.apply_to_image(output, strict=True)
    require(replay["written_spans"] == replay["written_bytes"] == replay["changed_bytes"] == 0,
            "repair replay wrote bytes")
    write_json(receipt_dir / "disc_replay.json", dict(schema="b772/ny1/disc-replay/v1", **replay))
    scope = compare_scope(source, output, ranges)
    require(scope["before_sha256"] == BASE_SHA256 and scope["changed_outside_owned"] == 0,
            "full-disc byte-scope check failed")
    write_json(receipt_dir / "disc_scope.json", scope)
    actual, output_ranges = read_resource(output)
    require(output_ranges == ranges, "output resource mapping changed")
    equality = [dict(offset=at, length=len(data), studio_sha256=numbers.sha(data),
                     disc_sha256=numbers.sha(actual[at:at + len(data)]),
                     equal=actual[at:at + len(data)] == data) for at, data in parts]
    require(all(r["equal"] for r in equality), "disc differs from the Studio compiler")
    write_json(receipt_dir / "disc_studio_equality.json", dict(schema="b772/ny1/studio-equality/v1",
               compiler="mod_editor.core.nfl2k5_nyg_numbers.compile_resource", all_equal=True, spans=equality))
    return dict(written_spans=receipt["written_spans"], written_bytes=receipt["written_bytes"],
                changed_bytes=scope["changed_bytes"], replay_written_bytes=0,
                changed_outside_owned=0, studio_equal=True, output_sha256=scope["after_sha256"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("input", "output", "receipts"):
        parser.add_argument("--" + flag, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args)))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, "ny1_repair: REFUSED: " + str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
