#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

clang++-18 -std=c++20 -O2 \
  tools/xex_extract_pe.cpp \
  -Itools/vendor/XenonRecomp/XenonUtils \
  -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \
  -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \
  tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
  -o "$tmp/xex_extract_pe"

"$tmp/xex_extract_pe" \
  "extracted/All-Pro Football 2K8 (USA)/default.xex" \
  "$tmp/apf2k8_default.pe"

PYTHONPYCACHEPREFIX="$tmp/pycache" python3 -m py_compile tools/menu_state_trace.py

python3 tools/menu_state_trace.py \
  --nfl-xbe "extracted/ESPN NFL 2K5 (USA)/default.xbe" \
  --nfl-header reports/headers/nfl2k5_xbe_header.json \
  --apf-pe "$tmp/apf2k8_default.pe" \
  --layout-semantics reports/assets/cross_title_layout_semantics.json \
  --layout-records reports/assets/cross_title_layout_records.tsv \
  --json-out "$tmp/menu_state_trace.json" \
  --tsv-out "$tmp/menu_state_trace.tsv" \
  --portme-c-out "$tmp/menu_state_trace_portme.c"

cmp reports/assets/menu_state_trace.json "$tmp/menu_state_trace.json"
cmp reports/assets/menu_state_trace.tsv "$tmp/menu_state_trace.tsv"
cmp reports/assets/menu_state_trace_portme.c "$tmp/menu_state_trace_portme.c"

cc -std=c11 -Wall -Wextra -Werror -c \
  reports/assets/menu_state_trace_portme.c \
  -o "$tmp/menu_state_trace_portme.o"

python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("reports/assets/menu_state_trace.json").read_text())
assert report["schema"] == "vc_menu_state_trace/v1"
assert report["scope"]["launches_original_menu"] is False
assert report["nfl2k5"]["state_descriptor"]["address"] == "0x00515660"
assert report["nfl2k5"]["state_descriptor"]["loaded_layout_name"] == "main_menu_sub"
assert report["nfl2k5"]["state_loaded_layout_entry"]["inner_index"] == 18
assert [row["label"] for row in report["nfl2k5"]["navigation_rows"]] == [
    "Quick Game", "Game Modes", "The Crib|TM|", "Features", "Options", "Xbox Live", "Extras"
]
assert report["apf2k8"]["state_descriptor"]["address"] == "0x820F4350"
assert report["apf2k8"]["state_descriptor"]["loaded_layout_name"] == "quicknav"
assert report["apf2k8"]["resource_lookup"]["logical_resource_id"] == "0x210FFA23"
assert report["apf2k8"]["state_loaded_layout_entry"]["inner_index"] == 57
assert report["apf2k8"]["visual_layout_entry"]["inner_index"] == 53
assert [row["type"] for row in report["apf2k8"]["navigation_rows"]] == [12, 11, 11, 12, 11, 11, 10]
assert report["apf2k8"]["visual_layout_link_status"]["status"].startswith("no executable edge")
assert len(report["portme"]) == 23

portme = Path("reports/assets/menu_state_trace_portme.c").read_text()
assert portme.count("// PORTME:") == len(report["portme"])

doc = Path("docs/research/menu_state_trace.md").read_text()
for heading in ("## Worked", "## Failed or unproved", "## Blocking"):
    assert heading in doc
assert "does not launch the original menu" in doc
PY

echo "menu_state_trace validation: PASS"
