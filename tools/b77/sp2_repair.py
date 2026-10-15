#!/usr/bin/env python3
"""Pinned human tap-burst repair for the 10/14 v0.6.1 feedback disc.

Only fixed executable, allocator-seal and section-digest spans may change.
The complete input and output hashes are checked before and after writing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import xdvdfs_compact as xd

BASE_DISC_SHA256 = "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4"
BASE_XBE_SHA256 = "1b41ec19aac6377484b9b30ee7a5c5ab220fb93d61aa3c14bafdb70092a9504f"
RESULT_DISC_SHA256 = "0123f8a4deaa571315b8ddfc35d88b1131330fc083f06bdfb8078fbeb784d53e"
RESULT_XBE_SHA256 = "a1304b2c59290d019a1edbcfb128985f191595141c631a15f230081396b40959"
DISC_SIZE, XBE_SIZE, XBE_OFFSET = 6004408320, 12300288, 2398208
SCOPE = (
    (916, 936, 'derived section SHA-1'),
    (2316, 2336, 'derived section SHA-1'),
    (2428, 2448, 'derived section SHA-1'),
    (3508, 3540, 'allocator directory SHA-256'),
    (3141448, 3141453, 'initialize hook'),
    (3141563, 3141568, 'update hook'),
    (12131920, 12132432, 'human burst code'),
    (12279808, 12283904, 'sealed allocator directory'),
)


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def open_binary(path, writable=False):
    flags = os.O_RDWR if writable else os.O_RDONLY
    fd = os.open(path, flags | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    return os.fdopen(fd, "r+b" if writable else "rb")


def digest(stream):
    stream.seek(0)
    result = hashlib.sha256()
    size = 0
    while block := stream.read(8 << 20):
        result.update(block)
        size += len(block)
    return result.hexdigest(), size


def ready():
    require(RESULT_DISC_SHA256 and RESULT_XBE_SHA256 and SCOPE,
            "repair pins are not finalized; no writes are authorized")


def repair_xbe(raw):
    ready()
    require(len(raw) == XBE_SIZE, "unexpected executable size")
    require(sha(raw) in (BASE_XBE_SHA256, RESULT_XBE_SHA256), "unknown complete executable hash")
    fixed, source_receipt = abilities.apply(raw)
    require(len(fixed) == len(raw) and sha(fixed) == RESULT_XBE_SHA256,
            "Studio output differs from the pinned repair")
    changes = [i for i, (a, b) in enumerate(zip(raw, fixed)) if a != b]
    require(all(any(lo <= i < hi for lo, hi, _ in SCOPE) for i in changes),
            "executable change outside fixed spans")
    require(abilities.apply(fixed)[0] == fixed, "Studio replay is not identical")
    return fixed, dict(before_sha256=sha(raw), after_sha256=sha(fixed),
                       changed_bytes=len(changes), outside_scope_changed_bytes=0,
                       studio_equal=True, replay_equal=True, studio_receipt=source_receipt)


def repair_disc(path):
    ready()
    with open_binary(path, writable=True) as stream:
        before, size = digest(stream)
        require(size == DISC_SIZE and before in (BASE_DISC_SHA256, RESULT_DISC_SHA256),
                "unknown complete input disc hash or size")
        entry = xd.read_layout(stream).entries["default.xbe"]
        require((entry.byte_offset, entry.size) == (XBE_OFFSET, XBE_SIZE), "executable extent moved")
        stream.seek(XBE_OFFSET)
        raw = stream.read(XBE_SIZE)
        fixed, executable = repair_xbe(raw)
        writes = []
        for lo, hi, purpose in SCOPE:
            if raw[lo:hi] == fixed[lo:hi]:
                continue
            stream.seek(XBE_OFFSET + lo)
            require(stream.write(fixed[lo:hi]) == hi - lo, "short disc write")
            writes.append(dict(offset=XBE_OFFSET + lo, size=hi-lo, purpose=purpose))
        stream.flush()
        os.fsync(stream.fileno())
        after, size = digest(stream)
        require(after == RESULT_DISC_SHA256 and size == DISC_SIZE, "disc readback hash differs")
    return dict(schema="b773/sp2-repair/v1", before_sha256=before, after_sha256=after,
                changed_bytes=executable["changed_bytes"], written_bytes=sum(r["size"] for r in writes),
                writes=writes, executable=executable)


def repair_executable(path):
    with open_binary(path, writable=True) as stream:
        raw = stream.read(XBE_SIZE + 1)
        fixed, receipt = repair_xbe(raw)
        writes = []
        for lo, hi, purpose in SCOPE:
            if raw[lo:hi] != fixed[lo:hi]:
                stream.seek(lo)
                require(stream.write(fixed[lo:hi]) == hi-lo, "short executable write")
                writes.append(dict(offset=lo, size=hi-lo, purpose=purpose))
        stream.flush()
        os.fsync(stream.fileno())
        stream.seek(0)
        require(stream.read() == fixed, "executable readback differs")
    return dict(schema="b773/sp2-xbe-write/v1", **receipt,
                written_bytes=sum(r["size"] for r in writes), writes=writes)


def compare_executable(before, after, *, studio=False):
    ready()
    with open_binary(before) as source, open_binary(after) as output:
        a, b = source.read(XBE_SIZE+1), output.read(XBE_SIZE+1)
    require(len(a) == len(b) == XBE_SIZE, "unexpected executable comparison sizes")
    require(sha(a) == BASE_XBE_SHA256 and sha(b) == RESULT_XBE_SHA256, "unknown comparison hashes")
    changes = [i for i, (x,y) in enumerate(zip(a,b)) if x != y]
    outside = sum(not any(lo <= i < hi for lo,hi,_ in SCOPE) for i in changes)
    require(outside == 0, "executable change outside owned spans")
    result = dict(schema="b773/sp2-studio/v1" if studio else "b773/sp2-xbe-scope/v1",
                  compared_bytes=len(a), changed_bytes=len(changes), outside_scope_changed_bytes=outside,
                  before_sha256=sha(a), after_sha256=sha(b))
    if studio:
        compiled, _ = abilities.apply(a)
        require(compiled == b, "full executable differs from Studio output")
        result.update(studio_equal=True, studio_writer="nfl2k5_abilities_runtime.apply")
    return result


def compare_scope(before, after):
    ready()
    with open_binary(before) as left, open_binary(after) as right:
        require(digest(left) == (BASE_DISC_SHA256, DISC_SIZE), "scope input is not the pinned base disc")
        require(digest(right) == (RESULT_DISC_SHA256, DISC_SIZE), "scope output is not the pinned repaired disc")
        left.seek(0)
        right.seek(0)
        at = changed = outside = 0
        spans = [(XBE_OFFSET+lo, XBE_OFFSET+hi) for lo, hi, _ in SCOPE]
        while a := left.read(8 << 20):
            b = right.read(len(a))
            require(len(a) == len(b), "scope lengths differ")
            if a != b:
                for i, (x, y) in enumerate(zip(a, b)):
                    if x != y:
                        changed += 1
                        outside += not any(lo <= at+i < hi for lo, hi in spans)
            at += len(a)
        require(not right.read(1) and at == DISC_SIZE, "scope sizes differ")
        require(outside == 0, "change outside owned disc spans")
    return dict(schema="b773/sp2-scope/v1", compared_bytes=at, changed_bytes=changed,
                outside_scope_changed_bytes=outside,
                scope=[dict(start=XBE_OFFSET+lo, end_exclusive=XBE_OFFSET+hi, purpose=why)
                       for lo, hi, why in SCOPE])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    disc = sub.add_parser("disc")
    disc.add_argument("--disc", type=Path, required=True)
    scope = sub.add_parser("scope")
    scope.add_argument("--before", type=Path, required=True)
    scope.add_argument("--after", type=Path, required=True)
    executable = sub.add_parser("xbe")
    executable.add_argument("--xbe", type=Path, required=True)
    scoped = sub.add_parser("scope-xbe")
    studio = sub.add_parser("studio")
    for command in (scoped, studio):
        command.add_argument("--before", type=Path, required=True)
        command.add_argument("--after", type=Path, required=True)
    for command in (disc, scope, executable, scoped, studio):
        command.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "disc":
        result = repair_disc(args.disc)
    elif args.command == "scope":
        result = compare_scope(args.before, args.after)
    elif args.command == "xbe":
        result = repair_executable(args.xbe)
    else:
        result = compare_executable(args.before, args.after, studio=args.command == "studio")
    with args.receipt.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
