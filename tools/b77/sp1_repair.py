#!/usr/bin/env python3
"""Pinned sp1 ordinary-tap repair. Disc writes require an existing base copy.

xbe --input XBE --output NEW_XBE --receipt JSON
disc --disc COPIED_ISO --receipt JSON
scope --before BASE_ISO --after COPIED_ISO --receipt JSON
Only the 52-byte initializer span and its derived .text SHA-1 may change.
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
from mod_editor.core import nfl2k5_tap_burst as burst
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import xdvdfs_compact as xd
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest

BASE_DISC_SHA256 = "d735215760ff08bceeff2a3860baccf0a84885422a4205e966154e948812103e"
BASE_XBE_SHA256 = "ffc5a33c99819d83017d75b2e4173d988328870834fd465ce67af0674d9b4118"
DISC_SIZE, XBE_SIZE, XBE_OFFSET = 6004408320, 12300288, 2398208
SCOPE = ((0x394, 0x3A8, "derived .text SHA-1"),
         (0x2FEDF1, 0x2FEE25, "ordinary burst initializer"))


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def open_binary(path, writable=False, new=False):
    flags = os.O_RDWR if writable else os.O_RDONLY
    if new:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0), 0o644)
    return os.fdopen(fd, "wb" if new else "r+b" if writable else "rb")


def canonical_xbe(raw):
    require(len(raw) == XBE_SIZE, "unexpected XBE size")
    require(burst.status(raw) in ("retail", "applied"), "foreign burst code or dependencies")
    buf = bytearray(raw)
    buf[0x2FEDF1:0x2FEE25] = burst.BEFORE
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(sha(result) == BASE_XBE_SHA256, "unknown complete input XBE hash")
    return result


def repair_xbe(raw):
    canonical_xbe(raw)
    fixed, detail = burst.apply(raw)
    studio, _ = abilities.apply(raw)
    require(studio == fixed, "native output differs from Studio abilities output")
    require(space.status(fixed) == "applied", "invalid output seals")
    changes = [i for i, (a, b) in enumerate(zip(raw, fixed)) if a != b]
    require(all(any(lo <= i < hi for lo, hi, _ in SCOPE) for i in changes), "outside-scope XBE change")
    require(burst.apply(fixed)[0] == fixed and abilities.apply(fixed)[0] == fixed, "non-idempotent output")
    return fixed, dict(schema="b772/sp1-repair/v1", status="repaired" if changes else "already_repaired",
                       before_sha256=sha(raw), after_sha256=sha(fixed), size=len(raw),
                       changed_bytes=len(changes), changed_offsets=[hex(i) for i in changes],
                       scope=[dict(start=lo, end_exclusive=hi, purpose=why) for lo, hi, why in SCOPE],
                       outside_scope_changed_bytes=0, studio_equal=True, replay_equal=True,
                       abilities_settings=abilities.read_settings(fixed), initializer=detail)


def digest_disc(stream, replacements=()):
    stream.seek(0)
    digest = hashlib.sha256()
    at = 0
    while block := stream.read(8 << 20):
        for lo, value in replacements:
            hi = lo + len(value)
            if hi <= at or lo >= at + len(block):
                continue
            start, end = max(lo, at), min(hi, at + len(block))
            block = block[:start - at] + value[start - lo:end - lo] + block[end - at:]
        digest.update(block)
        at += len(block)
    require(at == DISC_SIZE, "unexpected disc size")
    return digest.hexdigest()


def disc_xbe(stream):
    layout = xd.read_layout(stream)
    entry = layout.entries["default.xbe"]
    require((entry.byte_offset, entry.size) == (XBE_OFFSET, XBE_SIZE), "unexpected XBE disc extent")
    stream.seek(XBE_OFFSET)
    return stream.read(XBE_SIZE)


def repair_disc(path):
    with open_binary(path, writable=True) as stream:
        raw = disc_xbe(stream)
        baseline = canonical_xbe(raw)
        fixed, receipt = repair_xbe(raw)
        replacements = [(XBE_OFFSET + lo, baseline[lo:hi]) for lo, hi, _ in SCOPE]
        require(digest_disc(stream, replacements) == BASE_DISC_SHA256, "unknown complete input disc hash")
        before = digest_disc(stream)
        written = 0
        for lo, hi, _ in SCOPE:
            if raw[lo:hi] == fixed[lo:hi]:
                continue
            stream.seek(XBE_OFFSET + lo)
            require(stream.write(fixed[lo:hi]) == hi - lo, "short fixed-span write")
            written += hi - lo
        stream.flush()
        os.fsync(stream.fileno())
        require(disc_xbe(stream) == fixed, "disc readback mismatch")
        require(digest_disc(stream, replacements) == BASE_DISC_SHA256, "outside-scope disc change after write")
        receipt.update(disc_before_sha256=before, disc_after_sha256=digest_disc(stream),
                       bytes_written=written, disc_size=DISC_SIZE, xbe_offset=XBE_OFFSET,
                       disc_canonical_base_sha256=BASE_DISC_SHA256)
        return receipt


def compare_discs(before, after):
    require(before.resolve() != after.resolve(), "scope comparison requires separate files")
    spans = [(XBE_OFFSET + lo, XBE_OFFSET + hi) for lo, hi, _ in SCOPE]
    changed = at = 0
    ah, bh = hashlib.sha256(), hashlib.sha256()
    with open_binary(before) as a, open_binary(after) as b:
        old_layout, new_layout = xd.read_layout(a), xd.read_layout(b)
        geometry = lambda layout: {k: (e.byte_offset, e.size, e.attributes) for k, e in layout.entries.items()}
        require(geometry(old_layout) == geometry(new_layout), "disc layout changed")
        a.seek(0); b.seek(0)
        while old := a.read(8 << 20):
            new = b.read(len(old))
            require(len(new) == len(old), "disc length changed")
            ah.update(old); bh.update(new)
            cursor = 0
            for lo, hi in spans:
                if hi <= at or lo >= at + len(old):
                    continue
                start, end = max(0, lo - at), min(len(old), hi - at)
                require(old[cursor:start] == new[cursor:start], f"outside scope near {at + cursor:#x}")
                changed += sum(x != y for x, y in zip(old[start:end], new[start:end]))
                cursor = end
            require(old[cursor:] == new[cursor:], f"outside scope near {at + cursor:#x}")
            at += len(old)
        require(not b.read(1) and at == DISC_SIZE, "unexpected disc size")
    require(ah.hexdigest() == BASE_DISC_SHA256, "comparison source is not the pinned base disc")
    return dict(schema="b772/sp1-disc-scope/v1", size=at, before_sha256=ah.hexdigest(),
                after_sha256=bh.hexdigest(), changed_bytes=changed, outside_scope_changed_bytes=0,
                layout_equal=True, scope=spans)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    x = sub.add_parser("xbe")
    x.add_argument("--input", type=Path, required=True)
    x.add_argument("--output", type=Path, required=True)
    d = sub.add_parser("disc")
    d.add_argument("--disc", type=Path, required=True)
    c = sub.add_parser("scope")
    c.add_argument("--before", type=Path, required=True)
    c.add_argument("--after", type=Path, required=True)
    for parser in (x, d, c):
        parser.add_argument("--receipt", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        data_paths = [v.resolve() for k, v in vars(args).items() if isinstance(v, Path) and k != "receipt"]
        require(args.receipt.resolve() not in data_paths and not args.receipt.exists(), "receipt must be new and separate")
        if args.command == "xbe":
            require(args.input.resolve() != args.output.resolve(), "XBE output must be a separate file")
            with open_binary(args.input) as stream:
                raw = stream.read(XBE_SIZE + 1)
            fixed, receipt = repair_xbe(raw)
            if args.output.exists():
                with open_binary(args.output) as stream:
                    require(stream.read(XBE_SIZE + 1) == fixed, "refusing to replace a different XBE")
            else:
                with open_binary(args.output, new=True) as stream:
                    stream.write(fixed)
        elif args.command == "disc":
            receipt = repair_disc(args.disc)
        else:
            receipt = compare_discs(args.before, args.after)
        with args.receipt.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt, stream, indent=2); stream.write("\n")
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
