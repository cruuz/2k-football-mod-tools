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
  tools/apf_frontend_boot_backdrop_v5.py

generate_report() {
  local trace="$1"
  local pseudo="$2"
  local prefix="$3"
  python3 tools/apf_frontend_boot_backdrop_v5.py \
    --apf-xex "extracted/All-Pro Football 2K8 (USA)/default.xex" \
    --apf-pe "$temporary/apf2k8_default.pe" \
    --base-closure reports/assets/menu_state_trace_closure_v2.json \
    --base-menu reports/assets/menu_state_trace.json \
    --outer-manifest reports/manifests/apf_outer.json \
    --inner-candidates reports/manifests/apf_inner_candidates.tsv \
    --trace "$trace" \
    --pseudo "$pseudo" \
    --json-out "$prefix.json" \
    --tsv-out "$prefix.tsv" \
    --portme-c-out "${prefix}_portme.c"
}

generate_report \
  reports/assets/apf_frontend_boot_backdrop_v5_ghidra/apf_frontend_boot_backdrop_v5_trace.txt \
  reports/assets/apf_frontend_boot_backdrop_v5_ghidra/apf_frontend_boot_backdrop_v5_pseudo_c.c \
  "$temporary/apf_frontend_boot_backdrop_v5"

cmp reports/assets/apf_frontend_boot_backdrop_v5.json \
  "$temporary/apf_frontend_boot_backdrop_v5.json"
cmp reports/assets/apf_frontend_boot_backdrop_v5.tsv \
  "$temporary/apf_frontend_boot_backdrop_v5.tsv"
cmp reports/assets/apf_frontend_boot_backdrop_v5_portme.c \
  "$temporary/apf_frontend_boot_backdrop_v5_portme.c"

for compiler in gcc clang-18; do
  "$compiler" -std=c11 -Wall -Wextra -Werror -c \
    reports/assets/apf_frontend_boot_backdrop_v5_portme.c \
    -o "$temporary/apf_frontend_boot_backdrop_v5_${compiler//[^a-zA-Z0-9]/_}.o"
done

python3 - <<'PY'
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


report = json.loads(Path("reports/assets/apf_frontend_boot_backdrop_v5.json").read_text())
assert report["schema"] == "vc_apf_frontend_boot_backdrop/v5"
scope = report["scope"]
assert scope == {
    "cold_boot_to_main_menu_proved": False,
    "cold_boot_to_title_state_proved": True,
    "frontend_sync_archive_identity_proved": True,
    "launches_original_menu": False,
    "layout_mainmenu_archive_identity_proved": True,
    "layout_mainmenu_executable_owner_proved": False,
    "state_to_layout_mainmenu_edge_proved": False,
    "title_action_runtime_key_semantics_proved": False,
    "title_static_action_to_startup_menu_proved": True,
    "writes_executable": False,
    "writes_ghidra_project": False,
}

source = report["source"]
assert source["xex_sha256"] == "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
assert source["reconstructed_pe_sha256"] == "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
assert source["reconstructed_pe"] == "apf2k8_default.pe"

boundaries = {row["address"]: row for row in report["recovered_boundaries"]}
assert len(boundaries) == 6
assert boundaries["0x84BE9D08"]["end_exclusive"] == "0x84BE9EC8"
assert boundaries["0x846913E0"]["end_exclusive"] == "0x8469154C"
assert boundaries["0x84691650"]["end_exclusive"] == "0x84691C68"
assert boundaries["0x846E0338"]["end_exclusive"] == "0x846E0468"
assert boundaries["0x846F9360"]["end_exclusive"] == "0x846F9480"
assert boundaries["0x84A59E68"]["end_exclusive"] == "0x84A5A4C4"

entry = report["entry_to_main_loop"]
assert entry["entry"] == "0x84BE9D08"
assert entry["crt_main_call"] == {"site": "0x84BE9E9C", "target": "0x84B8B1D0"}
assert entry["game_main_loop_call"] == {"site": "0x84B8B1E0", "target": "0x84691C68"}
assert entry["bootstrap_call"] == {"site": "0x84691CC0", "target": "0x84691650"}

title = report["cold_boot_title_state"]
assert title["registration"] == {
    "callee": "0x846F9360",
    "descriptor": "0x82015330",
    "result_store": "0x84FEF4FC",
    "runtime_enable_site": "0x84691B88",
    "runtime_lookup_site": "0x84691B7C",
    "runtime_store": "0x84FEF500",
    "site": "0x84691B74",
    "state_id": "0x1F1A625A",
}
assert title["descriptor"]["name"] == "TitlePage_Menu"
assert title["action_table"]["display_record"]["literal"] == "Press START"
assert title["action_table"]["startup_action_record"] == {
    "callback": "0x846E0528",
    "key": 11,
    "literal": "Ambient: Title Start",
    "record": "0x820152EC",
    "record_type": 1,
}
assert title["action_table"]["runtime_key_11_name"] is None
assert title["registration_contract"]["event_3_dispatch"]["condition"] == \
    "event 1 callback returned nonzero"

startup = report["title_to_startup_menu"]
assert startup["descriptor"]["name"] == "StartupMenu"
assert startup["route"] == {
    "call_site": "0x846E0578",
    "callee": "0x846F8A60",
    "descriptor": "0x820F4940",
    "descriptor_site": "0x846E0574",
}
assert startup["runtime_invocation_of_key_11_proved"] is False
fallthrough = report["startup_menu_fallthrough"]
assert fallthrough["callback"] == "0x84A59E68"
assert fallthrough["descriptor_title"] == "Team Select"
assert fallthrough["transition"] == "TeamSelectMenu_QuickGameMenu"

