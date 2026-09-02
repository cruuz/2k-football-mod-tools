#!/usr/bin/env python3
"""Bake an authored formation + play into a layout-identical copy of the retail XISO.

Compiles through ``mod_editor.core.nfl2k5_formation_play_writer`` (imported, never
copied) and reuses the proven transport helpers from
``tools/nfl_uniform_color_xiso_direct_patch.py``.  Writes ``plan.json`` beside the
XISO so the runtime driver can stake guest-RAM markers.  Never touches the retail
image (hashed before and after).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import nfl_uniform_color_xiso_direct_patch as xc  # noqa: E402
from mod_editor.core import nfl2k5_formation_play_writer as writer  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core.nfl2k5_playbook_inspector import (  # noqa: E402
    FORMATION_AUX_BASE, FORMATION_AUX_SIZE, FORMATION_BASE, FORMATION_SIZE, PLAY_BASE, PLAY_SIZE,
    RESOURCE_HEADER_SIZE, parse_playbook_resource,
)

CACHE = Path.home() / ".cache/2k5-mod-studio/7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
INDEX = CACHE / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
INVENTORY = CACHE / "indexes/nfl2k5_resource_chunks_v2.json"
RETAIL_XISO = Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")
RETAIL_SHA = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
ATL = "nfl2k5.resource.o0308.c0000.k504c4159"
YD = codec.YD_CM


def default_plan() -> tuple[list, list, list]:
    pistol = [
        (0, int(-4 * YD)), (304, 0), (-304, 0), (0, 0), (152, 0), (-152, 0),
        (-457, 0), (-1371, -219), (1371, -219), (457, 0), (0, int(-7 * YD)),
    ]
    def slant(depth):
        return [[0x01, [1, 3, 0, 0.0, 0.0, 0.0]], [0x12, [0, 0, 3 * YD, 15]], [0x12, [2, 0, depth * YD, 15]]]
    assignments: list = [None] * 11
    assignments[0] = [[0x01, [1, 4, 0, 0.0, 0.0, 0.0]], [0x03, [0]], [0x04, [0, 0.0, -1 * YD, 0]], [0x06, [0, 1, 4, 2, 3, 0.0]]]
    assignments[6] = slant(8)
    assignments[9] = slant(12)
    assignments[7] = [[0x01, [1, 3, 0, 0.0, 0.0, 0.0]], [0x12, [0, 0, 5 * YD, 15]], [0x12, [5, 0, 8 * YD, 15]]]
    assignments[8] = [[0x01, [1, 3, 0, 0.0, 0.0, 0.0]], [0x12, [0, 0, 15 * YD, 15]]]
    assignments[10] = [[0x01, [1, 3, 0, 0.0, 0.0, 0.0]], [0x12, [0, 0, 4 * YD, 15]], [0x12, [4, 0, 6 * YD, 15]]]
    f = [{"asset_id": ATL, "donor_formation_index": 10, "custom_name": "Pistol Ace", "slot_positions": pistol}]
    p = [{"asset_id": ATL, "donor_play_index": 141, "custom_name": "Pistol Slants", "assignments": assignments}]
    l = [{"asset_id": ATL, "formation_index": 39, "play_index": 254}]
    return f, p, l


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--plan-json", help="JSON with formation_requests/play_requests/link_requests")
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.plan_json:
        spec = json.loads(Path(args.plan_json).read_text())
        f, p, l = spec["formation_requests"], spec["play_requests"], spec.get("link_requests", [])
    else:
        f, p, l = default_plan()
    replacement, _, report, selector, target = writer.build_unified_formation_play_import(INDEX, INVENTORY, ATL, f, p, l)
    parsed = parse_playbook_resource(replacement, asset_id=ATL)
    new_f = report["new_formation_indices"][0] if report["new_formation_indices"] else None
    new_p = report["new_play_indices"][0] if report["new_play_indices"] else None
    body = replacement[RESOURCE_HEADER_SIZE:]
    markers = {}
    if new_f is not None:
        off = FORMATION_BASE + new_f * FORMATION_SIZE
        markers["formation_record"] = body[off:off + FORMATION_SIZE].hex()
        markers["formation_record_body_offset"] = off
    if new_p is not None:
        off = PLAY_BASE + new_p * PLAY_SIZE
        markers["play_record"] = body[off:off + PLAY_SIZE].hex()
        markers["play_record_body_offset"] = off
    plan = {
        "asset_id": ATL, "selector": selector, "target": target, "report": json.loads(json.dumps(report, default=list)),
        "new_formation_index": new_f, "new_play_index": new_p,
        "formation_name": parsed.formations[new_f].name if new_f is not None else None,
        "play_name": parsed.plays[new_p].name if new_p is not None else None,
        "markers": markers,
        "replacement_sha256": hashlib.sha256(replacement).hexdigest(),
        "requests": {"formation_requests": f, "play_requests": p, "link_requests": l},
    }
    (out_dir / "replacement.bin").write_bytes(replacement)
    xiso_path = out_dir / "ESPN-NFL-2K5-play-author-ATL.xiso.iso"
    span_start = target["xiso_absolute_span_offset"]
    span_size = len(replacement)
    if xiso_path.exists():
        fd = os.open(xiso_path, os.O_RDONLY)
        try:
            got = xc.read_exact(fd, span_start, span_size)
        finally:
            os.close(fd)
        if got != replacement:
            xiso_path.unlink()
    if not xiso_path.exists():
        print(f"baking {span_size} bytes at {span_start} into {xiso_path}", flush=True)
        source_fd = os.open(RETAIL_XISO, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        owned = None
        try:
            info = os.fstat(source_fd)
            xc.require(info.st_size == xc.EXPECTED_XISO_SIZE, "retail XISO size mismatch")
            retail_span = xc.read_exact(source_fd, span_start, span_size)
            xc.require(hashlib.sha256(retail_span).hexdigest() == report["source_sha256"], "retail span mismatch")
            owned = xc.reserve_file(xiso_path)
            xc.copy_fd_exact(source_fd, owned.descriptor, info.st_size)
            os.pwrite(owned.descriptor, replacement, span_start)
            xc.require(xc.read_exact(owned.descriptor, span_start, span_size) == replacement, "readback mismatch")
            os.fsync(owned.descriptor)
        finally:
            os.close(source_fd)
            if owned is not None:
                os.close(owned.descriptor)
    plan["xiso_path"] = str(xiso_path)
    (out_dir / "plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True))
    print(json.dumps({k: plan[k] for k in ("formation_name", "play_name", "new_formation_index", "new_play_index", "xiso_path")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
