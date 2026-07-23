#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index=${APF_INDEX:-extracted/All-Pro Football 2K8 (USA)/0A}
report=reports/assets/apf_curve_anim_inventory.json
tsv=reports/assets/apf_curve_anim.tsv
speech=reports/assets/apf_curve_anim_face_speech.bin
ambient=reports/assets/apf_curve_anim_face_ambient.bin
trace=reports/assets/apf_curve_anim_ghidra/curve_anim_trace.txt
pseudo=reports/assets/apf_curve_anim_ghidra/curve_anim_candidate_pseudo_c.c

for required in \
  "$index" tools/apf_curve_anim.py \
  tools/ghidra_scripts/apf/ApfCurveAnimTrace.java \
  docs/research/apf_curve_anim.md "$report" "$tsv" "$speech" "$ambient" \
  "$trace" "$pseudo"; do
  test -f "$required"
done

python3 -m py_compile tools/apf_curve_anim.py
temporary=$(mktemp -d /tmp/apf-curve-anim.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/apf_curve_anim.py "$index" \
  --json "$temporary/inventory.json" \
  --tsv "$temporary/inventory.tsv" \
  --face-speech-bin "$temporary/face_speech.bin" \
  --face-ambient-bin "$temporary/face_ambient.bin"

cmp "$temporary/inventory.json" "$report"
cmp "$temporary/inventory.tsv" "$tsv"
cmp "$temporary/face_speech.bin" "$speech"
cmp "$temporary/face_ambient.bin" "$ambient"

test "$(sha256sum "$speech" | cut -d' ' -f1)" = \
  fd5e95c9fa99c1157ea83d66819f06a31eefe6bde4b28f5660904dbe917b7941
test "$(sha256sum "$ambient" | cut -d' ' -f1)" = \
  4df057a6dc9b6681b5c56e18d41be726428171dfbe1dc63e00d77464eb68783b
test "$(wc -l < "$tsv")" -eq 2326

python3 - "$report" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["schema"] == "apf_curve_anim_inventory/v1"
assert report["pointer_rule"] == (
    "target = field_offset + signed_be32(stored_value) - 1; zero means null"
)
assert report["root_layout"]["pointer_fields"] == [12, 16, 20, 24]
assert report["root_layout"]["fixed_targets_in_every_nonnull_body"] == [32, 212]
assert report["summary"] == {
    "all_bodies_tile_their_decoded_blocks": True,
    "body_length": {"maximum": 3008, "minimum": 32, "unique_count": 223},
    "curve_count": 2324,
    "decoded_body_bytes": 2657064,
    "duplicate_body_group_count": 14,
    "null_sentinel_count": 1,
    "packed_word_08_high16": {"maximum": 785, "minimum": 20, "unique_count": 250},
    "region_lengths": {
        "region_0": {"maximum": 180, "minimum": 180, "unique_count": 1},
        "region_1": {"maximum": 1828, "minimum": 242, "unique_count": 454},
        "region_2": {"maximum": 420, "minimum": 0, "unique_count": 147},
        "region_3": {"maximum": 908, "minimum": 80, "unique_count": 271},
    },
    "relocated_pointer_count": 9296,
    "resource_count": 2325,
    "unique_body_sha256_count": 2311,
    "unique_name_count": 2325,
}
assert len(report["resources"]) == 2325
curves = [item for item in report["resources"] if item["kind"] == "curve"]
nulls = [item for item in report["resources"] if item["kind"] == "null_sentinel"]
assert len(curves) == 2324 and len(nulls) == 1
assert nulls[0]["name"] == "null"
assert nulls[0]["inline_word_1c"] == "6972636c"
assert nulls[0]["sha256"] == "c9ce968a3cbf682c01fc3e73b088515bf375c2dd4a7aea2ea430e0c0860c1956"
assert all([pointer["target"] for pointer in item["pointers"]][:2] == [32, 212]
           for item in curves)
assert all(len(item["pointers"]) == 4 and len(item["regions"]) == 4
           for item in curves)
assert all(sum(region["length"] for region in item["regions"]) + 32 == item["length"]
           for item in curves)
assert all("PORTME:" in item for item in report["portme"])
print("APF_CURVE_ANIM_JSON_INVARIANTS_PASS")
PY

rg -q '^Program MD5: 217eea6084c3d03f0f1143802b1f5636$' "$trace"
rg -q '^CURVE_ANIM_HASH 0xF4257702 raw_hits=6$' "$trace"
rg -q '^0x82003E10 raw=0xF4257702$' "$trace"
rg -q '^0x82003E14 raw=0x84668C00$' "$trace"
rg -q '^0x82003E18 raw=0x84668C50$' "$trace"
rg -q '^0x82003E1C raw=0x84668F40$' "$trace"
rg -q '^CANDIDATE_FUNCTIONS count=9$' "$trace"
for address in 846684B0 84668528 84668C00 84668C50 84668F40 849CD578; do
  rg -q "^/\\* 0x${address}:" "$pseudo"
done
for offset in 0xc 0x10 0x14 0x18; do
  rg -Fq "param_1 + ${offset}" "$pseudo"
done
rg -Fq 'DAT_820d5a18,0' "$pseudo"
! rg -q 'PORTME: could not decompile' "$pseudo"

if [[ ${APF_CURVE_ANIM_GHIDRA:-0} == 1 ]]; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfCurveAnimTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/curve_anim_trace.txt" "$trace"
  cmp "$temporary/ghidra/curve_anim_candidate_pseudo_c.c" "$pseudo"
  echo APF_CURVE_ANIM_GHIDRA_REGEN_PASS
fi

echo 'APF_CURVE_ANIM_VALIDATION_PASS resources=2325 curves=2324 pointers=9296 regions=9296'
