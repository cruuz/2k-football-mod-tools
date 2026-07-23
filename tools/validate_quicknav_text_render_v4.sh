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
  tools/quicknav_text_render_v4.py

generate_report() {
  local trace="$1"
  local pseudo="$2"
  local prefix="$3"
  python3 tools/quicknav_text_render_v4.py \
    --apf-xex "extracted/All-Pro Football 2K8 (USA)/default.xex" \
    --apf-pe "$temporary/apf2k8_default.pe" \
    --base-v3 reports/assets/menu_label_renderer_v3.json \
    --localization-tsv reports/assets/apf_txt_localization.tsv \
    --trace "$trace" \
    --pseudo "$pseudo" \
    --json-out "$prefix.json" \
    --tsv-out "$prefix.tsv" \
    --portme-c-out "${prefix}_portme.c"
}

generate_report \
  reports/assets/quicknav_text_render_v4_ghidra/apf_quicknav_text_render_v4_trace.txt \
  reports/assets/quicknav_text_render_v4_ghidra/apf_quicknav_text_render_v4_pseudo_c.c \
  "$temporary/quicknav_text_render_v4"

cmp reports/assets/quicknav_text_render_v4.json \
  "$temporary/quicknav_text_render_v4.json"
cmp reports/assets/quicknav_text_render_v4.tsv \
  "$temporary/quicknav_text_render_v4.tsv"
cmp reports/assets/quicknav_text_render_v4_portme.c \
  "$temporary/quicknav_text_render_v4_portme.c"

for compiler in gcc clang-18; do
  "$compiler" -std=c11 -Wall -Wextra -Werror -c \
    reports/assets/quicknav_text_render_v4_portme.c \
    -o "$temporary/quicknav_text_render_v4_portme_${compiler//[^a-zA-Z0-9]/_}.o"
done

python3 - <<'PY'
import hashlib
import json
from pathlib import Path

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

report = json.loads(Path("reports/assets/quicknav_text_render_v4.json").read_text())
assert report["schema"] == "vc_apf_quicknav_text_render/v4"
scope = report["scope"]
assert scope["launches_original_menu"] is False
assert scope["writes_executable"] is False
assert scope["writes_ghidra_project"] is False
assert scope["provider_runtime_callback_invocation_proved"] is True
assert scope["provider_output_destination_proved"] is True
assert scope["provider_output_semantic_consumer_proved"] is False
assert scope["immediate_handoff_discards_provider_argument_proved"] is True
assert scope["static_to_runtime_binding_materialization_proved"] is False
assert scope["generic_text_backend_proved"] is True
assert scope["generic_utf16_glyph_walk_proved"] is True
assert scope["generic_vertex_generation_proved"] is True
assert scope["generic_gpu_command_buffer_path_proved"] is True
assert scope["named_font_resource_proved"] is False
assert scope["atlas_binding_proved"] is False
assert scope["named_final_gpu_draw_api_proved"] is False
assert scope["main_provider_localization_bypass_proved"] is True
assert scope["alternate_locale_policy_proved"] is False

dispatch = report["runtime_provider_dispatch"]
assert len(dispatch["static_bindings_from_v3"]) == 8
assert dispatch["runtime_entry_stride"] == 24
assert dispatch["runtime_table_load"] == {"field": "layout/root +0x14", "site": "0x846EF0D8"}
assert len(dispatch["callback_context_at_stack_0x50"]) == 9

handoff = report["provider_output_handoff"]
assert handoff["destination"] == "0x8500C060"
assert handoff["capacity_utf16_units"] == 1024
assert handoff["fullword_pointer_occurrences"] == []
assert handoff["incoming_r4_mentions_in_0x84693198"] == [
    {"address": "0x846931BC", "instruction": "addi r4,r31,0xa8"},
    {"address": "0x846931F0", "instruction": "addi r4,r1,0x50"},
]
assert handoff["callee_source_selection"]["provider_scratch_selected"] is False

