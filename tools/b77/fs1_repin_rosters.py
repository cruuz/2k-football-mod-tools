#!/usr/bin/env python3
"""fs1: re-pin the 35 retail-moment rosters after the heads (appearance.json) changed.

The pins live in two places: data/nfl2k5_espn25_moment_rosters/manifest.json (per resource ``applied_sha256`` and the
file digest ``appearance_sha256``), and nfl2k5_espn25_rosters.py (DATASET_SHA256 and the second hash of every
ONE_POOL_PINS pair, the One-pool reclassify of the applied resource). Both are recomputed from the user's retail game
with the module's own compile (no pin is read), then written.

  python3 tools/b77/fs1_repin_rosters.py --retail "ESPN NFL 2K5 (USA).xiso.iso" [--write]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_espn25_rosters as e  # noqa: E402
from mod_editor.core import nfl2k5_moment_scans as ms  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
import nfl2k5_roster_reclassify as rc  # noqa: E402

MODULE = ROOT / "mod_editor/core/nfl2k5_espn25_rosters.py"
MANIFEST = e.DATA_DIR / "manifest.json"


def reclassified(outer, raw):
    resource = rc.parse_resource(outer, 0, raw)
    moves, _ = rc.plan_resource(resource, {})
    body = bytearray(resource.body)
    rc.apply_moves(body, moves)
    return raw[:32] + bytes(body)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--retail", type=Path, required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    raw_manifest = MANIFEST.read_bytes()
    manifest = json.loads(raw_manifest)
    manifest["appearance_sha256"] = e.sha(e.APPEARANCE_JSON.read_bytes())
    doc = json.loads(e.APPEARANCE_JSON.read_text(encoding="utf-8"))
    slot_scans = ms.slots()
    with rr._outer_image()(a.retail) as archive:
        retail = {t["outer"]: archive.read_entry(t["outer"]) for t in manifest["resources"]}
    pins = {}
    changed = 0
    for t in manifest["resources"]:
        raw = retail[t["outer"]]
        require_retail = e.sha(e.without_edge_placeholders(raw)) == t["retail_sha256"]
        assert require_retail, f"{t['filename']}: not the pinned retail resource"
        rows = e.parse_csv((e.DATA_DIR / t["csv"]).read_text(encoding="utf-8"))
        looks = doc["files"][t["filename"]]
        applied = e.compile_resource(e.without_edge_placeholders(raw), rows, manifest["colleges"], layout="retail",
                                     source_colleges=manifest["colleges"], looks=looks, slot_scans=slot_scans)
        one_base = reclassified(t["outer"], raw)
        one_applied = reclassified(t["outer"], applied)
        pins[t["outer"]] = (e.sha(one_base), e.sha(one_applied))
        if e.sha(applied) != t["applied_sha256"]:
            changed += 1
        t["applied_sha256"] = e.sha(applied)
    new_manifest = (json.dumps(manifest, indent=2, ensure_ascii=True) + "\n").encode()
    print("resources whose applied bytes changed:", changed, "of", len(manifest["resources"]))
    print("manifest sha256", e.sha(new_manifest))
    # the module constants
    source = MODULE.read_text(encoding="utf-8")
    source = re.sub(r'DATASET_SHA256 = "[0-9a-f]{64}"', f'DATASET_SHA256 = "{e.sha(new_manifest)}"', source)

    def pin(m):
        outer = int(m.group(1))
        old = e.ONE_POOL_PINS[outer]
        assert old[0] == pins[outer][0], f"{outer}: the reclassified retail pin differs"
        return f'    {outer}: ("{pins[outer][0]}",\n          "{pins[outer][1]}"),'
    source = re.sub(r'    (\d+): \("([0-9a-f]{64})",\s*"([0-9a-f]{64})"\),', pin, source)
    if a.write:
        MANIFEST.write_bytes(new_manifest)
        MODULE.write_text(source, encoding="utf-8", newline="\n")
        print("written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
