#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

temporary=$(mktemp -d /tmp/nfl-actual-jersey-binding.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

python3 -m py_compile tools/nfl_actual_jersey_binding.py
PYTHONPATH=tools python3 tools/nfl_actual_jersey_binding.py \
  --output "$temporary/report.json" \
  --resources-tsv "$temporary/resources.tsv" \
  --textures-tsv "$temporary/textures.tsv" \
  --comparison-tsv "$temporary/comparison.tsv" \
  --materials-tsv "$temporary/materials.tsv" >/dev/null

cmp "$temporary/report.json" \
  reports/assets/nfl2k5_actual_jersey_binding.json
cmp "$temporary/resources.tsv" \
  reports/assets/nfl2k5_actual_jersey_binding_resources.tsv
cmp "$temporary/textures.tsv" \
  reports/assets/nfl2k5_actual_jersey_binding_textures.tsv
cmp "$temporary/comparison.tsv" \
  reports/assets/nfl2k5_actual_jersey_binding_comparison.tsv
cmp "$temporary/materials.tsv" \
  reports/assets/nfl2k5_actual_jersey_binding_materials.tsv

python3 - <<'PY'
import csv
import hashlib
import json
from pathlib import Path

base = Path("reports/assets")
report = json.loads((base / "nfl2k5_actual_jersey_binding.json").read_text())
assert report["schema"] == "nfl2k5_actual_jersey_binding/v1"
assert report["target"] == {
    "logical_name": "09H0.IFF",
    "outer_id": "0x9a4832d6",
    "outer_index": 3685,
    "selector": "09H0",
    "side_context": "HOME",
    "style": "Current Uniform",
    "team": "Detroit Lions",
    "variant": 0,
}
fresh = report["fresh_archive_revalidation"]
assert fresh["chunk_count"] == 53
assert fresh["tset_count"] == 10
assert fresh["embedded_tset_texture_count"] == 51
assert fresh["standalone_txtr_count"] == 41
assert fresh["all_wrappers_and_decoded_bodies_re_read_from_pack"]
assert fresh["all_rows_match_canonical_inventories"]
assert report["comparison"] == {
    "distinct_jersey_palette_hashes": 11,
    "distinct_jersey_pixel_hashes": 11,
    "distinct_sleeve_pixel_hashes": 13,
    "package_count": 22,
    "scope": "all 20 Detroit HOME/AWAY variants plus 01A0 and 27H0 cross-team controls",
}

binding = report["executable_binding"]
assert binding["torso"]["texture_cache_slots"] == [7, 8]
assert binding["torso"]["binding_table_names"] == ["jersey00", "jersey00"]
assert binding["torso"]["material_route_table"].endswith("UNIF_jersey")
assert binding["sleeve"]["texture_cache_slot"] == 9
assert binding["sleeve"]["binding_table_name"] == "sleeve00"
assert binding["digits"]["plain_jersey_names"] == [str(value) for value in range(48, 58)]
assert binding["digits"]["helmet_names"] == [f"hn{value}" for value in range(48, 58)]
assert binding["digits"]["arm_shoulder_names"] == [f"an{value}" for value in range(48, 58)]
assert binding["trace_anchor_count"] == 22
assert not report["runtime_negative_result"]["resolved"]
assert all(item["confidence"] == "high" for item in report["conclusions"])
assert all(item.startswith("PORTME:") for item in report["portme"])

def rows(name):
    with (base / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))

resources = rows("nfl2k5_actual_jersey_binding_resources.tsv")
textures = rows("nfl2k5_actual_jersey_binding_textures.tsv")
comparison = rows("nfl2k5_actual_jersey_binding_comparison.tsv")
materials = rows("nfl2k5_actual_jersey_binding_materials.tsv")
assert (len(resources), len(textures), len(comparison), len(materials)) == (53, 92, 22, 138)
assert [row["kind"] for row in resources] == \
    ["Unif"] + ["TSET"] * 10 + ["TXTR"] * 33 + ["NAME"] + ["TXTR"] * 8

by_name = {row["name"]: row for row in textures}
assert by_name["jersey00"]["storage_kind"] == "embedded_TSET"
assert by_name["jersey00"]["chunk_index"] == "1"
assert by_name["jersey00"]["width"] == "512"
assert by_name["jersey00"]["height"] == "256"
assert by_name["jersey00"]["pixel_sha256"] == \
    "2e42b604477996b1aad6e41a33adf7af1d00f0703913902f22c8981cf2e7efa4"
