#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT

clang++-18 -std=c++20 -O2 \
  tools/xex_extract_pe.cpp \
  -Itools/vendor/XenonRecomp/XenonUtils \
  -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \
  -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \
  tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
  -o "$temporary/xex_extract_pe"

"$temporary/xex_extract_pe" \
  "extracted/All-Pro Football 2K8 (USA)/default.xex" \
  "$temporary/apf2k8_default.pe"

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/menu_state_trace_closure.py

python3 tools/menu_state_trace_closure.py \
  --nfl-xbe "extracted/ESPN NFL 2K5 (USA)/default.xbe" \
  --nfl-header reports/headers/nfl2k5_xbe_header.json \
  --apf-xex "extracted/All-Pro Football 2K8 (USA)/default.xex" \
  --apf-pe "$temporary/apf2k8_default.pe" \
  --base-report reports/assets/menu_state_trace.json \
  --nfl-trace reports/assets/menu_state_trace_closure_ghidra/nfl_menu_trace_closure.txt \
  --nfl-pseudo reports/assets/menu_state_trace_closure_ghidra/nfl_menu_trace_closure_pseudo_c.c \
  --apf-trace reports/assets/menu_state_trace_closure_ghidra/apf_menu_trace_closure.txt \
  --apf-pseudo reports/assets/menu_state_trace_closure_ghidra/apf_menu_trace_closure_pseudo_c.c \
  --json-out "$temporary/menu_state_trace_closure_v2.json" \
  --tsv-out "$temporary/menu_state_trace_closure_v2.tsv" \
  --portme-c-out "$temporary/menu_state_trace_closure_portme.c"

cmp reports/assets/menu_state_trace_closure_v2.json \
  "$temporary/menu_state_trace_closure_v2.json"
cmp reports/assets/menu_state_trace_closure_v2.tsv \
  "$temporary/menu_state_trace_closure_v2.tsv"
cmp reports/assets/menu_state_trace_closure_portme.c \
  "$temporary/menu_state_trace_closure_portme.c"

cc -std=c11 -Wall -Wextra -Werror -c \
  reports/assets/menu_state_trace_closure_portme.c \
  -o "$temporary/menu_state_trace_closure_portme.o"

python3 - <<'PY'
import hashlib
import json
from pathlib import Path

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

report = json.loads(Path("reports/assets/menu_state_trace_closure_v2.json").read_text())
assert report["schema"] == "vc_menu_state_trace_closure/v2"
assert report["scope"]["launches_original_menu"] is False
assert report["scope"]["writes_ghidra_project"] is False
assert len(report["recovered_boundaries"]) == 12
assert len(report["resolved_portme_from_v1"]) == 8
assert len(report["portme"]) == 15

boundaries = {(row["platform"], row["address"]): row for row in report["recovered_boundaries"]}
assert boundaries[("nfl2k5", "0x000F3E90")]["end_exclusive"] == "0x000F3F78"
assert boundaries[("nfl2k5", "0x002C8810")]["end_exclusive"] == "0x002C886C"
assert boundaries[("apf2k8", "0x846F2E00")]["end_exclusive"] == "0x846F308C"
assert boundaries[("apf2k8", "0x846F45E0")]["end_exclusive"] == "0x846F4778"
assert boundaries[("apf2k8", "0x846F59A8")]["end_exclusive"] == "0x846F5BB8"
assert boundaries[("apf2k8", "0x846EFD38")]["end_exclusive"] == "0x846EFE14"
assert boundaries[("apf2k8", "0x846EE1A8")]["end_exclusive"] == "0x846EE510"
assert boundaries[("apf2k8", "0x846EF638")]["end_exclusive"] == "0x846EF7A0"

timeline = report["apf2k8"]["template_quicknav_timeline"]
assert timeline["template_config"]["address"] == "0x84D30458"
assert timeline["proved_apply_path"]["callback_a_type3_id"] == "0x0A7E11EF"
assert timeline["descriptor_name_gap"]["string"] == "SlideOnNav_MainMenu"
assert timeline["descriptor_name_gap"]["crc_fullword_occurrences_in_unpatched_pe"] == 0

backdrop = report["apf2k8"]["layout_mainmenu_backdrop"]
assert backdrop["archive_entry"]["logical_crc32"] == "0x48C6D154"
assert backdrop["rejected_split_immediate_collision"]["status"] == "not a 0x48C6D154 construction"
assert report["apf2k8"]["labels_and_localization"]["final_renderer_proved"] is False
assert len(report["apf2k8"]["main_routes"]["queue_or_route_sites"]) == 7

assert digest("reports/assets/menu_state_trace_closure_v2.json") == \
    "1145accb0a91cc0137cbf3757a0bff9d6a85a00a55ed41efa891e2a267c7788a"
assert digest("reports/assets/menu_state_trace_closure_v2.tsv") == \
    "5075ef34aa779929e48cbb151da6f45f15b55992afb04bc21d9f4c6a213b73b0"
assert digest("reports/assets/menu_state_trace_closure_portme.c") == \
    "8ec1e93535eaa7b6a9faf1dce29f9beb0ecd015cbcf3cc0ff43dcefb59043882"

portme = Path("reports/assets/menu_state_trace_closure_portme.c").read_text()
assert portme.count("// PORTME:") == len(report["portme"])

doc = Path("docs/research/menu_state_trace_closure_v2.md").read_text()
for heading in ("## Worked", "## Failed or unproved", "## Blocking"):
    assert heading in doc
assert "does not launch an original menu" in doc
assert "no original retail menu was launched" in doc
PY

mode=normal
if [[ "${MENU_STATE_TRACE_CLOSURE_GHIDRA:-0}" == 1 ]]; then
  ghidra=tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless
  test -x "$ghidra"
  mkdir -p "$temporary/ghidra"
  for project in nfl2k5 apf2k8; do
    program=default.xbe
    if [[ "$project" == apf2k8 ]]; then
      program=default.xex
    fi
    env \
      HOME="$root/tools/ghidra-home" \
      XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
      JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
      "$ghidra" "$root/ghidra_projects" "$project" \
        -process "$program" -readOnly -noanalysis \
        -scriptPath "$root/tools/ghidra_scripts" \
        -postScript MenuTraceClosure.java "$temporary/ghidra"
  done
  for name in \
      nfl_menu_trace_closure.txt nfl_menu_trace_closure_pseudo_c.c \
      apf_menu_trace_closure.txt apf_menu_trace_closure_pseudo_c.c; do
    cmp "reports/assets/menu_state_trace_closure_ghidra/$name" \
      "$temporary/ghidra/$name"
  done
  mode=full
fi

echo "MENU_STATE_TRACE_CLOSURE_VALIDATION_PASS mode=$mode boundaries=12 resolved=8 portme=15"
