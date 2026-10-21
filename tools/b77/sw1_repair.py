#!/usr/bin/env python3
"""sw1 (b777): the sleeve swoosh layer (``data/nfl2k5_kit_fixes_2026_sw1.json``) on the b776 base disc.

  sw1_repair.py --audit --disc BASE.iso --receipts DIR    read-only: Studio writer on a compact native pack fixture of
                                                          the real kit packages, zero-byte replay, Studio equality,
                                                          and a full streamed scope of the base with the planned
                                                          spans overlaid (no disc is copied or written)
  sw1_repair.py --disc COPY.iso --receipts DIR            patch a disposable copy (the exact base, or this layer's
                                                          exact output, which is a no-op)

Unknown inputs are refused before a writable descriptor is opened. Only vector data and hashes are in the repository;
the swoosh pixels the layer moves are the kits' own, read from the disc at build time.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import numpy as np  # noqa: E402
from mod_editor.core import nfl2k5_bump_texture_writer as bump  # noqa: E402
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402
from tools.b77 import ov1_repair as ov1  # noqa: E402
from tools.b77 import uf3_repair as transport  # noqa: E402

BASE_SHA256 = "5d4ab13054823d6e0995bb2f6a5c4cdc16a2aec76f7cb534097ff82cb1029cfd"   # b776 test disc (2026-10-19)
DISC_SIZE = 6069813248                                   # b776 (the Anniversary kits appended)


def require(ok, message):
    if not ok:
        raise ValueError("sw1: " + message)


def full_scope(disc, ranges, before, after, *, virtual):
    """ov1's full-disc stream, against the b776 base."""
    import hashlib
    h_before, h_after = hashlib.sha256(), hashlib.sha256()
    changed = outside = total = 0
    pieces, pos = [], 0
    for row in ranges:
        n = row["end"] - row["start"]
        pieces.append((row["start"], row["end"], before[pos:pos + n], after[pos:pos + n]))
        pos += n
    with os.fdopen(transport.binary(disc, os.O_RDONLY), "rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            old, new = bytearray(block), bytearray(block)
            owned = np.zeros(len(block), bool)
            end = total + len(block)
            for start, stop, b, a in pieces:
                lo, hi = max(total, start), min(end, stop)
                if lo >= hi:
                    continue
                owned[lo - total:hi - total] = True
                old[lo - total:hi - total] = b[lo - start:hi - start]
                if virtual:
                    new[lo - total:hi - total] = a[lo - start:hi - start]
            diff = np.frombuffer(old, np.uint8) != np.frombuffer(new, np.uint8)
            changed += int(diff.sum())
            outside += int((diff & ~owned).sum())
            h_before.update(old)
            h_after.update(new)
            total = end
    require(total == DISC_SIZE and h_before.hexdigest() == BASE_SHA256, "full-scope reconstructed base differs")
    require(outside == 0, "bytes changed outside owned spans")
    return dict(mode="virtual_after_stream" if virtual else "written_disc", compared_bytes=total,
                changed_bytes=changed, changed_bytes_outside_spans=outside,
                reconstructed_base_sha256=h_before.hexdigest(), output_sha256=h_after.hexdigest())


def compile_plans(raws, doc, donors):
    """Every owned kit compiled by the Studio compiler (the donor kit's sleeve read as the swoosh source)."""
    out, receipts = {}, []
    for sel, raw in sorted(raws.items()):
        parts, receipt = fixes.compile_resource(sel, raw, document=doc, kits=donors)
        buf = bytearray(raw)
        for at, data in parts:
            buf[at:at + len(data)] = data
        out[sel] = bytes(buf)
        receipts.append(receipt)
    return out, receipts


def run(disc, receipts, audit=False):
    require(not disc.is_symlink(), "disc is a symlink")
    require(disc.is_file() and disc.stat().st_size == DISC_SIZE, "unexpected disc size")
    doc = fixes.swooshes()
    digest = transport.file_sha(disc)
    require(digest in {BASE_SHA256, doc.get("output_disc_sha256")}, "unknown whole-disc hash")
    require(not audit or digest == BASE_SHA256, "audit requires the base disc")
    donors = {}
    raws, ranges, extents = transport.read_resources(disc, doc, donors)
    require(set(donors) == set(fixes.donor_kits(doc)), "the swoosh donor kit is absent")
    require(not set(donors) & set(raws), "a donor kit is also repaired")
    require(not transport.alias_check(ranges, extents), "another archive entry aliases an owned span")
    require({r["chunk"] for r in ranges} <= {1, 3}, "unexpected ownership (only torso and sleeve textures)")
    compiled, plans = compile_plans(raws, doc, donors)
    states = {p["state"] for p in plans}
    require(states == {"applied"}, "a kit did not compile")
    before = b"".join(raws[r["selector"]][r["resource_offset"]:r["resource_offset"] + r["end"] - r["start"]]
                      for r in ranges)
    after = b"".join(compiled[r["selector"]][r["resource_offset"]:r["resource_offset"] + r["end"] - r["start"]]
                     for r in ranges)
    receipts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sw1-packs-", dir=receipts) as tmp:
        fixture = Path(tmp)
        ov1.compact_fixture(fixture, dict(raws, **donors))
        original = (fixture / "1").read_bytes()
        wrote = fixes.apply_swooshes(fixture, strict=digest == BASE_SHA256)
        fixed = (fixture / "1").read_bytes()
        replay = fixes.apply_swooshes(fixture, strict=True)
        require(replay["written_bytes"] == replay["changed_bytes"] == 0, "fixture replay changed bytes")
        equal = []
        with bump._Image.open(fixture, writable=False) as im:
            ix = bump._parsed_index(im)
            for e in ix.entries:
                sel = bump.logical_name_for(e.name_id)[:-4]
                actual = im.read_segments(ix.sub_extents(e, 0, e.size))
                require(actual == compiled.get(sel, donors.get(sel)), sel + ": Studio writer differs from the native compile")
                equal.append(sel)
        owned = np.zeros(len(original), bool)
        at = 0
        for sel, raw in sorted(dict(raws, **donors).items()):
            for row in doc["textures"]:
                if row["selector"] == sel:
                    owned[at + row["offset"]:at + row["offset"] + row["length"]] = True
            at += (len(raw) + 2047) // 2048 * 2048
        diff = np.frombuffer(original, np.uint8) != np.frombuffer(fixed, np.uint8)
        require(not (diff & ~owned).any(), "compact fixture changed bytes outside spans")
        fixture_scope = dict(compared_bytes=len(original), changed_bytes=int(diff.sum()),
                             changed_bytes_outside_spans=int((diff & ~owned).sum()))
    transport.write_json(receipts / "studio_write.json", wrote)
    transport.write_json(receipts / "studio_replay.json", replay)
    transport.write_json(receipts / "studio_scope.json", fixture_scope)
    transport.write_json(receipts / "studio_equality.json", dict(equal=True, selectors=equal,
                         compiler="nfl2k5_kit_fixes_2026.compile_resource", writer="apply_swooshes(strict=True)"))
    disc_written_bytes = 0
    if not audit and before != after:
        with os.fdopen(transport.binary(disc, os.O_RDWR), "r+b") as stream:
            pos = 0
            for r in ranges:
                n = r["end"] - r["start"]
                if before[pos:pos + n] != after[pos:pos + n]:
                    stream.seek(r["start"])
                    stream.write(after[pos:pos + n])
                    disc_written_bytes += n
                pos += n
            stream.flush()
            os.fsync(stream.fileno())
        require(transport.read_spans(disc, ranges) == after, "disc read-back differs")
    if digest != BASE_SHA256:
        require(before == after, "pinned output was not a no-op")
        scope = dict(mode="pinned_output_replay", compared_bytes=DISC_SIZE, output_sha256=digest, changed_bytes=0)
    else:
        scope = full_scope(disc, ranges, before, after, virtual=audit)
    if doc.get("output_disc_sha256"):
        require(scope["output_sha256"] == doc["output_disc_sha256"], "whole-disc output differs from its pin")
    transport.write_json(receipts / "disc_scope.json", scope)
    transport.write_json(receipts / "ranges.json", ranges)
    summary = dict(mode="audit_no_disc_write" if audit else "disc_write", disc_written=bool(disc_written_bytes),
                   disc_written_bytes=disc_written_bytes, kits=len(raws), textures=len(doc["textures"]),
                   fixture_written_spans=wrote["written_spans"], fixture_written_bytes=wrote["written_bytes"],
                   fixture_changed_bytes=wrote["changed_bytes"], fixture_replay_bytes=replay["written_bytes"],
                   studio_equal=True, disc_stream_compared_bytes=scope["compared_bytes"],
                   disc_changed_bytes=scope["changed_bytes"],
                   disc_changed_outside_spans=scope.get("changed_bytes_outside_spans", 0),
                   output_sha256=scope["output_sha256"], alias_count=0)
    transport.write_json(receipts / "summary.json", summary)
    print(json.dumps(summary, sort_keys=True))
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--disc", type=Path, required=True)
    p.add_argument("--receipts", type=Path, required=True)
    p.add_argument("--audit", action="store_true")
    a = p.parse_args()
    try:
        run(a.disc, a.receipts, a.audit)
    except (ValueError, OSError) as exc:
        p.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
