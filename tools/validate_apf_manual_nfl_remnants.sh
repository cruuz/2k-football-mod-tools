#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

mkdir -p /media/noah/Storage/.codex-tmp
temporary="$(mktemp -d /media/noah/Storage/.codex-tmp/apf-manual-remnants.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT

apf_index='extracted/All-Pro Football 2K8 (USA)/0A'
nfl_index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
nfl_xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
apf_gltf='assets/intermediate/apf2k8/models/0499_0006_open_book.gltf'
nfl_gltf='assets/intermediate/nfl2k5/models/0109_0015_open_book.gltf'
canonical_trace='reports/cut_content/apf_nfl_lineage/manual_remnants/ghidra_trace.txt'
canonical_json='reports/cut_content/apf_nfl_lineage/manual_remnants.json'
canonical_pages='reports/cut_content/apf_nfl_lineage/manual_remnants_pages.tsv'
canonical_diff='reports/cut_content/apf_nfl_lineage/manual_remnants_authored_diff.tsv'
canonical_licensed='reports/cut_content/apf_nfl_lineage/manual_remnants_licensed_text.tsv'
canonical_claims='reports/cut_content/apf_nfl_lineage/manual_remnants_video_claims.tsv'

sha256sum "$apf_index" "$nfl_index" "$nfl_xbe" "$apf_gltf" "$nfl_gltf" \
  > "$temporary/originals.before"

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/apf_manual_nfl_remnants.py

trace="$canonical_trace"
mode=normal
if [[ "${APF_MANUAL_REMNANTS_GHIDRA:-0}" == 1 ]]; then
  ghidra=tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless
  test -x "$ghidra"
  env \
    HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    "$ghidra" "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfManualRemnantTrace.java "$temporary/ghidra_trace.txt" \
      > "$temporary/ghidra.stdout" 2>&1
  cmp "$canonical_trace" "$temporary/ghidra_trace.txt"
  trace="$temporary/ghidra_trace.txt"
  mode=full
fi

generate() {
  local prefix="$1"
  PYTHONPATH=tools python3 tools/apf_manual_nfl_remnants.py \
    --ghidra-trace "$trace" \
    --json-out "$prefix.json" \
    --pages-tsv-out "$prefix.pages.tsv" \
    --diff-tsv-out "$prefix.diff.tsv" \
    --licensed-tsv-out "$prefix.licensed.tsv" \
    --claims-tsv-out "$prefix.claims.tsv"
}

generate "$temporary/first" > "$temporary/first.stdout"
generate "$temporary/second" > "$temporary/second.stdout"
cmp "$temporary/first.json" "$temporary/second.json"
cmp "$temporary/first.pages.tsv" "$temporary/second.pages.tsv"
cmp "$temporary/first.diff.tsv" "$temporary/second.diff.tsv"
cmp "$temporary/first.licensed.tsv" "$temporary/second.licensed.tsv"
cmp "$temporary/first.claims.tsv" "$temporary/second.claims.tsv"

# A full optional Ghidra run pins its temporary trace path in the generated
# JSON.  The trace itself is byte-identical, and all path-independent tables
# must still reproduce the canonical outputs.
cmp "$canonical_pages" "$temporary/first.pages.tsv"
cmp "$canonical_diff" "$temporary/first.diff.tsv"
cmp "$canonical_licensed" "$temporary/first.licensed.tsv"
cmp "$canonical_claims" "$temporary/first.claims.tsv"
if [[ "$mode" == normal ]]; then
  cmp "$canonical_json" "$temporary/first.json"
fi

python3 - <<'PY'
import csv
import json
from pathlib import Path

report = json.loads(Path(
    "reports/cut_content/apf_nfl_lineage/manual_remnants.json"
).read_text())
assert report["schema"] == "vc_apf_manual_nfl_remnants/v1"
assert report["scope"] == {
    "executes_translated_guest_code": False,
    "formal_nfl_2k6_product_identity_proved": False,
    "launches_game_or_emulator": False,
    "read_only_static_and_asset_analysis": True,
    "runtime_reachability_proved": False,
    "writes_game_images": False,
}

identity = report["filename_identity"]
assert identity["uppercase_name"] == "MANUAL.IFF"
assert identity["apf_crc32_uppercase_ascii"] == "0x53e0eb08"
assert identity["nfl_crc32_uppercase_utf16le"] == "0x87408605"
assert identity["matches_apf_outer_id"] is True
assert identity["matches_nfl_outer_id"] is True
assert identity["nfl_xbe_utf16le_literal_count"] == 1
assert identity["nfl_xbe_utf16le_literal_offsets"] == ["0x00b4bad0"]

apf = report["apf"]
nfl = report["nfl"]
assert apf["outer_index"] == 499 and apf["outer_id"] == "0x53e0eb08"
assert apf["resource_count"] == 16
assert apf["manual_page_count"] == 15 and apf["scene_count"] == 1
assert apf["logical_page_names"] == [f"xenon-{i}" for i in range(1, 16)]
assert nfl["outer_index"] == 109 and nfl["outer_id"] == "0x87408605"
assert nfl["chunk_count"] == 16
assert nfl["manual_page_count"] == 15 and nfl["scene_count"] == 1
assert nfl["logical_page_names"] == [f"xb-{i}" for i in range(1, 16)]

