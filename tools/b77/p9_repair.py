#!/usr/bin/env python3
"""b77 p9: CPU decisions "Modern 2" on a SOFTDRINK 2K28 v0.5 disc's default.xbe, natively.

    p9_repair.py --xbe IN_XBE --out-dir OUT --receipt RECEIPT.json [--disc IMAGE]

IN_XBE is the disc's ``default.xbe`` (shared with other jobs). OUT receives ``default.xbe`` with only these bytes changed:

* the owner's own 2048-byte code allocation of ``nfl2k5_cpu_money_downs`` (Modern template -> Modern 2 template; same VA,
  same size, nothing else in that region of the executable is touched);
* eight sites in ``.text``: the three existing hooks ``0x20B180`` (``fourth``), ``0x20980D`` (``play``), ``0x1987B5`` (``target``)
  re-pointed at the new template, and the five new ones: the two-point chart entry ``0x206E70`` (5 bytes), the two calls of the
  field goal test ``0x20B1A4`` (dispatcher) and ``0x20B6DD`` (commit, the fake check) (5 bytes each, call targets only) and the
  two defensive lottery exponents ``0x20AA1F`` / ``0x20AC4E`` (1 byte each, ``push 3`` -> ``push 2``);
* derived seals only, recomputed from the bytes above: the ``.text`` section digest, the digests of the two scale-out sections that
  hold the owner's code and the allocator directory page, the directory page's code seal and its header copy. Every later writer of
  ``.text`` or of the allocator reseals them again.

The shotgun 10-yard rule (``0x207F85``) is NOT touched: the modern books are being fixed instead (job p48o).

The repair is a function of the owner's bytes only: the owner must already be the v0.5 Modern (or Aggressive) installation, every
dependent routine must match its pinned retail bytes and the hooks must be exactly the older three; otherwise it refuses.
Idempotent: a Modern 2 input comes back byte-identical (status ALREADY_APPLIED). The receipt carries the exact before/after SHA-256 of
the file, the declared byte ranges and a scope proof that every byte outside them is identical. With ``--disc`` (read only) it also states
where each range sits in that disc image.
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
from mod_editor.core import nfl2k5_cpu_money_downs as md  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections  # noqa: E402

# The SOFTDRINK 2K28 v0.5 disc's default.xbe (2026-10-06, disc sha256 5317a7b1...), for the receipt's provenance note only: the gates
# are the owned bytes, so the repair also stacks after other jobs' repairs of the same file.
V05_DISC_SHA256 = "5317a7b16558621e4030f3883789060f37a42af542df431a5d338b2ca1f3c76f"
V05_XBE_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
XBE_NAME = "default.xbe"
SOURCES = ROOT / "docs/mod_editor/nfl2k5_cpu_decisions_modern2_sources.json"


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
    """File ranges the repair owns in this executable: owner code, the eight .text sites, and the derived seals."""
    allocation = next(a for a in space.layout(xbe)["allocations"] if a["owner"] == md.OWNER)
    ranges, rows = [], []
    ranges.append((allocation["raw"], allocation["raw"] + allocation["size"]))
    rows.append(dict(label="owner code allocation", va=hex(allocation["va"]), file_offset=hex(allocation["raw"]), size=allocation["size"]))
    for name, va, before, _after in md.sites(allocation["va"], "modern2"):
        at = rdata.offset_of(xbe, va)
        ranges.append((at, at + len(before)))
        rows.append(dict(label=f"site {name}", va=hex(va), file_offset=hex(at), size=len(before)))
    # derived seals (recomputed here; whoever writes .text or the allocator afterwards reseals them again)
    sections = _sections(xbe)
    text = next(s for s in sections if s.virtual_address <= 0x20B180 < s.virtual_address + s.raw_size)
    derived = [("section digest of .text", text.header_offset + 36, 20)]
    regions = space._scale_regions()
    owner_region = next(i for i, r in enumerate(regions) if r["raw"] <= allocation["raw"] < r["raw"] + r["size"])
    directory_region = next(i for i, r in enumerate(regions) if r["raw"] <= space.SCALE_DIRECTORY < r["raw"] + r["size"])
    for label, index in (("descriptor digest of the section holding the owner code", owner_region),
                         ("descriptor digest of the section holding the allocator directory page", directory_region)):
        derived.append((label, space.META_START + index * 56 + 36, 20))
    derived.append(("allocator directory header copy: sha256 of the directory page", space.DIRECTORY + 20, 32))
    derived.append(("allocator directory page: sha256 seal of the scale-out code", space.SCALE_DIRECTORY + 12, 32))
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
    before = md.read_settings(xbe)
    state_before = None if before is None else before["level"]
    if md.status(xbe) == "foreign":
        raise ValueError(f"unexpected input bytes: the CPU money downs owner or a dependent routine is foreign ({md.status(xbe)})")
    new, detail = md.upgrade_to_modern2(xbe)
    ranges, rows = declared_ranges(new)
    receipt = dict(
        job="b77 p9", option="cpu_money_downs", level="modern2", label=md.BUILD_CAPTION, runtime_witnessed=False,
        state_before=state_before, state_after=md.read_settings(new)["level"],
        files={XBE_NAME: dict(size=len(xbe), before_sha256=sha(xbe), after_sha256=sha(new), input_is_v05=sha(xbe) == V05_XBE_SHA256,
                              sites=rows, edits=detail["edits"], sections_resealed=detail.get("sections_repinned", []),
                              scope=scope(xbe, new, ranges))},
        pins=dict(sources=dict(path="docs/mod_editor/nfl2k5_cpu_decisions_modern2_sources.json", sha256=sha(SOURCES.read_bytes())),
                  template_modern2_sha256=sha(md.assembly.CODE2), template_v05_sha256=sha(md.assembly.CODE),
                  guards=[[hex(va), size, digest] for va, size, digest in md.GUARDS]),
        untouched=dict(shotgun_formation_rule_0x207F85="owned by the books job (p48o); bytes and constants identical to the input"))
    if not receipt["files"][XBE_NAME]["scope"]["identical_outside"]:
        raise ValueError("bytes changed outside the declared ranges")
    already = detail.get("already_applied", False)
    receipt["status"] = "ALREADY_APPLIED" if already else "OK"
    if already and new != xbe:
        raise ValueError("an already-Modern-2 input changed")
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
