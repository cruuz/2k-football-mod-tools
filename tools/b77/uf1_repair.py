#!/usr/bin/env python3
"""Fix the 2026 home/away kit art (b772 uf1) on ONE copy of the pinned ny1 disc.

  uf1_repair.py --input NY1.iso --output UF1.iso --receipts DIR

The input is always read-only and must be the ny1 disc (co2 plus the Giants home shoulder fix). An existing output
is accepted only if every unowned byte equals the input and its owned spans match the input or output pins. The
Studio's kit finish pass (``mod_editor.core.nfl2k5_kit_fixes_2026``) performs the writes. Receipts cover the
write, a zero-byte replay, a complete disc comparison, Studio byte equality and a check that no other archive
entry shares an owned byte.
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
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402
from mod_editor.core import nfl2k5_modern_metlife as native  # noqa: E402

BASE_SHA256 = "33fa4166d577f11f740d66d49b1ecccd8494427a30efcf7b55311b6232097d63"   # ny1 output disc
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


def read_resources(path):
    """Every kit package the data owns: raw bytes, owned disc ranges, and the pack extents of every OTHER entry
    (to prove no other archive entry aliases an owned byte)."""
    spec = fixes.spec()
    wanted = fixes.selectors(spec)
    raws, ranges, entry_extents = {}, [], []
    with native._outer_image()(path) as image:
        ids = {native.name_id(s + ".IFF"): s for s in wanted}
        seen = {}
        for entry in image.entries:
            selector = ids.get(entry.name_id)
            extents = [(pack.image_offset + offset, pack.image_offset + offset + length)
                       for pack, offset, length in image._segments(entry.virtual_offset, entry.size)]
            if selector is None:
                entry_extents.extend(extents)
                continue
            require(selector not in seen, selector + " kit package duplicated")
            seen[selector] = entry
        require(set(seen) == set(wanted), "a kit package is absent")
        for selector, entry in sorted(seen.items()):
            raws[selector] = image.read(entry.virtual_offset, entry.size)
            for row in [r for r in spec["textures"] if r["selector"] == selector]:
                for pack, offset, length in image._segments(entry.virtual_offset + row["offset"], row["length"]):
                    start = pack.image_offset + offset
                    ranges.append(dict(start=start, end=start + length, selector=selector, chunk=row["chunk"]))
    return raws, sorted(ranges, key=lambda r: r["start"]), entry_extents


def alias_check(ranges, extents):
    """No other archive entry may cover an owned byte (a shared texture would change another style)."""
    import bisect
    extents = sorted(extents)
    starts = [e[0] for e in extents]
    hits = []
    for r in ranges:
        i = bisect.bisect_right(starts, r["end"]) - 1
        while i >= 0 and extents[i][0] < r["end"]:
            if extents[i][1] > r["start"]:
                hits.append(dict(r, other_extent=list(extents[i])))
            i -= 1
            if len(hits) > 50:
                break
    return hits


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
            hashes[0].update(b)
            hashes[1].update(a)
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
    return dict(schema="b772/uf1/disc-scope/v1", compared_bytes=offset,
                before_sha256=hashes[0].hexdigest(), after_sha256=hashes[1].hexdigest(),
                changed_bytes=changed, changed_outside_owned=outside,
                owned_ranges=ranges, owned_bytes=sum(r["end"] - r["start"] for r in ranges))


def run(args):
    source, output = args.input.resolve(strict=True), args.output.absolute()
    require(not args.input.is_symlink() and not output.is_symlink(), "disc symlinks are refused")
    require(source != output.resolve(), "input and output must differ")
    require(source.stat().st_size == BASE_SIZE and file_sha(source) == BASE_SHA256, "unknown input disc hash/size")
    raws, ranges, extents = read_resources(source)
    parts = {}
    for selector, raw in raws.items():
        replacements, receipt = fixes.compile_resource(selector, raw, strict=True)
        require(receipt["state"] == "applied" and replacements, selector + ": input is not the pinned unrepaired kit")
        parts[selector] = replacements
    aliases = alias_check(ranges, extents)
    require(not aliases, "another archive entry shares an owned byte: " + json.dumps(aliases[:3]))
    needed = 0 if output.exists() else BASE_SIZE
    require(shutil.disk_usage("/").free - needed >= 25 * 1024**3, "copy would cross the 25 GiB root floor")
    receipt_dir = args.receipts.resolve()
    require(receipt_dir not in (source, output.resolve()), "receipt directory overlaps a disc")
    receipt_dir.mkdir(parents=True, exist_ok=True)
    if output.exists():
        old_scope = compare_scope(source, output, ranges)
        require(old_scope["changed_outside_owned"] == 0, "existing output differs outside owned spans")
        current, output_ranges, _ = read_resources(output)
        require(ranges == output_ranges, "output resource mapping differs")
        for selector, raw in current.items():
            fixes.compile_resource(selector, raw, strict=True)
    else:
        with os.fdopen(binary(source, os.O_RDONLY), "rb") as src, os.fdopen(
                binary(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "wb") as dst:
            shutil.copyfileobj(src, dst, BLOCK)
            dst.flush()
            os.fsync(dst.fileno())
        require(file_sha(output) == BASE_SHA256, "new copy differs from base")
    receipt = fixes.apply_to_image(output, strict=True)
    write_json(receipt_dir / "disc_write.json", dict(schema="b772/uf1/disc-write/v1", input=str(source),
               output=str(output), base_sha256=BASE_SHA256, **receipt))
    replay = fixes.apply_to_image(output, strict=True)
    require(replay["written_spans"] == replay["written_bytes"] == replay["changed_bytes"] == 0,
            "repair replay wrote bytes")
    write_json(receipt_dir / "disc_replay.json", dict(schema="b772/uf1/disc-replay/v1", **replay))
    scope = compare_scope(source, output, ranges)
    require(scope["before_sha256"] == BASE_SHA256 and scope["changed_outside_owned"] == 0,
            "full-disc byte-scope check failed")
    write_json(receipt_dir / "disc_scope.json", scope)
    write_json(receipt_dir / "disc_alias.json", dict(schema="b772/uf1/alias-check/v1", owned_ranges=len(ranges),
               other_entry_extents=len(extents), overlapping=aliases))
    actual, output_ranges, _ = read_resources(output)
    require(output_ranges == ranges, "output resource mapping changed")
    equality = []
    for selector, replacements in sorted(parts.items()):
        for at, data in replacements:
            got = actual[selector][at:at + len(data)]
            equality.append(dict(selector=selector, offset=at, length=len(data), studio_sha256=fixes.sha(data),
                                 disc_sha256=fixes.sha(got), equal=got == data))
    require(all(r["equal"] for r in equality), "disc differs from the Studio compiler")
    write_json(receipt_dir / "disc_studio_equality.json", dict(schema="b772/uf1/studio-equality/v1",
               compiler="mod_editor.core.nfl2k5_kit_fixes_2026.compile_resource", all_equal=True, spans=equality))
    return dict(kits=len(parts), written_spans=receipt["written_spans"], written_bytes=receipt["written_bytes"],
                changed_bytes=scope["changed_bytes"], replay_written_bytes=0, changed_outside_owned=0,
                aliased_owned_bytes=0, studio_equal=True, output_sha256=scope["after_sha256"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("input", "output", "receipts"):
        parser.add_argument("--" + flag, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args)))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, "uf1_repair: REFUSED: " + str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
