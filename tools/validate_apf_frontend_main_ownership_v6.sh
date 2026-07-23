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
  tools/apf_frontend_main_ownership_v6.py

generate_report() {
  local trace="$1"
  local pseudo="$2"
  local prefix="$3"
  python3 tools/apf_frontend_main_ownership_v6.py \
    --apf-xex "extracted/All-Pro Football 2K8 (USA)/default.xex" \
    --apf-pe "$temporary/apf2k8_default.pe" \
    --outer-index "extracted/All-Pro Football 2K8 (USA)/0A" \
    --outer-manifest reports/manifests/apf_outer.json \
    --inner-candidates reports/manifests/apf_inner_candidates.tsv \
    --base-menu reports/assets/menu_state_trace.json \
    --base-closure reports/assets/menu_state_trace_closure_v2.json \
    --v5-report reports/assets/apf_frontend_boot_backdrop_v5.json \
    --trace "$trace" \
    --pseudo "$pseudo" \
    --json-out "$prefix.json" \
    --tsv-out "$prefix.tsv" \
    --portme-c-out "${prefix}_portme.c"
}

generate_report \
  reports/assets/apf_frontend_main_ownership_v6_ghidra/apf_frontend_main_ownership_v6_trace.txt \
  reports/assets/apf_frontend_main_ownership_v6_ghidra/apf_frontend_main_ownership_v6_pseudo_c.c \
  "$temporary/apf_frontend_main_ownership_v6"

cmp reports/assets/apf_frontend_main_ownership_v6.json \
  "$temporary/apf_frontend_main_ownership_v6.json"
cmp reports/assets/apf_frontend_main_ownership_v6.tsv \
  "$temporary/apf_frontend_main_ownership_v6.tsv"
cmp reports/assets/apf_frontend_main_ownership_v6_portme.c \
  "$temporary/apf_frontend_main_ownership_v6_portme.c"

for compiler in gcc clang-18; do
  "$compiler" -std=c11 -Wall -Wextra -Werror -c \
    reports/assets/apf_frontend_main_ownership_v6_portme.c \
    -o "$temporary/apf_frontend_main_ownership_v6_${compiler//[^a-zA-Z0-9]/_}.o"
done

python3 - <<'PY'
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


report = json.loads(Path("reports/assets/apf_frontend_main_ownership_v6.json").read_text())
assert report["schema"] == "vc_apf_frontend_main_ownership/v6"
assert report["scope"] == {
    "boot_frontend_sync_request_proved": True,
    "boot_static_path_to_team_select_proved": True,
    "cold_boot_to_main_menu_proved": False,
    "frontend_sync_outer_identity_proved": True,
    "launches_original_menu": False,
    "layout_mainmenu_runtime_instantiation_proved": False,
    "main_direct_layout_is_layout_mainmenu": False,
    "main_direct_layout_is_quicknav_proved": True,
    "orphan_main_wrapper_owner_proved": False,
    "team_select_owns_main_policy_argument_proved": True,
    "team_select_policy_constructs_main_proved": False,
    "writes_executable": False,
    "writes_ghidra_project": False,
}

source = report["source"]
assert source["xex_sha256"] == "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
assert source["reconstructed_pe_sha256"] == "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
assert source["reconstructed_pe"] == "apf2k8_default.pe"
assert {row["name"]: row["sha256"] for row in source["packs"]} == {
    "0A": "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "0B": "775bd47bbac3101938eb7f8b83bf1a71925776fb36b6ef4773ba4f8f6368df53",
    "1A": "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb",
    "1B": "04dd4a16240f94db79671b9f4a46bf60d7b23a2cfc3146e37a686587b6a0c084",
}

