#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

tool='tools/apf_static_boot_import_frontier.py'
report='reports/static_recomp/apf2k8_static_boot_import_frontier.json'
doc='docs/research/apf_static_boot_import_frontier.md'
original_xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
original_volume='extracted/All-Pro Football 2K8 (USA)/0A'

for required in "$tool" "$report" "$doc" "$original_xex" \
    "$original_volume" \
    reports/headers/apf2k8_xex_report.json \
    reports/static_recomp/apf2k8_static_recomp_all_tus.json \
    build-static-recomp-apf/ppc-filtered/ppc_func_mapping.cpp; do
  test -f "$required"
done

expected_xex='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
expected_volume='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
before_xex=$(sha256sum "$original_xex" | awk '{print $1}')
before_volume=$(sha256sum "$original_volume" | awk '{print $1}')
test "$before_xex" = "$expected_xex"
test "$before_volume" = "$expected_volume"

temporary=$(mktemp -d /tmp/apf-static-boot-frontier-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile "$tool"
python3 "$tool" --json "$temporary/report.json"
cmp "$temporary/report.json" "$report"

python3 - "$report" "$doc" <<'PY'
import json
from pathlib import Path
import sys

report_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf2k8_static_boot_import_frontier/v1"
assert report["result"] == {
    "boundary_stopped_callable_imports": 27,
    "boundary_stopped_total_nodes": 103,
    "callable_import_semantics_implemented": False,
    "entry_guest_address": "0x84BE9D08",
    "entry_symbol": "_xstart",
    "full_entry_direct_closure_total_nodes": 6917,
    "full_entry_reachable_callable_imports": 151,
    "generated_implementation_count": 60397,
    "global_direct_call_site_count": 116970,
    "global_indirect_dispatch_site_count": 3589,
    "global_unique_direct_edge_count": 85643,
    "indirect_targets_resolved": False,
    "mapping_count": 60731,
    "successful_boot_path_proved": False,
    "title_entry_executed": False,
}

inputs = report["inputs"]
assert inputs["numbered_source_count"] == 236
assert inputs["generated_cpp_manifest_sha256"] == (
    "5e90f504e1291e3bcc2ba2e3688da07d44ba7b7bfbf10ac62beffb48d1e79132"
)
assert inputs["complete_generated_tree_sha256"] == (
    "6ac280d3fa0c6f016011ff176089ddbee4df4077c366a69623d9556db0e54599"
)
assert inputs["mapping_source"] == {
    "path": "build-static-recomp-apf/ppc-filtered/ppc_func_mapping.cpp",
    "sha256": "9050c9a14781b40e0329ed9abca512f780cfba6ca709c8e8326397a66de6b5bd",
    "size": 1887998,
}
assert inputs["xex_report"]["sha256"] == (
    "dfd21f9db2fdb683b2dbd0390d351fdac84ba1e796a0e0c5e0e60c28827f3f1c"
)

surface = report["import_surface"]
assert surface == {
    "callable_thunks": 334,
    "callable_thunks_with_any_global_static_call": 333,
    "data_slots_participate_in_direct_call_graph": False,
    "global_callable_import_call_sites": 1708,
    "global_unique_callable_import_edges": 1407,
    "imported_data_slots": 13,
    "logical_imports": 347,
}
graph = report["global_direct_graph"]
assert graph == {
    "callable_import_call_sites": 1708,
    "direct_call_sites": 116970,
    "generated_call_sites": 115262,
    "generated_nodes": 60397,
    "indirect_dispatch_sites": 3589,
    "unique_callable_import_edges": 1407,
    "unique_direct_edges": 85643,
    "unique_generated_edges": 84236,
    "unclassified_direct_edges": 0,
}

full = report["full_entry_direct_closure"]
assert full["generated_nodes_including_opaque_boundaries"] == 6766
assert full["descended_generated_node_count"] == 6766
assert full["callable_import_nodes"] == 151
assert full["total_nodes_including_imports"] == 6917
assert full["direct_call_sites_from_descended_nodes"] == 27905
assert full["unique_direct_edges_from_descended_nodes"] == 19830
assert full["callable_import_call_sites"] == 423
assert full["unique_callable_import_edges"] == 356
assert full["indirect_dispatch_sites_in_descended_nodes"] == 939
assert full["descended_nodes_with_indirect_dispatch"] == 519
assert len(full["reachable_callable_imports"]) == 151
assert len(set(full["reachable_callable_imports"])) == 151

narrow = report["boundary_stopped_entry_closure"]
assert narrow["generated_nodes_including_opaque_boundaries"] == 76
assert narrow["opaque_boundary_node_count"] == 2
assert narrow["descended_generated_node_count"] == 74
assert narrow["callable_import_nodes"] == 27
assert narrow["total_nodes_including_imports"] == 103
assert narrow["direct_call_sites_from_descended_nodes"] == 183
assert narrow["unique_direct_edges_from_descended_nodes"] == 167
assert narrow["callable_import_call_sites"] == 60
assert narrow["unique_callable_import_edges"] == 49
assert narrow["indirect_dispatch_sites_in_descended_nodes"] == 15
assert narrow["descended_nodes_with_indirect_dispatch"] == 11
assert narrow["unclassified_direct_edge_count"] == 0
assert narrow["callable_imports_by_library"] == {
    "xam.xex": 4, "xboxkrnl.exe": 23,
}
assert narrow["static_import_call_sites_by_library"] == {
    "xam.xex": 5, "xboxkrnl.exe": 55,
}
assert narrow["opaque_boundaries"] == [
    {"role": "title_main", "symbol": "sub_84B8B1D0"},
    {"role": "post_main_teardown", "symbol": "sub_84BDAC80"},
]

expected_sites = {
    "DbgPrint": 1,
    "ExGetXConfigSetting": 2,
    "HalReturnToFirmware": 1,
    "KeBugCheckEx": 2,
    "KeGetCurrentProcessType": 3,
    "KeTlsAlloc": 1,
    "KeTlsFree": 1,
    "KeTlsGetValue": 2,
    "KeTlsSetValue": 2,
    "NtAllocateVirtualMemory": 11,
    "NtClose": 1,
    "NtCreateEvent": 1,
    "NtFreeVirtualMemory": 5,
    "NtQueryVirtualMemory": 2,
    "NtWaitForSingleObjectEx": 1,
    "RtlCompareMemoryUlong": 4,
    "RtlEnterCriticalSection": 4,
    "RtlImageXexHeaderField": 1,
    "RtlInitializeCriticalSection": 1,
    "RtlLeaveCriticalSection": 6,
    "RtlNtStatusToDosError": 1,
    "RtlRaiseException": 1,
    "XGetAVPack": 1,
    "XGetLanguage": 1,
    "XamLoaderTerminateTitle": 2,
    "XamShowMessageBoxUIEx": 1,
    "XexCheckExecutablePrivilege": 1,
}
frontier = narrow["frontier"]
assert len(frontier) == 27
assert {row["name"]: row["static_call_sites_in_boundary_stopped_closure"]
        for row in frontier} == expected_sites
assert sum(expected_sites.values()) == 60
assert all(row["callers"] for row in frontier)
assert all(row["distinct_callers_in_boundary_stopped_closure"] ==
           len(row["callers"]) for row in frontier)

sequence = report["entry_direct_call_sequence"]
assert sequence["implementation_source"] == "ppc_recomp.216.cpp"
assert sequence["internal_implementation_symbol"] == "__imp___xstart"
assert sequence["site_count"] == 13
assert sequence["execution_order_proved"] is False
assert [row["callee"] for row in sequence["calls_in_source_order"]] == [
    "__savegprlr_28", "sub_84BF1950", "sub_84BF0C50",
    "sub_84BE9B20", "__imp__XamLoaderTerminateTitle",
    "sub_84BDEA98", "sub_84BF17D8", "sub_84BF16F8",
    "sub_84BF1620", "sub_84B8B1D0", "sub_84BDAC80",
    "__imp__DbgPrint", "__imp__XamLoaderTerminateTitle",
]
assert [row["call_instruction_address"]
        for row in sequence["calls_in_source_order"]] == [
    "0x84BE9D0C", "0x84BE9D38", "0x84BE9D40", "0x84BE9D44",
    "0x84BE9D50", "0x84BE9D58", "0x84BE9D5C", "0x84BE9D64",
    "0x84BE9D8C", "0x84BE9E9C", "0x84BE9EA4", "0x84BE9EB4",
    "0x84BE9EC4",
]

limits = report["method_and_limits"]
assert limits["path_sensitivity"] is False
assert limits["failure_and_destructor_paths_filtered"] is False
assert limits["indirect_dispatch_target_inference"] is False
assert "Fifteen PPC_CALL_INDIRECT_FUNC" in limits["why_incomplete"]
assert len(report["portme"]) == 4
assert all("PORTME" in row for row in report["portme"])

serialized = report_path.read_text(encoding="utf-8")
for forbidden in (
    '"function_body"', '"source_text"', '"retail_bytes"',
    '"decoded_image"', '"replacement_bytes"',
):
    assert forbidden not in serialized

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "## Worked", "## Failed or unproved", "## Blocking", "## Validation",
    "60,397 function implementations", "85,643 unique direct",
    "6,917", "151 callable XEX imports", "103-node", "27 callable imports",
    "failure/destructor paths", "15 `PPC_CALL_INDIRECT_FUNC` sites",
    "not a proved sequence", "not asserted execution order",
    "APF_STATIC_BOOT_IMPORT_FRONTIER_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

after_xex=$(sha256sum "$original_xex" | awk '{print $1}')
after_volume=$(sha256sum "$original_volume" | awk '{print $1}')
test "$after_xex" = "$before_xex"
test "$after_volume" = "$before_volume"

echo 'APF_STATIC_BOOT_IMPORT_FRONTIER_VALIDATION_PASS implementations=60397 direct_edges=85643 full_nodes=6917 full_imports=151 bounded_nodes=103 bounded_imports=27 indirect_holes=15 title_entry=no runtime=no originals=unchanged'
