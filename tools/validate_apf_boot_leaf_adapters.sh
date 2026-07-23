#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

header='include/static_runtime/apf_boot_leaf_adapters.h'
source_file='src/static_runtime/apf_boot_leaf_adapters.c'
test_file='tests/apf_boot_leaf_adapters_test.c'
tool='tools/apf_boot_leaf_adapters_report.py'
report='reports/static_recomp/apf2k8_boot_leaf_adapters.json'
doc='docs/research/apf_boot_leaf_adapters.md'
frontier='reports/static_recomp/apf2k8_static_boot_import_frontier.json'
indirect_frontier='reports/static_recomp/apf2k8_boot_indirect_frontier.json'
imported_data_frontier='reports/static_recomp/apf2k8_imported_data_frontier.json'
xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
volume='extracted/All-Pro Football 2K8 (USA)/0A'
xenia='/media/noah/Storage/.codex-tmp/xenia-source'
xenon='tools/vendor/XenonRecomp'

for required in \
    "$header" "$source_file" "$test_file" "$tool" "$report" "$doc" \
    "$frontier" "$indirect_frontier" "$imported_data_frontier" \
    tools/apf_static_boot_import_frontier.py \
    reports/static_recomp/apf2k8_xex_dispatch_boundary.json \
    reports/headers/apf2k8_xex_report.json \
    reports/headers/apf2k8_xex_header.bin tools/xex_extract_pe.cpp \
    "$xenon/build/XenonUtils/libXenonUtils.a" \
    "$xenon/XenonUtils/xex.h" \
    "$xex" "$volume" CMakeLists.txt \
    tools/vendor/Cxbx-Reloaded/src/core/kernel/exports/EmuKrnlRtl.cpp \
    tools/vendor/Cxbx-Reloaded/src/core/kernel/exports/EmuKrnlKe.cpp \
    tools/vendor/Cxbx-Reloaded/src/core/kernel/common/types.h \
    "$xenia/src/xenia/kernel/xobject.h" \
    "$xenia/src/xenia/kernel/xevent.cc" \
    "$xenia/src/xenia/kernel/xevent.h" \
    "$xenia/src/xenia/kernel/util/object_table.cc" \
    "$xenia/src/xenia/kernel/util/object_table.h" \
    "$xenia/src/xenia/kernel/user_module.cc" \
    "$xenia/src/xenia/kernel/user_module.h" \
    "$xenia/src/xenia/kernel/util/shim_utils.h" \
    "$xenia/src/xenia/kernel/util/xex2_info.h" \
    "$xenia/src/xenia/kernel/kernel_state.cc" \
    "$xenia/src/xenia/kernel/xboxkrnl/xboxkrnl_debug.cc" \
    "$xenia/src/xenia/kernel/xboxkrnl/xboxkrnl_error.cc" \
    "$xenia/src/xenia/kernel/xboxkrnl/xboxkrnl_hal.cc" \
    "$xenia/src/xenia/kernel/xboxkrnl/xboxkrnl_memory.cc" \
    "$xenia/src/xenia/kernel/xboxkrnl/xboxkrnl_table.inc" \
    "$xenia/src/xenia/kernel/xboxkrnl/xboxkrnl_ob.cc" \
    "$xenia/src/xenia/kernel/xboxkrnl/xboxkrnl_rtl.cc" \
    "$xenia/src/xenia/kernel/xboxkrnl/xboxkrnl_strings.cc" \
    "$xenia/src/xenia/kernel/xboxkrnl/xboxkrnl_xconfig.cc" \
    "$xenia/src/xenia/kernel/xam/xam_info.cc" \
    "$xenia/src/xenia/kernel/xam/xam_table.inc" \
    "$xenia/src/xenia/kernel/xam/xam_ui.cc" \
    "$xenia/src/xenia/kernel/xthread.cc" \
    "$xenia/src/xenia/kernel/xthread.h" \
    "$xenia/src/xenia/memory.cc" \
    "$xenia/src/xenia/memory.h" \
    "$xenia/src/xenia/xbox.h" \
    "$xenia/LICENSE"; do
  test -f "$required"
done

test "$(sha256sum "$header" | awk '{print $1}')" = \
  '93e82f3ca93e0993f7686d901ebcd491c414ee9ccebccafb5c1da12d26580eb2'
test "$(sha256sum "$source_file" | awk '{print $1}')" = \
  '4e162c5b45e78665a63428033fc4b564740fb3753f222515028aa00c16829a10'
test "$(sha256sum "$test_file" | awk '{print $1}')" = \
  'c90fc1c2f09836a6edbef35e3396e1a108e9e9c759331b7f5d2fe47afc4c0f34'
test "$(sha256sum "$tool" | awk '{print $1}')" = \
  '727882e784340dc799c1b846b0c35bd5cd5990f5d29bab5a86e8383828a55cd4'
test "$(sha256sum "$doc" | awk '{print $1}')" = \
  'cd57c5a2deace28b3f38a221d0e15d9ebcd0fa5186b201f38ba1ac58d823f45d'
test "$(sha256sum "$report" | awk '{print $1}')" = \
  '6b7b7d65bb5d0cc5d90bc7dd4abb34b8b3a780a9e3be7e57afb1946a260f0b5e'

test "$(git -C "$xenia" rev-parse HEAD)" = \
  '95a5c3ee250f80c3b9d139658649d9ffb6db3eec'
git -C "$xenia" diff --quiet HEAD --
test "$(git -C "$xenon" rev-parse HEAD)" = \
  'ddd128bcca99fe8bfbb99bea583c972351fa6ace'
git -C "$xenon" diff --quiet HEAD --

expected_xex='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
expected_volume='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
test "$(sha256sum "$xex" | awk '{print $1}')" = "$expected_xex"
test "$(sha256sum "$volume" | awk '{print $1}')" = "$expected_volume"

