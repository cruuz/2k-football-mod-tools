#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index=${APF_INDEX:-extracted/All-Pro Football 2K8 (USA)/0A}
inventory=reports/assets/apf_roster_inventory.json
players=reports/assets/apf_roster_players.tsv
teams=reports/assets/apf_roster_teams.tsv
stadiums=reports/assets/apf_roster_stadiums.tsv
memberships=reports/assets/apf_roster_memberships.tsv
trace=reports/assets/apf_roster_ghidra/roster_trace.txt
pseudo=reports/assets/apf_roster_ghidra/roster_focused_pseudo_c.c

for required in \
  "$index" tools/apf_roster.py tools/ghidra_scripts/ApfRosterTrace.java \
  "$inventory" "$players" "$teams" "$stadiums" "$memberships" \
  "$trace" "$pseudo" reports/assets/apf_roster.sha256; do
  test -f "$required"
done

python3 -m py_compile tools/apf_roster.py
sha256sum --check reports/assets/apf_roster.sha256

temporary=$(mktemp -d /tmp/apf-roster-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

python3 tools/apf_roster.py "$index" \
  --report "$temporary/inventory.json" \
  --players-tsv "$temporary/players.tsv" \
  --teams-tsv "$temporary/teams.tsv" \
  --stadiums-tsv "$temporary/stadiums.tsv" \
  --memberships-tsv "$temporary/memberships.tsv"

cmp "$temporary/inventory.json" "$inventory"
cmp "$temporary/players.tsv" "$players"
cmp "$temporary/teams.tsv" "$teams"
cmp "$temporary/stadiums.tsv" "$stadiums"
cmp "$temporary/memberships.tsv" "$memberships"

python3 - "$inventory" <<'PY'
import json
from pathlib import Path
import sys

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert document["schema"] == "apf_roster_inventory/v1"
assert document["source"] == {
    "index_path": "extracted/All-Pro Football 2K8 (USA)/0A",
    "outer_table_index": 1126,
    "outer_name_id": "0xbceffd46",
    "outer_stored_size": 436224,
    "outer_stored_sha256": "e98dd07b38caa73ea2ce91eed19bef68896f9b63830a9169af4b7f22d8788cc7",
    "inner_index": 0,
    "inner_name": "roster",
    "inner_type": "ROST",
    "decoded_length": 2294304,
    "decoded_sha256": "e959d3067ebcdbeb4f08979fa74d9fa61cf90fd91b90793863e6a3313be7f7ff",
}
summary = document["summary"]
assert summary == {
    "player_count": 2254,
    "players_with_nonempty_name": 2241,
    "stadium_count": 31,
    "team_record_count": 40,
    "teams_with_counted_rosters": 32,
    "counted_team_roster_reference_count": 1344,
    "unique_counted_team_roster_player_count": 1344,
    "unassigned_player_count": 910,
    "utf16be_string_count": 6469,
    "empty_utf16be_string_count": 13,
}

tables = document["root"]["tables"]
assert len(tables) == 40
assert [row["count"] for row in tables] == [
    2254, 0, 1, 31, 40, 295, 199, 199, 199, 42, 5957, 69,
    650, 1050, 3200, 266, 266, 3724, 266, 40, 93, 204, 212,
] + [0] * 17
assert tables[0]["offset"] == "0x00014c" and tables[0]["stride"] == "0x0000014c"
assert tables[3]["offset"] == "0x0b7c18" and tables[3]["stride"] == "0x00000024"
assert tables[4]["offset"] == "0x0b8074" and tables[4]["stride"] == "0x00000180"
assert tables[18]["storage_length"] == 1330 and tables[18]["alignment_padding"] == 2
assert document["root"]["array_end"] == 2049940
assert document["root"]["workspace_length"] == 4000
assert document["root"]["workspace_utf16_code_unit_capacity"] == 2000
assert document["root"]["string_pool_offset"] == 2053940
assert document["root"]["string_pool_length"] == 240364

assert [(row["code"], row["abbreviation"], row["name"]) for row in document["position_labels"]] == [
    (0, "QB", "Quarterback"), (1, "K", "Kicker"), (2, "P", "Punter"),
    (3, "WR", "Wide Receiver"), (4, "CB", "Cornerback"),
    (5, "FS", "Free Safety"), (6, "SS", "Strong Safety"),
    (7, "HB", "Halfback"), (8, "FB", "Fullback"),
    (9, "TE", "Tight End"), (10, "OLB", "Outside Linebacker"),
    (11, "ILB", "Inside Linebacker"), (12, "C", "Center"),
    (13, "G", "Guard"), (14, "T", "Tackle"),
    (15, "DT", "Defensive Tackle"), (16, "DE", "Defensive End"),
]

players = document["players"]
teams = document["teams"]
stadiums = document["stadiums"]
memberships = document["team_roster_memberships"]
assert len(players) == 2254 and len(teams) == 40 and len(stadiums) == 31
assert len(memberships) == 1344
assert len({row["player_index"] for row in memberships}) == 1344
assert all(0 <= row["position_code"] <= 16 for row in players)
assert all(row["roster_count"] in (0, 42) for row in teams)
assert [row["derived_slot_kind"] for row in teams].count("built_in_team") == 24
assert [row["derived_slot_kind"] for row in teams].count("online_slot") == 8
assert [row["derived_slot_kind"] for row in teams].count("user_slot") == 8

mike = players[0]
assert (mike["first_name"], mike["last_name"], mike["position_abbreviation"]) == ("Mike", "Haynes", "CB")
assert mike["hall_of_fame_induction_year_at_0x112"] == 1997
assert mike["strings"]["career_history"] == "NE '76-'82, LA '83-'89"
assert mike["team_memberships"] == [{"team_index": 19, "team_name": "Scorpions", "roster_slot": 0}]

scorpions = teams[19]
assert scorpions["display_name"] == "Scorpions" and scorpions["abbreviation"] == "ARI"
assert scorpions["roster_player_indices"] == list(range(42))
assert scorpions["stadium_index"] == 19 and scorpions["stadium_name"] == "TMU Field"
assert stadiums[0]["display_name"] == "Liberty Park" and stadiums[0]["capacity"] == 78227
assert document["root_table_02_pointer_inventory"]["slot_count"] == 1001
assert document["root_table_02_pointer_inventory"]["nonnull_player_reference_count"] == 427
assert document["root_table_02_pointer_inventory"]["null_slot_count"] == 574
assert document["portme"] and document["failed"]
print("APF_ROSTER_JSON_INVARIANTS_PASS")
PY

test "$(wc -l < "$players")" -eq 2255
test "$(wc -l < "$teams")" -eq 41
test "$(wc -l < "$stadiums")" -eq 32
test "$(wc -l < "$memberships")" -eq 1345

rg -q '^  10 slot=0x820FEC48 raw=0x8461AC50 target=0x8461AC50 value=Outside Linebacker$' "$trace"
rg -q '^0x84750EF8 .* refs=0x82017D78\(none,DATA\)$' "$trace"
rg -q '^0x82017D78 raw=0x84750EF8 ' "$trace"
rg -q '^/\* 0x84750EF8:' "$pseudo"
rg -q '\*param_2 = 0x14c;' "$pseudo"
rg -q '\*param_2 = 0x180;' "$pseudo"
rg -q 'param_1 \+ 0x118' "$pseudo"

if [[ ${APF_ROSTER_GHIDRA:-0} == 1 ]]; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      ghidra_projects apf2k8 -process default.xex -noanalysis -readOnly \
      -scriptPath tools/ghidra_scripts \
      -postScript ApfRosterTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/roster_trace.txt" "$trace"
  cmp "$temporary/ghidra/roster_focused_pseudo_c.c" "$pseudo"
  echo APF_ROSTER_GHIDRA_REGEN_PASS
fi

echo 'APF_ROSTER_VALIDATION_PASS players=2254 teams=40 stadiums=31 memberships=1344 strings=6469'
