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
  tools/menu_label_renderer_v3.py

generate_report() {
  local trace="$1"
  local pseudo="$2"
  local prefix="$3"
  python3 tools/menu_label_renderer_v3.py \
    --apf-xex "extracted/All-Pro Football 2K8 (USA)/default.xex" \
    --apf-pe "$temporary/apf2k8_default.pe" \
    --base-report reports/assets/menu_state_trace_closure_v2.json \
    --base-trace reports/assets/menu_state_trace.json \
    --trace "$trace" \
    --pseudo "$pseudo" \
    --json-out "$prefix.json" \
    --tsv-out "$prefix.tsv" \
    --portme-c-out "${prefix}_portme.c"
}

generate_report \
  reports/assets/menu_label_renderer_v3_ghidra/apf_menu_label_renderer_v3_trace.txt \
  reports/assets/menu_label_renderer_v3_ghidra/apf_menu_label_renderer_v3_pseudo_c.c \
  "$temporary/menu_label_renderer_v3"

cmp reports/assets/menu_label_renderer_v3.json \
  "$temporary/menu_label_renderer_v3.json"
cmp reports/assets/menu_label_renderer_v3.tsv \
  "$temporary/menu_label_renderer_v3.tsv"
cmp reports/assets/menu_label_renderer_v3_portme.c \
  "$temporary/menu_label_renderer_v3_portme.c"

for compiler in gcc clang-18; do
  "$compiler" -std=c11 -Wall -Wextra -Werror -c \
    reports/assets/menu_label_renderer_v3_portme.c \
    -o "$temporary/menu_label_renderer_v3_portme_${compiler//[^a-zA-Z0-9]/_}.o"
done

python3 - <<'PY'
import hashlib
import json
from pathlib import Path

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

report = json.loads(Path("reports/assets/menu_label_renderer_v3.json").read_text())
assert report["schema"] == "vc_apf_menu_label_renderer/v3"
assert report["scope"]["launches_original_menu"] is False
assert report["scope"]["writes_ghidra_project"] is False
assert report["scope"]["main_label_content_provider_proved"] is True
assert report["scope"]["main_visible_label_renderer_proved"] is False
assert report["scope"]["final_glyph_renderer_proved"] is False
assert report["scope"]["main_provider_localization_bypass_proved"] is True
assert report["scope"]["localization_policy_proved"] is False
assert report["scope"]["cold_boot_predecessor_proved"] is False
assert len(report["recovered_boundaries"]) == 17
assert len(report["main_label_ownership"]["rows"]) == 7
audit = report["main_label_ownership"]["runtime_row_accessor_audit"]
assert audit["direct_call_count_in_apf_code"] == 18
assert all(row["callback_38"] is None for row in report["main_label_ownership"]["rows"])
layout = report["main_label_ownership"]["loaded_layout_join"]
assert layout["loaded_child"]["layout_name"] == "template_quicknav"
assert len(layout["option_bindings"]) == 8
assert all(row["content_provider"] == "0x846F5198" for row in layout["option_bindings"])
provider = report["main_label_ownership"]["runtime_label_provider"]
assert provider["function"] == "0x846F5198"
assert provider["label_getter"]["semantics"] == "lwz r3,+0x08(r3); blr"
assert provider["label_getter"]["all_direct_callers_in_apf_code"] == [
    "0x846F4A50", "0x846F524C", "0x846F5298", "0x84A3534C",
]
assert provider["selected_row_output"]["format"] == "{0}|M_PRIMARY|"
assert report["main_label_ownership"]["provider_localization_boundary"]["resolver_calls_in_proved_chain"] == []
assert report["generic_label_path_rejected_for_main"]["owner_callback"] == "0x846F2748"
assert report["generic_label_path_rejected_for_main"]["runtime_label_read"].startswith("0x846F6B94")
assert len(report["generic_label_path_rejected_for_main"]["incoming_string_argument_audit"]["normal_0x846933C0_r4_mentions"]) == 4
assert len(report["generic_label_path_rejected_for_main"]["incoming_string_argument_audit"]["colored_0x84693478_r4_mentions"]) == 6
cold = report["cold_boot_candidate_rejection"]
assert cold["candidate"] == "0x84A58698"
assert cold["static_owner_descriptor"]["title"] == "End Of Game"
assert cold["exact_owner"] == {
    "field": "+0x48 preflight callback",
    "label": "Quit",
    "row_index": 5,
    "row_type": 10,
    "source_row": "0x84E58AA0",
}
assert "definitively not a cold-boot predecessor" in cold["result"]
assert len(report["portme"]) == 4

