#!/usr/bin/env python3
"""Repair automatic CPU presentation on an exact private feedback-wave disc.

Only the known input or this compiler's exact output is accepted. The source
stays read only, the copy receives fixed spans, and all bytes are compared.
No game payload is bundled with this tool.
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
from mod_editor.core import nfl2k5_coach_ai as ai, nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core.nfl2k5_cave_manifest import changed_runs
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from tools.b77.vt1_repair import compare, patched_digest

BASE_SHA256 = "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4"
BASE_XBE_SHA256 = "1b41ec19aac6377484b9b30ee7a5c5ab220fb93d61aa3c14bafdb70092a9504f"
DISC_SIZE = 6004408320


def binary(path, writable=False):
    return os.fdopen(os.open(path, (os.O_RDWR if writable else os.O_RDONLY) |
                            getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)),
                     "r+b" if writable else "rb")


def digest(path):
    with binary(path) as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def emit(path, value):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def repair_xbe(payload):
    """Remove only the exact old owner, then use the Studio's current writer."""
    ai.require(hashlib.sha256(payload).hexdigest() == BASE_XBE_SHA256,
               "Unknown feedback-wave executable")
    image = XbeImage(payload)
    old_layout = space.layout(payload)["allocations"]
    owned = ai.allocations(payload)
    buf = bytearray(payload)
    # The eight previous hooks have the same native pins. The full executable
    # hash above also pins every old adapter byte and destination.
    for _, va, pin, _ in ai.HOOKS[:8]:
        before = bytes.fromhex(pin)
        off = image.offset(va, len(before))
        buf[off:off + len(before)] = before
    for _, va, pin, _ in ai.HOOKS[8:]:
        before = bytes.fromhex(pin)
        ai.require(image.read(va, len(before)) == before, "Unexpected new-hook input")
    allocation = owned["code"]
    off = image.offset(allocation["va"], allocation["size"])
    buf[off:off + allocation["size"]] = b"\xcc" * allocation["size"]
    space._seal_scaleout(buf, space._read_scale_directory(payload))
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    source = bytes(buf)
    ai.require(ai.status(source) == "retail", "Old-owner removal did not restore native sites")
    final, receipt = ai.apply(source)
    ai.require(space.layout(final)["allocations"] == old_layout, "Owner allocations moved")
    ai.require(len(final) == len(payload), "Executable size changed")
    ai.require(ai.apply(final)[0] == final, "Studio replay is not idempotent")
    return final, source, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="Read-only known source disc")
    parser.add_argument("--image", type=Path, required=True, help="Existing private copy, repaired in place")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    ai.require(args.base.is_file() and args.image.is_file(), "Expected source and existing copy")
    ai.require(not args.base.is_symlink() and not args.image.is_symlink(), "Symlinks are not accepted")
    ai.require(not args.base.samefile(args.image) and args.image.stat().st_nlink == 1,
               "The output must be an independent copy")
    ai.require(args.base.stat().st_size == args.image.stat().st_size == DISC_SIZE, "Unknown disc size")
    ai.require(shutil.disk_usage("/").free >= 30_000_000_000, "Root free space is below 30 GB")
    ai.require(digest(args.base) == BASE_SHA256, "Unknown source disc hash")
    with binary(args.base) as stream:
        off, size = tt.image_xbe_extent(stream.fileno(), DISC_SIZE)
        stream.seek(off)
        original = stream.read(size)
    final, studio_input, studio_receipt = repair_xbe(original)
    edits = [(off + lo, original[lo:hi], final[lo:hi], "coach_ai_runtime")
             for lo, hi in changed_runs(original, final)]
    expected = patched_digest(args.base, edits)
    before = digest(args.image)
    ai.require(before in (BASE_SHA256, expected), "Unknown input copy hash")
    written = 0
    if before == BASE_SHA256:
        with binary(args.image, writable=True) as stream:
            for at, old, new, _ in edits:
                stream.seek(at)
                ai.require(stream.read(len(old)) == old, "Input changed after preflight")
                stream.seek(at)
                ai.require(stream.write(new) == len(new), "Short write")
                written += len(new)
            stream.flush()
            os.fsync(stream.fileno())
    scope = compare(args.base, args.image, edits)
    after = digest(args.image)
    ai.require(after == expected, "Final disc hash differs from prepared output")
    with binary(args.image) as stream:
        stream.seek(off)
        observed = stream.read(size)
    studio, _ = ai.apply(studio_input)
    ai.require(observed == final == studio, "Executable differs from Studio output")
    args.evidence.mkdir(parents=True, exist_ok=True)
    result = dict(status="applied" if written else "already_applied", bytes_written=written,
                  before_sha256=before, after_sha256=after, readback_verified=True,
                  spans=[dict(offset=at, size=len(old)) for at, old, _, _ in edits])
    emit(args.evidence / ("write.json" if written else "replay.json"), result)
    emit(args.evidence / "scope.json", scope)
    emit(args.evidence / "studio-equality.json", dict(equal=True,
         scope="Whole executable equals Studio coach_ai.apply on the same plan with the old owner removed; resource bytes unchanged",
         executable_sha256=hashlib.sha256(final).hexdigest(), studio_receipt=studio_receipt))
    print(json.dumps({k: v for k, v in result.items() if k != "spans"}))
    print(json.dumps(scope))
    print("Studio executable equality: true; playbook profiles unchanged")


if __name__ == "__main__":
    main()
