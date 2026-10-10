#!/usr/bin/env python3
"""b77 v1: modern goalposts (uprights 35 ft above the crossbar) on a SOFTDRINK 2K28 v0.5 disc's files, natively.

    v1_repair.py --pack0 IN_PACK0 --xbe IN_XBE --out-dir OUT --receipt RECEIPT.json [--disc IMAGE]

IN_PACK0 is the disc's ``vc_53450030/0`` and IN_XBE its ``default.xbe`` (both shared with other jobs). OUT receives
``vc_53450030__0`` and ``default.xbe`` with only these bytes changed:

* pack 0: the two shared goalpost scenes of gamedata.iff (outer 346), each rebuilt inside its own stored span (same
  size, wrapper identical): ``goalpost_shadow`` (chunk 71, 1,968 bytes) and ``goalpost`` (chunk 88, 2,832 bytes).
  gamedata.iff is found through pack 0's own index (entry 346, name id 0x00B6926C) and the chunks through its own
  chunk table, so other owners' edits elsewhere in pack 0 (and gamedata.iff's appended chunks) are carried as they are;
* default.xbe: three 4-byte operands (``0x986AB``, ``0x986FC``: the upright lines' tops 1,219.2 -> 1,371.6;
  ``0x1C6A2E``: the ball/upright collision top re-pointed from 0x50A510 to the 1,371.6 literal at 0x4F689C) and the
  ``.text`` section digest (derived: re-sealed after the operands, and again by whoever writes .text after this).

The repair is a function of those bytes only: each goalpost span must hold its pinned retail or modern bytes, each
XBE site its retail or modern bytes (and 0x4F689C must hold 1,371.6), or it refuses. Idempotent: already-modern inputs
come back byte-identical (status ALREADY_APPLIED). The receipt carries the exact before/after SHA-256 of every file
and span, the declared byte ranges and a scope proof that every byte outside them is identical. With ``--disc`` (read
only) it also states where each range sits in that disc image.
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
from mod_editor.core import nfl2k5_modern_goalposts as g  # noqa: E402

# The SOFTDRINK 2K28 v0.5 disc's files (2026-10-06, disc sha256 5317a7b1...), for the receipt's provenance note only:
# the gates are the owned bytes, so the repair also stacks after other jobs' repairs of the same files.
V05_DISC_SHA256 = "5317a7b16558621e4030f3883789060f37a42af542df431a5d338b2ca1f3c76f"
V05_PACK0_SHA256 = "b2c48dd3a3e8c7b5e75a596f83b9f6ef64e6c7c00b613611ed5e9e88b790fd72"
V05_XBE_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
PACK0_NAME, XBE_NAME = "vc_53450030__0", "default.xbe"


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
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
                 0o644)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)
    os.replace(tmp, path)
    g.require(read(path) == data, f"{path}: read-back failed")


def scope(before: bytes, after: bytes, ranges: list[tuple[int, int]]) -> dict:
    """Bytes changed inside / outside the declared [start, end) ranges (the file size never changes)."""

    g.require(len(before) == len(after), "a file changed size")
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


def xbe_ranges(xbe: bytes) -> tuple[list[tuple[int, int]], list[dict]]:
    """File ranges of the three operands and the .text digest field in this executable."""

    from mod_editor.core.nfl2k5_bump_strength import _sections
    offset = g._xbe_offsets(xbe)
    ranges, rows = [], []
    for label, va, size in g.operand_ranges():
        at = offset(va, size)
        ranges.append((at, at + size))
        rows.append(dict(label=label, va=hex(va), file_offset=hex(at), size=size))
    for index in sorted(g._touched_sections(xbe)):
        section = _sections(xbe)[index]
        at = section.header_offset + 36
        ranges.append((at, at + 20))
        rows.append(dict(label=f"section {index} digest (derived)", file_offset=hex(at), size=20))
    return sorted(ranges), rows


def disc_offsets(disc: Path) -> dict:
    """Where pack 0 and default.xbe start inside a disc image (XDVDFS directory only; read only)."""

    sys.path.insert(0, str(ROOT / "tools"))
    import nfl_uniform_color_xiso_direct_patch as xc  # noqa: E402
    fd = os.open(disc, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        size = os.fstat(fd).st_size
        entries, _ = xc.parse_xdvdfs(fd, size)
        pack0 = xc.file_extent(fd, size, "vc_53450030/0", entries=entries)
        xbe = xc.file_extent(fd, size, "default.xbe", entries=entries)
        return dict(image=str(disc), image_size=size, pack0_offset=int(pack0.byte_offset), pack0_size=int(pack0.size),
                    xbe_offset=int(xbe.byte_offset), xbe_size=int(xbe.size))
    finally:
        os.close(fd)


def repair(pack0: bytes, xbe: bytes) -> tuple[bytes, bytes, dict]:
    states_before = dict(g.pack0_states(pack0), xbe=g.xbe_status(xbe))
    g.require("foreign" not in states_before.values(), f"unexpected input bytes: {states_before}")
    new_pack0, pack_detail = g.apply_pack0(pack0)
    new_xbe, xbe_detail = g.apply_xbe(xbe)
    pack_ranges = sorted((r["pack0_offset"], r["pack0_offset"] + r["span_size"]) for r in pack_detail["resources"])
    x_ranges, x_rows = xbe_ranges(xbe)
    receipt = dict(
        job="b77 v1", option=g.BUILD_KEY, label=g.LABEL, runtime_witnessed=False,
        states_before=states_before,
        states_after=dict(g.pack0_states(new_pack0), xbe=g.xbe_status(new_xbe)),
        upright_top_cm=dict(before=g.RETAIL_TOP, after=g.MODERN_TOP), crossbar_top_cm=g.CROSSBAR_TOP,
        files={
            PACK0_NAME: dict(size=len(pack0), before_sha256=sha(pack0), after_sha256=sha(new_pack0),
                             input_is_v05=sha(pack0) == V05_PACK0_SHA256, outer346=dict(
                                 offset=pack_detail["outer_offset"], size=pack_detail["outer_size"]),
                             resources=pack_detail["resources"], scope=scope(pack0, new_pack0, pack_ranges)),
            XBE_NAME: dict(size=len(xbe), before_sha256=sha(xbe), after_sha256=sha(new_xbe),
                           input_is_v05=sha(xbe) == V05_XBE_SHA256, sites=x_rows,
                           sections_resealed=xbe_detail.get("sections_resealed", []),
                           scope=scope(xbe, new_xbe, x_ranges)),
        },
        pins=dict(path="data/nfl2k5_modern_goalposts_pins.json", sha256=sha(g.PINS_PATH.read_bytes())),
    )
    for name in (PACK0_NAME, XBE_NAME):
        g.require(receipt["files"][name]["scope"]["identical_outside"], f"{name}: bytes changed outside the declared ranges")
    g.require(set(receipt["states_after"].values()) == {"applied"}, "the read-back is not modern")
    already = all(v == "applied" for v in states_before.values())
    receipt["status"] = "ALREADY_APPLIED" if already else "OK"
    if already:
        g.require(new_pack0 == pack0 and new_xbe == xbe, "an already-modern input changed")
    return new_pack0, new_xbe, receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pack0", type=Path, required=True, help="the disc's vc_53450030/0")
    ap.add_argument("--xbe", type=Path, required=True, help="the disc's default.xbe")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--disc", type=Path, help="optional: the disc image the inputs came from (read only), for offsets")
    args = ap.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    outs = (args.out_dir / PACK0_NAME, args.out_dir / XBE_NAME)
    for out in outs + (args.receipt,):
        g.require(out.resolve() not in (args.pack0.resolve(), args.xbe.resolve()), "an output aliases an input")
    pack0, xbe = read(args.pack0), read(args.xbe)
    new_pack0, new_xbe, receipt = repair(pack0, xbe)
    if args.disc:
        where = disc_offsets(args.disc)
        where["disc_is_v05"] = None   # hashing 6 GB is left to the integrator; the file hashes above are exact
        for name, base_key in ((PACK0_NAME, "pack0_offset"), (XBE_NAME, "xbe_offset")):
            receipt["files"][name]["disc_ranges"] = [
                [hex(where[base_key] + int(a, 16)), hex(where[base_key] + int(b, 16)), n]
                for a, b, n in receipt["files"][name]["scope"]["declared_ranges"]]
        receipt["disc"] = where
    write(outs[0], new_pack0)
    write(outs[1], new_xbe)
    args.receipt.write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": receipt["status"],
                      PACK0_NAME: receipt["files"][PACK0_NAME]["after_sha256"],
                      XBE_NAME: receipt["files"][XBE_NAME]["after_sha256"],
                      "outside_changed": [receipt["files"][n]["scope"]["bytes_changed_outside"] for n in (PACK0_NAME, XBE_NAME)]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
