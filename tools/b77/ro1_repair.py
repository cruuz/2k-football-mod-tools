#!/usr/bin/env python3
"""Apply a dated roster refresh to a verified disc copy, or prove it virtually.

Virtual mode reads the complete input and hashes the projected complete output
without making a disc copy. Both modes use Studio's roster and optional draft
initialization writers, changing fixed spans in the existing ROST/XBE allocations.
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
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_draft_picks as picks
from mod_editor.core import nfl2k5_hback as hback
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.core import platform_compat as io

BASE_SHA = "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4"
BLOCK = 8 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def runs(before, after):
    if len(before) != len(after):
        raise ValueError("Fixed allocation growth is forbidden")
    start = None
    for i, (a, b) in enumerate(zip(before, after)):
        if a != b and start is None:
            start = i
        if a == b and start is not None:
            yield start, after[start:i]
            start = None
    if start is not None:
        yield start, after[start:]


def project_hash(path, spans):
    old, new, outside_old, outside_new = (hashlib.sha256() for _ in range(4))
    count = 0
    with path.open("rb") as handle:
        offset = 0
        while raw := handle.read(BLOCK):
            changed = bytearray(raw)
            mask = []
            for at, data in spans:
                lo, hi = max(at, offset), min(at + len(data), offset + len(raw))
                if lo < hi:
                    changed[lo-offset:hi-offset] = data[lo-at:hi-at]
                    mask.append((lo-offset, hi-offset))
            old.update(raw); new.update(changed)
            if mask:
                count += sum(a != b for a, b in zip(raw, changed))
            cursor = 0
            for lo, hi in sorted(mask):
                outside_old.update(raw[cursor:lo]); outside_new.update(changed[cursor:lo]); cursor = hi
            outside_old.update(raw[cursor:]); outside_new.update(changed[cursor:])
            offset += len(raw)
    return dict(input_sha256=old.hexdigest(), output_sha256=new.hexdigest(),
                changed_bytes=count, outside_spans_equal=outside_old.digest()==outside_new.digest(),
                outside_sha256=outside_old.hexdigest(), scanned_bytes=offset)


def write_spans(path, spans):
    """Write and read back fixed spans through a privately owned binary descriptor."""
    written = 0
    fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        for at, data in spans:
            if io.pwrite(fd, data, at) != len(data):
                raise OSError("Short repair write")
            written += len(data)
        os.fsync(fd)
        for at, data in spans:
            if io.pread(fd, len(data), at) != data:
                raise OSError("Repair readback differs")
    finally:
        os.close(fd)
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--disc", type=Path, required=True)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--virtual", action="store_true")
    ap.add_argument("--prior-receipt", type=Path, help="Accept the exact previous output for replay")
    ap.add_argument("--picks-plan", type=Path, help="Complete ownership table for new franchises")
    ap.add_argument("--hback-plan", type=Path, help="All 32 backfield role decisions")
    args = ap.parse_args()
    if args.receipt.resolve() in tuple(p.resolve() for p in (args.disc, args.plan, args.picks_plan, args.hback_plan, args.prior_receipt) if p):
        raise ValueError("Receipt must not overwrite an input")
    plan_raw = args.plan.read_bytes()
    plan = json.loads(plan_raw)
    with rr._outer_image()(args.disc) as archive:
        entry = rr._entry(archive)
        before = archive.read(entry.virtual_offset, entry.size)
        # Resolve each run through the same archive mapping used by Studio.
        fragment = dict(schema=rr.EDITS_SCHEMA, edits=[], roster_refresh=plan)
        body, studio = rr.apply_body(before[32:], fragment, scheme="one_pool")
        body, commentary = rr.repair_commentary_body(body)
        after = before[:32] + body
        spans = [(archive.image_offset(entry.virtual_offset + at), data) for at, data in runs(before, after)]
        # A seam cannot occur inside one run in the main ROST allocation.
        for at, data in runs(before, after):
            assert archive.image_offset(entry.virtual_offset+at+len(data)-1) == archive.image_offset(entry.virtual_offset+at)+len(data)-1
    picks_sha, pick_receipt = None, None
    hback_sha, hback_receipt = None, None
    xbe_before = xbe_after = None
    if args.picks_plan or args.hback_plan:
        with args.disc.open("rb") as handle:
            xbe_at, length = tt.image_xbe_extent(handle.fileno(), args.disc.stat().st_size)
            handle.seek(xbe_at)
            xbe_before = handle.read(length)
        xbe_after = xbe_before
        if args.picks_plan:
            picks_raw = args.picks_plan.read_bytes()
            picks_sha = sha(picks_raw)
            pick_plan = json.loads(picks_raw)
            xbe_after, pick_receipt = picks.apply(xbe_after, pick_plan)
            if picks.apply(xbe_after, pick_plan)[0] != xbe_after:
                raise ValueError("Draft initializer replay changed bytes")
        if args.hback_plan:
            hback_raw = args.hback_plan.read_bytes()
            hback_sha = sha(hback_raw)
            hback_plan = json.loads(hback_raw)
            xbe_after, hback_receipt = hback.apply(xbe_after, hback_plan)
            if hback.apply(xbe_after, hback_plan)[0] != xbe_after:
                raise ValueError("H-back replay changed bytes")
        spans.extend((xbe_at + at, data) for at, data in runs(xbe_before, xbe_after))
    spans.sort()
    if any(a+len(data)>b for (a,data),(b,_) in zip(spans,spans[1:])):
        raise ValueError("Overlapping repair spans")
    proof = project_hash(args.disc, spans)
    accepted = {BASE_SHA}
    if args.prior_receipt:
        previous = json.loads(args.prior_receipt.read_text(encoding="utf-8"))
        if (previous["plan_sha256"] != sha(plan_raw) or previous["input_sha256"] != BASE_SHA
                or previous.get("picks_plan_sha256") != picks_sha
                or previous.get("hback_plan_sha256") != hback_sha):
            raise ValueError("Replay receipt does not describe this plan and base")
        accepted.add(previous["output_sha256"])
    if proof["input_sha256"] not in accepted:
        raise ValueError("Unknown disc input hash; nothing written")
    repeated, _ = rr.apply_body(body, fragment, scheme="one_pool")
    repeated, _ = rr.repair_commentary_body(repeated)
    if repeated != body:
        raise ValueError("Studio refresh replay changed bytes")
    written = 0
    if not args.virtual:
        written = write_spans(args.disc, spans)
        if project_hash(args.disc, [])["input_sha256"] != proof["output_sha256"]:
            raise ValueError("Complete output hash differs")
    receipt = dict(proof, mode="virtual" if args.virtual else "in_place_copy", physical_bytes_written=written,
                   plan_sha256=sha(plan_raw), body_before_sha256=sha(before[32:]), body_after_sha256=sha(body),
                   replay_changed_bytes=0, studio_equal=True, studio=studio["roster_refresh"],
                   picks_plan_sha256=picks_sha, draft_picks=pick_receipt,
                   hback_plan_sha256=hback_sha, hback=hback_receipt,
                   xbe_before_sha256=sha(xbe_before) if xbe_before else None,
                   xbe_after_sha256=sha(xbe_after) if xbe_after else None,
                   spans=[dict(offset=at,size=len(data),sha256=sha(data)) for at,data in spans])
    args.receipt.write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps({k:v for k,v in receipt.items() if k not in ("spans", "studio")},sort_keys=True))
    print("SPAN_COUNT", len(spans))


if __name__ == "__main__":
    main()
