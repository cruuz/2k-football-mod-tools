#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

nfl_xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
apf_xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
director='reports/assets/cross_title_director_inventory.json'
report='reports/cut_content/apf_nfl_lineage/basic_training_remnant.json'

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
  tools/apf_basic_training_remnant.py

python3 tools/apf_basic_training_remnant.py \
  --nfl-xbe "$nfl_xbe" \
  --nfl-header reports/headers/nfl2k5_xbe_header.json \
  --apf-xex "$apf_xex" \
  --apf-pe "$tmp/apf2k8_default.pe" \
  --director-report "$director" \
  --json-out "$tmp/basic_training_remnant.json" \
  >"$tmp/generator.txt"

cmp "$report" "$tmp/basic_training_remnant.json"

python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("reports/cut_content/apf_nfl_lineage/basic_training_remnant.json").read_text())
assert report["schema"] == "vc_apf_basic_training_remnant/v1"
assert report["scope"]["runtime_reachability_claimed"] is False
assert report["scope"]["playable_hidden_tutorial_claimed"] is False
assert set(report["apf2k8"]["states"]) == {"basic", "pause", "crippled_pause"}
assert len(report["apf2k8"]["states"]["basic"]["events"]) == 6
assert report["apf2k8"]["states"]["basic"]["transition"] == "TutorialSelectMenu"
assert report["apf2k8"]["states"]["basic"]["layout"] == "spreadsheet"
assert report["nfl2k5"]["training_update"]["last_instruction_start"] == "0x0011EE28"
assert report["nfl2k5"]["training_update"]["next_function"] == "0x0011EE30"
assert report["apf2k8"]["training_update"]["last_instruction_start"] == "0x84ADFB08"
assert report["apf2k8"]["training_update"]["tail_epilogue_target"] == "0x84BD6E34"
assert report["apf2k8"]["training_update"]["alignment_padding"]["word"] == "00000000"
assert report["apf2k8"]["training_update"]["next_function"] == "0x84ADFB10"
assert report["apf2k8"]["tutorial_package_loader"]["last_instruction_start"] == "0x849D8E54"
assert report["apf2k8"]["tutorial_package_loader"]["next_function"] == "0x849D8E58"
assert report["apf2k8"]["ownership"]["external_frontend_route_proved"] is False
assert report["apf2k8"]["mode_gate"]["required_value"] == 4
assert report["apf2k8"]["mode_gate"]["fixed_immediate_value_4_store_found"] is False
assert len(report["apf2k8"]["mode_gate"]["conventional_store_classifications"]) == 10
assert all(row["fixed_value"] != 4 for row in report["apf2k8"]["mode_gate"]["conventional_store_classifications"])
assert report["apf2k8"]["tutorial_package_loader"]["function_pointer_sites"] == ["0x844F0F30"]
assert report["director_package_lineage"]["shared_exact_primary_string_count"] == 101
assert report["cross_title_findings"]["three_state_subsystem_retained"] is True
assert report["cross_title_findings"]["apf_tutorial_loader_function_pointer_retained"] is True
assert report["cross_title_findings"]["apf_external_frontend_route_proved"] is False
assert len(report["portme"]) == 4
PY

test "$(sha256sum "$nfl_xbe" | cut -d' ' -f1)" = "$before_nfl"
test "$(sha256sum "$apf_xex" | cut -d' ' -f1)" = "$before_apf"

echo "APF_BASIC_TRAINING_REMNANT_VALIDATION_PASS states=3 events=6 director_strings=101 external_route=false mode4_fixed_store=false runtime=false originals_unchanged=yes"