backend = report["generic_text_backend"]
assert backend["active_string_state"] == "0x84D22FAC (global render state 0x84D22EC0 +0xEC)"
assert backend["utf16_adapter"]["scratch"] == "0x85008DA8"
assert backend["utf16_adapter"]["capacity"] == 2048
assert backend["source_and_case_transform"]["uppercase"]["text"] == "|MAKE_UPPERCASE|{0}"
assert backend["source_and_case_transform"]["lowercase"]["text"] == "|MAKE_LOWERCASE|{0}"
assert backend["material_selection"]["special_identifier"] == "0x536192E7"
assert backend["vertex_and_submission"]["named_final_draw_api"] is None
assert len(backend["vertex_and_submission"]["edges"]) == 10

assert len(report["recovered_boundaries"]) == 31
assert len(report["raw_or_orphan_extents"]) == 7
assert len(report["portme"]) == 6
assert report["static_binding_materialization_negative"]["static_base_fullword_occurrences"] == []
assert report["static_binding_materialization_negative"]["static_base_lis_addi_constructions"] == []

expected_hashes = {
    "reports/assets/quicknav_text_render_v4.json": "b5b2bc068b918459dd96686665edeed5ca1edb033f1ef835c285b67bab34f591",
    "reports/assets/quicknav_text_render_v4.tsv": "304a514f029a5d3813a911c437716aab764b5c26ce96e44cd76ea7eea259bae7",
    "reports/assets/quicknav_text_render_v4_portme.c": "2acab311635a6d238f6384caff45bac9795cc65aace1ca1120ef6110afcda132",
    "reports/assets/quicknav_text_render_v4_ghidra/apf_quicknav_text_render_v4_trace.txt": "04c4904b0fb7676a949edeb54e3d30ae36d6f8bed8046ed7236b4ec27a9b1a57",
    "reports/assets/quicknav_text_render_v4_ghidra/apf_quicknav_text_render_v4_pseudo_c.c": "baa36909aec7cab67cd6f38d324b6ce2835e41e9be91ffac7ef983c1a1e17436",
    "tools/ghidra_scripts/apf/ApfQuicknavTextRenderV4.java": "4d10a72fa66106d2303c41bcfcdb42257486b0f74050d03d88aa7f39d00dba2a",
    "tools/quicknav_text_render_v4.py": "00047bcebc67e08700638ef86c0c284085ffe3e6f3ee888dca93703403ac78ec",
}
for path, expected in expected_hashes.items():
    assert digest(path) == expected, (path, digest(path), expected)

portme = Path("reports/assets/quicknav_text_render_v4_portme.c").read_text()
assert portme.count("// PORTME:") == len(report["portme"])
doc = Path("docs/research/quicknav_text_render_v4.md").read_text()
doc_words = " ".join(doc.split()).lower()
for heading in ("## Worked", "## Failed or unproved", "## Blocking"):
    assert heading in doc
assert "does not launch an original menu" in doc_words
assert "immediate type-0 handoff does not use" in doc_words
assert "run +0xa8" in doc_words
assert "0x0a000000" in doc_words
assert "no semantic consumer of the main provider characters is proved" in doc_words
PY

mode=normal
if [[ "${QUICKNAV_TEXT_RENDER_V4_GHIDRA:-0}" == 1 ]]; then
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
      -postScript ApfQuicknavTextRenderV4.java "$temporary/ghidra"

  for name in \
      apf_quicknav_text_render_v4_trace.txt \
      apf_quicknav_text_render_v4_pseudo_c.c; do
    cmp "reports/assets/quicknav_text_render_v4_ghidra/$name" \
      "$temporary/ghidra/$name"
  done

  generate_report \
    "$temporary/ghidra/apf_quicknav_text_render_v4_trace.txt" \
    "$temporary/ghidra/apf_quicknav_text_render_v4_pseudo_c.c" \
    "$temporary/quicknav_text_render_v4_full"
  cmp reports/assets/quicknav_text_render_v4.json \
    "$temporary/quicknav_text_render_v4_full.json"
  cmp reports/assets/quicknav_text_render_v4.tsv \
    "$temporary/quicknav_text_render_v4_full.tsv"
  cmp reports/assets/quicknav_text_render_v4_portme.c \
    "$temporary/quicknav_text_render_v4_full_portme.c"
  mode=full
fi

echo "APF_QUICKNAV_TEXT_RENDER_V4_VALIDATION_PASS mode=$mode boundaries=31 raw_extents=7 bindings=8 r4_overwrites=2 vertex_edges=10 portme=6"