titles = report["page_titles"]
assert titles == [
    "CONTROL SUMMARY",
    "QUICK GAME",
    "In-Game Pause Menu",
    "THE CRIB|TM|",
    "FRANCHISE",
    "OFF-SEASON TASKS",
    "FIRST PERSON Football|TM|",
    "ESPN 25th ANNIVERSARY",
    "PRACTICE",
    "SITUATION",
    "TOURNAMENT",
    "Features",
    "Options",
    "Extras",
    "Xbox Live",
]

lineage = report["manual_lineage"]
assert lineage["apf_string_slot_count"] == 1553
assert lineage["nfl_string_slot_count"] == 1553
assert lineage["page_string_cardinalities_exact_match"] is True
assert lineage["raw_exact_ordered_string_matches"] == 1414
assert lineage["markup_normalized_exact_ordered_string_matches"] == 1544
assert lineage["authored_difference_string_count"] == 9
assert lineage["authored_difference_class_counts"] == {
    "minor_article_cleanup": 2,
    "weekly_prep_hours_60_to_40": 3,
    "xbox_live_challenge_copy": 2,
    "xenon_control_token": 2,
}
assert lineage["licensed_category_string_counts"] == {
    "ESPN_NFL_2K5": 18,
    "ESPN_token": 44,
    "First_Person_Football": 5,
    "Franchise": 27,
    "NFL_token": 46,
    "The_Crib": 12,
    "Weekly_Prep": 4,
    "Xbox_Live": 4,
}

scene = report["open_book_scene_lineage"]
assert scene["node_order"] == ["book", "tab1", "tab2", "tab3", "tab4"]
assert scene["node_order_exact_match"] is True
assert scene["all_four_tabs_preserve_60_vertices_30_triangles"] is True
assert scene["whole_scene_byte_identical_claimed"] is False
assert [row["name"] for row in scene["meshes"]] == [
    "book", "tab1", "tab2", "tab3", "tab4"
]
for row in scene["meshes"][1:]:
    assert row["apf_vertex_count"] == row["nfl_vertex_count"] == 60
    assert row["apf_triangle_count"] == row["nfl_triangle_count"] == 30

executable = report["executable_evidence"]
assert executable["manu_type_hash"] == "0x4c997ffb"
assert executable["static_descriptor_hash_address"] == "0x82008108"
assert executable["runtime_node_hash_address"] == "0x84d22ea4"
assert executable["manu_runtime_page_accessor"] == "0x846b02b8"
assert executable["compiled_initializer_slot"] == "0x820081e8"
assert executable["compiled_manual_initializer"] == "0x846b0320"
assert executable["manual_book_initializer_pdata_extent"] == "0x846af7b0..0x846afc88"
assert executable["manual_package_string_address"] == "0x8450d6e8"
assert executable["manual_package_string"] == "manual.iff"
assert executable["open_book_resource_id"] == "0x7211e214"
assert executable["compiled_page_table_address"] == "0x84d25440"
assert executable["compiled_page_table_count"] == 15
assert executable["compiled_page_table_exactly_names_xenon_1_through_15"] is True
assert executable["compiled_initializer_and_manu_dispatch_present"] is True
assert executable["retail_frontend_route_to_initializer_proved"] is False
assert report["claims"]["not_proved"]
assert all(line.startswith("// PORTME:") for line in report["portme"])

def read_tsv(path):
    with Path(path).open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))

pages = read_tsv(
    "reports/cut_content/apf_nfl_lineage/manual_remnants_pages.tsv"
)
assert len(pages) == 15
assert [row["title"] for row in pages] == titles
assert [row["apf_name"] for row in pages] == [f"xenon-{i}" for i in range(1, 16)]
assert [row["nfl_name"] for row in pages] == [f"xb-{i}" for i in range(1, 16)]
assert sum(int(row["string_count"]) for row in pages) == 1553
assert sum(int(row["raw_exact_ordered_matches"]) for row in pages) == 1414
assert sum(int(row["markup_normalized_exact_ordered_matches"]) for row in pages) == 1544
assert sum(int(row["authored_difference_count"]) for row in pages) == 9

diffs = read_tsv(
    "reports/cut_content/apf_nfl_lineage/manual_remnants_authored_diff.tsv"
)
assert len(diffs) == 9
classes = {}
for row in diffs:
    classes[row["classification"]] = classes.get(row["classification"], 0) + 1
assert classes == lineage["authored_difference_class_counts"]
assert sum("40 hour" in row["apf_text"] and "60 hour" in row["nfl_text"] for row in diffs) == 3

licensed = read_tsv(
    "reports/cut_content/apf_nfl_lineage/manual_remnants_licensed_text.tsv"
)
assert len(licensed) == 111
assert sum("ESPN_NFL_2K5" in row["categories"] for row in licensed) == 18
assert any("FIRST PERSON Football" in row["text"] for row in licensed)

claims = read_tsv(
    "reports/cut_content/apf_nfl_lineage/manual_remnants_video_claims.tsv"
)
assert [row["grade"] for row in claims] == ["A_proven", "A_proven", "boundary"]
assert all(row["boundary"] for row in claims)
PY

sha256sum "$apf_index" "$nfl_index" "$nfl_xbe" "$apf_gltf" "$nfl_gltf" \
  > "$temporary/originals.after"
cmp "$temporary/originals.before" "$temporary/originals.after"

printf '%s\n' \
  "APF_MANUAL_NFL_REMNANTS_VALIDATION_PASS mode=$mode pages=15 strings=1553 normalized_shared=1544 authored_diffs=9 compiled_initializer=true runtime=false originals_unchanged=true"
