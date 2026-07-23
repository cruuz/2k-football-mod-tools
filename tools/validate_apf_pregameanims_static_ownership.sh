#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

mkdir -p /media/noah/Storage/.codex-tmp
temporary="$(mktemp -d /media/noah/Storage/.codex-tmp/apf-pregame-owner.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT

apf_index='extracted/All-Pro Football 2K8 (USA)/0A'
apf_xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
nfl_index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
nfl_xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
canonical_dir='reports/cut_content/apf_nfl_lineage/pregameanims_owner'
canonical_json='reports/cut_content/apf_nfl_lineage/pregameanims_static_ownership.json'
canonical_names='reports/cut_content/apf_nfl_lineage/pregameanims_mrks_names.tsv'
canonical_claims='reports/cut_content/apf_nfl_lineage/pregameanims_static_ownership_claims.tsv'

sha256sum "$apf_index" "$apf_xex" "$nfl_index" "$nfl_xbe" \
  > "$temporary/originals.before"
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/apf_pregameanims_static_ownership.py

apf_trace="$canonical_dir/apf_trace.txt"
nfl_trace="$canonical_dir/nfl_trace.txt"
mode=normal
if [[ "${APF_PREGAMEANIMS_GHIDRA:-0}" == 1 ]]; then
  ghidra='tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless'
  test -x "$ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    "$ghidra" "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfPregameAnimsOwnerTrace.java "$temporary/apf_trace.txt" \
      > "$temporary/apf-ghidra.log" 2>&1
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    "$ghidra" "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/nfl2k5" \
      -postScript NflPregameAnimsOwnerTrace.java "$temporary/nfl_trace.txt" \
      > "$temporary/nfl-ghidra.log" 2>&1
  cmp "$canonical_dir/apf_trace.txt" "$temporary/apf_trace.txt"
  cmp "$canonical_dir/nfl_trace.txt" "$temporary/nfl_trace.txt"
  apf_trace="$temporary/apf_trace.txt"
  nfl_trace="$temporary/nfl_trace.txt"
  mode=full
fi

generate() {
  local prefix="$1"
  PYTHONPATH=tools python3 tools/apf_pregameanims_static_ownership.py \
    --apf-trace "$apf_trace" \
    --nfl-trace "$nfl_trace" \
    --json-out "$prefix.json" \
    --names-tsv-out "$prefix.names.tsv" \
    --claims-tsv-out "$prefix.claims.tsv"
}

generate "$temporary/first" > "$temporary/first.stdout"
generate "$temporary/second" > "$temporary/second.stdout"
cmp "$temporary/first.json" "$temporary/second.json"
cmp "$temporary/first.names.tsv" "$temporary/second.names.tsv"
cmp "$temporary/first.claims.tsv" "$temporary/second.claims.tsv"
cmp "$canonical_json" "$temporary/first.json"
cmp "$canonical_names" "$temporary/first.names.tsv"
cmp "$canonical_claims" "$temporary/first.claims.tsv"

python3 - "$canonical_json" "$canonical_names" "$canonical_claims" <<'PY'
import csv
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["schema"] == "vc_apf_pregameanims_static_ownership/v1"
assert report["scope"] == {
    "game_images_modified": False,
    "games_launched": False,
    "question": (
        "Does APF retain a static owner for pregameanims.iff, and how does "
        "big_team_matchup MRKS descend from NFL 2K5?"
    ),
    "read_only": True,
}

pair = report["exact_package_pair"]
assert pair["apf"]["outer_index"] == 239
assert pair["apf"]["outer_id"] == "0x27b28292"
assert pair["nfl"]["outer_index"] == 1193
assert pair["nfl"]["outer_id"] == "0x0205429d"
assert pair["same_four_named_resources"] is True
assert pair["physical_order_changed"] is True
assert [(row["name"], row["type"]) for row in pair["apf"]["resources"]] == [
    ("bigfigureafc", "SCNE"), ("bigfigurenfc", "SCNE"),
    ("bighelmet", "SCNE"), ("big_team_matchup", "MRKS"),
]

lineage = report["mrks_lineage"]
assert lineage["classification"] == "structurally_converted_same_named_resource"
assert lineage["common_pointer_rule"] == "one-based field-relative pointer"
assert lineage["shared_header_word_04"] == 6
assert lineage["header_word_08"] == {"apf": 25, "nfl": 41}
assert lineage["nfl_compact_identifier_count"] == 79
assert lineage["apf_exact_retained_identifier_count"] == 78
assert lineage["apf_missing_identifiers"] == ["opaque"]
assert lineage["descriptor_name"]["apf"]["text"] == "big_team_matchup"
assert lineage["descriptor_name"]["nfl"]["text"] == "big_team_matchup"

scan = report["apf_serialized_owner_scan"]
assert scan["pack_count"] == 4
assert scan["total_bytes_scanned"] == 3_873_511_424
assert scan["exact_name_external_owner_count"] == 0
assert scan["exact_utf16be_literal_occurrences"]["pregameanims_iff"] == []
assert all(
    len(scan["exact_utf16be_literal_occurrences"][f"{name}_resource_name"]) == 1
    for name in ("bigfigureafc", "bigfigurenfc", "bighelmet", "big_team_matchup")
)

apf = report["apf_executable"]
assert apf["classification"] == "no_package_specific_static_owner_found"
assert apf["exact_package_literal_count"] == 0
assert apf["exact_resource_literal_count"] == 0
assert apf["generic_mrks_handler"]["registered_type_support_present"] is True
assert apf["package_specific_runtime_route_proved"] is False

nfl = report["nfl_executable"]
assert nfl["classification"] == "compiled_package_lifecycle_owner"
assert nfl["initializer"] == "0x00125700"
assert nfl["resource_resolution_callback"] == "0x00125660"
assert nfl["resolved_scene_names"] == ["bighelmet", "bigfigureafc", "bigfigurenfc"]
table = nfl["presentation_descriptor_table"]
assert table["base"] == "0x00aad1ec"
assert table["record_count"] == 31
assert table["record_stride"] == "0x0000006c"
assert table["category_counts"] == {
    "GAMEDATA": 1, "HALFTIME": 5, "OVERLAY": 24, "PREGAME": 1,
}
assert table["big_team_matchup_record"]["index"] == 12
assert table["big_team_matchup_record"]["category"] == "PREGAME"
assert nfl["individual_descriptor_code_traversal_proved"] is False

conclusion = report["conclusion"]
assert conclusion["apf_classification"] == (
    "static_orphan_candidate_with_generic_mrks_support"
)
assert conclusion["runtime_reachability_proved_in_apf"] is False
assert conclusion["runtime_reachability_disproved_in_apf"] is False

with open(sys.argv[2], encoding="utf-8", newline="") as source:
    names = list(csv.DictReader(source, delimiter="\t"))
assert len(names) == 79
assert [row["name"] for row in names if row["apf_exact_identifier_present"] == "False"] == [
    "opaque"
]
with open(sys.argv[3], encoding="utf-8", newline="") as source:
    claims = list(csv.DictReader(source, delimiter="\t"))
assert len(claims) == 4
PY

sha256sum "$apf_index" "$apf_xex" "$nfl_index" "$nfl_xbe" \
  > "$temporary/originals.after"
cmp "$temporary/originals.before" "$temporary/originals.after"

printf 'APF_PREGAMEANIMS_STATIC_OWNERSHIP_VALIDATION_PASS mode=%s package_pair=true mrks_names=78/79 apf_static_owner=false nfl_lifecycle=true runtime=false originals_unchanged=true\n' "$mode"
