#!/usr/bin/env python3
"""ic1 fixed-span repair and offline proof, without making a disc copy.

--input BASE --receipts DIR checks the pinned base read-only, simulates writes
in a sparse memory overlay, replays, and compares the entire virtual disc.
--disc EXISTING_COPY additionally writes the repair to that copy in place.
The offline receipt explicitly says virtual; it is not a physical-write claim.
No command copies an image. Unknown full-image hashes are refused.
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
from mod_editor.core import nfl2k5_menu_icon_orientation as icons
from mod_editor.core import nfl2k5_modern_fans as fans

BASE_SHA256 = "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4"
BLOCK = 8 << 20


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for data in iter(lambda: f.read(BLOCK), b""):
            h.update(data)
    return h.hexdigest()


class Overlay:
    """Only fixed-span writes are materialized; all other reads use the base."""
    def __init__(self, archive):
        self.archive, self.entries, self.writes = archive, archive.entries, {}

    def read(self, at, size):
        data = bytearray(self.archive.read(at, size))
        for start, payload in self.writes.items():
            lo, hi = max(at, start), min(at + size, start + len(payload))
            if lo < hi:
                data[lo - at:hi - at] = payload[lo - start:hi - start]
        return bytes(data)

    def write(self, at, payload):
        self.writes[at] = bytes(payload)
        return len(payload)


def physical(archive, plan):
    ranges = []
    for at, before, after in plan:
        used = 0
        for pack, offset, length in archive._segments(at, len(before)):
            ranges.append((pack.image_offset + offset, before[used:used + length], after[used:used + length]))
            used += length
        require(used == len(before), "incomplete physical mapping")
    ranges.sort()
    require(all(a[0] + len(a[1]) <= b[0] for a, b in zip(ranges, ranges[1:])), "overlapping writes")
    return ranges


def compare_stream(base, ranges, disc=None):
    """Compare every byte to the base, either a real image or the sparse overlay."""
    h = hashlib.sha256()
    changed = outside = 0
    fd = open(disc, "rb") if disc is not None else None
    try:
        with open(base, "rb") as src:
            offset = 0
            while True:
                before = src.read(BLOCK)
                if not before:
                    break
                expected = bytearray(before)
                for at, old, new in ranges:
                    lo, hi = max(offset, at), min(offset + len(before), at + len(old))
                    if lo < hi:
                        require(before[lo - offset:hi - offset] == old[lo - at:hi - at], "base span mismatch")
                        expected[lo - offset:hi - offset] = new[lo - at:hi - at]
                after = fd.read(len(before)) if fd else bytes(expected)
                require(len(after) == len(before), "disc length differs")
                if after != expected:
                    # The strict expected-output comparison includes owned bytes too.
                    raise ValueError(f"disc differs from Studio output near image offset {offset}")
                if after != before:
                    changed += sum(a != b for a, b in zip(before, after))
                    # Check the difference itself against the declared physical spans.
                    for i, (a, b) in enumerate(zip(before, after)):
                        if a != b and not any(at <= offset + i < at + len(old) for at, old, _ in ranges):
                            outside += 1
                h.update(after)
                offset += len(before)
            require(fd is None or fd.read(1) == b"", "disc has a trailing byte")
    finally:
        if fd:
            fd.close()
    return dict(compared_bytes=offset, changed_bytes=changed, changed_outside_owned=outside,
                output_sha256=h.hexdigest())


def save(folder, name, payload):
    (folder / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--receipts", type=Path, required=True)
    p.add_argument("--disc", type=Path, help="existing copy to repair in place; never the input")
    args = p.parse_args(argv)
    require(digest(args.input) == BASE_SHA256, "unknown input image hash")
    with fans._outer_image()(args.input) as archive:
        plan, write = icons.plan_archive(archive)
        require(len(plan) == 1, "base does not need exactly the pinned Denver correction")
        ranges = physical(archive, plan)
        overlay = Overlay(archive)
        fans._write_all(overlay, plan)
        replay, replay_state = icons.plan_archive(overlay)
        require(not replay, "virtual replay writes bytes")
        _, donor = icons.locate(archive, icons.DONOR)
        _, back = icons.locate(overlay, icons.TARGET)
        tx, _ = fans._tools()
        def rgba(span):
            c = tx.parse_chunks(span, allow_trailing=True)[0]
            d, _ = tx.decode_chunk(span, c)
            t = tx.parse_texture(d, c)
            return tx.texture_to_rgba(d, c, t)
        source_rgba = rgba(donor)
        expected = b"".join(source_rgba[(y * 64 + x) * 4:(y * 64 + x + 1) * 4]
                            for y in range(64) for x in reversed(range(64)))
        require(rgba(back) == expected, "decoded correction is not the exact donor reflection")
        equality = dict(studio_equal=back == icons.reflect_slot(plan[0][1], donor),
                        decoded_rgba_exact_reflection=True, target_sha256=icons.sha(back))
        require(equality["studio_equal"], "overlay differs from the Studio compile")
    scope = compare_stream(args.input, ranges)
    mode = "virtual_overlay"
    if args.disc:
        require(not os.path.samefile(args.input, args.disc), "input must remain read-only; choose a separate copy")
        current = digest(args.disc)
        require(current in (BASE_SHA256, scope["output_sha256"]), "unknown destination image hash")
        # All checks, compilation and the expected full-image hash precede mutation.
        # Hold one descriptor through hash validation and all physical writes.
        fd = os.open(args.disc, os.O_RDWR | getattr(os, "O_BINARY", 0))
        original = []
        with os.fdopen(fd, "r+b") as f:
            h = hashlib.sha256()
            for block in iter(lambda: f.read(BLOCK), b""):
                h.update(block)
            require(h.hexdigest() == current, "destination changed before opening")
            try:
                for at, before, after in ranges:
                    f.seek(at)
                    old = f.read(len(before))
                    require(old in (before, after), "destination span changed")
                    if old != after:
                        original.append((at, old))
                        f.seek(at)
                        require(f.write(after) == len(after), "short write")
                f.flush()
                os.fsync(f.fileno())
                for at, _, after in ranges:
                    f.seek(at)
                    require(f.read(len(after)) == after, "physical read-back differs")
            except BaseException:
                for at, old in original:
                    f.seek(at)
                    f.write(old)
                f.flush()
                os.fsync(f.fileno())
                raise
        scope = compare_stream(args.input, ranges, args.disc)
        with fans._outer_image()(args.disc) as archive:
            replay, replay_state = icons.plan_archive(archive)
            require(not replay, "physical replay writes bytes")
        mode = "physical_disc"
        write["written"] = len(original)
        if not original:
            write["changed_bytes"] = 0
    args.receipts.mkdir(parents=True, exist_ok=True)
    common = dict(mode=mode, input_sha256=BASE_SHA256)
    save(args.receipts, "write.json", dict(common, **write,
        physical_spans=[dict(offset=at, size=len(old)) for at, old, _ in ranges]))
    save(args.receipts, "replay.json", dict(common, writes=len(replay), changed_bytes=0, **replay_state))
    save(args.receipts, "scope.json", dict(common, **scope))
    save(args.receipts, "studio_equality.json", dict(common, **equality))
    print(f"MODE {mode}: {write['written']} writes; replay {len(replay)} writes")
    print(f"SCOPE {scope['compared_bytes']} bytes compared; {scope['changed_bytes']} changed; {scope['changed_outside_owned']} outside owned spans")
    print("STUDIO equal=True; decoded RGBA exact reflection=True")
    print(f"OUTPUT_SHA256 {scope['output_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
