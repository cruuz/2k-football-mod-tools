#!/usr/bin/env python3
"""b77 / a1x: keep the Anniversary moment manifests in step with the spec and the team CSVs after a data change.

Two jobs edit the authored moment data without running the generator (it needs the nflverse downloads):
  * a2 handedness: the `hand` cells of data/nfl2k5_espn25_more_teams/*.csv and the spec's `handedness` block;
  * a3 uniforms: the `kits` of tools/nfl2k5_espn25_more_moments_spec.json and data/nfl2k5_espn25_more_moments.json.
This tool recomputes only what those edits change in the manifests, with the generator's own serializer:
  * data/nfl2k5_espn25_more_teams/manifest.json: spec_sha256, each team's csv_sha256, and the `hand_basis` of every
    player whose hand the spec's `handedness` block sources;
  * data/nfl2k5_espn25_unc_bowl.json: the csv_sha256 and hand_basis of its two teams, and the embedded moment's kits.
Idempotent. `python3 tools/b77/data_sync.py [--root DIR] [--check]` (check: exit 1 when a file would change).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

SPEC = "tools/nfl2k5_espn25_more_moments_spec.json"
TEAMS_DIR = "data/nfl2k5_espn25_more_teams"
MANIFEST = f"{TEAMS_DIR}/manifest.json"
UNC_BOWL = "data/nfl2k5_espn25_unc_bowl.json"
SOURCED = "sourced (b77 a2 handedness)"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sync(root):
    """{path: new text} for the manifest files that are out of step (empty when in step)."""
    from nfl2k5_espn25_more_moments_build import compact_json
    root = Path(root)
    spec_raw = (root / SPEC).read_bytes()
    spec = json.loads(spec_raw)
    answers = spec.get("handedness", {}).get("answers", {})
    out = {}

    def update_teams(teams):
        for key, team in teams.items():
            raw = (root / TEAMS_DIR / f"{key}.csv").read_bytes()
            team["csv_sha256"] = sha(raw)
            rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
            for player in team["players"]:
                row = rows[player["index"]]
                if f"{row['first']} {row['last']}|{row['position']}" in answers:
                    player["hand_basis"] = SOURCED

    path = root / MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["spec_sha256"] = sha(spec_raw)
    update_teams(manifest["teams"])
    text = compact_json(manifest) + "\n"
    if text != path.read_text(encoding="utf-8"):
        out[path] = text

    path = root / UNC_BOWL
    unc = json.loads(path.read_text(encoding="utf-8"))
    update_teams(unc["teams"])
    by_id = {m["id"]: m for m in spec["moments"]}
    for moment in unc["spec"]["moments"]:
        if moment["id"] in by_id:
            moment["kits"] = by_id[moment["id"]]["kits"]
    text = json.dumps(unc, indent=2) + "\n"
    if text != path.read_text(encoding="utf-8"):
        out[path] = text
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    todo = sync(args.root)
    for path, text in sorted(todo.items()):
        print(("would write " if args.check else "wrote ") + str(path))
        if not args.check:
            path.write_bytes(text.encode("utf-8"))
    return 1 if (args.check and todo) else 0


if __name__ == "__main__":
    raise SystemExit(main())
