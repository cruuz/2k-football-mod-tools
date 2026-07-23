#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

tool='tools/apf_static_recomp_guest_image_bootstrap.py'
report='reports/static_recomp/apf2k8_static_recomp_guest_image_bootstrap.json'
doc='docs/research/apf_static_recomp_guest_image_bootstrap.md'
xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
mapping='build-static-recomp-apf/ppc-filtered/ppc_func_mapping.cpp'
config='build-static-recomp-apf/ppc-filtered/ppc_config.h'
for required in "$tool" "$report" "$doc" "$xex" "$mapping" "$config" \
    tools/xex_extract_pe.cpp \
    tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
    reports/headers/apf2k8_xex_report.json \
    reports/static_recomp/apf2k8_static_recomp_all_tus.json; do
  test -f "$required"
done

temporary=$(mktemp -d /tmp/apf-static-recomp-guest-image-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile "$tool"

xex_before=$(sha256sum "$xex")
mapping_before=$(sha256sum "$mapping")
config_before=$(sha256sum "$config")
before=$(find .codex-tmp -maxdepth 1 -type d \
  -name 'apf-guest-bootstrap-*' | wc -l)

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 "$tool" \
  --jobs 12 --json "$temporary/report.json"

after=$(find .codex-tmp -maxdepth 1 -type d \
  -name 'apf-guest-bootstrap-*' | wc -l)
test "$before" -eq "$after"
test "$xex_before" = "$(sha256sum "$xex")"
test "$mapping_before" = "$(sha256sum "$mapping")"
test "$config_before" = "$(sha256sum "$config")"
cmp "$temporary/report.json" "$report"

python3 - "$report" "$doc" <<'PY'
import json
from pathlib import Path
import sys

report_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf2k8_static_recomp_guest_image_bootstrap/v1"
assert report["result"] == {
    "untouched_xex_decoded": True,
    "decoded_image_exactly_loaded": True,
    "pe_section_header_count": 9,
    "section_backings_exactly_verified": 9,
    "generated_function_mappings_initialized": 60731,
    "generated_function_mappings_read_back": 60731,
    "entry_mapping_present": True,
    "data_import_slots_ledgered": 13,
    "data_import_slots_runtime_seeded": 0,
    "data_import_slots_preserved": 13,
    "tls_descriptor_verified": True,
    "title_entry_called": False,
    "translated_game_code_called": False,
    "native_game_boot_proved": False,
    "loaded_xex_dispatch_boundary_reconciled": True,
    "runtime_dispatch_collision_policy_implemented": False,
    "temporary_outputs_deleted": True,
}

space = report["guest_address_space"]
assert space["reservation_bytes"] == 0x100000000
assert space["reservation_flags"] == [
    "MAP_PRIVATE", "MAP_ANONYMOUS", "MAP_NORESERVE"]
assert space["initial_protection"] == "PROT_NONE"
assert space["final_touched_region_protection"] == "PROT_READ"
assert space["guest_pages_ever_host_executable"] is False
assert space["maximum_explicitly_writable_guest_bytes"] == 68366336
assert space["reservation_released"] is True

image = report["image"]
assert image["guest_image_base"] == "0x82000000"
assert image["xex_security_image_size"] == 54001664
assert image["xex_security_loaded_end"] == "0x85380000"
assert image["xex_security_header_size"] == 0x4EC4
assert image["xex_page_size"] == 0x10000
assert image["xex_page_descriptor_count"] == 824
assert image["xex_page_count_sum"] == 824
assert image["xex_page_descriptor_span_bytes"] == 0x03380000
assert image["xex_descriptor_table_sha256"] == (
    "672db62025d2ebff99922949de735401fcc4090b88a370f5df8c611b9f76943a")
assert image["xex_security_size_matches_page_descriptor_span"] is True
assert image["decoded_image_sha256"] == (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf")
assert image["guest_loaded_image_sha256"] == image["decoded_image_sha256"]
assert image["whole_image_memcmp_before_and_after_dispatch"] is True
assert image["pe_size_of_image"] == 54955008
assert image["pe_size_of_image_end"] == "0x85468C00"
assert image["pe_virtual_size_exceeds_decoded_span_by"] == 953344
assert image["pe_size_of_image_controls_xex_loader"] is False
assert image["pe_declared_tail_loaded_as_title_bytes"] is False
assert image["authoritative_loaded_span_reconciled"] is True
sections = image["sections"]
assert [row["name"] for row in sections] == [
    ".rdata", ".pdata", ".string_", ".text", ".data",
    ".XBMOVIE", ".idata", ".XBLD", ".reloc"]
assert [row["decoded_backed_size"] for row in sections] == [
    38648148, 147776, 1230811, 7180364, 6055148, 12, 1506, 176, 589312]
assert [row["unbacked_virtual_tail_size"] for row in sections] == [
    0, 0, 0, 0, 0, 0, 0, 0, 366096]
assert all(len(row["decoded_backing_sha256"]) == 64 for row in sections)
assert all(row["exact_guest_copy_verified"] is True for row in sections)

dispatch = report["dispatch"]
assert dispatch["generated_ppc_image_base"] == "0x82000000"
assert dispatch["generated_ppc_image_size"] == 54001664
assert dispatch["generated_ppc_code_base"] == "0x84630000"
assert dispatch["generated_ppc_code_size"] == 7180364
assert dispatch["dispatch_guest_offset"] == "0x85380000"
assert dispatch["dispatch_reserved_bytes"] == 14360736
assert dispatch["dispatch_end_exclusive"] == "0x861320A0"
assert dispatch["dispatch_host_page_rounded_end_exclusive"] == "0x86133000"
assert dispatch["loaded_title_byte_overlap"] == 0
assert dispatch["pe_size_of_image_metadata_overlap_bytes"] == 953344
assert dispatch["runtime_dynamic_allocation_mmio_collision_free_proved"] is False
assert dispatch["mapping_count"] == 60731
assert dispatch["strictly_sorted_unique_aligned_guest_addresses"] is True
assert dispatch["all_host_pointers_non_null"] is True
assert dispatch["all_roundtrips_exact"] is True
assert dispatch["entry_mapping_index"] == 55520
assert dispatch["entry_mapping_guest_address"] == "0x84BE9D08"
assert dispatch["entry_mapping_host_symbol"] == "_xstart"
assert dispatch["entry_function_pointer_invoked"] is False

tls = report["entry_and_tls"]
assert tls == {
    "xex_entry_point": "0x84BE9D08",
    "pe_entry_point": "0x84BE9D08",
    "entry_owned_by_text_section": True,
    "tls_slot_count": 64,
    "tls_raw_data_address": "0x00000000",
    "tls_data_size": 0,
    "tls_raw_data_size": 0,
    "tls_template_mapped": False,
    "thread_context_created": False,
}

ledger = report["imported_data_ledger"]
assert ledger["count"] == 13
assert ledger["runtime_values_seeded"] == 0
assert ledger["state"] == "explicitly_ledgered_unresolved_fail_closed"
assert ledger["all_original_ordinal_words_verified"] is True
assert ledger["all_slots_unchanged_after_dispatch_initialization"] is True
items = ledger["items"]
assert [row["name"] for row in items] == [
    "ExLoadedCommandLine", "XexExecutableModuleHandle", "KeTimeStampBundle",
    "ExTimerObjectType", "ExSemaphoreObjectType", "ExEventObjectType",
    "VdHSIOCalibrationLock", "VdGpuClockInMHz", "XboxKrnlVersion",
    "ExThreadObjectType", "VdGlobalDevice", "KeCertMonitorData",
    "KeDebugMonitorData"]
assert all(row["runtime_seed_state"] ==
           "unresolved_preserved_xex_ordinal" for row in items)
assert all(row["guest_valid_runtime_value_seeded"] is False for row in items)

build = report["build_observation"]
assert build["compiled_object_count"] == 239
assert build["compile_failure_count"] == 0
assert build["link_succeeded"] is True
assert build["undefined_guest_symbol_count"] == 0
assert build["fail_fast_callable_import_definitions"] == 334
assert build["decoded_image_preserved"] is False
assert build["executable_preserved"] is False
assert len(report["portme"]) == 4
assert all("PORTME" in row for row in report["portme"])
assert "dynamic allocator and MMIO" in report["portme"][1]
assert "move the XenonRecomp indirect table entirely host-side" in \
    report["portme"][1]
assert "reconcile XenonRecomp" not in report["portme"][1]

serialized = report_path.read_text(encoding="utf-8")
for forbidden in (
    '"raw_word"', '"replacement_bytes"', '"source_text"',
    '"decoded_bytes"', '"executable_path"', '"decoded_image_path"'):
    assert forbidden not in serialized, forbidden
assert report["sources"]["retail_or_decoded_bytes_embedded_in_report"] is False

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "## Worked", "## Failed or unproved", "## Blocking",
    "pre-execution loader checkpoint", "60,731 generated indirect function",
    "MAP_NORESERVE", "953,344-byte difference", "Zero slots receive invented",
    "Reconciled image-size boundary", "zero loaded-byte overlap",
    "[0x85380000, 0x86133000)", "dynamic allocator and MMIO",
    "does not call `_xstart`", "loader readiness, not a native APF boot",
    "APF_STATIC_RECOMP_GUEST_IMAGE_BOOTSTRAP_VALIDATION_PASS"):
    assert phrase in doc, phrase
PY

echo 'APF_STATIC_RECOMP_GUEST_IMAGE_BOOTSTRAP_VALIDATION_PASS image=exact sections=9 mappings=60731 data_ledger=13 seeded=0 tls=verified entry=no runtime=no cleanup=yes'
