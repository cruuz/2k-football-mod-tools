#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

mkdir -p /media/noah/Storage/.codex-tmp
temporary="$(mktemp -d /media/noah/Storage/.codex-tmp/apf-pregame-conference.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT

apf_index='extracted/All-Pro Football 2K8 (USA)/0A'
nfl_index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
nfl_xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
canonical_assets='reports/cut_content/apf_nfl_lineage/pregame_conference_remnants'
canonical_json='reports/cut_content/apf_nfl_lineage/pregame_conference_remnants.json'
canonical_textures='reports/cut_content/apf_nfl_lineage/pregame_conference_texture_lineage.tsv'
canonical_claims='reports/cut_content/apf_nfl_lineage/pregame_conference_video_claims.tsv'

gltfs=(
  'assets/intermediate/apf2k8/models/0239_0000_bigfigureafc.gltf'
  'assets/intermediate/apf2k8/models/0239_0001_bigfigurenfc.gltf'
  'assets/intermediate/apf2k8/models/0239_0002_bighelmet.gltf'
  'assets/intermediate/nfl2k5/models/1193_0003_bigfigureafc.gltf'
  'assets/intermediate/nfl2k5/models/1193_0002_bigfigurenfc.gltf'
  'assets/intermediate/nfl2k5/models/1193_0001_bighelmet.gltf'
)

sha256sum "$apf_index" "$nfl_index" "$nfl_xbe" "${gltfs[@]}" \
  > "$temporary/originals.before"

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/apf_pregame_conference_remnants.py

generate() {
  local prefix="$1"
  PYTHONPATH=tools python3 tools/apf_pregame_conference_remnants.py \
    --output-dir "$canonical_assets" \
    --json-out "$prefix.json" \
    --texture-tsv-out "$prefix.textures.tsv" \
    --claims-tsv-out "$prefix.claims.tsv"
}