assert by_name["jersey00"]["palette_sha256"] == \
    "f9738b74119ecc3c530561b637acf394bbed6b2c649f4c5757f644dcf12e3eca"
assert by_name["sleeve00"]["chunk_index"] == "3"
assert by_name["sleeve00"]["width"] == by_name["sleeve00"]["height"] == "128"
assert by_name["bump_jersey"]["role"] == "bump_or_normal_detail_not_diffuse"
assert all(str(value) in by_name for value in range(48, 58))
assert all(f"hn{value}" in by_name for value in range(48, 58))
assert all(f"an{value}" in by_name for value in range(48, 58))

assert any(row["scene_name"] == "hi_body" and
           row["material_name"] == "UNIF_jersey" and
           row["mapping_status"] == "unmapped" for row in materials)
assert any(row["scene_name"] == "hi_body" and
           row["material_name"] == "UNIF_sleeve" and
           row["mapping_status"] == "unmapped" for row in materials)
assert any(row["scene_name"] == "hi_body" and
           row["material_name"] == "NUMBER_L" and
           row["mapping_status"] == "unmapped" for row in materials)

trace = (base / "nfl_actual_jersey_binding_ghidra" /
         "nfl_actual_jersey_binding_trace.txt").read_text()
assert "0x004EF3D8 value=0x00000018 possible_material_index=24 possible_material=UNIF_jersey" in trace
assert "0x004EF3DC value=0x00000019 possible_material_index=25 possible_material=UNIF_sleeve" in trace
assert "0x0008EC1F MOV ECX,dword ptr [EDX*0x4 + 0xb65428]" in trace
assert "0x0008EC4A MOV EAX,dword ptr [EDX + 0xb6544c]" in trace
assert "0x0008F576 MOV EDX,0xc" in trace
assert "0x0008F058 MOV EDX,0xd" in trace
assert "0x0008F5AF MOV EDX,0xe" in trace

artifact = report["built_diagnostic_artifact"]
manifest_path = Path(artifact["manifest_path"])
xiso_path = Path(artifact["xiso_path"])
assert manifest_path.is_file() and xiso_path.is_file()
manifest_bytes = manifest_path.read_bytes()
assert hashlib.sha256(manifest_bytes).hexdigest() == artifact["manifest_sha256"]
manifest = json.loads(manifest_bytes)
assert manifest["target"]["selector"] == "09A0"
assert manifest["target"]["outer_index"] == 4002
assert manifest["target"]["chunk_index"] == 1
assert manifest["output"]["xiso_sha256"] == artifact["xiso_sha256"]
assert xiso_path.stat().st_size == artifact["xiso_size"]
with xiso_path.open("rb") as stream:
    stream.seek(manifest["target"]["absolute_span_offset"])
    span = stream.read(manifest["target"]["span_size"])
assert hashlib.sha256(span).hexdigest() == artifact["replacement_span_sha256"]
assert manifest["patch"]["all_other_image_bytes_identical"]
assert manifest["claims"]["originals_modified"] is False
assert manifest["claims"]["xemu_started"] is False
assert manifest["claims"]["runtime_visibility_proved"] is False
PY

if [[ ${NFL_ACTUAL_JERSEY_BINDING_GHIDRA:-0} == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      ghidra_projects nfl2k5 \
      -process default.xbe -noanalysis -readOnly \
      -scriptPath tools/ghidra_scripts \
      -postScript NflActualJerseyBindingTrace.java "$temporary/ghidra" >/dev/null
  cmp "$temporary/ghidra/nfl_actual_jersey_binding_trace.txt" \
    reports/assets/nfl_actual_jersey_binding_ghidra/nfl_actual_jersey_binding_trace.txt
  cmp "$temporary/ghidra/nfl_actual_jersey_binding_pseudo_c.c" \
    reports/assets/nfl_actual_jersey_binding_ghidra/nfl_actual_jersey_binding_pseudo_c.c
fi

echo 'NFL_ACTUAL_JERSEY_BINDING_VALIDATION_PASS chunks=53 textures=92 materials=138 comparison=22 torso=09H0/chunk1/jersey00 sleeve=09H0/chunk3/sleeve00 probe=09A0/no-xemu'
