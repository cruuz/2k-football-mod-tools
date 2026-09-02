#!/usr/bin/env python3
"""Throw-distance curve editor for the ESPN NFL 2K5 retail XBE (local research tool).

What it edits
-------------
2K5 clamps every human throw to a maximum distance that is a piecewise-linear
function of the passer's *effective* arm strength (0..1).  The curves are plain
``(count, [x, y] * count)`` float tables in ``.rdata`` and are read through the
shared interpolator ``FUN_001b0ae0``; nothing else limits the ball (the launch,
``FUN_001cbdb0``, is a pure ballistic solve from the clamped target and the
flight time, with no velocity cap).

  bullet  VA 0x50bdc0  used by ComputeThrowTarget (``FUN_002da8e0``) when the
                       throw button is held past 0.5 -> bullet pass max distance
  lob     VA 0x50bd8c  same function, hold <= 0.5 -> lob max distance
  anim    VA 0x50bd58  throw-animation selector (``FUN_002d9290``): targets past
                       this distance use the heave animation

``y`` is centimetres in the file; this tool speaks yards (1 yd = 91.44 cm).
The count word is not changed and tables are never moved: a new curve must
have exactly as many points as the retail one, x strictly ascending in
[0, 1].

Outputs are xemu-only by design (same as ``nfl2k5_bump_strength``): the
affected section digest is recomputed but the RSA signature stays stale.

Modes
-----
  read        --xbe PATH | --xiso PATH
  write       --xbe-in PATH --xbe-out PATH  [--bullet SPEC] [--lob SPEC] [--anim SPEC]
  patch-xiso  --source-xiso PATH (--output-xiso PATH | --in-place) --manifest PATH
              [--bullet SPEC] [--lob SPEC] [--anim SPEC]

SPEC is ``x:y,x:y,...`` e.g. ``0:25,0.65:35,0.85:45,0.9:80,1:85`` (distance tables: x = arm 0..1,
y = yards; speed tables: x = yards, y = yd/s).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_bump_strength as bs  # noqa: E402
import nfl_uniform_color_xiso_direct_patch as xc  # noqa: E402

YD_CM = 91.44
IMAGE_BASE = 0x10000


class ThrowDistanceError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ThrowDistanceError(message)


@dataclass(frozen=True)
class Curve:
    name: str
    va: int                      # VA of the count dword; pairs follow
    retail: tuple[tuple[float, float], ...]   # (x, y) in the units below
    x_unit: str = "arm"          # "arm" (0..1 raw) or "yd" (stored as cm)
    y_unit: str = "yd"           # "yd" (stored as cm) or "yd/s" (stored as cm/s)

    @property
    def x_scale(self) -> float:
        return YD_CM if self.x_unit == "yd" else 1.0

    @property
    def count(self) -> int:
        return len(self.retail)

    @property
    def size(self) -> int:
        return 4 + 8 * self.count

    def encode(self, pairs: tuple[tuple[float, float], ...]) -> bytes:
        out = struct.pack("<I", self.count)
        for x, y in pairs:
            out += struct.pack("<ff", x * self.x_scale, y * YD_CM)
        return out

    @property
    def retail_bytes(self) -> bytes:
        return self.encode(self.retail)


CURVES: dict[str, Curve] = {
    "bullet": Curve("bullet", 0x50BDC0, ((0.0, 25), (0.65, 35), (0.85, 45), (0.95, 50), (1.0, 55))),
    "lob": Curve("lob", 0x50BD8C, ((0.0, 20), (0.5, 35), (0.65, 50), (0.85, 60), (0.95, 65), (1.0, 75))),
    "anim": Curve("anim", 0x50BD58, ((0.0, 20), (0.2, 30), (0.3, 50), (0.5, 60), (0.9, 70), (1.0, 80))),
    # speed-vs-distance tables used by FUN_002d8970: speed = hold*armfrac*(bulletspeed - lobspeed) + lobspeed.
    # Deep throws (>= 20 yd) are forced to hold 0, so lobspeed alone sets deep flight time = dist / speed.
    "lobspeed": Curve("lobspeed", 0x50BCB8, ((6, 6), (10, 12), (20, 16), (35, 18), (40, 20)), "yd", "yd/s"),
    "bulletspeed": Curve("bulletspeed", 0x50BC8C, ((4, 13), (10, 18), (15, 24), (25, 28), (35, 30)), "yd", "yd/s"),
}


def parse_spec(curve: Curve, spec: str) -> tuple[tuple[float, float], ...]:
    pairs: list[tuple[float, float]] = []
    for item in spec.split(","):
        item = item.strip()
        require(":" in item, f"{curve.name}: bad point {item!r}, want x:y")
        xs, ys = item.split(":", 1)
        x = float(xs)
        y = float(ys)
        if curve.x_unit == "arm":
            require(0.0 <= x <= 1.0, f"{curve.name}: x {x} outside 0..1")
        else:
            require(0.0 < x <= 150.0, f"{curve.name}: x {x} yd is not sane")
        require(0.0 < y <= 150.0, f"{curve.name}: {y} {curve.y_unit} is not sane")
        pairs.append((x, y))
    require(len(pairs) == curve.count,
            f"{curve.name}: retail table has {curve.count} points, spec has {len(pairs)}; "
            "tables cannot grow or shrink in place")
    for (xa, _), (xb, _) in zip(pairs, pairs[1:]):
        require(xa < xb, f"{curve.name}: x must be strictly ascending")
    return tuple(pairs)


def decode(blob: bytes, curve: Curve) -> tuple[tuple[float, float], ...]:
    count = struct.unpack_from("<I", blob, 0)[0]
    require(count == curve.count, f"{curve.name}: count word is {count}, expected {curve.count}")
    return tuple(
        (round(struct.unpack_from("<f", blob, 4 + 8 * i)[0] / curve.x_scale, 6),
         round(struct.unpack_from("<f", blob, 8 + 8 * i)[0] / YD_CM, 3))
        for i in range(count)
    )


def fmt(pairs, curve: Curve | None = None) -> str:
    yu = curve.y_unit if curve else "yd"
    xu = "yd" if curve and curve.x_unit == "yd" else ""
    return "  ".join(f"{x:g}{xu}->{y:g}{yu}" for x, y in pairs)


# ---------------------------------------------------------------- XBE side
def xbe_offset(payload: bytes, curve: Curve) -> int:
    """File offset of the curve: found by unique retail byte pattern, cross-checked
    against the section table.  If the table was already edited, fall back to the
    section-table address but insist the count word still matches."""
    sections = bs._sections(payload)
    expected = None
    for section in sections:
        if section.virtual_address <= curve.va < section.virtual_address + section.raw_size:
            expected = section.raw_offset + (curve.va - section.virtual_address)
            break
    require(expected is not None, f"{curve.name}: VA {curve.va:#x} is not in any section")
    hits = []
    start = payload.find(curve.retail_bytes)
    while start >= 0:
        hits.append(start)
        start = payload.find(curve.retail_bytes, start + 1)
    if hits:
        require(hits == [expected],
                f"{curve.name}: retail pattern at {[hex(h) for h in hits]}, section table says {expected:#x}")
    else:
        count = struct.unpack_from("<I", payload, expected)[0]
        require(count == curve.count,
                f"{curve.name}: table at {expected:#x} is neither retail nor a same-count edit")
    return expected


def read_xbe_curves(payload: bytes) -> dict[str, dict[str, object]]:
    out = {}
    for name, curve in CURVES.items():
        off = xbe_offset(payload, curve)
        blob = payload[off: off + curve.size]
        out[name] = {
            "file_offset": off,
            "va": curve.va,
            "retail": blob == curve.retail_bytes,
            "points": decode(blob, curve),
        }
    return out


def plan_edits(payload: bytes, wanted: dict[str, tuple[tuple[float, float], ...]]):
    """Return [(file_offset, before_bytes, after_bytes, curve)] for the requested curves."""
    edits = []
    for name, pairs in wanted.items():
        curve = CURVES[name]
        off = xbe_offset(payload, curve)
        before = payload[off: off + curve.size]
        after = curve.encode(pairs)
        require(before[:4] == after[:4], f"{name}: count word mismatch")
        require(before != after, f"{name}: requested curve equals the current one")
        edits.append((off, before, after, curve))
    return edits


def apply_to_xbe_bytes(payload: bytes, wanted) -> tuple[bytes, list[dict[str, object]]]:
    buf = bytearray(payload)
    edits = plan_edits(payload, wanted)
    records = []
    touched_sections = set()
    sections = bs._sections(payload)
    for off, before, after, curve in edits:
        buf[off: off + len(after)] = after
        section = bs._section_for_offset(sections, off)
        touched_sections.add(section.index)
        records.append({
            "curve": curve.name, "va": curve.va, "file_offset": off,
            "before_hex": before.hex(), "after_hex": after.hex(),
            "before": decode(before, curve), "after": decode(after, curve),
        })
    digest_records = []
    for section in sections:
        if section.index not in touched_sections:
            continue
        digest_off = section.header_offset + 36
        old = bytes(buf[digest_off: digest_off + 20])
        new = bs.section_digest(bytes(buf), section)
        buf[digest_off: digest_off + 20] = new
        digest_records.append({"section_index": section.index, "digest_offset": digest_off,
                               "before_hex": old.hex(), "after_hex": new.hex()})
    return bytes(buf), records + [{"section_digests": digest_records}]


def write_xbe(source: Path, target: Path, wanted, overwrite: bool) -> dict[str, object]:
    source = source.expanduser().resolve(strict=True)
    info = source.lstat()
    require(stat.S_ISREG(info.st_mode) and not source.is_symlink(), "source must be a regular file")
    target = target.expanduser()
    require(not target.exists() or overwrite, f"target exists; pass --overwrite: {target}")
    require(target.resolve() != source, "target must be a copy, not the source")
    payload = source.read_bytes()
    patched, records = apply_to_xbe_bytes(payload, wanted)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o644)
    try:
        os.write(fd, patched)
    finally:
        os.close(fd)
    # verify
    check = read_xbe_curves(target.read_bytes())
    return {"source_sha256": hashlib.sha256(payload).hexdigest(),
            "target_sha256": hashlib.sha256(patched).hexdigest(),
            "edits": records, "verified": {k: v["points"] for k, v in check.items()}}


# ---------------------------------------------------------------- XISO side
def xiso_default_xbe(fd: int, size: int) -> xc.XdvdfsEntry:
    entries, _directory = xc.parse_xdvdfs(fd, size)
    xbe = entries.get("default.xbe")
    require(xbe is not None, "XISO has no default.xbe")
    require(xbe.size == xc.EXPECTED_XBE_SIZE, f"default.xbe size {xbe.size} != retail {xc.EXPECTED_XBE_SIZE}")
    return xbe


def read_xiso(path: Path) -> dict[str, object]:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        size = os.fstat(fd).st_size
        xbe = xiso_default_xbe(fd, size)
        payload = xc.read_exact(fd, xbe.byte_offset, xbe.size)
    finally:
        os.close(fd)
    return {"xbe_byte_offset": xbe.byte_offset, "xbe_sha256": hashlib.sha256(payload).hexdigest(),
            "xbe_retail": hashlib.sha256(payload).hexdigest() == bs.RETAIL_XBE_SHA256,
            "curves": read_xbe_curves(payload)}


def patch_xiso(source: Path, output: Path | None, in_place: bool, manifest: Path, wanted) -> dict[str, object]:
    source = source.expanduser()
    require(not source.is_symlink(), "source must not be a symlink")
    source = source.resolve(strict=True)
    require(manifest.expanduser().resolve() != source, "manifest must not be the source")
    require(not manifest.exists(), f"manifest exists: {manifest}")
    if in_place:
        require(output is None, "--in-place and --output-xiso are exclusive")
        target = source
    else:
        require(output is not None, "need --output-xiso or --in-place")
        output = output.expanduser()
        require(not output.exists(), f"output exists: {output}")
        require(output.resolve() != source, "output must differ from source")
        t0 = time.time()
        shutil.copyfile(source, output)
        print(f"copied {source.stat().st_size} bytes in {time.time() - t0:.0f}s", file=sys.stderr)
        target = output.resolve()
    fd = os.open(target, os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        size = os.fstat(fd).st_size
        xbe = xiso_default_xbe(fd, size)
        payload = xc.read_exact(fd, xbe.byte_offset, xbe.size)
        before_sha = hashlib.sha256(payload).hexdigest()
        patched, records = apply_to_xbe_bytes(payload, wanted)
        # write only the changed byte ranges
        ranges = []
        i = 0
        while i < len(payload):
            if payload[i] != patched[i]:
                j = i
                while j < len(payload) and payload[j] != patched[j]:
                    j += 1
                ranges.append((i, j))
                i = j
            else:
                i += 1
        for a, b in ranges:
            xc.pwrite(fd, patched[a:b], xbe.byte_offset + a)
        os.fsync(fd)
        after = xc.read_exact(fd, xbe.byte_offset, xbe.size)
        require(after == patched, "read-back after patch does not match")
        check = read_xbe_curves(after)
    finally:
        os.close(fd)
    result = {
        "schema": "nfl2k5_throw_distance/v1",
        "source": str(source), "target": str(target), "in_place": in_place,
        "xbe_byte_offset": xbe.byte_offset,
        "xbe_sha256_before": before_sha, "xbe_sha256_after": hashlib.sha256(patched).hexdigest(),
        "written_ranges": [{"xbe_offset": a, "iso_offset": xbe.byte_offset + a, "length": b - a} for a, b in ranges],
        "edits": records,
        "verified": {k: v["points"] for k, v in check.items()},
    }
    manifest.write_text(json.dumps(result, indent=1, default=str))
    return result


# ---------------------------------------------------------------- CLI
def wanted_from_args(args) -> dict[str, tuple[tuple[float, float], ...]]:
    wanted = {}
    for name in CURVES:
        spec = getattr(args, name, None)
        if spec:
            wanted[name] = parse_spec(CURVES[name], spec)
    require(bool(wanted), "no curve changes requested (--bullet/--lob/--anim)")
    return wanted


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    r = sub.add_parser("read")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--xbe")
    g.add_argument("--xiso")
    w = sub.add_parser("write")
    w.add_argument("--xbe-in", required=True)
    w.add_argument("--xbe-out", required=True)
    w.add_argument("--overwrite", action="store_true")
    p = sub.add_parser("patch-xiso")
    p.add_argument("--source-xiso", required=True)
    p.add_argument("--output-xiso")
    p.add_argument("--in-place", action="store_true")
    p.add_argument("--manifest", required=True)
    for parser in (w, p):
        for name in CURVES:
            parser.add_argument(f"--{name}", help=f"{name} curve spec x:y,... ({CURVES[name].count} points; x in {CURVES[name].x_unit}, y in {CURVES[name].y_unit})")
    args = ap.parse_args()
    try:
        if args.mode == "read":
            if args.xbe:
                out = read_xbe_curves(Path(args.xbe).read_bytes())
                for name, rec in out.items():
                    print(f"{name:11s} @file {rec['file_offset']:#x} {'RETAIL' if rec['retail'] else 'EDITED'}: {fmt(rec['points'], CURVES[name])}")
            else:
                out = read_xiso(Path(args.xiso))
                print(f"default.xbe at ISO offset {out['xbe_byte_offset']:#x}, {'retail' if out['xbe_retail'] else 'NON-retail'} sha {out['xbe_sha256'][:16]}")
                for name, rec in out["curves"].items():
                    print(f"{name:11s} @xbe {rec['file_offset']:#x} (iso {out['xbe_byte_offset'] + rec['file_offset']:#x}) {'RETAIL' if rec['retail'] else 'EDITED'}: {fmt(rec['points'], CURVES[name])}")
        elif args.mode == "write":
            res = write_xbe(Path(args.xbe_in), Path(args.xbe_out), wanted_from_args(args), args.overwrite)
            print(json.dumps(res, indent=1, default=str))
        else:
            res = patch_xiso(Path(args.source_xiso), Path(args.output_xiso) if args.output_xiso else None,
                             args.in_place, Path(args.manifest), wanted_from_args(args))
            print(json.dumps({k: v for k, v in res.items() if k != "edits"}, indent=1, default=str))
    except (ThrowDistanceError, bs.BumpStrengthError, xc.PatchError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
