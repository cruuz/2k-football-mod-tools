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
  tools/apf_franchise_runtime_ownership.py

generate_report() {
  local trace="$1"
  local pseudo="$2"
  local prefix="$3"
  python3 tools/apf_franchise_runtime_ownership.py \
    --apf-xex "extracted/All-Pro Football 2K8 (USA)/default.xex" \
    --apf-pe "$temporary/apf2k8_default.pe" \
    --inner-candidates reports/manifests/apf_inner_candidates.tsv \
    --menu-state reports/assets/menu_state_trace.json \
    --cross-layout reports/assets/cross_title_layout_inventory.json \
    --localization-json reports/assets/apf_txt_localization.json \
    --localization-tsv reports/assets/apf_txt_localization.tsv \
    --toolchain-strings reports/headers/apf2k8_toolchain_strings.tsv \
    --trace "$trace" \
    --pseudo "$pseudo" \
    --json-out "$prefix.json" \
    --tsv-out "$prefix.tsv" \
    --portme-c-out "${prefix}_portme.c"
}

generate_report \
  reports/assets/apf_franchise_runtime_ownership_ghidra/apf_franchise_runtime_ownership_trace.txt \
  reports/assets/apf_franchise_runtime_ownership_ghidra/apf_franchise_runtime_ownership_pseudo_c.c \
  "$temporary/apf_franchise_runtime_ownership"

cmp reports/assets/apf_franchise_runtime_ownership.json \
  "$temporary/apf_franchise_runtime_ownership.json"
cmp reports/assets/apf_franchise_runtime_ownership.tsv \
  "$temporary/apf_franchise_runtime_ownership.tsv"
cmp reports/assets/apf_franchise_runtime_ownership_portme.c \
  "$temporary/apf_franchise_runtime_ownership_portme.c"

for compiler in gcc clang-18; do
  "$compiler" -std=c11 -Wall -Wextra -Werror -c \
    reports/assets/apf_franchise_runtime_ownership_portme.c \
    -o "$temporary/apf_franchise_runtime_ownership_${compiler//[^a-zA-Z0-9]/_}.o"
done

python3 - <<'PY'
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


report = json.loads(Path("reports/assets/apf_franchise_runtime_ownership.json").read_text())
assert report["schema"] == "vc_apf_franchise_runtime_ownership/v1"
assert report["scope"] == {
    "franchise_archive_request_compiled_proved": True,
    "franchise_assets_only": False,
    "franchise_code_compiled_proved": True,
    "half_finished_franchise_playable_proved": False,
    "launches_original_game": False,
    "retail_season_main_route_proved": True,
    "retail_season_old_franchise_gameplan_link_proved": True,
    "selected_nfl_espn_localization_display_proved": False,
    "standalone_franchise_entry_compiled_proved": True,
    "standalone_franchise_main_menu_route_proved": False,
    "standalone_franchise_static_owner_proved": False,
    "wrapup_descriptor_owns_franchise_requests_proved": True,
    "wrapup_retail_root_proved": False,
    "writes_executable": False,
    "writes_ghidra_project": False,
}

source = report["source"]
assert source["xex_sha256"] == "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
assert source["reconstructed_pe_sha256"] == "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
assert source["reconstructed_pe"] == "apf2k8_default.pe"

assert len(report["recovered_boundaries"]) == 13
boundaries = {row["address"]: row for row in report["recovered_boundaries"]}
assert boundaries["0x849DF2F0"]["end_exclusive"] == "0x849DF3E0"
assert boundaries["0x84A1FD00"]["end_exclusive"] == "0x84A1FDCC"
assert boundaries["0x84AEE800"]["end_exclusive"] == "0x84AEE9E8"
assert boundaries["0x84AEF1C0"]["end_exclusive"] == "0x84AEF340"
assert boundaries["0x84B00948"]["end_exclusive"] == "0x84B01574"

