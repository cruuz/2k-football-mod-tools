#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

tool='tools/apf_xex_dispatch_boundary.py'
report='reports/static_recomp/apf2k8_xex_dispatch_boundary.json'
doc='docs/research/apf_xex_dispatch_boundary.md'
xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
config='build-static-recomp-apf/ppc-filtered/ppc_config.h'
mapping='build-static-recomp-apf/ppc-filtered/ppc_func_mapping.cpp'
xenon='tools/vendor/XenonRecomp'
xenia='/media/noah/Storage/.codex-tmp/xenia-source'

for required in "$tool" "$report" "$doc" "$xex" "$config" "$mapping" \
    tools/xex_extract_pe.cpp \
    "$xenon/build/XenonUtils/libXenonUtils.a" \
    "$xenon/XenonUtils/xex.h" "$xenon/XenonUtils/xex.cpp" \
    "$xenon/XenonRecomp/recompiler.cpp" "$xenon/XenonUtils/ppc_context.h" \
    "$xenia/src/xenia/kernel/util/xex2_info.h" \
    "$xenia/src/xenia/cpu/xex_module.h" \
    "$xenia/src/xenia/cpu/xex_module.cc" \
    "$xenia/src/xenia/kernel/user_module.cc" \
    "$xenia/src/xenia/memory.cc"; do
  test -f "$required"
done

