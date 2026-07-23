#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

nfl_xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
apf_xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
trace='reports/cut_content/apf_nfl_lineage/audio_test_ghidra/apf_audio_test_remnant_trace.txt'
pseudo='reports/cut_content/apf_nfl_lineage/audio_test_ghidra/apf_audio_test_remnant_pseudo_c.c'
report='reports/cut_content/apf_nfl_lineage/audio_test_remnant.json'
table='reports/cut_content/apf_nfl_lineage/audio_test_remnant.tsv'

before_nfl="$(sha256sum "$nfl_xbe" | cut -d' ' -f1)"
before_apf="$(sha256sum "$apf_xex" | cut -d' ' -f1)"

clang++-18 -std=c++20 -O2 \
  tools/xex_extract_pe.cpp \
  -Itools/vendor/XenonRecomp/XenonUtils \
  -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \
  -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \
  tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
  -o "$tmp/xex_extract_pe"

"$tmp/xex_extract_pe" "$apf_xex" "$tmp/apf2k8_default.pe" >/dev/null

PYTHONPYCACHEPREFIX="$tmp/pycache" python3 -m py_compile \
  tools/audio_test_remnant.py

generate() {
  local ghidra_trace="$1"
  local ghidra_pseudo="$2"
  local output_dir="$3"
  python3 tools/audio_test_remnant.py \
    --nfl-xbe "$nfl_xbe" \
    --nfl-header reports/headers/nfl2k5_xbe_header.json \
    --apf-xex "$apf_xex" \
    --apf-pe "$tmp/apf2k8_default.pe" \
    --apf-inner reports/manifests/apf_inner.json \
    --nfl-chunks reports/assets/nfl2k5_resource_chunks_v2.json \
    --lineage reports/cut_content/apf_nfl_lineage/resource_lineage.tsv \
    --ghidra-trace "$ghidra_trace" \
    --ghidra-pseudo "$ghidra_pseudo" \
    --json-out "$output_dir/audio_test_remnant.json" \
    --tsv-out "$output_dir/audio_test_remnant.tsv"
}

mkdir -p "$tmp/normal"
generate "$trace" "$pseudo" "$tmp/normal"
cmp "$report" "$tmp/normal/audio_test_remnant.json"
cmp "$table" "$tmp/normal/audio_test_remnant.tsv"

python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("reports/cut_content/apf_nfl_lineage/audio_test_remnant.json").read_text())
assert report["schema"] == "vc_audio_test_remnant/v1"
assert report["scope"]["read_only_static_audit"] is True
assert report["scope"]["runtime_reachability_claimed"] is False
assert [row["label"] for row in report["nfl2k5"]["options"]["rows"]][-1] == "Audio Test"
assert report["nfl2k5"]["options"]["rows"][-1]["target"] == "0x0052BFA0"
assert report["nfl2k5"]["sound_test"]["absolute_pointer_count_in_xbe"] == 1
assert report["apf2k8"]["options"]["row_count"] == 7
assert all(row["label"] != "Audio Test" for row in report["apf2k8"]["options"]["rows"])
sound = report["apf2k8"]["sound_test"]
assert sound["address"] == "0x82006870"
assert sound["title"] == "Sound Test"
assert sound["transition"] == "AudioTestMenu"
assert sound["layout"] == "gamesound"
assert sound["absolute_pointer_count_in_pe"] == 0
assert sound["conventional_lis_addi_or_ori_materializations"] == []
assert sound["control_counts"]["main_menu_descriptor_absolute_pointers"] == 78
assert sound["control_counts"]["options_descriptor_absolute_pointers"] == 2
assert [row["event"] for row in sound["events"]] == [4, 5, 6]
assert len(report["package_lineage"]["direct_shared_resources"]) == 10
assert report["package_lineage"]["nfl2k5"]["resource_count"] == 14
assert report["package_lineage"]["apf2k8"]["resource_count"] == 10
assert len(report["portme"]) == 4
PY

mode=normal
if [[ "${APF_AUDIO_TEST_REMNANT_GHIDRA:-0}" == 1 ]]; then
  ghidra='tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless'
  test -x "$ghidra"
  mkdir -p "$tmp/ghidra" "$tmp/full"
  env \
    HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    "$ghidra" "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfAudioTestRemnantTrace.java "$tmp/ghidra"
  cmp "$trace" "$tmp/ghidra/apf_audio_test_remnant_trace.txt"
  cmp "$pseudo" "$tmp/ghidra/apf_audio_test_remnant_pseudo_c.c"
  generate \
    "$tmp/ghidra/apf_audio_test_remnant_trace.txt" \
    "$tmp/ghidra/apf_audio_test_remnant_pseudo_c.c" \
    "$tmp/full"
  # Input paths differ in full mode, so compare the semantic payload after
  # normalizing only those two provenance path fields.
  python3 - "$report" "$tmp/full/audio_test_remnant.json" <<'PY'
import json, sys
from pathlib import Path

left = json.loads(Path(sys.argv[1]).read_text())
right = json.loads(Path(sys.argv[2]).read_text())
for key in ("ghidra_trace", "ghidra_pseudo"):
    right["inputs"][key]["path"] = left["inputs"][key]["path"]
assert right == left
PY
  cmp "$table" "$tmp/full/audio_test_remnant.tsv"
  mode=full
fi

after_nfl="$(sha256sum "$nfl_xbe" | cut -d' ' -f1)"
after_apf="$(sha256sum "$apf_xex" | cut -d' ' -f1)"
test "$before_nfl" = "$after_nfl"
test "$before_apf" = "$after_apf"

echo "APF_AUDIO_TEST_REMNANT_VALIDATION_PASS mode=$mode nfl_options=9 apf_options=7 shared_resources=10 apf_descriptor_pointers=0 runtime=false originals_unchanged=yes"
