#!/usr/bin/env python3
"""b77 v1b: 30 ft uprights for the pre-2014 Anniversary moments, on a SOFTDRINK 2K28 v0.5 disc's default.xbe, natively.

    v1b_repair.py --xbe IN_XBE --out-dir OUT --receipt RECEIPT.json [--disc IMAGE]

IN_XBE is the disc's ``default.xbe`` (shared with other jobs): the v0.5 file, or the output of the v1 repair
(``v1_repair.py``), or of any other job's repair. It may be stacked in any order with them. OUT receives ``default.xbe`` with
only these bytes changed:

* the four executable sites of the goalposts: the call at VA 0x99B16 (its 4-byte target now the owner's stub), the two
  ``push <upright line top>`` at 0x986AA / 0x986FB (5 bytes each, now calls to one stub) and the collision's ``fadd`` at
  0x1C6A2C (6 bytes, now a call and a nop). These are the bytes v1 changed for the 35 ft posts; v1b supersedes them, so the
  result is the same whether or not v1's executable part was applied first (v1's goalpost scenes in pack 0 are required and
  are not touched here);
* the owner's two allocations: 176 bytes of code in the scale-out code section and 32 read-only bytes (period mask, heights, scene descriptors);
* derived seals only, recomputed from the bytes above: the ``.text`` section digest, the allocator directory page (its request
  list gains the owner's two requests), its header copy and the section descriptors.

The owner ``nfl2k5_period_goalposts`` is placed after every other owner (like K128), so no other owner's address or byte
moves; the repair proves it. It is a function of the owned bytes only: the executable must carry the sealed scale-out allocator
(the v0.5 one), the four sites must hold their retail or v1 bytes (or the owner's own), otherwise it refuses. Idempotent: an
input that already carries the owner comes back byte-identical (status ALREADY_APPLIED). The receipt carries the exact
before/after SHA-256, the declared byte ranges and a scope proof that every byte outside them is identical. With ``--disc``
(read only) it also states where each range sits in that disc image.
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
from mod_editor.core import nfl2k5_period_goalposts as pg  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

# The SOFTDRINK 2K28 v0.5 disc's default.xbe (2026-10-06, disc sha256 5317a7b1...), for the receipt's provenance note only.
V05_DISC_SHA256 = "5317a7b16558621e4030f3883789060f37a42af542df431a5d338b2ca1f3c76f"
V05_XBE_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
XBE_NAME = "default.xbe"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        chunks = []
        while True:
            block = os.read(fd, 1 << 20)
            if not block:
                return b"".join(chunks)
            chunks.append(block)
    finally:
        os.close(fd)


def write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0), 0o644)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)
    os.replace(tmp, path)
    if read(path) != data:
        raise ValueError(f"{path}: read-back failed")


def scope(before: bytes, after: bytes, ranges: list[tuple[int, int]]) -> dict:
    """Bytes changed inside / outside the declared [start, end) ranges (the file size never changes)."""
    if len(before) != len(after):
        raise ValueError("a file changed size")
    owned = bytearray(len(before))
    for start, end in ranges:
        owned[start:end] = b"\x01" * (end - start)
    inside = outside = 0
    first_outside = None
    for i in range(len(before)):
        if before[i] != after[i]:
            if owned[i]:
                inside += 1
            else:
                outside += 1
                first_outside = i if first_outside is None else first_outside
    return dict(declared_ranges=[[hex(a), hex(b), b - a] for a, b in ranges], bytes_changed_inside=inside,
                bytes_changed_outside=outside, first_outside=None if first_outside is None else hex(first_outside),
                identical_outside=outside == 0)


def declared_ranges(xbe: bytes) -> tuple[list[tuple[int, int]], list[dict]]:
    """File ranges the repair owns in this executable (``xbe`` is the repaired file): the four sites, the owner's two
    allocations and the derived seals."""
    a = pg.allocations(xbe)
    image = XbeImage(xbe)
    ranges, rows = [], []
    for kind in ("code", "read_only"):
        ranges.append((a[kind]["raw"], a[kind]["raw"] + a[kind]["size"]))
        rows.append(dict(label=f"owner {kind} allocation", va=hex(a[kind]["va"]), file_offset=hex(a[kind]["raw"]), size=a[kind]["size"]))
    for label, va, accepted, after in pg.sites(a["code"]["va"], a["read_only"]["va"]):
        # the hook's call opcode stays retail: only its 4-byte target is owned there
        skip = 1 if label == "stadium_load_hook" else 0
        at = image.offset(va + skip, len(after) - skip)
        ranges.append((at, at + len(after) - skip))
        rows.append(dict(label=f"site {label}", va=hex(va + skip), file_offset=hex(at), size=len(after) - skip))
    text = next(s for s in _sections(xbe) if s.virtual_address <= pg.LOAD_CALL_VA < s.virtual_address + s.raw_size)
    derived = [("section digest of .text", text.header_offset + 36, 20),
               ("allocator directory page (request list, sizes, seals)", space.SCALE_DIRECTORY, space.PAGE),
               ("allocator directory header copy", space.DIRECTORY, space.LIB_COPY - space.DIRECTORY),
               ("section descriptors and digests of the scale-out sections", space.META_START,
                space.SCALE_HEADER_END - space.META_START)]
    for label, at, size in derived:
        ranges.append((at, at + size))
        rows.append(dict(label=f"{label} (derived)", file_offset=hex(at), size=size))
    return sorted(set(ranges)), rows


def disc_offsets(disc: Path) -> dict:
    """Where default.xbe starts inside a disc image (XDVDFS directory only; read only)."""
    sys.path.insert(0, str(ROOT / "tools"))
    from mod_editor.core import nfl2k5_throw_tuning as tt
    fd = os.open(disc, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        size = os.fstat(fd).st_size
        offset, length = tt.image_xbe_extent(fd, size)
        return dict(image=str(disc), image_size=size, xbe_offset=int(offset), xbe_size=int(length))
    finally:
        os.close(fd)


def repair(xbe: bytes) -> tuple[bytes, dict]:
    before_state = pg.status(xbe)
    if before_state == "foreign":
        raise ValueError("unexpected input bytes: a goalpost site or the owner's code is foreign")
    key = lambda x: (x["owner"], x["kind"], x["va"], x["raw"], x["size"])
    old_alloc = {key(x) for x in space.layout(xbe)["allocations"]}
    new, detail = pg.apply(xbe)
    new_alloc = {key(x) for x in space.layout(new)["allocations"]}
    if old_alloc - new_alloc or {x[0] for x in new_alloc - old_alloc} - {pg.OWNER}:
        raise ValueError("another owner's allocation moved")
    ranges, rows = declared_ranges(new)
    receipt = dict(
        job="b77 v1b", option="modern_goalposts (period uprights for pre-2014 Anniversary moments)", runtime_witnessed=False,
        state_before=before_state, state_after=pg.status(new),
        files={XBE_NAME: dict(size=len(xbe), before_sha256=sha(xbe), after_sha256=sha(new), input_is_v05=sha(xbe) == V05_XBE_SHA256,
                              sites=rows, edits=detail["edits"], owner=pg.OWNER,
                              allocations=dict(code=pg.allocations(new)["code"], read_only=pg.allocations(new)["read_only"]),
                              other_owner_allocations_moved=0, scope=scope(xbe, new, ranges))},
        pins=dict(table=dict(path="data/nfl2k5_moment_goalposts.json", sha256=sha(pg.DATA.read_bytes())),
                  cave_sha256=sha(pg.code_for(pg.allocations(new)["code"]["va"], pg.allocations(new)["read_only"]["va"])),
                  words=dict(modern=pg.WORD_MODERN, period=pg.WORD_PERIOD)))
    if not receipt["files"][XBE_NAME]["scope"]["identical_outside"]:
        raise ValueError("bytes changed outside the declared ranges")
    already = detail["status"] == "already_applied"
    receipt["status"] = "ALREADY_APPLIED" if already else "OK"
    if already and new != xbe:
        raise ValueError("an already-applied input changed")
    return new, receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--xbe", type=Path, required=True, help="the disc's default.xbe")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--disc", type=Path, help="optional: the disc image the input came from (read only), for offsets")
    args = ap.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / XBE_NAME
    for target in (out, args.receipt):
        if target.resolve() == args.xbe.resolve():
            raise ValueError("an output aliases the input")
    xbe = read(args.xbe)
    new, receipt = repair(xbe)
    if args.disc:
        where = disc_offsets(args.disc)
        receipt["files"][XBE_NAME]["disc_ranges"] = [
            [hex(where["xbe_offset"] + int(a, 16)), hex(where["xbe_offset"] + int(b, 16)), n]
            for a, b, n in receipt["files"][XBE_NAME]["scope"]["declared_ranges"]]
        receipt["disc"] = where
    write(out, new)
    args.receipt.write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": receipt["status"], XBE_NAME: receipt["files"][XBE_NAME]["after_sha256"],
                      "outside_changed": receipt["files"][XBE_NAME]["scope"]["bytes_changed_outside"],
                      "inside_changed": receipt["files"][XBE_NAME]["scope"]["bytes_changed_inside"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
