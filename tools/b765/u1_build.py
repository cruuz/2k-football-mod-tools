#!/usr/bin/env python3
"""Merge reviewed u1 native spans or overlay the same corrections in a Studio project.

Game-derived replacement bytes and projects remain in private scratch. The
overlay preserves every unrelated base edit and records the exact target keys.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(Path(__file__).resolve().parent)]
from nfl2k5_team_2026_art import _edit_target
from u1_repair import publish_batch, replacement_bytes, refuse_links, require, sha

JERSEY_CODES = {"00", "06", "08", "09", "14", "15", "16", "24", "28", "37"}
HELMET_CODES = {"16", "24"}


def overlay(base: dict, corrections: list[dict]) -> tuple[dict, dict]:
    require(base.get("schema") == "nfl2k5_visual_mod_project/v1", "unsupported base project")
    changed = {}
    for correction in corrections:
        require(correction.get("schema") == base["schema"], "unsupported correction project")
        for edit in correction["edits"]:
            key = _edit_target(edit)
            require(key not in changed, "duplicate correction target")
            if edit["kind"] == "unif_color":
                require(edit.get("selector") in {"16H0", "16A0"}, "unowned uniform color target")
            elif edit["kind"] == "torso":
                require(edit.get("asset_code") == "16" and edit.get("side") in {"H", "A"} and
                        edit.get("variant") == 0, "unowned torso target")
            elif edit["kind"] == "live_number_nameplate":
                family = edit.get("family")
                allowed = JERSEY_CODES if family in {"jersey_digit", "arm_digit"} else HELMET_CODES if family == "helmet_digit" else set()
                require(edit.get("asset_code") in allowed and edit.get("side") in {"H", "A"} and
                        edit.get("variant") == 0 and type(edit.get("digit")) is int and
                        0 <= edit["digit"] <= 9,
                        "unowned number target")
            elif edit["kind"] == "live_helmet":
                require(edit.get("asset_code") == "18" and edit.get("side") in {"H", "A"} and
                        edit.get("variant") == 0 and edit.get("family") == "helmet02",
                        "unowned live helmet target")
            else:
                raise ValueError("unowned correction kind")
            changed[key] = edit
    seen = set()
    result = []
    for edit in base["edits"]:
        key = _edit_target(edit)
        require(key not in seen, "duplicate base target")
        seen.add(key)
        result.append(changed.get(key, edit))
    result.extend(edit for key, edit in changed.items() if key not in seen)
    preserved = [e for e in base["edits"] if _edit_target(e) not in changed]
    require(preserved == [e for e in result if _edit_target(e) not in changed], "unrelated project edits changed")
    doc = dict(base, edits=result)
    receipt = {"schema": "b765/u1/project-overlay-receipt/v1", "targets": [list(k) for k in changed],
               "preserved_edit_count": len(preserved), "unrelated_edits_identical": True,
               "preserved_edits_sha256": sha(json.dumps(preserved, sort_keys=True).encode())}
    return doc, receipt


def merge_native(paths: list[Path], out: Path) -> dict:
    resources = {}
    binaries = {}
    inputs = []
    for path in paths:
        refuse_links(path)
        doc = json.loads(path.read_text())
        require(doc.get("schema") == "b765/u1/texture-repair/v1", "unsupported native manifest")
        inputs.append({"path": str(path.resolve()), "sha256": sha(path.read_bytes())})
        for name, patches in doc["resources"].items():
            require(re.fullmatch(r"[0-9]{2}[HA][0-9]{1,2}\.IFF", name) is not None, "unowned resource type")
            for patch in patches:
                data = replacement_bytes(path.parent, patch["replacement"])
                require(len(data) == patch["length"] and sha(data) == patch["after_sha256"], "replacement pin changed")
                filename = sha(data) + ".span"
                binaries[filename] = data
                resources.setdefault(name, []).append(dict(patch, replacement=filename))
    for patches in resources.values():
        patches.sort(key=lambda p: p["offset"])
        end = 0
        for patch in patches:
            require(type(patch["offset"]) is int and type(patch["length"]) is int and
                    patch["length"] > 0 and patch["offset"] >= end, "overlapping/invalid native spans")
            end = patch["offset"] + patch["length"]
    doc = {"schema": "b765/u1/texture-repair/v1", "resources": resources, "input_manifests": inputs}
    publish_batch([(out.parent / name, data) for name, data in binaries.items()] +
                  [(out, (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode())])
    return doc


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest="command", required=True)
    s = subs.add_parser("merge-native")
    s.add_argument("--manifest", action="append", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s = subs.add_parser("overlay-project")
    s.add_argument("--base", type=Path, required=True)
    s.add_argument("--correction", action="append", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--receipt", type=Path, required=True)
    a = p.parse_args()
    if a.command == "merge-native":
        doc = merge_native(a.manifest, a.out)
        print(f"merged {len(doc['resources'])} uniform resources, {sum(map(len, doc['resources'].values()))} spans")
    else:
        doc, receipt = overlay(json.loads(a.base.read_text()), [json.loads(x.read_text()) for x in a.correction])
        data = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode()
        receipt.update(base_sha256=sha(a.base.read_bytes()), output_sha256=sha(data))
        publish_batch([(a.out, data), (a.receipt, (json.dumps(receipt, indent=2) + "\n").encode())])
        print(f"overlaid {len(receipt['targets'])} targets; preserved {receipt['preserved_edit_count']} edits")


if __name__ == "__main__":
    main()
