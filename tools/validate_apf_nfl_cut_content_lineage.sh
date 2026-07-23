#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python_cache="${TMPDIR:-/tmp}/vc-apf-lineage-pycache-$$"
trap 'rm -rf "$python_cache"' EXIT
export PYTHONPYCACHEPREFIX="$python_cache"

script="tools/apf_nfl_cut_content_lineage.py"
output="reports/cut_content/apf_nfl_lineage"
apf_index="extracted/All-Pro Football 2K8 (USA)/0A"
nfl_index="extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"

python3 -m py_compile "$script"

before_apf="$(stat -c '%s:%Y' "$apf_index")"
before_nfl="$(stat -c '%s:%Y' "$nfl_index")"

python3 "$script" >"$python_cache/first.log"
grep -q '^APF_NFL_CUT_CONTENT_LINEAGE_PASS archives=7 resources=228 direct_shared=105 byte_identical=0 franchise_strings=1492$' "$python_cache/first.log"

sha256sum \
  "$output/lineage.json" \
  "$output/archive_summary.tsv" \
  "$output/resource_lineage.tsv" \
  "$output/scene_vertex_lineage.tsv" \
  "$output/video_evidence.tsv" \
  >"$python_cache/first.sha256"

python3 "$script" >"$python_cache/second.log"
grep -q '^APF_NFL_CUT_CONTENT_LINEAGE_PASS archives=7 resources=228 direct_shared=105 byte_identical=0 franchise_strings=1492$' "$python_cache/second.log"

sha256sum \
  "$output/lineage.json" \
  "$output/archive_summary.tsv" \
  "$output/resource_lineage.tsv" \
  "$output/scene_vertex_lineage.tsv" \
  "$output/video_evidence.tsv" \
  >"$python_cache/second.sha256"
cmp "$python_cache/first.sha256" "$python_cache/second.sha256"

[[ "$before_apf" == "$(stat -c '%s:%Y' "$apf_index")" ]]
[[ "$before_nfl" == "$(stat -c '%s:%Y' "$nfl_index")" ]]

python3 - <<'PY'
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

root = Path.cwd()
base = root / "reports/cut_content/apf_nfl_lineage"
report = json.loads((base / "lineage.json").read_text(encoding="utf-8"))
assert report["schema"] == "vc_apf_nfl_cut_content_lineage/v1"

expected_summary = {
    "selected_apf_archive_count": 7,
    "selected_apf_resource_count": 228,
    "direct_archive_pair_count": 5,
    "direct_shared_name_type_count": 105,
    "direct_byte_identical_decoded_resource_count": 0,
    "global_nfl_name_type_match_count": 107,
    "apf_only_in_complete_named_nfl_catalog_count": 121,
    "franchise_apf_resource_count": 118,
    "franchise_nfl_resource_count": 91,
    "franchise_direct_shared_name_type_count": 77,
    "franchise_apf_addition_count": 41,
    "franchise_nfl_only_count": 14,
    "franchise_shared_layout_count": 22,
    "franchise_exact_whole_layout_sequence_count": 21,
    "franchise_exact_ordered_string_record_count": 1492,
    "franchise_exact_string_pool_entry_count": 1106,
    "texture_visual_comparison_count": 3,
    "probable_common_source_audio_count": 4,
    "scene_exact_node_name_lineage_count": 3,
    "runtime_reachability_proved": False,
    "nfl_2k6_identity_proved": False,
}
assert report["summary"] == expected_summary

coverage = report["catalog_coverage"]["counts"]
assert coverage == {
    "AMCR": 10, "AUDO": 850, "AUSB": 17, "LAYT": 86,
    "MRKS": 170, "SCNE": 4616, "STRG": 2, "TXTR": 57208,
}

archives = {row["apf_outer_index"]: row for row in report["archive_summaries"]}
assert set(archives) == {108, 137, 730, 810, 941, 1215, 1221}
for index, values in {
    137: (10, 14, 10, 0, 4),
    730: (15, 15, 14, 1, 1),
    810: (118, 91, 77, 41, 14),
    941: (1, 1, 1, 0, 0),
    1221: (4, 3, 3, 1, 0),
}.items():
    row = archives[index]
    actual = (
        row["apf_resource_count"], row["nfl_resource_count"],
        row["direct_shared_name_type_count"], row["direct_apf_only_name_type_count"],
        row["direct_nfl_only_name_type_count"],
    )
    assert actual == values, (index, actual, values)
    assert row["direct_byte_identical_decoded_resource_count"] == 0
assert archives[108]["apf_only_in_complete_named_nfl_catalog_count"] == 61
assert archives[1215]["global_nfl_name_type_match_count"] == 2
assert archives[1215]["apf_only_in_complete_named_nfl_catalog_count"] == 17

