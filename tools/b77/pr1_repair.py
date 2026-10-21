#!/usr/bin/env python3
"""Retire 7-on-7 on the pinned feedback disc, without moving any file.

prove --disc INPUT --retail RETAIL --out DIRECTORY: read-only full-disc streamed
proof, Studio retirement pass on the base XBE, full base-plan build on retail
with 7-on-7 installed, and fixed-span repair of extracted default.xbe.
apply --disc COPY --receipt JSON: patch a caller-created copy in place.
The proof never creates a disc copy. Unknown full-disc hashes are refused.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import mod_build, platform_compat
from mod_editor.core import nfl2k5_seven_on_seven as seven
from mod_editor.core import nfl2k5_throw_tuning as tt

BASE_SHA256 = "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4"
OUTPUT_SHA256 = "4af13189418c2b7492430ae4c95629a33813690d1fc5e3b542d4be283bfaa37d"


def require(ok, message):
    if not ok:
        raise ValueError(f"pr1 repair refused: {message}")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, default=lambda obj: asdict(obj) if is_dataclass(obj) else str(obj))
        stream.write("\n")


def spans(before, after, receipt):
    require(len(before) == len(after), "XBE size changed")
    rows = []
    for edit in receipt["edits"]:
        at, size = int(edit["file_offset"], 16), edit["bytes"]
        rows.append((at, before[at:at + size], after[at:at + size], edit["label"]))
    rows.sort()
    cursor = 0
    for at, old, new, _ in rows:
        require(at >= cursor and len(old) == len(new), "invalid fixed spans")
        require(before[cursor:at] == after[cursor:at], "change outside fixed spans")
        cursor = at + len(old)
    require(before[cursor:] == after[cursor:], "change after fixed spans")
    return rows


def stream_hashes(fd, size, rows):
    """Hash the actual file and a virtual fixed-span replacement, reading all bytes."""
    actual, replaced = hashlib.sha256(), hashlib.sha256()
    changed = 0
    for start in range(0, size, 4 << 20):
        raw = platform_compat.pread(fd, min(4 << 20, size - start), start)
        require(len(raw) == min(4 << 20, size - start), "short read")
        out = bytearray(raw)
        for at, old, new, _ in rows:
            lo, hi = max(start, at), min(start + len(raw), at + len(old))
            if lo < hi:
                require(raw[lo-start:hi-start] == old[lo-at:hi-at], "span preimage mismatch")
                out[lo-start:hi-start] = new[lo-at:hi-at]
        actual.update(raw)
        replaced.update(out)
        # Outside spans, out is a direct copy of raw; compare every edited chunk.
        if raw != out:
            changed += sum(a != b for a, b in zip(raw, out))
    return dict(actual_sha256=actual.hexdigest(), replaced_sha256=replaced.hexdigest(),
                bytes_compared=size, changed_bytes=changed, outside_span_changes=0)


def write_spans(fd, rows):
    """Preflight every span, write only differences, read back, and support replay."""
    writes = []
    for at, old, new, label in rows:
        got = platform_compat.pread(fd, len(old), at)
        require(got in (old, new), f"{label}: unexpected preimage")
        if got != new:
            writes.append((at, new))
    for at, new in writes:
        platform_compat.pwrite(fd, new, at)
    os.fsync(fd)
    for at, _, new, label in rows:
        require(platform_compat.pread(fd, len(new), at) == new, f"{label}: readback mismatch")
    return dict(writes=len(writes), written_bytes=sum(len(new) for _, new in writes))


def menu(payload):
    at = seven._offset(payload, seven.REGISTER_SITE_VA)
    table = struct.unpack_from("<I", payload, at + 1)[0]
    count = payload[at + 6] + 1
    require(count in (4, 5), "unexpected menu count")
    values = []
    for pointer in struct.unpack_from(f"<{count}I", payload, seven._offset(payload, table)):
        offset = seven._offset(payload, pointer)
        end = offset
        while end + 2 <= len(payload) and payload[end:end + 2] != b"\0\0":
            end += 2
        values.append(payload[offset:end].decode("utf-16le"))
    return dict(table_va=hex(table), count=count, choices=values)


def prepare(fd):
    size = os.fstat(fd).st_size
    at, length = tt.image_xbe_extent(fd, size)
    before = platform_compat.pread(fd, length, at)
    after, receipt = seven.remove(before)
    rows = spans(before, after, receipt)
    disc_rows = [(at + off, old, new, label) for off, old, new, label in rows]
    scope = stream_hashes(fd, size, disc_rows)
    require(scope["actual_sha256"] in (BASE_SHA256, OUTPUT_SHA256), "unknown input disc hash")
    return before, after, rows, disc_rows, scope


def prove(disc, retail, out):
    out.mkdir(parents=True, exist_ok=True)
    with disc.open("rb") as stream:
        before, after, rows, disc_rows, scope = prepare(stream.fileno())
    require(scope["actual_sha256"] == BASE_SHA256, "prove needs the original feedback disc")
    require(scope["replaced_sha256"] == OUTPUT_SHA256, "unexpected repaired disc hash")
    # All temporary game bytes are removed; receipts retain only their hashes.
    with tempfile.TemporaryDirectory(prefix="pr1-xbe-", dir=out) as folder:
        source, target, native = (Path(folder) / name for name in ("source.xbe", "studio.xbe", "native.xbe"))
        # The integrated disc cannot pass a bare-XBE base plan: its installed
        # runtime options require the full image. Exercise the actual Studio
        # retirement pass on that XBE, and its full base build on retail+7-on-7.
        target.write_bytes(before)
        pass_receipt = mod_build.retire_seven_on_seven(target)
        studio = target.read_bytes()
        require(studio == after, "Studio retirement pass differs from native removal")
        target.unlink()
        retail_xbe = mod_build._xbe_bytes(retail)
        source.write_bytes(seven.apply(retail_xbe)[0])
        plan = mod_build.BuildPlan(str(source), str(target), seven_on_seven=True)
        build_receipt = mod_build.build(plan)
        require(target.read_bytes() == retail_xbe, "Studio base plan failed to restore retail")
        build_receipt["menu_before"] = menu(source.read_bytes())
        build_receipt["menu_after"] = menu(target.read_bytes())
        native.write_bytes(before)
        fd = os.open(native, os.O_RDWR | getattr(os, "O_BINARY", 0))
        try:
            write = write_spans(fd, rows)
            replay = write_spans(fd, rows)
        finally:
            os.close(fd)
        require(native.read_bytes() == studio, "native XBE differs from Studio")
        save(out / "studio_build.json", build_receipt)
        save(out / "studio_base_disc_pass.json", pass_receipt)
    save(out / "write.json", {"transport": "extracted XBE, no disc copy", **write})
    save(out / "replay.json", replay)
    save(out / "scope.json", {"transport": "streamed virtual disc, no disc write", **scope})
    evidence = dict(before_menu=menu(before), after_menu=menu(after),
                    studio_equal=True, before_xbe_sha256=sha(before), after_xbe_sha256=sha(after),
                    changed_bytes=scope["changed_bytes"], spans=[
                        dict(label=label, xbe_offset=hex(off), disc_offset=hex(disc_rows[i][0]),
                             length=len(old), before_hex=old.hex(), after_hex=new.hex())
                        for i, (off, old, new, label) in enumerate(rows)])
    save(out / "studio_equality.json", evidence)
    print(json.dumps({"before_menu": evidence["before_menu"], "after_menu": evidence["after_menu"],
                      "write": write, "replay": replay, "scope": scope, "studio_equal": True}, indent=2))


def apply(disc, receipt):
    fd = os.open(disc, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        before, after, rows, disc_rows, scope = prepare(fd)
        require(scope["replaced_sha256"] == OUTPUT_SHA256, "unexpected repaired disc hash")
        write = write_spans(fd, disc_rows)
        replay = write_spans(fd, disc_rows)
        # Reconstruct the original stream and hash EVERY byte after the write.
        reverse = [(off, new, old, label) for off, old, new, label in disc_rows]
        checked = stream_hashes(fd, os.fstat(fd).st_size, reverse)
        require(checked["actual_sha256"] == OUTPUT_SHA256, "output hash mismatch")
        require(checked["replaced_sha256"] == scope["actual_sha256"], "bytes outside repair changed")
        got = mod_build._xbe_bytes(disc)
        require(got == after, "disc XBE readback mismatch")
        result = dict(write=write, replay=replay, scope=checked, before_menu=menu(before), after_menu=menu(got),
                      studio_writer_equal=True, input_sha256=scope["actual_sha256"])
        save(receipt, result)
        print(json.dumps(result, indent=2))
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    proof = sub.add_parser("prove")
    proof.add_argument("--disc", type=Path, required=True)
    proof.add_argument("--retail", type=Path, required=True)
    proof.add_argument("--out", type=Path, required=True)
    patch = sub.add_parser("apply")
    patch.add_argument("--disc", type=Path, required=True)
    patch.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prove":
        prove(args.disc, args.retail, args.out)
    else:
        apply(args.disc, args.receipt)


if __name__ == "__main__":
    main()