generate "$temporary/first" > "$temporary/first.stdout"
mkdir "$temporary/first-assets"
cp "$canonical_assets"/*.png "$temporary/first-assets/"
generate "$temporary/second" > "$temporary/second.stdout"
cmp "$temporary/first.json" "$temporary/second.json"
cmp "$temporary/first.textures.tsv" "$temporary/second.textures.tsv"
cmp "$temporary/first.claims.tsv" "$temporary/second.claims.tsv"
for path in "$canonical_assets"/*.png; do
  cmp "$path" "$temporary/first-assets/$(basename "$path")"
done

cmp "$canonical_json" "$temporary/first.json"
cmp "$canonical_textures" "$temporary/first.textures.tsv"
cmp "$canonical_claims" "$temporary/first.claims.tsv"

python3 - <<'PY'
import csv
import json
from pathlib import Path

report = json.loads(Path(
    "reports/cut_content/apf_nfl_lineage/pregame_conference_remnants.json"
).read_text())
assert report["schema"] == "vc_apf_pregame_conference_remnants/v1"
assert report["scope"] == {
    "executes_translated_guest_code": False,
    "launches_game_or_emulator": False,
    "read_only_static_and_asset_analysis": True,
    "runtime_reachability_proved": False,
    "writes_game_images": False,
}

identity = report["filename_identity"]
assert identity["uppercase_name"] == "PREGAMEANIMS.IFF"
assert identity["apf_crc32_uppercase_ascii"] == "0x27b28292"
assert identity["nfl_crc32_uppercase_utf16le"] == "0x0205429d"
assert identity["matches_apf_outer_id"] is True
assert identity["matches_nfl_outer_id"] is True
assert identity["nfl_xbe_utf16le_literal_offsets"] == ["0x00b027d4"]

apf = report["apf"]
nfl = report["nfl"]
assert apf["outer_index"] == 239 and apf["outer_id"] == "0x27b28292"
assert [(row["name"], row["type"]) for row in apf["resources"]] == [
    ("bigfigureafc", "SCNE"),
    ("bigfigurenfc", "SCNE"),
    ("bighelmet", "SCNE"),
    ("big_team_matchup", "MRKS"),
]
assert nfl["outer_index"] == 1193 and nfl["outer_id"] == "0x0205429d"
assert [(row["kind"], row["logical_name"]) for row in nfl["chunks"]] == [
    ("MRKS", "big_team_matchup"),
    ("SCNE", "bighelmet"),
    ("SCNE", "bigfigurenfc"),
    ("SCNE", "bigfigureafc"),
]

for name, materials in (
    ("bigfigureafc", ["afc00", "afc01"]),
    ("bigfigurenfc", ["nfc00", "nfc01"]),
):
    scene = apf["conference_scenes"][name]
    assert scene["material_order"] == materials
    assert scene["node_name"] == name
    assert scene["draw_material_indices"] == [0, 1]
    assert scene["texture_count"] == 2
    assert all(row["format"] == "DXT1" for row in scene["textures"])
    assert all(row["dimensions"] == [256, 256] for row in scene["textures"])
    nfl_scene = nfl["conference_scenes"][name]
    assert nfl_scene["material_order"] == materials
    assert all(row["format"] == "P8" for row in nfl_scene["textures"])

textures = report["conference_texture_lineage"]
assert [(row["scene"], row["material"]) for row in textures] == [
    ("bigfigureafc", "afc00"),
    ("bigfigureafc", "afc01"),
    ("bigfigurenfc", "nfc00"),
    ("bigfigurenfc", "nfc01"),
]
assert all(row["dimensions"] == [256, 256] for row in textures)
assert all(row["apf_format"] == "DXT1" and row["nfl_format"] == "P8" for row in textures)
assert all(row["rgba_byte_identical"] is False for row in textures)
assert min(row["minimum_channel_correlation"] for row in textures) > 0.9726
assert max(row["minimum_channel_correlation"] for row in textures) > 0.994

geometry = report["conference_geometry_lineage"]
assert [(row["name"], row["apf_vertex_count"], row["nfl_vertex_count"],
         row["apf_triangle_count"], row["nfl_triangle_count"]) for row in geometry] == [
    ("bigfigureafc", 919, 918, 1218, 1216),
    ("bigfigurenfc", 919, 918, 1218, 1216),
    ("bighelmet", 864, 864, 1077, 1076),
]
assert all(1.8 < row["unordered_vertex_hausdorff_distance"] < 2.0 for row in geometry)

mrks = report["mrks_lineage"]
assert mrks["selected_exact_identifier_count"] == 13
assert "ESPNlogo" in mrks["selected_exact_identifiers_present_in_both"]
assert "team_homelogo" in mrks["selected_exact_identifiers_present_in_both"]
assert apf["big_team_matchup"]["printable_utf16be_occurrence_count"] == 259
assert apf["big_team_matchup"]["distinct_printable_utf16be_count"] == 79

sheet = report["contact_sheet"]
assert sheet["dimensions"] == [1024, 512]
assert sheet["sha256"] == "08f2ea42969704b3eaf6c150d7882dbabc723efb18538e3358a8080d564a1d6f"
assert report["claims"]["not_proved"]
assert all(line.startswith("// PORTME:") for line in report["portme"])

def read_tsv(path):
    with Path(path).open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))

texture_rows = read_tsv(
    "reports/cut_content/apf_nfl_lineage/pregame_conference_texture_lineage.tsv"
)
assert len(texture_rows) == 4
assert min(float(row["minimum_channel_correlation"]) for row in texture_rows) > 0.9726
claims = read_tsv(
    "reports/cut_content/apf_nfl_lineage/pregame_conference_video_claims.tsv"
)
assert [row["grade"] for row in claims] == ["A_proven", "A_proven", "boundary"]
assert all(row["boundary"] for row in claims)
PY

sha256sum "$apf_index" "$nfl_index" "$nfl_xbe" "${gltfs[@]}" \
  > "$temporary/originals.after"
cmp "$temporary/originals.before" "$temporary/originals.after"

printf '%s\n' \
  'APF_PREGAME_CONFERENCE_REMNANTS_VALIDATION_PASS resources=4 textures=4 corr_min=0.972666 geometry=3 runtime=false originals_unchanged=true'