resources = report["resources"]
assert len(resources) == 228
classifications = Counter(row["classification"] for row in resources)
assert classifications == {
    "apf_only_in_complete_named_nfl_catalog": 121,
    "structurally_converted_same_named_resource": 76,
    "structurally_converted_exact_layout_sequence": 21,
    "probable_common_source_transcoded_audio": 4,
    "visually_equivalent_transcoded_texture": 3,
    "name_and_type_match_only": 2,
    "structurally_converted_exact_1492_text_sequence": 1,
}
assert not any(row["direct_decoded_byte_identical"] for row in resources)
assert not any(row["global_nfl_byte_match_count"] for row in resources)

textures = {row["name"]: row for row in report["texture_comparisons"]}
assert set(textures) == {"mailpieces", "email2", "draft_logo"}
assert textures["draft_logo"]["apf_dimensions"] == "128x128"
assert textures["draft_logo"]["nfl_dimensions"] == "128x128"
assert textures["draft_logo"]["apf_format"] == "DXT4_5"
assert textures["draft_logo"]["nfl_format"] == "P8"
assert textures["draft_logo"]["pearson_correlation_rgba"] > 0.997
assert textures["email2"]["pearson_correlation_rgba"] > 0.998
assert textures["mailpieces"]["pearson_correlation_rgba"] > 0.91

audio = {row["name"]: row for row in report["audio_comparisons"]}
assert set(audio) == {
    "draft_whoosh_in1", "draft_board_pick1",
    "draft_draftboard_to_computer1", "draft_computer_to_draftboard1",
}
for row in audio.values():
    assert row["apf_codec"] == "XMA1"
    assert row["nfl_codec"] == "Xbox IMA ADPCM"
    assert row["apf_channels"] == row["nfl_channels"]
    assert row["apf_sample_rate"] == row["nfl_sample_rate"] == 22050
    assert abs(row["sample_count_delta_apf_minus_nfl"]) <= 128
    assert row["global_stft_magnitude_cosine"] > 0.97
    assert 0.99 < row["rms_ratio"] < 1.02

scenes = {row["name"]: row for row in report["scene_vertex_lineage"]}
assert {
    name: (
        row["node_count"], row["nfl_declared_vertex_total"],
        row["apf_declared_vertex_total"], row["changed_node_count"],
    )
    for name, row in scenes.items()
} == {
    "sc_logo": (3, 1858, 1958, 2),
    "bermanintro": (20, 4328, 4270, 3),
    "draft_menu": (41, 8624, 8671, 7),
}
assert {row["name"]: row["delta_apf_minus_nfl"] for row in scenes["sc_logo"]["changed_nodes"]} == {
    "group1": 50, "group3": 50,
}
assert {row["name"]: row["delta_apf_minus_nfl"] for row in scenes["bermanintro"]["changed_nodes"]} == {
    "b_studio_floor": 9, "i_paper_shadow": 20, "s_bermanhead": -87,
}

strings = report["franchise_string_evidence"]
assert strings["record_count"] == 1492
assert strings["ordered_texts_identical"] is True
assert strings["pool_entry_count"] == 1106
assert strings["pools_identical"] is True
assert strings["numeric_id_domains_shared"] is False
assert {int(row["record_index"]) for row in strings["witnesses"]} == {49, 52, 73, 76, 82, 98, 201}

identity = report["apf_executable_identity"]
assert identity["original_pe_name"] == "nfl_clean_opt_submission_ready.xex"
assert identity["build_timestamp_utc"] == "2007-06-12T22:11:24Z"
assert "XENON\\NFL\\CLEAN_OPT\\default.xex.pdb" in identity["pdb_path"]
assert identity["embedded_vcsports_nfl_code_path_count"] == 24
values = [row["value"].casefold() for row in identity["embedded_vcsports_nfl_code_paths"]]
for suffix in (
    "franchisemenu_coachsdesk.vcc", "franchisemenu_playsetup.mvcc",
    "seasonmenus.mvcc", "trophyroommenu.mvcc", "userplaybooks.vcc",
):
    assert any(value.endswith(suffix) for value in values)

localization = {row["text"] for row in report["apf_nfl_espn_localization_witnesses"]}
assert {
    "NFL", "PRESENTED BY ESPN", "Franchise/", "Playoff Picture", "Draft",
    "SEASON AWARDS", "Next week on SportsCenter", "OFF-SEASON",
} <= localization

assert report["interpretation_boundary"]["not_proved"]
assert report["portme"]
for visual in report["video_ready_visuals"]:
    path = root / visual["path"]
    assert path.is_file() and path.stat().st_size > 10_000
    assert hashlib.sha256(path.read_bytes()).hexdigest() == visual["sha256"]
    assert visual["width"] >= 512 and visual["height"] >= 512

for filename, expected_rows in (
    ("archive_summary.tsv", 7),
    ("resource_lineage.tsv", 228),
    ("scene_vertex_lineage.tsv", 3),
    ("video_evidence.tsv", 8),
):
    with (base / filename).open(encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    assert len(rows) == expected_rows, (filename, len(rows), expected_rows)

print(
    "APF_NFL_CUT_CONTENT_LINEAGE_VALIDATION_PASS "
    "archives=7 resources=228 direct_shared=105 byte_identical=0 "
    "layouts=21 strings=1492 scenes=3 audio=4"
)
PY
