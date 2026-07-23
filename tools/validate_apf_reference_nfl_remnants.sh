#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

mkdir -p /media/noah/Storage/.codex-tmp
temporary="$(mktemp -d /media/noah/Storage/.codex-tmp/apf-reference-remnants.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT

apf_index='extracted/All-Pro Football 2K8 (USA)/0A'
nfl_index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
nfl_xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
canonical_trace='reports/cut_content/apf_nfl_lineage/reference_remnants/ghidra_trace.txt'
canonical_json='reports/cut_content/apf_nfl_lineage/reference_remnants.json'
canonical_diff='reports/cut_content/apf_nfl_lineage/reference_remnants_text_diff.tsv'
canonical_licensed='reports/cut_content/apf_nfl_lineage/reference_remnants_licensed_text.tsv'
canonical_claims='reports/cut_content/apf_nfl_lineage/reference_remnants_video_claims.tsv'
canonical_assets='reports/cut_content/apf_nfl_lineage/reference_remnants'

sha256sum "$apf_index" "$nfl_index" "$nfl_xbe" > "$temporary/originals.before"

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/apf_reference_nfl_remnants.py

trace="$canonical_trace"
mode=normal
if [[ "${APF_REFERENCE_REMNANTS_GHIDRA:-0}" == 1 ]]; then
  ghidra=tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless
  test -x "$ghidra"
  env \
    HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    "$ghidra" "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfReferenceRemnantTrace.java "$temporary/ghidra_trace.txt" \
      > "$temporary/ghidra.stdout" 2>&1
  cmp "$canonical_trace" "$temporary/ghidra_trace.txt"
  trace="$temporary/ghidra_trace.txt"
  mode=full
fi

generate() {
  local prefix="$1"
  PYTHONPATH=tools python3 tools/apf_reference_nfl_remnants.py \
    --ghidra-trace "$trace" \
    --output-dir "$canonical_assets" \
    --json-out "$prefix.json" \
    --diff-tsv-out "$prefix.diff.tsv" \
    --licensed-tsv-out "$prefix.licensed.tsv" \
    --claims-tsv-out "$prefix.claims.tsv"
}

generate "$temporary/first" > "$temporary/first.stdout"
cp "$canonical_assets/apf_reference_nfl_shield.png" "$temporary/first.png"
generate "$temporary/second" > "$temporary/second.stdout"
cmp "$temporary/first.json" "$temporary/second.json"
cmp "$temporary/first.diff.tsv" "$temporary/second.diff.tsv"
cmp "$temporary/first.licensed.tsv" "$temporary/second.licensed.tsv"
cmp "$temporary/first.claims.tsv" "$temporary/second.claims.tsv"
cmp "$temporary/first.png" "$canonical_assets/apf_reference_nfl_shield.png"

# A full optional Ghidra run uses a temporary trace path, which is deliberately
# pinned in the report.  The trace itself is byte-identical; compare canonical
# generated reports in normal mode only.
if [[ "$mode" == normal ]]; then
  cmp "$canonical_json" "$temporary/first.json"
  cmp "$canonical_diff" "$temporary/first.diff.tsv"
  cmp "$canonical_licensed" "$temporary/first.licensed.tsv"
  cmp "$canonical_claims" "$temporary/first.claims.tsv"
fi

python3 - <<'PY'
import csv
import json
from pathlib import Path

report = json.loads(Path(
    "reports/cut_content/apf_nfl_lineage/reference_remnants.json"
).read_text())
assert report["schema"] == "vc_apf_reference_nfl_remnants/v1"
assert report["scope"] == {
    "executes_translated_guest_code": False,
    "launches_game_or_emulator": False,
    "read_only_static_and_asset_analysis": True,
    "runtime_reachability_proved": False,
    "writes_game_images": False,
}

identity = report["filename_identity"]
assert identity["apf_crc32_uppercase_ascii"] == "0xbe047dd2"
assert identity["nfl_crc32_uppercase_utf16le"] == "0x107a62a5"
assert identity["matches_apf_outer_id"] is True
assert identity["matches_nfl_outer_id"] is True
assert identity["nfl_xbe_utf16le_literal_offsets"] == ["0x00b4b71c"]

apf = report["apf"]
nfl = report["nfl"]
assert apf["outer_index"] == 1135 and apf["outer_id"] == "0xbe047dd2"
assert nfl["outer_index"] == 110 and nfl["outer_id"] == "0x107a62a5"
assert [(row["name"], row["type"]) for row in apf["files"]] == [
    ("open_book", "SCNE"),
    ("closed_book", "SCNE"),
    ("reference_data", "REFR"),
]