states = {row["name"]: row["descriptor_candidate"] for row in report["old_franchise_states"]}
assert len(states) == 9
assert states["FranchiseMenu_CoachsDesk"] == "0x820E0BC8"
assert states["FranchiseMenu_SimpleCoachsDesk"] == "0x820E0C10"
assert states["FranchiseMenu_CoachGameplan"] == "0x820E0B80"
assert states["FranchiseMenu_Weekly"] == "0x820E1908"

entry = report["standalone_franchise_entry"]
assert entry["mode_zero_target"] == "0x820E0BC8"
assert entry["mode_nonzero_target"] == "0x820E0C10"
assert entry["stack_push"] == "0x846F8A60"
assert entry["incoming_static_audit"] == {
    "classic_materializations": [],
    "direct_branches": [],
    "fullword_sites": ["0x844F1340"],
    "non_pdata_fullword_sites": [],
}

requests = {row["archive"]: row for row in report["archive_requests"]}
assert len(requests) == 6
assert requests["franchise.iff"]["call_site"] == "0x84A1FD6C"
assert requests["franchise.iff"]["request_hash"] == "0x68F0ED58"
assert requests["season.iff"]["call_site"] == "0x84A54A7C"
assert requests["franchise_show.iff"]["call_site"] == "0x84AEF220"
assert requests["franchise_show.iff"]["request_hash"] == "0xDACF91F0"
assert requests["franchise_show_intro.iff"]["call_site"] == "0x84AEF450"
assert requests["franchise_show_outro.iff"]["call_site"] == "0x84AEF510"

inventory = {row["archive"]: row for row in report["archive_inventory"]}
assert inventory["franchise.iff"]["outer_index"] == 810
assert inventory["franchise.iff"]["inner_file_count"] == 118
assert inventory["franchise.iff"]["type_counts"] == {
    "AUDO": 4, "LAYT": 29, "MRKS": 65, "SCNE": 8, "STRG": 1, "TXTR": 11,
}
assert inventory["franchise_show.iff"]["inner_file_count"] == 15
assert inventory["season.iff"]["inner_file_count"] == 19
assert inventory["trophyroom.iff"]["inner_file_count"] == 61

season = report["retail_season_reuse"]
assert season["main_row"]["label"] == "Season"
assert season["main_row"]["type"] == 11
assert season["main_row"]["target_descriptor"] == "0x820F4308"
assert season["old_gameplan_target_site"] == "0x84E55F10"
assert season["old_gameplan_descriptor"] == "0x820E0B80"

wrapup = report["wrapup_ownership"]
assert wrapup["descriptor"] == "0x820FAB68"
assert wrapup["event_1_callback"] == "0x84AEE800"
assert wrapup["event_3_callback"] == "0x84AEE9E8"
assert wrapup["route_static_audit"] == {
    "classic_materializations": [],
    "direct_branches": [{"kind": "jump", "site": "0x84AECE18"}],
    "fullword_sites": ["0x844F8578"],
    "non_pdata_fullword_sites": [],
}
assert wrapup["orphan_wrapper_direct_callers"] == []
assert wrapup["orphan_wrapper_fullword_sites"] == []

layouts = report["cross_title_franchise_layouts"]
assert layouts["apf_layout_count"] == 29
assert layouts["same_name_nfl_layout_count"] == 22
assert layouts["byte_identical_count"] == 0
assert len(layouts["matches"]) == 22

localization = report["selected_localization"]
assert len(localization["records"]) == 12
assert {row["text"] for row in localization["records"]} >= {
    "NFL", "PRESENTED BY ESPN", "Franchise/", "Draft", "OFF-SEASON", "TRADE REQUESTS",
}
assert all(row["display_call_site_proved"] is False for row in localization["records"])

retained = {row["address"]: row for row in report["retained_executable_strings"]}
assert "All-Pro Football 2K8 franchise" in retained["0x845F3268"]["text"]
assert "ESPN NFL 2K5" in retained["0x8461F500"]["text"]
assert "ESPN NFL 2K5" in retained["0x8461F730"]["text"]
assert all(row["retail_display_proved"] is False for row in retained.values())