temporary=$(mktemp -d /tmp/apf-xex-dispatch-boundary.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile "$tool"

inputs=(
  "$xex"
  "$config"
  "$mapping"
  tools/xex_extract_pe.cpp
  "$xenon/build/XenonUtils/libXenonUtils.a"
  "$xenon/XenonUtils/xex.h"
  "$xenon/XenonUtils/xex.cpp"
  "$xenon/XenonUtils/image.h"
  "$xenon/XenonRecomp/recompiler.cpp"
  "$xenon/XenonUtils/ppc_context.h"
  "$xenia/src/xenia/kernel/util/xex2_info.h"
  "$xenia/src/xenia/cpu/xex_module.h"
  "$xenia/src/xenia/cpu/xex_module.cc"
  "$xenia/src/xenia/kernel/user_module.cc"
  "$xenia/src/xenia/memory.cc"
)
sha256sum "${inputs[@]}" > "$temporary/before.sha256"

test "$(git -C "$xenon" rev-parse HEAD)" = \
  'ddd128bcca99fe8bfbb99bea583c972351fa6ace'
test "$(git -C "$xenia" rev-parse HEAD)" = \
  '95a5c3ee250f80c3b9d139658649d9ffb6db3eec'
git -C "$xenon" diff --quiet HEAD --
git -C "$xenia" diff --quiet HEAD --

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

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 "$tool" \
  --xex "$xex" \
  --pe "$temporary/apf.pe" \
  --xenonrecomp "$xenon" \
  --xenia "$xenia" \
  --config "$config" \
  --mapping "$mapping" \
  --json "$temporary/report.json"

cmp "$temporary/report.json" "$report"
sha256sum --check --status "$temporary/before.sha256"

python3 - "$report" "$doc" <<'PY'
import json
from pathlib import Path
import sys

report_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf2k8_xex_dispatch_boundary/v1"

result = report["result"]
assert result == {
    "authoritative_loaded_xex_span_proved": True,
    "security_image_size_equals_page_descriptor_span": True,
    "xenonrecomp_uses_security_span_for_decode_and_ppc_image_size": True,
    "xenia_primary_source_independently_corroborates_span": True,
    "dispatch_starts_at_loaded_span_exclusive_end": True,
    "loaded_title_byte_overlap_with_dispatch": 0,
    "pe_size_of_image_controls_xex_loader": False,
    "pe_declared_tail_is_loaded_title_bytes": False,
    "runtime_dynamic_allocation_mmio_collision_free_proved": False,
    "title_code_executed": False,
    "original_or_vendor_files_modified": False,
}

xex = report["xex_security_and_pages"]
assert xex["security_offset"] == "0x00000090"
assert xex["security_header_size"] == 0x4EC4
assert xex["security_header_end"] == "0x00004F54"
assert xex["load_address"] == "0x82000000"
assert xex["security_image_size"] == 0x03380000
assert xex["security_image_end_exclusive"] == "0x85380000"
assert xex["page_size_for_0x80000000_xex_heap"] == 0x10000
assert xex["page_descriptor_count"] == 824
assert xex["page_descriptor_count_by_type"] == {
    "code": 110, "read_write_data": 93, "read_only_data": 621}
assert xex["all_descriptor_page_counts"] == 1
assert xex["page_count_sum"] == 824
assert xex["descriptor_span_bytes"] == 0x03380000
assert xex["security_size_equals_descriptor_span"] is True
assert xex["descriptor_table_sha256"] == (
    "672db62025d2ebff99922949de735401fcc4090b88a370f5df8c611b9f76943a")
runs = xex["descriptor_runs"]
assert [(row["section_type_name"], row["page_count"],
         row["guest_start"], row["guest_end_exclusive"]) for row in runs] == [
    ("read_only_data", 611, "0x82000000", "0x84630000"),
    ("code", 110, "0x84630000", "0x84D10000"),
    ("read_write_data", 93, "0x84D10000", "0x852E0000"),
    ("read_only_data", 10, "0x852E0000", "0x85380000"),
]

pe = report["pe_metadata"]
assert pe["decoded_file_size"] == 0x03380000
assert pe["image_base"] == "0x82000000"
assert pe["section_alignment"] == 0x10000
assert pe["size_of_image"] == 0x03468C00
assert pe["size_of_image_end_exclusive"] == "0x85468C00"
assert pe["size_of_image_exceeds_xex_span_by"] == 953344
assert pe["size_of_image_alignment_remainder"] == 0x8C00
assert pe["size_of_image_is_section_aligned"] is False
assert pe["highest_declared_section"] == ".reloc"
assert pe["highest_declared_section_end_rva_exclusive"] == "0x033D9610"
assert pe["highest_section_exceeds_xex_span_by"] == 366096
assert pe["size_of_image_exceeds_highest_section_by"] == 587248

xenon = report["xenonrecomp_loader_contract"]
assert xenon["commit"] == "ddd128bcca99fe8bfbb99bea583c972351fa6ace"
assert xenon["tracked_sources_unchanged"] is True
assert xenon["pe_size_of_image_member_accesses_in_loader"] == 0
assert xenon["image_size_stored_from_security_image_size"]["line"] == 261
assert xenon["generated_ppc_image_size_from_image_size"]["line"] == 2533
assert xenon["dispatch_lookup_after_image_span"]["line"] == 110

xenia = report["xenia_primary_source_corroboration"]
assert xenia["commit"] == "95a5c3ee250f80c3b9d139658649d9ffb6db3eec"
assert xenia["tracked_sources_unchanged"] is True
assert xenia["xex_heap_for_apf_base"] == "v80000000"
assert xenia["xex_heap_page_size"] == 0x10000
assert xenia["pe_size_of_image_token_occurrences_in_src_xenia_cc_h"] == 0

dispatch = report["dispatch"]
assert dispatch["ppc_image_base"] == "0x82000000"
assert dispatch["ppc_image_size"] == 0x03380000
assert dispatch["ppc_code_base"] == "0x84630000"
assert dispatch["ppc_code_size"] == 0x006D904C
assert dispatch["dispatch_start"] == "0x85380000"
assert dispatch["dispatch_logical_bytes"] == 14360736
assert dispatch["dispatch_end_exclusive"] == "0x861320A0"
assert dispatch["dispatch_host_page_rounded_end_exclusive"] == "0x86133000"
assert dispatch["mapping_count"] == 60731
assert dispatch["maximum_mapped_guest_function"] == "0x84D0903C"
assert dispatch["last_populated_slot_end_exclusive"] == "0x86132080"
assert dispatch["loaded_title_byte_overlap"] == 0
assert dispatch["pe_size_of_image_metadata_overlap_bytes"] == 953344
assert dispatch["reloc_virtual_metadata_overlap_bytes"] == 366096
assert dispatch["runtime_collision_policy_implemented"] is False

assert len(report["portme"]) == 1
assert "dynamic allocator and MMIO" in report["portme"][0]
assert "move the XenonRecomp indirect table entirely host-side" in report["portme"][0]
assert report["sources"]["retail_or_decoded_bytes_embedded_in_report"] is False
assert report["sources"]["transient_decoded_pe"]["preserved"] is False
assert report["sources"]["extractor_source"]["sha256"] == (
    "26587b2c040efa6c92eda382d30fb8f050c0be0ce173b799442bd4517e3b2f73")
assert report["sources"]["xenonutils_library"]["sha256"] == (
    "0653cc0005ae3904e0c8e856678101dcf54d887a1f1f96702e7f5e5205692b37")
assert len(report["sources"]["generator"]["sha256"]) == 64

serialized = report_path.read_text(encoding="utf-8")
for forbidden in ('"decoded_bytes":', '"raw_page_bytes":',
                  '"rsa_signature_bytes":', '"executable_path":',
                  '"decoded_image_path":'):
    assert forbidden not in serialized, forbidden

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "authoritative loaded APF XEX image size",
    "zero loaded title bytes",
    "824 × 64 KiB",
    "metadata overlap, not title-byte overlap",
    "[0x85380000, 0x86133000)",
    "dynamic allocator",
    "lookup table entirely host-side",
    "No title entry point",
    "APF_XEX_DISPATCH_BOUNDARY_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

rm -f "$temporary/apf.pe" "$temporary/xex_extract_pe"
test ! -e "$temporary/apf.pe"
test ! -e "$temporary/xex_extract_pe"
sha256sum --check --status "$temporary/before.sha256"

echo 'APF_XEX_DISPATCH_BOUNDARY_VALIDATION_PASS xex_span=0x03380000 descriptors=824 dispatch=0x85380000 table_end=0x861320A0 loaded_overlap=0 pe_loader_authority=no runtime_collision=PORTME title_executed=no originals_unchanged=yes'
