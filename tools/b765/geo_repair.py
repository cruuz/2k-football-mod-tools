#!/usr/bin/env python3
"""b765 geo: refit the 15 modern facemasks on a SOFTDRINK 2K28 v0.4 pack 0 (vc_53450030/0) in place.

The v0.4 masks were authored with the old depth fit (the lower cage on the face). This rewrites only the two player
scene spans (o3c113/o3c115) and the 15 modern mask textures inside outer 3, rebuilt from the retail outer 3 with the
current ``data/nfl2k5_modern_helmets`` geometry, keeping each scene's Guardian-overlay state as v0.4 had it. Every byte
of pack 0 outside those chunks is left as it was (other jobs' roster edits included); outer 3 is located by offset and
gated by hash, not by the whole file's hash.

    geo_repair.py --pack0 IN --retail-outer3 RETAIL_OUTER3 --out OUT --receipt RECEIPT.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_helmets as mh  # noqa: E402
from mod_editor.core import nfl2k5_models as models  # noqa: E402

OUTER3_OFFSET, OUTER3_SIZE = 854016, 2387424
V04_OUTER3_SHA256 = "154908c6d7df9317599b2fbcb65e110b6183404c8d246e7c98c52e3caa2a41dc"
RETAIL_OUTER3_SHA256 = "791e66e2314630640af60d976b1053926c717fe3b27cf8c71801b4a9c279e4eb"
V04_PINS = Path(__file__).with_name("geo_v04_pins.json")


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
    mh.require(read(path) == data, f"{path}: read-back failed")


def repair_outer3(v04: bytes, retail: bytes) -> tuple[bytes, dict]:
    old_pins = json.loads(V04_PINS.read_text(encoding="utf-8"))
    document, pins = mh.load_geometry(), mh.load_pins()
    chunks_v04, chunks_retail = mh._chunks(v04), mh._chunks(retail)
    out = bytearray(v04)
    receipt: dict = {"scenes": [], "masks": [], "owned_ranges": []}
    for key in mh.KEYS:
        _outer, index = models.parse_model_key(key)
        c_v, c_r = chunks_v04[index], chunks_retail[index]
        span_v, span_r = mh._chunk_span(v04, c_v), mh._chunk_span(retail, c_r)
        mh.require(c_v.offset == c_r.offset and len(span_v) == len(span_r), f"{key}: layouts differ")
        state = mh.classify(key, mh.decode_span_bytes(span_v, span_v), old_pins)
        mh.require(state[0] in ("applied", "unchanged") and state[1] in ("retail", "guardian"),
                   f"{key}: v0.4 scene is {state}, not the v0.4 helmets")
        start = span_r if state[1] == "retail" else mh.refit(span_r, mh.guardian_lanes(key, mh.decode_span_bytes(span_r, span_r)))
        new, rec = mh.compile_scene(key, start, document, pins)
        out[c_v.offset:c_v.offset + len(new)] = new
        receipt["scenes"].append({"key": key, "v04_state": list(state), "before_sha256": sha(span_v),
                                  "after_sha256": sha(new), "compile": rec["state"]})
        receipt["owned_ranges"].append([c_v.offset, len(new)])
    for slot in mh.MODERN_MASKS:
        idx = mh.MASK_CHUNKS[slot]
        c_v, c_r = chunks_v04[idx], chunks_retail[idx]
        span_v, span_r = mh._chunk_span(v04, c_v), mh._chunk_span(retail, c_r)
        mh.require(sha(span_v) == old_pins["masks"][str(slot)]["applied"], f"mask{slot:02d}: v0.4 texture is not the v0.4 mask")
        mh.require(sha(span_r) == pins["masks"][str(slot)]["retail"], f"mask{slot:02d}: retail texture differs")
        new = mh.compile_mask_texture(mh.mask_alpha(document, slot), span_r)
        mh.require(sha(new) == pins["masks"][str(slot)]["applied"], f"mask{slot:02d}: texture differs from its pin")
        out[c_v.offset:c_v.offset + len(new)] = new
        receipt["masks"].append({"slot": slot, "before_sha256": sha(span_v), "after_sha256": sha(new)})
        receipt["owned_ranges"].append([c_v.offset, len(new)])
    mh.require(len(out) == len(v04), "outer 3 changed size")
    mh.require(mh.collection_status(bytes(out), pins) == "applied", "the helmets read-back failed")
    owned = bytearray(len(v04))
    for off, size in receipt["owned_ranges"]:
        owned[off:off + size] = b"\x01" * size
    outside = sum(1 for i in range(len(v04)) if not owned[i] and out[i] != v04[i])
    mh.require(outside == 0, f"{outside} bytes changed outside the owned chunks")
    receipt["bytes_changed_outside_owned"] = outside
    receipt["bytes_changed_inside_owned"] = sum(1 for i in range(len(v04)) if out[i] != v04[i])
    return bytes(out), receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pack0", type=Path, required=True)
    ap.add_argument("--retail-outer3", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args(argv)
    mh.require(args.out.resolve() not in (args.pack0.resolve(), args.retail_outer3.resolve()), "output aliases an input")
    pack0, retail = read(args.pack0), read(args.retail_outer3)
    mh.require(sha(retail) == RETAIL_OUTER3_SHA256, "retail outer 3 hash differs")
    v04 = pack0[OUTER3_OFFSET:OUTER3_OFFSET + OUTER3_SIZE]
    current = mh.collection_status(v04, mh.load_pins())
    if current == "applied":
        print(json.dumps({"status": "ALREADY_APPLIED", "pack0_sha256": sha(pack0)}))
        return 0
    mh.require(sha(v04) == V04_OUTER3_SHA256, "outer 3 is not the v0.4 outer 3")
    new_outer, receipt = repair_outer3(v04, retail)
    out = pack0[:OUTER3_OFFSET] + new_outer + pack0[OUTER3_OFFSET + OUTER3_SIZE:]
    mh.require(len(out) == len(pack0), "pack 0 changed size")
    write(args.out, out)
    receipt.update({"status": "OK", "pack0_before_sha256": sha(pack0), "pack0_after_sha256": sha(out),
                    "outer3_offset": OUTER3_OFFSET, "outer3_before_sha256": sha(v04),
                    "outer3_after_sha256": sha(new_outer), "geometry_sha256": mh.load_pins()["geometry_sha256"]})
    args.receipt.write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("status", "pack0_after_sha256", "bytes_changed_inside_owned",
                                              "bytes_changed_outside_owned")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