main = report["main_menu_boundary"]
assert main["descriptor"] == "0x820F4350"
assert len(main["existing_queued_call_routes"]) == 7
assert main["new_orphan_tail_wrapper"] == {
    "callee": "0x846F60E8",
    "descriptor_site": "0x84A56954",
    "owner": None,
    "range": "0x84A56950..0x84A5695B",
    "tail_site": "0x84A56958",
}
assert main["main_descriptor_constructions_in_recovered_boot_extents"] == []
assert main["cold_boot_predecessor_proved"] is False

backdrop = report["layout_mainmenu_backdrop"]
assert backdrop["archive"] == "frontend_sync.iff"
assert backdrop["outer_index"] == 1493
assert backdrop["outer_name_id"] == "0xF69D21E4"
assert backdrop["bundle_entry_count"] == 157
assert backdrop["bundle_layout_count"] == 30
assert backdrop["inner_index"] == 53
assert backdrop["layout_name"] == "layout_mainmenu"
assert backdrop["logical_crc32"] == "0x48C6D154"
assert backdrop["type_hash"] == "0x86A1AC9E"
assert backdrop["parts"] == "b0:0x1df720+0x2c0"
assert len(backdrop["records"]) == 7
negative = backdrop["executable_negative"]
assert negative["frontend_sync_utf16be_occurrences"] == ["0x8450232C"]
for key, value in negative.items():
    if key not in ("frontend_sync_utf16be_occurrences", "frontend_sync_string_address"):
        assert value == [], (key, value)
assert backdrop["rejected_split_immediate_collision"]["status"] == \
    "not a 0x48C6D154 construction"

ghidra = report["ghidra"]
assert ghidra["read_only"] is True
assert ghidra["transient_rebuild_count"] == 6
assert ghidra["focused_decompile_portme_count"] == 0
assert len(report["portme"]) == 5

expected_hashes = {
    "reports/assets/apf_frontend_boot_backdrop_v5.json": "7124d3864bb7fbb30d9c8d42a454b115b3a6c07721ad1f3f2a75da0a21bcb911",
    "reports/assets/apf_frontend_boot_backdrop_v5.tsv": "e7cbd924b9c10a2294fbed414fe96b6cd2330f8692b773074da6e8def5650f92",
    "reports/assets/apf_frontend_boot_backdrop_v5_portme.c": "2b48ec319d8ec1dcf9c819c14e1d7bb081eb1d871065d4926f857f31ec55f2e4",
    "reports/assets/apf_frontend_boot_backdrop_v5_ghidra/apf_frontend_boot_backdrop_v5_trace.txt": "94f4ede9dd11e1670d46ddc6746c41d7b8a4e8a0022dec1a7e03142905ae9cbf",
    "reports/assets/apf_frontend_boot_backdrop_v5_ghidra/apf_frontend_boot_backdrop_v5_pseudo_c.c": "70a536124cec041da2ecb5d99ade1bb8fcb821b82d0397847f7214acbe606cff",
    "tools/ghidra_scripts/apf/ApfFrontendBootBackdropV5.java": "2208d6ec85aa87f5e06571f578b943ca0f799139798503e6d1f7344e397e94e8",
    "tools/apf_frontend_boot_backdrop_v5.py": "ddc04ba5ca35dc26efef49187130aa2408db47673776c05598a8c2c80a2df308",
}
for path, expected in expected_hashes.items():
    assert digest(path) == expected, (path, digest(path), expected)

portme = Path("reports/assets/apf_frontend_boot_backdrop_v5_portme.c").read_text()
assert portme.count("// PORTME:") == len(report["portme"])
doc = Path("docs/research/apf_frontend_boot_backdrop_v5.md").read_text()
doc_words = " ".join(doc.split()).lower()
for heading in ("## Worked", "## Failed or unproved", "## Blocking"):
    assert heading in doc
assert "does not launch an original menu" in doc_words
assert "titlepage_menu" in doc_words and "startupmenu" in doc_words
assert "cold-boot-to-main predecessor remains unproved" in doc_words
assert "absence of a literal or classic absolute construction is not proof" in doc_words
PY

mode=normal
if [[ "${APF_FRONTEND_BOOT_BACKDROP_V5_GHIDRA:-0}" == 1 ]]; then
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
      -postScript ApfFrontendBootBackdropV5.java "$temporary/ghidra"

  for name in \
      apf_frontend_boot_backdrop_v5_trace.txt \
      apf_frontend_boot_backdrop_v5_pseudo_c.c; do
    cmp "reports/assets/apf_frontend_boot_backdrop_v5_ghidra/$name" \
      "$temporary/ghidra/$name"
  done

  generate_report \
    "$temporary/ghidra/apf_frontend_boot_backdrop_v5_trace.txt" \
    "$temporary/ghidra/apf_frontend_boot_backdrop_v5_pseudo_c.c" \
    "$temporary/apf_frontend_boot_backdrop_v5_full"
  cmp reports/assets/apf_frontend_boot_backdrop_v5.json \
    "$temporary/apf_frontend_boot_backdrop_v5_full.json"
  cmp reports/assets/apf_frontend_boot_backdrop_v5.tsv \
    "$temporary/apf_frontend_boot_backdrop_v5_full.tsv"
  cmp reports/assets/apf_frontend_boot_backdrop_v5_portme.c \
    "$temporary/apf_frontend_boot_backdrop_v5_full_portme.c"
  mode=full
fi

echo "APF_FRONTEND_BOOT_BACKDROP_V5_VALIDATION_PASS mode=$mode boundaries=6 boot_states=2 bundle_entries=157 bundle_layouts=30 portme=5"