ghidra = report["ghidra"]
assert ghidra["read_only"] is True
assert ghidra["transient_rebuild_count"] == 11
assert ghidra["pseudo_portme_count"] == 1
assert len(report["portme"]) == 5

expected_hashes = {
    "reports/assets/apf_franchise_runtime_ownership.json": "3e57d3bc84d88bc7765f98cf432507f5ca27813c8be59dd50a6cbc3a52a39e54",
    "reports/assets/apf_franchise_runtime_ownership.tsv": "c7e06aa47e910890d25f79a0ab82b8575adafc9f8422868c7b2f58b3fc1346be",
    "reports/assets/apf_franchise_runtime_ownership_portme.c": "17d762f33978182592d5361397596388c0ab7ffb5c5bedbe70d4ff102e424bd5",
    "reports/assets/apf_franchise_runtime_ownership_ghidra/apf_franchise_runtime_ownership_trace.txt": "c011520726af8548fd4c946a71ee7e22b3636e806bbebebdfc65306162eaf012",
    "reports/assets/apf_franchise_runtime_ownership_ghidra/apf_franchise_runtime_ownership_pseudo_c.c": "1997df7e210146ab57c26747b6a7498ead10c287fdbfd4c8686c3846dd81a375",
    "tools/ghidra_scripts/apf/ApfFranchiseRuntimeOwnershipTrace.java": "b4ec2b83473e8b4a81c7e93da06ff456ea8e359778eff263e1759dfab107b85d",
    "tools/apf_franchise_runtime_ownership.py": "9e462eae8e16262959725d7a2c406b50f465b2e2a0f0e0861328d2bd514419a3",
    "docs/research/apf_franchise_runtime_ownership.md": "e1a6f348d63f6d426c27c884470633fc0d8a776c7e5cba1eb42163d3e3a7050a",
}
for path, expected in expected_hashes.items():
    assert digest(path) == expected, (path, digest(path), expected)

portme = Path("reports/assets/apf_franchise_runtime_ownership_portme.c").read_text()
assert portme.count("// PORTME:") == len(report["portme"])
doc = Path("docs/research/apf_franchise_runtime_ownership.md").read_text()
for heading in ("## Worked", "## Failed or unproved", "## Blocking"):
    assert heading in doc
words = " ".join(doc.split()).lower()
assert "not assets-only" in words
assert "hidden playable franchise" in words
assert "standalone franchise initializer has no static incoming owner" in words
assert "retail season statically reuses an old franchise menu" in words
assert "does not modify `default.xex`" in words
PY

mode=normal
if [[ "${APF_FRANCHISE_RUNTIME_OWNERSHIP_GHIDRA:-0}" == 1 ]]; then
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
      -postScript ApfFranchiseRuntimeOwnershipTrace.java "$temporary/ghidra"

  for name in \
      apf_franchise_runtime_ownership_trace.txt \
      apf_franchise_runtime_ownership_pseudo_c.c; do
    cmp "reports/assets/apf_franchise_runtime_ownership_ghidra/$name" \
      "$temporary/ghidra/$name"
  done

  generate_report \
    "$temporary/ghidra/apf_franchise_runtime_ownership_trace.txt" \
    "$temporary/ghidra/apf_franchise_runtime_ownership_pseudo_c.c" \
    "$temporary/apf_franchise_runtime_ownership_full"
  cmp reports/assets/apf_franchise_runtime_ownership.json \
    "$temporary/apf_franchise_runtime_ownership_full.json"
  cmp reports/assets/apf_franchise_runtime_ownership.tsv \
    "$temporary/apf_franchise_runtime_ownership_full.tsv"
  cmp reports/assets/apf_franchise_runtime_ownership_portme.c \
    "$temporary/apf_franchise_runtime_ownership_full_portme.c"
  mode=full
fi

echo "APF_FRANCHISE_RUNTIME_OWNERSHIP_VALIDATION_PASS mode=$mode states=9 archives=6 layouts=29 cross_title=22 portme=5 standalone_owner=unproved wrapup_root=unproved"
