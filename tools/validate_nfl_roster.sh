#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
inventory='reports/assets/nfl2k5_resource_chunks_v2.json'
apf_index='extracted/All-Pro Football 2K8 (USA)/0A'
apf_tmp='/tmp/nfl2k5-roster-apf-validate'
fresh='/tmp/nfl2k5-roster-validation'

python3 -m py_compile tools/nfl_roster.py
mkdir -p "$apf_tmp"
python3 tools/apf_inner.py "$apf_index" \
  --entry 1126 --dump-file 0 --output-dir "$apf_tmp" >/dev/null

python3 tools/nfl_roster.py "$index" \
  --inventory "$inventory" \
  --apf-block "$apf_tmp/roster.block0.bin" \
  --output "$fresh.json" \
  --resources-tsv "$fresh-resources.tsv" \
  --teams-tsv "$fresh-teams.tsv" \
  --players-tsv "$fresh-players.tsv" >/dev/null

cmp "$fresh.json" reports/assets/nfl2k5_roster.json
cmp "$fresh-resources.tsv" reports/assets/nfl2k5_roster_resources.tsv
cmp "$fresh-teams.tsv" reports/assets/nfl2k5_roster_teams.tsv
cmp "$fresh-players.tsv" reports/assets/nfl2k5_roster_players.tsv
sha256sum -c reports/assets/nfl2k5_roster.sha256 >/dev/null

python3 - <<'PY'
import csv
import json
from collections import Counter
from pathlib import Path

report = json.loads(Path("reports/assets/nfl2k5_roster.json").read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_roster_inventory/v1"
summary = report["summary"]
assert summary["resource_count"] == 76
assert summary["labels"] == {"historic": 75, "roster": 1}
assert summary["unique_body_sha256_count"] == 76
assert summary["player_total"] == 6522
assert summary["table_totals"] == {
    "coaches": 110,
    "colleges": 266,
    "generated_names": 485,
    "historic_descriptors": 75,
    "player_pointer_vector": 241,
    "primary_players": 6454,
    "secondary_players": 68,
    "stadiums": 157,
    "team_labels": 36,
    "teams": 127,
}
assert summary["team_kind_codes"] == {"0": 32, "1": 9, "2": 2, "4": 75, "5": 9}
assert report["format"]["relative_pointer_formula"] == "field_offset + signed_stored_value - 1"
assert report["format"]["player_stride"] == 0x54
assert report["format"]["team_stride"] == 0x1F4

cross = report["xex_cross_title"]
assert cross["schema"] == "vc_roster_cross_title_probe/v1"
assert cross["sha256"] == "e959d3067ebcdbeb4f08979fa74d9fa61cf90fd91b90793863e6a3313be7f7ff"
assert cross["primary_player_count"] == 2254
assert cross["primary_player_offset"] == 0x14C
assert cross["primary_player_stride"] == 0x14C
assert cross["primary_player_end"] == 0xB6C74
assert all(cross["validation"].values())

patterns = Counter()
for resource in report["resources"]:
    assert all(resource["validation"].values())
    tables = resource["tables"]
    patterns[tuple(tables[name]["count"] for name in (
        "primary_players", "secondary_players", "stadiums", "teams", "colleges",
        "player_pointer_vector", "coaches", "team_labels", "generated_names", "historic_descriptors"
    ))] += 1
assert patterns == Counter({
    (53, 0, 1, 1, 0, 0, 1, 0, 0, 0): 75,
    (2479, 68, 82, 52, 266, 241, 35, 36, 485, 75): 1,
})

def rows(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))

resources = rows("reports/assets/nfl2k5_roster_resources.tsv")
teams = rows("reports/assets/nfl2k5_roster_teams.tsv")
players = rows("reports/assets/nfl2k5_roster_players.tsv")
assert len(resources) == 76
assert len(teams) == 127
assert len(players) == 6522
cardinals = next(row for row in teams if row["outer_index"] == "5" and row["nickname"] == "Cardinals")
assert cardinals["abbreviation"] == "ARZ" and cardinals["city"] == "Arizona"
duane = next(row for row in players if row["outer_index"] == "5" and row["player_index"] == "0" and row["pool"] == "primary_players")
assert (duane["first_name"], duane["last_name"], duane["college_name"], duane["team_names"]) == (
    "Duane", "Starks", "Miami, FL", "Cardinals"
)

trace = Path("research/functions/nfl2k5/focused/roster_trace.txt").read_text(encoding="utf-8")
assert "RAW_ROST count=8" in trace
assert "SCALAR_ROST_COUNT=6" in trace
assert "0x000C1F00:FUN_000c1f00" in trace
assert "0x000C2040:FUN_000c2040" in trace
assert "0x000C2180:FUN_000c2180" in trace
assert "0x002D17B0:FUN_002d17b0" in trace
pseudo = Path("research/functions/nfl2k5/focused/roster_focused_pseudo_c.c").read_text(encoding="utf-8")
assert "PORTME: could not decompile" not in pseudo
PY

printf 'NFL2K5_ROSTER_VALIDATION_PASS resources=76 players=6522 teams=127\n'