temporary=$(mktemp -d /tmp/apf-boot-leaf-adapters.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
export PYTHONPYCACHEPREFIX="$temporary/pycache"

clang++-18 -std=c++20 -O2 \
  tools/xex_extract_pe.cpp \
  -I"$xenon/XenonUtils" \
  -I"$xenon/thirdparty/TinySHA1" \
  -I"$xenon/thirdparty/tiny-AES-c" \
  "$xenon/build/XenonUtils/libXenonUtils.a" \
  -o "$temporary/xex_extract_pe"
extraction=$("$temporary/xex_extract_pe" "$xex" "$temporary/apf.pe")
test "$extraction" = \
  'blocks=642 chunks=1648 lzx_bytes=37717546 image_bytes=54001664 window_size=32768'
test "$(sha256sum "$temporary/apf.pe" | awk '{print $1}')" = \
  'cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'
python3 - "$temporary/apf.pe" <<'PY'
from pathlib import Path
import sys

image = Path(sys.argv[1]).read_bytes()
expected = b"[XAPI RETURN VALUE] %d\n\0"
assert len(expected) == 24
assert image[0x024D37B8:0x024D37B8 + len(expected)] == expected
PY

python3 -m py_compile "$tool"
python3 "$tool" --json "$temporary/report.json"
cmp "$temporary/report.json" "$report"

python3 - "$report" "$frontier" "$indirect_frontier" "$source_file" "$doc" CMakeLists.txt <<'PY'
import hashlib
import json
from pathlib import Path
import re
import sys

report_path, frontier_path, indirect_path, source_path, doc_path, cmake_path = map(
    Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
frontier = json.loads(frontier_path.read_text(encoding="utf-8"))
indirect_frontier = json.loads(indirect_path.read_text(encoding="utf-8"))
source = source_path.read_text(encoding="utf-8")
doc = doc_path.read_text(encoding="utf-8")
cmake = cmake_path.read_text(encoding="utf-8")

assert report["schema"] == "apf2k8_boot_leaf_adapters/v7"
assert report["validation_date"] == "2026-07-11"
assert report["result"] == {
    "all_non_ok_statuses_stop_immediate_guest_continuation": True,
    "augmented_direct_static_call_site_count": 87,
    "classified_frontier_import_count": 30,
    "classified_static_call_site_count": 87,
    "dbgprint_implemented": True,
    "exception_required_import_count": 1,
    "exception_required_static_call_site_count": 2,
    "frontier_import_count": 30,
    "guest_title_code_executed": False,
    "normal_host_shell_links_adapter": False,
    "proved_indirect_import_dispatch_site_count": 4,
    "resumable_import_count": 24,
    "resumable_proved_indirect_dispatch_site_count": 4,
    "resumable_static_call_site_count": 76,
    "terminal_import_count": 4,
    "terminal_static_call_site_count": 8,
    "thread_create_required_import_count": 1,
    "thread_create_required_static_call_site_count": 1,
    "total_classified_import_dispatch_site_count": 91,
    "unresolved_indirect_runtime_surface_site_count": 7,
    "unsupported_frontier_import_count": 0,
    "unsupported_static_call_site_count": 0,
}

expected_resumable_sites = {
    "DbgPrint": ["0x84BE9EB4"],
    "ExGetXConfigSetting": ["0x84BE9B84", "0x84BE9BB4"],
    "KeGetCurrentProcessType": [
        "0x84BECCF8", "0x84BED908", "0x84BEDA78", "0x84BEED38",
        "0x84BEF2E8"],
    "KeTlsAlloc": ["0x84BDE6F8", "0x84BDEAE4"],
    "KeTlsFree": ["0x84BDE800"],
    "KeTlsGetValue": ["0x84BDE770", "0x84BDE868"],
    "KeTlsSetValue": ["0x84BDE788", "0x84BDEAFC"],
    "NtAllocateVirtualMemory": [
        "0x84BEBACC", "0x84BEBB1C", "0x84BEBB50", "0x84BEBE0C",
        "0x84BECE14", "0x84BED00C", "0x84BED050", "0x84BED0A0",
        "0x84BED7B8", "0x84BED808", "0x84BEE1CC"],
    "NtClose": ["0x84BE9A8C"],
    "NtCreateEvent": ["0x84BE7088", "0x84BE9A2C"],
    "NtFreeVirtualMemory": [
        "0x84BEBB70", "0x84BED10C", "0x84BED244", "0x84BED830",
        "0x84BEEF3C", "0x84BEF50C"],
    "NtQueryVirtualMemory": ["0x84BED6F8", "0x84BED750"],
    "NtWaitForSingleObjectEx": ["0x84BF0E3C"],
    "XamShowMessageBoxUIEx": ["0x84BE9A68"],
    "RtlCompareMemoryUlong": [
        "0x84BEC138", "0x84BEC1E4", "0x84BEC324", "0x84BEC3F0",
        "0x84BEC900", "0x84BECB74", "0x84BEF73C"],
    "RtlEnterCriticalSection": [
        "0x84B579CC", "0x84BDE26C", "0x84BEDADC", "0x84BEED8C",
        "0x84BEF3A0", "0x84BF0C6C", "0x84BF0CF0"],
    "RtlInitAnsiString": ["0x84BF0BAC", "0x84BF0DD4"],
    "RtlNtStatusToDosError": ["0x84BF0D64"],
    "RtlImageXexHeaderField": ["0x84BF1888"],
    "RtlInitializeCriticalSection": [
        "0x84B5796C", "0x84BDE614", "0x84BED954", "0x84D05740",
        "0x84D05778", "0x84D057B0"],
    "RtlLeaveCriticalSection": [
        "0x84B57A0C", "0x84BDE0C0", "0x84BDE20C", "0x84BEE164",
        "0x84BEE2F4", "0x84BEEF18", "0x84BEEFB4", "0x84BEFB04",
        "0x84BF0CA4", "0x84BF0D30"],
    "XGetAVPack": ["0x84BE9B4C"],
    "XGetLanguage": ["0x84BE9BD4"],
    "XexCheckExecutablePrivilege": ["0x84BE9B40"],
}
implemented = report["guest_abi"]["implemented_imports"]
assert report["guest_abi"]["integer_result_register"] == (
    "r3, sign-extended from 32 bits through all 64 bits")
assert "ResultBase<T>::Store" in report["guest_abi"][
    "pinned_xenia_result_extension"]
assert "s32/u32" in report["guest_abi"]["narrowed_control_flow_effect"]
assert {row["name"] for row in implemented} == set(expected_resumable_sites)
assert sum(row["static_call_sites"] for row in implemented) == 76
for row in implemented:
    assert [call["call_address"] for call in row["calls"]] == (
        expected_resumable_sites[row["name"]])
    assert row["static_call_sites"] == len(row["calls"])
assert sum(row["proved_indirect_static_sites"] for row in implemented) == 4

expected_terminal_sites = {
    "HalReturnToFirmware": ["0x84BF1994"],
    "KeBugCheck": ["0x84BDAA24"],
    "KeBugCheckEx": [
        "0x84BECD1C", "0x84BEDA9C", "0x84BEED5C", "0x84BEF30C"],
    "XamLoaderTerminateTitle": ["0x84BE9D50", "0x84BE9EC4"],
}
terminal = report["guest_abi"]["terminal_imports"]
assert {row["name"] for row in terminal} == set(expected_terminal_sites)
assert sum(row["static_call_sites"] for row in terminal) == 8
for row in terminal:
    assert row["resumable"] is False
    assert [call["call_address"] for call in row["calls"]] == (
        expected_terminal_sites[row["name"]])

expected_exception_sites = {
    "RtlRaiseException": ["0x84BEE284", "0x84BEFA84"]}
exception_required = report["guest_abi"]["exception_required_imports"]
assert {row["name"] for row in exception_required} == set(
    expected_exception_sites)
assert sum(row["static_call_sites"] for row in exception_required) == 2
for row in exception_required:
    assert row["resumable_without_seh"] is False
    assert [call["call_address"] for call in row["calls"]] == (
        expected_exception_sites[row["name"]])

thread_create_required = report["guest_abi"][
    "thread_create_required_imports"]
assert len(thread_create_required) == 1
assert thread_create_required[0]["name"] == "ExCreateThread"
assert thread_create_required[0]["thunk_address"] == "0x84D0876C"
assert thread_create_required[0][
    "resumable_without_scheduler_lifecycle"] is False
assert [call["call_address"] for call in thread_create_required[0]["calls"]] == [
    "0x84BF108C"]
assert thread_create_required[0]["calls"][0]["return_address"] == (
    "0x84BF1090")

xconfig = report["xconfig"]
assert xconfig["exact_variants"] == [
    {
        "buffer": "r1+84", "buffer_size": 4,
        "call_address": "0x84BE9B84", "category": 2,
        "required_size": "r1+80", "setting": 2,
        "value_source": "configured secured_av_region",
    },
    {
        "buffer": "r1+88", "buffer_size": 4,
        "call_address": "0x84BE9BB4", "category": 3,
        "required_size": "r1+80", "setting": 10,
        "value_source": "configured user_video_flags",
    },
]
assert xconfig["writes_per_successful_call"] == 2
assert xconfig["guest_status_on_success"] == "0x00000000"
assert "before either write" in xconfig["preflight_policy"]
assert xconfig["unobserved_variant_status"].startswith("unsupported_variant")

dbgprint = report["dbg_print"]
assert dbgprint == {
    "call_address": "0x84BE9EB4",
    "decoded_pe_sha256": (
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"),
    "exact_abi": "r3=0x844D37B8; r4=one signed 32-bit decimal",
    "format_address": "0x844D37B8",
    "format_bytes_including_nul": 24,
    "format_hex_including_nul": (
        "5b584150492052455455524e2056414c55455d2025640a00"),
    "format_literal": "[XAPI RETURN VALUE] %d\n",
    "format_rva": "0x024D37B8",
    "guest_memory_policy": (
        "all 24 bytes including NUL must be in bounds and byte-exact"),
    "mismatched_exact_address_bytes_status": "guest_state",
    "other_callsite_or_format_status": "unsupported_variant",
    "output_policy": (
        "record XAPI_RETURN_VALUE_S32 as a structured event; never pass "
        "guest bytes to a host format function"),
    "pinned_xenia_behavior": (
        "DbgPrint uses StackArgList and format_core, logs the formatted "
        "string, and returns X_STATUS_SUCCESS"),
    "return_address": "0x84BE9EB8",
    "success_result": "X_STATUS_SUCCESS (r3=0)",
}

xex_field = report["rtl_image_xex_header_field"]
assert xex_field["call_address"] == "0x84BF1888"
assert xex_field["return_address"] == "0x84BF188C"
assert xex_field["requested_key"] == "0x00020401"
assert xex_field["requested_key_name"] == "XEX_HEADER_DEFAULT_HEAP_SIZE"
assert xex_field["retail_optional_header_count"] == 15
assert xex_field["requested_key_present"] is False
assert xex_field["retail_prefix_bytes_parsed"] == 144
assert "0x00020401" not in xex_field["retail_optional_header_keys"]
assert xex_field["dynamic_guest_header_pointer"] == "r3; never guessed"
assert xex_field["fabricated_guest_pointer_or_heap_value"] is False
assert xex_field["success_result"] == (
    "NULL (r3=0) because the key is absent")
assert xex_field["other_key_or_callsite_status"] == "unsupported_variant"
assert xex_field["malformed_or_nonretail_prefix_status"] == "guest_state"

ansi = report["rtl_init_ansi_string"]
assert ansi["direct_call_sites"] == ["0x84BF0BAC", "0x84BF0DD4"]
assert ansi["guest_layout"] == {
    "0x00": "big-endian u16 Length",
    "0x02": "big-endian u16 MaximumLength",
    "0x04": "big-endian u32 Buffer guest pointer",
    "size": 8,
}
assert "NUL byte must occur" in ansi["source_bound_policy"]
assert "0xFFFE" in ansi["long_string_policy"]
assert "can wrap" in ansi["pinned_xenia_long_string_divergence"]
assert ansi["transactional_write"].startswith("preflight")
assert ansi["microsoft_contract"].startswith("https://learn.microsoft.com/")

config = report["explicit_configuration"]
assert config["all_values_required"] is True
assert config["apf_retail_system_flags"] == "0x00000200"
assert config["apf_early_privilege_query"] == 10
assert config["apf_retail_query_result"] is False
for key in [
    "av_pack_default", "language_default", "process_type_default",
    "secured_av_region_default", "user_video_flags_default",
    "vm_arena_default", "vm_backing_default", "vm_existing_ranges_default",
]:
    assert config[key] is None

critical = report["critical_sections"]
assert critical["candidate_layout"]["size"] == 28
assert critical["layout_confidence"].startswith(
    "cross-reference-derived candidate")
assert "16-byte dispatcher header" in critical[
    "layout_provenance"]["pinned_xenia"]
assert critical["frontier_call_sites"] == {
    "enter": [
        "0x84B579CC", "0x84BDE26C", "0x84BEDADC", "0x84BEED8C",
        "0x84BEF3A0", "0x84BF0C6C", "0x84BF0CF0"],
    "initialize": [
        "0x84B5796C", "0x84BDE614", "0x84BED954", "0x84D05740",
        "0x84D05778", "0x84D057B0"],
    "leave": [
        "0x84B57A0C", "0x84BDE0C0", "0x84BDE20C", "0x84BEE164",
        "0x84BEE2F4", "0x84BEEF18", "0x84BEEFB4", "0x84BEFB04",
        "0x84BF0CA4", "0x84BF0D30"],
}
assert critical["recursion_supported"] is True
assert critical["contention_policy"].startswith("scheduler_blocked")
assert critical["foreign_leave_policy"].startswith("guest_state")
assert critical["tail_failure_provenance"] == {
    "call_address": "0x84BDE0C0",
    "inherited_return_address": "0x84BD7C9C",
    "runtime_records_exact_static_call_address": True,
}
assert critical["host_atomic_or_pthread_lock_used"] is False
assert critical["microsoft_contract"].startswith("https://learn.microsoft.com/")

tls = report["tls"]
assert tls["allocation_slots"] == 2048
assert tls["guest_thread_capacity_in_bounded_adapter"] == 64
assert tls["host_thread_local_storage_used"] is False
assert tls["free_clears_all_registered_guest_threads"] is True

memory = report["guest_memory"]
assert memory == {
    "big_endian_ulong_loads": True,
    "big_endian_xconfig_ansi_and_critical_section_writes": True,
    "bounds_check_policy": "base/offset/length checked without 32-bit wrap",
    "memory_fault_is_fatal_dispatch_status": True,
    "writes_guest_memory": True,
}

vm = report["virtual_memory"]
assert vm["direct_call_site_count"] == 19
assert vm["all_calls_gated_by_exact_return_address"] is True
assert "initializes r24 to zero and never rewrites it" in vm[
    "dynamic_nozero_proof"]
assert vm["page_size"] == 65536
assert vm["pinned_xenia_large_heap"] == "[0x40000000, 0x7F000000)"
assert len(vm["allocate_call_sites"]) == 11
assert len(vm["free_call_sites"]) == 6
assert len(vm["query_call_sites"]) == 2
assert [row["call_address"] for row in vm["allocate_call_sites"]] == [
    "0x84BEBACC", "0x84BEBB1C", "0x84BEBB50", "0x84BEBE0C",
    "0x84BECE14", "0x84BED00C", "0x84BED050", "0x84BED0A0",
    "0x84BED7B8", "0x84BED808", "0x84BEE1CC",
]
assert sum(row["operation"] == "reserve"
           for row in vm["allocate_call_sites"]) == 4
assert vm["allocate_call_sites"][-1]["allocation_types"] == [
    "0x60001000", "0x60801000"]
assert [row["operation"] for row in vm["free_call_sites"]].count(
    "decommit") == 1
assert {row["information_size"] for row in vm["query_call_sites"]} == {28}
assert vm["loader_configuration"] == {
    "arena_base_and_size_required": True,
    "core_ranges_must_not_overlap_arena": True,
    "defaults": None,
    "existing_range_capacity": 16,
    "other_mapping_intersections_exclude_whole_arena_pages": True,
    "required_existing_range_kinds": [
        "title_image", "static_dispatch", "import_thunks"],
    "required_apf_coverage": {
        "title_image": "[0x82000000, 0x85380000)",
        "static_dispatch": "[0x85380000, 0x86133000)",
        "import_thunks": "[0x84D07B6C, 0x84D09040)",
    },
    "writable_backing_exactly_arena_size_required": True,
}
assert vm["ledger"]["maximum_pages"] == 16384
assert vm["ledger"]["maximum_allocations"] == 256
assert vm["ledger"]["collision_free_bottom_up_first_fit"] is True
assert vm["ledger"]["separate_from_title_dispatch_and_import_ranges"] is True
assert vm["allocation_semantics"]["commit_zero_gate"].startswith(
    "match pinned Xenia")
assert vm["allocation_semantics"][
    "nozero_preserves_newly_committed_backing"] is True
assert vm["query_layout"]["size"] == 28
assert "sign-extended NTSTATUS" in vm["guest_failure_policy"]
assert "before any output or ledger mutation" in vm["transactional_policy"]
assert vm["host_page_protection_enforced"] is False
assert vm["normal_host_shell_or_title_executed"] is False

event_group = report["event_handle_wait"]
assert event_group["direct_call_site_count"] == 4
assert [row["call_address"] for row in event_group["create_call_sites"]] == [
    "0x84BE7088", "0x84BE9A2C"]
assert [row["return_address"] for row in event_group["create_call_sites"]] == [
    "0x84BE708C", "0x84BE9A30"]
assert event_group["close_call_sites"] == [{
    "call_address": "0x84BE9A8C",
    "return_address": "0x84BE9A90",
    "shape": "r3=BE handle loaded from r1+124",
}]
assert event_group["wait_call_sites"][0]["call_address"] == "0x84BF0E3C"
assert event_group["wait_call_sites"][0]["return_address"] == "0x84BF0E40"
assert event_group["all_frontier_calls_gated_by_exact_return_address"] is True
assert event_group["handle_table"] == {
    "capacity": 64,
    "disjoint_from_title_dispatch_and_import_ranges": True,
    "first_handle": "0xF8000004",
    "namespace_base": "0xF8000000",
    "pinned_xenia_provenance": (
        "XObject::kHandleBase plus ObjectTable slot<<2"),
    "slot_zero_reserved": True,
    "stride": 4,
    "unknown_or_stale_handle_status": "0xC0000008",
}
assert event_group["named_event_layout"]["object_attributes_size"] == 12
assert event_group["named_event_layout"]["root_directory"] == "0xFFFFFFFC"
assert event_group["named_event_layout"]["maximum_retained_name_bytes"] == 255
assert event_group["named_event_layout"]["duplicate_retains_same_handle"] is True
assert event_group["event_semantics"] == {
    "auto_reset_consumes_signal": True,
    "event_type_0": "notification/manual-reset",
    "event_type_1": "synchronization/auto-reset",
    "invalid_handle_checked_before_timeout_pointer": True,
    "manual_reset_preserves_signal": True,
    "zero_timeout_unsignaled_result": "0x00000102",
}
assert event_group["wait_policy"] == {
    "deadline_apc_and_signal_wakeup": "PORTME",
    "host_thread_blocks": False,
    "null_or_negative_pending_wait": "scheduler_blocked",
    "positive_absolute_timeout": "unsupported_variant",
    "zero_relative_timeout": "immediate X_STATUS_TIMEOUT",
}
assert event_group["transactional_policy"].startswith("preflight")
assert event_group["title_executed"] is False

ui = report["message_box_ui"]
assert ui["name"] == "XamShowMessageBoxUIEx"
assert ui["thunk_address"] == "0x84D07EDC"
assert ui["direct_call_address"] == "0x84BE9A68"
assert ui["return_address"] == "0x84BE9A6C"
assert ui["caller"] == "sub_84BE99E0"
assert ui["parent_caller"] == "sub_84BE9B20"
assert ui["sole_direct_import_site"] is True
assert ui["register_arguments"] == {
    "r3": "255 (exact caller value)",
    "r4": "NULL title",
    "r5": "UTF-16 message at current r1+432",
    "r6": "1 button",
    "r7": "one big-endian pointer cell at current r1+204",
    "r8": "active button 0",
    "r9": "flags 1",
    "r10": "opaque UIEx argument 1",
}
assert ui["stack_arguments"] == {
    "r1+84": "big-endian pointer to eight-byte object at r1+104",
    "r1+92": "big-endian pointer to XAM_OVERLAPPED at r1+112",
}
assert ui["caller_pointer_graph"]["message"].endswith("current r1+432")
assert ui["caller_pointer_graph"]["button"].endswith("current r1+368")
assert ui["input_buffers"]["message"][
    "capacity_code_units_including_nul"] == 256
assert ui["input_buffers"]["button"][
    "capacity_code_units_including_nul"] == 32
assert ui["opaque_result_object"] == {
    "adapter_writes_selection": False,
    "address": "r1+104",
    "initial_state": "two zero big-endian dwords",
    "policy": (
        "validate and preserve; exact UIEx layout is not proved and the "
        "reached APF caller never consumes it"),
    "reachable_reads_after_import": 0,
    "size": 8,
}
assert ui["xam_overlapped"]["size"] == 28
assert ui["xam_overlapped"]["layout"] == {
    "0x00": "big-endian result",
    "0x04": "big-endian length",
    "0x08": "big-endian context",
    "0x0C": "big-endian event handle",
    "0x10": "big-endian completion routine",
    "0x14": "big-endian completion context",
    "0x18": "big-endian extended error",
}
assert ui["xam_overlapped"]["request_write"].startswith("result=997")
assert "signal exact event" in ui["xam_overlapped"]["completion_writes"]
assert "no guest thread handle is fabricated" in ui[
    "xam_overlapped"]["context_policy"]
assert ui["immediate_consumer"]["pending_value"] == 997
assert ui["immediate_consumer"]["helper_address"] == "0x84BE9230"
assert ui["immediate_consumer"]["helper_return_consumed_by_caller"] is False
assert ui["immediate_consumer"]["event_close_after_helper"] == {
    "call_address": "0x84BE9A8C",
    "return_address": "0x84BE9A90",
}
assert ui["request_boundary"] == {
    "automatic_or_default_selection": False,
    "dispatch_status": "ui_requested",
    "explicit_completion_selection": 0,
    "host_thread_blocks": False,
    "import_result_before_pause": 997,
    "maximum_pending_requests": 1,
    "requesting_guest_thread_latched": True,
    "resume_context": (
        "exact post-import context with r3=997; completed guest "
        "overlapped and signaled event are visible before continuation"),
}
assert ui["failure_policy"] == {
    "changed_result_overlapped_or_event_state": "guest_state",
    "failed_request_or_completion_is_transactional": True,
    "invalid_guest_pointer": "memory_fault",
    "wrong_callsite_or_argument_shape": "unsupported_variant",
}
assert ui["pinned_xenia_provenance"] == {
    "commit": "95a5c3ee250f80c3b9d139658649d9ffb6db3eec",
    "completion_sets_result_extended_error_length_and_event": True,
    "deferred_overlapped_sets_pending_and_thread_context": True,
    "kernel_overlapped_source": "src/xenia/kernel/kernel_state.cc",
    "kernel_overlapped_source_sha256": (
        "0cd0cf42c9dd4d48fbea5d19956d970723891b269bf4e544e026122948108880"),
    "overlapped_layout_source": "src/xenia/xbox.h",
    "overlapped_layout_source_sha256": (
        "a9348e9370aa9b1735413788ffc71bba229d3e22a1c5d7e36b77c3005e485d35"),
    "regular_dialog_completion_uses_explicit_choice": True,
    "regular_headless_mode_auto_selects_active_button": True,
    "regular_message_box_implemented": True,
    "regular_message_box_source": "src/xenia/kernel/xam/xam_ui.cc",
    "regular_message_box_source_sha256": (
        "15e53c8a3a6864c4a944329fcccef3327752196adf677dfd38ae3ecc9dabd4da"),
    "ui_ex_export_present": True,
    "ui_ex_implementation_present": False,
    "ui_export_table_source": "src/xenia/kernel/xam/xam_table.inc",
    "ui_export_table_source_sha256": (
        "d1f599dcabd14930f8f408d81fd6f97f7b3cc768923cf2ca27551fc1805dc1e0"),
}
assert "does not implement UIEx" in ui["evidence_limit"]
assert ui["guest_title_code_executed"] is False
assert ui["frontier_is_path_sensitive_boot_trace"] is False

thread_create = report["thread_creation_required"]
assert thread_create["dispatch_status"] == "thread_create_requested"
assert thread_create["resumable_without_scheduler_lifecycle"] is False
assert thread_create["frontier_import"] == {
    "call_address": "0x84BF108C",
    "direct_caller": "sub_84BF1048",
    "return_address": "0x84BF1090",
    "sole_direct_site_in_458_node_frontier": True,
    "thunk_address": "0x84D0876C",
    "upstream_chain": [
        "sub_84679E00", "sub_84B578D8", "sub_84BE84A0", "sub_84BF1048"],
}
assert thread_create["exact_xenon_abi"] == {
    "r3": "handle output at current r1+80",
    "r4": "requested stack size 0x0001C000",
    "r5": "thread ID output at current r1+176",
    "r6": "XAPI startup trampoline 0x84BF2930",
    "r7": "start address 0x84B57888",
    "r8": "dynamic start-context object",
    "r9": "creation flags 0 (not suspended; no processor mask)",
    "result": "signed NTSTATUS in r3",
}
assert thread_create["start_context_candidate"]["size_preflighted"] == 40
assert thread_create["start_context_candidate"]["layout"] == {
    "0x00": "0x820046D4 candidate vtable",
    "0x04": "0xFFFFFFFF handle sentinel before return",
    "0x08": "0x84502174 upstream value",
    "0x0C": "0",
    "0x10": "self pointer",
    "0x14": "0",
    "0x18": "self pointer",
    "0x1C": "0",
    "0x20": "128",
    "0x24": "0",
}
assert thread_create["immediate_consumer"] == {
    "failure_conversion": (
        "RtlNtStatusToDosError then wrapper returns handle value 0"),
    "generated_continuation_allowed_by_adapter": False,
    "signed_status_test": "negative branches to sub_84BF0D58",
    "success_handle_load": "big-endian handle from wrapper r1+80",
    "upstream_handle_store": "start-context +0x04",
}
assert thread_create["request_contract"] == {
    "complete_ppc_integer_context_preserved": True,
    "completion_api_available": False,
    "guest_entry_executed": False,
    "guest_stack_allocated": False,
    "guest_thread_object_allocated": False,
    "guest_tls_pcr_or_cpu_context_allocated": False,
    "handle_or_thread_id_output_written": False,
    "host_thread_created": False,
    "maximum_pending_requests": 1,
    "ntstatus_returned_to_guest": False,
    "reason_no_completion": (
        "the future scheduler must atomically accept ownership of all thread "
        "resources before success and either enqueue this creation_flags=0 "
        "thread or return a real failure NTSTATUS"),
    "requesting_guest_thread_latched": True,
}
assert thread_create["failure_policy"] == {
    "changed_start_context_candidate": "guest_state",
    "invalid_output_or_context_span": "memory_fault",
    "request_publication_is_transactional": True,
    "wrong_frontier_shape_or_nonfrontier_lr": "unsupported_variant",
}
assert thread_create["other_known_direct_site"] == {
    "adapter_policy": (
        "explicitly rejected by LR; no nonfrontier thread is created"),
    "call_address": "0x84BF759C",
    "caller": "sub_84BF7340",
    "creation_flags": (
        "X_CREATE_SUSPENDED plus one top-byte processor-affinity bit"),
    "downstream_consumers": [
        "ObReferenceObjectByHandle", "KeSetBasePriorityThread",
        "KeResumeThread", "ObDereferenceObject"],
    "in_458_node_frontier": False,
    "loop_count": 6,
    "return_address": "0x84BF75A0",
    "stack_size": 0,
    "start_addresses": ["0x84BF6EE0", "0x84BF6FA8"],
    "start_context": "NULL",
    "thread_id_pointer": "NULL",
    "xapi_thread_startup": "NULL",
}
assert thread_create["pinned_xenia_provenance"] == {
    "allocates_guest_object_stack_scratch_tls_pcr_cpu_state": True,
    "commit": "95a5c3ee250f80c3b9d139658649d9ffb6db3eec",
    "creates_host_thread_suspended_before_guest_policy_resume": True,
    "export_source": "src/xenia/kernel/xboxkrnl/xboxkrnl_threading.cc",
    "export_source_sha256": (
        "1b4b23d1eed5734e8c93965975b5256b3976707c59c698e696392773b71ce01d"),
    "export_table": "src/xenia/kernel/xboxkrnl/xboxkrnl_table.inc",
    "export_table_sha256": (
        "efe1609d2609007e38a905ea8a18ce68228d15610d2bc85d08a6e832fe224950"),
    "returns_handle_and_optional_thread_id_only_after_create": True,
    "thread_header": "src/xenia/kernel/xthread.h",
    "thread_header_sha256": (
        "1435d459dcb3cbe42be2d1095f3a4c8d42d277df14f2967efa2019105d2bd8f5"),
    "thread_source": "src/xenia/kernel/xthread.cc",
    "thread_source_sha256": (
        "5542763d8edcd08df500384a7b05011699262dc4b56ece756002c8fc99c04f49"),
    "x_create_suspended": "0x00000001",
    "x_kthread_size": "0xAB0",
}
assert thread_create["imported_data_frontier_evidence"] == {
    "all_thirteen_slots_resolved": False,
    "ex_thread_object_type_runtime_state": (
        "preserved retail ordinal 0x0001001B, not a guest object-type pointer; "
        "classified outside the current frontier"),
    "ex_thread_object_type_slot": "0x820008D8",
    "frontier_needed_slots_seeded": 2,
    "imported_data_files_modified": False,
    "nonfrontier_consumer_dependency": (
        "sub_84BF7340 loads 0x820008D8 before ObReferenceObjectByHandle"),
    "source": "reports/static_recomp/apf2k8_imported_data_frontier.json",
    "source_sha256": (
        "33055983b2104dc12ad5840161ce136887194474d70aec9ef9e67e0e8ee7b71b"),
}
assert thread_create["guest_title_code_executed"] is False
assert thread_create["frontier_is_path_sensitive_boot_trace"] is False

rtl = report["rtl_compare_memory_ulong"]
assert rtl["all_seven_augmented_frontier_calls_ignore_result"] is True
assert "leading matching bytes" in rtl["adapter_semantics"]
assert "increments once per matching ULONG" in rtl["pinned_xenia_divergence"]

status_map = report["rtl_nt_status_to_dos_error"]
assert status_map["thunk_address"] == "0x84D0864C"
assert status_map["direct_call_address"] == "0x84BF0D64"
assert status_map["return_address"] == "0x84BF0D68"
assert status_map["helper_address"] == "0x84BF0D58"
assert status_map["exact_callsite_gated"] is True
assert status_map["helper_preserves_input_r3_until_import"] is True
assert status_map["frontier_scope"] == {
    "source": "reports/static_recomp/apf2k8_boot_indirect_frontier.json",
    "total_nodes_including_imports": 458,
    "descended_generated_nodes": 426,
    "helper_caller_count": 3,
    "path_sensitive_boot_trace": False,
    "title_main_descended_or_executed": False,
}
assert [row["caller"] for row in
        status_map["augmented_frontier_helper_callers"]] == [
    "sub_84BE7038", "sub_84BF0E08", "sub_84BF1048"]
assert [(row["upstream_import"], row["upstream_call_address"],
         row["helper_call_address"], row["current_negative_statuses"])
        for row in status_map["augmented_frontier_helper_callers"]] == [
    ("NtCreateEvent", "0x84BE7088", "0x84BE70B4", ["0xC0000017"]),
    ("NtWaitForSingleObjectEx", "0x84BF0E3C", "0x84BF0E5C",
     ["0xC0000008"]),
    ("ExCreateThread", "0x84BF108C", "0x84BF1098", []),
]
assert status_map["current_resumable_negative_status_set"] == [
    "0xC0000008", "0xC0000017"]
assert [(row["ntstatus"], row["dos_error"])
        for row in status_map["bounded_mappings"]] == [
    ("0xC0000008", "0x00000006"),
    ("0xC0000017", "0x00000008"),
]
assert status_map["mapping_scope"].startswith("fail-closed two-entry")
assert status_map["unknown_ntstatus_treated_as_success"] is False
assert status_map["error_mr_mid_not_found_synthesized"] is False
assert "unsupported_variant" in status_map[
    "unknown_or_wrong_callsite_status"]
assert "sign- or zero-extended" in status_map["input_abi"]
assert "upper 32 bits" in status_map["result_abi"]
assert status_map["microsoft_contract"].startswith(
    "https://learn.microsoft.com/")
assert status_map["pinned_xenia_provenance"] == {
    "commit": "95a5c3ee250f80c3b9d139658649d9ffb6db3eec",
    "complete_table_copied": False,
    "fallback_317_adopted": False,
    "license": "BSD-3-Clause",
    "license_path": "LICENSE",
    "license_sha256": (
        "369ea6b0f7ba57544067e9d470ca82a927da787fb0a749b11cb55f1fd0ba47ae"),
    "mapping_source": "src/xenia/kernel/xboxkrnl/xboxkrnl_error.cc",
    "mapping_source_sha256": (
        "e0ac3f50ce4b7410557280f6fefb23c04b5ff717b9d563791bd2adc19b367b18"),
}

terminal_outcomes = report["terminal_outcomes"]
assert terminal_outcomes["dispatch_status"] == "terminal_outcome"
assert terminal_outcomes["resumable"] is False
assert terminal_outcomes[
    "guest_arguments_r3_through_r7_recorded_before_r3_is_cleared"] is True
assert terminal_outcomes["ke_bug_check_tail_branch"] == {
    "call_address": "0x84BDAA24",
    "inherited_lr": True,
    "runtime_records_exact_static_call_address": True,
}

exception_outcome = report["exception_dispatch_required"]
assert exception_outcome["dispatch_status"] == "exception_required"
assert exception_outcome["resumable_without_seh"] is False
assert exception_outcome[
    "exception_record_and_adapter_context_preserved"] == (
        "all 32 integer GPRs plus LR")
assert exception_outcome["guest_thread_latched_until_seh_exists"] is True

unsupported = report["fail_fast_frontier"]
assert unsupported == []
assert all(row["portme"].startswith(
    f"// PORTME at {row['thunk_address']}:") for row in unsupported)
frontier_names = {
    symbol.removeprefix("__imp__")
    for symbol in indirect_frontier["augmented_frontier"][
        "reachable_callable_imports"]
}
assert ({row["name"] for row in unsupported} |
        set(expected_resumable_sites) | set(expected_terminal_sites) |
        set(expected_exception_sites) |
        {row["name"] for row in thread_create_required}) == (
            frontier_names)

proved_indirect = report["guest_abi"]["proved_indirect_import_dispatches"]
assert [(row["call_address"], row["target_thunk_address"])
        for row in proved_indirect] == [
    ("0x84BDE7E4", "0x84D0837C"),
    ("0x84BDE878", "0x84D0835C"),
    ("0x84BDE8AC", "0x84D0836C"),
    ("0x84BDEB60", "0x84D0836C"),
]
assert all(row["dispatch_path"] == "proved_indirect_frontier"
           for row in proved_indirect)

unresolved_indirect = report["unresolved_indirect_runtime_surface"]
assert [row["call_address"] for row in unresolved_indirect] == [
    "0x8468CF4C", "0x84BDAA00", "0x84BDAFA0", "0x84BDDF90",
    "0x84BEBDEC", "0x84BF0C94", "0x84BF198C",
]
assert all(row["portme"].startswith(
    f"// PORTME at {row['call_address']}:") for row in unresolved_indirect)

source_portmes = re.findall(r"PORTME at (0x[0-9A-F]{8})", source)
partial_portme = report["partial_portme"]
assert len(partial_portme) == 13
assert {row["name"] for row in partial_portme} == {
    "ExGetXConfigSetting", "NtAllocateVirtualMemory",
    "NtFreeVirtualMemory", "NtQueryVirtualMemory", "NtCreateEvent",
    "NtClose", "NtWaitForSingleObjectEx",
    "RtlEnterCriticalSection", "RtlLeaveCriticalSection",
    "RtlRaiseException", "RtlNtStatusToDosError",
    "ExCreateThread", "XamShowMessageBoxUIEx",
}
assert all(row["portme"].startswith(
    f"// PORTME at {row['thunk_address']}:") for row in partial_portme)
assert len(source_portmes) == 13
assert set(source_portmes) == (
    {row["thunk_address"] for row in unsupported} |
    {row["thunk_address"] for row in partial_portme})
for forbidden in ["printf(", "fprintf(", "pthread", "thread_local", "exit(",
                  "abort("]:
    assert forbidden not in source
for required in [
    "VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED",
    "VC_APF_BOOT_LEAF_EXCEPTION_REQUIRED",
    "VC_APF_BOOT_LEAF_TERMINAL_OUTCOME",
    "VC_APF_BOOT_LEAF_UI_REQUESTED",
    "VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED",
    "vc_apf_failure_call_address",
    "vc_apf_store_be_u16",
    "vc_apf_store_be_u32",
    "vc_apf_guest_c_string_length",
    "VC_APF_ANSI_STRING_SIZE",
    "VC_APF_RTL_CRITICAL_SECTION_SIZE",
    "VC_APF_THUNK_DBG_PRINT",
    "VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD",
    "VC_APF_BOOT_DEBUG_EVENT_XAPI_RETURN_VALUE_S32",
    "vc_apf_dbg_print_xapi_return_format",
    "vc_apf_retail_xex_options",
    "VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY",
    "VC_APF_THUNK_NT_FREE_VIRTUAL_MEMORY",
    "VC_APF_THUNK_NT_QUERY_VIRTUAL_MEMORY",
    "VC_APF_THUNK_NT_CREATE_EVENT",
    "VC_APF_THUNK_NT_CLOSE",
    "VC_APF_THUNK_NT_WAIT_FOR_SINGLE_OBJECT_EX",
    "VC_APF_THUNK_RTL_NT_STATUS_TO_DOS_ERROR",
    "VC_APF_THUNK_XAM_SHOW_MESSAGE_BOX_UI_EX",
    "VC_APF_THUNK_EX_CREATE_THREAD",
    "VC_APF_BOOT_UI_MESSAGE_MAX_CODE_UNITS",
    "VC_APF_BOOT_UI_BUTTON_MAX_CODE_UNITS",
    "VC_APF_XAM_OVERLAPPED_SIZE",
    "VC_APF_X_ERROR_IO_PENDING",
    "VC_APF_BOOT_THREAD_START_CONTEXT_SIZE",
    "VC_APF_BOOT_FRONTIER_THREAD_STACK_SIZE",
    "VC_APF_BOOT_FRONTIER_XAPI_THREAD_STARTUP",
    "VC_APF_BOOT_FRONTIER_THREAD_START_ADDRESS",
    "VC_APF_BOOT_FIRST_EVENT_HANDLE",
    "vc_apf_nt_create_event",
    "vc_apf_nt_close",
    "vc_apf_nt_wait_for_single_object_ex",
    "vc_apf_rtl_nt_status_to_dos_error",
    "vc_apf_xam_show_message_box_ui_ex",
    "vc_apf_load_ui_utf16z",
    "vc_apf_boot_leaf_complete_message_box_ui",
    "vc_apf_ex_create_thread_request",
    "vc_apf_event_for_handle",
    "vc_apf_vm_initialize_ledger",
    "vc_apf_vm_allocate_site_type",
    "vc_apf_vm_free_site_type",
    "VC_APF_BOOT_VM_PAGE_SIZE",
    "VC_APF_RETAIL_TITLE_BASE",
    "VC_APF_STATIC_DISPATCH_BASE",
    "VC_APF_RETAIL_IMPORT_THUNK_BASE",
    "vc_apf_span_contains",
]:
    assert required in source

assert "VC_PORT_ENABLE_APF_BOOT_LEAF_TESTS" in cmake
assert "vc_apf_boot_leaf_adapter_tests" in cmake
main_start = cmake.index("add_executable(vc_football_port")
main_end = cmake.index("\n)", main_start)
assert "apf_boot_leaf_adapters" not in cmake[main_start:main_end]

for required in [
    "Twenty-four bounded",
    "All 87 direct import sites",
    "four proved indirect TLS dispatches",
    "No generated APF function",
    "There are no defaults",
    "Only the two variants physically reached",
    "Exact 64 KiB virtual-memory group",
    "Exact event, handle, and nonblocking wait group",
    "`0xF8000004`",
    "No Linux host thread sleeps",
    "case-insensitive reopen",
    "complete direct VM group",
    "no guessed base policy",
    "Every operation is preflighted",
    "reservation collision returns",
    "Host page protections are not yet",
    "Exact `DbgPrint` event and absent retail XEX field",
    "never forwards a guest-controlled host format string",
    "does not guess the",
    "invent a heap value",
    "Cross-reference-derived 28-byte critical-section candidate",
    "scheduler_blocked` without modifying any byte",
    "Explicit terminal and exception-dispatch outcomes",
    "captured context",
    "Bounds-checked `RtlInitAnsiString`",
    "sign-extending it through all 64 bits of PPC `r3`",
    "exact static call address instead of the incorrect",
    "Fail-closed `RtlNtStatusToDosError` subset",
    "Exact one-button `XamShowMessageBoxUIEx` boundary",
    "There is no automatic or default selection",
    "has no implementation there",
    "Typed `ExCreateThread` scheduler handoff",
    "There is deliberately no completion API yet",
    "The only other direct `ExCreateThread` instruction",
    "No import in the 30-symbol frontier now returns the generic",
    "The completed imported-data frontier is supporting evidence",
    "Seven unresolved indirect runtime-surface sites",
    "This does not execute `_xstart`",
]:
    assert required in doc
for row in unsupported:
    assert row["thunk_address"] in doc

inputs = report["inputs"]
assert inputs["pinned_xenia_commit"] == (
    "95a5c3ee250f80c3b9d139658649d9ffb6db3eec")
assert "src/xenia/kernel/util/shim_utils.h" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/user_module.cc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/util/xex2_info.h" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/xboxkrnl/xboxkrnl_strings.cc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/xboxkrnl/xboxkrnl_error.cc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/xam/xam_ui.cc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/xam/xam_table.inc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/kernel_state.cc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/xbox.h" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "LICENSE" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/xboxkrnl/xboxkrnl_memory.cc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/xboxkrnl/xboxkrnl_threading.cc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/xboxkrnl/xboxkrnl_table.inc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/xthread.cc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/xthread.h" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/xboxkrnl/xboxkrnl_ob.cc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/xevent.cc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/kernel/util/object_table.cc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert "src/xenia/memory.cc" in {
    row["path"] for row in inputs["pinned_xenia_sources"]}
assert inputs["retail_xex_sha256"] == (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f")
assert {row["path"] for row in inputs["generated_sources"]} == {
    "build-static-recomp-apf/ppc-filtered/ppc_recomp.14.cpp",
    "build-static-recomp-apf/ppc-filtered/ppc_recomp.215.cpp",
    "build-static-recomp-apf/ppc-filtered/ppc_recomp.216.cpp",
    "build-static-recomp-apf/ppc-filtered/ppc_recomp.217.cpp",
    "build-static-recomp-apf/ppc-filtered/ppc_recomp.219.cpp",
    "build-static-recomp-apf/ppc-filtered/ppc_recomp.193.cpp",
    "build-static-recomp-apf/ppc-filtered/ppc_recomp.214.cpp",
    "build-static-recomp-apf/ppc-filtered/ppc_recomp.234.cpp",
}
assert "reports/static_recomp/apf2k8_imported_data_frontier.json" in {
    row["path"] for row in inputs["local_sources"]}
for row in inputs["local_sources"]:
    path = Path(row["path"])
    assert path.stat().st_size == row["size"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]

contract = report["test_contract"]
for key in [
    "proves_big_endian_xconfig_value_and_size_writes",
    "proves_big_endian_ansi_string_layout",
    "proves_ansi_string_null_and_long_source_semantics",
    "proves_ansi_string_unterminated_source_is_transactional_fault",
    "proves_critical_section_candidate_28_byte_layout",
    "proves_critical_section_recursion",
    "proves_contention_and_foreign_leave_do_not_mutate",
    "proves_blocked_thread_retry_after_owner_release",
    "proves_duplicate_guest_thread_identity_is_rejected",
    "proves_no_generic_unsupported_frontier_imports",
    "proves_32bit_result_sign_extension",
    "proves_rtl_leave_tail_failure_site_is_exact",
    "proves_exception_context_is_latched_until_seh_exists",
    "proves_ke_bug_check_tail_site_is_typed_terminal",
    "proves_terminal_outcomes_never_return_ok",
    "proves_exact_dbgprint_structured_event",
    "proves_dbgprint_rejects_other_call_shapes_and_bytes",
    "proves_retail_xex_default_heap_key_is_absent",
    "proves_retail_xex_pointer_is_validated_not_guessed",
    "proves_vm_loader_configuration_has_no_defaults",
    "proves_vm_core_ranges_are_disjoint",
    "proves_vm_other_mapping_exclusion",
    "proves_vm_64k_rounding_and_big_endian_outputs",
    "proves_vm_reserve_commit_decommit_release_query",
    "proves_vm_commit_zero_and_nozero",
    "proves_vm_recommit_preserves_first_page_backing",
    "proves_vm_failures_are_transactional",
    "proves_vm_ntstatus_sign_extension",
    "proves_vm_unproved_call_shapes_fail_closed",
    "proves_event_handle_namespace_and_capacity",
    "proves_event_handle_big_endian_transactional_output",
    "proves_named_event_reopen_and_reference_close",
    "proves_manual_and_auto_reset_event_semantics",
    "proves_zero_timeout_and_pending_scheduler_boundary",
    "proves_event_ntstatus_sign_extension",
    "proves_rtl_ntstatus_two_entry_mapping",
    "proves_rtl_ntstatus_unknown_status_fails_closed",
    "proves_rtl_ntstatus_exact_callsite_gate",
    "proves_rtl_ntstatus_input_and_result_extension",
    "proves_ui_exact_callsite_arguments_and_pointer_graph",
    "proves_ui_request_has_no_automatic_selection",
    "proves_ui_pending_overlapped_and_event_completion",
    "proves_ui_completion_failures_are_transactional",
    "proves_ui_requesting_thread_is_latched",
    "proves_thread_create_exact_frontier_shape",
    "proves_thread_create_other_direct_site_is_rejected",
    "proves_thread_create_request_is_transactional",
    "proves_thread_create_outputs_and_guest_entry_are_untouched",
    "proves_thread_create_requesting_thread_is_latched",
]:
    assert contract[key] is True
assert contract["success_line"].endswith("unsupported_frontier_imports=0")
assert len(report["limits"]) == 10
PY

gcc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -Iinclude "$test_file" "$source_file" -o "$temporary/adapter_test"
"$temporary/adapter_test" > "$temporary/adapter.stdout" \
  2> "$temporary/adapter.stderr"
test ! -s "$temporary/adapter.stderr"
test "$(cat "$temporary/adapter.stdout")" = \
  'APF_BOOT_LEAF_ADAPTERS_PASS resumable_imports=24 terminal_imports=4 exception_imports=1 direct_sites=87 proved_indirect_import_sites=4 guest_threads=2 xconfig_writes=2 critical_sites=23 ansi_string_sites=2 be_compare_bytes=12 dbgprint_events=1 xex_absent=1 vm_sites=19 vm_pages=64 event_sites=4 event_capacity=64 ui_sites=1 ui_requests=1 thread_create_sites=1 thread_create_requests=1 unsupported_frontier_imports=0'

gcc -std=c11 -O1 -g -Wall -Wextra -Wpedantic -Wconversion -Wshadow \
  -Werror -fno-omit-frame-pointer -fsanitize=address,undefined,leak \
  -Iinclude "$test_file" "$source_file" -o "$temporary/adapter_sanitize"
ASAN_OPTIONS='detect_leaks=1:halt_on_error=1' \
UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1' \
LSAN_OPTIONS='exitcode=23' \
  "$temporary/adapter_sanitize" > "$temporary/sanitize.stdout" \
  2> "$temporary/sanitize.stderr"
test ! -s "$temporary/sanitize.stderr"
cmp "$temporary/adapter.stdout" "$temporary/sanitize.stdout"

gcc -std=c11 -O0 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -fanalyzer -Iinclude -c "$source_file" -o "$temporary/adapter_analyzer.o"

if nm -a "$temporary/adapter_test" | grep -Eq '(_xstart|sub_84|ppc_recomp)'; then
  echo 'isolated adapter test unexpectedly contains generated title symbols' >&2
  exit 1
fi

cmake -S . -B "$temporary/build" \
  -DBUILD_TESTING=ON \
  -DVC_PORT_ENABLE_APF_BOOT_LEAF_TESTS=ON \
  -DVC_PORT_ENABLE_GL_TESTS=OFF > "$temporary/cmake.log"
cmake --build "$temporary/build" --target vc_apf_boot_leaf_adapter_tests \
  -j "$(nproc)" > "$temporary/build.log"
ctest --test-dir "$temporary/build" \
  -R '^apf_boot_leaf_adapter_semantics$' --output-on-failure \
  > "$temporary/ctest.log"
grep -Fq '100% tests passed, 0 tests failed out of 1' "$temporary/ctest.log"

test "$(sha256sum "$xex" | awk '{print $1}')" = "$expected_xex"
test "$(sha256sum "$volume" | awk '{print $1}')" = "$expected_volume"
git -C "$xenia" diff --quiet HEAD --
git -C "$xenon" diff --quiet HEAD --

echo 'APF_BOOT_LEAF_ADAPTERS_VALIDATION_PASS resumable=24 terminal=4 exception_required=1 thread_create_required=1 direct_sites=87 proved_indirect_import_sites=4 xconfig=2 ansi=2 critical_sites=23 dbgprint=1 xex_absent=1 vm_sites=19 event_sites=4 event_capacity=64 ui_sites=1 ui_requests=1 thread_create_requests=1 rtl_status_mappings=2 unsupported=0 unresolved_indirect=7 title_executed=false originals_unchanged=true'