boundaries = {row["address"]: row for row in report["recovered_boundaries"]}
assert len(boundaries) == 15
assert boundaries["0x8467CA70"]["end_exclusive"] == "0x8467CB20"
assert boundaries["0x8468DA70"]["end_exclusive"] == "0x8468DB64"
assert boundaries["0x846DE230"]["end_exclusive"] == "0x846DE398"
assert boundaries["0x846F0058"]["end_exclusive"] == "0x846F0190"
assert boundaries["0x84A59B10"]["end_exclusive"] == "0x84A59BA4"
assert boundaries["0x84A56900"]["end_exclusive"] == "0x84A56950"

request = report["boot_frontend_sync_request"]
assert request["bootstrap_call"] == {"site": "0x84691BB8", "callee": "0x8467CA70"}
assert request["string_construction"]["cross_register_addi_site"] == "0x8467CAAC"
assert request["string_construction"]["result"] == "0x8450232C"
assert request["request"] == {
    "archive_name": "frontend_sync.iff",
    "callee": "0x8468DA70",
    "group_hash": "0x48181338",
    "group_hash_derivation": "CRC32 uppercase ASCII FRONTEND_SYNC",
    "manager": "0x84F43800",
    "request_object": "0x84D21F68",
    "site": "0x8467CACC",
}

bundle = report["frontend_bundle"]
assert bundle["outer_index"] == 1493
assert bundle["outer_name_id"] == "0xF69D21E4"
assert bundle["inner_index"] == 53
assert bundle["inner_name"] == "layout_mainmenu"
assert bundle["inner_file_id"] == "0x48C6D154"
assert bundle["inner_file_descriptor_offset"] == "0x0000065C"
assert bundle["part"] == {"block_index": 0, "offset": "0x001DF720", "length": "0x000002C0"}
assert bundle["decoded_payload_hash_hits"] == []
assert bundle["decoded_payload_name_hits"] == [{"block_index": 0, "offset": "0x001DF8B0"}]

boundary = report["boot_to_main_boundary"]
team = boundary["team_select_descriptor"]
assert team["address"] == "0x820F6D38"
assert team["exit_policy"] == "0x820F6D0C"
assert team["exit_policy_callback"] == "0x84A59B10"
assert team["exit_policy_argument"] == "0x820F4350"
assert boundary["policy_argument_audit"]["common_endpoint"] == "0x846F5518"
assert boundary["policy_argument_audit"]["result"] == \
    "exact Main-valued callback argument, but not an exact Main descriptor construction edge"
assert boundary["cold_boot_to_main_menu_proved"] is False

direct = report["main_direct_layout"]
assert direct["descriptor"] == "0x820F4350"
assert direct["descriptor_layout_name"] == "quicknav"
assert direct["descriptor_layout_crc32"] == "0x210FFA23"
assert direct["physical_resource"] == {"archive": "global.iff", "outer_index": 1310, "inner_index": 57}

scan = report["layout_mainmenu_cross_reference_audit"]
assert scan["outer_archive_count"] == 13
assert scan["layout_file_count"] == 161
assert scan["decoded_unique_block_bytes"] == 19668428
assert scan["hash_big_endian_hits"] == []
assert scan["utf16be_name_hits"] == [{
    "block_index": 0,
    "block_offset": "0x001DF8B0",
    "inner_index": 53,
    "inner_name": "layout_mainmenu",
    "outer_index": 1493,
    "part_offset": "0x00000190",
}]

orphan = report["orphan_main_wrapper"]
assert orphan == {
    "descriptor": "0x820F4350",
    "direct_branch_sites": [],
    "fullword_pointer_sites": [],
    "ghidra_references": [],
    "next_pdata_function": "0x84A56960",
    "owner_status": "unproved; exact code with no static incoming edge",
    "pdata_entry": None,
    "preceding_pdata_function_end_exclusive": "0x84A56950",
    "range": "0x84A56950..0x84A5695B",
    "tail_target": "0x846F60E8",
}

ghidra = report["ghidra"]
assert ghidra["read_only"] is True
assert ghidra["transient_rebuild_count"] == 10
assert ghidra["pseudo_warning_count"] == 2
assert ghidra["pseudo_portme_count"] == 1
assert len(report["portme"]) == 4