assert digest("reports/assets/menu_label_renderer_v3.json") == \
    "59f81323ba3edc5bbb0331c47998a1bfe15fc4246358863941fc54287e6f860b"
assert digest("reports/assets/menu_label_renderer_v3.tsv") == \
    "79d155dca9c909d23013b2132e9a229f0037a5d48db1760e2abeebef7379e4c8"
assert digest("reports/assets/menu_label_renderer_v3_portme.c") == \
    "78ef6e0955eac9dfa167af8e3c84c15172ea523e6d9e34e67f198afbdbf6c7c1"
assert digest("reports/assets/menu_label_renderer_v3_ghidra/apf_menu_label_renderer_v3_trace.txt") == \
    "051bb1c007437da73fd0608aff59a0f3e783914f6092b56aa49f82ee2c2e4a6d"
assert digest("reports/assets/menu_label_renderer_v3_ghidra/apf_menu_label_renderer_v3_pseudo_c.c") == \
    "a27ab4722a8685170f3c1f2881212891c62930574d77c4d76a7f58d56f62866a"

portme = Path("reports/assets/menu_label_renderer_v3_portme.c").read_text()
assert portme.count("// PORTME:") == len(report["portme"])
doc = Path("docs/research/menu_label_renderer_v3.md").read_text()
doc_words = " ".join(doc.split()).lower()
for heading in ("## Worked", "## Failed or unproved", "## Blocking"):
    assert heading in doc
assert "does not launch an original menu" in doc
assert "End Of Game" in doc and "Quit" in doc
assert "not a cold-boot predecessor" in doc_words
assert "content provider is proved" in doc_words
assert "final font selection, glyph layout, and gpu submission are not proved" in doc_words
PY

mode=normal
if [[ "${MENU_LABEL_RENDERER_V3_GHIDRA:-0}" == 1 ]]; then
  ghidra=tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless
  test -x "$ghidra"
  mkdir -p "$temporary/ghidra"
  env \
    HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    "$ghidra" "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfMenuLabelRendererV3.java "$temporary/ghidra"

  for name in \
      apf_menu_label_renderer_v3_trace.txt \
      apf_menu_label_renderer_v3_pseudo_c.c; do
    cmp "reports/assets/menu_label_renderer_v3_ghidra/$name" \
      "$temporary/ghidra/$name"
  done

  generate_report \
    "$temporary/ghidra/apf_menu_label_renderer_v3_trace.txt" \
    "$temporary/ghidra/apf_menu_label_renderer_v3_pseudo_c.c" \
    "$temporary/menu_label_renderer_v3_full"
  cmp reports/assets/menu_label_renderer_v3.json \
    "$temporary/menu_label_renderer_v3_full.json"
  cmp reports/assets/menu_label_renderer_v3.tsv \
    "$temporary/menu_label_renderer_v3_full.tsv"
  cmp reports/assets/menu_label_renderer_v3_portme.c \
    "$temporary/menu_label_renderer_v3_full_portme.c"
  mode=full
fi

echo "APF_MENU_LABEL_RENDERER_V3_VALIDATION_PASS mode=$mode boundaries=17 accessors=18 provider_bindings=8 main_rows=7 cold_rejections=1 portme=4"
