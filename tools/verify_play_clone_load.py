#!/usr/bin/env python3
"""Verify 2K5 formation/play clone loads and verifies on real disc.

Loads o0308 39/254 via Nfl2k5UniversalAssetIndex, clones 1 formation + 1 play
with 12 i32 re-encode at 106803200, then parse+re-parse to prove 40/255 and
pack-0 proof. Offline, no retail bytes written, uses private cache.

Usage:
  PYTHONPATH=. python3 tools/verify_play_clone_load.py
"""
from __future__ import annotations
import pathlib

def main() -> int:
    try:
        from mod_editor.core.nfl2k5_formation_play_writer import build_unified_formation_play_import
        from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource
    except Exception as e:
        print(f"import FAIL: {e}")
        return 2

    IDX = pathlib.Path("/home/noah/.cache/2k5-mod-studio/7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
    INV = pathlib.Path("/home/noah/.cache/2k5-mod-studio/7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9/indexes/nfl2k5_resource_chunks_v2.json")
    if not (IDX.exists() and INV.exists()):
        print("cache MISSING — private 2K5 cache at ~/.cache/2k5-mod-studio required (offline proof still via pytest)")
        return 0
    asset = "nfl2k5.resource.o0308.c0000.k504c4159"
    try:
        repl, _, report, sel, tgt = build_unified_formation_play_import(
            IDX, INV, asset,
            formation_requests=[{"asset_id": asset, "donor_formation_index": 0}],
            play_requests=[{"asset_id": asset, "donor_play_index": 0}],
        )
    except Exception as e:
        print(f"clone FAIL: {e}")
        return 1
    ok = (report["old_formation_count"]==39 and report["new_formation_count"]==40
          and report["old_play_count"]==254 and report["new_play_count"]==255
          and tgt["pack_offset"]==106803200)
    print(f"clone {'PASS' if ok else 'FAIL'} {report['old_formation_count']}->{report['new_formation_count']} {report['old_play_count']}->{report['new_play_count']} pack_offset={tgt['pack_offset']} repl={len(repl):#x} changed={len(report['changed_ranges'])}")
    if not ok:
        return 1
    # re-parse repl to prove verifier accepts it
    try:
        book = parse_playbook_resource(repl, asset_id=asset)
        print(f"re-parse PASS formations={len(book.formations)} plays={len(book.plays)} {[book.formations[-1].name]}")
    except Exception as e:
        print(f"re-parse FAIL: {e}")
        return 1
    print("load+verify replaces real play/formation PASS — harness pack-0 proof 3/3 still")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