expected_hashes = {
    "reports/assets/apf_frontend_main_ownership_v6.json": "8b5d6862486bb03909550402d51814ec24cec20694151886de9e4a0b6290ef19",
    "reports/assets/apf_frontend_main_ownership_v6.tsv": "a564e062f1721325d5d758fc59a0d80768ffbdd33c6dd270e4b71214448dd13c",
    "reports/assets/apf_frontend_main_ownership_v6_portme.c": "7582502e3ebed10f8fc5bd26d04327ee87db3ce016e87c9e74b45ca82da4844d",
    "reports/assets/apf_frontend_main_ownership_v6_ghidra/apf_frontend_main_ownership_v6_trace.txt": "7d7f1cf9e3863455b31fa0cc1d1e428e560cf84cdd1bf24fc16d7607af660bad",
    "reports/assets/apf_frontend_main_ownership_v6_ghidra/apf_frontend_main_ownership_v6_pseudo_c.c": "2cd55e1f871593464e9150498c2738c84620ae65ce46119307459fe5ea2d7c12",
    "tools/ghidra_scripts/apf/ApfFrontendMainOwnershipV6.java": "9e09db818764ca3bd0da6fee1c70b54f1cc720d01159e36d0fa7aefbcd835754",
    "tools/apf_frontend_main_ownership_v6.py": "ee6a0fc8282815583f7e096296a0a0bd6714a53fb51a54cbccb21d42f3fdc940",
    "docs/research/apf_frontend_main_ownership_v6.md": "6901cb4132781d42f058f8c2ad00a296b5abf41602044307c1312ff024cda980",
}
for path, expected in expected_hashes.items():
    assert digest(path) == expected, (path, digest(path), expected)

portme = Path("reports/assets/apf_frontend_main_ownership_v6_portme.c").read_text()
assert portme.count("// PORTME:") == len(report["portme"])
doc = Path("docs/research/apf_frontend_main_ownership_v6.md").read_text()
for heading in ("## Worked", "## Failed or unproved", "## Blocking"):
    assert heading in doc
words = " ".join(doc.split()).lower()
assert "does not launch the retail menu" in words
assert "constructs the filename in a different register" in words
assert "not a proved main construction" in words
assert "direct layt path selects `quicknav`, not `layout_mainmenu`" in words
PY

mode=normal
if [[ "${APF_FRONTEND_MAIN_OWNERSHIP_V6_GHIDRA:-0}" == 1 ]]; then
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
      -postScript ApfFrontendMainOwnershipV6.java "$temporary/ghidra"

  for name in \
      apf_frontend_main_ownership_v6_trace.txt \
      apf_frontend_main_ownership_v6_pseudo_c.c; do
    cmp "reports/assets/apf_frontend_main_ownership_v6_ghidra/$name" \
      "$temporary/ghidra/$name"
  done

  generate_report \
    "$temporary/ghidra/apf_frontend_main_ownership_v6_trace.txt" \
    "$temporary/ghidra/apf_frontend_main_ownership_v6_pseudo_c.c" \
    "$temporary/apf_frontend_main_ownership_v6_full"
  cmp reports/assets/apf_frontend_main_ownership_v6.json \
    "$temporary/apf_frontend_main_ownership_v6_full.json"
  cmp reports/assets/apf_frontend_main_ownership_v6.tsv \
    "$temporary/apf_frontend_main_ownership_v6_full.tsv"
  cmp reports/assets/apf_frontend_main_ownership_v6_portme.c \
    "$temporary/apf_frontend_main_ownership_v6_full_portme.c"
  mode=full
fi

echo "APF_FRONTEND_MAIN_OWNERSHIP_V6_VALIDATION_PASS mode=$mode boundaries=15 layouts=161 portme=4 archive_owner=exact main_construction=unproved layout_owner=unproved"