closed = apf["closed_book"]
assert closed["node_order"] == ["book", "nfl_shield1", "tabs"]
assert closed["material_order"] == [
    "corner_right", "corner_left", "cover", "nfl_shield", "tab_corner_left"
]
binding = closed["shield_binding"]
assert binding["node"] == "nfl_shield1"
assert binding["draw_material_index"] == 3
assert binding["material"] == "nfl_shield"
assert binding["texture_format"] == "DXT4_5"
assert binding["dimensions"] == [128, 128]

structure = apf["reference_data"]["structure"]
assert structure["record_group_counts"] == [93, 46, 217, 82]
assert structure["record_group_offsets"] == ["0x20", "0xa4c", "0xf54", "0x2710"]
assert structure["record_stride"] == 28
assert structure["total_record_count"] == 438
assert structure["string_pool_offset"] == "0x3008"
assert structure["nonzero_string_pointer_count"] == 1092
assert structure["unique_string_pointer_target_count"] == 1092
assert structure["all_nonzero_string_pointers_valid"] is True

texts = report["cross_title_text_lineage"]
assert texts["apf_printable_utf16_string_occurrences"] == 988
assert texts["nfl_printable_utf16_string_occurrences"] == 1024
assert texts["exact_ordered_string_occurrence_matches"] == 987
assert texts["removed_nfl_glossary_entry_count"] == 13
assert texts["removed_nfl_glossary_entry_titles"] == [
    '"The Catch"', '"The Comeback"', "Dawg Pound, The", "Dirty Bird",
    '"The Drive"', "Frozen Tundra, The", "Fun 'N Gun", "Green Zone",
    "Immaculate Reception", "Lambeau Leap", "No-Name Defense",
    "Run and Shoot Offense", "West Coast Offense",
]
assert texts["selectively_modified_pair_count"] == 1
assert "Bengals' defender" in texts["selectively_modified_pairs"][0]["nfl"]
assert "Bengals' defender" not in texts["selectively_modified_pairs"][0]["apf"]
assert texts["apf_explicit_nfl_token_string_count"] == 18
assert texts["apf_espn_nfl_football_string_count"] == 3
assert texts["apf_super_bowl_string_count"] == 9
assert texts["apf_nfl_team_name_string_count"] == 41

art = report["cross_title_shield_art"]
assert art["dimensions"] == [128, 128]
assert art["rgba_byte_identical"] is False
assert min(
    row["pearson_correlation"] for row in art["channel_metrics"].values()
) > 0.977
geometry = report["cross_title_shield_geometry"]
assert geometry["apf_vertex_count"] == geometry["nfl_vertex_count"] == 4
assert geometry["apf_triangle_count"] == geometry["nfl_triangle_count"] == 2
assert 0.097 < geometry["unordered_vertex_hausdorff_distance"] < 0.098

executable = report["executable_evidence"]
assert executable["refr_type_hash"] == "0x15578f45"
assert executable["apf_refr_record_relocation_worker"] == "0x84ab0d58"
assert executable["apf_load_callback"] == "0x84ab10c0"
assert executable["apf_destructor_callback"] == "0x84ab11a8"
assert executable["compiled_refr_handler_present"] is True
assert executable["menu_or_state_route_to_reference_screen_proved"] is False
assert report["claims"]["not_proved"]
assert all(line.startswith("// PORTME:") for line in report["portme"])

with Path(
    "reports/cut_content/apf_nfl_lineage/reference_remnants_text_diff.tsv"
).open(newline="") as stream:
    diff = list(csv.DictReader(stream, delimiter="\t"))
assert len(diff) == 37
assert sum(row["operation"] == "insert" for row in diff) == 36
assert sum(row["operation"] == "replace" for row in diff) == 1

with Path(
    "reports/cut_content/apf_nfl_lineage/reference_remnants_licensed_text.tsv"
).open(newline="") as stream:
    licensed = list(csv.DictReader(stream, delimiter="\t"))
assert len(licensed) == 56
assert any("ESPN NFL Football" in row["text"] for row in licensed)
assert any("NFL_team_names" in row["categories"] for row in licensed)

with Path(
    "reports/cut_content/apf_nfl_lineage/reference_remnants_video_claims.tsv"
).open(newline="") as stream:
    claims = list(csv.DictReader(stream, delimiter="\t"))
assert [row["grade"] for row in claims] == ["A_proven", "A_proven", "boundary"]
assert all(row["boundary"] for row in claims)
PY

sha256sum "$apf_index" "$nfl_index" "$nfl_xbe" > "$temporary/originals.after"
cmp "$temporary/originals.before" "$temporary/originals.after"

printf '%s\n' \
  "APF_REFERENCE_NFL_REMNANTS_VALIDATION_PASS mode=$mode shared_strings=987 apf_strings=988 refr_records=438 shield_quad=true runtime=false originals_unchanged=true"
